"""Runde 3, Paket „ausgabe-status“: jede Datei bekommt eine bereinigte Ausgabe, EINE Regel für den Status
(jede Meldung der Art „fehler“ und jede leckrelevante Warnung macht die Ausgabe _PRUEFEN oder verhindert sie),
Zuordnungsdatei neben dem Ausgabeordner (M-25), abgeschnittener Text, Beschnitt-Rückfall „Seite als Bild“ (R-08)
und Nebenkanäle (Anhangnamen in Wörtern, Gerätenamen im Titel).
"""

import os
import re
import sys
from pathlib import Path

import pymupdf as fitz
import pytest

from anonymisierer import analyse, dateien, gui, nebenkanaele, schwaerzung
from anonymisierer import gui_attrappen as attrappen
from anonymisierer import seitenmodell as sm
from anonymisierer.analyse import analysiere_pdf
from anonymisierer.schwaerzung import schwaerze_pdf
from test_gui import (_prozesszustand, analysiere, app, dialoge, fake_analyse, pdf_schreiben,  # noqa: F401
                      root, starte_lauf, umgebung)
from test_robustheit_analyse import (NAME, NEUTRAL, STANDARD, Attrappe, bildseite, codes, textseiten,  # noqa: F401
                                     volltext)
from test_seiten_robustheit import (VERSTECKT, _alle_zeichen, _versteckt_lesbar, brief_mit_langem_feld,
                                    tabelle_mit_abgeschnittener_zelle, zyklus_mit_beschnitt)

WURZEL = Path(__file__).resolve().parent.parent
gui_test = pytest.mark.skipif(not os.environ.get("DISPLAY") and sys.platform != "win32",
                              reason="kein Display (DISPLAY nicht gesetzt)")


def fund_mit_stelle(seite, start, ende, text, kategorie="namen", ersatz="[PERSON A]"):
    return {"kategorie": kategorie, "text": text, "ersatz": ersatz,
            "stellen": [{"seite": seite, "start": start, "ende": ende, "an": True, "text": text}]}


# ======================================================================
# 1. Jede lesbare PDF bekommt eine bereinigte Ausgabe
# ======================================================================
def test_datei_ohne_fund_bekommt_bereinigte_ausgabe_fertig(tmp_path):
    """Früher: keine Ausgabe (KEIN_TREFFER) – die Nutzerin hatte nichts hochzuladen und nahm das Original samt Titel,
    Autor und Lesezeichen. Jetzt: eine bereinigte Ausgabe, „fertig“, ohne Grund."""
    pdf = textseiten(tmp_path / "avb.pdf", NEUTRAL)
    with fitz.open(pdf) as doc:
        doc.set_metadata({"title": "Allgemeine Versicherungsbedingungen", "author": "Fachabteilung",
                          "creator": "Microsoft Word - AVB.docx"})
        doc.set_toc([[1, "§ 1 Gegenstand der Versicherung", 1]])
        doc.saveIncr()
    e = analysiere_pdf(pdf, STANDARD, [], [])
    assert e["funde"] == [] and e["fehler"] is None
    s = schwaerze_pdf(pdf, e["funde"], ocr=Attrappe(), modell=e["modell"], nebenkanaele=e["nebenkanaele"])
    assert s["fehler"] is None and s["ausgabe"] == tmp_path / "anonymisiert" / "anonym_01.pdf"
    assert s["status"] == "fertig" and s["pruefen_gruende"] == [] and s["treffer"] == 0
    assert "NICHTS_GESCHWAERZT" in codes(s) and "KEIN_TREFFER" not in codes(s)
    with fitz.open(s["ausgabe"]) as aus:
        assert not aus.get_toc() and not any((aus.metadata or {}).get(k) for k in ("title", "author", "creator"))
    assert all(z in volltext(s["ausgabe"]) for z in NEUTRAL)
    assert schwaerzung.zuordnung_pfad(tmp_path / "anonymisiert").read_text(encoding="utf-8").startswith(
        "anonym_01.pdf  <-  avb.pdf  (")


def test_unlesbarer_scan_ohne_fund_ist_pruefen_mit_grund(tmp_path):
    """Ein Scan, aus dem die OCR nichts liest, aber Tinte trägt: bereinigte Ausgabe, _PRUEFEN mit Grund – nie
    „fertig“ (die Seite wurde nicht geprüft)."""
    pdf = bildseite(tmp_path / "scan.pdf", tinte=True)
    s = schwaerze_pdf(pdf, [], ocr=Attrappe())
    assert s["ausgabe"] is not None and s["status"] == "pruefen" and s["ausgabe"].name.endswith("_PRUEFEN.pdf")
    assert any("Seite 1" in g for g in s["pruefen_gruende"]), s["pruefen_gruende"]


