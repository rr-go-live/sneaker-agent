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
"""

import re

# Recognized number words for extract_requested_count, in addition to plain digits.
_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

_COUNT_MIN = 1
_COUNT_MAX = 10

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

    wanted = {c.lower() for c in colors}
    # "grey"/"gray" are the same color under two spellings.
    if "grey" in wanted:
        wanted.add("gray")
    if "gray" in wanted:
        wanted.add("grey")

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
