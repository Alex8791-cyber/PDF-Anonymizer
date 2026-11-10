"""Runde 2, Paket „oberflaeche-eingang“: Eingangsprüfung, Passwort, Erststart-Hinweis, Programmsymbol, Laufprotokoll.

Geprüft wird, was beim Hinzufügen von Dateien passiert (Inhalt statt Endung, Fotos als PDF, Nicht-PDFs und
unlesbare Dateien gemeldet, lange Windows-Pfade, Ausgaben als Eingabe, geschützte PDFs), dazu Erststart-Hinweis
(M-19), Programmsymbol und Alt-Kürzel (M-27/M-67), PyMuPDF-Import mit Rückfall (M-37), Laufprotokoll ohne
Personendaten (M-61), EXE-Hilfetexte (M-70), Seitenverdacht ohne Lage in der Vorschau, gesperrter Schwärzen-Knopf
und Personendaten nur in Nebenkanälen (Schnittstelle des Pakets analyse-status: NEBENKANAL_FUND, „nebenkanaele“).
GUI-Tests laufen unter Xvfb (ohne Display übersprungen), die Dateiprüfungen überall.
"""

import importlib.util
import json
import os
import shutil
import struct
import subprocess
import sys
import tkinter as tk
from pathlib import Path

import pytest

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen kennen nur den Namen "fitz"
    import fitz

from anonymisierer import dateien, gui, vorschau_fenster

from conftest import braucht_ocr
from test_gui import (FUND_MAIL, FUND_NAME, FUND_TEL, TEXT, Verdacht, _display_wiederherstellen,  # noqa: F401
                      _prozesszustand, _screenshot, _screenshot_ordner, analysiere, app, dialoge, display_1366,
                      fake_analyse, fake_analyse_neu, fake_schwaerzung, fake_schwaerzung_neu, pdf_schreiben, pumpe,
                      root, starte_lauf, umgebung)

WURZEL = Path(__file__).resolve().parent.parent
gui_test = pytest.mark.skipif(not os.environ.get("DISPLAY") and sys.platform != "win32",
                              reason="kein Display (DISPLAY nicht gesetzt)")


@pytest.fixture(autouse=True)
def _temp_ordner(monkeypatch, tmp_path):
    """Arbeitskopien (Bild als PDF, entschlüsselte PDF) nie im echten Programmordner des Benutzers."""
    monkeypatch.setattr(dateien, "temp_basis", lambda: tmp_path / "programm_temp")
    monkeypatch.setattr(dateien, "_SITZUNG", None)
    monkeypatch.setattr(dateien, "_SITZUNG_BEENDET", False)      # ein Test davor hat ein Fenster geschlossen
    yield
    dateien.sitzung_aufraeumen()


# ----------------------------------------------------------------------
# Testdateien: Fotos (JPEG/PNG mit PyMuPDF, BMP/TIFF von Hand), geschützte PDF
# ----------------------------------------------------------------------
BRIEF = ("Muster Versicherung AG\nHerrn\nMax Mustermann\nHauptstrasse 12\n10115 Berlin\n\n"
         "IBAN: DE89 3704 0044 0532 0130 00\nTelefon: 0171 2345678\n")


def _pixmap(breite=595, hoehe=842, text=BRIEF, dpi=100, drehen=0):
    doc = fitz.open()
    seite = doc.new_page(width=breite, height=hoehe)
    seite.insert_text((60, 90) if not drehen else (90, hoehe - 40), text, fontsize=13, rotate=drehen)
    return seite.get_pixmap(dpi=dpi, alpha=False)


def jpeg_bytes(**kw) -> bytes:
    return _pixmap(**kw).tobytes("jpeg")


def png_bytes(**kw) -> bytes:
    return _pixmap(**kw).tobytes("png")


def exif_jpeg(orientierung: int) -> bytes:
    """JPEG eines Handyfotos: Text liegt quer im Bild, die EXIF-Angabe richtet es auf (6 = 90° im Uhrzeigersinn)."""
    roh = _pixmap(breite=842, hoehe=595, drehen=90).tobytes("jpeg")
    tiff = (b"II*\x00" + struct.pack("<I", 8) + struct.pack("<H", 1)
            + struct.pack("<HHIHH", 0x0112, 3, 1, orientierung, 0) + struct.pack("<I", 0))
    daten = b"Exif\x00\x00" + tiff
    return roh[:2] + b"\xff\xe1" + struct.pack(">H", len(daten) + 2) + daten + roh[2:]


def bmp_bytes(pix=None) -> bytes:
    pix = pix or _pixmap(breite=300, hoehe=150, text="Max Mustermann", dpi=72)
    b, h, s = pix.width, pix.height, pix.samples
    zeile = (b * 3 + 3) & ~3
    daten = bytearray()
    for y in range(h - 1, -1, -1):
        z = bytearray()
        for x in range(b):
            i = (y * b + x) * 3
            z += bytes((s[i + 2], s[i + 1], s[i]))
        daten += z + b"\x00" * (zeile - len(z))
    return (b"BM" + struct.pack("<IHHI", 54 + len(daten), 0, 0, 54)
            + struct.pack("<IiiHHIIiiII", 40, b, h, 1, 24, 0, len(daten), 2835, 2835, 0, 0) + bytes(daten))


def tiff_bytes(seiten: int = 1) -> bytes:
    """Unkomprimiertes RGB-TIFF (mehrseitig wie ein Fax), von Hand geschrieben."""
    bilder = [_pixmap(breite=300, hoehe=150, text=f"Seite {i + 1} Max Mustermann", dpi=72) for i in range(seiten)]
    aus = bytearray(b"II*\x00\x00\x00\x00\x00")
    erster_ifd = None
    vorher_naechster = None
    for pix in bilder:
        daten = bytes(pix.samples)
        bps_ofs = len(aus)
        aus += struct.pack("<HHH", 8, 8, 8)
        res_ofs = len(aus)
        aus += struct.pack("<IIII", 72, 1, 72, 1)
        daten_ofs = len(aus)
        aus += daten
        if len(aus) % 2:
            aus += b"\x00"
        ifd_ofs = len(aus)
        eintraege = [(256, 4, 1, pix.width), (257, 4, 1, pix.height), (258, 3, 3, bps_ofs), (259, 3, 1, 1),
                     (262, 3, 1, 2), (273, 4, 1, daten_ofs), (277, 3, 1, 3), (278, 4, 1, pix.height),
                     (279, 4, 1, len(daten)), (282, 5, 1, res_ofs), (283, 5, 1, res_ofs + 8), (296, 3, 1, 2)]
        aus += struct.pack("<H", len(eintraege))
        for tag, typ, anzahl, wert in eintraege:
            if typ == 3 and anzahl == 1:
                aus += struct.pack("<HHIHH", tag, typ, anzahl, wert, 0)
            else:
                aus += struct.pack("<HHII", tag, typ, anzahl, wert)
        naechster = len(aus)
        aus += struct.pack("<I", 0)
        if erster_ifd is None:
            erster_ifd = ifd_ofs
        if vorher_naechster is not None:
            struct.pack_into("<I", aus, vorher_naechster, ifd_ofs)
        vorher_naechster = naechster
    struct.pack_into("<I", aus, 4, erster_ifd)
    return bytes(aus)


def geschuetzte_pdf(pfad: Path, kennwort="geheim", text=TEXT) -> Path:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    doc.new_page().insert_text((40, 60), text, fontsize=9, fontname="helv")
    doc.save(pfad, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=kennwort, owner_pw="eigentuemer-" + kennwort)
    doc.close()
    return pfad


def schreibe(pfad: Path, daten: bytes) -> Path:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(daten)
    return pfad


def kundenordner(basis: Path) -> Path:
    """Ein typischer Kundenordner wie im Befund R-10 (Fotos, umbenanntes Foto, Mail, Systemdateien, Ausgaben)."""
    ordner = basis / "Kunde_Mustermann"
    pdf_schreiben(ordner / "Antrag.pdf")
    schreibe(ordner / "Ausweis_Mustermann.jpg", jpeg_bytes())
    schreibe(ordner / "Unterordner" / "Schaden.JPEG", jpeg_bytes())
    schreibe(ordner / "Foto_umbenannt.pdf", jpeg_bytes())                     # Handyfoto, als .pdf gespeichert
    schreibe(ordner / "Portal_Fehlerseite.pdf", b"<!DOCTYPE html><html><body>Fehler 404</body></html>")
    schreibe(ordner / "Mail_vom_Kunden.msg", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100)
    schreibe(ordner / "Portal_Download", (ordner / "Antrag.pdf").read_bytes())  # PDF ohne Endung
    schreibe(ordner / "desktop.ini", b"[.ShellClassInfo]")
    schreibe(ordner / "Thumbs.db", b"\x00" * 10)
    schreibe(ordner / "~$Brief.docx", b"\x00" * 10)
    pdf_schreiben(ordner / "anonymisiert" / "anonym_01.pdf")
    schreibe(ordner / "anonymisiert" / "_zuordnung.txt", b"anonym_01.pdf  <-  Antrag.pdf\n")
    return ordner


# ----------------------------------------------------------------------
# R-01 / R-10: Inhalt statt Endung, nichts fällt still weg
# ----------------------------------------------------------------------
def test_art_aus_kopf_erkennt_den_inhalt():
    erwartet = {
        b"%PDF-1.7\n": "pdf", b"Werbung\n%PDF-1.4\n": "pdf", jpeg_bytes(breite=50, hoehe=50, text="x"): "jpeg",
        png_bytes(breite=50, hoehe=50, text="x"): "png", tiff_bytes(): "tiff", bmp_bytes(): "bmp",
        b"GIF89a\x01\x00": "gif", b"RIFF\x00\x00\x00\x00WEBPVP8 ": "webp", b"\x00\x00\x00\x18ftypheic\x00": "heic",
        b"<!DOCTYPE html><html>": "html", b"\xef\xbb\xbf  <html><body>": "html",
        b'<?xml version="1.0"?><html xmlns="x">': "html", b'<svg xmlns="http://www.w3.org/2000/svg">': "svg",
        b'<?xml version="1.0"?><FictionBook>': "xml", b"PK\x03\x04rest": "office",
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00": "ole", b"{\\rtf1 Text}": "rtf", b"Herr Max Mustermann\n": "text",
        b"": "leer", bytes(range(256)): "unbekannt"}
    for kopf, art in erwartet.items():
        assert dateien.art_aus_kopf(kopf) == art, (kopf[:20], art)
    assert dateien.datei_art(Path("/gibt/es/nicht.pdf")) == "nicht_lesbar"
    # mit der Endung .pdf geht nur Unbestimmtes an die Engine (meldet „keine lesbare PDF-Datei“); alles, was
    # PyMuPDF als Nicht-PDF öffnet, nie (Absturz, R-01). „text“/„unbekannt“ aus datei_art heißt: auch MuPDF selbst
    # kann die Datei nicht öffnen – datei_art fragt MuPDF (Runde 2: UTF-16-Webseite, PNM, Photoshop, FB2 stürzten ab)
    for art in ("pdf", "text", "leer", "unbekannt", "nicht_lesbar"):
        assert dateien.fuer_engine_erlaubt(art), art
    for art in ("jpeg", "png", "tiff", "bmp", "gif", "html", "svg", "xml", "office", "webp", "heic", "ole", "rtf"):
        assert not dateien.fuer_engine_erlaubt(art), art


def test_ordner_scan_meldet_jede_nicht_pdf_und_findet_fotos(tmp_path):
    ordner = kundenordner(tmp_path)
    b = dateien.sammle_pdfs_bericht([str(ordner)])
    namen = {k: sorted(Path(p).name for p in v) for k, v in b.items() if isinstance(v, list)}
    assert namen["pdfs"] == ["Antrag.pdf"]
    assert namen["bilder"] == ["Ausweis_Mustermann.jpg", "Foto_umbenannt.pdf", "Schaden.JPEG"]
    assert b["arten"][ordner / "Foto_umbenannt.pdf"] == "jpeg"
    assert namen["keine_pdf"] == ["Mail_vom_Kunden.msg", "Portal_Fehlerseite.pdf"]
    assert b["arten"][ordner / "Portal_Fehlerseite.pdf"] == "html"
    assert namen["pdf_ohne_endung"] == ["Portal_Download"]
    assert namen["ausgaben"] == ["anonym_01.pdf"]
    # System- und Programmdateien sind kein „nicht geprüft“
    gemeldet = {n for k, v in namen.items() if k != "pdfs" for n in v}
    assert not gemeldet & {"desktop.ini", "Thumbs.db", "~$Brief.docx", "_zuordnung.txt"}
    assert namen["uebersprungen"] == [] and namen["leere_ordner"] == [] and namen["nicht_lesbar"] == []


def test_pdf_endung_mit_unbestimmtem_inhalt_geht_weiter_an_die_engine(tmp_path):
    """Leere/kaputte „PDFs“ meldet die Engine selbst („keine lesbare PDF-Datei“); Bilder, Webseiten, SVG, ZIP mit der
    Endung .pdf erreichen sie nie."""
    for name, daten in (("leer.pdf", b""), ("kaputt.pdf", b"kein pdf"), ("binaer.pdf", bytes(range(256)) * 4)):
        schreibe(tmp_path / name, daten)
    for name, daten in (("bild.pdf", png_bytes(breite=60, hoehe=60, text="x")), ("grafik.pdf", b"<svg></svg>"),
                        ("archiv.pdf", b"PK\x03\x04" + b"\x00" * 40), ("animation.pdf", b"GIF89a" + b"\x00" * 20)):
        schreibe(tmp_path / "andere" / name, daten)
    b = dateien.sammle_pdfs_bericht([str(tmp_path / n) for n in ("leer.pdf", "kaputt.pdf", "binaer.pdf")])
    assert sorted(p.name for p in b["pdfs"]) == ["binaer.pdf", "kaputt.pdf", "leer.pdf"]
    b = dateien.sammle_pdfs_bericht([str(tmp_path / "andere")])
    assert b["pdfs"] == [] and [p.name for p in b["bilder"]] == ["bild.pdf"]
    assert sorted(p.name for p in b["keine_pdf"]) == ["animation.pdf", "archiv.pdf", "grafik.pdf"]


