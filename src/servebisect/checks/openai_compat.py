from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


@dataclass
class ConformanceResult:
    base_url: str
    model: str
    checks: list[CheckResult]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "model": self.model,
            "passed": self.passed,
            "checks": [asdict(check) for check in self.checks],
        }


class OpenAIConformanceSuite:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_s: float = 90.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_s = timeout_s

    def _request(self, payload: dict[str, Any], *, stream: bool = False) -> tuple[int, bytes]:
        data = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                return int(response.status), response.read()
        except urllib.error.HTTPError as exc:
            return int(exc.code), exc.read()

    def _basic(self) -> CheckResult:
        status, body = self._request(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": "Reply with the word OK."}],
                "temperature": 0,
                "max_tokens": 16,
            }
        )
        if status != 200:
            return CheckResult("basic_chat", False, f"HTTP {status}: {body[:160]!r}")
        try:
            data = json.loads(body)
            message = data["choices"][0]["message"]
            has_output = bool(message.get("content") or message.get("reasoning_content"))
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            return CheckResult("basic_chat", False, f"invalid response shape: {exc}")
        return CheckResult("basic_chat", has_output, "choice message contains model output")

    def _json_object(self) -> CheckResult:
        status, body = self._request(
            {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": 'Return exactly one JSON object with key "servebisect" and value true.',
                    }
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0,
                "max_tokens": 64,
            }
        )
        if status != 200:
            return CheckResult("json_object", False, f"HTTP {status}: {body[:160]!r}")
        try:
            data = json.loads(body)
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            return CheckResult("json_object", False, f"response was not valid JSON content: {exc}")
        return CheckResult("json_object", isinstance(parsed, dict), "content parses as a JSON object")

    def _tool_choice(self) -> CheckResult:
        tool = {
            "type": "function",
            "function": {
                "name": "servebisect_probe",
                "description": "Return a probe value.",
                "parameters": {
                    "type": "object",
                    "properties": {"value": {"type": "integer"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
            },
        }
        status, body = self._request(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": "Call the probe with value 7."}],
                "tools": [tool],
                "tool_choice": {"type": "function", "function": {"name": "servebisect_probe"}},
                "temperature": 0,
            }
        )
        if status != 200:
            return CheckResult("tool_choice", False, f"HTTP {status}: {body[:160]!r}")
        try:
            data = json.loads(body)
            call = data["choices"][0]["message"]["tool_calls"][0]
            function = call["function"]
            arguments = json.loads(function["arguments"])
            passed = function["name"] == "servebisect_probe" and arguments.get("value") == 7
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            return CheckResult("tool_choice", False, f"invalid tool call shape: {exc}")
        return CheckResult("tool_choice", passed, "forced tool call is structurally valid")

    def _stream(self) -> CheckResult:
        status, body = self._request(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": "Reply OK."}],
                "stream": True,
                "temperature": 0,
                "max_tokens": 16,
            },
            stream=True,
        )
        if status != 200:
            return CheckResult("stream_sse", False, f"HTTP {status}: {body[:160]!r}")
        text = body.decode(errors="replace")
        data_lines = [line[6:] for line in text.splitlines() if line.startswith("data: ")]
        if not data_lines or data_lines[-1].strip() != "[DONE]":
            return CheckResult("stream_sse", False, "stream did not terminate with data: [DONE]")
        json_chunks = [line for line in data_lines[:-1] if line.strip()]
        try:
            chunks = [json.loads(line) for line in json_chunks]
        except json.JSONDecodeError as exc:
            return CheckResult("stream_sse", False, f"stream chunk is not JSON: {exc}")
        valid = bool(chunks) and all("choices" in chunk for chunk in chunks)
        return CheckResult("stream_sse", valid, "SSE chunks are JSON and terminate cleanly")

    def run(self, selected: list[str] | None = None) -> ConformanceResult:
        probes = {
            "basic_chat": self._basic,
            "json_object": self._json_object,
            "tool_choice": self._tool_choice,
            "stream_sse": self._stream,
        }
        names = selected or list(probes)
        unknown = [name for name in names if name not in probes]
        if unknown:
            raise ValueError(f"unknown conformance checks: {', '.join(unknown)}")
        return ConformanceResult(
            base_url=self.base_url,
            model=self.model,
            checks=[probes[name]() for name in names],
        )
