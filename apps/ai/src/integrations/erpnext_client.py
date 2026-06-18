"""
ERPNext REST API client — pure-stdlib, lightweight wrapper for Frappe REST endpoints.

Provides a minimal, dependency-free client for interacting with the ERPNext
(Frappe) REST API using only Python standard library modules.

Environment Variables:
    ERPNEXT_URL: Base URL of the ERPNext instance (default: http://localhost:8080)
    ERPNEXT_API_KEY: API key for token auth (falls back to ERPNEXT_USER)
    ERPNEXT_API_SECRET: API secret for token auth (falls back to ERPNEXT_PASSWORD)

Methods:
    get(doctype, name): Fetch a single document by name
    list(doctype, ...): List documents with filters, fields, pagination
    count(doctype, ...): Count documents matching filters
    get_value(doctype, filters, fieldname): Fetch a single field value
    submit(doctype, name): Submit a draft document (docstatus=1)
    cancel(doctype, name): Cancel a submitted document (docstatus=2)
"""

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from .retry import circuit_breaker, compute_backoff_delay

logger = logging.getLogger(__name__)


class ERPNextError(RuntimeError):
    """Raised on non-2xx responses from the ERPNext API."""


class ERPNextClient:
    """Low-level client for Frappe/ERPNext REST API.

    Reads configuration from environment variables at instantiation time.
    All requests use token-based authentication via the ``Authorization`` header.

    Usage::

        client = ERPNextClient()
        issue = client.get("Issue", "ISS-.2024.-00001")
        open_issues = client.list("Issue", filters=[["status", "!=", "Closed"]])
        count = client.count("Issue")
    """

    def __init__(self) -> None:
        self.base = os.getenv("ERPNEXT_URL", "http://localhost:8080").rstrip("/")
        api_key = os.getenv("ERPNEXT_API_KEY") or os.getenv("ERPNEXT_USER") or ""
        api_secret = os.getenv("ERPNEXT_API_SECRET") or os.getenv("ERPNEXT_PASSWORD") or ""
        self._auth = f"token {api_key}:{api_secret}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @circuit_breaker("erpnext")
    def _request(self, method: str, path: str,
                 params: Optional[dict] = None,
                 body: Optional[dict] = None) -> Any:
        """Execute an HTTP request and return the parsed JSON response.

        Automatically retries transient failures (HTTP 5xx, connection errors,
        timeouts) up to 3 times with jittered exponential backoff.  The
        ``@circuit_breaker`` decorator trips after 5 consecutive failures
        across all callers.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            path: URL path starting with ``/`` (e.g. ``/api/resource/Issue/...``).
            params: Query-string parameters (values that are ``list`` or ``dict``
                    are JSON-encoded; ``None`` values are omitted).
            body: JSON-serialisable request body (for POST/PUT).

        Returns:
            The parsed JSON response (typically a ``dict`` with ``data`` or
            ``message`` keys for Frappe endpoints).

        Raises:
            ERPNextError: On any HTTP non-2xx response, with Frappe error
                          details extracted from ``_server_messages``.
        """
        url = f"{self.base}{path}"
        if params:
            enc: Dict[str, str] = {}
            for k, v in params.items():
                if v is not None:
                    enc[k] = json.dumps(v) if isinstance(v, (list, dict)) else str(v)
            url += "?" + urllib.parse.urlencode(enc)

        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": self._auth,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

        max_attempts = 4  # 1 initial + 3 retries

        for attempt in range(max_attempts):
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                # Retry on server errors (5xx); client errors (4xx) are permanent
                if e.code >= 500 and attempt < max_attempts - 1:
                    delay = compute_backoff_delay(attempt)
                    logger.warning(
                        "ERPNext server error %d on %s %s, retrying in %.1fs "
                        "(attempt %d/%d)",
                        e.code, method, path, delay, attempt + 1, max_attempts,
                    )
                    time.sleep(delay)
                    continue

                # Non-retryable HTTP error — parse Frappe error details
                raw = e.read().decode("utf-8", "ignore")
                msg = f"HTTP {e.code}"
                try:
                    j = json.loads(raw)
                    sm = j.get("_server_messages")
                    if sm:
                        parts = [json.loads(m).get("message", m) for m in json.loads(sm)]
                        msg += ": " + "; ".join(str(p) for p in parts)
                    elif j.get("exception"):
                        msg += ": " + j["exception"]
                    elif j.get("message"):
                        msg += ": " + str(j["message"])
                except Exception:
                    msg += ": " + raw[:300]
                raise ERPNextError(msg) from None
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                # Transient connection / network error — retry
                if attempt < max_attempts - 1:
                    delay = compute_backoff_delay(attempt)
                    logger.warning(
                        "ERPNext connection error on %s %s: %s, retrying in %.1fs "
                        "(attempt %d/%d)",
                        method, path, e, delay, attempt + 1, max_attempts,
                    )
                    time.sleep(delay)
                    continue
                raise ERPNextError(
                    f"Connection failed after {max_attempts} attempts: {e}"
                ) from e

        # Should be unreachable, but satisfies the type checker
        raise ERPNextError("Request failed unexpectedly")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, doctype: str, name: str) -> dict:
        """Fetch a single ERPNext document by its name."""
        path = f"/api/resource/{urllib.parse.quote(doctype)}/{urllib.parse.quote(name)}"
        return self._request("GET", path)["data"]

    def list(self, doctype: str, filters: Optional[list] = None,
             fields: Optional[list] = None,
             order_by: Optional[str] = None,
             limit: int = 20, start: int = 0) -> List[dict]:
        """List documents of a DocType with optional filtering and pagination.

        Uses ``frappe.client.get_list`` which returns lightweight dicts with
        only the requested fields (defaults to ``["name"]``).
        """
        params: Dict[str, Any] = {
            "doctype": doctype,
            "filters": filters,
            "fields": fields or ["name"],
            "order_by": order_by,
            "limit_page_length": limit,
            "limit_start": start,
        }
        return self._request("GET", "/api/method/frappe.client.get_list", params)["message"]

    def count(self, doctype: str, filters: Optional[list] = None) -> int:
        """Count documents of a DocType matching optional filters.

        Uses ``frappe.client.get_count``.
        """
        params: Dict[str, Any] = {"doctype": doctype, "filters": filters}
        return self._request("GET", "/api/method/frappe.client.get_count", params)["message"]

    def get_value(self, doctype: str, filters: list,
                  fieldname: str = "name") -> Any:
        """Fetch a single field value from a document matching filters.

        Uses ``frappe.client.get_value``.
        """
        params: Dict[str, Any] = {
            "doctype": doctype,
            "filters": filters,
            "fieldname": fieldname,
        }
        msg = self._request("GET", "/api/method/frappe.client.get_value", params)["message"]
        if isinstance(fieldname, str) and isinstance(msg, dict):
            return msg.get(fieldname)
        return msg

    def submit(self, doctype: str, name: str) -> dict:
        """Submit a draft document for approval (sets docstatus to 1)."""
        path = f"/api/resource/{urllib.parse.quote(doctype)}/{urllib.parse.quote(name)}"
        return self._request("PUT", path, body={"docstatus": 1})["data"]

    def cancel(self, doctype: str, name: str) -> dict:
        """Cancel a submitted document (sets docstatus to 2)."""
        path = f"/api/resource/{urllib.parse.quote(doctype)}/{urllib.parse.quote(name)}"
        return self._request("PUT", path, body={"docstatus": 2})["data"]
