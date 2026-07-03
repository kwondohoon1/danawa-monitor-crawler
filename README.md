# 다나와 상품 데이터

다나와에 올라온 모니터, 키보드, 노트북, TV 상품의 가격과 스펙을 CSV로 모읍니다.
CPU, 그래픽카드, 메인보드, RAM, SSD, HDD, 쿨러, 케이스, 파워는 가격만 수집합니다.

각 카테고리는 서로 다른 GitHub Actions에서 따로 수집합니다.

## 가격정보 바로가기

- [monitor.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/latest/monitor.csv)
- [keyboard.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/latest/keyboard.csv)
- [laptop.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/latest/laptop.csv)
- [tv.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/latest/tv.csv)
- [cpu.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/latest/cpu.csv)
- [gpu.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/latest/gpu.csv)
- [motherboard.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/latest/motherboard.csv)
- [ram.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/latest/ram.csv)
- [ssd.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/latest/ssd.csv)
- [hdd.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/latest/hdd.csv)
- [cooler.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/latest/cooler.csv)
- [case.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/latest/case.csv)
- [power.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/latest/power.csv)

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

## 신제품 수집일 바로가기

- [monitor.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/new_products/monitor.csv)
- [keyboard.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/new_products/keyboard.csv)
- [laptop.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/new_products/laptop.csv)
- [tv.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/new_products/tv.csv)
- [cpu.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/new_products/cpu.csv)
- [gpu.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/new_products/gpu.csv)
- [motherboard.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/new_products/motherboard.csv)
- [ram.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/new_products/ram.csv)
- [ssd.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/new_products/ssd.csv)
- [hdd.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/new_products/hdd.csv)
- [cooler.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/new_products/cooler.csv)
- [case.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/new_products/case.csv)
- [power.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/new_products/power.csv)

각 파일에는 `product_code`, `product_name`, `first_collected_date`를 저장합니다.
`first_collected_date`는 다나와 등록월이 아니라 이 저장소에서 상품을 처음 확인한 날짜입니다.
기능 적용 전에 이미 수집 중이던 상품은 신제품 CSV에 넣지 않습니다.
한번 기록된 상품은 목록에서 사라졌다가 다시 나타나도 최초 날짜를 그대로 유지합니다.
상품코드가 `122000000` 이상인 상품만 기록하며, 상품명에 `중고` 또는 `해외구매`가 있으면 제외합니다.

## 스펙정보 바로가기

- [monitor_specs.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/specs/monitor_specs.csv)
- [keyboard_specs.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/specs/keyboard_specs.csv)
- [laptop_specs.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/specs/laptop_specs.csv)
- [tv_specs.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/specs/tv_specs.csv)

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

- 브랜드
- 인치
- 무게
- 운영체제
- 해상도
- 주사율
- 패널
- CPU
- CPU 브랜드
- CPU 모델
- CPU 코어
- NPU
- 그래픽
- 그래픽 구분
- 그래픽 모델
- 그래픽 메모리
- 램
- 램 종류
- 램 슬롯
- SSD
- 저장장치 슬롯
- 무선
- 배터리
- 단자
- 전체정보
- 등록년월

TV 스펙:

- 화면크기
- 화면종류
- 해상도
- 주사율
- HDR
- 스마트기능
- 전체정보
- 등록년월

## History 바로가기

- [monitor_price_history.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/history/monitor_price_history.csv)
- [keyboard_price_history.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/history/keyboard_price_history.csv)
- [laptop_price_history.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/history/laptop_price_history.csv)
- [tv_price_history.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/history/tv_price_history.csv)
- [cpu_price_history.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/history/cpu_price_history.csv)
- [gpu_price_history.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/history/gpu_price_history.csv)
- [motherboard_price_history.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/history/motherboard_price_history.csv)
- [ram_price_history.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/history/ram_price_history.csv)
- [ssd_price_history.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/history/ssd_price_history.csv)
- [hdd_price_history.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/history/hdd_price_history.csv)
- [cooler_price_history.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/history/cooler_price_history.csv)
- [case_price_history.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/history/case_price_history.csv)
- [power_price_history.csv](https://github.com/kwondohoon1/danawa-monitor-crawler/blob/main/data/history/power_price_history.csv)

## 자동 업데이트

- 모니터/키보드/노트북 가격정보: 매일 07:00 KST에 수집
- TV 가격정보: 매일 07:30 KST에 수집
- PC부품 가격정보: 매일 08:30 KST에 수집
- 모니터 스펙정보: 매일 03:00 KST에 수집
- 키보드 스펙정보: 매일 04:00 KST에 수집
- 노트북 스펙정보: 매일 12:00 KST에 수집
- TV 스펙정보: 매일 05:00 KST에 수집

사용하는 GitHub Actions는 아래와 같습니다.

- [Update Danawa price CSV](.github/workflows/update-danawa-prices.yml)
- [Update keyboard price CSV](.github/workflows/update-keyboard-prices.yml)
- [Update laptop price CSV](.github/workflows/update-laptop-prices.yml)
- [Update TV price CSV](.github/workflows/update-tv-prices.yml)
- [Update monitor specs CSV](.github/workflows/update-monitor-specs.yml)
- [Update keyboard specs CSV](.github/workflows/update-keyboard-specs.yml)
- [Update laptop specs CSV](.github/workflows/update-laptop-specs.yml)
- [Update TV specs CSV](.github/workflows/update-tv-specs.yml)

CPU, 그래픽카드, 메인보드, RAM, SSD, HDD, 쿨러, 케이스, 파워는 아래 액션에서 한 번에 수집합니다.
데스크탑은 같은 액션에서 수동으로만 돌릴 수 있습니다.

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
python scripts/crawl_laptop_prices.py --fail-on-empty --max-pages-per-maker 2 --workers 24
```

노트북은 상품 수가 많아서 전체 목록을 수집하지 않습니다.
ACER, ASUS, DELL, GIGABYTE, MSI, LENOVO, HP, 삼성, LG만 제조사 필터로 수집하고, 브랜드별 2페이지를 병렬로 가져옵니다.

TV 가격 수집:

```bash
python scripts/crawl_danawa.py --category tv --fail-on-empty --fetcher requests --skip-combined
```

PC부품 가격 수집:

```bash
python scripts/crawl_danawa.py --category cpu --category gpu --category motherboard --category ram --category ssd --category hdd --category cooler --category case --category power --fail-on-empty --fetcher requests --skip-combined
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
python scripts/crawl_laptop_specs.py --workers 48 --timeout 15 --retries 2 --fail-on-error
```

TV 스펙 수집:

```bash
python scripts/crawl_tv_specs.py --workers 48 --timeout 15 --retries 2
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
- `cpu`: CPU
- `gpu`: 그래픽카드
- `motherboard`: 메인보드
- `ram`: RAM
- `ssd`: SSD
- `hdd`: HDD
- `cooler`: 쿨러
- `case`: 케이스
- `power`: 파워
- `tv`: TV

매일 자동 수집은 모니터, 키보드, 노트북, TV, PC부품 가격만 켜두었습니다. 데스크탑은 수동 액션으로 돌리면 됩니다.
