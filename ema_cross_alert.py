"""
EMA Cross alert — UZSE aksiyalari (xisobterminal.uz ochiq API) -> Telegram

Ishlatish:
    pip install requests
    export TG_TOKEN="BotFather bergan token"
    export TG_CHAT_ID="sizning chat id"
    python ema_cross_alert.py --inspect UZMK     # avval API formatini ko'rish
    python ema_cross_alert.py                    # doimiy ishlaydi (har 30 daqiqada tekshiradi)
    python ema_cross_alert.py --once             # bir marta tekshiradi (cron uchun)
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
SHORT, LONG = 9, 26                  # skrindagi EMA Cross sozlamasi
RANGE = "1y"                         # tarix uzunligi
CHECK_EVERY = 30 * 60                # sekund
STATE_FILE = "ema_state.json"        # takroriy alertni oldini olish
BASE = "https://xisobterminal.uz"
TG_TOKEN = os.getenv("TG_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")
# --------------------------------------------


def fetch_raw(ticker):
    r = requests.get(f"{BASE}/api/compare",
                     params={"tickers": ticker, "range": RANGE}, timeout=20,
                     headers={"User-Agent": "ema-cross-alert/1.0"})
    r.raise_for_status()
    return r.json()


def _num(p):
    """Nuqtadan (dict yoki [t, v] ro'yxat) qiymatni oladi."""
    if isinstance(p, (list, tuple)) and len(p) >= 2:
        return p[1]
    if isinstance(p, dict):
        for k in ("close", "c", "price", "value", "v", "last"):
            if k in p and p[k] is not None:
                return p[k]
    return p if isinstance(p, (int, float)) else None


def _find_points(obj, ticker):
    """JSON ichidan narx qatorini topadi (format noma'lum bo'lgani uchun moslashuvchan)."""
    if isinstance(obj, list) and obj and all(_num(x) is not None for x in obj[:5]):
        return obj
    if isinstance(obj, dict):
        if ticker in obj:
            found = _find_points(obj[ticker], ticker)
            if found:
                return found
        for v in obj.values():
            found = _find_points(v, ticker)
            if found:
                return found
    if isinstance(obj, list):
        for v in obj:
            found = _find_points(v, ticker)
            if found:
                return found
    return None


def get_closes(ticker):
    pts = _find_points(fetch_raw(ticker), ticker)
    if not pts:
        raise ValueError("Narx qatori topilmadi — --inspect bilan formatni tekshiring")
    return [float(x) for x in (_num(p) for p in pts) if x is not None]


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


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(st):
    with open(STATE_FILE, "w") as f:
        json.dump(st, f)


def check_all():
    st = load_state()
    errors = 0
    for t in TICKERS:
        try:
            closes = get_closes(t)
            sig = detect_cross(closes)
            key = f"{sig}:{len(closes)}"          # bir xil sham uchun qayta yubormaslik
            if sig and st.get(t) != key:
                arrow = "🟢 YUQORIGA (EMA9 > EMA26)" if sig == "up" else "🔴 PASTGA (EMA9 < EMA26)"
                send_tg(f"EMA Cross: {t}\n{arrow}\nSo'nggi narx: {closes[-1]:,.2f}")
                st[t] = key
            print(f"{t}: {sig or 'cross yo‘q'}")
        except Exception as e:
            errors += 1
            print(f"{t}: xato — {e}", file=sys.stderr)
        time.sleep(1.2)                            # API: ~1 so'rov/soniya
    save_state(st)
    if errors == len(TICKERS):                     # hammasi xato -> Actions "failed" bo'ladi
        sys.exit(1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--inspect", metavar="TICKER")
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    if a.inspect:
        print(json.dumps(fetch_raw(a.inspect), indent=2)[:3000])
    elif a.once:
        check_all()
    else:
        while True:
            check_all()
            time.sleep(CHECK_EVERY)
