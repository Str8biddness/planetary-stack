"""
SYNTHESUS 5 — REAL ACCOUNT SYSTEM
Persistent email/password accounts with hashed credentials.

Self-contained on purpose: uses only stdlib sqlite3 + Werkzeug (ships with Flask)
+ PyJWT, so it imports cleanly both in dev and inside the PyInstaller AppImage.
"""

import os
import re
import stat
import time
import sqlite3
import jwt
from werkzeug.security import generate_password_hash, check_password_hash

# Persistent DB in the user's home (NOT /tmp — survives reboots).
DB_DIR = os.path.expanduser("~/.synthesus")
DB_PATH = os.environ.get("SYNTHESUS_DB", os.path.join(DB_DIR, "synthesus.db"))

JWT_ALGO = "HS256"
TOKEN_TTL_MINUTES = 60 * 24 * 7  # 7 days

_KNOWN_DEFAULT_JWT_SECRETS = frozenset({"dev_secret_change_me"})
_MIN_JWT_SECRET_BYTES = 32

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Free starter allowance so a brand-new account can actually use the product.
FREE_TIER_TOKENS = 50_000


class AccountError(Exception):
    """Raised for any expected, user-facing account problem (bad input, dup email, etc.)."""


def _jwt_secret():
    """Return the private install secret or refuse insecure account operation.

    ``JWT_SECRET`` remains a compatibility input for existing private installs,
    but new installs use the namespaced ``SYNTHESUS_JWT_SECRET`` variable.
    There is deliberately no source-tree default: a public fallback would let
    any local process forge a login and mint a terminal capability.
    """
    secret = (
        os.environ.get("SYNTHESUS_JWT_SECRET")
        or os.environ.get("JWT_SECRET")
        or ""
    ).strip()
    if secret in _KNOWN_DEFAULT_JWT_SECRETS or len(secret.encode("utf-8")) < _MIN_JWT_SECRET_BYTES:
        raise RuntimeError(
            "Synthesus accounts require a unique per-install JWT secret of at least "
            f"{_MIN_JWT_SECRET_BYTES} bytes; run install.sh or set "
            "SYNTHESUS_JWT_SECRET."
        )
    return secret


def require_secure_configuration():
    """Fail closed during desktop startup if account signing is insecure."""
    _jwt_secret()


def _confine_database_path():
    """Create/check the SQLite path without following a database symlink."""
    path = os.path.abspath(os.path.expanduser(DB_PATH))
    parent = os.path.dirname(path)
    parent_existed = os.path.lexists(parent)
    os.makedirs(parent, mode=0o700, exist_ok=True)

    parent_stat = os.lstat(parent)
    if not stat.S_ISDIR(parent_stat.st_mode):
        raise RuntimeError(f"Synthesus account database parent is not a directory: {parent}")
    if parent_stat.st_uid != os.geteuid():
        raise RuntimeError(f"Synthesus account database parent is not owned by this user: {parent}")
    parent_mode = stat.S_IMODE(parent_stat.st_mode)
    default_parent = os.path.abspath(os.path.expanduser(DB_DIR))
    if parent_mode & 0o077:
        if parent == default_parent:
            # Tighten the legacy default directory in place during upgrade.
            os.chmod(parent, 0o700)
        elif parent_existed:
            # Never chmod an arbitrary configured parent such as /tmp or $HOME.
            raise RuntimeError(
                f"Synthesus account database parent must be owner-only (0700): {parent}"
            )

    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise RuntimeError(f"Synthesus account database path is unsafe: {path}: {exc}") from exc
    try:
        file_stat = os.fstat(fd)
        if not stat.S_ISREG(file_stat.st_mode):
            raise RuntimeError(f"Synthesus account database is not a regular file: {path}")
        if file_stat.st_uid != os.geteuid():
            raise RuntimeError(f"Synthesus account database is not owned by this user: {path}")
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)
    return path


def _connect():
    path = _confine_database_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                email         TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                tier          TEXT NOT NULL DEFAULT 'free',
                token_balance INTEGER NOT NULL DEFAULT 0,
                created_at    INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                user_id INTEGER NOT NULL,
                key     TEXT NOT NULL,
                value   TEXT,
                PRIMARY KEY (user_id, key),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        conn.commit()


def _issue_token(user_id, email):
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": int(time.time()) + TOKEN_TTL_MINUTES * 60,
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGO)


def _public(row):
    """A user dict safe to send to the frontend (never the password hash)."""
    return {
        "id": row["id"],
        "email": row["email"],
        "tier": row["tier"],
        "token_balance": row["token_balance"],
    }


