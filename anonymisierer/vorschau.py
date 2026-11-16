"""Vorschau-Engine (Vertrag Phase 2, Abschnitt 8): Seitenbilder und Markierungen für das Vorschau-Fenster.

Alle Koordinaten stammen aus demselben Seitenmodell wie Analyse und Schwärzung (seitenmodell.py) und
beziehen sich auf die vorbereitete Seite (seitenmodell.dokument_vorbereiten: bake, Drehung wie
ocr.drehung_entfernen – der sichtbare Ausschnitt einer gedrehten Seite mit CropBox bleibt exakt, Befund R-05) –
Seitenbild, Wörter und Fundstellen passen deshalb genau übereinander.

Jedes Seitenbild entsteht aus einer Kopie im Speicher: das Original bleibt unverändert und ohne offenen
Datei-Handle (unter Windows bleibt es umbenenn- und löschbar), und vor dem Rendern wird der Strukturbaum entfernt –
an einem Zyklus darin hängt MuPDF 1.28 beim Rendern über zehn Minuten (ocr.strukturbaum_entfernen).

    seite_bild(pdf_pfad_oder_doc, seite_nr0, zoom) -> (PNG-Bytes, Faktor pt -> px); eine Datei, die keine PDF ist
                     (Bild, Webseite … mit der Endung .pdf), ergibt ValueError mit Erklärung statt eines Absturzes
    vorschau_daten(ergebnis, seite_nr0) -> {"woerter", "stellen", "bilder", "seitenrect"}
    ausgabe_vorschau(ausgabe_pfad, verdacht, seite_nr0, zoom) -> {"bild", "faktor", "verdacht", "seitenrect"}
"""

from __future__ import annotations

import threading
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen kennen nur den Namen "fitz"
    import fitz

from . import ocr as _ocr
from . import seitenmodell as sm
from .analyse import keine_pdf_meldung as _keine_pdf_meldung
from .analyse import reparatur_erzwingen as _reparatur_erzwingen

_SPERRE = threading.Lock()
_VORBEREITET: dict = {}           # (Pfad, Größe, Zeitstempel) -> vorbereitetes Dokument (höchstens 2)


def _datei_schluessel(pfad: Path):
    st = pfad.stat()
    return (str(pfad.resolve()), st.st_size, st.st_mtime_ns)


def dokument_fuer_vorschau(pfad) -> "fitz.Document":
    """Kopie der Datei im Speicher, vorbereitet wie in Analyse und Schwärzung und ohne Strukturbaum.

    Reihenfolge wie in analysiere_pdf: Nicht-PDF prüfen (vor jedem Seitenzugriff, Gutachten R-01), Kennwort, jedes
    Objekt einmal laden (eine nötige Reparatur geschieht vor jeder Änderung, R-11), dokument_vorbereiten (bake,
    Drehung, Ebenen sichtbar). Ohne Zwischenspeicher (threadsicher); der Aufrufer schließt das Dokument. Auch die
    Vorschau der Attrappe (gui_attrappen) öffnet ihre Dokumente hiermit."""
    pfad = Path(pfad)
    doc = fitz.open(stream=pfad.read_bytes(), filetype="pdf")
    try:
        keine_pdf = _keine_pdf_meldung(doc, pfad)
        if keine_pdf:
            raise ValueError(keine_pdf)
        if doc.needs_pass:
            raise ValueError("Passwortgeschützt – keine Vorschau möglich.")
        _reparatur_erzwingen(doc)
        vorbereitet = sm.dokument_vorbereiten(doc).get("dokument") or doc
    except BaseException:
        doc.close()
        raise
    if vorbereitet is not doc:                 # Ebenen: neu geöffnete Fassung – die alte wird nicht mehr gebraucht
        doc.close()
    _ocr.strukturbaum_entfernen(vorbereitet)   # die Kopie wird nie gespeichert
    return vorbereitet


def _vorbereitetes_dokument(pfad: Path):
    """dokument_fuer_vorschau – zwischengespeichert, damit das Blättern nicht jedes Mal neu einbrennt."""
    schluessel = _datei_schluessel(pfad)
    with _SPERRE:
        doc = _VORBEREITET.get(schluessel)
        if doc is not None:
            return doc
        doc = dokument_fuer_vorschau(pfad)
        if len(_VORBEREITET) >= 2:
            for alt in list(_VORBEREITET)[:-1]:
                try:
                    _VORBEREITET.pop(alt).close()
                except Exception:
                    pass
        _VORBEREITET[schluessel] = doc
        return doc


