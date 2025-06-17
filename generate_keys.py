# generate_keys.py
import secrets

# 32바이트(256비트) 길이의 16진수 문자열 생성
# 이 길이면 충분히 안전합니다.
local_api_key = secrets.token_hex(32)
internal_api_key = secrets.token_hex(32)

print(f"LOCAL_API_KEY: {local_api_key}")
print(f"INTERNAL_API_KEY: {internal_api_key}")