def test_nicht_lokalisierte_angehakte_funde_machen_pruefen_und_stehen_im_grund(tmp_path):
    """Entscheidung Runde 3: ein angehakter Fund, der sich nicht finden lässt (Datei inzwischen geändert), steht
    vermutlich noch in der Datei. Statt KEINER Ausgabe (dann ginge das Original mit allen versteckten Teilen weiter)
    entsteht eine bereinigte Ausgabe als _PRUEFEN, deren Grund die nicht gefundenen Texte nennt – in der Vorschau lässt
    sich dort gezielt nachschwärzen."""
    pdf = textseiten(tmp_path / "geaendert.pdf", NEUTRAL)
    funde = [fund_mit_stelle(0, 0, 14, "Erika Musterfrau"), fund_mit_stelle(0, 20, 30, "Hauptstraße 12", "strasse",
                                                                             "[ADRESSE]")]
    s = schwaerze_pdf(pdf, funde, ocr=Attrappe())
    assert s["ausgabe"] is not None and s["status"] == "pruefen" and s["treffer"] == 0
    assert s["stellen_nicht_lokalisiert"] == 2
    grund = next(g for g in s["pruefen_gruende"] if "nicht lokalisiert" in g)
    assert "»Erika Musterfrau«" in grund and "»Hauptstraße 12«" in grund
    assert any(m["art"] == "fehler" and m["code"] == "NICHT_LOKALISIERT" for m in s["meldungen"])


@pytest.mark.parametrize("art", ["kein_pdf", "kaputt", "kennwort"])
def test_nicht_bearbeitbare_datei_ohne_ausgabe_mit_fehler_meldung(tmp_path, art):
    pfad = tmp_path / "datei.pdf"
    if art == "kein_pdf":
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40), False)
        pix.clear_with(200)
        pfad.write_bytes(pix.tobytes("png"))
    elif art == "kaputt":
        pfad.write_bytes(b"kein pdf")
    else:
        doc = fitz.open()
        doc.new_page().insert_text((50, 72), "Geheim")
        doc.save(pfad, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="x", owner_pw="x")
        doc.close()
    s = schwaerze_pdf(pfad, [], ocr=Attrappe())
    assert s["ausgabe"] is None and s["status"] is None and s["fehler"]
    fehler = [m for m in s["meldungen"] if m["art"] == "fehler"]
    assert len(fehler) == 1 and fehler[0]["code"] in analyse.FEHLER_CODES
    assert analyse.FEHLER_CODES[fehler[0]["code"]][0] is False          # „keine Ausgabe“ laut Tabelle
    assert not (tmp_path / "anonymisiert").exists()


def test_seite_weder_schwaerz_noch_renderbar_ergibt_keine_ausgabe(tmp_path, monkeypatch):
    pfad = tmp_path / "zyklus.pdf"
    zyklus_mit_beschnitt("selbst", True).save(pfad)

    def kaputt(*a, **k):
        raise RuntimeError("Rendern unmöglich")
    monkeypatch.setattr(schwaerzung._bilder, "seite_als_bild_schwaerzen", kaputt)
    s = schwaerze_pdf(pfad, [], ocr=Attrappe(), ziel_ordner=tmp_path / "aus")
    assert s["ausgabe"] is None and "keine Ausgabe" in s["fehler"]
    assert [m["code"] for m in s["meldungen"] if m["art"] == "fehler"] == ["SEITE_NICHT_SCHWAERZBAR"]
    assert not list(tmp_path.rglob("anonym_*.pdf")) and not list(tmp_path.rglob(".anonym_tmp_*"))


# ======================================================================
# 4. EINE Regel: Meldungs-Codes vollständig eingeordnet, „fehler“ nie „fertig“
# ======================================================================
_MELDUNG_RES = (
    re.compile(r"\"(warnung|fehler|hinweis)\",\s*\"([A-Z_]+)\""),
    re.compile(r"\"art\":\s*\"(warnung|fehler|hinweis)\",\s*\"code\":\s*\"([A-Z_]+)\""),
    re.compile(r"art=\"(warnung|fehler|hinweis)\",\s*code=\"([A-Z_]+)\""),
)
_OHNE_AUSGABE_RE = re.compile(r"ohne_ausgabe\(\"([A-Z_]+)\"")


def _gemeldete_codes() -> set:
    """(Art, Code) aller Meldungen, die das Programm im Quelltext erzeugt."""
    gefunden = set()
    for datei in sorted((WURZEL / "anonymisierer").rglob("*.py")):
        text = datei.read_text(encoding="utf-8")
        for muster in _MELDUNG_RES:
            gefunden |= {(m.group(1), m.group(2)) for m in muster.finditer(text)}
        gefunden |= {("fehler", m.group(1)) for m in _OHNE_AUSGABE_RE.finditer(text)}
    return gefunden


