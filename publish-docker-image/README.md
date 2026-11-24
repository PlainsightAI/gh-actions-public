# Publish Docker Image to GAR

Builds and publishes a Docker image to Google Artifact Registry (GAR). This action uses `make build-image` and `make publish-image`, and supports overriding the image path and version.

## Inputs

| Name         | Description                                                                 | Required | Default       |
|--------------|-----------------------------------------------------------------------------|----------|---------------|
| `version`    | Override the version in the `VERSION` file                                  | ❌        | `""`          |
| `image`      | Override the default Docker image path (e.g., `gcr.io/...`)                 | ❌        | `""`          |
| `environment`| Environment for GCP Workload Identity (`production`, `staging`, `development`) | ❌    | `"production"`|
| `attest_tlog`| Upload the SBOM attestation to the public Rekor transparency log. Defaults to `'false'` because this action is GAR-only — every ref it attests is a private Artifact Registry coordinate that should not land in a public log; on `'false'` the attestation carries an RFC3161 signed timestamp instead so it stays verifiable. Set `'true'` only for a genuinely public image. | ❌ | `"false"` |
| `tag_latest` | Also tag `<image>:latest` alongside the versioned tag (mirrors `publish-gar-image`), so callers don't need their own `:latest` step. Created **registry-to-registry** with `docker buildx imagetools create` — no dependency on the image being in the local daemon (a `buildx --push` build never populates it) and multi-arch manifests are preserved. Needs a resolvable ref (`print-image-refs` target or `IMAGE`+`VERSION`), same as attestation. | ❌ | `"false"` |
| `disk_cleanup` | Reclaim disk on the runner **before** the build: delete the preinstalled .NET, Android SDK, GHC and CodeQL toolchains and prune local Docker images and build cache. Freed ~22 GB on an `ubuntu-latest` runner (free space on `/` went from ~15 GB to ~37 GB). Turn it on for an image that bakes large artifacts (model weights, CUDA wheels) and fails the build with "no space left on device". Leave it off if the job uses any of those toolchains after the publish, or needs a local image an earlier step built — see [Disk space](#disk-space). | ❌ | `"false"` |

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

**What gates it:** the pushed image reference must be resolvable — expose it via a
`print-image-refs` make target (newline-separated, one line per image — best for repos that
push more than one), or set `IMAGE` and `VERSION` in the job environment (`IMAGE:VERSION` is
then attested):

```makefile
print-image-refs:
	@echo $(IMAGE):$(VERSION)
```

Attestation also needs the job to hold `permissions: id-token: write` for keyless cosign — but
this action authenticates with Workload Identity Federation, which already requires it, so any
caller that works at all has it. In practice attestation runs for **every** caller that exposes
a ref; the id-token check is a safety net, not an opt-in switch. The attest steps are
`continue-on-error`, so a signing outage never fails the (already-pushed) publish.

The action **assumes single-platform images** — it wraps `make publish-image` and does not know
the built platforms, so a multi-arch image would have only one architecture cataloged.

### Verifying the attestation

The verify command depends on `attest_tlog`:

```bash
# attest_tlog=false (the default — RFC3161 signed timestamp, no Rekor entry): BOTH flags.
# --insecure-ignore-tlog skips the Rekor lookup for an entry that deliberately does not exist;
# --use-signed-timestamps supplies trusted time from the stamp so the short-lived Fulcio cert
# is proven valid at signing time. --use-signed-timestamps alone fails "signature not found in
# transparency log".
cosign verify-attestation --type spdxjson --insecure-ignore-tlog --use-signed-timestamps \
  --certificate-identity-regexp '<your signer identity>' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com <image-ref>

# attest_tlog=true (public image, Rekor entry): neither flag.
cosign verify-attestation --type spdxjson \
  --certificate-identity-regexp '<your signer identity>' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com <image-ref>
```

## Disk space

A GitHub-hosted runner starts with roughly 15 GB free on `/`. An image that bakes large
artifacts — model weights, CUDA wheels — exhausts that during `make build-image`, and the
job dies with `no space left on device`. The failure is easy to misread: the runner
sometimes hits the full filesystem while writing its own diagnostic log, so **no step is
marked failed** and the run looks like an infrastructure flake. It is not — a re-run
reproduces it, because the cause is the runner's free space, not the build.

Set `disk_cleanup: "true"` and the action deletes the preinstalled toolchains it never uses
and prunes local Docker state before building:

```yaml
      - name: Publish Docker Image to GAR
        uses: PlainsightAI/gh-actions-public/publish-docker-image@main
        with:
          disk_cleanup: "true"
```

It is **off by default** because it is destructive to the runner rather than to the build.
Leave it off when, in the same job:

- a later step uses .NET, the Android SDK, GHC or CodeQL — they are deleted; or
- a later step needs a local image, because `docker image prune --all` removes every image
  the daemon holds, including one an earlier step built with `load: true` for tests.

Neither applies to the push itself: the step runs before the build, so `make publish-image`
still finds the image it pushes, and SBOM attestation reads the image from the registry
(`syft registry:<ref>`), not from the local daemon.

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