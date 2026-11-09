"""Tests des Vorschau-Fensters (Vertrag Phase 2, Abschnitt 10) und der Attrappen (12.5) unter Xvfb.

Geprüft wird mit dem echten Tk: Seitenbild und Markierungen, Klick auf Wörter (Fund/Stelle an/aus, manuelle
Stelle), Rahmen (manueller Bereich), Kontextmenü, Blättern/Zoom, Gleichlauf mit der Hauptliste sowie der
Freigabe-Ablauf nach dem Schwärzen (Freigeben, Nachschwärzen, Verwerfen) – mit Engine-Attrappen beider
Vertragsstände und einmal mit der echten Engine. Helfer und Fixtures stammen aus test_gui.py.
"""

import os
import sys
from types import SimpleNamespace

import fitz
import pytest

from anonymisierer import dateien, gui, vorschau_fenster
from anonymisierer import gui_attrappen as attrappen

from test_gui import (FUND_MAIL, FUND_NAME, FUND_TEL, Verdacht, _prozesszustand, _screenshot,  # noqa: F401,F811
                      _screenshot_ordner, analysiere, app, dialoge, fake_analyse, fake_analyse_neu,
                      fake_schwaerzung, fake_schwaerzung_neu, pdf_schreiben, pumpe, root, starte_lauf, umgebung)

pytestmark = pytest.mark.skipif(not os.environ.get("DISPLAY") and sys.platform != "win32",
                                reason="kein Display (DISPLAY nicht gesetzt)")

ZWEIMAL = ("Sehr geehrter Herr Max Mustermann,\nwir bestätigen Max Mustermann den neuen Vertrag.\n"
           "Allianz Lebensversicherungs-AG, Tel. 0171 2345678\n")


# ----------------------------------------------------------------------
# Hilfen
# ----------------------------------------------------------------------
def oeffne(app, pdf, **kw):
    fenster = app.vorschau_oeffnen(pdf, **kw)
    assert fenster is not None, app.letzter_dialog
    pumpe(app.root, timeout=0.3)
    return fenster


def mitte(rect) -> fitz.Point:
    r = fitz.Rect(rect)
    return fitz.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)


def klicke(fenster, punkt):
    x, y = fenster.punkt_fuer(punkt.x, punkt.y)
    fenster.canvas.event_generate("<ButtonPress-1>", x=x, y=y)
    fenster.canvas.event_generate("<ButtonRelease-1>", x=x, y=y)
    fenster.app.root.update()


def ziehe(fenster, von, nach):
    x0, y0 = fenster.punkt_fuer(*von)
    x1, y1 = fenster.punkt_fuer(*nach)
    fenster.canvas.event_generate("<ButtonPress-1>", x=x0, y=y0)
    fenster.canvas.event_generate("<B1-Motion>", x=(x0 + x1) // 2, y=(y0 + y1) // 2)
    assert fenster.canvas.find_withtag("gummi"), "Gummiband-Rahmen wird beim Ziehen nicht gezeigt"
    fenster.canvas.event_generate("<ButtonRelease-1>", x=x1, y=y1)
    fenster.app.root.update()


def stelle_von(fenster, text, nummer=0):
    """(Rechteck, Fund-Index, Stellen-Index) der n-ten Markierung eines Fundtexts auf der aktuellen Seite."""
    funde = fenster.app.analyse_ergebnisse[fenster.pdf]["funde"]
    treffer = [e for e in fenster.fund_stellen() if funde[e[1]]["text"] == text]
    assert len(treffer) > nummer, f"keine Markierung für {text!r}: {fenster.fund_stellen()}"
    return treffer[nummer]


def wort(fenster, text):
    return next(w for w in fenster.daten()["woerter"] if w[1] == text)


def markierungen(fenster, tag):
    return [i for i in fenster.canvas.find_withtag(tag)]


def gestrichelt(fenster, item) -> bool:
    return bool(fenster.canvas.itemcget(item, "dash"))


# ----------------------------------------------------------------------
# Vor dem Schwärzen: geplante Schwärzung
# ----------------------------------------------------------------------
def test_vorschau_zeigt_geplante_schwaerzung_und_klick_schaltet_fund(app, umgebung, monkeypatch, tmp_path_factory):
    """Alte Engine (Funde ohne Stellen): rote Rahmen liegen über dem Text; ein Klick schaltet den Fund an
    allen Stellen um – die Hauptliste folgt."""
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "a.pdf")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({"a.pdf": [FUND_NAME, FUND_TEL, FUND_MAIL]}))
    analysiere(app, [pdf])
    fenster = oeffne(app, pdf)
    assert fenster.modus == "vorher" and fenster.seiten == 1
    assert fenster.fenster.title() == "Vorschau – a.pdf"
    assert len(fenster.fund_stellen()) == 3
    assert len(markierungen(fenster, "stelle")) == 3
    assert all(fenster.canvas.itemcget(i, "outline") == vorschau_fenster.FARBE_SCHWAERZEN
               for i in markierungen(fenster, "stelle"))

    # Koordinaten stimmen: unter dem Rahmen der Telefonnummer ist Text (dunkle Pixel), rechts daneben Papier
    rect, index, si = stelle_von(fenster, "0171 2345678")
    assert index == 1 and si is None
    dunkel = 0
    for x in range(int(rect.x0 * fenster.faktor) + 1, int(rect.x1 * fenster.faktor) - 1, 2):
        for y in range(int(rect.y0 * fenster.faktor) + 1, int(rect.y1 * fenster.faktor) - 1, 2):
            if sum(fenster._bild.get(x, y)) < 300:
                dunkel += 1
    assert dunkel >= 5, "unter dem Rahmen liegt kein Text – Koordinaten verschoben?"
    assert sum(fenster._bild.get(int(500 * fenster.faktor), int(rect.y0 * fenster.faktor) + 2)) > 700

    klicke(fenster, mitte(rect))
    assert app.fund_zustand(pdf, 1) == "aus" and app._zustand(f"{pdf}::1") == "aus"
    assert app._zustand(str(pdf)) == "teil"
    item = markierungen(fenster, "fund_1")[0]
    assert gestrichelt(fenster, item) and fenster.canvas.itemcget(item, "outline") == vorschau_fenster.FARBE_AUS
    klicke(fenster, mitte(rect))
    assert app.fund_zustand(pdf, 1) == "an" and not gestrichelt(fenster, markierungen(fenster, "fund_1")[0])
    _screenshot(app.root, None, _screenshot_ordner(tmp_path_factory) / "vorschau_vorher.png")


