"""OCR (Texterkennung für eingescannte PDFs) auf Basis des in PyMuPDF eingebauten Tesseract.

Öffentliche Schnittstelle (CONTRACT.md, CONTRACT_V2.md 12.3):
    _tessdata_finden()                      Sprachdaten-Ordner suchen (Projekt-tessdata zuerst)
    seiten_pruefung(seite)                  EINE Heuristik für Analyse, Schwärzung und Kontrolle:
                                            SeitenPruefung(modus, bereiche, zeichen, bildanteil, meldungen)
    ocr_noetig(seite, meldungen=None)       "nein" | "seite" | "bilder"   (= seiten_pruefung(...).modus)
    bild_bereiche(seite, meldungen=None)    relevante Bildbereiche (= seiten_pruefung(...).bereiche)
    woerter_zu_zeilen(woerter, winkel=None, schraeg=None)
                                            robuste Zeilenbildung für OCR-Wörter -> list[list[Wort]]
                                            (gerade gerückt; Etikett und Wert derselben Höhe = eine Zeile)
    woerter_zu_text(woerter, winkel=None)   Text aus woerter_zu_zeilen (Zeilen "\\n", Wörter " ")
    lesekasten(w, winkel, schraeg)          Wortkasten in gerade gerückten Lesekoordinaten
    ausrichtung_der_woerter(woerter)        (winkel, schraeg) einer Wortliste (aus den 10-Tupeln)
    tessdata_mit_einstellungen(tessdata, sprache, einstellungen=None)
                                            Ordner mit traineddata-Kopie samt Tesseract-Einstellungen
    schraeglage_schaetzen(grau), hintergrund_ungleichmaessig(grau), hintergrund_herausrechnen(grau)
    class OcrDienst                         OCR im Prozess-Pool (Start-Methode "spawn"):
        woerter / ergebnis / text / winkel / winkel_falls_bekannt / vorab / selbsttest /
        abbrechen / zuruecksetzen / schliessen (Context-Manager)
Kompatibilität für ältere Aufrufer: ist_scan_seite(seite), ocr_textpage(seite).

Koordinaten: Alle Wörter (x0, y0, x1, y1, text[, block, zeile, wort, winkel, schraeg]) beziehen sich auf die
Seite NACH page.remove_rotation(). Ein Wort ist ein 5-Tupel (woerter()) bzw. 10-Tupel (ergebnis()["woerter"]):
die letzten beiden Werte sind die erkannte Ausrichtung (0/90/180/270) und die für die OCR herausgedrehte
Schräglage in Grad (0, wenn die Seite nicht gerade gerückt wurde) – so trägt jede Wortliste (auch der ocr_cache
zwischen Analyse und Schwärzung) alles, was die Zeilenbildung braucht, und Analyse, Schwärzung und Kontrolle
bilden dieselben Zeilen.

Seitenaufteilung (Messung Phase 3): PyMuPDF reicht keine Parameter an das eingebaute Tesseract durch, das
deshalb mit seiner Bibliotheks-Voreinstellung PSM 6 ("ein einheitlicher Textblock") liest. Zweispaltige
Briefköpfe werden so verzahnt ("04109 Leipzi Telefon pzig"), auf schrägen Tabellen-Scans fällt jede zweite
Zeile aus. Volle Lesungen laufen deshalb mit PSM 3 (automatische Seitenaufteilung wie die Tesseract-
Kommandozeile): Die Einstellung steht in der Komponente "config" einer Kopie der traineddata-Datei
(tessdata_mit_einstellungen), die Tesseract beim Laden übernimmt. Gemessen auf den Scan-Seiten des
Entwicklungskorpus: 79 % -> 93 % der Wahrheitstexte im OCR-Text bei +10 % OCR-Zeit. Die Ausrichtungsproben
(100 dpi) bleiben bei PSM 6 – dafür sind ihre Schwellen gemessen.

Ausrichtung (Gutachten S-01/PERF-02): Gedrehter Text liefert bei Tesseract keinen erkennbaren Müll,
sondern wortähnlichen Buchstabensalat ("youyseN uuewlesjsnyy"). Maß ist deshalb der Anteil "starker"
Wörter: häufige deutsche (und einige englische) Wörter ab drei Buchstaben sowie wohlgeformte Daten,
Beträge, IBAN-Anfänge, E-Mail-Adressen. Aufrechte Seiten liegen bei 0,12-0,60, gedrehte bei 0,00-0,02.
Reihenfolge: 0° zuerst; ist 0° nicht klar plausibel, wird IMMER 180° gelesen; 90°/270° nur, wenn weder
0° noch 180° plausibel sind. Eine Drehung gewinnt nur, wenn sie deutlich besser ist als 0° (aufrechte
Code-Tabellen bleiben bei 0°). Bleibt die beste Lesung unplausibel: Meldung OCR_UNPLAUSIBEL.
"""

import concurrent.futures
import concurrent.futures.process  # registriert sein Beenden-Hook vor unserem (siehe _beim_beenden)
import hashlib
import math
import multiprocessing
import os
import re
import struct
import sys
import tempfile
import threading
import time
import unicodedata
import warnings
import weakref
from pathlib import Path
from typing import NamedTuple

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen kennen nur den Namen "fitz"
    import fitz

Wort = tuple  # (x0, y0, x1, y1, text) bzw. (x0, y0, x1, y1, text, block, zeile, wort)

PROJEKTWURZEL = Path(__file__).resolve().parent.parent

# ----------------------------------------------------------------------
# Schwellen der Seiten-Heuristik (ocr_noetig / bild_bereiche) – EINE Quelle für alle Nutzer
# ----------------------------------------------------------------------
BILD_ABSTAND_PT = 2.0         # Bilder, die sich bis auf diesen Abstand nähern, bilden EINEN Bereich
                              # (Kacheln, Streifen-Scans aus 50-300 Bändern, PERF-03)
MIN_BILD_ANTEIL = 0.0025      # zusammengefasste Bereiche unter 0,25 % der Seitenfläche (Icons, Aufzählungs-
                              # zeichen) zählen nicht; ein Stempel- oder Unterschriftsbild (ca. 80 x 30 pt)
                              # liegt darüber. Die Schwelle gilt NACH dem Zusammenfassen.
MIN_BILD_KANTE_PT = 6.0       # schmaler als 6 pt (Linien, Rahmen als Bild) trägt keinen lesbaren Text
SCAN_BILD_ANTEIL = 0.20       # ab 20 % Bildfläche (in Summe) gilt eine textarme Seite als Scan
WENIG_TEXT_ZEICHEN = 200      # weniger sichtbare Zeichen = textarm (Stempel, Faxkopf, Seitenzahl, DMS-Fuß)
AUSRICHTUNG_BILD_ANTEIL = 0.20  # Bildbereiche ab dieser Größe bekommen ebenfalls die Ausrichtungssuche

# ----------------------------------------------------------------------
# Ausrichtung / Plausibilität der OCR-Wörter
# ----------------------------------------------------------------------
WORTQUOTE_KLAR = 0.10         # 0° mit >= 10 % starken Wörtern (und >= 2 Treffern): keine weitere Drehung
WORTQUOTE_MIN = 0.05          # darunter (oder < 2 Treffer) gilt eine Lesung als unplausibel
MIN_TREFFER = 2               # so viele starke Wörter braucht eine plausible Lesung mindestens
KLEINE_SEITE_TOKENS = 5       # bis zu so vielen Wörtern reicht 1 starkes Wort (Stempel, Seitenzahl) ...
KLEINE_SEITE_SALAT = 15       # ... bei Proben aber nur, wenn auch die volle 0°-Lesung kurz war (<= 15 Wörter):
                              # sonst könnte auf einer Handschrift-/Rauschseite ein zufälliges "den" in einer
                              # Probe mit 3 Wörtern eine Drehung wählen und die Warnung unterdrücken
MIN_TOKENS_SUCHE = 4          # weniger Wörter bei 0°: nichts, was sich auszurichten lohnt
MIN_TOKENS_WARNUNG = 10       # erst ab so vielen Wörtern wird "unplausibel" gemeldet
DREHUNG_FAKTOR = 2.0          # eine Drehung gewinnt nur mit >= 2-facher Quote von 0° ...
DREHUNG_VORSPRUNG = 0.03      # ... und mindestens 3 Prozentpunkten Vorsprung
PROBE2_DPI = 200              # zweite Probenstufe, wenn keine 100-dpi-Probe plausibel ist, die Seite aber Text
                              # trägt: kleine Schrift (Tabellen, 8-9 pt) ist bei 100 dpi unlesbar, und PSM 6 liest
                              # Tabellen auch richtig herum nicht – gemessen: kopfstehende/seitliche Bestandslisten
                              # blieben ungedreht (0 von 73 Einträgen lesbar); die Stufe liest mit PSM 3 und 200 dpi
PROBE_DPI = 100               # Ausrichtungsproben (nur wenn 0° bei voller Auflösung nicht klar ist): bei 100 dpi
                              # liegt die richtige Ausrichtung gemessen bei 0,30-0,62, jede falsche <= 0,04; eine
                              # Probe kostet 0,1-4 s statt 5-13 s Buchstabensalat bei 300 dpi, und Fotos mit
                              # Bildunterschrift ertrinken nicht im Rauschen (300 dpi: 695 Rauschwörter).
PLAUSIBEL_SKALA = 0.25        # "plausibel" (0..1) = min(1, Quote / 0,25) – Kompatibilität zur alten Skala
PLAUSIBEL_GUT = 0.75          # alte Namen (Skala 0..1), nur noch für Aufrufer, die sie importieren
PLAUSIBEL_WARNUNG = 0.40      # unter 0,40 (= Quote 0,10) melden alte Ergebnisse ohne Flag "unplausibel"

OCR_ZEITLIMIT_S = 900         # Sekunden je Auftrag (ab Beginn des Wartens), danach gilt er als gescheitert
OCR_DPI = 300
MAX_FEHLVERSUCHE = 2          # ein Auftrag, der den Arbeiter zweimal abstürzen lässt, wird übersprungen

# ----------------------------------------------------------------------
# Tesseract-Einstellungen der vollen Lesungen (siehe Modulbeschreibung "Seitenaufteilung")
# ----------------------------------------------------------------------
SEITENAUFTEILUNG = 3          # Tesseract-PSM 3: Spalten, Blöcke und Tabellenzeilen automatisch finden
OCR_EINSTELLUNGEN = {"tessedit_pageseg_mode": str(SEITENAUFTEILUNG)}
_TRAINEDDATA_CONFIG = 0       # Index der Komponente "config" (lang.config) im traineddata-Archiv
_TRAINEDDATA_MAX_EINTRAEGE = 1000

# ----------------------------------------------------------------------
# Schräglage und Hintergrund (Bildanalyse vor der OCR, numpy optional)
# ----------------------------------------------------------------------
SCHRAEG_DPI = 100             # Auflösung der Schräglagen-Schätzung (Projektionsprofil dunkler Pixel)
SCHRAEG_MAX_GRAD = 5.0        # gesucht wird in -5° … +5° (größere Winkel: Ausrichtungssuche 90/180/270)
SCHRAEG_MIN_GRAD = 0.1        # darunter gilt eine Seite als gerade
SCHRAEG_KORREKTUR_AB = 1.0    # ab 1° Schräglage wird für die OCR gerade gerückt gerendert: darüber verliert
                              # die Seitenaufteilung Zeilen (gemessen: 3 Zeilen eines 2,85°-Absatzes fehlten)
                              # und ordnet Formularwerte der Nachbarzeile zu; darunter kein Gewinn
SCHRAEG_MIN_PIXEL = 400       # weniger dunkle Pixel: zu wenig Text für eine Schätzung
SCHRAEG_MAX_PIXEL = 150_000   # mehr dunkle Pixel werden gleichmäßig ausgedünnt (Laufzeit)
TINTE_MIN = 0.005             # ab 0,5 % dunkler Pixel trägt eine Seite sichtbar Inhalt: liest die Seitenaufteilung
                              # dort (fast) nichts (Handschrift, Kritzel – PSM 3 verwirft sie als Nicht-Text),
                              # laufen trotzdem die Proben, damit OCR_UNPLAUSIBEL gemeldet werden kann
HINTERGRUND_BLOCK = 16        # Blockgröße (Pixel) der Hintergrund-Schätzung bei OCR_DPI
HINTERGRUND_SPANNE = 40       # Grauwert-Spanne des Hintergrunds (5.-95. Perzentil), ab der er ungleichmäßig
                              # ist (Schatten, Fotos, Kopierränder) und vor der OCR herausgerechnet wird.
                              # Gleichmäßiges Papier bleibt unverändert (gemessen: dort kein Gewinn).

_RANDZEICHEN = ".,;:!?()[]{}\"'„“”‚‘’«»/\\|<>*-–—_•·"

