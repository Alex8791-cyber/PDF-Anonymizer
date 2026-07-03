#!/usr/bin/env python3
"""
PDF-Anonymisierer — Dokumente sicher für ChatGPT & Claude machen
=================================================================

Zweck: PDFs sollen an KI-Dienste (ChatGPT, Claude …) gegeben werden
können, ohne personenbezogene Daten preiszugeben. Das Programm findet
automatisch:

  • Namen von Personen        (KI-Erkennung, deutsches Sprachmodell)
  • Adressen                  (Straße + Hausnummer, PLZ + Ort)
  • IBANs                     (mit Prüfziffern-Kontrolle)
  • Telefonnummern
  • E-Mail-Adressen
  • Geburtsdaten              (Datumsangaben neben "geb." / "Geburtsdatum")
  • Vertrags-/Kunden-/Versicherungsschein-Nummern
  • Sozialversicherungsnummern & Steuer-IDs
  • Kfz-Kennzeichen

Ersetzt wird mit lesbaren Platzhaltern wie [PERSON A], [IBAN],
[ADRESSE] — so bleibt das Dokument für die KI verständlich
("Person A" bleibt im ganzen Dokument dieselbe Person!), aber ohne
echte Daten. Der Text wird dabei WIRKLICH aus der PDF entfernt.

WICHTIG: Vor dem Schwärzen zeigt das Programm eine Prüfliste aller
Funde. Keine automatische Erkennung ist perfekt — der Blick auf die
Liste (und stichprobenartig auf das Ergebnis) bleibt Pflicht!

Einmalige Vorbereitung: Installieren.bat doppelklicken
Starten: Desktop-Verknüpfung "PDF-Anonymisierer"
"""

import re
import sys
import threading
import traceback
from pathlib import Path

# ----------------------------------------------------------------------
# Windows-Feinschliff
# ----------------------------------------------------------------------
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # scharfe Darstellung
    except Exception:
        pass

def _unbehandelter_fehler(typ, wert, tb):
    """Fehler in Logdatei schreiben (ohne Konsole wären sie unsichtbar)."""
    log = Path(__file__).with_name("fehler.log")
    with open(log, "a", encoding="utf-8") as f:
        f.write("".join(traceback.format_exception(typ, wert, tb)) + "\n")
    try:
        from tkinter import messagebox
        messagebox.showerror("Unerwarteter Fehler",
                             f"Es ist ein Fehler aufgetreten.\nDetails stehen in:\n{log}")
    except Exception:
        pass

sys.excepthook = _unbehandelter_fehler

# ----------------------------------------------------------------------
# Abhängigkeiten
# ----------------------------------------------------------------------
try:
    import fitz  # PyMuPDF
except ImportError:
    meldung = ("Das Paket 'PyMuPDF' fehlt.\n\n"
               "Bitte einmal 'Installieren.bat' ausführen.")
    print("FEHLER: " + meldung)
    try:
        import tkinter as _tk
        from tkinter import messagebox as _mb
        _w = _tk.Tk(); _w.withdraw()
        _mb.showerror("PDF-Anonymisierer — Paket fehlt", meldung)
    except Exception:
        pass
    sys.exit(1)

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_VERFUEGBAR = True
except ImportError:
    DND_VERFUEGBAR = False


# ======================================================================
# TEIL 1: ERKENNUNGS-LOGIK (unabhängig von der Oberfläche)
# ======================================================================

# ---- OCR (Texterkennung für eingescannte PDFs) -------------------------
import os

def _tessdata_finden():
    """Sucht den Tesseract-Sprachdaten-Ordner an den üblichen Orten."""
    kandidaten = [os.environ.get("TESSDATA_PREFIX")]
    if sys.platform == "win32":
        kandidaten += [
            r"C:\Program Files\Tesseract-OCR\tessdata",
            r"C:\Program Files (x86)\Tesseract-OCR\tessdata",
            str(Path.home() / r"AppData\Local\Programs\Tesseract-OCR\tessdata"),
        ]
    else:
        kandidaten += ["/usr/share/tesseract-ocr/5/tessdata",
                       "/usr/share/tesseract-ocr/4.00/tessdata",
                       "/usr/share/tessdata"]
    for k in kandidaten:
        if k and Path(k).exists():
            os.environ["TESSDATA_PREFIX"] = k
            return k
    return None


