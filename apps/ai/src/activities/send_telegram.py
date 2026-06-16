"""
Telegram Activity for Temporal.

Sends messages via the Telegram mock server (tg-mock).
Uses httpx.AsyncClient to POST to http://localhost:8085/bot{TOKEN}/sendMessage
"""
import os
from typing import Optional

import httpx
from temporalio import activity

# Telegram mock server configuration
# Supports both env vars and defaults
TELEGRAM_API_BASE = os.getenv("TELEGRAM_API_BASE", "http://localhost:8085")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "test-bot-token")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "trackguard-alerts")


@activity.defn(name="send_telegram_message")
async def send_telegram_message(
    chat_id: str,
    text: str,
    parse_mode: str = "HTML",
) -> dict:
    """
    Send a text message via Telegram mock API.

    Args:
        chat_id: Telegram chat ID (or username)
        text: Message text (supports HTML parse_mode)
        parse_mode: Parse mode for formatting (default: HTML)

    Returns:
        dict with keys:
            - ok: bool (True if sent successfully)
            - message_id: int (Telegram message ID)
            - chat_id: str (echo of input chat_id)

    Raises:
        ValueError: If text is empty
        httpx.HTTPError: If the API request fails
    """
    if not text or not text.strip():
        raise ValueError("Message text cannot be empty")

    url = f"{TELEGRAM_API_BASE}/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, timeout=10.0)
        response.raise_for_status()
        result = response.json()

    return {
        "ok": result.get("ok", False),
        "message_id": result.get("result", {}).get("message_id", 0),
        "chat_id": chat_id,
    }


@activity.defn(name="send_telegram_photo")
async def send_telegram_photo(
    chat_id: str,
    photo_path: str,
    caption: str = "",
) -> dict:
    """
    Send a photo with optional caption via Telegram mock API.

    Args:
        chat_id: Telegram chat ID (or username)
        photo_path: Absolute path to PNG file
        caption: Optional caption text

    Returns:
        dict with keys:
            - ok: bool (True if sent successfully)
            - message_id: int (Telegram message ID)
            - chat_id: str (echo of input chat_id)

    Raises:
        ValueError: If photo_path is missing or file doesn't exist
        httpx.HTTPError: If the API request fails
    """
    if not photo_path or not photo_path.strip():
        raise ValueError("Photo path cannot be empty")

    # Check file exists (skip in test mode)
    if not os.path.exists(photo_path):
        raise ValueError(f"Photo file not found: {photo_path}")

    url = f"{TELEGRAM_API_BASE}/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"

    # Send as multipart form data
    with open(photo_path, "rb") as photo_file:
        files = {"photo": photo_file}
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption

        async with httpx.AsyncClient() as client:
            response = await client.post(url, files=files, data=data, timeout=10.0)
            response.raise_for_status()
            result = response.json()

    return {
        "ok": result.get("ok", False),
        "message_id": result.get("result", {}).get("message_id", 0),
        "chat_id": chat_id,
    }
