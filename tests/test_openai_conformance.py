from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from servebisect.checks.openai_benchmark import OpenAIEndpointBenchmark
from servebisect.checks.openai_compat import OpenAIConformanceSuite


class FakeOpenAIHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def do_POST(self) -> None:
        size = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(size))
        self.send_response(200)
        if payload.get("stream"):
            first = 'data: {"choices":[{"delta":{"content":"OK"},"index":0}]}\n\n'
            usage = 'data: {"choices":[],"usage":{"completion_tokens":4}}\n\n'
            body = (first + usage + "data: [DONE]\n\n").encode()
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if payload.get("tool_choice"):
            message = {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "servebisect_probe", "arguments": '{"value": 7}'},
                    }
                ],
            }
        elif payload.get("response_format"):
            message = {"role": "assistant", "content": '{"servebisect": true}'}
        else:
            message = {"role": "assistant", "content": "OK"}
        body = json.dumps({"choices": [{"index": 0, "message": message}]}).encode()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class OpenAIConformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOpenAIHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_full_suite(self) -> None:
        base = f"http://127.0.0.1:{self.server.server_port}/v1"
        result = OpenAIConformanceSuite(base_url=base, model="fake").run()
        self.assertTrue(result.passed)
        self.assertEqual(len(result.checks), 4)

    def test_streaming_benchmark_emits_ci_metrics(self) -> None:
        base = f"http://127.0.0.1:{self.server.server_port}/v1"
        result = OpenAIEndpointBenchmark(base_url=base, model="fake").run(
            requests=4, concurrency=2
        )
        payload = result.payload()
        self.assertTrue(payload["checks"]["all_requests_succeeded"])
        self.assertEqual(payload["metrics"]["success_rate_pct"], 100.0)
        self.assertGreater(payload["metrics"]["requests_per_second"], 0)
        self.assertGreater(payload["metrics"]["completion_tokens_per_second"], 0)


if __name__ == "__main__":
    unittest.main()
