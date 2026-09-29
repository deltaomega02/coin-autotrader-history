#!/usr/bin/env python3
"""
운영자 "추세롱 + funding carry 두 sleeve 같이 굴리면?" — 결합 포트폴리오 데이터.
중립 측정: 두 sleeve 상관계수 + 합산 Sharpe/MDD + 가중치별. funding은 basis까지 반영(더 현실적).
"""
import requests, time, datetime, math, os
import numpy as np

OHLC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btcache_ohlc")
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btcache_fund")
FEE_LEG = 0.0006; SLIP = 0.0005; SPOT_FEE = 0.001


def load_spot(sym, y):
    d = np.load(f"{OHLC}/{sym}_{y}.npz"); return d["t"], d["c"]
def sma(c, n):
    s = np.full(len(c), np.nan); cs = np.cumsum(np.insert(c, 0, 0)); s[n-1:] = (cs[n:]-cs[:-n])/n; return s
def stats(e):
    e = np.array(e, float)
    if len(e) < 2 or e[-1] <= 0: return dict(ret=-1, cagr=-1, mdd=-1, sh=0)
    ret = e[-1]/e[0]-1; cagr = (e[-1]/e[0])**(365/len(e))-1
    pk = np.maximum.accumulate(e); mdd = ((e-pk)/pk).min()
    dr = np.diff(e)/e[:-1]; sh = np.nanmean(dr)/np.nanstd(dr)*math.sqrt(365) if np.nanstd(dr) > 0 else 0
    return dict(ret=ret, cagr=cagr, mdd=mdd, sh=sh)


def fetch_cached(kind, sym, fn_url, parse, extra=None):
    os.makedirs(CACHE, exist_ok=True)
    fn = f"{CACHE}/{kind}_{sym}.npz"
    if os.path.exists(fn) and time.time()-os.path.getmtime(fn) < 86400:
        d = np.load(fn); return d["k"], d["v"]
    out = {}; cur = int(datetime.datetime(2019, 1, 1, tzinfo=datetime.timezone.utc).timestamp()*1000)
    now = int(time.time()*1000)
    for _ in range(400):
        try:
            params = {"symbol": sym, "startTime": cur, "limit": 1000}
            if extra: params.update(extra)
            r = requests.get(fn_url, params=params, timeout=20).json()
        except Exception: time.sleep(1); continue
        if not isinstance(r, list): break
        if not r:
            if out: break                       # 끝 도달
            cur += 90*86400000                  # 상장 전 공백 건너뛰기
            if cur > now: break
            continue
        for x in r:
            k, v = parse(x)
            out[k] = v
        last = max(parse(x)[0] for x in r)
        if last <= cur or len(r) < 1000: break
        cur = last+1; time.sleep(0.05)
    ks = np.array(sorted(out)); vs = np.array([out[k] for k in ks])
    np.savez(fn, k=ks, v=vs); return ks, vs


def get_funding(sym):
    return fetch_cached("fund", sym, "https://fapi.binance.com/fapi/v1/fundingRate",
                        lambda x: (int(x["fundingTime"]), float(x["fundingRate"])))
def get_perp(sym):
    return fetch_cached("perp", sym, "https://fapi.binance.com/fapi/v1/klines",
                        lambda x: (int(x[0]), float(x[4])), extra={"interval": "1d"})


def carry_sleeve(sym, thr=0.0006):
    ft, fv = get_funding(sym); pt, pv = get_perp(sym)
    yspot = 2017 if sym in ("BTCUSDT", "ETHUSDT") else (2020 if sym == "SOLUSDT" else 2018)
    st, sv = load_spot(sym, yspot)
    # 일별 펀딩 합
    df = {}
    for i in range(len(ft)):
        d = ft[i]-(ft[i] % 86400000); df[d] = df.get(d, 0)+fv[i]
    perp = {pt[i]: pv[i] for i in range(len(pt))}
    spot = {st[i]: sv[i] for i in range(len(st))}
    days = sorted(set(df) & set(perp) & set(spot))
    eq = 1.0; e = {}; inpos = False
    frl = [df[d] for d in days]
    for i in range(3, len(days)):
        d = days[i]
        trail = np.mean(frl[i-3:i])
        if not inpos and trail > thr:
            eq *= (1-2*(FEE_LEG+SLIP)); inpos = True
        elif inpos and trail <= 0:
            eq *= (1-2*(FEE_LEG+SLIP)); inpos = False
        if inpos:
            perp_ret = perp[d]/perp[days[i-1]]-1; spot_ret = spot[d]/spot[days[i-1]]-1
            daily = frl[i] - (perp_ret - spot_ret)     # 펀딩수취 - basis드리프트
            eq *= (1+daily)
        e[d] = eq
    return e


