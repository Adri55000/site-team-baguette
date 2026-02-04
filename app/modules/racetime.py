# app/modules/racetime.py
#
# Helpers for racetime.gg integration (read-only).
#
# This module is aligned with Racetime's race data endpoint:
#   https://racetime.gg/<category>/<race>/data
#
# Key points from the API doc:
# - race["status"] is an object: {"value": "...", "verbose_value": "...", "help_text": "..."}
# - each entrant["status"] is also an object with the same keys
# - entrant["finish_time"] is an ISO 8601 duration (e.g. "PT2H13M45S") or null
#
# Project expectations:
# - players.racetime_user: "username#1234"
# - matches.racetime_room: full URL like "https://racetime.gg/<category>/<race_slug>"
#   (path-only accepted too, for robustness)
#
# Team result aggregation for co-op:
# - Team time = LAST finisher time among the team's players (max finish_time)
# - If any player is DQ => team is DQ
# - Else if any player is DNF => team is DNF

from __future__ import annotations
from flask_babel import gettext as _
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import re

import requests


# ----------------------------
# Public exceptions
# ----------------------------

class RacetimeError(Exception):
    """Base error for racetime integration."""


class RacetimeRoomInvalid(RacetimeError):
    """Raised when racetime_room cannot be normalized."""


class RacetimeFetchError(RacetimeError):
    """Raised when racetime API cannot be reached or returns invalid data."""


# ----------------------------
# Normalization utilities
# ----------------------------

def normalize_room_to_path(racetime_room: str) -> str:
    """
    Normalize a racetime room identifier to a path: "<category>/<race_slug>".

    Accepts:
      - Full URL: "https://racetime.gg/ootr/social-kirby-4429"
      - Path: "ootr/social-kirby-4429" or "/ootr/social-kirby-4429"

    Returns:
      - "ootr/social-kirby-4429"

    Raises:
      - RacetimeRoomInvalid
    """
    room = (racetime_room or "").strip()
    if not room:
        raise RacetimeRoomInvalid(_("Empty racetime_room"))

    if room.startswith(("http://", "https://")):
        parsed = urlparse(room)
        path = (parsed.path or "").strip("/")
    else:
        path = room.strip("/")

    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        raise RacetimeRoomInvalid(
            _("racetime_room must look like '<category>/<race_slug>' or a full URL")
        )

    # Keep only "<category>/<race>"
    return f"{parts[0]}/{parts[1]}"


def build_data_url(racetime_room: str) -> str:
    """Build the racetime 'data' endpoint URL for a given room."""
    path = normalize_room_to_path(racetime_room)
    return f"https://racetime.gg/{path}/data"


# ----------------------------
# Time parsing/formatting
# ----------------------------

_ISO8601_DURATION_RE = re.compile(
    r"^P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$"
)


def iso8601_duration_to_seconds(duration: Optional[str]) -> Optional[int]:
    """
    Convert ISO 8601 durations to seconds.
    Supports both:
      - 'PT2H13M45S'
      - 'P0DT01H40M58.575274S' (days + fractional seconds)
    Returns None for empty/unknown formats.
    """
    if not duration:
        return None

    s = duration.strip()

    # Some implementations emit 'PT...' (without days) – normalize to 'P0DT...'
    if s.startswith("PT"):
        s = "P0D" + s[1:]  # "PT..." -> "P0DT..."

    m = _ISO8601_DURATION_RE.match(s)
    if not m:
        return None

    days = int(m.group(1) or 0)
    hours = int(m.group(2) or 0)
    minutes = int(m.group(3) or 0)
    seconds_float = float(m.group(4) or 0.0)

    total = days * 86400 + hours * 3600 + minutes * 60 + seconds_float

    # On renvoie un int (arrondi vers le bas) car ton format final est HH:MM:SS
    return int(total)


def seconds_to_hms(total_seconds: int) -> str:
    """Format seconds into HH:MM:SS (zero-padded)."""
    if total_seconds < 0:
        total_seconds = 0
    h = total_seconds // 3600
    rem = total_seconds % 3600
    m = rem // 60
    s = rem % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


# ----------------------------
# Racetime JSON helpers (aligned with API doc)
# ----------------------------

def racetime_user_from_user_obj(user_obj: Dict[str, Any]) -> Optional[str]:
    """
    Build 'username#1234' from racetime 'user' blob (entrant["user"]).
    Expected keys: name, discriminator.
    """
    if not user_obj:
        return None
    name = (user_obj.get("name") or "").strip()
    disc = (user_obj.get("discriminator") or "").strip()
    if not name or not disc:
        return None
    return f"{name}#{disc}"


