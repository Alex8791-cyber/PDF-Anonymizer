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
    monkeypatch.setattr(dateien, "FEHLERLOG_MAX_BYTES", 300)
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
