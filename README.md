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
- `/last_error`

## Setup

This project targets Python 3.12+.

Install runtime packages:

```bash
pip install -r requirements.txt
```

Install development/test packages:

```bash
pip install -r requirements-dev.txt
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

`FS25_XML_URL` is required for polling to start; the bot will log an error and stay idle if it is missing.

Run the bot:

```bash
python bot.py
```

## Testing

Before running tests, activate the project virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Then run:

```powershell
pytest -q
```

If you prefer not to activate the venv, use the venv Python directly:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
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
