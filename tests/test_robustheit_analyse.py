"""Robustheit der Analyse und Status der Ausgabe (Runde 2, Paket „analyse-status“):

R-01  Bild/Webseite mit der Endung .pdf: klare Meldung statt Absturz (Analyse, Schwärzung, Vorschau)
R-04  Personendaten nur in Nebenkanälen (Metadaten, Lesezeichen, Anhänge, Portfolio, XFA): Meldung NEBENKANAL_FUND,
      Ergebnis „nebenkanaele“ und eine bereinigte Ausgabe auch ohne Fund auf den Seiten
R-07  Leckrelevante Gründe (Scan kaum lesbar, Texterkennung unplausibel, XFA, Schlüsselwort ohne Fund …) -> _PRUEFEN
R-11  Beschädigte, von MuPDF reparierte Datei: DATEI_REPARIERT, _PRUEFEN, gültiger Seitenbaum in der Ausgabe
Dazu: Firmenanschriften abgewählt angeboten, leicht verlesene Vorkommen auf OCR-Seiten, Namen in anderen Stellen,
Formularfeld „Titel“ ohne eigene Person.
Alle Eingaben werden mit PyMuPDF erzeugt (keine weiteren Bibliotheken)."""

import json
import re
import struct
import subprocess
import sys
import zipfile
from io import BytesIO
from pathlib import Path

import pymupdf as fitz
import pytest

from anonymisierer import analyse, nebenkanaele, schwaerzung, vorschau
from anonymisierer import ocr as ocr_modul
from anonymisierer.analyse import analysiere_pdf, analysiere_text
from anonymisierer.muster import KATEGORIEN
from anonymisierer.schwaerzung import schwaerze_pdf

WURZEL = Path(__file__).resolve().parent.parent
ALLE = {k for k, *_ in KATEGORIEN}
STANDARD = {k for k, _, _, _, an in KATEGORIEN if an}
NAME = "Max Mustermann"
IBAN = "DE89 3704 0044 0532 0130 00"
NEUTRAL = ["Allgemeine Versicherungsbedingungen (AVB) - Auszug", "Versichert sind Schäden an den im",
           "Versicherungsschein bezeichneten Sachen.", "Der erste Beitrag ist nach Ablauf von zwei Wochen fällig."]


# ----------------------------------------------------------------------
# Hilfen
# ----------------------------------------------------------------------
class Attrappe:
    """OCR-Attrappe: feste Wörter je Seite (x0, y0, x1, y1, Text)."""

    def __init__(self, woerter_je_seite=None):
        self.woerter_je_seite = woerter_je_seite or {}
        self.hinweise = []

    def woerter(self, pdf_pfad, seite_nr0, dpi=300, clip=None, **_):
        return list(self.woerter_je_seite.get(seite_nr0, [])), None

    def abbrechen(self):
        pass

    def schliessen(self):
        pass


def woerter_aus_zeilen(zeilen, x0=50.0, y0=70.0):
    aus = []
    for i, z in enumerate(zeilen):
        x, y = x0, y0 + 16 * i
        for w in z.split():
            breite = 6.0 * len(w)
            aus.append((x, y, x + breite, y + 12, w))
            x += breite + 5
    return aus


def textseiten(pfad, *seiten):
    doc = fitz.open()
    for zeilen in seiten:
        seite = doc.new_page()
        for i, z in enumerate(zeilen):
            seite.insert_text((50, 72 + 16 * i), z, fontsize=11, fontname="helv")
    doc.save(pfad)
    doc.close()
    return Path(pfad)


def bildseite(pfad, tinte=True):
    """Eine Seite, die nur aus einem Bild besteht (für die OCR-Attrappe ein „Scan“); mit Tinte: dunkle Fläche."""
    doc = fitz.open()
    seite = doc.new_page()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 280), False)
    pix.clear_with(255)
    if tinte:
        pix.set_rect(fitz.IRect(20, 30, 180, 90), (0, 0, 0))
    seite.insert_image(seite.rect, pixmap=pix)
    doc.save(pfad)
    doc.close()
    return Path(pfad)


def codes(ergebnis):
    return [m["code"] for m in ergebnis.get("meldungen") or []]


def volltext(pfad):
    with fitz.open(pfad) as doc:
        return "\n".join(s.get_text() for s in doc)


@pytest.fixture
def scan_modus(monkeypatch):
    """Jede Seite gilt als Scan (OCR der ganzen Seite)."""
    monkeypatch.setattr(ocr_modul, "ocr_noetig", lambda seite, meldungen=None: "seite", raising=False)


# ----------------------------------------------------------------------
# R-01: Keine PDF (Bild, Webseite) mit der Endung .pdf
# ----------------------------------------------------------------------
def _tiff(breite=8, hoehe=8) -> bytes:
    """Kleinstes unkomprimiertes Graustufen-TIFF (wie ein Fax), von Hand gebaut."""
    pixel = bytes([0x80]) * (breite * hoehe)
    eintraege = [(256, 3, breite), (257, 3, hoehe), (258, 3, 8), (259, 3, 1), (262, 3, 1), (273, 4, 0),
                 (277, 3, 1), (278, 3, hoehe), (279, 4, len(pixel))]
    daten_ab = 8 + 2 + 12 * len(eintraege) + 4
    ifd = struct.pack("<H", len(eintraege))
    for tag, typ, wert in eintraege:
        wert = daten_ab if tag == 273 else wert
        ifd += struct.pack("<HHIHH", tag, typ, 1, wert, 0) if typ == 3 else struct.pack("<HHII", tag, typ, 1, wert)
    return b"II*\x00" + struct.pack("<I", 8) + ifd + struct.pack("<I", 0) + pixel


