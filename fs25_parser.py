import requests
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple, Union


@dataclass
class FieldInfo:
    id: str
    area: float
    value: float


@dataclass
class ServerSnapshot:
    server_name: str
    game: str
    version: str
    map_name: str
    slots_capacity: int
    slots_used: int
    players: Set[str]
    mods: List[str]
    owned_fields: Dict[str, FieldInfo]
    stock: Dict[str, float]
    production_counts: Dict[str, int]
    vehicles: List[dict]


PRODUCTION_TYPES = {
    "HONEY",
    "LETTUCE",
    "CANOLA_OIL",
    "GARLIC",
    "CHILLI",
    "STRAWBERRY",
    "TOMATO",
    "SPRING_ONION",
    "NAPACABBAGE",
}


def fetch_xml(xml_url: str, timeout: int = 5) -> ET.Element:
    response = requests.get(xml_url, timeout=timeout)
    response.raise_for_status()
    return ET.fromstring(response.text)


def _float(value: Optional[str], default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except ValueError:
        return default


def get_players(root: ET.Element) -> Set[str]:
    players = set()

    for player in root.findall(".//Slots/Player"):
        if player.get("isUsed") == "true" and player.text:
            players.add(player.text.strip())

    return players


def get_owned_fields(root: ET.Element) -> Dict[str, FieldInfo]:
    fields: Dict[str, FieldInfo] = {}

    for field in root.findall(".//Farmlands/Farmland"):
        field_id = field.get("id")
        owner = field.get("owner")
        if owner and owner != "0" and field_id:
            fields[field_id] = FieldInfo(
                id=field_id,
                area=_float(field.get("area")),
                value=_float(field.get("price") or field.get("value")),
            )

    return fields

def get_mods(root: ET.Element) -> List[str]:
    return [
        name
        for mod in root.findall(".//Mods/Mod")
        if (name := mod.get("name"))
    ]

def get_stock_levels(root: ET.Element) -> Dict[str, float]:
    stock = defaultdict(float)

    for vehicle in root.findall(".//Vehicles/Vehicle"):
        fill_types = vehicle.get("fillTypes")
        fill_levels = vehicle.get("fillLevels")

        if not fill_types or not fill_levels:
            continue

        types = fill_types.split()
        levels = fill_levels.split()

        for fill_type, level in zip(types, levels):
            stock[fill_type] += _float(level)

    return dict(stock)


def get_production_counts(root: ET.Element) -> Dict[str, int]:
    counts = defaultdict(int)

    for vehicle in root.findall(".//Vehicles/Vehicle"):
        fill_types = vehicle.get("fillTypes")
        fill_levels = vehicle.get("fillLevels")

        if not fill_types or not fill_levels:
            continue

        types = fill_types.split()
        levels = fill_levels.split()

        for fill_type, level in zip(types, levels):
            if fill_type in PRODUCTION_TYPES and _float(level) > 0:
                counts[fill_type] += 1

    return dict(counts)


def get_vehicles(root: ET.Element) -> List[dict]:
    vehicles = []

    for vehicle in root.findall(".//Vehicles/Vehicle"):
        vehicles.append(
            {
                "name": vehicle.get("name", "Unknown"),
                "category": vehicle.get("category", "Unknown"),
                "type": vehicle.get("type", "Unknown"),
                "x": _float(vehicle.get("x")),
                "y": _float(vehicle.get("y")),
                "z": _float(vehicle.get("z")),
                "fillTypes": vehicle.get("fillTypes", ""),
                "fillLevels": vehicle.get("fillLevels", ""),
                "isAIActive": vehicle.get("isAIActive"),
            }
        )

    return vehicles


def parse_snapshot(root: ET.Element) -> ServerSnapshot:
    slots = root.find(".//Slots")

    return ServerSnapshot(
        server_name=root.get("name", "FS25 Server"),
        game=root.get("game", "Farming Simulator 25"),
        version=root.get("version", "Unknown"),
        map_name=root.get("mapName", "Unknown"),
        slots_capacity=int(slots.get("capacity", "0")) if slots is not None else 0,
        slots_used=int(slots.get("numUsed", "0")) if slots is not None else 0,
        players=get_players(root),
        owned_fields=get_owned_fields(root),
        stock=get_stock_levels(root),
        production_counts=get_production_counts(root),
        vehicles=get_vehicles(root),
        mods=get_mods(root)
    )


def fetch_snapshot(xml_url: str, timeout: int = 5) -> ServerSnapshot:
    root = fetch_xml(xml_url, timeout=timeout)
    return parse_snapshot(root)
