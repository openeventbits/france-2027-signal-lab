"""Explicit-path, atomic and deterministic projection CLI."""
import argparse
import json
import os
from pathlib import Path
import tempfile


def serialize(payload):
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode("utf-8")


def atomic_write(path, content):
    path = Path(path)
    if path.exists() and path.read_bytes() == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(builder, output, argv=None):
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=builder.__doc__)
    parser.add_argument("--news", type=Path, default=root / "news_wire.json")
    parser.add_argument("--output", type=Path, default=root / output)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.news.resolve() == args.output.resolve():
            raise ValueError("projection output must differ from News Wire input")
        content = serialize(builder(json.loads(args.news.read_text(encoding="utf-8"))))
        if args.check:
            if not args.output.exists() or args.output.read_bytes() != content:
                raise ValueError("projection is missing or differs from News Wire")
        else:
            atomic_write(args.output, content)
    except (OSError, ValueError, RuntimeError, TypeError, KeyError) as error:
        print(f"Live projection failed: {error}")
        return 1
    return 0
