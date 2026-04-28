"""Tests for the curl-based Jira client — focus on retry/backoff and bulk."""

from __future__ import annotations

import json
from unittest.mock import patch

from mdjira.jira_client import JiraAuth, JiraClient


def _curl_response(stdout_body: str, status: int = 200):
    class FakeCompleted:
        returncode = 0
        stdout = (stdout_body + f"\n{status}").encode()
        stderr = b""

    return FakeCompleted()


def _make_client(**kwargs) -> JiraClient:
    return JiraClient(
        site="https://example.atlassian.net",
        auth=JiraAuth(email="x@example.com", token="t"),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Retry / backoff
# ---------------------------------------------------------------------------


def test_retry_on_503_then_success():
    sleeps: list[float] = []
    client = _make_client(max_attempts=4, backoff_base=1.0, sleep=sleeps.append)

    responses = iter(
        [
            _curl_response("", status=503),
            _curl_response("", status=503),
            _curl_response(json.dumps({"key": "ABC-1"}), status=201),
        ]
    )

    with patch("mdjira.jira_client.subprocess.run", side_effect=lambda *a, **kw: next(responses)):
        result = client.create_issue({"fields": {}})
    assert result == {"key": "ABC-1"}
    # Two backoffs before success: 1s, 2s.
    assert sleeps == [1.0, 2.0]


def test_retry_on_429_then_success():
    sleeps: list[float] = []
    client = _make_client(max_attempts=3, backoff_base=0.5, sleep=sleeps.append)

    responses = iter(
        [
            _curl_response("", status=429),
            _curl_response(json.dumps({"key": "ABC-1"}), status=201),
        ]
    )
    with patch("mdjira.jira_client.subprocess.run", side_effect=lambda *a, **kw: next(responses)):
        client.create_issue({"fields": {}})
    assert sleeps == [0.5]


def test_no_retry_on_400():
    """4xx other than 429 are real errors, not transient — fail fast."""
    sleeps: list[float] = []
    client = _make_client(max_attempts=4, sleep=sleeps.append)
    import contextlib

    with (
        patch(
            "mdjira.jira_client.subprocess.run",
            side_effect=[_curl_response(json.dumps({"errorMessages": ["bad"]}), status=400)],
        ),
        contextlib.suppress(Exception),
    ):
        client.create_issue({"fields": {}})
    assert sleeps == []


def test_backoff_exhausted_returns_last_response():
    """After max_attempts retries on 5xx, the last 5xx is surfaced."""
    sleeps: list[float] = []
    client = _make_client(max_attempts=2, backoff_base=0.1, sleep=sleeps.append)
    with patch(
        "mdjira.jira_client.subprocess.run",
        side_effect=[_curl_response("", status=503), _curl_response("", status=503)],
    ):
        try:
            client.create_issue({"fields": {}})
        except Exception as exc:
            assert "503" in str(exc)
    # Only one sleep — between the two attempts.
    assert sleeps == [0.1]


# ---------------------------------------------------------------------------
# Bulk
# ---------------------------------------------------------------------------


def test_bulk_create_all_succeed():
    client = _make_client()
    response_body = {
        "issues": [{"key": "ABC-1"}, {"key": "ABC-2"}, {"key": "ABC-3"}],
        "errors": [],
    }
    with patch(
        "mdjira.jira_client.subprocess.run",
        return_value=_curl_response(json.dumps(response_body), status=201),
    ):
        keys, errors = client.bulk_create_issues([{"fields": {}}, {"fields": {}}, {"fields": {}}])
    assert keys == ["ABC-1", "ABC-2", "ABC-3"]
    assert errors == []


def test_bulk_create_partial_failure_correlates_indices():
    """When element 1 of 3 fails, the keys array has [key, None, key] and errors lists index 1."""
    client = _make_client()
    response_body = {
        "issues": [{"key": "ABC-1"}, {"key": "ABC-3"}],  # only successful issues, in order
        "errors": [
            {
                "failedElementNumber": 1,
                "elementErrors": {"errorMessages": ["validation failed"]},
            }
        ],
    }
    with patch(
        "mdjira.jira_client.subprocess.run",
        return_value=_curl_response(json.dumps(response_body), status=201),
    ):
        keys, errors = client.bulk_create_issues(
            [{"fields": {"id": 0}}, {"fields": {"id": 1}}, {"fields": {"id": 2}}]
        )
    assert keys == ["ABC-1", None, "ABC-3"]
    assert errors == [(1, "validation failed")]


def test_bulk_create_empty_payload_short_circuits():
    client = _make_client()
    with patch("mdjira.jira_client.subprocess.run") as mock_run:
        keys, errors = client.bulk_create_issues([])
    assert keys == [] and errors == []
    assert mock_run.call_count == 0


def test_bulk_create_payload_too_large_raises():
    client = _make_client()
    payloads = [{"fields": {}}] * 60
    try:
        client.bulk_create_issues(payloads)
    except Exception as exc:
        assert "exceeds" in str(exc)
        return
    raise AssertionError("expected JiraError for >50 payloads")
