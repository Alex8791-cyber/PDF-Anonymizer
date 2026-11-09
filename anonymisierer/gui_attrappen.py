"""Attrappen (Rückfall) für Engine-Schnittstellen aus Vertrag Phase 2 (CONTRACT_V2, Abschnitt 12.5).

Die Oberfläche erkennt die echten Funktionen per hasattr/try-Import und nimmt diese Attrappen nur, solange
die Engine sie noch nicht hat (und in Tests). Jede Attrappe hält die Vertragsschnittstelle ein, tut aber nur
das Nötigste:
  - PROFILE: Schutzstufen aus den vorhandenen Kategorien abgeleitet (muster.PROFILE ersetzt sie)
  - seite_bild / vorschau_daten: Seitenbild und Wörter per PyMuPDF (vorschau.py ersetzt sie)
  - freigeben / verwerfen: _PRUEFEN entfernen bzw. Ausgabe löschen, _zuordnung.txt nachführen
    (schwaerzung.freigeben/verwerfen ersetzen sie); als_pruefen_markieren emuliert freigabe_erforderlich
    für eine Engine ohne diesen Parameter
  - restrisiko_pruefen: liefert [] (restrisiko.py ersetzt sie)
  - Kundenliste: zählt nur Kunden, speichert nur die Anzahl, erkennt nichts (kundenliste.py ersetzt sie)
  - meldungen_aus_texten: leitet Meldungs-Codes (12.6) aus den Warnungstexten einer alten Engine ab
"""

import json
import os
import re
from pathlib import Path

import fitz  # PyMuPDF

from . import dateien
from .muster import KATEGORIEN

ATTRAPPE = True
PLATZHALTER_MANUELL = "[GESCHWÄRZT]"
WARNUNG_KEIN_TREFFER = ("Kein angehakter Fund konnte im Dokument lokalisiert werden – "
                        "keine Ausgabedatei erzeugt.")
ZUORDNUNG_DATEI = "_zuordnung.txt"
SATZZEICHEN = ".,;:!?()[]{}\"'„“‚‘«»/\\|<>*"


# ----------------------------------------------------------------------
# Schutzstufen (Profile)
# ----------------------------------------------------------------------
PROFIL_REIHENFOLGE = ("ausgewogen", "hoch", "maximal")
STANDARD_PROFIL = "hoch"
BENUTZERDEFINIERT = "benutzerdefiniert"
PROFIL_ANZEIGE = {"ausgewogen": "Ausgewogen", "hoch": "Hoch (Standard)", "maximal": "Maximal",
                  BENUTZERDEFINIERT: "Benutzerdefiniert"}
_ZUSATZ_HOCH = ("beruf", "arbeitgeber", "international")
_ZUSATZ_MAXIMAL = ("diagnose", "medikament")


def _kategorie_schluessel(kategorien) -> list[str]:
    return [eintrag[0] for eintrag in kategorien]


def _standard_kategorien(kategorien) -> set[str]:
    return {eintrag[0] for eintrag in kategorien if len(eintrag) < 5 or eintrag[4]}


def _profile_aus_kategorien(kategorien) -> dict:
    """Schutzstufen nach Vertrag Abschnitt 9, beschränkt auf die Kategorien, die die Engine kennt:
    ausgewogen = Standard aus Phase 1, hoch = + Beruf/Arbeitgeber/international, maximal = + Diagnosen/
    Medikamente. Fehlen diese Kategorien (alte Engine), sind die drei Stufen gleich."""
    alle = set(_kategorie_schluessel(kategorien))
    ausgewogen = _standard_kategorien(kategorien) - set(_ZUSATZ_HOCH) - set(_ZUSATZ_MAXIMAL)
    hoch = ausgewogen | (set(_ZUSATZ_HOCH) & alle)
    maximal = hoch | (set(_ZUSATZ_MAXIMAL) & alle)
    return {"ausgewogen": {"aktive": ausgewogen}, "hoch": {"aktive": hoch}, "maximal": {"aktive": maximal},
            "attrappe": True}


PROFILE = _profile_aus_kategorien(KATEGORIEN)


