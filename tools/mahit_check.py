#!/usr/bin/env python3
"""MaHit.pine(이평때리기)의 로직을 봉 단위로 재현해 검증한다.

bowl_check.py 와 같은 취지다 — Pine 코드 자체가 아니라 "로직 설계"의 검증이며,
두 구현이 갈라질 수 있으니 신호 날짜는 반드시 차트와 대조할 것.

이평때리기 = 많이 빠졌던 주가가 역배열 상태에서 112선을 돌파하면 머리 위 224선을
             때리고, 224선을 맞고 빠진 뒤 다시 힘을 모아 224선을 넘어 448선을 때린다.
             "작은 형님을 먼저 깨고 큰 형님한테 덤빈다."

사용법:
    python3 tools/mahit_check.py --selftest
    python3 tools/mahit_check.py data/*.csv

표준 라이브러리만 사용한다 (설치 불필요).
"""

import argparse
import math
import random
import sys
from datetime import datetime

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from bowl_check import read_csv  # noqa: E402

# ── Pine 기본값과 동일하게 유지할 것 ──────────────────────────────
DEFAULTS = dict(
    mid_len=112,
    long_len=224,
    xlong_len=448,
    deep_lookback=250,         # "많이 빠졌던" 판정 기간
    min_deep_pct=35.0,         # 이 기간 중 주가가 448선보다 이 % 이상 아래로 벌어진 적이 있어야 함
                               # 합성: 급락 패턴은 바닥 길이(60~300봉)와 무관하게 98% 통과,
                               # 완만한 조정(-15%)은 최대 28% 라 0% 통과.
    spread_lookback=120,
    contract_pct=2.0,
    settle_bars=3,
)


def ema(src, length):
    """ta.ema — 첫 값은 SMA 로 시드하고, 그 전은 None"""
    a, out, e = 2 / (length + 1), [], None
    for i, x in enumerate(src):
        if e is None:
            if i >= length - 1:
                e = sum(src[i - length + 1:i + 1]) / length
        else:
            e = a * x + (1 - a) * e
        out.append(e)
    return out


def run_mahit(data, p):
    times, o, h, l, c, v = data
    n = len(c)
    m1, m2, m3 = ema(c, p["mid_len"]), ema(c, p["long_len"]), ema(c, p["xlong_len"])
    sb = p["settle_bars"]

    in_pos = hit1 = broke_long = False
    bars_above_mid = bars_above_long = 0
    settled_prev = long_settled_prev = False
    spreads, dists = [], []

    buys, long_breaks, t1, t2, stops = [], [], [], [], []

    for i in range(n):
        if m3[i] is None:
            spreads.append(None)
            dists.append(None)
            continue
        rev = m1[i] < m2[i] < m3[i]
        dist_xlong = (m3[i] - c[i]) / c[i] * 100
        dists.append(dist_xlong)
        deep = max(d for d in dists[-p["deep_lookback"]:] if d is not None)
        spread = (m3[i] - m1[i]) / m3[i] * 100
        spreads.append(spread)
        window = [s for s in spreads[-p["spread_lookback"]:] if s is not None]
        peak = max(window)
        contracting = peak > 0 and spread < peak * (1 - p["contract_pct"] / 100)

        bars_above_mid = bars_above_mid + 1 if c[i] > m1[i] else 0
        settled = bars_above_mid >= sb
        just_settled = settled and not settled_prev
        settled_prev = settled

        bars_above_long = bars_above_long + 1 if c[i] > m2[i] else 0
        long_settled = bars_above_long >= sb
        long_just = long_settled and not long_settled_prev
        long_settled_prev = long_settled

        buy = just_settled and rev and deep >= p["min_deep_pct"] and contracting
        if buy and not in_pos:
            in_pos, hit1, broke_long = True, False, False
            buys.append(dict(i=i, date=times[i], price=c[i], dist=dist_xlong, deep=deep))

        if in_pos and not hit1 and h[i] >= m2[i]:
            hit1 = True
            t1.append(dict(i=i, date=times[i]))

        # 224선을 "때린" 뒤 그 위에 안착하면 448선 도전 시작 (이미지의 두 번째 화살표)
        if in_pos and hit1 and not broke_long and long_just:
            broke_long = True
            long_breaks.append(dict(i=i, date=times[i], price=c[i]))

        if in_pos and h[i] >= m3[i]:
            t2.append(dict(i=i, date=times[i]))
            in_pos = False

        if in_pos and not buy and c[i] < m1[i]:
            stops.append(dict(i=i, date=times[i]))
            in_pos = False

    return dict(bars=n, span=(times[0], times[-1]), buys=buys, long_breaks=long_breaks,
                t1=t1, t2=t2, stops=stops)


