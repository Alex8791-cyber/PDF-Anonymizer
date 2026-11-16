"""Tests der Regeln für neue Dokumentformen: Faxkopfzeile (faxkopf.py), Kammfelder und gesperrte Schrift
(kammfelder.py), EDV-/Schreibmaschinenausdrucke mit breiten Lücken, quer gestellte Tabellen mit einer Spalte je
Beteiligtem, Bestandslisten mit Kürzel-Spaltenköpfen und Versalien, Rohwerte hinter Feldnamen auf OCR-Seiten
(struktur.py, struktur_adresse.py, struktur_tabelle.py).

Zu jeder Regel gibt es Gegenproben: Druckzeile eines E-Mail-Programms, Faxkopf einer Organisation, Briefkopf mit
Registerangaben, Satzreste und Spaltenköpfe hinter Feldnamen, Ereignisorte."""

import pytest

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen
    import fitz

from anonymisierer import detektoren, seitenmodell
from anonymisierer.detektoren import Kontext
from anonymisierer.detektoren import faxkopf as fk
from anonymisierer.detektoren import struktur as st
from anonymisierer.muster import KATEGORIEN

ALLE = {k[0] for k in KATEGORIEN if k[4]}


def _detektor(name):
    return next(e for e in detektoren.REGISTER if e.name == name).funktion


def _treffer(dok, name):
    return [(t.kategorie, dok.text[t.start:t.ende]) for t in _detektor(name)(dok, Kontext(ALLE, "hoch"))]


def _text(text, name):
    return set(_treffer(seitenmodell.dokument_aus_text(text), name))


def _ocr_dok(zeilen):
    """OCR-Seite wie in test_detektoren_ocr.py: Zellen durch "\\t\\t" (große Lücke), Wörter durch " "."""
    doc = fitz.open()
    seite = doc.new_page(width=595, height=842)
    woerter = []
    y = 80.0
    for zi, zeile in enumerate(zeilen):
        x, wi = 50.0, 0
        for ci, zelle in enumerate(zeile.split("\t\t")):
            if ci:
                x += 60
            for w in zelle.split(" "):
                if not w:
                    x += 5
                    continue
                breite = 6.0 * len(w)
                woerter.append((x, y, x + breite, y + 12, w, 0, zi, wi))
                wi += 1
                x += breite + 4
        y += 18
    s = seitenmodell.seite_aufbauen(seite, 0, ocr_woerter=woerter, ocr_quelle="ocr")
    doc.close()
    return seitenmodell.Dokument(None, [s])


# ----------------------------------------------------------------------
# Faxkopfzeile
# ----------------------------------------------------------------------
@pytest.mark.parametrize("zeile, name, nummer", [
    ("16.04.2025 14:32   MÜLLER HANS   FAX 0911 123456   S. 01/02", "MÜLLER HANS", "0911 123456"),
    ("Von: Hans Müller  Fax: 0911 123456   An: Maklerbüro   16.04.2025 14:32   Seite 1 von 2",
     "Hans Müller", "0911 123456"),
    ("+49 6221 324615   HORST STEINBRÜCK   2025-04-16 10:05   P.001", "HORST STEINBRÜCK", "+49 6221 324615"),
    ("069 342183   PRAXIS DR. SCHÄFER   16.04.25 09:12   P.002", "PRAXIS DR. SCHÄFER", "069 342183"),
    # 1-Bit-Fax: die OCR verliest die führende 0 – die Stelle zählt trotzdem
    ("Von: charlotte Frisch Fax: 99171/44511 An: Maklerbüro\t\t2025-05-09 17:24\t\tSeite 1 von 3",
     "charlotte Frisch", "99171/44511"),
])
def test_faxkopf_absender_und_nummer(zeile, name, nummer):
    werte = {(zeile[s:e], k) for s, e, k in fk.faxkopf_werte(zeile)}
    assert werte == {(name, "namen"), (nummer, "telefon")}


