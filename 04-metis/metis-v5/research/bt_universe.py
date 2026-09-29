#!/usr/bin/env python3
"""
운영자 "진짜 모든 전략 + 대규모 유니버스" — 크로스섹션 모멘텀 로테이션 중심.
"그날 뜰 코인 골라서" = 유니버스에서 강한 코인 top-K 보유, 주기적 갈아타기.
+ 포트폴리오 배분(동일/역변동성/리밸런싱) + 페어(BTC/ETH) + 단일코인 추세 벤치.
Binance 일봉 풀히스토리. 수수료 0.1%. 무차입. 벤치=BTC BH & 동일가중 BH.
생존편향: 현존 코인만(낙관 가능). 명시.
"""
import requests, time, datetime, math, os, itertools
import numpy as np

FEE = 0.001; CASH0 = 10000.0
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btcache_uni")
UNIVERSE = ["BTCUSDT","ETHUSDT","BNBUSDT","XRPUSDT","SOLUSDT","ADAUSDT","DOGEUSDT",
            "AVAXUSDT","LINKUSDT","DOTUSDT","LTCUSDT","BCHUSDT","TRXUSDT","ATOMUSDT",
            "UNIUSDT","ETCUSDT","XLMUSDT","NEARUSDT","FILUSDT","ALGOUSDT","VETUSDT",
            "ICPUSDT","HBARUSDT","AAVEUSDT","EOSUSDT","XTZUSDT","SANDUSDT","MANAUSDT"]


def fetch(sym, start_year=2018):
    os.makedirs(CACHE, exist_ok=True)
    fn = f"{CACHE}/{sym}.npz"
    if os.path.exists(fn) and time.time()-os.path.getmtime(fn) < 86400:
        d = np.load(fn); return d["t"], d["c"]
    sm = int(datetime.datetime(start_year,1,1,tzinfo=datetime.timezone.utc).timestamp()*1000)
    out = {}; cur = sm
    for _ in range(80):
        try:
            r = requests.get("https://api.binance.com/api/v3/klines",
                params={"symbol":sym,"interval":"1d","startTime":cur,"limit":1000},timeout=20).json()
        except Exception: time.sleep(1); continue
        if not isinstance(r,list) or not r: break
        for k in r: out[int(k[0])] = float(k[4])
        last = int(r[-1][0])
        if last <= cur or len(r) < 1000: break
        cur = last+86400000; time.sleep(0.04)
    t = np.array(sorted(out)); c = np.array([out[x] for x in t])
    np.savez(fn,t=t,c=c); return t,c


def stats(e):
    e = np.array(e,float)
    if len(e)<2 or e[-1]<=0: return -1,-1,0
    ret = e[-1]/e[0]-1; pk=np.maximum.accumulate(e); mdd=((e-pk)/pk).min()
    dr=np.diff(e)/e[:-1]; sh=(np.nanmean(dr)/np.nanstd(dr)*math.sqrt(365)) if np.nanstd(dr)>0 else 0
    return ret,mdd,sh


# ---- 데이터 정렬 (마스터 캘린더) ----
print("유니버스 다운로드...")
raw = {}
for s in UNIVERSE:
    t,c = fetch(s)
    if len(c) >= 600: raw[s] = (t,c)
    else: print(f"  스킵 {s} ({len(c)}일)")
syms = list(raw.keys())
all_days = sorted(set().union(*[set(raw[s][0]) for s in syms]))
day_idx = {d:i for i,d in enumerate(all_days)}
N = len(all_days); M = len(syms)
P = np.full((M,N), np.nan)
for j,s in enumerate(syms):
    t,c = raw[s]
    for k in range(len(t)): P[j, day_idx[t[k]]] = c[k]
print(f"유니버스 {M}코인, {N}일 ({datetime.datetime.utcfromtimestamp(all_days[0]/1000).date()}~{datetime.datetime.utcfromtimestamp(all_days[-1]/1000).date()})")
BTCJ = syms.index("BTCUSDT")


def smacol(arr, n):
    out = np.full(len(arr), np.nan)
    for i in range(n-1,len(arr)):
        w = arr[i-n+1:i+1]
        if not np.isnan(w).any(): out[i] = w.mean()
    return out
SMAS = {s: smacol(P[j], 100) for j,s in enumerate(syms)}
SMA100 = np.vstack([SMAS[s] for s in syms])