def profil_kategorien(profile, name: str, alle) -> set[str] | None:
    """Aktive Kategorien einer Schutzstufe – tolerant gegenüber der Form des Eintrags (dict mit „aktive“/
    „kategorien“, oder direkt eine Menge/Liste). None, wenn die Stufe fehlt oder keine Kategorien nennt."""
    eintrag = profile.get(name) if isinstance(profile, dict) else None
    werte = None
    if isinstance(eintrag, dict):
        for schluessel in ("aktive", "kategorien", "aktiv"):
            if schluessel in eintrag:
                werte = eintrag[schluessel]
                break
    elif isinstance(eintrag, (set, frozenset, list, tuple)):
        werte = eintrag
    elif eintrag is not None:                       # z. B. dataclass/NamedTuple mit Attribut
        for schluessel in ("aktive", "kategorien", "aktiv"):
            if hasattr(eintrag, schluessel):
                werte = getattr(eintrag, schluessel)
                break
    if werte is None:
        return None
    if isinstance(werte, dict):
        werte = [k for k, v in werte.items() if v]
    return {str(k) for k in werte} & set(alle)


def profil_beschreibung(profile, name: str, kategorien=KATEGORIEN) -> str:
    """Kurzbeschreibung einer Schutzstufe; nennt nur Kategorien, die die Engine wirklich kennt."""
    eintrag = profile.get(name) if isinstance(profile, dict) else None
    if isinstance(eintrag, dict) and isinstance(eintrag.get("beschreibung"), str):
        return eintrag["beschreibung"]
    if eintrag is not None and isinstance(getattr(eintrag, "beschreibung", None), str):
        return eintrag.beschreibung
    if name == BENUTZERDEFINIERT:
        return "Eigene Auswahl der Kategorien (Erkennungsregeln der zuletzt gewählten Stufe)."
    alle = _kategorie_schluessel(kategorien)
    anzeige = {e[0]: e[1] for e in kategorien}
    basis = profil_kategorien(profile, "ausgewogen", alle) or set()
    eigene = profil_kategorien(profile, name, alle) or set()
    extra = [anzeige[k] for k in alle if k in eigene - basis]
    if name == "ausgewogen":
        return "Direkte Kennungen: Namen, Anschrift, IBAN, Telefon, Nummern … – mehr Zusammenhang für die KI."
    text = "Empfohlen." if name == "hoch" else "Größter Schutz, weniger Zusammenhang für die KI."
    if extra:
        text += " Zusätzlich: " + ", ".join(extra) + "."
    return text


# ----------------------------------------------------------------------
# Seitenmodell der Attrappe (Wörter in Lesereihenfolge, Text mit Offsets)
# ----------------------------------------------------------------------
_CACHE: dict[str, dict] = {}
_CACHE_MAX = 4


def cache_leeren(pfad=None):
    """Vergisst vorbereitete Dokumente (alle oder eines) – z. B. bevor eine Ausgabe umbenannt wird."""
    if pfad is None:
        eintraege = list(_CACHE.values())
        _CACHE.clear()
    else:
        eintrag = _CACHE.pop(str(Path(pfad)), None)
        eintraege = [eintrag] if eintrag else []
    for eintrag in eintraege:
        try:
            eintrag["doc"].close()
        except Exception:
            pass


def _vorbereitet(pfad) -> dict:
    """PDF aus dem Speicher öffnen (keine offene Datei – unter Windows bleibt sie umbenennbar), Formular-
    felder einbrennen und Drehung entfernen wie Analyse und Schwärzung; je Pfad und Dateistand gemerkt."""
    pfad = Path(pfad)
    stand = pfad.stat()
    kennung = (stand.st_mtime_ns, stand.st_size)
    eintrag = _CACHE.get(str(pfad))
    if eintrag is not None and eintrag["kennung"] == kennung:
        return eintrag
    cache_leeren(pfad)
    doc = fitz.open(stream=pfad.read_bytes(), filetype="pdf")
    if doc.needs_pass:
        doc.close()
        raise ValueError("Die PDF-Datei ist passwortgeschützt.")
    try:
        doc.bake()
    except Exception:
        pass
    for seite in doc:
        try:
            seite.remove_rotation()
        except Exception:
            pass
    eintrag = {"kennung": kennung, "doc": doc, "seiten": {}}
    while len(_CACHE) >= _CACHE_MAX:
        cache_leeren(next(iter(_CACHE)))
    _CACHE[str(pfad)] = eintrag
    return eintrag