def ist_scan_seite(seite) -> bool:
    """Erkennt Scan-Seiten: kein Text ODER ein Bild bedeckt >50 % der Seite
    (z. B. Scans mit Textstempel oder bereits eingefügten Platzhaltern)."""
    if not seite.get_text().strip():
        return True
    seiten_flaeche = abs(seite.rect)
    try:
        for info in seite.get_image_info():
            if abs(fitz.Rect(info["bbox"])) >= 0.5 * seiten_flaeche:
                return True
    except Exception:
        pass
    return False


def ocr_textpage(seite, melde=None):
    """
    Erzeugt per OCR eine durchsuchbare Textebene für eine Scan-Seite.
    Rückgabe: (textpage oder None, Warnung oder None)
    """
    tessdata = _tessdata_finden()
    if tessdata is None:
        return None, ("Tesseract-OCR ist nicht installiert — Scans können nicht "
                      "gelesen werden. Bitte Installieren.bat erneut ausführen.")
    if (Path(tessdata) / "deu.traineddata").exists():
        sprache, warnung = "deu", None
    elif (Path(tessdata) / "eng.traineddata").exists():
        sprache = "eng"
        warnung = ("Deutsche OCR-Sprachdatei fehlt — nutze Englisch "
                   "(Umlaute werden evtl. falsch erkannt).")
    else:
        return None, "Keine OCR-Sprachdatei gefunden — Installieren.bat erneut ausführen."
    try:
        tp = seite.get_textpage_ocr(language=sprache, dpi=300, full=True,
                                    tessdata=tessdata)
        return tp, warnung
    except Exception as e:
        return None, f"OCR fehlgeschlagen: {e}"

# ---- KI-Namenserkennung (spaCy) laden — optional -----------------------
_NLP = None          # das geladene Sprachmodell (oder None)
_NLP_FEHLER = None   # Begründung, falls nicht verfügbar

def lade_ner():
    """Lädt das deutsche spaCy-Modell für die Namenserkennung (einmalig)."""
    global _NLP, _NLP_FEHLER
    if _NLP is not None or _NLP_FEHLER is not None:
        return _NLP
    try:
        import spacy
        for modell in ("de_core_news_md", "de_core_news_sm"):
            try:
                _NLP = spacy.load(modell, disable=["lemmatizer", "tagger"])
                return _NLP
            except OSError:
                continue
        _NLP_FEHLER = ("Deutsches Sprachmodell fehlt "
                       "(Installieren.bat erneut ausführen).")
    except ImportError:
        _NLP_FEHLER = "Paket 'spacy' fehlt (Installieren.bat erneut ausführen)."
    return None


def finde_personen_ner(text: str) -> set[str]:
    """Findet Personennamen per KI-Modell. Leere Menge, falls Modell fehlt."""
    nlp = lade_ner()
    if nlp is None:
        return set()
    namen: set[str] = set()
    # Lange Texte in Stücke teilen (Speicher schonen)
    for anfang in range(0, len(text), 90_000):
        doc = nlp(text[anfang:anfang + 100_000])
        for ent in doc.ents:
            if ent.label_ == "PER":
                name = ent.text.strip(" \n\t,.;:()[]\"'")
                if len(name) >= 3 and any(c.isalpha() for c in name):
                    namen.add(name)
    return namen


# ---- Muster-Erkennung (Reguläre Ausdrücke) -----------------------------

def _iban_gueltig(iban: str) -> bool:
    """Prüfziffern-Kontrolle (Modulo 97) — filtert Zufallstreffer heraus."""
    s = re.sub(r"\s", "", iban).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", s):
        return False
    umgestellt = s[4:] + s[:4]
    zahl = "".join(str(int(z, 36)) for z in umgestellt)
    return int(zahl) % 97 == 1


# Jede Kategorie: (Anzeigename, Platzhalter, Suchfunktion)
def _suche(muster, text, flags=0):
    return [m.group(0) for m in re.finditer(muster, text, flags)]

def finde_iban(text):
    kandidaten = _suche(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?[A-Z0-9]{1,4})?\b", text)
    return [k for k in kandidaten if _iban_gueltig(k)]

def finde_email(text):
    return _suche(r"\b[\w.\-+%]+@[\w.\-]+\.[A-Za-z]{2,}\b", text)

