#!/usr/bin/env python3
"""
GPT Test1: 추세추종 robustness 정직검증 — lookahead 제거(신호 t-1, 체결 t+1 시가 근사),
비용 민감도(fee 0.1%+slippage 0/0.05/0.1%, 2x), subperiod, PnL 집중도, vs BTC/ETH/50:50 BH.
"추세가 진짜 BH를 이기나, 아니면 견디기 쉬운 BH 변형인가" 판정.
"""
import os, math, datetime
import numpy as np

CASH0 = 10000.0
OHLC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btcache_ohlc")


def load(sym, y):
    d = np.load(f"{OHLC}/{sym}_{y}.npz"); return d["t"], d["o"], d["c"]
def sma(c, n):
    s = np.full(len(c), np.nan); cs = np.cumsum(np.insert(c, 0, 0)); s[n-1:] = (cs[n:]-cs[:-n])/n; return s
def ema(c, n):
    a = 2/(n+1); o = np.empty(len(c)); o[0] = c[0]
    for i in range(1, len(c)): o[i] = a*c[i]+(1-a)*o[i-1]
    return o
def yof(ms): return datetime.datetime.utcfromtimestamp(ms/1000).year


def metrics(eq, t):
    eq = np.array(eq, float)
    if len(eq) < 2 or eq[-1] <= 0: return None
    ret = eq[-1]/eq[0]-1
    cagr = (eq[-1]/eq[0])**(365/len(eq))-1
    pk = np.maximum.accumulate(eq); mdd = ((eq-pk)/pk).min()
    dr = np.diff(eq)/eq[:-1]; sh = np.nanmean(dr)/np.nanstd(dr)*math.sqrt(365) if np.nanstd(dr) > 0 else 0
    calmar = cagr/abs(mdd) if mdd < 0 else 0
    # 연도별 로그수익 집중도
    yrs = {}
    for i in range(1, len(eq)):
        y = yof(t[i]); yrs[y] = yrs.get(y, 0) + math.log(eq[i]/eq[i-1]) if eq[i] > 0 and eq[i-1] > 0 else yrs.get(y, 0)
    tot_log = sum(yrs.values()); worst = min(yrs.values()) if yrs else 0
    conc = (max(yrs.values())/tot_log*100) if tot_log > 0 else 0
    return dict(ret=ret, cagr=cagr, mdd=mdd, sh=sh, calmar=calmar, worst=worst, conc=conc)


def trend_eq(c, t, sig_raw, fee, slip):
    """신호 1일 지연(lookahead 제거). 전환 시 fee+slip. close-to-close."""
    pos = np.zeros(len(c)); pos[1:] = sig_raw[:-1]
    eq = CASH0; e = np.empty(len(c)); tim = 0; trades = 0
    for i in range(1, len(c)):
        if pos[i] == 1:
            eq *= (1 + (c[i]/c[i-1]-1)); tim += 1
        if pos[i] != pos[i-1]:
            eq *= (1-(fee+slip)); trades += 1
        e[i] = eq
    e[0] = CASH0
    return e, tim/(len(c)-1)*100, trades


def bh_eq(c):
    return CASH0*c/c[0]


COINS = {"BTCUSDT": 2017, "ETHUSDT": 2017}
D = {s: load(s, y) for s, y in COINS.items()}

STR = (["SMA50","SMA75","SMA100","SMA125","SMA150","SMA200"])
def sigof(name, c):
    n = int(name[3:]); return (c > sma(c, n)).astype(float)


def run_period(label, mask_from):
    print(f"\n{'='*98}\n[{label}] (fee 0.1% + slippage 0.05%, 신호지연+t+1근사)\n{'='*98}")
    for s, (t, o, c) in D.items():
        i0 = next((i for i in range(len(t)) if yof(t[i]) >= mask_from), 0)
        tt, cc = t[i0:], c[i0:]
        bh = bh_eq(cc); bm = metrics(bh, tt)
        print(f"\n  [{s}] BH: ret {bm['ret']*100:+.0f}% CAGR {bm['cagr']*100:+.0f}% MDD {bm['mdd']*100:.0f}% Sharpe {bm['sh']:.2f} Calmar {bm['calmar']:.2f} 최악년 {bm['worst']*100:+.0f}% 집중 {bm['conc']:.0f}%")
        for name in STR:
            sig = sigof(name, cc)
            e, tim, tr = trend_eq(cc, tt, sig, 0.001, 0.0005)
            m = metrics(e, tt)
            win = "★" if m['ret'] > bm['ret'] else " "
            cwin = "C" if m['calmar'] > bm['calmar'] else " "
            print(f"  {win}{cwin}{name:<7} ret {m['ret']*100:+8.0f}% CAGR {m['cagr']*100:+5.0f}% MDD {m['mdd']*100:5.0f}% Sh {m['sh']:.2f} Calmar {m['calmar']:.2f} 보유 {tim:.0f}% 거래 {tr} 집중 {m['conc']:.0f}%")


for lbl, fr in [("전체 2017~", 2017), ("2021~ (후반 사이클)", 2021), ("2022~ (최근, 불장 일부제외)", 2022)]:
    run_period(lbl, fr)

# 비용 민감도 (BTC SMA100, 전체)
print(f"\n{'='*98}\n비용 민감도 — BTC SMA100 (slippage·fee 2배까지)\n{'='*98}")
t, o, c = D["BTCUSDT"]; sig = sigof("SMA100", c); bm = metrics(bh_eq(c), t)
for fee, slip, lbl in [(0.001,0.0,"fee0.1 slip0"),(0.001,0.0005,"fee0.1 slip0.05"),(0.001,0.001,"fee0.1 slip0.1"),(0.002,0.001,"fee0.2 slip0.1(2배)")]:
    e, tim, tr = trend_eq(c, t, sig, fee, slip); m = metrics(e, t)
    print(f"  {lbl:<20} ret {m['ret']*100:+8.0f}% (BH {bm['ret']*100:+.0f}%) MDD {m['mdd']*100:.0f}% Calmar {m['calmar']:.2f}")

# BTC/ETH 50:50 포트폴리오 (SMA100 각 sleeve)
print(f"\n{'='*98}\nBTC/ETH 50:50 — 각 sleeve SMA100 추세 vs 50:50 BH\n{'='*98}")
tb, ob, cb = D["BTCUSDT"]; te, oe, ce = D["ETHUSDT"]
n = min(len(cb), len(ce)); cb2, ce2, tt = cb[-n:], ce[-n:], tb[-n:]
eb, _, _ = trend_eq(cb2, tt, (cb2 > sma(cb2,100)).astype(float), 0.001, 0.0005)
ee, _, _ = trend_eq(ce2, tt, (ce2 > sma(ce2,100)).astype(float), 0.001, 0.0005)
port = 0.5*np.array(eb)+0.5*np.array(ee)
bhport = 0.5*bh_eq(cb2)+0.5*bh_eq(ce2)
mp = metrics(port, tt); mb = metrics(bhport, tt)
print(f"  50:50 추세 ret {mp['ret']*100:+.0f}% MDD {mp['mdd']*100:.0f}% Sharpe {mp['sh']:.2f} Calmar {mp['calmar']:.2f}")
print(f"  50:50 BH   ret {mb['ret']*100:+.0f}% MDD {mb['mdd']*100:.0f}% Sharpe {mb['sh']:.2f} Calmar {mb['calmar']:.2f}")
print("\n판정: ret로 BH 이기는 별(★) + Calmar 우위(C) + 집중도 낮음 + 비용2배 생존 + subperiod 일관이면 → 진짜 우위. 아니면 'BH 변형'.")