def test_jeder_gemeldete_code_steht_mit_begruendung_in_der_tabelle():
    gemeldet = _gemeldete_codes()
    assert len(gemeldet) >= 40 and ("fehler", "KEIN_PDF") in gemeldet and ("warnung", "TEXTEBENE_UNLESBAR") in gemeldet
    fehlt = []
    for art, code in sorted(gemeldet):
        tabelle = {"fehler": analyse.FEHLER_CODES, "warnung": analyse.WARNUNGS_CODES}.get(art)
        if tabelle is None:
            if code not in analyse.HINWEIS_CODES:
                fehlt.append((art, code))
        elif code not in tabelle:
            fehlt.append((art, code))
    # Codes, die die Oberfläche aus Texten älterer Engines ableitet (gui_attrappen), gelten als Warnung
    for _, code in attrappen._TEXT_CODES:
        if code not in analyse.WARNUNGS_CODES and code not in analyse.HINWEIS_CODES:
            fehlt.append(("abgeleitet", code))
    assert not fehlt, f"Codes ohne Einordnung in analyse.WARNUNGS_CODES/FEHLER_CODES/HINWEIS_CODES: {fehlt}"
    for tabelle in (analyse.WARNUNGS_CODES, analyse.FEHLER_CODES):
        for code, (wert, grund) in tabelle.items():
            assert isinstance(wert, bool) and len(str(grund).strip()) >= 20, code


def test_klassifizierung_der_entschiedenen_codes():
    leck = analyse.ist_leckrelevant
    assert leck({"art": "warnung", "code": "TEXTEBENE_UNLESBAR"})            # Textebene bleibt, ungeprüft
    assert not leck({"art": "warnung", "code": "TEXT_ABGESCHNITTEN"})        # entfernt und nachgeprüft
    assert leck({"art": "warnung", "code": "TEXT_ABGESCHNITTEN_REST"})
    assert leck({"art": "warnung", "code": "NAMEN_INAKTIV"}) and leck({"art": "warnung", "code": "KEIN_TEXT"})
    assert leck({"art": "warnung", "code": "NEUER_CODE_OHNE_TABELLE"})       # unbekannt: im Zweifel prüfen
    assert leck({"art": "fehler", "code": "NEUER_FEHLER"})
    assert not leck({"art": "hinweis", "code": "OCR_UNPLAUSIBEL"}) and not leck({"art": "warnung", "code": "OCR_GELESEN"})
    assert schwaerzung.LECKRELEVANTE_CODES is analyse.LECKRELEVANTE_CODES       # eine Tabelle, nicht zwei


def _mit_meldung(monkeypatch, meldung: dict):
    """Lässt den Aufbau des frischen Modells in der Schwärzung zusätzlich `meldung` erzeugen – so, wie OCR oder
    Seitenmodell es täten."""
    echt = sm.dokument_aufbauen

    def aufbauen(*args, meldungen=None, **kwargs):
        dok = echt(*args, meldungen=meldungen, **kwargs)
        if meldungen is not None:
            meldungen.append(dict(meldung))
        return dok
    monkeypatch.setattr(sm, "dokument_aufbauen", aufbauen)


@pytest.mark.parametrize("code", sorted(c for c, (leck, _) in analyse.WARNUNGS_CODES.items() if leck)
                         + ["UNBEKANNTE_WARNUNG"])
def test_jede_leckrelevante_warnung_macht_die_ausgabe_pruefen(tmp_path, monkeypatch, code):
    pdf = textseiten(tmp_path / "a.pdf", NEUTRAL)
    _mit_meldung(monkeypatch, {"art": "warnung", "code": code, "text": f"Seite 1: Testmeldung {code}", "seite": 0})
    s = schwaerze_pdf(pdf, [], ocr=Attrappe())
    assert s["ausgabe"] is not None and s["status"] == "pruefen", (code, s["pruefen_gruende"])
    assert s["pruefen_gruende"] and all(g.strip() for g in s["pruefen_gruende"])


@pytest.mark.parametrize("code", sorted(c for c, (leck, _) in analyse.WARNUNGS_CODES.items() if not leck))
def test_nicht_leckrelevante_warnung_laesst_fertig(tmp_path, monkeypatch, code):
    pdf = textseiten(tmp_path / "a.pdf", NEUTRAL)
    _mit_meldung(monkeypatch, {"art": "warnung", "code": code, "text": f"Testmeldung {code}", "seite": None})
    s = schwaerze_pdf(pdf, [], ocr=Attrappe())
    assert s["status"] == "fertig", (code, s["pruefen_gruende"])


@pytest.mark.parametrize("code", sorted(analyse.FEHLER_CODES) + ["UNBEKANNTER_FEHLER"])
def test_jede_fehler_meldung_endet_nie_mit_fertig(tmp_path, monkeypatch, code):
    """Zentrale Regel: eine Meldung der Art „fehler“ – gleich welcher Code, auch künftige – macht eine geschriebene
    Ausgabe _PRUEFEN (mit Grund); die Codes „ohne Ausgabe“ prüfen die Tests oben auch einzeln."""
    pdf = textseiten(tmp_path / "a.pdf", NEUTRAL)
    _mit_meldung(monkeypatch, {"art": "fehler", "code": code, "text": f"Testfehler {code}", "seite": None})
    s = schwaerze_pdf(pdf, [], ocr=Attrappe())
    assert s["status"] != "fertig"
    if s["ausgabe"] is not None:
        assert s["status"] == "pruefen" and s["pruefen_gruende"]


