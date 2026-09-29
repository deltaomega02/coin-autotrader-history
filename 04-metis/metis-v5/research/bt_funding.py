#!/usr/bin/env python3
"""
GPT Test4: funding carry (cash-and-carry) — 현물 long + perp short = 델타중립, 펀딩 수취.
추세와 다른 메커니즘(롱 레버리지 수요가 펀딩 지불). 약세장/횡보 무관 독립 수익원 후보.
Binance 실제 funding 이력(8h) + perp/spot 종가(basis). 진입 trailing funding>thresh, 청산 <=0.
비용: leg당 0.06%×2(왕복 0.24% on notional) + slippage. lookahead 금지(확정 펀딩만).
"""
import requests, time, datetime, math
import numpy as np

FEE_LEG = 0.0006; SLIP = 0.0005


def fetch_funding(sym):
    out = {}; cur = int(datetime.datetime(2019,1,1,tzinfo=datetime.timezone.utc).timestamp()*1000)
    for _ in range(200):
        try:
            r = requests.get("https://fapi.binance.com/fapi/v1/fundingRate",
                params={"symbol":sym,"startTime":cur,"limit":1000},timeout=20).json()
        except Exception: time.sleep(1); continue
        if not isinstance(r,list) or not r: break
        for x in r: out[int(x["fundingTime"])] = float(x["fundingRate"])
        last = max(int(x["fundingTime"]) for x in r)
        if last <= cur or len(r) < 1000: break
        cur = last+1; time.sleep(0.05)
    return out


def fetch_perp_daily(sym):
    out = {}; cur = int(datetime.datetime(2019,1,1,tzinfo=datetime.timezone.utc).timestamp()*1000)
    for _ in range(80):
        try:
            r = requests.get("https://fapi.binance.com/fapi/v1/klines",
                params={"symbol":sym,"interval":"1d","startTime":cur,"limit":1000},timeout=20).json()
        except Exception: time.sleep(1); continue
        if not isinstance(r,list) or not r: break
        for k in r: out[int(k[0])] = float(k[4])
        last = int(r[-1][0])
        if last<=cur or len(r)<1000: break
        cur = last+86400000; time.sleep(0.04)
    return out


def stats(e):
    e=np.array(e,float)
    if len(e)<2 or e[-1]<=0: return -1,-1,0,0
    ret=e[-1]/e[0]-1; cagr=(e[-1]/e[0])**(365/len(e))-1
    pk=np.maximum.accumulate(e); mdd=((e-pk)/pk).min()
    dr=np.diff(e)/e[:-1]; sh=np.nanmean(dr)/np.nanstd(dr)*math.sqrt(365) if np.nanstd(dr)>0 else 0
    return ret,cagr,mdd,sh


for sym in ["BTCUSDT","ETHUSDT","SOLUSDT"]:
    fund = fetch_funding(sym); perp = fetch_perp_daily(sym)
    if len(fund) < 500:
        print(f"{sym}: funding 데이터 부족({len(fund)})"); continue
    # 일별 펀딩 합산
    daily_f = {}
    for ts,rate in fund.items():
        d = ts - (ts % 86400000); daily_f[d] = daily_f.get(d,0)+rate
    days = sorted(set(daily_f) & set(perp))
    fr = np.array([daily_f[d] for d in days])           # 일 펀딩합
    pp = np.array([perp[d] for d in days])
    n = len(days)
    avg_f8 = fund and (np.mean(list(fund.values()))*100)
    print(f"\n[{sym}] {n}일, 평균 펀딩 {np.mean(fr)*100:.4f}%/일 (연 {np.mean(fr)*365*100:.1f}%), 양수일 비율 {np.mean(fr>0)*100:.0f}%")

    # 항상 보유(always carry) vs 조건부(funding>thresh)
    for mode, thr in [("항상 캐리", -1e9), ("펀딩>0.06%/일", 0.0006), ("펀딩>0.10%/일", 0.0010)]:
        cash = 10000.0; e = []; inpos = False; tim = 0; trades = 0
        for i in range(3, n):
            trail = np.mean(fr[i-3:i])      # 직전 3일(확정) = lookahead 금지
            if not inpos and trail > thr:
                cash *= (1 - 2*(FEE_LEG+SLIP)); inpos = True; trades += 1   # 양다리 진입
            elif inpos and trail <= 0:
                cash *= (1 - 2*(FEE_LEG+SLIP)); inpos = False; trades += 1   # 양다리 청산
            if inpos:
                cash *= (1 + fr[i])         # 숏이 펀딩 수취(델타중립=가격상쇄 근사)
                tim += 1
            e.append(cash)
        r,cg,m,sh = stats(e)
        print(f"   {mode:<14} 연 {cg*100:+6.1f}%  총 {r*100:+7.0f}%  MDD {m*100:5.1f}%  Sharpe {sh:5.2f}  보유 {tim/(n-3)*100:3.0f}%  거래 {trades}")

print("\n주의: 델타중립 가격상쇄는 근사(basis 변동·청산·거래소리스크 미반영). 펀딩은 실제이력.")
print("판정: 비용 후 연 8~15%+ & 낮은 MDD면 '저변동 독립 수익원'으로 가치. BH terminal은 못 넘음(불장).")
