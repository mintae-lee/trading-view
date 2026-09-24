#!/usr/bin/env python3
"""ReverseCloud.pine 의 "V자 → 횡보 박스 → 224선 돌파" 표시 로직을 봉 단위로 재현해 검증한다.

bowl_check.py 와 같은 취지다 — Pine 코드 자체가 아니라 "로직 설계"의 검증이며,
두 구현이 갈라질 수 있으니 신호 날짜는 반드시 차트와 대조할 것.

패턴 = 224선 아래로 단기간에 크게 빠졌다가(V 왼쪽) 빠르게 되오르고(V 오른쪽),
       224선 아래에서 횡보 박스를 만든 뒤, 224선과 박스 상단을 함께 돌파.

사용법:
    python3 tools/vbox_check.py --selftest
    python3 tools/vbox_check.py data/*.csv

표준 라이브러리만 사용한다 (설치 불필요).
"""

import argparse
import random
import sys
from datetime import datetime

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from bowl_check import highest, lowest, pivot_low, read_csv, sma  # noqa: E402

# ── Pine 기본값과 동일하게 유지할 것 ──────────────────────────────
DEFAULTS = dict(
    long_len=224,
    v_pivot_len=5,          # V 바닥 = 좌우 이 봉수보다 낮은 피벗 저점
    v_drop_bars=30,         # 급락: 바닥까지 이 봉수 안의 최고가 대비
    v_drop_pct=25.0,        #       이 % 이상 빠져야 "급락"
    v_recover_bars=30,      # 급반등: 바닥 후 이 봉수 안에
    v_recover_ratio=50.0,   #         낙폭의 이 % 이상 되돌려야 "V"
    box_len=15,             # 박스: 최근 이 봉수의 고저 폭이
    box_max_pct=12.0,       #       이 % 이내면 횡보
    box_fail_pct=3.0,       # 박스 하단을 종가로 이 % 넘게 깨면 무효
    max_box_wait=60,        # V 완성 후 박스가 이 봉수 안에 안 나오면 무효
    max_box_bars=150,       # 박스 시작 후 이 봉수 안에 돌파 못 하면 무효
)


def run_vbox(data, p):
    times, o, h, l, c, v = data
    n = len(c)
    ma = sma(c, p["long_len"])
    pl = p["v_pivot_len"]
    piv = pivot_low(l, pl, pl)
    pre_high = highest(h, p["v_drop_bars"])
    box_hi = highest(h, p["box_len"])
    box_lo = lowest(l, p["box_len"])

    stage = 0          # 0=대기, 1=V 바닥(반등 대기), 2=V 완성(박스 대기), 3=박스(돌파 대기)
    v_low = v_low_bar = v_high = v_done_bar = None
    box_top = box_bot = box_start = None
    vs, boxes, breaks, fails = [], [], [], []

    for i in range(n):
        if ma[i] is None:
            continue
        j = i - pl                                  # 피벗이 찍힌 봉
        if (piv[i] is not None and j >= 0 and pre_high[j] is not None and ma[j] is not None
                and (pre_high[j] - piv[i]) / pre_high[j] * 100 >= p["v_drop_pct"]
                and piv[i] < ma[j] and stage != 3):
            stage, v_low, v_low_bar, v_high = 1, piv[i], j, pre_high[j]

        if stage == 1:
            if c[i] >= v_low + (v_high - v_low) * p["v_recover_ratio"] / 100:
                stage, v_done_bar = 2, i
                vs.append(dict(i=v_low_bar, done=i, date=times[v_low_bar], low=v_low, high=v_high))
            elif i - v_low_bar > p["v_recover_bars"]:
                stage = 0
        elif stage == 2:
            width = (box_hi[i] - box_lo[i]) / box_lo[i] * 100
            if i - v_done_bar >= p["box_len"] and width <= p["box_max_pct"] and c[i] < ma[i]:
                stage = 3
                box_top, box_bot, box_start = box_hi[i], box_lo[i], i - p["box_len"] + 1
                boxes.append(dict(i=i, start=box_start, top=box_top, bot=box_bot))
            elif i - v_done_bar > p["max_box_wait"]:
                stage = 0
        elif stage == 3:
            level = max(ma[i], box_top)
            if c[i] > level:
                stage = 0
                breaks.append(dict(i=i, date=times[i], price=c[i], box_top=box_top, ma=ma[i]))
            elif c[i] < box_bot * (1 - p["box_fail_pct"] / 100):
                stage = 0
                fails.append(dict(i=i, date=times[i], why="박스 하단 이탈"))
            elif i - box_start > p["max_box_bars"]:
                stage = 0
                fails.append(dict(i=i, date=times[i], why="박스 시간 초과"))

    return dict(bars=n, span=(times[0], times[-1]), vs=vs, boxes=boxes, breaks=breaks, fails=fails)


