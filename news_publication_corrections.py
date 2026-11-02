"""Source-reviewed publication dates for specific misdated discovery records.

Apply only to derived public entries. Raw inventory and corpus observations
retain the timestamp supplied by the feed. This is not a headline/year filter.
"""
from datetime import datetime, timezone
from urllib.parse import urlsplit

# Verified 2026-11-02: publisher says 'Publié le 1 février 2017 à 21h06'
# (Europe/Paris, UTC+1). The page also reports a September 2026 update;
# neither that update nor the Google News October date is publication.
TF1_SOURCE = ('https://www.tf1info.fr/politique/elections/presidentielle/'
              'presidentielles-2017-nicolas-dupont-aignan-devoile-son-programme-2024438.html')
TF1_FEED_TOKEN = ('CBMi0AFBVV95cUxNRTQ1RXBoUlEzVXZGZnVFNzJHLU91LU1fZ2NHZW1DQWJLRWFVNHZ1'
    'LU5NSlR6VWpyVTBuV0gtZE5IUFRnOU9Kb0VldFhkN3JaVTNTazI1WmVubXh0ZVNZMHI2'
    'Q0pBS0xYRU5jR2hCYjB3dkdVQW9LelhCMW5ObUozR09kQ1JTQmhnRFFBM2tMRTNlN0Jx'
    'alJTY3o1WFlYZVFwbllycjFROXJsdFpjSThLd191TnVVcVJybGRyT1RlS2Q1TUNydmcyQ0'
    'ZZTldVYUVn')


def reviewed_publication_entry(entry):
    """Return a copy with a verified date for this exact article only."""
    result = dict(entry)
    url = urlsplit(str(entry.get('url') or ''))
    is_feed = url.hostname == 'news.google.com' and url.path == '/rss/articles/' + TF1_FEED_TOKEN
    is_publisher = url.hostname in ('www.tf1info.fr', 'tf1info.fr') and url.path.endswith(
        '/presidentielles-2017-nicolas-dupont-aignan-devoile-son-programme-2024438.html')
    if entry.get('publisher') == 'TF1 Info' and (is_feed or is_publisher):
        result['published_at'] = datetime(2017, 2, 1, 20, 6, tzinfo=timezone.utc)
    return result
