# 다나와 상품 데이터

다나와에 올라온 모니터, 키보드, 노트북 상품의 가격과 스펙을 CSV로 모읍니다.

각 카테고리는 서로 다른 GitHub Actions에서 따로 수집합니다.

## 가격정보 바로가기

- [모니터 가격](data/latest/monitor.csv?raw=1)
- [키보드 가격](data/latest/keyboard.csv?raw=1)
- [노트북 가격](data/latest/laptop.csv?raw=1)

가격 CSV는 아래처럼 단순하게 저장됩니다.

```csv
product_code,product_name,2026-05-19,2026-05-18,2026-05-17,...
```

- `product_code`: 다나와 상품코드
- `product_name`: 상품명
- 날짜 열: 해당 날짜의 가격

가격 CSV는 C열부터 J열까지 8개 날짜만 보여줍니다.

- C열: 오늘 가격
- D열: 어제 가격
- J열: 7일 전 가격

아직 수집한 적 없는 날짜는 빈칸으로 둡니다.

60일 기록 CSV는 파일 하나에 최근 60일만 저장합니다. 60일이 지난 날짜 열은 다음 업데이트 때 자동으로 빠집니다.

## 스펙정보 바로가기

- [모니터 스펙](data/specs/monitor_specs.csv?raw=1)
- [키보드 스펙](data/specs/keyboard_specs.csv?raw=1)
- [노트북 스펙](data/specs/laptop_specs.csv?raw=1)

스펙 CSV는 각 가격 CSV에 있는 상품코드 순서대로 수집합니다.

모니터 스펙:

- 인치
- 해상도
- 주사율
- 패널
- 비율
- 형태
- 밝기
- 색상
- 특수기능
- 정보전체
- 상품등록월

키보드 스펙:

- 사이즈
- 키 배열
- 연결 방식
- 배터리
- 배터리 용량
- 접점 방식
- 스위치 방식
- 키압
- 키 스위치
- 폴링레이트
- 응답속도
- 동시입력
- 키캡 재질
- 키캡 각인방식
- 부가 기능
- 정보전체
- 상품등록월

노트북 스펙:

- 인치
- 무게
- 운영체제
- 해상도
- 주사율
- CPU
- 그래픽
- 램
- SSD
- 전체정보
- 등록년월

## History 바로가기

- [모니터 가격 60일 데이터](data/history/monitor_price_history.csv?raw=1)
- [키보드 가격 60일 데이터](data/history/keyboard_price_history.csv?raw=1)
- [노트북 가격 60일 데이터](data/history/laptop_price_history.csv?raw=1)

## 자동 업데이트

- 가격정보: 매일 07:00 KST에 수집
- 모니터 스펙정보: 매일 03:00 KST에 수집
- 키보드 스펙정보: 매일 04:00 KST에 수집
- 노트북 스펙정보: 매일 12:00 KST에 수집

사용하는 GitHub Actions는 아래와 같습니다.

- [Update Danawa price CSV](.github/workflows/update-danawa-prices.yml)
- [Update keyboard price CSV](.github/workflows/update-keyboard-prices.yml)
- [Update laptop price CSV](.github/workflows/update-laptop-prices.yml)
- [Update monitor specs CSV](.github/workflows/update-monitor-specs.yml)
- [Update keyboard specs CSV](.github/workflows/update-keyboard-specs.yml)
- [Update laptop specs CSV](.github/workflows/update-laptop-specs.yml)

데스크탑을 따로 돌리고 싶을 때는 아래 수동 액션을 실행하면 됩니다.

- [Update extra Danawa price CSV](.github/workflows/update-extra-prices.yml)

## 직접 실행

모니터 가격 수집:

```bash
pip install -r requirements.txt
python scripts/crawl_danawa.py --category monitor --fail-on-empty --fetcher requests
```

키보드 가격 수집:

```bash
python scripts/crawl_danawa.py --category keyboard --fail-on-empty --fetcher requests
```

노트북 가격 수집:

```bash
python scripts/crawl_danawa.py --category laptop --pages 300 --fail-on-empty --fetcher requests
```

모니터 스펙 수집:

```bash
python scripts/crawl_monitor_specs.py --workers 32 --timeout 20 --retries 3 --fail-on-error
```

키보드 스펙 수집:

```bash
python scripts/crawl_keyboard_specs.py --workers 32 --timeout 20 --retries 3 --fail-on-error
```

노트북 스펙 수집:

```bash
python scripts/crawl_laptop_specs.py --workers 32 --timeout 20 --retries 3 --fail-on-error
```

테스트:

```bash
python -m unittest discover -s tests
```

## 카테고리 추가

카테고리 주소는 [config/categories.csv](config/categories.csv)에 있습니다.

현재 등록된 값:

- `monitor`: 모니터
- `desktop`: 데스크탑
- `keyboard`: 키보드
- `laptop`: 노트북

매일 자동 수집은 모니터, 키보드, 노트북만 켜두었습니다. 데스크탑은 수동 액션으로 돌리거나, 나중에 별도 스케줄을 추가하면 됩니다.
