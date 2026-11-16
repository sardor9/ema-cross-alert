"""
EMA Cross alert — UZSE aksiyalari (GoInvest ochiq API) -> Telegram

Ishlatish:
    pip install requests
    export TG_TOKEN="BotFather bergan token"
    export TG_CHAT_ID="sizning chat id"
    python ema_cross_alert.py --inspect KVTS     # bitta aksiya uchun javobni ko'rish
    python ema_cross_alert.py --once             # bir marta tekshiradi (GitHub Actions uchun)
    python ema_cross_alert.py                    # doimiy ishlaydi (har 24 soatda)
"""
import argparse, json, os, sys, time
import requests

# ---------------- SOZLAMALAR ----------------
TICKERS = [
    "UZINP", "SQBN", "BRBN", "UZTLP", "ALKB", "HMKB", "UZMKP", "UZNF",
    "KVTS", "IPKY", "SQBNP", "KFSK", "UNVB", "ALKBP", "KFSKP", "PLST",
    "URTS", "IPTB", "UZMK", "HMKBP", "UZMT", "KASU", "CBSK", "UZTL",
    "IPTBP", "UZGFP", "UZNGP", "KASUP", "BNGP", "TNBN", "BIOK", "BRBNP",
    "AGBA", "TRSB", "UZAL", "UPOS", "QATT", "QZSM", "BECM", "TMYS",
    "ALSM", "UZIR", "MCBA", "UZIRP", "MCBAP", "BNGPP", "NGQS", "UVGT",
    "AGBAP", "OHDN", "UTGAP", "DORI", "GRBK", "AGMKP",
]   # faqat aksiyalar (obligatsiyalarsiz)
SHORT, LONG = 9, 26                  # EMA Cross sozlamasi
LIMIT = 350                          # nechta kunlik sham olinadi
CHECK_EVERY = 24 * 3600              # faqat doimiy rejim uchun
STATE_FILE = "ema_state.json"        # takroriy alertni oldini olish
IDS_FILE = "ticker_ids.json"         # tiker -> GoInvest ichki ID
API = "https://api.goinvest.uz/api"
MAX_ID = 400                         # ID qidirishda yuqori chegara
PAUSE = 0.7                          # so'rovlar orasidagi pauza (sekund)
TRIES = 4
TG_TOKEN = os.getenv("TG_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")
# --------------------------------------------

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "ema-cross-alert/2.0"


def get_json(url, params=None):
    last = None
    for i in range(TRIES):
        try:
            r = SESSION.get(url, params=params, timeout=(10, 45))
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            last = e
            if i < TRIES - 1:
                time.sleep(5 * (i + 1))
    raise last


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=1, sort_keys=True)


def discover_ids(wanted, ids):
    """Stock/{id}/ ni aylanib, tiker -> ID jadvalini to'ldiradi (bir marta, keyin keshlanadi)."""
    missing = set(wanted) - set(ids)
    misses = 0
    for i in range(1, MAX_ID + 1):
        if not missing:
            break
        try:
            r = SESSION.get(f"{API}/webapp/v1/stock/Stock/{i}/", timeout=(10, 30))
            if r.status_code != 200:
                misses += 1
                if misses >= 40 and i > 100:      # ketma-ket 40 ta bo'sh ID — tugadi
                    break
                continue
            d = r.json()
            misses = 0
            tk = d.get("ticker")
            if tk:
                ids[tk] = d["id"]
                missing.discard(tk)
        except (requests.RequestException, ValueError):
            pass
        time.sleep(0.4)
    return ids


def get_closes(stock_id):
    """(yopilish narxlari eskidan yangiga, oxirgi sham sanasi)."""
    j = get_json(f"{API}/app/v1/stock/StockGraphData/",
                 {"stock": stock_id, "limit": LIMIT, "date": "d"})
    rows = [r for r in j["results"] if r.get("closing_price") is not None]
    rows.sort(key=lambda r: r["date_"])           # eskidan yangiga
    return [float(r["closing_price"]) for r in rows], (rows[-1]["date_"] if rows else "")


