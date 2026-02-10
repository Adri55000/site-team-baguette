from flask import render_template, abort, current_app
from app.database import get_db
from app.main.repo import get_internal_tournament_by_slug, get_teams_by_tournament_id, get_phases_by_tournament_id
from app.main.repo import get_series_by_phases_ids, get_teams_by_series_ids, get_scores_by_series_ids, get_tiebreaks_by_tournament
from app.main.repo import get_teams_by_matches_ids, get_groupteams_by_tournament_id, get_winnerteams_by_phase_id
from app.main.repo import get_playedmatches_by_phase_id, get_bracketseries_by_phase_id, get_tournaments
import json
from collections import defaultdict
from app.modules.tournaments import ensure_public_tournament
from app.modules.i18n import get_translation
from flask_babel import get_locale as babel_get_locale
from app.main import main_bp

@main_bp.route("/tournament/<slug>")
def tournament(slug):
    # -------------------------------------------------
    # Tournoi interne (BDD)
    # -------------------------------------------------
    tournament = get_internal_tournament_by_slug(slug)

    if tournament:
        # -----------------------------
        # Traductions (name + metadata JSON complet)
        # -----------------------------
        lang = str(babel_get_locale() or "fr").strip().lower()

        # Important: sqlite Row -> dict si tu veux modifier proprement
        tournament = dict(tournament)

        name_tr = get_translation("tournament", slug, "name", lang)
        tournament["display_name"] = name_tr if name_tr else tournament["name"]

        metadata_tr = get_translation("tournament", slug, "metadata", lang)
        metadata_json_raw = metadata_tr if metadata_tr else tournament["metadata"]

        ensure_public_tournament(tournament)
        # -----------------------------
        # Statut PUBLIC (mapping v1)
        # -----------------------------
        public_status = tournament["status"]

        if public_status == "draft":
            public_status = "upcoming"

        # -----------------------------
        # Metadata (JSON)
        # -----------------------------
        metadata = {}

        if metadata_json_raw:
            try:
                metadata = json.loads(metadata_json_raw)
            except ValueError:
                metadata = {}

        # Fallbacks v1
        metadata.setdefault("edition", None)
        metadata.setdefault("description", None)
        metadata.setdefault("organizers", [])
        metadata.setdefault("highlights", [])
        metadata.setdefault("external_links", {})

        # -----------------------------
        # Équipes participantes
        # -----------------------------
        teams = get_teams_by_tournament_id(tournament["id"])

        return render_template(
            "tournaments/internal.html",
            tournament=tournament,
            metadata=metadata,
            teams=teams,
            public_status=public_status
        )

    # -------------------------------------------------
    # Fallback tournoi externe (archives)
    # -------------------------------------------------
    tournaments_external = current_app.config.get("TOURNAMENTS", [])

    external = next(
        (t for t in tournaments_external if t.get("slug") == slug),
        None
    )

    if external:
        return render_template(
            "tournaments/external.html",
            tournament=external
        )

    abort(404)

