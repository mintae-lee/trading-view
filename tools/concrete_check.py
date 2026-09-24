#!/usr/bin/env python3
"""ConcreteThrough.pine(하락후지지 돌파 = 공구리 기법)의 로직을 봉 단위로 재현해 검증한다.

bowl_check.py 와 같은 취지다 — Pine 코드 자체가 아니라 "로직 설계"의 검증이며,
두 구현이 갈라질 수 있으니 신호 날짜는 반드시 차트와 대조할 것.

공구리 = 224선 아래에서 하락하던 주가가 하락 박스를 돌파한 뒤, 되밀릴 때
         "직전 언덕"이 지지가 되는 것. 돌파가 아니라 지지 확인이 신호다.

사용법:
    python3 tools/concrete_check.py --selftest
    python3 tools/concrete_check.py data/*.csv

표준 라이브러리만 사용한다 (설치 불필요).
"""

import argparse
import math
import random
import sys
from datetime import datetime

from bowl_check import read_csv, sma

# ── Pine 기본값과 동일하게 유지할 것 ──────────────────────────────
DEFAULTS = dict(
    ma1_len=112,
    ma2_len=224,
    pivot_left=5,
    pivot_right=5,
    vol_len=20,
    vol_mult=1.5,
    vol_window=5,            # 최근 이 봉수 중 최대 거래량으로 판정 (돌파봉 ≠ 거래량 폭발봉)
    require_lower_high=True,
    lower_high_pct=2.0,      # 이번 언덕이 그 전 언덕보다 이 % 이상 낮아야 "하락 박스"
    min_runup_pct=5.0,       # 돌파 후 언덕 위로 이만큼 올라가야 되밀림 인정
    retest_tol_pct=2.0,      # 되밀림 저가가 언덕 +이 % 안까지 오면 "언덕에 닿음"
    fail_tol_pct=2.0,        # 종가가 언덕 -이 % 아래면 돌파 실패
    max_retest_wait=30,
    use_elliott=True,
    elliott_near_pct=5.0,    # 1파 모드: 언덕이 224선 ±이 % 안
    elliott_memory=120,      # 1파 모드: 이 봉수 안에 바닥권이었어야 함
)


def pivot_high(h, left, right):
    """ta.pivothigh — 확정되는 봉(center + right)에 값이 찍힌다.
    동률 처리는 Pine 과 다를 수 있다(여기선 좌우 모두 엄격히 커야 함)."""
    n, out = len(h), [None] * len(h)
    for i in range(left + right, n):
        c = i - right
        win = h[c - left:c] + h[c + 1:i + 1]
        if h[c] > max(win):
            out[i] = h[c]
    return out


def barssince(cond):
    out, last = [], None
    for i, x in enumerate(cond):
        if x:
            last = i
        out.append(None if last is None else i - last)
    return out


def run_concrete(data, p):
    times, o, h, l, c, v = data
    n = len(c)
    ma1, ma2 = sma(c, p["ma1_len"]), sma(c, p["ma2_len"])
    vol_avg = sma(v, p["vol_len"])
    w = p["vol_window"]
    piv = pivot_high(h, p["pivot_left"], p["pivot_right"])

    bottom = [ma1[i] is not None and ma2[i] is not None
              and c[i] < ma1[i] and c[i] < ma2[i] and ma1[i] < ma2[i] for i in range(n)]
    since_bottom = barssince(bottom)

    hill = prev_hill = None
    stage = 0                      # 0=대기, 1=돌파(되밀림 대기), 2=공구리 확인(지지 중)
    broken = bo_bar = None
    ran_up = touched = elliott = False
    support = None

    breakouts, concretes, fails, losses = [], [], [], []

    for i in range(n):
        prev_hill_level = hill      # ta.crossover 는 직전 봉의 hillLevel 과 비교한다
        if piv[i] is not None:
            prev_hill, hill = hill, piv[i]
        if ma2[i] is None or ma1[i] is None or vol_avg[i] is None:
            continue

        lower_high = prev_hill is not None and hill <= prev_hill * (1 - p["lower_high_pct"] / 100)
        cross = (i > 0 and hill is not None and prev_hill_level is not None
                 and c[i - 1] <= prev_hill_level and c[i] > hill)
        # 기준 평균은 판정 윈도우 "이전" 구간 것을 쓴다. 현재 평균을 쓰면 돌파 랠리의
        # 큰 거래량이 평균을 끌어올려 배수 조건이 무력화된다(합성 seed 0: 1.49배로 탈락).
        base = vol_avg[i - w] if i >= w else None
        vol_spike = base is not None and max(v[i - w + 1:i + 1]) > base * p["vol_mult"]

        mode_a = bottom[i] and (not p["require_lower_high"] or lower_high)
        near224 = hill is not None and abs(hill - ma2[i]) / ma2[i] * 100 <= p["elliott_near_pct"]
        mode_b = (p["use_elliott"] and not bottom[i] and c[i] > ma2[i] and near224
                  and since_bottom[i] is not None and since_bottom[i] <= p["elliott_memory"])

        if stage != 1 and cross and vol_spike and (mode_a or mode_b):
            stage, broken, bo_bar = 1, hill, i
            ran_up = touched = False
            elliott = mode_b
            breakouts.append(dict(i=i, date=times[i], hill=hill, elliott=mode_b))

        # 되밀림 판정 — ran_up 은 이전 봉까지의 값을 쓴다 (돌파 직후 첫 봉이 곧바로
        # "되밀림"으로 잡히는 걸 막는다. 밥그릇 흔들기 버그와 같은 구조)
        concrete = False
        if stage == 1 and i > bo_bar:
            if ran_up and l[i] <= broken * (1 + p["retest_tol_pct"] / 100):
                touched = True
            if touched and c[i] > broken and c[i] > o[i]:
                concrete = True
        if stage == 1 and h[i] >= broken * (1 + p["min_runup_pct"] / 100):
            ran_up = True

        if concrete:
            stage, support = 2, broken
            concretes.append(dict(i=i, date=times[i], hill=broken, elliott=elliott,
                                  wait=i - bo_bar))
        elif stage == 1:
            if c[i] < broken * (1 - p["fail_tol_pct"] / 100):
                stage = 0
                fails.append(dict(i=i, date=times[i]))
            elif i - bo_bar > p["max_retest_wait"]:
                stage = 0
        elif stage == 2 and c[i] < support:
            stage = 0
            losses.append(dict(i=i, date=times[i]))

    return dict(bars=n, span=(times[0], times[-1]), breakouts=breakouts,
                concretes=concretes, fails=fails, losses=losses)


