# Danawa Price Crawler

다나와에 등록된 모니터, 데스크탑, 키보드 상품의 상품코드, 상품명, 가격을 CSV로 수집합니다.

기본 실행은 카테고리별 첫 페이지만 가져오지 않고, 다나와 Ajax 상품 리스트를 끝까지 순회합니다. 큰 카테고리에서 다나와가 한 정렬 기준으로 약 2천 개 근처까지만 반복 노출하는 경우가 있어, 가격 범위를 자동으로 나눠가며 상품코드를 합칩니다.

## CSV 파일 바로가기

- [전체 상품 CSV](data/latest/danawa_products.csv)
- [모니터 CSV](data/latest/monitor.csv)
- [데스크탑 CSV](data/latest/desktop.csv)
- [키보드 CSV](data/latest/keyboard.csv)
- [가격 히스토리 CSV](data/history/danawa_price_history.csv)

## 실행

```bash
pip install -r requirements.txt
python scripts/crawl_danawa.py --fail-on-empty
```

특정 카테고리만 수집:

```bash
python scripts/crawl_danawa.py --category monitor --fail-on-empty
```

테스트용으로 페이지 수를 제한:

```bash
python scripts/crawl_danawa.py --pages 2 --fail-on-empty
```

`--pages`를 지정하면 가격 범위 분할 없이 지정한 페이지만 확인합니다. 전체 수집은 `--pages`를 빼고 실행합니다.

## CSV 열

- `collected_at`
- `category`
- `product_code`
- `product_name`
- `price`
- `price_text`
- `product_url`

## 카테고리 설정

대상 카테고리는 [config/categories.csv](config/categories.csv)에서 관리합니다.

`pages` 값을 비워두면 마지막 페이지까지 자동 수집합니다. 테스트나 임시 제한이 필요할 때만 숫자를 넣으면 됩니다.

## GitHub Actions

[Update Danawa price CSV](.github/workflows/update-danawa-prices.yml) workflow가 매일 09:00 KST에 실행됩니다. 크롤링 후 `data/` 아래 CSV가 바뀌면 GitHub Actions bot이 자동 커밋합니다.

수동 실행은 GitHub Actions 화면에서 `workflow_dispatch`로 할 수 있습니다.
