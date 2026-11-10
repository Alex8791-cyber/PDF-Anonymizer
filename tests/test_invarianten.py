"""Invarianten der Zuverlässigkeitsarchitektur (Vertrag Phase 2, Abschnitt 11 – Pflicht).

Für jedes PDF aus tests/daten und eine Reihe erzeugter Dokumente (Briefe, enge Tabellen in Base14-Schrift,
Ligaturen, Silbentrennung, Formulare mit Kammfeld, Versalien und gemischte Schreibweisen, gedrehte Seiten,
Scans mit /Rotate 90/180/270) gilt nach Analyse + Schwärzung:

  Z1  stellen_nicht_lokalisiert == 0      – jede Stelle der Analyse wird gefunden und geschwärzt
  Z2  reste == []                         – die Selbstkontrolle der AUSGABE (dasselbe Modell, derselbe
                                            Vergleicher, Glyphenrest-Prüfung) findet keinen Fund mehr,
                                            weder ganz noch teilweise
  Z2' unabhängige Nachkontrolle           – der Text jeder geschwärzten Stelle (Textebene) kommt in der
                                            Ausgabe als Ganzwort in keiner Schreibweise mehr vor
"""

import re
import shutil
from collections import Counter
from pathlib import Path

import pytest

import pymupdf as fitz

from anonymisierer.analyse import analysiere_pdf
from anonymisierer.muster import KATEGORIEN
from anonymisierer.ocr import OcrDienst
from anonymisierer.schwaerzung import schwaerze_pdf
from conftest import (_modell_vorhanden, braucht_ocr, schrift_mit_geteilten_glyphen, schrift_mit_zeichen,
                      textebene_angleichen, textebene_fehlt)

DATEN = Path(__file__).parent / "daten"
SCHRIFT_ESZETT = schrift_mit_zeichen("ẞßÄÖÜäöü")   # Linux: DejaVu Sans, Windows: Arial/Segoe UI
STANDARD = {k for k, _, _, _, an in KATEGORIEN if an}
MIT_MODELL = _modell_vorhanden()
AKTIVE = STANDARD if MIT_MODELL else STANDARD - {"namen"}

NAMEN = ["Max Mustermann", "Erika Musterfrau", "Sandra Klein-Hoffmann", "Steffi Hoffmann", "Giovanni Esposito",
         "Monika Groß", "Jean-Pierre Dubois"]


class KeinOcr:
    """Für Textdokumente: OCR darf nicht nötig sein (sonst schlägt der Test laut fehl)."""
    hinweise: list = []

    def woerter(self, pdf_pfad, seite_nr0, dpi=300, clip=None, **_):
        return [], None

    def schliessen(self):
        pass


# ----------------------------------------------------------------------
# Erzeugte Dokumente
# ----------------------------------------------------------------------
def _seite(doc, zeilen, fontsize=10.0, abstand=1.35, fontname="helv", fontfile=None, x=56, y=70, breite=None):
    seite = doc.new_page(width=breite or 595, height=842)
    for z in zeilen:
        if isinstance(z, tuple):
            for xx, t in z:
                seite.insert_text((xx, y), t, fontsize=fontsize, fontname=fontname, fontfile=fontfile)
        elif z:
            seite.insert_text((x, y), z, fontsize=fontsize, fontname=fontname, fontfile=fontfile)
        y += fontsize * abstand
    return seite


def brief(pfad):
    doc = fitz.open()
    _seite(doc, ["Süddeutsche Versicherung AG · Postfach 12 34 · 80331 München", "", "Herrn",
                 "MAX MUSTERMANN", "Hauptstraße 12a", "90402 Nürnberg", "",
                 "Versicherungsschein-Nr.: LV-2024-887766        Kunden-Nr. 4711-0815",
                 "Sehr geehrter Herr Max Mustermann,",
                 "Ihr Antrag vom 01.10.2024 ist eingegangen. Herr Muster-",
                 "mann, geb. 02.09.1983, hat die Erstattung auf das Konto",
                 "IBAN DE89 3704 0044 0532 0130 00 beantragt. Rückfragen unter Tel. 0911 / 123 45 67",
                 "oder max.mustermann@example.de. Zeugin war Frau Sandra Klein-",
                 "Hoffmann, Goethestraße 21, 99423 Weimar.",
                 "Mit freundlichen Grüßen", "i. A. Erika Musterfrau"])
    _seite(doc, ["Seite 2 – Versicherungsschein-Nr.: LV-2024-887766",
                 "Mustermanns Vertrag läuft weiter; Frau Klein-Hoffmann wurde informiert.",
                 "Die IBAN DE89370400440532013000 bleibt hinterlegt."])
    doc.save(pfad)
    doc.close()


