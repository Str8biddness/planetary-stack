#!/usr/bin/env bash
# Install or remove the sudo timestamp policy used by `synthesus --agentic`.
# This never grants NOPASSWD access.
set -euo pipefail

action="${1:---install}"
target_user="${2:-${SUDO_USER:-${USER:-}}}"
visudo_bin="${VISUDO:-/usr/sbin/visudo}"

if [[ -z "$target_user" || ! "$target_user" =~ ^[a-z_][a-z0-9_-]*[$]?$ ]]; then
  printf 'Invalid target user: %s\n' "$target_user" >&2
  exit 2
fi
if ! id "$target_user" >/dev/null 2>&1; then
  printf 'Target user does not exist: %s\n' "$target_user" >&2
  exit 2
fi

policy_path="/etc/sudoers.d/synthesus-agentic-$target_user"
render_policy() {
  cat <<EOF
# Synthesus agentic elevation for $target_user.
# No commands are passwordless. A launch performs sudo -k, authenticates once,
# refreshes every 30 seconds, and revokes the ticket when the desktop exits.
Defaults:$target_user timestamp_type=global, timestamp_timeout=1
EOF
}

if [[ "$action" == "--render" ]]; then
  render_policy
  exit 0
fi

if ((EUID != 0)); then
  printf 'Run this setup through sudo or pkexec.\n' >&2
  exit 1
fi
if [[ ! -x "$visudo_bin" ]]; then
  printf 'visudo not found at %s\n' "$visudo_bin" >&2
  exit 1
fi

case "$action" in
  --install)
    tmp="$(mktemp)"
    trap 'rm -f "$tmp"' EXIT
    render_policy >"$tmp"
    "$visudo_bin" -cf "$tmp"
    install -o root -g root -m 0440 "$tmp" "$policy_path"
    "$visudo_bin" -cf /etc/sudoers
    printf 'Installed %s\n' "$policy_path"
    ;;
  --remove)
    rm -f "$policy_path"
    "$visudo_bin" -cf /etc/sudoers
    printf 'Removed %s\n' "$policy_path"
    ;;
  *)
    printf 'Usage: %s [--install|--remove|--render] [user]\n' "$0" >&2
    exit 2
    ;;
esac
