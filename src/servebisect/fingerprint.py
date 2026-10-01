from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
from typing import Any


def _capture(command: list[str], timeout: float = 5.0) -> str | None:
    if shutil.which(command[0]) is None:
        return None
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def environment_fingerprint() -> dict[str, Any]:
    result: dict[str, Any] = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": sys.version.split()[0],
    }
    git_version = _capture(["git", "--version"])
    if git_version:
        result["git"] = git_version

    gpu_json = _capture(
        [
            "nvidia-smi",
            "--query-gpu=name,uuid,driver_version,memory.total",
            "--format=csv,noheader,nounits",
        ]
    )
    if gpu_json:
        gpus = []
        for row in gpu_json.splitlines():
            parts = [part.strip() for part in row.split(",")]
            if len(parts) == 4:
                gpus.append(
                    {
                        "name": parts[0],
                        "uuid": parts[1],
                        "driver_version": parts[2],
                        "memory_mb": int(parts[3]),
                    }
                )
        if gpus:
            result["nvidia_gpus"] = gpus

    rocm = _capture(["rocminfo"], timeout=8.0)
    if rocm:
        result["rocm_detected"] = True
    return json.loads(json.dumps(result))
