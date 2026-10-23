import os
import json
import secrets
import sqlite3
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

load_dotenv()

CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "").strip()
REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "").strip()
SESSION_SECRET = os.getenv("SESSION_SECRET", "").strip()
PANEL_API_KEY = os.getenv("PANEL_API_KEY", "").strip()
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
OWNER_IDS = {x.strip() for x in os.getenv("PANEL_OWNER_IDS", "").split(",") if x.strip()}

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "panel.sqlite3"
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="ALVAREZZ Admin Panel")
if SESSION_SECRET:
    app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax", https_only=True, max_age=60 * 60 * 8)

DEFAULT_SETTINGS = {
    "welcome_enabled": True,
    "welcome_channel_id": "",
    "welcome_message": "Hoş geldin {user}! {server} sunucusuna katıldın. Üyemiz: {count}",
    "autorole_id": "",
    "log_channel_id": "",
    "suggestion_channel_id": "",
    "ticket_panel_channel_id": "",
    "ticket_category_id": "",
    "support_role_id": "",
    "invite_filter": False,
    "spam_filter": False,
    "premium_status": "inactive",
}

def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db_conn() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id TEXT PRIMARY KEY,
            settings_json TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")

init_db()

def config_ready():
    return bool(CLIENT_ID and CLIENT_SECRET and REDIRECT_URI and SESSION_SECRET and PANEL_API_KEY and BOT_TOKEN)

def current_user(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Önce Discord ile giriş yap.")
    return user

def allowed_guild_ids(request: Request) -> set[str]:
    ids = request.session.get("guild_ids", [])
    return {str(x) for x in ids}

def require_guild_access(request: Request, guild_id: str):
    user = current_user(request)
    if str(guild_id) not in allowed_guild_ids(request):
        raise HTTPException(status_code=403, detail="Bu sunucu için yönetici yetkin doğrulanmadı.")
    return user

def load_settings(guild_id: str) -> dict[str, Any]:
    with db_conn() as conn:
        row = conn.execute("SELECT settings_json FROM guild_settings WHERE guild_id=?", (str(guild_id),)).fetchone()
    settings = DEFAULT_SETTINGS.copy()
    if row:
        try:
            settings.update(json.loads(row["settings_json"]))
        except (ValueError, TypeError):
            pass
    return settings

def save_settings(guild_id: str, incoming: dict[str, Any]) -> dict[str, Any]:
    allowed = set(DEFAULT_SETTINGS)
    clean = {k: incoming[k] for k in allowed if k in incoming}
    settings = load_settings(guild_id)
    settings.update(clean)
    # IDs remain strings so long Discord snowflakes are never rounded.
    for key in ("welcome_channel_id", "autorole_id", "log_channel_id", "suggestion_channel_id",
                "ticket_panel_channel_id", "ticket_category_id", "support_role_id"):
        settings[key] = str(settings.get(key, "") or "").strip()
    settings["welcome_enabled"] = bool(settings.get("welcome_enabled"))
    settings["invite_filter"] = bool(settings.get("invite_filter"))
    settings["spam_filter"] = bool(settings.get("spam_filter"))
    settings["welcome_message"] = str(settings.get("welcome_message", ""))[:1500]
    # Premium is informational only; it cannot be activated from the client.
    settings["premium_status"] = "inactive"
    with db_conn() as conn:
        conn.execute("""INSERT INTO guild_settings(guild_id, settings_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id) DO UPDATE SET settings_json=excluded.settings_json, updated_at=CURRENT_TIMESTAMP""",
            (str(guild_id), json.dumps(settings, ensure_ascii=False)))
    return settings

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    if not config_ready():
        return HTMLResponse(
            "<h1>ALVAREZZ Admin kurulumu tamamlanmadı</h1><p>.env dosyasını .env.example üzerinden oluşturup Discord bilgilerini ekle.</p>",
            status_code=503
        )
    user = request.session.get("user")
    return templates.TemplateResponse("index.html", {"request": request, "user": user})

@app.get("/login")
async def login(request: Request):
    if not config_ready():
        raise HTTPException(503, "Önce .env ayarlarını tamamla.")
    state = secrets.token_urlsafe(24)
    request.session["oauth_state"] = state
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "identify guilds",
        "state": state,
    }
    from urllib.parse import urlencode
    return RedirectResponse("https://discord.com/oauth2/authorize?" + urlencode(params), status_code=302)