# Häufige Wörter (klein, >= 3 Buchstaben): Funktionswörter und Geschäfts-/Versicherungskorrespondenz,
# dazu englische und einige romanische/türkische/polnische Funktionswörter (fremdsprachige Seiten sollen
# nicht als "verdreht" gelten). Buchstabensalat verdrehter Seiten trifft diese Wörter praktisch nie.
_HAEUFIGE_WOERTER = frozenset("""
und oder aber auch als wie wenn dass daß weil damit sowie bzw ggf evtl inkl zzgl usw etc der die das den dem
des ein eine einen einem einer eines kein keine keinen keinem keiner nicht nur noch schon bereits sehr mehr
viel viele vielen alle allen aller alles jede jeder jedes jeden jedem dieser diese dieses diesen diesem
welche welcher welches welchen wir sie ihr ihre ihren ihrem ihrer ihres ihnen uns unser unsere unseren
unserem unserer ich mich mir mein meine meinen meinem meiner sich man ist sind war waren wird werden wurde
wurden worden sein seine seinen seinem seiner hat haben hatte hatten habe kann können konnte konnten muss
müssen musste soll sollen sollte sollten darf dürfen will wollen möchten möchte gibt geben bitte danke dank
mit für von vom zum zur bei beim nach über unter aus auf durch gegen ohne bis seit während wegen trotz laut
gemäß per pro zwischen hier dort dann denn doch also etwa rund ganz gern gerne heute morgen jetzt immer
wieder hiermit anbei folgende folgenden folgendes weitere weiteren weiterer jedoch daher deshalb dazu davon
dafür darauf darüber hierzu hierbei insgesamt nämlich sofern soweit falls was wer wem wen warum wann wie
neu neue neuen neuer alt alte alten erste ersten zweite letzte letzten gut beide beiden andere anderen
sehr geehrte geehrter geehrten herr herrn frau damen herren freundlichen freundlicher grüßen gruß grüße
betreff datum seite seiten anlage anlagen unterschrift telefon tel fax mail e-mail internet www iban bic
bank konto kontoinhaber nummer versicherung versicherungen versicherungsschein versicherungsnehmer
versicherungsnehmerin versicherte versicherten versicherer vertrag vertrages vertrags verträge beitrag
beiträge beitrags leistung leistungen schaden schadens schäden schadenmeldung antrag anträge police tarif
tarife kunde kunden kundin kundennummer person personen name vorname nachname geburtsdatum geboren
anschrift adresse straße str ort plz postfach land deutschland euro eur betrag beträge summe gesamt
zahlung zahlungen rechnung rechnungen monat monate monatlich jahr jahre jahres jahren jährlich quartal tag
tage tagen woche wochen termin frist fristen beginn ende ablauf laufzeit kündigung änderung änderungen
mitteilung information informationen hinweis hinweise unterlagen dokument dokumente angaben frage fragen
rückfragen verfügung stehen steht erhalten erhalt gezahlt erstattung erstatten überweisen überwiesen
gutschrift abrechnung leistungsabrechnung gesellschaft gmbh mbh krankenversicherung lebensversicherung
haftpflicht hausrat rente renten rentenversicherung kranken unfall kfz fahrzeug kennzeichen halter
sachbearbeiter sachbearbeiterin ansprechpartner ansprechpartnerin kundenservice service büro abteilung
januar februar märz april mai juni juli august september oktober november dezember montag dienstag
mittwoch donnerstag freitag samstag sonntag uhr nein bitte vers
the and for with you your this that are from have has had will would not our all can could been was were
which their there they his her she him any may date name policy insurance dear please sincerely regards
yours thank thanks page number amount total account address phone email claim claims payment customer
letter contact questions regarding should also other more about into than them these those such only
les des est pour dans une que qui avec sur par pas vous nous votre sont che del della non con sono gli
los las por para usted bir için ile olarak nie jest się dla oraz
""".split())

_STRUKTUR_TOKEN = re.compile(
    r"(?:0?[1-9]|[12]\d|3[01])\.(?:0?[1-9]|1[0-2])\.(?:\d{2}|\d{4})"   # Datum 02.09.1983
    r"|\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2}"                             # Betrag 1.287,60 / 1278,01
    r"|\d+,\d{1,2}%"                                                     # 3,5%
    r"|(?:[01]?\d|2[0-3]):[0-5]\d"                                       # Uhrzeit 09:12
    r"|[A-Z]{2}\d{2}"                                                    # IBAN-Anfang DE44
    r"|[\w.+-]+@[\w-]+(?:\.[\w-]+)+"                                    # E-Mail
    r"|www\.[\w-]+(?:\.[\w-]+)+")                                       # Web-Adresse