def status_value(status_obj: Any) -> str:
    """
    Racetime status is an object with keys:
      - value
      - verbose_value
      - help_text
    Entrant status uses the same structure.

    Returns the machine-parsable status string (lowercase), or "".
    """
    if status_obj is None:
        return ""
    if isinstance(status_obj, str):
        # Defensive: if API ever returns a string
        return status_obj.strip().lower()
    if isinstance(status_obj, dict):
        v = status_obj.get("value")
        if isinstance(v, str):
            return v.strip().lower()
        return ""
    return ""


def entrants_index_by_racetime_user(race_json: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Index entrants by 'username#1234' for quick lookups.
    """
    entrants = race_json.get("entrants") or []
    index: Dict[str, Dict[str, Any]] = {}
    for entrant in entrants:
        user_blob = entrant.get("user") or {}
        rt_user = racetime_user_from_user_obj(user_blob)
        if rt_user:
            index[rt_user] = entrant
    return index


# ----------------------------
# Fetching
# ----------------------------

def fetch_race_data(racetime_room: str, *, timeout: float = 6.0) -> Dict[str, Any]:
    """
    Fetch race data JSON from racetime:
      https://racetime.gg/<category>/<race>/data

    Raises:
      - RacetimeRoomInvalid
      - RacetimeFetchError
    """
    url = build_data_url(racetime_room)

    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "TeamBaguette/1.0 (+racetime prefill)"},
        )
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            raise RacetimeFetchError(_("Invalid racetime payload (not a dict)"))
        return data
    except RacetimeRoomInvalid:
        raise
    except Exception as e:
        raise RacetimeFetchError(_("Failed to fetch racetime data")) from e


# ----------------------------
# Team aggregation (co-op)
# ----------------------------

@dataclass(frozen=True)
class TeamPrefillResult:
    """
    Computed prefill suggestion for one team.

    raw is formatted for your existing parse_final_time:
      - "HH:MM:SS" or "DNF" or "DQ" (or "" if unknown / not finished)
    """
    raw: str
    details: Dict[str, Any]


def compute_team_prefill_from_racetime_users(
    team_racetime_users: List[str],
    entrants_index: Dict[str, Dict[str, Any]],
) -> TeamPrefillResult:
    """
    Compute a single team result from multiple racetime users.

    API doc entrant status values (machine) include:
      requested, invited, declined, partitioned, ready, not_ready,
      in_progress, done, dnf, dq

    Team aggregation rules:
      - If any player is dq => team "DQ"
      - Else if any player is dnf => team "DNF"
      - Else if players have finish_time => team time = max(finish_time) (last finisher)
      - Else => "" (not enough info to prefill)
    """
    users = [u.strip() for u in (team_racetime_users or []) if u and u.strip()]
    missing_users = [u for u in users if u not in entrants_index]

    statuses: List[Tuple[str, str]] = []   # (user, status_value)
    times_sec: List[Tuple[str, int]] = []  # (user, seconds)

    for u in users:
        entrant = entrants_index.get(u)
        if not entrant:
            continue

        st = status_value(entrant.get("status"))
        statuses.append((u, st))

        # finish_time is ISO8601 duration or null
        sec = iso8601_duration_to_seconds(entrant.get("finish_time"))
        if sec is not None:
            times_sec.append((u, sec))

    # Severity: dq > dnf > time
    if any(st == "dq" for _, st in statuses):
        return TeamPrefillResult(
            raw="DQ",
            details={
                "missing_users": missing_users,
                "statuses": statuses,
                "times_sec": times_sec,
            },
        )

    if any(st == "dnf" for _, st in statuses):
        return TeamPrefillResult(
            raw="DNF",
            details={
                "missing_users": missing_users,
                "statuses": statuses,
                "times_sec": times_sec,
            },
        )

    # If we have at least one time, pick last finisher (max seconds)
    if times_sec:
        last_user, last_sec = max(times_sec, key=lambda x: x[1])
        return TeamPrefillResult(
            raw=seconds_to_hms(last_sec),
            details={
                "missing_users": missing_users,
                "statuses": statuses,
                "last_user": last_user,
                "last_sec": last_sec,
                "times_sec": times_sec,
            },
        )

    # Not finished / no usable times
    return TeamPrefillResult(
        raw="",
        details={
            "missing_users": missing_users,
            "statuses": statuses,
            "times_sec": times_sec,
        },
    )


def build_prefill_payload_for_teams(
    team_to_racetime_users: Dict[int, List[str]],
    race_json: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Build a list of {team_id, raw} results suitable for the JS prefill.

    Returns:
      - results: list of dicts {team_id, raw}
      - meta: dict with potential problems

    meta shape:
      {
        "race_status": "<value>",  # e.g. "in_progress", "finished"
        "missing_users_by_team": {team_id: [..]},
        "empty_results": [team_id, ...]
      }
    """
    entrants_index = entrants_index_by_racetime_user(race_json)

    results: List[Dict[str, Any]] = []
    missing_users_by_team: Dict[int, List[str]] = {}
    empty_results: List[int] = []

    for team_id, users in team_to_racetime_users.items():
        res = compute_team_prefill_from_racetime_users(users, entrants_index)
        results.append({"team_id": team_id, "raw": res.raw})

        missing = res.details.get("missing_users") or []
        if missing:
            missing_users_by_team[team_id] = list(missing)

        if res.raw == "":
            empty_results.append(team_id)

    meta = {
        "race_status": status_value((race_json.get("status") or {})),
        "missing_users_by_team": missing_users_by_team,
        "empty_results": empty_results,
    }
    return results, meta

# ----------------------------
# Overlay extraction (per entrant)
# ----------------------------

# ----------------------------
# Overlay extraction (per entrant)
# ----------------------------

@dataclass(frozen=True)
class EntrantOverlayInfo:
    racetime_user: str
    status: str               # done / in_progress / dnf / dq / ...
    twitch_name: str          # best effort
    twitch_channel: str       # best effort
    finish_time_hms: str      # "HH:MM:SS" or ""


def _twitch_name_from_channel_url(url: str) -> str:
    if not url:
        return ""
    u = url.strip().rstrip("/")
    m = re.search(r"twitch\.tv/([^/?#]+)", u, re.IGNORECASE)
    return (m.group(1) if m else "").strip()


def extract_entrants_overlay_info(race_json: Dict[str, Any]) -> Dict[str, EntrantOverlayInfo]:
    """
    Returns dict keyed by 'username#1234' => twitch + status + final time.
    """
    out: Dict[str, EntrantOverlayInfo] = {}
    for entrant in (race_json.get("entrants") or []):
        user_blob = entrant.get("user") or {}
        rt_user = racetime_user_from_user_obj(user_blob)
        if not rt_user:
            continue

        st = status_value(entrant.get("status"))

        twitch_channel = (user_blob.get("twitch_channel") or "").strip()
        twitch_name = (user_blob.get("twitch_name") or "").strip()
        if not twitch_name and twitch_channel:
            twitch_name = _twitch_name_from_channel_url(twitch_channel)

        finish_hms = ""
        finish_raw = entrant.get("finish_time")
        sec = iso8601_duration_to_seconds(finish_raw)
        if sec is not None:
            finish_hms = seconds_to_hms(sec)

        out[rt_user] = EntrantOverlayInfo(
            racetime_user=rt_user,
            status=st,
            twitch_name=twitch_name,
            twitch_channel=twitch_channel,
            finish_time_hms=finish_hms,
        )

    return out

# app/modules/racetime.py

# app/modules/racetime.py

ALLOWED_INTERVIEW_STATUSES = {"in_progress", "done", "dnf", "dq"}


def extract_interview_top8(race_json: dict, limit: int = 5) -> list[dict]:
    """
    Extrait une liste ordonnée (ordre Racetime) des entrants à afficher
    pour l'overlay interview.

    Format retourné :
    [
        {"name": str, "twitch": str, "status": str, "time": str},
        ...
    ]
    """
    results: list[dict] = []

    entrants = race_json.get("entrants") or []
    for entrant in entrants:
        if len(results) >= limit:
            break

        status = status_value(entrant.get("status"))
        if status not in ALLOWED_INTERVIEW_STATUSES:
            continue

        user = entrant.get("user") or {}

        # Nom (Racetime)
        name = (user.get("name") or "").strip()

        # Twitch (best effort) - aligné sur extract_entrants_overlay_info
        twitch_name = (user.get("twitch_name") or "").strip()
        twitch_channel = (user.get("twitch_channel") or "").strip()
        twitch = twitch_name or twitch_channel or ""

        # Temps final (Racetime) : champ entrant["finish_time"]
        time_hms = ""
        if status == "done":
            finish_raw = entrant.get("finish_time")
            sec = iso8601_duration_to_seconds(finish_raw)
            if sec is not None:
                time_hms = seconds_to_hms(sec)

        results.append({
            "name": name,
            "twitch": twitch,
            "status": status,
            "time": time_hms,
        })

    return results