def seitenzahl(pdf_pfad) -> int:
    return len(_vorbereitet(pdf_pfad)["doc"])


def seiten_modell(pdf_pfad, seite_nr0: int) -> dict:
    """{"text": str, "woerter": [(Rect, text, start, ende)], "seitenrect": Rect, "bilder": [Rect]} –
    Wörter derselben Zeile durch " ", Zeilen durch "\\n" getrennt (Offsets beziehen sich auf "text")."""
    eintrag = _vorbereitet(pdf_pfad)
    if seite_nr0 in eintrag["seiten"]:
        return eintrag["seiten"][seite_nr0]
    seite = eintrag["doc"][seite_nr0]
    teile, woerter, pos, letzte = [], [], 0, None
    for w in seite.get_text("words"):
        zeile = (w[5], w[6])
        if letzte is not None:
            teile.append(" " if zeile == letzte else "\n")
            pos += 1
        teile.append(w[4])
        woerter.append((fitz.Rect(w[:4]), w[4], pos, pos + len(w[4])))
        pos += len(w[4])
        letzte = zeile
    bilder = []
    try:
        for info in seite.get_image_info():
            r = fitz.Rect(info["bbox"]) & seite.rect
            if not r.is_empty:
                bilder.append(r)
    except Exception:
        pass
    modell = {"text": "".join(teile), "woerter": woerter, "seitenrect": fitz.Rect(seite.rect), "bilder": bilder}
    eintrag["seiten"][seite_nr0] = modell
    return modell


def _kern(wort: str) -> str:
    return wort.strip(SATZZEICHEN).casefold()


def rechtecke_zusammenfassen(rects) -> list:
    """Wortrechtecke derselben Zeile zu einem Rechteck je Zeile vereinen."""
    zeilen: list[fitz.Rect] = []
    for r in rects:
        r = fitz.Rect(r)
        for i, z in enumerate(zeilen):
            hoehe = min(r.height, z.height) or 1
            if min(r.y1, z.y1) - max(r.y0, z.y0) > 0.5 * hoehe:
                zeilen[i] = z | r
                break
        else:
            zeilen.append(r)
    return zeilen


def stellen_suchen(woerter, fundtext: str) -> list[tuple[int, int, list]]:
    """Ganzwort-Wortfolgen-Suche eines Fundtexts in der Wortliste (Groß-/Kleinschreibung egal, Satzzeichen
    am Wortrand ignoriert). Rückgabe: [(start, ende, [Rect je Zeile])] – nur für die Anzeige."""
    tokens = [t for t in (_kern(t) for t in str(fundtext).split()) if t]
    if not tokens:
        return []
    # reine Satzzeichen-Wörter („/“, „-“) zählen nicht mit: „02204 / 91 23 45“ = „02204/91 23 45“
    folge = [(i, k) for i, k in ((i, _kern(w[1])) for i, w in enumerate(woerter)) if k]
    treffer = []
    n = len(tokens)
    for j in range(len(folge) - n + 1):
        if folge[j][1] == tokens[0] and all(folge[j + m][1] == tokens[m] for m in range(1, n)):
            gruppe = woerter[folge[j][0]:folge[j + n - 1][0] + 1]
            treffer.append((gruppe[0][2], gruppe[-1][3], rechtecke_zusammenfassen([w[0] for w in gruppe])))
    return treffer


def rechtecke_fuer(woerter, start: int, ende: int) -> list:
    """Rechtecke (je Zeile) der Wörter, die den Textbereich [start, ende) berühren."""
    return rechtecke_zusammenfassen([w[0] for w in woerter if w[2] < ende and w[3] > start])


