# Pine Script 지표 개발 사양서

TradingView Claude.ai 대화에서 개발한 지표들의 최종 상태 정리. 각 스크립트는 대화에서 마지막으로 확정된 버전을 기준으로 작성했으며, 미해결/확인 필요 항목은 별도로 표시함.

---

## 1. ReverseAlign112 (계보: 역매공파112 → 빨녹노112돌파 → ReverseAlign112)

### 목적
장기 이평선(112/224/448) 역배열 상태에서, 볼린저밴드(20,2) 상단선을 26봉 선행이동(이치모쿠 구름과 동일 원리)시켜 "덜 엄격한 저항선"으로 삼고, 그 선과 112일선을 동시에 터치하는 양봉을 신호로 표시.

### 핵심 로직
- **역배열 정의**: `MA112 < MA224 < MA448` (숫자가 클수록 값이 큰 순서 = 하락정렬)
- **BB 상단선**: 실시간 값이 아니라 26봉 전에 계산된 값을 `offset`으로 현재 위치에 투영 (이치모쿠 구름과 동일 원리)
- **매수 신호**: 양봉 + (26봉전 BB상단값 ≤ 현재 고가) + (MA112 ≤ 현재 고가) → 역삼각형. 역배열 상태면 밝은 라임그린, 아니면 옅은 그린
- **이치모쿠 구름**: Tenkan(9)/Kijun(26)/Senkou B(52)/26봉 선행이동 완전 구현
- **배경색**: 역배열 상태일 때 옅은 빨강

### 확인 필요
- 삼각형 신호(`signalCond`)가 "26봉 전 변동성 기준 상단선"에 지금 닿았는지로 판정됨 — 실제 차트에서 신호 빈도/위치가 의도와 맞는지 검증 필요

```pine
// This Pine Script® code is subject to the terms of the Mozilla Public License 2.0 at https://mozilla.org/MPL/2.0/
// © busiruk

//@version=6
indicator("ReverseAlign112", overlay=true)

// ── 1. Bollinger Band(20,2) upper line, 26-bar displaced (like Ichimoku cloud) ──
bbDLen         = input.int(20, "BB Length", group="Displaced BB")
bbDMult        = input.float(2.0, "BB Mult", group="Displaced BB")
bbDisplacement = input.int(26, "BB Displacement", group="Displaced BB")

[bbMidD, bbUpperD, bbLowerD] = ta.bb(close, bbDLen, bbDMult)

plot(bbUpperD, title="BB Upper (26-Displaced)", offset=bbDisplacement - 1,
     color=color.new(#0044ff, 0), style=plot.style_line, linewidth=1)

// ── 2~4. Moving averages ──
ma112 = ta.sma(close, 112)
ma224 = ta.sma(close, 224)
ma448 = ta.sma(close, 448)

plot(ma112, title="MA112", color=color.yellow, linewidth=1)
plot(ma224, title="MA224", color=color.green, linewidth=1)
plot(ma448, title="MA448", color=color.red, linewidth=1)

isReverseAlign = ma112 < ma224 and ma224 < ma448

// ── 5. MA 5, gray, bold ──
ma5 = ta.sma(close, 5)
plot(ma5, title="MA5", color=color.gray, linewidth=3)

// ── 6. Ichimoku Kijun-sen, pink ──
kijunLen = input.int(26, "Kijun-sen Length")
kijunSen = (ta.highest(high, kijunLen) + ta.lowest(low, kijunLen)) / 2
plot(kijunSen, title="Kijun-sen", color=color.new(#FF69B4, 0), linewidth=2)

// ── 7. MA 60, orange ──
ma60 = ta.sma(close, 60)
plot(ma60, title="MA60", color=color.new(color.orange, 0), linewidth=2)

// ── 8. Bullish candle touching both displaced BB upper and MA112 → triangle ──
isBullish = close > open
touchDisplacedBB = high >= bbUpperD[bbDisplacement - 1]   // value now shown at current bar's position
touchBoth = touchDisplacedBB and high >= ma112
signalCond = isBullish and touchBoth

plotshape(signalCond, title="Displaced BB Upper + MA112 Touch", style=shape.triangledown,
     location=location.abovebar,
     color=isReverseAlign ? color.new(color.lime, 0) : color.new(color.green, 60),
     size=size.tiny)

// ── 9. MA112 / MA224 / MA448 reverse alignment check (MA112 < MA224 < MA448) ──
bgcolor(isReverseAlign ? color.new(color.red, 85) : na, title="Reverse Alignment Background")

// ── 10. Ichimoku Cloud (Tenkan 9 / Kijun 26 / Senkou B 52 / displacement 26) ──
tenkanLen  = input.int(9, "Tenkan-sen Length", group="Ichimoku Cloud")
senkouBLen = input.int(52, "Senkou Span B Length", group="Ichimoku Cloud")
displacement = input.int(26, "Cloud Displacement", group="Ichimoku Cloud")

tenkanSen = (ta.highest(high, tenkanLen) + ta.lowest(low, tenkanLen)) / 2

senkouSpanA = (tenkanSen + kijunSen) / 2
senkouSpanB = (ta.highest(high, senkouBLen) + ta.lowest(low, senkouBLen)) / 2

spanA = plot(senkouSpanA, title="Senkou Span A", color=color.new(color.green, 70), offset=displacement - 1)
spanB = plot(senkouSpanB, title="Senkou Span B", color=color.new(color.red, 70), offset=displacement - 1)

fill(spanA, spanB,
     color = senkouSpanA > senkouSpanB ? color.new(color.green, 85) : color.new(color.red, 85),
     title = "Cloud")


// ── Show each line's name as a label at the last bar ──
if barstate.islast
    label.new(bar_index + 1, bbUpperD, "BB Upper (26-Displaced)",
         color=color.new(#0000CD, 0), textcolor=color.white,
         style=label.style_label_left, size=size.small)

    label.new(bar_index + 1, ma112, "MA112",
         color=color.new(color.yellow, 0), textcolor=color.black,
         style=label.style_label_left, size=size.small)

    label.new(bar_index + 1, ma224, "MA224",
         color=color.new(color.green, 0), textcolor=color.white,
         style=label.style_label_left, size=size.small)

    label.new(bar_index + 1, ma448, "MA448",
         color=color.new(color.red, 0), textcolor=color.white,
         style=label.style_label_left, size=size.small)

    label.new(bar_index + 1, ma5, "MA5",
         color=color.new(color.gray, 0), textcolor=color.black,
         style=label.style_label_left, size=size.small)

    label.new(bar_index + 1, ma60, "MA60",
         color=color.new(color.orange, 0), textcolor=color.white,
         style=label.style_label_left, size=size.small)

    label.new(bar_index + 1, kijunSen, "Kijun-sen",
         color=color.new(#FF69B4, 0), textcolor=color.white,
         style=label.style_label_left, size=size.small)

    label.new(bar_index + 1, (ma112 + ma448) / 2,
         isReverseAlign ? "GO Buy" : "No Buy",
         color=color.new(isReverseAlign ? color.red : color.gray, 0),
         textcolor=color.white, style=label.style_label_left, size=size.small)
```

