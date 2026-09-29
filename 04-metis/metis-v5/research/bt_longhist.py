#!/usr/bin/env python3
"""
운영자 "더 철저히, 아주 상세히, 긴 시점으로" — 분할매수/물타기 vs BH vs v4 풀 히스토리 검증.
Binance 현물 일봉 2017~2026 (BTC/ETH 풀사이클 多: 2018 -84%, 2021불, 2022 -, 2024-25불).
상세: 전체기간 + 연도별 + robustness + 멀티폴드 walk-forward(매년 OOS).
"""
import requests, time, datetime, math, os
import numpy as np

FEE = 0.001
CASH0 = 10000.0
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btcache_long")


def fetch_binance(sym, start_year=2017):
    os.makedirs(CACHE, exist_ok=True)
    fn = f"{CACHE}/{sym}_{start_year}.npz"
    if os.path.exists(fn) and time.time() - os.path.getmtime(fn) < 43200:
        d = np.load(fn); return d["t"], d["c"]
    start_ms = int(datetime.datetime(start_year, 1, 1, tzinfo=datetime.timezone.utc).timestamp() * 1000)
    out = {}; cur = start_ms
    for _ in range(80):
        try:
            r = requests.get("https://api.binance.com/api/v3/klines",
                             params={"symbol": sym, "interval": "1d", "startTime": cur, "limit": 1000}, timeout=20).json()
        except Exception:
            time.sleep(1); continue
        if not isinstance(r, list) or not r:
            break
        for k in r:
            out[int(k[0])] = float(k[4])
        last = int(r[-1][0])
        if last <= cur or len(r) < 1000:
            break
        cur = last + 86400000; time.sleep(0.05)
    t = np.array(sorted(out)); c = np.array([out[x] for x in t])
    np.savez(fn, t=t, c=c); return t, c


def sma(c, n):
    s = np.full(len(c), np.nan)
    cs = np.cumsum(np.insert(c, 0, 0)); s[n-1:] = (cs[n:]-cs[:-n])/n; return s


def rsi(c, n=14):
    d = np.diff(c, prepend=c[0]); up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    ru = np.zeros_like(c); rd = np.zeros_like(c)
    if len(c) > n:
        ru[n] = up[1:n+1].mean(); rd[n] = dn[1:n+1].mean()
        for i in range(n+1, len(c)):
            ru[i] = (ru[i-1]*(n-1)+up[i])/n; rd[i] = (rd[i-1]*(n-1)+dn[i])/n
    rs = np.divide(ru, rd, out=np.ones_like(c), where=rd != 0); return 100-100/(1+rs)


def stats(eqc):
    e = np.array(eqc, float)
    if len(e) < 2 or e[-1] <= 0: return -1, -1, 0
    ret = e[-1]/e[0]-1; peak = np.maximum.accumulate(e); mdd = ((e-peak)/peak).min()
    dr = np.diff(e)/e[:-1]; sh = (np.nanmean(dr)/np.nanstd(dr)*math.sqrt(365)) if np.nanstd(dr) > 0 else 0
    return ret, mdd, sh


def bh(c): return CASH0*c/c[0]


def v4_trend(c, n=125, buf=0.02):
    s = sma(c, n); cash = CASH0; coins = 0.0; eq = np.empty(len(c)); pos = 0
    for i, p in enumerate(c):
        if not np.isnan(s[i]):
            if pos == 0 and p > s[i]: coins = cash/p*(1-FEE); cash = 0; pos = 1
            elif pos == 1 and p < s[i]*(1-buf): cash = coins*p*(1-FEE); coins = 0; pos = 0
        eq[i] = cash+coins*p
    return eq


