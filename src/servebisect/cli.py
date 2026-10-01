from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path

from .bisect import BisectError, bisect_metric
from .checks import OpenAIConformanceSuite, OpenAIEndpointBenchmark
from .config import load_run_config
from .demo import run_demo
from .engines import get_engine
from .models import MetricRule, Observation
from .providers.lium import LiumCLI, LiumError
from .regression import compare_observations
from .reports import (
    bisect_markdown,
    comparison_markdown,
    write_json_report,
    write_markdown,
)
from .runner import BenchmarkError, parse_benchmark_payload, run_benchmark


def _add_metric_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--metric", required=True, help="Metric key emitted by the benchmark")
    parser.add_argument("--direction", choices=["higher", "lower"], default="higher")
    parser.add_argument("--max-regression-pct", type=float, default=5.0)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="servebisect",
        description="Reproduce, compare, and bisect inference regressions.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run baseline and candidate benchmarks from TOML")
    run.add_argument("config", type=Path)

    bisect = sub.add_parser("bisect", help="find the first revision exceeding a metric budget")
    bisect.add_argument("--repo", type=Path, default=Path.cwd())
    bisect.add_argument("--good", required=True)
    bisect.add_argument("--bad", required=True)
    bisect.add_argument("--command", required=True, help="benchmark command run inside each worktree")
    _add_metric_args(bisect)
    bisect.add_argument("--timeout-s", type=float, default=900.0)
    bisect.add_argument("--json", dest="json_path", type=Path)
    bisect.add_argument("--markdown", dest="markdown_path", type=Path)

    conformance = sub.add_parser("conformance", help="probe an OpenAI-compatible chat endpoint")
    conformance.add_argument("--base-url", required=True, help="for example http://127.0.0.1:8000/v1")
    conformance.add_argument("--model", required=True)
    conformance.add_argument("--api-key-env", default="OPENAI_API_KEY")
    conformance.add_argument(
        "--check",
        action="append",
        choices=["basic_chat", "json_object", "tool_choice", "stream_sse"],
        help="repeat to run only selected checks",
    )
    conformance.add_argument("--json", dest="json_path", type=Path)

    benchmark = sub.add_parser("benchmark", help="benchmark an OpenAI-compatible streaming endpoint")
    benchmark.add_argument("--base-url", required=True)
    benchmark.add_argument("--model", required=True)
    benchmark.add_argument("--api-key-env", default="OPENAI_API_KEY")
    benchmark.add_argument("--requests", type=int, default=8)
    benchmark.add_argument("--concurrency", type=int, default=1)
    benchmark.add_argument("--max-tokens", type=int, default=128)
    benchmark.add_argument("--prompt", default="Write ten short numbered facts about the moon.")
    benchmark.add_argument("--timeout-s", type=float, default=120.0)
    benchmark.add_argument("--json", dest="json_path", type=Path)

    serve = sub.add_parser("serve-command", help="print a launch command for a supported engine")
    serve.add_argument("--engine", required=True, choices=["vllm", "sglang"])
    serve.add_argument("--model", required=True)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("extra", nargs=argparse.REMAINDER)

    lium = sub.add_parser("lium", help="use Lium ephemeral GPU workers")
    lium_sub = lium.add_subparsers(dest="lium_command", required=True)
    doctor = lium_sub.add_parser("doctor", help="verify CLI auth and show matching nodes")
    doctor.add_argument("--gpu")
    doctor.add_argument("--count", type=int, default=1)
    remote = lium_sub.add_parser("run", help="rent the cheapest matching GPU, run, and tear down")
    remote.add_argument("--gpu", required=True)
    remote.add_argument("--count", type=int, default=1)
    remote.add_argument("--ttl", default="1h")
    remote.add_argument("--max-hourly-price", type=float)
    remote.add_argument("--setup")
    remote.add_argument("--command", required=True)

    compare = lium_sub.add_parser(
        "compare",
        help="run baseline and candidate commands on one ephemeral GPU and compare them",
    )
    compare.add_argument("--gpu", required=True)
    compare.add_argument("--count", type=int, default=1)
    compare.add_argument("--ttl", default="1h")
    compare.add_argument("--max-hourly-price", type=float)
    compare.add_argument("--setup")
    compare.add_argument(
        "--upload",
        action="append",
        default=[],
        metavar="LOCAL:REMOTE",
        help="upload a local file before running; repeat as needed",
    )
    compare.add_argument("--baseline-command", required=True)
    compare.add_argument("--candidate-command", required=True)
    compare.add_argument("--baseline-label", default="baseline")
    compare.add_argument("--candidate-label", default="candidate")
    _add_metric_args(compare)
    compare.add_argument("--json", dest="json_path", type=Path)
    compare.add_argument("--markdown", dest="markdown_path", type=Path)

    demo = sub.add_parser("demo", help="run a deterministic synthetic regression bisect")
    demo.add_argument("--json", dest="json_path", type=Path)
    demo.add_argument("--markdown", dest="markdown_path", type=Path)
    return parser