def test_leckrelevante_meldungen_der_analyse_wirken_ueber_das_modell(tmp_path, monkeypatch):
    """Meldungen, die die Analyse erst bei der Erkennung erzeugt (NAMEN_INAKTIV: Sprachmodell fehlt), standen früher
    nicht am Modell – die Ausgabe hieß „fertig“, obwohl keine Namen gesucht wurden."""
    pdf = textseiten(tmp_path / "a.pdf", NEUTRAL)
    monkeypatch.setattr(analyse, "lade_ner", lambda: None)
    e = analysiere_pdf(pdf, STANDARD, [], [])
    assert "NAMEN_INAKTIV" in [m["code"] for m in e["modell"].leckrelevant]
    s = schwaerze_pdf(pdf, e["funde"], ocr=Attrappe(), modell=e["modell"], nebenkanaele=e["nebenkanaele"])
    assert s["status"] == "pruefen" and any("Namenserkennung inaktiv" in g for g in s["pruefen_gruende"])


def test_leere_datei_ohne_tinte_ist_trotz_kein_text_fertig(tmp_path):
    """KEIN_TEXT ist leckrelevant – außer die Datei hat gar keine Tinte (leere Seiten): dort steht nichts."""
    pdf = tmp_path / "leer.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(pdf)
    e = analysiere_pdf(pdf, STANDARD, [], [])
    assert "KEIN_TEXT" in codes(e)
    s = schwaerze_pdf(pdf, e["funde"], ocr=Attrappe(), modell=e["modell"])
    assert s["status"] == "fertig", s["pruefen_gruende"]


def test_fehlende_restrisiko_pruefung_ist_nie_still(tmp_path, monkeypatch):
    pdf = textseiten(tmp_path / "a.pdf", NEUTRAL)
    monkeypatch.setattr(schwaerzung, "_restrisiko", None)
    s = schwaerze_pdf(pdf, [], ocr=Attrappe())
    assert s["status"] == "pruefen" and "Restrisiko-Prüfung ausgefallen" in s["pruefen_gruende"]


def test_teilweise_entfernte_nebenkanaele_machen_pruefen(tmp_path, monkeypatch):
    pdf = textseiten(tmp_path / "a.pdf", NEUTRAL)
    echt = nebenkanaele.nebenkanaele_entfernen

    def mit_fehler(doc, zaehler=None, rueckfall=None):
        z = echt(doc, zaehler, rueckfall=rueckfall)
        z.setdefault("fehler", []).append("Bild 7: defekt")
        return z
    monkeypatch.setattr(nebenkanaele, "nebenkanaele_entfernen", mit_fehler)
    s = schwaerze_pdf(pdf, [], ocr=Attrappe())
    assert s["status"] == "pruefen" and any("nur teilweise entfernt" in g for g in s["pruefen_gruende"])


# ======================================================================
# 3. Abgeschnittener Text (TEXT_ABGESCHNITTEN)
# ======================================================================
@pytest.mark.parametrize("bauen", [brief_mit_langem_feld, lambda: tabelle_mit_abgeschnittener_zelle(False),
                                   tabelle_mit_abgeschnittener_zelle], ids=["feld", "zelle", "zelle_mit_nachbar"])
def test_abgeschnittener_text_ohne_fund_verlaesst_die_ausgabe_nicht(tmp_path, bauen):
    """Mit Runde 3 bekommt auch eine Datei ohne Fund eine Ausgabe – der abgeschnittene Teil („IBAN DE02 …“), den
    Textprogramme lesen würden, ist darin nicht mehr enthalten (Zeichenspur, Text ohne Beschneidung, Rohdaten)."""
    pfad = tmp_path / "abgeschnitten.pdf"
    bauen().save(pfad)
    assert "2020 51" in _alle_zeichen(pfad)
    s = schwaerze_pdf(pfad, [], ocr=Attrappe())
    assert s["ausgabe"] is not None and s["fehler"] is None
    assert "2020" not in _alle_zeichen(s["ausgabe"]) and "DE02" not in _alle_zeichen(s["ausgabe"])
    with fitz.open(s["ausgabe"]) as aus:
        ohne_beschnitt = "".join(p.get_text(flags=sm.TEXT_FLAGS & ~fitz.TEXT_MEDIABOX_CLIP) for p in aus)
        roh = b"".join(aus.xref_stream(x) or b"" for x in range(1, aus.xref_length()) if aus.xref_is_stream(x))
    assert "2020" not in ohne_beschnitt and b"2020 51" not in roh
    assert "TEXT_ABGESCHNITTEN_REST" not in codes(s)