---

## 2. 하락후지지 공구리돌파 (Concrete Detection)

### 목적
역배열 바닥권(112/224일선 아래 + 역배열)에서, 직전 스윙 고점("언덕")을 강한 거래량과 함께 돌파하는 지점("공구리")을 감지. 돌파 봉의 시가를 지지선으로 설정하고 이탈 시 손절 경고.

### 핵심 파라미터
| 변수 | 기본값 | 설명 |
|---|---|---|
| maLen1 | 112 | 바닥권 판단 이평선1 |
| maLen2 | 224 | 바닥권 판단 이평선2 |
| pivotLeft/Right | 5 / 5 | 언덕(스윙고점) 감지 좌우 봉수 |
| volLen | 20 | 거래량 평균 기간 |
| volMult | 1.5 | 거래량 급증 배수 |
| ma5NearMa224Pct | 2.0 | MA5-MA224 근접 허용범위(%) |

### 핵심 로직
- `isBottomZone` = 종가 < MA112, 종가 < MA224, MA112 < MA224
- 언덕(Hill) = `ta.pivothigh()`로 스윙 고점 추적
- 언덕 돌파 캔들: 양봉 + 몸통비율 ≥ 60% + 언덕 고가 상회 (언덕당 1회만 마킹)
- Concrete 신호: `ta.crossover(close, hillLevel)` + 거래량 급증 + 바닥권 상태 동시 만족
- 지지선: Concrete 발생 봉의 시가를 대시선으로 우측 연장, 종가가 이탈하면 "Loss" 라벨
- MA5-MA224 근접: 처음 근접하는 순간에만 자홍색 역삼각형 + "근접" 텍스트 표시

