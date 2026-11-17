"""Langlauf (Runde 3b): Eine lange Sitzung – wie auf dem Windows-Laptop eines Maklers, der den ganzen Tag Schreiben
anonymisiert – darf weder Datei-Handles noch Speicher, Temp-Dateien oder Arbeitsprozesse anhäufen.

Die Sitzung verarbeitet 200 kleine, erzeugte PDFs nacheinander in EINEM Prozess über denselben Engine-Weg wie die
Oberfläche (gui.py) – mit den echten Funktionen, keine Attrappen:

  Hinzufügen    wie AnonymisiererApp._pdfs_hinzufuegen: dateien.sammle_pdfs_bericht (Inhalt statt Endung),
                geschützte PDFs über pdf_kennwort_noetig, arbeitskopie_ziel und pdf_entschluesseln als Arbeitskopie
                ohne Kennwort im Sitzungsordner
  Analysieren   wie _analyse_lauf, im eigenen Thread „Analyse“: je Lauf ein OcrDienst und ein LaufWissen,
                _seitenzahl, datei_art/fuer_engine_erlaubt, analysiere_pdf (Schutzstufe „hoch“, Kategorien der
                Stufe), _analyse_ergebnis_pruefen, weitergabe_anwenden; am Ende den OCR-Dienst schließen
  Schwärzen     wie _schwaerz_lauf, im Thread „Schwaerzung“: Funde wie _auftrag (angehakte mit ihren Stellen,
                abgewählte nur als Bildfund), je Lauf ein OcrDienst, zwischendateien_aufraeumen, schwaerze_pdf mit
                Freigabe-Pflicht (Standard) in einen gemeinsamen Zielordner, _schwaerz_ergebnis_pruefen,
                _reste_verorten, _ausgabe_status
  Liste leeren  wie _datei_vergessen: Ergebnis vergessen, dann arbeitskopie_entfernen
  Beenden       wie _aufraeumen: sitzung_aufraeumen(endgueltig=True)

Der Makler arbeitet in Stapeln zu 10 Dateien (Hinzufügen, Analysieren, Schwärzen, Liste leeren): 20 Stapel,
40 Läufe. Dateimix: Briefe mit Name, Anschrift, IBAN, Geburtsdatum, Telefon, E-Mail und Versicherungsschein-Nr. –
jede Datei eine andere Person; jede 25. Datei mit Bildbereich (Rasterbild mit Text: die Analyse liest ihn per OCR,
die Schwärzung prüft ihn mit der Kontroll-OCR – in 16 Läufen startet und endet ein OCR-Pool mit Arbeitsprozess);
jede 40. Datei kennwortgeschützt (AES-256).

Geprüft nach einer Aufwärmphase von 20 Dateien (Sprachmodell geladen, erster OCR-Pool samt dem Ressourcen-Wächter
von multiprocessing, erste Arbeitskopie):
1. Handles (Linux: Einträge in /proc/self/fd; Windows: Handles des Prozesses, psutil oder GetProcessHandleCount):
   an jedem Ruhepunkt (Lauf beendet, OCR-Dienst geschlossen, Arbeitsprozesse beendet) höchstens HANDLES_RUHE über
   der Grundlinie und nicht mehr Threads als vor der Sitzung; nach jeder Datei höchstens HANDLES_LAUF darüber – das
   deckt einen gerade laufenden OCR-Pool (Pipes der Warteschlangen, je Arbeitsprozess ein Handle).
2. Speicher: Der residente Speicher wächst von Datei 50 bis 200 um höchstens SPEICHER_SCHRANKE_MB (eigener Test:
   nur er wird übersprungen, wo weder psutil noch /proc/self/statm ihn messen).
3. Temp-Dateien: Nach jeder Datei liegen im Ordner für Arbeitskopien genau die Kopien der Kennwort-PDFs des
   laufenden Stapels, nach „Liste leeren“ keine mehr, nach dem Beenden nicht einmal mehr der Sitzungsordner; das
   System-Temp (für die Sitzung umgeleitet, auch für die Arbeitsprozesse) bleibt nach der Aufwärmphase unverändert.
   Im Zielordner liegt nach Datei k genau anonym_01 … anonym_k (keine Zwischendatei .anonym_tmp_*), daneben nur die
   Zuordnungsdatei mit 200 Zeilen; der Eingangsordner bleibt unverändert, es entsteht keine fehler.log.
4. Prozesse: Nach jedem Lauf leben keine OCR-Arbeitsprozesse mehr, am Ende keine neuen Kindprozesse – außer dem
   einen Ressourcen-Wächter von multiprocessing (POSIX: ein Prozess je Programm, kein OCR-Arbeiter; er endet mit dem
   Programm). Dass Arbeitsprozesse wirklich liefen, wird mitgeprüft (sonst prüfte der Punkt nichts).

Gegenprobe mit eingebauten Lecks (Runde 3b, Linux; je ein Lauf mit einer Ersetzung per monkeypatch, danach wieder
entfernt) – alle rot: jede mit pymupdf.open geöffnete Datei bleibt zusätzlich offen -> nach Datei 21 (342 statt
höchstens 299 + 16 Deskriptoren); jeder OCR-Dienst öffnet eine Datei und schließt sie nie (ein Handle je Lauf) ->
Ruhepunkt nach Stapel 5 (22 statt höchstens 17 + 4); jedes Analyse-Ergebnis samt Seitenmodell bleibt im Speicher ->
+50 bis 52 MB von Datei 50 bis 200; Arbeitskopien werden nicht gelöscht -> „Liste leeren“ in Stapel 2
(brief_017.pdf bleibt); jede Schwärzung lässt eine Zwischendatei liegen -> nach Datei 1; der OCR-Dienst bleibt
erreichbar und wird nie geschlossen -> erster Ruhepunkt (Arbeitsprozess lebt); jeder OCR-Dienst startet einen
Thread, der nie endet -> erster Ruhepunkt. Zu Recht grün blieben zwei Ersetzungen, die kein Leck sind: _aufraeumen
lässt .anonym_tmp_* stehen (die einzige Zwischendatei dieser Briefe wird per os.replace zur Ausgabe – es bleibt
nichts zu löschen), und ein vergessenes schliessen() allein (ist der Dienst nach dem Lauf unerreichbar, beendet die
Speicherbereinigung den Pool über den Rückruf von ProcessPoolExecutor).
"""