# ══════════════════════════════════════════════════════════════
# 합성 패턴 — 이미지의 모양을 그대로 만든다
# ══════════════════════════════════════════════════════════════
class _Gen:
    def __init__(self, seed, noise=0.01):
        self.rnd = random.Random(seed)
        self.noise = noise
        self.t0 = datetime(2022, 1, 3)
        self.times, self.o, self.h, self.l, self.c, self.v = [], [], [], [], [], []
        self.price = 100.0

    def bar(self, drift=0.0, level=None):
        op = self.price
        cl = (level if level is not None else op * (1 + drift)) * (1 + self.rnd.gauss(0, self.noise))
        self.times.append(datetime.fromordinal(self.t0.toordinal() + len(self.c)))
        self.o.append(op)
        self.c.append(cl)
        self.h.append(max(op, cl) * (1 + abs(self.rnd.gauss(0, 0.003))))
        self.l.append(min(op, cl) * (1 - abs(self.rnd.gauss(0, 0.003))))
        self.v.append(1e6)
        self.price = cl

    def ema_now(self, length):
        return ema(self.c, length)[-1]

    def data(self):
        return (self.times, self.o, self.h, self.l, self.c, self.v)


def synth_crash(seed, base_len, drop=0.015):
    """상승 → 급락(40봉) → 바닥(base_len 봉) → 회복. drop=0.004 면 -15% 수준의 완만한 조정."""
    g = _Gen(seed)
    for _ in range(500):
        g.bar(0.0005)
    for _ in range(40):
        g.bar(-drop)
    b = g.price
    for i in range(base_len):
        g.noise = 0.004
        g.bar(level=b * (1 + math.sin(i / 6) * 0.02))
    g.noise = 0.01
    for _ in range(80):
        g.bar(0.006)
    return g.data()


def synth_full(seed):
    """이미지 전체: 급락 → 긴 바닥 → 112 돌파 → 224 때리고 되밀림(112선까지) → 224 돌파 → 448 때림."""
    g = _Gen(seed)
    for _ in range(500):
        g.bar(0.0005)
    for _ in range(40):
        g.bar(-0.015)
    b = g.price
    g.noise = 0.003
    for i in range(150):
        g.bar(level=b * (1 + math.sin(i / 6) * 0.02))
    for _ in range(200):                                  # 112 돌파 → 224 때림
        if g.h and g.h[-1] >= g.ema_now(224):
            break
        g.bar(0.008)
    for _ in range(60):                                   # 224 맞고 빠짐 (112선 근처까지)
        if g.price <= g.ema_now(112) * 1.03:
            break
        g.bar(-0.006)
    for _ in range(300):                                  # 힘을 모아 224 돌파 → 448 때림
        if g.h[-1] >= g.ema_now(448):
            break
        g.bar(0.006)
    for _ in range(10):
        g.bar(0.0)
    return g.data()


