import os
import requests
import json
import time
from dotenv import load_dotenv

load_dotenv()

RENDER_API_KEY = os.getenv("RENDER_API_KEY")
RENDER_SERVICE_ID = os.getenv("RENDER_SERVICE_ID")
RENDER_DEPLOY_HOOK_URL = os.getenv("RENDER_DEPLOY_HOOK_URL")
ENV_VAR_NAME = "LOCAL_API_SERVER_URL"
NGROK_API_URL = "http://127.0.0.1:4040/api/tunnels"

MAX_RETRIES = 12  # 최대 60초 대기 (5초 * 12번)

def get_ngrok_public_url():
    for attempt in range(MAX_RETRIES):
        try:
            print(f"🔄 ngrok 터널 감지 시도 {attempt + 1}/{MAX_RETRIES}...")
            response = requests.get(NGROK_API_URL, timeout=5)
            response.raise_for_status()
            tunnels = response.json().get("tunnels", [])
            for tunnel in tunnels:
                if tunnel["public_url"].startswith("https://"):
                    print(f"✅ 감지된 ngrok 주소: {tunnel['public_url']}")
                    return tunnel["public_url"]
            print("🔎 HTTPS ngrok 터널을 아직 찾지 못했습니다. 재시도 중...")
        except Exception as e:
            print(f"❗ ngrok API 연결 실패 (재시도 중): {e}")
        time.sleep(5)
    print("❌ ngrok 주소 감지 실패. ngrok이 제대로 실행 중인지 확인하세요.")
    return None

def update_render_env_var(new_url):
    url = f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/env-vars"
    headers = {
        "Authorization": f"Bearer {RENDER_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        print(f"🌐 Render에서 환경 변수 목록 조회 중...")
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        existing_env_vars = response.json()

        updated_env_vars = [var for var in existing_env_vars if var["key"] != ENV_VAR_NAME]
        updated_env_vars.append({"key": ENV_VAR_NAME, "value": new_url})

        print(f"🔁 Render 환경 변수 업데이트 요청...")
        put_response = requests.put(url, headers=headers, json=updated_env_vars, timeout=10)
        put_response.raise_for_status()
        print(f"✅ 환경 변수 {ENV_VAR_NAME} 업데이트 성공: {new_url}")
        return True

    except Exception as e:
        print(f"❌ 환경 변수 업데이트 실패: {e}")
        return False

def trigger_render_deploy():
    if not RENDER_DEPLOY_HOOK_URL:
        print("⚠️ RENDER_DEPLOY_HOOK_URL 설정 없음. 재배포 생략.")
        return False
    try:
        print(f"🚀 Render 재배포 트리거 중...")
        response = requests.post(RENDER_DEPLOY_HOOK_URL, timeout=10)
        response.raise_for_status()
        print("✅ Render 재배포 트리거 성공.")
        return True
    except Exception as e:
        print(f"❌ 재배포 트리거 실패: {e}")
        return False

if __name__ == "__main__":
    print("🚀 자동화 시작: ngrok 주소 → Render 환경 변수 → 재배포")

    ngrok_url = get_ngrok_public_url()
    if not ngrok_url:
        print("❌ ngrok URL을 감지하지 못해 종료합니다.")
        exit(1)

    if update_render_env_var(ngrok_url):
        trigger_render_deploy()
    else:
        print("⚠️ 환경 변수 업데이트 실패로 재배포 생략.")
