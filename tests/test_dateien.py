"""Tests für anonymisierer.dateien (PDF-Sammlung, Einstellungen, Fehlerprotokoll, Ordner öffnen) und das Startskript."""

import json
import sys
from pathlib import Path


from anonymisierer import dateien


def _leere_pdf(pfad: Path):
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_bytes(b"%PDF-1.4\n%%EOF\n")


# ----------------------------------------------------------------------
# sammle_pdfs
# ----------------------------------------------------------------------
def test_sammle_pdfs_ordner_scan_alle_schreibweisen_und_ohne_ausgaben(tmp_path):
    _leere_pdf(tmp_path / "a.pdf")
    _leere_pdf(tmp_path / "unter" / "B.PDF")
    (tmp_path / "c.txt").write_text("kein pdf")
    _leere_pdf(tmp_path / "anonymisiert" / "anonym_01.pdf")
    _leere_pdf(tmp_path / "anonymisiert" / "anonym_02_PRUEFEN.pdf")
    _leere_pdf(tmp_path / "alt_anonym.pdf")

    gefunden = dateien.sammle_pdfs([str(tmp_path)])
    assert gefunden == [tmp_path / "a.pdf", tmp_path / "unter" / "B.PDF"]

    bericht = dateien.sammle_pdfs_bericht([str(tmp_path)])
    assert len(bericht["ausgaben"]) == 3
    assert bericht["uebersprungen"] == []        # Nicht-PDFs im Ordner-Scan sind kein Fehler


def test_sammle_pdfs_bericht_meldet_nicht_pdf_leeren_ordner_und_fehlende(tmp_path):
    _leere_pdf(tmp_path / "a.pdf")
    (tmp_path / "brief.docx").write_text("x")
    leer = tmp_path / "leer"
    leer.mkdir()
    bericht = dateien.sammle_pdfs_bericht([str(tmp_path / "a.pdf"), str(tmp_path / "brief.docx"),
                                           str(leer), str(tmp_path / "gibt_es_nicht.pdf")])
    assert bericht["pdfs"] == [tmp_path / "a.pdf"]
    assert bericht["uebersprungen"] == [tmp_path / "brief.docx"]
    assert bericht["leere_ordner"] == [leer]
    assert bericht["fehlend"] == [tmp_path / "gibt_es_nicht.pdf"]


def test_sammle_pdfs_einzeldatei_bereits_anonymisiert_wird_angenommen(tmp_path):
    """Nachschwärzen einer Ausgabe muss möglich bleiben (Einzelauswahl), nur der Ordner-Scan filtert."""
    _leere_pdf(tmp_path / "anonymisiert" / "anonym_01.pdf")
    assert dateien.sammle_pdfs([str(tmp_path / "anonymisiert" / "anonym_01.pdf")]) == [
        tmp_path / "anonymisiert" / "anonym_01.pdf"]


def test_sammle_pdfs_dubletten_und_gleiche_namen_in_verschiedenen_ordnern(tmp_path):
    _leere_pdf(tmp_path / "KundeA" / "Police.pdf")
    _leere_pdf(tmp_path / "KundeB" / "Police.pdf")
    gefunden = dateien.sammle_pdfs([str(tmp_path), str(tmp_path / "KundeA" / "Police.pdf")])
    assert gefunden == [tmp_path / "KundeA" / "Police.pdf", tmp_path / "KundeB" / "Police.pdf"]
    assert dateien.gemeinsamer_stamm(gefunden) == tmp_path
    assert dateien.gemeinsamer_stamm([]) is None


def test_ist_ausgabedatei_und_cloud_ordner(tmp_path):
    assert dateien.ist_ausgabedatei(Path("x/anonymisiert/anonym_01.pdf"))
    assert dateien.ist_ausgabedatei(Path("x/anonym_07_PRUEFEN.pdf"))
    assert dateien.ist_ausgabedatei(Path("x/Police_anonym.pdf"))
    assert not dateien.ist_ausgabedatei(Path("x/Police.pdf"))
    assert not dateien.ist_ausgabedatei(Path("x/anonymisiert_leitfaden.pdf"))
    assert dateien.ist_cloud_ordner(r"C:\Users\m\OneDrive - Makler GmbH\Kunden")
    assert dateien.ist_cloud_ordner("/home/m/Dropbox/Kunden")
    assert not dateien.ist_cloud_ordner(str(tmp_path))


