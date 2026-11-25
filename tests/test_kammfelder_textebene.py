"""Kurze Kammfeld-Werte der Textebene, mehrere Feldnamen über einem Kammfeld und Kundendatenblöcke eines
EDV-Ausdrucks in OCR-Zellen.

Stille Lecks der Entwicklungskorpora: Hausnummer „1 3“ allein in ihrem Kammfeld unter „Hausnr.“ (kürzer als die drei
Zeichen einer gesperrten Folge), Straße und Hausnummer in einer Zeile unter „Straße, Hausnr.“ (zwei Feldnamen in der
Zeile darüber), Kundenanschrift unter „VERSICHERUNGSNEHMER ⇥⇥ NWOSU, ⇥⇥ TESFAY“ als Firmenanschrift verworfen (der
Name in zwei OCR-Zellen zählte nicht als Kundenzeile, „BANKVERBINDUNG“ im Block machte ihn zum Briefkopf).

Zu jeder Regel Abwandlungen und Gegenproben: Zählfelder, Kürzel und Kreuzchen hinter anderen Feldnamen, Ziffern unter
Namensfeldern, Feldnamen verschiedener Kategorien darüber, kurze Werte ohne Feldnamen; Mitarbeiterzeilen und
Briefköpfe mit Registerangaben behalten ihre Firmenanschrift. Alle Werte sind erfunden."""

import pytest

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen
    import fitz

from anonymisierer import analyse, detektoren, seitenmodell
from anonymisierer.detektoren import Kontext
from anonymisierer.muster import KATEGORIEN

ALLE = {k[0] for k in KATEGORIEN if k[4]}
KOPF = "Name\nM U S T E R M A N N\n"          # ein Kammfeld auf der Seite (Vorfilter der Regel)


def _detektor(name):
    return next(e for e in detektoren.REGISTER if e.name == name).funktion


def _treffer(dok, name):
    return [(t.kategorie, dok.text[t.start:t.ende]) for t in _detektor(name)(dok, Kontext(ALLE, "hoch"))]


def _kamm(text):
    """Treffer von struktur.kammfeld ohne den Namen der Kopfzeile."""
    return set(_treffer(seitenmodell.dokument_aus_text(KOPF + text), "struktur.kammfeld")) - \
        {("namen", "M U S T E R M A N N")}


# ----------------------------------------------------------------------
# Kurze Werte (ein oder zwei Zeichen) hinter einem Feldnamen
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, erwartet", [
    ("Hausnr.\n1 3", ("strasse", "1 3")),
    ("Hausnummer\n7 A", ("strasse", "7 A")),
    ("Hausnr.\n8", ("strasse", "8")),
    ("Hausnr. 1 3", ("strasse", "1 3")),                 # Feldname links in derselben Zeile
    ("Hausnr.\n1 3 5", ("strasse", "1 3 5")),            # drei Zeichen: wie bisher als gesperrte Folge
    ("Vorname\nL I", ("namen", "L I")),                  # Name aus zwei Buchstaben
])
def test_kurzer_kammfeldwert_hinter_feldnamen(text, erwartet):
    assert _kamm(text) == {erwartet}


@pytest.mark.parametrize("text", [
    "Anzahl der Kinder\n2",           # Zählfeld
    "Tarifgruppe\nB 4",               # Kürzel hinter einem Feldnamen ohne Personenbezug
    "Geschlecht\nM",                  # Kreuzchen/Kürzel
    "Name des Kindes\n1 2",           # Ziffern sind kein Name
    "Vorname\nM",                     # ein Buchstabe: Initiale, kein Name
    "Hausnr.\nA B",                   # keine Hausnummer (beginnt nicht mit einer Ziffer)
    "\n1 3",                          # ohne Feldnamen
    "Bemerkung\n1 3",                 # Feldname ohne Personenbezug
    "Name, Telefon\nL I",             # Feldnamen verschiedener Kategorien darüber: mehrdeutig
    "Seite 1 2",                      # Seitenzahl im Fließtext
])
def test_kurzer_kammfeldwert_gegenproben(text):
    assert _kamm(text) == set()


