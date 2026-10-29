from __future__ import annotations

import logging

import discord
from discord.ext import commands

from .config import Config
from .database import Database


log = logging.getLogger(__name__)


class CommunityEvents(commands.Cog):
    def __init__(self, bot: commands.Bot, config: Config, database: Database) -> None:
        self.bot = bot
        self.config = config
        self.db = database

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        if interaction.type is discord.InteractionType.component:
            custom_id = interaction.data.get("custom_id", "unknown") if interaction.data else "unknown"
            log.info(
                "Đã nhận tương tác nút: custom_id=%s user_id=%s guild_id=%s channel_id=%s",
                custom_id,
                interaction.user.id,
                interaction.guild_id,
                interaction.channel_id,
            )

    async def assign_new_citizen_role(self, member: discord.Member) -> None:
        role = member.guild.get_role(self.config.new_citizen_role_id)
        if not role:
            return
        if role not in member.roles:
            try:
                await member.add_roles(role, reason="Cấp role mặc định New Citizen")
            except discord.Forbidden:
                return

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        await self.assign_new_citizen_role(member)
        settings = await self.db.get_guild_settings(member.guild.id)
        channel = member.guild.get_channel(settings.get("welcome_channel_id"))
        if not isinstance(channel, discord.TextChannel):
            return
        embed = discord.Embed(
            title="Chào mừng đến V Roleplay Community",
            description=f"Chào mừng {member.mention} đến với thành phố!",
            colour=discord.Colour.green(),
        )
        rules = f"[Xem luật thành phố]({self.config.rules_url})" if self.config.rules_url else "Chưa cấu hình link"
        citizen_id = settings.get("citizen_panel_channel_id")
        whitelist = f"<#{citizen_id}>" if citizen_id else (
            f"[Đăng ký whitelist]({self.config.whitelist_url})" if self.config.whitelist_url else "Chưa cấu hình link"
        )
        panel_id = settings.get("panel_channel_id")
        support = f"<#{panel_id}>" if panel_id else "Kênh hỗ trợ ticket"
        embed.add_field(name="📜 Luật thành phố", value=rules, inline=False)
        embed.add_field(name="📝 Đăng ký whitelist", value=whitelist, inline=False)
        embed.add_field(name="🎫 Ticket hỗ trợ", value=support, inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        if self.config.welcome_image_url:
            embed.set_image(url=self.config.welcome_image_url)
        await channel.send(content=member.mention, embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        settings = await self.db.get_guild_settings(member.guild.id)
        channel = member.guild.get_channel(settings.get("goodbye_channel_id"))
        if not isinstance(channel, discord.TextChannel):
            return
        embed = discord.Embed(
            title="Tạm biệt!",
            description=f"**{member.display_name}** đã rời V Roleplay Community.",
            colour=discord.Colour.red(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)

