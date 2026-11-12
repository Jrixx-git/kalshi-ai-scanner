#!/usr/bin/env bash
set -euo pipefail
branch=research/nba-team-development-evidence
parent=()
if git ls-remote --exit-code origin "refs/heads/$branch" > /dev/null; then
  # Repeated depth-one fetches can reject a tracking-ref update when shallow
  # grafts hide ancestry. FETCH_HEAD needs no local ref rewrite; the push below
  # still requires a real fast-forward on the server.
  git fetch --depth=1 origin "refs/heads/$branch"
  prior=$(git rev-parse FETCH_HEAD)
  git read-tree "$prior"
  parent=(-p "$prior")
else
  code=$?
  test "$code" -eq 2
  git read-tree --empty
fi
git config user.name github-actions[bot]
git config user.email 41898282+github-actions[bot]@users.noreply.github.com
git add -- .gitattributes team-development
if [ "${#parent[@]}" -ne 0 ] && [ -n "$(git diff --cached --name-only --diff-filter=MD "$prior" -- team-development)" ]; then
  echo 'Refusing replacement or deletion of durable evidence' >&2
  exit 1
fi
tree=$(git write-tree)
commit=$(printf 'Archive prospective development %s [skip ci]\n' "$GITHUB_RUN_ID" | git commit-tree "$tree" "${parent[@]}")
gh auth setup-git
git push origin "$commit:refs/heads/$branch"
test "$(git ls-remote origin "refs/heads/$branch" | cut -f1)" = "$commit"
