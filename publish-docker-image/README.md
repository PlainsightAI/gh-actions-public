# Publish Docker Image to GAR

Builds and publishes a Docker image to Google Artifact Registry (GAR). This action uses `make build-image` and `make publish-image`, and supports overriding the image path and version.

## Inputs

| Name         | Description                                                                 | Required | Default       |
|--------------|-----------------------------------------------------------------------------|----------|---------------|
| `version`    | Override the version in the `VERSION` file                                  | ❌        | `""`          |
| `image`      | Override the default Docker image path (e.g., `gcr.io/...`)                 | ❌        | `""`          |
| `environment`| Environment for GCP Workload Identity (`production`, `staging`, `development`) | ❌    | `"production"`|
| `attest_tlog`| Upload the SBOM attestation to the public Rekor transparency log. `'false'` skips the public log for images whose reference/SBOM must not be recorded publicly (keyless signing is unaffected). | ❌ | `"true"` |

## Prerequisites

Your `Makefile` must support:

```makefile
build-image:
	# build your image using IMAGE and VERSION

publish-image:
	# push your image to GAR using IMAGE and VERSION
```

## SBOM attestation

After the push, the action attaches a signed SPDX SBOM to the image as a keyless cosign
attestation (via the job's GitHub OIDC token — no long-lived key), so a scanner can re-check
the released image from its SBOM without pulling it.

It is **opt-in and non-breaking** — it no-ops with a warning unless the caller enables it:

1. Grant the job `permissions: id-token: write` (keyless cosign needs the OIDC token).
2. Expose the pushed image reference(s) via a `print-image-refs` make target (newline-separated,
   one line per image — best for repos that push more than one), or set `IMAGE` and `VERSION`
   in the job environment (`IMAGE:VERSION` is then attested):

   ```makefile
   print-image-refs:
   	@echo $(IMAGE):$(VERSION)
   ```

The action **assumes single-platform images** — it wraps `make publish-image` and does not know
the built platforms, so a multi-arch image would have only one architecture cataloged.

## Usage

```yaml
name: Publish Docker Image

on:
  push:
    tags:
      - 'v*.*.*'

jobs:
  publish-docker:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Publish Docker Image to GAR
        uses: PlainsightAI/gh-actions-public/publish-docker-image@main
        with:
          version: "v1.2.3"
          environment: "production"
```

### Override the image path (optional)

```yaml
      - name: Publish custom image
        uses: PlainsightAI/gh-actions-public/publish-docker-image@main
        with:
          image: us-west1-docker.pkg.dev/my-project/custom/image-name
          version: "v1.2.3"
```