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
scripts/                          serverda ishlatiladi (7-bo'lim)
  deploy.sh                         .env tekshiruvi, zaxira, yig'ish, ishga tushirish
  backup.sh                         baza + sessiyalar + rasmlar zaxirasi
  restore.sh                        zaxiradan tiklash
.gitattributes                    .sh va sozlamalar doim LF bilan saqlanadi
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

## 7. Serverga joylashtirish

Ikki domen, bitta server (`185.80.234.161`, Ubuntu, o‘z nginx‘i bilan):

```
Mijoz --HTTPS--> Cloudflare --> host nginx --> konteyner nginx --> gunicorn
                                avtoxabar.vipads.uz

Click --HTTPS---------------->  host nginx --> konteyner nginx --> gunicorn
                                dns.vipads.uz/api/payments/click/webhook
```

Docker to‘plami faqat `127.0.0.1:8080` da tinglaydi — tashqariga
serverning o‘z nginx‘i chiqaradi. TLS ham, Cloudflare sozlamalari ham
o‘sha yerda.

| Skript | Nima qiladi |
|---|---|
| `scripts/deploy.sh` | `.env` ni yaratadi/tekshiradi, zaxira oladi, konteynerlarni yig‘ib ko‘taradi, sog‘lig‘ini tekshiradi |
| `scripts/backup.sh` | baza + Telegram sessiyalari + rasmlar → `backups/*.tar.gz` |
| `scripts/restore.sh` | arxivdan tiklaydi (oldin hozirgi holatdan zaxira oladi) |

### 7.1. Docker

Kerak: Docker Engine va Compose plagini **2.24** yoki yangirog‘i.
Serverda yo‘q bo‘lsa:

```bash
curl -fsSL https://get.docker.com | sh
```

### 7.2. Kodni serverga olib chiqish

Git orqali (tavsiya etiladi — keyin yangilash bitta buyruq):

```bash
git clone https://github.com/avazbek-011/autoxabar.git /opt/autoxabar
```

Git ishlatilmasa — kompyuterda arxiv yasab, `scp` bilan yuboring.
`git archive` faqat repozitoriydagi fayllarni oladi (`.env`, mahalliy
baza va sessiyalar tushmaydi) va qator oxirlarini Linux ko‘rinishida
saqlaydi:

```bash
git archive --format=tar.gz -o autoxabar.tar.gz HEAD
```

```bash
scp autoxabar.tar.gz root@185.80.234.161:/opt/
```

```bash
mkdir -p /opt/autoxabar && tar xzf /opt/autoxabar.tar.gz -C /opt/autoxabar
```

> Papkani Windows‘dan to‘g‘ridan-to‘g‘ri nusxalamang: mahalliy `.env`,
> baza va Telegram sessiyalari ham ketib qoladi, `.sh` fayllar esa
> Windows qator oxirlari (CRLF) bilan ishlamaydi.

### 7.3. Ilovani ishga tushirish

```bash
cd /opt/autoxabar && ./scripts/deploy.sh
```

Birinchi ishga tushishda skript `.env` yaratadi: `SECRET_KEY` va
`ADMIN_PASSWORD` tasodifiy qiymat bilan to‘ldiriladi,
`BASE_URL=https://avtoxabar.vipads.uz` qo‘yiladi, admin paroli ekranga
chiqariladi va skript to‘xtaydi. `.env` ni tahrirlang (`nano .env`):

| Kalit | Nima yoziladi |
|---|---|
| `ADMIN_PHONE` | o‘z raqamingiz (admin shu raqam bilan kiradi) |
| `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` | <https://my.telegram.org> — bo‘lmasa DEMO rejim |
| `CLICK_MERCHANT_ID`, `CLICK_SERVICE_ID`, `CLICK_MERCHANT_USER_ID`, `CLICK_SECRET_KEY` | Click merchant kabinetidan |

va skriptni qayta ishga tushiring. U `.env` ni tekshiradi (bo‘sh
`SECRET_KEY`, `FLASK_DEBUG=1` kabi xatolarda to‘xtaydi, bo‘sh Telegram /
Click kalitlari haqida ogohlantiradi), konteynerlarni yig‘adi, ilova
sog‘lom bo‘lguncha kutadi va `127.0.0.1:8080` javob berayotganini
tekshiradi.

### 7.4. Cloudflare va host nginx

Brauzer ko‘radigan sertifikatni Cloudflare beradi. Host nginx‘dagi
sertifikat faqat Cloudflare bilan server orasidagi ulanish uchun, shuning
uchun **Cloudflare Origin Certificate** ishlatiladi — u 15 yil amal
qiladi, certbot kerak emas.

**1. DNS.** Cloudflare → DNS → Records → Add record:
`A` · `avtoxabar` · `185.80.234.161` · Proxy status **Proxied** (to‘q sariq).

**2. Origin Certificate.** Cloudflare → SSL/TLS → Origin Server
→ Create Certificate. Hostname: `avtoxabar.vipads.uz`. Berilgan ikki
matnni serverga saqlang:

```
/etc/ssl/cloudflare/avtoxabar.pem     <- Origin Certificate
/etc/ssl/cloudflare/avtoxabar.key     <- Private Key   (chmod 600)
```

**3. SSL rejimi.** Cloudflare → SSL/TLS → Overview → **Full (strict)**.

> «Flexible» qo‘ymang: Cloudflare serverga HTTP bilan murojaat qiladi,
> nginx esa HTTPS ga yo‘naltiradi — cheksiz redirect halqasi hosil
> bo‘ladi va sayt umuman ochilmay qoladi.

**4. Host nginx — sayt.** Repozitoriy ildizidan:

```bash
sudo cp nginx/snippets/cloudflare-real-ip.conf /etc/nginx/snippets/
```

```bash
sudo cp nginx/host/avtoxabar.vipads.uz.conf.example /etc/nginx/sites-available/avtoxabar.vipads.uz
```

```bash
sudo ln -s ../sites-available/avtoxabar.vipads.uz /etc/nginx/sites-enabled/
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

**5. Host nginx — Click webhook.**
`nginx/host/dns.vipads.uz-click.conf.example` dagi `location` blokini
serverdagi mavjud `dns.vipads.uz` server bloki **ichiga** qo‘ying.
Avval fayl boshidagi ogohlantirishni o‘qing: bu yo‘l uchun serverda eski
qoida bor (POST → 403), u yangi blok bilan to‘qnashadi:

```bash
grep -rn "payments/click" /etc/nginx/
```

**6. Click kabineti.** Prepare URL va Complete URL maydonlarining
ikkalasiga ham:

```
https://dns.vipads.uz/api/payments/click/webhook
```

**Haqiqiy mijoz IP si.** Cloudflare orqasida hamma so‘rov Cloudflare
serverlaridan keladi. `cloudflare-real-ip.conf` haqiqiy IP ni
`CF-Connecting-IP` sarlavhasidan oladi va bunga faqat Cloudflare
diapazonlaridan kelgan so‘rovlarda ishonadi. Konteyner ichidagi nginx
esa uni host nginx yuborgan `X-Forwarded-For` dan oladi
(`upstream-real-ip.conf`), ilova esa `TRUSTED_PROXIES=1` bilan
(compose‘da o‘rnatilgan). Cloudflare diapazonlari o‘zgarsa yangilang:

```bash
curl https://www.cloudflare.com/ips-v4 && curl https://www.cloudflare.com/ips-v6
```

**Ixtiyoriy himoya.** Server IP sini topib olgan odam Cloudflare‘ni
chetlab o‘tmasligi uchun `nginx/snippets/cloudflare-only.conf` ni host
nginx‘ning HTTPS blokiga include qiling — faqat DNS yozuvi «Proxied»
ekaniga ishonch hosil qilgandan keyin, aks holda sayt o‘zingizga ham
yopiladi.

### 7.5. Tekshirish

```bash
curl -sI https://avtoxabar.vipads.uz | head -n 1
```

`HTTP/2 200` kutiladi. Click yo‘li ochiqligini tekshirish:

```bash
curl -s -X POST https://dns.vipads.uz/api/payments/click/webhook -d "action=0"
```

JSON kelishi kerak (imzo yo‘q, shuning uchun `"error": -8` normal).
403 / 404 / 502 kelsa — host nginx sozlamasida xato bor.

Admin panel: `https://avtoxabar.vipads.uz/kirish` → `ADMIN_PHONE` va
`ADMIN_PASSWORD` bilan kiring.

### 7.6. Yangilash

```bash
cd /opt/autoxabar && git pull && ./scripts/deploy.sh
```

Skript yangilashdan oldin avtomatik zaxira oladi. Baza va sessiyalar
volume‘da bo‘lgani uchun yangilashda yo‘qolmaydi.

### 7.7. Zaxira va tiklash

```bash
./scripts/backup.sh
```

Natija: `backups/autoxabar-YYYY-MM-DD-HHMMSS.tar.gz` — SQLite bazasi
(ishlab turgan paytda ham butun holatda olinadi), Telegram sessiyalari
va yuklangan rasmlar. Oxirgi 14 tasi saqlanadi (`BACKUP_KEEP` bilan
o‘zgartiriladi). Har kuni avtomatik olish uchun `crontab -e` ga:

```
0 4 * * * cd /opt/autoxabar && ./scripts/backup.sh >> backups/backup.log 2>&1
```

> Arxivda Telegram sessiyalari bor — ular akkauntlarga to‘liq kirish
> beradi. Arxivlar faqat egasiga o‘qiladi; serverdan tashqariga
> shifrlanmagan holda ko‘chirmang.

Tiklash (tasdiq so‘raydi, oldin hozirgi holatdan zaxira oladi):

```bash
./scripts/restore.sh backups/autoxabar-2026-10-08-040000.tar.gz
```

### 7.8. Muhim cheklovlar

**Konteynerni ko‘paytirmang.** `--scale` yoki `replicas` ishlatilsa, fon
vazifalari har bir nusxada qaytadan ishlaydi va bitta profil bir necha
marta xabar yuboradi — Telegram akkaunti bloklanishi mumkin. Yuklama
oshsa `Dockerfile` dagi `--threads` ni oshiring.

**Proksi orqasida ishlash.** `TRUSTED_PROXIES=1` compose‘da o‘rnatilgan —
shunda ilova haqiqiy mijoz IP sini va `https` sxemasini ko‘radi. Ilovani
proksisiz, to‘g‘ridan-to‘g‘ri ochsangiz `TRUSTED_PROXIES=0` qiling, aks
holda har kim o‘z IP sini soxtalashtira oladi.

### Docker‘siz (Windows)

```bash
pip install waitress
```

```bash
waitress-serve --host=0.0.0.0 --port=5000 app:app
```

Fon vazifalari `create_app()` ichida yoqiladi, shuning uchun waitress
ostida ham ishlaydi. `.env` da `SECRET_KEY`, `ADMIN_PASSWORD`,
`BASE_URL` (https) va `FLASK_DEBUG=0` ni o‘zingiz to‘ldiring.

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
