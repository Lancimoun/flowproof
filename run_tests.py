"""Run FlowProof's full suite with Starlette deprecations made fatal."""

from __future__ import annotations

import sys
import unittest
import warnings

from starlette.exceptions import StarletteDeprecationWarning


def configure_warning_policy() -> None:
    """Apply third-party warning filters only after Starlette is importable."""
    warnings.filterwarnings("error", category=StarletteDeprecationWarning)


def main() -> int:
    configure_warning_policy()
    suite = unittest.defaultTestLoader.discover("tests")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