def test_einzeln_gewaehlte_ausgabe_wird_markiert(tmp_path):
    """M-63: die Datei bleibt in „pdfs“ (Nachschwärzen bleibt möglich), steht aber auch in „ausgaben_einzeln“."""
    ausgabe = pdf_schreiben(tmp_path / "anonymisiert" / "anonym_01_PRUEFEN.pdf")
    original = pdf_schreiben(tmp_path / "Police.pdf")
    b = dateien.sammle_pdfs_bericht([str(ausgabe), str(original)])
    assert b["pdfs"] == [ausgabe, original] and b["ausgaben_einzeln"] == [ausgabe]


# ----------------------------------------------------------------------
# R-09: nichts Unlesbares wird still übergangen, lange Windows-Pfade
# ----------------------------------------------------------------------
def test_ordner_scan_meldet_unlesbare_unterordner(tmp_path, monkeypatch):
    ordner = tmp_path / "Kunde"
    pdf_schreiben(ordner / "A.pdf")
    pdf_schreiben(ordner / "gesperrt" / "B.pdf")
    pdf_schreiben(ordner / "zu_lang" / "C.pdf")
    echt = os.scandir

    def scandir(pfad):
        name = Path(os.fsdecode(pfad)).name
        if name == "gesperrt":
            raise PermissionError(13, "Permission denied", os.fsdecode(pfad))
        if name == "zu_lang":
            raise OSError(36, "File name too long", os.fsdecode(pfad))
        return echt(pfad)
    monkeypatch.setattr(dateien.os, "scandir", scandir)
    b = dateien.sammle_pdfs_bericht([str(ordner)])
    assert [p.name for p in b["pdfs"]] == ["A.pdf"]
    assert sorted(p.name for p in b["nicht_lesbar"]) == ["gesperrt", "zu_lang"]
    gruende = {p.name: g for p, g in b["gruende"].items()}
    assert gruende["gesperrt"] == "Zugriff verweigert" and gruende["zu_lang"].startswith("Pfad zu lang")
    # ein Ordner, dessen Inhalt nur unlesbar ist, ist nicht „ohne PDF-Dateien“ (Befund R-09)
    b = dateien.sammle_pdfs_bericht([str(ordner / "gesperrt")])
    assert b["leere_ordner"] == [] and len(b["nicht_lesbar"]) == 1


def test_linux_analogon_sehr_langer_pfad_wird_gemeldet(tmp_path):
    """Linux-Analogon zu MAX_PATH: ein Pfad über 4096 Zeichen. Früher fehlte die Datei ohne jede Meldung."""
    basis = tmp_path / "kundenordner"
    for name in ("A_vorher", "Z_nachher"):
        pdf_schreiben(basis / name / f"{name}.pdf")
    tief = os.open(basis, os.O_RDONLY)
    try:
        for i in range(22):
            name = f"Ebene_{i:02d}_" + "x" * 190
            os.mkdir(name, dir_fd=tief)
            neu = os.open(name, os.O_RDONLY, dir_fd=tief)
            os.close(tief)
            tief = neu
        fd = os.open("tief_versteckt.pdf", os.O_WRONLY | os.O_CREAT, dir_fd=tief)
        os.write(fd, b"%PDF-1.4\n%%EOF\n")
        os.close(fd)
    finally:
        os.close(tief)
    b = dateien.sammle_pdfs_bericht([str(basis)])
    assert [p.name for p in b["pdfs"]] == ["A_vorher.pdf", "Z_nachher.pdf"]
    assert b["nicht_lesbar"], "der zu lange Pfad muss gemeldet werden, nicht still fehlen"
    assert any(g.startswith("Pfad zu lang") for g in b["gruende"].values())


def test_lange_windows_pfade_mit_praefix():
    lang = "C:\\Users\\anna\\OneDrive - Makler GmbH\\Kunden\\" + "Mustermann, Max\\" * 12 + "Police.pdf"
    assert dateien.langpfad(lang, "win32") == "\\\\?\\" + lang
    assert dateien.langpfad("\\\\server\\freigabe\\Kunden\\a.pdf", "win32") == \
        "\\\\?\\UNC\\server\\freigabe\\Kunden\\a.pdf"
    assert dateien.langpfad("\\\\?\\C:\\x.pdf", "win32") == "\\\\?\\C:\\x.pdf"           # nicht doppelt
    assert dateien.langpfad("/home/a/b.pdf", "linux") == "/home/a/b.pdf"
    assert dateien.ohne_langpfad("\\\\?\\UNC\\server\\freigabe\\a.pdf") == "\\\\server\\freigabe\\a.pdf"
    assert dateien.ohne_langpfad("\\\\?\\" + lang) == lang
    # kurze Pfade bleiben, wie sie sind; erst lange bekommen das Präfix (Ausgabeordner und -name kommen dazu)
    assert str(dateien.pfad_fuer_programm("C:\\Kunden\\a.pdf", "win32")) == "C:\\Kunden\\a.pdf"
    assert str(dateien.pfad_fuer_programm(lang, "win32")).startswith("\\\\?\\C:\\Users")
    assert len(lang) >= dateien.LANGPFAD_AB


# ----------------------------------------------------------------------
# Arbeitskopien: Bild als PDF, entschlüsselte PDF, Aufräumen
# ----------------------------------------------------------------------
@pytest.mark.parametrize("art", ["jpeg", "png", "tiff", "bmp"])
def test_bild_als_pdf(tmp_path, art):
    daten = {"jpeg": jpeg_bytes, "png": png_bytes, "tiff": tiff_bytes, "bmp": bmp_bytes}[art]()
    bild = schreibe(tmp_path / f"Foto.{art}", daten)
    ziel = tmp_path / "Foto.pdf"
    assert dateien.bild_als_pdf(bild, ziel) == 1
    with fitz.open(ziel) as doc:
        assert doc.is_pdf and len(doc) == 1
        seite = doc[0]
        assert max(seite.rect.width, seite.rect.height) <= dateien.A4_LANG + 0.5
        assert seite.get_images() or seite.get_image_info(), "die Seite enthält das Bild"
    assert dateien.datei_art(ziel) == "pdf"


def test_bild_als_pdf_handyfoto_mehrseitiges_fax_und_kaputtes_bild(tmp_path):
    # EXIF „90° drehen“: die Seite steht hochkant wie das Foto auf dem Handy
    ziel = tmp_path / "exif.pdf"
    dateien.bild_als_pdf(schreibe(tmp_path / "IMG_0001.jpg", exif_jpeg(6)), ziel)
    with fitz.open(ziel) as doc:
        assert doc[0].rect.height > doc[0].rect.width
    # Handyfoto mit 72 dpi: 3000 x 2000 Pixel wären 106 x 71 cm – die Seite wird auf A4 verkleinert
    gross = schreibe(tmp_path / "gross.jpg", _pixmap(breite=3000, hoehe=2000, dpi=72).tobytes("jpeg"))
    dateien.bild_als_pdf(gross, tmp_path / "gross.pdf")
    with fitz.open(tmp_path / "gross.pdf") as doc:
        assert max(doc[0].rect.width, doc[0].rect.height) <= dateien.A4_LANG + 0.5
    # Fax mit zwei Seiten
    assert dateien.bild_als_pdf(schreibe(tmp_path / "fax.tif", tiff_bytes(2)), tmp_path / "fax.pdf") == 2
    # kaputtes Bild: ValueError mit Erklärung, keine halbe Datei
    with pytest.raises(ValueError):
        dateien.bild_als_pdf(schreibe(tmp_path / "kaputt.jpg", b"\xff\xd8\xff\xe0kaputt"), tmp_path / "k.pdf")
    assert not (tmp_path / "k.pdf").exists()


def test_geschuetzte_pdf_entschluesseln(tmp_path):
    pdf = geschuetzte_pdf(tmp_path / "Police.pdf")
    assert dateien.pdf_kennwort_noetig(pdf)
    assert not dateien.pdf_kennwort_noetig(pdf_schreiben(tmp_path / "offen.pdf"))
    ziel = tmp_path / "kopie.pdf"
    assert dateien.pdf_entschluesseln(pdf, "falsch", ziel) is False and not ziel.exists()
    assert dateien.pdf_entschluesseln(pdf, "geheim", ziel) is True
    with fitz.open(ziel) as doc:
        assert not doc.needs_pass and not doc.is_encrypted
        assert "Max Mustermann" in doc[0].get_text()
    assert b"geheim" not in ziel.read_bytes()


def test_arbeitskopien_liegen_im_programmordner_und_werden_aufgeraeumt(tmp_path):
    basis = dateien.temp_basis()
    ziel = dateien.arbeitskopie_ziel("Ausweis.jpg")
    assert ziel.name == "Ausweis.jpg.pdf" and str(ziel).startswith(str(basis))
    assert ziel.parent.parent.name.startswith(f"sitzung_{os.getpid()}_")
    ziel.write_bytes(b"%PDF-1.4\n")
    assert dateien.arbeitskopie_entfernen(ziel) and not ziel.parent.exists()
    fremd = schreibe(tmp_path / "Kunde" / "Police.pdf", b"%PDF-1.4\n")
    assert dateien.arbeitskopie_entfernen(fremd) is False and fremd.exists()     # nie außerhalb löschen
    # verwaiste Sitzung (Prozess beendet) wird beim Start gelöscht, die eigene nicht
    tot = basis / "sitzung_2147480000_abc"
    schreibe(tot / "kopie_x" / "Police.pdf", b"%PDF")
    eigene = dateien.sitzungsordner()
    assert dateien.alte_sitzungen_aufraeumen() == [tot] and not tot.exists() and eigene.exists()
    assert dateien.sitzung_aufraeumen() and not eigene.exists()


# ----------------------------------------------------------------------
# GUI: Hinzufügen (R-01, R-10, R-09, M-63)
# ----------------------------------------------------------------------
@gui_test
def test_gui_kundenordner_fotos_als_pdf_und_meldungen(app, umgebung, monkeypatch, dialoge):
    tmp = umgebung["tmp"]
    ordner = kundenordner(tmp)
    dialoge.antwort = True                                    # „Fotos als PDF übernehmen?“ -> ja
    app._pdfs_hinzufuegen([str(ordner)])
    assert dialoge.liste[0][1] == "Fotos als PDF übernehmen?" and "Foto_umbenannt.pdf" in dialoge.liste[0][2]
    namen = sorted(p.name for p in app.dateien)
    assert namen == ["Antrag.pdf", "Ausweis_Mustermann.jpg", "Foto_umbenannt.pdf", "Portal_Download", "Schaden.JPEG"]
    foto = ordner / "Ausweis_Mustermann.jpg"
    kopie = app._arbeitsdatei(foto)
    assert kopie != foto and kopie.exists() and dateien.datei_art(kopie) == "pdf"
    assert str(kopie).startswith(str(dateien.temp_basis()))
    assert app.beschriftungen[str(foto)].endswith("(Bild → PDF)")
    protokoll = app.protokoll_text()
    assert "Mail_vom_Kunden.msg" in protokoll and "Portal_Fehlerseite.pdf" in protokoll and "NICHT geprüft" in protokoll
    assert "desktop.ini" not in protokoll and "Thumbs.db" not in protokoll
    hinweis = app.datei_hinweis.cget("text")
    assert "3 Bild(er) als PDF übernommen" in hinweis and "2 keine PDF (nicht geprüft)" in hinweis
    assert app.warnungen_anzahl == 0                          # Auswahlmeldungen zählen nicht (GR-07)

    # Analyse und Schwärzung lesen die Arbeitskopie, die Ausgabe landet neben dem ORIGINAL
    aufrufe_a, aufrufe_s = [], []
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse_neu({"Ausweis_Mustermann.jpg.pdf": [FUND_TEL],
                                                                 "Antrag.pdf": [FUND_MAIL]}, aufrufe=aufrufe_a))
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung_neu(aufrufe_s))
    starte_lauf(app, app.analysieren)
    gelesen = {Path(a["pdf"]).name: Path(a["pdf"]) for a in aufrufe_a}
    assert gelesen["Ausweis_Mustermann.jpg.pdf"] == kopie and "Ausweis_Mustermann.jpg" not in gelesen
    starte_lauf(app, app.schwaerzen)
    zum_foto = next(a for a in aufrufe_s if Path(a["pdf"]) == kopie)
    assert zum_foto["ziel_ordner"] == ordner / "anonymisiert"
    ausgabe = app.ausgaben[foto]["pfad"]
    assert ausgabe.parent == ordner / "anonymisiert" and ausgabe.name.startswith("anonym_")
    assert not list(Path(dateien.temp_basis()).rglob("anonym_*.pdf")), "keine Ausgabe im Temp-Ordner"
    # Entfernen aus der Liste löscht die Arbeitskopie; Liste leeren alle
    app.datei_entfernen(str(foto))
    assert not kopie.exists() and foto.exists()
    uebrig = [app._arbeitsdatei(p) for p in app.dateien if p in app.arbeitskopien]
    assert uebrig and all(p.exists() for p in uebrig)
    app.liste_leeren()
    assert not any(p.exists() for p in uebrig) and app.arbeitskopien == {}


