#!/usr/bin/env python3
"""BowlNo3_256.pine 의 로직(256 기법 + 1년 밥그릇 3번 흔들기)을 봉 단위로 재현해 로컬에서 검증한다.

Pine 런타임은 로컬에 없으므로 이 스크립트는 .pine 파일을 실행하지 않는다.
BowlNo3_256.pine 과 같은 계산을 파이썬으로 다시 구현한 것이므로,
어디까지나 "로직 설계"의 검증이지 "Pine 코드 자체"의 검증은 아니다.
두 구현이 갈라질 수 있으니 신호 날짜는 반드시 차트와 대조할 것.

데이터: TradingView 차트 → 우상단 메뉴 → "Export chart data..." 로 받은 CSV.

사용법:
    python3 tools/bowl_check.py data/AAPL.csv
    python3 tools/bowl_check.py data/*.csv --sweep
    python3 tools/bowl_check.py data/AAPL.csv --min-accum 40 --accum-ratio 1.5

표준 라이브러리만 사용한다 (설치 불필요).
"""

import argparse
import csv
import sys
from datetime import datetime

# ── Pine 기본값과 동일하게 유지할 것 ──────────────────────────────
DEFAULTS = dict(
    ma224_len=224,   # Pine 기본값과 동기화
    ma20_len=20,
    ma5_len=5,
    vol_mult=1.5,
    vol_window=10,
    flat_len=20,
    new_low_tol_pct=5.0,
    min_accum_bars=80,     # 이미지 "2번 기간 조정 최소 4개월" ≈ 84 거래일
    min_drop_pct=30.0,     # 1번 가격 조정: 하락 전 고점 대비 최소 낙폭
    drop_lookback=250,     # 하락 전 고점 탐색 기간 (224선 이탈 시점 기준)
    min_runup_pct=10.0,    # 3번 흔들기: 돌파 후 224선 위로 이만큼 올라가야 눌림 인정
    target1_pct=50.0,      # 4번 급등 목표
    target2_pct=100.0,
    accum_ratio=1.0,
    max_pullback_wait=30,
    pullback_tol_pct=3.0,
    fail_tol_pct=3.0,
    bounce_left=3,         # 쌍바닥 피벗 저점 감지
    bounce_right=3,
    # ── 256 기법 (이미지 4: 밥그릇 2번 끝단부 = 3번 상승 초입) ──
    sig_mode="단기",       # 단기 = 5/20/60, 중장기 = 5/112/224
    db_recent=10,          # 두 번째 바닥 = 최근 이 봉수의 최저가
    db_window=60,          # 첫 번째 바닥은 이 봉수 안의 피벗 저점
    db_tol_pct=3.0,        # 두 번째 바닥이 첫 번째보다 이 % 넘게 낮으면 쌍바닥 아님
    db_rise_pct=10.0,      # 두 번째 바닥이 이 % 넘게 높으면 "바닥"이 아님
)

FORWARD_HORIZONS = (5, 10, 20, 40)


# ══════════════════════════════════════════════════════════════
# CSV 읽기 (TradingView export 포맷에 관대하게)
# ══════════════════════════════════════════════════════════════
def _find_col(header, *candidates):
    lowered = {h.strip().lower(): h for h in header}
    for cand in candidates:
        if cand in lowered:
            return lowered[cand]
    # 부분 일치 (예: "Volume MA" 말고 "volume" 우선)
    for cand in candidates:
        for key, orig in lowered.items():
            if key == cand or key.startswith(cand):
                return orig
    return None


def _parse_time(raw):
    raw = raw.strip()
    # unix seconds
    try:
        n = int(float(raw))
        if n > 10_000_000:
            return datetime.utcfromtimestamp(n)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=None)
        except ValueError:
            continue
    raise ValueError(f"시간 형식을 알 수 없음: {raw!r}")


def read_csv(path):
    """→ (times, o, h, l, c, v) 오름차순 정렬된 리스트들"""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise SystemExit(f"{path}: 빈 파일")

    header = list(rows[0].keys())
    col_t = _find_col(header, "time", "date", "datetime")
    col_o = _find_col(header, "open")
    col_h = _find_col(header, "high")
    col_l = _find_col(header, "low")
    col_c = _find_col(header, "close")
    col_v = _find_col(header, "volume", "vol")

    missing = [n for n, c in
               [("time", col_t), ("open", col_o), ("high", col_h),
                ("low", col_l), ("close", col_c), ("volume", col_v)] if c is None]
    if missing:
        raise SystemExit(f"{path}: 필요한 열을 못 찾음 {missing}\n  실제 열: {header}")

    bars = []
    for r in rows:
        try:
            bars.append((
                _parse_time(r[col_t]),
                float(r[col_o]), float(r[col_h]),
                float(r[col_l]), float(r[col_c]), float(r[col_v] or 0),
            ))
        except (ValueError, TypeError):
            continue  # 빈 줄이나 지표 열만 있는 줄은 건너뛴다

    bars.sort(key=lambda b: b[0])
    return tuple(zip(*bars))


