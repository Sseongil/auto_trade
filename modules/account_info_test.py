# account_info_test.py
from pykiwoom.kiwoom import Kiwoom

kiwoom = Kiwoom()
kiwoom.CommConnect(block=True)  # 로그인

accounts = kiwoom.GetLoginInfo("ACCNO")  # 계좌번호 가져오기
print("📄 연결된 계좌 리스트:", accounts)
