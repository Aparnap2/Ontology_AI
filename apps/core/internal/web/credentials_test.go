package web

import (
	"io"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gofiber/fiber/v2"
)

// ── Credentials Panel ──────────────────────────────────────────────────

func TestCredentialsPanel_EmptyState(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/workspace/credentials", h.APICredentialsList)

	req := httptest.NewRequest("GET", "/api/workspace/credentials", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	if !strings.Contains(bodyStr, "No credentials configured") {
		t.Errorf("FAIL: Expected empty state 'No credentials configured', got: %q", bodyStr)
	}
}

func TestCredentialsPanel_WithoutHXRequest(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/workspace/credentials", h.APICredentialsList)

	req := httptest.NewRequest("GET", "/api/workspace/credentials", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := strings.TrimSpace(string(body))

	if bodyStr != "Credentials" {
		t.Errorf("FAIL: Expected 'Credentials', got: %q", bodyStr)
	}
}

func TestCredentialsPanel_NoDBNotCrash(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/workspace/credentials", h.APICredentialsList)

	req := httptest.NewRequest("GET", "/api/workspace/credentials", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	if resp.StatusCode != 200 {
		t.Errorf("FAIL: Expected 200, got %d", resp.StatusCode)
	}
}

// ── Add Credential Form ────────────────────────────────────────────────

func TestAddCredentialForm(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/workspace/credentials/add", h.APICredentialsAddForm)

	req := httptest.NewRequest("GET", "/api/workspace/credentials/add", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	checks := []string{"Add Credential", "Provider", "Display Name", "Secret Value"}
	for _, check := range checks {
		if !strings.Contains(bodyStr, check) {
			t.Errorf("FAIL: Expected '%s' in form, got: %q", check, bodyStr)
		}
	}
}

// ── Create Credential ──────────────────────────────────────────────────

func TestCreateCredential(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Post("/api/workspace/credentials", h.APICredentialsCreate)

	bodyPayload := "provider=slack&name=My+Slack+Token&value=xoxb-123"
	req := httptest.NewRequest("POST", "/api/workspace/credentials", strings.NewReader(bodyPayload))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	if resp.StatusCode != 201 {
		t.Errorf("FAIL: Expected 201, got %d", resp.StatusCode)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	if !strings.Contains(bodyStr, "slack") {
		t.Errorf("FAIL: Expected credential to contain 'slack', got: %q", bodyStr)
	}
	if !strings.Contains(bodyStr, "My Slack Token") {
		t.Errorf("FAIL: Expected credential to contain 'My Slack Token', got: %q", bodyStr)
	}

	// Verify it's in the store
	h.creds.mu.RLock()
	credsCount := len(h.creds.items)
	h.creds.mu.RUnlock()
	if credsCount != 1 {
		t.Errorf("FAIL: Expected 1 credential in store, got %d", credsCount)
	}
}

// ── Validation ─────────────────────────────────────────────────────────

func TestCreateCredentialValidation_EmptyName(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Post("/api/workspace/credentials", h.APICredentialsCreate)

	bodyPayload := "provider=slack&name=&value=secret"
	req := httptest.NewRequest("POST", "/api/workspace/credentials", strings.NewReader(bodyPayload))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	if resp.StatusCode != 400 {
		t.Errorf("FAIL: Expected 400 for empty name, got %d", resp.StatusCode)
	}
}

func TestCreateCredentialValidation_InvalidProvider(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Post("/api/workspace/credentials", h.APICredentialsCreate)

	bodyPayload := "provider=invalid_provider&name=Test&value=secret"
	req := httptest.NewRequest("POST", "/api/workspace/credentials", strings.NewReader(bodyPayload))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	if resp.StatusCode != 400 {
		t.Errorf("FAIL: Expected 400 for invalid provider, got %d", resp.StatusCode)
	}
}

func TestCreateCredentialValidation_EmptyValue(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Post("/api/workspace/credentials", h.APICredentialsCreate)

	bodyPayload := "provider=slack&name=Test&value="
	req := httptest.NewRequest("POST", "/api/workspace/credentials", strings.NewReader(bodyPayload))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	if resp.StatusCode != 400 {
		t.Errorf("FAIL: Expected 400 for empty value, got %d", resp.StatusCode)
	}
}

// ── Delete Credential ──────────────────────────────────────────────────

func TestDeleteCredential(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Delete("/api/workspace/credentials/:id", h.APICredentialsDelete)

	// First add a credential to the store
	h.creds.mu.Lock()
	h.creds.items["test-1"] = Credential{
		ID:        "test-1",
		Provider:  "slack",
		Name:      "Test Token",
		CreatedAt: time.Now().Format(time.RFC3339),
	}
	h.creds.mu.Unlock()

	req := httptest.NewRequest("DELETE", "/api/workspace/credentials/test-1", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	if resp.StatusCode != 200 {
		t.Errorf("FAIL: Expected 200, got %d", resp.StatusCode)
	}

	// Verify it's gone
	h.creds.mu.RLock()
	_, exists := h.creds.items["test-1"]
	h.creds.mu.RUnlock()
	if exists {
		t.Errorf("FAIL: Credential 'test-1' should have been deleted")
	}
}

func TestDeleteCredential_NotFound(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Delete("/api/workspace/credentials/:id", h.APICredentialsDelete)

	req := httptest.NewRequest("DELETE", "/api/workspace/credentials/nonexistent", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	if resp.StatusCode != 404 {
		t.Errorf("FAIL: Expected 404 for nonexistent credential, got %d", resp.StatusCode)
	}
}

// ── Credential List Shows Stored Items ─────────────────────────────────

func TestCredentialList_ShowsStoredCredentials(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/workspace/credentials", h.APICredentialsList)

	h.creds.mu.Lock()
	h.creds.items["c1"] = Credential{ID: "c1", Provider: "slack", Name: "Workspace Token", CreatedAt: time.Now().Format(time.RFC3339)}
	h.creds.items["c2"] = Credential{ID: "c2", Provider: "hubspot", Name: "HubSpot API Key", CreatedAt: time.Now().Format(time.RFC3339)}
	h.creds.mu.Unlock()

	req := httptest.NewRequest("GET", "/api/workspace/credentials", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	if !strings.Contains(bodyStr, "Workspace Token") {
		t.Errorf("FAIL: Expected 'Workspace Token' in list, got: %q", bodyStr)
	}
	if !strings.Contains(bodyStr, "HubSpot API Key") {
		t.Errorf("FAIL: Expected 'HubSpot API Key' in list, got: %q", bodyStr)
	}
	if !strings.Contains(bodyStr, "slack") {
		t.Errorf("FAIL: Expected 'slack' provider badge in list, got: %q", bodyStr)
	}
	if !strings.Contains(bodyStr, "hubspot") {
		t.Errorf("FAIL: Expected 'hubspot' provider badge in list, got: %q", bodyStr)
	}
}

// ── Full E2E Flow (in-memory) ──────────────────────────────────────────

func TestCredentialFullFlow(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/workspace/credentials", h.APICredentialsList)
	app.Post("/api/workspace/credentials", h.APICredentialsCreate)
	app.Delete("/api/workspace/credentials/:id", h.APICredentialsDelete)

	// Step 1: GET — empty state
	req := httptest.NewRequest("GET", "/api/workspace/credentials", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	body, _ := io.ReadAll(resp.Body)
	if !strings.Contains(string(body), "No credentials configured") {
		t.Errorf("FAIL Step 1: Expected empty state, got: %q", string(body))
	}

	// Step 2: POST — create a credential
	bodyPayload := "provider=gmail&name=My+Gmail+Key&value=secret-123"
	req2 := httptest.NewRequest("POST", "/api/workspace/credentials", strings.NewReader(bodyPayload))
	req2.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req2.Header.Set("HX-Request", "true")
	resp2, err := app.Test(req2)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	if resp2.StatusCode != 201 {
		t.Errorf("FAIL Step 2: Expected 201, got %d", resp2.StatusCode)
	}
	body2, _ := io.ReadAll(resp2.Body)
	if !strings.Contains(string(body2), "My Gmail Key") {
		t.Errorf("FAIL Step 2: Expected 'My Gmail Key' in response, got: %q", string(body2))
	}

	// Grab the credential ID from the response
	credID := h.creds.getFirstID()

	// Step 3: GET — list should show the credential
	req3 := httptest.NewRequest("GET", "/api/workspace/credentials", nil)
	req3.Header.Set("HX-Request", "true")
	resp3, err := app.Test(req3)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	body3, _ := io.ReadAll(resp3.Body)
	if !strings.Contains(string(body3), "My Gmail Key") {
		t.Errorf("FAIL Step 3: Expected 'My Gmail Key' in list, got: %q", string(body3))
	}

	// Step 4: DELETE the credential
	req4 := httptest.NewRequest("DELETE", "/api/workspace/credentials/"+credID, nil)
	req4.Header.Set("HX-Request", "true")
	resp4, err := app.Test(req4)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	if resp4.StatusCode != 200 {
		t.Errorf("FAIL Step 4: Expected 200 on delete, got %d", resp4.StatusCode)
	}

	// Step 5: GET — list should be empty again
	req5 := httptest.NewRequest("GET", "/api/workspace/credentials", nil)
	req5.Header.Set("HX-Request", "true")
	resp5, err := app.Test(req5)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}
	body5, _ := io.ReadAll(resp5.Body)
	if strings.Contains(string(body5), "My Gmail Key") {
		t.Errorf("FAIL Step 5: Credential should not appear after delete, got: %q", string(body5))
	}
	if !strings.Contains(string(body5), "No credentials configured") {
		t.Errorf("FAIL Step 5: Expected empty state after delete, got: %q", string(body5))
	}
}
