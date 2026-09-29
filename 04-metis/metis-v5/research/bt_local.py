#!/usr/bin/env python3
"""
운영자 "확실하게" — 분할매수/평균회귀 계열 정밀 검증 (로컬, 4코인).
미리보기 유망 2종(물타기+추세필터, RSI평균회귀)을 v4식으로:
  1) 파라미터 robustness — 대부분 조합이 BH 이기면 진짜, 한 조합만이면 과적합
  2) walk-forward OOS — 앞 60%서 베스트 파라미터 → 뒤 40%(표본밖)서도 BH 이기나
  3) v4 추세추종(SMA125)과 직접 비교
  4) 일봉 + 1h
수수료 0.1%/체결 포함. BH가 벤치마크.
"""
import requests, time, os, math
import numpy as np

FEE = 0.001
CASH0 = 10000.0
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btcache_local")


def fetch(sym, interval, days):
    os.makedirs(CACHE, exist_ok=True)
    fn = f"{CACHE}/{sym}_{interval}_{days}.npy"
    if os.path.exists(fn) and time.time() - os.path.getmtime(fn) < 43200:
        return np.load(fn)
    end = int(time.time() * 1000); start = end - days * 86400000
    allk = {}; cur = end
    for _ in range(800):
        try:
            r = requests.get("https://api.bybit.com/v5/market/kline",
                             params={"category": "spot", "symbol": sym, "interval": interval, "end": cur, "limit": 1000}, timeout=20)
            lst = r.json().get("result", {}).get("list", [])
        except Exception:
            time.sleep(1); continue
        if not lst:
            break
        for k in lst:
            allk[int(k[0])] = float(k[4])
        oldest = min(int(k[0]) for k in lst)
        if oldest <= start or len(lst) < 1000:
            break
        cur = oldest - 1; time.sleep(0.05)
    arr = np.array([allk[t] for t in sorted(allk) if t >= start])
    np.save(fn, arr); return arr


def sma(c, n):
    s = np.full(len(c), np.nan)
    csum = np.cumsum(np.insert(c, 0, 0))
    s[n-1:] = (csum[n:] - csum[:-n]) / n
    return s


def rsi(c, n=14):
    d = np.diff(c, prepend=c[0])
    up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    ru = np.zeros_like(c); rd = np.zeros_like(c)
    if len(c) > n:
        ru[n] = up[1:n+1].mean(); rd[n] = dn[1:n+1].mean()
        for i in range(n+1, len(c)):
            ru[i] = (ru[i-1]*(n-1)+up[i])/n; rd[i] = (rd[i-1]*(n-1)+dn[i])/n
    rs = np.divide(ru, rd, out=np.ones_like(c), where=rd != 0)
    return 100 - 100/(1+rs)


def stats(eqc, ppy=365):
    eqc = np.array(eqc, float)
    if len(eqc) < 2 or eqc[-1] <= 0:
        return -1, -1, 0
    ret = eqc[-1]/eqc[0]-1
    peak = np.maximum.accumulate(eqc); mdd = ((eqc-peak)/peak).min()
    dr = np.diff(eqc)/eqc[:-1]
    sh = (np.nanmean(dr)/np.nanstd(dr)*math.sqrt(ppy)) if np.nanstd(dr) > 0 else 0
    return ret, mdd, sh


# ---------- 전략 ----------
def bh(c):
    return CASH0 * c / c[0]


def dip_trend(c, trig, target, frac=0.15, tn=125):
    tr = sma(c, tn)
    cash = CASH0; coins = 0.0; inv = 0.0; last = None; eq = np.empty(len(c))
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


def rsi_mr(c, buy, sell, frac=0.15, target=0.05):
    r = rsi(c); cash = CASH0; coins = 0.0; inv = 0.0; eq = np.empty(len(c))
    for i, p in enumerate(c):
        if r[i] < buy and cash >= CASH0*frac:
            amt = CASH0*frac; coins += amt/p*(1-FEE); cash -= amt; inv += amt
        if coins > 0 and (r[i] > sell or p >= (inv/coins)*(1+target)):
            cash += coins*p*(1-FEE); coins = 0; inv = 0
        eq[i] = cash+coins*p
    return eq


def v4_trend(c, n=125, buf=0.02):
    s = sma(c, n); cash = CASH0; coins = 0.0; eq = np.empty(len(c)); pos = 0
    for i, p in enumerate(c):
        if not np.isnan(s[i]):
            if pos == 0 and p > s[i]:
                coins = cash/p*(1-FEE); cash = 0; pos = 1
            elif pos == 1 and p < s[i]*(1-buf):
                cash = coins*p*(1-FEE); coins = 0; pos = 0
        eq[i] = cash+coins*p
    return eq


COINS = {"BTCUSDT": 1500, "ETHUSDT": 1500, "SOLUSDT": 1500, "XRPUSDT": 1500}
DATA = {s: fetch(s, "D", d) for s, d in COINS.items()}
print("데이터 로드:", {s: len(v) for s, v in DATA.items()})