def test_bleibt_abgeschnittener_text_stehen_wird_die_ausgabe_pruefen(tmp_path, monkeypatch):
    """Nachprüfung in der gespeicherten Ausgabe: scheitert das Entfernen still, ist die Ausgabe _PRUEFEN."""
    pfad = tmp_path / "abgeschnitten.pdf"
    tabelle_mit_abgeschnittener_zelle(False).save(pfad)

    def nichts_entfernen(lauf, nr, seite, m):
        lauf.abgeschnitten_seiten.add(nr)
        return seite, False
    monkeypatch.setattr(schwaerzung, "_abgeschnittenen_text_entfernen", nichts_entfernen)
    s = schwaerze_pdf(pfad, [], ocr=Attrappe())
    assert "TEXT_ABGESCHNITTEN_REST" in codes(s) and s["status"] == "pruefen"
    assert any("abgeschnittener" in g for g in s["pruefen_gruende"])


# ======================================================================
# 5. R-08: Beschnitt-Entfernung mit Rückfall „Seite als Bild“
# ======================================================================
@pytest.mark.parametrize("art", ["selbst", "paar", "tief"])
def test_beschnitt_entfernen_faellt_bei_zyklischem_xobjekt_auf_bild_zurueck(tmp_path, art):
    """nebenkanaele.beschnitt_entfernen rief apply_redactions ohne Rückfall: bei zyklischen Form-XObjects und Inhalt
    außerhalb der CropBox brach es ab („exception stack overflow“), nebenkanaele_entfernen gleich mit."""
    doc = zyklus_mit_beschnitt(art, True)
    assert nebenkanaele.beschnitt_entfernen(doc, doc[1]) == nebenkanaele.SEITE_ALS_BILD
    pfad = tmp_path / "bild.pdf"
    doc.save(pfad)
    assert not _versteckt_lesbar(pfad)
    # über nebenkanaele_entfernen: nie eine Ausnahme, die Seite wird gemeldet, der Rückfall des Aufrufers greift
    doc = zyklus_mit_beschnitt(art, True)
    aufrufe = []

    def rueckfall(seite, fehler):
        aufrufe.append((seite.number, type(fehler).__name__))
        nebenkanaele._bilder.seite_als_bild_schwaerzen(doc, seite, [], [])
    z = nebenkanaele.nebenkanaele_entfernen(doc, rueckfall=rueckfall)
    assert z["seite_als_bild"] == [1] and [nr for nr, _ in aufrufe] == [1]
    assert "Bild neu erzeugt" in nebenkanaele.nebenkanal_hinweis(z)
    pfad2 = tmp_path / "bild2.pdf"
    doc.save(pfad2, garbage=4)
    assert not _versteckt_lesbar(pfad2)
    with fitz.open(pfad2) as aus:
        assert "Anlage: Fotodokumentation" not in aus[1].get_text() and aus[1].get_images()


def test_zyklische_seite_ohne_fund_bekommt_ausgabe_ohne_verstecktes(tmp_path):
    """Nur die zyklische Seite, kein Fund: früher keine Ausgabe (das Original mit dem Text außerhalb der CropBox ging
    weiter); jetzt eine bereinigte Ausgabe, die Seite als Bild."""
    doc = zyklus_mit_beschnitt("selbst", True)
    doc.select([1])
    pfad = tmp_path / "zyklus.pdf"
    doc.save(pfad)
    assert _versteckt_lesbar(pfad)
    s = schwaerze_pdf(pfad, [], ocr=Attrappe())
    assert s["ausgabe"] is not None and s["fehler"] is None and "SEITE_ALS_BILD" in codes(s)
    assert not _versteckt_lesbar(s["ausgabe"]) and "Musterfrau" in VERSTECKT


def test_beschnitt_entfernen_ohne_zyklus_unveraendert(tmp_path):
    doc = fitz.open()
    s = doc.new_page()
    s.insert_text((50, 80), "Sichtbar", fontsize=11)
    s.insert_text((50, 800), "Unsichtbar " + NAME, fontsize=11)
    s.set_cropbox(fitz.Rect(0, 0, 595, 700))
    assert nebenkanaele.beschnitt_entfernen(doc, s) is True
    assert nebenkanaele.beschnitt_entfernen(doc, s) is False
    s.set_cropbox(s.mediabox)
    assert "Sichtbar" in s.get_text() and NAME not in s.get_text()


# ======================================================================
# 6. Nebenkanäle: Anhangnamen in Wörtern, Geräte- und Programmnamen im Titel
# ======================================================================
@pytest.mark.parametrize("name,woerter", [
    ("Ausweis_Mustermann.txt", "Ausweis Mustermann"),
    ("PIB_Hausrat_Mustermann_Max.docx", "PIB Hausrat Mustermann Max"),
    ("Antrag.Schmidt.Peter.pdf", "Antrag Schmidt Peter"),
    ("erika-musterfrau-ausweis.jpg", "erika musterfrau ausweis"),
    ("AntragThomasSchaefer.pdf", "Antrag Thomas Schaefer"),
    ("Antrag Hausrat.pdf", "Antrag Hausrat"),
    ("Antrag Hausrat", None),
])
def test_dateiname_als_woerter(name, woerter):
    assert nebenkanaele.dateiname_als_woerter(name) == woerter