@pytest.mark.parametrize("zeile", [
    "16.04.2025 14:32   SCHADENSERVICE   FAX 069 1234567   S. 01/02",        # Organisation sendet
    "Von: Musterversicherung AG  Fax: 0221 998877   16.04.2025 14:32   Seite 1 von 2",
    "Gedruckt am 16.04.2025 14:32 – Seite 1 von 2",                             # Druckzeile, kein Fax
    "Telefax 0221 123456 · www.muster-versicherung.de",                         # Briefkopf ohne Uhrzeit
])
def test_faxkopf_gegenproben(zeile):
    assert fk.faxkopf_werte(zeile) == []


# Review-Befund 3: Kopfzeilen realer Geräte – ohne das Wort Fax, mit Sekunden oder AM/PM, englisch, "P. 1/2",
# Tabulatoren der OCR, Feldnamen ohne Lücke
@pytest.mark.parametrize("zeile, name, nummer", [
    ("16.04.2025 14:32   MUELLER HANS   +49 911 123456   S. 1/2", "MUELLER HANS", "+49 911 123456"),
    ("16/04/2025 14:32  FROM: MUELLER HANS  +49911123456  PAGE 01/02", "MUELLER HANS", "+49911123456"),
    ("APR-16-2025 02:32PM   MUELLER HANS   0911 123456   P. 1/2", "MUELLER HANS", "0911 123456"),
    ("16.04.2025 14:32:07   MUELLER HANS   Fax 0911 123456   Seite 1/2", "MUELLER HANS", "0911 123456"),
    ("16.04.2025 14:32   GRUBER JOSEF   0911 123456   Page 1 of 2", "GRUBER JOSEF", "0911 123456"),
    ("FROM:MUELLER HANS 0911123456 TO:MAKLERBUERO 16.04.2025 14:32 P.001/002", "MUELLER HANS", "0911123456"),
    ("16.04.2025 14:32   M. HUFNAGL   +49 911 123456   S.\t\t01/02", "M. HUFNAGL", "+49 911 123456"),
    ("16.04.2025 14:32   NÜRNBERGER HANS   FAX 0911 963636   S. 01/02", "NÜRNBERGER HANS", "0911 963636"),
    ("16.04.2025 14:32   NÜRNBERGER   FAX 0911 963636   S. 01/02", "NÜRNBERGER", "0911 963636"),   # auch Nachname
])
def test_faxkopf_reale_kopfformen(zeile, name, nummer):
    werte = {(zeile[s:e], k) for s, e, k in fk.faxkopf_werte(zeile)}
    assert werte == {(name, "namen"), (nummer, "telefon")}


# Review-Befund 10: Versicherer und Organisationen der Erlaubnisliste als Absender sind keine Person
@pytest.mark.parametrize("kennung", ["HUK-COBURG", "ERGO", "Gothaer", "SIGNAL IDUNA", "Debeka", "Provinzial",
                                     "ALLIANZ", "Alte Leipziger", "DEBEKA KOBLENZ"])
def test_faxkopf_versicherer_als_absender(kennung):
    assert fk.faxkopf_werte(f"16.04.2025 14:32   {kennung}   FAX 09561 963636   S. 01/02") == []


def test_faxkopf_druckzeile_mit_vorgangsnummer_ist_kein_fax():
    assert fk.faxkopf_werte("Druck: 16.04.2025 14:32   Seite 1 von 3   Vorgang 2025-123") == []


# ohne Fax-Merkmal (nur an der Rufnummer erkannt) muss jede Wortgruppe eine Kennung sein: Druck- und Fußzeilen mit
# Feldnamen, Funktionswörtern oder Sprechzeiten bleiben unberührt
@pytest.mark.parametrize("zeile", [
    "Erstellt am 16.04.2025 14:32   Vertrag 1234567890   Seite 1 von 2",
    "Gültig ab 16.04.2025 14:32   Kundennummer 123456789   Seite 1 von 2",
    "Druck: 16.04.2025 14:32   Seite 1 von 3   Vorgang 2025-123456",
    "Mo-Fr 8:00-18:00   Tel 0911 123456   Seite 2 von 4",
    "16.04.2025 14:32   PRAXIS AM MARKT   0911 123456   S. 1/2",
])
def test_faxkopf_ohne_merkmal_druckzeilen(zeile):
    assert fk.faxkopf_werte(zeile) == []