# "Lange" Treffer: im Buchstabensalat praktisch nie zufällig (zufällige Treffer sind kurz: den, Ein, are)
_LANGE_STRUKTUR = re.compile(
    r"(?:0?[1-9]|[12]\d|3[01])\.(?:0?[1-9]|1[0-2])\.(?:\d{2}|\d{4})|\d{1,3}(?:\.\d{3})*,\d{2}"
    r"|[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


class OcrAbgebrochen(Exception):
    """Die OCR wurde über OcrDienst.abbrechen() gestoppt."""


def _meldung(art, code, text, seite=None) -> dict:
    """Strukturierte Meldung (Vertrag 12.6)."""
    return {"art": art, "code": code, "text": text, "seite": seite}


def _protokollieren(fehler: BaseException):
    """Unerwartete Ausnahme in fehler.log festhalten (Gutachten KQ-12: nichts still verschlucken)."""
    try:
        from .dateien import fehler_protokollieren
        fehler_protokollieren(type(fehler), fehler, fehler.__traceback__)
    except Exception:
        pass


# ----------------------------------------------------------------------
# Sprachdaten
# ----------------------------------------------------------------------
def _hat_sprachdaten(ordner) -> bool:
    try:
        return any(Path(ordner).glob("*.traineddata"))
    except OSError:
        return False


def _tessdata_finden():
    """Sucht den Tesseract-Sprachdaten-Ordner.

    Reihenfolge: $TESSDATA_PREFIX (nur, wenn dort *.traineddata liegt), <Projektwurzel>/tessdata
    (mitgelieferte deu.traineddata), sys._MEIPASS/tessdata (PyInstaller), dann die üblichen
    Installationspfade. Rückgabe: Pfad als str oder None.
    """
    kandidaten = []
    umgebung = os.environ.get("TESSDATA_PREFIX")
    if umgebung:
        kandidaten.append(umgebung)
    kandidaten.append(PROJEKTWURZEL / "tessdata")
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        kandidaten.append(Path(meipass) / "tessdata")
    if sys.platform == "win32":
        kandidaten += [
            r"C:\Program Files\Tesseract-OCR\tessdata",
            r"C:\Program Files (x86)\Tesseract-OCR\tessdata",
            str(Path.home() / r"AppData\Local\Programs\Tesseract-OCR\tessdata"),
        ]
    else:
        kandidaten += ["/usr/share/tesseract-ocr/5/tessdata",
                       "/usr/share/tesseract-ocr/4.00/tessdata",
                       "/usr/share/tessdata", "/usr/local/share/tessdata"]
    for k in kandidaten:
        if k and _hat_sprachdaten(k):
            pfad = str(Path(k))
            os.environ["TESSDATA_PREFIX"] = pfad
            return pfad
    return None


def _ocr_sprache(tessdata):
    """Liefert (Sprachkürzel oder None, Warnung oder None) für den Sprachdaten-Ordner."""
    if tessdata is None:
        return None, ("Tesseract-Sprachdaten nicht gefunden – Scans können nicht gelesen werden. "
                      "Der Ordner »tessdata« mit deu.traineddata muss neben dem Programm liegen "
                      "(Installieren.bat erneut ausführen).")
    if (Path(tessdata) / "deu.traineddata").exists():
        return "deu", None
    if (Path(tessdata) / "eng.traineddata").exists():
        return "eng", ("Deutsche OCR-Sprachdatei fehlt – nutze Englisch "
                       "(Umlaute werden evtl. falsch erkannt).")
    return None, "Keine OCR-Sprachdatei gefunden – Installieren.bat erneut ausführen."


def traineddata_mit_einstellungen(daten: bytes, einstellungen: dict) -> bytes:
    """Kopie einer traineddata-Datei, deren Komponente "config" (lang.config) die Tesseract-Einstellungen
    enthält; Tesseract liest sie beim Laden der Sprache (TessdataManager: uint32 Anzahl der Einträge,
    int64-Versatz je Eintrag oder -1, danach die Komponenten lückenlos in Index-Reihenfolge).
    Vorhandene Zeilen der Komponente bleiben, gleichnamige Einstellungen werden ersetzt.
    ValueError, wenn die Daten kein traineddata-Archiv sind."""
    if len(daten) < 4:
        raise ValueError("traineddata zu kurz")
    anzahl = struct.unpack_from("<I", daten, 0)[0]
    kopf = 4 + 8 * anzahl
    if not 1 <= anzahl <= _TRAINEDDATA_MAX_EINTRAEGE or len(daten) < kopf:
        raise ValueError("kein traineddata-Archiv")
    versatz = struct.unpack_from(f"<{anzahl}q", daten, 4)
    vorhanden = [(i, o) for i, o in enumerate(versatz) if o >= 0]
    teile = {}
    for k, (i, o) in enumerate(vorhanden):
        ende = vorhanden[k + 1][1] if k + 1 < len(vorhanden) else len(daten)
        if not kopf <= o <= ende <= len(daten):
            raise ValueError("traineddata-Verzeichnis beschädigt")
        teile[i] = daten[o:ende]
    if _TRAINEDDATA_CONFIG >= anzahl:
        raise ValueError("traineddata ohne Platz für eine Konfiguration")
    alt = teile.get(_TRAINEDDATA_CONFIG, b"").decode("utf-8", "replace").splitlines()
    zeilen = [z for z in alt if z.split()[:1] and z.split()[0] not in einstellungen]
    zeilen += [f"{schluessel} {wert}" for schluessel, wert in sorted(einstellungen.items())]
    teile[_TRAINEDDATA_CONFIG] = ("\n".join(zeilen) + "\n").encode("utf-8")
    neu_versatz, inhalt, pos = [], [], kopf
    for i in range(anzahl):
        if i in teile:
            neu_versatz.append(pos)
            inhalt.append(teile[i])
            pos += len(teile[i])
        else:
            neu_versatz.append(-1)
    return struct.pack("<I", anzahl) + struct.pack(f"<{anzahl}q", *neu_versatz) + b"".join(inhalt)


_EINSTELLUNGS_ORDNER: dict = {}       # (tessdata, sprache, Einstellungen) -> Ordner (je Prozess)


def tessdata_mit_einstellungen(tessdata, sprache, einstellungen=None):
    """Ordner mit einer Kopie von <sprache>.traineddata, die `einstellungen` (Standard: OCR_EINSTELLUNGEN)
    enthält – für pdfocr_tobytes(tessdata=...). Der Ordner liegt im Temp-Verzeichnis (der Programmordner kann
    schreibgeschützt sein) und ist nach Inhalt benannt; fehlt die Datei (z. B. von der Datenträgerbereinigung
    gelöscht), wird sie neu angelegt. Rückgabe: Ordner oder None (dann liest die OCR mit der Voreinstellung)."""
    if not tessdata or not sprache:
        return None
    einstellungen = OCR_EINSTELLUNGEN if einstellungen is None else einstellungen
    schluessel = (str(tessdata), str(sprache), tuple(sorted(einstellungen.items())))
    ordner = _EINSTELLUNGS_ORDNER.get(schluessel)
    if ordner is not None and (Path(ordner) / f"{sprache}.traineddata").exists():
        return ordner
    try:
        daten = (Path(tessdata) / f"{sprache}.traineddata").read_bytes()
        neu = traineddata_mit_einstellungen(daten, einstellungen)
        kennung = hashlib.blake2b(neu, digest_size=10).hexdigest()
        ziel = Path(tempfile.gettempdir()) / "pdf-anonymisierer-ocr" / kennung
        datei = ziel / f"{sprache}.traineddata"
        if not (datei.exists() and datei.stat().st_size == len(neu) and datei.read_bytes() == neu):
            ziel.mkdir(parents=True, exist_ok=True)
            tmp = ziel / f".{sprache}.{os.getpid()}.{threading.get_ident()}.tmp"
            tmp.write_bytes(neu)
            os.replace(tmp, datei)
        _EINSTELLUNGS_ORDNER[schluessel] = str(ziel)
        return str(ziel)
    except Exception as e:      # Temp-Ordner nicht beschreibbar, Datei beschädigt …
        _protokollieren(e)
        return None


# ----------------------------------------------------------------------
# Seiten-Heuristik: EINE Entscheidung für Analyse, Schwärzung und Kontrolle (KQ-06/S-15)
# ----------------------------------------------------------------------
class SeitenPruefung(NamedTuple):
    modus: str              # "nein" | "seite" | "bilder"
    bereiche: list          # relevante Bildbereiche (fitz.Rect, zusammengefasst, auf die Seite beschnitten)
    zeichen: int            # sichtbare Textzeichen
    bildanteil: float       # Fläche der Bereiche / Seitenfläche
    meldungen: list         # strukturierte Meldungen (z. B. fehlgeschlagene Bildanalyse)


def _vereinige(rechtecke, abstand: float = BILD_ABSTAND_PT) -> list:
    """Fasst sich überlappende oder bis auf `abstand` nahe Rechtecke zusammen (Kacheln, Streifen -> ein
    Bereich). Sweep über x mit Union-Find, wiederholt, bis keine Bereiche mehr zusammenwachsen –
    auch tausende Streifen kosten nur Millisekunden."""
    rs = [fitz.Rect(r) for r in rechtecke]
    rs = [r for r in rs if not r.is_empty and not r.is_infinite]
    while True:
        rs.sort(key=lambda r: r.x0)
        eltern = list(range(len(rs)))

        def wurzel(i):
            while eltern[i] != i:
                eltern[i] = eltern[eltern[i]]
                i = eltern[i]
            return i

        aktiv: list = []
        for i, r in enumerate(rs):
            aktiv = [j for j in aktiv if rs[j].x1 + abstand >= r.x0]
            for j in aktiv:
                a = rs[j]
                if a.y0 - abstand <= r.y1 and r.y0 - abstand <= a.y1:
                    wi, wj = wurzel(i), wurzel(j)
                    if wi != wj:
                        eltern[wi] = wj
            aktiv.append(i)
        gruppen: dict = {}
        for i, r in enumerate(rs):
            w = wurzel(i)
            gruppen[w] = gruppen[w] | r if w in gruppen else fitz.Rect(r)
        neu = list(gruppen.values())
        if len(neu) == len(rs):
            return neu
        rs = neu


def _relevant(r, seitenrect) -> bool:
    """Ein (zusammengefasster) Bildbereich kann lesbaren Text tragen."""
    flaeche = abs(seitenrect) or 1.0
    return (abs(r) >= MIN_BILD_ANTEIL * flaeche and min(r.width, r.height) >= MIN_BILD_KANTE_PT)


def _sichtbare_zeichen(seite, meldungen=None) -> int:
    """Anzahl sichtbarer Textzeichen auf der Seite. Unsichtbarer Text (Rendermodus 3, z. B. die OCR-Ebene
    eines Kopierers) und völlig transparenter Text zählen nicht – sonst gälte ein durchsuchbarer Scan als
    Textseite."""
    try:
        anzahl = 0
        rect = seite.rect
        for span in seite.get_texttrace():
            if span.get("type", 0) == 3 or span.get("opacity", 1) == 0:
                continue
            for z in span["chars"]:
                if chr(z[0]).isspace():
                    continue
                box = fitz.Rect(z[3]) if len(z) > 3 else None
                if box is not None and not box.is_empty and not box.intersects(rect):
                    continue
                anzahl += 1
        return anzahl
    except Exception as e:      # Rückfall: einfacher Text (zählt unsichtbaren Text mit)
        _protokollieren(e)
        try:
            return len(re.sub(r"\s", "", seite.get_text()))
        except Exception as e2:
            _protokollieren(e2)
            if meldungen is not None:
                meldungen.append(_meldung("warnung", "BILDER_UNGEPRUEFT",
                                          f"Seite {seite.number + 1}: Text der Seite nicht prüfbar ({e2}) – "
                                          f"sie wird vorsorglich per OCR gelesen.", seite.number))
            return 0


def _hat_zeichnungen(seite) -> bool:
    """Vektorgrafik auf der Seite (z. B. in Pfade gewandelter Text). Im Fehlerfall True (vorsorglich OCR)."""
    try:
        return any(art.endswith("path") and "clip" not in art for art, _ in seite.get_bboxlog())
    except Exception as e:
        _protokollieren(e)
        return True


def seiten_pruefung(seite) -> SeitenPruefung:
    """Entscheidet je Seite, ob und wie OCR nötig ist (dokumentierte Schwellen oben).

    modus "seite":  Scan – OCR der ganzen Seite: kein sichtbarer Text (Bilder oder Vektorgrafik vorhanden)
                    oder textarm (< WENIG_TEXT_ZEICHEN) mit Bildfläche >= SCAN_BILD_ANTEIL. Stempel,
                    Faxkopf, Kacheln und Streifen-Scans ändern daran nichts: die Bildfläche zählt in Summe,
                    die Mindestgröße gilt erst nach dem Zusammenfassen.
    modus "bilder": Textseite mit relevanten Bildbereichen (Briefkopf, Unterschrift, Ausweiskopie, Foto,
                    ganzseitiges Hintergrundbild) – OCR dieser Bereiche.
    modus "nein":   reiner Text.
    Schlägt die Bildanalyse fehl, wird die ganze Seite als Bildbereich behandelt (vorsorglich OCR) und eine
    Meldung BILDER_UNGEPRUEFT erzeugt – nie still "kein Bild" (Gutachten KQ-12).
    """
    meldungen: list = []
    seitenrect = fitz.Rect(seite.rect)
    try:
        infos = seite.get_image_info()
        rechtecke = []
        for info in infos:
            r = fitz.Rect(info["bbox"]) & seitenrect
            if not r.is_empty and not r.is_infinite:
                rechtecke.append(r)
        bereiche = [r for r in _vereinige(rechtecke) if _relevant(r, seitenrect)]
    except Exception as e:
        _protokollieren(e)
        meldungen.append(_meldung("warnung", "BILDER_UNGEPRUEFT",
                                  f"Seite {seite.number + 1}: Bildanalyse fehlgeschlagen ({e}) – die ganze "
                                  f"Seite wird vorsorglich per OCR gelesen, bitte prüfen.", seite.number))
        bereiche = [seitenrect]
    flaeche = abs(seitenrect) or 1.0
    bildanteil = sum(abs(r) for r in bereiche) / flaeche
    zeichen = _sichtbare_zeichen(seite, meldungen)
    if zeichen == 0:
        modus = "seite" if bereiche or _hat_zeichnungen(seite) else "nein"
    elif zeichen < WENIG_TEXT_ZEICHEN and bildanteil >= SCAN_BILD_ANTEIL:
        modus = "seite"
    else:
        modus = "bilder" if bereiche else "nein"
    return SeitenPruefung(modus, bereiche, zeichen, bildanteil, meldungen)


def bild_bereiche(seite, meldungen=None) -> list:
    """Relevante Bildbereiche der Seite (zusammengefasst, auf die Seite beschnitten, Winzlinge entfernt).
    meldungen: optionale Liste, an die Meldungen (fehlgeschlagene Bildanalyse) angehängt werden."""
    pruefung = seiten_pruefung(seite)
    if meldungen is not None:
        meldungen.extend(pruefung.meldungen)
    return pruefung.bereiche


def ocr_noetig(seite, meldungen=None) -> str:
    """"nein" | "seite" | "bilder" – siehe seiten_pruefung()."""
    pruefung = seiten_pruefung(seite)
    if meldungen is not None:
        meldungen.extend(pruefung.meldungen)
    return pruefung.modus


def ist_scan_seite(seite) -> bool:
    """Kompatibilität: True, wenn die ganze Seite per OCR gelesen werden muss."""
    return ocr_noetig(seite) == "seite"


# ----------------------------------------------------------------------
# Plausibilität und Ausrichtung
# ----------------------------------------------------------------------
def _lesung_bewerten(texte) -> dict:
    """Bewertet eine OCR-Lesung: {"quote": Anteil starker Wörter, "treffer": Anzahl, "tokens": Wörter}.
    Stark = häufiges Wort (>= 3 Buchstaben, siehe _HAEUFIGE_WOERTER) oder wohlgeformte Struktur
    (Datum, Betrag, Uhrzeit, IBAN-Anfang, E-Mail)."""
    tokens = []
    for t in texte:
        kern = unicodedata.normalize("NFC", str(t)).strip(_RANDZEICHEN + " ")
        if kern:
            tokens.append(kern)
    treffer = lange = 0
    for kern in tokens:
        wort = len(kern) >= 3 and kern.lower() in _HAEUFIGE_WOERTER
        if wort or _STRUKTUR_TOKEN.fullmatch(kern):
            treffer += 1
            if (wort and len(kern) >= 5) or _LANGE_STRUKTUR.fullmatch(kern):
                lange += 1
    return {"quote": treffer / len(tokens) if tokens else 0.0, "treffer": treffer, "tokens": len(tokens),
            "lange_treffer": lange}


def lesung_plausibel(texte) -> bool:
    """Öffentlich: Ist eine OCR-Lesung (Liste von Wörtern/Texten) plausibel? Dieselbe Regel wie die
    Ausrichtungssuche (_plausibel(_lesung_bewerten(...))); die internen Namen bleiben für ältere Aufrufer
    (restrisiko) erhalten."""
    return _plausibel(_lesung_bewerten(texte))


def _plausibilitaet(texte) -> float:
    """Plausibilität einer Lesung auf der Skala 0..1 (Quote starker Wörter / PLAUSIBEL_SKALA, gekappt)."""
    return min(1.0, _lesung_bewerten(texte)["quote"] / PLAUSIBEL_SKALA)


def _kurz_plausibel(b) -> bool:
    """Kurze Lesung (<= KLEINE_SEITE_TOKENS Wörter) mit einem starken Wort. Für Proben auf langen Salatseiten
    (klein_erlaubt=False, siehe KLEINE_SEITE_SALAT) zählt nur ein langer Treffer (Wort ab 5 Buchstaben,
    Datum, Betrag, E-Mail): zufällige Treffer im Buchstabensalat sind kurz ("den", "Ein", "are")."""
    if b["tokens"] > KLEINE_SEITE_TOKENS:
        return False
    if b.get("klein_erlaubt", True):
        return b["treffer"] >= 1
    return b.get("lange_treffer", 0) >= 1


def _klar(b) -> bool:
    return _kurz_plausibel(b) or (b["treffer"] >= MIN_TREFFER and b["quote"] >= WORTQUOTE_KLAR)


def _plausibel(b) -> bool:
    return _kurz_plausibel(b) or (b["treffer"] >= MIN_TREFFER and b["quote"] >= WORTQUOTE_MIN)


def _naechster_winkel(bewertungen: dict):
    """Welche Ausrichtung als Nächstes gelesen werden muss; None = Suche beendet.
    0° zuerst; 180° immer, wenn 0° nicht klar plausibel ist; 90°/270° nur, wenn weder 0° noch 180°
    plausibel sind (dort Abbruch, sobald eine Drehung klar plausibel ist)."""
    if 0 not in bewertungen:
        return 0
    b0 = bewertungen[0]
    if _klar(b0) or b0["tokens"] < MIN_TOKENS_SUCHE:
        return None
    if 180 not in bewertungen:
        return 180
    if _klar(bewertungen[180]) or _plausibel(b0) or _plausibel(bewertungen[180]):
        return None
    for w in (90, 270):
        if w not in bewertungen:
            return w
        if _klar(bewertungen[w]):
            return None
    return None


def _ausrichtung_waehlen(bewertungen: dict) -> int:
    """Gelesene Ausrichtung mit der besten Lesung. Eine Drehung gewinnt nur, wenn sie für sich plausibel
    und deutlich besser als 0° ist – sonst bleibt 0° (aufrechte Code-/Zahlentabellen werden nicht gedreht)."""
    b0 = bewertungen.get(0, {"quote": 0.0, "treffer": 0, "tokens": 0})
    beste = 0
    for w in (180, 90, 270):
        b = bewertungen.get(w)
        if b is None or not _plausibel(b):
            continue
        if b["quote"] < DREHUNG_FAKTOR * b0["quote"] or b["quote"] < b0["quote"] + DREHUNG_VORSPRUNG:
            continue
        if beste == 0 or b["quote"] > bewertungen[beste]["quote"]:
            beste = w
    return beste


# ----------------------------------------------------------------------
# Bildanalyse vor der OCR: Schräglage, ungleichmäßiger Hintergrund (numpy; ohne numpy: keine Analyse)
# ----------------------------------------------------------------------
def _numpy():
    try:
        import numpy
        return numpy
    except Exception:      # numpy fehlt (kommt sonst mit PyMuPDF 2.x und spaCy): ohne Bildanalyse weiter
        return None


def _grauwerte(pix):
    """Pixmap -> 2D-Array uint8 (Graustufen)."""
    np = _numpy()
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n >= 3:
        return ((a[:, :, 0].astype(np.uint16) * 77 + a[:, :, 1].astype(np.uint16) * 150
                 + a[:, :, 2].astype(np.uint16) * 29) >> 8).astype(np.uint8)
    return a[:, :, 0].copy()


def schraeglage_schaetzen(grau) -> float:
    """Schräglage eines Graustufenbilds (2D-Array, Text dunkel) in Grad: der Winkel, unter dem das
    Projektionsprofil der dunklen Pixel am schärfsten ist (Textzeilen = Spitzen). Vorzeichen wie
    fitz.Matrix.prerotate: Rendern mit prerotate(-schraeg) richtet die Zeilen waagerecht aus.
    0.0, wenn zu wenig Text da ist oder numpy fehlt."""
    np = _numpy()
    if np is None or grau is None or grau.size == 0:
        return 0.0
    schwelle = min(160, int(np.percentile(grau, 50)) - 40)
    ys, xs = np.nonzero(grau < schwelle)
    if len(xs) < SCHRAEG_MIN_PIXEL:
        return 0.0
    if len(xs) > SCHRAEG_MAX_PIXEL:
        schritt = int(math.ceil(len(xs) / SCHRAEG_MAX_PIXEL))
        ys, xs = ys[::schritt], xs[::schritt]
    ys = ys.astype(np.float64)
    xs = xs.astype(np.float64) - grau.shape[1] / 2.0

    def schaerfe(grad):
        y = ys - xs * math.tan(math.radians(grad))
        profil = np.bincount((y - y.min()).astype(np.int64)).astype(np.float64)
        return float((profil * profil).sum())

    grob = max(np.arange(-SCHRAEG_MAX_GRAD, SCHRAEG_MAX_GRAD + 1e-9, 0.25), key=schaerfe)
    fein = max(np.arange(grob - 0.25, grob + 0.25 + 1e-9, 0.025), key=schaerfe)
    grad = float(round(fein, 3))
    return grad if abs(grad) >= SCHRAEG_MIN_GRAD else 0.0


def _hintergrund(grau, block: int):
    """Geschätzter Papierhintergrund (hellster Wert je Block, 3x3-Maximum, 3x3-Mittel) in Blockauflösung."""
    np = _numpy()
    h, w = grau.shape
    hb, wb = (h + block - 1) // block, (w + block - 1) // block
    rand = np.pad(grau, ((0, hb * block - h), (0, wb * block - w)), mode="edge")
    klein = rand.reshape(hb, block, wb, block).max(axis=(1, 3)).astype(np.float32)
    p = np.pad(klein, 1, mode="edge")
    m = np.max([p[dy:dy + hb, dx:dx + wb] for dy in range(3) for dx in range(3)], axis=0)
    p = np.pad(m, 1, mode="edge")
    return np.mean([p[dy:dy + hb, dx:dx + wb] for dy in range(3) for dx in range(3)], axis=0)


def hintergrund_ungleichmaessig(grau) -> bool:
    """Ist der Papierhintergrund ungleichmäßig (Schatten, Foto, dunkle Kopierränder)? grau: ~100 dpi."""
    np = _numpy()
    if np is None or grau is None or min(grau.shape) < 32:
        return False
    bg = _hintergrund(grau, max(4, HINTERGRUND_BLOCK * SCHRAEG_DPI // OCR_DPI))
    unten, oben = np.percentile(bg, [5, 95])
    return float(oben - unten) >= HINTERGRUND_SPANNE


def hintergrund_herausrechnen(grau, block: int = HINTERGRUND_BLOCK):
    """Graustufenbild durch den geschätzten Hintergrund teilen: Schatten und Papierton werden weiß,
    Schrift bleibt dunkel (vor der Binarisierung durch Tesseract)."""
    np = _numpy()
    h, w = grau.shape
    bg = _hintergrund(grau, block)
    voll = np.repeat(np.repeat(bg, block, axis=0), block, axis=1)[:h, :w]
    norm = grau.astype(np.float32) / np.maximum(voll, 1.0) * 255.0
    return np.clip(norm, 0, 255).astype(np.uint8)


def _bildanalyse(seite, clip, winkel: int) -> dict:
    """Schräglage (in Leserichtung `winkel`) und Hintergrund der Seite bzw. des Ausschnitts, aus einem
    Rendering mit SCHRAEG_DPI. Fehler oder fehlendes numpy: {"schraeg": 0.0, "hintergrund": False}."""
    ergebnis = {"schraeg": 0.0, "hintergrund": False, "tinte": None}
    if _numpy() is None:
        return ergebnis
    try:
        matrix = fitz.Matrix(SCHRAEG_DPI / 72.0, SCHRAEG_DPI / 72.0).prerotate(winkel)
        pix = seite.get_pixmap(matrix=matrix, clip=clip, colorspace=fitz.csGRAY, alpha=False)
        grau = _grauwerte(pix)
        ergebnis["schraeg"] = schraeglage_schaetzen(grau)
        ergebnis["hintergrund"] = hintergrund_ungleichmaessig(grau)
        np = _numpy()
        ergebnis["tinte"] = float((grau < min(160, int(np.percentile(grau, 50)) - 40)).mean())
    except Exception as e:
        _protokollieren(e)
    return ergebnis


# ----------------------------------------------------------------------
# OCR-Kern (läuft im Kindprozess ODER – nur wenn kein Pool startbar ist – im eigenen Prozess)
# ----------------------------------------------------------------------
_LINIEN_ZEICHEN = "|¦"           # senkrechte Tabellenlinien, die Tesseract als Zeichen liest
# Wörter aus höchstens zwei dieser Zeichen, die FREI in der Zeile stehen, sind Staub/Rauschen ("°", ".", ";",
# "'") – sie zerreißen sonst "Etikett: Wert" in Zellen ("Name:\t\t:\t\tHerr …"). Bedeutungstragende Zeichen
# bleiben immer: * (geboren), & § % € + # @ / und ein am Wort hängender Doppelpunkt ("Geburtsdatum :").
_RAUSCH_ZEICHEN = frozenset(".,:;'\"`´°^~-_–—·•()[]{}<>!?\\¸¨")
RAUSCH_ABSTAND = 0.6          # frei = Lücke zu beiden Nachbarn > 0,6 x Worthöhe


def _rauschen(text: str) -> bool:
    return 0 < len(text) <= 2 and all(c in _RAUSCH_ZEICHEN for c in text)


def _linien_trennen(text: str, x0: float, x1: float) -> list:
    """Ein OCR-Wort mit eingelesenen Tabellenlinien ("1|Wolkow,", "1.714,85|01.12.2039", "|") in seine Teile
    zerlegen: [(Text, x0, x1)] in Wortkoordinaten (anteilig nach Zeichen), Linienzeichen entfallen."""
    if not any(c in _LINIEN_ZEICHEN for c in text):
        return [(text, x0, x1)]
    breite = (x1 - x0) / max(len(text), 1)
    teile, start = [], 0
    for i, c in enumerate(text + "|"):
        if c in _LINIEN_ZEICHEN:
            if i > start:
                teile.append((text[start:i], x0 + start * breite, x0 + i * breite))
            start = i + 1
    return teile


ENTARTET_FAKTOR = 3.0         # Zeile, deren Wortkästen höher sind als 3 x Median der Seite …
ENTARTET_ZEICHEN = 4.0        # … und höher als 4 x ihre mittlere Zeichenbreite: entartete Zeilenmaße


def _entartete_zeilen_reparieren(woerter, pix, dpi):
    """Die in MuPDF eingebaute OCR schreibt einzelne Zeilen mit unsinniger Schriftgröße/Grundlinie ins OCR-PDF
    (gemessen: "Geburtsdatum …" mit 86 pt statt 14 pt, Kasten über die ganze Seitenhöhe), obwohl Tesseract die
    Wörter richtig gefunden hat; die waagerechte Lage stimmt. Geschwärzt würde dann ein seitenhoher Streifen.
    Reparatur: Im Bild (pix) wird im waagerechten Bereich der Zeile das Tintenband gesucht, das kein anderes
    Wort erklärt, und die Wörter werden dorthin gesetzt. woerter: Liste von Listen [x0, y0, x1, y1, text, b, l, w]
    in Koordinaten des OCR-PDFs (Punkte, Rendering-Richtung). Rückgabe: (repariert, nicht reparierbar)."""
    if len(woerter) < 3:
        return 0, 0
    hoehen = sorted(w[3] - w[1] for w in woerter)
    median = hoehen[len(hoehen) // 2]
    zeilen: dict = {}
    for w in woerter:
        zeilen.setdefault((w[5], w[6]), []).append(w)
    entartet = []
    for schluessel, ws in zeilen.items():
        h = max(w[3] - w[1] for w in ws)
        zeichen = sum(len(str(w[4])) for w in ws) or 1
        breite = sum(w[2] - w[0] for w in ws) / zeichen
        if h > ENTARTET_FAKTOR * median and h > ENTARTET_ZEICHEN * max(breite, 0.5):
            entartet.append(schluessel)
    if not entartet:
        return 0, 0
    np = _numpy()
    if np is None or pix is None:
        return 0, len(entartet)
    try:
        grau = _grauwerte(pix)
    except Exception as e:
        _protokollieren(e)
        return 0, len(entartet)
    s = dpi / 72.0                                         # Punkte -> Pixel
    tinte = grau < min(160, int(np.percentile(grau, 50)) - 60)
    erklaert = np.zeros_like(tinte)
    kaputt = {id(w) for k in entartet for w in zeilen[k]}
    for w in woerter:
        if id(w) in kaputt:
            continue
        x0, y0 = max(0, int(w[0] * s) - 2), max(0, int(w[1] * s) - 2)
        x1, y1 = min(tinte.shape[1], int(w[2] * s) + 3), min(tinte.shape[0], int(w[3] * s) + 3)
        if x1 > x0 and y1 > y0:
            erklaert[y0:y1, x0:x1] = True
    offen = tinte & ~erklaert
    med_px = max(2.0, median * s)
    repariert = nicht = 0
    for k in entartet:
        ws = zeilen[k]
        x0 = max(0, int(min(w[0] for w in ws) * s))
        x1 = min(offen.shape[1], int(max(w[2] for w in ws) * s) + 1)
        if x1 - x0 < 2:
            nicht += 1
            continue
        profil = offen[:, x0:x1].sum(axis=1)
        schwelle = max(2, int(0.01 * (x1 - x0)))
        zeilen_mit = np.nonzero(profil >= schwelle)[0]
        baender = []
        if len(zeilen_mit):
            anfang = vorige = int(zeilen_mit[0])
            for y in zeilen_mit[1:]:
                y = int(y)
                if y - vorige > 0.3 * med_px:
                    baender.append((anfang, vorige + 1))
                    anfang = y
                vorige = y
            baender.append((anfang, vorige + 1))
        kandidaten = [(int(profil[a:b].sum()), a, b) for a, b in baender if 0.4 * med_px <= b - a <= 4.0 * med_px]
        if not kandidaten:
            nicht += 1
            continue
        _, a, b = max(kandidaten)
        reihe0, reihe1 = max(0, a - int(med_px)), min(offen.shape[0], b + int(med_px))
        ws = sorted(ws, key=lambda w: w[0])
        for i, w in enumerate(ws):
            # Die linke Kante stimmt; die rechte ist mit der falschen Schriftgröße berechnet: bis zum nächsten
            # Wort (bzw. höchstens die dreifache Breite) die letzte Tintenspalte im Band suchen
            wx0 = max(0, int(w[0] * s))
            grenze = int(ws[i + 1][0] * s) - 1 if i + 1 < len(ws) else int((w[0] + 3 * (w[2] - w[0])) * s)
            grenze = min(offen.shape[1], max(grenze, wx0 + 1))
            band = tinte[a:b, wx0:grenze]
            spalten = np.nonzero(band.sum(axis=0) > 0)[0] if band.size else []
            wx1 = wx0 + int(spalten[-1]) + 1 if len(spalten) else min(offen.shape[1], int(w[2] * s) + 1)
            if i + 1 == len(ws) and len(spalten):
                # letztes Wort: an einer Lücke von mehr als einer Zeilenhöhe endet es
                luecken = np.diff(spalten)
                bruch = np.nonzero(luecken > med_px)[0]
                if len(bruch):
                    wx1 = wx0 + int(spalten[bruch[0]]) + 1
            fenster = offen[reihe0:reihe1, wx0:max(wx1, wx0 + 1)]
            reihen = np.nonzero(fenster.sum(axis=1) > 0)[0] if fenster.size else []
            if len(reihen):
                oben, unten = reihe0 + int(reihen[0]), reihe0 + int(reihen[-1]) + 1
            else:
                oben, unten = a, b
            w[1], w[3] = oben / s, unten / s
            w[2] = max(w[2], wx1 / s)
        repariert += 1
    return repariert, nicht


def _woerter_aus_ocr_pdf(ocr_bytes, dpi, pix_x, pix_y, matrix, pix=None, zaehler=None):
    """Wörter (8-Tupel wie get_text("words")) aus dem OCR-PDF, in Seitenkoordinaten umgerechnet.
    Reihenfolge und Block-/Zeilennummern sind die Lesefolge der OCR (Grundlage für woerter_zu_zeilen).
    Als "|" gelesene senkrechte Tabellenlinien entfallen; ein Wort, an dem eine Linie klebt, wird an ihr
    geteilt (die Teile sind Zellinhalte). Entartete Zeilenmaße werden mit dem Bild (pix) repariert
    (_entartete_zeilen_reparieren); zaehler (dict) erhält "entartet_repariert"/"entartet_offen"."""
    ocr_doc = fitz.open("pdf", ocr_bytes)
    try:
        ocr_seite = ocr_doc[0]
        zoom = fitz.Matrix(dpi / 72.0, dpi / 72.0)        # OCR-PDF (Punkte bei dpi) -> Pixel
        rueck = ~matrix                                    # Pixel -> Seitenkoordinaten
        roh = []
        for w in ocr_seite.get_text("words"):
            for text, tx0, tx1 in _linien_trennen(w[4], w[0], w[2]):
                roh.append([tx0, w[1], tx1, w[3], text, w[5], w[6], w[7]])
        repariert, offen = _entartete_zeilen_reparieren(roh, pix, dpi)
        if zaehler is not None:
            zaehler["entartet_repariert"] = zaehler.get("entartet_repariert", 0) + repariert
            zaehler["entartet_offen"] = zaehler.get("entartet_offen", 0) + offen
        ergebnis = []
        for w in roh:
            r = fitz.Rect(w[0], w[1], w[2], w[3]) * zoom
            r = fitz.Rect(r.x0 + pix_x, r.y0 + pix_y, r.x1 + pix_x, r.y1 + pix_y) * rueck
            r.normalize()
            ergebnis.append((r.x0, r.y0, r.x1, r.y1, w[4], w[5], w[6], w[7]))
        return ergebnis
    finally:
        ocr_doc.close()


def _ocr_durchlauf(seite, dpi, clip, winkel, sprache, tessdata, hintergrund=False, zaehler=None):
    """Rendert die Seite (oder den Ausschnitt) um `winkel` gedreht, lässt Tesseract laufen und
    liefert die Wörter in Seitenkoordinaten (Drehung herausgerechnet). hintergrund: ungleichmäßigen
    Papierhintergrund (Schatten) vorher herausrechnen. zaehler: siehe _woerter_aus_ocr_pdf."""
    matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0).prerotate(winkel)
    pix = None
    if hintergrund and _numpy() is not None:
        try:
            grau_pix = seite.get_pixmap(matrix=matrix, clip=clip, colorspace=fitz.csGRAY, alpha=False)
            grau = hintergrund_herausrechnen(_grauwerte(grau_pix), max(4, HINTERGRUND_BLOCK * dpi // OCR_DPI))
            np = _numpy()
            rgb = np.repeat(grau[:, :, None], 3, axis=2)
            pix = fitz.Pixmap(fitz.csRGB, grau.shape[1], grau.shape[0], rgb.tobytes(), False)
            pix.set_origin(grau_pix.x, grau_pix.y)
        except Exception as e:
            _protokollieren(e)
            pix = None
    if pix is None:
        # RGB ist Pflicht: mit Graustufen-Pixmaps liefert pdfocr_tobytes keine Wörter (MuPDF 1.28)
        pix = seite.get_pixmap(matrix=matrix, clip=clip, colorspace=fitz.csRGB, alpha=False)
    pix.set_dpi(dpi, dpi)
    ocr_bytes = pix.pdfocr_tobytes(compress=False, language=sprache, tessdata=tessdata)
    return _woerter_aus_ocr_pdf(ocr_bytes, dpi, pix.x, pix.y, matrix, pix, zaehler)


def _normwort(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold().strip(_RANDZEICHEN + " ")


def _ohne_textebene(woerter, seite, clip):
    """Entfernt OCR-Wörter, die GENAU ein sichtbares Wort der Textebene an derselben Stelle doppeln
    (Text über einem Hintergrundbild). Weicht die OCR-Lesung ab, bleibt sie erhalten – sie kann der
    richtig gelesene Bildinhalt sein, während die Textebene (z. B. eines Kopierers) sich verlesen hat."""
    try:
        textwoerter = [(fitz.Rect(w[:4]), _normwort(w[4])) for w in seite.get_text("words", clip=clip)]
    except Exception as e:
        _protokollieren(e)
        return woerter
    if not textwoerter:
        return woerter
    behalten = []
    for w in woerter:
        r = fitz.Rect(w[:4])
        flaeche = abs(r) or 1.0
        norm = _normwort(w[4])
        if any(t == norm and abs(r & tr) > 0.5 * flaeche for tr, t in textwoerter if r.intersects(tr)):
            continue
        behalten.append(w)
    return behalten


def _ocr_worker(pdf_pfad, seite_nr0, dpi, clip, sprache, tessdata, ausrichtung_pruefen=True,
                nur_bilder=False, winkel_fest=None):
    """Modulfunktion für den Kindprozess (muss per Import erreichbar sein – Start-Methode "spawn").

    Rückgabe: {"woerter": [(x0, y0, x1, y1, text, block, zeile, nr, winkel, schraeg), ...],
               "winkel": 0|90|180|270, "schraeg": Schräglage in Grad (Leserichtung), "hintergrund": bool
               (ungleichmäßiger Hintergrund herausgerechnet), "seitenaufteilung": PSM der vollen Lesung,
               "plausibel": 0..1, "wortquote": Anteil starker Wörter, "treffer", "tokens",
               "laeufe": Anzahl OCR-Durchläufe, "lesungen": [{winkel, dpi, quote, treffer, tokens, dauer}],
               "unplausibel": bool}. Koordinaten beziehen sich auf die Seite nach remove_rotation().
    Ablauf: 0° bei voller Auflösung; ist das klar plausibel, fertig (Normalfall, ein Lauf). Sonst
    Ausrichtungsproben bei PROBE_DPI (0°, 180°, ggf. 90°/270° nach _naechster_winkel) und – falls eine
    Drehung gewinnt – ein Lauf bei voller Auflösung in dieser Ausrichtung.
    Volle Lesungen laufen mit OCR_EINSTELLUNGEN (Seitenaufteilung PSM 3), Proben mit der Voreinstellung.
    Ab SCHRAEG_KORREKTUR_AB Schräglage wird für volle Lesungen gerade gerückt gerendert (Wortkästen in
    Seitenkoordinaten = Umriss des schrägen Worts); darunter findet Tesseract die schrägen Zeilen selbst.
    winkel_fest: Ausrichtung vorgeben (Kontroll-OCR der Ausgabe) statt sie zu suchen.
    Ausschnitte (clip) bekommen die Ausrichtungssuche erst ab AUSRICHTUNG_BILD_ANTEIL der Seitenfläche.
    """
    warnings.simplefilter("ignore")
    doc = fitz.open(pdf_pfad)
    try:
        seite = doc[seite_nr0]
        if seite.rotation:
            seite.remove_rotation()
        clip_rect = fitz.Rect(clip) if clip else None
        suchen = winkel_fest is None and ausrichtung_pruefen
        if suchen and clip_rect is not None:
            suchen = abs(clip_rect & seite.rect) >= AUSRICHTUNG_BILD_ANTEIL * abs(seite.rect)
        protokoll: list = []
        tessdata_voll = tessdata_mit_einstellungen(tessdata, sprache) or tessdata
        seitenaufteilung = {"psm": SEITENAUFTEILUNG if tessdata_voll != tessdata else 6}
        start_winkel = int(winkel_fest or 0) % 360
        analyse = _bildanalyse(seite, clip_rect, start_winkel)
        schraeg_je_lage = {start_winkel % 180: analyse["schraeg"]}

        def korrektur(winkel) -> float:
            """Schräglage, um die eine volle Lesung in Ausrichtung `winkel` gerade gerückt wird (0 = keine).
            Nur ganze Seiten: ein gedrehtes Rendering mit Ausschnitt umfasst den Umriss des gedrehten
            Ausschnitts und läse Text der Seite neben dem Bildbereich mit."""
            if clip_rect is not None:
                return 0.0
            lage = winkel % 180
            if lage not in schraeg_je_lage:      # 90°/270°: die Zeilen liefen in der ersten Analyse senkrecht
                schraeg_je_lage[lage] = _bildanalyse(seite, clip_rect, winkel)["schraeg"]
            s = float(schraeg_je_lage[lage] or 0.0)  # (180° ändert die Steigung der Zeilen nicht)
            return s if abs(s) >= SCHRAEG_KORREKTUR_AB else 0.0

        def lesen(winkel, aufloesung, probe=False, aufteilung=False):
            t0 = time.perf_counter()
            zaehler: dict = {}
            if probe and aufteilung and seitenaufteilung["psm"] != 6:
                korr = 0.0                          # Probe mit Seitenaufteilung (zweite Probenstufe)
                woerter = _ocr_durchlauf(seite, aufloesung, clip_rect, winkel, sprache, tessdata_voll, False, zaehler)
            elif probe or seitenaufteilung["psm"] == 6:
                korr = 0.0 if probe else korrektur(winkel)
                woerter = _ocr_durchlauf(seite, aufloesung, clip_rect, winkel - korr, sprache, tessdata,
                                         analyse["hintergrund"] and not probe, zaehler)
            else:
                korr = korrektur(winkel)
                try:
                    woerter = _ocr_durchlauf(seite, aufloesung, clip_rect, winkel - korr, sprache, tessdata_voll,
                                             analyse["hintergrund"], zaehler)
                except Exception as e:     # abgeleitete Sprachdatei unbrauchbar: Voreinstellung
                    _protokollieren(e)
                    seitenaufteilung["psm"] = 6
                    zaehler = {}
                    woerter = _ocr_durchlauf(seite, aufloesung, clip_rect, winkel - korr, sprache, tessdata,
                                             analyse["hintergrund"], zaehler)
            if not probe:
                seitenaufteilung["entartet"] = zaehler
                seitenaufteilung["korrektur"] = korr
            bewertung = _lesung_bewerten([w[4] for w in woerter])
            protokoll.append(dict(bewertung, winkel=winkel, dpi=aufloesung,
                                  dauer=round(time.perf_counter() - t0, 2)))
            return woerter, bewertung

        if not suchen:
            winkel = start_winkel
            woerter, bewertung = lesen(winkel, dpi)
            plausibel_gelesen = _plausibel(bewertung)
        else:
            woerter, bewertung = lesen(0, dpi)
            winkel = 0
            plausibel_gelesen = _plausibel(bewertung)
            viel_tinte = (analyse.get("tinte") or 0.0) >= TINTE_MIN
            if not _klar(bewertung) and (bewertung["tokens"] >= MIN_TOKENS_SUCHE or viel_tinte):
                probe_dpi = min(PROBE_DPI, dpi)
                seite_kurz = bewertung["tokens"] <= KLEINE_SEITE_SALAT
                proben: dict = {0: bewertung}
                if probe_dpi < dpi:
                    # 0° auch als Probe: Rauschen (Foto, Raster) verschwindet bei geringer Auflösung; ist die
                    # Probe für sich plausibel und besser, ist sie die Vergleichsbasis für alle Drehungen
                    probe0 = dict(lesen(0, probe_dpi, probe=True)[1], klein_erlaubt=seite_kurz)
                    if ((_plausibel(probe0) and probe0["quote"] > bewertung["quote"])
                            or bewertung["tokens"] < MIN_TOKENS_SUCHE <= probe0["tokens"]):
                        # (die Seitenaufteilung verwirft verdrehten Text und Kritzel oft fast ganz – dann ist
                        # die Probe die Vergleichsbasis, sonst würde 180° gar nicht erst geprüft)
                        proben[0] = probe0
                while True:
                    naechster = _naechster_winkel(proben)
                    if naechster is None:
                        break
                    proben[naechster] = dict(lesen(naechster, probe_dpi, probe=True)[1], klein_erlaubt=seite_kurz)
                null = (woerter, bewertung, plausibel_gelesen)        # volle 0°-Lesung
                winkel = _ausrichtung_waehlen(proben)
                plausibel_gelesen = _plausibel(proben[winkel]) or (winkel == 0 and plausibel_gelesen)

                def drehung_lesen(drehung):
                    """Volle Lesung in der gewählten Drehung – sie zählt nur, wenn sie selbst plausibel oder
                    deutlich besser als 0° ist (eine 100-dpi-Probe kann zufällig Wörter "treffen")."""
                    w_d, b_d = lesen(drehung, dpi)
                    if _plausibel(b_d) or b_d["quote"] >= null[1]["quote"] + DREHUNG_VORSPRUNG:
                        return w_d, b_d, _plausibel(b_d)
                    return None

                if winkel != 0:
                    gelesen = drehung_lesen(winkel)
                    if gelesen is None:
                        winkel = 0
                        woerter, bewertung, plausibel_gelesen = null
                    else:
                        woerter, bewertung = gelesen[0], gelesen[1]
                        plausibel_gelesen = plausibel_gelesen or gelesen[2]
                if (winkel == 0 and not plausibel_gelesen and probe_dpi < PROBE2_DPI <= dpi
                        and (bewertung["tokens"] >= MIN_TOKENS_WARNUNG or viel_tinte)):
                    # Zweite Stufe: Text ist da, aber keine Probe ergab eine plausible Lesung – kleine Schrift oder
                    # Tabelle. Proben mit Seitenaufteilung bei PROBE2_DPI, Vergleich mit der vollen 0°-Lesung
                    # (ebenfalls Seitenaufteilung); 180° zuerst, Abbruch bei klarer Lesung.
                    proben2: dict = {0: bewertung}
                    for drehung in (180, 90, 270):
                        proben2[drehung] = lesen(drehung, PROBE2_DPI, probe=True, aufteilung=True)[1]
                        if _klar(proben2[drehung]):
                            break
                    winkel2 = _ausrichtung_waehlen(proben2)
                    if winkel2 != 0:
                        gelesen = drehung_lesen(winkel2)
                        if gelesen is not None:
                            winkel = winkel2
                            woerter, bewertung = gelesen[0], gelesen[1]
                            plausibel_gelesen = _plausibel(proben2[winkel2]) or gelesen[2]
        schraeg = float(schraeg_je_lage.get(winkel % 180) or 0.0)
        korr = float(seitenaufteilung.get("korrektur") or 0.0)
        # 10-Tupel: Ausrichtung und die TATSÄCHLICH herausgedrehte Schräglage – nur dann sind die Wortkästen
        # gerade gerückt Zeilenbänder; ohne Korrektur trägt MuPDF jedem Wort das Band seiner ganzen schrägen
        # Zeile ein, und eine nachträgliche Drehung würde die Zeilen gegeneinander verschieben
        woerter = [tuple(w[:8]) + (winkel, korr) for w in woerter]
        if nur_bilder and clip_rect is not None:
            woerter = _ohne_textebene(woerter, seite, clip_rect)
        # Wortzahl aus ALLEN Lesungen: die Seitenaufteilung (PSM 3) verwirft Kritzel/Handschrift oft als
        # Nicht-Text – die Proben (PSM 6) zeigen dann, dass dort etwas steht, das nicht lesbar ist
        tokens_max = max([bewertung["tokens"]] + [lauf.get("tokens", 0) for lauf in protokoll])
        unplausibel = (winkel_fest is None and not plausibel_gelesen and tokens_max >= MIN_TOKENS_WARNUNG)
        entartet = seitenaufteilung.get("entartet") or {}
        return {"woerter": woerter, "winkel": winkel, "schraeg": schraeg, "korrektur": korr,
                "hintergrund": analyse["hintergrund"], "seitenaufteilung": seitenaufteilung["psm"],
                "zeilen_repariert": entartet.get("entartet_repariert", 0),
                "zeilen_unsicher": entartet.get("entartet_offen", 0),
                "plausibel": min(1.0, bewertung["quote"] / PLAUSIBEL_SKALA),
                "wortquote": round(bewertung["quote"], 4), "treffer": bewertung["treffer"],
                "tokens": bewertung["tokens"], "laeufe": len(protokoll), "lesungen": protokoll,
                "unplausibel": unplausibel}
    finally:
        doc.close()


def _ping_worker():
    """Selbsttest des Pools: liefert (PID, Start-Methode, ist Kindprozess)."""
    return (os.getpid(), multiprocessing.get_start_method(allow_none=True),
            multiprocessing.parent_process() is not None)


def _eltern_waechter():
    """Initialisierer jedes Arbeitsprozesses: beendet ihn, sobald der Elternprozess (die Oberfläche) nicht
    mehr lebt (Absturz, "Task beenden"). Sonst blieben verwaiste Tesseract-Prozesse mit je 100-180 MB
    zurück, weil die Auftragswarteschlange des Pools nie geschlossen wird (Gutachten GR-03/S-09).
    parent_process().join() wartet plattformübergreifend auf das Prozess-Handle bzw. die Pipe."""
    eltern = multiprocessing.parent_process()
    if eltern is None:
        return

    def warten():
        try:
            eltern.join()
        except Exception:
            while eltern.is_alive():
                time.sleep(1.0)
        os._exit(0)

    threading.Thread(target=warten, daemon=True, name="Eltern-Waechter").start()


def _pool_beenden(pool, hart=False):
    """Pool herunterfahren; hart: laufende Tesseract-Aufrufe sofort beenden (Abbruch, Zeitlimit, Ende)."""
    prozesse = list((getattr(pool, "_processes", None) or {}).values())
    try:
        pool.shutdown(wait=False, cancel_futures=True)
    except Exception:
        pass
    if hart:
        for prozess in prozesse:
            try:
                prozess.terminate()
            except Exception:
                pass


# Alle lebenden Dienste: beim Programmende werden ihre Arbeiter sofort beendet. concurrent.futures wartet
# sonst in seinem eigenen Beenden-Hook auf laufende Aufträge (bis zu einer ganzen Seite, im Fehlerfall bis
# zum Zeitlimit). threading._register_atexit läuft in umgekehrter Reihenfolge – unser Hook vor dem von
# concurrent.futures (oben importiert).
_DIENSTE: "weakref.WeakSet" = weakref.WeakSet()


def _beim_beenden():
    for dienst in list(_DIENSTE):
        try:
            dienst._pool_verwerfen(hart=True)
        except Exception:
            pass


try:
    threading._register_atexit(_beim_beenden)
except Exception:   # andere Python-Implementierung: gewöhnlicher atexit-Hook
    import atexit
    atexit.register(_beim_beenden)


# ----------------------------------------------------------------------
# Datei-Fingerabdruck (Cache-Schlüssel)
# ----------------------------------------------------------------------
_KOPF_BYTES = 1 << 20
_PROBEN = 32
_PROBE_BYTES = 64 << 10


def _datei_fingerabdruck(pdf_pfad) -> tuple:
    """Inhaltsbasierter Schlüssel (Größe + BLAKE2b): bis 4 MB über die ganze Datei, sonst über Anfang, Ende
    und 32 Stichproben. Ein Pfad allein genügt nicht – dieselbe Hilfsdatei der Schwärzung wird für mehrere
    Dokumente nacheinander benutzt, und FAT/Netzlaufwerke haben grobe Zeitstempel. Das Dateiende enthält
    bei jeder neu gespeicherten PDF eine neue /ID und neue xref-Offsets."""
    p = Path(pdf_pfad)
    try:
        groesse = p.stat().st_size
        h = hashlib.blake2b(digest_size=16)
        with open(p, "rb") as f:
            if groesse <= 4 * _KOPF_BYTES:
                h.update(f.read())
            else:
                h.update(f.read(_KOPF_BYTES))
                schritt = (groesse - 2 * _KOPF_BYTES) // (_PROBEN + 1)
                for i in range(1, _PROBEN + 1):
                    f.seek(_KOPF_BYTES + i * schritt)
                    h.update(f.read(_PROBE_BYTES))
                f.seek(groesse - _KOPF_BYTES)
                h.update(f.read(_KOPF_BYTES))
        return (groesse, h.hexdigest())
    except OSError:
        return (str(p), 0)


# ----------------------------------------------------------------------
# OcrDienst
# ----------------------------------------------------------------------
class _Auftrag:
    """Ein OCR-Auftrag im Pool (für vorab() und ergebnis())."""
    __slots__ = ("funktion", "args", "zukunft", "pool", "fehlschlaege", "start")

    def __init__(self, funktion, args):
        self.funktion = funktion
        self.args = args
        self.zukunft = None
        self.pool = None
        self.fehlschlaege = 0
        self.start = None


class OcrDienst:
    """OCR außerhalb des GUI-Threads: Prozess-Pool (Start-Methode "spawn" wie unter Windows), damit
    Tesseract den GIL der Oberfläche nicht blockiert und Abstürze von Tesseract/MuPDF die Oberfläche nicht
    mitreißen.

    * Ergebnisse werden je (Datei-Fingerabdruck, Seite, dpi, Ausschnitt, Winkel) zwischengespeichert.
    * vorab(): mehrere Seiten parallel einreihen (alle Arbeiter nutzen), spätere Aufrufe warten nur noch.
    * Jeder Arbeiter beendet sich, wenn der Elternprozess stirbt (keine verwaisten Prozesse).
    * Stürzt ein Arbeiter ab, wird der Pool neu aufgebaut und der Auftrag einzeln wiederholt; stürzt er
      erneut ab, gilt nur dieser Auftrag als gescheitert (Meldung OCR_FEHLER). NIE läuft die OCR danach im
      eigenen Prozess – derselbe Absturz würde die Oberfläche beenden (Gutachten KQ-05/S-10).
    * Nur wenn sich gar kein Pool starten lässt (eingeschränkte Umgebung), läuft die OCR im eigenen
      Prozess (Hinweis in self.hinweise).
    """

    def __init__(self, prozesse: int | None = None):
        kerne = os.cpu_count() or 2
        self.prozesse = max(1, prozesse if prozesse else min(3, kerne - 1))
        self._pool = None
        self._pool_fehler = None          # Grund, falls kein Pool startbar ist (dann OCR im eigenen Prozess)
        self._pool_lief = False           # mindestens ein Auftrag ist im Pool fertig geworden
        self._seriell = False             # nach einem Absturz: Aufträge einzeln (Verursacher isolieren)
        self._seriell_sperre = threading.Lock()
        self._lock = threading.RLock()
        self._abbruch = threading.Event()
        self._cache: dict = {}
        self._laufend: dict = {}          # Schlüssel -> _Auftrag (vorab eingereiht)
        self.tessdata = _tessdata_finden()
        self.sprache, self.sprach_warnung = _ocr_sprache(self.tessdata)
        self.in_prozess = False           # True, sobald die OCR ohne Pool im eigenen Prozess läuft
        self.hinweise: list[str] = []     # einmalige Hinweise (z. B. OCR im Hauptprozess)
        self.statistik = {"auftraege": 0, "abstuerze": 0, "laeufe": 0}
        _DIENSTE.add(self)

    # -- Pool-Verwaltung ------------------------------------------------
    def _pool_holen(self):
        """Liefert den Pool (legt ihn bei Bedarf an) oder None, wenn kein Pool startbar ist."""
        with self._lock:
            if self._pool is None and self._pool_fehler is None:
                try:
                    self._pool = concurrent.futures.ProcessPoolExecutor(
                        max_workers=self.prozesse, mp_context=multiprocessing.get_context("spawn"),
                        initializer=_eltern_waechter)
                except Exception as e:  # z. B. eingeschränkte Umgebung ohne Prozessstart
                    self._pool = None
                    self._pool_fehler = str(e) or type(e).__name__
            return self._pool

    def _fallback_melden(self, grund):
        if not self.in_prozess:
            self.in_prozess = True
            self.hinweise.append(f"OCR läuft im Hauptprozess ({grund}) – die Oberfläche kann "
                                 f"während der Texterkennung kurz einfrieren.")

    def _pool_verwerfen(self, pool=None, hart=False):
        """Verwirft den aktuellen Pool (oder nur `pool`, falls er noch der aktuelle ist)."""
        with self._lock:
            if pool is not None and pool is not self._pool:
                alt = None
            else:
                alt, self._pool = self._pool, None
        if alt is not None:
            _pool_beenden(alt, hart=hart)
        elif pool is not None and hart:
            _pool_beenden(pool, hart=True)

    def _pool_startbar(self) -> bool:
        """Prüft nach einem Absturz vor dem ersten erfolgreichen Auftrag, ob sich überhaupt ein Arbeiter
        starten lässt. Wenn nicht: _pool_fehler setzen (dann OCR im eigenen Prozess)."""
        pool = self._pool_holen()
        if pool is None:
            return False
        try:
            pool.submit(_ping_worker).result(timeout=120)
            self._pool_lief = True
            return True
        except Exception as e:
            self._pool_verwerfen(pool, hart=True)
            if self._abbruch.is_set():
                raise OcrAbgebrochen() from e
            with self._lock:
                self._pool_fehler = f"Arbeitsprozess startet nicht: {type(e).__name__} {e}".strip()
            return False

    def _einreichen(self, auftrag: _Auftrag) -> bool:
        """Reicht den Auftrag im Pool ein (ohne zu warten). False, wenn kein Pool verfügbar ist."""
        pool = self._pool_holen()
        if pool is None:
            return False
        auftrag.zukunft = pool.submit(auftrag.funktion, *auftrag.args)
        auftrag.pool = pool
        auftrag.start = None
        self.statistik["auftraege"] += 1
        return True

    def _warten(self, auftrag: _Auftrag):
        """Wartet auf das Ergebnis des Auftrags (reicht ihn bei Bedarf ein). Beachtet Abbruch und
        Zeitlimit; nach einem Absturz des Arbeiters wird der Pool neu aufgebaut und der Auftrag einzeln
        wiederholt (höchstens MAX_FEHLVERSUCHE Abstürze je Auftrag, dann RuntimeError)."""
        while True:
            if self._abbruch.is_set():
                raise OcrAbgebrochen()
            if self.in_prozess:
                return auftrag.funktion(*auftrag.args)
            seriell = self._seriell
            sperre = self._seriell_sperre if seriell else None
            if sperre is not None:
                sperre.acquire()
            try:
                if auftrag.zukunft is None:
                    try:
                        if not self._einreichen(auftrag):
                            self._fallback_melden("Prozess-Pool konnte nicht gestartet werden: "
                                                  + (self._pool_fehler or "unbekannt"))
                            return auftrag.funktion(*auftrag.args)
                    except Exception as e:   # Pool gerade im Abbau (abbrechen) oder kaputt
                        self._pool_verwerfen(auftrag.pool, hart=True)
                        if self._abbruch.is_set():
                            raise OcrAbgebrochen() from e
                        auftrag.zukunft = None
                        auftrag.fehlschlaege += 1
                        if auftrag.fehlschlaege >= MAX_FEHLVERSUCHE:
                            raise RuntimeError(f"OCR-Prozess nicht verfügbar ({e})") from e
                        continue
                if auftrag.start is None:
                    auftrag.start = time.monotonic()
                while True:
                    try:
                        ergebnis = auftrag.zukunft.result(timeout=0.25)
                        self._pool_lief = True
                        return ergebnis
                    except concurrent.futures.TimeoutError:
                        if self._abbruch.is_set():
                            auftrag.zukunft.cancel()
                            self._pool_verwerfen(hart=True)
                            raise OcrAbgebrochen()
                        if time.monotonic() - auftrag.start > OCR_ZEITLIMIT_S:
                            self._pool_verwerfen(auftrag.pool, hart=True)
                            raise RuntimeError(f"Zeitlimit von {OCR_ZEITLIMIT_S} s überschritten")
                    except concurrent.futures.CancelledError:
                        if self._abbruch.is_set():
                            raise OcrAbgebrochen()
                        auftrag.zukunft = None       # durch einen Pool-Neustart verdrängt: neu einreichen
                        break
                    except concurrent.futures.process.BrokenProcessPool as e:
                        self.statistik["abstuerze"] += 1
                        self._seriell = True
                        self._pool_verwerfen(auftrag.pool, hart=True)
                        if self._abbruch.is_set():
                            raise OcrAbgebrochen() from e
                        auftrag.zukunft = None
                        auftrag.fehlschlaege += 1
                        if not self._pool_lief and not self._pool_startbar():
                            self._fallback_melden("Prozess-Pool konnte nicht gestartet werden: "
                                                  + (self._pool_fehler or "unbekannt"))
                            return auftrag.funktion(*auftrag.args)
                        if auftrag.fehlschlaege >= MAX_FEHLVERSUCHE:
                            raise RuntimeError("OCR-Prozess wiederholt abgestürzt – Seite wird übersprungen") \
                                from e
                        break                        # Pool neu aufbauen, Auftrag einzeln wiederholen
            finally:
                if sperre is not None:
                    sperre.release()

    def _ausfuehren(self, funktion, *args):
        """Führt `funktion(*args)` im Pool aus und wartet auf das Ergebnis (siehe _warten)."""
        return self._warten(_Auftrag(funktion, args))

    def selbsttest(self):
        """Prüft den Pool: liefert (PID des Arbeiters, Start-Methode, ist Kindprozess) oder None."""
        try:
            return self._ausfuehren(_ping_worker)
        except Exception:
            return None

    # -- Schnittstelle ---------------------------------------------------
    @staticmethod
    def _datei_schluessel(pdf_pfad):
        return _datei_fingerabdruck(pdf_pfad)

    @staticmethod
    def _clip_tupel(clip):
        return tuple(round(float(v), 1) for v in fitz.Rect(clip)) if clip is not None else None

    def _schluessel(self, pdf_pfad, seite_nr0, dpi, clip, winkel):
        w = None if winkel is None else int(winkel) % 360
        return (self._datei_schluessel(pdf_pfad), int(seite_nr0), int(dpi), self._clip_tupel(clip), w)

    def _auftrag_fuer(self, pdf_pfad, seite_nr0, dpi, clip_tupel, winkel) -> _Auftrag:
        # _ocr_worker wird erst hier nachgeschlagen (Tests ersetzen ihn im Modul)
        return _Auftrag(_ocr_worker, (str(pdf_pfad), int(seite_nr0), int(dpi), clip_tupel, self.sprache,
                                      self.tessdata, True, clip_tupel is not None, winkel))

    def vorab(self, pdf_pfad, seiten, dpi: int = OCR_DPI, winkel=None) -> int:
        """Reiht OCR-Aufträge parallel im Pool ein (wartet nicht); spätere woerter()/ergebnis()/text()
        für dieselben Seiten warten nur noch auf das Ergebnis (Gutachten PERF-05).

        seiten: Seitenindizes (0-basiert) oder Paare (seite, clip) für Bildbereiche.
        winkel: None (Ausrichtung suchen), eine feste Ausrichtung oder {seite: winkel} (Kontroll-OCR).
        Rückgabe: Anzahl neu eingereihter Aufträge (0, wenn kein Pool läuft, nach einem Absturz oder
        Abbruch – dann liest ergebnis() wie gewohnt einzeln)."""
        if self.sprache is None or self._abbruch.is_set() or self.in_prozess or self._seriell:
            return 0
        neu = 0
        for eintrag in seiten:
            nr, clip = (eintrag if isinstance(eintrag, (tuple, list)) else (eintrag, None))
            w = winkel.get(nr) if isinstance(winkel, dict) else winkel
            schluessel = self._schluessel(pdf_pfad, nr, dpi, clip, w)
            with self._lock:
                if schluessel in self._cache or schluessel in self._laufend:
                    continue
                auftrag = self._auftrag_fuer(pdf_pfad, nr, dpi, schluessel[3], schluessel[4])
                try:
                    if not self._einreichen(auftrag):
                        return neu
                except Exception:
                    return neu
                self._laufend[schluessel] = auftrag
            neu += 1
        return neu

    def ergebnis(self, pdf_pfad, seite_nr0: int, dpi: int = OCR_DPI, clip=None, winkel=None) -> dict:
        """Vollständiges OCR-Ergebnis einer Seite:
        {"woerter": 8-Tupel in Lesefolge, "winkel": erkannte/vorgegebene Ausrichtung, "plausibel": 0..1,
         "wortquote", "laeufe", "unplausibel": bool, "warnung": Text oder None, "meldungen": [...]}.
        clip: nur dieser Bereich (Bilder auf Textseiten; Ausrichtungssuche erst ab 20 % der Seite).
        winkel: Ausrichtung vorgeben (Kontroll-OCR der Ausgabe, Gutachten S-08) statt sie zu suchen."""
        schluessel = self._schluessel(pdf_pfad, seite_nr0, dpi, clip, winkel)
        with self._lock:
            if schluessel in self._cache:
                return self._cache[schluessel]
        if self.sprache is None:
            return {"woerter": [], "winkel": 0, "plausibel": 0.0, "wortquote": 0.0, "laeufe": 0,
                    "unplausibel": False, "warnung": self.sprach_warnung,
                    "meldungen": [_meldung("warnung", "OCR_FEHLER", self.sprach_warnung, seite_nr0)]}
        with self._lock:
            auftrag = self._laufend.get(schluessel)
            if auftrag is None:
                auftrag = self._auftrag_fuer(pdf_pfad, seite_nr0, dpi, schluessel[3], schluessel[4])
                self._laufend[schluessel] = auftrag
        try:
            roh = self._warten(auftrag)
        except OcrAbgebrochen:
            return {"woerter": [], "winkel": 0, "plausibel": 0.0, "wortquote": 0.0, "laeufe": 0,
                    "unplausibel": False, "warnung": "Abgebrochen",
                    "meldungen": [_meldung("hinweis", "ABGEBROCHEN", "Abgebrochen", seite_nr0)]}
        except Exception as e:
            text = f"Seite {seite_nr0 + 1}: OCR fehlgeschlagen ({e}) – Seite nicht lesbar."
            ergebnis = {"woerter": [], "winkel": 0, "plausibel": 0.0, "wortquote": 0.0, "laeufe": 0,
                        "unplausibel": False, "warnung": text, "fehler": True,
                        "meldungen": [_meldung("warnung", "OCR_FEHLER", text, seite_nr0)]}
            with self._lock:
                self._cache[schluessel] = ergebnis    # dieselbe Seite nicht erneut abstürzen lassen
            return ergebnis
        finally:
            with self._lock:
                if self._laufend.get(schluessel) is auftrag:
                    del self._laufend[schluessel]
        ergebnis = self._ergebnis_aufbereiten(roh, seite_nr0, clip, winkel)
        with self._lock:
            self._cache[schluessel] = ergebnis
        return ergebnis

    def _ergebnis_aufbereiten(self, roh, seite_nr0, clip, winkel) -> dict:
        warnungen, meldungen = [], []
        if self.sprach_warnung:
            warnungen.append(self.sprach_warnung)
            meldungen.append(_meldung("warnung", "OCR_FEHLER", self.sprach_warnung, seite_nr0))
        gedreht = int(roh.get("winkel") or 0)
        if gedreht and winkel is None:
            ort = "Bildbereich auf Seite" if clip is not None else "Seite"
            text = f"{ort} {seite_nr0 + 1}: Scan lag um {gedreht}° gedreht – OCR mit korrigierter Ausrichtung."
            warnungen.append(text)
            meldungen.append(_meldung("hinweis", "OCR_GELESEN", text, seite_nr0))
        if "unplausibel" in roh:
            unplausibel = bool(roh["unplausibel"])
        else:   # Ergebnis im alten Format (ohne Flag)
            unplausibel = (roh.get("plausibel", 1.0) < PLAUSIBEL_WARNUNG and len(roh.get("woerter", [])) >= 5
                           and winkel is None)
        if unplausibel and winkel is None:
            if clip is None:
                text = (f"Seite {seite_nr0 + 1}: OCR-Text ist unplausibel (Seite verdreht, Handschrift oder "
                        f"unleserlich?) – dort kann NICHTS zuverlässig erkannt werden. Unbedingt manuell "
                        f"prüfen!")
                warnungen.append(text)
                meldungen.append(_meldung("warnung", "OCR_UNPLAUSIBEL", text, seite_nr0))
            else:
                text = (f"Seite {seite_nr0 + 1}: Text in einem Bildbereich ist unplausibel (Foto, Handschrift "
                        f"oder verdreht?) – Bildbereich bitte ansehen.")
                meldungen.append(_meldung("hinweis", "OCR_UNPLAUSIBEL", text, seite_nr0))
        self.statistik["laeufe"] += int(roh.get("laeufe", 1) or 1)
        if roh.get("zeilen_unsicher"):
            ort = "Bildbereich auf Seite" if clip is not None else "Seite"
            text = (f"{ort} {seite_nr0 + 1}: Lage von {roh['zeilen_unsicher']} OCR-Zeile(n) unsicher – dort wird "
                    f"großzügig geschwärzt, bitte prüfen.")
            warnungen.append(text)
            meldungen.append(_meldung("warnung", "OCR_UNPLAUSIBEL", text, seite_nr0))
        if roh.get("seitenaufteilung") == 6 and SEITENAUFTEILUNG != 6:
            hinweis = ("OCR-Einstellung für die Seitenaufteilung konnte nicht gesetzt werden – Scans werden mit "
                       "der Grundeinstellung gelesen (mehrspaltige Seiten und Tabellen schlechter).")
            if hinweis not in self.hinweise:
                self.hinweise.append(hinweis)
        return {"woerter": roh.get("woerter", []), "winkel": gedreht, "schraeg": float(roh.get("schraeg") or 0.0),
                "korrektur": float(roh.get("korrektur") or 0.0),
                "hintergrund": bool(roh.get("hintergrund")), "seitenaufteilung": roh.get("seitenaufteilung"),
                "plausibel": roh.get("plausibel", 0.0),
                "wortquote": roh.get("wortquote", 0.0), "laeufe": roh.get("laeufe", 1),
                "lesungen": roh.get("lesungen", {}), "unplausibel": bool(unplausibel and winkel is None),
                "warnung": " ".join(warnungen) if warnungen else None, "meldungen": meldungen}

    def woerter(self, pdf_pfad, seite_nr0: int, dpi: int = OCR_DPI, clip=None, winkel=None):
        """Wörter der OCR-Ebene einer Seite (nach remove_rotation; mit clip nur dieser Bereich).

        Rückgabe: (Liste von (x0, y0, x1, y1, text) in Lesefolge, Warnung oder None). Bei kopfstehenden
        oder seitlichen Scans wird die Ausrichtung erkannt und korrigiert (winkel=None); mit winkel wird
        diese Ausrichtung ohne Suche verwendet (Kontroll-OCR der Ausgabe).
        """
        ergebnis = self.ergebnis(pdf_pfad, seite_nr0, dpi, clip, winkel)
        return [tuple(w[:5]) for w in ergebnis["woerter"]], ergebnis["warnung"]

    def winkel(self, pdf_pfad, seite_nr0: int, dpi: int = OCR_DPI, clip=None) -> int:
        """Erkannte Ausrichtung (0/90/180/270) der Seite – OCR läuft, falls noch nicht geschehen."""
        return self.ergebnis(pdf_pfad, seite_nr0, dpi, clip)["winkel"]

    def winkel_falls_bekannt(self, pdf_pfad, seite_nr0: int, dpi: int = OCR_DPI, clip=None):
        """Ausrichtung aus dem Zwischenspeicher (startet KEINE OCR) oder None (Gutachten S-08)."""
        with self._lock:
            eintrag = self._cache.get(self._schluessel(pdf_pfad, seite_nr0, dpi, clip, None))
        if eintrag is None or eintrag.get("fehler"):
            return None
        return eintrag["winkel"]

    def text(self, pdf_pfad, seite_nr0: int, dpi: int = OCR_DPI, winkel=None, clip=None) -> str:
        """OCR-Text einer Seite (Kontroll-OCR), zeilenweise in Lesefolge. winkel: Ausrichtung des Originals
        übernehmen – die Ausgabe enthält zu wenige Wörter, um sie neu zu bestimmen (Gutachten S-08)."""
        ergebnis = self.ergebnis(pdf_pfad, seite_nr0, dpi, clip, winkel)
        return woerter_zu_text(ergebnis["woerter"], winkel=ergebnis["winkel"])

    def abbrechen(self):
        """Stoppt laufende und wartende OCR-Aufträge (Kindprozesse werden beendet)."""
        self._abbruch.set()
        self._pool_verwerfen(hart=True)
        with self._lock:
            self._laufend.clear()

    def zuruecksetzen(self):
        """Hebt einen Abbruch wieder auf (für einen neuen Lauf mit demselben Dienst); der Einzelmodus nach
        einem Absturz endet, ein nicht startbarer Pool wird erneut versucht (außer die OCR läuft schon
        dauerhaft im eigenen Prozess)."""
        self._abbruch.clear()
        with self._lock:
            self._pool_fehler = None
            self._seriell = False
            self._laufend.clear()

    def schliessen(self):
        """Beendet den Pool und leert den Zwischenspeicher."""
        self._pool_verwerfen(hart=True)
        with self._lock:
            self._cache.clear()
            self._laufend.clear()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.schliessen()
        return False


# ----------------------------------------------------------------------
# Zeilenbildung (Gutachten EQ-01) – von Seitenmodell, Analyse, Schwärzung und Kontrolle benutzt
# ----------------------------------------------------------------------
ZEILE_GLEICHE_HOEHE = 0.25    # Zeilenwechsel der OCR, aber gleiche Höhe (Mitte < 0,25 x Wortkasten): Tabellen-
                              # spalte derselben Zeile ("Vers.-Nr.:" | "4455/667788") – zusammenfassen
ZEILE_TOLERANZ = 0.40         # ohne OCR-Struktur: Mitte weicht um mehr als 0,4 x Zeilenabstand ab -> neue Zeile
ZEILE_UEBERLAPP_PT = 1.0      # so weit darf ein Wort links vom Ende des vorigen beginnen (kein Wagenrücklauf)


def _lesebox(w, winkel: int, schraeg: float = 0.0):
    """Wortkasten in Lesekoordinaten (Leserichtung = +x, Zeilen untereinander = +y); mit `schraeg` (Grad,
    Vorzeichen wie schraeglage_schaetzen) zusätzlich gerade gerückt: Mittelpunkt um -schraeg gedreht, Breite
    und Höhe aus dem achsenparallelen Kasten des schrägen Worts zurückgerechnet."""
    x0, y0, x1, y1 = (float(v) for v in w[:4])
    if winkel == 180:
        box = (-x1, -y1, -x0, -y0)
    elif winkel == 90:        # Seite * Matrix(90): (x, y) -> (-y, x)
        box = (-y1, x0, -y0, x1)
    elif winkel == 270:       # Seite * Matrix(270): (x, y) -> (y, -x)
        box = (y0, -x1, y1, -x0)
    else:
        box = (x0, y0, x1, y1)
    if not schraeg:
        return box
    c, s = math.cos(math.radians(schraeg)), math.sin(math.radians(schraeg))
    mx, my = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    gx, gy = mx * c + my * s, -mx * s + my * c        # wie Matrix.prerotate(-schraeg)
    b, h = box[2] - box[0], box[3] - box[1]
    d = c * c - s * s
    b2, h2 = (b * c - h * abs(s)) / d, (h * c - b * abs(s)) / d
    if b2 <= 0.2 * b or h2 <= 0.2 * h:              # sehr flache/schmale Kästen: Größe beibehalten
        b2, h2 = b, h
    return (gx - b2 / 2, gy - h2 / 2, gx + b2 / 2, gy + h2 / 2)


def _wort_ausrichtung(woerter):
    """(winkel, schraeg) aus 10-Tupeln (ergebnis()["woerter"]), sonst (None, 0.0)."""
    for w in woerter:
        if len(w) >= 10:
            try:
                return int(w[8]) % 360, float(w[9] or 0.0)
            except (TypeError, ValueError):
                break
    return None, 0.0


def lesekasten(w, winkel: int = 0, schraeg: float = 0.0):
    """Öffentlich: Wortkasten eines OCR-Worts in gerade gerückten Lesekoordinaten (für Zeilenbildung und
    Spaltenlücken im Seitenmodell). Rückgabe (x0, y0, x1, y1)."""
    return _lesebox(w, int(winkel or 0) % 360, float(schraeg or 0.0))


def ausrichtung_der_woerter(woerter) -> tuple:
    """(winkel, schraeg) einer Wortliste: aus den 10-Tupeln von ergebnis(), sonst Leserichtung aus der
    Lesefolge geschätzt und Schräglage 0 – dieselbe Annahme, die woerter_zu_zeilen trifft."""
    woerter = [w for w in (woerter or []) if len(w) >= 5 and str(w[4]).strip()]
    if not woerter:
        return 0, 0.0
    winkel, schraeg = _wort_ausrichtung(woerter)
    if winkel is None:
        winkel = _leserichtung_schaetzen(woerter)
    return int(winkel) % 360, float(schraeg or 0.0)


def _leserichtung_schaetzen(woerter) -> int:
    """Ausrichtung aus der Lesefolge der OCR schätzen (aufeinanderfolgende Wörter derselben Zeile laufen
    in Leserichtung): 0, 90, 180 oder 270. Ohne Anhaltspunkte 0."""
    stimmen = {0: 0, 90: 0, 180: 0, 270: 0}
    hat_struktur = len(woerter[0]) >= 8
    for a, b in zip(woerter, woerter[1:]):
        if hat_struktur and (a[5], a[6]) != (b[5], b[6]):
            continue
        dx = (b[0] + b[2]) / 2 - (a[0] + a[2]) / 2
        dy = (b[1] + b[3]) / 2 - (a[1] + a[3]) / 2
        if abs(dx) < 0.5 and abs(dy) < 0.5:
            continue
        if abs(dx) >= abs(dy):
            stimmen[0 if dx > 0 else 180] += 1
        else:
            stimmen[90 if dy < 0 else 270] += 1
    beste = max(stimmen, key=stimmen.get)
    return beste if stimmen[beste] > 0 else 0


def woerter_zu_zeilen(woerter, winkel=None, schraeg=None) -> list:
    """Gruppiert OCR-Wörter zu Zeilen in Lesereihenfolge (Gutachten EQ-01).

    woerter: 5-, 8- oder 10-Tupel in Seitenkoordinaten, in der Reihenfolge, in der die OCR sie liefert
    (OcrDienst.woerter()/ergebnis(), ocr_cache der Analyse). winkel: erkannte Ausrichtung des Scans
    (OcrDienst.ergebnis()["winkel"]); None = aus den 10-Tupeln bzw. aus der Lesefolge schätzen.
    schraeg: Schräglage in Grad (None = aus den 10-Tupeln, sonst 0): die Zeilen werden in gerade gerückten
    Koordinaten gebildet – auch lange Tabellenzeilen eines schrägen Scans bleiben EINE Zeile.
    Regeln (in Lesekoordinaten, also auch für gedrehte Scans):
      * Grundlage ist die Lesefolge der OCR, nicht die y-Lage: OCR-Wortkästen sind oft höher als der
        Zeilenabstand, eine Sortierung nach y verzahnt sonst Nachbarzeilen (IBAN, Telefon zerrissen).
      * Neue Zeile beim Wagenrücklauf (das Wort beginnt links vom Ende des vorigen) oder wenn es nicht auf
        gleicher Höhe liegt; bei 8-Tupeln zusätzlich beim Zeilen-/Blockwechsel der OCR – außer das Wort
        setzt die Zeile auf gleicher Höhe nach rechts fort (Tabellenspalte: "Vers.-Nr.:" "4455/667788").
      * Schräg gescannte Zeilen bleiben zusammen, weil nur benachbarte Wörter verglichen werden.
      * Kommen 5-Tupel erkennbar NICHT in Lesefolge (eine Zeile liegt über der vorigen in derselben
        Spalte), wird geometrisch gruppiert: Toleranz aus dem Zeilenabstand, echte Zeilenmitte.
    Rückgabe: Liste von Zeilen, jede eine Liste der ursprünglichen Wort-Tupel in Leserichtung.
    """
    woerter = [w for w in (woerter or []) if len(w) >= 5 and str(w[4]).strip()]
    if not woerter:
        return []
    eigen_winkel, eigen_schraeg = _wort_ausrichtung(woerter)
    if winkel is None:
        winkel = eigen_winkel
    if schraeg is None:
        schraeg = eigen_schraeg
    schraeg = float(schraeg or 0.0)
    winkel_vorgegeben = winkel is not None
    if winkel is None:
        winkel = _leserichtung_schaetzen(woerter)
    winkel = int(winkel) % 360
    zeilen = _zeilen_aus_lesefolge(woerter, winkel, schraeg)
    if zeilen is None:                   # keine Lesefolge: geometrisch, Ausrichtung vorgegeben oder aufrecht
        w = winkel if winkel_vorgegeben else 0
        boxen = [_lesebox(x, w, schraeg) for x in woerter]
        hoehen = sorted(max(b[3] - b[1], 0.5) for b in boxen)
        return _zeilen_geometrisch(woerter, boxen, hoehen[len(hoehen) // 2])
    zeilen = _rauschen_entfernen(zeilen, winkel, schraeg)
    return _zeilen_zusammenfuehren(zeilen, winkel, schraeg)


def _rauschen_entfernen(zeilen: list, winkel: int, schraeg: float) -> list:
    """Frei stehende Staubzeichen (siehe _rauschen) aus den Zeilen nehmen; leere Zeilen entfallen."""
    aus = []
    for zeile in zeilen:
        if not any(_rauschen(str(w[4])) for w in zeile):
            aus.append(zeile)
            continue
        boxen = [_lesebox(w, winkel, schraeg) for w in zeile]
        hoehen = sorted(max(b[3] - b[1], 0.5) for b in boxen)
        h = hoehen[len(hoehen) // 2]
        neu = []
        for i, w in enumerate(zeile):
            if _rauschen(str(w[4])):
                links = boxen[i][0] - boxen[i - 1][2] if i else None
                rechts = boxen[i + 1][0] - boxen[i][2] if i + 1 < len(zeile) else None
                frei = [x for x in (links, rechts) if x is not None]
                if all(x > RAUSCH_ABSTAND * h for x in frei):
                    continue
            neu.append(w)
        if neu:
            aus.append(neu)
    return aus


ZUSAMMEN_LUECKE = 12.0        # Zeilen derselben Höhe bis 12 x Worthöhe Abstand gehören zu einer Zeile …


def _ist_etikett(zeile) -> bool:
    """… wenn die linke ein Etikett ist: endet auf ":" (auch als eigenes Wort "Name :")."""
    return str(zeile[-1][4]).rstrip().endswith(":")


def _zeilen_zusammenfuehren(zeilen: list, winkel: int, schraeg: float) -> list:
    """Die Seitenaufteilung (PSM 3) liest Formulare spaltenweise: alle Etiketten eines Abschnitts, dann alle
    Werte ("Anschrift:" | "Dr.-Martin-Luther-Ring 74 b …"). Textseiten halten Etikett und Wert auf einer Zeile
    (Spaltentrenner dazwischen) – eine Etikett-Zeile (endet auf ":") wird deshalb mit der Zeile derselben Höhe
    rechts daneben vereinigt, wenn die Lücke höchstens ZUSAMMEN_LUECKE Worthöhen beträgt. Andere Spalten
    (Fußzeilen-Blöcke, Briefkopf, Fließtext) bleiben getrennt wie auf Textseiten: dort laufen Namen über das
    Zeilenende in die nächste Zeile DERSELBEN Spalte ("Vorstand: Horst / Biedermann"). Reihenfolge: die
    vereinigte Zeile steht an der frühesten Stelle ihrer Teile."""
    if len(zeilen) < 2:
        return zeilen
    infos = []
    for zeile in zeilen:
        boxen = [_lesebox(w, winkel, schraeg) for w in zeile]
        hoehen = sorted(max(b[3] - b[1], 0.5) for b in boxen)
        infos.append({"x0": min(b[0] for b in boxen), "x1": max(b[2] for b in boxen),
                      "m": sum((b[1] + b[3]) / 2 for b in boxen) / len(boxen),
                      "h": hoehen[len(hoehen) // 2], "n": len(zeile), "etikett": _ist_etikett(zeile)})
    # 1) je Zeile der nächste passende rechte Nachbar
    rechts: dict = {}
    for i, a in enumerate(infos):
        beste = None
        for j, b in enumerate(infos):
            if j == i:
                continue
            luecke = b["x0"] - a["x1"]
            h = max(a["h"], b["h"])
            if luecke < -1.0 or luecke > ZUSAMMEN_LUECKE * h:
                continue
            if not (0.6 <= a["h"] / b["h"] <= 1.67) or abs(a["m"] - b["m"]) > 0.35 * min(a["h"], b["h"]):
                continue
            if not a["etikett"]:
                continue
            if beste is None or luecke < beste[0]:
                beste = (luecke, j)
        if beste is not None:
            rechts[i] = beste
    # 2) jede Zeile ist höchstens EINES linken Nachbar (der nächste gewinnt)
    links: dict = {}
    for i, (luecke, j) in rechts.items():
        if j not in links or luecke < links[j][0]:
            links[j] = (luecke, i)
    folge = {i: j for j, (_, i) in links.items()}
    # 3) Ketten von links nach rechts; jede Kette steht an der frühesten Stelle ihrer Teile (Lesefolge)
    ketten = []
    for start in range(len(zeilen)):
        if start in links:
            continue
        kette, i, gesehen = [start], start, {start}
        while i in folge and folge[i] not in gesehen:
            i = folge[i]
            gesehen.add(i)
            kette.append(i)
        ketten.append(kette)
    erfasst = {i for k in ketten for i in k}
    ketten += [[i] for i in range(len(zeilen)) if i not in erfasst]     # Ringe (sollten nicht vorkommen)
    ketten.sort(key=min)
    return [[w for i in kette for w in zeilen[i]] for kette in ketten]


def _zeilen_aus_lesefolge(woerter, winkel, schraeg=0.0):
    """Zeilen aus der Lesefolge der OCR (siehe woerter_zu_zeilen); None, wenn 5-Tupel erkennbar nicht in
    Lesefolge kamen."""
    boxen = [_lesebox(w, winkel, schraeg) for w in woerter]
    hat_struktur = all(len(w) >= 8 for w in woerter)
    hoehen = sorted(max(b[3] - b[1], 0.5) for b in boxen)
    median_hoehe = hoehen[len(hoehen) // 2]

    # Zeilenabstand aus eindeutigen Zeilenwechseln (Wagenrücklauf) schätzen
    abstaende = []
    for i in range(1, len(boxen)):
        a, b = boxen[i - 1], boxen[i]
        if b[0] < a[2] - ZEILE_UEBERLAPP_PT:
            d = (b[1] + b[3]) / 2 - (a[1] + a[3]) / 2
            if d > 0.5:
                abstaende.append(d)
    abstaende.sort()
    zeilenabstand = abstaende[len(abstaende) // 2] if abstaende else None

    def gleiche_hoehe(a, b, streng) -> bool:
        ha, hb = a[3] - a[1], b[3] - b[1]
        d = abs((a[1] + a[3]) / 2 - (b[1] + b[3]) / 2)
        if streng:
            return d <= ZEILE_GLEICHE_HOEHE * max(min(ha, hb), 0.5)
        grenze = 0.5 * max(min(ha, hb), 0.5)
        if zeilenabstand:
            grenze = min(grenze, ZEILE_TOLERANZ * zeilenabstand)
        return d <= max(grenze, 1.0)

    zeilen, aktuell, letzte = [], [], None
    for i, (w, b) in enumerate(zip(woerter, boxen)):
        if letzte is None:
            aktuell = [i]
            letzte = (i, b)
            continue
        vorher = woerter[letzte[0]]
        a = letzte[1]
        rechts = b[0] >= a[2] - ZEILE_UEBERLAPP_PT or b[0] >= (a[0] + a[2]) / 2
        if hat_struktur and (w[5], w[6]) != (vorher[5], vorher[6]):
            weiter = rechts and gleiche_hoehe(a, b, streng=True)
        else:
            weiter = rechts and gleiche_hoehe(a, b, streng=False)
        if weiter:
            aktuell.append(i)
        else:
            zeilen.append(aktuell)
            aktuell = [i]
        letzte = (i, b)
    if aktuell:
        zeilen.append(aktuell)
    if not hat_struktur and _unordnung(zeilen, boxen, median_hoehe):
        return None
    return [[woerter[i] for i in zeile] for zeile in zeilen]


def _unordnung(zeilen, boxen, median_hoehe) -> bool:
    """True, wenn die Wörter offenbar NICHT in Lesefolge kamen: eine Zeile liegt über der vorigen in
    derselben Spalte (waagerechte Überlappung). Spaltenwechsel (nach oben UND daneben) sind erlaubt."""
    def umriss(zeile):
        return (min(boxen[i][0] for i in zeile), min(boxen[i][1] for i in zeile),
                max(boxen[i][2] for i in zeile), max(boxen[i][3] for i in zeile))
    vorige = None
    for zeile in zeilen:
        u = umriss(zeile)
        if vorige is not None:
            ueberlappt = min(u[2], vorige[2]) - max(u[0], vorige[0]) > 0
            hoeher = (u[1] + u[3]) / 2 < (vorige[1] + vorige[3]) / 2 - 0.5 * median_hoehe
            if ueberlappt and hoeher:
                return True
        vorige = u
    return False


def _zeilen_geometrisch(woerter, boxen, median_hoehe) -> list:
    """Rückfall für Wörter ohne Lesefolge: nach der Höhe sortieren und zu Zeilen fassen. Die Toleranz richtet
    sich nach dem Zeilenabstand der Seite (Median der Abstände verschiedener Wortmitten), nicht nach der
    Worthöhe, und die Zeilenmitte ist ein echter Mittelwert (kein Wandern) – Gutachten EQ-01."""
    mitten = sorted({round((b[1] + b[3]) / 2, 1) for b in boxen})
    abstaende = sorted(y - x for x, y in zip(mitten, mitten[1:]) if y - x > 1.5)
    toleranz = 0.5 * median_hoehe
    if abstaende:
        toleranz = min(toleranz, 0.45 * abstaende[len(abstaende) // 2])
    toleranz = max(toleranz, 1.5)
    reihenfolge = sorted(range(len(woerter)), key=lambda i: ((boxen[i][1] + boxen[i][3]) / 2, boxen[i][0]))
    zeilen, aktuell, summe = [], [], 0.0
    for i in reihenfolge:
        m = (boxen[i][1] + boxen[i][3]) / 2
        if aktuell and abs(m - summe / len(aktuell)) > toleranz:
            zeilen.append(aktuell)
            aktuell, summe = [], 0.0
        aktuell.append(i)
        summe += m
    if aktuell:
        zeilen.append(aktuell)
    return [[woerter[i] for i in sorted(zeile, key=lambda i: boxen[i][0])] for zeile in zeilen]


def woerter_zu_text(woerter, winkel=None) -> str:
    """Setzt Wörter (5- oder 8-Tupel) zu Text zusammen: Zeilen (woerter_zu_zeilen) durch Umbruch,
    Wörter durch Leerzeichen."""
    return "\n".join(" ".join(str(w[4]) for w in zeile) for zeile in woerter_zu_zeilen(woerter, winkel))


# ----------------------------------------------------------------------
# Kompatibilität (alte Aufrufer): OCR-Textpage im eigenen Prozess
# ----------------------------------------------------------------------
def ocr_textpage(seite, melde=None):
    """Erzeugt per OCR eine durchsuchbare Textebene für eine Scan-Seite (im eigenen Prozess).
    Rückgabe: (textpage oder None, Warnung oder None). Dreht /Rotate-Seiten vorher gerade."""
    tessdata = _tessdata_finden()
    sprache, warnung = _ocr_sprache(tessdata)
    if sprache is None:
        return None, warnung
    try:
        if seite.rotation:
            seite.remove_rotation()
        tp = seite.get_textpage_ocr(language=sprache, dpi=300, full=True, tessdata=tessdata)
        return tp, warnung
    except Exception as e:
        return None, f"OCR fehlgeschlagen: {e}"
