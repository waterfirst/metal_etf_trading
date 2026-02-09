"""
뉴스 크롤링 에이전트
- Google News RSS 피드를 통한 경제/증시 뉴스 수집
- 키워드 기반 뉴스 필터링
- 뉴스 감성 분석 (키워드 기반)
"""

import xml.etree.ElementTree as ET
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from html.parser import HTMLParser
import logging
import re
import ssl
import json

logger = logging.getLogger(__name__)

# SSL 인증서 검증 비활성화 (일부 뉴스 사이트 대응)
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE


class HTMLStripper(HTMLParser):
    """HTML 태그 제거"""
    def __init__(self):
        super().__init__()
        self.result = []

    def handle_data(self, d):
        self.result.append(d)

    def get_text(self):
        return "".join(self.result)


def strip_html(html_text: str) -> str:
    """HTML에서 텍스트만 추출"""
    stripper = HTMLStripper()
    stripper.feed(html_text)
    return stripper.get_text()


@dataclass
class NewsArticle:
    """뉴스 기사"""
    title: str
    source: str
    published: str
    link: str
    summary: str = ""
    sentiment: str = "중립"  # "긍정", "부정", "중립"
    relevance_score: float = 0.0
    keywords: List[str] = field(default_factory=list)


# 감성 분석용 키워드 사전
POSITIVE_KEYWORDS = [
    "상승", "급등", "반등", "호재", "돌파", "신고가", "강세", "랠리",
    "회복", "개선", "호실적", "성장", "확대", "증가", "최고",
    "bullish", "rally", "surge", "growth", "record", "boost",
    "outperform", "upgrade", "beat", "strong",
]

NEGATIVE_KEYWORDS = [
    "하락", "급락", "폭락", "악재", "위기", "공포", "약세",
    "침체", "둔화", "감소", "축소", "손실", "적자", "리스크",
    "bearish", "crash", "decline", "recession", "fear", "risk",
    "downgrade", "miss", "weak", "slump", "sell-off",
]

# 포트폴리오 관련 키워드
PORTFOLIO_KEYWORDS = {
    "반도체": ["반도체", "semiconductor", "AI칩", "HBM", "삼성전자", "SK하이닉스"],
    "방산": ["방산", "방위", "defense", "군사", "무기", "한화에어로"],
    "조선": ["조선", "shipbuilding", "LNG선", "HD현대", "한화오션"],
    "증권": ["증권", "금융", "증시", "securities", "broker"],
    "금": ["금값", "금가격", "gold", "귀금속", "안전자산"],
    "미국시장": ["S&P", "나스닥", "nasdaq", "월가", "wall street", "연준", "fed"],
    "AI": ["인공지능", "AI", "artificial intelligence", "챗봇", "GPU", "엔비디아"],
    "로봇": ["로봇", "robot", "humanoid", "자동화"],
    "배당": ["배당", "dividend", "인컴", "분배금"],
    "ETF": ["ETF", "인덱스", "패시브", "리밸런싱"],
    "환율": ["환율", "달러", "원화", "USD", "KRW"],
    "금리": ["금리", "기준금리", "interest rate", "국채", "bond"],
}


