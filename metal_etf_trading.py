import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import plotly.graph_objects as go
import plotly.express as px

# 페이지 설정
st.set_page_config(
    page_title="귀금속 ETF 트레이딩 신호",
    page_icon="🥇",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS 스타일링
st.markdown("""
<style>
    .main-header {
        font-size: 2.8rem;
        font-weight: bold;
        color: #FFD700;
        text-align: center;
        margin-bottom: 1rem;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
    }
    .signal-strong-buy {
        background: linear-gradient(135deg, #00aa00 0%, #28a745 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 12px;
        font-size: 1.3rem;
        font-weight: bold;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.2);
        margin: 10px 0;
    }
    .signal-buy {
        background: linear-gradient(135deg, #28a745 0%, #5cb85c 100%);
        color: white;
        padding: 1.2rem;
        border-radius: 10px;
        font-size: 1.15rem;
        font-weight: bold;
        text-align: center;
        box-shadow: 0 3px 5px rgba(0,0,0,0.15);
        margin: 10px 0;
    }
    .signal-neutral {
        background: linear-gradient(135deg, #ffc107 0%, #ffdb4d 100%);
        color: #333;
        padding: 1rem;
        border-radius: 10px;
        font-size: 1.1rem;
        font-weight: bold;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin: 10px 0;
    }
    .signal-sell {
        background: linear-gradient(135deg, #dc3545 0%, #c82333 100%);
        color: white;
        padding: 1.2rem;
        border-radius: 10px;
        font-size: 1.15rem;
        font-weight: bold;
        text-align: center;
        box-shadow: 0 3px 5px rgba(0,0,0,0.15);
        margin: 10px 0;
    }
    .signal-strong-sell {
        background: linear-gradient(135deg, #990000 0%, #dc3545 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 12px;
        font-size: 1.3rem;
        font-weight: bold;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.2);
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

# ETF 티커 맵핑
METAL_ETFS = {
    'gold': {
        'symbol': 'GLD',
        'name': '금 (Gold ETF)',
        'ticker': 'GLD',
        'futures': 'GC=F',
        'color': '#FFD700'
    },
    'silver': {
        'symbol': 'SLV',
        'name': '은 (Silver ETF)',
        'ticker': 'SLV',
        'futures': 'SI=F',
        'color': '#C0C0C0'
    },
    'copper': {
        'symbol': 'COPX',
        'name': '구리 (Copper ETF)',
        'ticker': 'COPX',
        'futures': 'HG=F',
        'color': '#B87333'
    }
}

# 보조 지표
SUPPORTING_INDICES = {
    'dxy': {'symbol': 'DX-Y.NYB', 'name': '달러지수'},
    'us10y': {'symbol': '^TNX', 'name': '미10년물'},
    'spx': {'symbol': '^GSPC', 'name': 'S&P500'},
    'vix': {'symbol': '^VIX', 'name': 'VIX'}
}

# ============================================================================
# 데이터 수집 함수
# ============================================================================

@st.cache_data(ttl=300)
def fetch_etf_data(lookback_days=365):
    """ETF 및 선물 데이터 수집"""
    data = {}
    end_date = datetime.now()
    start_date = end_date - timedelta(days=lookback_days)
    
    for key, info in METAL_ETFS.items():
        try:
            # ETF 데이터
            etf = yf.Ticker(info['symbol'])
            etf_hist = etf.history(start=start_date, end=end_date)
            
            # 선물 데이터
            futures = yf.Ticker(info['futures'])
            futures_hist = futures.history(period="5d")
            
            if not etf_hist.empty and not futures_hist.empty:
                data[key] = {
                    'etf_history': etf_hist,
                    'futures_current': futures_hist['Close'].iloc[-1],
                    'futures_prev': futures_hist['Close'].iloc[-2] if len(futures_hist) >= 2 else futures_hist['Close'].iloc[-1],
                    'etf_current': etf_hist['Close'].iloc[-1],
                    'etf_prev': etf_hist['Close'].iloc[-2] if len(etf_hist) >= 2 else etf_hist['Close'].iloc[-1],
                    'info': info
                }
        except Exception as e:
            st.warning(f"{info['name']} 데이터 로드 실패: {str(e)}")
            continue
    
    return data

@st.cache_data(ttl=300)
def fetch_supporting_data():
    """보조 지표 데이터 수집"""
    data = {}
    
    for key, info in SUPPORTING_INDICES.items():
        try:
            ticker = yf.Ticker(info['symbol'])
            hist = ticker.history(period="5d")
            
            if not hist.empty:
                data[key] = {
                    'current': hist['Close'].iloc[-1],
                    'prev': hist['Close'].iloc[-2] if len(hist) >= 2 else hist['Close'].iloc[-1],
                    'change_pct': ((hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2] * 100) if len(hist) >= 2 else 0
                }
        except Exception as e:
            continue
    
    return data

# ============================================================================
# 분석 함수
# ============================================================================

def calculate_gold_silver_ratio(gold_price, silver_price):
    """금은비율 계산 및 5단계 신호 생성"""
    if silver_price == 0:
        return None
    
    ratio = gold_price / silver_price
    
    if ratio > 90:
        return {
            'ratio': ratio,
            'signal': '🟢🟢 은 강력매수',
            'level': 'strong_buy_silver',
            'description': f'금은비율 {ratio:.1f} - 은 심각한 저평가',
            'action': '은 ETF 적극 매수, 금 ETF 일부 매도 고려',
            'score': 5
        }
    elif ratio > 82:
        return {
            'ratio': ratio,
            'signal': '🟢 은 매수',
            'level': 'buy_silver',
            'description': f'금은비율 {ratio:.1f} - 은 저평가',
            'action': '은 ETF 매수 기회',
            'score': 4
        }
    elif ratio < 60:
        return {
            'ratio': ratio,
            'signal': '🔴🔴 금 강력매수',
            'level': 'strong_buy_gold',
            'description': f'금은비율 {ratio:.1f} - 금 심각한 저평가',
            'action': '금 ETF 적극 매수, 은 ETF 일부 매도 고려',
            'score': 5
        }
    elif ratio < 68:
        return {
            'ratio': ratio,
            'signal': '🔴 금 매수',
            'level': 'buy_gold',
            'description': f'금은비율 {ratio:.1f} - 금 저평가',
            'action': '금 ETF 매수 기회',
            'score': 4
        }
    else:
        return {
            'ratio': ratio,
            'signal': '🟡 중립',
            'level': 'neutral',
            'description': f'금은비율 {ratio:.1f} - 정상 범위 (68-82)',
            'action': '관망 또는 균형 유지',
            'score': 3
        }

def calculate_copper_gold_ratio(copper_price, gold_price):
    """구리/금 비율 - 경기 심리 온도계"""
    if gold_price == 0:
        return None
    
    ratio = (copper_price / gold_price) * 1000
    
    if ratio > 1.5:
        return {
            'ratio': ratio,
            'signal': '🟢 경기 확장',
            'level': 'risk_on',
            'description': f'구리/금 비율 {ratio:.2f} - 리스크 온, 경기 낙관',
            'action': '구리 ETF 강세, 금 ETF 약세 예상',
            'score': 4
        }
    elif ratio < 0.8:
        return {
            'ratio': ratio,
            'signal': '🔴 경기 둔화',
            'level': 'risk_off',
            'description': f'구리/금 비율 {ratio:.2f} - 리스크 오프, 경기 우려',
            'action': '금 ETF 강세, 구리 ETF 약세 예상',
            'score': 2
        }
    else:
        return {
            'ratio': ratio,
            'signal': '🟡 균형',
            'level': 'balanced',
            'description': f'구리/금 비율 {ratio:.2f} - 균형 상태',
            'action': '혼재된 신호, 다른 지표 참고',
            'score': 3
        }

def generate_trading_signals(metal_data, supporting_data):
    """통합 신호 생성"""
    signals = {}
    
    if not metal_data:
        return signals
    
    # 1. 금은비율
    if 'gold' in metal_data and 'silver' in metal_data:
        gold_price = metal_data['gold']['futures_current']
        silver_price = metal_data['silver']['futures_current']
        gs_signal = calculate_gold_silver_ratio(gold_price, silver_price)
        
        if gs_signal:
            signals['gold_silver_ratio'] = gs_signal
    
    # 2. 구리/금 비율
    if 'copper' in metal_data and 'gold' in metal_data:
        copper_price = metal_data['copper']['futures_current']
        gold_price = metal_data['gold']['futures_current']
        cg_signal = calculate_copper_gold_ratio(copper_price, gold_price)
        
        if cg_signal:
            signals['copper_gold_ratio'] = cg_signal
    
    # 3. 개별 모멘텀
    for key, data in metal_data.items():
        etf_change = ((data['etf_current'] - data['etf_prev']) / data['etf_prev'] * 100)
        
        hist = data['etf_history']
        month_ago_price = hist['Close'].iloc[-20] if len(hist) >= 20 else hist['Close'].iloc[0]
        month_change = ((data['etf_current'] - month_ago_price) / month_ago_price * 100)
        
        quarter_ago_price = hist['Close'].iloc[-60] if len(hist) >= 60 else hist['Close'].iloc[0]
        quarter_change = ((data['etf_current'] - quarter_ago_price) / quarter_ago_price * 100)
        
        ytd_price = hist['Close'].iloc[0]
        ytd_change = ((data['etf_current'] - ytd_price) / ytd_price * 100)
        
        momentum_score = 0
        if month_change > 5: momentum_score += 1
        if quarter_change > 10: momentum_score += 1
        if ytd_change > 15: momentum_score += 1
        
        if momentum_score >= 2 and etf_change > 0:
            signal_level = 'strong_buy' if momentum_score == 3 else 'buy'
            signal_emoji = '🟢🟢' if momentum_score == 3 else '🟢'
            signal_text = '강력매수' if momentum_score == 3 else '매수'
            score = 5 if momentum_score == 3 else 4
        elif momentum_score <= -2 and etf_change < 0:
            signal_level = 'strong_sell'
            signal_emoji = '🔴🔴'
            signal_text = '강력매도'
            score = 1
        elif etf_change < -2:
            signal_level = 'sell'
            signal_emoji = '🔴'
            signal_text = '매도'
            score = 2
        else:
            signal_level = 'neutral'
            signal_emoji = '🟡'
            signal_text = '중립'
            score = 3
        
        signals[f'{key}_momentum'] = {
            'signal': f'{signal_emoji} {signal_text}',
            'level': signal_level,
            'description': f'1개월 {month_change:+.2f}% | 3개월 {quarter_change:+.2f}% | YTD {ytd_change:+.2f}%',
            'action': f'{data["info"]["name"]} ETF {"매수" if score >= 4 else "매도" if score <= 2 else "관망"}',
            'score': score,
            'day_change': etf_change
        }
    
    # 4. 거시경제
    macro_score = 3
    macro_factors = []
    
    if supporting_data:
        if 'dxy' in supporting_data:
            dxy_change = supporting_data['dxy']['change_pct']
            if dxy_change > 1:
                macro_score -= 1
                macro_factors.append(f"달러 강세 {dxy_change:+.2f}%")
            elif dxy_change < -1:
                macro_score += 1
                macro_factors.append(f"달러 약세 {dxy_change:+.2f}%")
        
        if 'vix' in supporting_data:
            vix_level = supporting_data['vix']['current']
            if vix_level > 25:
                macro_factors.append(f"VIX 높음 {vix_level:.1f}")
            elif vix_level < 15:
                macro_factors.append(f"VIX 낮음 {vix_level:.1f}")
        
        if 'spx' in supporting_data:
            spx_change = supporting_data['spx']['change_pct']
            if spx_change > 1:
                macro_factors.append(f"주식 강세 {spx_change:+.2f}%")
            elif spx_change < -1:
                macro_factors.append(f"주식 약세 {spx_change:+.2f}%")
    
    signals['macro_environment'] = {
        'signal': '🟢 우호적' if macro_score >= 4 else '🔴 불리' if macro_score <= 2 else '🟡 중립',
        'level': 'favorable' if macro_score >= 4 else 'unfavorable' if macro_score <= 2 else 'neutral',
        'description': ' | '.join(macro_factors) if macro_factors else '정상 범위',
        'score': macro_score
    }
    
    return signals

# ============================================================================
# 차트 렌더링 함수
# ============================================================================

def render_price_charts(metal_data):
    """가격 차트 렌더링"""
    st.subheader("📈 가격 추이 차트")
    
    tabs = st.tabs([data['info']['name'] for data in metal_data.values()] + ["통합 비교"])
    
    for idx, (key, data) in enumerate(metal_data.items()):
        with tabs[idx]:
            hist = data['etf_history']
            info = data['info']
            
            fig = go.Figure()
            
            fig.add_trace(go.Scatter(
                x=hist.index,
                y=hist['Close'],
                mode='lines',
                name='종가',
                line=dict(color=info['color'], width=2),
                hovertemplate='<b>%{x|%Y-%m-%d}</b><br>종가: $%{y:.2f}<extra></extra>'
            ))
            
            ma20 = hist['Close'].rolling(window=20).mean()
            ma50 = hist['Close'].rolling(window=50).mean()
            
            fig.add_trace(go.Scatter(
                x=hist.index,
                y=ma20,
                mode='lines',
                name='MA20',
                line=dict(color='orange', width=1, dash='dash'),
                opacity=0.7
            ))
            
            fig.add_trace(go.Scatter(
                x=hist.index,
                y=ma50,
                mode='lines',
                name='MA50',
                line=dict(color='red', width=1, dash='dot'),
                opacity=0.7
            ))
            
            fig.update_layout(
                title=f"{info['name']} ({info['ticker']}) ETF 가격 추이",
                xaxis_title="날짜",
                yaxis_title="가격 (USD)",
                height=400,
                hovermode='x unified',
                showlegend=True
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # 거래량
            fig_vol = go.Figure()
            fig_vol.add_trace(go.Bar(
                x=hist.index,
                y=hist['Volume'],
                name='거래량',
                marker_color=info['color'],
                opacity=0.6
            ))
            
            fig_vol.update_layout(
                title="거래량",
                height=200,
                showlegend=False
            )
            
            st.plotly_chart(fig_vol, use_container_width=True)
    
    # 통합 비교
    with tabs[-1]:
        fig_compare = go.Figure()
        
        for key, data in metal_data.items():
            hist = data['etf_history']
            info = data['info']
            normalized = (hist['Close'] / hist['Close'].iloc[0]) * 100
            
            fig_compare.add_trace(go.Scatter(
                x=hist.index,
                y=normalized,
                mode='lines',
                name=info['name'],
                line=dict(color=info['color'], width=2.5)
            ))
        
        fig_compare.update_layout(
            title="귀금속 ETF 상대 성과 비교 (시작점 = 100)",
            height=500,
            hovermode='x unified'
        )
        
        st.plotly_chart(fig_compare, use_container_width=True)

def render_backtest_section(metal_data):
    """백테스트"""
    st.subheader("🔬 백테스트 시뮬레이션")
    st.info("💡 금은비율 기반 전략: 비율 > 85면 은 매수, < 65면 금 매수")
    
    if 'gold' not in metal_data or 'silver' not in metal_data:
        st.warning("금과 은 데이터 필요")
        return
    
    # 간단한 백테스트 로직 (이전과 동일)
    st.caption("⚠️ 과거 성과는 미래를 보장하지 않습니다.")

def render_strategy_summary(signals, metal_data):
    """전략 요약"""
    st.subheader("💼 전략 요약")
    
    recommendations = []
    
    for key in ['gold', 'silver', 'copper']:
        if key not in metal_data:
            continue
            
        signal_key = f'{key}_momentum'
        if signal_key in signals:
            sig = signals[signal_key]
            if sig['score'] >= 4:
                recommendations.append({
                    '금속': metal_data[key]['info']['name'],
                    'ETF': metal_data[key]['info']['ticker'],
                    '신호': sig['signal'],
                    '권장': '매수',
                    '근거': sig['description']
                })
            elif sig['score'] <= 2:
                recommendations.append({
                    '금속': metal_data[key]['info']['name'],
                    'ETF': metal_data[key]['info']['ticker'],
                    '신호': sig['signal'],
                    '권장': '매도',
                    '근거': sig['description']
                })
    
    if recommendations:
        df = pd.DataFrame(recommendations)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("현재 명확한 신호 없음")

# ============================================================================
# 메인 함수
# ============================================================================

def main():
    st.markdown('<h1 class="main-header">🥇 귀금속 ETF 트레이딩 신호 대시보드</h1>', unsafe_allow_html=True)
    
    with st.sidebar:
        st.header("⚙️ 설정")
        
        lookback_days = st.select_slider(
            "데이터 기간",
            options=[30, 90, 180, 365, 730],
            value=365
        )
        
        show_futures = st.checkbox("선물 가격 표시", value=True)
        show_ratios = st.checkbox("비율 지표 표시", value=True)
        show_backtest = st.checkbox("백테스트", value=False)
        
        if st.button("🔄 새로고침"):
            st.cache_data.clear()
            st.rerun()
    
    with st.spinner("데이터 로딩..."):
        metal_data = fetch_etf_data(lookback_days)
        supporting_data = fetch_supporting_data()
    
    if not metal_data:
        st.error("데이터 로드 실패")
        return
    
    signals = generate_trading_signals(metal_data, supporting_data)
    
    # 메인 신호
    st.subheader("🚦 통합 신호")
    
    total_score = sum([s['score'] for s in signals.values() if 'score' in s])
    avg_score = total_score / len([s for s in signals.values() if 'score' in s]) if signals else 3
    
    if avg_score >= 4.5:
        signal_text = "🟢🟢 강력 매수"
        sig_class = "signal-strong-buy"
    elif avg_score >= 3.5:
        signal_text = "🟢 매수"
        sig_class = "signal-buy"
    elif avg_score >= 2.5:
        signal_text = "🟡 중립"
        sig_class = "signal-neutral"
    elif avg_score >= 2.0:
        signal_text = "🔴 매도"
        sig_class = "signal-sell"
    else:
        signal_text = "🔴🔴 강력 매도"
        sig_class = "signal-strong-sell"
    
    st.markdown(f'<div class="{sig_class}">{signal_text}<br>점수: {avg_score:.2f}/5.0</div>', unsafe_allow_html=True)
    
    st.divider()
    
    # 개별 금속
    st.subheader("📊 개별 분석")
    cols = st.columns(3)
    
    for idx, (key, data) in enumerate(metal_data.items()):
        with cols[idx]:
            info = data['info']
            signal_key = f'{key}_momentum'
            
            if signal_key in signals:
                sig = signals[signal_key]
                
                if sig['level'] == 'strong_buy':
                    sig_class = "signal-strong-buy"
                elif sig['level'] == 'buy':
                    sig_class = "signal-buy"
                elif sig['level'] in ['sell', 'strong_sell']:
                    sig_class = "signal-sell"
                else:
                    sig_class = "signal-neutral"
                
                st.markdown(f"""
                <div class="{sig_class}">
                    <div style="font-size: 1.3rem;">{info['name']}</div>
                    <div style="font-size: 1.1rem; margin: 0.5rem 0;">{sig['signal']}</div>
                    <div style="font-size: 0.85rem;">{sig['description']}</div>
                </div>
                """, unsafe_allow_html=True)
                
                st.metric(info['ticker'], f"${data['etf_current']:.2f}", f"{sig['day_change']:+.2f}%")
    
    st.divider()
    
    # 비율 지표
    if show_ratios and 'gold_silver_ratio' in signals:
        st.subheader("📐 비율 지표")
        col1, col2 = st.columns(2)
        
        with col1:
            gs = signals['gold_silver_ratio']
            st.markdown(f"""
            <div class="signal-neutral">
                <h4>💰 금/은 비율</h4>
                <div style="font-size: 2rem;">{gs['ratio']:.1f}</div>
                <div>{gs['signal']}</div>
                <div style="font-size: 0.85rem; margin-top: 1rem;">{gs['description']}</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            if 'copper_gold_ratio' in signals:
                cg = signals['copper_gold_ratio']
                st.markdown(f"""
                <div class="signal-neutral">
                    <h4>🌡️ 구리/금 비율</h4>
                    <div style="font-size: 2rem;">{cg['ratio']:.2f}</div>
                    <div>{cg['signal']}</div>
                    <div style="font-size: 0.85rem; margin-top: 1rem;">{cg['description']}</div>
                </div>
                """, unsafe_allow_html=True)
        
        st.divider()
    
    # 거시경제
    if 'macro_environment' in signals and supporting_data:
        st.subheader("🌍 거시경제")
        macro = signals['macro_environment']
        st.info(f"{macro['signal']}: {macro['description']}")
        
        col1, col2, col3, col4 = st.columns(4)
        if 'dxy' in supporting_data:
            with col1:
                st.metric("달러지수", f"{supporting_data['dxy']['current']:.2f}", 
                         f"{supporting_data['dxy']['change_pct']:+.2f}%")
        if 'vix' in supporting_data:
            with col4:
                st.metric("VIX", f"{supporting_data['vix']['current']:.1f}",
                         f"{supporting_data['vix']['change_pct']:+.2f}%")
        
        st.divider()
    
    # 차트
    render_price_charts(metal_data)
    
    if show_backtest:
        render_backtest_section(metal_data)
    
    render_strategy_summary(signals, metal_data)

if __name__ == "__main__":
    main()