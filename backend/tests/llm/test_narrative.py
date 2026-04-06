"""
Tests for the LLM narrative layer.

All tests mock the OpenRouter HTTP endpoint with respx — no real API calls.

Coverage:
- OpenRouterClient: correct URL, headers (auth + model hot-swap), payload, response parsing
- narrative.build_prompt: key result fields appear in the user message
- narrative.generate_narrative: returns NarrativeOutput; headline extraction
- narrative._extract_headline: parses ## Headline section; fallback
- API endpoint: 200 with narrative body; 404 no result; 401/403 auth; job_id override
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest
import respx
from httpx import Response

from app.services.llm.client import OPENROUTER_URL, LLMResponse, OpenRouterClient
from app.services.llm.narrative import (
    NarrativeOutput,
    _extract_headline,
    build_prompt,
    generate_narrative,
)
from tests.api.conftest import WORKSPACE_A_ID, WORKSPACE_B_ID, USER_A_ID
from app.models.workspace import AnalysisJob, AnalysisResult, JobStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_MODEL = "anthropic/claude-sonnet-4-5"
MOCK_API_KEY = "test-openrouter-key"

MOCK_NARRATIVE_BODY = """\
## Headline
**The geo split test confirms a statistically significant 15% revenue lift.**

## What We Measured
We ran a geo split test across 50 markets measuring weekly revenue.

## Results
- TWFE estimate: 15.0% lift (p = 0.0200)
- 95% confidence interval: 8.0%–22.0%
- Simple DiD cross-check: 14.0% (closely aligned)

## Incrementality
- Best estimate: $117,500 in incremental revenue
- ROAS: 1.80x – 2.35x – 2.90x (conservative / mid / optimistic)

## Data Quality Notes
- Parallel trends: PASSED ✓
- Causally clean: Yes
- Statistical power: 85% (adequate)

