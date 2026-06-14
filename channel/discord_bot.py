"""Discord 채널 봇: 명령 접수 + 승인(HITL) + 알림.

실행:
    python -m channel.discord_bot

기능:
  /ping            봇 생존 확인
  /task            작업 큐에 등록 (needs_approval 선택)
  /tasks           최근 작업 목록
  버튼 승인 흐름    needs_approval 작업이 큐에 들어오면 승인 채널에
                   [승인]/[거부] 버튼 카드를 자동 게시. 클릭 시 SQLite 상태 갱신.

Hermes(Claude Code) 쪽 사용 예:
    tid=$(python -m hermes.bus add "main 브랜치에 v0.2 배포" --approve)
    python -m hermes.bus wait $tid --timeout 600   # approved/rejected 반환

승인/거부 버튼은 discord.py DynamicItem custom_id 라우팅을 사용하므로
봇 재시작 후에도 기존 승인 카드의 버튼 인터랙션을 처리할 수 있다.
"""
import asyncio
import logging
import re

import discord
from discord import app_commands
from discord.ext import tasks

from hermes import bus
from hermes.config import (
    DISCORD_APPROVAL_CHANNEL_ID,
    DISCORD_BOT_TOKEN,
    DISCORD_GUILD_ID,
)

log = logging.getLogger("hermes.discord")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")

intents = discord.Intents.default()

STATUS_LABEL = {
    "queued": "🟦 대기",
    "pending": "🟨 승인 대기",
    "approved": "🟩 승인됨",
    "rejected": "🟥 거부됨",
    "running": "⏳ 실행 중",
    "done": "✅ 완료",
    "failed": "❌ 실패",
}

APPROVAL_CUSTOM_ID_TEMPLATE = (
    r"hermes:approval:(?P<action>approve|reject):(?P<task_id>\d+)"
)


def _approval_custom_id(action: str, task_id: int) -> str:
    return f"hermes:approval:{action}:{task_id}"


def _approval_color(status: str) -> discord.Color:
    if status == "approved":
        return discord.Color.green()
    if status == "rejected":
        return discord.Color.red()
    return discord.Color.light_grey()


def _approval_embed_from_message(
    interaction: discord.Interaction,
    task_id: int,
) -> discord.Embed:
    if interaction.message and interaction.message.embeds:
        return interaction.message.embeds[0]
    return discord.Embed(title=f"승인 요청 · 작업 #{task_id}")


class ApprovalButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=APPROVAL_CUSTOM_ID_TEMPLATE,
):
    """재시작 후에도 custom_id에서 작업 ID와 액션을 복원하는 버튼."""

    def __init__(self, action: str, task_id: int, *, disabled: bool = False):
        self.action = action
        self.task_id = task_id

        if action == "approve":
            label = "승인"
            style = discord.ButtonStyle.success
            emoji = "✅"
        else:
            label = "거부"
            style = discord.ButtonStyle.danger
            emoji = "✋"

        super().__init__(
            discord.ui.Button(
                label=label,
                style=style,
                emoji=emoji,
                custom_id=_approval_custom_id(action, task_id),
                disabled=disabled,
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match: re.Match[str],
    ) -> "ApprovalButton":
        return cls(match.group("action"), int(match.group("task_id")))

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.action == "approve":
            await self._finish(interaction, "approved")
        else:
            await self._finish(interaction, "rejected")

    async def _finish(self, interaction: discord.Interaction, status: str) -> None:
        if bus.set_status_if_pending(self.task_id, status):
            embed = _approval_embed_from_message(interaction, self.task_id)
            embed.colour = _approval_color(status)
            embed.set_footer(
                text=f"{STATUS_LABEL[status]} · {interaction.user.display_name}"
            )
            await interaction.response.edit_message(
                embed=embed,
                view=ApprovalView(self.task_id, disabled=True),
            )
            return

        task = bus.get_task(self.task_id)
        current_status = task["status"] if task else "missing"
        current_label = STATUS_LABEL.get(current_status, "삭제됨")

        await interaction.response.send_message(
            f"이미 처리된 요청입니다. 현재 상태: {current_label}",
            ephemeral=True,
        )

        if interaction.message:
            embed = _approval_embed_from_message(interaction, self.task_id)
            embed.colour = _approval_color(current_status)
            embed.set_footer(text=f"{current_label} · 이미 처리된 요청")
            await interaction.message.edit(
                embed=embed,
                view=ApprovalView(self.task_id, disabled=True),
            )


class ApprovalView(discord.ui.View):
    """승인/거부 버튼. DynamicItem custom_id로 재시작 후에도 동작한다."""

    def __init__(self, task_id: int, *, disabled: bool = False):
        super().__init__(timeout=None)
        self.task_id = task_id
        self.add_item(ApprovalButton("approve", task_id, disabled=disabled))
        self.add_item(ApprovalButton("reject", task_id, disabled=disabled))


def approval_embed(task: dict) -> discord.Embed:
    e = discord.Embed(
        title=f"승인 요청 · 작업 #{task['id']}",
        description=task["title"],
        color=discord.Color.orange(),
    )
    if task.get("body"):
        e.add_field(name="상세", value=task["body"][:1000], inline=False)
    e.add_field(name="종류", value=task.get("kind", "general"), inline=True)
    e.add_field(name="등록 시각", value=task.get("created_at", "-"), inline=True)
    return e


class HermesBot(discord.Client):
    def __init__(self) -> None:
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        bus.init_db()
        self.add_dynamic_items(ApprovalButton)
        if DISCORD_GUILD_ID:
            guild = discord.Object(id=DISCORD_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()
        approval_poller.start()

    async def on_ready(self) -> None:
        log.info("로그인: %s (guild=%s)", self.user, DISCORD_GUILD_ID or "global")


bot = HermesBot()


@tasks.loop(seconds=5)
async def approval_poller() -> None:
    """CLI/Hermes가 등록한 승인 대기 작업을 승인 채널에 카드로 게시."""
    if not DISCORD_APPROVAL_CHANNEL_ID:
        return
    pending = bus.unposted_approvals()
    if not pending:
        return
    channel = bot.get_channel(DISCORD_APPROVAL_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(DISCORD_APPROVAL_CHANNEL_ID)
        except discord.DiscordException as e:
            log.warning("승인 채널 조회 실패: %s", e)
            return
    for t in pending:
        await channel.send(embed=approval_embed(t), view=ApprovalView(t["id"]))
        bus.mark_posted(t["id"])
        log.info("승인 카드 게시: #%s %s", t["id"], t["title"])


@approval_poller.before_loop
async def _wait_ready() -> None:
    await bot.wait_until_ready()


@bot.tree.command(name="ping", description="봇 생존 확인")
async def ping(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(
        f"🏛️ Hermes 채널 온라인 (지연 {bot.latency * 1000:.0f}ms)", ephemeral=True
    )


@bot.tree.command(name="task", description="작업을 큐에 등록")
@app_commands.describe(
    title="작업 제목",
    body="상세 설명 (선택)",
    needs_approval="승인 버튼 카드를 게시할지 여부",
)
async def task_cmd(interaction: discord.Interaction, title: str,
                   body: str = "", needs_approval: bool = False) -> None:
    tid = bus.add_task(title=title, body=body, needs_approval=needs_approval)
    note = " · 승인 카드가 곧 게시됩니다" if needs_approval else ""
    await interaction.response.send_message(f"📥 작업 #{tid} 등록: {title}{note}")


@bot.tree.command(name="tasks", description="최근 작업 목록")
async def tasks_cmd(interaction: discord.Interaction) -> None:
    rows = bus.list_tasks(limit=10)
    if not rows:
        await interaction.response.send_message("큐가 비어 있습니다.", ephemeral=True)
        return
    e = discord.Embed(title="최근 작업 10건", color=discord.Color.blurple())
    for t in rows:
        label = STATUS_LABEL.get(t["status"], t["status"])
        e.add_field(name=f"#{t['id']} {t['title'][:60]}",
                    value=f"{label} · {t['kind']} · {t['created_at']}",
                    inline=False)
    await interaction.response.send_message(embed=e, ephemeral=True)


def main() -> None:
    if not DISCORD_BOT_TOKEN:
        raise SystemExit(
            ".env의 DISCORD_BOT_TOKEN이 비어 있습니다. "
            "README의 Discord 봇 설정 절차를 먼저 진행하세요."
        )
    bot.run(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
