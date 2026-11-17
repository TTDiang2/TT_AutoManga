"""Project collections: projects grouped as the episodes of a series.

data/collections.json holds a list of
{id, name, description, projectIds: [ordered], cover: {projectId, pageId}|None,
 auto, createdAt, updatedAt}. A project may sit in several collections. Every
read-modify-write runs under one module lock and the file is written
atomically. Ids of projects that no longer exist are kept on disk (a project
dir can come back from a backup) but skipped, with a warning, by listing and
export; deleting a project through StorageManager.delete_project removes it
from every collection.

Auto-grouping (POST /api/collections/auto-group) reads series titles from
project names: "<Title> — <Subtitle>" (the Comics converter's em dash; " - "
and " – " too) or projects sharing an exact name, ordered by the episode/part
number in the subtitle. The uncut edition of a Comics script (its project
marked ``settings.comicScript: "<name>:uncut"``, named "<Title> (Uncut) — …")
always goes into its own collection, "<Title> (Uncut)", never with the
regular episodes; such a collection is stored with ``mature: true`` (the
Showcase blurs mature collections).
"""
import json
import logging
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..core.config import DATA_DIR, atomic_write_json

logger = logging.getLogger(__name__)

COLLECTIONS_FILE = DATA_DIR / "collections.json"

_lock = threading.RLock()


class CollectionError(ValueError):
    """Invalid collection input (unknown project, duplicate id, bad name)."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> List[Dict[str, Any]]:
    f = COLLECTIONS_FILE
    if not f.exists():
        return []
    try:
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as e:
        logger.warning("collections.json unreadable (%s); treating as empty", e)
        return []
    if not isinstance(data, list):
        logger.warning("collections.json is not a list; treating as empty")
        return []
    return [c for c in data if isinstance(c, dict) and c.get("id")]


def _save(items: List[Dict[str, Any]]) -> None:
    atomic_write_json(COLLECTIONS_FILE, items, indent=2, ensure_ascii=False)


def _project_exists(pid: str) -> bool:
    from . import manager
    try:
        manager.validate_project_id(pid)
    except manager.InvalidProjectIdError:
        return False
    return (manager.PROJECTS_DIR / pid / "project.json").is_file()


def _check_project_ids(ids: Any) -> List[str]:
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise CollectionError("projectIds must be a list of project ids")
    if len(set(ids)) != len(ids):
        raise CollectionError("projectIds must not contain duplicates")
    missing = [i for i in ids if not _project_exists(i)]
    if missing:
        raise CollectionError(f"unknown project id(s): {', '.join(missing)}")
    return list(ids)


def _check_name(name: Any) -> str:
    if not isinstance(name, str) or not name.strip():
        raise CollectionError("name is required")
    return name.strip()[:200]


def _check_cover(cover: Any, project_ids: List[str]) -> Optional[Dict[str, str]]:
    if cover is None:
        return None
    if not isinstance(cover, dict) or not isinstance(cover.get("projectId"), str):
        raise CollectionError("cover must be {projectId, pageId} or null")
    if cover["projectId"] not in project_ids:
        raise CollectionError("cover project is not an episode of this collection")
    page_id = cover.get("pageId")
    if page_id is not None and not isinstance(page_id, str):
        raise CollectionError("cover.pageId must be a string")
    return {"projectId": cover["projectId"], "pageId": page_id}


def list_collections() -> List[Dict[str, Any]]:
    with _lock:
        return _load()


def get_collection(cid: str) -> Optional[Dict[str, Any]]:
    with _lock:
        return next((c for c in _load() if c.get("id") == cid), None)


def create_collection(name: Any, project_ids: Any = None,
                      description: Optional[str] = None,
                      auto: bool = False) -> Dict[str, Any]:
    name = _check_name(name)
    ids = _check_project_ids(project_ids if project_ids is not None else [])
    now = _now()
    col = {"id": uuid.uuid4().hex, "name": name,
           "description": (description or "").strip(),
           "projectIds": ids, "cover": None, "auto": bool(auto),
           "createdAt": now, "updatedAt": now}
    with _lock:
        items = _load()
        items.append(col)
        _save(items)
    return col


def update_collection(cid: str, changes: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Apply {name?, description?, projectIds?, cover?}; None if no such
    collection. Any user edit turns an auto collection into a manual one."""
    with _lock:
        items = _load()
        col = next((c for c in items if c.get("id") == cid), None)
        if col is None:
            return None
        if "name" in changes and changes["name"] is not None:
            col["name"] = _check_name(changes["name"])
        if "description" in changes and changes["description"] is not None:
            if not isinstance(changes["description"], str):
                raise CollectionError("description must be a string")
            col["description"] = changes["description"].strip()[:2000]
        if "projectIds" in changes and changes["projectIds"] is not None:
            col["projectIds"] = _check_project_ids(changes["projectIds"])
            cover = col.get("cover")
            if cover and cover.get("projectId") not in col["projectIds"]:
                col["cover"] = None
        if "cover" in changes:
            col["cover"] = _check_cover(changes["cover"], col["projectIds"])
        col["auto"] = False
        col["updatedAt"] = _now()
        _save(items)
        return col


