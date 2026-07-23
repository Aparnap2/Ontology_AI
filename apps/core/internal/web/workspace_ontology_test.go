package web

import (
	"encoding/json"
	"io"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gofiber/fiber/v2"
)

// ── Ontology Schema Tests (V5.1 canonical contract) ────────────────────
// The locked V5.1 contract specifies exactly 6 canonical object types and
// 9 link types. Artifact / Decision / Metric are V6 BABOK view-model
// categories, not V5.1 ontology types.

func TestWorkspaceOntology_ReturnsObjectTypes(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/workspace/ontology", h.APIWorkspaceOntology)

	req := httptest.NewRequest("GET", "/api/workspace/ontology", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	var result map[string]json.RawMessage
	if err := json.Unmarshal(body, &result); err != nil {
		t.Fatalf("Failed to parse JSON: %v", err)
	}

	var objectTypes []string
	if err := json.Unmarshal(result["object_types"], &objectTypes); err != nil {
		t.Fatalf("Failed to parse object_types: %v", err)
	}

	expectedObjects := V5_1_CANONICAL_OBJECT_TYPES

	if len(objectTypes) != len(expectedObjects) {
		t.Errorf("FAIL: Expected %d object types, got %d: %v",
			len(expectedObjects), len(objectTypes), objectTypes)
	}

	for _, exp := range expectedObjects {
		found := false
		for _, got := range objectTypes {
			if got == exp {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("FAIL: Missing object type %q in response: %v", exp, objectTypes)
		}
	}
}

func TestWorkspaceOntology_ReturnsLinkTypes(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/workspace/ontology", h.APIWorkspaceOntology)

	req := httptest.NewRequest("GET", "/api/workspace/ontology", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	var result map[string]json.RawMessage
	if err := json.Unmarshal(body, &result); err != nil {
		t.Fatalf("Failed to parse JSON: %v", err)
	}

	var linkTypes []string
	if err := json.Unmarshal(result["link_types"], &linkTypes); err != nil {
		t.Fatalf("Failed to parse link_types: %v", err)
	}

	expectedLinks := V5_1_CANONICAL_LINK_TYPES

	if len(linkTypes) != len(expectedLinks) {
		t.Errorf("FAIL: Expected %d link types, got %d: %v",
			len(expectedLinks), len(linkTypes), linkTypes)
	}

	for _, exp := range expectedLinks {
		found := false
		for _, got := range linkTypes {
			if got == exp {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("FAIL: Missing link type %q in response: %v", exp, linkTypes)
		}
	}
}

func TestWorkspaceOntology_ReturnsEmptyObjectsAndLinks(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/workspace/ontology", h.APIWorkspaceOntology)

	req := httptest.NewRequest("GET", "/api/workspace/ontology", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	var result map[string]json.RawMessage
	if err := json.Unmarshal(body, &result); err != nil {
		t.Fatalf("Failed to parse JSON: %v", err)
	}

	if string(result["objects"]) != "[]" {
		t.Errorf("FAIL: Expected empty objects array, got %s", string(result["objects"]))
	}
	if string(result["links"]) != "[]" {
		t.Errorf("FAIL: Expected empty links array, got %s", string(result["links"]))
	}
}

func TestWorkspaceOntology_HasJSONContentType(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/workspace/ontology", h.APIWorkspaceOntology)

	req := httptest.NewRequest("GET", "/api/workspace/ontology", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	ct := resp.Header.Get("Content-Type")
	if !strings.Contains(ct, "application/json") {
		t.Errorf("FAIL: Expected Content-Type application/json, got %q", ct)
	}
}

func TestWorkspaceOntology_CanonicalContractCounts(t *testing.T) {
	app := fiber.New()
	h := NewHandler(nil, nil)
	app.Get("/api/workspace/ontology", h.APIWorkspaceOntology)

	req := httptest.NewRequest("GET", "/api/workspace/ontology", nil)
	resp, err := app.Test(req)
	if err != nil {
		t.Fatalf("Failed: %v", err)
	}

	body, _ := io.ReadAll(resp.Body)
	var result map[string]json.RawMessage
	if err := json.Unmarshal(body, &result); err != nil {
		t.Fatalf("Failed to parse JSON: %v", err)
	}

	var objectTypes []string
	json.Unmarshal(result["object_types"], &objectTypes)
	var linkTypes []string
	json.Unmarshal(result["link_types"], &linkTypes)

	if len(objectTypes) != 6 {
		t.Errorf("FAIL: V5.1 contract requires exactly 6 canonical object types, got %d: %v",
			len(objectTypes), objectTypes)
	}
	if len(linkTypes) != 9 {
		t.Errorf("FAIL: V5.1 contract requires exactly 9 canonical link types, got %d: %v",
			len(linkTypes), linkTypes)
	}
}
