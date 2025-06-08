# modules/report_generator.py

import os
import pandas as pd
from datetime import datetime
from modules.notify import send_telegram_message

def generate_text_summary():
    # 오늘 날짜를 YYYYMMDD 형식으로 가져옵니다.
    today = datetime.today().strftime("%Y%m%d")
    # 백테스트 결과 파일의 전체 경로를 생성합니다.
    file_path = os.path.join("data", today, f"backtest_result_{today}.csv") # f-string 사용으로 가독성 향상

    # 파일이 존재하는지 확인합니다.
    if not os.path.exists(file_path):
        print(f"❌ 백테스트 파일 없음: {file_path}") # f-string 사용
        return

    try:
        # CSV 파일을 데이터프레임으로 읽어옵니다.
        df = pd.read_csv(file_path, encoding='utf-8-sig') # 한글 깨짐 방지를 위한 encoding 추가
    except Exception as e:
        print(f"❌ 백테스트 파일 읽기 오류: {e}")
        return

    # 데이터프레임이 비어있는지 확인합니다.
    if df.empty:
        print("📂 백테스트 결과 없음.")
        return

    # 수익률이 0보다 큰 경우를 '승리'로 간주하여 승률을 계산합니다.
    # df["수익률(%)"]가 숫자형인지 확인하는 과정 추가 가능 (예: pd.to_numeric)
    win_rate = (df["수익률(%)"] > 0).mean() * 100
    # 평균 수익률을 계산합니다.
    avg_return = df["수익률(%)"].mean()

    # 익절, 손절, 보유종료 건수를 정확하게 계산합니다.
    # .str.contains() 대신 .eq()를 사용하는 것이 더 정확할 수 있습니다.
    # 그러나 현재 컬럼 '결과'에 '익절', '손절', '보유종료'만 명확히 들어간다면 큰 문제는 없습니다.
    # 다만, 문자열 내부에 해당 문자열이 포함된 경우도 True가 되므로,
    # 정확한 문자열 일치를 원한다면 `df['결과'] == '익절'`과 같이 사용하는 것이 좋습니다.
    num_profit = df[df["결과"] == "익절"].shape[0] # 정확한 일치로 변경
    num_loss = df[df["결과"] == "손절"].shape[0]   # 정확한 일치로 변경
    num_hold_end = df[df["결과"] == "보유종료"].shape[0] # 정확한 일치로 변경


    # 요약 메시지를 포맷팅합니다.
    summary = (
        f"📈 [{today}] 자동매매 요약\n"
        f"총 종목 수: {len(df)}개\n"
        f"▶ 평균 수익률: {avg_return:.2f}%\n"
        f"▶ 승률: {win_rate:.2f}%\n"
        f"▶ 익절: {num_profit}개\n"
        f"▶ 손절: {num_loss}개\n"
        f"▶ 보유종료: {num_hold_end}개"
    )
    
    # 요약 메시지를 콘솔에 출력하고 텔레그램으로 전송합니다.
    print(summary)
    send_telegram_message(summary)

if __name__ == "__main__":
    generate_text_summary()