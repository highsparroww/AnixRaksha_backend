"""Integration boundary for future health-intake NLP processing.

This module intentionally performs no extraction, prediction, or response generation.
It can later consume temporary client-side conversation state and update
HealthIntake.structured_data without persisting a raw transcript.
"""

from typing import Protocol


class ConversationProcessor(Protocol):
    async def process_intake_state(self, conversation_id: str, state: dict) -> None: ...


class NoopConversationProcessor:
    async def process_intake_state(self, conversation_id: str, state: dict) -> None:
        return None