import gc
import multiprocessing
import os
import re
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen kennen nur den Namen "fitz"
    import fitz

try:
    import psutil
except ImportError:  # PyMuPDF 2.x bringt psutil mit; mit älteren Fassungen gelten die Rückfälle unten
    psutil = None

from anonymisierer import dateien, gui

WINDOWS = sys.platform == "win32"
ANZAHL = 200                   # Dateien der Sitzung (brief_001.pdf … brief_200.pdf)
STAPEL = 10                    # Dateien je Lauf: Hinzufügen, Analysieren, Schwärzen, Liste leeren
AUFWAERMEN = 20                # Grundlinie (Handles, System-Temp) nach so vielen Dateien
SPEICHER_VON = 50              # Speicherzuwachs ab Datei 50 …
BILD_ALLE, BILD_REST = 25, 3              # Dateien 3, 28, 53 … mit Bildbereich (OCR)
KENNWORT_ALLE, KENNWORT_REST = 40, 17     # Dateien 17, 57, 97 … kennwortgeschützt
KENNWORT = "Makler-2026"
PROFIL = gui.attrappen.STANDARD_PROFIL   # „hoch“ wie beim ersten Start; Kategorien der Stufe wie die Häkchen
AKTIVE = gui.attrappen.profil_kategorien(gui.PROFILE, PROFIL, {k[0] for k in gui.KATEGORIEN})

# Spielräume (Messung Runde 3b, Linux): an Ruhepunkten lagen die offenen Dateideskriptoren auf der Grundlinie oder
# 2 darüber (Pipes eines eben geschlossenen Pools, bis die Speicherbereinigung sie schließt); ein laufender OCR-Pool
# hält 8 bis 10 mehr (Pipes der Warteschlangen und des Weckrufs, je Arbeitsprozess eine). Unter Windows kommen
# Handles hinzu, die kommen und gehen (Thread-Pool von Windows), und ein Pool hält Prozess-, Pipe- und
# Semaphor-Handles. Ein Leck von einem Handle je Datei übersteigt den Ruhe-Spielraum spätestens nach zwei Stapeln,
# eines von einem Handle je Lauf nach 5 (Linux) bzw. 17 Läufen (Windows) – Gegenprobe oben.
HANDLES_RUHE = 16 if WINDOWS else 4
HANDLES_LAUF = 48 if WINDOWS else 16
SPEICHER_SCHRANKE_MB = 16      # Begründung bei test_langlauf_speicher_waechst_begrenzt
RUHE_WARTEN_S = 30.0           # so lange darf ein geschlossener OCR-Pool brauchen, bis Arbeiter und Pipes weg sind

_AUSGABE_NAME = re.compile(r"^anonym_(\d+)(_PRUEFEN)?\.pdf$")

VORNAMEN = ("Max", "Anna", "Jürgen", "Sabine", "Thomas", "Petra", "Michael", "Claudia", "Stefan", "Monika",
            "Andreas", "Birgit", "Frank", "Susanne", "Markus", "Heike", "Ralf", "Karin", "Uwe", "Martina")
NACHNAMEN = ("Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker", "Schulz",
             "Hoffmann", "Koch", "Richter", "Klein", "Wolf", "Schröder", "Neumann", "Schwarz", "Zimmermann",
             "Braun", "Krüger")
STRASSEN = ("Hauptstraße", "Bahnhofstraße", "Gartenweg", "Lindenallee", "Schulstraße", "Bergstraße", "Am Markt")
ORTE = (("10115", "Berlin"), ("80331", "München"), ("50667", "Köln"), ("20095", "Hamburg"),
        ("90402", "Nürnberg"), ("04109", "Leipzig"), ("70173", "Stuttgart"))


# ----------------------------------------------------------------------
# Messfühler (Linux und Windows, mit und ohne psutil)
# ----------------------------------------------------------------------
def offene_handles() -> int | None:
    """Offene Dateideskriptoren (POSIX) bzw. Handles (Windows) dieses Prozesses; None, wenn nicht messbar."""
    if WINDOWS:
        if psutil is not None:
            return psutil.Process().num_handles()
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.GetProcessHandleCount.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong))
        anzahl = ctypes.c_ulong()
        if kernel32.GetProcessHandleCount(kernel32.GetCurrentProcess(), ctypes.byref(anzahl)):
            return int(anzahl.value)
        return None
    for ordner in ("/proc/self/fd", "/dev/fd"):
        if os.path.isdir(ordner):
            return len(os.listdir(ordner))
    if psutil is not None:
        return psutil.Process().num_fds()
    return None


def residenter_speicher() -> int | None:
    """Residenter Speicher dieses Prozesses in Byte (Windows: Arbeitssatz); None, wenn nicht messbar."""
    if psutil is not None:
        return psutil.Process().memory_info().rss
    try:
        with open("/proc/self/statm", encoding="ascii") as statm:
            return int(statm.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, AttributeError, IndexError):
        return None


