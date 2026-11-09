"""Analyse: Text und PDFs nach personenbezogenen Daten durchsuchen.

Ergebnis sind "Funde" (dict): kategorie, anzeige, text, ersatz, seiten, anzahl, kontext
(siehe Schnittstellen-Vertrag). analysiere_text arbeitet auf reinem Text (seiten bleibt
leer), analysiere_pdf liest ein PDF seitenweise (Textebene, bei Scans OCR) und füllt die
Seitennummern.
"""

import re
from pathlib import Path

import fitz  # PyMuPDF

from . import ocr as _ocr
from .muster import KATEGORIEN, KATEGORIE_PRIORITAET
from .namen import (ANREDEN, NAMEN_STOPPLISTE, PARTIKEL, TITEL, finde_personen, lade_ner,
                    ner_fehler)

ANZEIGE_BEGRIFF = "Begriff (IMMER-Liste)"
PLATZHALTER_BEGRIFF = "[BEGRIFF]"
_KONTEXT_RAND = 25


# ----------------------------------------------------------------------
# Hilfen
# ----------------------------------------------------------------------
def _normalisiert(text: str) -> str:
    """Leerraum zusammenziehen (für Vergleiche und die NIE-Liste)."""
    return re.sub(r"\s+", " ", text).strip()


def _such_muster(fundtext: str) -> re.Pattern:
    """Regex, der den Fundtext als ganzes Wort/Wortfolge mit beliebigem Leerraum zwischen
    den Wörtern findet (Groß-/Kleinschreibung egal, wie die Suche im PDF)."""
    teile = [re.escape(t) for t in fundtext.split()]
    if not teile:
        return re.compile(r"(?!x)x")
    muster = r"\s+".join(teile)
    if re.match(r"[\wäöüß]", fundtext):
        muster = r"(?<![\wäöüß])" + muster
    if re.search(r"[\wäöüß]$", fundtext.strip()):
        muster = muster + r"(?![\wäöüß])"
    return re.compile(muster, re.IGNORECASE)


def _spannen(text: str, fundtext: str) -> list:
    return [(m.start(), m.end()) for m in _such_muster(fundtext).finditer(text)]


def _kontext(text: str, fundtext: str) -> tuple:
    """(anzahl, kontext): Vorkommen im Text und ca. 25 Zeichen um das erste Vorkommen."""
    spannen = _spannen(text, fundtext)
    if not spannen:
        return 1, f"»{_normalisiert(fundtext)}«"
    s, e = spannen[0]
    davor = _normalisiert(text[max(0, s - _KONTEXT_RAND):s].replace("\n", " "))
    danach = _normalisiert(text[e:e + _KONTEXT_RAND].replace("\n", " "))
    mitte = _normalisiert(text[s:e].replace("\n", " "))
    kontext = f"{'…' if s > _KONTEXT_RAND else ''}{davor} »{mitte}« {danach}{'…' if e + _KONTEXT_RAND < len(text) else ''}"
    return len(spannen), _normalisiert(kontext)


def _kennung(text: str) -> str:
    """Schlüssel für 'gleicher Text': Groß-/Kleinschreibung egal (wie die Suche im PDF),
    aber nur bei reinem ASCII — Versalien mit Umlaut (MÜLLER) bleiben ein eigener Fund."""
    n = _normalisiert(text)
    return n.casefold() if n.isascii() else n


def _neuer_fund(kategorie, anzeige, text, ersatz) -> dict:
    return {"kategorie": kategorie, "anzeige": anzeige, "text": text, "ersatz": ersatz,
            "seiten": [], "anzahl": 1, "kontext": ""}


class _NieListe:
    """NIE-schwärzen-Liste: nur Ganzwort-/Ganzphrasen-Treffer, Mindestlänge 3.
    Ein Fund wird nur freigegeben, wenn er (normalisiert, Groß-/Kleinschreibung egal) genau
    einem Eintrag entspricht."""

    def __init__(self, eintraege):
        self.eintraege = set()
        for e in eintraege or []:
            n = _normalisiert(e).casefold().strip(".,;:")
            if len(n) >= 3:
                self.eintraege.add(n)

    def erlaubt(self, fundtext: str) -> bool:
        if not self.eintraege:
            return False
        return _normalisiert(fundtext).casefold().strip(".,;:") in self.eintraege


