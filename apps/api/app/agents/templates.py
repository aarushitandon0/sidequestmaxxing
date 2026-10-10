"""Quest templates for the deterministic engine (MASTERSPEC §7.5).

Two sets, both consumed by `fallback_engine`:

* `PLACE_TEMPLATES` need a real seeded place and fill `{name}` from the candidate.
* `ANYWHERE_TEMPLATES` need nothing but the player's own street, so they are what the engine
  reaches for when the Scout found nothing nearby — which is the normal case outside a seeded
  city, not an edge case.

Every template here is written to pass V1-V13 unchanged. The table test in
`tests/test_templates.py` runs all of them through `validate_quest` plus the banned-term lint
for every persona, so a template that trips a safety rule fails the suite. When that happens
the template gets reworded; the validator does not get weakened (CLAUDE.md invariant 1).
"""

from dataclasses import dataclass, field

from app.models.enums import Category, PlaceKind


@dataclass(frozen=True)
class Template:
    category: Category
    title: str  # {name} available
    objective: str  # {name}
    core: str  # one or two spoken sentences; {name}
    activity_min: int
    method: str  # "photo" | "checkin" | "honor"
    photo_prompt: str | None = None  # {name}
    kinds: tuple[PlaceKind, ...] = field(default_factory=tuple)
    indoor: bool = False
    """True when the whole quest can be done under a roof, so bad weather cannot block it."""
    hours: tuple[int, int] | None = None
    """Local hour window `[start, end)` this quest only makes sense in (sunrise, golden hour,
    a midday matinee). Skipped entirely when the engine has no clock."""
    min_minutes: int = 0
    """Shortest free slot worth offering this in. Stops a 90-minute class being squeezed into
    20 minutes, which `min(activity_min, minutes_available)` would otherwise do silently."""
    safety_note: str | None = None
    """Overrides the generic rotation where a quest needs its own warning."""


# "other" is the catch-all for `tourism=attraction` and `natural=wood`, so it holds woods
# and museums alike. Templates that need actual grass, a bench or a tree must not match it:
# live generation produced "Laps of Museum of Illusions" and a quest to find the oldest tree
# at an art gallery. Only wording that works at any outdoor spot gets _OUTDOOR_ANY.
_OUTDOOR_GREEN: tuple[PlaceKind, ...] = ("park", "garden", "nature_reserve")
_OUTDOOR_ANY: tuple[PlaceKind, ...] = (*_OUTDOOR_GREEN, "other")

