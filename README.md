# VIPADSUZ · AutoXabar

**@auto_habar** kanalidagi AutoXabarBot xizmatining to‘liq veb-versiyasi.

Telegram akkauntingizni ulaysiz — tizim sizning e'loningizni siz a'zo bo‘lgan
barcha guruhlarga belgilangan interval bilan avtomatik yuboradi.

- **Narx:** 1 profil = 1 oy = **5 000 so‘m** (sozlamalardan o‘zgartiriladi)
- **To‘lov:** Click (SHOP API — UzCard / Humo, har 30 kunga alohida to‘lov)
- **Moliya:** har bir tushum yalpi → komissiya → **soliq 10%** → **sof foyda** ga ajratiladi,
  oylik hisobot va bankdan yechib olish hisobi yuritiladi

---

## 1. Ishga tushirish

### Docker bilan (tavsiya etiladi)

```bash
copy .env.example .env
```

```bash
docker compose up -d --build
```

Manzil: **http://127.0.0.1:8080** · loglar: `docker compose logs -f`

Ikkita konteyner ko‘tariladi: **nginx** (statik fayllar va reverse-proxy)
va **autoxabar** (gunicorn, faqat ichki tarmoqda). nginx `127.0.0.1:8080`
da tinglaydi — tashqariga serverning o‘z nginx‘i chiqaradi
(7-bo‘limga qarang). Portni `.env` dagi `APP_PORT` bilan o‘zgartirasiz.

Ma‘lumotlar ikkita volume‘da saqlanadi va `docker compose down` dan keyin
ham joyida qoladi:

| Volume | Nima saqlanadi |
|---|---|
| `autoxabar-data` | SQLite bazasi va Telegram sessiyalari |
| `autoxabar-uploads` | foydalanuvchi yuklagan rasmlar |

To‘xtatish: `docker compose down` · hamma narsani ma‘lumotlari bilan
o‘chirish: `docker compose down -v`

> `.env` fayli bo‘lmasa ham ishga tushadi, lekin `SECRET_KEY` va
> `ADMIN_PASSWORD` tasodifiy bo‘lib qoladi — avval `.env` ni to‘ldiring.

### Python bilan

```bash
pip install -r requirements.txt
```

```bash
python app.py
```

Manzil: **http://127.0.0.1:5000**

Birinchi admin `.env` faylidagi ma'lumotlar bilan avtomatik yaratiladi:

| | |
|---|---|
| Telefon | `ADMIN_PHONE` (sukut: `+998900000000`) |
| Parol | `ADMIN_PASSWORD` — `.env` da o'zingiz belgilaysiz |

> **Muhim:** `.env` da `ADMIN_PASSWORD` ko‘rsatilmasa, birinchi ishga tushishda
> tasodifiy parol yaratiladi va konsolga chiqariladi — uni yozib oling.
> `SECRET_KEY` ni ham albatta o‘zingizniki bilan almashtiring:
>
> ```bash
> python -c "import secrets; print(secrets.token_urlsafe(48))"
> ```

---

## 2. Sozlash (`.env`)

### Telegram (haqiqiy yuborish uchun shart)

`TELEGRAM_API_ID` va `TELEGRAM_API_HASH` ni <https://my.telegram.org> saytidan oling:

```
TELEGRAM_API_ID=1234567
TELEGRAM_API_HASH=abcdef0123456789abcdef0123456789
TELEGRAM_ENGINE=auto
```

Kalitlar bo‘lmasa tizim **DEMO rejimda** ishlaydi: saytning barcha bo‘limlarini
sinab ko‘rish mumkin, lekin haqiqiy xabar yuborilmaydi (tasdiqlash kodi: `12345`).

### Click — to‘lovni qabul qilish (SHOP API)

```
CLICK_MERCHANT_ID=<merchant ID>
CLICK_SERVICE_ID=<servis ID>
CLICK_MERCHANT_USER_ID=<merchant user ID>
CLICK_SECRET_KEY=<maxfiy kalit>
```

Bu to‘rttasini Click merchant kabinetidan olasiz. Servis sozlamalarida
ikkita manzilni ko‘rsatish kerak:

Click Prepare va Complete ni `action` maydoni bilan ajratadi, shuning
uchun **ikkala maydonga ham bitta manzil** yoziladi:

| Maydon | Manzil |
|---|---|
| **Prepare URL** | `https://dns.vipads.uz/api/payments/click/webhook` |
| **Complete URL** | `https://dns.vipads.uz/api/payments/click/webhook` |