def ema(values, n):
    k = 2 / (n + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def detect_cross(closes):
    """Oxirgi sham bo'yicha: 'up' (golden), 'down' (death) yoki None."""
    if len(closes) < LONG + 2:
        return None
    s, l = ema(closes, SHORT), ema(closes, LONG)
    if s[-2] <= l[-2] and s[-1] > l[-1]:
        return "up"
    if s[-2] >= l[-2] and s[-1] < l[-1]:
        return "down"
    return None


def send_tg(text):
    if not TG_TOKEN or not TG_CHAT_ID:
        print("[TG sozlanmagan]", text)
        return
    requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                  json={"chat_id": TG_CHAT_ID, "text": text}, timeout=20)


def check_one(t, ids, st, crosses):
    if t not in ids:
        raise KeyError("GoInvest'da tiker topilmadi")
    closes, last_date = get_closes(ids[t])
    if len(closes) < LONG + 2:
        raise ValueError(f"tarix yetarli emas ({len(closes)} sham)")
    sig = detect_cross(closes)
    key = f"{sig}:{last_date}"                     # bir xil sham uchun qayta yubormaslik
    if sig and st.get(t) != key:
        arrow = "🟢 YUQORIGA (EMA9 > EMA26)" if sig == "up" else "🔴 PASTGA (EMA9 < EMA26)"
        send_tg(f"EMA Cross: {t}\n{arrow}\nNarx: {closes[-1]:,.2f} ({last_date})")
        st[t] = key
        crosses.append(f"{t} {'▲' if sig == 'up' else '▼'}")
    print(f"{t}: {sig or 'cross yo‘q'} ({last_date}, {len(closes)} sham)")


def run_pass(tickers, ids, st, crosses):
    """Ketma-ket 6 ta xatodan keyin to'xtaydi (server o'chiq bo'lsa vaqt ketmasligi uchun)."""
    failed, streak = [], 0
    for idx, t in enumerate(tickers):
        try:
            check_one(t, ids, st, crosses)
            streak = 0
        except KeyError as e:
            failed.append(t)
            print(f"{t}: {e}", file=sys.stderr)
        except Exception as e:
            failed.append(t)
            streak += 1
            print(f"{t}: xato — {e}", file=sys.stderr)
            if streak >= 6:
                failed += tickers[idx + 1:]
                print("Ketma-ket 6 ta xato — to'xtatildi", file=sys.stderr)
                break
        time.sleep(PAUSE)
    return failed


def check_all():
    st = load_json(STATE_FILE, {})
    ids = load_json(IDS_FILE, {})
    if set(TICKERS) - set(ids):
        print("Tiker -> ID jadvali to'ldirilmoqda…")
        ids = discover_ids(TICKERS, ids)
        save_json(IDS_FILE, ids)
    crosses = []
    failed = run_pass(TICKERS, ids, st, crosses)
    if failed and len(failed) < len(TICKERS):
        retry = [t for t in failed if t in ids]
        if retry:
            print(f"Qayta urinish: {len(retry)} ta tiker", file=sys.stderr)
            time.sleep(30)
            again = run_pass(retry, ids, st, crosses)
            failed = [t for t in failed if t not in retry] + again
    save_json(STATE_FILE, st)
    ok = len(TICKERS) - len(failed)
    summary = f"✅ EMA tekshiruvi tugadi: {ok}/{len(TICKERS)} aksiya tekshirildi."
    summary += f"\nCross: {', '.join(crosses)}" if crosses else "\nYangi cross yo'q."
    if failed:
        summary += f"\n⚠️ Olinmadi: {', '.join(failed)}"
    send_tg(summary)
    if len(failed) == len(TICKERS):                # hammasi xato -> Actions "failed" bo'ladi
        sys.exit(1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--inspect", metavar="TICKER")
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    if a.inspect:
        ids = discover_ids([a.inspect], load_json(IDS_FILE, {}))
        sid = ids.get(a.inspect)
        print("ID:", sid)
        if sid:
            c, d = get_closes(sid)
            print(len(c), "sham, oxirgisi", d, c[-5:], "->", detect_cross(c) or "cross yo'q")
    elif a.once:
        check_all()
    else:
        while True:
            check_all()
            time.sleep(CHECK_EVERY)
