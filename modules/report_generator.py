# modules/report_generator.py


import os
import pandas as pd
from datetime import datetime
import logging
from modules.notify import send_telegram_message

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- 상수 선언 ---
COL_RETURN = "수익률(%)"
COL_RESULT = "결과"

def generate_daily_trade_report() -> None:
    today_str = datetime.today().strftime("%Y%m%d")
    file_path = os.path.join("data", today_str, f"backtest_result_{today_str}.csv")
    report_title = f"📈 [{today_str}] 일일 자동매매 리포트"

    if not os.path.exists(file_path):
        msg = f"❌ 리포트 생성 실패: 백테스트 파일 없음: '{file_path}'"
        logger.warning(msg)
        send_telegram_message(f"{report_title}\n{msg}")
        return

    try:
        df = pd.read_csv(file_path, encoding='utf-8-sig')
        logger.info(f"📂 백테스트 파일 로드 성공: '{file_path}'")
    except pd.errors.EmptyDataError:
        msg = f"⚠️ 리포트 생성 경고: 백테스트 파일이 비어 있습니다: '{file_path}'"
        logger.warning(msg)
        send_telegram_message(f"{report_title}\n{msg}")
        return
    except Exception as e:
        msg = f"❌ 리포트 생성 오류: 백테스트 파일 읽기 실패: {e}"
        logger.error(msg, exc_info=True)
        send_telegram_message(f"{report_title}\n{msg}")
        return

    # --- 유효성 검사 ---
    required_cols = ["종목명", COL_RETURN, COL_RESULT]
    for col in required_cols:
        if col not in df.columns:
            msg = f"❌ 필수 컬럼 '{col}'이 누락되어 리포트를 생성할 수 없습니다."
            logger.error(msg)
            send_telegram_message(f"{report_title}\n{msg}")
            return

    try:
        df[COL_RETURN] = pd.to_numeric(df[COL_RETURN], errors='coerce')
        df.dropna(subset=[COL_RETURN], inplace=True)
    except Exception as e:
        msg = f"❌ '{COL_RETURN}' 숫자 변환 실패: {e}"
        logger.error(msg, exc_info=True)
        send_telegram_message(f"{report_title}\n{msg}")
        return

    if df.empty:
        msg = "📂 유효한 데이터가 없어 리포트를 생성할 수 없습니다."
        logger.info(msg)
        send_telegram_message(f"{report_title}\n{msg}")
        return

    # --- 통계 계산 ---
    total_trades = len(df)
    total_profit_loss = df[COL_RETURN].sum()
    avg_return = df[COL_RETURN].mean()

    win_trades = df[df[COL_RETURN] > 0]
    num_wins = len(win_trades)
    win_rate = (num_wins / total_trades) * 100 if total_trades > 0 else 0.0

    num_profit = df[df[COL_RESULT] == "익절"].shape[0]
    num_loss = df[df[COL_RESULT] == "손절"].shape[0]
    num_hold_end = df[df[COL_RESULT] == "보유종료"].shape[0]

    avg_win_return = win_trades[COL_RETURN].mean() if num_wins > 0 else 0.0
    loss_trades = df[df[COL_RETURN] <= 0]
    num_losses = len(loss_trades)
    avg_loss_return = loss_trades[COL_RETURN].mean() if num_losses > 0 else 0.0

    # --- 리포트 생성 ---
    summary_message = (
        f"{report_title}\n"
        f"------------------------------------\n"
        f"📊 거래 요약\n"
        f"  - 총 거래 횟수: {total_trades}회\n"
        f"  - 총 수익률: {total_profit_loss:.2f}%\n"
        f"  - 평균 수익률: {avg_return:.2f}%\n"
        f"  - 승률: {win_rate:.2f}%\n"
        f"------------------------------------\n"
        f"📈 상세 결과\n"
        f"  - 익절: {num_profit}회 (평균 수익: {avg_win_return:.2f}%)\n"
        f"  - 손절: {num_loss}회 (평균 손실: {avg_loss_return:.2f}%)\n"
        f"  - 보유종료: {num_hold_end}회\n"
        f"------------------------------------"
    )

    logger.info("\n" + summary_message + "\n")
    send_telegram_message(summary_message)

if __name__ == "__main__":
    generate_daily_trade_report()