@gui_test
def test_gui_fotos_abgelehnt_nicht_still_weg(app, umgebung, monkeypatch, dialoge):
    tmp = umgebung["tmp"]
    ordner = kundenordner(tmp)
    dialoge.antwort = False
    app._pdfs_hinzufuegen([str(ordner)])
    assert sorted(p.name for p in app.dateien) == ["Antrag.pdf", "Portal_Download"]
    assert "3 Bild(er) nicht übernommen" in app.datei_hinweis.cget("text")
    assert "Ausweis_Mustermann.jpg" in app.protokoll_text() and "NICHT übernommen" in app.protokoll_text()
    assert not list(Path(dateien.temp_basis()).rglob("*.jpg.pdf"))
    # der Abschlussdialog der Schwärzung erinnert an die nicht geprüften Dateien (R-10)
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({"Antrag.pdf": [FUND_TEL]}))
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung([]))
    starte_lauf(app, app.analysieren)
    starte_lauf(app, app.schwaerzen)
    text = app.letzter_dialog[2]
    assert "NICHT geprüft" in text and "Ausweis_Mustermann.jpg" in text and "Mail_vom_Kunden.msg" in text


@gui_test
def test_gui_unlesbarer_ordner_wird_gemeldet(app, umgebung, monkeypatch, dialoge):
    tmp = umgebung["tmp"]
    pdf_schreiben(tmp / "Kunde" / "A.pdf")
    pdf_schreiben(tmp / "Kunde" / "gesperrt" / "B.pdf")
    echt = os.scandir

    def scandir(pfad):
        if Path(os.fsdecode(pfad)).name == "gesperrt":
            raise PermissionError(13, "Permission denied", os.fsdecode(pfad))
        return echt(pfad)
    monkeypatch.setattr(dateien.os, "scandir", scandir)
    app._pdfs_hinzufuegen([str(tmp / "Kunde")])
    assert [p.name for p in app.dateien] == ["A.pdf"]
    assert "1 nicht lesbar" in app.datei_hinweis.cget("text")
    assert "gesperrt (Zugriff verweigert)" in app.protokoll_text()


@gui_test
@braucht_ocr
def test_gui_umbenanntes_foto_mit_echter_engine_kein_absturz(app, umgebung, dialoge, monkeypatch):
    """R-01: Früher stürzte das ganze Programm (SIGSEGV) bei einem Foto mit der Endung .pdf ab. Jetzt wird es als
    PDF übernommen, per Texterkennung gelesen und geschwärzt – mit der echten Engine im selben Prozess."""
    from anonymisierer.ocr import OcrDienst
    monkeypatch.setattr(gui, "OcrDienst", OcrDienst)                 # echte Texterkennung statt Attrappe
    tmp = umgebung["tmp"]
    foto = schreibe(tmp / "Kunde" / "Foto_Schaden.pdf", jpeg_bytes(dpi=150))
    dialoge.antwort = True
    app._pdfs_hinzufuegen([str(foto)])
    assert app.dateien == [foto] and app.arbeitskopien[foto]["art"] == "bild"
    app.kategorie_vars["namen"].set(False)
    starte_lauf(app, app.analysieren, timeout=180)
    ergebnis = app.analyse_ergebnisse[foto]
    assert not ergebnis["fehler"] and any("DE89" in f["text"] for f in ergebnis["funde"])
    dialoge.antwort = False
    starte_lauf(app, app.schwaerzen, timeout=180)
    ausgabe = app.ausgaben[foto]["pfad"]
    assert ausgabe.parent == tmp / "Kunde" / "anonymisiert"
    with fitz.open(ausgabe) as doc:
        assert doc.is_pdf and "DE89" not in doc[0].get_text()


@gui_test
def test_gui_ersetzte_datei_erreicht_die_engine_nie(app, umgebung, monkeypatch, dialoge):
    """Wird eine Datei nach dem Hinzufügen durch ein Bild ersetzt, prüft die Oberfläche vor Analyse, Schwärzung
    und Vorschau noch einmal den Inhalt – PyMuPDF bekommt nie eine Nicht-PDF (R-01)."""
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "Police.pdf")
    app._pdfs_hinzufuegen([str(pdf)])
    pdf.write_bytes(jpeg_bytes(breite=100, hoehe=100, text="x"))

    def nie(*a, **k):
        raise AssertionError("die Engine darf keine Nicht-PDF bekommen")
    monkeypatch.setattr(gui, "analysiere_pdf", nie)
    starte_lauf(app, app.analysieren)
    e = app.analyse_ergebnisse[pdf]
    assert "keine PDF, sondern ein Foto (JPEG)" in e["fehler"] and "KEIN_PDF" in gui.meldungs_codes(e)
    assert "Nicht analysierbar" in app.letzter_dialog[2]


@gui_test
def test_gui_ausgabe_als_eingabe_fragt_nach(app, umgebung, dialoge):
    """M-63: eine Ausgabe des Programms wird nur nach Rückfrage (Standard „Nein“) aufgenommen."""
    tmp = umgebung["tmp"]
    ausgabe = pdf_schreiben(tmp / "KundeA" / "anonymisiert" / "anonym_01_PRUEFEN.pdf")
    dialoge.antwort = False
    app._pdfs_hinzufuegen([str(ausgabe)])
    art, titel, text = dialoge.liste[-1]
    assert art == "askyesno" and titel == "Bereits anonymisierte Datei" and "ORIGINAL" in text
    assert app.dateien == [] and "nicht hinzugefügt" in app.datei_hinweis.cget("text")
    dialoge.antwort = True
    app._pdfs_hinzufuegen([str(ausgabe)])
    assert app.dateien == [ausgabe] and "trotzdem hinzugefügt" in app.protokoll_text()


# ----------------------------------------------------------------------
# R-12: Kennwort
# ----------------------------------------------------------------------
@gui_test
def test_gui_kennwort_abfragen_entschluesseln_und_nirgends_speichern(app, umgebung, monkeypatch, dialoge):
    tmp = umgebung["tmp"]
    a = geschuetzte_pdf(tmp / "Kunde" / "Abrechnung_1.pdf")
    b = geschuetzte_pdf(tmp / "Kunde" / "Abrechnung_2.pdf")       # gleiches Kennwort: nur einmal fragen
    c = geschuetzte_pdf(tmp / "Kunde" / "Police.pdf", kennwort="anders")
    antworten = iter(["falsch", "geheim", None])
    abfragen = []

    def abfrage(pfad, fehlversuch=False):
        abfragen.append((Path(pfad).name, fehlversuch))
        return next(antworten)
    monkeypatch.setattr(app, "_kennwort_abfragen", abfrage)
    app._pdfs_hinzufuegen([str(tmp / "Kunde")])
    assert abfragen == [("Abrechnung_1.pdf", False), ("Abrechnung_1.pdf", True), ("Police.pdf", False)]
    assert app.dateien == [a, b] and c not in app.arbeitskopien    # Police.pdf übersprungen
    for pdf in (a, b):
        kopie = app._arbeitsdatei(pdf)
        assert kopie.name == pdf.name and str(kopie).startswith(str(dateien.temp_basis()))
        with fitz.open(kopie) as doc:
            assert not doc.needs_pass and "Max Mustermann" in doc[0].get_text()
        assert app.beschriftungen[str(pdf)].endswith("(Kennwort entfernt)")
    protokoll = app.protokoll_text()
    assert "Ausgabedatei hat KEIN Kennwort" in protokoll
    assert "Ohne Kennwort übersprungen" in protokoll and "Police.pdf" in protokoll
    assert "1 ohne Kennwort übersprungen" in app.datei_hinweis.cget("text")
    # das Kennwort steht nirgends: Protokoll, Einstellungen, Laufprotokoll
    app.einstellungen_speichern()
    for text in (protokoll, dateien.einstellungen_pfad().read_text(encoding="utf-8"), app.laufprotokoll_text()):
        assert "geheim" not in text and "falsch" not in text
    # Analyse und Schwärzung lesen die entschlüsselte Kopie, die Ausgabe liegt neben dem Original
    aufrufe = []
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse_neu({"Abrechnung_1.pdf": [FUND_TEL],
                                                                 "Abrechnung_2.pdf": [FUND_TEL]}))
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung_neu(aufrufe))
    starte_lauf(app, app.analysieren)
    starte_lauf(app, app.schwaerzen)
    assert {Path(x["pdf"]) for x in aufrufe} == {app._arbeitsdatei(a), app._arbeitsdatei(b)}
    assert app.ausgaben[a]["pfad"].parent == tmp / "Kunde" / "anonymisiert"
    with fitz.open(app.ausgaben[a]["pfad"]) as doc:
        assert not doc.needs_pass                                   # Ausgabe ohne Kennwort, wie angekündigt
    # Schließen löscht die entschlüsselten Kopien
    kopien = [app._arbeitsdatei(a), app._arbeitsdatei(b)]
    app.schliessen()
    assert not any(k.exists() for k in kopien)


@gui_test
def test_kennwort_dialog_ist_maskiert(app, umgebung):
    pdf = umgebung["tmp"] / "Police.pdf"
    erfasst = {}

    def eingeben():
        dialog = app.kennwort_dialog
        erfasst["show"] = dialog.eingabe.cget("show")
        erfasst["titel"] = dialog.fenster.title()
        erfasst["fehler"] = dialog.fehler_label.cget("text")
        dialog.eingabe.insert(0, "geheim")
        dialog.ok_knopf.invoke()
    app.root.after(150, eingeben)
    assert app._kennwort_abfragen(pdf, fehlversuch=True) == "geheim"
    assert erfasst["show"] == "•" and erfasst["titel"] == gui.KENNWORT_TITEL and "falsch" in erfasst["fehler"]
    app.root.after(150, lambda: app.kennwort_dialog.fenster.event_generate("<Escape>"))
    assert app._kennwort_abfragen(pdf) is None
    assert app.kennwort_dialog is None


# ----------------------------------------------------------------------
# M-19: Hinweis beim ersten Start
# ----------------------------------------------------------------------
@gui_test
def test_erststart_hinweis_erscheint_einmal(umgebung, dialoge, monkeypatch):
    monkeypatch.setattr(gui, "DND_VERFUEGBAR", False)
    monkeypatch.setattr(gui, "ERSTSTART_NACH_MS", 10)
    app = gui.main(ereignisschleife=False)
    try:
        app.root.tk.willdispatch()
        assert pumpe(app.root, lambda: app.hinweis_dialog is not None, timeout=5)
        dialog = app.hinweis_dialog
        assert dialog.fenster.title() == gui.ERSTSTART_TITEL
        text = dialog.text_label.cget("text")
        for teil in ("PSEUDONYMISIERT", "Schutzstufe", "Diagnosen", "bevor Sie es weitergeben", "in der Vorschau",
                     "Verantwortung", "bleibt bei Ihnen"):
            assert teil in text, teil
        assert dialog.nicht_mehr.get() is True                      # „Nicht mehr anzeigen“ vorbelegt
        dialog.bestaetigen()
        assert json.loads(dateien.einstellungen_pfad().read_text(encoding="utf-8"))["hinweis_gelesen"] is True
    finally:
        app.schliessen()
    zweite = gui.main(ereignisschleife=False)
    try:
        zweite.root.tk.willdispatch()
        pumpe(zweite.root, lambda: zweite.hinweis_dialog is not None, timeout=0.5)
        assert zweite.hinweis_dialog is None                        # nur einmal
        # jederzeit über die Hilfe
        hilfe = [zweite.hilfe_menue.entrycget(i, "label") for i in range(zweite.hilfe_menue.index("end") + 1)
                 if zweite.hilfe_menue.type(i) == "command"]
        assert "Hinweise vor der Nutzung …" in hilfe
        zweite.hilfe_hinweis()
        assert zweite.hinweis_dialog is not None and zweite.hinweis_dialog.fenster.winfo_exists()
        zweite.hinweis_dialog.nicht_mehr.set(False)                 # wieder beim Start zeigen
        zweite.hinweis_dialog.bestaetigen()
        assert zweite.hinweis_gelesen is False
    finally:
        zweite.schliessen()
    assert "Hinweise vor der Nutzung" in gui.GRENZEN_TEXT


