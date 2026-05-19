# Danawa Price Crawler

다나와 카테고리에서 상품코드, 상품명, 최저 표시 가격을 수집해 CSV로 저장하는 최소 버전입니다. 현재 대상은 모니터, 데스크탑, 키보드 3종입니다.

## 실행

```bash
pip install -r requirements.txt
python scripts/crawl_danawa.py --fail-on-empty
```

결과 파일:

- `data/latest/monitor.csv`
- `data/latest/desktop.csv`
- `data/latest/keyboard.csv`
- `data/latest/danawa_products.csv`
- `data/history/danawa_price_history.csv`

## 카테고리 조정

대상 카테고리는 `config/categories.csv`에서 관리합니다. `pages` 값을 늘리면 더 많은 페이지를 수집합니다. 안정화 전에는 다나와 요청 부담을 줄이기 위해 기본값을 1페이지로 두었습니다.

## GitHub Actions

`.github/workflows/update-danawa-prices.yml`가 매일 09:00 KST에 실행됩니다. 크롤링 후 `data/` 아래 CSV가 바뀌면 GitHub Actions bot이 자동 커밋합니다. 수동 실행은 GitHub Actions 화면의 `workflow_dispatch`로 할 수 있습니다.

## 다음 단계

상품 상세 스펙은 상세 페이지의 `pcode` 기반 URL에서 붙이면 됩니다. 현재 CSV에 `product_url`을 저장해 두었기 때문에 다음 단계에서는 이 URL을 순회하면서 스펙 필드를 추가하면 됩니다.
