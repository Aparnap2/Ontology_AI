#!/usr/bin/env bash
# =============================================================================
# health_check.sh -- readiness gate for the OntologyAI local integration stack
# =============================================================================
# Verifies, in order:
#   1. Postgres (localgcp-cloudsql) is accepting connections
#   2. ontologiai-temporal container is running and Docker-health == healthy
#   3. Temporal cluster reports SERVING
#   4. `temporal operator namespace list` returns the `default` namespace
#      (a REAL client call, not a port probe)
#   5. The HOST-PUBLISHED 7233 is reachable by a real client (not just in-container)
#   6. The vendor mock answers real HTTP on 3003, including its rule-based routes
#
# WHY AN OPEN PORT IS NOT ENOUGH
# ------------------------------
# The gRPC listener binds 7233 BEFORE the persistence backend is reachable, so on
# a wedged server `nc -z localhost 7233` succeeds while nothing works. That is
# exactly how this stack was previously misdiagnosed. Every Temporal check below
# makes an actual RPC. If Postgres is unreachable, check 4 fails loudly instead
# of reporting a false HEALTHY.
#
# EXIT CODES
#   0  every check passed  -- stack is ready for integration tests
#   1  at least one check failed
#   2  bad usage / missing dependency
#
# USAGE
#   ./health_check.sh              # human readable
#   ./health_check.sh --quiet      # only print the final verdict
#
# OVERRIDES (all optional)
#   POSTGRES_CONTAINER=localgcp-cloudsql
#   TEMPORAL_CONTAINER=ontologiai-temporal
#   MOCK_CONTAINER=ontologiai-vendor-mock
#   TEMPORAL_PORT=7233
#   VENDOR_MOCK_URL=http://localhost:3003
# =============================================================================
set -uo pipefail

POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-localgcp-cloudsql}"
TEMPORAL_CONTAINER="${TEMPORAL_CONTAINER:-ontologiai-temporal}"
MOCK_CONTAINER="${MOCK_CONTAINER:-ontologiai-vendor-mock}"
TEMPORAL_PORT="${TEMPORAL_PORT:-7233}"
VENDOR_MOCK_URL="${VENDOR_MOCK_URL:-http://localhost:3003}"
TEMPORAL_IMAGE="${TEMPORAL_IMAGE:-temporalio/auto-setup:latest}"

QUIET=0
[[ "${1:-}" == "--quiet" ]] && QUIET=1

FAILURES=0
declare -a RESULTS=()

say() { [[ $QUIET -eq 1 ]] || printf '%s\n' "$*"; }

# record <PASS|FAIL|WARN> <name> <detail>
record() {
    local status="$1" name="$2" detail="${3:-}"
    RESULTS+=("$status|$name|$detail")
    case "$status" in
        PASS) say "  [ OK ] ${name}${detail:+ -- ${detail}}" ;;
        FAIL) say "  [FAIL] ${name}${detail:+ -- ${detail}}"; FAILURES=$((FAILURES + 1)) ;;
        WARN) say "  [WARN] ${name}${detail:+ -- ${detail}}" ;;
    esac
}