```pine
// This Pine Script® code is subject to the terms of the Mozilla Public License 2.0 at https://mozilla.org/MPL/2.0/
// © busiruk

//@version=6
indicator("하락후지지 공구리돌파", overlay=true)

// ── Inputs ──
maLen1      = input.int(112, "Bottom Zone MA Length 1", group="Bottom Zone Condition")
maLen2      = input.int(224, "Bottom Zone MA Length 2", group="Bottom Zone Condition")

pivotLeft   = input.int(5, "Hill Detection Left Bars", group="Hill Condition")
pivotRight  = input.int(5, "Hill Detection Right Bars (Confirmation Delay)", group="Hill Condition")

volLen      = input.int(20, "Volume Average Length", group="Breakout Condition")
volMult     = input.float(1.5, "Volume Spike Multiplier", group="Breakout Condition")

// ── 1. Bottom zone check (reverse alignment + price below MAs) ──
ma1 = ta.sma(close, maLen1)
ma2 = ta.sma(close, maLen2)

plot(ma1, title="MA112", color=color.new(#b91e6b, 0), linewidth=2)
plot(ma2, title="MA224", color=color.green, linewidth=1)

isBelowMA      = close < ma1 and close < ma2
isReverseAlign = ma1 < ma2
isBottomZone   = isBelowMA and isReverseAlign

// ── MA 5
ma5  = ta.sma(close, 5)

plot(ma5,  title="MA5",  color=color.rgb(255, 255, 255), linewidth=2)

// ── 6. MA5가 MA224에 근접 시 역삼각형 표시 (최초 근접 시점만) ──
ma5NearMa224Pct = input.float(2.0, "MA5-MA224 근접 허용범위(%)", group="근접 조건")

ma5NearMa224 = math.abs(ma5 - ma2) / ma2 * 100 <= ma5NearMa224Pct
ma5NearMa224JustNow = ma5NearMa224 and not ma5NearMa224[1]

plotshape(ma5NearMa224JustNow, title="MA5-MA224 근접", style=shape.triangledown,
     location=location.abovebar, color=color.new(color.fuchsia, 0),
     textcolor=color.fuchsia, text="근접", size=size.tiny)

// ── 2. Hill (previous swing high) tracking ──
pivotHigh = ta.pivothigh(high, pivotLeft, pivotRight)

var float hillLevel = na
var int   hillBar   = na

if not na(pivotHigh)
    hillLevel := pivotHigh
    hillBar   := bar_index - pivotRight

// ── Hill breakout candle marker (first bullish candle exceeding hill's high) ──
var bool hillBreakMarked = false

if not na(pivotHigh)
    hillLevel := pivotHigh
    hillBar   := bar_index - pivotRight
    hillBreakMarked := false   // reset marker state for the new hill

isBullishCandle = close > open
bodySize   = close - open
rangeSize  = high - low
bodyRatio  = rangeSize > 0 ? bodySize / rangeSize : 0
isStrongBody = bodyRatio >= 0.6

breakHillHigh = not na(hillLevel) and high > hillLevel and isBullishCandle and isStrongBody and not hillBreakMarked

if breakHillHigh
    hillBreakMarked := true

plotshape(breakHillHigh, title="Hill Breakout Candle", style=shape.triangledown,
     location=location.abovebar, color=color.new(color.green, 0), size=size.tiny)

// ── 3. Breakout (Concrete) condition: hill breakout + volume spike + in bottom zone ──
volSpike     = volume > ta.sma(volume, volLen) * volMult
crossHill    = ta.crossover(close, hillLevel)   // always called every bar
breakout     = not na(hillLevel) and crossHill
concreteCond = breakout and volSpike and isBottomZone

plotshape(concreteCond, title="Concrete", style=shape.labelup,
     location=location.belowbar, color=color.new(#8B7355, 0),
     textcolor=color.white, text="Concrete", size=size.small)

// ── 4. Support line (breakout bar's open price as horizontal support) ──
var line supportLine = na
var float supportPrice = na
var bool  supportBroken = false

if concreteCond
    if not na(supportLine)
        line.delete(supportLine)
    supportLine := line.new(bar_index, open, bar_index + 200, open,
         color=color.new(#8B7355, 0), style=line.style_dashed, width=2, extend=extend.right)
    supportPrice := open
    supportBroken := false

// ── 5. Support break warning (stop-loss alert) ──
if not na(supportPrice) and not supportBroken and close < supportPrice
    supportBroken := true
    label.new(bar_index, low, "Loss", color=color.new(color.red, 0),
         textcolor=color.white, style=label.style_label_up, size=size.small)

// ── Hill marker (only shown for the hill that triggered a Concrete signal) ──
if concreteCond
    label.new(hillBar, hillLevel, "", style=label.style_circle,
         color=color.new(color.orange, 20), size=size.tiny)

bgcolor(isBottomZone ? color.new(color.blue, 80) : na, title="Bottom Zone (Reverse Align + Below MA) Background")

// ── Show each line's name as a label at the last bar ──
if barstate.islast
    label.new(bar_index + 1, ma1, "MA112",
         color=color.new(#b91e6b, 0), textcolor=color.white,
         style=label.style_label_left, size=size.small)

    label.new(bar_index + 1, ma2, "MA224",
         color=color.new(color.green, 0), textcolor=color.white,
         style=label.style_label_left, size=size.small)

    label.new(bar_index + 1, ma5, "MA5",
         color=color.new(color.white, 0), textcolor=color.black,
         style=label.style_label_left, size=size.small)
```

---

## 3. 1년밥그릇256기법 (256 매매)

### 목적
224일선 아래에서 좁게 횡보("밥그릇" 바닥)한 뒤, 5일선이 20일선을 골든크로스하고, 이후 224일선에 근접하는 지점을 매수 관심 구간으로 표시.

### 핵심 파라미터
| 변수 | 기본값 | 설명 |
|---|---|---|
| ma5Len/ma20Len/ma60Len/ma224Len | 5/20/60/224 | 이평선 기간 |
| consolLen | 20 | 횡보 판단 기간 |
| consolPctMax | 8.0 | 횡보 판단 최대 변동폭(%) |
| maxWaitBars | 60 | 골든크로스 후 대기 최대 봉수 |
| proximityPct | 2.0 | 224일선 근접 허용범위(%) |

