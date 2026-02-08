from datetime import datetime

from flask import render_template, abort, jsonify, url_for
from flask_babel import get_locale as babel_get_locale

from .. import restream_bp

from app.database import get_db
from app.modules.i18n import get_translation
from app.modules.tournaments import overlay_tournament_name

from app.restream.queries import (
    get_active_restream_by_slug,
    get_match_teams,
    get_next_planned_match_for_overlay,
    simplify_restream_title,
    split_commentators,
)

from app.modules.overlay.registry import resolve_overlay_pack_for_match
from app.modules.tracker.registry import get_tracker_definition
from app.modules.tracker.base import (
    load_session_restream,
    ensure_session_restream,
    save_session_restream,
)
from app.modules.racetime import (
    fetch_race_data,
    extract_entrants_overlay_info,
    extract_interview_top8,
)


@restream_bp.get("/<slug>/overlay")
def restream_overlay(slug: str):
    db = get_db()

    restream = db.execute(
        """
        SELECT
            id,
            slug,
            title,
            match_id,
            is_active,
            commentator_name,
            tracker_type
        FROM restreams
        WHERE slug = ? AND is_active = 1
        """,
        (slug,),
    ).fetchone()

    if not restream:
        abort(404)

    # --------------------------------------------------------------
    # Tracker désactivé → overlay vide / 404
    # --------------------------------------------------------------
    if restream["tracker_type"] == "none":
        abort(404)

    tracker_type = restream["tracker_type"]

    # --------------------------------------------------------------
    # Récupération définition tracker
    # --------------------------------------------------------------
    try:
        tracker_def = get_tracker_definition(tracker_type)
    except KeyError:
        abort(500)  # incohérence DB

    # --------------------------------------------------------------
    # Participants (teams du match)
    # --------------------------------------------------------------
    teams = get_match_teams(db, restream["match_id"])

    participants_count = max(1, len(teams))
    
    # --------------------------------------------------------------
    # Racetime (twitch + temps final) pour overlay
    # --------------------------------------------------------------
    match_row = db.execute(
        "SELECT racetime_room FROM matches WHERE id = ?",
        (restream["match_id"],),
    ).fetchone()

    racetime_room = (match_row["racetime_room"] if match_row else "") or ""

    def team_racetime_users(team_id: int) -> list[str]:
        rows = db.execute(
            """
            SELECT p.racetime_user
            FROM team_players tp
            JOIN players p ON p.id = tp.player_id
            WHERE tp.team_id = ?
            ORDER BY tp.position ASC
            """,
            (team_id,),
        ).fetchall()
        return [r["racetime_user"] for r in rows if r["racetime_user"]]

    # best effort: on prend le 1er joueur de chaque team pour slot1/slot2
    left_rt_user = ""
    right_rt_user = ""

    if len(teams) > 0:
        left_users = team_racetime_users(int(teams[0]["team_id"]))
        left_rt_user = left_users[0] if left_users else ""

    if len(teams) > 1:
        right_users = team_racetime_users(int(teams[1]["team_id"]))
        right_rt_user = right_users[0] if right_users else ""

    left_twitch = ""
    right_twitch = ""
    left_time = ""
    right_time = ""
    left_status = ""
    right_status = ""

    if racetime_room:
        try:
            race_json = fetch_race_data(racetime_room)
            overlay_map = extract_entrants_overlay_info(race_json)

            left_info = overlay_map.get(left_rt_user)
            right_info = overlay_map.get(right_rt_user)

            if left_info:
                left_twitch = left_info.twitch_name
                left_status = left_info.status
                if left_info.status == "done":
                    left_time = left_info.finish_time_hms

            if right_info:
                right_twitch = right_info.twitch_name
                right_status = right_info.status
                if right_info.status == "done":
                    right_time = right_info.finish_time_hms

        except Exception:
            # overlay ne doit pas casser si Racetime est KO / URL invalide
            pass


    # --------------------------------------------------------------
    # Session tracker (création si absente)
    # --------------------------------------------------------------
    existing_session = load_session_restream(int(restream["id"]))

    session = ensure_session_restream(
        tracker_type=tracker_type,
        restream_id=int(restream["id"]),
        restream_slug=restream["slug"],
        preset_factory=tracker_def["default_preset"],
        participants_count=participants_count,
    )

    # --------------------------------------------------------------
    # Injection labels / team_id UNIQUEMENT à la création
    # --------------------------------------------------------------
    if existing_session is None:
        for i, p in enumerate(session.get("participants", [])):
            p["slot"] = i + 1
            p.setdefault("show_final_time", False)
            if i < len(teams):
                name = (teams[i]["team_name"] or f"Slot {i+1}").replace("Solo - ", "")
                p["team_id"] = int(teams[i]["team_id"])
                p["label"] = name
            else:
                p.setdefault("team_id", 0)
                p.setdefault("label", f"Slot {i+1}")

        save_session_restream(int(restream["id"]), session)

    # --------------------------------------------------------------
    # Payload tracker (read-only)
    # --------------------------------------------------------------
    tracker_payload = {
        "tracker_type": tracker_type,
        "catalog": tracker_def["catalog"](),
        "session": session,
        "use_storage": False,
        "frontend": tracker_def["frontend"],
        # SSE stream utilisé par OBS
        "stream_url": url_for(
            "restream.restream_tracker_stream",
            slug=restream["slug"],
        ),
        # update_url présent mais non utilisé (overlay read-only)
        "update_url": url_for(
            "restream.restream_tracker_update",
            slug=restream["slug"],
        ),
    }
    
    left = (teams[0]["team_name"] if len(teams) > 0 else "Slot 1") or "Slot 1"
    right = (teams[1]["team_name"] if len(teams) > 1 else "Slot 2") or "Slot 2"

    c1, c2 = split_commentators(restream["commentator_name"])
    
    # exemple logique côté route overlay
    left_show_time = False
    right_show_time = False

    for p in session.get("participants", []):
        if p.get("slot") == 1:
            left_show_time = bool(p.get("show_final_time", False))
        elif p.get("slot") == 2:
            right_show_time = bool(p.get("show_final_time", False))


    live_payload = {
        "left_name": left.replace("Solo - ", ""),
        "right_name": right.replace("Solo - ", ""),
        "title": simplify_restream_title(restream["title"]),
        "commentator_1": c1,
        "commentator_2": c2,
        "left_twitch": left_twitch,
        "right_twitch": right_twitch,
        "left_time": left_time,
        "right_time": right_time,
        "left_status": left_status,
        "right_status": right_status,
        "left_show_time": left_show_time,
        "right_show_time": right_show_time,
    }


    # IMPORTANT : overlay = toujours read-only
    can_edit = False
    
    overlay_pack = resolve_overlay_pack_for_match(db, restream["match_id"])

    return render_template(
        "restream/overlay_live.html",
        restream=restream,
        restream_slug=slug,
        tracker=tracker_payload,
        can_edit=can_edit,
        overlay_pack=overlay_pack,
        live=live_payload,
    )
    