def _cmd_run(args: argparse.Namespace) -> int:
    config = load_run_config(args.config)
    base_dir = args.config.resolve().parent

    def target_cwd(value: str | None) -> Path:
        return (base_dir / value).resolve() if value else base_dir

    baseline = run_benchmark(
        label=config.baseline.label,
        command=config.baseline.command,
        cwd=target_cwd(config.baseline.cwd),
        timeout_s=config.baseline.timeout_s,
    )
    candidate = run_benchmark(
        label=config.candidate.label,
        command=config.candidate.command,
        cwd=target_cwd(config.candidate.cwd),
        timeout_s=config.candidate.timeout_s,
    )
    report = compare_observations(baseline, candidate, config.metrics)
    json_path = (base_dir / config.json_report).resolve()
    markdown_path = (base_dir / config.markdown_report).resolve()
    write_json_report(report, json_path)
    write_markdown(comparison_markdown(report), markdown_path)
    print(comparison_markdown(report), end="")
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")
    return 0 if report.passed else 1


def _cmd_bisect(args: argparse.Namespace) -> int:
    report = bisect_metric(
        repo=args.repo,
        good=args.good,
        bad=args.bad,
        command=shlex.split(args.command),
        rule=MetricRule(args.metric, args.direction, args.max_regression_pct),
        timeout_s=args.timeout_s,
    )
    if args.json_path:
        write_json_report(report, args.json_path)
    markdown = bisect_markdown(report)
    if args.markdown_path:
        write_markdown(markdown, args.markdown_path)
    print(markdown, end="")
    return 0


def _cmd_conformance(args: argparse.Namespace) -> int:
    suite = OpenAIConformanceSuite(
        base_url=args.base_url,
        model=args.model,
        api_key=os.getenv(args.api_key_env),
    )
    result = suite.run(args.check)
    payload = result.to_dict()
    if args.json_path:
        args.json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    for check in result.checks:
        print(f"{'PASS' if check.passed else 'FAIL'} {check.name}: {check.detail}")
    return 0 if result.passed else 1


def _cmd_serve(args: argparse.Namespace) -> int:
    engine = get_engine(args.engine)
    command = engine.launch_command(
        model=args.model,
        host=args.host,
        port=args.port,
        extra_args=args.extra,
    )
    print(shlex.join(command))
    return 0


def _cmd_benchmark(args: argparse.Namespace) -> int:
    benchmark = OpenAIEndpointBenchmark(
        base_url=args.base_url,
        model=args.model,
        api_key=os.getenv(args.api_key_env),
        timeout_s=args.timeout_s,
        prompt=args.prompt,
        max_tokens=args.max_tokens,
    )
    result = benchmark.run(requests=args.requests, concurrency=args.concurrency)
    payload = result.payload()
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.json_path:
        args.json_path.write_text(rendered + "\n")
    print(rendered)
    return 0 if payload["checks"]["all_requests_succeeded"] else 1