def _nicht_pdfs(ordner: Path) -> dict:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 40), False)
    pix.clear_with(200)
    dateien = {
        "foto.pdf": pix.tobytes("jpeg"),
        "scan.pdf": pix.tobytes("png"),
        "portal.pdf": b"<!DOCTYPE html><html><head><title>Fehler</title></head><body><h1>Sitzung abgelaufen"
                      b"</h1></body></html>",
        "fax.pdf": _tiff(),
    }
    for name, daten in dateien.items():
        (ordner / name).write_bytes(daten)
    return {name: ordner / name for name in dateien}


def test_keine_pdf_wird_ohne_absturz_abgewiesen(tmp_path):
    """Gutachten R-01: PyMuPDF öffnet Bilder und HTML mit der Endung .pdf als Nicht-PDF; der erste Zugriff auf
    seite.xref beendete den ganzen Prozess (Speicherzugriffsfehler). In einem eigenen Prozess geprüft, damit ein
    Rückfall den Testlauf nicht mitreißt."""
    dateien = _nicht_pdfs(tmp_path)
    programm = (
        "import json, sys\n"
        f"sys.path.insert(0, {str(WURZEL)!r})\n"
        "from anonymisierer.analyse import analysiere_pdf\n"
        "from anonymisierer.schwaerzung import schwaerze_pdf\n"
        "aus = {}\n"
        "for p in sys.argv[1:]:\n"
        "    a = analysiere_pdf(p, {'iban', 'email'}, [], [])\n"
        "    s = schwaerze_pdf(p, [{'kategorie': 'namen', 'text': 'Max', 'ersatz': '[PERSON A]'}])\n"
        "    aus[p] = [a['fehler'], [m['code'] for m in a['meldungen']], s['fehler'], s['ausgabe'] is None,\n"
        "              [m['code'] for m in s['meldungen']]]\n"
        "print(json.dumps(aus))\n")
    lauf = subprocess.run([sys.executable, "-c", programm, *map(str, dateien.values())], capture_output=True,
                          text=True, timeout=300)
    assert lauf.returncode == 0, lauf.stderr[-2000:]
    ergebnis = json.loads(lauf.stdout.strip().splitlines()[-1])
    for name, pfad in dateien.items():
        a_fehler, a_codes, s_fehler, ohne_ausgabe, s_codes = ergebnis[str(pfad)]
        try:
            fitz.open(pfad).close()               # nur öffnen, keine Seite anfassen
        except Exception:                         # ältere PyMuPDF-Versionen öffnen HTML gar nicht
            assert a_fehler.startswith("Konnte nicht geöffnet werden") and s_fehler and ohne_ausgabe, name
            continue
        assert a_fehler and f"»{name}« ist keine PDF, sondern" in a_fehler, (name, a_fehler)
        assert "KEIN_PDF" in a_codes and "KEIN_PDF" in s_codes and s_fehler == a_fehler and ohne_ausgabe
    assert "ein Bild (JPEG)" in ergebnis[str(dateien["foto.pdf"])][0]
    assert "ein Bild (PNG)" in ergebnis[str(dateien["scan.pdf"])][0]
    assert "ein Bild (TIFF)" in ergebnis[str(dateien["fax.pdf"])][0]
    portal = ergebnis[str(dateien["portal.pdf"])][0]
    assert "eine Webseite (HTML)" in portal or portal.startswith("Konnte nicht geöffnet werden")
    assert not list(tmp_path.rglob("anonym_*.pdf"))


def test_keine_pdf_meldung_ist_verstaendlich_und_wird_nicht_umgedeutet(tmp_path):
    """Die Meldung erklärt in einfachem Deutsch, was zu tun ist; die Oberfläche übersetzt sie nicht in die
    allgemeine „beschädigt, leer oder umbenannt“-Meldung (keines ihrer Suchwörter kommt vor)."""
    pfad = _nicht_pdfs(tmp_path)["foto.pdf"]
    with fitz.open(pfad) as doc:
        text = analyse.keine_pdf_meldung(doc, pfad)
    assert text.startswith("»foto.pdf« ist keine PDF, sondern ein Bild (JPEG)")
    assert "Microsoft Print to PDF" in text
    assert not any(w in text.lower() for w in ("as type pdf", "not a pdf", "format error", "no objects found"))
    with fitz.open(textseiten(tmp_path / "echt.pdf", ["Hallo"])) as doc:
        assert analyse.keine_pdf_meldung(doc, tmp_path / "echt.pdf") is None


def test_vorschau_weist_keine_pdf_mit_meldung_ab(tmp_path):
    pfad = _nicht_pdfs(tmp_path)["foto.pdf"]
    with pytest.raises(ValueError, match="ist keine PDF, sondern ein Bild"):
        vorschau.seite_bild(pfad, 0, 1.0)
    vorschau.zwischenspeicher_leeren()


def test_echte_pdf_unveraendert_analysiert(tmp_path):
    pdf = textseiten(tmp_path / "brief.pdf", [f"Versicherungsnehmer: {NAME}", f"IBAN {IBAN}"])
    e = analysiere_pdf(pdf, STANDARD, [], [])
    assert e["fehler"] is None and "KEIN_PDF" not in codes(e)
    assert ("iban", IBAN) in [(f["kategorie"], f["text"]) for f in e["funde"]]


# ----------------------------------------------------------------------
# R-04: Personendaten nur in Nebenkanälen
# ----------------------------------------------------------------------
def _nur_metadaten_pdf(pfad):
    doc = fitz.open()
    seite = doc.new_page()
    for i, z in enumerate(NEUTRAL):
        seite.insert_text((50, 72 + 16 * i), z, fontsize=11, fontname="helv")
    doc.set_metadata({"title": f"Kündigung {NAME}", "author": NAME, "subject": f"IBAN {IBAN}",
                      "producer": "Microsoft® Word für Microsoft 365"})
    doc.set_toc([[1, f"Antrag {NAME}", 1], [1, "Bedingungen", 1]])
    doc.embfile_add("Ausweis.txt", f"Personalausweis {NAME}".encode(), filename="Ausweis.txt")
    doc.save(pfad)
    doc.close()
    return Path(pfad)


