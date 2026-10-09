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
    # --- Added by the P20 red-team (D-64). Each rule below closed a case that reached a
    # --- player-visible quest with V1-V12 untouched. §9.1 forbids all of it, and §9.2 says the
    # --- starting list is to be extended in tests — which is what these are.
    # Watching, waiting for, or recording people (§9.1 "following or photographing strangers")
    _r("surveil", r"\b(?:spy|spies|spying|surveil\w*|stake out|staking out|stakeout)\b"),
    _r("watch_people", r"\b(?:watch|watches|watching|observe|observes|observing|monitor|monitors|monitoring)\b[^.]{0,20}\b(?:who|whoever|people|someone|somebody|a person|strangers?|the (?:man|woman|resident|occupant|neighbou?r|staff|worker|guard|owner|driver))\b"),
    # The target has to be somewhere a *person* is waited for: "wait at the bus stop by the park
    # entrance" is an ordinary meeting point, so bare `gate`/`entrance`/`door` are not listed.
    _r("wait_for_person", r"\bwait(?:s|ing)?\b[^.]{0,24}\b(?:outside|by|near|across from|opposite|at)\b[^.]{0,24}\b(?:house|home|flat|flats|apartment|bedroom|front door|back door|staff exit|staff door|their (?:door|gate|window))s?\b"),
    # `driveway` is deliberately absent: it is an ordinary navigational landmark ("turn left
    # after the driveway") and test_v4_allows pins it as allowed.
    _r("private_dwelling", r"\b(?:someone'?s (?:house|home|flat|garden|window|balcony|room)|the flats|apartment\w*|balcon(?:y|ies)|back garden|front garden|doorstep|letterbox|residential (?:street|lane|block|building))\b"),
    _r("record_identifiers", r"\b(?:number plates?|licen[cs]e plates?|registration (?:numbers?|plates?)|house numbers?|door numbers?|name ?plates?)\b"),
    _r("eavesdrop", r"\b(?:eavesdrop\w*|overhear\w*|listen in on)\b|\b(?:write down|note down|record)\b[^.]{0,30}\b(?:say|says|saying|said|talking|discussing|conversation)\b"),
    _r("count_people", r"\b(?:count|counts|counting|tally|tallies|tallying)\b[^.]{0,24}\b(?:people|persons?|men|women|man|woman|kids?|children|customers?|passers\w*|pedestrians?|shoppers?)\b"),
    _r("trail_person", r"\b(?:pick|choose|select)\w*\b[^.]{0,12}\b(?:a|one|the) (?:person|man|woman|stranger|passer\w*)\b|\bsame route (?:they|he|she|them)\b|\bwhere (?:they|he|she) (?:lives?|works?|goes?|went)\b|\b(?:trail|trails|trailing|shadow|shadows|shadowing)\b[^.]{0,16}\b(?:someone|somebody|a person|people|them|him|her|the (?:man|woman|stranger))\b"),
    _r("school_grounds", r"\b(?:school|nursery|creche|kindergarten|playgroup)\b[^.]{0,12}\b(?:gates?|entrance|yard|grounds|run|children|kids)\b|\b(?:outside|by|near|at) (?:the |a )?(?:school|nursery|creche|kindergarten)\b"),
    # Private property and restricted areas (§9.1 "never instruct entry to private property")
    _r("building_site", r"\b(?:building site|construction site|construction zone|hoarding|scaffold\w*|demolition)\b"),
    _r("tunnel", r"\b(?:storm drain|drainage tunnel|culvert|sewer|service tunnel|tunnels?)\b"),
    _r("service_area", r"\b(?:staff only|employees only|authorised personnel|authorized personnel|back of house|staff (?:exit|entrance|room|door)|service (?:lift|elevator|entrance|corridor|stairwell|door))\b"),
    _r("bribe", r"\b(?:bribe\w*|baksheesh)\b|\b(?:pay|pays|paying|offer|offers|offering|tip|tips|tipping|slip)\b[^.]{0,20}\b(?:the |a )?(?:guard|guards|watchman|security|attendant|caretaker|doorman|bouncer)\b"),
    _r("get_over", r"\b(?:get|gets|getting|clamber\w*|boost|hoist|vault\w*|haul)\b[^.]{0,16}\bover (?:the |a |it\b)"),
    _r("locked_access", r"\b(?:padlock\w*|locked (?:gate|door|entrance|shut)|chained (?:gate|shut)|prise\w* open|pry open|force the (?:door|gate|lock))\b"),
    _r("car_park_deck", r"\b(?:top deck|roof deck|upper deck)\b|\bmulti ?stor(?:e?y|ies) car park\b"),
    _r("defer_to_name", r"\bdo what\b[^.]{0,24}\b(?:name|sign|label|place|it)\b[^.]{0,12}\bsays?\b|\bfollow the instruction\w*\b"),
    # Water edges (§9.1) beyond the swim/dive wording
    _r("paddle", r"\bpaddl\w*"),
    _r("step_into_water", r"\bstep(?:s|ping)? into (?:the |a )?(?:fountain|water|basin|pond|river|lake|sea|stream|canal|creek|flood\w*)\b"),
    _r("out_to_water", r"\b(?:buoy|buoys)\b|\bout to the (?:middle|island|far (?:side|bank)|opposite bank)\b"),
    _r("ice", r"\b(?:thin ice|test the ice|on the ice|onto the ice|frozen (?:pond|lake|river|canal|reservoir))\b"),
    # Heights (§9.1) beyond climb/cliff/ledge
    _r("lean_over", r"\blean(?:s|ing)? (?:in |out |right )?(?:over|into|in over|out over)\b"),
    _r("sheer_drop", r"\b(?:above the drop|sheer drop|long drop|straight down)\b"),
    # Traffic (§9.1 "never traffic crossing instructions") beyond "cross the"
    _r("traffic_gap", r"\b(?:dash|dart|sprint|weave|dodge|nip|run)\w*\b[^.]{0,16}\b(?:between|through|across|into)\b[^.]{0,12}\b(?:traffic|cars|lanes|vehicles)\b|\bgaps? in the traffic\b"),
    _r("fast_road", r"\b(?:hard shoulder|motorway|expressway|freeway|dual carriageway|central reservation|median strip|bypass|flyover|slip road)\b"),
    # Wildlife (§9.1 "touching/feeding wildlife") beyond feed/touch
    _r("offer_animals", rf"\b(?:offer|offers|offering|give|gives|giving|throw|throws|throwing|hand)\w*\b[^.]{{0,20}}\b{_ANIMALS}\b"),
    _r("trail_animals", rf"\b(?:follow|follows|following|trail|trails|trailing|track|tracks|tracking|chase|chases|chasing)\w*\b[^.]{{0,16}}\b{_ANIMALS}\b"),
    # Substances (§9.1) beyond alcohol
    _r("tobacco_drugs", r"\b(?:cigarettes?|cigars?|bidis?|tobacco|vape|vapes|vaping|hookah|shisha|cannabis|marijuana|hashish|ganja|narcotics?|cocaine|opium)\b|\bsmoke (?:it|one|a )\b"),
    # Eating wild things (§9.1) beyond forage/mushroom
    _r(
        "pick_and_eat",
        r"\b(?:pick|picks|picking|taste|tastes|tasting|chew|chews|chewing|eat|eats|eating|swallow\w*|nibble\w*)\b[^.]{0,20}\b(?:berr(?:y|ies)|fruits?|nuts?|herbs?|leaves|plants?|flowers?|seeds?|pods?)\b",
        # "pick out three flowers" is identifying them, not harvesting them.
        unless=r"\bpick(?:s|ing)? out\b",
    ),
    # Weather exposure (§9.1 "heat/rain/storm -> indoor or reschedule"). Narrowed to the
    # *instruction*: a safety_note that says "come back if you hear thunder" is good advice and
    # must keep passing, so the bare words `storm` and `thunder` are deliberately not banned.
    _r("storm_exposure", r"\b(?:in|into|out in) the open\b[^.]{0,30}\b(?:lightning|thunder\w*|storm|gale|hail)\b|\bduring the (?:lightning|thunder\w*|storm|gale|hail|downpour)\b|\bwhile the (?:gale|storm|lightning)\b"),
    _r("shelter_under_trees", r"\bunder (?:the |a |some )?(?:big |tall |large |old )?trees?\b[^.]{0,24}\b(?:gale|storm|lightning|thunder\w*|wind)\b"),
    _r("flood_water", r"\b(?:flooded|floodwater|knee (?:height|deep)|waist deep|ankle deep in water)\b"),
    _r("extreme_cold", r"\b(?:minus \w+|sub ?zero|freezing cold|frostbite|wind ?chill)\b"),
    _r("air_quality", r"\bair quality (?:warning|alert|advisory|index)\b|\b(?:smog|hazardous air|smoke haze)\b"),
    _r("unlit", r"\bunlit\b"),
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
