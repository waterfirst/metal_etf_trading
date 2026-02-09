"""
투자 분석 대시보드 (Streamlit)
기존 metal_etf_trading.py와 별도로, 연금 포트폴리오 전용 대시보드
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import sys
import os
import json
import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.market_data_agent import MarketDataAgent
from agents.technical_analysis_agent import TechnicalAnalysisAgent
from agents.economic_indicator_agent import EconomicIndicatorAgent
from agents.rebalancing_agent import RebalancingAgent
from config.portfolio import ALL_ACCOUNTS, ETF_SECTORS

st.set_page_config(
    page_title="연금 투자 분석 대시보드",
    page_icon="📊",
    layout="wide",
)

st.title("📊 연금 포트폴리오 투자 분석 대시보드")
st.caption(f"최종 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# 사이드바
with st.sidebar:
    st.header("설정")
    lookback = st.selectbox("분석 기간", [90, 180, 365, 730], index=2, format_func=lambda x: f"{x}일")
    account_choice = st.radio("계좌 선택", ["전체", "연금저축 CMA", "퇴직연금 DC"])
    auto_refresh = st.button("🔄 데이터 새로고침")

    st.markdown("---")
    st.markdown("### 실행 방법")
    st.code("python investment_agent.py", language="bash")
    st.markdown("주간 리포트 자동생성:")
    st.code("python investment_agent.py --schedule", language="bash")


@st.cache_data(ttl=300)
def load_data(lookback_days):
    """데이터 로드 (5분 캐시)"""
    agent = MarketDataAgent(lookback_days=lookback_days)
    prices = agent.fetch_etf_prices()
    econ = agent.fetch_economic_indicators()
    valuation = agent.calculate_portfolio_valuation()
    perf = agent.get_performance_metrics()
    correlation = agent.get_correlation_matrix()
    return prices, econ, valuation, perf, correlation, agent


# 데이터 로드
with st.spinner("데이터 로드 중..."):
    prices, econ_data, valuations, perf_metrics, corr_matrix, market_agent = load_data(lookback)

# 기술적 분석
tech_agent = TechnicalAnalysisAgent()
tech_analysis = tech_agent.analyze_all(prices)

# 경제지표 분석
econ_agent = EconomicIndicatorAgent()
econ_analysis = econ_agent.analyze(econ_data)

# ── 탭 구성 ──
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📋 포트폴리오", "📈 기술적 분석", "🌍 경제지표", "🔄 리밸런싱", "📰 리포트"
])

# ── TAB 1: 포트폴리오 현황 ──
with tab1:
    total_all = sum(a["총평가액"] for a in valuations)
    st.metric("전체 연금자산", f"{total_all:,.0f}원")

    cols = st.columns(len(valuations))
    for i, acct in enumerate(valuations):
        with cols[i]:
            st.subheader(acct["계좌명"])
            st.metric("평가액", f"{acct['총평가액']:,.0f}원")

            df = pd.DataFrame(acct["보유종목"])
            df["비중(%)"] = df["비중"].apply(lambda x: f"{x:.1%}")
            df["평가금액"] = df["평가금액"].apply(lambda x: f"{x:,.0f}")
            st.dataframe(
                df[["종목명", "보유수량", "평가금액", "비중(%)", "섹터"]],
                use_container_width=True,
                hide_index=True,
            )

            # 자산배분 파이차트
            fig = px.pie(
                df, values="비중", names="자산유형",
                title=f"{acct['계좌명']} 자산배분",
            )
            fig.update_layout(height=350)
            st.plotly_chart(fig, use_container_width=True)

    # 상관관계 히트맵
    if corr_matrix is not None and len(corr_matrix) > 1:
        st.subheader("ETF 상관관계")
        fig = px.imshow(
            corr_matrix, text_auto=".2f", color_continuous_scale="RdBu_r",
            zmin=-1, zmax=1, title="ETF 수익률 상관관계"
        )
        fig.update_layout(height=500)
        st.plotly_chart(fig, use_container_width=True)

# ── TAB 2: 기술적 분석 ──
with tab2:
    st.subheader("종목별 기술적 분석")

    if tech_analysis:
        # 종합 시그널 테이블
        signal_data = []
        for name, analysis in tech_analysis.items():
            judgment = analysis.get("종합판단", "N/A")
            color_map = {
                "강력매수": "🟢🟢", "매수": "🟢", "중립": "🟡",
                "매도": "🔴", "강력매도": "🔴🔴"
            }
            signal_data.append({
                "종목": name,
                "시그널": f"{color_map.get(judgment, '')} {judgment}",
                "점수": analysis.get("종합점수", 0),
                "추세": analysis.get("추세", ""),
                "RSI": analysis.get("기술지표", {}).get("RSI", None),
            })

        sig_df = pd.DataFrame(signal_data)
        sig_df = sig_df.sort_values("점수", ascending=False)
        st.dataframe(sig_df, use_container_width=True, hide_index=True)

        # 개별 종목 차트
        selected = st.selectbox("종목 선택", list(prices.keys()))
        if selected and selected in prices:
            df = prices[selected]
            fig = go.Figure()
            fig.add_trace(go.Candlestick(
                x=df.index, open=df["Open"], high=df["High"],
                low=df["Low"], close=df["Close"], name=selected
            ))

            # 이동평균선 추가
            for period, color in [(20, "orange"), (60, "blue"), (120, "purple")]:
                if len(df) >= period:
                    ma = df["Close"].rolling(period).mean()
                    fig.add_trace(go.Scatter(
                        x=df.index, y=ma, name=f"MA{period}",
                        line=dict(color=color, width=1)
                    ))

            fig.update_layout(
                title=f"{selected} 가격 차트", height=500,
                xaxis_rangeslider_visible=False
            )
            st.plotly_chart(fig, use_container_width=True)

            # 세부 시그널
            if selected in tech_analysis:
                st.write("**시그널 상세:**")
                for s in tech_analysis[selected].get("시그널", []):
                    st.write(f"- **{s['지표']}**: {s['판단']} (점수: {s['점수']}) - {s['설명']}")
    else:
        st.warning("기술적 분석 데이터가 없습니다.")

# ── TAB 3: 경제지표 ──
with tab3:
    st.subheader("거시경제 환경")

    regime = econ_analysis.get("시장환경", {})
    col1, col2, col3 = st.columns(3)
    col1.metric("시장 환경", regime.get("판단", "N/A"))
    col2.metric("종합 점수", f"{regime.get('평균점수', 0)}/5.0")
    col3.metric("권고", regime.get("권고", "N/A")[:20])

    signals = econ_analysis.get("시그널", [])
    if signals:
        econ_df = pd.DataFrame(signals)
        st.dataframe(econ_df, use_container_width=True, hide_index=True)

    # 주요 경제지표 차트
    st.subheader("경제지표 추이")
    indicator_choice = st.multiselect(
        "지표 선택", list(econ_data.keys()),
        default=["KOSPI", "S&P 500"] if "KOSPI" in econ_data else list(econ_data.keys())[:2]
    )
    if indicator_choice:
        fig = go.Figure()
        for ind in indicator_choice:
            if ind in econ_data:
                df = econ_data[ind]
                normalized = df["Close"] / df["Close"].iloc[0] * 100
                fig.add_trace(go.Scatter(
                    x=df.index, y=normalized, name=ind, mode="lines"
                ))
        fig.update_layout(
            title="경제지표 정규화 추이 (시작=100)",
            height=400, yaxis_title="정규화 지수"
        )
        st.plotly_chart(fig, use_container_width=True)

# ── TAB 4: 리밸런싱 ──
with tab4:
    st.subheader("리밸런싱 추천")

    rebal_agent = RebalancingAgent()
    news_dummy = {"종합감성": "중립"}
    recs = rebal_agent.generate_recommendations(
        valuations, tech_analysis, econ_analysis, news_dummy
    )

    for rec in recs:
        st.markdown(f"### {rec['계좌명']}")

        # 위험 경고
        for w in rec.get("위험경고", []):
            if "⚠️" in w:
                st.warning(w)
            else:
                st.success(w)

        actions = rec.get("리밸런싱_액션", [])
        if actions:
            action_df = pd.DataFrame(actions)
            st.dataframe(action_df, use_container_width=True, hide_index=True)

        # 포트폴리오 성과
        metrics = rebal_agent.calculate_portfolio_metrics(
            prices, next(a for a in valuations if a["계좌명"] == rec["계좌명"])["보유종목"]
        )
        if metrics and "오류" not in metrics:
            mcols = st.columns(5)
            for i, (k, v) in enumerate(metrics.items()):
                if i < 5:
                    mcols[i].metric(k, str(v))

# ── TAB 5: 리포트 ──
with tab5:
    st.subheader("저장된 리포트")

    report_dir = os.path.join(os.path.dirname(__file__), "reports")
    report_files = sorted(glob.glob(os.path.join(report_dir, "weekly_report_*.md")), reverse=True)

    if report_files:
        selected_report = st.selectbox(
            "리포트 선택",
            report_files,
            format_func=lambda x: os.path.basename(x)
        )
        if selected_report:
            with open(selected_report, "r", encoding="utf-8") as f:
                st.markdown(f.read())
    else:
        st.info("저장된 리포트가 없습니다. `python investment_agent.py`를 실행하여 리포트를 생성하세요.")

    if st.button("지금 리포트 생성"):
        with st.spinner("분석 진행 중..."):
            from investment_agent import InvestmentAnalysisAgent
            agent = InvestmentAnalysisAgent(lookback_days=lookback)
            report = agent.run_full_analysis(skip_news=True)
            st.markdown(report)
            st.success("리포트 생성 완료!")
