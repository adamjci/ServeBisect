from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from servebisect.providers.lium import LiumCLI


class LiumTests(unittest.TestCase):
    @patch.object(LiumCLI, "_run")
    def test_rejects_old_cli_for_ephemeral_automation(self, run_mock) -> None:
        from servebisect.providers.lium import LiumError

        run_mock.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="lium, version 0.0.5\n", stderr=""
        )
        with self.assertRaisesRegex(LiumError, "too old"):
            LiumCLI().ensure_scriptable_version()

    @patch.object(LiumCLI, "_run")
    def test_nodes_are_filtered_and_sorted_by_price(self, run_mock) -> None:
        run_mock.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                [
                    {"id": "a", "gpu_type": "H100", "gpu_count": 1, "price_per_hour": 3.0},
                    {
                        "id": "b",
                        "gpu_type": "H100",
                        "gpu_count": 2,
                        "price_per_hour": 2.0,
                        "price_per_gpu_hour": 1.0,
                    },
                    {
                        "id": "unknown-subset-price",
                        "gpu_type": "H100",
                        "gpu_count": 4,
                        "price_per_hour": 0.25,
                    },
                    {"id": "c", "gpu_type": "A100", "gpu_count": 8, "price_per_hour": 1.0},
                ]
            ),
            stderr="",
        )
        nodes = LiumCLI().list_nodes(gpu_type="H100", count=1)
        self.assertEqual([node.id for node in nodes], ["b", "a"])


    @patch.object(LiumCLI, "remove")
    @patch.object(LiumCLI, "_find_pod_by_name")
    @patch.object(LiumCLI, "_run")
    def test_rent_reconciles_after_outer_timeout(self, run_mock, find_pod, remove) -> None:
        from servebisect.providers.lium import LiumError, LiumNode

        node = LiumNode("n1", "A100", 1, 0.3, 0.3)
        run_mock.side_effect = LiumError("lium command timed out: ['up']")
        find_pod.return_value = "stable-wolf-aa"
        with self.assertRaisesRegex(LiumError, "reconciled and removed"):
            LiumCLI().rent(node, name="servebisect-timeout", count=1, ttl="20m")
        find_pod.assert_called_once_with("servebisect-timeout")
        remove.assert_called_once_with("stable-wolf-aa")

    @patch.object(LiumCLI, "remove")
    @patch.object(LiumCLI, "exec")
    @patch.object(LiumCLI, "rent")
    @patch.object(LiumCLI, "list_nodes")
    @patch.object(LiumCLI, "ensure_scriptable_version")
    def test_ephemeral_run_always_tears_down(
        self, ensure_version, list_nodes, rent, execute, remove
    ) -> None:
        from servebisect.providers.lium import LiumNode, LiumRunResult

        node = LiumNode("n1", "H100", 1, 2.0, 2.0)
        list_nodes.return_value = [node]
        rent.return_value = "pod-1"
        execute.return_value = LiumRunResult("pod-1", node, 0, "ok\n", "")
        result = LiumCLI().run_ephemeral(command="nvidia-smi", gpu_type="H100")
        self.assertEqual(result.node, node)
        remove.assert_called_once_with("pod-1")

    @patch.object(LiumCLI, "ensure_scriptable_version")
    @patch.object(LiumCLI, "list_nodes")
    def test_price_ceiling_blocks_rent(self, list_nodes, ensure_version) -> None:
        from servebisect.providers.lium import LiumError, LiumNode

        list_nodes.return_value = [LiumNode("n1", "H100", 1, 3.25, 3.25)]
        with self.assertRaisesRegex(LiumError, "above"):
            LiumCLI().run_ephemeral(
                command="nvidia-smi",
                gpu_type="H100",
                max_hourly_price=2.0,
            )

    @patch.object(LiumCLI, "_pods")
    @patch.object(LiumCLI, "_run")
    def test_remove_verifies_pod_is_gone(self, run_mock, pods_mock) -> None:
        run_mock.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        pods_mock.return_value = []
        LiumCLI().remove("pod-1")
        run_mock.assert_called_once_with(["rm", "pod-1"], timeout=120.0)
        pods_mock.assert_called_once()

    @patch("servebisect.providers.lium.time.sleep", return_value=None)
    @patch.object(LiumCLI, "_pods")
    @patch.object(LiumCLI, "_run")
    def test_remove_checks_name_even_when_pod_has_huid(
        self, run_mock, pods_mock, sleep_mock
    ) -> None:
        from servebisect.providers.lium import LiumError

        run_mock.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        pods_mock.return_value = [
            {"huid": "stable-wolf-aa", "id": "uuid-1", "name": "servebisect-run"}
        ]
        with self.assertRaisesRegex(LiumError, "still active"):
            LiumCLI().remove("servebisect-run")
        self.assertEqual(pods_mock.call_count, 3)
        self.assertEqual(sleep_mock.call_count, 3)

    @patch.object(LiumCLI, "_run")
    def test_copy_to_uses_stable_pod_selector(self, run_mock) -> None:
        run_mock.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "case.py"
            source.write_text("print('ok')\n")
            LiumCLI().copy_to("stable-wolf-aa", source, "/tmp/case.py")
        run_mock.assert_called_once_with(
            ["scp", "stable-wolf-aa", str(source.resolve()), "/tmp/case.py"],
            timeout=300.0,
        )

    @patch.object(LiumCLI, "remove")
    @patch.object(LiumCLI, "exec")
    @patch.object(LiumCLI, "copy_to")
    @patch.object(LiumCLI, "rent")
    @patch.object(LiumCLI, "list_nodes")
    @patch.object(LiumCLI, "ensure_scriptable_version")
    def test_ephemeral_commands_share_one_pod(
        self, ensure_version, list_nodes, rent, copy_to, execute, remove
    ) -> None:
        from servebisect.providers.lium import LiumNode, LiumRunResult

        node = LiumNode("n1", "A100", 8, 0.3, 0.3, "US", 80.0)
        list_nodes.return_value = [node]
        rent.return_value = "stable-wolf-aa"
        execute.side_effect = [
            LiumRunResult("stable-wolf-aa", node, 0, '{"metrics":{"rate":10}}\n', ""),
            LiumRunResult("stable-wolf-aa", node, 0, '{"metrics":{"rate":5}}\n', ""),
        ]
        results = LiumCLI().run_ephemeral_commands(
            commands=["python /tmp/case.py --variant parent", "python /tmp/case.py --variant culprit"],
            gpu_type="A100",
            count=1,
            uploads=[("/tmp/local.py", "/tmp/case.py")],
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].allocated_gpu_count, 1)
        self.assertEqual(results[0].node.gpu_count, 8)
        copy_to.assert_called_once_with("stable-wolf-aa", "/tmp/local.py", "/tmp/case.py")
        remove.assert_called_once_with("stable-wolf-aa")


if __name__ == "__main__":
    unittest.main()
