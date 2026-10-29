from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent


def _int_env(name: str, default: int = 0) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} phải là một số nguyên") from exc


@dataclass(frozen=True, slots=True)
class Config:
    token: str
    support_role_id: int
    citizen_role_id: int
    new_citizen_role_id: int
    rules_url: str
    whitelist_url: str
    welcome_image_url: str
    ticket_image_url: str
    retention_days: int
    max_attachment_bytes: int
    command_prefix: str
    database_path: Path
    transcript_dir: Path

    @classmethod
    def load(cls) -> "Config":
        load_dotenv(BASE_DIR / ".env")
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token:
            raise RuntimeError("Thiếu DISCORD_TOKEN trong file .env")
        support_role_id = _int_env("SUPPORT_ROLE_ID")
        if support_role_id <= 0:
            raise RuntimeError("Thiếu SUPPORT_ROLE_ID hợp lệ trong file .env")
        citizen_role_id = _int_env("CITIZEN_ROLE_ID")
        if citizen_role_id <= 0:
            raise RuntimeError("Thiếu CITIZEN_ROLE_ID hợp lệ trong file .env")
        new_citizen_role_id = _int_env("NEW_CITIZEN_ROLE_ID")
        if new_citizen_role_id <= 0:
            raise RuntimeError("Thiếu NEW_CITIZEN_ROLE_ID hợp lệ trong file .env")

        data_dir = BASE_DIR / "data"
        transcript_dir = data_dir / "transcripts"
        data_dir.mkdir(parents=True, exist_ok=True)
        transcript_dir.mkdir(parents=True, exist_ok=True)

        return cls(
            token=token,
            support_role_id=support_role_id,
            citizen_role_id=citizen_role_id,
            new_citizen_role_id=new_citizen_role_id,
            rules_url=os.getenv("RULES_URL", "").strip(),
            whitelist_url=os.getenv("WHITELIST_URL", "").strip(),
            welcome_image_url=os.getenv("WELCOME_IMAGE_URL", "").strip(),
            ticket_image_url=os.getenv("TICKET_IMAGE_URL", "").strip(),
            retention_days=max(1, _int_env("TRANSCRIPT_RETENTION_DAYS", 15)),
            max_attachment_bytes=max(1, _int_env("MAX_ATTACHMENT_MB", 25)) * 1024 * 1024,
            command_prefix=os.getenv("COMMAND_PREFIX", "+").strip() or "+",
            database_path=data_dir / "bot.db",
            transcript_dir=transcript_dir,
        )

