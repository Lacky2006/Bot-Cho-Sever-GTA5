from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks

from .config import Config
from .database import Database
from .transcript import TranscriptService


log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FormField:
    label: str
    placeholder: str
    style: discord.TextStyle = discord.TextStyle.paragraph
    required: bool = True
    max_length: int = 1000


@dataclass(frozen=True, slots=True)
class TicketKind:
    key: str
    label: str
    emoji: str
    colour: discord.ButtonStyle
    fields: tuple[FormField, ...]


KINDS = {
    "support": TicketKind("support", "Hỗ trợ", "🛟", discord.ButtonStyle.primary, (
        FormField("Bạn cần hỗ trợ vấn đề gì?", "Mô tả ngắn vấn đề", discord.TextStyle.short, max_length=200),
        FormField("Nội dung chi tiết", "Hãy cung cấp đầy đủ thông tin để nhân viên hỗ trợ"),
        FormField("ID nhân vật / ID Discord", "Nếu không có, ghi: Không", discord.TextStyle.short, max_length=100),
    )),
    "report": TicketKind("report", "Tố cáo", "🚨", discord.ButtonStyle.danger, (
        FormField("Người bị tố cáo", "Tên hoặc ID người chơi", discord.TextStyle.short, max_length=150),
        FormField("Nội dung vi phạm", "Mô tả hành vi và thời gian xảy ra"),
        FormField("Bằng chứng", "Dán link video/ảnh; có thể gửi file trong ticket", required=False),
    )),
    "donate": TicketKind("donate", "Donate", "💎", discord.ButtonStyle.success, (
        FormField("Tên/ID nhân vật", "Tên nhân vật hoặc ID", discord.TextStyle.short, max_length=150),
        FormField("Gói hoặc vật phẩm", "Bạn muốn đăng ký gói/vật phẩm nào?"),
        FormField("Số tiền dự kiến", "Ví dụ: 500.000 VNĐ", discord.TextStyle.short, max_length=100),
    )),
    "bug": TicketKind("bug", "Báo lỗi", "🐛", discord.ButtonStyle.secondary, (
        FormField("Tên lỗi", "Mô tả lỗi trong một câu", discord.TextStyle.short, max_length=200),
        FormField("Các bước gây ra lỗi", "1. ...\n2. ...\n3. ..."),
        FormField("Kết quả thực tế", "Điều gì đã xảy ra?"),
        FormField("Kết quả mong muốn", "Đúng ra điều gì phải xảy ra?", required=False),
        FormField("Thông tin thêm / bằng chứng", "Phiên bản, thời gian, link; có thể gửi ảnh sau", required=False),
    )),
}


class TicketModal(discord.ui.Modal):
    def __init__(self, service: "TicketService", kind: TicketKind) -> None:
        super().__init__(title=f"Phiếu {kind.label}", custom_id=f"vroleplay:modal:{kind.key}")
        self.service = service
        self.kind = kind
        self.inputs: list[discord.ui.TextInput] = []
        for index, field in enumerate(kind.fields):
            item = discord.ui.TextInput(
                label=field.label,
                placeholder=field.placeholder,
                style=field.style,
                required=field.required,
                max_length=field.max_length,
                custom_id=f"field_{index}",
            )
            self.inputs.append(item)
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        answers = [(field.label, str(item.value)) for field, item in zip(self.kind.fields, self.inputs)]
        await self.service.create(interaction, self.kind, answers)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        log.exception("Lỗi xử lý modal ticket", exc_info=error)
        message = "Không thể tạo ticket. Hãy thử lại hoặc báo quản trị viên."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


