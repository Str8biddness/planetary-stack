#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synthesus_knowledge_cloud.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main(["validate-sources", *sys.argv[1:]]))
