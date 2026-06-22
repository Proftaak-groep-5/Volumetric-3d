import sys
from pathlib import Path
import tempfile
import unittest
from unittest import mock

# Ensure the backend app package is importable when running tests from repo root.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.services.calibration_runner import CalibrationRunnerService


class _FakeProcess:
    def __init__(self) -> None:
        self._poll_value = None
        self.pid = 1234

    def poll(self):
        return self._poll_value

    def wait(self, timeout: float | None = None):
        return 0

    def terminate(self) -> None:
        self._poll_value = 0

    def kill(self) -> None:
        self._poll_value = -9


class _NoOpThread:
    def __init__(self, *args, **kwargs) -> None:
        self._target = kwargs.get("target")
        self._args = kwargs.get("args", ())

    def start(self) -> None:
        # Intentionally do nothing to avoid races.
        return


class CalibrationRunnerTests(unittest.TestCase):
    def _report(self, test_name: str, success: bool, *details: str) -> None:
        status = "PASS" if success else "FAIL"
        source = Path(__file__).name
        message = " | ".join(str(detail) for detail in details if detail is not None)
        print(f". [{status}] {source}::{test_name}: {message}")

    def test_start_sets_running_state(self) -> None:
        # Verifies that start() sets running state and opens a log file handle.
        # This ensures UI/clients can see the job as running and stream logs.
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            config_path = repo_root / "calibration_config.json"
            config_path.write_text("{}", encoding="utf-8")
            fake_process = _FakeProcess()

            calibration_store = mock.Mock()
            with mock.patch("app.services.calibration_runner.subprocess.Popen", return_value=fake_process):
                with mock.patch("app.services.calibration_runner.threading.Thread", _NoOpThread):
                    runner = CalibrationRunnerService(
                        repo_root=repo_root,
                        calibration_config_file=config_path,
                        calibration_store=calibration_store,
                    )
                    snapshot = runner.start()
                    try:
                        self.assertTrue(snapshot.running)
                        self.assertEqual(snapshot.state, "running")
                        self.assertIsNotNone(snapshot.log_file)
                    finally:
                        runner.shutdown()
        self._report(
            "start_sets_running_state",
            True,
            "check=start sets running state and log file",
            f"state={snapshot.state}",
            f"running={snapshot.running}",
            f"log_file_set={snapshot.log_file is not None}",
        )

    def test_refresh_marks_success_and_reloads(self) -> None:
        # Ensures that a finished process (exit code 0) is detected as success,
        # and that calibration_store.load() is invoked to refresh cached values.
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            config_path = repo_root / "calibration_config.json"
            config_path.write_text("{}", encoding="utf-8")
            fake_process = _FakeProcess()

            calibration_store = mock.Mock()
            with mock.patch("app.services.calibration_runner.subprocess.Popen", return_value=fake_process):
                with mock.patch("app.services.calibration_runner.threading.Thread", _NoOpThread):
                    runner = CalibrationRunnerService(
                        repo_root=repo_root,
                        calibration_config_file=config_path,
                        calibration_store=calibration_store,
                    )
                    _ = runner.start()

            fake_process._poll_value = 0
            snapshot = runner.status()
            self.assertFalse(snapshot.running)
            self.assertEqual(snapshot.state, "succeeded")
            calibration_store.load.assert_called_once()
            self._report(
                "refresh_marks_success",
                True,
                "check=refresh marks success and reloads calibration",
                f"state={snapshot.state}",
                "calibration_reloaded=True",
            )

    def test_start_raises_for_missing_config(self) -> None:
        # Missing config should fail early before launching any subprocess.
        # This prevents a stray process with an invalid working directory.
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            config_path = repo_root / "missing.json"
            calibration_store = mock.Mock()
            runner = CalibrationRunnerService(
                repo_root=repo_root,
                calibration_config_file=config_path,
                calibration_store=calibration_store,
            )

            with self.assertRaises(FileNotFoundError) as context:
                runner.start()
            self._report(
                "start_missing_config",
                True,
                "check=missing config raises before start",
                f"missing={config_path}",
                f"error={context.exception}",
            )


if __name__ == "__main__":
    unittest.main()
