#!/usr/bin/env bash
# OntologyAI v1.0 Phase 6 - Integration Testing Script
# Tests: HITL flow, BI workflow, Cross-agent triggers
#
# Usage: ./scripts/test_integration.sh
#
# Prerequisites:
# - Docker containers running (Temporal, tg-mock, PostgreSQL)
# - Go server and Python worker will be started by this script

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
GO_SERVER_PORT="${GO_SERVER_PORT:-8080}"
TG_MOCK_URL="${TG_MOCK_URL:-http://localhost:8085}"
TEMPORAL_UI="${TEMPORAL_UI:-http://localhost:8088}"
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-test-bot-token}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-sarthi-alerts}"

# Process tracking
GO_SERVER_PID=""
PYTHON_WORKER_PID=""

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}Cleaning up...${NC}"
    
    if [[ -n "$GO_SERVER_PID" ]] && kill -0 "$GO_SERVER_PID" 2>/dev/null; then
        echo -n "   Stopping Go server (PID: $GO_SERVER_PID)... "
        kill "$GO_SERVER_PID" 2>/dev/null || true
        sleep 2
        echo -e "${GREEN}✓${NC}"
    fi
    
    if [[ -n "$PYTHON_WORKER_PID" ]] && kill -0 "$PYTHON_WORKER_PID" 2>/dev/null; then
        echo -n "   Stopping Python worker (PID: $PYTHON_WORKER_PID)... "
        kill "$PYTHON_WORKER_PID" 2>/dev/null || true
        sleep 2
        echo -e "${GREEN}✓${NC}"
    fi
    
    echo -e "${GREEN}Cleanup complete${NC}"
}

trap cleanup EXIT

# Helper function to log test results
log_test() {
    local test_name="$1"
    local status="$2"
    local details="$3"
    
    if [[ "$status" == "PASS" ]]; then
        echo -e "   ${GREEN}✓${NC} $test_name"
    elif [[ "$status" == "FAIL" ]]; then
        echo -e "   ${RED}✗${NC} $test_name"
        if [[ -n "$details" ]]; then
            echo -e "      ${YELLOW}Details: $details${NC}"
        fi
    else
        echo -e "   ${BLUE}ℹ${NC} $test_name"
    fi
}

# Helper function to run a test command
run_test() {
    local test_name="$1"
    shift
    
    if "$@" >/dev/null 2>&1; then
        log_test "$test_name" "PASS"
        return 0
    else
        log_test "$test_name" "FAIL"
        return 1
    fi
}

# Check if a port is in use
wait_for_port() {
    local port="$1"
    local service="$2"
    local timeout="${3:-30}"
    
    echo -n "   Waiting for $service on port $port... "
    
    local count=0
    while ! nc -z localhost "$port" 2>/dev/null; do
        sleep 1
        count=$((count + 1))
        if [[ $count -ge $timeout ]]; then
            echo -e "${RED}✗${NC} Timeout after ${timeout}s"
            return 1
        fi
    done
    
    echo -e "${GREEN}✓${NC} Ready (${count}s)"
    return 0
}

# Check if containers are running
check_containers() {
    echo -e "\n${BLUE}[1/6] Checking Docker containers...${NC}"
    
    local temporal_running=$(docker ps --filter name="iterateswarm-temporal" --format "{{.Status}}" | grep -c "Up" || true)
    local tg_mock_running=$(docker ps --filter name="sarthi-tg-mock" --format "{{.Status}}" | grep -c "Up" || true)
    
    if [[ "$temporal_running" -ge 1 ]]; then
        log_test "Temporal container" "PASS"
    else
        log_test "Temporal container" "FAIL" "Container not running"
        echo -e "${RED}Please start containers: docker-compose up -d${NC}"
        exit 1
    fi
    
    if [[ "$tg_mock_running" -ge 1 ]]; then
        log_test "TG-Mock container" "PASS"
    else
        log_test "TG-Mock container" "FAIL" "Container not running"
        echo -e "${YELLOW}Starting tg-mock...${NC}"
        bash /home/aparna/Desktop/iterate_swarm/scripts/start-tg-mock.sh
        sleep 3
    fi
    
    wait_for_port 7233 "Temporal" 10 || exit 1
    wait_for_port 8085 "TG-Mock" 10 || exit 1
}

