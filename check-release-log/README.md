# ✅ Check Release Log

This composite GitHub Action ensures that your `RELEASE.md` changelog is properly maintained on every pull request to `main`. It checks that:

- The `RELEASE.md` file has been updated
- The changelog follows expected format and parsing succeeds
- (Optional) The `VERSION` file (if present) matches the latest changelog entry
- (Optional) The `VERSION` file is not behind the base branch (catches stale branches)

---

## 🔧 Usage

Default (every PR to `main` must update `RELEASE.md`):

```yaml
jobs:
  check-release-log:
    if: github.event_name == 'pull_request' && github.base_ref == 'main'
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v6

      - name: Check RELEASE.md
        uses: PlainsightAI/gh-actions-public/check-release-log@main
```

Gated on substantive changes (CI-only / test-only / docs-only PRs skip the check):

```yaml
# Filter-repo convention (filter_sam3_detector, filter_global_position, etc.)
- name: Check RELEASE.md
  uses: PlainsightAI/gh-actions-public/check-release-log@main
  with:
    source-paths: |
      filter_*/**
      pyproject.toml
      Dockerfile*
      requirements*.txt
```

Do NOT include `RELEASE.md` itself in `source-paths` — the downstream step already checks that, and including it here creates a tautology where any `RELEASE.md` edit satisfies the gate regardless of substantive change.

For repos that don't follow the `filter_*/**` convention, use whatever source layout applies (e.g. `src/**`):

```yaml
- name: Check RELEASE.md
  uses: PlainsightAI/gh-actions-public/check-release-log@main
  with:
    source-paths: |
      src/**
      pyproject.toml
      Dockerfile*
      requirements*.txt
```

Alternatively, express the gate as an exclude-list via `ignore-paths` — useful when enumerating every substantive top-level directory invites drift (repo adds a new source dir, `source-paths` isn't updated, gate silently misses the change):

```yaml
- name: Check RELEASE.md
  uses: PlainsightAI/gh-actions-public/check-release-log@main
  with:
    ignore-paths: |
      docs/**
      .github/**
      **/*.md
```

If the PR touches none of the listed globs (or, for `ignore-paths`, ONLY files matching the ignore globs), the action exits 0 as a no-op: no `RELEASE.md` requirement, no `VERSION` bump check. This matches the pattern used in `protege-ml`'s `pr.yaml` (where the check-release-log job is gated externally via `dorny/paths-filter`), pushed down into the composite so every consumer gets it for free.

---

## 📥 Inputs

| Input          | Required | Default | Description |
|----------------|----------|---------|-------------|
| `source-paths` | no       | `''`    | Newline-separated glob patterns considered "substantive". When set and the PR touches none of them, the action is a no-op. When unset, every PR to main requires a `RELEASE.md` update (original behavior). Do NOT include `RELEASE.md` itself — it creates a tautology with the downstream check. |
| `ignore-paths` | no       | `''`    | Newline-separated glob patterns of paths that do NOT count as substantive. When set, the action is a no-op if the PR changes ONLY files matching these globs. Can be combined with `source-paths`; both filters apply. |

---

## 📋 Behavior

| Check                           | Description |
|----------------------------------|-------------|
| Substantive-change gate (optional) | If `source-paths` is set and the PR touches none of them, or if `ignore-paths` is set and the PR changes ONLY files matching those globs, all subsequent checks are skipped and the action passes. Both inputs can be combined; the gate fires when either condition applies. |
| `RELEASE.md` updated            | Fails the PR if `RELEASE.md` is not modified |
| Changelog entry parsing         | Uses [`changelog-parser-action`](https://github.com/PlainsightAI/changelog-parser-action) to extract the latest changelog version |
| `VERSION` consistency (optional)| If a `VERSION` file exists, it must match the parsed changelog version |
| `VERSION` not behind base (optional) | If a `VERSION` file exists on both the PR and base branch, ensures the PR version is not behind the base branch. Catches stale branches that diverged before a version bump on `main`. Only compares plain `X.Y.Z` versions — skips gracefully for pre-release suffixes or missing VERSION files. |

---

## 🔌 Integration

This action is typically used as part of your PR CI checks for repositories that publish versioned packages, Docker images, or documentation.

---

## 📁 File Structure

This action assumes your changelog lives at:

```
RELEASE.md
```

You may use the [`path` input](https://github.com/PlainsightAI/changelog-parser-action#-usage) on the parser to override this in the future.

---

## 🛠 Related Actions

- [`create-release`](https://github.com/PlainsightAI/gh-actions-public/blob/main/.github/workflows/filter-release.yaml) – Parses `RELEASE.md`, checks the `VERSION` file, and pushes a GitHub release.
- [`changelog-parser-action`](https://github.com/PlainsightAI/changelog-parser-action) – Custom changelog parser with support for production/pre-release tagging.
