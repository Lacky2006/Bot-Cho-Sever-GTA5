from __future__ import annotations

import asyncio
import logging

import discord

from .config import Config
from .database import Database


log = logging.getLogger(__name__)


class GuildSetupService:
    def __init__(self, bot: discord.Client, config: Config, database: Database) -> None:
        self.bot = bot
        self.config = config
        self.db = database
        self._locks: dict[int, asyncio.Lock] = {}

    async def ensure_guild(
        self, guild: discord.Guild, panel_view: discord.ui.View, citizen_view: discord.ui.View
    ) -> None:
        lock = self._locks.setdefault(guild.id, asyncio.Lock())
        async with lock:
            settings = await self.db.get_guild_settings(guild.id)
            me = guild.me
            if me is None:
                return

            welcome = await self._text_channel(guild, settings.get("welcome_channel_id"), "welcome")
            goodbye = await self._text_channel(guild, settings.get("goodbye_channel_id"), "byebye")
            ticket_category = await self._category(guild, settings.get("ticket_category_id"), "🎫 HỖ TRỢ TICKET")
            closed_category = await self._category(guild, settings.get("closed_category_id"), "🔒 TICKET ĐÃ ĐÓNG")

            public_overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=False),
                me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True),
            }
            panel = await self._text_channel(
                guild, settings.get("panel_channel_id"), "hỗ-trợ-ticket",
                category=ticket_category, overwrites=public_overwrites,
            )

            private_overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True),
            }
            support_role = guild.get_role(self.config.support_role_id)
            if support_role:
                private_overwrites[support_role] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True
                )
            log_channel = await self._text_channel(
                guild, settings.get("log_channel_id"), "log-ticket",
                category=ticket_category, overwrites=private_overwrites,
            )

            await self.db.update_guild_settings(
                guild.id,
                welcome_channel_id=welcome.id,
                goodbye_channel_id=goodbye.id,
                ticket_category_id=ticket_category.id,
                closed_category_id=closed_category.id,
                panel_channel_id=panel.id,
                log_channel_id=log_channel.id,
            )
            await self._ensure_panel(panel, settings.get("panel_message_id"), panel_view)
            citizen_panel = await self._text_channel(
                guild,
                settings.get("citizen_panel_channel_id"),
                "đăng-ký-citizen",
                overwrites=public_overwrites,
            )
            citizen_log = await self._text_channel(
                guild,
                settings.get("citizen_log_channel_id"),
                "log-citizen",
                category=ticket_category,
                overwrites=private_overwrites,
            )
            await self.db.update_guild_settings(
                guild.id,
                citizen_panel_channel_id=citizen_panel.id,
                citizen_log_channel_id=citizen_log.id,
            )
            await self._ensure_citizen_panel(
                citizen_panel, settings.get("citizen_panel_message_id"), citizen_view
            )

    async def _category(self, guild: discord.Guild, channel_id: int | None, name: str) -> discord.CategoryChannel:
        channel = guild.get_channel(channel_id) if channel_id else None
        if isinstance(channel, discord.CategoryChannel):
            return channel
        existing = discord.utils.get(guild.categories, name=name)
        return existing or await guild.create_category(name, reason="Thiết lập tự động V Roleplay Bot")

    async def _text_channel(
        self,
        guild: discord.Guild,
        channel_id: int | None,
        name: str,
        *,
        category: discord.CategoryChannel | None = None,
        overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite] | None = None,
    ) -> discord.TextChannel:
        channel = guild.get_channel(channel_id) if channel_id else None
        if isinstance(channel, discord.TextChannel):
            if overwrites is not None:
                await channel.edit(category=category, overwrites=overwrites, reason="Đồng bộ cấu hình V Roleplay Bot")
            return channel
        existing = discord.utils.get(guild.text_channels, name=name)
        if existing:
            if overwrites is not None:
                await existing.edit(category=category, overwrites=overwrites, reason="Đồng bộ cấu hình V Roleplay Bot")
            return existing
        return await guild.create_text_channel(
            name, category=category, overwrites=overwrites,
            reason="Thiết lập tự động V Roleplay Bot",
        )

    async def _ensure_panel(
        self, channel: discord.TextChannel, message_id: int | None, view: discord.ui.View
    ) -> None:
        if message_id:
            try:
                message = await channel.fetch_message(message_id)
                if self.bot.user and message.author.id == self.bot.user.id:
                    return
            except (discord.NotFound, discord.Forbidden):
                pass

        embed = discord.Embed(
            title="Trung tâm hỗ trợ V Roleplay",
            description="Bạn đang cần hỗ trợ? Hãy nhấn chọn loại hỗ trợ tại đây.",
            colour=discord.Colour.gold(),
        )
        embed.add_field(name="Lưu ý", value="Mỗi người chỉ được mở một ticket cùng lúc.", inline=False)
        if self.config.ticket_image_url:
            embed.set_image(url=self.config.ticket_image_url)
        message = await channel.send(embed=embed, view=view)
        await self.db.update_guild_settings(channel.guild.id, panel_message_id=message.id)
        log.info("Đã tạo panel ticket tại guild %s", channel.guild.id)

    async def _ensure_citizen_panel(
        self, channel: discord.TextChannel, message_id: int | None, view: discord.ui.View
    ) -> None:
        if message_id:
            try:
                message = await channel.fetch_message(message_id)
                if self.bot.user and message.author.id == self.bot.user.id:
                    return
            except (discord.NotFound, discord.Forbidden):
                pass

        embed = discord.Embed(
            title="Đăng ký Verified Citizen tại đây",
            description="Nhấn nút bên dưới để nhận hướng dẫn và bắt đầu đăng ký qua tin nhắn riêng.",
            colour=discord.Colour.magenta(),
        )
        image_path = self.config.database_path.parent.parent / "assets" / "citizen-banner.png"
        if image_path.is_file():
            embed.set_image(url="attachment://citizen-banner.png")
            message = await channel.send(
                embed=embed,
                view=view,
                file=discord.File(image_path, filename="citizen-banner.png"),
            )
        else:
            message = await channel.send(embed=embed, view=view)
        await self.db.update_guild_settings(channel.guild.id, citizen_panel_message_id=message.id)
        log.info("Đã tạo panel Citizen tại guild %s", channel.guild.id)

