# AutoXabar — to'liq qo'llanma

> VIPADSUZ · Telegram guruhlariga avtomatik xabar tarqatish xizmati
> Oxirgi yangilanish: 2026-yil 1-sentabr

---

## Mundarija

1. [Bu nima va qanday ishlaydi](#1-bu-nima-va-qanday-ishlaydi)
2. [Sizdagi havolalar va ularning farqi](#2-sizdagi-havolalar-va-ularning-farqi)
3. [DOIMIY HAVOLA — Render'ga joylashtirish](#3-doimiy-havola--renderga-joylashtirish)
4. [Saytdan foydalanish](#4-saytdan-foydalanish)
5. [Pul: narx, obuna, to'lovlar](#5-pul-narx-obuna-tolovlar)
6. [Admin panel va moliya hisoboti](#6-admin-panel-va-moliya-hisoboti)
7. [Click'ni ulash](#7-clickni-ulash)
8. [Kompyuterda ishga tushirish](#8-kompyuterda-ishga-tushirish)
9. [Muammolar va yechimlar](#9-muammolar-va-yechimlar)
10. [Muhim ma'lumotlar](#10-muhim-malumotlar)

---

## 1. Bu nima va qanday ishlaydi

AutoXabar — foydalanuvchi o'z Telegram akkauntini saytga ulaydi, e'lonini yozadi,
va tizim uni **o'sha akkaunt a'zo bo'lgan barcha guruhlarga** belgilangan interval
bilan avtomatik yuboradi.

**Ishlash tartibi:**

```
Foydalanuvchi ro'yxatdan o'tadi
        ↓
Telegram akkauntini ulaydi (QR yoki telefon raqami orqali)
        ↓
Akkaunt a'zo bo'lgan guruhlar avtomatik ro'yxatga tushadi
        ↓
Foydalanuvchi e'lon matnini yozadi
        ↓
Interval tanlaydi (2 dan 30 daqiqagacha)
        ↓
«Ishga tushirish» → tizim 24/7 xabar tarqatadi
```

**Ban bo'lmasligi uchun himoya:**

| Himoya | Nima qiladi |
|---|---|
| Tasodifiy pauza | Har guruh orasida 3–8 soniya kutadi |
| Aqlli dam olish | 1 soat ishlagach 3–5 daqiqa tanaffus |
| FloodWait | Telegram cheklov qo'ysa, avtomatik kutadi |
| Avto-o'chirish | Guruhda yozish taqiqlansa, o'sha guruh ro'yxatdan chiqadi |

---

## 2. Sizdagi havolalar va ularning farqi

Buni tushunish muhim — uchta havola bor va ular **turli ishni** qiladi.

### A) GitHub — kodni saqlaydi

**https://github.com/avazbek-011/autoxabar**

Bu kutubxona. Loyihaning barcha fayllari shu yerda turadi. **Sayt bu yerda ishlamaydi.**

### B) GitHub Pages — faqat tanishtiruv

**https://avazbek-011.github.io/autoxabar/**

Bosh sahifa, narxlar, qo'llanma, oferta — chiroyli ko'rinadi va istalgan odam ochadi.

⚠️ **Bu yerda ro'yxatdan o'tib bo'lmaydi.** GitHub Pages faqat tayyor HTML fayllarni
ko'rsatadi — Python dasturini ishlatmaydi, ma'lumotlar bazasi yo'q. Bu GitHub'ning
texnik chegarasi, sozlama bilan o'zgarmaydi.

Mashinaning surati bilan mashinaning o'zi kabi farq: suratni ko'rasiz, lekin
unda yura olmaysiz.

### C) Render — hamma narsa ishlaydigan sayt

**https://autoxabar-7tbz.onrender.com** ✅ *ishlayapti*

Bu yerda ro'yxatdan o'tish, akkaunt ulash, to'lov — hammasi ishlaydi.
Kompyuteringiz o'chsa ham ishlaydi. Manzil hech qachon o'zgarmaydi.

**Buni ishga tushirish — 3-bo'limda.**

---

## 3. DOIMIY HAVOLA — Render'ga joylashtirish

Bu eng muhim bo'lim. Bir marta qilasiz, keyin doim ishlaydi.

Barcha sozlama fayllari (`render.yaml`) allaqachon GitHub'da tayyor turibdi.

### 1-qadam — Render'ga kirish

1. Brauzerda oching: **https://render.com**
2. **`Get Started`** yoki **`Sign In`** tugmasini bosing
3. **`GitHub`** tugmasini tanlang
4. **`Authorize Render`** bosing

> Email, parol, bank kartasi — **hech narsa so'ralmaydi**. GitHub hisobingiz
> bilan kiradi, xolos.

### 2-qadam — Loyihani ulash

1. Yuqori o'ngdagi **`New +`** tugmasi
2. Ro'yxatdan **`Blueprint`** ni tanlang
3. Repozitoriylar ro'yxatida **`autoxabar`** ni toping → **`Connect`**

> **Ko'rinmasa:** `Configure account` → `Only select repositories` →
> `autoxabar` ni belgilang → `Save`.

### 3-qadam — 4 ta maydonni to'ldirish

Render `render.yaml` ni o'qiydi va faqat shu 4 tasini so'raydi:

| Maydon | Qiymat |
|---|---|
| `ADMIN_PHONE` | `+998900000000` |
| `ADMIN_PASSWORD` | `Telegram-8815-LJ8ZdeHs` |
| `TELEGRAM_API_ID` | `34206677` |
| `TELEGRAM_API_HASH` | `e46c550f98e46809a6eae1d003918c91` |

Qolgan hamma narsa (narx, soliq, manzil) oldindan to'ldirilgan.

### 4-qadam — Apply

**`Apply`** tugmasini bosing va 3–5 daqiqa kuting.

Yakunda yuqorida havola paydo bo'ladi:

```
https://autoxabar.onrender.com
```

*(nom band bo'lsa Render oxiriga raqam qo'shadi, masalan `autoxabar-a1b2`)*

### Bepul tarifning ikkita cheklovi

Buni oldindan bilib qo'ying — keyin ajablanmaslik uchun:

**1. Uyqu rejimi.** 15 daqiqa hech kim kirmasa xizmat uxlaydi. Keyingi ochilish
~30 soniya kutdiradi. Muhimi: **uxlagan paytda xabar tarqatish ham to'xtaydi**.

**2. Ma'lumotlar saqlanmaydi.** Har yangilanishda baza nolga qaytadi —
foydalanuvchilar, profillar, to'lovlar o'chadi.

### Haqiqiy ish uchun — Starter tarif

Mijozlar kelganda bepul tarif yetmaydi. Starter tarifga o'tish (~$7/oy):

1. Render'da xizmatni oching → **`Settings`** → **`Instance Type`** → **`Starter`**
2. **`Disks`** bo'limi → **`Add Disk`** → Mount Path: `/var/data`, hajmi 1 GB
3. **`Environment`** bo'limiga qo'shing:

```
DATA_DIR=/var/data
```

Shundan keyin: uyqu yo'q, baza doim saqlanadi, xabar tarqatish 24/7 uzluksiz.

---

## 4. Saytdan foydalanish

### Ro'yxatdan o'tish

1. Saytga kiring → **`Boshlash`** yoki **`Ro'yxatdan o'tish`**
2. Ism, telefon raqami (`+998...`), parol (kamida 6 belgi)
3. Oferta belgisini qo'ying → **`Ro'yxatdan o'tish`**

Darhol kabinetga tushasiz.

### Telegram akkauntini ulash

**Profillar** bo'limida ikkita usul bor.

#### Usul 1 — QR kod (tavsiya etiladi)

Eng tez va xavfsiz. Kod kutish shart emas.

1. **`QR kod`** yorlig'i → **`QR kodni ko'rsatish`**
2. Telefoningizda **Telegram** ilovasini oching
3. **Sozlamalar** → **Qurilmalar** → **Kompyuterni ulash**
4. Kamerani ekrandagi QR kodga qarating
5. Tasdiqlang — sayt o'zi profil sahifasiga o'tadi

> QR har 25 soniyada yangilanadi — bu normal holat.
> Ikki bosqichli parolingiz (2FA) bo'lsa, uni ham so'raydi.

#### Usul 2 — Telefon raqami

1. **`Telefon raqami`** yorlig'i → raqamni kiriting → **`Kod yuborish`**
2. Telegram ilovangizdagi **«Telegram»** nomli rasmiy chatga 5 xonali kod keladi
   *(SMS emas!)*
3. Kodni kataklarga yozing → **`Tasdiqlash`**

> **Diqqat:** kodni ko'p marta qayta so'ratmang. Telegram raqamni vaqtincha
> bloklashi mumkin (24 soatgacha). Bunday bo'lsa QR usulidan foydalaning —
> unga cheklov ta'sir qilmaydi.

Ulanish tugagach **guruhlar avtomatik ro'yxatga tushadi**.

### Xabar yaratish

**Xabarlar** bo'limi → matnni yozing → **`Xabarni saqlash`**

Formatlash ishlaydi:

```html
<b>Qalin matn</b>
<i>Kursiv</i>
<u>Tagi chizilgan</u>
<code>Kod</code>
<a href="https://sayt.uz">Havola</a>
```

PRO rejada rasm ham qo'shiladi.

### Guruhlarni tanlash

Profil sahifasi → **`Guruhlar`** yorlig'i.

⚠️ **Birinchi sinovda ehtiyot bo'ling:** avval **`Hammasini o'chirish`** bosing,
keyin faqat 1–2 ta guruhni yoqing va shunda sinab ko'ring. Ishonch hosil
qilgach qolganlarini yoqasiz.

### Ishga tushirish

Profil sahifasi → **`Sozlamalar`** yorlig'i:

| Sozlama | Tavsiya |
|---|---|
| Faol xabar | yaratgan xabaringizni tanlang |
| Interval | **yangi akkaunt uchun 15 daqiqa** |
| Aqlli dam olish | **yoqiq qoldiring** |

**`Saqlash`** → yuqoridagi **`Ishga tushirish`** tugmasi.

30 soniyadan keyin **`Jurnal`** yorlig'ida birinchi yuborilgan xabarni ko'rasiz.

---

## 5. Pul: narx, obuna, to'lovlar

### Narx

**1 ta Telegram akkaunti = 30 kun = 5 000 so'm**

### Har akkaunt alohida to'lanadi

Bu muhim: obuna **akkauntga** biriktiriladi, foydalanuvchiga emas.

```
1-akkauntga PRO sotib oldingiz  →  faqat 1-akkaunt PRO bo'ladi
2-akkaunt bepul holicha qoladi  →  unga alohida to'lash kerak
```

**Misol:** 10 ta akkauntingiz bor va hammasi PRO bo'lsin desangiz —
10 × 5 000 = **50 000 so'm/oy**.

Har bir akkauntning muddati ham alohida hisoblanadi.

### Akkauntlar soni

Hozir **cheksiz** qilib qo'yilgan. Aniq son qo'ymoqchi bo'lsangiz:

**Admin → Sozlamalar → Maks. akkaunt / foydalanuvchi**

- `0` — cheksiz
- `30` — 30 ta akkaunt

### Bepul va PRO farqi

| | Bepul | PRO |
|---|---|---|
| Avtomatik tarqatish | ✅ | ✅ |
| Barcha intervallar | ✅ | ✅ |
| Statistika | ✅ | ✅ |
| Aqlli dam olish | ✅ | ✅ |
| Xabar ostida reklama | ❌ qo'shiladi | ✅ yo'q |
| Rasm yuborish | ❌ | ✅ |

---

## 6. Admin panel va moliya hisoboti

Admin sifatida kiring → chap menyuda **Admin → Boshqaruv paneli**, yoki `/admin`.

### Moliya bo'limi — eng muhimi

**Admin → Moliya**

Har bir to'lov shunday ajratiladi:

```
yalpi tushum                        5 000 so'm
 − Ekvayring komissiyasi (1%)         −50 so'm
 ─────────────────────────────────────────────
 = hisobga tushgan summa            4 950 so'm
 − soliq (10%)                      −495 so'm
 ─────────────────────────────────────────────
 = SOF FOYDA                        4 455 so'm
```

Oylik darajada bundan **xarajatlar** ham ayriladi.

### Bo'limda nima bor

| Qism | Nima ko'rsatadi |
|---|---|
| Yuqoridagi 4 karta | Yalpi tushum, komissiya, soliq, sof foyda |
| Taqsimot chizig'i | Pul qayerga ketganini rangli ko'rsatadi |
| **Bankdan yechib olish** | Hozir yechish mumkin bo'lgan summa + qayd etish formasi |
| Xarajat qo'shish | Server, reklama, ish haqi va boshqalar |
| Prognoz | Faol obunalar bo'yicha keyingi oy tushumi |
| Grafiklar | 12 oylik sof foyda va 30 kunlik tushum |
| Oylar jadvali | Har oy: tushum, soliq, xarajat, yechilgan, qoldiq |
| Tushumlar daftari | Har bir to'lov alohida |

### Har oy nima qilasiz

1. **Moliya** bo'limini oching
2. «Bankdan yechish mumkin» summasini ko'ring
3. Bankdan o'sha summani yechib oling
4. **`Yechib olishni qayd etish`** formasiga summani yozing → saqlang

Shundan keyin tizim «qancha tushdi / qancha yechildi / qancha qoldi» ni
aniq yuritadi. Soliq alohida hisoblanadi — uni ham shu formada
`Turi: Soliq to'lovi` qilib qayd etasiz.

### Foizlarni o'zgartirish

**Admin → Sozlamalar**: soliq foizi, ekvayring foizi, narx, sinov kunlari —
hammasi kodga tegmasdan o'zgartiriladi.

> Eslatma: o'zgarish faqat **yangi** to'lovlarga ta'sir qiladi. Eski yozuvlar
> o'sha paytdagi foizlar bilan saqlanadi.

### Boshqa bo'limlar

- **To'lovlar** — barcha to'lovlar, qo'lda tasdiqlash imkoni
- **Foydalanuvchilar** — bloklash, balans qo'shish, bepul obuna berish
- **Profillar** — barcha akkauntlar monitoringi
- **Tizim holati** — fon vazifalari, xatolar, baza statistikasi

---

## 7. Click'ni ulash

Kod to'liq yozilgan va sinovdan o'tgan. Sizdan faqat kalitlar kerak.

> **Avval o'qing.** Bepul Render tarifida Click'ni ulamang: xizmat 15 daqiqa
> harakatsizlikdan keyin uxlaydi, Click'ning so'rovlari timeout bo'ladi va
> to'lov Click tomonda qo'lda tekshiruvga tushadi. Bundan tashqari bepul
> tarifda baza saqlanmaydi — to'lovlar tarixi har deployda yo'qoladi.
> Ketma-ketlik: **Starter tarif → doimiy disk → keyin Click**.

### Click kabinetida

1. Click merchant kabinetiga kiring (<https://merchant.click.uz>)
2. **Servis yarating** (SHOP API sxemasi bo'yicha)
3. Servis sozlamalarida ikkita manzilni ko'rsating:

```
Prepare URL   https://autoxabar-7tbz.onrender.com/api/click/prepare
Complete URL  https://autoxabar-7tbz.onrender.com/api/click/complete
```

> Bu ikkita manzilni admin panelning **Tizim holati** bo'limidan ham
> nusxalab olsangiz bo'ladi — u yerda joriy domen bilan ko'rsatiladi.

4. Payme'dagidek alohida "buyurtma maydoni" yaratish **shart emas**:
   Click buyurtma raqamini `merchant_trans_id` maydonida o'zi qaytaradi.

5. Ulanish tugagach Click sizga 4 ta qiymat beradi:
   `merchant_id`, `service_id`, `merchant_user_id`, `secret_key`

### Render'da kalitlarni kiritish

Render → xizmatingiz → **`Environment`** → quyidagilarni to'ldiring:

```
CLICK_MERCHANT_ID       = merchant_id
CLICK_SERVICE_ID        = service_id
CLICK_MERCHANT_USER_ID  = merchant_user_id
CLICK_SECRET_KEY        = secret_key
```

**`Save Changes`** → xizmat o'zi qayta ishga tushadi.

> `CLICK_SECRET_KEY` — eng maxfiy qiymat. U bilan har qanday odam soxta
> "to'landi" so'rovi yubora oladi. Uni hech kimga bermang va repozitoriyga
> yozmang.

### To'lov qanday kechadi

1. Foydalanuvchi kabinetda **«Click orqali 5 000 so'm»** tugmasini bosadi
2. Tizim `pending` holatidagi to'lov yozuvini yaratadi va Click sahifasiga
   yo'naltiradi
3. Foydalanuvchi UzCard yoki Humo kartasi bilan to'laydi
4. Click bizga **Prepare** (tekshirish), so'ng **Complete** (yakunlash)
   so'rovini yuboradi
5. Complete muvaffaqiyatli bo'lgach: to'lov `paid` bo'ladi, obuna 30 kunga
   uzayadi, profil PRO rejimga o'tadi va moliya daftariga yoziladi
6. Foydalanuvchi **«To'lov qabul qilindi»** sahifasiga qaytadi

### Obuna yangilanishi

Click SHOP API kartani saqlashga ruxsat bermaydi, shuning uchun obuna
**qo'lda** yangilanadi:

1. Muddat tugashiga 3 kun qolganda foydalanuvchiga eslatma boradi
2. U kabinetdan Click orqali to'laydi
3. To'lanmasa muddat tugagach profil to'xtaydi (ma'lumotlar saqlanadi)

### Sinov

Kalitlarni kiritgach, admin panel → **Tizim holati** bo'limida
**Click: Sozlangan** yozuvi paydo bo'lishi kerak. Keyin kichik summa bilan
haqiqiy to'lov qilib ko'ring va **To'lovlar** bo'limida `paid` holatga
o'tganini tekshiring.

---

## 8. Kompyuterda ishga tushirish

Render ishga tushmaguncha yoki sinov uchun kerak bo'ladi.

### Mahalliy sayt

Loyiha papkasida `run.bat` faylini ikki marta bosing, yoki:

```
python app.py
```

Manzil: **http://127.0.0.1:5000** — faqat shu kompyuterda ochiladi.

### Docker bilan

Docker Desktop o'rnatilgan bo'lsa, Python va kutubxonalarni alohida
o'rnatish shart emas. Loyiha papkasida bitta buyruq:

```
docker compose up -d --build
```

Manzil o'sha: **http://127.0.0.1:5000**

| Buyruq | Nima qiladi |
|---|---|
| `docker compose logs -f` | loglarni jonli ko'rsatadi (Ctrl+C bilan chiqiladi) |
| `docker compose restart` | qayta ishga tushiradi |
| `docker compose down` | to'xtatadi, **ma'lumotlar saqlanadi** |
| `docker compose up -d --build` | kod o'zgargandan keyin yangilaydi |

Baza, Telegram sessiyalari va yuklangan rasmlar Docker volume'larida
saqlanadi — konteynerni o'chirsangiz ham yo'qolmaydi.

⚠️ `docker compose down -v` buyrug'idagi **`-v`** volume'larni ham
o'chiradi: foydalanuvchilar, to'lovlar va Telegram sessiyalari butunlay
yo'qoladi. Faqat noldan boshlamoqchi bo'lsangiz ishlating.

### Vaqtinchalik ommaviy havola

Ish stolidagi **`SAYTNI-ISHGA-TUSHIRISH.bat`** faylini ikki marta bosing.

U ikkita oyna ochadi:
- **AutoXabar SERVER** — saytning o'zi
- **AutoXabar TUNNEL** — ommaviy havola

TUNNEL oynasida ramka ichida havola yoziladi:

```
|  https://xxxx-xxxx-xxxx.trycloudflare.com  |
```

⚠️ **Ikkala oynani ham yopmang.** Yopsangiz yoki kompyuterni o'chirsangiz —
havola o'ladi. Har qayta ishga tushirishda **havola o'zgaradi**.

Shuning uchun bu havolani reklamaga qo'ymang — faqat sinash va ko'rsatish uchun.

---

## 9. Muammolar va yechimlar

### «Kod kelmayapti»

**Sabab:** Telegram raqamga vaqtincha cheklov qo'ygan (ko'p marta so'ralgani uchun).

**Yechim:** **QR kod** usulidan foydalaning — unga cheklov ta'sir qilmaydi.
Yoki 24 soat kutib, qayta urining.

### «Havola ishlamay qoldi»

Agar `trycloudflare.com` havolasi bo'lsa — bu normal, u vaqtinchalik.
Ish stolidagi `SAYTNI-ISHGA-TUSHIRISH.bat` ni qayta bosing, yangi havola chiqadi.

**Doimiy yechim:** Render (3-bo'lim).

### «github.io da ro'yxatdan o'tib bo'lmayapti»

Bu kutilgan holat — GitHub Pages dastur ishlatmaydi. Ro'yxatdan o'tish uchun
Render havolasi yoki mahalliy sayt kerak.

### «Profil to'xtab qoldi»

Profil sahifasidagi izohni o'qing:

| Izoh | Ma'nosi |
|---|---|
| Faol xabar tanlanmagan | Sozlamalarda xabarni tanlang |
| Yoqilgan guruh yo'q | Guruhlar yorlig'ida kamida bittasini yoqing |
| Obuna muddati tugagan | To'lovlar bo'limidan yangilang |
| Sessiya bekor qilingan | Profilni o'chirib, qaytadan ulang |
| Telegram akkaunt bloklangan | Akkaunt Telegram tomonidan bloklangan |

### «Guruhda xabar ketmayapti»

Guruhlar yorlig'ida o'sha guruhning holatini ko'ring:

- `muted` — guruhda yozish taqiqlangan
- `banned` — akkaunt guruhdan chiqarilgan
- `slow` — guruhda sekin rejim yoqilgan

Tizim bunday guruhlarni avtomatik o'chiradi. **`Tozalash`** tugmasi bilan
ro'yxatdan olib tashlaysiz.

### Akkaunt bloklanmasligi uchun

- Yangi akkauntlar uchun **15–30 daqiqalik interval**
- Guruhlar sonini asta-sekin oshiring
- «Aqlli dam olish» doim yoqiq bo'lsin
- 2 daqiqalik interval + ko'p guruh = **yuqori xavf**

---

## 10. Muhim ma'lumotlar

### Kirish ma'lumotlari

| | |
|---|---|
| Admin telefon | `+998900000000` |
| Admin parol | `Telegram-8815-LJ8ZdeHs` |

> Bu parolni o'zgartirmoqchi bo'lsangiz: `.env` faylida `ADMIN_PASSWORD` ni
> almashtiring va bazani yangilang, yoki saytdan **Sozlamalar → Parolni
> o'zgartirish** orqali.

### Telegram API kalitlari

| | |
|---|---|
| `TELEGRAM_API_ID` | `34206677` |
| `TELEGRAM_API_HASH` | `e46c550f98e46809a6eae1d003918c91` |

Manba: https://my.telegram.org → API development tools

### Havolalar

| | |
|---|---|
| Kod (GitHub) | https://github.com/avazbek-011/autoxabar |
| Tanishtiruv sahifasi | https://avazbek-011.github.io/autoxabar/ |
| Doimiy sayt | https://autoxabar-7tbz.onrender.com |

### Maxfiy fayllar — hech qachon tarqatmang

Bu fayllar `.gitignore` da, ya'ni GitHub'ga hech qachon tushmaydi:

| Fayl | Nima bor |
|---|---|
| `.env` | Telegram kalitlari, parollar, Click kalitlari |
| `data/autoxabar.db` | Foydalanuvchilar, to'lovlar, parol hashlari |
| `sessions/` | Telegram sessiyalari |

⚠️ **GitHub'ga hech qachon qo'lda fayl sudramang** («drag files» usuli).
U `.gitignore` ni bilmaydi va maxfiy fayllarni ham yuklab yuboradi.
Kod o'zgarsa — `git push` ishlatiladi.

### Sozlamalar qayerdan o'zgartiriladi

Deyarli hamma narsa **Admin → Sozlamalar** dan, kodga tegmasdan:

- Bitta profil narxi
- Soliq foizi va ekvayring komissiyasi
- Sinov kunlari
- Maks. akkaunt soni (0 = cheksiz)
- Telegram rejimi (haqiqiy / demo)
- Aloqa ma'lumotlari (username, kanal, bot)
- Bank nomi va hisob raqami
- Ro'yxatdan o'tishni ochish/yopish

### Fon vazifalari

Sayt ishga tushganda avtomatik yoqiladi:

| Vazifa | Davriylik |
|---|---|
| Yuborish sikllarini tekshirish | 30 soniya |
| Hisoblagichlarni yangilash | 5 daqiqa |
| Avto-to'lovlarni bajarish | 30 daqiqa |
| Muddati tugaganlarni yopish | 60 daqiqa |
| Eski jurnallarni tozalash | har kuni 03:30 |

Har birini **Admin → Tizim holati** dan qo'lda ham ishga tushirish mumkin.

---

## Qisqacha: keyingi qadamlar

1. ☐ **Render'ga joylashtiring** (3-bo'lim) — doimiy havola olasiz
2. ☐ QR orqali Telegram akkauntingizni ulang
3. ☐ Xabar yozing, 1–2 guruhda sinab ko'ring
4. ☐ Ishonch hosil qilgach barcha guruhlarni yoqing
5. ☐ Click kalitlarini oling va ulang (7-bo'lim)
6. ☐ Mijozlar kelganda Starter tarifga o'ting
