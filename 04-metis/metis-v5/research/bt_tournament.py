#!/usr/bin/env python3
"""
운영자 "모든 가용한 모든걸" — 전략 대 토너먼트. Binance 일봉 풀히스토리 2017~ (4코인).
추세/모멘텀/돌파/채널 + 평균회귀/분할매수 + 포트폴리오 로테이션. 파라미터 스윕. BH/v4 대비 랭킹.
수수료 0.1%. 롱/현금(무차입). 상세 + 긴 시점.
"""
import requests, time, datetime, math, os
import numpy as np

FEE = 0.001; CASH0 = 10000.0
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btcache_ohlc")


def fetch(sym, start_year=2017):
    os.makedirs(CACHE, exist_ok=True)
    fn = f"{CACHE}/{sym}_{start_year}.npz"
    if os.path.exists(fn) and time.time()-os.path.getmtime(fn) < 43200:
        d = np.load(fn); return d["t"], d["o"], d["h"], d["l"], d["c"]
    sm = int(datetime.datetime(start_year, 1, 1, tzinfo=datetime.timezone.utc).timestamp()*1000)
    out = {}; cur = sm
    for _ in range(80):
        try:
            r = requests.get("https://api.binance.com/api/v3/klines",
                             params={"symbol": sym, "interval": "1d", "startTime": cur, "limit": 1000}, timeout=20).json()
        except Exception:
            time.sleep(1); continue
        if not isinstance(r, list) or not r: break
        for k in r: out[int(k[0])] = (float(k[1]), float(k[2]), float(k[3]), float(k[4]))
        last = int(r[-1][0])
        if last <= cur or len(r) < 1000: break
        cur = last+86400000; time.sleep(0.05)
    t = np.array(sorted(out))
    o = np.array([out[x][0] for x in t]); h = np.array([out[x][1] for x in t])
    l = np.array([out[x][2] for x in t]); c = np.array([out[x][3] for x in t])
    np.savez(fn, t=t, o=o, h=h, l=l, c=c); return t, o, h, l, c


def sma(c, n):
    s = np.full(len(c), np.nan); cs = np.cumsum(np.insert(c, 0, 0)); s[n-1:] = (cs[n:]-cs[:-n])/n; return s
def ema(c, n):
    a = 2/(n+1); o = np.empty(len(c)); o[0] = c[0]
    for i in range(1, len(c)): o[i] = a*c[i]+(1-a)*o[i-1]
    return o
def atr(h, l, c, n=14):
    tr = np.empty(len(c)); tr[0] = h[0]-l[0]
    for i in range(1, len(c)): tr[i] = max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
    a = np.full(len(c), np.nan)
    if len(c) > n:
        a[n-1] = tr[:n].mean()
        for i in range(n, len(c)): a[i] = (a[i-1]*(n-1)+tr[i])/n
    return a
def rsi(c, n=14):
    d = np.diff(c, prepend=c[0]); up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    ru = np.zeros_like(c); rd = np.zeros_like(c)
    if len(c) > n:
        ru[n] = up[1:n+1].mean(); rd[n] = dn[1:n+1].mean()
        for i in range(n+1, len(c)): ru[i] = (ru[i-1]*(n-1)+up[i])/n; rd[i] = (rd[i-1]*(n-1)+dn[i])/n
    rs = np.divide(ru, rd, out=np.ones_like(c), where=rd != 0); return 100-100/(1+rs)
def rollmax(a, n):
    o = np.full(len(a), np.nan)
    for i in range(n-1, len(a)): o[i] = a[i-n+1:i+1].max()
    return o
def rollmin(a, n):
    o = np.full(len(a), np.nan)
    for i in range(n-1, len(a)): o[i] = a[i-n+1:i+1].min()
    return o
def stats(e):
    e = np.array(e, float)
    if len(e) < 2 or e[-1] <= 0: return -1, -1, 0
    ret = e[-1]/e[0]-1; pk = np.maximum.accumulate(e); mdd = ((e-pk)/pk).min()
    dr = np.diff(e)/e[:-1]; sh = (np.nanmean(dr)/np.nanstd(dr)*math.sqrt(365)) if np.nanstd(dr) > 0 else 0
    return ret, mdd, sh


