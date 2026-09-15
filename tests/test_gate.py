"""The gate end to end on a toy dataset: items in, pool, scores, handpick, prospect, paydirt."""
import json
import math
from pathlib import Path

import pytest

from motherlode import cli, survey as assay
from motherlode.dataset import read_dataset, read_jsonl, truth_rows, write_dataset
from motherlode.grading import build_grading_tool
from motherlode.judge import adjudication_template, validate, validate_judge
from motherlode.rubric import load_rubric, parse_scores, rubric_hash, single_label_spec, spec_from_dict
from motherlode.stats import weighted_kappa

SPEC = {"dimensions": [
    {"id": "D1", "name": "Success", "scale": ["0", "1"], "ordinal": True, "na_allowed": False},
    {"id": "D2", "name": "Economy", "scale": ["0", "1", "2"], "ordinal": True, "na_allowed": True},
]}
RUBRIC = "# Toy rubric\n\nD1: did it work. D2: was it wasteful; NA when nothing could be wasted.\n"


def make_items_dataset(tmp_path: Path, n: int = 6):
    items = [{"id": f"it{i}", "text": f"item {i} does thing {i % 2}", "truth": {"D1": str(i % 2)},
              "packet": f"long packet {i}", "meta": {"group": "a" if i < 3 else "b"}} for i in range(n)]
    return write_dataset(tmp_path / "items", "toy-items", "items-v1", items=items,
                         files={"rubric.md": RUBRIC, "rubric.json": json.dumps(SPEC)}, producer="test")


def test_dataset_roundtrip_and_verification(tmp_path):
    ds = make_items_dataset(tmp_path)
    again = read_dataset(ds.path)
    assert again.hash == ds.hash and again.schema == "items-v1" and len(again.items()) == 6
    assert again.rubric().hash == rubric_hash(RUBRIC, spec_from_dict(SPEC))
    (ds.path / "items.jsonl").write_text("tampered\n")
    with pytest.raises(ValueError):
        read_dataset(ds.path)
    with pytest.raises(ValueError):
        write_dataset(tmp_path / "bad", "x", "items-v1", items=[{"id": "1"}])


def test_rubric_spec_and_parser():
    spec = spec_from_dict(SPEC, RUBRIC)
    assert spec.ids == ["D1", "D2"] and spec.dimension("D2").labels() == ["0", "1", "2", "NA"]
    assert rubric_hash(RUBRIC) != spec.hash                       # the spec is part of the hash
    s = parse_scores('sure: {"D1": {"score": 1, "rationale": "done"}, "D2": {"score": "na"}}', spec)
    assert s["D1"] == {"label": "1", "rationale": "done"} and s["D2"]["label"] == "NA"
    with pytest.raises(ValueError):
        parse_scores('{"D1": "NA", "D2": 1}', spec)
    with pytest.raises(ValueError):
        parse_scores('{"D1": 3, "D2": 1}', spec)
    single = single_label_spec(["sound", "vacuous"])
    assert single.ids == ["label"] and single.dimension("label").check("sound") == "sound"


def test_pool_and_survey(tmp_path):
    ds = make_items_dataset(tmp_path)
    ws = tmp_path / "ws"
    m = assay.pool(ds, ws)
    assert len(m["keys"]) == 6 and all(len(k) == 8 for k in m["keys"])
    assert m["keys"] == assay.pool(ds, tmp_path / "ws2")["keys"]     # deterministic
    key = next(iter(m["keys"]))
    assert (ws / "pool" / f"{key}.md").read_text().startswith("item ")
    rows = assay.record(ws, key, "judge-a", '{"D1": {"score": 1, "rationale": "r"}, "D2": {"score": "NA"}}')
    assert {r["dimension"] for r in rows} == {"D1", "D2"} and rows[0]["item_id"] == m["keys"][key]
    assert rows[0]["rubric_hash"] == ds.rubric().hash and rows[0]["key"] == key
    assert assay.scored_keys(ws) == {key}
    with pytest.raises(KeyError):
        assay.record(ws, "nope", "j", "{}")
    # a changed rubric is refused
    (ds.path / "rubric.md").write_text(RUBRIC + "changed\n")
    with pytest.raises(ValueError):
        assay.record(ws, key, "judge-a", "{}")


