#!/usr/bin/env bash
set -euo pipefail

components=(
    apps/synthesus
    knowledge/knowledge-cloud
    platform/planetary-os
    platform/synthesus-os
    research/synthetic-intelligence-network
)

printf 'MONOREPO %s\n' "$(git rev-parse --show-toplevel)"
printf 'BRANCH %s\n' "$(git branch --show-current)"
printf 'HEAD %s\n' "$(git rev-parse --short HEAD)"

for component in "${components[@]}"; do
    if [[ -d "$component" ]]; then
        tracked_files="$(git ls-files "$component" | wc -l)"
        printf 'PRESENT %s tracked_files=%s\n' "$component" "$tracked_files"
    else
        printf 'MISSING %s\n' "$component"
    fi
done

