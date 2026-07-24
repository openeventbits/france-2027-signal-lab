"""Bounded, retrying HTTP fetches for the news collector."""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import gzip
import http.client
import random
import re
import socket
import ssl
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zlib


DEFAULT_MAX_RESPONSE_BYTES = 5 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 12
MAX_ATTEMPTS = 3
MAX_RETRY_AFTER_SECONDS = 30.0
READ_CHUNK_BYTES = 64 * 1024
RETRYABLE_HTTP_STATUSES = {
    408,
    425,
    429,
    500,
    502,
    503,
    504,
}

_ACCEPT = (
    "application/rss+xml, application/atom+xml, "
    "application/xml, text/xml, */*;q=0.5"
)
_USER_AGENT = "Mozilla/5.0 FR27SignalLab-news-wire/1.0"


@dataclass(frozen=True, slots=True)
class HttpFetchResult:
    """The complete outcome of one logical news-route fetch."""

    success: bool
    not_modified: bool
    status_code: int | None
    response_body: bytes | None
    final_url: str
    attempts: int
    elapsed_ms: int
    etag: str | None
    last_modified: str | None
    failure_category: str | None
    failure_message: str | None
    response_bytes: int
    retry_after_used: bool


class _ResponseTooLarge(Exception):
    pass


class _InvalidResponse(Exception):
    pass


class _LimitedReader:
    def __init__(self, response: Any, maximum_bytes: int):
        self.response = response
        self.maximum_bytes = maximum_bytes
        self.total = 0

    def read(self, size: int = -1) -> bytes:
        remaining_with_sentinel = self.maximum_bytes - self.total + 1
        if size < 0 or size > remaining_with_sentinel:
            size = remaining_with_sentinel
        chunk = self.response.read(size)
        if not isinstance(chunk, bytes):
            raise _InvalidResponse("response read did not return bytes")
        self.total += len(chunk)
        if self.total > self.maximum_bytes:
            raise _ResponseTooLarge(
                f"response exceeds limit {self.maximum_bytes}"
            )
        return chunk


def _safe_header_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if (
        not cleaned
        or len(cleaned) > 1024
        or any(ord(character) < 32 for character in cleaned)
        or any(ord(character) == 127 for character in cleaned)
    ):
        return None
    return cleaned


def _response_header(response: Any, name: str) -> str | None:
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    try:
        return _safe_header_value(headers.get(name))
    except (AttributeError, TypeError):
        return None


def _response_status(response: Any) -> int | None:
    status = getattr(response, "status", None)
    if status is None:
        try:
            status = response.getcode()
        except (AttributeError, TypeError):
            return None
    if isinstance(status, int) and not isinstance(status, bool):
        return status
    return None


def _response_url(response: Any, fallback: str) -> str:
    try:
        value = response.geturl()
    except (AttributeError, TypeError):
        return fallback
    return value if isinstance(value, str) and value else fallback


def _content_length(response: Any) -> int | None:
    value = _response_header(response, "Content-Length")
    if value is None or not value.isascii() or not value.isdecimal():
        return None
    return int(value)


def _read_limited(response: Any, maximum_bytes: int) -> bytes:
    content_length = _content_length(response)
    if content_length is not None and content_length > maximum_bytes:
        raise _ResponseTooLarge(
            f"Content-Length {content_length} exceeds limit {maximum_bytes}"
        )

    content_encoding = (
        _response_header(response, "Content-Encoding") or ""
    ).lower()
    limited_reader = _LimitedReader(response, maximum_bytes)
    reader: Any = limited_reader
    gzip_reader: gzip.GzipFile | None = None
    if content_encoding == "gzip":
        try:
            gzip_reader = gzip.GzipFile(fileobj=limited_reader, mode="rb")
        except (OSError, ValueError) as error:
            raise _InvalidResponse("invalid gzip response") from error
        reader = gzip_reader

    chunks: list[bytes] = []
    total = 0
    try:
        while True:
            chunk = reader.read(
                min(READ_CHUNK_BYTES, maximum_bytes - total + 1)
            )
            if not isinstance(chunk, bytes):
                raise _InvalidResponse("response read did not return bytes")
            if not chunk:
                break
            total += len(chunk)
            if total > maximum_bytes:
                raise _ResponseTooLarge(
                    f"response exceeds limit {maximum_bytes}"
                )
            chunks.append(chunk)
    except _ResponseTooLarge:
        raise
    except (gzip.BadGzipFile, EOFError, zlib.error) as error:
        raise _InvalidResponse("invalid encoded response") from error
    finally:
        if gzip_reader is not None:
            gzip_reader.close()

    return b"".join(chunks)