def test_nebenkanaele_ohne_seitenfund_werden_gemeldet_und_bereinigt(tmp_path):
    """Gutachten R-04: Name und IBAN nur in Titel, Autor, Betreff, Lesezeichen und Anhang. Früher: 0 Funde, keine
    Meldung, keine Ausgabe – das Original ging samt Metadaten weiter."""
    pdf = _nur_metadaten_pdf(tmp_path / "nur_metadaten.pdf")
    e = analysiere_pdf(pdf, STANDARD, [], [])
    assert e["fehler"] is None and e["funde"] == []
    assert e["nebenkanaele"] == {"metadaten": 3, "lesezeichen": 1, "anhaenge": 1, "xfa": False,
                                 "personenbezug": True}
    meldung = next(m for m in e["meldungen"] if m["code"] == "NEBENKANAL_FUND")
    assert meldung["art"] == "warnung" and meldung["text"] in e["warnungen"]
    assert "Dateieigenschaften" in meldung["text"] and "1 Lesezeichen" in meldung["text"]
    assert "angehängten Datei" in meldung["text"] and "entfernt" in meldung["text"]
    assert NAME not in meldung["text"] and "Ausweis" not in meldung["text"]      # Meldung ohne Personendaten
    s = schwaerze_pdf(pdf, e["funde"], ocr=Attrappe(), nebenkanaele=e["nebenkanaele"])
    assert s["fehler"] is None and s["ausgabe"] is not None and s["ausgabe"].name == "anonym_01.pdf"
    assert s["treffer"] == 0 and s["status"] == "fertig"
    with fitz.open(s["ausgabe"]) as aus:
        assert not aus.get_toc() and aus.embfile_count() == 0
        assert not any((aus.metadata or {}).get(k) for k in ("title", "author", "subject"))
        roh = aus.tobytes(garbage=0)
    assert b"Mustermann" not in roh and b"DE89" not in roh
    assert NEUTRAL[0] in volltext(s["ausgabe"])


def test_schwaerzung_prueft_nebenkanaele_selbst_wenn_kein_ergebnis_uebergeben(tmp_path):
    """Aufrufer ohne Analyse-Ergebnis (alte Schnittstelle, Benchmark): schwaerze_pdf erkennt die Nebenkanäle selbst."""
    pdf = _nur_metadaten_pdf(tmp_path / "selbst.pdf")
    s = schwaerze_pdf(pdf, [], ocr=Attrappe())
    assert s["ausgabe"] is not None and s["ausgabe"].exists()
    # abgewählte Seitenfunde (Fehlalarm abgewählt) + Nebenkanäle: trotzdem eine bereinigte Ausgabe
    fund = {"kategorie": "namen", "text": "Versichert", "ersatz": "[PERSON A]",
            "stellen": [{"seite": 0, "start": 0, "ende": 10, "an": False, "text": "Allgemeine"}]}
    s2 = schwaerze_pdf(pdf, [fund], ocr=Attrappe())
    assert s2["ausgabe"] is not None and s2["treffer"] == 0


def test_ohne_personendaten_in_nebenkanaelen_bleibt_es_bei_keiner_ausgabe(tmp_path):
    pdf = textseiten(tmp_path / "avb.pdf", NEUTRAL)
    with fitz.open(pdf) as doc:
        doc.set_metadata({"title": "Allgemeine Versicherungsbedingungen", "producer": "Adobe PDF Library 15.0",
                          "creator": "Microsoft Word - AVB.docx"})
        doc.set_toc([[1, "§ 1 Gegenstand der Versicherung", 1]])
        doc.saveIncr()
    e = analysiere_pdf(pdf, STANDARD, [], [])
    assert e["nebenkanaele"] == analyse.NEBENKANAELE_LEER and "NEBENKANAL_FUND" not in codes(e)
    s = schwaerze_pdf(pdf, e["funde"], ocr=Attrappe())
    assert s["ausgabe"] is None and "KEIN_TREFFER" in codes(s)
    assert not (tmp_path / "anonymisiert").exists()


def test_portfolio_mit_pdf_und_text_anhaengen(tmp_path):
    """Portfolio: neutrales Deckblatt, Kundendaten nur in angehängter PDF (rekursiv gelesen) und Textdatei."""
    innen = fitz.open()
    s = innen.new_page()
    s.insert_text((50, 72), f"Antrag von {NAME}, IBAN {IBAN}", fontsize=11, fontname="helv")
    innen_bytes = innen.tobytes()
    innen.close()
    doc = fitz.open()
    doc.new_page().insert_text((50, 72), "Dieses PDF-Portfolio enthält mehrere Dateien.", fontsize=11)
    doc.embfile_add("Anlage1.pdf", innen_bytes, filename="Anlage1.pdf", desc="Anlage")
    doc.embfile_add("Bank.txt", f"Kontoinhaber {NAME}\nIBAN {IBAN}\n".encode(), filename="Bank.txt")
    doc.xref_set_key(doc.pdf_catalog(), "Collection", "<</Type/Collection>>")
    pdf = tmp_path / "portfolio.pdf"
    doc.save(pdf)
    doc.close()
    e = analysiere_pdf(pdf, STANDARD, [], [])
    assert e["funde"] == [] and e["nebenkanaele"]["anhaenge"] == 2 and e["nebenkanaele"]["personenbezug"]
    s = schwaerze_pdf(pdf, [], ocr=Attrappe(), nebenkanaele=e["nebenkanaele"])
    with fitz.open(s["ausgabe"]) as aus:
        assert aus.embfile_count() == 0