# ----------------------------------------------------------------------
# Namen und Pseudonyme
# ----------------------------------------------------------------------
_NAMENSSUFFIXE = {"jun.", "jun", "sen.", "sen", "junior", "senior", "jr.", "jr", "sr.", "sr"}


def _name_zerlegen(name: str) -> tuple:
    """(vornamen, nachname) aus einem Namen: Titel/Anreden/Partikel/Suffixe entfernt,
    'Nachname, Vorname' erkannt. Bei einem einzelnen Wort ist nachname None und das Wort
    steht in vornamen (Rolle offen)."""
    def tokens(teil):
        aus = []
        for roh in teil.split():
            t = roh.strip(".,;:()[]\"'")
            if not t:
                continue
            tl, rl = t.lower(), roh.lower()
            if tl in TITEL or rl in TITEL or tl in ANREDEN or rl in ANREDEN or rl in _NAMENSSUFFIXE:
                continue
            if t.islower() and tl in PARTIKEL:
                continue
            aus.append(t)
        return aus
    if "," in name:
        links, rechts = name.split(",", 1)
        nach, vor = tokens(links), tokens(rechts)
        if nach and vor:
            return vor, nach[-1]
        rest = nach + vor
    else:
        rest = tokens(name)
    if not rest:
        return [], None
    if len(rest) == 1:
        return rest, None
    return rest[:-1], rest[-1]


def _schluessel(wort: str) -> str:
    return wort.casefold().replace("ß", "ss")


def _bestandteile(name: str) -> list:
    """Namensbestandteile für eigene Funde: Mindestlänge 3, keine Titel/Partikel/Anreden."""
    aus = []
    for roh in re.split(r"[\s,]+", name):
        t = roh.strip(".,;:()[]\"'")
        if len(t) < 3:
            continue
        tl, rl = t.lower(), roh.lower()
        if tl in TITEL or rl in TITEL or tl in ANREDEN or tl in PARTIKEL or tl in NAMEN_STOPPLISTE:
            continue
        if rl in _NAMENSSUFFIXE or any(c.isdigit() for c in t):
            continue
        if t.casefold() != name.casefold():
            aus.append(t)
    return aus


def _pseudonym(nummer: int) -> str:
    return f"[PERSON {chr(65 + nummer)}]" if nummer < 26 else f"[PERSON {nummer + 1}]"


def _familienpseudonym(nummer: int) -> str:
    return f"[FAMILIE {chr(65 + nummer)}]" if nummer < 26 else f"[FAMILIE {nummer + 1}]"