def finde_telefon(text):
    # Deutsche Formate: 0171 1234567, +49 911 123456, (09171) 12 34 56 …
    # Der Blick zurück (?<!…) verhindert Treffer MITTEN in längeren Nummern.
    treffer = _suche(r"(?<![\d\-./])(?:\+49[\s\-/]?|0)\d{2,5}[\s\-/]?\d{3,}(?:[\s\-/]?\d{2,})*", text)
    # Mindestlänge, sonst erwischt man Vertragsnummern o. Ä.
    return [t for t in treffer if len(re.sub(r"\D", "", t)) >= 8]

def finde_geburtsdaten(text):
    """Datumsangaben, die bei 'geb.' / 'geb. am' / 'Geburtsdatum' o. Ä. stehen.
    Zwischen Stichwort und Datum dürfen bis zu 25 Zeichen liegen (auch
    Zeilenumbrüche) — deckt Formularlayouts ab wie:
    'geb. am / Geschlecht\\n02.09.1983'."""
    ergebnisse = []
    for m in re.finditer(
        r"(?:geb\.?|geboren|Geburtsdatum|Geburtstag)"
        r"[^\d]{0,25}?"
        r"(\d{1,2}\.\s?\d{1,2}\.\s?\d{2,4})", text, re.IGNORECASE | re.DOTALL):
        ergebnisse.append(m.group(1))
    return ergebnisse

def finde_alle_daten(text):
    """Optional: ALLE Datumsangaben (Vorsicht — auch Vertragsdaten!)."""
    return _suche(r"\b\d{1,2}\.\s?\d{1,2}\.\s?(?:19|20)\d{2}\b", text)

def finde_strasse(text):
    return _suche(
        r"\b[A-ZÄÖÜ][\w\.\-äöüß]*(?:straße|strasse|str\.|weg|platz|gasse|allee|"
        r"ring|damm|ufer|hof|steig|pfad|chaussee)\s+\d+\s?[a-hA-H]?\b", text)

def finde_plz_ort(text):
    return _suche(r"\b\d{5}\s+[A-ZÄÖÜ][a-zäöüß\-]+(?:\s(?:am|an\sder|bei|im)\s[A-ZÄÖÜ][a-zäöüß\-]+)?\b", text)

def finde_vertragsnummern(text):
    """Nummern, die hinter einem verräterischen Etikett stehen."""
    ergebnisse = []
    for m in re.finditer(
        r"(?:Versicherungsschein|Vertrags?|Kunden|Schaden[s]?|Antrags?|"
        r"Police[n]?|Personal|Mitglieds?|Depot|Konto|Zulage[n]?)"
        r"[\s\-]?(?:Nr\.?|Nummer|nummer)\s*[:.\s]?\s*"
        r"([A-Z0-9][A-Z0-9\-./ ]{3,24}[A-Z0-9])", text, re.IGNORECASE):
        ergebnisse.append(m.group(1).strip())
    return ergebnisse

def finde_sv_nummer(text):
    return _suche(r"\b\d{2}\s?\d{6}\s?[A-Z]\s?\d{3}\b", text)

def _steuer_id_gueltig(nummer: str) -> bool:
    """Amtliche Prüfziffern-Kontrolle der Steuer-IdNr (§ 139b AO).
    Damit erkennen wir 11-stellige IDs auch OHNE Beschriftung davor,
    ohne zufällige Zahlenkolonnen zu erwischen."""
    z = re.sub(r"\D", "", nummer)
    if len(z) != 11 or z[0] == "0":
        return False
    produkt = 10
    for ziffer in z[:10]:
        summe = (int(ziffer) + produkt) % 10
        if summe == 0:
            summe = 10
        produkt = (2 * summe) % 11
    pruef = 11 - produkt
    if pruef == 10:
        pruef = 0
    return pruef == int(z[10])


def finde_steuer_id(text):
    ergebnisse = []
    # 1) Mit Beschriftung — auch Formularlayouts wie "Identifikationsnummer (4)"
    #    mit bis zu 12 Zeichen zwischen Etikett und Nummer (inkl. Zeilenumbruch)
    for m in re.finditer(r"(?:Steuer[\s\-]?(?:ID|Id|id)|IdNr\.?|Identifikationsnummer)"
                         r"[^\d]{0,12}?(\d[\d\s]{9,13}\d)", text, re.DOTALL):
        ergebnisse.append(m.group(1).strip())
    # 2) Ohne Beschriftung: freistehende 11-stellige Nummer mit gültiger Prüfziffer
    for m in re.finditer(r"(?<!\d)(\d{11})(?!\d)", text):
        if _steuer_id_gueltig(m.group(1)):
            ergebnisse.append(m.group(1))
    return ergebnisse

