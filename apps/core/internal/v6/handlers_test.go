package v6

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gofiber/fiber/v2"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func newTestApp() *fiber.App {
	app := fiber.New()
	RegisterRoutes(app, &Dependencies{})
	return app
}

// concretePath substitutes route params with concrete values for test requests.
func concretePath(p string) string {
	return strings.ReplaceAll(p, ":id", "test-id")
}

func TestStatusReturns200(t *testing.T) {
	app := newTestApp()
	req := httptest.NewRequest(http.MethodGet, "/v6/status", nil)
	resp, err := app.Test(req)
	require.NoError(t, err)
	defer resp.Body.Close()
	assert.Equal(t, http.StatusOK, resp.StatusCode)
}

func TestStatusJSONShape(t *testing.T) {
	app := newTestApp()
	req := httptest.NewRequest(http.MethodGet, "/v6/status", nil)
	resp, err := app.Test(req)
	require.NoError(t, err)
	defer resp.Body.Close()

	var body map[string]any
	require.NoError(t, json.NewDecoder(resp.Body).Decode(&body))

	assert.Equal(t, float64(6), body["version"])
	assert.NotEmpty(t, body["branch"])

	inventory, ok := body["runtime_inventory"].([]any)
	require.True(t, ok, "runtime_inventory should be an array")
	assert.ElementsMatch(t, []string{
		"evidence",
		"knowledge",
		"mission",
		"employee",
		"capability",
		"memory",
		"governance",
		"workspace",
		"orchestration",
	}, inventory)

	rs, ok := body["route_status"].(map[string]any)
	require.True(t, ok, "route_status should be an object")
	assert.Equal(t, float64(len(v6Routes)), rs["total"])
	assert.Equal(t, float64(6), rs["implemented"]) // /health /status + 4 workspace panels
	assert.Equal(t, float64(len(v6Routes)-6), rs["stubs"])
}

func TestRouteCountsMatchRegistry(t *testing.T) {
	total, implemented, stubs := routeCounts()
	assert.Equal(t, len(v6Routes), total)
	assert.Equal(t, total, implemented+stubs)
	assert.Equal(t, 6, implemented) // /health /status + 4 workspace panels
}

func TestStubRoutesReturn501(t *testing.T) {
	app := newTestApp()
	for _, r := range v6Routes {
		if r.Implemented {
			continue
		}
		req := httptest.NewRequest(r.Method, "/v6"+concretePath(r.Path), nil)
		resp, err := app.Test(req)
		require.NoError(t, err, "route %s %s", r.Method, r.Path)
		assert.Equal(t, http.StatusNotImplemented, resp.StatusCode, "route %s %s", r.Method, r.Path)
		resp.Body.Close()
	}
}

func TestHealthReturns200(t *testing.T) {
	app := newTestApp()
	req := httptest.NewRequest(http.MethodGet, "/v6/health", nil)
	resp, err := app.Test(req)
	require.NoError(t, err)
	defer resp.Body.Close()
	assert.Equal(t, http.StatusOK, resp.StatusCode)
}
