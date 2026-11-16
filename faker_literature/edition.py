"""Building blocks of fake editions: formats, prices and ISBN-13."""

from __future__ import annotations

import zlib
from typing import NamedTuple


class Format(NamedTuple):
    """A book format in one locale: its name, page ratio and price range."""

    name: str
    page_ratio: float
    min_price: float
    max_price: float


CURRENCIES = {"fr_FR": "EUR", "en_US": "USD"}

# Pocket editions use smaller type (more pages), hardcovers larger pages (fewer)
FORMATS: dict[str, tuple[Format, ...]] = {
    "fr_FR": (
        Format("poche", 1.15, 5.9, 12.9),
        Format("broché", 1.0, 15.0, 25.0),
        Format("relié", 0.95, 22.0, 45.0),
    ),
    "en_US": (
        Format("mass market paperback", 1.15, 7.99, 10.99),
        Format("paperback", 1.0, 12.99, 19.99),
        Format("hardcover", 0.95, 22.99, 35.99),
    ),
}

# ISBN registration groups: French-speaking (2), English-speaking (0 and 1)
ISBN_GROUPS = {"fr_FR": ("2",), "en_US": ("0", "1")}


def isbn13_check_digit(first_twelve: str) -> str:
    """Return the check digit of an ISBN-13 from its first twelve digits."""
    total = sum(int(digit) * (3 if index % 2 else 1) for index, digit in enumerate(first_twelve))
    return str((10 - total % 10) % 10)


def is_valid_isbn13(isbn: str) -> bool:
    """Tell whether ``isbn`` (hyphens allowed) is a well-formed ISBN-13 with the right check digit."""
    digits = isbn.replace("-", "")
    return len(digits) == 13 and digits.isdigit() and digits[:3] in ("978", "979") \
        and isbn13_check_digit(digits[:12]) == digits[12]


def publisher_code(publisher: str, locale: str) -> tuple[str, str]:
    """Return the stable ``(group, registrant)`` ISBN prefix of a publisher.

    The same publisher always gets the same prefix, as in real life.
    """
    groups = ISBN_GROUPS[locale]
    checksum = zlib.crc32(f"{locale}:{publisher}".encode())
    return groups[checksum % len(groups)], str(1000 + checksum % 9000)


def make_isbn13(publisher: str, locale: str, title_number: int) -> str:
    """Return a hyphenated ISBN-13 such as ``978-2-1234-0042-7`` for a publisher's ``title_number``."""
    group, registrant = publisher_code(publisher, locale)
    publication = f"{title_number % 10000:04d}"
    first_twelve = f"978{group}{registrant}{publication}"
    return f"978-{group}-{registrant}-{publication}-{isbn13_check_digit(first_twelve)}"


def round_price(price: float, locale: str) -> float:
    """Round like shop prices: 8.90 € or 9.50 € in French, $12.99 in English."""
    if locale == "en_US":
        return round(max(1, round(price)) - 0.01, 2)
    return round(round(price * 10) / 10, 2)
