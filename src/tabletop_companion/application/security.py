from __future__ import annotations

from typing import Protocol


class SecretDigester(Protocol):
    def digest(self, secret: str) -> str: ...

    def derive(self, purpose: str, material: str) -> str: ...


class RoomPasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, encoded_hash: str, password: str) -> bool: ...
