#!/usr/bin/env python3
"""비중 메뉴 — 추세/carry 80/20~30/70. 정상 + 거래소전손 tail MDD + 절대 income. 운영자가 고르게."""
import math, os, datetime
import numpy as np

OHLC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btcache_ohlc")
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btcache_fund")
FEE_LEG = 0.0006; SLIP = 0.0005; SPOT_FEE = 0.001


def load_spot(s, y): d = np.load(f"{OHLC}/{s}_{y}.npz"); return d["t"], d["c"]
def cached(k, s): d = np.load(f"{CACHE}/{k}_{s}.npz"); return d["k"], d["v"]
def sma(c, n):
    s = np.full(len(c), np.nan); cs = np.cumsum(np.insert(c, 0, 0)); s[n-1:] = (cs[n:]-cs[:-n])/n; return s
def stt(e):
    e = np.array(e, float); pk = np.maximum.accumulate(e); dr = np.diff(e)/e[:-1]
    return e[-1]/e[0]-1, ((e-pk)/pk).min(), (np.nanmean(dr)/np.nanstd(dr)*math.sqrt(365) if np.nanstd(dr) > 0 else 0)


def carry_sleeve(sym):
    ft, fv = cached("fund", sym); pt, pv = cached("perp", sym)
    ys = 2017 if sym in ("BTCUSDT", "ETHUSDT") else 2020
    s_t, s_v = load_spot(sym, ys)
    df = {}
    for i in range(len(ft)):
        d = int(ft[i])-(int(ft[i]) % 86400000); df[d] = df.get(d, 0)+fv[i]
    perp = {int(pt[i]): pv[i] for i in range(len(pt))}; spot = {int(s_t[i]): s_v[i] for i in range(len(s_t))}
    days = sorted(set(df) & set(perp) & set(spot)); frl = [df[d] for d in days]
    v = 1.0; e = {}; inp = False
    for i in range(3, len(days)):
        d = days[i]; tr = np.mean(frl[i-3:i])
        if not inp and tr > 0.0006: v *= (1-2*(FEE_LEG+SLIP)); inp = True
        elif inp and tr <= 0: v *= (1-2*(FEE_LEG+SLIP)); inp = False
        if inp: v *= (1+frl[i]-(perp[d]/perp[days[i-1]]-1-(spot[d]/spot[days[i-1]]-1)))
        e[d] = v
    return e


def trend_sleeve(sym):
    ys = 2017 if sym in ("BTCUSDT", "ETHUSDT") else 2020
    t, c = load_spot(sym, ys); s = sma(c, 125); sig = np.zeros(len(c)); sig[1:] = (c > s).astype(float)[:-1]
    v = 1.0; e = {}
    for i in range(1, len(c)):
        if sig[i] == 1: v *= c[i]/c[i-1]
        if sig[i] != sig[i-1]: v *= (1-SPOT_FEE)
        e[int(t[i])] = v
    return e


carry = {}; trend = {}
for sym in ("BTCUSDT", "ETHUSDT"):
    for d, v in carry_sleeve(sym).items(): carry.setdefault(d, []).append(v)
    for d, v in trend_sleeve(sym).items(): trend.setdefault(d, []).append(v)
common = sorted(set(carry) & set(trend))
te = np.array([np.mean(trend[d]) for d in common]); te /= te[0]
ce = np.array([np.mean(carry[d]) for d in common]); ce /= ce[0]
ftx = next((i for i, d in enumerate(common) if abs(d-int(datetime.datetime(2022, 11, 9, tzinfo=datetime.timezone.utc).timestamp()*1000)) < 2*86400000), len(common)//2)


def port(wt, shock=None):
    ut = wt; uc = 1-wt; last = 0; out = []
    for i in range(len(common)):
        if i > 0:
            ut *= te[i]/te[i-1]; cr = ce[i]/ce[i-1]-1
            if shock and i == shock[0]: cr += shock[1]
            uc *= (1+cr)
        tot = ut+uc
        if i-last >= 30: ut = tot*wt; uc = tot*(1-wt); last = i
        out.append(tot)
    return np.array(out)


print(f"공통 {len(common)}일. 두 sleeve 상관 {np.corrcoef(np.diff(te)/te[:-1], np.diff(ce)/ce[:-1])[0,1]:+.2f}\n")
print(f"{'추세/carry':<12}{'총수익':>9}{'정상MDD':>8}{'Sharpe':>8}{'거래소전손MDD':>13}{'carry income/년($1k)':>20}")
for wt in (0.8, 0.7, 0.6, 0.5, 0.4, 0.3):
    r, m, sh = stt(port(wt))
    _, mt, _ = stt(port(wt, shock=(ftx, -1.0)))
    inc = (1-wt)*1000*0.10
    print(f"  {int(wt*100)}/{int((1-wt)*100):<7}{r*100:>+8.0f}%{m*100:>7.0f}%{sh:>8.2f}{mt*100:>12.0f}%{inc:>16.0f}/년")
print("\n참고: 정상MDD는 carry 많을수록↓, 근데 거래소전손 시엔 carry 많을수록↑(반대). Sharpe는 carry 많을수록↑(수익은↓).")
