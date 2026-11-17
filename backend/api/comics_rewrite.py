"""Comics tab "AI rewrite": the configured OpenAI-compatible LLM (the owner's
LM Studio, usually) rewrites one block of a .comic script.

POST /api/comics/scripts/{name}/rewrite takes the editor's full text (unsaved
is fine), the block's offsets and an action, asks the model for a replacement
of just that block, and checks the result with ``comic.js --plan --stdin`` on
the text with the block replaced. Nothing is saved: the client shows the
suggestion and puts it in the editor on Accept.

Minor protection: for draft_uncut, and for any action on an uncut block or in
a ``rating: mature`` script, the block's panels are checked with comic.js (its
lib/rating.js rules) BEFORE the model is called: every character on them must
be a known adult, else 400 and the model never sees the block. The suggestion
is checked the same way afterwards.

Offsets are UTF-16 code units (JavaScript string indices), so a textarea's
selectionStart/End can be sent as they are.
"""
import asyncio
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import comics as cm
from ..core.openai_client import OpenAIClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/comics", tags=["comics"])

ACTIONS = ("tighten_dialogue", "enrich_description", "draft_uncut", "custom")
CONTEXT_LINES = 40          # lines of script before and after the block sent for continuity
HEADER_LINES = 120          # at most this many header lines are sent
MAX_TEXT = 1_000_000        # characters of script text accepted
TEMPERATURE = 0.7
MAX_TOKENS = 4096

SYSTEM_PROMPT = """You edit comic scripts written in the plain-text .comic format. A script is a header, then pages and panels:

HEADER (before the first PAGE):
  title: / subtitle: / author: / game: / seed: lines
  character NAME: description      (an invented character's look)
  place key: description           (a place; panels use the key)
  negative NAME: / face NAME: / lora NAME: / ref NAME: lines
  rating: sfw|mature               (sfw is the default)
  age NAME: n                      (a character's age)

PAGE [uncut [todo]] [args]         starts a page; "layout: 1-2" (panels per row) and "layout_uncut:" may follow
PANEL [uncut [todo]] [h=1.2 w=.. seed=..]   starts a panel; then, in any order:
  place: key, time                 key from the header or the game (or free text), time morning|day|evening|night|dawn|dusk|sunset
  cast: kim(casual, smile), mara(work, determined, holding a mug)   left to right; brackets: outfit, expression, free words; "wearing ..." replaces the outfit
  shot: establishing|wide|full|medium|cowboy|closeup|extreme|over|low|high (or own words)
  seats: / neg: / prompt: / model: / regions: / lora: / ref: / face: / rating: lines (panel settings)
  any other line is the panel DESCRIPTION: what the picture shows (it becomes the image prompt)
  NAME (mods): text                speech; mods: whisper, shout, thought, off, "off, left", notail, tl tc tr ml mc mr bl bc br; *word* = emphasis
  CAPTION (pos): text              narration box
  SFX (pos): text                  sound effect
  TEXT (pos): text                 words on a phone or screen
  // comment

Painting rules: descriptions say only what is visible (people, poses, clothes, setting, framing, light); the story goes in the lettering. The image model can't draw text, so no signs or written words in descriptions. Keep two people per panel at most unless it is wide.
"PAGE uncut" / "PANEL uncut" blocks exist only in the mature uncut edition, for adult characters only; "todo" after "uncut" marks a slot not written yet.

HARD RULES:
- Return ONLY the replacement text for the block you are given: no markdown code fences, no commentary, no explanation, no surrounding context.
- Keep the block's structure: the same PAGE/PANEL marker lines with their arguments, the same cast ids, place keys, speaker names and layout lines, in the same order, unless the task says otherwise.
- Never add characters who are not in the block's cast or the header. Every character is an adult; never describe anyone as young, a teen, a child, a student or with an age under 18.
- Keep // comment lines unless the task replaces them."""

