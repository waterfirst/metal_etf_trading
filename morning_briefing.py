"""
미국 증시 분석 → 한국 증시/ETF 예측 에이전트
- 미국 장 마감 후 데이터 분석
- 한국 시간 아침 7시에 당일 증시 및 ETF 예측 리포트 생성
- 미국 주요 지표 → 한국 시장 영향도 분석

사용법:
    python morning_briefing.py              # 즉시 모닝 브리핑 생성
    python morning_briefing.py --schedule   # 매일 오전 7시 자동 실행
"""

import sys
import os
import argparse
import logging
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import yfinance as yf
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.portfolio import (
    KOREAN_ETF_TICKERS, ALL_ACCOUNTS, ETF_SECTORS, ASSET_CLASSES,
)

REPORT_DIR = os.path.join(os.path.dirname(__file__), "reports")
CHART_DIR = os.path.join(REPORT_DIR, "charts")
os.makedirs(CHART_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(REPORT_DIR, "morning.log"), encoding="utf-8"),
    ],
)
logger = logging.getLogger("MorningBriefing")


# ══════════════════════════════════════════════════════════════
# 미국 시장 데이터 설정
# ══════════════════════════════════════════════════════════════

US_MARKET_TICKERS = {
    # 주요 지수
    "S&P 500": "^GSPC",
    "NASDAQ": "^IXIC",
    "다우존스": "^DJI",
    "러셀2000": "^RUT",
    # 섹터 ETF
    "기술(XLK)": "XLK",
    "반도체(SOXX)": "SOXX",
    "에너지(XLE)": "XLE",
    "금융(XLF)": "XLF",
    "헬스케어(XLV)": "XLV",
    "유틸리티(XLU)": "XLU",
    # 변동성/공포
    "VIX": "^VIX",
    # 국채
    "미국10년국채": "^TNX",
    "미국2년국채": "^IRX",
    # 통화
    "달러인덱스": "DX-Y.NYB",
    "USD/KRW": "KRW=X",
    "USD/JPY": "JPY=X",
    # 원자재
    "금": "GC=F",
    "은": "SI=F",
    "WTI원유": "CL=F",
    "구리": "HG=F",
    # 미국 주요 종목 (한국 시장 영향)
    "엔비디아": "NVDA",
    "애플": "AAPL",
    "테슬라": "TSLA",
    "마이크로소프트": "MSFT",
    # 선물 (프리마켓)
    "S&P500선물": "ES=F",
    "나스닥선물": "NQ=F",
    "코스피선물(SGX)": "KS=F",  # SGX 코스피 선물
}

# 미국 → 한국 영향 매핑
US_TO_KR_IMPACT = {
    "S&P 500":       {"영향ETF": ["KODEX 미국S&P500", "KODEX 200미국채혼합"], "방향": "동행", "강도": 0.8},
    "NASDAQ":        {"영향ETF": ["KODEX 미국나스닥100", "ACE 구글밸류체인액티브"], "방향": "동행", "강도": 0.9},
    "반도체(SOXX)":  {"영향ETF": ["TIGER 반도체TOP10"], "방향": "동행", "강도": 0.85},
    "VIX":           {"영향ETF": ["ACE KRX금현물"], "방향": "역행", "강도": 0.6},
    "미국10년국채":  {"영향ETF": ["KODEX 200미국채혼합"], "방향": "역행", "강도": 0.7},
    "달러인덱스":    {"영향ETF": ["ACE KRX금현물", "KODEX 미국S&P500"], "방향": "역행", "강도": 0.5},
    "금":            {"영향ETF": ["ACE KRX금현물"], "방향": "동행", "강도": 0.9},
    "엔비디아":      {"영향ETF": ["TIGER 반도체TOP10", "KODEX 미국AI전력핵심인프라"], "방향": "동행", "강도": 0.7},
    "USD/KRW":       {"영향ETF": ["KODEX 200", "KODEX 증권"], "방향": "역행", "강도": 0.6},
}

# 한국 시장 영향 요인별 가중치
KOSPI_INFLUENCE_WEIGHTS = {
    "S&P 500": 0.25,
    "NASDAQ": 0.20,
    "USD/KRW": -0.15,    # 원화약세 → 코스피 부정적
    "VIX": -0.10,        # VIX 상승 → 코스피 부정적
    "달러인덱스": -0.10,
    "금": 0.05,
    "WTI원유": 0.05,
    "미국10년국채": -0.10,
}