# ----------------------------------------------------------------------
# M-27 / M-67: Programmsymbol, Alt-Kürzel
# ----------------------------------------------------------------------
def _programmsymbol_modul():
    spec = importlib.util.spec_from_file_location("programmsymbol", WURZEL / "werkzeuge" / "programmsymbol.py")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def test_icon_ico_im_projekt_und_generator_ohne_pil(tmp_path):
    modul = _programmsymbol_modul()
    for quelle in (WURZEL / "icon.ico", modul.symbol_erzeugen(tmp_path / "neu.ico")):
        eintraege = modul.ico_lesen(quelle.read_bytes())
        assert sorted(e["groesse"] for e in eintraege) == [16, 32, 48, 256]
        for e in eintraege:
            assert e["bits"] == 32
            if e["groesse"] == 256:
                assert e["art"] == "png"
                pix = fitz.Pixmap(e["daten"])
                assert (pix.width, pix.height) == (256, 256)
            else:
                assert e["art"] == "bitmap"
                groesse, breite, hoehe = struct.unpack_from("<Iii", e["daten"], 0)
                assert (groesse, breite, hoehe) == (40, e["groesse"], 2 * e["groesse"])
                # Alphakanal: Ecken durchsichtig, Mitte (Blatt) deckend
                n = e["groesse"]
                pixel = e["daten"][40:40 + n * n * 4]
                alpha = [pixel[i + 3] for i in range(0, len(pixel), 4)]
                assert alpha[0] == 0 and alpha[n * (n // 2) + n // 2] == 255
    assert "PIL" not in (WURZEL / "werkzeuge" / "programmsymbol.py").read_text(encoding="utf-8").replace(
        "ohne PIL", "")


@gui_test
def test_fenstersymbol_und_alt_kuerzel(app):
    assert [p.width() for p in app._symbole] == list(gui.SYMBOL_GROESSEN)
    # die Kürzel-Buchstaben sind unterstrichen und gebunden – auch als Großbuchstabe (Feststelltaste)
    for knopf, buchstabe in ((app.analyse_knopf, "a"), (app.start_knopf, "s"), (app.vorschau_knopf, "v")):
        index = int(knopf.cget("underline"))
        assert index >= 0 and knopf.cget("text")[index].lower() == buchstabe
        assert app.root.bind(f"<Alt-{buchstabe}>") and app.root.bind(f"<Alt-{buchstabe.upper()}>")
    menues = [app.menue.entrycget(i, "label") for i in range(app.menue.index("end") + 1)
              if app.menue.type(i) == "cascade"]
    assert menues == ["Datei", "Kundenliste", "Hilfe"]
    assert all(int(app.menue.entrycget(i, "underline")) == 0 for i in range(app.menue.index("end") + 1)
               if app.menue.type(i) == "cascade")
    if sys.platform != "win32" and os.environ.get("DISPLAY") and shutil.which("xdotool") and shutil.which("xprop"):
        # Gegenprobe wie im Befund: das echte X-Fenster trägt _NET_WM_ICON (vorher: „no such atom“)
        titel = f"Symboltest {os.getpid()}"
        app.root.title(titel)
        app.root.update()
        ids = subprocess.run(["xdotool", "search", "--name", f"^{titel}$"], capture_output=True, text=True,
                             timeout=10).stdout.split()
        assert ids, "Hauptfenster nicht gefunden"
        assert any("_NET_WM_ICON(CARDINAL)" in subprocess.run(["xprop", "-id", i, "_NET_WM_ICON"], capture_output=True,
                                                              text=True, timeout=10).stdout for i in ids)


# ----------------------------------------------------------------------
# M-37: PyMuPDF unter dem Namen „pymupdf“, Rückfall auf „fitz“
# ----------------------------------------------------------------------
def test_pymupdf_import_ohne_fitz_alias():
    for datei in ("pdf_anonymisierer.py", "anonymisierer/gui.py", "anonymisierer/vorschau_fenster.py",
                  "anonymisierer/gui_attrappen.py"):
        quelle = (WURZEL / datei).read_text(encoding="utf-8")
        assert "import pymupdf as fitz" in quelle and "import fitz" in quelle, datei
        assert quelle.index("import pymupdf as fitz") < quelle.index("    import fitz"), datei
    # Fällt der veraltete Alias „fitz“ weg, startet das Programm trotzdem (früher: „PyMuPDF fehlt“)
    code = ("import sys; sys.modules['fitz'] = None; sys.path.insert(0, sys.argv[1]); "
            "import anonymisierer.gui, anonymisierer.vorschau_fenster, anonymisierer.gui_attrappen; "
            "import pdf_anonymisierer; print('ok', pdf_anonymisierer._pymupdf_laden().__name__)")
    ergebnis = subprocess.run([sys.executable, "-W", "ignore", "-c", code, str(WURZEL)], capture_output=True,
                              text=True, timeout=180, env=dict(os.environ, DISPLAY=""))
    assert ergebnis.returncode == 0, ergebnis.stderr[-800:]
    assert ergebnis.stdout.strip().endswith("ok pymupdf")


# ----------------------------------------------------------------------
# M-70: Hilfetexte in der EXE
# ----------------------------------------------------------------------
def test_exe_texte_nennen_kein_installieren_bat(monkeypatch):
    import pdf_anonymisierer as pa
    texte = ["Deutsches Sprachmodell fehlt (Installieren.bat erneut ausführen).",
             "Paket 'spacy' fehlt (Installieren.bat erneut ausführen).",
             "Tesseract-Sprachdaten nicht gefunden – Der Ordner »tessdata« mit deu.traineddata muss neben dem "
             "Programm liegen (Installieren.bat erneut ausführen).",
             "Keine OCR-Sprachdatei gefunden – Installieren.bat erneut ausführen."]
    # die Texte der Engine stehen wirklich so im Quelltext (sonst greift die Übersetzung ins Leere)
    quellen = "".join((WURZEL / "anonymisierer" / n).read_text(encoding="utf-8") for n in ("namen.py", "ocr.py"))
    for teil in ("(Installieren.bat erneut ausführen)", "Installieren.bat erneut ausführen"):
        assert teil in quellen
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert gui._text_fuer_exe(texte[0]) == texte[0]
    assert "Installieren.bat" in pa._meldung_paket_fehlt()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    for text in texte:
        neu = gui._text_fuer_exe(text)
        assert "Installieren.bat" not in neu and ("neu entpacken" in neu or "_internal" in neu), neu
    assert "_internal\\tessdata" in gui._text_fuer_exe(texte[2])
    assert "Installieren.bat" not in pa._meldung_paket_fehlt() and "neu entpacken" in pa._meldung_paket_fehlt()


@gui_test
def test_exe_texte_im_protokoll_und_dialog(app, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    app._log("⚠ a.pdf: Namenserkennung inaktiv: Deutsches Sprachmodell fehlt (Installieren.bat erneut ausführen).",
             "warnung")
    app._dialog("info", "Test", "Paket 'spacy' fehlt (Installieren.bat erneut ausführen).")
    assert "Installieren.bat" not in app.protokoll_text() and "Installieren.bat" not in app.letzter_dialog[2]


# ----------------------------------------------------------------------
# M-61: Laufprotokoll ohne Personendaten
# ----------------------------------------------------------------------
@gui_test
def test_laufprotokoll_ohne_personendaten(app, umgebung, monkeypatch, dialoge):
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "Mustermann_Max" / "Police_Mustermann_Max.pdf")
    app.nie_feld.insert("1.0", "Allianz Lebensversicherungs-AG\nMakler Schmidt")
    app.immer_feld.insert("1.0", "Erika Mustermann")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse_neu(
        {"Police_Mustermann_Max.pdf": [FUND_NAME, FUND_TEL, FUND_MAIL]},
        meldungen_je_datei={"Police_Mustermann_Max.pdf": [{"art": "warnung", "code": "OCR_GELESEN",
                                                            "text": "1 Seite per OCR gelesen: Max Mustermann",
                                                            "seite": None}]}))
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung_neu([]))
    analysiere(app, [pdf])
    app._umschalten(f"{pdf}::1")                                   # Telefon abgewählt
    dialoge.antwort = False
    starte_lauf(app, app.schwaerzen)
    app.ausgabe_freigeben(pdf)
    menue = [app.datei_menue.entrycget(i, "label") for i in range(app.datei_menue.index("end") + 1)
             if app.datei_menue.type(i) == "command"]
    assert "Protokoll speichern …" in menue
    ziel = app.protokoll_speichern(tmp / "protokoll.txt")
    text = ziel.read_text(encoding="utf-8-sig")
    for erwartet in (f"Programmversion: {gui.__version__}", "PyMuPDF: ", "spaCy: ", "Sprachmodell: ",
                     "Schutzstufe: Hoch (Standard)", "Aktive Kategorien: ", "NIE-Liste: 2 ", "IMMER-Liste: 1 ",
                     "Dokument 1", "anonym_01_PRUEFEN.pdf (Dokument 1)", "⚠ prüfen", "Meldungen: OCR_GELESEN",
                     "Freigabe vor Weitergabe: an", "anonym_01_PRUEFEN.pdf freigegeben → anonym_01.pdf"):
        assert erwartet in text, erwartet
    namen = {e[0]: e[1] for e in gui.KATEGORIEN}
    analyse_zeile = next(z for z in text.splitlines() if z.startswith("  Dokument 1"))
    schwaerz_zeile = next(z for z in text.splitlines() if z.startswith("  anonym_01_PRUEFEN.pdf"))
    assert f"{namen['telefon']} 1" in analyse_zeile                      # bei der Analyse noch angehakt
    assert f"{namen['email']} 1" in schwaerz_zeile and namen["telefon"] not in schwaerz_zeile   # abgewählt
    assert "2 Stelle(n) ersetzt" in schwaerz_zeile
    # keine Inhalte, keine Originalnamen, keine Ordner, keine NIE-/IMMER-Einträge
    for verboten in ("Mustermann", "0171", "example.de", "Allianz", "Schmidt", "Erika", str(tmp), "Police"):
        assert verboten not in text, verboten
    assert ziel.name in app.protokoll_text()


@gui_test
def test_protokoll_speichern_ohne_lauf(app, dialoge):
    assert app.protokoll_speichern() is None and dialoge.liste[-1][1] == "Protokoll speichern"


# ----------------------------------------------------------------------
# Punkt 11: Seitenverdacht ohne Lage in der Vorschau
# ----------------------------------------------------------------------
@gui_test
def test_seitenverdacht_rahmen_liste_und_vorauswahl(app, umgebung, monkeypatch, dialoge, tmp_path_factory):
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "a.pdf", seiten=2)
    with fitz.open(pdf) as doc:
        stelle = doc[0].search_for("0171 2345678")[0]
    ganze_seite = Verdacht(1, -1, -1, "Seite 2", "Seite nicht lesbar – bitte selbst prüfen", [])
    mit_lage = Verdacht(0, 5, 17, "0171 2345678", "Ziffernfolge", [stelle])
    aufrufe = []
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse_neu({"a.pdf": [FUND_MAIL]}, seiten=2))
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung_neu(aufrufe, verdacht_fuer={"a.pdf": [ganze_seite,
                                                                                                    mit_lage]}))
    analysiere(app, [pdf])
    dialoge.antwort = False
    starte_lauf(app, app.schwaerzen)
    fenster = app.vorschau_oeffnen(pdf, modus="nachher", seite=1)
    pumpe(app.root, timeout=0.3)
    eintraege = list(fenster.verdacht_liste.get(0, "end"))
    assert eintraege[0] == "S. 2 (ganze Seite): Seite nicht lesbar – bitte selbst prüfen"
    assert eintraege[1].startswith("S. 1: „0171 2345678“")
    assert fenster.verdacht_liste.curselection() == (1,)            # nur die Stelle mit Lage vorausgewählt
    assert "ganze Seite" in fenster.verdacht_titel.cget("text")
    rahmen = fenster.canvas.find_withtag("ganze_seite")
    assert len(rahmen) == 1
    x0, y0, x1, y1 = fenster.canvas.coords(rahmen[0])
    bild_b, bild_h = fenster._bild.width(), fenster._bild.height()
    assert x1 - x0 > 0.95 * bild_b and y1 - y0 > 0.95 * bild_h      # um die ganze Seite
    assert fenster.canvas.itemcget(rahmen[0], "outline") == vorschau_fenster.FARBE_VERDACHT
    _screenshot(app.root, None, _screenshot_ordner(tmp_path_factory) / "vorschau_ganze_seite.png")
    # Nachschwärzen mit der Vorauswahl: kein Dialog „keine Lage bekannt“, nur die Stelle mit Lage
    dialoge.liste.clear()
    vorher = app.laeufe_beendet
    fenster.nachschwaerzen()
    assert app.laeuft and not any(d[1] == "Nachschwärzen nicht möglich" for d in dialoge.liste)
    assert pumpe(app.root, lambda: app.laeufe_beendet > vorher, timeout=30)
    pumpe(app.root, timeout=0.2)
    assert set(aufrufe[-1]["manuelle_bereiche"]) == {0}
    # ausdrücklich nur den Seitenverdacht markiert: ehrlicher Hinweis statt stillem Nichts
    fenster = app.vorschauen[pdf]
    fenster.verdacht_liste.selection_clear(0, "end")
    fenster.verdacht_liste.selection_set(0)
    fenster.nachschwaerzen()
    assert not app.laeuft and dialoge.liste[-1][1] == "Nachschwärzen nicht möglich"


# ----------------------------------------------------------------------
# Punkt 12: gesperrter Schwärzen-Knopf ist sichtbar anders
# ----------------------------------------------------------------------
@gui_test
def test_gesperrter_hauptknopf_sieht_gesperrt_aus(app, umgebung, monkeypatch, tmp_path_factory):
    assert str(app.start_knopf.cget("state")) == "disabled"
    assert app.start_knopf.cget("bg") == gui.FARBE_KNOPF_GESPERRT != gui.FARBE_AKZENT
    assert app.start_knopf.cget("disabledforeground") == gui.FARBE_KNOPF_GESPERRT_TEXT
    assert app.analyse_knopf.cget("bg") == gui.FARBE_AKZENT
    _screenshot(app.root, None, _screenshot_ordner(tmp_path_factory) / "knopf_gesperrt.png")
    pdf = pdf_schreiben(umgebung["tmp"] / "a.pdf")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({"a.pdf": [FUND_TEL]}))
    analysiere(app, [pdf])
    assert str(app.start_knopf.cget("state")) == "normal" and app.start_knopf.cget("bg") == gui.FARBE_AKZENT
    app._lauf_starten("analyse")                                 # während eines Laufs: beide grau
    assert app.analyse_knopf.cget("bg") == gui.FARBE_KNOPF_GESPERRT and int(app.analyse_knopf.cget("underline")) == -1
    app._lauf_beenden()
    assert app.analyse_knopf.cget("bg") == gui.FARBE_AKZENT and int(app.analyse_knopf.cget("underline")) == 2
    _screenshot(app.root, None, _screenshot_ordner(tmp_path_factory) / "knopf_bereit.png")


