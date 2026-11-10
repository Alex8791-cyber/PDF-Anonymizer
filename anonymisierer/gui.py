"""Grafische Oberfläche (tkinter): Dateien wählen, analysieren, Funde prüfen, schwärzen, Ausgaben freigeben.

Die Engine wird direkt nach Vertrag aufgerufen (CONTRACT/CONTRACT_V2). Neue Vertragsteile (Schutzstufen,
Kundenliste, Fundstellen, manuelle Bereiche, Freigabe, Vorschau, Meldungs-Codes) werden genutzt, sobald die
Engine sie anbietet (Signatur bzw. hasattr); bis dahin greifen die Attrappen in gui_attrappen.py. Fehlt der
Engine eine Fähigkeit, die der Nutzer anfordert, sagt die Oberfläche das – sie lässt nichts still weg.
"""

import base64
import errno
import importlib.metadata
import inspect
import os
import re
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen kennen nur den Namen "fitz"
    import fitz

from . import __version__, dateien
from . import analyse as _analyse_modul
from . import gui_attrappen as attrappen
from . import muster as _muster_modul
from . import schwaerzung as _schwaerz_modul
from .analyse import analysiere_pdf
from .muster import KATEGORIEN
from .namen import lade_ner
from .ocr import OcrDienst
from .schwaerzung import schwaerze_pdf

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_VERFUEGBAR = True
except ImportError:
    DND_FILES = TkinterDnD = None
    DND_VERFUEGBAR = False

# Vertragsteile aus Phase 2: echte Engine, sonst Attrappe (12.5) bzw. None (Funktion entfällt)
weitergabe_anwenden = getattr(_analyse_modul, "weitergabe_anwenden", None)
LaufWissen = getattr(_analyse_modul, "LaufWissen", None)
gesundheit_nur_vermutet = getattr(_analyse_modul, "gesundheit_nur_vermutet", None)
freigeben = getattr(_schwaerz_modul, "freigeben", None) or attrappen.freigeben
verwerfen = getattr(_schwaerz_modul, "verwerfen", None) or attrappen.verwerfen
WARNUNG_KEIN_TREFFER = getattr(_schwaerz_modul, "WARNUNG_KEIN_TREFFER", attrappen.WARNUNG_KEIN_TREFFER)
PROFILE = getattr(_muster_modul, "PROFILE", None) or attrappen.PROFILE
try:
    from .kundenliste import Kundenliste
except ImportError:
    Kundenliste = attrappen.Kundenliste


# ----------------------------------------------------------------------
# Konstanten
# ----------------------------------------------------------------------
FARBE_HINTERGRUND = "#f4f5f7"
FARBE_KARTE = "#ffffff"
FARBE_AKZENT = "#1a5fb4"
FARBE_AKZENT_HELL = "#e8f0fb"
FARBE_TEXT = "#111827"
FARBE_TEXT_GRAU = "#6b7280"
FARBE_GRUEN = "#1a7f37"
FARBE_ROT = "#b91c1c"
FARBE_WARNUNG = "#b45309"
FARBE_HINWEIS_HINTERGRUND = "#fff7e6"
FARBE_HINWEIS_RAND = "#f0c36d"
FARBE_RAND = "#e5e7eb"
FARBE_KNOPF_GESPERRT = "#d1d5db"     # gesperrter Hauptknopf: grau statt blau – deutlich anders als „bereit“
FARBE_KNOPF_GESPERRT_TEXT = "#4b5563"

SCHRIFT = "Segoe UI"
SCHRIFT_MONO = "Consolas"
BASIS_SKALIERUNG = 4 / 3            # „tk scaling“ bei 96 dpi (Windows 100 %)
FENSTER_BREITE, FENSTER_HOEHE = 940, 940   # Entwurfsmaße bei 100 % (passt auf 1080p mit Taskleiste)
FENSTER_MINDESTMASS = (640, 520)
FENSTER_RAND_UNTEN = 140            # Platz für Taskleiste, Titelleiste und Menüleiste
FENSTER_KLEIN_HOEHE = 760           # darunter (bei 100 %) gilt das Fenster als klein: Protokoll kürzer
BAUM_MINDESTHOEHE = 120             # bei 100 %, damit die Fundliste nie ganz verschwindet
BAUM_ANTEIL = 0.45                  # Anteil des freien Platzes für die Fundliste (Arbeitsbereich, GR-02);
                                    # der Einstellbereich (einmal einstellen) scrollt bei Bedarf
KATEGORIE_SPALTEN = 3               # Häkchen-Gitter (4 Spalten schneiden bei 940 px Breite lange Namen ab)
KONTEXT_VORLAUF = 14                # Zeichen vor dem Fund in der Kontextspalte, damit der Fund sichtbar ist
UNTERTITEL_MINDESTHOEHE = 700       # bei 100 %; darunter wird der Untertitel ausgeblendet
OBEN_MINDESTHOEHE = 60              # bei 100 %, Mindesthöhe des scrollbaren Einstellbereichs (Titel + Drop-Zone)
PROTOKOLL_ZEILEN = 5
PROTOKOLL_ZEILEN_KLEIN = 3
PROTOKOLL_MAX_ZEILEN = 5000
VORLADEN_NACH_MS = 800              # spaCy-Modell so lange nach dem Start im Hintergrund laden (PERF-09)
ERSTSTART_NACH_MS = 300             # Hinweis beim ersten Start erst, wenn das Hauptfenster steht
RESTE_WARTEN_S = 30.0               # beim Beenden höchstens so lange auf den Arbeits-Thread warten, der eine
                                    # Arbeitskopie noch offen hält (Windows löscht sie sonst nicht)

HAKEN = {"an": "☑", "aus": "☐", "teil": "⊟"}
# Zeichen vor der Kategorie in der Fundliste: ⚑ = Fund mit Hinweis der Engine (Statuszeile zeigt ihn; steht auch an
# angehakten Kennungen), ⚕ = Gesundheitsdaten (Art. 9 DSGVO), die nur angeboten werden – nur dieses Zeichen nennt
# der Abschlussdialog (Befund: wer jedes ⚑ anklickt, hakte angehakte Kennungen ab)
MARKE_HINWEIS = "⚑ "
MARKE_GESUNDHEIT = "⚕ "
GESUNDHEIT_KATEGORIEN = frozenset(getattr(_muster_modul, "GESUNDHEIT", ("diagnose", "medikament")))
SPALTEN = ("kategorie", "text", "seiten", "anzahl", "kontext", "ersatz")
# Spalte -> (Breite, Mindestbreite, dehnbar) bei 100 %
SPALTEN_MASSE = {"#0": (185, 150, False), "kategorie": (130, 105, False), "text": (160, 130, True),
                 "seiten": (60, 52, False), "anzahl": (55, 48, False), "kontext": (210, 160, True),
                 "ersatz": (95, 85, False)}
ANALYSE_TEXT = "  Analysieren – Funde anzeigen  "
START_TEXT = "  Schwärzen starten  "
VORSCHAU_TEXT = "Vorschau …"
# Tastenkürzel (Alt + Buchstabe); der Buchstabe ist im Knopf unterstrichen (M-67)
KUERZEL = {"analyse": "a", "start": "s", "vorschau": "v"}
SYMBOL_GROESSEN = (16, 32, 48, 64)        # Fenstersymbol (iconphoto); icon.ico enthält 16, 32, 48 und 256
ERSTSTART_TITEL = "Bitte vor der ersten Nutzung lesen"
ERSTSTART_TEXT = (
    "Dieses Programm PSEUDONYMISIERT: Es ersetzt direkte Angaben wie Namen, Anschriften, Geburtsdaten, IBAN, "
    "Telefon- und Vertragsnummern durch Platzhalter wie [PERSON A].\n\n"
    "Andere Angaben bleiben je nach Schutzstufe lesbar – zum Beispiel Diagnosen, Beruf, Beträge oder Orte. "
    "Daraus kann eine Person unter Umständen noch zu erkennen sein.\n\n"
    "Gesichter und Lichtbilder (etwa auf einer Ausweiskopie), Unterschriften und Handschrift werden NICHT "
    "geschwärzt – sie bleiben sichtbar, wenn Sie in der Vorschau keinen Rahmen darüber ziehen.\n\n"
    "Keine automatische Erkennung ist fehlerfrei. Sehen Sie sich deshalb jedes Ergebnis in der Vorschau an, "
    "bevor Sie es weitergeben.\n\n"
    "Die Verantwortung für die Weitergabe an einen KI-Dienst bleibt bei Ihnen.")
# Fotos und Ausweiskopien (Befund Runde 2): Gesicht/Lichtbild, Unterschrift und Handschrift bleiben stehen
FOTO_GRENZEN = ("Gesichter und Lichtbilder (z. B. auf einer Ausweiskopie), Unterschriften und Handschrift werden "
                "NICHT geschwärzt – in der Vorschau unter „Geplante Schwärzung“ einen Rahmen darüber ziehen.")
KENNWORT_TITEL = "Kennwort erforderlich"
ANZEIGE_ART = {"bild": " (Bild → PDF)", "entschluesselt": " (Kennwort entfernt)", "kopie": " (als PDF)"}
NEBENKANAL_NAMEN = (("metadaten", "Metadaten"), ("lesezeichen", "Lesezeichen"), ("anhaenge", "Anhänge"),
                    ("xfa", "Formulardaten (XFA)"))
BAUM_HINWEIS = ("Kästchen (oder Leertaste) = Fund an/aus · Doppelklick auf eine Datei = Vorschau (dort per Klick "
               "oder Rahmen nachschwärzen) · Rechtsklick = mehr")
ANZEIGE_BEGRIFF_VORSCHAU = "Begriff (Vorschau)"
ANZEIGE_MANUELL = "Manuell (Vorschau)"
ANZEIGE_NACHSCHWAERZEN = "Manuell (Nachschwärzen)"
PLATZHALTER_MANUELL = attrappen.PLATZHALTER_MANUELL
PRUEFEN_ERKLAERUNG = ("„_PRUEFEN“ im Dateinamen heißt: noch nicht zur Weitergabe freigegeben – erst in der "
                      "Vorschau prüfen und dort „Freigeben“ drücken.")
STATUS_TEXT = {"fertig": "✔ fertig", "pruefen": "⚠ prüfen", "fehler": "✖ Fehler", "verworfen": "verworfen",
               "keine": "keine Ausgabe"}

_KATEGORIE_SCHLUESSEL = {eintrag[0] for eintrag in KATEGORIEN}


def _ohne_marke(anzeige: str) -> str:
    """Kategorie-Anzeige ohne vorangestelltes Zeichen (⚑/⚕)."""
    for marke in (MARKE_GESUNDHEIT, MARKE_HINWEIS):
        if anzeige.startswith(marke):
            return anzeige[len(marke):]
    return anzeige


def _profil_wert(profile, name: str, schluessel: str):
    """Eintrag `schluessel` einer Schutzstufe (dict wie muster.PROFILE oder Objekt mit Attribut), sonst None."""
    eintrag = profile.get(name) if isinstance(profile, dict) else None
    if isinstance(eintrag, dict):
        return eintrag.get(schluessel)
    return getattr(eintrag, schluessel, None)


_NEUE_KATEGORIEN = bool(_KATEGORIE_SCHLUESSEL & {"beruf", "arbeitgeber", "diagnose", "medikament"})


def _texte_zur_engine(neue_kategorien: bool) -> tuple[str, str, str]:
    """Untertitel, Hinweiskasten und Hilfetext – wahrheitsgemäß für den Funktionsumfang der Engine (GR-09)."""
    if neue_kategorien:
        lesbar = "je nach Schutzstufe bleiben Diagnosen, Beruf, Arbeitgeber, Beträge und Orte lesbar"
        kasten = ("Nur je nach Schutzstufe erkannt: Diagnosen, Beruf, Arbeitgeber. Nicht erkannt und nicht geschwärzt "
                  "werden: Gesichter/Lichtbilder (z. B. auf Ausweiskopien), Unterschriften, Handschrift, Freitext; "
                  "Text in Bildern nur unsicher (OCR).")
        grenzen_kopf = "NICHT oder nur teilweise erkannt werden:\n"
        grenzen_umfang = ("  • Diagnosen, Krankheiten, Medikamente: nur bekannte Begriffe, angehakt erst in der "
                          "Schutzstufe „Maximal“ (sonst gemeldet und nicht angehakt in der Fundliste angeboten, "
                          "Zeichen ⚕)\n"
                          "  • Beruf, Arbeitgeber: nur mit Etikett oder Personenbezug (ab Schutzstufe „Hoch“); "
                          "Einkommen und Familienstand nicht\n")
    else:
        lesbar = "Diagnosen, Beruf, Arbeitgeber, Beträge und Orte bleiben lesbar"
        kasten = ("Nicht erkannt werden: Diagnosen, Beruf, Arbeitgeber, Gesichter/Lichtbilder (z. B. auf "
                  "Ausweiskopien), Unterschriften, Handschrift, Freitext; Text in Bildern nur unsicher (OCR).")
        grenzen_kopf = "NICHT erkannt werden:\n"
        grenzen_umfang = ("  • Diagnosen, Krankheiten, ICD-Codes, Medikamente\n"
                          "  • Beruf, Arbeitgeber, Einkommen, Familienstand\n")
    untertitel = ("Ersetzt direkte Identifikatoren (Namen, IBAN, Adresse, Telefon …) durch Platzhalter wie "
                  f"[PERSON A] – eine Pseudonymisierung, keine vollständige Anonymisierung: {lesbar}. "
                  "Fundliste und Ergebnis müssen vor jeder Weitergabe geprüft werden.")
    hinweis = (kasten + " Ausgaben in Cloud-Ordnern (OneDrive, Dropbox …) werden mitsynchronisiert. "
               "Mehr: Hilfe → „Was wird nicht erkannt?“")
    grenzen = (
        "Das Programm ersetzt direkte Identifikatoren durch Platzhalter (Pseudonymisierung).\n\n"
        + grenzen_kopf + grenzen_umfang +
        "  • Gesichter und Lichtbilder (z. B. das Passfoto auf einer Ausweiskopie) – sie werden NICHT geschwärzt\n"
        "  • Unterschriften, Stempel, Handschrift\n"
        "  • Text in Bildern, Fotos und Logos wird per OCR nur unsicher gelesen (Handyfotos, geringe Auflösung)\n"
        "  • Freitext, aus dem eine Person erkennbar bleibt\n"
        "  • Dateinamen (die Ausgabe heißt neutral anonym_01.pdf; der Originalname steht in _zuordnung.txt)\n\n"
        "Deshalb: jede Ausgabe in der Vorschau prüfen (Doppelklick auf die Datei). Was dort noch zu sehen ist, "
        "per Klick oder Rahmen nachschwärzen.\n\n"
        "Pseudonymisierte Dokumente bleiben personenbezogene Daten. Für die Weitergabe an einen KI-Dienst "
        "braucht es weiterhin eine Rechtsgrundlage und in der Regel einen Auftragsverarbeitungsvertrag. Die "
        "Verantwortung für die Weitergabe bleibt bei Ihnen (Hilfe → „Hinweise vor der Nutzung …“).\n\n"
        "Fotos und Bild-Scans (JPEG, PNG, TIFF, BMP, PNM) werden auf Wunsch in eine PDF umgewandelt und per "
        "Texterkennung gelesen. Gesichter, Lichtbilder, Unterschriften und Handschrift darauf werden NICHT "
        "geschwärzt: in der Vorschau unter „Geplante Schwärzung“ einen Rahmen darüber ziehen. Die Ausgabe eines "
        "Fotos muss deshalb immer in der Vorschau freigegeben werden („_PRUEFEN“). "
        "PDFs mit Kennwort werden nach Eingabe des Kennworts geprüft – die Ausgabe hat "
        "dann kein Kennwort mehr. Die umgewandelte bzw. entschlüsselte Arbeitskopie liegt nur während der "
        "Bearbeitung im Programmordner für Zwischendateien und wird beim Entfernen aus der Liste und beim Beenden "
        "gelöscht. Andere Dateien (Word, Mails …) werden nicht geprüft: zuerst als PDF speichern.\n\n"
        "Ausgaben in Ordnern, die mit OneDrive, Dropbox o. Ä. synchronisiert werden, landen ebenfalls in der "
        "Cloud. Per Dateidialog geöffnete Dateien merkt sich Windows unter „Zuletzt verwendet“."
    )
    return untertitel, hinweis, grenzen


UNTERTITEL, HINWEISKASTEN, GRENZEN_TEXT = _texte_zur_engine(_NEUE_KATEGORIEN)


# ----------------------------------------------------------------------
# Engine-Aufruf: Fähigkeiten, Ergebnisprüfung, Meldungs-Codes
# ----------------------------------------------------------------------
def _parameter(funktion) -> set | None:
    """Parameternamen einer Engine-Funktion; None, wenn sie beliebige Schlüsselwörter annimmt."""
    try:
        parameter = inspect.signature(funktion).parameters
    except (TypeError, ValueError):
        return None
    if any(p.kind is p.VAR_KEYWORD for p in parameter.values()):
        return None
    return set(parameter)


def kann(funktion, name: str) -> bool:
    """Kennt die Engine-Funktion den (neuen, optionalen) Parameter? Pflichtparameter aus Phase 1 werden
    immer direkt übergeben – ein umbenannter Parameter führt zu einem sichtbaren Fehler, nie zu Stille."""
    parameter = _parameter(funktion)
    return parameter is None or name in parameter


class Vertragsfehler(RuntimeError):
    """Die Engine hat ein Ergebnis geliefert, das nicht dem Vertrag entspricht."""


ANALYSE_PFLICHT = ("datei", "funde", "warnungen", "hinweise", "fehler", "seiten", "ocr_seiten", "ocr_cache")
FUND_PFLICHT = ("kategorie", "anzeige", "text", "ersatz", "seiten", "anzahl", "kontext")
SCHWAERZ_PFLICHT = ("ausgabe", "treffer", "warnungen", "hinweise", "reste", "fehler")


def _analyse_ergebnis_pruefen(ergebnis, pdf: Path) -> dict:
    """Prüft das Analyse-Ergebnis streng (KQ-07): fehlende Pflichtschlüssel sind ein Fehler, keine
    stille Entwarnung („0 Funde“)."""
    if not isinstance(ergebnis, dict):
        raise Vertragsfehler(f"analysiere_pdf lieferte {type(ergebnis).__name__} statt dict")
    fehlend = [k for k in ANALYSE_PFLICHT if k not in ergebnis]
    if fehlend:
        raise Vertragsfehler("analysiere_pdf: Ergebnis ohne " + ", ".join(fehlend))
    if not isinstance(ergebnis["funde"], list):
        raise Vertragsfehler("analysiere_pdf: „funde“ ist keine Liste")
    for nummer, fund in enumerate(ergebnis["funde"], 1):
        fehlend = [k for k in FUND_PFLICHT if k not in fund]
        if fehlend:
            raise Vertragsfehler(f"analysiere_pdf: Fund {nummer} ohne " + ", ".join(fehlend))
    ergebnis["datei"] = Path(ergebnis["datei"])
    ergebnis["warnungen"] = [str(w) for w in ergebnis["warnungen"] or []]
    ergebnis["hinweise"] = [str(h) for h in ergebnis["hinweise"] or []]
    return ergebnis


def _schwaerz_ergebnis_pruefen(ergebnis, pdf: Path) -> dict:
    if not isinstance(ergebnis, dict):
        raise Vertragsfehler(f"schwaerze_pdf lieferte {type(ergebnis).__name__} statt dict")
    fehlend = [k for k in SCHWAERZ_PFLICHT if k not in ergebnis]
    if fehlend:
        raise Vertragsfehler("schwaerze_pdf: Ergebnis ohne " + ", ".join(fehlend))
    if ergebnis["ausgabe"] is not None:
        ergebnis["ausgabe"] = Path(ergebnis["ausgabe"])
    ergebnis.setdefault("original", pdf)
    ergebnis["warnungen"] = [str(w) for w in ergebnis["warnungen"] or []]
    ergebnis["hinweise"] = [str(h) for h in ergebnis["hinweise"] or []]
    ergebnis["reste"] = [str(r) for r in ergebnis["reste"] or []]
    return ergebnis


def _fehler_ergebnis(pdf: Path, text: str) -> dict:
    """Analyse-Ergebnis für eine Datei, deren Analyse mit einer Ausnahme endete."""
    return {"datei": pdf, "funde": [], "warnungen": [], "hinweise": [], "fehler": text, "seiten": 0,
            "ocr_seiten": 0, "ocr_cache": {}}


def meldungs_codes(ergebnis: dict) -> set[str]:
    """Codes der strukturierten Meldungen (12.6). Liefert die Engine keine "meldungen", leitet die Attrappe
    sie aus den Texten ab – Entscheidungen der Oberfläche hängen nur an Codes (KQ-08)."""
    meldungen = ergebnis.get("meldungen")
    if meldungen is None:
        meldungen = attrappen.meldungen_aus_texten(ergebnis)
    return {str(m.get("code")) for m in meldungen if isinstance(m, dict) and m.get("code")}


# ----------------------------------------------------------------------
# Texte für den Nutzer
# ----------------------------------------------------------------------
_FEHLERTEXT_MUSTER = (
    (("permission denied", "zugriff verweigert", "errno 13", "winerror 5]", "winerror 32]",
      "used by another process", "von einem anderen prozess verwendet", "cannot remove file", "errno 1]",
      "errno 30]", "read-only file system"),
     "Ausgabedatei konnte nicht geschrieben werden – vermutlich ist sie in einem anderen Programm (PDF-Reader) "
     "geöffnet oder der Ordner ist schreibgeschützt. Bitte die Datei schließen oder einen anderen Zielordner "
     "wählen und erneut schwärzen."),
    (("file exists", "errno 17]", "winerror 183]", "bereits vorhanden", "not a directory", "errno 20]",
      "winerror 267]"),
     "Im Zielordner liegt bereits eine Datei mit dem Namen des Ausgabeordners („anonymisiert“) – bitte "
     "umbenennen oder einen anderen Zielordner wählen."),
    (("no space left", "errno 28]", "winerror 112]", "nicht genügend speicherplatz"),
     "Kein Speicherplatz mehr auf dem Laufwerk – bitte Platz schaffen oder anderen Zielordner wählen."),
    (("winerror 206]", "winerror 3]", "errno 36]", "file name too long"),
     "Der Dateipfad ist zu lang für Windows – bitte den Ordner näher an C:\\ kopieren oder einen kurzen "
     "Zielordner wählen."),
    (("as type pdf", "cannot open empty file", "no objects found", "not a pdf", "format error"),
     "Die Datei ist keine lesbare PDF-Datei (beschädigt, leer oder nur umbenannt) – bitte neu aus dem "
     "Ursprungsprogramm als PDF speichern."),
)


def _fehlertext_verstaendlich(text: str) -> str:
    """Übersetzt eine Fehlermeldung der Engine (auch deutsche Windows-Systemtexte) in eine Handlungsanweisung;
    die Systemmeldung bleibt gekürzt in Klammern erhalten (GR-04)."""
    tl = (text or "").lower()
    for muster, meldung in _FEHLERTEXT_MUSTER:
        if any(m in tl for m in muster):
            kurz = text if len(text) <= 120 else text[:117] + "…"
            return f"{meldung} (Systemmeldung: {kurz})"
    return text


def _verstaendliche_fehlermeldung(fehler: BaseException, pfad: Path | None = None) -> str:
    """Übersetzt eine Ausnahme in eine Handlungsanweisung."""
    text = str(fehler)
    if isinstance(fehler, PermissionError):
        return _FEHLERTEXT_MUSTER[0][1]
    if isinstance(fehler, (FileExistsError, NotADirectoryError)):
        return _FEHLERTEXT_MUSTER[1][1]
    if isinstance(fehler, OSError) and getattr(fehler, "errno", None) == errno.ENOSPC:
        return _FEHLERTEXT_MUSTER[2][1]
    if pfad is not None and sys.platform == "win32" and len(str(pfad)) > 240:
        return _FEHLERTEXT_MUSTER[3][1]
    uebersetzt = _fehlertext_verstaendlich(text)
    if uebersetzt != text:
        return uebersetzt
    return f"Unerwarteter Fehler ({type(fehler).__name__}: {text[:200]}) – Details stehen in fehler.log."


def _kontext_anzeige(kontext: str) -> str:
    """Kürzt den Vorlauf vor dem Fund, damit in der schmalen Kontextspalte der Fund selbst zu sehen ist (GR-05)."""
    kontext = str(kontext or "").replace("\n", " ")
    pos = kontext.find("»")
    if pos > KONTEXT_VORLAUF:
        return "…" + kontext[pos - KONTEXT_VORLAUF:].lstrip()
    return kontext


def _seitenzahl(pdf: Path) -> int:
    """Seitenzahl für den Fortschrittsbalken (1, wenn das PDF nicht lesbar ist – oder gar keine PDF, R-01)."""
    if not dateien.fuer_engine_erlaubt(dateien.datei_art(pdf)):
        return 1
    try:
        with fitz.open(pdf) as doc:
            return max(1, len(doc))
    except Exception:
        return 1


def _profil_name(name: str) -> str:
    return attrappen.PROFIL_ANZEIGE.get(name, name)


def _kuerzel_index(text: str, buchstabe: str) -> int:
    """Stelle des Kürzel-Buchstabens im Knopftext (für underline); -1, wenn er fehlt."""
    return text.lower().find(buchstabe.lower())


# Hilfetexte der Engine nennen „Installieren.bat“ – in der EXE gibt es die nicht (M-70)
_EXE_ERSETZUNGEN = (
    ("Der Ordner »tessdata« mit deu.traineddata muss neben dem Programm liegen",
     "Die Datei deu.traineddata muss im Programmordner unter _internal\\tessdata liegen"),
    ("(Installieren.bat erneut ausführen)",
     "(bitte den Programmordner vollständig neu entpacken bzw. eine neue ZIP-Datei anfordern; ggf. die "
     "Quarantäne des Virenscanners prüfen)"),
    ("Installieren.bat erneut ausführen",
     "bitte den Programmordner vollständig neu entpacken bzw. eine neue ZIP-Datei anfordern"),
    ("Bitte einmal 'Installieren.bat' ausführen",
     "Bitte den Programmordner vollständig neu entpacken bzw. eine neue ZIP-Datei anfordern"),
    ("Installieren.bat", "eine neue ZIP-Datei des Programms (neu entpacken)"),
)


def _text_fuer_exe(text: str) -> str:
    """In der EXE (sys.frozen) führen Hinweise auf Installieren.bat ins Leere: dort heißt die Abhilfe „Programmordner
    neu entpacken“. Im Skriptbetrieb bleibt der Text unverändert."""
    if not getattr(sys, "frozen", False) or not text or ("Installieren.bat" not in text and "tessdata" not in text):
        return text
    for alt, neu in _EXE_ERSETZUNGEN:
        text = text.replace(alt, neu)
    return text


_LANGPFAD_PRAEFIX = "\\\\?\\"            # „\\?\“ vor langen Windows-Pfaden (R-09)


def _anzeigetext(text: str) -> str:
    """Text für Protokoll und Dialoge: EXE-gerechte Hilfetexte (M-70), ohne das Präfix langer Windows-Pfade."""
    text = _text_fuer_exe(text)
    if text and _LANGPFAD_PRAEFIX in text:
        text = text.replace(_LANGPFAD_PRAEFIX + "UNC\\", "\\\\").replace(_LANGPFAD_PRAEFIX, "")
    return text


def _nebenkanal_bezug(ergebnis: dict) -> dict | None:
    """Personenbezogene Daten nur in Nebenkanälen (Metadaten, Lesezeichen, Anhänge, XFA – R-04, Paket
    analyse-status): {"metadaten", "lesezeichen", "anhaenge", "xfa", "personenbezug"} oder None."""
    nk = ergebnis.get("nebenkanaele") if isinstance(ergebnis, dict) else None
    if isinstance(nk, dict) and nk.get("personenbezug"):
        return nk
    if isinstance(ergebnis, dict) and "NEBENKANAL_FUND" in meldungs_codes(ergebnis):
        return nk if isinstance(nk, dict) else {"personenbezug": True}
    return None


def _nebenkanal_text(nk: dict) -> str:
    """„Metadaten (2), Anhänge (1)“ – wo die Daten stehen (ohne Inhalte)."""
    teile = []
    for schluessel, name in NEBENKANAL_NAMEN:
        wert = nk.get(schluessel)
        if isinstance(wert, bool):
            if wert:
                teile.append(name)
        elif isinstance(wert, (int, float)) and wert:
            teile.append(f"{name} ({int(wert)})")
    return ", ".join(teile) or "Metadaten/Anhänge"


def programm_symbol_png(groesse: int) -> bytes:
    """Programmsymbol als PNG (groesse × groesse Pixel, durchsichtiger Hintergrund), mit PyMuPDF gezeichnet: ein
    Blatt mit umgeknickter Ecke, schwarzen Balken (geschwärzte Stellen) und grauen Textzeilen. Dieselbe Zeichnung
    schreibt werkzeuge/programmsymbol.py in icon.ico (EXE und Desktop-Verknüpfung). Ganzzahlige Kanten, damit
    das Symbol auch mit 16 Pixeln scharf bleibt."""
    n = int(groesse)
    doc = fitz.open()
    try:
        seite = doc.new_page(width=n, height=n)
        blau, weiss, schwarz = (0.10, 0.37, 0.71), (1, 1, 1), (0.07, 0.09, 0.15)
        grau, hell = (0.61, 0.64, 0.69), (0.86, 0.91, 0.97)
        x0, y0 = round(n * 0.15), round(n * 0.06)
        x1, y1 = n - x0, n - y0
        rand = max(1, round(n / 24))
        ecke = max(3, round(n * 0.24))
        form = seite.new_shape()
        aussen = [(x0, y0), (x1 - ecke, y0), (x1, y0 + ecke), (x1, y1), (x0, y1), (x0, y0)]
        form.draw_polyline([fitz.Point(p) for p in aussen])
        form.finish(color=None, fill=blau, closePath=True)
        innen = [(x0 + rand, y0 + rand), (x1 - ecke - rand * 0.4, y0 + rand), (x1 - rand, y0 + ecke + rand * 0.4),
                 (x1 - rand, y1 - rand), (x0 + rand, y1 - rand), (x0 + rand, y0 + rand)]
        form.draw_polyline([fitz.Point(p) for p in innen])
        form.finish(color=None, fill=weiss, closePath=True)
        knick = [(x1 - ecke, y0), (x1 - ecke, y0 + ecke), (x1, y0 + ecke), (x1 - ecke, y0)]
        form.draw_polyline([fitz.Point(p) for p in knick])
        form.finish(color=None, fill=blau if n < 48 else hell, closePath=True)
        if n >= 48:
            form.draw_polyline([fitz.Point(p) for p in knick])
            form.finish(color=blau, width=rand, closePath=True)
        # Zeilen: schwarze Balken im Wechsel mit grauen Textzeilen (bei 16 Pixeln nur Balken)
        innen_x0, innen_x1 = x0 + rand + max(1, round(n * 0.07)), x1 - rand - max(1, round(n * 0.07))
        hoehe = max(2, round(n * 0.085))
        abstand = max(1, round(n * 0.065))
        y = y0 + ecke + abstand
        breiten = (1.0, 0.8, 0.9, 0.65, 1.0)
        for nr, anteil in enumerate(breiten):
            if y + hoehe > y1 - rand - max(1, round(n * 0.05)):
                break
            balken = n < 32 or nr % 2 == 0
            ende = innen_x0 + round((innen_x1 - innen_x0) * anteil)
            zeile_h = hoehe if balken else max(1, round(hoehe * 0.45))
            versatz = 0 if balken else (hoehe - zeile_h) // 2
            form.draw_rect(fitz.Rect(innen_x0, y + versatz, ende, y + versatz + zeile_h))
            form.finish(color=None, fill=schwarz if balken else grau)
            y += hoehe + abstand
        form.commit()
        return seite.get_pixmap(alpha=True).tobytes("png")
    finally:
        doc.close()