def test_einzelne_stelle_mit_seitenmodell(app, umgebung, monkeypatch):
    """Neue Engine (Seitenmodell + Stellen): ein Klick schaltet genau eine Stelle; der Fund wird „teil“, und
    schwaerze_pdf bekommt die Stellen mit ihren an-Kennzeichen und das Modell."""
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "a.pdf", text=ZWEIMAL)
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse_neu({"a.pdf": [FUND_NAME, FUND_TEL]}, modell=True,
                                                                mit_stellen=True))
    aufrufe = []
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung_neu(aufrufe))
    analysiere(app, [pdf])
    assert app.einzelstellen_moeglich(pdf)
    fenster = oeffne(app, pdf)
    erste, zweite = stelle_von(fenster, "Max Mustermann", 0), stelle_von(fenster, "Max Mustermann", 1)
    assert (erste[1], erste[2]) == (0, 0) and (zweite[1], zweite[2]) == (0, 1)
    klicke(fenster, mitte(zweite[0]))
    fund = app.analyse_ergebnisse[pdf]["funde"][0]
    assert [s["an"] for s in fund["stellen"]] == [True, False]
    assert app._zustand(f"{pdf}::0") == "teil" and app.baum.item(f"{pdf}::0", "text") == gui.HAKEN["teil"]
    # Hauptliste: Klick auf einen teilweise angehakten Fund hakt alle Stellen an
    app._umschalten(f"{pdf}::0")
    assert [s["an"] for s in fund["stellen"]] == [True, True]
    assert not any(gestrichelt(fenster, i) for i in markierungen(fenster, "fund_0"))
    klicke(fenster, mitte(zweite[0]))
    starte_lauf(app, app.schwaerzen)
    gesendet = aufrufe[0]["funde"][0]
    assert [s["an"] for s in gesendet["stellen"]] == [True, False]
    assert aufrufe[0]["modell"] is app.analyse_ergebnisse[pdf]["modell"]


def test_rahmen_ziehen_erzeugt_manuellen_bereich(app, umgebung, monkeypatch):
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "a.pdf")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse_neu({"a.pdf": [FUND_TEL]}))
    aufrufe = []
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung_neu(aufrufe))
    analysiere(app, [pdf])
    fenster = oeffne(app, pdf)
    ziehe(fenster, (300, 300), (420, 360))
    eintraege = list(app.manuell[pdf].items())
    assert len(eintraege) == 1
    mid, eintrag = eintraege[0]
    r = eintrag["rechtecke"][0]
    assert eintrag["art"] == "bereich" and eintrag["seite"] == 0
    assert abs(r.x0 - 300) < 1.5 and abs(r.y0 - 300) < 1.5 and abs(r.x1 - 420) < 1.5 and abs(r.y1 - 360) < 1.5
    zeile = f"{pdf}::m{mid}"
    assert app.baum.exists(zeile) and app.baum.set(zeile, "kategorie") == gui.ANZEIGE_MANUELL
    assert app.baum.set(zeile, "ersatz") == "[GESCHWÄRZT]"
    assert [fenster.canvas.itemcget(i, "outline") for i in markierungen(fenster, "manuell")] == \
        [vorschau_fenster.FARBE_MANUELL]
    # Linksklick in den Bereich entfernt ihn nicht (Schutz vor versehentlichem Aufheben)
    klicke(fenster, fitz.Point(360, 330))
    assert mid in app.manuell[pdf] and "Bereich entfernen" in fenster.status_label.cget("text")
    menue = dict(fenster.kontextmenue_eintraege(fitz.Point(360, 330)))
    assert "Bereich entfernen" in menue

    starte_lauf(app, app.schwaerzen)
    assert set(aufrufe[0]["manuelle_bereiche"]) == {0}
    assert fitz.Rect(aufrufe[0]["manuelle_bereiche"][0][0]) == fitz.Rect(r)
    assert aufrufe[0]["manuelle_stellen"] is None
    menue["Bereich entfernen"]()
    assert app.manuell[pdf] == {} and not app.baum.exists(zeile)