def test_xfa_daten_werden_geprueft_und_ausgabe_ist_pruefen(tmp_path):
    """XFA-Formular: die Daten stehen nur im datasets-Strom. Sie werden geprüft (NEBENKANAL_FUND, xfa True), die
    Ausgabe entfernt sie und ist _PRUEFEN (Inhalt des Formulars nicht prüfbar, R-07)."""
    doc = fitz.open()
    doc.new_page().insert_text((50, 72), "Bitte warten ...", fontsize=11)
    datasets = (f"<xfa:datasets xmlns:xfa=\"http://www.xfa.org/schema/xfa-data/1.0/\"><xfa:data><antrag><name>{NAME}"
                f"</name><iban>{IBAN}</iban></antrag></xfa:data></xfa:datasets>").encode()
    xrefs = []
    for inhalt in (b"<xdp:xdp xmlns:xdp=\"http://ns.adobe.com/xdp/\">", b"<template/>", datasets, b"</xdp:xdp>"):
        x = doc.get_new_xref()
        doc.update_object(x, "<<>>")
        doc.update_stream(x, inhalt)
        xrefs.append(x)
    feld = doc.get_new_xref()
    doc.update_object(feld, f"<</Fields[]/XFA[(xdp:xdp){xrefs[0]} 0 R(template){xrefs[1]} 0 R(datasets)"
                            f"{xrefs[2]} 0 R(</xdp:xdp>){xrefs[3]} 0 R]>>")
    doc.xref_set_key(doc.pdf_catalog(), "AcroForm", f"{feld} 0 R")
    pdf = tmp_path / "xfa.pdf"
    doc.save(pdf)
    doc.close()
    e = analysiere_pdf(pdf, STANDARD, [], [])
    assert e["nebenkanaele"]["xfa"] is True and e["nebenkanaele"]["personenbezug"]
    assert {"NEBENKANAL_FUND", "XFA"} <= set(codes(e))
    s = schwaerze_pdf(pdf, e["funde"], ocr=Attrappe(), nebenkanaele=e["nebenkanaele"])
    assert s["status"] == "pruefen" and s["ausgabe"].name == "anonym_01_PRUEFEN.pdf"
    assert any("XFA" in g for g in s["pruefen_gruende"])
    with fitz.open(s["ausgabe"]) as aus:
        assert b"Mustermann" not in aus.tobytes(garbage=0)


def test_nicht_lesbarer_anhang_gilt_als_personenbezogen(tmp_path):
    """Ein angehängtes Foto lässt sich ohne OCR nicht prüfen: lieber bereinigen als das Original weitergeben."""
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 30, 30), False)
    pix.clear_with(128)
    pdf = textseiten(tmp_path / "foto_anhang.pdf", NEUTRAL)
    with fitz.open(pdf) as doc:
        doc.embfile_add("IMG_2041.jpg", pix.tobytes("jpeg"), filename="IMG_2041.jpg")
        doc.saveIncr()
    e = analysiere_pdf(pdf, STANDARD, [], [])
    assert e["nebenkanaele"]["anhaenge"] == 1 and e["nebenkanaele"]["personenbezug"]
    text = next(m["text"] for m in e["meldungen"] if m["code"] == "NEBENKANAL_FUND")
    assert "nicht geprüft werden (Bild (JPEG))" in text


def test_ausfall_der_nebenkanalpruefung_gilt_als_nicht_auszuschliessen(tmp_path, monkeypatch):
    """Fällt die Prüfung aus (kaputte Regel), bricht die Analyse nicht ab: die Nebenkanäle gelten als nicht
    geprüft – lieber eine bereinigte Ausgabe als das Original."""
    def kaputt(*args, **kwargs):
        raise RuntimeError("Regel kaputt")
    monkeypatch.setattr(analyse, "_nebenkanal_funde", kaputt)
    e = analysiere_pdf(_nur_metadaten_pdf(tmp_path / "m.pdf"), STANDARD, [], [])
    assert e["fehler"] is None and e["nebenkanaele"]["personenbezug"] is True
    text = next(m["text"] for m in e["meldungen"] if m["code"] == "NEBENKANAL_FUND")
    assert "nicht geprüft werden" in text and "ließen sich nicht lesen" in text


def test_nie_liste_gilt_auch_fuer_nebenkanaele(tmp_path):
    """Die eigene Maklerin als Autorin (NIE-Liste) ist kein Personenbezug des Kunden."""
    pdf = textseiten(tmp_path / "autorin.pdf", NEUTRAL)
    with fitz.open(pdf) as doc:
        doc.set_metadata({"author": "Sabine Kraus"})
        doc.saveIncr()
    assert analysiere_pdf(pdf, STANDARD, [], [])["nebenkanaele"]["personenbezug"] is True
    assert analysiere_pdf(pdf, STANDARD, ["Sabine Kraus"], [])["nebenkanaele"]["personenbezug"] is False


# ----------------------------------------------------------------------
# R-11: Beschädigte (abgeschnittene) Datei
# ----------------------------------------------------------------------
def _abgeschnitten(tmp_path, anteil=0.6):
    voll = tmp_path / "voll.pdf"
    doc = fitz.open()
    for nr in range(3):
        seite = doc.new_page()
        for i in range(25):
            seite.insert_text((50, 60 + 25 * i), f"Seite {nr + 1} Zeile {i}: {NAME}, IBAN {IBAN}", fontsize=10,
                              fontname="helv")
    doc.save(voll, garbage=0, deflate=False)
    doc.close()
    daten = voll.read_bytes()
    kaputt = tmp_path / "abgeschnitten.pdf"
    kaputt.write_bytes(daten[:int(len(daten) * anteil)])
    return kaputt


