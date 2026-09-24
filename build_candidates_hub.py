"""Generate the bilingual Candidates directory from the canonical active roster."""

from __future__ import annotations

import argparse
from pathlib import Path

from build_candidate_reference import (
    ROOT,
    _newline_equivalent,
    atomic_write,
    build_all_active_artifacts,
    load_sources,
)


HUB_PATHS = (
    Path("candidates") / "index.html",
    Path("en") / "candidates" / "index.html",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output_root = args.output_root or args.root
    if not output_root.is_absolute():
        output_root = args.root / output_root

    artifacts = build_all_active_artifacts(load_sources(args.root), args.root)
    for relative_path in HUB_PATHS:
        content = artifacts[relative_path]
        target = output_root / relative_path
        if args.check:
            if (
                not target.exists()
                or not _newline_equivalent(target.read_bytes(), content)
            ):
                raise SystemExit(f"stale generated Candidates hub: {target}")
        else:
            atomic_write(target, content)
            print(f"wrote {target}")

    if args.check:
        print("bilingual Candidates hubs are current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
