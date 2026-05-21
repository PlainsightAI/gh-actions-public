# Publish Docker Image to GAR

Builds and publishes a Docker image to Google Artifact Registry (GAR). This action uses `make build-image` and `make publish-image`, and supports overriding the image path and version.

## Inputs

| Name         | Description                                                                 | Required | Default       |
|--------------|-----------------------------------------------------------------------------|----------|---------------|
| `version`    | Override the version in the `VERSION` file                                  | ❌        | `""`          |
| `image`      | Override the default Docker image path (e.g., `gcr.io/...`)                 | ❌        | `""`          |
| `environment`| Environment for GCP Workload Identity (`production`, `staging`, `development`) | ❌    | `"production"`|

## Prerequisites

Your `Makefile` must support:

```makefile
build-image:
	# build your image using IMAGE and VERSION

publish-image:
	# push your image to GAR using IMAGE and VERSION
```

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
        uses: PlainsightAI/gh-actions/publish-docker-image@main
        with:
          version: "v1.2.3"
          environment: "production"
```

### Override the image path (optional)

```yaml
      - name: Publish custom image
        uses: PlainsightAI/gh-actions/publish-docker-image@main
        with:
          image: us-west1-docker.pkg.dev/my-project/custom/image-name
          version: "v1.2.3"
```