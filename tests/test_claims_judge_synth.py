import json
from dataclasses import dataclass

import pytest

from motherlode.claims import Claim, Verdict, check_claims, faithfulness_report
from motherlode.grading import build_grading_tool, rubric_hash
from motherlode.judge import adjudication_template, validate_judge
from motherlode.synth import MineSpec, ScriptedTeacher, mine, pan


@dataclass
class ScoreChecker:
    name: str = "score"
    kinds: frozenset = frozenset({"score"})

    def verify(self, claim: Claim, context) -> Verdict:
        ok = context["scores"].get(claim.data["team"]) == claim.data["points"]
        return Verdict(claim.id, "verified" if ok else "refuted", self.name)


def test_check_claims_dispatches_and_leaves_unknown_unresolved():
    ctx = {"scores": {"KC": 27}}
    claims = [
        Claim("c1", "score", "KC scored 27", {"team": "KC", "points": 27}, item_id="g1"),
        Claim("c2", "score", "KC scored 24", {"team": "KC", "points": 24}, item_id="g1"),
        Claim("c3", "weather", "it rained", {}, item_id="g1"),
    ]
    v = check_claims(claims, [ScoreChecker()], ctx)
    assert [x.status for x in v] == ["verified", "refuted", "unresolved"]
    rep = faithfulness_report({"g1": v}, n_boot=50)
    assert rep["overall"]["claims"] == 3
    assert rep["overall"]["verified"] == pytest.approx(1 / 3)


def test_faithfulness_by_group():
    v_en = [Verdict("a", "verified", "x"), Verdict("b", "verified", "x")]
    v_cs = [Verdict("c", "refuted", "x"), Verdict("d", "verified", "x")]
    rep = faithfulness_report({"i1": v_en, "i2": v_cs}, n_boot=50, by={"i1": "en", "i2": "cs"})
    assert rep["by_group"]["en"]["verified"] == pytest.approx(1.0)
    assert rep["by_group"]["cs"]["verified"] == pytest.approx(0.5)


def test_validate_judge_reports_blind_kappa_and_reveal_shift():
    human = []
    judge = []
    labels = ["sound", "unsupported"]
    for i in range(40):
        h = labels[i % 2]
        j = h if i % 5 else labels[(i + 1) % 2]   # judge disagrees on every fifth item
        human.append({"item_id": f"i{i}", "rater": "z", "label": h, "rubric_hash": "abc", "pass": "blind"})
        judge.append({"item_id": f"i{i}", "rater": "judge", "label": j, "rubric_hash": "abc", "pass": "blind"})
        if i % 5 == 0:  # after the reveal the human moves toward the judge on half of those
            human.append({"item_id": f"i{i}", "rater": "z", "label": j if i % 10 == 0 else h, "rubric_hash": "abc", "pass": "revealed"})
    rep = validate_judge(human, judge, n_boot=100)
    assert rep["n"] == 40 and rep["rubric_consistent"]
    assert 0.5 < rep["kappa"] < 0.7
    assert rep["after_reveal"]["items"] == 8
    assert rep["after_reveal"]["moved_toward_judge"] == pytest.approx(0.5)
    adj = adjudication_template(human, judge)
    assert len(adj) == 8 and all(r["verdict"] == "" for r in adj)


def test_validate_judge_gives_human_human_alpha_with_second_rater():
    human = [{"item_id": f"i{i}", "rater": "z", "label": "a" if i % 2 else "b", "pass": "blind"} for i in range(20)]
    human += [{"item_id": f"i{i}", "rater": "friend", "label": "a" if i % 2 else "b", "pass": "blind"} for i in range(10)]
    judge = [{"item_id": f"i{i}", "rater": "judge", "label": "a" if i % 2 else "b", "pass": "blind"} for i in range(20)]
    rep = validate_judge(human, judge, human_rater="z", n_boot=50)
    assert rep["human_human"]["alpha_nominal"] == pytest.approx(1.0)


def test_mine_writes_paydirt_and_tailings_and_resumes(tmp_path):
    items = [{"id": "a", "n": 1}, {"id": "b", "n": 2}, {"id": "c", "n": 3}]
    teacher = ScriptedTeacher(responses={"say 2 in cs": "dva"}, default="one")
    spec = MineSpec(
        name="numbers",
        items=items,
        prompt="say {n} in {language}",
        parse=lambda t: {"word": t.strip()},
        checks=[("nonempty", lambda s: (bool(s["word"]), "empty")), ("not_one", lambda s: (s["word"] != "one", "said one"))],
        languages=["cs"],
    )
    rec = mine(spec, teacher, tmp_path)
    assert rec["counts"] == {"paydirt": 1, "tailings": 2, "skipped": 0}
    pay = [json.loads(l) for l in (tmp_path / "paydirt.jsonl").read_text().splitlines()]
    assert pay[0]["word"] == "dva" and pay[0]["spec_hash"] == spec.spec_hash()
    tails = [json.loads(l) for l in (tmp_path / "tailings.jsonl").read_text().splitlines()]
    assert all(t["reason"].startswith("not_one") for t in tails)
    rec2 = mine(spec, teacher, tmp_path)
    assert rec2["counts"]["skipped"] == 3 and teacher.calls == 3
    out = pan(tmp_path / "tailings.jsonl", tmp_path / "re", checks=[("nonempty", lambda s: (bool(s["word"]), "empty"))])
    assert out == {"paydirt": 2, "tailings": 0}


def test_grading_tool_embeds_hash_and_hides_judge_fields(tmp_path):
    items = [
        {"id": "r1", "text": "Box now, the undercut is open.", "fact_sheet": "gap ahead 1.9 s", "judge_label": "sound", "judge_rationale": "window open"},
        {"id": "r2", "text": "Stay out.", "fact_sheet": "gap ahead 12 s", "judge_label": "unsupported", "judge_rationale": "no threat"},
    ]
    rubric = "sound: the mechanism applies.\nunsupported: it does not."
    out = build_grading_tool(items, rubric, tmp_path / "g.html", labels=["sound", "unsupported"],
                             context_keys=["fact_sheet"], hidden_keys=["judge_label", "judge_rationale"], rater="z")
    doc = out.read_text(encoding="utf-8")
    assert rubric_hash(rubric) in doc
    assert "gap ahead 1.9 s" in doc
    assert "window open" not in doc and "no threat" not in doc  # hidden fields are encoded, not in plain text
