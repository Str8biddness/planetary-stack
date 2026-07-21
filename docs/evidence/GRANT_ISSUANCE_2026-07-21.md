# Controller grant issuance against real physical documents — 2026-07-21

## What was checked

The desktop controller minted a `ResponseGrant` for the **genuine signed lease
and request produced by the physical mesh on 2026-07-20**, and the grant
validator then authorized the return leg carrying the real 314-byte result.

```
real lease   : lease:bbf2c5843caf745d83d3924e095c03e2
real request : fcd505f85421a8ee fencing: 1
grant signed : grant:physical:0001 ceiling 4096
RETURN LEG AUTHORIZED for the real result 5df96635… (314 B)
ceiling refused 314 B under a 128 B grant: response exceeds the granted byte ceiling
```

The second line matters as much as the first: the byte ceiling is not
decorative. A 314-byte result under a 128-byte grant is refused.

These are the same documents that, before grants existed, rejected the return
leg outright with `transfer destination is not the leased node`
(`docs/design/EXCHANGE_RESPONSE_AUTHORITY.md`).

## What this is NOT

**This is not a live two-machine exchange.** It replays real signed documents
recorded from earlier physical runs; no socket was opened between `.54` and
`.55` for this check. A live physical exchange additionally needs
`exchange-serve` / `exchange-request` commands in
`services/unisync/mesh_node_cli.py`, which **do not exist yet**.

Also not done here:
- Nothing in the scheduler automatically issues a grant during job placement;
  a caller must ask for one.
- The swarm `mesh_http_post` adapter is not started, so that project's cluster
  traffic remains plaintext HTTP.

## Reproduce

The script lives in the session scratchpad, not the repo, because it hardcodes
paths to recorded evidence. The equivalent assertions are permanent in
`tests/private_mesh/test_response_grants.py` and
`tests/unisync/test_mesh_grant.py::test_the_return_leg_now_authorizes_against_real_documents`.

No FINISH_CHECKLIST box is checked by this document.
