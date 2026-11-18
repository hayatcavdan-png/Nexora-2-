"""Optional TELETHON listener for a future clean deployment.

Never start this alongside an already running nexora_tg_bridge session.
Records *only* source handle, numeric message ID, local arrival time.
Does not read, parse, forward or persist text, token mints or private chats.

Telegram account/API credentials MUST NOT be committed to GitHub.
"""
import asyncio
from datetime import datetime
import getpass
import os
from pathlib import Path


TARGET_HANDLES = {"solearlytrending", "kolscope"}


async def listen():
    try:
        from telethon import TelegramClient, events
    except ImportError as exc:
        raise SystemExit("Telethon gerekli; mevcut T5 servisini durdurmayin") from exc

    os.umask(0o077)
    root = Path.home() / ".nexora_telegram_bridge"
    root.mkdir(mode=0o700, exist_ok=True)
    session = root / "nexora_user"
    try:
        api_id = int(getpass.getpass("Telegram API ID (yalnizca yerel): ").strip())
        api_hash = getpass.getpass("Telegram API Hash (yalnizca yerel): ").strip()
        if api_id < 1 or len(api_hash) != 32:
            raise ValueError("Invalid API credentials")
    except ValueError as exc:
        raise SystemExit("API ID/Hash gecersiz") from exc

    client = TelegramClient(str(session), api_id, api_hash)
    try:
        await client.start()
        channels = {}
        async for dialog in client.iter_dialogs():
            username = getattr(dialog.entity, "username", None)
            if isinstance(username, str) and username.lower() in TARGET_HANDLES:
                channels[dialog.id] = "@" + username
        if set(s.lower().lstrip("@") for s in channels.values()) != TARGET_HANDLES:
            raise SystemExit("HATA: iki kanal da hesapta mevcut olmali")

        @client.on(events.NewMessage(chats=list(channels)))
        async def on_new_message(event):
            handle = channels.get(event.chat_id)
            msg_id = getattr(event.message, "id", None)
            if handle is None or type(msg_id) is not int or msg_id <= 0:
                return
            stamp = datetime.now().strftime("%H:%M:%S")
            print(f"YENI PAYLASIM | {handle} | ID: {msg_id} | {stamp}", flush=True)

        print("TELEGRAM METADATA DINLEYICI: AKTIF | KANAL: 2/2", flush=True)
        print("MESAJ METNI: YOK | SOCIAL AI AKTARIMI: KAPALI", flush=True)
        await client.run_until_disconnected()
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(listen())