def test_faxkopf_ohne_merkmal_nur_rufnummer():
    zeile = "16.04.2025 14:32   +49 911 123456   S. 1/2"
    assert [(zeile[s:e], k) for s, e, k in fk.faxkopf_werte(zeile)] == [("+49 911 123456", "telefon")]


def test_faxkopf_detektor_nur_im_seitenrand(tmp_path):
    pfad = tmp_path / "fax.pdf"
    doc = fitz.open()
    seite = doc.new_page(width=595, height=842)
    seite.insert_text((20, 20), "16.04.2025 14:32   MUELLER HANS   FAX 0911 123456   S. 01/02", fontsize=7,
                      fontname="cour")
    seite.insert_text((60, 400), "16.04.2025 14:32   MUELLER HANS   FAX 0911 123456   S. 01/02", fontsize=9,
                      fontname="cour")
    doc.save(pfad)
    doc.close()
    doc = fitz.open(pfad)
    vorbereitung = seitenmodell.dokument_vorbereiten(doc)
    dok = seitenmodell.dokument_aufbauen(vorbereitung.get("dokument") or doc, pfad, vorbereitung=vorbereitung)
    treffer = [t for t in _detektor("struktur.faxkopf")(dok, Kontext(ALLE, "hoch"))]
    assert {dok.text[t.start:t.ende] for t in treffer} == {"MUELLER HANS", "0911 123456"}
    assert all(dok.seite_von(t.start) == 0 and t.start < dok.text.index("\n") for t in treffer)


# ----------------------------------------------------------------------
# Kammfelder / gesperrte Schrift
# ----------------------------------------------------------------------
def test_kammfelder_mit_feldnamen():
    gefunden = _text("Name\nM A R K O V I Ć\nGeburtsdatum (TTMMJJJJ) 2 6 0 7 1 9 8 3\n"
                     "Straße, Hausnummer\nH A U P T S T R . 1 2", "struktur.kammfeld")
    assert ("namen", "M A R K O V I Ć") in gefunden
    assert ("geburt", "2 6 0 7 1 9 8 3") in gefunden
    assert ("strasse", "H A U P T S T R . 1 2") in gefunden


def test_kammfeld_ohne_feldnamen_nur_was_sich_selbst_ausweist():
    gefunden = _text("D E 8 9 3 7 0 4 0 0 4 4 0 5 3 2 0 1 3 0 0 0\nA B C D E F", "struktur.kammfeld")
    assert gefunden == {("iban", "D E 8 9 3 7 0 4 0 0 4 4 0 5 3 2 0 1 3 0 0 0")}
    assert _text("Bitte in Druckbuchstaben ausfüllen: A B C", "struktur.kammfeld") == set()


# ----------------------------------------------------------------------
# EDV-Ausdruck / Schreibmaschine: breite Lücken statt Doppelpunkt, Versalien
# ----------------------------------------------------------------------
_EDV = ("WESERBERGLAND RECHTSSCHUTZ AG   BLATT 1   DRUCK 23.04.25\nBEITRAGSRECHNUNG\n"
        "VERS.-NR.             LV 8195-1542-21     KD.-NR. 43768327\nVERSICHERUNGSNEHMER   HAAS, FIETE\n"
        "ANSCHRIFT             HOHE STRASSE 129-131, 96450 COBURG\nGEB.-DATUM            03.06.1962\n"
        "BANKVERBINDUNG        IBAN DE31914762221104673928")