def _retry_after_seconds(
    response: Any,
    now: Callable[[], datetime],
) -> float | None:
    value = _response_header(response, "Retry-After")
    if value is None:
        return None
    if value.isascii() and value.isdecimal():
        return min(float(value), MAX_RETRY_AFTER_SECONDS)
    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if retry_at.tzinfo is None or retry_at.utcoffset() is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    current = now()
    if current.tzinfo is None or current.utcoffset() is None:
        current = current.replace(tzinfo=timezone.utc)
    delay = (retry_at - current.astimezone(timezone.utc)).total_seconds()
    return min(max(0.0, delay), MAX_RETRY_AFTER_SECONDS)


def _failure_category(error: BaseException) -> str:
    if isinstance(error, (TimeoutError, socket.timeout)):
        return "timeout"
    if isinstance(error, URLError):
        if isinstance(error.reason, (TimeoutError, socket.timeout)):
            return "timeout"
        return "network_error"
    if isinstance(
        error,
        (
            ConnectionError,
            http.client.IncompleteRead,
            OSError,
        ),
    ):
        return "network_error"
    return "unknown_error"


def _clean_message(message: Any) -> str:
    text = " ".join(str(message).split())
    if not text:
        return "request failed"
    text = re.sub(
        r"(https?://)[^/\s:@]+:[^@/\s]+@",
        r"\1[redacted]@",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"([?&](?:api[_-]?key|token|password)=)[^&\s]+",
        r"\1[redacted]",
        text,
        flags=re.IGNORECASE,
    )
    return text[:300]


def _http_failure(status: int, reason: Any = None) -> tuple[str, str]:
    if status == 429:
        category = "rate_limited"
    elif 400 <= status <= 499:
        category = "http_4xx"
    elif 500 <= status <= 599:
        category = "http_5xx"
    else:
        category = "invalid_response"
    detail = _clean_message(reason) if reason else ""
    message = f"HTTP {status}"
    if detail and detail != str(status):
        message = f"{message}: {detail}"
    return category, message


def _elapsed_ms(started: float, monotonic: Callable[[], float]) -> int:
    return max(0, round((monotonic() - started) * 1000))


