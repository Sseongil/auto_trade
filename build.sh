#!/usr/bin/env bash

# pip 캐시 디렉토리 생성 (없을 경우)
mkdir -p /.cache/pip

# pip install 명령 실행 시 캐시 디렉토리 사용하도록 설정
pip install --cache-dir /.cache/pip -r requirements.txt