def test_edv_ausdruck_kundenanschrift_trotz_firmenkopf():
    """Der Kundendatenblock unter dem Firmenkopf ist kein Briefkopf: "BANKVERBINDUNG" (Registerwort) und der
    Firmenname darüber machen die Kundenanschrift nicht zur Firmenanschrift; "STRASSE" in "HOHE STRASSE" ist kein
    Feldname, und die Straße beginnt nicht schon beim Feldnamen."""
    dok = seitenmodell.dokument_aus_text(_EDV)
    assert ("strasse", "HOHE STRASSE 129-131") in _treffer(dok, "muster.strasse")
    assert ("plzort", "96450 COBURG") in _treffer(dok, "muster.plzort")
    werte = set(_treffer(dok, "struktur.etikett_wert"))
    assert {("strasse", "HOHE STRASSE 129-131"), ("plzort", "96450 COBURG"), ("namen", "HAAS, FIETE"),
            ("geburt", "03.06.1962")} <= werte


def test_firmenanschrift_im_briefkopf_bleibt():
    text = ("Musterversicherung AG\nHauptstraße 5\n50667 Köln\nVorstand: Dr. A. Beispiel\nHRB 12345 Amtsgericht Köln\n"
            "\n\n\n\n\n\n\n\n\n\n\n\n\n\nSehr geehrte Damen und Herren,")
    dok = seitenmodell.dokument_aus_text(text)
    assert _treffer(dok, "muster.strasse") == [] and _treffer(dok, "muster.plzort") == []


def test_strassenwort_im_strassennamen_ist_kein_feldname():
    seite = seitenmodell.dokument_aus_text("Anschrift: Neue Str. 5, 12345 Musterstadt\nStraße: Hauptweg 3").seiten[0]
    etiketten = {seite.text[et.start:et.ende] for et in st.etiketten(seite)}
    assert "Str." not in etiketten
    assert "Straße" in etiketten                                    # Feldname am Zeilenanfang mit Doppelpunkt


# ----------------------------------------------------------------------
# Quer gestellte Tabelle: eine Spalte je Beteiligtem
# ----------------------------------------------------------------------
def test_quer_gestellte_tabelle_liest_alle_wertzellen():
    text = ("Unfallbeteiligter A\t\tUnfallbeteiligter B\nName, Vorname\t\tAydemir, Zozan\t\tKudrjawzewa, Natalia\n"
            "Führerschein-Nr.\t\tH996KNYGE24\t\tP9873B6ND15\n"
            "Versicherungsschein-Nr.\t\t6 392 585 469\t\t092/488085-9\nFahrzeug\t\tFiat 500e\t\tMercedes-Benz C 200")
    werte = _text(text, "struktur.etikett_wert")
    assert {("namen", "Kudrjawzewa, Natalia"), ("ausweis", "H996KNYGE24"), ("ausweis", "P9873B6ND15"),
            ("vertrag", "6 392 585 469"), ("vertrag", "092/488085-9")} <= werte
    assert not any("Fiat" in t or "Mercedes" in t for _, t in werte)


def test_folgezellen_hoeren_beim_naechsten_feldnamen_auf():
    werte = _text("Vertragsnummer\t\tLV-2024-123456\t\tBeginn\t\t01.01.2024\t\tBeitrag\t\t45,90 EUR",
                  "struktur.etikett_wert")
    assert ("vertrag", "LV-2024-123456") in werte
    assert not any("45,90" in t or "01.01.2024" in t for _, t in werte)