@restream_bp.get("/<slug>/overlay/intro")
def restream_overlay_intro(slug: str):
    db = get_db()
    restream = get_active_restream_by_slug(db, slug)
    if not restream:
        abort(404)

    teams = get_match_teams(db, restream["match_id"])

    left = (teams[0]["team_name"] if len(teams) > 0 else "Slot 1") or "Slot 1"
    right = (teams[1]["team_name"] if len(teams) > 1 else "Slot 2") or "Slot 2"

    # tournament name
    row = db.execute(
        """
        SELECT t.name AS tournament_name, t.slug AS tournament_slug
        FROM matches m
        JOIN tournaments t ON t.id = m.tournament_id
        WHERE m.id = ?
        """,
        (restream["match_id"],),
    ).fetchone()

    lang = str(babel_get_locale() or "fr").strip().lower()

    tournament_name_raw = row["tournament_name"] if row else ""
    tslug = row["tournament_slug"] if row else None

    if tslug:
        tr = get_translation("tournament", tslug, "name", lang)
        if tr:
            tournament_name_raw = tr

    tournament_name = overlay_tournament_name(tournament_name_raw) if tournament_name_raw else ""

    overlay_pack = resolve_overlay_pack_for_match(db, restream["match_id"])
    
    display_title = simplify_restream_title(restream["title"])

    return render_template(
        "restream/overlay_intro.html",
        restream=restream,
        restream_slug=slug,
        intro={
            "tournament_name": tournament_name,
            "match_label": display_title,  # on réutilise le title comme label
            "left_name": left.replace("Solo - ", ""),
            "right_name": right.replace("Solo - ", ""),
        },
        overlay_pack=overlay_pack,
    )


