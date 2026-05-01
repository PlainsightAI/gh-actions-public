# Open Mechanical PR

Composite action that mechanically opens a bot-authored pull request against a target consumer repo. Designed to be the shared mechanics layer for cross-repo bump cascades (e.g. openfilter → eligible consumers, gh-actions → eligible consumers).

Behavior:

1. Configure git identity to `plainsight-bot <cloudinfra@plainsight.ai>`.
2. If the working tree is clean, exit success without doing anything (idempotent re-runs).
3. List open PRs in the target repo whose head branch starts with `branch_prefix` and close them with a "Superseded by a fresh `${branch_prefix}` run." comment + branch deletion.
4. Create branch `${branch_prefix}${short_sha}-${github_run_id}`, commit working-tree changes (modifications and untracked files) with `commit_message`, push using a token-in-URL (no global git config mutation).
5. Open the PR against `base_branch` (default `main`) with `pr_title` / `pr_body`. If a PR for the same head branch already exists (e.g. on workflow re-run), reuse it instead of erroring.
6. If `auto_merge` is `true` (default), call `gh pr merge --auto --${merge_method}` on the new PR. If auto-merge enablement fails (e.g. target branch has no protection rule), log a warning and continue — the PR remains open for manual merge.

Lifted from the supersede + push + create logic of `client-portal/.github/workflows/update-api-client.yaml`, factored once so any cascade workflow can share it.

---

## Inputs

| Input               | Required | Default   | Description |
|---------------------|----------|-----------|-------------|
| `repo`              | yes      | —         | Target consumer in `owner/name` form (e.g. `PlainsightAI/filter-sam3-detector`). |
| `branch_prefix`     | yes      | —         | Prefix for the bot PR head branch (e.g. `bump-openfilter-`, `bump-gh-actions-`). Used both to name the new branch (`${branch_prefix}${short_sha}-${github_run_id}`) and to identify stale predecessors to supersede. **Pick a prefix unique to the cascade** so unrelated bot PRs are not closed. |
| `commit_message`    | yes      | —         | Commit message for the staged changes. |
| `pr_title`          | yes      | —         | Pull request title. |
| `pr_body`           | yes      | —         | Pull request body (markdown). |
| `gh_token`          | yes      | —         | GitHub token (the plainsight-bot PAT) used for `git push`, `gh pr create`, `gh pr merge --auto`, **and listing/closing prior PRs in the supersede step**. Must have `repo` scope (or equivalent fine-grained `Pull requests: read+write` and `Contents: read+write`) on every repo this action targets. |
| `auto_merge`        | no       | `'true'`  | Set to `'false'` to skip `gh pr merge --auto`. |
| `merge_method`      | no       | `'squash'`| Merge method for native auto-merge: `squash` \| `merge` \| `rebase`. Validated unconditionally (in the precheck step) so a typo fails fast even when `auto_merge: 'false'`. |
| `base_branch`       | no       | `'main'`  | Base branch the PR targets and the supersede step queries against. Defaults to `main`. |
| `working_directory` | no       | `'.'`     | Path on the runner to the cloned consumer repo. |

---

## Outputs

| Output   | Description |
|----------|-------------|
| `pr_url` | URL of the created pull request. Empty if the working tree was clean (no-op). |

---

## Idempotency

Re-running the action with no working-tree changes is a no-op: step 2 short-circuits all subsequent steps. Concretely, this means a cascade can safely retry on transient failures, and the upstream's bump strategy can converge to the same state across multiple runs (e.g. when the consumer's pin already satisfies the new version) without producing empty PRs.

## Auto-merge failure mode

`gh pr merge --auto` requires native auto-merge to be enabled on the repo, which in turn requires branch protection. The action degrades gracefully:

- Repo with required status checks → merges as soon as checks pass.
- Repo with required codeowner reviews → waits for review, then merges.
- **Repo with no branch protection** → `gh pr merge --auto` errors. The action logs a warning and continues; the PR is left open for a human to merge manually. The cascade does **not** fail.