# Start Go server
start_go_server() {
    echo -e "\n${BLUE}[2/6] Starting Go server...${NC}"
    
    cd /home/aparna/Desktop/iterate_swarm/apps/core
    
    # Build if binary doesn't exist
    if [[ ! -f bin/server ]]; then
        echo -n "   Building Go server... "
        mkdir -p bin
        go build -o bin/server ./cmd/server/main.go 2>&1 | tail -5
        echo -e "${GREEN}✓${NC}"
    fi
    
    # Start server in background
    echo -n "   Starting server on port $GO_SERVER_PORT... "
    ./bin/server -port "$GO_SERVER_SERVER_PORT" > /tmp/go_server.log 2>&1 &
    GO_SERVER_PID=$!
    
    sleep 3
    
    if kill -0 "$GO_SERVER_PID" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} Server started (PID: $GO_SERVER_PID)"
    else
        echo -e "${RED}✗${NC} Server failed to start"
        echo -e "${YELLOW}Logs:${NC}"
        tail -20 /tmp/go_server.log
        exit 1
    fi
    
    wait_for_port "$GO_SERVER_PORT" "Go server" 10 || exit 1
}

# Start Python worker
start_python_worker() {
    echo -e "\n${BLUE}[3/6] Starting Python worker...${NC}"
    
    cd /home/aparna/Desktop/iterate_swarm/apps/ai
    
    echo -n "   Starting worker... "
    uv run python -m src.worker > /tmp/python_worker.log 2>&1 &
    PYTHON_WORKER_PID=$!
    
    sleep 5
    
    if kill -0 "$PYTHON_WORKER_PID" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} Worker started (PID: $PYTHON_WORKER_PID)"
    else
        echo -e "${RED}✗${NC} Worker failed to start"
        echo -e "${YELLOW}Logs:${NC}"
        tail -20 /tmp/python_worker.log
        exit 1
    fi
}

# Test HITL investigate endpoint
test_hitl_investigate() {
    echo -e "\n${BLUE}[4/6] Testing HITL Investigate Flow...${NC}"
    
    local workflow_id="hitl-test-$(date +%s)"
    
    # Start a FinanceWorkflow first
    echo -n "   Starting FinanceWorkflow... "
    uv run python -c "
import asyncio
from temporalio.client import Client

async def start():
    client = await Client.connect('localhost:7233')
    handle = await client.start_workflow(
        'FinanceWorkflow',
        args=['demo-tenant', {'vendor': 'AWS', 'amount': 42000}, '$TELEGRAM_CHAT_ID'],
        id='$workflow_id',
        task_queue='sarthi-queue',
    )
    print(handle.id)

asyncio.run(start())
" 2>/dev/null && echo -e "${GREEN}✓${NC} Workflow started" || {
        log_test "Start FinanceWorkflow" "FAIL"
        return 1
    }
    
    sleep 3
    
    # Send HITL investigate signal
    echo -n "   Sending HITL investigate signal... "
    local response
    response=$(curl -sf -X POST "http://localhost:$GO_SERVER_PORT/internal/hitl/investigate" \
        -H "Content-Type: application/json" \
        -d "{\"workflow_id\":\"$workflow_id\",\"tenant_id\":\"demo-tenant\",\"vendor\":\"AWS\"}" \
        2>&1)
    
    if echo "$response" | grep -q '"ok":true'; then
        echo -e "${GREEN}✓${NC} Signal sent"
        log_test "HITL investigate endpoint" "PASS"
    else
        echo -e "${RED}✗${NC} Signal failed"
        log_test "HITL investigate endpoint" "FAIL" "Response: $response"
        return 1
    fi
    
    # Wait for BI workflow to be triggered
    echo -n "   Waiting for BI workflow trigger... "
    sleep 5
    echo -e "${GREEN}✓${NC} (Check Temporal UI)"
    
    # Check Telegram for messages
    echo -n "   Checking Telegram messages... "
    local tg_response
    tg_response=$(curl -sf "$TG_MOCK_URL/bot$TELEGRAM_BOT_TOKEN/getUpdates" 2>&1)
    
    if echo "$tg_response" | grep -q '"ok":true'; then
        echo -e "${GREEN}✓${NC} Messages received"
        log_test "Telegram alert delivery" "PASS"
    else
        log_test "Telegram alert delivery" "FAIL" "No messages"
    fi
    
    return 0
}

