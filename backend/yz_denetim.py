"""Yerel etiket kopyasından salt okunur V1 raporu."""
import argparse
import json
import sqlite3

from nexora.ai_denetim import rapor


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", required=True, help="Yerel etiket SQLite kopyası")
    p.add_argument("--ufuk", choices=("kaynak", "5dk", "30dk"), default="kaynak", help="Model ve gölge sınama ufku")
    p.add_argument("--sinyaller", action="store_true", help="Kimliksiz sinyal bazlı gölge kararları ekle")
    args = p.parse_args()
    try:
        d = rapor(args.db, args.ufuk, ayrinti=args.sinyaller)
    except sqlite3.Error:
        p.exit(1, "Etiket veritabanı okunamadı.\n")
    print(json.dumps(d, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