# ----------------------------------------------------------------------
# Bestandsliste (Excel-Export): Kürzel-Spaltenköpfe, Versalien, Namen, die zugleich Wörter sind
# ----------------------------------------------------------------------
_LISTE = ("NR.\t\tNACHNAME\t\tVORN.\t\tGEB.DAT.\t\tVN_PLZ\t\tVN_ORT\t\tSP.\n"
          "1\t\tGOLEBIOWSKA\t\tMALGORZATA\t\t22.02.2001\t\t66606\t\tST. WENDEL\t\tRIESTER\n"
          "2\t\tFREITAG\t\tKLAUS\t\t27.11.1970\t\t39104\t\tMAGDEBURG\t\tKFZ\n"
          "3\t\tPOPAL\t\tMEHDI\t\t24.08.1954\t\t19053\t\tSCHWERIN\t\tKFZ\n"
          "4\t\tGUENDOGDU\t\tNUR\t\t28.04.2006\t\t66386\t\tLAUF A.D.PEGNITZ\t\tUNF\n"
          "5\t\tMEYER\t\tPETRA\t\t01.03.1980\t\t20095\t\tHAMBURG\t\tPHV\n"
          "6\t\tSCHMIDT\t\tJONAS\t\t11.11.1991\t\t80331\t\tMÜNCHEN\t\tBU")


def _liste_pdf(pfad, text, xs):
    """Tabelle mit festen Spalten (wie ein Excel-Ausdruck): Zellen je Zeile durch "\\t\\t" getrennt."""
    doc = fitz.open()
    seite = doc.new_page(width=842, height=595)
    for j, zeile in enumerate(text.split("\n")):
        for x, zelle in zip(xs, zeile.split("\t\t")):
            seite.insert_text((x, 60 + 14 * j), zelle, fontsize=8, fontname="helv")
    doc.save(pfad)
    doc.close()
    doc = fitz.open(pfad)
    vorbereitung = seitenmodell.dokument_vorbereiten(doc)
    return seitenmodell.dokument_aufbauen(vorbereitung.get("dokument") or doc, pfad, vorbereitung=vorbereitung)


def test_bestandsliste_namensspalten_und_ortsspalte(tmp_path):
    dok = _liste_pdf(tmp_path / "liste.pdf", _LISTE, [40, 70, 150, 230, 290, 330, 430])
    werte = set(_treffer(dok, "struktur.tabelle"))
    # Datenbank-Spaltennamen "VN_PLZ"/"VN_ORT": das Feld steht hinten; Ort-Zellen ganz (Abkürzungen, "AN DER")
    assert {("namen", "FREITAG"), ("namen", "NUR"), ("namen", "GUENDOGDU"), ("plzort", "66386"),
            ("plzort", "66606"), ("plzort", "ST. WENDEL"), ("plzort", "LAUF A.D.PEGNITZ")} <= werte
    assert not any(t in ("RIESTER", "KFZ", "UNF", "PHV", "BU") for _, t in werte)


def test_kopfzeile_der_bestandsliste_liefert_keine_kopfzellen_als_wert(tmp_path):
    dok = _liste_pdf(tmp_path / "liste.pdf", _LISTE, [40, 70, 150, 230, 290, 330, 430])
    texte = {t for _, t in _treffer(dok, "struktur.etikett_wert")}
    assert not texte & {"NACHNAME", "VORN.", "GEB.DAT.", "VN_PLZ", "VN_ORT", "SP.", "NR."}