def register(email, password):
    """Create a new account. Returns {token, user}. Raises AccountError on bad input / duplicate."""
    email = (email or "").strip().lower()
    password = password or ""

    if not EMAIL_RE.match(email):
        raise AccountError("Please enter a valid email address.")
    if len(password) < 8:
        raise AccountError("Password must be at least 8 characters.")

    pw_hash = generate_password_hash(password)
    try:
        with _connect() as conn:
            cur = conn.execute(
                "INSERT INTO users (email, password_hash, tier, token_balance, created_at) "
                "VALUES (?, ?, 'free', ?, ?)",
                (email, pw_hash, FREE_TIER_TOKENS, int(time.time())),
            )
            conn.commit()
            user_id = cur.lastrowid
    except sqlite3.IntegrityError:
        raise AccountError("An account with that email already exists. Try logging in.")

    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    return {"token": _issue_token(user_id, email), "user": _public(row)}


def authenticate(email, password):
    """Verify credentials. Returns {token, user} or raises AccountError."""
    email = (email or "").strip().lower()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    if row is None or not check_password_hash(row["password_hash"], password or ""):
        # Same message for "no such user" and "wrong password" — don't leak which emails exist.
        raise AccountError("Incorrect email or password.")

    return {"token": _issue_token(row["id"], email), "user": _public(row)}


def verify_token(token):
    """Returns the decoded payload, or None if invalid/expired."""
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGO])
    except jwt.InvalidTokenError:
        return None


VALID_TIERS = ("free", "pro", "ultra")


def set_tier(email, tier):
    """Manually upgrade/downgrade an account after a Stripe payment. Returns True if a row changed."""
    email = (email or "").strip().lower()
    tier = (tier or "").strip().lower()
    if tier not in VALID_TIERS:
        raise AccountError(f"Tier must be one of {VALID_TIERS}, got '{tier}'.")
    with _connect() as conn:
        cur = conn.execute("UPDATE users SET tier = ? WHERE email = ?", (tier, email))
        conn.commit()
        return cur.rowcount > 0


def list_users():
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, email, tier, token_balance, created_at FROM users ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


# CLI:
#   python3 accounts.py upgrade <email> <free|pro|ultra>   -> fulfill a paid order
#   python3 accounts.py list                               -> show all accounts
#   python3 accounts.py                                    -> run self-test
if __name__ == "__main__":
    import sys
    import tempfile

    _args = sys.argv[1:]
    if _args and _args[0] == "upgrade":
        if len(_args) != 3:
            print("usage: accounts.py upgrade <email> <free|pro|ultra>")
            sys.exit(2)
        init_db()
        try:
            changed = set_tier(_args[1], _args[2])
        except AccountError as e:
            print("Error:", e); sys.exit(2)
        if changed:
            print(f"OK: {_args[1].strip().lower()} is now tier '{_args[2].strip().lower()}'")
            sys.exit(0)
        print(f"No account found for '{_args[1]}'"); sys.exit(1)

    if _args and _args[0] == "list":
        init_db()
        users = list_users()
        if not users:
            print("(no accounts yet)")
        for u in users:
            print(f"  #{u['id']:<3} {u['email']:<32} {u['tier']:<6} balance={u['token_balance']}")
        sys.exit(0)

    # Use a throwaway DB so the real one isn't touched during the test.
    DB_PATH = os.path.join(tempfile.mkdtemp(prefix="synthesus_accounts_test_"), "accounts.db")
    os.environ.setdefault("SYNTHESUS_JWT_SECRET", "accounts-self-test-" + ("x" * 32))

    init_db()
    print("DB initialized at", DB_PATH)

    r = register("Dakin@Example.com", "supersecret123")
    print("REGISTER ok    ->", r["user"], "token[:20]=", r["token"][:20] + "...")

    a = authenticate("dakin@example.com", "supersecret123")
    print("LOGIN ok       ->", a["user"])

    try:
        authenticate("dakin@example.com", "wrongpass")
        print("WRONG PASS     -> FAIL (should have raised!)")
    except AccountError as e:
        print("WRONG PASS     -> correctly rejected:", e)

    try:
        register("dakin@example.com", "anotherpass1")
        print("DUPLICATE      -> FAIL (should have raised!)")
    except AccountError as e:
        print("DUPLICATE      -> correctly rejected:", e)

    try:
        register("not-an-email", "supersecret123")
        print("BAD EMAIL      -> FAIL")
    except AccountError as e:
        print("BAD EMAIL      -> correctly rejected:", e)

    try:
        register("ok@example.com", "short")
        print("SHORT PASS     -> FAIL")
    except AccountError as e:
        print("SHORT PASS     -> correctly rejected:", e)

    p = verify_token(r["token"])
    print("TOKEN verify   ->", {"sub": p["sub"], "email": p["email"]})
    print("\nALL CHECKS PASSED")
    sys.exit(0)