# ══════════════════════════════════════════════════════════════
# 합성 패턴
# ══════════════════════════════════════════════════════════════
def synth(seed=0, kind="ok"):
    """평평한 300봉(224선 ≈ 100) → V자 → 박스 → 224선 돌파.
    kind: ok / slow(완만한 U자 하락) / nobox(V 후 곧장 224 위로) /
          weak(반등이 약함, 데드캣) / boxfail(박스 하단 붕괴)"""
    rnd = random.Random(seed)
    t0 = datetime(2022, 1, 3)
    times, o, h, l, c, v = [], [], [], [], [], []
    st = dict(p=100.0)

    def bar(cl):
        op = st["p"]
        cl *= 1 + rnd.gauss(0, 0.003)
        times.append(datetime.fromordinal(t0.toordinal() + len(c)))
        o.append(op)
        c.append(cl)
        h.append(max(op, cl) * (1 + abs(rnd.gauss(0, 0.003))))
        l.append(min(op, cl) * (1 - abs(rnd.gauss(0, 0.003))))
        v.append(1e6)
        st["p"] = cl

    def leg(tgt, bars):
        s0 = st["p"]
        for k in range(1, bars + 1):
            bar(s0 + (tgt - s0) * k / bars)

    for _ in range(300):
        bar(100.0)
    if kind == "slow":
        leg(70, 150)                     # 완만한 하락 — 30봉 안의 낙폭은 6% 수준
        leg(86, 60)
    else:
        leg(70, 15)                      # V 왼쪽: 15봉에 -30%
        leg(75 if kind == "weak" else 86, 12)   # V 오른쪽
    if kind == "nobox":
        leg(108, 25)                     # 박스 없이 곧장 224 위로
        leg(112, 10)
        return (times, o, h, l, c, v)
    base = st["p"]
    for k in range(40):                  # 224선 아래 횡보 박스 (폭 ≈ 8%)
        bar(base * (1 + 0.035 * (1 if (k // 5) % 2 else -1)))
    if kind == "boxfail":
        leg(base * 0.85, 10)
        leg(base * 0.8, 10)
        return (times, o, h, l, c, v)
    leg(105, 10)                         # 224선 + 박스 상단 돌파
    for _ in range(10):
        bar(106)
    return (times, o, h, l, c, v)


def selftest():
    fails, rows = [], []
    N = 10
    expect = {"ok": 1, "slow": 0, "nobox": 0, "weak": 0, "boxfail": 0}
    label = {"ok": "V → 박스 → 224 돌파", "slow": "완만한 U자 하락(V 아님)",
             "nobox": "V 후 박스 없이 곧장 224 위로", "weak": "반등 약함(데드캣, V 미완성)",
             "boxfail": "박스 하단 붕괴"}
    for kind, want in expect.items():
        got = [len(run_vbox(synth(s, kind), DEFAULTS)["breaks"]) for s in range(N)]
        ok = sum(g == want for g in got)
        rows.append(f"  {label[kind]}: 돌파 신호 {got}  (기대 {want}건씩, 일치 {ok}/{N})")
        if ok < N:
            fails.append(f"{label[kind]} 일치 {ok}/{N}")

    # 정상 패턴에서 신호 봉이 실제로 224선과 박스 상단을 막 넘은 봉인지
    for s in range(N):
        d = synth(s, "ok")
        r = run_vbox(d, DEFAULTS)
        if r["breaks"]:
            b = r["breaks"][0]
            i, c = b["i"], d[4]
            ma = sma(c, DEFAULTS["long_len"])
            prev_level = max(ma[i - 1], b["box_top"])
            if not (c[i] > max(b["ma"], b["box_top"]) and c[i - 1] <= prev_level):
                fails.append(f"seed {s}: 신호 봉이 첫 돌파 봉이 아님")

    print("자가 검증 (합성: V자 → 224선 아래 횡보 박스 → 224선 돌파, 변형 4종 × 10 seed)")
    print("\n".join(rows))
    for f in fails:
        print(f"  ✗ {f}")
    if not fails:
        print("  ✓ 통과")
    return 0 if not fails else 1


def report(name, r):
    fmt = lambda d: d.strftime("%Y-%m-%d")
    print(f"\n{'=' * 60}\n{name}   {r['bars']}봉  {fmt(r['span'][0])} ~ {fmt(r['span'][1])}\n{'=' * 60}")
    print(f"V자 {len(r['vs'])} / 박스 {len(r['boxes'])} / 224 돌파 {len(r['breaks'])} / 무효 {len(r['fails'])}")
    for b in r["breaks"]:
        print(f"  {fmt(b['date'])}  {b['price']:>10,.2f}  (박스 상단 {b['box_top']:,.2f}, 224선 {b['ma']:,.2f})")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", nargs="*")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        raise SystemExit(selftest())
    if not args.csv:
        ap.error("CSV 를 지정하거나 --selftest 를 쓸 것")
    for path in args.csv:
        report(path.split("/")[-1], run_vbox(read_csv(path), DEFAULTS))


if __name__ == "__main__":
    main()
