from __future__ import annotations

from .base import EngineAdapter


class VLLMAdapter(EngineAdapter):
    def __init__(self) -> None:
        super().__init__(name="vllm", module="vllm.entrypoints.openai.api_server")

    def launch_command(
        self,
        *,
        model: str,
        host: str = "127.0.0.1",
        port: int = 8000,
        extra_args: list[str] | None = None,
    ) -> list[str]:
        command = [
            "python",
            "-m",
            self.module,
            "--model",
            model,
            "--host",
            host,
            "--port",
            str(port),
        ]
        return command + list(extra_args or [])
