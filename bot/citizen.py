from __future__ import annotations

import json
import logging

import discord
from discord.ext import commands

from .config import Config
from .database import Database


log = logging.getLogger(__name__)
QUESTIONS = (
    "1/5. Họ và Tên? Năm sinh?",
    "2/5. Bạn đã bao giờ tham gia thành phố Roleplay bao giờ chưa?",
    "3/5. Roleplay là gì?",
    "4/5. MG (Meta Gaming) là gì? Hãy cho 1 ví dụ cụ thể mà bạn biết.",
    "5/5. Bạn có đồng ý với quy tắc và bộ luật thành phố đưa ra khi vào thành phố không?",
)


class CitizenStartView(discord.ui.View):
    def __init__(self, cog: "CitizenCog", guild_id: int) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.children[0].custom_id = f"vroleplay:citizen:start:{guild_id}"

    @discord.ui.button(
        label="Start",
        emoji="📝",
        style=discord.ButtonStyle.success,
        custom_id="vroleplay:citizen:start",
    )
    async def start(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.cog.begin_application(interaction, self.guild_id)


class CitizenPanelView(discord.ui.View):
    def __init__(self, cog: "CitizenCog") -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Verified Citizen",
        emoji="🏙️",
        style=discord.ButtonStyle.primary,
        custom_id="vroleplay:citizen:open",
    )
    async def open_dm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Nút này chỉ dùng trong máy chủ.", ephemeral=True)
            return
        await self.cog.send_start_dm(interaction)


class CitizenReviewView(discord.ui.View):
    def __init__(self, cog: "CitizenCog", application_id: int) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.application_id = application_id
        approve = discord.ui.Button(
            label="Duyệt", emoji="✅", style=discord.ButtonStyle.success,
            custom_id=f"vroleplay:citizen:approve:{application_id}",
        )
        reject = discord.ui.Button(
            label="Từ chối", emoji="❌", style=discord.ButtonStyle.danger,
            custom_id=f"vroleplay:citizen:reject:{application_id}",
        )
        approve.callback = self.approve
        reject.callback = self.reject
        self.add_item(approve)
        self.add_item(reject)

    async def _staff_check(self, interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member) or not self.cog.is_staff(interaction.user):
            await interaction.response.send_message("Chỉ nhân viên hỗ trợ mới được xử lý đơn Citizen.", ephemeral=True)
            return False
        return True

    async def approve(self, interaction: discord.Interaction) -> None:
        if not await self._staff_check(interaction):
            return
        application = await self.cog.db.get_citizen_application(self.application_id)
        if not application or application["status"] != "pending":
            await interaction.response.send_message("Đơn này đã được xử lý hoặc không còn tồn tại.", ephemeral=True)
            return
        guild = interaction.guild
        if not guild or guild.id != application["guild_id"]:
            await interaction.response.send_message("Không tìm thấy server của đơn này.", ephemeral=True)
            return
        role = guild.get_role(self.cog.config.citizen_role_id)
        member = guild.get_member(application["user_id"])
        if not role or not member:
            await interaction.response.send_message("Không tìm thấy role Citizen hoặc thành viên.", ephemeral=True)
            return
        try:
            await member.add_roles(role, reason=f"Citizen được duyệt bởi {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message(
                "Bot chưa thể cấp role. Hãy đưa role bot lên cao hơn role Citizen.", ephemeral=True
            )
            return
        await self.cog.db.review_citizen_application(
            self.application_id, interaction.user.id, "approved"
        )
        await interaction.response.edit_message(
            content=f"✅ **Đã duyệt bởi {interaction.user.display_name}** — role {role.mention} đã được cấp.",
            view=None,
        )
        try:
            await member.send(f"Chúc mừng! Đơn Verified Citizen của bạn đã được {interaction.user.display_name} duyệt và bạn đã nhận role {role.name}.")
        except discord.Forbidden:
            pass

    async def reject(self, interaction: discord.Interaction) -> None:
        if not await self._staff_check(interaction):
            return
        application = await self.cog.db.get_citizen_application(self.application_id)
        if not application or application["status"] != "pending":
            await interaction.response.send_message("Đơn này đã được xử lý hoặc không còn tồn tại.", ephemeral=True)
            return
        await interaction.response.send_modal(CitizenRejectModal(self.cog, self.application_id))


