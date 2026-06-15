import asyncio
import os
from typing import Optional

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

from alerts import AlertManager
from fs25_parser import ServerSnapshot, fetch_snapshot

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
        super().__init__(intents=intents)
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


def chunk_lines(lines, limit=1900):
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


@tasks.loop(seconds=CHECK_EVERY_SECONDS)
async def poll_fs25():
    global latest_snapshot, last_error_message

    try:
        snapshot = await asyncio.to_thread(fetch_snapshot, FS25_XML_URL, REQUEST_TIMEOUT)
        latest_snapshot = snapshot
        last_error_message = None
        alerts.process(snapshot)
    except Exception as error:
        last_error_message = str(error)
        alerts.mark_offline()
        print(f"FS25 poll error: {error}")


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    if not poll_fs25.is_running():
        poll_fs25.start()


@client.tree.command(name="status", description="Show the current FS25 server status")
async def status(interaction: discord.Interaction):
    try:
        snapshot = require_snapshot()
    except RuntimeError as error:
        await interaction.response.send_message(str(error), ephemeral=True)
        return

    players = ", ".join(sorted(snapshot.players)) or "None"
    owned_fields = ", ".join(sorted(snapshot.owned_fields, key=int)) or "None"

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
    try:
        snapshot = require_snapshot()
    except RuntimeError as error:
        await interaction.response.send_message(str(error), ephemeral=True)
        return
    if not snapshot.players:
        await interaction.response.send_message("No players online.")
        return

    await interaction.response.send_message("👤 **Online players:**\n" + "\n".join(f"• {p}" for p in sorted(snapshot.players)))


@client.tree.command(name="fields", description="List owned FS25 fields")
async def fields(interaction: discord.Interaction):
    try:
        snapshot = require_snapshot()
    except RuntimeError as error:
        await interaction.response.send_message(str(error), ephemeral=True)
        return
    fields_list = sorted(snapshot.owned_fields, key=int)
    message = "🌾 **Owned fields:**\n" + ("\n".join(f"• Field {f}" for f in fields_list) or "None")
    await interaction.response.send_message(message)


@client.tree.command(name="stock", description="Show stock/fill levels from the FS25 XML")
async def stock(interaction: discord.Interaction):
    try:
        snapshot = require_snapshot()
    except RuntimeError as error:
        await interaction.response.send_message(str(error), ephemeral=True)
        return
    if not snapshot.stock:
        await interaction.response.send_message("No stock levels found.")
        return

    lines = ["📦 **Stock levels:**"]
    for item, amount in sorted(snapshot.stock.items()):
        if item != "UNKNOWN":
            lines.append(f"• {item}: {amount:.0f}")

    await interaction.response.send_message("\n".join(lines[:60]))


@client.tree.command(name="production", description="Show production pallet counts")
async def production(interaction: discord.Interaction):
    try:
        snapshot = require_snapshot()
    except RuntimeError as error:
        await interaction.response.send_message(str(error), ephemeral=True)
        return
    if not snapshot.production_counts:
        await interaction.response.send_message("No production pallets found.")
        return

    lines = ["🏭 **Production pallets:**"]
    for item, count in sorted(snapshot.production_counts.items()):
        lines.append(f"• {item}: {count}")

    await interaction.response.send_message("\n".join(lines))


@client.tree.command(name="vehicles", description="List vehicles and equipment")
async def vehicles(interaction: discord.Interaction):
    try:
        snapshot = require_snapshot()
    except RuntimeError as error:
        await interaction.response.send_message(str(error), ephemeral=True)
        return
    lines = ["🚜 **Vehicles and equipment:**"]

    for vehicle in snapshot.vehicles:
        lines.append(f"• {vehicle['name']} — {vehicle['category']}")

    chunks = chunk_lines(lines)
    await interaction.response.send_message(chunks[0])

    for chunk in chunks[1:]:
        await interaction.followup.send(chunk)


@client.tree.command(name="list_mods", description="List active mods on the FS25 server")
async def list_mods(interaction: discord.Interaction):
    try:
        snapshot = require_snapshot()
    except RuntimeError as error:
        await interaction.response.send_message(str(error), ephemeral=True)
        return

    if not snapshot.mods:
        await interaction.response.send_message("No active mods found.")
        return

    lines = ["🧩 **Active Mods:**"]
    for mod in snapshot.mods:
        lines.append(f"• {mod}")

    await interaction.response.send_message("\n".join(lines))


@client.tree.command(name="search_vehicle", description="Search vehicles by name")
@app_commands.describe(query="Vehicle name or part of a name, e.g. MF")
async def search_vehicle(interaction: discord.Interaction, query: str):
    try:
        snapshot = require_snapshot()
    except RuntimeError as error:
        await interaction.response.send_message(str(error), ephemeral=True)
        return
    query_lower = query.lower()
    matches = [v for v in snapshot.vehicles if query_lower in v["name"].lower()]

    if not matches:
        await interaction.response.send_message(f"No vehicles found matching `{query}`.")
        return

    lines = [f"🔎 **Vehicle search: {query}**"]
    for vehicle in matches[:20]:
        lines.append(
            f"• **{vehicle['name']}** — {vehicle['category']} "
            f"at x={vehicle['x']:.0f}, z={vehicle['z']:.0f}"
        )
        if vehicle["fillTypes"]:
            lines.append(f"  Fill: {vehicle['fillTypes']} / {vehicle['fillLevels']}")

    await interaction.response.send_message("\n".join(lines))


@client.tree.command(name="last_error", description="Show the last error from polling FS25 XML")
async def last_error_command(interaction: discord.Interaction):
    if last_error_message is None:
        await interaction.response.send_message("✅ No errors yet. All good!")
        return

    await interaction.response.send_message(f"❌ **Last error:**\n```\n{last_error_message}\n```")


if not DISCORD_BOT_TOKEN:
    raise SystemExit("Missing DISCORD_BOT_TOKEN in .env")

if not FS25_XML_URL:
    raise SystemExit("Missing FS25_XML_URL in .env")

client.run(DISCORD_BOT_TOKEN)