container_running() {
    [[ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null)" == "true" ]]
}

container_health() {
    docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$1" 2>/dev/null
}

# ---------------------------------------------------------------------------
say "OntologyAI integration stack health check"
say "-----------------------------------------"

# --- 0. dependencies -------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
    say "ERROR: docker not found on PATH"
    exit 2
fi
if ! docker info >/dev/null 2>&1; then
    say "ERROR: cannot talk to the Docker daemon"
    exit 2
fi

# --- 1. Postgres -----------------------------------------------------------
if ! container_running "$POSTGRES_CONTAINER"; then
    record FAIL "postgres container running" \
        "$POSTGRES_CONTAINER is not running. Start it, e.g. docker start $POSTGRES_CONTAINER"
else
    if docker exec "$POSTGRES_CONTAINER" pg_isready -U postgres >/dev/null 2>&1; then
        record PASS "postgres accepting connections" "$POSTGRES_CONTAINER"
    else
        record FAIL "postgres accepting connections" \
            "pg_isready failed inside $POSTGRES_CONTAINER"
    fi
fi

# --- 2. Temporal container -------------------------------------------------
if ! container_running "$TEMPORAL_CONTAINER"; then
    record FAIL "temporal container running" \
        "$TEMPORAL_CONTAINER is not running. Bring the stack up with:
      docker compose -f apps/ai/tests/docker-compose.integration.yml up -d"
    # No point probing a container that is not running.
    HEALTH_TEMPORAL=0
else
    record PASS "temporal container running" "$TEMPORAL_CONTAINER"

    _h="$(container_health "$TEMPORAL_CONTAINER")"
    if [[ "$_h" == "healthy" ]]; then
        record PASS "temporal docker health" "healthy"
        HEALTH_TEMPORAL=1
    else
        # 'starting' is legitimate while the server comes up; only a definite
        # 'unhealthy' after retries is a hard failure, reported by the RPC
        # checks below. Treat 'none' (no healthcheck defined) as soft.
        case "$_h" in
            starting) record WARN "temporal docker health" "starting (still booting)" ;;
            none)     record WARN "temporal docker health" "no healthcheck defined" ;;
            *)        record FAIL "temporal docker health" "$_h" ;;
        esac
        HEALTH_TEMPORAL=1
    fi
fi

# --- 3. cluster SERVING ----------------------------------------------------
if [[ "${HEALTH_TEMPORAL:-0}" == "1" ]]; then
    if docker exec "$TEMPORAL_CONTAINER" \
        temporal operator cluster health --address "127.0.0.1:${TEMPORAL_PORT}" 2>/dev/null \
        | grep -q SERVING; then
        record PASS "temporal cluster SERVING" "all services up"
    else
        record FAIL "temporal cluster SERVING" \
            "cluster did not report SERVING (persistence backend likely unreachable)"
    fi

    # --- 4. namespace readiness (REAL RPC, in-container) -------------------
    _ns="$(docker exec "$TEMPORAL_CONTAINER" \
        temporal operator namespace list 2>/dev/null)"
    if grep -qE '^[[:space:]]*NamespaceInfo\.Name[[:space:]]+default[[:space:]]*$' <<<"$_ns"; then
        record PASS "temporal namespace 'default' registered" \
            "$(grep -c 'NamespaceInfo.Name' <<<"$_ns") namespace(s) total"
    else
        record FAIL "temporal namespace 'default' registered" \
            "namespace list did not contain 'default'. This is the real readiness signal:
      an open port $TEMPORAL_PORT does NOT mean Temporal is usable."
    fi

    # --- 5. HOST-published port reachable by a real client ------------------
    # Reach the host's published port through the container's network gateway.
    # This exercises the same 0.0.0.0:${TEMPORAL_PORT} -> ${TEMPORAL_PORT} mapping
    # a host-side worker uses, rather than the container's loopback.
    _gw="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.Gateway}}{{"\n"}}{{end}}' \
        "$TEMPORAL_CONTAINER" 2>/dev/null | head -n1)"
    _host_ok=0
    for _addr in ${_gw:+"${_gw}:${TEMPORAL_PORT}"}; do
        if docker exec "$TEMPORAL_CONTAINER" \
            temporal operator namespace list --address "$_addr" 2>/dev/null \
            | grep -qE '^[[:space:]]*NamespaceInfo\.Name[[:space:]]+default[[:space:]]*$'; then
            record PASS "host-published :${TEMPORAL_PORT} serves RPC" \
                "client reached it via host gateway ${_addr}"
            _host_ok=1
            break
        fi
    done
    if [[ "$_host_ok" -eq 0 ]]; then
        # Fallback: prove it from the host's own network namespace.
        if docker run --rm --network host --entrypoint temporal "$TEMPORAL_IMAGE" \
            operator namespace list --address "localhost:${TEMPORAL_PORT}" 2>/dev/null \
            | grep -qE '^[[:space:]]*NamespaceInfo\.Name[[:space:]]+default[[:space:]]*$'; then
            record PASS "host-published :${TEMPORAL_PORT} serves RPC" \
                "client reached it from the host network namespace"
            _host_ok=1
        fi
    fi
    if [[ "$_host_ok" -eq 0 ]]; then
        record FAIL "host-published :${TEMPORAL_PORT} serves RPC" \
            "no client could reach localhost:${TEMPORAL_PORT}. Check the published port."
    fi
