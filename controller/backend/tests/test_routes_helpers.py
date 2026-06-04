import os
import sys
from pathlib import Path
import tempfile
import time
import unittest

from fastapi import HTTPException

# Ensure the backend app package is importable when running tests from repo root.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.api.routes import _resolve_capture_file, _resolve_latest_capture_file


class RoutesHelperTests(unittest.TestCase):
    def _report(self, test_name: str, success: bool, *details: str) -> None:
        status = "PASS" if success else "FAIL"
        source = Path(__file__).name
        message = " | ".join(str(detail) for detail in details if detail is not None)
        print(f". [{status}] {source}::{test_name}: {message}")

    def test_resolve_latest_capture_file_picks_newest(self) -> None:
        # Ensures newest capture is selected by modification time (mtime).
        # This matches the API behavior when users request "latest".
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir)
            old_file = output / "a.ply"
            new_file = output / "b.ply"
            old_file.write_text("old", encoding="utf-8")
            time.sleep(0.01)
            new_file.write_text("new", encoding="utf-8")
            try:
                resolved = _resolve_latest_capture_file(output)
                self.assertEqual(resolved.name, "b.ply")
            except Exception as exc:
                self._report("resolve_latest_capture_file", False, f"unexpected error: {exc}")
                raise
            else:
                self._report(
                    "resolve_latest_capture_file",
                    True,
                    "check=select newest capture by mtime",
                    f"picked={resolved.name}",
                    "order=mtime",
                )

    def test_resolve_latest_capture_file_raises_if_missing(self) -> None:
        # When no captures are present, the API should return a 404.
        # This avoids returning a misleading empty path.
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir)
            with self.assertRaises(HTTPException) as context:
                _resolve_latest_capture_file(output)
            self.assertEqual(context.exception.status_code, 404)
            self._report(
                "resolve_latest_capture_file_missing",
                True,
                "check=raise 404 when no captures exist",
                f"status={context.exception.status_code}",
                "reason=no captures",
            )

    def test_resolve_capture_file_rejects_bad_name(self) -> None:
        # Rejects path traversal or invalid names to prevent directory escape.
        # This is a security guardrail on file access.
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir)
            with self.assertRaises(HTTPException) as context:
                _resolve_capture_file(output, "../escape.ply")
            self.assertEqual(context.exception.status_code, 400)
            self._report(
                "resolve_capture_file_bad_name",
                True,
                "check=reject path traversal or invalid names",
                "name=../escape.ply",
                f"status={context.exception.status_code}",
            )

    def test_resolve_capture_file_requires_existing_file(self) -> None:
        # Requests for a missing capture file should return a 404.
        # This keeps API behavior consistent with missing resources.
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir)
            with self.assertRaises(HTTPException) as context:
                _resolve_capture_file(output, "missing.ply")
            self.assertEqual(context.exception.status_code, 404)
            self._report(
                "resolve_capture_file_missing",
                True,
                "check=raise 404 for missing capture file",
                "name=missing.ply",
                f"status={context.exception.status_code}",
            )

    def test_resolve_capture_file_accepts_valid(self) -> None:
        # Valid file names should resolve to a path within output dir.
        # Ensures resolve() doesn't escape and respects expected extension.
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir)
            valid = output / "capture.ply"
            valid.write_text("data", encoding="utf-8")
            try:
                resolved = _resolve_capture_file(output, "capture.ply")
                self.assertEqual(resolved, valid.resolve())
                self.assertTrue(os.path.samefile(resolved, valid))
            except Exception as exc:
                self._report("resolve_capture_file_accepts_valid", False, f"unexpected error: {exc}")
                raise
            else:
                self._report(
                    "resolve_capture_file_accepts_valid",
                    True,
                    "check=accept valid capture inside output dir",
                    f"name={valid.name}",
                    f"resolved={resolved}",
                )


if __name__ == "__main__":
    unittest.main()