@main_bp.route("/tournament/<slug>/results")
def tournament_results(slug):
    # -------------------------------------------------
    # Tournoi
    # -------------------------------------------------
    tournament = get_internal_tournament_by_slug(slug)

    if not tournament:
        abort(404)
        
    ensure_public_tournament(tournament)
    
    # -------------------------------------------------
    # Traductions (tournoi + metadata)
    # -------------------------------------------------
    lang = str(babel_get_locale() or "fr").strip().lower()

    # sqlite Row -> dict pour pouvoir enrichir
    tournament = dict(tournament)

    name_tr = get_translation("tournament", slug, "name", lang)
    tournament["display_name"] = name_tr if name_tr else tournament["name"]

    metadata_tr = get_translation("tournament", slug, "metadata", lang)
    metadata_json_raw = metadata_tr if metadata_tr else tournament["metadata"]


    # -------------------------------------------------
    # Metadata JSON
    # -------------------------------------------------
    metadata = {}
    if metadata_json_raw:
        try:
            metadata = json.loads(metadata_json_raw)
        except ValueError:
            metadata = {}

    metadata.setdefault("edition", None)


    # -------------------------------------------------
    # Phases
    # -------------------------------------------------
    phases = get_phases_by_tournament_id(tournament["id"])
    
    # -------------------------------------------------
    # Traductions phases
    # -------------------------------------------------
    phases = [dict(p) for p in phases]
    for p in phases:
        phase_key = str(p["id"])
        phase_tr = get_translation("tournament_phase", phase_key, "name", lang)
        p["display_name"] = phase_tr if phase_tr else p["name"]


    phase_ids = [p["id"] for p in phases]

    # -------------------------------------------------
    # Séries
    # -------------------------------------------------
    series_rows = []
    if phase_ids:
        placeholders = ",".join("?" for _ in phase_ids)
        series_rows = get_series_by_phases_ids(phase_ids, placeholders)

    series_ids = [s["id"] for s in series_rows]

    # -------------------------------------------------
    # Équipes par série
    # -------------------------------------------------
    teams_by_series = {}

    if series_ids:
        placeholders = ",".join("?" for _ in series_ids)
        rows = get_teams_by_series_ids(series_ids,placeholders)

        for r in rows:
            teams_by_series.setdefault(r["series_id"], []).append(r["team_name"])

    # -------------------------------------------------
    # Score BO (LOGIQUE ADMIN — is_winner)
    # -------------------------------------------------
    scores_by_series = {}

    if series_ids:
        placeholders = ",".join("?" for _ in series_ids)
        rows = get_scores_by_series_ids(series_ids,placeholders)

        for r in rows:
            if r["team1_wins"] or r["team2_wins"]:
                scores_by_series[r["series_id"]] = (
                    f"{r['team1_wins']}-{r['team2_wins']}"
                )

    # -------------------------------------------------
    # Assemblage par phase
    # -------------------------------------------------
    series_by_phase = {p["id"]: [] for p in phases}

    for s in series_rows:
        series_by_phase[s["phase_id"]].append({
            "stage": s["stage"],
            "teams": teams_by_series.get(s["id"], []),
            "winner_name": s["winner_name"],
            "score": scores_by_series.get(s["id"])
        })

    # -------------------------------------------------
    # Tie-breaks (matchs sans série)
    # -------------------------------------------------
    tiebreaks = []

    tb_matches = get_tiebreaks_by_tournament(tournament["id"])

    tb_ids = [m["id"] for m in tb_matches]

    teams_by_match = {}
    if tb_ids:
        placeholders = ",".join("?" for _ in tb_ids)
        rows = get_teams_by_matches_id(tb_ids, placeholders)

        for r in rows:
            teams_by_match.setdefault(r["match_id"], []).append(r["team_name"])

    for m in tb_matches:
        tiebreaks.append({
            "teams": teams_by_match.get(m["id"], []),
            "positions": None,   # prévu plus tard
            "is_completed": m["is_completed"]
        })

    return render_template(
        "tournaments/results.html",
        tournament=tournament,
        metadata=metadata,
        phases=phases,
        series_by_phase=series_by_phase,
        tiebreaks=tiebreaks
    )

