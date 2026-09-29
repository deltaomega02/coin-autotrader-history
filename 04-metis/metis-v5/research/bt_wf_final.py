#!/usr/bin/env python3
"""마지막: '더 빠른 추세필터가 표본 밖에서도 진짜 나은가' walk-forward.
매 테스트연도 직전까지로 베스트 SMA기간 선택 → 그 해 OOS. 과적합이면 OOS서 무너짐.
+ 고정기간(50/100/125)의 연도별 OOS 안정성도 직접 비교.
"""
import os, math, datetime
import numpy as np
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "bt_tournament.py")).read().split("COINS = {")[0])  # 함수 재사용

import time, requests
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btcache_ohlc")
def fetch2(sym, y):
    d = np.load(f"{CACHE}/{sym}_{y}.npz"); return d["t"], d["c"]
COINS = {"BTCUSDT": 2017, "ETHUSDT": 2017, "SOLUSDT": 2020, "XRPUSDT": 2018}
D = {s: fetch2(s, y) for s, y in COINS.items()}
yof = lambda ms: datetime.datetime.utcfromtimestamp(ms/1000).year
PERIODS = [50, 75, 100, 125, 150, 200]

print("="*96)
print("A) 적응형 — 매년 직전까지 베스트 SMA 선택 → OOS. (과적합이면 무너짐)")
print("="*96)
for s, (t, c) in D.items():
    yrs = sorted(set(yof(x) for x in t)); wins = 0; tot = 0; picks = []; oos_sh = []
    for ty in yrs[2:]:
        tri = [i for i in range(len(t)) if yof(t[i]) < ty]; tei = [i for i in range(len(t)) if yof(t[i]) == ty]
        if len(tri) < 200 or len(tei) < 100: continue
        ctr = c[tri]; cte = c[tei]
        best = max(PERIODS, key=lambda n: stats(sma_cross(ctr, n))[2])
        r, m, sh = stats(sma_cross(cte, best)); bhr = cte[-1]/cte[0]-1
        w = r > bhr; wins += w; tot += 1; picks.append(best); oos_sh.append(sh)
        # noqa
    print(f"  {s:<8} OOS {wins}/{tot} BH초과 | 선택기간 {picks} | OOS Sharpe평균 {np.mean(oos_sh):+.2f}")

print("\n" + "="*96)
print("B) 고정기간 연도별 안정성 — SMA50 vs SMA100 vs SMA125, 매년 BH초과 횟수")
print("="*96)
for s, (t, c) in D.items():
    yrs = sorted(set(yof(x) for x in t))
    line = f"  {s:<8}"
    for n in (50, 100, 125):
        e = sma_cross(c, n); beat = 0; tot = 0
        for ty in yrs[1:]:
            idx = [i for i in range(len(t)) if yof(t[i]) == ty]
            if len(idx) < 100: continue
            a, b = idx[0], idx[-1]
            sret = e[b]/e[a-1]-1 if a > 0 else e[b]/e[a]-1
            bhr = c[b]/c[a-1]-1 if a > 0 else c[b]/c[a]-1
            beat += sret > bhr; tot += 1
        full = stats(e); line += f" | SMA{n}: 연{beat}/{tot}승 Sh{full[2]:.2f}"
    print(line)

print("\n" + "="*96)
print("C) 전체기간 SMA기간별 (과적합 곡선인지 — 완만하면 robust, 뾰족하면 위험)")
print("="*96)
for s, (t, c) in D.items():
    line = f"  {s:<8}"
    for n in PERIODS:
        r, m, sh = stats(sma_cross(c, n)); line += f" SMA{n} Sh{sh:.2f}"
    print(line)

print("\n판정: A에서 적응형이 OOS서도 BH 다수 초과 + 선택기간이 안정적이면 → 빠른추세 진짜.")
print("       C에서 기간별 Sharpe가 완만한 고원이면 robust(과적합X), 한 점만 튀면 위험.")
