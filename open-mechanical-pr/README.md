# Open Mechanical PR

Composite action that mechanically opens a bot-authored pull request against a target consumer repo. Designed to be the shared mechanics layer for cross-repo bump cascades (e.g. openfilter → eligible consumers, gh-actions → eligible consumers).

Behavior:

1. Configure git identity to `plainsight-bot <cloudinfra@plainsight.ai>`.
2. If the working tree is clean, exit success without doing anything (idempotent re-runs).
3. List open PRs in the target repo whose head branch starts with `branch_prefix` and close them with a "Superseded by a fresh `${branch_prefix}` run." comment + branch deletion.
4. Create branch `${branch_prefix}${short_sha}`, commit staged changes with `commit_message`, push to origin (using `gh_token`).
5. Open the PR against `main` with `pr_title` / `pr_body`.
6. If `auto_merge` is `true` (default), call `gh pr merge --auto --${merge_method}` on the new PR. If auto-merge enablement fails (e.g. target branch has no protection rule), log a warning and continue — the PR remains open for manual merge.

Lifted from the supersede + push + create logic of `client-portal/.github/workflows/update-api-client.yaml`, factored once so any cascade workflow can share it.

---

## Inputs

| Input               | Required | Default   | Description |
|---------------------|----------|-----------|-------------|
| `repo`              | yes      | —         | Target consumer in `owner/name` form (e.g. `PlainsightAI/filter-sam3-detector`). |
| `branch_prefix`     | yes      | —         | Prefix for the bot PR head branch (e.g. `bump-openfilter-`, `bump-gh-actions-`). Used both to name the new branch and to identify stale predecessors to supersede. **Pick a prefix unique to the cascade** so unrelated bot PRs are not closed. |
| `commit_message`    | yes      | —         | Commit message for the staged changes. |
| `pr_title`          | yes      | —         | Pull request title. |
| `pr_body`           | yes      | —         | Pull request body (markdown). |
| `gh_token`          | yes      | —         | GitHub token (the plainsight-bot PAT) used for `git push`, `gh pr create`, supersede, and `gh pr merge --auto`. |
| `auto_merge`        | no       | `'true'`  | Set to `'false'` to skip `gh pr merge --auto`. |
| `merge_method`      | no       | `'squash'`| Merge method for native auto-merge: `squash` \| `merge` \| `rebase`. |
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

A snippet from the openfilter cascade workflow that fans out a bump to one consumer:

```yaml
# .github/workflows/cascade-on-tag.yaml in openfilter
name: Cascade openfilter bump
on:
  push:
    tags: ['v*']

jobs:
  cascade:
    runs-on: ubuntu-latest
    env:
      UPSTREAM_VERSION: ${{ github.ref_name }}
    steps:
      - uses: actions/checkout@v4

      - name: Discover eligible consumers
        id: discover
        env:
          GH_TOKEN: ${{ secrets.GH_BOT_USER_PAT }}
        run: ./scripts/cascade/discover.sh > /tmp/consumers.txt

      - name: Bump and PR each consumer
        env:
          GH_BOT_USER_PAT: ${{ secrets.GH_BOT_USER_PAT }}
          UPSTREAM_VERSION: ${{ env.UPSTREAM_VERSION }}
        run: |
          while read -r repo; do
            workdir="/tmp/consumers/${repo##*/}"
            git clone "https://x-access-token:${GH_BOT_USER_PAT}@github.com/${repo}" "$workdir"
            (cd "$workdir" && /github/workspace/scripts/cascade/bump-strategy.sh)
            echo "REPO=$repo WORKDIR=$workdir" >> "$GITHUB_ENV"
          done < /tmp/consumers.txt

      # Per-consumer step (typical pattern: matrix-fan-out, one job per repo)
      - name: Open mechanical bump PR
        uses: PlainsightAI/gh-actions-public/open-mechanical-pr@main
        with:
          repo: ${{ env.REPO }}
          working_directory: ${{ env.WORKDIR }}
          branch_prefix: bump-openfilter-
          commit_message: |
            chore(deps): bump openfilter to ${{ env.UPSTREAM_VERSION }}
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
```

In production the per-consumer `bump-strategy.sh` + `open-mechanical-pr` invocation is typically wrapped in a matrix-fan-out job so each consumer's PR opens in parallel; the snippet above flattens it to one block for readability.

---

## Related actions

- [`check-release-log`](../check-release-log/) — companion composite action used in CI to gate every PR on a `RELEASE.md` update. Cascade-opened PRs include the bump's changelog entry and so satisfy this check naturally.
