"""Generator 1.3: Gegenproben-Strom (werkzeuge/benchmark/dokumenttypen_gegenproben.py) und die Korrekturen der
erweiterten Verteilung (Review der Runde 2b, Befunde 2, 3, 5, 6, 10, 15).

* Gegenproben-Strom: Unterlagen, auf die eine zu weite Regel anspräche (Kfz-Angebot mit "Führerschein" und
  nummerierter Liste, GwG-Blatt mit sechsstelligen Zahlen, E-Mail mit Kontaktzeilen, Versicherer-Fax, Kopfzeilen
  realer Faxgeräte, Formularzeilen in Versalien, Steuernummer-Schreibweisen, Ereignisorte, TD2-Ausweis) – mit
  vollständiger Wahrheit: Personenangaben zu schwärzen, alles andere, was eine zu weite Regel träfe, zu behalten.
* Erweiterte Verteilung: Plan (Typen, Scans) wie Generator 1.2; mindestens zwei vorläufige Personalausweise (TD2),
  Excel-Listen mit 8 bis 14 Zeilen, Kopfzeilen realer Faxgeräte und Versicherer-Marken als Absender, Straße und
  Hausnummer im Kammfeld als EIN Eintrag, Ausstellungsdaten und Klassen des Führerscheins als zu behaltende
  Einträge, unsichtbare Textebene durchsuchbarer Scans mit Wortgrenzen.
* Selbstprüfung der Bewertung auf neuen Typen (Null-Anonymisierer, Orakel): die Wahrheit ist messbar.
"""

import hashlib
import re
from collections import Counter

import pytest

from conftest import braucht_ocr
from werkzeuge.benchmark import bewertung, generator
from werkzeuge.benchmark import dokumenttypen_erweitert as neu
from werkzeuge.benchmark import dokumenttypen_gegenproben as gp


def _plan_digest(plaene) -> str:
    teile = [f"{p.nr}|{p.typ}|{p.scan}|{','.join(p.neben)}" for p in plaene]
    return hashlib.sha256("\n".join(teile).encode()).hexdigest()


# ----------------------------------------------------------------------
# Pläne
# ----------------------------------------------------------------------
@pytest.mark.parametrize("seed, erwartet", [
    (3, "e85351200ed6045493af6460674aee24af45c8d60f6782448ebc04d03d95627e"),
    (9, "6eb45a0de7a03a5fd4a7d5c26efd23c5672044c6c6aacf87c78cfd7b3d49d48d"),
])
def test_erweiterter_plan_wie_generator_12(seed, erwartet):
    """Typen und Scans der erweiterten Verteilung bleiben (die Korpora s3x/s9x wurden mit Generator 1.2 erzeugt);
    Generator 1.3 ändert nur Inhalte einzelner Typen und erzwingt die TD2-Variante."""
    assert _plan_digest(generator.plane_korpus(80, seed, erweitert=True)) == erwartet


@pytest.mark.parametrize("seed", [3, 9, 11])
def test_mindestzahl_vorlaeufiger_personalausweise(seed):
    plaene = generator.plane_korpus(80, seed, erweitert=True)
    ausweise = [p for p in plaene if p.typ == "personalausweis"]
    assert len(ausweise) >= 6
    assert sum(1 for p in ausweise if p.variante == "td2") >= 2
    assert all(p.variante is None for p in plaene if p.typ != "personalausweis")


def test_gegenproben_plan():
    a = generator.plane_korpus(27, 5, gegenproben=True)
    assert _plan_digest(a) == _plan_digest(generator.plane_korpus(27, 5, gegenproben=True))     # deterministisch
    assert Counter(p.typ for p in a) == Counter({t: 3 for t in gp.TYPEN_REIHENFOLGE})
    assert all(p.mischung == "gegenproben" for p in a)
    assert all(p.scan for p in a if p.typ in ("gp_ereignisort", "gp_td2_ausweis"))
    # der Gegenproben-Strom berührt Standard- und erweiterte Pläne nicht
    assert not {p.typ for p in generator.plane_korpus(80, 1)} & set(gp.TYPEN_GEGENPROBEN)


