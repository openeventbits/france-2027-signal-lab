"""Project dashboard destinations from published family route authorities."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def navigation_model(root: Path = ROOT) -> dict:
    def load(name):
        return json.loads((root / name).read_text(encoding="utf-8"))

    # Published routes, rather than the monitoring universe, own detail availability.
    candidate_routes = {}
    candidate_hubs = {}
    for route in load("route_registry.json")["routes"]:
        if route["family"] != "candidates":
            continue
        if route["kind"] == "hub":
            candidate_hubs[route["language"]] = route["path"]
        elif route["kind"] == "candidate-detail" and (root / route["source_file"]).is_file():
            candidate_routes.setdefault(route["entity_id"], {})[route["language"]] = route["path"]
    issues = load("issue_pages_manifest.json")
    agenda = load("agenda_pages_manifest.json")
    polls = load("poll_pages_manifest.json")
    model = {
        "hubs": {
            "candidates": candidate_hubs,
            "issues": issues["hubs"],
            "agenda": agenda["hubs"],
            "polls": {"fr": "/sondages/", "en": "/en/sondages/"},
        },
        "candidates": candidate_routes,
        "issues": {}, "agenda": {}, "waves": {}, "events": {},
    }
    for family, manifest, identity in (("issues", issues, "issue_id"), ("agenda", agenda, "topic_id")):
        for page in manifest["pages"]:
            model[family][page[identity]] = {lang: page[f"page_path_{lang}"] for lang in ("fr", "en")}
    published = {page["wave_id"]: page for page in polls["pages"]}
    for wave in load("poll_explorer.json")["waves"]:
        page = published.get(wave["wave_id"])
        if page is None:
            raise ValueError(f"Unpublished poll wave: {wave['wave_id']}")
        model["waves"][wave["wave_id"]] = {lang: page[f"page_path_{lang}"] for lang in ("fr", "en")}
        # build_poll_pages.detail_page enumerates this same scenario list from 1.
        for index, scenario in enumerate(wave["scenarios"], start=1):
            event_id = scenario["event_id"]
            if event_id in model["events"]:
                raise ValueError(f"Ambiguous poll event: {event_id}")
            model["events"][event_id] = [wave["wave_id"], index]
    missing = [event["event_id"] for event in load("polls.json")
               if event["round"] == "first_round" and event["event_id"] not in model["events"]]
    if missing:
        raise ValueError(f"Unmapped first-round poll events: {missing}")
    return model


def poll_href(model: dict, event_id: str, language: str) -> str:
    destination = model["events"].get(event_id)
    if destination is None:
        return model["hubs"]["polls"][language]
    wave_id, index = destination
    return f"{model['waves'][wave_id][language]}#scenario-{index}"
