"""Build deterministic localized search entrypoints for FR27."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "index.html"
ENGLISH_OUTPUT = ROOT / "en" / "index.html"

ENGLISH_TITLE = (
    "France 2027 Signal Lab — Source-Linked Election Signals"
)
ENGLISH_DESCRIPTION = (
    "Source-linked polling, election news, candidate coverage and fact checks "
    "for France's 2027 presidential race. No averages, no forecast, no voting advice."
)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"{label}: expected exactly 1 source occurrence, found {count}"
        )
    return text.replace(old, new, 1)


def build_english_entrypoint(source: str) -> str:
    newline = "\r\n" if "\r\n" in source else "\n"
    text = source

    text = replace_once(
        text,
        '<html lang="fr" data-site-root="./"',
        '<html lang="en" data-site-root="/"',
        "document language/site root",
    )

    text = replace_once(
        text,
        "<head>",
        f'<head>{newline}  <base href="/">',
        "English base URL",
    )

    text = replace_once(
        text,
        (
            '<meta name="description" content="'
            "Sondages sourcés, actualité électorale, couverture des candidats "
            "et vérifications pour la présidentielle française de 2027. "
            'Aucune moyenne, aucune prévision, aucun conseil de vote.">'
        ),
        f'<meta name="description" content="{ENGLISH_DESCRIPTION}">',
        "English meta description",
    )

    text = replace_once(
        text,
        '<link rel="canonical" href="https://france2027.app/">',
        '<link rel="canonical" href="https://france2027.app/en/">',
        "English canonical",
    )

    text = replace_once(
        text,
        (
            '<meta property="og:title" content="'
            'France 2027 Signal Lab — Signaux électoraux sourcés">'
        ),
        f'<meta property="og:title" content="{ENGLISH_TITLE}">',
        "English Open Graph title",
    )

    text = replace_once(
        text,
        (
            '<meta property="og:description" content="'
            "Sondages sourcés, actualité électorale, couverture des candidats "
            "et vérifications pour la présidentielle française de 2027. "
            'Aucune moyenne, aucune prévision, aucun conseil de vote.">'
        ),
        f'<meta property="og:description" content="{ENGLISH_DESCRIPTION}">',
        "English Open Graph description",
    )

    text = replace_once(
        text,
        '<meta property="og:url" content="https://france2027.app/">',
        '<meta property="og:url" content="https://france2027.app/en/">',
        "English Open Graph URL",
    )

    text = replace_once(
        text,
        (
            '<meta name="twitter:title" content="'
            'France 2027 Signal Lab — Signaux électoraux sourcés">'
        ),
        f'<meta name="twitter:title" content="{ENGLISH_TITLE}">',
        "English Twitter title",
    )

    text = replace_once(
        text,
        (
            '<meta name="twitter:description" content="'
            "Sondages sourcés, actualité électorale, couverture des candidats "
            "et vérifications pour la présidentielle française de 2027. "
            'Aucune moyenne, aucune prévision, aucun conseil de vote.">'
        ),
        f'<meta name="twitter:description" content="{ENGLISH_DESCRIPTION}">',
        "English Twitter description",
    )

    text = replace_once(
        text,
        "<title>France 2027 Signal Lab — Signaux électoraux sourcés</title>",
        f"<title>{ENGLISH_TITLE}</title>",
        "English document title",
    )

    return text


def main() -> None:
    source = SOURCE.read_bytes().decode("utf-8")
    english = build_english_entrypoint(source)

    ENGLISH_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    ENGLISH_OUTPUT.write_bytes(english.encode("utf-8"))

    print(f"Generated {ENGLISH_OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()