# ----------------------------------------------------------------------
# Punkt 13: Personendaten nur in Nebenkanälen (Schnittstelle analyse-status)
# ----------------------------------------------------------------------
NEBENKANAELE = {"metadaten": 2, "lesezeichen": 1, "anhaenge": 1, "xfa": False, "personenbezug": True}


def fake_analyse_nebenkanal(nebenkanal_fuer=("Kuendigung.pdf",), funde=None):
    def analysiere_pdf(pdf_pfad, aktive, whitelist, immer_schwaerzen, melde=None, fortschritt=None, abbruch=None,
                       ocr=None, profil="hoch", kundenliste=None, lauf=None):
        nk = pdf_pfad.name in nebenkanal_fuer
        meldungen = [{"art": "warnung", "code": "NEBENKANAL_FUND", "seite": None,
                      "text": "Personenbezogene Daten in Metadaten (2), Lesezeichen (1), Anhängen (1)"}] if nk else []
        return {"datei": pdf_pfad, "funde": [dict(f) for f in (funde or {}).get(pdf_pfad.name, [])],
                "warnungen": [m["text"] for m in meldungen], "hinweise": [], "fehler": None, "seiten": 1,
                "ocr_seiten": 0, "ocr_cache": {}, "meldungen": meldungen,
                "nebenkanaele": dict(NEBENKANAELE) if nk else {"metadaten": 0, "lesezeichen": 0, "anhaenge": 0,
                                                               "xfa": False, "personenbezug": False}}
    return analysiere_pdf


def fake_schwaerzung_nebenkanal(aufrufe):
    def schwaerze_pdf(pdf_pfad, funde, melde=None, fortschritt=None, abbruch=None, ocr=None, ocr_cache=None,
                      ziel_ordner=None, modell=None, manuelle_bereiche=None, manuelle_stellen=None,
                      freigabe_erforderlich=False, profil="hoch", nebenkanaele=None):
        aufrufe.append({"pdf": pdf_pfad, "funde": list(funde), "nebenkanaele": nebenkanaele})
        ordner = Path(ziel_ordner) if ziel_ordner else pdf_pfad.parent / "anonymisiert"
        ordner.mkdir(parents=True, exist_ok=True)
        ausgabe = ordner / ("anonym_01_PRUEFEN.pdf" if freigabe_erforderlich else "anonym_01.pdf")
        ausgabe.write_bytes(pdf_pfad.read_bytes())
        return {"original": pdf_pfad, "ausgabe": ausgabe, "treffer": len(funde), "uebersprungen": 0,
                "warnungen": [], "hinweise": ["Entfernt bzw. eingebrannt: Metadaten/XMP, 2 Lesezeichen"], "reste": [],
                "fehler": None, "verdacht": [], "status": "pruefen" if freigabe_erforderlich else "fertig",
                "meldungen": [{"art": "hinweis", "code": "NEBENKANAL_ENTFERNT", "text": "…", "seite": None}]}
    return schwaerze_pdf


@gui_test
def test_nebenkanal_fund_ohne_seitenfund(app, umgebung, monkeypatch, dialoge):
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "Kuendigung.pdf")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse_nebenkanal())
    aufrufe = []
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung_nebenkanal(aufrufe))
    analysiere(app, [pdf])
    art, titel, text = app.letzter_dialog
    assert art == "warning" and "keine personenbezogenen Daten" not in text and titel != "Keine Funde"
    assert "Metadaten (2)" in text and "Anhänge (1)" in text and "bereinigte Ausgabe" in text
    assert "Original NICHT weitergeben" in text
    assert "werden entfernt" in app.baum.set(str(pdf), "kategorie")
    assert str(app.start_knopf.cget("state")) == "normal"          # Schwärzen erlaubt, obwohl 0 Funde
    starte_lauf(app, app.schwaerzen)
    assert aufrufe and aufrufe[0]["funde"] == [] and aufrufe[0]["nebenkanaele"]["personenbezug"] is True
    assert app.ausgaben[pdf]["pfad"].exists()
    assert "1 von 1 Datei(en) geschrieben" in app.protokoll_text()


@gui_test
def test_nebenkanal_fund_neben_seitenfunden_und_alte_engine(app, umgebung, monkeypatch, dialoge):
    """Mit Seitenfunden steht der Nebenkanal als eigener Block im Dialog; eine Engine ohne den Parameter
    „nebenkanaele“ bekommt ihn nicht (sie prüft dann selbst oder meldet „keine Ausgabe“ – nie still)."""
    tmp = umgebung["tmp"]
    a = pdf_schreiben(tmp / "Kuendigung.pdf")
    b = pdf_schreiben(tmp / "Antrag.pdf")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse_nebenkanal(funde={"Antrag.pdf": [FUND_TEL]}))
    aufrufe = []
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung_neu(aufrufe, treffer_null=("Kuendigung.pdf",),
                                                                   warnung_bei_null=gui.WARNUNG_KEIN_TREFFER))
    analysiere(app, [a, b])
    text = app.letzter_dialog[2]
    assert "Personenbezogene Daten in versteckten Teilen" in text and "Kuendigung.pdf" in text
    dialoge.antwort = False
    starte_lauf(app, app.schwaerzen)
    assert {Path(x["pdf"]).name for x in aufrufe} == {"Kuendigung.pdf", "Antrag.pdf"}
    assert "OHNE Ausgabedatei" in app.letzter_dialog[2] and "Kuendigung.pdf" in app.letzter_dialog[2]


# ----------------------------------------------------------------------
# Layout der neuen Dialoge auf 1366x768 und 150 %
# ----------------------------------------------------------------------
@gui_test
@pytest.mark.parametrize("skalierung", [1.3333, 2.0])
def test_dialoge_passen_auf_kleine_bildschirme(skalierung, umgebung, dialoge, tmp_path_factory, display_1366):
    """Kennwort- und Hinweisdialog passen auf 1366x768 bei 100 % und 150 % (tk scaling 2.0), Knöpfe sichtbar."""
    display_vorher = os.environ.get("DISPLAY")
    display = display_1366
    try:
        root = tk.Tk(screenName=display) if display else tk.Tk()
    except tk.TclError as fehler:
        pytest.skip(f"Tk kann kein Fenster öffnen: {fehler}")
    skalierung_vorher = float(root.tk.call("tk", "scaling"))
    try:
        root.tk.willdispatch()
        root.tk.call("tk", "scaling", skalierung)
        app = gui.AnonymisiererApp(root, einstellungen={})
        root.update()
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        hinweis = app.hinweis_zeigen()
        kennwort = gui.KennwortDialog(app, "Abrechnung_Mustermann_2024_Juni.pdf", fehlversuch=True)
        pumpe(root, timeout=0.4)
        ordner = _screenshot_ordner(tmp_path_factory)
        _screenshot(root, display, ordner / f"dialoge_{'1366' if display else 'standard'}_{skalierung}.png")
        for dialog, knopf in ((hinweis.fenster, hinweis.ok_knopf), (kennwort.fenster, kennwort.ok_knopf)):
            b, h = dialog.winfo_reqwidth(), dialog.winfo_reqheight()
            assert b <= sw and h <= sh - 40, (b, h, sw, sh)
            assert knopf.winfo_ismapped() and knopf.winfo_height() >= 20
        kennwort.abbrechen()
        hinweis.bestaetigen()
    finally:
        try:
            root.tk.call("tk", "scaling", skalierung_vorher)
            root.destroy()
        except tk.TclError:
            pass
        _display_wiederherstellen(display_vorher)


# ======================================================================
# Runde 2, Fix-Paket „oberflaeche-eingang“ (Review-Befunde 1–6)
# ======================================================================
import ctypes            # noqa: E402
import ctypes.util       # noqa: E402
import io                # noqa: E402
import tarfile           # noqa: E402
import threading         # noqa: E402
import time              # noqa: E402
from types import SimpleNamespace  # noqa: E402

from test_gui import TARIFUEBERSICHT, fenster_existiert  # noqa: E402

HTML_PORTAL = ("<!DOCTYPE html>\n<html><head><meta charset=\"utf-16\"><title>Versicherungsportal</title></head><body>"
               "<p>Versicherungsnehmerin: Erika Musterfrau, Musterstraße 1, 12345 Musterstadt</p>"
               "<p>IBAN DE02 1203 0000 0000 2020 51</p></body></html>\n")
FB2_BUCH = ("<FictionBook xmlns=\"http://www.gribuser.ru/xml/fictionbook/2.0\"><body><section><p>Erika Musterfrau</p>"
            "</section></body></FictionBook>\n")
MAIL_MSG = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 600


def ppm_scan(breite=240, hoehe=160) -> bytes:
    """PNM-Scan (P6) wie von einem SANE-Scanner: weißer Rand, schwarze Zeile – der Kopf sieht aus wie Text."""
    zeilen = []
    for y in range(hoehe):
        zeile = bytearray(b"\xff\xff\xff" * breite)
        if 70 <= y < 80:
            zeile[120:600] = b"\x10" * 480
        zeilen.append(bytes(zeile))
    return f"P6\n{breite} {hoehe}\n255\n".encode() + b"".join(zeilen)


def psd_bild(breite=120, hoehe=80) -> bytes:
    """Minimale Photoshop-Datei (RGB, 8 Bit, unkomprimiert), von Hand geschrieben."""
    kopf = b"8BPS" + struct.pack(">H", 1) + b"\x00" * 6 + struct.pack(">HIIHH", 3, hoehe, breite, 8, 3)
    kopf += struct.pack(">III", 0, 0, 0) + struct.pack(">H", 0)
    return kopf + b"\xff" * (3 * breite * hoehe)