def seite_bild(pdf_pfad_oder_doc, seite_nr0: int, zoom: float) -> tuple[bytes, float]:
    """PNG der Seite (nach remove_rotation) und Faktor pt -> Pixel (Vertrag Abschnitt 8)."""
    zoom = max(0.1, min(float(zoom), 6.0))
    if isinstance(pdf_pfad_oder_doc, fitz.Document):
        doc = pdf_pfad_oder_doc
    else:
        doc = _vorbereitet(pdf_pfad_oder_doc)["doc"]
    pix = doc[seite_nr0].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    return pix.tobytes("png"), zoom


def _vergleichstext(text: str) -> str:
    return " ".join(str(text).split()).casefold()


def _mit_ocr_woertern(modell: dict, ocr_woerter) -> dict:
    """Seitenmodell um OCR-Wörter (ocr_cache der Analyse: (x0, y0, x1, y1, text) in Seitenkoordinaten nach
    remove_rotation) ergänzen – sonst zeigt die Vorschau auf Scans keine einzige Fundstelle."""
    if not ocr_woerter:
        return modell
    woerter = list(modell["woerter"])
    teile = [modell["text"]]
    pos = len(modell["text"])
    letzte_y = None
    for w in ocr_woerter:
        text = str(w[4])
        rect = fitz.Rect(w[:4])
        if woerter or letzte_y is not None:
            neue_zeile = letzte_y is None or abs(rect.y1 - letzte_y) > max(rect.height, 1.0) * 0.6
            teile.append("\n" if neue_zeile else " ")
            pos += 1
        woerter.append((rect, text, pos, pos + len(text)))
        teile.append(text)
        pos += len(text)
        letzte_y = rect.y1
    return dict(modell, text="".join(teile), woerter=woerter)


def vorschau_daten(ergebnis: dict, seite_nr0: int) -> dict:
    """Vertrag Abschnitt 8: {"woerter": [(rect, text, start, ende)], "stellen": [(rect, fund_id, stelle_index,
    an)], "bilder": [rect], "seitenrect": rect}.
    Funde ohne "stellen" (alte Engine) werden per Wortfolgen-Suche gezeigt (stelle_index None = ganzer Fund).
    Funde mit "stellen" werden über die Offsets abgebildet – aber nur, wenn der Text an diesen Offsets im
    Seitenmodell der Attrappe wirklich der Fund ist. Stammen die Offsets aus dem Seitenmodell der Engine
    (anderer Text), wird nicht geraten: dann zeigt die Suche den ganzen Fund (stelle_index None)."""
    modell = _mit_ocr_woertern(seiten_modell(ergebnis["datei"], seite_nr0),
                               (ergebnis.get("ocr_cache") or {}).get(seite_nr0))
    stellen = []
    for index, fund in enumerate(ergebnis.get("funde") or []):
        fund_id = fund.get("id") or f"#{index}"
        eigene = fund.get("stellen")
        hier = [(si, st) for si, st in enumerate(eigene or []) if st.get("seite") == seite_nr0]
        soll = _vergleichstext(fund.get("text", ""))
        passend = bool(hier) and all(
            _vergleichstext(modell["text"][int(st["start"]):int(st["ende"])]) == soll for _, st in hier)
        if passend:
            for si, stelle in hier:
                for r in rechtecke_fuer(modell["woerter"], int(stelle["start"]), int(stelle["ende"])):
                    stellen.append((r, fund_id, si, bool(stelle.get("an", True))))
        elif not eigene or hier:
            for _, _, rects in stellen_suchen(modell["woerter"], fund.get("text", "")):
                for r in rects:
                    stellen.append((r, fund_id, None, True))
    return {"woerter": modell["woerter"], "stellen": stellen, "bilder": modell["bilder"],
            "seitenrect": modell["seitenrect"]}


def ausgabe_vorschau(ausgabe_pfad, verdacht, seite_nr0: int, zoom: float) -> dict:
    """Vertrag Abschnitt 8 (Form der Attrappe): Bild der Ausgabeseite und die Verdachtsrechtecke dieser Seite."""
    png, faktor = seite_bild(ausgabe_pfad, seite_nr0, zoom)
    markierungen = []
    for index, v in enumerate(verdacht or []):
        if verdacht_feld(v, "seite") == seite_nr0:
            for r in verdacht_feld(v, "rechtecke") or []:
                markierungen.append((fitz.Rect(r), index))
    return {"bild": png, "faktor": faktor, "verdacht": markierungen}


