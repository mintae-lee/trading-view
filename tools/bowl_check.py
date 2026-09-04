#!/usr/bin/env python3
"""BowlNo3_256.pine 의 로직을 봉 단위로 재현해 로컬에서 검증한다.

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
    min_accum_bars=30,
    accum_ratio=1.0,
    max_pullback_wait=30,
    pullback_tol_pct=3.0,
    fail_tol_pct=3.0,
    bowl_len=60,
    min_bounces=2,
    bounce_left=3,
    bounce_right=3,
    floor_tol_pct=5.0,
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

    flat_len = p["flat_len"]
    low_flat = lowest(l, flat_len)

    bowl_len = p["bowl_len"]
    half = bowl_len // 2
    bowl_floor = lowest(l, bowl_len)
    piv_low = pivot_low(l, p["bounce_left"], p["bounce_right"])
    low_recent = lowest(l, half)

    is_bounce_num = []
    for i in range(n):
        pv, floor = piv_low[i], bowl_floor[i]
        ok = pv is not None and floor and (pv - floor) / floor * 100 <= p["floor_tol_pct"]
        is_bounce_num.append(1.0 if ok else 0.0)
    bounce_count = rolling_sum(is_bounce_num, bowl_len)

    # ── 상태 변수 (Pine 의 var 에 대응) ──
    bars_below = 0
    stretch_start = stretch_low = bottom_entry_bar = None
    accum_vol_sum, accum_vol_cnt = 0.0, 0
    stage = 0
    breakout_bar = None
    bo_decline = bo_accum = 0

    breakouts, buys, rejects = [], [], []

    for i in range(n):
        if ma224[i] is None or ma20[i] is None or ma5[i] is None:
            continue

        is_below = c[i] < ma224[i]
        bars_below = bars_below + 1 if is_below else 0

        if is_below:
            # 경계는 "바닥권 진입 봉". 하락은 누적이라 봉 단위 갱신폭이 아니라
            # 윈도우 대 윈도우로 비교해야 한다.
            prior = low_flat[i - flat_len] if i >= flat_len else None
            still_falling = (prior is not None and low_flat[i] is not None
                             and low_flat[i] < prior * (1 - p["new_low_tol_pct"] / 100))

            if bars_below == 1 or stretch_low is None:
                stretch_start, stretch_low, bottom_entry_bar = i, l[i], i
                accum_vol_sum, accum_vol_cnt = 0.0, 0
            else:
                if l[i] < stretch_low:
                    stretch_low = l[i]
                if still_falling:
                    bottom_entry_bar = i          # 아직 하락 중 → 매집 시작점을 뒤로
                    accum_vol_sum, accum_vol_cnt = 0.0, 0

            accum_vol_sum += v[i]
            accum_vol_cnt += 1

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

        if crossed and stage == 0:
            if vol_spike and pass_len and pass_ratio:
                stage, breakout_bar = 1, i
                bo_decline, bo_accum = decline_bars, accum_bars
                breakouts.append(dict(i=i, date=times[i], price=c[i],
                                      accum=accum_bars, decline=decline_bars))
            else:
                why = []
                if not vol_spike:
                    why.append("거래량")
                if not pass_len:
                    why.append(f"매집길이({accum_bars}<{p['min_accum_bars']})")
                if not pass_ratio:
                    why.append(f"매집<급락({accum_bars}<{decline_bars})")
                rejects.append(dict(date=times[i], why="+".join(why)))

        # ── 3번 2단계: 눌림목 진입 ──
        buy = False
        if stage == 1 and i > breakout_bar:
            near = l[i] <= ma224[i] * (1 + p["pullback_tol_pct"] / 100)
            if near and c[i] > ma224[i] and c[i] > o[i]:
                buy = True

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

    return dict(bars=n, span=(times[0], times[-1]),
                breakouts=breakouts, buys=buys, rejects=rejects,
                bounce_count=bounce_count)


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
              f"매집 {b['accum']:>3}봉 / 급락 {b['decline']:>3}봉")

    if res["rejects"]:
        print(f"\n돌파했으나 탈락: {len(res['rejects'])}건")
        reasons = {}
        for r in res["rejects"]:
            reasons[r["why"]] = reasons.get(r["why"], 0) + 1
        for why, cnt in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"  {cnt:>3}회  {why}")

    buys = res["buys"]
    print(f"\n눌림목 매수 신호: {len(buys)}건")
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
SYNTH = dict(pre=260, decline=40, accum=90, breakout=12, pullback=8, rise=40)


def _synthetic(seed=7):
    import math
    import random
    rnd = random.Random(seed)
    t0 = datetime(2022, 1, 3)
    times, o, h, l, c, v = [], [], [], [], [], []
    price, day = 100.0, 0

    def bar(p, vol_mult=1.0, drift=0.0):
        nonlocal day
        op = p
        cl = p * (1 + drift + rnd.gauss(0, 0.008))
        times.append(datetime.fromordinal(t0.toordinal() + day))
        o.append(op)
        h.append(max(op, cl) * (1 + abs(rnd.gauss(0, 0.005))))
        l.append(min(op, cl) * (1 - abs(rnd.gauss(0, 0.005))))
        c.append(cl)
        v.append(1_000_000 * vol_mult * (1 + abs(rnd.gauss(0, 0.3))))
        day += 1
        return cl

    for _ in range(SYNTH["pre"]):
        price = bar(price, drift=0.0012)
    for _ in range(SYNTH["decline"]):
        price = bar(price, drift=-0.012)
    base = price
    for i in range(SYNTH["accum"]):
        tgt = base * (1 + math.sin(i / 7) * 0.02 + (i / SYNTH["accum"]) * 0.04)
        price = bar(price, drift=(tgt - price) / price * 0.4)
    for _ in range(SYNTH["breakout"]):
        price = bar(price, vol_mult=3.0, drift=0.022)
    for _ in range(SYNTH["pullback"]):
        price = bar(price, drift=-0.010)
    for _ in range(SYNTH["rise"]):
        price = bar(price, vol_mult=1.5, drift=0.015)

    return (times, o, h, l, c, v)


def selftest():
    """정답을 아는 패턴 하나를 넣고 구간 분리·신호 발생을 확인한다."""
    res = run_bowl(_synthetic(), DEFAULTS)
    fails = []

    if len(res["breakouts"]) != 1:
        fails.append(f"돌파 1건이어야 하는데 {len(res['breakouts'])}건")
    if not res["buys"]:
        fails.append("눌림목 매수 신호가 안 잡힘")

    if res["breakouts"]:
        b = res["breakouts"][0]
        # 윈도우 방식이라 경계에 flatLen 정도의 지연이 있다 → 넉넉한 허용오차
        for label, got, want in (("급락", b["decline"], SYNTH["decline"]),
                                 ("매집", b["accum"], SYNTH["accum"])):
            if abs(got - want) > DEFAULTS["flat_len"]:
                fails.append(f"{label} 구간 {got}봉, 주입값 {want}봉 "
                             f"(허용 ±{DEFAULTS['flat_len']})")
        if b["accum"] <= b["decline"]:
            fails.append(f"매집({b['accum']})이 급락({b['decline']})보다 길어야 함")

    print("자가 검증 (합성 밥그릇: 급락 {decline}봉 / 매집 {accum}봉 주입)"
          .format(**SYNTH))
    if res["breakouts"]:
        b = res["breakouts"][0]
        print(f"  측정: 급락 {b['decline']}봉 / 매집 {b['accum']}봉")
    for f in fails:
        print(f"  ✗ {f}")
    if not fails:
        print("  ✓ 통과")
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
    args = ap.parse_args()

    if args.selftest:
        raise SystemExit(selftest())
    if not args.csv:
        ap.error("CSV 를 지정하거나 --selftest 를 쓸 것")

    params = dict(DEFAULTS, min_accum_bars=args.min_accum,
                  accum_ratio=args.accum_ratio, vol_mult=args.vol_mult)

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