def tabelle(pfad):
    """Versichertenliste: 9-pt-Helvetica, 10-pt-Zeilenabstand (Nachbarzeilen berühren sich fast)."""
    doc = fitz.open()
    zeilen = [((56, "Name"), (200, "Vorname"), (320, "Geburtsdatum"), (430, "Beitrag"))]
    personen = [("Mustermann", "Max", "02.09.1983"), ("Musterfrau", "Erika", "15.05.1985"),
                ("Hoffmann", "Steffi", "12.07.1990"), ("Dubois", "Jean-Pierre", "03.03.1995"),
                ("Groß", "Monika", "21.11.1960"), ("Esposito", "Giovanni", "30.07.1988")]
    for nach, vor, geb in personen:
        zeilen.append(((56, nach), (200, vor), (320, geb), (430, "123,45 EUR")))
    _seite(doc, zeilen, fontsize=9, abstand=10 / 9)
    doc.save(pfad)
    doc.close()


LIGATUR_ZEILEN = ["Versicherungsnehmerin: Frau Steﬃ Hoﬀmann", "Ehemann: Herr Raﬀael Pfeiﬀer",
                  "Die Auﬂage ist oﬀen; Steﬃ Hoﬀmann unterschreibt."]
SCHRIFT_LIGATUREN = schrift_mit_zeichen("".join(LIGATUR_ZEILEN))   # Linux: DejaVu Sans, Windows: z. B. Calibri


def ligaturen(pfad):
    doc = fitz.open()
    _seite(doc, LIGATUR_ZEILEN, fontname="F0", fontfile=str(SCHRIFT_LIGATUREN))
    doc.save(pfad)
    doc.close()


def formular(pfad):
    doc = fitz.open()
    seite = _seite(doc, ["Antrag", "", "Name:", "", "Geburtsdatum:", "", "IBAN:", "", "Telefon:"], fontsize=10,
                   abstand=2.2)
    felder = [("name", "Giovanni Esposito", 0), ("geb", "30071988", fitz.PDF_TX_FIELD_IS_COMB),
              ("iban", "DE12 5001 0517 0648 4898 90", 0), ("tel", "0911 2345678", 0)]
    for i, (name, wert, flags) in enumerate(felder):
        y = 70 + 2 * 22 * (i + 1) - 12
        w = fitz.Widget()
        w.field_name, w.field_type, w.rect, w.field_value = name, fitz.PDF_WIDGET_TYPE_TEXT, fitz.Rect(150, y, 400, y + 16), wert
        if flags:
            w.field_flags, w.text_maxlen = flags, len(wert)
        seite.add_widget(w)
    doc.save(pfad)
    doc.close()


def versalien(pfad):
    doc = fitz.open()
    _seite(doc, ["Versicherungsnehmerin: MONIKA GROẞ", "Sehr geehrte Frau Monika Groß,", "Frau GROSS, Herr Groß",
                 "Der Großteil der Beiträge ist groß. JEAN-PIERRE DUBOIS ist Zeuge, Herr Dubois bestätigt."],
           fontname="F0", fontfile=str(SCHRIFT_ESZETT))
    doc.save(pfad)
    doc.close()


def gedrehte_textseite(pfad):
    doc = fitz.open()
    seite = _seite(doc, ["Versicherungsnehmer: Max Mustermann", "IBAN DE89 3704 0044 0532 0130 00",
                         "geb. 02.09.1983, Tel. 0171 2345678"])
    seite.set_rotation(90)
    doc.save(pfad)
    doc.close()


ERZEUGT = {"brief": brief, "tabelle": tabelle, "ligaturen": ligaturen, "formular": formular,
           "versalien": versalien, "gedreht": gedrehte_textseite}


def scan(pfad, rotate):
    vorlage = fitz.open()
    s = vorlage.new_page()
    y = 120
    for z in ("Versicherungsnehmer Max Mustermann", "IBAN DE89 3704 0044 0532 0130 00",
              "Geburtsdatum 02.09.1983 Telefon 0171 2345678", "Mit freundlichen Grüßen"):
        s.insert_text((60, y), z, fontsize=13, fontname="helv")
        y += 24
    pix = s.get_pixmap(matrix=fitz.Matrix(200 / 72, 200 / 72).prerotate(-rotate), colorspace=fitz.csRGB, alpha=False)
    bild = pix.tobytes("jpeg", jpg_quality=80)
    breite, hoehe = pix.width * 72 / 200, pix.height * 72 / 200
    vorlage.close()
    doc = fitz.open()
    p = doc.new_page(width=breite, height=hoehe)
    p.insert_image(p.rect, stream=bild)
    if rotate:
        p.set_rotation(rotate)
    doc.save(pfad)
    doc.close()


