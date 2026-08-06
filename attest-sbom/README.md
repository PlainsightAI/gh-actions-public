# Attest SBOM

Attach a keyless cosign **SBOM attestation** (SPDX, one per platform) to an image that has
**already been built and pushed**. Unlike [`publish-docker-image`](../publish-docker-image)
(which builds + pushes to GAR and attests in one step), this only *signs an existing ref*, so
it composes with any build pipeline — including a native per-arch `build-and-push` + `docker
buildx imagetools create` merge that pushes a multi-arch manifest to Docker Hub.

Use it when you want to keep your existing (e.g. native multi-arch) build but add the same
signed-SBOM supply-chain guarantee the shared publish paths provide, so the released image is
verifiable and shows up scanned (not `no_sbom`) in `grype-release-metric`.

## Requirements (on the calling job)

- `permissions: id-token: write` — keyless signing via GitHub OIDC (no long-lived key).
- Already authenticated to the image's registry (the same `docker login` used to push), so
  syft can read the image and cosign can push the `.att`.

## Inputs

| Name | Description | Default |
|------|-------------|---------|
| `image` | Full ref of the already-pushed image (e.g. `plainsightai/foo:1.2.3`). For multi-arch, pass the tag — the attestation attaches to the manifest-list digest. | (required) |
| `platforms` | Comma-separated platforms to catalog; one SBOM + attestation per platform. | `linux/amd64,linux/arm64` |
| `tlog` | Upload to the public Rekor log. `'true'` for PUBLIC images (Docker Hub); `'false'` for PRIVATE (attaches an RFC3161 timestamp instead). | `'true'` |
| `cosign-version` / `syft-version` | Pinned tool versions. | `v2.5.2` / `v1.50.0` |

## Usage — after a multi-arch merge (Docker Hub)

```yaml
merge:
  runs-on: ubuntu-latest
  needs: build-and-push
  permissions:
    contents: read
    id-token: write        # keyless cosign
  steps:
    # ... assemble the manifest with `docker buildx imagetools create -t $IMAGE:$TAG ...`
    #     while logged in to Docker Hub ...
    - name: Attest SBOM
      uses: PlainsightAI/gh-actions-public/attest-sbom@main
      continue-on-error: true   # image is already live; a signing blip shouldn't fail the release
      with:
        image: plainsightai/my-service:${{ steps.meta.outputs.tag }}
        platforms: linux/amd64,linux/arm64
        # tlog defaults to true (public Docker Hub)
```

## Verifying

```bash
# tlog=true (public Docker Hub, Rekor entry): no extra flags.
cosign verify-attestation --type spdxjson \
  --certificate-identity-regexp '^https://github\.com/PlainsightAI/<repo>/\.github/workflows/<wf>@refs/(heads/main|tags/.+)$' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com <image-ref>

# tlog=false (private, RFC3161 timestamp): BOTH flags.
cosign verify-attestation --type spdxjson --insecure-ignore-tlog --use-signed-timestamps \
  --certificate-identity-regexp '...' --certificate-oidc-issuer https://token.actions.githubusercontent.com <image-ref>
```

A multi-arch image carries one SPDX predicate per platform; `grype-release-metric` keeps every
predicate and scans each.
