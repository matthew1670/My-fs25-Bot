import logging
import requests
from typing import Optional

from fs25_parser import ServerSnapshot

logger = logging.getLogger(__name__)


class AlertManager:
    """Manage FS25 alerts and send notifications via Discord webhook."""

    def __init__(self, webhook_url: str):
        """Create a new AlertManager.

        Args:
            webhook_url: The Discord webhook URL where alerts should be posted.
        """
        self.webhook_url = webhook_url
        self.last_snapshot: Optional[ServerSnapshot] = None
        self.server_online = False

    def send(self, message: str):
        """Send a message to Discord or log it when webhook is missing."""
        if not self.webhook_url:
            logger.info("DISCORD ALERT: %s", message)
            return

        try:
            response = requests.post(self.webhook_url, json={"content": message}, timeout=10)
            response.raise_for_status()
        except Exception:
            logger.exception("Failed to send alert via webhook")
            logger.info("DISCORD ALERT: %s", message)

    def build_startup_summary(self, snapshot: ServerSnapshot) -> str:
        """Build a summary message for when the server first comes online."""
        owned_field_ids = sorted(
            snapshot.owned_fields.keys(),
            key=lambda x: int(x) if isinstance(x, str) and x.isdigit() else x,
        )
        owned_fields = ", ".join(owned_field_ids) or "None"

        lines = [
            f"🚜 **{snapshot.server_name} alerts started**",
            f"🗺️ Map: {snapshot.map_name}",
            f"👤 Players online: {len(snapshot.players)}/{snapshot.slots_capacity}",
            f"🌾 Owned fields: {owned_fields}",
        ]

        return "\n".join(lines)

    def mark_online(self, snapshot: ServerSnapshot):
        """Send an online alert once when the server first becomes reachable."""
        if not self.server_online:
            self.send("✅ **FS25 server is online**")
            self.send(self.build_startup_summary(snapshot))
            self.server_online = True

    def mark_offline(self):
        """Send an offline alert once when the server becomes unreachable."""
        if self.server_online:
            self.send("❌ **FS25 server appears to be offline or unreachable**")
            self.server_online = False

    def process(self, snapshot: ServerSnapshot):
        """Process a new server snapshot and send alerts for detected changes."""
        self.mark_online(snapshot)

        if self.last_snapshot is None:
            self.last_snapshot = snapshot
            return

        joined = snapshot.players - self.last_snapshot.players
        left = self.last_snapshot.players - snapshot.players
        # alert for players joining the server
        for name in sorted(joined):
            self.send(f"🚜 **{name} joined the FS25 server**")
        # alert for players leaving the server
        for name in sorted(left):
            self.send(f"👋 **{name} left the FS25 server**")

        current_field_ids = set(snapshot.owned_fields)
        previous_field_ids = set(self.last_snapshot.owned_fields)
        bought_fields = current_field_ids - previous_field_ids
        sold_fields = previous_field_ids - current_field_ids

        # alert for fields being bought
        for field_id in sorted(bought_fields, key=int):
            field = snapshot.owned_fields[field_id]
            self.send(
                f"🌾 **Field {field_id} has been bought** "
                f"({field.area:.2f} ha, £{field.value:.0f})"
            )

        # alert for fields being sold
        for field_id in sorted(sold_fields, key=int):
            self.send(f"💸 **Field {field_id} has been sold**")
        
        """alert for new production pallets being detected"""
        for item, count in snapshot.production_counts.items():
            old_count = self.last_snapshot.production_counts.get(item, 0)
            if count > old_count:
                self.send(f"📦 **New {item} pallet detected** ({old_count} → {count})")

        self.last_snapshot = snapshot
