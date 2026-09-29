#!/usr/bin/env python3
"""레버리지: 방향성(추세) vs 마켓중립(carry)에 거는 차이. 1/2/3x, 청산 모델.
추세 레버=조정에 청산(위험). carry 레버=델타중립이라 가격청산 거의X, 펀딩 증폭(합리). basis spike만 위험."""
import math, os
import numpy as np

OHLC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btcache_ohlc")
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btcache_fund")
FEE_LEG = 0.0006; SLIP = 0.0005; SPOT_FEE = 0.001


def load_spot(s, y): d = np.load(f"{OHLC}/{s}_{y}.npz"); return d["t"], d["c"]
def cached(k, s): d = np.load(f"{CACHE}/{k}_{s}.npz"); return d["k"], d["v"]
def sma(c, n):
    s = np.full(len(c), np.nan); cs = np.cumsum(np.insert(c, 0, 0)); s[n-1:] = (cs[n:]-cs[:-n])/n; return s
def metr(e):
    e = np.array(e, float); pk = np.maximum.accumulate(e); dr = np.diff(e)/e[:-1]
    cg = (e[-1]/e[0])**(365/len(e))-1 if e[-1] > 0 else -1
    return cg, ((e-pk)/pk).min(), (np.nanmean(dr)/np.nanstd(dr)*math.sqrt(365) if np.nanstd(dr) > 0 else 0)


def carry_daily(sym):
    ft, fv = cached("fund", sym); pt, pv = cached("perp", sym)
    ys = 2017 if sym in ("BTCUSDT", "ETHUSDT") else 2020
    s_t, s_v = load_spot(sym, ys)
    df = {}
    for i in range(len(ft)):
        d = int(ft[i])-(int(ft[i]) % 86400000); df[d] = df.get(d, 0)+fv[i]
    perp = {int(pt[i]): pv[i] for i in range(len(pt))}; spot = {int(s_t[i]): s_v[i] for i in range(len(s_t))}
    days = sorted(set(df) & set(perp) & set(spot)); frl = [df[d] for d in days]
    out = {}; inp = False
    for i in range(3, len(days)):
        d = days[i]; tr = np.mean(frl[i-3:i]); r = 0.0
        if not inp and tr > 0.0006: r -= 2*(FEE_LEG+SLIP); inp = True
        elif inp and tr <= 0: r -= 2*(FEE_LEG+SLIP); inp = False
        if inp: r += frl[i]-(perp[d]/perp[days[i-1]]-1-(spot[d]/spot[days[i-1]]-1))
        out[d] = r
    return out


def trend_daily(sym):
    ys = 2017 if sym in ("BTCUSDT", "ETHUSDT") else 2020
    t, c = load_spot(sym, ys); s = sma(c, 125); sig = np.zeros(len(c)); sig[1:] = (c > s).astype(float)[:-1]
    out = {}
    for i in range(1, len(c)):
        r = (c[i]/c[i-1]-1) if sig[i] == 1 else 0.0
        if sig[i] != sig[i-1]: r -= SPOT_FEE
        out[int(t[i])] = r
    return out


def lever(daily_map, lev, liq_buffer=0.95):
    """일별수익 × lev. 누적 마진 소진(자본≤0) 시 청산(전손)."""
    days = sorted(daily_map); eq = 1.0; e = []; liq = 0; worst = 0
    for d in days:
        r = daily_map[d]; worst = min(worst, r)
        eq *= (1 + lev*r)
        if eq <= (1-liq_buffer):   # 마진 소진 근사
            eq = 1e-9; liq += 1
        e.append(eq)
    return e, liq, worst


# BTC+ETH 평균 일수익
def avg_daily(fn):
    m = {}
    for sym in ("BTCUSDT", "ETHUSDT"):
        for d, r in fn(sym).items(): m.setdefault(d, []).append(r)
    return {d: np.mean(v) for d, v in m.items()}


tr = avg_daily(trend_daily); ca = avg_daily(carry_daily)

print("="*80)
print("방향성(추세 롱) 레버리지 — 조정에 청산 위험")
print("="*80)
for lev in (1, 2, 3):
    e, liq, w = lever(tr, lev); cg, m, sh = metr(e)
    print(f"  추세 {lev}x   연 {cg*100:+6.0f}%  MDD {m*100:6.0f}%  Sharpe {sh:.2f}  최악일 {w*100:.0f}%  청산 {liq}회")

print("\n" + "="*80)
print("마켓중립(carry) 레버리지 — 델타중립이라 가격청산 거의X, 펀딩 증폭")
print("="*80)
for lev in (1, 2, 3, 5):
    e, liq, w = lever(ca, lev); cg, m, sh = metr(e)
    print(f"  carry {lev}x  연 {cg*100:+6.0f}%  MDD {m*100:6.0f}%  Sharpe {sh:.2f}  최악일 {w*100:.2f}%  청산 {liq}회")

print("\n참고: carry 최악일이 작으면(±몇%) 레버 줘도 청산 안 남=펀딩 증폭 가능. 추세는 최악일 크면 레버 시 청산.")
print("주의: carry 레버는 basis spike·거래소 tail도 같이 증폭. cross-margin(spot+perp 한계좌) 가정.")
