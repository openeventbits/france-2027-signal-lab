"""First-discovered tests for TRACE import and construction isolation."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
TRACE_ROOT = Path(__file__).resolve().parents[1]


def repository_snapshot() -> dict[str, tuple[str, str]]:
    """Snapshot all repository paths and file bytes without entering .git."""

    snapshot: dict[str, tuple[str, str]] = {}
    for current_root, directory_names, file_names in os.walk(
        REPOSITORY_ROOT, topdown=True, followlinks=False
    ):
        directory_names[:] = sorted(name for name in directory_names if name != ".git")
        root = Path(current_root)
        for name in directory_names:
            path = root / name
            relative = path.relative_to(REPOSITORY_ROOT).as_posix()
            if path.is_symlink():
                snapshot[relative] = ("symlink", os.readlink(path))
            else:
                snapshot[relative] = ("directory", "")
        for name in sorted(file_names):
            if name == ".git":
                continue
            path = root / name
            relative = path.relative_to(REPOSITORY_ROOT).as_posix()
            if path.is_symlink():
                snapshot[relative] = ("symlink", os.readlink(path))
            else:
                snapshot[relative] = ("file", hashlib.sha256(path.read_bytes()).hexdigest())
    return snapshot


def run_python(script: str) -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(REPOSITORY_ROOT)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    subprocess.run(
        [sys.executable, "-B", "-c", script],
        cwd=TRACE_ROOT,
        env=environment,
        check=True,
        capture_output=True,
    )


class RepositoryIsolationTests(unittest.TestCase):
    def test_import_and_draft_build_leave_repository_unchanged(self) -> None:
        self.assertNotIn(
            "tools.fr27_trace",
            sys.modules,
            "TRACE was imported before the repository-isolation baseline",
        )
        before_import = repository_snapshot()
        run_python("import tools.fr27_trace")
        after_import = repository_snapshot()
        self.assertEqual(before_import, after_import, "first import changed the repository tree")

        before_build = repository_snapshot()
        run_python(
            "from tools.fr27_trace import build_draft_trace\n"
            "build_draft_trace(\n"
            "    family='story',\n"
            "    detector_id='isolation_fixture.v1',\n"
            "    primary_entity_ids=['story:fixture'],\n"
            "    observation_window={'start': '2026-08-01', 'end': '2026-08-31'},\n"
            "    evidence={'datum': {'availability': 'not_applicable'}},\n"
            ")"
        )
        self.assertEqual(
            before_build,
            repository_snapshot(),
            "draft construction changed the repository tree",
        )

    def test_render_module_imports_leave_repository_unchanged(self) -> None:
        before_import = repository_snapshot()
        run_python(
            "import socket\n"
            "import subprocess\n"
            "import sys\n"
            "def forbidden(*args, **kwargs):\n"
            "    raise AssertionError('import attempted network or process activity')\n"
            "socket.socket = forbidden\n"
            "subprocess.Popen = forbidden\n"
            "subprocess.run = forbidden\n"
            "import tools.fr27_trace.render\n"
            "import tools.fr27_trace.coverage_anatomy\n"
            "import tools.fr27_trace.flash_shift\n"
            "import tools.fr27_trace.signal_braid\n"
            "import tools.fr27_trace.render.cli\n"
            "import tools.fr27_trace.render.model\n"
            "import tools.fr27_trace.render.paths\n"
            "assert 'build_candidate_attention' not in sys.modules\n"
            "assert 'build_candidate_signals' not in sys.modules"
        )
        self.assertEqual(
            before_import,
            repository_snapshot(),
            "renderer import changed the repository tree",
        )

    def test_production_attention_contract_import_is_side_effect_free(self) -> None:
        before_import = repository_snapshot()
        run_python(
            "import socket\n"
            "import subprocess\n"
            "import sys\n"
            "def forbidden(*args, **kwargs):\n"
            "    raise AssertionError('import attempted network or process activity')\n"
            "socket.socket = forbidden\n"
            "subprocess.Popen = forbidden\n"
            "subprocess.run = forbidden\n"
            "import candidate_attention_contract\n"
            "import tools.fr27_trace.flash_shift\n"
            "import tools.fr27_trace.signal_braid\n"
            "assert 'build_candidate_signals' not in sys.modules"
        )
        self.assertEqual(
            before_import,
            repository_snapshot(),
            "Candidate Attention contract or Flash/Shift import changed the repository tree",
        )

    def test_milestone_defines_no_forbidden_integration_modules(self) -> None:
        forbidden_names = {
            "detector.py",
            "publisher.py",
            "registry.py",
        }
        self.assertTrue(forbidden_names.isdisjoint(path.name for path in TRACE_ROOT.rglob("*.py")))


if __name__ == "__main__":
    unittest.main()
