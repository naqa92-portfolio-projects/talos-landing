#!/usr/bin/env bash
set -euo pipefail

# Une PR n'est mergée que si son rollup de checks est complet et vert, et que son SHA de tête n'a
# pas bougé entre la lecture et le merge : mergeStateStatus vaut CLEAN tant qu'aucun check n'est
# encore enregistré (fenêtre qui suit un force-push de rebase Renovate), une PR rouge y passe.

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
final_workflow=""
# merge-renovate.conf (optionnel) : final_workflow="<fichier>" pour un repo dont un workflow
# tourne sur push main. Les merges portent alors [skip ci] et un seul build est lancé à la fin.
[[ -f "$script_dir/merge-renovate.conf" ]] && source "$script_dir/merge-renovate.conf"

merged=0
max_retries=10
retry=0
skip_list=""

# Première PR Renovate mergeable dont tous les checks sont terminés et verts : "<numéro> <sha>".
next_pr() {
    gh pr list --author "app/renovate" --state open \
        --json number,headRefOid,mergeable,isDraft,statusCheckRollup \
        --jq "
          def green: (.status == \"COMPLETED\"
                      and (.conclusion == \"SUCCESS\" or .conclusion == \"SKIPPED\" or .conclusion == \"NEUTRAL\"))
                     or (.state == \"SUCCESS\");
          [ .[]
            | . as \$pr
            | select(.mergeable == \"MERGEABLE\" and .isDraft == false)
            | select(([$skip_list] | index(\$pr.number)) | not)
            | select((.statusCheckRollup | length) > 0)
            | select([.statusCheckRollup[] | select(green | not)] | length == 0)
          ]
          | first
          | if . == null then empty else \"\(.number) \(.headRefOid)\" end"
}

# PR encore susceptibles de devenir vertes : mergeabilité ou checks pas encore tranchés.
pending_count() {
    gh pr list --author "app/renovate" --state open \
        --json number,mergeable,isDraft,statusCheckRollup \
        --jq '[ .[]
                | select(.isDraft == false and .mergeable != "CONFLICTING")
                | select(.mergeable == "UNKNOWN"
                         or (.statusCheckRollup | length) == 0
                         or ([.statusCheckRollup[] | select(.status != null and .status != "COMPLETED")] | length) > 0)
              ] | length'
}

echo "=== Merge Renovate PRs ==="
echo ""

while true; do
    line=$(next_pr)

    if [[ -n "$line" ]]; then
        read -r pr sha <<< "$line"
        retry=0
        title=$(gh pr view "$pr" --json title --jq '.title')

        merge_args=(--merge --delete-branch --match-head-commit "$sha")
        [[ -n "$final_workflow" ]] && merge_args+=(--subject "$title [skip ci]")

        if gh pr merge "$pr" "${merge_args[@]}"; then
            echo "✅ #$pr: $title"
            merged=$((merged + 1))
        else
            # SHA obsolète (rebase concurrent) ou merge refusé : on n'y revient pas ce run.
            echo "↩️  #$pr: merge refusé (la branche a bougé), laissée ouverte"
            skip_list="${skip_list:+$skip_list,}$pr"
        fi
        sleep 5
        continue
    fi

    waiting=$(pending_count)
    if [[ "$waiting" -gt 0 && "$retry" -lt "$max_retries" ]]; then
        retry=$((retry + 1))
        echo "⏳ $waiting PR(s) en attente (rebase ou checks en cours), retry $retry/$max_retries..."
        sleep 30
        continue
    fi
    break
done

echo ""
echo "Résultat: $merged PR(s) mergée(s)"

remaining=$(gh pr list --author "app/renovate" --state open --json number --jq 'length')
if [[ "$remaining" -gt 0 ]]; then
    echo "⚠️  $remaining PR(s) restante(s) :"
    gh pr list --author "app/renovate" --state open \
        --json number,title,mergeable,statusCheckRollup \
        --jq '.[] | "   #\(.number) [\(.mergeable)] \(.title)\n     checks KO: \([.statusCheckRollup[]? | select(.conclusion != "SUCCESS" and .conclusion != "SKIPPED" and .conclusion != "NEUTRAL" and .state != "SUCCESS") | "\(.name // .context)=\(.conclusion // .state // .status)"] | join(", "))"'
fi

if [[ "$merged" -gt 0 && -n "$final_workflow" ]]; then
    echo ""
    echo "🚀 Déclenchement du build final ($final_workflow)..."
    gh workflow run "$final_workflow" --ref main
    echo "✅ Build déclenché sur main"
fi