class NewsAgent:
    """뉴스 수집 및 분석 에이전트"""

    def __init__(self, max_articles_per_feed: int = 20):
        self.max_articles = max_articles_per_feed

    def collect_all_news(self) -> Dict[str, List[Dict]]:
        """모든 소스에서 뉴스 수집"""
        from config.portfolio import RSS_FEEDS

        all_news = {
            "한국경제": [],
            "미국시장": [],
            "ETF/연금": [],
        }

        # Google News RSS 피드 수집
        feed_category_map = {
            "google_news_kr_economy": "한국경제",
            "google_news_us_market": "미국시장",
            "google_news_kr_etf": "ETF/연금",
            "investing_com_kr": "한국경제",
        }

        for feed_name, url in RSS_FEEDS.items():
            category = feed_category_map.get(feed_name, "한국경제")
            articles = self._fetch_rss_feed(url, feed_name)
            for article in articles:
                all_news[category].append(self._article_to_dict(article))

        # 추가 키워드 검색
        extra_queries = [
            ("한국 증시 전망 이번주", "한국경제"),
            ("ETF 리밸런싱 전략", "ETF/연금"),
            ("미국 경제지표 연준", "미국시장"),
        ]

        for query, category in extra_queries:
            articles = self._search_google_news(query)
            for article in articles:
                all_news[category].append(self._article_to_dict(article))

        # 중복 제거 및 정렬
        for category in all_news:
            seen_titles = set()
            unique = []
            for article in all_news[category]:
                if article["제목"] not in seen_titles:
                    seen_titles.add(article["제목"])
                    unique.append(article)
            all_news[category] = sorted(unique, key=lambda x: x["관련도"], reverse=True)

        return all_news

    def analyze_sentiment_summary(self, all_news: Dict[str, List[Dict]]) -> Dict:
        """뉴스 감성 종합 분석"""
        total_positive = 0
        total_negative = 0
        total_neutral = 0
        category_sentiment = {}

        for category, articles in all_news.items():
            pos = sum(1 for a in articles if a["감성"] == "긍정")
            neg = sum(1 for a in articles if a["감성"] == "부정")
            neu = sum(1 for a in articles if a["감성"] == "중립")

            total_positive += pos
            total_negative += neg
            total_neutral += neu

            total = pos + neg + neu
            if total > 0:
                category_sentiment[category] = {
                    "긍정비율": round(pos / total, 2),
                    "부정비율": round(neg / total, 2),
                    "기사수": total,
                    "감성": "긍정" if pos > neg else ("부정" if neg > pos else "중립"),
                }

        total = total_positive + total_negative + total_neutral
        overall = "중립"
        if total > 0:
            if total_positive > total_negative * 1.5:
                overall = "긍정"
            elif total_negative > total_positive * 1.5:
                overall = "부정"

        # 섹터별 관련 뉴스 요약
        sector_news = self._extract_sector_relevant_news(all_news)

        return {
            "종합감성": overall,
            "긍정기사수": total_positive,
            "부정기사수": total_negative,
            "중립기사수": total_neutral,
            "카테고리별": category_sentiment,
            "섹터관련뉴스": sector_news,
        }

    def get_top_headlines(self, all_news: Dict[str, List[Dict]], n: int = 10) -> List[Dict]:
        """주요 헤드라인 추출"""
        all_articles = []
        for articles in all_news.values():
            all_articles.extend(articles)

        # 관련도 + 감성 강도로 정렬
        all_articles.sort(key=lambda x: x["관련도"], reverse=True)
        return all_articles[:n]

    def _fetch_rss_feed(self, url: str, feed_name: str) -> List[NewsArticle]:
        """RSS 피드 파싱"""
        articles = []
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; InvestmentBot/1.0)"
            })
            with urllib.request.urlopen(req, timeout=10, context=ssl_context) as response:
                content = response.read().decode("utf-8", errors="ignore")

            root = ET.fromstring(content)

            # RSS 2.0 형식
            items = root.findall(".//item")
            for item in items[:self.max_articles]:
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                pub_date = item.findtext("pubDate", "")
                description = strip_html(item.findtext("description", ""))
                source_elem = item.find("source")
                source = source_elem.text if source_elem is not None else feed_name

                article = NewsArticle(
                    title=title.strip(),
                    source=source,
                    published=pub_date,
                    link=link,
                    summary=description[:200],
                )
                self._analyze_article(article)
                articles.append(article)

            logger.info(f"RSS {feed_name}: {len(articles)}건 수집")
        except Exception as e:
            logger.warning(f"RSS {feed_name} 수집 실패: {e}")

        return articles

    def _search_google_news(self, query: str) -> List[NewsArticle]:
        """Google News RSS 검색"""
        encoded_query = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"
        return self._fetch_rss_feed(url, f"google_search:{query}")

    def _analyze_article(self, article: NewsArticle):
        """기사 감성 및 관련도 분석"""
        text = (article.title + " " + article.summary).lower()

        # 감성 분석
        pos_count = sum(1 for kw in POSITIVE_KEYWORDS if kw.lower() in text)
        neg_count = sum(1 for kw in NEGATIVE_KEYWORDS if kw.lower() in text)

        if pos_count > neg_count:
            article.sentiment = "긍정"
        elif neg_count > pos_count:
            article.sentiment = "부정"
        else:
            article.sentiment = "중립"

        # 포트폴리오 관련도 분석
        matched_keywords = []
        relevance = 0
        for sector, keywords in PORTFOLIO_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in text:
                    matched_keywords.append(sector)
                    relevance += 1
                    break

        article.keywords = list(set(matched_keywords))
        article.relevance_score = min(1.0, relevance / 5)

    def _extract_sector_relevant_news(self, all_news: Dict[str, List[Dict]]) -> Dict[str, List[str]]:
        """섹터별 관련 뉴스 추출"""
        sector_news = {}
        all_articles = []
        for articles in all_news.values():
            all_articles.extend(articles)

        for sector in PORTFOLIO_KEYWORDS:
            relevant = [
                a["제목"] for a in all_articles
                if sector in a.get("키워드", [])
            ]
            if relevant:
                sector_news[sector] = relevant[:5]

        return sector_news

    def _article_to_dict(self, article: NewsArticle) -> Dict:
        """NewsArticle을 딕셔너리로 변환"""
        return {
            "제목": article.title,
            "출처": article.source,
            "발행일": article.published,
            "링크": article.link,
            "요약": article.summary,
            "감성": article.sentiment,
            "관련도": article.relevance_score,
            "키워드": article.keywords,
        }
