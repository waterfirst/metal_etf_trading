"""
텔레그램 봇을 통한 모닝 브리핑 발송
- 마크다운 리포트를 텔레그램으로 발송
- 차트 이미지 첨부
- chat_id 자동 탐지

사용법:
    python telegram_sender.py                    # 모닝 브리핑 생성 + 텔레그램 발송
    python telegram_sender.py --find-chat-id     # chat_id 확인
    python telegram_sender.py --test             # 테스트 메시지 발송
"""

import os
import sys
import json
import argparse
import logging
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime
from typing import Optional, List
from glob import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

REPORT_DIR = os.path.join(os.path.dirname(__file__), "reports")
CHART_DIR = os.path.join(REPORT_DIR, "charts")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TelegramSender")

# 환경변수 또는 직접 설정
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "7974097561:AAHqJj2bpHHeDlHICCRcjddzSDQKuJPOv4w")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
MAX_MESSAGE_LENGTH = 4096  # 텔레그램 메시지 최대 길이


class TelegramBot:
    """텔레그램 봇 메시지 발송"""

    def __init__(self, token: str = TELEGRAM_BOT_TOKEN, chat_id: str = TELEGRAM_CHAT_ID):
        self.token = token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{token}"

    def find_chat_id(self) -> Optional[str]:
        """봇에 메시지를 보낸 사용자의 chat_id 자동 탐지"""
        url = f"{self.api_url}/getUpdates"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if data.get("ok") and data.get("result"):
                for update in data["result"]:
                    msg = update.get("message", {})
                    chat = msg.get("chat", {})
                    chat_id = str(chat.get("id", ""))
                    username = chat.get("username", "")
                    first_name = chat.get("first_name", "")
                    if chat_id:
                        logger.info(f"Chat ID 발견: {chat_id} (사용자: {first_name} @{username})")
                        return chat_id

            logger.warning("Chat ID를 찾을 수 없습니다. 봇에 /start 메시지를 보내주세요.")
            return None
        except Exception as e:
            logger.error(f"getUpdates 실패: {e}")
            return None

    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """텍스트 메시지 발송"""
        if not self.chat_id:
            self.chat_id = self.find_chat_id()
            if not self.chat_id:
                logger.error("chat_id가 없습니다. --find-chat-id를 먼저 실행하세요.")
                return False

        # 텔레그램은 4096자 제한 → 분할 발송
        chunks = self._split_message(text)

        for i, chunk in enumerate(chunks):
            success = self._send_text(chunk, parse_mode)
            if not success:
                # Markdown 실패 시 plain text로 재시도
                logger.warning(f"Markdown 발송 실패, plain text로 재시도 (파트 {i+1})")
                self._send_text(chunk, parse_mode=None)

        return True

    def send_photo(self, photo_path: str, caption: str = "") -> bool:
        """이미지 발송"""
        if not self.chat_id:
            return False

        url = f"{self.api_url}/sendPhoto"

        try:
            import mimetypes
            boundary = "----FormBoundary" + datetime.now().strftime("%Y%m%d%H%M%S")

            body = b""
            # chat_id
            body += f"--{boundary}\r\n".encode()
            body += f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{self.chat_id}\r\n'.encode()
            # caption
            if caption:
                body += f"--{boundary}\r\n".encode()
                body += f'Content-Disposition: form-data; name="caption"\r\n\r\n{caption[:1024]}\r\n'.encode()
            # photo
            filename = os.path.basename(photo_path)
            body += f"--{boundary}\r\n".encode()
            body += f'Content-Disposition: form-data; name="photo"; filename="{filename}"\r\n'.encode()
            body += f"Content-Type: image/png\r\n\r\n".encode()
            with open(photo_path, "rb") as f:
                body += f.read()
            body += f"\r\n--{boundary}--\r\n".encode()

            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if result.get("ok"):
                    logger.info(f"이미지 발송 완료: {filename}")
                    return True
                else:
                    logger.error(f"이미지 발송 실패: {result}")
                    return False
        except Exception as e:
            logger.error(f"이미지 발송 실패 ({photo_path}): {e}")
            return False

    def _send_text(self, text: str, parse_mode: Optional[str] = "Markdown") -> bool:
        """단일 텍스트 메시지 발송"""
        url = f"{self.api_url}/sendMessage"
        params = {
            "chat_id": self.chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            params["parse_mode"] = parse_mode

        try:
            data = urllib.parse.urlencode(params).encode("utf-8")
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("ok", False)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            logger.error(f"메시지 발송 실패: {e.code} - {body[:200]}")
            return False
        except Exception as e:
            logger.error(f"메시지 발송 실패: {e}")
            return False

    def _split_message(self, text: str) -> List[str]:
        """긴 메시지를 텔레그램 제한에 맞게 분할"""
        if len(text) <= MAX_MESSAGE_LENGTH:
            return [text]

        chunks = []
        lines = text.split("\n")
        current_chunk = ""

        for line in lines:
            # 섹션 구분자(##)에서 분할 우선
            if len(current_chunk) + len(line) + 1 > MAX_MESSAGE_LENGTH - 100:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = line + "\n"
            else:
                current_chunk += line + "\n"

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks


def format_report_for_telegram(report_md: str) -> str:
    """마크다운 리포트를 텔레그램 형식으로 변환"""
    text = report_md

    # 텔레그램 Markdown은 제한적이므로 일부 변환
    # ## 헤더 → 굵은 텍스트
    import re
    text = re.sub(r'^#{1,3}\s+(.+)$', r'*\1*', text, flags=re.MULTILINE)

    # 테이블은 텔레그램에서 지원하지 않으므로 간소화
    # 복잡한 테이블을 유지하면 깨지므로 코드블록으로 감싸기
    lines = text.split("\n")
    result_lines = []
    in_table = False

    for line in lines:
        if "|" in line and "---" not in line:
            if not in_table:
                result_lines.append("```")
                in_table = True
            # 테이블 셀 정리
            cells = [c.strip() for c in line.split("|") if c.strip()]
            result_lines.append("  ".join(cells))
        else:
            if in_table:
                result_lines.append("```")
                in_table = False
            if "---" in line and "|" in line:
                continue  # 테이블 구분선 제거
            result_lines.append(line)

    if in_table:
        result_lines.append("```")

    return "\n".join(result_lines)


def run_and_send(quick: bool = False):
    """모닝 브리핑 생성 + 텔레그램 발송"""
    from morning_briefing import MorningBriefingAgent

    bot = TelegramBot()

    # chat_id 확인
    if not bot.chat_id:
        bot.chat_id = bot.find_chat_id()
        if not bot.chat_id:
            logger.error("텔레그램 chat_id를 찾을 수 없습니다!")
            logger.error("1. t.me/Shinbong_bot 에 /start 메시지를 보내세요")
            logger.error("2. python telegram_sender.py --find-chat-id 를 실행하세요")
            return False

    # 모닝 브리핑 생성
    logger.info("모닝 브리핑 생성 중...")
    agent = MorningBriefingAgent()
    report = agent.run()

    # 텔레그램 발송
    logger.info("텔레그램 발송 중...")

    # 1) 텍스트 리포트 발송
    telegram_text = format_report_for_telegram(report)
    bot.send_message(telegram_text)

    # 2) 차트 이미지 발송
    today = datetime.now().strftime("%Y-%m-%d")
    chart_files = [
        (f"morning_01_us_market_{today}.png", "미국 시장 전일 등락률"),
        (f"morning_02_etf_prediction_{today}.png", "ETF 오늘 예측 등락률"),
        (f"morning_03_kospi_factors_{today}.png", "KOSPI 예측 영향 요인"),
        (f"morning_04_us_sectors_{today}.png", "미국 섹터별 등락률"),
    ]

    for filename, caption in chart_files:
        filepath = os.path.join(CHART_DIR, filename)
        if os.path.exists(filepath):
            bot.send_photo(filepath, caption)
        else:
            logger.warning(f"차트 파일 없음: {filename}")

    logger.info("텔레그램 발송 완료!")
    return True


def main():
    parser = argparse.ArgumentParser(description="모닝 브리핑 텔레그램 발송")
    parser.add_argument("--find-chat-id", action="store_true", help="chat_id 자동 탐지")
    parser.add_argument("--test", action="store_true", help="테스트 메시지 발송")
    parser.add_argument("--send-latest", action="store_true", help="가장 최근 리포트 발송 (새로 생성하지 않음)")
    args = parser.parse_args()

    if args.find_chat_id:
        bot = TelegramBot()
        chat_id = bot.find_chat_id()
        if chat_id:
            print(f"\n✅ Chat ID: {chat_id}")
            print(f"   환경변수로 설정: export TELEGRAM_CHAT_ID={chat_id}")
        else:
            print("\n❌ Chat ID를 찾을 수 없습니다.")
            print("   1. 텔레그램에서 @Shinbong_bot 을 검색하세요")
            print("   2. /start 메시지를 보내세요")
            print("   3. 다시 이 명령을 실행하세요")
        return

    if args.test:
        bot = TelegramBot()
        if not bot.chat_id:
            bot.chat_id = bot.find_chat_id()
        if bot.chat_id:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            bot.send_message(f"🤖 *테스트 메시지*\n\n모닝 브리핑 봇이 정상 작동합니다.\n시각: {now}")
            print("✅ 테스트 메시지 발송 완료!")
        else:
            print("❌ chat_id를 찾을 수 없습니다. --find-chat-id를 먼저 실행하세요.")
        return

    if args.send_latest:
        # 가장 최근 리포트 찾기
        reports = sorted(glob(os.path.join(REPORT_DIR, "morning_briefing_*.md")), reverse=True)
        if reports:
            with open(reports[0], "r", encoding="utf-8") as f:
                report = f.read()
            bot = TelegramBot()
            if not bot.chat_id:
                bot.chat_id = bot.find_chat_id()
            if bot.chat_id:
                telegram_text = format_report_for_telegram(report)
                bot.send_message(telegram_text)
                print(f"✅ 발송 완료: {os.path.basename(reports[0])}")
        else:
            print("❌ 저장된 리포트가 없습니다.")
        return

    # 기본: 모닝 브리핑 생성 + 발송
    run_and_send()


if __name__ == "__main__":
    main()