# ----------------------------------------------------------------------
# Prüfung
# ----------------------------------------------------------------------
_PLATZHALTER_RE = re.compile(r"\[[A-ZÄÖÜẞ][A-ZÄÖÜẞ\- ]*(?: [A-Z0-9]{1,2})?\]")


def _ganzwort(text: str):
    teile = [re.escape(t) for t in text.split()]
    muster = r"\s+".join(teile)
    if text[:1].isalnum():
        muster = r"(?<![^\W_])" + muster
    if text[-1:].isalnum():
        muster += r"(?![^\W_])"
    return re.compile(muster, re.IGNORECASE)


def invarianten_pruefen(pdf: Path, ocr, immer=()):
    analyse = analysiere_pdf(pdf, AKTIVE, [], list(immer) + ([] if MIT_MODELL else NAMEN), ocr=ocr)
    assert analyse["fehler"] is None, analyse["fehler"]
    funde = analyse["funde"]
    assert funde, f"{pdf.name}: keine Funde"
    erg = schwaerze_pdf(pdf, funde, modell=analyse["modell"], ocr=ocr, ocr_cache=analyse["ocr_cache"],
                        ziel_ordner=pdf.parent / f"aus_{pdf.stem}")
    assert erg["fehler"] is None, erg
    # Z1
    assert erg["stellen_nicht_lokalisiert"] == 0, (pdf.name, erg["warnungen"])
    assert not any(m["code"] == "NICHT_LOKALISIERT" for m in erg["meldungen"]), erg["meldungen"]
    # Z2
    assert erg["reste"] == [], (pdf.name, erg["reste"])
    # Z2': unabhängige Nachkontrolle über die Textebene (OCR-Stellen prüft die Kontroll-OCR in Z2)
    # Textebene angeglichen: Windows-Schriften liefern NBSP statt Leerzeichen und weiche/geschützte Trennstriche
    # statt Bindestrichen – sonst fände die Nachkontrolle "51-633867" in der Ausgabe nie (conftest)
    with fitz.open(erg["ausgabe"]) as aus:
        ausgabe = _PLATZHALTER_RE.sub(" ", textebene_angleichen("\n".join(s.get_text() for s in aus)))
    modell = analyse["modell"]
    # abgewählte Stellen (bewusst ausgelassen: NIE-Liste, mehrdeutig am Satzanfang …) dürfen stehen bleiben
    erlaubt = Counter(" ".join(st["text"].split()).casefold() for f in funde for st in f["stellen"]
                      if not st.get("an", True))
    for f in funde:
        for st in f["stellen"]:
            if not st.get("an", True):
                continue
            seite = modell.seiten[st["seite"]]
            glyphen = seite.glyphen(st["start"], st["ende"])
            if not glyphen or seite.zeichen[glyphen[0]].quelle != "text":
                continue
            text = " ".join(st["text"].split())
            for m in _ganzwort(text).finditer(ausgabe):
                if f["kategorie"] == "namen" and not all(
                        w[0].isupper() for w, s in zip(re.findall(r"[^\W_]+", m.group(0)), re.findall(r"[^\W_]+", text))
                        if s[0].isupper()):
                    continue        # Namen nur großgeschrieben (Vertrag: "klein"/"groß" bleiben)
                if erlaubt[text.casefold()] > 0:
                    erlaubt[text.casefold()] -= 1
                    continue
                raise AssertionError((pdf.name, f["kategorie"], text, m.group(0)))
    return analyse, erg


@pytest.mark.parametrize("name", sorted(p.name for p in DATEN.glob("*.pdf")))
def test_invarianten_testdaten(tmp_path, name):
    pdf = tmp_path / name
    shutil.copy(DATEN / name, pdf)
    invarianten_pruefen(pdf, KeinOcr(), immer=["Mustermann", "Musterfrau"])


@pytest.mark.parametrize("art", sorted(ERZEUGT))
def test_invarianten_erzeugte_dokumente(tmp_path, art):
    if art == "ligaturen" and SCHRIFT_LIGATUREN is None:
        pytest.skip("keine installierte Schrift mit den Ligaturen ﬀ, ﬃ, ﬂ")
    if art == "versalien" and SCHRIFT_ESZETT is None:
        pytest.skip("keine installierte Schrift mit Versal-ß (ẞ)")
    pdf = tmp_path / f"{art}.pdf"
    ERZEUGT[art](pdf)
    analyse, erg = invarianten_pruefen(pdf, KeinOcr())
    if art == "brief":
        texte = {st["text"] for f in analyse["funde"] for st in f["stellen"]}
        assert {"MAX MUSTERMANN", "Max Mustermann", "Mustermanns"} <= texte | {t.split(",")[0] for t in texte}
    if art == "formular":
        assert any(f["kategorie"] == "geburt" and f["text"] == "30071988" for f in analyse["funde"])


