#!/usr/bin/env python3
"""GPT 1순위 오버레이 robustness — 결론이 설계선택에 흔들리나 확인(과적합 탐색 아님).
앙상블 SMA / 변동성타게팅 / BTC·ETH 동적 / 2-sleeve 리스크패리티 / 리밸런스밴드."""
import math, os, datetime
import numpy as np

OHLC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btcache_ohlc")
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btcache_fund")
FEE = 0.001; FEE_LEG = 0.0006; SLIP = 0.0005


def load_spot(s, y): d = np.load(f"{OHLC}/{s}_{y}.npz"); return d["t"], d["c"]
def cached(k, s): d = np.load(f"{CACHE}/{k}_{s}.npz"); return d["k"], d["v"]
def sma(c, n):
    s = np.full(len(c), np.nan); cs = np.cumsum(np.insert(c, 0, 0)); s[n-1:] = (cs[n:]-cs[:-n])/n; return s
def st(e):
    e = np.array(e, float)
    if len(e) < 2 or e[-1] <= 0: return dict(ret=-1, mdd=-1, sh=0)
    pk = np.maximum.accumulate(e); dr = np.diff(e)/e[:-1]
    return dict(ret=e[-1]/e[0]-1, mdd=((e-pk)/pk).min(), sh=np.nanmean(dr)/np.nanstd(dr)*math.sqrt(365) if np.nanstd(dr) > 0 else 0)


def eq_from_pos(c, raw, fee=FEE):
    pos = np.zeros(len(c)); pos[1:] = raw[:-1]
    e = np.empty(len(c)); v = 1.0
    for i in range(1, len(c)):
        if pos[i] > 0: v *= (1 + pos[i]*(c[i]/c[i-1]-1))
        if abs(pos[i]-pos[i-1]) > 1e-9: v *= (1-fee*abs(pos[i]-pos[i-1]))
        e[i] = v
    e[0] = 1; return e


def realized_vol(c, w=20):
    r = np.diff(c, prepend=c[0])/c; v = np.full(len(c), np.nan)
    for i in range(w, len(c)): v[i] = np.std(r[i-w:i])*math.sqrt(365)
    return v


tb, cb = load_spot("BTCUSDT", 2017); te_, ce_ = load_spot("ETHUSDT", 2017)

print("="*90)
print("A) 추세 신호 robustness — 단일 SMA125 vs 앙상블(100/125/150/200 평균) [BTC]")
print("="*90)
single = (cb > sma(cb, 125)).astype(float)
ens = np.mean([(cb > sma(cb, n)).astype(float) for n in (100, 125, 150, 200)], axis=0)
for name, raw in [("단일 SMA125", single), ("앙상블 4종", ens)]:
    m = st(eq_from_pos(cb, raw)); print(f"  {name:<14} ret {m['ret']*100:+8.0f}% MDD {m['mdd']*100:5.0f}% Sharpe {m['sh']:.2f}")

print("\n" + "="*90)
print("B) 변동성 타게팅 오버레이 — SMA125 노출을 목표변동성으로 스케일 [BTC]")
print("="*90)
rv = realized_vol(cb)
base = (cb > sma(cb, 125)).astype(float)
m = st(eq_from_pos(cb, base)); print(f"  타게팅 없음        ret {m['ret']*100:+8.0f}% MDD {m['mdd']*100:5.0f}% Sharpe {m['sh']:.2f}")
for tgt in (0.4, 0.6, 0.8):
    scaled = base * np.clip(np.where(np.isnan(rv), 0.5, tgt/np.where(rv > 0, rv, 1)), 0, 1)
    m = st(eq_from_pos(cb, scaled)); print(f"  목표vol {tgt*100:.0f}%       ret {m['ret']*100:+8.0f}% MDD {m['mdd']*100:5.0f}% Sharpe {m['sh']:.2f}")

print("\n" + "="*90)
print("C) BTC/ETH 배분 robustness — 50:50 고정 vs 상대모멘텀 동적 (각 sleeve SMA125)")
print("="*90)
n = min(len(cb), len(ce_)); b, e2 = cb[-n:], ce_[-n:]
eb = eq_from_pos(b, (b > sma(b, 125)).astype(float)); ee = eq_from_pos(e2, (e2 > sma(e2, 125)).astype(float))
fix = 0.5*eb+0.5*ee
# 동적: 90일 상대수익 가중, 월 리밸
dyn = []; wb = 0.5; last = 0; ub = 0.5; ue = 0.5
for i in range(n):
    if i > 0: ub *= eb[i]/eb[i-1]; ue *= ee[i]/ee[i-1]
    if i >= 90 and i-last >= 30:
        mb = b[i]/b[i-90]-1; me = e2[i]/e2[i-90]-1
        tot_m = max(mb, 0)+max(me, 0)
        wb = 0.5 if tot_m <= 0 else max(mb, 0)/tot_m
        s = ub+ue; ub = s*wb; ue = s*(1-wb); last = i
    dyn.append(ub+ue)