class CitizenRejectModal(discord.ui.Modal, title="Lý do từ chối Citizen"):
    reason = discord.ui.TextInput(
        label="Lý do từ chối",
        placeholder="Nhập lý do để gửi cho người đăng ký",
        style=discord.TextStyle.paragraph,
        min_length=3,
        max_length=1000,
        custom_id="reason",
    )

    def __init__(self, cog: "CitizenCog", application_id: int) -> None:
        super().__init__(custom_id=f"vroleplay:citizen:reason:{application_id}")
        self.cog = cog
        self.application_id = application_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not self.cog.is_staff(interaction.user):
            await interaction.response.send_message("Chỉ nhân viên hỗ trợ mới được xử lý đơn Citizen.", ephemeral=True)
            return
        application = await self.cog.db.get_citizen_application(self.application_id)
        if not application or application["status"] != "pending":
            await interaction.response.send_message("Đơn này đã được xử lý.", ephemeral=True)
            return
        reason = str(self.reason.value).strip()
        await self.cog.db.review_citizen_application(
            self.application_id, interaction.user.id, "rejected", reason
        )
        await interaction.response.send_message("Đã từ chối đơn Citizen và lưu lý do.", ephemeral=True)
        await self.cog.finish_log(application, interaction.user, "Từ chối", reason)
        user = self.cog.bot.get_user(application["user_id"])
        if user:
            try:
                await user.send(f"Đơn Verified Citizen của bạn đã bị từ chối. Lý do: {reason}")
            except discord.Forbidden:
                pass