Alohida manzil kerak bo‘lsa `/api/click/prepare` va `/api/click/complete`
ham ishlaydi.

Buyurtma raqami sifatida `payments.id` ishlatiladi — Click uni
`merchant_trans_id` maydonida qaytaradi, alohida sozlash shart emas.

Ikkala so‘rov ham `sign_string` (MD5) bilan tekshiriladi:

```
Prepare  : md5(click_trans_id + service_id + SECRET_KEY + merchant_trans_id
                + amount + action + sign_time)
Complete : md5(click_trans_id + service_id + SECRET_KEY + merchant_trans_id
                + merchant_prepare_id + amount + action + sign_time)
```

Hujjat: <https://docs.click.uz/shop-api/requests>

### Obunani yangilash

Click SHOP API faqat to‘lov havolasini beradi — kartani saqlab, keyin
o‘zimiz yechish imkoni yo‘q. Shuning uchun obuna **qo‘lda** yangilanadi:
muddat tugashiga 3 kun qolganda foydalanuvchiga eslatma boradi, u kabinetdan
Click orqali to‘laydi.

Kelajakda avtomatik yechim kerak bo‘lsa, `services/payme.py` dagi Subscribe
API kodi joyida turibdi (kalitlari bo‘sh) — yoki Click Merchant API ning
`card_token/*` metodlarini ulash mumkin.

### Moliya

```
PRICE_PER_PROFILE=5000     # 1 profil / oy
TAX_PERCENT=10             # foydadan soliq
ACQUIRING_PERCENT=1.0      # Payme komissiyasi
```

Bu qiymatlarni admin panelning **Sozlamalar** bo‘limidan ham o‘zgartirish mumkin.

---

## 3. Moliya qanday hisoblanadi

Har bir muvaffaqiyatli to‘lov `finance_ledger` jadvaliga quyidagicha yoziladi:

```
yalpi tushum                       5 000 so'm
 − Payme komissiyasi (1%)            −50 so'm
 ─────────────────────────────────────────────
 = hisobga tushgan summa           4 950 so'm
 − soliq (10%)                     −495 so'm
 ─────────────────────────────────────────────
 = SOF FOYDA                       4 455 so'm
```

Oylik darajada bundan **xarajatlar** ham ayriladi va natija —
«bankdan yechib olish mumkin bo‘lgan summa».

Admin → **Moliya** bo‘limida:

- oy bo‘yicha to‘liq taqsimot (yalpi / komissiya / soliq / xarajat / sof foyda)
- 12 oylik va 30 kunlik grafiklar
- har bir tushum yozuvi
- **yechib olishni qayd etish** (sof foyda va soliq alohida)
- xarajatlarni kiritish
- faol avto-obunalar asosida keyingi oy prognozi

Yechib olingan summalar qayd etilgani uchun «qancha tushdi / qancha yechildi /
qancha qoldi» har doim aniq ko‘rinadi.

---

## 4. Loyiha tuzilishi

```
app.py                  Flask ilovasi (factory, filtrlar, xatoliklar)
config.py               .env dan sozlamalar
core/
  db.py                 SQLite sxemasi va so'rov yordamchilari
  auth.py               sessiya, ruxsatlar, dekoratorlar
  utils.py              formatlash, CSRF, rate-limit, audit
services/
  click.py              Click SHOP API: Prepare / Complete + to'lov havolasi
  payme.py              Payme Merchant + Subscribe API (ishlatilmaydi, kalitlar bo'sh)
  billing.py            obunalar, to'lovlar, avto-uzaytirish
  finance.py            daftar, soliq, oylik hisobot, yechimlar
  telegram_engine.py    Telethon: ulash, guruhlar, yuborish (+ demo rejim)
  worker.py             yuborish sikli, aqlli dam olish, FloodWait
  scheduler.py          fon vazifalari (APScheduler)
blueprints/
  site.py               ochiq sahifalar
  auth_bp.py            kirish / ro'yxat / parol
  cabinet.py            foydalanuvchi kabineti
  admin.py              admin panel va moliya
  click_bp.py           /api/payments/click/webhook (+ prepare/complete)
  payme_bp.py           /api/payme kirish nuqtasi (ishlatilmaydi)
templates/  static/     Jinja2 shablonlari va dizayn tizimi
data/autoxabar.db       SQLite bazasi
Dockerfile              konteyner: python:3.12-slim, gunicorn, root'siz
docker-compose.yml      nginx + ilova, volume'lar bilan
.dockerignore           konteynerga tushmaydigan fayllar
nginx/                            KONTEYNER ichidagi nginx
  conf.d/00-forwarded.conf          X-Forwarded-Proto ni saqlab qolish
  conf.d/autoxabar.conf             server bloki (faqat HTTP, 80)
  snippets/app.conf                 proxy va statik fayl qoidalari
  snippets/upstream-real-ip.conf    host nginx'dan haqiqiy mijoz IP si
  snippets/cloudflare-real-ip.conf  HOST nginx uchun: CF-Connecting-IP
  snippets/cloudflare-only.conf     HOST nginx uchun: faqat CF'dan qabul qilish
nginx/host/                       SERVERNING O'Z nginx'i uchun namunalar
  avtoxabar.vipads.uz.conf.example  sayt: TLS + Cloudflare + proxy
  dns.vipads.uz-click.conf.example  Click webhook uchun location bloki
```

