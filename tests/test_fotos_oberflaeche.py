"""Oberfläche und Vorschau mit Bildfunden (Lichtbild): Zeile in der Fundliste, Rahmen in der Vorschau, Abwählen per
Klick, und die Ausgabe braucht dann die Freigabe – auch wenn „Freigabe vor Weitergabe“ aus ist. Echte Engine (Analyse
und Schwärzung), OCR als Attrappe; unter Xvfb. Helfer und Fixtures stammen aus test_gui.py."""

import os
import sys
from pathlib import Path

import numpy as np
import pytest

import pymupdf as fitz

import foto_vorlagen as fv
from anonymisierer import analyse, fotos, gui, schwaerzung

from test_gui import app, dialoge, root, starte_lauf, umgebung  # noqa: F401,F811
from test_vorschau_fenster import klicke, mitte, oeffne

pytestmark = [pytest.mark.skipif(not os.environ.get("DISPLAY") and sys.platform != "win32",
                                 reason="kein Display (DISPLAY nicht gesetzt)"),
              pytest.mark.skipif(not fotos.verfuegbar(), reason="numpy fehlt")]
MM = fv.MM


class Attrappe:
    hinweise: list = []

    def woerter(self, pdf_pfad, seite_nr0, dpi=300, clip=None, **_):
        return [], None

    def ergebnis(self, pdf_pfad, seite_nr0, dpi=300, clip=None, **_):
        return {"woerter": [], "fehler": None}

    def abbrechen(self):
        pass

    def schliessen(self):
        pass


def brief_mit_ausweiskopie(pfad) -> fitz.Rect:
    """Brief (Textebene) mit eingebetteter Kopie der Ausweis-Vorderseite; liefert das Lichtbild-Rechteck."""
    rng = np.random.default_rng(61)
    doc = fitz.open()
    s = fv.textseite(doc, ["Sehr geehrte Damen und Herren,", "",
                           "anbei die Kopie meines Personalausweises.", "",
                           "Rückfragen bitte an erika.musterfrau@example.org", "", "Mit freundlichen Grüßen"])
    karte, licht = fv.karte_rendern(rng, "personalausweis", "vorn", dpi=150)
    r = fitz.Rect(300, 430, 300 + 85.6 * MM, 430 + 54 * MM)
    s.insert_image(r, stream=fv.jpeg(karte, 80), keep_proportion=False)
    f = r.width / karte.shape[1]
    doc.save(pfad)
    doc.close()
    return fitz.Rect(r.x0 + licht[0] * f, r.y0 + licht[1] * f, r.x0 + licht[2] * f, r.y0 + licht[3] * f)


def test_lichtbild_in_fundliste_vorschau_und_freigabe(app, umgebung, monkeypatch, dialoge):
    pdf = Path(umgebung["tmp"]) / "Kunde" / "Brief_Ausweis.pdf"
    pdf.parent.mkdir(parents=True)
    foto = brief_mit_ausweiskopie(pdf)

    def analyse_attrappe(*a, **k):
        k["ocr"] = Attrappe()
        return analyse.analysiere_pdf(*a, **k)

    def schwaerzung_attrappe(*a, **k):
        k["ocr"] = Attrappe()
        return schwaerzung.schwaerze_pdf(*a, **k)
    monkeypatch.setattr(gui, "analysiere_pdf", analyse_attrappe)
    monkeypatch.setattr(gui, "schwaerze_pdf", schwaerzung_attrappe)
    app.freigabe_var.set(False)
    app._pdfs_hinzufuegen([str(pdf)])
    starte_lauf(app, app.analysieren, timeout=120)
    funde = app.analyse_ergebnisse[pdf]["funde"]
    index = next(i for i, f in enumerate(funde) if f["kategorie"] == fotos.KAT_LICHTBILD)
    zeile = app.baum.item(f"{pdf}::{index}")
    assert zeile["values"][0].endswith("Lichtbild (Ausweis)") and zeile["values"][1] == "(Bereich im Bild)"
    assert app.fund_zustand(pdf, index) == "an"
    # Vorschau: Rahmen über dem Lichtbild, Klick wählt ihn ab (wie jeden Fund)
    fenster = oeffne(app, pdf)
    rahmen = [(r, si) for r, i, si in fenster.fund_stellen() if i == index]
    assert rahmen and any(abs(r & foto) >= 0.8 * abs(foto) for r, _ in rahmen), rahmen
    klicke(fenster, mitte(rahmen[0][0]))
    assert app.fund_zustand(pdf, index) == "aus"
    assert "Lichtbild (Ausweis)" in fenster.status_label.cget("text")
    # Schwärzen: das abgewählte Lichtbild bleibt stehen -> Ausgabe braucht die Freigabe, obwohl sie aus ist
    dialoge.antwort = False
    starte_lauf(app, app.schwaerzen, timeout=180)
    ausgabe = app.ausgaben[pdf]
    assert ausgabe["status"] == "pruefen" and "_PRUEFEN" in ausgabe["pfad"].name
    assert "Lichtbild" in ausgabe["grund"]
    assert "Seite 1: Lichtbild nicht abgedeckt" in ausgabe["ergebnis"]["pruefen_gruende"]
    with fitz.open(ausgabe["pfad"]) as doc:
        assert "erika.musterfrau@example.org" not in doc[0].get_text()


def test_abgewaehltes_lichtbild_ohne_einzelstellen_bleibt_abgewaehlt(app, umgebung, monkeypatch):
    """Kann die Engine keine Einzelstellen (kein Seitenmodell), gilt das Häkchen der Zeile: ein dort abgewähltes
    Lichtbild geht mit allen Bereichen abgewählt in den Auftrag – es wird nicht abgedeckt, verlangt aber die Freigabe."""
    pdf = Path(umgebung["tmp"]) / "Kunde" / "Brief_Ausweis.pdf"
    pdf.parent.mkdir(parents=True)
    brief_mit_ausweiskopie(pdf)

    def analyse_attrappe(*a, **k):
        k["ocr"] = Attrappe()
        return analyse.analysiere_pdf(*a, **k)
    monkeypatch.setattr(gui, "analysiere_pdf", analyse_attrappe)
    app._pdfs_hinzufuegen([str(pdf)])
    starte_lauf(app, app.analysieren, timeout=120)
    funde = app.analyse_ergebnisse[pdf]["funde"]
    index = next(i for i, f in enumerate(funde) if f["kategorie"] == fotos.KAT_LICHTBILD)
    monkeypatch.setattr(app, "einzelstellen_moeglich", lambda *a, **k: False)
    app.fund_setzen(pdf, index, False)
    assert app.fund_zustand(pdf, index) == "aus"
    auftrag = app._auftrag(pdf)
    (licht,) = [f for f in auftrag["funde"] if f["kategorie"] == fotos.KAT_LICHTBILD]
    assert licht["stellen"] and not any(st.get("an", True) for st in licht["stellen"])
    assert all(st.get("an", True) for st in funde[index]["stellen"])     # das Analyseergebnis bleibt unverändert
