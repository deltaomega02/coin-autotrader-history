#!/usr/bin/env python3
"""
운영자 검증: (1) 숏/롱숏까지 전부 (2) 불장 편향인가 — per-regime 분리.
숏추세/롱숏추세/크로스섹션 롱숏(마켓중립) + 연도별 불장 vs 약세장 분리.
캐시 재사용. 숏=perp 가정 + 보유비용(funding) 일 0.01%. 수수료 0.1%.
"""
import os, math, datetime
import numpy as np

FEE = 0.001; CASH0 = 10000.0; SHORT_CARRY = 0.0001
OHLC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btcache_ohlc")
UNI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btcache_uni")


def load_ohlc(sym, y):
    d = np.load(f"{OHLC}/{sym}_{y}.npz"); return d["t"], d["c"]
def sma(c, n):
    s = np.full(len(c), np.nan); cs = np.cumsum(np.insert(c, 0, 0)); s[n-1:] = (cs[n:]-cs[:-n])/n; return s
def stats(e):
    e = np.array(e, float)
    if len(e) < 2 or e[-1] <= 0: return -1, -1, 0
    ret = e[-1]/e[0]-1; pk = np.maximum.accumulate(e); mdd = ((e-pk)/pk).min()
    dr = np.diff(e)/e[:-1]; sh = (np.nanmean(dr)/np.nanstd(dr)*math.sqrt(365)) if np.nanstd(dr) > 0 else 0
    return ret, mdd, sh
def yof(ms): return datetime.datetime.utcfromtimestamp(ms/1000).year


def run_dir(c, sig):
    """sig in {-1,0,1}. 방향 노출 1x. 숏 보유비용 포함."""
    eq = CASH0; d = 0; e = np.empty(len(c))
    for i, p in enumerate(c):
        if i > 0 and d != 0:
            eq *= (1 + (c[i]/c[i-1]-1)*d)
            if d < 0: eq *= (1-SHORT_CARRY)
        if sig[i] != d:
            eq *= (1-FEE); d = sig[i]
        e[i] = eq
    return e


COINS = {"BTCUSDT": 2017, "ETHUSDT": 2017, "SOLUSDT": 2020, "XRPUSDT": 2018}
D = {s: load_ohlc(s, y) for s, y in COINS.items()}

print("="*94)
print("1) 숏/롱숏 추세 (SMA125) vs 롱onlly vs BH — 전체기간")
print("="*94)
for s, (t, c) in D.items():
    sm = sma(c, 125)
    long_sig = np.where(c > sm, 1, 0); long_sig[np.isnan(sm)] = 0
    short_sig = np.where(c < sm, -1, 0); short_sig[np.isnan(sm)] = 0
    ls_sig = np.where(c > sm, 1, -1); ls_sig[np.isnan(sm)] = 0
    print(f"\n[{s}]")
    for name, e in [("BH", CASH0*c/c[0]), ("롱only", run_dir(c, long_sig)),
                    ("숏only", run_dir(c, short_sig)), ("롱숏", run_dir(c, ls_sig))]:
        r, m, sh = stats(e)
        print(f"  {name:<8} ret {r*100:+8.0f}%  MDD {m*100:5.0f}%  Sharpe {sh:5.2f}")

print("\n" + "="*94)
print("2) per-regime — 불장 해 vs 약세장 해 분리 (BTC 연수익 기준 분류)")
print("="*94)
# BTC 연도별로 불/약세 분류
tb, cb = D["BTCUSDT"]
yrs = sorted(set(yof(x) for x in tb))
btc_yr = {}
for y in yrs:
    idx = [i for i in range(len(tb)) if yof(tb[i]) == y]
    btc_yr[y] = cb[idx[-1]]/cb[idx[0]]-1