---

## 5. Fon vazifalari

`app.py` ishga tushganda APScheduler avtomatik yoqiladi:

| Vazifa | Davriylik | Nima qiladi |
|---|---|---|
| `tick` | 30 soniya | muddati kelgan profillarni yuborishga qo‘yadi |
| `counters` | 5 daqiqa | 24 soatlik va guruh hisoblagichlarini yangilaydi |
| `charge` | 30 daqiqa | avto-to‘lovlarni kartadan yechadi |
| `expire` | 60 daqiqa | muddati tugagan obunalarni yopadi |
| `cleanup` | har kuni 03:30 | 14 kundan eski jurnallarni tozalaydi |

Har birini admin → **Tizim holati** bo‘limidan qo‘lda ham ishga tushirish mumkin.

---

## 6. Akkaunt xavfsizligi

Telegram bloklanishining oldini olish uchun:

- guruhlar orasida tasodifiy **3–8 soniya** pauza
- **aqlli dam olish**: 1 soat ishlagach 3–5 daqiqa tanaffus
- **FloodWait** cheklovi aniqlansa profil avtomatik kutadi
- guruhda yozish taqiqlansa yoki akkaunt chiqarib yuborilsa — o‘sha guruh
  ro‘yxatdan avtomatik o‘chiriladi

Yangi akkauntlar uchun **10–15 daqiqalik interval** tavsiya etiladi.

---

## 7. Ishlab chiqarishga chiqarish

1. `.env` da `SECRET_KEY` ni uzun tasodifiy qatorga almashtiring
2. `ADMIN_PASSWORD` ni o‘zgartiring
3. `BASE_URL` ni haqiqiy domenga qo‘ying
4. HTTPS orqasiga qo‘ying (Click faqat HTTPS endpoint bilan ishlaydi)
5. `FLASK_DEBUG=0` ekanini tekshiring

Waitress bilan ishga tushirish (Windows uchun qulay):

```bash
pip install waitress
```

```bash
waitress-serve --host=0.0.0.0 --port=5000 app:app
```

Fon vazifalari (yuborish sikli, avto-to‘lov) `create_app()` ichida yoqiladi,
shuning uchun waitress/gunicorn ostida ham avtomatik ishlaydi.

> Bir nechta ishchi jarayon (worker) ishlatsangiz, ulardan faqat bittasida
> rejalashtiruvchi yonishi kerak — qolganlariga `.env` orqali
> `RUN_SCHEDULER=0` bering, aks holda xabarlar takroran yuboriladi.

### Docker + nginx bilan serverga qo‘yish

```bash
docker compose up -d --build
```

Ilova `--workers 1 --threads 8` bilan, root huquqisiz (`uid 10001`) ishlaydi
va tashqariga port chiqarmaydi — hamma so‘rov nginx orqali o‘tadi.
nginx `/static/` ni o‘zi beradi, qolganini gunicorn‘ga uzatadi.

**Proksi orqasida ishlash.** `TRUSTED_PROXIES=1` compose‘da o‘rnatilgan —
shunda ProxyFix `X-Forwarded-*` ni o‘qiydi va ilova haqiqiy mijoz IP sini
hamda `https` sxemasini ko‘radi. Busiz audit jurnaliga nginx‘ning ichki IP
si yoziladi va Click‘dan qaytish manzili `http://` bo‘lib qoladi.
Ilovani to‘g‘ridan-to‘g‘ri ochsangiz `TRUSTED_PROXIES=0` qiling, aks
holda har kim o‘z IP sini soxtalashtira oladi.

