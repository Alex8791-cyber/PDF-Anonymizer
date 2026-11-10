# Änderungen

Alle nennenswerten Änderungen am PDF-Anonymisierer. Das Format folgt
[Keep a Changelog](https://keepachangelog.com/de/1.1.0/); die Versionsnummer steht in
`anonymisierer/__init__.py`.

## [Unreleased]

Auslieferung und Dokumentation nach dem Review „Auslieferung/Doku“ (AD-01 … AD-08):

### Installation und EXE (`Installieren.bat`, `EXE-bauen.bat`, `requirements.txt`)
- **Kein erneuter 44-MB-Download mehr:** Eine Vorab-Prüfung (Importe plus Versionsgrenzen wie
  in `requirements.txt`) überspringt pip, wenn alles in passender Version installiert ist.
  Vorher lud pip das per URL eingebundene Sprachmodell bei jedem Lauf neu und scheiterte ohne
  github.com – auch beim zweiten Lauf nach dem Verschieben des Ordners und bei jedem EXE-Bau.
  `EXE-bauen.bat` prüft Laufzeitpakete und PyInstaller getrennt: Fehlt nur PyInstaller, wird
  nur `requirements-dev.txt` installiert.
- **Offline-Weg für das Sprachmodell:** Liegt `de_core_news_md-3.8.0-py3-none-any.whl` im
  Programmordner, installiert `Installieren.bat` das Modell daraus (`--no-index`), ohne
  github.com; die Fehlermeldung erklärt den Weg. Ehrlicher Hinweis, dass auch
  `spacy download` von github.com lädt.
- **PyMuPDF-Untergrenze 1.24.10** (vorher 1.24): `Page.remove_rotation()` gibt es erst ab
  1.24.3, `Document.bake()`/`apply_redactions(text=…)` ab 1.24.2, und bis 1.24.9 liest die OCR
  seitlich gedrehte Scans nicht (mit Schatten-Installationen geprüft: 1.24.3 und 1.24.9 – ein
  Test rot, 1.24.10, 1.28.2 und 2.1 – alle 382 Tests grün). Gleiche Grenzen in beiden
  Batch-Dateien; `werkzeuge/pruefe_installation.py` meldet Versionen, die nicht zu
  `requirements.txt` passen.
- **Lizenztexte in der EXE-ZIP:** `EXE-bauen.bat` legt `LICENSE.txt`, `THIRD_PARTY_NOTICES.md`,
  `README.md` und den vollständigen AGPL-3.0-Text (`licenses/AGPL-3.0.txt`, neu im Repository –
  das PyMuPDF-Wheel enthält nur einen Einzeiler) in den Programmordner und bricht ab, wenn das
  nicht gelingt.
- **ARM64:** Für ARM64-Python 3.11 bis 3.15 gibt es inzwischen alle Pakete als fertige Wheels
  (mit pip für `win_arm64` aufgelöst); Hinweistexte sagen jetzt „ungetestet“ statt „nicht
  unterstützt“, ein ARM64-Python 3.10 (ohne spaCy-Pakete) wird übersprungen, und
  „No matching distribution found“ wird nicht mehr pauschal mit ARM64 erklärt.

### GitHub-Action (`.github/workflows/tests.yml`)
- `permissions: contents: read`, Zeitlimits für Jobs und Schritte, Windows-Bildschirmauflösung
  im Protokoll (Versuch, sie auf 1920×1080 zu stellen), Layout-Screenshots beider Systeme als
  Artefakt, Begründungen übersprungener Tests im Bericht (`-rs`).
- Neuer Job **`exe`** (windows-latest; von Hand oder für Tags `v*`): führt `EXE-bauen.bat` aus,
  prüft OCR-Sprachdatei, Sprachmodell, Lizenztexte und ZIP-Inhalt, startet die EXE probeweise
  (Fenster da, keine `fehler.log`) und lädt die ZIP als Artefakt hoch.
- Layout-Test: Auf Bildschirmen unter 1366×768 (Windows-Runner: oft 1024×768) werden nur die
  Skalierungen übersprungen, die Windows dort gar nicht anbietet (mindestens 720 Bildzeilen
  nach Skalierung); ab 1366×768 und im 1366×768-Szenario prüft der Test unverändert.

### Dokumentation
- README: „Was NICHT erkannt wird“ behauptete fälschlich, Versicherten-, Fahrzeug-Ident- und
  Ausweisnummern würden nicht erkannt; jetzt steht dort, welche Nummern nur mit Etikett gefunden
  werden. `fehler.log` der EXE liegt immer unter `%LOCALAPPDATA%\PDF-Anonymisierer`; Hinweise
  für EXE-Empfänger (`_internal`, Rückfragen), Offline-Weg, Downloadgröße (ca. 170 MB),
  PyMuPDF-Reihe je Python-Version.
- `THIRD_PARTY_NOTICES.md`: TkDND 2.10.3 (BSD-artige Lizenz) statt „2.9.x, MIT-ähnlich“,
  PyMuPDF ab 1.24.10 (MuPDF 1.24.9) statt „MuPDF 1.26–1.28“, Abhängigkeiten von PyMuPDF 2.x
  (onnxruntime u. a. nur bei pip, psutil/PyYAML auch in der EXE), Copyright-Vermerke der
  MIT-Komponenten, Ort des AGPL-Texts.

## [0.2.0] – 2026-11-09

Ergebnis eines Audits mit 70 bestätigten Befunden (Erkennung, Schwärzung/OCR,
Oberfläche, Installation/EXE, Dokumentation). Zusammenfassung nach Bereichen:

### Erkennung (`muster.py`, `namen.py`, `analyse.py`)
- Neue Kategorie **Kindergeldnummern** (`[KINDERGELD-NR]`); die Funktion gab es, sie war
  nur nicht eingehängt. **Kfz-Kennzeichen** sind jetzt standardmäßig an.
- Vertragsnummern: zusätzliche Etiketten (Schein-Nr., Versicherungsnummer, Vers.-Nr. …).
- Pseudonyme: eine Person bekommt in allen Schreibweisen („Dr. Max Mustermann“,
  „Mustermann, Max“, „MAX MUSTERMANN“) denselben Platzhalter; Familien mit gleichem
  Nachnamen werden unterschieden; Namensbestandteile erben das Pseudonym; Partikel und
  Titel (von, de, Dr., Herr …) werden nicht mehr einzeln geschwärzt.
- „NIE schwärzen“ gilt nur noch für ganze Wörter/Phrasen (Mindestlänge 3) und meldet
  freigegebene Funde als Hinweis; „IMMER schwärzen“ ersetzt durch `[BEGRIFF]`.
- Funde tragen Seitennummern, Anzahl und Kontext; Formularfelder werden vor der Analyse
  eingebrannt, XFA-Formulare werden gemeldet.

### Schwärzung und OCR (`schwaerzung.py`, `ocr.py`)
- Ganzwort-Prüfung bei der Suche im PDF: Ein Fund wird nicht mehr mitten in einem
  längeren Wort geschwärzt; Treffer werden gegen die Wortkoordinaten plausibilisiert
  (Silbentrennung).
- Nebenkanäle entfernt: Anmerkungen, Links, Lesezeichen, eingebettete Dateien, Metadaten
  (Info + XMP), Vorschaubilder; Speichern mit `garbage=4`.
- Neutrale Ausgabedateinamen `anonym_01.pdf`, `_zuordnung.txt` mit der Zuordnung zum
  Original, `_PRUEFEN` im Namen, wenn die Selbstkontrolle noch Fundtext findet; nie
  Überschreiben bestehender Ausgaben; keine Ausgabe, wenn kein Fund lokalisiert wurde.
- OCR: Scan-Erkennung über die Bildfläche in Summe (Textstempel, Fax-Kopf, Kacheln),
  Ausrichtung kopfstehender Scans, OCR-Wörter werden einmal je Seite erzeugt und
  wiederverwendet (statt dreimal), OCR läuft in eigenen Prozessen mit Abbruch.
- Sprachdaten: `tessdata/deu.traineddata` wird mitgeliefert und zuerst im Programm-/
  EXE-Ordner gesucht; ein Ordner ohne Sprachdatei zählt nicht mehr als Fund.

### Oberfläche (`gui.py`, `pdf_anonymisierer.py`)
- Baumzeilen sind an den vollständigen Pfad gebunden (gleichnamige PDFs in verschiedenen
  Ordnern wurden vorher verwechselt); Ordner werden relativ angezeigt.
- Häkchen per Einfachklick, „alle an/aus“ je Datei und Kategorie; Spalten Seite(n),
  Anzahl, Kontext, Ersatz.
- Layout passt sich an Bildschirmgröße und Skalierung an (Mindestgröße ca. 640 × 520,
  Aktionsleiste unten verankert); Fortschritt je Seite, Abbrechen-Knopf,
  Schließen-Rückfrage während eines Laufs.
- Fehler in Arbeitsthreads landen in `fehler.log` und einem Dialog (vorher fror die
  Oberfläche ein); `fehler.log` liegt neben dem Skript oder unter
  `%LOCALAPPDATA%\PDF-Anonymisierer`, nie im temporären PyInstaller-Ordner.
- Abschlussdialog mit Anzahl Warnungen, Dateien ohne Ausgabe und `_PRUEFEN`-Dateien,
  „Ordner öffnen“; Einstellungen werden gespeichert; Hinweiskasten „Nicht erkannt werden …“;
  Wortwahl ohne „gefahrlos“; Versionsnummer im Fenstertitel.

### Installation und EXE (`Installieren.bat`, `EXE-bauen.bat`, `requirements.txt`)
- `Installieren.bat` braucht nur noch **einen** Lauf (nach der Python-Installation wird
  der Interpreter direkt gefunden), prüft jeden Schritt, nennt bei Fehlern die
  wahrscheinliche Ursache (kein Internet, Proxy/Firmenzertifikat, ARM64/32-Bit, Rechte,
  Store-Alias) und meldet „Fertig“ nur bei Erfolg; kein Autostart nach Fehlern.
- Pakete über `requirements.txt` mit Bereichs-Pins und `--only-binary=:all:` (kein
  Quellbau mehr auf ARM64); Sprachmodell als Wheel von GitHub, Fallback `spacy download`.
- **Kein winget-Tesseract mehr** – PyMuPDF bringt die Engine mit, die Sprachdatei liegt im
  Repository.
- Desktop-Verknüpfung über `werkzeuge/verknuepfung.py` (Pfade per Umgebungsvariablen,
  .ps1 als UTF-8 mit BOM, Prüfung der .lnk) – funktioniert mit Umlauten, „&“, „!“,
  Klammern und Apostroph im Pfad; fehlendes `echo` vor „[5/5]“ behoben; neues
  `Starten.bat` als zweiter Startweg.
- `EXE-bauen.bat`: onedir statt onefile (schnellerer Start, keine Temp-Kopien, weniger
  Virenscanner-Fehlalarme), `--noconfirm --clean`, `--add-data tessdata`,
  Versionsinformationen, Icon falls vorhanden, Modellprüfung vor dem Bau, ZIP des
  Ordners, Hinweise zu SmartScreen/Signatur/Verteilweg; Empfänger brauchen kein Tesseract.
- Neu: `werkzeuge/pruefe_installation.py` für Rückfragen.

### Dokumentation und Projekt
- README in echtem Markdown: Erkennungstabelle aus dem Code erzeugt
  (`werkzeuge/readme_tabelle.py`), Erststart-Dialoge, ZIP-Ordnerstruktur,
  „Was NICHT erkannt wird“, Ausgabedateinamen, Pseudonymisierungs-Hinweis, EXE-Weitergabe,
  Problemlösung, Lizenzlage.
- `LICENSE` (MIT), `THIRD_PARTY_NOTICES.md` (PyMuPDF AGPL-3.0, Tesseract-Sprachdaten
  Apache-2.0, spaCy/Modell/tkinterdnd2 MIT), `.gitattributes` (CRLF für .bat),
  `.gitignore`, GitHub-Action mit pytest auf Ubuntu und Windows, Testsuite `tests/`.
- Code in das Paket `anonymisierer/` aufgeteilt; `pdf_anonymisierer.py` bleibt Startskript.

## [0.1.0] – 2026-07-03

- Erste Veröffentlichung: eine Datei `pdf_anonymisierer.py` mit Erkennung, Schwärzung,
  OCR und Oberfläche; `Installieren.bat`, `EXE-bauen.bat`, README.
