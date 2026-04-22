# External Review Freshness

Dismisses APPROVED pull request reviews whenever an **untrusted** contributor
pushes new commits, while preserving approvals when the pusher is a trusted
repository collaborator.

## Usage

```yaml
# .github/workflows/dismiss-stale-approvals.yaml
name: Dismiss stale approvals on untrusted push

on:
  pull_request_target:
    types: [synchronize]

permissions:
  pull-requests: write
  contents: read

jobs:
  dismiss:
    runs-on: ubuntu-latest
    steps:
      - uses: PlainsightAI/gh-actions-public/external-review-freshness@main
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          # Start with dry-run on first rollout to validate behavior in logs.
          dry-run: "true"
```

## Inputs

| Name                | Required | Default                                                                                                           | Description                                                                                                      |
| ------------------- | -------- | ----------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `github-token`      | yes      | —                                                                                                                 | Token with `pull-requests: write` + repo `metadata: read`. `secrets.GITHUB_TOKEN` usually suffices.              |
| `dismissal-message` | no       | "Approving review dismissed because an untrusted contributor pushed new commits. A collaborator must re-review." | Message attached to each dismissal.                                                                              |
| `dry-run`           | no       | `"false"`                                                                                                         | When `"true"`, logs what would be dismissed without calling the dismissal API. Recommended for initial rollout.  |

## Notes

- **Why `pull_request_target`?** Workflows triggered by `pull_request` from a
  fork run with the fork's permissions and cannot dismiss reviews. The
  `pull_request_target` event runs with the base repository's permissions,
  which is exactly what we need here. Only the `synchronize` event type is
  relevant (new commits pushed).

- **Why collaborator permission, not org membership?** Outside collaborators
  with `write` access are trusted enough to push directly to the repo; their
  PRs should not have approvals dismissed on every push. Org membership is the
  wrong axis — it excludes trusted non-members and includes org members who
  only have `read` on this specific repo. The action consults
  `GET /repos/{owner}/{repo}/collaborators/{username}/permission` and treats
  `role_name ∈ {admin, maintain, write}` as trusted; everything else (including
  a 404, i.e. fork contributors with no collaborator entry) triggers dismissal.

- **Start with `dry-run: "true"`.** The logs will show exactly which reviews
  would be dismissed. Flip to `"false"` once you've validated behavior.

- **Relationship to the native branch-protection setting.** GitHub's built-in
  "Dismiss stale pull request approvals when new commits are pushed" branch
  rule dismisses approvals from *every* reviewer on *every* push. This action
  is complementary: it only dismisses when the push comes from an untrusted
  contributor, so trusted maintainer self-pushes don't invalidate fresh
  approvals. Use whichever matches your policy; they are not redundant.
