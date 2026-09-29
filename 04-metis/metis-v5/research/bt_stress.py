#!/usr/bin/env python3
"""GPT 1순위: tail stress(carry에 거래소파산급 충격) + funding robustness.
"평소 -2%는 가짜" 검증 — carry sleeve에 FTX형 충격 넣고 결합 MDD 재계산."""
import requests, time, datetime, math, os
import numpy as np

OHLC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btcache_ohlc")
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btcache_fund")
FEE_LEG = 0.0006; SLIP = 0.0005; SPOT_FEE = 0.001


def load_spot(sym, y):
    d = np.load(f"{OHLC}/{sym}_{y}.npz"); return d["t"], d["c"]
def sma(c, n):
    s = np.full(len(c), np.nan); cs = np.cumsum(np.insert(c, 0, 0)); s[n-1:] = (cs[n:]-cs[:-n])/n; return s
def mdd(e):
    e = np.array(e, float); pk = np.maximum.accumulate(e); return ((e-pk)/pk).min()
def sharpe(e):
    e = np.array(e, float); dr = np.diff(e)/e[:-1]; return np.nanmean(dr)/np.nanstd(dr)*math.sqrt(365) if np.nanstd(dr) > 0 else 0
def cached(kind, sym):
    d = np.load(f"{CACHE}/{kind}_{sym}.npz"); return d["k"], d["v"]


def carry_sleeve(sym, thr=0.0006, win=3):
    ft, fv = cached("fund", sym); pt, pv = cached("perp", sym)
    ys = 2017 if sym in ("BTCUSDT", "ETHUSDT") else 2020
    st, sv = load_spot(sym, ys)
    df = {}
    for i in range(len(ft)):
        d = int(ft[i])-(int(ft[i]) % 86400000); df[d] = df.get(d, 0)+fv[i]
    perp = {int(pt[i]): pv[i] for i in range(len(pt))}; spot = {int(st[i]): sv[i] for i in range(len(st))}
    days = sorted(set(df) & set(perp) & set(spot)); frl = [df[d] for d in days]
    eq = 1.0; e = {}; inpos = False
    for i in range(win, len(days)):
        d = days[i]; trail = np.mean(frl[i-win:i])
        if not inpos and trail > thr: eq *= (1-2*(FEE_LEG+SLIP)); inpos = True
        elif inpos and trail <= 0: eq *= (1-2*(FEE_LEG+SLIP)); inpos = False
        if inpos:
            daily = frl[i] - (perp[d]/perp[days[i-1]]-1 - (spot[d]/spot[days[i-1]]-1))
            eq *= (1+daily)
        e[d] = eq
    return e


def trend_sleeve(sym, n=125):
    ys = 2017 if sym in ("BTCUSDT", "ETHUSDT") else 2020
    t, c = load_spot(sym, ys); s = sma(c, n); sig = np.zeros(len(c)); sig[1:] = (c > s).astype(float)[:-1]
    eq = 1.0; e = {}
    for i in range(1, len(c)):
        if sig[i] == 1: eq *= (c[i]/c[i-1])
        if sig[i] != sig[i-1]: eq *= (1-SPOT_FEE)
        e[int(t[i])] = eq
    return e


# 두 sleeve (BTC+ETH 평균) — 기본 파라미터
def build(thr=0.0006, win=3):
    carry = {}; trend = {}
    for sym in ("BTCUSDT", "ETHUSDT"):
        for d, v in carry_sleeve(sym, thr, win).items(): carry.setdefault(d, []).append(v)
        for d, v in trend_sleeve(sym).items(): trend.setdefault(d, []).append(v)
    common = sorted(set(carry) & set(trend))
    ce = np.array([np.mean(carry[d]) for d in common]); ce /= ce[0]
    te = np.array([np.mean(trend[d]) for d in common]); te /= te[0]
    return common, te, ce


common, te, ce = build()
# 일수익
def port_series(te, ce, wt, reb=30, shock=None):
    """wt=추세비중. shock=(idx, frac) carry에 일회성 충격."""
    ut = wt; uc = 1-wt; last = 0; out = []
    for i in range(len(common)):
        if i > 0:
            ut *= te[i]/te[i-1]
            cret = ce[i]/ce[i-1]-1
            if shock and i == shock[0]: cret += shock[1]   # 충격일
            uc *= (1+cret)
        tot = ut+uc
        if i-last >= reb: ut = tot*wt; uc = tot*(1-wt); last = i
        out.append(tot)
    return np.array(out)


# FTX 시점 인덱스 (2022-11-08 근처)
ftx = next((i for i, d in enumerate(common) if abs(d-int(datetime.datetime(2022,11,9,tzinfo=datetime.timezone.utc).timestamp()*1000)) < 86400000*2), len(common)//2)
worst_i = int(np.argmin(np.diff(ce)))  # carry 최악일

print(f"공통구간 {len(common)}일. FTX idx={ftx}\n")
print("="*88)
print("Tail stress — carry sleeve에 일회성 충격(거래소파산/디페그/ADL 가정), 결합 MDD 재계산")
print("="*88)
print(f"{'믹스':<16}{'정상 MDD':>10}{'carry-20%':>12}{'carry-50%':>12}{'carry-100%':>12}")
for wt, lbl in [(0.7,"추세70/carry30"),(0.5,"추세50/carry50"),(0.3,"추세30/carry70")]:
    base = mdd(port_series(te, ce, wt))
    s20 = mdd(port_series(te, ce, wt, shock=(ftx,-0.20)))
    s50 = mdd(port_series(te, ce, wt, shock=(ftx,-0.50)))
    s100 = mdd(port_series(te, ce, wt, shock=(ftx,-1.00)))
    print(f"  {lbl:<14}{base*100:>9.0f}%{s20*100:>11.0f}%{s50*100:>11.0f}%{s100*100:>11.0f}%")

print("\n" + "="*88)
print("Funding carry robustness — threshold × 평균기간 (과최적화 점검). carry 단독 연수익/Sharpe")
print("="*88)
print(f"{'thr/win':<12}" + "".join(f"win{w:>8}" for w in (1,3,7,14)))
for thr in (0.0003, 0.0006, 0.0010, 0.0015):
    row = f"  {thr*100:.2f}%/일  "
    for win in (1,3,7,14):
        _, _, ce2 = build(thr, win)
        cg = (ce2[-1])**(365/len(ce2))-1; sh = sharpe(ce2)
        row += f" {cg*100:+5.0f}%/{sh:.1f}"
    print(row)

print("\n판정: tail -100%(거래소 전손)에도 결합 MDD가 운영자 감내 범위면 carry 비중 OK. funding robustness가 thr/win 전반 양호하면 과최적화 아님.")
