"""Beenden während eines Laufs (Korrekturrunde „Schließen“): Nach dem Beenden liegt im Ausgabeordner nie eine unfertige
Datei, auch nicht nach „Lauf läuft noch“ → „Ja“; Zwischendateien eines abgestürzten oder abgewürgten Programms werden
beim nächsten Start, Hinzufügen oder Schwärzen erkannt, gemeldet und gelöscht; Zwischenstände heißen nie „….pdf“ und
liegen nie im Ausgabeordner; die Rückfrage „Lauf läuft noch“ nennt Ausgaben, die noch auf die Freigabe warten.

GUI-Tests laufen unter Xvfb (ohne Display übersprungen), die Datei-Prüfungen überall. Helfer und Fixtures stammen aus
test_gui.py.
"""

import os
import sys
import threading
import time
import tkinter as tk
from pathlib import Path

import pytest

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen kennen nur den Namen "fitz"
    import fitz

from anonymisierer import dateien, gui, schwaerzung

from conftest import braucht_ocr
from test_gui import (FUND_TEL, FakeOcr, _prozesszustand, app, bis_geschlossen, dialoge,  # noqa: F401
                      fake_analyse, fake_schwaerzung, fenster_existiert, pdf_schreiben, pumpe, root, starte_lauf,
                      umgebung)

gui_test = pytest.mark.skipif(not os.environ.get("DISPLAY") and sys.platform != "win32",
                              reason="kein Display (DISPLAY nicht gesetzt)")
IBAN = "DE89 3704 0044 0532 0130 00"
TOTE_PID = 2147480000                       # eine PID, die es nicht gibt (Programm abgestürzt)


@pytest.fixture(autouse=True)
def _temp_ordner(monkeypatch, tmp_path):
    """Arbeitskopien und Zwischenstände nie im echten Programmordner des Benutzers."""
    monkeypatch.setattr(dateien, "temp_basis", lambda: tmp_path / "programm_temp")
    monkeypatch.setattr(dateien, "_SITZUNG", None)
    monkeypatch.setattr(dateien, "_SITZUNG_BEENDET", False)      # ein Test davor hat ein Fenster geschlossen
    yield
    dateien.sitzung_aufraeumen()


def zwischendateien(ordner: Path) -> list:
    return sorted(p.name for p in Path(ordner).rglob(".anonym_tmp_*")) if Path(ordner).exists() else []


def inhalt(ordner: Path) -> list:
    return sorted(p.name for p in Path(ordner).iterdir()) if Path(ordner).exists() else []


def status(app) -> str | None:
    try:
        return app.status_label.cget("text") if fenster_existiert(app.root) else None
    except tk.TclError:
        return None