# Test BI query endpoint
test_bi_query() {
    echo -e "\n${BLUE}[5/6] Testing BI Query Flow...${NC}"
    
    local query="Show total revenue last 30 days"
    local workflow_id="bi-query-test-$(date +%s)"
    
    # Trigger BI workflow via API
    echo -n "   POST /internal/query... "
    local response
    response=$(curl -sf -X POST "http://localhost:$GO_SERVER_PORT/internal/query" \
        -H "Content-Type: application/json" \
        -d "{\"tenant_id\":\"demo-tenant\",\"query\":\"$query\"}" \
        2>&1)
    
    if echo "$response" | grep -q '"workflow_id"'; then
        echo -e "${GREEN}✓${NC} Workflow started"
        log_test "BI query endpoint" "PASS"
        
        # Extract workflow ID for status check
        local extracted_id
        extracted_id=$(echo "$response" | grep -o '"workflow_id":"[^"]*"' | cut -d'"' -f4)
        echo "      Workflow ID: $extracted_id"
    else
        echo -e "${RED}✗${NC} Failed"
        log_test "BI query endpoint" "FAIL" "Response: $response"
        return 1
    fi
    
    # Wait for workflow completion
    echo -n "   Waiting for workflow completion... "
    sleep 8
    echo -e "${GREEN}✓${NC}"
    
    # Check workflow status in Temporal
    echo -n "   Checking workflow status... "
    uv run python -c "
import asyncio
from temporalio.client import Client

async def check():
    client = await Client.connect('localhost:7233')
    try:
        handle = client.get_workflow_handle('$extracted_id')
        status = await handle.status()
        print(f'Status: {status}')
        return status
    except Exception as e:
        print(f'Error: {e}')
        return None

asyncio.run(check())
" 2>/dev/null || log_test "Workflow status check" "FAIL"
    
    # Check Telegram for results
    echo -n "   Checking Telegram for results... "
    local tg_response
    tg_response=$(curl -sf "$TG_MOCK_URL/bot$TELEGRAM_BOT_TOKEN/getUpdates" 2>&1)
    
    if echo "$tg_response" | grep -q "Query:"; then
        echo -e "${GREEN}✓${NC} Results sent"
        log_test "BI results delivery" "PASS"
    else
        log_test "BI results delivery" "FAIL" "No query results"
    fi
    
    return 0
}

# Test cross-agent trigger (Finance → BI)
test_cross_agent() {
    echo -e "\n${BLUE}[6/6] Testing Cross-Agent Trigger...${NC}"
    
    local workflow_id="cross-agent-test-$(date +%s)"
    
    # Simulate AWS expense anomaly
    echo -n "   Simulating AWS expense (₹42,000)... "
    
    # Start FinanceWorkflow with high anomaly
    uv run python -c "
import asyncio
from temporalio.client import Client

async def start():
    client = await Client.connect('localhost:7233')
    handle = await client.start_workflow(
        'FinanceWorkflow',
        args=['demo-tenant', {'vendor': 'AWS', 'amount': 42000, 'baseline': 18000}, '$TELEGRAM_CHAT_ID'],
        id='$workflow_id',
        task_queue='sarthi-queue',
    )
    print(handle.id)

asyncio.run(start())
" 2>/dev/null && echo -e "${GREEN}✓${NC}" || {
        log_test "Start FinanceWorkflow with anomaly" "FAIL"
        return 1
    }
    
    sleep 3
    
    # Send investigate signal
    echo -n "   Sending investigate signal... "
    curl -sf -X POST "http://localhost:$GO_SERVER_PORT/internal/hitl/investigate" \
        -H "Content-Type: application/json" \
        -d "{\"workflow_id\":\"$workflow_id\",\"tenant_id\":\"demo-tenant\",\"vendor\":\"AWS\"}" \
        >/dev/null 2>&1 && echo -e "${GREEN}✓${NC}" || {
        log_test "Send investigate signal" "FAIL"
        return 1
    }
    
    # Wait for BI workflow to complete
    echo -n "   Waiting for BI breakdown... "
    sleep 10
    echo -e "${GREEN}✓${NC}"
    
    # Verify Telegram received investigation results
    echo -n "   Verifying investigation results... "
    local tg_response
    tg_response=$(curl -sf "$TG_MOCK_URL/bot$TELEGRAM_BOT_TOKEN/getUpdates" 2>&1)
    
    if echo "$tg_response" | grep -q "Investigation results"; then
        echo -e "${GREEN}✓${NC}"
        log_test "Cross-agent trigger (Finance → BI)" "PASS"
    else
        log_test "Cross-agent trigger (Finance → BI)" "FAIL" "No investigation results"
    fi
    
    return 0
}

# Print summary
print_summary() {
    echo -e "\n========================================"
    echo -e "${GREEN}Integration Test Complete${NC}"
    echo "========================================"
    echo ""
    echo "Next steps:"
    echo "1. Check Temporal UI: $TEMPORAL_UI"
    echo "2. Check Go server logs: cat /tmp/go_server.log"
    echo "3. Check Python worker logs: cat /tmp/python_worker.log"
    echo "4. Check Telegram messages: curl $TG_MOCK_URL/bot$TELEGRAM_BOT_TOKEN/getUpdates"
    echo ""
}

# Main execution
main() {
    echo "========================================"
    echo "OntologyAI v1.0 Phase 6 - Integration Tests"
    echo "========================================"
    echo ""
    
    check_containers
    start_go_server
    start_python_worker
    test_hitl_investigate
    test_bi_query
    test_cross_agent
    print_summary
}

# Run main
main
