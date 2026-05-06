#!/usr/bin/env bash
# Download artifacts from Synthesus GitHub Releases
# Usage: ./download_artifacts.sh [tag]
#   tag  - specific release tag (default: latest)

set -e

REPO="Str8biddness/synthesus"
TAG="${1:-latest}"
ARTIFACTS_DIR="artifacts"

mkdir -p "$ARTIFACTS_DIR"

if [ "$TAG" = "latest" ]; then
  TAG=$(gh release list --repo "$REPO" --limit 1 --json tagName --jq '.[0].tagName')
  echo "Latest release: $TAG"
fi

cd "$ARTIFACTS_DIR"
gh release download "$TAG" --repo "$REPO" --pattern "faiss.index" --dir . 2>/dev/null || echo "faiss.index not found in release"
gh release download "$TAG" --repo "$REPO" --pattern "faiss_metadata.json" --dir . 2>/dev/null || echo "faiss_metadata.json not found in release"
cd ..

echo "Download complete."
ls -lh "$ARTIFACTS_DIR/"*.index "$ARTIFACTS_DIR/"*metadata* 2>/dev/null || echo "No artifacts downloaded"