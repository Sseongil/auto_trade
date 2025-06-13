# C:\Users\user\stock_auto\test_kiwoom_opw00004.py
from pykiwoom.kiwoom import Kiwoom
import time
import logging
import traceback
import pandas as pd 

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    kiwoom = Kiwoom()
    kiwoom.CommConnect()
    time.sleep(5)  # 연결 대기

    if kiwoom.GetConnectState() == 1:
        logger.info("Kiwoom API connected successfully!")

        accounts = kiwoom.GetLoginInfo("ACCNO")
        account_number = accounts.split(';')[0] if isinstance(accounts, str) else str(accounts[0])
        logger.info(f"Using account number: {account_number}")

        logger.info("Attempting block_request for OPW00004...")

        df = kiwoom.block_request(
            "OPW00004",
            계좌번호=account_number,
            비밀번호="",  # 공란 가능
            상장폐지구분=0,
            비밀번호입력매체구분="00",
            거래소구분="KRX",
            output="계좌평가현황",  # ✅ 반드시 추가해야 함!
            next=0
        )

        logger.info(f"Result from OPW00004:\n{df}")

        if isinstance(df, dict):
            logger.info(f"총매입금액: {df.get('총매입금액')}")
            logger.info(f"총평가금액: {df.get('총평가금액')}")
            logger.info(f"총평가손익금액: {df.get('총평가손익금액')}")
            logger.info(f"총수익률: {df.get('총수익률')}")
        elif isinstance(df, pd.DataFrame):
            logger.info(f"Returned DataFrame with {len(df)} rows")
        else:
            logger.warning(f"Unexpected type of result for OPW00004: {type(df)}")

    else:
        logger.error("Failed to connect to Kiwoom API.")

except Exception as e:
    logger.error(f"An error occurred: {e}")
    logger.error(traceback.format_exc())