def test_wortklick_erzeugt_manuelle_stelle_mit_engine_vorschau(app, umgebung, monkeypatch):
    """Mit Seitenmodell und vorschau.vorschau_daten der Engine wird ein nicht erkanntes Wort zur manuellen
    Stelle (Offsets im Seitentext); ein zweiter Klick nimmt sie zurück."""
    monkeypatch.setattr(vorschau_fenster, "_engine_vorschau",
                        SimpleNamespace(seite_bild=attrappen.seite_bild, vorschau_daten=attrappen.vorschau_daten))
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "a.pdf")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse_neu({"a.pdf": [FUND_TEL]}, modell=True,
                                                                mit_stellen=True))
    aufrufe = []
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung_neu(aufrufe))
    analysiere(app, [pdf])
    fenster = oeffne(app, pdf)
    assert vorschau_fenster.vorher_quelle_engine(app, pdf)
    allianz = wort(fenster, "Allianz")
    klicke(fenster, mitte(allianz[0]))
    (mid, eintrag), = app.manuell[pdf].items()
    assert eintrag["art"] == "stelle" and (eintrag["start"], eintrag["ende"]) == (allianz[2], allianz[3])
    assert app.baum.set(f"{pdf}::m{mid}", "text") == "Allianz"
    starte_lauf(app, app.schwaerzen)
    assert aufrufe[-1]["manuelle_stellen"] == {0: [(allianz[2], allianz[3], "[GESCHWÄRZT]")]}
    # nach dem Schwärzen zeigt das Fenster die Ausgabe; zurück zur geplanten Schwärzung
    assert fenster.modus == "nachher"
    fenster.geplant_knopf.invoke()
    assert fenster.modus == "vorher"
    # zweiter Klick: Stelle aus (bleibt sichtbar in der Liste, wird nicht übergeben)
    klicke(fenster, mitte(allianz[0]))
    assert app.manuell[pdf][mid]["an"] is False and app._zustand(f"{pdf}::m{mid}") == "aus"
    starte_lauf(app, app.schwaerzen)
    assert aufrufe[-1]["manuelle_stellen"] is None


def test_wortklick_alte_engine_schwaerzt_ueberall_im_dokument(app, umgebung, monkeypatch):
    """Ohne manuelle Stellen/Bereiche in der Engine: ein Klick auf ein Wort schwärzt es überall im Dokument
    (IMMER-Begriff für diesen Lauf) – nie still nichts; Rahmen werden ehrlich abgelehnt."""
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "a.pdf")
    analyse_aufrufe, schwaerz_aufrufe = [], []
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({"a.pdf": [FUND_TEL]}, aufrufe=analyse_aufrufe))
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung(schwaerz_aufrufe))
    analysiere(app, [pdf])
    fenster = oeffne(app, pdf)
    klicke(fenster, mitte(wort(fenster, "Allianz")[0]))
    funde = app.analyse_ergebnisse[pdf]["funde"]
    assert funde[-1]["text"] == "Allianz" and funde[-1]["anzeige"] == gui.ANZEIGE_BEGRIFF_VORSCHAU
    assert "stellen" not in funde[-1]                     # die Schwärzung sucht alle Vorkommen selbst
    assert app.lauf_immer[pdf] == ["Allianz"]
    assert app.baum.set(f"{pdf}::1", "text") == "Allianz"
    assert stelle_von(fenster, "Allianz")[1] == 1         # sofort rot markiert
    assert "überall in diesem Dokument" in fenster.status_label.cget("text")
    ziehe(fenster, (300, 300), (420, 360))
    assert not app.manuell.get(pdf) and "noch nicht" in fenster.status_label.cget("text")
    starte_lauf(app, app.schwaerzen)
    assert schwaerz_aufrufe[0]["texte"] == ["0171 2345678", "Allianz"]
    starte_lauf(app, app.analysieren)                     # erneute Analyse: Begriff geht als IMMER mit
    assert analyse_aufrufe[-1]["immer"] == ["Allianz"]