@dataclass
class USMarketSummary:
    """미국 시장 종합 요약"""
    date: str
    sp500_change: float
    nasdaq_change: float
    dow_change: float
    vix_level: float
    vix_change: float
    treasury_10y: float
    dollar_index: float
    usd_krw: float
    gold_change: float
    oil_change: float
    nvidia_change: float
    sector_leaders: List[Tuple[str, float]]    # 상승 상위 섹터
    sector_laggards: List[Tuple[str, float]]   # 하락 상위 섹터
    futures_sp500: Optional[float]
    futures_nasdaq: Optional[float]


class MorningBriefingAgent:
    """모닝 브리핑 에이전트"""

    def __init__(self):
        self.us_data: Dict[str, pd.DataFrame] = {}
        self.us_changes: Dict[str, float] = {}
        self.us_current: Dict[str, float] = {}

    # ──────────────────────────────────────────
    # 1단계: 미국 시장 데이터 수집
    # ──────────────────────────────────────────
    def fetch_us_market_data(self) -> Dict[str, pd.DataFrame]:
        """미국 시장 데이터 수집 (최근 30일)"""
        logger.info("미국 시장 데이터 수집 중...")
        end = datetime.now()
        start = end - timedelta(days=60)

        for name, ticker in US_MARKET_TICKERS.items():
            try:
                df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
                if not df.empty:
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    self.us_data[name] = df

                    close = df["Close"]
                    self.us_current[name] = float(close.iloc[-1])
                    if len(close) >= 2:
                        self.us_changes[name] = (float(close.iloc[-1]) - float(close.iloc[-2])) / float(close.iloc[-2])
            except Exception as e:
                logger.warning(f"{name} ({ticker}) 수집 실패: {e}")

        logger.info(f"  → {len(self.us_data)}개 항목 수집 완료")
        return self.us_data

    # ──────────────────────────────────────────
    # 2단계: 미국 시장 분석
    # ──────────────────────────────────────────
    def analyze_us_market(self) -> USMarketSummary:
        """미국 시장 종합 분석"""
        logger.info("미국 시장 분석 중...")

        # 섹터별 등락률
        sectors = {}
        for name in ["기술(XLK)", "반도체(SOXX)", "에너지(XLE)", "금융(XLF)", "헬스케어(XLV)", "유틸리티(XLU)"]:
            if name in self.us_changes:
                sectors[name] = self.us_changes[name]

        sorted_sectors = sorted(sectors.items(), key=lambda x: x[1], reverse=True)

        summary = USMarketSummary(
            date=datetime.now().strftime("%Y-%m-%d"),
            sp500_change=self.us_changes.get("S&P 500", 0),
            nasdaq_change=self.us_changes.get("NASDAQ", 0),
            dow_change=self.us_changes.get("다우존스", 0),
            vix_level=self.us_current.get("VIX", 0),
            vix_change=self.us_changes.get("VIX", 0),
            treasury_10y=self.us_current.get("미국10년국채", 0),
            dollar_index=self.us_current.get("달러인덱스", 0),
            usd_krw=self.us_current.get("USD/KRW", 0),
            gold_change=self.us_changes.get("금", 0),
            oil_change=self.us_changes.get("WTI원유", 0),
            nvidia_change=self.us_changes.get("엔비디아", 0),
            sector_leaders=sorted_sectors[:3],
            sector_laggards=sorted_sectors[-3:],
            futures_sp500=self.us_changes.get("S&P500선물"),
            futures_nasdaq=self.us_changes.get("나스닥선물"),
        )

        return summary

    # ──────────────────────────────────────────
    # 3단계: 한국 시장 예측
    # ──────────────────────────────────────────
    def predict_korean_market(self, us_summary: USMarketSummary) -> Dict:
        """한국 증시 예측"""
        logger.info("한국 시장 예측 중...")

        # KOSPI 예측 점수 (-1 ~ +1)
        kospi_score = 0
        score_breakdown = []

        for indicator, weight in KOSPI_INFLUENCE_WEIGHTS.items():
            change = self.us_changes.get(indicator, 0)
            contribution = change * weight * 100  # 백분율 기여도
            kospi_score += contribution
            if abs(contribution) > 0.01:
                direction = "↑" if contribution > 0 else "↓"
                score_breakdown.append({
                    "요인": indicator,
                    "전일등락": f"{change:+.2%}",
                    "가중치": weight,
                    "기여도": f"{contribution:+.3f}",
                    "영향": direction,
                })

        # KOSPI 예상 등락률 (경험적 베타 적용)
        # 한국시장은 미국 대비 약 0.8~1.2배 민감
        sensitivity = 1.0
        if us_summary.vix_level > 25:
            sensitivity = 1.3  # 공포 시 민감도 증가
        elif us_summary.vix_level < 15:
            sensitivity = 0.8

        kospi_predicted_change = kospi_score * sensitivity

        # 예측 신뢰도
        # 미국 변동폭이 클수록 예측 신뢰도 높음
        us_abs_change = abs(us_summary.sp500_change)
        if us_abs_change > 0.02:
            confidence = "높음"
        elif us_abs_change > 0.005:
            confidence = "보통"
        else:
            confidence = "낮음 (미국시장 변동 미미)"

        # 시장 분위기 판단
        if kospi_predicted_change > 0.5:
            mood = "강한 상승 예상 📈📈"
        elif kospi_predicted_change > 0.1:
            mood = "상승 예상 📈"
        elif kospi_predicted_change > -0.1:
            mood = "보합 예상 ➡️"
        elif kospi_predicted_change > -0.5:
            mood = "하락 예상 📉"
        else:
            mood = "강한 하락 예상 📉📉"

        return {
            "KOSPI_예측등락률": f"{kospi_predicted_change:+.2f}%",
            "예측점수": round(kospi_predicted_change, 3),
            "시장분위기": mood,
            "신뢰도": confidence,
            "VIX민감도보정": sensitivity,
            "요인분석": sorted(score_breakdown, key=lambda x: abs(float(x["기여도"])), reverse=True),
        }

    # ──────────────────────────────────────────
    # 4단계: 개별 ETF 예측
    # ──────────────────────────────────────────
    def predict_etf_movements(self, us_summary: USMarketSummary, kospi_prediction: Dict) -> List[Dict]:
        """개별 ETF 예측"""
        logger.info("ETF별 예측 생성 중...")
        predictions = []

        all_etfs = set()
        for acct in ALL_ACCOUNTS:
            for name in acct["holdings"]:
                all_etfs.add(name)

        kospi_base = float(kospi_prediction["예측점수"])

        for etf_name in sorted(all_etfs):
            sector = ETF_SECTORS.get(etf_name, "기타")
            asset_class = ASSET_CLASSES.get(sector, "기타")

            # 기본 예측: KOSPI 예측 기반
            predicted_change = kospi_base

            # 개별 영향 요인 반영
            influences = []
            for us_indicator, impact_info in US_TO_KR_IMPACT.items():
                if etf_name in impact_info["영향ETF"]:
                    us_change = self.us_changes.get(us_indicator, 0)
                    strength = impact_info["강도"]

                    if impact_info["방향"] == "동행":
                        adjustment = us_change * strength * 100
                    else:  # 역행
                        adjustment = -us_change * strength * 100

                    predicted_change += adjustment
                    if abs(adjustment) > 0.01:
                        influences.append(f"{us_indicator} {us_change:+.2%} → {adjustment:+.2f}%p")

            # 자산유형별 추가 조정
            if asset_class == "해외주식":
                # 환율 영향 (원화 약세 → 원화 환산 시 이득)
                krw_change = self.us_changes.get("USD/KRW", 0)
                fx_effect = krw_change * 100
                predicted_change += fx_effect * 0.3
                if abs(fx_effect) > 0.1:
                    influences.append(f"환율효과 {fx_effect:+.2f}%p")

            elif asset_class == "원자재":
                gold_change = self.us_changes.get("금", 0) * 100
                predicted_change = gold_change * 0.9  # 금ETF는 금 가격에 직접 연동
                influences = [f"금선물 {gold_change:+.2f}% 직접 연동"]

            elif asset_class in ("채권혼합", "TDF"):
                # 채권 혼합은 변동이 작음
                predicted_change *= 0.4
                influences.append("채권혼합 변동 완화")

            # 시그널 판단
            if predicted_change > 1.0:
                signal = "강한 상승 🟢🟢"
                action = "매수 유리"
            elif predicted_change > 0.3:
                signal = "상승 🟢"
                action = "매수 고려"
            elif predicted_change > -0.3:
                signal = "보합 ⚪"
                action = "관망"
            elif predicted_change > -1.0:
                signal = "하락 🔴"
                action = "매도 고려"
            else:
                signal = "강한 하락 🔴🔴"
                action = "매도 유리"

            predictions.append({
                "종목명": etf_name,
                "섹터": sector,
                "자산유형": asset_class,
                "예측등락률": f"{predicted_change:+.2f}%",
                "예측값": round(predicted_change, 3),
                "시그널": signal,
                "액션": action,
                "주요영향": influences,
            })

        # 예측 등락률 기준 정렬
        predictions.sort(key=lambda x: x["예측값"], reverse=True)
        return predictions

    # ──────────────────────────────────────────
    # 5단계: 오늘의 투자 전략
    # ──────────────────────────────────────────
    def generate_daily_strategy(
        self, us_summary: USMarketSummary,
        kospi_prediction: Dict,
        etf_predictions: List[Dict],
    ) -> Dict:
        """오늘의 투자 전략 생성"""

        # 매수 추천
        buy_candidates = [e for e in etf_predictions if e["예측값"] > 0.3]
        sell_candidates = [e for e in etf_predictions if e["예측값"] < -0.3]

        # 주의 사항
        warnings = []
        if us_summary.vix_level > 25:
            warnings.append("⚠️ VIX가 25 이상으로 시장 변동성이 큽니다. 포지션 크기를 줄이세요.")
        if abs(us_summary.sp500_change) > 0.02:
            warnings.append(f"⚠️ 미국 S&P500이 {us_summary.sp500_change:+.2%} 급변했습니다. 갭 발생 주의.")
        if us_summary.usd_krw > 1400:
            warnings.append(f"⚠️ 환율 {us_summary.usd_krw:.0f}원으로 높은 수준. 해외ETF 환위험 주의.")
        if us_summary.vix_change > 0.1:
            warnings.append(f"⚠️ VIX가 전일 대비 {us_summary.vix_change:+.1%} 급등. 공포 확산 주의.")

        # 오늘의 핵심 전략
        kospi_score = float(kospi_prediction["예측점수"])
        if kospi_score > 0.5:
            core_strategy = "공격적 매수 전략 - 상승 모멘텀 활용"
        elif kospi_score > 0.1:
            core_strategy = "선별적 매수 전략 - 상승 종목 위주 매수"
        elif kospi_score > -0.1:
            core_strategy = "관망 전략 - 변동 미미, 기존 포지션 유지"
        elif kospi_score > -0.5:
            core_strategy = "방어적 전략 - 안전자산 비중 확대 고려"
        else:
            core_strategy = "리스크 관리 전략 - 손실 제한, 현금 비중 확대"

        return {
            "핵심전략": core_strategy,
            "매수후보": [
                {"종목": e["종목명"], "예측": e["예측등락률"], "이유": ", ".join(e["주요영향"][:2])}
                for e in buy_candidates[:5]
            ],
            "매도후보": [
                {"종목": e["종목명"], "예측": e["예측등락률"], "이유": ", ".join(e["주요영향"][:2])}
                for e in sell_candidates[:5]
            ],
            "주의사항": warnings,
        }

    # ──────────────────────────────────────────
    # 6단계: 모닝 브리핑 리포트 생성
    # ──────────────────────────────────────────
    def generate_morning_report(
        self,
        us_summary: USMarketSummary,
        kospi_prediction: Dict,
        etf_predictions: List[Dict],
        daily_strategy: Dict,
    ) -> str:
        """모닝 브리핑 마크다운 리포트"""
        now = datetime.now()
        lines = []

        # ── 헤더 ──
        lines.append(f"# ☀️ 모닝 브리핑 - {now.strftime('%Y년 %m월 %d일 %A')}")
        lines.append(f"**생성 시각:** {now.strftime('%H:%M')} KST")
        lines.append(f"**분석 기준:** 전일 미국 시장 마감 데이터\n")
        lines.append("---\n")

        # ── 1. 미국 시장 마감 요약 ──
        lines.append("## 1. 🇺🇸 미국 시장 마감 요약\n")

        sp_emoji = "📈" if us_summary.sp500_change > 0 else "📉"
        nq_emoji = "📈" if us_summary.nasdaq_change > 0 else "📉"
        dj_emoji = "📈" if us_summary.dow_change > 0 else "📉"

        lines.append("| 지수 | 등락률 | 현재값 |")
        lines.append("|------|--------|--------|")
        lines.append(f"| {sp_emoji} S&P 500 | **{us_summary.sp500_change:+.2%}** | {self.us_current.get('S&P 500', 0):,.0f} |")
        lines.append(f"| {nq_emoji} NASDAQ | **{us_summary.nasdaq_change:+.2%}** | {self.us_current.get('NASDAQ', 0):,.0f} |")
        lines.append(f"| {dj_emoji} 다우존스 | **{us_summary.dow_change:+.2%}** | {self.us_current.get('다우존스', 0):,.0f} |")
        lines.append("")

        # 핵심 지표
        lines.append("### 핵심 지표\n")
        vix_emoji = "🔴" if us_summary.vix_level > 20 else ("🟡" if us_summary.vix_level > 15 else "🟢")
        lines.append(f"| 지표 | 값 | 변동 | 상태 |")
        lines.append(f"|------|----|------|------|")
        lines.append(f"| VIX (공포지수) | {us_summary.vix_level:.1f} | {us_summary.vix_change:+.1%} | {vix_emoji} |")
        lines.append(f"| 미국 10년 국채 | {us_summary.treasury_10y:.2f}% | {self.us_changes.get('미국10년국채', 0):+.2%} | |")
        lines.append(f"| 달러인덱스 | {us_summary.dollar_index:.1f} | {self.us_changes.get('달러인덱스', 0):+.2%} | |")
        lines.append(f"| USD/KRW | {us_summary.usd_krw:,.0f}원 | {self.us_changes.get('USD/KRW', 0):+.2%} | |")
        lines.append(f"| 금 선물 | ${self.us_current.get('금', 0):,.0f} | {us_summary.gold_change:+.2%} | |")
        lines.append(f"| WTI 원유 | ${self.us_current.get('WTI원유', 0):,.1f} | {us_summary.oil_change:+.2%} | |")
        lines.append("")

        # 섹터 동향
        lines.append("### 미국 섹터 동향\n")
        lines.append("**상승 섹터:** " + ", ".join(
            [f"{name} ({change:+.2%})" for name, change in us_summary.sector_leaders if change > 0]
        ))
        lines.append("**하락 섹터:** " + ", ".join(
            [f"{name} ({change:+.2%})" for name, change in us_summary.sector_laggards if change < 0]
        ))
        lines.append("")

        # 주요 종목
        key_stocks = ["엔비디아", "애플", "테슬라", "마이크로소프트"]
        lines.append("### 주요 종목\n")
        lines.append("| 종목 | 등락률 |")
        lines.append("|------|--------|")
        for stock in key_stocks:
            if stock in self.us_changes:
                emoji = "📈" if self.us_changes[stock] > 0 else "📉"
                lines.append(f"| {emoji} {stock} | **{self.us_changes[stock]:+.2%}** |")
        lines.append("")

        # ── 2. 한국 시장 예측 ──
        lines.append("---\n")
        lines.append("## 2. 🇰🇷 한국 시장 예측\n")
        lines.append(f"### {kospi_prediction['시장분위기']}\n")
        lines.append(f"- **KOSPI 예측 등락률:** {kospi_prediction['KOSPI_예측등락률']}")
        lines.append(f"- **예측 신뢰도:** {kospi_prediction['신뢰도']}")
        lines.append(f"- **VIX 민감도 보정:** ×{kospi_prediction['VIX민감도보정']}\n")

        # 요인 분석
        factors = kospi_prediction.get("요인분석", [])
        if factors:
            lines.append("### KOSPI 영향 요인 분석\n")
            lines.append("| 요인 | 전일 등락 | 가중치 | KOSPI 기여도 | 방향 |")
            lines.append("|------|----------|--------|-------------|------|")
            for f in factors:
                lines.append(f"| {f['요인']} | {f['전일등락']} | {f['가중치']} | {f['기여도']} | {f['영향']} |")
            lines.append("")

        # ── 3. ETF 예측 ──
        lines.append("---\n")
        lines.append("## 3. 📊 ETF별 예측\n")
        lines.append("| 순위 | 종목 | 예측 등락률 | 시그널 | 액션 | 주요 영향 |")
        lines.append("|------|------|-----------|--------|------|----------|")
        for i, etf in enumerate(etf_predictions, 1):
            influences_str = ", ".join(etf["주요영향"][:2]) if etf["주요영향"] else "-"
            lines.append(
                f"| {i} | {etf['종목명']} | **{etf['예측등락률']}** | "
                f"{etf['시그널']} | {etf['액션']} | {influences_str} |"
            )
        lines.append("")

        # 계좌별 예상 영향
        lines.append("### 계좌별 예상 영향\n")
        for acct in ALL_ACCOUNTS:
            total_val = sum(h["avg_value"] for h in acct["holdings"].values())
            weighted_change = 0
            for etf_name, info in acct["holdings"].items():
                weight = info["avg_value"] / total_val
                etf_pred = next((e for e in etf_predictions if e["종목명"] == etf_name), None)
                if etf_pred:
                    weighted_change += weight * etf_pred["예측값"]

            emoji = "📈" if weighted_change > 0 else "📉"
            est_amount = total_val * weighted_change / 100
            lines.append(
                f"- **{acct['account_name']}**: {emoji} 예상 {weighted_change:+.2f}% "
                f"(약 {est_amount:+,.0f}원)"
            )
        lines.append("")

        # ── 4. 오늘의 투자 전략 ──
        lines.append("---\n")
        lines.append("## 4. 🎯 오늘의 투자 전략\n")
        lines.append(f"### 핵심 전략: **{daily_strategy['핵심전략']}**\n")

        # 주의사항
        warnings = daily_strategy.get("주의사항", [])
        if warnings:
            for w in warnings:
                lines.append(f"{w}")
            lines.append("")

        # 매수 추천
        buy = daily_strategy.get("매수후보", [])
        if buy:
            lines.append("### 🟢 매수 고려 종목\n")
            for b in buy:
                lines.append(f"- **{b['종목']}** ({b['예측']}) - {b['이유']}")
            lines.append("")

        # 매도 추천
        sell = daily_strategy.get("매도후보", [])
        if sell:
            lines.append("### 🔴 매도 고려 종목\n")
            for s in sell:
                lines.append(f"- **{s['종목']}** ({s['예측']}) - {s['이유']}")
            lines.append("")

        # ── 5. 시간대별 행동 가이드 ──
        lines.append("---\n")
        lines.append("## 5. ⏰ 시간대별 행동 가이드\n")
        lines.append("| 시간 | 행동 |")
        lines.append("|------|------|")
        lines.append("| 08:30~09:00 | 장 시작 전 주문 설정 (예약 매수/매도) |")

        if float(kospi_prediction["예측점수"]) > 0.3:
            lines.append("| 09:00~09:30 | 갭 상승 시 관망, 눌림목에서 매수 |")
            lines.append("| 09:30~10:30 | 상승 확인 후 추가 매수 |")
        elif float(kospi_prediction["예측점수"]) < -0.3:
            lines.append("| 09:00~09:30 | 갭 하락 시 공포 매도 자제, 관망 |")
            lines.append("| 09:30~10:30 | 저점 매수 기회 탐색 (분할 매수) |")
        else:
            lines.append("| 09:00~09:30 | 시장 방향 확인, 성급한 매매 자제 |")
            lines.append("| 09:30~10:30 | 추세 확인 후 소규모 매매 |")

        lines.append("| 14:00~15:00 | 마감 전 포지션 정리/유지 결정 |")
        lines.append("| 15:30 | 장 마감 후 리뷰 |")

        lines.append("\n---")
        lines.append(f"*본 리포트는 전일 미국 시장 데이터 기반 자동 생성 예측이며, 투자 결정의 최종 책임은 투자자에게 있습니다.*")
        lines.append(f"*생성 시각: {now.strftime('%Y-%m-%d %H:%M:%S')} KST*")

        report = "\n".join(lines)

        # 파일 저장
        filename = f"morning_briefing_{now.strftime('%Y-%m-%d')}.md"
        filepath = os.path.join(REPORT_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)
        logger.info(f"모닝 브리핑 저장: {filepath}")

        # JSON 데이터 저장
        json_data = {
            "date": now.strftime("%Y-%m-%d"),
            "generated_at": now.strftime("%H:%M:%S"),
            "us_market": {k: v for k, v in self.us_changes.items()},
            "us_current": {k: v for k, v in self.us_current.items()},
            "kospi_prediction": kospi_prediction,
            "etf_predictions": etf_predictions,
            "strategy": daily_strategy,
        }
        json_path = os.path.join(REPORT_DIR, f"morning_data_{now.strftime('%Y-%m-%d')}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2, default=str)

        return report

    # ──────────────────────────────────────────
    # 7단계: 시각화 차트 생성
    # ──────────────────────────────────────────
    def generate_charts(self, us_summary: USMarketSummary, etf_predictions: List[Dict], kospi_prediction: Dict):
        """모닝 브리핑 차트 생성"""
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        today = datetime.now().strftime("%Y-%m-%d")

        # ── 차트 1: 미국 시장 요약 ──
        categories = []
        values = []
        colors = []
        for name in ["S&P 500", "NASDAQ", "다우존스", "러셀2000", "VIX",
                      "금", "WTI원유", "엔비디아", "애플", "테슬라"]:
            if name in self.us_changes:
                categories.append(name)
                v = self.us_changes[name] * 100
                values.append(v)
                colors.append("#2ecc71" if v > 0 else "#e74c3c")

        fig = go.Figure(go.Bar(
            x=categories, y=values, marker_color=colors,
            text=[f"{v:+.2f}%" for v in values], textposition="outside",
        ))
        fig.update_layout(
            title=f"미국 시장 전일 등락률 ({today})",
            yaxis_title="등락률 (%)", width=1200, height=500,
            font=dict(size=12), xaxis_tickangle=-20,
        )
        fig.write_image(os.path.join(CHART_DIR, f"morning_01_us_market_{today}.png"), scale=2)
        logger.info("  차트 저장: morning_01_us_market.png")

        # ── 차트 2: ETF 예측 등락률 ──
        etf_names = [e["종목명"] for e in etf_predictions]
        etf_vals = [e["예측값"] for e in etf_predictions]
        etf_colors = ["#2ecc71" if v > 0.3 else ("#e74c3c" if v < -0.3 else "#95a5a6") for v in etf_vals]

        fig = go.Figure(go.Bar(
            x=etf_names, y=etf_vals, marker_color=etf_colors,
            text=[f"{v:+.2f}%" for v in etf_vals], textposition="outside",
        ))
        fig.update_layout(
            title=f"ETF 오늘 예측 등락률 ({today})",
            yaxis_title="예측 등락률 (%)", width=1400, height=550,
            font=dict(size=12), xaxis_tickangle=-25,
        )
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
        fig.write_image(os.path.join(CHART_DIR, f"morning_02_etf_prediction_{today}.png"), scale=2)
        logger.info("  차트 저장: morning_02_etf_prediction.png")

        # ── 차트 3: KOSPI 영향 요인 워터폴 ──
        factors = kospi_prediction.get("요인분석", [])
        if factors:
            factor_names = [f["요인"] for f in factors]
            factor_vals = [float(f["기여도"]) for f in factors]
            factor_names.append("KOSPI 예측")
            factor_vals.append(sum(factor_vals))

            measures = ["relative"] * (len(factor_names) - 1) + ["total"]

            fig = go.Figure(go.Waterfall(
                x=factor_names, y=factor_vals, measure=measures,
                increasing=dict(marker_color="#2ecc71"),
                decreasing=dict(marker_color="#e74c3c"),
                totals=dict(marker_color="#3498db"),
                text=[f"{v:+.3f}" for v in factor_vals],
                textposition="outside",
            ))
            fig.update_layout(
                title=f"KOSPI 예측 영향 요인 분석 ({today})",
                yaxis_title="기여도 (%p)", width=1200, height=550,
                font=dict(size=12),
            )
            fig.write_image(os.path.join(CHART_DIR, f"morning_03_kospi_factors_{today}.png"), scale=2)
            logger.info("  차트 저장: morning_03_kospi_factors.png")

        # ── 차트 4: 미국 섹터 성과 ──
        sector_names = []
        sector_vals = []
        for name in ["기술(XLK)", "반도체(SOXX)", "에너지(XLE)", "금융(XLF)", "헬스케어(XLV)", "유틸리티(XLU)"]:
            if name in self.us_changes:
                sector_names.append(name)
                sector_vals.append(self.us_changes[name] * 100)

        if sector_names:
            s_colors = ["#2ecc71" if v > 0 else "#e74c3c" for v in sector_vals]
            fig = go.Figure(go.Bar(
                x=sector_names, y=sector_vals, marker_color=s_colors,
                text=[f"{v:+.2f}%" for v in sector_vals], textposition="outside",
            ))
            fig.update_layout(
                title=f"미국 섹터별 등락률 ({today})",
                yaxis_title="등락률 (%)", width=900, height=450,
                font=dict(size=12),
            )
            fig.write_image(os.path.join(CHART_DIR, f"morning_04_us_sectors_{today}.png"), scale=2)
            logger.info("  차트 저장: morning_04_us_sectors.png")

    # ──────────────────────────────────────────
    # 전체 실행
    # ──────────────────────────────────────────
    def run(self) -> str:
        """모닝 브리핑 전체 실행"""
        logger.info("=" * 60)
        logger.info("☀️ 모닝 브리핑 시작")
        logger.info(f"실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} KST")
        logger.info("=" * 60)

        # 1. 미국 시장 데이터 수집
        self.fetch_us_market_data()

        # 2. 미국 시장 분석
        us_summary = self.analyze_us_market()

        # 3. 한국 시장 예측
        kospi_prediction = self.predict_korean_market(us_summary)

        # 4. ETF별 예측
        etf_predictions = self.predict_etf_movements(us_summary, kospi_prediction)

        # 5. 오늘의 전략
        daily_strategy = self.generate_daily_strategy(us_summary, kospi_prediction, etf_predictions)

        # 6. 리포트 생성
        report = self.generate_morning_report(us_summary, kospi_prediction, etf_predictions, daily_strategy)

        # 7. 차트 생성
        try:
            self.generate_charts(us_summary, etf_predictions, kospi_prediction)
        except Exception as e:
            logger.warning(f"차트 생성 실패 (계속 진행): {e}")

        logger.info("=" * 60)
        logger.info("모닝 브리핑 완료!")
        logger.info("=" * 60)

        return report


def run_scheduled():
    """매일 오전 7시(KST) 자동 실행"""
    import sched
    import time as time_mod

    scheduler = sched.scheduler(time_mod.time, time_mod.sleep)

    def next_7am():
        now = datetime.now()
        target = now.replace(hour=7, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        # 주말 건너뛰기 (토, 일)
        while target.weekday() >= 5:
            target += timedelta(days=1)
        return target

    def scheduled_run():
        try:
            agent = MorningBriefingAgent()
            report = agent.run()
            print("\n" + report[:1000] + "...\n")
        except Exception as e:
            logger.error(f"모닝 브리핑 실패: {e}")

        # 다음 실행 예약
        next_time = next_7am()
        delay = (next_time - datetime.now()).total_seconds()
        logger.info(f"다음 실행: {next_time.strftime('%Y-%m-%d %H:%M')} ({delay/3600:.1f}시간 후)")
        scheduler.enter(delay, 1, scheduled_run)

    # 첫 실행 예약
    next_time = next_7am()
    delay = (next_time - datetime.now()).total_seconds()

    if delay < 120:  # 2분 이내면 즉시 실행
        logger.info("오전 7시에 가까워 즉시 실행합니다.")
        scheduled_run()
    else:
        logger.info(f"다음 실행: {next_time.strftime('%Y-%m-%d %H:%M')} ({delay/3600:.1f}시간 후)")
        logger.info("대기 중... (Ctrl+C로 종료)")
        scheduler.enter(delay, 1, scheduled_run)

    try:
        scheduler.run()
    except KeyboardInterrupt:
        print("\n스케줄러 종료")


def main():
    parser = argparse.ArgumentParser(description="모닝 브리핑 - 미국 증시 분석 → 한국 시장 예측")
    parser.add_argument("--schedule", action="store_true", help="매일 오전 7시 자동 실행")
    args = parser.parse_args()

    if args.schedule:
        print("⏰ 스케줄 모드 - 매일 오전 7:00 KST에 모닝 브리핑을 생성합니다.")
        print("   (주말 제외, Ctrl+C로 종료)\n")
        run_scheduled()
    else:
        print("☀️ 모닝 브리핑을 생성합니다...\n")
        agent = MorningBriefingAgent()
        report = agent.run()
        print("\n" + report)


if __name__ == "__main__":
    main()