# ══════════════════════════════════════════════════════════════
# 합성 패턴 — 이미지의 두 그림을 그대로 만든다
# ══════════════════════════════════════════════════════════════
class _Gen:
    def __init__(self, seed):
        self.rnd = random.Random(seed)
        self.t0 = datetime(2022, 1, 3)
        self.times, self.o, self.h, self.l, self.c, self.v = [], [], [], [], [], []
        self.price = 100.0

    def bar(self, cl, vol=1.0):
        op = self.price
        cl *= 1 + self.rnd.gauss(0, 0.002)
        self.times.append(datetime.fromordinal(self.t0.toordinal() + len(self.c)))
        self.o.append(op)
        self.c.append(cl)
        self.h.append(max(op, cl) * (1 + abs(self.rnd.gauss(0, 0.002))))
        self.l.append(min(op, cl) * (1 - abs(self.rnd.gauss(0, 0.002))))
        self.v.append(1e6 * vol * (1 + abs(self.rnd.gauss(0, 0.2))))
        self.price = cl

    def leg(self, target, bars, vol=1.0):
        """현재가에서 target 까지 bars 봉에 걸쳐 직선으로 간다 (꼭짓점 = 피벗)."""
        start = self.price
        for k in range(1, bars + 1):
            self.bar(start + (target - start) * k / bars, vol)

    def flat(self, level, bars):
        for k in range(bars):
            self.bar(level * (1 + math.sin(k / 3) * 0.01))

    def data(self):
        return (self.times, self.o, self.h, self.l, self.c, self.v)


def synth_down_box(seed=0, kind="ok"):
    """왼쪽 그림: 224선 아래 하락 박스 → 직전 언덕 돌파 → 되밀림.
    kind: ok(언덕에서 지지) / fail(언덕 뚫고 내려감) / flatbox(고점이 안 낮아지는 횡보 박스)"""
    g = _Gen(seed)
    g.flat(100, 260)
    g.leg(62, 40)                                   # 224선 아래로 급락
    hills = (66, 63, 60) if kind != "flatbox" else (60.5, 60.3, 60.0)
    lows = (57, 54, 50) if kind != "flatbox" else (55, 55, 55)
    for hl, lw in zip(hills, lows):                 # 고점·저점을 낮추는 하락 박스
        g.leg(hl, 8)
        g.leg(lw, 8)
    last_hill = hills[-1]
    g.leg(last_hill * 1.08, 10, vol=3.0)            # 직전 언덕 돌파 (거래량)
    if kind == "fail":
        g.leg(last_hill * 0.93, 8)                  # 언덕을 뚫고 내려감
        g.leg(last_hill * 0.88, 10)
    else:
        g.leg(last_hill * 1.005, 6)                 # 언덕까지 되밀림
        g.flat(last_hill * 1.02, 3)
        g.leg(last_hill * 1.25, 20, vol=1.5)
    return g.data(), last_hill


