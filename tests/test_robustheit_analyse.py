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
    # Befund R-04 (Runde 2a): nur wegen der Nebenkanäle entstanden -> nie still „fertig“, immer _PRUEFEN mit Grund
    assert s["fehler"] is None and s["ausgabe"] is not None and s["ausgabe"].name == "anonym_01_PRUEFEN.pdf"
    assert s["treffer"] == 0 and s["status"] == "pruefen"
    assert schwaerzung._grund("NUR_NEBENKANAL").text in s["pruefen_gruende"]
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


# ======================================================================
# Runde 2a, Review-Befunde (Paket „analyse-status“, Nachbesserung)
# ======================================================================
def _lesbar(text: str, funde: list) -> str:
    """Text mit allen angehakten Stellen durch █ ersetzt – was danach noch dasteht, bliebe lesbar."""
    for s, e in sorted(((st["start"], st["ende"]) for f in funde for st in f["stellen"] if st.get("an", True)),
                       reverse=True):
        text = text[:s] + "█" * (e - s) + text[e:]
    return text


# ----------------------------------------------------------------------
# Befund Punkt 9: Nachnamen, die zugleich Titel sind (Graf, Ritter, Herzog, Kaplan, Pastor …)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, name", [
    ("Sehr geehrter Herr Graf,\nvielen Dank für Ihre Nachricht. Herr Graf, bitte senden Sie uns noch die Rechnung.\n"
     "Mit freundlichen Grüßen\n\nAnlage: Schreiben an Graf vom 01.04.2024", "Graf"),
    ("Schadenmeldung Hausrat\nName: Kaplan\nVorname: Ayse\nGeburtsdatum: 12.03.1975\n\n"
     "Die Mieterin Frau Kaplan hat den Schaden am 02.05.2024 bemerkt.\n\nUnterschrift: A. Kaplan", "Kaplan"),
    ("Antrag Hausratversicherung\nName: Herzog\nVorname: Anna\nGeburtsdatum: 12.03.1975\n"
     "Straße: Hauptstraße 12\nPLZ/Ort: 10115 Berlin\n\nUnterschrift Antragsteller: A. Herzog", "Herzog"),
    ("Sehr geehrter Herr Ritter,\nwir bestätigen den Eingang Ihrer Kündigung vom 03.05.2024.\n\n"
     "Mit freundlichen Grüßen\nMuster Versicherung AG\n\nKopie: Familie Ritter, Hauptstraße 12, 10115 Berlin", "Ritter"),
])
def test_nachname_der_zugleich_titel_ist_wird_ueberall_geschwaerzt(text, name):
    """Befund Punkt 9 (hoch): „Graf“, „Kaplan“, „Herzog“, „Ritter“ stehen in der Liste der Anreden und Titel, sind aber
    häufige Nachnamen. Früher galt der Treffer als „Titel ohne Namen“: nur seine Stelle wurde [TITEL], alle übrigen
    Vorkommen waren abgewählt („derselbe Titel bei einer anderen Person“) – der Nachname blieb in Anrede, Fließtext und
    Unterschrift lesbar, Status „fertig“. Jetzt ist er eine Person: jedes Vorkommen angehakt, [PERSON …]."""
    funde = analysiere_text(text, STANDARD, [], [], profil="hoch")
    assert name not in _lesbar(text, funde), _lesbar(text, funde)
    person = [f for f in funde if f["kategorie"] == "namen" and f["text"].endswith(name)]
    assert person and all(f["ersatz"].startswith("[PERSON") for f in person)
    assert not any(f["anzeige"] == analyse.ANZEIGE_TITEL for f in funde)
    assert not any(st.get("grund") == analyse.GRUND_TITEL for f in funde for st in f["stellen"])


def test_titel_regel_kennt_namen_und_bleibt_fuer_echte_titel():
    for name in ("Graf", "Herr Graf", "Frau Kaplan", "Herzog", "Ritter", "Pastor", "Fürst", "Prinz", "Sen",
                 "Phil Graf", "Jun Kaplan", "An Herrn"):
        assert not analyse._nur_titel(name, analyse._wissen_modul()), name
    for titel in ("Dipl.-Ing.", "Dr. med.", "Prof. Dr.", "Herrn Dr.", "Dr. phil.", "Rechtsanwalt",
                  "Dipl.Ing", "Dr.med"):            # Punkt im Wortinneren: Abkürzung, nie ein Name
        assert analyse._nur_titel(titel, analyse._wissen_modul()), titel
    # Formularfeld „Titel“: auch die übrigen Titel der Wissensbasis, aber nie ein Nachname
    assert analyse._nur_titel("Mag. phil.", analyse._wissen_modul(), feld=True)
    assert not analyse._nur_titel("Graf", analyse._wissen_modul(), feld=True)


def test_pastor_als_nachname_mit_vollem_namen():
    """„Pastor“ steht zusätzlich in namen.TITEL: mit vollem Namen „Thomas Pastor“ blieb „Herr Pastor“ lesbar."""
    text = ("Herrn\nThomas Pastor\nLindenweg 7\n99423 Weimar\n\nSehr geehrter Herr Pastor,\nwir bestätigen Ihre "
            "Kündigung.\nMit freundlichen Grüßen\n\nKopie an Herrn Pastor")
    funde = analysiere_text(text, STANDARD, [], [], profil="hoch")
    assert "Pastor" not in _lesbar(text, funde), _lesbar(text, funde)
    ersatz = {f["ersatz"] for f in funde if f["kategorie"] == "namen"}
    assert ersatz == {"[PERSON A]"}, ersatz
    # Titel und Namenszusätze bleiben Titel: „Pastor Müller“ ist ein Pastor namens Müller, „sen.“ ein Zusatz
    assert analyse._name_zerlegen("Pastor Müller") == (["Müller"], None)        # ein Namenswort, Rolle offen
    assert analyse._name_zerlegen("Thomas Pastor") == (["Thomas"], "Pastor")
    assert analyse._name_zerlegen("Max Müller sen.") == (["Max"], "Müller")
    assert "Pastor" in analyse._bestandteile("Thomas Pastor") and "Pastor" not in analyse._bestandteile("Pastor Müller")