def run_sig(c, sig):
    cash = CASH0; coins = 0.0; e = np.empty(len(c)); pos = 0
    for i, p in enumerate(c):
        if sig[i] == 1 and pos == 0: coins = cash/p*(1-FEE); cash = 0; pos = 1
        elif sig[i] == 0 and pos == 1: cash = coins*p*(1-FEE); coins = 0; pos = 0
        e[i] = cash+coins*p
    return e


# ---- 전략(→equity) ----
def bh(c): return CASH0*c/c[0]
def sma_cross(c, n): return run_sig(c, (c > sma(c, n)).astype(float))
def v4(c, n=125, buf=0.02):
    s = sma(c, n); sig = np.zeros(len(c)); pos = 0
    for i, p in enumerate(c):
        if not np.isnan(s[i]):
            if pos == 0 and p > s[i]: pos = 1
            elif pos == 1 and p < s[i]*(1-buf): pos = 0
        sig[i] = pos
    return run_sig(c, sig)
def ema_cross(c, f, s): return run_sig(c, (ema(c, f) > ema(c, s)).astype(float))
def macd_s(c):
    m = ema(c, 12)-ema(c, 26); sg = ema(m, 9); return run_sig(c, (m > sg).astype(float))
def tsmom(c, L):
    sig = np.zeros(len(c))
    for i in range(L, len(c)): sig[i] = 1.0 if c[i] > c[i-L] else 0.0
    return run_sig(c, sig)
def donchian(h, l, c, n):
    hh = rollmax(h, n); ll = rollmin(l, n); sig = np.zeros(len(c)); pos = 0
    for i in range(n, len(c)):
        if pos == 0 and c[i] > hh[i-1]: pos = 1
        elif pos == 1 and c[i] < ll[i-1]: pos = 0
        sig[i] = pos
    return run_sig(c, sig)
def supertrend(h, l, c, n=10, mult=3):
    a = atr(h, l, c, n); hl2 = (h+l)/2; up = hl2-mult*a; dn = hl2+mult*a; sig = np.zeros(len(c)); pos = 0
    for i in range(n, len(c)):
        if pos == 0 and c[i] > dn[i-1]: pos = 1
        elif pos == 1 and c[i] < up[i-1]: pos = 0
        sig[i] = pos
    return run_sig(c, sig)
def voltarget(c, target=0.6, lb=20):
    ret = np.diff(c, prepend=c[0])/c; e = np.empty(len(c)); cash = CASH0; coins = 0.0
    for i, p in enumerate(c):
        if i >= lb:
            rv = np.std(ret[i-lb:i])*math.sqrt(365); w = min(1.0, (target/rv) if rv > 0 else 1.0)
        else: w = 0.5
        tot = cash+coins*p; tgt = tot*w
        cur = coins*p
        if abs(tgt-cur) > tot*0.05:
            d = tgt-cur
            if d > 0: amt = min(d, cash); coins += amt/p*(1-FEE); cash -= amt
            else: coins += d/p; cash -= d*(1-FEE)
        e[i] = cash+coins*p
    return e
# 분할매수/회귀
def dip_trend(c, trig, target, frac=0.15, tn=125):
    tr = sma(c, tn); cash = CASH0; coins = 0.0; inv = 0.0; last = None; e = np.empty(len(c))
    for i, p in enumerate(c):
        okt = (not np.isnan(tr[i])) and p > tr[i]
        if coins == 0 and cash > 0 and okt: amt = CASH0*frac; coins += amt/p*(1-FEE); cash -= amt; inv += amt; last = p
        elif coins > 0 and last and p <= last*(1-trig) and okt and cash > 5: amt = min(CASH0*frac, cash); coins += amt/p*(1-FEE); cash -= amt; inv += amt; last = p
        if coins > 0 and p >= (inv/coins)*(1+target): cash += coins*p*(1-FEE); coins = 0; inv = 0; last = None
        e[i] = cash+coins*p
    return e
def rsi_mr(c, buy=30, sell=70, frac=0.15, target=0.05):
    r = rsi(c); cash = CASH0; coins = 0.0; inv = 0.0; e = np.empty(len(c))
    for i, p in enumerate(c):
        if r[i] < buy and cash >= CASH0*frac: amt = CASH0*frac; coins += amt/p*(1-FEE); cash -= amt; inv += amt
        if coins > 0 and (r[i] > sell or p >= (inv/coins)*(1+target)): cash += coins*p*(1-FEE); coins = 0; inv = 0
        e[i] = cash+coins*p
    return e
