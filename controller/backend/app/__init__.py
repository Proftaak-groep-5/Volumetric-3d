from __future__ import annotations

import sys
from pathlib import Path


def _ensure_repo_root_on_path() -> None:
	# File is controller/backend/app/__init__.py, so parents[3] is repo root.
	repo_root = Path(__file__).resolve().parents[3]
	repo_root_str = str(repo_root)
	if repo_root_str not in sys.path:
		sys.path.insert(0, repo_root_str)


_ensure_repo_root_on_path()

