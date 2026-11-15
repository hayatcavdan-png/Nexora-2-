from decimal import Decimal


def _validate_decimals(decimals: int) -> None:
    if isinstance(decimals, bool) or not isinstance(decimals, int):
        raise TypeError("decimals must be an integer")
    if not 0 <= decimals <= 255:
        raise ValueError("decimals must be between 0 and 255")


def raw_to_decimal(raw_amount: str, decimals: int) -> Decimal:
    """Convert a positive raw integer string to Decimal without rounding."""
    if not isinstance(raw_amount, str):
        raise TypeError("raw_amount must be a string")

    if (
        not raw_amount
        or not raw_amount.isascii()
        or not raw_amount.isdigit()
        or raw_amount.startswith("0")
    ):
        raise ValueError("raw_amount must be a positive integer without leading zeros")

    _validate_decimals(decimals)

    digits = tuple(int(char) for char in raw_amount)
    return Decimal((0, digits, -decimals))


def decimal_to_raw(amount: Decimal, decimals: int) -> str:
    """Convert Decimal units to an exact raw integer string without rounding."""
    if not isinstance(amount, Decimal):
        raise TypeError("amount must be a Decimal; float is not accepted")

    if not amount.is_finite() or amount <= 0:
        raise ValueError("amount must be finite and positive")

    _validate_decimals(decimals)

    sign, digits, exponent = amount.as_tuple()

    if sign:
        raise ValueError("amount must be positive")

    digits = list(digits)
    shift = exponent + decimals

    if shift < 0:
        remove_count = -shift

        if remove_count > len(digits):
            raise ValueError("amount has more decimal places than token supports")

        if any(digits[-remove_count:]):
            raise ValueError("amount has more decimal places than token supports")

        digits = digits[:-remove_count]

    elif shift > 0:
        digits.extend([0] * shift)

    raw = "".join(str(digit) for digit in digits).lstrip("0")

    if not raw:
        raise ValueError("converted raw amount must be positive")

    return raw
