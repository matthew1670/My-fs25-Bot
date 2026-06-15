import requests
from typing import Optional, Set

from fs25_parser import ServerSnapshot


LOW_STOCK_LIMITS = {
    "SEEDS": 100,
    "HERBICIDE": 250,
    "LIQUIDFERTILIZER": 500,
    "BALE_WRAP": 10,
    "BALE_NET": 5,
}


class AlertManager:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self.last_snapshot: Optional[ServerSnapshot] = None
        self.low_stock_already_alerted: Set[str] = set()
        self.server_online = False

    def send(self, message: str):
        if not self.webhook_url:
            print(f"DISCORD ALERT: {message}")
            return

        requests.post(self.webhook_url, json={"content": message}, timeout=10)

    def build_startup_summary(self, snapshot: ServerSnapshot) -> str:
        owned_fields = ", ".join(sorted(snapshot.owned_fields, key=int)) or "None"

        lines = [
            f"🚜 **{snapshot.server_name} alerts started**",
            f"🗺️ Map: {snapshot.map_name}",
            f"👤 Players online: {len(snapshot.players)}/{snapshot.slots_capacity}",
            f"🌾 Owned fields: {owned_fields}",
        ]

        return "\n".join(lines)

    def mark_online(self, snapshot: ServerSnapshot):
        if not self.server_online:
            self.send("✅ **FS25 server is online**")
            self.send(self.build_startup_summary(snapshot))
            self.server_online = True

    def mark_offline(self):
        if self.server_online:
            self.send("❌ **FS25 server appears to be offline or unreachable**")
            self.server_online = False

    def process(self, snapshot: ServerSnapshot):
        self.mark_online(snapshot)

        if self.last_snapshot is None:
            self.last_snapshot = snapshot
            return

        joined = snapshot.players - self.last_snapshot.players
        left = self.last_snapshot.players - snapshot.players

        for name in sorted(joined):
            self.send(f"🚜 **{name} joined the FS25 server**")

        for name in sorted(left):
            self.send(f"👋 **{name} left the FS25 server**")

        current_field_ids = set(snapshot.owned_fields)
        previous_field_ids = set(self.last_snapshot.owned_fields)
        bought_fields = current_field_ids - previous_field_ids
        sold_fields = previous_field_ids - current_field_ids

        for field_id in sorted(bought_fields, key=int):
            field = snapshot.owned_fields[field_id]
            self.send(
                f"🌾 **Field {field_id} has been bought** "
                f"({field['area']:.2f} ha, £{field['value']:.0f})"
            )

        for field_id in sorted(sold_fields, key=int):
            self.send(f"💸 **Field {field_id} has been sold**")

        for item, limit in LOW_STOCK_LIMITS.items():
            amount = snapshot.stock.get(item, 0)
            old_amount = self.last_snapshot.stock.get(item, 0)

            if amount < limit and item not in self.low_stock_already_alerted:
                self.send(f"⚠️ **Low stock: {item} is at {amount:.0f}**")
                self.low_stock_already_alerted.add(item)

            if amount >= limit and item in self.low_stock_already_alerted:
                self.send(f"✅ **Stock recovered: {item} is now at {amount:.0f}**")
                self.low_stock_already_alerted.discard(item)

        for item, count in snapshot.production_counts.items():
            old_count = self.last_snapshot.production_counts.get(item, 0)
            if count > old_count:
                self.send(f"📦 **New {item} pallet detected** ({old_count} → {count})")

        self.last_snapshot = snapshot
