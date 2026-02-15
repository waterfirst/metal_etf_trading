"""
국민연금(NPS) SEC 13F 보고서 수집·분석 에이전트

SEC EDGAR에서 국민연금(National Pension Service)이 제출한 13F-HR 보고서를
자동으로 수집하고, 보유 종목·섹터·분기별 변동을 분석합니다.

CIK: 0001608046
"""

import os
import re
import time
import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import pandas as pd

logger = logging.getLogger(__name__)

# SEC EDGAR 상수
NPS_CIK = "0001608046"
SEC_BASE = "https://data.sec.gov"
SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
USER_AGENT = "metal_etf_trading research@example.com"

# 13F XML 네임스페이스
NS_INFO = "http://www.sec.gov/edgar/document/thirteenf/informationtable"
NS_COVER = "http://www.sec.gov/edgar/thirteenffiler"

# CUSIP → 섹터 매핑 (주요 종목)
SECTOR_MAP = {
    # Technology
    "67066G10": "Technology", "594918104": "Technology", "037833100": "Technology",
    "023135106": "Technology", "30303M102": "Technology", "88160R101": "Technology",
    "79466L302": "Technology", "09075V102": "Technology", "02079K107": "Technology",
    "00724F101": "Technology", "035420103": "Technology", "44919P508": "Technology",
    "004336102": "Technology",
    # Financials
    "46625H100": "Financials", "0927804100": "Financials", "78462F103": "Financials",
    "172967424": "Financials", "060505104": "Financials",
    # Healthcare
    "58933Y105": "Healthcare", "002824100": "Healthcare", "718172109": "Healthcare",
    "91324P102": "Healthcare", "478160104": "Healthcare",
    # Consumer
    "931142103": "Consumer", "742718109": "Consumer", "654106103": "Consumer",
    "88579Y101": "Consumer", "617446448": "Consumer",
    # Communication
    "02079K305": "Communication",
    # Energy
    "806857108": "Energy", "20825C104": "Energy", "166764100": "Energy",
    # Industrials
    "369604301": "Industrials", "912456100": "Industrials",
    # Materials
    "462858100": "Materials",
    # ETF
    "46138J101": "ETF", "46090E103": "ETF", "78464A870": "ETF",
    "464287655": "ETF", "464287200": "ETF",
}

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports")


