from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Protocol, Self

from tabletop_companion.domain.events import DomainEvent
from tabletop_companion.domain.models import (
    Account,
    Character,
    CharacterDraft,
    ItemDefinition,
    LocalPlayer,
    Room,
)


@dataclass(frozen=True, slots=True)
class ProcessedCommand:
    command_id: str
    command_type: str
    payload_hash: str
    actor_id: str
    device_id: str
    client_time: str | None
    host_time: str
    result: dict[str, Any]


class UnitOfWork(Protocol):
    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def get_processed_command(self, command_id: str) -> ProcessedCommand | None: ...

    def add_processed_command(self, command: ProcessedCommand) -> None: ...

    def add_room(self, room: Room) -> None: ...

    def get_room(self, room_id: str) -> Room: ...

    def add_local_player(self, player: LocalPlayer) -> None: ...

    def add_account(self, account: Account) -> None: ...

    def get_local_player(self, player_id: str) -> LocalPlayer: ...

    def add_character_draft(self, draft: CharacterDraft) -> None: ...

    def get_character_draft(self, draft_id: str) -> CharacterDraft: ...

    def save_character_draft(self, draft: CharacterDraft) -> None: ...

    def add_character(self, character: Character) -> None: ...

    def get_character(self, character_id: str) -> Character: ...

    def add_item_definition(self, definition: ItemDefinition) -> None: ...

    def save_character(self, character: Character) -> None: ...

    def is_character_assigned(self, character_id: str, room_id: str) -> bool: ...

    def assign_character(self, character_id: str, room_id: str, assigned_at: str) -> None: ...

    def character_in_active_encounter(self, character_id: str) -> bool: ...

    def clear_character_selections(self, character_id: str) -> None: ...

    def add_event(self, event: DomainEvent) -> DomainEvent: ...

    def list_events(self, room_id: str) -> list[DomainEvent]: ...

    def list_events_by_command(self, command_id: str) -> list[DomainEvent]: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]
