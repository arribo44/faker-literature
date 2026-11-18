"""Run every update script on the bundled catalogue, in order, then report what changed.

The steps run on a copy of the catalogue: ``literature.json`` is replaced only
when all of them succeeded, so that a failing source (network, quota) leaves
it as it was.  The answers of Wikidata (editions), Wikipedia, Open Library and
the BnF are kept in ``--cache-dir`` (``data/sources/`` by default, ignored by
git), so that a second run reads only what is new.

Steps, in order:

1. ``popularity``: Wikipedia articles of the works, Wikidata ids of the books typed by hand;
2. ``authors``: Wikidata ids, birth and death of the authors;
3. ``awards``, 4. ``series``: literary awards and series of the works;
5. ``foreign-publishers``: publishers of another language than their locale's left out;
6. ``editions``, 7. ``wikipedia``, 8. ``openlibrary``, 9. ``bnf``: page counts and publishers of real editions.

Usage::

    python tools/literature_editor/update_all.py [--dry-run] [--only STEP ...] [--skip STEP ...]
"""

from __future__ import annotations

import argparse
import importlib
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import editor

from faker_literature.store import LOCALES

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "sources"

# (step, script module, cache option and file, or None)
STEPS = [
    ("popularity", "update_popularity", None),
    ("authors", "update_authors", None),
    ("awards", "update_awards", None),
    ("series", "update_series", None),
    ("foreign-publishers", "drop_foreign_publishers", None),
    ("editions", "update_editions", ("--rows", "wikidata_editions.json")),
    ("wikipedia", "update_wikipedia", ("--cache", "wikipedia.json")),
    ("openlibrary", "update_openlibrary", ("--cache", "openlibrary.json")),
    ("bnf", "update_bnf", ("--cache", "bnf.json")),
]
STEP_NAMES = [name for name, _, _ in STEPS]


def summary(data):
    """Count the books, the vocabularies and the missing page counts and publishers of a catalogue."""
    counts = Counter()
    for author in data["authors"]:
        for book in author["books"]:
            counts["books"] += 1
            counts["books in a series"] += bool(book.get("series"))
            counts["books with an award"] += bool(book.get("awards"))
            for field in ("pages", "publisher"):
                values = book.get(field) or {}
                for locale in LOCALES:
                    counts[f"{field} missing ({locale})"] += values.get(locale) is None
    for vocabulary in ("genres", "awards", "series", "publishers"):
        counts[vocabulary] = len(data.get(vocabulary, {}))
    counts["authors"] = len(data["authors"])
    return counts


def selected_steps(only=None, skip=None):
    """Return the steps to run, in their order."""
    unknown = sorted((set(only or ()) | set(skip or ())) - set(STEP_NAMES))
    if unknown:
        raise ValueError(f"unknown steps: {', '.join(unknown)} (steps: {', '.join(STEP_NAMES)})")
    return [step for step in STEPS if (not only or step[0] in only) and step[0] not in (skip or ())]


def run(catalogue, steps, cache_dir=None, dry_run=False, log=print, load=importlib.import_module):
    """Run ``steps`` on a copy of ``catalogue``; write it back unless ``dry_run``; return ``(before, after)``."""
    before = summary(editor.load_catalogue(catalogue))
    with tempfile.TemporaryDirectory(prefix="faker-literature-update-") as work:
        copy = Path(work) / catalogue.name
        shutil.copyfile(catalogue, copy)
        for name, module, cache in steps:
            log(f"== {name}")
            argv = ["--catalogue", str(copy)]
            if cache and cache_dir is not None:
                cache_dir.mkdir(parents=True, exist_ok=True)
                argv += [cache[0], str(cache_dir / cache[1])]
            try:
                load(module).main(argv)
            except (Exception, SystemExit) as error:
                raise RuntimeError(f"step {name!r} failed ({error!r}): the catalogue was not modified") from error
        data = editor.load_catalogue(copy)
        if not dry_run:
            editor.save_catalogue(data, catalogue)
    return before, summary(data)


def report(before, after):
    """Return the lines of the before / after table of the counts that changed."""
    lines = []
    for key in sorted(set(before) | set(after)):
        if before[key] != after[key]:
            change = after[key] - before[key]
            lines.append(f"  {key:30} {before[key]:6} -> {after[key]:6} ({change:+d})")
    return lines or ["  nothing changed"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--catalogue", type=Path, default=editor.CATALOGUE_PATH)
    parser.add_argument("--dry-run", action="store_true", help="run every step on a copy, without writing")
    parser.add_argument("--only", nargs="+", choices=STEP_NAMES, metavar="STEP", help="run these steps only")
    parser.add_argument("--skip", nargs="+", choices=STEP_NAMES, metavar="STEP", help="leave these steps out")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR,
                        help="directory of the caches of the sources (default: data/sources)")
    parser.add_argument("--no-cache", action="store_true", help="read every source again, without cache")
    args = parser.parse_args(argv)

    steps = selected_steps(args.only, args.skip)
    try:
        before, after = run(args.catalogue, steps, None if args.no_cache else args.cache_dir, args.dry_run)
    except RuntimeError as error:
        print(f"\n{error}", file=sys.stderr)
        return 1
    print("\n" + ("Dry run, nothing written:" if args.dry_run else f"{args.catalogue} updated:"))
    print("\n".join(report(before, after)))
    print("\nReview the changes with `git diff`, then run pytest.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
