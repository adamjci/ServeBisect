from __future__ import annotations

from .base import EngineAdapter


class SGLangAdapter(EngineAdapter):
    def __init__(self) -> None:
        super().__init__(name="sglang", module="sglang.launch_server")

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
            "--model-path",
            model,
            "--host",
            host,
            "--port",
            str(port),
        ]
        return command + list(extra_args or [])