def test_nachname_als_titel_im_pdf_und_ueber_den_lauf(tmp_path):
    """Wie in der Oberfläche (Modell übergeben, Freigabe aus): in der Ausgabe steht kein „Graf“ mehr; im Lauf mit einem
    zweiten Dokument („Sabine Ritter“) wird „Frau Ritter“ im ersten überall geschwärzt."""
    pdf = textseiten(tmp_path / "graf.pdf", ["Muster Versicherung AG · Postfach 10 11 12 · 20007 Hamburg", "",
                                            "Sehr geehrter Herr Graf,", "vielen Dank für Ihre Nachricht vom 01.04.2024.",
                                            "Herr Graf, bitte senden Sie uns noch die Rechnung der Werkstatt.", "",
                                            "Anlage: Schreiben an Graf vom 01.04.2024"])
    e = analysiere_pdf(pdf, STANDARD, [], [], profil="hoch")
    s = schwaerze_pdf(pdf, e["funde"], ocr=Attrappe(), modell=e["modell"], ziel_ordner=tmp_path / "aus")
    assert s["ausgabe"] is not None and "Graf" not in volltext(s["ausgabe"])
    a = textseiten(tmp_path / "a.pdf", ["Versicherungsnehmerin: Sabine Ritter", "Lindenweg 7, 99423 Weimar"])
    b = textseiten(tmp_path / "b.pdf", ["Schadenmeldung", "Sehr geehrte Frau Ritter,", "wir haben Ihre Meldung "
                                        "erhalten. Fahrerin war Ritter selbst.", "Unterschrift: Ritter"])
    lauf = analyse.LaufWissen()
    ea = analysiere_pdf(a, STANDARD, [], [], profil="hoch", lauf=lauf)
    eb = analysiere_pdf(b, STANDARD, [], [], profil="hoch", lauf=lauf)
    analyse.weitergabe_anwenden([ea, eb])
    ritter = [st for f in eb["funde"] for st in f["stellen"] if st["text"] == "Ritter"]
    assert len(ritter) == 3 and all(st["an"] for st in ritter)


# ----------------------------------------------------------------------
# Befund R-11 (kritisch): Reparatur erst beim Laden eines kaputten Objekts
# ----------------------------------------------------------------------
NAMEN_BRIEF = ["Muster Versicherung AG - Abteilung Leistung", "Herrn", NAME, "", "Sehr geehrter Herr Mustermann,",
               f"wir haben den Antrag von {NAME} geprüft.", "Ihre Ansprechpartnerin ist Erika Musterfrau.",
               "Mit freundlichen Grüßen", "Erika Musterfrau"]


def _getaggt_kaputt(tmp_path, art: str) -> Path:
    """Getaggte PDF (Strukturbaum wie beim Word-Export), deren letztes Strukturelement beschädigt ist: falscher Versatz
    in der Querverweistabelle (art="versatz") bzw. mit Nullbytes überschrieben (art="genullt", Übertragungsfehler).
    MuPDF repariert so eine Datei erst, wenn das kaputte Objekt geladen wird – Öffnen und Seitenlesen berühren es nicht."""
    doc = fitz.open()
    for n in range(2):
        seite = doc.new_page()
        for i, z in enumerate(NAMEN_BRIEF):
            seite.insert_text((72, 90 + i * 16), z if i else f"{z} – Seite {n + 1}", fontsize=11)
    wurzel, dokel = doc.get_new_xref(), doc.get_new_xref()
    elemente = []
    for n in range(len(doc)):
        x = doc.get_new_xref()
        doc.update_object(x, f"<</Type/StructElem/S/P/P {dokel} 0 R/Pg {doc[n].xref} 0 R/K 0>>")
        elemente.append(x)
    doc.update_object(dokel, f"<</Type/StructElem/S/Document/P {wurzel} 0 R/K[{' '.join(f'{x} 0 R' for x in elemente)}]>>")
    doc.update_object(wurzel, f"<</Type/StructTreeRoot/K {dokel} 0 R>>")
    doc.xref_set_key(doc.pdf_catalog(), "StructTreeRoot", f"{wurzel} 0 R")
    doc.xref_set_key(doc.pdf_catalog(), "MarkInfo", "<</Marked true>>")
    roh = doc.tobytes(garbage=0, deflate=False, expand=255)
    doc.close()
    ziel = elemente[-1]
    if art == "versatz":
        m = re.search(rb"xref\r?\n0 (\d+)\r?\n", roh)
        pos = m.end() + ziel * 20
        roh = roh[:pos] + b"%010d" % (int(roh[pos:pos + 10]) + 7) + roh[pos + 10:]
    else:
        m = re.search(rb"(?m)^%d 0 obj" % ziel, roh)
        ende = roh.find(b"endobj", m.start()) + len(b"endobj")
        roh = roh[:m.start()] + b"\x00" * (ende - m.start()) + roh[ende:]
    pfad = tmp_path / f"getaggt_{art}.pdf"
    pfad.write_bytes(roh)
    with fitz.open(pfad) as probe:
        if probe.is_repaired:
            pytest.skip("MuPDF repariert diese Datei schon beim Öffnen")
    return pfad


@pytest.mark.parametrize("art", ["versatz", "genullt"])
def test_spaete_reparatur_wird_vor_dem_schwaerzen_ausgeloest(tmp_path, art):
    """Befund R-11 (kritisch): MuPDF reparierte die Datei erst in der Nebenkanal-Bereinigung – nach allen Schwärzungen –
    und verwarf dabei alle Änderungen im Speicher: die Ausgabe trug „Max Mustermann“ 4× im Klartext, Status „fertig“,
    Selbstkontrolle ohne Rest. Jetzt wird jedes Objekt direkt nach dem Öffnen geladen: die Reparatur geschieht vor jeder
    Änderung, DATEI_REPARIERT, _PRUEFEN, kein Klartext."""
    pdf = _getaggt_kaputt(tmp_path, art)
    with fitz.open(pdf) as doc:
        assert not doc.is_repaired and analyse.reparatur_erzwingen(doc) and doc.is_repaired
    e = analysiere_pdf(pdf, STANDARD, [], [])
    assert "DATEI_REPARIERT" in codes(e) and any(m["code"] == "DATEI_REPARIERT" for m in e["modell"].leckrelevant)
    for modell in (e["modell"], None):
        s = schwaerze_pdf(pdf, e["funde"], ocr=Attrappe(), modell=modell,
                          ziel_ordner=tmp_path / ("mit" if modell else "ohne"))
        assert s["status"] == "pruefen" and any("beschädigt" in g for g in s["pruefen_gruende"])
        text = volltext(s["ausgabe"])
        assert "Mustermann" not in text and "Musterfrau" not in text and "[PERSON A]" in text


