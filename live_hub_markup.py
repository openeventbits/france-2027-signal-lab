"""Stable data hooks for the existing current-hub markup contract."""
import html
import json
import re


def live_hub_markup(markup, *, family, projection, language):
    from agenda_page_contract import CANONICAL_AGENDA_IDS
    from issue_page_contract import CANONICAL_ISSUE_IDS, ISSUE_DEFINITIONS
    from build_poll_pages import FR_MONTHS, EN_MONTHS, FR_MONTHS_ABBREVIATED, EN_MONTHS_ABBREVIATED
    prefix = "agenda" if family == "agenda" else "issue"
    rows = projection["topics" if family == "agenda" else "issues"]
    ids = CANONICAL_AGENDA_IDS if family == "agenda" else CANONICAL_ISSUE_IDS
    escape = lambda value: html.escape(str(value), quote=True)
    source = projection["generated_at"] if family == "agenda" else projection["live_source_snapshot"]
    dates = {"full": FR_MONTHS if language == "fr" else EN_MONTHS,
             "short": FR_MONTHS_ABBREVIATED if language == "fr" else EN_MONTHS_ABBREVIATED}
    attrs = (f'data-{prefix}-live-url="/{"agenda" if family == "agenda" else "enjeux"}/live.json" '
             f'data-{prefix}-live-ids="{escape(json.dumps(list(ids)))}" '
             f'data-{prefix}-live-snapshot="{escape(source)}" '
             f'data-{prefix}-live-dates="{escape(json.dumps(dates, ensure_ascii=False))}"')
    markup = markup.replace(f'data-{prefix}-card-grid>', f'data-{prefix}-card-grid {attrs}>')
    key = "topic_id" if family == "agenda" else "issue_id"
    for row in rows:
        route = re.escape(escape(row["routes"][language]))
        pattern = rf'<a\b(?=[^>]*class="{prefix}-card")(?=[^>]*href="{route}")[^>]*>.*?</a>'
        def card_hook(match):
            text = match.group()
            text = text.replace(f'data-{prefix}-card', f'data-{prefix}-card data-{key.replace("_", "-")}="{row[key]}"', 1)
            for cls, names in (("counts", ("count", "publishers")), ("window", ("share", "movement")),
                               ("subtopic", ("signal",))):
                start = text.index(f'class="{prefix}-card-{cls}"')
                end = text.index(f'class="{prefix}-card-', start + 10) if cls != "subtopic" else len(text)
                part = text[start:end]
                iterator = iter(names)
                part = re.sub(r'<strong>', lambda _: f'<strong data-{prefix}-live="{next(iterator)}">', part)
                text = text[:start] + part + text[end:]
            text = text.replace(f'class="{prefix}-card-microbars"', f'class="{prefix}-card-microbars" data-{prefix}-live-bars')
            lifecycle = row["lifecycle"]
            text = text.replace(f'class="{prefix}-state is-{lifecycle}"',
                                f'class="{prefix}-state is-{lifecycle}" data-{prefix}-live-state data-static-state="{lifecycle}" data-historical-qualified="{str(row["qualification"]["historical"]).lower()}"')
            if family == "issues":
                definition = next(d for d in ISSUE_DEFINITIONS if d.issue_id == row[key])
                labels = {sid: fr if language == "fr" else en for sid, fr, en in definition.subtopics}
                text = text.replace(f'data-{key.replace("_", "-")}="{row[key]}"',
                                    f'data-{key.replace("_", "-")}="{row[key]}" data-issue-live-subtopics="{escape(json.dumps(labels, ensure_ascii=False))}"')
            return text
        markup, count = re.subn(pattern, card_hook, markup, flags=re.S)
        if count != 1:
            raise ValueError(f"missing current hub card hook: {row[key]}")
    metric_class = "agenda-metrics" if family == "agenda" else "issues-metrics"
    names = ("topics", "items", "source-days", "publishers", "period") if family == "agenda" else ("topics", "items", "publishers", "candidates", "period")
    def metric_hook(match):
        iterator = iter(names)
        return re.sub(r'<strong>', lambda _: f'<strong data-{prefix}-live-metric="{next(iterator)}">', match.group())
    markup = re.sub(rf'<section class="polling-metrics {metric_class}".*?</section>', metric_hook, markup, flags=re.S)
    # Canonical IDs on comparison rows and segments; links/labels are untouched.
    agenda_rows = rows if family == "agenda" else projection["campaign_agenda"]["topics"]
    for row in rows:
        route = re.escape(escape(row["routes"][language]))
        markup = re.sub(rf'(<div class="{prefix}-dumbbell-row")(?=>\s*<a href="{route}")',
                        rf'\1 data-{prefix}-live-movement="{row[key]}"', markup)
    # Composition follows its existing localized sort (Agenda) or source order (Issues).
    ordered = sorted(agenda_rows, key=lambda row: row["labels"][language].casefold()) if family == "agenda" else agenda_rows
    for cls, hook in ((f'{prefix}-agenda-topic', "composition"), (f'{prefix}-agenda-segment', "segment")):
        matches = list(re.finditer(rf'<(?:div|span) class="{cls}(?: [^"]*)?"', markup))
        for index, match in reversed(list(enumerate(matches))):
            row = ordered[index % len(ordered)]
            topic_id = row["topic_id"] if family == "agenda" else row["id"]
            window = "previous" if index < len(ordered) else "latest"
            attrs = f' data-{prefix}-live-{hook}="{topic_id}"'
            if hook == "segment":
                attrs += f' data-live-window="{window}"'
                if family == "issues":
                    from agenda_page_contract import AGENDA_BY_ID
                    definition = AGENDA_BY_ID[topic_id]
                    label = definition.label_fr if language == "fr" else definition.label_en
                    attrs += f' data-live-label="{escape(label)}" data-live-position="{index % len(ordered) + 1}"'
            markup = markup[:match.end()] + attrs + markup[match.end():]
    # Small period captions occur twice in each panel, in previous/latest order.
    for cls, suffix in ((f'{prefix}-dumbbell-legend', 'comparison'), (f'{prefix}-agenda-period', 'composition')):
        start = markup.index(f'class="{cls}"')
        captions = list(re.finditer(r'<small>', markup[start:]))[:2]
        for index, match in reversed(list(enumerate(captions))):
            position = start + match.start()
            markup = markup[:position] + f'<small data-{prefix}-live-period="{suffix}-{"previous" if index == 0 else "latest"}">' + markup[position+7:]
    return markup
