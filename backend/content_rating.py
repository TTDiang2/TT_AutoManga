"""Content rating: SFW by default, opt-in Mature for adult fictional characters.

One place decides what every image generation may be (agent /generate and
/generate-batch, the Assets tab's /api/assets/swarmui/generate, the
Characters tab's sheet /api/characters/templates/generate-image, the LoRA
dataset generator in /api/training, and the MCP tools, which go through the
agent API): ``apply_rating`` is called right before
``swarm_client.generate_image`` on each of those paths.

The rating of a generation:

- ``settings.content.defaultRating`` ("sfw" unless changed) is the default;
- a project's ``settings.contentRating`` ("sfw" | "mature") overrides it for
  generations made for that project; anything else there reads as unset;
- the LoRA training dataset generator is always SFW (``force_sfw``).

Minor protections, the same in every mode and on every path:

- A character is a MINOR when its explicit ``age`` is under 18, or its text
  (name, appearance, description, project prompt block) reads as a minor:
  "N years old" (also "N-year-old", "aged N", "N yo") with N < 18, or a
  minor term (teen, kid, child, schoolgirl, loli, "middle school", ...).
  A description that reads as a minor wins over an explicit adult age.
- A character is an ADULT when not a minor and its age is 18+, or its text
  says "N years old" with N >= 18, or "adult". Otherwise its age is UNKNOWN.
- Mature content is never produced for a generation involving a minor or a
  character of unknown age: it is forced to SFW, with a notice saying why.
- In mature mode a free prompt containing a minor term is refused
  (``RatingRefused`` -> HTTP 400), never silently altered.
- SFW generations get ``SFW_NEG`` in the negative prompt. Mature generations
  get ``AGE_POS`` in the prompt and ``AGE_NEG`` in the negative prompt.

Negative prompts reduce what a model draws; they do not guarantee it.
"""
import re
from typing import Any, Dict, Iterable, List, Optional

RATINGS = ("sfw", "mature")
SFW_NEG = "nsfw, nude, naked, nipples, cleavage, underwear, lingerie"
AGE_POS = "adult, mature adult"
AGE_NEG = "child, loli, shota, childlike, teen, young, underage, petite child body"

# words for numbers a description may spell out ("sixteen years old", "twenty-five")
_UNITS = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
_TEENS = ["ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
          "seventeen", "eighteen", "nineteen"]
