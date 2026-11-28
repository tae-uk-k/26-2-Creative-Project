import asyncio
import json
import os
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
import respx
from pydantic import BaseModel

from seelo.config import get_settings
from seelo.integrations.llm import LlmError
from seelo.integrations.local_cli import LocalCliClient
from seelo.local_ai.runner import CliRunner, communicate_bounded, parse_events
from seelo.local_ai.server import create_app

TOKEN = "test-bridge-token-with-more-than-32-characters"
MODEL = "codex-cli/gpt-6.1-sol"


def events(*items):
    return "\n".join(json.dumps(i) for i in items)


def codex_answer(output, *, search=True):
    result = []
    if search:
        result.append({"type": "item.completed", "item": {"type": "web_search"}})
    result += [
        {"type": "item.completed", "item": {"type": "reasoning", "text": "DO NOT STORE"}},
        {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(output)}},
        {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}},
    ]
    return events(*result)


@pytest.fixture(autouse=True)
def local_settings(monkeypatch):
    monkeypatch.setenv("LOCAL_AI_TOKEN", TOKEN)
    monkeypatch.setenv("LOCAL_AI_SOCKET", "")
    monkeypatch.setenv("LOCAL_AI_URL", "http://127.0.0.1:18765")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_cli_parser_requires_real_search_and_discards_reasoning():
    data = parse_events(codex_answer({"text": "answer", "sources": []}), "openai", MODEL, web=True)
    assert data["search_calls"] == 1
    assert "DO NOT STORE" not in json.dumps(data)
    with pytest.raises(LlmError, match="parse_failed"):
        parse_events(codex_answer({"text": "invented"}, search=False), "openai", MODEL, web=True)


@pytest.mark.parametrize("kind", ["command_execution", "file_change", "mcp_tool_call"])
def test_unexpected_local_tools_fail_closed(kind):
    with pytest.raises(LlmError, match="refused"):
        parse_events(events({"type": "item.completed", "item": {"type": kind}}), "openai", MODEL, web=False)


def test_gemini_cannot_be_recorded_as_codex():
    stream = events(
        {"type": "tool_use", "tool_name": "google_web_search"},
        {"type": "message", "role": "assistant", "content": '{"ok":true}'},
        {"type": "result", "status": "success", "stats": {"input_tokens": 4, "output_tokens": 3}},
    )
    data = parse_events(stream, "gemini", "gemini-cli/auto", web=True)
    assert data["model_id"] == "gemini-cli/auto"
    assert data["output"] == {"ok": True}


def test_quota_survives_restart(tmp_path):
    CliRunner(tmp_path, daily_limit=1).reserve()
    with pytest.raises(LlmError, match="rate_limited"):
        CliRunner(tmp_path, daily_limit=1).reserve()


def test_command_uses_argv_and_rejects_unconfigured_model(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCAL_AI_CODEX_EXE", "codex.exe")
    runner = CliRunner(tmp_path)
    command, _, _ = runner.command("openai", MODEL, {"type": "object", "properties": {}}, web=True)
    assert "read-only" in command
    assert 'forced_login_method="chatgpt"' in command
    assert "shell_tool" in command
    assert "--dangerously-bypass-approvals-and-sandbox" not in command
    assert "--ignore-rules" not in command
    with pytest.raises(LlmError, match="not_configured"):
        runner.command("openai", "other; malicious.exe", {}, web=False)


async def test_bridge_auth_and_origin_are_checked_before_execution():
    runner = AsyncMock()
    app = create_app(runner, TOKEN)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://bridge") as client:
        body = {"provider": "openai", "model": MODEL, "operation": "web", "prompt": "public question"}
        assert (await client.post("/call", json=body)).status_code == 401
        assert (
            await client.post(
                "/call",
                json=body,
                headers={
                    "Authorization": "Bearer " + TOKEN,
                    "Origin": "https://other.example",
                },
            )
        ).status_code == 401
        runner.call.assert_not_called()
        runner.call.return_value = {"model_id": MODEL, "output": {"ok": True}}
        response = await client.post("/call", json=body, headers={"Authorization": "Bearer " + TOKEN})
        assert response.status_code == 200


async def test_bridge_errors_do_not_leak_provider_output():
    runner = AsyncMock()
    runner.call.side_effect = LlmError("gemini", "auth_error")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runner, TOKEN)), base_url="http://bridge"
    ) as client:
        result = await client.post(
            "/call",
            headers={"Authorization": "Bearer " + TOKEN},
            json={
                "provider": "gemini",
                "model": "gemini-cli/auto",
                "operation": "web",
                "prompt": "q",
            },
        )
        assert result.status_code == 503
        assert result.json() == {"error": "auth_error"}


