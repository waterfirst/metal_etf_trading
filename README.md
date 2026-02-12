# 귀금속 ETF 트레이딩 + 연금 포트폴리오 투자 분석 에이전트

금(Gold), 은(Silver), 구리(Copper) ETF 트레이딩 대시보드와 한국 연금 포트폴리오(연금저축/퇴직연금 DC) 투자 분석 에이전트를 포함합니다.

![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Streamlit](https://img.shields.io/badge/streamlit-1.32.0+-red.svg)

## 프로젝트 구조

```
metal_etf_trading/
├── metal_etf_trading.py          # 귀금속 ETF 트레이딩 대시보드 (기존)
├── investment_agent.py           # 연금 투자 분석 에이전트 (메인)
├── dashboard.py                  # 연금 포트폴리오 대시보드 (Streamlit)
├── config/
│   └── portfolio.py              # 포트폴리오 설정 (보유종목, 경제지표, 제약조건)
├── agents/
│   ├── market_data_agent.py      # 시장 데이터 수집 에이전트
│   ├── technical_analysis_agent.py  # 기술적 분석 에이전트
│   ├── economic_indicator_agent.py  # 경제지표 분석 에이전트
│   ├── news_agent.py             # 뉴스 크롤링/감성 분석 에이전트
│   ├── rebalancing_agent.py      # 리밸런싱 추천 에이전트
│   └── report_agent.py           # 리포트 생성 에이전트
├── reports/                      # 생성된 주간 리포트 저장
└── requirements.txt
```

## 연금 투자 분석 에이전트

### 주요 기능

1. **시장 데이터 수집** - Yahoo Finance를 통한 한국 ETF 가격/경제지표 실시간 수집
2. **기술적 분석** - RSI, MACD, 볼린저밴드, 이동평균선, 스토캐스틱, 거래량 분석
3. **경제지표 분석** - USD/KRW, 미국 국채금리, VIX, 달러인덱스, KOSPI/S&P500
4. **뉴스 크롤링** - Google News RSS 기반 경제/증시 뉴스 수집 + 감성 분석
5. **리밸런싱 추천** - 기술적/거시경제/뉴스 분석을 종합한 비중 조정 추천
6. **주간 리포트** - 매주 일요일 자동 분석 리포트 생성 (마크다운 + JSON)

### 보유 종목 (2개 계좌)

**연금저축 CMA:** KODEX 200, KODEX 증권, KODEX 미국S&P500, KODEX 미국나스닥100, ACE KRX금현물, ACE 구글밸류체인액티브, KODEX 미국AI전력핵심인프라

**퇴직연금 DC:** KODEX 증권, KODEX 200, TIGER 반도체TOP10, PLUS K방산, SOL 조선TOP3플러스, PLUS 고배당주, ACE KRX금현물, KODEX 미국S&P500, KODEX 200미국채혼합, TIGER 코리아휴머노이드로봇산업, KODEX 미국나스닥100, TIGER TDF2045

### 사용법

```bash
# 의존성 설치
pip install -r requirements.txt

# 주간 분석 리포트 생성 (전체 분석)
python investment_agent.py

# 빠른 분석 (뉴스 크롤링 제외)
python investment_agent.py --quick

# 매주 일요일 09:00 자동 실행
python investment_agent.py --schedule

# 분석 기간 지정 (기본 365일)
python investment_agent.py --lookback 180

# 연금 포트폴리오 대시보드
streamlit run dashboard.py

# 귀금속 ETF 트레이딩 대시보드 (기존)
streamlit run metal_etf_trading.py
```

### 분석 파이프라인

```
[시장 데이터 수집] → [포트폴리오 평가] → [기술적 분석] → [경제지표 분석]
                                                              ↓
[리포트 생성] ← [리밸런싱 추천] ← [뉴스 감성 분석] ←──────────┘
```

### 리포트 내용

매주 생성되는 리포트에는 다음이 포함됩니다:
- 포트폴리오 현황 (평가액, 비중, 섹터 배분)
- 시장 환경 분석 (Risk-On/Off 판단)
- 종목별 기술적 분석 시그널 (5단계)
- 뉴스 감성 종합 분석
- 포트폴리오 성과 지표 (샤프비율, MDD 등)
- 리밸런싱 매수/매도 추천 (금액, 사유 포함)
- 종합 의견 및 핵심 추천사항

### 설정 변경

`config/portfolio.py`에서 보유 종목, 수량, 경제지표, 리밸런싱 제약조건 등을 수정할 수 있습니다.

## 귀금속 ETF 트레이딩 대시보드 (기존)

금/은/구리 ETF의 매수/매도 타이밍을 실시간으로 분석하는 대시보드입니다.
- 5단계 통합 트레이딩 신호
- 금/은 비율, 구리/금 비율 분석
- 거시경제 환경 분석
- 백테스트 시뮬레이션