fi

# --- 6. vendor mock --------------------------------------------------------
if ! container_running "$MOCK_CONTAINER"; then
    record FAIL "vendor mock container running" \
        "$MOCK_CONTAINER is not running"
else
    record PASS "vendor mock container running" "$MOCK_CONTAINER"
fi

if ! command -v curl >/dev/null 2>&1; then
    record WARN "mock HTTP probe" "curl not found on PATH; skipped"
else
    # Static 200 route -- proves the server is serving the Jira fixture.
    _code="$(curl -sS -o /dev/null -w '%{http_code}' \
        --max-time 5 "${VENDOR_MOCK_URL}/rest/api/3/project" 2>/dev/null)"
    if [[ "$_code" == "200" ]]; then
        record PASS "mock GET /rest/api/3/project" "200"
    else
        record FAIL "mock GET /rest/api/3/project" \
            "expected 200, got '${_code:-<no response>}' from ${VENDOR_MOCK_URL}"
    fi

    # Parameterised route -> 200, with a real issue key.
    _code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 \
        "${VENDOR_MOCK_URL}/rest/api/3/issue/PORTAL-1" 2>/dev/null)"
    if [[ "$_code" == "200" ]]; then
        record PASS "mock GET /rest/api/3/issue/PORTAL-1" "200"
    else
        record FAIL "mock GET /rest/api/3/issue/PORTAL-1" "expected 200, got '${_code:-<none>}'"
    fi

    # Rule-based route -> 429. Verifies rule routing, not just the static
    # default response. This is the route test_jira_demo_binding.py maps to
    # JiraRateLimitedError.
    _code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 \
        "${VENDOR_MOCK_URL}/rest/api/3/issue/RATE-LIMITED-1" 2>/dev/null)"
    if [[ "$_code" == "429" ]]; then
        record PASS "mock GET /rest/api/3/issue/RATE-LIMITED-1" "429 (rule-routed)"
    else
        record FAIL "mock GET /rest/api/3/issue/RATE-LIMITED-1" "expected 429, got '${_code:-<none>}'"
    fi

    # Rule-triggered 400 on the search route (?trigger=error).
    _code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 \
        "${VENDOR_MOCK_URL}/rest/api/3/search?trigger=error" 2>/dev/null)"
    if [[ "$_code" == "400" ]]; then
        record PASS "mock GET /rest/api/3/search?trigger=error" "400 (rule-routed)"
    else
        record WARN "mock GET /rest/api/3/search?trigger=error" \
            "expected 400, got '${_code:-<none>}' (rule-triggered branch)"
    fi
fi

# --- verdict ---------------------------------------------------------------
say "-----------------------------------------"
if [[ "$FAILURES" -eq 0 ]]; then
    say "RESULT: HEALTHY -- Temporal (localhost:${TEMPORAL_PORT}) and vendor mock (${VENDOR_MOCK_URL}) are ready."
    say "        run: cd apps/ai && uv run pytest tests/integration/ -v"
    exit 0
fi

say "RESULT: UNHEALTHY -- ${FAILURES} check(s) failed:"
for _r in "${RESULTS[@]}"; do
    [[ "${_r%%|*}" == "FAIL" ]] || continue
    _rest="${_r#*|}"          # name|detail
    _name="${_rest%%|*}"
    _det="${_rest#*|}"
    if [[ "$_name" == "$_det" ]]; then
        say "  - ${_name}"
    else
        say "  - ${_name}"
        [[ -n "$_det" ]] && say "      ${_det}"
    fi
done
say "        bring the stack up with:"
say "          docker compose -f apps/ai/tests/docker-compose.integration.yml up -d"
exit 1