class CitizenCog(commands.Cog):
    def __init__(self, bot: commands.Bot, config: Config, database: Database) -> None:
        self.bot = bot
        self.config = config
        self.db = database
        self.panel_view = CitizenPanelView(self)

    async def restore_review_views(self) -> None:
        for application in await self.db.pending_citizen_applications():
            if application.get("log_message_id"):
                self.bot.add_view(
                    CitizenReviewView(self, application["id"]),
                    message_id=application["log_message_id"],
                )

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        if interaction.type is not discord.InteractionType.component or not interaction.data:
            return
        custom_id = interaction.data.get("custom_id", "")
        if custom_id == "vroleplay:citizen:open":
            await self.send_start_dm(interaction)
        elif custom_id.startswith("vroleplay:citizen:start:"):
            try:
                guild_id = int(custom_id.rsplit(":", 1)[1])
            except ValueError:
                await interaction.response.send_message("Không đọc được mã server trong nút Start.", ephemeral=True)
                return
            await self.begin_application(interaction, guild_id)

    async def send_start_dm(self, interaction: discord.Interaction) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message("Nút này chỉ dùng trong máy chủ.", ephemeral=True)
            return
        try:
            dm = interaction.user.dm_channel or await interaction.user.create_dm()
            embed = discord.Embed(
                title="Bắt đầu đăng ký Citizen",
                description="Nhấn vào đây để bắt đầu đăng ký Citizen. Bot sẽ lần lượt gửi 5 câu hỏi trong DM.",
                colour=discord.Colour.magenta(),
            )
            await dm.send(embed=embed, view=CitizenStartView(self, interaction.guild_id))
            log.info("Đã gửi DM bắt đầu Citizen cho user_id=%s guild_id=%s", interaction.user.id, interaction.guild_id)
        except discord.Forbidden:
            log.warning("Không thể gửi DM Citizen cho user_id=%s", interaction.user.id)
            await interaction.response.send_message(
                "Mình không gửi được DM. Hãy bật tin nhắn riêng từ thành viên server rồi thử lại.",
                ephemeral=True,
            )
            return
        if not interaction.response.is_done():
            await interaction.response.send_message("Mình đã gửi hướng dẫn vào DM cho bạn.", ephemeral=True)

    def is_staff(self, member: discord.Member) -> bool:
        return member.guild_permissions.administrator or any(
            role.id == self.config.support_role_id for role in member.roles
        )

    async def begin_application(self, interaction: discord.Interaction, guild_id: int) -> None:
        user = interaction.user
        if not isinstance(user, discord.User):
            await interaction.response.send_message("Không lấy được thông tin server.", ephemeral=True)
            return
        log.info("Bắt đầu hỏi Citizen user_id=%s guild_id=%s", user.id, guild_id)
        existing = await self.db.pending_citizen_application(guild_id, user.id)
        if existing:
            await interaction.response.send_message("Bạn đang có đơn Citizen chờ duyệt.")
            return
        await interaction.response.send_message(
            "Bắt đầu đăng ký Citizen. Hãy trả lời từng câu hỏi ngay trong DM này. "
            "Mỗi câu có tối đa 10 phút để trả lời."
        )
        answers: list[str] = []
        try:
            dm = user.dm_channel or await user.create_dm()
            for question in QUESTIONS:
                await dm.send(question)
                reply = await self.bot.wait_for(
                    "message",
                    timeout=600,
                    check=lambda message: message.author.id == user.id and message.channel.id == dm.id,
                )
                answer = reply.content.strip()
                if not answer:
                    await dm.send("Mình chưa nhận được nội dung. Hãy nhấn Start để bắt đầu lại.")
                    return
                answers.append(answer[:4000])
        except TimeoutError:
            try:
                await user.send("Đã hết 10 phút chờ trả lời. Hãy nhấn Start để bắt đầu đăng ký lại.")
            except discord.Forbidden:
                pass
            return
        except discord.Forbidden:
            return

        application_id = await self.db.create_citizen_application(
            guild_id, user.id, json.dumps(answers, ensure_ascii=False)
        )
        application = await self.db.get_citizen_application(application_id)
        if application:
            await self.send_application_log(guild_id, application)
        try:
            await user.send("Đã nhận đủ câu trả lời! Đơn của bạn đã được gửi đến đội ngũ xét duyệt.")
        except discord.Forbidden:
            pass

    async def send_application_log(self, guild_id: int, application: dict) -> None:
        settings = await self.db.get_guild_settings(guild_id)
        channel = self.bot.get_channel(settings.get("citizen_log_channel_id"))
        if not isinstance(channel, discord.TextChannel):
            return
        guild = channel.guild
        member = guild.get_member(application["user_id"])
        user_label = member.display_name if member else f"ID {application['user_id']}"
        answers = json.loads(application["answers_json"])
        embed = discord.Embed(
            title=f"Đơn Verified Citizen • {user_label}",
            description=f"Người đăng ký: {member.mention if member else user_label}",
            colour=discord.Colour.gold(),
        )
        for question, answer in zip(QUESTIONS, answers):
            embed.add_field(name=question, value=answer[:1024], inline=False)
        embed.set_footer(text=f"Đơn #{application['id']} • Đang chờ xét duyệt")
        message = await channel.send(embed=embed, view=CitizenReviewView(self, application["id"]))
        await self.db.execute(
            "UPDATE citizen_applications SET log_message_id = ? WHERE id = ?",
            (message.id, application["id"]),
        )

    async def finish_log(
        self, application: dict, reviewer: discord.Member, decision: str, reason: str | None = None
    ) -> None:
        settings = await self.db.get_guild_settings(application["guild_id"])
        channel = self.bot.get_channel(settings.get("citizen_log_channel_id"))
        if not isinstance(channel, discord.TextChannel) or not application.get("log_message_id"):
            return
        try:
            message = await channel.fetch_message(application["log_message_id"])
        except (discord.NotFound, discord.Forbidden):
            return
        text = f"❌ **Từ chối bởi {reviewer.display_name}**"
        if reason:
            text += f"\n**Lý do:** {reason}"
        await message.edit(content=text, view=None)


async def restore_citizen_views(bot: commands.Bot, cog: CitizenCog) -> None:
    await cog.restore_review_views()