# ══════════════════════════════════════════════════════════════
# Pine 내장함수 재현
# ══════════════════════════════════════════════════════════════
def sma(src, length):
    """ta.sma — 앞쪽 length-1 개는 None"""
    out, total = [], 0.0
    for i, v in enumerate(src):
        total += v
        if i >= length:
            total -= src[i - length]
        out.append(total / length if i >= length - 1 else None)
    return out


def lowest(src, length):
    """ta.lowest — 현재 봉 포함 최근 length 봉의 최저"""
    return [min(src[max(0, i - length + 1): i + 1]) if i >= length - 1 else None
            for i in range(len(src))]


def highest(src, length):
    """ta.highest — 현재 봉 포함 최근 length 봉의 최고"""
    return [max(src[max(0, i - length + 1): i + 1]) if i >= length - 1 else None
            for i in range(len(src))]


def rolling_sum(src, length):
    """math.sum"""
    out, total = [], 0.0
    for i, v in enumerate(src):
        total += v
        if i >= length:
            total -= src[i - length]
        out.append(total)
    return out


def pivot_low(low, left, right):
    """ta.pivotlow — 봉 t 에서 알 수 있는 피벗 저점 값 (없으면 None).

    후보는 t-right 봉이며, 좌우 이웃보다 엄격히 낮아야 한다.
    (Pine 구현의 동률 처리와 미세하게 다를 수 있음)
    """
    n = len(low)
    out = [None] * n
    for t in range(n):
        i = t - right
        if i - left < 0 or i < 0:
            continue
        cand = low[i]
        if all(cand < low[j] for j in range(i - left, i)) and \
           all(cand < low[j] for j in range(i + 1, i + right + 1)):
            out[t] = cand
    return out