def test_kurzer_wert_braucht_ein_kammfeld_auf_der_seite():
    """Ohne gesperrte Folge auf der Seite (kein Kammfeld-Formular) bleibt die Regel aus – Fließtext „Hausnr. 8“ ist
    Sache der übrigen Regeln."""
    assert _treffer(seitenmodell.dokument_aus_text("Hausnr.\n1 3"), "struktur.kammfeld") == []


# ----------------------------------------------------------------------
# Mehrere Feldnamen in der Zeile über dem Kammfeld
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, erwartet", [
    ("Straße, Hausnr.\nB R U N N E N W E G\t\t7 5", ("strasse", "B R U N N E N W E G\t\t7 5")),
    ("Straße, Hausnummer\nA M A N G E R\t\t1 2 A", ("strasse", "A M A N G E R\t\t1 2 A")),
    ("PLZ, Ort\n5 3 1 1 1\t\tB O N N", ("plzort", "5 3 1 1 1\t\tB O N N")),
    ("Name, Vorname\nO S T E R K A M P\t\tT I L L", ("namen", "O S T E R K A M P\t\tT I L L")),
])
def test_feldnamen_derselben_kategorie_darueber(text, erwartet):
    assert _kamm(text) == {erwartet}


@pytest.mark.parametrize("text", [
    "Name, Telefon\nO S T E R K A M P\t\t0 5 5 1 2 3",     # verschiedene Kategorien: mehrdeutig, wie bisher
    "Anzahl, Tarifgruppe\n2\t\tB 4",                       # Feldnamen ohne Personenbezug
])
def test_feldnamen_verschiedener_kategorien_darueber_gegenproben(text):
    assert _kamm(text) == set()


# ----------------------------------------------------------------------
# Ende zu Ende auf der Textebene: genau die eine Stelle, nichts in der IBAN
# ----------------------------------------------------------------------
_BREITE = 14.2


def _kammformular(pfad, zeilen):
    """Formular mit Kammfeldern auf der Textebene: je Zeile Felder (Feldname, Wert, Kästchen), ein Zeichen je
    Kästchen; Feldnamen über dem Feld."""
    doc = fitz.open()
    seite = doc.new_page(width=595, height=842)
    seite.insert_text((57, 60), "Änderung der Anschrift", fontsize=13)
    y = 100.0
    for zeile in zeilen:
        x = 57.0
        for etikett, wert, n in zeile:
            if etikett:
                seite.insert_text((x, y), etikett, fontsize=7.5)
            for i in range(n):
                r = fitz.Rect(x + i * _BREITE, y + 4, x + (i + 1) * _BREITE, y + 21)
                seite.draw_rect(r, color=(0.3, 0.3, 0.3), width=0.5)
                if i < len(wert) and wert[i] != " ":
                    seite.insert_text((r.x0 + 4, r.y1 - 4.5), wert[i], fontsize=11, fontname="cour")
            x += n * _BREITE + 20
        y += 45
    doc.save(pfad)
    doc.close()
    return pfad


@pytest.mark.parametrize("anschrift", [
    [[("Straße", "LINDENWEG", 14)], [("Hausnr.", "13", 4)]],                    # Hausnummer im eigenen Feld
    [[("Straße, Hausnr.", "LINDENWEG", 14), ("", "13", 4)]],                     # beide Felder in einer Zeile
])
def test_hausnummer_im_kammfeld_der_textebene_geschwaerzt(tmp_path, anschrift):
    zeilen = [[("Name", "BERGHAUSEN", 14)], [("Vorname", "IDA", 10)], *anschrift,
              [("PLZ", "37073", 5)], [("Ort", "GOETTINGEN", 14)],
              [("IBAN", "DE13 3704 0044 0532 0130 00", 27)], [("Anzahl der Fahrzeuge", "2", 3)]]
    e = analyse.analysiere_pdf(_kammformular(tmp_path / "kamm.pdf", zeilen), ALLE, [], [])
    text = e["modell"].text
    strasse = [f for f in e["funde"] if f["kategorie"] == "strasse"]
    gedeckt = [text[st["start"]:st["ende"]] for f in strasse for st in f["stellen"] if st.get("an", True)]
    assert any(t.replace(" ", "").replace("\t", "").endswith("13") for t in gedeckt), gedeckt
    # „1 3“ steht auch in der IBAN – dort keine eigene Stelle der Hausnummer
    iban = next(f for f in e["funde"] if f["kategorie"] == "iban")
    i0, i1 = iban["stellen"][0]["start"], iban["stellen"][0]["ende"]
    assert not any(i0 <= st["start"] < i1 for f in strasse for st in f["stellen"])
    # das Zählfeld bleibt lesbar
    assert not any(f["text"].strip() == "2" for f in e["funde"])