def _befehlszeile(pid: int) -> str:
    try:
        if psutil is not None:
            return " ".join(psutil.Process(pid).cmdline())
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
    except Exception:          # beendet, kein Zugriff, kein /proc: zählt als gewöhnlicher Kindprozess
        return ""


def ist_ressourcen_waechter(befehlszeile: str) -> bool:
    """Der Ressourcen-Wächter von multiprocessing (POSIX): ein Prozess je Programm, gestartet mit dem ersten
    Prozess-Pool, beendet mit dem Programm – kein OCR-Arbeiter, darf also bleiben (aber nur einer)."""
    return "multiprocessing.resource_tracker" in befehlszeile


def kindprozesse() -> dict[int, str]:
    """{PID: Befehlszeile} aller Kindprozesse, auch beendeter, die noch niemand abgeholt hat. Mit psutil über die
    Elternkennung (eine wiederverwendete PID eines fremden Prozesses zählt nicht); ohne psutil die Prozesse von
    multiprocessing und unter Linux /proc. Nur im Rückfall multiprocessing.active_children(): es holt beendete
    Kinder ab und veränderte so, was gemessen wird."""
    if psutil is not None:
        kinder = {kind.pid for kind in psutil.Process().children(recursive=True)}
    else:
        kinder = {prozess.pid for prozess in multiprocessing.active_children()}
        if os.path.isdir("/proc"):
            eigene = str(os.getpid())
            for eintrag in filter(str.isdigit, os.listdir("/proc")):
                try:
                    stat = Path(f"/proc/{eintrag}/stat").read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if stat.rpartition(")")[2].split()[1:2] == [eigene]:       # Feld 4: Elternprozess
                    kinder.add(int(eintrag))
    return {pid: _befehlszeile(pid) for pid in kinder}


# ----------------------------------------------------------------------
# Testdateien
# ----------------------------------------------------------------------
def _iban(nr: int) -> str:
    blz, konto = f"{37040044 + nr:08d}", f"{532013000 + 7919 * nr:010d}"
    roh = f"DE{98 - int(blz + konto + '131400') % 97:02d}{blz}{konto}"
    return " ".join(roh[i:i + 4] for i in range(0, len(roh), 4))


