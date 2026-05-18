# Filter-release → pipeline-manifest cascade — consumer surface

**Ticket:** [PLAT-1052](https://plainsight-ai.atlassian.net/browse/PLAT-1052) — Phase 1 deliverable.

This document enumerates the PR-walkable surfaces where filter image tags are pinned in production-bearing or production-adjacent repos. It is the input to the Phase 2 second-level cascade workflow: each row becomes (or feeds) one matrix shard, with its `(repo, path glob, pin pattern, bump strategy)` fully specified so the workflow does not have to discover them at runtime.

## TL;DR

| # | Repo | Path glob | Pin form | Bump strategy | In scope? |
|---|---|---|---|---|---|
| 1 | `PlainsightAI/jester-pipelines` | `deploy/**/base/deployment.yaml`, `deploy/**/overlays/*/patch.yaml` | `image: us-west1-docker.pkg.dev/plainsightai-prod/oci/<filter>:<tag>` (GAR) | YAML in-place rewrite of `<tag>`, scoped to images whose repo basename matches the released filter | **Yes** |
| 2 | `PlainsightAI/openfilter-pipelines-controller` | `demo/pipeline_*.yaml`, `config/samples/pipelines_*.yaml` | `image: plainsightai/openfilter-<name>:v<ver>` (DockerHub) and `ghcr.io/plainsightai/openfilter-<name>:latest` | YAML in-place rewrite of `<ver>` on DockerHub-pinned entries only; `:latest` entries skipped (intent is "track tip") | **Yes** (low-business-value but covers contract) |
| 3 | `PlainsightAI/eval-demo-pipelines` | `filters/*/docker-compose*.yaml`, `scripts/docker-compose.*.yaml` | mixed: bare image literal **and** `${VAR:-<default>}` env override with default | YAML/regex rewrite of the *default* in the `${VAR:-…}` form; bare literal rewritten directly | **Yes** |
| 4 | `PlainsightAI/openfilter-hub` | n/a — **investigated and rejected** | filter metadata fetched from `https://api.prod.plainsight.tech` at build time; no image tags pinned in the repo | n/a | **No** — listed in ticket as a candidate; confirmed not a cascade target |
| 5 | `plainsight-api` DB-stored PipelineInstance specs | n/a — **out of scope** | hardcoded image tags in DB rows authored by users | n/a | **No** — ticket explicitly scopes this out; follow-up needed |

## Section 1 — `jester-pipelines`

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

## Section 3 — `eval-demo-pipelines`

### What's there

Filter image pins across `filters/*/docker-compose*.yaml` and `scripts/docker-compose.*.yaml`. Three distinct pin shapes coexist:

```yaml
# Shape A — bare literal, DockerHub mirror
image: containers.openfilter.io/plainsightai/openfilter-video-in:v0.1.10
# Shape B — bare literal, GAR (prod and dev)
image: us-west1-docker.pkg.dev/plainsightai-prod/oci/filter-json-transform:0.1.0
image: us-west1-docker.pkg.dev/plainsightai-dev/oci/filter-sam3-detector:0.2.0-dev
# Shape C — env-var override with default
image: ${SAM3_IMAGE:-us-west1-docker.pkg.dev/plainsightai-prod/oci/filter-sam3-detector:0.1.2-dev}
```

`containers.openfilter.io` resolves to `gateway.scarf.sh` — Scarf is a registry analytics proxy that fronts DockerHub. From a release-tag perspective the Scarf URL and the DockerHub URL refer to the same image. The cascade should treat the two as equivalent when matching repo basenames.

Shape C is the most common in `scripts/`. The default inside `${VAR:-default}` is the cascade target; the surrounding `${VAR:-…}` machinery stays in place so local overrides keep working.

### Bump strategy

```text
in:  filters/*/docker-compose*.yaml, scripts/docker-compose.*.yaml
pin: shape A | shape B | shape C above
out:
  shape A:  image: <same-prefix>/<name>:<new>
  shape B:  image: <same-prefix>/<name>:<new>
  shape C:  image: ${<VAR>:-<same-prefix>/<name>:<new>}
skip: any image whose tag is `local` or a developer fixture (e.g. `filter-grounding-dino:local`)
skip: any image not matching the released filter's repo basename
```

Implementation hint: a single regex with three alternation arms is brittle. Prefer a two-pass approach — first identify the file's pin shape per line, then rewrite. `yq` is shape-agnostic only for shape A/B; shape C requires string-level surgery on the value because `yq` collapses the `${VAR:-…}` envelope.

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

4. **Matrix shape.** Three consumer repos × N pin sites. The cascade should fan out per-consumer (matching first-level cascade shape: `strategy.matrix.consumer`), not per pin site. Each shard's bump strategy script does its own intra-repo scan.

5. **`open-mechanical-pr` branch_prefix.** Use `bump-filter-<name>-` to keep the supersede-stale logic scoped per released filter — so a faceblur release doesn't close a still-open frame-dedup bump PR.

## Open questions to resolve before Phase 2 ships

1. **GAR mirror sync confirmation.** Does anything publish to `us-west1-docker.pkg.dev/plainsightai-prod/oci/<filter>` automatically on a filter release? If not, jester-pipelines bump PRs will rewrite to non-existent tags. Either confirm a mirror exists or scope jester-pipelines out until one does.

2. **`filter-connector-gcs` release source.** Its versioning (`1.4.x`) doesn't match the SDK-cascade tag line. Does it use `filter-release.yaml` at all, or a different publisher? Phase 2 needs to know whether a release on this filter will actually fire the cascade trigger.

3. **`workflow_call` vs `release.published` trigger.** Ticket text describes the trigger as "`release.published` in each filter-* repo" — that's a *consumer* trigger model. First-level cascade triggers on `push: tags: 'v*'` on the *upstream* (openfilter). The two are equivalent in steady state, but `release.published` requires every filter-* repo to call back into a reusable workflow here; `push: tags` keeps the trigger inside each repo. Confirm which model before writing the workflow file.
