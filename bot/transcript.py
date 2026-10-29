from __future__ import annotations

import html
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import discord

from .config import Config


SAFE_FILE = re.compile(r"[^a-zA-Z0-9._-]+")


class TranscriptService:
    def __init__(self, config: Config) -> None:
        self.config = config

    async def export(self, channel: discord.TextChannel, slug: str) -> Path:
        target = self.config.transcript_dir / slug
        assets = target / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        rows: list[str] = []
        avatar_cache: dict[int, str] = {}

        async for message in channel.history(limit=None, oldest_first=True):
            author_name = html.escape(getattr(message.author, "display_name", message.author.name))
            avatar_url = await self._save_avatar(message.author, assets, avatar_cache)
            content = html.escape(message.clean_content).replace("\n", "<br>")
            embeds = self._embeds(message)
            attachments = await self._attachments(message, assets)
            timestamp = message.created_at.astimezone(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
            edited = " <span class='edited'>(đã sửa)</span>" if message.edited_at else ""
            rows.append(
                f"<article class='message'><img class='avatar' src='{html.escape(avatar_url)}' alt=''>"
                f"<div class='body'><div><strong>{author_name}</strong> "
                f"<time>{timestamp}</time>{edited}</div>"
                f"<div class='content'>{content}</div>{embeds}{attachments}</div></article>"
            )

        index = target / "index.html"
        index.write_text(self._document(channel, "\n".join(rows)), encoding="utf-8")
        return index

    async def _save_avatar(
        self, author: discord.User | discord.Member, assets: Path, cache: dict[int, str]
    ) -> str:
        if author.id in cache:
            return cache[author.id]
        filename = f"avatar-{author.id}.png"
        try:
            await author.display_avatar.save(assets / filename)
            value = f"assets/{filename}"
        except (discord.HTTPException, OSError):
            value = str(author.display_avatar.url)
        cache[author.id] = value
        return value

    async def _attachments(self, message: discord.Message, assets: Path) -> str:
        blocks: list[str] = []
        for attachment in message.attachments:
            safe_name = SAFE_FILE.sub("_", attachment.filename)[:120] or "file"
            filename = f"{message.id}-{attachment.id}-{safe_name}"
            if attachment.size > self.config.max_attachment_bytes:
                blocks.append(f"<div class='file'>📎 {html.escape(attachment.filename)} (quá giới hạn lưu)</div>")
                continue
            try:
                await attachment.save(assets / filename, use_cached=True)
                rel = f"assets/{filename}"
                if attachment.content_type and attachment.content_type.startswith("image/"):
                    blocks.append(f"<a href='{rel}' target='_blank'><img class='attachment' src='{rel}' alt='{html.escape(attachment.filename)}'></a>")
                elif attachment.content_type and attachment.content_type.startswith("video/"):
                    blocks.append(f"<video class='attachment' controls src='{rel}'></video>")
                else:
                    blocks.append(f"<div class='file'>📎 <a href='{rel}'>{html.escape(attachment.filename)}</a></div>")
            except (discord.HTTPException, OSError):
                blocks.append(f"<div class='file'>📎 {html.escape(attachment.filename)} (không thể lưu)</div>")
        return "".join(blocks)

    def _embeds(self, message: discord.Message) -> str:
        rendered: list[str] = []
        for embed in message.embeds:
            parts: list[str] = []
            if embed.title:
                parts.append(f"<strong class='embed-title'>{self._clean_embed_text(embed.title, message.guild)}</strong>")
            if embed.description:
                parts.append(f"<div>{self._clean_embed_text(embed.description, message.guild)}</div>")
            for field in embed.fields:
                parts.append(
                    f"<div class='embed-field'><strong>{self._clean_embed_text(field.name, message.guild)}</strong>"
                    f"<div>{self._clean_embed_text(field.value, message.guild)}</div></div>"
                )
            if embed.footer and embed.footer.text:
                parts.append(f"<small>{self._clean_embed_text(embed.footer.text, message.guild)}</small>")
            if parts:
                rendered.append(f"<section class='embed'>{''.join(parts)}</section>")
        return "".join(rendered)

    @staticmethod
    def _clean_embed_text(value: str, guild: discord.Guild | None) -> str:
        if guild:
            def member_name(match: re.Match[str]) -> str:
                member = guild.get_member(int(match.group(1)))
                return f"@{member.display_name}" if member else f"@ID-{match.group(1)}"

            def role_name(match: re.Match[str]) -> str:
                role = guild.get_role(int(match.group(1)))
                return f"@{role.name}" if role else f"@role-{match.group(1)}"

            def channel_name(match: re.Match[str]) -> str:
                channel = guild.get_channel(int(match.group(1)))
                return f"#{channel.name}" if channel else f"#channel-{match.group(1)}"

            value = re.sub(r"<@!?(\d+)>", member_name, value)
            value = re.sub(r"<@&(\d+)>", role_name, value)
            value = re.sub(r"<#(\d+)>", channel_name, value)
        return html.escape(value).replace("\n", "<br>")

    def delete(self, slug: str) -> None:
        target = (self.config.transcript_dir / slug).resolve()
        root = self.config.transcript_dir.resolve()
        if target.parent == root and target.exists():
            shutil.rmtree(target)

    @staticmethod
    def _document(channel: discord.TextChannel, messages: str) -> str:
        title = html.escape(channel.name)
        generated = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
        return f"""<!doctype html>
<html lang='vi'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Transcript #{title}</title>
<style>
:root{{--bg:#313338;--panel:#2b2d31;--text:#dbdee1;--muted:#949ba4;--link:#00a8fc}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:16px/1.45 Arial,sans-serif}}
header{{position:sticky;top:0;background:#1e1f22;padding:18px 5%;z-index:2;box-shadow:0 2px 8px #0005}}
header h1{{font-size:20px;margin:0}}header p{{color:var(--muted);margin:4px 0 0;font-size:13px}}
main{{max-width:1000px;margin:auto;padding:20px}}.message{{display:flex;gap:14px;padding:9px 14px;border-radius:6px}}
.message:hover{{background:var(--panel)}}.avatar{{width:40px;height:40px;border-radius:50%;object-fit:cover;flex:none}}
.body{{min-width:0;flex:1}}time,.edited{{color:var(--muted);font-size:12px;margin-left:6px}}.content{{white-space:normal;overflow-wrap:anywhere}}
.embed{{border-left:4px solid #5865f2;background:#2b2d31;padding:10px 12px;margin-top:7px;border-radius:4px;max-width:560px}}
.embed-title{{display:block;margin-bottom:5px}}.embed-field{{margin-top:9px}}.embed small{{display:block;color:var(--muted);margin-top:9px}}
.attachment{{display:block;max-width:min(520px,100%);max-height:520px;border-radius:8px;margin-top:8px}}
.file{{margin-top:7px;padding:9px;background:#1e1f22;border-radius:5px;width:max-content;max-width:100%}}a{{color:var(--link)}}
</style></head><body><header><h1>#{title}</h1><p>V Roleplay • tạo lúc {generated}</p></header><main>{messages}</main></body></html>"""