bull_yrs = [y for y in yrs if btc_yr[y] > 0]; bear_yrs = [y for y in yrs if btc_yr[y] <= 0]
print(f"불장 해: {bull_yrs}")
print(f"약세 해: {bear_yrs}")
print(f"\n{'코인/전략':<22}{'불장 누적':>12}{'약세 누적':>12}  해석")
for s, (t, c) in D.items():
    sm = sma(c, 125)
    strats = {"BH": CASH0*c/c[0], "롱only": run_dir(c, np.where(c > sm, 1, 0)),
              "숏only": run_dir(c, np.where(c < sm, -1, 0)), "롱숏": run_dir(c, np.where((c > sm), 1, -1))}
    for name, e in strats.items():
        bull_mult = 1.0; bear_mult = 1.0
        for y in yrs:
            idx = [i for i in range(len(t)) if yof(t[i]) == y]
            if len(idx) < 30: continue
            a, b = idx[0], idx[-1]
            yr = e[b]/e[a-1] if a > 0 else e[b]/e[a]
            if y in bull_yrs: bull_mult *= yr
            else: bear_mult *= yr
        tag = ""
        if name == "숏only": tag = "← 약세서 +면 숏 가치"
        print(f"  {s[:3]}/{name:<14}{(bull_mult-1)*100:>+11.0f}%{(bear_mult-1)*100:>+11.0f}%  {tag}")
    print()

print("="*94)
print("3) 크로스섹션 롱숏 (마켓중립) — 강한코인 롱 + 약한코인 숏. 28코인 유니버스")
print("="*94)
import glob
files = glob.glob(f"{UNI}/*.npz")
raw = {}
for f in files:
    s = os.path.basename(f)[:-4]; d = np.load(f)
    if len(d["c"]) >= 600: raw[s] = (d["t"], d["c"])
syms = list(raw.keys())
days = sorted(set().union(*[set(raw[s][0]) for s in syms]))
di = {d: i for i, d in enumerate(days)}; N = len(days); Msy = len(syms)
P = np.full((Msy, N), np.nan)
for j, s in enumerate(syms):
    t, c = raw[s]
    for k in range(len(t)): P[j, di[t[k]]] = c[k]


def cs_longshort(lb=30, k=3, reb=7, market_neutral=True):
    eqv = CASH0; e = []; start = lb+1
    longs = []; shorts = []
    for i in range(start, N):
        if (i-start) % reb == 0:
            mom = np.full(Msy, np.nan)
            for j in range(Msy):
                if not np.isnan(P[j, i]) and not np.isnan(P[j, i-lb]) and P[j, i-lb] > 0:
                    mom[j] = P[j, i]/P[j, i-lb]-1
            valid = [j for j in range(Msy) if not np.isnan(mom[j])]
            order = sorted(valid, key=lambda j: -mom[j])
            longs = order[:k]; shorts = order[-k:] if market_neutral else []
            eqv *= (1-FEE*2)  # 회전 수수료 근사
        # 일 수익: 롱 평균 - 숏 평균
        if i > start and longs:
            lr = np.nanmean([P[j, i]/P[j, i-1]-1 for j in longs if not np.isnan(P[j, i]) and not np.isnan(P[j, i-1])])
            sr = np.nanmean([P[j, i]/P[j, i-1]-1 for j in shorts if not np.isnan(P[j, i]) and not np.isnan(P[j, i-1])]) if shorts else 0
            lr = 0 if np.isnan(lr) else lr; sr = 0 if np.isnan(sr) else sr
            if market_neutral:
                eqv *= (1 + 0.5*lr - 0.5*sr - SHORT_CARRY*0.5)
            else:
                eqv *= (1 + lr)
        e.append(eqv)
    return e


for mn, lbl in [(True, "롱숏 마켓중립"), (False, "롱only(top3)")]:
    for lb in (30, 60):
        e = cs_longshort(lb, 3, 7, mn); r, m, sh = stats(e)
        print(f"  {lbl:<14} lb{lb} ret {r*100:+8.0f}% MDD {m*100:5.0f}% Sharpe {sh:.2f}")

print("\n판정: 숏only가 약세장서도 마이너스면 → 숏 가치 X(드리프트). 롱숏 마켓중립이 BH 못넘고 변동만 크면 → 숏 추가 의미 X.")
print("      불장 누적 >> 약세 누적이면 → 수익은 본질적으로 불장 의존(롱추세=불장캡처+약세현금).")
