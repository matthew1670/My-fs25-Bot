# FS25 Discord Bot

Discord bot for Farming Simulator 25 dedicated server XML alerts and slash commands.

## Features

Automatic alerts:

- Server online/offline
- Player joined/left
- Field bought/sold
- Low stock alerts
- New production pallet alerts

Slash commands:

- `/status`
- `/players`
- `/fields`
- `/stock`
- `/production`
- `/vehicles`
- `/search_vehicle`
- `/last_error`

## Setup

Install packages:

```bash
pip install -r requirements.txt
```

Create your environment file:

```bash
cp .env.example .env
```

Edit `.env` and fill in:

```env
DISCORD_BOT_TOKEN=...
DISCORD_GUILD_ID=...
DISCORD_WEBHOOK=...
FS25_XML_URL=...
```

Run the bot:

```bash
python bot.py
```

## Discord Developer Portal

Create a Discord application and bot, then invite it with these scopes:

- `bot`
- `applications.commands`

Bot permissions:

- Send Messages
- Read Message History
- Use Slash Commands

## Notes

`CHECK_EVERY_SECONDS=10` is a good near-real-time starting point.
Going lower than 5-10 seconds may be unnecessary and could annoy your server host.
