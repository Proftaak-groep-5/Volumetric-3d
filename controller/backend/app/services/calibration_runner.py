from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.services.calibration_store import CalibrationStore

LOGGER = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class CalibrationRunStatusSnapshot:
    state: str
    running: bool
    started_at_utc: str | None
    finished_at_utc: str | None
    return_code: int | None
    message: str | None
    command: list[str] | None
    log_file: str | None
    output_tail: str | None


class CalibrationRunnerService:
    def __init__(
        self,
        *,
        repo_root: Path,
        calibration_config_file: Path,
        calibration_store: CalibrationStore,
    ) -> None:
        self._repo_root = Path(repo_root).resolve()
        self._calibration_config_file = Path(calibration_config_file).resolve()
        self._calibration_store = calibration_store

        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._process_log_handle = None
        self._state = "idle"
        self._started_at_utc: str | None = None
        self._finished_at_utc: str | None = None
        self._return_code: int | None = None
        self._message: str | None = None
        self._command: list[str] | None = None
        self._log_file: Path | None = None

    def start(self) -> CalibrationRunStatusSnapshot:
        with self._lock:
            self._refresh_locked()

            if self._process is not None:
                raise RuntimeError("Calibration is already running")

            if not self._calibration_config_file.exists():
                raise FileNotFoundError(f"Calibration config file was not found: {self._calibration_config_file}")

            log_dir = self._repo_root / "calib_out" / "controller_backend"
            log_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            log_file = log_dir / f"calibration_{timestamp}.log"

            command = [
                sys.executable,
                "-m",
                "calibration.main",
                "--config",
                str(self._calibration_config_file),
            ]

            try:
                log_handle = log_file.open("w", encoding="utf-8")
                creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW") else 0
                process = subprocess.Popen(
                    command,
                    cwd=str(self._repo_root),
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    text=True,
                    creationflags=creationflags,
                )
            except Exception:
                try:
                    log_handle.close()
                except Exception:
                    pass
                raise

            self._process = process
            self._process_log_handle = log_handle
            self._state = "running"
            self._started_at_utc = _utc_now_iso()
            self._finished_at_utc = None
            self._return_code = None
            self._message = "Calibration started"
            self._command = command
            self._log_file = log_file

            monitor = threading.Thread(target=self._monitor_process, args=(process,), daemon=True, name="calibration-runner-monitor")
            monitor.start()

            LOGGER.info("Started calibration process pid=%s config=%s", process.pid, self._calibration_config_file)
            return self._snapshot_locked()

    def status(self) -> CalibrationRunStatusSnapshot:
        with self._lock:
            self._refresh_locked()
            return self._snapshot_locked()

    def shutdown(self) -> None:
        process: subprocess.Popen[str] | None = None
        with self._lock:
            self._refresh_locked()
            process = self._process

        if process is None:
            return

        try:
            process.terminate()
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2.0)
        except Exception as exc:
            LOGGER.warning("Failed while stopping calibration process pid=%s: %s", process.pid, exc)

        with self._lock:
            self._refresh_locked()

    def _monitor_process(self, process: subprocess.Popen[str]) -> None:
        try:
            process.wait()
        except Exception:
            return
        with self._lock:
            if self._process is process:
                self._refresh_locked()

    def _refresh_locked(self) -> None:
        if self._process is None:
            return

        return_code = self._process.poll()
        if return_code is None:
            return

        self._return_code = int(return_code)
        self._finished_at_utc = _utc_now_iso()
        self._state = "succeeded" if return_code == 0 else "failed"
        self._message = "Calibration completed successfully" if return_code == 0 else f"Calibration failed with exit code {return_code}"

        if self._process_log_handle is not None:
            try:
                self._process_log_handle.close()
            except Exception:
                pass
            self._process_log_handle = None

        self._process = None

        if return_code == 0:
            try:
                self._calibration_store.load()
                self._message = "Calibration completed and calibration file was reloaded"
            except Exception as exc:
                self._message = f"Calibration completed, but reloading calibration file failed: {exc}"
                LOGGER.exception("Calibration reload after successful run failed: %s", exc)

    def _snapshot_locked(self) -> CalibrationRunStatusSnapshot:
        return CalibrationRunStatusSnapshot(
            state=self._state,
            running=self._process is not None,
            started_at_utc=self._started_at_utc,
            finished_at_utc=self._finished_at_utc,
            return_code=self._return_code,
            message=self._message,
            command=None if self._command is None else list(self._command),
            log_file=str(self._log_file) if self._log_file is not None else None,
            output_tail=self._read_log_tail(self._log_file),
        )

    @staticmethod
    def _read_log_tail(log_file: Path | None, *, max_lines: int = 40, max_chars: int = 6000) -> str | None:
        if log_file is None or not log_file.exists():
            return None
        try:
            lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            return None
        if not lines:
            return None
        tail_lines = lines[-max_lines:]
        text = "\n".join(tail_lines).strip()
        if not text:
            return None
        if len(text) > max_chars:
            return text[-max_chars:]
        return text

