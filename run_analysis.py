"""
투자 분석 실행 + 시각화 차트 PNG 저장
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger()

from agents.market_data_agent import MarketDataAgent
from agents.technical_analysis_agent import TechnicalAnalysisAgent
from agents.economic_indicator_agent import EconomicIndicatorAgent
from agents.news_agent import NewsAgent
from agents.rebalancing_agent import RebalancingAgent
from agents.report_agent import ReportAgent
from config.portfolio import ALL_ACCOUNTS, ETF_SECTORS, ASSET_CLASSES

CHART_DIR = os.path.join(os.path.dirname(__file__), "reports", "charts")
os.makedirs(CHART_DIR, exist_ok=True)

# ══════════════════════════════════════════════
# 1. 데이터 수집
# ══════════════════════════════════════════════
logger.info("=" * 60)
logger.info("투자 분석 + 시각화 차트 생성 시작")
logger.info("=" * 60)

market_agent = MarketDataAgent(lookback_days=365)

logger.info("[1/7] ETF 가격 데이터 수집...")
prices = market_agent.fetch_etf_prices()

logger.info("[2/7] 경제지표 수집...")
econ_data = market_agent.fetch_economic_indicators()

logger.info("[3/7] 포트폴리오 평가...")
valuations = market_agent.calculate_portfolio_valuation()
perf_metrics = market_agent.get_performance_metrics()
corr_matrix = market_agent.get_correlation_matrix()

logger.info("[4/7] 기술적 분석...")
tech_agent = TechnicalAnalysisAgent()
tech_analysis = tech_agent.analyze_all(prices)

logger.info("[5/7] 경제지표 분석...")
econ_agent = EconomicIndicatorAgent()
econ_analysis = econ_agent.analyze(econ_data)

logger.info("[6/7] 뉴스 수집 및 분석...")
try:
    news_agent = NewsAgent()
    all_news = news_agent.collect_all_news()
    news_summary = news_agent.analyze_sentiment_summary(all_news)
except Exception as e:
    logger.warning(f"뉴스 수집 실패: {e}")
    news_summary = {"종합감성": "중립", "긍정기사수": 0, "부정기사수": 0, "중립기사수": 0}
    all_news = {}

logger.info("[7/7] 리밸런싱 추천...")
rebal_agent = RebalancingAgent()
rebal_recs = rebal_agent.generate_recommendations(
    valuations, tech_analysis, econ_analysis, news_summary
)

# 포트폴리오 성과
portfolio_metrics = {}
for acct in valuations:
    m = rebal_agent.calculate_portfolio_metrics(prices, acct["보유종목"])
    portfolio_metrics[acct["계좌명"]] = m

# ══════════════════════════════════════════════
# 리포트 생성
# ══════════════════════════════════════════════
report_agent = ReportAgent()
report = report_agent.generate_weekly_report(
    portfolio_valuation=valuations,
    technical_analysis=tech_analysis,
    economic_analysis=econ_analysis,
    news_summary=news_summary,
    rebalancing_recommendations=rebal_recs,
    portfolio_metrics=portfolio_metrics,
    performance_metrics=perf_metrics,
)
logger.info("리포트 생성 완료!")

# ══════════════════════════════════════════════
# 시각화 차트 생성 + PNG 저장
# ══════════════════════════════════════════════
logger.info("차트 생성 시작...")

COLORS = px.colors.qualitative.Set2

# ── 차트 1: 계좌별 자산배분 파이차트 ──
for i, acct in enumerate(valuations):
    df = pd.DataFrame(acct["보유종목"])
    df = df.sort_values("평가금액", ascending=False)

    fig = px.pie(
        df, values="평가금액", names="종목명",
        title=f"{acct['계좌명']} 종목별 비중<br><sub>총 평가액: {acct['총평가액']:,.0f}원</sub>",
        color_discrete_sequence=COLORS,
        hole=0.35,
    )
    fig.update_traces(textposition="outside", textinfo="label+percent")
    fig.update_layout(
        width=900, height=650,
        font=dict(size=13),
        legend=dict(orientation="h", yanchor="bottom", y=-0.2, x=0.5, xanchor="center"),
    )
    fname = f"chart_01_portfolio_pie_{i+1}.png"
    fig.write_image(os.path.join(CHART_DIR, fname), scale=2)
    logger.info(f"  저장: {fname}")

# ── 차트 2: 자산유형별 배분 ──
fig = make_subplots(rows=1, cols=2, specs=[[{"type": "pie"}, {"type": "pie"}]],
                     subplot_titles=[a["계좌명"] for a in valuations])
for i, acct in enumerate(valuations):
    asset_map = {}
    for h in acct["보유종목"]:
        a = h["자산유형"]
        asset_map[a] = asset_map.get(a, 0) + h["평가금액"]
    fig.add_trace(
        go.Pie(labels=list(asset_map.keys()), values=list(asset_map.values()),
               hole=0.4, textinfo="label+percent"),
        row=1, col=i+1
    )
fig.update_layout(
    title_text="자산유형별 배분 현황", width=1200, height=550,
    font=dict(size=13), showlegend=True
)
fig.write_image(os.path.join(CHART_DIR, "chart_02_asset_allocation.png"), scale=2)
logger.info("  저장: chart_02_asset_allocation.png")

# ── 차트 3: ETF 수익률 비교 (기간별) ──
if perf_metrics:
    etf_names = []
    ret_1w = []
    ret_1m = []
    ret_3m = []
    for name, perf in perf_metrics.items():
        etf_names.append(name)
        ret_1w.append((perf.get("수익률_1주") or 0) * 100)
        ret_1m.append((perf.get("수익률_1개월") or 0) * 100)
        ret_3m.append((perf.get("수익률_3개월") or 0) * 100)

    fig = go.Figure()
    fig.add_trace(go.Bar(name="1주", x=etf_names, y=ret_1w, marker_color="#4ecdc4"))
    fig.add_trace(go.Bar(name="1개월", x=etf_names, y=ret_1m, marker_color="#45b7d1"))
    fig.add_trace(go.Bar(name="3개월", x=etf_names, y=ret_3m, marker_color="#6c5ce7"))
    fig.update_layout(
        title="ETF 기간별 수익률 비교 (%)",
        barmode="group", width=1400, height=600,
        xaxis_tickangle=-30, font=dict(size=12),
        yaxis_title="수익률 (%)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.5, xanchor="center"),
    )
    fig.update_traces(texttemplate="%{y:.1f}%", textposition="outside")
    fig.write_image(os.path.join(CHART_DIR, "chart_03_returns_comparison.png"), scale=2)
    logger.info("  저장: chart_03_returns_comparison.png")

# ── 차트 4: 기술적 분석 시그널 히트맵 ──
if tech_analysis:
    signal_names = set()
    for analysis in tech_analysis.values():
        for s in analysis.get("시그널", []):
            signal_names.add(s["지표"])
    signal_names = sorted(signal_names)

    etf_list = sorted(tech_analysis.keys())
    z_data = []
    text_data = []
    for etf in etf_list:
        row = []
        text_row = []
        signal_map = {s["지표"]: s for s in tech_analysis[etf].get("시그널", [])}
        for sig_name in signal_names:
            if sig_name in signal_map:
                row.append(signal_map[sig_name]["점수"])
                text_row.append(signal_map[sig_name]["판단"])
            else:
                row.append(3)
                text_row.append("N/A")
        z_data.append(row)
        text_data.append(text_row)

    fig = go.Figure(data=go.Heatmap(
        z=z_data, x=signal_names, y=etf_list,
        text=text_data, texttemplate="%{text}",
        colorscale=[[0, "#e74c3c"], [0.25, "#e67e22"], [0.5, "#f1c40f"],
                     [0.75, "#2ecc71"], [1, "#27ae60"]],
        zmin=1, zmax=5,
        colorbar=dict(title="점수", tickvals=[1, 2, 3, 4, 5],
                      ticktext=["강력매도", "매도", "중립", "매수", "강력매수"]),
    ))
    fig.update_layout(
        title="종목별 기술적 분석 시그널 히트맵",
        width=1200, height=max(500, len(etf_list) * 50 + 150),
        font=dict(size=12),
        xaxis_title="기술 지표", yaxis_title="종목",
    )
    fig.write_image(os.path.join(CHART_DIR, "chart_04_technical_heatmap.png"), scale=2)
    logger.info("  저장: chart_04_technical_heatmap.png")

# ── 차트 5: 주요 ETF 가격 추이 (이동평균선) ──
top_etfs = sorted(perf_metrics.keys(), key=lambda x: abs(perf_metrics[x].get("수익률_3개월") or 0), reverse=True)[:6]
fig = make_subplots(rows=3, cols=2, subplot_titles=top_etfs, vertical_spacing=0.08)

for idx, etf in enumerate(top_etfs):
    row = idx // 2 + 1
    col = idx % 2 + 1
    if etf not in prices:
        continue
    df = prices[etf]
    close = df["Close"]

    fig.add_trace(go.Scatter(x=df.index, y=close, name=etf, mode="lines",
                              line=dict(width=1.5), showlegend=False), row=row, col=col)
    if len(close) >= 20:
        ma20 = close.rolling(20).mean()
        fig.add_trace(go.Scatter(x=df.index, y=ma20, name="MA20", mode="lines",
                                  line=dict(width=1, color="orange", dash="dash"),
                                  showlegend=(idx == 0)), row=row, col=col)
    if len(close) >= 60:
        ma60 = close.rolling(60).mean()
        fig.add_trace(go.Scatter(x=df.index, y=ma60, name="MA60", mode="lines",
                                  line=dict(width=1, color="blue", dash="dot"),
                                  showlegend=(idx == 0)), row=row, col=col)

fig.update_layout(title="주요 ETF 가격 추이 (MA20/MA60)", width=1400, height=1000, font=dict(size=11))
fig.write_image(os.path.join(CHART_DIR, "chart_05_price_trends.png"), scale=2)
logger.info("  저장: chart_05_price_trends.png")

# ── 차트 6: 경제지표 추이 ──
key_indicators = ["KOSPI", "S&P 500", "VIX", "USD/KRW", "금 선물", "달러인덱스"]
fig = make_subplots(rows=3, cols=2, subplot_titles=key_indicators, vertical_spacing=0.08)

for idx, ind in enumerate(key_indicators):
    row = idx // 2 + 1
    col = idx % 2 + 1
    if ind not in econ_data:
        continue
    df = econ_data[ind]
    fig.add_trace(go.Scatter(
        x=df.index, y=df["Close"], name=ind, mode="lines",
        line=dict(width=1.5), showlegend=False
    ), row=row, col=col)

fig.update_layout(title="주요 경제지표 추이", width=1400, height=1000, font=dict(size=11))
fig.write_image(os.path.join(CHART_DIR, "chart_06_economic_indicators.png"), scale=2)
logger.info("  저장: chart_06_economic_indicators.png")

# ── 차트 7: 상관관계 히트맵 ──
if corr_matrix is not None and len(corr_matrix) > 1:
    fig = px.imshow(
        corr_matrix, text_auto=".2f", color_continuous_scale="RdBu_r",
        zmin=-1, zmax=1, title="ETF 수익률 상관관계 매트릭스",
    )
    fig.update_layout(width=1000, height=900, font=dict(size=11))
    fig.write_image(os.path.join(CHART_DIR, "chart_07_correlation_matrix.png"), scale=2)
    logger.info("  저장: chart_07_correlation_matrix.png")

# ── 차트 8: 리밸런싱 추천 시각화 ──
for i, rec in enumerate(rebal_recs):
    actions = rec.get("리밸런싱_액션", [])
    if not actions:
        continue

    names = [a["종목"] for a in actions]
    current_w = [float(a["현재비중"].strip("%")) for a in actions]
    target_w = [float(a["목표비중"].strip("%")) for a in actions]

    fig = go.Figure()
    fig.add_trace(go.Bar(name="현재 비중", x=names, y=current_w, marker_color="#95a5a6"))
    fig.add_trace(go.Bar(name="목표 비중", x=names, y=target_w, marker_color="#3498db"))
    fig.update_layout(
        title=f"{rec['계좌명']} - 리밸런싱 비중 변경 추천",
        barmode="group", width=1300, height=550,
        xaxis_tickangle=-25, font=dict(size=12),
        yaxis_title="비중 (%)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.5, xanchor="center"),
    )
    fname = f"chart_08_rebalancing_{i+1}.png"
    fig.write_image(os.path.join(CHART_DIR, fname), scale=2)
    logger.info(f"  저장: {fname}")

# ── 차트 9: 종합 점수 레이더 차트 ──
if tech_analysis:
    top5 = sorted(tech_analysis.items(), key=lambda x: x[1].get("종합점수", 0), reverse=True)[:8]

    fig = go.Figure()
    for name, analysis in top5:
        signals = analysis.get("시그널", [])
        if not signals:
            continue
        categories = [s["지표"] for s in signals]
        values = [s["점수"] for s in signals]
        categories.append(categories[0])
        values.append(values[0])
        fig.add_trace(go.Scatterpolar(
            r=values, theta=categories, name=f"{name} ({analysis.get('종합점수', 0)})",
            fill="toself", opacity=0.6,
        ))

    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 5.5])),
        title="종목별 기술 지표 레이더 차트", width=1000, height=800,
        font=dict(size=11),
    )
    fig.write_image(os.path.join(CHART_DIR, "chart_09_radar.png"), scale=2)
    logger.info("  저장: chart_09_radar.png")

# ── 차트 10: 뉴스 감성 분석 ──
if news_summary.get("긍정기사수", 0) + news_summary.get("부정기사수", 0) > 0:
    labels = ["긍정", "부정", "중립"]
    values = [
        news_summary.get("긍정기사수", 0),
        news_summary.get("부정기사수", 0),
        news_summary.get("중립기사수", 0),
    ]
    colors = ["#2ecc71", "#e74c3c", "#95a5a6"]

    fig = go.Figure()
    fig.add_trace(go.Pie(
        labels=labels, values=values, marker=dict(colors=colors),
        hole=0.4, textinfo="label+value+percent",
    ))
    fig.update_layout(
        title=f"뉴스 감성 분석 (종합: {news_summary.get('종합감성', 'N/A')})",
        width=700, height=550, font=dict(size=13),
    )
    fig.write_image(os.path.join(CHART_DIR, "chart_10_news_sentiment.png"), scale=2)
    logger.info("  저장: chart_10_news_sentiment.png")

logger.info("=" * 60)
logger.info("모든 작업 완료!")
logger.info(f"리포트: reports/weekly_report_{datetime.now().strftime('%Y-%m-%d')}.md")
logger.info(f"차트: reports/charts/ 디렉토리")
logger.info("=" * 60)
