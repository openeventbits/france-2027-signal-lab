# Candidate YouTube evidence

YouTube is an independent source of **platform reach / platform activity**.
It is not voting intention, electoral support, approval, candidate momentum,
a forecast, win probability, an FR27 score or popularity among French voters.
FR27 does not combine YouTube with polls, Wikipedia, Polymarket, media, agenda,
events or fact checks into a synthetic score, total or candidate ranking.
Unavailable is not zero. There is no YouTube candidate-page UI in this stage.

## Official source and identity

Reviewed on 17 October 2026 against current Google documentation:

- [channels.list](https://developers.google.com/youtube/data/reference/rest/v3/channels/list)
  accepts pinned channel IDs (batched in groups of 50). Exact `forHandle`
  resolution is supported officially, but this implementation does not need it.
- [Channel resource](https://developers.google.com/youtube/data/reference/rest/v3/channels)
  defines channel statistics, subscriber precision and the uploads playlist.
- [playlistItems.list](https://developers.google.com/youtube/data/reference/rest/v3/playlistItems/list)
  accepts `maxResults=50` and page tokens.
- [Playlist item resource](https://developers.google.com/youtube/data/reference/rest/v3/playlistItems)
  defines `contentDetails.videoPublishedAt` as the video publication time.
  `snippet.publishedAt` is when an item was added to a playlist; it is never
  used as the video publication time here.
- [videos.list](https://developers.google.com/youtube/data/reference/rest/v3/videos/list)
  batches video IDs; [video statistics](https://developers.google.com/youtube/data/reference/rest/v3/videos)
  define current public view counts.
- [Quota costs](https://developers.google.com/youtube/data/determine_quota_cost):
  each of these three list methods costs 1 unit per request; pages and retry
  attempts consume additional requests. There is no `search.list` request.

Only reviewed official personal/campaign channels are pinned in
`youtube_candidate_channels.json`. Each mapped account was linked from a
reviewed first-party site/profile. Exact handles and legacy URLs were resolved
during identity review, validated through the official API and pinned as stable
channel IDs. Titles, search positions,
photos and counts alone do not establish identity. Party, parliamentary-group,
media, fan, supporter and repost/archive channels are not substitutions.
An unmapped candidate may have a YouTube presence: no claim of absence is made.
The complete registry-wide mapping decision ledger is in
[candidate-youtube-mapping-review.md](candidate-youtube-mapping-review.md).

## Collection and publication contract

`candidate_youtube.py` validates mapping, counts, timestamps, candidate rows and
projections. `build_candidate_youtube.py` collects only YouTube Data API v3:

| Endpoint | Parts | Partial response fields |
| --- | --- | --- |
| `GET https://www.googleapis.com/youtube/v3/channels` | `snippet,contentDetails,statistics` | ID, title, uploads playlist, subscriber count/visibility, channel views, public video count |
| `GET https://www.googleapis.com/youtube/v3/playlistItems` | `snippet,contentDetails` | next page token; title, owner channel ID, video ID, video publication time |
| `GET https://www.googleapis.com/youtube/v3/videos` | `snippet,statistics` | ID, owner channel ID, current view count |

No descriptions, tags, comments, transcripts, thumbnails or unnecessary channel
metadata are requested. Channel and recent-video IDs are deduplicated, sorted
and batched. No fuzzy runtime identity search, scraping, unofficial API,
browser-side request or third-party analytics service is involved.

The provider artifact has exactly `schema_version`, `provider`, `generated_at`,
`observed_at`, `stale_after_hours`, `recent_window_days`, `candidates`.
The registry's entire canonical candidate set is covered, including hidden
registry candidates. Candidate rows are sorted by candidate ID.

Rows contain candidate ID and state; channel ID/title/link; subscriber count and
visibility; channel views; public video count; uploads playlist ID; latest upload
time; exact recent upload count when proven; window completeness; recent-video
metric completeness; and recent videos. Recent videos contain exactly video ID,
title, publication time, nullable current views and a stable watch link.

States are `observed`, `unavailable_no_channel`, and
`unavailable_channel_missing`. All unmapped evidence fields are null, including
channel URL and completeness flags. The missing-channel state is recognized by
the contract, but the collector fails the entire observation if a reviewed
channel disappears or is inaccessible; it never replaces a valid snapshot
with invented missing-channel rows. Missing video statistics are different:
the independently observed upload remains, with `view_count=null` and
`recent_video_metrics_complete=false`.

Counts must be unsigned ASCII decimal strings from the API, converted to JSON
integers without rounding. Malformed, negative, empty, null or coerced counts
fail validation. Values above `2**53-1` fail the entire collection, preserving
the prior artifact; no precision-losing JSON number is emitted.

## Recent uploads and completeness

The seven-day interval is **[observed_at minus seven days, observed_at]**,
inclusive at both ends. `observed_at` is the real UTC collection-start instant;
calls subsequently read changing platform data and are not simultaneous.
Future scheduled publication times are excluded. All accepted video times come
from `contentDetails.videoPublishedAt`.

The API reference does not promise the publication-time ordering needed to stop
at the first older item. Therefore the collector follows every page until
exhaustion, with a hard bound of **20 pages / 1,000 items per channel**, and
never stops merely because an older upload was encountered. It requests 50
items per page. Repeated page tokens, duplicate video IDs and pagination errors
fail the whole observation. Missing publication dates (for example on private
items) make completeness unproven; no playlist-addition-time fallback is used.

Reaching the bound with another page available, or seeing an undated item,
sets `recent_window_complete=false`. In that state `uploads_last_7d` and
`latest_upload_at` are null: neither an exact count nor an exact latest-upload
claim is justified by an unordered partial scan. The observed recent-video
records are still retained. On a complete scan the count equals the number of
recent video records, and latest upload is the maximum publication time across
all dated, non-future uploads, even when older than seven days. An empty complete
scan has zero recent uploads and no latest upload. This does not equate a
missing observation with zero activity.

Recent-video statistics are batched across all channels in groups of 50.
Window completeness and metric completeness are independent. A missing video
or omitted view count is null, never zero. No recent-view sum is calculated.
Any current views on recent videos are **current cumulative views on videos
published within the window**, not views gained during the last seven days.

## Interpretation limits

Public `statistics.subscriberCount` is **rounded down to three significant
figures**. FR27 preserves the returned numeric value, without implying exact
precision or calculating small subscriber deltas. Hidden subscribers remain
unavailable (`subscriber_count=null`), even if the API also supplies a count.

Public channel views count viewing activity across formats. They are not unique
viewers, engaged views, deliberate clicks, watch time or electoral support.
Google's current channel and video resource documentation says that, beginning
**24 August 2026**, public `viewCount` across long-form, Live and Shorts counts
when playback starts, including autoplay, pointer hover and click/tap to play.
Pre-change and post-change public view counts must not be treated as
methodologically identical. Cumulative totals can span that discontinuity.

Official-channel uploads measure platform activity, not voting intention.
Audiences can include non-voters, non-French viewers and repeated viewing.
YouTube, Wikipedia and Polymarket measure different concepts and cannot be
compared as interchangeable measures or combined into a synthetic score.

Only a current snapshot is implemented. Existing Wikimedia daily pageviews and
FR27 media/agenda histories have different units and collection semantics.
Subscriber/view histories, 24h/7d deltas and backfills are deferred; none is
fabricated. Future real observations can support a separately reviewed history.

## Freshness, failures and credentials

Freshness is the age of the last successful FR27 YouTube `observed_at`, with a
48-hour threshold. It is not latest-upload age, channel age or metadata age.
A retained artifact naturally becomes stale from its original observation time.

Each HTTP request uses a 20-second timeout, a 2 MiB response bound and at most
three attempts. Network/timeouts and HTTP 408/425/429/500/502/503/504 retry with
bounded backoff (1 then 2 seconds; numeric Retry-After capped at 30 seconds).
HTTP 400/401/403, including quota exhaustion, fail immediately. Invalid JSON,
schema, identity, counts, owner IDs, timestamps or pagination fail closed.
Validation and credential-contamination checks finish before the repository's
existing atomic fsync/replace writer is invoked. Failures exit nonzero and leave
prior artifact bytes intact.

The only key source is `YOUTUBE_API_KEY`. Request query parameters include the
key, but transport diagnostics suppress URLs, reasons, bodies and exception
chains. CLI failure output is generic. Responses and the final artifact are
checked for credential contamination. Offline tests patch a synthetic credential
in memory and assert no leakage in formatted tracebacks, stdout, stderr,
artifacts or projections. Tests never use the real key or call Google.

## Candidate publication transaction

Candidate `data.json` gets an independent top-level `youtube` projection. It is
not nested under candidate signals, attention or Polymarket. The existing
candidate HTML renderer does not consume it: no visible or hidden provider card,
placeholder, subscriber value, channel link, CSS or browser JavaScript is added.

The manifest has a separate `candidate_youtube` lane, hashing both artifact and
mapping, validating the current canonical candidate universe, and using the real
observation time as its evidence timestamp. Its provenance stays independent.

The existing candidate-family scheduled/manual transaction collects YouTube once
after dependency checks. The key is scoped only to that collection step. Failed
collection blocks publication. Publication time uses the new YouTube collection
step's publication instant, then the existing Polymarket collection instant,
then the prior manifest publication time for source-only rebuilds. Provider
observation times are not rewritten. PR/general validation remains offline.

**Deployment requirement:** the user must configure GitHub Actions secret
`YOUTUBE_API_KEY` before eventual push/activation. It has not been configured by
this task. The workflow deliberately fails if production collection lacks it.
No GitHub secrets are created or modified here.