### 핵심 로직
- 공구리(횡보) 구간: 20봉 고저 range가 8% 이내 + 종가 < MA224
- 골든크로스: `ta.crossover(ma5,ma20)` + 종가>MA20 + 횡보구간 안에서 발생 → "골든크로스" 깃발
- 골든크로스 후 대기 상태 진입, 60봉 이내에 224일선 근접(±2%) 시 "1년선근접" 신호(최초 1회만, 이후 대기상태 해제)
- 이평선 정렬(`MA60>MA5>MA20` + MA5 상승 중) → 흰 삼각형 (조건 유지되는 매 봉마다 표시됨)

### ⚠️ 미해결 항목
"이평선 정렬" 신호(섹션 5)가 상승추세 구간에서도 너무 자주 뜬다는 문제가 제기됨. 두 가지 개선안이 제시되었으나 **최종 선택되지 않음**:
- 안 A: `maOrderJustFormed`(정렬이 방금 성립된 순간만) + `recentlyConsol`(최근 횡보 구간을 거쳤는지, `ta.barssince(isConsolZone) <= 15`) 필터 추가
- 안 B: `MA60>MA5>MA20` 엄격한 순서 대신 `MA5>MA20`만 확인 + 5일선 상승 조건만 유지 (급락 강도에 관계없이 반등 시 신호가 뜨도록 완화)

포드(F) 차트 검증 결과, 급락 폭이 클수록 60일선까지 넘는 정확한 순서가 성립하지 않고 지나가버리는 경우가 확인됨. Claude Code에서 이어서 결정 필요.

```pine
// This Pine Script® code is subject to the terms of the Mozilla Public License 2.0 at https://mozilla.org/MPL/2.0/

//@version=6
indicator("1년밥그릇256기법", overlay=true)

// ══════════════════════════════════════
// 1. 이동평균선 설정
// ══════════════════════════════════════
ma5Len   = input.int(5,   "5일선", group="이동평균선")
ma20Len  = input.int(20,  "20일선", group="이동평균선")
ma60Len  = input.int(60,  "60일선", group="이동평균선")
ma224Len = input.int(224, "224일선", group="이동평균선")

ma5   = ta.sma(close, ma5Len)
ma20  = ta.sma(close, ma20Len)
ma60  = ta.sma(close, ma60Len)
ma224 = ta.sma(close, ma224Len)

plot(ma5,   title="MA5",   color=color.new(color.lime, 0), linewidth=2)
plot(ma20,  title="MA20",  color=color.new(color.orange, 0), linewidth=2)
plot(ma60,  title="MA60",  color=color.new(color.red, 0), linewidth=2)
plot(ma224, title="MA224", color=color.new(color.purple, 0), linewidth=1)

// ══════════════════════════════════════
// 2. 하락 후 224일선 아래 횡보(공구리) 구간 감지
// ══════════════════════════════════════
consolLen    = input.int(20, "횡보 판단 기간", group="공구리 구간")
consolPctMax = input.float(8.0, "횡보 판단 최대 변동폭(%)", group="공구리 구간")

rangeHigh = ta.highest(high, consolLen)
rangeLow  = ta.lowest(low, consolLen)
rangePct  = (rangeHigh - rangeLow) / rangeLow * 100

isSideways   = rangePct <= consolPctMax
isBelow224   = close < ma224
isConsolZone = isSideways and isBelow224

bgcolor(isConsolZone ? color.new(color.maroon, 90) : na, title="공구리(횡보) 구간 표시")

// ══════════════════════════════════════
// 3. 골든크로스 발생 (5일선이 20일선 상향돌파, 20일선 위 확인)
// ══════════════════════════════════════
goldenCross = ta.crossover(ma5, ma20)   // 매 봉 항상 호출
aboveMA20   = close > ma20

goldenCrossValid = goldenCross and aboveMA20 and isConsolZone

plotshape(goldenCrossValid, title="골든크로스", style=shape.flag,
     location=location.belowbar, color=color.new(color.yellow, 0),
     size=size.small, text="골든크로스", textcolor=color.yellow)

// ── 골든크로스 발생 시 "매수 대기" 상태 진입 ──
maxWaitBars = input.int(60, "골든크로스 후 대기 최대 봉수(초과시 취소)", group="매수 신호")

var bool waitingBreakout = false
var int  goldenCrossBar  = na

if goldenCrossValid
    waitingBreakout := true
    goldenCrossBar  := bar_index

// 대기 시간 초과 시 신호 취소 (오래된 골든크로스는 무효화)
if waitingBreakout and not na(goldenCrossBar) and (bar_index - goldenCrossBar > maxWaitBars)
    waitingBreakout := false

// ══════════════════════════════════════
// 4. 224일선 근접 = 매수 관심 구간
// ══════════════════════════════════════
proximityPct = input.float(2.0, "224일선 근접 허용범위(%)", group="매수 신호")

nearMa224 = math.abs(close - ma224) / ma224 * 100 <= proximityPct
buySignal256 = nearMa224 and waitingBreakout

if buySignal256
    waitingBreakout := false   // 신호 발생 후 대기 상태 해제 (다음 사이클 준비)

plotshape(buySignal256, title="근접", style=shape.triangledown,
     location=location.abovebar, color=color.new(color.lime, 0),
     textcolor=color.lime, size=size.small, text="1년선근접")

// ══════════════════════════════════════
// 5. 이동평균선 정렬 조건 (60일선 > 5일선 > 20일선 순서, 5일선 상승 중)
//    ※ 신호 과다 발생 이슈 있음 — 위 "미해결 항목" 참고
// ══════════════════════════════════════
isMaOrder60_5_20 = ma60 > ma5 and ma5 > ma20
isMa5Rising = ma5 > ma5[1]

maOrderSignal = isMaOrder60_5_20 and isMa5Rising

plotshape(maOrderSignal, title="MA정렬 60-5-20", style=shape.triangleup,
     location=location.belowbar, color=color.new(color.white, 0),
     textcolor=color.white, size=size.tiny)

// ══════════════════════════════════════
// 6. 각 이평선 이름을 마지막 봉 오른쪽에 라벨로 표시
// ══════════════════════════════════════
if barstate.islast
    label.new(bar_index + 1, ma5, "MA5",
         color=color.new(color.lime, 0), textcolor=color.black,
         style=label.style_label_left, size=size.small)

    label.new(bar_index + 1, ma20, "MA20",
         color=color.new(color.orange, 0), textcolor=color.white,
         style=label.style_label_left, size=size.small)

    label.new(bar_index + 1, ma60, "MA60",
         color=color.new(color.red, 0), textcolor=color.white,
         style=label.style_label_left, size=size.small)

    label.new(bar_index + 1, ma224, "MA224",
         color=color.new(color.purple, 0), textcolor=color.white,
         style=label.style_label_left, size=size.small)
```