def verdacht_feld(verdacht, name, standard=None):
    """Feld eines Verdachts lesen – NamedTuple (Vertrag) oder dict."""
    if isinstance(verdacht, dict):
        return verdacht.get(name, standard)
    return getattr(verdacht, name, standard)


def restrisiko_pruefen(ausgabe_pfad, ocr=None, platzhalter=None, profil="hoch", nie=None, wissen=None) -> list:
    """Attrappe der Restrisiko-Prüfung (Vertrag Abschnitt 7): meldet nichts."""
    return []


# ----------------------------------------------------------------------
# Ausgaben: Freigabe, Verwerfen, _PRUEFEN markieren
# ----------------------------------------------------------------------
_AUSGABE_RE = re.compile(r"^anonym_(\d+)(_PRUEFEN)?\.pdf$", re.IGNORECASE)


def _nummer_frei(ordner: Path, nummer: int) -> bool:
    return not (ordner / f"anonym_{nummer:02d}.pdf").exists() and \
        not (ordner / f"anonym_{nummer:02d}_PRUEFEN.pdf").exists()


def _umbenennen_ohne_ueberschreiben(alt: Path, neu: Path):
    """Umbenennen, ohne eine vorhandene Datei zu ersetzen (os.link scheitert, wenn das Ziel existiert)."""
    try:
        os.link(alt, neu)
    except FileExistsError:
        raise
    except OSError:
        if neu.exists():
            raise FileExistsError(str(neu))
        alt.rename(neu)
        return
    alt.unlink()


def _zuordnung_umschreiben(ordner: Path, alt_name: str, neu_name: str | None):
    """Zeile „<alt_name>  <-  …“ in _zuordnung.txt umbenennen (neu_name) oder entfernen (None)."""
    pfad = ordner / ZUORDNUNG_DATEI
    try:
        zeilen = pfad.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError:
        return
    neu = []
    for zeile in zeilen:
        if zeile.startswith(f"{alt_name}  <-"):
            if neu_name is None:
                continue
            zeile = neu_name + zeile[len(alt_name):]
        neu.append(zeile)
    pfad.write_text("".join(neu), encoding="utf-8")


def freigeben(ausgabe_pfad) -> Path:
    """_PRUEFEN aus dem Namen entfernen (gleiche Nummer, sonst die nächste freie) und _zuordnung.txt
    nachführen. Eine Ausgabe ohne _PRUEFEN bleibt, wie sie ist."""
    ausgabe = Path(ausgabe_pfad)
    if not ausgabe.exists():
        raise FileNotFoundError(f"Ausgabedatei nicht gefunden: {ausgabe.name}")
    m = _AUSGABE_RE.match(ausgabe.name)
    if not m or not m.group(2):
        return ausgabe
    ordner = ausgabe.parent
    nummer = int(m.group(1))
    ziel = ordner / f"anonym_{nummer:02d}.pdf"
    while True:
        if not ziel.exists():
            try:
                _umbenennen_ohne_ueberschreiben(ausgabe, ziel)
                break
            except FileExistsError:
                pass
        nummer += 1
        while not _nummer_frei(ordner, nummer):
            nummer += 1
        ziel = ordner / f"anonym_{nummer:02d}.pdf"
    _zuordnung_umschreiben(ordner, ausgabe.name, ziel.name)
    cache_leeren(ausgabe)
    return ziel


def verwerfen(ausgabe_pfad) -> None:
    """Ausgabe löschen und aus _zuordnung.txt austragen."""
    ausgabe = Path(ausgabe_pfad)
    cache_leeren(ausgabe)
    if ausgabe.exists():
        ausgabe.unlink()
    _zuordnung_umschreiben(ausgabe.parent, ausgabe.name, None)