def test_kontextmenue_ueberall_und_nicht_schwaerzen(app, umgebung, monkeypatch):
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "a.pdf")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({"a.pdf": [FUND_NAME, FUND_TEL]}))
    analysiere(app, [pdf])
    fenster = oeffne(app, pdf)
    rect, index, _ = stelle_von(fenster, "0171 2345678")
    menue = dict(fenster.kontextmenue_eintraege(mitte(rect)))
    assert "„0171 2345678“ nirgends schwärzen (ganzer Fund)" in menue
    menue["„0171 2345678“ nirgends schwärzen (ganzer Fund)"]()
    assert app.fund_zustand(pdf, index) == "aus"
    menue = dict(fenster.kontextmenue_eintraege(mitte(rect)))
    menue["„0171 2345678“ überall schwärzen (ganzer Fund)"]()
    assert app.fund_zustand(pdf, index) == "an"
    leben = wort(fenster, "Lebensversicherungs-AG")
    menue = dict(fenster.kontextmenue_eintraege(mitte(leben[0])))
    assert set(menue) == {"Dieses Wort schwärzen", "„Lebensversicherungs-AG“ überall in diesem Dokument schwärzen"}
    menue["„Lebensversicherungs-AG“ überall in diesem Dokument schwärzen"]()
    assert app.analyse_ergebnisse[pdf]["funde"][-1]["text"] == "Lebensversicherungs-AG"
    # doppelt gewählt: kein zweiter Fund
    dict(fenster.kontextmenue_eintraege(mitte(leben[0])))[
        "„Lebensversicherungs-AG“ überall in diesem Dokument schwärzen"]()
    assert sum(1 for f in app.analyse_ergebnisse[pdf]["funde"] if f["text"] == "Lebensversicherungs-AG") == 1


def test_seiten_blaettern_und_zoom(app, umgebung, monkeypatch):
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "lang.pdf", seiten=3)
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({"lang.pdf": [FUND_TEL]}, seiten=3))
    analysiere(app, [pdf])
    fenster = oeffne(app, pdf)
    assert fenster.seiten == 3 and fenster.seite == 0
    assert fenster.seiten_label.cget("text") == "Seite 1 / 3"
    assert str(fenster.zurueck_knopf.cget("state")) == "disabled"
    # Zoom auf Fensterbreite
    soll = fenster.canvas.winfo_width() - 2 * vorschau_fenster.RAND - 4
    # Das Bild füllt die Breite; unter Windows nimmt die senkrechte Bildlaufleiste nach dem ersten
    # Zeichnen bis zu ~20 px weg, deshalb darf es etwas schmaler sein, aber nie breiter.
    assert -3 <= soll - fenster._bild.width() <= 25
    fenster.fenster.event_generate("<Next>")
    app.root.update()
    assert fenster.seite == 1 and fenster.seiten_label.cget("text") == "Seite 2 / 3"
    assert len(markierungen(fenster, "stelle")) == 1        # jede Seite hat ihre Markierungen
    fenster.fenster.event_generate("<End>")
    fenster.fenster.event_generate("<Next>")
    app.root.update()
    assert fenster.seite == 2 and str(fenster.vor_knopf.cget("state")) == "disabled"
    fenster.fenster.event_generate("<Prior>")
    app.root.update()
    assert fenster.seite == 1
    faktor = fenster.faktor
    fenster.zoomen(1)
    assert fenster.faktor == pytest.approx(faktor * 1.25, rel=0.01)
    fenster.zoom_breite()
    assert fenster.faktor == pytest.approx(faktor, rel=0.01)


def test_hauptliste_und_vorschau_bleiben_gleich(app, umgebung, monkeypatch):
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "a.pdf")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({"a.pdf": [FUND_NAME, FUND_TEL, FUND_MAIL]}))
    analysiere(app, [pdf])
    fenster = oeffne(app, pdf)
    app._umschalten(f"{pdf}::2")
    assert gestrichelt(fenster, markierungen(fenster, "fund_2")[0])
    app.alle_setzen("aus")
    assert all(gestrichelt(fenster, i) for i in markierungen(fenster, "stelle"))
    assert str(app.start_knopf.cget("state")) == "disabled"
    klicke(fenster, mitte(stelle_von(fenster, "Max Mustermann")[0]))
    assert app._zustand(f"{pdf}::0") == "an" and str(app.start_knopf.cget("state")) == "normal"
    # Doppelklick auf eine Fundzeile öffnet die Vorschau mit hervorgehobenem Fund
    app._vorschau_fuer_zeile(f"{pdf}::1")
    assert app.vorschauen[pdf] is fenster and fenster.markiert_fund == 1
    assert int(float(fenster.canvas.itemcget(markierungen(fenster, "fund_1")[0], "width"))) == 4
    # neue Analyse schließt die Vorschau (Daten werden neu aufgebaut)
    starte_lauf(app, app.analysieren)
    assert pdf not in app.vorschauen and not fenster.existiert()


# ----------------------------------------------------------------------
# Nach dem Schwärzen: Freigeben, Nachschwärzen, Verwerfen
# ----------------------------------------------------------------------
def _verdacht_fuer(pdf, text):
    modell = attrappen.seiten_modell(pdf, 0)
    (start, ende, rects), = attrappen.stellen_suchen(modell["woerter"], text)
    return Verdacht(0, start, ende, text, "Vorname aus der Wissensbasis", rects)