PLACE_TEMPLATES: tuple[Template, ...] = (
    # Viewpoints
    Template("explorer", "The Lookout at {name}", "Walk to {name} and find the spot with the widest view.",
             "Your destination is {name}. Find the spot with the widest view and name three landmarks you can see.",
             15, "photo", "the view from {name}", ("viewpoint",)),
    Template("mindful", "Stillness at {name}", "Sit at {name} for five quiet minutes and count distant sounds.",
             "Head to {name}, sit somewhere comfortable, and spend five quiet minutes counting the distant sounds.",
             15, "checkin", None, ("viewpoint",)),
    # Green spaces
    Template("naturalist", "Leaf Hunt at {name}", "Find three different leaf shapes at {name}.",
             "Make your way to {name} and find three leaves with completely different shapes. Bonus points for a weird one.",
             20, "photo", "three different leaves side by side", _OUTDOOR_GREEN),
    Template("fitness", "Laps of {name}", "Walk two full laps of the main path at {name}.",
             "Get to {name} and walk two full laps of the main path at a pace that warms you up.",
             20, "checkin", None, _OUTDOOR_GREEN),
    Template("mindful", "Bench Time at {name}", "Sit on a bench at {name} and listen for three different bird calls.",
             "Find a bench at {name}, settle in, and listen until you can tell apart three different bird calls.",
             15, "checkin", None, _OUTDOOR_GREEN),
    Template("creative", "Colour Quest at {name}", "Find five different colours in nature at {name}.",
             "At {name}, look for five different natural colours: flowers, bark, moss, sky, anything.",
             15, "photo", "a colourful flower or leaf", _OUTDOOR_ANY),
    # Water (always from the path)
    Template("naturalist", "Water Watch at {name}", "From the main path at {name}, spot two kinds of birds.",
             "Walk to {name}, stay on the main path, and spot two different kinds of birds.",
             20, "checkin", None, ("water",)),
    # Peaks
    Template("fitness", "Trail toward {name}", "Walk the marked trail toward {name} for ten minutes, then turn back.",
             "Follow the marked trail toward {name} for ten minutes, enjoy the view, then turn back the way you came.",
             25, "checkin", None, ("peak",)),
    # Heritage and art
    Template("explorer", "The Story of {name}", "Find {name} and read its plaque or inscription.",
             "Track down {name} and read its plaque or inscription. Remember one fact to tell someone later.",
             15, "photo", "a plaque or carved detail at {name}", ("heritage",)),
    Template("creative", "Sketch {name}", "Sketch one detail of {name} in under five minutes.",
             "Go to {name}, pick one small detail, and sketch it in under five minutes. Wobbly lines welcome.",
             15, "photo", "your sketch of a detail at {name}", ("heritage", "artwork")),
    Template("creative", "Poem for {name}", "Find {name} and write a three-line poem about it.",
             "Find {name}, look at it for a full minute, then write a three-line poem about what it makes you feel.",
             15, "photo", "the artwork {name}", ("artwork",)),
    # Markets and cafes
    Template("foodie", "New Taste at {name}", "Visit {name} and try one snack you have never had.",
             "Head to {name} and try one snack you have never had before. Rate it out of ten.",
             20, "photo", "your new snack at {name}", ("market",)),
    # "pick out" is deliberate: the bare "pick ... fruit" reads as harvesting to the
    # pick_and_eat lint, which quietly disabled this template until the P24 table test
    # caught it. The core sentence always said "pick out"; the objective did not.
    Template("social", "Fruit Run at {name}", "Bring a friend to {name} and pick out the best fruit together.",
             "Bring a friend or family member to {name} and pick out the best-looking fruit together.",
             20, "photo", "the fruit you picked at {name}", ("market",)),
    Template("foodie", "Mystery Order at {name}", "Order a drink you have never tried at {name}.",
             "Walk to {name} and order a drink you have never tried. Sip it slowly, no screen allowed.",
             20, "checkin", None, ("cafe",)),
    Template("social", "Story Swap at {name}", "Take a friend to {name} and swap one good story each.",
             "Invite a friend or family member to {name} and swap one good story each over a drink.",
             30, "checkin", None, ("cafe",)),
    # Indoor culture
    Template("explorer", "Oldest Thing at {name}", "Find the oldest object on display at {name}.",
             "Visit {name} and hunt for the oldest object on display. Remember what it is and how old.",
             30, "checkin", None, ("museum",)),
    Template("creative", "Gallery Eye at {name}", "Pick one exhibit at {name} and describe it in three words.",
             "Wander {name}, choose one exhibit that grabs you, and describe it in exactly three words.",
             25, "checkin", None, ("museum",)),
    Template("mindful", "Quiet Pages at {name}", "Read one page of a book about local history at {name}.",
             "Go to {name}, find a book about local history, and read one page somewhere quiet.",
             20, "checkin", None, ("library",)),
    Template("mindful", "Courtyard Calm at {name}", "Sit quietly in the courtyard at {name} for five minutes.",
             "Visit {name}, be respectful, and sit quietly in the courtyard for five minutes, just noticing.",
             15, "checkin", None, ("temple",)),
    # --- The player's own list, pointed at the kinds the Scout can actually find (P24) ---
    Template("explorer", "Blind Spine Pick at {name}", "Borrow a book from {name} chosen only by its spine.",
             "Go to {name}, walk the shelves slowly, and borrow a book you picked only by the look of its spine.",
             25, "checkin", None, ("library",)),
    Template("social", "First Time at {name}", "Walk into {name} for the first time and order something.",
             "You have walked past {name} a hundred times. Today you go in, order something, and ask whoever serves you what their favourite song is.",
             25, "checkin", None, ("cafe",)),
    Template("foodie", "Dinner from {name}", "Buy everything for tonight's dinner at {name}.",
             "Find your way to {name} and buy everything for tonight's dinner there. No supermarket allowed.",
             30, "photo", "your haul from {name}", ("market",)),
    Template("explorer", "New Wing at {name}", "Visit {name} and find the one room you would come back for.",
             "Visit {name} for the first time, walk every room, and decide which single room you would come back for.",
             35, "checkin", None, ("museum",)),
    Template("mindful", "Phone Away at {name}", "Sit at {name} for fifteen minutes with your phone put away.",
             "Go to {name}, find a bench, put your phone right away for fifteen minutes, and invent a story about the oldest tree you can see.",
             20, "checkin", None, _OUTDOOR_GREEN),
    Template("naturalist", "Golden Hour at {name}", "Picture golden hour, then compare it with the real one at {name}.",
             "Picture golden hour in your head in detail. Then go to {name} and see how much of it you got wrong.",
             25, "photo", "the golden light at {name}", ("viewpoint", "park", "garden", "water"),
             hours=(16, 20)),
    Template("fitness", "The Long Path at {name}", "Walk the path alongside {name} for twenty minutes.",
             "Walk the path alongside {name} for a full twenty minutes, staying on the path the whole way.",
             25, "checkin", None, ("water",)),
)  # fmt: skip