# ══════════════════════════════════════════════════════════════
# BowlNo3_256 로직 재현
# ══════════════════════════════════════════════════════════════
def run_bowl(data, p):
    times, o, h, l, c, v = data
    n = len(c)

    ma5 = sma(c, p["ma5_len"])
    ma20 = sma(c, p["ma20_len"])
    ma224 = sma(c, p["ma224_len"])
    hh_drop = highest(h, p["drop_lookback"])

    flat_len = p["flat_len"]
    low_flat = lowest(l, flat_len)

    mid_len, trend_len = (20, 60) if p["sig_mode"] == "단기" else (112, 224)
    ma_mid = sma(c, mid_len)          # 256 의 "2" — 20일선(단기) / 112일선(중장기)
    ma_trend = sma(c, trend_len)      # 256 의 "6" — 60일선(단기) / 224일선(중장기)
    piv_low = pivot_low(l, p["bounce_left"], p["bounce_right"])
    # 쌍바닥 창은 단기(20일선) 기준 값이다. 중장기는 모든 구간이 112/20 = 5.6배 길므로
    # 같은 비율로 늘린다 — 안 늘리면 두 바닥 간격이 창을 넘어 중장기 쌍바닥을 못 잡는다.
    db_scale = mid_len / 20
    db_recent = round(p["db_recent"] * db_scale)
    db_window = round(p["db_window"] * db_scale)
    db_low = lowest(l, db_recent)
    stretch_hist = [None] * n

    # ── 상태 변수 (Pine 의 var 에 대응) ──
    bars_below = 0
    stretch_start = stretch_low = bottom_entry_bar = stretch_peak = None
    accum_vol_sum, accum_vol_cnt = 0.0, 0
    stage = 0
    breakout_bar = None
    ran_up = False
    bo_decline = bo_accum = 0

    breakouts, buys, rejects = [], [], []

    last_pl = last_pl_bar = prev_pl = prev_pl_bar = None
    pos256 = 0            # 0=없음, 1=매수구간(20선 손절), 2=수익구간(60선 돌파 후)
    buys256, stops256, profits256, exits256 = [], [], [], []

    for i in range(n):
        if piv_low[i] is not None:
            prev_pl, prev_pl_bar = last_pl, last_pl_bar
            last_pl, last_pl_bar = piv_low[i], i - p["bounce_right"]
        if ma224[i] is None or ma20[i] is None or ma5[i] is None:
            continue

        is_below = c[i] < ma224[i]
        bars_below = bars_below + 1 if is_below else 0

        if is_below:
            # 경계는 "바닥권 진입 봉". 하락은 누적이라 봉 단위 갱신폭이 아니라
            # 윈도우로 비교해야 한다. 비교 기준은 "flat_len 봉 전까지의 바닥(스트레치
            # 최저가)"이다. 예전엔 직전 윈도우 저점과 비교해서, 바닥 위에서 5% 넘게
            # 되밀린 것(2번 끝단부의 쌍바닥)도 "아직 하락 중"으로 보고 매집 기간을 0으로
            # 리셋했다 — 256 골든크로스 시점에 매집 조건이 깨지던 원인.
            if p.get("_legacy_falling") or bars_below <= flat_len:
                prior = low_flat[i - flat_len] if i >= flat_len else None
            else:
                prior = stretch_hist[i - flat_len]
            still_falling = (prior is not None and low_flat[i] is not None
                             and low_flat[i] < prior * (1 - p["new_low_tol_pct"] / 100))

            if bars_below == 1 or stretch_low is None:
                stretch_start, stretch_low, bottom_entry_bar = i, l[i], i
                stretch_peak = hh_drop[i]     # 224선 이탈 시점까지의 고점 = 1번 출발점
                accum_vol_sum, accum_vol_cnt = 0.0, 0
            else:
                if l[i] < stretch_low:
                    stretch_low = l[i]
                if still_falling:
                    bottom_entry_bar = i          # 아직 하락 중 → 매집 시작점을 뒤로
                    accum_vol_sum, accum_vol_cnt = 0.0, 0

            accum_vol_sum += v[i]
            accum_vol_cnt += 1

        stretch_hist[i] = stretch_low
        decline_bars = 0 if (bottom_entry_bar is None or stretch_start is None) \
            else bottom_entry_bar - stretch_start
        accum_bars = 0 if bottom_entry_bar is None else i - bottom_entry_bar

        # ── 3번 1단계: 224선 돌파 ──
        crossed = (i > 0 and ma224[i - 1] is not None
                   and c[i - 1] <= ma224[i - 1] and c[i] > ma224[i])
        # 매집 기간 평균 대비. 직전 20봉 평균과 비교하면 랠리가 평균을 끌어올려 무력화된다.
        # 또한 교차봉 한 봉만 보면 안 된다 — 거래량이 터지는 봉과 종가가 224선을
        # 넘는 봉은 일치할 이유가 없다. 최근 vol_window 봉 중 최대치로 판정한다.
        accum_vol_avg = accum_vol_sum / accum_vol_cnt if accum_vol_cnt else None
        vol_recent = max(v[max(0, i - p["vol_window"] + 1): i + 1])
        vol_spike = accum_vol_avg is not None and vol_recent > accum_vol_avg * p["vol_mult"]
        pass_len = accum_bars >= p["min_accum_bars"]
        pass_ratio = accum_bars >= decline_bars * p["accum_ratio"]
        drop_pct = ((stretch_peak - stretch_low) / stretch_peak * 100
                    if stretch_peak and stretch_low is not None else 0.0)
        pass_drop = drop_pct >= p["min_drop_pct"]

        # ── 256 기법: 밥그릇 2번 끝단부에서 역배열 + 짝궁뎅이 쌍바닥 + 5/20 골든크로스 ──
        if ma_mid[i] is not None and ma_trend[i] is not None and ma_mid[i - 1] is not None:
            if last_pl_bar is not None and last_pl_bar < i - db_recent:
                first, fbar = last_pl, last_pl_bar
            else:
                first, fbar = prev_pl, prev_pl_bar
            double_bottom = (first is not None and i - fbar <= db_window
                             and first * (1 - p["db_tol_pct"] / 100) <= db_low[i]
                             <= first * (1 + p["db_rise_pct"] / 100))
            gc = ma5[i - 1] <= ma_mid[i - 1] and ma5[i] > ma_mid[i]
            reverse = ma_mid[i] < ma_trend[i]
            bowl_ctx = is_below and pass_len and pass_ratio and pass_drop

            if pos256 == 0 and gc and reverse and double_bottom and bowl_ctx:
                pos256 = 1
                buys256.append(dict(i=i, date=times[i], price=c[i], first=first,
                                    second=db_low[i], accum=accum_bars))
            elif pos256 == 1:
                if c[i] < ma_mid[i]:
                    pos256 = 0
                    stops256.append(dict(i=i, date=times[i]))
                elif c[i] > ma_trend[i]:
                    pos256 = 2
                    profits256.append(dict(i=i, date=times[i]))
            elif pos256 == 2 and c[i] < ma_trend[i]:
                pos256 = 0
                exits256.append(dict(i=i, date=times[i]))

        if crossed and stage == 0:
            if vol_spike and pass_len and pass_ratio and pass_drop:
                stage, breakout_bar, ran_up = 1, i, False
                bo_decline, bo_accum = decline_bars, accum_bars
                breakouts.append(dict(i=i, date=times[i], price=c[i],
                                      accum=accum_bars, decline=decline_bars,
                                      drop=drop_pct))
            else:
                why = []
                if not vol_spike:
                    why.append("거래량")
                if not pass_len:
                    why.append(f"매집길이({accum_bars}<{p['min_accum_bars']})")
                if not pass_ratio:
                    why.append(f"매집<급락({accum_bars}<{decline_bars})")
                if not pass_drop:
                    why.append(f"낙폭({drop_pct:.0f}%<{p['min_drop_pct']:.0f}%)")
                rejects.append(dict(date=times[i], why="+".join(why)))

        # ── 3번 2단계: 눌림목 진입 ──
        buy = False
        # 흔들기 = 먼저 224선 위로 충분히 올라간 뒤(ran_up) 224선까지 눌리는 것.
        # ran_up 은 "이전 봉까지"의 값을 쓴다 — 돌파 직후 224선 +3% 안에 있는
        # 첫 양봉이 곧바로 눌림으로 잡히던 버그(합성 23/23건 돌파 다음 봉 BUY)의 수정.
        if stage == 1 and i > breakout_bar and ran_up:
            near = l[i] <= ma224[i] * (1 + p["pullback_tol_pct"] / 100)
            if near and c[i] > ma224[i] and c[i] > o[i]:
                buy = True
        if stage == 1 and h[i] >= ma224[i] * (1 + p["min_runup_pct"] / 100):
            ran_up = True

        if buy:
            buys.append(dict(i=i, date=times[i], price=c[i], stop=l[i],
                             accum=bo_accum, decline=bo_decline,
                             wait=i - breakout_bar))
            stage = 2
        elif stage == 1:
            if c[i] < ma224[i] * (1 - p["fail_tol_pct"] / 100):
                stage = 0
            elif i - breakout_bar > p["max_pullback_wait"]:
                stage = 0
        elif stage == 2 and is_below:
            stage = 0

    # ── 진입 후 성과 (평가용, 실시간 로직 아님) ──
    for b in buys:
        i = b["i"]
        b["fwd"] = {}
        for hz in FORWARD_HORIZONS:
            j = min(i + hz, n - 1)
            b["fwd"][hz] = (c[j] - b["price"]) / b["price"] * 100
        stop_hit = None
        for j in range(i + 1, min(i + max(FORWARD_HORIZONS) + 1, n)):
            if c[j] < b["stop"]:
                stop_hit = j - i
                break
        b["stop_hit"] = stop_hit
        for key, pct in (("t1", p["target1_pct"]), ("t2", p["target2_pct"])):
            b[key] = next((j - i for j in range(i + 1, n)
                           if h[j] >= b["price"] * (1 + pct / 100)), None)

    return dict(bars=n, span=(times[0], times[-1]), params=p,
                breakouts=breakouts, buys=buys, rejects=rejects,
                buys256=buys256, stops256=stops256, profits256=profits256, exits256=exits256)


