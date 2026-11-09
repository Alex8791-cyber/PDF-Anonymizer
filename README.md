# PDF-Anonymisierer

**Personenbezogene Daten in PDFs finden und durch Platzhalter ersetzen – lokal, ohne Cloud.**

Ein Windows-Programm für Versicherungsmakler und andere Büros, die Dokumente
(Anträge, Policen, Schadenmeldungen, Schreiben – auch eingescannte) an KI-Dienste
wie ChatGPT oder Claude geben möchten, ohne Kundendaten preiszugeben. Das Programm
sucht Namen, Adressen, IBANs, Nummern usw., zeigt alle Funde zur Prüfung an und
entfernt sie dann **wirklich** aus der PDF (echte PDF-Redaction, keine schwarzen Balken
über Text, der darunter weiterlebt).

Was dabei entsteht, ist eine **Pseudonymisierung**: Aus „Max Mustermann“ wird
`[PERSON A]`, aus der IBAN `[IBAN]`. Die KI kann das Dokument weiterhin sinnvoll
auswerten („Person A ist Versicherungsnehmer, Person B die Ehefrau“), aber ohne
echte Daten. Keine automatische Erkennung ist vollständig – die Prüfliste vor dem
Schwärzen und ein Blick ins Ergebnis bleiben Pflicht (siehe
[Wichtiger Hinweis](#wichtiger-hinweis-bitte-lesen)).

Läuft zu 100 % lokal: Zur Laufzeit verlassen keine Daten den Rechner. Nur die
Installation lädt einmalig Pakete aus dem Internet.

## Inhalt

- [Was wird erkannt?](#was-wird-erkannt)
- [Was NICHT erkannt wird](#was-nicht-erkannt-wird)
- [Voraussetzungen](#voraussetzungen)
- [Installation (Windows)](#installation-windows)
- [Benutzung](#benutzung)
- [Ausgabedateien](#ausgabedateien)
- [Wichtiger Hinweis (bitte lesen)](#wichtiger-hinweis-bitte-lesen)
- [Weitergabe an Kollegen: die EXE-Version](#weitergabe-an-kollegen-die-exe-version)
- [Problemlösung](#problemlösung)
- [Technik](#technik)
- [Mitentwickeln und Tests](#mitentwickeln-und-tests)
- [Lizenz](#lizenz)

## Was wird erkannt?

Jede Kategorie lässt sich in der Oberfläche einzeln an- und abschalten. Die Tabelle
wird aus dem Code erzeugt (`python werkzeuge/readme_tabelle.py --schreiben`), damit
sie immer zum Programm passt.

<!-- TABELLE-ANFANG -->
| Kategorie | Beispiel | Wird ersetzt durch | Standard | Hinweis |
|---|---|---|---|---|
| Personennamen (KI-Erkennung) | Max Mustermann | `[PERSON A], [PERSON B] …` | an | KI-Modell (spaCy); gleiche Person = gleicher Platzhalter |
| IBANs | DE89 3704 0044 0532 0130 00 | `[IBAN]` | an | nur mit gültiger Prüfsumme |
| E-Mail-Adressen | max.mustermann@example.de | `[E-MAIL]` | an |  |
| Telefonnummern | 0171 2345678 | `[TELEFON]` | an |  |
| Geburtsdaten | geb. am 02.09.1983 | `[GEB-DATUM]` | an | Datum hinter „geb.“, „Geburtsdatum“ … |
| Straße + Hausnummer | Hauptstraße 12a | `[ADRESSE]` | an |  |
| PLZ + Ort | 90402 Nürnberg | `[PLZ ORT]` | an |  |
| Vertrags-/Kunden-/Schein-Nummern | Versicherungsschein-Nr. LV-2024-887766 | `[VERTRAGS-NR]` | an | Nummer hinter einem Etikett wie „Vertrags-Nr.“ |
| Sozialversicherungsnummern | 12 345678 A 123 | `[SV-NR]` | an |  |
| Steuer-IDs | 91064389278 | `[STEUER-ID]` | an | amtliche Prüfziffer, auch ohne Beschriftung |
| Kindergeldnummern | 009FK407160 | `[KINDERGELD-NR]` | an |  |
| Kfz-Kennzeichen | N-XY 123 | `[KENNZEICHEN]` | an |  |
| ALLE Datumsangaben (Vorsicht!) | 15.03.2024 | `[DATUM]` | aus | Vorsicht: auch Vertrags- und Briefdaten |
<!-- TABELLE-ENDE -->

Dazu kommen zwei eigene Listen in der Oberfläche:

- **IMMER schwärzen** – eigene Begriffe (z. B. ein Firmenname), die in jedem Dokument
  ersetzt werden (`[BEGRIFF]`).
- **NIE schwärzen** – Begriffe, die trotz Treffer stehen bleiben sollen (z. B. der
  eigene Maklername). Es zählt nur der ganze Begriff, nicht ein Teil davon.

Platzhalter sind konsistent: `[PERSON A]` bleibt im ganzen Dokument dieselbe Person,
auch in Schreibweisen wie „Mustermann, Max“ oder „MAX MUSTERMANN“. Mehrere Personen
mit gleichem Nachnamen (Familie) bekommen eigene Buchstaben.

## Was NICHT erkannt wird

Bitte vor dem Einsatz lesen – das sind die Grenzen des Werkzeugs:

- **Diagnosen, Krankheiten, Medikamente** – medizinische Angaben werden nicht gesucht.
- **Beruf, Arbeitgeber, Familienstand, Einkommen** – bleiben stehen.
- **Unterschriften, Handschrift, Stempel** – die Texterkennung (OCR) liest nur
  gedruckten Text; Handschriftliches wird weder erkannt noch entfernt.
- **Fotos und Grafiken** – Gesichter, Ausweiskopien oder eingebettete Bilder werden
  nicht geschwärzt (außer dem Bildbereich direkt unter einem erkannten Text).
- **Ungewöhnliche Schreibweisen** – seltene Namen, Namen in Großbuchstaben mitten im
  Fließtext, ausländische Adressformate oder sehr schlechte Scans können durchrutschen.
- **Andere Kennnummern** – Krankenversichertennummer, Fahrzeug-Identnummer,
  Ausweisnummer u. Ä. werden nicht gesondert erkannt (ggf. über „IMMER schwärzen“).

Bei Scans gilt zusätzlich: Seiten mit sehr wenig erkennbarem Text werden ausdrücklich
als Warnung gemeldet („blinder Fleck“) statt still übersprungen. Das Ergebnis solcher
Seiten muss von Hand geprüft werden.

## Voraussetzungen

- Windows 10 oder 11, **64-Bit (x64)**. ARM64-Geräte (Snapdragon, Surface Pro X) werden
  nicht unterstützt; 32-Bit-Windows ebenfalls nicht.
- Python 3.10 bis 3.15 – wird vom Installationsskript automatisch mitinstalliert
  (Python 3.12, nur für das eigene Benutzerkonto, keine Administratorrechte nötig).
- Etwa 1 GB freier Speicher (Sprachmodell und Bibliotheken), Internet nur während der
  Installation.
- Für eingescannte PDFs ist **keine** zusätzliche Software nötig: Die Texterkennung
  (Tesseract) steckt in PyMuPDF, die deutsche Sprachdatei liegt im Ordner `tessdata`
  bei.

## Installation (Windows)

1. Auf der GitHub-Seite oben rechts **„Code“ → „Download ZIP“** wählen. Die Datei heißt
   `PDF-Anonymizer-main.zip`.
2. Rechtsklick auf die ZIP → **„Alle extrahieren…“**. Windows legt dabei einen Ordner
   `PDF-Anonymizer-main` an, in dem **noch einmal** ein Ordner `PDF-Anonymizer-main`
   liegt – das ist normal. Den inneren Ordner kann man an einen beliebigen Ort
   verschieben, z. B. nach `Dokumente\PDF-Anonymisierer`. (Nicht aus der ZIP heraus
   starten, ohne vorher zu entpacken.)
3. Doppelklick auf **`Installieren.bat`**.
   - Erscheint **„Datei öffnen – Sicherheitswarnung“** („Der Herausgeber konnte nicht
     verifiziert werden“): auf **„Ausführen“** klicken. Windows zeigt das bei jeder
     aus dem Internet geladenen Skriptdatei.
   - Erscheint **„Der Computer wurde durch Windows geschützt“** (SmartScreen): auf
     **„Weitere Informationen“** und dann **„Trotzdem ausführen“** klicken.
   - Das schwarze Fenster offen lassen, bis **„Fertig“** erscheint. Beim ersten Mal
     dauert es einige Minuten (ca. 300 MB Download).
4. Das Skript erledigt in **einem** Lauf:
   1. Python finden oder installieren (Python 3.12 über den Windows-Paketmanager
      `winget`; ohne Administratorrechte),
   2. Rechner prüfen (64-Bit, Prozessor),
   3. Pakete installieren (PyMuPDF, spaCy, tkinterdnd2 und das deutsche Sprachmodell
      aus `requirements.txt`),
   4. Installation prüfen,
   5. Desktop-Verknüpfung **„PDF-Anonymisierer“** anlegen.

   Jeder Schritt wird geprüft. Geht etwas schief, nennt das Skript die wahrscheinliche
   Ursache (kein Internet, Firmen-Proxy, ARM64, fehlende Rechte …) und es erscheint
   **kein** „Fertig“.
5. Starten: Doppelklick auf die Desktop-Verknüpfung oder auf **`Starten.bat`** im
   Programmordner. Wird der Ordner später verschoben, einfach `Installieren.bat` noch
   einmal ausführen (geht dann schnell, es wird nichts erneut heruntergeladen).

Für Büros, in denen Python nicht installiert werden darf oder das Internet gefiltert
ist, gibt es die [EXE-Version](#weitergabe-an-kollegen-die-exe-version).

## Benutzung

1. PDFs oder ganze Ordner (inkl. Unterordner) in die blaue Fläche ziehen – oder über
   „Dateien auswählen“ / „Ordner auswählen“ hinzufügen.
2. Kategorien prüfen, bei Bedarf Begriffe in „IMMER schwärzen“ / „NIE schwärzen“
   eintragen.
3. **Analysieren** klicken. Die Fundliste zeigt je Datei alle Treffer mit Kategorie,
   gefundenem Text, Seite(n), Anzahl, Kontext und Platzhalter.
4. Liste prüfen: Ein Klick auf das Häkchen schaltet einen Fund an oder aus; „alle
   an/aus“ gibt es je Datei und je Kategorie.
5. **Schwärzen** klicken. Fortschritt und Warnungen stehen im Protokoll; am Ende fasst
   ein Dialog zusammen, wie viele Warnungen es gab und welche Dateien geprüft werden
   müssen. „Ordner öffnen“ führt direkt zum Ergebnis.
6. Das Ergebnis **stichprobenartig öffnen**, bevor es an einen KI-Dienst geht.

Während eines Laufs sind die Eingaben gesperrt; „Abbrechen“ beendet den Lauf, ohne
halbe Ausgabedateien zu hinterlassen. Einstellungen (Kategorien, Listen, Fenstergröße)
werden unter `%APPDATA%\PDF-Anonymisierer\einstellungen.json` gespeichert.

## Ausgabedateien

Die Originale bleiben unverändert. Neben jeder Eingabedatei entsteht ein Unterordner
`anonymisiert` (oder ein selbst gewählter Zielordner) mit:

| Datei | Bedeutung |
|---|---|
| `anonym_01.pdf`, `anonym_02.pdf`, … | Die geschwärzten PDFs. Die Namen sind absichtlich neutral – der Original-Dateiname (oft ein Kundenname!) soll nicht mit zur KI wandern. Bestehende Dateien werden nie überschrieben, es wird immer die nächste freie Nummer genommen. |
| `_zuordnung.txt` | Welche Ausgabe zu welchem Original gehört, z. B. `anonym_01.pdf  <-  Antrag_Mustermann.pdf  (2026-11-09 14:32)`. Diese Datei bleibt im Büro und wird **nicht** weitergegeben. |
| `anonym_03_PRUEFEN.pdf` | Die eingebaute Selbstkontrolle hat nach dem Schwärzen noch Fundtext in der Ausgabe gefunden (z. B. in einem schlechten Scan). Diese Datei **unbedingt von Hand prüfen**, bevor sie das Haus verlässt. |

Weitere Eigenschaften der Ausgabe: Formularfelder und Anmerkungen werden vor der Analyse
in den Seiteninhalt eingebrannt (damit auch Feldinhalte geprüft werden), Metadaten
(Autor, Titel, XMP), Lesezeichen, Links, eingebettete Dateien und Vorschaubilder werden
entfernt, bei Scans werden die Bildpixel unter der Fundstelle gelöscht. Konnte kein
einziger angehakter Fund im Dokument lokalisiert werden, entsteht **keine** Ausgabedatei
und das Protokoll warnt.

## Wichtiger Hinweis (bitte lesen)

- Das Programm **pseudonymisiert**. Eine Person kann aus dem Zusammenhang (Beruf,
  Wohnort im Fließtext, Diagnose, Datumskombinationen) weiterhin erkennbar sein. Ob
  ein Dokument weitergegeben werden darf, muss im Einzelfall entschieden werden – die
  Verantwortung für die datenschutzkonforme Weitergabe bleibt beim Nutzer.
- Keine automatische Erkennung ist zu 100 % zuverlässig. Die Fundliste ansehen, das
  Ergebnis stichprobenartig öffnen, Warnungen im Protokoll ernst nehmen – insbesondere
  bei Scans und bei Dateien mit `_PRUEFEN` im Namen.
- `_zuordnung.txt` enthält die Originalnamen und gehört nicht zur KI.
- Bei Fehlern schreibt das Programm eine `fehler.log` (siehe
  [Problemlösung](#problemlösung)); sie kann Dateipfade und damit Kundennamen enthalten
  – vor dem Weiterleiten prüfen.

## Weitergabe an Kollegen: die EXE-Version

`EXE-bauen.bat` erzeugt mit PyInstaller einen eigenständigen Programmordner
`dist\PDF-Anonymisierer\` (mit `PDF-Anonymisierer.exe`, Sprachmodell und
OCR-Sprachdatei) und packt ihn als `dist\PDF-Anonymisierer-<Version>-windows-x64.zip`.
Empfänger brauchen **weder Python noch Tesseract** – nur den entpackten Ordner.

- Den Bau macht ein Rechner, auf dem `Installieren.bat` gelaufen ist (x64-Windows).
  Das Skript prüft vorher, dass Sprachmodell und Sprachdatei vorhanden sind – eine EXE
  ohne Namenserkennung wird nicht gebaut.
- Weitergabe über **Netzlaufwerk, OneDrive/SharePoint oder USB**. Per E-Mail geht es
  nicht: Outlook blockiert `.exe`-Dateien, auch in ZIP-Archiven, und die Datei ist für
  Mail-Anhänge ohnehin zu groß (mehrere hundert MB).
- Der Ordner gehört zusammen: Die `.exe` allein läuft nicht; der Ordner `_internal`
  muss daneben liegen. Empfänger entpacken z. B. nach `Dokumente\PDF-Anonymisierer` und
  legen sich eine Verknüpfung auf `PDF-Anonymisierer.exe`.
- **SmartScreen:** Beim ersten Start erscheint „Der Computer wurde durch Windows
  geschützt“ → „Weitere Informationen“ → „Trotzdem ausführen“. Die EXE ist nicht
  signiert; die Warnung kommt nach jedem neuen Build wieder. Dauerhaft hilft nur eine
  Code-Signatur (Herausgeberzertifikat oder Azure Trusted Signing, kostenpflichtig;
  `signtool`-Aufruf steht am Ende von `EXE-bauen.bat`).
- **Firmennetze:** Bei AppLocker-/Defender-Richtlinien muss die IT die EXE freigeben.
  Virenscanner melden PyInstaller-Programme gelegentlich fälschlich – dann die Datei
  beim Hersteller als Fehlalarm melden.
- Die EXE läuft auf 64-Bit-Windows (x64); auf ARM64-Geräten nur unter Windows 11 in der
  x64-Emulation. Die Versionsnummer steht im Fenstertitel und in den Dateieigenschaften
  der EXE.
- Lizenz bei Weitergabe: Der Ordner enthält PyMuPDF (AGPL-3.0). Innerhalb des eigenen
  Unternehmens ist das unkritisch; bei Weitergabe an Dritte `THIRD_PARTY_NOTICES.md`
  und den Link zu diesem Repository mitgeben (siehe [Lizenz](#lizenz)).

## Problemlösung

| Symptom | Ursache und Abhilfe |
|---|---|
| `Installieren.bat` meldet „Pakete konnten nicht installiert werden“ | Die eigentliche pip-Meldung steht darüber. **Kein Internet** → Verbindung prüfen. **`CERTIFICATE_VERIFY_FAILED` / `ProxyError`** → Firmen-Proxy oder TLS-Prüfung; IT bitten, `pypi.org`, `files.pythonhosted.org` und `github.com` freizugeben, oder die EXE-Version nutzen. **`No matching distribution found`** → ARM64-Gerät oder 32-Bit-Python (nicht unterstützt). **`PermissionError` / `Access is denied`** → Ordner z. B. nach `Dokumente` verschieben, Virenscanner prüfen. |
| „Sprachmodell konnte nicht geladen werden“ | Das Modell kommt von `github.com`. Im Firmennetz gesperrt → einmalig über ein anderes Netz (Hotspot) installieren oder die EXE-Version nutzen. Ohne Modell gibt es keine Namenserkennung, deshalb bricht die Installation hier bewusst ab. |
| „Python konnte nicht automatisch installiert werden“ | `winget` fehlt oder ist gesperrt, oder `python` ist nur der Store-Alias von Windows. Python 3.12 (64-Bit) von [python.org](https://www.python.org/downloads/windows/) installieren (Haken „Add python.exe to PATH“), dann `Installieren.bat` erneut starten. Den Store-Alias schaltet man unter Einstellungen → Apps → Erweiterte App-Einstellungen → „Aliase für die App-Ausführung“ aus. |
| Keine Desktop-Verknüpfung, obwohl alles andere lief | PowerShell ist durch Firmenrichtlinien eingeschränkt. Programm über `Starten.bat` starten (Rechtsklick → „Senden an“ → „Desktop (Verknüpfung erstellen)“). |
| Doppelklick auf die Verknüpfung – nichts passiert | Ordner verschoben oder Python aktualisiert. `Installieren.bat` erneut ausführen, oder `Starten.bat` benutzen. Steht in `fehler.log` etwas? (siehe unten) |
| Programm meldet „Namenserkennung inaktiv“ | Sprachmodell fehlt. `Installieren.bat` erneut ausführen; in der EXE-Version eine neue EXE anfordern. |
| OCR liest Scans auf Englisch / Umlaute falsch | Die Datei `tessdata\deu.traineddata` fehlt im Programmordner (muss mit entpackt werden). |
| Fenster zu groß für den Bildschirm | Das Fenster passt sich der Bildschirmgröße an und ist ab ca. 640 × 520 Pixel nutzbar; bei sehr kleinen Bildschirmen startet es maximiert. |
| `fehler.log` finden | Liegt neben `pdf_anonymisierer.py` (bzw. neben der EXE), wenn der Ordner beschreibbar ist, sonst unter `%LOCALAPPDATA%\PDF-Anonymisierer\fehler.log`. Der Fehlerdialog nennt den genauen Pfad. |
| Für Rückfragen | `python werkzeuge\pruefe_installation.py` im Programmordner ausführen und die Ausgabe mitschicken (Python-Version, Pakete, Sprachdatei, Log-Pfad). |

## Technik

- **Python 3.10–3.15**, Oberfläche mit tkinter (+ tkinterdnd2 für Drag & Drop).
- **PyMuPDF** (MuPDF) für Textextraktion, echte Redaction (`apply_redactions` mit
  Bildpixel-Löschung), Entfernen von Metadaten/Anmerkungen/Links/Lesezeichen und für die
  eingebaute Tesseract-OCR; deutsche Sprachdatei `tessdata/deu.traineddata`
  (tessdata_fast) liegt im Repository.
- **spaCy** mit dem Modell `de_core_news_md` für Personennamen; feste Pseudonyme je
  Person, Varianten und Namensbestandteile werden zusammengeführt.
- **Muster mit Validierung** statt blindem Regex: IBAN-Prüfsumme (Mod 97),
  Steuer-ID-Prüfziffer (§ 139b AO), Etiketten für Vertragsnummern, Ganzwort-Prüfung bei
  der Schwärzung (ein Fund darf nicht Teil eines längeren Wortes sein).
- **Selbstkontrolle:** Nach dem Schwärzen wird die Ausgabe erneut durchsucht (bei Scans
  per erneuter OCR); Reste führen zum Dateinamen `_PRUEFEN`.
- OCR läuft in eigenen Prozessen, die Oberfläche bleibt bedienbar; Fortschritt je Seite,
  Abbrechen jederzeit.
- Code und Oberfläche sind deutsch; Paketaufbau: `anonymisierer/` mit `muster.py`
  (Regex + Kategorien), `namen.py` (spaCy), `analyse.py`, `ocr.py`, `schwaerzung.py`,
  `dateien.py`, `gui.py`; Startskript `pdf_anonymisierer.py`.

## Mitentwickeln und Tests

```bash
python -m pip install --only-binary=:all: -r requirements.txt -r requirements-dev.txt
python -m pytest -q tests/
```

Unter Linux braucht die OCR die Sprachdaten (`TESSDATA_PREFIX` auf den Ordner `tessdata`
setzen) und die Oberflächentests ein Display (`xvfb-run`). Die GitHub-Action
`.github/workflows/tests.yml` führt die Tests auf Ubuntu und Windows aus.
Versionsnummer: `anonymisierer/__init__.py` (`__version__`), gespiegelt in
`werkzeuge/version_info.txt` und `CHANGELOG.md`.

## Lizenz

Der Code dieses Projekts steht unter der **MIT-Lizenz** (siehe [LICENSE](LICENSE)) –
Nutzung auf eigene Verantwortung, ohne Gewähr.

Enthaltene bzw. beim EXE-Bau gebündelte Komponenten haben eigene Lizenzen, Details in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md):

- **PyMuPDF / MuPDF** (Artifex): **AGPL-3.0** oder kommerzielle Lizenz. Eine
  weitergegebene EXE enthält PyMuPDF und wird damit insgesamt unter AGPL-Bedingungen
  weitergegeben: Empfänger haben Anspruch auf den Quelltext (dieses öffentliche
  Repository erfüllt das) und auf den Lizenztext. Firmeninterne Nutzung löst keine
  Pflichten aus; bei kommerzieller Weitergabe an Dritte die Artifex-Lizenz prüfen.
- **Tesseract-Sprachdatei** `tessdata/deu.traineddata` (tessdata_fast): Apache-2.0.
- **spaCy** und das Modell **de_core_news_md**: MIT.
- **tkinterdnd2** / TkDND: MIT.

Hinweis zur Historie: Der erste Commit enthielt eine Apache-2.0-LICENSE, die danach
gelöscht wurde; die README nannte MIT. Seit Version 0.2.0 liegt der MIT-Text als
`LICENSE` bei. Änderungen stehen in [CHANGELOG.md](CHANGELOG.md).