def _personen_funde(text: str, kandidaten: list, nie: _NieListe, hinweise: list) -> list:
    """Baut aus den Namenskandidaten Personen mit festen Pseudonymen.

    - Varianten derselben Person (Dr. Max Mustermann / Mustermann, Max / MAX MUSTERMANN)
      teilen sich ein Pseudonym (Schlüssel: erster Vorname + Nachname).
    - Buchstaben werden in der Reihenfolge des ersten Auftretens vergeben.
    - Einzelne Nachnamen gehören zur einzigen Person mit diesem Nachnamen; tragen mehrere
      Personen den Nachnamen (Familie), wird er zu [FAMILIE A].
    - Bestandteile erben das Pseudonym ihrer Person (Nachname bei Familien -> [FAMILIE X]).
    """
    personen: dict = {}            # schluessel -> {"varianten": {text: pos}, "vor": set, "nach": str|None}
    einzel: list = []              # (text, pos, gruppe) einzelne Wörter ohne Gruppe
    text_cf = text.casefold()

    def position(t: str) -> int:
        p = text_cf.find(t.casefold())
        return p if p >= 0 else len(text)

    def person_anlegen(schl, vor, nach):
        return personen.setdefault(schl, {"varianten": {}, "vor": set(), "nach": nach, "pos": len(text)})

    for k in kandidaten:
        name = k["text"]
        if nie.erlaubt(name):
            hinweise.append(f"Durch NIE-Liste freigegeben: {name}")
            continue
        basis = k.get("gruppe") or name
        vor, nach = _name_zerlegen(basis)
        if nach is None and k.get("gruppe"):
            vor, nach = _name_zerlegen(name)
        if nach is None:
            einzel.append((name, k["start"]))
            continue
        schl = (_schluessel(vor[0]) if vor else "", _schluessel(nach))
        p = person_anlegen(schl, vor, nach)
        p["varianten"][name] = min(p["varianten"].get(name, len(text)), k["start"])
        p["vor"].update(_schluessel(v) for v in vor)
        p["pos"] = min(p["pos"], k["start"])

    # Register: Nachname -> Personen, Vorname -> Personen
    nach_index: dict = {}
    vor_index: dict = {}
    for schl, p in personen.items():
        nach_index.setdefault(schl[1], set()).add(schl)
        for v in p["vor"]:
            vor_index.setdefault(v, set()).add(schl)

    # Einzelne Wörter zuordnen: eindeutiger Nachname -> Person; Familie -> Familienplatzhalter;
    # eindeutiger Vorname -> Person; sonst eigene Person
    einzel_zuordnung: dict = {}    # text -> ("person", schl) | ("familie", nachname)
    for name, pos in einzel:
        s = _schluessel(name.strip(".,;:()"))
        if s in nach_index:
            traeger = nach_index[s]
            if len(traeger) == 1:
                schl = next(iter(traeger))
                personen[schl]["varianten"].setdefault(name, pos)
                personen[schl]["pos"] = min(personen[schl]["pos"], pos)
                einzel_zuordnung[name] = ("person", schl)
            else:
                einzel_zuordnung[name] = ("familie", s)
        elif s in vor_index:
            traeger = sorted(vor_index[s], key=lambda x: personen[x]["pos"])
            schl = traeger[0]
            personen[schl]["varianten"].setdefault(name, pos)
            personen[schl]["pos"] = min(personen[schl]["pos"], pos)
            einzel_zuordnung[name] = ("person", schl)
        else:
            schl = ("", s)
            p = person_anlegen(schl, [], None)
            p["varianten"].setdefault(name, pos)
            p["pos"] = min(p["pos"], pos)
            nach_index.setdefault(s, set()).add(schl)
            einzel_zuordnung[name] = ("person", schl)

    # Pseudonyme in Reihenfolge des ersten Auftretens
    reihenfolge = sorted(personen, key=lambda schl: personen[schl]["pos"])
    pseudonyme = {schl: _pseudonym(i) for i, schl in enumerate(reihenfolge)}
    familien = {}
    for schl in reihenfolge:
        nach = schl[1]
        if nach and len(nach_index.get(nach, ())) > 1 and nach not in familien:
            familien[nach] = _familienpseudonym(len(familien))

    def ersatz_fuer_teil(teil: str, eigene_person) -> str:
        s = _schluessel(teil)
        if s in familien:
            return familien[s]
        return pseudonyme[eigene_person]

    funde, gesehen = [], set()

    def hinzufuegen(anzeige, t, ersatz):
        schluessel = _kennung(t)
        if schluessel in gesehen:
            return
        if nie.erlaubt(t):
            hinweise.append(f"Durch NIE-Liste freigegeben: {t}")
            gesehen.add(schluessel)
            return
        gesehen.add(schluessel)
        funde.append(_neuer_fund("namen", anzeige, t, ersatz))

    # Erst alle Varianten (in Textreihenfolge), dann die Bestandteile
    varianten = []
    for schl in reihenfolge:
        for t, pos in personen[schl]["varianten"].items():
            varianten.append((pos, t, schl))
    for pos, t, schl in sorted(varianten):
        if t in einzel_zuordnung and einzel_zuordnung[t][0] == "familie":
            continue
        vor, nach = _name_zerlegen(t)
        if nach is None and vor and _schluessel(vor[0]) in familien:
            hinzufuegen("Name", t, familien[_schluessel(vor[0])])     # nackter Familienname
            continue
        hinzufuegen("Name", t, pseudonyme[schl])
    for name, zuordnung in einzel_zuordnung.items():
        if zuordnung[0] == "familie":
            hinzufuegen("Name", name, familien[zuordnung[1]])
    for pos, t, schl in sorted(varianten):
        for teil in _bestandteile(t):
            hinzufuegen("Name (Bestandteil)", teil, ersatz_fuer_teil(teil, schl))
    return funde


