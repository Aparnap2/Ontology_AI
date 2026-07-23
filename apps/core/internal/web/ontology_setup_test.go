package web

import (
	"io"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gofiber/fiber/v2"
)

// ── Wizard Page ─────────────────────────────────────────────────────────

func TestOntologySetup_StartPage_ServesHTML(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	h.RegisterOntologySetupRoutes(app)

	req := httptest.NewRequest("GET", "/ontology-setup/eng-123", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	checks := []string{"Business Map Setup", "Problem Framing", "eng-123"}
	for _, check := range checks {
		if !strings.Contains(bodyStr, check) {
			t.Errorf("FAIL: Expected %q in response, got: %q", check, bodyStr)
		}
	}
}

// ── Step Rendering (string-based step names) ────────────────────────────

// advanceWizard submits steps sequentially to reach the desired current step.
func advanceWizard(app *fiber.App, engagementID string, targetStep int) {
	// Start the wizard
	app.Test(httptest.NewRequest("GET", "/ontology-setup/"+engagementID, nil))

	for step := 1; step < targetStep; step++ {
		path := "/ontology-setup/" + engagementID + "/step/" + string(rune('0'+step))
		req := httptest.NewRequest("POST", path,
			strings.NewReader("details=test"))
		req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
		req.Header.Set("HX-Request", "true")
		app.Test(req)
	}
}

func TestOntologySetup_Step1_RendersAfterStart(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	h.RegisterOntologySetupRoutes(app)

	// Start the wizard (starts at step 1, can access step 1 and 2)
	startReq := httptest.NewRequest("GET", "/ontology-setup/e-step1", nil)
	startReq.Header.Set("HX-Request", "true")
	app.Test(startReq)

	req := httptest.NewRequest("GET", "/ontology-setup/e-step1/step/problem_framing", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	if resp.StatusCode != 200 {
		t.Fatalf("Expected 200, got %d. Body: %s", resp.StatusCode, bodyStr)
	}

	if !strings.Contains(bodyStr, "Problem Framing") {
		t.Errorf("FAIL: Expected 'Problem Framing' in response, got: %q", bodyStr)
	}
}

func TestOntologySetup_Step2_AccessibleAfterStart(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	h.RegisterOntologySetupRoutes(app)

	// Start wizard — allows access to step 1 and step 2
	app.Test(httptest.NewRequest("GET", "/ontology-setup/e-evidence", nil))

	req := httptest.NewRequest("GET", "/ontology-setup/e-evidence/step/evidence_intake", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	if resp.StatusCode != 200 {
		t.Fatalf("Expected 200, got %d. Body: %s", resp.StatusCode, bodyStr)
	}

	if !strings.Contains(bodyStr, "Evidence Intake") {
		t.Errorf("FAIL: Expected 'Evidence Intake' in response, got: %q", bodyStr)
	}
}

func TestOntologySetup_Step3_AccessibleAfterStep1(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	h.RegisterOntologySetupRoutes(app)

	// Start wizard and submit step 1 — unlocks step 3
	advanceWizard(app, "e-candidate", 2)

	req := httptest.NewRequest("GET", "/ontology-setup/e-candidate/step/candidate_review", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	if resp.StatusCode != 200 {
		t.Fatalf("Expected 200, got %d. Body: %s", resp.StatusCode, bodyStr)
	}

	if !strings.Contains(bodyStr, "Candidate Review") {
		t.Errorf("FAIL: Expected 'Candidate Review' in response, got: %q", bodyStr)
	}
}

func TestOntologySetup_Step4_AccessibleAfterSteps1to2(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	h.RegisterOntologySetupRoutes(app)

	// Start wizard and submit steps 1-2 — unlocks step 4
	advanceWizard(app, "e-relationship", 3)

	req := httptest.NewRequest("GET", "/ontology-setup/e-relationship/step/relationship_review", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	if resp.StatusCode != 200 {
		t.Fatalf("Expected 200, got %d. Body: %s", resp.StatusCode, bodyStr)
	}

	if !strings.Contains(bodyStr, "Relationship Review") {
		t.Errorf("FAIL: Expected 'Relationship Review' in response, got: %q", bodyStr)
	}
}

func TestOntologySetup_Step5_AccessibleAfterSteps1to4(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	h.RegisterOntologySetupRoutes(app)

	// Start wizard and submit steps 1-4 — unlocks step 5
	advanceWizard(app, "e-approval", 5)

	req := httptest.NewRequest("GET", "/ontology-setup/e-approval/step/approval", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	if resp.StatusCode != 200 {
		t.Fatalf("Expected 200, got %d. Body: %s", resp.StatusCode, bodyStr)
	}

	if !strings.Contains(bodyStr, "Approval & Launch") {
		t.Errorf("FAIL: Expected 'Approval & Launch' in response, got: %q", bodyStr)
	}
}

// ── Step Post / Transition ────────────────────────────────────────────────

func TestOntologySetup_SubmitStep1_TransitionsToStep2(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	h.RegisterOntologySetupRoutes(app)

	// Start wizard
	app.Test(httptest.NewRequest("GET", "/ontology-setup/eng-456", nil))

	bodyPayload := "business_goal=Reduce+costs&scope_description=AP+workflow"
	req := httptest.NewRequest("POST", "/ontology-setup/eng-456/step/1",
		strings.NewReader(bodyPayload))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	if resp.StatusCode != 200 {
		t.Errorf("FAIL: Expected 200, got %d", resp.StatusCode)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	if !strings.Contains(bodyStr, "Evidence Intake") {
		t.Errorf("FAIL: Expected next step 'Evidence Intake' in response, got: %q", bodyStr)
	}
}

func TestOntologySetup_SubmitAllSteps_CompletesWizard(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	h.RegisterOntologySetupRoutes(app)

	// Start wizard
	app.Test(httptest.NewRequest("GET", "/ontology-setup/eng-789", nil))

	// Advance through steps 1-4
	for step := 1; step <= 4; step++ {
		path := "/ontology-setup/eng-789/step/" + string(rune('0'+step))
		stepReq := httptest.NewRequest("POST", path,
			strings.NewReader("details=test"))
		stepReq.Header.Set("Content-Type", "application/x-www-form-urlencoded")
		stepReq.Header.Set("HX-Request", "true")
		app.Test(stepReq)
	}

	// Submit final step (step 5)
	bodyPayload := "user_feedback=All+good"
	req := httptest.NewRequest("POST", "/ontology-setup/eng-789/step/5",
		strings.NewReader(bodyPayload))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	if !strings.Contains(bodyStr, "Setup Complete") {
		t.Errorf("FAIL: Expected 'Setup Complete' in response, got: %q", bodyStr)
	}
}

// ── Summary Page ────────────────────────────────────────────────────────

func TestOntologySetup_SummaryPage(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	h.RegisterOntologySetupRoutes(app)

	// Start wizard first
	app.Test(httptest.NewRequest("GET", "/ontology-setup/eng-123", nil))

	req := httptest.NewRequest("GET", "/ontology-setup/eng-123/summary", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	if resp.StatusCode != 200 {
		t.Errorf("FAIL: Expected 200, got %d", resp.StatusCode)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	if !strings.Contains(bodyStr, "Approval") {
		t.Errorf("FAIL: Expected 'Approval' in response, got: %q", bodyStr)
	}
}

// ── Launch ──────────────────────────────────────────────────────────────

func TestOntologySetup_LaunchReturnsSuccess(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	h.RegisterOntologySetupRoutes(app)

	// Start wizard first
	app.Test(httptest.NewRequest("GET", "/ontology-setup/eng-123", nil))

	req := httptest.NewRequest("POST", "/ontology-setup/eng-123/launch", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	if resp.StatusCode != 200 {
		t.Errorf("FAIL: Expected 200, got %d", resp.StatusCode)
	}

	body, _ := io.ReadAll(resp.Body)
	bodyStr := string(body)

	if !strings.Contains(bodyStr, "Setup launched") {
		t.Errorf("FAIL: Expected 'Setup launched' in response, got: %q", bodyStr)
	}
}

// ── Error Handling ──────────────────────────────────────────────────────

func TestOntologySetup_InvalidStep_Returns400(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	h.RegisterOntologySetupRoutes(app)

	app.Test(httptest.NewRequest("GET", "/ontology-setup/eng-123", nil))

	req := httptest.NewRequest("GET", "/ontology-setup/eng-123/step/invalid_step", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	if resp.StatusCode != 400 {
		t.Errorf("FAIL: Expected 400 for invalid step, got %d", resp.StatusCode)
	}
}

func TestOntologySetup_CannotSkipAhead(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	h.RegisterOntologySetupRoutes(app)

	// Start wizard - current step is 1, which allows up to step 2
	app.Test(httptest.NewRequest("GET", "/ontology-setup/e-skip", nil))

	req := httptest.NewRequest("GET", "/ontology-setup/e-skip/step/3", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	if resp.StatusCode != 400 {
		t.Errorf("FAIL: Expected 400 for skip, got %d", resp.StatusCode)
	}
}

func TestOntologySetup_WrongOrderSubmit_Returns400(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	h.RegisterOntologySetupRoutes(app)

	// Start wizard
	app.Test(httptest.NewRequest("GET", "/ontology-setup/e-wrong", nil))

	// Try to submit step 2 when on step 1
	req := httptest.NewRequest("POST", "/ontology-setup/e-wrong/step/2",
		strings.NewReader("details=test"))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	if resp.StatusCode != 400 {
		t.Errorf("FAIL: Expected 400 for wrong step, got %d: %s", resp.StatusCode, resp.Body)
	}
}

func TestOntologySetup_NoWizard_Returns404(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	h.RegisterOntologySetupRoutes(app)

	// Access step without starting the wizard
	req := httptest.NewRequest("GET", "/ontology-setup/no-such-engagement/step/problem_framing", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	if resp.StatusCode != 404 {
		t.Errorf("FAIL: Expected 404 for unstarted wizard, got %d", resp.StatusCode)
	}
}

func TestOntologySetup_NilHandler_DoesNotPanic(t *testing.T) {
	// All endpoints must work with nil DB/temporal
	app := fiber.New()
	h := NewHandler(nil, nil)
	h.RegisterOntologySetupRoutes(app)

	// GET start
	req := httptest.NewRequest("GET", "/ontology-setup/eng-nil/step/problem_framing", nil)
	req.Header.Set("HX-Request", "true")
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("GET step failed: %v", err)
	}
	if resp.StatusCode >= 500 {
		t.Errorf("FAIL: Expected <500, got %d", resp.StatusCode)
	}
}

// ── Route Registration ─────────────────────────────────────────────────

func TestOntologySetup_RoutesRegistered(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	h.RegisterOntologySetupRoutes(app)

	// Start the wizard
	app.Test(httptest.NewRequest("GET", "/ontology-setup/eng-1", nil))

	routes := []string{
		"/ontology-setup/eng-1",
		"/ontology-setup/eng-1/step/problem_framing",
		"/ontology-setup/eng-1/summary",
	}

	for _, route := range routes {
		req := httptest.NewRequest("GET", route, nil)
		resp, err := app.Test(req)
		if err != nil {
			t.Errorf("FAIL: Route %s failed: %v", route, err)
			continue
		}
		if resp.StatusCode >= 500 {
			t.Errorf("FAIL: Route %s returned %d", route, resp.StatusCode)
		}
	}
}

// ── Status Endpoint ─────────────────────────────────────────────────────

func TestOntologySetup_StatusEndpoint(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	h.RegisterOntologySetupRoutes(app)

	// Start wizard
	app.Test(httptest.NewRequest("GET", "/ontology-setup/eng-123", nil))

	req := httptest.NewRequest("GET", "/ontology-setup/eng-123/status", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	if resp.StatusCode != 200 {
		t.Errorf("FAIL: Expected 200, got %d", resp.StatusCode)
	}
}
