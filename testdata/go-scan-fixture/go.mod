// Fixture for the security-scan.yaml `language: go` self-test: a real go.mod so `grype dir:.`
// exercises its Go cataloger (no Python setup involved). Intentionally has no dependencies, so
// the scan is deterministic (zero findings, passes) and can't flake on Grype DB changes — the
// test's job is to prove the Go path runs end to end, not to assert a specific CVE.
module example.com/plainsightai/security-scan-go-fixture

go 1.22
