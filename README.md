# VIPADSUZ · AutoXabar

**@auto_habar** kanalidagi AutoXabarBot xizmatining to‘liq veb-versiyasi.

Telegram akkauntingizni ulaysiz — tizim sizning e'loningizni siz a'zo bo‘lgan
barcha guruhlarga belgilangan interval bilan avtomatik yuboradi.

- **Narx:** 1 profil = 1 oy = **5 000 so‘m** (sozlamalardan o‘zgartiriladi)
- **To‘lov:** Payme (bir martalik + saqlangan kartadan **avtomatik oylik yechim**)
- **Moliya:** har bir tushum yalpi → komissiya → **soliq 10%** → **sof foyda** ga ajratiladi,
  oylik hisobot va bankdan yechib olish hisobi yuritiladi

---

## 1. Ishga tushirish

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

### Payme — to‘lovni qabul qilish (Merchant API)

```
PAYME_MERCHANT_ID=<kassa ID>
PAYME_KEY=<kassa kaliti>
```

Payme kabinetida kassa yaratganda:

1. **Endpoint URL:** `https://sizning-domeningiz.uz/api/payme`
2. **Buyurtma maydoni (account):** nomi aynan `payment_id` bo‘lishi shart —
   tizim buyurtmani shu maydon orqali topadi.

### Payme — avtomatik oylik to‘lov (Subscribe API)

```
PAYME_SUBSCRIBE_ID=<Subscribe kassa ID>
PAYME_SUBSCRIBE_KEY=<Subscribe kassa kaliti>
```

Bu yoqilganda foydalanuvchi kabinetda kartasini bir marta bog‘laydi
(karta raqami serverda saqlanmaydi — faqat Payme bergan token), so‘ng obuna
muddati tugaganda summa avtomatik yechiladi.

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
  payme.py              Merchant API (JSON-RPC) + Subscribe API (avto-to'lov)
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
  payme_bp.py           /api/payme kirish nuqtasi
templates/  static/     Jinja2 shablonlari va dizayn tizimi
data/autoxabar.db       SQLite bazasi
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
4. HTTPS orqasiga qo‘ying (Payme faqat HTTPS endpoint bilan ishlaydi)
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
| `PAYME_*` | hozircha bo'sh qoldiring |
| `BASE_URL` | deploydan keyin haqiqiy havola bilan to'ldiring |

4. **Apply** → 3–5 daqiqada `https://autoxabar.onrender.com` tayyor bo'ladi

Keyin **Environment** bo'limida `BASE_URL` ni haqiqiy havola bilan almashtiring
(Payme qaytish manzili shu asosda quriladi).

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

> Payme integratsiyasi uchun HTTPS manzil shart — Render buni avtomatik beradi.
> Payme kassasidagi Endpoint URL: `https://sizning-manzilingiz.onrender.com/api/payme`
