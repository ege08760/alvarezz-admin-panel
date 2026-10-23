# ALVAREZZ Admin Panel — başlangıç paketi

Bu proje, mevcut Discord botundan ve Netlify sitesinden ayrı bir yönetim paneli başlangıcıdır. Panel; Discord OAuth2 ile giriş, yöneticisi olduğun ve botun bulunduğu sunucuları listeleme, ayarları SQLite veritabanına kaydetme ve dahili ayar API'si içerir.

**Önemli:** İlk sürüm ayarları panel veritabanına kaydeder. Botun canlı ayarlarına yansıtmak için `panel_bridge.py` bağlantısı ayrıca etkinleştirilmelidir. Premium durumu bu pakette yalnızca gösterim amaçlıdır; ödeme doğrulaması yapmaz.

## 1. Discord uygulaması ayarı

1. Discord Developer Portal'da ALVAREZZ uygulamanı aç.
2. OAuth2 bölümünde Client ID ve Client Secret bilgilerini al.
3. Redirect URL olarak tam panel adresini ekle: `https://SENIN-PANEL-ADRESIN/callback`
4. Botun sunucularda zaten bulunuyor olmalı. Girişte yalnızca `identify` ve `guilds` izinleri istenir.
5. Client Secret ve bot token'ını asla HTML/JavaScript içine yazma.

## 2. Ortam değişkenleri

1. `.env.example` dosyasını `.env` olarak kopyala.
2. `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `DISCORD_REDIRECT_URI`, `SESSION_SECRET`, `PANEL_API_KEY`, `DISCORD_BOT_TOKEN` değerlerini doldur.
3. `SESSION_SECRET` ve `PANEL_API_KEY` için birbirinden farklı, uzun ve tahmin edilemez değerler kullan.
4. `.env` dosyasını GitHub'a veya herkese açık bir yere yükleme.

## 3. Bilgisayarda test

Windows PowerShell'de bu klasöre gir:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn panel_app:app --host 127.0.0.1 --port 8000
```

Sonra tarayıcıda `http://127.0.0.1:8000` aç. Yerel testte HTTPS zorunlu çerezler nedeniyle OAuth callback için gerçek HTTPS adresi gerekir; çevrimiçi dağıtımda sağlayıcının HTTPS adresini kullan. Yerel arayüzü OAuth'suz görmek için geçici olarak `https_only=True` ayarını geliştirme ortamında kapatman gerekir; bunu üretimde kapatma.

## 4. Çevrimiçi yayın

Panel için Python/FastAPI çalıştırabilen bir uygulama barındırma hizmeti seç. Proje dosyalarını oraya yükle ve şu komutu kullan:

```bash
uvicorn panel_app:app --host 0.0.0.0 --port $PORT
```

Barındırma hizmetinin Environment Variables bölümüne `.env` değerlerini gir; `.env` dosyasını yüklemek yerine panelden secret olarak tanımlamak daha güvenlidir. Servis HTTPS sağlamalıdır. Sonra Discord Developer Portal'daki Redirect URL'yi gerçek `https://.../callback` adresiyle güncelle.

## 5. Mevcut ALVAREZZ botuyla bağlama

Panel ayarlarının botun SQLite ayarlarına aktarılması için:

1. `panel_bridge.py` dosyasını mevcut `main.py` dosyanın bulunduğu klasöre kopyala.
2. Bot klasöründeki `.env` dosyana şu iki değeri ekle:
   - `PANEL_BASE_URL=https://SENIN-PANEL-ADRESIN`
   - `PANEL_API_KEY=` panel sunucusunda kullandığın aynı anahtar
3. Bot klasöründe `aiohttp` kurulu değilse `pip install aiohttp` çalıştır.
4. `main.py` içinde, `bot.run(TOKEN)` satırından **hemen önce** aşağıdaki iki satırı ekle:

```python
from panel_bridge import attach
attach(bot, db)
```

5. Mevcut `main.py` dosyanı önce yedekle. Botu yeniden başlat. Konsolda hata olup olmadığını kontrol et.

Bridge, paneldeki hoş geldin kanalını, otomatik rolü, log ve öneri kanalını, davet/spam filtrelerini ve ticket alanlarını mevcut tablolarına aktarır. Panelde `welcome_message` ve `welcome_enabled` alanları saklanır ancak mevcut botun hoş geldin mesajı kodu henüz bu özelleştirilmiş metni kullanmaz. Bunları canlı kullanmak için `on_member_join` işleyicisine küçük bir uyarlama gerekir.

## 6. Güvenlik ve sınırlar

- Panel erişimi yalnızca Discord'da yönetici olduğun ve ALVAREZZ botunun bulunduğu sunucular için gösterilir.
- Bu bir başlangıç sürümüdür; ödeme sağlayıcısı, Premium lisans doğrulaması, ayrıntılı audit log ve CSRF koruması ayrıca tamamlanmalıdır.
- Gerçek kullanıcılarla kullanmadan önce HTTPS, secret yönetimi, erişim kontrolleri ve yedeklemeleri test et.
- Bot token'ını, Client Secret'ı veya `PANEL_API_KEY` değerini sohbete gönderme.
