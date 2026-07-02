import argparse
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from danawa_crawler.new_products import update_new_products  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Record the first date each Danawa product was collected.")
    parser.add_argument("--category", action="append", required=True)
    parser.add_argument("--output", default="data")
    args = parser.parse_args()

    output_dir = Path(args.output)
    for category in args.category:
        added, total = update_new_products(output_dir, category)
        print(f"[{category}] added {added} new products, {total} recorded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