@respx.mock
async def test_adapter_labels_cli_and_rejects_missing_sources():
    reply = {
        "model_id": MODEL,
        "search_calls": 1,
        "output": {
            "text": "Place [1]",
            "sources": [{"url": "https://example.com/place", "title": "place"}],
        },
    }
    route = respx.post("http://127.0.0.1:18765/call").respond(200, json=reply)
    response = await LocalCliClient("openai").web_answer("q", model=MODEL)
    assert response.raw["_seelo"]["transport"] == "local_cli"
    assert response.sources[0]["n"] == 1
    assert route.calls[0].request.headers["Authorization"] == "Bearer " + TOKEN
    reply["output"]["sources"] = []
    route.respond(200, json=reply)
    with pytest.raises(LlmError, match="parse_failed"):
        await LocalCliClient("openai").web_answer("q", model=MODEL)


@respx.mock
async def test_adapter_never_falls_back_to_paid_api():
    respx.post("http://127.0.0.1:18765/call").respond(503, json={"error": "auth_error"})
    with pytest.raises(LlmError, match="auth_error"):
        await LocalCliClient("openai").web_answer("q", model=MODEL)
    assert len(respx.calls) == 1


@respx.mock
async def test_structured_result_is_validated():
    class Output(BaseModel):
        ok: bool

    route = respx.post("http://127.0.0.1:18765/call").respond(
        200,
        json={
            "model_id": MODEL,
            "output": {"ok": True},
        },
    )
    assert (await LocalCliClient("openai").structured("q", Output, model=MODEL)).parsed.ok is True
    route.respond(200, json={"model_id": MODEL, "output": {"wrong": True}})
    with pytest.raises(LlmError, match="parse_failed"):
        await LocalCliClient("openai").structured("q", Output, model=MODEL)


async def test_output_reader_is_bounded():
    class Process:
        stdin = Mock(drain=AsyncMock())
        stdout = asyncio.StreamReader()
        stderr = asyncio.StreamReader()
        wait = AsyncMock(return_value=0)

    process = Process()
    process.stdout.feed_data(b"x" * 4_000_001)
    process.stdout.feed_eof()
    process.stderr.feed_eof()
    with pytest.raises(LlmError, match="parse_failed"):
        await communicate_bounded(process, b"prompt", "openai")


async def test_spawn_receives_prompt_on_stdin_and_not_secret_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCAL_AI_CODEX_EXE", "codex.exe")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-cli")
    monkeypatch.setenv("LOCAL_AI_TOKEN", TOKEN)

    class Process:
        returncode = 0
        stdin = Mock(drain=AsyncMock())
        stdout = asyncio.StreamReader()
        stderr = asyncio.StreamReader()
        wait = AsyncMock(return_value=0)

    process = Process()
    process.stdout.feed_data(codex_answer({"ok": True}, search=False).encode())
    process.stdout.feed_eof()
    process.stderr.feed_eof()
    spawn = AsyncMock(return_value=process)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    result = await CliRunner(tmp_path).call(
        "openai",
        MODEL,
        "x; arbitrary command",
        "structured",
        {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
        },
    )
    assert result["output"] == {"ok": True}
    assert "x; arbitrary command" not in spawn.call_args.args
    assert "OPENAI_API_KEY" not in spawn.call_args.kwargs["env"]
    assert "LOCAL_AI_TOKEN" not in spawn.call_args.kwargs["env"]
    assert os.environ["OPENAI_API_KEY"] == "must-not-reach-cli"
