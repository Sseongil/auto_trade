from flask import Flask, request

app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    print("✅ Webhook 수신 성공!")
    print("📦 요청 데이터:", request.json)
    return "ok"

if __name__ == "__main__":
    print("✅ Flask 테스트 서버 시작됨 (포트 5000)")
    app.run(host="0.0.0.0", port=5000)
