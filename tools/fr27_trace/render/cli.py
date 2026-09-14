"""Explicit local entry point for the Task 02 PNG smoke renderer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from .model import TraceRenderModel
from .paths import REPOSITORY_ROOT, fixture_path, resolve_output_path


CAPTURE_SCRIPT = Path(__file__).with_name("capture.cjs")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render the frozen TRACE shell to PNG")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--fixture", help="TRACE-local frozen fixture JSON")
    source.add_argument(
        "--candidate-id",
        help="explicit canonical candidate ID for the fixed read-only Task 05 adapter",
    )
    parser.add_argument("--output", required=True, help="PNG beneath _trace_output/")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    destination = resolve_output_path(arguments.output)
    if arguments.fixture is not None:
        source = fixture_path(arguments.fixture)
        with source.open(encoding="utf-8") as fixture_file:
            document = json.load(fixture_file)
    else:
        from ..signal_braid import (
            build_signal_braid_document,
            extract_live_signal_braid,
        )

        document = build_signal_braid_document(
            extract_live_signal_braid(arguments.candidate_id)
        )
    model = TraceRenderModel.from_document(document)

    destination.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        ["node", str(CAPTURE_SCRIPT), "--output", str(destination)],
        cwd=REPOSITORY_ROOT,
        input=json.dumps(model.to_payload(), ensure_ascii=False),
        text=True,
        encoding="utf-8",
        check=True,
    )
    return completed.returncode