def tar_mit_bild() -> bytes:
    puffer = io.BytesIO()
    daten = png_bytes(breite=60, hoehe=40, text="x")
    with tarfile.open(fileobj=puffer, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        info = tarfile.TarInfo("seite1.png")
        info.size = len(daten)
        tar.addfile(info, io.BytesIO(daten))
    return puffer.getvalue()


# Inhalte mit der Endung .pdf, die MuPDF als Nicht-PDF öffnet – mit 7a59cfe stürzte bei jedem davon das ganze
# Programm ab (rc -11 beim ersten Seitenzugriff); dahinter die Art nach der Eingangsprüfung
GETARNT = {
    "html_utf16le": (("\ufeff" + HTML_PORTAL).encode("utf-16-le"), "html"),
    "html_utf16be": (("\ufeff" + HTML_PORTAL).encode("utf-16-be"), "html"),
    "pnm_p6": (ppm_scan(), "pnm"),
    "pnm_p5": (b"P5\n# Scanner\n40 30\n255\n" + b"\xff" * 1200, "pnm"),
    "pnm_p3": (b"P3\n2 2\n255\n" + b"255 255 255\n" * 4, "pnm"),
    "pnm_p4": (b"P4\n16 2\n" + b"\x00" * 4, "pnm"),
    "pam": (b"P7\nWIDTH 40\nHEIGHT 30\nDEPTH 3\nMAXVAL 255\nTUPLTYPE RGB\nENDHDR\n" + b"\xff" * 3600, "pnm"),
    "psd": (psd_bild(), "psd"),
    "fb2": (FB2_BUCH.encode(), "xml"),
    "fb2_bom": (b"\xef\xbb\xbf" + FB2_BUCH.encode(), "xml"),
    "tar": (tar_mit_bild(), "archiv"),
}
GETARNT_BILDER = {name for name, (_, art) in GETARNT.items() if art in ("pnm", "psd")}


def getarnte_dateien(ordner: Path) -> dict[str, Path]:
    return {name: schreibe(ordner / f"{name}.pdf", daten) for name, (daten, _) in GETARNT.items()}


# ----------------------------------------------------------------------
# Befund 2: Nicht-PDFs mit der Endung .pdf – MuPDF selbst fragen
# ----------------------------------------------------------------------
def test_getarnte_nicht_pdfs_erreichen_die_engine_nie(tmp_path):
    pfade = getarnte_dateien(tmp_path / "Kunde")
    for name, pfad in pfade.items():
        art = dateien.datei_art(pfad)
        assert art == GETARNT[name][1], (name, art)
        assert not dateien.fuer_engine_erlaubt(art), name
    # Ordner-Scan und Einzeldatei: Bilder (PNM, Photoshop) werden als Foto angeboten, der Rest als „keine PDF“ gemeldet
    bericht = dateien.sammle_pdfs_bericht([str(tmp_path / "Kunde")])
    assert bericht["pdfs"] == [] and bericht["pdf_ohne_endung"] == []
    assert {p.stem for p in bericht["bilder"]} == GETARNT_BILDER
    assert {p.stem for p in bericht["keine_pdf"]} == set(GETARNT) - GETARNT_BILDER
    einzeln = dateien.sammle_pdfs_bericht([str(pfade["html_utf16le"]), str(pfade["psd"])])
    assert [p.stem for p in einzeln["uebersprungen"]] == ["html_utf16le"]
    assert [p.stem for p in einzeln["bilder"]] == ["psd"] and einzeln["pdfs"] == []
    # Gegenproben: echte PDFs (auch mit Vorspann vor „%PDF“) und Unbestimmtes, das auch MuPDF nicht öffnet
    echt = pdf_schreiben(tmp_path / "echt" / "Antrag.pdf")
    vorspann = schreibe(tmp_path / "echt" / "Vorspann.pdf", b"Werbung " * 300 + echt.read_bytes())
    text16 = schreibe(tmp_path / "echt" / "Text16.pdf", ("\ufeffErika Musterfrau\r\n").encode("utf-16-le"))
    assert dateien.art_aus_kopf(vorspann.read_bytes()[:2048]) == "text"
    assert [dateien.datei_art(p) for p in (echt, vorspann, text16)] == ["pdf", "pdf", "text"]
    assert all(dateien.fuer_engine_erlaubt(dateien.datei_art(p)) for p in (echt, vorspann, text16))


def test_mupdf_entscheidet_auch_ohne_bekannten_kopf(tmp_path, monkeypatch):
    """Nicht raten, sondern MuPDF fragen: erkennt die Kopfprüfung nichts („unbekannt“), sagt MuPDF, wie es die Datei
    öffnet – nur als PDF darf sie an die Engine."""
    pdf = pdf_schreiben(tmp_path / "a.pdf")
    proben = {"html": schreibe(tmp_path / "html.pdf", ("\ufeff" + HTML_PORTAL).encode("utf-16-le")),
              "bild": schreibe(tmp_path / "psd.pdf", psd_bild()),
              "pnm": schreibe(tmp_path / "ppm.pdf", ppm_scan()),
              "xml": schreibe(tmp_path / "fb2.pdf", FB2_BUCH.encode()),
              "archiv": schreibe(tmp_path / "tar.pdf", tar_mit_bild()),
              "svg": schreibe(tmp_path / "svg.pdf", b'<svg xmlns="http://www.w3.org/2000/svg" width="9" height="9">'
                                                    b"<text>Max</text></svg>"),
              "unbekannt": schreibe(tmp_path / "text.pdf", b"Erika Musterfrau\n")}
    monkeypatch.setattr(dateien, "art_aus_kopf", lambda kopf: "unbekannt")
    assert dateien.datei_art(pdf) == "pdf"
    for erwartet, pfad in proben.items():
        art = dateien.datei_art(pfad)
        assert art == erwartet, (pfad.name, art)
        assert dateien.fuer_engine_erlaubt(art) == (erwartet == "unbekannt"), pfad.name
    assert dateien.ist_bild_art("bild") and dateien.ist_bild_art("pnm") and dateien.ist_bild_art("psd")
    assert dateien.art_beschreibung("format:XYZ") == "eine Datei im Format „XYZ“"
    assert not dateien.fuer_engine_erlaubt("format:XYZ")


@pytest.mark.parametrize("name", ["pnm_p6", "pam", "psd"])
def test_scanner_und_photoshop_bilder_werden_pdf(tmp_path, name):
    daten, art = GETARNT[name]
    bild = schreibe(tmp_path / f"{name}.pdf", daten)
    (tmp_path / "kopie").mkdir()
    ziel = tmp_path / "kopie" / "x.pdf"
    assert dateien.bild_als_pdf(bild, ziel, art) == 1
    assert dateien.datei_art(ziel) == "pdf"
    # ein Bildformat, das nur MuPDF erkannt hat („bild“), wird so geöffnet, wie es geprüft wurde
    ziel2 = tmp_path / "kopie" / "y.pdf"
    assert dateien.bild_als_pdf(bild, ziel2, "bild") == 1 and dateien.datei_art(ziel2) == "pdf"


_ENGINE_SKRIPT = r"""
import faulthandler, json, sys, warnings
faulthandler.enable()
warnings.simplefilter("ignore")
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from anonymisierer import dateien
from anonymisierer.analyse import analysiere_pdf
from anonymisierer.muster import KATEGORIEN
aktive = {e[0] for e in KATEGORIEN if len(e) < 5 or e[4]} - {"namen"}
ergebnis = {}
for pfad in sorted(Path(sys.argv[2]).iterdir()):
    art = dateien.datei_art(pfad)                         # dieselbe Prüfung wie vor Analyse, Schwärzung, Vorschau
    if dateien.fuer_engine_erlaubt(art):
        e = analysiere_pdf(pfad, aktive, [], [], melde=lambda t: None)
        ergebnis[pfad.name] = [art, e["fehler"]]
    else:
        ergebnis[pfad.name] = [art, "gesperrt"]
print(json.dumps(ergebnis))
"""


def test_eingangspruefung_mit_echter_engine_stuerzt_nie_ab(tmp_path):
    """Gegenprobe im eigenen Prozess (ein Absturz im C-Code beendete sonst die Testsitzung): mit 7a59cfe endete
    analysiere_pdf für jede dieser Dateien mit rc -11. Jetzt sperrt die Eingangsprüfung sie; Unbestimmtes, das auch
    MuPDF nicht öffnet, meldet die Engine sauber."""
    ordner = tmp_path / "proben"
    getarnte_dateien(ordner)
    schreibe(ordner / "text.pdf", b"Erika Musterfrau\n")
    schreibe(ordner / "leer.pdf", b"")
    pdf_schreiben(ordner / "echt.pdf")
    lauf = subprocess.run([sys.executable, "-c", _ENGINE_SKRIPT, str(WURZEL), str(ordner)], capture_output=True,
                          text=True, timeout=600, env=dict(os.environ, OMP_THREAD_LIMIT="1"))
    assert lauf.returncode == 0, lauf.stderr[-1500:]
    ergebnis = json.loads(lauf.stdout.strip().splitlines()[-1])
    for name, (_, erwartet) in GETARNT.items():
        assert ergebnis[f"{name}.pdf"] == [erwartet, "gesperrt"], name
    assert ergebnis["echt.pdf"] == ["pdf", None]
    assert ergebnis["text.pdf"][0] == "text" and ergebnis["text.pdf"][1]          # sauberer Fehlertext
    assert ergebnis["leer.pdf"][0] == "leer" and ergebnis["leer.pdf"][1]


@gui_test
def test_gui_ordner_mit_getarnten_nicht_pdfs(app, umgebung, monkeypatch, dialoge):
    """Befund 2 im Ablauf der Oberfläche: Kundenordner mit Antrag und Nicht-PDFs mit der Endung .pdf. Früher stand
    dort „12 PDF-Datei(en) hinzugefügt“, und „Analysieren“ beendete das ganze Programm (Segmentation fault)."""
    tmp = umgebung["tmp"]
    ordner = tmp / "Kunde_Musterfrau"
    antrag = pdf_schreiben(ordner / "01_Antrag.pdf")
    getarnte_dateien(ordner)
    gelesen = []

    def analyse(pdf_pfad, *args, **kwargs):
        art = dateien.datei_art(pdf_pfad)
        if art != "pdf":
            raise AssertionError(f"die Engine darf keine Nicht-PDF bekommen: {pdf_pfad.name} ({art})")
        gelesen.append(Path(pdf_pfad))
        return fake_analyse_neu({"01_Antrag.pdf": [FUND_TEL]})(pdf_pfad, *args, **kwargs)
    monkeypatch.setattr(gui, "analysiere_pdf", analyse)
    dialoge.antwort = False                                   # Fotos (PNM, Photoshop) nicht übernehmen
    app._pdfs_hinzufuegen([str(ordner)])
    assert app.dateien == [antrag]
    hinweis = app.datei_hinweis.cget("text")
    assert "1 PDF-Datei(en) hinzugefügt" in hinweis and "NICHT geprüft" in hinweis
    gruende = {p.stem: g for p, g in app.nicht_geprueft.items()}
    assert set(gruende) == set(GETARNT)
    assert gruende["html_utf16le"] == "keine PDF, sondern eine Webseite (HTML)"
    assert gruende["tar"].startswith("keine PDF, sondern ein Archiv") and gruende["psd"] == "Bild nicht übernommen"
    starte_lauf(app, app.analysieren)
    assert gelesen == [antrag]
    # „Ja“: Scanner- und Photoshop-Bilder werden PDF-Arbeitskopien – die Engine liest nur echte PDFs
    app.liste_leeren()
    dialoge.antwort = True
    app._pdfs_hinzufuegen([str(ordner)])
    assert {p.stem for p in app.dateien} - {"01_Antrag"} == GETARNT_BILDER
    assert all(app.arbeitskopien[p]["art"] == "bild" for p in app.dateien if p != antrag)
    gelesen.clear()
    starte_lauf(app, app.analysieren)
    assert len(gelesen) == len(app.dateien) and all(dateien.datei_art(p) == "pdf" for p in gelesen)


@gui_test
def test_vorschau_gibt_ersetzte_nicht_pdf_nie_an_die_engine(app, umgebung, monkeypatch, dialoge):
    """Auch die offene Vorschau prüft vor jedem Seitenbild der Engine den Inhalt (Datei nach der Analyse durch eine
    UTF-16-Webseite ersetzt – das Vorschau-Modul der Engine stürzte damit im C-Code ab)."""
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "Police.pdf")
    seitenbilder = []

    def seite_bild(datei, nr, zoom):
        seitenbilder.append(Path(datei))
        return gui.attrappen.seite_bild(datei, nr, zoom)
    monkeypatch.setattr(vorschau_fenster, "_engine_vorschau",
                        SimpleNamespace(seite_bild=seite_bild, vorschau_daten=gui.attrappen.vorschau_daten))
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse_neu({"Police.pdf": [FUND_TEL]}, modell=True))
    analysiere(app, [pdf])
    fenster = app.vorschau_oeffnen(pdf)
    assert vorschau_fenster.vorher_quelle_engine(app, pdf) and seitenbilder == [pdf]
    pdf.write_bytes(("\ufeff" + HTML_PORTAL).encode("utf-16-le"))     # inzwischen ersetzt
    fenster._bild_kennung = None
    fenster.zeige_seite(0, erzwingen=True)
    assert seitenbilder == [pdf], "das Vorschau-Modul der Engine darf die Webseite nicht bekommen"
    texte = [fenster.canvas.itemcget(i, "text") for i in fenster.canvas.find_all()
             if fenster.canvas.type(i) == "text"]
    assert any("keine PDF mehr" in t and "Webseite" in t for t in texte), texte
    fenster.schliessen()
    # und ein neues Fenster öffnet sie gar nicht erst
    assert app.vorschau_oeffnen(pdf) is None and dialoge.liste[-1][1] == "Vorschau nicht möglich"


# ----------------------------------------------------------------------
# Befund 1/4: Analyse ohne Funde verschweigt die nicht geprüften Dateien nicht
# ----------------------------------------------------------------------
def _kunde_mit_ungeprueften(ordner: Path) -> dict:
    """Ordner wie im Befund: Bedingungswerk ohne Personendaten, geschützte Beitragsrechnung (Kennwort unbekannt),
    Ausweisfoto, Mail."""
    return {"avb": pdf_schreiben(ordner / "AVB_Hausrat.pdf", "Allgemeine Bedingungen\nEs gelten die gesetzlichen "
                                                             "Bestimmungen."),
            "geschuetzt": geschuetzte_pdf(ordner / "Beitragsrechnung_Mustermann.pdf", kennwort="15031975"),
            "foto": schreibe(ordner / "Ausweis_Mustermann.jpg", jpeg_bytes()),
            "mail": schreibe(ordner / "Mail_vom_Kunden.msg", MAIL_MSG)}


@gui_test
def test_gui_analyse_ohne_funde_nennt_nicht_gepruefte_dateien(app, umgebung, monkeypatch, dialoge):
    """Befunde 1 und 4: Die Analyse fand in den geprüften Dateien nichts – der Dialog war eine Information „Keine
    Funde – Es wurden keine personenbezogenen Daten erkannt“, ohne ein Wort zu Ausweisfoto, geschützter Abrechnung
    und Mail, die gar nicht geprüft wurden."""
    tmp = umgebung["tmp"]
    d = _kunde_mit_ungeprueften(tmp / "Kunde_Mustermann")
    monkeypatch.setattr(app, "_kennwort_abfragen", lambda pfad, fehlversuch=False: None)   # „Überspringen“
    dialoge.antwort = False                                                               # Foto: „Nein“
    app._pdfs_hinzufuegen([str(tmp / "Kunde_Mustermann")])
    assert app.dateien == [d["avb"]] and len(app.nicht_geprueft) == 3
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({}))
    starte_lauf(app, app.analysieren)
    art, titel, text = app.letzter_dialog
    assert art == "warning" and titel == "Keine Funde – 3 Datei(en) NICHT geprüft", titel
    assert "keine personenbezogenen Daten" not in text and "In den geprüften Dateien wurde nichts gefunden" in text
    for name, grund in (("Ausweis_Mustermann.jpg", "Bild nicht übernommen"),
                        ("Beitragsrechnung_Mustermann.pdf", "Kennwort nicht eingegeben"),
                        ("Mail_vom_Kunden.msg", "keine PDF, sondern eine Outlook-Nachricht")):
        assert f"  • {name}: {grund}" in text, (name, text)
    bloecke = [b.split("\n") for b in text.split("\n\n")]
    assert bloecke[1][0].startswith("NICHT geprüft wurden 3 Datei(en)")     # gleich nach der ersten Aussage
    assert all(z.startswith("  •") for z in bloecke[1][1:])
    status = app.status_label.cget("text")
    assert "NICHT geprüft" in status and "3 Datei(en)" in status
    letzte = app.protokoll_text().splitlines()[-1]
    assert letzte.startswith("⚠ NICHT geprüft: 3 Datei(en)") and "Ausweis_Mustermann.jpg" in letzte
    assert app.warnungen_anzahl == 0                          # Auswahlmeldungen zählen nicht (GR-07)
    assert str(app.start_knopf.cget("state")) == "disabled"
    # Gegenprobe: alles geprüft -> unverändert „Keine Funde“ mit „keine personenbezogenen Daten“ (Information)
    app.liste_leeren()
    analysiere(app, [d["avb"]])
    art, titel, text = app.letzter_dialog
    assert (art, titel) == ("info", "Keine Funde") and text.startswith("Es wurden keine personenbezogenen Daten erkannt")


