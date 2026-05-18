# Cascade Pipeline Bumps — Prepare Bump

Composite action that stages a consumer-repo clone for a filter-image bump PR. Clones the consumer, runs the in-repo `bump-strategy.sh` rewriter against the clone, and emits the inputs `open-mechanical-pr` needs to push the branch and open the PR.

The split (this action does clone+bump, `open-mechanical-pr` does push+PR+auto-merge) mirrors the openfilter cascade pattern (`scripts/cascade/bump-and-pr.sh` + `open-mechanical-pr@main`) — PR mechanics are shared across both cascades; bump strategy is scoped per cascade.

PLAT-1052: <https://plainsight-ai.atlassian.net/browse/PLAT-1052>.

---

## What the rewriter does

Reads tracked `*.yaml` / `*.yml` files in the consumer clone via `git ls-files`. For each line matching `image: <…>/<filter_name>:<tag>` (with optional `${VAR:-…}` envelope or quoting), rewrites the entire image coordinate to `new_image_coord`. **Registry is part of the rewrite, not preserved** — a stale GAR pin of a filter that now releases to DockerHub becomes a DockerHub pin.

Skip rules (encoded in the awk match):

| Skip | Why |
|---|---|
| `:latest` | Deliberate intent — track tip. Rewriting would defeat the point. |
| `:local`, `:*-local` | Developer fixture; not a deploy target. |
| Any line with a `$imagepolicy` trailing comment | Flux reconciler manages it; a PR-time rewrite would race the next sync and either no-op or revert. |

Pins whose basename does not match `filter_name` are silently passed through. The match requires a literal `/<filter_name>:` substring, so `openfilter-faceblur` and `filter-faceblur` are unambiguously distinct.

---

## Inputs

| Input | Required | Description |
|---|---|---|
| `consumer_repo` | yes | Target consumer in `owner/name` (e.g. `PlainsightAI/jester-pipelines`). Cloned shallow at default branch. |
| `filter_name` | yes | Repo basename of the released filter (e.g. `filter-faceblur`). Drives the match. |
| `new_image_coord` | yes | New authoritative coordinate in `<repo>:<tag>` form (e.g. `plainsightai/filter-faceblur:0.1.5`). Validated as shape-correct before any rewrite. |
| `version` | yes | Bare semver (e.g. `0.1.5`). Used in commit/PR text only. |
| `release_url` | yes | URL of the upstream release page; linked in the PR body. |
| `gh_token` | yes | plainsight-bot PAT. Must have read access to the consumer for the clone; the subsequent `open-mechanical-pr` call uses the same token for push + PR + auto-merge, so write access is also needed. |

---

## Outputs

| Output | Description |
|---|---|
| `has_changes` | `'true'` if at least one pin was rewritten, `'false'` for a no-op. |
| `clone_dir` | Path on the runner to the staged clone. Working tree carries the rewritten pins; pass to `open-mechanical-pr` as `working_directory`. |
| `commit_message` | Suggested commit message — feed to `open-mechanical-pr`. |
| `pr_title` | Suggested PR title — feed to `open-mechanical-pr`. |
| `pr_body` | Suggested PR body (markdown) — feed to `open-mechanical-pr`. |

---

## Typical caller shape

```yaml
- id: prep
  uses: PlainsightAI/gh-actions-public/cascade-pipeline-bumps@main
  with:
    consumer_repo: PlainsightAI/jester-pipelines
    filter_name: filter-faceblur
    new_image_coord: plainsightai/filter-faceblur:0.1.5
    version: 0.1.5
    release_url: https://github.com/PlainsightAI/filter-faceblur/releases/tag/v0.1.5
    gh_token: ${{ secrets.GH_BOT_USER_PAT }}

- if: steps.prep.outputs.has_changes == 'true'
  uses: PlainsightAI/gh-actions-public/open-mechanical-pr@main
  with:
    repo: PlainsightAI/jester-pipelines
    working_directory: ${{ steps.prep.outputs.clone_dir }}
    branch_prefix: bump-filter-faceblur-
    commit_message: ${{ steps.prep.outputs.commit_message }}
    pr_title: ${{ steps.prep.outputs.pr_title }}
    pr_body: ${{ steps.prep.outputs.pr_body }}
    gh_token: ${{ secrets.GH_BOT_USER_PAT }}
```

The full orchestration (consumer matrix, dry-run, single-consumer, Slack-on-failure) lives in the reusable workflow `.github/workflows/cascade-pipeline-bumps.yaml`.