# ══════════════════════════════════════════════════════════════
# 출력
# ══════════════════════════════════════════════════════════════
def fmt_date(d):
    return d.strftime("%Y-%m-%d")


def report(name, res):
    print(f"\n{'=' * 62}\n{name}   {res['bars']}봉  "
          f"{fmt_date(res['span'][0])} ~ {fmt_date(res['span'][1])}\n{'=' * 62}")

    print(f"\n224선 돌파 통과: {len(res['breakouts'])}건")
    for b in res["breakouts"]:
        print(f"  {fmt_date(b['date'])}  {b['price']:>10,.2f}   "
              f"매집 {b['accum']:>3}봉 / 급락 {b['decline']:>3}봉 / 낙폭 {b['drop']:.0f}%")

    if res["rejects"]:
        print(f"\n돌파했으나 탈락: {len(res['rejects'])}건")
        reasons = {}
        for r in res["rejects"]:
            reasons[r["why"]] = reasons.get(r["why"], 0) + 1
        for why, cnt in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"  {cnt:>3}회  {why}")

    b256 = res["buys256"]
    print(f"\n256 매수 신호 ({res['params']['sig_mode']}): {len(b256)}건  "
          f"손절 {len(res['stops256'])} / 수익구간 진입 {len(res['profits256'])} / "
          f"수익 실현 {len(res['exits256'])}")
    for b in b256:
        print(f"  {fmt_date(b['date'])}  {b['price']:>10,.2f}   쌍바닥 {b['first']:,.2f} → "
              f"{b['second']:,.2f}   매집 {b['accum']}봉")

    buys = res["buys"]
    print(f"\n3번 흔들기 매수 신호: {len(buys)}건")
    if not buys:
        print("  (없음)")
        return

    hdr = "  " + " ".join(f"{f'+{hz}봉':>8}" for hz in FORWARD_HORIZONS)
    print(f"  {'날짜':<12}{'진입가':>11}{'대기':>5}{hdr}   손절")
    for b in buys:
        fwd = " ".join(f"{b['fwd'][hz]:>+7.1f}%" for hz in FORWARD_HORIZONS)
        stop = f"{b['stop_hit']}봉후" if b["stop_hit"] else "-"
        print(f"  {fmt_date(b['date']):<12}{b['price']:>11,.2f}{b['wait']:>4}봉  "
              f"{fwd}   {stop}")

    for hz in FORWARD_HORIZONS:
        rets = [b["fwd"][hz] for b in buys]
        wins = sum(1 for r in rets if r > 0)
        print(f"  +{hz:>2}봉 평균 {sum(rets) / len(rets):>+6.1f}%   "
              f"승률 {wins}/{len(rets)}")
    stopped = sum(1 for b in buys if b["stop_hit"])
    print(f"  손절 도달 {stopped}/{len(buys)}")
    for key, pct in (("t1", "target1_pct"), ("t2", "target2_pct")):
        hit = [b[key] for b in buys if b[key] is not None]
        print(f"  4번 +{res['params'][pct]:.0f}% 도달 {len(hit)}/{len(buys)}"
              + (f"  (평균 {sum(hit) / len(hit):.0f}봉)" if hit else ""))