ANYWHERE_TEMPLATES: tuple[Template, ...] = (
    # --- The original seven (MASTERSPEC §7.5) ---
    Template("naturalist", "Street Botanist", "Find three different leaf shapes on your street.",
             "Step outside and find three leaves with different shapes within a short walk of your door.",
             15, "photo", "three different leaves side by side"),
    Template("explorer", "Door Detective", "Find the most interesting door within a ten-minute walk.",
             "Take a slow walk around your block and find the most interesting door you can.",
             20, "photo", "an interesting door"),
    Template("creative", "Sky Sketch", "Look up and sketch the shape of one cloud.",
             "Find a comfortable spot with a view of the sky and sketch the shape of one cloud in a few lines.",
             10, "photo", "your cloud sketch", indoor=True),
    Template("mindful", "Window Listening", "Sit by a window for ten minutes and count different sounds.",
             "Sit by a window, close your eyes, and count how many different sounds you can hear in ten minutes.",
             10, "honor", indoor=True),
    Template("fitness", "Block Loop", "Walk one brisk loop around your block.",
             "Lace up and walk one brisk loop around your block. Notice one thing you never saw before.",
             15, "honor"),
    Template("foodie", "Kitchen Experiment", "Make a snack using one ingredient you rarely use.",
             "Raid the kitchen and make a simple snack with one ingredient you rarely use. Taste test required.",
             20, "photo", "your homemade snack on a plate", indoor=True),
    Template("social", "Postcard Mission", "Write a short note to a friend and deliver or post it.",
             "Write a short handwritten note to a friend or family member, then deliver it or drop it in a postbox.",
             20, "honor"),

    # --- P24: the player's own list. Reworded only where V1-V13 required it. ---
    # Explorer: going somewhere new on purpose
    Template("explorer", "Ten Cool Doors", "Photograph ten doors you genuinely find interesting.",
             "Walk your neighbourhood and photograph ten doors you actually find interesting. Ten, not nine.",
             30, "photo", "the best of your ten doors"),
    Template("explorer", "The Unwalked Street", "Walk a street near you that you have never walked down.",
             "Pick a street near you that you have never once walked down. Walk it to the end, take five turns, then find your own way back.",
             30, "photo", "something you had never seen before"),
    Template("explorer", "New Route, Same Place", "Take a route you have never taken to somewhere familiar.",
             "Go somewhere you go all the time, but take a route you have never taken before. Count three things you had never noticed.",
             25, "honor"),
    Template("explorer", "The Highest Public View", "Reach the highest public viewpoint you can get to on foot.",
             "Find the highest spot near you that anyone is allowed to walk into, go there, and name three things you can see from it.",
             35, "photo", "the view from the top"),
    Template("explorer", "One Stop Further", "Ride one stop past the furthest you have ever been.",
             "Take the bus or the train one stop further than you have ever been, get off, and explore for twenty minutes.",
             60, "photo", "something at your new stop", hours=(8, 17), min_minutes=45,
             safety_note="Check the return timetable before you set off and keep to busy public areas."),
    Template("explorer", "Your Own Scavenger Hunt", "Write a five-item scavenger hunt, then complete it.",
             "Before you leave, write down five things to find: a red door, a cat, something perfectly round. Then go and find all five.",
             35, "honor"),
    Template("explorer", "Oldest and Newest", "Visit the oldest and the newest cafe in your area.",
             "Track down the oldest cafe in your area and the newest one. Visit both, and decide which one you would go back to.",
             50, "honor", min_minutes=40),

    # Naturalist: the outdoors, at the right hour
    Template("naturalist", "Riverside Twenty", "Walk a river or canal path for twenty minutes.",
             "Find a river or canal path near you and walk it for twenty minutes, staying on the path the whole way.",
             25, "photo", "the water seen from the path"),
    Template("naturalist", "Sunrise Watch", "Watch one sunrise from start to finish.",
             "Set an alarm, get somewhere with an open view to the east, and watch the whole sunrise without once checking your phone.",
             40, "photo", "the sky at sunrise", hours=(4, 8)),
    Template("naturalist", "Golden Hour, Checked", "Picture golden hour, then go and compare it with the real thing.",
             "Picture golden hour in your head in as much detail as you can. Then go outside and notice everything you got wrong.",
             30, "photo", "the golden light", hours=(16, 20)),
    Template("naturalist", "Name One Plant", "Learn the name of one plant growing near your door.",
             "Find a plant growing near your door, look it up until you know exactly what it is called, then say the name out loud.",
             20, "photo", "the plant you identified"),

    # Fitness
    Template("fitness", "Cycle the Bus Route", "Cycle a journey you would normally make by bus.",
             "Get on a bicycle and make a journey you would usually make by bus. Take the quiet streets, not the fast ones.",
             45, "honor", min_minutes=35,
             safety_note="Wear a helmet, use cycle paths and quiet streets, and stay off main roads."),
    Template("fitness", "Twenty Minutes Upright", "Spend twenty minutes learning to stay upright on a skateboard.",
             "Borrow or hire a skateboard, find a flat open space well away from traffic, and spend twenty minutes just learning to stay upright.",
             30, "honor",
             safety_note="Wear a helmet and any pads you have, and stay on flat ground away from traffic."),

    # Mindful: doing much less, on purpose
    Template("mindful", "No Phone, No Destination", "Walk with no phone and no destination for half an hour.",
             "Leave your phone at home, step outside, and walk with no destination at all for half an hour. Be back before dark.",
             30, "honor"),
    Template("mindful", "An Hour of Nothing", "Sit somewhere beautiful and do nothing at all for an hour.",
             "Find somewhere beautiful and public, sit down, and do absolutely nothing for a whole hour. No phone, no book, no music.",
             60, "honor", min_minutes=45),
    Template("mindful", "Lobby Reading Hour", "Read for an hour in the lobby of a hotel you have never stayed in.",
             "Walk into the lobby of a hotel you have never stayed in, order a coffee, and read there for a full hour.",
             60, "honor", indoor=True, min_minutes=45),
    Template("mindful", "Headstone Histories", "Visit a cemetery and find the headstone with the best story.",
             "Visit a cemetery near you, walk it slowly and respectfully, and read until you find the headstone with the best story on it.",
             30, "honor", hours=(8, 17)),
    Template("mindful", "One Hundred Pages", "Read a hundred pages of one book without opening anything else.",
             "Pick one book, put every screen in another room, and read a hundred pages of it without opening anything else.",
             120, "honor", indoor=True, min_minutes=90),

    # Creative: make a thing
    Template("creative", "The View From Here", "Draw the view from your window.",
             "Sit at your window and draw exactly what you can see. It does not have to be good, it has to be finished.",
             25, "photo", "your drawing of the view", indoor=True),
    Template("creative", "One Impressive Fold", "Fold one piece of origami that looks too hard.",
             "Pick a piece of origami that looks far too hard, find the instructions, and fold it until it actually looks right.",
             30, "photo", "your finished origami", indoor=True),
    Template("creative", "Fool One Person", "Learn a card trick well enough to fool one person.",
             "Learn one card trick properly, practise it until your hands know it on their own, then fool exactly one person with it.",
             40, "honor", indoor=True),
    Template("creative", "Made and Given Away", "Make something with your hands and give it away.",
             "Make something with your hands today, anything at all, and give it to someone before the day is over.",
             45, "photo", "the thing you made", indoor=True, min_minutes=35),
    Template("creative", "Places Before You Die", "Write down every place you want to see before you die.",
             "Get a pen and real paper, and write down every single place you want to see before you die. Do not stop at ten.",
             30, "honor", indoor=True),
    Template("creative", "First Lesson", "Take one lesson on an instrument you do not play.",
             "Find a beginner lesson for an instrument you have never played, and get all the way through the first lesson.",
             45, "honor", indoor=True, min_minutes=35),
    Template("creative", "Clay, Ink or Pasta", "Book a pottery, printing or pasta-making class and go.",
             "Find a pottery, printing or pasta-making class near you, book yourself onto it, and turn up with no expectations at all.",
             90, "photo", "what you made in the class", min_minutes=75),

    # Foodie
    Template("foodie", "A Country You Have Never Seen", "Cook a dish from a country you have never visited.",
             "Pick a country you have never been to, find one of its everyday dishes, and cook it properly tonight.",
             45, "photo", "your finished dish", indoor=True, min_minutes=35),
    Template("foodie", "First Bake", "Bake something you have never baked before.",
             "Choose something you have never baked before, follow the recipe honestly, and let it cool before you taste it.",
             60, "photo", "what you baked", indoor=True, min_minutes=45),
    Template("foodie", "Lunch For One", "Take yourself out for lunch on your own.",
             "Take yourself out for lunch, on your own, somewhere with table service. No phone on the table, not once.",
             60, "honor", hours=(11, 15), min_minutes=45),
    Template("foodie", "Most Ambitious Thing", "Cook the most ambitious thing you have ever attempted.",
             "Cook the most ambitious thing you have ever attempted, and cook all of it just for you.",
             90, "photo", "your most ambitious dish", indoor=True, min_minutes=75),

    # Social
    Template("social", "Strangest Thing in the Shop", "Buy the strangest thing you can find in a charity shop.",
             "Go to a charity shop and buy the strangest object you can find there for less than the price of lunch.",
             35, "photo", "the strangest thing you found"),
    Template("social", "Yes To The Next Three", "Say yes to the next three reasonable suggestions you get.",
             "For the rest of today, say yes to the next three reasonable suggestions anyone makes to you. Within reason.",
             60, "honor", min_minutes=45),
    Template("social", "A Proper Date With Yourself", "Plan the date you would plan for someone else, and go.",
             "Plan the kind of date you would plan for someone you really liked. Then take yourself on it, properly.",
             90, "honor", min_minutes=75),
    Template("social", "Live Music This Week", "Find live music happening near you and go to it.",
             "Find out what live music is happening near you this week, pick one, and actually turn up to it.",
             90, "honor", min_minutes=75),
    Template("social", "The Letter You Owe", "Write to someone you have lost touch with and post it.",
             "Write a real letter, by hand, to someone you have lost touch with. Then put a stamp on it and post it.",
             35, "honor"),
)  # fmt: skip
