#!/usr/bin/env bash
set -euo pipefail

target="synthesus.bin"
if [[ "${1:-}" == "--iso" ]]; then
    target="synthesus.iso"
fi

for command_name in as g++ make; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        printf 'Missing Planetary kernel build dependency: %s\n' \
            "$command_name" >&2
        exit 1
    fi
done

if [[ "$target" == "synthesus.iso" ]]; then
    for command_name in grub-mkrescue xorriso; do
        if ! command -v "$command_name" >/dev/null 2>&1; then
            printf 'Missing Planetary ISO build dependency: %s\n' \
                "$command_name" >&2
            exit 1
        fi
    done
fi

source_dir="platform/planetary-os/Synthesus_Kernel"
build_dir="$(mktemp -d)"
trap 'rm -rf -- "$build_dir"' EXIT

cp \
    "$source_dir/Makefile" \
    "$source_dir/boot.s" \
    "$source_dir/font8x8_basic.h" \
    "$source_dir/grub.cfg" \
    "$source_dir/kernel.cpp" \
    "$source_dir/linker.ld" \
    "$build_dir/"

make -C "$build_dir" "$target"
test -s "$build_dir/synthesus.bin"
if [[ "$target" == "synthesus.iso" ]]; then
    test -s "$build_dir/synthesus.iso"
fi

printf 'Planetary build target %s passed in isolated directory: %s\n' \
    "$target" "$build_dir"
