"""
국민연금(NPS) SEC 13F 보고서 수집·분석 실행 스크립트

사용법:
    python run_nps_report.py                  # 최신 2분기 비교 분석
    python run_nps_report.py --quarters 4     # 최신 4분기 비교 분석
    python run_nps_report.py --list           # 사용 가능한 13F 파일링 목록 출력
"""

import sys
import os
import argparse
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger()


def main():
    parser = argparse.ArgumentParser(
        description="국민연금(NPS) SEC 13F 보고서 분석"
    )
    parser.add_argument(
        "--quarters", "-q", type=int, default=2,
        help="분석할 분기 수 (기본: 2, 최신+직전 비교)",
    )
    parser.add_argument(
        "--list", "-l", action="store_true",
        help="사용 가능한 13F 파일링 목록만 출력",
    )
    parser.add_argument(
        "--top", "-t", type=int, default=30,
        help="상위 보유 종목 표시 개수 (기본: 30)",
    )
    args = parser.parse_args()

    from agents.nps_sec_agent import NPSSecAgent

    agent = NPSSecAgent()

    if args.list:
        logger.info("=" * 60)
        logger.info("국민연금(NPS) SEC 13F 파일링 목록")
        logger.info("=" * 60)
        filings = agent.get_filing_list(count=20)
        for i, f in enumerate(filings, 1):
            logger.info(
                f"  [{i:2d}] 보고 기준일: {f['reportDate']}  "
                f"제출일: {f['filingDate']}  "
                f"Accession: {f['accession']}"
            )
        return

    logger.info("=" * 60)
    logger.info("국민연금(NPS) SEC 13F 보고서 수집·분석 시작")
    logger.info(f"  분석 분기 수: {args.quarters}")
    logger.info("=" * 60)

    report = agent.run(quarters=args.quarters)

    logger.info("")
    logger.info("=" * 60)
    logger.info("분석 완료!")
    logger.info("=" * 60)

    # 리포트 미리보기 출력
    print("\n" + "=" * 60)
    print("리포트 미리보기:")
    print("=" * 60)
    # 상위 80줄만 출력
    for line in report.split("\n")[:80]:
        print(line)
    print("...")
    print(f"\n전체 리포트는 reports/ 디렉토리에 저장되었습니다.")


if __name__ == "__main__":
    main()