@gui_test
def test_gui_analyse_ohne_funde_nicht_analysierbar_ist_keine_entwarnung(app, umgebung, monkeypatch, dialoge):
    """Auch eine Datei, die nicht analysiert werden konnte, ist nicht geprüft: kein „keine personenbezogenen Daten“."""
    tmp = umgebung["tmp"]
    a, b = pdf_schreiben(tmp / "avb.pdf"), pdf_schreiben(tmp / "kaputt.pdf")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({}, fehler_fuer={"kaputt.pdf": ValueError("kaputt")}))
    analysiere(app, [a, b])
    art, titel, text = app.letzter_dialog
    assert art == "warning" and titel == "Keine Funde – 1 Datei(en) NICHT geprüft"
    assert "keine personenbezogenen Daten" not in text and "Nicht analysierbar" in text and "kaputt.pdf" in text
    app.datei_entfernen(str(a))                                    # nur noch die Datei, die nicht analysierbar ist
    starte_lauf(app, app.analysieren)
    art, titel, text = app.letzter_dialog
    assert text.startswith("Keine Datei der Auswahl konnte geprüft werden") and "Mögliche Gründe" not in text


@gui_test
def test_gui_nur_angeboten_nennt_nicht_gepruefte_dateien(app, umgebung, dialoge):
    """Zweig „nur angeboten“ (echte Engine: Tarifübersicht mit Gesundheitsbegriffen) plus eine Mail im Ordner."""
    tmp = umgebung["tmp"]
    ordner = tmp / "Kunde_Gesund"
    pdf_schreiben(ordner / "KV_Tarifuebersicht.pdf", TARIFUEBERSICHT)
    schreibe(ordner / "Mail_vom_Kunden.msg", MAIL_MSG)
    app.kategorie_vars["namen"].set(False)
    app._pdfs_hinzufuegen([str(ordner)])
    starte_lauf(app, app.analysieren, timeout=120)
    art, titel, text = app.letzter_dialog
    assert str(app.start_knopf.cget("state")) == "disabled"
    assert art == "warning" and titel == "Analyse abgeschlossen – 1 Datei(en) NICHT geprüft"
    assert text.startswith("In den geprüften Dateien wurden keine Personendaten zum Schwärzen erkannt"), text
    assert "  • Mail_vom_Kunden.msg: keine PDF, sondern eine Outlook-Nachricht" in text
    assert app.status_label.cget("text").startswith("⚠ 1 Datei(en) NICHT geprüft")


@gui_test
def test_gui_analyse_mit_funden_nennt_nicht_gepruefte_dateien(app, umgebung, monkeypatch, dialoge):
    """Auch mit Funden erinnert schon der Analyse-Abschluss an die nicht geprüften Dateien (nicht erst die
    Schwärzung)."""
    ordner = umgebung["tmp"] / "Kunde"
    pdf_schreiben(ordner / "Antrag.pdf")
    schreibe(ordner / "Mail_vom_Kunden.msg", MAIL_MSG)
    schreibe(ordner / "Brief.docx", b"PK\x03\x04" + b"\x00" * 40)
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({"Antrag.pdf": [FUND_TEL]}))
    app._pdfs_hinzufuegen([str(ordner)])
    starte_lauf(app, app.analysieren)
    art, titel, text = app.letzter_dialog
    assert art == "warning" and titel == "Analyse abgeschlossen – 2 Datei(en) NICHT geprüft"
    assert text.startswith("Die Analyse hat 1 Fund(e)")
    assert "Brief.docx: keine PDF, sondern ein Word-Dokument" in text and "Mail_vom_Kunden.msg" in text
    assert str(app.start_knopf.cget("state")) == "normal"


# ----------------------------------------------------------------------
# Befund 3: Schließen bei offenem Kennwortdialog / während eines Laufs
# ----------------------------------------------------------------------
def _ereignisse_bis_geschlossen(root, timeout=10.0) -> bool:
    """Treibt die Ereignisschleife, bis das Fenster zerstört ist (pumpe() bräche dann mit TclError ab)."""
    ende = time.time() + timeout
    while time.time() < ende:
        if not fenster_existiert(root):
            return True
        try:
            root.update()
        except tk.TclError:
            return True
        time.sleep(0.01)
    return not fenster_existiert(root)


def _temp_dateien() -> list:
    basis = dateien.temp_basis()
    return sorted(p for p in basis.rglob("*") if p.is_file()) if basis.exists() else []


def _sitzungsordner_im_temp() -> list:
    basis = dateien.temp_basis()
    return sorted(basis.glob("sitzung_*")) if basis.exists() else []


def _schliessen_wie_fenstermanager(app):
    """Was Tk beim Klick auf das X der Titelleiste tut: den WM_DELETE_WINDOW-Handler des Hauptfensters aufrufen."""
    app.root.tk.call(app.root.protocol("WM_DELETE_WINDOW"))


def _dialog_name(app) -> str:
    """„„c_Police_Mustermann.pdf“ ist mit einem Kennwort geschützt.“ – erste Zeile des Kennwortdialogs."""
    return app.kennwort_dialog.fenster.winfo_children()[0].winfo_children()[0].cget("text")


@gui_test
def test_schliessen_bei_offenem_kennwortdialog_laesst_keine_kopie_liegen(app, umgebung, dialoge):
    """Befund 3: Das Hauptfenster wird geschlossen, während der Kennwortdialog der dritten geschützten PDF offen ist.
    Früher wurde danach die nächste PDF still mit dem gemerkten Kennwort entschlüsselt – in einen NEU angelegten
    Sitzungsordner, der nach dem Beenden mit Name und IBAN liegen blieb."""
    ordner = umgebung["tmp"] / "Kunde_Mustermann"
    for name, kennwort in (("a_Abrechnung", "geheim"), ("b_Beitragsrechnung", "geheim"), ("c_Police", "anders"),
                           ("d_Nachtrag", "geheim")):
        geschuetzte_pdf(ordner / f"{name}_Mustermann.pdf", kennwort=kennwort)
    schreibe(ordner / "e_Portal_Download_Mustermann", pdf_schreiben(umgebung["tmp"] / "vorlage.pdf").read_bytes())
    ablauf = []

    def bedienen():
        if app.kennwort_dialog is None:
            app.root.after(20, bedienen)
            return
        ablauf.append(_dialog_name(app))
        if len(ablauf) == 1:
            app.kennwort_dialog.var.set("geheim")
            app.kennwort_dialog.ok()
            app.root.after(20, bedienen)
        else:
            _schliessen_wie_fenstermanager(app)
    app.root.after(50, bedienen)
    app._pdfs_hinzufuegen([str(ordner)])
    assert len(ablauf) == 2 and "c_Police" in ablauf[1]
    assert _ereignisse_bis_geschlossen(app.root), "das Fenster muss nach der abgebrochenen Auswahl schließen"
    assert app.beendet and _temp_dateien() == [] and _sitzungsordner_im_temp() == []
    with pytest.raises(dateien.SitzungBeendet):                   # nie still eine neue Sitzung anlegen
        dateien.arbeitskopie_ziel("d_Nachtrag_Mustermann.pdf")
    fehlerlog = umgebung["fehlerlog"]
    assert not fehlerlog.exists() or "TclError" not in fehlerlog.read_text(encoding="utf-8")


_X11 = None


def _x11():
    global _X11
    if _X11 is None:
        name = ctypes.util.find_library("X11") if sys.platform.startswith("linux") else None
        _X11 = ctypes.cdll.LoadLibrary(name) if name else False
        if _X11:
            _X11.XOpenDisplay.restype = ctypes.c_void_p
            _X11.XOpenDisplay.argtypes = [ctypes.c_char_p]
            _X11.XInternAtom.restype = ctypes.c_ulong
            _X11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
            _X11.XSendEvent.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_long, ctypes.c_void_p]
            _X11.XFlush.argtypes = [ctypes.c_void_p]
            _X11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    return _X11


class _ClientMessage(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int), ("serial", ctypes.c_ulong), ("send_event", ctypes.c_int),
                ("display", ctypes.c_void_p), ("window", ctypes.c_ulong), ("message_type", ctypes.c_ulong),
                ("format", ctypes.c_int), ("data", ctypes.c_long * 5)]


class _XEreignis(ctypes.Union):
    _fields_ = [("xclient", _ClientMessage), ("pad", ctypes.c_long * 24)]


def _wm_delete_window_senden(fenster: int) -> bool:
    """Schickt WM_DELETE_WINDOW als ClientMessage an ein X-Fenster – genau das tut ein Fenstermanager beim Klick auf
    das X der Titelleiste (eigene Verbindung zum X-Server, wie ein fremder Prozess)."""
    x11 = _x11()
    anzeige = x11.XOpenDisplay(None)
    if not anzeige:
        return False
    try:
        ereignis = _XEreignis()
        ereignis.xclient.type = 33                             # ClientMessage
        ereignis.xclient.window = fenster
        ereignis.xclient.message_type = x11.XInternAtom(anzeige, b"WM_PROTOCOLS", False)
        ereignis.xclient.format = 32
        ereignis.xclient.data[0] = x11.XInternAtom(anzeige, b"WM_DELETE_WINDOW", False)
        ok = x11.XSendEvent(anzeige, fenster, False, 0, ctypes.byref(ereignis))
        x11.XFlush(anzeige)
        return bool(ok)
    finally:
        x11.XCloseDisplay(anzeige)


@gui_test
@pytest.mark.skipif(sys.platform == "win32", reason="X11-Ereignis (unter Windows sperrt Tk die Titelleiste)")
def test_schliessen_per_echtem_wm_delete_window(app, umgebung, dialoge):
    """Variante b des Befunds mit einem echten X11-Ereignis: geschützte PDF und PDF ohne Endung; das Hauptfenster
    wird bei offenem Kennwortdialog über die Titelleiste geschlossen (früher blieb die Kopie der PDF ohne Endung
    mit Name und IBAN liegen)."""
    if not _x11() or not os.environ.get("DISPLAY"):
        pytest.skip("libX11 bzw. Display fehlt")
    ordner = umgebung["tmp"] / "Kunde_Mustermann"
    geschuetzte_pdf(ordner / "Abrechnung_Mustermann.pdf")
    schreibe(ordner / "Portal_Download_Mustermann", pdf_schreiben(umgebung["tmp"] / "vorlage.pdf").read_bytes())
    gesendet = []

    def schliessen():
        if app.kennwort_dialog is None:
            app.root.after(20, schliessen)
            return
        app.root.update_idletasks()
        gesendet.append(_wm_delete_window_senden(int(app.root.wm_frame(), 16)))
    app.root.after(80, schliessen)
    app._pdfs_hinzufuegen([str(ordner)])
    assert gesendet == [True]
    assert _ereignisse_bis_geschlossen(app.root)
    assert app.beendet and _temp_dateien() == [] and _sitzungsordner_im_temp() == []


@gui_test
def test_schliessen_waehrend_der_fotofrage(app, umgebung, monkeypatch, dialoge):
    """Kommt das Schließen, während eine Rückfrage offen ist (unter Linux erreicht WM_DELETE_WINDOW das Fenster trotz
    modaler Meldung), wird danach nichts mehr umgewandelt – und das Fenster schließt."""
    ordner = umgebung["tmp"] / "Kunde"
    pdf_schreiben(ordner / "Antrag.pdf")
    schreibe(ordner / "Ausweis.jpg", jpeg_bytes())

    def frage(titel=None, nachricht=None, **kw):
        _schliessen_wie_fenstermanager(app)              # während die Frage offen ist …
        return True                                      # … danach „Ja“
    monkeypatch.setattr(gui.messagebox, "askyesno", frage)
    app._pdfs_hinzufuegen([str(ordner)])
    assert app.dateien == []
    assert _ereignisse_bis_geschlossen(app.root)
    assert app.beendet and _temp_dateien() == []


@gui_test
def test_schliessen_waehrend_des_laufs_loescht_kopie_nach_dem_thread(app, umgebung, monkeypatch, dialoge):
    """Zweiter Weg (Windows): Schließen mit „Ja“ während einer Analyse – der Analyse-Thread hält die entschlüsselte
    Kopie noch offen, und Windows löscht keine offene Datei. Nachgebildet: rmtree lässt die „offene“ Datei stehen.
    Früher schluckten rmtree(ignore_errors) und arbeitskopie_entfernen das still, die Kopie blieb bis zum nächsten
    Start liegen. Jetzt wird nach dem Ende des Threads erneut gelöscht."""
    pdf = geschuetzte_pdf(umgebung["tmp"] / "Kunde" / "Abrechnung.pdf")
    monkeypatch.setattr(app, "_kennwort_abfragen", lambda pfad, fehlversuch=False: "geheim")
    app._pdfs_hinzufuegen([str(pdf)])
    kopie = app._arbeitsdatei(pdf)
    sitzung = dateien.aktuelle_sitzung()
    assert kopie != pdf and kopie.exists() and sitzung is not None
    offen, weiter = threading.Event(), threading.Event()

    def analyse(pdf_pfad, *args, **kwargs):
        offen.set()                                       # die Engine hat die Kopie geöffnet …
        try:
            weiter.wait(15)
            return fake_analyse_neu({})(pdf_pfad, *args, **kwargs)
        finally:
            offen.clear()                                 # … und wieder geschlossen
    monkeypatch.setattr(gui, "analysiere_pdf", analyse)
    echtes_rmtree = dateien.shutil.rmtree

    def rmtree_wie_windows(pfad, ignore_errors=False, **kw):
        if offen.is_set() and Path(kopie).is_relative_to(Path(pfad)):
            if ignore_errors:
                return None
            raise PermissionError(13, "Der Prozess kann nicht auf die Datei zugreifen", str(kopie))
        return echtes_rmtree(pfad, ignore_errors=ignore_errors, **kw)
    monkeypatch.setattr(dateien.shutil, "rmtree", rmtree_wie_windows)
    app.analysieren()
    assert pumpe(app.root, offen.is_set, timeout=10)
    dialoge.antwort = True                                 # „Wirklich beenden?“ -> Ja
    app.schliessen()
    assert not fenster_existiert(app.root) and kopie.exists()      # noch offen: konnte nicht gelöscht werden
    faden = app._reste_threads.get(str(sitzung))
    assert faden is not None and faden.is_alive() and not faden.daemon
    weiter.set()                                          # Analyse endet, die Datei ist wieder zu
    faden.join(20)
    assert not faden.is_alive() and not kopie.exists() and not sitzung.exists()
    fehlerlog = umgebung["fehlerlog"]
    assert not fehlerlog.exists() or "nicht gelöscht" not in fehlerlog.read_text(encoding="utf-8")