def rotation(lb, topk, reb, absfilter):
    """크로스섹션 모멘텀 로테이션. absfilter: 'none'/'sma'/'pos'"""
    cash = CASH0; units = np.zeros(M); eq = np.full(N, CASH0); start = max(lb, 100)+1
    for i in range(start, N):
        valid = ~np.isnan(P[:,i])
        # 일일 평가
        val = cash + np.nansum(np.where(valid, units*P[:,i], 0))
        eq[i] = val
        if (i-start) % reb != 0:
            continue
        # 모멘텀 계산
        mom = np.full(M, -1e9)
        for j in range(M):
            if valid[j] and not np.isnan(P[j,i-lb]) and P[j,i-lb] > 0:
                m = P[j,i]/P[j,i-lb]-1
                if absfilter == "sma" and not (not np.isnan(SMA100[j,i]) and P[j,i] > SMA100[j,i]):
                    continue
                if absfilter == "pos" and m <= 0:
                    continue
                mom[j] = m
        rank = [j for j in np.argsort(-mom) if mom[j] > -1e8][:topk]
        # 목표: 선택 코인 동일가중, 없으면 현금
        tgt = np.zeros(M)
        if rank:
            for j in rank: tgt[j] = 1.0/topk
        cur_val = cash + np.nansum(np.where(valid, units*P[:,i], 0))
        # 리밸런스 (회전율에 수수료)
        for j in range(M):
            if not valid[j]:
                if units[j] > 0:  # 상장폐지 근사: 마지막값으로 청산 불가 → 보유 유지(드물게)
                    pass
                continue
            tgt_val = cur_val*tgt[j]; cur_pos = units[j]*P[j,i]; d = tgt_val-cur_pos
            if abs(d) > cur_val*0.01:
                units[j] += (d/P[j,i])*(1-FEE if d > 0 else 1); cash -= d
        cash = cur_val - np.nansum(np.where(valid, units*P[:,i], 0))
        eq[i] = cash + np.nansum(np.where(valid, units*P[:,i], 0))
    return eq[start:]


def btc_bh(start):
    p = P[BTCJ]; out = []
    base = None
    for i in range(start, N):
        if not np.isnan(p[i]):
            if base is None: base = p[i]
            out.append(CASH0*p[i]/base)
        else:
            out.append(out[-1] if out else CASH0)
    return out


def ew_bh(start):
    # 동일가중 매수후보유 (각 코인 상장 시점부터 동일 비중, 단순화: start에 존재하는 코인 동일가중)
    valid0 = ~np.isnan(P[:,start])
    w = valid0/valid0.sum()
    base = np.where(valid0, P[:,start], 1)
    out = []
    for i in range(start, N):
        rel = np.where(~np.isnan(P[:,i]) & valid0, P[:,i]/base, 1)
        out.append(CASH0*np.sum(w*rel))
    return out


start = max(120, 100)+1
print("\n" + "="*92)
print("로테이션 스윕 (lb×topk×reb×필터). 벤치: BTC BH, 동일가중 BH")
print("="*92)
bb = btc_bh(start); eb = ew_bh(start)
br = stats(bb); er = stats(eb)
print(f"  [벤치] BTC BH      ret {br[0]*100:+8.0f}% MDD {br[1]*100:5.0f}% Sharpe {br[2]:.2f}")
print(f"  [벤치] 동일가중 BH   ret {er[0]*100:+8.0f}% MDD {er[1]*100:5.0f}% Sharpe {er[2]:.2f}")

results = []
for lb in (30,60,90):
    for topk in (1,3,5):
        for reb in (7,30):
            for af in ("none","sma","pos"):
                e = rotation(lb, topk, reb, af)
                r,m,sh = stats(e); results.append((f"lb{lb} top{topk} reb{reb}d {af}", r,m,sh))
results.sort(key=lambda x:-x[3])
print("\n  --- 로테이션 상위 15 (Sharpe) ---")
for name,r,m,sh in results[:15]:
    star = "★" if r > br[0] else " "
    print(f"  {star} {name:<24} ret {r*100:+9.0f}% MDD {m*100:5.0f}% Sharpe {sh:.2f}")
print(f"\n  로테이션 중 BTC BH(ret) 초과: {sum(1 for _,r,_,_ in results if r>br[0])}/{len(results)}")
print(f"  로테이션 중 BTC BH(Sharpe) 초과: {sum(1 for _,_,_,sh in results if sh>br[2])}/{len(results)}")
print("\n판정: 로테이션 다수가 BTC BH(Sharpe·ret) 넘으면 → '강한코인 갈아타기'가 진짜 엣지. 소수면 과적합/생존편향.")
