from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import time

DEFAULT_ROWS = 384
DEFAULT_WIDTH = 8192


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Microbenchmark the structured-output staging path from vLLM #49013."
    )
    parser.add_argument("--variant", choices=["parent", "culprit", "culprit-single-thread"])
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument(
        "--describe",
        action="store_true",
        help="print the case shape without importing CUDA/PyTorch",
    )
    return parser


def _describe() -> dict[str, object]:
    return {
        "case": "vllm-49013",
        "known_good": "8dd1b702f27edeed24a4336f531b01c346e04253",
        "first_bad": "7df3d7dada840c68b85b26b79de7f59f676d58e3",
        "rows": DEFAULT_ROWS,
        "bitmask_width": DEFAULT_WIDTH,
        "bytes_per_staging_buffer": DEFAULT_ROWS * DEFAULT_WIDTH * 4,
    }


def main() -> int:
    args = _parser().parse_args()
    if args.describe:
        print(json.dumps(_describe(), sort_keys=True))
        return 0
    if not args.variant:
        raise SystemExit("--variant is required unless --describe is used")
    if args.rows <= 0 or args.width <= 0 or args.warmup < 0 or args.iterations <= 0:
        raise SystemExit("rows, width, and iterations must be positive; warmup cannot be negative")

    try:
        import numpy as np
        import torch
    except ImportError as exc:
        raise SystemExit("this benchmark requires numpy and a CUDA-enabled PyTorch build") from exc

    if not torch.cuda.is_available():
        raise SystemExit("CUDA is required for the vllm-49013 benchmark")

    if args.variant == "culprit-single-thread":
        torch.set_num_threads(1)

    device = torch.device("cuda")
    source = np.zeros((args.rows, args.width), dtype=np.int32)
    source[:, ::2] = -1

    def parent_step():
        sorted_bitmask = np.full(
            shape=(args.rows, args.width),
            fill_value=-1,
            dtype=source.dtype,
        )
        for row in range(args.rows):
            sorted_bitmask[row] = source[row]
        return torch.from_numpy(sorted_bitmask).to(device, non_blocking=True)

    def culprit_step():
        sorted_bitmask_tensor = torch.full(
            (args.rows, args.width),
            -1,
            dtype=torch.int32,
            pin_memory=True,
        )
        sorted_bitmask = sorted_bitmask_tensor.numpy()
        for row in range(args.rows):
            sorted_bitmask[row] = source[row]
        return sorted_bitmask_tensor.to(device, non_blocking=True)

    step = parent_step if args.variant == "parent" else culprit_step

    for _ in range(args.warmup):
        staged = step()
        del staged
        torch.cuda.synchronize()

    samples_ms: list[float] = []
    for _ in range(args.iterations):
        started = time.perf_counter()
        staged = step()
        torch.cuda.synchronize()
        samples_ms.append((time.perf_counter() - started) * 1000.0)
        del staged

    mean_ms = statistics.fmean(samples_ms)
    ordered = sorted(samples_ms)
    p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95) - 1))
    payload = {
        "metrics": {
            "staging_steps_per_second": 1000.0 / mean_ms,
            "mean_step_ms": mean_ms,
            "p95_step_ms": ordered[p95_index],
        },
        "checks": {
            "cuda_available": True,
            "shape_matches_upstream": args.rows == DEFAULT_ROWS and args.width == DEFAULT_WIDTH,
        },
        "details": {
            "case": "vllm-49013",
            "variant": args.variant,
            "rows": args.rows,
            "bitmask_width": args.width,
            "bytes_per_staging_buffer": args.rows * args.width * 4,
            "torch_num_threads": torch.get_num_threads(),
            "cpu_count": os.cpu_count(),
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "gpu": torch.cuda.get_device_name(0),
            "torch_version": torch.__version__,
            "torch_cuda_version": torch.version.cuda,
            "numpy_version": np.__version__,
        },
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