_TENS = ["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_NUMBER_WORDS = {w: i + 1 for i, w in enumerate(_UNITS)}
_NUMBER_WORDS.update({w: i + 10 for i, w in enumerate(_TEENS)})
_NUMBER_WORDS.update({w: (i + 2) * 10 for i, w in enumerate(_TENS)})
_SEP = r"[\s_\-]*"
# a compound ("twenty-five") first, so its unit is never read on its own
_NUM = (r"((?:" + "|".join(_TENS) + r")(?:[\s_\-]+(?:" + "|".join(_UNITS) + r"))?|\d{1,3}|"
        + "|".join(_TEENS + _UNITS) + r")")
_B = r"(?<![a-z0-9\-])"
# "16 years old", "16-year-old", "16 yrs old", "16yo", "16 y/o", "aged 16", "age: 16"
_AGE_PATTERNS = [
    re.compile(_B + _NUM + _SEP + r"(?:years?|yrs?)" + _SEP + r"old(?![a-z])", re.I),
    re.compile(_B + _NUM + _SEP + r"(?:yo|y/o|y\.o\.?)(?![a-z])", re.I),
    re.compile(r"(?<![a-z0-9])age[ds]?" + r"[\s_:=\-]*" + _NUM + r"(?![a-z0-9])", re.I),
]
# terms that read as a minor (plurals and _/- separated tag spellings too)
_W = r"[\s_\-]+"
_MINOR_TERMS = [
    r"child\w*", r"kids?", r"kiddos?", r"kiddies", r"kiddie",
    r"teens?", r"teenage[dr]?s?", r"teen" + _W + r"aged", r"tweens?", r"tweenagers?",
    r"pre" + r"[\s_\-]?" + r"teens?", r"preteens?",
    r"under" + r"[\s_\-]?" + r"aged?",
    r"lolis?", r"lolicon", r"lolita", r"shotas?", r"shotacon",
    r"young" + _W + r"(?:girls?|boys?)", r"little" + _W + r"(?:girls?|boys?)",
    r"school" + r"[\s_\-]?" + r"(?:girls?|boys?|kids?|child(?:ren)?)",
    r"toddlers?", r"bab(?:y|ies)", r"infants?", r"newborns?",
    r"minors?",
    r"middle" + _W + r"school\w*", r"elementary" + _W + r"school\w*",
    r"grade" + _W + r"school\w*", r"junior" + _W + r"high",
    r"high" + _W + r"school" + _W + r"(?:students?|girls?|boys?|kids?)", r"high" + r"[\s_\-]?" + r"schoolers?",
    r"jailbait",
]
_MINOR_RE = re.compile(r"(?<![a-z0-9])(?:" + "|".join(_MINOR_TERMS) + r")(?![a-z0-9])", re.I)
_ADULT_RE = re.compile(r"(?<![a-z0-9])adults?(?![a-z0-9])", re.I)


class RatingRefused(ValueError):
    """A mature request that may not run (minor terms in its prompt): 400."""


def _num(token: str) -> Optional[int]:
    token = token.lower()
    if token.isdigit():
        return int(token)
    parts = re.split(r"[\s_\-]+", token)
    if len(parts) == 2:
        return _NUMBER_WORDS.get(parts[0], 0) + _NUMBER_WORDS.get(parts[1], 0) or None
    return _NUMBER_WORDS.get(token)


def stated_ages(text: str) -> List[int]:
    """Ages a text states ("16 years old", "aged 30", "sixteen-year-old")."""
    out = []
    for pat in _AGE_PATTERNS:
        for m in pat.finditer(text or ""):
            n = _num(m.group(1))
            if n is not None:
                out.append(n)
    return out


def minor_terms(text: str) -> List[str]:
    """The words in ``text`` that read as a minor (a stated age under 18
    included), in order, without duplicates; [] when none."""
    text = str(text or "")
    found: List[str] = []
    for m in _MINOR_RE.finditer(text):
        t = m.group(0).lower()
        if t not in found:
            found.append(t)
    for pat in _AGE_PATTERNS:
        for m in pat.finditer(text):
            n = _num(m.group(1))
            if n is not None and n < 18 and m.group(0).lower() not in found:
                found.append(m.group(0).lower())
    return found


def normalize_age(value: Any) -> Optional[int]:
    """A character's ``age`` -> an int 0-120, or None (unset or invalid)."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, float):
        if value != value or not value.is_integer():
            return None
        value = int(value)
    if isinstance(value, str):
        value = value.strip()
        if not value.isdigit():
            return None
        value = int(value)
    if not isinstance(value, int) or not 0 <= value <= 120:
        return None
    return value


def classify(age: Any, text: str) -> Dict[str, Any]:
    """``{"status": "minor" | "adult" | "unknown", "reason": str}`` for a
    character with an explicit ``age`` (None = unset) and its text."""
    age = normalize_age(age)
    if age is not None and age < 18:
        return {"status": "minor", "reason": f"age {age}"}
    terms = minor_terms(text)
    if terms:
        return {"status": "minor", "reason": f'its description says "{terms[0]}"'}
    if age is not None:
        return {"status": "adult", "reason": f"age {age}"}
    ages = stated_ages(text)
    if ages and min(ages) >= 18:
        return {"status": "adult", "reason": f"{min(ages)} years old in its description"}
    if _ADULT_RE.search(text or ""):
        return {"status": "adult", "reason": '"adult" in its description'}
    return {"status": "unknown", "reason": "no age (set its age, 18 or over, in the Characters tab)"}


def normalize_rating(value: Any) -> Optional[str]:
    v = str(value or "").strip().lower()
    return v if v in RATINGS else None


def default_rating() -> str:
    from .core.config import settings
    return normalize_rating(getattr(getattr(settings, "content", None), "defaultRating", None)) or "sfw"


def project_rating(project: Optional[Dict[str, Any]]) -> str:
    """A project's rating: its ``settings.contentRating``, else the global default."""
    if project:
        r = normalize_rating((project.get("settings") or {}).get("contentRating"))
        if r:
            return r
    return default_rating()


def _library() -> List[Dict[str, Any]]:
    from .prompting import _global_characters
    return _global_characters()


def character_record(name: str, project: Optional[Dict[str, Any]] = None,
                     library: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """{name, age, text, found} for a panel character, from the global library
    and the project's ``settings.characters`` (whose ``age`` wins when set;
    all their texts are read for minor terms)."""
    key = str(name or "").strip().lower()
    lib = _library() if library is None else library
    entries = [c for c in lib if isinstance(c, dict) and str(c.get("name") or "").strip().lower() == key]
    entries += [c for c in ((project or {}).get("settings") or {}).get("characters") or []
                if isinstance(c, dict) and str(c.get("name") or "").strip().lower() == key]
    age = None
    texts = [str(name or "")]
    for c in entries:
        a = normalize_age(c.get("age"))
        if a is not None:
            age = a
        for k in ("appearance", "description", "prompt_block"):
            if c.get(k):
                texts.append(str(c[k]))
    return {"name": str(name or "").strip(), "age": age, "text": ", ".join(texts), "found": bool(entries)}


def panel_cast(project: Optional[Dict[str, Any]], panel: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The characters on a panel, resolved like conditioning_for_panel (by
    name, library + project entries)."""
    if not panel:
        return []
    names, seen = [], set()
    for n in panel.get("characters") or []:
        n = str(n).strip()
        if n and n.lower() not in seen:
            seen.add(n.lower())
            names.append(n)
    lib = _library() if names else []
    return [character_record(n, project, lib) for n in names]


def _append(text: str, extra: str, sep: str = ", ") -> str:
    text = (text or "").rstrip().rstrip(",").rstrip()
    return f"{text}{sep}{extra}" if text else extra


def _missing_tokens(text: str, tokens: str) -> str:
    """The comma-separated ``tokens`` not already in ``text`` (as tokens)."""
    have = {t.strip().lower() for t in re.split(r"[,\n]", text or "")}
    return ", ".join(t for t in (x.strip() for x in tokens.split(",")) if t and t.lower() not in have)


def check_prompt(prompt: str, rating: str) -> None:
    """Refuse a mature request whose free prompt reads as involving a minor."""
    if rating != "mature":
        return
    terms = minor_terms(prompt)
    if terms:
        raise RatingRefused(
            "refused: this is a Mature (adult content) generation and its prompt mentions a minor "
            f"({', '.join(repr(t) for t in terms[:5])}). Mature content is only for adult characters: "
            "remove those words, or set the project's content rating to SFW.")


def decide(requested: str, cast: Iterable[Dict[str, Any]], scene: str = "") -> Dict[str, Any]:
    """The effective rating for ``requested`` and the cast:
    ``{"rating", "requested", "forced", "notice", "cast": [{name, status, reason}]}``."""
    requested = normalize_rating(requested) or "sfw"
    people = []
    for c in cast:
        st = classify(c.get("age"), c.get("text") or c.get("name") or "")
        people.append({"name": c.get("name") or "", **st})
    out = {"rating": requested, "requested": requested, "forced": False, "notice": None, "cast": people}
    if requested != "mature":
        return out
    blocked = [p for p in people if p["status"] != "adult"]
    reasons = [f"{p['name']} is a minor ({p['reason']})" if p["status"] == "minor"
               else f"{p['name']} has {p['reason']}" for p in blocked]
    scene_terms = minor_terms(scene)
    if scene_terms:
        reasons.append(f"the panel's scene mentions a minor (\"{scene_terms[0]}\")")
    if reasons:
        out.update(rating="sfw", forced=True,
                   notice="forced SFW: " + "; ".join(reasons)
                   + ". Mature content is only made when every character on it is a known adult.")
    return out


def apply_rating(prompt: str, negative: str, *, project: Optional[Dict[str, Any]] = None,
                 panel: Optional[Dict[str, Any]] = None,
                 cast: Optional[List[Dict[str, Any]]] = None,
                 rating: Optional[str] = None, free_prompt: Optional[str] = None,
                 force_sfw: bool = False, sep: str = ", ") -> Dict[str, Any]:
    """The rating rules for one generation (call it right before
    generate_image). ``rating`` overrides the project's/global rating;
    ``cast`` overrides the panel's characters (a character sheet passes its
    own); ``free_prompt`` is the user's text checked for minor terms
    (default ``prompt``). Raises RatingRefused for a mature prompt with minor
    terms. Returns ``{"prompt", "negative", "rating", "requested", "forced",
    "notice", "injected"}`` (``injected``: the list entry for the metadata)."""
    requested = "sfw" if force_sfw else (normalize_rating(rating) or project_rating(project))
    check_prompt(prompt if free_prompt is None else free_prompt, requested)
    people = panel_cast(project, panel) if cast is None else cast
    d = decide(requested, people, scene=(panel or {}).get("scene") or "")
    negative = negative or ""
    if d["rating"] == "sfw":
        extra = _missing_tokens(negative, SFW_NEG)
        if extra:
            negative = _append(negative, extra)
    else:
        extra = _missing_tokens(prompt, AGE_POS)
        if extra:
            prompt = _append(prompt, extra, sep)
        extra = _missing_tokens(negative, AGE_NEG)
        if extra:
            negative = _append(negative, extra)
    injected = {"kind": "rating", "rating": d["rating"], "requested": d["requested"]}
    if d["forced"]:
        injected.update(forced=True, notice=d["notice"])
    return {"prompt": prompt, "negative": negative, "rating": d["rating"],
            "requested": d["requested"], "forced": d["forced"], "notice": d["notice"],
            "injected": injected}
