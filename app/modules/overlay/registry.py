# app/modules/overlay/registry.py

import json


DEFAULT_PACK_SLUG = "default"

OVERLAY_PACKS = {
    "default": {
        "slug": "default",
        "css": {
            "intro": "overlay/packs/default/intro.css",
            "live": "overlay/packs/default/live.css",
            "next": "overlay/packs/default/next.css",
            "interview": "overlay/packs/default/interview.css",
            # "solo": "overlay/packs/default/solo.css",
        },
        "assets": {
            "background_intro": "overlay/packs/default/assets/bg_intro.png",
            "background_live": "overlay/packs/default/assets/bg_live.png",
            "background_next": "overlay/packs/default/assets/bg_next.png",
        },
    },
    "ssr-s4": {
        "slug": "ssr-s4",
        "css": {
            "intro": "overlay/packs/ssr-s4/intro.css",
            "live": "overlay/packs/ssr-s4/live.css",
            "next": "overlay/packs/ssr-s4/next.css",
            "interview": "overlay/packs/ssr-s4/interview.css",
            # "solo": "overlay/packs/ssr-s4/solo.css",
        },
        "assets": {
            "background_intro": "overlay/packs/ssr-s4/assets/s4_intro.png",
            "background_live": "overlay/packs/ssr-s4/assets/s4_live.png",
            "background_next": "overlay/packs/ssr-s4/assets/s4_next.png",
        },
    },

    # Exemple tournoi :
    # "tb_ssr_s4": {...}
}


def get_overlay_pack(pack_slug: str | None):
    if pack_slug and pack_slug in OVERLAY_PACKS:
        return OVERLAY_PACKS[pack_slug]
    return OVERLAY_PACKS[DEFAULT_PACK_SLUG]

def resolve_overlay_pack_for_match(db, match_id: int):
    row = db.execute(
        """
        SELECT t.metadata
        FROM matches m
        JOIN tournaments t ON t.id = m.tournament_id
        WHERE m.id = ?
        """,
        (match_id,),
    ).fetchone()

    pack_slug = None

    if row and row["metadata"]:
        try:
            meta = json.loads(row["metadata"])
            pack_slug = meta.get("overlay_pack")
        except Exception:
            pack_slug = None

    return get_overlay_pack(pack_slug)