---

## 4. 5일하락 후 장대양봉 돌파

### 목적
5일간 하락 흐름 이후, 거래량을 동반한 강한 몸통의 양봉이 그 하락을 되돌리며 5일선을 돌파하는 지점을 감지. 20일 하락추세, 신호 전 베이스(횡보), 강한 종가 위치, 과도한 급락(떨어지는 칼날) 배제 필터까지 포함한 최종 버전.

### 핵심 파라미터
| 변수 | 기본값 | 설명 |
|---|---|---|
| declineLen | 5 | 하락 확인 기간(봉수) |
| bodyLen / bodyMult | 20 / 1.3 | 평균 몸통 계산 기간 / 배수 |
| volLen / volMult | 20 / 1.2 | 거래량 평균 기간 / 급증 배수 |
| trendLen | 20 | 하락추세 확인 기간 |
| baseLen / baseRangeMax | 5 / 10.0 | 신호 전 베이스 확인 기간 / 최대 변동폭(%) |
| closePosMin | 0.75 | 종가 위치 최소값(0~1, 캔들 range 내 상대위치) |
| steepMaxPct | -35.0 | 20일 최대 하락률(%) 제한 |

### 핵심 로직 (7단계 필터, 전부 AND)
1. 하락 구간: 직전 5봉 중 3봉 이상 음봉 OR MA5가 5봉 전보다 낮음
2. 큰 양봉: 몸통이 평균(오늘 제외) 대비 1.3배 이상 + 거래량 1.2배 이상
3. 돌파: 종가가 직전 5봉 종가 최고값 상회 + MA5 상회
4. 20일 하락추세: 선형회귀 기울기 음수 + 어제 종가 < 21봉전 종가 (오늘 캔들 제외하고 계산)
5. 신호 전 베이스: 신호 전 5봉 range가 10% 이내 (급락 도중 반등 배제)
6. 강한 종가: 종가 위치가 캔들 range의 상위 75% 이상 (위꼬리 긴 약한 양봉 배제)
7. 급락속도 제한: 20일 하락률 -35% 이내 (떨어지는 칼날 배제)

