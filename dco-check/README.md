# DCO Check

Verifies that every commit in a pull request carries a
`Signed-off-by: Name <email>` trailer per the
[Developer Certificate of Origin](https://developercertificate.org/).

## Usage

```yaml
# .github/workflows/dco.yaml
name: DCO

on:
  pull_request:

jobs:
  dco:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with:
          # Full history is required to walk origin/<base>..HEAD.
          fetch-depth: 0
          # Check out the PR head explicitly so the commits under review are
          # what we inspect (avoids the default merge-ref used by pull_request).
          ref: ${{ github.event.pull_request.head.sha }}

      - uses: PlainsightAI/gh-actions-public/dco-check@main
```

## Inputs

None.

## Remediation

If the check fails, amend the offending commit(s) and force-push:

```bash
# Sign off the most recent commit
git commit --amend --signoff

# Or sign off the last N commits in bulk
git rebase HEAD~<N> --signoff

git push --force-with-lease
```

`--signoff` adds a line of the form `Signed-off-by: Your Name <you@example.com>`
using your git `user.name` and `user.email`. By adding it you are certifying the
[Developer Certificate of Origin](https://developercertificate.org/).