def delete_collection(cid: str) -> bool:
    with _lock:
        items = _load()
        kept = [c for c in items if c.get("id") != cid]
        if len(kept) == len(items):
            return False
        _save(kept)
        return True


def remove_project(project_id: str) -> int:
    """Drop a (deleted) project from every collection; returns how many
    collections changed. Never raises: a failure here must not fail the
    project delete that already happened."""
    try:
        with _lock:
            items = _load()
            changed = 0
            for c in items:
                ids = c.get("projectIds") or []
                if project_id in ids:
                    c["projectIds"] = [i for i in ids if i != project_id]
                    if (c.get("cover") or {}).get("projectId") == project_id:
                        c["cover"] = None
                    c["updatedAt"] = _now()
                    changed += 1
            if changed:
                _save(items)
            return changed
    except Exception as e:
        logger.warning("could not remove project %s from collections: %s",
                       project_id, e)
        return 0


# ---------------------------------------------------------------- auto-group

# " — " (spaces optional) as the Comics converter writes it; " – " / " - "
# only with spaces, so "Spider-Man" stays one word
_SEP_RE = re.compile(r"\s*—\s*|\s+[–-]\s+")

_NUM_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve "
    "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty"
    .split())}
_ORDINALS = {w: i + 1 for i, w in enumerate(
    "first second third fourth fifth sixth seventh eighth ninth tenth".split())}

_EPISODE_RE = re.compile(
    r"\b(?:episode|ep|part|pt|chapter|ch|volume|vol|book|issue)(?:\.|\b|(?=\d))"
    r"\s*#?\s*([0-9]+|[a-z]+)\b", re.IGNORECASE)
_ORDINAL_PART_RE = re.compile(r"\b([a-z]+)\s+(?:part|episode|chapter)\b",
                              re.IGNORECASE)
_HASH_RE = re.compile(r"#\s*([0-9]+)\b")
_ROMAN = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100}


def _roman(s: str) -> Optional[int]:
    s = s.lower()
    if not s or any(ch not in _ROMAN for ch in s):
        return None
    total = 0
    for i, ch in enumerate(s):
        v = _ROMAN[ch]
        total += -v if i + 1 < len(s) and _ROMAN[s[i + 1]] > v else v
    return total if 0 < total < 400 else None


def _number(token: str) -> Optional[int]:
    t = token.lower()
    if t.isdigit():
        return int(t)
    if t in _NUM_WORDS:
        return _NUM_WORDS[t]
    if t in _ORDINALS:
        return _ORDINALS[t]
    return _roman(t)


def split_title(name: str) -> Tuple[str, str]:
    """("Jade & Haile", "Episode 1 — The Rainy Gym") for
    "Jade & Haile — Episode 1 — The Rainy Gym"; (name, "") without a separator."""
    name = (name or "").strip()
    m = _SEP_RE.search(name)
    if not m or m.start() == 0:
        return name, ""
    return name[:m.start()].strip(), name[m.end():].strip()


