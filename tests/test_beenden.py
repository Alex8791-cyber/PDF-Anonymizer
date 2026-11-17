"""Beenden während eines Laufs (Korrekturrunde „Schließen“): Nach dem Beenden liegt im Ausgabeordner nie eine unfertige
Datei, auch nicht nach „Lauf läuft noch“ → „Ja“; Zwischendateien eines abgestürzten oder abgewürgten Programms werden
beim nächsten Start, Hinzufügen oder Schwärzen erkannt, gemeldet und gelöscht; Zwischenstände heißen nie „….pdf“ und
liegen nie im Ausgabeordner; die Rückfrage „Lauf läuft noch“ nennt Ausgaben, die noch auf die Freigabe warten.

Runde 2 (Gegenprüfung zu 5b6cf87): Die Rückfrage nennt auch die schon fertigen Ausgaben des LAUFENDEN Laufs; das
Beenden liest Ausgabeordner nur, wo eigene Reste sein können – im Hintergrund, ein hängendes Netzlaufwerk hält das
Fenster nicht auf; Hilfsdateien tragen eine Rechnerkennung, die eines anderen Rechners (gemeinsame Freigabe) gelten
erst nach 24 Stunden als verwaist, der gemeinsame Zielordner wird beim Start nur gelesen, wenn er eingeschaltet ist.

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
    dort nur „….pdf“); eigene_zwischendateien_loeschen löscht nur die dieses Prozesses. Seit Runde 2 tragen die Namen
    eine Rechnerkennung: Die eines abgestürzten Prozesses dieses Rechners ist sofort verwaist, eine in der älteren
    Namensform (Rechner unbekannt, vielleicht ein Kollege an derselben Freigabe) erst nach 24 Stunden."""
    ordner = tmp_path / "Kunde" / "anonymisiert"
    ordner.mkdir(parents=True)
    neu = ordner / eigener_name(TOTE_PID, "77_ausgabe.tmp")
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
    assert dateien.zwischendateien_aufraeumen(ordner) == [neu]      # dieser Rechner, Prozess abgestürzt: weg
    assert alt.exists()                                             # Rechner unbekannt: erst nach 24 Stunden
    _altern(alt, 25)
    assert dateien.zwischendateien_aufraeumen(ordner) == [alt]
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
    gleich gelöscht und mit Ordner gemeldet; die eines laufenden Programms bleiben unberührt. Verwaist (Runde 2):
    die eines abgestürzten Prozesses dieses Rechners, eine ältere Namensform ohne Rechnerkennung erst nach 24 Stunden
    (sie könnte zu einem laufenden Programm auf einem anderen Rechner gehören)."""
    kunde = umgebung["tmp"] / "Kunde"
    pdf = pdf_schreiben(kunde / "Police.pdf")
    ordner = kunde / "anonymisiert"
    ordner.mkdir()
    reste = [ordner / f".anonym_tmp_{TOTE_PID}_1_a.pdf", ordner / eigener_name(TOTE_PID, "1_ausgabe.tmp")]
    for p in reste:
        p.write_bytes(b"%PDF-1.4 halb geschwaerzt")
    _altern(reste[0], 25)                                           # ältere Version, über 24 Stunden alt
    lebend = ordner / eigener_name(os.getppid(), "2_a.tmp")         # ein anderer, laufender Prozess dieses Rechners
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
@pytest.mark.parametrize("zielordner_aktiv", [True, False], ids=["zielordner_an", "zielordner_aus"])
def test_start_nach_absturz_loescht_und_meldet_reste(umgebung, dialoge, monkeypatch, zielordner_aktiv):
    """Befund 1 (Absturz): Das Programm wurde während einer Schwärzung abgewürgt. Der nächste Start findet die
    Ausgabeordner über den Vermerk der alten Sitzung (und den gemeinsamen Zielordner, wenn er eingeschaltet ist),
    löscht die Reste dort und meldet sie im Protokoll; der alte Sitzungsordner mit den Zwischenständen ist danach weg.
    Runde 2 (Befund 3): Ist der gemeinsame Zielordner ausgeschaltet, liest der Start ihn nicht – vorher löschte er
    dort bei jedem Start (auch die Hilfsdatei eines Kollegen an derselben Freigabe) und meldete sie als eigenen
    Absturz. Die Reste tragen die PID der abgestürzten Sitzung: sie sind sicher verwaist, auch in der älteren
    Namensform."""
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
    dateien.einstellungen_speichern({"zielordner": str(upload), "zielordner_aktiv": zielordner_aktiv,
                                     "hinweis_gelesen": True})
    app = gui.main(ereignisschleife=False)
    try:
        app.root.tk.willdispatch()
        assert not tot.exists()                                     # Zwischenstände der alten Sitzung: weg
        assert pumpe(app.root, lambda: "unfertige Zwischendatei" in app.protokoll_text(), timeout=10)
        for faden in [f for f in threading.enumerate() if f.name == "Reste-beim-Start"]:
            faden.join(10)
        pumpe(app.root, timeout=0.2)
        assert not rest_a.exists() and fertig.exists()
        assert rest_u.exists() is not zielordner_aktiv              # ausgeschaltet: der Start liest den Ordner nicht
        zeilen = [z for z in app.protokoll_text().splitlines() if "unfertige Zwischendatei" in z]
        assert len(zeilen) == 1, zeilen
        anzahl = 2 if zielordner_aktiv else 1
        assert zeilen[0].startswith(f"⚠ Beim letzten Programmende blieb eine Schwärzung unfertig (Absturz?): {anzahl} "
                                    f"unfertige Zwischendatei(en)"), zeilen[0]
        assert str(ordner_a) in zeilen[0] and (str(upload) in zeilen[0]) is zielordner_aktiv
        assert dateien.AUSGABEORDNER_VERMERK == "ausgabeordner.txt"
    finally:
        app.schliessen()


# ======================================================================
# Korrekturrunde „Schließen“, Runde 2 (Befunde der Gegenprüfung zu 5b6cf87)
# ======================================================================
FREMDER_RECHNER = "0badc0de"                # Rechnerkennung eines anderen Rechners (Kollege an derselben Freigabe)


def eigener_name(pid: int, rest: str) -> str:
    """Name einer Hilfsdatei, die ein Prozess (pid) auf DIESEM Rechner angelegt hat."""
    return f".anonym_tmp_{pid}_r{dateien.rechner_kennung()}_{rest}"


def fremder_name(pid: int, rest: str) -> str:
    """Name einer Hilfsdatei eines anderen Rechners (seine PID sagt hier nichts)."""
    return f".anonym_tmp_{pid}_r{FREMDER_RECHNER}_{rest}"


def _altern(pfad: Path, stunden: float):
    zeit = time.time() - stunden * 3600
    os.utime(pfad, (zeit, zeit))


def _zwei_kunden_mit_wartendem_zweiten(umgebung, monkeypatch):
    """KundeA und KundeB schwärzen (Freigabe vor Weitergabe: anonym_01_PRUEFEN.pdf); die Schwärzung von KundeB wartet,
    bis „weiter“ gesetzt oder der Lauf abgebrochen ist. Liefert (pdfs, zweite_laeuft, weiter)."""
    kunden = ("KundeA", "KundeB")
    pdfs = [pdf_schreiben(umgebung["tmp"] / k / "Police.pdf") for k in kunden]
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({f"{k}/Police.pdf": [FUND_TEL] for k in kunden}))
    innen = fake_schwaerzung([])
    zweite_laeuft, weiter = threading.Event(), threading.Event()

    def schwaerze_pdf(pdf_pfad, funde, melde=None, fortschritt=None, abbruch=None, ocr=None, ocr_cache=None,
                      ziel_ordner=None):
        if Path(pdf_pfad).parent.name == "KundeB":
            zweite_laeuft.set()
            while not weiter.wait(0.02):
                if abbruch is not None and abbruch.is_set():
                    return {"original": pdf_pfad, "ausgabe": None, "treffer": 0, "uebersprungen": 0, "warnungen": [],
                            "hinweise": [], "reste": [], "fehler": "Abgebrochen"}
        return innen(pdf_pfad, funde, melde, fortschritt, abbruch, ocr, ocr_cache, ziel_ordner)
    monkeypatch.setattr(gui, "schwaerze_pdf", schwaerze_pdf)
    return pdfs, zweite_laeuft, weiter


# ----------------------------------------------------------------------
# Runde 2, Befund 1: „Lauf läuft noch“ nennt auch die schon fertigen Ausgaben des LAUFENDEN Laufs
# ----------------------------------------------------------------------
@gui_test
def test_rueckfrage_nennt_fertige_ausgaben_des_laufenden_laufs(app, umgebung, monkeypatch, dialoge):
    """Befund: Mehrere Dateien schwärzen und mittendrin schließen – der häufigste Fall. „Lauf läuft noch“ nannte nur
    Ausgaben FRÜHERER Läufe; die schon fertige anonym_01_PRUEFEN.pdf des laufenden Laufs fehlte (self.ausgaben kennt
    sie erst nach dem Lauf), und die Voreinstellung blieb „Ja“ – danach lässt sie sich nie mehr freigeben. Der Satz
    „„Nein“: … Prüfen und freigeben können Sie in der Vorschau“ stimmte erst nach dem Lauf: bis dahin ist die Vorschau
    gesperrt, und ausgabe_freigeben weist ab."""
    pdfs, zweite_laeuft, weiter = _zwei_kunden_mit_wartendem_zweiten(umgebung, monkeypatch)
    app._pdfs_hinzufuegen([str(p) for p in pdfs])
    starte_lauf(app, app.analysieren)
    assert app.freigabe_var.get()                                   # Standard: „Freigabe vor Weitergabe“
    assert app.schwaerzen()
    try:
        assert pumpe(app.root, zweite_laeuft.is_set, timeout=10)
        fertig = pdfs[0].parent / dateien.AUSGABE_ORDNER / "anonym_01_PRUEFEN.pdf"
        assert fertig.exists() and app.offene_freigaben() == []     # KundeA fertig, noch nicht in ausgaben
        fragen = []

        def askyesno(titel=None, nachricht=None, **kw):
            fragen.append((titel, nachricht, kw))
            return dialoge.antwort
        monkeypatch.setattr(gui.messagebox, "askyesno", askyesno)
        dialoge.antwort = False                                     # „Nein“: das Programm bleibt offen
        app.schliessen()
        assert [f[0] for f in fragen] == [gui.LAUF_LAEUFT_TITEL]    # eine Frage, nicht zwei
        titel, text, optionen = fragen[0]
        wartet = "Eine Ausgabe wartet noch auf Ihre Freigabe:\n  • KundeA/Police.pdf → anonym_01_PRUEFEN.pdf"
        assert wartet in text, text
        assert "KundeB" not in text                                 # noch nicht fertig
        assert "Nach dem Beenden lässt sie sich nicht mehr freigeben." in text
        assert optionen.get("default") == gui.messagebox.NO and optionen.get("icon") == "warning"
        # „Nein“: der Lauf geht weiter – freigeben erst danach
        assert ("„Nein“: Das Programm bleibt offen, der Lauf geht weiter. Prüfen und freigeben können Sie nach dem "
                "Ende des Laufs in der Vorschau (Doppelklick auf die Datei).") in text, text
        assert fenster_existiert(app.root) and app.laeuft and not app.abbruch.is_set()
        assert app.ausgabe_freigeben(pdfs[0]) is None               # während des Laufs geht Freigeben wirklich nicht
    finally:
        weiter.set()
    assert pumpe(app.root, lambda: not app.laeuft, timeout=20)
    assert app.offene_freigaben() == pdfs                           # nach dem Lauf: beide freizugeben
    assert app.ausgabe_freigeben(pdfs[0]) is not None


@gui_test
def test_ja_waehrend_des_laufs_nach_hinweis_auf_die_fertige_ausgabe(app, umgebung, monkeypatch, dialoge):
    """Befund (Folge): Mit „Ja“ blieb die fertige anonym_01_PRUEFEN.pdf des laufenden Laufs für immer unfreigegeben,
    ohne dass die Rückfrage es sagte. Jetzt steht sie in der Rückfrage (Voreinstellung „Nein“); nach „Ja“ wird der
    Lauf abgebrochen, das Fenster schließt, die Ausgabe bleibt unverändert liegen (nicht weitergeben)."""
    pdfs, zweite_laeuft, weiter = _zwei_kunden_mit_wartendem_zweiten(umgebung, monkeypatch)
    app._pdfs_hinzufuegen([str(p) for p in pdfs])
    starte_lauf(app, app.analysieren)
    assert app.schwaerzen()
    lauf = app._lauf_thread
    try:
        assert pumpe(app.root, zweite_laeuft.is_set, timeout=10)
        fragen = []

        def askyesno(titel=None, nachricht=None, **kw):
            fragen.append((titel, nachricht, kw))
            return True
        monkeypatch.setattr(gui.messagebox, "askyesno", askyesno)
        app.schliessen()
        assert bis_geschlossen(app, timeout=30)
    finally:
        weiter.set()
        lauf.join(20)
    assert [f[0] for f in fragen] == [gui.LAUF_LAEUFT_TITEL]
    titel, text, optionen = fragen[0]
    wartet = "Eine Ausgabe wartet noch auf Ihre Freigabe:\n  • KundeA/Police.pdf → anonym_01_PRUEFEN.pdf"
    assert wartet in text, text
    assert optionen.get("default") == gui.messagebox.NO
    assert inhalt(pdfs[0].parent / dateien.AUSGABE_ORDNER) == ["_zuordnung.txt", "anonym_01_PRUEFEN.pdf"]
    assert not (pdfs[1].parent / dateien.AUSGABE_ORDNER).exists()   # KundeB: abgebrochen, keine (halbe) Ausgabe


# ----------------------------------------------------------------------
# Runde 2, Befund 2: Beenden liest Ausgabeordner nicht im Hauptthread, nicht doppelt – nur, wo Reste sein können
# ----------------------------------------------------------------------
@gui_test
def test_beenden_nach_dem_lauf_greift_auf_keinen_ausgabeordner_zu(umgebung, dialoge, monkeypatch):
    """Befund: Beim Schließen las der Hauptthread jeden Ausgabeordner der Sitzung, und zwar zweimal
    (_beenden_abschliessen → _aufraeumen, danach die <Destroy>-Bindung von main → noch einmal _aufraeumen) – auch ohne
    laufenden Lauf. Ein nicht erreichbares Netzlaufwerk (VPN getrennt) hielt so das Fenster auf. Nach einem Lauf hat
    dessen Ende die eigenen Zwischendateien schon gelöscht: Jetzt greift das Beenden auf keinen Ausgabeordner zu (wie
    vor der Korrekturrunde). Echtes main() samt <Destroy>-Bindung."""
    monkeypatch.setattr(gui, "DND_VERFUEGBAR", False)
    monkeypatch.setattr(gui, "ERSTSTART_NACH_MS", 60_000)
    monkeypatch.setattr(gui, "VORLADEN_NACH_MS", 60_000)            # kein Sprachmodell im Hintergrund
    dateien.einstellungen_speichern({"hinweis_gelesen": True})
    kunden = ("KundeA", "KundeB")
    pdfs = [pdf_schreiben(umgebung["tmp"] / "Netz" / k / "Police.pdf") for k in kunden]
    ausgabeordner = [p.parent / dateien.AUSGABE_ORDNER for p in pdfs]
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({f"{k}/Police.pdf": [FUND_TEL] for k in kunden}))
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung([]))
    app = gui.main(ereignisschleife=False)
    try:
        app.root.tk.willdispatch()
        app._pdfs_hinzufuegen([str(p) for p in pdfs])
        starte_lauf(app, app.analysieren)
        starte_lauf(app, app.schwaerzen)
        assert all(o.is_dir() for o in ausgabeordner)
        zugriffe = []
        echt_loeschen, echt_iterdir = dateien.eigene_zwischendateien_loeschen, Path.iterdir

        def loeschen(ordner, *args, **kwargs):
            zugriffe.append(("eigene", threading.current_thread().name, Path(ordner).parent.name))
            return echt_loeschen(ordner, *args, **kwargs)

        def iterdir(self):
            if self in ausgabeordner:
                zugriffe.append(("iterdir", threading.current_thread().name, self.parent.name))
            return echt_iterdir(self)
        monkeypatch.setattr(dateien, "eigene_zwischendateien_loeschen", loeschen)
        monkeypatch.setattr(Path, "iterdir", iterdir)
        dialoge.antwort = True                                      # „Freigabe noch offen – trotzdem beenden?“ – Ja
        app.schliessen()
        assert not fenster_existiert(app.root) and app.beendet
        for faden in list(app._reste_threads.values()):
            faden.join(10)
        assert zugriffe == []
    finally:
        if fenster_existiert(app.root):
            dialoge.antwort = True
            app.schliessen()


@gui_test
def test_beenden_haengendes_laufwerk_haelt_das_fenster_nicht_auf(app, umgebung, monkeypatch, dialoge):
    """Befund: Blieb nach einem Lauf in einem Ausgabeordner eine eigene Zwischendatei liegen (unter Windows beim Löschen
    noch geöffnet, z. B. vom Virenscanner) und ist das Laufwerk beim Beenden nicht erreichbar (VPN getrennt), hing das
    Fenster beim Schließen, bis Windows aufgab. Jetzt löscht ein Hilfs-Thread je Ordner: Das Fenster wartet höchstens
    BEENDEN_ORDNER_WARTEN_S auf den ersten Versuch, der Nachlauf (nicht im Hintergrund) höchstens RESTE_WARTEN_S – dann
    endet das Programm, und der Ordner bleibt für den nächsten Start vermerkt. Ein erreichbarer Ordner ist im Moment,
    in dem das Fenster zu ist, sauber (Befund 1 der ersten Runde bleibt behoben); jeder Ordner wird nur einmal
    gelesen."""
    monkeypatch.setattr(gui, "BEENDEN_ORDNER_WARTEN_S", 0.5, raising=False)
    monkeypatch.setattr(gui, "RESTE_WARTEN_S", 2.0)
    kunden = ("Netz", "Lokal")
    pdfs = [pdf_schreiben(umgebung["tmp"] / k / "Police.pdf") for k in kunden]
    netz, lokal = (p.parent / dateien.AUSGABE_ORDNER for p in pdfs)
    rest = f".anonym_tmp_{os.getpid()}_1_ausgabe.tmp"                # eigene Hilfsdatei (dieser Prozess)
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({f"{k}/Police.pdf": [FUND_TEL] for k in kunden}))
    innen = fake_schwaerzung([])

    def schwaerze_pdf(pdf_pfad, funde, melde=None, fortschritt=None, abbruch=None, ocr=None, ocr_cache=None,
                      ziel_ordner=None):
        ergebnis = innen(pdf_pfad, funde, melde, fortschritt, abbruch, ocr, ocr_cache, ziel_ordner)
        (Path(ergebnis["ausgabe"]).parent / rest).write_bytes(b"%PDF-1.4 unfertig")   # bleibt liegen
        return ergebnis
    monkeypatch.setattr(gui, "schwaerze_pdf", schwaerze_pdf)
    gesperrt = {netz / rest, lokal / rest}                          # am Ende des Laufs noch geöffnet
    echt_unlink = Path.unlink

    def unlink(self, *args, **kwargs):
        if self in gesperrt:
            raise PermissionError(13, "Der Prozess kann nicht auf die Datei zugreifen", str(self))
        return echt_unlink(self, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", unlink)
    app._pdfs_hinzufuegen([str(p) for p in pdfs])
    starte_lauf(app, app.analysieren)
    starte_lauf(app, app.schwaerzen)
    assert (netz / rest).exists() and (lokal / rest).exists()       # das Ende des Laufs konnte sie nicht löschen
    gesperrt.clear()                                                # jetzt wieder frei …
    haengt = threading.Event()
    echt_iterdir = Path.iterdir
    lesen = []

    def iterdir(self):
        if self in (netz, lokal):
            lesen.append(self.parent.name)
        if self == netz:
            haengt.wait(6)                                          # … aber das Netzlaufwerk antwortet nicht
        return echt_iterdir(self)
    monkeypatch.setattr(Path, "iterdir", iterdir)
    try:
        dialoge.antwort = True                                      # „Freigabe noch offen“ – trotzdem beenden
        beginn = time.monotonic()
        app.schliessen()
        dauer = time.monotonic() - beginn
        assert not fenster_existiert(app.root) and app.beendet
        assert dauer < 3.0, f"schliessen() blockierte {dauer:.1f} s"
        assert not (lokal / rest).exists()                          # erreichbar: beim Schließen schon gelöscht
        nachlauf = list(app._reste_threads.values())
        assert nachlauf and all(not f.daemon for f in nachlauf)     # hält das Programm bis zum Aufräumen am Leben …
        for faden in nachlauf:
            faden.join(6)
        assert not any(f.is_alive() for f in nachlauf)              # … aber nicht länger als RESTE_WARTEN_S
        assert lesen.count("Lokal") == 1 and lesen.count("Netz") == 1   # jeder Ordner einmal, nicht doppelt
        # der Ordner, der nicht zu erreichen war, bleibt für den nächsten Start vermerkt
        sitzungen = list(dateien.temp_basis().glob("sitzung_*"))
        assert len(sitzungen) == 1 and [p.name for p in sitzungen[0].iterdir()] == [dateien.AUSGABEORDNER_VERMERK]
        vermerk = (sitzungen[0] / dateien.AUSGABEORDNER_VERMERK).read_text(encoding="utf-8").splitlines()
        assert vermerk == [str(netz)]
        assert "nicht gelöscht" in umgebung["fehlerlog"].read_text(encoding="utf-8")
    finally:
        haengt.set()


@gui_test
def test_ausgabeordner_am_laufende_nicht_lesbar_wird_beim_beenden_aufgeraeumt(app, umgebung, monkeypatch, dialoge):
    """Gegenstück zu Befund 2: Das Beenden liest nur noch Ausgabeordner, in denen eigene Reste sein können – keiner darf
    dabei verloren gehen. Ist ein Ausgabeordner am Ende des Laufs nicht lesbar (Netzlaufwerk kurz getrennt), bleibt er
    als „Ordner mit Resten“ vermerkt; ist er beim Beenden wieder erreichbar, löscht das Beenden die dort liegen
    gebliebene Hilfsdatei – im Moment, in dem das Fenster zu ist, liegt dort nichts Unfertiges mehr."""
    pdf = pdf_schreiben(umgebung["tmp"] / "Netz" / "Police.pdf")
    ordner = pdf.parent / dateien.AUSGABE_ORDNER
    rest = f".anonym_tmp_{os.getpid()}_1_ausgabe.tmp"
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({"Police.pdf": [FUND_TEL]}))
    innen = fake_schwaerzung([])
    getrennt = threading.Event()

    def schwaerze_pdf(pdf_pfad, funde, melde=None, fortschritt=None, abbruch=None, ocr=None, ocr_cache=None,
                      ziel_ordner=None):
        ergebnis = innen(pdf_pfad, funde, melde, fortschritt, abbruch, ocr, ocr_cache, ziel_ordner)
        (Path(ergebnis["ausgabe"]).parent / rest).write_bytes(b"%PDF-1.4 unfertig")   # ihr Löschen scheiterte
        getrennt.set()                                              # und jetzt ist das Netzlaufwerk weg
        return ergebnis
    monkeypatch.setattr(gui, "schwaerze_pdf", schwaerze_pdf)
    echt_iterdir = Path.iterdir

    def iterdir(self):
        if self == ordner and getrennt.is_set():
            raise OSError(22, "Der angegebene Netzwerkname ist nicht mehr verfügbar", str(self))
        return echt_iterdir(self)
    monkeypatch.setattr(Path, "iterdir", iterdir)
    app._pdfs_hinzufuegen([str(pdf)])
    starte_lauf(app, app.analysieren)
    starte_lauf(app, app.schwaerzen)
    assert (ordner / rest).exists()
    assert app._ordner_mit_resten == {ordner}
    vermerk = dateien.aktuelle_sitzung() / dateien.AUSGABEORDNER_VERMERK
    assert vermerk.read_text(encoding="utf-8").splitlines() == [str(ordner)]   # für einen Absturz bis zum Beenden
    getrennt.clear()                                                # beim Beenden wieder erreichbar
    dialoge.antwort = True                                          # „Freigabe noch offen“ – trotzdem beenden
    app.schliessen()
    assert not fenster_existiert(app.root)
    assert not (ordner / rest).exists() and inhalt(ordner) == ["_zuordnung.txt", "anonym_01_PRUEFEN.pdf"]
    for faden in list(app._reste_threads.values()):
        faden.join(10)
    assert not list(dateien.temp_basis().glob("sitzung_*"))         # alles erledigt: auch kein Vermerk mehr


@gui_test
def test_beenden_wartet_auf_den_eingereihten_abschluss_des_laufs(app, umgebung, monkeypatch, dialoge):
    """Gegenprobe des Prüfers (Nachschwärzen und Beenden): Wird die neue Ausgabe trotz Abbruch noch fertig, verwirft der
    Abschluss des Laufs (_schwaerzen_fertig) die alte – sonst lägen beide im Ausgabeordner. Der Arbeits-Thread reiht den
    Abschluss vor seinem Ende per after() ein. Sah das wartende Fenster den Thread schon beendet, bevor der Abschluss
    an der Reihe war, schloss es sofort, und der Abschluss lief nie (die Gegenprobe mit BEENDEN_PRUEFEN_MS = 0 war auf
    5b6cf87 mal rot, mal grün). Hier ohne Zufall nachgestellt: Der Abschluss ist eingereiht, der Thread zu Ende, dann
    sieht das Fenster nach."""
    monkeypatch.setattr(gui, "BEENDEN_PRUEFEN_MS", 60_000)          # nachgesehen wird unten von Hand
    pdf = pdf_schreiben(umgebung["tmp"] / "Kunde" / "Police.pdf")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({"Police.pdf": [FUND_TEL]}))
    innen = fake_schwaerzung([])
    monkeypatch.setattr(gui, "schwaerze_pdf", innen)
    app._pdfs_hinzufuegen([str(pdf)])
    starte_lauf(app, app.analysieren)
    starte_lauf(app, app.schwaerzen)
    alt = Path(app.ausgaben[pdf]["pfad"])
    assert alt.exists()
    gestartet = threading.Event()

    def spaet_fertig(pdf_pfad, funde, melde=None, fortschritt=None, abbruch=None, ocr=None, ocr_cache=None,
                     ziel_ordner=None):
        gestartet.set()
        abbruch.wait(20)                    # der Abbruch kommt nach der letzten Abbruchprüfung: die Ausgabe wird fertig
        return innen(pdf_pfad, funde, melde, fortschritt, abbruch, ocr, ocr_cache, ziel_ordner)
    monkeypatch.setattr(gui, "schwaerze_pdf", spaet_fertig)
    abgefangen = []
    echt = app._im_hauptthread

    def im_hauptthread(funktion, *args):
        if getattr(funktion, "__name__", "") == "_schwaerzen_fertig":
            abgefangen.append((funktion, args))           # wird unten eingereiht – wie vom Arbeits-Thread
            return
        echt(funktion, *args)
    monkeypatch.setattr(app, "_im_hauptthread", im_hauptthread)
    assert app.schwaerzen(nur=[pdf], ersetzt=alt)
    lauf = app._lauf_thread
    assert pumpe(app.root, gestartet.is_set, timeout=10)
    dialoge.antwort = True
    app.schliessen()                                                # „Lauf läuft noch“ – Ja: abbrechen, warten
    assert fenster_existiert(app.root) and app.status_label.cget("text") == gui.BEENDEN_TEXT
    assert pumpe(app.root, lambda: not lauf.is_alive(), timeout=20)   # der Thread meldet noch ins Protokoll
    assert len(abgefangen) == 1
    neu = [p for p in alt.parent.glob("anonym_*.pdf") if p != alt]
    assert len(neu) == 1                                            # die neue Ausgabe ist fertig geworden
    funktion, args = abgefangen[0]
    app.root.after(0, funktion, *args)                              # vom Arbeits-Thread vor seinem Ende eingereiht
    app._beenden_warten()                                           # das Fenster sieht nach: der Thread ist zu Ende
    assert bis_geschlossen(app, timeout=10)
    assert not alt.exists(), sorted(p.name for p in alt.parent.iterdir())
    assert neu[0].exists()


# ----------------------------------------------------------------------
# Runde 2, Befund 3: Hilfsdateien eines anderen Rechners (gemeinsame Freigabe) nur löschen, wenn sicher verwaist
# ----------------------------------------------------------------------
def test_hilfsdatei_eines_anderen_rechners_gilt_nicht_als_verwaist(tmp_path):
    """Befund: Als verwaist galt eine Zwischendatei, deren PID auf DIESEM Rechner nicht lebt – die PID eines anderen
    Rechners ist hier aber praktisch immer „tot“. In einem gemeinsam genutzten Ordner (Netzwerkfreigabe) löschten so
    Programmstart, Hinzufügen und Schwärzen die Hilfsdatei eines Kollegen mitten in seinem Lauf (seine Datei endete
    ohne Ausgabe mit Fehler). Jetzt trägt jede Hilfsdatei eine Kennung des Rechners (kurzer Hash des Rechnernamens).
    Die eines anderen Rechners – und eine ohne Kennung aus einer älteren Programmversion, deren Rechner unbekannt ist
    – gilt erst nach FREMDE_ZWISCHENDATEI_MAX_ALTER (24 Stunden) als verwaist; die eines abgestürzten Prozesses auf
    diesem Rechner sofort (wie bisher)."""
    ordner = tmp_path / "Freigabe" / "Upload"
    ordner.mkdir(parents=True)
    kollege = ordner / fremder_name(TOTE_PID, "140234_ausgabe.tmp")     # Lauf eines Kollegen, läuft noch
    alte_form = ordner / f".anonym_tmp_{TOTE_PID}_77_ausgabe.tmp"        # ältere Version, Rechner unbekannt
    alte_pdf = ordner / f".anonym_tmp_{TOTE_PID}_78_a.pdf"
    for p in (kollege, alte_form, alte_pdf):
        p.write_bytes(b"%PDF-1.4")
    assert dateien.zwischendateien_aufraeumen(ordner) == []
    assert kollege.exists() and alte_form.exists() and alte_pdf.exists()
    assert dateien.rechner_kennung() != FREMDER_RECHNER and len(dateien.rechner_kennung()) == 8
    assert dateien.FREMDE_ZWISCHENDATEI_MAX_ALTER == 24 * 3600
    # 23 Stunden alt: bleibt; älter als 24 Stunden: sicher verwaist
    _altern(kollege, 23)
    assert dateien.zwischendateien_aufraeumen(ordner) == [] and kollege.exists()
    for p in (kollege, alte_form, alte_pdf):
        _altern(p, 25)
    assert sorted(dateien.zwischendateien_aufraeumen(ordner)) == sorted([kollege, alte_form, alte_pdf])
    # dieser Rechner: Prozess abgestürzt -> sofort verwaist; Prozess lebt -> bleibt; dieser Prozess -> bleibt
    tot = ordner / eigener_name(TOTE_PID, "5_ausgabe.tmp")
    lebt = ordner / eigener_name(os.getppid(), "6_ausgabe.tmp")
    selbst = ordner / eigener_name(os.getpid(), "7_ausgabe.tmp")
    for p in (tot, lebt, selbst):
        p.write_bytes(b"%PDF-1.4")
    assert dateien.zwischendateien_aufraeumen(ordner) == [tot]
    assert lebt.exists() and selbst.exists()
    assert [dateien.zwischendatei_herkunft(p) for p in (selbst, lebt, kollege, alte_form)] == [
        "prozess", "rechner", "fremd", "unbekannt"]
    # beim Beenden löscht das Programm nur die eigenen – nie die eines anderen Rechners mit zufällig gleicher PID
    gleiche_pid = ordner / fremder_name(os.getpid(), "8_ausgabe.tmp")
    gleiche_pid.write_bytes(b"%PDF-1.4")
    assert dateien.eigene_zwischendateien_loeschen(ordner) == []
    assert not selbst.exists() and gleiche_pid.exists() and lebt.exists()


def test_hilfsdateien_der_schwaerzung_tragen_die_rechnerkennung(tmp_path, monkeypatch):
    """Befund 3: Die Engine legt ihre Hilfsdateien als .anonym_tmp_<PID>_r<Rechner>_<Lauf>_<Kennung>.tmp an – mit
    Rechnerkennung; ältere Namensformen (ohne Kennung, auch „….pdf“) erkennt das Programm weiter als Zwischendateien."""
    import re
    angelegt: list = []
    echt = schwaerzung._Lauf.tmp_pfad

    def tmp_pfad(lauf, kennung, ordner=None):
        p = echt(lauf, kennung, ordner) if ordner is not None else echt(lauf, kennung)
        angelegt.append(p)
        return p
    monkeypatch.setattr(schwaerzung._Lauf, "tmp_pfad", tmp_pfad)
    pdf = pdf_schreiben(tmp_path / "Kunde" / "Police.pdf")
    funde = [{"kategorie": "namen", "anzeige": "Name", "text": "Max Mustermann", "ersatz": "[PERSON A]", "seiten": [],
              "anzahl": 1, "kontext": ""}]
    e = schwaerzung.schwaerze_pdf(pdf, funde, ocr=PerfekteOcr({}))
    assert e["fehler"] is None and e["ausgabe"] is not None, e
    assert angelegt
    for p in angelegt:
        assert re.fullmatch(rf"\.anonym_tmp_{os.getpid()}_r[0-9a-f]{{8}}_\d+_[a-z]+\.tmp", p.name), p.name
        assert p.name.startswith(dateien.zwischendatei_praefix()) and dateien.zwischendatei_herkunft(p) == "prozess"
    for alt in (".anonym_tmp_123_456_a.pdf", ".anonym_tmp_123_ausgabe.pdf", ".ANONYM_TMP_123_456_b.tmp"):
        assert dateien.ist_zwischendatei(Path(alt)) and dateien.zwischendatei_herkunft(Path(alt)) == "unbekannt"


@gui_test
def test_hinzufuegen_laesst_hilfsdatei_eines_anderen_rechners_liegen(app, umgebung):
    """Befund 3: Das Hinzufügen eines Ordners auf einer gemeinsamen Freigabe löschte die Hilfsdatei eines Kollegen, der
    gerade dorthin schwärzt. Jetzt bleibt sie liegen (nie eine Eingabe, im Protokoll erwähnt); erst nach 24 Stunden
    gilt sie als verwaist."""
    kunde = umgebung["tmp"] / "Freigabe" / "Kunde"
    pdf = pdf_schreiben(kunde / "Police.pdf")
    ordner = kunde / dateien.AUSGABE_ORDNER
    ordner.mkdir()
    kollege = ordner / fremder_name(TOTE_PID, "5_ausgabe.tmp")
    kollege.write_bytes(b"%PDF-1.4")
    app._pdfs_hinzufuegen([str(kunde)])
    assert app.dateien == [pdf]
    assert kollege.exists()
    protokoll = app.protokoll_text()
    assert "gelöscht" not in protokoll, protokoll
    assert ("ℹ 1 Zwischendatei(en) einer Schwärzung auf einem anderen Rechner oder aus einer älteren Programmversion "
            "(.anonym_tmp_…) ignoriert") in protokoll, protokoll


@gui_test
def test_start_loescht_im_gemeinsamen_zielordner_keine_hilfsdatei_eines_kollegen(umgebung, dialoge, monkeypatch):
    """Befund 3: Der Programmstart löschte im gespeicherten gemeinsamen Zielordner (Netzwerkfreigabe) die Hilfsdatei
    eines Kollegen mitten in seinem Lauf und meldete fälschlich „Beim letzten Programmende blieb eine Schwärzung
    unfertig (Absturz?)“. Jetzt bleibt sie liegen (anderer Rechner, jünger als 24 Stunden). Eine ältere eines anderen
    Rechners wird gelöscht, aber nicht als eigener Absturz gemeldet."""
    monkeypatch.setattr(gui, "DND_VERFUEGBAR", False)
    monkeypatch.setattr(gui, "ERSTSTART_NACH_MS", 60_000)
    monkeypatch.setattr(gui, "VORLADEN_NACH_MS", 60_000)
    upload = umgebung["tmp"] / "Freigabe" / "Upload"
    upload.mkdir(parents=True)
    kollege = upload / fremder_name(TOTE_PID, "11_ausgabe.tmp")         # Kollege schwärzt gerade dorthin
    liegen_geblieben = upload / fremder_name(TOTE_PID + 4, "12_ausgabe.tmp")
    for p in (kollege, liegen_geblieben):
        p.write_bytes(b"%PDF-1.4")
    _altern(liegen_geblieben, 30)
    dateien.einstellungen_speichern({"zielordner": str(upload), "zielordner_aktiv": True, "hinweis_gelesen": True})
    app = gui.main(ereignisschleife=False)
    try:
        app.root.tk.willdispatch()
        assert pumpe(app.root, lambda: not liegen_geblieben.exists(), timeout=10)
        for faden in [f for f in threading.enumerate() if f.name == "Reste-beim-Start"]:
            faden.join(10)
        pumpe(app.root, timeout=0.3)
        assert kollege.exists()
        protokoll = app.protokoll_text()
        assert "Beim letzten Programmende" not in protokoll, protokoll
        assert (f"⚠ 1 unfertige Zwischendatei(en) einer abgebrochenen Schwärzung (.anonym_tmp_…) gelöscht – in "
                f"{upload}.") in protokoll, protokoll
    finally:
        app.schliessen()