# ----------------------------------------------------------------------
# Gegenproben: gültige Wahrheit, zu behaltende Einträge
# ----------------------------------------------------------------------
_BEHALTEN_ERWARTET = {
    "gp_kfz_angebot": ["Beginn aller Angebote", "Werkstattbindung optional"],
    "gp_gwg_zahlen": ["Personalausweis"],
    "gp_email_kontakt": [],
    "gp_fax_versicherer": [],
    "gp_fax_kunde": ["TELEFAX"],
    "gp_versalien_zeilen": [],
    "gp_steuernummer": [],
    "gp_ereignisort": ["Ihrer Wahl", "3. Verletzte: nein"],
    "gp_td2_ausweis": [],
}


@pytest.mark.parametrize("typ", gp.TYPEN_REIHENFOLGE)
def test_gegenproben_dokumente_haben_gueltige_wahrheit(typ, tmp_path):
    nr = gp.TYPEN_REIHENFOLGE.index(typ) + 1
    plan = generator.Plan(nr, typ, None, (), mischung="gegenproben", variante="td2" if typ == "gp_td2_ausweis"
                          else None)
    w = generator.erzeuge_dokument(plan, 5, tmp_path)
    assert w["erzeugung"]["mischung"] == "gegenproben"
    assert w["erzeugung"]["generator"] == generator.GENERATOR_VERSION_ERWEITERT
    assert bewertung.pruefe_wahrheit(tmp_path / w["dokument"], w) == []
    kern = [e for e in w["eintraege"] if e["erwartung"] == "schwaerzen" and e["umfang"] == "kern"]
    assert kern
    behalten = {e["text"] for e in w["eintraege"] if e["erwartung"] == "behalten"}
    assert set(_BEHALTEN_ERWARTET[typ]) <= behalten, behalten
    if typ == "gp_td2_ausweis":
        assert "mrz_td2" in w["merkmale"]
    if typ == "gp_fax_versicherer":
        assert behalten & set(gp._MARKEN)                    # Markenname als Absender: bleibt
    if typ == "gp_versalien_zeilen":
        texte = {e["text"] for e in kern}
        assert any(re.search(r"[A-ZÄÖÜ]+ {3,}[A-ZÄÖÜ]+ \d+", t) for t in texte)   # Straße mit mehreren Leerzeichen


# ----------------------------------------------------------------------
# Erweiterte Verteilung (Generator 1.3)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("seed", [3, 4, 5])
def test_excel_liste_hoechstens_vierzehn_zeilen(seed, tmp_path):
    """Eine Excel-Liste trug in Generator 1.2 mit 22 bis 40 Zeilen zwei Drittel aller Kern-Einträge eines Korpus und
    bestimmte damit die Schlagzeile (Befund 6)."""
    plan = generator.Plan(1, "bestandsliste_excel", None, (), mischung="erweitert")
    w = generator.erzeuge_dokument(plan, seed, tmp_path)
    zeilen = [e for e in w["eintraege"] if e["bemerkung"].split(";")[0] == "Excel-Spalte Name"]
    assert neu.EXCEL_ZEILEN[0] <= len(zeilen) <= neu.EXCEL_ZEILEN[1]


def test_blockschrift_strasse_und_hausnummer_ein_eintrag(tmp_path):
    plan = generator.Plan(1, "blockschrift_formular", None, (), mischung="erweitert")
    w = generator.erzeuge_dokument(plan, 3, tmp_path)
    strassen = [e["text"] for e in w["eintraege"] if e["kategorie"] == "strasse"]
    assert strassen and all(re.search(r"\d", t) and re.search(r"[A-ZÄÖÜ]{3}", t) for t in strassen), strassen


def test_fuehrerschein_daten_und_klassen_bleiben(tmp_path):
    plan = generator.Plan(1, "fuehrerschein", None, (), mischung="erweitert")
    w = generator.erzeuge_dokument(plan, 3, tmp_path)
    behalten = [e["text"] for e in w["eintraege"] if e["erwartung"] == "behalten"]
    assert sum(1 for t in behalten if re.fullmatch(r"\d{2}\.\d{2}\.\d{2,4}", t)) >= 2       # 4a und 4b
    assert any(re.fullmatch(r"[A-Z0-9]{1,3}(?:/[A-Z0-9]{1,3})+", t) for t in behalten)      # Klassen