for name, e in [("50:50 고정", fix), ("상대모멘텀 동적", np.array(dyn))]:
    m = st(e); print(f"  {name:<14} ret {m['ret']*100:+8.0f}% MDD {m['mdd']*100:5.0f}% Sharpe {m['sh']:.2f}")

# carry sleeve
def carry_sleeve(sym, thr=0.0006, win=3):
    ft, fv = cached("fund", sym); pt, pv = cached("perp", sym)
    ys = 2017 if sym in ("BTCUSDT", "ETHUSDT") else 2020
    s_t, s_v = load_spot(sym, ys)
    df = {}
    for i in range(len(ft)):
        d = int(ft[i])-(int(ft[i]) % 86400000); df[d] = df.get(d, 0)+fv[i]
    perp = {int(pt[i]): pv[i] for i in range(len(pt))}; spot = {int(s_t[i]): s_v[i] for i in range(len(s_t))}
    days = sorted(set(df) & set(perp) & set(spot)); frl = [df[d] for d in days]
    v = 1.0; e = {}; inp = False
    for i in range(win, len(days)):
        d = days[i]; tr = np.mean(frl[i-win:i])
        if not inp and tr > thr: v *= (1-2*(FEE_LEG+SLIP)); inp = True
        elif inp and tr <= 0: v *= (1-2*(FEE_LEG+SLIP)); inp = False
        if inp: v *= (1+frl[i]-(perp[d]/perp[days[i-1]]-1-(spot[d]/spot[days[i-1]]-1)))
        e[d] = v
    return e


print("\n" + "="*90)
print("D) 2-sleeve 배분 robustness — 고정70/30 vs 리스크패리티(역변동성 동적)")
print("="*90)
carry = {}; trend = {}
for sym in ("BTCUSDT", "ETHUSDT"):
    for d, v in carry_sleeve(sym).items(): carry.setdefault(d, []).append(v)
    raw = (load_spot(sym, 2017)[1] > sma(load_spot(sym, 2017)[1], 125)).astype(float)
    tt, cc = load_spot(sym, 2017); eqs = eq_from_pos(cc, raw)
    for i in range(len(tt)): trend.setdefault(int(tt[i]), []).append(eqs[i])
common = sorted(set(carry) & set(trend))
tE = np.array([np.mean(trend[d]) for d in common]); tE /= tE[0]
cE = np.array([np.mean(carry[d]) for d in common]); cE /= cE[0]
def mix(tw, rp=False):
    ut = tw; uc = 1-tw; last = 0; out = []
    tr = np.diff(tE)/tE[:-1]; cr = np.diff(cE)/cE[:-1]
    for i in range(len(common)):
        if i > 0: ut *= tE[i]/tE[i-1]; uc *= cE[i]/cE[i-1]
        tot = ut+uc
        if i-last >= 30 and i > 60:
            if rp:
                vt = np.std(tr[i-60:i]); vc = np.std(cr[i-60:i])
                w = (1/vt)/((1/vt)+(1/vc)) if vt > 0 and vc > 0 else tw
                w = min(max(w, 0.3), 0.85)  # carry tail 제한 위해 추세 최소30%
            else: w = tw
            ut = tot*w; uc = tot*(1-w); last = i
        out.append(tot)
    return np.array(out)
for name, e in [("고정 70/30", mix(0.7)), ("고정 50/50", mix(0.5)), ("리스크패리티", mix(0.7, rp=True))]:
    m = st(e); print(f"  {name:<14} ret {m['ret']*100:+8.0f}% MDD {m['mdd']*100:5.0f}% Sharpe {m['sh']:.2f}")

print("\n판정: 오버레이가 base보다 *일관되게* 개선하면 채택가치, 비슷하면 단순한 게 나음(과적합 회피).")
print("      결론(추세=핵심, carry=무상관 보조)이 모든 설계변형서 유지되면 = robust 확정.")