# ----------------------------------------------------------------------
# Textanalyse
# ----------------------------------------------------------------------
def _begriff_funde(text: str, immer_schwaerzen: list, hinweise: list) -> list:
    """IMMER-schwärzen-Begriffe: eigene Kategorie, nur wenn der Begriff (Ganzwort) vorkommt."""
    funde, gesehen = [], set()
    for begriff in immer_schwaerzen or []:
        b = _normalisiert(begriff)
        if len(b) < 2 or b.casefold() in gesehen:
            continue
        gesehen.add(b.casefold())
        muster = re.compile(r"(?<![\wäöüß])" + r"\s+".join(re.escape(t) for t in b.split()) + r"(?![\wäöüß])",
                            re.IGNORECASE)
        m = muster.search(text)
        if not m:
            continue
        funde.append(_neuer_fund("begriff", ANZEIGE_BEGRIFF, _normalisiert(m.group(0)), PLATZHALTER_BEGRIFF))
    return funde


_ANREDE_DAVOR_RE = re.compile(r"(?:Herrn?|Frau|Hr\.|Fr\.|Familie|Fam\.|Eheleute)[ \t]*$")


def _ohne_ortsnamen(text: str, kandidaten: list, muster_funde: list) -> list:
    """Einzelwort-Namenskandidaten verwerfen, die als Ort hinter einer PLZ vorkommen
    (die KI hält Städte gern für Personen) — außer hinter Herr/Frau."""
    orte = set()
    for f in muster_funde:
        if f["kategorie"] == "plzort":
            ort = re.sub(r"^\D*\d{4,5}\s*", "", f["text"]).strip()
            if ort:
                orte.add(_normalisiert(ort).casefold())
    if not orte:
        return kandidaten
    aus = []
    for k in kandidaten:
        if (" " not in k["text"] and k["text"].casefold() in orte
                and not _ANREDE_DAVOR_RE.search(text[max(0, k["start"] - 12):k["start"]])):
            continue
        aus.append(k)
    return aus


def _muster_funde(text: str, aktive: set, nie: _NieListe, hinweise: list) -> list:
    """Alle aktiven Muster-Kategorien; gleiche Texte nur einmal (spezifischste Kategorie)."""
    prioritaet = {k: i for i, k in enumerate(KATEGORIE_PRIORITAET)}
    beste: dict = {}       # text.casefold() -> fund
    reihenfolge: list = []
    for schluessel, anzeige, ersatz, funktion, _ in KATEGORIEN:
        if funktion is None or schluessel not in aktive:
            continue
        for treffer in funktion(text):
            t = treffer.strip()
            if len(t) < 2:
                continue
            kennung = _kennung(t)
            if kennung in beste:
                alt = beste[kennung]
                if prioritaet.get(schluessel, 99) < prioritaet.get(alt["kategorie"], 99):
                    alt.update(kategorie=schluessel, anzeige=anzeige, ersatz=ersatz, text=t)
                continue
            if nie.erlaubt(t):
                hinweise.append(f"Durch NIE-Liste freigegeben: {t}")
                beste[kennung] = None
                continue
            fund = _neuer_fund(schluessel, anzeige, t, ersatz)
            beste[kennung] = fund
            reihenfolge.append(fund)
    return [f for f in reihenfolge if beste.get(_kennung(f["text"])) is f]


def _bruchstuecke_entfernen(text: str, funde: list) -> list:
    """Positionsbasierter Bruchstück-Filter: Ein Muster-Fund fällt nur weg, wenn JEDE seiner
    Fundstellen innerhalb einer Fundstelle eines längeren Muster-Funds liegt (z. B. die
    'Telefonnummer' mitten in einer IBAN). Namen und IMMER-Begriffe werden nie gefiltert."""
    muster_funde = [f for f in funde if f["kategorie"] not in ("namen", "begriff")]
    spannen_cache: dict = {}

    def spannen(f):
        if f["text"] not in spannen_cache:
            spannen_cache[f["text"]] = _spannen(text, f["text"])
        return spannen_cache[f["text"]]

    behalten = []
    for f in funde:
        if f["kategorie"] in ("namen", "begriff"):
            behalten.append(f)
            continue
        eigene = spannen(f)
        if not eigene:
            behalten.append(f)
            continue
        kurz = _normalisiert(f["text"]).casefold()
        laengere = [g for g in muster_funde
                    if g is not f and len(g["text"]) > len(f["text"])
                    and kurz in _normalisiert(g["text"]).casefold()]
        if not laengere:
            behalten.append(f)
            continue
        huellen = [sp for g in laengere for sp in spannen(g)]
        eingeschlossen = all(any(hs <= s and e <= he for hs, he in huellen) for s, e in eigene)
        if not eingeschlossen:
            behalten.append(f)
    return behalten