This is intentional: failing the cascade over a missing branch protection rule would block bumps from landing in repos that haven't completed the protection sweep yet. The calling workflow's `if: failure()` Slack step (or equivalent) is the right place to flag systemic problems.

To skip auto-merge entirely (e.g. respect a consumer's `.github/no-cascade-automerge` marker), pass `auto_merge: 'false'`.

## Supersede semantics

The action closes **all** open PRs in `${repo}` whose head branch starts with `${branch_prefix}`, deleting the remote branch and posting a supersede comment. This is the "latest wins" pattern from `update-api-client.yaml` — bumps coalesce rather than queue.

The match is a literal `startswith` against the head branch name. Choose a `branch_prefix` that is unique to your cascade. If two cascades share a prefix, they will close each other's PRs.

---

## Example: openfilter cascade caller

A two-job pattern from the openfilter cascade workflow: a `discover` job emits the list of eligible consumers as a JSON array, and a `cascade` job fans out one matrix shard per consumer. Each shard clones, applies the bump strategy, and invokes `open-mechanical-pr` independently — one PR per repo, opened in parallel.

```yaml
# .github/workflows/cascade-on-tag.yaml in openfilter
name: Cascade openfilter bump
on:
  push:
    tags: ['v*']

jobs:
  discover:
    runs-on: ubuntu-latest
    outputs:
      consumers: ${{ steps.list.outputs.consumers }}
    steps:
      - uses: actions/checkout@v4
      - id: list
        env:
          GH_TOKEN: ${{ secrets.GH_BOT_USER_PAT }}
        run: |
          # Emit a JSON array of repo names, one per matrix shard.
          consumers=$(./scripts/cascade/discover.sh | jq -Rsn '[inputs | select(length>0)]')
          echo "consumers=$consumers" >> "$GITHUB_OUTPUT"

  cascade:
    needs: discover
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        repo: ${{ fromJSON(needs.discover.outputs.consumers) }}
    env:
      UPSTREAM_VERSION: ${{ github.ref_name }}
    steps:
      - name: Clone consumer
        env:
          GH_BOT_USER_PAT: ${{ secrets.GH_BOT_USER_PAT }}
        run: |
          git clone "https://x-access-token:${GH_BOT_USER_PAT}@github.com/${{ matrix.repo }}" /tmp/consumer

      - name: Apply bump strategy
        working-directory: /tmp/consumer
        run: <consumer-specific bump command, e.g. ./scripts/cascade/bump-strategy.sh>

      - name: Open mechanical bump PR
        uses: PlainsightAI/gh-actions-public/open-mechanical-pr@main
        with:
          repo: ${{ matrix.repo }}
          working_directory: /tmp/consumer
          branch_prefix: bump-openfilter-
          commit_message: "chore(deps): bump openfilter to ${{ env.UPSTREAM_VERSION }}"
          pr_title: "chore(deps): bump openfilter to ${{ env.UPSTREAM_VERSION }}"
          pr_body: |
            Mechanical bump of `openfilter` to `${{ env.UPSTREAM_VERSION }}`,
            triggered by the openfilter cascade-on-tag workflow.

            Auto-merges once required checks pass. See branch protection on
            this repo's `main` for the exact gate.
          gh_token: ${{ secrets.GH_BOT_USER_PAT }}
          # auto_merge defaults to 'true'; pass 'false' to honor a
          # .github/no-cascade-automerge marker file in the consumer.
          # merge_method defaults to 'squash'.
          # base_branch defaults to 'main'.
```

`fail-fast: false` matters here: one consumer's bump strategy failing (e.g. a merge conflict in the lockfile) shouldn't cancel the other shards' in-flight PRs. The calling workflow's `if: failure()` Slack/notification step (or equivalent) is the right place to flag systemic problems.

---

## Related actions

- [`check-release-log`](../check-release-log/) — companion composite action used in CI to gate every PR on a `RELEASE.md` update. Cascade-opened PRs include the bump's changelog entry and so satisfy this check naturally.
