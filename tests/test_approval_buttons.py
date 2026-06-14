import asyncio
import re
import tempfile
import unittest
from pathlib import Path

import discord

from channel.discord_bot import (
    APPROVAL_CUSTOM_ID_TEMPLATE,
    ApprovalButton,
    ApprovalView,
)
from hermes import bus


class FakeResponse:
    def __init__(self):
        self.edited = None
        self.sent = None
        self._done = False

    def is_done(self):
        return self._done

    async def edit_message(self, **kwargs):
        self.edited = kwargs
        self._done = True

    async def send_message(self, content, *, ephemeral=False):
        self.sent = {"content": content, "ephemeral": ephemeral}
        self._done = True


class FakeMessage:
    def __init__(self):
        self.embeds = [discord.Embed(title="승인 요청 · 작업 #1")]
        self.edited = None

    async def edit(self, **kwargs):
        self.edited = kwargs


class FakeUser:
    display_name = "probe"


class FakeInteraction:
    def __init__(self):
        self.response = FakeResponse()
        self.message = FakeMessage()
        self.user = FakeUser()


class ApprovalButtonTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db_path = bus.DB_PATH
        bus.DB_PATH = Path(self.tmp.name) / "hermes.db"
        bus.init_db()

    def tearDown(self):
        bus.DB_PATH = self.old_db_path
        self.tmp.cleanup()

    def test_set_status_if_pending_only_updates_once(self):
        task_id = bus.add_task("동시 클릭 방지", needs_approval=True)

        self.assertTrue(bus.set_status_if_pending(task_id, "approved"))
        self.assertFalse(bus.set_status_if_pending(task_id, "rejected"))
        self.assertEqual(bus.get_task(task_id)["status"], "approved")

    def test_dynamic_view_custom_ids_match_template(self):
        view = ApprovalView(42)
        custom_ids = [child.custom_id for child in view.children]

        self.assertEqual(
            custom_ids,
            ["hermes:approval:approve:42", "hermes:approval:reject:42"],
        )
        for custom_id in custom_ids:
            self.assertIsNotNone(re.fullmatch(APPROVAL_CUSTOM_ID_TEMPLATE, custom_id))

    def test_dynamic_item_rehydrates_from_custom_id(self):
        match = re.fullmatch(
            APPROVAL_CUSTOM_ID_TEMPLATE,
            "hermes:approval:reject:123",
        )
        button = asyncio.run(ApprovalButton.from_custom_id(None, None, match))

        self.assertEqual(button.action, "reject")
        self.assertEqual(button.task_id, 123)
        self.assertEqual(button.custom_id, "hermes:approval:reject:123")

    def test_callback_approves_pending_task_and_disables_card(self):
        task_id = bus.add_task("승인 카드", needs_approval=True)
        interaction = FakeInteraction()

        asyncio.run(ApprovalButton("approve", task_id).callback(interaction))

        self.assertEqual(bus.get_task(task_id)["status"], "approved")
        self.assertIsNotNone(interaction.response.edited)
        edited_view = interaction.response.edited["view"]
        self.assertTrue(all(child.item.disabled for child in edited_view.children))

    def test_callback_on_processed_task_sends_ephemeral_notice(self):
        task_id = bus.add_task("이미 승인된 카드", needs_approval=True)
        bus.set_status(task_id, "approved")
        interaction = FakeInteraction()

        asyncio.run(ApprovalButton("reject", task_id).callback(interaction))

        self.assertEqual(bus.get_task(task_id)["status"], "approved")
        self.assertEqual(
            interaction.response.sent,
            {
                "content": "이미 처리된 요청입니다. 현재 상태: 🟩 승인됨",
                "ephemeral": True,
            },
        )
        self.assertIsNotNone(interaction.message.edited)
        edited_view = interaction.message.edited["view"]
        self.assertTrue(all(child.item.disabled for child in edited_view.children))


if __name__ == "__main__":
    unittest.main()
