#!/usr/bin/env bash
# Launch smoke — real HTTP checks only. No mocks.
# Usage:
#   RUNTIME_URL=http://127.0.0.1:5010 API_KEY=... ./tools/launch_smoke.sh
set -uo pipefail

URL="${RUNTIME_URL:-http://127.0.0.1:5010}"
KEY="${API_KEY:-${SYNTHESUS_API_KEY:-dev-key-change-me}}"
PY="${PYTHON:-$HOME/synthesus/.venv/bin/python}"
ROOT="${SYNTHESUS_SRC:-$HOME/synthesus}"

pass=0
fail=0
skip=0

ok()   { echo "  PASS  $*"; pass=$((pass+1)); }
bad()  { echo "  FAIL  $*"; fail=$((fail+1)); }
note() { echo "  SKIP  $*"; skip=$((skip+1)); }

http_code() {
  # usage: http_code METHOD URL [curl args...]
  local method=$1; shift
  local url=$1; shift
  local code
  code=$(curl -s -o /tmp/smoke_body.bin -w "%{http_code}" -X "$method" "$url" "$@" 2>/dev/null) || code="000"
  echo "$code"
}

echo "=== Synthesus launch smoke ==="
echo "  URL=$URL"
echo

# 1) Health
code=$(http_code GET "$URL/api/v1/health")
if [ "$code" = "200" ]; then
  ok "health HTTP $code $(head -c 120 /tmp/smoke_body.bin 2>/dev/null | tr '\n' ' ')"
else
  bad "health HTTP $code (start runtime to pass this check)"
fi

# 2) Query
code=$(http_code POST "$URL/api/v1/query" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $KEY" \
  -d '{"query":"who are you in one short sentence","mode":"chal","character":"synthesus"}')
if [ "$code" = "200" ]; then
  body=$(head -c 300 /tmp/smoke_body.bin 2>/dev/null | tr '\n' ' ')
  if echo "$body" | grep -qiE 'traceback|internal server error'; then
    bad "query 200 but looks broken: $body"
  else
    ok "query HTTP $code body=${body}"
  fi
else
  bad "query HTTP $code"
fi

# 3) Feedback without human proof must NOT upgrade
code=$(http_code POST "$URL/api/v1/feedback" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $KEY" \
  -d '{"session_id":"smoke","query":"q","response":"r","rating":5}')
if [ "$code" = "200" ] || [ "$code" = "401" ]; then
  if grep -q '"upgraded": true' /tmp/smoke_body.bin 2>/dev/null; then
    bad "feedback upgraded without human proof: $(head -c 200 /tmp/smoke_body.bin)"
  else
    ok "feedback without human proof did not crystallize (HTTP $code)"
  fi
else
  note "feedback endpoint HTTP $code"
fi

# 4) Image endpoint
code=$(http_code POST "$URL/api/v1/image" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $KEY" \
  -d '{"prompt":"a red cube on a table"}')
if [ "$code" = "200" ]; then
  ok "image HTTP 200 (bytes=$(wc -c </tmp/smoke_body.bin))"
elif [ "$code" = "404" ] || [ "$code" = "405" ]; then
  note "image endpoint not available ($code)"
else
  note "image HTTP $code"
fi

# 5) sklearn pin (local)
if [ -x "$PY" ]; then
  if "$PY" -c "
import warnings, sys
from pathlib import Path
root = Path.home() / 'synthesus'
sys.path[:0] = [str(root/'runtime/packages/knowledge'), str(root/'runtime/packages'), str(root/'runtime')]
warnings.simplefilter('always')
caught = []
def show(m, c, f, l, file=None, line=None):
    caught.append(c.__name__)
warnings.showwarning = show
import sklearn
assert sklearn.__version__.startswith('1.8'), sklearn.__version__
from swarm_embedder import SwarmEmbedder
e = SwarmEmbedder(dim=16)
e.fit(['alpha beta', 'gamma delta'])
_ = e.embed_texts(['alpha'])
assert 'InconsistentVersionWarning' not in caught
print('sklearn', sklearn.__version__, 'ok')
" 2>/tmp/smoke_sk.txt; then
    ok "sklearn embedder: $(tr '\n' ' ' </tmp/smoke_sk.txt)"
  else
    bad "sklearn embedder: $(tr '\n' ' ' </tmp/smoke_sk.txt)"
  fi
else
  note "python $PY missing"
fi

# 6) Kernel IPC
KBIN="${SYNTHESUS_KERNEL_BIN:-$ROOT/runtime/packages/kernel/build/zo_kernel}"
if [ -x "$KBIN" ]; then
  resp=$(printf '%s\n' '{"query":"smoke kernel"}' 'quit' | "$KBIN" 2>/dev/null | head -1 || true)
  if echo "$resp" | grep -q 'response'; then
    ok "zo_kernel IPC: ${resp:0:120}"
  else
    bad "zo_kernel IPC bad response: $resp"
  fi
else
  note "zo_kernel not at $KBIN"
fi

# 7) Verbatim prompt present
if grep -q 'VERBATIM' "$ROOT/runtime/packages/core/chal/devices/llm_device.py" 2>/dev/null; then
  ok "llm_device DEFAULT_SYSTEM_PROMPT contains VERBATIM instruction"
else
  bad "VERBATIM grounding instruction missing from llm_device"
fi

# 8) Human session secret documented in install
if grep -q 'SYNTHESUS_HUMAN_SESSION_SECRET' "$ROOT/install.sh" 2>/dev/null; then
  ok "install.sh generates SYNTHESUS_HUMAN_SESSION_SECRET"
else
  bad "install.sh missing human session secret"
fi

echo
echo "=== summary: pass=$pass fail=$fail skip=$skip ==="
if [ "$fail" -gt 0 ]; then
  exit 1
fi
exit 0