@pytest.fixture(scope="module")
def dienst():
    with OcrDienst(prozesse=2) as d:
        yield d


@braucht_ocr
@pytest.mark.parametrize("rotate", [90, 180, 270])
def test_invarianten_scans_mit_rotate(tmp_path, dienst, rotate):
    pdf = tmp_path / f"scan_{rotate}.pdf"
    scan(pdf, rotate)
    analyse, erg = invarianten_pruefen(pdf, dienst, immer=["Max Mustermann"])
    assert analyse["ocr_seiten"] == 1
    kontrolle = dienst.text(erg["ausgabe"], 0)
    for rest in ("Mustermann", "3704", "1983", "2345678"):
        assert rest not in kontrolle, (rotate, rest, kontrolle)


WINDOWS_ZEILEN = ["Versicherungsnehmerin: Frau Noémie\xa0Bonnet",
                  "Kundennummer: 51\xad633867",
                  "Telefon 0421 3498\xad936, Mobil 0171\u20112345678",
                  "E-Mail a.krause@schwarzwald\xadversicherung.de",
                  "IBAN DE89\xa03704\xa00044\xa00532\xa00130\xa000"]
# Vertrag 12.7 ist nur prüfbar, wenn die Textebene NBSP, den sichtbaren weichen Trennstrich und U+2011 als EIGENE
# Zeichen liefert – Schriften, die U+00AD mit U+2010/U+2011 auf eine Glyphe legen (Textebene: U+2011), überspringt
# die Schriftwahl (conftest). Linux: DejaVu Sans; Windows: z. B. Times New Roman (Arial hat kein U+2011) – deren
# Textebene liefert zusätzlich NBSP statt Leerzeichen und U+00AD statt Bindestrichen (gemeinsame Glyphen).
WINDOWS_UNTERSCHEIDBAR = "\xa0\xad\u2011"
SCHRIFT_WINDOWS = schrift_mit_zeichen("".join(WINDOWS_ZEILEN), unterscheidbar=WINDOWS_UNTERSCHEIDBAR)
# wie Arial und Times New Roman des Windows-Runners: Leerzeichen und Bindestrich auf der Glyphe von NBSP bzw. weichem
# Trennstrich – die Textebene liefert NBSP statt JEDEM Leerzeichen und U+00AD statt JEDEM Bindestrich
WINDOWS_TEILUNG = {0x20: 0xA0, 0x2D: 0xAD}


def windows_sonderzeichen(pfad, schrift=None):
    """Vertrag 12.7: Textauslesung wie auf dem Windows-Runner – NBSP statt Leerzeichen, sichtbarer weicher
    Trennstrich (U+00AD) statt Bindestrich, U+2011 in Nummern."""
    doc = fitz.open()
    _seite(doc, WINDOWS_ZEILEN, fontname="F0", fontfile=str(schrift or SCHRIFT_WINDOWS))
    doc.save(pfad)
    doc.close()


@pytest.mark.skipif(SCHRIFT_WINDOWS is None,
                    reason="keine installierte Schrift, deren Textebene NBSP, weichen Trennstrich (U+00AD) und U+2011 "
                           "als eigene Zeichen liefert – Vertrag 12.7 ist hier nicht prüfbar")
@pytest.mark.parametrize("variante", ["installiert", "windows_artig"])
def test_windows_sonderzeichen_werden_erkannt_und_geschwaerzt(tmp_path, variante):
    pdf = tmp_path / "windows.pdf"
    schrift = SCHRIFT_WINDOWS
    if variante == "windows_artig":
        schrift = schrift_mit_geteilten_glyphen(SCHRIFT_WINDOWS, tmp_path / "windows_artig.ttf", WINDOWS_TEILUNG)
    windows_sonderzeichen(pdf, schrift)
    # Testvoraussetzung (sichert die Schriftwahl am echten Testdokument ab): sonst prüfte der Test Vertrag 12.7 nicht
    assert textebene_fehlt(pdf, WINDOWS_UNTERSCHEIDBAR) == "", schrift
    analyse, erg = invarianten_pruefen(pdf, KeinOcr(), immer=["Noémie Bonnet"])
    texte = {" ".join(f["text"].split()) for f in analyse["funde"]}
    for wert in ("Noémie Bonnet", "51-633867", "0421 3498-936", "0171-2345678",
                 "a.krause@schwarzwald-versicherung.de", "DE89 3704 0044 0532 0130 00"):
        assert any(wert in t for t in texte), (wert, texte)
    with fitz.open(erg["ausgabe"]) as aus:
        ausgabe = "\n".join(s.get_text() for s in aus)
    for rest in ("Bonnet", "633867", "3498", "2345678", "krause", "schwarzwald", "3704"):
        assert rest not in ausgabe, (rest, ausgabe)
    assert erg["status"] == "fertig", erg["meldungen"]
