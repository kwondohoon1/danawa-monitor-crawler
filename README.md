# 다나와 모니터 데이터

다나와에 올라온 모니터 상품의 가격과 스펙을 CSV로 모읍니다.

현재 매일 자동 업데이트되는 대상은 **모니터**입니다. 데스크탑과 키보드는 나중에 필요할 때 바로 추가할 수 있도록 설정만 남겨두었습니다.

## 가격정보 바로가기

- [모니터 가격](data/latest/monitor.csv)

가격 CSV는 아래처럼 단순하게 저장됩니다.

```csv
product_code,product_name,2026-05-19,2026-05-18,2026-05-17,...
```

- `product_code`: 다나와 상품코드
- `product_name`: 상품명
- 날짜 열: 해당 날짜의 가격

모니터 가격 CSV는 C열부터 J열까지 8개 날짜만 보여줍니다.

- C열: 오늘 가격
- D열: 어제 가격
- J열: 7일 전 가격

아직 수집한 적 없는 날짜는 빈칸으로 둡니다.

60일 기록 CSV는 파일 하나에 최근 60일만 저장합니다. 60일이 지난 날짜 열은 다음 업데이트 때 자동으로 빠집니다.

## 스펙정보 바로가기

- [모니터 스펙](data/specs/monitor_specs.csv)

스펙 CSV는 모니터 가격 CSV에 있는 상품코드 순서대로 수집합니다.

수집하는 주요 스펙은 아래 항목입니다.

- 인치
- 해상도
- 주사율
- 패널
- 비율
- 형태
- 색상
- 특수기능
- 정보전체
- 상품등록월

## History 바로가기

- [모니터 가격 60일 데이터](data/history/monitor_price_history.csv)

## 자동 업데이트

- 가격정보: 매일 09:00 KST에 모니터 가격만 업데이트
- 스펙정보: 매일 03:00 KST에 모니터 스펙 업데이트

사용하는 GitHub Actions는 아래 2개입니다.

- [Update Danawa price CSV](.github/workflows/update-danawa-prices.yml)
- [Update monitor specs CSV](.github/workflows/update-monitor-specs.yml)

데스크탑이나 키보드를 따로 돌리고 싶을 때는 아래 수동 액션을 실행하면 됩니다.

- [Update extra Danawa price CSV](.github/workflows/update-extra-prices.yml)

## 직접 실행

모니터 가격 수집:

```bash
pip install -r requirements.txt
python scripts/crawl_danawa.py --category monitor --fail-on-empty --fetcher requests
```

모니터 스펙 수집:

```bash
python scripts/crawl_monitor_specs.py --workers 32 --timeout 20 --retries 3 --fail-on-error
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

매일 자동 수집은 모니터만 켜두었습니다. 데스크탑과 키보드는 수동 액션으로 돌리거나, 나중에 별도 스케줄을 추가하면 됩니다.
