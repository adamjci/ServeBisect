from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EngineAdapter:
    name: str
    module: str

    def launch_command(
        self,
        *,
        model: str,
        host: str = "127.0.0.1",
        port: int = 8000,
        extra_args: list[str] | None = None,
    ) -> list[str]:
        raise NotImplementedError