def seite_bild(pdf_pfad_oder_doc, seite_nr0: int, zoom: float) -> tuple:
    """PNG der (vorbereiteten) Seite in `zoom` (1.0 = 72 dpi) und der Faktor pt -> px.

    Mit einem geöffneten Dokument wird es wie in der Analyse vorbereitet (dokument_vorbereiten ist bei einem schon
    vorbereiteten Dokument wirkungslos); sein Strukturbaum bleibt nur während des Renderns ausgeblendet."""
    zoom = max(0.05, float(zoom))
    matrix = fitz.Matrix(zoom, zoom)
    if isinstance(pdf_pfad_oder_doc, (str, Path)):
        doc = _vorbereitetes_dokument(Path(pdf_pfad_oder_doc))
        with _SPERRE:
            pix = doc[seite_nr0].get_pixmap(matrix=matrix, alpha=False)
    else:
        doc = sm.dokument_vorbereiten(pdf_pfad_oder_doc).get("dokument") or pdf_pfad_oder_doc
        with _ocr.strukturbaum_ausgeblendet(doc):
            pix = doc[seite_nr0].get_pixmap(matrix=matrix, alpha=False)
    return pix.tobytes("png"), zoom


def vorschau_daten(ergebnis: dict, seite_nr0: int) -> dict:
    """Markierungen einer Seite aus dem Analyse-Ergebnis (Modell der Analyse):
    {"woerter": [(Rect, Text, start, ende)], "stellen": [(Rect, fund_id, stelle_index, an)],
     "bilder": [Rect], "seitenrect": Rect}. Eine Stelle über mehrere Zeilen liefert ein Rechteck je Zeile."""
    modell = (ergebnis or {}).get("modell")
    if modell is None or not (0 <= seite_nr0 < len(modell.seiten)):
        return {"woerter": [], "stellen": [], "bilder": [], "seitenrect": fitz.Rect()}
    seite = modell.seiten[seite_nr0]
    stellen = []
    for fund in ergebnis.get("funde", []):
        for i, st in enumerate(fund.get("stellen") or []):
            if st.get("seite") != seite_nr0:
                continue
            for teil in seite.rechtecke(st["start"], st["ende"]):
                stellen.append((fitz.Rect(teil[1]), fund.get("id"), i, bool(st.get("an", True))))
    return {"woerter": seite.woerter(), "stellen": stellen, "bilder": [fitz.Rect(b) for b in seite.bilder],
            "seitenrect": fitz.Rect(seite.rect)}


def ausgabe_vorschau(ausgabe_pfad, verdacht, seite_nr0: int, zoom: float) -> dict:
    """Seitenbild einer AUSGABE mit den Verdachtsstellen der Restrisiko-Prüfung dieser Seite – vorbereitet wie jede
    andere Vorschau und aus einer Kopie im Speicher (die Ausgabe bleibt umbenenn- und löschbar)."""
    zoom = max(0.05, float(zoom))
    doc = _vorbereitetes_dokument(Path(ausgabe_pfad))
    with _SPERRE:
        seite = doc[seite_nr0]
        pix = seite.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        seitenrect = fitz.Rect(seite.rect)
    markiert = []
    for v in verdacht or []:
        nr = getattr(v, "seite", None) if not isinstance(v, dict) else v.get("seite")
        if nr != seite_nr0:
            continue
        rechtecke = getattr(v, "rechtecke", None) if not isinstance(v, dict) else v.get("rechtecke")
        text = getattr(v, "text", "") if not isinstance(v, dict) else v.get("text", "")
        grund = getattr(v, "grund", "") if not isinstance(v, dict) else v.get("grund", "")
        markiert.append({"rechtecke": [fitz.Rect(r) for r in (rechtecke or [])], "text": text, "grund": grund})
    return {"bild": pix.tobytes("png"), "faktor": zoom, "verdacht": markiert, "seitenrect": seitenrect}


def zwischenspeicher_leeren():
    """Vorbereitete Dokumente freigeben (z. B. beim Schließen des Vorschau-Fensters)."""
    with _SPERRE:
        for doc in _VORBEREITET.values():
            try:
                doc.close()
            except Exception:
                pass
        _VORBEREITET.clear()