def _dok_mit(titel=None, anhang=None):
    d = fitz.open()
    d.new_page().insert_text((72, 72), "Allgemeine Bedingungen ohne Personenbezug.")
    if titel:
        d.set_metadata({"title": titel})
    if anhang:
        d.embfile_add(anhang, b"keine Angaben", filename=anhang)
    return fitz.open("pdf", d.tobytes())


@pytest.mark.parametrize("anhang", ["Ausweis_Mustermann.txt", "PIB_Hausrat_Mustermann_Max.docx",
                                    "Antrag.Schmidt.Peter.pdf", "mustermann_max.txt", "erika-musterfrau-ausweis.jpg",
                                    "Vollmacht.Weber.Iris.pdf"])
def test_namen_in_anhangnamen_mit_trennern_werden_erkannt(anhang):
    e = analyse.nebenkanaele_pruefen(_dok_mit(anhang=anhang), STANDARD, meldungen=[], warnungen=[])
    assert e["personenbezug"] and e["anhaenge"] == 1, anhang


@pytest.mark.parametrize("anhang", ["Rechnung_2024.pdf", "AVB_Hausrat_2023.pdf", "Police-Hausrat.pdf", "IMG_1234.JPG",
                                    "bedingungen.kfz.haftpflicht.pdf", "Datenschutz_Hinweise.pdf"])
def test_anhangnamen_ohne_namen_bleiben_ohne_personenbezug(anhang):
    e = analyse.nebenkanaele_pruefen(_dok_mit(anhang=anhang), STANDARD, meldungen=[], warnungen=[])
    assert not e["personenbezug"], anhang


@pytest.mark.parametrize("wert,geraet,rest", [
    ("RICOH MP C3004", "RICOH MP C3004", ""),
    ("Kyocera ECOSYS M2540dn - Scan Mustermann", "Kyocera ECOSYS M2540dn", "Scan Mustermann"),
    ("RICOH MP C3004 MAX MUSTERMANN", "RICOH MP C3004", "MAX MUSTERMANN"),
    ("Canon iR-ADV C5535 PDF", "Canon iR-ADV C5535", "PDF"),
    ("Sharp Thomas", None, "Sharp Thomas"),
    ("Iris Weber", None, "Iris Weber"),
])
def test_geraetename_abtrennen(wert, geraet, rest):
    assert nebenkanaele.geraetename_abtrennen(wert) == (geraet, rest)


@pytest.mark.parametrize("titel", ["RICOH MP C3004", "Kyocera ECOSYS M2540dn", "Canon iR-ADV C5535 PDF",
                                   "SHARP MX-M3071", "OKI MC573", "RICOH IM C3000", "CamScanner 05-03-2024 10.11",
                                   "Microsoft Word - Vorlage Kündigung.docx", "Microsoft Word - Dokument1",
                                   "Scan_20240503_101112", "WhatsApp Image 2024-05-03 at 10.11.12"])
def test_geraete_und_programmnamen_im_titel_sind_kein_personenbezug(titel):
    e = analyse.nebenkanaele_pruefen(_dok_mit(titel=titel), STANDARD, meldungen=[], warnungen=[])
    assert not e["personenbezug"], titel


@pytest.mark.parametrize("titel", ["RICOH MP C3004 - Max Mustermann", "Scan Max Mustermann",
                                   "KONICA MINOLTA bizhub C300i Kopie Meier", "Microsoft Word - Kündigung Mustermann.docx",
                                   "Canon iR-ADV C5535 - Antrag Schmidt", "Scan 0171 2345678"])
def test_echte_namen_im_titel_werden_weiter_erkannt(titel):
    e = analyse.nebenkanaele_pruefen(_dok_mit(titel=titel), STANDARD, meldungen=[], warnungen=[])
    assert e["personenbezug"], titel


def test_saubere_datei_mit_geraetenamen_im_titel_ist_fertig(tmp_path):
    """Befund: ein Gerätename im Titel machte eine sonst saubere Ausgabe _PRUEFEN (Personenbezug „nicht
    auszuschließen“, Grund NUR_NEBENKANAL)."""
    pdf = textseiten(tmp_path / "scan_titel.pdf", NEUTRAL)
    with fitz.open(pdf) as doc:
        doc.set_metadata({"title": "RICOH MP C3004", "author": "KONICA MINOLTA bizhub C300i"})
        doc.saveIncr()
    e = analysiere_pdf(pdf, STANDARD, [], [])
    assert not e["nebenkanaele"]["personenbezug"]
    s = schwaerze_pdf(pdf, e["funde"], ocr=Attrappe(), modell=e["modell"], nebenkanaele=e["nebenkanaele"])
    assert s["status"] == "fertig", s["pruefen_gruende"]


