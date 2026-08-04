"""The README's example must be real: run it, and compare its output.

Why this test and not a spot-check
----------------------------------
A README code block is the part of a repository most likely to be wrong and least
likely to be noticed, because nothing executes it. It starts correct, the code
moves underneath it, and it keeps looking correct — a reader's first five minutes
with the project are spent on the one artifact with no test behind it.

So the example is not quoted here from memory. This runs
`python -m examples.ledger_demo` and asserts the README contains **exactly** what
that produced. If a routing rule, a status name, or the retry ceiling changes, the
documentation goes red with the code instead of quietly describing a program that
no longer exists.

Stdlib-only and provider-free, like the core it documents, so it runs in the
dependency-free CI job rather than the one that installs FastAPI.

Encoding note, learned the hard way in a sibling repo: this decodes the child's
output as **UTF-8 explicitly**. Without it, a Windows console hands back cp1252
and an em-dash in the demo becomes mojibake, failing the comparison for a reason
that has nothing to do with the code under test. The example is deliberately ASCII
for the same reason — a doc test should fail for real drift only.
"""

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
EXAMPLE = ROOT / "examples" / "ledger_demo.py"


class ReadmeExampleIsExecutable(unittest.TestCase):
    def setUp(self):
        self.readme = README.read_text(encoding="utf-8")

    def test_the_example_file_exists_and_is_referenced(self):
        self.assertTrue(EXAMPLE.is_file(), "examples/ledger_demo.py is missing")
        self.assertIn("python -m examples.ledger_demo", self.readme)

    def test_the_example_runs_and_the_readme_carries_its_exact_output(self):
        proc = subprocess.run(
            [sys.executable, "-m", "examples.ledger_demo"],
            cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="strict", timeout=120,
        )
        self.assertEqual(proc.returncode, 0,
                         f"the documented example failed to run:\n{proc.stderr}")
        output = proc.stdout.strip()
        self.assertTrue(output, "the example produced no output to compare")
        self.assertIn(output, self.readme,
                      "the README no longer carries what the example actually prints:\n"
                      f"--- actual ---\n{output}")

    def test_the_output_is_deterministic_so_it_can_be_pinned(self):
        """The check above is only meaningful if the example is reproducible.

        The first draft printed workflow ids. They are UUIDs, so the README could
        never have matched twice — the test would have failed on run two and the
        obvious fix would have been to weaken it into a substring check that
        proves nothing.
        """
        runs = []
        for _ in range(2):
            proc = subprocess.run(
                [sys.executable, "-m", "examples.ledger_demo"],
                cwd=ROOT, capture_output=True, text=True,
                encoding="utf-8", errors="strict", timeout=120,
            )
            runs.append(proc.stdout)
        self.assertEqual(runs[0], runs[1],
                         "the example is not reproducible, so its output cannot be pinned")

    def test_the_library_surface_is_actually_shown(self):
        # The gap this whole file was written for: the README advertised a
        # "provider-free core" while never naming the class that IS the core.
        self.assertIn("WorkflowStore", self.readme)
        self.assertIn("from flowproof.core import", self.readme)


if __name__ == "__main__":
    unittest.main(verbosity=2)
