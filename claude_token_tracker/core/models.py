"""Dataclasses for session, message, token usage, and dashboard snapshots."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input: int = 0
    output: int = 0
    cache_create: int = 0
    cache_read: int = 0

    @property
    def total(self) -> int:
        return self.input + self.output + self.cache_create + self.cache_read


@dataclass(frozen=True, slots=True)
class Message:
    timestamp: datetime
    usage: TokenUsage


@dataclass(slots=True)
class Session:
    file: str
    project: str
    session_id: str
    title: Optional[str]
    model: Optional[str]
    is_subagent: bool
    messages: list[Message] = field(default_factory=list)
    first_timestamp: Optional[datetime] = None
    last_timestamp: Optional[datetime] = None

    @property
    def input_tokens(self) -> int:
        return sum(m.usage.input for m in self.messages)

    @property
    def output_tokens(self) -> int:
        return sum(m.usage.output for m in self.messages)

    @property
    def cache_create_tokens(self) -> int:
        return sum(m.usage.cache_create for m in self.messages)

    @property
    def cache_read_tokens(self) -> int:
        return sum(m.usage.cache_read for m in self.messages)

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_create_tokens
            + self.cache_read_tokens
        )