@gui_test
def test_schliessen_reste_die_bleiben_stehen_in_fehler_log(app, umgebung, monkeypatch, dialoge):
    """Bleibt eine Kopie auch nach dem Warten offen, steht das in fehler.log (der nächste Start löscht sie)."""
    schreibe(umgebung["tmp"] / "Kunde" / "Ausweis.jpg", jpeg_bytes())
    dialoge.antwort = True
    app._pdfs_hinzufuegen([str(umgebung["tmp"] / "Kunde")])
    sitzung = dateien.aktuelle_sitzung()
    assert sitzung is not None and _temp_dateien()
    monkeypatch.setattr(gui, "RESTE_WARTEN_S", 0.5)
    monkeypatch.setattr(dateien.shutil, "rmtree", lambda pfad, ignore_errors=False, **kw: None)   # alles „offen“
    app.schliessen()
    faden = app._reste_threads[str(sitzung)]
    faden.join(10)
    assert not faden.is_alive() and sitzung.exists()
    assert "konnten beim Beenden nicht gelöscht werden" in umgebung["fehlerlog"].read_text(encoding="utf-8")


def test_sitzung_nach_endgueltigem_aufraeumen(tmp_path, monkeypatch):
    """dateien: nach dem endgültigen Aufräumen keine neue Sitzung; ein Ordner, der (noch) nicht gelöscht werden
    konnte, bleibt vermerkt und wird beim nächsten Versuch gelöscht."""
    ziel = dateien.arbeitskopie_ziel("Police.pdf")
    ziel.write_bytes(b"%PDF-1.4\n")
    sitzung = dateien.aktuelle_sitzung()
    echtes_rmtree = dateien.shutil.rmtree
    monkeypatch.setattr(dateien.shutil, "rmtree", lambda pfad, ignore_errors=False, **kw: None)
    assert dateien.sitzung_aufraeumen(endgueltig=True) is False and dateien.aktuelle_sitzung() == sitzung
    with pytest.raises(dateien.SitzungBeendet):
        dateien.sitzungsordner()
    monkeypatch.setattr(dateien.shutil, "rmtree", echtes_rmtree)
    assert dateien.sitzung_aufraeumen(endgueltig=True) and not sitzung.exists() and dateien.aktuelle_sitzung() is None
    with pytest.raises(dateien.SitzungBeendet):
        dateien.arbeitskopie_ziel("Ausweis.jpg")
    dateien.sitzung_beginnen()                                    # neues Hauptfenster: wieder erlaubt
    neu = dateien.arbeitskopie_ziel("Ausweis.jpg")
    assert neu.parent.parent != sitzung and dateien.ordner_loeschen(neu.parent.parent)
    fremd = tmp_path / "Kunde"                                    # nie außerhalb des Ordners für Arbeitskopien
    fremd.mkdir()
    assert dateien.ordner_loeschen(fremd) is False and fremd.exists()


# ----------------------------------------------------------------------
# Befund 5: Gesicht/Lichtbild, Unterschrift, Handschrift auf Fotos
# ----------------------------------------------------------------------
def test_texte_nennen_gesicht_lichtbild_unterschrift_handschrift():
    for text in (gui.ERSTSTART_TEXT, gui.GRENZEN_TEXT, gui.FOTO_GRENZEN, *gui._texte_zur_engine(True)[1:],
                 *gui._texte_zur_engine(False)[1:]):
        for wort in ("Gesicht", "Lichtbild", "Unterschrift", "Handschrift"):
            assert wort in text, (wort, text)
    assert "„Geplante Schwärzung“" in gui.FOTO_GRENZEN and "Rahmen" in gui.FOTO_GRENZEN
    assert "immer in der Vorschau freigegeben" in gui.GRENZEN_TEXT
    assert vorschau_fenster.HINWEIS_FOTO.startswith("Foto:") and "Gesicht" in vorschau_fenster.HINWEIS_FOTO


@gui_test
def test_foto_ausgabe_braucht_immer_freigabe(app, umgebung, monkeypatch, dialoge):
    """Befund 5: Mit ausgeschalteter Freigabe ging ein „anonymisierter“ Ausweis mit Gesicht als anonym_NN.pdf
    („fertig“) hinaus. Für umgewandelte Fotos verlangt die Oberfläche die Freigabe jetzt immer."""
    ordner = umgebung["tmp"] / "Kunde"
    foto = schreibe(ordner / "Ausweis_Mustermann.jpg", jpeg_bytes())
    pdf = pdf_schreiben(ordner / "Antrag.pdf")
    dialoge.antwort = True
    app._pdfs_hinzufuegen([str(ordner)])
    frage = next(t for _, ti, t in dialoge.liste if ti == "Fotos als PDF übernehmen?")
    assert "Gesichter und Lichtbilder" in frage and "Unterschriften und Handschrift" in frage
    app.freigabe_var.set(False)
    aufrufe = []
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse_neu({"Ausweis_Mustermann.jpg.pdf": [FUND_TEL],
                                                                 "Antrag.pdf": [FUND_MAIL]}))
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung_neu(aufrufe))
    starte_lauf(app, app.analysieren)
    dialoge.antwort = False
    starte_lauf(app, app.schwaerzen)
    freigabe = {Path(a["pdf"]).name: a["freigabe_erforderlich"] for a in aufrufe}
    assert freigabe == {"Ausweis_Mustermann.jpg.pdf": True, "Antrag.pdf": False}
    assert app.ausgaben[foto]["status"] == "pruefen" and "_PRUEFEN" in app.ausgaben[foto]["pfad"].name
    assert "Gesicht" in app.ausgaben[foto]["grund"] and app.ausgaben[pdf]["status"] == "fertig"
    assert "Freigabe vor Weitergabe: aus (für Fotos immer)" in app.laufprotokoll_text()
    # Vorschau eines Fotos: der Hinweis steht vorn in der Statuszeile
    fenster = app.vorschau_oeffnen(foto, modus="vorher")
    assert fenster.status_label.cget("text").startswith(vorschau_fenster.HINWEIS_FOTO)
    fenster_pdf = app.vorschau_oeffnen(pdf, modus="vorher")
    assert not fenster_pdf.status_label.cget("text").startswith("Foto:")


@gui_test
def test_foto_freigabe_auch_mit_alter_engine(app, umgebung, monkeypatch, dialoge):
    """Engine ohne Parameter freigabe_erforderlich: die Oberfläche markiert die Foto-Ausgabe selbst als _PRUEFEN."""
    foto = schreibe(umgebung["tmp"] / "Kunde" / "Schaden.png", png_bytes())
    dialoge.antwort = True
    app._pdfs_hinzufuegen([str(foto)])
    app.freigabe_var.set(False)
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({"Schaden.png.pdf": [FUND_TEL]}))
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung([]))
    starte_lauf(app, app.analysieren)
    dialoge.antwort = False
    starte_lauf(app, app.schwaerzen)
    assert app.ausgaben[foto]["status"] == "pruefen" and app.ausgaben[foto]["pfad"].name.endswith("_PRUEFEN.pdf")


@gui_test
@braucht_ocr
def test_foto_mit_echter_engine_ohne_freigabe_haken_bleibt_pruefen(app, umgebung, dialoge, monkeypatch):
    """Echte Engine: Ausweisfoto, Häkchen „Freigabe …“ aus – die Ausgabe heißt trotzdem _PRUEFEN."""
    from anonymisierer.ocr import OcrDienst
    monkeypatch.setattr(gui, "OcrDienst", OcrDienst)
    foto = schreibe(umgebung["tmp"] / "Kunde" / "Ausweis_Mustermann.jpg", jpeg_bytes(dpi=150))
    dialoge.antwort = True
    app._pdfs_hinzufuegen([str(foto)])
    app.freigabe_var.set(False)
    app.kategorie_vars["namen"].set(False)
    starte_lauf(app, app.analysieren, timeout=180)
    assert app.analyse_ergebnisse[foto]["funde"]
    dialoge.antwort = False
    starte_lauf(app, app.schwaerzen, timeout=180)
    ausgabe = app.ausgaben[foto]["pfad"]
    assert app.ausgaben[foto]["status"] == "pruefen" and "_PRUEFEN" in ausgabe.name


# ----------------------------------------------------------------------
# Befund 6: Hinweiszeile umbrechen, NICHT-geprüft-Zeile zuletzt, Statuszeile
# ----------------------------------------------------------------------
@gui_test
def test_hinweiszeile_bricht_um_und_nicht_geprueft_steht_zuletzt(app, umgebung, dialoge):
    ordner = kundenordner(umgebung["tmp"])                   # Fotos, Mail, Webseite als .pdf, Ausgaben …
    dialoge.antwort = False
    app._pdfs_hinzufuegen([str(ordner)])
    app.root.update()
    hinweis = app.datei_hinweis
    text = hinweis.cget("text")
    assert "keine PDF (nicht geprüft)" in text and "NICHT geprüft – Namen im Protokoll" in text
    assert hinweis.cget("fg") == gui.FARBE_WARNUNG
    # eigene Zeile unter den Knöpfen (nicht mehr in der Knopfzeile), Breite folgt dem Fenster: nichts abgeschnitten
    assert hinweis.master is app.drop_zone.master and int(hinweis.cget("wraplength")) > 0
    assert hinweis.winfo_reqwidth() <= hinweis.winfo_width() + 2, (hinweis.winfo_reqwidth(), hinweis.winfo_width())
    assert hinweis.winfo_height() >= 2 * app.zeilenhoehe - 2          # umgebrochen statt abgeschnitten
    # die Namen der nicht geprüften Dateien stehen in der LETZTEN Protokollzeile – keine ℹ-Zeile schiebt sie hinaus
    protokoll = app.protokoll_text()
    letzte = protokoll.splitlines()[-1]
    assert letzte.startswith("⚠ NICHT geprüft aus dieser Auswahl: 5 Datei(en)"), letzte
    for name in ("Ausweis_Mustermann.jpg", "Schaden.JPEG", "Foto_umbenannt.pdf", "Mail_vom_Kunden.msg",
                 "Portal_Fehlerseite.pdf"):
        assert name in letzte, name
    assert protokoll.index("bereits Ausgaben") < protokoll.index(letzte)
    # die immer sichtbare Statuszeile nennt es zuerst
    assert app.status_label.cget("text").startswith("⚠ 5 Datei(en) werden NICHT geprüft")
    assert app.warnungen_anzahl == 0
    app.liste_leeren()
    assert app.datei_hinweis.cget("fg") == gui.FARBE_TEXT_GRAU and "NICHT" not in app.status_label.cget("text")


@gui_test
@pytest.mark.parametrize("skalierung", [1.3333, 2.0])
def test_hinweiszeile_vollstaendig_auf_kleinem_bildschirm(skalierung, umgebung, dialoge, tmp_path_factory,
                                                          display_1366):
    """1366x768 bei 100 % und 150 %: die lange Hinweiszeile ist nicht abgeschnitten (früher 486 von 964 px)."""
    display_vorher = os.environ.get("DISPLAY")
    display = display_1366
    try:
        root = tk.Tk(screenName=display) if display else tk.Tk()
    except tk.TclError as fehler:
        pytest.skip(f"Tk kann kein Fenster öffnen: {fehler}")
    skalierung_vorher = float(root.tk.call("tk", "scaling"))
    try:
        root.tk.willdispatch()
        root.tk.call("tk", "scaling", skalierung)
        app = gui.AnonymisiererApp(root, einstellungen={})
        pumpe(root, timeout=0.3)
        dialoge.antwort = False
        app._pdfs_hinzufuegen([str(kundenordner(umgebung["tmp"]))])
        pumpe(root, timeout=0.4)
        hinweis = app.datei_hinweis
        _screenshot(root, display, _screenshot_ordner(tmp_path_factory) / f"hinweiszeile_{skalierung}.png")
        assert hinweis.winfo_reqwidth() <= hinweis.winfo_width() + 2, (hinweis.winfo_reqwidth(), hinweis.winfo_width())
        assert hinweis.winfo_rootx() + hinweis.winfo_width() <= root.winfo_rootx() + root.winfo_width()
        assert app.status_label.cget("text").startswith("⚠ 5 Datei(en) werden NICHT geprüft")
    finally:
        try:
            root.tk.call("tk", "scaling", skalierung_vorher)
            root.destroy()
        except tk.TclError:
            pass
        _display_wiederherstellen(display_vorher)
