from __future__ import annotations

import base64
import hashlib
import hmac
import os
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


class HmacSecretDigester:
    def __init__(self, key: bytes) -> None:
        if len(key) < 32:
            raise ValueError("The local host secret must contain at least 32 bytes.")
        self._key = key

    def digest(self, secret: str) -> str:
        return hmac.new(self._key, secret.encode("utf-8"), hashlib.sha256).hexdigest()

    def derive(self, purpose: str, material: str) -> str:
        value = hmac.new(
            self._key,
            f"{purpose}\0{material}".encode(),
            hashlib.sha256,
        ).digest()
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class Argon2RoomPasswordHasher:
    def __init__(self) -> None:
        self._hasher = PasswordHasher()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, encoded_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(encoded_hash, password)
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            return False


def load_or_create_host_secret(path: Path) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        value = path.read_bytes()
        if len(value) < 32:
            raise RuntimeError(f"Host secret at {path} is invalid.")
        return value
    value = os.urandom(32)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path.read_bytes()
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(value)
    return value