def test_fax_kopfzeilen_realer_geraete_und_versicherer(tmp_path):
    formen, marken = set(), set()
    for nr in range(1, 25):
        w = generator.erzeuge_dokument(generator.Plan(nr, "fax", None, (), mischung="erweitert"), 3, tmp_path)
        marken |= {e["text"] for e in w["eintraege"] if e["erwartung"] == "behalten"} & set(neu.FAX_MARKEN)
        import pymupdf as fitz
        with fitz.open(tmp_path / w["dokument"]) as doc:
            kopf = next(z for z in doc[0].get_text("text").splitlines() if re.search(r"\d\d:\d\d", z))
        formen.add("page" if "Page" in kopf or "PAGE" in kopf else "sekunden" if re.search(r"\d:\d\d:\d\d", kopf)
                   else "ampm" if re.search(r"\d[AP]M", kopf) else "s_ohne_fax" if re.search(r"S\. \d/\d", kopf)
                   else "generator_12")
    assert len(formen) >= 4, formen
    assert marken, "kein Versicherer-Fax mit Markennamen"


# ----------------------------------------------------------------------
# Selbstprüfung der Bewertung auf den neuen Typen (Befund 5)
# ----------------------------------------------------------------------
@braucht_ocr
def test_selbstpruefung_auf_neuen_typen(tmp_path):
    """Null-Anonymisierer: jeder zu schwärzende Eintrag ein Leck an seiner Stelle, alles zu Behaltende erhalten;
    Orakel (auch mit Platzhaltertext): Recall 100 %, Über-Schwärzung 0 – auf Kammfeldern (Straße und Hausnummer EIN
    Eintrag) und Handschrift durchsuchbarer Scans (Textebene mit Wortgrenzen), Führerschein- und TD2-Scans, Fax,
    Versalien-Formular und E-Mail-Ausdruck. Ausweise mit MRZ auf der TEXTEBENE fehlen bewusst: eine MRZ-Zeile ist dort
    EIN PDF-Wort, und die Bewertung (bewertung._am_ort, Wortmitte im Eintragsrechteck) kann ein einzelnes MRZ-Feld nicht
    ortsgenau prüfen – eine Lücke der Bewertung, nicht der Wahrheit."""
    korpus = tmp_path / "korpus"
    plaene = [
        generator.Plan(1, "blockschrift_formular", "scan_durchsuchbar", (), mischung="erweitert"),
        generator.Plan(2, "sepa_mandat", "scan_durchsuchbar", (), mischung="erweitert"),
        generator.Plan(3, "blockschrift_formular", None, (), mischung="erweitert"),
        generator.Plan(4, "fuehrerschein", "scan_300_gut", (), mischung="erweitert"),
        generator.Plan(5, "fax", "fax", (), mischung="erweitert"),
        generator.Plan(6, "gp_versalien_zeilen", None, (), mischung="gegenproben"),
        generator.Plan(7, "gp_td2_ausweis", "scan_300_gut", (), mischung="gegenproben", variante="td2"),
        generator.Plan(8, "gp_email_kontakt", None, (), mischung="gegenproben"),
    ]
    for plan in plaene:
        w = generator.erzeuge_dokument(plan, 21, korpus)
        assert bewertung.pruefe_wahrheit(korpus / w["dokument"], w) == [], w["dokument"]
    e = bewertung.selbstpruefung(korpus, tmp_path / "selbst", melde=None)
    null = e["null_anonymisierer"]
    assert null["schwaerzen"] > 50 and null["leck"] == null["schwaerzen"], null["nicht_leck"][:10]
    assert null["nicht_am_ort"] == [] and null["behalten_erhalten"] == null["behalten"], null
    for name in ("orakel", "orakel_platzhalter"):
        assert e[name]["recall_kern"] == 1.0 and e[name]["recall_erweitert"] == 1.0, e[name]["nicht_entfernt"][:10]
        assert e[name]["ueberschwaerzung"] == 0.0, e[name]["ueberschwaerzt"]