# ----------------------------------------------------------------------
# Einstellungen
# ----------------------------------------------------------------------
def test_einstellungen_laden_speichern_rundlauf(tmp_path):
    pfad = tmp_path / "konfig" / "einstellungen.json"
    daten = {"kategorien": {"namen": True, "kfz": False}, "nie": ["Müller & Söhne"], "fenster": "900x800+10+10"}
    assert dateien.einstellungen_speichern(daten, pfad)
    assert dateien.einstellungen_laden(pfad) == daten
    assert json.loads(pfad.read_text(encoding="utf-8"))["nie"] == ["Müller & Söhne"]


def test_einstellungen_laden_defekt_oder_fehlend(tmp_path):
    pfad = tmp_path / "einstellungen.json"
    assert dateien.einstellungen_laden(pfad) == {}
    pfad.write_text("{kaputt", encoding="utf-8")
    assert dateien.einstellungen_laden(pfad) == {}
    pfad.write_text("[1, 2]", encoding="utf-8")
    assert dateien.einstellungen_laden(pfad) == {}


def test_einstellungen_pfad_im_nutzerprofil(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    pfad = dateien.einstellungen_pfad()
    assert pfad.name == "einstellungen.json"
    assert pfad.parent.name == "PDF-Anonymisierer"
    assert str(pfad).startswith(str(tmp_path))


def test_einstellungen_speichern_scheitert_leise(tmp_path):
    datei_statt_ordner = tmp_path / "datei"
    datei_statt_ordner.write_text("x")
    assert dateien.einstellungen_speichern({"a": 1}, datei_statt_ordner / "einstellungen.json") is False


# ----------------------------------------------------------------------
# Fehlerprotokoll
# ----------------------------------------------------------------------
def test_fehlerlog_pfad_nie_in_meipass(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "_MEI123"), raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    pfad = dateien.fehlerlog_pfad()
    assert pfad.name == "fehler.log"
    assert "_MEI123" not in str(pfad)
    assert pfad.parent.name == "PDF-Anonymisierer"
    assert str(pfad).startswith(str(tmp_path))


def test_fehlerlog_pfad_skriptbetrieb(monkeypatch, tmp_path):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    pfad = dateien.fehlerlog_pfad()
    assert pfad.name == "fehler.log"
    wurzel = Path(dateien.__file__).resolve().parent.parent
    assert pfad.parent in (wurzel, tmp_path / "Local" / "PDF-Anonymisierer", tmp_path / "state" / "PDF-Anonymisierer")


def test_fehler_protokollieren_schreibt_und_rotiert(monkeypatch, tmp_path):
    log = tmp_path / "logs" / "fehler.log"
    monkeypatch.setattr(dateien, "fehlerlog_pfad", lambda: log)
    monkeypatch.setattr(dateien, "FEHLERLOG_MAX_BYTES", 50)  # kleiner als jeder Eintrag, unabhaengig von Pfadlaengen
    try:
        raise RuntimeError("Simulierter Fehler 4711")
    except RuntimeError:
        ergebnis = dateien.fehler_protokollieren(*sys.exc_info())
    assert ergebnis == log
    inhalt = log.read_text(encoding="utf-8")
    assert "RuntimeError: Simulierter Fehler 4711" in inhalt and "====" in inhalt
    # Größenbegrenzung: zweiter Eintrag rotiert die (dann zu große) Datei
    try:
        raise ValueError("zweiter Fehler")
    except ValueError:
        dateien.fehler_protokollieren(*sys.exc_info())
    assert (tmp_path / "logs" / "fehler.log.1").exists()
    assert "zweiter Fehler" in log.read_text(encoding="utf-8")


def test_fehler_protokollieren_faellt_auf_zustandsordner_zurueck(monkeypatch, tmp_path):
    gesperrt = tmp_path / "gesperrt"
    gesperrt.write_text("ich bin eine Datei, kein Ordner")
    monkeypatch.setattr(dateien, "fehlerlog_pfad", lambda: gesperrt / "fehler.log")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    try:
        raise OSError("x")
    except OSError:
        ergebnis = dateien.fehler_protokollieren(*sys.exc_info())
    assert ergebnis is not None and ergebnis.exists()
    assert ergebnis.parent.name == "PDF-Anonymisierer"


# ----------------------------------------------------------------------
# Ordner öffnen
# ----------------------------------------------------------------------
def test_oeffne_ordner_ohne_fehlerabbruch(monkeypatch, tmp_path):
    aufrufe = []

    class FakeProzess:
        def __init__(self, befehl, **kw):
            aufrufe.append(befehl)

    monkeypatch.setattr(dateien.subprocess, "Popen", FakeProzess)
    monkeypatch.setattr(dateien.os, "startfile", lambda p: aufrufe.append(["startfile", p]), raising=False)
    datei = tmp_path / "a.pdf"
    datei.write_bytes(b"%PDF")
    assert dateien.oeffne_ordner(datei) is True              # Datei -> ihr Ordner
    assert aufrufe and str(tmp_path) in " ".join(map(str, aufrufe[-1]))
    assert dateien.oeffne_ordner(tmp_path / "fehlt") is False

    def kaputt(*a, **k):
        raise OSError("kein xdg-open")
    monkeypatch.setattr(dateien.subprocess, "Popen", kaputt)
    monkeypatch.setattr(dateien.os, "startfile", kaputt, raising=False)
    assert dateien.oeffne_ordner(tmp_path) is False          # kein Abbruch


# ----------------------------------------------------------------------
# Startskript
# ----------------------------------------------------------------------
def test_startskript_exporte_und_fehlerhaken(monkeypatch):
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)   # wird vom Import gesetzt, danach zurück
    import importlib
    import pdf_anonymisierer as pa
    importlib.reload(pa)
    for name in ("main", "AnonymisiererApp", "analysiere_pdf", "schwaerze_pdf", "sammle_pdfs",
                 "KATEGORIEN", "fehlerlog_pfad", "__version__", "DND_VERFUEGBAR"):
        assert hasattr(pa, name), name
    assert sys.excepthook is pa._unbehandelter_fehler
    quelle = Path(pa.__file__).read_text(encoding="utf-8")
    assert "multiprocessing.freeze_support()" in quelle
    assert quelle.index('if __name__ == "__main__":') < quelle.index("multiprocessing.freeze_support()")
    assert "gefahrlos" not in quelle