def test_spaete_reparatur_nach_beginn_der_aenderungen_gibt_keine_ausgabe(tmp_path, monkeypatch):
    """Zweites Netz: Kippt is_repaired doch erst nach Beginn der Änderungen (hier: Erzwingen abgeschaltet), entsteht
    KEINE Ausgabe – eine _PRUEFEN-Datei mit zurückgesetzten Schwärzungen wäre kein Schutz."""
    pdf = _getaggt_kaputt(tmp_path, "versatz")
    e = analysiere_pdf(pdf, STANDARD, [], [])
    monkeypatch.setattr(analyse, "reparatur_erzwingen", analyse.datei_repariert)
    s = schwaerze_pdf(pdf, e["funde"], ocr=Attrappe(), ziel_ordner=tmp_path / "aus")
    assert s["ausgabe"] is None and s["status"] is None and s["fehler"] == schwaerzung.TEXT_SPAETE_REPARATUR
    assert any(m["code"] == "DATEI_REPARIERT" and m["art"] == "fehler" for m in s["meldungen"])
    assert not list((tmp_path / "aus").glob("*.pdf")) if (tmp_path / "aus").exists() else True


def test_selbstkontrolle_wertet_originaltext_im_rechteck_nicht_als_platzhalter(tmp_path, monkeypatch):
    """Drittes Netz: Steht nach einer (hier erzwungen unbemerkten) späten Reparatur der Originaltext wieder in den
    Schwärzungsrechtecken, meldet die Selbstkontrolle ihn als Rest – früher galt jeder Treffer im Rechteck als
    Platzhaltertext."""
    pdf = _getaggt_kaputt(tmp_path, "genullt")
    e = analysiere_pdf(pdf, STANDARD, [], [])
    monkeypatch.setattr(analyse, "reparatur_erzwingen", analyse.datei_repariert)
    monkeypatch.setattr(schwaerzung, "_spaete_reparatur_pruefen", lambda lauf, doc: None)
    s = schwaerze_pdf(pdf, e["funde"], ocr=Attrappe(), ziel_ordner=tmp_path / "aus")
    assert s["status"] == "pruefen" and NAME in s["reste"]


def test_platzhalter_erkennung_im_rechteck():
    platzhalter = {"[PERSON A]", "[P A]", "[ADRESSE]"}
    text = "Herr [PERSON A] wohnt in [ADRESSE] bei Max Mustermann"
    s = text.index("PERSON")
    assert schwaerzung._im_platzhalter(text, s, s + 6, platzhalter)
    assert schwaerzung._im_platzhalter(text, text.index("[ADRESSE]"), text.index("[ADRESSE]") + 9, platzhalter)
    s = text.index("Mustermann")
    assert not schwaerzung._im_platzhalter(text, s, s + 10, platzhalter)
    assert schwaerzung._im_platzhalter("[GESCHWÄRZT]", 1, 4, set())        # unbekannter, aber typischer Platzhalter
    assert not schwaerzung._im_platzhalter("[Max Mustermann]", 1, 4, set())


# ----------------------------------------------------------------------
# Befund R-04: Ausgabe nur wegen Nebenkanälen; Nebenkanäle, die die Erkennung nicht las
# ----------------------------------------------------------------------
def test_ausgabe_nur_wegen_nebenkanal_ist_pruefen_auch_mit_modell(tmp_path):
    """Befund R-04 (mittel): Die Seiten nennen nichts (z. B. weil die Textebene unlesbar ist), der Titel nennt eine
    Person – das ist ein starkes Warnsignal. Die Ausgabe heißt _PRUEFEN mit Grund, nie still „fertig“ (wie die
    Oberfläche: Modell übergeben, Freigabe aus)."""
    pdf = textseiten(tmp_path / "titel.pdf", NEUTRAL)
    with fitz.open(pdf) as doc:
        doc.set_metadata({"title": f"Kündigung {NAME}"})
        doc.saveIncr()
    e = analysiere_pdf(pdf, STANDARD, [], [])
    assert e["funde"] == [] and e["nebenkanaele"]["personenbezug"]
    s = schwaerze_pdf(pdf, [], ocr=Attrappe(), modell=e["modell"], nebenkanaele=e["nebenkanaele"])
    assert s["status"] == "pruefen" and s["ausgabe"].name == "anonym_01_PRUEFEN.pdf"
    assert s["pruefen_gruende"] == ["Personendaten nur außerhalb der Seiten gefunden – Seiten bitte selbst ansehen"]
    hinweis = next(m["text"] for m in s["meldungen"] if "Auf den Seiten" in m["text"])
    assert hinweis.startswith("Auf den Seiten wurde nichts erkannt")
    assert any(m["code"] == "AUSGABE_PRUEFEN" and m["art"] == "warnung" for m in s["meldungen"])


@pytest.mark.parametrize("feld, wert", [
    ("title", "Microsoft Word - PIB_Hausrat_Mustermann_Max.docx"),        # das Beispiel aus R-04 selbst
    ("title", "Scan_Mustermann_Max_2024-05-03"),
    ("title", "Antrag-Thomas-Schaefer-Kfz.pdf"),
    ("title", "AntragThomasSchaefer"),
    ("keywords", "Kunde_Schaefer_Thomas"),
    ("subject", "Schadenmeldung_Schäfer_Thomas_2024.docx"),
    ("producer", "Thomas Schäfer"),
    ("producer", NAME),
    ("creator", "Schäfer, Thomas"),
    ("creator", "max.mustermann@example.de"),
])
def test_nebenkanal_namen_in_dateinamen_schreibweise_und_programmfeldern(tmp_path, feld, wert):
    """Befund R-04 (hoch): Titel im Stil eines Dateinamens und das Feld Producer ergaben personenbezug=False – keine
    Ausgabe, das Original ging samt Titel weiter. Jetzt werden sie als Wörter gelesen bzw. auf Personennamen geprüft."""
    pdf = textseiten(tmp_path / "nk.pdf", NEUTRAL)
    with fitz.open(pdf) as doc:
        doc.set_metadata({feld: wert})
        doc.saveIncr()
    e = analysiere_pdf(pdf, STANDARD, [], [])
    assert e["nebenkanaele"]["personenbezug"] and e["nebenkanaele"]["metadaten"] == 1, wert
    s = schwaerze_pdf(pdf, e["funde"], ocr=Attrappe(), nebenkanaele=e["nebenkanaele"])
    assert s["status"] == "pruefen"
    with fitz.open(s["ausgabe"]) as aus:
        assert not any((aus.metadata or {}).get(k) for k in ("title", "subject", "keywords", "creator", "producer"))