def _cmd_lium(args: argparse.Namespace) -> int:
    client = LiumCLI()
    if args.lium_command == "doctor":
        client.doctor()
        nodes = client.list_nodes(gpu_type=args.gpu, count=args.count)
        print(json.dumps([node.__dict__ for node in nodes[:10]], indent=2))
        return 0
    if args.lium_command == "compare":
        uploads: list[tuple[Path, str]] = []
        for value in args.upload:
            local, separator, remote = value.partition(":")
            if not separator or not local or not remote:
                raise ValueError("--upload must use LOCAL:REMOTE syntax")
            uploads.append((Path(local), remote))
        baseline_command = args.baseline_command
        candidate_command = args.candidate_command
        results = client.run_ephemeral_commands(
            commands=[baseline_command, candidate_command],
            gpu_type=args.gpu,
            count=args.count,
            ttl=args.ttl,
            setup=args.setup,
            max_hourly_price=args.max_hourly_price,
            uploads=uploads,
        )

        def observation(label: str, command: str, result) -> Observation:
            payload = parse_benchmark_payload(result.stdout)
            metrics_raw = payload.get("metrics", {})
            checks_raw = payload.get("checks", {})
            if not isinstance(metrics_raw, dict) or not isinstance(checks_raw, dict):
                raise BenchmarkError("remote benchmark fields 'metrics' and 'checks' must be objects")
            details = payload.get("details", {})
            if not isinstance(details, dict):
                details = {"value": details}
            return Observation(
                label=label,
                command=[command],
                returncode=result.exit_code,
                duration_s=0.0,
                metrics={str(key): float(value) for key, value in metrics_raw.items()},
                checks={str(key): bool(value) for key, value in checks_raw.items()},
                details=details,
                environment={
                    "provider": "lium",
                    "pod": result.pod,
                    "gpu_type": result.node.gpu_type,
                    "gpu_count": result.allocated_gpu_count or result.node.gpu_count,
                    "vram_gb": result.node.vram_gb,
                    "country": result.node.country,
                    "price_per_hour": result.node.price_per_hour,
                },
                stdout=result.stdout,
                stderr=result.stderr,
            )

        report = compare_observations(
            observation(args.baseline_label, baseline_command, results[0]),
            observation(args.candidate_label, candidate_command, results[1]),
            [MetricRule(args.metric, args.direction, args.max_regression_pct)],
        )
        markdown = comparison_markdown(report)
        if args.json_path:
            write_json_report(report, args.json_path)
        if args.markdown_path:
            write_markdown(markdown, args.markdown_path)
        print(markdown, end="")
        return 0 if report.passed else 1
    result = client.run_ephemeral(
        command=args.command,
        gpu_type=args.gpu,
        count=args.count,
        ttl=args.ttl,
        setup=args.setup,
        max_hourly_price=args.max_hourly_price,
    )
    sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.exit_code


def _cmd_demo(args: argparse.Namespace) -> int:
    report = run_demo()
    markdown = bisect_markdown(report)
    if args.json_path:
        write_json_report(report, args.json_path)
    if args.markdown_path:
        write_markdown(markdown, args.markdown_path)
    print(markdown, end="")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "run":
            return _cmd_run(args)
        if args.command == "bisect":
            return _cmd_bisect(args)
        if args.command == "conformance":
            return _cmd_conformance(args)
        if args.command == "benchmark":
            return _cmd_benchmark(args)
        if args.command == "serve-command":
            return _cmd_serve(args)
        if args.command == "lium":
            return _cmd_lium(args)
        if args.command == "demo":
            return _cmd_demo(args)
        raise AssertionError(args.command)
    except (BenchmarkError, BisectError, LiumError, KeyError, ValueError) as exc:
        print(f"servebisect: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
