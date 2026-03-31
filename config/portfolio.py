"""
포트폴리오 설정 - 연금 계좌 보유 종목 정보
"""

# 한국 ETF 종목코드 매핑 (종목명 → Yahoo Finance 티커)
KOREAN_ETF_TICKERS = {
    "KODEX 200": "069500.KS",
    "KODEX 증권": "102110.KS",
    "KODEX 미국S&P500": "379800.KS",
    "KODEX 미국나스닥100": "379810.KS",
    "ACE KRX금현물": "411060.KS",
    "ACE 구글밸류체인액티브": "456600.KS",
    "KODEX 미국AI전력핵심인프라": "486500.KS",
    "TIGER 반도체TOP10": "091230.KS",
    "PLUS K방산": "461500.KS",
    "SOL 조선TOP3플러스": "466920.KS",
    "PLUS 고배당주": "161510.KS",
    "KODEX 200미국채혼합": "284430.KS",
    "TIGER 코리아휴머노이드로봇산업": "490050.KS",
    "TIGER TDF2045": "327080.KS",
    "TIGER 코리아원자력": "471920.KS",
    "KoAct 코스닥액티브": "467810.KS",
}

# 섹터 분류
ETF_SECTORS = {
    "KODEX 200": "국내주식_대형",
    "KODEX 증권": "국내주식_섹터",
    "KODEX 미국S&P500": "해외주식_미국",
    "KODEX 미국나스닥100": "해외주식_미국",
    "ACE KRX금현물": "원자재_금",
    "ACE 구글밸류체인액티브": "해외주식_테마",
    "KODEX 미국AI전력핵심인프라": "해외주식_테마",
    "TIGER 반도체TOP10": "국내주식_섹터",
    "PLUS K방산": "국내주식_섹터",
    "SOL 조선TOP3플러스": "국내주식_섹터",
    "PLUS 고배당주": "국내주식_배당",
    "KODEX 200미국채혼합": "혼합_채권",
    "TIGER 코리아휴머노이드로봇산업": "국내주식_테마",
    "TIGER TDF2045": "혼합_TDF",
    "TIGER 코리아원자력": "국내주식_테마",
    "KoAct 코스닥액티브": "국내주식_대형",
}

# 자산유형 대분류
ASSET_CLASSES = {
    "국내주식_대형": "국내주식",
    "국내주식_섹터": "국내주식",
    "국내주식_배당": "국내주식",
    "국내주식_테마": "국내주식",
    "해외주식_미국": "해외주식",
    "해외주식_테마": "해외주식",
    "원자재_금": "원자재",
    "혼합_채권": "채권혼합",
    "혼합_TDF": "TDF",
}

# ============================================================
# 계좌 1: 연금저축 CMA (7156074820-15)
# 2026-03-30 매도 반영: S&P500 500주, 나스닥 50주 → MMF 전환
# ============================================================
PENSION_SAVINGS_ACCOUNT = {
    "account_name": "연금저축 CMA",
    "account_number": "7156074820-15",
    "holdings": {
        "KODEX 200": {"shares": 71, "avg_value": 5_562_140},
        "KODEX 증권": {"shares": 1_686, "avg_value": 39_283_800},
        "KODEX 미국S&P500": {"shares": 500, "avg_value": 11_472_500},
        "KODEX 미국나스닥100": {"shares": 959, "avg_value": 23_299_405},
        "ACE KRX금현물": {"shares": 588, "avg_value": 19_615_680},
        "ACE 구글밸류체인액티브": {"shares": 784, "avg_value": 13_339_760},
        "KODEX 미국AI전력핵심인프라": {"shares": 615, "avg_value": 11_325_225},
        "MMF": {"shares": 0, "avg_value": 12_687_250},  # S&P 500주 + 나스닥 50주 매도 대금
    },
}