def test_reparierte_datei_wird_gemeldet_und_pruefen(tmp_path):
    pdf = _abgeschnitten(tmp_path)
    with fitz.open(pdf) as doc:
        if not doc.is_repaired:
            pytest.skip("MuPDF hat diese Datei ohne Reparatur geöffnet")
    e = analysiere_pdf(pdf, STANDARD, [], [])
    meldung = next(m for m in e["meldungen"] if m["code"] == "DATEI_REPARIERT")
    assert meldung["art"] == "warnung" and meldung["text"].startswith(analyse.TEXT_REPARIERT)
    assert any(m["code"] == "DATEI_REPARIERT" for m in e["modell"].leckrelevant)
    s = schwaerze_pdf(pdf, e["funde"], ocr=Attrappe(), modell=e["modell"])
    assert s["status"] == "pruefen" and "_PRUEFEN" in s["ausgabe"].name
    assert "DATEI_REPARIERT" in codes(s) and any("beschädigt" in g for g in s["pruefen_gruende"])
    # Die Ausgabe hat einen gültigen Seitenbaum: jede Seite ist ein /Page-Objekt
    with fitz.open(s["ausgabe"]) as aus:
        assert not aus.is_repaired
        wurzel = int(aus.xref_get_key(aus.pdf_catalog(), "Pages")[1].split()[0])
        kinder = [int(x) for x in re.findall(r"(\d+) 0 R", aus.xref_get_key(wurzel, "Kids")[1])]
        assert kinder and all(aus.xref_get_key(x, "Type")[1] == "/Page" for x in kinder)
        assert "Mustermann" not in "".join(seite.get_text() for seite in aus)


def test_gesunde_datei_ist_nicht_repariert(tmp_path):
    pdf = textseiten(tmp_path / "gesund.pdf", [f"Versicherungsnehmer: {NAME}"])
    e = analysiere_pdf(pdf, STANDARD, [], [])
    assert "DATEI_REPARIERT" not in codes(e)
    s = schwaerze_pdf(pdf, e["funde"], ocr=Attrappe(), modell=e["modell"])
    assert s["status"] == "fertig" and s["pruefen_gruende"] == []


# ----------------------------------------------------------------------
# R-07: leckrelevante Gründe -> _PRUEFEN
# ----------------------------------------------------------------------
def test_kaum_lesbare_scanseite_macht_pruefen(tmp_path, scan_modus):
    """Gutachten R-07: Die Analyse warnte „kaum lesbar“, die Ausgabe hieß trotzdem „fertig“. Jetzt: _PRUEFEN mit Grund
    – auch ohne das Modell der Analyse (Benchmark, alte Aufrufer), die Schwärzung stellt es selbst fest."""
    pdf = bildseite(tmp_path / "fax.pdf")
    dienst = Attrappe({0: woerter_aus_zeilen(["Herrn Max Mustermann", "Hauptstraße 12"])})
    e = analysiere_pdf(pdf, STANDARD, [], [], ocr=dienst)
    assert "KAUM_LESBAR" in codes(e) and e["funde"]
    for modell in (e["modell"], None):
        s = schwaerze_pdf(pdf, e["funde"], ocr=dienst, ocr_cache=e["ocr_cache"], modell=modell,
                          ziel_ordner=tmp_path / ("mit" if modell else "ohne"))
        assert s["status"] == "pruefen" and "_PRUEFEN" in s["ausgabe"].name, s["warnungen"]
        assert "Seite 1: Scan kaum lesbar" in s["pruefen_gruende"]


def test_leere_scanseite_ohne_tinte_ist_kein_grund(tmp_path, scan_modus):
    """Eine leere Rückseite (keine Tinte, keine OCR-Wörter) macht die Ausgabe nicht _PRUEFEN."""
    doc = fitz.open()
    for tinte in (True, False):
        seite = doc.new_page()
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 280), False)
        pix.clear_with(255)
        if tinte:
            pix.set_rect(fitz.IRect(20, 30, 180, 90), (0, 0, 0))
        seite.insert_image(seite.rect, pixmap=pix)
    pdf = tmp_path / "rueckseite.pdf"
    doc.save(pdf)
    doc.close()
    zeilen = [f"Versicherungsnehmer {NAME} wohnhaft in der Hauptstraße 12 in 10115 Berlin",
              "wir bestätigen den Eingang Ihrer Unterlagen und die Änderung Ihres Vertrags zum Monatsende",
              "Mit freundlichen Grüßen Ihre Muster Versicherung AG Abteilung Leistung"]
    dienst = Attrappe({0: woerter_aus_zeilen(zeilen)})
    e = analysiere_pdf(pdf, STANDARD, [], [], ocr=dienst)
    s = schwaerze_pdf(pdf, e["funde"], ocr=dienst, ocr_cache=e["ocr_cache"])
    assert not any(g.startswith("Seite 2") for g in s["pruefen_gruende"]), s["pruefen_gruende"]


def test_unplausible_lesung_wird_grund(tmp_path):
    """Buchstabensalat (verdrehte Seite, Handschrift) nach dem Maß der OCR: Grund für _PRUEFEN."""
    lauf = schwaerzung._Lauf(Path("x.pdf"), [], None, None, None, None, {0: woerter_aus_zeilen(
        ["Xq7 zzvb Kqw pplx vrrt Qwx zkk Brrq Xwq vvz", "kkq Zrx wqq Pvb zzt xxq"])}, Path("."))

    class Seite:
        ocr_modus, ocr_woerter = "seite", 30

    class Modell:
        seiten = [Seite()]
    gruende = schwaerzung._leckrelevant_ermitteln(lauf, Modell(), {})
    assert [g.code for g in gruende] == ["OCR_UNPLAUSIBEL"]