## Recommendation
Increase media investment in this channel by 20% in the next quarter.
"""

MOCK_OPENROUTER_RESPONSE = {
    "id": "gen-abc123",
    "model": MOCK_MODEL,
    "choices": [{"message": {"role": "assistant", "content": MOCK_NARRATIVE_BODY}}],
    "usage": {"prompt_tokens": 320, "completion_tokens": 210},
}

SAMPLE_RESULT = {
    "twfe_treatment_effect": 0.15,
    "twfe_treatment_effect_dollars": 120_000.0,
    "twfe_p_value": 0.02,
    "twfe_ci_95": {"lower": 0.08, "upper": 0.22},
    "simple_did_estimate": 0.14,
    "simple_did_dollars": 115_000.0,
    "incremental_revenue_midpoint": 117_500.0,
    "incremental_revenue_weighted": 116_000.0,
    "roas_low": 1.80,
    "roas_mid": 2.35,
    "roas_high": 2.90,
    "total_spend": 50_000.0,
    "parallel_trends_passes": True,
    "parallel_trends_flag": None,
    "is_causally_clean": True,
    "power_analysis_json": {
        "power": 0.85,
        "is_adequately_powered": True,
        "warning_message": None,
    },
}


def _mock_client(model: str = MOCK_MODEL) -> OpenRouterClient:
    return OpenRouterClient(
        api_key=MOCK_API_KEY,
        model=model,
        site_url="https://test.example.com",
        site_name="Test",
    )


# ---------------------------------------------------------------------------
# OpenRouterClient unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_client_posts_to_openrouter_url():
    route = respx.post(OPENROUTER_URL).mock(
        return_value=Response(200, json=MOCK_OPENROUTER_RESPONSE)
    )
    client = _mock_client()
    await client.chat([{"role": "user", "content": "Hello"}])
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_client_sends_bearer_auth():
    respx.post(OPENROUTER_URL).mock(
        return_value=Response(200, json=MOCK_OPENROUTER_RESPONSE)
    )
    client = _mock_client()
    await client.chat([{"role": "user", "content": "Hello"}])
    request = respx.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {MOCK_API_KEY}"


@pytest.mark.asyncio
@respx.mock
async def test_client_sends_model_in_payload():
    respx.post(OPENROUTER_URL).mock(
        return_value=Response(200, json=MOCK_OPENROUTER_RESPONSE)
    )
    custom_model = "openai/gpt-4o"
    client = _mock_client(model=custom_model)
    await client.chat([{"role": "user", "content": "Hello"}])

    request = respx.calls.last.request
    payload = json.loads(request.content)
    assert payload["model"] == custom_model


@pytest.mark.asyncio
@respx.mock
async def test_client_returns_content_string():
    respx.post(OPENROUTER_URL).mock(
        return_value=Response(200, json=MOCK_OPENROUTER_RESPONSE)
    )
    client = _mock_client()
    result = await client.chat([{"role": "user", "content": "Hello"}])
    assert isinstance(result, LLMResponse)
    assert "15% revenue lift" in result.content


@pytest.mark.asyncio
@respx.mock
async def test_client_parses_token_usage():
    respx.post(OPENROUTER_URL).mock(
        return_value=Response(200, json=MOCK_OPENROUTER_RESPONSE)
    )
    client = _mock_client()
    result = await client.chat([{"role": "user", "content": "Hello"}])
    assert result.prompt_tokens == 320
    assert result.completion_tokens == 210


@pytest.mark.asyncio
@respx.mock
async def test_client_raises_on_non_200():
    respx.post(OPENROUTER_URL).mock(
        return_value=Response(401, json={"error": "Invalid API key"})
    )
    client = _mock_client()
    with pytest.raises(Exception):
        await client.chat([{"role": "user", "content": "Hello"}])


@pytest.mark.asyncio
@respx.mock
async def test_model_is_hot_swappable():
    """Different model slugs go out in the payload without code changes."""
    models_to_test = [
        "google/gemini-2.0-flash",
        "meta-llama/llama-3.1-8b-instruct",
        "openai/o3-mini",
    ]
    for model in models_to_test:
        respx.post(OPENROUTER_URL).mock(
            return_value=Response(200, json={**MOCK_OPENROUTER_RESPONSE, "model": model})
        )
        client = _mock_client(model=model)
        result = await client.chat([{"role": "user", "content": "test"}])
        assert result.model == model


# ---------------------------------------------------------------------------
# build_prompt tests
# ---------------------------------------------------------------------------


def test_build_prompt_returns_system_and_user_messages():
    messages = build_prompt(SAMPLE_RESULT)
    roles = [m["role"] for m in messages]
    assert roles == ["system", "user"]


def test_build_prompt_includes_twfe_lift():
    messages = build_prompt(SAMPLE_RESULT)
    user_content = messages[1]["content"]
    assert "15.0%" in user_content


def test_build_prompt_includes_p_value():
    messages = build_prompt(SAMPLE_RESULT)
    user_content = messages[1]["content"]
    assert "0.0200" in user_content


def test_build_prompt_includes_roas_range():
    messages = build_prompt(SAMPLE_RESULT)
    user_content = messages[1]["content"]
    assert "1.80" in user_content
    assert "2.35" in user_content
    assert "2.90" in user_content


def test_build_prompt_parallel_trends_passed():
    messages = build_prompt(SAMPLE_RESULT)
    assert "PASSED" in messages[1]["content"]


def test_build_prompt_parallel_trends_failed():
    failing = {**SAMPLE_RESULT, "parallel_trends_passes": False, "parallel_trends_flag": "Pre-trend slope detected"}
    messages = build_prompt(failing)
    assert "FAILED" in messages[1]["content"]
    assert "Pre-trend slope detected" in messages[1]["content"]


def test_build_prompt_no_roas_when_no_spend():
    no_roas = {**SAMPLE_RESULT, "roas_low": None, "roas_mid": None, "roas_high": None, "total_spend": None}
    messages = build_prompt(no_roas)
    assert "Not computed" in messages[1]["content"]


def test_build_prompt_power_warning_included():
    underpowered = {
        **SAMPLE_RESULT,
        "power_analysis_json": {
            "power": 0.45,
            "is_adequately_powered": False,
            "warning_message": "Recommend 4 more test weeks",
        },
    }
    messages = build_prompt(underpowered)
    assert "Recommend 4 more test weeks" in messages[1]["content"]
    assert "UNDERPOWERED" in messages[1]["content"]


# ---------------------------------------------------------------------------
# _extract_headline tests
# ---------------------------------------------------------------------------


def test_extract_headline_parses_section():
    md = "## Headline\n**The test confirmed a 15% lift.**\n\n## What We Measured\n..."
    assert _extract_headline(md) == "The test confirmed a 15% lift."


def test_extract_headline_strips_bold_markers():
    md = "## Headline\n**Bold headline here.**"
    assert _extract_headline(md) == "Bold headline here."


def test_extract_headline_fallback_to_first_line():
    md = "No headline section here.\nSecond line."
    assert _extract_headline(md) == "No headline section here."


def test_extract_headline_empty_string_fallback():
    assert _extract_headline("") == "Analysis complete."


# ---------------------------------------------------------------------------
# generate_narrative integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_generate_narrative_returns_narrative_output():
    respx.post(OPENROUTER_URL).mock(
        return_value=Response(200, json=MOCK_OPENROUTER_RESPONSE)
    )
    client = _mock_client()
    output = await generate_narrative(SAMPLE_RESULT, client)
    assert isinstance(output, NarrativeOutput)


@pytest.mark.asyncio
@respx.mock
async def test_generate_narrative_headline_extracted():
    respx.post(OPENROUTER_URL).mock(
        return_value=Response(200, json=MOCK_OPENROUTER_RESPONSE)
    )
    client = _mock_client()
    output = await generate_narrative(SAMPLE_RESULT, client)
    assert "15% revenue lift" in output.headline


@pytest.mark.asyncio
@respx.mock
async def test_generate_narrative_body_contains_sections():
    respx.post(OPENROUTER_URL).mock(
        return_value=Response(200, json=MOCK_OPENROUTER_RESPONSE)
    )
    client = _mock_client()
    output = await generate_narrative(SAMPLE_RESULT, client)
    assert "## Results" in output.body_markdown
    assert "## Recommendation" in output.body_markdown


@pytest.mark.asyncio
@respx.mock
async def test_generate_narrative_records_model():
    respx.post(OPENROUTER_URL).mock(
        return_value=Response(200, json=MOCK_OPENROUTER_RESPONSE)
    )
    client = _mock_client()
    output = await generate_narrative(SAMPLE_RESULT, client)
    assert output.model == MOCK_MODEL


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


async def _seed_completed_job_and_result(db_session, test_id: str, workspace_id: uuid.UUID) -> str:
    job = AnalysisJob(
        test_id=uuid.UUID(test_id),
        workspace_id=workspace_id,
        triggered_by=USER_A_ID,
        status=JobStatus.COMPLETED,
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.flush()

    result = AnalysisResult(
        job_id=job.id,
        test_id=uuid.UUID(test_id),
        workspace_id=workspace_id,
        parallel_trends_passes=True,
        parallel_trends_p_value=0.45,
        twfe_treatment_effect=0.15,
        twfe_treatment_effect_dollars=120_000.0,
        twfe_p_value=0.02,
        twfe_ci_95={"lower": 0.08, "upper": 0.22},
        simple_did_estimate=0.14,
        simple_did_dollars=115_000.0,
        incremental_revenue_midpoint=117_500.0,
        incremental_revenue_weighted=116_000.0,
        roas_low=1.80,
        roas_mid=2.35,
        roas_high=2.90,
        total_spend=50_000.0,
        power_analysis_json={"power": 0.85, "is_adequately_powered": True},
    )
    db_session.add(result)
    await db_session.commit()
    return str(job.id)


def _mock_llm_client_override():
    """Returns a dependency override that injects a pre-configured mock client."""
    from app.api.routes.narrative import get_llm_client

    def _override() -> OpenRouterClient:
        return _mock_client()

    return get_llm_client, _override


def test_narrative_endpoint_unauthenticated_returns_401(client_unauthenticated):
    tid = uuid.uuid4()
    r = client_unauthenticated.post(f"/api/tests/{tid}/narrative", json={})
    assert r.status_code == 401


def test_narrative_endpoint_cross_workspace_returns_403(client_a, client_b):
    # client_b creates the test, client_a tries to narrate it
    r = client_b.post("/api/tests/", json={"name": "B's Test"})
    tid = r.json()["id"]
    resp = client_a.post(f"/api/tests/{tid}/narrative", json={})
    assert resp.status_code == 403


def test_narrative_endpoint_no_completed_job_returns_404(client_a):
    r = client_a.post("/api/tests/", json={"name": "No Analysis Test"})
    tid = r.json()["id"]
    resp = client_a.post(f"/api/tests/{tid}/narrative", json={})
    assert resp.status_code == 404


def test_narrative_endpoint_nonexistent_test_returns_404(client_a):
    resp = client_a.post(f"/api/tests/{uuid.uuid4()}/narrative", json={})
    assert resp.status_code == 404


@pytest.mark.asyncio
@respx.mock
async def test_narrative_endpoint_returns_200_with_headline(client_a, db_session):
    from app.main import app
    from app.api.routes.narrative import get_llm_client

    respx.post(OPENROUTER_URL).mock(
        return_value=Response(200, json=MOCK_OPENROUTER_RESPONSE)
    )

    r = client_a.post("/api/tests/", json={"name": "Narrative Test"})
    tid = r.json()["id"]
    await _seed_completed_job_and_result(db_session, tid, WORKSPACE_A_ID)

    # Override LLM dependency so tests don't need a real API key
    app.dependency_overrides[get_llm_client] = lambda: _mock_client()
    try:
        resp = client_a.post(f"/api/tests/{tid}/narrative", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "headline" in data
        assert "body_markdown" in data
        assert data["model"] == MOCK_MODEL
        assert data["test_id"] == tid
    finally:
        app.dependency_overrides.pop(get_llm_client, None)


@pytest.mark.asyncio
@respx.mock
async def test_narrative_endpoint_specific_job_id(client_a, db_session):
    from app.main import app
    from app.api.routes.narrative import get_llm_client

    respx.post(OPENROUTER_URL).mock(
        return_value=Response(200, json=MOCK_OPENROUTER_RESPONSE)
    )

    r = client_a.post("/api/tests/", json={"name": "Job ID Narrative Test"})
    tid = r.json()["id"]
    job_id = await _seed_completed_job_and_result(db_session, tid, WORKSPACE_A_ID)

    app.dependency_overrides[get_llm_client] = lambda: _mock_client()
    try:
        resp = client_a.post(f"/api/tests/{tid}/narrative", json={"job_id": job_id})
        assert resp.status_code == 200
        assert resp.json()["job_id"] == job_id
    finally:
        app.dependency_overrides.pop(get_llm_client, None)


@pytest.mark.asyncio
@respx.mock
async def test_narrative_endpoint_nonexistent_job_id_returns_404(client_a, db_session):
    from app.main import app
    from app.api.routes.narrative import get_llm_client

    r = client_a.post("/api/tests/", json={"name": "Bad Job ID Test"})
    tid = r.json()["id"]
    await _seed_completed_job_and_result(db_session, tid, WORKSPACE_A_ID)

    app.dependency_overrides[get_llm_client] = lambda: _mock_client()
    try:
        resp = client_a.post(
            f"/api/tests/{tid}/narrative",
            json={"job_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_llm_client, None)


@pytest.mark.asyncio
@respx.mock
async def test_narrative_endpoint_token_counts_in_response(client_a, db_session):
    from app.main import app
    from app.api.routes.narrative import get_llm_client

    respx.post(OPENROUTER_URL).mock(
        return_value=Response(200, json=MOCK_OPENROUTER_RESPONSE)
    )

    r = client_a.post("/api/tests/", json={"name": "Token Count Test"})
    tid = r.json()["id"]
    await _seed_completed_job_and_result(db_session, tid, WORKSPACE_A_ID)

    app.dependency_overrides[get_llm_client] = lambda: _mock_client()
    try:
        resp = client_a.post(f"/api/tests/{tid}/narrative", json={})
        data = resp.json()
        assert data["prompt_tokens"] == 320
        assert data["completion_tokens"] == 210
    finally:
        app.dependency_overrides.pop(get_llm_client, None)