class TicketPanelView(discord.ui.View):
    def __init__(self, service: "TicketService") -> None:
        super().__init__(timeout=None)
        self.service = service

    async def open_form(self, interaction: discord.Interaction, key: str) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Nút này chỉ dùng trong máy chủ.", ephemeral=True)
            return
        await interaction.response.send_modal(TicketModal(self.service, KINDS[key]))

    @discord.ui.button(label="Hỗ trợ", emoji="🛟", style=discord.ButtonStyle.primary, custom_id="vroleplay:ticket:support")
    async def support(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_form(interaction, "support")

    @discord.ui.button(label="Tố cáo", emoji="🚨", style=discord.ButtonStyle.danger, custom_id="vroleplay:ticket:report")
    async def report(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_form(interaction, "report")

    @discord.ui.button(label="Donate", emoji="💎", style=discord.ButtonStyle.success, custom_id="vroleplay:ticket:donate")
    async def donate(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_form(interaction, "donate")

    @discord.ui.button(label="Báo lỗi", emoji="🐛", style=discord.ButtonStyle.secondary, custom_id="vroleplay:ticket:bug")
    async def bug(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.open_form(interaction, "bug")


class TicketService:
    def __init__(self, bot: commands.Bot, config: Config, database: Database, transcript: TranscriptService) -> None:
        self.bot = bot
        self.config = config
        self.db = database
        self.transcript = transcript
        self._locks: dict[tuple[int, int], asyncio.Lock] = {}

    async def create(
        self, interaction: discord.Interaction, kind: TicketKind, answers: list[tuple[str, str]]
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild, member = interaction.guild, interaction.user
        lock = self._locks.setdefault((guild.id, member.id), asyncio.Lock())
        async with lock:
            existing = await self.db.find_open_ticket(guild.id, member.id)
            if existing:
                channel = guild.get_channel(existing["channel_id"])
                if channel:
                    await interaction.followup.send(f"Bạn đã có ticket đang mở: {channel.mention}", ephemeral=True)
                    return
                await self.db.close_ticket(existing["channel_id"], datetime.now(timezone.utc).isoformat(), "missing")

            settings = await self.db.get_guild_settings(guild.id)
            category = guild.get_channel(settings.get("ticket_category_id"))
            if not isinstance(category, discord.CategoryChannel):
                await interaction.followup.send("Danh mục ticket chưa sẵn sàng. Hãy báo quản trị viên.", ephemeral=True)
                return
            me = guild.me
            if me is None:
                return
            support_role = guild.get_role(self.config.support_role_id)
            overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite] = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True),
                me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True),
            }
            if support_role:
                overwrites[support_role] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True, manage_messages=True
                )

            clean_name = re.sub(r"[^a-z0-9-]", "", member.name.lower().replace("_", "-"))[:40] or str(member.id)
            channel = await guild.create_text_channel(
                f"{kind.key}-{clean_name}", category=category, overwrites=overwrites,
                topic=f"VROLEPLAY owner={member.id} type={kind.key}",
                reason=f"Ticket {kind.label} của {member}",
            )
            slug = uuid.uuid4().hex
            try:
                await self.db.create_ticket(guild.id, channel.id, member.id, kind.key, slug)
            except Exception:
                await channel.delete(reason="Không thể lưu ticket vào cơ sở dữ liệu")
                raise

            embed = discord.Embed(
                title=f"{kind.emoji} Ticket {kind.label}",
                description=f"Xin chào {member.mention}. Đội ngũ hỗ trợ sẽ phản hồi sớm nhất có thể.",
                colour=discord.Colour.blurple(),
            )
            for label, value in answers:
                embed.add_field(name=label, value=value[:1024] or "Không cung cấp", inline=False)
            embed.set_footer(text=f"Người tạo: {member.display_name} • Đóng bằng +cl")
            mention = support_role.mention if support_role else "@Hỗ trợ (chưa cấu hình role)"
            await channel.send(
                content=f"{member.mention} {mention}", embed=embed,
                allowed_mentions=discord.AllowedMentions(users=True, roles=True, everyone=False),
            )
            await interaction.followup.send(f"Đã tạo ticket: {channel.mention}", ephemeral=True)

    def is_staff(self, member: discord.Member) -> bool:
        return member.guild_permissions.administrator or any(role.id == self.config.support_role_id for role in member.roles)