def test_schluesselwort_mit_fremdkategorie_direkt_dahinter_ist_kein_grund(tmp_path, scan_modus):
    """Das Schlüsselwort „IBAN“ mit einem direkt folgenden geschwärzten Wert einer anderen Kategorie (OCR-Verleser in
    der Prüfziffer, als Vertragsnummer erkannt) ist erledigt; beginnt die Schwärzung erst mitten im Wert, bleibt die
    Warnung – und die Ausgabe ist _PRUEFEN (R-07)."""
    pdf = bildseite(tmp_path / "iban.pdf")
    zeilen = ["Versicherungsnehmer Max Mustermann", "IBAN DE89 3/04 0044 0532 0130 00",
              "Wir bestätigen den Eingang Ihrer Unterlagen und die Änderung zum Monatsende.",
              "Bitte prüfen Sie die Angaben und melden Sie Änderungen umgehend schriftlich bei uns."]
    dienst = Attrappe({0: woerter_aus_zeilen(zeilen)})
    e = analysiere_pdf(pdf, STANDARD, [], [], ocr=dienst)
    wert = next(f for f in e["funde"] if f["text"].startswith("DE89 3/04"))
    assert wert["kategorie"] != "iban"                           # Prüfziffer verlesen: keine IBAN
    name = next(f for f in e["funde"] if f["text"] == NAME)
    s = schwaerze_pdf(pdf, [name, wert], ocr=dienst, ocr_cache=e["ocr_cache"], modell=e["modell"],
                      ziel_ordner=tmp_path / "a")
    assert "SCHLUESSELWORT_OHNE_FUND" not in codes(s), s["warnungen"]
    assert not any("Schlüsselwort" in g for g in s["pruefen_gruende"])
    m = e["modell"].seiten[0]
    start = m.text.index("0044 0532")
    spaet = dict(wert, text="0044 0532 0130 00", stellen=[{"seite": 0, "start": start, "ende": start + 17,
                                                           "an": True, "text": m.text[start:start + 17]}])
    s2 = schwaerze_pdf(pdf, [name, spaet], ocr=dienst, ocr_cache=e["ocr_cache"], modell=e["modell"],
                       ziel_ordner=tmp_path / "b")
    assert "SCHLUESSELWORT_OHNE_FUND" in codes(s2) and s2["status"] == "pruefen"
    assert "Seite 1: Schlüsselwort ohne geschwärzten Wert (OCR-Verleser?)" in s2["pruefen_gruende"]
    assert any(m["code"] == "AUSGABE_PRUEFEN" and "Schlüsselwort" in m["text"] for m in s2["meldungen"])


# ----------------------------------------------------------------------
# Firmenanschriften, verlesene Vorkommen, Namen in anderen Stellen, Formularfeld „Titel“
# ----------------------------------------------------------------------
BRIEFKOPF = ("Schmidt Finanz GmbH · Hauptstraße 12a · 60311 Frankfurt am Main\nTel.: 069 123456-0\n\nHerrn\n"
             "Max Mustermann\nBirkenallee 40\n12345 Musterstadt\n\nSehr geehrter Herr Mustermann,\n")


def test_firmenanschrift_wird_abgewaehlt_angeboten():
    funde = analysiere_text(BRIEFKOPF, STANDARD, [], [], profil="hoch")
    firma = [f for f in funde if analyse.QUELLE_FIRMENANSCHRIFT in f["quellen"]]
    assert {f["text"] for f in firma} == {"Hauptstraße 12a", "60311 Frankfurt am Main"}
    for f in firma:
        assert f["hinweis"] == analyse.HINWEIS_FIRMENANSCHRIFT and not any(st["an"] for st in f["stellen"])
    kunde = {f["text"] for f in funde if any(st["an"] for st in f["stellen"])}
    assert {"Birkenallee 40", "12345 Musterstadt"} <= kunde
    # ohne Schutzstufe (reine Text-Schnittstelle) wird nichts angeboten
    assert not any(analyse.QUELLE_FIRMENANSCHRIFT in f["quellen"] for f in analysiere_text(BRIEFKOPF, STANDARD, [], []))


def test_firmenanschrift_ueber_vorhandener_stelle_entfaellt():
    class Dok:
        text = "Muster GmbH, Hauptstraße 12a"
        struktur_vorschlaege = [{"start": 13, "ende": 28, "kategorie": "strasse",
                                 "quelle": "struktur.firmenanschrift", "grund": "vermutlich Firmenanschrift"}]

        def lokal(self, s, e):
            return [(0, s, e)]
    vorhanden = [{"stellen": [{"seite": 0, "start": 20, "ende": 28}]}]
    assert analyse._firmenanschriften(Dok(), vorhanden, {"strasse"}) == []


def test_firmenanschrift_und_titel_wandern_nicht_in_andere_dokumente(tmp_path):
    """Ein abgewählt angebotener Firmenwert (hier eine Telefonnummer, damit die Weitergabe ihn überhaupt sucht) wird
    in anderen Dokumenten nie zur angehakten Stelle und nicht ins Laufwissen übernommen; ein normaler Fund schon."""
    a = textseiten(tmp_path / "a.pdf", ["Zentrale 069 123456-0", "Durchwahl 069 123456-77"])
    b = textseiten(tmp_path / "b.pdf", ["Rückruf an 069 123456-0 oder 069 123456-77 erbeten."])
    ea = analysiere_pdf(a, {"iban"}, [], [], profil="hoch")
    eb = analysiere_pdf(b, {"iban"}, [], [], profil="hoch")
    dok = ea["modell"]

    def fund(text, quellen, an):
        s = dok.text.index(text)
        return {"id": "", "kategorie": "telefon", "anzeige": "Telefon", "text": text, "ersatz": "[TELEFON]",
                "seiten": [1], "anzahl": 1, "kontext": "", "quellen": quellen, "sicherheit": 0.3, "hinweis": None,
                "stellen": [{"seite": 0, "start": s, "ende": s + len(text), "an": an, "text": text}]}
    ea["funde"] = [fund("069 123456-0", [analyse.QUELLE_FIRMENANSCHRIFT], False),
                   fund("069 123456-77", ["muster.telefon"], True)]
    lauf = analyse.LaufWissen()
    lauf.aufnehmen(ea)
    assert {t for _, t in lauf.kennungen.items()} == {"069 123456-77"}
    analyse.weitergabe_anwenden([ea, eb])
    texte = {st["text"] for f in eb["funde"] for st in f["stellen"]}
    assert "069 123456-77" in texte and "069 123456-0" not in texte


