"""
selection.py
-------------
Deterministic filtering and validation logic for sneaker_agent.

These functions exist because relying on prompt wording alone to enforce
brand, colorway, and count requirements is unreliable — an LLM can ignore
or contradict a soft instruction (e.g. a prompt that says both "match the
user's brand preference" and "offer brand variety" in the same breath).
Hard-filtering the candidate pool before the LLM ever sees it, and
validating its answer against that same pool afterward, makes compliance
a guarantee instead of a hope.

TWO WAYS A CONSTRAINT ARRIVES
-----------------------------
A shopping constraint can reach sneaker_agent two ways:

  1. Structured — the Advisor UI's brand/color/profile chips send explicit
     list fields (requested_brands, requested_colors) in the request body.
  2. Free text — the user types "a low top jordan under $150" into the
     Advisor's "Interested In" box, the admin Custom Scenario panel, or the
     CLI, where there are no structured fields at all.

Only path 1 used to be honored, so a brand named purely in prose was
silently dropped — and worse, sneaker_agent then told the LLM "no specific
brand was requested — favor variety across brands", actively steering it
away from the brand the user had just named. The extract_* functions below
close that gap by parsing the same constraints out of prose. Structured
fields still win when both are present, since an explicit UI selection is a
stronger signal than a phrase in a sentence.
"""

import re

# Recognized number words for extract_requested_count, in addition to plain digits.
_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

_COUNT_MIN = 1
_COUNT_MAX = 10

# Colors a shopper might name, mapped to the spellings/synonyms that should
# also match. Kept here (rather than inside filter_by_color) so extraction
# and filtering share one vocabulary and can't drift apart.
COLOR_SYNONYMS = {
    "black":  ["black"],
    "white":  ["white"],
    "grey":   ["grey", "gray"],
    "blue":   ["blue"],
    "red":    ["red"],
    "orange": ["orange"],
    "green":  ["green"],
    "pink":   ["pink"],
    "purple": ["purple"],
    "yellow": ["yellow"],
    "brown":  ["brown"],
    "cream":  ["cream", "sail", "bone"],
}

# Silhouette height. "lows"/"highs" are how shoppers usually say it.
_PROFILE_PATTERNS = {
    "low":  re.compile(r"\b(?:low[\s-]?tops?|low[\s-]?cut|lows)\b", re.IGNORECASE),
    "high": re.compile(r"\b(?:high[\s-]?tops?|high[\s-]?cut|highs)\b", re.IGNORECASE),
    "mid":  re.compile(r"\b(?:mid[\s-]?tops?|mids)\b", re.IGNORECASE),
}