# ======================================================================
# 2. M-25: Zuordnungsdatei neben dem Ausgabeordner – alle Abläufe
# ======================================================================
def test_zuordnungsdateien_sind_systemdateien(tmp_path):
    for name in ("_zuordnung.txt", "_zuordnung_anonymisiert.txt", "_zuordnung_KI-Upload.txt", "_ZUORDNUNG_x.TXT"):
        assert dateien.ist_systemdatei(name), name
    assert not dateien.ist_systemdatei("zuordnung.txt") and not dateien.ist_systemdatei("_zuordnung.pdf")
    # im Ordner der Originale: der Ordner-Scan übergeht sie ohne Meldung „keine PDF“
    pdf = textseiten(tmp_path / "Antrag.pdf", NEUTRAL)
    s = schwaerze_pdf(pdf, [], ocr=Attrappe())
    assert schwaerzung.zuordnung_pfad(s["ausgabe"].parent) == tmp_path / "_zuordnung_anonymisiert.txt"
    bericht = dateien.sammle_pdfs_bericht([tmp_path])
    assert bericht["pdfs"] == [pdf] and not bericht["keine_pdf"] and not bericht["uebersprungen"]


def test_alte_zuordnung_im_ausgabeordner_wird_beim_schwaerzen_uebernommen(tmp_path):
    pdf = textseiten(tmp_path / "Antrag_Mustermann.pdf", NEUTRAL)
    ziel = tmp_path / "anonymisiert"
    ziel.mkdir()
    for alt in ("anonym_01.pdf", "anonym_02.pdf"):                  # Ausgaben früherer Läufe
        (ziel / alt).write_bytes(b"%PDF-1.4 alt")
    # ältere Programmversion: Zuordnung IM Ausgabeordner (ohne Zeilenende); neuere: schon daneben
    (ziel / "_zuordnung.txt").write_text("anonym_01.pdf  <-  Alt.pdf  (2026-01-01 10:00)", encoding="utf-8")
    neu = tmp_path / "_zuordnung_anonymisiert.txt"
    neu.write_text("anonym_02.pdf  <-  Mittel.pdf  (2026-02-01 10:00)\n", encoding="utf-8")
    s = schwaerze_pdf(pdf, [], ocr=Attrappe(), freigabe_erforderlich=True)
    assert s["ausgabe"].name == "anonym_03_PRUEFEN.pdf" and not (ziel / "_zuordnung.txt").exists()
    zeilen = neu.read_text(encoding="utf-8").splitlines()
    assert [z.split()[0] for z in zeilen] == ["anonym_01.pdf", "anonym_02.pdf", "anonym_03_PRUEFEN.pdf"]
    assert sorted(p.name for p in ziel.iterdir()) == ["anonym_01.pdf", "anonym_02.pdf", "anonym_03_PRUEFEN.pdf"]
    freigegeben = schwaerzung.freigeben(s["ausgabe"])
    assert neu.read_text(encoding="utf-8").splitlines()[2].startswith("anonym_03.pdf  <-  Antrag_Mustermann.pdf")
    schwaerzung.verwerfen(freigegeben)
    assert [z.split()[0] for z in neu.read_text(encoding="utf-8").splitlines()] == ["anonym_01.pdf", "anonym_02.pdf"]


def test_zuordnung_neben_eigenem_zielordner(tmp_path):
    (tmp_path / "in").mkdir()
    pdf = textseiten(tmp_path / "in" / "Antrag.pdf", NEUTRAL)
    ziel = tmp_path / "KI-Upload"
    s = schwaerze_pdf(pdf, [], ocr=Attrappe(), ziel_ordner=ziel)
    assert s["ausgabe"].parent == ziel and (tmp_path / "_zuordnung_KI-Upload.txt").exists()
    assert sorted(p.name for p in ziel.iterdir()) == [s["ausgabe"].name]


def test_attrappe_fuehrt_die_zuordnung_neben_dem_ordner_nach(tmp_path):
    ordner = tmp_path / "anonymisiert"
    ordner.mkdir()
    (ordner / "anonym_01_PRUEFEN.pdf").write_bytes(b"%PDF x")
    neben = tmp_path / "_zuordnung_anonymisiert.txt"
    neben.write_text("anonym_01_PRUEFEN.pdf  <-  A.pdf  (2026-01-01 10:00)\n", encoding="utf-8")
    neu = attrappen.freigeben(ordner / "anonym_01_PRUEFEN.pdf")
    assert neben.read_text(encoding="utf-8") == f"{neu.name}  <-  A.pdf  (2026-01-01 10:00)\n"
    attrappen.verwerfen(neu)
    assert neben.read_text(encoding="utf-8") == ""


# ======================================================================
# GUI: Schwärzen-Knopf, Auftrag, Status und Abschlussdialog (echte Engine)
# ======================================================================
def _gui_dateien(ordner: Path) -> dict:
    """Die drei Fälle der Ende-zu-Ende-Prüfung: ohne Fund, mit abgeschnittenem Text, nur Nebenkanal."""
    ordner.mkdir(parents=True, exist_ok=True)
    ohne = textseiten(ordner / "AVB_Hausrat.pdf", NEUTRAL)
    abgeschnitten = ordner / "Antrag_Feld.pdf"
    tabelle_mit_abgeschnittener_zelle(False).save(abgeschnitten)
    nur_neben = textseiten(ordner / "Deckblatt.pdf", NEUTRAL[:2])
    with fitz.open(nur_neben) as doc:
        doc.set_metadata({"title": f"Antrag {NAME}", "author": NAME})
        doc.set_toc([[1, f"Unterlagen {NAME}", 1]])
        doc.saveIncr()
    return {"ohne": ohne, "abgeschnitten": abgeschnitten, "nur_neben": nur_neben}