def sweep(datasets, base):
    """minAccumBars × accumRatio 격자를 훑어 기본값 후보를 찾는다."""
    print(f"\n{'=' * 62}\n파라미터 스윕 (전 종목 합산)\n{'=' * 62}")
    print(f"  {'최소매집':>8}{'비율':>7}{'돌파':>6}{'매수':>6}"
          f"{'+20봉평균':>11}{'승률':>8}")
    for min_accum in (20, 30, 40, 60, 80):
        for ratio in (0.8, 1.0, 1.5, 2.0):
            p = dict(base, min_accum_bars=min_accum, accum_ratio=ratio)
            all_buys, n_bo = [], 0
            for _, data in datasets:
                r = run_bowl(data, p)
                all_buys += r["buys"]
                n_bo += len(r["breakouts"])
            if all_buys:
                rets = [b["fwd"][20] for b in all_buys]
                avg = sum(rets) / len(rets)
                win = sum(1 for r in rets if r > 0)
                stat = f"{avg:>+10.1f}%{win:>5}/{len(rets):<3}"
            else:
                stat = f"{'-':>11}{'-':>8}"
            print(f"  {min_accum:>8}{ratio:>7.1f}{n_bo:>6}{len(all_buys):>6}{stat}")


# ══════════════════════════════════════════════════════════════
# 자가 검증 — 정답을 아는 합성 밥그릇으로 로직 회귀를 잡는다
# ══════════════════════════════════════════════════════════════
SYNTH = dict(pre=260, decline=40, accum=150, runup=15.0, rise=60)


def _synthetic(seed=7, shake=True, decline_drift=-0.012):
    """이미지의 밥그릇 모양을 그대로 만든다.
    상승 → 1번 급락 → 2번 긴 바닥 → 3번 224선 돌파 후 흔들기(224선까지 되밀림) → 4번 급등.

    예전 생성기는 바닥이 90봉으로 짧아 돌파 랠리가 224선을 못 넘거나(seed 3),
    눌림이 224선까지 안 내려와 흔들기를 검증할 수 없었다. 이제는 224선을 실시간으로
    계산해 "224선 +runup% 까지 랠리 → 224선 +1% 까지 되밀림"을 목표값으로 만든다.
    """
    import math
    import random
    rnd = random.Random(seed)
    t0 = datetime(2022, 1, 3)
    times, o, h, l, c, v = [], [], [], [], [], []
    st = dict(price=100.0, day=0)

    def ma224():
        w = c[-224:]
        return sum(w) / len(w)

    def bar(drift=0.0, vol_mult=1.0):
        op = st["price"]
        cl = op * (1 + drift + rnd.gauss(0, 0.008))
        times.append(datetime.fromordinal(t0.toordinal() + st["day"]))
        o.append(op)
        h.append(max(op, cl) * (1 + abs(rnd.gauss(0, 0.005))))
        l.append(min(op, cl) * (1 - abs(rnd.gauss(0, 0.005))))
        c.append(cl)
        v.append(1_000_000 * vol_mult * (1 + abs(rnd.gauss(0, 0.3))))
        st["price"], st["day"] = cl, st["day"] + 1

    for _ in range(SYNTH["pre"]):
        bar(0.0012)
    for _ in range(SYNTH["decline"]):
        bar(decline_drift)
    base = st["price"]
    for i in range(SYNTH["accum"]):
        tgt = base * (1 + math.sin(i / 7) * 0.02 + (i / SYNTH["accum"]) * 0.04)
        bar((tgt - st["price"]) / st["price"] * 0.4)
    for _ in range(60):                              # 3번: 거래량 실은 돌파 랠리
        if st["price"] >= ma224() * (1 + SYNTH["runup"] / 100):
            break
        bar(0.025, vol_mult=3.0)
    if shake:                                        # 3번: 흔들기
        for _ in range(30):
            if st["price"] <= ma224() * 1.01:
                break
            bar(-0.015)
        for _ in range(3):
            bar(0.0)
    for _ in range(SYNTH["rise"]):                   # 4번: 급등
        bar(0.012, vol_mult=1.5)

    return (times, o, h, l, c, v)


