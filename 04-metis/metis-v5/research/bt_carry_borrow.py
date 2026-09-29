#!/usr/bin/env python3
"""GPT 1순위: 레버 carry에 차입비용(borrow cost) 반영 = 진짜 엣지냐 착시냐.
levered daily = L×(unlev carry daily) - (L-1)×borrow_daily (보유일만). borrow APR 민감도."""
import math, os
import numpy as np

OHLC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btcache_ohlc")
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btcache_fund")
FEE_LEG = 0.0006; SLIP = 0.0005


def load_spot(s, y): d = np.load(f"{OHLC}/{s}_{y}.npz"); return d["t"], d["c"]
def cached(k, s): d = np.load(f"{CACHE}/{k}_{s}.npz"); return d["k"], d["v"]
def metr(e):
    e = np.array(e, float); pk = np.maximum.accumulate(e); dr = np.diff(e)/e[:-1]
    cg = (e[-1]/e[0])**(365/len(e))-1 if e[-1] > 0 else -1
    return cg, ((e-pk)/pk).min()


def carry_daily(sym):
    """(날짜, unlev 일수익, 보유여부)"""
    ft, fv = cached("fund", sym); pt, pv = cached("perp", sym)
    ys = 2017 if sym in ("BTCUSDT", "ETHUSDT") else 2020
    s_t, s_v = load_spot(sym, ys)
    df = {}
    for i in range(len(ft)):
        d = int(ft[i])-(int(ft[i]) % 86400000); df[d] = df.get(d, 0)+fv[i]
    perp = {int(pt[i]): pv[i] for i in range(len(pt))}; spot = {int(s_t[i]): s_v[i] for i in range(len(s_t))}
    days = sorted(set(df) & set(perp) & set(spot)); frl = [df[d] for d in days]
    out = []; inp = False
    for i in range(3, len(days)):
        d = days[i]; tr = np.mean(frl[i-3:i]); r = 0.0; fee = 0.0
        if not inp and tr > 0.0006: fee = 2*(FEE_LEG+SLIP); inp = True
        elif inp and tr <= 0: fee = 2*(FEE_LEG+SLIP); inp = False
        held = inp
        if inp: r = frl[i]-(perp[d]/perp[days[i-1]]-1-(spot[d]/spot[days[i-1]]-1))
        out.append((d, r-fee, held))
    return out


# BTC+ETH 평균
m = {}
for sym in ("BTCUSDT", "ETHUSDT"):
    for d, r, h in carry_daily(sym): m.setdefault(d, []).append((r, h))
days = sorted(m)
unlev = np.array([np.mean([x[0] for x in m[d]]) for d in days])
held = np.array([np.mean([x[1] for x in m[d]]) for d in days])  # 보유 비율(0~1)

print("레버 carry 차입비용(borrow APR) 반영 — net 연수익 (BTC/ETH 평균)")
print("="*72)
print(f"{'레버':<6}" + "".join(f"borrow {b}%".rjust(12) for b in (0, 5, 10, 15, 20)))
for L in (1, 2, 3, 5):
    row = f"  {L}x  "
    for bapr in (0, 0.05, 0.10, 0.15, 0.20):
        bday = bapr/365
        eq = 1.0; e = []
        for i in range(len(days)):
            r = L*unlev[i] - (L-1)*bday*held[i]   # 보유일만 차입이자
            eq *= (1+r); e.append(eq)
        cg, mdd = metr(e)
        row += f"{cg*100:+10.0f}%"
    print(row)

print("\n해석: borrow가 펀딩엣지보다 높으면 레버가 net 깎음. 같으면 레버 무의미. 낮으면 레버 이득.")
print("판정: 현실 borrow(USDT 마진 5~15%)에서 2x net이 1x보다 *확실히* 높아야 레버 가치. 아니면 1x(또는 무레버).")
print("주의: 여기에도 basis shock·ADL·거래소 tail은 아직 미반영(레버가 그것도 증폭).")
