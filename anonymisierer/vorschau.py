"""Vorschau-Engine (Vertrag Phase 2, Abschnitt 8): Seitenbilder und Markierungen für das Vorschau-Fenster.

Alle Koordinaten stammen aus demselben Seitenmodell wie Analyse und Schwärzung (seitenmodell.py) und
beziehen sich auf die vorbereitete Seite (nach bake und remove_rotation) – Seitenbild, Wörter und
Fundstellen passen deshalb genau übereinander.

    seite_bild(pdf_pfad_oder_doc, seite_nr0, zoom) -> (PNG-Bytes, Faktor pt -> px)
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

from . import seitenmodell as sm

_SPERRE = threading.Lock()
_VORBEREITET: dict = {}           # (Pfad, Größe, Zeitstempel) -> vorbereitetes Dokument (höchstens 2)


def _datei_schluessel(pfad: Path):
    st = pfad.stat()
    return (str(pfad.resolve()), st.st_size, st.st_mtime_ns)


def _vorbereitetes_dokument(pfad: Path):
    """Vorbereitetes Dokument (bake, remove_rotation, Ebenen sichtbar) – zwischengespeichert, damit das
    Blättern nicht jedes Mal neu einbrennt."""
    schluessel = _datei_schluessel(pfad)
    with _SPERRE:
        doc = _VORBEREITET.get(schluessel)
        if doc is not None:
            return doc
        doc = fitz.open(pfad)
        if doc.needs_pass:
            doc.close()
            raise ValueError("Passwortgeschützt – keine Vorschau möglich.")
        info = sm.dokument_vorbereiten(doc)
        doc = info.get("dokument") or doc
        if len(_VORBEREITET) >= 2:
            for alt in list(_VORBEREITET)[:-1]:
                try:
                    _VORBEREITET.pop(alt).close()
                except Exception:
                    pass
        _VORBEREITET[schluessel] = doc
        return doc


def seite_bild(pdf_pfad_oder_doc, seite_nr0: int, zoom: float) -> tuple:
    """PNG der (vorbereiteten) Seite in `zoom` (1.0 = 72 dpi) und der Faktor pt -> px."""
    zoom = max(0.05, float(zoom))
    if isinstance(pdf_pfad_oder_doc, (str, Path)):
        doc = _vorbereitetes_dokument(Path(pdf_pfad_oder_doc))
        with _SPERRE:
            pix = doc[seite_nr0].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    else:
        seite = pdf_pfad_oder_doc[seite_nr0]
        if seite.rotation:
            seite.remove_rotation()
        pix = seite.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
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
    """Seitenbild einer AUSGABE mit den Verdachtsstellen der Restrisiko-Prüfung dieser Seite."""
    pfad = Path(ausgabe_pfad)
    with fitz.open(pfad) as doc:
        seite = doc[seite_nr0]
        pix = seite.get_pixmap(matrix=fitz.Matrix(max(0.05, float(zoom)), max(0.05, float(zoom))), alpha=False)
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
    return {"bild": pix.tobytes("png"), "faktor": float(zoom), "verdacht": markiert, "seitenrect": seitenrect}


def zwischenspeicher_leeren():
    """Vorbereitete Dokumente freigeben (z. B. beim Schließen des Vorschau-Fensters)."""
    with _SPERRE:
        for doc in _VORBEREITET.values():
            try:
                doc.close()
            except Exception:
                pass
        _VORBEREITET.clear()