@pytest.mark.parametrize("feld, wert", [
    ("creator", "RICOH MP C3004"), ("creator", "OKI MC573"), ("creator", "EPSON WF-4830"), ("creator", "Impress"),
    ("creator", "Genius Scan"), ("creator", "Crystal Reports"), ("creator", "Olivetti d-Color MF3302"),
    ("producer", "RICOH IM C3000"), ("producer", "Microsoft: Print To PDF"), ("producer", "GPL Ghostscript 9.55"),
    ("title", "Unbenannt"), ("title", "Dokument1"), ("title", "Microsoft Word - AVB_Hausrat_2024.docx"),
])
def test_geraete_und_programmnamen_sind_kein_personenbezug(tmp_path, feld, wert):
    """Befund NEBENKANAL_FUND (mittel): Modell- und Programmnamen lösten das Kfz-Muster bzw. die Namenserkennung aus –
    auf jedem Scan dieses Geräts stand eine falsche Warnung. Programmfelder zählen nur mit einem ausdrücklichen
    Personennamen, Standardtitel nie."""
    pdf = textseiten(tmp_path / "geraet.pdf", NEUTRAL)
    with fitz.open(pdf) as doc:
        doc.set_metadata({feld: wert})
        doc.saveIncr()
    e = analysiere_pdf(pdf, STANDARD, [], [])
    assert e["nebenkanaele"] == analyse.NEBENKANAELE_LEER and "NEBENKANAL_FUND" not in codes(e), wert


def test_xmp_creatortool_ist_programmfeld():
    xmp = ('<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="r"><rdf:Description xmlns:xmp="x" '
           'xmlns:pdf="p" xmp:CreatorTool="RICOH MP C3004"><pdf:Producer>OKI MC573</pdf:Producer></rdf:Description>'
           '</rdf:RDF></x:xmpmeta>')
    programme: list = []
    assert "RICOH" not in nebenkanaele._xml_zu_text(xmp, programme) and set(programme) == {"RICOH MP C3004",
                                                                                            "OKI MC573"}
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), NEUTRAL[0], fontsize=11)
    doc.set_xml_metadata(xmp)
    assert analyse.nebenkanaele_pruefen(doc, STANDARD, meldungen=[], warnungen=[])["personenbezug"] is False


def _neutral_doc():
    doc = fitz.open()
    seite = doc.new_page()
    for i, z in enumerate(NEUTRAL):
        seite.insert_text((50, 72 + 16 * i), z, fontsize=11, fontname="helv")
    return doc


def test_unsichtbare_kanaele_werden_gelesen():
    """Befund R-04: JavaScript, Link-Ziele (mailto, Parameter einer Adresse), Seitenbeschriftungen und XMP an Seite und
    Bild entfernte die Ausgabe zwar, die Analyse las sie aber nicht – personenbezug=False, keine Ausgabe."""
    xmp = ('<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="r"><rdf:Description xmlns:dc="d"><dc:creator>'
           f'<rdf:Seq><rdf:li>{NAME}</rdf:li></rdf:Seq></dc:creator></rdf:Description></rdf:RDF></x:xmpmeta>')

    def javascript(doc):
        js = doc.get_new_xref()
        doc.update_object(js, f"<</S/JavaScript/JS(app.alert\\('{NAME}, IBAN {IBAN}'\\);)>>")
        namen = doc.get_new_xref()
        doc.update_object(namen, f"<</Names[(a) {js} 0 R]>>")
        doc.xref_set_key(doc.pdf_catalog(), "Names", f"<</JavaScript {namen} 0 R>>")

    def mailto(doc):
        doc[0].insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(72, 300, 200, 315),
                            "uri": "mailto:max.mustermann@example.de"})

    def parameter(doc):
        doc[0].insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(72, 300, 200, 315),
                            "uri": "https://portal.example.de/antrag?name=Thomas%20Sch%C3%A4fer&iban=DE89370400440532013000"})

    def seitenbeschriftung(doc):
        doc.set_page_labels([{"startpage": 0, "prefix": "Mustermann-", "style": "D", "firstpagenum": 1}])

    def seiten_xmp(doc):
        x = doc.get_new_xref()
        doc.update_object(x, "<</Type/Metadata/Subtype/XML>>")
        doc.update_stream(x, xmp.encode(), compress=False)
        doc.xref_set_key(doc[0].xref, "Metadata", f"{x} 0 R")

    for einbauen in (javascript, mailto, parameter, seitenbeschriftung, seiten_xmp):
        doc = _neutral_doc()
        einbauen(doc)
        doc = fitz.open("pdf", doc.tobytes())
        meldungen: list = []
        ergebnis = analyse.nebenkanaele_pruefen(doc, STANDARD, meldungen=meldungen, warnungen=[])
        assert ergebnis["personenbezug"], einbauen.__name__
        assert meldungen and NAME not in meldungen[0]["text"] and "Mustermann" not in meldungen[0]["text"]
    # Kontrolle: eine bloße Webadresse des Versicherers trägt nichts
    doc = _neutral_doc()
    doc[0].insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(72, 300, 200, 315),
                        "uri": "https://www.versicherer.de/service/kontakt"})
    doc = fitz.open("pdf", doc.tobytes())
    assert analyse.nebenkanaele_pruefen(doc, STANDARD, meldungen=[], warnungen=[])["personenbezug"] is False


def test_csv_anhang_und_anhangname_im_dateinamen_stil(tmp_path):
    """Kundenliste als CSV mit Semikolon (Standard des deutschen Excel) und ein Anhang „Ausweis_Mustermann_Max.txt“ mit
    neutralem Inhalt: beide Personenbezug."""
    for name, daten in (("liste.csv", "Nachname;Vorname;Ort\nMustermann;Max;Berlin\nSchmidt;Erika;Hamburg\n"),
                        ("Ausweis_Mustermann_Max.txt", "Kopie liegt vor.\n")):
        doc = _neutral_doc()
        doc.embfile_add(name, daten.encode(), filename=name)
        doc = fitz.open("pdf", doc.tobytes())
        assert analyse.nebenkanaele_pruefen(doc, STANDARD, meldungen=[], warnungen=[])["anhaenge"] == 1, name
    assert "Nachname: Mustermann" in nebenkanaele._csv_zu_text("Nachname;Vorname\nMustermann;Max")
    assert nebenkanaele._csv_zu_text("Ein ganz normaler Satz.") is None


def test_angehaengte_pdf_mit_bild_und_textzeile_ist_nicht_pruefbar():
    """Eine angehängte PDF mit „Anlage 1“ als Text und dem Brief als Bild galt als prüfbar (sie hatte ja Text)."""
    brief = fitz.open()
    s = brief.new_page()
    for i, z in enumerate([NAME, "Hauptstraße 12", "10115 Berlin", f"IBAN {IBAN}"]):
        s.insert_text((70, 110 + 22 * i), z, fontsize=12)
    png = s.get_pixmap(dpi=100, colorspace=fitz.csGRAY).tobytes("png")
    innen = fitz.open()
    seite = innen.new_page()
    seite.insert_text((60, 50), "Anlage 1", fontsize=11)
    seite.insert_image(fitz.Rect(30, 70, 565, 830), stream=png)
    doc = _neutral_doc()
    doc.embfile_add("anlage1.pdf", innen.tobytes(), filename="anlage1.pdf")
    doc = fitz.open("pdf", doc.tobytes())
    meldungen: list = []
    assert analyse.nebenkanaele_pruefen(doc, STANDARD, meldungen=meldungen, warnungen=[])["personenbezug"]
    assert "nicht geprüft werden" in meldungen[0]["text"]