def rebalance(c, target=0.5, band=0.1):
    coins = CASH0*target/c[0]*(1-FEE); cash = CASH0*(1-target); e = np.empty(len(c))
    for i, p in enumerate(c):
        v = coins*p; tot = cash+v; f = v/tot if tot > 0 else 0
        if f > target+band: sv = (f-target)*tot; coins -= sv/p; cash += sv*(1-FEE)
        elif f < target-band and cash > 0: bv = min((target-f)*tot, cash); coins += bv/p*(1-FEE); cash -= bv
        e[i] = cash+coins*p
    return e
def dca(c, n=50):
    cash = CASH0; coins = 0.0; e = np.empty(len(c)); ev = max(1, len(c)//n); k = 0
    for i, p in enumerate(c):
        if i % ev == 0 and k < n: amt = CASH0/n; coins += amt/p*(1-FEE); cash -= amt; k += 1
        e[i] = cash+coins*p
    return e


COINS = {"BTCUSDT": 2017, "ETHUSDT": 2017, "SOLUSDT": 2020, "XRPUSDT": 2018}
DATA = {s: fetch(s, y) for s, y in COINS.items()}
print("로드:", {s: len(v[4]) for s, v in DATA.items()})


def battery(t, o, h, l, c):
    S = {}
    S["BH"] = bh(c)
    for n in (50, 75, 100, 125, 150, 200): S[f"SMA{n}"] = sma_cross(c, n)
    S["v4(SMA125+2%)"] = v4(c)
    S["v4(SMA150+2%)"] = v4(c, 150)
    for f, s in ((10, 50), (20, 100), (50, 200)): S[f"EMA{f}/{s}"] = ema_cross(c, f, s)
    S["MACD"] = macd_s(c)
    for L in (60, 90, 120, 200): S[f"TSmom{L}"] = tsmom(c, L)
    for n in (20, 55): S[f"Donchian{n}"] = donchian(h, l, c, n)
    S["Supertrend"] = supertrend(h, l, c)
    S["VolTarget"] = voltarget(c)
    S["dip+trend5/5"] = dip_trend(c, 0.05, 0.05); S["dip+trend8/8"] = dip_trend(c, 0.08, 0.08)
    S["RSI회귀"] = rsi_mr(c); S["리밸런싱50"] = rebalance(c, 0.5); S["DCA"] = dca(c)
    return S


print("\n" + "="*100)
print("전략 토너먼트 — 코인별 Sharpe 랭킹 (풀히스토리, 수수료 0.1%). ★=BH 초과 ret")
print("="*100)
overall = {}
for s, (t, o, h, l, c) in DATA.items():
    S = battery(t, o, h, l, c)
    bhr = S["BH"][-1]/CASH0-1
    rows = []
    for name, e in S.items():
        r, m, sh = stats(e); rows.append((name, r, m, sh))
        overall.setdefault(name, []).append(sh)
    rows.sort(key=lambda x: -x[3])
    print(f"\n[{s}]  (BH ret {bhr*100:+.0f}%, Sharpe {[x[3] for x in rows if x[0]=='BH'][0]:.2f})")
    for name, r, m, sh in rows[:10]:
        star = "★" if r > bhr and name != "BH" else " "
        print(f"  {star} {name:<16} Sharpe {sh:5.2f}  ret {r*100:+8.0f}%  MDD {m*100:5.0f}%")

print("\n" + "="*100)
print("전체 종합 — 4코인 평균 Sharpe 랭킹 (어떤 전략이 *전반적으로* 최강인가)")
print("="*100)
agg = sorted(((name, np.mean(shs), len(shs)) for name, shs in overall.items()), key=lambda x: -x[1])
for name, ms, n in agg:
    print(f"  {name:<18} 평균 Sharpe {ms:5.2f}  (코인 {n})")

print("\n판정: 평균 Sharpe 최상위가 추세/모멘텀 계열이면 → 엣지는 추세추종 확정. 분할매수/회귀가 상위면 재검토.")
