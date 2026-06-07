# Filter-release → consumer cascade — consumer surface

**Ticket:** [PLAT-1052](https://plainsight-ai.atlassian.net/browse/PLAT-1052) — Phase 1 deliverable.

This document records the PR-walkable surfaces where filter image tags are pinned in production-bearing or production-adjacent repos, documenting each consumer's `(path glob, pin pattern, bump strategy)`. After Phase 1 investigation the live cascade surface is a single repo — `openfilter-pipelines-controller` — so the cascade hardcodes a one-entry matrix in `cascade-pipeline-bumps.yaml` rather than discovering consumers at runtime; a per-shard resolve-check guards against a typo'd or deleted repo. The rest of this doc is the audit trail of the candidates that were considered and why each was kept, dropped, or scoped out. The pin shapes below are what the content-driven `bump-strategy.sh` must handle.

## TL;DR

| # | Repo | Path glob | Pin form | Bump strategy | In scope? |
|---|---|---|---|---|---|
| 1 | `PlainsightAI/openfilter-pipelines-controller` | `demo/pipeline_*.yaml`, `config/samples/pipelines_*.yaml` | `image: plainsightai/openfilter-<name>:v<ver>` (DockerHub) and `ghcr.io/plainsightai/openfilter-<name>:latest` | YAML in-place rewrite of `<ver>` on DockerHub-pinned entries only; `:latest` entries skipped (intent is "track tip") | **Yes** — the one live consumer |
| 2 | `PlainsightAI/jester-pipelines` | `deploy/**/base/deployment.yaml`, `deploy/**/overlays/*/patch.yaml` | `image: us-west1-docker.pkg.dev/plainsightai-prod/oci/<filter>:<tag>` (GAR) | YAML in-place rewrite of `<tag>` | **No** — dropped (see Section 1): effectively dormant (last real push 2026-01), and its GAR pins depend on an unconfirmed mirror sync (Open question 1) |
| 3 | `PlainsightAI/eval-demo-pipelines` | n/a — **does not exist** | n/a | n/a | **No** — this repo never existed (org audit log shows no create/rename/destroy footprint); the row was authored in error and removed (see Section 3) |
| 4 | `PlainsightAI/openfilter-hub` | n/a — **investigated and rejected** | filter metadata fetched from `https://api.prod.plainsight.tech` at build time; no image tags pinned in the repo | n/a | **No** — listed in ticket as a candidate; confirmed not a cascade target |
| 5 | `plainsight-api` DB-stored PipelineInstance specs | n/a — **out of scope** | hardcoded image tags in DB rows authored by users | n/a | **No** — ticket explicitly scopes this out; follow-up needed |

## Section 1 — `jester-pipelines` (dropped from the live cascade)

**Not currently a cascade target.** `jester-pipelines` is effectively dormant (last real push 2026-01) and its pins are GAR-registry coordinates whose bump only does something useful if a DockerHub→GAR mirror sync exists on release — unconfirmed (Open question 1). Rather than carry a consumer that may rewrite to non-resolving tags, it's left out of the matrix. The analysis below is retained so it can be re-added deliberately if those questions are resolved.

### What's there

Two pipeline compositions:

- `deploy/jester-pipelines/...` — the `jester-pipelines` service itself. Image is `oci/jester-pipelines`, not a filter. **Not a cascade target.**
- `deploy/data-injestion-demo/...` — the data-ingestion demo pipeline. Two image pins:

  ```yaml
  # deploy/data-injestion-demo/base/deployment.yaml:20
  image: us-west1-docker.pkg.dev/plainsightai-prod/oci/video_in:1.4.18
  # deploy/data-injestion-demo/base/deployment.yaml:41
  image: us-west1-docker.pkg.dev/plainsightai-prod/oci/filter-connector-gcs:1.4.8
  ```

  Overlays under `deploy/data-injestion-demo/overlays/{development,staging,production}/patch.yaml` reference these containers by `name:` but **do not override the `image:`** — the base pin governs all envs.

### Registry mismatch — critical to handle in Phase 2

The pins are **Google Artifact Registry** (`us-west1-docker.pkg.dev/plainsightai-prod/oci/`), but `filter-release.yaml` pushes to **DockerHub** (`plainsightai/<filter>`). For the cascade to do something useful here, one of the following must already be true:

1. A separate mirror sync pushes DockerHub → GAR after release (confirm with infra before Phase 2 ships).
2. The filter repos that produce GAR-targeted images use a *different* release workflow that publishes to GAR directly. `filter-connector-gcs` versioning (`1.4.8`) is far from the openfilter SDK line (`0.2.x`), which is a strong signal it has an independent release pipeline.

**Phase 2 recommendation:** the cascade should always cross-match the released image's repo basename (`filter-connector-gcs`) against the pin's repo basename, independent of registry host. If a mirror does not exist, the bump PR will rewrite to a tag that does not yet resolve on GAR — caught by the consumer's own CI before merge, not by the cascade.

### Bump strategy

For each filter release `<name>:<new>`:

```text
in:  deploy/**/{base/deployment.yaml,overlays/*/patch.yaml}
pin: image: <registry>/<repo-prefix>/<name>:<any-tag>
out: image: <registry>/<repo-prefix>/<name>:<new>
```

Use a YAML-aware rewriter (e.g. `yq` `-i` with a path predicate on `.spec.template.spec.containers[].image`) rather than a blind `sed`, so unrelated `image:` keys in commented blocks or sub-templates are untouched.

### Flux `$imagepolicy` interaction

`deploy/jester-pipelines/overlays/{development,staging,production}/patch.yaml` carries `# {"$imagepolicy": "<ns>:jester-pipelines"}` markers driven by flux's `ImagePolicy` reconciler. These pins are governed by flux, not a cascade. **The cascade must not write to lines carrying `$imagepolicy` markers** — a PR-driven rewrite would race the reconciler's next bump and either no-op or revert. The YAML-path predicate above already misses these (they live under different paths in the kustomize patch shape), but Phase 2 should add an explicit check that skips any image whose trailing comment contains `$imagepolicy`.

## Section 2 — `openfilter-pipelines-controller`

### What's there

Two classes of in-repo pinning:

1. **Demo / sample PipelineInstance manifests** under `demo/pipeline_*.yaml` and `config/samples/pipelines_v1alpha1_pipeline_*.yaml`. These are real PipelineInstance CR YAMLs used as documentation / smoke tests. Pin form:

   ```yaml
   image: plainsightai/openfilter-video-in:v0.1.10
   image: plainsightai/openfilter-faceblur:v1.1.4
   image: plainsightai/openfilter-webvis:v0.1.10
   image: plainsightai/openfilter-image-out:v0.1.14
   ```

   A subset is pinned to `ghcr.io/plainsightai/openfilter-<name>:latest` — the cascade must **skip `:latest`** (deliberate intent to track tip; a cascade rewrite to a specific version would defeat the point).

2. **Helm chart values** under `charts/openfilter-pipelines-controller/values{,-production}.yaml` pin the controller's *own* image (`plainsightai/openfilter-pipelines-controller`). **Not a filter image — out of scope** for this cascade.

### Business value

Demo manifests are documentation. They will not cause a production regression if they lag. Including them in the cascade still has two real benefits:

- **Consistency with first-level contract.** First-level cascade (openfilter SDK → filter-* source bumps) walks every eligible repo regardless of business-criticality; the second level should match that contract so the population is predictable.
- **Smoke test surface.** A failed demo bump PR is a cheap canary for breaking changes that would otherwise only surface in production pipelines.

### Bump strategy

```text
in:  demo/pipeline_*.yaml, config/samples/pipelines_*.yaml
pin: image: plainsightai/openfilter-<name>:v<ver>   (DockerHub form only)
out: image: plainsightai/openfilter-<name>:v<new>
skip: any image ending in `:latest`
skip: any image not matching the released filter's repo basename
```

## Section 3 — `eval-demo-pipelines` (removed — never existed)

This section originally specified `PlainsightAI/eval-demo-pipelines` as a third cascade consumer with three coexisting pin shapes (bare DockerHub/Scarf literal, bare GAR literal, and a `${VAR:-default}` env override). **That repo never existed.** `gh repo view PlainsightAI/eval-demo-pipelines` returns `Could not resolve to a Repository`, and the org audit log shows zero create/rename/destroy footprint for the name — so it is not a rename or a deletion either. The entry was authored speculatively during Phase 1 and shipped into the cascade matrix in #19, where it 404'd on clone for every production filter release and fired the "human needs to investigate" Slack alert.

It has been removed from the cascade matrix. No real repo was an obvious typo target — a scan of the `PlainsightAI` org surfaced no `docker-compose`-pinning consumer matching the described layout — so this was dropped, not renamed. If a Docker-Compose-based consumer is later stood up, enrol it by adding a row to the bump matrix in `cascade-pipeline-bumps.yaml` and restoring a strategy section here describing its pin shapes.

## Section 4 — `openfilter-hub` (rejected)

The ticket's Phase 1 candidate list names `openfilter-hub` as a "filter helm charts" surface. **This is wrong.** `openfilter-hub` is a Next.js gallery site (`hub.openfilter.io`). Its filter catalog is populated at SSG/SSR time by fetching `https://api.prod.plainsight.tech` (see `pages/index.tsx`); there are zero image tags pinned in the repo. The `latest_version` shown in the UI is metadata, not a deploy pin.

**No cascade action needed.** Updating the version displayed in the gallery happens when the API's data source is updated — outside the cascade's scope.

## Section 5 — DB-stored PipelineInstance specs (out of scope per ticket)

PipelineInstance CRs created at runtime by `openfilter-pipelines-controller` are constructed from records in the `plainsight-api` database, where users author them with hardcoded image tags. The ticket scopes this surface out (see "Out of scope" in PLAT-1052).

**Follow-up signal for the separate migration ticket:** a workable mechanism would be a controller-side mutation that resolves `<filter>:<tag>` against a "current release" lookup table at PipelineInstance reconciliation time, plus a one-off migration that rewrites existing DB rows. Neither is in this cascade's scope; flag here so the follow-up ticket can pick it up.

## Cross-cutting Phase 2 implications

1. **Registry-agnostic matching.** The cascade input is a *released filter name* (e.g. `filter-connector-gcs`), not a fully-qualified image URL. The bumper must walk pins by repo basename, ignoring the registry host (`plainsightai/…`, `containers.openfilter.io/plainsightai/…`, `us-west1-docker.pkg.dev/plainsightai-{prod,dev}/oci/…`).

2. **Tag prefix preservation.** Pin tags use mixed prefixes — `v0.1.10`, `0.1.10`, `0.2.0-dev`, `1.4.18`. The cascade should preserve the existing tag's `v` prefix presence and the existing tag's pre-release suffix policy when rewriting (a pin at `0.2.0-dev` should bump to the next dev tag, not jump to a prod tag).

3. **Skip-list for non-cascade pins:**
   - any tag literally `:latest` (intent: track tip)
   - any tag of form `:local` or `:<repo>-local` (developer fixture)
   - any image whose `image:` line carries a flux `$imagepolicy` trailing comment

4. **Matrix shape.** The cascade fans out per-consumer (`strategy.matrix.consumer`), not per pin site — each shard's bump strategy script does its own intra-repo scan. The consumer set is a hardcoded matrix in `cascade-pipeline-bumps.yaml` (one live entry today: `openfilter-pipelines-controller`); a per-shard resolve-check fails the shard loudly if an entry doesn't resolve, so a typo can't silently 404 on clone as `eval-demo-pipelines` did.

5. **Fleet-deduplicated second-level Slack alert.** This cascade fires once per filter release, so a multi-filter openfilter wave produces N independent runs in N filter-repo Actions contexts. Concurrency groups are per-repo and cannot coalesce them, so a naive per-run notify multiplies N× (the eval-demo phantom made this unmissable: 8 filters × 1 phantom shard = 8 pages per release). The notify job dedups via a cross-repo claim lock: it hashes the failure identity `(consumer, failure_class, UTC hour)` — filter name/version excluded, since that's the collapsed dimension — and atomically creates `refs/notify-claims/<hour>/<hash>` in `gh-actions-public` (git ref creation is a compare-and-swap: 201 wins, 422 means a sibling already claimed it). Exactly one run posts; the rest skip. Claim failure with no existing ref fails open (posts) so an alert is never lost to a flaky lock. Stale locks are aged out hourly by `gc-notify-claims.yaml`. Wave-level alerting for the *first* level still lives independently at `openfilter/.github/workflows/cascade-on-tag.yaml`.

6. **`open-mechanical-pr` branch_prefix.** Use `bump-filter-<name>-` to keep the supersede-stale logic scoped per released filter — so a faceblur release doesn't close a still-open frame-dedup bump PR.

## Open questions to resolve before Phase 2 ships

1. **GAR mirror sync confirmation.** Does anything publish to `us-west1-docker.pkg.dev/plainsightai-prod/oci/<filter>` automatically on a filter release? If not, jester-pipelines bump PRs will rewrite to non-existent tags. Either confirm a mirror exists or scope jester-pipelines out until one does.

2. **`filter-connector-gcs` release source.** Its versioning (`1.4.x`) doesn't match the SDK-cascade tag line. Does it use `filter-release.yaml` at all, or a different publisher? Phase 2 needs to know whether a release on this filter will actually fire the cascade trigger.

3. **`workflow_call` vs `release.published` trigger.** Ticket text describes the trigger as "`release.published` in each filter-* repo" — that's a *consumer* trigger model. First-level cascade triggers on `push: tags: 'v*'` on the *upstream* (openfilter). The two are equivalent in steady state, but `release.published` requires every filter-* repo to call back into a reusable workflow here; `push: tags` keeps the trigger inside each repo. Confirm which model before writing the workflow file.