MONTHS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre"
]
DAYS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _format_dt_fr(scheduled_at: str | None) -> str:
    if not scheduled_at:
        return ""
    # SQLite renvoie souvent "YYYY-MM-DD HH:MM:SS"
    try:
        dt = datetime.fromisoformat(scheduled_at.replace("Z", "").replace("T", " "))
    except ValueError:
        return scheduled_at

    day = DAYS_FR[dt.weekday()].capitalize()
    month = MONTHS_FR[dt.month - 1].capitalize()
    return f"{day} {dt.day} {month} - {dt:%Hh%M}"


@restream_bp.get("/<slug>/overlay/next")
def restream_overlay_next(slug: str):
    db = get_db()
    restream = get_active_restream_by_slug(db, slug)
    if not restream:
        abort(404)

    # tournoi courant (pour afficher le titre, même si next_match=None)
    row = db.execute(
        """
        SELECT
            t.id AS tournament_id,
            t.slug AS tournament_slug,
            t.name AS tournament_name
        FROM matches m
        JOIN tournaments t ON t.id = m.tournament_id
        WHERE m.id = ?
        """,
        (restream["match_id"],),
    ).fetchone()

    tournament_id = row["tournament_id"] if row else None
    lang = str(babel_get_locale() or "fr").strip().lower()

    tournament_name_raw = row["tournament_name"] if row else ""
    tslug = row["tournament_slug"] if row else None

    if tslug:
        tr = get_translation("tournament", tslug, "name", lang)
        if tr:
            tournament_name_raw = tr

    tournament_name = overlay_tournament_name(tournament_name_raw) if tournament_name_raw else ""
        

    overlay_pack = resolve_overlay_pack_for_match(db, restream["match_id"])

    next_match = get_next_planned_match_for_overlay(db, tournament_id=tournament_id, exclude_match_id=restream["match_id"])

    # Payload affichage (ou None)
    next_payload = None
    if next_match:
        teams = next_match.get("teams") or []
        left = (teams[0]["team_name"] if len(teams) > 0 else "Slot 1") or "Slot 1"
        right = (teams[1]["team_name"] if len(teams) > 1 else "Slot 2") or "Slot 2"

        label_raw = next_match.get("restream_title") or "Prochain match"
        label = simplify_restream_title(label_raw) or label_raw

        next_payload = {
            "left_name": left.replace("Solo - ", ""),
            "right_name": right.replace("Solo - ", ""),
            "label": label,
            "datetime_label": _format_dt_fr(next_match.get("scheduled_at")),
        }

    return render_template(
        "restream/overlay_next.html",
        restream=restream,
        restream_slug=slug,
        overlay_pack=overlay_pack,
        tournament_name=tournament_name,
        next=next_payload,
    )

@restream_bp.get("/<slug>/overlay/live-data")
def restream_overlay_live_data(slug: str):
    db = get_db()

    restream = db.execute(
        "SELECT id, slug, match_id, tracker_type FROM restreams WHERE slug = ? AND is_active = 1",
        (slug,),
    ).fetchone()
    if not restream or restream["tracker_type"] == "none":
        abort(404)

    # Match: racetime_room (URL complète)
    match_row = db.execute(
        "SELECT racetime_room FROM matches WHERE id = ?",
        (restream["match_id"],),
    ).fetchone()
    racetime_room = (match_row["racetime_room"] if match_row else "") or ""

    # Session pour connaitre team_id/slot (et racetime users via DB)
    session = load_session_restream(int(restream["id"])) or {}
    participants = session.get("participants", [])

    # helper: récupérer 1 racetime_user par team (slot)
    def team_racetime_user(team_id: int) -> str:
        row = db.execute(
            """
            SELECT p.racetime_user
            FROM team_players tp
            JOIN players p ON p.id = tp.player_id
            WHERE tp.team_id = ?
            ORDER BY tp.position ASC
            LIMIT 1
            """,
            (team_id,),
        ).fetchone()
        return (row["racetime_user"] if row else "") or ""

    # Prépare slots -> racetime_user
    slot_to_rt = {}
    for p in participants:
        slot = int(p.get("slot", 0) or 0)
        team_id = int(p.get("team_id", 0) or 0)
        if slot and team_id:
            slot_to_rt[str(slot)] = team_racetime_user(team_id)

    # Réponse vide si pas de racetime_room
    payload = {"slots": {}}

    if not racetime_room:
        return payload

    try:
        race_json = fetch_race_data(racetime_room)
        overlay_map = extract_entrants_overlay_info(race_json)

        for slot_str, rt_user in slot_to_rt.items():
            info = overlay_map.get(rt_user)
            if not info:
                payload["slots"][slot_str] = {"status": "", "time": ""}
                continue

            payload["slots"][slot_str] = {
                "status": info.status,
                "time": info.finish_time_hms if info.status == "done" else "",
            }

    except Exception:
        # fail-safe
        pass

    return payload