@main_bp.route("/tournament/<slug>/bracket")
def tournament_bracket(slug):
    # -------------------------------------------------
    # Tournoi
    # -------------------------------------------------
    tournament = get_internal_tournament_by_slug(slug)

    if not tournament:
        abort(404)

    ensure_public_tournament(tournament)
    
    # -------------------------------------------------
    # Traductions (tournoi + metadata)
    # -------------------------------------------------
    lang = str(babel_get_locale() or "fr").strip().lower()

    tournament = dict(tournament)

    name_tr = get_translation("tournament", slug, "name", lang)
    tournament["display_name"] = name_tr if name_tr else tournament["name"]

    metadata_tr = get_translation("tournament", slug, "metadata", lang)
    metadata_json_raw = metadata_tr if metadata_tr else tournament["metadata"]


    # -------------------------------------------------
    # Metadata
    # -------------------------------------------------
    metadata = {}
    if metadata_json_raw:
        try:
            metadata = json.loads(metadata_json_raw)
        except ValueError:
            metadata = {}


    # -------------------------------------------------
    # Phases du tournoi (ordre officiel)
    # -------------------------------------------------
    phases_rows = get_phases_by_tournament_id(tournament["id"])

    processed_phases = []

    # -------------------------------------------------
    # Boucle sur les phases
    # -------------------------------------------------
    for phase_row in phases_rows:
        phase = dict(phase_row)
        # Traduction du nom de la phase
        phase_tr = get_translation("tournament_phase", str(phase["id"]), "name", lang)
        phase_display_name = phase_tr if phase_tr else phase["name"]

        ptype = (phase["type"] or "").strip().lower()

        if ptype == "groups":
            display_type = "groups"
        elif ptype == "bracket_simple_elim":
            display_type = "bracket_simple_elim"
        else:
            display_type = "default"

        # =============================
        # PHASE DE GROUPES
        # =============================
        if display_type == "groups":

            teams_rows = get_groupteams_by_tournament_id(tournament["id"])

            wins_rows = get_winnerteams_by_phase_id(phase["id"])

            wins_by_team = {r["team_id"]: r["wins"] for r in wins_rows}

            played_rows = get_playedmatches_by_phase_id(phase["id"])

            played_by_team = {r["team_id"]: r["played"] for r in played_rows}

            groups_map = {}
            group_display_by_name = {}

            for r in teams_rows:
                gname = r["group_name"]
                team_id = r["team_id"]
                wins = int(wins_by_team.get(team_id, 0))
                played = int(played_by_team.get(team_id, 0))

                # Traduction du nom de groupe (tir groupé)
                gkey = f"{slug}|{gname}"
                g_tr = get_translation("tournament_group", gkey, "name", lang)
                group_display_by_name[gname] = g_tr if g_tr else gname

                groups_map.setdefault(gname, []).append({
                    "team_id": team_id,
                    "team": r["team_name"],
                    "wins": wins,
                    "played": played,
                    "losses": max(0, played - wins),
                    "seed": r["seed"],
                    "position": r["position"],
                })

            groups = []
            for gname, rows in groups_map.items():
                rows_sorted = sorted(
                    rows,
                    key=lambda x: (
                        -x["wins"],
                        x["position"] is None,
                        x["position"] if x["position"] is not None else 10**9,
                        x["seed"] if x["seed"] is not None else 10**9,
                        x["team"].lower(),
                    )
                )
                groups.append({
                    "id": phase["id"],
                    "name": group_display_by_name.get(gname, gname),
                    "standings": rows_sorted,
                })

            groups.sort(key=lambda g: (g["name"] or "").lower())


            groups.sort(key=lambda g: g["name"].lower())

            qualifiers_per_group = None
            try:
                if phase.get("details"):
                    details = json.loads(phase["details"])
                    q = details.get("qualifiers_per_group")
                    if q is not None:
                        qualifiers_per_group = int(q)
            except Exception:
                qualifiers_per_group = None

            processed_phases.append({
                "id": phase["id"],
                "name": phase_display_name,
                "display_type": "groups",
                "data": {
                    "groups": groups,
                    "qualifiers_per_group": qualifiers_per_group,
                },
            })

        # =============================
        # PHASE DE BRACKET (simple élimination)
        # =============================
        elif display_type == "bracket_simple_elim":

            series_rows = get_bracketseries_by_phase_id(phase["id"])

            source_label_by_id = {
                str(r["id"]): (r["stage"] or f"Série #{r['id']}")
                for r in series_rows
            }


            from collections import defaultdict

            rounds_map = defaultdict(list)
            series_by_id = {}

            def _safe_int(x):
                try:
                    return int(x)
                except Exception:
                    return None

            # 1) Construire tous les objets "série" (modifiables)
            for row in series_rows:
                src1 = row["source_team1_series_id"]
                src2 = row["source_team2_series_id"]
                name1 = row["team1_name"]
                name2 = row["team2_name"]

                s_obj = {
                    "id": str(row["id"]),
                    "round": row["round"],
                    "stage": row["stage"],   # on garde l’original
                    "label": row["stage"],
                    "team1": {
                        "id": row["team1_id"],
                        "name": name1 if name1 else None,
                        "is_tbd": (not name1),   # True si pas de nom réel
                        "wins": row["team1_wins"] or 0,
                        "source_series_id": str(src1) if src1 is not None else None,
                        "source_type": row["source_team1_type"],
                        "source_label": source_label_by_id.get(str(src1)) if src1 is not None else None,
                    },
                    "team2": {
                        "id": row["team2_id"],
                        "name": name2 if name2 else None,
                        "is_tbd": (not name2),
                        "wins": row["team2_wins"] or 0,
                        "source_series_id": str(src2) if src2 is not None else None,
                        "source_type": row["source_team2_type"],
                        "source_label": source_label_by_id.get(str(src2)) if src2 is not None else None,
                    },
                    "best_of": row["best_of"],
                    # marqueurs utiles pour le template (ne casse rien si ignoré)
                    "is_virtual": False,
                    "is_bye": False,
                }

                series_by_id[s_obj["id"]] = s_obj


            # 2) Injection des "séries virtuelles Bye" (uniquement affichage)
            # On fait ça avant de remplir rounds_map pour pouvoir insérer dans le round précédent.
            min_round = min((s["round"] for s in series_by_id.values()), default=1)

            def make_bye_series(parent_series, side_key):
                """
                parent_series: la série du round r (r>min_round) où une équipe est seedée sans source
                side_key: "team1" ou "team2" (côté où l’équipe arrive via bye)
                """
                parent_id = parent_series["id"]
                r = parent_series["round"]
                if r <= min_round:
                    return None  # pas de bye à injecter au 1er round

                team = parent_series[side_key]
                if team["id"] is None:
                    return None  # pas d’équipe réelle => pas un bye, juste "à déterminer"
                if team["source_series_id"] is not None:
                    return None  # il y a déjà une source => pas un bye

                # Déduire une "stage" cohérente dans le round précédent si stage est numérique
                parent_stage_int = _safe_int(parent_series["stage"])
                prev_round = r - 1

                # convention bracket classique : feeders de stage S = (2S-1, 2S)
                if parent_stage_int is not None:
                    prev_stage_int = (2 * parent_stage_int - 1) if side_key == "team1" else (2 * parent_stage_int)
                    prev_stage = str(prev_stage_int)
                else:
                    prev_stage = "BYE"

                virtual_id = f"vbye:{parent_id}:{side_key}"

                v = {
                    "id": virtual_id,
                    "round": prev_round,
                    "stage": prev_stage,
                    "label": "Bye",
                    "team1": {
                        "id": team["id"],
                        "name": team["name"],
                        "wins": 1,
                        "source_series_id": None,
                        "source_type": None,
                        "source_label": None,
                    },
                    "team2": {
                        "id": None,
                        "name": "Bye",
                        "wins": 0,
                        "source_series_id": None,
                        "source_type": None,
                        "source_label": None,
                    },
                    "best_of": 1,
                    "is_virtual": True,
                    "is_bye": True,
                    # optionnel si un jour tu veux afficher un badge "qualifié"
                    "winner_team_id": team["id"],
                }

                # Important : mettre la "source" côté parent pour que l’affichage soit cohérent
                team["source_series_id"] = virtual_id
                team["source_type"] = "winner"
                team["source_label"] = "Bye"

                # Et permettre au label mapping de retrouver cet id si ton template l’utilise
                source_label_by_id[virtual_id] = "Bye"

                return v


            virtual_series = []
            for s in list(series_by_id.values()):
                v1 = make_bye_series(s, "team1")
                if v1:
                    virtual_series.append(v1)
                v2 = make_bye_series(s, "team2")
                if v2:
                    virtual_series.append(v2)

            # 3) Remplir rounds_map avec vraies + virtuelles séries
            for s in series_by_id.values():
                rounds_map[s["round"]].append(s)

            for v in virtual_series:
                rounds_map[v["round"]].append(v)

            # 4) Tri stable dans chaque round (stage ASC si possible)
            def stage_sort_key(s):
                si = _safe_int(s.get("stage"))
                return (0, si) if si is not None else (1, str(s.get("stage") or ""))

            for r in rounds_map:
                rounds_map[r].sort(key=stage_sort_key)


            processed_phases.append({
                "id": phase["id"],
                "name": phase_display_name,
                "display_type": "bracket_simple_elim",
                "data": {
                    "bracket": {
                        "rounds": [
                            {
                                "round": r,
                                "series": rounds_map[r],
                            }
                            for r in sorted(rounds_map.keys())
                        ]
                    }
                },
            })

    return render_template(
        "tournaments/bracket.html",
        tournament=tournament,
        metadata=metadata,
        phases=processed_phases,
    )