@gui_test
def test_gui_ohne_fund_abgeschnitten_und_nebenkanal_ende_zu_ende(app, umgebung, dialoge):
    """Echte Engine in der echten Oberfläche: drei Dateien ohne angehakten Fund bekommen je eine Ausgabe; der Knopf
    ist an, „OHNE Ausgabedatei“ erscheint nicht, der Status nennt den Grund, die Zuordnung liegt neben dem
    Ausgabeordner und der abgeschnittene Text ist nicht in der Ausgabe."""
    tmp = umgebung["tmp"]
    d = _gui_dateien(tmp / "Kunde")
    app.freigabe_var.set(False)
    app._pdfs_hinzufuegen([str(p) for p in d.values()])
    starte_lauf(app, app.analysieren, timeout=180)
    assert all(not app.analyse_ergebnisse[p].get("fehler") for p in d.values())
    assert app.analyse_ergebnisse[d["ohne"]]["funde"] == [] and app.analyse_ergebnisse[d["nur_neben"]]["funde"] == []
    app.alle_setzen("aus")                                 # nichts angehakt lassen (auch nicht im Brief)
    assert app._angehakte_funde() == 0 and str(app.start_knopf.cget("state")) == "normal"
    dialoge.antwort = False
    starte_lauf(app, app.schwaerzen, timeout=180)
    art, titel, text = app.letzter_dialog
    assert titel == "Schwärzung abgeschlossen" and "3 von 3 Datei(en) geschrieben" in text, text
    assert "OHNE Ausgabedatei" not in text and "Hochladen nur aus dem Ausgabeordner" in text
    aus = {name: app.ausgaben[pdf] for name, pdf in d.items()}
    assert all(e["pfad"] is not None and e["pfad"].exists() for e in aus.values()), aus
    assert aus["ohne"]["status"] == "fertig" and aus["ohne"]["grund"] == "keine personenbezogenen Daten gefunden"
    assert app.baum.set(str(d["ohne"]), "text").startswith("✔ fertig: anonym_")
    assert aus["nur_neben"]["status"] == "pruefen" and "außerhalb der Seiten" in aus["nur_neben"]["grund"]
    assert "2020 51" not in _alle_zeichen(aus["abgeschnitten"]["pfad"])
    ordner = tmp / "Kunde" / "anonymisiert"
    assert not (ordner / "_zuordnung.txt").exists() and schwaerzung.zuordnung_pfad(ordner).exists()
    assert sorted(p.suffix for p in ordner.iterdir()) == [".pdf", ".pdf", ".pdf"]
    with fitz.open(aus["nur_neben"]["pfad"]) as doc:
        assert not doc.get_toc() and NAME not in str(doc.metadata) and b"Mustermann" not in doc.tobytes(garbage=0)


@gui_test
def test_gui_nicht_analysierbare_datei_steht_unter_ohne_ausgabedatei(app, umgebung, monkeypatch, dialoge):
    """„OHNE Ausgabedatei“ nur für Dateien, die wirklich nicht bearbeitet werden konnten."""
    tmp = umgebung["tmp"]
    gut = pdf_schreiben(tmp / "gut.pdf")
    kaputt = pdf_schreiben(tmp / "kaputt.pdf")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({}, fehler_fuer={"kaputt.pdf": ValueError("defekt")}))
    analysiere(app, [gut, kaputt])
    assert app._auftrag(kaputt) is None and app._auftrag(gut)["ohne_haken"] is True
    assert str(app.start_knopf.cget("state")) == "normal"
    dialoge.antwort = False
    starte_lauf(app, app.schwaerzen, timeout=60)
    text = app.letzter_dialog[2]
    assert "1 von 2 Datei(en) geschrieben" in text
    block = text.split("OHNE Ausgabedatei", 1)[1].split("\n\n", 1)[0]
    assert "kaputt.pdf: nicht analysierbar" in block and "gut.pdf" not in block
    assert app.ausgaben[gut]["pfad"].exists()


@gui_test
def test_gui_warnt_deutlich_wenn_die_zuordnung_im_ausgabeordner_landet(app, umgebung, dialoge):
    tmp = umgebung["tmp"]
    pdf = textseiten(tmp / "Antrag.pdf", NEUTRAL)
    (tmp / "_zuordnung_anonymisiert.txt").mkdir()            # neben dem Ausgabeordner kann keine Datei entstehen
    app.freigabe_var.set(False)
    analysiere(app, [pdf])
    dialoge.antwort = False
    starte_lauf(app, app.schwaerzen, timeout=60)
    text = app.letzter_dialog[2]
    assert "ACHTUNG Zuordnungsdatei" in text and "NICHT mit auswählen" in text
    assert app.letzter_dialog[0] in ("askyesno", "warning")