def test_freigabe_ablauf_nach_dem_schwaerzen(app, umgebung, monkeypatch, dialoge, tmp_path_factory):
    tmp = umgebung["tmp"]
    a = pdf_schreiben(tmp / "a.pdf")
    b = pdf_schreiben(tmp / "b.pdf")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse_neu({"a.pdf": [FUND_TEL], "b.pdf": [FUND_MAIL]}))
    aufrufe = []
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung_neu(
        aufrufe, verdacht_fuer={"a.pdf": [_verdacht_fuer(a, "Max Mustermann")]}))
    analysiere(app, [a, b])
    dialoge.antwort = True                                   # „Vorschau jetzt öffnen?“ -> ja
    starte_lauf(app, app.schwaerzen)
    art, titel, text = dialoge.liste[-1]
    assert art == "askyesno" and gui.PRUEFEN_ERKLAERUNG in text and "1 Verdachtsstelle(n)" in text
    assert app.ausgaben[a]["status"] == "pruefen" and app.ausgaben[b]["status"] == "pruefen"
    fenster = app.vorschauen[a]
    pumpe(app.root, timeout=0.3)
    assert fenster.modus == "nachher" and fenster.fenster.title().startswith("Prüfen – anonym_01_PRUEFEN.pdf")
    assert fenster.verdacht_liste.size() == 1 and fenster.verdacht_liste.curselection() == (0,)
    assert [fenster.canvas.itemcget(i, "outline") for i in markierungen(fenster, "verdacht")] == \
        [vorschau_fenster.FARBE_VERDACHT]
    assert str(fenster.freigeben_knopf.cget("state")) == "normal"
    _screenshot(app.root, None, _screenshot_ordner(tmp_path_factory) / "vorschau_nachher.png")

    fenster.freigeben()
    assert "1 Verdachtsstelle(n)" in dialoge.liste[-1][2]   # Rückfrage nennt offene Verdachtsstellen
    ausgabe_a = tmp / "anonymisiert" / "anonym_01.pdf"
    assert ausgabe_a.exists() and not (tmp / "anonymisiert" / "anonym_01_PRUEFEN.pdf").exists()
    assert app.ausgaben[a]["status"] == "fertig" and app.ausgaben[a]["pfad"] == ausgabe_a
    assert app.baum.set(str(a), "text") == "✔ fertig: anonym_01.pdf"
    # weiter mit der nächsten zu prüfenden Datei im selben Fenster
    assert fenster.pdf == b and app.vorschauen[b] is fenster and a not in app.vorschauen
    assert fenster.verdacht_liste.size() == 1 and "Keine Verdachtsstellen" in fenster.verdacht_liste.get(0)
    fenster.freigeben()
    assert (tmp / "anonymisiert" / "anonym_02.pdf").exists()
    assert "alle Ausgaben dieses Laufs sind geprüft" in fenster.status_label.cget("text")
    assert str(fenster.freigeben_knopf.cget("state")) == "disabled"
    zuordnung = (tmp / "anonymisiert" / "_zuordnung.txt").read_text(encoding="utf-8")
    assert "anonym_01.pdf  <-  a.pdf" in zuordnung and "anonym_02.pdf  <-  b.pdf" in zuordnung
    assert "PRUEFEN" not in zuordnung


def test_nachschwaerzen_ersetzt_die_ausgabe(app, umgebung, monkeypatch, dialoge):
    tmp = umgebung["tmp"]
    a = pdf_schreiben(tmp / "a.pdf")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse_neu({"a.pdf": [FUND_TEL]}))
    aufrufe = []
    verdacht = {"a.pdf": [_verdacht_fuer(a, "Max Mustermann")]}
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung_neu(aufrufe, verdacht_fuer=verdacht))
    analysiere(app, [a])
    starte_lauf(app, app.schwaerzen)
    alt = app.ausgaben[a]["pfad"]
    assert alt.name == "anonym_01_PRUEFEN.pdf"
    fenster = oeffne(app, a, modus="nachher")
    verdacht.clear()                                          # der zweite Lauf findet nichts mehr
    vorher = app.laeufe_beendet
    fenster.nachschwaerzen()
    assert app.laeuft and fenster.gesperrt
    assert pumpe(app.root, lambda: app.laeufe_beendet > vorher, timeout=30)
    pumpe(app.root, timeout=0.2)
    bereiche = aufrufe[-1]["manuelle_bereiche"]
    assert set(bereiche) == {0} and len(bereiche[0]) == 1
    assert fitz.Rect(bereiche[0][0]).contains(fitz.Rect(_verdacht_fuer(a, "Max Mustermann").rechtecke[0]))
    neu = app.ausgaben[a]["pfad"]
    assert neu.name == "anonym_02_PRUEFEN.pdf" and neu.exists() and not alt.exists()
    zuordnung = (tmp / "anonymisiert" / "_zuordnung.txt").read_text(encoding="utf-8")
    assert "anonym_01_PRUEFEN.pdf" not in zuordnung and "anonym_02_PRUEFEN.pdf  <-  a.pdf" in zuordnung
    assert fenster.modus == "nachher" and "anonym_02_PRUEFEN.pdf" in fenster.fenster.title()
    assert any(app.baum.set(k, "kategorie") == gui.ANZEIGE_NACHSCHWAERZEN for k in app.baum.get_children(str(a)))
    assert "nachgeschwärzt" in app.protokoll_text()