def _synthetic256(seed=0, kind="ok", mode="단기"):
    """이미지 4 (256 기법): 1번 급락 → 2번 바닥 → 2번 끝단부에서 바닥 위로 올랐다가 되밀리며
    짝궁뎅이 쌍바닥 → 5일선이 20일선 골든크로스(20 < 60 역배열) → 20선 눌림 → 60선 돌파(수익구간).

    kind: ok / stop(골든크로스 후 20선 이탈) / lowerlow(두 번째 바닥이 더 낮음)
          / noreverse(바닥에서 계속 올라와 20 > 60) / shallow(1번 낙폭 부족)
    mode: 중장기면 "20→112, 60→224" 에 맞게 256 파동(고원·쌍바닥·골든크로스)의 길이를
          5.6배로 늘린다. 밥그릇 자체(급락·바닥)는 두 모드 모두 224선 기준이라 그대로 둔다
          — 바닥까지 늘리면 바닥 도중에 224선이 내려와 주가를 넘어 2번이 끝나 버린다.
    """
    import math
    import random
    rnd = random.Random(seed)
    k = 1 if mode == "단기" else 5.6
    mid_len, trend_len = (20, 60) if mode == "단기" else (112, 224)
    t0 = datetime(2022, 1, 3)
    times, o, h, l, c, v = [], [], [], [], [], []
    st = dict(p=100.0)

    def bar(cl, vm=1.0):
        op = st["p"]
        cl *= 1 + rnd.gauss(0, 0.003)
        times.append(datetime.fromordinal(t0.toordinal() + len(c)))
        o.append(op)
        c.append(cl)
        h.append(max(op, cl) * (1 + abs(rnd.gauss(0, 0.003))))
        l.append(min(op, cl) * (1 - abs(rnd.gauss(0, 0.003))))
        v.append(1e6 * vm)
        st["p"] = cl

    def leg(tgt, n):
        s0, n = st["p"], max(1, round(n * k))
        for j in range(1, n + 1):
            bar(s0 + (tgt - s0) * j / n)

    def avg(n):
        return sum(c[-n:]) / n

    for _ in range(300):
        bar(st["p"] * 1.0012)
    s0 = st["p"]
    for j in range(1, 41):                                         # 1번 급락
        bar(s0 + (s0 * (0.85 if kind == "shallow" else 0.6) - s0) * j / 40)
    B = st["p"]
    for i in range(90):                                            # 2번 바닥 (바닥선 B)
        bar(B * (1.02 + math.sin(i / 5) * 0.02))
    if kind == "noreverse":                                        # 바닥에서 계속 올라옴
        leg(B * 1.15, 50)
        leg(B * 1.10, 6)
        leg(B * 1.13, 5)
        leg(B * 1.105, 5)
    else:                                                          # 2번 끝단부
        # 바닥 위로 오르되 224선 아래에 머문다 — 넘으면 밥그릇 2번이 끝나 버린다.
        # (중장기는 바닥이 길어 224선이 B×1.10 근처까지 내려와 있다)
        top = min(B * 1.16, avg(224) * 0.97)
        leg(top, 15)
        for _ in range(round(25 * k)):
            bar(min(top, avg(224) * 0.97))
        leg(B * 1.00, 12)                                          # 쌍바닥 ①
        leg(B * 1.035, 5)
        leg(B * (0.88 if kind == "lowerlow" else 1.02), 6)         # 쌍바닥 ② (짝궁뎅이)
    for _ in range(round(30 * k)):                                 # 5일선이 20일선 골든크로스
        if avg(5) > avg(mid_len) * 1.01:
            break
        bar(st["p"] * (1 + 0.012 / k), 2.0)
    if kind == "stop":
        leg(avg(mid_len) * 0.9, 10)                                # 20선 이탈 → 손절
        return (times, o, h, l, c, v)
    for _ in range(round(40 * k)):                                 # 60선 바로 아래까지
        if st["p"] >= avg(trend_len) * 0.98:
            break
        bar(st["p"] * (1 + 0.01 / k))
    for _ in range(round(20 * k)):                                 # 20선 눌림
        if st["p"] <= avg(mid_len) * 1.01:
            break
        bar(st["p"] * (1 - 0.008 / k))
    for _ in range(round(60 * k)):                                 # 60선 돌파 → 수익구간
        if st["p"] >= avg(trend_len) * 1.08:
            break
        bar(st["p"] * (1 + 0.012 / k))
    leg(st["p"] * 1.05, 5)
    leg(avg(trend_len) * 0.95, 12)                                 # 60선 아래로 → 수익 실현
    return (times, o, h, l, c, v)


