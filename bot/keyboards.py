"""
Inline keyboards.

Kept minimal — most user interaction is conversational, not button-driven.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def takeover_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Shown to admin on escalation — one-click to assume the conversation."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎤 Take over conversation",
                    callback_data=f"admin:takeover:{user_id}",
                )
            ]
        ]
    )
