#!/usr/bin/env python3
"""
XRP 박스 mean-reversion paper — Keltner_20_1.5 + BTC risk-on filter.
8년 백테스트 통과 (CAGR +15%, OOS PF 1.82). Stage 0 paper 검증 진입.
독립 서비스 (paper_xrp.db). BTC paper 영향 X.
룰: 진입=XRP_low<=Keltner_lower, 익절=midline, 손절=lower-1.0*ATR14, time_stop=20d, cooldown=3d, 1.5x.
"""
import os, sqlite3, datetime, math, time, sys
from pybit.unified_trading import HTTP

# 파라미터 (Wave 6 OOS 통과)
SMA_N = 20; ATR_N = 14
KELTNER_K = 1.5
SL_ATR_MULT = 1.0
LEV = 1.5
TIME_STOP_DAYS = 20
COOLDOWN_DAYS = 3
WIDTH_MIN, WIDTH_MAX = 0.05, 0.80
MM = 0.005
FEE_PERP = 0.0006
INTERVAL = int(os.getenv("METIS_PAPER_INTERVAL", "600"))
DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(DIR, "paper_xrp.db")
VARIANT = "V_xrp_keltner"

s = HTTP(testnet=False, api_key=os.getenv("BYBIT_API_KEY"),
         api_secret=os.getenv("BYBIT_API_SECRET") or os.getenv("BYBIT_SECRET"))


def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c