def selftest256():
    """256 기법 (이미지 4) — 단기 모드는 패턴별로, 중장기 모드는 밥그릇 합성과의 정합성으로 본다."""
    fails, rows = [], []
    P = dict(DEFAULTS, sig_mode="단기")

    def runs(kind, params=P):
        return [run_bowl(_synthetic256(s, kind), params) for s in range(10)]

    ok = runs("ok")
    good = sum(bool(r["buys256"]) and bool(r["profits256"]) and bool(r["exits256"])
               and not r["stops256"] for r in ok)
    legacy = sum(bool(r["buys256"]) for r in runs("ok", dict(P, _legacy_falling=True)))
    rows.append(f"  정상 (쌍바닥→골든크로스→20선 눌림→60 돌파): BUY→수익구간→수익실현 {good}/10"
                f"  (예전 하락 지속 판정이면 BUY {legacy}/10)")
    if good < 10:
        fails.append(f"정상 패턴 {good}/10")

    stop = runs("stop")
    n = sum(bool(r["buys256"]) and bool(r["stops256"]) and not r["profits256"] for r in stop)
    rows.append(f"  골든크로스 후 20선 이탈: BUY→손절 {n}/10")
    if n < 10:
        fails.append(f"손절 패턴 {n}/10")

    for kind, label in (("lowerlow", "두 번째 바닥이 더 낮음(쌍바닥 아님)"),
                        ("shallow", "1번 낙폭 부족(밥그릇 아님)")):
        n = sum(len(r["buys256"]) for r in runs(kind))
        rows.append(f"  {label}: BUY {n}건 (0 이어야 함)")
        if n:
            fails.append(f"{label} BUY {n}건")

    # 바닥에서 계속 올라와 20 > 60 인 상태의 골든크로스는 걸러야 한다.
    # 상승 시작점(바닥 끝, 430봉) 근처의 BUY 는 20<60 이 실제로 성립한 정당한 자리라 제외.
    late = sum(1 for r in runs("noreverse") for b in r["buys256"] if b["i"] >= 470)
    rows.append(f"  상승 후(20>60) 골든크로스: BUY {late}건 (0 이어야 함)")
    if late:
        fails.append(f"역배열 아닌 골든크로스 BUY {late}건")

    # 중장기(5/112/224): 256 의 수익구간 = 224 돌파 = 밥그릇 3번 시작이어야 한다.
    PL = dict(DEFAULTS, sig_mode="중장기")
    reached, mismatched = 0, []
    for s in range(10):
        r = run_bowl(_synthetic(s), PL)
        bo = [b["i"] for b in r["breakouts"]]
        for pr in r["profits256"]:
            reached += 1
            if not any(abs(pr["i"] - x) <= 3 for x in bo):
                mismatched.append(s)
    rows.append(f"  중장기: 256 BUY 가 224 돌파까지 이어진 seed {reached}/10, "
                f"그 돌파가 밥그릇 3번 돌파와 어긋난 경우 {len(mismatched)}건")
    if mismatched:
        fails.append(f"중장기 수익구간이 3번 돌파와 어긋남: seed {mismatched}")
    if reached < 4:
        fails.append(f"중장기 256 → 224 돌파 {reached}/10 < 4/10")
    return fails, rows


