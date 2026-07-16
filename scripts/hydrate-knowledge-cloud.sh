#!/usr/bin/env bash
set -euo pipefail

if ! command -v git-lfs >/dev/null 2>&1; then
    printf 'Git LFS is required to hydrate the Knowledge Cloud bundle.\n' >&2
    exit 1
fi

git lfs install --local
git lfs pull --include='knowledge/knowledge-cloud/**'
git lfs checkout knowledge/knowledge-cloud

printf 'Knowledge Cloud LFS assets are hydrated.\n'