```pine
// This Pine Script® code is subject to the terms of the Mozilla Public License 2.0 at https://mozilla.org/MPL/2.0/
// © busiruk

//@version=6
indicator("5일하락 후 장대양봉 돌파", overlay=true)

// ── Inputs ──
declineLen  = input.int(5, "하락 확인 기간(봉수)", group="하락 구간 조건")
bodyLen     = input.int(20, "평균 몸통 계산 기간", group="양봉 강도 조건")
bodyMult    = input.float(1.3, "몸통 크기 배수(평균 대비)", group="양봉 강도 조건")
volLen      = input.int(20, "거래량 평균 기간", group="거래량 조건")
volMult     = input.float(1.2, "거래량 급증 배수", group="거래량 조건")

trendLen    = input.int(20, "하락추세 확인 기간", group="20일 추세 조건")

baseLen      = input.int(5, "베이스 확인 기간(신호 전)", group="베이스 조건")
baseRangeMax = input.float(10.0, "베이스 최대 변동폭(%)", group="베이스 조건")

closePosMin = input.float(0.75, "종가 위치 최소값(0~1)", group="강한 종가 조건")

steepMaxPct = input.float(-35.0, "20일 최대 하락률(%) 제한", group="급락속도 조건")

// ── 5일선(SMA) ──
ma5 = ta.sma(close, declineLen)
plot(ma5, title="MA5", color=color.new(color.gray, 0), linewidth=1)

// ── 1. 하락 구간 판단 ──
bearishCount = 0
for i = 1 to declineLen
    if close[i] < open[i]
        bearishCount += 1

majorityBearish = bearishCount >= declineLen - 2
ma5DownOverall  = ma5[declineLen] > ma5

isDeclineZone = majorityBearish or ma5DownOverall

// ── 2. 큰 양봉 확인 (오늘 캔들 제외하고 평균 계산) ──
isBullishCandle = close > open
bodySize   = close - open
avgBody    = ta.sma(math.abs(close[1] - open[1]), bodyLen)
isBigBody  = bodySize > avgBody * bodyMult

volSpike = volume > ta.sma(volume[1], volLen) * volMult

// ── 3. 돌파 확인 (종가 기준, 위꼬리 노이즈 제외) ──
priorHighestClose = ta.highest(close[1], declineLen)
coversDownMove = close > priorHighestClose
aboveMA5 = close > ma5

// ── 4. 과거 20일 하락추세 확인 (오늘 캔들 제외, 어제 기준) ──
regSlope20 = ta.linreg(close[1], trendLen, 0) - ta.linreg(close[1], trendLen, 1)
isDowntrend20 = close[1] < close[1 + trendLen] and regSlope20 < 0

// ── 5. 신호 전 횡보 베이스 확인 (급락 도중 반등 배제) ──
baseHigh = ta.highest(high[1], baseLen)
baseLow  = ta.lowest(low[1], baseLen)
baseRangePct = (baseHigh - baseLow) / baseLow * 100
hasBase = baseRangePct <= baseRangeMax

// ── 6. 종가가 캔들 상단 근처인지 확인 (위꼬리 거부 배제) ──
closePosition = (close - low) / (high - low)
isStrongClose = closePosition >= closePosMin

// ── 7. 최근 하락 속도가 과도하게 가파르지 않은지 확인 (떨어지는 칼날 배제) ──
declineSpeed = (close[1] - close[1 + trendLen]) / close[1 + trendLen] * 100
isNotTooSteep = declineSpeed > steepMaxPct

// ── 최종 신호 ──
signalCond = isDeclineZone and isBullishCandle and isBigBody and volSpike 
     and coversDownMove and aboveMA5 and isDowntrend20 
     and hasBase and isStrongClose and isNotTooSteep

plotshape(signalCond, title="5일하락 돌파", style=shape.triangledown,
     location=location.abovebar, color=color.new(color.lime, 0), size=size.small)

bgcolor(isDeclineZone ? color.new(color.maroon, 92) : na, title="하락구간 배경표시")
```

---

## 5. 112지지매집

### 목적
역배열 상태에서 매집봉(스윙 고점 + 거래량 급증, "끌어올렸다 다시 빼는" 형태)이 발생하고, 20/60일선 위에 안착한 뒤, 켈트너채널 상단을 터치했다가 다시 112일선으로 눌림 지지받는 3단계 시퀀스를 매수 신호로 판정.

### 핵심 파라미터
| 변수 | 기본값 | 설명 |
|---|---|---|
| kcLen / kcAtrLen / kcMult | 20 / 10 / 2.0 | 켈트너채널 EMA·ATR 기간, 배수 |
| pivotLeft / pivotRight | 5 / 5 | 매집봉(피벗 고점) 감지 좌우 봉수 |
| volLen / volMult | 20 / 1.3 | 매집봉 거래량 평균 기간 / 배수 |
| maxStage1Wait | 15 | 1단계 후 KC터치 대기 최대봉수 |
| maxStage2Wait | 15 | 2단계 후 112지지 대기 최대봉수 |
| proximityPct | 3.0 | 112선 근접 허용범위(%) |

### 핵심 로직 (3단계 상태머신)
- **1단계**: `isReverseAlign`(MA112<224<448) + `accumulationBar`(피벗고점 확정 시점의 거래량이 평균×1.3배 이상) + `isAboveShortTerm`(종가>MA20, 종가>MA60) → "돌파" 텍스트 라벨
- **2단계**: 1단계 후 켈트너채널 상단(EMA20+ATR10×2) 터치 → "KC터치" 텍스트 라벨
- **3단계**: 2단계 후 저가가 MA112 ±3% 이내 + 양봉 마감 → "BUY" 초록 삼각형 (매수 신호)
- 손절선: 매수 신호 발생 시 MA112를 손절선으로 설정, 종가가 MA112 아래로 마감하면 "손절(112선 이탈)" 라벨 + 손절선 해제
- 볼린저밴드는 제거되어 있지 않으며, **켈트너채널만 사용** (사용자가 "켈트너채널만" 명시적으로 선택함)

### ⚠️ 미해결 항목
1. **매집봉(`accumulationBar`) 트렌드 필터 미적용**: 실제 차트(디즈니 DIS)에서 상승추세 구간에도 "매집" 라벨이 과다하게 표시되는 문제가 확인됨. 제안된 해결책(택 1) 중 아직 미확정:
   - `accumulationBar`에 `isReverseAlign[pivotRight]` 조건 추가 (피벗 확정 시점이 실제로 역배열 상태였는지 확인)
   - `volMult`를 1.3 → 2.0으로 상향
   - "매집" 라벨 표시를 `accumulationBar` 발생 시점이 아니라 `stage1Trigger` 통과 시점으로 한정