def selftest():
    """정답을 아는 패턴으로 구간 분리·신호 발생, 그리고 걸러야 할 패턴의 탈락을 확인한다."""
    fails = []
    tol = DEFAULTS["flat_len"]   # 윈도우 방식이라 경계에 flatLen 정도의 지연이 있다

    # ① 정상 밥그릇 — 여러 seed 에서 돌파 1건, 흔들기 뒤 BUY 1건
    waits = []
    for seed in range(10):
        data = _synthetic(seed)
        res = run_bowl(data, DEFAULTS)
        if len(res["breakouts"]) != 1:
            fails.append(f"seed {seed}: 돌파 1건이어야 하는데 {len(res['breakouts'])}건")
            continue
        b = res["breakouts"][0]
        for label, got, want in (("급락", b["decline"], SYNTH["decline"]),
                                 ("매집", b["accum"], SYNTH["accum"])):
            if abs(got - want) > tol:
                fails.append(f"seed {seed}: {label} {got}봉, 주입값 {want}봉 (허용 ±{tol})")
        if not res["buys"]:
            fails.append(f"seed {seed}: 흔들기 뒤 눌림목 BUY 가 안 잡힘")
            continue
        buy = res["buys"][0]
        # BUY 전에 224선 위로 min_runup_pct 이상 올라간 적이 있어야 한다
        h, c = data[2], data[4]
        ma = sma(c, DEFAULTS["ma224_len"])
        bo = b["i"]
        runup = max((h[j] - ma[j]) / ma[j] * 100 for j in range(bo, buy["i"]))
        if runup < DEFAULTS["min_runup_pct"]:
            fails.append(f"seed {seed}: BUY 전 상승폭 {runup:.1f}% — 흔들기 전에 샀음")
        waits.append(buy["wait"])

    # ② 흔들기 없이 곧장 급등 — 3번 자리가 없으므로 BUY 가 나오면 안 된다
    for seed in range(10):
        res = run_bowl(_synthetic(seed, shake=False), DEFAULTS)
        if res["buys"]:
            fails.append(f"seed {seed}: 흔들기 없는 급등에서 BUY 발생 (대기 {res['buys'][0]['wait']}봉)")

    # ③ 얕은 하락(실측 낙폭 20%대) — 1번 가격 조정 미달이므로 돌파가 탈락해야 한다
    for seed in range(10):
        res = run_bowl(_synthetic(seed, decline_drift=-0.004), DEFAULTS)
        if res["breakouts"]:
            fails.append(f"seed {seed}: 얕은 하락인데 돌파 통과 (낙폭 {res['breakouts'][0]['drop']:.0f}%)")

    print("자가 검증 ① 3번 흔들기 (합성 밥그릇: 급락 {decline}봉 / 매집 {accum}봉 / 돌파 +{runup:.0f}% 후 흔들기)"
          .format(**SYNTH))
    if waits:
        print(f"  정상 패턴 돌파→BUY 대기: {sorted(waits)}봉")
    for f in fails:
        print(f"  ✗ {f}")
    if not fails:
        print("  ✓ 통과 — 정상 10건 BUY / 흔들기 없음 10건 무신호 / 얕은 하락 10건 탈락")

    f256, rows = selftest256()
    print("\n자가 검증 ② 256 기법 (2번 끝단부: 역배열 + 짝궁뎅이 쌍바닥 + 5/20 골든크로스)")
    print("\n".join(rows))
    for f in f256:
        print(f"  ✗ {f}")
    if not f256:
        print("  ✓ 통과")
    fails += f256
    return 0 if not fails else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", nargs="*", help="TradingView 에서 내보낸 CSV")
    ap.add_argument("--selftest", action="store_true",
                    help="합성 데이터로 로직 자가 검증 (CSV 불필요)")
    ap.add_argument("--sweep", action="store_true",
                    help="minAccumBars × accumRatio 격자 탐색")
    ap.add_argument("--min-accum", type=int, default=DEFAULTS["min_accum_bars"])
    ap.add_argument("--accum-ratio", type=float, default=DEFAULTS["accum_ratio"])
    ap.add_argument("--vol-mult", type=float, default=DEFAULTS["vol_mult"])
    ap.add_argument("--mode", choices=["단기", "중장기"], default=DEFAULTS["sig_mode"],
                    help="256 이평선 조합: 단기 5/20/60, 중장기 5/112/224")
    args = ap.parse_args()

    if args.selftest:
        raise SystemExit(selftest())
    if not args.csv:
        ap.error("CSV 를 지정하거나 --selftest 를 쓸 것")

    params = dict(DEFAULTS, min_accum_bars=args.min_accum,
                  accum_ratio=args.accum_ratio, vol_mult=args.vol_mult,
                  sig_mode=args.mode)

    datasets = []
    for path in args.csv:
        try:
            datasets.append((path.split("/")[-1], read_csv(path)))
        except SystemExit as e:
            print(e, file=sys.stderr)

    if not datasets:
        raise SystemExit("읽은 데이터 없음")

    for name, data in datasets:
        if len(data[0]) < params["ma224_len"] + 60:
            print(f"\n{name}: {len(data[0])}봉뿐 — 224일선 계산에 부족. "
                  f"최소 {params['ma224_len'] + 60}봉 이상 내보낼 것.", file=sys.stderr)
            continue
        report(name, run_bowl(data, params))

    if args.sweep:
        sweep(datasets, params)


if __name__ == "__main__":
    main()
