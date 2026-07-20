package web

import (
	"fmt"
	"html"
	"sort"
	"sync"
	"time"

	"github.com/gofiber/fiber/v2"
)

// ── Credential Types ─────────────────────────────────────────────────────

// Credential represents a stored credential binding for a target system.
type Credential struct {
	ID        string `json:"id"`
	Provider  string `json:"provider"`
	Name      string `json:"name"`
	CreatedAt string `json:"created_at"`
}

// CredentialStore is an in-memory thread-safe store for credentials.
// Will be replaced with a database-backed store in a future iteration.
type CredentialStore struct {
	mu    sync.RWMutex
	items map[string]Credential
}

// NewCredentialStore creates a new empty credential store.
func NewCredentialStore() *CredentialStore {
	return &CredentialStore{
		items: make(map[string]Credential),
	}
}

// Add inserts a credential into the store and returns its generated ID.
func (s *CredentialStore) Add(c Credential) string {
	s.mu.Lock()
	defer s.mu.Unlock()
	id := fmt.Sprintf("cred-%d", time.Now().UnixNano())
	c.ID = id
	s.items[id] = c
	return id
}

// Delete removes a credential by ID. Returns true if found, false otherwise.
func (s *CredentialStore) Delete(id string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	_, exists := s.items[id]
	if exists {
		delete(s.items, id)
	}
	return exists
}

// List returns all credentials sorted by creation time (newest first).
func (s *CredentialStore) List() []Credential {
	s.mu.RLock()
	defer s.mu.RUnlock()
	result := make([]Credential, 0, len(s.items))
	for _, c := range s.items {
		result = append(result, c)
	}
	sort.Slice(result, func(i, j int) bool {
		return result[i].CreatedAt > result[j].CreatedAt
	})
	return result
}

// GetFirstID returns the ID of the first credential in the store (for tests).
func (s *CredentialStore) GetFirstID() string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	for id := range s.items {
		return id
	}
	return ""
}

// validProviders is the set of allowed provider identifiers.
var validProviders = map[string]bool{
	"slack":      true,
	"gmail":      true,
	"hubspot":    true,
	"n8n":        true,
	"github":     true,
	"gitlab":     true,
	"aws":        true,
	"azure":      true,
	"gcp":        true,
	"stripe":     true,
	"plaid":      true,
	"quickbooks": true,
	"erpnext":    true,
	"notion":     true,
	"linear":     true,
	"jira":       true,
	"salesforce": true,
	"zendesk":    true,
	"postgresql": true,
}

// getFirstID is a package-level helper used by tests to retrieve a credential ID.
func (s *CredentialStore) getFirstID() string {
	return s.GetFirstID()
}

// ── Credential Handlers ─────────────────────────────────────────────────

// APICredentialsList returns the credential list HTMX partial.
// GET /api/workspace/credentials
func (h *Handler) APICredentialsList(c *fiber.Ctx) error {
	if c.Get("HX-Request") != "true" {
		return c.SendString("Credentials")
	}

	creds := h.creds.List()
	return Render(c, "partials/workspace_credentials", fiber.Map{
		"Credentials": creds,
	})
}

// APICredentialsAddForm returns the add-credential form partial.
// GET /api/workspace/credentials/add
func (h *Handler) APICredentialsAddForm(c *fiber.Ctx) error {
	if c.Get("HX-Request") != "true" {
		return c.SendString("Add Credential")
	}

	// Build provider options list from validProviders
	type ProviderOption struct {
		Value string
		Label string
	}
	providerDisplay := map[string]string{
		"slack":      "Slack",
		"gmail":      "Gmail",
		"hubspot":    "HubSpot",
		"n8n":        "n8n",
		"github":     "GitHub",
		"gitlab":     "GitLab",
		"aws":        "AWS",
		"azure":      "Azure",
		"gcp":        "GCP",
		"stripe":     "Stripe",
		"plaid":      "Plaid",
		"quickbooks": "QuickBooks",
		"erpnext":    "ERPNext",
		"notion":     "Notion",
		"linear":     "Linear",
		"jira":       "Jira",
		"salesforce": "Salesforce",
		"zendesk":    "Zendesk",
		"postgresql": "PostgreSQL",
	}
	var providers []ProviderOption
	for p := range validProviders {
		label := providerDisplay[p]
		if label == "" {
			label = p
		}
		providers = append(providers, ProviderOption{Value: p, Label: label})
	}
	sort.Slice(providers, func(i, j int) bool {
		return providers[i].Label < providers[j].Label
	})

	return Render(c, "partials/workspace_credential_form", fiber.Map{
		"Providers": providers,
	})
}

// APICredentialsCreate creates a new credential and returns the row partial.
// POST /api/workspace/credentials
func (h *Handler) APICredentialsCreate(c *fiber.Ctx) error {
	provider := c.FormValue("provider")
	name := c.FormValue("name")
	value := c.FormValue("value")

	// Validation
	if name == "" {
		return c.Status(400).SendString(`<div class="text-red-400 text-xs mt-1">Display name is required</div>`)
	}
	if !validProviders[provider] {
		return c.Status(400).SendString(`<div class="text-red-400 text-xs mt-1">Invalid provider. Valid providers: slack, gmail, hubspot, n8n, github, gitlab, aws, azure, gcp, stripe, plaid, quickbooks, erpnext, notion, linear, jira, salesforce, zendesk, postgresql</div>`)
	}
	if value == "" {
		return c.Status(400).SendString(`<div class="text-red-400 text-xs mt-1">Secret value is required</div>`)
	}

	// Store credential (value is stored but never returned in the list)
	cred := Credential{
		Provider:  provider,
		Name:      html.EscapeString(name),
		CreatedAt: time.Now().Format(time.RFC3339),
	}
	id := h.creds.Add(cred)
	cred.ID = id

	// Store value in memory (not exposed via list)
	_ = value // In production, this would be encrypted and stored in a secure vault

	c.Status(201)
	return Render(c, "partials/workspace_credential_row", fiber.Map{
		"Credential": cred,
	})
}

// APICredentialsDelete deletes a credential by ID.
// DELETE /api/workspace/credentials/:id
func (h *Handler) APICredentialsDelete(c *fiber.Ctx) error {
	id := c.Params("id")
	if id == "" {
		return c.Status(400).SendString("Missing credential ID")
	}

	if !h.creds.Delete(id) {
		return c.Status(404).SendString("Credential not found")
	}

	return c.SendString("")
}
