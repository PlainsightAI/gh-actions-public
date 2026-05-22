# Deploy Environment Action

Deploys a service to a specified environment by downloading a policy applier tool, modifying deployment manifest files with the latest image tag, and committing/pushing the updates back to the repository.

## Inputs

| Name              | Description                                                                                  | Required | Default |
|-------------------|----------------------------------------------------------------------------------------------|----------|---------|
| `service-name`    | The name of the service to deploy (used as the policy name).                                 | ✅ Yes   | -       |
| `environment`     | The target deployment environment (e.g., `production`, `staging`, `development`).             | ✅ Yes   | -       |
| `manifests-path`  | The path to the directory containing Kubernetes/Kustomize/Helm manifests to be updated.     | ✅ Yes   | -       |
| `gh-bot-user-pat` | GitHub Personal Access Token (PAT) used by the bot to pull/push commits.                      | ✅ Yes   | -       |

## Behavior

This action automates the entire deployment modification and push cycle using the following flow:
1. **Shallow Checkout**: Checks out the repository using the provided `gh-bot-user-pat` token with `fetch-depth: 2` (see [Checkout & Rebase Behavior](#checkout--rebase-behavior) for details).
2. **Download Image Policy Applier**: Retrieves the `image-policy-applier` tool from `PlainsightAI/infrastructure-tooling`.
3. **Apply Image Policy**: Runs the policy applier tool to write the new image tag (retrieved via the `image-tag` Makefile target) into the manifests directory.
4. **Local Git Setup**: Configures Git user name and email locally (scoped to the repository) as `plainsight-bot` / `cloudinfra@plainsight.ai`.
5. **No-Op Guard**: Checks if any manifests were actually changed. If no files were modified, the action exits cleanly without producing an empty commit or failing.
6. **Rebase and Push Retries**: Commits the change and attempts to push. To avoid conflicts with concurrent deployments, it fetches, rebases using `-X theirs`, and retries up to 5 times with exponential backoff and randomized jitter to prevent thundering herd issues.

## Prerequisites

### 1. Required Makefile Target (`image-tag`)

The action invokes `make image-tag` to determine the latest image path and tag. The caller repository's `Makefile` must define this target and print the image identifier to standard output without any extra logs or decoration.

**Example `Makefile`:**
```makefile
VERSION ?= $(shell cat VERSION)
IMAGE ?= us-west1-docker.pkg.dev/my-project/my-service

image-tag:
	@echo "$(IMAGE):$(VERSION)"
```

> ⚠️ **Note on Makefile variables:** Ensure that `VERSION` is defined using lazy assignment (e.g. `VERSION ?= ...` or overridable with env vars) rather than immediate assignment (e.g. `VERSION := ...`). The deployment action sets `VERSION=${GITHUB_SHA}` in the environment, which must be allowed to override the Makefile's default value so the correct build-specific tag is outputted.

### 2. PAT Write Scope (`gh-bot-user-pat`)

Because GitHub Actions' default `GITHUB_TOKEN` may not trigger downstream workflows or might have restricted permissions, this action requires a Personal Access Token (PAT) passed via `gh-bot-user-pat`.
- The PAT must have **`contents: write`** permissions for the target repository to successfully push the manifest changes back to the `main` branch.

## Checkout & Rebase Behavior

### `fetch-depth: 2` Optimization
A shallow clone of depth `2` is used initially to minimize checkout duration, reduce disk IO, and minimize network overhead in large repositories.

### Robust Rebase & Deepen Loop
Since shallow checkouts only contain 2 commits, rebasing onto a busy `main` branch that has moved forward by more than 2 commits would normally fail due to a missing common merge ancestor.
To resolve this elegantly without sacrificing the performance of the initial checkout:
- The retry loop uses `git fetch --deepen=50 origin main` to incrementally fetch older history.
- The `--deepen` parameter is only invoked if the first push attempt fails due to concurrency, ensuring we only fetch more commits when a rebase is actually needed.
- If concurrent pushes collision occurs, the retry sleep uses a randomized jitter:
  `sleep $(( (RANDOM % 3) + attempt * 2 ))`
  This prevents multiple parallel runs from syncing up their retry attempts and colliding repeatedly.