def episode_number(subtitle: str) -> Optional[int]:
    """Episode/part number in a subtitle: "Episode 3", "Ep. 3", "Part Two",
    "Part 2", "Part II", "Chapter 4", "#5", "Second Part"; None if none."""
    for m in _EPISODE_RE.finditer(subtitle or ""):
        n = _number(m.group(1))
        if n is not None:
            return n
    m = _ORDINAL_PART_RE.search(subtitle or "")
    if m and m.group(1).lower() in _ORDINALS:
        return _ORDINALS[m.group(1).lower()]
    m = _HASH_RE.search(subtitle or "")
    return int(m.group(1)) if m else None


def _episode_sort_key(project: Dict[str, Any]):
    _, sub = split_title(project.get("name", ""))
    n = episode_number(sub)
    # numbered episodes first, in number order; the rest by name
    return (n is None, n if n is not None else 0,
            (project.get("name") or "").lower(), project.get("id", ""))


def order_episodes(projects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(projects, key=_episode_sort_key)


UNCUT_SUFFIX = " (Uncut)"
_UNCUT_RE = re.compile(r"\s*\(uncut\)\s*$", re.IGNORECASE)


def is_uncut(project: Dict[str, Any]) -> bool:
    """An uncut edition: marked so by the Comics converter, or named "<Title> (Uncut)…"."""
    mark = (project.get("settings") or {}).get("comicScript")
    if isinstance(mark, str) and mark.endswith(":uncut"):
        return True
    base, _ = split_title(project.get("name", ""))
    return bool(_UNCUT_RE.search(base))


def group_title(project: Dict[str, Any]) -> str:
    """The collection a project auto-groups into: its base title, with
    " (Uncut)" for an uncut edition (so it never joins the regular episodes)."""
    base, _ = split_title(project.get("name", ""))
    if base and is_uncut(project):
        base = _UNCUT_RE.sub("", base).strip() + UNCUT_SUFFIX
    return base


def auto_groups(projects: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """base title -> ordered project ids, for titles with >= 2 projects."""
    by_base: Dict[str, List[Dict[str, Any]]] = {}
    for p in projects:
        if not p.get("id"):
            continue
        base = group_title(p)
        if base:
            by_base.setdefault(base, []).append(p)
    return {base: [p["id"] for p in order_episodes(ps)]
            for base, ps in by_base.items() if len(ps) >= 2}


def auto_group(projects: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Create / refresh auto collections from project names. A collection
    the user made or edited (auto false) is never changed; a title it
    already covers is reported under ``skipped``."""
    groups = auto_groups(projects)
    uncut_titles = {group_title(p) for p in projects if p.get("id") and is_uncut(p)}
    created: List[Dict[str, Any]] = []
    updated: List[Dict[str, Any]] = []
    unchanged: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    with _lock:
        items = _load()
        for base, ids in groups.items():
            same = [c for c in items if c.get("name") == base]
            manual = next((c for c in same if not c.get("auto")), None)
            if manual is not None:
                skipped.append({"id": manual["id"], "name": base,
                                "reason": "a manual collection has this name"})
                continue
            existing = next((c for c in same if c.get("auto")), None)
            if existing is None:
                now = _now()
                col = {"id": uuid.uuid4().hex, "name": base, "description": "",
                       "projectIds": ids, "cover": None, "auto": True,
                       "createdAt": now, "updatedAt": now}
                if base in uncut_titles:
                    col["mature"] = True
                items.append(col)
                created.append({"id": col["id"], "name": base, "projectIds": ids})
            elif existing.get("projectIds") != ids or (base in uncut_titles and not existing.get("mature")):
                existing["projectIds"] = ids
                if base in uncut_titles:
                    existing["mature"] = True
                if (existing.get("cover") or {}).get("projectId") not in ids:
                    existing["cover"] = None
                existing["updatedAt"] = _now()
                updated.append({"id": existing["id"], "name": base, "projectIds": ids})
            else:
                unchanged.append({"id": existing["id"], "name": base})
        if created or updated:
            _save(items)
    return {"created": created, "updated": updated, "unchanged": unchanged,
            "skipped": skipped}
