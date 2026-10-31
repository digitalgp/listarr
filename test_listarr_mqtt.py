import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from argparse import Namespace

import listarr_mqtt as job


class JobTests(unittest.TestCase):
    def test_success_then_failure_keeps_timestamp(self):
        args = Namespace(config="test.conf", dry_run=False)
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"LISTARR_STATE_DIR": directory}), patch.object(job, "now", return_value="2026-10-31T21:00:00+01:00"), patch.object(job, "publish"), patch.object(job.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, "[Sonarr] SYNCED -> MDBList 123\nNot found: 0")
            self.assertFalse(job.run_target("sonarr", args, []))
            path = Path(directory) / "sonarr.json"
            success = json.loads(path.read_text())["last_success"]
            self.assertIsNotNone(success)
            run.return_value = subprocess.CompletedProcess([], 2, "API failed")
            self.assertTrue(job.run_target("sonarr", args, []))
            state = json.loads(path.read_text())
            self.assertEqual(state["status"], "error")
            self.assertEqual(state["last_success"], success)

    def test_incomplete_and_dry_runs_are_not_success(self):
        self.assertEqual(job.outcome(0, "SYNCED\nNot found: 3", False), "partial")
        self.assertEqual(job.outcome(0, "SYNCED", True), "dry_run")
        self.assertEqual(job.outcome(0, "no confirmation", False), "unconfirmed")
        self.assertEqual(job.outcome(2, "SYNCED", False), "error")

    def test_all_continues_after_first_failure(self):
        with patch("sys.argv", ["job", "--all"]), patch.object(job, "run_target", side_effect=[True, False]) as run:
            self.assertEqual(job.main(), 1)
            self.assertEqual([call.args[0] for call in run.call_args_list], ["sonarr", "radarr"])


if __name__ == "__main__":
    unittest.main()