ACTION_PROMPTS = {
    "tighten_dialogue": (
        "Tighten the dialogue: rewrite only the speech lines (NAME: text) and the CAPTION and TEXT lines, shorter and "
        "punchier, keeping their meaning, speakers, modifiers and order. Leave every other line exactly as it is."),
    "enrich_description": (
        "Enrich the panel descriptions: rewrite only the description lines (the lines that are not settings, cast, "
        "place, shot or lettering) with concrete visual detail: camera framing, poses, expressions, lighting, what is "
        "in the foreground and background. Describe only what is visible; the story stays in the lettering. Keep the "
        "cast:, shot:, place: and all lettering lines exactly as they are."),
    "draft_uncut": (
        "Draft this uncut (mature, adults only) scene: write the panel description lines for the uncut moment, "
        "continuing from the context, and set the characters' outfits in the cast brackets with \"wearing ...\" where "
        "they change. Keep the cast ids, the place, the PAGE/PANEL marker lines and any lettering lines. Replace "
        "\"// TODO\" placeholder comments with the descriptions."),
    "custom": "Follow the author's instruction below for this block.",
}

_MARKER_RE = re.compile(r"^\s*(PAGE|PANEL)\b")
_UNCUT_MARK_RE = re.compile(r"^(\s*(?:PAGE|PANEL)\s+(?:\d+\s+)?uncut)(\s+todo\b)?")
_PANEL_RATING_RE = re.compile(r"^\s*rating\s*:", re.I)
_HEADER_RATING_RE = re.compile(r"^\s*rating\s*:\s*(\S+)", re.I)
# the prompt's own section markers: distinctive, so an answer that echoes a section can be cut there
SEC_HEADER, SEC_BEFORE, SEC_AFTER, SEC_BLOCK, SEC_END = (
    "<<<SCRIPT_HEADER>>>", "<<<CONTEXT_BEFORE>>>", "<<<CONTEXT_AFTER>>>", "<<<BLOCK>>>", "<<<END>>>")
# a line opening one of the prompt's sections (these markers, the older plain labels, or a TASK/instruction line)
_SECTION_RE = re.compile(
    r"^\s*(?:<<<\s*/?\s*(?:SCRIPT_HEADER|CONTEXT_BEFORE|CONTEXT_AFTER|BLOCK|END)\b[^>\n]*>>>"
    r"|<<<BLOCK\b|BLOCK>>>"
    r"|SCRIPT HEADER:|CONTEXT (?:BEFORE|AFTER) THE BLOCK\b|BLOCK TO REWRITE\b"
    r"|TASK: (?:Tighten|Enrich|Draft|Follow)\b|AUTHOR'S (?:EXTRA )?INSTRUCTION:)")
