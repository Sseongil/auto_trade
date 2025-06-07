from PyQt5.QtWidgets import QApplication
from PyQt5.QAxContainer import QAxWidget
import sys

app = QApplication(sys.argv)
ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")

if ocx is not None:
    print("✅ KHOpenAPI 컨트롤 연결 성공")
else:
    print("❌ KHOpenAPI 컨트롤 연결 실패")
