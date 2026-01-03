# app/modules/text.py
import re
import unicodedata
from typing import Optional, List

def slugify(text):
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text

def _canonical_key(label: str) -> str:
    """Clé canonique pour comparer des noms de groupes (sans accents, sans casse, espaces normalisés)."""
    label = (label or "").strip()
    label = re.sub(r"\s+", " ", label)
    label = unicodedata.normalize("NFKD", label)
    label = label.encode("ascii", "ignore").decode("ascii")
    return label.lower()

def normalize_group_name(input_name: str, existing_names: List[str]) -> Optional[str]:
    """
    Retourne :
    - None si input vide => pas de groupe
    - un nom existant EXACT (si équivalent canonique trouvé)
    - sinon le nom nettoyé (espaces multiples) tel que saisi
    """
    raw = (input_name or "").strip()
    if not raw:
        return None

    cleaned = re.sub(r"\s+", " ", raw)

    # Map: canonical -> existing exact label (on conserve EXACTEMENT le libellé déjà stocké)
    existing_map = {
        _canonical_key(n): n
        for n in existing_names
        if n and str(n).strip()
    }

    key = _canonical_key(cleaned)
    if key in existing_map:
        return existing_map[key]

    return cleaned