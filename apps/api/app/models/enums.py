"""Enumerations shared by request, quest and profile schemas (MASTERSPEC §6)."""

from typing import Literal, get_args

Category = Literal["explorer", "naturalist", "social", "foodie", "creative", "fitness", "mindful"]
Mood = Literal["curious", "tired", "restless", "social", "calm", "adventurous"]
Persona = Literal["chill", "dramatic", "nature_nerd", "sarcastic"]
TravelMode = Literal["walk", "transit_ok"]
VerificationMethod = Literal["photo", "checkin", "honor"]
Rarity = Literal["common", "rare", "legendary"]
PlaceKind = Literal[
    "viewpoint",
    "park",
    "garden",
    "nature_reserve",
    "peak",
    "water",
    "heritage",
    "artwork",
    "market",
    "cafe",
    "museum",
    "temple",
    "library",
    "other",
]

CATEGORIES: tuple[Category, ...] = get_args(Category)
MOODS: tuple[Mood, ...] = get_args(Mood)
PERSONAS: tuple[Persona, ...] = get_args(Persona)
PLACE_KINDS: tuple[PlaceKind, ...] = get_args(PlaceKind)
