"""Publishing a tagged version by hand, without network."""

import io
import json
import urllib.error

import pytest
import release

CHANGELOG = """# Changelog

## [Non publié]

- Next thing.

## [0.7.1] - 2026-11-20

### Corrigé

- A fix.

## [0.7.0] - 2026-11-18

- Older.

[0.7.1]: https://example.org/v0.7.1
"""


def test_release_notes_are_the_dated_section_only():
    assert release.release_notes(CHANGELOG, "0.7.1") == "### Corrigé\n\n- A fix.\n"
    assert release.release_notes(CHANGELOG, "0.7.0") == "- Older.\n"
    with pytest.raises(ValueError, match=r"no '## \[0.8.0\] - YYYY-MM-DD' section"):
        release.release_notes(CHANGELOG, "0.8.0")
    with pytest.raises(ValueError, match="no"):
        release.release_notes("## [0.9.0]\n\n- Undated.\n", "0.9.0")


def test_package_version_is_read_from_the_package():
    assert release.package_version('"""Doc."""\n__version__ = "0.7.1"\n') == "0.7.1"
    with pytest.raises(ValueError):
        release.package_version("nothing here")


def test_tags_and_versions_are_checked():
    with pytest.raises(ValueError, match="not a version"):
        release.check_tag("v0.7")
    with pytest.raises(ValueError, match="does not exist"):
        release.check_tag("99.0.0")


def _opener(payload=None, status=None):
    def opener(url, timeout):
        if status:
            raise urllib.error.HTTPError(url, status, "Not Found", {}, None)
        return io.BytesIO(json.dumps(payload).encode())
    return opener


def test_pypi_digests_are_read_and_a_missing_version_is_empty():
    payload = {"urls": [{"filename": "faker_literature-0.7.1.tar.gz", "digests": {"sha256": "abc"}}]}
    assert release.pypi_digests("0.7.1", _opener(payload)) == {"faker_literature-0.7.1.tar.gz": "abc"}
    assert release.pypi_digests("0.7.1", _opener(status=404)) == {}