def test_nebenkanal_fund_ist_hinweis_wenn_ohnehin_geschwaerzt_wird(tmp_path):
    """Befund NEBENKANAL_FUND (Warnlast): Wird auf den Seiten ohnehin geschwärzt, entfernt die Ausgabe die Nebenkanäle
    sowieso – dann ist der Fund ein Hinweis. Ohne Seitenfund bleibt es eine Warnung (sie ist der Grund der Ausgabe)."""
    mit = textseiten(tmp_path / "mit.pdf", [f"Versicherungsnehmer: {NAME}"])
    ohne = textseiten(tmp_path / "ohne.pdf", NEUTRAL)
    for pdf in (mit, ohne):
        with fitz.open(pdf) as doc:
            doc.set_metadata({"author": "Erika Musterfrau"})
            doc.saveIncr()
    e = analysiere_pdf(mit, STANDARD, [], [])
    meldung = next(m for m in e["meldungen"] if m["code"] == "NEBENKANAL_FUND")
    assert meldung["art"] == "hinweis" and meldung["text"] in e["hinweise"] and meldung["text"] not in e["warnungen"]
    e = analysiere_pdf(ohne, STANDARD, [], [])
    meldung = next(m for m in e["meldungen"] if m["code"] == "NEBENKANAL_FUND")
    assert meldung["art"] == "warnung" and meldung["text"] in e["warnungen"]


# ----------------------------------------------------------------------
# Befund R-07, Fall scan_bild_defekt: Bild mit abgebrochenen JPEG-Daten
# ----------------------------------------------------------------------
_JPEG_LUMA = [16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55, 14, 13, 16, 24, 40, 57, 69, 56, 14, 17,
              22, 29, 51, 87, 80, 62, 18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92, 49, 64, 78,
              87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99]
_JPEG_ZICKZACK = [0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6,
                  7, 14, 21, 28, 35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51, 58, 59, 52, 45, 38,
                  31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63]
_JPEG_DC_BITS = [0, 1, 5, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0]
_JPEG_DC_WERTE = list(range(12))
_JPEG_AC_BITS = [0, 2, 1, 3, 3, 2, 4, 3, 5, 5, 4, 4, 0, 0, 1, 0x7D]
_JPEG_AC_WERTE = bytes.fromhex(
    "01020300041105122131410613516107227114328191a1082342b1c11552d1f02433627282090a161718191a25262728292a3435363738"
    "393a434445464748494a535455565758595a636465666768696a737475767778797a838485868788898a92939495969798999aa2a3a4a5"
    "a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8f9fa")