def _analysiere(text: str, aktive: set, whitelist: list, immer_schwaerzen: list) -> tuple:
    """Kern der Analyse. Liefert (funde, hinweise)."""
    hinweise: list = []
    nie = _NieListe(whitelist)
    funde: list = []
    funde.extend(_begriff_funde(text, immer_schwaerzen, hinweise))
    muster_funde = _muster_funde(text, aktive, nie, hinweise)
    if "namen" in aktive:
        kandidaten = _ohne_ortsnamen(text, finde_personen(text), muster_funde)
        funde.extend(_personen_funde(text, kandidaten, nie, hinweise))
    funde.extend(muster_funde)

    # Doppelte Texte über alle Gruppen (Begriff > Name > Muster)
    gesehen, eindeutig = set(), []
    for f in funde:
        k = _kennung(f["text"])
        if k in gesehen:
            continue
        gesehen.add(k)
        eindeutig.append(f)
    funde = _bruchstuecke_entfernen(text, eindeutig)
    for f in funde:
        f["anzahl"], f["kontext"] = _kontext(text, f["text"])
    return funde, hinweise


def analysiere_text(text: str, aktive: set[str], whitelist: list[str],
                    immer_schwaerzen: list[str]) -> list[dict]:
    """Durchsucht einen Text nach allen aktivierten Kategorien.
    Liefert eine Liste von Funden: {kategorie, anzeige, text, ersatz, seiten, anzahl, kontext}
    (seiten bleibt leer; anzahl/kontext werden aus dem Text berechnet)."""
    funde, _ = _analysiere(text, set(aktive), whitelist, immer_schwaerzen)
    return funde


# ----------------------------------------------------------------------
# PDF-Analyse
# ----------------------------------------------------------------------
def _ocr_noetig(seite) -> str:
    """Vertrags-API ocr_noetig(seite) -> 'nein' | 'seite' | 'bilder'; Rückfall auf die alte
    Funktion ist_scan_seite, solange ocr.py sie noch nicht bietet."""
    if hasattr(_ocr, "ocr_noetig"):
        return _ocr.ocr_noetig(seite)
    return "seite" if _ocr.ist_scan_seite(seite) else "nein"


class _AlterOcrDienst:
    """Rückfall auf die alten Funktionen (ocr_textpage), wenn ocr.py noch keinen OcrDienst hat."""

    def __init__(self, doc):
        self.doc = doc

    def woerter(self, pdf_pfad, seite_nr0, dpi=300, clip=None):
        seite = self.doc[seite_nr0]
        tp, warnung = _ocr.ocr_textpage(seite)
        if tp is None:
            return [], warnung
        woerter = [(w[0], w[1], w[2], w[3], w[4]) for w in tp.extractWORDS()
                   if clip is None or fitz.Rect(w[:4]).intersects(clip)]
        return woerter, warnung

    def abbrechen(self):
        pass

    def schliessen(self):
        pass


