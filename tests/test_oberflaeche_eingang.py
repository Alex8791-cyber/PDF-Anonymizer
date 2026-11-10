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
    # PyMuPDF als Nicht-PDF öffnet, nie (Absturz, R-01)
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
