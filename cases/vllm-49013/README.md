# vLLM #49013 — structured-output staging regression

This case targets [vLLM issue #49013](https://github.com/vllm-project/vllm/issues/49013), a closed performance regression in structured-output decoding.

Upstream reported that the parent commit `8dd1b702f27edeed24a4336f531b01c346e04253` drained its workload at about 233 requests/minute, while `7df3d7dada840c68b85b26b79de7f59f676d58e3` dropped to about 121 requests/minute. The issue narrowed the hot path to `vllm/v1/structured_output/utils.py::apply_grammar_bitmask`; the culprit commit replaced NumPy staging with a freshly allocated pinned PyTorch tensor on each engine step. The merged vLLM fix in PR #49919 explicitly cites #49013 and manages PyTorch CPU threads during serving.

The upstream end-to-end reproduction used one A100 80GB, a Gemma-4-26B-A4B-IT model, a 262k-vocabulary structured-output workload, and up to 384 logit rows. That makes a faithful full replay useful but unnecessarily expensive as the first public ServeBisect case.

This directory therefore contains a **root-cause microbenchmark** first. It reproduces the exact staging-buffer shape described upstream (`384 × 8192 × int32`, about 12.6 MiB per engine step), compares the parent NumPy staging path with the culprit pinned-PyTorch path, and emits ServeBisect's normal JSON benchmark contract. It does not claim to reproduce the full 2,000/15,000-request model-serving workload.

## Offline validation

No CUDA packages are imported by the description path:

```bash
python staging_benchmark.py --describe
python staging_benchmark.py --help
```

## GPU run

On an A100 80GB machine with CUDA-enabled PyTorch and NumPy installed:

```bash
servebisect run servebisect.toml
```

The config treats a throughput loss greater than 20% as a reproduced regression. Results are written under `artifacts/`.

The benchmark also exposes the mitigation implicated by vLLM's merged fix:

```bash
python staging_benchmark.py --variant culprit-single-thread --iterations 100
```

If the default-thread culprit path is materially slower while the single-thread variant recovers, the artifact directly demonstrates the CPU-thread interaction described in vLLM PR #49919.

### Ephemeral A100 run through Lium

ServeBisect can run both variants on one disposable GPU, which keeps the hardware constant and avoids publishing this repository before the first reproduction. From the repository root:

```bash
PATH="$PWD/.venv/bin:$PATH" .venv/bin/servebisect lium compare \
  --gpu A100 \
  --count 1 \
  --ttl 20m \
  --max-hourly-price 0.35 \
  --setup "python3 -c 'import numpy, torch; assert torch.cuda.is_available(); print(torch.__version__, torch.version.cuda)'" \
  --upload cases/vllm-49013/staging_benchmark.py:/tmp/staging_benchmark.py \
  --baseline-label vllm-parent-8dd1b70 \
  --candidate-label vllm-culprit-7df3d7d \
  --baseline-command "python3 /tmp/staging_benchmark.py --variant parent --iterations 100" \
  --candidate-command "python3 /tmp/staging_benchmark.py --variant culprit --iterations 100" \
  --metric staging_steps_per_second \
  --direction higher \
  --max-regression-pct 20 \
  --json cases/vllm-49013/artifacts/servebisect-report.json \
  --markdown cases/vllm-49013/artifacts/servebisect-report.md
```

The `20m` TTL and `$0.35/h` price ceiling bound the requested run to a short, low-cost rental under Lium's TTL semantics. ServeBisect still removes the pod explicitly after the comparison and verifies that it disappears from fresh provider state. The setup command only verifies that NumPy, CUDA-enabled PyTorch, and a visible GPU are already available on the provider image; it does not modify the system Python environment. The actual PyTorch version and GPU name are emitted by the benchmark so a published artifact records the environment rather than implying it exactly matches upstream's PyTorch build.

## Case progression

The microbenchmark is the cheap first proof. A stronger public case can then replay the upstream model workload on the same A100 class and use ServeBisect to compare the known parent, first-bad commit, and a post-fix revision. That second phase should preserve the model revision, vLLM build identity, GPU/driver fingerprint, workload corpus, raw timings, and provider spend in the published artifact.