def dip_trend(c, trig, target, frac=0.15, tn=125):
    tr = sma(c, tn); cash = CASH0; coins = 0.0; inv = 0.0; last = None; eq = np.empty(len(c))
    for i, p in enumerate(c):
        okt = (not np.isnan(tr[i])) and p > tr[i]
        if coins == 0 and cash > 0 and okt:
            amt = CASH0*frac; coins += amt/p*(1-FEE); cash -= amt; inv += amt; last = p
        elif coins > 0 and last and p <= last*(1-trig) and okt and cash > 5:
            amt = min(CASH0*frac, cash); coins += amt/p*(1-FEE); cash -= amt; inv += amt; last = p
        if coins > 0 and p >= (inv/coins)*(1+target):
            cash += coins*p*(1-FEE); coins = 0; inv = 0; last = None
        eq[i] = cash+coins*p
    return eq


def dca(c, n_steps=50):
    cash = CASH0; coins = 0.0; eq = np.empty(len(c)); every = max(1, len(c)//n_steps); k = 0
    for i, p in enumerate(c):
        if i % every == 0 and k < n_steps and cash >= CASH0/n_steps-1e-9:
            amt = CASH0/n_steps; coins += amt/p*(1-FEE); cash -= amt; k += 1
        eq[i] = cash+coins*p
    return eq


def rebalance(c, target=0.5, band=0.1):
    coins = CASH0*target/c[0]*(1-FEE); cash = CASH0*(1-target); eq = np.empty(len(c))
    for i, p in enumerate(c):
        val = coins*p; tot = cash+val; f = val/tot if tot > 0 else 0
        if f > target+band: sv = (f-target)*tot; coins -= sv/p; cash += sv*(1-FEE)
        elif f < target-band and cash > 0: bv = min((target-f)*tot, cash); coins += bv/p*(1-FEE); cash -= bv
        eq[i] = cash+coins*p
    return eq


def year_of(ms): return datetime.datetime.utcfromtimestamp(ms/1000).year


COINS = {"BTCUSDT": 2017, "ETHUSDT": 2017, "SOLUSDT": 2020, "XRPUSDT": 2018}
DATA = {}
for s, y in COINS.items():
    t, c = fetch_binance(s, y)
    if len(c) > 300: DATA[s] = (t, c)
print("로드:", {s: f"{len(v[1])}일 {year_of(v[0][0])}~{year_of(v[0][-1])}" for s, v in DATA.items()})

STRATS = [
    ("BH", lambda c: bh(c)),
    ("v4추세", lambda c: v4_trend(c)),
    ("물타기5/5", lambda c: dip_trend(c, 0.05, 0.05)),
    ("물타기8/8", lambda c: dip_trend(c, 0.08, 0.08)),
    ("DCA", lambda c: dca(c)),
    ("리밸런싱50", lambda c: rebalance(c, 0.5)),
    ("RSI회귀", lambda c: __import__("builtins").__dict__ and rsi_mr(c)),
]


def rsi_mr(c, buy=30, sell=70, frac=0.15, target=0.05):
    r = rsi(c); cash = CASH0; coins = 0.0; inv = 0.0; eq = np.empty(len(c))
    for i, p in enumerate(c):
        if r[i] < buy and cash >= CASH0*frac: amt = CASH0*frac; coins += amt/p*(1-FEE); cash -= amt; inv += amt
        if coins > 0 and (r[i] > sell or p >= (inv/coins)*(1+target)): cash += coins*p*(1-FEE); coins = 0; inv = 0
        eq[i] = cash+coins*p
    return eq


STRATS = [("BH", bh), ("v4추세", v4_trend), ("물타기5/5", lambda c: dip_trend(c, 0.05, 0.05)),
          ("물타기8/8", lambda c: dip_trend(c, 0.08, 0.08)), ("DCA", dca),
          ("리밸런싱50", lambda c: rebalance(c, 0.5)), ("RSI회귀", rsi_mr)]

# ===== 전체기간 =====
print("\n" + "="*96)
print("A) 전체기간 (풀 히스토리, 다중 사이클) — 수수료 0.1% 포함")
print("="*96)
for s, (t, c) in DATA.items():
    print(f"\n[{s}] {year_of(t[0])}~{year_of(t[-1])} ({len(c)}일)")
    bhr = bh(c)[-1]/CASH0-1
    for name, fn in STRATS:
        r, m, sh = stats(fn(c))
        win = "✅" if r > bhr and name != "BH" else "  "
        print(f"  {win} {name:<10} ret {r*100:+8.0f}%  MDD {m*100:5.0f}%  Sharpe {sh:5.2f}")

# ===== 연도별 =====
print("\n" + "="*96)
print("B) 연도별 수익률 (%) — 시장 국면별 행동 (음수해=약세장)")
print("="*96)
for s, (t, c) in DATA.items():
    yrs = sorted(set(year_of(x) for x in t))
    eqs = {name: fn(c) for name, fn in STRATS}
    print(f"\n[{s}]  " + "".join(f"{y:>7}" for y in yrs))
    for name, _ in STRATS:
        e = eqs[name]; row = []
        for y in yrs:
            idx = [i for i in range(len(t)) if year_of(t[i]) == y]
            a, b = idx[0], idx[-1]
            yret = (e[b]/e[a-1]-1) if a > 0 else (e[b]/e[a]-1)
            row.append(yret*100)
        print(f"  {name:<10}" + "".join(f"{v:>+7.0f}" for v in row))

# ===== robustness (풀 히스토리) =====
print("\n" + "="*96)
print("C) robustness — 물타기+추세 16조합 중 BH 이긴 수 (풀 히스토리)")
print("="*96)
for s, (t, c) in DATA.items():
    bhr = bh(c)[-1]/CASH0-1; res = []
    for tg in [0.03, 0.05, 0.08, 0.10]:
        for tp in [0.03, 0.05, 0.08, 0.10]:
            res.append(stats(dip_trend(c, tg, tp)))
    beat = sum(1 for r, m, sh in res if r > bhr)
    print(f"  {s:<8} BH {bhr*100:+6.0f}% | BH이긴 {beat}/16 | Sharpe중앙 {np.median([r[2] for r in res]):.2f} | ret중앙 {np.median([r[0] for r in res])*100:+.0f}% | MDD중앙 {np.median([r[1] for r in res])*100:.0f}%")

# ===== 멀티폴드 walk-forward (매년 OOS) =====
print("\n" + "="*96)
print("D) 멀티폴드 walk-forward — 매 테스트연도 직전까지 학습→그 해 OOS. BH 대비 승/패")
print("="*96)
params = [(tg, tp) for tg in [0.03, 0.05, 0.08, 0.10] for tp in [0.03, 0.05, 0.08, 0.10]]
for s, (t, c) in DATA.items():
    yrs = sorted(set(year_of(x) for x in t))
    wins = 0; tot = 0; detail = []
    for ty in yrs[2:]:
        tr_idx = [i for i in range(len(t)) if year_of(t[i]) < ty]
        te_idx = [i for i in range(len(t)) if year_of(t[i]) == ty]
        if len(tr_idx) < 200 or len(te_idx) < 100: continue
        ctr = c[tr_idx]; cte = c[te_idx]
        best = max(params, key=lambda pr: stats(dip_trend(ctr, pr[0], pr[1]))[2])
        r = stats(dip_trend(cte, best[0], best[1]))[0]
        bhr = cte[-1]/cte[0]-1
        w = r > bhr; wins += w; tot += 1
        detail.append(f"{ty}:{'W' if w else 'L'}({r*100:+.0f}/{bhr*100:+.0f})")
    print(f"  {s:<8} OOS {wins}/{tot} 승 | " + " ".join(detail))

print("\n판정: 풀사이클서 ret로 BH+v4 둘 다 못 넘으면 → 성장 엣지 X 확정. Sharpe/MDD만 우위면 '리스크 감소용'.")
