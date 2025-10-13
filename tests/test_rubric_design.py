import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

import rubric_design.rubric_design as rubric
from config import LlmRoute
from jd_analysis.jd_analysis import CompetencyArea, CompetencyMatrix


def _route() -> LlmRoute:
    return LlmRoute(
        name="rubric-test",
        base_url="http://example.com",
        endpoint="/llm",
        model="test",
        timeout_s=1.0,
    )


def _anchors() -> list[rubric.RubricAnchor]:
    return [rubric.RubricAnchor(level=index + 1, text=f"Level {index + 1}") for index in range(5)]


def _criteria() -> list[rubric.RubricCriterion]:
    weights = [0.34, 0.33, 0.33]
    names = ["Clarity", "Accuracy", "Experience"]
    return [
        rubric.RubricCriterion(name=name, weight=weight, anchors=_anchors())
        for name, weight in zip(names, weights, strict=True)
    ]


def _rubric(name: str) -> rubric.Rubric:
    return rubric.Rubric(
        competency=name,
        band="4-6",
        band_notes=["note"],
        criteria=_criteria(),
        red_flags=["flag"],
        evidence=["e1", "e2", "e3"],
        min_pass_score=3.4,
    )


def test_build_task_formats_prompt() -> None:
    area = CompetencyArea(name="Backend Development", skills=["HTTP", "Databases", "Resilience"])
    prompt = rubric._build_task(area, "4-6")
    assert prompt.startswith("You are a rubric generator")
    assert '"competency": "Backend Development"' in prompt
    assert '"band": "4-6"' in prompt
    assert prompt.endswith("Guidance for anchors: tailor to band scope; emphasize definitions, when-to-use, trade-offs, failure modes, and concrete examples from experience.")


def test_infer_band_matches_numeric_ranges() -> None:
    assert rubric._infer_band("0-1 years") == "0-1"
    assert rubric._infer_band("Experience: 2-3") == "2-3"
    assert rubric._infer_band("6+ years") == "4-6"
    assert rubric._infer_band("10 years experience") == "7-10"
    assert rubric._infer_band("12+ years") == "10+"
    assert rubric._infer_band("unknown") == "4-6"


def test_coerce_area_tuple_valid_and_invalid() -> None:
    name, skills = rubric._coerce_area_tuple(("Backend", ["API", "Resilience"]))
    assert name == "Backend"
    assert skills == ["API", "Resilience"]
    with pytest.raises(TypeError):
        rubric._coerce_area_tuple(("Backend",))


def test_design_rubrics_generates_and_persists(monkeypatch, tmp_path) -> None:
    areas = [
        CompetencyArea(name="Backend", skills=["API", "Queues", "Resilience"]),
        {"name": "DevOps", "skills": ["CI", "Monitoring", "IaC"]},
        ("Leadership", ["Coaching", "Strategy", "Stakeholders"]),
        CompetencyArea(name="Quality", skills=["Testing", "Reviews", "Automation"]),
        CompetencyArea(name="Security", skills=["Threat Modeling", "OWASP", "Privacy"]),
    ]
    matrix = CompetencyMatrix.model_construct(
        job_title="Staff Engineer",
        experience_years="7-10",
        competency_areas=areas,
    )
    route = _route()
    store_path = tmp_path / "rubrics.sqlite"
    store = rubric.RubricStore(store_path)
    tasks: list[str] = []
    area_names = ["Backend", "DevOps", "Leadership", "Quality", "Security"]

    def fake_call(task: str, schema, *, cfg) -> rubric.Rubric:
        index = len(tasks)
        tasks.append(task)
        assert schema is rubric.Rubric
        assert cfg == route
        assert area_names[index] in task
        return _rubric(area_names[index])

    class DummyUUID:
        hex = "deadbeef"

    monkeypatch.setattr(rubric, "call", fake_call)
    monkeypatch.setattr(rubric, "uuid4", lambda: DummyUUID())
    interview_id = rubric.design_rubrics(
        matrix,
        route=route,
        store=store,
        job_description="Detailed JD",
    )
    assert interview_id == "deadbeef"
    assert len(tasks) == len(area_names)
    snapshot = store.load(interview_id)
    assert snapshot.job_title == "Staff Engineer"
    assert snapshot.experience_years == "7-10"
    assert snapshot.job_description == "Detailed JD"
    assert len(snapshot.rubrics) == len(area_names)
    assert {rubric_obj.competency for rubric_obj in snapshot.rubrics} == set(area_names)

    conn = sqlite3.connect(store_path)
    try:
        cur = conn.execute("SELECT COUNT(*) FROM competency_rubrics")
        assert cur.fetchone()[0] == len(area_names)
    finally:
        conn.close()


def test_design_with_config_and_load(monkeypatch, tmp_path) -> None:
    matrix = CompetencyMatrix(
        job_title="Engineer",
        experience_years="4-6",
        competency_areas=[
            CompetencyArea(name="Backend", skills=["API", "Databases", "Caching"]),
            CompetencyArea(name="Testing", skills=["Unit", "Integration", "Automation"]),
            CompetencyArea(name="Architecture", skills=["Design", "Scaling", "Reliability"]),
            CompetencyArea(name="DevOps", skills=["CI", "Monitoring", "IaC"]),
            CompetencyArea(name="Security", skills=["Threat Modeling", "Encryption", "Privacy"]),
        ],
    )
    route = _route()
    db_path = tmp_path / "rubric.sqlite"
    config_path = tmp_path / "config.json"
    tasks: list[str] = []

    def fake_load_app_registry(path, schemas):
        assert path == config_path
        assert schemas == {"rubric_design.generate_rubric": rubric.Rubric}
        return {"rubric_design.generate_rubric": (route, rubric.Rubric)}

    monkeypatch.setattr(rubric, "load_app_registry", fake_load_app_registry)
    monkeypatch.setattr(
        rubric,
        "call",
        lambda task, schema, *, cfg: tasks.append(task) or _rubric("Backend"),
    )
    interview_id = rubric.design_with_config(
        matrix,
        config_path=config_path,
        db_path=db_path,
        job_description="JD",
    )
    assert len(tasks) == 5
    snapshot = rubric.load_rubrics(interview_id, db_path=db_path)
    assert snapshot.interview_id == interview_id
    assert snapshot.job_title == "Engineer"
    assert snapshot.experience_years == "4-6"
    assert len(snapshot.rubrics) == 5