def init():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS xstate(id INTEGER PRIMARY KEY, equity REAL, leverage REAL,
        active INT, last_price REAL, entry_price REAL, entry_eq REAL, peak_eq REAL,
        tp_price REAL, sl_price REAL, entry_date TEXT, last_lev_date TEXT,
        last_fund_ts INTEGER, cooldown_until_date TEXT, days_held INTEGER);
    CREATE TABLE IF NOT EXISTS xequity(ts TEXT, price REAL, leverage REAL, equity REAL,
        liq_price REAL, liq_dist REAL, event TEXT);
    CREATE TABLE IF NOT EXISTS xdaily(date TEXT PRIMARY KEY, xrp_close REAL, sma20 REAL,
        atr14 REAL, keltner_lower REAL, keltner_mid REAL, keltner_upper REAL,
        width_pct REAL, btc_filter_ok INT, signal TEXT);
    """); c.commit(); c.close()


def xrp_daily():
    """XRP 일봉 (완성봉)."""
    r = s.get_kline(category="linear", symbol="XRPUSDT", interval="D", limit=200)["result"]["list"]
    rows = sorted(([int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4])] for x in r), key=lambda z: z[0])
    t0 = int(datetime.datetime.now(datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()*1000)
    rows = [x for x in rows if x[0] < t0]
    return rows                          # [(ts, o, h, l, c), ...]


def xrp_price():
    return float(s.get_tickers(category="linear", symbol="XRPUSDT")["result"]["list"][0]["lastPrice"])


def xrp_intraday_low(since_ms):
    r = s.get_kline(category="linear", symbol="XRPUSDT", interval="1", limit=30)["result"]["list"]
    lows = [float(x[3]) for x in r if int(x[0]) >= since_ms - 60000]
    return min(lows) if lows else None


def xrp_intraday_high(since_ms):
    r = s.get_kline(category="linear", symbol="XRPUSDT", interval="1", limit=30)["result"]["list"]
    highs = [float(x[2]) for x in r if int(x[0]) >= since_ms - 60000]
    return max(highs) if highs else None


def latest_funding():
    r = s.get_funding_rate_history(category="linear", symbol="XRPUSDT", limit=5)["result"]["list"]
    return (int(r[0]["fundingRateTimestamp"]), float(r[0]["fundingRate"])) if r else (0, 0.0)


def btc_filter_ok():
    """BTC risk-on: close>SMA125 AND vol20/vol60<1.5."""
    try:
        r = s.get_kline(category="spot", symbol="BTCUSDT", interval="D", limit=200)["result"]["list"]
        rows = sorted(([int(x[0]), float(x[4])] for x in r), key=lambda z: z[0])
        t0 = int(datetime.datetime.now(datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()*1000)
        closes = [x[1] for x in rows if x[0] < t0]
        if len(closes) < 125: return True
        sma125 = sum(closes[-125:])/125
        if closes[-1] <= sma125: return False
        if len(closes) >= 60:
            r20 = [closes[i]/closes[i-1]-1 for i in range(len(closes)-19, len(closes))]
            r60 = [closes[i]/closes[i-1]-1 for i in range(len(closes)-59, len(closes))]
            v20 = (sum((x-sum(r20)/20)**2 for x in r20)/20)**0.5*math.sqrt(365)
            v60 = (sum((x-sum(r60)/60)**2 for x in r60)/60)**0.5*math.sqrt(365)
            if v60 > 0 and v20/v60 >= 1.5: return False
        return True
    except Exception:
        return True


def btc_force_exit():
    """보유 중 강제 청산: BTC가 추세 깨거나 vol 폭증."""
    try:
        r = s.get_kline(category="spot", symbol="BTCUSDT", interval="D", limit=200)["result"]["list"]
        rows = sorted(([int(x[0]), float(x[4])] for x in r), key=lambda z: z[0])
        t0 = int(datetime.datetime.now(datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()*1000)
        closes = [x[1] for x in rows if x[0] < t0]
        if len(closes) < 125: return False
        sma125 = sum(closes[-125:])/125
        if closes[-1] < sma125 * 0.98: return True
        if len(closes) >= 60:
            r20 = [closes[i]/closes[i-1]-1 for i in range(len(closes)-19, len(closes))]
            r60 = [closes[i]/closes[i-1]-1 for i in range(len(closes)-59, len(closes))]
            v20 = (sum((x-sum(r20)/20)**2 for x in r20)/20)**0.5*math.sqrt(365)
            v60 = (sum((x-sum(r60)/60)**2 for x in r60)/60)**0.5*math.sqrt(365)
            if v60 > 0 and v20/v60 >= 2.0: return True
        if len(closes) >= 2 and (closes[-1]/closes[-2]-1) <= -0.08: return True
        return False
    except Exception:
        return False


def compute_keltner(rows):
    """rows=[(ts,o,h,l,c)], 마지막 봉 = t-1 (완성). t-1 기준 Keltner."""
    if len(rows) < max(SMA_N, ATR_N+1): return None
    closes = [r[4] for r in rows[-SMA_N:]]
    sma20 = sum(closes)/SMA_N
    tr = []
    for i in range(len(rows)-ATR_N, len(rows)):
        h, l, prev_c = rows[i][2], rows[i][3], rows[i-1][4]
        tr.append(max(h-l, abs(h-prev_c), abs(l-prev_c)))
    atr14 = sum(tr)/ATR_N
    lower = sma20 - KELTNER_K * atr14
    upper = sma20 + KELTNER_K * atr14
    return sma20, atr14, lower, sma20, upper


def liq_of(entry_price, lev):
    if lev <= 0: return 0.0, 0.0
    lp = entry_price * (1 - (1 - MM)/lev)
    return lp, 100.0  # liq_dist will be recomputed with current price


def cycle():
    init()
    rows = xrp_daily()
    if not rows: print("no XRP data"); return
    price = xrp_price()
    fund_ts, fund_rate = latest_funding()
    k = compute_keltner(rows)
    if not k: print("not enough data for Keltner"); return
    sma20, atr14, lower, mid, upper = k
    width_pct = (upper - lower)/mid if mid > 0 else 0
    btc_ok = btc_filter_ok()
    btc_off = btc_force_exit()
    date = datetime.datetime.utcfromtimestamp(rows[-1][0]/1000).strftime("%Y-%m-%d")
    now = datetime.datetime.utcnow().isoformat()
    c = db()
    st = c.execute("SELECT * FROM xstate WHERE id=1").fetchone()
    if st is None:
        c.execute("INSERT INTO xstate(id,equity,leverage,active,last_price,entry_price,entry_eq,peak_eq,tp_price,sl_price,entry_date,last_lev_date,last_fund_ts,cooldown_until_date,days_held) VALUES(1,1000.0,0,0,?,0,0,0,0,0,?,?,?,?,0)",
                  (price, "", date, fund_ts, ""))
        c.execute("INSERT INTO xequity VALUES(?,?,?,?,?,?,?)", (now, price, 0, 1000.0, 0, 0, "init"))
        c.commit(); c.close(); return
    eq = st["equity"]; lev = st["leverage"]; active = st["active"]; lastp = st["last_price"]
    entry_p = st["entry_price"]; entry_eq = st["entry_eq"]; peak = st["peak_eq"]
    tp = st["tp_price"]; sl = st["sl_price"]; entry_date = st["entry_date"]
    last_lev_date = st["last_lev_date"]; last_fund = st["last_fund_ts"]
    cooldown = st["cooldown_until_date"] or ""; days_held = st["days_held"] or 0
    event = ""
    # 보유 중 처리
    if active and lev > 0:
        # 장중 SL 청산 체크 (1분봉 저가)
        lo = xrp_intraday_low(int(time.time()*1000) - INTERVAL*1000 - 120000) or price
        hi = xrp_intraday_high(int(time.time()*1000) - INTERVAL*1000 - 120000) or price
        # 청산
        liq_px = entry_p * (1 - (1-MM)/lev)
        if lo <= liq_px:
            eq *= max(0.0, 1 + lev*(liq_px/entry_p - 1)); eq = max(eq, 0.01)
            active = 0; lev = 0; event = "LIQUIDATED"
            cooldown = (datetime.datetime.strptime(date, "%Y-%m-%d") + datetime.timedelta(days=COOLDOWN_DAYS)).strftime("%Y-%m-%d")
        # SL hit
        elif lo <= sl:
            pnl = lev * (sl/entry_p - 1)
            eq *= (1 + pnl) * (1 - lev*FEE_PERP)
            active = 0; lev = 0; event = "SL_HIT"
            cooldown = (datetime.datetime.strptime(date, "%Y-%m-%d") + datetime.timedelta(days=COOLDOWN_DAYS)).strftime("%Y-%m-%d")
        # TP hit
        elif hi >= tp:
            pnl = lev * (tp/entry_p - 1)
            eq *= (1 + pnl) * (1 - lev*FEE_PERP)
            active = 0; lev = 0; event = f"TP_HIT@{(pnl*100):.1f}%"
            cooldown = (datetime.datetime.strptime(date, "%Y-%m-%d") + datetime.timedelta(days=COOLDOWN_DAYS)).strftime("%Y-%m-%d")
        # BTC 강제 청산
        elif btc_off:
            eq *= (1 + lev*(price/entry_p - 1)) * (1 - lev*FEE_PERP)
            eq = max(eq, 0.01); active = 0; lev = 0; event = "BTC_OFF"
            cooldown = (datetime.datetime.strptime(date, "%Y-%m-%d") + datetime.timedelta(days=COOLDOWN_DAYS)).strftime("%Y-%m-%d")
        else:
            # mark to market
            eq *= (1 + lev*(price/lastp - 1))
            lastp = price
            # 펀딩
            if fund_ts > last_fund:
                eq *= (1 - lev*fund_rate); last_fund = fund_ts
                event = (event+" funding") if event else "funding"
            # peak
            if eq > peak: peak = eq
            # time stop check (daily)
            if date != last_lev_date:
                days_held += 1
                if days_held >= TIME_STOP_DAYS:
                    eq *= (1 - lev*FEE_PERP)
                    active = 0; lev = 0; event = (event+" TIME_STOP") if event else "TIME_STOP"
                    cooldown = (datetime.datetime.strptime(date, "%Y-%m-%d") + datetime.timedelta(days=COOLDOWN_DAYS)).strftime("%Y-%m-%d")
                last_lev_date = date
    # 신규 진입 (daily rebalance에서만)
    signal = "no_pos"
    if not active and date != last_lev_date:
        in_cooldown = bool(cooldown) and date <= cooldown
        width_ok = WIDTH_MIN <= width_pct <= WIDTH_MAX
        if in_cooldown:
            signal = "COOLDOWN"
        elif not width_ok:
            signal = f"WIDTH_OUT({width_pct*100:.1f}%)"
        elif not btc_ok:
            signal = "BTC_RISK_OFF"
        elif price > lower:
            signal = f"NO_TOUCH (px {price:.4f} > lower {lower:.4f})"
        else:
            # 진입 — 가격이 lower 아래로 왔음
            eq *= (1 - LEV*FEE_PERP)
            entry_p = price; entry_eq = eq; peak = eq
            tp = mid; sl = lower - SL_ATR_MULT * atr14
            active = 1; lev = LEV; lastp = price; entry_date = date; days_held = 0
            event = f"ENTRY@{price:.4f} tp={tp:.4f} sl={sl:.4f}"
            signal = "ENTERED"
        last_lev_date = date
    # 청산거리 계산 (현재가 기준)
    lp = entry_p * (1 - (1-MM)/lev) if active and lev > 0 else 0
    ld = (price - lp)/price*100 if lp > 0 else 0
    # 저장
    c.execute("INSERT OR REPLACE INTO xdaily VALUES(?,?,?,?,?,?,?,?,?,?)",
              (date, rows[-1][4], sma20, atr14, lower, mid, upper, width_pct, int(btc_ok), signal))
    c.execute("""UPDATE xstate SET equity=?,leverage=?,active=?,last_price=?,entry_price=?,entry_eq=?,peak_eq=?,
              tp_price=?,sl_price=?,entry_date=?,last_lev_date=?,last_fund_ts=?,cooldown_until_date=?,days_held=? WHERE id=1""",
              (eq, lev, active, lastp, entry_p, entry_eq, peak, tp, sl, entry_date, last_lev_date, last_fund, cooldown, days_held))
    c.execute("INSERT INTO xequity VALUES(?,?,?,?,?,?,?)", (now, price, lev, eq, lp, ld, event or signal))
    c.commit(); c.close()


def status():
    try:
        c = db()
        st = c.execute("SELECT * FROM xstate WHERE id=1").fetchone()
        n = c.execute("SELECT COUNT(*) FROM xequity").fetchone()[0]
        c.close()
        if not st: return None
        return dict(eq=st["equity"], lev=st["leverage"], active=st["active"],
                    entry=st["entry_price"], tp=st["tp_price"], sl=st["sl_price"], n=n)
    except Exception:
        return None


def main():
    once = "--once" in sys.argv
    while True:
        try: cycle()
        except Exception as e: print("cycle err:", str(e)[:160])
        if once: print(status()); break
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