def test_handpick_multi_dimension(tmp_path):
    ds = make_items_dataset(tmp_path)
    spec = ds.rubric()
    items = ds.items()
    for it in items:
        it["judge_D1"] = "1: fine"
        it["judge_D2"] = "NA: nothing to waste"
    out = build_grading_tool(items, spec, tmp_path / "grade.html", context_keys=["packet"],
                             hidden_prefix="judge_", rater="z", title="toy", seed=3)
    html = out.read_text()
    assert spec.hash in html and '"dimensions": [' in html and "long packet 1" in html
    assert "nothing to waste" not in html                          # hidden, encoded
    assert "Glossary" in html and "Mechanism" not in html
    # single-label path still works
    out2 = build_grading_tool([{"id": "a", "text": "x"}], "rubric text", tmp_path / "s.html", labels=["good", "bad"])
    assert '"id": "label"' in out2.read_text()


def test_weighted_kappa_reference():
    scale = ["0", "1", "2"]
    a = ["0", "1", "2", "2", "1", "0"]
    assert weighted_kappa(a, a, scale) == pytest.approx(1.0)
    b = ["0", "1", "2", "1", "1", "0"]                              # one step off once
    c = ["0", "1", "2", "0", "1", "0"]                              # two steps off once
    assert weighted_kappa(a, b, scale, "quadratic") > weighted_kappa(a, c, scale, "quadratic")
    assert math.isnan(weighted_kappa(["1"] * 4, ["1"] * 4, scale))
    with pytest.raises(ValueError):
        weighted_kappa(["3"], ["0"], scale)


def test_prospect_per_dimension_with_truth_and_reveal(tmp_path):
    ds = make_items_dataset(tmp_path, 8)
    spec = ds.rubric()
    rh = spec.hash
    judge = []
    human = []
    for i, it in enumerate(ds.items()):
        d1 = it["truth"]["D1"]
        judge += [{"item_id": it["id"], "rater": "judge", "dimension": "D1", "label": d1, "rubric_hash": rh},
                  {"item_id": it["id"], "rater": "judge", "dimension": "D2", "label": "NA" if i == 0 else str(i % 3), "rubric_hash": rh}]
        human += [{"item_id": it["id"], "rater": "z", "dimension": "D1", "label": d1 if i != 7 else ("0" if d1 == "1" else "1"), "rubric_hash": rh, "pass": "blind"},
                  {"item_id": it["id"], "rater": "z", "dimension": "D2", "label": str(i % 3), "rubric_hash": rh, "pass": "blind"}]
    human.append({"item_id": "it7", "rater": "z", "dimension": "D1", "label": ds.items()[7]["truth"]["D1"], "rubric_hash": rh, "pass": "revealed"})
    rep = validate(human, judge, spec, truth_rows=truth_rows(ds.items(), rh), n_boot=200)
    d1 = rep["dimensions"]["D1"]
    assert d1["human_vs_judge"]["n"] == 8 and d1["human_vs_judge"]["kappa"] < 1
    assert d1["judge_vs_truth"]["kappa"] == pytest.approx(1.0)
    assert d1["human_vs_judge"]["after_reveal"]["moved_toward_judge"] == 1.0
    d2 = rep["dimensions"]["D2"]
    assert d2["human_vs_judge"]["na_excluded"] == 1 and d2["human_vs_judge"]["n"] == 7
    assert "weighted_kappa_linear" in d2["human_vs_judge"]
    assert rep["rubric_consistent"] and rep["judge_rater"] == "judge"
    adj = adjudication_template(human, judge)
    assert [(r["item_id"], r["dimension"], r["kind"]) for r in adj] == [("it7", "D1", "label"), ("it0", "D2", "applicability")]
    # single-label files through the v0.1 entry point
    h = [{"item_id": "1", "rater": "z", "label": "a", "rubric_hash": "x"}, {"item_id": "2", "rater": "z", "label": "b", "rubric_hash": "x"}]
    j = [{"item_id": "1", "rater": "j", "label": "a"}, {"item_id": "2", "rater": "j", "label": "a"}]
    old = validate_judge(h, j, n_boot=50)
    assert old["n"] == 2 and "kappa" in old and old["rubric_consistent"]