class TicketCog(commands.Cog):
    def __init__(
        self, bot: commands.Bot, config: Config, database: Database, service: TicketService,
        transcript: TranscriptService,
    ) -> None:
        self.bot = bot
        self.config = config
        self.db = database
        self.service = service
        self.transcript = transcript
        self.cleanup_expired.start()

    def cog_unload(self) -> None:
        self.cleanup_expired.cancel()

    @commands.command(name="cl")
    @commands.guild_only()
    async def close_ticket(self, ctx: commands.Context) -> None:
        if not isinstance(ctx.channel, discord.TextChannel) or not isinstance(ctx.author, discord.Member):
            return
        ticket = await self.db.get_ticket(ctx.channel.id)
        if not ticket:
            await ctx.reply("Lệnh này chỉ dùng trong kênh ticket.", mention_author=False)
            return
        if ticket["status"] != "open":
            await ctx.reply("Ticket này đã được đóng.", mention_author=False)
            return
        if ctx.author.id != ticket["owner_id"] and not self.service.is_staff(ctx.author):
            await ctx.reply("Bạn không có quyền đóng ticket này.", mention_author=False)
            return

        async with ctx.typing():
            await self.transcript.export(ctx.channel, ticket["slug"])
        expires = datetime.now(timezone.utc) + timedelta(days=self.config.retention_days)
        await self.db.close_ticket(ctx.channel.id, expires.isoformat())
        owner = ctx.guild.get_member(ticket["owner_id"])
        if owner:
            await ctx.channel.set_permissions(owner, view_channel=True, send_messages=False, read_message_history=True)
        settings = await self.db.get_guild_settings(ctx.guild.id)
        category = ctx.guild.get_channel(settings.get("closed_category_id"))
        name = ctx.channel.name
        if not name.startswith("closed-"):
            name = f"closed-{name}"[:100]
        await ctx.channel.edit(
            name=name,
            category=category if isinstance(category, discord.CategoryChannel) else None,
            reason=f"Đóng ticket bởi {ctx.author}",
        )
        await ctx.send(
            f"🔒 Ticket đã đóng bởi {ctx.author.mention}. Log sẽ được giữ {self.config.retention_days} ngày.\n"
            f"Xem log: {self.transcript.url(ticket['slug'])}"
        )
        await self._send_log(ctx.guild, ticket, ctx.author, "Đã đóng")

    @commands.command(name="delete")
    @commands.guild_only()
    async def delete_ticket(self, ctx: commands.Context) -> None:
        if not isinstance(ctx.channel, discord.TextChannel) or not isinstance(ctx.author, discord.Member):
            return
        ticket = await self.db.get_ticket(ctx.channel.id)
        if not ticket:
            await ctx.reply("Lệnh này chỉ dùng trong kênh ticket.", mention_author=False)
            return
        if not self.service.is_staff(ctx.author):
            await ctx.reply("Chỉ quản trị viên hoặc role hỗ trợ mới được xóa ticket.", mention_author=False)
            return

        async with ctx.typing():
            await self.transcript.export(ctx.channel, ticket["slug"])
        expires = datetime.now(timezone.utc) + timedelta(days=self.config.retention_days)
        await self.db.close_ticket(ctx.channel.id, expires.isoformat(), "deleted")
        await self._send_log(ctx.guild, ticket, ctx.author, "Đã xóa")
        await ctx.channel.delete(reason=f"Xóa ticket bởi {ctx.author}")

    async def _send_log(
        self, guild: discord.Guild, ticket: dict, actor: discord.Member, action: str
    ) -> None:
        settings = await self.db.get_guild_settings(guild.id)
        channel = guild.get_channel(settings.get("log_channel_id"))
        if not isinstance(channel, discord.TextChannel):
            return
        owner = guild.get_member(ticket["owner_id"])
        owner_name = owner.display_name if owner else f"ID {ticket['owner_id']}"
        embed = discord.Embed(title=f"{action} ticket", colour=discord.Colour.orange())
        embed.add_field(name="Người tạo", value=owner_name)
        embed.add_field(name="Loại", value=ticket["ticket_type"])
        embed.add_field(name="Thực hiện bởi", value=actor.display_name)
        embed.add_field(name="Transcript", value=f"[Xem log trực tuyến]({self.transcript.url(ticket['slug'])})", inline=False)
        message = await channel.send(embed=embed)
        await self.db.execute("UPDATE tickets SET log_message_id = ? WHERE channel_id = ?", (message.id, ticket["channel_id"]))

    @tasks.loop(hours=1)
    async def cleanup_expired(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        expired = await self.db.fetchall(
            "SELECT * FROM tickets WHERE expires_at IS NOT NULL AND expires_at <= ? AND status != 'expired'", (now,)
        )
        for ticket in expired:
            guild = self.bot.get_guild(ticket["guild_id"])
            if guild:
                channel = guild.get_channel(ticket["channel_id"])
                if isinstance(channel, discord.TextChannel):
                    try:
                        await channel.delete(reason="Ticket đã hết hạn lưu trữ")
                    except discord.HTTPException:
                        log.warning("Không thể xóa kênh ticket hết hạn %s", channel.id)
                        continue
                if ticket.get("log_message_id"):
                    settings = await self.db.get_guild_settings(guild.id)
                    log_channel = guild.get_channel(settings.get("log_channel_id"))
                    if isinstance(log_channel, discord.TextChannel):
                        try:
                            message = await log_channel.fetch_message(ticket["log_message_id"])
                            await message.delete()
                        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                            pass
            self.transcript.delete(ticket["slug"])
            await self.db.execute("UPDATE tickets SET status = 'expired' WHERE id = ?", (ticket["id"],))

    @cleanup_expired.before_loop
    async def before_cleanup(self) -> None:
        await self.bot.wait_until_ready()

