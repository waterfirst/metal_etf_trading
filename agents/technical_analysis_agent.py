"""
기술적 분석 에이전트
- RSI, MACD, 볼린저밴드, 이동평균선 분석
- 매매 시그널 생성
- 추세 판단
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    """매매 시그널"""
    name: str
    value: str          # "강력매수", "매수", "중립", "매도", "강력매도"
    score: int          # 1~5 (5=강력매수)
    description: str
    indicator_value: float = 0.0


class TechnicalAnalysisAgent:
    """기술적 분석 에이전트"""

    def analyze_all(self, price_data: Dict[str, pd.DataFrame]) -> Dict[str, Dict]:
        """전체 ETF에 대한 기술적 분석 수행"""
        results = {}
        for name, df in price_data.items():
            if df.empty or len(df) < 30:
                logger.warning(f"{name}: 데이터 부족 (최소 30일 필요, 현재 {len(df)}일)")
                continue
            try:
                results[name] = self.analyze_single(name, df)
            except Exception as e:
                logger.error(f"{name} 분석 실패: {e}")
        return results

    def analyze_single(self, name: str, df: pd.DataFrame) -> Dict:
        """단일 ETF 기술적 분석"""
        close = df["Close"].astype(float)
        volume = df["Volume"].astype(float) if "Volume" in df.columns else None

        signals = []

        # 1. RSI 분석
        rsi = self._calculate_rsi(close)
        if rsi is not None:
            signals.append(self._interpret_rsi(rsi))

        # 2. MACD 분석
        macd_line, signal_line, histogram = self._calculate_macd(close)
        if macd_line is not None:
            signals.append(self._interpret_macd(macd_line, signal_line, histogram))

        # 3. 볼린저밴드 분석
        upper, middle, lower = self._calculate_bollinger(close)
        if upper is not None:
            signals.append(self._interpret_bollinger(close, upper, middle, lower))

        # 4. 이동평균선 분석
        signals.append(self._analyze_moving_averages(close))

        # 5. 거래량 분석
        if volume is not None and len(volume) > 20:
            signals.append(self._analyze_volume(close, volume))

        # 6. 스토캐스틱
        if len(df) > 14 and "High" in df.columns and "Low" in df.columns:
            stoch = self._calculate_stochastic(df)
            if stoch is not None:
                signals.append(stoch)

        # 종합 점수 계산
        valid_signals = [s for s in signals if s is not None]
        avg_score = np.mean([s.score for s in valid_signals]) if valid_signals else 3.0

        if avg_score >= 4.2:
            overall = "강력매수"
        elif avg_score >= 3.5:
            overall = "매수"
        elif avg_score >= 2.5:
            overall = "중립"
        elif avg_score >= 1.8:
            overall = "매도"
        else:
            overall = "강력매도"

        # 추세 판단
        trend = self._determine_trend(close)

        return {
            "종목명": name,
            "종합판단": overall,
            "종합점수": round(avg_score, 2),
            "추세": trend,
            "시그널": [
                {
                    "지표": s.name,
                    "판단": s.value,
                    "점수": s.score,
                    "설명": s.description,
                    "값": s.indicator_value,
                }
                for s in valid_signals
            ],
            "기술지표": {
                "RSI": round(rsi, 2) if rsi is not None else None,
                "MACD": round(float(macd_line), 4) if macd_line is not None else None,
                "MACD_시그널": round(float(signal_line), 4) if signal_line is not None else None,
                "볼린저_상단": round(float(upper), 0) if upper is not None else None,
                "볼린저_하단": round(float(lower), 0) if lower is not None else None,
                "현재가": round(float(close.iloc[-1]), 0),
            },
        }

    def _calculate_rsi(self, close: pd.Series, period: int = 14) -> Optional[float]:
        """RSI 계산"""
        if len(close) < period + 1:
            return None
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)

        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1])

    def _interpret_rsi(self, rsi: float) -> Signal:
        """RSI 해석"""
        if rsi <= 20:
            return Signal("RSI", "강력매수", 5, f"RSI {rsi:.1f} - 극심한 과매도 구간", rsi)
        elif rsi <= 30:
            return Signal("RSI", "매수", 4, f"RSI {rsi:.1f} - 과매도 구간 진입", rsi)
        elif rsi <= 45:
            return Signal("RSI", "중립(매수편향)", 3, f"RSI {rsi:.1f} - 중립 하단", rsi)
        elif rsi <= 55:
            return Signal("RSI", "중립", 3, f"RSI {rsi:.1f} - 중립 구간", rsi)
        elif rsi <= 70:
            return Signal("RSI", "중립(매도편향)", 3, f"RSI {rsi:.1f} - 중립 상단", rsi)
        elif rsi <= 80:
            return Signal("RSI", "매도", 2, f"RSI {rsi:.1f} - 과매수 구간 진입", rsi)
        else:
            return Signal("RSI", "강력매도", 1, f"RSI {rsi:.1f} - 극심한 과매수 구간", rsi)

    def _calculate_macd(self, close: pd.Series) -> Tuple:
        """MACD 계산"""
        if len(close) < 35:
            return None, None, None
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9).mean()
        histogram = macd_line - signal_line
        return float(macd_line.iloc[-1]), float(signal_line.iloc[-1]), float(histogram.iloc[-1])

    def _interpret_macd(self, macd: float, signal: float, histogram: float) -> Signal:
        """MACD 해석"""
        prev_hist_positive = histogram > 0

        if macd > signal and histogram > 0:
            if macd > 0:
                return Signal("MACD", "강력매수", 5,
                             "MACD 양전환 + 시그널 상향돌파", histogram)
            return Signal("MACD", "매수", 4,
                         "MACD 시그널 상향돌파 (골든크로스)", histogram)
        elif macd < signal and histogram < 0:
            if macd < 0:
                return Signal("MACD", "강력매도", 1,
                             "MACD 음전환 + 시그널 하향돌파", histogram)
            return Signal("MACD", "매도", 2,
                         "MACD 시그널 하향돌파 (데드크로스)", histogram)
        else:
            return Signal("MACD", "중립", 3,
                         f"MACD: {macd:.4f}, 시그널: {signal:.4f}", histogram)

    def _calculate_bollinger(self, close: pd.Series, period: int = 20, std_mult: float = 2.0) -> Tuple:
        """볼린저밴드 계산"""
        if len(close) < period:
            return None, None, None
        middle = close.rolling(window=period).mean()
        std = close.rolling(window=period).std()
        upper = middle + std_mult * std
        lower = middle - std_mult * std
        return float(upper.iloc[-1]), float(middle.iloc[-1]), float(lower.iloc[-1])

    def _interpret_bollinger(self, close: pd.Series, upper: float, middle: float, lower: float) -> Signal:
        """볼린저밴드 해석"""
        current = float(close.iloc[-1])
        band_width = upper - lower
        position = (current - lower) / band_width if band_width > 0 else 0.5

        if current <= lower:
            return Signal("볼린저밴드", "강력매수", 5,
                         f"하단 이탈 (밴드 위치: {position:.1%})", position)
        elif current < lower + 0.2 * band_width:
            return Signal("볼린저밴드", "매수", 4,
                         f"하단 근접 (밴드 위치: {position:.1%})", position)
        elif current > upper:
            return Signal("볼린저밴드", "강력매도", 1,
                         f"상단 이탈 (밴드 위치: {position:.1%})", position)
        elif current > upper - 0.2 * band_width:
            return Signal("볼린저밴드", "매도", 2,
                         f"상단 근접 (밴드 위치: {position:.1%})", position)
        else:
            return Signal("볼린저밴드", "중립", 3,
                         f"밴드 중간 (밴드 위치: {position:.1%})", position)

    def _analyze_moving_averages(self, close: pd.Series) -> Signal:
        """이동평균선 분석"""
        current = float(close.iloc[-1])

        ma5 = float(close.tail(5).mean())
        ma20 = float(close.tail(20).mean()) if len(close) >= 20 else None
        ma60 = float(close.tail(60).mean()) if len(close) >= 60 else None
        ma120 = float(close.tail(120).mean()) if len(close) >= 120 else None

        score = 3  # 중립 시작
        reasons = []

        if ma20:
            if current > ma20:
                score += 0.5
                reasons.append("20일선 위")
            else:
                score -= 0.5
                reasons.append("20일선 아래")

        if ma60:
            if current > ma60:
                score += 0.5
                reasons.append("60일선 위")
            else:
                score -= 0.5
                reasons.append("60일선 아래")

        if ma120:
            if current > ma120:
                score += 0.5
                reasons.append("120일선 위")
            else:
                score -= 0.5
                reasons.append("120일선 아래")

        # 정배열 / 역배열 확인
        if ma20 and ma60 and ma120:
            if ma5 > ma20 > ma60 > ma120:
                score = min(5, score + 0.5)
                reasons.append("정배열")
            elif ma5 < ma20 < ma60 < ma120:
                score = max(1, score - 0.5)
                reasons.append("역배열")

        score = max(1, min(5, round(score)))
        labels = {5: "강력매수", 4: "매수", 3: "중립", 2: "매도", 1: "강력매도"}

        return Signal("이동평균선", labels[score], score,
                      ", ".join(reasons) if reasons else "분석 데이터 부족",
                      current)

    def _analyze_volume(self, close: pd.Series, volume: pd.Series) -> Optional[Signal]:
        """거래량 분석"""
        if len(volume) < 20:
            return None

        avg_vol_20 = float(volume.tail(20).mean())
        recent_vol = float(volume.iloc[-1])
        vol_ratio = recent_vol / avg_vol_20 if avg_vol_20 > 0 else 1.0

        price_change = (float(close.iloc[-1]) - float(close.iloc[-2])) / float(close.iloc[-2])

        if vol_ratio > 2.0 and price_change > 0.01:
            return Signal("거래량", "강력매수", 5,
                         f"거래량 급증({vol_ratio:.1f}배) + 가격 상승", vol_ratio)
        elif vol_ratio > 1.5 and price_change > 0:
            return Signal("거래량", "매수", 4,
                         f"거래량 증가({vol_ratio:.1f}배) + 가격 상승", vol_ratio)
        elif vol_ratio > 2.0 and price_change < -0.01:
            return Signal("거래량", "강력매도", 1,
                         f"거래량 급증({vol_ratio:.1f}배) + 가격 하락", vol_ratio)
        elif vol_ratio > 1.5 and price_change < 0:
            return Signal("거래량", "매도", 2,
                         f"거래량 증가({vol_ratio:.1f}배) + 가격 하락", vol_ratio)
        else:
            return Signal("거래량", "중립", 3,
                         f"거래량 보통 ({vol_ratio:.1f}배)", vol_ratio)

    def _calculate_stochastic(self, df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> Optional[Signal]:
        """스토캐스틱 계산 및 해석"""
        if len(df) < k_period:
            return None

        high = df["High"].astype(float)
        low = df["Low"].astype(float)
        close = df["Close"].astype(float)

        lowest_low = low.rolling(window=k_period).min()
        highest_high = high.rolling(window=k_period).max()

        denominator = highest_high - lowest_low
        denominator = denominator.replace(0, np.nan)
        k = 100 * (close - lowest_low) / denominator
        d = k.rolling(window=d_period).mean()

        k_val = float(k.iloc[-1])
        d_val = float(d.iloc[-1])

        if k_val <= 20 and k_val > d_val:
            return Signal("스토캐스틱", "강력매수", 5,
                         f"K={k_val:.1f}, D={d_val:.1f} - 과매도 + 골든크로스", k_val)
        elif k_val <= 30:
            return Signal("스토캐스틱", "매수", 4,
                         f"K={k_val:.1f}, D={d_val:.1f} - 과매도 구간", k_val)
        elif k_val >= 80 and k_val < d_val:
            return Signal("스토캐스틱", "강력매도", 1,
                         f"K={k_val:.1f}, D={d_val:.1f} - 과매수 + 데드크로스", k_val)
        elif k_val >= 70:
            return Signal("스토캐스틱", "매도", 2,
                         f"K={k_val:.1f}, D={d_val:.1f} - 과매수 구간", k_val)
        else:
            return Signal("스토캐스틱", "중립", 3,
                         f"K={k_val:.1f}, D={d_val:.1f}", k_val)

    def _determine_trend(self, close: pd.Series) -> str:
        """추세 판단"""
        if len(close) < 60:
            return "판단불가"

        ma20 = close.rolling(20).mean()
        ma60 = close.rolling(60).mean()

        current = float(close.iloc[-1])
        ma20_now = float(ma20.iloc[-1])
        ma60_now = float(ma60.iloc[-1])

        ma20_slope = (float(ma20.iloc[-1]) - float(ma20.iloc[-5])) / float(ma20.iloc[-5]) if len(ma20) > 5 else 0

        if current > ma20_now > ma60_now and ma20_slope > 0:
            return "강한 상승추세"
        elif current > ma20_now and ma20_slope > 0:
            return "상승추세"
        elif current < ma20_now < ma60_now and ma20_slope < 0:
            return "강한 하락추세"
        elif current < ma20_now and ma20_slope < 0:
            return "하락추세"
        else:
            return "횡보/조정"