# ----------------------------------------------------------------------
# Dialog: Spalten der Kundenliste zuordnen
# ----------------------------------------------------------------------
class SpaltenDialog:
    """Zuordnung der CSV-Spalten zu Merkmalen der Kundenliste, wenn die Kopfzeile nicht erkannt wurde.
    Nicht blockierend: fertig(spalten) wird mit {merkmal: spaltenname | spaltenindex} aufgerufen."""

    NICHT = "— nicht verwenden —"

    def __init__(self, app, csv_pfad: Path, vorschau: dict, fertig):
        self.app = app
        self.fertig = fertig
        self.zeilen = vorschau["zeilen"]
        self.merkmale = dict(getattr(sys.modules.get(Kundenliste.__module__), "MERKMALE", None)
                             or attrappen.MERKMALE)
        breite = max((len(z) for z in self.zeilen), default=0)
        self.fenster = tk.Toplevel(app.root)
        self.fenster.title("Kundenliste – Spalten zuordnen")
        self.fenster.configure(bg=FARBE_KARTE)
        self.fenster.transient(app.root)
        rahmen = tk.Frame(self.fenster, bg=FARBE_KARTE, padx=14, pady=10)
        rahmen.pack(fill="both", expand=True)
        tk.Label(rahmen, text=f"Die Spalten von „{csv_pfad.name}“ wurden nicht erkannt. Bitte angeben, was in "
                              "welcher Spalte steht – mindestens Name, Nachname, Kundennummer, IBAN oder E-Mail.",
                 font=app.f_normal, bg=FARBE_KARTE, wraplength=app._px(560), justify="left").pack(anchor="w")
        erste = self.zeilen[0] if self.zeilen else []
        kopf_vermutet = len(self.zeilen) > 1 and not any(ch.isdigit() for ch in "".join(erste))
        self.kopf_var = tk.BooleanVar(value=kopf_vermutet)
        tk.Checkbutton(rahmen, text="Erste Zeile enthält Spaltenüberschriften (wird nicht importiert)",
                       variable=self.kopf_var, font=app.f_normal, bg=FARBE_KARTE,
                       activebackground=FARBE_KARTE).pack(anchor="w", pady=(6, 4))
        gitter = tk.Frame(rahmen, bg=FARBE_KARTE)
        gitter.pack(fill="x")
        auswahl = [self.NICHT] + list(self.merkmale.values())
        vorschlag = attrappen.spalten_erkennen(erste) if kopf_vermutet else {}
        index_zu_merkmal = {i: m for m, i in vorschlag.items()}
        self.boxen: list[ttk.Combobox] = []
        for i in range(breite):
            beispiele = [z[i] for z in self.zeilen[:4] if i < len(z) and z[i]]
            tk.Label(gitter, text=f"Spalte {i + 1}", font=app.f_fett, bg=FARBE_KARTE).grid(
                row=i, column=0, sticky="w", padx=(0, 8), pady=1)
            text = " · ".join(beispiele)[:60] or "(leer)"
            tk.Label(gitter, text=text, font=app.f_normal, bg=FARBE_KARTE, fg=FARBE_TEXT_GRAU,
                     anchor="w", width=36).grid(row=i, column=1, sticky="w", padx=(0, 8))
            box = ttk.Combobox(gitter, values=auswahl, state="readonly", width=28)
            box.set(self.merkmale.get(index_zu_merkmal.get(i), self.NICHT))
            box.grid(row=i, column=2, sticky="w")
            self.boxen.append(box)
        self.meldung = tk.Label(rahmen, text="", font=app.f_normal, bg=FARBE_KARTE, fg=FARBE_ROT,
                                wraplength=app._px(560), justify="left")
        self.meldung.pack(anchor="w", pady=(6, 0))
        knoepfe = tk.Frame(rahmen, bg=FARBE_KARTE)
        knoepfe.pack(fill="x", pady=(8, 0))
        self.ok_knopf = app._knopf(knoepfe, "Importieren", self.bestaetigen)
        self.ok_knopf.pack(side="right")
        app._knopf(knoepfe, "Abbrechen", self.abbrechen, True).pack(side="right", padx=(0, 8))
        self.fenster.protocol("WM_DELETE_WINDOW", self.abbrechen)

    def zuordnung(self) -> dict | None:
        """{merkmal: spaltenname (mit Kopfzeile) | spaltenindex (ohne)} oder None (Meldung im Dialog)."""
        name_zu_merkmal = {v: k for k, v in self.merkmale.items()}
        gewaehlt: dict[str, int] = {}
        for i, box in enumerate(self.boxen):
            merkmal = name_zu_merkmal.get(box.get())
            if merkmal is None:
                continue
            if merkmal in gewaehlt:
                self.meldung.config(text=f"„{box.get()}“ ist mehreren Spalten zugeordnet – bitte nur einer.")
                return None
            gewaehlt[merkmal] = i
        if not any(m in gewaehlt for m in attrappen.STARKE_MERKMALE):
            self.meldung.config(text="Bitte mindestens eine Spalte mit Name, Nachname, Kundennummer, IBAN oder "
                                     "E-Mail zuordnen – sonst kann kein Kunde sicher erkannt werden.")
            return None
        if not self.kopf_var.get():
            return gewaehlt
        kopf = self.zeilen[0] if self.zeilen else []
        namen = {}
        for merkmal, i in gewaehlt.items():
            name = kopf[i] if i < len(kopf) else ""
            if not name or kopf.count(name) > 1:
                self.meldung.config(text="Die Spaltenüberschriften sind leer oder doppelt – bitte in der CSV-Datei "
                                         "eindeutige Überschriften vergeben oder „Erste Zeile enthält "
                                         "Spaltenüberschriften“ abwählen.")
                return None
            namen[merkmal] = name
        return namen

    def bestaetigen(self):
        spalten = self.zuordnung()
        if spalten is None:
            return
        self.fenster.destroy()
        self.fertig(spalten)

    def abbrechen(self):
        self.fenster.destroy()


# ----------------------------------------------------------------------
# Hauptknopf mit sichtbarem gesperrten Zustand (Punkt 12)
# ----------------------------------------------------------------------
class PrimaerKnopf(tk.Button):
    """Blauer Hauptknopf. Gesperrt wird er grau mit dunkelgrauer Schrift – vorher blieb er blau und sah wie
    „bereit“ aus. Die Farbe folgt jedem config(state=…), auch aus Vorschau und Tests."""

    def _farben(self, zustand):
        gesperrt = str(zustand) == "disabled"
        tk.Button.configure(self, bg=FARBE_KNOPF_GESPERRT if gesperrt else FARBE_AKZENT,
                            cursor="arrow" if gesperrt else "hand2")

    def configure(self, cnf=None, **kw):
        ergebnis = tk.Button.configure(self, cnf, **kw)
        zustand = kw.get("state", cnf.get("state") if isinstance(cnf, dict) else None)
        if zustand is not None:
            self._farben(zustand)
        return ergebnis

    config = configure

    def __setitem__(self, schluessel, wert):
        self.configure({schluessel: wert})


# ----------------------------------------------------------------------
# Dialoge: Kennwort (R-12), Hinweis beim ersten Start (M-19)
# ----------------------------------------------------------------------
def _modal_machen(fenster):
    """Dialog vor das Hauptfenster legen und Eingaben dorthin lenken (grab erst, wenn das Fenster sichtbar ist)."""
    def greifen(versuche=20):
        try:
            if fenster.winfo_exists():
                fenster.grab_set()
        except tk.TclError:
            if versuche:
                fenster.after(50, greifen, versuche - 1)
    try:
        fenster.lift()
        fenster.focus_force()
    except tk.TclError:
        pass
    greifen()


class KennwortDialog:
    """Fragt das Kennwort einer geschützten PDF ab – maskiert, nur für diesen Augenblick im Speicher (nie
    gespeichert oder protokolliert). ergebnis: das Kennwort oder None (Überspringen)."""

    def __init__(self, app, name: str, fehlversuch: bool = False):
        self.app = app
        self.ergebnis: str | None = None
        self._fertig = False
        f = self.fenster = tk.Toplevel(app.root)
        f.title(KENNWORT_TITEL)
        f.configure(bg=FARBE_KARTE)
        f.resizable(False, False)
        try:
            f.transient(app.root)
        except tk.TclError:
            pass
        rahmen = tk.Frame(f, bg=FARBE_KARTE, padx=16, pady=12)
        rahmen.pack(fill="both", expand=True)
        breite = app._px(420)
        tk.Label(rahmen, text=f"„{name}“ ist mit einem Kennwort geschützt.", font=app.f_fett, bg=FARBE_KARTE,
                 wraplength=breite, justify="left").pack(anchor="w")
        tk.Label(rahmen, text="Bitte das Kennwort zum Öffnen eingeben. Es wird nicht gespeichert. Die Ausgabedatei "
                              "wird OHNE Kennwort gespeichert – sie ist ja zur Weitergabe gedacht.",
                 font=app.f_normal, bg=FARBE_KARTE, fg=FARBE_TEXT_GRAU, wraplength=breite,
                 justify="left").pack(anchor="w", pady=(4, 8))
        self.fehler_label = tk.Label(rahmen, text="Das Kennwort ist falsch. Bitte erneut eingeben oder "
                                                  "„Überspringen“ wählen." if fehlversuch else "",
                                     font=app.f_fett, bg=FARBE_KARTE, fg=FARBE_ROT, wraplength=breite,
                                     justify="left")
        if fehlversuch:
            self.fehler_label.pack(anchor="w", pady=(0, 6))
        zeile = tk.Frame(rahmen, bg=FARBE_KARTE)
        zeile.pack(fill="x")
        tk.Label(zeile, text="Kennwort:", font=app.f_normal, bg=FARBE_KARTE).pack(side="left")
        self.var = tk.StringVar(master=f)
        self.eingabe = tk.Entry(zeile, textvariable=self.var, show="•", width=30, font=app.f_normal,
                                relief="flat", highlightthickness=1, highlightbackground=FARBE_RAND)
        self.eingabe.pack(side="left", fill="x", expand=True, padx=(8, 0))
        knoepfe = tk.Frame(rahmen, bg=FARBE_KARTE)
        knoepfe.pack(fill="x", pady=(12, 0))
        self.ok_knopf = app._knopf(knoepfe, "  Öffnen  ", self.ok, unterstrichen=2)
        self.ok_knopf.pack(side="right")
        self.ueberspringen_knopf = app._knopf(knoepfe, "Überspringen", self.abbrechen, True, unterstrichen=0)
        self.ueberspringen_knopf.pack(side="right", padx=(0, 8))
        f.bind("<Return>", lambda e: self.ok())
        f.bind("<KP_Enter>", lambda e: self.ok())
        f.bind("<Escape>", lambda e: self.abbrechen())
        f.protocol("WM_DELETE_WINDOW", self.abbrechen)
        self.eingabe.focus_set()

    def ok(self):
        if self._fertig:
            return
        self.ergebnis = self.var.get()
        self._schliessen()

    def abbrechen(self):
        if self._fertig:
            return
        self.ergebnis = None
        self._schliessen()

    def _schliessen(self):
        self._fertig = True
        try:
            self.var.set("")
            self.fenster.grab_release()
            self.fenster.destroy()
        except tk.TclError:
            pass

    def zeigen(self) -> str | None:
        """Blockiert (mit laufender Ereignisschleife), bis der Dialog geschlossen ist."""
        _modal_machen(self.fenster)
        try:
            self.eingabe.focus_force()
        except tk.TclError:
            pass
        try:
            self.app.root.wait_window(self.fenster)
        except tk.TclError:
            pass
        ergebnis, self.ergebnis = self.ergebnis, None
        return ergebnis


class HinweisDialog:
    """Hinweis beim ersten Start (M-19): Pseudonymisierung, Ergebnis immer ansehen, Verantwortung bleibt beim
    Makler. „Nicht mehr anzeigen“ ist vorbelegt – der Hinweis erscheint also einmal; über Hilfe → „Hinweise vor der
    Nutzung …“ ist er jederzeit wieder da."""

    def __init__(self, app):
        self.app = app
        self._fertig = False
        f = self.fenster = tk.Toplevel(app.root)
        f.title(ERSTSTART_TITEL)
        f.configure(bg=FARBE_KARTE)
        f.resizable(False, False)
        try:
            f.transient(app.root)
        except tk.TclError:
            pass
        rahmen = tk.Frame(f, bg=FARBE_KARTE, padx=18, pady=14)
        rahmen.pack(fill="both", expand=True)
        tk.Label(rahmen, text="Wichtig: Pseudonymisierung, keine vollständige Anonymisierung", font=app.f_karte,
                 bg=FARBE_KARTE, fg=FARBE_TEXT, wraplength=app._px(480), justify="left").pack(anchor="w")
        self.text_label = tk.Label(rahmen, text=ERSTSTART_TEXT, font=app.f_normal, bg=FARBE_KARTE, fg=FARBE_TEXT,
                                   wraplength=app._px(480), justify="left")
        self.text_label.pack(anchor="w", pady=(8, 10))
        self.nicht_mehr = tk.BooleanVar(master=f, value=True)
        tk.Checkbutton(rahmen, text="Nicht mehr anzeigen", variable=self.nicht_mehr, font=app.f_normal,
                       bg=FARBE_KARTE, activebackground=FARBE_KARTE, underline=0).pack(anchor="w")
        knoepfe = tk.Frame(rahmen, bg=FARBE_KARTE)
        knoepfe.pack(fill="x", pady=(10, 0))
        self.ok_knopf = app._knopf(knoepfe, "  Verstanden  ", self.bestaetigen, unterstrichen=2)
        self.ok_knopf.pack(side="right")
        f.bind("<Return>", lambda e: self.bestaetigen())
        f.bind("<Escape>", lambda e: self.bestaetigen())
        f.bind("<Alt-n>", lambda e: self.nicht_mehr.set(not self.nicht_mehr.get()))
        f.protocol("WM_DELETE_WINDOW", self.bestaetigen)
        _modal_machen(f)
        self.ok_knopf.focus_set()

    def bestaetigen(self):
        if self._fertig:
            return
        self._fertig = True
        self.app.hinweis_bestaetigt(bool(self.nicht_mehr.get()))
        try:
            self.fenster.grab_release()
            self.fenster.destroy()
        except tk.TclError:
            pass


