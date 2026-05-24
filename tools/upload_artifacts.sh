#!/usr/bin/env bash
# Upload faiss.index and metadata to a new GitHub Release
# Usage: ./upload_artifacts.sh [tag]
#   tag  - release tag (default: release-YYYYMMDD-HHMMSS)

set -e

REPO="Str8biddness/synthesus"
ARTIFACTS_DIR="artifacts"

if [ -z "$1" ]; then
  TAG="release-$(date +%Y%m%d-%H%M%S)"
else
  TAG="$1"
fi

mkdir -p "$ARTIFACTS_DIR"

# Ensure required artifacts exist
if [ ! -f "$ARTIFACTS_DIR/faiss.index" ]; then
  echo "ERROR: $ARTIFACTS_DIR/faiss.index not found"
  exit 1
fi

echo "Creating release: $TAG"
gh release create "$TAG" --repo "$REPO" --title "$TAG" --generate-changelog

echo "Uploading artifacts..."
gh release upload "$TAG" "$ARTIFACTS_DIR/faiss.index" --repo "$REPO" --clobber
gh release upload "$TAG" "$ARTIFACTS_DIR/faiss_metadata.json" --repo "$REPO" --clobber 2>/dev/null || true

echo "Release $TAG created and artifacts uploaded."