def _person(nr: int) -> tuple[str, str, bool]:
    """(Vorname, Nachname, männlich) – jede Datei eine andere Person."""
    return VORNAMEN[nr % 20], NACHNAMEN[(7 * nr + nr // 20) % 20], nr % 2 == 0


def _brieftext(nr: int) -> str:
    vorname, nachname, herr = _person(nr)
    plz, ort = ORTE[nr % len(ORTE)]
    return (f"Muster Versicherung AG · Schadenabteilung · Postfach 10 20 30 · 50667 Köln\n\n"
            f"{'Herrn' if herr else 'Frau'}\n{vorname} {nachname}\n{STRASSEN[nr % len(STRASSEN)]} {nr % 90 + 1}\n"
            f"{plz} {ort}\n\n"
            f"Versicherungsschein-Nr.: LV-2024-{100000 + 37 * nr}\nSchaden-Nr.: S-26-{4400 + nr}\n\n"
            f"{'Sehr geehrter Herr' if herr else 'Sehr geehrte Frau'} {nachname},\n\n"
            f"wir bestätigen den Eingang Ihrer Unterlagen vom 03.11.2026 zum Leitungswasserschaden.\n"
            f"Versicherte Person: {vorname} {nachname}, geb. am {nr % 28 + 1:02d}.{nr % 12 + 1:02d}."
            f"{1950 + nr % 50}\n"
            f"Bankverbindung für die Erstattung: IBAN {_iban(nr)}\n"
            f"Ihre Rufnummer für Rückfragen: 0171 {2345000 + nr}\n"
            f"E-Mail: {vorname.lower()}.{nachname.lower()}@example.de\n\n"
            f"Mit freundlichen Grüßen\nIhre Muster Versicherung AG\n")


def _bildbereich(nr: int) -> bytes:
    """Graustufen-PNG mit Text (ein eingeklebter Ausschnitt wie ein Kundenetikett) – die Analyse liest ihn per OCR."""
    vorname, nachname, _ = _person(nr)
    with fitz.open() as doc:
        seite = doc.new_page(width=220, height=60)
        seite.insert_text((10, 35), f"Kunde: {vorname} {nachname}", fontsize=14)
        return seite.get_pixmap(dpi=150, colorspace=fitz.csGRAY).tobytes("png")


def _nummer(pdf: Path) -> int:
    """brief_017.pdf -> 17"""
    return int(Path(pdf).stem.rpartition("_")[2])


def ist_bilddatei(nr: int) -> bool:
    return nr % BILD_ALLE == BILD_REST


def ist_kennwortdatei(nr: int) -> bool:
    return nr % KENNWORT_ALLE == KENNWORT_REST


def eingang_schreiben(eingang: Path) -> list[list[Path]]:
    """Je Stapel ein Kundenordner mit 10 Briefen (brief_001.pdf … brief_200.pdf); liefert die Dateien je Stapel."""
    stapel = []
    for nr in range(1, ANZAHL + 1):
        ordner = eingang / f"kunde_{(nr - 1) // STAPEL + 1:02d}"
        ordner.mkdir(parents=True, exist_ok=True)
        pfad = ordner / f"brief_{nr:03d}.pdf"
        with fitz.open() as doc:
            seite = doc.new_page()
            seite.insert_text((60, 80), _brieftext(nr), fontsize=10, fontname="helv")
            if ist_bilddatei(nr):
                seite.insert_image(fitz.Rect(300, 420, 520, 480), stream=_bildbereich(nr))
            schutz = {"encryption": fitz.PDF_ENCRYPT_AES_256, "user_pw": KENNWORT, "owner_pw": KENNWORT + "!"} \
                if ist_kennwortdatei(nr) else {}
            doc.save(pfad, **schutz)
        if nr % STAPEL == 1:
            stapel.append([])
        stapel[-1].append(pfad)
    return stapel


# ----------------------------------------------------------------------
# Die Sitzung: derselbe Weg wie die Oberfläche, ohne Fenster
# ----------------------------------------------------------------------
def _still(*_):
    """melde/fortschritt: die Oberfläche schreibt ins Protokoll und auf den Fortschrittsbalken."""


def _im_thread(name: str, funktion, *argumente):
    """Wie die Oberfläche: jeder Lauf in einem eigenen Thread (AnonymisiererApp.analysieren/schwaerzen)."""
    fehler = []

    def ziel():
        try:
            funktion(*argumente)
        except BaseException as e:  # noqa: BLE001 – im Test-Thread weitergeben
            fehler.append(e)

    faden = threading.Thread(target=ziel, name=name, daemon=True)
    faden.start()
    faden.join(timeout=600)
    assert not faden.is_alive(), f"Lauf „{name}“ ist nicht fertig geworden"
    if fehler:
        raise fehler[0]


def auftrag_funde(ergebnis: dict) -> list:
    """Funde wie AnonymisiererApp._auftrag mit den Häkchen nach der Analyse: angehakte (auch teilweise) mit ihren
    Stellen; ganz abgewählte gehen nur als Bildfund mit (ein abgewähltes Lichtbild verlangt die Freigabe)."""
    funde, abgewaehlte_bilder = [], []
    for fund in ergebnis["funde"]:
        stellen = fund.get("stellen") or []
        if stellen and not any(st.get("an", True) for st in stellen):
            if gui._ist_bildfund(fund):
                abgewaehlte_bilder.append(dict(fund, stellen=[dict(st, an=False) for st in stellen]))
            continue
        kopie = dict(fund)
        if stellen:
            kopie["stellen"] = [dict(st) for st in stellen]
        funde.append(kopie)
    return funde + abgewaehlte_bilder


class Langlauf:
    """Eine Sitzung der Oberfläche ohne Fenster – Stapel hinzufügen, analysieren, schwärzen, Liste leeren – mit den
    Prüfungen nach jeder Datei und an jedem Ruhepunkt."""

    def __init__(self, wurzel: Path):
        self.wurzel = wurzel
        self.eingang = wurzel / "eingang"
        self.ausgabe = wurzel / "ausgabe"           # gemeinsamer Zielordner (Häkchen „Zielordner“)
        self.temp = dateien.temp_basis()
        self.systemp = Path(tempfile.gettempdir())
        self.stapel = eingang_schreiben(self.eingang)
        self.eingang_vorher = sorted(p.relative_to(self.eingang) for p in self.eingang.rglob("*"))
        self.fehler: Exception | None = None
        self.dauer_s: float | None = None
        self.geschwaerzt = 0                         # fertig geschwärzte Dateien
        self.datei_nr = 0                            # zuletzt angefasste Datei
        self.kopien: dict[Path, Path] = {}           # Arbeitskopien des laufenden Stapels (Original -> Kopie)
        self.je_datei: list = []                     # (Datei, Schritt, Handles, RSS in MB)
        self.ruhe: list = []                         # (Datei, Ruhepunkt, Handles, Threads)
        self.speicher: dict[int, int] = {}           # Datei -> RSS am Stapelende (nach gc.collect)
        self.kinder_vorher = kindprozesse()
        self.threads_vorher = threading.active_count()
        self.arbeiter: dict[int, str] = {}           # OCR-Arbeitsprozesse, die während der Läufe lebten
        self.ocr_laeufe: list[tuple[str, int]] = []  # (Lauf, letzte Datei) mit Aufträgen im OCR-Pool
        self.handles_basis: int | None = None
        self.systemp_basis: list | None = None

    # -- Ablauf ----------------------------------------------------------
    def ausfuehren(self):
        beginn = time.monotonic()
        dateien.alte_sitzungen_aufraeumen()          # wie beim Programmstart
        dateien.sitzung_beginnen()                   # wie beim Öffnen des Hauptfensters
        for nr, dateien_des_stapels in enumerate(self.stapel, 1):
            self._stapel(nr, dateien_des_stapels)
        # Fenster schließen (_aufraeumen): Arbeitskopien endgültig weg, keine neue Sitzung mehr
        assert dateien.sitzung_aufraeumen(endgueltig=True), "Sitzungsordner ließ sich beim Beenden nicht löschen"
        self._ruhepunkt("Beenden")
        self.dauer_s = time.monotonic() - beginn

    def _stapel(self, nr: int, dateien_des_stapels: list[Path]):
        bericht = dateien.sammle_pdfs_bericht([str(dateien_des_stapels[0].parent)])    # Kundenordner hinzufügen
        pdfs = bericht["pdfs"]                          # wie die Oberfläche: mit den Pfaden der Eingangsprüfung
        assert [p.name for p in pdfs] == [p.name for p in dateien_des_stapels], \
            f"Stapel {nr}: Eingangsprüfung lieferte {pdfs}"
        for pdf in pdfs:                                # R-12: geschützte PDFs als Kopie ohne Kennwort
            if dateien.pdf_kennwort_noetig(pdf):
                ziel = dateien.arbeitskopie_ziel(pdf.name)
                assert dateien.pdf_entschluesseln(pdf, KENNWORT, ziel), f"{pdf.name}: Kennwort abgelehnt"
                self.kopien[pdf] = ziel
        assert len(self.kopien) == sum(1 for p in pdfs if ist_kennwortdatei(_nummer(p)))
        self._temp_pruefen(f"Stapel {nr} hinzugefügt")
        ergebnisse: dict[Path, dict] = {}
        _im_thread("Analyse", self._analyse_lauf, pdfs, ergebnisse)
        self._ruhepunkt(f"Stapel {nr} analysiert")
        _im_thread("Schwaerzung", self._schwaerz_lauf, pdfs, ergebnisse)
        self._ruhepunkt(f"Stapel {nr} geschwärzt")
        for pdf in pdfs:                                # „Liste leeren“ (_datei_vergessen)
            ergebnisse.pop(pdf, None)
            kopie = self.kopien.pop(pdf, None)
            if kopie is not None:
                assert dateien.arbeitskopie_entfernen(kopie), f"{pdf.name}: Arbeitskopie nicht gelöscht"
        self._temp_pruefen(f"Stapel {nr}: Liste geleert")
        self._ruhepunkt(f"Stapel {nr}: Liste geleert", stapelende=True)

    def _analyse_lauf(self, pdfs: list[Path], ergebnisse: dict):
        """AnonymisiererApp._analyse_lauf ohne Oberfläche (Protokoll und Fortschritt entfallen)."""
        abbruch = threading.Event()
        ocr = None
        try:
            ocr = gui.OcrDienst()
            for pdf in pdfs:
                gui._seitenzahl(self.kopien.get(pdf, pdf))          # Fortschrittsbalken
            if "namen" in AKTIVE:
                gui.lade_ner()
            zusatz = {"profil": PROFIL} if gui.kann(gui.analysiere_pdf, "profil") else {}
            if gui.LaufWissen is not None and gui.kann(gui.analysiere_pdf, "lauf"):
                zusatz["lauf"] = gui.LaufWissen()
            for pdf in pdfs:
                datei = self.kopien.get(pdf, pdf)
                assert dateien.fuer_engine_erlaubt(dateien.datei_art(datei)), pdf.name
                ergebnis = gui.analysiere_pdf(datei, AKTIVE, [], [], melde=_still, fortschritt=_still,
                                              abbruch=abbruch, ocr=ocr, **zusatz)
                ergebnis = gui._analyse_ergebnis_pruefen(ergebnis, pdf)
                assert not ergebnis["fehler"], f"{pdf.name}: {ergebnis['fehler']}"
                assert any(f["kategorie"] == "iban" for f in ergebnis["funde"]), f"{pdf.name}: keine IBAN gefunden"
                ergebnisse[pdf] = ergebnis
                self._nach_datei(pdf, "analysiert")
            gute = [e for e in ergebnisse.values() if not e["fehler"]]
            if gui.weitergabe_anwenden is not None and len(gute) > 1:
                gui.weitergabe_anwenden(gute)
        finally:
            self._ocr_vermerken("Analyse", ocr)
            gui.AnonymisiererApp._ocr_schliessen(ocr)

    def _schwaerz_lauf(self, pdfs: list[Path], ergebnisse: dict):
        """AnonymisiererApp._schwaerz_lauf ohne Oberfläche, gemeinsamer Zielordner, Freigabe erforderlich."""
        abbruch = threading.Event()
        ocr = None
        try:
            ocr = gui.OcrDienst()
            for pdf in pdfs:
                gui._seitenzahl(self.kopien.get(pdf, pdf))
            dateien.zwischendateien_aufraeumen(self.ausgabe)
            for pdf in pdfs:
                ergebnis = ergebnisse[pdf]
                kwargs = {"melde": _still, "fortschritt": _still, "abbruch": abbruch, "ocr": ocr,
                          "ocr_cache": ergebnis.get("ocr_cache"), "ziel_ordner": self.ausgabe}
                if isinstance(ergebnis.get("nebenkanaele"), dict) and gui.kann(gui.schwaerze_pdf, "nebenkanaele"):
                    kwargs["nebenkanaele"] = ergebnis["nebenkanaele"]
                if ergebnis.get("modell") is not None and gui.kann(gui.schwaerze_pdf, "modell"):
                    kwargs["modell"] = ergebnis["modell"]
                if gui.kann(gui.schwaerze_pdf, "freigabe_erforderlich"):
                    kwargs["freigabe_erforderlich"] = True    # Häkchen „Freigabe erforderlich“ ist Standard
                if gui.kann(gui.schwaerze_pdf, "profil"):
                    kwargs["profil"] = PROFIL
                datei = self.kopien.get(pdf, pdf)
                assert dateien.fuer_engine_erlaubt(dateien.datei_art(datei)), pdf.name
                schwaerzung = gui.schwaerze_pdf(datei, auftrag_funde(ergebnis), **kwargs)
                schwaerzung = gui._schwaerz_ergebnis_pruefen(schwaerzung, pdf)
                gui.AnonymisiererApp._reste_verorten(schwaerzung)
                status = gui.AnonymisiererApp._ausgabe_status(schwaerzung)
                assert not schwaerzung["fehler"] and schwaerzung["treffer"] > 0, \
                    f"{pdf.name}: {schwaerzung['fehler'] or 'nichts geschwärzt'}"
                assert status == "pruefen", f"{pdf.name}: Status {status} trotz Freigabe-Pflicht"
                self.geschwaerzt += 1
                self._ausgabe_pruefen(schwaerzung["ausgabe"])
                self._nach_datei(pdf, "geschwärzt")
        finally:
            self._ocr_vermerken("Schwärzung", ocr)
            gui.AnonymisiererApp._ocr_schliessen(ocr)

    # -- Messungen und Prüfungen ------------------------------------------
    def _neue_kinder(self) -> dict[int, str]:
        return {pid: zeile for pid, zeile in kindprozesse().items() if pid not in self.kinder_vorher}

    def _ocr_vermerken(self, lauf: str, ocr):
        """Vor dem Schließen des OCR-Diensts: hat er im Pool gerechnet, leben jetzt seine Arbeitsprozesse – sie
        werden vermerkt (der nächste Ruhepunkt verlangt, dass sie beendet sind)."""
        if ocr is None or not int((getattr(ocr, "statistik", None) or {}).get("auftraege", 0) or 0):
            return
        self.ocr_laeufe.append((lauf, self.datei_nr))
        self.arbeiter.update((pid, z) for pid, z in self._neue_kinder().items() if not ist_ressourcen_waechter(z))

    def _nach_datei(self, pdf: Path, schritt: str):
        self.datei_nr = _nummer(pdf)
        handles, rss = offene_handles(), residenter_speicher()
        self.je_datei.append((self.datei_nr, schritt, handles, None if rss is None else round(rss / 2 ** 20, 1)))
        if schritt == "geschwärzt":
            self._temp_pruefen(f"{pdf.name} geschwärzt")
        if self.handles_basis is not None:
            assert handles <= self.handles_basis + HANDLES_LAUF, (
                f"{pdf.name} {schritt}: {handles} offene Handles, Grundlinie {self.handles_basis} + Spielraum "
                f"{HANDLES_LAUF} – je Datei (Nr., a/g, Handles): "
                + ", ".join(f"{nr}{s[0]}:{h}" for nr, s, h, _ in self.je_datei[-12:]))

    def _ruhepunkt(self, name: str, stapelende: bool = False):
        """Nach einem Lauf: warten, bis der geschlossene OCR-Pool seine Arbeitsprozesse und Threads beendet hat
        (höchstens RUHE_WARTEN_S), dann Prozesse, Threads, Handles und System-Temp prüfen."""
        ende = time.monotonic() + RUHE_WARTEN_S
        while True:
            lebend = {pid: z for pid, z in self._neue_kinder().items() if not ist_ressourcen_waechter(z)}
            threads = threading.active_count()
            handles = offene_handles()
            ruhig = not lebend and threads <= self.threads_vorher and (
                self.handles_basis is None or handles <= self.handles_basis + HANDLES_RUHE)
            if ruhig or time.monotonic() > ende:
                break
            gc.collect()                    # Pipes und Prozess-Objekte des Pools hängen auch an Zyklen
            time.sleep(0.05)
        self.ruhe.append((self.datei_nr, name, handles, threads))
        assert not lebend, (f"{name}: {len(lebend)} Kindprozess(e) leben nach dem Schließen des OCR-Dienstes "
                            f"weiter: {lebend}")
        waechter = [pid for pid, z in self._neue_kinder().items() if ist_ressourcen_waechter(z)]
        assert len(waechter) <= 1, f"{name}: {len(waechter)} Ressourcen-Wächter von multiprocessing"
        assert threads <= self.threads_vorher, (
            f"{name}: {threads} Threads, vor der Sitzung {self.threads_vorher}: "
            f"{[t.name for t in threading.enumerate()]}")
        if self.handles_basis is None and stapelende and self.datei_nr >= AUFWAERMEN:
            gc.collect()
            self.handles_basis = offene_handles()
            assert self.handles_basis is not None, "offene Handles sind auf diesem System nicht messbar"
            self.systemp_basis = self._baum(self.systemp)
            self.ruhe.append((self.datei_nr, "Grundlinie", self.handles_basis, threads))
        elif self.handles_basis is not None:
            assert handles <= self.handles_basis + HANDLES_RUHE, (
                f"{name}: {handles} offene Handles, Grundlinie nach {AUFWAERMEN} Dateien {self.handles_basis} + "
                f"Spielraum {HANDLES_RUHE} – Ruhepunkte (Datei, Punkt, Handles, Threads): {self.ruhe[-8:]}")
            neu = sorted(set(self._baum(self.systemp)) - set(self.systemp_basis))
            assert self._baum(self.systemp) == self.systemp_basis, f"{name}: System-Temp verändert, neu: {neu}"
        if stapelende:
            gc.collect()
            rss = residenter_speicher()
            if rss is not None:
                self.speicher[self.datei_nr] = rss

    @staticmethod
    def _baum(ordner: Path) -> list[str]:
        return sorted(str(p.relative_to(ordner)) for p in ordner.rglob("*")) if ordner.exists() else []

    def _temp_pruefen(self, wann: str):
        """Im Ordner für Arbeitskopien liegen genau die Kopien der Kennwort-PDFs des laufenden Stapels (in ihrem
        kopie_-Unterordner des Sitzungsordners) – sonst nichts."""
        erwartet = {p.resolve() for p in self.kopien.values()}
        sitzung = dateien.aktuelle_sitzung()
        if sitzung is not None:
            erwartet |= {Path(sitzung).resolve()} | {p.resolve().parent for p in self.kopien.values()}
        vorhanden = {p.resolve() for p in self.temp.rglob("*")} if self.temp.exists() else set()
        assert vorhanden == erwartet, (f"{wann}: Ordner für Arbeitskopien enthält Reste "
                                       f"{sorted(str(p) for p in vorhanden - erwartet)}, es fehlen "
                                       f"{sorted(str(p) for p in erwartet - vorhanden)}")

    def _ausgabe_pruefen(self, ausgabe: Path):
        """Nach Datei k liegen im Zielordner genau anonym_01 … anonym_k – keine Zwischendatei, nichts anderes."""
        namen = sorted(os.listdir(self.ausgabe))
        nummern = sorted(int(m.group(1)) for m in map(_AUSGABE_NAME.match, namen) if m)
        assert len(nummern) == len(namen) and nummern == list(range(1, self.geschwaerzt + 1)), (
            f"Zielordner nach {self.geschwaerzt} Datei(en): {namen[-5:]} (unerwartet: "
            f"{[n for n in namen if not _AUSGABE_NAME.match(n)]})")
        assert Path(ausgabe).name in namen and os.path.samefile(Path(ausgabe).parent, self.ausgabe), ausgabe

    def abschluss_pruefen(self):
        """Nach dem Beenden: keine neuen Kindprozesse (außer dem Ressourcen-Wächter), Arbeitsprozesse liefen
        wirklich, Ordner für Arbeitskopien leer, Eingang unverändert, Zielordner und Zuordnungsdatei vollständig."""
        neue = self._neue_kinder()
        assert all(ist_ressourcen_waechter(z) for z in neue.values()), f"Kindprozesse nach dem Beenden: {neue}"
        reste = [p for p in multiprocessing.active_children() if p.pid not in self.kinder_vorher]
        assert not reste, f"multiprocessing-Prozesse nach dem Beenden: {reste}"
        assert self.arbeiter, "kein OCR-Arbeitsprozess lief – die Prüfung der Prozesse hätte nichts geprüft"
        nach_aufwaermen = [lauf for lauf in self.ocr_laeufe if lauf[1] > AUFWAERMEN]
        assert len(nach_aufwaermen) >= 4, f"zu wenige Läufe mit OCR-Pool nach der Aufwärmphase: {self.ocr_laeufe}"
        assert not self._baum(self.temp), f"Ordner für Arbeitskopien nach dem Beenden: {self._baum(self.temp)}"
        assert dateien.aktuelle_sitzung() is None
        assert sorted(p.relative_to(self.eingang) for p in self.eingang.rglob("*")) == self.eingang_vorher, \
            "im Eingangsordner ist etwas entstanden"
        namen = sorted(os.listdir(self.ausgabe))
        assert len(namen) == ANZAHL and all(_AUSGABE_NAME.match(n) for n in namen), namen[-5:]
        neben = sorted(p.name for p in self.wurzel.iterdir() if p.name not in ("eingang", "ausgabe", "temp", "log"))
        assert neben == [f"_zuordnung_{self.ausgabe.name}.txt"], f"neben dem Zielordner: {neben}"
        zeilen = [z for z in (self.wurzel / neben[0]).read_text(encoding="utf-8").splitlines() if "<-" in z]
        assert len(zeilen) == ANZAHL, f"Zuordnungsdatei mit {len(zeilen)} statt {ANZAHL} Zeilen"
        fehlerlog = self.wurzel / "log" / "fehler.log"
        assert not fehlerlog.exists(), fehlerlog.read_text(encoding="utf-8")[-2000:]

    def bericht(self) -> str:
        nach = [h for nr, _, h, _ in self.je_datei if nr > AUFWAERMEN]
        zeilen = [f"Langlauf {ANZAHL} Dateien, {sys.platform}, psutil {'ja' if psutil else 'nein'}, "
                  f"Dauer {self.dauer_s or 0:.1f} s, Fehler: {self.fehler!r}",
                  f"Handles: Grundlinie {self.handles_basis}, je Datei nach der Aufwärmphase höchstens "
                  f"{max(nach) if nach else None} (Spielraum Lauf {HANDLES_LAUF}, Ruhe {HANDLES_RUHE})",
                  "Ruhepunkte (Datei, Punkt, Handles, Threads):"]
        zeilen += [f"  {r}" for r in self.ruhe]
        zeilen.append("RSS am Stapelende (Datei: MB): " + ", ".join(
            f"{nr}: {rss / 2 ** 20:.1f}" for nr, rss in sorted(self.speicher.items())))
        zeilen.append(f"Läufe mit OCR-Pool (Lauf, bis Datei): {self.ocr_laeufe}")
        zeilen.append(f"OCR-Arbeitsprozesse: {len(self.arbeiter)}")
        return "\n".join(zeilen)


@pytest.fixture(scope="module")
def langlauf(tmp_path_factory):
    """Die Sitzung läuft einmal; die Prüfungen auf Handles, Temp-Dateien und Prozesse laufen dabei mit (ein Fehler
    wird vermerkt und von test_langlauf_200_dateien_ohne_lecks gemeldet), die auf Speicher danach. Ordner für
    Arbeitskopien, Fehlerprotokoll und System-Temp liegen im Testordner – das System-Temp auch für die
    OCR-Arbeitsprozesse (sie erben die Umgebung beim Start). In der CI landen die Messwerte im Bericht-Artefakt."""
    wurzel = tmp_path_factory.mktemp("langlauf")
    systemp = wurzel / "temp" / "system"
    systemp.mkdir(parents=True)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(dateien, "temp_basis", lambda: wurzel / "temp" / "programm")
        mp.setattr(dateien, "fehlerlog_pfad", lambda: wurzel / "log" / "fehler.log")
        mp.setattr(dateien, "_SITZUNG", None)
        mp.setattr(dateien, "_SITZUNG_BEENDET", False)       # ein Test davor hat womöglich ein Fenster geschlossen
        for name in ("TMPDIR", "TEMP", "TMP"):
            mp.setenv(name, str(systemp))
        mp.setattr(tempfile, "tempdir", str(systemp))
        lauf = Langlauf(wurzel)
        try:
            lauf.ausfuehren()
            lauf.abschluss_pruefen()
        except Exception as fehler:
            lauf.fehler = fehler
        finally:
            ablage = os.environ.get("PDF_ANONYMISIERER_BERICHT")
            if ablage:
                Path(ablage).mkdir(parents=True, exist_ok=True)
                (Path(ablage) / f"langlauf_{sys.platform}.txt").write_text(lauf.bericht() + "\n", encoding="utf-8")
        yield lauf


def test_messfuehler_sehen_lecks(tmp_path):
    """Gegenprobe der Messfühler auf dieser Plattform – sonst prüfte der Langlauf womöglich nichts: fünf offene
    Dokumente zählen als mindestens fünf Handles, 64 MB Ballast als residenter Speicher, ein laufender Prozess
    (Start-Methode „spawn“ wie der OCR-Pool) als Kindprozess, der nach dem Beenden verschwindet."""
    pdf = tmp_path / "probe.pdf"
    with fitz.open() as doc:
        doc.new_page().insert_text((72, 72), "Probe", fontname="helv")
        doc.save(pdf)
    vorher = offene_handles()
    assert vorher is not None, "offene Handles sind auf diesem System nicht messbar"
    offen = [fitz.open(pdf) for _ in range(5)]
    try:
        assert offene_handles() >= vorher + 5
    finally:
        for doc in offen:
            doc.close()
    assert offene_handles() <= vorher + HANDLES_RUHE
    rss = residenter_speicher()
    if rss is not None:                    # nicht messbar: nur test_langlauf_speicher_waechst_begrenzt entfällt
        ballast = b"\x01" * (64 << 20)       # jede Seite beschrieben, also resident
        try:
            assert residenter_speicher() >= rss + (48 << 20), f"{len(ballast) >> 20} MB Ballast nicht gemessen"
        finally:
            del ballast
    prozess = multiprocessing.get_context("spawn").Process(target=time.sleep, args=(60,), daemon=True)
    prozess.start()
    try:
        assert prozess.pid in kindprozesse()
    finally:
        prozess.terminate()
        prozess.join(30)
    assert prozess.pid not in kindprozesse()


def test_langlauf_200_dateien_ohne_lecks(langlauf):
    """Punkte 1, 3 und 4: Handles und Threads, Temp-Dateien und Ausgaben, Arbeitsprozesse – geprüft während der
    Sitzung nach jeder Datei und an jedem Ruhepunkt (Messung Runde 3b, Linux: 34 s für 200 Dateien; Grundlinie und
    alle Ruhepunkte bei 13 Deskriptoren, zweimal kurz nach einem OCR-Pool 15; ein Thread; 16 Läufe mit OCR-Pool,
    16 Arbeitsprozesse, alle beendet)."""
    if langlauf.fehler is not None:
        raise langlauf.fehler
    assert langlauf.geschwaerzt == ANZAHL


def test_langlauf_speicher_waechst_begrenzt(langlauf):
    """Punkt 2: Der residente Speicher wächst von Datei 50 bis 200 um höchstens SPEICHER_SCHRANKE_MB.

    Messung Runde 3b (Linux, Sprachmodell geladen, RSS um 520 MB): +1,5 bis +4,8 MB in mehreren Läufen, in Stufen
    von gut 1,5 MB. Das sind begrenzte Zwischenspeicher, die sich mit den neuen Wörtern jedes Briefs füllen
    (lru_cache von wissen.normalisieren: nach 400 Briefen 33 719 von höchstens 131 072 Einträgen,
    normalisieren_umschrift 31 495 von 65 536; die Stufen sind das Verdoppeln ihrer Hash-Tabellen) – sie wachsen
    bis zu ihrer Obergrenze, nicht ohne Ende: über 400 Briefe +5,0 MB von Datei 50 bis 400. Ein echtes Leck ist
    größer: ein behaltenes Analyse-Ergebnis samt Seitenmodell kostet bei diesen Briefen rund 340 KB, über 150
    Dateien +50 bis 52 MB (Gegenprobe). Die Schranke liegt beim Dreifachen des größten gemessenen Zuwachses (Raum
    für Speicherverwaltung und Arbeitssatz unter Windows) und fängt jedes Leck ab etwa 110 KB je Datei."""
    if residenter_speicher() is None:
        pytest.skip("residenter Speicher ist hier nicht messbar (weder psutil noch /proc/self/statm) – Handles, "
                    "Temp-Dateien und Prozesse prüft test_langlauf_200_dateien_ohne_lecks")
    if not {SPEICHER_VON, ANZAHL} <= set(langlauf.speicher):
        pytest.fail(f"Die Sitzung endete vor Datei {ANZAHL} ({langlauf.fehler!r}) – Speicher nicht bewertbar, siehe "
                    f"test_langlauf_200_dateien_ohne_lecks", pytrace=False)
    zuwachs = (langlauf.speicher[ANZAHL] - langlauf.speicher[SPEICHER_VON]) / 2 ** 20
    assert zuwachs <= SPEICHER_SCHRANKE_MB, (
        f"Speicher wuchs von Datei {SPEICHER_VON} bis {ANZAHL} um {zuwachs:.1f} MB (Schranke "
        f"{SPEICHER_SCHRANKE_MB} MB)\n{langlauf.bericht()}")
