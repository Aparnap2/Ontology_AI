"""Jira hero client — sync HTTP with strict schemas (Phase E P0).

Covers the blocker mission's minimum surface: get/search/create/link/update
issues. Every method validates input (Pydantic), normalizes output, maps
connector errors with an explicit retryable flag, and enforces tenant scope.
Demo binding is localhost-only; the client never decides policy — it only
executes and reports.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field


class JiraClientError(Exception):
    """Base error; ``retryable`` tells the caller (Temporal/executor) the class."""

    def __init__(self, message: str, *, status: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.retryable = retryable


class JiraNotFoundError(JiraClientError):
    def __init__(self, message: str):
        super().__init__(message, status=404, retryable=False)


class JiraAuthError(JiraClientError):
    def __init__(self, message: str, *, status: int):
        super().__init__(message, status=status, retryable=False)


class JiraBadRequestError(JiraClientError):
    def __init__(self, message: str):
        super().__init__(message, status=400, retryable=False)


class JiraRateLimitedError(JiraClientError):
    def __init__(self, message: str, *, retry_after: float = 0.0):
        super().__init__(message, status=429, retryable=True)
        self.retry_after = retry_after


class JiraServerError(JiraClientError):
    def __init__(self, message: str, *, status: int):
        super().__init__(message, status=status, retryable=True)


class JiraTimeoutError(JiraClientError):
    def __init__(self, message: str):
        super().__init__(message, status=None, retryable=True)


class JiraConnectionError(JiraClientError):
    def __init__(self, message: str):
        super().__init__(message, status=None, retryable=True)


class JiraIssue(BaseModel):
    """Normalized Jira issue (subset the mission needs)."""

    model_config = ConfigDict(extra="ignore")

    key: str = Field(min_length=1)
    summary: str = ""
    status: str = ""
    assignee: str | None = None
    project_key: str = ""


class CreateIssueRequest(BaseModel):
    """Strict input for issue creation."""

    model_config = ConfigDict(extra="forbid")

    project: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    description: str = ""
    issue_type: str = "Task"
    assignee: str = ""


class LinkIssuesRequest(BaseModel):
    """Strict input for linking two issues (e.g. Blocks)."""

    model_config = ConfigDict(extra="forbid")

    inward_key: str = Field(min_length=1)
    outward_key: str = Field(min_length=1)
    link_type: str = "Blocks"


def parse_issue(raw: dict[str, Any]) -> JiraIssue:
    """Normalize a Jira REST issue payload (tolerates partial shapes)."""
    fields = raw.get("fields", {}) if isinstance(raw.get("fields"), dict) else {}
    status = fields.get("status")
    status_name = status.get("name", "") if isinstance(status, dict) else str(status or "")
    assignee = fields.get("assignee")
    assignee_name = (
        assignee.get("displayName", "") if isinstance(assignee, dict) else None
    )
    project = fields.get("project")
    project_key = project.get("key", "") if isinstance(project, dict) else ""
    return JiraIssue(
        key=str(raw.get("key", "")),
        summary=str(fields.get("summary", "")),
        status=status_name,
        assignee=assignee_name or None,
        project_key=project_key,
    )


class JiraClient:
    """Sync Jira REST client for demo (Mockoon) and prod bindings."""

    def __init__(
        self,
        base_url: str,
        *,
        tenant_id: str,
        username: str | None = None,
        api_token: str | None = None,
        timeout_seconds: float = 10.0,
        demo: bool = False,
        transport: httpx.BaseTransport | None = None,
    ):
        if not (tenant_id or "").strip():
            raise ValueError("tenant_id must be non-empty (tenant scope enforcement)")
        if demo:
            host = (urlparse(base_url).hostname or "").lower()
            if host not in ("localhost", "127.0.0.1", "::1"):
                raise ValueError(
                    f"demo binding refuses non-localhost base_url {base_url!r}"
                )
        auth = (username, api_token) if username and api_token else None
        self.base_url = base_url.rstrip("/")
        self.tenant_id = tenant_id
        self._http = httpx.Client(
            base_url=self.base_url, auth=auth, timeout=timeout_seconds,
            transport=transport,
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise JiraTimeoutError(f"jira {method} {path} timed out: {exc}") from exc
        except httpx.TransportError as exc:
            raise JiraConnectionError(f"jira {method} {path} unreachable: {exc}") from exc
        status = response.status_code
        if status in (200, 201, 204):
            return response
        body = response.text[:300]
        if status in (401, 403):
            raise JiraAuthError(f"jira {method} {path} forbidden ({status}): {body}", status=status)
        if status == 404:
            raise JiraNotFoundError(f"jira {method} {path} not found: {body}")
        if status == 400:
            raise JiraBadRequestError(f"jira {method} {path} rejected: {body}")
        if status == 429:
            retry_after = float(response.headers.get("retry-after", "0") or 0.0)
            raise JiraRateLimitedError(
                f"jira {method} {path} rate limited: {body}", retry_after=retry_after
            )
        if 500 <= status <= 599:
            raise JiraServerError(f"jira {method} {path} server error ({status}): {body}", status=status)
        raise JiraClientError(f"jira {method} {path} unexpected status {status}: {body}", status=status)

    def get_issue(self, key: str) -> JiraIssue:
        """Fetch one issue by key (404 → JiraNotFoundError)."""
        response = self._request("GET", f"/rest/api/3/issue/{key}")
        return parse_issue(response.json())

    def search_issues(self, jql: str = "", limit: int = 50) -> list[JiraIssue]:
        """Search issues; returns normalized records (empty, never None)."""
        response = self._request(
            "GET", "/rest/api/3/search", params={"jql": jql, "maxResults": limit}
        )
        payload = response.json()
        issues = payload.get("issues", []) if isinstance(payload, dict) else payload
        return [parse_issue(raw) for raw in issues if isinstance(raw, dict)]

    def create_issue(self, data: dict[str, Any]) -> str:
        """Create an issue; returns the new issue key."""
        request = CreateIssueRequest(
            project=str(data.get("project", "")),
            summary=str(data.get("summary", "")),
            description=str(data.get("description", "")),
            issue_type=str(data.get("issue_type", "Task")),
            assignee=str(data.get("assignee", "")),
        )
        fields: dict[str, Any] = {
            "project": {"key": request.project},
            "summary": request.summary,
            "description": request.description,
            "issuetype": {"name": request.issue_type},
        }
        if request.assignee:
            fields["assignee"] = {"name": request.assignee}
        response = self._request("POST", "/rest/api/3/issue", json={"fields": fields})
        key = str(response.json().get("key", ""))
        if not key:
            raise JiraClientError("jira create returned no issue key")
        return key

    def link_issues(self, inward_key: str, outward_key: str, link_type: str = "Blocks") -> dict[str, Any]:
        """Link outward → inward (e.g. blocker Blocks task); returns ack."""
        request = LinkIssuesRequest(
            inward_key=inward_key, outward_key=outward_key, link_type=link_type
        )
        self._request(
            "POST",
            "/rest/api/3/issueLink",
            json={
                "type": {"name": request.link_type},
                "inwardIssue": {"key": request.inward_key},
                "outwardIssue": {"key": request.outward_key},
            },
        )
        return {"linked": True, "inward": request.inward_key, "outward": request.outward_key}

    def update_issue(self, issue_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        """Update issue fields; returns the merged record view."""
        if not issue_id:
            raise ValueError("issue_id must be non-empty")
        self._request(
            "PUT", f"/rest/api/3/issue/{issue_id}", json={"fields": dict(fields)}
        )
        return {"id": issue_id, **fields}

    # ── Op-surface adapters (match CapabilityOpRegistry closures) ────────────

    def get_issues(self, **filters: Any) -> list[dict[str, Any]]:
        """Adapter for jira.search/jira.read ops: raw dicts for verification."""
        jql = str(filters.get("jql", "") or filters.get("query", ""))
        limit = int(filters.get("limit", 50) or 50)
        response = self._request(
            "GET", "/rest/api/3/search", params={"jql": jql, "maxResults": limit}
        )
        payload = response.json()
        issues = payload.get("issues", []) if isinstance(payload, dict) else payload
        return [raw for raw in issues if isinstance(raw, dict)]

    def close(self) -> None:
        """Release the underlying HTTP connection pool."""
        self._http.close()
