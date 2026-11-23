"""Dosya okuma yardımcıları: dosyayı her zaman kapatır (with bloğu)."""
import json


def json_oku(yol, encoding="utf-8"):
    with open(yol, encoding=encoding) as f:
        return json.load(f)


def metin_oku(yol, encoding="utf-8"):
    with open(yol, encoding=encoding) as f:
        return f.read()


def bayt_oku(yol):
    with open(yol, "rb") as f:
        return f.read()
