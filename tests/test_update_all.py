"""Running every update script in order, without network."""

import json
import types

import pytest
import update_all

from faker_literature.store import BUILTIN_DATA


@pytest.fixture
def catalogue(tmp_path):
    path = tmp_path / "literature.json"
    data = json.loads(BUILTIN_DATA.read_text(encoding="utf-8"))
    data["authors"] = data["authors"][:3]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _script(calls, name, change=None, fail=False):
    def main(argv):
        calls.append((name, argv))
        path = argv[argv.index("--catalogue") + 1]
        data = json.loads(open(path, encoding="utf-8").read())
        if fail:
            raise ConnectionError("network down")
        if change:
            change(data)
        with open(path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
    return types.SimpleNamespace(main=main)


def _drop_first_publishers(data):
    data["authors"][0]["books"][0]["publisher"] = None


def test_steps_run_in_order_on_a_copy_with_their_cache(catalogue, tmp_path):
    calls = []
    scripts = {"update_series": _script(calls, "series"),
               "update_openlibrary": _script(calls, "openlibrary", _drop_first_publishers)}
    steps = update_all.selected_steps(only=["openlibrary", "series"])

    before, after = update_all.run(catalogue, steps, tmp_path / "cache", load=scripts.__getitem__, log=lambda _: None)

    assert [name for name, _ in calls] == ["series", "openlibrary"]  # the order of STEPS
    assert all(argv[1] != str(catalogue) for _, argv in calls)  # a copy
    assert calls[1][1][2:] == ["--cache", str(tmp_path / "cache" / "openlibrary.json")]
    assert json.loads(catalogue.read_text(encoding="utf-8"))["authors"][0]["books"][0]["publisher"] is None
    assert after["books"] == before["books"]
    assert after["publisher missing (en_US)"] >= before["publisher missing (en_US)"]


def test_a_failing_step_or_a_dry_run_leaves_the_catalogue_untouched(catalogue):
    original = catalogue.read_bytes()
    calls = []
    scripts = {"update_awards": _script(calls, "awards", _drop_first_publishers),
               "update_series": _script(calls, "series", fail=True)}

    with pytest.raises(RuntimeError, match="'series' failed.*not modified"):
        update_all.run(catalogue, update_all.selected_steps(only=["awards", "series"]),
                       load=scripts.__getitem__, log=lambda _: None)
    update_all.run(catalogue, update_all.selected_steps(only=["awards"]), dry_run=True,
                   load=scripts.__getitem__, log=lambda _: None)

    assert catalogue.read_bytes() == original


def test_unknown_steps_are_refused():
    assert [name for name, _, _ in update_all.selected_steps(skip=["bnf", "wikipedia"])][-2:] == [
        "editions", "openlibrary"]
    with pytest.raises(ValueError, match="unknown steps: nope"):
        update_all.selected_steps(only=["nope"])


def test_the_report_lists_what_changed():
    lines = update_all.report({"books": 10, "series": 2}, {"books": 12, "series": 2})
    assert lines == ["  books                              10 ->     12 (+2)"]
    assert update_all.report({"books": 1}, {"books": 1}) == ["  nothing changed"]