#### Domen va HTTPS

Ikki domen, bitta server (`185.80.234.161`):

```
Mijoz --HTTPS--> Cloudflare --> host nginx --> konteyner --> gunicorn
                                avtoxabar.vipads.uz

Click --HTTPS---------------->  host nginx --> konteyner --> gunicorn
                                dns.vipads.uz/api/payments/click/webhook
```

Docker to‘plami faqat `127.0.0.1:8080` da tinglaydi — tashqariga
serverning o‘z nginx‘i (nginx/1.24, Ubuntu) chiqaradi. TLS ham,
Cloudflare sozlamalari ham o‘sha yerda. Tayyor namunalar:

| Fayl | Nima uchun |
|---|---|
| `nginx/host/avtoxabar.vipads.uz.conf.example` | sayt uchun to‘liq server bloki |
| `nginx/host/dns.vipads.uz-click.conf.example` | Click webhook uchun `location` bloki |

Ularni serverga `/etc/nginx/sites-available/` ga qo‘ying, ichidagi
yo‘riqnomaga amal qiling, so‘ng `nginx -t && systemctl reload nginx`.

Brauzer ko‘radigan sertifikatni Cloudflare beradi. nginx‘dagi
sertifikat faqat Cloudflare bilan server orasidagi ulanish uchun, shuning
uchun **Cloudflare Origin Certificate** ishlatiladi — u 15 yil amal
qiladi va yangilanishi shart emas (certbot kerak emas).

**1. DNS.** Cloudflare → DNS → Records → Add record:
`A` · `avtoxabar` · `<server IP>` · Proxy status **Proxied** (to‘q sariq).

**2. Origin Certificate.** Cloudflare → SSL/TLS → Origin Server
→ Create Certificate. Hostname: `avtoxabar.vipads.uz`. Berilgan ikki
matnni serverga saqlang:

```
nginx/certs/origin.pem     <- Origin Certificate
nginx/certs/origin.key     <- Private Key   (chmod 600)
```

Bu papka `.gitignore` da — kalitlar repozitoriyga tushmaydi.

**3. SSL rejimi.** Cloudflare → SSL/TLS → Overview →
**Full (strict)**.

> «Flexible» qo‘ymang: Cloudflare serverga HTTP bilan murojaat qiladi,
> nginx esa HTTPS ga yo‘naltiradi — cheksiz redirect halqasi hosil
> bo‘ladi va sayt umuman ochilmay qoladi.

**4. nginx.** `nginx/conf.d/autoxabar-ssl.conf.example` ni
`autoxabar-ssl.conf` deb nomlang, `autoxabar.conf` dagi izohga amal qilib
HTTPS redirect‘ni yoqing, so‘ng `docker compose restart nginx`.

**5. Ilova.** `.env` da `BASE_URL=https://avtoxabar.vipads.uz`.
Click kabinetida Prepare va Complete maydonlarining ikkalasiga ham:

```
https://dns.vipads.uz/api/payments/click/webhook
```

**Haqiqiy mijoz IP si.** Cloudflare orqasida hamma so‘rov Cloudflare
serverlaridan keladi. `nginx/snippets/cloudflare-real-ip.conf` haqiqiy IP
ni `CF-Connecting-IP` sarlavhasidan oladi va bunga faqat Cloudflare
diapazonlaridan kelgan so‘rovlarda ishonadi. Diapazonlar o‘zgarsa
yangilang:

```bash
curl https://www.cloudflare.com/ips-v4 && curl https://www.cloudflare.com/ips-v6
```

**Ixtiyoriy himoya.** Server IP sini topib olgan odam Cloudflare‘ni
chetlab o‘tmasligi uchun `nginx/snippets/cloudflare-only.conf` ni
HTTPS blokiga include qiling — faqat DNS yozuvi «Proxied» ekaniga
ishonch hosil qilgandan keyin, aks holda sayt o‘zingizga ham yopiladi.

**Konteynerni ko‘paytirmang.** `--scale` yoki `replicas` ishlatilsa, fon
vazifalari har bir nusxada qaytadan ishlaydi va bitta profil bir necha marta
xabar yuboradi — Telegram akkaunti bloklanishi mumkin. Yuklama oshsa
`--threads` ni oshiring.

Yangilash:

```bash
git pull && docker compose up -d --build
```

