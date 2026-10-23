"""
Optional bridge for the existing ALVAREZZ discord.py bot.

This file polls the panel backend and syncs settings into the bot's existing
SQLite tables. It is deliberately separate from main.py to protect the user's
working bot. Follow README before enabling it.
"""
import os
import asyncio
import logging
import aiohttp
from discord.ext import tasks

log = logging.getLogger("alvarezz.panel_bridge")

def attach(bot, db):
    base_url = os.getenv("PANEL_BASE_URL", "").rstrip("/")
    api_key = os.getenv("PANEL_API_KEY", "").strip()
    if not base_url or not api_key:
        log.warning("Panel bridge kapalı: PANEL_BASE_URL / PANEL_API_KEY eksik.")
        return

    async def sync_once():
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                base_url + "/api/internal/settings",
                headers={"X-Panel-API-Key": api_key}
            ) as response:
                if response.status != 200:
                    log.warning("Panel bridge API yanıtı: %s", response.status)
                    return
                data = await response.json()
        for item in data.get("guilds", []):
            gid = int(item["guild_id"])
            if not bot.get_guild(gid):
                continue
            s = item.get("settings", {})
            # Existing table in ALVAREZZ main.py
            db.execute("""INSERT INTO sunucu_ayarlar(guild_id, welcome_channel_id, autorole_id, log_channel_id, suggestion_channel_id)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                welcome_channel_id=excluded.welcome_channel_id,
                autorole_id=excluded.autorole_id,
                log_channel_id=excluded.log_channel_id,
                suggestion_channel_id=excluded.suggestion_channel_id""",
                (gid, _id(s.get("welcome_channel_id")), _id(s.get("autorole_id")),
                 _id(s.get("log_channel_id")), _id(s.get("suggestion_channel_id"))))
            # Existing table in ALVAREZZ main.py
            db.execute("""INSERT INTO koruma_ayarlar(guild_id, invite_filter, spam_filter)
                VALUES(?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                invite_filter=excluded.invite_filter, spam_filter=excluded.spam_filter""",
                (gid, int(bool(s.get("invite_filter"))), int(bool(s.get("spam_filter")))))
            # Ticket settings table from the current ALVAREZZ package.
            db.execute("""INSERT INTO ticket_ayarlar(guild_id, panel_channel_id, category_id, support_role_id)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                panel_channel_id=excluded.panel_channel_id,
                category_id=excluded.category_id,
                support_role_id=excluded.support_role_id""",
                (gid, _id(s.get("ticket_panel_channel_id")), _id(s.get("ticket_category_id")),
                 _id(s.get("support_role_id"))))
        db.commit()

    def _id(value):
        value = str(value or "").strip()
        return int(value) if value.isdigit() else None

    @tasks.loop(minutes=1)
    async def poll():
        try:
            await sync_once()
        except Exception:
            log.exception("Panel ayarları eşitlenemedi.")

    @poll.before_loop
    async def before_poll():
        await bot.wait_until_ready()

    async def on_ready():
        if not poll.is_running():
            poll.start()

    bot.add_listener(on_ready, "on_ready")
