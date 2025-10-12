import jd_analysis.jd_analysis as jd_mod
from config import LlmRoute


def _route() -> LlmRoute:
    return LlmRoute(
        name="test",
        base_url="http://example.com",
        endpoint="/llm",
        model="test-model",
        timeout_s=1.0,
    )


def _matrix() -> jd_mod.CompetencyMatrix:
    areas = [
        jd_mod.CompetencyArea(name=f"Area {index}", skills=["Skill A", "Skill B", "Skill C"])
        for index in range(5)
    ]
    return jd_mod.CompetencyMatrix(
        job_title="Senior Engineer",
        experience_years="5-7",
        competency_areas=areas,
    )


def test_build_task_includes_profile_details() -> None:
    profile = jd_mod.JobProfile(
        job_title="Backend Developer",
        job_description="Build APIs and services",
        experience_years="4-6",
    )
    task = jd_mod._build_task(profile)
    assert task.startswith("Analyze the job description")
    assert "Job title: Backend Developer" in task
    assert "Required years of experience: 4-6" in task
    assert "Build APIs and services" in task
    assert task.strip().endswith("Return only JSON without markdown fences, text, or commentary.")


def test_generate_competency_matrix_invokes_gateway(monkeypatch) -> None:
    profile = jd_mod.JobProfile(
        job_title="ML Engineer",
        job_description="Deploy and monitor models",
        experience_years="4-6",
    )
    expected = _matrix()
    route = _route()
    captured: dict[str, object] = {}

    def fake_call(task: str, schema, *, cfg) -> jd_mod.CompetencyMatrix:
        captured["task"] = task
        captured["schema"] = schema
        captured["cfg"] = cfg
        return expected

    monkeypatch.setattr(jd_mod, "call", fake_call)
    result = jd_mod.generate_competency_matrix(profile, route=route)
    assert result is expected
    assert isinstance(captured["task"], str)
    assert captured["schema"] is jd_mod.CompetencyMatrix
    assert captured["cfg"] == route


def test_analyze_with_config_loads_registry(monkeypatch, tmp_path) -> None:
    profile = jd_mod.JobProfile(
        job_title="Data Scientist",
        job_description="Modeling",
        experience_years="2-3",
    )
    matrix = _matrix()
    route = _route()
    registry_key = "jd_analysis.generate_competency_matrix"
    config_path = tmp_path / "config.json"

    def fake_load_app_registry(path, schemas):
        assert path == config_path
        assert schemas == {registry_key: jd_mod.CompetencyMatrix}
        return {registry_key: (route, jd_mod.CompetencyMatrix)}

    def fake_generate(profile_arg, *, route: LlmRoute):
        assert profile_arg is profile
        assert route is route_obj
        return matrix

    route_obj = route
    monkeypatch.setattr(jd_mod, "load_app_registry", fake_load_app_registry)
    monkeypatch.setattr(jd_mod, "generate_competency_matrix", fake_generate)
    result = jd_mod.analyze_with_config(profile, config_path=config_path)
    assert result is matrix
