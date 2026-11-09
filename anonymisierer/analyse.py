"""Analyse: Text und PDFs nach personenbezogenen Daten durchsuchen."""

import re
from pathlib import Path

import fitz  # PyMuPDF

from .muster import KATEGORIEN
from .namen import NAMEN_STOPPLISTE, finde_personen_ner, lade_ner, ner_fehler
from .ocr import ist_scan_seite, ocr_textpage

def analysiere_text(text: str, aktive: set[str], whitelist: list[str],
                    immer_schwaerzen: list[str]) -> list[dict]:
    """
    Durchsucht einen Text nach allen aktivierten Kategorien.
    Liefert eine Liste von Funden: {kategorie, anzeige, text, ersatz}
    """
    funde: list[dict] = []
    gesehen: set[tuple] = set()
    wl = [w.lower() for w in whitelist if w.strip()]

    def ist_erlaubt(t: str) -> bool:
        tl = t.lower().strip()
        return any(w in tl or tl in w for w in wl)

    def hinzufuegen(schluessel, anzeige, treffer, ersatz):
        t = treffer.strip()
        if len(t) < 2 or ist_erlaubt(t):
            return
        kennung = t.lower()   # gleicher Text nur einmal, egal welche Kategorie
        if kennung in gesehen:
            return
        gesehen.add(kennung)
        funde.append({"kategorie": schluessel, "anzeige": anzeige,
                      "text": t, "ersatz": ersatz})

    # ---- Personennamen (KI) + manuelle "immer schwärzen"-Begriffe ----
    if "namen" in aktive or immer_schwaerzen:
        personen: list[str] = []
        if "namen" in aktive:
            personen = sorted(finde_personen_ner(text), key=len, reverse=True)
        # Manuelle Begriffe behandeln wir wie Personennamen
        personen = [p for p in immer_schwaerzen if p.strip()] + personen

        pseudonyme: dict[str, str] = {}   # kleingeschriebener Name -> "PERSON A"
        buchstabe = 0

        def pseudonym_fuer(name: str) -> str:
            nonlocal buchstabe
            nl = name.lower()
            # Ist der Name Teil eines schon bekannten Namens (z. B. nur Nachname)?
            for bekannt, ps in pseudonyme.items():
                if nl in bekannt or bekannt in nl:
                    return ps
            ps = f"[PERSON {chr(65 + buchstabe)}]" if buchstabe < 26 else f"[PERSON {buchstabe+1}]"
            buchstabe += 1
            pseudonyme[nl] = ps
            return ps

        for person in personen:
            person = person.strip()
            if not person or ist_erlaubt(person):
                continue
            ps = pseudonym_fuer(person)
            hinzufuegen("namen", "Name", person, ps)
            # Einzelne Namensbestandteile ebenfalls schwärzen
            # (damit "Herr Mustermann" auch ohne Vornamen erwischt wird)
            for teil in re.split(r"[\s\-]+", person):
                teil = teil.strip(".,;:()")
                if len(teil) >= 3 and teil.lower() not in NAMEN_STOPPLISTE:
                    if not ist_erlaubt(teil) and teil.lower() != person.lower():
                        hinzufuegen("namen", "Name (Bestandteil)", teil, ps)

    # ---- Muster-Kategorien ----
    for schluessel, anzeige, ersatz, funktion, _ in KATEGORIEN:
        if funktion is None or schluessel not in aktive:
            continue
        for treffer in funktion(text):
            hinzufuegen(schluessel, anzeige, treffer, ersatz)

    # ---- Bruchstück-Filter ----
    # Ist ein Fund nur ein Teilstück eines längeren Funds ANDERER Kategorie
    # (z. B. eine "Telefonnummer" mitten in einer IBAN), fliegt er raus.
    # Namens-Bestandteile (gleiche Kategorie) bleiben absichtlich erhalten.
    bereinigt = []
    for f in funde:
        # Namen werden NIE herausgefiltert — sie sind das Sensibelste.
        ist_bruchstueck = f["kategorie"] != "namen" and any(
            f is not g and f["kategorie"] != g["kategorie"]
            and len(f["text"]) < len(g["text"])
            and f["text"].lower() in g["text"].lower()
            for g in funde
        )
        if not ist_bruchstueck:
            bereinigt.append(f)
    return bereinigt


def analysiere_pdf(pdf_pfad: Path, aktive: set[str], whitelist: list[str],
                   immer_schwaerzen: list[str], melde=None) -> dict:
    """Öffnet ein PDF (liest Scans per OCR) und liefert alle Funde."""
    ergebnis = {"datei": pdf_pfad, "funde": [], "warnungen": [], "fehler": None,
                "ocr_seiten": 0}
    try:
        doc = fitz.open(pdf_pfad)
    except Exception as e:
        ergebnis["fehler"] = f"Konnte nicht geöffnet werden: {e}"
        return ergebnis
    if doc.needs_pass:
        doc.close()
        ergebnis["fehler"] = "Passwortgeschützt — übersprungen."
        return ergebnis

    teile, ocr_warnung_gezeigt = [], False
    for nr in range(len(doc)):
        seite = doc[nr]
        text = seite.get_text()
        if text.strip():
            teile.append(text)
        if not ist_scan_seite(seite):
            continue
        # Scan-Seite (ggf. mit Textstempel) -> zusätzlich OCR
        if melde:
            melde(f"   OCR läuft: {pdf_pfad.name}, Seite {nr + 1}/{len(doc)} …")
        tp, warnung = ocr_textpage(seite)
        if warnung and not ocr_warnung_gezeigt:
            ergebnis["warnungen"].append(warnung)
            ocr_warnung_gezeigt = True
        if tp is not None:
            ocr_text = seite.get_text(textpage=tp)
            teile.append(ocr_text)
            ergebnis["ocr_seiten"] += 1
            # Blinden Fleck melden: Wenn die OCR auf einer Seite fast nichts
            # lesen kann, kann sie dort auch nichts finden!
            if len(ocr_text.split()) < 25:
                ergebnis["warnungen"].append(
                    f"Seite {nr + 1} ist für die OCR kaum lesbar — dort kann "
                    f"NICHTS automatisch erkannt werden. Unbedingt manuell prüfen!")
    doc.close()
    text = "\n".join(teile)

    if not text.strip():
        ergebnis["warnungen"].append(
            "Kein Text lesbar — weder direkt noch per OCR.")
        return ergebnis
    if ergebnis["ocr_seiten"]:
        ergebnis["warnungen"].append(
            f"{ergebnis['ocr_seiten']} Seite(n) per OCR gelesen. OCR kann sich "
            f"verlesen — Ergebnis bitte besonders sorgfältig prüfen!")

    ergebnis["funde"] = analysiere_text(text, aktive, whitelist, immer_schwaerzen)
    if "namen" in aktive and lade_ner() is None:
        ergebnis["warnungen"].append(
            "Namenserkennung inaktiv: " + (ner_fehler() or "Modell fehlt."))
    return ergebnis
