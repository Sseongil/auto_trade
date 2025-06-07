from pykrx.stock import get_market_cap_by_ticker, get_market_ticker_name
from datetime import datetime
import pandas as pd
import logging

logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

def get_krx_stock_list(market="KOSPI"):
    try:
        today = datetime.today().strftime("%Y%m%d")
        df = get_market_cap_by_ticker(today, market)

        if df is None or df.empty:
            logging.error(f"[get_krx_stock_list] 시가총액 데이터 없음. 날짜: {today}, 시장: {market}")
            return None

        df.index.name = 'ticker'
        df = df.reset_index()

        # ✅ 종목명 수집: 컬럼에 '종목명'이 없으면 직접 수집해서 추가
        if '종목명' not in df.columns:
            df['종목명'] = df['ticker'].apply(get_market_ticker_name)

        # ✅ 컬럼명 통일
        df = df.rename(columns={
            'ticker': 'ticker',
            '종목명': 'name',
            '시가총액': 'market_cap'
        })

        return df[['ticker', 'name', 'market_cap']]

    except Exception as e:
        logging.error(f"[get_krx_stock_list] 예외 발생: {e}")
        return None