class NPSSecAgent:
    """국민연금 SEC 13F 보고서 수집·분석 에이전트"""

    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = cache_dir or os.path.join(REPORT_DIR, "nps_13f_cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(REPORT_DIR, exist_ok=True)

    # ──────────────────────────────────────────────
    # SEC EDGAR HTTP 헬퍼
    # ──────────────────────────────────────────────

    def _sec_get(self, url: str, max_retries: int = 3) -> bytes:
        """SEC EDGAR에서 데이터를 가져옵니다. Rate limit (10 req/s) 준수."""
        for attempt in range(max_retries):
            try:
                req = Request(url, headers={"User-Agent": USER_AGENT})
                with urlopen(req, timeout=30) as resp:
                    data = resp.read()
                time.sleep(0.15)  # SEC rate limit 준수
                return data
            except (HTTPError, URLError) as e:
                logger.warning(f"SEC 요청 실패 (시도 {attempt+1}/{max_retries}): {url} - {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** (attempt + 1))
                else:
                    raise
        return b""

    # ──────────────────────────────────────────────
    # 13F 파일링 목록 조회
    # ──────────────────────────────────────────────

    def get_filing_list(self, count: int = 8) -> List[Dict]:
        """SEC EDGAR에서 국민연금 13F-HR 파일링 목록을 조회합니다.

        Returns:
            List of dicts with keys: form, filingDate, reportDate, accession, accessionPath
        """
        logger.info("SEC EDGAR에서 국민연금 13F 파일링 목록 조회 중...")
        url = f"{SEC_BASE}/submissions/CIK{NPS_CIK}.json"
        data = json.loads(self._sec_get(url))

        filings = data.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])
        filing_dates = filings.get("filingDate", [])
        report_dates = filings.get("reportDate", [])
        accessions = filings.get("accessionNumber", [])

        result = []
        for i in range(len(forms)):
            if forms[i] == "13F-HR":
                result.append({
                    "form": forms[i],
                    "filingDate": filing_dates[i],
                    "reportDate": report_dates[i],
                    "accession": accessions[i],
                    "accessionPath": accessions[i].replace("-", ""),
                })
                if len(result) >= count:
                    break

        logger.info(f"  총 {len(result)}건의 13F-HR 파일링 확인")
        return result

    # ──────────────────────────────────────────────
    # 13F 정보 테이블 다운로드 및 파싱
    # ──────────────────────────────────────────────

    def _find_info_table_url(self, accession_path: str) -> str:
        """파일링 디렉토리에서 정보 테이블 XML 파일 URL을 찾습니다."""
        dir_url = f"{SEC_ARCHIVES}/{NPS_CIK.lstrip('0')}/{accession_path}/"
        html = self._sec_get(dir_url).decode("utf-8", errors="replace")
        xml_files = re.findall(r'href="([^"]+\.xml)"', html)
        for f in xml_files:
            fname = f.split("/")[-1]
            if fname != "primary_doc.xml":
                return f if f.startswith("http") else f"https://www.sec.gov{f}"
        raise ValueError(f"정보 테이블 XML 파일을 찾을 수 없습니다: {dir_url}")

    def _get_cover_page(self, accession_path: str) -> Dict:
        """13F 커버 페이지(primary_doc.xml)에서 요약 정보를 추출합니다."""
        url = f"{SEC_ARCHIVES}/{NPS_CIK.lstrip('0')}/{accession_path}/primary_doc.xml"
        xml_data = self._sec_get(url)
        root = ET.fromstring(xml_data)

        # 네임스페이스 자동 탐색
        ns = {"ns": NS_COVER}
        summary = {}

        # summaryPage
        for tag in ["tableEntryTotal", "tableValueTotal"]:
            el = root.find(f".//{{{NS_COVER}}}{tag}")
            if el is not None and el.text:
                summary[tag] = int(el.text)

        # reportCalendarOrQuarter
        el = root.find(f".//{{{NS_COVER}}}reportCalendarOrQuarter")
        if el is not None and el.text:
            summary["reportDate"] = el.text

        return summary

    def fetch_13f_holdings(self, filing: Dict) -> pd.DataFrame:
        """13F 정보 테이블 XML을 다운로드하여 DataFrame으로 반환합니다.

        Args:
            filing: get_filing_list()에서 반환된 파일링 정보

        Returns:
            DataFrame with columns: issuer, titleOfClass, cusip, value, shares, shareType,
                                    investmentDiscretion, votingSole, votingShared, votingNone
        """
        report_date = filing["reportDate"]
        cache_path = os.path.join(self.cache_dir, f"holdings_{report_date}.csv")

        # 캐시 확인
        if os.path.exists(cache_path):
            logger.info(f"  캐시에서 로드: {report_date}")
            return pd.read_csv(cache_path)

        accession_path = filing["accessionPath"]
        logger.info(f"  {report_date} 정보 테이블 다운로드 중...")

        info_url = self._find_info_table_url(accession_path)
        xml_data = self._sec_get(info_url)

        # XML 파싱
        root = ET.fromstring(xml_data)
        records = []

        for entry in root.findall(f"{{{NS_INFO}}}infoTable"):
            issuer = entry.findtext(f"{{{NS_INFO}}}nameOfIssuer", "")
            title = entry.findtext(f"{{{NS_INFO}}}titleOfClass", "")
            cusip = entry.findtext(f"{{{NS_INFO}}}cusip", "")
            value = int(entry.findtext(f"{{{NS_INFO}}}value", "0"))
            discretion = entry.findtext(f"{{{NS_INFO}}}investmentDiscretion", "")

            shares_el = entry.find(f"{{{NS_INFO}}}shrsOrPrnAmt")
            shares = 0
            share_type = "SH"
            if shares_el is not None:
                shares = int(shares_el.findtext(f"{{{NS_INFO}}}sshPrnamt", "0"))
                share_type = shares_el.findtext(f"{{{NS_INFO}}}sshPrnamtType", "SH")

            voting_el = entry.find(f"{{{NS_INFO}}}votingAuthority")
            v_sole = v_shared = v_none = 0
            if voting_el is not None:
                v_sole = int(voting_el.findtext(f"{{{NS_INFO}}}Sole", "0"))
                v_shared = int(voting_el.findtext(f"{{{NS_INFO}}}Shared", "0"))
                v_none = int(voting_el.findtext(f"{{{NS_INFO}}}None", "0"))

            records.append({
                "issuer": issuer.strip(),
                "titleOfClass": title.strip(),
                "cusip": cusip.strip(),
                "value": value,       # 단위: 천 달러 ($1,000)
                "shares": shares,
                "shareType": share_type,
                "investmentDiscretion": discretion,
                "votingSole": v_sole,
                "votingShared": v_shared,
                "votingNone": v_none,
            })

        df = pd.DataFrame(records)
        df["value_usd"] = df["value"]  # 이미 달러 단위
        df = df.sort_values("value", ascending=False).reset_index(drop=True)

        # 캐시 저장
        df.to_csv(cache_path, index=False)
        logger.info(f"  {report_date}: {len(df)}개 종목, 총 ${df['value_usd'].sum():,.0f}")

        return df

    # ──────────────────────────────────────────────
    # 분석 기능
    # ──────────────────────────────────────────────

    def _assign_sector(self, cusip: str) -> str:
        """CUSIP 기반 섹터 매핑. 없으면 'Other'."""
        return SECTOR_MAP.get(cusip[:9], SECTOR_MAP.get(cusip[:8], "Other"))

    def analyze_holdings(self, df: pd.DataFrame, top_n: int = 30) -> Dict:
        """단일 분기 보유 종목 분석.

        Returns:
            Dict with keys: summary, top_holdings, sector_breakdown
        """
        total_value = df["value_usd"].sum()
        num_holdings = len(df)

        # 비중 계산
        df = df.copy()
        df["weight"] = df["value_usd"] / total_value

        # 상위 종목
        top = df.head(top_n)[["issuer", "cusip", "value_usd", "shares", "weight"]].copy()
        top["value_billion"] = top["value_usd"] / 1e9
        top_list = top.to_dict("records")

        # 섹터별 집계
        df["sector"] = df["cusip"].apply(self._assign_sector)
        sector_agg = (
            df.groupby("sector")["value_usd"]
            .agg(["sum", "count"])
            .rename(columns={"sum": "total_value", "count": "num_holdings"})
            .sort_values("total_value", ascending=False)
        )
        sector_agg["weight"] = sector_agg["total_value"] / total_value
        sector_breakdown = sector_agg.reset_index().to_dict("records")

        return {
            "summary": {
                "total_value_usd": total_value,
                "total_value_billion": total_value / 1e9,
                "num_holdings": num_holdings,
                "top10_weight": df.head(10)["weight"].sum(),
                "top20_weight": df.head(20)["weight"].sum(),
            },
            "top_holdings": top_list,
            "sector_breakdown": sector_breakdown,
        }

    def compare_quarters(
        self, df_current: pd.DataFrame, df_previous: pd.DataFrame,
        report_current: str, report_previous: str,
    ) -> Dict:
        """두 분기 보유 종목을 비교 분석합니다.

        Returns:
            Dict with keys: new_positions, closed_positions, increased, decreased, summary
        """
        cur = df_current[["issuer", "cusip", "value_usd", "shares"]].copy()
        prev = df_previous[["issuer", "cusip", "value_usd", "shares"]].copy()

        cur_cusips = set(cur["cusip"])
        prev_cusips = set(prev["cusip"])

        # 신규 편입
        new_cusips = cur_cusips - prev_cusips
        new_positions = cur[cur["cusip"].isin(new_cusips)].sort_values(
            "value_usd", ascending=False
        ).head(20).to_dict("records")

        # 완전 매도
        closed_cusips = prev_cusips - cur_cusips
        closed_positions = prev[prev["cusip"].isin(closed_cusips)].sort_values(
            "value_usd", ascending=False
        ).head(20).to_dict("records")

        # 공통 종목 비교
        common_cusips = cur_cusips & prev_cusips
        merged = pd.merge(
            cur[cur["cusip"].isin(common_cusips)],
            prev[prev["cusip"].isin(common_cusips)],
            on="cusip",
            suffixes=("_cur", "_prev"),
        )
        merged["value_change"] = merged["value_usd_cur"] - merged["value_usd_prev"]
        merged["shares_change"] = merged["shares_cur"] - merged["shares_prev"]
        merged["shares_change_pct"] = (
            merged["shares_change"] / merged["shares_prev"].replace(0, 1) * 100
        )

        # 비중 확대 (주식 수 기준)
        increased = (
            merged[merged["shares_change"] > 0]
            .sort_values("value_change", ascending=False)
            .head(20)
        )
        increased_list = []
        for _, row in increased.iterrows():
            increased_list.append({
                "issuer": row["issuer_cur"],
                "cusip": row["cusip"],
                "value_cur": row["value_usd_cur"],
                "value_prev": row["value_usd_prev"],
                "value_change": row["value_change"],
                "shares_cur": row["shares_cur"],
                "shares_prev": row["shares_prev"],
                "shares_change_pct": row["shares_change_pct"],
            })

        # 비중 축소
        decreased = (
            merged[merged["shares_change"] < 0]
            .sort_values("value_change", ascending=True)
            .head(20)
        )
        decreased_list = []
        for _, row in decreased.iterrows():
            decreased_list.append({
                "issuer": row["issuer_cur"],
                "cusip": row["cusip"],
                "value_cur": row["value_usd_cur"],
                "value_prev": row["value_usd_prev"],
                "value_change": row["value_change"],
                "shares_cur": row["shares_cur"],
                "shares_prev": row["shares_prev"],
                "shares_change_pct": row["shares_change_pct"],
            })

        total_cur = df_current["value_usd"].sum()
        total_prev = df_previous["value_usd"].sum()

        return {
            "periods": {
                "current": report_current,
                "previous": report_previous,
            },
            "summary": {
                "total_current": total_cur,
                "total_previous": total_prev,
                "total_change": total_cur - total_prev,
                "total_change_pct": (total_cur - total_prev) / total_prev * 100,
                "num_current": len(df_current),
                "num_previous": len(df_previous),
                "new_positions": len(new_cusips),
                "closed_positions": len(closed_cusips),
            },
            "new_positions": new_positions,
            "closed_positions": closed_positions,
            "increased": increased_list,
            "decreased": decreased_list,
        }

    # ──────────────────────────────────────────────
    # 리포트 생성
    # ──────────────────────────────────────────────

    def generate_report(
        self, analysis: Dict, comparison: Optional[Dict] = None
    ) -> str:
        """분석 결과를 마크다운 리포트로 생성합니다."""
        lines = []
        summary = analysis["summary"]

        lines.append("# 국민연금(NPS) SEC 13F 보유 종목 분석 리포트")
        lines.append("")
        lines.append(f"**분석일:** {datetime.now().strftime('%Y-%m-%d')}")
        lines.append(f"**데이터 출처:** SEC EDGAR (CIK: {NPS_CIK})")
        lines.append("")
        lines.append("---")
        lines.append("")

        # 1. 포트폴리오 요약
        lines.append("## 1. 포트폴리오 요약")
        lines.append("")
        lines.append(f"- **총 운용 규모:** ${summary['total_value_billion']:.2f}B (약 {summary['total_value_billion']:.1f}십억 달러)")
        lines.append(f"- **보유 종목 수:** {summary['num_holdings']}개")
        lines.append(f"- **상위 10종목 비중:** {summary['top10_weight']:.1%}")
        lines.append(f"- **상위 20종목 비중:** {summary['top20_weight']:.1%}")
        lines.append("")

        # 2. 상위 보유 종목
        lines.append("## 2. 상위 보유 종목")
        lines.append("")
        lines.append("| 순위 | 종목명 | CUSIP | 보유가치($B) | 보유주수 | 비중 |")
        lines.append("|------|--------|-------|-------------|---------|------|")
        for i, h in enumerate(analysis["top_holdings"], 1):
            lines.append(
                f"| {i} | {h['issuer']} | {h['cusip']} | "
                f"${h['value_billion']:.3f}B | {h['shares']:,} | "
                f"{h['weight']:.2%} |"
            )
        lines.append("")

        # 3. 섹터별 배분
        lines.append("## 3. 섹터별 배분")
        lines.append("")
        lines.append("| 섹터 | 보유가치($B) | 종목수 | 비중 |")
        lines.append("|------|-------------|--------|------|")
        for s in analysis["sector_breakdown"]:
            lines.append(
                f"| {s['sector']} | ${s['total_value']/1e9:.2f}B | "
                f"{s['num_holdings']} | {s['weight']:.1%} |"
            )
        lines.append("")

        # 4. 분기 비교 (있는 경우)
        if comparison:
            comp_sum = comparison["summary"]
            periods = comparison["periods"]

            lines.append(f"## 4. 분기별 비교 ({periods['previous']} → {periods['current']})")
            lines.append("")
            lines.append(f"- **총 운용 규모 변동:** ${comp_sum['total_previous']/1e9:.2f}B → ${comp_sum['total_current']/1e9:.2f}B ({comp_sum['total_change_pct']:+.1f}%)")
            lines.append(f"- **종목 수 변동:** {comp_sum['num_previous']} → {comp_sum['num_current']}")
            lines.append(f"- **신규 편입:** {comp_sum['new_positions']}종목")
            lines.append(f"- **완전 매도:** {comp_sum['closed_positions']}종목")
            lines.append("")

            # 신규 편입
            if comparison["new_positions"]:
                lines.append("### 4-1. 신규 편입 종목 (Top)")
                lines.append("")
                lines.append("| 종목명 | 보유가치($M) | 보유주수 |")
                lines.append("|--------|-------------|---------|")
                for p in comparison["new_positions"][:15]:
                    lines.append(
                        f"| {p['issuer']} | ${p['value_usd']/1e6:.1f}M | {p['shares']:,} |"
                    )
                lines.append("")

            # 완전 매도
            if comparison["closed_positions"]:
                lines.append("### 4-2. 완전 매도 종목 (Top)")
                lines.append("")
                lines.append("| 종목명 | 이전 보유가치($M) | 이전 보유주수 |")
                lines.append("|--------|-----------------|-------------|")
                for p in comparison["closed_positions"][:15]:
                    lines.append(
                        f"| {p['issuer']} | ${p['value_usd']/1e6:.1f}M | {p['shares']:,} |"
                    )
                lines.append("")

            # 비중 확대
            if comparison["increased"]:
                lines.append("### 4-3. 비중 확대 종목 (Top Buys)")
                lines.append("")
                lines.append("| 종목명 | 이전가치($M) | 현재가치($M) | 주수변동(%) |")
                lines.append("|--------|-------------|-------------|-----------|")
                for p in comparison["increased"][:15]:
                    lines.append(
                        f"| {p['issuer']} | ${p['value_prev']/1e6:.1f}M | "
                        f"${p['value_cur']/1e6:.1f}M | {p['shares_change_pct']:+.1f}% |"
                    )
                lines.append("")

            # 비중 축소
            if comparison["decreased"]:
                lines.append("### 4-4. 비중 축소 종목 (Top Sells)")
                lines.append("")
                lines.append("| 종목명 | 이전가치($M) | 현재가치($M) | 주수변동(%) |")
                lines.append("|--------|-------------|-------------|-----------|")
                for p in comparison["decreased"][:15]:
                    lines.append(
                        f"| {p['issuer']} | ${p['value_prev']/1e6:.1f}M | "
                        f"${p['value_cur']/1e6:.1f}M | {p['shares_change_pct']:+.1f}% |"
                    )
                lines.append("")

        lines.append("---")
        lines.append(f"*본 리포트는 SEC EDGAR 공시 데이터를 기반으로 자동 생성되었습니다.*")
        lines.append(f"*생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

        return "\n".join(lines)

    # ──────────────────────────────────────────────
    # 전체 실행
    # ──────────────────────────────────────────────

    def run(self, quarters: int = 2) -> str:
        """최신 13F 보고서를 수집하고 분석합니다.

        Args:
            quarters: 분석할 분기 수 (최소 1, 비교 분석은 2 이상)

        Returns:
            마크다운 리포트 문자열
        """
        quarters = max(1, min(quarters, 8))
        filings = self.get_filing_list(count=quarters)

        if not filings:
            raise RuntimeError("13F 파일링을 찾을 수 없습니다.")

        # 최신 분기 데이터
        logger.info(f"\n최신 보고서: {filings[0]['reportDate']} (제출일: {filings[0]['filingDate']})")
        df_current = self.fetch_13f_holdings(filings[0])
        analysis = self.analyze_holdings(df_current)

        # 이전 분기와 비교
        comparison = None
        if quarters >= 2 and len(filings) >= 2:
            logger.info(f"이전 보고서: {filings[1]['reportDate']} (제출일: {filings[1]['filingDate']})")
            df_previous = self.fetch_13f_holdings(filings[1])
            comparison = self.compare_quarters(
                df_current, df_previous,
                filings[0]["reportDate"], filings[1]["reportDate"],
            )

        # 리포트 생성
        report = self.generate_report(analysis, comparison)

        # 파일 저장
        report_date = filings[0]["reportDate"]
        filename = f"nps_13f_report_{report_date}.md"
        filepath = os.path.join(REPORT_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)
        logger.info(f"\n리포트 저장: {filepath}")

        # JSON 데이터도 저장
        json_data = {
            "report_date": report_date,
            "generated_at": datetime.now().isoformat(),
            "analysis": self._sanitize(analysis),
        }
        if comparison:
            json_data["comparison"] = self._sanitize(comparison)

        json_path = os.path.join(REPORT_DIR, f"nps_13f_data_{report_date}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"JSON 저장: {json_path}")

        return report

    def _sanitize(self, obj):
        """JSON 직렬화를 위한 타입 변환."""
        if isinstance(obj, dict):
            return {k: self._sanitize(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._sanitize(v) for v in obj]
        elif isinstance(obj, float):
            if obj != obj:
                return None
            return obj
        elif isinstance(obj, (int, str, bool, type(None))):
            return obj
        else:
            return str(obj)