def _woerter_zu_text(woerter) -> str:
    """OCR-Wörter (x0, y0, x1, y1, text) zu Zeilen zusammensetzen."""
    if not woerter:
        return ""
    sortiert = sorted(woerter, key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    zeilen, aktuelle, mitte = [], [], None
    for w in sortiert:
        m = (w[1] + w[3]) / 2
        hoehe = max(w[3] - w[1], 1.0)
        if mitte is None or abs(m - mitte) <= hoehe * 0.6:
            aktuelle.append(w)
            mitte = m if mitte is None else (mitte + m) / 2
        else:
            zeilen.append(" ".join(x[4] for x in sorted(aktuelle, key=lambda x: x[0])))
            aktuelle, mitte = [w], m
    if aktuelle:
        zeilen.append(" ".join(x[4] for x in sorted(aktuelle, key=lambda x: x[0])))
    return "\n".join(zeilen)


def _hat_xfa(doc) -> bool:
    try:
        katalog = doc.pdf_catalog()
        art, wert = doc.xref_get_key(katalog, "AcroForm/XFA")
        return art not in ("null", None) and wert not in ("null", "", None)
    except Exception:
        return False


def _bildbereiche(seite) -> list:
    """Rechtecke der größeren Bilder einer Textseite (für OCR der Bildbereiche)."""
    bereiche = []
    try:
        flaeche = abs(seite.rect)
        for info in seite.get_image_info():
            r = fitz.Rect(info["bbox"]) & seite.rect
            if not r.is_empty and abs(r) >= 0.03 * flaeche:
                bereiche.append(r)
    except Exception:
        pass
    return bereiche


def analysiere_pdf(pdf_pfad: Path, aktive: set[str], whitelist: list[str],
                   immer_schwaerzen: list[str], melde=None, fortschritt=None,
                   abbruch=None, ocr=None) -> dict:
    """Öffnet ein PDF (liest Scans per OCR) und liefert alle Funde mit Seitennummern.
    melde(text): Fortschrittstext; fortschritt(seite_1basiert, seiten_gesamt);
    abbruch: threading.Event (bei is_set() sofort aufhören, fehler='Abgebrochen');
    ocr: OcrDienst oder None (dann eigener Dienst im Prozess)."""
    pdf_pfad = Path(pdf_pfad)
    ergebnis = {"datei": pdf_pfad, "funde": [], "warnungen": [], "hinweise": [], "fehler": None,
                "seiten": 0, "ocr_seiten": 0, "ocr_cache": {}}
    aktive = set(aktive)
    try:
        doc = fitz.open(pdf_pfad)
    except Exception as e:
        ergebnis["fehler"] = f"Konnte nicht geöffnet werden: {e}"
        return ergebnis
    try:
        if doc.needs_pass:
            ergebnis["fehler"] = "Passwortgeschützt — übersprungen."
            return ergebnis
        ergebnis["seiten"] = len(doc)
        if _hat_xfa(doc):
            ergebnis["warnungen"].append("XFA-Formular: Feldinhalte können nicht geprüft werden")
        # Formularfelder und Anmerkungen in den Seiteninhalt einbrennen, damit ihre Werte
        # im Text auftauchen
        try:
            doc.bake()
        except Exception as e:  # ältere PyMuPDF-Version ohne bake()
            ergebnis["warnungen"].append(f"Formularfelder konnten nicht eingebrannt werden: {e}")

        eigener_dienst = None
        dienst = ocr
        if dienst is None:
            if hasattr(_ocr, "OcrDienst"):
                try:
                    eigener_dienst = _ocr.OcrDienst()
                except Exception as e:
                    ergebnis["warnungen"].append(f"OCR-Dienst konnte nicht gestartet werden: {e}")
                    eigener_dienst = _AlterOcrDienst(doc) if hasattr(_ocr, "ocr_textpage") else None
            elif hasattr(_ocr, "ocr_textpage"):
                eigener_dienst = _AlterOcrDienst(doc)
            dienst = eigener_dienst

        seitentexte: list = []
        ocr_warnung_gezeigt = False
        try:
            for nr in range(len(doc)):
                if abbruch is not None and abbruch.is_set():
                    ergebnis["fehler"] = "Abgebrochen"
                    return ergebnis
                if fortschritt:
                    fortschritt(nr + 1, len(doc))
                seite = doc[nr]
                teile = []
                text = seite.get_text()
                if text.strip():
                    teile.append(text)
                entscheidung = _ocr_noetig(seite)
                if entscheidung in ("seite", "bilder") and dienst is None:
                    if not ocr_warnung_gezeigt:
                        ergebnis["warnungen"].append(
                            f"Seite {nr + 1} enthält Bilder/Scans, aber OCR ist nicht verfügbar — "
                            f"dort kann nichts automatisch erkannt werden.")
                        ocr_warnung_gezeigt = True
                elif entscheidung == "seite":
                    if melde:
                        melde(f"   OCR läuft: {pdf_pfad.name}, Seite {nr + 1}/{len(doc)} …")
                    woerter, warnung = dienst.woerter(pdf_pfad, nr)
                    if warnung and not ocr_warnung_gezeigt:
                        ergebnis["warnungen"].append(warnung)
                        ocr_warnung_gezeigt = True
                    if woerter:
                        ergebnis["ocr_cache"][nr] = list(woerter)
                        ocr_text = _woerter_zu_text(woerter)
                        teile.append(ocr_text)
                        ergebnis["ocr_seiten"] += 1
                        # Blinden Fleck melden: Wenn die OCR auf einer Seite fast nichts
                        # lesen kann, kann sie dort auch nichts finden!
                        if len(ocr_text.split()) < 25:
                            ergebnis["warnungen"].append(
                                f"Seite {nr + 1} ist für die OCR kaum lesbar — dort kann "
                                f"NICHTS automatisch erkannt werden. Unbedingt manuell prüfen!")
                    elif not warnung:
                        ergebnis["warnungen"].append(
                            f"Seite {nr + 1}: OCR hat keinen Text gelesen — bitte manuell prüfen!")
                elif entscheidung == "bilder":
                    bereiche = _bildbereiche(seite)
                    bild_woerter = []
                    for r in bereiche:
                        if abbruch is not None and abbruch.is_set():
                            ergebnis["fehler"] = "Abgebrochen"
                            return ergebnis
                        try:
                            woerter, warnung = dienst.woerter(pdf_pfad, nr, clip=r)
                        except TypeError:        # alter Dienst ohne clip
                            woerter, warnung = dienst.woerter(pdf_pfad, nr)
                        if warnung and not ocr_warnung_gezeigt:
                            ergebnis["warnungen"].append(warnung)
                            ocr_warnung_gezeigt = True
                        bild_woerter.extend(woerter or [])
                    if bild_woerter:
                        ergebnis["ocr_cache"][nr] = bild_woerter
                        teile.append(_woerter_zu_text(bild_woerter))
                        ergebnis["hinweise"].append(
                            f"Seite {nr + 1}: Text in Bildern per OCR gelesen und mitgeprüft.")
                seitentexte.append("\n".join(teile))
        finally:
            if eigener_dienst is not None:
                try:
                    eigener_dienst.schliessen()
                except Exception:
                    pass
    finally:
        doc.close()

    text = "\n".join(seitentexte)
    if not text.strip():
        ergebnis["warnungen"].append("Kein Text lesbar — weder direkt noch per OCR.")
        return ergebnis
    if ergebnis["ocr_seiten"]:
        ergebnis["warnungen"].append(
            f"{ergebnis['ocr_seiten']} Seite(n) per OCR gelesen. OCR kann sich "
            f"verlesen — Ergebnis bitte besonders sorgfältig prüfen!")

    if abbruch is not None and abbruch.is_set():
        ergebnis["fehler"] = "Abgebrochen"
        return ergebnis
    if melde:
        melde(f"   Erkennung läuft: {pdf_pfad.name} …")
    funde, hinweise = _analysiere(text, aktive, whitelist, immer_schwaerzen)
    ergebnis["hinweise"].extend(hinweise)

    # Seitennummern je Fund (Leerraum normalisiert); Rückfall über die Zeichenposition
    grenzen, lauf = [], 0
    for st in seitentexte:
        lauf += len(st) + 1
        grenzen.append(lauf)
    for f in funde:
        muster = _such_muster(f["text"])
        seiten = [i + 1 for i, st in enumerate(seitentexte) if muster.search(st)]
        if not seiten:
            m = muster.search(text)
            if m:
                seiten = [next(i + 1 for i, g in enumerate(grenzen) if m.start() < g)]
        f["seiten"] = seiten
    ergebnis["funde"] = funde

    if "namen" in aktive and lade_ner() is None:
        ergebnis["warnungen"].append(
            "Namenserkennung inaktiv: " + (ner_fehler() or "Modell fehlt."))
    return ergebnis
