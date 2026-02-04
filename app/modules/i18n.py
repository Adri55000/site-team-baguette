from app.database import get_db

def get_translation(entity_type, entity_key, field, lang):
    """
    Retourne la traduction si elle existe, sinon None
    """
    lang = (lang or "").strip().lower()
    db = get_db()
    row = db.execute(
        """
        SELECT value
        FROM translations
        WHERE entity_type = ?
          AND entity_key  = ?
          AND field       = ?
          AND lang        = ?
        """,
        (entity_type, entity_key, field, lang)
    ).fetchone()

    return row["value"] if row else None

def delete_translation(entity_type, entity_key, field, lang):
    db = get_db()
    db.execute(
        """
        DELETE FROM translations
        WHERE entity_type = ?
          AND entity_key  = ?
          AND field       = ?
          AND lang        = ?
        """,
        (entity_type, entity_key, field, lang)
    )
    db.commit()

def upsert_translation(entity_type, entity_key, field, lang, value):
    lang = (lang or "").strip().lower()

    # Règle: valeur vide => on supprime la trad (retour fallback DB)
    if value is None or (isinstance(value, str) and value.strip() == ""):
        delete_translation(entity_type, entity_key, field, lang)
        return

    db = get_db()
    db.execute(
        """
        INSERT INTO translations (entity_type, entity_key, field, lang, value, updated_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(entity_type, entity_key, field, lang)
        DO UPDATE SET
            value = excluded.value,
            updated_at = datetime('now')
        """,
        (entity_type, entity_key, field, lang, value)
    )
    db.commit()

def resolve_translation(
    *,
    entity_type,
    entity_key,
    field,
    lang,
    fallback_value
):
    lang = (lang or "").strip().lower()
    """
    Retourne la traduction si dispo, sinon la valeur DB
    """
    translated = get_translation(entity_type, entity_key, field, lang)
    if translated is not None:
        return translated
    return fallback_value