2. **1단계 조건의 시간 관계 불명확**: "매집봉 발생"과 "20/60일선 안착"이 같은 봉에서 동시에 필요한지, 매집봉 발생 후 시간차를 두고 안착하는 흐름을 허용할지 미확정 (현재는 같은 봉 AND 조건)
3. **"덜 엄격한 선" 재정의 이슈**: 대화 후반에 사용자가 "켈트너채널이 아니라 26봉 선행이동 볼린저밴드였다"고 정정했으나, 이 변경은 실제로는 스크립트 1번(ReverseAlign112)에 적용되었고 112지지매집은 켈트너채널을 그대로 유지 중. **112지지매집도 켈트너채널 대신 26봉 선행이동 BB로 바꿀지 확인 필요.**

```pine
// This Pine Script® code is subject to the terms of the Mozilla Public License 2.0 at https://mozilla.org/MPL/2.0/
// © busiruk

//@version=6
indicator("112지지매집", overlay=true)

// ══════════════════════════════════════
// 1. 기술적 지표 설정
// ══════════════════════════════════════

// ── 장기 이동평균선 (역배열 판단용) ──
ma112 = ta.sma(close, 112)
ma224 = ta.sma(close, 224)
ma448 = ta.sma(close, 448)

plot(ma112, title="MA112", color=color.yellow, linewidth=1)
plot(ma224, title="MA224", color=color.green, linewidth=1)
plot(ma448, title="MA448", color=color.red, linewidth=1)

isReverseAlign = ma112 < ma224 and ma224 < ma448   // 112 < 224 < 448 = 역배열(하락정렬)

// ── 단기 추세선 ──
ma20 = ta.sma(close, 20)
ma60 = ta.sma(close, 60)

plot(ma20, title="MA20", color=color.new(color.white, 0), linewidth=1)
plot(ma60, title="MA60", color=color.new(color.orange, 0), linewidth=2)

// ── MA5 ──
ma5 = ta.sma(close, 5)
plot(ma5, title="MA5", color=#00FFAA, linewidth=3)

// ── 켈트너채널 상단 (매수신호 판단용) ──
kcLen    = input.int(20, "켈트너채널 EMA 기간", group="켈트너채널")
kcAtrLen = input.int(10, "켈트너채널 ATR 기간", group="켈트너채널")
kcMult   = input.float(2.0, "켈트너채널 배수", group="켈트너채널")

kcBase  = ta.ema(close, kcLen)
kcAtr   = ta.atr(kcAtrLen)
kcUpper = kcBase + kcAtr * kcMult

plot(kcUpper, title="KC Upper", color=color.new(color.aqua, 0), linewidth=1)

bgcolor(isReverseAlign ? color.new(color.red, 85) : na, title="Reverse Alignment Background")

// ══════════════════════════════════════
// 2. 매집봉(피벗 고점) 감지 — "끌어올렸다가 다시 빼는" 형태
// ══════════════════════════════════════
pivotLeft   = input.int(5, "매집봉 감지 좌측 봉수", group="매집봉 조건")
pivotRight  = input.int(5, "매집봉 감지 우측 봉수(확정 지연)", group="매집봉 조건")
volLen      = input.int(20, "거래량 평균 기간", group="매집봉 조건")
volMult     = input.float(1.3, "매집봉 거래량 배수", group="매집봉 조건")

pivotHighVal = ta.pivothigh(high, pivotLeft, pivotRight)
pivotVolAtPeak = volume[pivotRight]
avgVolAtPeak   = ta.sma(volume, volLen)[pivotRight]

accumulationBar = not na(pivotHighVal) and pivotVolAtPeak > avgVolAtPeak * volMult

var float hillLevel = na
var int   hillBar    = na

if accumulationBar
    hillLevel := pivotHighVal
    hillBar   := bar_index - pivotRight

plotshape(accumulationBar, title="매집봉", style=shape.labeldown,
     location=location.abovebar, offset=-pivotRight,
     color=color.new(#8B7355, 0), textcolor=color.white, text="매집", size=size.tiny)

// ══════════════════════════════════════
// 3. 공구리(20/60일선 안착) 확인
// ══════════════════════════════════════
isAboveShortTerm = close > ma20 and close > ma60   // 20/60일선 안착 (명시적 조건)

// ══════════════════════════════════════
// 4. 3단계 매수 신호 로직
// ══════════════════════════════════════
maxStage1Wait = input.int(15, "1단계(매집+안착) 후 KC터치 대기 최대봉수", group="매수 신호")
maxStage2Wait = input.int(15, "2단계(KC터치) 후 112지지 대기 최대봉수", group="매수 신호")
proximityPct  = input.float(3.0, "112선 근접 허용범위(%)", group="매수 신호")

// ── 1단계: 역배열 상태에서 매집봉 발생 + 20/60일선 안착 ──
stage1Trigger = isReverseAlign and accumulationBar and isAboveShortTerm

var int  stage    = 0   // 0=대기, 1=매집+안착 확인됨, 2=KC터치됨
var int  stageBar = na

if stage1Trigger and stage == 0
    stage    := 1
    stageBar := bar_index

if stage == 1 and (bar_index - stageBar > maxStage1Wait)
    stage := 0

// ── 2단계: 켈트너채널 상단 터치 ──
touchKC = high >= kcUpper

if stage == 1 and touchKC
    stage    := 2
    stageBar := bar_index

if stage == 2 and (bar_index - stageBar > maxStage2Wait)
    stage := 0

// ── 3단계: MA112로 눌림목 지지 확인 → 매수 신호 ──
nearMa112 = math.abs(low - ma112) / ma112 * 100 <= proximityPct
supportBounce = nearMa112 and close > open

buySignal = stage == 2 and supportBounce

if buySignal
    stage := 0

plotshape(buySignal, title="112지지 매수", style=shape.triangleup,
     location=location.belowbar, color=color.new(color.lime, 0),
     size=size.small, text="BUY")

// 단계 진행 상황 참고 표시
plotshape(stage1Trigger, title="1단계:매집+안착", style=shape.labelup,
     location=location.top, color=color.new(color.yellow, 0),
     textcolor=color.black, text="돌파", size=size.tiny)
plotshape(stage == 1 and touchKC, title="2단계:KC터치", style=shape.labelup,
     location=location.top, color=color.new(color.aqua, 0),
     textcolor=color.black, text="KC터치", size=size.tiny)

// ══════════════════════════════════════
// 5. 손절선
// ══════════════════════════════════════
var float stop_loss = na
var bool  inPosition = false

if buySignal and not inPosition
    stop_loss  := ma112
    inPosition := true

stopHit = inPosition and close < ma112

if stopHit
    label.new(bar_index, low, "손절\n(112선 이탈)", color=color.new(color.red, 0),
         textcolor=color.white, style=label.style_label_up, size=size.small)
    stop_loss  := na
    inPosition := false

plot(inPosition ? stop_loss : na, title="손절선(112선)", color=color.new(color.red, 0),
     style=plot.style_circles, linewidth=1)

// ══════════════════════════════════════
// 각 선 이름을 마지막 봉 오른쪽에 라벨로 표시
// ══════════════════════════════════════
if barstate.islast
    label.new(bar_index + 1, kcUpper, "KC Upper",
         color=color.new(color.aqua, 0), textcolor=color.black,
         style=label.style_label_left, size=size.small)

    label.new(bar_index + 1, ma112, "MA112",
         color=color.new(color.yellow, 0), textcolor=color.black,
         style=label.style_label_left, size=size.small)

    label.new(bar_index + 1, ma224, "MA224",
         color=color.new(color.green, 0), textcolor=color.white,
         style=label.style_label_left, size=size.small)

    label.new(bar_index + 1, ma448, "MA448",
         color=color.new(color.red, 0), textcolor=color.white,
         style=label.style_label_left, size=size.small)

    label.new(bar_index + 1, ma5, "MA5",
         color=color.new(#00FFAA, 0), textcolor=color.black,
         style=label.style_label_left, size=size.small)

    label.new(bar_index + 1, ma20, "MA20",
         color=color.new(color.white, 0), textcolor=color.black,
         style=label.style_label_left, size=size.small)

    label.new(bar_index + 1, ma60, "MA60",
         color=color.new(color.orange, 0), textcolor=color.white,
         style=label.style_label_left, size=size.small)

    label.new(bar_index + 1, (ma112 + ma448) / 2,
         isReverseAlign ? "Reverse Align" : "Not Reverse Align",
         color=color.new(isReverseAlign ? color.red : color.gray, 0),
         textcolor=color.white, style=label.style_label_left, size=size.small)
```

