from __future__ import annotations

import httpx
import pytest
import respx

from apps.reviews import llm


@respx.mock
def test_nim_llm_request_and_usage(settings):
    route = respx.post(f"{settings.NVIDIA_BASE_URL}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"ok": 1}'}, "finish_reason": "length"}],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 5,
                    "prompt_tokens_details": {"cached_tokens": 3},
                },
            },
        )
    )
    result = llm.NimLLM().complete_json(model="m", system="s", user="u", max_tokens=100)
    assert (result.text, result.tokens_in, result.tokens_out, result.tokens_cached) == (
        '{"ok": 1}',
        12,
        5,
        3,
    )
    assert result.truncated
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer test-key"
    body = request.read().decode().replace(" ", "")
    assert '"model":"m"' in body and '"max_tokens":100' in body and "json_object" in body


@respx.mock
def test_nim_llm_raises_on_error_status(settings):
    respx.post(f"{settings.NVIDIA_BASE_URL}/chat/completions").mock(
        return_value=httpx.Response(429)
    )
    with pytest.raises(llm.LLMRequestError, match="429"):
        llm.NimLLM().complete_json(model="m", system="s", user="u", max_tokens=10)


def test_reasoning_blocks_are_ignored_when_parsing():
    text = '<think>let me check</think>\n```json\n{"summary": "ok", "findings": []}\n```'
    assert llm.parse_review(text).findings == []
