"""NEXORA Solana Social Radar pilotunun çevrimdışı CLI arayüzü."""
import argparse
import json
from pathlib import Path

from .service import SocialRadar
from .sources import CATALOG, NO_ACCESS, SourceBatch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    status = commands.add_parser("source-status", help="Kaynak kataloğu ve erişim durumu")
    status.add_argument("--fixture", type=Path, help="Yerel sentetik kaynak verisi")
    report = commands.add_parser("report", help="Salt okunur gölge raporu")
    report.add_argument("--fixture", type=Path, required=True, help="Yerel sentetik kaynak ve zincir verisi")
    args = parser.parse_args()

    if args.fixture is None:
        result = [SourceBatch(status=NO_ACCESS, enabled=source.enabled).describe(source, 0)
                  for source in CATALOG.values()]
    else:
        try:
            with args.fixture.open(encoding="utf-8") as handle:
                radar = SocialRadar.from_fixture(json.load(handle))
            result = radar.report() if args.command == "report" else radar.source_status()
        except (OSError, ValueError, RecursionError):
            parser.exit(1, "Sentetik fixture okunamadı veya geçersiz.\n")
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
