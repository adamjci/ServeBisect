from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class LiumError(RuntimeError):
    pass


@dataclass(frozen=True)
class LiumNode:
    id: str
    gpu_type: str
    gpu_count: int
    price_per_hour: float
    price_per_gpu_hour: float | None = None
    country: str | None = None
    vram_gb: float | None = None


@dataclass(frozen=True)
class LiumRunResult:
    pod: str
    node: LiumNode
    exit_code: int
    stdout: str
    stderr: str
    allocated_gpu_count: int | None = None


class LiumCLI:
    """Small non-interactive wrapper around the official Lium CLI."""

    MIN_SCRIPTABLE_VERSION = (0, 0, 42)

    def __init__(self, executable: str = "lium") -> None:
        self.executable = executable
        self._cached_version: tuple[int, int, int] | None = None

    def _run(self, args: list[str], *, timeout: float = 900.0) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["LIUM_NONINTERACTIVE"] = "1"
        try:
            return subprocess.run(
                [self.executable, *args],
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise LiumError("lium CLI is not installed or not on PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise LiumError(f"lium command timed out: {args!r}") from exc

    def version(self) -> tuple[int, int, int]:
        if self._cached_version is not None:
            return self._cached_version
        result = self._run(["--version"], timeout=15.0)
        if result.returncode != 0:
            raise LiumError(result.stderr.strip() or "could not read lium CLI version")
        match = re.search(r"(\d+)\.(\d+)\.(\d+)", result.stdout or result.stderr)
        if not match:
            raise LiumError("could not parse lium CLI version")
        self._cached_version = tuple(int(part) for part in match.groups())  # type: ignore[assignment]
        return self._cached_version

    def ensure_scriptable_version(self) -> None:
        installed = self.version()
        if installed < self.MIN_SCRIPTABLE_VERSION:
            current = ".".join(str(part) for part in installed)
            minimum = ".".join(str(part) for part in self.MIN_SCRIPTABLE_VERSION)
            raise LiumError(
                f"lium CLI {current} is too old for safe non-interactive runs; "
                f"upgrade to {minimum} or newer"
            )

    def doctor(self) -> None:
        if shutil.which(self.executable) is None:
            raise LiumError("lium CLI is not installed or not on PATH")
        self.ensure_scriptable_version()
        result = self._run(["balance", "--json"], timeout=30.0)
        if result.returncode != 0:
            raise LiumError(result.stderr.strip() or "lium authentication check failed")

    def list_nodes(self, *, gpu_type: str | None = None, count: int = 1) -> list[LiumNode]:
        result = self._run(["ls", "--format", "json"], timeout=60.0)
        if result.returncode != 0:
            raise LiumError(result.stderr.strip() or result.stdout.strip() or "lium ls failed")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise LiumError("lium ls did not return JSON") from exc
        nodes: list[LiumNode] = []
        for item in payload:
            node_gpu = str(item.get("gpu_type", ""))
            node_count = int(item.get("gpu_count", 0))
            if gpu_type and node_gpu.casefold() != gpu_type.casefold():
                continue
            if node_count < count:
                continue
            per_gpu_raw = item.get("price_per_gpu_hour", item.get("price_per_gpu"))
            per_gpu = float(per_gpu_raw) if per_gpu_raw is not None else None
            total_raw = item.get("price_per_hour")
            if per_gpu is not None:
                requested_price = per_gpu * count
            elif total_raw is not None and node_count == count:
                requested_price = float(total_raw)
            else:
                # We cannot safely enforce a price ceiling for a partial-node
                # rental when the provider omits per-GPU pricing.
                continue
            nodes.append(
                LiumNode(
                    id=str(item["id"]),
                    gpu_type=node_gpu,
                    gpu_count=node_count,
                    price_per_hour=requested_price,
                    price_per_gpu_hour=per_gpu,
                    country=str(item["country"]) if item.get("country") else None,
                    vram_gb=float(item["vram_gb"]) if item.get("vram_gb") is not None else None,
                )
            )
        return sorted(nodes, key=lambda node: node.price_per_hour)

    def _pods(self) -> list[dict[str, Any]]:
        result = self._run(["ps", "--format", "json"], timeout=30.0)
        if result.returncode != 0:
            raise LiumError(result.stderr.strip() or "lium ps failed")
        try:
            pods = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise LiumError("lium ps did not return JSON") from exc
        if not isinstance(pods, list):
            raise LiumError("lium ps returned an unexpected JSON shape")
        return [pod for pod in pods if isinstance(pod, dict)]

    def _find_pod_by_name(self, name: str) -> str | None:
        pods = self._pods()
        for pod in pods:
            if pod.get("name") == name:
                return str(pod.get("huid") or pod.get("id") or name)
        return None

    def _reconcile_failed_rent(self, name: str) -> str:
        try:
            pod = self._find_pod_by_name(name)
        except LiumError as exc:
            return f"; reconciliation failed: {exc}"
        if not pod:
            return "; no matching pod found during reconciliation"
        try:
            self.remove(pod)
        except LiumError as exc:
            return f"; found pod {pod} but cleanup failed: {exc}"
        return f"; reconciled and removed pod {pod}"

    def rent(self, node: LiumNode, *, name: str, count: int, ttl: str = "1h") -> str:
        try:
            result = self._run(
                [
                    "up",
                    node.id,
                    "--count",
                    str(count),
                    "--name",
                    name,
                    "--ttl",
                    ttl,
                    "--yes",
                    "--no-ssh",
                ],
                timeout=900.0,
            )
        except LiumError as exc:
            raise LiumError(str(exc) + self._reconcile_failed_rent(name)) from exc
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "lium up failed"
            raise LiumError(message + self._reconcile_failed_rent(name))
        pod = self._find_pod_by_name(name)
        if not pod:
            try:
                self.remove(name)
            except LiumError as cleanup_exc:
                raise LiumError(
                    f"rented pod {name!r} was not visible in lium ps; "
                    f"cleanup by name also failed: {cleanup_exc}"
                ) from cleanup_exc
            raise LiumError(
                f"rented pod {name!r} was not visible in lium ps; removed it by unique name"
            )
        return pod

    def exec(self, pod: str, command: str, *, timeout: float = 3600.0) -> LiumRunResult:
        result = self._run(["exec", pod, "--json", command], timeout=timeout)
        try:
            payload: dict[str, Any] = json.loads(result.stdout) if result.stdout.strip() else {}
        except json.JSONDecodeError:
            payload = {}
        rows = payload.get("results", []) if isinstance(payload, dict) else []
        row = rows[0] if rows else {}
        return LiumRunResult(
            pod=pod,
            node=LiumNode(id="unknown", gpu_type="unknown", gpu_count=0, price_per_hour=0.0),
            exit_code=int(row.get("exit_code", result.returncode)),
            stdout=str(row.get("stdout", result.stdout)),
            stderr=str(row.get("stderr", result.stderr)),
        )

    def copy_to(self, pod: str, source: str | Path, destination: str) -> None:
        source_path = Path(source).expanduser().resolve()
        if not source_path.is_file():
            raise LiumError(f"upload source is not a file: {source_path}")
        result = self._run(
            ["scp", pod, str(source_path), destination],
            timeout=300.0,
        )
        if result.returncode != 0:
            raise LiumError(
                result.stderr.strip()
                or result.stdout.strip()
                or f"failed to upload {source_path} to {pod}:{destination}"
            )

    def remove(self, pod: str) -> None:
        result = self._run(["rm", pod], timeout=120.0)
        if result.returncode != 0:
            raise LiumError(result.stderr.strip() or result.stdout.strip() or f"failed to remove {pod}")
        for _ in range(3):
            if not any(
                pod
                in {
                    str(item.get("huid") or ""),
                    str(item.get("id") or ""),
                    str(item.get("name") or ""),
                }
                for item in self._pods()
            ):
                return
            time.sleep(0.5)
        raise LiumError(f"lium reported success but pod {pod!r} is still active")

    def run_ephemeral(
        self,
        *,
        command: str,
        gpu_type: str,
        count: int = 1,
        ttl: str = "1h",
        setup: str | None = None,
        max_hourly_price: float | None = None,
    ) -> LiumRunResult:
        results = self.run_ephemeral_commands(
            commands=[command],
            gpu_type=gpu_type,
            count=count,
            ttl=ttl,
            setup=setup,
            max_hourly_price=max_hourly_price,
        )
        return results[0]

    def run_ephemeral_commands(
        self,
        *,
        commands: list[str],
        gpu_type: str,
        count: int = 1,
        ttl: str = "1h",
        setup: str | None = None,
        max_hourly_price: float | None = None,
        uploads: list[tuple[str | Path, str]] | None = None,
    ) -> list[LiumRunResult]:
        if not commands:
            raise LiumError("at least one remote command is required")
        self.ensure_scriptable_version()
        nodes = self.list_nodes(gpu_type=gpu_type, count=count)
        if not nodes:
            raise LiumError(f"no rentable Lium node matched {count}x {gpu_type}")
        node = nodes[0]
        if max_hourly_price is not None and node.price_per_hour > max_hourly_price:
            raise LiumError(
                f"cheapest matching node is ${node.price_per_hour:.4g}/h, above "
                f"the configured ${max_hourly_price:.4g}/h ceiling"
            )
        name = f"servebisect-{uuid.uuid4().hex[:10]}"
        pod = self.rent(node, name=name, count=count, ttl=ttl)
        try:
            for source, destination in uploads or []:
                self.copy_to(pod, source, destination)
            if setup:
                setup_result = self.exec(pod, setup)
                if setup_result.exit_code != 0:
                    raise LiumError(
                        f"remote setup failed with exit {setup_result.exit_code}: {setup_result.stderr}"
                    )
            results: list[LiumRunResult] = []
            for command in commands:
                result = self.exec(pod, command)
                results.append(
                    LiumRunResult(
                        pod=pod,
                        node=node,
                        exit_code=result.exit_code,
                        stdout=result.stdout,
                        stderr=result.stderr,
                        allocated_gpu_count=count,
                    )
                )
                if result.exit_code != 0:
                    raise LiumError(
                        f"remote command failed with exit {result.exit_code}: {result.stderr}"
                    )
            return results
        finally:
            self.remove(pod)