# A spending ceiling, in any of the ways a shopper phrases one:
# "under $150", "with 150 dollars", "nothing over $200", "$150 or less",
# "budget of 300", "up to 250 bucks", "300 dollars max", "I have 250 bucks".
#
# A bare number is only ever read as a price when it carries a currency
# marker ("$", "dollars", "bucks") or follows an explicit ceiling phrase.
# Without that rule "sneakers with 3 stripes" parses as a $3 budget.
_MAX_PRICE_PATTERN = re.compile(
    r"""
    (?:
        # Explicit ceiling phrase, then the amount: "under $150", "nothing over 200"
        \b(?:under|below|less\s+than|within|up\s+to|at\s+most|no\s+more\s+than
           |nothing\s+over|not\s+more\s+than|budget\s+of|max(?:imum)?\s+of|spend(?:ing)?)\s*
        \$?\s*(?P<p1>\d{1,5}(?:\.\d{1,2})?)\b
        |
        # "with $150"
        \bwith\s+\$\s*(?P<p2>\d{1,5}(?:\.\d{1,2})?)\b
        |
        # "with 150 dollars"
        \bwith\s+(?P<p3>\d{1,5}(?:\.\d{1,2})?)\s*(?:dollars?|bucks?|usd)\b
        |
        # "I have $250"
        \b(?:i\s+have|i\s+got|i've\s+got)\s+\$\s*(?P<p4>\d{1,5}(?:\.\d{1,2})?)\b
        |
        # "I have 250 bucks"
        \b(?:i\s+have|i\s+got|i've\s+got)\s+(?P<p5>\d{1,5}(?:\.\d{1,2})?)\s*(?:dollars?|bucks?|usd)\b
        |
        # "$150 or less", "$200 max"
        \$\s*(?P<p6>\d{1,5}(?:\.\d{1,2})?)\s*(?:or\s+(?:less|under|cheaper)|max(?:imum)?)\b
        |
        # "300 dollars max", "150 bucks or less"
        \b(?P<p7>\d{1,5}(?:\.\d{1,2})?)\s*(?:dollars?|bucks?)\s*(?:or\s+(?:less|under|cheaper)|max(?:imum)?)\b
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Phrases that flip the meaning of a brand mention from "I want this" to
# "I don't want this" ("no jordans", "anything but adidas", "I already own
# nikes"). Checked against the text immediately before a brand match.
_NEGATION_PATTERN = re.compile(
    r"(?:\bno\b|\bnot\b|\bdon'?t\b|\bdoesn'?t\b|\bwithout\b|\bexcept\b|\bbesides\b"
    r"|\bother\s+than\b|\banything\s+but\b|\binstead\s+of\b|\bavoid\b|\bhate\b"
    r"|\bsick\s+of\b|\btired\s+of\b|\balready\s+(?:own|have|got)\b)"
    r"[^.;!?]{0,30}$",
    re.IGNORECASE,
)

# A release-year floor: "after 2022", "post-2022", "since 2021",
# "newer than 2020", "released in 2023 or later", "2023 releases".
_MIN_YEAR_PATTERN = re.compile(
    r"""
    (?:
        \b(?:after|post|since|newer\s+than|later\s+than|from)\s*-?\s*(?P<y1>19\d{2}|20\d{2})\b
        |
        \b(?P<y2>19\d{2}|20\d{2})\s+(?:or\s+(?:later|newer)|and\s+(?:later|newer)|releases?|onwards?)\b
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# How the shopper wants the pool ordered when they ask for an extreme
# ("the most expensive", "cheapest"). Without one of these the pool stays
# ranked by popularity, which is the right default for open-ended browsing
# but the wrong answer for a superlative query.
#
# Two tiers deliberately. "most expensive" is unambiguous on its own, but a
# bare "highest" or "max" is not — "300 dollars max" is a ceiling, not a
# request for the priciest shoe, and "highest quality" isn't about price at
# all. So the generic words only count when an actual price noun follows.
_SORT_PATTERNS = [
    ("retail_desc", re.compile(
        r"\b(?:most\s+expensive|priciest|most\s+costly)\b",
        re.IGNORECASE,
    )),
    ("retail_desc", re.compile(
        r"\b(?:highest|top|greatest|largest|biggest)[\s-]*"
        r"(?:retail|price[ds]?|value|cost)\b",
        re.IGNORECASE,
    )),
    ("retail_asc", re.compile(
        r"\b(?:cheapest|least\s+expensive|most\s+affordable|budget[\s-]?friendly)\b",
        re.IGNORECASE,
    )),
    ("retail_asc", re.compile(
        r"\b(?:lowest|smallest)[\s-]*(?:retail|price[ds]?|cost)\b",
        re.IGNORECASE,
    )),
]

# How many sneakers sneaker_agent proposes when the user doesn't state a
# count explicitly. Shared with critique_agent so both agree on the same
# target without duplicating the constant.
DEFAULT_PICK_COUNT = 5

# A number only counts as a requested pick count when it sits next to one of
# these count-indicating words — otherwise a stray number in the free-text
# input (a year, a price, a model number) would be misread as a count.
_COUNT_PATTERN = re.compile(
    r"""
    (?:
        \b(?:give|show|suggest|recommend|find|get)\s+me\s+(?:just\s+|only\s+)?(?P<n1>\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\b
        |
        \b(?:just|only)\s+(?P<n2>\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\b
        |
        \b(?P<n3>\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:sneakers?|pairs?|options?|picks?|choices?|shoes?)\b
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def filter_by_brand(candidates, brands):
    """
    filter_by_brand
    ----------------
    Hard-filters candidates to only the requested brand(s). Brand data is
    always present on every catalog entry, so this filter is exact — unlike
    colorway, there's no missing-data case to fall back on.

    Args:
        candidates (list[tuple[str, dict]]): (name, details) pairs
        brands     (list[str]):              requested brands, e.g. ["Jordan"].
                                              Empty means no filter requested.

    Returns:
        list[tuple[str, dict]]: candidates matching one of the requested
                                 brands (case-insensitive), or all candidates
                                 unchanged if brands is empty. Can be an
                                 empty list if nothing matches — callers
                                 must handle that honestly, not by silently
                                 widening the search.
    """
    if not brands:
        return candidates

    wanted = {b.lower() for b in brands}
    return [
        (name, details) for name, details in candidates
        if details.get("brand", "").lower() in wanted
    ]


def filter_by_color(candidates, colors):
    """
    filter_by_color
    ----------------
    Prefers candidates whose colorway (or, failing that, name) mentions one
    of the requested colors. Colorway data is frequently missing in the
    catalog, so unlike brand this can't be a strict hard filter — if
    nothing matches, the full input list is returned instead of an empty
    result, with matched=False so the caller can be honest about it rather
    than silently pretending a color match was found.

    Args:
        candidates (list[tuple[str, dict]]): (name, details) pairs
        colors     (list[str]):              requested colors, e.g. ["Grey"].
                                              Empty means no filter requested.

    Returns:
        tuple[list[tuple[str, dict]], bool]:
          (filtered_candidates, matched) — matched is True when the filter
          actually narrowed the pool, False when it fell back to the full
          list because nothing matched.
    """
    if not colors:
        return candidates, True

    # Expand each requested color to its synonyms/alternate spellings
    # ("grey"/"gray", "cream"/"sail"/"bone") from the shared vocabulary.
    wanted = set()
    for color in colors:
        color_lower = color.lower()
        wanted.add(color_lower)
        for synonym in COLOR_SYNONYMS.get(color_lower, []):
            wanted.add(synonym)

    def matches(name, details):
        haystacks = [details.get("colorway", ""), name]
        return any(
            color in haystack.lower()
            for haystack in haystacks
            for color in wanted
        )

    filtered = [(name, details) for name, details in candidates if matches(name, details)]

    if not filtered:
        return candidates, False

    return filtered, True


def extract_requested_count(text, default=5):
    """
    extract_requested_count
    ------------------------
    Parses free-text input for an explicit pick-count request. Only matches
    a number when it's adjacent to a count-indicating phrase ("give me 2",
    "just one", "3 sneakers") so an unrelated number in the text — a year,
    a price, a model number — is never mistaken for a count.

    Args:
        text    (str): the user's free-text input
        default (int): value to return when no explicit count is found

    Returns:
        int: the requested count, clamped to [1, 10], or the default
    """
    match = _COUNT_PATTERN.search(text or "")
    if not match:
        return default

    raw = next(g for g in match.groups() if g is not None)
    value = _NUMBER_WORDS.get(raw.lower(), None)
    if value is None:
        value = int(raw)

    return max(_COUNT_MIN, min(_COUNT_MAX, value))


def clamp_count_to_pool(requested_count, pool_size):
    """
    clamp_count_to_pool
    --------------------
    Reduces a requested pick count to what's actually possible given the
    candidate pool. Asking an LLM to "pick exactly 5" from a pool of 2 is
    an impossible instruction that just causes an endless critique/retry
    loop — better to lower the target to what the pool can supply and say
    so, than to demand something that can't be satisfied.

    Args:
        requested_count (int): the count the user asked for (or the default)
        pool_size       (int): how many candidates are actually available

    Returns:
        int: min(requested_count, pool_size)
    """
    return min(requested_count, pool_size)


def extract_proposed_names(raw_answer, candidates):
    """
    extract_proposed_names
    ------------------------
    Matches sneaker names mentioned in the LLM's raw answer text against
    ONLY the candidate pool it was actually shown — never the full catalog.
    This guarantees every returned pick already passed stock/brand/color
    filtering, even if the LLM hallucinates or mentions a real sneaker
    name that wasn't part of the options it was given.

    Args:
        raw_answer (str):                     the LLM's answer text
        candidates (list[tuple[str, dict]]):   the pool shown to the LLM

    Returns:
        list[str]: sneaker names from `candidates` that appear in the answer,
                    in candidate order
    """
    raw_lower = (raw_answer or "").lower()
    return [name for name, _ in candidates if name.lower() in raw_lower]


def extract_requested_brands(text, known_brands):
    """
    extract_requested_brands
    -------------------------
    Finds brand names mentioned in free-text input. Without this, a brand
    named in prose ("get me a low top jordan") was silently dropped, because
    sneaker_agent only ever read the structured requested_brands field that
    the UI's brand chips populate — and then told the LLM no brand was
    requested, actively steering it toward other brands.

    Matching is word-boundary and case-insensitive against the catalog's own
    brand list, so it can never invent a brand the catalog doesn't stock.
    Multi-word brands ("New Balance") are matched as whole phrases, and
    plurals/possessives ("jordans", "jordan's") count as mentions.

    A negated mention is skipped: "no jordans", "anything but adidas" and "I
    already own nikes" all name a brand the shopper explicitly does NOT
    want, so treating them as a filter would invert the request.

    Args:
        text         (str):       the user's free-text input
        known_brands (iterable):  every brand string present in the catalog

    Returns:
        list[str]: matched brand names using the catalog's own casing, in
                    the order they appear in known_brands. Empty when the
                    text names no known brand, or names only negated ones.
    """
    if not text:
        return []

    # Deduplicate case-insensitively but keep the catalog's own spelling —
    # the catalog holds both "ASICS" and "Asics", and downstream filtering
    # is case-insensitive anyway, so one canonical hit per brand is enough.
    matched = []
    already_seen = set()

    for brand in known_brands:
        brand_lower = brand.lower()
        if not brand_lower or brand_lower in already_seen:
            continue

        # Optional trailing "s"/"'s" so "jordans" and "jordan's" both match.
        pattern = re.compile(
            r"\b" + re.escape(brand_lower) + r"(?:'s|s'|s)?\b",
            re.IGNORECASE,
        )

        for match in pattern.finditer(text):
            if _is_negated(text, match.start()):
                continue
            matched.append(brand)
            already_seen.add(brand_lower)
            break

    return matched


def _is_negated(text, match_start):
    """
    _is_negated
    -----------
    Checks whether the text immediately before a match negates it, so a
    brand the shopper ruled out isn't treated as one they asked for.

    Only looks back to the nearest sentence boundary, so a negation in an
    earlier sentence ("I don't like slides. Show me jordans.") doesn't
    wrongly suppress a later positive mention.

    Args:
        text        (str): the full input text
        match_start (int): index where the matched term begins

    Returns:
        bool: True when a negation phrase precedes the match
    """
    preceding_text = text[:match_start]
    return _NEGATION_PATTERN.search(preceding_text) is not None


def extract_requested_colors(text):
    """
    extract_requested_colors
    -------------------------
    Finds colorway preferences mentioned in free-text input, using the same
    COLOR_SYNONYMS vocabulary filter_by_color matches against, so extraction
    and filtering can never drift apart.

    Args:
        text (str): the user's free-text input

    Returns:
        list[str]: canonical color names (the COLOR_SYNONYMS keys) found in
                    the text. Empty when no known color is mentioned.
    """
    if not text:
        return []

    matched = []

    for canonical_color, synonyms in COLOR_SYNONYMS.items():
        for synonym in synonyms:
            pattern = re.compile(r"\b" + re.escape(synonym) + r"\b", re.IGNORECASE)
            if pattern.search(text):
                matched.append(canonical_color)
                break

    return matched


def extract_profile(text):
    """
    extract_profile
    ---------------
    Finds a silhouette-height preference ("low top", "highs", "mid") in
    free-text input.

    Args:
        text (str): the user's free-text input

    Returns:
        str | None: "low", "mid", or "high", or None when unstated. If the
                     text somehow names more than one, the first match in
                     low → high → mid order wins rather than guessing.
    """
    if not text:
        return None

    for profile_name, pattern in _PROFILE_PATTERNS.items():
        if pattern.search(text):
            return profile_name

    return None


def extract_max_price(text):
    """
    extract_max_price
    -----------------
    Finds a spending ceiling in free-text input ("under $150", "with 150
    dollars", "$200 or less").

    This is a filter on what the shopper said they'd spend, not a revival of
    the removed budget-agent concept — nothing here looks up or enforces an
    account balance. A stated ceiling is simply another constraint, the same
    as a brand or a colorway.

    Args:
        text (str): the user's free-text input

    Returns:
        float | None: the ceiling in dollars, or None when unstated
    """
    if not text:
        return None

    match = _MAX_PRICE_PATTERN.search(text)
    if not match:
        return None

    for group_value in match.groups():
        if group_value is not None:
            return float(group_value)

    return None


def extract_min_release_year(text):
    """
    extract_min_release_year
    -------------------------
    Finds a release-recency floor in free-text input ("released after 2022",
    "post-2022", "2023 or later").

    Args:
        text (str): the user's free-text input

    Returns:
        int | None: the earliest acceptable release year, or None when unstated
    """
    if not text:
        return None

    match = _MIN_YEAR_PATTERN.search(text)
    if not match:
        return None

    for group_value in match.groups():
        if group_value is not None:
            return int(group_value)

    return None


def extract_sort_preference(text):
    """
    extract_sort_preference
    ------------------------
    Detects a superlative price request ("the highest retail value Jordan",
    "the cheapest low tops") so the candidate pool can be ordered to match.

    This matters because the pool is capped at MAX_CATALOG_SIZE before the
    LLM sees it. Under the default popularity ranking, the actual
    highest-retail item can sit far outside that window and never reach the
    model at all — so a superlative query is unanswerable no matter how good
    the prompt is, unless the sort changes first.

    Args:
        text (str): the user's free-text input

    Returns:
        str | None: "retail_desc", "retail_asc", or None for the default
                     popularity ranking
    """
    if not text:
        return None

    for sort_key, pattern in _SORT_PATTERNS:
        if pattern.search(text):
            return sort_key

    return None


def filter_by_profile(candidates, profile):
    """
    filter_by_profile
    ------------------
    Hard-filters candidates to one silhouette height. Profile data is
    present on every catalog entry, so like brand this is exact — a request
    with zero matches correctly yields nothing rather than silently
    returning the wrong silhouette.

    Args:
        candidates (list[tuple[str, dict]]): (name, details) pairs
        profile    (str|None):               "low", "mid", "high", or None
                                              for no filter

    Returns:
        list[tuple[str, dict]]: matching candidates, or all candidates
                                 unchanged when profile is None
    """
    if not profile:
        return candidates

    kept = []
    for name, details in candidates:
        if details.get("profile", "").lower() == profile.lower():
            kept.append((name, details))

    return kept


def filter_by_max_price(candidates, max_price):
    """
    filter_by_max_price
    --------------------
    Hard-filters candidates to those at or below a stated retail ceiling.

    Retail price is used rather than market value because retail is what the
    shopper pays at the store this app models — market value is displayed
    alongside it as resale reference data only.

    A retail price of 0 means "unknown", not "free" — 10 catalog entries
    carry one. Those are excluded when a ceiling is set, for the same reason
    a missing release date is excluded from a year filter: an unknown price
    cannot be confirmed to be under budget, and including it would present
    an unverified item as a match.

    Args:
        candidates (list[tuple[str, dict]]): (name, details) pairs
        max_price  (float|None):             ceiling in dollars, or None

    Returns:
        list[tuple[str, dict]]: candidates at or under the ceiling, or all
                                 candidates unchanged when max_price is None
    """
    if max_price is None:
        return candidates

    kept = []
    for name, details in candidates:
        retail_price = details.get("retail_price")
        if not retail_price:
            continue
        if retail_price <= max_price:
            kept.append((name, details))

    return kept


def filter_by_release_year(candidates, min_year):
    """
    filter_by_release_year
    -----------------------
    Hard-filters candidates to those released in or after a given year.

    Entries with no release_date are excluded when a year floor is set —
    an unknown release date cannot be confirmed to satisfy "released after
    2022", and silently including it would misreport an unverified item as
    a match.

    Args:
        candidates (list[tuple[str, dict]]): (name, details) pairs
        min_year   (int|None):               earliest acceptable year, or None

    Returns:
        list[tuple[str, dict]]: candidates released in or after min_year, or
                                 all candidates unchanged when min_year is None
    """
    if min_year is None:
        return candidates

    kept = []
    for name, details in candidates:
        release_date = details.get("release_date") or ""
        # Dates are ISO "YYYY-MM-DD", so the year is the first four chars.
        year_text = release_date[:4]
        if year_text.isdigit() and int(year_text) >= min_year:
            kept.append((name, details))

    return kept


def sort_candidates(candidates, sort_preference):
    """
    sort_candidates
    ----------------
    Orders the candidate pool before it is capped at MAX_CATALOG_SIZE.

    The default (None) is popularity, which is the right ranking for
    open-ended browsing — most shoppers want well-known sneakers. A stated
    superlative overrides it, because for those queries the correct answer
    is defined by price, and popularity ranking would push it out of the
    capped window entirely.

    Items with an unknown retail price (stored as 0) sort to the END of
    either price ordering rather than to the top of the ascending one.
    Sorting them naively would answer "what's your cheapest sneaker?" with
    an item whose price nobody knows.

    Args:
        candidates      (list[tuple[str, dict]]): (name, details) pairs
        sort_preference (str|None):               "retail_desc", "retail_asc",
                                                   or None for popularity

    Returns:
        list[tuple[str, dict]]: a new sorted list (the input is not mutated)
    """
    ordered = list(candidates)

    if sort_preference == "retail_desc":
        # An unknown price (0) already falls to the bottom here.
        ordered.sort(key=lambda pair: pair[1].get("retail_price") or 0, reverse=True)
    elif sort_preference == "retail_asc":
        # Sort unknown prices last by pairing each item with a flag that is
        # 1 when the price is unknown and 0 otherwise — Python compares the
        # flag first, so every known price ranks ahead of every unknown one.
        ordered.sort(
            key=lambda pair: (
                0 if pair[1].get("retail_price") else 1,
                pair[1].get("retail_price") or 0,
            )
        )
    else:
        ordered.sort(key=lambda pair: pair[1].get("sales_this_period", 0), reverse=True)

    return ordered
