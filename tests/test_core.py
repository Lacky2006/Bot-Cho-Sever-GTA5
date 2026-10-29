from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from bot.database import Database
from bot.tickets import KINDS, TicketModal
from bot.transcript import TranscriptService


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        test_root = Path(__file__).resolve().parents[1] / "work"
        test_root.mkdir(exist_ok=True)
        self.temp_dir = tempfile.TemporaryDirectory(dir=test_root)
        self.db = Database(Path(self.temp_dir.name) / "test.db")
        await self.db.initialize()

    async def asyncTearDown(self) -> None:
        self.temp_dir.cleanup()

    async def test_ticket_lifecycle(self) -> None:
        settings = await self.db.get_guild_settings(100)
        self.assertEqual(settings["guild_id"], 100)

        await self.db.create_ticket(100, 200, 300, "bug", "a" * 32)
        ticket = await self.db.find_open_ticket(100, 300)
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket["channel_id"], 200)

        await self.db.close_ticket(200, datetime.now(timezone.utc).isoformat())
        self.assertIsNone(await self.db.find_open_ticket(100, 300))
        self.assertEqual((await self.db.get_ticket(200))["status"], "closed")


class ModalTests(unittest.TestCase):
    def test_all_ticket_forms_fit_discord_limit(self) -> None:
        for kind in KINDS.values():
            modal = TicketModal(None, kind)  # type: ignore[arg-type]
            self.assertEqual(len(modal.children), len(kind.fields))
            self.assertLessEqual(len(modal.children), 5)

    def test_transcript_escapes_embed_html(self) -> None:
        cleaned = TranscriptService._clean_embed_text("<script>alert(1)</script>\nOK", None)
        self.assertNotIn("<script>", cleaned)
        self.assertIn("&lt;script&gt;", cleaned)
        self.assertIn("<br>", cleaned)


if __name__ == "__main__":
    unittest.main()
