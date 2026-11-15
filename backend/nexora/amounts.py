from decimal import Decimal

def raw_to_decimal(raw, decimals):
    """Ham tamsayı miktarı Decimal'e çevirir. Katı: negatif, sıfır, bool ve bozuk girdi reddedilir."""
    if isinstance(decimals, bool) or not isinstance(decimals, int) or not 0 <= decimals <= 255:
        raise ValueError("decimals 0-255 arası tamsayı olmalı")
    if isinstance(raw, bool):
        raise TypeError("raw bool olamaz")
    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, str) and raw.isascii() and raw.isdigit():
        value = int(raw)
    else:
        raise ValueError("raw pozitif tamsayı ya da rakam dizisi olmalı")
    if value <= 0:
        raise ValueError("miktar sıfırdan büyük olmalı")
    return Decimal(value).scaleb(-decimals)
