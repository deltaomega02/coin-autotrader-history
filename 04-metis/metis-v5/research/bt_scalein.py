#!/usr/bin/env python3
"""
운영자 스케일인 진입 검증: 추세필터(SMA125 위에서만, 깨지면 전량청산, **TP 없음**) 안에서
진입을 일괄 vs 15% 시간분할 vs 15% 하락분할(딥마다, 평단↓). winner는 그대로 끝까지 탐.
질문: 분할진입이 평단을 낮춰 도움? 아니면 현금드래그로 손해? (TP 없으니 예전 물타기와 다름)
"""
import os, math
import numpy as np

OHLC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btcache_ohlc")
FEE = 0.001


def load(s, y): d = np.load(f"{OHLC}/{s}_{y}.npz"); return d["t"], d["c"]
def sma(c, n):
    s = np.full(len(c), np.nan); cs = np.cumsum(np.insert(c, 0, 0)); s[n-1:] = (cs[n:]-cs[:-n])/n; return s
def st(e):
    e = np.array(e, float); pk = np.maximum.accumulate(e); dr = np.diff(e)/e[:-1]
    return e[-1]/e[0]-1, ((e-pk)/pk).min(), (np.nanmean(dr)/np.nanstd(dr)*math.sqrt(365) if np.nanstd(dr) > 0 else 0)


def sim(c, n, method, trig=0.05, frac=0.15):
    """method: lump / scale_time / scale_dip. 추세 위=진입가능, 종가<SMA*0.98=전량청산. TP없음."""
    s = sma(c, n)
    above = c > s
    below = c < s*(1-0.02)
    cash = 1.0; coins = 0.0; invested_cap = 0.0; last_buy = None
    eq = np.empty(len(c))
    in_regime = False
    for i in range(1, len(c)):
        # 신호는 전일(i-1) 기준 = lookahead 제거
        ab = above[i-1] if not np.isnan(s[i-1]) else False
        bl = below[i-1] if not np.isnan(s[i-1]) else False
        price = c[i]
        # 청산
        if (coins > 0) and bl:
            cash += coins*price*(1-FEE); coins = 0; invested_cap = 0; last_buy = None; in_regime = False
        # 진입 (추세 위)
        if ab:
            tot = cash + coins*price
            if not in_regime:
                in_regime = True; last_buy = None
            if method == "lump":
                if coins == 0 and cash > 1e-9:
                    amt = cash; coins += amt/price*(1-FEE); cash -= amt; last_buy = price
            elif method == "scale_time":
                if invested_cap < 1-1e-9 and cash > 1e-9:
                    amt = min(frac*tot, cash); coins += amt/price*(1-FEE); cash -= amt; invested_cap += frac
            elif method == "scale_dip":
                buy = False
                if coins == 0:
                    buy = True
                elif last_buy and price <= last_buy*(1-trig) and cash > 0.01*tot:
                    buy = True
                if buy and cash > 1e-9:
                    amt = min(frac*tot, cash); coins += amt/price*(1-FEE); cash -= amt; last_buy = price
        # 추세 유지되는 동안 평가
        eq[i] = cash + coins*price
    eq[0] = 1.0
    return eq


for sym, y in [("BTCUSDT", 2017), ("ETHUSDT", 2017), ("SOLUSDT", 2020)]:
    t, c = load(sym, y)
    bh = c/c[0]
    print(f"\n[{sym}]  BH ret {(bh[-1]-1)*100:+.0f}%")
    for method, lbl in [("lump", "일괄매수(현 v4)"), ("scale_time", "시간분할 15%/일"),
                        ("scale_dip", "하락분할 15%(딥5%)"),]:
        e = sim(c, 125, method)
        r, m, sh = st(e)
        print(f"  {lbl:<18} ret {r*100:+8.0f}%  MDD {m*100:5.0f}%  Sharpe {sh:.2f}")
    # 하락분할 트리거 변형
    for trig in (0.03, 0.08):
        e = sim(c, 125, "scale_dip", trig=trig)
        r, m, sh = st(e)
        print(f"  하락분할 15%(딥{int(trig*100)}%)  ret {r*100:+8.0f}%  MDD {m*100:5.0f}%  Sharpe {sh:.2f}")

print("\n판정: 분할진입이 일괄과 비슷하거나 MDD↓면 운영자 직관 맞음(채택가치). 일괄이 확실히 높으면 현금드래그가 큼.")
