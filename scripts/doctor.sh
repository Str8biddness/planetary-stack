#!/usr/bin/env bash
set -uo pipefail

required_missing=0
optional_missing=0
python_bin="${PYTHON_BIN:-python3}"

check_required() {
    local command_name="$1"
    if command -v "$command_name" >/dev/null 2>&1; then
        printf 'PASS required command: %s\n' "$command_name"
    else
        printf 'FAIL required command: %s\n' "$command_name"
        required_missing=$((required_missing + 1))
    fi
}

check_optional() {
    local command_name="$1"
    if command -v "$command_name" >/dev/null 2>&1; then
        printf 'PASS optional command: %s\n' "$command_name"
    else
        printf 'DEGRADED optional command: %s\n' "$command_name"
        optional_missing=$((optional_missing + 1))
    fi
}

check_path() {
    local path="$1"
    if [[ -e "$path" ]]; then
        printf 'PASS component path: %s\n' "$path"
    else
        printf 'FAIL component path: %s\n' "$path"
        required_missing=$((required_missing + 1))
    fi
}

check_required git
if command -v "$python_bin" >/dev/null 2>&1; then
    printf 'PASS required Python: %s\n' "$python_bin"
else
    printf 'FAIL required Python: %s\n' "$python_bin"
    required_missing=$((required_missing + 1))
fi
check_required make
check_required g++
check_optional git-lfs
check_optional node
check_optional bun
check_optional cmake
check_optional qemu-system-i386
check_optional grub-mkrescue
check_optional xorriso
check_optional ollama
check_optional nvidia-smi

check_path apps/synthesus
check_path knowledge/knowledge-cloud
check_path platform/planetary-os
check_path platform/synthesus-os
check_path research/synthetic-intelligence-network

if command -v git-lfs >/dev/null 2>&1; then
    lfs_listing="$(
        git lfs ls-files --include='knowledge/knowledge-cloud/**' 2>/dev/null
    )"
    if grep -q ' - ' <<<"$lfs_listing"; then
        printf 'DEGRADED Knowledge Cloud LFS objects are not fully hydrated\n'
        optional_missing=$((optional_missing + 1))
    elif grep -q ' \* ' <<<"$lfs_listing"; then
        printf 'PASS Knowledge Cloud LFS objects are hydrated\n'
    else
        printf 'DEGRADED Knowledge Cloud LFS tracking state is unavailable\n'
        optional_missing=$((optional_missing + 1))
    fi
else
    printf 'DEGRADED Knowledge Cloud LFS hydration cannot be inspected\n'
fi

printf 'SUMMARY required_missing=%d optional_missing=%d\n' \
    "$required_missing" "$optional_missing"

if (( required_missing > 0 )); then
    exit 1
fi