def synth_elliott(seed=0):
    """오른쪽 그림: 바닥권에서 올라와 224선 근처 언덕 → 224선·언덕 돌파(1파) → 언덕에서 지지."""
    g = _Gen(seed)
    g.flat(75, 260)
    g.leg(60, 20)
    g.flat(60, 100)                                 # 224선이 내려와 붙는 동안 바닥
    ma224 = sum(g.c[-224:]) / 224
    hill = ma224 * 0.99
    g.leg(hill, 10)                                 # 224선 근처 언덕
    g.leg(hill * 0.94, 8)
    g.leg(hill * 1.12, 12, vol=3.0)                 # 1파
    g.leg(hill * 1.01, 8)                           # 1파 눌림 — 언덕에서 지지
    g.flat(hill * 1.03, 3)
    g.leg(hill * 1.35, 20, vol=1.5)
    return g.data(), hill


def selftest():
    fails = []
    waits = {"하락박스": [], "1파": []}

    for seed in range(10):
        # ① 정상 공구리
        data, hill = synth_down_box(seed, "ok")
        r = run_concrete(data, DEFAULTS)
        ok = [x for x in r["concretes"] if abs(x["hill"] - hill) / hill < 0.02 and not x["elliott"]]
        if not ok:
            fails.append(f"seed {seed}: 하락 박스 공구리가 안 잡힘 "
                         f"(돌파 {len(r['breakouts'])} / 공구리 {len(r['concretes'])})")
        else:
            x = ok[0]
            h = data[2]
            bo = next(b["i"] for b in r["breakouts"] if b["hill"] == x["hill"])
            runup = max(h[bo:x["i"]]) / x["hill"] * 100 - 100
            if runup < DEFAULTS["min_runup_pct"]:
                fails.append(f"seed {seed}: 공구리 전 상승폭 {runup:.1f}% — 되밀림 전에 확정됨")
            waits["하락박스"].append(x["wait"])

        # ② 되밀려 언덕을 뚫고 내려감 → 공구리가 아니다
        data, hill = synth_down_box(seed, "fail")
        r = run_concrete(data, DEFAULTS)
        if any(abs(x["hill"] - hill) / hill < 0.02 for x in r["concretes"]):
            fails.append(f"seed {seed}: 언덕을 뚫고 내려갔는데 공구리 확정")
        if not r["fails"]:
            fails.append(f"seed {seed}: 돌파 실패가 표시되지 않음")

        # ③ 고점이 안 낮아지는 횡보 박스 → 하락 박스 돌파가 아니다
        data, hill = synth_down_box(seed, "flatbox")
        r = run_concrete(data, DEFAULTS)
        if any(abs(b["hill"] - hill) / hill < 0.02 for b in r["breakouts"]):
            fails.append(f"seed {seed}: 횡보 박스인데 돌파 인정")

        # ④ 엘리엇 1파 눌림
        data, hill = synth_elliott(seed)
        r = run_concrete(data, DEFAULTS)
        ok = [x for x in r["concretes"] if x["elliott"] and abs(x["hill"] - hill) / hill < 0.02]
        if not ok:
            fails.append(f"seed {seed}: 1파 눌림 공구리가 안 잡힘 "
                         f"(돌파 {[(b['elliott'], round(b['hill'], 1)) for b in r['breakouts']]}, 언덕 {hill:.1f})")
        else:
            waits["1파"].append(ok[0]["wait"])

    print("자가 검증 (합성: 하락 박스 공구리 / 실패 / 횡보 박스 / 엘리엇 1파 × 10 seed)")
    for k, w in waits.items():
        if w:
            print(f"  {k} 돌파→공구리 대기: {sorted(w)}봉")
    for f in fails:
        print(f"  ✗ {f}")
    if not fails:
        print("  ✓ 통과 — 정상 10/10, 실패 10/10 걸러냄, 횡보 박스 10/10 걸러냄, 1파 10/10")
    return 0 if not fails else 1


def report(name, r):
    fmt = lambda d: d.strftime("%Y-%m-%d")
    print(f"\n{'=' * 60}\n{name}   {r['bars']}봉  {fmt(r['span'][0])} ~ {fmt(r['span'][1])}\n{'=' * 60}")
    print(f"산 돌파 {len(r['breakouts'])}건 / 공구리 확정 {len(r['concretes'])}건 / "
          f"돌파 실패 {len(r['fails'])}건 / 지지 이탈(Loss) {len(r['losses'])}건")
    for x in r["concretes"]:
        print(f"  {fmt(x['date'])}  언덕 {x['hill']:>10,.2f}  돌파 후 {x['wait']:>2}봉"
              + ("  [1파 눌림]" if x["elliott"] else ""))


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
        report(path.split("/")[-1], run_concrete(read_csv(path), DEFAULTS))


if __name__ == "__main__":
    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    main()
