// Command migrate applies SQL migrations to PostgreSQL.
//
// A fresh deployment must go: empty Postgres -> migration runner -> schema ->
// application. Previously no binary, Dockerfile or compose step applied
// migrations, so a fresh database stayed empty and the app started against
// missing tables. Only scripts/dev/start.sh and CI ran them, by hand.
//
// Migrations are discovered from two directories that exist in the repo:
//
//	internal/db/migrations   001..010
//	migrations               001..005, 011..012
//
// Their numeric prefixes collide, so ordering is resolved by sorting on the
// full filename within a stable directory order rather than by prefix alone.
// Every applied file is recorded in schema_migrations, making the run
// idempotent and re-runnable.
package main

import (
	"database/sql"
	"flag"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"sort"
	"strings"

	_ "github.com/lib/pq"
)

// migrationDirs is the canonical, ordered set of migration directories.
// Order matters: internal/db/migrations is the original sqlc-backed series
// and must be applied before the later migrations/ additions.
var migrationDirs = []string{
	"internal/db/migrations",
	"migrations",
}

type migration struct {
	Version string
	Path    string
}

func main() {
	var (
		dbURL  = flag.String("db", envOr("DATABASE_URL", ""), "PostgreSQL connection string")
		status = flag.Bool("status", false, "report applied/pending migrations and exit")
		dir    = flag.String("dir", ".", "apps/core directory containing the migration folders")
	)
	flag.Parse()

	if *dbURL == "" {
		log.Fatal("DATABASE_URL (or -db) is required")
	}

	db, err := sql.Open("postgres", *dbURL)
	if err != nil {
		log.Fatalf("open database: %v", err)
	}
	defer db.Close()
	if err := db.Ping(); err != nil {
		log.Fatalf("ping database: %v", err)
	}

	if _, err := db.Exec(`CREATE TABLE IF NOT EXISTS schema_migrations (
		version     TEXT PRIMARY KEY,
		path        TEXT NOT NULL,
		applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
	)`); err != nil {
		log.Fatalf("create schema_migrations: %v", err)
	}

	migrations, err := discover(*dir)
	if err != nil {
		log.Fatalf("discover migrations: %v", err)
	}

	applied := map[string]bool{}
	rows, err := db.Query(`SELECT version FROM schema_migrations`)
	if err != nil {
		log.Fatalf("read schema_migrations: %v", err)
	}
	defer rows.Close()
	for rows.Next() {
		var v string
		if err := rows.Scan(&v); err != nil {
			log.Fatalf("scan schema_migrations: %v", err)
		}
		applied[v] = true
	}
	if err := rows.Err(); err != nil {
		log.Fatalf("iterate schema_migrations: %v", err)
	}

	pending := 0
	for _, m := range migrations {
		if applied[m.Version] {
			continue
		}
		pending++
		if *status {
			fmt.Printf("pending  %s (%s)\n", m.Version, m.Path)
			continue
		}
		sqlBytes, err := os.ReadFile(m.Path)
		if err != nil {
			log.Fatalf("read %s: %v", m.Path, err)
		}
		tx, err := db.Begin()
		if err != nil {
			log.Fatalf("begin %s: %v", m.Version, err)
		}
		if _, err := tx.Exec(string(sqlBytes)); err != nil {
			_ = tx.Rollback()
			log.Fatalf("apply %s (%s): %v", m.Version, m.Path, err)
		}
		if _, err := tx.Exec(
			`INSERT INTO schema_migrations (version, path) VALUES ($1, $2)
			 ON CONFLICT (version) DO NOTHING`,
			m.Version, m.Path,
		); err != nil {
			_ = tx.Rollback()
			log.Fatalf("record %s: %v", m.Version, err)
		}
		if err := tx.Commit(); err != nil {
			log.Fatalf("commit %s: %v", m.Version, err)
		}
		log.Printf("applied %s (%s)", m.Version, m.Path)
	}

	if *status {
		log.Printf("%d migration(s) total, %d pending", len(migrations), pending)
		return
	}
	log.Printf("migrations complete: %d applied, %d already present", pending, len(migrations)-pending)
}

// discover returns every *.sql under the canonical directories, ordered by
// numeric prefix and then by filename.
//
// The two directories are NOT independent series. 002_sarthi_v1.sql expects
// `tenant_id` on tables that 001_sarthi_sop_runtime.sql creates with
// `founder_id`, and 003_saarathi_pivot.sql rewrites the same tables. Applying
// one directory fully before the other therefore fails; the series must be
// interleaved by numeric prefix, which is what this ordering does.
func discover(root string) ([]migration, error) {
	type prefixed struct {
		m   migration
		num int
	}
	var all []prefixed
	for _, d := range migrationDirs {
		abs := filepath.Join(root, d)
		entries, err := os.ReadDir(abs)
		if err != nil {
			if os.IsNotExist(err) {
				continue
			}
			return nil, fmt.Errorf("read %s: %w", abs, err)
		}
		for _, e := range entries {
			if e.IsDir() || !strings.HasSuffix(e.Name(), ".sql") {
				continue
			}
			num := 0
			if _, err := fmt.Sscanf(e.Name(), "%d", &num); err != nil {
				num = 1 << 30 // unnumbered files sort last
			}
			all = append(all, prefixed{
				m:   migration{Version: e.Name(), Path: filepath.Join(abs, e.Name())},
				num: num,
			})
		}
	}
	if len(all) == 0 {
		return nil, fmt.Errorf("no migrations found under %v", migrationDirs)
	}
	// Stable: same prefix keeps directory discovery order.
	sort.SliceStable(all, func(i, j int) bool {
		if all[i].num != all[j].num {
			return all[i].num < all[j].num
		}
		return all[i].m.Version < all[j].m.Version
	})
	out := make([]migration, 0, len(all))
	for _, p := range all {
		out = append(out, p.m)
	}
	return out, nil
}

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
