"""
SSR inventory tracker catalog (final).

Declarative catalog:
- items
- behaviors
- asset mapping
- layout order via groups
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Union, Literal


TRACKER_TYPE = "ssr_inventory"
ASSET_DIR = "tracker/ssr"

ItemKind = Literal["toggle", "cycle", "counter", "wallet", "composite"]


@dataclass(frozen=True)
class ItemDef:
    id: str
    kind: ItemKind
    label: str
    group: str
    asset_base: Optional[str] = None
    level_values: Optional[List[int]] = None
    counter_min: Optional[int] = None
    counter_max: Optional[int] = None
    counter_step: Optional[int] = None
    wallet_bonus_values: Optional[List[int]] = None


@dataclass(frozen=True)
class CompositeDef:
    id: str
    kind: Literal["composite"]
    label: str
    group: str
    base_asset: str
    overlays: Dict[str, str]


def _range(a: int, b: int) -> List[int]:
    return list(range(a, b + 1))


# -------------------------------------------------------------------------
# Donjons (affichage texte uniquement)
# -------------------------------------------------------------------------

DUNGEONS = ["SV", "ET", "LMF", "AC", "SSH", "FS", "SK"]


# -------------------------------------------------------------------------
# Composites
# -------------------------------------------------------------------------

TABLETS = CompositeDef(
    id="tablets",
    kind="composite",
    label="Tablettes",
    group="special",
    base_asset="tablet0.png",
    overlays={
        "emerald": "tabletemerald.png",
        "ruby": "tabletruby.png",
        "amber": "tabletamber.png",
    },
)

TRIFORCES = CompositeDef(
    id="triforces",
    kind="composite",
    label="Triforce",
    group="special",
    base_asset="triforce0.png",
    overlays={
        "wisdom": "triforcewisdom.png",
        "power": "triforcepower.png",
        "courage": "triforcecourage.png",
    },
)


# -------------------------------------------------------------------------
# Items
# -------------------------------------------------------------------------

ITEMS: List[Union[ItemDef, CompositeDef]] = [

    # =========================
    # ÉQUIPEMENT
    # =========================
    ItemDef("epee", "cycle", "Épée", "equipment", "épée", _range(0, 6)),
    ItemDef("beetle", "cycle", "Scarabée", "equipment", "beetle", _range(0, 4)),
    ItemDef("bow", "cycle", "Arc", "equipment", "bow", _range(0, 3)),
    ItemDef("slingshot", "toggle", "Lance-pierre", "equipment", "slingshot", _range(0, 2)),
    ItemDef("clawshots", "toggle", "Grappin", "equipment", "clawshots", [0, 1]),
    ItemDef("bomb", "toggle", "Bombes", "equipment", "bomb", [0, 1]),
    ItemDef("whip", "toggle", "Fouet", "equipment", "whip", [0, 1]),
    ItemDef("bugnet", "cycle", "Filet à papillon", "equipment", "bugnet", _range(0, 2)),
    ItemDef("gustbellows", "toggle", "Jarre magique", "equipment", "gustbellows", [0, 1]),

    # =========================
    # CONSOMMABLES / COMPTEURS
    # =========================
    ItemDef("pouch", "toggle", "Sacoche", "counters", "pouch", [0, 1]),
    ItemDef("bottle", "counter", "Bouteilles", "counters",
            "bottle", [0, 1], 0, 5, 1),
    ItemDef("wallet", "wallet", "Bourse", "counters",
            "wallet", _range(1, 5), wallet_bonus_values=[0, 300, 600, 900]),
    ItemDef("gratitude", "counter", "Cristaux de gratitude", "counters",
            "gratitudecrystal", [0, 1], 0, 80, 5),
    ItemDef("tadtones", "counter", "Fironote", "counters",
            "tadtones", [0, 1], 0, 17, 1),

    # =========================
    # QUÊTES / OBJETS SPÉCIAUX
    # =========================
    
    ItemDef("water_scale", "toggle", "Écaille du dragon d’eau", "quest", "scale", [0, 1]),
    ItemDef("fireshield", "toggle", "Boucles ignifuges", "quest", "fireshieldearrings", [0, 1]),
    ItemDef("mitts", "cycle", "Gants", "quest", "mitts", _range(0, 2)),
    ItemDef("seachart", "toggle", "Carte marine", "quest", "seachart", [0, 1]),
    ItemDef("caves_key", "toggle", "Clé des grottes de Lanelle", "quest", "caveskey", [0, 1]),
    ItemDef("spiralcharge", "toggle", "Attaque tournoyante", "quest", "spiralcharge", [0, 1]),
    ItemDef("cawlin_letter", "toggle", "Lettre d'Orbo", "quest", "cawlinsletter", [0, 1]),
    ItemDef("rattle", "toggle", "Hochet", "quest", "rattle", [0, 1]),
    ItemDef("horned_beetle", "toggle", "Insecte de Terry", "quest", "hornedcolossusbeetle", [0, 1]),
    ItemDef("life_tree_fruit", "toggle", "Fruit de l’Arbre de Vie", "quest", "lifetreefruit", [0, 1]),
    ItemDef("scrapper", "toggle", "Récupix", "quest", "scrapper", [0, 1]),
    ItemDef("tumbleweed", "toggle", "Virevoltant", "quest", "tumbleweed", [0, 1]),
   
    # =========================
    # CHANTS ET LYRE
    # =========================

    ItemDef("harp", "toggle", "Lyre de la Déesse", "song", "harp", [0, 1]),
    ItemDef("ballad", "toggle", "Chant de la Déesse", "song", "ballad", [0, 1]),
    ItemDef("farore_courage", "toggle", "Courage de Farore", "song", "farorescourage", [0, 1]),
    ItemDef("nayru_wisdom", "toggle", "Sagesse de Nayru", "song", "nayruswisdom", [0, 1]),
    ItemDef("din_power", "toggle", "Force de Din", "song", "dinspower", [0, 1]),
    ItemDef("soth", "counter", "Chant du Héros", "song",
            "songofthehero", [0, 1], 0, 3, 1),

    # =========================
    # DONJONS — LIGNE OBJETS
    # (ordre strict, group unique)
    # =========================
    ItemDef("smallkey_sv", "cycle", "Clés — Temple de la Contemplation", "dungeons", "smallkey", _range(0, 2)),
    ItemDef("golden_carving", "toggle", "Sculpture Dorée", "dungeons", "goldencarving", [0, 1]),
    ItemDef("key_pieces", "cycle", "Fragments de clé", "dungeons", "keypiece", _range(0, 5)),
    ItemDef("dragon_sculpture", "toggle", "Statuette de Dragon", "dungeons", "dragonsculpture", [0, 1]),

    ItemDef("smallkey_lmf", "cycle", "Clé — Raffinerie de Lanelle", "dungeons", "smallkey", _range(0, 1)),
    ItemDef("ancient_circuit", "toggle", "Circuit Antique", "dungeons", "ancientcircuit", [0, 1]),

    ItemDef("smallkey_ac", "cycle", "Clés — Grande Caverne Antique", "dungeons", "smallkey", _range(0, 2)),
    ItemDef("blessed_idol", "toggle", "Statuette Sereine", "dungeons", "blessedidol", [0, 1]),

    ItemDef("smallkey_ssh", "cycle", "Clés — Galion des Sables", "dungeons", "smallkey", _range(0, 2)),
    ItemDef("squid_carving", "toggle", "Sculpture Tentaculaire", "dungeons", "squidcarving", [0, 1]),

    ItemDef("smallkey_fs", "cycle", "Clés — Grand Sanctuaire Ancien", "dungeons", "smallkey", _range(0, 3)),
    ItemDef("mysterious_crystals", "toggle", "Cristal mystérieux", "dungeons", "mysteriouscrystals", [0, 1]),

    ItemDef("smallkey_sk", "cycle", "Clé — Tour des Cieux", "dungeons", "smallkey", _range(0, 1)),
    ItemDef("stone_of_trials", "toggle", "Sceau des épreuves", "dungeons", "stoneoftrials", [0, 1]),

    # =========================
    # COMPOSITES
    # =========================
    TABLETS,
    TRIFORCES,
]


# -------------------------------------------------------------------------
# Export
# -------------------------------------------------------------------------

def get_catalog() -> Dict:
    items = []
    for it in ITEMS:
        if isinstance(it, CompositeDef):
            items.append({
                "id": it.id,
                "kind": it.kind,
                "label": it.label,
                "group": it.group,
                "base_asset": it.base_asset,
                "overlays": it.overlays,
            })
        else:
            items.append({
                "id": it.id,
                "kind": it.kind,
                "label": it.label,
                "group": it.group,
                "asset_base": it.asset_base,
                "level_values": it.level_values,
                "counter_min": it.counter_min,
                "counter_max": it.counter_max,
                "counter_step": it.counter_step,
                "wallet_bonus_values": it.wallet_bonus_values,
            })

    return {
        "tracker_type": TRACKER_TYPE,
        "asset_dir": ASSET_DIR,
        "dungeons": DUNGEONS,
        "items": items,
    }
