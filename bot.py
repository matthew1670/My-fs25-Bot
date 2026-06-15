import asyncio
import logging
import os
import sys
from typing import Optional

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

from alerts import AlertManager
from fs25_parser import ServerSnapshot, fetch_snapshot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "")
FS25_XML_URL = os.getenv("FS25_XML_URL", "")
GUILD_ID = os.getenv("DISCORD_GUILD_ID")
CHECK_EVERY_SECONDS = int(os.getenv("CHECK_EVERY_SECONDS", "10"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "5"))

latest_snapshot: Optional[ServerSnapshot] = None
last_error_message: Optional[str] = None
alerts = AlertManager(DISCORD_WEBHOOK)


class FS25Bot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True

        super().__init__(
            intents=intents,
            member_cache_flags=discord.MemberCacheFlags.all(),
        )

        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()


client = FS25Bot()


def require_snapshot() -> ServerSnapshot:
    if latest_snapshot is None:
        raise RuntimeError("No FS25 data loaded yet. Try again in a few seconds.")
    return latest_snapshot


async def get_snapshot_or_reply(
    interaction: discord.Interaction,
) -> Optional[ServerSnapshot]:
    try:
        return require_snapshot()
    except RuntimeError as error:
        await interaction.response.send_message(str(error), ephemeral=True)
        return None


def sort_field_ids(field_ids):
    return sorted(
        field_ids,
        key=lambda x: int(x) if isinstance(x, str) and x.isdigit() else x,
    )


def chunk_lines(lines: list[str], limit: int = 1900) -> list[str]:
    chunks = []
    current = []
    current_len = 0

    for line in lines:
        line_len = len(line) + 1
        if current and current_len + line_len > limit:
            chunks.append("\n".join(current))
            current = []
            current_len = 0

        current.append(line)
        current_len += line_len

    if current:
        chunks.append("\n".join(current))

    return chunks


async def send_chunked_response(interaction: discord.Interaction, lines: list[str]):
    chunks = chunk_lines(lines)
    await interaction.response.send_message(chunks[0])

    for chunk in chunks[1:]:
        await interaction.followup.send(chunk)


@tasks.loop(seconds=CHECK_EVERY_SECONDS)
async def poll_fs25():
    global latest_snapshot, last_error_message

    try:
        snapshot = await asyncio.to_thread(
            fetch_snapshot,
            FS25_XML_URL,
            REQUEST_TIMEOUT,
        )
        latest_snapshot = snapshot
        last_error_message = None
        alerts.process(snapshot)
    except Exception as error:
        last_error_message = str(error)
        alerts.mark_offline()
        logger.exception("FS25 poll error")


@client.event
async def on_ready():
    logger.info("Logged in as %s", client.user)
    logger.info("Connected guilds:")

    for guild in client.guilds:
        logger.info("- %s (%s)", guild.name, guild.id)

    if not DISCORD_WEBHOOK:
        logger.warning(
            "DISCORD_WEBHOOK is not configured; alerts will be printed to stdout instead of sent."
        )

    if not poll_fs25.is_running():
        poll_fs25.start()


@client.event
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
):
    if isinstance(error, app_commands.CheckFailure):
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "❌ You do not have permission to use this command.",
                ephemeral=True,
            )
        return

    logger.exception("Unhandled slash command error")
    if not interaction.response.is_done():
        await interaction.response.send_message(
            "❌ An unexpected error occurred. The developer has been notified.",
            ephemeral=True,
        )


@client.tree.command(name="status", description="Show the current FS25 server status")
async def status(interaction: discord.Interaction):
    snapshot = await get_snapshot_or_reply(interaction)
    if snapshot is None:
        return

    players = ", ".join(sorted(snapshot.players)) or "None"
    field_ids = sort_field_ids(snapshot.owned_fields.keys())
    owned_fields = ", ".join(field_ids) or "None"

    message = (
        f"🚜 **{snapshot.server_name}**\n"
        f"🗺️ Map: {snapshot.map_name}\n"
        f"🎮 Version: {snapshot.version}\n"
        f"👤 Players: {len(snapshot.players)}/{snapshot.slots_capacity}\n"
        f"Online: {players}\n"
        f"🌾 Owned fields: {owned_fields}"
    )

    await interaction.response.send_message(message)


@client.tree.command(name="players", description="List online FS25 players")
async def players(interaction: discord.Interaction):
    snapshot = await get_snapshot_or_reply(interaction)
    if snapshot is None:
        return

    if not snapshot.players:
        await interaction.response.send_message("No players online.")
        return

    lines = ["👤 **Online players:**"]
    lines.extend(f"• {player}" for player in sorted(snapshot.players))

    await interaction.response.send_message("\n".join(lines))