def test_verlesenes_vorkommen_auf_ocr_seite_wird_geschwaerzt(tmp_path, scan_modus):
    """'Birkanallea 40' (OCR-Verleser) ist dieselbe Anschrift wie 'Birkenallee 40': gleiche Wortzahl, gleiche Ziffern,
    Abstand 2 bei 14 Zeichen (<= 14/7)."""
    zeilen = ["Muster Versicherung AG", "Herrn", NAME, "Birkenallee 40", "12345 Musterstadt", "",
              "Sehr geehrter Herr Mustermann,", "Ihre neue Anschrift Birkanallea 40 haben wir gespeichert.",
              "Die Birkenallee 46 ist die Anschrift Ihres Nachbarn."]
    pdf = bildseite(tmp_path / "scan.pdf")
    dienst = Attrappe({0: woerter_aus_zeilen(zeilen)})
    e = analysiere_pdf(pdf, STANDARD, [], [], profil="hoch", ocr=dienst)
    strasse = next(f for f in e["funde"] if f["text"] == "Birkenallee 40")
    texte = [st["text"] for st in strasse["stellen"] if st["an"]]
    assert "Birkanallea 40" in texte and "Birkenallee 46" not in texte
    assert analyse.QUELLE_AEHNLICH in strasse["quellen"]


def test_aehnlichkeit_nur_mit_genug_zeichen_und_gleichen_ziffern():
    class Seite:
        def __init__(self, text):
            self.text = text
            self.bloecke = [type("B", (), {"quelle": "ocr", "zeilen": (0,)})()]
            self.zeilen = [type("Z", (), {"id": 0, "start": 0, "ende": len(text)})()]

    class Dok:
        def __init__(self, text):
            self.text = text
            self.seiten = [Seite(text)]
            self.seiten_start = [0]
    werte = [("strasse", "Birkenallee 40"), ("kurz", "Am Hof 1"), ("wort", "Schreiber")]
    treffer = analyse._aehnliche_stellen(Dok("Birkanallea 40 Birkenallee 41 Am Hof 7 Schreiben"), werte)
    assert treffer == {"strasse": [(0, 14)]}
    assert analyse._abstand("birkanallea 40", "birkenallee 40", 2) == 2


def test_name_in_anderer_stelle_behaelt_eigene_stelle(tmp_path):
    """„Meier“ im Arbeitgeber „Meier Bau GmbH“ und „Weimar“ in „99423 Weimar“ (Nachname einer Person) bekommen eine
    eigene Namensstelle: wird die größere Stelle abgewählt, bleibt der Name trotzdem geschwärzt."""
    text = ["Versicherungsnehmer: Hans Meier", "Arbeitgeber: Meier Bau GmbH", "Anschrift: Lindenweg 3, 99423 Weimar",
            "Mitversichert: Frank Weimar"]
    pdf = textseiten(tmp_path / "meier.pdf", text)
    e = analysiere_pdf(pdf, ALLE, [], [], profil="hoch")
    funde = e["funde"]
    arbeitgeber = next(f for f in funde if f["text"] == "Meier Bau GmbH")
    anfang = arbeitgeber["stellen"][0]["start"]
    meier = [f for f in funde if f["kategorie"] == "namen"
             and any(st["text"] == "Meier" and st["start"] == anfang for st in f["stellen"])]
    assert len(meier) == 1 and meier[0]["ersatz"] == next(f for f in funde if f["text"] == "Hans Meier")["ersatz"]
    assert not any(f["text"] == "Meier Bau" for f in funde), "kein Schein-Name aus dem Firmennamen"
    assert any(f["kategorie"] == "namen" and any(st["text"] == "Weimar" for st in f["stellen"]) for f in funde)
    # Nutzerin wählt den Arbeitgeber ab: „Meier“ verschwindet trotzdem, „Bau GmbH“ bleibt lesbar
    for st in arbeitgeber["stellen"]:
        st["an"] = False
    s = schwaerze_pdf(pdf, funde, ocr=Attrappe(), modell=e["modell"])
    zeile = next(z for z in volltext(s["ausgabe"]).splitlines() if "Bau GmbH" in z)
    assert "Meier" not in zeile


