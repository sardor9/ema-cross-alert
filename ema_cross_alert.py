"""
EMA Cross alert — UZSE aksiyalari (GoInvest ochiq API) -> Telegram + veb-sahifa uchun docs/data.json

Ishlatish:
    pip install requests
    export TG_TOKEN="..." ; export TG_CHAT_ID="..."
    python ema_cross_alert.py --inspect KVTS     # bitta aksiyani tekshirish
    python ema_cross_alert.py --once             # bir marta tekshiradi (GitHub Actions)
"""
import argparse, datetime, json, os, sys, time
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
SERIES_N = 120                       # veb-grafik uchun oxirgi shamlar soni
CHECK_EVERY = 24 * 3600              # faqat doimiy rejim uchun
STATE_FILE = "ema_state.json"        # takroriy alertni oldini olish
META_FILE = "ticker_meta.json"       # tiker -> {id, name, sector}
DATA_FILE = "docs/data.json"         # veb-sahifa o'qiydigan fayl
API = "https://api.goinvest.uz/api"
MAX_ID = 400
PAUSE = 0.7
TRIES = 4
TG_TOKEN = os.getenv("TG_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")
# --------------------------------------------

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "ema-cross-alert/3.0"


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
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data, **kw):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, sort_keys=True, **kw)


def discover_ids(wanted, meta):
    """Stock/{id}/ ni aylanib, tiker -> {id, name, sector} jadvalini to'ldiradi (bir marta, keyin keshlanadi)."""
    missing = set(wanted) - set(meta)
    misses = 0
    for i in range(1, MAX_ID + 1):
        if not missing:
            break
        try:
            r = SESSION.get(f"{API}/webapp/v1/stock/Stock/{i}/", timeout=(10, 30))
            if r.status_code != 200:
                misses += 1
                if misses >= 40 and i > 100:
                    break
                continue
            d = r.json()
            misses = 0
            tk = d.get("ticker")
            if tk:
                meta[tk] = {"id": d["id"],
                            "name": d.get("short_title") or d.get("title") or tk,
                            "sector": d.get("category") or ""}
                missing.discard(tk)
        except (requests.RequestException, ValueError):
            pass
        time.sleep(0.4)
    return meta


def get_closes(stock_id):
    """(yopilish narxlari, sanalar) — eskidan yangiga."""
    j = get_json(f"{API}/app/v1/stock/StockGraphData/",
                 {"stock": stock_id, "limit": LIMIT, "date": "d"})
    rows = [r for r in j["results"] if r.get("closing_price") is not None]
    rows.sort(key=lambda r: r["date_"])
    return [float(r["closing_price"]) for r in rows], [r["date_"] for r in rows]


def ema(values, n):
    k = 2 / (n + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def analyze(t, m, closes, dates):
    s, l = ema(closes, SHORT), ema(closes, LONG)
    n = len(closes) - 1
    last = None
    for i in range(n, LONG - 1, -1):               # isinish davridan oldingi soxta cross'larni o'tkazib yuboramiz
        if s[i - 1] <= l[i - 1] and s[i] > l[i]:
            last = ("up", i); break
        if s[i - 1] >= l[i - 1] and s[i] < l[i]:
            last = ("down", i); break
    prev = closes[-2]
    r = lambda arr: [round(x, 2) for x in arr[-SERIES_N:]]
    return {
        "t": t, "name": m.get("name", t), "sector": m.get("sector", ""),
        "last": round(closes[-1], 2), "chg": round((closes[-1] / prev - 1) * 100, 2) if prev else 0,
        "ema_s": round(s[-1], 2), "ema_l": round(l[-1], 2), "above": s[-1] > l[-1],
        "cross": last[0] if last else None,
        "cross_date": dates[last[1]] if last else None,
        "ago": (n - last[1]) if last else None,
        "date": dates[-1], "bars": len(closes),
        "dates": dates[-SERIES_N:], "c": r(closes), "s": r(s), "l": r(l),
    }


def send_tg(text):
    if not TG_TOKEN or not TG_CHAT_ID:
        print("[TG sozlanmagan]", text)
        return
    requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                  json={"chat_id": TG_CHAT_ID, "text": text}, timeout=20)


