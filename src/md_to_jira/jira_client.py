"""Jira Cloud REST API v3 client using curl.

We shell out to curl rather than using urllib/requests for two reasons:

1. python.org macOS builds ship with their own bundled OpenSSL and may
   miss the system root CAs, leading to spurious SSL handshake failures
   against atlassian.net. The system curl uses the OS keychain.
2. curl gives us a stable, debuggable command line we can echo on errors.

The client is intentionally tiny — only the endpoints we need.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# How many issues Jira accepts in one bulk request. The cap is 50 per
# the REST API v3 docs; we keep it as a constant so tests can stub it.
MAX_BULK_BATCH = 50

# Retry policy for transient server-side failures. We retry only on
# 429 (rate limit) and 5xx; anything else is a real error and bubbles
# up immediately. Back-off is exponential, capped, with a small jitter
# multiplier on each attempt — enough to recover from a brief Jira
# blip without grinding to a halt.
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_DEFAULT_MAX_ATTEMPTS = 4
_DEFAULT_BACKOFF_BASE = 1.0  # seconds
_DEFAULT_BACKOFF_CAP = 30.0  # seconds


class JiraError(RuntimeError):
    pass


@dataclass
class JiraAuth:
    email: str
    token: str

    def header(self) -> str:
        creds = f"{self.email}:{self.token}".encode()
        return "Basic " + base64.b64encode(creds).decode()


def load_auth(email: str | None = None) -> JiraAuth:
    """Resolve email + token from CLI flag / env / config / file.

    Resolution order (highest priority first):
      Email: --email flag, $JIRA_EMAIL, config.yaml defaults.email, ~/.jira-email
      Token: $JIRA_API_TOKEN, ~/.jira-token (chmod 600)

    File-based fallbacks exist because Claude Code (and any tool that
    spawns subshells) doesn't inherit interactive `export`s. The config
    file is the recommended path; ~/.jira-email is kept as a fallback
    for users on the older flow.
    """
    # Local import to avoid a circular dependency at module load time.
    from .config import config_email

    resolved_email = email or os.environ.get("JIRA_EMAIL") or config_email()
    if not resolved_email:
        email_path = Path.home() / ".jira-email"
        if email_path.exists():
            resolved_email = email_path.read_text(encoding="utf-8").strip()
    if not resolved_email:
        raise JiraError(
            "Jira email not set. Run `md-to-jira init` to set it, export JIRA_EMAIL, or pass --email."
        )

    token = os.environ.get("JIRA_API_TOKEN")
    if not token:
        token_path = Path.home() / ".jira-token"
        if token_path.exists():
            mode = token_path.stat().st_mode & 0o777
            if mode & 0o077:
                raise JiraError(
                    f"{token_path} has insecure permissions {oct(mode)}; run: chmod 600 ~/.jira-token"
                )
            token = token_path.read_text(encoding="utf-8").strip()
    if not token:
        raise JiraError(
            "Jira API token not set. Write it to ~/.jira-token (chmod 600) or export JIRA_API_TOKEN."
        )

    return JiraAuth(email=resolved_email, token=token)


@dataclass
class JiraResponse:
    status: int
    body: Any  # parsed JSON, or raw text on parse failure
    raw: str

    def ok(self) -> bool:
        return 200 <= self.status < 300


class JiraClient:
    def __init__(
        self,
        site: str,
        auth: JiraAuth,
        *,
        timeout: int = 30,
        max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
        backoff_base: float = _DEFAULT_BACKOFF_BASE,
        backoff_cap: float = _DEFAULT_BACKOFF_CAP,
        sleep: Any = time.sleep,
    ):
        self.site = site.rstrip("/")
        self.auth = auth
        self.timeout = timeout
        self.max_attempts = max(1, max_attempts)
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        # Indirected so tests can pass a mock and avoid real sleeping.
        self._sleep = sleep

    # ------------------------------------------------------------------
    # Low level
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> JiraResponse:
        """Make a request with exponential-backoff retry on 429/5xx."""
        last: JiraResponse | None = None
        for attempt in range(1, self.max_attempts + 1):
            resp = self._request_once(method, path, json_body=json_body)
            if resp.status not in _RETRY_STATUSES or attempt == self.max_attempts:
                return resp
            # Server says "try again later" — back off and loop.
            delay = min(self.backoff_cap, self.backoff_base * (2 ** (attempt - 1)))
            self._sleep(delay)
            last = resp
        # Loop is exhaustive; this is unreachable but keeps mypy happy.
        assert last is not None
        return last

    def _request_once(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> JiraResponse:
        url = f"{self.site}{path}"
        cmd = [
            "curl",
            "-sS",
            "-w",
            "\n%{http_code}",
            "-X",
            method,
            "-H",
            f"Authorization: {self.auth.header()}",
            "-H",
            "Accept: application/json",
        ]
        if json_body is not None:
            cmd += [
                "-H",
                "Content-Type: application/json",
                "--data-binary",
                "@-",
            ]
            input_bytes: bytes | None = json.dumps(json_body).encode("utf-8")
        else:
            input_bytes = None
        cmd.append(url)

        result = subprocess.run(
            cmd,
            input=input_bytes,
            capture_output=True,
            timeout=self.timeout,
        )
        if result.returncode != 0:
            raise JiraError(
                f"curl failed ({result.returncode}) for {method} {url}: "
                f"{result.stderr.decode('utf-8', 'replace').strip()}"
            )
        text = result.stdout.decode("utf-8", "replace")
        # Last line is the status code we asked for via -w.
        body_text, _, status_line = text.rpartition("\n")
        try:
            status = int(status_line.strip())
        except ValueError as exc:
            raise JiraError(f"could not parse status line from curl output: {text!r}") from exc
        try:
            parsed: Any = json.loads(body_text) if body_text.strip() else {}
        except json.JSONDecodeError:
            parsed = body_text
        return JiraResponse(status=status, body=parsed, raw=body_text)

    def _expect_ok(self, resp: JiraResponse, action: str) -> Any:
        if resp.ok():
            return resp.body
        raise JiraError(f"{action} failed: HTTP {resp.status} — {self._format_error(resp.body)}")

    @staticmethod
    def _format_error(body: Any) -> str:
        if isinstance(body, dict):
            messages: list[str] = list(body.get("errorMessages") or [])
            errors = body.get("errors")
            if isinstance(errors, dict):
                messages += [f"{k}: {v}" for k, v in errors.items()]
            if messages:
                return "; ".join(messages)
        return str(body)[:500]

    # ------------------------------------------------------------------
    # High level
    # ------------------------------------------------------------------

    def get_project(self, key: str) -> dict[str, Any]:
        resp = self._request("GET", f"/rest/api/3/project/{key}")
        return self._expect_ok(resp, f"GET project {key}")

    def create_issue(self, payload: dict[str, Any]) -> dict[str, Any]:
        resp = self._request("POST", "/rest/api/3/issue", json_body=payload)
        return self._expect_ok(resp, "create issue")

    def bulk_create_issues(
        self,
        payloads: list[dict[str, Any]],
    ) -> tuple[list[str | None], list[tuple[int, str]]]:
        """Create up to 50 issues in one round-trip.

        Returns `(keys, errors)` where:
          * `keys[i]` is the Jira key created for `payloads[i]`, or `None`
            if that element failed.
          * `errors` is a list of `(index, error_message)` pairs for the
            failed elements, in the order Jira reported them.

        Jira's bulk endpoint returns a 201 even when some elements failed,
        so we never raise here for partial failures — the caller decides
        how to surface them. We do raise (via _expect_ok) on a hard HTTP
        failure of the bulk request itself.
        """
        if not payloads:
            return [], []
        if len(payloads) > MAX_BULK_BATCH:
            raise JiraError(
                f"bulk_create_issues: payload count {len(payloads)} exceeds "
                f"server cap of {MAX_BULK_BATCH}; chunk before calling."
            )
        body = {"issueUpdates": payloads}
        resp = self._request("POST", "/rest/api/3/issue/bulk", json_body=body)
        result = self._expect_ok(resp, "bulk create")

        keys: list[str | None] = [None] * len(payloads)
        # Jira's response shape (v3): {"issues": [{key, ...}, ...], "errors": [{...}]}
        # The successful issues array is in the same order as the request,
        # but error entries carry an explicit `failedElementNumber` index.
        issues = result.get("issues") or [] if isinstance(result, dict) else []
        errors_raw = result.get("errors") or [] if isinstance(result, dict) else []

        success_indices = sorted(
            i
            for i in range(len(payloads))
            if i not in {e.get("failedElementNumber") for e in errors_raw if isinstance(e, dict)}
        )
        for slot, issue in zip(success_indices, issues, strict=False):
            if isinstance(issue, dict):
                keys[slot] = issue.get("key")

        error_pairs: list[tuple[int, str]] = []
        for e in errors_raw:
            if not isinstance(e, dict):
                continue
            idx = e.get("failedElementNumber")
            elem_errors = e.get("elementErrors") or {}
            msg = self._format_error(elem_errors)
            if isinstance(idx, int):
                error_pairs.append((idx, msg))
        return keys, error_pairs

    def list_fields(self) -> list[dict[str, Any]]:
        """Return all fields visible to the authenticated user — used by
        `md-to-jira fields` for tenant-specific customfield discovery
        (Acceptance Criteria, Story Points, etc.).
        """
        resp = self._request("GET", "/rest/api/3/field")
        body = self._expect_ok(resp, "list fields")
        if not isinstance(body, list):
            raise JiraError(f"unexpected /field response shape: {type(body).__name__}")
        return body

    def myself(self) -> dict[str, Any]:
        """Return the authenticated user's identity — used by `whoami`
        as the cheapest possible round-trip to verify auth works.
        """
        resp = self._request("GET", "/rest/api/3/myself")
        body = self._expect_ok(resp, "GET /myself")
        if not isinstance(body, dict):
            raise JiraError(f"unexpected /myself response shape: {type(body).__name__}")
        return body
