from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType


@dataclass(frozen=True, slots=True)
class OrbbecRuntime:
    module: ModuleType | None
    error: str | None = None

    @property
    def available(self) -> bool:
        return self.module is not None


def load_orbbec_runtime() -> OrbbecRuntime:
    """Load Orbbec SDK module lazily so startup can degrade gracefully."""
    try:
        import pyorbbecsdk as sdk  # type: ignore

        return OrbbecRuntime(module=sdk)
    except Exception as exc:
        return OrbbecRuntime(module=None, error=str(exc))