def test_startskript_fehlerhaken_schreibt_log(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    import pdf_anonymisierer as pa
    log = tmp_path / "fehler.log"
    monkeypatch.setattr(dateien, "fehlerlog_pfad", lambda: log)
    gezeigt = []
    import tkinter.messagebox as mb
    monkeypatch.setattr(mb, "showerror", lambda *a, **k: gezeigt.append(a))
    try:
        raise KeyError("test")
    except KeyError:
        pa._unbehandelter_fehler(*sys.exc_info())
    assert "KeyError" in log.read_text(encoding="utf-8")
    assert gezeigt and str(log) in gezeigt[0][1]


# ----------------------------------------------------------------------
# GR-11: Zwischendateien der Schwärzung
# ----------------------------------------------------------------------
def test_zwischendateien_sind_nie_eingabe(tmp_path):
    _leere_pdf(tmp_path / "ziel" / "a.pdf")
    _leere_pdf(tmp_path / "ziel" / "anonym_01.pdf")
    _leere_pdf(tmp_path / "ziel" / ".anonym_tmp_12345_ausgabe.pdf")
    assert dateien.ist_zwischendatei(Path("x/.anonym_tmp_12345_a.pdf"))
    assert dateien.ist_ausgabedatei(Path("x/.anonym_tmp_12345_ausgabe.pdf"))
    assert not dateien.ist_zwischendatei(Path("x/anonym_tmp.pdf"))
    bericht = dateien.sammle_pdfs_bericht([str(tmp_path / "ziel")])
    assert bericht["pdfs"] == [tmp_path / "ziel" / "a.pdf"]
    assert bericht["zwischendateien"] == [tmp_path / "ziel" / ".anonym_tmp_12345_ausgabe.pdf"]
    assert bericht["ausgaben"] == [tmp_path / "ziel" / "anonym_01.pdf"]
    # auch einzeln übergeben keine Eingabe (anders als echte Ausgaben, die man nachschwärzen darf)
    einzeln = dateien.sammle_pdfs_bericht([str(tmp_path / "ziel" / ".anonym_tmp_12345_ausgabe.pdf")])
    assert einzeln["pdfs"] == [] and len(einzeln["zwischendateien"]) == 1


def test_verwaiste_zwischendateien_werden_aufgeraeumt(tmp_path, monkeypatch):
    import os
    import time
    tot = tmp_path / ".anonym_tmp_2147480000_ausgabe.pdf"           # Prozess gibt es nicht
    eigen = tmp_path / f".anonym_tmp_{os.getpid()}_ausgabe.pdf"      # dieser Prozess: bleibt
    eltern = os.getppid()                                           # lebt sicher (startete pytest)
    lebend_jung = tmp_path / f".anonym_tmp_{eltern}_a.pdf"          # Prozess lebt, Datei jung -> bleibt
    lebend_alt = tmp_path / f".anonym_tmp_{eltern}_b.pdf"           # Prozess lebt, aber > 1 h alt -> weg
    andere = tmp_path / "anonym_01.pdf"
    for p in (tot, eigen, lebend_jung, lebend_alt, andere):
        p.write_bytes(b"%PDF")
    alt = time.time() - 2 * 3600
    os.utime(lebend_alt, (alt, alt))
    entfernt = dateien.zwischendateien_aufraeumen(tmp_path)
    assert sorted(entfernt) == sorted([tot, lebend_alt])
    assert eigen.exists() and lebend_jung.exists() and andere.exists()
    assert dateien.zwischendateien_aufraeumen(tmp_path / "gibt_es_nicht") == []


def test_prozess_lebt():
    import os
    assert dateien.prozess_lebt(os.getpid())
    assert not dateien.prozess_lebt(2147480000)
    assert not dateien.prozess_lebt(0)


# ----------------------------------------------------------------------
# GR-10: Einzelinstanz-Sperre
# ----------------------------------------------------------------------
def test_instanz_sperre_im_selben_prozess(tmp_path):
    pfad = tmp_path / "konfig" / "instanz.lock"
    erste = dateien.instanz_sperren(pfad)
    assert erste is not None and erste.aktiv
    assert dateien.instanz_sperren(pfad) is None
    erste.freigeben()
    erste.freigeben()                                          # zweimal freigeben schadet nicht
    zweite = dateien.instanz_sperren(pfad)
    assert zweite is not None and zweite.aktiv
    zweite.freigeben()


def test_instanz_sperre_ueber_prozesse_und_nach_absturz(tmp_path):
    """Hält ein anderer Prozess die Sperre, startet keine zweite Instanz; stirbt er (Absturz, Task beenden),
    gibt das Betriebssystem die Sperre frei – keine tote Sperrdatei."""
    import subprocess
    import time
    pfad = tmp_path / "instanz.lock"
    wurzel = Path(dateien.__file__).resolve().parent.parent
    kind = subprocess.Popen(
        [sys.executable, "-c", "import sys, time; sys.path.insert(0, sys.argv[1]); "
                               "from anonymisierer import dateien; s = dateien.instanz_sperren(sys.argv[2]); "
                               "print('gesperrt' if s and s.aktiv else 'frei', flush=True); time.sleep(60)",
         str(wurzel), str(pfad)], stdout=subprocess.PIPE, text=True)
    try:
        assert kind.stdout.readline().strip() == "gesperrt"
        assert dateien.instanz_sperren(pfad) is None
    finally:
        kind.kill()
        kind.wait(10)
    for _ in range(50):
        sperre = dateien.instanz_sperren(pfad)
        if sperre is not None:
            break
        time.sleep(0.1)
    assert sperre is not None and sperre.aktiv
    sperre.freigeben()


def test_instanz_sperre_ohne_schreibrecht_blockiert_nicht(tmp_path):
    datei_statt_ordner = tmp_path / "datei"
    datei_statt_ordner.write_text("x")
    sperre = dateien.instanz_sperren(datei_statt_ordner / "instanz.lock")
    assert sperre is not None and not sperre.aktiv              # Programm startet trotzdem
    sperre.freigeben()


# ----------------------------------------------------------------------
# KQ-14 / KQ-10: Fehlerprotokoll ohne Kundenordner, Schreibprobe nur einmal
# ----------------------------------------------------------------------
def test_fehlerprotokoll_enthaelt_keine_ordnernamen(monkeypatch, tmp_path):
    log = tmp_path / "fehler.log"
    monkeypatch.setattr(dateien, "fehlerlog_pfad", lambda: log)
    try:
        raise PermissionError(13, "Permission denied", "/home/makler/Kunden/Mustermann_Max/anonymisiert/anonym_02.pdf")
    except PermissionError:
        dateien.fehler_protokollieren(*sys.exc_info())
    inhalt = log.read_text(encoding="utf-8")
    assert "anonym_02.pdf" in inhalt and "Mustermann_Max" not in inhalt and "/home/makler" not in inhalt
    assert "test_dateien.py" in inhalt                             # Quelldatei bleibt für die Fehlersuche
    for text, erwartet in (
            (r"'C:\\Users\\Jörg Müller\\Kunden\\Meier Anna\\x.pdf'", "'…\\x.pdf'"),
            ("(/tmp/Kunden/Max Mustermann/anonymisiert): [Errno 17]", "(…/anonymisiert): [Errno 17]"),
            ("Seite 1/2 und/oder 3/4", "Seite 1/2 und/oder 3/4")):
        assert dateien.pfade_kuerzen(text) == erwartet


def test_schreibprobe_der_projektwurzel_nur_einmal(monkeypatch, tmp_path):
    aufrufe = []
    echt = dateien.tempfile.NamedTemporaryFile

    def zaehlend(*a, **k):
        aufrufe.append(k.get("dir"))
        return echt(*a, **k)
    monkeypatch.setattr(dateien.tempfile, "NamedTemporaryFile", zaehlend)
    monkeypatch.setattr(dateien, "_SCHREIBPROBEN", {})
    for _ in range(3):
        assert dateien._beschreibbar(tmp_path)
    assert len(aufrufe) == 1


# ----------------------------------------------------------------------
# CSV-Vorschau (Kundenliste)
# ----------------------------------------------------------------------
def test_csv_vorschau_kodierung_und_trennzeichen(tmp_path):
    utf8 = tmp_path / "utf8.csv"
    utf8.write_text("Name;Ort\nJörg Müller;Köln\n\nÄnne Groß;Fürth\n", encoding="utf-8-sig")
    v = dateien.csv_vorschau(utf8)
    assert v["trennzeichen"] == ";" and v["kodierung"] == "utf-8-sig"
    assert v["zeilen"] == [["Name", "Ort"], ["Jörg Müller", "Köln"], ["Änne Groß", "Fürth"]]
    ansi = tmp_path / "ansi.csv"
    ansi.write_bytes("Name,Ort\nJörg Müller,Köln\n".encode("cp1252"))
    v = dateien.csv_vorschau(ansi)
    assert v["trennzeichen"] == "," and v["kodierung"] == "cp1252" and v["zeilen"][1] == ["Jörg Müller", "Köln"]
    tab = tmp_path / "tab.txt"
    tab.write_text("a\tb\n" + "".join(f"{i}\t{i}\n" for i in range(20)), encoding="utf-8")
    assert dateien.csv_vorschau(tab, max_zeilen=3)["zeilen"] == [["a", "b"], ["0", "0"], ["1", "1"]]
    assert len(dateien.csv_vorschau(tab, max_zeilen=None)["zeilen"]) == 21
    xlsx = tmp_path / "liste.xlsx"
    xlsx.write_bytes(b"PK\x03\x04\x00\x00binary")
    import pytest
    with pytest.raises(ValueError):
        dateien.csv_vorschau(xlsx)


def test_startskript_exportiert_explizit():
    """KQ-07: keine dynamische Export-Schleife mehr, die Vertragsnamen werden ausdrücklich importiert."""
    import pdf_anonymisierer as pa
    for name in ("OcrDienst", "ocr_noetig", "_tessdata_finden"):
        assert hasattr(pa, name), name
    quelle = Path(pa.__file__).read_text(encoding="utf-8")
    assert "globals()[" not in quelle