@main_bp.get("/tournaments")
def tournaments():
    db = get_db()

    # -------------------------------------------------
    # Tournois internes (BDD) + infos de jeu + last_match_at
    # -------------------------------------------------
    rows = get_tournaments()
    
    lang = str(babel_get_locale() or "fr").strip().lower()

    internal = []
    for r in rows:
        item = dict(r)

        # Traduction nom tournoi (interne)
        slug = item.get("slug")
        name_tr = get_translation("tournament", slug, "name", lang) if slug else None
        item["display_name"] = name_tr if name_tr else item.get("name")

        # Statut public v1 : draft -> upcoming
        status = (item.get("status") or "").strip().lower()
        if status == "draft":
            status = "upcoming"
        item["public_status"] = status

        # Nom de jeu pour grouping
        item["game_name"] = item.get("game_name") or "Autre"

        internal.append(item)


    # -------------------------------------------------
    # Tournois externes (config) : SSR uniquement
    # - On conserve l'ordre du fichier
    # - On les met en "finished" par défaut si pas de status
    # -------------------------------------------------
    external_cfg = current_app.config.get("TOURNAMENTS", [])
    external = []
    for t in external_cfg:
        status = (t.get("status") or "finished").strip().lower()
        if status == "draft":
            status = "upcoming"

        external.append({
            "id": None,
            "name": t.get("name"),
            "display_name": t.get("name"),
            "slug": t.get("slug"),
            "public_status": status,
            "game_name": "The Legend of Zelda : Skyward Sword Randomizer",
            "source": "external",
            # pas de last_match_at fiable pour l'externe
            "last_match_at": None,
        })

    # -------------------------------------------------
    # Grouping : status -> game -> [tournois]
    # -------------------------------------------------
    sections = {
        "active": defaultdict(list),
        "upcoming": defaultdict(list),
        "finished": defaultdict(list),
    }

    # Internes
    for t in internal:
        s = t["public_status"]
        if s not in sections:
            # fallback : si statut inattendu -> archives
            s = "finished"
        sections[s][t["game_name"]].append(t)

    # Externes : on les injecte, en conservant l'ordre
    for t in external:
        s = t["public_status"]
        if s not in sections:
            s = "finished"
        sections[s][t["game_name"]].append(t)

    # -------------------------------------------------
    # Tri par section
    # -------------------------------------------------
    def sort_active_or_upcoming(lst):
        # tri par nom (dans chaque jeu)
        return sorted(lst, key=lambda x: (x.get("display_name") or x.get("name") or "").lower())

    def sort_finished(lst):
        # 1) Split : avec date / sans date
        with_date = []
        no_date = []

        for t in lst:
            if t.get("last_match_at"):
                with_date.append(t)
            else:
                no_date.append(t)

        # 2) Trier uniquement ceux qui ont une date : plus récent -> plus ancien
        # (les strings datetime ISO se trient correctement en lexicographique si format homogène)
        with_date.sort(
            key=lambda t: (
                t["last_match_at"],
                (t.get("display_name") or t.get("name") or "").lower()
            ),
            reverse=True
        )

        # 3) Concat : datés d'abord, puis non datés dans l'ordre original (donc ordre fichier conservé)
        return with_date + no_date


    # Appliquer les tris
    for game_name, lst in sections["active"].items():
        sections["active"][game_name] = sort_active_or_upcoming(lst)

    for game_name, lst in sections["upcoming"].items():
        sections["upcoming"][game_name] = sort_active_or_upcoming(lst)

    for game_name, lst in sections["finished"].items():
        sections["finished"][game_name] = sort_finished(lst)

    # Ordonner les jeux (affichage) : alphabétique
    def ordered_games(d):
        return sorted(d.keys(), key=lambda x: (x or "").lower())

    ordered = {
        "active": ordered_games(sections["active"]),
        "upcoming": ordered_games(sections["upcoming"]),
        "finished": ordered_games(sections["finished"]),
    }

    return render_template(
        "tournaments/index.html",
        sections=sections,
        ordered_games=ordered,
    )