def selftest():
    fails, rows = [], []
    p = DEFAULTS
    N = 20
    # 전부 통과를 요구하지 않는다. 랜덤워크라 하락 전 상승이 약한 seed 는 급락해도
    # 448선과 크게 안 벌어진다 — 기법상 "많이 빠졌던" 종목이 아니므로 걸러지는 게 맞다.
    FLOOR = 0.9

    # ① 급락 후 바닥 길이별 탐지율 — 이미지처럼 긴 바닥에서도 잡혀야 한다
    for base in (60, 120, 200, 300):
        hit = sum(bool(run_mahit(synth_crash(s, base), p)["buys"]) for s in range(N))
        # 수정 전 조건(최근 60봉 안에 112선 대비 이격 -10%)과 비교
        old = 0
        for s in range(N):
            d = synth_crash(s, base)
            c, m1 = d[4], ema(d[4], p["mid_len"])
            r = run_mahit(d, p)
            if r["buys"]:
                i = r["buys"][0]["i"]
                old += min((c[j] - m1[j]) / m1[j] * 100 for j in range(i - 59, i + 1)) <= -10
        rows.append(f"  급락 + 바닥 {base:3}봉: BUY {hit}/{N}  (그중 수정 전 이격 조건도 통과 {old})")
        if hit < N * FLOOR:
            fails.append(f"바닥 {base}봉 탐지율 {hit}/{N} < {FLOOR:.0%}")

    # ② 완만한 조정(-15%) — "많이 빠졌던" 주가가 아니므로 BUY 가 나오면 안 된다
    fp = sum(len(run_mahit(synth_crash(s, b, drop=0.004), p)["buys"])
             for s in range(N) for b in (60, 120, 200))
    rows.append(f"  완만한 조정 -15%: BUY {fp}건 (0 이어야 함)")
    if fp:
        fails.append(f"완만한 조정에서 BUY {fp}건")

    # ③ 이미지 전체 시퀀스 — 112 돌파 → 224 때림 → 224 돌파 → 448 때림
    seq_ok = n_buy = 0
    for s in range(N):
        r = run_mahit(synth_full(s), p)
        if not r["buys"]:
            continue
        n_buy += 1
        order = []
        for k, lst in (("BUY", r["buys"]), ("224때림", r["t1"]), ("224돌파", r["long_breaks"]),
                       ("448때림", r["t2"])):
            if lst:
                order.append((lst[0]["i"], k))
        got = [k for _, k in sorted(order)]
        if got == ["BUY", "224때림", "224돌파", "448때림"] and not r["stops"]:
            seq_ok += 1
        else:
            fails.append(f"seed {s}: 시퀀스 {got}, 손절 {len(r['stops'])}건")
    rows.append(f"  전체 시퀀스(112돌파→224때림→224돌파→448때림): BUY {n_buy}/{N}, "
                f"그중 순서대로 진행 {seq_ok}/{n_buy}")
    if n_buy < N * FLOOR:
        fails.append(f"전체 시퀀스 BUY {n_buy}/{N} < {FLOOR:.0%}")

    print("자가 검증 (합성: 급락 후 바닥 길이별 / 완만한 조정 / 이미지 전체 시퀀스)")
    print("\n".join(rows))
    for f in fails:
        print(f"  ✗ {f}")
    if not fails:
        print("  ✓ 통과")
    return 0 if not fails else 1


def report(name, r):
    fmt = lambda d: d.strftime("%Y-%m-%d")
    print(f"\n{'=' * 60}\n{name}   {r['bars']}봉  {fmt(r['span'][0])} ~ {fmt(r['span'][1])}\n{'=' * 60}")
    print(f"BUY {len(r['buys'])} / 224때림 {len(r['t1'])} / 224돌파 {len(r['long_breaks'])} / "
          f"448때림 {len(r['t2'])} / 손절 {len(r['stops'])}")
    for b in r["buys"]:
        print(f"  {fmt(b['date'])}  {b['price']:>10,.2f}  448선까지 {b['dist']:.0f}%"
              f"  (최근 최대 {b['deep']:.0f}%)")


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
        report(path.split("/")[-1], run_mahit(read_csv(path), DEFAULTS))


if __name__ == "__main__":
    main()