def test_verwerfen_loescht_die_ausgabe(app, umgebung, monkeypatch, dialoge):
    tmp = umgebung["tmp"]
    a = pdf_schreiben(tmp / "a.pdf")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse_neu({"a.pdf": [FUND_TEL]}))
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung_neu([]))
    analysiere(app, [a])
    starte_lauf(app, app.schwaerzen)
    alt = app.ausgaben[a]["pfad"]
    fenster = oeffne(app, a, modus="nachher")
    dialoge.antwort = False
    fenster.verwerfen()
    assert alt.exists()                                       # abgelehnt: nichts passiert
    dialoge.antwort = True
    fenster.verwerfen()
    assert not alt.exists() and app.ausgaben[a]["status"] == "verworfen"
    assert alt.name not in (tmp / "anonymisiert" / "_zuordnung.txt").read_text(encoding="utf-8")
    assert app.baum.set(str(a), "text") == "verworfen"
    assert fenster.modus == "vorher"


def test_freigabe_mit_echter_engine(app, umgebung, dialoge):
    """Echte (heutige) Engine: Analyse, Klick in der Vorschau, Schwärzen mit Freigabe-Pflicht, Freigeben."""
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "echt" / "Vertrag.pdf")
    app.kategorie_vars["namen"].set(False)
    analysiere(app, [pdf])
    fenster = oeffne(app, pdf)
    funde = app.analyse_ergebnisse[pdf]["funde"]
    tel = next(i for i, f in enumerate(funde) if f["kategorie"] == "telefon")
    rect = next(r for r, i, _ in fenster.fund_stellen() if i == tel)
    klicke(fenster, mitte(rect))
    assert app.fund_zustand(pdf, tel) == "aus"
    dialoge.antwort = True
    starte_lauf(app, app.schwaerzen, timeout=120)
    ausgabe = tmp / "echt" / "anonymisiert" / "anonym_01_PRUEFEN.pdf"
    assert ausgabe.exists() and fenster.modus == "nachher"
    with fitz.open(ausgabe) as doc:
        text = doc[0].get_text()
    assert "0171 2345678" in text and "DE89 3704" not in text   # abgewählt bleibt, angehakt ist weg
    fenster.freigeben()
    assert (tmp / "echt" / "anonymisiert" / "anonym_01.pdf").exists() and not ausgabe.exists()
    assert (tmp / "echt" / "anonymisiert" / "_zuordnung.txt").read_text(encoding="utf-8").startswith(
        "anonym_01.pdf  <-  Vertrag.pdf")


# ----------------------------------------------------------------------
# Attrappen (Vertrag 12.5)
# ----------------------------------------------------------------------
def test_attrappe_freigeben_verwerfen_markieren(tmp_path):
    ordner = tmp_path / "anonymisiert"
    ordner.mkdir()
    for name in ("anonym_01_PRUEFEN.pdf", "anonym_01.pdf", "anonym_03.pdf"):
        (ordner / name).write_bytes(b"%PDF " + name.encode())
    (ordner / "_zuordnung.txt").write_text("anonym_01_PRUEFEN.pdf  <-  A.pdf  (2026-01-01 10:00)\n"
                                           "anonym_03.pdf  <-  C.pdf  (2026-01-01 10:01)\n", encoding="utf-8")
    # anonym_01.pdf gibt es schon (z. B. von Hand angelegt): nächste freie Nummer, nichts überschreiben
    neu = attrappen.freigeben(ordner / "anonym_01_PRUEFEN.pdf")
    assert neu == ordner / "anonym_02.pdf" and neu.read_bytes() == b"%PDF anonym_01_PRUEFEN.pdf"
    assert (ordner / "anonym_01.pdf").read_bytes() == b"%PDF anonym_01.pdf"
    assert attrappen.freigeben(neu) == neu                    # ohne _PRUEFEN: unverändert
    markiert = attrappen.als_pruefen_markieren(ordner / "anonym_03.pdf")
    assert markiert == ordner / "anonym_03_PRUEFEN.pdf" and markiert.exists()
    zuordnung = (ordner / "_zuordnung.txt").read_text(encoding="utf-8")
    assert zuordnung == ("anonym_02.pdf  <-  A.pdf  (2026-01-01 10:00)\n"
                         "anonym_03_PRUEFEN.pdf  <-  C.pdf  (2026-01-01 10:01)\n")
    attrappen.verwerfen(markiert)
    assert not markiert.exists()
    assert (ordner / "_zuordnung.txt").read_text(encoding="utf-8") == "anonym_02.pdf  <-  A.pdf  (2026-01-01 10:00)\n"
    with pytest.raises(FileNotFoundError):
        attrappen.freigeben(ordner / "anonym_09_PRUEFEN.pdf")


