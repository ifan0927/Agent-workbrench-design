"""Single-host refresh coordination. Real OAuth is an injected provider."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import fcntl
import json
import os
from pathlib import Path
import tempfile


class AuthFailure(Exception):
    def __init__(self, action):
        self.action = action
        super().__init__(action)


@dataclass(frozen=True)
class Tokens:
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    account_id: str = field(repr=False)
    generation: int = 0

    def external(self):
        return {"accessToken": self.access_token, "chatgptAccountId": self.account_id}


def classify(error):
    """Map structured errors; never infer an action from arbitrary error text."""
    code = error.get("code")
    info = error.get("codexErrorInfo")
    if code in ("invalid_grant", "revoked", "unauthorized", 401) or info == "unauthorized":
        return "reauthenticate"
    if code in ("insufficient_quota", "usage_limit_reached") or info == "usageLimitExceeded":
        return "quota_exhausted"
    if (code in ("timeout", "rate_limit_exceeded", 408, 429, 503)
            or info in ("rateLimitExceeded", "serverOverloaded", "sessionBudgetExceeded")):
        return "pause"
    if isinstance(info, dict):
        status = next((v.get("httpStatusCode") for v in info.values() if isinstance(v, dict)), None)
        if status in (401, 408, 429, 503):
            return classify({"code": status})
    return "stop"


def atomic_json(path, value):
    """Persist the state and its secret generation in one replacement."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".write-")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class Coordinator:
    def __init__(self, private_dir, provider, crash=lambda phase: None):
        self.root = Path(private_dir)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.stat().st_mode & 0o077:
            raise AuthFailure("private_directory_permissions")
        self.path = self.root / "credential.json"
        self.provider = provider
        self.crash = crash

    def seed(self, tokens):
        # Initialization is explicit and must never replace an existing identity.
        if self.path.exists():
            raise AuthFailure("already_initialized")
        self.save(tokens, "ready")

    def save(self, tokens, phase, action=None):
        atomic_json(self.path, {"access_token": tokens.access_token,
                               "refresh_token": tokens.refresh_token,
                               "account_id": tokens.account_id,
                               "generation": tokens.generation,
                               "phase": phase, "action": action})

    def read(self):
        d = json.loads(self.path.read_text())
        return Tokens(**{k: d[k] for k in ("access_token", "refresh_token", "account_id", "generation")}), d

    @asynccontextmanager
    async def locked(self):
        fd = os.open(self.root / "refresh.lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    await asyncio.sleep(0.01)
            yield
        finally:
            os.close(fd)

    async def refresh(self, observed_generation, account_id):
        # Keep coordination below the app-server's approximately 10 second deadline.
        try:
            async with asyncio.timeout(8):
                async with self.locked():
                    old, state = self.read()
                    if account_id != old.account_id:
                        raise AuthFailure("account_mismatch")
                    if state["phase"] == "in_flight":
                        raise AuthFailure("reauthenticate_unknown")
                    if state["phase"] == "failed":
                        raise AuthFailure(state["action"])
                    if old.generation > observed_generation:
                        return old
                    if old.generation != observed_generation:
                        raise AuthFailure("generation_mismatch")
                    self.save(old, "prepared")
                    self.crash("before_remote")
                    # A crash from this point may have consumed the refresh token.
                    self.save(old, "in_flight")
                    try:
                        new = await self.provider(old)
                    except AuthFailure as exc:
                        self.save(old, "failed", exc.action)
                        raise
                    except Exception:
                        # Unknown transport outcomes are not safe to replay.
                        raise AuthFailure("reauthenticate_unknown") from None
                    self.crash("after_remote")
                    if new.account_id != old.account_id or new.generation != old.generation + 1:
                        raise AuthFailure("reauthenticate_unknown")
                    self.save(new, "ready")
                    self.crash("after_saved")
                    return new
        except TimeoutError:
            # A timed-out remote refresh may already have rotated credentials.
            raise AuthFailure("pause") from None