# ----------------------------------------------------------------------
# Ausgefüllte Formularzeilen in Versalien sind keine Kopfzeilen (Review-Befunde 1 und 7): eine Zelle "NAME: KOCH"
# trägt einen Wert, ein Versalwort ohne Punkt ("KOCH", "ZOLT") ist kein Spaltenkürzel, ein Kürzel rechts neben einem
# Personen-Feldnamen ("NAME ⇥⇥ LI") ist dessen Wert – Textebene und OCR, drei und mehr Zellen, kurze Werte
# ----------------------------------------------------------------------
_FORMZEILEN = [
    ("NAME: KOCH\t\tVORNAME: UWE\t\tORT: BONN", {"KOCH", "UWE", "BONN"}),
    ("NAME: ZWIRGLMAIER\t\tVORNAME: QUIRIN\t\tGEBURTSORT: PFAFFENHOFEN", {"ZWIRGLMAIER", "QUIRIN", "PFAFFENHOFEN"}),
    ("NACHNAME: OSTERTAG\t\tGEBURTSNAME: HOLZAPFEL\t\tVORNAME: WENZEL", {"OSTERTAG", "HOLZAPFEL", "WENZEL"}),
    ("NAME\t\tZOLT\t\tVORNAME\t\tILKA\t\tORT\t\tPRÜM", {"ZOLT", "ILKA", "PRÜM"}),
    ("NAME: OYELARAN\t\tVORNAME: ADEBAYO\t\tGEBURTSNAME: OKAFOR", {"OYELARAN", "ADEBAYO", "OKAFOR"}),
    ("NAME: TRAN\t\tVORNAME: EVA\t\tGEBURTSNAME: HEITMANN\t\tORT: KIEL", {"TRAN", "EVA", "HEITMANN", "KIEL"}),
    ("NAME\t\tKOCH\t\tVORNAME\t\tANNA\t\tORT\t\tKIEL", {"KOCH", "ANNA", "KIEL"}),
    ("NAME\t\tLI\t\tVORNAME\t\tYU\t\tGEBURTSNAME\t\tWU", {"LI", "YU", "WU"}),
]


@pytest.mark.parametrize("ebene", ["text", "ocr"])
@pytest.mark.parametrize("zeile, werte", _FORMZEILEN)
def test_formularzeile_in_versalien_ist_keine_kopfzeile(zeile, werte, ebene):
    dok = seitenmodell.dokument_aus_text(zeile) if ebene == "text" else _ocr_dok([zeile])
    gefunden = {t for _, t in _treffer(dok, "struktur.etikett_wert")}
    assert werte <= gefunden, (ebene, zeile, gefunden)


def test_rohwert_einer_formularzeile_in_versalien_auf_ocr():
    """Buchstabensalat hinter Feldnamen (Druckbuchstaben, Kästchen): der Rohwert-Pfad liest auch Zeilen mit drei
    Feld-Wert-Zellen."""
    dok = _ocr_dok(["NAME: REN RER\t\tVORNAME: ERNEST EI\t\tGEBURTSNAME: QXLTEMANN"])
    gefunden = " ".join(t for _, t in _treffer(dok, "struktur.etikett_wert"))
    assert "REN" in gefunden and "ERNEST" in gefunden and "QXLTEMANN" in gefunden


def test_formularzeile_auf_der_textebene_mit_breiten_zellen(tmp_path):
    """Wie im Befund: Textebenen-PDF, Zellen 180 pt auseinander, dazu Zeilen mit Kunden-Nr., Geburtsdatum und
    Telefon – die Personenzeile liefert alle drei Werte."""
    pfad = tmp_path / "form.pdf"
    doc = fitz.open()
    seite = doc.new_page(width=595, height=842)
    for j, zellen in enumerate([["NAME: BRANDSTETTER", "VORNAME: WENZEL", "LAND: DEUTSCHLAND"],
                                ["KUNDEN-NR.: 4711-0815", "GEB.-DATUM: 03.06.1962", "TELEFON: 0911 123456"]]):
        for i, zelle in enumerate(zellen):
            seite.insert_text((40 + 180 * i, 100 + 16 * j), zelle, fontsize=9, fontname="cour")
    doc.save(pfad)
    doc.close()
    doc = fitz.open(pfad)
    vorbereitung = seitenmodell.dokument_vorbereiten(doc)
    dok = seitenmodell.dokument_aufbauen(vorbereitung.get("dokument") or doc, pfad, vorbereitung=vorbereitung)
    gefunden = set(_treffer(dok, "struktur.etikett_wert"))
    assert {("namen", "BRANDSTETTER"), ("namen", "WENZEL")} <= gefunden