def test_attrappe_vorschau_daten_und_wortsuche(tmp_path):
    pdf = pdf_schreiben(tmp_path / "a.pdf")
    modell = attrappen.seiten_modell(pdf, 0)
    assert modell["text"].startswith("Allianz Lebensversicherungs-AG\nSehr geehrter Herr Max Mustermann,")
    w = modell["woerter"][0]
    assert w[1] == "Allianz" and modell["text"][w[2]:w[3]] == "Allianz"
    # Satzzeichen am Wortrand und Groß-/Kleinschreibung egal, Ganzwort
    assert len(attrappen.stellen_suchen(modell["woerter"], "max mustermann")) == 1
    assert attrappen.stellen_suchen(modell["woerter"], "Muster") == []
    (start, ende, rects), = attrappen.stellen_suchen(modell["woerter"], "DE89 3704 0044 0532 0130 00")
    assert modell["text"][start:ende] == "DE89 3704 0044 0532 0130 00" and len(rects) == 1
    fund_stellen = {"id": "f1", "text": "Allianz", "stellen": [{"seite": 0, "start": 0, "ende": 7, "an": False}]}
    daten = attrappen.vorschau_daten({"datei": pdf, "funde": [fund_stellen, dict(FUND_TEL)]}, 0)
    assert {(e[1], e[2], e[3]) for e in daten["stellen"]} == {("f1", 0, False), ("#1", None, True)}
    assert daten["seitenrect"] == fitz.Rect(0, 0, 595, 842)
    png, faktor = attrappen.seite_bild(pdf, 0, 0.5)
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and faktor == 0.5


def test_attrappe_kundenliste_ohne_klartext(tmp_path):
    csv_datei = tmp_path / "k.csv"
    csv_datei.write_text("Vorname;Nachname;Kundennummer\nMax;Mustermann;4711\nErika;Musterfrau;\n;;\n",
                         encoding="utf-8-sig")
    liste = attrappen.Kundenliste.importieren(csv_datei)
    assert liste.anzahl_kunden == 2
    ziel = tmp_path / "konfig" / "kundenliste.dat"
    liste.speichern(ziel)
    assert "Mustermann" not in ziel.read_text(encoding="utf-8") and "4711" not in ziel.read_text(encoding="utf-8")
    assert attrappen.Kundenliste.laden(ziel).anzahl_kunden == 2
    assert attrappen.Kundenliste.laden(tmp_path / "fehlt.dat") is None
    unbekannt = tmp_path / "u.csv"
    unbekannt.write_text("A;B\n1;2\n", encoding="utf-8")
    with pytest.raises(attrappen.SpaltenNichtErkannt):
        attrappen.Kundenliste.importieren(unbekannt)
    assert attrappen.Kundenliste.importieren(unbekannt, {"kundennummer": 0}).anzahl_kunden == 2
    assert attrappen.Kundenliste.importieren(unbekannt, {"kundennummer": "A"}).anzahl_kunden == 1
    assert liste.treffer(None) == []


def test_attrappe_meldungs_codes_aus_texten():
    erg = {"fehler": "Abgebrochen", "warnungen": ["Kein Text lesbar — weder direkt noch per OCR.",
                                                  "Abgebrochen", "3 Fund(e) konnten im Dokument nicht lokalisiert "
                                                                 "werden"],
           "hinweise": ["Durch NIE-Liste freigegeben: Makler GmbH"], "reste": ["Max"]}
    codes = [m["code"] for m in attrappen.meldungen_aus_texten(erg)]
    assert codes == ["ABGEBROCHEN", "KEIN_TEXT", "NICHT_LOKALISIERT", "NIE_FREIGABE", "RESTE"]
    assert gui.meldungs_codes({"meldungen": [{"code": "XFA"}], "warnungen": ["Kein Text lesbar"]}) == {"XFA"}


def test_verdacht_wird_zu_manueller_markierung(app, umgebung, monkeypatch):
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "a.pdf")
    v = _verdacht_fuer(pdf, "Max Mustermann")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse_neu({"a.pdf": [FUND_TEL]}, modell=True))
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung_neu([]))
    analysiere(app, [pdf])
    # ohne Engine-Vorschau: Bereich (Geometrie), mit Engine-Vorschau: Stelle (Offsets im Seitenmodell)
    (bereich,) = vorschau_fenster.verdacht_zu_markierungen(app, pdf, v)
    assert bereich["art"] == "bereich" and bereich["rechtecke"][0].contains(fitz.Rect(v.rechtecke[0]))
    monkeypatch.setattr(vorschau_fenster, "_engine_vorschau",
                        SimpleNamespace(seite_bild=attrappen.seite_bild, vorschau_daten=attrappen.vorschau_daten))
    (stelle,) = vorschau_fenster.verdacht_zu_markierungen(app, pdf, v)
    assert stelle["art"] == "stelle" and (stelle["start"], stelle["ende"]) == (v.start, v.ende)
    assert stelle["text"] == "Max Mustermann,"


def test_kundenliste_pfad_liegt_bei_den_einstellungen(umgebung):
    assert dateien.kundenliste_pfad() == dateien.einstellungen_pfad().parent / "kundenliste.dat"


def test_attrappe_raet_keine_fremden_offsets(tmp_path):
    """Stammen die Stellen aus dem Seitenmodell der Engine (andere Offsets), zeigt die Attrappe den Fund über
    die Suche als Ganzes (stelle_index None) statt Rahmen auf falsche Wörter zu setzen."""
    pdf = pdf_schreiben(tmp_path / "a.pdf")
    fremd = {"id": "f1", "text": "Max Mustermann", "stellen": [{"seite": 0, "start": 3, "ende": 17, "an": True}]}
    daten = attrappen.vorschau_daten({"datei": pdf, "funde": [fremd]}, 0)
    assert [(e[1], e[2]) for e in daten["stellen"]] == [("f1", None)]
    text = attrappen.seiten_modell(pdf, 0)["text"]
    assert text[3:17] != "Max Mustermann"
    # Stellen nur auf einer anderen Seite: auf dieser Seite nichts
    anderswo = dict(fremd, stellen=[{"seite": 1, "start": 0, "ende": 5, "an": True}])
    assert attrappen.vorschau_daten({"datei": pdf, "funde": [anderswo]}, 0)["stellen"] == []


