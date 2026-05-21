# Google Cloud Auth Action

Authenticates to Google Cloud using **Workload Identity Federation** based on the provided environment. Automatically sets up the correct service account and provider for `development`, `staging`, or `production`.

## Usage

```yaml
name: Authenticate GCP

on:
  push:
    branches:
      - main

jobs:
  authenticate-gcp:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Authenticate to Google Cloud
        uses: PlainsightAI/gh-actions/google-cloud-auth@main
        with:
          environment: development # or staging or production
```

## Inputs

| Name         | Description                                                   | Required | Default     |
|--------------|---------------------------------------------------------------|----------|-------------|
| `environment` | The environment to authenticate to (`development`, `staging`, or `production`) | ✅ Yes   | `production` |

## Behavior

This action:
- Validates the `environment` input.
- Dynamically selects the correct **Workload Identity Provider** and **Service Account** for the environment.
- Uses `google-github-actions/auth@v2` and `setup-gcloud@v2` to authenticate and configure `gcloud`.