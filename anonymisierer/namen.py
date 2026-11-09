"""KI-Namenserkennung (spaCy) und Stoppliste."""

_NLP = None          # das geladene Sprachmodell (oder None)
_NLP_FEHLER = None   # Begründung, falls nicht verfügbar

def lade_ner():
    """Lädt das deutsche spaCy-Modell für die Namenserkennung (einmalig)."""
    global _NLP, _NLP_FEHLER
    if _NLP is not None or _NLP_FEHLER is not None:
        return _NLP
    try:
        import spacy
        for modell in ("de_core_news_md", "de_core_news_sm"):
            try:
                _NLP = spacy.load(modell, disable=["lemmatizer", "tagger"])
                return _NLP
            except OSError:
                continue
        _NLP_FEHLER = ("Deutsches Sprachmodell fehlt "
                       "(Installieren.bat erneut ausführen).")
    except ImportError:
        _NLP_FEHLER = "Paket 'spacy' fehlt (Installieren.bat erneut ausführen)."
    return None


def finde_personen_ner(text: str) -> set[str]:
    """Findet Personennamen per KI-Modell. Leere Menge, falls Modell fehlt."""
    nlp = lade_ner()
    if nlp is None:
        return set()
    namen: set[str] = set()
    # Lange Texte in Stücke teilen (Speicher schonen)
    for anfang in range(0, len(text), 90_000):
        doc = nlp(text[anfang:anfang + 100_000])
        for ent in doc.ents:
            if ent.label_ == "PER":
                name = ent.text.strip(" \n\t,.;:()[]\"'")
                if len(name) >= 3 and any(c.isalpha() for c in name):
                    namen.add(name)
    return namen

# Wörter, die die Namenserkennung gern fälschlich als Person meldet
NAMEN_STOPPLISTE = {
    "gmbh", "co", "kg", "ag", "mbh", "versicherung", "lebensversicherung",
    "herr", "frau", "herrn", "sehr", "geehrte", "geehrter", "grüßen",
    "freundlichen", "mit", "und",
}


def ner_fehler():
    """Begründung, falls die Namenserkennung nicht verfügbar ist (sonst None)."""
    return _NLP_FEHLER
