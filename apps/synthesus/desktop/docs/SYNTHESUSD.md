# synthesusd local controller boundary

`synthesusd` is the desktop-facing local controller. It keeps the WebSocket
desktop as an unprivileged presentation client and prevents it from treating
the cognitive runtime or host terminal as directly reachable services.

```text
Desktop shell :8081
  |
  | per-install API key (runtime) or per-launch capability (terminal)
  v
synthesusd :5011, loopback only
  |                              |
  | authenticated HTTP          | authenticated WebSocket/HTTP
  v                              v
Synthesus runtime :5010       user-only Unix socket
                                  |
                                  v
                              PTY backend
```

## Authentication

- Runtime proxy routes require `X-API-Key`, using the private install key that
  the desktop shell already injects on its server-to-server hop.
- Terminal HTTP and WebSocket routes require a separate random capability
  generated for each desktop launch.
- WebSocket capabilities travel in the subprotocol handshake, not in the URL,
  so access logs do not record them.
- The same-origin shell mints the browser capability only after validating the
  logged-in user's desktop JWT.
- The browser receives only the terminal capability. It never receives the
  install API key or human-attestation secret.
- WebSocket terminal requests must also present an allowed local UI `Origin`.

## Transport

- `synthesusd` refuses non-loopback binding.
- The PTY backend listens on
  `~/.synthesus/ipc/terminal.sock`, not a TCP port.
- The socket directory is mode `0700`; the socket is created under umask
  `0077`.
- Runtime and terminal failures return explicit degraded/unavailable responses.

## Development overrides

The defaults can be moved for isolated tests:

```bash
SYNTHESUS_SHELL_PORT=18081
SYNTHESUS_CONTROLLER_PORT=15011
SYNTHESUS_TERMINAL_SOCKET=/tmp/synthesus-test/terminal.sock
SYNTHESUS_HEADLESS=1
```

Remote headless use must tunnel both `8081` and `5011`; see `HEADLESS.md`.

## Desktop identity

The native application-menu entry and web favicon share
`desktop/assets/synthesus-icon.png`: a high-contrast black field with a white
symbolic S. The installer references the copied absolute asset path so desktop
environments do not depend on the launch working directory.
