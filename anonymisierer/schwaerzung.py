"""Schwärzung: Funde wirklich aus dem PDF entfernen (Text und Bildpixel), Selbstkontrolle."""

from pathlib import Path

import fitz  # PyMuPDF

from .ocr import ist_scan_seite, ocr_textpage

def schwaerze_pdf(pdf_pfad: Path, funde: list[dict], melde=None) -> dict:
    """
    Ersetzt alle übergebenen Funde durch ihre Platzhalter — auch in Scans
    (dort werden die Bildpixel unter der Fundstelle mit entfernt).
    """
    ergebnis = {"treffer": 0, "ausgabe": None, "warnungen": []}
    doc = fitz.open(pdf_pfad)

    # Längere Fundtexte zuerst (verhindert Überschneidungen)
    funde = sorted(funde, key=lambda f: len(f["text"]), reverse=True)

    ocr_genutzt = False
    for nr in range(len(doc)):
        seite = doc[nr]
        tp = None
        if ist_scan_seite(seite):                 # Scan-Seite -> OCR-Textebene
            if melde:
                melde(f"   OCR läuft: {pdf_pfad.name}, Seite {nr + 1}/{len(doc)} …")
            tp, _ = ocr_textpage(seite)
            if tp is None:
                continue
            ocr_genutzt = True
        bereits: list = []
        for fund in funde:
            # In der normalen Text-Ebene UND (falls Scan) in der OCR-Ebene suchen
            treffer = list(seite.search_for(fund["text"]))
            if tp is not None:
                treffer += list(seite.search_for(fund["text"], textpage=tp))
            for rechteck in treffer:
                if any(rechteck.intersects(alt) for alt in bereits):
                    continue
                bereits.append(rechteck)
                seite.add_redact_annot(
                    rechteck, text=fund["ersatz"],
                    fill=(0.92, 0.92, 0.92), text_color=(0, 0, 0), fontsize=7,
                )
                ergebnis["treffer"] += 1
        # apply_redactions entfernt Text UND die Bildpixel im Rechteck
        seite.apply_redactions()

    if ergebnis["treffer"] == 0:
        doc.close()
        return ergebnis

    doc.set_metadata({})
    doc.del_xml_metadata()

    ziel_ordner = pdf_pfad.parent / "anonymisiert"
    ziel_ordner.mkdir(exist_ok=True)
    ausgabe = ziel_ordner / (pdf_pfad.stem + "_anonym.pdf")
    doc.save(ausgabe, garbage=4, deflate=True)
    doc.close()
    ergebnis["ausgabe"] = ausgabe

    # ---- Selbstkontrolle: sind die Originaltexte wirklich weg? ----
    kontrolle = fitz.open(ausgabe)
    kontroll_teile = []
    for nr in range(len(kontrolle)):
        seite = kontrolle[nr]
        text = seite.get_text()
        if text.strip():
            kontroll_teile.append(text)
        if ist_scan_seite(seite) and ocr_genutzt:
            if melde:
                melde(f"   Kontroll-OCR: {ausgabe.name}, Seite {nr + 1}/{len(kontrolle)} …")
            tp, _ = ocr_textpage(seite)
            if tp is not None:
                kontroll_teile.append(seite.get_text(textpage=tp))
    kontrolle.close()
    voller_text = "\n".join(kontroll_teile).lower()
    for fund in funde:
        if fund["text"].lower() in voller_text:
            ergebnis["warnungen"].append(
                f"'{fund['text']}' ist noch auffindbar — bitte manuell prüfen!")
    return ergebnis