def finde_kindergeldnummer(text):
    """Kindergeldnummern wie 009FK407160 (Format: 3 Ziffern + FK + 6 Ziffern)."""
    return _suche(r"\b\d{3}\s?FK\s?\d{6}\b", text, re.IGNORECASE)

def finde_kennzeichen(text):
    return _suche(r"\b[A-ZÄÖÜ]{1,3}[-\s][A-Z]{1,2}\s?\d{1,4}[EH]?\b", text)


# Reihenfolge = Reihenfolge der Häkchen in der Oberfläche
KATEGORIEN = [
    # (Schlüssel, Anzeigename, Platzhalter, Funktion, standardmäßig an?)
    ("namen",    "Personennamen (KI-Erkennung)",        None,            None,                 True),
    ("iban",     "IBANs",                               "[IBAN]",        finde_iban,           True),
    ("email",    "E-Mail-Adressen",                     "[E-MAIL]",      finde_email,          True),
    ("telefon",  "Telefonnummern",                      "[TELEFON]",     finde_telefon,        True),
    ("geburt",   "Geburtsdaten",                        "[GEB-DATUM]",   finde_geburtsdaten,   True),
    ("strasse",  "Straße + Hausnummer",                 "[ADRESSE]",     finde_strasse,        True),
    ("plzort",   "PLZ + Ort",                           "[PLZ ORT]",     finde_plz_ort,        True),
    ("vertrag",  "Vertrags-/Kunden-/Schein-Nummern",    "[VERTRAGS-NR]", finde_vertragsnummern, True),
    ("svnr",     "Sozialversicherungsnummern",          "[SV-NR]",       finde_sv_nummer,      True),
    ("steuerid", "Steuer-IDs",                          "[STEUER-ID]",   finde_steuer_id,      True),
    ("kfz",      "Kfz-Kennzeichen",                     "[KENNZEICHEN]", finde_kennzeichen,    False),
    ("datum",    "ALLE Datumsangaben (Vorsicht!)",      "[DATUM]",       finde_alle_daten,     False),
]

# Wörter, die die Namenserkennung gern fälschlich als Person meldet
NAMEN_STOPPLISTE = {
    "gmbh", "co", "kg", "ag", "mbh", "versicherung", "lebensversicherung",
    "herr", "frau", "herrn", "sehr", "geehrte", "geehrter", "grüßen",
    "freundlichen", "mit", "und",
}


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
            "Namenserkennung inaktiv: " + (_NLP_FEHLER or "Modell fehlt."))
    return ergebnis


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


def sammle_pdfs(pfade: list[str]) -> list[Path]:
    """Nimmt Dateien UND Ordner entgegen, liefert alle PDFs darin."""
    gefunden: list[Path] = []
    for p in pfade:
        pfad = Path(p)
        if pfad.is_dir():
            for pdf in sorted(pfad.rglob("*.pdf")):
                if "anonymisiert" not in pdf.parts and not pdf.stem.endswith("_anonym"):
                    gefunden.append(pdf)
        elif pfad.suffix.lower() == ".pdf" and pfad.exists():
            gefunden.append(pfad)
    return list(dict.fromkeys(gefunden))


# ======================================================================
# TEIL 2: OBERFLÄCHE
# ======================================================================

FARBE_HINTERGRUND = "#f4f5f7"
FARBE_KARTE = "#ffffff"
FARBE_AKZENT = "#1a5fb4"
FARBE_AKZENT_HELL = "#e8f0fb"
FARBE_TEXT_GRAU = "#6b7280"
FARBE_GRUEN = "#1a7f37"
FARBE_ROT = "#b91c1c"


class AnonymisiererApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF-Anonymisierer — Dokumente sicher für KI-Dienste machen")
        self.root.geometry("860x900")
        self.root.minsize(760, 780)
        self.root.configure(bg=FARBE_HINTERGRUND)

        self.dateien: list[Path] = []
        self.analyse_ergebnisse: dict = {}   # Pfad -> Ergebnis von analysiere_pdf
        self.laeuft = False

        self._baue_oberflaeche()

    # ------------------------------------------------------------------
    def _baue_oberflaeche(self):
        haupt = tk.Frame(self.root, bg=FARBE_HINTERGRUND, padx=20, pady=12)
        haupt.pack(fill="both", expand=True)

        tk.Label(haupt, text="PDF-Anonymisierer", font=("Segoe UI", 19, "bold"),
                 bg=FARBE_HINTERGRUND, fg="#111827").pack(anchor="w")
        tk.Label(haupt,
                 text="Findet personenbezogene Daten automatisch und ersetzt sie durch Platzhalter "
                      "([PERSON A], [IBAN] …) — für die gefahrlose Weitergabe an ChatGPT & Claude.",
                 font=("Segoe UI", 9), bg=FARBE_HINTERGRUND, fg=FARBE_TEXT_GRAU,
                 wraplength=800, justify="left").pack(anchor="w", pady=(0, 8))

        # ---------- Schritt 1: Dateien ----------
        karte1 = self._karte(haupt, "1  ·  PDF-Dateien", expand=False)
        drop_text = ("PDFs oder ganze Ordner hierher ziehen  (oder klicken zum Auswählen)"
                     if DND_VERFUEGBAR else
                     "Drag & Drop nicht verfügbar — bitte klicken zum Auswählen")
        self.drop_zone = tk.Label(karte1, text="⬇  " + drop_text,
                                  font=("Segoe UI", 10), bg=FARBE_AKZENT_HELL,
                                  fg=FARBE_AKZENT, height=2, cursor="hand2",
                                  highlightthickness=2, highlightbackground="#b9cfee")
        self.drop_zone.pack(fill="x", pady=(2, 6))
        self.drop_zone.bind("<Button-1>", lambda e: self.dateien_waehlen())
        if DND_VERFUEGBAR:
            self.drop_zone.drop_target_register(DND_FILES)
            self.drop_zone.dnd_bind("<<Drop>>", self._drop_ereignis)

        zeile = tk.Frame(karte1, bg=FARBE_KARTE); zeile.pack(fill="x")
        self._knopf(zeile, "Dateien auswählen …", self.dateien_waehlen, True).pack(side="left")
        self._knopf(zeile, "Ordner auswählen …", self.ordner_waehlen, True).pack(side="left", padx=(6, 0))
        self.datei_hinweis = tk.Label(zeile, text="Noch keine Dateien.",
                                      font=("Segoe UI", 9), bg=FARBE_KARTE, fg=FARBE_TEXT_GRAU)
        self.datei_hinweis.pack(side="left", padx=(12, 0))
        self._knopf(zeile, "Liste leeren", self.liste_leeren, True).pack(side="right")

        # ---------- Schritt 2: Was soll erkannt werden? ----------
        karte2 = self._karte(haupt, "2  ·  Was soll erkannt werden?", expand=False)
        gitter = tk.Frame(karte2, bg=FARBE_KARTE); gitter.pack(fill="x")
        self.kategorie_vars: dict[str, tk.BooleanVar] = {}
        for i, (schluessel, anzeige, _, _, standard) in enumerate(KATEGORIEN):
            var = tk.BooleanVar(value=standard)
            self.kategorie_vars[schluessel] = var
            tk.Checkbutton(gitter, text=anzeige, variable=var, font=("Segoe UI", 9),
                           bg=FARBE_KARTE, activebackground=FARBE_KARTE, anchor="w"
                           ).grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 12))

        listen = tk.Frame(karte2, bg=FARBE_KARTE); listen.pack(fill="x", pady=(8, 0))
        links = tk.Frame(listen, bg=FARBE_KARTE); links.pack(side="left", fill="both", expand=True, padx=(0, 8))
        rechts = tk.Frame(listen, bg=FARBE_KARTE); rechts.pack(side="left", fill="both", expand=True)

        tk.Label(links, text="Zusätzlich IMMER schwärzen (ein Begriff pro Zeile):",
                 font=("Segoe UI", 9, "bold"), bg=FARBE_KARTE).pack(anchor="w")
        self.immer_feld = tk.Text(links, height=3, font=("Segoe UI", 9), relief="flat",
                                  highlightthickness=1, highlightbackground="#e5e7eb", bg="#fafafa")
        self.immer_feld.pack(fill="x")

        tk.Label(rechts, text="NIE schwärzen (z. B. eigene Firmen-/Beraternamen):",
                 font=("Segoe UI", 9, "bold"), bg=FARBE_KARTE).pack(anchor="w")
        self.nie_feld = tk.Text(rechts, height=3, font=("Segoe UI", 9), relief="flat",
                                highlightthickness=1, highlightbackground="#e5e7eb", bg="#fafafa")
        self.nie_feld.pack(fill="x")

        self.analyse_knopf = self._knopf(karte2, "  1. Analysieren — Funde anzeigen  ", self.analysieren)
        self.analyse_knopf.pack(anchor="w", pady=(8, 0))

        # ---------- Schritt 3: Prüfen & Schwärzen ----------
        karte3 = self._karte(haupt, "3  ·  Funde prüfen, dann schwärzen", expand=True)
        tk.Label(karte3, text="Doppelklick auf eine Zeile = Häkchen an/aus. Nur angehakte Funde werden ersetzt.",
                 font=("Segoe UI", 9), bg=FARBE_KARTE, fg=FARBE_TEXT_GRAU).pack(anchor="w")

        baum_rahmen = tk.Frame(karte3, bg=FARBE_KARTE)
        baum_rahmen.pack(fill="both", expand=True, pady=(4, 6))
        spalten = ("kategorie", "text", "ersatz")
        self.baum = ttk.Treeview(baum_rahmen, columns=spalten, show="tree headings",
                                 selectmode="browse")
        self.baum.heading("#0", text="✓ / Datei")
        self.baum.heading("kategorie", text="Kategorie")
        self.baum.heading("text", text="Gefundener Text")
        self.baum.heading("ersatz", text="Wird ersetzt durch")
        self.baum.column("#0", width=200, anchor="w")
        self.baum.column("kategorie", width=140, anchor="w")
        self.baum.column("text", width=260, anchor="w")
        self.baum.column("ersatz", width=130, anchor="w")
        roll = ttk.Scrollbar(baum_rahmen, command=self.baum.yview)
        self.baum.configure(yscrollcommand=roll.set)
        self.baum.pack(side="left", fill="both", expand=True)
        roll.pack(side="right", fill="y")
        self.baum.bind("<Double-Button-1>", self._haken_umschalten)
        self.baum.bind("<space>", self._haken_umschalten)

        zeile3 = tk.Frame(karte3, bg=FARBE_KARTE); zeile3.pack(fill="x")
        self.start_knopf = self._knopf(zeile3, "  2. Schwärzen starten  ", self.schwaerzen)
        self.start_knopf.pack(side="left")
        self.start_knopf.config(state="disabled")
        self.fortschritt = ttk.Progressbar(zeile3, mode="determinate")
        self.fortschritt.pack(side="left", fill="x", expand=True, padx=(10, 0))

        self.protokoll = tk.Text(karte3, height=5, font=("Consolas", 9), relief="flat",
                                 highlightthickness=1, highlightbackground="#e5e7eb",
                                 bg="#fafafa", state="disabled", wrap="word")
        self.protokoll.pack(fill="x", pady=(6, 0))
        for stil, farbe in [("ok", FARBE_GRUEN), ("warnung", "#b45309"),
                            ("fehler", FARBE_ROT), ("grau", FARBE_TEXT_GRAU)]:
            self.protokoll.tag_configure(stil, foreground=farbe)

    # Oberflächen-Helfer ------------------------------------------------
    def _karte(self, eltern, titel, expand):
        rahmen = tk.Frame(eltern, bg=FARBE_KARTE, padx=14, pady=10,
                          highlightthickness=1, highlightbackground="#e5e7eb")
        rahmen.pack(fill="both" if expand else "x", expand=expand, pady=(0, 10))
        tk.Label(rahmen, text=titel, font=("Segoe UI", 11, "bold"),
                 bg=FARBE_KARTE, fg="#111827").pack(anchor="w", pady=(0, 4))
        return rahmen

    def _knopf(self, eltern, text, befehl, sekundaer=False):
        if sekundaer:
            return tk.Button(eltern, text=text, command=befehl, font=("Segoe UI", 9),
                             bg="#eef1f5", fg="#111827", relief="flat",
                             padx=10, pady=3, cursor="hand2", activebackground="#dde3ea")
        return tk.Button(eltern, text=text, command=befehl, font=("Segoe UI", 10, "bold"),
                         bg=FARBE_AKZENT, fg="white", relief="flat",
                         padx=12, pady=6, cursor="hand2",
                         activebackground="#134a8e", activeforeground="white")

    # Dateiauswahl ------------------------------------------------------
    def _drop_ereignis(self, ereignis):
        pfade = re.findall(r"\{([^}]*)\}|(\S+)", ereignis.data)
        self._pdfs_hinzufuegen([a or b for a, b in pfade])

    def dateien_waehlen(self):
        pfade = filedialog.askopenfilenames(title="PDF-Dateien auswählen",
                                            filetypes=[("PDF-Dateien", "*.pdf")])
        if pfade:
            self._pdfs_hinzufuegen(list(pfade))

    def ordner_waehlen(self):
        ordner = filedialog.askdirectory(title="Ordner mit PDFs auswählen")
        if ordner:
            self._pdfs_hinzufuegen([ordner])

    def _pdfs_hinzufuegen(self, pfade):
        for pdf in sammle_pdfs(pfade):
            if pdf not in self.dateien:
                self.dateien.append(pdf)
        self.datei_hinweis.config(text=f"{len(self.dateien)} PDF-Datei(en) ausgewählt."
                                  if self.dateien else "Noch keine Dateien.")

    def liste_leeren(self):
        self.dateien.clear()
        self.analyse_ergebnisse.clear()
        self.baum.delete(*self.baum.get_children())
        self.start_knopf.config(state="disabled")
        self.datei_hinweis.config(text="Noch keine Dateien.")

    # Analyse -----------------------------------------------------------
    def analysieren(self):
        if self.laeuft:
            return
        if not self.dateien:
            messagebox.showwarning("Keine Dateien", "Bitte zuerst PDF-Dateien auswählen.")
            return
        self.laeuft = True
        self.analyse_knopf.config(state="disabled", text="  Analysiere …  ")
        self.start_knopf.config(state="disabled")
        self.baum.delete(*self.baum.get_children())
        self._protokoll_leeren()
        self.fortschritt.config(value=0, maximum=len(self.dateien))

        aktive = {k for k, v in self.kategorie_vars.items() if v.get()}
        immer = [z.strip() for z in self.immer_feld.get("1.0", "end").splitlines() if z.strip()]
        nie = [z.strip() for z in self.nie_feld.get("1.0", "end").splitlines() if z.strip()]

        threading.Thread(target=self._analyse_lauf, args=(aktive, nie, immer),
                         daemon=True).start()

    def _analyse_lauf(self, aktive, nie, immer):
        # Sprachmodell einmal vorab laden (dauert beim ersten Mal einige Sekunden)
        if "namen" in aktive:
            self._log("Lade Namenserkennungs-Modell …", "grau")
            lade_ner()
        gesamt = 0
        for i, pdf in enumerate(self.dateien, 1):
            ergebnis = analysiere_pdf(pdf, aktive, nie, immer,
                                      melde=lambda t: self._log(t, "grau"))
            self.analyse_ergebnisse[pdf] = ergebnis
            if ergebnis["fehler"]:
                self._log(f"✖ {pdf.name}: {ergebnis['fehler']}", "fehler")
            for w in ergebnis["warnungen"]:
                self._log(f"⚠ {pdf.name}: {w}", "warnung")
            gesamt += len(ergebnis["funde"])
            self.root.after(0, self._baum_fuellen, pdf, ergebnis["funde"])
            self._fortschritt_setzen(i)
        self._log(f"Analyse fertig: {gesamt} Fund(e) in {len(self.dateien)} Datei(en). "
                  f"Bitte Liste prüfen, dann schwärzen.", "ok")
        self.root.after(0, self._analyse_fertig, gesamt)

    def _baum_fuellen(self, pdf, funde):
        eltern = self.baum.insert("", "end", text=f"☑  {pdf.name}", open=True,
                                  values=("", f"{len(funde)} Fund(e)", ""))
        for fund in funde:
            self.baum.insert(eltern, "end", text="☑",
                             values=(fund["anzeige"], fund["text"], fund["ersatz"]),
                             tags=("an",))

    def _analyse_fertig(self, gesamt):
        self.laeuft = False
        self.analyse_knopf.config(state="normal", text="  1. Analysieren — Funde anzeigen  ")
        if gesamt:
            self.start_knopf.config(state="normal")

    def _haken_umschalten(self, ereignis=None):
        eintrag = self.baum.focus()
        if not eintrag:
            return
        text = self.baum.item(eintrag, "text")
        neu = text.replace("☑", "☐") if "☑" in text else text.replace("☐", "☑")
        self.baum.item(eintrag, text=neu)
        # Bei einer Datei-Zeile: alle Kinder mit umschalten
        for kind in self.baum.get_children(eintrag):
            kt = self.baum.item(kind, "text")
            self.baum.item(kind, text="☑" if "☑" in neu else "☐")

    # Schwärzen ---------------------------------------------------------
    def schwaerzen(self):
        if self.laeuft:
            return
        auftraege = []  # (pdf, [funde])
        for datei_eintrag in self.baum.get_children():
            name = self.baum.item(datei_eintrag, "text").replace("☑", "").replace("☐", "").strip()
            pdf = next((p for p in self.dateien if p.name == name), None)
            if pdf is None:
                continue
            gewaehlt = []
            alle_funde = self.analyse_ergebnisse.get(pdf, {}).get("funde", [])
            kinder = self.baum.get_children(datei_eintrag)
            for kind, fund in zip(kinder, alle_funde):
                if "☑" in self.baum.item(kind, "text"):
                    gewaehlt.append(fund)
            if gewaehlt:
                auftraege.append((pdf, gewaehlt))
        if not auftraege:
            messagebox.showwarning("Nichts ausgewählt", "Es ist kein Fund angehakt.")
            return

        self.laeuft = True
        self.start_knopf.config(state="disabled", text="  Läuft …  ")
        self.fortschritt.config(value=0, maximum=len(auftraege))
        threading.Thread(target=self._schwaerz_lauf, args=(auftraege,), daemon=True).start()

    def _schwaerz_lauf(self, auftraege):
        gesamt, letzte_ausgabe = 0, None
        for i, (pdf, funde) in enumerate(auftraege, 1):
            try:
                ergebnis = schwaerze_pdf(pdf, funde,
                                         melde=lambda t: self._log(t, "grau"))
            except Exception:
                self._log(f"✖ {pdf.name}: Unerwarteter Fehler (siehe fehler.log)", "fehler")
                _unbehandelter_fehler(*sys.exc_info())
                self._fortschritt_setzen(i)
                continue
            gesamt += ergebnis["treffer"]
            if ergebnis["ausgabe"]:
                letzte_ausgabe = ergebnis["ausgabe"].parent
                self._log(f"✔ {pdf.name}: {ergebnis['treffer']} Stelle(n) ersetzt "
                          f"→ {ergebnis['ausgabe'].name}", "ok")
            for w in ergebnis["warnungen"]:
                self._log(f"⚠ {pdf.name}: {w}", "warnung")
            self._fortschritt_setzen(i)
        self._log("")
        self._log(f"Fertig: {gesamt} Stelle(n) ersetzt. Ergebnisse liegen im "
                  f"Unterordner \"anonymisiert\".", "ok")
        self._log("Bitte Ergebnis stichprobenartig öffnen und prüfen, bevor es "
                  "an einen KI-Dienst geht!", "warnung")
        self.root.after(0, self._schwaerzen_fertig)

    def _schwaerzen_fertig(self):
        self.laeuft = False
        self.start_knopf.config(state="normal", text="  2. Schwärzen starten  ")

    # Protokoll-Helfer (thread-sicher) ----------------------------------
    def _log(self, text, stil=None):
        def einfuegen():
            self.protokoll.config(state="normal")
            self.protokoll.insert("end", text + "\n", stil)
            self.protokoll.see("end")
            self.protokoll.config(state="disabled")
        self.root.after(0, einfuegen)

    def _protokoll_leeren(self):
        self.protokoll.config(state="normal")
        self.protokoll.delete("1.0", "end")
        self.protokoll.config(state="disabled")

    def _fortschritt_setzen(self, wert):
        self.root.after(0, lambda: self.fortschritt.config(value=wert))


def main():
    root = TkinterDnD.Tk() if DND_VERFUEGBAR else tk.Tk()
    AnonymisiererApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
