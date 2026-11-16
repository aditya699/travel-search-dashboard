"""The Claude client and the Power BI publisher, with their network calls mocked."""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from app.clean.schema import CleanBatch
from app.core.errors import LLMRefusalError, PublishError
from app.llm.anthropic_client import FALLBACK_BETA, AnthropicLLM
from app.powerbi.publish import API, publish_pbix


async def test_anthropic_client_sends_structured_request(monkeypatch):
    llm = AnthropicLLM(model="claude-opus-5-5", effort="low", api_key="test-key")
    sent = {}

    async def fake_parse(**kwargs):
        sent.update(kwargs)
        return SimpleNamespace(
            id="msg_1",
            stop_reason="end_turn",
            stop_details=None,
            parsed_output=CleanBatch(records=[]),
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )

    monkeypatch.setattr(llm._client.beta.messages, "parse", fake_parse)
    result = await llm.structured(system="sys", content='{"listings": []}', schema=CleanBatch)
    assert result.records == []
    assert sent["model"] == "claude-opus-5-5"
    assert sent["output_format"] is CleanBatch
    assert sent["output_config"] == {"effort": "low"}
    assert sent["betas"] == [FALLBACK_BETA] and sent["fallbacks"] == "default"
    assert sent["messages"][0]["content"] == '{"listings": []}'


async def test_anthropic_refusal_raises(monkeypatch):
    llm = AnthropicLLM(model="claude-opus-5-5", api_key="test-key")

    async def refuse(**kwargs):
        return SimpleNamespace(
            id="msg_2",
            stop_reason="refusal",
            stop_details=SimpleNamespace(explanation="nope"),
            parsed_output=None,
            usage=None,
        )

    monkeypatch.setattr(llm._client.beta.messages, "parse", refuse)
    with pytest.raises(LLMRefusalError, match="nope"):
        await llm.structured(system="s", content="{}", schema=CleanBatch)


def test_publish_uploads_waits_and_checks_rls(settings, tmp_path):
    pbix = tmp_path / "TravelSearch.pbix"
    pbix.write_bytes(b"PK fake pbix")
    settings = settings.model_copy(
        update={"pbi_workspace_id": "ws-1", "pbi_pbix_path": pbix, "pbi_dataset_name": "Travel"}
    )
    seen = []
    polls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, str(request.url)))
        assert request.headers["authorization"] == "Bearer tok"
        if request.method == "POST":
            assert request.url.params["datasetDisplayName"] == "Travel.pbix"
            assert request.url.params["nameConflict"] == "CreateOrOverwrite"
            assert b"PK fake pbix" in request.content
            return httpx.Response(202, json={"id": "imp-1"})
        if "/imports/" in request.url.path:
            polls["n"] += 1
            if polls["n"] == 1:
                return httpx.Response(200, json={"importState": "Publishing"})
            return httpx.Response(
                200,
                json={
                    "importState": "Succeeded",
                    "datasets": [{"id": "ds-1"}],
                    "reports": [{"id": "rep-1", "webUrl": "https://app.powerbi.com/r/1"}],
                },
            )
        return httpx.Response(200, json={"id": "ds-1", "isEffectiveIdentityRolesRequired": True})

    result = publish_pbix(
        settings,
        "tok",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda s: None,
    )
    assert result.report_url == "https://app.powerbi.com/r/1"
    assert result.rls_roles_detected is True
    assert seen[0][1].startswith(f"{API}/groups/ws-1/imports")


def test_publish_explains_a_403(settings, tmp_path):
    pbix = tmp_path / "x.pbix"
    pbix.write_bytes(b"x")
    settings = settings.model_copy(update={"pbi_workspace_id": "ws", "pbi_pbix_path": pbix})
    transport = httpx.MockTransport(lambda r: httpx.Response(403, text=json.dumps({"e": 1})))
    with pytest.raises(PublishError, match="Member or Admin"):
        publish_pbix(settings, "tok", client=httpx.Client(transport=transport))


def test_publish_needs_a_workspace(settings):
    with pytest.raises(PublishError, match="PBI_WORKSPACE_ID"):
        publish_pbix(settings, "tok")
