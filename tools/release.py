"""Publish a tagged version by hand, while the Release workflow cannot reach PyPI.

The Release workflow publishes a pushed tag ``vX.Y.Z`` on PyPI by Trusted
Publishing.  Until PyPI accepts it, a version is published in three steps,
with the same checks as the workflow:

1. ``python tools/release.py build X.Y.Z`` checks that the tag exists and
   matches ``__version__`` and a dated CHANGELOG section, builds the wheel and
   the source archive from the tag alone (``git archive``: no local file
   outside the repository gets in), checks them with ``twine check --strict``
   and prints their SHA-256 and the upload command;
2. you run ``twine upload`` yourself, with your own PyPI token;
3. ``python tools/release.py github X.Y.Z`` checks that PyPI serves the same
   files (same SHA-256), then creates the GitHub release: title
   "faker-literature X.Y.Z", the CHANGELOG section as notes, both files
   attached.

The files go to ``build/release-X.Y.Z/`` (ignored by git).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "faker-literature"
DIST_NAME = "faker_literature"
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")


def _git(*args, text=True):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=text).stdout


def tagged_file(tag, path):
    return _git("show", f"{tag}:{path}")


def package_version(init_text):
    """The ``__version__`` of ``faker_literature/__init__.py``."""
    match = re.search(r'^__version__ = "([^"]+)"', init_text, re.MULTILINE)
    if not match:
        raise ValueError("faker_literature/__init__.py defines no __version__")
    return match.group(1)


def release_notes(changelog, version):
    """The CHANGELOG section of ``version``, without its heading and the links at the end.

    Raises ``ValueError`` when the section is missing, undated or empty.
    """
    lines, found = [], False
    for line in changelog.splitlines():
        if found and (line.startswith("## [") or re.match(r"^\[[^]]+\]: ", line)):
            break
        if found:
            lines.append(line)
        elif re.match(rf"^## \[{re.escape(version)}\] - [0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$", line):
            found = True
    notes = "\n".join(lines).strip()
    if not found:
        raise ValueError(f"CHANGELOG.md has no '## [{version}] - YYYY-MM-DD' section")
    if not notes:
        raise ValueError(f"the CHANGELOG section of {version} is empty")
    return notes + "\n"


def check_tag(version):
    """Check that ``vVERSION`` exists and matches the version and the CHANGELOG; return the tag."""
    if not VERSION.fullmatch(version):
        raise ValueError(f"{version!r} is not a version such as 0.7.1")
    tag = f"v{version}"
    if not _git("tag", "--list", tag).strip():
        raise ValueError(f"tag {tag} does not exist: merge the release and push the tag first")
    found = package_version(tagged_file(tag, "faker_literature/__init__.py"))
    if found != version:
        raise ValueError(f"tag {tag} holds version {found}")
    release_notes(tagged_file(tag, "CHANGELOG.md"), version)
    return tag


def dist_files(version):
    directory = ROOT / "build" / f"release-{version}"
    return directory, [directory / f"{DIST_NAME}-{version}-py3-none-any.whl",
                       directory / f"{DIST_NAME}-{version}.tar.gz"]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(version, log=print):
    tag = check_tag(version)
    directory, files = dist_files(version)
    with tempfile.TemporaryDirectory(prefix="faker-literature-release-") as work:
        archive = _git("archive", "--format=tar", tag, text=False)
        subprocess.run(["tar", "-x", "-C", work], input=archive, check=True)
        subprocess.run([sys.executable, "-m", "build", "--outdir", str(directory), work], check=True,
                       capture_output=True)
    subprocess.run([sys.executable, "-m", "twine", "check", "--strict", *map(str, files)], check=True)
    for path in files:
        log(f"{sha256(path)}  {path.name}")
    log(f"\nUpload them with your PyPI token (user name __token__):\n"
        f"  {sys.executable} -m twine upload {directory}/*\n"
        f"then run: python tools/release.py github {version}")
    return files


def pypi_digests(version, opener=urllib.request.urlopen):
    """``{filename: sha256}`` of ``version`` on PyPI, empty when PyPI does not serve it yet."""
    try:
        with opener(f"https://pypi.org/pypi/{PACKAGE}/{version}/json", timeout=30) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return {}
        raise
    return {file["filename"]: file["digests"]["sha256"] for file in data.get("urls", [])}


def github(version, log=print, opener=urllib.request.urlopen):
    tag = check_tag(version)
    _, files = dist_files(version)
    missing = [path.name for path in files if not path.exists()]
    if missing:
        raise ValueError(f"{', '.join(missing)} missing: run 'python tools/release.py build {version}' first")
    online = pypi_digests(version, opener)
    if not online:
        raise ValueError(f"PyPI does not serve {PACKAGE} {version} yet: upload it, or wait a minute")
    for path in files:
        if online.get(path.name) != sha256(path):
            raise ValueError(f"{path.name} on PyPI differs from the local build: do not attach other files")
    notes = release_notes(tagged_file(tag, "CHANGELOG.md"), version)
    with tempfile.NamedTemporaryFile("w", suffix=".md", encoding="utf-8", delete=False) as file:
        file.write(notes)
    subprocess.run(["gh", "release", "create", tag, "--title", f"{PACKAGE} {version}", "--notes-file", file.name,
                    "--verify-tag", *map(str, files)], cwd=ROOT, check=True)
    Path(file.name).unlink()
    log(f"GitHub release {tag} created; PyPI: https://pypi.org/project/{PACKAGE}/{version}/")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("step", choices=["build", "github"], help="build the files, or create the GitHub release")
    parser.add_argument("version", help="the version to publish, such as 0.7.1")
    args = parser.parse_args(argv)
    try:
        (build if args.step == "build" else github)(args.version)
    except (ValueError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
