# Swarm cluster transport is cleartext and unauthenticated — 2026-07-21

Motivating finding for the paired request/response exchange
(`services/unisync/exchange.py`). Recorded here because it is the reason that
work exists, not as a claim about this repo's code.

## Subject

`Str8biddness/synthesus-mobile-desktop` at commit `4b86caf`, module
`runtime/packages/swarm/coordinator.py`. This is a *different repository* from
planetary-stack; nothing here is a defect in planetary-stack.

## What was run

The unmodified `ClusterCoordinator` — real `ClusterRegistry`, real
`ClusterNode`, default `http_post` (i.e. `_default_http_post`, the production
transport at `coordinator.py:277`) — driven against a raw socket listener that
writes out every byte it receives before replying.

## Captured bytes

```
POST /api/generate HTTP/1.1
Accept-Encoding: identity
Content-Length: 196
Host: 127.0.0.1:11666
User-Agent: Python-urllib/3.12
Content-Type: application/json
Connection: close

{"model": "demo-3b", "prompt": "My social security number is 078-05-1120 and my
bank password is hunter2. Summarize my medical history.", "stream": false,
"system": "You are a private assistant."}
```

1. **No TLS.** The first bytes on the wire are the HTTP request line; there is
   no handshake. Node addresses in `cluster_config.py` are `http://<ip>:<port>`.
2. **No authentication.** The only header set is `Content-Type`. There is no
   `Authorization`. `desktop/shell_auth.py` gates the desktop shell's *inbound*
   routes; it does not apply to cluster traffic.
3. **Response injection.** The listener replied
   `{"response":"WIRE-CAPTURE-REPLY","done":true}` — an arbitrary string from an
   unauthenticated peer. The coordinator returned
   `served_locally: False, degraded: False, text: 'WIRE-CAPTURE-REPLY'`,
   accepting it as a genuine model answer with no degradation signal. Anything
   able to answer at that address dictates what the user reads as their AI's
   response.

## What was found to be correct

- Ollama on the second machine binds `127.0.0.1:11434`, not `0.0.0.0` (verified
  via `ss -ltnp`). Correct default.
- With the node unreachable, the coordinator degraded to local with
  `degrade_reason: all_nodes_failed_and_no_local_fallback` — it fails safe
  rather than open.

## Limits of this evidence

**This is a loopback socket capture, not a LAN wire capture.** The cross-machine
leg was attempted between this desktop and `dakin-MS-7C95` (192.168.68.54) and
was blocked: ufw is enabled on that host (`/etc/ufw/ufw.conf` `ENABLED=yes`) and
no passwordless sudo is available to open a port. The bytes a transport emits do
not depend on the peer's address, so the three conclusions above hold — but a
two-machine on-the-wire capture was **not** obtained and is not claimed.

No FINISH_CHECKLIST box is checked by this document.
