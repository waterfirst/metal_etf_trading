"""
투자 분석 에이전트 - 메인 오케스트레이터
모든 에이전트를 조합하여 주간 분석 리포트를 생성합니다.

사용법:
    python investment_agent.py              # 주간 리포트 생성
    python investment_agent.py --quick      # 빠른 분석 (뉴스 제외)
    python investment_agent.py --schedule   # 매주 일요일 자동 실행
"""

import sys
import os
import argparse
import logging
import time
from datetime import datetime

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.market_data_agent import MarketDataAgent
from agents.technical_analysis_agent import TechnicalAnalysisAgent
from agents.economic_indicator_agent import EconomicIndicatorAgent
from agents.news_agent import NewsAgent
from agents.rebalancing_agent import RebalancingAgent
from agents.report_agent import ReportAgent

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(os.path.dirname(__file__), "reports", "agent.log"),
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("InvestmentAgent")


class InvestmentAnalysisAgent:
    """투자 분석 메인 오케스트레이터"""

    def __init__(self, lookback_days: int = 365):
        self.market_agent = MarketDataAgent(lookback_days=lookback_days)
        self.technical_agent = TechnicalAnalysisAgent()
        self.economic_agent = EconomicIndicatorAgent()
        self.news_agent = NewsAgent()
        self.rebalancing_agent = RebalancingAgent()
        self.report_agent = ReportAgent()

    def run_full_analysis(self, skip_news: bool = False) -> str:
        """전체 분석 파이프라인 실행"""
        logger.info("=" * 60)
        logger.info("투자 분석 에이전트 시작")
        logger.info(f"분석 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)

        # ── 1단계: 시장 데이터 수집 ──
        logger.info("[1/6] 시장 데이터 수집 중...")
        price_data = self.market_agent.fetch_etf_prices()
        logger.info(f"  → {len(price_data)}개 ETF 가격 데이터 수집 완료")

        economic_data = self.market_agent.fetch_economic_indicators()
        logger.info(f"  → {len(economic_data)}개 경제지표 수집 완료")

        # ── 2단계: 포트폴리오 평가 ──
        logger.info("[2/6] 포트폴리오 평가 중...")
        portfolio_valuation = self.market_agent.calculate_portfolio_valuation()
        performance_metrics = self.market_agent.get_performance_metrics()
        total_assets = sum(a["총평가액"] for a in portfolio_valuation)
        logger.info(f"  → 전체 연금자산: {total_assets:,.0f}원")

        # ── 3단계: 기술적 분석 ──
        logger.info("[3/6] 기술적 분석 수행 중...")
        technical_analysis = self.technical_agent.analyze_all(price_data)
        buy_count = sum(1 for t in technical_analysis.values() if "매수" in t.get("종합판단", ""))
        sell_count = sum(1 for t in technical_analysis.values() if "매도" in t.get("종합판단", ""))
        logger.info(f"  → {len(technical_analysis)}개 종목 분석 (매수:{buy_count}, 매도:{sell_count})")

        # ── 4단계: 경제지표 분석 ──
        logger.info("[4/6] 경제지표 분석 중...")
        economic_analysis = self.economic_agent.analyze(economic_data)
        regime = economic_analysis.get("시장환경", {}).get("판단", "N/A")
        logger.info(f"  → 시장 환경: {regime}")

        # ── 5단계: 뉴스 분석 ──
        if not skip_news:
            logger.info("[5/6] 뉴스 수집 및 분석 중...")
            try:
                all_news = self.news_agent.collect_all_news()
                news_summary = self.news_agent.analyze_sentiment_summary(all_news)
                total_news = sum(len(v) for v in all_news.values())
                logger.info(f"  → {total_news}건 뉴스 수집, 감성: {news_summary.get('종합감성', 'N/A')}")
            except Exception as e:
                logger.warning(f"  → 뉴스 수집 실패 (계속 진행): {e}")
                news_summary = {"종합감성": "중립", "긍정기사수": 0, "부정기사수": 0, "중립기사수": 0}
        else:
            logger.info("[5/6] 뉴스 분석 건너뜀 (--quick 모드)")
            news_summary = {"종합감성": "중립", "긍정기사수": 0, "부정기사수": 0, "중립기사수": 0}

        # ── 6단계: 리밸런싱 추천 ──
        logger.info("[6/6] 리밸런싱 추천 생성 중...")
        rebalancing_recs = self.rebalancing_agent.generate_recommendations(
            portfolio_valuation, technical_analysis, economic_analysis, news_summary
        )

        # 포트폴리오 전체 성과 지표
        portfolio_metrics = {}
        for acct in portfolio_valuation:
            metrics = self.rebalancing_agent.calculate_portfolio_metrics(
                price_data, acct["보유종목"]
            )
            portfolio_metrics[acct["계좌명"]] = metrics

        # ── 리포트 생성 ──
        logger.info("리포트 생성 중...")
        report = self.report_agent.generate_weekly_report(
            portfolio_valuation=portfolio_valuation,
            technical_analysis=technical_analysis,
            economic_analysis=economic_analysis,
            news_summary=news_summary,
            rebalancing_recommendations=rebalancing_recs,
            portfolio_metrics=portfolio_metrics,
            performance_metrics=performance_metrics,
        )

        logger.info("=" * 60)
        logger.info("분석 완료!")
        logger.info(f"리포트 위치: reports/weekly_report_{datetime.now().strftime('%Y-%m-%d')}.md")
        logger.info("=" * 60)

        return report


def run_scheduled(agent: InvestmentAnalysisAgent):
    """매주 일요일 자동 실행 (간단한 스케줄러)"""
    import sched
    import time as time_mod
    from datetime import timedelta

    scheduler = sched.scheduler(time_mod.time, time_mod.sleep)

    def next_sunday():
        now = datetime.now()
        days_until_sunday = (6 - now.weekday()) % 7
        if days_until_sunday == 0 and now.hour >= 9:
            days_until_sunday = 7
        target = now.replace(hour=9, minute=0, second=0, microsecond=0)
        target += timedelta(days=days_until_sunday)
        return target

    def scheduled_run():
        logger.info("스케줄 실행: 주간 분석 시작")
        try:
            report = agent.run_full_analysis()
            print("\n" + "=" * 80)
            print(report[:500] + "...")
            print("=" * 80)
        except Exception as e:
            logger.error(f"분석 실행 실패: {e}")

        # 다음 실행 예약
        next_time = next_sunday()
        delay = (next_time - datetime.now()).total_seconds()
        logger.info(f"다음 실행 예정: {next_time.strftime('%Y-%m-%d %H:%M')}")
        scheduler.enter(delay, 1, scheduled_run)

    # 첫 실행 예약
    next_time = next_sunday()
    delay = (next_time - datetime.now()).total_seconds()

    if delay < 60:  # 1분 이내면 바로 실행
        logger.info("일요일 09:00에 가까워 즉시 실행합니다.")
        scheduled_run()
    else:
        logger.info(f"다음 실행 예정: {next_time.strftime('%Y-%m-%d %H:%M')} ({delay/3600:.1f}시간 후)")
        scheduler.enter(delay, 1, scheduled_run)

    scheduler.run()


def main():
    parser = argparse.ArgumentParser(
        description="연금 포트폴리오 투자 분석 에이전트",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="빠른 분석 (뉴스 크롤링 제외)"
    )
    parser.add_argument(
        "--schedule", action="store_true",
        help="매주 일요일 09:00 자동 실행"
    )
    parser.add_argument(
        "--lookback", type=int, default=365,
        help="분석 기간 (일, 기본: 365)"
    )

    args = parser.parse_args()

    agent = InvestmentAnalysisAgent(lookback_days=args.lookback)

    if args.schedule:
        print("📅 스케줄 모드 시작 - 매주 일요일 09:00에 분석을 실행합니다.")
        print("   종료하려면 Ctrl+C를 누르세요.\n")
        try:
            run_scheduled(agent)
        except KeyboardInterrupt:
            print("\n스케줄러 종료")
    else:
        print("🔍 투자 분석 에이전트를 시작합니다...\n")
        report = agent.run_full_analysis(skip_news=args.quick)
        print("\n" + report)


if __name__ == "__main__":
    main()