def check_one(t, meta, st, crosses, items):
    if t not in meta:
        raise KeyError("GoInvest'da tiker topilmadi")
    closes, dates = get_closes(meta[t]["id"])
    if len(closes) < LONG + 2:
        raise ValueError(f"tarix yetarli emas ({len(closes)} sham)")
    it = analyze(t, meta[t], closes, dates)
    items[t] = it
    sig = it["cross"] if it["ago"] == 0 else None
    key = f"{sig}:{it['date']}"                    # bir xil sham uchun qayta yubormaslik
    if sig and st.get(t) != key:
        arrow = "🟢 YUQORIGA (EMA9 > EMA26)" if sig == "up" else "🔴 PASTGA (EMA9 < EMA26)"
        send_tg(f"EMA Cross: {t} · {it['name']}\n{arrow}\nNarx: {it['last']:,.2f} ({it['date']})")
        st[t] = key
        crosses.append(f"{t} {'▲' if sig == 'up' else '▼'}")
    print(f"{t}: {sig or 'cross yo‘q'} ({it['date']}, {len(closes)} sham)")


def run_pass(tickers, meta, st, crosses, items):
    """Ketma-ket 6 ta xatodan keyin to'xtaydi (server o'chiq bo'lsa vaqt ketmasligi uchun)."""
    failed, streak = [], 0
    for idx, t in enumerate(tickers):
        try:
            check_one(t, meta, st, crosses, items)
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


def write_data(items, failed):
    old = {x["t"]: x for x in load_json(DATA_FILE, {}).get("items", [])}
    out = []
    for t in TICKERS:
        if t in items:
            out.append(items[t])
        elif t in old:                              # olinmagan tikerning eski ma'lumoti saqlanadi
            old[t]["stale"] = True
            out.append(old[t])
    save_json(DATA_FILE, {
        "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "short": SHORT, "long": LONG, "items": out, "failed": failed,
    }, separators=(",", ":"))


def check_all():
    st = load_json(STATE_FILE, {})
    meta = load_json(META_FILE, {})
    meta = {k: v for k, v in meta.items() if isinstance(v, dict)}   # eski formatni tashlab yuboradi
    if set(TICKERS) - set(meta):
        print("Tiker jadvali to'ldirilmoqda…")
        meta = discover_ids(TICKERS, meta)
        save_json(META_FILE, meta, indent=1)
    crosses, items = [], {}
    failed = run_pass(TICKERS, meta, st, crosses, items)
    if failed and len(failed) < len(TICKERS):
        retry = [t for t in failed if t in meta]
        if retry:
            print(f"Qayta urinish: {len(retry)} ta tiker", file=sys.stderr)
            time.sleep(30)
            again = run_pass(retry, meta, st, crosses, items)
            failed = [t for t in failed if t not in retry] + again
    save_json(STATE_FILE, st)
    write_data(items, failed)
    ok = len(TICKERS) - len(failed)
    summary = f"✅ EMA tekshiruvi tugadi: {ok}/{len(TICKERS)} aksiya tekshirildi."
    summary += f"\nCross: {', '.join(crosses)}" if crosses else "\nYangi cross yo'q."
    if failed:
        summary += f"\n⚠️ Olinmadi: {', '.join(failed)}"
    send_tg(summary)
    if len(failed) == len(TICKERS):
        sys.exit(1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--inspect", metavar="TICKER")
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    if a.inspect:
        meta = discover_ids([a.inspect], load_json(META_FILE, {}))
        m = meta.get(a.inspect)
        print("Meta:", m)
        if m:
            c, d = get_closes(m["id"])
            it = analyze(a.inspect, m, c, d)
            print({k: v for k, v in it.items() if k not in ("dates", "c", "s", "l")})
    elif a.once:
        check_all()
    else:
        while True:
            check_all()
            time.sleep(CHECK_EVERY)