def test_kopfzeile_nur_mit_wertzeile_darunter():
    """Eine Zeile aus Feldnamen ist nur dann Spaltenkopf, wenn darunter Werte in denselben Spalten stehen."""
    kopf = "NAME\t\tVORN.\t\tGEBURTSORT\t\tPLZ"
    for text, erwartet in ((kopf, False), (kopf + "\nMUELLER\t\tHANS\t\tKIEL\t\t24103", True)):
        seite = seitenmodell.dokument_aus_text(text).seiten[0]
        assert st.kopfzeile(seite, st.lage(seite), 0, st.etiketten(seite)) is erwartet, text


def test_unbelegte_namensspalte_bleibt_streng(tmp_path):
    text = ("NAME\t\tSPARTE\t\tBEITRAG\nHausrat\t\tSach\t\t120,00\nUnfall\t\tPerson\t\t80,00\n"
            "Leben\t\tLeben\t\t300,00\nWohngebäude\t\tSach\t\t410,00")
    dok = _liste_pdf(tmp_path / "liste.pdf", text, [40, 160, 280])
    assert not {k for k, _ in _treffer(dok, "struktur.tabelle")} & {"namen"}


# ----------------------------------------------------------------------
# Rohwerte hinter Feldnamen (nur OCR): grobe Gestalt der Kategorie
# ----------------------------------------------------------------------
def test_rohwert_liest_unleserliche_werte_auf_ocr_seiten():
    dok = _ocr_dok(["Versicherungsnummer:\t\tKV I3 5Z O6I8", "Name, Vorname:\t\tMxrkovic Jlena",
                    "Geburtsdatum:\t\t28.1 l 1964"])
    werte = set(_treffer(dok, "struktur.etikett_wert"))
    assert ("vertrag", "KV I3 5Z O6I8") in werte
    assert ("namen", "Mxrkovic Jlena") in werte
    assert ("geburt", "28.1 l 1964") in werte
    # Rohwerte gibt es nur auf OCR-Zeilen: auf der Textebene gelten allein die Wertformen
    dok = seitenmodell.dokument_aus_text("Geburtsdatum:\t\t28.1 l 1964\nName, Vorname:\t\tMxrkovic Jlena")
    quellen = {t.quelle for t in _detektor("struktur.etikett_wert")(dok, Kontext(ALLE, "hoch"))}
    assert not any(q.endswith(".rohwert") for q in quellen)


@pytest.mark.parametrize("zeile", [
    "Facharzt:\t\tfür Innere Medizin",                       # Satzrest
    "Geburtsdatum:\t\tIch kündige daher den",                   # Datum ohne Ziffern
    "Versicherte Person:\t\tGeburtsdatum",                      # Spaltenkopf statt Wert
    "Unser Zeichen:\t\tLB/hh",                                  # Kennung ohne Ziffern
    "Schadenort:\t\tKreuzung Hauptstraße / Kirchenweg",        # Ereignisort, keine Anschrift
    "Surname:\t\t/ Nom",                                        # Übersetzung des Feldnamens
    "Unterschrift:\t\tVersicherungsnehmer",                     # Beschriftung unter der Linie
    "Zeugen:\t\tNamen, Anschriften",                            # Mehrzahl von Feldnamen
])
def test_rohwert_gegenproben(zeile):
    assert _treffer(_ocr_dok([zeile]), "struktur.etikett_wert") == []


def test_rohwert_ueberspringt_fuehrungspunkte():
    dok = _ocr_dok(["Kontoinhaber ...........2...............; Zeidler, Thomas"])
    assert ("namen", "Zeidler, Thomas") in set(_treffer(dok, "struktur.etikett_wert"))


