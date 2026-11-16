"""Bibliographic references of catalogue books in the APA, MLA and Chicago styles (plain text)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

STYLES = ("apa", "mla", "chicago")

# Lower-case particles that follow the given names in an inverted name: "Balzac, Honoré de"
PARTICLES = {"de", "d'", "du", "des", "von", "van", "der", "den", "da", "di", "del", "della", "le", "la"}

CO_AUTHOR_SEPARATOR = ", "


def split_name(name: str) -> tuple[str, str, str]:
    """Return ``(given names, particles, surname)``: "Honoré de Balzac" -> ("Honoré", "de", "Balzac").

    A single name ("Homer", "Voltaire") is a surname without given names.
    """
    words = name.split()
    if len(words) < 2:
        return "", "", name.strip()
    surname = words[-1]
    rest = words[:-1]
    particles: list[str] = []
    while len(rest) > 1 and rest[-1].lower() in PARTICLES:
        particles.insert(0, rest.pop())
    return " ".join(rest), " ".join(particles), surname


def initials(given: str) -> str:
    """Return the initials of given names: "Jean-Paul" -> "J.-P.", "J.K." -> "J. K."."""
    def initial(word: str) -> str:
        return "-".join(part[:1].upper() + "." for part in word.split("-") if part)

    return " ".join(initial(word) for word in re.findall(r"[^\s.]+", given))


def _inverted(name: str, abbreviate: bool) -> str:
    given, particles, surname = split_name(name)
    if not given:
        return surname
    first = initials(given) if abbreviate else given
    return f"{surname}, {' '.join(filter(None, [first, particles]))}"


def _join(names: list[str], conjunction: str, serial_comma: bool) -> str:
    if len(names) == 1:
        return names[0]
    comma = "," if serial_comma else ""
    return f"{', '.join(names[:-1])}{comma} {conjunction} {names[-1]}"


def _year(year: int, locale: str) -> str:
    if year > 0:
        return str(year)
    return f"{-year} av. J.-C." if locale == "fr_FR" else f"{-year} BC"


def _sentence(text: str) -> str:
    """End ``text`` with a period unless it already ends with a punctuation mark."""
    return text if re.search(r"[.!?]$", text) else text + "."


def format_citation(book: Mapping[str, Any], style: str = "apa", locale: str = "en_US") -> str:
    """Return the reference of a localized ``book`` (``writer``, ``title``, ``year``, ``publisher``).

    ``locale`` sets the conjunction between authors ("&" / "and" or "et")
    and how years BC are written.
    """
    style = style.lower()
    if style not in STYLES:
        raise ValueError(f"Unknown citation style {style!r}; expected one of {', '.join(STYLES)}")
    authors = book["writer"].split(CO_AUTHOR_SEPARATOR)
    french = locale == "fr_FR"
    year = _year(book["year"], locale)
    title = book["title"]
    publisher = book.get("publisher")

    if style == "apa":
        names = [_inverted(author, abbreviate=True) for author in authors]
        conjunction = "et" if french else "&"
        reference = f"{_join(names, conjunction, serial_comma=not french)} ({year}). {_sentence(title)}"
        return f"{reference} {_sentence(publisher)}" if publisher else reference

    # MLA and Chicago: the first author inverted, the others in natural order
    conjunction = "et" if french else "and"
    if style == "mla" and len(authors) > 2:
        names_text = f"{_inverted(authors[0], abbreviate=False)}, et al"
    else:
        names = [_inverted(authors[0], abbreviate=False), *authors[1:]]
        # "Dorris, Michael, and Louise Erdrich": the comma also separates an inverted first name
        names_text = _join(names, conjunction, serial_comma=not french)
    publication = f"{publisher}, {year}" if publisher else year
    return f"{_sentence(names_text)} {_sentence(title)} {_sentence(publication)}"
