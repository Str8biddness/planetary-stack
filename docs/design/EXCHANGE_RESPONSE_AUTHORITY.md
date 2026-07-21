# The response leg has no authority to travel under (blocker) — 2026-07-21

Found while preparing the two-machine physical run of the paired
request/response exchange (`services/unisync/exchange.py`, merged in `0aeb919`).
The transport is sound; its **authorization model is wrong**, and the unit tests
did not catch it because they inject the permissive test `StrictValidator`.

## What happens against the real validator

Replaying the genuine signed lease + request from the 2026-07-20 physical pull
(`docs/evidence/F020_DESKTOP_INITIATED_PULL_PHYSICAL_2026-07-20.evidence.json`)
through `SignedLeaseValidator`:

```
leg-1 context authorizes under the REAL validator: YES
leg-2 derived context authorizes: NO -> AuthorizationError
                                        transfer destination is not the leased node
```

## Two independent blockers

1. **A lease pins one destination node.** `SignedLeaseValidator` requires
   `expected_context.destination_node_id == lease.node_id`
   (`mesh_lease.py:179`). Leg 2 delivers to the *requester*, a different node.
   One lease therefore cannot authorize both directions — by design, not by
   oversight: a lease is authority to deliver TO a leased node.

2. **The response digest cannot be pre-declared.** The validator requires the
   transferred object to be an exact content reference in the signed request
   (`mesh_lease.py:189-196`; the existing gate test asserts this with
   `match="content reference"`). A response does not exist until the handler
   runs, so its digest cannot appear in a request signed beforehand.

Blocker 2 is the deeper one: even issuing a second lease for the return
direction would not help, because the controller cannot name the response
digest in advance.

## Consequence

`services/unisync/exchange.py` **cannot be run against the production
`SignedLeaseValidator` as written.** It works only with a validator that does
not enforce the leased-destination and content-reference rules. It must not be
wired into any application path until this is resolved.

## Direction (not yet built, not yet agreed)

The CHAL request already models this shape for jobs: it declares
`outputs: ["output:classification:001"]` — an output *slot*, not a digest. The
likely fix is to let a signed request authorize a bounded response slot for the
return leg (bounded by size, media type, and the request digest it answers),
and to have the scheduler issue the return-leg authority at the same time as the
forward lease. That is a **contracts change**, not a transport change, and it
needs its own review — a slot that is too loose would let a node return
arbitrary bytes under a lease the owner never approved.

## Status

- Physical two-machine run of the exchange: **NOT DONE — blocked by this.**
- No FINISH_CHECKLIST box is checked.
