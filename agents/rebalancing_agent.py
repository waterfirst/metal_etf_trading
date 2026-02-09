"""
리밸런싱 에이전트
- 포트폴리오 최적화
- 리밸런싱 추천
- 위험 관리
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging

from config.portfolio import (
    REBALANCING_CONSTRAINTS,
    ETF_SECTORS,
    ASSET_CLASSES,
)

logger = logging.getLogger(__name__)


@dataclass
class RebalancingAction:
    """리밸런싱 액션"""
    etf_name: str
    action: str          # "매수", "매도", "유지"
    current_weight: float
    target_weight: float
    weight_change: float
    estimated_amount: int  # 변경 금액 (원)
    reason: str
    priority: int        # 1=높음, 2=중간, 3=낮음


class RebalancingAgent:
    """리밸런싱 에이전트"""

    def __init__(self):
        self.constraints = REBALANCING_CONSTRAINTS

    def generate_recommendations(
        self,
        portfolio_valuation: List[Dict],
        technical_signals: Dict[str, Dict],
        economic_analysis: Dict,
        news_sentiment: Dict,
    ) -> List[Dict]:
        """계좌별 리밸런싱 추천 생성"""
        recommendations = []

        for account in portfolio_valuation:
            rec = self._analyze_account(
                account, technical_signals, economic_analysis, news_sentiment
            )
            recommendations.append(rec)

        return recommendations

    def _analyze_account(
        self,
        account: Dict,
        technical_signals: Dict[str, Dict],
        economic_analysis: Dict,
        news_sentiment: Dict,
    ) -> Dict:
        """계좌 분석 및 리밸런싱 추천"""
        account_name = account["계좌명"]
        total_value = account["총평가액"]
        holdings = account["보유종목"]

        # 현재 자산배분 분석
        current_allocation = self._get_current_allocation(holdings)

        # 목표 자산배분 계산
        target_allocation = self._calculate_target_allocation(
            account_name, holdings, technical_signals, economic_analysis, news_sentiment
        )

        # 리밸런싱 액션 생성
        actions = self._generate_actions(
            holdings, target_allocation, total_value, technical_signals
        )

        # 위험 분석
        risk_warnings = self._check_risk_warnings(
            account_name, holdings, current_allocation
        )

        return {
            "계좌명": account_name,
            "총평가액": total_value,
            "현재배분": current_allocation,
            "목표배분": target_allocation,
            "리밸런싱_액션": [
                {
                    "종목": a.etf_name,
                    "액션": a.action,
                    "현재비중": f"{a.current_weight:.1%}",
                    "목표비중": f"{a.target_weight:.1%}",
                    "비중변경": f"{a.weight_change:+.1%}",
                    "예상금액": f"{a.estimated_amount:,}원",
                    "사유": a.reason,
                    "우선순위": a.priority,
                }
                for a in sorted(actions, key=lambda x: x.priority)
            ],
            "위험경고": risk_warnings,
        }

    def _get_current_allocation(self, holdings: List[Dict]) -> Dict:
        """현재 자산배분 분석"""
        asset_allocation = {}
        sector_allocation = {}

        for h in holdings:
            asset_type = h["자산유형"]
            sector = h["섹터"]
            weight = h["비중"]

            asset_allocation[asset_type] = asset_allocation.get(asset_type, 0) + weight
            sector_allocation[sector] = sector_allocation.get(sector, 0) + weight

        return {
            "자산유형별": asset_allocation,
            "섹터별": sector_allocation,
        }

    def _calculate_target_allocation(
        self,
        account_name: str,
        holdings: List[Dict],
        technical_signals: Dict,
        economic_analysis: Dict,
        news_sentiment: Dict,
    ) -> Dict[str, float]:
        """목표 자산배분 계산"""
        targets = {}
        total_weight = 0

        market_regime = economic_analysis.get("시장환경", {})
        regime_type = market_regime.get("판단", "혼조세")

        # 시장 환경에 따른 기본 방향
        if "Risk-On" in regime_type:
            equity_bias = 0.03    # 주식 비중 약간 확대
            safe_bias = -0.02     # 안전자산 비중 축소
        elif "Risk-Off" in regime_type:
            equity_bias = -0.03   # 주식 비중 축소
            safe_bias = 0.03      # 안전자산 비중 확대
        else:
            equity_bias = 0
            safe_bias = 0

        for h in holdings:
            name = h["종목명"]
            current_weight = h["비중"]
            asset_type = h["자산유형"]
            sector = h["섹터"]

            # 기술적 분석 기반 조정
            tech_adjustment = 0
            if name in technical_signals:
                tech_score = technical_signals[name].get("종합점수", 3)
                tech_adjustment = (tech_score - 3) * 0.01  # 점수 1당 1%

            # 자산유형별 시장환경 조정
            market_adjustment = 0
            if asset_type in ("국내주식", "해외주식"):
                market_adjustment = equity_bias
            elif asset_type in ("원자재", "채권혼합", "TDF"):
                market_adjustment = safe_bias

            # 뉴스 감성 기반 조정
            news_adj = 0
            sentiment = news_sentiment.get("종합감성", "중립")
            if sentiment == "긍정" and asset_type in ("국내주식", "해외주식"):
                news_adj = 0.005
            elif sentiment == "부정" and asset_type in ("국내주식", "해외주식"):
                news_adj = -0.005

            # 과도한 집중 방지
            concentration_adj = 0
            if current_weight > self.constraints["max_single_etf_weight"]:
                concentration_adj = -(current_weight - self.constraints["max_single_etf_weight"]) * 0.5

            target = current_weight + tech_adjustment + market_adjustment + news_adj + concentration_adj
            target = max(0.02, min(0.30, target))  # 최소 2%, 최대 30%
            targets[name] = target
            total_weight += target

        # 비중 합계 정규화 (100%)
        if total_weight > 0:
            for name in targets:
                targets[name] /= total_weight

        return targets

    def _generate_actions(
        self,
        holdings: List[Dict],
        target_allocation: Dict[str, float],
        total_value: float,
        technical_signals: Dict,
    ) -> List[RebalancingAction]:
        """리밸런싱 액션 생성"""
        actions = []

        for h in holdings:
            name = h["종목명"]
            current_weight = h["비중"]
            target_weight = target_allocation.get(name, current_weight)
            weight_change = target_weight - current_weight
            amount_change = int(weight_change * total_value)

            # 변동이 작으면 유지
            if abs(weight_change) < 0.01:  # 1% 미만 변동은 무시
                actions.append(RebalancingAction(
                    etf_name=name,
                    action="유지",
                    current_weight=current_weight,
                    target_weight=target_weight,
                    weight_change=weight_change,
                    estimated_amount=0,
                    reason="현재 비중 적정",
                    priority=3,
                ))
                continue

            # 매수/매도 판단
            if weight_change > 0:
                action = "매수"
                reason = self._get_buy_reason(name, technical_signals, weight_change)
                priority = 1 if weight_change > 0.03 else 2
            else:
                action = "매도"
                reason = self._get_sell_reason(name, technical_signals, weight_change)
                priority = 1 if abs(weight_change) > 0.03 else 2

            actions.append(RebalancingAction(
                etf_name=name,
                action=action,
                current_weight=current_weight,
                target_weight=target_weight,
                weight_change=weight_change,
                estimated_amount=abs(amount_change),
                reason=reason,
                priority=priority,
            ))

        return actions

    def _get_buy_reason(self, name: str, signals: Dict, weight_change: float) -> str:
        """매수 사유 생성"""
        reasons = []
        if name in signals:
            judgment = signals[name].get("종합판단", "")
            trend = signals[name].get("추세", "")
            if "매수" in judgment:
                reasons.append(f"기술적 {judgment}")
            if "상승" in trend:
                reasons.append(trend)

        if weight_change > 0.03:
            reasons.append("비중 확대 필요")

        return " / ".join(reasons) if reasons else "리밸런싱 비중 조정"

    def _get_sell_reason(self, name: str, signals: Dict, weight_change: float) -> str:
        """매도 사유 생성"""
        reasons = []
        if name in signals:
            judgment = signals[name].get("종합판단", "")
            trend = signals[name].get("추세", "")
            if "매도" in judgment:
                reasons.append(f"기술적 {judgment}")
            if "하락" in trend:
                reasons.append(trend)

        if abs(weight_change) > 0.03:
            reasons.append("비중 축소 필요")

        return " / ".join(reasons) if reasons else "리밸런싱 비중 조정"

    def _check_risk_warnings(
        self, account_name: str, holdings: List[Dict], allocation: Dict
    ) -> List[str]:
        """위험 경고 확인"""
        warnings = []

        # 1. 단일 종목 집중 위험
        for h in holdings:
            if h["비중"] > self.constraints["max_single_etf_weight"]:
                warnings.append(
                    f"⚠️ {h['종목명']} 비중 {h['비중']:.1%}로 "
                    f"권고치({self.constraints['max_single_etf_weight']:.0%}) 초과"
                )

        # 2. 섹터 집중 위험
        for sector, weight in allocation.get("섹터별", {}).items():
            if weight > self.constraints["max_sector_weight"]:
                warnings.append(
                    f"⚠️ {sector} 섹터 비중 {weight:.1%}로 "
                    f"권고치({self.constraints['max_sector_weight']:.0%}) 초과"
                )

        # 3. DC형 해외주식 비중 확인
        if "DC" in account_name:
            foreign = allocation.get("자산유형별", {}).get("해외주식", 0)
            if foreign > self.constraints["max_foreign_equity_dc"]:
                warnings.append(
                    f"⚠️ 퇴직연금 DC 해외주식 비중 {foreign:.1%}로 "
                    f"권고치({self.constraints['max_foreign_equity_dc']:.0%}) 초과"
                )

        # 4. 분산투자 부족
        asset_types = allocation.get("자산유형별", {})
        if len(asset_types) < 3:
            warnings.append("⚠️ 자산유형 분산 부족 (최소 3개 이상 권고)")

        if not warnings:
            warnings.append("✅ 특별한 위험 경고 없음")

        return warnings

    def calculate_portfolio_metrics(
        self, price_data: Dict[str, pd.DataFrame], holdings: List[Dict]
    ) -> Dict:
        """포트폴리오 성과 지표 계산"""
        # 포트폴리오 수익률 계산
        returns_dict = {}
        weights = {}

        for h in holdings:
            name = h["종목명"]
            if name in price_data and not price_data[name].empty:
                returns_dict[name] = price_data[name]["Close"].pct_change().dropna()
                weights[name] = h["비중"]

        if not returns_dict:
            return {"오류": "수익률 데이터 부족"}

        returns_df = pd.DataFrame(returns_dict).dropna()
        weight_series = pd.Series(weights)

        # 공통 종목만 사용
        common = returns_df.columns.intersection(weight_series.index)
        if len(common) == 0:
            return {"오류": "공통 데이터 없음"}

        returns_df = returns_df[common]
        w = weight_series[common]
        w = w / w.sum()  # 정규화

        # 포트폴리오 일일 수익률
        portfolio_returns = (returns_df * w).sum(axis=1)

        # 연율화 수익률
        annual_return = float(portfolio_returns.mean() * 252)
        annual_vol = float(portfolio_returns.std() * np.sqrt(252))

        # 샤프 비율 (무위험이자율 3.5% 가정)
        risk_free = 0.035
        sharpe = (annual_return - risk_free) / annual_vol if annual_vol > 0 else 0

        # 최대 낙폭 (MDD)
        cumulative = (1 + portfolio_returns).cumprod()
        rolling_max = cumulative.expanding().max()
        drawdown = (cumulative - rolling_max) / rolling_max
        mdd = float(drawdown.min())

        # 승률
        win_rate = float((portfolio_returns > 0).mean())

        return {
            "연율화수익률": f"{annual_return:.2%}",
            "연율화변동성": f"{annual_vol:.2%}",
            "샤프비율": round(sharpe, 2),
            "최대낙폭(MDD)": f"{mdd:.2%}",
            "일일승률": f"{win_rate:.1%}",
            "분석기간일수": len(portfolio_returns),
        }
