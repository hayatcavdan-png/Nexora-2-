"""Günlük paper raporu (salt okunur). Çalıştır (backend klasöründe): python gunluk_rapor.py"""
import os
from nexora.rapor import build_report, as_text

if __name__ == "__main__":
    print(as_text(build_report(os.getenv("NEXORA_DB", "nexora_paper.db"), os.getenv("TRACKER_DB", "nexora_tracker.db"))))
