"""Yerel sentetik Solana sosyal olay fixture'ından yönetici JSON raporu."""
import argparse
import json
from pathlib import Path

from .report import report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True, help="Yerel sentetik JSON fixture")
    args = parser.parse_args()
    try:
        with args.fixture.open(encoding="utf-8") as handle:
            result = report(json.load(handle))
    except (OSError, ValueError, RecursionError):
        parser.exit(1, "Sentetik fixture okunamadı veya geçersiz.\n")
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
