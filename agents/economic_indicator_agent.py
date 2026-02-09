"""
경제지표 분석 에이전트
- 거시경제 지표 분석
- 시장 환경 판단
- 금리/환율/변동성 영향 분석
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class MacroSignal:
    """거시경제 시그널"""
    indicator: str
    current_value: float
    trend: str          # "상승", "하락", "횡보"
    impact: str         # "긍정", "부정", "중립"
    impact_target: str  # 영향받는 자산
    description: str
    score: int          # 1~5


class EconomicIndicatorAgent:
    """경제지표 분석 에이전트"""

    def analyze(self, indicator_data: Dict[str, pd.DataFrame]) -> Dict:
        """전체 경제지표 분석"""
        signals = []

        # 1. 달러/원 환율 분석
        if "USD/KRW" in indicator_data:
            sig = self._analyze_usd_krw(indicator_data["USD/KRW"])
            if sig:
                signals.append(sig)

        # 2. 미국 국채금리 분석
        if "미국 10년 국채" in indicator_data:
            sig = self._analyze_us_treasury(indicator_data["미국 10년 국채"])
            if sig:
                signals.append(sig)

        # 3. VIX 분석
        if "VIX" in indicator_data:
            sig = self._analyze_vix(indicator_data["VIX"])
            if sig:
                signals.append(sig)

        # 4. 달러인덱스 분석
        if "달러인덱스" in indicator_data:
            sig = self._analyze_dollar_index(indicator_data["달러인덱스"])
            if sig:
                signals.append(sig)

        # 5. KOSPI/KOSDAQ 분석
        kospi_sig = self._analyze_index(indicator_data.get("KOSPI"), "KOSPI")
        if kospi_sig:
            signals.append(kospi_sig)
        kosdaq_sig = self._analyze_index(indicator_data.get("KOSDAQ"), "KOSDAQ")
        if kosdaq_sig:
            signals.append(kosdaq_sig)

        # 6. S&P 500 분석
        sp500_sig = self._analyze_index(indicator_data.get("S&P 500"), "S&P 500")
        if sp500_sig:
            signals.append(sp500_sig)

        # 7. 금 선물 분석
        if "금 선물" in indicator_data:
            sig = self._analyze_gold(indicator_data["금 선물"])
            if sig:
                signals.append(sig)

        # 8. 원유 분석
        if "WTI 원유" in indicator_data:
            sig = self._analyze_oil(indicator_data["WTI 원유"])
            if sig:
                signals.append(sig)

        # 시장 환경 종합 판단
        market_regime = self._determine_market_regime(signals)

        return {
            "시그널": [
                {
                    "지표": s.indicator,
                    "현재값": s.current_value,
                    "추세": s.trend,
                    "영향": s.impact,
                    "영향대상": s.impact_target,
                    "설명": s.description,
                    "점수": s.score,
                }
                for s in signals
            ],
            "시장환경": market_regime,
        }

    def _get_trend(self, close: pd.Series, period: int = 20) -> str:
        """추세 판단"""
        if len(close) < period:
            return "판단불가"
        recent = float(close.iloc[-1])
        past = float(close.iloc[-period])
        change = (recent - past) / past
        if change > 0.02:
            return "상승"
        elif change < -0.02:
            return "하락"
        return "횡보"

    def _analyze_usd_krw(self, df: pd.DataFrame) -> Optional[MacroSignal]:
        """달러/원 환율 분석"""
        if df.empty:
            return None
        close = df["Close"].astype(float)
        current = float(close.iloc[-1])
        trend = self._get_trend(close)

        # 환율 수준 판단
        if current > 1400:
            impact = "부정"
            desc = f"원화 약세 ({current:.0f}원) - 해외투자 환차손 위험, 수출주에 긍정적"
            score = 2
        elif current > 1300:
            impact = "중립"
            desc = f"환율 보통 수준 ({current:.0f}원)"
            score = 3
        else:
            impact = "긍정"
            desc = f"원화 강세 ({current:.0f}원) - 해외투자 환차익 기대"
            score = 4

        if trend == "상승":
            desc += " | 환율 상승 추세 (원화 약세 진행)"
            score = max(1, score - 1)
        elif trend == "하락":
            desc += " | 환율 하락 추세 (원화 강세 진행)"
            score = min(5, score + 1)

        return MacroSignal("USD/KRW", current, trend, impact, "해외주식ETF", desc, score)

    def _analyze_us_treasury(self, df: pd.DataFrame) -> Optional[MacroSignal]:
        """미국 국채금리 분석"""
        if df.empty:
            return None
        close = df["Close"].astype(float)
        current = float(close.iloc[-1])
        trend = self._get_trend(close)

        if current > 4.5:
            impact = "부정"
            desc = f"고금리 환경 ({current:.2f}%) - 성장주/채권 부정적, 고배당주 상대적 매력 감소"
            score = 2
        elif current > 3.5:
            impact = "중립"
            desc = f"금리 보통 수준 ({current:.2f}%)"
            score = 3
        else:
            impact = "긍정"
            desc = f"저금리 환경 ({current:.2f}%) - 성장주/채권 긍정적"
            score = 4

        return MacroSignal("미국 10년 국채금리", current, trend, impact,
                          "성장주/채권", desc, score)

    def _analyze_vix(self, df: pd.DataFrame) -> Optional[MacroSignal]:
        """VIX 공포지수 분석"""
        if df.empty:
            return None
        close = df["Close"].astype(float)
        current = float(close.iloc[-1])
        trend = self._get_trend(close, period=5)

        if current > 30:
            impact = "위험"
            desc = f"VIX {current:.1f} - 극심한 공포 구간. 역발상 매수 기회 가능성"
            score = 2  # 위험하지만 역발상 기회
        elif current > 20:
            impact = "주의"
            desc = f"VIX {current:.1f} - 불안정한 시장"
            score = 2
        elif current > 15:
            impact = "중립"
            desc = f"VIX {current:.1f} - 정상 범위"
            score = 3
        else:
            impact = "긍정"
            desc = f"VIX {current:.1f} - 안정적 시장 (과도한 낙관 주의)"
            score = 4

        return MacroSignal("VIX", current, trend, impact, "전체시장", desc, score)

    def _analyze_dollar_index(self, df: pd.DataFrame) -> Optional[MacroSignal]:
        """달러인덱스 분석"""
        if df.empty:
            return None
        close = df["Close"].astype(float)
        current = float(close.iloc[-1])
        trend = self._get_trend(close)

        if current > 105:
            impact = "부정"
            desc = f"달러 강세 ({current:.1f}) - 신흥국/원자재 부정적"
            score = 2
        elif current > 100:
            impact = "중립"
            desc = f"달러 보통 ({current:.1f})"
            score = 3
        else:
            impact = "긍정"
            desc = f"달러 약세 ({current:.1f}) - 신흥국/원자재 긍정적"
            score = 4

        return MacroSignal("달러인덱스", current, trend, impact, "원자재/신흥국", desc, score)

    def _analyze_index(self, df: Optional[pd.DataFrame], name: str) -> Optional[MacroSignal]:
        """주가지수 분석"""
        if df is None or df.empty:
            return None
        close = df["Close"].astype(float)
        current = float(close.iloc[-1])
        trend = self._get_trend(close)

        # 이동평균 기반 판단
        ma20 = float(close.tail(20).mean()) if len(close) >= 20 else current
        ma60 = float(close.tail(60).mean()) if len(close) >= 60 else current

        if current > ma20 > ma60:
            impact = "긍정"
            desc = f"{name} {current:,.0f} - 상승추세 (20일선/60일선 위)"
            score = 4
        elif current > ma20:
            impact = "중립"
            desc = f"{name} {current:,.0f} - 20일선 위, 60일선 근접"
            score = 3
        elif current < ma20 < ma60:
            impact = "부정"
            desc = f"{name} {current:,.0f} - 하락추세 (20일선/60일선 아래)"
            score = 2
        else:
            impact = "중립"
            desc = f"{name} {current:,.0f} - 혼조세"
            score = 3

        target = "국내주식" if name in ("KOSPI", "KOSDAQ") else "해외주식"
        return MacroSignal(name, current, trend, impact, target, desc, score)

    def _analyze_gold(self, df: pd.DataFrame) -> Optional[MacroSignal]:
        """금 가격 분석"""
        if df.empty:
            return None
        close = df["Close"].astype(float)
        current = float(close.iloc[-1])
        trend = self._get_trend(close)

        if trend == "상승":
            impact = "긍정"
            desc = f"금 ${current:,.0f} - 상승추세 (안전자산 선호 or 인플레이션 헤지)"
            score = 4
        elif trend == "하락":
            impact = "부정"
            desc = f"금 ${current:,.0f} - 하락추세 (위험자산 선호)"
            score = 2
        else:
            impact = "중립"
            desc = f"금 ${current:,.0f} - 횡보"
            score = 3

        return MacroSignal("금 선물", current, trend, impact, "금ETF", desc, score)

    def _analyze_oil(self, df: pd.DataFrame) -> Optional[MacroSignal]:
        """원유 가격 분석"""
        if df.empty:
            return None
        close = df["Close"].astype(float)
        current = float(close.iloc[-1])
        trend = self._get_trend(close)

        if current > 90:
            desc = f"WTI ${current:.1f} - 고유가 (인플레이션 우려, 에너지주 긍정)"
            score = 2
        elif current > 70:
            desc = f"WTI ${current:.1f} - 보통 수준"
            score = 3
        else:
            desc = f"WTI ${current:.1f} - 저유가 (경기침체 우려 or 소비자 긍정)"
            score = 3

        return MacroSignal("WTI 원유", current, trend, "중립", "전체시장", desc, score)

    def _determine_market_regime(self, signals: List[MacroSignal]) -> Dict:
        """시장 환경 종합 판단"""
        if not signals:
            return {"판단": "데이터부족", "설명": "분석할 지표 데이터가 부족합니다"}

        avg_score = np.mean([s.score for s in signals])

        positive_count = sum(1 for s in signals if s.impact in ("긍정",))
        negative_count = sum(1 for s in signals if s.impact in ("부정", "위험", "주의"))

        if avg_score >= 3.5 and positive_count > negative_count:
            regime = "위험자산 선호 (Risk-On)"
            recommendation = "주식 비중 확대, 채권/금 비중 축소 권고"
        elif avg_score <= 2.5 or negative_count > positive_count * 2:
            regime = "안전자산 선호 (Risk-Off)"
            recommendation = "채권/금 비중 확대, 주식 비중 축소 권고"
        else:
            regime = "혼조세 (Mixed)"
            recommendation = "현재 비중 유지, 선별적 리밸런싱 권고"

        return {
            "판단": regime,
            "평균점수": round(avg_score, 2),
            "긍정지표수": positive_count,
            "부정지표수": negative_count,
            "권고": recommendation,
        }
