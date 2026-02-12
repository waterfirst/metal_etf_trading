"""
리포트 생성 에이전트
- 주간 분석 리포트 생성 (마크다운 + HTML)
- 차트 생성
- 리포트 저장
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports")


class ReportAgent:
    """리포트 생성 에이전트"""

    def __init__(self):
        os.makedirs(REPORT_DIR, exist_ok=True)

    def generate_weekly_report(
        self,
        portfolio_valuation: List[Dict],
        technical_analysis: Dict[str, Dict],
        economic_analysis: Dict,
        news_summary: Dict,
        rebalancing_recommendations: List[Dict],
        portfolio_metrics: Dict,
        performance_metrics: Dict,
    ) -> str:
        """주간 분석 리포트 생성"""
        now = datetime.now()
        report_date = now.strftime("%Y-%m-%d")
        week_num = now.isocalendar()[1]

        sections = []

        # 헤더
        sections.append(self._header(report_date, week_num))

        # 1. 포트폴리오 현황
        sections.append(self._portfolio_summary(portfolio_valuation))

        # 2. 시장 환경 분석
        sections.append(self._market_environment(economic_analysis))

        # 3. 기술적 분석 요약
        sections.append(self._technical_summary(technical_analysis))

        # 4. 뉴스 요약
        sections.append(self._news_section(news_summary))

        # 5. 포트폴리오 성과 지표
        sections.append(self._performance_section(portfolio_metrics, performance_metrics))

        # 6. 리밸런싱 추천
        sections.append(self._rebalancing_section(rebalancing_recommendations))

        # 7. 종합 의견
        sections.append(self._overall_opinion(
            economic_analysis, technical_analysis,
            news_summary, rebalancing_recommendations
        ))

        report = "\n\n".join(sections)

        # 파일 저장
        filename = f"weekly_report_{report_date}.md"
        filepath = os.path.join(REPORT_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)
        logger.info(f"리포트 저장: {filepath}")

        # JSON 데이터도 저장
        json_filename = f"weekly_data_{report_date}.json"
        json_filepath = os.path.join(REPORT_DIR, json_filename)
        self._save_json_data(json_filepath, {
            "report_date": report_date,
            "portfolio_valuation": self._sanitize_for_json(portfolio_valuation),
            "economic_analysis": self._sanitize_for_json(economic_analysis),
            "news_summary": self._sanitize_for_json(news_summary),
            "rebalancing": self._sanitize_for_json(rebalancing_recommendations),
        })

        return report

    def _header(self, date: str, week_num: int) -> str:
        return f"""# 📊 주간 연금 포트폴리오 분석 리포트

**분석일:** {date} (제{week_num}주)
**분석 시스템:** Investment Analysis Agent v1.0

