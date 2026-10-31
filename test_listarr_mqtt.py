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
    def test_partial_updates_last_run_and_preserves_success(self):
        args = Namespace(config="test.conf", dry_run=False)
        previous_run = "2026-10-30T20:00:00+01:00"
        current_run = "2026-10-31T21:00:00+01:00"
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"LISTARR_STATE_DIR": directory}), patch.object(job, "now", return_value=current_run), patch.object(job, "publish") as publish, patch.object(job.subprocess, "run") as run:
            path = Path(directory) / "sonarr.json"
            # Older state files have finished_at but no last_run.
            path.write_text(json.dumps({"finished_at": previous_run, "last_success": previous_run}))
            snapshots = []
            publish.side_effect = lambda target, state: snapshots.append(dict(state))
            run.return_value = subprocess.CompletedProcess([], 0, "SYNCED\nNot found: 15")
            self.assertTrue(job.run_target("sonarr", args, []))
            self.assertEqual(snapshots[0]["last_run"], previous_run)
            state = json.loads(path.read_text())
            self.assertEqual(state["status"], "partial")
            self.assertEqual(state["last_run"], current_run)
            self.assertEqual(state["last_success"], previous_run)
            self.assertEqual(snapshots[-1]["last_run"], current_run)

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