# ===== 1) robustness 스윕 (BH 이기는 조합 비율) =====
print("\n" + "="*92)
print("1) 파라미터 robustness — 물타기+추세필터 (trig×target 16조합 중 BH 이긴 수 / Sharpe중앙값)")
print("="*92)
trigs = [0.03, 0.05, 0.08, 0.10]; targets = [0.03, 0.05, 0.08, 0.10]
for s, c in DATA.items():
    bhr = bh(c)[-1]/CASH0-1
    res = []
    for tg in trigs:
        for tp in targets:
            e = dip_trend(c, tg, tp); r, m, sh = stats(e); res.append((r, m, sh))
    beat = sum(1 for r, m, sh in res if r > bhr)
    shs = sorted(r[2] for r in res)
    rets = [r[0] for r in res]
    print(f"  {s:<8} BH {bhr*100:+5.0f}% | BH이긴조합 {beat}/16 | Sharpe중앙 {np.median(shs):.2f} | ret중앙 {np.median(rets)*100:+.0f}% | MDD중앙 {np.median([r[1] for r in res])*100:.0f}%")

print("\n   RSI 평균회귀 (buy×sell 조합)")
for s, c in DATA.items():
    bhr = bh(c)[-1]/CASH0-1; res = []
    for b in [25, 30, 35]:
        for sl in [65, 70, 75]:
            e = rsi_mr(c, b, sl); res.append(stats(e))
    beat = sum(1 for r, m, sh in res if r > bhr)
    print(f"  {s:<8} BH {bhr*100:+5.0f}% | BH이긴조합 {beat}/9 | Sharpe중앙 {np.median([r[2] for r in res]):.2f} | ret중앙 {np.median([r[0] for r in res])*100:+.0f}%")

# ===== 2) walk-forward OOS =====
print("\n" + "="*92)
print("2) walk-forward — 앞 60%서 베스트 파라미터 선택 → 뒤 40%(표본밖)서 BH 대비")
print("="*92)
for s, c in DATA.items():
    n = len(c); split = int(n*0.6)
    cis, cos = c[:split], c[split:]
    best = None
    for tg in trigs:
        for tp in targets:
            r, m, sh = stats(dip_trend(cis, tg, tp))
            if best is None or sh > best[0]:
                best = (sh, tg, tp)
    e_oos = dip_trend(cos, best[1], best[2]); r, m, sh = stats(e_oos)
    bhr = bh(cos)[-1]/CASH0-1
    win = "✅" if r > bhr else "❌"
    print(f"  {s:<8} IS베스트(trig{best[1]*100:.0f}/tgt{best[2]*100:.0f}) → OOS ret {r*100:+5.0f}% MDD {m*100:.0f}% Sh {sh:.2f} {win} vs BH(OOS) {bhr*100:+.0f}%")

# ===== 3) v4 추세추종 직접 비교 =====
print("\n" + "="*92)
print("3) v4 추세추종(SMA125) vs 물타기+추세필터(5%/5%) vs BH — 전체기간")
print("="*92)
for s, c in DATA.items():
    for name, e in [("BH", bh(c)), ("v4 추세추종", v4_trend(c)), ("물타기+추세", dip_trend(c, 0.05, 0.05))]:
        r, m, sh = stats(e)
        print(f"  {s:<8} {name:<12} ret {r*100:+6.0f}%  MDD {m*100:5.0f}%  Sharpe {sh:.2f}")
    print()

# ===== 4) 1h (더 잦은 분할매수) — 수수료 적 확인 =====
print("\n" + "="*92)
print("4) 1h 타임프레임 (더 자주 물타기) — 720h(30일) 추세필터. BH/v4와 비교. ppy=8760")
print("="*92)
D1H = {s: fetch(s, "60", 720) for s in COINS}
print("1h 데이터:", {s: len(v) for s, v in D1H.items()})
for s, c in D1H.items():
    if len(c) < 1000:
        print(f"  {s}: 데이터 부족({len(c)})"); continue
    rows = []
    for name, e in [("BH", bh(c)), ("v4추세(720h)", v4_trend(c, 720)),
                    ("물타기+추세 5/5", dip_trend(c, 0.05, 0.05, tn=720)),
                    ("물타기+추세 3/3", dip_trend(c, 0.03, 0.03, tn=720)),
                    ("RSI평균회귀", rsi_mr(c, 30, 70))]:
        r, m, sh = stats(e, ppy=8760)
        rows.append((name, r, m, sh))
    bhr = rows[0][1]
    for name, r, m, sh in rows:
        win = "✅" if r > bhr and name != "BH" else "  "
        print(f"  {s:<8} {name:<14} ret {r*100:+7.0f}%  MDD {m*100:5.0f}%  Sharpe {sh:5.2f} {win}")
    print()

print("판정: robustness에서 BH이긴조합이 다수(>50%)+OOS도 ✅면 진짜 엣지. 한 조합만이거나 OOS ❌면 과적합.")
