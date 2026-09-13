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
    parser.add_argument("--fixture", required=True, help="TRACE-local frozen fixture JSON")
    parser.add_argument("--output", required=True, help="PNG beneath _trace_output/")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    source = fixture_path(arguments.fixture)
    destination = resolve_output_path(arguments.output)
    with source.open(encoding="utf-8") as fixture_file:
        model = TraceRenderModel.from_document(json.load(fixture_file))

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