def test_titel_im_formularfeld_ohne_eigene_person(tmp_path):
    """Formularfeld „Titel“ = „Dipl.-Ing.“: an dieser Stelle geschwärzt ([TITEL]), aber keine Person – die Titel
    anderer Personen („Dipl.-Ing. Thomas Schmidt“) bleiben und wandern auch nicht in andere Dokumente."""
    pdf = tmp_path / "antrag.pdf"
    doc = fitz.open()
    seite = doc.new_page()
    for i, (name, wert) in enumerate((("Titel", "Dipl.-Ing."), ("Vorname", "Max"), ("Nachname", "Mustermann"))):
        seite.insert_text((50, 110 + 30 * i), f"{name}:", fontsize=10)
        w = fitz.Widget()
        w.field_name = name
        w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        w.rect = fitz.Rect(130, 98 + 30 * i, 330, 114 + 30 * i)
        w.field_value = wert
        seite.add_widget(w)
    seite.insert_text((50, 260), "Ihr Berater: Dipl.-Ing. Thomas Schmidt", fontsize=10)
    doc.save(pdf)
    doc.close()
    e = analysiere_pdf(pdf, STANDARD, [], [], profil="hoch")
    titel = [f for f in e["funde"] if f["anzeige"] == analyse.ANZEIGE_TITEL]
    assert len(titel) == 1 and titel[0]["ersatz"] == analyse.PLATZHALTER_TITEL
    assert [st["an"] for st in titel[0]["stellen"]] == [True, False]
    assert not any(f["kategorie"] == "namen" and f["text"] == "Dipl.-Ing." and f["anzeige"] != analyse.ANZEIGE_TITEL
                   for f in e["funde"])
    s = schwaerze_pdf(pdf, e["funde"], ocr=Attrappe(), modell=e["modell"])
    text = volltext(s["ausgabe"])
    assert "Dipl.-Ing. [PERSON" not in text and "Dipl.-Ing." in text and s["reste"] == []
    assert text.count("Dipl.-Ing.") == 1
    # nicht dokumentübergreifend
    b = textseiten(tmp_path / "b.pdf", ["Gutachter: Dipl.-Ing. Peter Lang"])
    eb = analysiere_pdf(b, STANDARD, [], [], profil="hoch")
    analyse.weitergabe_anwenden([e, eb])
    assert not any(f["anzeige"] == analyse.ANZEIGE_TITEL or f["text"] == "Dipl.-Ing." for f in eb["funde"])


def test_titel_treffer_eines_detektors_wird_keine_person():
    """Liefert eine Regel nur einen Titel als Namen („Dr. med.“), entsteht keine Person und kein [PERSON …]."""
    assert analyse._nur_titel("Dipl.-Ing.") and analyse._nur_titel("Dr. med.") and analyse._nur_titel("Prof. Dr.")
    assert not analyse._nur_titel("Dr. Meier") and not analyse._nur_titel("")


# ----------------------------------------------------------------------
# M-25: Zuordnungsdatei nicht im Ordner, der hochgeladen wird (vorbereitet, noch ausgeschaltet)
# ----------------------------------------------------------------------
def test_zuordnung_standard_unveraendert_im_ausgabeordner(tmp_path):
    assert schwaerzung.ZUORDNUNG_NEBEN_AUSGABEORDNER is False
    assert schwaerzung.zuordnung_pfad(tmp_path / "anonymisiert") == tmp_path / "anonymisiert" / "_zuordnung.txt"


def test_zuordnung_neben_dem_ausgabeordner(tmp_path, monkeypatch):
    """Eingeschaltet: im Ausgabeordner liegen nur die anonym_….pdf; die Zuordnung steht daneben
    („_zuordnung_anonymisiert.txt“ neben den Originalen), eine alte _zuordnung.txt wird übernommen und gelöscht,
    Freigeben und Verwerfen führen die neue Datei nach, die Meldung nennt den Ort."""
    monkeypatch.setattr(schwaerzung, "ZUORDNUNG_NEBEN_AUSGABEORDNER", True)
    pdf = textseiten(tmp_path / "Mustermann_Max_Police.pdf", [f"Versicherungsnehmer: {NAME}"])
    ziel = tmp_path / "anonymisiert"
    ziel.mkdir()
    (ziel / "_zuordnung.txt").write_text("anonym_07.pdf  <-  Alt_Kunde.pdf  (2026-01-01 10:00)\n", encoding="utf-8")
    e = analysiere_pdf(pdf, STANDARD, [], [])
    s = schwaerze_pdf(pdf, e["funde"], ocr=Attrappe(), freigabe_erforderlich=True)
    datei = tmp_path / "_zuordnung_anonymisiert.txt"
    assert sorted(p.name for p in ziel.iterdir()) == [s["ausgabe"].name]
    zeilen = datei.read_text(encoding="utf-8").splitlines()
    assert zeilen[0].startswith("anonym_07.pdf  <-  Alt_Kunde.pdf")
    assert zeilen[1].startswith(f"{s['ausgabe'].name}  <-  Mustermann_Max_Police.pdf  (")
    assert any(m["code"] == "ZUORDNUNG" and str(datei) in m["text"] for m in s["meldungen"])
    neu = schwaerzung.freigeben(s["ausgabe"])
    assert datei.read_text(encoding="utf-8").splitlines()[1].startswith(f"{neu.name}  <-  ")
    schwaerzung.verwerfen(neu)
    assert [z.split()[0] for z in datei.read_text(encoding="utf-8").splitlines()] == ["anonym_07.pdf"]
    assert not list(ziel.iterdir())


# ----------------------------------------------------------------------
# Nebenkanäle lesen (Einheiten)
# ----------------------------------------------------------------------
def test_office_anhang_wird_gelesen():
    puffer = BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("word/document.xml", "<w:document><w:body><w:p><w:r><w:t>Antrag von Max Muster</w:t></w:r>"
                                        "<w:r><w:t>mann</w:t></w:r></w:p></w:body></w:document>")
        z.writestr("docProps/core.xml", "<cp:coreProperties><dc:creator>Erika Musterfrau</dc:creator>"
                                        "</cp:coreProperties>")
    texte, pruefbar, art = nebenkanaele._anhang_inhalt(puffer.getvalue(), 0)
    assert pruefbar and art == "Office-Dokument"
    text = "\n".join(texte)
    assert "Antrag von Max Mustermann" in text and "creator: Erika Musterfrau" in text