def als_pruefen_markieren(ausgabe_pfad) -> Path:
    """Emuliert freigabe_erforderlich für eine Engine ohne diesen Parameter: anonym_NN.pdf ->
    anonym_NN_PRUEFEN.pdf (die Nummer ist frei, weil die Schwärzung beide Formen als belegt zählt)."""
    ausgabe = Path(ausgabe_pfad)
    m = _AUSGABE_RE.match(ausgabe.name)
    if not m or m.group(2):
        return ausgabe
    ziel = ausgabe.with_name(f"anonym_{int(m.group(1)):02d}_PRUEFEN.pdf")
    _umbenennen_ohne_ueberschreiben(ausgabe, ziel)
    _zuordnung_umschreiben(ausgabe.parent, ausgabe.name, ziel.name)
    return ziel


# ----------------------------------------------------------------------
# Kundenliste (Attrappe)
# ----------------------------------------------------------------------
MERKMALE = {
    "name": "Name (vollständig)", "vorname": "Vorname", "nachname": "Nachname",
    "geburtsdatum": "Geburtsdatum", "strasse": "Straße (ggf. mit Hausnummer)", "hausnummer": "Hausnummer",
    "plz": "PLZ", "ort": "Ort", "iban": "IBAN", "kundennummer": "Kunden-/Vertragsnummer",
    "email": "E-Mail", "telefon": "Telefon", "kennzeichen": "Kfz-Kennzeichen",
}
STARKE_MERKMALE = ("name", "nachname", "iban", "kundennummer", "email")
_KOPF_MUSTER = {
    "vorname": r"vorname|first ?name",
    "nachname": r"nachname|familienname|last ?name|surname",
    "name": r"name|kunde|kundenname|versicherungsnehmer",
    "geburtsdatum": r"geb(urts)?(\.|datum)?|geboren|birth",
    "hausnummer": r"haus ?(nr|nummer)\.?|hnr\.?",
    "strasse": r"stra(ss|ß)e|str\.?|anschrift|adresse",
    "plz": r"plz|postleitzahl",
    "ort": r"ort|wohnort|stadt",
    "iban": r"iban",
    "kundennummer": r"(kunden|vertrags|versicherungsschein|vs|police)[ -]?(nr|nummer)\.?|kd[ .-]?nr\.?",
    "email": r"e-?mail|mail",
    "telefon": r"tel(efon)?\.?|mobil|handy|telefonnummer",
    "kennzeichen": r"(kfz[ -]?)?kennzeichen",
}


class SpaltenNichtErkannt(ValueError):
    """Die Kopfzeile der CSV-Datei enthält keine bekannten Spaltennamen – Zuordnung durch die Oberfläche."""


def spalten_erkennen(kopf) -> dict:
    """{merkmal: spaltenindex} für bekannte Spaltenüberschriften."""
    erkannt = {}
    for index, zelle in enumerate(kopf):
        text = str(zelle).strip().lower()
        for merkmal, muster in _KOPF_MUSTER.items():
            if merkmal not in erkannt and re.fullmatch(muster, text):
                erkannt[merkmal] = index
                break
    return erkannt


