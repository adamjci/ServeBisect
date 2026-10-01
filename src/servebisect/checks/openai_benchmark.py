from __future__ import annotations

import concurrent.futures
import json
import math
import statistics
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any

from ..fingerprint import environment_fingerprint


@dataclass(frozen=True)
class RequestSample:
    ok: bool
    latency_ms: float
    ttft_ms: float | None
    completion_tokens: int | None
    error: str | None = None


@dataclass
class BenchmarkResult:
    base_url: str
    model: str
    request_count: int
    concurrency: int
    wall_time_s: float
    samples: list[RequestSample]

    def _percentile(self, values: list[float], fraction: float) -> float:
        if not values:
            return math.nan
        ordered = sorted(values)
        index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
        return ordered[index]

    def payload(self) -> dict[str, Any]:
        successful = [sample for sample in self.samples if sample.ok]
        latencies = [sample.latency_ms for sample in successful]
        ttfts = [sample.ttft_ms for sample in successful if sample.ttft_ms is not None]
        token_counts = [
            sample.completion_tokens
            for sample in successful
            if sample.completion_tokens is not None
        ]
        metrics: dict[str, float] = {
            "requests_per_second": len(successful) / self.wall_time_s if self.wall_time_s else 0.0,
            "success_rate_pct": len(successful) / self.request_count * 100.0,
        }
        if latencies:
            metrics.update(
                {
                    "latency_ms_p50": statistics.median(latencies),
                    "latency_ms_p95": self._percentile(latencies, 0.95),
                }
            )
        if ttfts:
            metrics.update(
                {
                    "ttft_ms_p50": statistics.median(ttfts),
                    "ttft_ms_p95": self._percentile(ttfts, 0.95),
                }
            )
        if token_counts:
            metrics["completion_tokens_per_second"] = sum(token_counts) / self.wall_time_s
        return {
            "metrics": metrics,
            "checks": {
                "all_requests_succeeded": len(successful) == self.request_count,
                "stream_protocol_valid": all(sample.ttft_ms is not None for sample in successful),
            },
            "details": {
                "base_url": self.base_url,
                "model": self.model,
                "request_count": self.request_count,
                "concurrency": self.concurrency,
                "wall_time_s": self.wall_time_s,
                "environment": environment_fingerprint(),
                "samples": [asdict(sample) for sample in self.samples],
            },
        }


class OpenAIEndpointBenchmark:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_s: float = 120.0,
        prompt: str = "Write ten short numbered facts about the moon.",
        max_tokens: int = 128,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.prompt = prompt
        self.max_tokens = max_tokens

    def _once(self) -> RequestSample:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": self.prompt}],
            "temperature": 0,
            "max_tokens": self.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        started = time.perf_counter()
        first_data: float | None = None
        completion_tokens: int | None = None
        saw_done = False
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                if int(response.status) != 200:
                    return RequestSample(
                        False,
                        (time.perf_counter() - started) * 1000,
                        None,
                        None,
                        f"HTTP {response.status}",
                    )
                for raw in response:
                    line = raw.decode(errors="replace").strip()
                    if not line.startswith("data: "):
                        continue
                    data = line[6:].strip()
                    if data == "[DONE]":
                        saw_done = True
                        continue
                    if first_data is None:
                        first_data = time.perf_counter()
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError as exc:
                        return RequestSample(
                            False,
                            (time.perf_counter() - started) * 1000,
                            None,
                            None,
                            f"invalid SSE JSON: {exc}",
                        )
                    usage = chunk.get("usage")
                    if isinstance(usage, dict) and usage.get("completion_tokens") is not None:
                        completion_tokens = int(usage["completion_tokens"])
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return RequestSample(
                False,
                (time.perf_counter() - started) * 1000,
                None,
                None,
                str(exc),
            )
        finished = time.perf_counter()
        if first_data is None or not saw_done:
            return RequestSample(
                False,
                (finished - started) * 1000,
                None,
                completion_tokens,
                "stream did not contain data followed by [DONE]",
            )
        return RequestSample(
            True,
            (finished - started) * 1000,
            (first_data - started) * 1000,
            completion_tokens,
        )

    def run(self, *, requests: int = 8, concurrency: int = 1) -> BenchmarkResult:
        if requests < 1:
            raise ValueError("requests must be >= 1")
        if concurrency < 1:
            raise ValueError("concurrency must be >= 1")
        started = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            samples = list(executor.map(lambda _: self._once(), range(requests)))
        return BenchmarkResult(
            base_url=self.base_url,
            model=self.model,
            request_count=requests,
            concurrency=concurrency,
            wall_time_s=time.perf_counter() - started,
            samples=samples,
        )
