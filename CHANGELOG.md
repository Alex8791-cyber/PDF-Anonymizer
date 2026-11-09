# Änderungen

Alle nennenswerten Änderungen am PDF-Anonymisierer. Das Format folgt
[Keep a Changelog](https://keepachangelog.com/de/1.1.0/); die Versionsnummer steht in
`anonymisierer/__init__.py`.

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
