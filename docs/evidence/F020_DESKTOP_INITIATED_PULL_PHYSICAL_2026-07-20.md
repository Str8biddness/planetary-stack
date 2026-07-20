# Desktop-initiated result pull — PHYSICAL — 2026-07-20

## What was proven

The firewall-free result return works on real hardware: **this desktop dialed
OUTBOUND to the worker and received the genuine model result over lease-bound
mTLS**, with no inbound firewall opened on the desktop. Only the worker (a
provisioned mesh node) listened.

- Desktop / receiver: `dakin-chronos` (192.168.68.55) — LOCAL node, opened the
  TCP connection, acted as TLS server + object receiver.
- Worker / source: `dakin-MS-7C95` (192.168.68.54) — listened, acted as TLS
  client + object sender (pinned SSH host key
  `SHA256:q0JCxuHCtW6gnRbnnAvcH0sqFz5RE8tfKQHoXSMGw4w`).
- Node-side `implementation_sha256`:
  `fcb44987e1f4fb2bbaf465e210e5d8a49f108f7870f9a54b453fce12060d7784`
  (worker deployed at commit `699a338c9454f313ebd5a28ac8d12f3a27f97ce3`).

## The object

The genuine text-classification result produced earlier by real rootless
Podman on the worker (`docs/evidence/F020_RESULT_BYTE_RETURN_PHYSICAL_...`):

- sha256 `5df96635e0a6a63e1026d42ced2e4dbbaa72a370035f0d7aa0df004476e557b1`
  (314 bytes, `label: positive`) — byte-identical to every prior physical path.
- Staged into the worker outbox by `stage-result`, then pulled.

## Transfer (desktop-initiated pull)

Driven with the `hybrid` carrier + `pull=True`: fresh TLS enrollment on both
nodes, mesh CA issuance/install, a scheduler-signed active `lan_mtls` lease
bound to the desktop as destination, then `pull-serve` on the worker (listen +
upload as TLS client) and `pull-fetch` on the desktop (dial + receive as TLS
server).

- Direction: `desktop_initiated_pull`; run token `0fcbbe87a678631f`.
- Worker upload: `TLSv1.3`, `lan_mtls`, cert `97fbc6dd…`.
- Desktop receipt: `received=true`, audit `client_identity_bound`, cert
  `f0f500134cd0…`.
- Scheduler-signed lease `lease:bbf2c5843caf745d83d3924e095c03e2`; verified
  receipt `6fb6ec2a86e5b89a789a3442ffc2f92215957208f2792cfc5a14ec23e2cbc569`;
  durably released.
- Evidence transcript sha256
  `13958eeaaed942df876fa255bf6be415a8c4363b12817b2a96c1442e3c895d9e`;
  checkpoint-stable vSource SQLite sha256
  `66d3dfeb533343c5098cf1f7ba6c4817bb453cdf47efed80fdc0a8ae334b4fb0`.

## Independent verification

The desktop's LOCAL inbox object
`inbox/objects/5d/5df96635…` re-hashes to
`5df96635e0a6a63e1026d42ced2e4dbbaa72a370035f0d7aa0df004476e557b1` at 314
bytes, content byte-identical to the genuine result. The desktop opened the
connection; the worker never connected to the desktop.

## Claims (from the transcript)

- `desktop_initiated_pull_no_inbound_firewall: true`
- `receiver_opened_tcp_connection: true`
- `mutual_tls_client_certificate_required: true`,
  `negotiated_tls_version: TLSv1.3`, `scheduler_signed_active_lease_bound: true`
- `physical_two_node_execution_proven: true`

## Honest scope — no FINISH_CHECKLIST box is checked

This proves the sellable transport: a customer's desktop pulls its result
outbound over mutually-authenticated mTLS with no inbound firewall. It does NOT
yet include the `synthesusd` `result_loader` wiring that runs this pull when a
live browser fetches a completed job's result (the transport + coordinator are
proven; that final integration is the remaining step). Enrollment here is fresh
per transfer, not persistent-reuse.