# Review-Befund 12: Gestaltprüfung auch für Orte, Ereignisorte in jeder Wortstellung, Feldname über den Etikett hinaus,
# Feldnummer des nächsten Felds, "Ihrer Wahl"
@pytest.mark.parametrize("zeile", [
    "Ort des Schadens: Parkplatz Rewe-Markt",
    "Ort des Unfalls: Kreuzung Hauptstraße / Kirchenweg",
    "Ort des Ereignisses: Tiefgarage Altstadt",
    "2. Ort (Land, Ort, Straße)\t\t3. Verletzte: nein ja",
    "2. Ort (Land, Ort, Straße)\t\t3 Verletzte",
    "2. Ort der Besichtigung:",
    "2. Ort: Werkstatt Ihrer Wahl",
    "Ort: Parkplatz Rewe-Markt",
    "Werkstatt: Ihrer Wahl",
    "Gutachter: Ihrer Wahl",
    "Rechtsanwalt: Ihrer Wahl",
    "Arzt: Ihres Vertrauens",
    "Sachverständiger: Ihrem Wunsch entsprechend",
    "Ort: 3. Verletzte",
    "Ort: 5. Polizei",
    "PLZ: bitte angeben",
    "Geburtsort: unbekannt verzogen",
])
def test_rohwert_ort_und_formtext_gegenproben(zeile):
    assert _treffer(_ocr_dok([zeile]), "struktur.etikett_wert") == []


@pytest.mark.parametrize("zeile, wert", [
    ("Wohnort: KAUFBEUREN", ("plzort", "KAUFBEUREN")),
    ("Geburtsort: Bad Homburg v. d. Höhe", ("plzort", "Bad Homburg v. d. Höhe")),
    ("Ort: Frankfurt am Main", ("plzort", "Frankfurt am Main")),
    ("PLZ: 87600", ("plzort", "87600")),
    ("Name des Kindes: MAX KOWALSKI", ("namen", "MAX KOWALSKI")),
])
def test_rohwert_ort_und_name_positivkontrollen(zeile, wert):
    assert wert in set(_treffer(_ocr_dok([zeile]), "struktur.etikett_wert"))


@pytest.mark.parametrize("wert, erwartet", [
    ("Frankfurt am Main", True), ("Halle an der Saale", True), ("Freiburg im Breisgau", True),
    ("Bad Homburg v. d. Höhe", True), ("Rothenburg ob der Tauber", True), ("KAUFBEUREN", True),
    ("Werkstatt Ihrer Wahl", False), ("Parkplatz am Rewe-Markt", False), ("der Besichtigung", False),
    ("am Unfallort", False), ("bitte angeben", False), ("an der Ampel", False),
])
def test_rohwert_ort_mit_ortszusatz(wert, erwartet):
    """Ortszusätze ("am", "an der", "im") sind auch Funktionswörter: im Ortsnamen erlaubt, als Satzanfang nicht."""
    assert st._rohwert_passt(wert, "plzort") is erwartet


def test_ganze_ortzelle_ohne_ereignisort():
    from anonymisierer.detektoren import struktur_tabelle as tb
    assert tb._adresse("Parkplatz Rewe-Markt", 0, 20, "Ort") == []
    assert tb._adresse("Tiefgarage Altstadt", 0, 19, "Ort") == []
    assert tb._adresse("Werkstatt Ihrer Wahl", 0, 20, "Ort") == []
    assert tb._adresse("NEUSTADT AN DER WEINSTRASSE", 0, 27, "Ort") == [(0, 27, "plzort", None)]
    assert tb._adresse("ST. WENDEL", 0, 10, "Ort") == [(0, 10, "plzort", None)]


# Review-Befund 14: Straße mit mehreren Leerzeichen zwischen den Wörtern in Anschriftblock und Feldwert
def test_strasse_mit_mehrfach_leerzeichen_im_anschriftblock():
    assert st.strasse_spanne("Hohe   Straße 129", 0, 17) == (0, 17)
    assert st.strasse_spanne("BERLINER   STRASSE 5, 12345 BERLIN", 0, 34) == (0, 20)
    # die Lücke verbindet keine Nachbarzellen ohne Straßenwort
    assert st.strasse_spanne("Kreissparkasse Talheim   SWBPDEZ7", 0, 33) is None
    werte = _text("Herrn\nJonas Becker\nHohe   Straße 129\n50667 Köln", "struktur.adressblock")
    assert ("strasse", "Hohe   Straße 129") in werte