Baza va sessiyalar volume‘da bo‘lgani uchun yangilashda yo‘qolmaydi.
Zaxira nusxa:

```bash
docker run --rm -v autoxabar_autoxabar-data:/data -v "%cd%":/backup alpine tar czf /backup/autoxabar-backup.tar.gz -C /data .
```

> Render‘da hozir Python runtime ishlatiladi (`render.yaml`). Docker‘ga
> o‘tmoqchi bo‘lsangiz, `runtime: python` ni `runtime: docker` ga
> almashtiring va `buildCommand` / `startCommand` qatorlarini o‘chiring —
> qolgan sozlamalar o‘zgarishsiz ishlaydi.

---

## 8. Render.com ga joylashtirish (ommaviy havola)

Repozitoriyda `render.yaml` bor, shuning uchun sozlash bir necha bosishdan iborat.

1. <https://render.com> ga kiring — **Get Started** → **GitHub** bilan ro'yxatdan o'ting
2. **New** → **Blueprint** → `autoxabar` repozitoriysini tanlang
3. Render `render.yaml` ni o'qiydi va quyidagi qiymatlarni so'raydi:

| Maydon | Nima yoziladi |
|---|---|
| `ADMIN_PHONE` | `+998900000000` (yoki o'z raqamingiz) |
| `ADMIN_PASSWORD` | kuchli parol o'ylab toping |
| `TELEGRAM_API_ID` | my.telegram.org dan olingan raqam |
| `TELEGRAM_API_HASH` | my.telegram.org dan olingan hash |
| `CLICK_*` | Click merchant kabinetidan olingan 4 ta qiymat |
| `BASE_URL` | deploydan keyin haqiqiy havola bilan to'ldiring |

4. **Apply** → 3–5 daqiqada `https://autoxabar.onrender.com` tayyor bo'ladi

Keyin **Environment** bo'limida `BASE_URL` ni haqiqiy havola bilan almashtiring
(Click'dan qaytish manzili shu asosda quriladi).

### Bepul tarifning cheklovlari

- **Uyqu rejimi.** 15 daqiqa hech kim kirmasa xizmat uxlaydi; keyingi ochilish
  ~30 soniya kutdiradi. Fon vazifalari ham shu paytda to'xtaydi — ya'ni
  xabar tarqatish uzluksiz ishlashi uchun pullik tarif kerak.
- **Ma'lumotlar saqlanmaydi.** Har deploydan keyin fayl tizimi tozalanadi va
  SQLite bazasi nolga qaytadi (foydalanuvchilar, profillar, to'lovlar o'chadi).

### Doimiy ish uchun

Xizmat jiddiy ishlaydigan bo'lsa:

1. Render'da **Starter** tarifga o'ting (uyqu yo'q)
2. **Disks** bo'limida doimiy disk ulang, masalan `/var/data`
3. **Environment** ga qo'shing:

```
DATA_DIR=/var/data
```

Shundan keyin baza deploylardan keyin ham saqlanadi.

> **Click’ni bepul tarifda ulamang.** Xizmat uxlab qolganda Prepare/Complete
> so‘rovlari timeout bo‘ladi va to‘lov Click tomonda qo‘lda tekshiruvga tushadi;
> bundan tashqari baza saqlanmagani uchun to‘lov tarixi yo‘qoladi.
> Avval Starter tarif + doimiy disk, keyin Click.
>
> Click servisidagi manzil (ikkala maydonga ham):
> `https://dns.vipads.uz/api/payments/click/webhook`

---

## 9. GitHub Pages — tanishtiruv sahifasi

Repozitoriyning `docs/` papkasida saytning **ochiq sahifalari** statik holda
saqlanadi (bosh sahifa, narxlar, qo'llanma, oferta, maxfiylik).

Ular <https://avazbek-011.github.io/autoxabar/> manzilida ko'rinadi — server
kerak emas, chunki bu sahifalarda ma'lumotlar bazasi ishlatilmaydi.

> Kabinet, admin panel va to'lovlar Python serverini talab qiladi — ular
> GitHub Pages'da ishlamaydi. Ular uchun Render (8-bo'lim) kerak.

Sahifalarni qayta yig'ish:

```bash
python build_static.py https://autoxabar.onrender.com
```

Argument sifatida haqiqiy dastur manzili beriladi — statik sahifadagi
«Boshlash» va «Kirish» tugmalari o'sha manzilga yo'naltiriladi.
Argument berilmasa, tugmalar Telegram botga olib boradi.