---"""

    def _portfolio_summary(self, valuations: List[Dict]) -> str:
        lines = ["## 1. 포트폴리오 현황\n"]

        for acct in valuations:
            lines.append(f"### {acct['계좌명']} ({acct['계좌번호']})")
            lines.append(f"**총 평가액: {acct['총평가액']:,.0f}원**\n")
            lines.append("| 종목명 | 보유수량 | 평가금액 | 비중 | 섹터 |")
            lines.append("|--------|---------|---------|------|------|")

            for h in sorted(acct["보유종목"], key=lambda x: x["평가금액"], reverse=True):
                lines.append(
                    f"| {h['종목명']} | {h['보유수량']:,} | "
                    f"{h['평가금액']:,.0f}원 | {h['비중']:.1%} | {h['섹터']} |"
                )
            lines.append("")

        # 전체 합산
        total = sum(a["총평가액"] for a in valuations)
        lines.append(f"**전체 연금자산 합계: {total:,.0f}원**")

        return "\n".join(lines)

    def _market_environment(self, economic: Dict) -> str:
        lines = ["## 2. 시장 환경 분석\n"]

        regime = economic.get("시장환경", {})
        lines.append(f"### 시장 환경 판단: **{regime.get('판단', 'N/A')}**")
        lines.append(f"- 종합 점수: {regime.get('평균점수', 'N/A')}/5.0")
        lines.append(f"- 긍정 지표: {regime.get('긍정지표수', 0)}개 / 부정 지표: {regime.get('부정지표수', 0)}개")
        lines.append(f"- **{regime.get('권고', '')}**\n")

        signals = economic.get("시그널", [])
        if signals:
            lines.append("### 주요 경제지표\n")
            lines.append("| 지표 | 현재값 | 추세 | 영향 | 설명 |")
            lines.append("|------|--------|------|------|------|")
            for s in signals:
                lines.append(
                    f"| {s['지표']} | {s['현재값']:.2f} | {s['추세']} | "
                    f"{s['영향']} | {s['설명'][:50]} |"
                )

        return "\n".join(lines)

    def _technical_summary(self, technical: Dict[str, Dict]) -> str:
        lines = ["## 3. 기술적 분석 요약\n"]

        if not technical:
            lines.append("데이터 부족으로 분석 불가")
            return "\n".join(lines)

        lines.append("| 종목 | 종합판단 | 점수 | 추세 | RSI | MACD |")
        lines.append("|------|---------|------|------|-----|------|")

        for name, analysis in sorted(
            technical.items(), key=lambda x: x[1].get("종합점수", 0), reverse=True
        ):
            indicators = analysis.get("기술지표", {})
            rsi = indicators.get("RSI", "N/A")
            macd = indicators.get("MACD", "N/A")

            judgment = analysis.get("종합판단", "N/A")
            emoji = {"강력매수": "🟢🟢", "매수": "🟢", "중립": "🟡",
                     "매도": "🔴", "강력매도": "🔴🔴"}.get(judgment, "⚪")

            lines.append(
                f"| {name} | {emoji} {judgment} | "
                f"{analysis.get('종합점수', 'N/A')} | {analysis.get('추세', 'N/A')} | "
                f"{rsi if isinstance(rsi, str) else f'{rsi:.1f}'} | "
                f"{macd if isinstance(macd, str) else f'{macd:.4f}'} |"
            )

        # 세부 시그널
        lines.append("\n### 종목별 상세 시그널\n")
        for name, analysis in technical.items():
            signals = analysis.get("시그널", [])
            if signals:
                lines.append(f"**{name}** ({analysis.get('종합판단', '')}, 추세: {analysis.get('추세', '')})")
                for s in signals:
                    lines.append(f"  - {s['지표']}: {s['판단']} ({s['설명']})")
                lines.append("")

        return "\n".join(lines)

    def _news_section(self, news_summary: Dict) -> str:
        lines = ["## 4. 뉴스 및 시장 심리\n"]

        overall = news_summary.get("종합감성", "중립")
        emoji = {"긍정": "😊", "부정": "😟", "중립": "😐"}.get(overall, "😐")
        lines.append(f"### 뉴스 감성: {emoji} **{overall}**")
        lines.append(f"- 긍정 기사: {news_summary.get('긍정기사수', 0)}건")
        lines.append(f"- 부정 기사: {news_summary.get('부정기사수', 0)}건")
        lines.append(f"- 중립 기사: {news_summary.get('중립기사수', 0)}건\n")

        # 카테고리별
        cat = news_summary.get("카테고리별", {})
        if cat:
            lines.append("### 카테고리별 감성\n")
            lines.append("| 카테고리 | 감성 | 긍정비율 | 기사수 |")
            lines.append("|---------|------|---------|-------|")
            for k, v in cat.items():
                lines.append(f"| {k} | {v['감성']} | {v['긍정비율']:.0%} | {v['기사수']} |")

        # 섹터별 관련 뉴스
        sector_news = news_summary.get("섹터관련뉴스", {})
        if sector_news:
            lines.append("\n### 포트폴리오 관련 주요 뉴스\n")
            for sector, titles in sector_news.items():
                lines.append(f"**[{sector}]**")
                for title in titles[:3]:
                    lines.append(f"  - {title}")
                lines.append("")

        return "\n".join(lines)

    def _performance_section(self, portfolio_metrics: Dict, performance_metrics: Dict) -> str:
        lines = ["## 5. 포트폴리오 성과 지표\n"]

        if portfolio_metrics:
            lines.append("### 포트폴리오 전체 성과\n")
            for k, v in portfolio_metrics.items():
                lines.append(f"- **{k}:** {v}")

        if performance_metrics:
            lines.append("\n### 종목별 수익률\n")
            lines.append("| 종목 | 1주 | 1개월 | 3개월 | 6개월 | 변동성(20일) |")
            lines.append("|------|-----|-------|-------|-------|-------------|")

            for name, perf in sorted(
                performance_metrics.items(),
                key=lambda x: x[1].get("수익률_1주", 0) or 0,
                reverse=True,
            ):
                w = perf.get("수익률_1주")
                m = perf.get("수익률_1개월")
                q = perf.get("수익률_3개월")
                h = perf.get("수익률_6개월")
                vol = perf.get("변동성_20일")

                lines.append(
                    f"| {name} | "
                    f"{self._fmt_pct(w)} | {self._fmt_pct(m)} | "
                    f"{self._fmt_pct(q)} | {self._fmt_pct(h)} | "
                    f"{self._fmt_pct(vol)} |"
                )

        return "\n".join(lines)

    def _rebalancing_section(self, recommendations: List[Dict]) -> str:
        lines = ["## 6. 리밸런싱 추천\n"]

        for rec in recommendations:
            lines.append(f"### {rec['계좌명']}")
            lines.append(f"총 평가액: {rec['총평가액']:,.0f}원\n")

            # 위험 경고
            warnings = rec.get("위험경고", [])
            if warnings:
                lines.append("**위험 경고:**")
                for w in warnings:
                    lines.append(f"  {w}")
                lines.append("")

            # 리밸런싱 액션
            actions = rec.get("리밸런싱_액션", [])
            buy_actions = [a for a in actions if a["액션"] == "매수"]
            sell_actions = [a for a in actions if a["액션"] == "매도"]
            hold_actions = [a for a in actions if a["액션"] == "유지"]

            if sell_actions:
                lines.append("#### 🔴 매도 추천")
                lines.append("| 종목 | 현재비중 | 목표비중 | 변경 | 예상금액 | 사유 |")
                lines.append("|------|---------|---------|------|---------|------|")
                for a in sell_actions:
                    lines.append(
                        f"| {a['종목']} | {a['현재비중']} | {a['목표비중']} | "
                        f"{a['비중변경']} | {a['예상금액']} | {a['사유']} |"
                    )
                lines.append("")

            if buy_actions:
                lines.append("#### 🟢 매수 추천")
                lines.append("| 종목 | 현재비중 | 목표비중 | 변경 | 예상금액 | 사유 |")
                lines.append("|------|---------|---------|------|---------|------|")
                for a in buy_actions:
                    lines.append(
                        f"| {a['종목']} | {a['현재비중']} | {a['목표비중']} | "
                        f"{a['비중변경']} | {a['예상금액']} | {a['사유']} |"
                    )
                lines.append("")

            if hold_actions:
                lines.append("#### ⚪ 유지")
                for a in hold_actions:
                    lines.append(f"  - {a['종목']} ({a['현재비중']})")
                lines.append("")

        return "\n".join(lines)

    def _overall_opinion(
        self, economic: Dict, technical: Dict,
        news: Dict, rebalancing: List[Dict]
    ) -> str:
        lines = ["## 7. 종합 의견\n"]

        # 시장 환경
        regime = economic.get("시장환경", {}).get("판단", "혼조세")
        lines.append(f"### 시장 환경: {regime}\n")

        # 기술적 분석 종합
        if technical:
            buy_count = sum(1 for t in technical.values() if "매수" in t.get("종합판단", ""))
            sell_count = sum(1 for t in technical.values() if "매도" in t.get("종합판단", ""))
            neutral_count = len(technical) - buy_count - sell_count
            lines.append(f"- 기술적 분석: 매수 {buy_count}종목 / 매도 {sell_count}종목 / 중립 {neutral_count}종목")

        # 뉴스 감성
        sentiment = news.get("종합감성", "중립")
        lines.append(f"- 뉴스 감성: {sentiment}")

        # 핵심 추천사항
        lines.append("\n### 이번 주 핵심 추천사항\n")

        for rec in rebalancing:
            actions = rec.get("리밸런싱_액션", [])
            important = [a for a in actions if a["우선순위"] == 1]
            if important:
                lines.append(f"**{rec['계좌명']}:**")
                for a in important:
                    emoji = "🟢" if a["액션"] == "매수" else "🔴"
                    lines.append(f"  {emoji} {a['종목']}: {a['액션']} ({a['사유']})")
                lines.append("")

        lines.append("\n---")
        lines.append(f"*본 리포트는 자동 생성된 분석 자료이며, 투자 결정의 최종 책임은 투자자에게 있습니다.*")
        lines.append(f"*생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

        return "\n".join(lines)

    def _fmt_pct(self, value: Optional[float]) -> str:
        if value is None:
            return "N/A"
        return f"{value:+.2%}"

    def _sanitize_for_json(self, obj):
        """JSON 직렬화 가능하도록 변환"""
        if isinstance(obj, dict):
            return {k: self._sanitize_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._sanitize_for_json(v) for v in obj]
        elif isinstance(obj, float):
            if obj != obj:  # NaN check
                return None
            return obj
        elif isinstance(obj, (int, str, bool, type(None))):
            return obj
        else:
            return str(obj)

    def _save_json_data(self, filepath: str, data: Dict):
        """JSON 데이터 저장"""
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            logger.info(f"JSON 데이터 저장: {filepath}")
        except Exception as e:
            logger.error(f"JSON 저장 실패: {e}")