# ----------------------------------------------------------------------
# Hauptfenster
# ----------------------------------------------------------------------
class AnonymisiererApp:
    """Hauptfenster: Dateien wählen, analysieren, Funde prüfen, schwärzen, in der Vorschau freigeben."""

    def __init__(self, root, einstellungen: dict | None = None, modell_vorladen: bool = False):
        self.root = root
        self.einstellungen = dict(einstellungen) if einstellungen is not None else dateien.einstellungen_laden()
        self.root.title(f"PDF-Anonymisierer {__version__}")
        self.root.configure(bg=FARBE_HINTERGRUND)

        self.dateien: list[Path] = []
        self.analyse_ergebnisse: dict[Path, dict] = {}   # Pfad -> Ergebnis von analysiere_pdf
        self.zeilen: dict[str, Path] = {}                # iid der Datei-Zeile -> Pfad
        self.beschriftungen: dict[str, str] = {}         # iid -> Anzeigename (relativ zum Stamm)
        self.manuell: dict[Path, dict[int, dict]] = {}   # Pfad -> {mid: manuelle Markierung aus der Vorschau}
        self._manuell_zaehler = 0
        self.lauf_immer: dict[Path, list[str]] = {}      # Pfad -> „überall in diesem Dokument schwärzen“
        self.ausgaben: dict[Path, dict] = {}             # Pfad -> {"pfad", "status", "verdacht", "ergebnis"}
        self.vorschauen: dict[Path, object] = {}         # Pfad -> offenes Vorschau-Fenster
        self.kundenliste = None
        self.laeuft = False
        self.lauf_art: str | None = None
        self.abbruch: threading.Event | None = None
        self.ocr = None
        self.analyse_veraltet = False
        self.warnungen_anzahl = 0
        self.letzte_ausgabeordner: list[Path] = []
        self.letzter_dialog: tuple | None = None         # (Art, Titel, Text) des letzten Dialogs
        self.laeufe_beendet = 0                          # Zähler abgeschlossener Läufe (für Tests/Skripte)
        self.beendet = False                             # Fenster wird geschlossen: keine Tk-Aufrufe mehr
        self.instanz_sperre = None                       # von main() gesetzt (Einzelinstanz, GR-10)
        self.basis_profil = attrappen.STANDARD_PROFIL
        self.vorladen_thread: threading.Thread | None = None
        self._ner_sperre = threading.Lock()              # lade_ner nie doppelt gleichzeitig (Vorladen/Analyse)
        self._hauptthread_fehler_gemeldet = False
        self._anpassung_laeuft = False
        self.dnd_aktiv = False
        self._sperrbar: list = []
        self._einstellungen_werden_gesetzt = False
        self._profil_wird_gesetzt = False
        self._anpassung_geplant = False
        self._alter_threading_haken = threading.excepthook
        # Arbeitskopien (Bild als PDF, entschlüsselte PDF, PDF ohne Endung): Original -> {"pfad", "art"}; die Engine
        # liest die Kopie, Liste, Ausgabeordner und Protokoll gehören zum Original
        self.arbeitskopien: dict[Path, dict] = {}
        self.nicht_geprueft: dict[Path, str] = {}        # Datei -> Grund (keine PDF, unlesbar, ohne Kennwort …)
        self._auswahl_ungeprueft: dict[Path, str] | None = None   # davon aus der gerade laufenden Auswahl
        self._hinzufuegen_laeuft = False
        # Schließen, während eine Auswahl auf eine Rückfrage wartet (Kennwort, Fotos …): erst die Auswahl sauber
        # abbrechen (keine weitere Arbeitskopie), dann schließen (Befund Runde 2)
        self._schliessen_angefordert = False
        self._lauf_thread: threading.Thread | None = None   # Arbeits-Thread des laufenden bzw. letzten Laufs
        self._reste_threads: dict[str, threading.Thread] = {}   # Sitzungsordner -> Thread, der ihn später löscht
        self.laufprotokoll: list[dict] = []              # je Lauf eine Zusammenfassung ohne Inhalte (M-61)
        self.ereignisse: list[tuple[str, str]] = []      # (Uhrzeit, Ereignis) – Freigeben/Verwerfen/Nachschwärzen
        self._lauf_kontext: dict | None = None
        self._nach_start: list = []                      # after()-Kennungen, die beim Schließen verworfen werden
        self._symbole: list = []
        self.hinweis_dialog = None
        self.kennwort_dialog = None
        self.hinweis_gelesen = bool(self.einstellungen.get("hinweis_gelesen", False))
        dateien.sitzung_beginnen()                        # Arbeitskopien dieses Fensters in einem neuen Ordner

        self.skalierung = float(self.root.tk.call("tk", "scaling"))
        self.k = self.skalierung / BASIS_SKALIERUNG     # 1.0 = Windows 100 %
        self._schriften_anlegen()
        self._geometrie_setzen()
        self._fenstersymbol_setzen()
        self._baue_oberflaeche()
        self._menue_anlegen()
        self._einstellungen_anwenden()
        self._kundenliste_laden()

        self.root.protocol("WM_DELETE_WINDOW", self.schliessen)
        self.root.report_callback_exception = self._fehler_melden
        threading.excepthook = self._thread_excepthook
        self.root.bind("<Configure>", self._fenster_geaendert)
        # Alt+Buchstabe (unterstrichen im Knopf); Großbuchstabe für Feststelltaste und Alt+Umschalt (M-67)
        for name, knopf in (("analyse", self.analyse_knopf), ("start", self.start_knopf),
                            ("vorschau", self.vorschau_knopf)):
            for taste in (KUERZEL[name], KUERZEL[name].upper()):
                self.root.bind(f"<Alt-{taste}>", lambda e, k=knopf: k.invoke())
        self.root.after_idle(self._oben_anpassen)
        if modell_vorladen:
            self._nach_start.append(self.root.after(VORLADEN_NACH_MS, self.modell_vorladen))

    # ------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------
    def _schriften_anlegen(self):
        self.f_normal = tkfont.Font(family=SCHRIFT, size=9)
        self.f_fett = tkfont.Font(family=SCHRIFT, size=9, weight="bold")
        self.f_titel = (SCHRIFT, 19, "bold")
        self.f_karte = (SCHRIFT, 11, "bold")
        self.f_knopf = (SCHRIFT, 10, "bold")
        self.f_mono = (SCHRIFT_MONO, 9)
        self.zeilenhoehe = self.f_normal.metrics("linespace")
        stil = ttk.Style(self.root)
        stil.configure("Treeview", font=self.f_normal, rowheight=max(20, self.zeilenhoehe + 6))
        stil.configure("Treeview.Heading", font=self.f_fett)

    def _px(self, wert: int) -> int:
        """Entwurfsmaß (bei 100 %) in Bildschirmpixel umrechnen."""
        return max(1, round(wert * self.k))

    def _fenstersymbol_setzen(self):
        """Programmsymbol für dieses und alle später geöffneten Fenster (Vorschau, Dialoge; M-27/M-67). Ein Fehler
        dabei darf den Start nie verhindern."""
        try:
            self._symbole = [tk.PhotoImage(master=self.root, format="png",
                                           data=base64.b64encode(programm_symbol_png(g)).decode("ascii"))
                             for g in SYMBOL_GROESSEN]
            self.root.iconphoto(True, *self._symbole)
        except Exception:
            self._symbole = []
            dateien.fehler_protokollieren(*sys.exc_info())

    def _geometrie_setzen(self):
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        breite = min(self._px(FENSTER_BREITE), max(FENSTER_MINDESTMASS[0], sw - 24))
        hoehe = min(self._px(FENSTER_HOEHE), max(FENSTER_MINDESTMASS[1], sh - FENSTER_RAND_UNTEN))
        self.root.minsize(*FENSTER_MINDESTMASS)
        geometrie = f"{breite}x{hoehe}"
        gespeichert = self.einstellungen.get("fenster")
        if isinstance(gespeichert, str):
            m = re.fullmatch(r"(\d+)x(\d+)(?:([+-]\d+)([+-]\d+))?", gespeichert)
            if m:
                b, h = int(m.group(1)), int(m.group(2))
                if FENSTER_MINDESTMASS[0] <= b <= sw and FENSTER_MINDESTMASS[1] <= h <= sh:
                    geometrie = f"{b}x{h}"
                    if m.group(3) and m.group(4):
                        x, y = int(m.group(3)), int(m.group(4))
                        if 0 <= x < sw - 100 and 0 <= y < sh - 100:
                            geometrie += f"+{x}+{y}"
        self.root.geometry(geometrie)
        self._start_hoehe = int(geometrie.split("x")[1].split("+")[0])
        # Kleine Bildschirme (Laptops mit 1366x768 oder hoher Skalierung): maximiert starten
        if sh - FENSTER_RAND_UNTEN < self._px(FENSTER_HOEHE) or self.einstellungen.get("maximiert"):
            self._maximieren()

    def _maximieren(self):
        try:
            self.root.state("zoomed")                   # Windows
        except tk.TclError:
            try:
                self.root.attributes("-zoomed", True)   # Linux-Fenstermanager
            except tk.TclError:
                pass

    def _ist_maximiert(self) -> bool:
        try:
            if self.root.state() == "zoomed":
                return True
        except tk.TclError:
            pass
        try:
            return bool(self.root.attributes("-zoomed"))
        except tk.TclError:
            return False

    def _baue_oberflaeche(self):
        haupt = tk.Frame(self.root, bg=FARBE_HINTERGRUND, padx=16, pady=10)
        haupt.pack(fill="both", expand=True)
        self.haupt = haupt

        self.kopf = tk.Frame(haupt, bg=FARBE_HINTERGRUND)
        self.kopf.pack(fill="x")
        tk.Label(self.kopf, text="PDF-Anonymisierer", font=self.f_titel,
                 bg=FARBE_HINTERGRUND, fg=FARBE_TEXT).pack(anchor="w")
        self.untertitel = tk.Label(self.kopf, text=UNTERTITEL, font=self.f_normal, bg=FARBE_HINTERGRUND,
                                   fg=FARBE_TEXT_GRAU, wraplength=self._px(840), justify="left")
        self.untertitel.pack(anchor="w", pady=(0, 6))

        # Unten verankert (zuerst packen, damit sie nie abgeschnitten werden): Aktionsleiste, Protokoll
        self._baue_aktionsleiste(haupt)
        self._baue_protokoll(haupt)

        # Oben: scrollbarer Bereich mit Schritt 1 und 2
        self.oben_rahmen = tk.Frame(haupt, bg=FARBE_HINTERGRUND)
        self.oben_rahmen.pack(fill="x")
        self.oben_canvas = tk.Canvas(self.oben_rahmen, bg=FARBE_HINTERGRUND, highlightthickness=0, bd=0)
        self.oben_roll = ttk.Scrollbar(self.oben_rahmen, orient="vertical", command=self.oben_canvas.yview)
        self.oben_canvas.configure(yscrollcommand=self.oben_roll.set)
        self.oben_canvas.pack(side="left", fill="x", expand=True)
        self.oben = tk.Frame(self.oben_canvas, bg=FARBE_HINTERGRUND)
        self._oben_fenster = self.oben_canvas.create_window((0, 0), window=self.oben, anchor="nw")
        self.oben.bind("<Configure>", lambda e: self._anpassung_planen())
        self.oben_canvas.bind("<Configure>",
                              lambda e: self.oben_canvas.itemconfigure(self._oben_fenster, width=e.width))
        self.root.bind_all("<MouseWheel>", self._mausrad, add="+")
        self.root.bind_all("<Button-4>", self._mausrad, add="+")
        self.root.bind_all("<Button-5>", self._mausrad, add="+")

        self._baue_karte_dateien(self.oben)
        self._baue_karte_kategorien(self.oben)

        # Schritt 3 füllt den Rest
        self._baue_karte_funde(haupt)

    def _baue_aktionsleiste(self, eltern):
        leiste = tk.Frame(eltern, bg=FARBE_KARTE, padx=12, pady=6,
                          highlightthickness=1, highlightbackground=FARBE_RAND)
        leiste.pack(side="bottom", fill="x", pady=(6, 0))
        self.aktionsleiste = leiste
        # Statuszeile in eigener Zeile über die volle Breite (GR-06): zwischen Knöpfen und Warnzähler
        # wurde sie abgeschnitten.
        self.status_label = tk.Label(leiste, text="Bereit.", font=self.f_normal, bg=FARBE_KARTE,
                                     fg=FARBE_TEXT_GRAU, anchor="w")
        self.status_label.pack(side="bottom", fill="x", pady=(2, 0))
        knoepfe = tk.Frame(leiste, bg=FARBE_KARTE)
        knoepfe.pack(side="top", fill="x")
        # Beide Hauptaktionen in der unten verankerten Leiste (GR-01): der Analysieren-Knopf lag im
        # scrollbaren Einstellbereich und war auf 1366x768 nur nach Scrollen erreichbar.
        self.analyse_knopf = self._knopf(knoepfe, ANALYSE_TEXT, self.analysieren,
                                         unterstrichen=_kuerzel_index(ANALYSE_TEXT, KUERZEL["analyse"]))
        self.analyse_knopf.pack(side="left")
        self.start_knopf = self._knopf(knoepfe, START_TEXT, self.schwaerzen,
                                       unterstrichen=_kuerzel_index(START_TEXT, KUERZEL["start"]))
        self.start_knopf.pack(side="left", padx=(8, 0))
        self.start_knopf.config(state="disabled")
        self.abbrechen_knopf = self._knopf(knoepfe, "Abbrechen", self.abbrechen, True)
        self.abbrechen_knopf.pack(side="left", padx=(8, 0))
        self.abbrechen_knopf.config(state="disabled")
        self.ordner_knopf = self._knopf(knoepfe, "Ergebnisordner öffnen", self.ergebnisordner_oeffnen, True)
        self.ordner_knopf.pack(side="left", padx=(8, 0))
        self.ordner_knopf.config(state="disabled")
        # Fortschritt und Warnzähler in eigener Zeile: in der Knopfzeile bekam der Balken bei breiten
        # Systemschriften (z. B. DejaVu Sans, 150 % Skalierung) keinen Platz mehr und verschwand.
        fortschritt_zeile = tk.Frame(leiste, bg=FARBE_KARTE)
        fortschritt_zeile.pack(side="top", fill="x", pady=(4, 0))
        self.warn_label = tk.Label(fortschritt_zeile, text="", font=self.f_fett, bg=FARBE_KARTE,
                                   fg=FARBE_WARNUNG)
        self.warn_label.pack(side="right", padx=(8, 0))
        self.fortschritt = ttk.Progressbar(fortschritt_zeile, mode="determinate")
        self.fortschritt.pack(side="left", fill="x", expand=True)

    def _baue_protokoll(self, eltern):
        rahmen = tk.Frame(eltern, bg=FARBE_KARTE, padx=8, pady=4,
                          highlightthickness=1, highlightbackground=FARBE_RAND)
        rahmen.pack(side="bottom", fill="x", pady=(6, 0))
        self.protokoll_rahmen = rahmen
        innen = tk.Frame(rahmen, bg=FARBE_KARTE)
        innen.pack(fill="x")
        self.protokoll = tk.Text(innen, height=PROTOKOLL_ZEILEN, width=40, font=self.f_mono, relief="flat",
                                 highlightthickness=1, highlightbackground=FARBE_RAND,
                                 bg="#fafafa", state="disabled", wrap="word")
        roll = ttk.Scrollbar(innen, orient="vertical", command=self.protokoll.yview)
        self.protokoll.configure(yscrollcommand=roll.set)
        self.protokoll.pack(side="left", fill="x", expand=True)
        roll.pack(side="right", fill="y")
        for stil, farbe in [("ok", FARBE_GRUEN), ("warnung", FARBE_WARNUNG), ("fehler", FARBE_ROT),
                            ("grau", FARBE_TEXT_GRAU), ("hinweis", FARBE_AKZENT), ("trenner", FARBE_TEXT_GRAU)]:
            self.protokoll.tag_configure(stil, foreground=farbe)

    def _baue_karte_dateien(self, eltern):
        karte1 = self._karte(eltern, "1 · PDF-Dateien")
        self.drop_zone = tk.Label(karte1, text="", font=(SCHRIFT, 10), bg=FARBE_AKZENT_HELL, fg=FARBE_AKZENT,
                                  height=1, pady=6, cursor="hand2", highlightthickness=2,
                                  highlightbackground="#b9cfee")
        self.drop_zone.pack(fill="x", pady=(2, 6))
        self.drop_zone.bind("<Button-1>", lambda e: self.dateien_waehlen())
        if DND_VERFUEGBAR and DND_FILES is not None:
            try:
                self.drop_zone.drop_target_register(DND_FILES)
                self.drop_zone.dnd_bind("<<Drop>>", self._drop_ereignis)
                self.dnd_aktiv = True
            except Exception:
                self.dnd_aktiv = False
        self.drop_zone.config(text="⬇  " + ("PDFs, Fotos oder ganze Ordner hierher ziehen  (oder klicken zum "
                                            "Auswählen)" if self.dnd_aktiv else
                                            "Drag & Drop nicht verfügbar – klicken zum Auswählen"))

        zeile = tk.Frame(karte1, bg=FARBE_KARTE)
        zeile.pack(fill="x")
        k1 = self._knopf(zeile, "Dateien auswählen …", self.dateien_waehlen, True)
        k1.pack(side="left")
        k2 = self._knopf(zeile, "Ordner auswählen …", self.ordner_waehlen, True)
        k2.pack(side="left", padx=(6, 0))
        k3 = self._knopf(zeile, "Liste leeren", self.liste_leeren, True)
        k3.pack(side="right")
        self._sperrbar += [k1, k2, k3]
        # Bericht zum Hinzufügen in eigener Zeile unter den Knöpfen, mit Umbruch (Breite folgt dem Fenster): in der
        # Knopfzeile wurde er abgeschnitten – genau „(nicht geprüft)“ war nicht mehr zu sehen (Befund Runde 2)
        self.datei_hinweis = tk.Label(karte1, text="Noch keine Dateien. Die Liste erscheint unten in Schritt 3.",
                                      font=self.f_normal, bg=FARBE_KARTE, fg=FARBE_TEXT_GRAU, anchor="w",
                                      justify="left", wraplength=self._px(840))
        self.datei_hinweis.pack(fill="x", pady=(4, 0))

        ziel = tk.Frame(karte1, bg=FARBE_KARTE)
        ziel.pack(fill="x", pady=(6, 0))
        self.zielordner_aktiv = tk.BooleanVar(value=False)
        self.zielordner_var = tk.StringVar(value="")
        zk = tk.Checkbutton(ziel, text="Alle Ergebnisse in einen gemeinsamen Zielordner:",
                            variable=self.zielordner_aktiv, font=self.f_normal, bg=FARBE_KARTE,
                            activebackground=FARBE_KARTE, anchor="w")
        zk.pack(side="left")
        self.zielordner_feld = tk.Entry(ziel, textvariable=self.zielordner_var, font=self.f_normal, width=28,
                                        relief="flat", highlightthickness=1, highlightbackground=FARBE_RAND)
        self.zielordner_feld.pack(side="left", fill="x", expand=True, padx=(6, 0))
        zb = self._knopf(ziel, "Wählen …", self.zielordner_waehlen, True)
        zb.pack(side="left", padx=(6, 0))
        self._sperrbar += [zk, self.zielordner_feld, zb]

        self.freigabe_var = tk.BooleanVar(value=True)
        fk = tk.Checkbutton(karte1, text="Freigabe vor Weitergabe erforderlich (Ausgaben heißen „_PRUEFEN“, bis "
                                         "sie in der Vorschau freigegeben sind – empfohlen)",
                            variable=self.freigabe_var, font=self.f_normal, bg=FARBE_KARTE,
                            activebackground=FARBE_KARTE, anchor="w", justify="left")
        fk.pack(fill="x", pady=(4, 0))
        self.freigabe_knopf = fk
        self._sperrbar.append(fk)

    def _baue_karte_kategorien(self, eltern):
        karte2 = tk.Frame(eltern, bg=FARBE_KARTE, padx=14, pady=8,
                          highlightthickness=1, highlightbackground=FARBE_RAND)
        karte2.pack(fill="x", pady=(0, 8))
        self.karte2 = karte2
        titelzeile = tk.Frame(karte2, bg=FARBE_KARTE)
        titelzeile.pack(fill="x", pady=(0, 2))
        tk.Label(titelzeile, text="2 · Was soll erkannt werden?", font=self.f_karte,
                 bg=FARBE_KARTE, fg=FARBE_TEXT).pack(side="left")
        tk.Label(titelzeile, text="→ danach unten „Analysieren“ drücken", font=self.f_normal,
                 bg=FARBE_KARTE, fg=FARBE_TEXT_GRAU).pack(side="right")

        # Schutzstufe (Profil) über den Kategorien: die Häkchen folgen der Stufe
        stufe = tk.Frame(karte2, bg=FARBE_KARTE)
        stufe.pack(fill="x", pady=(2, 0))
        tk.Label(stufe, text="Schutzstufe:", font=self.f_fett, bg=FARBE_KARTE).pack(side="left")
        self.profil_var = tk.StringVar(value=attrappen.STANDARD_PROFIL)
        self.profil_knoepfe: dict[str, tk.Radiobutton] = {}
        for name in attrappen.PROFIL_REIHENFOLGE + (attrappen.BENUTZERDEFINIERT,):
            rb = tk.Radiobutton(stufe, text=_profil_name(name), value=name, variable=self.profil_var,
                                command=self._profil_gewaehlt, font=self.f_normal, bg=FARBE_KARTE,
                                activebackground=FARBE_KARTE)
            rb.pack(side="left", padx=(8, 0))
            self.profil_knoepfe[name] = rb
            self._sperrbar.append(rb)
        self.profil_beschreibung = tk.Label(karte2, text="", font=self.f_normal, bg=FARBE_KARTE,
                                            fg=FARBE_TEXT_GRAU, anchor="w", justify="left",
                                            wraplength=self._px(820))
        self.profil_beschreibung.pack(fill="x", pady=(0, 4))

        gitter = tk.Frame(karte2, bg=FARBE_KARTE)
        gitter.pack(fill="x")
        self.kategorie_vars: dict[str, tk.BooleanVar] = {}
        for i, eintrag in enumerate(KATEGORIEN):
            schluessel, anzeige = eintrag[0], eintrag[1]
            standard = bool(eintrag[4]) if len(eintrag) > 4 else True
            var = tk.BooleanVar(value=standard)
            self.kategorie_vars[schluessel] = var
            cb = tk.Checkbutton(gitter, text=anzeige, variable=var, font=self.f_normal,
                                bg=FARBE_KARTE, activebackground=FARBE_KARTE, anchor="w")
            cb.grid(row=i // KATEGORIE_SPALTEN, column=i % KATEGORIE_SPALTEN, sticky="w", padx=(0, 12))
            self._sperrbar.append(cb)
            var.trace_add("write", self._kategorie_geaendert)
        for spalte in range(KATEGORIE_SPALTEN):
            gitter.columnconfigure(spalte, weight=1)

        listen = tk.Frame(karte2, bg=FARBE_KARTE)
        listen.pack(fill="x", pady=(8, 0))
        links = tk.Frame(listen, bg=FARBE_KARTE)
        links.pack(side="left", fill="both", expand=True, padx=(0, 8))
        rechts = tk.Frame(listen, bg=FARBE_KARTE)
        rechts.pack(side="left", fill="both", expand=True)
        tk.Label(links, text="Zusätzlich IMMER schwärzen (ein Begriff pro Zeile):",
                 font=self.f_fett, bg=FARBE_KARTE).pack(anchor="w")
        self.immer_feld = tk.Text(links, height=2, width=30, font=self.f_normal, relief="flat", undo=False,
                                  highlightthickness=1, highlightbackground=FARBE_RAND, bg="#fafafa")
        self.immer_feld.pack(fill="x")
        tk.Label(rechts, text="NIE schwärzen (z. B. eigene Firmen-/Beraternamen):",
                 font=self.f_fett, bg=FARBE_KARTE).pack(anchor="w")
        self.nie_feld = tk.Text(rechts, height=2, width=30, font=self.f_normal, relief="flat", undo=False,
                                highlightthickness=1, highlightbackground=FARBE_RAND, bg="#fafafa")
        self.nie_feld.pack(fill="x")
        for feld in (self.immer_feld, self.nie_feld):
            feld.bind("<<Modified>>", self._text_geaendert)
            self._sperrbar.append(feld)

        kunden = tk.Frame(karte2, bg=FARBE_KARTE)
        kunden.pack(fill="x", pady=(6, 0))
        tk.Label(kunden, text="Kundenliste:", font=self.f_fett, bg=FARBE_KARTE).pack(side="left")
        self.kunden_entfernen_knopf = self._knopf(kunden, "Entfernen", self.kundenliste_entfernen, True)
        self.kunden_entfernen_knopf.pack(side="right")
        self.kunden_import_knopf = self._knopf(kunden, "Importieren …", self.kundenliste_importieren, True)
        self.kunden_import_knopf.pack(side="right", padx=(0, 6))
        self._sperrbar.append(self.kunden_import_knopf)
        self.kunden_label = tk.Label(kunden, text="", font=self.f_normal, bg=FARBE_KARTE, fg=FARBE_TEXT_GRAU,
                                     anchor="w", justify="left")
        self.kunden_label.pack(side="left", padx=(8, 0), fill="x", expand=True)

    def _baue_karte_funde(self, eltern):
        karte3 = tk.Frame(eltern, bg=FARBE_KARTE, padx=14, pady=8,
                          highlightthickness=1, highlightbackground=FARBE_RAND)
        karte3.pack(fill="both", expand=True, pady=(0, 8))
        self.karte3 = karte3
        titelzeile = tk.Frame(karte3, bg=FARBE_KARTE)
        titelzeile.pack(fill="x")
        tk.Label(titelzeile, text="3 · Funde prüfen, dann schwärzen", font=self.f_karte,
                 bg=FARBE_KARTE, fg=FARBE_TEXT).pack(side="left")
        self.entfernen_knopf = self._knopf(titelzeile, "Datei aus Liste entfernen", self.datei_entfernen, True)
        self.entfernen_knopf.pack(side="right")
        b2 = self._knopf(titelzeile, "Alle aus", lambda: self.alle_setzen("aus"), True)
        b2.pack(side="right", padx=(0, 6))
        b1 = self._knopf(titelzeile, "Alle an", lambda: self.alle_setzen("an"), True)
        b1.pack(side="right", padx=(0, 6))
        self.vorschau_knopf = self._knopf(titelzeile, VORSCHAU_TEXT, self.vorschau_auswahl, True,
                                          unterstrichen=_kuerzel_index(VORSCHAU_TEXT, KUERZEL["vorschau"]))
        self.vorschau_knopf.pack(side="right", padx=(0, 6))
        self._sperrbar += [b1, b2, self.entfernen_knopf, self.vorschau_knopf]
        self.baum_hinweis = tk.Label(karte3, text=BAUM_HINWEIS, font=self.f_normal, bg=FARBE_KARTE,
                                     fg=FARBE_TEXT_GRAU, anchor="w", justify="left", wraplength=self._px(840))
        self.baum_hinweis.pack(anchor="w", fill="x")

        # Hinweiskasten zuerst unten verankern: wird das Fenster knapp, schrumpft die Fundliste, nicht der Hinweis
        self.hinweis_kasten = tk.Label(karte3, text=HINWEISKASTEN, font=self.f_normal, justify="left",
                                       anchor="w", bg=FARBE_HINWEIS_HINTERGRUND, fg="#7c4a03", padx=8, pady=3,
                                       highlightthickness=1, highlightbackground=FARBE_HINWEIS_RAND,
                                       wraplength=self._px(840))
        self.hinweis_kasten.pack(side="bottom", fill="x", pady=(2, 0))

        baum_rahmen = tk.Frame(karte3, bg=FARBE_KARTE)
        baum_rahmen.pack(fill="both", expand=True, pady=(2, 2))
        self.baum_rahmen = baum_rahmen
        baum_rahmen.rowconfigure(0, weight=1)
        baum_rahmen.columnconfigure(0, weight=1)
        self.baum = ttk.Treeview(baum_rahmen, columns=SPALTEN, show="tree headings",
                                 selectmode="browse", height=4)
        self.baum.heading("#0", text="Häkchen / Datei")
        self.baum.heading("kategorie", text="Kategorie")
        self.baum.heading("text", text="Gefundener Text")
        self.baum.heading("seiten", text="Seite(n)")
        self.baum.heading("anzahl", text="Anzahl")
        self.baum.heading("kontext", text="Kontext")
        self.baum.heading("ersatz", text="Ersatz")
        for spalte, (breite, mindest, dehnbar) in SPALTEN_MASSE.items():
            self.baum.column(spalte, width=self._px(breite), minwidth=self._px(mindest), stretch=dehnbar,
                             anchor="center" if spalte in ("seiten", "anzahl") else "w")
        roll_y = ttk.Scrollbar(baum_rahmen, orient="vertical", command=self.baum.yview)
        roll_x = ttk.Scrollbar(baum_rahmen, orient="horizontal", command=self.baum.xview)
        self.baum.configure(yscrollcommand=roll_y.set, xscrollcommand=roll_x.set)
        self.baum.grid(row=0, column=0, sticky="nsew")
        roll_y.grid(row=0, column=1, sticky="ns")
        roll_x.grid(row=1, column=0, sticky="ew")
        self.baum.tag_configure("aus", foreground=FARBE_TEXT_GRAU)
        self.baum.tag_configure("teil", foreground=FARBE_WARNUNG)
        self.baum.tag_configure("datei", font=self.f_fett)
        self.baum.bind("<Button-1>", self._baum_klick)
        self.baum.bind("<Double-Button-1>", self._baum_doppelklick)
        self.baum.bind("<Button-3>", self._kontextmenue)
        self.baum.bind("<space>", self._taste_leer)
        self.baum.bind("<Delete>", lambda e: self.datei_entfernen())
        self.baum.bind("<Return>", lambda e: self.vorschau_auswahl())
        self.baum.bind("<<TreeviewSelect>>", self._auswahl_geaendert)
        self.baum.bind("<Configure>", self._spalten_anpassen)

    def _spalten_anpassen(self, ereignis=None):
        """Dehnbare Spalten füllen die verfügbare Breite; reicht sie nicht, bleibt die Mindestbreite
        (dann hilft die horizontale Bildlaufleiste)."""
        try:
            verfuegbar = self.baum.winfo_width() - 4
        except tk.TclError:
            return
        if verfuegbar < 50:
            return
        fest = sum(self.baum.column(sp, "width") for sp, (_, _, dehnbar) in SPALTEN_MASSE.items() if not dehnbar)
        dehnbare = [sp for sp, (_, _, dehnbar) in SPALTEN_MASSE.items() if dehnbar]
        rest = verfuegbar - fest
        gesamt_entwurf = sum(SPALTEN_MASSE[sp][0] for sp in dehnbare)
        for sp in dehnbare:
            anteil = SPALTEN_MASSE[sp][0] / gesamt_entwurf
            breite = max(self._px(SPALTEN_MASSE[sp][1]), int(rest * anteil))
            self.baum.column(sp, width=breite)

    def _menue_anlegen(self):
        menue = tk.Menu(self.root)
        datei = tk.Menu(menue, tearoff=0)
        datei.add_command(label="Dateien hinzufügen …", command=self.dateien_waehlen, underline=0)
        datei.add_command(label="Ordner hinzufügen …", command=self.ordner_waehlen, underline=0)
        datei.add_separator()
        datei.add_command(label="Protokoll speichern …", command=self.protokoll_speichern, underline=0)
        datei.add_separator()
        datei.add_command(label="Beenden", command=self.schliessen, underline=0)
        menue.add_cascade(label="Datei", menu=datei, underline=0)
        kunden = tk.Menu(menue, tearoff=0)
        kunden.add_command(label="Kundenliste importieren …", command=self.kundenliste_importieren, underline=12)
        kunden.add_command(label="Kundenliste entfernen", command=self.kundenliste_entfernen, underline=12)
        menue.add_cascade(label="Kundenliste", menu=kunden, underline=0)
        hilfe = tk.Menu(menue, tearoff=0)
        hilfe.add_command(label="Hinweise vor der Nutzung …", command=self.hilfe_hinweis, underline=0)
        hilfe.add_command(label="Was wird nicht erkannt?", command=self.hilfe_grenzen, underline=0)
        hilfe.add_command(label="Ordner des Fehlerprotokolls öffnen", command=self.fehlerlog_oeffnen, underline=11)
        hilfe.add_separator()
        hilfe.add_command(label="Über PDF-Anonymisierer …", command=self.hilfe_ueber, underline=0)
        menue.add_cascade(label="Hilfe", menu=hilfe, underline=0)
        self.menue = menue
        self.datei_menue = datei
        self.kunden_menue = kunden
        self.hilfe_menue = hilfe
        try:
            self.root.config(menu=menue)
        except tk.TclError:
            pass

    # Oberflächen-Helfer ------------------------------------------------
    def _karte(self, eltern, titel, expand=False):
        rahmen = tk.Frame(eltern, bg=FARBE_KARTE, padx=14, pady=8,
                          highlightthickness=1, highlightbackground=FARBE_RAND)
        rahmen.pack(fill="both" if expand else "x", expand=expand, pady=(0, 8))
        tk.Label(rahmen, text=titel, font=self.f_karte, bg=FARBE_KARTE, fg=FARBE_TEXT).pack(anchor="w", pady=(0, 2))
        return rahmen

    def _knopf(self, eltern, text, befehl, sekundaer=False, unterstrichen: int = -1):
        """Knopf im Stil des Programms; unterstrichen = Index des Buchstabens für Alt+Buchstabe (-1: keiner)."""
        if sekundaer:
            knopf = tk.Button(eltern, text=text, command=befehl, font=self.f_normal,
                              bg="#eef1f5", fg=FARBE_TEXT, relief="flat", underline=unterstrichen,
                              padx=10, pady=3, cursor="hand2", activebackground="#dde3ea",
                              disabledforeground="#9ca3af")
        else:
            knopf = PrimaerKnopf(eltern, text=text, command=befehl, font=self.f_knopf,
                                 bg=FARBE_AKZENT, fg="white", relief="flat", padx=12, pady=6, cursor="hand2",
                                 activebackground="#134a8e", activeforeground="white", underline=unterstrichen,
                                 disabledforeground=FARBE_KNOPF_GESPERRT_TEXT)
        knopf.bind("<Return>", lambda e: knopf.invoke())
        return knopf

    def _anpassung_planen(self):
        if not self._anpassung_geplant:
            self._anpassung_geplant = True
            try:
                self.root.after_idle(self._oben_anpassen)
            except tk.TclError:
                self._anpassung_geplant = False

    def _oben_anpassen(self):
        """Höhe des scrollbaren Einstellbereichs so wählen, dass Fundliste, Protokoll und Leiste sichtbar bleiben."""
        self._anpassung_geplant = False
        if self.beendet:
            return
        if self._anpassung_laeuft:
            try:
                self.root.after(1, self._oben_anpassen)     # läuft gerade: später noch einmal (nicht verwerfen)
            except tk.TclError:
                pass
            return
        self._anpassung_laeuft = True
        try:
            if not self.oben.winfo_exists():
                return
            benoetigt = self.oben.winfo_reqheight()
            fenster_h = self.root.winfo_height()
            if fenster_h <= 1:                               # noch nicht dargestellt: Startgeometrie nehmen
                fenster_h = self._start_hoehe
            klein = fenster_h < self._px(FENSTER_KLEIN_HOEHE)
            if fenster_h < self._px(UNTERTITEL_MINDESTHOEHE):
                if self.untertitel.winfo_ismapped():
                    self.untertitel.pack_forget()
                    self.kopf.update_idletasks()
            elif not self.untertitel.winfo_ismapped():
                self.untertitel.pack(anchor="w", pady=(0, 6))
                self.kopf.update_idletasks()
            # kleines Fenster: Bedienhinweis über der Fundliste ausblenden (der Knopf „Vorschau …“ und die
            # Statuszeile nennen die Vorschau weiterhin) – jede Zeile zählt für die Fundliste
            if klein and self.baum_hinweis.winfo_manager():
                self.baum_hinweis.pack_forget()
            elif not klein and not self.baum_hinweis.winfo_manager():
                self.baum_hinweis.pack(anchor="w", fill="x", before=self.baum_rahmen)
            zeilen = PROTOKOLL_ZEILEN_KLEIN if klein else PROTOKOLL_ZEILEN
            if int(self.protokoll.cget("height")) != zeilen:
                self.protokoll.config(height=zeilen)
                self.protokoll_rahmen.update_idletasks()
            karte3_rand = max(0, self.karte3.winfo_reqheight() - self.baum_rahmen.winfo_reqheight())
            fest = (self.kopf.winfo_reqheight() + self.aktionsleiste.winfo_reqheight()
                    + self.protokoll_rahmen.winfo_reqheight() + karte3_rand + self._px(44))
            rest = fenster_h - fest
            # Die Fundliste ist der Arbeitsbereich (GR-02): fester Anteil des freien Platzes (mindestens
            # BAUM_MINDESTHOEHE); der Einstellbereich bekommt den Rest und scrollt bei Bedarf.
            baum_soll = max(self._px(BAUM_MINDESTHOEHE), int(rest * BAUM_ANTEIL))
            verfuegbar = rest - baum_soll
            hoehe = max(self._px(OBEN_MINDESTHOEHE), min(benoetigt, verfuegbar))
            self.oben_canvas.configure(height=hoehe,
                                       scrollregion=(0, 0, self.oben.winfo_reqwidth(), benoetigt))
            if benoetigt > hoehe + 2:
                if not self.oben_roll.winfo_ismapped():
                    self.oben_roll.pack(side="right", fill="y")
            else:
                self.oben_roll.pack_forget()
                self.oben_canvas.yview_moveto(0)
        except tk.TclError:
            pass
        finally:
            self._anpassung_laeuft = False

    def _fenster_geaendert(self, ereignis):
        if ereignis.widget is not self.root:
            return
        breite = max(300, ereignis.width - self._px(60))
        self.untertitel.config(wraplength=breite)
        self.datei_hinweis.config(wraplength=max(300, breite - self._px(40)))
        self.hinweis_kasten.config(wraplength=max(300, breite - self._px(40)))
        self.profil_beschreibung.config(wraplength=max(300, breite - self._px(40)))
        self.baum_hinweis.config(wraplength=max(300, breite - self._px(40)))
        self._anpassung_planen()

    def _mausrad(self, ereignis):
        """Mausrad über dem Einstellbereich scrollt den Canvas (Text/Baum scrollen selbst)."""
        try:
            ziel = self.root.winfo_containing(ereignis.x_root, ereignis.y_root)
        except (tk.TclError, KeyError):
            return
        w = ziel
        while w is not None:
            if isinstance(w, (tk.Text, ttk.Treeview, tk.Listbox, tk.Entry)):
                return
            if w is self.oben_canvas:
                break
            w = getattr(w, "master", None)
        else:
            return
        if not self.oben_roll.winfo_ismapped():
            return
        if getattr(ereignis, "num", None) == 4 or getattr(ereignis, "delta", 0) > 0:
            self.oben_canvas.yview_scroll(-1, "units")
        else:
            self.oben_canvas.yview_scroll(1, "units")

    # ------------------------------------------------------------------
    # Dateiauswahl
    # ------------------------------------------------------------------
    def _drop_ereignis(self, ereignis):
        try:                                   # tkdnd liefert eine Tcl-Liste (Leerzeichen/Klammern gequotet, GR-08)
            pfade = list(self.root.tk.splitlist(ereignis.data))
        except tk.TclError:
            pfade = [a or b for a, b in re.findall(r"\{([^}]*)\}|(\S+)", ereignis.data)]
        self._pdfs_hinzufuegen(pfade)

    def dateien_waehlen(self):
        if self.laeuft:
            self._laeuft_hinweis()
            return
        bilder = " ".join(f"*{e}" for e in sorted(dateien.BILD_ENDUNGEN))
        pfade = filedialog.askopenfilenames(title="PDF-Dateien oder Fotos auswählen",
                                            filetypes=[("PDF-Dateien und Fotos", f"*.pdf {bilder}"),
                                                       ("PDF-Dateien", "*.pdf"), ("Fotos und Bild-Scans", bilder),
                                                       ("Alle Dateien", "*")], parent=self.root)
        if pfade:
            self._pdfs_hinzufuegen(list(pfade))

    def ordner_waehlen(self):
        if self.laeuft:
            self._laeuft_hinweis()
            return
        ordner = filedialog.askdirectory(title="Ordner mit PDFs oder Fotos auswählen", parent=self.root)
        if ordner:
            self._pdfs_hinzufuegen([ordner])

    def zielordner_waehlen(self):
        if self.laeuft:
            self._laeuft_hinweis()
            return
        ordner = filedialog.askdirectory(title="Gemeinsamen Zielordner wählen", parent=self.root)
        if ordner:
            self.zielordner_var.set(ordner)
            self.zielordner_aktiv.set(True)

    def _beschaeftigt(self, an: bool, text: str | None = None):
        """Sanduhr während längerer Prüfungen im Hauptthread (großer Ordner, Netzlaufwerk)."""
        try:
            self.root.config(cursor="watch" if an else "")
            if an and text:
                self.status_label.config(text=text)
            self.root.update_idletasks()
        except tk.TclError:
            pass

    @staticmethod
    def _kurzname(pfad) -> str:
        return Path(dateien.ohne_langpfad(pfad)).name

    def _nicht_geprueft_merken(self, pfad, grund: str):
        """Datei aus der Auswahl, die NICHT geprüft wird – steht in den Abschlussdialogen von Analyse und Schwärzung
        und (für die laufende Auswahl) in der letzten Protokollzeile des Hinzufügens."""
        self.nicht_geprueft[Path(pfad)] = grund
        if self._auswahl_ungeprueft is not None:
            self._auswahl_ungeprueft[Path(pfad)] = grund

    @staticmethod
    def _grund_keine_pdf(pfad, arten: dict) -> str:
        """„keine PDF, sondern eine Webseite (HTML)“ – mit der Art, wenn der Inhalt geprüft wurde, sonst nach der
        Endung („keine PDF, sondern eine Outlook-Nachricht“)."""
        art = (arten or {}).get(pfad)
        if art and art not in ("endung", "unbekannt"):
            return f"keine PDF, sondern {dateien.art_beschreibung(art)}"
        vermutlich = dateien.endung_beschreibung(dateien.ohne_langpfad(pfad)) if art == "endung" else None
        return f"keine PDF, sondern {vermutlich}" if vermutlich else "keine PDF"

    def _nicht_geprueft_text(self, eintraege, anzahl: int = 8) -> str:
        """„a.msg (keine PDF), b.pdf (Kennwort nicht eingegeben) und 2 weitere“."""
        eintraege = list(eintraege)
        teile = [f"{self._kurzname(pfad)} ({grund})" for pfad, grund in eintraege[:anzahl]]
        return ", ".join(teile) + (f" und {len(eintraege) - anzahl} weitere" if len(eintraege) > anzahl else "")

    def _nicht_geprueft_block(self, anzahl: int = 5) -> list[str]:
        """Block für die Abschlussdialoge: alle Dateien der Auswahl, die NICHT geprüft wurden – mit Grund."""
        eintraege = list(self.nicht_geprueft.items())
        if not eintraege:
            return []
        zeilen = [f"NICHT geprüft wurden {len(eintraege)} Datei(en) aus der Auswahl (keine PDF, Foto nicht "
                  f"übernommen, ohne Kennwort, nicht lesbar …) – diese Dateien nicht ungeprüft weitergeben:"]
        zeilen += [f"  • {self._kurzname(pfad)}: {grund}" for pfad, grund in eintraege[:anzahl]]
        if len(eintraege) > anzahl:
            zeilen.append(f"  • … und {len(eintraege) - anzahl} weitere (siehe Protokoll)")
        return zeilen

    def _namen_liste(self, pfade, anzahl=5, arten: dict | None = None) -> str:
        teile = []
        for p in pfade[:anzahl]:
            art = (arten or {}).get(p)
            if art and art not in ("endung", "unbekannt") and Path(p).suffix.lower() == ".pdf":
                teile.append(f"{self._kurzname(p)} (in Wahrheit {dateien.art_beschreibung(art)})")
            else:
                teile.append(self._kurzname(p))
        return ", ".join(teile) + (f" und {len(pfade) - anzahl} weitere" if len(pfade) > anzahl else "")

    def _ausgaben_bestaetigen(self, ausgaben: list) -> bool:
        """M-63: Datei ist schon eine Ausgabe des Programms – warnen und fragen."""
        namen = ", ".join(f"„{self._kurzname(p)}“" for p in ausgaben[:3]) + (" …" if len(ausgaben) > 3 else "")
        einzahl = len(ausgaben) == 1
        text = (f"{namen} {'ist' if einzahl else 'sind'} bereits {'eine Ausgabe' if einzahl else 'Ausgaben'} "
                f"dieses Programms (Name „anonym_…“ oder Ordner „{dateien.AUSGABE_ORDNER}“).\n\n"
                f"Zum Nachschwärzen besser das ORIGINAL wählen und in der Vorschau nachschwärzen. Eine Ausgabe "
                f"erneut zu bearbeiten, legt eine weitere Ausgabe in „{dateien.AUSGABE_ORDNER}\\"
                f"{dateien.AUSGABE_ORDNER}“ an.\n\nTrotzdem hinzufügen?")
        ja = self._frage("Bereits anonymisierte Datei", text, warnung=True, standard_nein=True)
        if ja:
            self._log(f"ℹ {namen}: bereits Ausgabe(n) des Programms – auf Wunsch trotzdem hinzugefügt.", "hinweis")
        else:
            self._log(f"ℹ {namen}: bereits Ausgabe(n) des Programms – nicht hinzugefügt.", "hinweis")
        return ja

    def _bilder_bestaetigen(self, bilder: list, arten: dict) -> bool:
        """R-01: Fotos und Bild-Scans (auch umbenannte) als PDF übernehmen?"""
        zeilen = [f"  • {self._kurzname(p)}" + (" (ein Bild mit der Endung .pdf)" if Path(p).suffix.lower() == ".pdf"
                                                 else "") for p in bilder[:8]]
        if len(bilder) > 8:
            zeilen.append(f"  … und {len(bilder) - 8} weitere")
        text = (f"{len(bilder)} Foto(s) bzw. Bild-Scan(s) gefunden:\n" + "\n".join(zeilen) + "\n\n"
                "In PDFs umwandeln und mitprüfen? Der Text wird dann per Texterkennung (OCR) gelesen – das ist "
                "unsicherer als bei einer echten PDF; das Ergebnis bitte besonders sorgfältig ansehen. Die Umwandlung "
                "liegt nur vorübergehend im Programmordner, die Ausgabe heißt wie gewohnt anonym_NN.pdf.\n\n"
                f"ACHTUNG: {FOTO_GRENZEN} Die Ausgabe eines Fotos muss deshalb immer in der Vorschau freigegeben "
                "werden.\n\n"
                "„Nein“: Die Bilder werden NICHT geprüft und nicht in die Liste aufgenommen.")
        return self._frage("Fotos als PDF übernehmen?", text)

    def _bild_umwandeln(self, bild: Path, art: str | None) -> dict | None:
        """Bild -> PDF-Arbeitskopie im Programmordner für Zwischendateien; None (mit Meldung), wenn es nicht geht."""
        ziel = None
        try:
            ziel = dateien.arbeitskopie_ziel(self._kurzname(bild))
            seiten = dateien.bild_als_pdf(bild, ziel, art)
        except Exception as fehler:
            if ziel is not None:
                dateien.arbeitskopie_entfernen(ziel)
            if not isinstance(fehler, (OSError, ValueError, dateien.SitzungBeendet)):
                dateien.fehler_protokollieren(*sys.exc_info())
            grund = str(fehler) if isinstance(fehler, ValueError) else _verstaendliche_fehlermeldung(fehler, bild)
            self._log(f"⚠ {self._kurzname(bild)}: konnte nicht als PDF übernommen werden ({grund}) – NICHT geprüft.",
                      "warnung", zaehlen=False)
            self._nicht_geprueft_merken(bild, "Bild nicht lesbar")
            return None
        return {"pfad": ziel, "art": "bild", "seiten": seiten}

    def _kennwort_abfragen(self, pfad, fehlversuch: bool = False) -> str | None:
        """Kennwort einer geschützten PDF abfragen (maskierter Dialog); None = überspringen. Nichts wird gespeichert."""
        dialog = KennwortDialog(self, self._kurzname(pfad), fehlversuch)
        self.kennwort_dialog = dialog
        try:
            return dialog.zeigen()
        finally:
            self.kennwort_dialog = None

    def _geschuetzte_pdf_entsperren(self, pdf: Path, bekannt: list) -> dict | None:
        """R-12: Kennwort abfragen (falsch: erneut fragen, bis „Überspringen“) und eine Kopie OHNE Kennwort im
        Programmordner für Zwischendateien ablegen. „bekannt“ hält höchstens das zuletzt richtige Kennwort dieser
        Auswahl (oft gilt eines für mehrere Schreiben) – nur bis zum Ende der Auswahl, nie auf der Festplatte."""
        ziel = None
        try:
            ziel = dateien.arbeitskopie_ziel(self._kurzname(pdf))
            if bekannt and dateien.pdf_entschluesseln(pdf, bekannt[0], ziel):
                return {"pfad": ziel, "art": "entschluesselt"}
            fehlversuch = False
            while True:
                kennwort = self._kennwort_abfragen(pdf, fehlversuch)
                if kennwort is None or self._auswahl_abgebrochen():   # „Überspringen“ oder Fenster geschlossen
                    dateien.arbeitskopie_entfernen(ziel)
                    return None
                if dateien.pdf_entschluesseln(pdf, kennwort, ziel):
                    bekannt[:] = [kennwort]
                    return {"pfad": ziel, "art": "entschluesselt"}
                fehlversuch = True
        except Exception as fehler:
            if ziel is not None:
                dateien.arbeitskopie_entfernen(ziel)
            if isinstance(fehler, dateien.SitzungBeendet):        # Programm wird beendet: still abbrechen
                return None
            log = dateien.fehler_protokollieren(*sys.exc_info())
            self._log(f"✖ {self._kurzname(pdf)}: konnte nicht entschlüsselt werden "
                      f"({_verstaendliche_fehlermeldung(fehler, pdf)}) – NICHT geprüft." + (f" Details: {log}" if log
                                                                                           else ""),
                      "fehler", zaehlen=False)
            return False

    def _pdfs_hinzufuegen(self, pfade):
        """Dateien und Ordner aufnehmen. Jede Datei wird am INHALT geprüft (R-01): echte PDFs kommen in die Liste,
        Fotos und Bild-Scans auf Wunsch als PDF-Arbeitskopie, geschützte PDFs nach Eingabe des Kennworts (R-12).
        Alles andere wird mit Namen und Grund gemeldet – nichts fällt still weg (R-10, R-09). Eine Datei, die schon
        eine Ausgabe des Programms ist, wird nur nach Rückfrage aufgenommen (M-63)."""
        if self.laeuft:
            self._laeuft_hinweis()
            return
        if self._hinzufuegen_laeuft:                  # z. B. Drag & Drop, während der Kennwortdialog offen ist
            self._status("Bitte erst die laufende Auswahl abschließen (Kennwort eingeben oder überspringen).")
            return
        if self.beendet or self._schliessen_angefordert:
            return
        self._hinzufuegen_laeuft = True
        self._auswahl_ungeprueft = {}
        try:
            self._pdfs_hinzufuegen_ausfuehren(pfade)
        finally:
            self._hinzufuegen_laeuft = False
            self._auswahl_ungeprueft = None
            self._beschaeftigt(False)
            if self._schliessen_angefordert and not self.beendet:
                # Das Fenster wurde während einer Rückfrage geschlossen: jetzt, da die Auswahl abgebrochen und ihre
                # Arbeitskopien gelöscht sind, wirklich schließen (nach dem laufenden Tk-Ereignis)
                try:
                    self.root.after_idle(self._schliessen_nachholen)
                except tk.TclError:
                    self._schliessen_nachholen()

    def _schliessen_nachholen(self):
        self._schliessen_angefordert = False
        if not self.beendet:
            self.schliessen()

    def _auswahl_abgebrochen(self) -> bool:
        """Wurde das Fenster während der Auswahl geschlossen? Dann keine weitere Datei und keine Arbeitskopie mehr."""
        return self.beendet or self._schliessen_angefordert

    def _kopien_verwerfen(self, kopien: dict):
        """Arbeitskopien einer abgebrochenen Auswahl löschen (sie stehen noch nicht in self.arbeitskopien)."""
        for eintrag in kopien.values():
            if eintrag and eintrag.get("pfad"):
                dateien.arbeitskopie_entfernen(eintrag["pfad"])
        kopien.clear()

    def _pdfs_hinzufuegen_ausfuehren(self, pfade):
        self._beschaeftigt(True, "Dateien werden geprüft …")
        try:
            bericht = dateien.sammle_pdfs_bericht(pfade)
        finally:
            self._beschaeftigt(False)
        arten = bericht.get("arten", {})
        gruende = bericht.get("gruende", {})
        teile = []
        kopien: dict[Path, dict] = {}

        # M-63: einzeln gewählte Ausgaben nur nach Rückfrage
        pdf_kandidaten = [p for p in bericht["pdfs"] if p not in self.dateien]
        ausgaben = [p for p in bericht.get("ausgaben_einzeln", []) if p in pdf_kandidaten]
        if ausgaben and not self._ausgaben_bestaetigen(ausgaben):
            pdf_kandidaten = [p for p in pdf_kandidaten if p not in ausgaben]
            teile.append(f"{len(ausgaben)} Ausgabe(n) nicht hinzugefügt")
        if self._auswahl_abgebrochen():
            return
        ohne_endung = [p for p in bericht.get("pdf_ohne_endung", []) if p not in self.dateien]

        # Fotos und Bild-Scans: auf Wunsch als PDF-Arbeitskopie
        bilder = [p for p in bericht.get("bilder", []) if p not in self.dateien]
        bilder_neu = 0
        if bilder:
            if self._bilder_bestaetigen(bilder, arten):
                if self._auswahl_abgebrochen():
                    return
                self._beschaeftigt(True, "Fotos werden in PDFs umgewandelt …")
                try:
                    for bild in bilder:
                        eintrag = self._bild_umwandeln(bild, arten.get(bild))
                        if eintrag is not None:
                            kopien[bild] = eintrag
                finally:
                    self._beschaeftigt(False)
            else:
                if self._auswahl_abgebrochen():
                    return
                for bild in bilder:
                    self._nicht_geprueft_merken(bild, "Bild nicht übernommen")
                teile.append(f"{len(bilder)} Bild(er) nicht übernommen")
                self._log(f"⚠ {len(bilder)} Foto(s)/Bild-Scan(s) NICHT übernommen und NICHT geprüft: "
                          f"{self._namen_liste(bilder, arten=arten)}", "warnung", zaehlen=False)

        # R-12: geschützte PDFs entsperren; PDFs ohne Endung als Kopie mit „.pdf“
        uebersprungen_kennwort = []
        ausgelassen: set[Path] = set()
        bekannt: list[str] = []
        try:
            for pdf in pdf_kandidaten + ohne_endung:
                if self._auswahl_abgebrochen():
                    break                    # geschlossen, während ein Kennwortdialog offen war: nichts mehr anlegen
                if dateien.pdf_kennwort_noetig(pdf):
                    eintrag = self._geschuetzte_pdf_entsperren(pdf, bekannt)
                    if not eintrag:
                        ausgelassen.add(pdf)
                        if eintrag is None:
                            uebersprungen_kennwort.append(pdf)
                        self._nicht_geprueft_merken(pdf, "Kennwort nicht eingegeben" if eintrag is None
                                                    else "nicht entschlüsselbar")
                        continue
                    kopien[pdf] = eintrag
                    self._log(f"ℹ {self._kurzname(pdf)}: mit Kennwort geöffnet – geprüft wird eine Kopie ohne "
                              f"Kennwort; auch die Ausgabedatei hat KEIN Kennwort.", "hinweis")
                elif pdf in ohne_endung:
                    ziel = None
                    try:
                        ziel = dateien.arbeitskopie_ziel(self._kurzname(pdf))
                        dateien.pdf_kopieren(pdf, ziel)
                    except (OSError, dateien.SitzungBeendet) as fehler:
                        if ziel is not None:
                            dateien.arbeitskopie_entfernen(ziel)
                        self._log(f"⚠ {self._kurzname(pdf)}: {_verstaendliche_fehlermeldung(fehler, pdf)} – NICHT "
                                  f"geprüft.", "warnung", zaehlen=False)
                        self._nicht_geprueft_merken(pdf, "nicht lesbar")
                        ausgelassen.add(pdf)
                        continue
                    kopien[pdf] = {"pfad": ziel, "art": "kopie"}
        finally:
            bekannt.clear()                  # das Kennwort lebt nicht über die Auswahl hinaus
        if self._auswahl_abgebrochen():
            # Fenster während einer Rückfrage geschlossen: nichts davon kommt in die Liste – und keine
            # (entschlüsselte) Arbeitskopie bleibt liegen (Befund Runde 2)
            self._kopien_verwerfen(kopien)
            return

        neu = 0
        for pdf in pdf_kandidaten + ohne_endung + bilder:
            if pdf in self.dateien or pdf in ausgelassen or (pdf in bilder and pdf not in kopien):
                continue
            if pdf in kopien:
                self.arbeitskopien[pdf] = kopien[pdf]
            self.nicht_geprueft.pop(pdf, None)          # z. B. jetzt mit Kennwort: doch geprüft
            self.dateien.append(pdf)
            self._datei_zeile_einfuegen(pdf)
            if pdf in bilder:
                bilder_neu += 1
            else:
                neu += 1
        self._beschriftungen_aktualisieren()

        # Meldungen zur Auswahl zählen nicht als Warnung eines Laufs (GR-07)
        teile.insert(0, f"{neu} PDF-Datei(en) hinzugefügt" if neu else "Keine neue PDF-Datei")
        if bilder_neu:
            teile.insert(1, f"{bilder_neu} Bild(er) als PDF übernommen")
            self._log(f"ℹ {bilder_neu} Foto(s)/Bild-Scan(s) als PDF übernommen – der Text wird per Texterkennung "
                      f"gelesen; das Ergebnis bitte besonders sorgfältig prüfen.", "hinweis")
        if uebersprungen_kennwort:
            teile.append(f"{len(uebersprungen_kennwort)} ohne Kennwort übersprungen")
            self._log(f"⚠ Ohne Kennwort übersprungen und NICHT geprüft: {self._namen_liste(uebersprungen_kennwort)} "
                      f"– zum Prüfen erneut hinzufügen und das Kennwort eingeben (oder die PDF ohne Kennwort "
                      f"speichern).", "warnung", zaehlen=False)
        if bericht["uebersprungen"]:
            namen = self._namen_liste(bericht["uebersprungen"], arten=arten)
            for p in bericht["uebersprungen"]:
                self._nicht_geprueft_merken(p, self._grund_keine_pdf(p, arten))
            teile.append(f"{len(bericht['uebersprungen'])} übersprungen – keine PDF")
            self._log(f"⚠ Übersprungen (keine PDF-Datei; Fotos, Mails oder Office-Dateien bitte zuerst als "
                      f"PDF speichern): {namen}", "warnung", zaehlen=False)
        keine_pdf = bericht.get("keine_pdf", [])
        if keine_pdf:
            for p in keine_pdf:
                self._nicht_geprueft_merken(p, self._grund_keine_pdf(p, arten))
            teile.append(f"{len(keine_pdf)} keine PDF (nicht geprüft)")
            satz = ("1 Datei im Ordner ist keine PDF und wurde" if len(keine_pdf) == 1 else
                    f"{len(keine_pdf)} Dateien im Ordner sind keine PDF und wurden")
            self._log(f"⚠ {satz} NICHT geprüft: {self._namen_liste(keine_pdf, 8, arten)} – bei Bedarf zuerst "
                      f"als PDF speichern (z. B. Drucken → „Microsoft Print to PDF“).", "warnung", zaehlen=False)
        unlesbar = bericht.get("nicht_lesbar", [])
        if unlesbar:
            for p in unlesbar:
                self._nicht_geprueft_merken(p, gruende.get(p, "nicht lesbar"))
            teile.append(f"{len(unlesbar)} nicht lesbar")
            liste = ", ".join(f"{self._kurzname(p)} ({gruende.get(p, 'nicht lesbar')})" for p in unlesbar[:5])
            self._log(f"⚠ {len(unlesbar)} Datei(en)/Ordner konnten nicht gelesen werden und wurden NICHT geprüft: "
                      f"{liste}" + (" …" if len(unlesbar) > 5 else ""), "warnung", zaehlen=False)
        if bericht["ausgaben"]:
            teile.append(f"{len(bericht['ausgaben'])} bereits anonymisierte Datei(en) ausgelassen")
            self._log(f"ℹ {len(bericht['ausgaben'])} Datei(en) im Ordner sind bereits Ausgaben des Programms "
                      f"und wurden ausgelassen.", "hinweis")
        if bericht.get("zwischendateien"):
            self._log(f"ℹ {len(bericht['zwischendateien'])} Zwischendatei(en) einer abgebrochenen Schwärzung "
                      f"(.anonym_tmp_…) ignoriert – sie werden beim nächsten Schwärzen aufgeräumt.", "hinweis")
        if bericht["leere_ordner"]:
            namen = ", ".join(dateien.ohne_langpfad(p) for p in bericht["leere_ordner"][:3])
            teile.append("Ordner ohne PDF-Dateien")
            self._log(f"⚠ Ordner enthält keine PDF-Dateien: {namen}", "warnung", zaehlen=False)
        if bericht["fehlend"]:
            teile.append(f"{len(bericht['fehlend'])} nicht gefunden")
            self._log("⚠ Nicht gefunden: " + ", ".join(
                dateien.ohne_langpfad(p) + (f" ({gruende[p]} – unter Windows ggf. zu lang)" if p in gruende else "")
                for p in bericht["fehlend"][:3]), "warnung", zaehlen=False)
        ungeprueft = dict(self._auswahl_ungeprueft or {})
        hinweis = "; ".join(teile) + f" · insgesamt {len(self.dateien)} Datei(en)."
        if ungeprueft:
            hinweis += f" ⚠ {len(ungeprueft)} Datei(en) dieser Auswahl werden NICHT geprüft – Namen im Protokoll."
        self.datei_hinweis.config(text=hinweis, fg=FARBE_WARNUNG if ungeprueft else FARBE_TEXT_GRAU)
        if (neu or bilder_neu) and self.analyse_ergebnisse:
            self._log("ℹ Neue Dateien sind noch nicht analysiert – bitte erneut analysieren, bevor geschwärzt wird.",
                      "hinweis")
        if ungeprueft:
            # als LETZTE Zeile: das Protokoll zeigt auf kleinen Bildschirmen nur drei Zeilen – die Namen der nicht
            # geprüften Dateien dürfen nicht von einer ℹ-Zeile hinausgeschoben werden (Befund Runde 2)
            self._log(f"⚠ NICHT geprüft aus dieser Auswahl: {len(ungeprueft)} Datei(en) – "
                      f"{self._nicht_geprueft_text(ungeprueft.items())}. Diese Dateien nicht ungeprüft weitergeben.",
                      "warnung", zaehlen=False)
        self._status_dateien()
        self._start_knopf_aktualisieren()

    def _status_dateien(self):
        # die Statuszeile ist immer sichtbar (auch wenn der Einstellbereich weggescrollt ist): nicht geprüfte Dateien
        # stehen dort zuerst
        vorne = (f"⚠ {len(self.nicht_geprueft)} Datei(en) werden NICHT geprüft (siehe Protokoll) · "
                 if self.nicht_geprueft else "")
        if not self.dateien:
            self._status(vorne + "Bereit. Bitte PDF-Dateien hinzufügen (Schritt 1).")
        elif not self.analyse_ergebnisse:
            self._status(vorne + f"{len(self.dateien)} Datei(en) ausgewählt – jetzt unten „Analysieren“ drücken.")

    def _datei_vergessen(self, pdf: Path):
        """Alles zu einer Datei vergessen (Vorschau, manuelle Markierungen, Ausgabestatus, Arbeitskopie)."""
        fenster = self.vorschauen.pop(pdf, None)
        if fenster is not None:
            fenster.schliessen(benachrichtigen=False)
        self.analyse_ergebnisse.pop(pdf, None)
        self.manuell.pop(pdf, None)
        self.lauf_immer.pop(pdf, None)
        self.ausgaben.pop(pdf, None)
        self._arbeitskopie_loeschen(pdf)

    def _arbeitsdatei(self, pdf: Path) -> Path:
        """Datei, die die Engine liest: die Arbeitskopie (Bild als PDF, entschlüsselte PDF) oder das Original."""
        eintrag = self.arbeitskopien.get(pdf)
        return Path(eintrag["pfad"]) if eintrag else pdf

    def _arbeitskopie_loeschen(self, pdf: Path):
        """Arbeitskopie einer Datei löschen (vorher offene Vorschau-Dokumente freigeben – Windows sperrt sie sonst)."""
        eintrag = self.arbeitskopien.pop(pdf, None)
        if not eintrag:
            return
        try:
            self._vorschau_dateien_freigeben(Path(eintrag["pfad"]))
        except Exception:
            pass
        dateien.arbeitskopie_entfernen(eintrag["pfad"])

    def liste_leeren(self):
        if self.laeuft:
            self._laeuft_hinweis()
            return
        for pdf in list(self.dateien):
            self._datei_vergessen(pdf)
        self.dateien.clear()
        self.analyse_ergebnisse.clear()
        self.zeilen.clear()
        self.beschriftungen.clear()
        self.baum.delete(*self.baum.get_children())
        self.analyse_veraltet = False
        self.nicht_geprueft.clear()
        self.datei_hinweis.config(text="Noch keine Dateien. Die Liste erscheint unten in Schritt 3.",
                                  fg=FARBE_TEXT_GRAU)
        self._status_dateien()
        self._start_knopf_aktualisieren()

    def datei_entfernen(self, iid=None):
        """Entfernt eine Datei (die ausgewählte, falls keine angegeben) aus Liste und Baum."""
        if self.laeuft:
            self._laeuft_hinweis()
            return
        if iid is None:
            auswahl = self.baum.selection()
            if not auswahl:
                self._dialog("info", "Keine Datei gewählt",
                             "Bitte zuerst eine Datei in der Liste anklicken, dann „Datei aus Liste entfernen“.")
                return
            iid = auswahl[0]
        if iid not in self.zeilen:
            iid = self.baum.parent(iid)
        pdf = self.zeilen.pop(iid, None)
        if pdf is None:
            return
        self.beschriftungen.pop(iid, None)
        if pdf in self.dateien:
            self.dateien.remove(pdf)
        self._datei_vergessen(pdf)
        if self.baum.exists(iid):
            self.baum.delete(iid)
        self._beschriftungen_aktualisieren()
        self.datei_hinweis.config(text=f"„{pdf.name}“ entfernt · insgesamt {len(self.dateien)} Datei(en).",
                                  fg=FARBE_TEXT_GRAU)
        self._status_dateien()
        self._start_knopf_aktualisieren()

    # ------------------------------------------------------------------
    # Baum (Dateien, Funde, manuelle Markierungen)
    # ------------------------------------------------------------------
    def _datei_zeile_einfuegen(self, pdf: Path) -> str:
        iid = str(pdf)
        if not self.baum.exists(iid):
            self.baum.insert("", "end", iid=iid, text="", open=True,
                             values=("noch nicht analysiert", "", "", "", "", ""), tags=("datei", "aus"))
            self.zeilen[iid] = pdf
            self.beschriftungen[iid] = pdf.name
            self._zeilentext_setzen(iid)
        return iid

    def _beschriftungen_aktualisieren(self):
        """Dateinamen relativ zum gemeinsamen Stammordner anzeigen (KundeA/Police.pdf, KundeB/Police.pdf); Bilder
        und entsperrte PDFs tragen einen Zusatz („(Bild → PDF)“, „(Kennwort entfernt)“)."""
        stamm = dateien.gemeinsamer_stamm(self.dateien)
        ein_ordner = len({Path(dateien.ohne_langpfad(p)).parent for p in self.dateien}) <= 1
        for iid, pdf in self.zeilen.items():
            anzeige = Path(dateien.ohne_langpfad(pdf))
            if stamm is None or ein_ordner:
                name = anzeige.name
            else:
                try:
                    name = anzeige.relative_to(stamm).as_posix()
                except ValueError:
                    name = str(anzeige)
            art = (self.arbeitskopien.get(pdf) or {}).get("art")
            self.beschriftungen[iid] = name + ANZEIGE_ART.get(art, "")
            self._zeilentext_setzen(iid)
        for fenster in self.vorschauen.values():
            fenster.titel_setzen()

    def _anzeigename(self, pdf: Path) -> str:
        return self.beschriftungen.get(str(pdf), pdf.name)

    def _zustand(self, iid) -> str:
        tags = self.baum.item(iid, "tags")
        for zustand in ("an", "aus", "teil"):
            if zustand in tags:
                return zustand
        return "aus"

    def _zustand_setzen(self, iid, zustand):
        tags = [t for t in self.baum.item(iid, "tags") if t not in HAKEN]
        tags.append(zustand)
        self.baum.item(iid, tags=tuple(tags))
        self._zeilentext_setzen(iid)

    def _zeilentext_setzen(self, iid):
        zustand = self._zustand(iid)
        if iid in self.zeilen:
            self.baum.item(iid, text=f"{HAKEN[zustand]}  {self.beschriftungen.get(iid, '')}")
        else:
            self.baum.item(iid, text=HAKEN[zustand])

    def _eltern_ableiten(self, eltern):
        kinder = self.baum.get_children(eltern)
        if not kinder:
            zustand = "aus"
        else:
            zustaende = [self._zustand(k) for k in kinder]
            if all(z == "an" for z in zustaende):
                zustand = "an"
            elif all(z == "aus" for z in zustaende):
                zustand = "aus"
            else:
                zustand = "teil"
        self._zustand_setzen(eltern, zustand)

    @staticmethod
    def _kind_art(iid: str):
        """("fund", Index) | ("manuell", mid) | (None, None) für eine Kind-iid „<pfad>::<index>“/„<pfad>::m<mid>“."""
        teile = str(iid).rsplit("::", 1)
        if len(teile) != 2:
            return None, None
        teil = teile[1]
        if teil.startswith("m") and teil[1:].isdigit():
            return "manuell", int(teil[1:])
        if teil.isdigit():
            return "fund", int(teil)
        return None, None

    def einzelstellen_moeglich(self, pdf: Path, ergebnis: dict | None = None) -> bool:
        """Kann die Engine einzelne Fundstellen schwärzen? (Analyse lieferte ein Seitenmodell, die Schwärzung
        nimmt es an – Vertrag Abschnitt 5). Sonst gilt ein Fund immer an allen seinen Stellen."""
        ergebnis = self.analyse_ergebnisse.get(pdf) if ergebnis is None else ergebnis
        return bool(ergebnis) and ergebnis.get("modell") is not None and kann(schwaerze_pdf, "modell")

    def kann_manuelle_bereiche(self) -> bool:
        return kann(schwaerze_pdf, "manuelle_bereiche")

    def kann_manuelle_stellen(self) -> bool:
        return kann(schwaerze_pdf, "manuelle_stellen")

    def _fund_hat_stellen(self, pdf: Path, fund: dict, ergebnis: dict | None = None) -> bool:
        return (isinstance(fund.get("stellen"), list) and bool(fund["stellen"])
                and self.einzelstellen_moeglich(pdf, ergebnis))

    def fund_zustand(self, pdf: Path, index: int) -> str:
        """an | aus | teil – bei Einzelstellen aus den Stellen abgeleitet, sonst das Häkchen des Funds."""
        ergebnis = self.analyse_ergebnisse.get(pdf)
        if not ergebnis or not 0 <= index < len(ergebnis["funde"]):
            return "aus"
        fund = ergebnis["funde"][index]
        if self._fund_hat_stellen(pdf, fund):
            an = sum(1 for s in fund["stellen"] if s.get("an", True))
            return "an" if an == len(fund["stellen"]) else ("aus" if an == 0 else "teil")
        iid = f"{pdf}::{index}"
        return self._zustand(iid) if self.baum.exists(iid) else "an"

    def _fund_zeile_einfuegen(self, pdf: Path, index: int, fund: dict, zustand: str):
        iid = str(pdf)
        seiten = fund.get("seiten") or []
        seiten_text = ", ".join(str(s) for s in seiten[:6]) + (" …" if len(seiten) > 6 else "")
        anzeige = fund["anzeige"]
        if fund.get("hinweis"):
            # ⚕ = angebotene Gesundheitsdaten, ⚑ = sonstiger Hinweis der Engine (auch an angehakten Funden)
            marke = MARKE_GESUNDHEIT if fund.get("kategorie") in GESUNDHEIT_KATEGORIEN else MARKE_HINWEIS
            anzeige = marke + anzeige
        self.baum.insert(iid, "end", iid=f"{iid}::{index}", text=HAKEN[zustand],
                         values=(anzeige, str(fund["text"]).replace("\n", " "), seiten_text,
                                 fund.get("anzahl", 1), _kontext_anzeige(fund.get("kontext", "")),
                                 fund["ersatz"]),
                         tags=("fund", zustand))

    def _manuell_zeile_einfuegen(self, pdf: Path, mid: int, eintrag: dict):
        anzeige = ANZEIGE_NACHSCHWAERZEN if eintrag.get("herkunft") == "nachschwaerzen" else ANZEIGE_MANUELL
        zustand = "an" if eintrag.get("an", True) else "aus"
        text = eintrag.get("text") or ("Bereich" if eintrag["art"] == "bereich" else "Stelle")
        self.baum.insert(str(pdf), "end", iid=f"{pdf}::m{mid}", text=HAKEN[zustand],
                         values=(anzeige, text, str(eintrag["seite"] + 1), 1,
                                 "Rahmen aus der Vorschau" if eintrag["art"] == "bereich" else "Klick in der Vorschau",
                                 PLATZHALTER_MANUELL),
                         tags=("manuell", zustand))

    def _baum_datei_fuellen(self, pdf: Path, ergebnis: dict):
        """Trägt die Funde einer Datei ein (Kind-iid = „<pfad>::<index>“, manuelle: „<pfad>::m<mid>“)."""
        if self.beendet:
            return
        iid = self._datei_zeile_einfuegen(pdf)
        self.baum.delete(*self.baum.get_children(iid))
        funde = ergebnis["funde"]
        for index, fund in enumerate(funde):
            zustand = "an"
            if self._fund_hat_stellen(pdf, fund, ergebnis):
                an = sum(1 for s in fund["stellen"] if s.get("an", True))
                zustand = "an" if an == len(fund["stellen"]) else ("aus" if an == 0 else "teil")
            self._fund_zeile_einfuegen(pdf, index, fund, zustand)
        for mid, eintrag in self.manuell.get(pdf, {}).items():
            self._manuell_zeile_einfuegen(pdf, mid, eintrag)
        codes = meldungs_codes(ergebnis)
        nebenkanal = _nebenkanal_bezug(ergebnis)
        if ergebnis["fehler"]:
            status = f"Fehler: {ergebnis['fehler']}"
        elif not funde and codes & {"KEIN_TEXT", "KAUM_LESBAR"}:
            status = "0 Funde – kein Text lesbar!"
        else:
            status = f"{len(funde)} Fund(e)"
        if nebenkanal is not None and not ergebnis["fehler"]:
            status += " · Personendaten in Metadaten/Anhängen – werden entfernt"
        if ergebnis["warnungen"]:
            status += f" · {len(ergebnis['warnungen'])} Warnung(en)"
        self.baum.set(iid, "kategorie", status)
        self.baum.set(iid, "seiten", str(ergebnis["seiten"]) if ergebnis["seiten"] else "")
        self.baum.set(iid, "anzahl", str(sum(f.get("anzahl", 1) for f in funde)) if funde else "")
        self._ausgabe_zeile_setzen(pdf)
        self._eltern_ableiten(iid)

    def _ausgabe_zeile_setzen(self, pdf: Path):
        """Status der Ausgabe (fertig / prüfen / Fehler) in der Dateizeile (Spalten Text und Kontext)."""
        iid = str(pdf)
        if not self.baum.exists(iid):
            return
        eintrag = self.ausgaben.get(pdf)
        if not eintrag:
            self.baum.set(iid, "text", "")
            self.baum.set(iid, "kontext", "")
            return
        status = STATUS_TEXT.get(eintrag["status"], eintrag["status"])
        ausgabe = eintrag.get("pfad")
        self.baum.set(iid, "text", f"{status}: {ausgabe.name}" if ausgabe is not None else status)
        self.baum.set(iid, "kontext", eintrag.get("grund", ""))

    def _baum_klick(self, ereignis):
        """Einfachklick in die Häkchen-Spalte schaltet um; Dreieck, Kopfzeile und Trenner bleiben Tk überlassen."""
        region = self.baum.identify_region(ereignis.x, ereignis.y)
        if region not in ("tree", "cell"):
            return None
        zeile = self.baum.identify_row(ereignis.y)
        if not zeile:
            return None
        if self.baum.identify_column(ereignis.x) != "#0":
            return None
        element = self.baum.identify_element(ereignis.x, ereignis.y)
        if element.endswith("indicator") and self.baum.get_children(zeile):
            return None
        if zeile in self.zeilen and not self._trifft_haken(zeile, ereignis.x):
            return None                 # Klick auf den Dateinamen: nur auswählen (Pfad anzeigen, Entfernen)
        self.baum.focus_set()           # Tastaturfokus für die Leertaste
        self.baum.selection_set(zeile)
        self.baum.focus(zeile)
        self._umschalten(zeile)
        return "break"

    def _trifft_haken(self, zeile, x) -> bool:
        """Liegt x (Baumkoordinate) auf dem Häkchen-Symbol einer Dateizeile?"""
        bbox = self.baum.bbox(zeile, "#0")
        if not bbox:
            return False
        einzug = self._px(20)                        # Platz des Aufklapp-Dreiecks
        haken_breite = self.f_fett.measure(HAKEN["an"] + "  ") + self._px(6)
        return bbox[0] + einzug - self._px(4) <= x <= bbox[0] + einzug + haken_breite

    def _baum_doppelklick(self, ereignis):
        zeile = self.baum.identify_row(ereignis.y)
        element = self.baum.identify_element(ereignis.x, ereignis.y)
        if zeile and element.endswith("indicator") and self.baum.get_children(zeile):
            return None                 # Dreieck: Tk klappt auf/zu
        if zeile and self.baum.identify_region(ereignis.x, ereignis.y) in ("tree", "cell"):
            if zeile in self.zeilen or self.baum.identify_column(ereignis.x) != "#0":
                self.root.after_idle(self._vorschau_fuer_zeile, zeile)
        return "break"                  # sonst nichts umschalten, nichts zuklappen

    def _taste_leer(self, ereignis=None):
        zeile = self.baum.focus()
        if zeile:
            self._umschalten(zeile)
        return "break"

    def _haken_umschalten(self, ereignis=None):
        """Umschalten der fokussierten Zeile (Tastatur / Skripte)."""
        return self._taste_leer(ereignis)

    def _umschalten(self, zeile):
        if self.laeuft or not self.baum.exists(zeile):
            return
        if zeile in self.zeilen:
            neu = "aus" if self._zustand(zeile) == "an" else "an"
            self._datei_setzen(zeile, neu)
            return
        pdf = self.zeilen.get(self.baum.parent(zeile))
        art, nummer = self._kind_art(zeile)
        if pdf is None or art is None:
            return
        if art == "fund":
            self.fund_setzen(pdf, nummer, self.fund_zustand(pdf, nummer) != "an")
        else:
            self.manuell_umschalten(pdf, nummer)

    def _kind_setzen(self, pdf: Path, kind: str, an: bool):
        """Fund- oder manuelle Zeile setzen, ohne Eltern/Knopf/Vorschau nachzuführen (für Sammelaktionen)."""
        art, nummer = self._kind_art(kind)
        if art == "fund":
            funde = self.analyse_ergebnisse[pdf]["funde"] if pdf in self.analyse_ergebnisse else []
            fund = funde[nummer] if 0 <= nummer < len(funde) else None
            if fund is not None and self._fund_hat_stellen(pdf, fund):
                for stelle in fund["stellen"]:
                    stelle["an"] = an
        elif art == "manuell":
            eintrag = self.manuell.get(pdf, {}).get(nummer)
            if eintrag is not None:
                eintrag["an"] = an
        self._zustand_setzen(kind, "an" if an else "aus")

    def _nach_aenderung(self, pdf: Path | None):
        """Nach jeder Änderung von Häkchen/Stellen: Elternzeile, Schwärzen-Knopf, offene Vorschau."""
        if pdf is not None and self.baum.exists(str(pdf)):
            self._eltern_ableiten(str(pdf))
        self._start_knopf_aktualisieren()
        fenster = self.vorschauen.get(pdf) if pdf is not None else None
        ziele = [fenster] if fenster is not None else (list(self.vorschauen.values()) if pdf is None else [])
        for f in ziele:
            f.neu_zeichnen()

    def fund_setzen(self, pdf: Path, index: int, an: bool):
        """Fund an allen Stellen an/aus (Hauptliste und Vorschau bleiben gleich)."""
        if self.laeuft:
            return
        iid = f"{pdf}::{index}"
        if not self.baum.exists(iid):
            return
        self._kind_setzen(pdf, iid, an)
        self._nach_aenderung(pdf)

    def stelle_setzen(self, pdf: Path, index: int, stelle_index: int, an: bool):
        """Eine einzelne Fundstelle an/aus (nur wenn die Engine Einzelstellen kann)."""
        if self.laeuft:
            return
        fund = self.analyse_ergebnisse[pdf]["funde"][index]
        if not self._fund_hat_stellen(pdf, fund):
            self.fund_setzen(pdf, index, an)
            return
        fund["stellen"][stelle_index]["an"] = an
        iid = f"{pdf}::{index}"
        if self.baum.exists(iid):
            self._zustand_setzen(iid, self.fund_zustand(pdf, index))
        self._nach_aenderung(pdf)

    def manuell_hinzufuegen(self, pdf: Path, eintrag: dict) -> int | None:
        """Neue manuelle Markierung aus der Vorschau: {"art": "stelle"|"bereich", "seite", "rechtecke",
        "start", "ende", "text", "herkunft"}; erscheint als eigene Zeile in der Fundliste."""
        if self.laeuft or pdf not in self.analyse_ergebnisse:
            return None
        self._manuell_zaehler += 1
        mid = self._manuell_zaehler
        eintrag = dict(eintrag)
        eintrag.setdefault("an", True)
        eintrag.setdefault("herkunft", "vorschau")
        self.manuell.setdefault(pdf, {})[mid] = eintrag
        if self.baum.exists(str(pdf)):
            self._manuell_zeile_einfuegen(pdf, mid, eintrag)
        self._nach_aenderung(pdf)
        return mid

    def manuell_umschalten(self, pdf: Path, mid: int):
        eintrag = self.manuell.get(pdf, {}).get(mid)
        if self.laeuft or eintrag is None:
            return
        self._kind_setzen(pdf, f"{pdf}::m{mid}", not eintrag.get("an", True))
        self._nach_aenderung(pdf)

    def manuell_entfernen(self, pdf: Path, mid: int):
        if self.laeuft:
            return
        if self.manuell.get(pdf, {}).pop(mid, None) is None:
            return
        iid = f"{pdf}::m{mid}"
        if self.baum.exists(iid):
            self.baum.delete(iid)
        self._nach_aenderung(pdf)

    def begriff_ueberall(self, pdf: Path, text: str) -> int | None:
        """„Überall in diesem Dokument schwärzen“: IMMER-Begriff für diesen Lauf (diese Datei). Wird sofort als
        Fund ergänzt (ohne „stellen“ – die Schwärzung sucht alle Vorkommen selbst) und bei einer erneuten
        Analyse dieser Datei als IMMER-Begriff mitgegeben. Liefert den Fund-Index."""
        text = " ".join(str(text).split())
        ergebnis = self.analyse_ergebnisse.get(pdf)
        if self.laeuft or not text or ergebnis is None:
            return None
        for index, fund in enumerate(ergebnis["funde"]):
            if fund["kategorie"] == "begriff" and fund["text"].casefold() == text.casefold():
                self.fund_setzen(pdf, index, True)
                return index
        begriffe = self.lauf_immer.setdefault(pdf, [])
        if text not in begriffe:
            begriffe.append(text)
        fund = {"id": f"vorschau_{len(ergebnis['funde']) + 1}", "kategorie": "begriff", "anzeige": ANZEIGE_BEGRIFF_VORSCHAU,
                "text": text, "ersatz": "[BEGRIFF]", "seiten": [], "anzahl": 1,
                "kontext": "in der Vorschau hinzugefügt", "quellen": ["vorschau"], "sicherheit": 1.0,
                "hinweis": None}
        ergebnis["funde"].append(fund)
        index = len(ergebnis["funde"]) - 1
        if self.baum.exists(str(pdf)):
            self._fund_zeile_einfuegen(pdf, index, fund, "an")
            # manuelle Zeilen bleiben am Ende der Liste
            for mid in self.manuell.get(pdf, {}):
                if self.baum.exists(f"{pdf}::m{mid}"):
                    self.baum.move(f"{pdf}::m{mid}", str(pdf), "end")
        self._log(f"ℹ {self._anzeigename(pdf)}: „{text}“ wird überall in diesem Dokument geschwärzt "
                  f"(IMMER-Begriff für diesen Lauf).", "hinweis")
        self._nach_aenderung(pdf)
        return index

    def _datei_setzen(self, iid, zustand):
        if self.laeuft or not self.baum.exists(iid):
            return
        pdf = self.zeilen.get(iid)
        for kind in self.baum.get_children(iid):
            self._kind_setzen(pdf, kind, zustand == "an")
        self._nach_aenderung(pdf)

    def alle_setzen(self, zustand):
        """Alle Funde aller Dateien an („an“) oder aus („aus“)."""
        if self.laeuft:
            return
        for iid in self.baum.get_children(""):
            self._datei_setzen(iid, zustand)

    def kategorie_setzen(self, anzeige, zustand):
        """Alle Funde einer Kategorie (Anzeigename) in allen Dateien an/aus."""
        if self.laeuft:
            return
        for iid in self.baum.get_children(""):
            pdf = self.zeilen.get(iid)
            for kind in self.baum.get_children(iid):
                if _ohne_marke(self.baum.set(kind, "kategorie")) == _ohne_marke(anzeige):
                    self._kind_setzen(pdf, kind, zustand == "an")
            self._nach_aenderung(pdf)
        self._start_knopf_aktualisieren()

    def _kontextmenue(self, ereignis):
        zeile = self.baum.identify_row(ereignis.y)
        menue = tk.Menu(self.root, tearoff=0)
        if zeile:
            self.baum.selection_set(zeile)
            self.baum.focus(zeile)
            datei = zeile if zeile in self.zeilen else self.baum.parent(zeile)
            name = self.beschriftungen.get(datei, "")
            menue.add_command(label=f"Vorschau von „{name}“ öffnen",
                              command=lambda: self._vorschau_fuer_zeile(zeile))
            menue.add_separator()
            menue.add_command(label=f"Alle Funde von „{name}“ anhaken",
                              command=lambda: self._datei_setzen(datei, "an"))
            menue.add_command(label=f"Alle Funde von „{name}“ abhaken",
                              command=lambda: self._datei_setzen(datei, "aus"))
            if zeile not in self.zeilen:
                kategorie = self.baum.set(zeile, "kategorie")
                menue.add_separator()
                menue.add_command(label=f"Kategorie „{kategorie}“ überall anhaken",
                                  command=lambda: self.kategorie_setzen(kategorie, "an"))
                menue.add_command(label=f"Kategorie „{kategorie}“ überall abhaken",
                                  command=lambda: self.kategorie_setzen(kategorie, "aus"))
            menue.add_separator()
            menue.add_command(label="Datei aus der Liste entfernen", command=lambda: self.datei_entfernen(datei))
            menue.add_separator()
        menue.add_command(label="Alle an", command=lambda: self.alle_setzen("an"))
        menue.add_command(label="Alle aus", command=lambda: self.alle_setzen("aus"))
        try:
            menue.tk_popup(ereignis.x_root, ereignis.y_root)
        finally:
            menue.grab_release()

    def _auswahl_geaendert(self, ereignis=None):
        """Statuszeile: vollständiger Pfad der gewählten Datei bzw. vollständiger Kontext des Funds."""
        if self.laeuft:
            return
        auswahl = self.baum.selection()
        if not auswahl:
            return
        iid = auswahl[0]
        if iid in self.zeilen:
            self.status_label.config(text=f"Datei: {self._pfad_passend(self.zeilen[iid])}")
            return
        pdf = self.zeilen.get(self.baum.parent(iid))
        art, nummer = self._kind_art(iid)
        if art == "fund" and pdf in self.analyse_ergebnisse:
            fund = self.analyse_ergebnisse[pdf]["funde"][nummer]
            teile = [f"Seite(n) {', '.join(map(str, fund.get('seiten') or [])) or '?'}"]
            if fund.get("hinweis"):
                teile.append(f"Hinweis: {fund['hinweis']}")
            teile.append(f"Kontext: {str(fund.get('kontext', '')).replace(chr(10), ' ')}")
            self.status_label.config(text=" · ".join(teile))
        elif art == "manuell":
            self.status_label.config(text="Manuelle Markierung aus der Vorschau – Kästchen schaltet sie an/aus.")

    def _pfad_passend(self, pfad: Path) -> str:
        """Voller Pfad, wenn er in die Statuszeile passt; sonst in der Mitte gekürzt (Dateiname bleibt sichtbar)."""
        text = str(pfad)
        try:
            breite = self.status_label.winfo_width() - self.f_normal.measure("Datei: ") - 8
        except tk.TclError:
            return text
        if breite < 100 or self.f_normal.measure(text) <= breite:
            return text
        teile = pfad.parts
        kandidat = f"…{os.sep}{pfad.name}"
        for i in range(1, len(teile) - 1):
            versuch = str(Path(*teile[:i + 1])) + f"{os.sep}…{os.sep}{pfad.name}"
            if self.f_normal.measure(versuch) > breite:
                break
            kandidat = versuch
        return kandidat

    def _angehakte_funde(self) -> int:
        """Angehakte (auch teilweise) Funde und manuelle Markierungen aller Dateien."""
        return sum(1 for e in self.baum.get_children("") for k in self.baum.get_children(e)
                   if self._zustand(k) in ("an", "teil"))

    def _nebenkanal_dateien(self) -> list[Path]:
        """Analysierte Dateien mit Personendaten in Metadaten, Lesezeichen, Anhängen oder XFA (R-04): auch ohne
        Fund auf den Seiten gibt es eine bereinigte Ausgabe."""
        return [pdf for pdf in self.dateien if pdf in self.analyse_ergebnisse
                and not self.analyse_ergebnisse[pdf].get("fehler")
                and _nebenkanal_bezug(self.analyse_ergebnisse[pdf]) is not None]

    def _start_knopf_aktualisieren(self):
        aktiv = not self.laeuft and not self.analyse_veraltet and (self._angehakte_funde() > 0
                                                                   or bool(self._nebenkanal_dateien()))
        self.start_knopf.config(state="normal" if aktiv else "disabled")

    # ------------------------------------------------------------------
    # Vorschau
    # ------------------------------------------------------------------
    def _vorschau_fuer_zeile(self, zeile):
        if not self.baum.exists(zeile):
            return
        if zeile in self.zeilen:
            self.vorschau_oeffnen(self.zeilen[zeile])
            return
        pdf = self.zeilen.get(self.baum.parent(zeile))
        art, nummer = self._kind_art(zeile)
        seite, markieren = None, None
        if art == "fund" and pdf in self.analyse_ergebnisse:
            fund = self.analyse_ergebnisse[pdf]["funde"][nummer]
            seiten = fund.get("seiten") or []
            stellen = fund.get("stellen") or []
            seite = stellen[0]["seite"] if stellen else (seiten[0] - 1 if seiten else None)
            markieren = nummer
        elif art == "manuell":
            eintrag = self.manuell.get(pdf, {}).get(nummer)
            seite = eintrag["seite"] if eintrag else None
        if pdf is not None:
            self.vorschau_oeffnen(pdf, seite=seite, modus="vorher", markieren=markieren)

    def vorschau_auswahl(self):
        """Knopf „Vorschau …“: Vorschau der gewählten Datei (sonst der ersten zu prüfenden bzw. ersten)."""
        auswahl = self.baum.selection()
        if auswahl:
            self._vorschau_fuer_zeile(auswahl[0])
            return
        zu_pruefen = [p for p in self.dateien if self.ausgaben.get(p, {}).get("status") == "pruefen"]
        kandidaten = zu_pruefen or [p for p in self.dateien if p in self.analyse_ergebnisse]
        if not kandidaten:
            self._dialog("info", "Vorschau", "Bitte zuerst Dateien hinzufügen und analysieren – dann zeigt die "
                                             "Vorschau jede Seite mit allen Fundstellen.")
            return
        self.vorschau_oeffnen(kandidaten[0])

    def ausgabe_vorhanden(self, pdf: Path) -> bool:
        eintrag = self.ausgaben.get(pdf)
        return bool(eintrag) and eintrag.get("pfad") is not None and eintrag["status"] in ("fertig", "pruefen") \
            and Path(eintrag["pfad"]).exists()

    def vorschau_oeffnen(self, pdf: Path, seite: int | None = None, modus: str | None = None, markieren=None):
        """Öffnet (oder holt nach vorn) das Vorschau-Fenster einer Datei. modus: "vorher" (geplante Schwärzung)
        oder "nachher" (Ausgabe mit Verdachtsstellen); ohne Angabe: Ausgabe, wenn sie noch zu prüfen ist."""
        from .vorschau_fenster import VorschauFenster
        if modus is None:
            modus = "nachher" if self.ausgabe_vorhanden(pdf) and (
                self.ausgaben[pdf]["status"] == "pruefen" or pdf not in self.analyse_ergebnisse) else "vorher"
        if modus == "nachher" and not self.ausgabe_vorhanden(pdf):
            modus = "vorher"
        if modus == "vorher" and pdf not in self.analyse_ergebnisse:
            self._dialog("info", "Vorschau", f"„{self._anzeigename(pdf)}“ ist noch nicht analysiert – bitte zuerst "
                                             f"unten „Analysieren“ drücken.")
            return None
        if modus == "vorher":
            art = dateien.datei_art(self._arbeitsdatei(pdf))
            if not dateien.fuer_engine_erlaubt(art):          # R-01: nie eine Nicht-PDF an PyMuPDFs Seitenfunktionen
                self._dialog("error", "Vorschau nicht möglich",
                             f"„{self._anzeigename(pdf)}“ ist keine PDF mehr, sondern {dateien.art_beschreibung(art)} "
                             f"(Datei inzwischen ersetzt?). Bitte aus der Liste entfernen und neu hinzufügen.")
                return None
        fenster = self.vorschauen.get(pdf)
        try:
            if fenster is not None and fenster.existiert():
                fenster.modus_wechseln(modus, seite=seite, markieren=markieren)
                fenster.nach_vorn()
                return fenster
            fenster = VorschauFenster(self, pdf, modus=modus, seite=seite or 0, markieren=markieren)
            if not fenster.existiert():
                return None
        except Exception as fehler:
            pfad = dateien.fehler_protokollieren(*sys.exc_info())
            self._dialog("error", "Vorschau nicht möglich",
                         f"Die Vorschau von „{self._anzeigename(pdf)}“ konnte nicht geöffnet werden:\n"
                         f"{_verstaendliche_fehlermeldung(fehler, pdf)}\n\nDetails: {pfad or 'fehler.log'}")
            return None
        self.vorschauen[pdf] = fenster
        return fenster

    def vorschau_geschlossen(self, pdf: Path):
        self.vorschauen.pop(pdf, None)

    def _vorschauen_schliessen(self):
        for fenster in list(self.vorschauen.values()):
            fenster.schliessen(benachrichtigen=False)
        self.vorschauen.clear()
        self._vorschau_dateien_freigeben()

    @staticmethod
    def _vorschau_dateien_freigeben(pfad: Path | None = None):
        """Zwischengespeicherte PDF-Dokumente der Vorschau (Attrappe und Vorschau-Modul der Engine) freigeben –
        vor dem Umbenennen/Löschen einer Ausgabe (unter Windows verhindert ein offener Handle beides)."""
        attrappen.cache_leeren(pfad)
        from .vorschau_fenster import engine_zwischenspeicher_leeren
        engine_zwischenspeicher_leeren()

    def naechste_zu_pruefen(self, nach: Path | None = None) -> Path | None:
        """Nächste Datei (in Listenreihenfolge nach „nach“), deren Ausgabe noch freigegeben werden muss."""
        reihe = [p for p in self.dateien if self.ausgabe_vorhanden(p) and self.ausgaben[p]["status"] == "pruefen"]
        if nach in self.dateien:
            spaeter = [p for p in reihe if self.dateien.index(p) > self.dateien.index(nach)]
            reihe = spaeter + [p for p in reihe if p not in spaeter]
        reihe = [p for p in reihe if p != nach]
        return reihe[0] if reihe else None

    def ausgabe_freigeben(self, pdf: Path) -> Path | None:
        """Ausgabe einer Datei freigeben (schwaerzung.freigeben bzw. Attrappe): _PRUEFEN entfällt."""
        eintrag = self.ausgaben.get(pdf)
        if self.laeuft or not eintrag or eintrag.get("pfad") is None:
            return None
        alt = Path(eintrag["pfad"])
        self._vorschau_dateien_freigeben(alt)
        try:
            neu = Path(freigeben(alt))
        except Exception as fehler:
            log = dateien.fehler_protokollieren(*sys.exc_info())
            self._dialog("error", "Freigabe nicht möglich",
                         f"„{alt.name}“ konnte nicht freigegeben werden:\n{_verstaendliche_fehlermeldung(fehler, alt)}"
                         + (f"\n\nDetails: {log}" if log else ""))
            return None
        eintrag.update(pfad=neu, status="fertig", grund="freigegeben", freigegeben=True)
        self._ereignis(f"{alt.name} freigegeben → {neu.name}")
        self._log(f"✔ {self._anzeigename(pdf)}: freigegeben  →  {neu}", "ok")
        self._ausgabe_zeile_setzen(pdf)
        self._status(f"„{self._anzeigename(pdf)}“ freigegeben: {neu.name}")
        return neu

    def ausgabe_verwerfen(self, pdf: Path) -> bool:
        """Ausgabe löschen (schwaerzung.verwerfen bzw. Attrappe) – das Original bleibt unberührt."""
        eintrag = self.ausgaben.get(pdf)
        if self.laeuft or not eintrag or eintrag.get("pfad") is None:
            return False
        alt = Path(eintrag["pfad"])
        self._vorschau_dateien_freigeben(alt)
        try:
            verwerfen(alt)
        except Exception as fehler:
            log = dateien.fehler_protokollieren(*sys.exc_info())
            self._dialog("error", "Verwerfen nicht möglich",
                         f"„{alt.name}“ konnte nicht gelöscht werden:\n{_verstaendliche_fehlermeldung(fehler, alt)}"
                         + (f"\n\nDetails: {log}" if log else ""))
            return False
        eintrag.update(pfad=None, status="verworfen", grund=f"{alt.name} gelöscht")
        self._ereignis(f"{alt.name} verworfen (gelöscht)")
        self._log(f"ℹ {self._anzeigename(pdf)}: Ausgabe {alt.name} verworfen (gelöscht).", "hinweis")
        self._ausgabe_zeile_setzen(pdf)
        return True

    def nachschwaerzen(self, pdf: Path, verdachte: list) -> bool:
        """Verdachtsstellen der Ausgabe als manuelle Markierungen übernehmen und die Datei erneut schwärzen;
        die alte Ausgabe wird nach Erfolg verworfen. Liefert True, wenn der Lauf gestartet wurde."""
        eintrag = self.ausgaben.get(pdf)
        if self.laeuft or not eintrag or not verdachte or pdf not in self.analyse_ergebnisse:
            return False
        if not (self.kann_manuelle_stellen() or self.kann_manuelle_bereiche()):
            self._dialog("warning", "Nachschwärzen nicht möglich",
                         "Diese Programmversion kann noch keine einzelnen Stellen nachschwärzen. Bitte den Text "
                         "in die IMMER-Liste eintragen und erneut analysieren und schwärzen.")
            return False
        from .vorschau_fenster import verdacht_zu_markierungen
        neue = 0
        for verdacht in verdachte:
            for markierung in verdacht_zu_markierungen(self, pdf, verdacht):
                markierung["herkunft"] = "nachschwaerzen"
                if self.manuell_hinzufuegen(pdf, markierung) is not None:
                    neue += 1
        if not neue:
            fenster = self.vorschauen.get(pdf)
            self._dialog("warning", "Nachschwärzen nicht möglich",
                         "Für die markierten Stellen ist keine Lage auf der Seite bekannt (z. B. Text aus "
                         "einem Scan). Bitte in „Geplante Schwärzung“ einen Rahmen um die Stelle ziehen oder "
                         "den Text in die IMMER-Liste eintragen und erneut schwärzen.",
                         eltern=fenster.fenster if fenster is not None and fenster.existiert() else None)
            return False
        return self.schwaerzen(nur=[pdf], ersetzt=Path(eintrag["pfad"]))

    # ------------------------------------------------------------------
    # Einstellungen (Schutzstufe, Kategorien, Listen, Freigabe)
    # ------------------------------------------------------------------
    @staticmethod
    def _zeilen_aus(feld) -> list[str]:
        return [z.strip() for z in feld.get("1.0", "end").splitlines() if z.strip()]

    def profil_kategorien(self, name: str) -> set[str] | None:
        """Aktive Kategorien einer Schutzstufe (muster.PROFILE, sonst Attrappe)."""
        alle = set(self.kategorie_vars)
        menge = attrappen.profil_kategorien(PROFILE, name, alle)
        if menge is None:
            menge = attrappen.profil_kategorien(attrappen.PROFILE, name, alle)
        return menge

    def _aktive_kategorien(self) -> set[str]:
        return {k for k, v in self.kategorie_vars.items() if v.get()}

    def _profil_anwenden(self, name: str):
        """Häkchen auf die Kategorien der Schutzstufe setzen (ohne „Benutzerdefiniert“ auszulösen)."""
        menge = self.profil_kategorien(name)
        if menge is None:
            return
        self._profil_wird_gesetzt = True
        try:
            for schluessel, var in self.kategorie_vars.items():
                var.set(schluessel in menge)
        finally:
            self._profil_wird_gesetzt = False

    def _profil_beschreibung_anzeigen(self):
        name = self.profil_var.get()
        text = attrappen.profil_beschreibung(PROFILE, name, KATEGORIEN)
        if name == attrappen.BENUTZERDEFINIERT:
            text = (f"Eigene Auswahl der Kategorien (Erkennungsregeln der Stufe „{_profil_name(self.basis_profil)}“).")
            if set(_profil_wert(PROFILE, self.basis_profil, "hinweis") or ()) & GESUNDHEIT_KATEGORIEN \
                    - self._aktive_kategorien():
                text += " Nicht angehakte Gesundheitsdaten werden gemeldet und abgewählt angeboten."
        self.profil_beschreibung.config(text=text)

    @staticmethod
    def _mindestens_so_stark(neu: str, basis: str) -> bool:
        """Ist die Stufe `neu` mindestens so streng wie die Grundstufe `basis`? Reihenfolge Ausgewogen < Hoch <
        Maximal; dazu dürfen keine Erkennungsregeln (muster.PROFILE "optionen", z. B. alle_geburtsdaten) und keine
        Hinweis-Kategorien der Grundstufe fehlen. Nur auf eine solche Stufe springt die Auswahl von selbst."""
        reihenfolge = attrappen.PROFIL_REIHENFOLGE
        if neu in reihenfolge and basis in reihenfolge and reihenfolge.index(neu) < reihenfolge.index(basis):
            return False
        optionen_neu = _profil_wert(PROFILE, neu, "optionen") or {}
        optionen_basis = _profil_wert(PROFILE, basis, "optionen") or {}
        if any(an and not optionen_neu.get(schluessel) for schluessel, an in dict(optionen_basis).items()):
            return False
        return set(_profil_wert(PROFILE, basis, "hinweis") or ()) <= set(_profil_wert(PROFILE, neu, "hinweis") or ())

    def _profil_gewaehlt(self):
        """Radioknopf der Schutzstufe angeklickt."""
        name = self.profil_var.get()
        if name != attrappen.BENUTZERDEFINIERT:
            self.basis_profil = name
            self._profil_anwenden(name)
        self._profil_beschreibung_anzeigen()
        self._einstellung_geaendert()

    def _kategorie_geaendert(self, *_):
        """Häkchen einer Kategorie geändert: Stufe nachführen. Passt die Auswahl genau zu einer Stufe, die mindestens
        so streng ist wie die Grundstufe (Ausgewogen + E-Mail -> Hoch), gilt diese; sonst „Benutzerdefiniert“ mit den
        Erkennungsregeln der Grundstufe – „Maximal“ ohne Diagnosen und Medikamente bleibt also „Maximal“ (alle
        Geburtsdaten, unbekannte Eigennamen) und springt nicht auf das schwächere „Hoch“ mit derselben
        Kategorienmenge."""
        if not self._profil_wird_gesetzt and not self._einstellungen_werden_gesetzt:
            aktive = self._aktive_kategorien()
            aktuell = self.profil_var.get()
            if aktuell == attrappen.BENUTZERDEFINIERT or self.profil_kategorien(aktuell) != aktive:
                passend = [n for n in attrappen.PROFIL_REIHENFOLGE if self.profil_kategorien(n) == aktive
                           and self._mindestens_so_stark(n, self.basis_profil)]
                if aktuell in passend:
                    neu = aktuell
                elif passend:
                    neu = passend[0]
                else:
                    neu = attrappen.BENUTZERDEFINIERT
                if neu != attrappen.BENUTZERDEFINIERT:
                    self.basis_profil = neu
                self.profil_var.set(neu)
            self._profil_beschreibung_anzeigen()
        self._einstellung_geaendert()

    def _einstellungen_anwenden(self):
        e = self.einstellungen
        self._einstellungen_werden_gesetzt = True
        try:
            echte = attrappen.PROFIL_REIHENFOLGE
            profil = e.get("profil")
            basis = e.get("basis_profil")
            kategorien = e.get("kategorien") if isinstance(e.get("kategorien"), dict) else None
            if profil not in echte + (attrappen.BENUTZERDEFINIERT,):
                # ältere Einstellungen ohne Schutzstufe: unveränderter Standard -> neue Standardstufe,
                # eigene Auswahl bleibt „Benutzerdefiniert“
                standard = attrappen._standard_kategorien(KATEGORIEN)
                gespeichert = {k for k, v in (kategorien or {}).items() if v and k in self.kategorie_vars}
                if kategorien is None or gespeichert == (standard & set(self.kategorie_vars)):
                    profil = attrappen.STANDARD_PROFIL
                else:
                    profil = attrappen.BENUTZERDEFINIERT
            self.basis_profil = basis if basis in echte else (profil if profil in echte else attrappen.STANDARD_PROFIL)
            self.profil_var.set(profil)
            if profil == attrappen.BENUTZERDEFINIERT:
                self._profil_anwenden(self.basis_profil)
                for schluessel, var in self.kategorie_vars.items():
                    if kategorien and schluessel in kategorien:
                        var.set(bool(kategorien[schluessel]))
            else:
                self._profil_anwenden(profil)
            self._profil_beschreibung_anzeigen()
            for feld, schluessel in ((self.immer_feld, "immer"), (self.nie_feld, "nie")):
                werte = e.get(schluessel)
                if isinstance(werte, list):
                    feld.delete("1.0", "end")
                    feld.insert("1.0", "\n".join(str(w) for w in werte))
                feld.edit_modified(False)
            if isinstance(e.get("zielordner"), str):
                self.zielordner_var.set(e["zielordner"])
            self.zielordner_aktiv.set(bool(e.get("zielordner_aktiv", False)))
            self.freigabe_var.set(bool(e.get("freigabe_erforderlich", True)))
        finally:
            self._einstellungen_werden_gesetzt = False

    def _einstellungen_sammeln(self) -> dict:
        # Erst den Stand auf der Festplatte lesen und nur die eigenen Schlüssel überschreiben (GR-10)
        daten = dict(self.einstellungen)
        daten.update(dateien.einstellungen_laden())
        daten.update({
            "version": __version__,
            "profil": self.profil_var.get(),
            "basis_profil": self.basis_profil,
            "kategorien": {k: bool(v.get()) for k, v in self.kategorie_vars.items()},
            "immer": self._zeilen_aus(self.immer_feld),
            "nie": self._zeilen_aus(self.nie_feld),
            "zielordner": self.zielordner_var.get().strip(),
            "zielordner_aktiv": bool(self.zielordner_aktiv.get()),
            "freigabe_erforderlich": bool(self.freigabe_var.get()),
            "maximiert": self._ist_maximiert(),
            "hinweis_gelesen": bool(self.hinweis_gelesen),
        })
        if not daten["maximiert"]:
            try:
                daten["fenster"] = self.root.geometry()
            except tk.TclError:
                pass
        return daten

    def einstellungen_speichern(self):
        self.einstellungen = self._einstellungen_sammeln()
        if not dateien.einstellungen_speichern(self.einstellungen):
            self._log("⚠ Einstellungen konnten nicht gespeichert werden (Ordner nicht beschreibbar).", "warnung",
                      zaehlen=False)

    def _text_geaendert(self, ereignis):
        feld = ereignis.widget
        if feld.edit_modified():
            feld.edit_modified(False)
            self._einstellung_geaendert()

    def _einstellung_geaendert(self, *_):
        """Stufe, Kategorie, Liste oder Kundenliste geändert: eine vorhandene Analyse passt nicht mehr ->
        zurücksetzen (auch Vorschau-Fenster und manuelle Markierungen)."""
        if self._einstellungen_werden_gesetzt or self.laeuft or not self.analyse_ergebnisse:
            return
        self.analyse_veraltet = True
        self.analyse_ergebnisse.clear()
        markierungen = sum(len(m) for m in self.manuell.values())
        self.manuell.clear()
        # Vorschau der geplanten Schwärzung passt nicht mehr; eine noch zu prüfende Ausgabe bleibt sichtbar
        for pdf, fenster in list(self.vorschauen.items()):
            if self.ausgabe_vorhanden(pdf):
                fenster.modus_wechseln("nachher")
            else:
                fenster.schliessen()
        for iid in self.zeilen:
            if self.baum.exists(iid):
                self.baum.delete(*self.baum.get_children(iid))
                self.baum.set(iid, "kategorie", "erneut analysieren")
                self.baum.set(iid, "anzahl", "")
                self._zustand_setzen(iid, "aus")
        self._start_knopf_aktualisieren()
        self._status("Einstellungen geändert – bitte erneut analysieren.")
        self._log("ℹ Schutzstufe, Kategorien oder Listen wurden geändert – die Fundliste wurde zurückgesetzt. "
                  "Bitte erneut analysieren.", "hinweis")
        if markierungen:
            self._log(f"ℹ {markierungen} manuelle Markierung(en) aus der Vorschau wurden verworfen – bitte nach "
                      f"der Analyse erneut setzen.", "hinweis")

    # ------------------------------------------------------------------
    # Kundenliste
    # ------------------------------------------------------------------
    def _kundenliste_nutzbar(self) -> bool:
        return self.kundenliste is not None and kann(analysiere_pdf, "kundenliste") \
            and not getattr(self.kundenliste, "attrappe", False)

    def _kundenliste_laden(self):
        try:
            self.kundenliste = Kundenliste.laden(dateien.kundenliste_pfad())
        except Exception:
            self.kundenliste = None
            dateien.fehler_protokollieren(*sys.exc_info())
            self._log("⚠ Die gespeicherte Kundenliste konnte nicht gelesen werden – bitte erneut importieren.",
                      "warnung", zaehlen=False)
        self._kundenliste_anzeigen()

    def _kundenliste_anzeigen(self):
        if self.kundenliste is None:
            text = "keine geladen – optional den Kundenbestand (CSV) importieren, damit bekannte Kunden sicher " \
                   "erkannt werden"
        else:
            anzahl = int(getattr(self.kundenliste, "anzahl_kunden", 0))
            text = f"{anzahl} Kunden geladen – gespeichert ohne Klartext"
            if not self._kundenliste_nutzbar():
                text += " (Abgleich in dieser Programmversion noch nicht aktiv)"
        self.kunden_label.config(text=text)
        self._kunden_knoepfe_aktualisieren()

    def _kunden_knoepfe_aktualisieren(self):
        aktiv = not self.laeuft and self.kundenliste is not None
        self.kunden_entfernen_knopf.config(state="normal" if aktiv else "disabled")
        try:
            self.kunden_menue.entryconfigure(1, state="normal" if aktiv else "disabled")
        except tk.TclError:
            pass

    def kundenliste_importieren(self, pfad=None):
        """Menü/Knopf „Kundenliste importieren …“: CSV wählen, Spalten erkennen (sonst zuordnen lassen)."""
        if self.laeuft:
            self._laeuft_hinweis()
            return
        if pfad is None:
            pfad = filedialog.askopenfilename(
                title="Kundenliste (CSV) auswählen", parent=self.root,
                filetypes=[("CSV-Dateien", "*.csv *.txt"), ("Alle Dateien", "*.*")])
            if not pfad:
                return
        self._kundenliste_import(Path(pfad), None)

    def _kundenliste_import(self, pfad: Path, spalten: dict | None):
        self.spalten_dialog = None
        try:
            liste = Kundenliste.importieren(pfad) if spalten is None else Kundenliste.importieren(pfad, spalten)
        except (ValueError, KeyError, LookupError) as fehler:
            if spalten is None:
                self._spalten_zuordnen(pfad)
                return
            self._dialog("warning", "Kundenliste nicht importiert", f"Die Kundenliste konnte nicht importiert "
                                                                    f"werden:\n{fehler}")
            return
        except Exception as fehler:
            if spalten is None and "spalte" in type(fehler).__name__.lower():
                self._spalten_zuordnen(pfad)              # eigene Ausnahme der Engine für unbekannte Spalten
                return
            log = dateien.fehler_protokollieren(*sys.exc_info())
            self._dialog("error", "Kundenliste nicht importiert",
                         f"„{pfad.name}“ konnte nicht gelesen werden:\n{_verstaendliche_fehlermeldung(fehler, pfad)}"
                         + (f"\n\nDetails: {log}" if log else ""))
            return
        anzahl = int(getattr(liste, "anzahl_kunden", 0) or 0)
        if not anzahl:
            if spalten is None:
                self._spalten_zuordnen(pfad)
                return
            self._dialog("warning", "Kundenliste nicht importiert",
                         "In der CSV-Datei wurde kein Kunde gefunden (leere Spalten?). Es wurde nichts gespeichert.")
            return
        try:
            liste.speichern(dateien.kundenliste_pfad())
        except Exception as fehler:
            log = dateien.fehler_protokollieren(*sys.exc_info())
            self._dialog("error", "Kundenliste nicht gespeichert",
                         f"Die Kundenliste konnte nicht gespeichert werden:\n"
                         f"{_verstaendliche_fehlermeldung(fehler)}" + (f"\n\nDetails: {log}" if log else ""))
            return
        self.kundenliste = liste
        self._kundenliste_anzeigen()
        hinweis = "" if self._kundenliste_nutzbar() else (" Hinweis: Diese Programmversion nutzt die Kundenliste "
                                                           "noch nicht beim Analysieren.")
        self._log(f"✔ Kundenliste: {anzahl} Kunden importiert – gespeichert ohne Klartext (nur Prüfwerte). "
                  f"Die CSV-Datei selbst wurde nicht verändert.{hinweis}", "ok")
        self._einstellung_geaendert()
        self._dialog("info", "Kundenliste importiert",
                     f"{anzahl} Kunden geladen – gespeichert ohne Klartext.\n\nDas Programm merkt sich nur "
                     f"nicht umkehrbare Prüfwerte, keine Namen oder Nummern. Die CSV-Datei wurde nicht verändert und "
                     f"kann gelöscht werden, wenn sie sonst nicht gebraucht wird.{hinweis}")

    def _spalten_zuordnen(self, pfad: Path):
        try:
            vorschau = dateien.csv_vorschau(pfad)
        except (OSError, ValueError) as fehler:
            self._dialog("error", "Kundenliste nicht lesbar", f"„{pfad.name}“ ist keine lesbare CSV-Datei:\n{fehler}")
            return
        if not vorschau["zeilen"]:
            self._dialog("warning", "Kundenliste leer", f"„{pfad.name}“ enthält keine Daten.")
            return
        self.spalten_dialog = SpaltenDialog(self, pfad, vorschau,
                                            lambda spalten: self._kundenliste_import(pfad, spalten))

    def kundenliste_entfernen(self):
        if self.laeuft:
            self._laeuft_hinweis()
            return
        pfad = dateien.kundenliste_pfad()
        if self.kundenliste is None and not pfad.exists():
            self._dialog("info", "Keine Kundenliste", "Es ist keine Kundenliste gespeichert.")
            return
        anzahl = int(getattr(self.kundenliste, "anzahl_kunden", 0) or 0) if self.kundenliste else 0
        if not self._frage("Kundenliste entfernen", f"Die gespeicherte Kundenliste ({anzahl} Kunden) wird "
                                                     f"gelöscht. Fortfahren?"):
            return
        try:
            if hasattr(Kundenliste, "entfernen"):
                Kundenliste.entfernen(pfad)
            elif pfad.exists():
                pfad.unlink()
        except OSError as fehler:
            self._dialog("error", "Kundenliste nicht entfernt", _verstaendliche_fehlermeldung(fehler, pfad))
            return
        self.kundenliste = None
        self._kundenliste_anzeigen()
        self._log("ℹ Kundenliste entfernt.", "hinweis")
        self._einstellung_geaendert()

    # ------------------------------------------------------------------
    # Lauf-Verwaltung (Sperren, Fortschritt, Abbruch)
    # ------------------------------------------------------------------
    def _eingaben_sperren(self, sperren: bool):
        zustand = "disabled" if sperren else "normal"
        for w in self._sperrbar:
            try:
                w.config(state=zustand)
            except tk.TclError:
                pass
        self.drop_zone.config(fg=FARBE_TEXT_GRAU if sperren else FARBE_AKZENT,
                              cursor="arrow" if sperren else "hand2")
        self._kunden_knoepfe_aktualisieren()
        for fenster in self.vorschauen.values():
            fenster.sperren(sperren)

    def _lauf_starten(self, art: str):
        self.laeuft = True
        self.lauf_art = art
        self.abbruch = threading.Event()
        self.ocr = None
        self.warnungen_anzahl = 0
        self._warnzaehler_anzeigen()
        self._eingaben_sperren(True)
        analyse_text = "  Analysiere …  " if art == "analyse" else ANALYSE_TEXT
        start_text = "  Läuft …  " if art == "schwaerzen" else START_TEXT
        self.analyse_knopf.config(state="disabled", text=analyse_text,
                                  underline=-1 if analyse_text != ANALYSE_TEXT else
                                  _kuerzel_index(ANALYSE_TEXT, KUERZEL["analyse"]))
        self.start_knopf.config(state="disabled", text=start_text,
                                underline=-1 if start_text != START_TEXT else _kuerzel_index(START_TEXT,
                                                                                             KUERZEL["start"]))
        self.abbrechen_knopf.config(state="normal")
        self.ordner_knopf.config(state="disabled")
        self.fortschritt.config(value=0, maximum=1)
        titel = "Analyse" if art == "analyse" else "Schwärzung"
        self._trenner(f"{titel} {datetime.now():%d.%m.%Y %H:%M:%S} · Schutzstufe {_profil_name(self.basis_profil)}")

    def _lauf_beenden(self):
        self.laeuft = False
        self.lauf_art = None
        self.laeufe_beendet += 1
        self.abbruch = None
        self.ocr = None
        self._eingaben_sperren(False)
        self.analyse_knopf.config(state="normal", text=ANALYSE_TEXT,
                                  underline=_kuerzel_index(ANALYSE_TEXT, KUERZEL["analyse"]))
        self.start_knopf.config(text=START_TEXT, underline=_kuerzel_index(START_TEXT, KUERZEL["start"]))
        self.abbrechen_knopf.config(state="disabled")
        self.ordner_knopf.config(state="normal" if self.letzte_ausgabeordner else "disabled")
        self._start_knopf_aktualisieren()

    def _ocr_dienst_anlegen(self):
        """Ein OCR-Dienst je Lauf (im Arbeits-Thread angelegt, damit die Oberfläche nicht wartet)."""
        try:
            return OcrDienst()
        except Exception as fehler:
            self._log(f"⚠ OCR-Dienst konnte nicht gestartet werden ({fehler}) – OCR läuft ohne Hilfsprozesse.",
                      "warnung")
            return None

    @staticmethod
    def _ocr_schliessen(ocr):
        if ocr is None:
            return
        try:
            ocr.schliessen()
        except Exception:
            pass

    def abbrechen(self):
        if not self.laeuft or self.abbruch is None:
            return
        self.abbruch.set()
        ocr = self.ocr
        if ocr is not None:
            try:
                ocr.abbrechen()
            except Exception:
                pass
        self.abbrechen_knopf.config(state="disabled")
        self._status("Abbruch angefordert – die aktuelle Seite wird noch beendet …")
        self._log("Abbruch angefordert …", "warnung", zaehlen=False)

    def _laeuft_hinweis(self):
        self._dialog("info", "Lauf läuft noch",
                     "Gerade läuft noch eine Analyse oder Schwärzung. Bitte warten oder „Abbrechen“ drücken.")

    def schliessen(self):
        """Fenster schließen (Rückfrage, solange ein Lauf aktiv ist); Einstellungen sichern, Sperre freigeben.
        Wartet gerade eine Auswahl auf eine Rückfrage (Kennwort, Fotos …), wird sie zuerst abgebrochen – erst danach
        schließt das Fenster, damit keine (entschlüsselte) Arbeitskopie mehr entsteht oder liegen bleibt."""
        if self.beendet:
            return
        if self._hinzufuegen_laeuft:
            self._schliessen_angefordert = True
            dialog = self.kennwort_dialog
            if dialog is not None:
                dialog.abbrechen()                      # wie „Überspringen“; _pdfs_hinzufuegen schließt danach
            return
        if self.laeuft:
            antwort = messagebox.askyesno(
                "Lauf läuft noch",
                "Es läuft noch eine Analyse oder Schwärzung. Wirklich beenden?\n\n"
                "Bereits fertige Ausgabedateien bleiben erhalten; die aktuelle Datei wird nicht fertig.",
                icon="warning", parent=self.root)
            self.letzter_dialog = ("askyesno", "Lauf läuft noch", str(antwort))
            if not antwort:
                return
            self.abbrechen()
        try:
            self.einstellungen_speichern()
        except Exception:
            pass
        self.beendet = True
        self._aufraeumen()
        self.root.destroy()

    def _aufraeumen(self):
        """Prozessweite Zustände zurückgeben (KQ-10): threading.excepthook, Einzelinstanz-Sperre, ausstehende
        after()-Aufrufe; Arbeitskopien (Bild als PDF, entschlüsselte PDF) dieser Sitzung löschen – endgültig: danach
        entsteht keine neue Arbeitskopie mehr. Lässt sich etwas nicht löschen (unter Windows hält ein noch laufender
        Analyse- oder Schwärz-Thread die Kopie offen), wird es nach dem Ende des Threads erneut versucht."""
        for kennung in self._nach_start:
            try:
                self.root.after_cancel(kennung)
            except (tk.TclError, ValueError):
                pass
        self._nach_start.clear()
        if threading.excepthook == self._thread_excepthook:
            threading.excepthook = self._alter_threading_haken
        try:
            self._vorschau_dateien_freigeben()
        except Exception:
            pass
        kopien = [Path(e["pfad"]) for e in self.arbeitskopien.values() if e and e.get("pfad")]
        for pdf in list(self.arbeitskopien):
            self._arbeitskopie_loeschen(pdf)
        sitzung = dateien.aktuelle_sitzung()
        if not dateien.sitzung_aufraeumen(endgueltig=True) and sitzung is not None:
            self._reste_spaeter_loeschen(sitzung, kopien)
        if self.instanz_sperre is not None:
            self.instanz_sperre.freigeben()
            self.instanz_sperre = None

    def _reste_spaeter_loeschen(self, sitzung: Path, kopien: list):
        """Arbeitskopien, die beim Beenden noch geöffnet waren (Windows löscht keine offene Datei; der Analyse- bzw.
        Schwärz-Thread liest sie noch), nach dem Ende des Threads löschen. Ein eigener, nicht im Hintergrund
        laufender Thread hält das Programm so lange am Leben (höchstens RESTE_WARTEN_S Sekunden). Bleibt trotzdem
        etwas übrig, steht das in fehler.log – der nächste Programmstart löscht es."""
        schluessel = str(sitzung)
        if schluessel in self._reste_threads and self._reste_threads[schluessel].is_alive():
            return
        lauf = self._lauf_thread

        def spaeter():
            ende = time.monotonic() + RESTE_WARTEN_S
            if lauf is not None and lauf.is_alive():
                lauf.join(max(0.1, ende - time.monotonic()))
            while True:
                for kopie in kopien:
                    dateien.arbeitskopie_entfernen(kopie)
                if dateien.ordner_loeschen(sitzung) or time.monotonic() >= ende:
                    break
                time.sleep(0.25)
            if Path(sitzung).exists():
                hinweis = RuntimeError(f"Arbeitskopien im Programmordner für Zwischendateien ({Path(sitzung).name}) "
                                       f"konnten beim Beenden nicht gelöscht werden (Datei noch geöffnet?) – sie "
                                       f"werden beim nächsten Programmstart gelöscht.")
                dateien.fehler_protokollieren(type(hinweis), hinweis, None)

        faden = threading.Thread(target=spaeter, daemon=False, name="Arbeitskopien-loeschen")
        self._reste_threads[schluessel] = faden
        faden.start()

    # ------------------------------------------------------------------
    # Namenserkennung vorladen (PERF-09)
    # ------------------------------------------------------------------
    def modell_vorladen(self):
        """Lädt das spaCy-Modell kurz nach dem Start im Hintergrund, damit der erste Klick auf „Analysieren“
        nicht hängt. Nur wenn Namen erkannt werden sollen und kein Lauf aktiv ist."""
        if self.beendet or self.laeuft or self.vorladen_thread is not None:
            return
        var = self.kategorie_vars.get("namen")
        if var is not None and not var.get():
            return
        vorher = self.status_label.cget("text")
        self.status_label.config(text="Namenserkennung wird vorbereitet …")

        def laden():
            try:
                with self._ner_sperre:
                    lade_ner()
            except Exception:
                dateien.fehler_protokollieren(*sys.exc_info())
            finally:
                self._im_hauptthread(self._vorladen_fertig, vorher)

        self.vorladen_thread = threading.Thread(target=laden, daemon=True, name="Modell-Vorladen")
        self.vorladen_thread.start()

    def _vorladen_fertig(self, vorher):
        if not self.laeuft and self.status_label.cget("text") == "Namenserkennung wird vorbereitet …":
            self.status_label.config(text=vorher if vorher and vorher != "Bereit." else "Bereit – Namenserkennung "
                                                                                       "geladen.")

    # ------------------------------------------------------------------
    # Analyse
    # ------------------------------------------------------------------
    def _analyse_zusatz(self) -> dict:
        """Optionale Vertragsparameter (Phase 2), soweit analysiere_pdf sie kennt."""
        zusatz = {}
        if kann(analysiere_pdf, "profil"):
            zusatz["profil"] = self.basis_profil
        if self.kundenliste is not None and kann(analysiere_pdf, "kundenliste"):
            zusatz["kundenliste"] = self.kundenliste
        return zusatz

    def analysieren(self):
        if self.laeuft:
            self._laeuft_hinweis()
            return
        if not self.dateien:
            self._dialog("warning", "Keine Dateien", "Bitte zuerst PDF-Dateien auswählen (Schritt 1).")
            return
        self.einstellungen_speichern()
        aktive = self._aktive_kategorien()
        immer = self._zeilen_aus(self.immer_feld)
        nie = self._zeilen_aus(self.nie_feld)
        pdfs = list(self.dateien)                       # Kopie: der Thread arbeitet nie auf der Live-Liste
        immer_je_datei = {pdf: immer + [b for b in self.lauf_immer.get(pdf, []) if b not in immer] for pdf in pdfs}
        zusatz = self._analyse_zusatz()
        arbeit = {pdf: self._arbeitsdatei(pdf) for pdf in pdfs}
        self._lauf_kontext = {"aktive": sorted(aktive), "nie": len(nie), "immer": len(immer),
                              "profil": self.profil_var.get(), "basis_profil": self.basis_profil,
                              "kundenliste": "kundenliste" in zusatz}

        markierungen = sum(len(m) for m in self.manuell.values())
        self._vorschauen_schliessen()
        self.manuell.clear()
        self.analyse_ergebnisse = {}
        self.analyse_veraltet = False
        for iid in self.zeilen:
            self.baum.delete(*self.baum.get_children(iid))
            self.baum.set(iid, "kategorie", "wird analysiert …")
            self.baum.set(iid, "anzahl", "")
            self._zustand_setzen(iid, "aus")
        self._lauf_starten("analyse")
        if markierungen:
            self._log(f"ℹ {markierungen} manuelle Markierung(en) der letzten Vorschau wurden verworfen (neue "
                      f"Analyse) – bitte in der Vorschau erneut setzen.", "hinweis")
        if self.kundenliste is not None and "kundenliste" not in zusatz:
            self._log("ℹ Die Kundenliste wird von dieser Programmversion noch nicht beim Analysieren genutzt.",
                      "hinweis")
        self._status("Analyse startet …")
        self._lauf_thread = threading.Thread(target=self._analyse_lauf,
                                             args=(pdfs, aktive, nie, immer_je_datei, zusatz, self.abbruch, arbeit),
                                             daemon=True, name="Analyse")
        self._lauf_thread.start()

    @staticmethod
    def _keine_pdf_ergebnis(pdf: Path, art: str) -> dict:
        """R-01: Datei ist (inzwischen) keine PDF – nie an PyMuPDFs Seitenfunktionen geben (Absturz im C-Code)."""
        text = (f"Die Datei ist keine PDF, sondern {dateien.art_beschreibung(art)} – sie wurde NICHT geprüft. Bitte im "
                f"Ursprungsprogramm als PDF speichern (bei einem Foto: aus der Liste entfernen und erneut hinzufügen, "
                f"dann wird es als PDF übernommen).")
        ergebnis = _fehler_ergebnis(pdf, text)
        ergebnis["meldungen"] = [{"art": "fehler", "code": "KEIN_PDF", "text": text, "seite": None}]
        return ergebnis

    def _analyse_lauf(self, pdfs, aktive, nie, immer_je_datei, zusatz, abbruch, arbeit=None):
        ergebnisse: dict[Path, dict] = {}
        fehler_intern = None
        erster_fehler = None
        weitergabe_neu = 0
        ocr = None
        arbeit = dict(arbeit or {})
        try:
            ocr = self._ocr_dienst_anlegen()
            self.ocr = ocr
            seiten = {pdf: _seitenzahl(arbeit.get(pdf, pdf)) for pdf in pdfs}
            gesamt_seiten = max(1, sum(seiten.values()))
            self._fortschritt_maximum(gesamt_seiten)
            if "namen" in aktive:
                self._status("Lade Namenserkennungs-Modell …")
                try:
                    with self._ner_sperre:              # wartet ggf. auf das Vorladen (PERF-09)
                        lade_ner()
                except Exception as fehler:
                    dateien.fehler_protokollieren(*sys.exc_info())
                    self._log(f"✖ Namenserkennung konnte nicht geladen werden ({type(fehler).__name__}: {fehler}) "
                              f"– Namen werden in diesem Lauf NICHT erkannt!", "fehler")
            lauf = None
            if LaufWissen is not None and kann(analysiere_pdf, "lauf"):
                try:
                    lauf = LaufWissen()
                except Exception:
                    dateien.fehler_protokollieren(*sys.exc_info())
            if lauf is not None:
                zusatz = dict(zusatz, lauf=lauf)
            basis = 0
            for nr, pdf in enumerate(pdfs, 1):
                if abbruch.is_set():
                    break
                name = self._anzeigename(pdf)
                self._status(f"Analyse: Datei {nr}/{len(pdfs)} – {name}")

                def fortschritt(seite, gesamt, _basis=basis, _nr=nr, _pdf=pdf, _name=name):
                    self._fortschritt_setzen(_basis + min(int(seite), seiten[_pdf]))
                    self._status(f"Analyse: Datei {_nr}/{len(pdfs)}, Seite {seite}/{gesamt} – {_name}")

                datei = arbeit.get(pdf, pdf)
                try:                                        # jede Datei für sich (KQ-03)
                    art = dateien.datei_art(datei)
                    if not dateien.fuer_engine_erlaubt(art):
                        ergebnis = self._keine_pdf_ergebnis(pdf, art)
                    else:
                        ergebnis = analysiere_pdf(datei, aktive, nie, immer_je_datei[pdf],
                                                  melde=lambda t: self._log(t, "grau"), fortschritt=fortschritt,
                                                  abbruch=abbruch, ocr=ocr, **zusatz)
                        ergebnis = _analyse_ergebnis_pruefen(ergebnis, pdf)
                    if ergebnis["fehler"] and ergebnis["fehler"] != "Abgebrochen":
                        ergebnis["fehler"] = _fehlertext_verstaendlich(ergebnis["fehler"])
                except Exception as fehler:
                    log = dateien.fehler_protokollieren(*sys.exc_info())
                    if erster_fehler is None:
                        erster_fehler = (log, fehler)
                    ergebnis = _fehler_ergebnis(pdf, _verstaendliche_fehlermeldung(fehler, pdf))
                ergebnisse[pdf] = ergebnis
                self._analyse_protokollieren(name, ergebnis)
                self._im_hauptthread(self._datei_ergebnis_uebernehmen, pdf, ergebnis)
                basis += seiten[pdf]
                self._fortschritt_setzen(basis)
            if weitergabe_anwenden is not None and not abbruch.is_set():
                gute = [e for e in ergebnisse.values() if not e["fehler"]]
                if len(gute) > 1:
                    try:
                        weitergabe_neu = int(weitergabe_anwenden(gute) or 0)
                    except Exception:
                        dateien.fehler_protokollieren(*sys.exc_info())
                        self._log("⚠ Dokumentübergreifende Suche (Namen aus anderen Dateien dieses Laufs) ist "
                                  "fehlgeschlagen – Details in fehler.log. Die Funde je Datei bleiben gültig.",
                                  "warnung")
        except Exception:
            fehler_intern = sys.exc_info()
        finally:
            self._ocr_schliessen(ocr)
            self._im_hauptthread(self._analyse_fertig, pdfs, ergebnisse, abbruch.is_set(), fehler_intern,
                                 erster_fehler, weitergabe_neu)

    def _datei_ergebnis_uebernehmen(self, pdf: Path, ergebnis: dict):
        """Im Hauptthread: Ergebnis einer Datei übernehmen und ihre Funde eintragen."""
        self.analyse_ergebnisse[pdf] = ergebnis
        self._baum_datei_fuellen(pdf, ergebnis)

    def _analyse_protokollieren(self, name: str, ergebnis: dict):
        codes = meldungs_codes(ergebnis)
        abgebrochen = "ABGEBROCHEN" in codes
        if ergebnis["fehler"]:
            self._log(f"✖ {name}: {ergebnis['fehler']}", "fehler", zaehlen=not abgebrochen)
        for w in ergebnis["warnungen"]:
            if abgebrochen and w.strip() == "Abgebrochen":
                continue                                    # Abbruch nicht doppelt melden (GR-07)
            self._log(f"⚠ {name}: {w}", "warnung")
        for h in ergebnis["hinweise"]:
            self._log(f"ℹ {name}: {h}", "hinweis")
        if not abgebrochen:
            zusatz = f", {ergebnis['seiten']} Seite(n)" if ergebnis["seiten"] else ""
            if ergebnis["ocr_seiten"]:
                zusatz += f", davon {ergebnis['ocr_seiten']} per OCR"
            self._log(f"{name}: {len(ergebnis['funde'])} Fund(e){zusatz}", "grau")

    def _analyse_fertig(self, pdfs, ergebnisse, abgebrochen, fehler_intern, erster_fehler=None, weitergabe_neu=0):
        self.analyse_ergebnisse.update(ergebnisse)
        for pdf in pdfs:
            if pdf not in ergebnisse and str(pdf) in self.zeilen and self.baum.exists(str(pdf)):
                self.baum.set(str(pdf), "kategorie", "nicht analysiert (abgebrochen)" if abgebrochen
                              else "nicht analysiert")
        if weitergabe_neu:
            for pdf, ergebnis in ergebnisse.items():
                self._baum_datei_fuellen(pdf, ergebnis)
        self._lauf_beenden()
        if erster_fehler is not None:
            self._fehler_dialog(*erster_fehler)
        if fehler_intern:
            self._fehler_melden(*fehler_intern)
        self._protokoll_analyse(pdfs, ergebnisse, abgebrochen)
        if abgebrochen:
            self.analyse_veraltet = True
            self._start_knopf_aktualisieren()
            self._log("Analyse abgebrochen – Fundliste unvollständig. Bitte erneut analysieren.", "fehler",
                      zaehlen=False)
            self._status("Analyse abgebrochen – bitte erneut analysieren.")
            return
        if weitergabe_neu:
            self._log(f"ℹ Dokumentübergreifende Suche: {weitergabe_neu} weitere Stelle(n) mit Namen/Kennungen aus "
                      f"anderen Dateien dieses Laufs ergänzt.", "hinweis")

        gesamt = sum(len(e["funde"]) for e in ergebnisse.values())
        # „nur angeboten“ = alle Stellen abgewählt (Gesundheitsdaten in „Hoch“); angehakt zählt wie der Schwärzen-Knopf
        # (Funde und manuelle Markierungen dieser Dateien, auch teilweise angehakt)
        angeboten_funde = [e["funde"][i] for pdf, e in ergebnisse.items() for i in range(len(e["funde"]))
                           if self.fund_zustand(pdf, i) == "aus"]
        angehakt = sum(1 for pdf in ergebnisse if self.baum.exists(str(pdf)) for k in self.baum.get_children(str(pdf))
                       if self._zustand(k) in ("an", "teil"))
        nur_gesundheit = bool(angeboten_funde) and all(f.get("kategorie") in GESUNDHEIT_KATEGORIEN
                                                       for f in angeboten_funde)
        codes = {pdf: meldungs_codes(e) for pdf, e in ergebnisse.items()}
        ohne_text = [pdf for pdf, e in ergebnisse.items() if not e["funde"]
                     and codes[pdf] & {"KEIN_TEXT", "KAUM_LESBAR"}]
        gesundheit = [pdf for pdf in ergebnisse if "GESUNDHEITSDATEN" in codes[pdf]]
        vermutet = [pdf for pdf in gesundheit if self._gesundheit_nur_vermutet(ergebnisse[pdf])]
        gesundheit_sicher = [pdf for pdf in gesundheit if pdf not in vermutet]
        mit_fehler = [(pdf, e["fehler"]) for pdf, e in ergebnisse.items() if e["fehler"]]
        mit_warnung = [(pdf, e["warnungen"]) for pdf, e in ergebnisse.items() if e["warnungen"]]
        # R-04 (Paket analyse-status): Personendaten nur in Metadaten, Lesezeichen, Anhängen oder XFA – nie
        # „keine personenbezogenen Daten“ sagen; „Schwärzen starten“ erzeugt eine bereinigte Ausgabe
        nebenkanal = [(pdf, nk) for pdf, e in ergebnisse.items() if not e["fehler"]
                      for nk in [_nebenkanal_bezug(e)] if nk is not None]
        nebenkanal_block = []
        if nebenkanal:
            nebenkanal_block = (["Personenbezogene Daten in versteckten Teilen der Datei (Metadaten, Lesezeichen, "
                                 "Anhänge, Formulardaten) – ein KI-Dienst bekäme sie mit dem Original mit:"]
                                + [f"  • {self._anzeigename(p)}: {_nebenkanal_text(nk)}" for p, nk in nebenkanal[:10]]
                                + ["„Schwärzen starten“ erzeugt eine bereinigte Ausgabe ohne diese Teile. Das "
                                   "Original NICHT weitergeben."])

        # Dateien der Auswahl, die gar nicht geprüft wurden (keine PDF, Foto nicht übernommen, ohne Kennwort, nicht
        # lesbar) oder nicht analysiert werden konnten: dann gilt kein Satz wie „keine personenbezogenen Daten“ für
        # die ganze Auswahl – er hieße für den Makler „der Ordner ist sauber“ (Befund Runde 2)
        ungeprueft = list(self.nicht_geprueft.items())
        alles_geprueft = not ungeprueft and not mit_fehler
        geprueft = [p for p, e in ergebnisse.items() if not e["fehler"]]
        nicht_zahl = len(ungeprueft) + len(mit_fehler)

        if gesamt == 0 and nebenkanal:
            self._log(f"Analyse fertig: auf den Seiten keine Funde, aber Personendaten in Metadaten/Anhängen von "
                      f"{len(nebenkanal)} Datei(en) – „Schwärzen starten“ erzeugt eine bereinigte Ausgabe.",
                      "warnung", zaehlen=False)
            status = "Personendaten in Metadaten/Anhängen – bitte „Schwärzen starten“: die Ausgabe wird bereinigt."
        elif gesamt and angehakt:
            davon = f", davon {len(angeboten_funde)} nur angeboten (nicht angehakt)" if angeboten_funde else ""
            self._log(f"Analyse fertig: {gesamt} Fund(e) in {len(ergebnisse)} Datei(en){davon}. "
                      f"Bitte Liste prüfen (Doppelklick = Vorschau), dann schwärzen.", "ok")
            status = (f"{gesamt} Fund(e) in {len(ergebnisse)} Datei(en){davon} – Liste prüfen (Doppelklick auf "
                      f"eine Datei = Vorschau), dann schwärzen.")
        elif gesamt:
            was = "mögliche Gesundheitsangaben" if nur_gesundheit else "Funde"
            folge = ("Wegen der Personendaten in Metadaten/Anhängen erzeugt „Schwärzen starten“ trotzdem eine "
                     "bereinigte Ausgabe." if nebenkanal else "Ohne Häkchen wird keine Ausgabedatei erzeugt.")
            wo = f"{len(ergebnisse)} Datei(en)" if alles_geprueft else f"den {len(geprueft)} geprüften Datei(en)"
            self._log(f"Analyse fertig: keine Personendaten zum Schwärzen in {wo} – nur "
                      f"{gesamt} {was} angeboten (nicht angehakt). {folge}",
                      "ok" if alles_geprueft else "warnung", zaehlen=False)
            status = (f"Keine Personendaten zum Schwärzen – nur {was} angeboten (nicht angehakt). Bitte prüfen; "
                      f"zum Schwärzen anhaken.")
        elif alles_geprueft:
            self._log(f"Analyse fertig: 0 Funde in {len(ergebnisse)} Datei(en) – es gibt nichts zu schwärzen, "
                      f"es wird keine Ausgabedatei erzeugt.", "warnung" if ohne_text else "ok", zaehlen=False)
            status = "Keine Funde – nichts zu schwärzen. Bitte Hinweise im Protokoll lesen."
        else:
            self._log(f"Analyse fertig: 0 Funde in den {len(geprueft)} geprüften Datei(en) – {nicht_zahl} Datei(en) "
                      f"der Auswahl wurden NICHT geprüft bzw. nicht analysiert (siehe unten).", "warnung",
                      zaehlen=False)
            status = (f"Keine Funde in den geprüften Dateien – {nicht_zahl} Datei(en) wurden NICHT geprüft "
                      f"(siehe Protokoll).")
        if ungeprueft:
            # als LETZTE Protokollzeile und VORN in der (immer sichtbaren) Statuszeile
            self._log(f"⚠ NICHT geprüft: {len(ungeprueft)} Datei(en) der Auswahl – "
                      f"{self._nicht_geprueft_text(ungeprueft)}. Diese Dateien nicht ungeprüft weitergeben.",
                      "warnung", zaehlen=False)
            if not (gesamt == 0 and not nebenkanal):
                status = f"⚠ {len(ungeprueft)} Datei(en) NICHT geprüft (siehe Protokoll) · " + status
        self._status(status)

        # Abschlussdialog aus Blöcken (je Überschrift mit ihren Punkten), durch Leerzeilen getrennt
        bloecke: list[list[str]] = []
        art = "info" if alles_geprueft else "warning"
        nicht_block = self._nicht_geprueft_block()
        if gesamt == 0 and nebenkanal:
            art = "warning"
            bloecke.append(nebenkanal_block)
            ohne = [p for p, e in ergebnisse.items() if not e["fehler"] and p not in dict(nebenkanal)]
            if ohne:
                bloecke.append([f"In {len(ohne)} weiteren Datei(en) wurde nichts gefunden – bitte selbst durchsehen "
                                f"(Doppelklick = Vorschau):"] + [f"  • {self._anzeigename(p)}" for p in ohne[:10]])
        elif gesamt == 0:
            if alles_geprueft:
                bloecke.append(["Es wurden keine personenbezogenen Daten erkannt. Es gibt nichts zu schwärzen, "
                                "deshalb bleibt der Schwärzen-Knopf aus und es wird keine Ausgabedatei erzeugt."])
            elif geprueft:
                bloecke.append(["In den geprüften Dateien wurde nichts gefunden – dort gibt es nichts zu schwärzen, "
                                "deshalb bleibt der Schwärzen-Knopf aus und es wird keine Ausgabedatei erzeugt. Das "
                                f"gilt NICHT für die {nicht_zahl} Datei(en), die nicht geprüft werden konnten "
                                f"(siehe unten)."])
            else:
                bloecke.append([f"Keine Datei der Auswahl konnte geprüft werden ({nicht_zahl} Datei(en), siehe "
                                f"unten) – es wird keine Ausgabedatei erzeugt."])
            if ohne_text:
                art = "warning"
                bloecke.append(["ACHTUNG – in diesen Dateien war kein Text lesbar (z. B. unlesbarer Scan). "
                                "Dort konnte NICHTS geprüft werden; diese Dateien nicht ungeprüft weitergeben:"]
                               + [f"  • {self._anzeigename(p)}" for p in ohne_text[:10]])
            elif geprueft:
                bloecke.append(["Mögliche Gründe: Das Dokument enthält keine Namen, IBANs, Adressen usw. "
                                "(z. B. ein Bedingungswerk), oder die Daten stehen in Bildern oder Handschrift. "
                                "Bitte das Dokument selbst durchsehen (Doppelklick = Vorschau)."])
        elif not angehakt and nebenkanal:
            art = "warning"
            bloecke.append(nebenkanal_block)
            bloecke.append(["Auf den Seiten stehen nur angebotene, NICHT angehakte Stellen – sie bleiben lesbar, "
                            "wenn sie nicht angehakt werden."])
        elif not angehakt:
            satz = ("Keine Personendaten zum Schwärzen erkannt" if alles_geprueft else
                    "In den geprüften Dateien wurden keine Personendaten zum Schwärzen erkannt")
            bloecke.append([f"{satz} (keine Namen, Anschriften, IBANs, Nummern …). In der Fundliste stehen nur "
                            f"angebotene, NICHT angehakte Stellen. Ohne Häkchen bleibt der Schwärzen-Knopf aus, und es "
                            f"wird keine Ausgabedatei erzeugt."])
        elif nebenkanal:
            art = "warning"
            bloecke.append(nebenkanal_block)
        elif ungeprueft and not self.warnungen_anzahl:
            bloecke.append([f"Die Analyse hat {gesamt} Fund(e) in {len(geprueft)} geprüften Datei(en) ergeben – "
                            f"bitte die Fundliste prüfen (Doppelklick = Vorschau), dann schwärzen."])
        if self.warnungen_anzahl and gesamt:
            art = "warning"
            kopf = (f"Die Analyse hat {gesamt} Fund(e) ergeben und {self.warnungen_anzahl} Warnung(en)/Fehler "
                    f"gemeldet (Details im Protokoll)" if angehakt else
                    f"Die Analyse hat {self.warnungen_anzahl} Warnung(en)/Fehler gemeldet (Details im Protokoll)")
            punkte = [f"  • {self._anzeigename(p)}: {ws[0]}" + (f" (+{len(ws) - 1})" if len(ws) > 1 else "")
                      for p, ws in mit_warnung[:10]]
            # Überschrift und ihre Punkte als EIN Block – vorne, wenn etwas angehakt ist
            bloecke.insert(0 if angehakt else len(bloecke), [kopf + (":" if punkte else ".")] + punkte)
        if nicht_block:
            # gleich nach der ersten Aussage (bzw. den Warnungen) – nicht erst unter allen anderen Hinweisen
            art = "warning"
            bloecke.insert(min(1, len(bloecke)), nicht_block)
        if mit_fehler:
            art = "warning"
            bloecke.append(["Nicht analysierbar:"] + [f"  • {self._anzeigename(p)}: {f}" for p, f in mit_fehler[:10]])
        if gesundheit_sicher:
            # die Engine meldet GESUNDHEITSDATEN nur, wenn sie Funde abgewählt anbietet (Hinweis-Kategorien der
            # Schutzstufe) – in „Maximal“ sind sie angehakt und es gibt keine Meldung. Erkennungszeichen ist ⚕ (nur
            # an angebotenen Gesundheitsdaten), nicht ⚑ (steht auch an angehakten Kennungen)
            art = "warning"
            bloecke.append([f"Gesundheitsdaten (Art. 9 DSGVO) erkannt – sie stehen in der Fundliste, sind aber NICHT "
                            f"angehakt und bleiben deshalb lesbar. Zum Schwärzen bitte die nicht angehakten Zeilen "
                            f"mit {MARKE_GESUNDHEIT.strip()} („Diagnosen …“, „Medikamente …“) anhaken – schneller per "
                            f"Rechtsklick auf eine solche Zeile → „Kategorie … überall anhaken“ – oder die Schutzstufe "
                            f"„Maximal“ wählen:"]
                           + [f"  • {self._anzeigename(p)}" for p in gesundheit_sicher[:10]])
        if vermutet:
            bloecke.append([f"Möglicherweise Gesundheitsdaten (Art. 9 DSGVO): erkannt wurden nur Fachbegriffe ohne "
                            f"Etikett wie „Diagnose:“, ohne ICD-Code und ohne Bezug zu einer Person – in Tarif- und "
                            f"Leistungsübersichten sind das meist nur Leistungen. Sie stehen NICHT angehakt in der "
                            f"Fundliste ({MARKE_GESUNDHEIT.strip()}) und bleiben lesbar. Sind es Angaben über eine "
                            f"Person, bitte anhaken oder die Schutzstufe „Maximal“ wählen:"]
                           + [f"  • {self._anzeigename(p)}{self._beispiele(ergebnisse[p])}" for p in vermutet[:10]])
        if self.warnungen_anzahl and not gesamt and mit_warnung and not ohne_text:
            art = "warning"
            bloecke.append([f"{self.warnungen_anzahl} Warnung(en) – Details im Protokoll."])
        if bloecke:
            zeilen = []
            for block in bloecke:
                if zeilen:
                    zeilen.append("")
                zeilen += block
            titel = "Analyse abgeschlossen" if gesamt else ("Personendaten in Metadaten/Anhängen" if nebenkanal
                                                             else "Keine Funde")
            # der Titel nennt, dass nicht alles geprüft wurde – ein bloßes „Keine Funde“ sah genauso aus wie
            # „alles geprüft, nichts gefunden“
            if ungeprueft or (not gesamt and not nebenkanal and not alles_geprueft):
                titel += f" – {nicht_zahl} Datei(en) NICHT geprüft"
            self._dialog(art, titel, "\n".join(zeilen))

    @staticmethod
    def _gesundheit_nur_vermutet(ergebnis: dict) -> bool:
        """Beruhen alle angebotenen Gesundheitsfunde einer Datei nur auf allgemeinen Fachbegriffen (Engine:
        analyse.gesundheit_nur_vermutet)? Ohne diese Funktion (ältere Engine) gilt die Meldung als sicher."""
        if gesundheit_nur_vermutet is None:
            return False
        funde = [f for f in ergebnis.get("funde", []) if f.get("kategorie") in GESUNDHEIT_KATEGORIEN
                 and f.get("hinweis")]
        return bool(funde) and all(gesundheit_nur_vermutet(f) for f in funde)

    @staticmethod
    def _beispiele(ergebnis: dict, anzahl: int = 3) -> str:
        """„ („Psychotherapie“, „Zahnersatz“ …)“ – die ersten angebotenen Gesundheitsbegriffe einer Datei."""
        texte = list(dict.fromkeys(str(f.get("text", "")).replace("\n", " ") for f in ergebnis.get("funde", [])
                                   if f.get("kategorie") in GESUNDHEIT_KATEGORIEN and f.get("hinweis")))
        if not texte:
            return ""
        return " (" + ", ".join(f"„{x}“" for x in texte[:anzahl]) + (" …" if len(texte) > anzahl else "") + ")"

    # ------------------------------------------------------------------
    # Schwärzen
    # ------------------------------------------------------------------
    def _zielordner(self):
        """(ok, Pfad|None): gewählter gemeinsamer Zielordner oder None (= neben dem Original)."""
        if not self.zielordner_aktiv.get():
            return True, None
        text = self.zielordner_var.get().strip()
        if not text:
            self._dialog("warning", "Zielordner fehlt",
                         "Bitte einen gemeinsamen Zielordner wählen oder die Option abschalten.")
            return False, None
        ziel = Path(text)
        try:
            ziel.mkdir(parents=True, exist_ok=True)
        except OSError as fehler:
            self._dialog("error", "Zielordner nicht nutzbar",
                         f"Der Zielordner kann nicht angelegt werden:\n{ziel}\n\n"
                         f"{_verstaendliche_fehlermeldung(fehler, ziel)}")
            return False, None
        return True, ziel

    def _auftrag(self, pdf: Path) -> dict | None:
        """Schwärz-Auftrag einer Datei aus den Häkchen: Funde (mit Stellen-Zuständen), manuelle Markierungen."""
        ergebnis = self.analyse_ergebnisse.get(pdf)
        if not ergebnis:
            return None
        funde = []
        for index, fund in enumerate(ergebnis["funde"]):
            if self.fund_zustand(pdf, index) == "aus":
                continue
            kopie = dict(fund)
            if self._fund_hat_stellen(pdf, fund):
                kopie["stellen"] = [dict(s) for s in fund["stellen"]]
            funde.append(kopie)
        bereiche: dict[int, list] = {}
        stellen: dict[int, list] = {}
        for eintrag in self.manuell.get(pdf, {}).values():
            if not eintrag.get("an", True):
                continue
            if eintrag["art"] == "bereich":
                bereiche.setdefault(eintrag["seite"], []).extend(fitz.Rect(r) for r in eintrag["rechtecke"])
            else:
                stellen.setdefault(eintrag["seite"], []).append(
                    (int(eintrag["start"]), int(eintrag["ende"]), PLATZHALTER_MANUELL))
        nebenkanal = None if ergebnis.get("fehler") else _nebenkanal_bezug(ergebnis)
        if not funde and not bereiche and not stellen and nebenkanal is None:
            return None
        kopie = self.arbeitskopien.get(pdf)
        return {"pdf": pdf, "funde": funde, "ocr_cache": ergebnis.get("ocr_cache"),
                "modell": ergebnis.get("modell") if self.einzelstellen_moeglich(pdf) else None,
                "bereiche": bereiche, "stellen": stellen,
                # die Engine liest die Arbeitskopie; die Ausgabe gehört neben das ORIGINAL (nie in den Temp-Ordner)
                "datei": Path(kopie["pfad"]) if kopie else pdf,
                "ziel_ordner": Path(pdf).parent / dateien.AUSGABE_ORDNER if kopie else None,
                "nebenkanaele": ergebnis.get("nebenkanaele") if nebenkanal is not None else None,
                "nur_nebenkanal": not funde and not bereiche and not stellen,
                # Foto/Ausweiskopie: Gesicht, Unterschrift und Handschrift bleiben stehen – die Ausgabe braucht
                # IMMER eine Freigabe in der Vorschau, auch wenn das Häkchen „Freigabe …“ aus ist (Befund Runde 2)
                "foto": self._ist_foto(pdf)}

    def _ist_foto(self, pdf: Path) -> bool:
        """Wurde die Datei aus einem Foto oder Bild-Scan in eine PDF umgewandelt?"""
        return (self.arbeitskopien.get(pdf) or {}).get("art") == "bild"

    def schwaerzen(self, nur: list | None = None, ersetzt: Path | None = None) -> bool:
        """Schwärzt alle angehakten Funde (bzw. nur die Dateien in „nur“, z. B. zum Nachschwärzen; die Ausgabe
        „ersetzt“ wird nach Erfolg verworfen). Liefert True, wenn ein Lauf gestartet wurde."""
        if self.laeuft:
            self._laeuft_hinweis()
            return False
        if self.analyse_veraltet:
            self._dialog("info", "Erneut analysieren",
                         "Schutzstufe, Kategorien, Listen oder Dateien wurden seit der letzten Analyse geändert. "
                         "Bitte zuerst erneut analysieren.")
            return False
        dateiliste = list(nur) if nur is not None else list(self.dateien)
        nicht_analysiert = [p for p in dateiliste if p not in self.analyse_ergebnisse]
        if nicht_analysiert:
            self._dialog("info", "Erst analysieren",
                         f"{len(nicht_analysiert)} Datei(en) sind noch nicht analysiert "
                         f"(z. B. {nicht_analysiert[0].name}). Bitte zuerst „Analysieren“ drücken.")
            return False
        auftraege = [a for a in (self._auftrag(p) for p in dateiliste) if a]
        if not auftraege:
            self._dialog("warning", "Nichts ausgewählt", "Es ist kein Fund angehakt – es gibt nichts zu schwärzen.")
            return False
        fehlt = []
        if any(a["bereiche"] for a in auftraege) and not self.kann_manuelle_bereiche():
            fehlt.append("Rahmen-Bereiche")
        if any(a["stellen"] for a in auftraege) and not self.kann_manuelle_stellen():
            fehlt.append("einzelne Stellen")
        if fehlt:
            self._dialog("error", "Nicht möglich", f"Diese Programmversion kann {' und '.join(fehlt)} aus der Vorschau "
                                                   f"nicht schwärzen. Bitte diese Markierungen entfernen oder als "
                                                   f"IMMER-Begriff eintragen.")
            return False
        if ersetzt is not None:
            ok, ziel_ordner = True, Path(ersetzt).parent
        else:
            ok, ziel_ordner = self._zielordner()
        if not ok:
            return False
        self.einstellungen_speichern()
        if nur is None:
            self.letzte_ausgabeordner = []
        freigabe = bool(self.freigabe_var.get())
        self._schwaerz_kontext = {"freigabe": freigabe, "profil": self.profil_var.get(),
                                  "basis_profil": self.basis_profil, "nachschwaerzen": ersetzt is not None,
                                  "gemeinsamer_zielordner": ziel_ordner is not None and ersetzt is None,
                                  "fotos": sum(1 for a in auftraege if a.get("foto"))}
        self._lauf_starten("schwaerzen")
        self._status("Schwärzung startet …")
        self._lauf_thread = threading.Thread(target=self._schwaerz_lauf,
                                             args=(auftraege, ziel_ordner, self.abbruch, freigabe, self.basis_profil,
                                                   ersetzt),
                                             daemon=True, name="Schwaerzung")
        self._lauf_thread.start()
        return True

    def _schwaerz_lauf(self, auftraege, ziel_ordner, abbruch, freigabe=True, profil="hoch", ersetzt=None):
        ergebnisse: list[tuple[Path, dict]] = []
        fehler_intern = None
        erster_fehler = None
        ocr = None
        try:
            ocr = self._ocr_dienst_anlegen()
            self.ocr = ocr
            seiten = {a["pdf"]: _seitenzahl(a.get("datei", a["pdf"])) for a in auftraege}
            self._fortschritt_maximum(max(1, sum(seiten.values())))
            ordner = {ziel_ordner} if ziel_ordner else {a.get("ziel_ordner") or a["pdf"].parent / dateien.AUSGABE_ORDNER
                                                        for a in auftraege}
            for o in sorted(ordner):
                entfernt = dateien.zwischendateien_aufraeumen(o)
                if entfernt:
                    self._log(f"ℹ {len(entfernt)} verwaiste Zwischendatei(en) einer abgebrochenen Schwärzung in "
                              f"{o} gelöscht.", "hinweis")
            basis = 0
            for nr, auftrag in enumerate(auftraege, 1):
                if abbruch.is_set():
                    break
                pdf = auftrag["pdf"]
                name = self._anzeigename(pdf)
                self._status(f"Schwärzung: Datei {nr}/{len(auftraege)} – {name}")

                def fortschritt(seite, gesamt, _basis=basis, _nr=nr, _pdf=pdf, _name=name):
                    self._fortschritt_setzen(_basis + min(int(seite), seiten[_pdf]))
                    self._status(f"Schwärzung: Datei {_nr}/{len(auftraege)}, Seite {seite}/{gesamt} – {_name}")

                kwargs = {"melde": lambda t: self._log(t, "grau"), "fortschritt": fortschritt, "abbruch": abbruch,
                          "ocr": ocr, "ocr_cache": auftrag["ocr_cache"],
                          "ziel_ordner": ziel_ordner or auftrag.get("ziel_ordner")}
                if auftrag.get("nebenkanaele") is not None and kann(schwaerze_pdf, "nebenkanaele"):
                    kwargs["nebenkanaele"] = auftrag["nebenkanaele"]
                if auftrag["modell"] is not None:
                    kwargs["modell"] = auftrag["modell"]
                if auftrag["bereiche"]:
                    kwargs["manuelle_bereiche"] = auftrag["bereiche"]
                if auftrag["stellen"]:
                    kwargs["manuelle_stellen"] = auftrag["stellen"]
                freigabe_engine = kann(schwaerze_pdf, "freigabe_erforderlich")
                freigabe_hier = bool(freigabe or auftrag.get("foto"))      # Fotos immer erst nach Freigabe
                if freigabe_engine:
                    kwargs["freigabe_erforderlich"] = freigabe_hier
                if kann(schwaerze_pdf, "profil"):
                    kwargs["profil"] = profil
                datei = auftrag.get("datei", pdf)
                art = dateien.datei_art(datei)
                try:
                    if not dateien.fuer_engine_erlaubt(art):      # R-01: nie eine Nicht-PDF an die Schwärzung
                        keine = self._keine_pdf_ergebnis(pdf, art)
                        ergebnis = {"original": pdf, "ausgabe": None, "treffer": 0, "uebersprungen": 0,
                                    "warnungen": [], "hinweise": [], "reste": [], "fehler": keine["fehler"],
                                    "meldungen": keine["meldungen"]}
                    else:
                        ergebnis = _schwaerz_ergebnis_pruefen(schwaerze_pdf(datei, auftrag["funde"], **kwargs), pdf)
                    if ergebnis["fehler"] and ergebnis["fehler"] != "Abgebrochen":
                        ergebnis["fehler"] = _fehlertext_verstaendlich(ergebnis["fehler"])
                    if freigabe_hier and not freigabe_engine:
                        self._freigabe_emulieren(ergebnis)
                    self._reste_verorten(ergebnis)
                except Exception as fehler:
                    log = dateien.fehler_protokollieren(*sys.exc_info())
                    if erster_fehler is None and not isinstance(fehler, OSError):
                        erster_fehler = (log, fehler)
                    ergebnis = {"original": pdf, "ausgabe": None, "treffer": 0, "uebersprungen": 0,
                                "warnungen": [], "hinweise": [], "reste": [],
                                "fehler": _verstaendliche_fehlermeldung(fehler, pdf)}
                ergebnis["_status"] = self._ausgabe_status(ergebnis)
                ergebnisse.append((pdf, ergebnis))
                self._schwaerz_protokollieren(name, ergebnis)
                basis += seiten[pdf]
                self._fortschritt_setzen(basis)
        except Exception:
            fehler_intern = sys.exc_info()
        finally:
            self._ocr_schliessen(ocr)
            self._im_hauptthread(self._schwaerzen_fertig, auftraege, ergebnisse, abbruch.is_set(), fehler_intern,
                                 erster_fehler, ersetzt)

    @staticmethod
    def _reste_verorten(ergebnis: dict):
        """Reste der Selbstkontrolle (nur Text) in der Ausgabe suchen: die Vorschau zeigt sie dann orange wie einen
        Verdacht und „Nachschwärzen“ erfasst sie (läuft im Arbeits-Thread)."""
        ausgabe = ergebnis.get("ausgabe")
        if not ergebnis["reste"] or ergebnis["fehler"] or ausgabe is None or not Path(ausgabe).exists():
            return
        try:
            ergebnis["_reste_verdacht"] = attrappen.reste_als_verdacht(ausgabe, ergebnis["reste"],
                                                                       ergebnis.get("verdacht") or [])
        except Exception:
            dateien.fehler_protokollieren(*sys.exc_info())

    @staticmethod
    def _freigabe_emulieren(ergebnis: dict):
        """Engine ohne freigabe_erforderlich: fertige Ausgabe selbst als _PRUEFEN markieren (Attrappe)."""
        ausgabe = ergebnis.get("ausgabe")
        if ergebnis["fehler"] or ausgabe is None or not Path(ausgabe).exists():
            return
        ergebnis["status"] = "pruefen"
        ergebnis["_freigabe_emuliert"] = True
        try:
            ergebnis["ausgabe"] = attrappen.als_pruefen_markieren(ausgabe)
        except OSError as fehler:
            ergebnis["warnungen"].append(f"Die Ausgabe konnte nicht als „_PRUEFEN“ markiert werden ({fehler}) – "
                                         f"sie ist trotzdem erst nach Prüfung in der Vorschau weiterzugeben.")

    @staticmethod
    def _ausgabe_status(ergebnis: dict) -> str:
        """fertig | pruefen | fehler | keine – die Engine meldet „status“ (Vertrag 5), sonst aus dem Namen."""
        ausgabe = ergebnis.get("ausgabe")
        if ergebnis["fehler"]:
            return "fehler"
        if ausgabe is None:
            return "keine"
        status = ergebnis.get("status")
        if "_PRUEFEN" in Path(ausgabe).name.upper() or ergebnis.get("reste") or ergebnis.get("verdacht") \
                or int(ergebnis.get("stellen_nicht_lokalisiert") or 0):
            return "pruefen"                           # im Zweifel prüfen, auch wenn „status“ anderes sagt
        return status if status in ("fertig", "pruefen") else "fertig"

    def _schwaerz_protokollieren(self, name: str, ergebnis: dict):
        codes = meldungs_codes(ergebnis)
        abgebrochen = "ABGEBROCHEN" in codes
        if (ergebnis["treffer"] == 0 and not ergebnis["fehler"] and ergebnis["ausgabe"] is None
                and "KEIN_TREFFER" not in codes):
            ergebnis["warnungen"].append(WARNUNG_KEIN_TREFFER)
        if ergebnis["fehler"]:
            self._log(f"✖ {name}: {ergebnis['fehler']}", "fehler", zaehlen=not abgebrochen)
        elif ergebnis["ausgabe"] is not None:
            zusatz = " – zu prüfen, dann in der Vorschau freigeben" if ergebnis["_status"] == "pruefen" else ""
            self._log(f"✔ {name}  →  {ergebnis['ausgabe']}  ({ergebnis['treffer']} Stelle(n) ersetzt){zusatz}", "ok")
        else:
            self._log(f"⚠ {name}: keine Ausgabedatei erzeugt.", "warnung", zaehlen=False)
        for w in ergebnis["warnungen"]:
            if abgebrochen and w.strip() == "Abgebrochen":
                continue
            self._log(f"⚠ {name}: {w}", "warnung")
        for h in ergebnis["hinweise"]:
            self._log(f"ℹ {name}: {h}", "hinweis")
        if ergebnis["reste"]:
            self._log(f"⚠ {name}: noch auffindbar: {', '.join(ergebnis['reste'][:5])} – Ausgabe prüfen!", "warnung",
                      zaehlen=False)
        verdacht = ergebnis.get("verdacht") or []
        if verdacht:
            self._log(f"⚠ {name}: {len(verdacht)} Verdachtsstelle(n) in der Ausgabe – in der Vorschau prüfen "
                      f"(nachschwärzen oder freigeben).", "warnung", zaehlen="VERDACHT" not in codes)
        nicht_lokalisiert = int(ergebnis.get("stellen_nicht_lokalisiert") or 0)
        if nicht_lokalisiert:
            self._log(f"✖ {name}: {nicht_lokalisiert} Fundstelle(n) konnten nicht lokalisiert werden – Ausgabe "
                      f"unbedingt prüfen!", "fehler", zaehlen="NICHT_LOKALISIERT" not in codes)

    def _grund(self, ergebnis: dict, status: str, pdf: Path | None = None) -> str:
        if status == "fehler":
            return ergebnis["fehler"] or ""
        if status == "keine":
            return ergebnis["warnungen"][0] if ergebnis["warnungen"] else "kein Treffer"
        teile = []
        verdacht = ergebnis.get("verdacht") or []
        if verdacht:
            teile.append(f"{len(verdacht)} Verdachtsstelle(n)")
        if ergebnis["reste"]:
            teile.append(f"{len(ergebnis['reste'])} Fundtext(e) noch auffindbar")
        if int(ergebnis.get("stellen_nicht_lokalisiert") or 0):
            teile.append("Stellen nicht lokalisiert")
        if status == "pruefen" and pdf is not None and self._ist_foto(pdf):
            teile.append("Foto: Gesicht, Unterschrift und Handschrift selbst prüfen")
        if status == "pruefen" and not teile:
            teile.append("Freigabe ausstehend")
        return " · ".join(teile)

    def _schwaerzen_fertig(self, auftraege, ergebnisse, abgebrochen, fehler_intern, erster_fehler=None,
                           ersetzt=None):
        for pdf, e in ergebnisse:
            status = e.get("_status") or self._ausgabe_status(e)
            if status in ("fehler", "keine") and ersetzt is not None:
                continue                                  # Nachschwärzen gescheitert: alte Ausgabe bleibt gültig
            verdacht = list(e.get("verdacht") or []) + list(e.get("_reste_verdacht") or [])
            self.ausgaben[pdf] = {"pfad": e["ausgabe"], "status": status, "verdacht": verdacht,
                                  "ergebnis": e, "grund": self._grund(e, status, pdf)}
            self._ausgabe_zeile_setzen(pdf)
        geschrieben = [(pdf, e) for pdf, e in ergebnisse
                       if e["ausgabe"] is not None and Path(e["ausgabe"]).exists()]
        ohne_ausgabe = [(pdf, e) for pdf, e in ergebnisse
                        if not (e["ausgabe"] is not None and Path(e["ausgabe"]).exists())]
        verarbeitet = {pdf for pdf, _ in ergebnisse}
        nicht_verarbeitet = [a["pdf"] for a in auftraege if a["pdf"] not in verarbeitet]
        pruefen = [pdf for pdf, e in geschrieben if self.ausgaben.get(pdf, {}).get("status") == "pruefen"]
        ordner: list[Path] = list(self.letzte_ausgabeordner) if ersetzt is not None else []
        for _, e in geschrieben:
            if e["ausgabe"].parent not in ordner:
                ordner.append(e["ausgabe"].parent)
        self.letzte_ausgabeordner = ordner
        stellen = sum(e["treffer"] for _, e in geschrieben)
        try:
            self._protokoll_schwaerzung(auftraege, ergebnisse, abgebrochen)
        except Exception:                                 # das Laufprotokoll darf den Abschluss nie verhindern
            dateien.fehler_protokollieren(*sys.exc_info())
        self._lauf_beenden()
        if erster_fehler is not None:
            self._fehler_dialog(*erster_fehler)
        if fehler_intern:
            self._fehler_melden(*fehler_intern)
        if ersetzt is not None:
            if abgebrochen and not ergebnisse:
                self._status(f"Nachschwärzen abgebrochen – die bisherige Ausgabe {ersetzt.name} bleibt zu prüfen.")
            self._nachschwaerzen_fertig(ergebnisse, ersetzt, abgebrochen)
            return

        alles_gut = (not ohne_ausgabe and not nicht_verarbeitet and not pruefen and not abgebrochen
                     and not self.nicht_geprueft)
        if abgebrochen:
            self._log("Schwärzung abgebrochen.", "fehler", zaehlen=False)
        self._log(f"Fertig: {len(geschrieben)} von {len(auftraege)} Datei(en) geschrieben, "
                  f"{stellen} Stelle(n) ersetzt.", "ok" if alles_gut else "warnung", zaehlen=False)
        for o in ordner:
            self._log(f"Ausgabeordner: {o}", "ok")
            if dateien.ist_cloud_ordner(o):
                self._log("ℹ Dieser Ordner wird von einem Cloud-Dienst synchronisiert – die Ausgabe landet "
                          "ebenfalls in der Cloud.", "hinweis")
        if pruefen:
            self._log(f"⚠ {len(pruefen)} Ausgabedatei(en) tragen „_PRUEFEN“ im Namen: in der Vorschau prüfen und "
                      f"freigeben (Doppelklick auf die Datei).", "warnung", zaehlen=False)
        self._log("Bitte jede Ausgabedatei prüfen, bevor sie an einen KI-Dienst geht – "
                  "das Programm pseudonymisiert nur direkte Identifikatoren.", "hinweis")
        self._status(f"Fertig: {len(geschrieben)} von {len(auftraege)} Datei(en) geschrieben, "
                     f"{stellen} Stelle(n) ersetzt." + ("" if alles_gut else " Bitte Hinweise beachten."))
        for pdf, fenster in list(self.vorschauen.items()):
            if self.ausgabe_vorhanden(pdf):
                fenster.modus_wechseln("nachher")

        zeilen = [f"{len(geschrieben)} von {len(auftraege)} Datei(en) geschrieben, {stellen} Stelle(n) ersetzt."]
        if abgebrochen:
            zeilen.append("Der Lauf wurde abgebrochen.")
        if ohne_ausgabe or nicht_verarbeitet:
            zeilen.append("")
            zeilen.append("OHNE Ausgabedatei (Original nicht weitergeben!):")
            for pdf, e in ohne_ausgabe[:10]:
                grund = e["fehler"] or (e["warnungen"][0] if e["warnungen"] else "kein Treffer")
                zeilen.append(f"  • {self._anzeigename(pdf)}: {grund}")
            for pdf in nicht_verarbeitet[:10]:
                zeilen.append(f"  • {self._anzeigename(pdf)}: nicht verarbeitet (abgebrochen)")
        if self.nicht_geprueft:
            zeilen.append("")
            zeilen += self._nicht_geprueft_block()
        if pruefen:
            zeilen.append("")
            zeilen.append(f"Zu prüfen: {len(pruefen)} Datei(en). {PRUEFEN_ERKLAERUNG}")
            for pdf in pruefen[:10]:
                eintrag = self.ausgaben[pdf]
                grund = eintrag.get("grund")
                zeilen.append(f"  • {self._anzeigename(pdf)} → {eintrag['pfad'].name}" + (f" ({grund})" if grund else ""))
            if len(pruefen) > 10:
                zeilen.append(f"  … und {len(pruefen) - 10} weitere")
        if self.warnungen_anzahl:
            zeilen.append("")
            zeilen.append(f"{self.warnungen_anzahl} Warnung(en)/Fehler – Details stehen im Protokoll.")
        if ordner:
            zeilen.append("")
            stamm = dateien.gemeinsamer_stamm(ordner) if len(ordner) > 3 else None
            if stamm is not None:
                zeilen.append(f"{len(ordner)} Ausgabeordner unterhalb von {stamm} (vollständige Liste im Protokoll).")
            else:
                zeilen.append("Ausgabeordner:")
                zeilen += [f"  {o}" for o in ordner[:5]]
                if len(ordner) > 5:
                    zeilen.append(f"  … und {len(ordner) - 5} weitere (siehe Protokoll)")
        zeilen.append("")
        zeilen.append("Bitte jede Ausgabedatei vor der Weitergabe prüfen.")
        art = "info" if alles_gut and not self.warnungen_anzahl else "warning"
        self._abschluss_dialog(art, "Schwärzung abgeschlossen", "\n".join(zeilen), ordner, pruefen)

    def _nachschwaerzen_fertig(self, ergebnisse, ersetzt: Path, abgebrochen: bool):
        """Ende eines Nachschwärz-Laufs: alte Ausgabe verwerfen, Vorschau auf die neue Ausgabe umstellen."""
        for pdf, e in ergebnisse:
            fenster = self.vorschauen.get(pdf)
            if e["ausgabe"] is not None and Path(e["ausgabe"]).exists() and not e["fehler"]:
                try:
                    self._vorschau_dateien_freigeben(ersetzt)
                    verwerfen(ersetzt)
                    self._ereignis(f"{ersetzt.name} nachgeschwärzt → {e['ausgabe'].name} (alte Ausgabe verworfen)")
                    self._log(f"ℹ {self._anzeigename(pdf)}: nachgeschwärzt → {e['ausgabe'].name} "
                              f"(alte Ausgabe {ersetzt.name} verworfen).", "ok")
                except Exception:
                    dateien.fehler_protokollieren(*sys.exc_info())
                    self._log(f"⚠ {self._anzeigename(pdf)}: alte Ausgabe {ersetzt.name} konnte nicht gelöscht "
                              f"werden – bitte von Hand löschen, sie ist NICHT nachgeschwärzt.", "warnung")
                self._status(f"Nachgeschwärzt: {e['ausgabe'].name} – bitte erneut prüfen.")
                if fenster is not None:
                    fenster.modus_wechseln("nachher")
            else:
                grund = e["fehler"] or (e["warnungen"][0] if e["warnungen"] else "keine Ausgabe")
                self._dialog("warning", "Nachschwärzen fehlgeschlagen",
                             f"„{self._anzeigename(pdf)}“ konnte nicht nachgeschwärzt werden: {grund}\n\n"
                             f"Die bisherige Ausgabe {ersetzt.name} bleibt unverändert und zu prüfen.")
                if fenster is not None:
                    fenster.neu_zeichnen()

    def _abschluss_dialog(self, art, titel, text, ordner, pruefen=()):
        self.letzter_dialog = (art, titel, text)
        if pruefen:
            erste = pruefen[0]
            frage = f"Vorschau von „{self._anzeigename(erste)}“ jetzt öffnen und prüfen?"
            if self._frage(titel, text + "\n\n" + frage, warnung=True):
                self.vorschau_oeffnen(erste, modus="nachher")
        elif ordner:
            if self._frage(titel, text + "\n\nErgebnisordner jetzt öffnen?", warnung=art == "warning"):
                self.ergebnisordner_oeffnen()
        else:
            self._dialog(art, titel, text)

    def ergebnisordner_oeffnen(self):
        ordner = list(self.letzte_ausgabeordner)
        if not ordner:
            self._dialog("info", "Kein Ergebnis", "Es wurde in dieser Sitzung noch keine Ausgabedatei erzeugt.")
            return
        if len(ordner) > 3:                                   # GR-12: nicht still nur die ersten drei
            stamm = dateien.gemeinsamer_stamm(ordner)
            if stamm is not None and dateien.oeffne_ordner(stamm):
                self._log(f"ℹ {len(ordner)} Ausgabeordner unterhalb von {stamm} – geöffnet wurde der gemeinsame "
                          f"Ordner (jeweils Unterordner „{dateien.AUSGABE_ORDNER}“).", "hinweis")
                return
            self._log(f"⚠ Geöffnet werden nur die ersten drei von {len(ordner)} Ausgabeordnern – alle stehen "
                      f"oben im Protokoll.", "warnung", zaehlen=False)
        for o in ordner[:3]:
            if not dateien.oeffne_ordner(o):
                self._log(f"⚠ Ordner konnte nicht geöffnet werden: {o}", "warnung", zaehlen=False)

    # ------------------------------------------------------------------
    # Hilfe
    # ------------------------------------------------------------------
    def hilfe_grenzen(self):
        self._dialog("info", "Was wird nicht erkannt?", GRENZEN_TEXT)

    def hilfe_hinweis(self):
        """Hilfe → „Hinweise vor der Nutzung …“: der Hinweis vom ersten Start (M-19)."""
        self.hinweis_zeigen()

    def hinweis_zeigen(self):
        if self.hinweis_dialog is not None:
            try:
                if self.hinweis_dialog.fenster.winfo_exists():
                    self.hinweis_dialog.fenster.lift()
                    return self.hinweis_dialog
            except tk.TclError:
                pass
        self.letzter_dialog = ("hinweis", ERSTSTART_TITEL, ERSTSTART_TEXT)
        self.hinweis_dialog = HinweisDialog(self)
        return self.hinweis_dialog

    def erststart_hinweis(self):
        """Beim Start (aus main()): den Hinweis zeigen, solange „Nicht mehr anzeigen“ nicht bestätigt wurde."""
        if self.beendet or self.hinweis_gelesen:
            return None
        try:
            return self.hinweis_zeigen()
        except tk.TclError:
            return None

    def hinweis_bestaetigt(self, nicht_mehr_anzeigen: bool):
        self.hinweis_dialog = None
        if bool(nicht_mehr_anzeigen) != self.hinweis_gelesen:
            self.hinweis_gelesen = bool(nicht_mehr_anzeigen)
            try:
                self.einstellungen_speichern()
            except Exception:
                dateien.fehler_protokollieren(*sys.exc_info())

    def hilfe_ueber(self):
        versionen = self._versionen()
        self._dialog("info", "Über PDF-Anonymisierer",
                     f"PDF-Anonymisierer {__version__}\n\nPseudonymisiert PDFs lokal auf diesem Rechner. Es werden "
                     f"keine Daten ins Internet übertragen.\n"
                     f"PyMuPDF {versionen['pymupdf']} · spaCy {versionen['spacy']} · Sprachmodell "
                     f"{versionen['modell']}\n\n"
                     f"Tastenkürzel: Alt+A = Analysieren, Alt+S = Schwärzen starten, Alt+V = Vorschau\n\n"
                     f"Fehlerprotokoll: {dateien.fehlerlog_pfad()}\n(enthält Dateinamen, aber keine Ordner und "
                     f"keine Dokumentinhalte)\nEinstellungen: {dateien.einstellungen_pfad()}")

    # ------------------------------------------------------------------
    # Laufprotokoll ohne Personendaten (M-61)
    # ------------------------------------------------------------------
    @staticmethod
    def _versionen() -> dict:
        """Programm-, PyMuPDF-, spaCy- und Modellversion (ohne das Modell zu laden)."""
        def paket(name):
            try:
                return importlib.metadata.version(name)
            except Exception:
                return "nicht installiert"
        pymupdf = str(getattr(fitz, "VersionBind", None) or getattr(fitz, "__version__", None) or paket("pymupdf"))
        mupdf = getattr(fitz, "VersionFitz", None)
        modell = None
        try:
            from . import namen as _namen
            nlp = getattr(_namen, "_NLP", None)
            if nlp is not None:
                meta = getattr(nlp, "meta", {}) or {}
                modell = f"{meta.get('lang', 'de')}_{meta.get('name', '?')} {meta.get('version', '')}".strip()
        except Exception:
            modell = None
        if modell is None:
            installiert = paket("de_core_news_md")
            modell = (f"de_core_news_md {installiert} (noch nicht geladen)" if installiert != "nicht installiert"
                      else "nicht installiert")
        return {"programm": __version__, "pymupdf": pymupdf + (f" (MuPDF {mupdf})" if mupdf else ""),
                "spacy": paket("spacy"), "modell": modell}

    def _ereignis(self, text: str):
        self.ereignisse.append((datetime.now().strftime("%d.%m.%Y %H:%M:%S"), text))

    def _dokument_nr(self, pdf: Path) -> int:
        return self.dateien.index(pdf) + 1 if pdf in self.dateien else 0

    def _kategorie_namen(self) -> dict:
        namen = {e[0]: e[1] for e in KATEGORIEN}
        namen.update({"begriff": "Begriffe (IMMER-Liste)", "manuell": "manuell markiert"})
        return namen

    def _protokoll_analyse(self, pdfs, ergebnisse: dict, abgebrochen: bool):
        """Zusammenfassung einer Analyse fürs Laufprotokoll: Zahlen, Kategorien und Meldungs-Codes – keine Texte,
        keine Dateinamen."""
        kontext = dict(self._lauf_kontext or {})
        dokumente = []
        for pdf in pdfs:
            e = ergebnisse.get(pdf)
            eintrag = {"nr": self._dokument_nr(pdf), "art": (self.arbeitskopien.get(pdf) or {}).get("art")}
            if e is None:
                eintrag["status"] = "nicht analysiert"
            else:
                angehakt, angeboten = {}, {}
                for i, fund in enumerate(e["funde"]):
                    ziel = angeboten if self.fund_zustand(pdf, i) == "aus" else angehakt
                    ziel[fund.get("kategorie", "?")] = ziel.get(fund.get("kategorie", "?"), 0) + 1
                nk = _nebenkanal_bezug(e)
                eintrag.update(status="Fehler" if e["fehler"] else "analysiert", seiten=e.get("seiten") or 0,
                               ocr_seiten=e.get("ocr_seiten") or 0, angehakt=angehakt, angeboten=angeboten,
                               codes=sorted(meldungs_codes(e)), nebenkanal=_nebenkanal_text(nk) if nk else None)
            dokumente.append(eintrag)
        self.laufprotokoll.append({"art": "Analyse", "zeit": datetime.now(), "abgebrochen": abgebrochen,
                                   "kontext": kontext, "dokumente": dokumente})

    def _protokoll_schwaerzung(self, auftraege, ergebnisse, abgebrochen: bool):
        kontext = dict(getattr(self, "_schwaerz_kontext", None) or {})
        nach_pdf = dict(ergebnisse)
        dokumente = []
        for auftrag in auftraege:
            pdf = auftrag["pdf"]
            e = nach_pdf.get(pdf)
            kategorien: dict[str, int] = {}
            for fund in auftrag["funde"]:
                kategorien[fund.get("kategorie", "?")] = kategorien.get(fund.get("kategorie", "?"), 0) + 1
            manuell = sum(len(v) for v in auftrag["bereiche"].values()) + sum(len(v) for v in auftrag["stellen"].values())
            if manuell:
                kategorien["manuell"] = manuell
            eintrag = {"nr": self._dokument_nr(pdf), "kategorien": kategorien,
                       "art": (self.arbeitskopien.get(pdf) or {}).get("art"),
                       "nur_nebenkanal": bool(auftrag.get("nur_nebenkanal"))}
            if e is None:
                eintrag.update(ausgabe=None, status="nicht verarbeitet", stellen=0, codes=[])
            else:
                analyse = self.analyse_ergebnisse.get(pdf) or {}
                codes = sorted(meldungs_codes(e) | (meldungs_codes(analyse) if analyse else set()))
                ausgabe = e.get("ausgabe")
                eintrag.update(ausgabe=Path(ausgabe).name if ausgabe is not None else None,
                               status=STATUS_TEXT.get(e.get("_status"), e.get("_status") or "?"),
                               stellen=int(e.get("treffer") or 0), verdacht=len(e.get("verdacht") or []),
                               codes=codes)
            dokumente.append(eintrag)
        self.laufprotokoll.append({"art": "Schwärzung", "zeit": datetime.now(), "abgebrochen": abgebrochen,
                                   "kontext": kontext, "dokumente": dokumente})

    def laufprotokoll_text(self) -> str:
        """Laufprotokoll als Text: Datum, Versionen, Schutzstufe, aktive Kategorien, ANZAHL der NIE-/IMMER-Einträge,
        je Dokument Ausgabename, Status, Anzahl je Kategorie und Meldungs-Codes. Bewusst OHNE Dokumenttext, ohne
        Originaldateinamen und ohne Ordner (die enthalten oft Kundennamen) – das Protokoll kann aufbewahrt werden."""
        v = self._versionen()
        namen = self._kategorie_namen()
        art_text = {"bild": "Bild → PDF", "entschluesselt": "Kennwort entfernt", "kopie": "PDF ohne Endung"}
        zeilen = ["PDF-Anonymisierer – Laufprotokoll",
                  f"Erstellt: {datetime.now():%d.%m.%Y %H:%M:%S}",
                  f"Programmversion: {v['programm']}",
                  f"PyMuPDF: {v['pymupdf']}",
                  f"spaCy: {v['spacy']} · Sprachmodell: {v['modell']}",
                  "Hinweis: Dieses Protokoll enthält keine Dokumentinhalte, keine Originaldateinamen und keine "
                  "Ordner. Dokumente sind nach ihrer Position in der Liste nummeriert.", ""]

        def kategorien_text(zahlen: dict) -> str:
            return ", ".join(f"{namen.get(k, k)} {n}" for k, n in sorted(zahlen.items())) or "keine"

        for nr, lauf in enumerate(self.laufprotokoll, 1):
            k = lauf["kontext"]
            kopf = f"──────── Lauf {nr}: {lauf['art']} · {lauf['zeit']:%d.%m.%Y %H:%M:%S}"
            zeilen.append(kopf + (" · ABGEBROCHEN" if lauf["abgebrochen"] else "") + " ────────")
            stufe = _profil_name(k.get("profil", ""))
            if k.get("profil") == attrappen.BENUTZERDEFINIERT:
                stufe += f" (Erkennungsregeln der Stufe „{_profil_name(k.get('basis_profil', ''))}“)"
            if stufe:
                zeilen.append(f"Schutzstufe: {stufe}")
            if lauf["art"] == "Analyse":
                zeilen.append("Aktive Kategorien: " + (", ".join(namen.get(a, a) for a in k.get("aktive", []))
                                                       or "keine"))
                zeilen.append(f"NIE-Liste: {k.get('nie', 0)} Eintrag/Einträge · IMMER-Liste: {k.get('immer', 0)} "
                              f"Eintrag/Einträge · Kundenliste: {'genutzt' if k.get('kundenliste') else 'nicht genutzt'}")
                for d in lauf["dokumente"]:
                    teile = [f"Dokument {d['nr']}"]
                    if d.get("art"):
                        teile.append(f"({art_text.get(d['art'], d['art'])})")
                    if d["status"] != "analysiert":
                        teile.append(f"– {d['status']}")
                    if "seiten" in d:
                        teile.append(f"– {d['seiten']} Seite(n)" + (f", {d['ocr_seiten']} per OCR"
                                                                     if d.get("ocr_seiten") else ""))
                        teile.append(f"– angehakt: {kategorien_text(d['angehakt'])}")
                        if d["angeboten"]:
                            teile.append(f"– nur angeboten: {kategorien_text(d['angeboten'])}")
                        if d.get("nebenkanal"):
                            teile.append(f"– Personendaten in {d['nebenkanal']}")
                        if d["codes"]:
                            teile.append(f"– Meldungen: {', '.join(d['codes'])}")
                    zeilen.append("  " + " ".join(teile))
            else:
                zeilen.append(f"Freigabe vor Weitergabe: {'an' if k.get('freigabe') else 'aus'}"
                              + (" (für Fotos immer)" if k.get("fotos") and not k.get("freigabe") else "")
                              + (" · Nachschwärzen" if k.get("nachschwaerzen") else "")
                              + (" · gemeinsamer Zielordner" if k.get("gemeinsamer_zielordner") else ""))
                for d in lauf["dokumente"]:
                    name = d["ausgabe"] or f"Dokument {d['nr']} (keine Ausgabe)"
                    teile = [f"{name} (Dokument {d['nr']})" if d["ausgabe"] else name, f"– {d['status']}"]
                    if d.get("art"):
                        teile.append(f"– {art_text.get(d['art'], d['art'])}")
                    teile.append(f"– {d['stellen']} Stelle(n) ersetzt")
                    teile.append(f"– geschwärzt: {kategorien_text(d['kategorien'])}")
                    if d.get("nur_nebenkanal"):
                        teile.append("– nur Metadaten/Anhänge bereinigt")
                    if d.get("verdacht"):
                        teile.append(f"– {d['verdacht']} Verdachtsstelle(n)")
                    if d["codes"]:
                        teile.append(f"– Meldungen: {', '.join(d['codes'])}")
                    zeilen.append("  " + " ".join(teile))
            zeilen.append("")
        if self.ereignisse:
            zeilen.append("──────── Ereignisse (Freigabe, Verwerfen, Nachschwärzen) ────────")
            zeilen += [f"  {zeit}  {text}" for zeit, text in self.ereignisse]
            zeilen.append("")
        if self.nicht_geprueft:
            zeilen.append(f"Nicht geprüft (keine PDF, nicht lesbar oder ohne Kennwort): {len(self.nicht_geprueft)} "
                          f"Datei(en) – Namen bewusst nicht im Protokoll.")
        return "\n".join(zeilen).rstrip() + "\n"

    def protokoll_speichern(self, pfad=None) -> Path | None:
        """Menü Datei → „Protokoll speichern …“: Laufprotokoll dieser Sitzung als Textdatei (M-61)."""
        if not self.laufprotokoll:
            self._dialog("info", "Protokoll speichern", "In dieser Sitzung gab es noch keinen Lauf – bitte zuerst "
                                                        "analysieren bzw. schwärzen.")
            return None
        if pfad is None:
            vorschlag = f"{dateien.PROTOKOLL_PRAEFIX}{datetime.now():%Y-%m-%d_%H-%M}.txt"
            ordner = self.letzte_ausgabeordner[0].parent if self.letzte_ausgabeordner else Path.home()
            pfad = filedialog.asksaveasfilename(title="Laufprotokoll speichern", parent=self.root,
                                                initialfile=vorschlag, initialdir=str(ordner),
                                                defaultextension=".txt", filetypes=[("Textdateien", "*.txt")])
            if not pfad:
                return None
        pfad = Path(pfad)
        try:
            pfad.write_text(self.laufprotokoll_text(), encoding="utf-8-sig")
        except OSError as fehler:
            self._dialog("error", "Protokoll nicht gespeichert", _verstaendliche_fehlermeldung(fehler, pfad))
            return None
        self._log(f"✔ Laufprotokoll gespeichert: {pfad.name} (ohne Dokumentinhalte und Originaldateinamen).", "ok")
        return pfad

    def fehlerlog_oeffnen(self):
        pfad = dateien.fehlerlog_pfad()
        try:
            pfad.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        if not dateien.oeffne_ordner(pfad.parent):
            self._dialog("info", "Fehlerprotokoll", f"Das Fehlerprotokoll liegt hier:\n{pfad}")

    # ------------------------------------------------------------------
    # Fehler, Dialoge, Protokoll (thread-sicher)
    # ------------------------------------------------------------------
    def _dialog(self, art, titel, text, eltern=None):
        """Zeigt einen Hinweis (nur im Hauptthread aufrufen) und merkt ihn sich für Tests."""
        text = _anzeigetext(text)
        self.letzter_dialog = (art, titel, text)
        zeiger = {"info": messagebox.showinfo, "warning": messagebox.showwarning,
                  "error": messagebox.showerror}[art]
        try:
            zeiger(titel, text, parent=eltern or self.root)
        except tk.TclError:
            pass

    def _frage(self, titel, text, warnung=False, eltern=None, standard_nein=False) -> bool:
        """Ja/Nein-Frage (nur im Hauptthread); merkt sich den Text für Tests. standard_nein: Enter = „Nein“."""
        text = _anzeigetext(text)
        self.letzter_dialog = ("askyesno", titel, text)
        optionen = {"default": messagebox.NO} if standard_nein else {}
        try:
            return bool(messagebox.askyesno(titel, text, icon="warning" if warnung else "question",
                                            parent=eltern or self.root, **optionen))
        except tk.TclError:
            return False

    def _fehler_melden(self, typ, wert, tb):
        """Unerwartete Ausnahme (Tk-Callback oder Arbeits-Thread): fehler.log + Protokoll + Dialog."""
        try:
            pfad = dateien.fehler_protokollieren(typ, wert, tb)
        except Exception:
            pfad = None
        try:
            self._fehler_dialog(pfad, wert)
        except Exception:
            pass

    def _fehler_dialog(self, pfad, wert):
        ort = str(pfad) if pfad else "(das Fehlerprotokoll konnte nicht geschrieben werden)"
        self._log(f"✖ Unerwarteter Fehler: {type(wert).__name__}: {str(wert)[:200]} – Details: {ort}", "fehler")
        self._dialog("error", "Unerwarteter Fehler",
                     f"Es ist ein unerwarteter Fehler aufgetreten:\n{type(wert).__name__}: {str(wert)[:300]}\n\n"
                     f"Details stehen in:\n{ort}")

    def _thread_excepthook(self, args):
        """Sicherheitsnetz für Threads ohne eigene Fehlerbehandlung."""
        pfad = dateien.fehler_protokollieren(args.exc_type, args.exc_value, args.exc_traceback)
        self._im_hauptthread(self._fehler_dialog, pfad, args.exc_value)
        self._im_hauptthread(self._lauf_notfall_freigeben)

    def _lauf_notfall_freigeben(self):
        if self.laeuft:
            self._lauf_beenden()
            self._status("Lauf nach Fehler beendet.")

    def _im_hauptthread(self, funktion, *args):
        """Führt eine Funktion im Tk-Hauptthread aus (aus Arbeits-Threads aufrufbar; im Hauptthread sofort)."""
        if self.beendet:
            return                                      # Fenster wird geschlossen, Nachzügler verwerfen
        if threading.current_thread() is threading.main_thread():
            try:
                funktion(*args)
            except tk.TclError:
                pass                                    # Fenster bereits geschlossen
            return
        try:
            self.root.after(0, funktion, *args)
        except tk.TclError:
            pass                                        # Fenster bereits geschlossen
        except RuntimeError:
            # Hauptthread verarbeitet keine Ereignisse (kein mainloop): nicht still verschlucken, aber nur einmal melden
            if not self._hauptthread_fehler_gemeldet and not self.beendet:
                self._hauptthread_fehler_gemeldet = True
                dateien.fehler_protokollieren(*sys.exc_info())

    def _log(self, text, stil=None, zaehlen=True):
        """Protokollzeile; Stil „warnung“/„fehler“ zählt als Warnung einer Datei – außer zaehlen=False für
        eigene Statuszeilen (Abbruch, Fertig-Zeile, Zusammenfassungen; GR-07)."""
        if not text:
            return
        text = _anzeigetext(text)

        def einfuegen():
            if zaehlen and stil in ("warnung", "fehler"):
                self.warnungen_anzahl += 1
                self._warnzaehler_anzeigen()
            self.protokoll.config(state="normal")
            self.protokoll.insert("end", text + "\n", stil or ())
            zeilen = int(self.protokoll.index("end-1c").split(".")[0])
            if zeilen > PROTOKOLL_MAX_ZEILEN:
                self.protokoll.delete("1.0", f"{zeilen - PROTOKOLL_MAX_ZEILEN}.0")
            self.protokoll.see("end")
            self.protokoll.config(state="disabled")

        self._im_hauptthread(einfuegen)

    def _trenner(self, titel):
        self._log(f"──────── {titel} ────────", "trenner")

    def _warnzaehler_anzeigen(self):
        self.warn_label.config(text=f"⚠ {self.warnungen_anzahl} Warnung(en)/Fehler" if self.warnungen_anzahl else "")

    def _status(self, text):
        self._im_hauptthread(lambda: self.status_label.config(text=text))

    def _fortschritt_setzen(self, wert):
        self._im_hauptthread(lambda: self.fortschritt.config(value=wert))

    def _fortschritt_maximum(self, maximum):
        self._im_hauptthread(lambda: self.fortschritt.config(maximum=maximum, value=0))

    def protokoll_text(self) -> str:
        return self.protokoll.get("1.0", "end").rstrip("\n")


def _bereits_gestartet_melden():
    """Zweiter Start (GR-10): Hinweis statt eines zweiten Fensters."""
    root = tk.Tk()
    root.withdraw()
    try:
        messagebox.showinfo("PDF-Anonymisierer läuft bereits",
                            "Das Programm ist bereits geöffnet – bitte das vorhandene Fenster verwenden "
                            "(Taskleiste). Zwei gleichzeitige Fenster würden sich Einstellungen und "
                            "Ausgabenummern gegenseitig überschreiben.", parent=root)
    except tk.TclError:
        pass
    finally:
        root.destroy()


def main(ereignisschleife: bool = True):
    """Startet die Oberfläche (eine Instanz je Benutzer); ohne Drag & Drop, wenn die tkdnd-Bibliothek nicht
    lädt. Liefert die App bzw. None, wenn bereits eine Instanz läuft."""
    global DND_VERFUEGBAR
    sperre = dateien.instanz_sperren()
    if sperre is None:
        _bereits_gestartet_melden()
        return None
    root = None
    if DND_VERFUEGBAR and TkinterDnD is not None:
        try:
            root = TkinterDnD.Tk()
        except Exception as fehler:          # z. B. tkdnd-DLL fehlt oder vom Virenscanner blockiert
            DND_VERFUEGBAR = False
            dateien.fehler_protokollieren(type(fehler), fehler, fehler.__traceback__)
    if root is None:
        root = tk.Tk()
    # Arbeitskopien früherer Sitzungen (z. B. nach einem Absturz) löschen – unter der Einzelinstanz-Sperre läuft
    # keine andere Sitzung dieses Benutzers
    try:
        dateien.alte_sitzungen_aufraeumen()
    except Exception:
        dateien.fehler_protokollieren(*sys.exc_info())
    app = AnonymisiererApp(root, modell_vorladen=True)
    app.instanz_sperre = sperre
    app._nach_start.append(root.after(ERSTSTART_NACH_MS, app.erststart_hinweis))

    def zerstoert(ereignis):
        if ereignis.widget is root:
            app._aufraeumen()

    root.bind("<Destroy>", zerstoert, add="+")
    if ereignisschleife:
        root.mainloop()
    return app