# ============================================================
# 계좌 2: 퇴직연금 DC (62636131-55)
# 2026-03-30 매도 반영: S&P500 500주 → MMF 전환
# ============================================================
RETIREMENT_DC_ACCOUNT = {
    "account_name": "퇴직연금 DC",
    "account_number": "62636131-55",
    "holdings": {
        "KODEX 증권": {"shares": 1_909, "avg_value": 44_479_700},
        "KODEX 200": {"shares": 383, "avg_value": 30_004_220},
        "TIGER 반도체TOP10": {"shares": 1_017, "avg_value": 29_620_125},
        "PLUS K방산": {"shares": 438, "avg_value": 28_695_570},
        "SOL 조선TOP3플러스": {"shares": 538, "avg_value": 19_061_340},
        "PLUS 고배당주": {"shares": 313, "avg_value": 8_036_275},
        "ACE KRX금현물": {"shares": 816, "avg_value": 27_221_760},
        "KODEX 미국S&P500": {"shares": 937, "avg_value": 21_499_991},
        "KODEX 200미국채혼합": {"shares": 3_248, "avg_value": 61_403_440},
        "TIGER 코리아휴머노이드로봇산업": {"shares": 371, "avg_value": 5_182_870},
        "KODEX 미국나스닥100": {"shares": 1_122, "avg_value": 27_258_990},
        "TIGER TDF2045": {"shares": 2_320, "avg_value": 26_993_200},
        "MMF": {"shares": 0, "avg_value": 11_471_974},  # S&P 500주 매도 대금
    },
}

ALL_ACCOUNTS = [PENSION_SAVINGS_ACCOUNT, RETIREMENT_DC_ACCOUNT]

# ============================================================
# 퇴직연금 DC 적립식 자동매수 설정 (2026-03-31 확인)
# 예약 종료일: 2026.09.30 / 주간 합계 160만원
# ============================================================
DC_DCA_SCHEDULE = {
    "account": "62636131-55",
    "total_weekly": 1_600_000,
    "end_date": "2026-09-30",
    "items": [
        {"name": "TIGER 반도체TOP10", "amount": 500_000, "day": "목", "time": "15:00", "type": "시장가"},
        {"name": "ACE KRX금현물", "amount": 100_000, "day": "화", "time": "15:00", "type": "시장가"},
        {"name": "TIGER 코리아원자력", "amount": 500_000, "day": "화", "time": "15:00", "type": "시장가"},
        {"name": "KoAct 코스닥액티브", "amount": 200_000, "day": "화", "time": "15:00", "type": "시장가"},
        {"name": "KODEX 증권", "amount": 300_000, "day": "화", "time": "15:00", "type": "시장가"},
    ],
}

# 경제지표 티커 (Yahoo Finance)
ECONOMIC_INDICATORS = {
    "USD/KRW": "KRW=X",
    "미국 10년 국채": "^TNX",
    "미국 2년 국채": "^IRX",
    "S&P 500": "^GSPC",
    "NASDAQ": "^IXIC",
    "KOSPI": "^KS11",
    "KOSDAQ": "^KQ11",
    "VIX": "^VIX",
    "달러인덱스": "DX-Y.NYB",
    "금 선물": "GC=F",
    "은 선물": "SI=F",
    "WTI 원유": "CL=F",
    "비트코인": "BTC-USD",
}

# 리밸런싱 제약조건 (연금 규정)
REBALANCING_CONSTRAINTS = {
    "max_single_etf_weight": 0.30,       # 단일 종목 최대 비중 30%
    "max_sector_weight": 0.40,            # 단일 섹터 최대 비중 40%
    "min_domestic_equity": 0.00,          # 국내주식 최소 비중
    "max_foreign_equity_dc": 0.70,        # DC형 해외주식 최대 70%
    "min_safe_asset_dc": 0.30,            # DC형 안전자산 최소 30% (법적 의무 아님, 권고)
    "transaction_cost_rate": 0.001,       # 거래비용율 0.1%
}

# 뉴스 소스
NEWS_SOURCES = {
    "연합뉴스_경제": "https://www.yna.co.kr/economy/all",
    "한경_증권": "https://www.hankyung.com/finance/stock",
    "매경_증권": "https://stock.mk.co.kr",
}

# RSS 피드
RSS_FEEDS = {
    "investing_com_kr": "https://kr.investing.com/rss/news.rss",
    "google_news_kr_economy": "https://news.google.com/rss/search?q=한국+경제+증시&hl=ko&gl=KR&ceid=KR:ko",
    "google_news_us_market": "https://news.google.com/rss/search?q=US+stock+market+ETF&hl=en&gl=US&ceid=US:en",
    "google_news_kr_etf": "https://news.google.com/rss/search?q=한국+ETF+연금&hl=ko&gl=KR&ceid=KR:ko",
}
