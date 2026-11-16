# EMA Cross Alert · UZSE aksiyalari

Oʻzbekiston fond birjasi (UZSE) aksiyalarida **EMA 9 / EMA 26 cross** boʻlganda Telegram'ga alert yuboradi va natijalarni veb-dashboard'da koʻrsatadi. Hammasi GitHub Actions'da bepul ishlaydi, kompyuter yoqiq boʻlishi shart emas.

## Imkoniyatlar

- 54 ta aksiya (obligatsiyalarsiz) uchun kunlik shamlar boʻyicha EMA 9 va EMA 26 hisoblanadi.
- Yangi cross boʻlsa, Telegram'ga xabar keladi: 🟢 yuqoriga (EMA9 > EMA26) yoki 🔴 pastga.
- Har tekshiruvdan keyin Telegram'ga qisqa xulosa yuboriladi (nechta aksiya tekshirildi, qaysilarida cross boʻldi, qaysilari olinmadi).
- Veb-dashboard: qidiruv, filtrlar, saralash, mini-grafiklar va har aksiya uchun narx + EMA grafigi.

## Qanday ishlaydi

```
GitHub Actions (har kuni 17:30 Toshkent)
        │
        ▼
ema_cross_alert.py ──► GoInvest ochiq API (kunlik shamlar)
        │
        ├──► Telegram (alert + xulosa)
        └──► docs/data.json ──► docs/index.html (GitHub Pages)
```

## Fayllar

| Fayl | Vazifasi |
|---|---|
| `ema_cross_alert.py` | Asosiy skript: maʼlumot olish, EMA hisoblash, Telegram, `data.json` yaratish |
| `.github/workflows/ema-cross.yml` | Jadval boʻyicha ishga tushirish va natijani repo'ga saqlash |
| `docs/index.html` | Veb-dashboard (`data.json` ni oʻqiydi) |
| `docs/data.json` | Skript yaratadi: har aksiya uchun narx, EMA va cross maʼlumoti |
| `ticker_meta.json` | Skript yaratadi: tiker → GoInvest ID va nom (kesh) |
| `ema_state.json` | Skript yaratadi: yuborilgan alertlar (takror yubormaslik uchun) |

## Oʻrnatish

### 1. Telegram bot

1. Telegram'da **@BotFather** ga `/newbot` yozing, token oling.
2. Yaratilgan botni oching va **Start** bosing.
3. **@userinfobot** orqali oʻzingizning chat ID'ingizni oling.

### 2. GitHub Secrets

Repo → Settings → Secrets and variables → Actions → **New repository secret**:

| Name | Qiymat |
|---|---|
| `TG_TOKEN` | BotFather bergan token |
| `TG_CHAT_ID` | Sizning chat ID |

### 3. Birinchi ishga tushirish

Actions → **EMA Cross Alert** → **Run workflow**. Birinchi marta ~3–5 daqiqa ketadi (tiker jadvali tuziladi). Tugagach `ticker_meta.json` va `docs/data.json` paydo boʻladi, Telegram'ga xulosa keladi.

> Run ishlab turganda repo'da fayllarni oʻzgartirmang. Eski run sahifasidagi *Re-run* tugmasini emas, aynan **Run workflow** tugmasini ishlating.

### 4. Veb-dashboard (GitHub Pages)

Settings → **Pages** → Source: *Deploy from a branch* → Branch: `main`, papka `/docs` → Save. Manzil: `https://<username>.github.io/<repo-nomi>/`.

Bepul hisobda Pages private repo'da ishlamaydi. Repo'ni public qilish xavfsiz: token va chat ID Secrets'da turadi, repo'da koʻrinmaydi.

## Sozlash

`ema_cross_alert.py` boshidagi **SOZLAMALAR** boʻlimi:

| Oʻzgaruvchi | Maʼnosi |
|---|---|
| `TICKERS` | Kuzatiladigan aksiyalar roʻyxati |
| `SHORT`, `LONG` | EMA davrlari (standart 9 va 26) |
| `LIMIT` | Nechta kunlik sham olinadi (350) |
| `SERIES_N` | Veb-grafikda nechta sham koʻrsatiladi (120) |

Tekshiruv vaqti `ema-cross.yml` ichidagi `cron` qatorida. U UTC'da yoziladi, Toshkent = UTC+5. Hozir `30 12 * * 1-5`, yaʼni dushanba–juma 17:30 (Toshkent).

## Lokal ishga tushirish

```bash
pip install requests
export TG_TOKEN="..." TG_CHAT_ID="..."
python ema_cross_alert.py --inspect KVTS   # bitta aksiyani tekshirish
python ema_cross_alert.py --once           # hammasini bir marta tekshirish
```

Veb-sahifani lokal koʻrish uchun `docs` papkasida `python -m http.server` ishga tushirib, `http://localhost:8000` ni oching (fayl toʻgʻridan-toʻgʻri ochilsa, `data.json` yuklanmaydi).

## Muammolarni hal qilish

| Muammo | Sabab va yechim |
|---|---|
| `Holatni saqlash` qadamida `fetch first` xatosi | Run paytida repo oʻzgargan. Workflow `git pull --rebase` bilan buni oʻzi hal qiladi. Eski commit'dan *Re-run* qilmang |
| Telegram'ga xabar kelmaydi | `TG_TOKEN` / `TG_CHAT_ID` nomlari va qiymatlarini tekshiring, botga **Start** bosganingizni tasdiqlang |
| Xulosada `⚠️ Olinmadi: ...` | Tiker GoInvest'da boshqacha nomlangan yoki server vaqtincha javob bermagan. Logda sababi yoziladi |
| `GoInvest'da tiker topilmadi` | Tikerni `TICKERS` dan olib tashlang yoki toʻgʻri nomini yozing, keyin `ticker_meta.json` ni oʻchirib qayta ishga tushiring |
| Sahifada "Maʼlumot topilmadi" | `docs/data.json` hali yaratilmagan. Workflow'ni bir marta muvaffaqiyatli ishga tushiring |

## Eslatmalar

- Maʼlumot manbai — GoInvest'ning ochiq (hujjatlashtirilmagan) API'si. U oʻzgarishi yoki ishlamay qolishi mumkin.
- Cross faqat **oxirgi kunlik sham** boʻyicha aniqlanadi. Siyrak savdo qilinadigan aksiyalarda EMA signallari kam ishonchli.
- Bu loyiha investitsion tavsiya emas.