def test_attrappe_zeigt_funde_auf_scans_ueber_ocr_woerter(tmp_path):
    """Scan ohne Textebene: die Wörter kommen aus dem ocr_cache der Analyse."""
    pdf = tmp_path / "scan.pdf"
    doc = fitz.open()
    seite = doc.new_page()
    seite.draw_rect(fitz.Rect(40, 40, 300, 120), color=(0, 0, 0))      # kein Text
    doc.save(pdf)
    doc.close()
    ocr = {0: [(50.0, 50.0, 80.0, 60.0, "Herr"), (82.0, 50.0, 110.0, 60.0, "Max"),
               (112.0, 50.0, 170.0, 60.0, "Mustermann,"), (50.0, 70.0, 90.0, 80.0, "Tel.")]}
    daten = attrappen.vorschau_daten({"datei": pdf, "funde": [dict(FUND_NAME)], "ocr_cache": ocr}, 0)
    (rect, fund_id, si, an), = daten["stellen"]
    assert fund_id == "#0" and si is None and rect == fitz.Rect(82, 50, 170, 60)
    assert [w[1] for w in daten["woerter"]] == ["Herr", "Max", "Mustermann,", "Tel."]
    assert attrappen.vorschau_daten({"datei": pdf, "funde": [dict(FUND_NAME)]}, 0)["stellen"] == []


def test_wortsuche_ignoriert_reine_satzzeichen_woerter(tmp_path):
    pdf = pdf_schreiben(tmp_path / "a.pdf", text="Telefon: 02204 / 91 23 45 und Fax 02204-91 23 46\n")
    woerter = attrappen.seiten_modell(pdf, 0)["woerter"]
    assert "/" in [w[1] for w in woerter]
    (start, ende, rects), = attrappen.stellen_suchen(woerter, "02204 / 91 23 45")
    text = attrappen.seiten_modell(pdf, 0)["text"]
    assert text[start:ende] == "02204 / 91 23 45" and len(rects) == 1
    assert len(attrappen.stellen_suchen(woerter, "02204/91 23 45")) == 0     # anderes Wort: kein Treffer


def test_vorschau_nennt_funde_ohne_markierung(app, umgebung, monkeypatch):
    """Ein Fund, der nur als Teil eines längeren Worts vorkommt, bekommt keinen roten Rahmen – das Fenster sagt
    es, statt still zu schweigen."""
    tmp = umgebung["tmp"]
    pdf = pdf_schreiben(tmp / "a.pdf", text="Gläubiger-ID DE98ZZZ09999999999\nTel. 0171 2345678\n")
    eingebettet = dict(FUND_TEL, text="09999999999", kontext="DE98ZZZ»09999999999«")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse({"a.pdf": [FUND_TEL, eingebettet]}))
    analysiere(app, [pdf])
    fenster = oeffne(app, pdf)
    assert fenster.ohne_markierung() == ["09999999999"]
    assert fenster.warnzeile.winfo_manager() == "pack"
    assert "ohne Markierung: „09999999999“" in fenster.warnzeile.cget("text")
    assert fenster.ohne_markierung(0) == ["09999999999"]
    mehrseitig = {"text": "X", "stellen": [{"seite": 1, "start": 0, "ende": 1}, {"seite": 0, "start": 0, "ende": 1}]}
    app.analyse_ergebnisse[pdf]["funde"].append(dict(FUND_TEL, **mehrseitig))
    assert "X" in fenster.ohne_markierung(0)



def test_einstellung_aendern_laesst_zu_pruefende_ausgabe_sichtbar(app, umgebung, monkeypatch, dialoge):
    tmp = umgebung["tmp"]
    a = pdf_schreiben(tmp / "a.pdf")
    b = pdf_schreiben(tmp / "b.pdf")
    monkeypatch.setattr(gui, "analysiere_pdf", fake_analyse_neu({"a.pdf": [FUND_TEL], "b.pdf": [FUND_TEL]}))
    monkeypatch.setattr(gui, "schwaerze_pdf", fake_schwaerzung_neu([]))
    analysiere(app, [a, b])
    starte_lauf(app, lambda: app.schwaerzen(nur=[a]))
    fenster_a = oeffne(app, a, modus="nachher")
    fenster_b = oeffne(app, b)
    app.kategorie_vars["iban"].set(False)                    # Analyse veraltet
    assert app.analyse_veraltet
    assert fenster_a.existiert() and fenster_a.modus == "nachher"
    assert not fenster_b.existiert() and b not in app.vorschauen
    assert str(fenster_a.nachschwaerzen_knopf.cget("state")) == "disabled"   # ohne Analyse nicht möglich
    assert str(fenster_a.freigeben_knopf.cget("state")) == "normal"