# ----------------------------------------------------------------------
# Kundendatenblock eines EDV-Ausdrucks in OCR-Zellen ist kein Briefkopf
# ----------------------------------------------------------------------
def _ocr_dok(zeilen):
    """OCR-Seite: (Block, Zeile) je Zeile, Zellen durch "\\t\\t" (große Lücke), Wörter durch " "."""
    doc = fitz.open()
    seite = doc.new_page(width=595, height=842)
    woerter = []
    y = 50.0
    for zi, (block, zeile) in enumerate(zeilen):
        x, wi = 50.0, 0
        for ci, zelle in enumerate(zeile.split("\t\t")):
            if ci:
                x += 60
            for w in zelle.split(" "):
                if not w:
                    x += 5
                    continue
                breite = 6.0 * len(w)
                woerter.append((x, y, x + breite, y + 12, w, block, zi, wi))
                wi += 1
                x += breite + 4
        y += 16
    s = seitenmodell.seite_aufbauen(seite, 0, ocr_woerter=woerter, ocr_quelle="ocr")
    doc.close()
    return seitenmodell.Dokument(None, [s])


_EDV_KOPF = [(0, "WESERBERGLAND RECHTSSCHUTZ AG\t\tBLATT\t\t1\t\tDRUCK\t\t23.04.25"), (1, "BEITRAGSRECHNUNG")]


@pytest.mark.parametrize("name", ["OKAFOR,\t\tAMARA", "AMARA\t\tOKAFOR", "Okafor,\t\tAmara", "OKAFOR, AMARA"])
def test_edv_kundenblock_in_ocr_zellen_ist_keine_firmenanschrift(name):
    zeilen = _EDV_KOPF + [(2, "VERS.-NR.\t\tLV 8195-1542-21\t\tKD.-NR.\t\t43768327"),
                          (2, "VERSICHERUNGSNEHMER\t\t" + name),
                          (2, "ANSCHRIFT\t\tAM LINDENHOF 12,\t\t37073 GOETTINGEN"), (2, "GEB.-DATUM\t\t03.06.1962"),
                          (2, "BANKVERBINDUNG\t\tIBAN DE31914762221104673928")]
    dok = _ocr_dok(zeilen)
    assert ("plzort", "37073 GOETTINGEN") in _treffer(dok, "muster.plzort")
    assert ("strasse", "AM LINDENHOF 12") in _treffer(dok, "muster.strasse")
    assert not getattr(dok, "struktur_vorschlaege", None)


@pytest.mark.parametrize("zeilen", [
    # Mitarbeiterzeile statt Kundenzeile: Block mit Registerwort bleibt Firmenblock
    _EDV_KOPF + [(2, "ANSPRECHPARTNER\t\tMUELLER,\t\tHANS"), (2, "ANSCHRIFT\t\tHAUPTSTRASSE 5,\t\t50667 KOELN"),
                 (2, "BANKVERBINDUNG\t\tIBAN DE31914762221104673928")],
    # Briefkopf mit Registerangaben
    [(0, "Musterversicherung AG\t\tHauptstraße 5\t\t50667 Köln"), (0, "Vorstand:\t\tDr. A. Beispiel"),
     (0, "HRB 12345\t\tAmtsgericht Köln")],
])
def test_firmenanschrift_in_ocr_zellen_bleibt(zeilen):
    dok = _ocr_dok(zeilen)
    assert _treffer(dok, "muster.plzort") == [] and _treffer(dok, "muster.strasse") == []
    assert {v["kategorie"] for v in dok.struktur_vorschlaege} == {"plzort", "strasse"}