def trend_sleeve(sym, n=125):
    yspot = 2017 if sym in ("BTCUSDT", "ETHUSDT") else (2020 if sym == "SOLUSDT" else 2018)
    t, c = load_spot(sym, yspot); s = sma(c, n)
    sig = np.zeros(len(c)); sig[1:] = (c > s).astype(float)[:-1]
    eq = 1.0; e = {}
    for i in range(1, len(c)):
        if sig[i] == 1: eq *= (c[i]/c[i-1])
        if sig[i] != sig[i-1]: eq *= (1-SPOT_FEE)
        e[t[i]] = eq
    return e


# 두 sleeve (BTC+ETH 평균)
carry = {}; trend = {}
for sym in ("BTCUSDT", "ETHUSDT"):
    cs = carry_sleeve(sym); ts = trend_sleeve(sym)
    for d, v in cs.items(): carry.setdefault(d, []).append(v)
    for d, v in ts.items(): trend.setdefault(d, []).append(v)
# 공통일자
common = sorted(set(carry) & set(trend))
# 각 sleeve 정규화 (공통 시작=1)
def norm(series, dct):
    base_each = {}
    out = []
    for d in series:
        vals = dct[d]
        out.append(np.mean(vals))
    out = np.array(out); return out/out[0]
carry_e = norm(common, carry); trend_e = norm(common, trend)
# BH (BTC+ETH 50:50, 공통구간)
tb, cb = load_spot("BTCUSDT", 2017); te, ce = load_spot("ETHUSDT", 2017)
bp = {tb[i]: cb[i] for i in range(len(tb))}; ep = {te[i]: ce[i] for i in range(len(te))}
bh = np.array([0.5*bp[d]/bp[common[0]]+0.5*ep[d]/ep[common[0]] for d in common if d in bp and d in ep])

d0 = datetime.datetime.utcfromtimestamp(common[0]/1000).date()
d1 = datetime.datetime.utcfromtimestamp(common[-1]/1000).date()
print(f"공통구간 {d0}~{d1} ({len(common)}일)\n")

tr_ret = np.diff(trend_e)/trend_e[:-1]; ca_ret = np.diff(carry_e)/carry_e[:-1]
corr = np.corrcoef(tr_ret, ca_ret)[0, 1]
print(f"두 sleeve 일수익 상관계수: {corr:+.2f}  (낮을수록 결합 효과↑)\n")

print(f"{'전략':<22}{'총수익':>9}{'연':>7}{'MDD':>7}{'Sharpe':>8}")
for name, e in [("추세롱(BTC/ETH SMA125)", trend_e), ("funding carry(basis반영)", carry_e),
                ("BH 50:50", bh)]:
    s = stats(e); print(f"  {name:<20}{s['ret']*100:>+8.0f}%{s['cagr']*100:>+6.0f}%{s['mdd']*100:>6.0f}%{s['sh']:>8.2f}")

print(f"\n결합 포트폴리오 (월 리밸런스):")
for wt in (0.7, 0.5, 0.3):
    # wt=추세 비중
    port = []
    eqp = 1.0
    last_reb = 0
    w_t, w_c = wt, 1-wt
    units_t = w_t; units_c = w_c  # 정규화 시작
    for i in range(len(common)):
        if i > 0:
            units_t *= trend_e[i]/trend_e[i-1]; units_c *= carry_e[i]/carry_e[i-1]
        tot = units_t+units_c
        if i - last_reb >= 30:  # 월 리밸런스
            units_t = tot*w_t; units_c = tot*w_c; last_reb = i
        port.append(tot)
    s = stats(np.array(port))
    print(f"  추세 {int(wt*100)}% + carry {int((1-wt)*100)}%   {s['ret']*100:>+8.0f}% {s['cagr']*100:>+5.0f}% MDD {s['mdd']*100:>5.0f}% Sharpe {s['sh']:.2f}")

print("\n판정(중립): 상관 낮고(<0.3) 결합 Sharpe가 추세단독·BH보다 높으면 → 두 sleeve 결합이 진짜 개선.")
print("           단 carry는 basis만 반영(거래소/청산/스테이블 tail 여전히 미반영).")
