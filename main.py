from __future__ import annotations

import logging

import discord
from discord.ext import commands

from bot.config import Config
from bot.citizen import CitizenCog, restore_citizen_views
from bot.database import Database
from bot.events import CommunityEvents
from bot.setup_service import GuildSetupService
from bot.tickets import TicketCog, TicketPanelView, TicketService
from bot.transcript import TranscriptService
from bot.web_server import TranscriptWebServer


class VRoleplayBot(commands.Bot):
    def __init__(self, config: Config) -> None:
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(
            command_prefix=config.command_prefix,
            intents=intents,
            help_command=None,
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=True, users=True),
        )
        self.config = config
        self.database = Database(config.database_path)
        self.transcripts = TranscriptService(config)
        self.web = TranscriptWebServer(config)
        self.tickets = TicketService(self, config, self.database, self.transcripts)
        self.panel_view = TicketPanelView(self.tickets)
        self.guild_setup = GuildSetupService(self, config, self.database)
        self.citizen = CitizenCog(self, config, self.database)
        self.community_events = CommunityEvents(self, self.config, self.database)
        self.ticket_cog = TicketCog(self, self.config, self.database, self.tickets, self.transcripts)
        self._new_citizen_role_synced: set[int] = set()

    async def setup_hook(self) -> None:
        await self.database.initialize()
        self.add_view(self.panel_view)
        await self.add_cog(self.citizen)
        await restore_citizen_views(self, self.citizen)
        await self.add_cog(self.community_events)
        await self.add_cog(self.ticket_cog)
        await self.web.start()

    async def on_ready(self) -> None:
        if self.user is None:
            return
        logging.getLogger(__name__).info("Đăng nhập: %s (%s)", self.user, self.user.id)
        for guild in self.guilds:
            try:
                await self.guild_setup.ensure_guild(guild, self.panel_view, self.citizen.panel_view)
            except discord.Forbidden:
                logging.getLogger(__name__).exception(
                    "Bot thiếu quyền để thiết lập máy chủ %s (%s)", guild.name, guild.id
                )
            except discord.HTTPException:
                logging.getLogger(__name__).exception("Không thể thiết lập máy chủ %s", guild.id)
            try:
                await self.ticket_cog.remove_legacy_closed_category(guild)
            except discord.Forbidden:
                logging.getLogger(__name__).exception(
                    "Bot thiếu quyền để dọn phòng ticket cũ trong máy chủ %s (%s)", guild.name, guild.id
                )
            except discord.HTTPException:
                logging.getLogger(__name__).exception("Không thể dọn phòng ticket cũ trong máy chủ %s", guild.id)
            if guild.id not in self._new_citizen_role_synced:
                await self.assign_new_citizen_to_existing_members(guild)

    async def assign_new_citizen_to_existing_members(self, guild: discord.Guild) -> None:
        role = guild.get_role(self.config.new_citizen_role_id)
        if role is None:
            logging.getLogger(__name__).error(
                "Không tìm thấy role New Citizen (%s) trong server %s",
                self.config.new_citizen_role_id,
                guild.id,
            )
            return
        try:
            async for member in guild.fetch_members(limit=None):
                await self.community_events.assign_new_citizen_role(member)
        except discord.Forbidden:
            logging.getLogger(__name__).exception(
                "Không thể cấp role New Citizen hàng loạt cho server %s. Kiểm tra Members Intent và thứ tự role.",
                guild.id,
            )
            return
        self._new_citizen_role_synced.add(guild.id)

    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self.guild_setup.ensure_guild(guild, self.panel_view, self.citizen.panel_view)
        await self.ticket_cog.remove_legacy_closed_category(guild)
        await self.assign_new_citizen_to_existing_members(guild)

    async def close(self) -> None:
        await self.web.stop()
        await super().close()

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.NoPrivateMessage):
            await ctx.reply("Lệnh này chỉ dùng trong máy chủ.", mention_author=False)
            return
        logging.getLogger(__name__).exception("Lỗi lệnh %s", ctx.command, exc_info=error)
        await ctx.reply("Có lỗi xảy ra khi chạy lệnh. Hãy kiểm tra log của bot.", mention_author=False)

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    config = Config.load()
    VRoleplayBot(config).run(config.token, log_handler=None)


if __name__ == "__main__":
    main()