def fetch_news_route(
    url: str,
    *,
    etag: str | None = None,
    last_modified: str | None = None,
    timeout: int | float = DEFAULT_TIMEOUT_SECONDS,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    opener: Callable[..., Any] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[float, float], float] = random.uniform,
    monotonic: Callable[[], float] = time.monotonic,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    context_factory: Callable[[], ssl.SSLContext] = ssl.create_default_context,
) -> HttpFetchResult:
    """Fetch one news route with bounded retries and response size."""
    if not isinstance(url, str) or not url:
        raise ValueError("url must be a non-empty string")
    if (
        not isinstance(max_response_bytes, int)
        or isinstance(max_response_bytes, bool)
        or max_response_bytes < 1
    ):
        raise ValueError("max_response_bytes must be a positive integer")

    effective_opener = opener or urlopen
    request_headers = {
        "Accept": _ACCEPT,
        "User-Agent": _USER_AGENT,
    }
    valid_etag = _safe_header_value(etag)
    valid_last_modified = _safe_header_value(last_modified)
    if valid_etag is not None:
        request_headers["If-None-Match"] = valid_etag
    if valid_last_modified is not None:
        request_headers["If-Modified-Since"] = valid_last_modified

    started = monotonic()
    retry_after_used = False
    last_status: int | None = None
    last_url = url

    for attempt_number in range(1, MAX_ATTEMPTS + 1):
        response: Any = None
        try:
            request = Request(url, headers=request_headers)
            response = effective_opener(
                request,
                timeout=timeout,
                context=context_factory(),
            )
        except HTTPError as error:
            response = error
        except Exception as error:
            category = _failure_category(error)
            if (
                category in {"timeout", "network_error"}
                and attempt_number < MAX_ATTEMPTS
            ):
                delay = 0.5 * (2 ** (attempt_number - 1))
                delay += max(0.0, min(0.1, jitter(0.0, 0.1)))
                sleep(min(delay, MAX_RETRY_AFTER_SECONDS))
                continue
            return HttpFetchResult(
                success=False,
                not_modified=False,
                status_code=last_status,
                response_body=None,
                final_url=last_url,
                attempts=attempt_number,
                elapsed_ms=_elapsed_ms(started, monotonic),
                etag=None,
                last_modified=None,
                failure_category=category,
                failure_message=_clean_message(error),
                response_bytes=0,
                retry_after_used=retry_after_used,
            )

        with closing(response):
            status = _response_status(response)
            final_url = _response_url(response, url)
            last_status = status
            last_url = final_url
            response_etag = _response_header(response, "ETag")
            response_last_modified = _response_header(
                response,
                "Last-Modified",
            )

            if status == 304:
                return HttpFetchResult(
                    success=True,
                    not_modified=True,
                    status_code=304,
                    response_body=None,
                    final_url=final_url,
                    attempts=attempt_number,
                    elapsed_ms=_elapsed_ms(started, monotonic),
                    etag=response_etag,
                    last_modified=response_last_modified,
                    failure_category=None,
                    failure_message=None,
                    response_bytes=0,
                    retry_after_used=retry_after_used,
                )

            if status != 200:
                if status is None:
                    category = "invalid_response"
                    message = "response has no valid HTTP status"
                else:
                    category, message = _http_failure(
                        status,
                        getattr(response, "reason", None),
                    )
                if (
                    status in RETRYABLE_HTTP_STATUSES
                    and attempt_number < MAX_ATTEMPTS
                ):
                    retry_after = _retry_after_seconds(response, now)
                    if retry_after is not None:
                        delay = retry_after
                        retry_after_used = True
                    else:
                        delay = 0.5 * (2 ** (attempt_number - 1))
                    delay += max(0.0, min(0.1, jitter(0.0, 0.1)))
                    sleep(min(delay, MAX_RETRY_AFTER_SECONDS))
                    continue
                return HttpFetchResult(
                    success=False,
                    not_modified=False,
                    status_code=status,
                    response_body=None,
                    final_url=final_url,
                    attempts=attempt_number,
                    elapsed_ms=_elapsed_ms(started, monotonic),
                    etag=None,
                    last_modified=None,
                    failure_category=category,
                    failure_message=message,
                    response_bytes=0,
                    retry_after_used=retry_after_used,
                )

            try:
                body = _read_limited(response, max_response_bytes)
            except _ResponseTooLarge as error:
                return HttpFetchResult(
                    success=False,
                    not_modified=False,
                    status_code=200,
                    response_body=None,
                    final_url=final_url,
                    attempts=attempt_number,
                    elapsed_ms=_elapsed_ms(started, monotonic),
                    etag=None,
                    last_modified=None,
                    failure_category="response_too_large",
                    failure_message=_clean_message(error),
                    response_bytes=0,
                    retry_after_used=retry_after_used,
                )
            except _InvalidResponse as error:
                return HttpFetchResult(
                    success=False,
                    not_modified=False,
                    status_code=200,
                    response_body=None,
                    final_url=final_url,
                    attempts=attempt_number,
                    elapsed_ms=_elapsed_ms(started, monotonic),
                    etag=None,
                    last_modified=None,
                    failure_category="invalid_response",
                    failure_message=_clean_message(error),
                    response_bytes=0,
                    retry_after_used=retry_after_used,
                )
            except Exception as error:
                category = _failure_category(error)
                if (
                    category in {"timeout", "network_error"}
                    and attempt_number < MAX_ATTEMPTS
                ):
                    delay = 0.5 * (2 ** (attempt_number - 1))
                    delay += max(0.0, min(0.1, jitter(0.0, 0.1)))
                    sleep(min(delay, MAX_RETRY_AFTER_SECONDS))
                    continue
                return HttpFetchResult(
                    success=False,
                    not_modified=False,
                    status_code=200,
                    response_body=None,
                    final_url=final_url,
                    attempts=attempt_number,
                    elapsed_ms=_elapsed_ms(started, monotonic),
                    etag=None,
                    last_modified=None,
                    failure_category=category,
                    failure_message=_clean_message(error),
                    response_bytes=0,
                    retry_after_used=retry_after_used,
                )

            return HttpFetchResult(
                success=True,
                not_modified=False,
                status_code=200,
                response_body=body,
                final_url=final_url,
                attempts=attempt_number,
                elapsed_ms=_elapsed_ms(started, monotonic),
                etag=response_etag,
                last_modified=response_last_modified,
                failure_category=None,
                failure_message=None,
                response_bytes=len(body),
                retry_after_used=retry_after_used,
            )

    raise AssertionError("bounded fetch loop exhausted unexpectedly")