class Kundenliste:
    """Attrappe der Kundenliste (Vertrag Abschnitt 6): zählt Kunden, speichert nur die Anzahl, findet nichts."""

    attrappe = True

    def __init__(self, anzahl_kunden: int = 0):
        self.anzahl_kunden = int(anzahl_kunden)

    @staticmethod
    def importieren(csv_pfad, spalten: dict | None = None) -> "Kundenliste":
        """spalten: {merkmal: spaltenname (Kopfzeile vorhanden) | spaltenindex (int, keine Kopfzeile)}."""
        zeilen = dateien.csv_vorschau(csv_pfad, max_zeilen=None)["zeilen"]
        if not zeilen:
            raise ValueError("Die CSV-Datei ist leer.")
        kopf = zeilen[0]
        if spalten is None:
            zuordnung = spalten_erkennen(kopf)
            if not any(m in zuordnung for m in STARKE_MERKMALE):
                raise SpaltenNichtErkannt("Spalten der Kundenliste nicht erkannt.")
            daten = zeilen[1:]
        elif any(isinstance(v, str) for v in spalten.values()):
            zuordnung = {m: kopf.index(v) if isinstance(v, str) else int(v) for m, v in spalten.items()
                         if not isinstance(v, str) or v in kopf}
            daten = zeilen[1:]
        else:
            zuordnung = {m: int(v) for m, v in spalten.items()}
            daten = zeilen
        starke = [i for m, i in zuordnung.items() if m in STARKE_MERKMALE]
        if not starke:
            raise SpaltenNichtErkannt("Keine Spalte mit Name, Kundennummer, IBAN oder E-Mail zugeordnet.")
        anzahl = sum(1 for z in daten if any(i < len(z) and z[i].strip() for i in starke))
        return Kundenliste(anzahl)

    def speichern(self, pfad=None):
        pfad = Path(pfad) if pfad is not None else dateien.kundenliste_pfad()
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_text(json.dumps({"attrappe": True, "anzahl_kunden": self.anzahl_kunden}), encoding="utf-8")

    @staticmethod
    def laden(pfad=None) -> "Kundenliste | None":
        pfad = Path(pfad) if pfad is not None else dateien.kundenliste_pfad()
        try:
            daten = json.loads(pfad.read_text(encoding="utf-8"))
            return Kundenliste(int(daten["anzahl_kunden"]))
        except (OSError, ValueError, KeyError, TypeError):
            return None

    @staticmethod
    def entfernen(pfad=None):
        pfad = Path(pfad) if pfad is not None else dateien.kundenliste_pfad()
        if pfad.exists():
            pfad.unlink()

    def treffer(self, dok) -> list:
        return []


# ----------------------------------------------------------------------
# Meldungs-Codes (12.6) aus den Texten einer alten Engine
# ----------------------------------------------------------------------
_TEXT_CODES = (
    ("Kein angehakter Fund", "KEIN_TREFFER"),
    ("Kein Text lesbar", "KEIN_TEXT"),
    ("kaum lesbar", "KAUM_LESBAR"),
    ("OCR hat keinen Text", "OCR_FEHLER"),
    ("OCR ist nicht verfügbar", "OCR_FEHLER"),
    ("OCR-Dienst konnte nicht", "OCR_FEHLER"),
    ("per OCR gelesen", "OCR_GELESEN"),
    ("XFA", "XFA"),
    ("nicht lokalisiert", "NICHT_LOKALISIERT"),
    ("noch auffindbar", "RESTE"),
    ("Durch NIE-Liste freigegeben", "NIE_FREIGABE"),
    ("Formularfelder wurden eingebrannt", "FORMULAR_EINGEBRANNT"),
    ("enthalten Bilder", "BILDER_UNGEPRUEFT"),
    ("Grafiken/Zeichnungen", "VEKTORGRAFIK"),
    ("Entfernt bzw. eingebrannt", "NEBENKANAL_ENTFERNT"),
    ("Platzhalter in engen Lücken", "PLATZHALTER_GEKUERZT"),
    ("Zuordnung Original", "ZUORDNUNG"),
)


def meldungen_aus_texten(ergebnis: dict) -> list[dict]:
    """Strukturierte Meldungen (Vertrag 12.6) für eine Engine, die noch keine "meldungen" liefert.
    Die Textmuster stehen nur hier; die Oberfläche wertet ausschließlich die Codes aus (KQ-08)."""
    meldungen = []
    fehler = ergebnis.get("fehler")
    if fehler:
        code = "ABGEBROCHEN" if str(fehler).strip() == "Abgebrochen" else "FEHLER"
        meldungen.append({"art": "fehler", "code": code, "text": str(fehler), "seite": None})
    for art, liste in (("warnung", ergebnis.get("warnungen") or []), ("hinweis", ergebnis.get("hinweise") or [])):
        for text in liste:
            for muster, code in _TEXT_CODES:
                if muster in str(text):
                    meldungen.append({"art": art, "code": code, "text": str(text), "seite": None})
                    break
    if ergebnis.get("reste"):
        meldungen.append({"art": "warnung", "code": "RESTE", "text": ", ".join(map(str, ergebnis["reste"])),
                          "seite": None})
    return meldungen
