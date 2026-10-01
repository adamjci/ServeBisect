from __future__ import annotations

import json
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "cases" / "vllm-49013"


class CaseTests(unittest.TestCase):
    def test_vllm_49013_manifest_pins_expected_boundary(self) -> None:
        manifest = tomllib.loads((CASE / "case.toml").read_text())
        self.assertEqual(
            manifest["revisions"]["known_good"],
            "8dd1b702f27edeed24a4336f531b01c346e04253",
        )
        self.assertEqual(
            manifest["revisions"]["first_bad"],
            "7df3d7dada840c68b85b26b79de7f59f676d58e3",
        )
        self.assertEqual(manifest["hardware"]["gpu"], "A100")
        self.assertEqual(manifest["hardware"]["vram_gb"], 80)

    def test_vllm_49013_description_runs_without_gpu_dependencies(self) -> None:
        result = subprocess.run(
            [sys.executable, str(CASE / "staging_benchmark.py"), "--describe"],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["rows"], 384)
        self.assertEqual(payload["bitmask_width"], 8192)
        self.assertEqual(payload["bytes_per_staging_buffer"], 12_582_912)


if __name__ == "__main__":
    unittest.main()
