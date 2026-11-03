"""Unit tests for collectors.openalex_kz. The OpenAlex API is mocked, so no network is needed."""

import json
import os

import pytest

from collectors import common
from collectors import openalex_kz as oa


@pytest.fixture(autouse=True)
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    monkeypatch.delenv("OPENALEX_EMAIL", raising=False)
    os.makedirs(oa.OUT)
    monkeypatch.setattr(oa.time, "sleep", lambda s: None)
    return tmp_path


def write_institutions(ids):
    with open(os.path.join(oa.OUT, "institutions.json"), "w") as f:
        json.dump([{"id": f"https://openalex.org/{i}"} for i in ids], f)


def read_out(name):
    return list(common.read_jsonl(os.path.join(oa.OUT, name)))


# ---------- helpers ----------

def test_short_extracts_id():
    assert oa.short("https://openalex.org/I123") == "I123"
    assert oa.short("A42") == "A42"
    assert oa.short(None) is None
    assert oa.short("") is None


def test_params_without_env():
    assert oa.params(per_page=200) == {"per_page": 200}


def test_params_with_key_and_email(monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "k")
    monkeypatch.setenv("OPENALEX_EMAIL", "me@example.org")
    assert oa.params(a=1) == {"a": 1, "api_key": "k", "mailto": "me@example.org"}


def test_fetch_ok(monkeypatch):
    calls = []

    def fake_get_json(url, params):
        calls.append((url, params))
        return 200, {"results": []}, {}

    monkeypatch.setattr(oa, "get_json", fake_get_json)
    assert oa.fetch("works", page=1) == {"results": []}
    assert calls == [(f"{oa.BASE}/works", {"page": 1})]


def test_fetch_raises_on_error(monkeypatch):
    monkeypatch.setattr(oa, "get_json", lambda url, params: (403, {"error": "forbidden"}, {}))
    with pytest.raises(RuntimeError, match="HTTP 403"):
        oa.fetch("works")



def test_step_institutions_excludes_schools(monkeypatch):
    excluded = next(iter(oa.EXCLUDE))
    results = [{"id": "https://openalex.org/I1"}, {"id": f"https://openalex.org/{excluded}"},
               {"id": "https://openalex.org/I2"}]
    monkeypatch.setattr(oa, "fetch", lambda path, **kw: {"results": results})
    oa.step_institutions()
    assert oa.university_ids() == ["I1", "I2"]


def test_works_paged_splits_large_slices_and_resumes(monkeypatch):
    write_institutions(["I1", "I2", "I3", "I4"])
    monkeypatch.setattr(oa, "YEAR_FROM", 2020)
    monkeypatch.setattr(oa, "YEAR_TO", 2020)
    calls = []

    def fake_fetch(path, filter, page, **kw):
        calls.append((filter, page))
        ids = filter.split(",")[0].split(":")[1].split("|")
        if len(ids) == 4:                      # whole list > 10 000 -> must be split in halves
            return {"meta": {"count": 15000}, "results": []}
        return {"meta": {"count": 250}, "results": [{"id": f"W{ids[0]}-{page}"}]}

    monkeypatch.setattr(oa, "fetch", fake_fetch)
    oa.works_paged()

    assert [w["id"] for w in read_out("works.jsonl")] == ["WI1-1", "WI1-2", "WI3-1", "WI3-2"]
    assert len(calls) == 5                     # 1 (too big) + 2 pages for each half

    calls.clear()
    oa.works_paged()                           # second run: everything is done, but the
    assert len(calls) == 1                     # top slice is re-checked and split again
    assert len(read_out("works.jsonl")) == 4


def test_works_cursor_saves_state(monkeypatch):
    write_institutions(["I1"])
    pages = {"*": ("c2", [{"id": "W1"}, {"id": "W2"}]), "c2": ("c3", [{"id": "W3"}]), "c3": ("c4", [])}
    monkeypatch.setattr(oa, "fetch", lambda path, cursor, **kw: {
        "meta": {"count": 3, "next_cursor": pages[cursor][0]}, "results": pages[cursor][1]})

    oa.works_cursor()
    assert [w["id"] for w in read_out("works.jsonl")] == ["W1", "W2", "W3"]
    state = json.load(open(os.path.join(oa.OUT, "works_state.json")))
    assert state == {"cursor": None, "count": 3, "total": 3}

    oa.works_cursor()                          # already finished -> nothing appended
    assert len(read_out("works.jsonl")) == 3


def test_step_works_chooses_mode(monkeypatch):
    used = []
    monkeypatch.setattr(oa, "works_cursor", lambda: used.append("cursor"))
    monkeypatch.setattr(oa, "works_paged", lambda: used.append("paged"))
    oa.step_works()
    monkeypatch.setenv("OPENALEX_API_KEY", "k")
    oa.step_works()
    assert used == ["paged", "cursor"]


def test_step_authors_only_kz_and_not_downloaded(monkeypatch):
    write_institutions(["I1"])
    common.append_jsonl(os.path.join(oa.OUT, "works.jsonl"), [{"authorships": [
        {"author": {"id": "https://openalex.org/A1"}, "institutions": [{"id": "https://openalex.org/I1"}]},
        {"author": {"id": "https://openalex.org/A2"}, "institutions": [{"id": "https://openalex.org/I1"}]},
        {"author": {"id": "https://openalex.org/A3"}, "institutions": [{"id": "https://openalex.org/I999"}]},
        {"author": {}, "institutions": [{"id": "https://openalex.org/I1"}]},
    ]}])
    common.append_jsonl(os.path.join(oa.OUT, "authors.jsonl"), [{"id": "https://openalex.org/A1"}])
    filters = []

    def fake_fetch(path, filter, **kw):
        filters.append(filter)
        return {"results": [{"id": "https://openalex.org/" + i} for i in filter.split(":")[1].split("|")]}

    monkeypatch.setattr(oa, "fetch", fake_fetch)
    oa.step_authors()
    assert filters == ["openalex:A2"]          # A1 already downloaded, A3 is not from a KZ university
    assert {oa.short(a["id"]) for a in read_out("authors.jsonl")} == {"A1", "A2"}


def test_main_runs_requested_steps(monkeypatch):
    ran = []
    monkeypatch.setattr(oa, "step_institutions", lambda: ran.append("institutions"))
    monkeypatch.setattr(oa, "step_works", lambda: ran.append("works"))
    monkeypatch.setattr(oa, "step_authors", lambda: ran.append("authors"))
    monkeypatch.setattr(oa.sys, "argv", ["openalex_kz", "works", "institutions"])
    oa.main()
    assert ran == ["works", "institutions"]
