"""
시장 데이터 수집 에이전트
- Yahoo Finance를 통한 한국/미국 ETF 가격 데이터 수집
- 경제지표 데이터 수집
- 포트폴리오 현재 평가액 계산
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging
import time

from config.portfolio import (
    KOREAN_ETF_TICKERS,
    ECONOMIC_INDICATORS,
    ALL_ACCOUNTS,
    ETF_SECTORS,
    ASSET_CLASSES,
)

logger = logging.getLogger(__name__)


class MarketDataAgent:
    """시장 데이터 수집 및 포트폴리오 평가 에이전트"""

    def __init__(self, lookback_days: int = 365):
        self.lookback_days = lookback_days
        self.price_cache: Dict[str, pd.DataFrame] = {}
        self.current_prices: Dict[str, float] = {}

    def fetch_etf_prices(self, etf_names: Optional[List[str]] = None) -> Dict[str, pd.DataFrame]:
        """ETF 가격 데이터 수집"""
        if etf_names is None:
            etf_names = list(KOREAN_ETF_TICKERS.keys())

        end_date = datetime.now()
        start_date = end_date - timedelta(days=self.lookback_days)
        results = {}

        for name in etf_names:
            ticker = KOREAN_ETF_TICKERS.get(name)
            if not ticker:
                logger.warning(f"티커를 찾을 수 없음: {name}")
                continue

            try:
                data = yf.download(
                    ticker, start=start_date, end=end_date,
                    progress=False, auto_adjust=True
                )
                if not data.empty:
                    # MultiIndex 컬럼 처리
                    if isinstance(data.columns, pd.MultiIndex):
                        data.columns = data.columns.get_level_values(0)
                    results[name] = data
                    if len(data) > 0:
                        self.current_prices[name] = float(data["Close"].iloc[-1])
                    logger.info(f"{name} ({ticker}): {len(data)}일 데이터 수집 완료")
                else:
                    logger.warning(f"{name} ({ticker}): 데이터 없음")
            except Exception as e:
                logger.error(f"{name} ({ticker}) 데이터 수집 실패: {e}")

        self.price_cache = results
        return results

    def fetch_economic_indicators(self) -> Dict[str, pd.DataFrame]:
        """경제지표 데이터 수집"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=self.lookback_days)
        results = {}

        for name, ticker in ECONOMIC_INDICATORS.items():
            try:
                data = yf.download(
                    ticker, start=start_date, end=end_date,
                    progress=False, auto_adjust=True
                )
                if not data.empty:
                    if isinstance(data.columns, pd.MultiIndex):
                        data.columns = data.columns.get_level_values(0)
                    results[name] = data
                    logger.info(f"경제지표 {name}: {len(data)}일 데이터 수집")
            except Exception as e:
                logger.error(f"경제지표 {name} 수집 실패: {e}")

        return results

    def get_current_prices(self) -> Dict[str, float]:
        """현재가 조회"""
        if not self.current_prices:
            self.fetch_etf_prices()
        return self.current_prices

    def calculate_portfolio_valuation(self) -> List[Dict]:
        """포트폴리오 현재 평가액 계산"""
        if not self.current_prices:
            self.fetch_etf_prices()

        account_valuations = []

        for account in ALL_ACCOUNTS:
            holdings_detail = []
            total_value = 0

            for etf_name, info in account["holdings"].items():
                current_price = self.current_prices.get(etf_name, 0)
                shares = info["shares"]
                current_value = current_price * shares
                recorded_value = info["avg_value"]

                holding = {
                    "종목명": etf_name,
                    "보유수량": shares,
                    "현재가": current_price,
                    "평가금액": current_value if current_value > 0 else recorded_value,
                    "기록평가액": recorded_value,
                    "섹터": ETF_SECTORS.get(etf_name, "기타"),
                    "자산유형": ASSET_CLASSES.get(ETF_SECTORS.get(etf_name, ""), "기타"),
                }
                holdings_detail.append(holding)
                total_value += holding["평가금액"]

            # 비중 계산
            for h in holdings_detail:
                h["비중"] = h["평가금액"] / total_value if total_value > 0 else 0

            account_valuations.append({
                "계좌명": account["account_name"],
                "계좌번호": account["account_number"],
                "총평가액": total_value,
                "보유종목": holdings_detail,
            })

        return account_valuations

    def get_performance_metrics(self) -> Dict[str, Dict]:
        """ETF별 수익률 지표 계산"""
        metrics = {}

        for name, df in self.price_cache.items():
            if df.empty or len(df) < 2:
                continue

            close = df["Close"]
            current = float(close.iloc[-1])

            perf = {"현재가": current}

            # 기간별 수익률
            periods = {
                "1일": 1, "1주": 5, "1개월": 21,
                "3개월": 63, "6개월": 126, "1년": 252
            }
            for label, days in periods.items():
                if len(close) > days:
                    past = float(close.iloc[-days - 1])
                    perf[f"수익률_{label}"] = (current - past) / past
                else:
                    perf[f"수익률_{label}"] = None

            # 변동성 (연율화)
            returns = close.pct_change().dropna()
            if len(returns) > 20:
                perf["변동성_20일"] = float(returns.tail(20).std() * np.sqrt(252))
                perf["변동성_60일"] = float(returns.tail(min(60, len(returns))).std() * np.sqrt(252))

            # 최고/최저
            perf["52주_최고"] = float(close.tail(252).max()) if len(close) >= 252 else float(close.max())
            perf["52주_최저"] = float(close.tail(252).min()) if len(close) >= 252 else float(close.min())
            perf["52주최고대비"] = (current - perf["52주_최고"]) / perf["52주_최고"]

            metrics[name] = perf

        return metrics

    def get_sector_allocation(self) -> List[Dict]:
        """계좌별 섹터 배분 현황"""
        valuations = self.calculate_portfolio_valuation()
        result = []

        for acct in valuations:
            sector_totals = {}
            asset_totals = {}

            for h in acct["보유종목"]:
                sector = h["섹터"]
                asset = h["자산유형"]
                sector_totals[sector] = sector_totals.get(sector, 0) + h["평가금액"]
                asset_totals[asset] = asset_totals.get(asset, 0) + h["평가금액"]

            total = acct["총평가액"]
            result.append({
                "계좌명": acct["계좌명"],
                "섹터배분": {k: v / total for k, v in sector_totals.items()},
                "자산유형배분": {k: v / total for k, v in asset_totals.items()},
            })

        return result

    def get_correlation_matrix(self) -> Optional[pd.DataFrame]:
        """ETF 간 상관관계 매트릭스"""
        if not self.price_cache:
            return None

        returns_dict = {}
        for name, df in self.price_cache.items():
            if not df.empty and len(df) > 20:
                returns_dict[name] = df["Close"].pct_change().dropna()

        if len(returns_dict) < 2:
            return None

        returns_df = pd.DataFrame(returns_dict).dropna()
        return returns_df.corr()
