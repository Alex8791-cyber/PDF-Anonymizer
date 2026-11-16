"""Neue Dokumenttypen der ERWEITERTEN Verteilung (Generator 1.2; Korpora s3x zum Abstimmen, s9x zur Kontrolle).

Opt-in: nur plane_korpus(..., erweitert=True) bzw. erzeuge_korpus(..., erweitert=True) verwendet diese Typen –
mit eigenen Zufallsströmen ("plan_erweitert/<seed>", "x<seed>/<nr>/<versuch>", Kennung "x<seed>-<nr>"). Die
Standardverteilung (Seeds 1 und 7, vorhandene Korpora, CI-Korpus mit 12 Dokumenten) bleibt byte-gleich.

Alle Inhalte stammen aus öffentlichen Formatbeschreibungen und dem Büroalltag eines Versicherungsmaklers, nie aus
einem Prüfkorpus:

    personalausweis       Ausweiskopie Vorder- und Rückseite, maschinenlesbare Zone TD1 (ICAO 9303, 3 x 30 Zeichen
                          mit Prüfziffern); Variante vorläufiger Personalausweis mit TD2 (2 x 36); teils mit
                          Legitimationsblatt nach dem Geldwäschegesetz
    reisepass             Kopie der Datenseite mit TD3 (2 x 44), auch ausländische Pässe mit englischen Feldnamen
    fuehrerschein         EU-Kartenführerschein: Werte hinter den Feldnummern 1., 2., 3., 4a.-4d., 5., 8., 9. – ohne
                          Feldnamen
    sepa_mandat           SEPA-Lastschriftmandat: Gläubiger-ID, Mandatsreferenz, Kontoinhaber, Anschrift, IBAN/BIC,
                          Ort/Datum, Unterschrift; Feldnamen unter der Linie oder links, IBAN teils in Kästchen
    bestandsliste_excel   Excel-Export im Querformat: viele Spalten, Feldnamen nur im Spaltenkopf (Versalien,
                          abgekürzt, "VN_NAME"), Werte oft in Versalien und mit Umschrift (MUELLER)
    unfallbericht         Europäischer Unfallbericht (Fahrzeug A/B nebeneinander, Feldname klein über dem Wert)
                          oder polizeiliche Unfallmitteilung (Beteiligte 01/02 als Spalten, Feldnamen links)
    fax                   Faxausdruck: Kopfzeile mit Datum, Absender, Faxnummer und Seite x/y auf jeder Seite, 1 Bit
    schreibmaschine       Schreibmaschinenbrief/-formular oder EDV-Ausdruck in Courier, Ausrichtung mit Leerzeichen
    handschrift_formular  Formular mit handschriftlich wirkenden Einträgen (Schreibschrift der Systemschriften,
                          zitternde Grundlinie, blaue Tinte)
    blockschrift_formular Formular in Druckbuchstaben (Versalien) mit Kammfeldern: ein Zeichen je Kästchen

Jeder Wert steht in einer Auszeichnung (Wahrheit mit Wortrechtecken); Scans entstehen wie bisher über
generator._scannen (Schräglage, niedrige Auflösung, Fax, Drehung).
"""

from __future__ import annotations

import datetime
import os
import random

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen
    import fitz

from . import kennungen as K
from . import satz as S
from . import stammdaten as D
from .bausteine import Dok, Fluss, Person, ascii_name, datum, name_bem, stil_waehlen
from .dokumenttypen import TYPEN, _betrag, _seitenzahl_registrieren, typ_brief, typ_mahnung
from .satz import A4_B, A4_H, MM, Schrift, k, m

TINTE = (0.08, 0.12, 0.48)            # Kugelschreiber blau
TINTE_SCHWARZ = (0.1, 0.1, 0.12)

# ----------------------------------------------------------------------
# Plan der erweiterten Verteilung
# ----------------------------------------------------------------------
NEUE_TYPEN_REIHENFOLGE = ["personalausweis", "reisepass", "fuehrerschein", "sepa_mandat", "bestandsliste_excel",
                          "unfallbericht", "fax", "schreibmaschine", "handschrift_formular", "blockschrift_formular"]
QUERFORMAT_NEU = frozenset({"bestandsliste_excel"})
# Zeilen je Excel-Liste (Generator 1.2: 22-40 – eine Liste trug dann zwei Drittel aller Kern-Einträge eines Korpus)
EXCEL_ZEILEN = (8, 14)
# Absender von Versicherer-Faxen (Markennamen der Erlaubnisliste – kein Personenname)
FAX_MARKEN = ["HUK-COBURG", "ERGO", "SIGNAL IDUNA", "Debeka", "Provinzial", "Gothaer", "ALLIANZ", "AXA",
              "Alte Leipziger", "HanseMerkur", "DEVK", "Barmenia"]
# vorläufige Personalausweise (TD2): jeder dritte Personalausweis eines erweiterten Korpus, mindestens zwei
TD2_JE_PERSONALAUSWEIS = 3
# Scan-Wahrscheinlichkeit und Varianten je neuem Typ (Ausweiskopien und handschriftliche Formulare sind fast
# immer Scans, Excel-Listen fast nie; Faxe immer 1 Bit)
SCAN_NEU = {
    "personalausweis": (0.85, ["scan_300_gut", "scan_200_schraeg", "scan_farbig", "scan_durchsuchbar",
                               "scan_150_rauschen", "scan_rotate_90", "scan_120_schlecht"]),
    "reisepass": (0.85, ["scan_300_gut", "scan_farbig", "scan_200_schraeg", "scan_durchsuchbar",
                         "scan_150_rauschen", "scan_rotate_270"]),
    "fuehrerschein": (0.85, ["scan_300_gut", "scan_farbig", "scan_200_schraeg", "scan_150_rauschen",
                             "scan_durchsuchbar", "scan_120_schlecht"]),
    "sepa_mandat": (0.5, ["scan_300_gut", "scan_200_schraeg", "fax", "scan_150_rauschen", "scan_durchsuchbar"]),
    "bestandsliste_excel": (0.15, ["scan_300_gut", "scan_rotate_90", "scan_200_schraeg"]),
    "unfallbericht": (0.75, ["scan_300_gut", "scan_200_schraeg", "scan_150_rauschen", "scan_farbig", "fax",
                             "scan_120_schlecht"]),
    "fax": (1.0, ["fax", "fax", "fax_fein"]),
    "schreibmaschine": (0.65, ["scan_300_gut", "scan_200_schraeg", "scan_150_rauschen", "fax", "scan_120_schlecht",
                               "scan_kopfstehend"]),
    "handschrift_formular": (0.85, ["scan_300_gut", "scan_200_schraeg", "scan_150_rauschen", "scan_farbig",
                                    "scan_120_schlecht", "fax"]),
    "blockschrift_formular": (0.8, ["scan_300_gut", "scan_200_schraeg", "scan_150_rauschen", "fax",
                                    "scan_durchsuchbar", "scan_rotate_180"]),
}
# Zusätzliche Scan-Variante: Fax in feiner Auflösung (204 x 196 dpi)
SCAN_VARIANTEN_NEU = {
    "fax_fein": dict(dpi=204, dpi_y=196, fax=True, jpeg=None, schraeg=(0.0, 1.2), rauschen=(3, 8),
                     flecken=(0.0001, 0.0004)),
}


def plane_erweitert(anzahl: int, seed: int, je_typ: int = 6, alte_typen=None, alte_gewichte=None,
                    scan_folge=None, nebenkanaele=()) -> list:
    """Plan der erweiterten Verteilung: jeder neue Typ mindestens `je_typ`-mal (soweit `anzahl` reicht), die
    ersten zehn Dokumente decken alle neuen Typen ab (auch kleine Läufe), der Rest mischt alte und neue Typen.
    Eigener Zufallsstrom "plan_erweitert/<seed>"."""
    from .generator import Plan
    rng = random.Random(f"plan_erweitert/{seed}")
    neu = list(NEUE_TYPEN_REIHENFOLGE)
    kontingent = []
    for runde in range(je_typ):
        for t in neu:
            kontingent.append(t)
    erste = list(neu)
    rng.shuffle(erste)
    rest = kontingent[len(neu):]
    alte_typen = list(alte_typen or [])
    while len(erste) + len(rest) < anzahl:
        if alte_typen and rng.random() < 0.6:
            rest.append(rng.choices(alte_typen, alte_gewichte)[0])
        else:
            rest.append(rng.choice(neu))
    rng.shuffle(rest)
    typen = (erste + rest)[:anzahl]
    plaene = []
    scan_index = 0
    for nr, typ in enumerate(typen, 1):
        if typ in SCAN_NEU:
            quote, varianten = SCAN_NEU[typ]
            scan = rng.choice(varianten) if rng.random() < quote else None
        else:
            scan = None
            if rng.random() < 0.32 and scan_folge:
                scan = scan_folge[scan_index % len(scan_folge)]
                scan_index += 1
        neben = tuple(n for n in nebenkanaele if rng.random() < 0.12)
        plaene.append(Plan(nr, typ, scan, neben, mischung="erweitert"))
    # Mindestzahl vorläufiger Personalausweise (TD2) ohne eigenen Zufall: der 2., 5., 8. … Personalausweis
    ausweise = [p for p in plaene if p.typ == "personalausweis"]
    for i, p in enumerate(ausweise):
        if i % TD2_JE_PERSONALAUSWEIS == 1 or (len(ausweise) >= 2 and i == len(ausweise) - 1 and len(ausweise) < 5):
            p.variante = "td2"
    return plaene


def dok_fuer(typ: str, rng, kennung: str, scan: str | None, variante: str | None = None) -> Dok:
    """Dokument-Kontext für einen neuen Typ: Schreibmaschine und EDV-Ausdruck in Courier, Excel in Calibri/Arial."""
    stil = None
    if typ == "schreibmaschine":
        stil = stil_waehlen(rng, familie=rng.choice(["mono", "cour", "cour"]), groesse=rng.choice([10, 10, 11, 12]),
                            zeilenabstand=rng.choice([1.15, 1.25, 1.5]))
        stil.blocksatz = False
        stil.trennung = False
    elif typ == "bestandsliste_excel":
        stil = stil_waehlen(rng, familie=rng.choice(["carlito", "carlito", "sans", "helv"]))
    dok = Dok(rng, kennung, stil=stil, querformat=typ in QUERFORMAT_NEU)
    dok.scan_geplant = scan
    dok.variante = variante
    return dok


# ----------------------------------------------------------------------
# Schriften: Schreibschrift, Druckbuchstaben, MRZ
# ----------------------------------------------------------------------
_HANDSCHRIFT_DATEIEN = ["Z003-MediumItalic.otf", "segoesc.ttf", "Inkfree.ttf", "LHANDW.TTF", "BRADHITC.TTF",
                        "comic.ttf", "Comic Sans MS.ttf", "URWChanceryL-MediItal.otf"]
_SCHRIFT_ZWISCHENSPEICHER: dict = {}


def _datei_suchen(namen) -> str | None:
    gesucht = [n.lower() for n in namen]
    gefunden = {}
    for basis in S._schriftordner():
        if not basis or not os.path.isdir(basis):
            continue
        for wurzel, _, dateien in os.walk(basis):
            for d in dateien:
                if d.lower() in gesucht and d.lower() not in gefunden:
                    gefunden[d.lower()] = os.path.join(wurzel, d)
    for n in gesucht:
        if n in gefunden:
            return gefunden[n]
    return None


def handschrift() -> Schrift:
    """Schreibschrift aus den installierten Schriften (Linux: URW Z003, Windows: Segoe Script, Ink Free …);
    ersatzweise eine kursive Grotesk."""
    if "hand" not in _SCHRIFT_ZWISCHENSPEICHER:
        datei = _datei_suchen(_HANDSCHRIFT_DATEIEN) or S.schriftdatei(["LiberationSans-Italic.ttf", "ariali.ttf"])
        _SCHRIFT_ZWISCHENSPEICHER["hand"] = Schrift("helv", datei) if datei else Schrift("heit")
    return _SCHRIFT_ZWISCHENSPEICHER["hand"]


