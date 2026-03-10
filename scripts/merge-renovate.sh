#!/usr/bin/env bash
set -euo pipefail

merged=0
max_retries=3
retry=0

echo "=== Merge Renovate PRs ==="
echo ""

while true; do
    pr=$(gh pr list --author "app/renovate" --state open \
        --json number,title,mergeStateStatus,mergeable \
        --jq '[.[] | select(.mergeable == "MERGEABLE" and .mergeStateStatus == "CLEAN")] | first | .number // empty')

    if [[ -z "$pr" ]]; then
        remaining=$(gh pr list --author "app/renovate" --state open --json number --jq 'length')
        if [[ "$remaining" -gt 0 && "$retry" -lt "$max_retries" ]]; then
            retry=$((retry + 1))
            echo "⏳ $remaining PR(s) en attente de rebase, retry $retry/$max_retries..."
            sleep 15
            continue
        fi
        break
    fi

    retry=0
    title=$(gh pr view "$pr" --json title --jq '.title')
    echo "✅ #$pr: $title"
    gh pr merge "$pr" --merge --delete-branch
    merged=$((merged + 1))
    sleep 5
done

echo ""
echo "Résultat: $merged PR(s) mergée(s)"

remaining=$(gh pr list --author "app/renovate" --state open --json number --jq 'length')
if [[ "$remaining" -gt 0 ]]; then
    echo "⚠️  $remaining PR(s) restante(s) (conflits ou en attente de rebase Renovate)"
fi
