# auto_trade (자동 주식 트레이딩 봇)

---

## 🚀 프로젝트 개요

이 프로젝트는 키움증권 API와 연동하여 주식 자동 매매를 수행하고, 텔레그램을 통해 알림을 제공하는 자동화된 트레이딩 봇입니다. 미리 정의된 매수 리스트(`buy_list.csv`)에 따라 주식을 매수하고, 손절, 익절, 트레일링 스탑, 최대 보유일 등 다양한 청산 전략을 사용하여 기존 보유 포지션을 관리하도록 설계되었습니다.

## ✨ 주요 기능

* **자동 매수**: 매일 `buy_list.csv` 파일을 읽어 매수 주문을 실행합니다.
* **포지션 모니터링**: 보유 중인 주식 포지션을 지속적으로 모니터링합니다.
* **스마트 청산 전략**:
    * **손절매**: 미리 정의된 손실률에 도달하면 손절매합니다.
    * **50% 익절**: 수익 목표에 도달하면 절반을 매도하고, 나머지 물량에 대한 트레일링 스탑을 설정합니다.
    * **트레일링 스탑**: 최고가 대비 일정 비율 하락 시 나머지 물량을 매도하여 수익을 보존합니다.
    * **최대 보유일**: 지정된 보유 기간을 초과하면 자동으로 포지션을 청산합니다.
* **텔레그램 연동**: 매매 내역, 오류, 상태 업데이트 등 실시간 알림을 텔레그램으로 전송합니다.
* **로그 기록**: 모든 매매 활동에 대한 상세 로그를 `trade_log.csv` 파일에 기록합니다.
* **설정 용이**: `modules/config.py`를 통해 거래 파라미터 및 API 키를 쉽게 조정할 수 있습니다.

## 🛠️ 설정 및 설치

### 전제 조건

* **Python 3.x**: Python이 설치되어 있어야 합니다.
* **키움증권 계좌**: 키움증권 계좌가 활성화되어 있어야 하며, Windows 운영체제에 `키움 OpenAPI+`가 설치되어 있어야 합니다.
* **텔레그램 봇 토큰**: BotFather를 통해 새로운 텔레그램 봇을 생성하고 봇 토큰을 받아야 합니다.
* **텔레그램 채팅 ID**: 봇이 메시지를 보낼 개인 또는 그룹 채팅 ID를 확인해야 합니다.

### 로컬 설정

1.  **저장소 복제**:
    ```bash
    git clone [https://github.com/your-username/auto_trade.git](https://github.com/your-username/auto_trade.git)
    cd auto_trade
    ```

2.  **가상 환경 생성 (권장)**:
    ```bash
    python -m venv venv
    # Windows:
    .\venv\Scripts\activate
    # macOS/Linux:
    source venv/bin/activate
    ```

3.  **의존성 설치**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **`modules/config.py` 설정**:
    `modules/config.py` 파일을 열어 다음 내용을 업데이트합니다:
    * `TELEGRAM_TOKEN`: 당신의 텔레그램 봇 토큰.
    * `TELEGRAM_CHAT_ID`: 알림을 받을 채팅 ID.
    * 당신의 전략에 맞춰 `STOP_LOSS_PCT`, `TAKE_PROFIT_PCT`, `TRAIL_STOP_PCT`, `MAX_HOLD_DAYS`, `DEFAULT_LOT_SIZE` 값을 조정합니다.
    * (선택 사항이지만 로컬 테스트 시 권장) `KIWOOM_ACCOUNT_PASSWORD`를 일시적으로 하드코딩하여 테스트할 수 있지만, 프로덕션 환경에서는 제거하거나 보안적으로 관리해야 합니다.

5.  **초기 파일 준비**:
    * 루트 디렉토리에 `status.json` 파일이 존재하는지 확인하거나 (없다면 직접 생성):
        ```json
        {
          "status": "start"
        }
        ```
    * 루트 디렉토리에 빈 `positions.csv` 파일을 생성합니다:
        ```csv
        ticker,name,buy_price,quantity,buy_date,half_exited,trail_high
        ```
    * 일별 `buy_list.csv` 파일이 저장될 `data` 디렉토리를 루트 디렉토리에 생성합니다. 예: `data/YYYYMMDD/buy_list.csv`.

## ⚙️ 실행 방법

이 봇은 지속적인 환경에서 실행되도록 설계되었습니다.

### 로컬 실행 (개발/테스트용)

일반적으로 텔레그램 연동을 위해 `server.py`를 실행하고, `auto_trade.py`와 `monitor_positions.py`는 작업 스케줄러(예: Windows 작업 스케줄러, Linux Cron)를 사용하여 예약 실행합니다.