@restream_bp.get("/<slug>/overlay/interview")
def restream_overlay_interview(slug: str):
    db = get_db()

    restream = get_active_restream_by_slug(db, slug)
    if not restream:
        abort(404)

    # --------------------------------------------------------------
    # Commentateurs : on relit le champ pour être sûr qu'il existe
    # --------------------------------------------------------------
    row = db.execute(
        "SELECT commentator_name FROM restreams WHERE id = ?",
        (int(restream["id"]),),
    ).fetchone()

    commentator_raw = (row["commentator_name"] if row else "") or ""
    c1, c2 = split_commentators(commentator_raw)

    # --------------------------------------------------------------
    # Titre affiché
    # --------------------------------------------------------------
    display_title = simplify_restream_title(restream["title"])

    # --------------------------------------------------------------
    # Nom du tournoi
    # --------------------------------------------------------------
    row = db.execute(
        """
        SELECT t.slug AS tournament_slug, t.name AS tournament_name
        FROM matches m
        JOIN tournaments t ON t.id = m.tournament_id
        WHERE m.id = ?
        """,
        (restream["match_id"],),
    ).fetchone()


    lang = str(babel_get_locale() or "fr").strip().lower()

    tournament_name_raw = row["tournament_name"] if row and row["tournament_name"] else ""
    tslug = row["tournament_slug"] if row else None

    if tslug:
        tr = get_translation("tournament", tslug, "name", lang)
        if tr:
            tournament_name_raw = tr

    tournament_name = overlay_tournament_name(tournament_name_raw) if tournament_name_raw else ""

    overlay_pack = resolve_overlay_pack_for_match(db, restream["match_id"])

    return render_template(
        "restream/overlay_interview.html",
        restream=restream,
        restream_slug=slug,
        interview={
            "title": display_title,
            "tournament_name": tournament_name,
            "commentator_1": c1,
            "commentator_2": c2,
        },
        overlay_pack=overlay_pack,
    )

@restream_bp.get("/<slug>/overlay/interview/data")
def restream_overlay_interview_data(slug: str):
    db = get_db()

    restream = get_active_restream_by_slug(db, slug)
    if not restream:
        return jsonify({"ok": False, "error": "restream_not_found"}), 404

    # --------------------------------------------------------------
    # Racetime room (URL complète)
    # --------------------------------------------------------------
    row = db.execute(
        "SELECT racetime_room FROM matches WHERE id = ?",
        (restream["match_id"],),
    ).fetchone()

    racetime_room = (row["racetime_room"] if row else "") or ""
    if not racetime_room:
        return jsonify({"ok": False, "error": "no_racetime_room"})

    # --------------------------------------------------------------
    # Appel API Racetime
    # --------------------------------------------------------------
    try:
        race_json = fetch_race_data(racetime_room)
    except Exception:
        # overlay = best effort, jamais de crash
        return jsonify({"ok": False, "error": "racetime_unreachable"})

    # --------------------------------------------------------------
    # Extraction classement interview
    # --------------------------------------------------------------
    top = extract_interview_top8(race_json)

    race_status = (
        race_json.get("status", {}).get("value", "")
    )

    return jsonify({
        "ok": True,
        "race_status": race_status,
        "top": top,
    })
