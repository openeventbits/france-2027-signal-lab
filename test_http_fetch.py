import gzip
import socket
import unittest
from urllib.error import HTTPError

from http_fetch import DEFAULT_MAX_RESPONSE_BYTES, fetch_news_route


class FakeResponse:
    def __init__(
        self,
        status=200,
        body=b"",
        *,
        headers=None,
        url="https://example.test/final",
        reason=None,
    ):
        self.status = status
        self.body = body
        self.headers = dict(headers or {})
        self.url = url
        self.reason = reason
        self.offset = 0
        self.read_calls = 0
        self.closed = False

    def read(self, size=-1):
        self.read_calls += 1
        if size is None or size < 0:
            size = len(self.body) - self.offset
        chunk = self.body[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk

    def geturl(self):
        return self.url

    def getcode(self):
        return self.status

    def close(self):
        self.closed = True


class SequenceOpener:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def __call__(self, request, **_kwargs):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class ReadErrorResponse(FakeResponse):
    def read(self, size=-1):
        self.read_calls += 1
        raise socket.timeout("timed out while reading")


def http_error(status, *, headers=None, reason=None):
    return HTTPError(
        "https://example.test/feed",
        status,
        reason or f"status {status}",
        dict(headers or {}),
        None,
    )


def fetch_with(opener, **kwargs):
    sleeps = kwargs.pop("sleeps", [])
    result = fetch_news_route(
        "https://example.test/feed",
        opener=opener,
        sleep=sleeps.append,
        jitter=lambda _start, _end: 0.0,
        monotonic=lambda: 0.0,
        context_factory=lambda: None,
        **kwargs,
    )
    return result, sleeps


class HttpFetchTests(unittest.TestCase):
    def test_default_response_limit_is_five_mib(self):
        self.assertEqual(DEFAULT_MAX_RESPONSE_BYTES, 5 * 1024 * 1024)

    def test_successful_200_response(self):
        response = FakeResponse(
            body=b"<rss/>",
            headers={
                "ETag": '"v1"',
                "Last-Modified": "Wed, 22 Jul 2026 08:00:00 GMT",
            },
        )
        opener = SequenceOpener(response)

        result, sleeps = fetch_with(opener)

        self.assertTrue(result.success)
        self.assertFalse(result.not_modified)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.response_body, b"<rss/>")
        self.assertEqual(result.response_bytes, 6)
        self.assertEqual(result.attempts, 1)
        self.assertEqual(result.etag, '"v1"')
        self.assertEqual(
            result.last_modified,
            "Wed, 22 Jul 2026 08:00:00 GMT",
        )
        self.assertEqual(sleeps, [])

    def test_etag_is_sent_as_if_none_match(self):
        opener = SequenceOpener(FakeResponse())
        fetch_with(opener, etag='"v1"')
        self.assertEqual(
            opener.requests[0].get_header("If-none-match"),
            '"v1"',
        )

    def test_last_modified_is_sent_as_if_modified_since(self):
        opener = SequenceOpener(FakeResponse())
        fetch_with(
            opener,
            last_modified="Wed, 22 Jul 2026 08:00:00 GMT",
        )
        self.assertEqual(
            opener.requests[0].get_header("If-modified-since"),
            "Wed, 22 Jul 2026 08:00:00 GMT",
        )

    def test_both_validators_may_be_sent_together(self):
        opener = SequenceOpener(FakeResponse())
        fetch_with(
            opener,
            etag='"v1"',
            last_modified="Wed, 22 Jul 2026 08:00:00 GMT",
        )
        request = opener.requests[0]
        self.assertEqual(request.get_header("If-none-match"), '"v1"')
        self.assertIsNotNone(request.get_header("If-modified-since"))

    def test_304_is_successful_and_body_is_not_read(self):
        response = FakeResponse(
            status=304,
            body=b"must not be read",
            headers={"ETag": '"v2"'},
        )
        result, _sleeps = fetch_with(SequenceOpener(response))
        self.assertTrue(result.success)
        self.assertTrue(result.not_modified)
        self.assertEqual(result.status_code, 304)
        self.assertIsNone(result.response_body)
        self.assertEqual(result.response_bytes, 0)
        self.assertEqual(response.read_calls, 0)

    def test_timeout_retries_and_eventually_succeeds(self):
        opener = SequenceOpener(
            socket.timeout("slow"),
            socket.timeout("still slow"),
            FakeResponse(body=b"ok"),
        )
        result, sleeps = fetch_with(opener)
        self.assertTrue(result.success)
        self.assertEqual(result.attempts, 3)
        self.assertEqual(sleeps, [0.5, 1.0])

    def test_timeout_while_reading_retries(self):
        opener = SequenceOpener(
            ReadErrorResponse(),
            FakeResponse(body=b"ok"),
        )
        result, sleeps = fetch_with(opener)
        self.assertTrue(result.success)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(sleeps, [0.5])

    def test_connection_failure_retries(self):
        opener = SequenceOpener(
            ConnectionResetError("reset"),
            FakeResponse(body=b"ok"),
        )
        result, sleeps = fetch_with(opener)
        self.assertTrue(result.success)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(sleeps, [0.5])

    def test_http_503_retries(self):
        opener = SequenceOpener(
            http_error(503),
            FakeResponse(body=b"ok"),
        )
        result, sleeps = fetch_with(opener)
        self.assertTrue(result.success)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(sleeps, [0.5])

    def test_http_429_respects_retry_after(self):
        opener = SequenceOpener(
            http_error(429, headers={"Retry-After": "7"}),
            FakeResponse(body=b"ok"),
        )
        result, sleeps = fetch_with(opener)
        self.assertTrue(result.success)
        self.assertTrue(result.retry_after_used)
        self.assertEqual(sleeps, [7.0])

    def test_retry_after_is_capped(self):
        opener = SequenceOpener(
            http_error(429, headers={"Retry-After": "9999"}),
            FakeResponse(body=b"ok"),
        )
        result, sleeps = fetch_with(opener)
        self.assertTrue(result.success)
        self.assertTrue(result.retry_after_used)
        self.assertEqual(sleeps, [30.0])

    def test_http_404_does_not_retry(self):
        opener = SequenceOpener(http_error(404))
        result, sleeps = fetch_with(opener)
        self.assertFalse(result.success)
        self.assertEqual(result.failure_category, "http_4xx")
        self.assertIn("HTTP 404", result.failure_message)
        self.assertEqual(result.attempts, 1)
        self.assertEqual(sleeps, [])

    def test_http_405_does_not_retry(self):
        opener = SequenceOpener(http_error(405, reason="Method Not Allowed"))
        result, _sleeps = fetch_with(opener)
        self.assertFalse(result.success)
        self.assertEqual(result.status_code, 405)
        self.assertIn("HTTP 405", result.failure_message)
        self.assertEqual(result.attempts, 1)

    def test_retry_limit_is_three_total_attempts(self):
        opener = SequenceOpener(
            socket.timeout("one"),
            socket.timeout("two"),
            socket.timeout("three"),
        )
        result, sleeps = fetch_with(opener)
        self.assertFalse(result.success)
        self.assertEqual(result.failure_category, "timeout")
        self.assertEqual(result.attempts, 3)
        self.assertEqual(len(opener.requests), 3)
        self.assertEqual(sleeps, [0.5, 1.0])

    def test_backoff_jitter_is_bounded(self):
        sleeps = []
        result = fetch_news_route(
            "https://example.test/feed",
            opener=SequenceOpener(
                socket.timeout("one"),
                socket.timeout("two"),
                FakeResponse(body=b"ok"),
            ),
            sleep=sleeps.append,
            jitter=lambda _start, _end: 999.0,
            monotonic=lambda: 0.0,
            context_factory=lambda: None,
        )
        self.assertTrue(result.success)
        self.assertEqual(sleeps, [0.6, 1.1])

    def test_invalid_retry_after_is_ignored(self):
        opener = SequenceOpener(
            http_error(503, headers={"Retry-After": "not-a-delay"}),
            FakeResponse(body=b"ok"),
        )
        result, sleeps = fetch_with(opener)
        self.assertTrue(result.success)
        self.assertFalse(result.retry_after_used)
        self.assertEqual(sleeps, [0.5])

    def test_large_content_length_fails_before_body_read(self):
        response = FakeResponse(
            body=b"small fake body",
            headers={"Content-Length": "11"},
        )
        result, _sleeps = fetch_with(
            SequenceOpener(response),
            max_response_bytes=10,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.failure_category, "response_too_large")
        self.assertEqual(response.read_calls, 0)

    def test_streaming_response_exceeding_limit_fails(self):
        response = FakeResponse(body=b"123456")
        result, _sleeps = fetch_with(
            SequenceOpener(response),
            max_response_bytes=5,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.failure_category, "response_too_large")
        self.assertIsNone(result.response_body)
        self.assertEqual(result.response_bytes, 0)

    def test_exact_limit_response_succeeds(self):
        result, _sleeps = fetch_with(
            SequenceOpener(FakeResponse(body=b"12345")),
            max_response_bytes=5,
        )
        self.assertTrue(result.success)
        self.assertEqual(result.response_body, b"12345")
        self.assertEqual(result.response_bytes, 5)

    def test_partial_oversized_body_is_never_returned(self):
        result, _sleeps = fetch_with(
            SequenceOpener(FakeResponse(body=b"123456789")),
            max_response_bytes=5,
        )
        self.assertFalse(result.success)
        self.assertIsNone(result.response_body)
        self.assertEqual(result.response_bytes, 0)

    def test_gzip_response_preserves_parser_compatible_bytes(self):
        raw = b"<rss><channel/></rss>"
        response = FakeResponse(
            body=gzip.compress(raw),
            headers={"Content-Encoding": "gzip"},
        )
        result, _sleeps = fetch_with(SequenceOpener(response))
        self.assertTrue(result.success)
        self.assertEqual(result.response_body, raw)
        self.assertEqual(result.response_bytes, len(raw))

    def test_gzip_transfer_bytes_are_also_bounded(self):
        response = FakeResponse(
            body=gzip.compress(b""),
            headers={"Content-Encoding": "gzip"},
        )
        result, _sleeps = fetch_with(
            SequenceOpener(response),
            max_response_bytes=5,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.failure_category, "response_too_large")
        self.assertIsNone(result.response_body)


if __name__ == "__main__":
    unittest.main()