_BLOCK_START_RE = re.compile(r"^[ \t]*<<<BLOCK>>>[^\n]*\n?", re.M)
_BLOCK_END_RE = re.compile(r"^[ \t]*<<<END>>>", re.M)
# actions that must keep the block's PAGE/PANEL marker lines as they are
STRUCTURE_KEPT = ("tighten_dialogue", "enrich_description")
_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)(?:\n```|\Z)", re.S)
_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.S | re.I)
_CHATTER_RE = re.compile(r"^(here(?:'s| is| are)|sure\b|okay\b|ok\b|certainly|below is|the rewritten|rewritten)", re.I)


class RewriteRequest(BaseModel):
    text: str = Field(max_length=MAX_TEXT)
    start: int
    end: int
    action: str
    instruction: Optional[str] = Field(default=None, max_length=2000)
    model: Optional[str] = Field(default=None, max_length=200)
    remove_todo: bool = False   # draft_uncut: drop "todo" from the block's uncut markers (default: keep, for review)


# ---------------------------------------------------------------------------
# Script structure (enough of the format to find pages, panels and uncut blocks)
# ---------------------------------------------------------------------------

class _Panel:
    __slots__ = ("line", "end", "uncut", "todo", "page")

    def __init__(self, line: int, uncut: bool, todo: bool, page: "_Page"):
        self.line, self.end, self.uncut, self.todo, self.page = line, line, uncut, todo, page


class _Page:
    __slots__ = ("line", "end", "uncut", "todo")

    def __init__(self, line: int, uncut: bool, todo: bool):
        self.line, self.end, self.uncut, self.todo = line, line, uncut, todo


def _structure(lines: List[str]) -> Tuple[int, List[_Page], List[_Panel]]:
    """(index of the first PAGE line (len(lines) if none), pages, panels); 0-based line indices, each with
    its last line (end, inclusive)."""
    pages: List[_Page] = []
    panels: List[_Panel] = []
    for i, line in enumerate(lines):
        m = _MARKER_RE.match(line)
        if not m:
            continue
        u = _UNCUT_MARK_RE.match(line)
        if m.group(1) == "PAGE":
            if pages:
                pages[-1].end = i - 1
            if panels and panels[-1].end < 0:
                panels[-1].end = i - 1
            pages.append(_Page(i, bool(u), bool(u and u.group(2))))
        else:
            if panels and panels[-1].end < 0:
                panels[-1].end = i - 1
            if not pages:
                continue   # a PANEL before any PAGE: comic.js reports it
            p = _Panel(i, bool(u), bool(u and u.group(2)), pages[-1])
            p.end = -1
            panels.append(p)
    if pages:
        pages[-1].end = len(lines) - 1
    if panels and panels[-1].end < 0:
        panels[-1].end = len(lines) - 1
    first_page = pages[0].line if pages else len(lines)
    return first_page, pages, panels


def _line_uncut(i: int, pages: List[_Page], panels: List[_Panel]) -> bool:
    """Whether line i is inside an uncut page or an uncut panel."""
    for p in panels:
        if p.line <= i <= p.end:
            return p.uncut or p.page.uncut
    for pg in pages:
        if pg.line <= i <= pg.end:
            return pg.uncut
    return False


def _u16_index(text: str, off: int) -> int:
    """The str index of a UTF-16 code unit offset (JavaScript string index)."""
    n = 0
    for i, ch in enumerate(text):
        if n >= off:
            if n != off:
                raise HTTPException(status_code=400, detail="an offset splits a character")
            return i
        n += 2 if ord(ch) > 0xFFFF else 1
    if n == off:
        return len(text)
    raise HTTPException(status_code=400, detail="offsets must be within the text")


def _u16_len(text: str) -> int:
    return len(text) + sum(1 for ch in text if ord(ch) > 0xFFFF)


def _line_of(text: str, idx: int) -> int:
    """0-based line index of str index idx."""
    return text.count("\n", 0, idx)


def _block_lines(text: str, start: int, end: int) -> Tuple[int, int]:
    """0-based first and last line of the block [start, end)."""
    # the last character's line: a block ending in a newline doesn't reach into the next line
    return _line_of(text, start), _line_of(text, max(start, end - 1))


def _header_rating(lines: List[str], first_page: int) -> str:
    for line in lines[:first_page]:
        m = _HEADER_RATING_RE.match(line)
        if m:
            return m.group(1).lower()
    return "sfw"


def _has_uncut(lines: List[str]) -> bool:
    return any(_UNCUT_MARK_RE.match(l) for l in lines)


# ---------------------------------------------------------------------------
# Minor protection
# ---------------------------------------------------------------------------

def _minor_check(path, text: str, lo: int, hi: int) -> Optional[Tuple[str, Optional[int]]]:
    """None when every character on the panels touching lines lo..hi (0-based) is a known adult, by comic.js's
    own rules; else (why, script line). The panels are planned as uncut (mature) panels, todo and panel
    "rating:" lines aside, so comic.js classifies their whole cast (and rejects minor words in their text)."""
    lines = text.split("\n")
    _, pages, panels = _structure(lines)
    hit = [p for p in panels if p.line <= hi and p.end >= lo]
    if not hit:
        return None
    probe = list(lines)
    for p in hit:
        if p.page.uncut:
            probe[p.page.line] = _UNCUT_MARK_RE.sub(r"\1", probe[p.page.line], count=1)   # drop todo
            probe[p.line] = _UNCUT_MARK_RE.sub(r"\1", probe[p.line], count=1)
        elif p.uncut:
            probe[p.line] = _UNCUT_MARK_RE.sub(r"\1", probe[p.line], count=1)
        else:
            probe[p.line] = re.sub(r"^(\s*PANEL)\b", r"\1 uncut", probe[p.line], count=1)
        for i in range(p.line + 1, p.end + 1):
            if _PANEL_RATING_RE.match(probe[i]):
                probe[i] = ""   # keeps the line numbers
    plan = cm._run_plan(path, "\n".join(probe), uncut=True)
    if not plan.get("ok"):
        return (f"the block's characters could not be checked: {plan.get('error')}", plan.get("line"))
    by_line = {p.get("line"): p for p in plan.get("panels", []) if p.get("edition", "uncut") == "uncut"}
    for p in hit:
        got = by_line.get(p.line + 1)
        if got is None:
            return (f"the panel at line {p.line + 1} could not be checked", p.line + 1)
        if got.get("rating") != "mature":
            notice = got.get("notice") or "its characters are not all known adults"
            notice = re.sub(r"^painted SFW:\s*", "", notice)
            hint = "" if "add \"age" in notice else " (an \"age NAME: <n>\" line, 18 or over, marks an adult)"
            return (f"panel at line {p.line + 1}: {notice}. Mature and uncut rewrites are for known adults "
                    f"only{hint}", p.line + 1)
    return None


# ---------------------------------------------------------------------------
# Prompt and answer
# ---------------------------------------------------------------------------

def _build_messages(lines: List[str], first_page: int, lo: int, hi: int, block: str, action: str,
                    instruction: Optional[str], uncut_block: bool) -> List[Dict[str, str]]:
    header = [l for l in lines[:min(first_page, lo)] if l.strip() and not l.strip().startswith("//")][:HEADER_LINES]
    before_from = max(first_page, lo - CONTEXT_LINES)
    before = lines[before_from:lo] if lo > first_page else []
    after = lines[hi + 1:hi + 1 + CONTEXT_LINES]
    # the context first (read-only), then the block, then the task last
    parts = [f"{SEC_HEADER} (the script's header; read only)", "\n".join(header) or "(none)", ""]
    if before:
        parts += [f"{SEC_BEFORE} (the script just before the block; read only, never return it)", "\n".join(before), ""]
    if after:
        parts += [f"{SEC_AFTER} (the script just after the block; read only, never return it)", "\n".join(after), ""]
    parts += [f"{SEC_BLOCK} (script lines {lo + 1}-{hi + 1}{', an uncut block: mature, adults only' if uncut_block else ''})",
              block.strip("\n"), SEC_END, ""]
    parts += ["TASK: " + ACTION_PROMPTS[action]]
    if instruction:
        parts += [("AUTHOR'S INSTRUCTION: " if action == "custom" else "AUTHOR'S EXTRA INSTRUCTION: ") + instruction]
    parts += ["", f"Return only the rewritten block, between a {SEC_BLOCK} line and an {SEC_END} line: nothing of the "
              "header or the context, nothing after it."]
    return [{"role": "user", "content": "\n".join(parts).replace("\r", "")}]


def _clean(answer: str, original: str) -> str:
    """The model's answer as a drop-in replacement for original: no think block, fences or chatter, and the
    original's leading/trailing whitespace and line endings."""
    s = _THINK_RE.sub("", answer or "").replace("\r\n", "\n")
    m = _BLOCK_START_RE.search(s)
    if m:
        # the answer as asked for: between <<<BLOCK>>> and <<<END>>> (or the end)
        s = s[m.end():]
        e = _BLOCK_END_RE.search(s)
        if e:
            s = s[:e.start()]
    m = _FENCE_RE.search(s)
    if m:
        s = m.group(1)
    body = s.strip("\n").split("\n")
    # an echoed prompt section (the context after the block, say) ends the answer; a marker line before any
    # content is dropped
    while body and (not body[0].strip() or _SECTION_RE.match(body[0])):
        body = body[1:]
    cut = next((i for i, l in enumerate(body) if _SECTION_RE.match(l)), None)
    if cut is not None:
        body = body[:cut]
    while body and not body[-1].strip():
        body = body[:-1]
    orig_lines = [l for l in original.replace("\r\n", "\n").split("\n") if l.strip()]
    starts_marker = bool(orig_lines and _MARKER_RE.match(orig_lines[0]))
    if starts_marker:
        # the block starts with PAGE/PANEL: anything before the model's first marker is chatter
        k = next((i for i, l in enumerate(body) if _MARKER_RE.match(l)), None)
        if k:
            body = body[k:]
    while body and _CHATTER_RE.match(body[0].strip()) and body[0].rstrip().endswith(":"):
        body = body[1:]
    core = "\n".join(body).strip("\n")
    norm = original.replace("\r\n", "\n")
    lead = re.match(r"^\s*", norm).group(0)
    lead = lead[:lead.rfind("\n") + 1] if "\n" in lead else ""
    trail = re.search(r"\s*$", norm).group(0)
    trail = trail[trail.find("\n"):] if "\n" in trail else ""
    out = lead + core + trail
    return out.replace("\n", "\r\n") if "\r\n" in original else out


def _markers(block: str) -> List[str]:
    """The block's PAGE/PANEL marker lines, whitespace normalised."""
    return [" ".join(l.split()) for l in block.replace("\r\n", "\n").split("\n") if _MARKER_RE.match(l)]


def _structure_error(original: str, suggestion: str) -> Optional[str]:
    """None when the suggestion has the original's PAGE/PANEL marker lines, in order and with their arguments."""
    want, got = _markers(original), _markers(suggestion)
    if want == got:
        return None
    n = sum(1 for l in want if l.startswith("PANEL"))
    m = sum(1 for l in got if l.startswith("PANEL"))
    msg = f"the model changed the panel structure (expected {n} panel{'s' if n != 1 else ''}, got {m})"
    if len(want) == len(got):
        i = next(i for i, (a, b) in enumerate(zip(want, got)) if a != b)
        msg += f": \"{want[i]}\" became \"{got[i]}\""
    elif n == m:
        msg += f": expected {len(want)} PAGE/PANEL lines, got {len(got)}"
    return msg


def _fix_todo(suggestion: str, original: str, remove: bool) -> str:
    """draft_uncut: the uncut markers keep their todo (the owner reviews the draft), or lose it on request."""
    orig = [l for l in original.split("\n") if _MARKER_RE.match(l)]
    out = suggestion.split("\n")
    marks = [i for i, l in enumerate(out) if _MARKER_RE.match(l)]
    for n, i in enumerate(marks):
        u = _UNCUT_MARK_RE.match(out[i])
        if not u:
            continue
        o = _UNCUT_MARK_RE.match(orig[n]) if n < len(orig) else None
        had_todo = bool(o and o.group(2))
        if remove and u.group(2):
            out[i] = _UNCUT_MARK_RE.sub(r"\1", out[i], count=1)
        elif not remove and had_todo and not u.group(2):
            out[i] = out[i][:u.end(1)] + " todo" + out[i][u.end(1):]
    return "\n".join(out)


def _llm_error(e: Exception) -> HTTPException:
    msg = str(e) or e.__class__.__name__
    low = msg.lower()
    hint = ""
    if "unexpected endpoint" in low or "404" in low[:20]:
        hint = " (check Settings: the LLM endpoint should end with /v1, e.g. http://127.0.0.1:1234/v1)"
    elif "crash" in low:
        hint = " (the model crashed in LM Studio: reload it there, or pick another model)"
    elif "connect" in low or "refused" in low:
        hint = " (is LM Studio's server running? Check the endpoint in Settings)"
    elif "timeout" in low or "timed out" in low:
        hint = " (the model took too long; try a smaller block or a faster model)"
    return HTTPException(status_code=502, detail=f"the LLM failed: {msg[:600]}{hint}")


def _plan_status(plan: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": bool(plan.get("ok")), "error": plan.get("error"), "line": plan.get("line")}


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------

@router.post("/scripts/{name}/rewrite")
async def rewrite_block(name: str, req: RewriteRequest):
    path = cm._script_path(name)
    if req.action not in ACTIONS:
        raise HTTPException(status_code=400, detail=f"action must be one of {list(ACTIONS)}")
    instruction = (req.instruction or "").strip() or None
    if req.action == "custom" and not instruction:
        raise HTTPException(status_code=400, detail="a custom rewrite needs an instruction")
    text = req.text
    if not (0 <= req.start <= req.end <= _u16_len(text)):
        raise HTTPException(status_code=400, detail="the block must satisfy 0 <= start <= end <= the text's length")
    start, end = _u16_index(text, req.start), _u16_index(text, req.end)
    original = text[start:end]
    if not original.strip():
        raise HTTPException(status_code=400, detail="the block is empty")

    lines = text.split("\n")
    first_page, pages, panels = _structure(lines)
    lo, hi = _block_lines(text, start, end)
    uncut_block = any(_line_uncut(i, pages, panels) for i in range(lo, hi + 1))
    all_uncut = all(_line_uncut(i, pages, panels) for i in range(lo, hi + 1))
    if req.action == "draft_uncut" and not all_uncut:
        raise HTTPException(status_code=400,
                            detail="Draft uncut scene works only inside a PAGE uncut / PANEL uncut block")
    mature = _header_rating(lines, first_page) == "mature"
    guarded = req.action == "draft_uncut" or uncut_block or mature

    # concurrent rewrites are allowed (LM Studio queues them): a cancelled request keeps running on the
    # server until the model answers, and must not block the retry
    if guarded:
        # BEFORE the model sees anything: every character on the block's panels must be a known adult
        refused = await asyncio.to_thread(_minor_check, path, text, lo, hi)
        if refused:
            raise HTTPException(status_code=400, detail=f"Not sent to the model: {refused[0]}")

    llm = OpenAIClient.for_request(model=(req.model or "").strip() or None, temperature=TEMPERATURE)
    llm.update_config(max_tokens=MAX_TOKENS)
    if not llm.endpoint or not llm.model:
        raise HTTPException(status_code=400, detail="no LLM configured: set the endpoint and model in Settings")
    messages = _build_messages(lines, first_page, lo, hi, original, req.action, instruction, uncut_block)
    t0 = time.monotonic()
    try:
        result = await llm.chat_completion(messages, temperature=TEMPERATURE, system_prompt=SYSTEM_PROMPT)
        answer = result["choices"][0]["message"]["content"] or ""
    except HTTPException:
        raise
    except Exception as e:   # transport errors, non-200s, odd bodies
        logger.warning("comics rewrite: LLM failed: %s", e)
        raise _llm_error(e)
    duration = int((time.monotonic() - t0) * 1000)

    suggestion = _clean(answer, original)
    if req.action == "draft_uncut":
        suggestion = _fix_todo(suggestion, original, req.remove_todo)
    if not suggestion.strip():
        raise HTTPException(status_code=502, detail="the LLM returned an empty answer")

    new_text = text[:start] + suggestion + text[end:]
    new_lines = new_text.split("\n")
    plan = await asyncio.to_thread(cm._run_plan, path, new_text, False, _has_uncut(new_lines))
    status = _plan_status(plan)
    if req.action in STRUCTURE_KEPT:
        # a duplicated or dropped panel is valid script, so the plan can't catch it: compare the markers
        broken = _structure_error(original, suggestion)
        if broken:
            status = {"ok": False, "error": broken, "line": lo + 1}
    if status["ok"] and guarded:
        n_lo, n_hi = _block_lines(new_text, start, start + len(suggestion))
        refused = await asyncio.to_thread(_minor_check, path, new_text, n_lo, n_hi)
        if refused:
            status = {"ok": False, "error": f"minor protection: {refused[0]}", "line": refused[1]}
    return {"suggestion": suggestion, "original": original, "plan": status, "model": llm.model,
            "durationMs": duration, "start": req.start, "end": req.end, "action": req.action}
