#!/usr/bin/env python3
"""
운영자: "15%씩 조금씩(분할/물타기)을 선물로, 숏까지" 전수.
선물 시뮬 — 롱/숏 물타기 + 레버리지 1/2/3x + 청산(liquidation) + 펀딩비 + 수수료.
each tranche=자본 15% 마진, 레버리지배 노티셔널. 역방향 trig%마다 추가. 평단±target% 익절.
청산: 포지션 자본(마진+미실현)≤0 → 전손. funding 0.01%/일 드래그. fee 0.06%/체결.
4코인 풀히스토리. vs BH. (선물=숏·레버 가능, 근데 청산/펀딩 현실)
"""
import os, math
import numpy as np

CASH0 = 10000.0; FEE = 0.0006; FUND = 0.0001
OHLC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btcache_ohlc")
COINS = {"BTCUSDT": 2017, "ETHUSDT": 2017, "SOLUSDT": 2020, "XRPUSDT": 2018}


def load(sym, y):
    d = np.load(f"{OHLC}/{sym}_{y}.npz"); return d["c"]
def sma(c, n):
    s = np.full(len(c), np.nan); cs = np.cumsum(np.insert(c, 0, 0)); s[n-1:] = (cs[n:]-cs[:-n])/n; return s
def stats(e):
    e = np.array(e, float)
    if len(e) < 2 or e[-1] <= 1e-6: return -1, -1, 0
    ret = e[-1]/e[0]-1; pk = np.maximum.accumulate(e); mdd = ((e-pk)/pk).min()
    dr = np.diff(e)/e[:-1]; sh = (np.nanmean(dr)/np.nanstd(dr)*math.sqrt(365)) if np.nanstd(dr) > 0 else 0
    return ret, mdd, sh


def fut_scale(c, direction, trig, target, lev, frac=0.15, trend_n=None):
    free = CASH0; units = 0.0; margin = 0.0; avg = None; last = None
    e = np.empty(len(c)); liq = 0
    tr = sma(c, trend_n) if trend_n else None
    for i, p in enumerate(c):
        if units > 0:
            free -= FUND*units*p                       # 펀딩 드래그
            upnl = direction*(p-avg)*units
            if margin + upnl <= 0:                      # 청산
                units = 0; margin = 0; avg = None; last = None; liq += 1
        okt = True
        if tr is not None and not np.isnan(tr[i]):
            okt = (p > tr[i]) if direction > 0 else (p < tr[i])
        elif tr is not None:
            okt = False
        add = False
        if units == 0 and free > 5 and okt:
            add = True
        elif units > 0 and last and okt:
            adverse = (p <= last*(1-trig)) if direction > 0 else (p >= last*(1+trig))
            if adverse and free >= frac*CASH0:
                add = True
        if add:
            m = min(frac*CASH0, free)
            if m > 5:
                notion = m*lev; u = notion/p
                avg = p if avg is None else (avg*units + p*u)/(units+u)
                units += u; margin += m; free -= m + notion*FEE; last = p
        if units > 0 and avg:
            tp = (p >= avg*(1+target)) if direction > 0 else (p <= avg*(1-target))
            if tp:
                upnl = direction*(p-avg)*units
                free += margin + upnl - units*p*FEE
                units = 0; margin = 0; avg = None; last = None
        upnl = direction*(p-avg)*units if (units > 0 and avg) else 0
        e[i] = max(free + margin + upnl, 0)
    return e, liq


D = {s: load(s, y) for s, y in COINS.items()}
print("="*98)
print("선물 분할매수(물타기) — 롱/숏 × 레버리지. trig8%/target8%. 청산·펀딩·수수료 반영. vs BH")
print("="*98)
for s, c in D.items():
    bhr = (c[-1]/c[0]-1)*100
    print(f"\n[{s}]  BH ret {bhr:+.0f}%")
    for direction, dl in [(1, "롱물타기"), (-1, "숏물타기")]:
        for lev in (1, 2, 3):
            e, liq = fut_scale(c, direction, 0.08, 0.08, lev)
            r, m, sh = stats(e)
            lqs = f" 청산{liq}회" if liq else ""
            print(f"  {dl} {lev}x      ret {r*100:+8.0f}%  MDD {m*100:5.0f}%  Sharpe {sh:5.2f}{lqs}")
    # 추세필터 버전 (롱은 추세위, 숏은 추세아래)
    for direction, dl in [(1, "롱물타기+추세"), (-1, "숏물타기+추세")]:
        e, liq = fut_scale(c, direction, 0.08, 0.08, 2, trend_n=125)
        r, m, sh = stats(e)
        lqs = f" 청산{liq}회" if liq else ""
        print(f"  {dl} 2x  ret {r*100:+8.0f}%  MDD {m*100:5.0f}%  Sharpe {sh:5.2f}{lqs}")

print("\n판정: 레버리지 올릴수록 청산으로 전손나면 → 선물물타기 = 파산구조. 1x도 BH 못넘으면 엣지 X.")
print("      숏물타기가 +면 약세장 가치 있으나, 불장 청산 빈도 보면 사이클 생존 여부 판단.")