def druckschrift() -> Schrift:
    """Druckbuchstaben (Blockschrift): fette Grotesk ohne Serifen."""
    if "druck" not in _SCHRIFT_ZWISCHENSPEICHER:
        datei = S.schriftdatei(["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "arialbd.ttf"])
        _SCHRIFT_ZWISCHENSPEICHER["druck"] = Schrift("hebo", datei)
    return _SCHRIFT_ZWISCHENSPEICHER["druck"]


def mrz_schrift() -> Schrift:
    """Schrift der maschinenlesbaren Zone (OCR-B ist selten installiert: nichtproportionale Grotesk/Courier)."""
    if "mrz" not in _SCHRIFT_ZWISCHENSPEICHER:
        datei = S.schriftdatei(["DejaVuSansMono.ttf", "LiberationMono-Regular.ttf", "cour.ttf", "consola.ttf"])
        _SCHRIFT_ZWISCHENSPEICHER["mrz"] = Schrift("cour", datei)
    return _SCHRIFT_ZWISCHENSPEICHER["mrz"]


# ----------------------------------------------------------------------
# Setzhilfen: Handschrift, Kammfelder, Feldnamen unter der Linie
# ----------------------------------------------------------------------
def _gedreht(r: tuple, punkt, winkel: float) -> list:
    """Achsenparalleles Rechteck um ein um `punkt` gedrehtes Rechteck (beide Drehrichtungen, großzügig)."""
    xs, ys = [], []
    for w in (winkel, -winkel):
        mat = fitz.Matrix(1, 1).prerotate(w)
        for x, y in ((r[0], r[1]), (r[2], r[1]), (r[0], r[3]), (r[2], r[3])):
            q = (fitz.Point(x, y) - punkt) * mat + punkt
            xs.append(q.x)
            ys.append(q.y)
    return [min(xs), min(ys), max(xs), max(ys)]


def hand(seite, x: float, y: float, markup: str, rng, groesse: float = 11.0, farbe=TINTE, zittern: bool = True,
         schrift: Schrift | None = None, zusatz: str = "") -> float:
    """Eine Zeile "handschriftlich": Wort für Wort mit zufälliger Grundlinie, Größe und (nur bei `zittern`)
    Neigung. Einträge bekommen je Wort ein Rechteck (bei Neigung das umschließende). Liefert das x-Ende."""
    schrift = schrift or handschrift()
    satz = seite.satz
    stuecke = satz.zerlegen(markup, schrift, seite.nr, zusatz)
    woerter = [w for w in seite._woerter(stuecke) if w != "\n"]
    lauf = x
    leer = schrift.breite(" ", groesse)
    for wort in woerter:
        g = groesse * rng.uniform(0.93, 1.07)
        dy = rng.uniform(-1.3, 1.3) if zittern else rng.uniform(-0.4, 0.4)
        winkel = rng.uniform(-3.5, 3.5) if zittern else 0.0
        text = "".join(s.text for s in wort)
        punkt = fitz.Point(lauf, y + dy)
        if not satz.messmodus:
            if winkel:
                seite.page.insert_text(punkt, text, fontsize=g, fontname=schrift.name, fontfile=schrift.datei,
                                       color=farbe, morph=(punkt, fitz.Matrix(1, 1).prerotate(winkel)))
            else:
                schrift.setzen(seite.page, punkt.x, punkt.y, text, g, farbe)
        pos = lauf
        for s in wort:
            b = schrift.breite(s.text, g)
            if not satz.messmodus:
                if s.eintrag is not None:
                    r = (pos, punkt.y - schrift.aufstieg * g, pos + b, punkt.y + schrift.abstieg * g)
                    s.eintrag["woerter"].append(_gedreht(r, punkt, winkel) + [s.text])
                else:
                    satz.klartext_merken(seite.nr, s.text)
            pos += b
        lauf = pos + leer * rng.uniform(0.9, 1.5)
    return lauf


def kammfeld(seite, x: float, y: float, n: int, kategorie: str | None, wert: str, bemerkung: str = "",
             schrift: Schrift | None = None, groesse: float = 11.0, rng=None, kasten: float = 5.0 * MM,
             hoehe: float = 6.4 * MM, farbe=TINTE_SCHWARZ, gruppen=None) -> float:
    """Kammfeld mit `n` Kästchen ab (x, y = Oberkante); `wert` steht ein Zeichen je Kästchen (Leerzeichen lässt ein
    Kästchen frei). `gruppen`: Kästchenzahlen je Gruppe mit kleiner Lücke (IBAN in Vierergruppen). Der Wert ist EIN
    Eintrag; Wortrechtecke je Wort (zusammenhängende Kästchen). Liefert das x-Ende."""
    schrift = schrift or druckschrift()
    satz = seite.satz
    luecke = 1.6 * MM
    kaesten = []
    pos = x
    grenzen = set()
    if gruppen:
        summe = 0
        for g in gruppen[:-1]:
            summe += g
            grenzen.add(summe)
    for i in range(n):
        if i in grenzen:
            pos += luecke
        kaesten.append((pos, y, pos + kasten, y + hoehe))
        pos += kasten
    if not satz.messmodus:
        form = seite.page.new_shape()
        for r in kaesten:
            form.draw_rect(fitz.Rect(r))
        form.finish(color=(0.25, 0.25, 0.3), width=0.5)
        form.commit()
    dargestellt = schrift.darstellbar(wert)
    bem = bemerkung + ("; transliteriert" if dargestellt != wert else "")
    eintrag = satz.eintrag(dargestellt, kategorie, seite.nr, bemerkung=bem) if (kategorie and dargestellt.strip()
                                                                                and not satz.messmodus) else None
    if kategorie is None and dargestellt.strip():
        satz.klartext_merken(seite.nr, dargestellt)
    wort = None
    for i, c in enumerate(dargestellt[:n]):
        x0, y0, x1, y1 = kaesten[i]
        if c == " ":
            if wort and eintrag is not None:
                eintrag["woerter"].append(wort)
            wort = None
            continue
        g = groesse * (rng.uniform(0.94, 1.06) if rng else 1.0)
        b = schrift.breite(c, g)
        dx = rng.uniform(-0.6, 0.6) if rng else 0.0
        dy = rng.uniform(-0.7, 0.7) if rng else 0.0
        gx = (x0 + x1) / 2 - b / 2 + dx
        gy = y1 - (hoehe - schrift.aufstieg * g) / 2 - 0.4 + dy
        if not satz.messmodus:
            schrift.setzen(seite.page, gx, gy, c, g, farbe)
        oben, unten = gy - schrift.aufstieg * g, gy + schrift.abstieg * g
        if wort is None:
            wort = [gx, oben, gx + b, unten, c]
        else:
            wort = [wort[0], min(wort[1], oben), gx + b, max(wort[3], unten), wort[4] + c]
    if wort and eintrag is not None:
        eintrag["woerter"].append(wort)
    return kaesten[-1][2] if kaesten else x


def feld_unter_linie(seite, x: float, y: float, breite: float, etikett: str, wert_markup: str, dok: Dok,
                     handschriftlich: bool = False, groesse: float | None = None, etikett_groesse: float = 6.5):
    """Wert über einer Linie, Feldname klein UNTER der Linie (typisch für SEPA-Mandate und Behördenformulare);
    y = Grundlinie des Werts."""
    st = dok.stil
    seite.linie(x, y + 2.2, x + breite, y + 2.2, 0.5, (0.2, 0.2, 0.2))
    seite.text(x, y + 2.2 + etikett_groesse + 1.0, etikett, st.normal, etikett_groesse, farbe=(0.25, 0.25, 0.25))
    if wert_markup:
        if handschriftlich:
            hand(seite, x + 2, y, wert_markup, dok.rng, groesse=groesse or 11.5, zittern=dok.scan_geplant is not None)
        else:
            seite.text(x + 1, y, wert_markup, st.normal, groesse or max(9.0, st.groesse))


def _wert(dok: Dok, seite, x: float, y: float, markup: str, handschriftlich: bool, groesse: float = 10.0,
          schrift: Schrift | None = None):
    """Eingetragener Wert: handschriftlich (zitternd nur auf Scans) oder getippt."""
    if handschriftlich:
        return hand(seite, x, y, markup, dok.rng, groesse=groesse * 1.12, zittern=dok.scan_geplant is not None)
    return seite.text(x, y, markup, schrift or dok.stil.normal, groesse)


def _versal(text: str, umschrift: bool = False) -> str:
    """Versalien wie in Ausweisen und EDV-Listen (ß -> SS; mit Umschrift Ä -> AE)."""
    t = text.upper().replace("ẞ", "SS")
    if umschrift:
        t = (t.replace("Ä", "AE").replace("Ö", "OE").replace("Ü", "UE"))
        t = ascii_name(t).upper()
    return t


def _behoerde(rng, ort: str) -> str:
    return rng.choice(["STADT", "STADT", "GEMEINDE", "LANDKREIS", "LANDRATSAMT"]) + " " + _versal(ort.split(" (")[0])


# ----------------------------------------------------------------------
# Ausweisdokumente: Karte, Lichtbild, MRZ
# ----------------------------------------------------------------------
def _karte(seite, r, rand=(0.35, 0.4, 0.55), fuellung=(0.93, 0.95, 0.97), rng=None):
    """Karte mit abgerundeten Ecken, zartem Sicherheitsmuster (Linien ohne Text)."""
    if seite.satz.messmodus:
        return
    page = seite.page
    page.draw_rect(fitz.Rect(r), color=rand, fill=fuellung, width=0.8, radius=0.06)
    if rng is not None:
        form = page.new_shape()
        x0, y0, x1, y1 = r
        for i in range(7):
            y = y0 + (y1 - y0) * (i + 1) / 8
            form.draw_bezier((x0 + 4, y), (x0 + (x1 - x0) * 0.3, y - 9 + rng.uniform(-3, 3)),
                             (x0 + (x1 - x0) * 0.7, y + 9 + rng.uniform(-3, 3)), (x1 - 4, y))
        form.finish(color=(0.8, 0.84, 0.9), width=0.3)
        form.commit()


def _lichtbild(seite, r):
    """Lichtbild als graue Silhouette (kein Text)."""
    if seite.satz.messmodus:
        return
    x0, y0, x1, y1 = r
    form = seite.page.new_shape()
    form.draw_rect(fitz.Rect(r))
    form.finish(color=(0.5, 0.5, 0.5), fill=(0.82, 0.83, 0.85), width=0.4)
    b, h = x1 - x0, y1 - y0
    form.draw_circle(fitz.Point(x0 + b / 2, y0 + h * 0.38), b * 0.22)
    form.finish(fill=(0.55, 0.56, 0.6), color=None)
    form.draw_oval(fitz.Rect(x0 + b * 0.15, y0 + h * 0.62, x1 - b * 0.15, y1 + h * 0.25) & fitz.Rect(r))
    form.finish(fill=(0.55, 0.56, 0.6), color=None)
    form.commit()


def _etikett_wert(seite, x: float, y: float, etikett: str, wert_markup: str, dok: Dok, groesse: float = 8.5,
                  etikett_groesse: float = 5.2, schrift: Schrift | None = None) -> float:
    """Feldname klein über dem Wert (Ausweise); y = Grundlinie des Feldnamens. Liefert die Grundlinie des Werts."""
    st = dok.stil
    seite.text(x, y, etikett, st.normal, etikett_groesse, farbe=(0.3, 0.32, 0.4))
    yw = y + groesse * 1.15
    if wert_markup:
        seite.text(x, yw, wert_markup, schrift or st.fett, groesse)
    return yw


def _mrz_zeilen(seite, x: float, y: float, zeilen: list, groesse: float = 9.5):
    """MRZ-Zeilen setzen (Auszeichnungen schon enthalten)."""
    sch = mrz_schrift()
    for z in zeilen:
        seite.text(x, y, z, sch, groesse)
        y += groesse * 1.45
    return y


def _person_ausweis(dok: Dok, alter=(18, 80)) -> Person:
    p = dok.person(alter=alter, titel_quote=0.06, adel_quote=0.03)
    dok.hauptperson = p
    return p


def _gwg_kopf(dok: Dok, fl: Fluss, p: Person, art: str, nummer_markup: str, behoerde_markup: str,
              gueltig: datetime.date):
    """Legitimationsblatt nach dem Geldwäschegesetz (Kopf über der Ausweiskopie)."""
    st = dok.stil
    makler = dok.person(alter=(30, 65), titel_quote=0.0)
    fl.ueberschrift(k("Legitimationsprüfung nach dem Geldwäschegesetz (GwG)"), groesse=st.groesse + 3)
    fl.kv("Kunde (Name, Vorname):", m("namen", p.liste(), name_bem(p, "GwG-Blatt")), tab=55 * MM)
    geb, gbem = dok.geburtsdatum_text(p.geburtsdatum, "punkt")
    fl.kv("Geburtsdatum:", m("geburt", geb, "GwG-Blatt; " + gbem), tab=55 * MM)
    fl.kv("Ausweisart:", k(art), tab=55 * MM)
    fl.kv("Ausweisnummer:", nummer_markup, tab=55 * MM)
    fl.kv("Ausstellende Behörde:", behoerde_markup, tab=55 * MM)
    fl.kv("Gültig bis:", datum(gueltig), tab=55 * MM)
    fl.kv("Identifiziert durch:", m("namen", makler.voll(), name_bem(makler, "GwG-Blatt Mitarbeiter")) + " am "
          + k(datum(dok.heute)), tab=55 * MM)
    fl.absatz("Die Kopie des Ausweisdokuments stimmt mit dem vorgelegten Original überein. Aufbewahrung nach "
              + k("§ 8 GwG") + " für fünf Jahre.", groesse=st.groesse * 0.9)
    fl.luecke(st.zeilenhoehe * 0.5)


def typ_personalausweis(dok: Dok) -> str:
    """Kopie eines Personalausweises (Vorder- und Rückseite) mit TD1-MRZ; Variante vorläufiger Ausweis (TD2)."""
    rng = dok.rng
    st = dok.stil
    p = _person_ausweis(dok)
    seite = dok.satz.neue_seite()
    vorlaeufig = rng.random() < 0.25 or getattr(dok, "variante", None) == "td2"
    nummer = K.personalausweisnummer(rng, False)
    if vorlaeufig:
        nummer = rng.choice("ABCDEFGHJ") + "".join(rng.choice("0123456789") for _ in range(8))
    ausstellung = dok.heute - datetime.timedelta(days=rng.randint(20, 300) if vorlaeufig else rng.randint(100, 3000))
    jahre = 1 if vorlaeufig else (10 if (dok.heute - p.geburtsdatum).days > 24 * 365 else 6)
    gueltig = ausstellung.replace(year=ausstellung.year + jahre, day=min(ausstellung.day, 28)) \
        - datetime.timedelta(days=1)
    behoerde = _behoerde(rng, p.ort)
    nachname_druck = _versal(p.nachname)
    y = 22 * MM
    fl = None
    if rng.random() < 0.45:
        fl = Fluss(dok, 25 * MM, A4_B - 20 * MM, 20 * MM, A4_H - 20 * MM, seite=seite, y_start=y)
        _gwg_kopf(dok, fl, p, "Vorläufiger Personalausweis" if vorlaeufig else "Personalausweis",
                  m("ausweis", nummer, "GwG-Blatt Ausweisnummer"), m("sonstiges", behoerde, "GwG-Blatt Behörde"),
                  gueltig)
        y = fl.y + 4 * MM
    else:
        dok.satz.merkmale.add("nur_kopie")
    skala = rng.uniform(1.25, 1.55)
    kb, kh = 85.6 * MM * skala, 54.0 * MM * skala
    x = (A4_B - kb) / 2 + rng.uniform(-15, 15)
    geb_text = f"{p.geburtsdatum:%d.%m.%Y}"
    vornamen_druck = _versal(p.vornamen)
    if vorlaeufig:
        # Papierausweis (A6-ähnlich), eine Seite mit TD2-MRZ
        r = (x, y, x + kb, y + kh * 1.25)
        _karte(seite, r, rand=(0.4, 0.4, 0.4), fuellung=(0.96, 0.95, 0.9), rng=rng)
        seite.text(x + 6, y + 14, k("VORLÄUFIGER PERSONALAUSWEIS"), st.fett, 9)
        seite.text(x + 6, y + 22, "BUNDESREPUBLIK DEUTSCHLAND", st.normal, 6.5)
        _lichtbild(seite, (x + 6, y + 30, x + 6 + 26 * MM, y + 30 + 33 * MM))
        fx = x + 12 + 26 * MM
        yy = y + 34
        for etikett, wert in (("Name", m("namen", nachname_druck, name_bem(p, "Ausweis Name; Versalien"))),
                              ("Vornamen", m("namen", vornamen_druck, "Ausweis Vornamen; Versalien")),
                              ("Geburtstag", m("geburt", geb_text, "Ausweis Geburtstag")),
                              ("Geburtsort", m("sonstiges", _versal(rng.choice(D.GEBURTSORTE)), "Ausweis Geburtsort")),
                              ("Anschrift", m("strasse", _versal(p.strasse_hnr()), "Ausweis Anschrift") + ", "
                               + m("plzort", _versal(p.plz_ort()), "Ausweis Anschrift")),
                              ("Gültig bis", datum(gueltig))):
            yy = _etikett_wert(seite, fx, yy, etikett, wert, dok, groesse=8) + 9
        seite.text(x + kb - 6, y + 14, m("ausweis", nummer, "Ausweisnummer oben rechts"), st.normal, 9,
                   ausrichtung="rechts")
        zeilen = K.mrz_td2("D", nummer, p.geburtsdatum, "<", gueltig, "D", p.nachname, p.vornamen)
        _mrz_td2_setzen(seite, x + 6, y + kh * 1.25 - 22, zeilen, nummer, p)
        dok.satz.merkmale.update({"mrz_td2", "ausweis"})
        dok.titel = "Vorläufiger Personalausweis"
        return "personalausweis"
    # Vorderseite
    r = (x, y, x + kb, y + kh)
    _karte(seite, r, rng=rng)
    seite.text(x + 8, y + 13, "BUNDESREPUBLIK DEUTSCHLAND", st.fett, 8)
    seite.text(x + 8, y + 20, k("PERSONALAUSWEIS") + " · IDENTITY CARD · CARTE D'IDENTITÉ", st.normal, 5.6)
    seite.text(x + kb - 8, y + 13, m("ausweis", nummer, "Ausweisnummer oben rechts"), mrz_schrift(), 9,
               ausrichtung="rechts")
    _lichtbild(seite, (x + 8, y + 26, x + 8 + 30 * MM, y + 26 + 38 * MM))
    fx = x + 16 + 30 * MM
    yy = y + 30
    titel = "DR. " if p.titel.startswith("Dr") else ""
    yy = _etikett_wert(seite, fx, yy, "Name / Surname / Nom",
                       (titel + m("namen", nachname_druck, name_bem(p, "Ausweis Name; Versalien"))), dok) + 7
    if p.geburtsname:
        yy = _etikett_wert(seite, fx, yy, "Geburtsname / Name at birth / Nom de naissance",
                           m("namen", _versal(p.geburtsname), "Ausweis Geburtsname; Versalien"), dok) + 7
    yy = _etikett_wert(seite, fx, yy, "Vornamen / Given names / Prénoms",
                       m("namen", vornamen_druck, "Ausweis Vornamen; Versalien"), dok) + 7
    spalte2 = fx + kb * 0.32
    _etikett_wert(seite, fx, yy, "Geburtsdatum / Date of birth",
                  m("geburt", geb_text, "Ausweis Geburtsdatum"), dok)
    _etikett_wert(seite, spalte2, yy, "Staatsangehörigkeit / Nationality",
                  m("sonstiges", "DEUTSCH", "Ausweis Staatsangehörigkeit"), dok)
    yy += 8.5 * 1.15 + 7
    _etikett_wert(seite, fx, yy, "Geburtsort / Place of birth",
                  m("sonstiges", _versal(rng.choice(D.GEBURTSORTE + [p.ort])), "Ausweis Geburtsort"), dok)
    _etikett_wert(seite, spalte2, yy, "Gültig bis / Date of expiry", datum(gueltig), dok)
    can = K.ausweis_can(rng)
    seite.text(x + kb - 8, y + kh - 8, m("ausweis", can, "Zugangsnummer (CAN) unten rechts"), mrz_schrift(), 8.5,
               ausrichtung="rechts")
    seite.unterschrift(x + 10, y + kh - 10, rng, breite=60, hoehe=12)
    # Rückseite
    y2 = y + kh + rng.uniform(8, 18) * MM
    r2 = (x, y2, x + kb, y2 + kh)
    _karte(seite, r2, rng=rng)
    yy = _etikett_wert(seite, x + 8, y2 + 12, "Anschrift / Address / Adresse",
                       m("plzort", _versal(p.plz_ort()), "Ausweis Rückseite Anschrift; Versalien"), dok, groesse=8.5)
    seite.text(x + 8, yy + 10, m("strasse", _versal(p.strasse_hnr()), "Ausweis Rückseite Anschrift; Versalien"),
               st.fett, 8.5)
    rx = x + kb * 0.62
    _etikett_wert(seite, rx, y2 + 12, "Größe / Height", m("sonstiges", f"{rng.randint(152, 198)} cm",
                                                          "Ausweis Körpergröße"), dok)
    _etikett_wert(seite, rx, y2 + 32, "Augenfarbe / Colour of eyes",
                  m("sonstiges", rng.choice(["BLAU", "GRÜN", "BRAUN", "GRAU", "GRAUBLAU", "BRAUNGRÜN"]),
                    "Ausweis Augenfarbe"), dok)
    _etikett_wert(seite, x + 8, yy + 24, "Behörde / Authority / Autorité",
                  m("sonstiges", behoerde, "Ausweis Behörde"), dok)
    _etikett_wert(seite, rx, yy + 24, "Datum / Date", datum(ausstellung), dok)
    zeilen = K.mrz_td1("D", nummer, p.geburtsdatum, "<", gueltig, "D", p.nachname, p.vornamen)
    _mrz_td1_setzen(seite, x + 8, y2 + kh - 34, zeilen, nummer, p)
    if fl is None and rng.random() < 0.5:
        seite.text(25 * MM, y2 + kh + 12 * MM, "Kopie – nur zur Identifizierung", st.normal, 9)
    dok.satz.merkmale.update({"mrz_td1", "ausweis"})
    dok.titel = "Ausweiskopie"
    return "personalausweis"


def _mrz_name_markup(feld: str, p: Person, laenge: int) -> str:
    """Namensfeld der MRZ als Auszeichnung: Nachname und Vornamen getrennte Einträge, Füllzeichen Klartext."""
    feld = feld[:laenge]
    kern = feld.rstrip("<")
    if "<<" in kern:
        nach, vor = kern.split("<<", 1)
    else:
        nach, vor = kern, ""
    aus = m("namen", nach, name_bem(p, "MRZ Namensfeld Nachname"))
    if vor.strip("<"):
        aus += "<<" + m("namen", vor.strip("<"), "MRZ Namensfeld Vornamen")
    return aus + "<" * (laenge - len(kern))


def _mrz_token_markup(zeile: str, felder: list) -> str:
    """Datenzeile der MRZ als Auszeichnung. Die Felder kleben ohne Trenner aneinander ("C01X00T478D" = Nummer,
    Prüfziffer und Staatsangehörigkeit); ein Eintrag umfasst deshalb das GANZE Zeichenstück zwischen zwei
    Füllzeichen, das ein persönliches Feld berührt (felder: [(start, ende, kategorie, bemerkung)])."""
    aus, pos = [], 0
    for teil in zeile.split("<"):
        a, b = pos, pos + len(teil)
        pos = b + 1
        if not teil:
            aus.append("")
            continue
        feld = next((f for f in felder if f[0] < b and a < f[1]), None)
        aus.append(m(feld[2], teil, feld[3]) if feld else teil)
    return "<".join(aus)


def _mrz_td1_setzen(seite, x, y, zeilen: list, nummer: str, p: Person):
    z1, z2, z3 = zeilen
    m1 = _mrz_token_markup(z1, [(5, 15, "ausweis", "MRZ Dokumentnummer mit Prüfziffer")])
    m2 = _mrz_token_markup(z2, [(0, 7, "geburt", "MRZ Geburtsdatum JJMMTT mit Prüfziffer")])
    m3 = _mrz_name_markup(z3, p, 30)
    _mrz_zeilen(seite, x, y, [m1, m2, m3])


def _mrz_td2_setzen(seite, x, y, zeilen: list, nummer: str, p: Person):
    z1, z2 = zeilen
    m1 = z1[:5] + _mrz_name_markup(z1[5:], p, 31)
    m2 = _mrz_token_markup(z2, [(0, 10, "ausweis", "MRZ Dokumentnummer mit Prüfziffer"),
                                (13, 20, "geburt", "MRZ Geburtsdatum JJMMTT mit Prüfziffer")])
    _mrz_zeilen(seite, x, y, [m1, m2], groesse=9.0)


_PASS_LAENDER = [
    # (Staatscode, Staatsname, Staatsangehörigkeit (gedruckt), Herkunft der Person)
    ("D", "BUNDESREPUBLIK DEUTSCHLAND", "DEUTSCH", "de"),
    ("D", "BUNDESREPUBLIK DEUTSCHLAND", "DEUTSCH", "de"),
    ("D", "BUNDESREPUBLIK DEUTSCHLAND", "DEUTSCH", "ru"),
    ("TUR", "REPUBLIC OF TÜRKİYE", "T.C.", "tr"),
    ("POL", "RZECZPOSPOLITA POLSKA", "POLSKIE", "pl"),
    ("ITA", "REPUBBLICA ITALIANA", "ITALIANA", "it"),
    ("ROU", "ROMÂNIA", "ROMÂNĂ", "ro"),
    ("GRC", "HELLENIC REPUBLIC", "ΕΛΛΗΝΙΚΗ HELLENIC", "gr"),
    ("HRV", "REPUBLIKA HRVATSKA", "HRVATSKO", "yu"),
]


def typ_reisepass(dok: Dok) -> str:
    """Kopie der Datenseite eines Reisepasses mit TD3-MRZ (deutsche und ausländische Pässe)."""
    rng = dok.rng
    st = dok.stil
    code, staat, nat_druck, herkunft = rng.choice(_PASS_LAENDER)
    p = dok.person(alter=(18, 80), herkunft=herkunft, titel_quote=0.0)
    dok.hauptperson = p
    seite = dok.satz.neue_seite()
    deutsch = code == "D"
    nummer = K.reisepassnummer(rng) if deutsch else (
        "".join(rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(rng.choice([1, 2])))
        + "".join(rng.choice("0123456789") for _ in range(7)))
    nummer = nummer[:9].ljust(9, "<") if len(nummer) < 9 else nummer[:9]
    ausstellung = dok.heute - datetime.timedelta(days=rng.randint(100, 3200))
    gueltig = ausstellung.replace(year=ausstellung.year + 10) - datetime.timedelta(days=1)
    y = rng.uniform(25, 60) * MM
    if rng.random() < 0.4:
        seite.text(25 * MM, 18 * MM, "Anlage zum Antrag – Kopie Reisepass von " + m("namen", p.voll(),
                                                                                   name_bem(p, "Begleittext")),
                   st.normal, 9.5)
    skala = rng.uniform(1.15, 1.4)
    kb, kh = 125 * MM * skala, 88 * MM * skala
    x = (A4_B - kb) / 2
    _karte(seite, (x, y, x + kb, y + kh), rand=(0.45, 0.3, 0.35), fuellung=(0.97, 0.95, 0.96), rng=rng)
    seite.text(x + 8, y + 14, staat, st.fett, 8.5)
    if deutsch:
        seite.text(x + 8, y + 22, k("REISEPASS") + " · PASSPORT · PASSEPORT", st.normal, 6)
        etiketten = ["Name / Surname / Nom (1)", "Vornamen / Given names / Prénoms (2)",
                     "Staatsangehörigkeit / Nationality (3)", "Geburtstag / Date of birth (4)", "Geschlecht / Sex (5)",
                     "Geburtsort / Place of birth (6)", "Ausstellungsdatum / Date of issue (7)",
                     "Behörde / Authority (8)", "Gültig bis / Date of expiry (9)"]
    else:
        seite.text(x + 8, y + 22, k("PASSPORT") + " · PASSEPORT", st.normal, 6)
        etiketten = ["Surname / Nom", "Given names / Prénoms", "Nationality / Nationalité", "Date of birth",
                     "Sex / Sexe", "Place of birth", "Date of issue", "Authority / Autorité", "Date of expiry"]
    seite.text(x + kb * 0.45, y + 30, "Typ/Type P   Kode/Code " + code, st.normal, 6.5)
    seite.text(x + kb - 8, y + 30, m("ausweis", nummer.rstrip("<"), "Passnummer oben rechts"), mrz_schrift(), 9,
               ausrichtung="rechts")
    _lichtbild(seite, (x + 8, y + 34, x + 8 + 32 * MM, y + 34 + 42 * MM))
    fx = x + 16 + 32 * MM
    geschlecht = "M" if p.geschlecht == "m" else "F"
    monate = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

    def datum_fmt(d):
        return f"{d:%d.%m.%Y}" if deutsch else f"{d.day:02d} {monate[d.month - 1]} {d.year % 100:02d}"
    behoerde = (m("sonstiges", _behoerde(rng, p.ort), "Pass Behörde") if deutsch
                else rng.choice(["MINISTRY OF INTERIOR", "CONSULATE GENERAL FRANKFURT"]))
    werte = [m("namen", _versal(p.nachname), name_bem(p, "Pass Name; Versalien")),
             m("namen", _versal(p.vornamen), "Pass Vornamen; Versalien"),
             m("sonstiges", nat_druck, "Pass Staatsangehörigkeit"),
             m("geburt", datum_fmt(p.geburtsdatum), "Pass Geburtsdatum"), geschlecht,
             m("sonstiges", _versal(rng.choice(D.GEBURTSORTE)), "Pass Geburtsort"), datum_fmt(ausstellung),
             behoerde, datum_fmt(gueltig)]
    # Zeilen: Name | Vornamen | Staatsangehörigkeit | Geburtstag + Geschlecht | Geburtsort | Ausstellung + Behörde |
    # Gültig bis
    anordnung = [(0,), (1,), (2,), (3, 4), (5,), (6, 7), (8,)]
    yy = y + 38
    for gruppe in anordnung:
        for j, i in enumerate(gruppe):
            _etikett_wert(seite, fx + j * kb * 0.3, yy, etiketten[i], werte[i], dok, groesse=8.5)
        yy += 8.5 * 1.15 + 7
    seite.unterschrift(fx, y + kh - 30, rng, breite=70, hoehe=12)
    z1, z2 = K.mrz_td3(code, nummer, p.geburtsdatum, geschlecht, gueltig, code, p.nachname, p.vornamen)
    if len(code) == 3:
        # dreibuchstabiger Staatscode: der Nachname klebt am Code ("P<TURAKGUEL<<…") – ein Zeichenstück
        rest = _mrz_name_markup(z1[5:], p, 39)
        nach_ende = rest.index("⟧") + 1
        stueck = rest[:nach_ende]
        nachname_mrz = stueck.split("|")[1]
        m1 = "P<" + m("namen", code + nachname_mrz, name_bem(p, "MRZ Namensfeld Nachname mit Staatscode verbunden")) \
            + rest[nach_ende:]
    else:
        m1 = z1[:5] + _mrz_name_markup(z1[5:], p, 39)
    m2 = _mrz_token_markup(z2, [(0, 10, "ausweis", "MRZ Passnummer mit Prüfziffer"),
                                (13, 20, "geburt", "MRZ Geburtsdatum JJMMTT mit Prüfziffer")])
    _mrz_zeilen(seite, x + 8, y + kh - 18, [m1, m2], groesse=min(9.0, kb / 44 / 0.6 * 0.97))
    dok.satz.merkmale.update({"mrz_td3", "ausweis"})
    dok.titel = "Reisepass"
    return "reisepass"


def typ_fuehrerschein(dok: Dok) -> str:
    """EU-Kartenführerschein: Werte hinter Feldnummern ohne Feldnamen (1. Name, 2. Vornamen, 3. Geburtsdatum und
    -ort, 4a. Ausstellung, 4b. Ablauf, 4c. Behörde, 4d. Kennziffer, 5. Nummer, 8. Wohnort, 9. Klassen)."""
    rng = dok.rng
    st = dok.stil
    p = _person_ausweis(dok, alter=(18, 85))
    seite = dok.satz.neue_seite()
    land = rng.choice(["D", "D", "D", "A", "PL", "I"])
    staatsname = {"D": "BUNDESREPUBLIK DEUTSCHLAND", "A": "REPUBLIK ÖSTERREICH", "PL": "RZECZPOSPOLITA POLSKA",
                  "I": "REPUBBLICA ITALIANA"}[land]
    nummer = K.fuehrerscheinnummer(rng) if land == "D" else "".join(rng.choice("0123456789") for _ in range(8))
    ausstellung = dok.heute - datetime.timedelta(days=rng.randint(100, 4000))
    ablauf = ausstellung.replace(year=ausstellung.year + 15) - datetime.timedelta(days=1)
    mit_adresse = land != "D" and rng.random() < 0.8 or rng.random() < 0.15
    mit_4d = land != "D" or rng.random() < 0.2
    y = rng.uniform(25, 50) * MM
    if rng.random() < 0.5:
        seite.text(25 * MM, 17 * MM, "Kopie Führerschein (Vorder- und Rückseite)", st.normal, 9.5)
    skala = rng.uniform(1.3, 1.6)
    kb, kh = 85.6 * MM * skala, 54.0 * MM * skala
    x = (A4_B - kb) / 2 + rng.uniform(-12, 12)
    _karte(seite, (x, y, x + kb, y + kh), rand=(0.6, 0.45, 0.5), fuellung=(0.98, 0.93, 0.94), rng=rng)
    seite.text(x + 8, y + 14, k("FÜHRERSCHEIN"), st.fett, 11)
    seite.text(x + 8, y + 22, staatsname, st.normal, 6.5)
    if not seite.satz.messmodus:
        seite.page.draw_circle(fitz.Point(x + kb - 18, y + 16), 10, color=(0.1, 0.2, 0.6), fill=(0.1, 0.2, 0.6))
    seite.text(x + kb - 18, y + 19, land, st.fett, 9, farbe=(1, 1, 1), ausrichtung="mitte")
    _lichtbild(seite, (x + 8, y + 28, x + 8 + 27 * MM, y + 28 + 34 * MM))
    fx = x + 14 + 27 * MM
    g = 8.5
    zh = g * 1.5
    yy = y + 36
    datum_fmt = (lambda d: f"{d:%d.%m.%Y}") if rng.random() < 0.6 else (lambda d: f"{d:%d.%m.%y}")
    ort_geb = _versal(rng.choice(D.GEBURTSORTE + [p.ort.split(" (")[0]]))
    zeilen = [("1.", m("namen", _versal(p.nachname), name_bem(p, "Führerschein Feld 1 ohne Feldnamen; Versalien"))),
              ("2.", m("namen", _versal(p.vornamen), "Führerschein Feld 2 ohne Feldnamen; Versalien")),
              ("3.", m("geburt", datum_fmt(p.geburtsdatum), "Führerschein Feld 3 ohne Feldnamen") + " "
               + m("sonstiges", ort_geb, "Führerschein Feld 3 Geburtsort"))]
    for nr, wert in zeilen:
        seite.text(fx, yy, nr, st.normal, g * 0.8)
        seite.text(fx + 12, yy, wert, st.fett, g)
        yy += zh
    seite.text(fx, yy, "4a.", st.normal, g * 0.8)
    seite.text(fx + 14, yy, k(datum_fmt(ausstellung)), st.fett, g)
    seite.text(fx + kb * 0.3, yy, "4c.", st.normal, g * 0.8)
    if land == "D":
        behoerde = rng.choice(["Landratsamt ", "Stadt ", "Kreis ", "Bürgerbüro "]) + p.ort.split(" (")[0]
    else:
        behoerde = {"A": rng.choice(["BH Innsbruck-Land", "LPD Wien", "BH Bregenz"]),
                    "PL": rng.choice(["Starosta Powiatowy", "Prezydent m. Krakowa"]),
                    "I": "MIT-UCO"}[land]
    seite.text(fx + kb * 0.3 + 14, yy, m("sonstiges", behoerde, "Führerschein Feld 4c Behörde"), st.fett, g * 0.9)
    yy += zh
    seite.text(fx, yy, "4b.", st.normal, g * 0.8)
    seite.text(fx + 14, yy, k(datum_fmt(ablauf)), st.fett, g)
    if mit_4d:
        seite.text(fx + kb * 0.3, yy, "4d.", st.normal, g * 0.8)
        kennziffer = "".join(rng.choice("0123456789") for _ in range(rng.choice([9, 10, 11])))
        seite.text(fx + kb * 0.3 + 14, yy, m("ausweis", kennziffer, "Führerschein Feld 4d persönliche Kennziffer"),
                   st.fett, g)
    yy += zh
    seite.text(fx, yy, "5.", st.normal, g * 0.8)
    seite.text(fx + 12, yy, m("ausweis", nummer, "Führerschein Feld 5 Nummer ohne Feldnamen"), st.fett, g)
    yy += zh
    seite.text(fx, yy + 4, "7.", st.normal, g * 0.8)
    seite.unterschrift(fx + 12, yy + 6, rng, breite=55, hoehe=10)
    yy += zh * 1.2
    if mit_adresse:
        seite.text(fx, yy, "8.", st.normal, g * 0.8)
        seite.text(fx + 12, yy, m("strasse", _versal(p.strasse_hnr()), "Führerschein Feld 8 Anschrift") + ", "
                   + m("plzort", _versal(p.plz_ort()), "Führerschein Feld 8 Anschrift"), st.fett, g * 0.9)
        yy += zh
    klassen = rng.choice(["AM/B/L", "AM/A1/B/BE/L", "B/BE/C1/C1E/L", "AM/A/B/L/T"])
    seite.text(x + 8, y + kh - 8, "9.", st.normal, g * 0.8)
    seite.text(x + 20, y + kh - 8, k(klassen), st.fett, g)
    # Rückseite: Klassentabelle
    y2 = y + kh + rng.uniform(8, 16) * MM
    _karte(seite, (x, y2, x + kb, y2 + kh), rand=(0.6, 0.45, 0.5), fuellung=(0.98, 0.95, 0.96))
    kopf = ["9.", "10.", "11.", "12."]
    sp = [x + 8, x + 8 + kb * 0.22, x + 8 + kb * 0.47, x + 8 + kb * 0.72]
    for xx, t in zip(sp, kopf):
        seite.text(xx, y2 + 12, t, st.fett, 7)
    yy = y2 + 22
    erste = p.geburtsdatum.replace(year=p.geburtsdatum.year + 18) + datetime.timedelta(days=rng.randint(10, 400))
    for kl in klassen.split("/"):
        seite.text(sp[0], yy, kl, st.normal, 7)
        seite.text(sp[1], yy, datum_fmt(min(erste, dok.heute)), st.normal, 7)
        if kl in ("C1", "C1E"):
            seite.text(sp[2], yy, datum_fmt(ablauf), st.normal, 7)
        if rng.random() < 0.2:
            seite.text(sp[3], yy, rng.choice(["79.03", "79.04", "01.06", "96"]), st.normal, 7)
        yy += 9
    seite.text(x + 8, y2 + kh - 10, "13.   14.", st.normal, 6.5)
    dok.satz.merkmale.update({"nummerierte_felder", "ausweis"})
    dok.titel = "Führerschein"
    return "fuehrerschein"


# ----------------------------------------------------------------------
# SEPA-Lastschriftmandat
# ----------------------------------------------------------------------
_SEPA_TEXT = ("Ich ermächtige {g}, Zahlungen von meinem Konto mittels Lastschrift einzuziehen. Zugleich weise ich "
              "mein Kreditinstitut an, die von {g} auf mein Konto gezogenen Lastschriften einzulösen. Hinweis: Ich kann "
              "innerhalb von acht Wochen, beginnend mit dem Belastungsdatum, die Erstattung des belasteten Betrages "
              "verlangen. Es gelten dabei die mit meinem Kreditinstitut vereinbarten Bedingungen.")


def typ_sepa_mandat(dok: Dok) -> str:
    rng = dok.rng
    st = dok.stil
    hs = dok.scan_geplant is not None and rng.random() < 0.75          # von Hand ausgefüllt und eingescannt
    p = dok.person(alter=(20, 85))
    dok.hauptperson = p
    abweichend = rng.random() < 0.3
    vn = dok.familienmitglied(p, "ehe", (20, 85)) if abweichend else p
    makler_glaeubiger = rng.random() < 0.3
    if makler_glaeubiger:
        makler = dok.person(alter=(35, 65), titel_quote=0.0)
        glaeubiger_name = (f"Versicherungsmakler {makler.voll()} e.K.", True)
        glaeubiger_adresse = (makler.strasse_hnr(), makler.plz_ort())
    else:
        v = dok.versicherer()
        glaeubiger_name = (v[0], False)
        glaeubiger_adresse = (v[4], f"{v[2]} {v[3]}")
    gid = K.glaeubiger_id(rng)
    mref = K.mandatsreferenz(rng)
    seite = dok.satz.neue_seite()
    y = 20 * MM
    seite.text(25 * MM, y, k("SEPA-Lastschriftmandat"), st.fett, st.groesse + 5)
    y += 9 * MM
    if makler_glaeubiger:
        name_m = "Versicherungsmakler " + m("namen", makler.voll(), name_bem(makler, "Zahlungsempfänger (Makler)")) \
            + " e.K."
        adr_m = (m("strasse", glaeubiger_adresse[0], "Zahlungsempfänger (Makler)") + ", "
                 + m("plzort", glaeubiger_adresse[1], "Zahlungsempfänger (Makler)"))
    else:
        name_m, adr_m = glaeubiger_name[0], f"{glaeubiger_adresse[0]}, {glaeubiger_adresse[1]}"
    seite.text(25 * MM, y, "Zahlungsempfänger: " + name_m, st.normal, st.groesse)
    y += st.zeilenhoehe
    seite.text(25 * MM, y, adr_m, st.normal, st.groesse)
    y += st.zeilenhoehe * 1.3
    # Gläubiger-ID des Zahlungsempfängers: Firmenkennung ohne Personenbezug (wie im Versicherungsschein unausgezeichnet)
    seite.text(25 * MM, y, rng.choice(["Gläubiger-Identifikationsnummer: ", "Gläubiger-ID: ", "Gläubiger-ID-Nr.: "])
               + gid, st.normal, st.groesse)
    y += st.zeilenhoehe * 1.3
    if rng.random() < 0.8:
        seite.text(25 * MM, y, rng.choice(["Mandatsreferenz: ", "Mandatsreferenz-Nr.: ", "Mandats-Nr.: "])
                   + m("mandat", mref, "SEPA-Mandat mit Etikett"), st.normal, st.groesse)
    else:
        seite.text(25 * MM, y, "Mandatsreferenz: wird separat mitgeteilt", st.normal, st.groesse)
    y += st.zeilenhoehe * 1.3
    vnr = K.vertragsnummer(rng, rng.choice(["LV", "KV", "HR", "KF"]))
    seite.text(25 * MM, y, rng.choice(["Für Vertrag/Versicherungsschein-Nr.: ", "Versicherungsnummer: ",
                                       "betrifft Vertrag "]) + m("vertrag", vnr, "SEPA-Mandat Vertragsnummer"),
               st.normal, st.groesse)
    y += st.zeilenhoehe * 1.8
    fl = Fluss(dok, 25 * MM, A4_B - 20 * MM, 20 * MM, A4_H - 20 * MM, seite=seite, y_start=y)
    fl.absatz(_SEPA_TEXT.format(g="den Zahlungsempfänger" if rng.random() < 0.5 else glaeubiger_name[0]),
              groesse=st.groesse * 0.92)
    y = fl.y + st.zeilenhoehe
    unter = rng.random() < 0.65                    # Feldnamen unter der Linie
    breite = A4_B - 45 * MM
    geb, _ = dok.geburtsdatum_text(p.geburtsdatum, "punkt")
    bank = rng.choice(D.BANKEN)
    bic = K.bic(rng)
    iban_roh = K.iban(rng, "DE")
    iban = K.iban_formatieren(iban_roh, "gruppen" if rng.random() < 0.7 else "kompakt")
    felder = [("Vorname und Name (Kontoinhaber)", m("namen", p.voll(), name_bem(p, "SEPA Kontoinhaber"))),
              ("Straße und Hausnummer", m("strasse", p.strasse_hnr(), "SEPA Kontoinhaber")),
              ("Postleitzahl und Ort", m("plzort", p.plz_ort(), "SEPA Kontoinhaber")),
              ("Kreditinstitut (Name und BIC)", bank + "   " + m("bic", bic, "SEPA BIC neben Bankname"))]
    if abweichend:
        felder.insert(0, ("Versicherungsnehmer (falls abweichend vom Kontoinhaber)",
                          m("namen", vn.voll(), name_bem(vn, "SEPA Versicherungsnehmer abweichend"))))
    iban_kaesten = rng.random() < 0.5
    for etikett, wert in felder:
        y += 9 * MM
        if unter:
            feld_unter_linie(seite, 25 * MM, y, breite, etikett, wert, dok, handschriftlich=hs)
            y += 4 * MM
        else:
            seite.text(25 * MM, y, etikett + ":", st.normal, st.groesse * 0.92)
            _wert(dok, seite, 25 * MM + 62 * MM, y, wert, hs, groesse=st.groesse)
            seite.linie(25 * MM + 60 * MM, y + 2, A4_B - 20 * MM, y + 2, 0.4)
    y += 10 * MM
    seite.text(25 * MM, y, "IBAN", st.fett, st.groesse)
    if iban_kaesten:
        kammfeld(seite, 25 * MM + 14 * MM, y - 5.2 * MM, 22, "iban", iban_roh, "SEPA IBAN in Kästchen",
                 schrift=handschrift() if hs else druckschrift(), groesse=11, rng=rng if hs else None,
                 kasten=4.6 * MM, gruppen=[2, 2, 4, 4, 4, 4, 2], farbe=TINTE if hs else TINTE_SCHWARZ)
    else:
        _wert(dok, seite, 25 * MM + 14 * MM, y, m("iban", iban, "SEPA IBAN"), hs, groesse=st.groesse + 0.5)
    y += 14 * MM
    ort = m("sonstiges", p.ort, "Ort-Datum-Zeile Mandat")
    _wert(dok, seite, 25 * MM, y, ort + ", " + k(datum(dok.heute)), hs, groesse=st.groesse)
    seite.linie(25 * MM, y + 2.5, 25 * MM + 70 * MM, y + 2.5, 0.4)
    seite.unterschrift(115 * MM, y, rng)
    seite.linie(110 * MM, y + 2.5, A4_B - 20 * MM, y + 2.5, 0.4)
    seite.text(25 * MM, y + 9, "Ort, Datum", st.normal, 6.5)
    seite.text(110 * MM, y + 9, "Unterschrift(en) des Zahlungspflichtigen (Kontoinhaber)", st.normal, 6.5)
    if rng.random() < 0.5:
        seite.text(25 * MM, A4_H - 20 * MM, "Bitte senden Sie das Mandat unterschrieben an Ihren Betreuer zurück. "
                   "Geburtsdatum des Kontoinhabers (für Rückfragen): " + m("geburt", geb, "SEPA Geburtsdatum"),
                   st.normal, 7)
    if hs:
        dok.satz.merkmale.add("handschrift")
    dok.satz.merkmale.add("sepa_mandat")
    dok.titel = "SEPA-Lastschriftmandat"
    return "sepa_mandat"


# ----------------------------------------------------------------------
# Excel-Bestandsliste
# ----------------------------------------------------------------------
_EXCEL_SPALTEN = {
    # Schlüssel: (Kopfvarianten, Breite in mm)
    "nr": (["NR", "LFD", "Nr.", "#", "POS"], 8),
    "kdnr": (["KD-NR", "KUNDENNR", "KD_NR", "Kd.-Nr.", "KUNDE_ID"], 17),
    "name": (["NAME", "NACHNAME", "VN_NAME", "VN-NAME", "Name"], 26),
    "vorname": (["VORNAME", "VN_VORNAME", "VORN.", "Vorname"], 22),
    "geb": (["GEBDAT", "GEB.-DAT.", "GEB_DATUM", "GEBURTSDATUM", "Geb.dat."], 18),
    "strasse": (["STRASSE", "STR.", "VN_STRASSE", "ANSCHRIFT", "Straße"], 32),
    "plz": (["PLZ", "VN_PLZ", "Plz"], 11),
    "ort": (["ORT", "WOHNORT", "VN_ORT", "Ort"], 24),
    "tel": (["TELEFON", "TEL", "TEL.", "TEL_PRIVAT", "Telefon"], 24),
    "email": (["EMAIL", "E-MAIL", "MAIL"], 40),
    "vsnr": (["VSNR", "VERTRAGSNR", "VERS.-NR.", "POLICE", "VERTRAG_NR"], 24),
    "sparte": (["SPARTE", "SP.", "PRODUKT"], 16),
    "ges": (["GESELLSCHAFT", "GES.", "VU", "VERSICHERER"], 22),
    "beitrag": (["BEITRAG", "JAHRESBEITRAG", "BEITR. P.A.", "BTR_BRUTTO"], 17),
    "zw": (["ZW", "ZAHLWEISE", "ZW."], 10),
    "beginn": (["BEGINN", "VB", "VERS.BEGINN"], 17),
    "ablauf": (["ABLAUF", "HF", "ABLAUFDATUM"], 17),
    "iban": (["IBAN", "BANKVERB."], 44),
    "kz": (["KENNZ.", "KFZ_KZ", "AMTL.KZ"], 21),
    "beruf": (["BERUF", "TAETIGKEIT"], 28),
    "betreuer": (["BETREUER", "BTR.", "VERMITTLER"], 18),
    "steuernr": (["STEUERNR", "ST.-NR.", "STEUER_NR"], 26),
}


def typ_bestandsliste_excel(dok: Dok) -> str:
    """Excel-Export im Querformat: Feldnamen nur im Spaltenkopf (Versalien, abgekürzt), Werte oft in Versalien."""
    rng = dok.rng
    st = dok.stil
    makler = dok.person(alter=(35, 65), titel_quote=0.0)
    dok.hauptperson = makler
    versal = rng.random() < 0.65
    umschrift = versal and rng.random() < 0.4
    kopf_versal = rng.random() < 0.8
    wahl = ["nr", "name", "vorname", "geb", "strasse", "plz", "ort", "vsnr", "sparte", "ges", "beitrag", "zw",
            "ablauf"]
    for extra, quote in (("kdnr", 0.5), ("tel", 0.5), ("email", 0.25), ("iban", 0.3), ("beginn", 0.4), ("kz", 0.25),
                         ("beruf", 0.15), ("betreuer", 0.3), ("steuernr", 0.12)):
        if rng.random() < quote:
            wahl.append(extra)
    reihenfolge = list(_EXCEL_SPALTEN)
    wahl.sort(key=reihenfolge.index)
    if rng.random() < 0.3:                       # Anschrift in einer Zelle "STRASSE, PLZ ORT" statt drei Spalten
        wahl = [w for w in wahl if w not in ("plz", "ort")]
    groesse = rng.choice([6.5, 7, 7, 7.5, 8])
    breite_verfuegbar = dok.format[0] - 16 * MM

    def kopf(s):
        t = rng.choice(_EXCEL_SPALTEN[s][0])
        return t.upper() if kopf_versal else t
    kopf_je_spalte = {s: kopf(s) for s in wahl}
    datei = f"Bestand_{rng.choice(['Privatkunden', 'PK', 'Gesamt', 'Kfz', 'Leben'])}_{dok.heute:%Y%m%d}.xlsx"
    blatt = rng.choice(["Tabelle1", "Bestand", "Export", "Liste"])
    fl = Fluss(dok, 8 * MM, dok.format[0] - 8 * MM, 16 * MM, dok.format[1] - 12 * MM, folgeseite=lambda s: 16 * MM)
    wiederholen = rng.random() < 0.6

    def kf(seite, nr, gesamt):
        seite.text(8 * MM, 9 * MM, datei, st.normal, 7)
        seite.text(seite.breite / 2, 9 * MM, blatt, st.normal, 7, ausrichtung="mitte")
        seite.text(seite.breite - 8 * MM, seite.hoehe - 6 * MM, f"Seite {nr} von {gesamt}", st.normal, 7,
                   ausrichtung="rechts")
    dok.kopf_fuss.append(kf)

    def w(text):
        return _versal(text, umschrift) if versal else text
    geb_art = rng.choice(["punkt", "punkt", "punkt", "iso", "kurz"])     # ein Datumsformat je Export
    zeilen = []
    for i in range(rng.randint(EXCEL_ZEILEN[0], EXCEL_ZEILEN[1])):
        q = dok.person(alter=(18, 88), titel_quote=0.02, adel_quote=0.03)
        geb, gbem = dok.geburtsdatum_text(q.geburtsdatum, geb_art)
        sparte = rng.choice(["HR", "PHV", "KFZ", "BU", "LV", "WG", "RS", "PKV", "UNF", "RIESTER"])
        zelle = {
            "nr": str(i + 1),
            "kdnr": m("vertrag", K.kundennummer(rng), "Excel-Spalte Kundennummer"),
            "name": m("namen", w(q.nachname), name_bem(q, "Excel-Spalte Name" + ("; Versalien" if versal else ""))),
            "vorname": m("namen", w(q.vornamen), "Excel-Spalte Vorname" + ("; Versalien" if versal else "")),
            "geb": m("geburt", geb, "Excel-Spalte Geburtsdatum; " + gbem),
            "strasse": m("strasse", w(q.strasse_hnr()), "Excel-Spalte Straße" + ("; Versalien" if versal else "")),
            "plz": m("plzort", q.plz, "Excel-Spalte PLZ (Ort eigene Spalte)"),
            "ort": m("plzort", w(q.ort), "Excel-Spalte Ort (PLZ eigene Spalte)"),
            "tel": m("telefon", dok.telefon(q, mobil=rng.random() < 0.3), "Excel-Spalte Telefon"),
            "email": m("email", q.email(rng), "Excel-Spalte E-Mail"),
            "vsnr": m("vertrag", K.vertragsnummer(rng, rng.choice(["LV", "KF", "HR", "BU"])), "Excel-Spalte VSNR"),
            "sparte": k(sparte),
            "ges": k(w(rng.choice(D.ECHTE_VERSICHERER_KURZ))),
            "beitrag": k(_betrag(rng, 30, 2400)),
            "zw": k(rng.choice(["J", "H", "V", "M", "JÄHRL.", "MTL."] if not umschrift else ["J", "H", "V", "M"])),
            "beginn": k(datum(datetime.date(rng.randint(2005, 2024), rng.randint(1, 12), 1))),
            "ablauf": k(datum(datetime.date(rng.randint(2025, 2045), rng.randint(1, 12), 1))),
            "iban": m("iban", K.iban_formatieren(K.iban(rng, "DE"), "kompakt"), "Excel-Spalte IBAN"),
            "kz": m("kfz", K.kennzeichen(rng), "Excel-Spalte Kennzeichen") if sparte == "KFZ" else "",
            "beruf": m("beruf", w(rng.choice(D.BERUFE)), "Excel-Spalte Beruf"),
            "betreuer": m("namen", w(makler.nachname), name_bem(makler, "Excel-Spalte Betreuer")),
            "steuernr": (m("steuernr", K.steuernummer_land(rng)[1], "Excel-Spalte Steuernummer")
                         if rng.random() < 0.3 else ""),
        }
        if "plz" not in wahl and "strasse" in wahl:
            zelle["strasse"] = (m("strasse", w(q.strasse_hnr()), "Excel-Zelle Anschrift") + ", "
                                + m("plzort", w(q.plz_ort()), "Excel-Zelle Anschrift"))
        zeilen.append(zelle)
    # Spaltenbreite wie "optimale Breite" in Excel, die ganze Tabelle auf Seitenbreite skaliert ("an Seite anpassen");
    # bei zu kleiner Schrift fallen Zusatzspalten weg (der Export enthielte sie sonst unlesbar klein)
    polster = 2.0

    def breite(markup: str, schrift: Schrift, g: float) -> float:
        return schrift.breite(schrift.darstellbar(S.ohne_auszeichnung(markup)), g)
    while True:
        breiten = {s: max([breite(kopf_je_spalte[s], st.fett, groesse)]
                          + [breite(z[s], st.normal, groesse) for z in zeilen]) + 2 * polster + 2.5 for s in wahl}
        faktor = breite_verfuegbar / sum(breiten.values())
        if faktor >= 1 or groesse * faktor >= 5.6 or len(wahl) <= 9:
            break
        weg = next((s for s in ("beruf", "email", "steuernr", "betreuer", "kz", "beginn", "tel", "iban", "kdnr",
                                "zw") if s in wahl), None)
        if weg is None:
            break
        wahl.remove(weg)
    if faktor < 1:
        groesse *= faktor
        breiten = {s: b * faktor for s, b in breiten.items()}
    ausr = ["rechts" if s in ("nr", "beitrag") else "links" for s in wahl]
    fl.tabelle(list(zip([kopf_je_spalte[s] for s in wahl], [breiten[s] for s in wahl], ausr)),
               [[z[s] for s in wahl] for z in zeilen], groesse=groesse, gitter=rng.random() < 0.85,
               zebra=rng.random() < 0.3, kopf_wiederholen=wiederholen, zeilenabstand=1.05)
    dok.satz.merkmale.update({"querformat", "excel_export"})
    if versal:
        dok.satz.merkmale.add("versalien")
    if umschrift:
        dok.satz.merkmale.add("umschrift_ae_oe_ue")
    dok.titel = "Bestandsliste Export"
    return "bestandsliste_excel"


# ----------------------------------------------------------------------
# Unfallbericht (zwei Parteien)
# ----------------------------------------------------------------------
def _partei(dok: Dok) -> dict:
    rng = dok.rng
    vn = dok.person(alter=(20, 80))
    fahrer = vn if rng.random() < 0.7 else dok.person(alter=(18, 80))
    return {"vn": vn, "fahrer": fahrer, "kz": K.kennzeichen(rng), "fahrzeug": rng.choice(D.FAHRZEUGE),
            "versicherer": rng.choice(D.ECHTE_VERSICHERER_KURZ), "vnr": K.vertragsnummer(rng, "KH"),
            "fs": K.fuehrerscheinnummer(rng), "tel": dok.telefon(vn, mobil=rng.random() < 0.6)}


def typ_unfallbericht(dok: Dok) -> str:
    rng = dok.rng
    if rng.random() < 0.55:
        return _europaeischer_unfallbericht(dok)
    return _polizei_unfallmitteilung(dok)


def _europaeischer_unfallbericht(dok: Dok) -> str:
    """Europäischer Unfallbericht: Fahrzeug A links, B rechts; Feldnamen klein über/vor dem Wert."""
    rng = dok.rng
    st = dok.stil
    hs = dok.scan_geplant is not None and rng.random() < 0.8
    a, b = _partei(dok), _partei(dok)
    dok.hauptperson = a["vn"]
    seite = dok.satz.neue_seite()
    seite.text(A4_B / 2, 14 * MM, k("Europäischer Unfallbericht"), st.fett, 13, ausrichtung="mitte")
    seite.text(A4_B / 2, 19 * MM, "Kein Schuldanerkenntnis – nur Feststellung der Identität und der Tatsachen",
               st.normal, 6.5, ausrichtung="mitte")
    unfall = dok.heute - datetime.timedelta(days=rng.randint(2, 40))
    y = 27 * MM
    seite.text(15 * MM, y, "1. Datum des Unfalls", st.normal, 6.5)
    _wert(dok, seite, 15 * MM, y + 10, k(datum(unfall)) + f"  {rng.randint(6, 22):02d}:{rng.choice(['10', '25', '40'])}",
          hs, groesse=9)
    seite.text(70 * MM, y, "2. Ort (Land, Ort, Straße)", st.normal, 6.5)
    _wert(dok, seite, 70 * MM, y + 10, "D, " + k(rng.choice(["Kreuzung Ringstraße/Kirchenweg",
                                                             "Parkplatz Einkaufszentrum", "B 8 Höhe Ausfahrt Nord"])),
          hs, groesse=9)
    seite.text(150 * MM, y, "3. Verletzte", st.normal, 6.5)
    _wert(dok, seite, 150 * MM, y + 10, "nein", hs, groesse=9)
    y += 16 * MM
    zeuge = dok.person()
    seite.text(15 * MM, y, "5. Zeugen: Namen, Anschriften, Tel.", st.normal, 6.5)
    _wert(dok, seite, 15 * MM, y + 10, m("namen", zeuge.voll(), name_bem(zeuge, "Unfallbericht Zeuge")) + ", "
          + m("strasse", zeuge.strasse_hnr(), "Unfallbericht Zeuge") + ", "
          + m("plzort", zeuge.plz_ort(), "Unfallbericht Zeuge") + ", "
          + m("telefon", dok.telefon(zeuge, mobil=True), "Unfallbericht Zeuge"), hs, groesse=8.5)
    y += 16 * MM
    spalten = [(12 * MM, "FAHRZEUG A", a, (0.75, 0.85, 1.0)), (A4_B / 2 + 18 * MM, "FAHRZEUG B", b, (1.0, 0.95, 0.7))]
    breite = A4_B / 2 - 30 * MM
    mitte_x = A4_B / 2 - 14 * MM
    seite.text(A4_B / 2, y + 4, "12. Umstände", st.fett, 6.5, ausrichtung="mitte")
    for i, umstand in enumerate(["parkte", "fuhr rückwärts", "fuhr auf", "bog rechts ab", "bog links ab",
                                 "wechselte Fahrstreifen", "beachtete Vorfahrt nicht"]):
        yy = y + 12 + i * 11
        seite.rechteck((mitte_x, yy - 6, mitte_x + 6, yy), farbe=(0.3, 0.3, 0.3))
        seite.rechteck((mitte_x + 22 * MM, yy - 6, mitte_x + 22 * MM + 6, yy), farbe=(0.3, 0.3, 0.3))
        seite.text(mitte_x + 9, yy - 1, umstand, st.normal, 5.2)
    for x, titel, pt, farbe in spalten:
        yy = y
        seite.rechteck((x, yy - 6, x + breite, yy + 4), fuellung=farbe, farbe=None)
        seite.text(x + 2, yy + 1.5, titel, st.fett, 8)
        yy += 12
        vn, fahrer = pt["vn"], pt["fahrer"]
        geb, _ = dok.geburtsdatum_text(fahrer.geburtsdatum, "punkt")
        felder = [("6. Versicherungsnehmer: Name", m("namen", _versal(vn.nachname) if not hs else vn.nachname,
                                                       name_bem(vn, f"Unfallbericht {titel} Name"))),
                  ("Vorname", m("namen", vn.vornamen, f"Unfallbericht {titel} Vorname")),
                  ("Anschrift", m("strasse", vn.strasse_hnr(), f"Unfallbericht {titel}")),
                  ("PLZ, Ort", m("plzort", vn.plz_ort(), f"Unfallbericht {titel}")),
                  ("Tel. oder E-Mail", m("telefon", pt["tel"], f"Unfallbericht {titel}")),
                  ("7. Amtl. Kennzeichen", m("kfz", pt["kz"], f"Unfallbericht {titel}")),
                  ("Marke, Typ", k(pt["fahrzeug"])),
                  ("8. Versicherer", k(pt["versicherer"])),
                  ("Vertragsnummer", m("vertrag", pt["vnr"], f"Unfallbericht {titel} Vertragsnummer")),
                  ("9. Fahrer: Name, Vorname", m("namen", fahrer.liste(), name_bem(fahrer, f"Unfallbericht {titel} Fahrer"))
                   if fahrer is not vn else "wie 6."),
                  ("Geburtsdatum", m("geburt", geb, f"Unfallbericht {titel} Fahrer")),
                  ("Führerschein-Nr.", m("ausweis", pt["fs"], f"Unfallbericht {titel} Führerschein"))]
        for etikett, wert in felder:
            seite.text(x, yy, etikett, st.normal, 5.8, farbe=(0.25, 0.25, 0.3))
            _wert(dok, seite, x + 1, yy + 9, wert, hs, groesse=8.5)
            seite.linie(x, yy + 11, x + breite, yy + 11, 0.3, (0.6, 0.6, 0.6))
            yy += 19
    y = y + 12 + 12 * 19 + 6
    seite.text(15 * MM, y, "14. Bemerkungen", st.normal, 6.5)
    _wert(dok, seite, 15 * MM, y + 10, k("Fahrzeug B fuhr beim Abbiegen auf Fahrzeug A auf."), hs, groesse=8.5)
    y += 18 * MM
    seite.text(15 * MM, y, "15. Unterschrift der Fahrer", st.normal, 6.5)
    seite.unterschrift(18 * MM, y + 14, rng)
    seite.unterschrift(A4_B / 2 + 20 * MM, y + 14, rng)
    seite.text(18 * MM, y + 22, "A", st.fett, 7)
    seite.text(A4_B / 2 + 20 * MM, y + 22, "B", st.fett, 7)
    if hs:
        dok.satz.merkmale.add("handschrift")
    dok.satz.merkmale.update({"zwei_parteien", "unfallbericht_eu"})
    dok.titel = "Unfallbericht"
    return "unfallbericht"


def _polizei_unfallmitteilung(dok: Dok) -> str:
    """Polizeiliche Unfallmitteilung: Feldnamen in der ersten Spalte, Werte der Beteiligten 01/02 daneben."""
    rng = dok.rng
    st = dok.stil
    a, b = _partei(dok), _partei(dok)
    dok.hauptperson = a["vn"]
    seite = dok.satz.neue_seite()
    dienst = rng.choice(D.POLIZEI)
    seite.text(20 * MM, 18 * MM, k(dienst), st.fett, 11)
    seite.text(20 * MM, 24 * MM, "Verkehrsunfallaufnahme – Mitteilung für Unfallbeteiligte", st.normal, 9)
    fl = Fluss(dok, 20 * MM, A4_B - 18 * MM, 20 * MM, A4_H - 20 * MM, seite=seite, y_start=34 * MM)
    unfall = dok.heute - datetime.timedelta(days=rng.randint(2, 40))
    fl.kv(rng.choice(["Tagebuch-Nr.:", "Vorgangsnummer:", "Aktenzeichen:"]),
          m("vertrag", K.aktenzeichen(rng), "Polizei Vorgangsnummer"), tab=40 * MM)
    fl.kv("Unfallzeit:", k(datum(unfall)) + f", {rng.randint(6, 22):02d}:{rng.choice(['05', '20', '45'])} Uhr",
          tab=40 * MM)
    fl.kv("Unfallort:", k(rng.choice(["Nürnberger Straße / Am Anger", "BAB 9, km 381,2", "Parkhaus Altstadt"])),
          tab=40 * MM)
    fl.luecke(st.zeilenhoehe)
    titel = rng.choice([("Beteiligte/r 01", "Beteiligte/r 02"), ("Beteiligter 1", "Beteiligter 2"),
                        ("Unfallbeteiligter A", "Unfallbeteiligter B")])
    zeilen = []
    for etikett, schl in (("Name, Vorname", "name"), ("Geburtsdatum", "geb"), ("Anschrift", "adr"),
                          ("Telefon", "tel"), ("Amtl. Kennzeichen", "kz"), ("Fahrzeug", "fz"),
                          ("Haftpflichtversicherer", "vers"), ("Versicherungsschein-Nr.", "vnr"),
                          ("Führerschein-Nr.", "fs"), ("Halter", "halter")):
        zeile = [etikett]
        for pt, seite_name in ((a, titel[0]), (b, titel[1])):
            f = pt["fahrer"]
            if schl == "name":
                zeile.append(m("namen", f.liste(), name_bem(f, f"Polizeimitteilung {seite_name}")))
            elif schl == "geb":
                zeile.append(m("geburt", f"{f.geburtsdatum:%d.%m.%Y}", f"Polizeimitteilung {seite_name}"))
            elif schl == "adr":
                zeile.append(m("strasse", f.strasse_hnr(), f"Polizeimitteilung {seite_name}") + ", "
                             + m("plzort", f.plz_ort(), f"Polizeimitteilung {seite_name}"))
            elif schl == "tel":
                zeile.append(m("telefon", dok.telefon(f, mobil=True), f"Polizeimitteilung {seite_name}"))
            elif schl == "kz":
                zeile.append(m("kfz", pt["kz"], f"Polizeimitteilung {seite_name}"))
            elif schl == "fz":
                zeile.append(k(pt["fahrzeug"]))
            elif schl == "vers":
                zeile.append(k(pt["versicherer"]))
            elif schl == "vnr":
                zeile.append(m("vertrag", pt["vnr"], f"Polizeimitteilung {seite_name}"))
            elif schl == "fs":
                zeile.append(m("ausweis", pt["fs"], f"Polizeimitteilung {seite_name}"))
            else:
                h = pt["vn"]
                zeile.append(m("namen", h.voll(), name_bem(h, f"Polizeimitteilung {seite_name} Halter"))
                             if h is not f else "wie Fahrer")
        zeilen.append(zeile)
    fl.tabelle([("", 42 * MM, "links"), (titel[0], 62 * MM, "links"), (titel[1], 62 * MM, "links")], zeilen,
               groesse=max(7.5, st.groesse - 1), gitter=rng.random() < 0.8)
    fl.absatz("Die Angaben dienen der Regulierung durch die Haftpflichtversicherer. Ein Schuldanerkenntnis ist "
              "damit nicht verbunden. Sachbearbeitung: " + m("namen", f"POK {dok.person(titel_quote=0).nachname}",
                                                               "Polizeibeamter mit Dienstgrad"), groesse=st.groesse * 0.9)
    _seitenzahl_registrieren(dok)
    dok.satz.merkmale.update({"zwei_parteien", "unfallmitteilung_polizei", "tabelle"})
    dok.titel = "Unfallmitteilung"
    return "unfallbericht"


# ----------------------------------------------------------------------
# Fax
# ----------------------------------------------------------------------
def typ_fax(dok: Dok) -> str:
    """Faxausdruck: Deckblatt oder Schreiben; Kopfzeile des Empfangsgeräts (Datum, Absenderkennung, Faxnummer,
    Seite x/y) auf jeder Seite. Gescannt wird mit der Fax-Variante (1 Bit)."""
    rng = dok.rng
    st = dok.stil
    kopf_rng = random.Random(f"faxkopf/{dok.satz.kennung}")    # eigener Strom (Generator 1.3)
    art = rng.choice(["kunde", "kunde", "praxis", "versicherer"])
    if art == "praxis":
        arzt = dok.person(titel_quote=0.0, alter=(35, 65))
        arzt.titel = "Dr. med."
        kennung_markup = m("namen", f"PRAXIS DR. {_versal(arzt.nachname)}", name_bem(arzt, "Fax-Kopfzeile Absender"))
        absender_tel = "0" + arzt.vorwahl + " " + "".join(rng.choice("0123456789") for _ in range(6))
    elif art == "versicherer":
        kennung_markup = rng.choice(["SCHADENSERVICE", "KUNDENSERVICE", "VERTRAGSSERVICE", "LEISTUNGSABTEILUNG"])
        if kopf_rng.random() < 0.6:
            kennung_markup = k(kopf_rng.choice(FAX_MARKEN))            # Markenname des Versicherers: bleibt
        absender_tel = "0" + rng.choice(["69", "221", "89", "40"]) + " " + "".join(rng.choice("0123456789")
                                                                                   for _ in range(7))
    else:
        absender = dok.person(alter=(30, 85), titel_quote=0.0)
        kennung_markup = m("namen", rng.choice([_versal(f"{absender.nachname} {absender.vorname1}"),
                                                _versal(absender.voll()), absender.voll()]),
                           name_bem(absender, "Fax-Kopfzeile Absender"))
        absender_tel = dok.telefon(absender, art=rng.choice(["din", "plus49", "strich", "schraeg"]))
    fax_m = (m("telefon", absender_tel, "Fax-Kopfzeile Faxnummer") if art != "versicherer" else absender_tel)
    zeit = dok.heute.strftime(rng.choice(["%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"])) + f" {rng.randint(7, 20):02d}:" \
        f"{rng.randint(0, 59):02d}"
    form = rng.randint(0, 2)
    kopf_schrift = mrz_schrift() if rng.random() < 0.5 else st.normal
    if kopf_rng.random() < 0.6:
        form = kopf_rng.choice([3, 4, 5, 6, 7])                       # Kopfzeilen realer Geräte
    sekunden = kopf_rng.randint(0, 59)
    stunde, minute = int(zeit[-5:-3]), int(zeit[-2:])
    ampm = f"{(stunde - 1) % 12 + 1:02d}:{minute:02d}{'PM' if stunde >= 12 else 'AM'}"
    monate_en = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    datum_en = f"{monate_en[dok.heute.month - 1]}-{dok.heute.day:02d}-{dok.heute.year}"

    def kopf(seite, nr, gesamt):
        if form == 0:
            text = f"{zeit}   {kennung_markup}   FAX {fax_m}   S. {nr:02d}/{gesamt:02d}"
        elif form == 1:
            text = f"Von: {kennung_markup}  Fax: {fax_m}   An: Maklerbüro   {zeit}   Seite {nr} von {gesamt}"
        elif form == 2:
            text = f"{fax_m}   {kennung_markup}   {zeit}   P.{nr:03d}"
        elif form == 3:
            text = f"{zeit}   {kennung_markup}   {fax_m}   S. {nr}/{gesamt}"
        elif form == 4:
            text = f"{dok.heute:%d/%m/%Y} {zeit[-5:]}  FROM: {kennung_markup}  {fax_m}  PAGE {nr:02d}/{gesamt:02d}"
        elif form == 5:
            text = f"{datum_en} {ampm}   {kennung_markup}   {fax_m}   P. {nr}/{gesamt}"
        elif form == 6:
            text = f"{zeit}:{sekunden:02d}   {kennung_markup}   Fax {fax_m}   Seite {nr}/{gesamt}"
        else:
            text = f"{zeit}   {kennung_markup}   {fax_m}   Page {nr} of {gesamt}"
        seite.text(8 * MM, 6 * MM, text, kopf_schrift, 7.5, zusatz="Fax-Kopfzeile")
    dok.kopf_fuss.append(kopf)
    if art == "kunde":
        dok.hauptperson = absender
        seite = dok.satz.neue_seite()
        fl = Fluss(dok, 25 * MM, A4_B - 20 * MM, 20 * MM, A4_H - 20 * MM, seite=seite, y_start=22 * MM)
        fl.ueberschrift(k("TELEFAX"), groesse=st.groesse + 8)
        fl.kv("An:", k("Versicherungsmakler – Kundenservice"), tab=35 * MM)
        fl.kv("Von:", m("namen", absender.voll(), name_bem(absender, "Fax-Deckblatt")), tab=35 * MM)
        fl.kv("Fax-Nr.:", m("telefon", absender_tel, "Fax-Deckblatt"), tab=35 * MM)
        fl.kv("Telefon:", m("telefon", dok.telefon(absender, mobil=True), "Fax-Deckblatt Rückruf"), tab=35 * MM)
        fl.kv("Datum:", k(datum(dok.heute)), tab=35 * MM)
        fl.kv("Seiten:", "2 (inkl. Deckblatt)", tab=35 * MM)
        vnr = K.vertragsnummer(rng, rng.choice(["HR", "KF", "LV"]))
        fl.kv("Betreff:", "Vertrag " + m("vertrag", vnr, "Fax-Deckblatt Betreff"), tab=35 * MM)
        fl.luecke(st.zeilenhoehe)
        fl.absatz("Sehr geehrte Damen und Herren, anbei wie telefonisch besprochen die unterschriebene Erklärung. "
                  "Bitte rufen Sie mich zurück, wenn noch etwas fehlt.")
        fl.absatz("Mit freundlichen Grüßen")
        fl.luecke(st.zeilenhoehe)
        fl.seite.unterschrift(fl.x0, fl.y, rng)
        fl.luecke(st.zeilenhoehe)
        fl.zeile(m("namen", absender.voll(), name_bem(absender, "Fax Unterschrift")))
        _fax_erklaerung(dok, absender, vnr)
    else:
        unter = Dok(dok.rng, dok.satz.kennung, stil=dok.stil)
        unter.satz = dok.satz
        unter._vornamen, unter._nachnamen, unter._orte = dok._vornamen, dok._nachnamen, dok._orte
        unter.heute = dok.heute
        if art == "praxis":
            _praxis_bescheinigung(unter, arzt)
        else:
            rng.choice([typ_brief, typ_mahnung])(unter)
        dok.kopf_fuss.extend(unter.kopf_fuss)
        dok.hauptperson = unter.hauptperson
    dok.satz.merkmale.add("fax_kopfzeile")
    dok.titel = "Telefax"
    return "fax"


def _fax_erklaerung(dok: Dok, p: Person, vnr: str):
    """Zweite Faxseite: die angekündigte Erklärung des Kunden (Bankverbindung, Steuernummer, Unterschrift)."""
    rng = dok.rng
    st = dok.stil
    seite = dok.satz.neue_seite()
    fl = Fluss(dok, 25 * MM, A4_B - 20 * MM, 20 * MM, A4_H - 20 * MM, seite=seite, y_start=24 * MM)
    for z in (m("namen", p.voll(), name_bem(p, "Fax Erklärung Absender")),
              m("strasse", p.strasse_hnr(), "Fax Erklärung Absender"), m("plzort", p.plz_ort(), "Fax Erklärung Absender")):
        fl.zeile(z)
    fl.luecke(st.zeilenhoehe * 2)
    fl.absatz(k("Erklärung zur Änderung der Vertragsdaten") + " – Vertrag " + m("vertrag", vnr, "Fax Erklärung"),
              schrift=st.fett)
    fl.absatz("Ab sofort sollen die Beiträge von meinem neuen Konto abgebucht werden: IBAN "
              + m("iban", dok.iban_text(), "Fax Erklärung") + ", Kontoinhaber " + m("namen", p.liste(),
                                                                                    name_bem(p, "Fax Erklärung")) + ".")
    if rng.random() < 0.6:
        _, stnr = K.steuernummer_land(rng, art=rng.choice(["land", "land", "elster", "elster_schraeg"]))
        mit_fa = rng.random() < 0.6
        fl.absatz("Der Vertrag läuft künftig über mein Gewerbe. "
                  + ("Steuernummer beim Finanzamt " + k(rng.choice(["Nürnberg-Süd", "Fürth", "Erlangen", "München",
                                                                    "Köln-Mitte", "Leipzig II"])) + ": "
                     if mit_fa else rng.choice(["Steuernummer: ", "St.-Nr. ", "Meine Steuernummer lautet "]))
                  + m("steuernr", stnr, "Fax Erklärung Steuernummer" + (" mit Finanzamt" if mit_fa else "")) + ".")
    fl.luecke(st.zeilenhoehe * 2)
    fl.zeile(m("sonstiges", p.ort, "Ort-Datum-Zeile Fax") + ", " + k(datum(dok.heute)))
    fl.seite.unterschrift(fl.x0 + 70 * MM, fl.y - 4, rng)
    fl.zeile("Unterschrift")


def _praxis_bescheinigung(dok: Dok, arzt: Person):
    """Ärztliche Bescheinigung (per Fax an den Makler weitergeleitet)."""
    rng = dok.rng
    st = dok.stil
    patient = dok.person(alter=(20, 70))
    dok.hauptperson = patient
    seite = dok.satz.neue_seite()
    fl = Fluss(dok, 25 * MM, A4_B - 20 * MM, 20 * MM, A4_H - 20 * MM, seite=seite, y_start=24 * MM)
    fl.zeile("Praxis " + m("namen", arzt.voll(titel=True), name_bem(arzt, "Praxiskopf")), schrift=st.fett)
    fl.zeile(rng.choice(D.FACHRICHTUNGEN) + " · " + m("strasse", f"{rng.choice(D.STRASSEN)} {rng.randint(1, 50)}",
                                                      "Praxisanschrift") + " · "
             + m("plzort", arzt.plz_ort(), "Praxisanschrift"), groesse=st.groesse * 0.85)
    fl.luecke(st.zeilenhoehe * 2)
    fl.ueberschrift(k("Ärztliche Bescheinigung"))
    geb, gbem = dok.geburtsdatum_text(patient.geburtsdatum)
    fl.absatz("Hiermit wird bescheinigt, dass " + m("namen", f"{patient.herr_frau} {patient.voll()}",
                                                    name_bem(patient, "Bescheinigung Patient"))
              + ", geb. " + m("geburt", geb, gbem) + ", wohnhaft " + m("strasse", patient.strasse_hnr(), "Bescheinigung")
              + ", " + m("plzort", patient.plz_ort(), "Bescheinigung") + ", seit dem "
              + k(datum(dok.heute - datetime.timedelta(days=rng.randint(10, 60)))) + " in unserer Behandlung ist.")
    fl.absatz("Diagnose: " + m("diagnose", rng.choice(D.DIAGNOSEN), "Bescheinigung Diagnose") + ". Die Patientin bzw. "
              "der Patient ist voraussichtlich bis " + k(datum(dok.heute + datetime.timedelta(days=21)))
              + " arbeitsunfähig.")
    fl.absatz("Versichertennummer: " + m("kvnr", K.kvnr(rng), "Bescheinigung KVNR"))
    fl.luecke(st.zeilenhoehe * 2)
    fl.zeile(m("sonstiges", arzt.ort, "Ort-Datum-Zeile Praxis") + ", " + k(datum(dok.heute)))
    fl.seite.unterschrift(fl.x0 + 60 * MM, fl.y - 2, rng)
    fl.zeile(m("namen", arzt.voll(titel=True), name_bem(arzt, "Unterschrift Arzt")))
    dok.titel = "Ärztliche Bescheinigung"


# ----------------------------------------------------------------------
# Schreibmaschine / EDV-Ausdruck
# ----------------------------------------------------------------------
def typ_schreibmaschine(dok: Dok) -> str:
    rng = dok.rng
    r = rng.random()
    if r < 0.4:
        return _schreibmaschinenbrief(dok)
    if r < 0.7:
        return _edv_ausdruck(dok)
    return _schreibmaschinenformular(dok)


def _mono_zeile(seite, x: float, y: float, markup: str, dok: Dok, groesse=None) -> None:
    st = dok.stil
    seite.text(x, y, markup, st.normal, groesse or st.groesse)


def _auffuellen(teil: str, breite: int) -> str:
    """Klartext auf eine feste Spaltenbreite mit Leerzeichen (Schreibmaschine/Großrechner)."""
    return teil + " " * max(1, breite - len(teil))


def _schreibmaschinenbrief(dok: Dok) -> str:
    """Getippter Kundenbrief: Absender oben links, Datum mit Leerzeichen eingerückt, Unterstreichungen."""
    rng = dok.rng
    st = dok.stil
    p = dok.person(alter=(55, 92), titel_quote=0.05)
    dok.hauptperson = p
    seite = dok.satz.neue_seite()
    g = st.groesse
    zh = g * 1.25
    x = 22 * MM
    y = 22 * MM
    for z in (m("namen", p.voll(titel=True), name_bem(p, "Schreibmaschine Absender")),
              m("strasse", p.strasse_hnr(), "Schreibmaschine Absender"),
              m("plzort", p.plz_ort(), "Schreibmaschine Absender")):
        _mono_zeile(seite, x, y, z, dok)
        y += zh
    if rng.random() < 0.6:
        _mono_zeile(seite, x, y, "Tel. " + m("telefon", dok.telefon(p, art=rng.choice(["alt_paare", "schraeg",
                                                                                         "klammer"])),
                                              "Schreibmaschine Absender"), dok)
        y += zh
    y += zh * 2
    v = dok.versicherer()
    for z in (v[0], "Abteilung Vertragsservice", v[4], f"{v[2]} {v[3]}"):
        _mono_zeile(seite, x, y, z, dok)
        y += zh
    y += zh
    ort_datum = m("sonstiges", p.ort, "Ort-Datum-Zeile Schreibmaschine") + ", den " + k(datum(dok.heute))
    _mono_zeile(seite, x, y, " " * rng.randint(30, 40) + ort_datum, dok)
    y += zh * 2.5
    vnr = K.vertragsnummer(rng, rng.choice(["HR", "LV", "KF"]))
    betreff = rng.choice(["Betr.: ", "Betrifft: ", "BETR.: "])
    _mono_zeile(seite, x, y, betreff + "Versicherungsschein-Nr. " + m("vertrag", vnr, "Schreibmaschine Betreff"), dok)
    seite.linie(x, y + 2, x + st.normal.breite(betreff + "Versicherungsschein-Nr. " + vnr, g), y + 2, 0.5)
    y += zh * 2
    fl = Fluss(dok, x, A4_B - 25 * MM, 20 * MM, A4_H - 20 * MM, seite=seite, y_start=y)
    fl.absatz("Sehr geehrte Damen und Herren,", trennung=False)
    anlass = rng.choice(["kuendigung", "umzug", "schaden"])
    if anlass == "kuendigung":
        fl.absatz("hiermit kuendige ich meine Hausratversicherung zum naechstmoeglichen Termin, da ich in ein Heim "
                  "ziehe. Meine Tochter " + m("namen", dok.familienmitglied(p, "kind", (30, 60)).voll(),
                                              "Schreibmaschine Fließtext Tochter") + " kuemmert sich um alles Weitere.",
                  trennung=False)
    elif anlass == "umzug":
        neu = dok.person()
        fl.absatz("ab dem " + k(datum(dok.heute + datetime.timedelta(days=20))) + " wohne ich in der "
                  + m("strasse", neu.strasse_hnr(), "Schreibmaschine neue Anschrift") + " in "
                  + m("plzort", neu.plz_ort(), "Schreibmaschine neue Anschrift") + ". Bitte aendern Sie meine Anschrift.",
                  trennung=False)
    else:
        fl.absatz("am " + k(datum(dok.heute - datetime.timedelta(days=6))) + " ist bei mir ein Wasserrohr geplatzt. Der "
                  "Handwerker, Herr " + m("namen", dok.person(geschlecht="m").nachname, "Schreibmaschine Handwerker")
                  + ", hat den Schaden aufgenommen. Bitte ueberweisen Sie die Kosten auf mein Konto "
                  + m("iban", dok.iban_text(), "Schreibmaschine Fließtext") + ".", trennung=False)
    fl.absatz("Fuer Rueckfragen bin ich vormittags zu erreichen.", trennung=False)
    fl.luecke(zh)
    fl.absatz("Hochachtungsvoll", trennung=False)
    fl.luecke(zh * 2)
    fl.seite.unterschrift(fl.x0, fl.y - 4, rng)
    fl.zeile("(" + m("namen", p.voll(), name_bem(p, "Schreibmaschine Unterschrift")) + ")")
    dok.satz.merkmale.update({"schreibmaschine", "monospace"})
    dok.titel = "Schreiben"
    return "schreibmaschine"


def _edv_ausdruck(dok: Dok) -> str:
    """Großrechner-Ausdruck eines Versicherers: Versalien, Umschrift, feste Spalten mit Leerzeichen."""
    rng = dok.rng
    st = dok.stil
    v = dok.versicherer()
    p = dok.person(alter=(25, 85))
    dok.hauptperson = p
    seite = dok.satz.neue_seite()
    g = min(st.groesse, 9.5)
    zh = g * 1.3
    x = 15 * MM
    y = 18 * MM
    u = lambda t: _versal(t, umschrift=True)  # noqa: E731
    _mono_zeile(seite, x, y, u(v[0]) + "   " + f"BLATT 1   DRUCK {dok.heute:%d.%m.%y}", dok, g)
    y += zh * 2
    _mono_zeile(seite, x, y, k(rng.choice(["VERSICHERUNGSBESTAETIGUNG", "BEITRAGSRECHNUNG", "VERTRAGSAUSZUG"])), dok, g)
    y += zh * 2
    vnr = K.vertragsnummer(rng, rng.choice(["LV", "KV", "HR"]))
    knr = K.kundennummer(rng)
    geb = f"{p.geburtsdatum:%d.%m.%Y}"
    zeilen = [
        _auffuellen("VERS.-NR.", 22) + m("vertrag", vnr, "EDV-Ausdruck") + "     " + "KD.-NR. "
        + m("vertrag", knr, "EDV-Ausdruck"),
        _auffuellen("VERSICHERUNGSNEHMER", 22) + m("namen", u(p.liste()), name_bem(p, "EDV-Ausdruck; Versalien")),
        _auffuellen("ANSCHRIFT", 22) + m("strasse", u(p.strasse_hnr()), "EDV-Ausdruck; Versalien") + ", "
        + m("plzort", u(p.plz_ort()), "EDV-Ausdruck; Versalien"),
        _auffuellen("GEB.-DATUM", 22) + m("geburt", geb, "EDV-Ausdruck"),
    ]
    if rng.random() < 0.6:
        ehe = dok.familienmitglied(p, "ehe", (25, 85))
        zeilen.append(_auffuellen("MITVERS. PERSON", 22) + m("namen", u(ehe.liste()), name_bem(ehe, "EDV-Ausdruck"))
                      + "  GEB. " + m("geburt", f"{ehe.geburtsdatum:%d.%m.%Y}", "EDV-Ausdruck"))
    zeilen.append(_auffuellen("BANKVERBINDUNG", 22) + "IBAN " + m("iban", K.iban_formatieren(K.iban(rng, "DE"),
                                                                                          "kompakt"),
                                                                 "EDV-Ausdruck"))
    if rng.random() < 0.4:
        _, stnr = K.steuernummer_land(rng, art=rng.choice(["land", "elster"]))
        zeilen.append(_auffuellen("STEUERNR. (GEWERBE)", 22) + m("steuernr", stnr, "EDV-Ausdruck Steuernummer"))
    for z in zeilen:
        _mono_zeile(seite, x, y, z, dok, g)
        y += zh
    y += zh
    _mono_zeile(seite, x, y, "-" * 72, dok, g)
    y += zh
    _mono_zeile(seite, x, y, "TARIF            BEGINN      ABLAUF      BEITRAG EUR   ZW", dok, g)
    y += zh
    for _ in range(rng.randint(2, 5)):
        tarif = u(rng.choice(D.PRODUKTE[rng.choice(["leben", "sach", "kranken"])]))[:16]
        beginn = datetime.date(rng.randint(2005, 2024), rng.randint(1, 12), 1)
        ablauf = beginn.replace(year=beginn.year + rng.choice([1, 10, 20, 30]))
        _mono_zeile(seite, x, y, k(_auffuellen(tarif, 17)) + _auffuellen(datum(beginn), 12)
                    + _auffuellen(datum(ablauf), 12) + _auffuellen(_betrag(rng, 20, 900), 14)
                    + rng.choice(["J", "H", "M"]), dok, g)
        y += zh
    y += zh
    _mono_zeile(seite, x, y, "BEARBEITER: " + m("namen", u(dok.person(titel_quote=0).nachname), "EDV-Ausdruck Bearbeiter")
                + "   TEL. " + m("telefon", dok.telefon(None, art="din_durchwahl"), "EDV-Ausdruck Durchwahl"), dok, g)
    dok.satz.merkmale.update({"edv_ausdruck", "monospace", "versalien"})
    dok.titel = "EDV-Ausdruck"
    return "schreibmaschine"


def _schreibmaschinenformular(dok: Dok) -> str:
    """Vorgedrucktes Formular (Schadenanzeige), mit der Schreibmaschine auf Punktlinien ausgefüllt."""
    rng = dok.rng
    st = dok.stil
    p = dok.person(alter=(25, 85))
    dok.hauptperson = p
    seite = dok.satz.neue_seite()
    g = st.groesse
    x = 20 * MM
    y = 20 * MM
    _mono_zeile(seite, x, y, k("SCHADENANZEIGE") + " (Haftpflicht/Hausrat)", dok, g + 2)
    y += g * 3
    geb = f"{p.geburtsdatum:%d.%m.%Y}"
    felder = [("Versicherungsschein-Nr.", m("vertrag", K.vertragsnummer(rng, "HR"), "Schreibmaschinenformular")),
              ("Versicherungsnehmer", m("namen", p.voll(), name_bem(p, "Schreibmaschinenformular"))),
              ("Geburtsdatum", m("geburt", geb, "Schreibmaschinenformular")),
              ("Strasse, Hausnr.", m("strasse", p.strasse_hnr(), "Schreibmaschinenformular")),
              ("PLZ, Wohnort", m("plzort", p.plz_ort(), "Schreibmaschinenformular")),
              ("Telefon", m("telefon", dok.telefon(p), "Schreibmaschinenformular")),
              ("Schadentag", k(datum(dok.heute - datetime.timedelta(days=rng.randint(3, 30))))),
              ("Geschaedigter", m("namen", dok.person().voll(), "Schreibmaschinenformular Geschädigter")),
              ("Bankverbindung (IBAN)", m("iban", dok.iban_text(), "Schreibmaschinenformular"))]
    breite = rng.choice([24, 26, 28])
    for etikett, wert in felder:
        punkte = "." * max(2, breite - len(etikett))
        _mono_zeile(seite, x, y, etikett + " " + punkte + " " + wert, dok, g)
        y += g * 2.0
    y += g
    fl = Fluss(dok, x, A4_B - 20 * MM, 20 * MM, A4_H - 20 * MM, seite=seite, y_start=y)
    fl.absatz("Schadenhergang: Beim Abstellen des Einkaufswagens wurde das Fahrzeug des Geschaedigten am hinteren "
              "Kotfluegel beschaedigt. Zeuge war " + m("namen", dok.person().voll(), "Schreibmaschinenformular Zeuge")
              + ".", trennung=False)
    fl.luecke(g * 2)
    fl.zeile(m("sonstiges", p.ort, "Ort-Datum-Zeile Schreibmaschinenformular") + ", " + k(datum(dok.heute)))
    fl.seite.unterschrift(fl.x0 + 70 * MM, fl.y - 4, rng)
    dok.satz.merkmale.update({"schreibmaschine", "monospace", "formular_papier"})
    dok.titel = "Schadenanzeige"
    return "schreibmaschine"


# ----------------------------------------------------------------------
# Handschrift und Blockschrift in Formularen
# ----------------------------------------------------------------------
_FORMULARE = ["Änderungsmitteilung", "Kundenstammblatt", "Schadenanzeige Hausrat", "Antrag auf Beitragsfreistellung",
              "Selbstauskunft"]


def typ_handschrift_formular(dok: Dok) -> str:
    """Vorgedrucktes Formular, handschriftlich (Schreibschrift) ausgefüllt."""
    rng = dok.rng
    st = dok.stil
    p = dok.person(alter=(20, 85))
    dok.hauptperson = p
    v = dok.versicherer()
    seite = dok.satz.neue_seite()
    seite.text(20 * MM, 18 * MM, k(v[0]), st.kopf_familie.fett, 11, farbe=st.akzent)
    titel = rng.choice(_FORMULARE)
    seite.text(20 * MM, 27 * MM, k(titel), st.fett, 13)
    zittern = dok.scan_geplant is not None
    y = 40 * MM
    geb, gbem = dok.geburtsdatum_text(p.geburtsdatum, rng.choice(["punkt", "punkt_ohne_null", "kurz"]))
    felder = [("Versicherungsnummer", m("vertrag", K.vertragsnummer(rng, rng.choice(["LV", "HR", "KV"])),
                                        "Handschrift Formular")),
              ("Name, Vorname", m("namen", p.liste(), name_bem(p, "Handschrift Formular"))),
              ("Geburtsdatum", m("geburt", geb, "Handschrift Formular; " + gbem)),
              ("Straße, Hausnummer", m("strasse", p.strasse_hnr(), "Handschrift Formular")),
              ("PLZ, Ort", m("plzort", p.plz_ort(), "Handschrift Formular")),
              ("Telefon (tagsüber)", m("telefon", dok.telefon(p, mobil=rng.random() < 0.5), "Handschrift Formular")),
              ("E-Mail", m("email", p.email(rng), "Handschrift Formular"))]
    if rng.random() < 0.5:
        felder.append(("Neue Bankverbindung (IBAN)", m("iban", dok.iban_text(), "Handschrift Formular")))
    if rng.random() < 0.4:
        felder.append(("Beruf / Tätigkeit", m("beruf", rng.choice(D.BERUFE), "Handschrift Formular")))
    if rng.random() < 0.3:
        _, stnr = K.steuernummer_land(rng)
        felder.append(("Steuernummer (bei Selbstständigen)", m("steuernr", stnr, "Handschrift Formular")))
    if rng.random() < 0.5:
        kind = dok.familienmitglied(p, "kind", (2, 17))
        felder.append(("Mitversicherte Person", m("namen", kind.voll(), name_bem(kind, "Handschrift Formular Kind"))))
    links = rng.random() < 0.6
    for etikett, wert in felder:
        if links:
            ende = seite.text(20 * MM, y, etikett + ":", st.normal, 8.5)
            x_wert = max(72 * MM, ende + 4 * MM)
            seite.linie(x_wert - 2 * MM, y + 2, A4_B - 20 * MM, y + 2, 0.4, (0.5, 0.5, 0.5))
            hand(seite, x_wert, y, wert, rng, groesse=rng.uniform(11, 13), zittern=zittern)
            y += 11 * MM
        else:
            seite.text(20 * MM, y, etikett, st.normal, 7, farbe=(0.3, 0.3, 0.3))
            seite.rechteck((20 * MM, y + 2, A4_B - 20 * MM, y + 2 + 9 * MM), farbe=(0.55, 0.55, 0.55))
            hand(seite, 23 * MM, y + 2 + 6.5 * MM, wert, rng, groesse=rng.uniform(11, 13), zittern=zittern)
            y += 15 * MM
    y += 4 * MM
    seite.text(20 * MM, y, "Bemerkungen:", st.normal, 8.5)
    hand(seite, 20 * MM, y + 7 * MM, rng.choice(["Bitte ab sofort neue Anschrift verwenden!",
                                                  "Rückruf erbeten, danke.", "Schaden wurde der Polizei gemeldet."]),
         rng, groesse=11.5, zittern=zittern)
    y += 20 * MM
    hand(seite, 20 * MM, y, m("sonstiges", p.ort, "Ort-Datum-Zeile Handschrift") + ", " + k(datum(dok.heute)), rng,
         groesse=11.5, zittern=zittern)
    seite.linie(20 * MM, y + 2.5, 85 * MM, y + 2.5, 0.4)
    seite.unterschrift(110 * MM, y, rng)
    seite.linie(105 * MM, y + 2.5, A4_B - 20 * MM, y + 2.5, 0.4)
    seite.text(20 * MM, y + 9, "Ort, Datum", st.normal, 6.5)
    seite.text(105 * MM, y + 9, "Unterschrift", st.normal, 6.5)
    dok.satz.merkmale.update({"handschrift", "formular_papier"})
    dok.titel = titel
    return "handschrift_formular"


def typ_blockschrift_formular(dok: Dok) -> str:
    """Formular "bitte in Druckbuchstaben ausfüllen": Versalien, ein Zeichen je Kästchen (Kammfelder)."""
    rng = dok.rng
    st = dok.stil
    p = dok.person(alter=(20, 85))
    dok.hauptperson = p
    v = dok.versicherer()
    seite = dok.satz.neue_seite()
    seite.text(20 * MM, 18 * MM, k(v[0]), st.kopf_familie.fett, 11, farbe=st.akzent)
    titel = rng.choice(["Änderung der Bankverbindung", "Mitteilung Adressänderung", "Antrag Kfz-Versicherung",
                        "Beitrittserklärung Gruppenvertrag"])
    seite.text(20 * MM, 27 * MM, k(titel), st.fett, 13)
    seite.text(20 * MM, 33 * MM, "Bitte in Druckbuchstaben ausfüllen und je Kästchen nur ein Zeichen eintragen.",
               st.normal, 7.5)
    hs = dok.scan_geplant is not None
    sch = druckschrift()
    farbe = TINTE if hs else TINTE_SCHWARZ
    jitter = rng if hs else None
    y = 44 * MM
    kasten = rng.choice([4.6, 5.0, 5.4]) * MM
    n_max = int((A4_B - 40 * MM) / kasten)
    etikett_oben = rng.random() < 0.6
    geb = f"{p.geburtsdatum:%d%m%Y}"
    vnr = K.vertragsnummer(rng, "KF")
    vnr_kurz = "".join(c for c in vnr if c.isalnum())[:14]
    felder = [("Name", "namen", _versal(p.nachname), name_bem(p, "Kammfeld Name; Versalien")),
              ("Vorname(n)", "namen", _versal(p.vornamen), "Kammfeld Vorname; Versalien"),
              ("Geburtsdatum (TTMMJJJJ)", "geburt", geb, "Kammfeld Geburtsdatum ohne Trenner"),
              ("Straße, Hausnr.", "strasse", _versal(p.strasse) + " " + p.hausnummer.upper().replace(" ", ""),
               "Kammfeld Straße und Hausnummer; Versalien"),
              ("PLZ", "plzort", p.plz, "Kammfeld PLZ (Ort eigenes Feld)"),
              ("Ort", "plzort", _versal(p.ort), "Kammfeld Ort (PLZ eigenes Feld); Versalien"),
              ("Telefon", "telefon", "0" + p.vorwahl + "".join(rng.choice("0123456789") for _ in range(6)),
               "Kammfeld Telefon ohne Trenner"),
              ("Versicherungsschein-Nr.", "vertrag", vnr_kurz, "Kammfeld Vertragsnummer")]
    if rng.random() < 0.6:
        felder.append(("IBAN", "iban", K.iban(rng, "DE"), "Kammfeld IBAN"))
    if rng.random() < 0.4:
        felder.append(("Amtl. Kennzeichen", "kfz", K.kennzeichen(rng).replace("-", " "), "Kammfeld Kennzeichen"))
    if rng.random() < 0.3:
        _, stnr = K.steuernummer_land(rng, art="elster")
        felder.append(("Steuernummer (13-stellig)", "steuernr", stnr, "Kammfeld Steuernummer ELSTER-Format"))
    for etikett, kat, wert, bem in felder:
        if y > A4_H - 45 * MM:
            seite = dok.satz.neue_seite()
            y = 25 * MM
        n = min(n_max, max(len(wert) + rng.randint(0, 6), {"PLZ": 5, "Hausnr.": 4}.get(etikett, 8)))
        gruppen = [2, 2, 4, 4, 4, 4, 2] if kat == "iban" else None
        if etikett_oben:
            seite.text(20 * MM, y, etikett, st.normal, 7)
            kammfeld(seite, 20 * MM, y + 2, n, kat, wert, bem, schrift=sch, groesse=11, rng=jitter, kasten=kasten,
                     farbe=farbe, gruppen=gruppen)
            y += 15 * MM
        else:
            seite.text(20 * MM, y + 4.5 * MM, etikett, st.normal, 7.5)
            n = min(n, int((A4_B - 75 * MM) / kasten))
            kammfeld(seite, 62 * MM, y, n, kat, wert[:n], bem, schrift=sch, groesse=11, rng=jitter, kasten=kasten,
                     farbe=farbe, gruppen=gruppen if n >= 22 else None)
            y += 11 * MM
    y += 6 * MM
    hand(seite, 20 * MM, y, m("sonstiges", p.ort, "Ort-Datum-Zeile Blockschrift") + ", " + k(datum(dok.heute)), rng,
         groesse=11, zittern=hs)
    seite.unterschrift(115 * MM, y, rng)
    seite.linie(20 * MM, y + 2.5, 85 * MM, y + 2.5, 0.4)
    seite.linie(110 * MM, y + 2.5, A4_B - 20 * MM, y + 2.5, 0.4)
    seite.text(20 * MM, y + 9, "Ort, Datum", st.normal, 6.5)
    seite.text(110 * MM, y + 9, "Unterschrift", st.normal, 6.5)
    dok.satz.merkmale.update({"kammfelder", "versalien", "formular_papier"})
    dok.titel = titel
    return "blockschrift_formular"


NEUE_TYPEN = {
    "personalausweis": typ_personalausweis,
    "reisepass": typ_reisepass,
    "fuehrerschein": typ_fuehrerschein,
    "sepa_mandat": typ_sepa_mandat,
    "bestandsliste_excel": typ_bestandsliste_excel,
    "unfallbericht": typ_unfallbericht,
    "fax": typ_fax,
    "schreibmaschine": typ_schreibmaschine,
    "handschrift_formular": typ_handschrift_formular,
    "blockschrift_formular": typ_blockschrift_formular,
}
assert list(NEUE_TYPEN) == NEUE_TYPEN_REIHENFOLGE and not set(NEUE_TYPEN) & set(TYPEN)