def scan_mit_iban(pfad: Path, seiten: int) -> Path:
    """Eingescannter Brief (JPEG je Seite, kein Text in der Datei) mit IBAN auf jeder Seite – auf jeder Seite wird
    also geschwärzt, nach 10 Scan-Seiten speichert die Schwärzung einen Zwischenstand (STAPEL_SCANSEITEN)."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    for nr in range(seiten):
        vorlage = fitz.open()
        seite = vorlage.new_page(width=420, height=300)
        seite.insert_text((40, 70), f"Beitragsrechnung Seite {nr + 1}", fontsize=14, fontname="helv")
        seite.insert_text((40, 120), f"IBAN: {IBAN}", fontsize=14, fontname="helv")
        seite.insert_text((40, 170), "Bitte bis zum Monatsende zahlen.", fontsize=14, fontname="helv")
        bild = seite.get_pixmap(dpi=200, colorspace=fitz.csRGB, alpha=False).tobytes("jpeg", jpg_quality=80)
        vorlage.close()
        neu = doc.new_page(width=420, height=300)
        neu.insert_image(neu.rect, stream=bild)
    doc.save(pfad)
    doc.close()
    return pfad


# ----------------------------------------------------------------------
# Befund 1 (a): Schließen während der Schwärzung – keine unfertige Datei im Ausgabeordner
# ----------------------------------------------------------------------
@gui_test
@braucht_ocr
def test_beenden_waehrend_der_schwaerzung_hinterlaesst_keine_unfertige_datei(app, umgebung, dialoge, monkeypatch):
    """Befund: „Lauf läuft noch“ → „Ja“ zerstörte das Fenster sofort; der Arbeits-Thread (daemon) räumte nicht mehr
    auf, sobald das Programm endete. Im Ausgabeordner blieb der Zwischenstand .anonym_tmp_<PID>_…_a.pdf liegen: die
    ersten 10 Seiten geschwärzt, die übrigen pixelgleich mit dem Original. Echte Oberfläche, echte Engine, echte
    Texterkennung; nachgestellt wird nur, dass die aktuelle Seite nach dem Abbruch noch eine Sekunde weiterläuft.
    Geprüft wird in dem Moment, in dem das Fenster zu ist – danach endet das Programm, ein Daemon-Thread räumt dann
    nichts mehr auf."""
    from anonymisierer.ocr import OcrDienst
    monkeypatch.setattr(gui, "OcrDienst", OcrDienst)                 # echte Texterkennung statt Attrappe
    scan = scan_mit_iban(umgebung["tmp"] / "Kunde" / "Beitragsrechnungen.pdf", seiten=12)
    ausgabe_ordner = scan.parent / dateien.AUSGABE_ORDNER
    app.kategorie_vars["namen"].set(False)                          # ohne Sprachmodell (schneller); IBAN genügt
    app._pdfs_hinzufuegen([str(scan)])
    starte_lauf(app, app.analysieren, timeout=240)
    funde = app.analyse_ergebnisse[scan]["funde"]
    assert not app.analyse_ergebnisse[scan]["fehler"] and any("DE89" in f["text"] for f in funde), funde

    zwischenstand = threading.Event()
    gespeichert: list = []
    echt = schwaerzung._Lauf.zwischenspeichern

    def zwischenspeichern(lauf, nr):
        echt(lauf, nr)
        gespeichert.append(Path(lauf.geoeffnet_von))
        zwischenstand.set()
        if lauf.abbruch is not None and lauf.abbruch.wait(30):
            time.sleep(1.0)                                         # die aktuelle Seite wird noch beendet
    monkeypatch.setattr(schwaerzung._Lauf, "zwischenspeichern", zwischenspeichern)
    assert app.schwaerzen()
    lauf = app._lauf_thread
    assert pumpe(app.root, zwischenstand.is_set, timeout=240), "kein Zwischenstand gespeichert"
    assert gespeichert[0].exists()
    try:
        dialoge.antwort = True                                      # „Lauf läuft noch – wirklich beenden?“ – Ja
        vorher = len(dialoge.liste)
        app.schliessen()
        wartet = status(app)                                        # das Fenster ist noch da und sagt, worauf es wartet
        lauf_noch = lauf.is_alive()
        app.schliessen()                                            # ungeduldig noch einmal: keine zweite Frage
        assert bis_geschlossen(app, timeout=60), "Fenster schließt nicht"
        # jetzt endet das Programm: es darf nichts Unfertiges mehr geben
        assert zwischendateien(ausgabe_ordner) == []
        assert not gespeichert[0].exists(), gespeichert[0]
        assert inhalt(ausgabe_ordner) == []                         # keine (halbe) Ausgabe
        assert not lauf.is_alive()
        assert wartet == gui.BEENDEN_TEXT and lauf_noch             # schliessen() wartete nicht blockierend
        assert len(dialoge.liste) == vorher + 1 and dialoge.liste[-1][1] == gui.LAUF_LAEUFT_TITEL
        # (c) der Zwischenstand lag nie im Ausgabeordner und hieß nie „….pdf“
        assert gespeichert[0].parent != ausgabe_ordner and gespeichert[0].suffix != ".pdf", gespeichert[0]
        assert not list(dateien.temp_basis().glob("sitzung_*")), "Sitzungsordner mit Zwischenständen bleibt"
    finally:
        lauf.join(60)


# ----------------------------------------------------------------------
# Befund 1 (b): Zeitgrenze gerissen – die eigenen Zwischendateien werden trotzdem gelöscht
# ----------------------------------------------------------------------
@gui_test
def test_beenden_nach_zeitgrenze_loescht_eigene_zwischendateien(app, umgebung, dialoge, monkeypatch):
    """Hängt der abgebrochene Lauf länger als BEENDEN_WARTEN_S (hier verkürzt; z. B. MuPDF an einer Riesenseite),
    schließt das Fenster trotzdem – und löscht dabei die Zwischendateien DIESES Prozesses in allen Ausgabeordnern der
    Sitzung selbst. Legt der Lauf danach noch eine an, löscht sie der Nachlauf nach seinem Ende. Vorher blieb die Datei
    liegen."""
    monkeypatch.setattr(gui, "BEENDEN_WARTEN_S", 0.3, raising=False)
    pdf = pdf_schreiben(umgebung["tmp"] / "Kunde" / "Police.pdf")
    ausgabe_ordner = pdf.parent / dateien.AUSGABE_ORDNER
    gestartet, weiter = threading.Event(), threading.Event()

    def haengt(pdf_pfad, funde, melde=None, fortschritt=None, abbruch=None, ocr=None, ocr_cache=None,
               ziel_ordner=None):
        ordner = Path(ziel_ordner) if ziel_ordner else Path(pdf_pfad).parent / dateien.AUSGABE_ORDNER
        ordner.mkdir(parents=True, exist_ok=True)
        (ordner / f".anonym_tmp_{os.getpid()}_1_ausgabe.tmp").write_bytes(b"%PDF-1.4 unfertig")
        gestartet.set()
        weiter.wait(30)                                             # reagiert nicht auf den Abbruch
        (ordner / f".anonym_tmp_{os.getpid()}_1_bildreste.tmp").write_bytes(b"%PDF-1.4 unfertig")
        return {"original": pdf_pfad, "ausgabe": None, "treffer": 0, "uebersprungen": 0, "warnungen": [],
                "hinweise": [], "reste": [], "fehler": "Abgebrochen"}
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({"Police.pdf": [FUND_TEL]}))
    monkeypatch.setattr(gui, "schwaerze_pdf", haengt)
    app._pdfs_hinzufuegen([str(pdf)])
    starte_lauf(app, app.analysieren)
    assert app.schwaerzen()
    lauf = app._lauf_thread
    try:
        assert pumpe(app.root, gestartet.is_set, timeout=10)
        assert zwischendateien(ausgabe_ordner) == [f".anonym_tmp_{os.getpid()}_1_ausgabe.tmp"]
        fremd = ausgabe_ordner / f".anonym_tmp_{os.getppid()}_9_a.tmp"   # ein anderer, laufender Prozess
        fremd.write_bytes(b"%PDF-1.4")
        dialoge.antwort = True
        app.schliessen()
        assert bis_geschlossen(app, timeout=10)
        assert lauf.is_alive()                                      # Zeitgrenze gerissen, der Lauf hängt noch
        assert zwischendateien(ausgabe_ordner) == [fremd.name]      # (b): die eigene ist trotzdem weg
        nachlauf = [f for f in app._reste_threads.values() if f.is_alive()]
        assert nachlauf and not nachlauf[0].daemon                  # hält das Programm bis zum Aufräumen am Leben
    finally:
        weiter.set()
        lauf.join(20)
    for faden in app._reste_threads.values():
        faden.join(20)
    assert zwischendateien(ausgabe_ordner) == [fremd.name]          # auch die nach dem Schließen angelegte ist weg
    fehlerlog = umgebung["fehlerlog"]
    assert not fehlerlog.exists() or "nicht gelöscht" not in fehlerlog.read_text(encoding="utf-8")


# ----------------------------------------------------------------------
# Befund 2: „Lauf läuft noch“ nennt die Ausgaben, die noch auf die Freigabe warten
# ----------------------------------------------------------------------
@gui_test
def test_rueckfrage_lauf_laeuft_noch_nennt_offene_freigaben(app, umgebung, monkeypatch, dialoge):
    """Befund: Beim Schließen während eines Laufs entfiel „Freigabe noch offen“ – README und CHANGELOG versprechen die
    Rückfrage ohne Ausnahme. Jetzt nennt „Lauf läuft noch“ die wartenden Ausgaben (Voreinstellung „Nein“); eine
    zweite Frage gibt es nicht. Ohne offene Freigabe bleibt die Frage wie bisher."""
    kunden = ("KundeA", "KundeB")
    pdfs = [pdf_schreiben(umgebung["tmp"] / k / "Police.pdf") for k in kunden]
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({f"{k}/Police.pdf": [FUND_TEL] for k in kunden}))
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung([]))
    app._pdfs_hinzufuegen([str(p) for p in pdfs])
    starte_lauf(app, app.analysieren)
    starte_lauf(app, app.schwaerzen)
    assert app.offene_freigaben() == pdfs
    fragen = []

    def askyesno(titel=None, nachricht=None, **kw):
        fragen.append((titel, nachricht, kw))
        return dialoge.antwort
    monkeypatch.setattr(gui.messagebox, "askyesno", askyesno)
    weiter = threading.Event()
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({}, warten=weiter))
    app.analysieren()
    assert pumpe(app.root, lambda: app.laeuft, timeout=5)
    dialoge.antwort = False
    app.schliessen()
    assert [f[0] for f in fragen] == ["Lauf läuft noch"]             # eine Frage, nicht zwei
    titel, text, optionen = fragen[-1]
    assert text.startswith("Es läuft noch eine Analyse oder Schwärzung. Wirklich beenden?")
    assert ("2 Ausgaben warten noch auf Ihre Freigabe:\n  • KundeA/Police.pdf → anonym_01_PRUEFEN.pdf\n"
            "  • KundeB/Police.pdf → anonym_01_PRUEFEN.pdf") in text
    assert "Nach dem Beenden lassen sie sich nicht mehr freigeben." in text
    assert "„Nein“: Das Programm bleibt offen, der Lauf geht weiter." in text
    assert optionen.get("default") == gui.messagebox.NO and optionen.get("icon") == "warning"
    assert fenster_existiert(app.root) and app.laeuft and not app.abbruch.is_set()      # „Nein“: läuft weiter
    # eine Ausgabe freigegeben: die Frage nennt nur noch die andere
    weiter.set()
    assert pumpe(app.root, lambda: not app.laeuft, timeout=30)
    assert app.ausgabe_freigeben(pdfs[0]) is not None
    weiter.clear()
    app.analysieren()
    assert pumpe(app.root, lambda: app.laeuft, timeout=5)
    app.schliessen()
    text = fragen[-1][1]
    assert "Eine Ausgabe wartet noch auf Ihre Freigabe:\n  • KundeB/Police.pdf → anonym_01_PRUEFEN.pdf" in text
    assert "KundeA" not in text and fragen[-1][2].get("default") == gui.messagebox.NO
    # beide freigegeben: wieder die schlichte Frage (Voreinstellung wie bisher)
    weiter.set()
    assert pumpe(app.root, lambda: not app.laeuft, timeout=30)
    assert app.ausgabe_freigeben(pdfs[1]) is not None and app.offene_freigaben() == []
    weiter.clear()
    app.analysieren()
    assert pumpe(app.root, lambda: app.laeuft, timeout=5)
    dialoge.antwort = True
    app.schliessen()
    titel, text, optionen = fragen[-1]
    assert "Freigabe" not in text and "default" not in optionen
    weiter.set()
    assert bis_geschlossen(app)
    assert [f[0] for f in fragen] == ["Lauf läuft noch"] * 3 and gui.LAUF_LAEUFT_TITEL == "Lauf läuft noch"


# ----------------------------------------------------------------------
# Befund 1 (c): Zwischenstände heißen nie „….pdf“ und liegen nie im Ausgabeordner
# ----------------------------------------------------------------------
class PerfekteOcr:
    """OcrDienst-Ersatz: liefert die Wörter, die auf der Scan-Seite stehen."""
    hinweise: list = []

    def __init__(self, woerter):
        self.woerter_je_seite = woerter

    def woerter(self, pdf_pfad, seite_nr0, dpi=300, clip=None, **_):
        return list(self.woerter_je_seite.get(seite_nr0, [])), None

    def text(self, pdf_pfad, seite_nr0, dpi=300, **_):
        return " ".join(w[4] for w in self.woerter_je_seite.get(seite_nr0, []))

    def abbrechen(self):
        pass

    def schliessen(self):
        pass


def _scan_mit_woertern(pfad: Path, seiten: int):
    vorlage = fitz.open()
    seite = vorlage.new_page(width=420, height=300)
    seite.insert_text((40, 100), f"IBAN: {IBAN}", fontsize=14, fontname="helv")
    woerter = [tuple(w[:5]) for w in seite.get_text("words")]
    bild = seite.get_pixmap(dpi=150, colorspace=fitz.csRGB, alpha=False).tobytes("jpeg", jpg_quality=80)
    vorlage.close()
    doc = fitz.open()
    for _ in range(seiten):
        neu = doc.new_page(width=420, height=300)
        neu.insert_image(neu.rect, stream=bild)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    doc.save(pfad)
    doc.close()
    return pfad, {nr: woerter for nr in range(seiten)}


@pytest.mark.parametrize("mit_ordner", [True, False], ids=["zwischen_ordner", "ohne_vorgabe"])
def test_zwischenstaende_heissen_nie_pdf_und_liegen_nicht_im_ausgabeordner(tmp_path, monkeypatch, mit_ordner):
    """Befund 1 (c): Der Zwischenstand (erste Seiten geschwärzt, übrige wie im Original) hieß .anonym_tmp_…_a.pdf und
    lag im Ausgabeordner – nach einem Absturz sah er dort wie eine Ausgabe aus. Jetzt enden alle Hilfsdateien auf
    „.tmp“; mit zwischen_ordner (so ruft die Oberfläche auf) liegen die Zwischenstände dort, nie im Ausgabeordner. Die
    Hilfsdatei der fertigen Ausgabe bleibt im Ausgabeordner: nur so wird sie per os.replace atomar abgelegt."""
    monkeypatch.setattr(schwaerzung, "STAPEL_SCANSEITEN", 2)
    pdf, woerter = _scan_mit_woertern(tmp_path / "Kunde" / "scan.pdf", seiten=5)
    ziel = tmp_path / "Kunde" / "anonymisiert"
    zwischen = tmp_path / "programm_temp" / "sitzung_x"
    angelegt: list = []
    echt = schwaerzung._Lauf.tmp_pfad

    def tmp_pfad(lauf, kennung, ordner=None):
        p = echt(lauf, kennung, ordner) if ordner is not None else echt(lauf, kennung)
        angelegt.append((kennung, p))
        return p
    monkeypatch.setattr(schwaerzung._Lauf, "tmp_pfad", tmp_pfad)
    funde = [{"kategorie": "iban", "anzeige": "IBAN", "text": IBAN, "ersatz": "[IBAN]", "seiten": [], "anzahl": 1,
              "kontext": ""}]
    kwargs = {"zwischen_ordner": zwischen} if mit_ordner else {}
    e = schwaerzung.schwaerze_pdf(pdf, funde, ocr=PerfekteOcr(woerter), ocr_cache=woerter, **kwargs)
    assert e["fehler"] is None and e["ausgabe"] is not None and e["ausgabe"].parent == ziel, e
    stände = {p for k, p in angelegt if k in ("a", "b")}
    assert stände, "kein Zwischenstand gespeichert"
    for _, p in angelegt:
        assert p.name.startswith(f".anonym_tmp_{os.getpid()}_") and p.suffix == ".tmp", p
        assert dateien.ist_zwischendatei(p)
        assert not p.exists(), p                                    # alles wieder gelöscht
    assert {p.parent for p in stände} == ({zwischen} if mit_ordner else {ziel})
    assert {p.parent for k, p in angelegt if k == "ausgabe"} == {ziel}  # atomar im selben Ordner abgelegt
    assert inhalt(ziel) == [e["ausgabe"].name]


def test_ausgabe_nicht_ablegbar_hinterlaesst_keinen_leeren_namen(tmp_path, monkeypatch):
    """Scheitert das Ablegen der fertigen Ausgabe (os.replace, z. B. weil ein Virenscanner die Hilfsdatei sperrt oder
    sie beim Beenden schon gelöscht ist), blieb der reservierte, leere Name anonym_01.pdf im Ausgabeordner – er sah
    wie eine fertige Ausgabe aus. Jetzt wird er wieder gelöscht; die Datei endet ohne Ausgabe mit Fehler."""
    pdf = pdf_schreiben(tmp_path / "Kunde" / "Police.pdf")
    echt = os.replace

    def replace(quelle, ziel, *args, **kwargs):
        if Path(ziel).name.startswith("anonym_"):
            raise PermissionError(13, "Zugriff verweigert", str(ziel))
        return echt(quelle, ziel, *args, **kwargs)
    monkeypatch.setattr(schwaerzung.os, "replace", replace)
    funde = [{"kategorie": "namen", "anzeige": "Name", "text": "Max Mustermann", "ersatz": "[PERSON A]", "seiten": [],
              "anzahl": 1, "kontext": ""}]
    e = schwaerzung.schwaerze_pdf(pdf, funde, ocr=PerfekteOcr({}))
    assert e["ausgabe"] is None and "Ausgabe konnte nicht abgelegt werden" in (e["fehler"] or ""), e["fehler"]
    assert inhalt(pdf.parent / dateien.AUSGABE_ORDNER) == []


# ----------------------------------------------------------------------
# Absturz: Reste erkennen, melden und löschen – beim Hinzufügen, beim Start, beim Schwärzen
# ----------------------------------------------------------------------
def test_zwischendateien_jeder_endung_werden_erkannt(tmp_path):
    """dateien: Zwischendateien sind nie eine Eingabe – auch die neuen „….tmp“ in einem Ordner-Scan (vorher zählten
    dort nur „….pdf“); eigene_zwischendateien_loeschen löscht nur die dieses Prozesses."""
    ordner = tmp_path / "Kunde" / "anonymisiert"
    ordner.mkdir(parents=True)
    neu = ordner / f".anonym_tmp_{TOTE_PID}_77_ausgabe.tmp"
    alt = ordner / f".anonym_tmp_{TOTE_PID}_77_a.pdf"
    eigen = ordner / f".anonym_tmp_{os.getpid()}_5_b.tmp"
    for p in (neu, alt, eigen):
        p.write_bytes(b"%PDF-1.4")
    pdf_schreiben(tmp_path / "Kunde" / "Police.pdf")
    bericht = dateien.sammle_pdfs_bericht([str(tmp_path / "Kunde")])
    assert sorted(bericht["zwischendateien"]) == sorted([neu, alt, eigen])
    assert bericht["pdfs"] == [tmp_path / "Kunde" / "Police.pdf"] and not bericht["keine_pdf"]
    assert dateien.eigene_zwischendateien_loeschen(ordner) == [] and not eigen.exists()
    assert neu.exists() and alt.exists()                            # fremde PID: nicht beim Beenden löschen
    assert sorted(dateien.zwischendateien_aufraeumen(ordner)) == sorted([neu, alt])    # verwaist: weg
    assert dateien.eigene_zwischendateien_loeschen(tmp_path / "gibt_es_nicht") == []


def test_vermerk_der_ausgabeordner_ueberlebt_nur_einen_absturz(tmp_path):
    """Während eines Laufs vermerkt die Sitzung ihre Ausgabeordner; nach einem Absturz liest der nächste Start den
    Vermerk (vor dem Löschen der alten Sitzungsordner), nach einem normalen Lauf ist er wieder weg."""
    ziel = tmp_path / "Kunde" / "anonymisiert"
    sitzung = dateien.ausgabeordner_vermerken([ziel, tmp_path / "Upload"])
    assert sitzung is not None and (sitzung / dateien.AUSGABEORDNER_VERMERK).exists()
    assert dateien.ausgabeordner_frueherer_sitzungen() == []        # die eigene Sitzung zählt nie
    dateien.ausgabeordner_vermerk_loeschen()
    assert not (sitzung / dateien.AUSGABEORDNER_VERMERK).exists()
    # eine abgestürzte Sitzung (PID gibt es nicht mehr)
    tot = dateien.temp_basis() / f"sitzung_{TOTE_PID}_abc"
    tot.mkdir(parents=True)
    (tot / dateien.AUSGABEORDNER_VERMERK).write_text(f"{ziel}\n{ziel}\n\n", encoding="utf-8")
    assert dateien.ausgabeordner_frueherer_sitzungen() == [ziel]
    assert dateien.alte_sitzungen_aufraeumen() == [tot] and not tot.exists()
    assert dateien.ausgabeordner_frueherer_sitzungen() == []


@gui_test
def test_hinzufuegen_loescht_und_meldet_verwaiste_zwischendateien(app, umgebung):
    """Befund 1 (Absturz): Reste einer abgebrochenen Schwärzung wurden beim Hinzufügen nur „ignoriert – sie werden
    beim nächsten Schwärzen aufgeräumt“, bis dahin lagen sie im Ordner, der hochgeladen wird. Jetzt werden verwaiste
    gleich gelöscht und mit Ordner gemeldet; die eines laufenden Programms bleiben unberührt."""
    kunde = umgebung["tmp"] / "Kunde"
    pdf = pdf_schreiben(kunde / "Police.pdf")
    ordner = kunde / "anonymisiert"
    ordner.mkdir()
    reste = [ordner / f".anonym_tmp_{TOTE_PID}_1_a.pdf", ordner / f".anonym_tmp_{TOTE_PID}_1_ausgabe.tmp"]
    for p in reste:
        p.write_bytes(b"%PDF-1.4 halb geschwaerzt")
    lebend = ordner / f".anonym_tmp_{os.getppid()}_2_a.tmp"         # ein anderer, laufender Prozess
    lebend.write_bytes(b"%PDF-1.4")
    app._pdfs_hinzufuegen([str(kunde)])
    assert app.dateien == [pdf]
    assert not any(p.exists() for p in reste) and lebend.exists()
    protokoll = app.protokoll_text()
    assert (f"⚠ 2 unfertige Zwischendatei(en) einer abgebrochenen Schwärzung (.anonym_tmp_…) gelöscht – in {ordner}."
            in protokoll), protokoll
    assert "1 Zwischendatei(en) einer laufenden Schwärzung (.anonym_tmp_…) ignoriert" in protokoll
    assert app.warnungen_anzahl == 0                                # Meldung zur Auswahl, keine Warnung eines Laufs


@gui_test
def test_start_nach_absturz_loescht_und_meldet_reste(umgebung, dialoge, monkeypatch):
    """Befund 1 (Absturz): Das Programm wurde während einer Schwärzung abgewürgt. Der nächste Start findet die
    Ausgabeordner über den Vermerk der alten Sitzung (und den gespeicherten gemeinsamen Zielordner), löscht die Reste
    dort und meldet sie im Protokoll; der alte Sitzungsordner mit den Zwischenständen ist danach weg."""
    monkeypatch.setattr(gui, "DND_VERFUEGBAR", False)
    monkeypatch.setattr(gui, "ERSTSTART_NACH_MS", 60_000)
    monkeypatch.setattr(gui, "VORLADEN_NACH_MS", 60_000)            # kein Sprachmodell im Hintergrund
    tmp = umgebung["tmp"]
    ordner_a = tmp / "KundeA" / "anonymisiert"
    upload = tmp / "Upload"
    for o in (ordner_a, upload):
        o.mkdir(parents=True)
    rest_a = ordner_a / f".anonym_tmp_{TOTE_PID}_1_ausgabe.tmp"
    rest_u = upload / f".anonym_tmp_{TOTE_PID}_1_ausgabe.pdf"        # Rest einer älteren Version
    fertig = ordner_a / "anonym_01.pdf"
    for p in (rest_a, rest_u, fertig):
        p.write_bytes(b"%PDF-1.4")
    tot = dateien.temp_basis() / f"sitzung_{TOTE_PID}_abc"
    tot.mkdir(parents=True)
    (tot / f".anonym_tmp_{TOTE_PID}_1_a.tmp").write_bytes(b"%PDF-1.4 halb geschwaerzt")
    (tot / "ausgabeordner.txt").write_text(f"{ordner_a}\n", encoding="utf-8")
    dateien.einstellungen_speichern({"zielordner": str(upload), "zielordner_aktiv": False, "hinweis_gelesen": True})
    app = gui.main(ereignisschleife=False)
    try:
        app.root.tk.willdispatch()
        assert not tot.exists()                                     # Zwischenstände der alten Sitzung: weg
        assert pumpe(app.root, lambda: "unfertige Zwischendatei" in app.protokoll_text(), timeout=10)
        assert not rest_a.exists() and not rest_u.exists() and fertig.exists()
        zeile = [z for z in app.protokoll_text().splitlines() if "unfertige Zwischendatei" in z][0]
        assert zeile.startswith("⚠ Beim letzten Programmende blieb eine Schwärzung unfertig (Absturz?): 2 unfertige "
                                "Zwischendatei(en)"), zeile
        assert str(ordner_a) in zeile and str(upload) in zeile
        assert dateien.AUSGABEORDNER_VERMERK == "ausgabeordner.txt"
    finally:
        app.schliessen()