def test_cli_end_to_end(tmp_path, capsys, monkeypatch):
    ds = make_items_dataset(tmp_path, 4)
    ws = tmp_path / "ws"
    cli.main(["pool", "--dataset", str(ds.path), "--out", str(ws)])
    keys = json.loads((ws / "manifest.json").read_text())["keys"]
    for key, item_id in keys.items():
        d1 = next(it for it in ds.items() if it["id"] == item_id)["truth"]["D1"]
        cli.main(["survey", "--pool", str(ws), "--key", key, "--rater", "judge",
                  "--scores", json.dumps({"D1": {"score": d1, "rationale": "ok"}, "D2": {"score": "1"}})])
    cli.main(["handpick", "--dataset", str(ds.path), "--pool", str(ws), "--out", str(tmp_path / "g.html"),
              "--context", "packet", "--rater", "z", "--title", "toy"])
    assert "1: ok" not in (tmp_path / "g.html").read_text()
    human = tmp_path / "labels-z.jsonl"
    human.write_text("".join(json.dumps({"item_id": it["id"], "rater": "z", "dimension": d, "label": it["truth"]["D1"] if d == "D1" else "1",
                                          "rubric_hash": ds.rubric().hash, "pass": "blind"}) + "\n"
                             for it in ds.items() for d in ("D1", "D2")))
    cli.main(["prospect", "--dataset", str(ds.path), "--human", str(human), "--judge", str(ws / "judgments.jsonl"),
              "--adjudication", str(tmp_path / "adj.jsonl")])
    out = capsys.readouterr().out
    assert "D1" in out and "D2" in out
    cli.main(["paydirt", "--dataset", str(ds.path), "--pool", str(ws), "--human", str(human), "--out", str(tmp_path / "graded")])
    g = read_dataset(tmp_path / "graded")
    assert g.schema == "graded-v1" and g.manifest["sources"][0]["dataset_sha256"] == ds.hash
    assert (g.path / "validation.json").exists() and (g.path / "labels" / "labels-z.jsonl").exists()
    assert len(read_jsonl(g.path / "truth.jsonl")) == 4


def test_dataset_seal_and_verify_cli(tmp_path, capsys):
    d = tmp_path / "raw"
    d.mkdir()
    (d / "items.jsonl").write_text(json.dumps({"id": "a", "text": "line one\nline two", "truth": {"D1": "1"}}) + "\n")
    (d / "rubric.md").write_text(RUBRIC)
    (d / "rubric.json").write_text(json.dumps(SPEC))
    cli.main(["dataset", "seal", str(d), "--name", "raw", "--schema", "items-v1", "--producer", "test",
              "--source", "snapshot=abc123", "--meta", '{"note": 1}'])
    ds = read_dataset(d)
    assert set(ds.manifest["files"]) == {"items.jsonl", "rubric.md", "rubric.json"}
    assert ds.manifest["sources"] == [{"name": "snapshot", "dataset_sha256": "abc123"}] and ds.manifest["meta"] == {"note": 1}
    assert cli.main(["dataset", "verify", str(d)]) == 0
    (d / "rubric.md").write_text("changed")
    assert cli.main(["dataset", "verify", str(d)]) == 1
    # multi-line text renders preformatted in the tool
    out = build_grading_tool(ds.items(), ds.rubric(), tmp_path / "g.html", rater="z")
    assert 'it.text.includes("\\n")' in out.read_text()
