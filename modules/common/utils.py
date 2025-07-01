# modules/common/utils.py

from datetime import datetime

def get_current_time_str():
    """
    현재 시간을 'YYYY-MM-DD HH:MM:SS' 형식의 문자열로 반환합니다.
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# 필요에 따라 다른 유틸리티 함수들을 여기에 추가할 수 있습니다.
# 예: 가격 포맷팅, 특정 데이터 변환 등
