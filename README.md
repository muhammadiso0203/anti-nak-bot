# 🛡 Nakrutka Blocker Bot

Telegram **kanal va guruhlar** uchun nakrutka (soxta/bot obunachilar) himoyasi.

**Faqat `start.bat` ni ishga tushirasiz** — qolgan hammasi botning ichida:

| Nima | Qanday |
|---|---|
| **Yangi kelayotganlar** | Avtomatik — bot kirish paytida (yoki kirish so'rovi bosqichida) aniqlab bloklaydi |
| **Kanal ichidagi eskilar** | Botga **`/scan`** yuborasiz — ro'yxat chiqadi, siz tasdiqlaysiz |
| Sozlamalar | **`/panel`** — rejim, chegara, qattiqlik, tezkor presetlar |

Eski a'zolar uchun Telegram botga a'zolar ro'yxatini **bermaydi** — faqat odamga
beradi. Shuning uchun `/scan` sizning akkauntingiz orqali **o'qiydi**, bloklashni
esa bot o'zi bajaradi. Buning uchun bir marta **`login.bat`** ishga tushiriladi
(2.6-bo'lim). `scanner.py` — xuddi shu ishning konsol varianti, juda katta
kanallar va CSV uchun qoldirilgan.

---

## 1. Nakrutkani qanday aniqlaydi?

Bitta belgi bo'yicha hukm chiqarilmaydi — **ball tizimi** ishlatiladi.
Har bir shubhali belgi ball qo'shadi, har bir "tirik odam" belgisi ball ayiradi.
Yig'indi chegaradan (default **50**) oshsa — nakrutka deb hisoblanadi.

**Shubhali belgilar (+)**

| Belgi | Ball |
|---|---|
| Telegram «scam/fake» deb belgilagan | +60 |
| Bot akkaunt | +50 |
| O'chirilgan / ismsiz akkaunt | +45 |
| Akkaunt juda yangi (ID juda yuqori) | +30 |
| Bir vaqtda to'da bo'lib kirish (nakrutka to'lqini) | +25 |
| Ismda reklama/havola/spam so'z | +25 |
| Cheklangan akkaunt | +25 |
| Bitta havoladan to'da bo'lib kirish | +20 |
| Akkaunt yangi | +20 |
| Ism tasodifiy harflar to'plami (`Qwrtbnm`) | +18 |
| Profil rasmi yo'q | +18 |
| Username tasodifiy (`k8xj2qm41`) | +16 |
| Ismda lotin+kirill aralash (soxta ism) | +14 |
| 1 yildan ortiq onlayn bo'lmagan (skaner) | +15 |
| Ism oxirida ketma-ket raqamlar (`Ali12345`) | +12 |
| Username yo'q | +10 |
| Ism juda qisqa (1-2 belgi) | +10 |
| Ilova tili aniqlanmagan | +8 |

**Tirik odam belgilari (−)**

| Belgi | Ball |
|---|---|
| Telegram Premium | −25 |
| Eski akkaunt (ko'p yillik) | −20 |
| Bio (haqida) yozilgan | −10 |
| Rasm ham, username ham bor | −8 |

Ballarni `detector.py` faylidagi `W = {...}` lug'atida xohlagancha o'zgartirishingiz mumkin.

---

## 2. O'rnatish (Windows)

### 2.1. Python
Agar Python o'rnatilmagan bo'lsa: https://python.org/downloads
O'rnatishda **«Add Python to PATH»** katagiga belgi qo'yish shart.

### 2.2. Bot token olish
1. Telegramda [@BotFather](https://t.me/BotFather) ga `/newbot` yuboring
2. Nom va username bering
3. Berilgan tokenni (`123456:AAE...`) saqlab qo'ying

### 2.3. O'z ID'ingizni bilish
[@userinfobot](https://t.me/userinfobot) ga `/start` yuboring — raqam chiqadi.

### 2.4. O'rnatishni ishga tushirish
`install.bat` faylini ikki marta bosing. U:
- kerakli kutubxonalarni o'rnatadi,
- `.env` faylini yaratib bloknotda ochadi.

`.env` faylida kamida shularni to'ldiring:

```ini
BOT_TOKEN=123456:AAE...
ADMIN_IDS=123456789
LOG_CHAT_ID=
MODE=ban
SCORE_THRESHOLD=50
```

Saqlab yoping.

### 2.5. Botni ishga tushirish
`start.bat` ni bosing. Konsolda `Bot ishga tushdi: @sizning_bot` chiqishi kerak.
Botga Telegramda `/start` yuboring. **Bu oyna ochiq qolishi kerak** — yopsangiz
bot ishlamaydi.

### 2.6. `/scan` uchun bir martalik login (ixtiyoriy, lekin tavsiya etiladi)

Kanal **ichidagi** eski nakrutkalarni tozalash uchun:

1. https://my.telegram.org → telefon raqamingiz → Telegramdan kelgan kod
2. **API development tools** → ilova yarating
3. `api_id` va `api_hash` ni `.env` ga yozing:
   ```ini
   API_ID=1234567
   API_HASH=abcdef1234567890abcdef1234567890
   ```
4. **`login.bat`** ni ishga tushirib telefon raqam va kodni kiriting

Shundan keyin botga `/scan` yuborsangiz ishlaydi. Login bir marta qilinadi —
sessiya `scanner.session` fayliga saqlanadi.

> Buni o'tkazib yuborsangiz ham bot ishlaydi, faqat `/scan` ishlamaydi
> (bot ishga tushganda sizga buni eslatadi).

---

## 3. Kanalga/guruhga ulash

### Kanal uchun (eng muhim qism!)

1. Kanal → **Administrators** → **Add Admin** → botni qo'shing
2. Unga quyidagi huquqlarni bering:
   - ✅ **Ban Users** (A'zolarni bloklash) — **majburiy**
   - ✅ Invite Users via Link (havolani yangilash funksiyasi uchun)
3. Kanal → **Subscribers / Invite Links** → **Approve New Members** (Yangi a'zolarni tasdiqlash) ni **yoqing**

> 🔑 3-qadam eng kuchli himoya: shunda nakrutka akkaunt kanalga **kirishidan oldin**
> so'rov bosqichida rad etiladi va obunachilar soni umuman o'zgarmaydi.
> Agar bu yoqilmasa, bot ularni kirgandan keyin darhol bloklaydi (bir necha soniya ichida).

### Guruh uchun
Botni guruhga qo'shing va **admin** qilib, «A'zolarni bloklash» huquqini bering.

### Log kanal (ixtiyoriy)
Alohida yopiq kanal yaratib, botni admin qiling, kanal ID'sini `.env` dagi
`LOG_CHAT_ID` ga yozing (masalan `-1001234567890`). Bot barcha bloklashlarni
sabablari bilan shu yerga yozadi. Bo'sh qoldirsangiz loglar sizga shaxsiy keladi.

---

## 4. Bot buyruqlari

| Buyruq | Vazifasi |
|---|---|
| `/start` | Yordam |
| `/panel` | Sozlamalar paneli (rejim, chegara, qattiqlik, presetlar) |
| `/scan` | **Kanal ichidagi eski** nakrutkalarni tekshirish va tozalash |
| `/skaner_akkaunt` | Tozalash uchun qaysi akkauntni admin qilish kerakligi |
| `/stats` | Statistika |
| `/log` | Oxirgi 10 hodisa |
| `/otkazilganlar` | O'tkazib yuborilganlar va ularning balli |
| `/qattiq 0-3` | Qattiq qoidalar darajasi |
| `/check 123456789` | Akkauntni tekshirish (yoki xabariga reply qilib) |
| `/oq 123456789` | Oq ro'yxatga qo'shish (hech qachon bloklanmaydi) |
| `/unban 123456789` | Blokdan chiqarish |
| `/id` | Chat yoki foydalanuvchi ID'sini ko'rsatish |

### Rejimlar
- **ban** — butunlay bloklaydi, qayta kira olmaydi ← *tavsiya*
- **kick** — chiqaradi, lekin qayta kirishi mumkin
- **mute** — guruhda ovozini o'chiradi
- **report** — **hech kimni o'chirmaydi**, faqat logga yozadi

> 💡 **Birinchi 1-2 kun `report` rejimida ishlatib ko'ring.** Log kanalida kim
> qancha ball olganini ko'rib, chegarani (`SCORE_THRESHOLD`) o'zingizga moslang,
> keyin `ban` ga o'tkazing. Shunda haqiqiy odamlar xato bloklanmaydi.

---

## 4.1. Nakrutka o'tib ketayotgan bo'lsa

Avval **sababini** aniqlang — uchta xil sabab bor, yechimlari ham boshqacha:

**1) Bot blokladi deb o'yladi, lekin huquqi yo'q edi.**
`/stats` da «Bajarilmagan chora» qatori chiqsa — aynan shu holat.
Kanal → Administrators → bot → **Ban Users** ni yoqing. (Bot endi bu holatni
yashirmaydi: logda «aniqlandi, lekin bloklanmadi» deb yozadi.)

**2) Ular bot admin bo'lishidan OLDIN kirgan.**
Bot faqat o'zi admin bo'lgandan keyingi kirishlarni ko'radi. Eski a'zolar uchun
`scanner.py` ishlatiladi (5-bo'lim), qattiqlik bilan:
`python scanner.py --chat @kanal --strict 2`

**3) Ball chegaradan past bo'ldi.** Eng ko'p uchraydigan sabab.
`/otkazilganlar` yuboring — o'tib ketganlarning ballini va tavsiya etilgan
chegarani ko'rsatadi. Keyin ikki yo'ldan birini tanlang:

### Yo'l A — tezkor sozlash (oson)
`/panel` → **⚡️ Tezkor sozlash**:

| Preset | Chegara | Qattiq qoida | Kimga |
|---|---|---|---|
| 🟢 Yumshoq | 65 | — | faqat aniq nakrutkalar |
| 🔵 Muvozanatli | 50 | — | default |
| 🟠 **Qattiq** | 42 | rasm **va** username yo'q = blok | **ko'pchilik uchun eng yaxshi** |
| 🔴 Temir | 34 | rasm yo'q = blok | nakrutka ko'p hujum qilsa |
| ⚫️ Maksimal | 25 | username yo'q **yoki** yangi akkaunt = blok | eng qattiq |

### Yo'l B — qattiq qoidalarni alohida yoqish
`/qattiq 1` yoki `/panel` → **🔒 Qattiq qoidalar**. Bu qoidalar **ball yetmasa
ham darhol bloklaydi**:

| Daraja | Shart |
|---|---|
| 0 | o'chiq, faqat ball tizimi |
| 1 | profil rasmi **ham**, username **ham** yo'q |
| 2 | profil rasmi yo'q |
| 3 | username yo'q **yoki** akkaunt yangi |

Telegram Premium akkauntlar bu qoidalardan ozod — nakrutka servislar pullik
Premium bermaydi, haqiqiy odamlarda esa u ko'p uchraydi.

> ⚠️ **"Hammasini o'chiradigan" sozlama bo'lmaydi.** Nakrutka akkaunt bilan
> yangi ro'yxatdan o'tgan, hali rasm qo'ymagan haqiqiy odam Telegram uchun
> **bir xil ko'rinadi** — botda ham, odamda ham ularni ajratishning 100% usuli yo'q.
> Qattiqlikni oshirgan sari o'tib ketadiganlar kamayadi, lekin xato bloklanadigan
> haqiqiy obunachilar ko'payadi. Shuning uchun:
> **Maksimal/Temir presetni avval `report` rejimida 1 kun sinab ko'ring** — kim
> bloklanishini oldin ko'rasiz. Xato bloklanganni log xabaridagi
> «♻️ Blokdan chiqarish» → «✅ Oq ro'yxat» tugmalari bilan qaytarasiz.
>
> Eng ishonchli yechim esa qattiqlik emas: kanalda **«Yangi a'zolarni
> tasdiqlash»** ni yoqish (3-bo'lim) — nakrutka kanalga kirmaydi ham.

---

## 5. Kanal ichidagi eski nakrutkalarni tozalash

Oldin API kalit va bir martalik login kerak — 2.6-bo'limga qarang.

### 5.1. Botning o'zidan (oson yo'l)

Botga yoki kanalga **`/scan`** yuboring. Bot:

1. kanal a'zolarini birma-bir tekshiradi (jarayonni xabarda ko'rsatib turadi),
2. topilganlar ro'yxatini + to'liq **CSV hisobotni** yuboradi,
3. **hech kimni o'chirmaydi** — «🗑 N ta akkauntni bloklash» tugmasini kutadi.

CSV ni ko'rib chiqing, so'ng tugmani bosasiz — bot o'zi bloklaydi. Xato
bloklangan bo'lsa kanal → Removed users dan qaytarasiz.

`/panel` → «🧹 Eski a'zolarni tekshirish» tugmasi ham shu ishni qiladi.

**Avtomatik tozalash** — `.env` da:
```ini
AUTO_SCAN_HOURS=24    # kunda bir marta o'zi tekshiradi (0 = o'chiq)
AUTO_SCAN_APPLY=0     # 0 = avval sizdan tasdiq so'raydi, 1 = o'zi bloklaydi
```

### 5.1.1. Botdan boshqa odam foydalansa?

| Vazifa | Akkaunt kerakmi? |
|---|---|
| **Yangi** nakrutkalardan himoya | ❌ Yo'q — botni admin qilish kifoya. Kim bo'lsa ham, qancha kanal bo'lsa ham ishlaydi |
| **/scan** (kanal ichidagi eskilar) | ✅ Ha — va faqat **bot egasining** akkaunti |

Bot egasining akkaunti bir marta ulanadi va o'sha turadi — boshqalar o'z
akkauntini ulamaydi. Lekin muhim cheklov: sizning akkauntingiz **faqat o'zi
a'zo bo'lgan** kanalning a'zolar ro'yxatini ko'radi. Ya'ni:

- O'z kanallaringiz → `/scan` ishlaydi
- Boshqa odamning kanali → sizni ham o'sha kanalga **admin** qilib qo'shsa ishlaydi;
  qo'shmasa `/scan` «kanalni topa olmadim» deydi (yangi kelayotganlar himoyasi esa
  baribir ishlaydi)
- Boshqa odam o'z kanalini mustaqil tozalashni xohlasa — bu loyihaning o'z
  nusxasini (o'z bot tokeni va o'z login'i bilan) ishga tushirishi kerak

### 5.1.2. Botdan boshqalarga xizmat ko'rsatish (to'g'ri usul)

Agar boshqa kanal egalari ham botingiz orqali **o'z** kanalini tozalashini
xohlasangiz, ular sizga hech narsa bermaydi — Telegramning o'z huquqlar
tizimidan foydalaniladi:

1. Kanal egasi botga **`/skaner_akkaunt`** yozadi — bot qaysi akkauntni
   qo'shish kerakligini aytadi (masalan `@skaner_hisob`)
2. Egasi o'sha akkauntni kanaliga **admin** qilib qo'shadi + «Ban Users» huquqi
3. Endi `/scan` o'sha kanalda ishlaydi
4. Tozalash tugagach egasi uni adminlikdan olib tashlaydi

Bu rejim uchun `.env` da `SCAN_ONLY_OWNER=0` qilinadi — shunda kanal adminlari
o'z kanali uchun `/scan` ni o'zi ishlata oladi.

**Mijoz uchun to'liq avtomatik oqim:**
1. Mijoz botni kanaliga admin qiladi
2. Bot aynan **qo'shgan odamга** shaxsiy xabar + «🔍 Nakrutkalarni tekshirish»
   tugmasini yuboradi (odam botni oldin `/start` qilgan bo'lsa). Agar `/start`
   qilmagan bo'lsa — bot kanalga «Botni ochish» havolasini qo'yadi
3. Mijoz tugmani bosadi → sizning (Muhammadso) akkauntingiz kanalga avtomatik
   qo'shiladi → bot admin qilishni so'raydi → admin bo'lgach a'zolar tekshiriladi
4. Bot **o'sha mijozga** «mana shuncha nakrutka topildi» hisoboti + CSV yuboradi
5. Mijoz tugma bilan tasdiqласa, bot ularni bloklaydi

> Bu oqim uchun `.env`: `SCAN_ONLY_OWNER=0` va `AUTO_JOIN=1`.
> Bot egasi (siz) ham har bir qo'shilish haqida qisqa bildirishnoma olasiz.

**Avtomatik qo'shilish.** `.env` da `AUTO_JOIN=1` bo'lsa, skaner akkaunti kanalda
a'zo bo'lmasa, bot (admin sifatida) vaqtinchalik taklif havolasi yaratadi va
akkaunt o'sha havola orqali **o'zi qo'shiladi** — siz qo'lda har bir kanalga
kirib o'tirmaysiz. Havola darhol bekor qilinadi.

> ⚠️ **Lekin to'liq avtomatlashtirib bo'lmaydigan bitta qadam bor — bu
> Telegramning xavfsizlik chegarasi, kod bilan aylanib o'tib bo'lmaydi:**
> akkauntni **admin qilishni** faqat kanal egasi qila oladi. Hech qanday bot
> yoki skript o'zini (yoki boshqa akkauntni) admin qila olmaydi — aks holda
> istalgan bot istalgan kanalni egallab olardi. Shuning uchun oqim shunday:
> bot akkauntni kanalga **qo'shadi** (avtomatik), so'ng egasiga «endi uni admin
> qiling» deb **aniq ko'rsatma** beradi (bir marta, uch marta bosish). Admin
> bo'lgandan keyin `/scan` to'liq ishlaydi.
>
> **Nega admin shart?** Oddiy a'zo (admin emas) kanalning a'zolar ro'yxatini
> ko'ra olmaydi (broadcast kanalda umuman, superguruhda ~200 tadan ortig'ini
> ko'rmaydi). Siz aytgan «200 cheklovi» aynan shu — va u faqat **admin** bo'lish
> bilan ochiladi, boshqa yo'l yo'q.

> 🚨 **Jiddiy ogohlantirish — akkaunt bloklanishi.** Bitta akkaunt qisqa vaqtda
> ko'p kanalga qo'shilsa, Telegram uni spam deb hisoblab vaqtincha yoki
> **butunlay** cheklaydi (FloodWait / akkaunt bloki). Agar xizmatingiz o'nlab
> mijozga xizmat qiladigan bo'lsa:
> - Shaxsiy akkauntingizni ishlatmang — **alohida, maxsus akkaunt** oching
> - Kuniga ~20-30 tadan ko'p yangi kanalga qo'shmang
> - Bot flood xabarini ko'rsatsa, kuting (o'zi to'xtaydi, yiqilmaydi)
> - Juda ko'p mijoz uchun — bir nechta akkaunt orasida taqsimlash kerak bo'ladi

> 🚫 **Hech qachon qilmang:** botga foydalanuvchining telefon raqami va Telegram
> **login kodini** so'ratish. Telegram kodni yuborganda «bu kodni hech kimga
> bermang» deb ogohlantiradi — chunki bu akkaunt o'g'irlashning asosiy usuli.
> Kod kiritilgan sessiya o'sha odamning **butun akkauntiga** (barcha shaxsiy
> yozishmalariga) kirish beradi — Telegramda «faqat a'zolar ro'yxatini o'qish»
> degan cheklangan ruxsat yo'q. Telegram bunday botlarni bloklaydi, kod kiritgan
> akkauntlar esa cheklanadi. Yuqoridagi adminlik usuli xuddi shu natijani
> beradi, lekin hech kim hech narsa xavf ostiga qo'ymaydi.

`.env` dagi `SCAN_ONLY_OWNER=1` sozlamasi `/scan` ni faqat `ADMIN_IDS` dagi
egalarga ruxsat beradi — boshqa kanal adminlari sizning akkauntingiz orqali
skaner ishlatib yubormaydi. 0 qilsangiz kanal adminlari ham ishlatadi.

> 🔐 **Xavfsizlik:** `scanner.session` fayli va `.env` — bu sizning Telegram
> akkauntingizga kirish kaliti. Ularni hech kimga bermang, GitHub'ga yuklamang.
> Botni birov bilan birgalikda serverga qo'yadigan bo'lsangiz, bu fayllarga
> faqat sizda ruxsat bo'lishi kerak.

### 5.2. Konsol varianti (katta kanallar uchun)
`scan.bat` ni bosing yoki konsolda:

```bash
# kanallar ro'yxati
python scanner.py --list

# faqat tekshirish — hech kim o'chirilmaydi, CSV hisobot yaratiladi
python scanner.py --chat @mykanal

# qattiqroq tekshirish (rasmi yo'qlar ham nakrutka deb hisoblanadi)
python scanner.py --chat @mykanal --strict 2

# faqat ma'lum sanadan keyin kirganlarni tekshirish (nakrutka to'lqinini tozalash)
python scanner.py --chat @mykanal --since 2026-11-01

# bio ham tekshiriladi (aniqroq, lekin sekin)
python scanner.py --chat @mykanal --deep

# topilganlarni haqiqatan o'chirish
python scanner.py --chat @mykanal --apply --mode ban
```

Natija: `hisobot_KanalNomi_20261119_1430.csv` — Excel'da ochib,
eng yuqori balli akkauntlarni ko'rib chiqing. **Avval hisobotni ko'ring,
keyin `--apply` qiling.**

### Cheklovlar
- Siz (bot emas) kanalda **admin** bo'lishingiz kerak
- Bot ishlab turganda konsol skaneri bilan bir vaqtda ishlatmaslik yaxshi
  (sessiya fayli band bo'lishi mumkin) — `/scan` ni ishlatish qulayroq
- Telegram juda katta kanallarda a'zolar ro'yxatini ~10 000 tagacha beradi
- Ko'p o'chirishda Telegram vaqtincha cheklaydi (FloodWait) — skript o'zi kutadi,
  `--delay 2` bilan pauzani oshirsa xavfsizroq

---

## 6. Nakrutka to'lqinidan himoya

`.env` dagi sozlamalar:

```ini
BURST_WINDOW=60      # 60 sekund ichida
BURST_LIMIT=8        # 8 dan ko'p odam kirsa -> to'lqin deb hisoblanadi
AUTO_ROTATE_LINK=1   # to'lqin paytida taklif havolasini avtomatik yangilash
```

To'lqin aniqlansa, kirayotganlarning hammasiga +25 ball qo'shiladi va
`AUTO_ROTATE_LINK=1` bo'lsa eski taklif havolasi bekor qilinadi
(nakrutka servis ishlatayotgan havola ishdan chiqadi). Yangi havola
log kanalga yuboriladi.

---

## 7. Telegram Web App (Mini App)

Botda zamonaviy va qulay Web App interfeysi mavjud:
- 🛡 **Kanallarni boshqarish:** rejim, chegara, qattiqlik va tezkor profillar (presets)
- 🧹 **Tozalash (Skaner):** eski nakrutkalarni tekshirish, topilgan botlar ro'yxatini ko'rish va bir tugma bilan barchasini bloklash
- 📜 **Hodisalar jurnali:** qaysi kanalga kim kirdi, necha ball oldi va nima sababdan bloklandi
- ⚪ **Oq ro'yxat:** qoidadan ozod qilingan ID larni ko'rish, qo'shish va o'chirish

### Web App'ni ishga tushirish:
1. `start.bat` (`python bot.py`) ishga tushirilganda avtomatik ravishda `WEBAPP_PORT` (odatda 8080) portida server ham ishga tushadi.
2. Web App Telegram ichida ishlashi uchun unga HTTPS havola kerak bo'ladi. Buning uchun bepul **Cloudflare Tunnel** yoki **ngrok** ishlatish mumkin:
   ```bash
   cloudflared tunnel --url http://localhost:8080
   ```
3. Olingan `https://xxxx.trycloudflare.com` manzilini `.env` faylida `WEBAPP_URL` qatoriga yozing:
   ```ini
   WEBAPP_URL=https://xxxx.trycloudflare.com
   ```
### Web App turlari:
1. **Foydalanuvchi Web App** (`/index.html`): Har bir mijoz faqat o'zining kanallarini, o'zining statistikasini va oq ro'yxatini ko'radi.
2. **Bosh Admin Web App** (`/admin.html`): Faqat `.env` dagi `ADMIN_IDS` egalari uchun!
   - 👑 **Barcha kanallar monitoringi:** bot qo'shilgan hamma kanallarning to'liq ro'yxati, sozlamalari va statistikasi
   - 👥 **Mijozlar bazasi:** botdan foydalanayotgan barcha kanal egalari va ularning kanallari soni
   - 📢 **Xabarnoma (Broadcast):** barcha mijozlarga bir vaqtda xabar tarqatish
   - 📜 **Global loglar:** butun bot bo'yicha real-vaqtda barcha bloklashlar oqimi
   - ⛔️ **Xavfsizlik:** oddiy foydalanuvchi bu manzilni ochsa, ruxsat berilmaydi (`403 Forbidden`).

Botda adminlar uchun `/admin` menyusida va `/admin_app` buyrug'i orqali ochiladi.

---

## 8. Fayllar

```
bot.py            — asosiy bot + Mini App integratsiyasi
webapp_server.py  — Telegram Mini App backend serveri (aiohttp)
webapp/index.html — zamonaviy React Mini App frontend interfeysi (foydalanuvchi)
webapp/admin.html — Bosh Admin Web App paneli (faqat adminlar uchun)
detector.py       — aniqlash algoritmi (ballar va qattiq qoidalar shu yerda)
scan_core.py      — a'zolar ro'yxatini o'qish/tahlil qilish (bot ham, CLI ham)
scanner.py        — konsol skaneri (katta kanallar, CSV)
login.py          — bir martalik akkaunt login
database.py       — SQLite (sozlamalar, loglar, oq ro'yxat)
config.py         — .env o'qish
_test_web.py      — Web App backendini tekshirish testi
test_detector.py  — algoritmni tekshirish (python test_detector.py)
.env.example      — sozlamalar namunasi

install.bat       — o'rnatish
start.bat         — BOTNI ISHGA TUSHIRISH (avtomatik restart bilan)
tunnel.bat        — Web App uchun bepul HTTPS havola yaratish (Cloudflare)
login.bat         — bir martalik login (/scan uchun)
scan.bat          — konsol skaneri
```

---

## 9. Tez-tez uchraydigan muammolar

**Bot hech kimni bloklamayapti / ba'zilarni o'tkazib yuboryapti**
→ 4.1-bo'limga qarang (sababni aniqlash va qattiqlikni oshirish).

**Haqiqiy odamlarni bloklayapti**
- Chegarani oshiring (`/panel` → ➕5, yoki `SCORE_THRESHOLD=60`)
- `PROTECT_PREMIUM=1` qiling
- Xato bloklanganni log xabaridagi «♻️ Blokdan chiqarish» tugmasi bilan qaytaring,
  so'ng «✅ Oq ro'yxat» ga qo'shing

**«Akkaunt yangi» hammaga qo'yilmoqda**
`NEW_ACCOUNT_ID` qiymatini o'zgartiring. O'z ID'ingizdan foydalanib taxminlang:
`/id` buyrug'i bilan yangi ro'yxatdan o'tgan tanishingiz ID'sini ko'ring va
`NEW_ACCOUNT_ID` ni shunga yaqin qilib qo'ying.

**Bot to'xtab qoladi**
`start.bat` o'zi 10 sekunddan keyin qayta ishga tushiradi. Doimiy ishlashi uchun
botni VPS (serverga) joylash tavsiya etiladi.

---

## 9. Muhim eslatma

Bu bot **ehtimollik** bo'yicha ishlaydi — 100% aniqlik bo'lmaydi. Rasmi va
username'i yo'q yangi akkaunt haqiqiy odam ham bo'lishi mumkin. Shuning uchun:

1. `report` rejimida boshlang,
2. chegarani o'z auditoriyangizga moslang,
3. oq ro'yxatdan foydalaning.