@app.get("/callback")
async def callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error:
        return RedirectResponse("/?error=discord_login_cancelled")
    expected = request.session.pop("oauth_state", None)
    if not code or not state or not expected or not secrets.compare_digest(state, expected):
        raise HTTPException(400, "OAuth doğrulaması başarısız. Tekrar giriş yap.")
    async with httpx.AsyncClient(timeout=15) as client:
        token_response = await client.post(
            "https://discord.com/api/oauth2/token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_response.status_code != 200:
            raise HTTPException(502, "Discord giriş kodu alınamadı. OAuth2 ayarlarını kontrol et.")
        token = token_response.json().get("access_token")
        user_response = await client.get("https://discord.com/api/users/@me",
                                         headers={"Authorization": f"Bearer {token}"})
        guild_response = await client.get("https://discord.com/api/users/@me/guilds",
                                          headers={"Authorization": f"Bearer {token}"})
        if user_response.status_code != 200 or guild_response.status_code != 200:
            raise HTTPException(502, "Discord kullanıcı veya sunucu bilgileri alınamadı.")
        user = user_response.json()
        guilds = guild_response.json()

        # Only allow guilds where the user is owner/admin and the bot is present.
        admin_guilds = []
        for guild in guilds:
            is_admin = guild.get("owner", False)
            try:
                perms = int(guild.get("permissions", "0"))
                is_admin = is_admin or bool(perms & 0x8)  # Administrator permission bit
            except (ValueError, TypeError):
                pass
            if not is_admin:
                continue
            gid = str(guild.get("id", ""))
            if not gid:
                continue
            # Confirm the ALVAREZZ bot can access this guild. Keep bot token server-side.
            bot_is_present = False
            try:
                check = await client.get(
                    f"https://discord.com/api/v10/guilds/{gid}",
                    headers={"Authorization": f"Bot {BOT_TOKEN}"}
                )
                bot_is_present = check.status_code == 200
            except httpx.HTTPError:
                bot_is_present = False
            if bot_is_present:
                admin_guilds.append({"id": gid, "name": guild.get("name", "Sunucu"),
                                     "icon": guild.get("icon"), "owner": bool(guild.get("owner"))})

    request.session.clear()
    request.session["user"] = {
        "id": str(user.get("id")),
        "username": user.get("global_name") or user.get("username") or "Admin",
        "avatar": user.get("avatar"),
    }
    request.session["guilds"] = admin_guilds
    request.session["guild_ids"] = [g["id"] for g in admin_guilds]
    return RedirectResponse("/", status_code=303)

@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)

@app.get("/api/guilds")
async def api_guilds(request: Request):
    current_user(request)
    return {"guilds": request.session.get("guilds", [])}

@app.get("/api/settings/{guild_id}")
async def api_get_settings(guild_id: str, request: Request):
    require_guild_access(request, guild_id)
    return {"guild_id": guild_id, "settings": load_settings(guild_id)}

@app.post("/api/settings/{guild_id}")
async def api_save_settings(guild_id: str, request: Request):
    require_guild_access(request, guild_id)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "Geçersiz ayar verisi.")
    settings = save_settings(guild_id, body)
    return {"ok": True, "settings": settings, "note": "Ayarlar panel veritabanına kaydedildi. Bot uygulaması için bridge bağlantısı gerekir."}

@app.get("/api/internal/settings")
async def internal_settings(x_panel_api_key: str | None = Header(default=None)):
    if not PANEL_API_KEY or not x_panel_api_key or not secrets.compare_digest(x_panel_api_key, PANEL_API_KEY):
        raise HTTPException(401, "Unauthorized")
    with db_conn() as conn:
        rows = conn.execute("SELECT guild_id, settings_json FROM guild_settings").fetchall()
    result = []
    for row in rows:
        try:
            result.append({"guild_id": row["guild_id"], "settings": json.loads(row["settings_json"])})
        except ValueError:
            continue
    return {"guilds": result}

@app.get("/health")
async def health():
    return {"ok": True, "service": "alvarezz-admin"}
