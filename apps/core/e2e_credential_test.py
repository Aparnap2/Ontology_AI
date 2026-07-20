#!/usr/bin/env python3
"""
OntologyAI V5.1 — Credential E2E Test

Tests the credential collection UI CRUD flow end-to-end:
  1. GET  /api/workspace/credentials       → empty state
  2. POST /api/workspace/credentials        → create credential
  3. GET  /api/workspace/credentials        → verify in list
  4. DELETE /api/workspace/credentials/:id  → delete credential
  5. GET  /api/workspace/credentials        → verify gone (empty state)

Usage:
  python e2e_credential_test.py            # expects server on http://localhost:8080
  URL=http://localhost:3000 python e2e_credential_test.py  # custom base URL

Exit code: 0 = all tests pass, 1 = any test fails
"""

import os
import sys
import re
import http.client
import urllib.parse

BASE_URL = os.environ.get("URL", "http://localhost:8080")

def parse_url(url):
    """Parse a URL into (host, port, path, is_ssl)."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return host, port, parsed.path, parsed.scheme == "https"

def request(method, path, body=None, headers=None):
    """Make an HTTP request and return (status, body, headers)."""
    host, port, base_path, is_ssl = parse_url(BASE_URL)
    full_path = base_path.rstrip("/") + "/" + path.lstrip("/")

    if is_ssl:
        conn = http.client.HTTPSConnection(host, port, timeout=10)
    else:
        conn = http.client.HTTPConnection(host, port, timeout=10)

    req_headers = {
        "User-Agent": "e2e-credential-test/1.0",
    }
    if headers:
        req_headers.update(headers)

    try:
        conn.request(method, full_path, body=body, headers=req_headers)
        resp = conn.getresponse()
        resp_body = resp.read().decode("utf-8")
        resp_headers = dict(resp.getheaders())
        return resp.status, resp_body, resp_headers
    except Exception as e:
        print(f"  ✗ Connection error: {e}")
        return 0, "", {}
    finally:
        conn.close()


def test_step(step_num, description, condition, detail=""):
    """Print a test step result."""
    status = "PASS" if condition else "FAIL"
    icon = "✓" if condition else "✗"
    detail_str = f" — {detail}" if detail else ""
    print(f"  Step {step_num}: {icon} {description}{detail_str}")
    return condition


def main():
    passed = 0
    failed = 0

    print(f"\n{'='*60}")
    print(f" OntologyAI V5.1 Credential E2E Test")
    print(f" Target: {BASE_URL}")
    print(f"{'='*60}\n")

    # ──────────────────────────────────────────────
    # Step 1: GET /api/workspace/credentials (empty state)
    # ──────────────────────────────────────────────
    print("1. Testing empty state...")
    status, body, _ = request("GET", "/api/workspace/credentials", headers={"HX-Request": "true"})

    ok = True
    ok &= test_step(1.1, "Status code 200", status == 200, f"got {status}")
    ok &= test_step(1.2, "Shows 'No credentials configured'",
                     "No credentials configured" in body)
    ok &= test_step(1.3, "Shows 'Add Credential' button",
                     "Add Credential" in body)

    if ok:
        passed += 1
    else:
        failed += 1
        print(f"  Body snippet: {body[:300]}")

    # ──────────────────────────────────────────────
    # Step 2: GET /api/workspace/credentials/add (form)
    # ──────────────────────────────────────────────
    print("\n2. Testing add credential form...")
    status, body, _ = request("GET", "/api/workspace/credentials/add", headers={"HX-Request": "true"})

    ok = True
    ok &= test_step(2.1, "Status code 200", status == 200, f"got {status}")
    ok &= test_step(2.2, "Form has provider select", 'name="provider"' in body)
    ok &= test_step(2.3, "Form has display name input", 'name="name"' in body)
    ok &= test_step(2.4, "Form has secret value input", 'name="value"' in body)
    ok &= test_step(2.5, "Form submits to correct endpoint",
                     'hx-post="/api/workspace/credentials"' in body)

    if ok:
        passed += 1
    else:
        failed += 1
        print(f"  Body snippet: {body[:300]}")

    # ──────────────────────────────────────────────
    # Step 3: POST /api/workspace/credentials (create)
    # ──────────────────────────────────────────────
    print("\n3. Testing credential creation...")
    form_body = "provider=slack&name=E2E+Test+Token&value=xoxb-e2e-test-secret"
    status, body, headers = request(
        "POST", "/api/workspace/credentials",
        body=form_body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "HX-Request": "true",
        },
    )

    ok = True
    ok &= test_step(3.1, "Status code 201", status == 201, f"got {status}")
    ok &= test_step(3.2, "Response contains provider badge",
                     "slack" in body, "expected 'slack' in response")
    ok &= test_step(3.3, "Response contains credential name",
                     "E2E Test Token" in body)

    if ok:
        passed += 1
    else:
        failed += 1
        print(f"  Body snippet: {body[:300]}")

    # ──────────────────────────────────────────────
    # Step 4: GET /api/workspace/credentials (verify in list)
    # ──────────────────────────────────────────────
    print("\n4. Verifying credential appears in list...")
    status, body, _ = request("GET", "/api/workspace/credentials", headers={"HX-Request": "true"})

    ok = True
    ok &= test_step(4.1, "Status code 200", status == 200, f"got {status}")
    ok &= test_step(4.2, "List shows created credential",
                     "E2E Test Token" in body)
    ok &= test_step(4.3, "List shows provider badge",
                     "slack" in body)
    ok &= test_step(4.4, "Delete button exists for credential",
                     "hx-delete" in body)
    ok &= test_step(4.5, "Empty state is NOT shown",
                     "No credentials configured" not in body)

    if ok:
        passed += 1
    else:
        failed += 1
        print(f"  Body snippet: {body[:300]}")

    # ──────────────────────────────────────────────
    # Step 5: Extract credential ID and DELETE it
    # ──────────────────────────────────────────────
    print("\n5. Testing credential deletion...")

    # Extract credential ID from the row (format: credential-row-<ID>)
    id_match = re.search(r'id="credential-row-([^"]+)"', body)
    if not id_match:
        test_step(5, "Extract credential ID from HTML",
                  False, "Could not find credential-row-XXX id")
        failed += 1
        print(f"  Body snippet: {body[:500]}")
    else:
        cred_id = id_match.group(1)
        test_step(5.1, f"Extracted credential ID: {cred_id}", True)

        status, delete_body, _ = request(
            "DELETE", f"/api/workspace/credentials/{cred_id}",
            headers={"HX-Request": "true"},
        )

        ok = True
        ok &= test_step(5.2, "Status code 200 on delete",
                         status == 200, f"got {status}")

        if ok:
            passed += 1
        else:
            failed += 1

    # ──────────────────────────────────────────────
    # Step 6: GET /api/workspace/credentials (verify empty after delete)
    # ──────────────────────────────────────────────
    print("\n6. Verifying empty state after delete...")
    status, body, _ = request("GET", "/api/workspace/credentials", headers={"HX-Request": "true"})

    ok = True
    ok &= test_step(6.1, "Status code 200", status == 200, f"got {status}")
    ok &= test_step(6.2, "Credential no longer in list",
                     "E2E Test Token" not in body,
                     "credential should be gone")
    ok &= test_step(6.3, "Empty state restored",
                     "No credentials configured" in body)

    if ok:
        passed += 1
    else:
        failed += 1
        print(f"  Body snippet: {body[:300]}")

    # ──────────────────────────────────────────────
    # Summary
    # ──────────────────────────────────────────────
    total = passed + failed
    print(f"\n{'='*60}")
    print(f" Results: {passed}/{total} steps passed", end="")
    if failed > 0:
        print(f", {failed} failed ❌")
    else:
        print(" ✅")
    print(f"{'='*60}\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
