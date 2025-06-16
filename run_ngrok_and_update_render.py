import os
import requests
import time
from dotenv import load_dotenv
import sys
import io
import json

# 콘솔 인코딩: 한글 깨짐 방지
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# .env 로드
load_dotenv()

RENDER_API_KEY = os.getenv("RENDER_API_KEY")
RENDER_SERVICE_ID = os.getenv("RENDER_SERVICE_ID")
RENDER_DEPLOY_HOOK_URL = os.getenv("RENDER_DEPLOY_HOOK_URL")
ENV_VAR_NAME = "LOCAL_API_SERVER_URL"
NGROK_API_URL = "http://127.0.0.1:4040/api/tunnels"
MAX_RETRIES = 12

def get_ngrok_public_url():
    print("[START] Get ngrok URL...")
    for attempt in range(MAX_RETRIES):
        try:
            print(f"[{attempt+1}/{MAX_RETRIES}] Trying ngrok API...")
            response = requests.get(NGROK_API_URL, timeout=5)
            response.raise_for_status()
            tunnels = response.json().get("tunnels", [])
            for tunnel in tunnels:
                if tunnel.get("public_url", "").startswith("https://"):
                    print(f"[OK] Found ngrok URL: {tunnel['public_url']}")
                    return tunnel["public_url"]
            print("[WAIT] No HTTPS tunnel found. Retrying...")
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            print(f"[ERROR] ngrok fetch failed: {e}")
        time.sleep(5)
    print("[FAIL] Could not get ngrok URL after retries.")
    return None

def update_render_env_var(new_url):
    url = f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/env-vars"
    headers = {
        "Authorization": f"Bearer {RENDER_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        print("[INFO] Fetching current env vars from Render...")
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        raw_env_vars = response.json()
        print(f"[OK] Retrieved {len(raw_env_vars)} env vars.")

        updated_env_vars = []
        found = False

        for var_item in raw_env_vars:
            var = var_item.get("envVar", var_item)  # compatibility
            key = var.get("key")
            value = var.get("value")
            var_id = var.get("id")
            is_sensitive = var.get("isSensitive", False)

            if not key or key.strip() == "":
                print(f"[WARN] Skipping invalid env var: {var_item}")
                continue

            if key == ENV_VAR_NAME:
                updated_env_vars.append({
                    "key": key,
                    "value": new_url,
                    "id": var_id,
                    "isSensitive": is_sensitive
                })
                found = True
                print(f"[INFO] Updated existing {ENV_VAR_NAME}.")
            else:
                updated_env_vars.append({
                    "key": key,
                    "value": value,
                    "id": var_id,
                    "isSensitive": is_sensitive
                })

        if not found:
            print(f"[INFO] Adding new env var {ENV_VAR_NAME}.")
            updated_env_vars.append({
                "key": ENV_VAR_NAME,
                "value": new_url,
                "isSensitive": False
            })

        print(f"[INFO] Sending PUT request to update env vars...")
        put_resp = requests.put(url, headers=headers, json=updated_env_vars, timeout=10)
        put_resp.raise_for_status()
        print(f"[SUCCESS] Environment variables updated. Status: {put_resp.status_code}")
        return True

    except requests.exceptions.HTTPError as e:
        print(f"[FAIL] HTTP error: {e.response.status_code} - {e.response.text}")
    except requests.exceptions.RequestException as e:
        print(f"[FAIL] Request exception: {e}")
    except Exception as e:
        print(f"[FAIL] Unexpected error: {e}")
    return False

def trigger_render_deploy():
    if not RENDER_DEPLOY_HOOK_URL:
        print("[SKIP] No RENDER_DEPLOY_HOOK_URL set. Skipping redeploy.")
        return False
    try:
        print("[INFO] Triggering redeploy...")
        resp = requests.post(RENDER_DEPLOY_HOOK_URL, timeout=10)
        resp.raise_for_status()
        print("[SUCCESS] Redeploy triggered.")
        return True
    except requests.exceptions.RequestException as e:
        print(f"[FAIL] Redeploy failed: {e}")
        return False

if __name__ == "__main__":
    print("[START] Sync ngrok URL to Render...")

    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        print("[ABORT] Missing RENDER_API_KEY or RENDER_SERVICE_ID.")
        sys.exit(1)

    ngrok_url = get_ngrok_public_url()
    if not ngrok_url:
        print("[ABORT] ngrok URL not found.")
        sys.exit(1)

    if update_render_env_var(ngrok_url):
        trigger_render_deploy()
    else:
        print("[ABORT] Skipping deploy trigger due to update failure.")

    print("[END] Sync ngrok URL to Render.")
