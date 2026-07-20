# Desktop-initiated result pull — the firewall-free result return

## Why

The result-byte return is proven node-to-node over lease-bound mTLS
(`docs/evidence/F020_RESULT_BYTE_RETURN_PHYSICAL_2026-07-20.md`). But making the
**desktop** the receiver requires the worker to open an mTLS socket *into* the
desktop, and a customer's desktop (a laptop/workstation) typically denies
inbound — the owner's desktop here has `ufw` active and blocked it. Asking a
buyer to open an inbound firewall port on their personal machine is a sales
killer and a support burden.

**Sellable design:** the desktop **dials outbound** to the worker and pulls the
result. The customer's desktop never opens a port. Only the worker — a machine
the customer *provisions* as a mesh node — listens, which is normal for a
server role.

## The key invariant (proven, not assumed)

A TLS server/client role is independent of which side opened the TCP
connection. So the desktop can **dial the TCP connection** (outbound) and still
be the **TLS server + object receiver**, while the worker **listens** (inbound)
but is the **TLS client + object sender**. Mutual-certificate auth and TLS 1.3
are preserved in both directions.

This is pinned by a running test with real sockets and mutual auth:
`tests/unisync/test_desktop_pull_feasibility.py` — the TCP dialer runs
`server_side=True`, receives the exact payload, and each side verifies the
other's certificate over TLS 1.3. If this regresses, the design's premise is
gone.

## What stays exactly the same (no security-semantics change)

- The scheduler-signed lease still binds `source = worker`, `destination =
  desktop`, `object = <result digest>`, `transport = lan_mtls`. Roles are
  unchanged: the **sender** (worker) validates the receiver is the enrolled
  destination; the **receiver** (desktop) validates the sender is the enrolled
  source. This is the same `require_authorized(... expected_peer_role=...)`
  binding the proven push uses.
- Content-addressing, TLS 1.3, mutual client certificate, verified receipt,
  durable lease release — all identical.
- The **only** thing that changes is which side opens the TCP socket.

## Implementation plan (contained, additive)

1. **Transport (`services/unisync/tls.py`).** Expose a
   `receive_object_over_tls_socket(...)` on the receiver that mirrors the
   sender's existing `upload_object_over_tls_socket(...)` — the internal
   frame/receipt/store logic already exists inside `TrustedLanServer`; this
   lifts it to run over a caller-provided `ssl.SSLSocket`. No change to the
   auth or lease checks. `TrustedLanClient.upload_object_over_tls_socket`
   already accepts a provided socket, so the sender side needs no change beyond
   wrapping its accepted socket `server_side=False`.
2. **Node CLI (`services/unisync/mesh_node_cli.py`).** Two commands:
   - `pull-serve` (worker): TCP-listen, accept one connection, wrap it
     `server_side=False` as the TLS client, and upload the leased object.
   - `pull-fetch` (desktop): TCP-dial the worker, wrap `server_side=True` as the
     TLS server, and receive the object into the local inbox, verifying the
     digest and emitting the receipt.
3. **Coordinator (`services/unisync/mesh_smoke.py`).** A pull variant that
   drives enroll/lease exactly as today, then runs `pull-serve` (worker, over
   SSH) + `pull-fetch` (desktop, local) with the desktop as the dialing
   receiver. `HybridMeshCarrier` already routes local-vs-SSH per node.
4. **Loader + wiring (`services/result_transfer.py`, `synthesusd`).** The
   physical `result_loader` runs `stage-result` on the worker (over SSH), then
   the desktop-initiated pull, and returns the verified bytes.
   `_build_job_pipeline` passes it to `build_remote_pipeline` (the passthrough
   already exists). The result endpoint and UI are already built.
5. **Physical verification.** Desktop `dakin-chronos` (.55) pulls a genuine
   staged result from worker `dakin-MS-7C95` (.54) — the desktop dials outbound
   (verified reachable), the worker accepts inbound (verified). No firewall
   change on the desktop.

## Honest status

Feasibility is **proven with running code** (the test above). The production
implementation of steps 1–5 is a focused, security-critical build on the mTLS
transport and must ship with full tests and a physical desktop→worker run
before any checklist box is checked. Nothing here claims the pull is
implemented yet — only that the architecture is validated and contained.
