#!/usr/bin/env bash
# bump-strategy.sh — Rewrite every pin of FILTER_NAME in the current
# working directory to NEW_IMAGE_COORD, registry-agnostic. Run from the
# root of a consumer repo's working tree; uses `git ls-files` so only
# tracked YAML is touched (avoids stomping on local-only experiments).
#
# Match shape (anchored on the trailing repo basename):
#   image: <any-registry>/<any-path>/<FILTER_NAME>:<any-tag>
#   image: ${VAR:-<any-registry>/<any-path>/<FILTER_NAME>:<any-tag>}
#   image: "<…/<FILTER_NAME>:tag>"   (single or double quoted)
#
# Skipped:
#   * tags `:latest`, `:local`, or `:*-local` (track-tip / dev fixture)
#   * lines carrying a flux `$imagepolicy` trailing comment
#     (reconciler-managed; cascade rewrite would race the next sync)
#
# Required env: FILTER_NAME, NEW_IMAGE_COORD.
# PLAT-1052: https://plainsight-ai.atlassian.net/browse/PLAT-1052
set -euo pipefail

: "${FILTER_NAME:?FILTER_NAME must be set (e.g. filter-faceblur)}"
: "${NEW_IMAGE_COORD:?NEW_IMAGE_COORD must be set (e.g. plainsightai/filter-faceblur:0.1.5)}"

# Catch caller mistakes (passing just the tag, just the repo, or a
# digest) before silently producing malformed pins across consumers.
if ! [[ "${NEW_IMAGE_COORD}" =~ ^[^[:space:]@]+:[^[:space:]@]+$ ]]; then
  echo "ERROR: NEW_IMAGE_COORD='${NEW_IMAGE_COORD}' is not <repo>:<tag> shaped." >&2
  exit 1
fi

mapfile -t FILES < <(git ls-files '*.yaml' '*.yml' || true)

if [[ "${#FILES[@]}" -eq 0 ]]; then
  echo "bump-strategy: no tracked YAML files in $(pwd); nothing to rewrite." >&2
  exit 0
fi

CHANGED_TOTAL=0
SKIPPED_TOTAL=0

# Single awk pass per file; emits the rewritten file to stdout, with
# counters to stderr that the wrapping bash loop sums up. Keeping the
# match + skip logic in one awk block (rather than splitting between
# grep prefilter + sed apply) means the printed diagnostic and the
# actual edit are guaranteed to agree.
for f in "${FILES[@]}"; do
  awk -v filter_name="${FILTER_NAME}" -v new_coord="${NEW_IMAGE_COORD}" '
    BEGIN {
      # Coordinate match: <segment>/<filter_name>:<tag>. The leading
      # segment matches the final path component of any registry/path
      # combination (e.g. `plainsightai`, `oci`, or `plainsightai/oci`
      # — the / chain is consumed greedily by the earlier line text).
      # Tag forbids whitespace, quotes, brace, dollar — terminators
      # for the pin literal in any of the three shapes we accept.
      #
      # First char is restricted to alphanumeric (not `-` or `.`) so we
      # do not chew into the `:-` of a `${VAR:-default}` envelope and
      # rewrite the `:-` into a stray `:`. Smoke-tested against
      # eval-demo-pipelines/scripts/docker-compose.sam3.yaml.
      coord_re = "[A-Za-z0-9]([A-Za-z0-9._/-]*[A-Za-z0-9])?/" filter_name ":[A-Za-z0-9._-]+"
      # The outer line match also requires the line to be an `image:`
      # key (with optional opener: quote or ${VAR:-) so we never touch
      # an `image_name:` field, comment text, etc.
      line_re  = "^[[:space:]]*image:[[:space:]]+(\"|\47|\\$\\{[A-Za-z_][A-Za-z0-9_]*:-)?" coord_re
      changed = 0
      skipped = 0
    }
    {
      if ($0 ~ line_re) {
        if ($0 ~ /\$imagepolicy/)                                    { skipped++; print; next }
        if ($0 ~ /:latest([[:space:]"\47}]|$)/)                      { skipped++; print; next }
        if ($0 ~ /:([A-Za-z0-9_.-]*-)?local([[:space:]"\47}]|$)/)    { skipped++; print; next }
        # sub() replaces the first match of coord_re on the line; the
        # surrounding pin envelope (quotes, ${VAR:-…}) stays intact.
        sub(coord_re, new_coord)
        changed++
      }
      print
    }
    END {
      print "AWK_CHANGED=" changed > "/dev/stderr"
      print "AWK_SKIPPED=" skipped > "/dev/stderr"
    }
  ' "$f" > "${f}.cascade.tmp" 2> "${f}.cascade.stderr"

  AWK_CHANGED=$(awk -F= '/^AWK_CHANGED=/{print $2; exit}' "${f}.cascade.stderr")
  AWK_SKIPPED=$(awk -F= '/^AWK_SKIPPED=/{print $2; exit}' "${f}.cascade.stderr")
  CHANGED_TOTAL=$((CHANGED_TOTAL + ${AWK_CHANGED:-0}))
  SKIPPED_TOTAL=$((SKIPPED_TOTAL + ${AWK_SKIPPED:-0}))

  if [[ "${AWK_CHANGED:-0}" -gt 0 ]]; then
    mv "${f}.cascade.tmp" "$f"
    echo "  BUMP ${f} (+${AWK_CHANGED})" >&2
  else
    rm -f "${f}.cascade.tmp"
  fi
  [[ "${AWK_SKIPPED:-0}" -gt 0 ]] && echo "  SKIP ${f} (${AWK_SKIPPED}: :latest/:local/\$imagepolicy)" >&2
  rm -f "${f}.cascade.stderr"
done

echo "bump-strategy: ${CHANGED_TOTAL} pin(s) rewritten, ${SKIPPED_TOTAL} skipped." >&2
