#!/usr/bin/env sh
set -eu

if ! command -v zenity >/dev/null 2>&1; then
  printf 'zenity is required for graphical sudo authorization\n' >&2
  exit 1
fi

exec zenity \
  --password \
  --title="Synthesus Agentic Elevation" \
  --text="Authorize elevated development commands for this Synthesus session."
