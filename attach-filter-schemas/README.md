# 📎 Attach Filter Schemas

Composite GitHub Action that emits an OpenFilter filter's JSON Schema(s) and attaches them as OCI 1.1 referrer artifacts on the pushed image manifest. This is the registry-agnostic core of [FILTER-453 / FC-3 schema transport](https://plainsight-ai.atlassian.net/browse/FILTER-453).

Lives in `gh-actions-public` so both public release paths (`filter-release.yaml`, Docker Hub) and private release paths (`gh-actions/publish-gar-image`, GAR) can share one implementation. See [FILTER-444](https://plainsight-ai.atlassian.net/browse/FILTER-444) for the SDK side (`FilterOutputSchema`).

---

## 🔧 Usage

For a filter that has migrated to `FilterConfigBase` (and optionally `FilterOutputSchema`), call this composite *after* the build + push step in your job:

```yaml
jobs:
  publish-docker:
    runs-on: ubuntu-latest
    steps:
      - name: Build and push Docker image
        uses: docker/build-push-action@v6
        with:
          push: true
          tags: ${{ inputs.docker_image }}:${{ steps.meta.outputs.version }}
          # …

      - name: Attach config + output schemas
        uses: PlainsightAI/gh-actions-public/attach-filter-schemas@main
        with:
          image: ${{ inputs.docker_image }}
          version: ${{ steps.meta.outputs.version }}
          schema_module: filter_sam3_detector.filter
```

For PR-time dry-run jobs that build (but do not push) the image:

```yaml
      - name: Build Docker image (no push)
        uses: docker/build-push-action@v6
        with:
          load: true
          push: false
          tags: localhost/filter:pr-${{ github.event.number }}

      - name: Emit schemas (dry-run; no attach)
        uses: PlainsightAI/gh-actions-public/attach-filter-schemas@main
        with:
          image: localhost/filter
          version: pr-${{ github.event.number }}
          dry_run: "true"
          schema_module: filter_sam3_detector.filter
```

When `schema_module` is empty the composite is a no-op — unmigrated filters can stay on the same release workflow without any opt-in.

## 📥 Inputs

| Input           | Required | Default   | Description |
|-----------------|----------|-----------|-------------|
| `image`         | yes      |           | Full image path including registry and repository, *without* a tag. Must already be locally available (single-platform `load: true` build) or pullable from the registry (multi-platform `push: true` build), since emit-schema executes via `docker run --entrypoint python "${image}:${version}"`. |
| `version`       | yes      |           | Image tag the schemas should attach to. Schemas are attached as OCI referrers with `subject: ${image}:${version}`. |
| `dry_run`       | no       | `'false'` | When `'true'`, schemas are emitted (to surface emission failures at PR time) but not attached. Useful for PR-time dry-run-publish jobs. |
| `schema_module` | no       | `''`      | Importable Python module path of the filter (e.g. `filter_sam3_detector.filter`). When set, emits the config schema (and, when declared, the output schema) via `python -m openfilter.cli emit-schema` inside the image, and attaches each as an OCI referrer. When unset, the composite is a no-op — back-compat for unmigrated filters. |
| `schema_class`  | no       | `''`      | Optional `ClassName` for emit-schema disambiguation when the module declares more than one matching `FilterConfigBase` / `FilterOutputSchema` subclass. Passed as the `module:Class` qualifier to `openfilter emit-schema`. Ignored when `schema_module` is empty. |

## 🧱 Artifact types

Up to two referrer artifacts are pushed alongside the image (config always; output only when the filter declares `FilterOutputSchema`):

| Artifact type | Meaning | Always present? |
|---|---|---|
| `application/vnd.openfilter.config-schema+json` | The filter's `FilterConfigBase` schema (operator-facing surface) | Yes — release fails if emit-schema does not produce one |
| `application/vnd.openfilter.output-schema+json` | The filter's `FilterOutputSchema` (`frame.data` declaration) | No — absent when the filter does not declare one |

Both are pushed via `oras attach` with `--artifact-type` set as above. The pushed image manifest itself is not mutated; the OCI 1.1 referrer pattern stores schema artifacts in the same registry repository with `subject` pointing to the image manifest digest.

## 🔎 Consumer-side retrieval

```bash
# List schemas attached to an image
oras discover \
  plainsightai/openfilter-sam3-detector:v1.2.3

# Pull a specific schema by artifact-type
oras discover \
  --artifact-type application/vnd.openfilter.config-schema+json \
  --format go-template='{{(index .manifests 0).digest}}' \
  plainsightai/openfilter-sam3-detector:v1.2.3

oras pull \
  plainsightai/openfilter-sam3-detector@sha256:<digest>
```

Docker Hub, GAR, and other OCI 1.1-compliant registries all support this — no registry-side configuration required beyond ordinary push permissions.

## ⚠️ Failure semantics

- **Config schema emit failure** is fatal — the filter declared `schema_module` but `emit-schema --kind config` crashed, indicating either a misconfiguration (wrong module path) or a regression. Job fails so the broken release does not ship.
- **Output schema emit failure** is non-fatal and downgraded to a `::notice::` annotation — filters that have migrated their config but not their output to the typed SDK are still supported. Output schema is attached only when emit succeeds.

This mirrors the `--kind config` / `--kind output` asymmetry built into `openfilter emit-schema` itself: config is the universal surface; output is opt-in.

## 🔁 Attach-after-push failure modes

`oras attach` runs *after* the image push, so the push and the referrer attach are not atomic. If config-emit succeeds, the image is pushed, then `oras attach` fails (network blip, registry auth race, transient registry error), the publish job fails — but the pushed image and any already-attached referrers remain in the registry. Retrying the same tag will overwrite the image; the orphaned referrer (if one was attached before the failure) stays until cleaned up manually.

This is a pre-existing limitation of the publish-then-attach approach, newly surfaced by schema attachment expanding the publish-job failure surface.
