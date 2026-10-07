"""Build the current agenda coverage projection from published News Wire data."""
from live_projection_contract import build_agenda_live_projection
from live_projection_io import main as run


def main(argv=None):
    return run(build_agenda_live_projection, "agenda/live.json", argv)


if __name__ == "__main__":
    raise SystemExit(main())