def _baseline_jpeg(samples: bytes, breite: int, hoehe: int, qualitaet: int = 80) -> bytes:
    """Kleinster Baseline-JPEG-Kodierer (Graustufen, Standardtabellen aus ITU T.81 Anhang K) – MuPDF schreibt nur
    progressive JPEGs, abgebrochene Scans sind aber meist Baseline-JPEGs (dort füllt der Dekoder den Rest einheitlich)."""
    import math
    skala = 5000 / qualitaet if qualitaet < 50 else 200 - 2 * qualitaet
    quant = [min(255, max(1, int((q * skala + 50) / 100))) for q in _JPEG_LUMA]
    m = [[(math.sqrt(0.5) if u == 0 else 1.0) / 2 * math.cos((2 * x + 1) * u * math.pi / 16) for x in range(8)]
         for u in range(8)]

    def codes(bits, werte):
        tabelle, code, k = {}, 0, 0
        for laenge in range(1, 17):
            for _ in range(bits[laenge - 1]):
                tabelle[werte[k]] = (code, laenge)
                code += 1
                k += 1
            code <<= 1
        return tabelle
    dc_codes, ac_codes = codes(_JPEG_DC_BITS, _JPEG_DC_WERTE), codes(_JPEG_AC_BITS, list(_JPEG_AC_WERTE))
    puffer, bitzahl, aus = 0, 0, bytearray()

    def schreiben(wert, laenge):
        nonlocal puffer, bitzahl
        puffer = (puffer << laenge) | (wert & ((1 << laenge) - 1))
        bitzahl += laenge
        while bitzahl >= 8:
            bitzahl -= 8
            byte = (puffer >> bitzahl) & 0xFF
            aus.append(byte)
            if byte == 0xFF:
                aus.append(0)

    def zahl(v):
        groesse = abs(v).bit_length()
        return groesse, (v if v >= 0 else v + (1 << groesse) - 1)
    vorher = 0
    for by in range(0, hoehe, 8):
        for bx in range(0, breite, 8):
            block = [[samples[min(hoehe - 1, by + y) * breite + min(breite - 1, bx + x)] - 128 for x in range(8)]
                     for y in range(8)]
            zeilen = [[sum(m[u][x] * block[y][x] for x in range(8)) for u in range(8)] for y in range(8)]
            koeff = [[sum(m[v][y] * zeilen[y][u] for y in range(8)) for u in range(8)] for v in range(8)]
            q = [int(round(koeff[i // 8][i % 8] / quant[i])) for i in range(64)]
            zz = [q[i] for i in _JPEG_ZICKZACK]
            groesse, bits = zahl(zz[0] - vorher)
            vorher = zz[0]
            schreiben(*dc_codes[groesse])
            schreiben(bits, groesse)
            lauf = 0
            for wert in zz[1:]:
                if wert == 0:
                    lauf += 1
                    continue
                while lauf > 15:
                    schreiben(*ac_codes[0xF0])
                    lauf -= 16
                groesse, bits = zahl(wert)
                schreiben(*ac_codes[(lauf << 4) | groesse])
                schreiben(bits, groesse)
                lauf = 0
            if lauf:
                schreiben(*ac_codes[0x00])
    if bitzahl:
        schreiben(0x7F, 8 - bitzahl)

    def segment(marker, nutzdaten):
        return bytes([0xFF, marker]) + (len(nutzdaten) + 2).to_bytes(2, "big") + nutzdaten
    kopf = b"\xff\xd8" + segment(0xDB, bytes([0]) + bytes(quant[i] for i in _JPEG_ZICKZACK))
    kopf += segment(0xC0, bytes([8]) + hoehe.to_bytes(2, "big") + breite.to_bytes(2, "big") + bytes([1, 1, 0x11, 0]))
    kopf += segment(0xC4, bytes([0x00] + _JPEG_DC_BITS + _JPEG_DC_WERTE))
    kopf += segment(0xC4, bytes([0x10] + _JPEG_AC_BITS) + _JPEG_AC_WERTE)
    kopf += segment(0xDA, bytes([1, 1, 0x00, 0, 63, 0]))
    return kopf + bytes(aus) + b"\xff\xd9"


def _text_jpeg(zeilen, breite=360, hoehe=280, rauschen=True) -> tuple:
    """Baseline-JPEG (Graustufen) mit Textzeilen über die ganze Höhe; mit Rauschen im Papier wie bei einem echten
    Scan (ein vollständiges Bild hat dann unten keine einheitliche Fläche)."""
    import random
    doc = fitz.open()
    seite = doc.new_page(width=breite, height=hoehe)
    for i, z in enumerate(zeilen):
        seite.insert_text((12, 22 + i * (hoehe - 30) / max(1, len(zeilen) - 1)), z, fontsize=12)
    pix = seite.get_pixmap(dpi=72, colorspace=fitz.csGRAY)
    doc.close()
    samples = pix.samples
    if rauschen:
        zufall = random.Random(7)
        samples = bytes(min(p, 236 + zufall.randrange(20)) for p in samples)
    return _baseline_jpeg(samples, pix.width, pix.height), pix.width, pix.height


BILD_ZEILEN = [f"Kontoinhaber: {NAME}", f"IBAN: {IBAN}", "geboren am 12.03.1975", "Hauptstraße 12, 10115 Berlin",
               "Versicherungsschein-Nr. HS-2023-445566", "Telefon 030 1234567", "E-Mail max@example.de"]


def _pdf_mit_jpeg(pfad, voll, daten, rect, text=()):
    """PDF mit einem Bild, dessen JPEG-Daten danach durch `daten` ersetzt werden (z. B. nach der Hälfte abgebrochen),
    und optional Textzeilen. Gespeichert und neu geöffnet wird erst beim Prüfen (MuPDF merkt sich Dekodiertes)."""
    doc = fitz.open()
    seite = doc.new_page()
    for i, z in enumerate(text):
        seite.insert_text((72, 90 + 16 * i), z, fontsize=11)
    seite.insert_image(fitz.Rect(rect), stream=voll)
    x = seite.get_images()[0][0]
    doc.update_stream(x, daten, compress=False)
    doc.xref_set_key(x, "Filter", "/DCTDecode")
    doc.save(pfad)
    doc.close()
    return Path(pfad)


def test_abgebrochenes_jpeg_wird_erkannt_und_macht_pruefen(tmp_path, scan_modus):
    """Befund R-07 (mittel): Bricht ein JPEG mitten im Bild ab, zeichnet MuPDF es bis zur Abbruchzeile; die halb
    sichtbare Zeile liest die OCR nicht, ein Mensch oder eine Bild-KI schon – Status war „fertig“. Jetzt: Warnung
    BILD_BESCHAEDIGT in der Analyse, Grund „Bild beschädigt“ in der Schwärzung (mit und ohne Modell)."""
    voll, _, _ = _text_jpeg(BILD_ZEILEN * 2)
    pdf = _pdf_mit_jpeg(tmp_path / "scan_defekt.pdf", voll, voll[:int(len(voll) * 0.5)], (0, 0, 595, 842))
    assert analyse.bild_schaeden(pdf) == {0: "bricht mitten im Bild ab"}
    dienst = Attrappe({0: woerter_aus_zeilen(BILD_ZEILEN[:3])})
    e = analysiere_pdf(pdf, STANDARD, [], [], ocr=dienst)
    assert "BILD_BESCHAEDIGT" in codes(e) and any(m["code"] == "BILD_BESCHAEDIGT" for m in e["modell"].leckrelevant)
    for modell in (e["modell"], None):
        s = schwaerze_pdf(pdf, e["funde"], ocr=dienst, ocr_cache=e["ocr_cache"], modell=modell,
                          ziel_ordner=tmp_path / ("mit" if modell else "ohne"))
        assert s["status"] == "pruefen" and "Seite 1: Bild beschädigt – Teile nicht lesbar" in s["pruefen_gruende"]


def test_abgebrochenes_bild_auf_textseite(tmp_path):
    """Dasselbe für ein beschädigtes Bild auf einer Textseite (Modus „bilder“): Grund für _PRUEFEN."""
    voll, _, _ = _text_jpeg(BILD_ZEILEN * 2)
    pdf = _pdf_mit_jpeg(tmp_path / "text_bild.pdf", voll, voll[:int(len(voll) * 0.55)], (72, 260, 520, 573),
                        text=["Sehr geehrter Herr Mustermann,", "anbei die Kopie Ihrer Kontoverbindung."])
    e = analysiere_pdf(pdf, STANDARD, [], [], ocr=Attrappe())
    assert "BILD_BESCHAEDIGT" in codes(e)
    s = schwaerze_pdf(pdf, e["funde"], ocr=Attrappe(), ziel_ordner=tmp_path / "aus")
    assert s["status"] == "pruefen" and any("Bild beschädigt" in g for g in s["pruefen_gruende"])


def test_vollstaendige_bilder_sind_kein_schaden(tmp_path):
    """Kein Fehlalarm: ein vollständiges JPEG und eines, dem nur die Endmarke fehlt (MuPDF warnt dann auch „premature
    end“, aber das Bild ist ganz – unten keine einheitliche Füllfläche)."""
    voll, _, _ = _text_jpeg(BILD_ZEILEN * 2)
    for name, daten in (("voll", voll), ("ohne_endmarke", voll[:-2])):
        pdf = _pdf_mit_jpeg(tmp_path / f"{name}.pdf", voll, daten, (0, 0, 595, 842))
        assert analyse.bild_schaeden(pdf) == {}, name


# ----------------------------------------------------------------------
# Befund Fehlalarm-Gründe: kurze lesbare Scan-Seite, Schlüsselwort im Fließtext
# ----------------------------------------------------------------------
def test_kurze_gut_lesbare_scanseite_ist_kein_grund(tmp_path, scan_modus):
    """Befund (mittel): Jede gut lesbare Scan-Seite mit weniger als 25 Wörtern hieß „Scan kaum lesbar“ (Unterschrifts-
    seite, „Seite 2 von 2“). Jetzt nur mit schlechter Lesung oder viel mehr Tinte, als die Wörter erklären."""
    doc = fitz.open()
    for zeilen in ([f"Herrn {NAME}", "Hauptstraße 12", "10115 Berlin",
                    "anbei erhalten Sie Ihren neuen Versicherungsschein für das kommende Jahr.",
                    "Mit freundlichen Grüßen", "Ihre Hanse Sachversicherung"],
                   ["Ort, Datum", "Unterschrift Versicherungsnehmer"]):
        text = doc.new_page()
        for i, z in enumerate(zeilen):
            text.insert_text((60, 72 + 16 * i), z, fontsize=11)
    scan = fitz.open()
    for seite in doc:
        neu = scan.new_page()
        neu.insert_image(neu.rect, pixmap=seite.get_pixmap(dpi=100, colorspace=fitz.csGRAY))
    pdf = tmp_path / "kurz.pdf"
    scan.save(pdf)
    woerter = {}
    for nr, seite in enumerate(doc):
        woerter[nr] = [(w[0], w[1], w[2], w[3], w[4]) for w in seite.get_text("words")]
    dienst = Attrappe(woerter)
    e = analysiere_pdf(pdf, STANDARD, [], [], ocr=dienst)
    assert all(0 < m.ocr_woerter < schwaerzung.KAUM_LESBAR_WOERTER for m in e["modell"].seiten)
    # Die Analyse warnt nicht mehr „kaum lesbar – Unbedingt manuell prüfen!“, sie gibt einen Hinweis (dieselbe Regel)
    assert "KAUM_LESBAR" not in codes(e) and not any("kaum lesbar" in w for w in e["warnungen"]), e["warnungen"]
    assert codes(e).count("WENIG_TEXT") == 2 and any("nur wenige Wörter" in h for h in e["hinweise"])
    s = schwaerze_pdf(pdf, e["funde"], ocr=dienst, ocr_cache=e["ocr_cache"], modell=e["modell"],
                      ziel_ordner=tmp_path / "aus")
    assert s["treffer"] and not any("kaum lesbar" in g for g in s["pruefen_gruende"]), s["pruefen_gruende"]
    # … und ohne das Modell der Analyse (Benchmark, alte Aufrufer) genauso
    s2 = schwaerze_pdf(pdf, e["funde"], ocr=dienst, ocr_cache=e["ocr_cache"], ziel_ordner=tmp_path / "ohne")
    assert s2["treffer"] and not any("kaum lesbar" in g for g in s2["pruefen_gruende"]), s2["pruefen_gruende"]


def test_schluesselwort_im_fliesstext_ist_kein_grund(tmp_path, scan_modus):
    """„Versicherungsschein“ und „IBAN“ im Fließtext einer Folgeseite (ohne Wert dahinter) sind kein Grund mehr;
    „Versicherungsschein vom 01.05.2024“ nennt keine Nummer. Ein ungeschwärzter Wert direkt dahinter bleibt einer."""
    pdf = bildseite(tmp_path / "folgeseite.pdf")
    zeilen = [f"Versicherungsnehmer {NAME}",
              "Bitte bewahren Sie diesen Versicherungsschein zusammen mit den Bedingungen auf.",
              "Ihr Versicherungsschein vom 01.05.2024 ersetzt alle früheren Fassungen.",
              "Die Beiträge werden per Lastschrift eingezogen; ändert sich Ihre IBAN, teilen Sie uns dies mit.",
              "Kinder, die nach Vertragsbeginn geboren werden, sind beitragsfrei mitversichert."]
    dienst = Attrappe({0: woerter_aus_zeilen(zeilen)})
    e = analysiere_pdf(pdf, STANDARD, [], [], ocr=dienst)
    name = [f for f in e["funde"] if f["text"] == NAME]
    s = schwaerze_pdf(pdf, name, ocr=dienst, ocr_cache=e["ocr_cache"], modell=e["modell"], ziel_ordner=tmp_path / "a")
    assert s["treffer"] and "SCHLUESSELWORT_OHNE_FUND" not in codes(s), s["warnungen"]
    # Gegenprobe: ein ungeschwärzter Wert direkt hinter dem Schlüsselwort (nur der Name wird geschwärzt)
    dienst2 = Attrappe({0: woerter_aus_zeilen(zeilen + ["Ihre Versicherungsschein-Nr. lautet HS-2023-445566."])})
    e2 = analysiere_pdf(pdf, STANDARD, [], [], ocr=dienst2)
    name2 = [f for f in e2["funde"] if f["text"] == NAME]
    s2 = schwaerze_pdf(pdf, name2, ocr=dienst2, ocr_cache=e2["ocr_cache"], modell=e2["modell"],
                       ziel_ordner=tmp_path / "b")
    assert "SCHLUESSELWORT_OHNE_FUND" in codes(s2) and s2["status"] == "pruefen"


@pytest.mark.parametrize("zeilen, kategorien, warnung", [
    # Formular in Spalten: das Etikett „Steuer-ID:“ steht allein, darunter schon das nächste Etikett mit SEINEM
    # (geschwärzten) Wert – der Steuer-ID-Wert selbst wurde nicht erkannt
    (["Steuer-ID:", "Sozialversicherungsnummer: 65 170839 J 003", "Ausweisnummer:"], {"namen", "svnr"}, True),
    # Etikett mit Doppelpunkt am Zeilenende, der (nicht erkannte) Wert ganz vorn in der nächsten Zeile
    (["Zulageberechtigt nach Paragraph 10a EStG. Steuer-ID der versicherten Person:",
      "24 568 099 736; Kindergeldnummer folgt"], {"namen"}, True),
    (["Geburtsdatum", "Geburtsort", "Staatsangehörigkeit"], {"namen"}, True),
    # Fließtext mit Zeilenumbruch hinter dem Schlüsselwort und eine Aufzählung: kein Grund
    (["Mitversichert sind Kinder, die während der Vertragslaufzeit geboren",
      "oder adoptiert werden, ab dem Tag der Geburt ohne zusätzlichen Beitrag.",
      "Anlagen: Nachtrag zum Versicherungsschein, Merkblatt"], {"namen"}, False),
])
def test_schluesselwort_als_formular_etikett_bleibt_grund(tmp_path, scan_modus, zeilen, kategorien, warnung):
    """Gegenprobe zu Befund 12 (in der Seed-7-Prüfung aufgefallen): Ein Etikett ohne Wert in derselben Zeile bleibt ein
    Grund für _PRUEFEN – der Wert steht in einer eigenen Zelle und wurde nicht erkannt; ein geschwärzter Wert eines
    ANDEREN Etiketts in der nächsten Zeile erledigt es nicht. Nur Fließtext ist kein Grund."""
    pdf = bildseite(tmp_path / "formular.pdf")
    dienst = Attrappe({0: woerter_aus_zeilen([f"Versicherungsnehmer {NAME}"] + zeilen)})
    e = analysiere_pdf(pdf, STANDARD, [], [], ocr=dienst)
    funde = [f for f in e["funde"] if f["kategorie"] in kategorien]
    assert {f["kategorie"] for f in funde} == kategorien, [(f["kategorie"], f["text"]) for f in e["funde"]]
    s = schwaerze_pdf(pdf, funde, ocr=dienst, ocr_cache=e["ocr_cache"], modell=e["modell"], ziel_ordner=tmp_path / "a")
    assert ("SCHLUESSELWORT_OHNE_FUND" in codes(s)) is warnung, s["warnungen"]
    if warnung:
        assert s["status"] == "pruefen" and "Seite 1: Schlüsselwort ohne geschwärzten Wert (OCR-Verleser?)" in \
            s["pruefen_gruende"]


# ----------------------------------------------------------------------
# Befund Punkt 6: Kundenanschrift im eigenen Briefkopf / in der Fußzeile
# ----------------------------------------------------------------------
@pytest.mark.parametrize("kopf, anschrift", [
    ("Max Mustermann · Fotografie\nHauptstraße 12 · 10115 Berlin\nTel. 030 1234567 · www.mustermann-foto.de\n",
     ["Hauptstraße 12", "10115 Berlin"]),
    ("Physiotherapie Anna Schmidt · Lindenweg 7 · 99423 Weimar · www.physio-schmidt.de\n",
     ["Lindenweg 7", "99423 Weimar"]),
])
def test_anschrift_im_absender_einer_person_wird_geschwaerzt(kopf, anschrift):
    """Befund Punkt 6 (hoch): Webadresse oder Bankverbindung im Briefkopf galten als Firmenbeleg – bei Selbständigen ist
    das die Anschrift der Kundin bzw. des Kunden. Abgewählt angeboten meldete sie die Restrisiko-Prüfung nie, Status
    „fertig“, die Anschrift blieb lesbar. Steht sie im Absender einer Person, wird sie geschwärzt."""
    text = (kopf + "\n\nMuster Versicherung AG\nKundenservice\nPostfach 10 11 12\n20007 Hamburg\n\n"
            "Kündigung meiner Berufshaftpflicht\n\nSehr geehrte Damen und Herren,\nhiermit kündige ich meine "
            "Versicherung zum 31.12.2024.\n\nMit freundlichen Grüßen")
    funde = analysiere_text(text, STANDARD, [], [], profil="hoch")
    for teil in anschrift:
        f = next(f for f in funde if f["text"] == teil)
        assert all(st["an"] for st in f["stellen"]), teil
        assert analyse.QUELLE_FIRMENANSCHRIFT not in f["quellen"]
    assert not any(teil in _lesbar(text, funde) for teil in anschrift)


def test_firmenanschriften_mit_rollen_bleiben_angeboten():
    """Gegenprobe: Firmenblock mit Ansprechpartner, Versicherer-Fußzeile mit Vorstand, Firmen-Briefkopf: weiter
    abgewählt angeboten (sonst kämen die Fehlverdachte zurück)."""
    texte = [BRIEFKOPF,
             "Muster Finanz GmbH\nIhr Ansprechpartner Max Schmidt\nHauptstraße 12a\n60311 Frankfurt am Main\n"
             "www.muster-finanz.de\n\nHerrn\nMax Mustermann\nBirkenallee 40\n12345 Musterstadt\n",
             "Herrn\nMax Mustermann\nBirkenallee 40\n12345 Musterstadt\n\nSehr geehrter Herr Mustermann,\nbla.\n\n"
             "Vorstand Dr. Hans Müller · Hauptstraße 12a · 60311 Frankfurt am Main · www.muster.de\n"]
    for text in texte:
        funde = analysiere_text(text, STANDARD, [], [], profil="hoch")
        firma = [f for f in funde if f["text"] in ("Hauptstraße 12a", "60311 Frankfurt am Main")]
        assert firma and all(not any(st["an"] for st in f["stellen"]) for f in firma), text


def test_kundenanschrift_aus_anderem_dokument_des_laufs(tmp_path):
    """Ist dieselbe Anschrift in einem anderen Dokument des Laufs als Kundenanschrift angehakt, wird sie auch dort
    geschwärzt, wo die Strukturregeln sie als Firmenanschrift abgewählt angeboten hatten."""
    a = textseiten(tmp_path / "police.pdf", ["Muster Versicherung AG · Postfach 10 11 12 · 20007 Hamburg", "",
                                             "Herrn", NAME, "Hauptstraße 12", "10115 Berlin", "",
                                             "Versicherungsschein Berufshaftpflicht"])
    b = textseiten(tmp_path / "brief.pdf", ["Studio Nord · Fotografie", "Hauptstraße 12 · 10115 Berlin",
                                            "Tel. 030 1234567 · www.studio-nord.de", "", "Muster Versicherung AG",
                                            "Postfach 10 11 12", "20007 Hamburg", "", "Kündigung zum 31.12.2024"])
    ea = analysiere_pdf(a, STANDARD, [], [], profil="hoch")
    eb = analysiere_pdf(b, STANDARD, [], [], profil="hoch")
    vorher = [f for f in eb["funde"] if f["text"] == "Hauptstraße 12"]
    if not vorher or any(st["an"] for st in vorher[0]["stellen"]):
        pytest.skip("Die Strukturregeln bieten die Anschrift hier nicht als Firmenanschrift an")
    analyse.weitergabe_anwenden([ea, eb])
    f = next(f for f in eb["funde"] if f["text"] == "Hauptstraße 12")
    assert all(st["an"] for st in f["stellen"]) and f["hinweis"] == analyse.HINWEIS_LAUF_KUNDENANSCHRIFT
    assert analyse.QUELLE_FIRMENANSCHRIFT not in f["quellen"]


# ----------------------------------------------------------------------
# M-25: Rückfall in den Ausgabeordner ist eine Warnung
# ----------------------------------------------------------------------
def test_zuordnung_rueckfall_in_den_ausgabeordner_ist_warnung(tmp_path, monkeypatch):
    """Lässt sich neben dem Ausgabeordner nicht schreiben, landet die Zuordnung doch im Ordner, der hochgeladen wird –
    das meldet die Schwärzung als Warnung, nicht nur als Hinweis."""
    monkeypatch.setattr(schwaerzung, "ZUORDNUNG_NEBEN_AUSGABEORDNER", True)
    pdf = textseiten(tmp_path / "Mustermann_Max.pdf", [f"Versicherungsnehmer: {NAME}"])
    (tmp_path / "_zuordnung_anonymisiert.txt").mkdir()          # dort kann keine Datei entstehen
    e = analysiere_pdf(pdf, STANDARD, [], [])
    s = schwaerze_pdf(pdf, e["funde"], ocr=Attrappe())
    meldung = next(m for m in s["meldungen"] if m["code"] == "ZUORDNUNG")
    assert meldung["art"] == "warnung" and (tmp_path / "anonymisiert" / "_zuordnung.txt").exists()