---

## 공통 배경 지식 (Claude Code 인수인계용)

### 이평선 기간 관례 (시장별)
- **한국(112/224/448)**: 특정 유튜버("단테")의 커스텀 설정. 표준값 120/240을 살짝 줄인 것으로, 공인된 표준은 아님. 한국 개인투자자 표준은 5/10/20/60/120일.
- **미국**: 50일(중기), 200일(장기)이 압도적 표준. 미국 종목 분석 시 112/224/448 대신 50/200 사용을 권장.
- **일본**: 5일(1주)/25일(1개월)/75일(1분기) 조합이 증권사 공식 표준.

### 매매 전략 맥락
- 사용자는 1-6주 보유 스윙 전략을 지향하며, NISA(일본 비과세 계좌) 한도 소진 문제로 단중기 스윙 중심 운용 방침을 세움.
- 미국주식 스캘핑은 일본시간 22:30~23:30(미국장 시가 직후 1시간)로 제한하는 규칙을 운용 중.

### 아직 전략(strategy) 미변환
현재까지 만든 모든 스크립트는 `indicator()`로, 신호만 시각화할 뿐 백테스트(승률/손익비)는 계산하지 않음. `strategy()`로 변환하면 Strategy Tester에서 자동 검증 가능 — 필요 시 Claude Code에서 변환 작업 진행 가능.
