"""Banned-term lint (V4), people-in-photo check (V6), contact-info check (V8).

Rules start from MASTERSPEC §9.2 and §9.1 and only ever get stricter. Every rule has an id so
failures are explainable in traces and training-filter stats. Word boundaries avoid false
hits like "diverse" (dive) or "driveway" (drive).
"""

import re
from dataclasses import dataclass

from app.validators.text import normalize


@dataclass(frozen=True)
class Rule:
    id: str
    pattern: re.Pattern[str]
    unless: re.Pattern[str] | None = None  # allowed phrasing that would otherwise match


def _r(rule_id: str, pattern: str, unless: str | None = None) -> Rule:
    return Rule(rule_id, re.compile(pattern), re.compile(unless) if unless else None)


_ANIMALS = (
    r"(?:birds?|ducks?|geese|goose|dogs?|puppies|cats?|kittens?|monkeys?|snakes?|pigeons?|"
    r"fish|squirrels?|cows?|cattle|animals?|wildlife|bees?|horses?|goats?|crows?)"
)

BANNED_RULES: tuple[Rule, ...] = (
    # Water
    _r("swim", r"\bswim\w*"),
    _r("dive", r"\b(?:dive|dives|diving|dived|dove in)\b"),
    _r("wade", r"\b(?:wade|wades|wading)\b"),
    _r("into_water", r"\binto (?:the )?(?:water|river|lake|sea|ocean|pond|stream|canal|creek)\b"),
    # Heights
    _r(
        "climb",
        r"\bclimb\w*",
        unless=r"\bclimb(?:s|ing)? (?:up )?the stairs (?:at|of|to|in|inside)\b",
    ),
    _r("cliff", r"\bcliff\w*"),
    _r("edge_of", r"\bedge of\b"),
    _r("ledge", r"\b(?:ledges?|parapets?|rooftops?|on the roof)\b"),
    # Property / trespass
    _r("trespass", r"\btrespass\w*"),
    _r("private_property", r"\bprivate (?:property|land|grounds?)\b"),
    _r("abandoned", r"\b(?:abandoned|derelict|condemned)\b"),
    _r("sneak", r"\b(?:sneak\w*|break\w* in(?:to)?)\b"),
    _r("fence_jump", r"\b(?:jump\w*|hop\w*|climb\w*|scal\w*) (?:over )?(?:the |a )?(?:fence|wall|gate|barrier)s?\b"),
    _r("gate_jump", r"\bgates?\b.*\bjump\w*|\bjump\w*.*\bgates?\b"),
    # Traffic / vehicles
    _r("cross_road", r"\bcross(?:ing)? (?:the |a |busy )?(?:highway|motorway|expressway|freeway|road|street|railway|railroad|tracks|train tracks)\b"),
    _r("drive", r"\b(?:drive|drives|driving|drove)\b"),
    # Substances / food safety
    _r("alcohol", r"\b(?:drunk|alcohol\w*|beers?|wine|liquor|vodka|whiske?y|rum|cocktails?|brewery|pub crawl|tequila)\b"),
    _r("forage", r"\bforag\w*"),
    _r("eat_wild", r"\beat(?:ing)? (?:the |some )?wild\b|\bwild (?:berries|plants|herbs|greens|fruit)\b"),
    _r("mushroom_food", r"\bmushrooms?\b.*\b(?:eat|taste|cook|pick|snack|try|chew)\w*|\b(?:eat|taste|cook|pick|snack|try|chew)\w*\b.*\bmushrooms?\b"),
    # Animals
    _r("feed_animals", rf"\bfeed(?:s|ing)? (?:the |a |some )?(?:\w+ )?{_ANIMALS}\b|\bfeed(?:s|ing)? the\b"),
    _r("touch_animals", rf"\b(?:touch|pet|pat|stroke|catch|chase|grab)\w* (?:the |a |some )?(?:\w+ )?{_ANIMALS}\b"),
    # People
    _r("strangers", r"\b(?:approach|follow|talk to|chat (?:up|with)|ask|hug|interview)\w* (?:a |some |random )?strangers?\b"),
    _r("follow_someone", r"\bfollow(?:s|ing)? (?:someone|somebody|a person|people|them|him|her|a stranger)\b"),
    _r("children", r"\b(?:talk|speak|chat|approach|play|give)\w* (?:to |with )?(?:a |some |the )?(?:child|children|kids?|minors?)\b"),
    # Time / isolation
    _r("night_alone", r"\b(?:at night alone|alone at night|after dark alone|alone after dark)\b"),
    _r("midnight", r"\bmidnight\b"),
    _r("isolated", r"\b(?:isolated|deserted|secluded|remote)\b"),
    # Misc hazards
    _r("fireworks", r"\bfireworks?\b|\bfirecrackers?\b"),
    _r("fire", r"\b(?:campfire|bonfire|light a fire|start a fire)\b"),
    _r("drone", r"\bdrones?\b"),
    _r("weapons", r"\b(?:knife|knives|gun|guns|weapon\w*|airsoft)\b"),
)  # fmt: skip

# Applied to photo prompts only (V4 "strangers in photo prompts" + V6 people/faces).
PEOPLE_PATTERN = re.compile(
    r"\b(?:people|person|persons|man|men|woman|women|boy|boys|girl|girls|guy|guys|lady|ladies|"
    r"kid|kids|child|children|baby|babies|toddler|teen\w*|faces?|selfies?|yourself|stranger\w*|"
    r"crowds?|someone|somebody|anyone|anybody|everyone|friends?|family|portrait\w*|vendor\w*|"
    r"seller\w*|shopkeeper\w*|stall ?keeper\w*|barista\w*|waiter\w*|staff|worker\w*|police\w*|"
    r"guards?|tourists?|pedestrians?|couples?|students?|players?|runners?|him|her|them|human\w*|"
    r"body|bodies|eyes|smil\w*|owner\w*|resident\w*|neighbou?r\w*|locals?|monks?|priests?|"
    r"artists?|musicians?|performer\w*)\b"
)

URL_PATTERN = re.compile(
    r"https?://|\bwww\.|\b[a-z0-9-]+\.(?:com|org|net|io|in|co|app|dev|ly|me|info|xyz|gg)\b"
)
EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
PHONE_RUN = re.compile(r"\+?\d[\d\s().-]{6,}\d")


@dataclass(frozen=True)
class LintHit:
    rule: str
    match: str


def banned_hits(text: str) -> list[LintHit]:
    norm = normalize(text)
    hits: list[LintHit] = []
    for rule in BANNED_RULES:
        for m in rule.pattern.finditer(norm):
            if rule.unless is not None:
                # Allowed phrase must cover this match's start.
                if any(a.start() <= m.start() < a.end() for a in rule.unless.finditer(norm)):
                    continue
            hits.append(LintHit(rule.id, m.group(0)))
            break
    return hits


def people_hits(photo_prompt: str) -> list[str]:
    return [m.group(0) for m in PEOPLE_PATTERN.finditer(normalize(photo_prompt))]


def contact_hits(text: str) -> list[str]:
    norm = normalize(text)
    hits = [m.group(0) for m in URL_PATTERN.finditer(norm)]
    hits += [m.group(0) for m in EMAIL_PATTERN.finditer(norm)]
    for m in PHONE_RUN.finditer(norm):
        if sum(ch.isdigit() for ch in m.group(0)) >= 8:
            hits.append(m.group(0))
    return hits