@client.tree.command(name="fields", description="List owned FS25 fields")
async def fields(interaction: discord.Interaction):
    snapshot = await get_snapshot_or_reply(interaction)
    if snapshot is None:
        return

    if not snapshot.owned_fields:
        await interaction.response.send_message("No owned fields found.")
        return

    lines = [
        "🌾 **Owned fields:**",
        "```",
        f"{'ID':<4} {'Area':>8} {'Value':>12}",
        f"{'----':<4} {'--------':>8} {'----------':>12}",
    ]

    for field_id in sort_field_ids(snapshot.owned_fields.keys()):
        field = snapshot.owned_fields[field_id]
        lines.append(
            f"{field_id:<4} {field.area:8.2f} {f'£{field.value:,.0f}':>12}"
        )

    lines.append("```")
    await interaction.response.send_message("\n".join(lines))


@client.tree.command(name="stock", description="Show stock/fill levels from the FS25 XML")
async def stock(interaction: discord.Interaction):
    snapshot = await get_snapshot_or_reply(interaction)
    if snapshot is None:
        return

    stock_items = {
        item: amount
        for item, amount in snapshot.stock.items()
        if item != "UNKNOWN"
    }

    if not stock_items:
        await interaction.response.send_message("No stock levels found.")
        return

    lines = [
        "📦 **Stock Levels:**",
        "```",
        f"{'Item':<20} {'Amount':>12} {'Pallets':>10}",
        f"{'-' * 20:<20} {'-' * 12:>12} {'-' * 10:>10}",
    ]

    lines.extend(
        f"{item:<20} {amount:12,.0f} {amount / 1000:10,.0f}"
        for item, amount in sorted(stock_items.items())
    )

    lines.append("```")

    await send_chunked_response(interaction, lines)


@client.tree.command(name="production", description="Show production pallet counts")
async def production(interaction: discord.Interaction):
    snapshot = await get_snapshot_or_reply(interaction)
    if snapshot is None:
        return

    if not snapshot.production_counts:
        await interaction.response.send_message("No production pallets found.")
        return

    lines = ["🏭 **Production pallets:**"]
    lines.extend(
        f"• {item}: {count}"
        for item, count in sorted(snapshot.production_counts.items())
    )

    await send_chunked_response(interaction, lines)


@client.tree.command(name="vehicles", description="List vehicles and equipment")
async def vehicles(interaction: discord.Interaction):
    snapshot = await get_snapshot_or_reply(interaction)
    if snapshot is None:
        return

    if not snapshot.vehicles:
        await interaction.response.send_message("No vehicles or equipment found.")
        return

    lines = ["🚜 **Vehicles and equipment:**"]
    lines.extend(
        f"• {vehicle['name']} — {vehicle['category']}"
        for vehicle in snapshot.vehicles
    )

    await send_chunked_response(interaction, lines)


@client.tree.command(name="list_mods", description="List active mods on the FS25 server")
async def list_mods(interaction: discord.Interaction):
    snapshot = await get_snapshot_or_reply(interaction)
    if snapshot is None:
        return

    if not snapshot.mods:
        await interaction.response.send_message("No active mods found.", ephemeral=True)
        return

    lines = ["🧩 **Active Mods:**"]
    lines.extend(f"• {mod}" for mod in snapshot.mods)

    await send_chunked_response(interaction, lines)


@client.tree.command(name="reboot", description="Restart the bot")
@app_commands.checks.has_permissions(administrator=True)
async def reboot(interaction: discord.Interaction):
    await interaction.response.send_message("🔄 Rebooting bot...", ephemeral=True)
    await client.close()
    os.execv(sys.executable, [sys.executable] + sys.argv)


@client.tree.command(name="my_perms", description="Show your Discord permissions")
@app_commands.default_permissions(administrator=True)
async def my_perms(interaction: discord.Interaction):
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "This command must be used in a server.",
            ephemeral=True,
        )
        return

    perms = interaction.permissions

    lines = [
        f"👤 **Permissions for {interaction.user.display_name}**",
        f"Guild ID: {interaction.guild_id}",
        f"Administrator: {perms.administrator}",
        f"Manage Roles: {perms.manage_roles}",
        f"Manage Channels: {perms.manage_channels}",
        f"Manage Messages: {perms.manage_messages}",
        f"Kick Members: {perms.kick_members}",
        f"Ban Members: {perms.ban_members}",
        f"Manage Guild: {perms.manage_guild}",
        f"View Audit Log: {perms.view_audit_log}",
        f"Send Messages: {perms.send_messages}",
        f"Embed Links: {perms.embed_links}",
    ]

    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@client.tree.command(name="last_error", description="Show the last error from polling FS25 XML")
async def last_error_command(interaction: discord.Interaction):
    if last_error_message is None:
        await interaction.response.send_message("✅ No errors yet. All good!" , ephemeral=True)
        return

    await interaction.response.send_message(
        f"❌ **Last error:**\n```\n{last_error_message}\n```", ephemeral=True
    )


if not DISCORD_BOT_TOKEN:
    raise SystemExit("Missing DISCORD_BOT_TOKEN in .env")

if not FS25_XML_URL:
    raise SystemExit("Missing FS25_XML_URL in .env")

client.run(DISCORD_BOT_TOKEN)
