"""Strateji teşhis raporu (salt okunur). Çalıştır (backend klasöründe):  python3 strateji_teshis.py [gün=3]"""
import sys
from nexora.teshis import rapor

if __name__ == "__main__":
    print(rapor(GUN=float(sys.argv[1]) if len(sys.argv) > 1 else 3.0))