1.  **텔레그램 웹훅 서버 시작**:
    ```bash
    python modules/server.py
    ```
    이 명령은 텔레그램 업데이트를 수신하기 위한 Flask 서버를 시작합니다. 이를 작동시키려면 텔레그램에 웹훅을 설정해야 합니다 (로컬 테스트 시에는 Ngrok 같은 공개 URL이 필요할 수 있습니다).

2.  **자동 매매 실행 (예약 실행)**:
    테스트를 위해 수동으로 실행:
    ```bash
    python modules/auto_trade.py
    python modules/monitor_positions.py
    ```
    운영 환경에서는 운영체제의 스케줄러를 사용하여 자동화합니다:
    * **`auto_trade.py`**: 하루에 한 번, 예를 들어 장 개장 직후(예: 오전 09:05 KST) 실행합니다.
    * **`monitor_positions.py`**: 장 중에는 빈번하게(예: 오전 09:00 ~ 오후 03:20 KST 사이에 5~10분 간격으로) 실행합니다.

### Render.com 배포 (운영 환경 권장)

`.render.yaml`에 명시된 대로 `server.py`를 웹 서비스로 배포합니다. `auto_trade.py`와 `monitor_positions.py`는 **Render Cron Job**으로 설정할 수 있습니다.

1.  **환경 변수 설정**: Render 대시보드의 서비스에서 `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` (선택적으로 `KIWOOM_ACCOUNT_PASSWORD`)를 환경 변수로 추가합니다.
2.  **웹 서비스 배포**: 코드를 Render에 연결된 Git 저장소로 푸시합니다. Render는 `.render.yaml` 설정에 따라 `telegram-bot` 웹 서비스를 빌드하고 배포할 것입니다.
3.  **Cron Job 생성**:
    * **자동 매매 Cron**: 새로운 Cron Job 서비스를 생성합니다. `startCommand`를 `python modules/auto_trade.py`로 설정합니다. 매일 실행되도록 스케줄을 구성합니다(예: 오전 09:05 KST).
    * **포지션 모니터링 Cron**: 또 다른 Cron Job 서비스를 생성합니다. `startCommand`를 `python modules/monitor_positions.py`로 설정합니다. 장 중에는 빈번하게 실행되도록 스케줄을 구성합니다(예: 5~10분 간격).

## 🗄️ 프로젝트 구조
.
├── modules/
│   ├── auto_trade.py         # 자동 매수 로직
│   ├── config.py             # 설정 상수 및 헬퍼 함수
│   ├── monitor_positions.py  # 포지션 모니터링 및 매도 로직
│   ├── notify.py             # 텔레그램 알림 모듈
│   ├── server.py             # 텔레그램 웹훅을 위한 Flask 서버
│   ├── trade_logger.py       # 모든 매매 활동 로그 기록
│   └── trade_manager.py      # positions.csv 관리 (추가/제거)
├── data/                     # 일별 매수 리스트 디렉토리
│   └──YYYYMMDD/
│       └── buy_list.csv      # 매일 매수할 종목 리스트
├── positions.csv             # 현재 보유 중인 포지션 저장 파일
├── trade_log.csv             # 모든 매매 내역 저장 파일
├── status.json               # 봇 상태 제어 파일 (start/stop)
├── .gitignore                # Git 추적 제외 파일 지정
├── .render.yaml              # Render.com 배포 설정
├── README.md                 # 프로젝트 문서
└── requirements.txt          # Python 의존성
## ⚠️ 중요 사항

* **보안**: 민감한 API 키나 비밀번호를 코드 저장소에 직접 커밋하지 마십시오. 환경 변수 또는 보안 설정 관리 시스템을 사용하세요.
* **키움 OpenAPI+**: 이 봇은 Windows에서 실행되는 키움 OpenAPI+에 의존합니다. Render와 같은 서버 배포 환경에서는 별도의 Windows 머신(예: 항상 켜져 있는 로컬 PC 또는 Windows 클라우드 VM)에서 키움이 실행되고, 봇이 프록시를 통해 통신하도록 설정해야 할 수 있습니다. Linux 기반 Render 인스턴스에서는 키움 API에 직접 연결하는 것이 불가능합니다.
* **장 운영 시간**: 오류 방지를 위해 봇은 정규 시장 운영 시간 내에만 거래를 시도해야 합니다.
* **테스트**: 실제 자금을 투입하기 전에 시뮬레이션 환경이나 소규모로 봇을 철저히 테스트하십시오.

## 🤝 기여

이 프로젝트 개선에 기여하고 싶다면 언제든지 이슈를 열거나 풀 리퀘스트를 보내주세요.

## 📄 라이선스

이 프로젝트는 **MIT License**를 따릅니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.