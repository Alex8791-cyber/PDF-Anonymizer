# PDF-Anonymisierer

**Personenbezogene Daten in PDFs finden und durch Platzhalter ersetzen – lokal, ohne Cloud.**

Ein Windows-Programm für Versicherungsmakler und andere Büros, die Dokumente
(Anträge, Policen, Schadenmeldungen, Schreiben – auch eingescannte oder abfotografierte)
an KI-Dienste wie ChatGPT oder Claude geben möchten, ohne Kundendaten preiszugeben. Das
Programm sucht Namen, Anschriften, IBANs, Nummern usw., zeigt alle Funde in einer Liste und
in einer Vorschau zur Prüfung an und entfernt sie dann **wirklich** aus der PDF (echte
PDF-Schwärzung, keine schwarzen Balken über Text, der darunter weiterlebt).

Was dabei entsteht, ist eine **Pseudonymisierung**: Aus „Max Mustermann“ wird
`[PERSON A]`, aus der IBAN `[IBAN]`. Die KI kann das Dokument weiterhin sinnvoll
auswerten („Person A ist Versicherungsnehmer, Person B die Ehefrau“), aber ohne
echte Daten. Keine automatische Erkennung ist vollständig. Deshalb heißt jede Ausgabe
standardmäßig zunächst `anonym_NN_PRUEFEN.pdf` und wird erst weitergegeben, wenn Sie sie in
der Vorschau angesehen und freigegeben haben (siehe
[Prüfen und freigeben](#prüfen-und-freigeben) und
[Wichtiger Hinweis](#wichtiger-hinweis-bitte-lesen)).

Läuft zu 100 % lokal: Zur Laufzeit verlassen keine Daten den Rechner. Nur die
Installation lädt einmalig Pakete aus dem Internet.

## Inhalt

- [Wichtiger Hinweis (bitte lesen)](#wichtiger-hinweis-bitte-lesen)
- [Was wird erkannt?](#was-wird-erkannt)
- [Was NICHT erkannt wird](#was-nicht-erkannt-wird)
- [Voraussetzungen](#voraussetzungen)
- [Installation (Windows)](#installation-windows)
- [Benutzung](#benutzung)
- [Prüfen und freigeben](#prüfen-und-freigeben)
- [Ausgabedateien](#ausgabedateien)
- [Wo das Programm Dateien ablegt](#wo-das-programm-dateien-ablegt)
- [Weitergabe an Kollegen: die EXE-Version](#weitergabe-an-kollegen-die-exe-version)
- [Problemlösung](#problemlösung)
- [Technik](#technik)
- [Mitentwickeln und Tests](#mitentwickeln-und-tests)
- [Lizenz](#lizenz)

## Wichtiger Hinweis (bitte lesen)

- Das Programm **pseudonymisiert**, es anonymisiert nicht. Eine Person kann aus dem
  Zusammenhang weiterhin erkennbar sein – aus Beträgen, Freitext, Datumskombinationen und,
  je nach Schutzstufe, aus Beruf, Orten oder Diagnosen. Pseudonymisierte Dokumente bleiben
  personenbezogene Daten: Für die Weitergabe an einen KI-Dienst braucht es weiterhin eine
  Rechtsgrundlage und in der Regel einen Auftragsverarbeitungsvertrag. Ob ein Dokument
  weitergegeben werden darf, muss im Einzelfall entschieden werden – die Verantwortung für
  die datenschutzkonforme Weitergabe bleibt beim Nutzer.
- Keine automatische Erkennung ist zu 100 % zuverlässig – auch eine Ausgabe ohne Warnung
  kann noch Personendaten enthalten. Deshalb **jede Ausgabe in der Vorschau ansehen** und
  erst dann „Freigeben“ drücken. Hochgeladen wird nur, was im Ausgabeordner liegt und kein
  `_PRUEFEN` mehr im Namen trägt – nie das Original.
- **Unterschriften, Handschrift und Stempel werden nicht geschwärzt.** Gesichter erkennt das
  Programm nur als Lichtbild auf Ausweiskopien – und auch das nicht immer. Alles andere
  decken Sie in der Vorschau mit einem Rahmen selbst ab (siehe
  [Was NICHT erkannt wird](#was-nicht-erkannt-wird)).
- Freigeben geht nur, solange das Programm geöffnet ist und die Datei in der Liste steht.
  Vor dem Beenden also alle Ausgaben prüfen und freigeben (siehe
  [Prüfen und freigeben](#prüfen-und-freigeben)).
- Die Zuordnungsdatei (`_zuordnung_anonymisiert.txt` neben dem Ausgabeordner) enthält die
  Original-Dateinamen und gehört nicht zur KI.
- Ausgaben in Ordnern, die OneDrive, Dropbox o. Ä. synchronisieren, landen ebenfalls in der
  Cloud. Per Dateidialog geöffnete Dateien merkt sich Windows unter „Zuletzt verwendet“.
- Bei Fehlern schreibt das Programm eine `fehler.log` (siehe [Problemlösung](#problemlösung)).
  Ordner sind darin gekürzt, Dateinamen (oft mit Kundennamen) stehen aber drin – vor dem
  Weiterleiten prüfen.

Beim ersten Start zeigt das Programm diese Punkte als „Bitte vor der ersten Nutzung lesen“;
später jederzeit über Hilfe → „Hinweise vor der Nutzung …“ und Hilfe → „Was wird nicht
erkannt?“.

## Was wird erkannt?

### Schutzstufen

Über den Häkchen der Kategorien wählen Sie eine Schutzstufe. Die Häkchen folgen der Stufe;
die Wahl wird gespeichert.

| Schutzstufe | Was angehakt wird |
|---|---|
| Ausgewogen | Direkte Kennungen: Namen, Anschriften, Geburtsdaten, IBAN, BIC, E-Mail, Telefon, Vertrags-, Steuer-, Sozialversicherungs-, Krankenversicherten-, Ausweis- und Fahrzeugnummern, Kennzeichen … – mehr Zusammenhang für die KI. |
| **Hoch (Standard, empfohlen)** | Zusätzlich Beruf, Arbeitgeber, ausländische Anschriften und Orte ohne PLZ. |
| Maximal | Zusätzlich Diagnosen und Medikamente, jedes Datum, das mindestens 14 Jahre zurückliegt (außer Vertragsdaten), unbekannte Eigennamen bei Personen – und Bilder und Fotos werden abgedeckt (siehe [unten](#bilder-fotos-und-lichtbilder)). Größter Schutz, am wenigsten Zusammenhang für die KI. |
| Benutzerdefiniert | Erscheint, sobald Ihre Häkchen zu keiner Stufe passen, die mindestens so streng ist wie die zuletzt gewählte. Es gelten dann weiter deren Erkennungsregeln – wer in „Maximal“ die Diagnosen abwählt, behält also z. B. das Abdecken der Bilder. |

**Gesundheitsdaten** (Diagnosen, Medikamente) sucht das Programm in jeder Stufe. In
„Ausgewogen“ und „Hoch“ stehen sie aber **nicht angehakt** in der Fundliste (Zeichen ⚕) und
bleiben lesbar, solange Sie sie nicht anhaken – der Abschlussdialog der Analyse weist darauf
hin. In „Maximal“ sind sie angehakt.

Ändern Sie nach der Analyse die Schutzstufe, ein Häkchen, eine Liste oder die Kundenliste,
wird die Fundliste zurückgesetzt: Dann bitte erneut analysieren. In der Vorschau gesetzte
Markierungen gehen dabei verloren.

### Kategorien

Die Tabelle wird aus dem Code erzeugt (`python werkzeuge/readme_tabelle.py --schreiben`),
damit sie immer zum Programm passt. „Angehakt ab Stufe“ nennt die mildeste Schutzstufe, in
der die Kategorie angehakt ist („Ausgewogen“ heißt also: in jeder Stufe). Jedes Häkchen lässt
sich auch einzeln setzen.

<!-- TABELLE-ANFANG -->
| Kategorie | Beispiel | Wird ersetzt durch | Angehakt ab Stufe | Hinweis |
|---|---|---|---|---|
| Personennamen (KI-Erkennung) | Max Mustermann | `[PERSON A], [PERSON B] …` | Ausgewogen | KI-Modell (spaCy), Namenslisten und Regeln; gleiche Person = gleicher Platzhalter im Dokument |
| IBANs | DE89 3704 0044 0532 0130 00 | `[IBAN]` | Ausgewogen | auch mit falscher Prüfziffer, wenn sie eindeutig wie eine IBAN aussieht (Hinweis „Lesefehler?“) |
| E-Mail-Adressen | max.mustermann@example.de | `[E-MAIL]` | Ausgewogen |  |
| Telefonnummern | 0171 2345678 | `[TELEFON]` | Ausgewogen |  |
| Geburtsdaten | geb. am 02.09.1983 | `[GEB-DATUM]` | Ausgewogen | hinter „geb.“, „Geburtsdatum“ … oder direkt hinter einem Namen; in „Maximal“ zusätzlich jedes Datum, das mindestens 14 Jahre zurückliegt (außer Vertragsdaten) |
| Straße + Hausnummer, Postfach | Hauptstraße 12a | `[ADRESSE]` | Ausgewogen |  |
| PLZ + Ort | 90402 Nürnberg | `[PLZ ORT]` | Ausgewogen |  |
| Vertrags-/Kunden-/Schein-/Aktenzeichen | Versicherungsschein-Nr. LV-2024-887766 | `[VERTRAGS-NR]` | Ausgewogen | Nummer hinter einem Etikett wie „Vertrags-Nr.“ |
| Sozialversicherungsnummern | 12 345678 A 123 | `[SV-NR]` | Ausgewogen |  |
| Steuer-IDs | 91064389278 | `[STEUER-ID]` | Ausgewogen | ohne Beschriftung nur mit gültiger Prüfziffer |
| Steuernummern / USt-IdNr. | Steuernummer: 181/815/08155 | `[STEUER-NR]` | Ausgewogen | ohne Etikett nur mit Schrägstrichen; USt-IdNr. nur mit Etikett und nicht die einer Firma |
| Krankenversichertennummern | A123456780 | `[KV-NR]` | Ausgewogen |  |
| Kindergeldnummern | 009FK407160 | `[KINDERGELD-NR]` | Ausgewogen |  |
| Kfz-Kennzeichen | N-XY 123 | `[KENNZEICHEN]` | Ausgewogen |  |
| Fahrzeug-Identnummern (FIN) | WVWZZZ1JZXW000001 | `[FIN]` | Ausgewogen |  |
| Ausweis-/Pass-/Führerscheinnummern | Ausweisnummer: L01X00T47 | `[AUSWEIS-NR]` | Ausgewogen | mit Etikett; Ausweis- und Passnummern auch ohne (Prüfziffer); auf Ausweiskopien auch die maschinenlesbare Zone |
| SEPA-Mandatsreferenzen | Mandatsreferenz MR-2024-0815 | `[MANDATSREFERENZ]` | Ausgewogen | nur hinter einem Etikett |
| BIC (bei IBAN oder Etikett) | COBADEFFXXX | `[BIC]` | Ausgewogen | hinter „BIC“, neben einer IBAN oder in eindeutiger Form (11 Zeichen auf „XXX“ oder mit Ziffer im Ortscode) |
| Kreditkartennummern | 4111 1111 1111 1111 | `[KREDITKARTE]` | Ausgewogen |  |
| Ausländische Anschriften und Kennzeichen | Kerkstraat 12, 1017 GC Amsterdam | `[AUSLAND]` | Hoch |  |
| Orte ohne PLZ (Ort-Datum-Zeile, Geburtsort) | Musterstadt, 03.04.2025 | `[ORT]` | Hoch | Ort-Datum-Zeile, „geboren in …“, „wohnhaft in …“ |
| Beruf (bei Personen) | Beruf: Elektriker | `[BERUF]` | Hoch | hinter „Beruf:“ oder im Satz („arbeitet als …“) |
| Arbeitgeber (bei Personen) | Arbeitgeber: Muster Bau GmbH | `[ARBEITGEBER]` | Hoch | hinter „Arbeitgeber:“ oder im Satz; bekannte Versicherer, Banken und Behörden bleiben stehen |
| Diagnosen, ICD-Codes (Gesundheitsdaten) | Diagnose: Diabetes mellitus (E11.9) | `[DIAGNOSE]` | Maximal | nur bekannte Begriffe und ICD-Codes mit Gesundheitsbezug; in „Ausgewogen“ und „Hoch“ nur angeboten (⚕, nicht angehakt) |
| Medikamente (Gesundheitsdaten) | Medikation: Metformin 500 mg | `[MEDIKAMENT]` | Maximal | nur bekannte Begriffe mit Gesundheitsbezug; in „Ausgewogen“ und „Hoch“ nur angeboten (⚕, nicht angehakt) |
| ALLE Datumsangaben (Vorsicht!) | 15.03.2024 | `[DATUM]` | – (nur von Hand) | Vorsicht: auch Vertrags- und Briefdaten |
<!-- TABELLE-ENDE -->

Weitere Platzhalter ohne eigenes Häkchen:

| Platzhalter | Wofür |
|---|---|
| `[FAMILIE A]` | ein allein stehender Nachname, den mehrere Personen im Dokument tragen (die Personen selbst behalten ihre eigenen Buchstaben) |
| `[TITEL]` | Inhalt eines Formularfelds „Titel“ (z. B. „Dipl.-Ing.“) |
| `[BEGRIFF]` | eigener Begriff aus „IMMER schwärzen“ oder „überall in diesem Dokument schwärzen“ (Vorschau) |
| `[GESCHWÄRZT]` | von Ihnen in der Vorschau angeklicktes Wort oder mit einem Rahmen markierte Fläche |
| `[LICHTBILD]` | Lichtbild auf einer Ausweiskopie (jede Schutzstufe) |
| `[BILD]` | eingebettetes Bild auf einer Textseite (nur „Maximal“) |
| `[FOTO]` | Fotobereich auf einer Scan-Seite oder einem Foto (nur „Maximal“) |

Dazu kommen zwei eigene Listen in der Oberfläche:

- **IMMER schwärzen** – eigene Begriffe (z. B. ein Firmenname), die in jedem Dokument
  ersetzt werden (`[BEGRIFF]`).
- **NIE schwärzen** – Begriffe, die trotz Treffer stehen bleiben sollen (z. B. der eigene
  Maklername). Es zählt nur der ganze Begriff (mindestens 3 Zeichen), nicht ein Teil davon;
  Nummern gelten auch mit anderen Leerzeichen („DE89 3704 …“ = „DE893704…“).

Platzhalter sind konsistent: `[PERSON A]` bleibt im ganzen Dokument dieselbe Person, auch in
Schreibweisen wie „Mustermann, Max“ oder „MAX MUSTERMANN“. Mehrere Personen mit gleichem
Nachnamen (Familie) bekommen eigene Buchstaben. Die Buchstaben gelten je Dokument: Dieselbe
Person kann in zwei Dokumenten verschiedene Buchstaben tragen.

Weitere Regeln:

- **Weitergabe im Lauf:** Namen und Nummern, die in einem Dokument erkannt sind, sucht das
  Programm auch in den anderen Dokumenten derselben Analyse (Hinweis „aus einem anderen
  Dokument dieses Laufs übernommen“). Was Sie abgewählt haben, bleibt abgewählt.
- **Firmenanschriften** in Briefköpfen und Fußzeilen (z. B. des Versicherers) bleiben stehen;
  sie stehen als nicht angehakter Fund „vermutlich Firmenanschrift – nicht geschwärzt, bitte
  prüfen“ in der Liste. Die Anschrift einer Person im eigenen Briefkopf (z. B. Selbständige)
  wird geschwärzt.
- **Versteckte Teile** der Datei – Metadaten, Lesezeichen, Anhänge, Formulardaten, Skripte –
  prüft die Analyse mit denselben Regeln. Die Ausgabe enthält sie nicht mehr.
- **Scans und Fotos** liest die eingebaute Texterkennung (OCR); schräge Scans werden gerade
  gerückt, gedrehte Seiten erkannt. Auf gelesenem Text gleicht das Programm typische
  Lesefehler aus (O/0, I/1 …); auf der Textebene einer echten PDF nicht.
- **Kundenliste (optional):** Über Menü „Kundenliste“ → „Kundenliste importieren …“ (oder
  „Importieren …“ in Schritt 2) lesen Sie eine CSV-Datei aus Ihrem Verwaltungsprogramm ein.
  Spalten werden möglichst automatisch erkannt, sonst ordnen Sie sie im Dialog zu. Gespeichert
  werden keine Namen oder Nummern im Klartext, nur Prüfwerte (gesalzene SHA-256-Hashes). Passt
  in einem Dokument ein starkes Merkmal eines Kunden (voller Name, Kunden-/Vertragsnummer,
  IBAN oder E-Mail), sucht das Programm alle seine Merkmale – auch Geburtsdatum, Anschrift,
  Telefon, Kennzeichen sowie Vor- und Nachname einzeln.

### Bilder, Fotos und Lichtbilder

- **Lichtbilder auf Ausweiskopien** (Personalausweis, Pass, Führerschein …) sucht das
  Programm in jeder Schutzstufe – auf Scan-Seiten und in eingebetteten Bildern. Ein Treffer
  steht als angehakter Fund „Lichtbild (Ausweis)“ in der Liste und wird mit `[LICHTBILD]`
  abgedeckt.
- Ist ein Foto auf einer ausweisartigen Fläche nicht sicher ein Lichtbild (z. B. eine stark
  vergrößerte Kopie), steht es **nicht angehakt** in der Liste: ansehen und anhaken, wenn es
  ein Gesicht zeigt.
- Bleibt ein Lichtbild sichtbar – abgewählt, unsicher und nicht angehakt, oder eine
  Ausweiskopie, auf der kein Lichtbild gefunden wurde –, heißt die Ausgabe immer `_PRUEFEN`,
  auch wenn „Freigabe vor Weitergabe“ ausgeschaltet ist.
- Andere Gesichter und Fotos (z. B. Schadenfotos) bleiben in „Ausgewogen“ und „Hoch“ stehen.
- **„Maximal“** deckt zusätzlich jedes Bild auf Textseiten ab (`[BILD]`) und die Fotobereiche
  auf Scan-Seiten und Fotos (`[FOTO]`). Ausnahmen: winzige Bilder (Symbole, Linien) bleiben;
  ein Bild, das mindestens die halbe Seite bedeckt (Hintergrund, fotografiertes Blatt), bleibt
  wie ein Scan stehen – abgedeckt werden nur die Fotos darin; Text, der über einem Bild liegt,
  bleibt lesbar. Jede Abdeckung lässt sich in Fundliste und Vorschau abwählen.
- **Unterschriften und Handschrift auf Scans bleiben auch in „Maximal“ stehen** – die
  Fotoerkennung blendet Striche bewusst aus. Nur eine Unterschrift, die als eigenes Bild in
  einer digitalen PDF steckt, deckt „Maximal“ als `[BILD]` ab.

## Was NICHT erkannt wird

Bitte vor dem Einsatz lesen – das sind die Grenzen des Werkzeugs:

- **Unterschriften, Handschrift, Stempel** – werden nicht geschwärzt, auf Scans auch in
  „Maximal“ nicht. Die Texterkennung (OCR) liest Handschrift nicht zuverlässig. Die
  Restrisiko-Prüfung meldet auf Scans nicht gelesene Tinte in Unterschriftsfeldern, neben
  Personenangaben und hinter Bankangaben als Verdacht; ein Unterschriftszug neben einem schon
  geschwärzten Namen gilt nicht als Verdacht. Als Linien gezeichnete Unterschriften, Stempel
  oder Logos in digitalen PDFs nennt nur ein Hinweis („Grafiken/Zeichnungen …, die nicht
  geprüft werden“). Abhilfe: in der Vorschau einen Rahmen darüberziehen.
- **Gesichter und Fotos** – gesucht werden nur Lichtbilder auf Ausweiskopien, und die nicht
  immer. Andere Gesichter und Fotos bleiben in „Ausgewogen“ und „Hoch“ stehen; in „Maximal“
  bleiben winzige Bilder, Bilder über mindestens die halbe Seite (nur die Fotos darin werden
  abgedeckt) und gezeichnete Grafiken.
- **Diagnosen, Krankheiten, Medikamente** – erkannt werden nur bekannte Begriffe aus den
  Wortlisten des Programms und ICD-10-Codes, und nur mit Gesundheitsbezug (z. B. hinter
  „Diagnose:“ oder „leidet an“). In „Ausgewogen“ und „Hoch“ sind sie nur angeboten (⚕, nicht
  angehakt) und bleiben lesbar, wenn Sie sie nicht anhaken.
- **Beruf und Arbeitgeber** – nur mit Etikett („Beruf:“, „Arbeitgeber:“) oder im Satz
  („arbeitet als …“) und erst ab „Hoch“. **Familienstand und Einkommen** werden nicht erkannt.
- **Nummern ohne Beschriftung** – SEPA-Mandatsreferenzen, USt-IdNr., Führerscheinnummern
  (außerhalb einer Führerscheinkopie), Steuernummern ohne Schrägstriche und BICs, die weder
  neben einer IBAN stehen noch eindeutig geformt sind (z. B. die kurze 8-Zeichen-Form), werden
  nur hinter einem Etikett gefunden („Mandatsreferenz“, „USt-IdNr.“, „Führerscheinnummer“,
  „Steuernummer“, „BIC“ …). Steht so eine Nummer nur ohne Beschriftung im Dokument, bleibt sie
  stehen – ebenso hausinterne Nummern ohne festes Format (ggf. über „IMMER schwärzen“ oder die
  Kundenliste). Ist sie an einer Stelle mit Etikett erkannt, wird sie auch an allen anderen
  Stellen des Dokuments geschwärzt. An ihrem Aufbau erkannt werden dagegen auch ohne Etikett:
  IBAN, Steuer-ID und Personalausweis- bzw. Passnummer (mit gültiger Prüfziffer),
  Krankenversicherten-, Fahrzeug-Ident- und Kreditkartennummern, Steuernummern mit
  Schrägstrichen, eine BIC in eindeutiger Form sowie auf Ausweiskopien die maschinenlesbare
  Zone (siehe Tabelle).
- **Geburtsdaten ohne Etikett** – erkannt hinter „geb.“, „Geburtsdatum“ … oder direkt hinter
  einem Namen. Das Geburtsdatum eines Kindes ohne Etikett (z. B. „Mitversichert: Tochter
  14.03.2015“) bleibt stehen, auch in „Maximal“, und die Restrisiko-Prüfung meldet es bewusst
  nicht (sonst wäre jedes jüngere Rechnungs- oder Schadendatum ein Verdacht). Bitte selbst
  darauf achten.
- **Ungewöhnliche Schreibweisen** – seltene oder unbekannte Namen ohne Zusammenhang,
  ausländische Anschriften in ungewohntem Format sowie Text in Bildern, Logos, Handyfotos und
  schlechten Scans können durchrutschen. Die Kundenliste hilft nur für bekannte Kunden – und
  nur, wenn im Dokument ein starkes Merkmal passt.
- **Unlesbare Textebene, XFA-Formulare** – Ist die Textebene einer PDF unlesbar (Zeichensalat),
  liest das Programm die Seite per OCR und schwärzt über die gelesenen Wörter; die unlesbare
  Textebene bleibt aber in der Ausgabe. Inhalte von XFA-Formularen lassen sich nicht prüfen.
  Beides macht die Ausgabe `_PRUEFEN`.

Kaum lesbare, unplausibel gelesene oder ganz ungelesene Scan-Seiten werden nicht still
übersprungen: Die Ausgabe heißt dann `_PRUEFEN`, und die Vorschau umrahmt die ganze Seite als
Verdacht – dort muss ein Mensch hinsehen.

## Voraussetzungen

- Windows 10 oder 11, **64-Bit (x64)**. 32-Bit-Windows geht nicht (für spaCy gibt es keine
  32-Bit-Pakete). ARM64-Geräte (Snapdragon, Surface Pro X) sind **ungetestet**: Für
  ARM64-Python 3.11 bis 3.15 gibt es inzwischen alle Pakete fertig (PyMuPDF dort 1.28.x),
  `Installieren.bat` versucht die Installation; die EXE-Version läuft unter Windows 11 in der
  x64-Emulation.
- Python 3.10 bis 3.15 – wird vom Installationsskript automatisch mitinstalliert
  (Python 3.12, nur für das eigene Benutzerkonto, keine Administratorrechte nötig).
  Mit Python 3.11 bis 3.14 kommt PyMuPDF 2.x, mit 3.10 und 3.15 PyMuPDF 1.28.x; verlangt wird
  mindestens PyMuPDF 1.24.10. Die GitHub-Action testet mit Python 3.12, also mit PyMuPDF 2.x.
- Etwa 1 GB freier Festplattenplatz (Sprachmodell und Bibliotheken), Internet nur während der
  Installation. Große Handyfotos und sehr große Seiten brauchen beim Lesen und Schwärzen
  deutlich mehr Arbeitsspeicher als gewöhnliche PDFs.
- Für eingescannte PDFs und Fotos ist **keine** zusätzliche Software nötig: Die
  Texterkennung (Tesseract) steckt in PyMuPDF, die deutsche Sprachdatei liegt im Ordner
  `tessdata` bei.

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
     dauert es einige Minuten (ca. 170 MB Download, dazu ggf. 25 MB für Python).
4. Das Skript erledigt in **einem** Lauf:
   1. Python finden oder installieren (Python 3.12 über den Windows-Paketmanager
      `winget`; ohne Administratorrechte),
   2. Rechner prüfen (64-Bit, Prozessor),
   3. Pakete installieren (PyMuPDF, spaCy, tkinterdnd2 und das deutsche Sprachmodell
      aus `requirements.txt`) – sind sie schon in passender Version da, wird nichts geladen,
   4. Installation prüfen,
   5. Desktop-Verknüpfung **„PDF-Anonymisierer“** anlegen.

   Jeder Schritt wird geprüft. Geht etwas schief, nennt das Skript die wahrscheinliche
   Ursache (kein Internet, Firmen-Proxy, gesperrtes github.com, fehlende Rechte …) und es
   erscheint **kein** „Fertig“.
5. Starten: Doppelklick auf die Desktop-Verknüpfung oder auf **`Starten.bat`** im
   Programmordner. Wird der Ordner später verschoben, einfach `Installieren.bat` noch
   einmal ausführen (geht dann schnell, es wird nichts erneut heruntergeladen).

**Ohne Zugang zu github.com (Offline-Weg für das Sprachmodell):** Das deutsche Sprachmodell
kommt von github.com, das manche Firmennetze sperren. Dann entweder die Installation einmalig
über ein anderes Netz laufen lassen (z. B. Handy-Hotspot) oder an einem anderen Rechner die
Datei `de_core_news_md-3.8.0-py3-none-any.whl` (44 MB) laden –
<https://github.com/explosion/spacy-models/releases/download/de_core_news_md-3.8.0/de_core_news_md-3.8.0-py3-none-any.whl>
–, sie unverändert in den Programmordner neben `Installieren.bat` legen und `Installieren.bat`
erneut starten. Das Modell wird dann aus der Datei installiert, die übrigen Pakete kommen wie
gewohnt von pypi.org.

Für Büros, in denen Python nicht installiert werden darf oder das Internet gefiltert
ist, gibt es die [EXE-Version](#weitergabe-an-kollegen-die-exe-version).

## Benutzung

Das Fenster führt in drei Schritten durch die Arbeit; unten stehen die Knöpfe
„Analysieren – Funde anzeigen“ (Alt+A), „Schwärzen starten“ (Alt+S) und „Ergebnisordner
öffnen“.

1. **Dateien hinzufügen (Schritt 1):** PDFs, Fotos oder ganze Ordner (inkl. Unterordner) in
   die blaue Fläche ziehen – oder „Dateien auswählen …“ / „Ordner auswählen …“. Dateien, die
   das Programm nicht prüfen kann, stehen mit Grund in der Zeile unter den Knöpfen
   („NICHT geprüft“) – siehe [Welche Dateien gehen?](#welche-dateien-gehen).
2. **Schutzstufe wählen (Schritt 2)** – Standard ist „Hoch“. Bei Bedarf Begriffe in
   „IMMER schwärzen“ / „NIE schwärzen“ eintragen oder die Kundenliste importieren.
3. **„Analysieren – Funde anzeigen“** klicken. Die Fundliste zeigt je Datei alle Treffer mit
   Kategorie, gefundenem Text, Seite(n), Anzahl, Kontext und Platzhalter. ⚑ markiert einen
   Fund mit Hinweis (z. B. „Prüfziffer ungültig (Lesefehler?)“), ⚕ nur angebotene
   Gesundheitsdaten.
4. **Liste prüfen (Schritt 3):** Kästchen oder Leertaste schaltet einen Fund an oder aus;
   „Alle an“ / „Alle aus“ und das Rechtsklick-Menü (z. B. „Kategorie … überall anhaken“)
   helfen bei vielen Funden. Doppelklick auf eine Datei (oder „Vorschau …“, Alt+V) öffnet die
   Vorschau „Geplante Schwärzung“: rot = wird geschwärzt, grau gestrichelt = wird nicht
   geschwärzt, blau = von Ihnen markiert. Ein Klick auf ein Wort schaltet es um, ein
   gezogener Rahmen schwärzt eine Fläche (Text und Bild); Rechtsklick bietet „überall in
   diesem Dokument schwärzen“ bzw. „nicht schwärzen“. So decken Sie Unterschriften,
   Handschrift, Stempel und Gesichter selbst ab.
5. **„Schwärzen starten“** klicken. Jede lesbare Datei bekommt eine Ausgabe – standardmäßig
   als `anonym_NN_PRUEFEN.pdf`. Der Abschlussdialog nennt die zu prüfenden Dateien mit Grund
   und bietet an, gleich die Vorschau der ersten zu öffnen.
6. **Jede Ausgabe prüfen und freigeben** – siehe [Prüfen und freigeben](#prüfen-und-freigeben).
   Erst danach hochladen, und nur aus dem Ausgabeordner.

Während eines Laufs sind die Eingaben gesperrt; „Abbrechen“ beendet den Lauf, ohne
halbe Ausgabedateien zu hinterlassen. Nach dem Schwärzen steht in der Zeile jeder Datei
„✔ fertig“ oder „⚠ prüfen“ mit dem Namen der Ausgabe, der Grund in der Spalte „Kontext“.
Menü Datei → „Protokoll speichern …“ sichert ein Laufprotokoll der Sitzung – ohne
Dokumentinhalte, Original-Dateinamen und Ordner.

Das Programm läuft nur einmal je Benutzer: Ein zweiter Start meldet „PDF-Anonymisierer läuft
bereits“ und öffnet kein zweites Fenster.

### Welche Dateien gehen?

- **PDFs**, auch eingescannte. Ob eine Datei eine PDF ist, prüft das Programm am Inhalt, nicht
  an der Endung.
- **Fotos und Bild-Scans** (JPEG, PNG, TIFF – auch mehrseitige Faxe –, BMP): Nach einer
  Rückfrage wandelt das Programm sie in eine PDF um und liest sie per Texterkennung. Die
  Ausgabe heißt wie gewohnt `anonym_NN.pdf` und liegt im Ordner `anonymisiert` neben dem
  Foto; sie muss **immer** in der Vorschau freigegeben werden.
- **PDFs mit Kennwort:** Das Programm fragt nach dem Kennwort („Überspringen“ ist möglich).
  Das Kennwort wird nicht gespeichert; die Ausgabe hat **kein** Kennwort mehr.
- **Nicht** verarbeitet werden Word-, Excel- und andere Office-Dateien, E-Mails, iPhone-Fotos
  (HEIC), WEBP- und GIF-Bilder – auch nicht, wenn sie die Endung `.pdf` tragen. Solche
  Dateien zuerst als PDF speichern (z. B. Drucken → „Microsoft Print to PDF“). Sie stehen als
  „NICHT geprüft“ in der Hinweiszeile und in den Abschlussdialogen.
- Eine Ausgabe des Programms (`anonym_…` oder Ordner `anonymisiert`) nimmt das Programm nur
  nach Rückfrage auf (Voreinstellung „Nein“) – zum Nachbessern besser das Original nehmen.

Umgewandelte Fotos und entschlüsselte PDFs liegen als Arbeitskopie nur während der Sitzung in
`%LOCALAPPDATA%\PDF-Anonymisierer\temp` – nie im Kundenordner. Sie werden beim Entfernen aus
der Liste und beim Beenden gelöscht, Reste nach einem Absturz beim nächsten Start.

## Prüfen und freigeben

Standardmäßig ist in Schritt 1 „Freigabe vor Weitergabe erforderlich“ eingeschaltet. Dann
heißt jede Ausgabe zunächst `anonym_NN_PRUEFEN.pdf` – auch eine, in der alles in Ordnung
scheint.

1. **Vorschau öffnen:** im Abschlussdialog „Ja“ – oder Doppelklick auf die Datei. Nach dem
   Schwärzen zeigt die Vorschau das „Ergebnis (Ausgabe)“.
2. **Jede Seite ansehen.** Graue Kästen mit Platzhalter sind geschwärzt. Orange markiert sind
   Verdachtsstellen der Restrisiko-Prüfung; eine ganze Seite ist umrahmt, wenn sie nicht
   verlässlich gelesen werden konnte.
3. **Steht noch etwas Persönliches da und ist es als Verdacht markiert:** in der Liste
   markieren und „Markierte nachschwärzen“. Es entsteht eine neue Ausgabe mit der nächsten
   freien Nummer; die alte wird gelöscht.
4. **Ist nichts Persönliches mehr zu sehen: „Freigeben“.** Die Datei heißt dann
   `anonym_NN.pdf` (dieselbe Nummer, wenn sie frei ist), die Zuordnungsdatei wird
   nachgetragen, und die Vorschau springt zur nächsten zu prüfenden Datei. Gibt es noch offene
   Verdachtsstellen, fragt das Programm vorher nach.
5. **Fehlt eine Schwärzung, die nicht als Verdacht markiert ist** (z. B. eine Unterschrift
   oder eine ganze unlesbare Seite): „Verwerfen (Ausgabe löschen)“ – die Vorschau zeigt dann
   wieder die geplante Schwärzung –, dort per Klick oder Rahmen nachbessern und erneut
   „Schwärzen starten“. Das schwärzt alle Dateien der Liste noch einmal (mit neuen Nummern);
   fertig freigegebene Dateien deshalb vorher mit „Datei aus Liste entfernen“ herausnehmen.

**Freigeben geht nur, solange die Datei in dieser Programmsitzung in der Liste steht.** Nach
einem Neustart, nach „Liste leeren“ oder „Datei aus Liste entfernen“ kann das Programm eine
ältere `_PRUEFEN`-Ausgabe nicht mehr freigeben. Dann das Original erneut hinzufügen,
analysieren, schwärzen und die neue Ausgabe prüfen und freigeben; die alte `_PRUEFEN`-Datei
nicht weitergeben. Beim Beenden warnt das Programm nicht vor Ausgaben, die noch nicht
freigegeben sind.

Fotos und Bild-Scans brauchen die Freigabe immer, ebenso eine Ausweiskopie mit sichtbarem
Lichtbild – auch wenn „Freigabe vor Weitergabe“ ausgeschaltet ist. Ohne die Option heißt eine
Ausgabe sonst nur dann `_PRUEFEN`, wenn das Programm einen Grund findet (siehe
[Ausgabedateien](#ausgabedateien)); geprüft werden sollte sie trotzdem.

## Ausgabedateien

Die Originale bleiben unverändert. Die einfache Regel lautet: **Hochladen nur aus dem
Ausgabeordner – nie das Original.** Dafür bekommt **jede** lesbare PDF eine bereinigte
Ausgabe, auch eine Datei, in der nichts zu schwärzen war (z. B. ein Bedingungswerk). Neben
jeder Eingabedatei entsteht ein Unterordner `anonymisiert`; mit „Alle Ergebnisse in einen
gemeinsamen Zielordner“ landen die Ausgaben direkt in diesem Ordner.

| Datei | Bedeutung |
|---|---|
| `anonym_01.pdf`, `anonym_02.pdf`, … | Freigegebene bzw. fertige Ausgaben. Die Namen sind absichtlich neutral – der Original-Dateiname (oft ein Kundenname!) soll nicht mit zur KI wandern. Bestehende Dateien werden nie überschrieben, es wird immer die nächste freie Nummer genommen. |
| `anonym_03_PRUEFEN.pdf` | Diese Ausgabe ist noch **nicht** zur Weitergabe freigegeben. Mit „Freigabe vor Weitergabe“ (Standard) heißt zunächst jede Ausgabe so; bei einer Datei ohne Fund steht dann „keine personenbezogenen Daten gefunden – Freigabe ausstehend“. Dazu kommen die Gründe unten. Erst in der Vorschau prüfen, ggf. nachschwärzen und dort „Freigeben“ drücken. |

Außerdem heißt eine Ausgabe immer `_PRUEFEN`, wenn mindestens einer dieser Gründe zutrifft
(der Grund steht in der Liste neben der Datei und im Abschlussdialog):

- Die Restrisiko-Prüfung meldet Verdacht oder ist ausgefallen, die Selbstkontrolle findet
  noch Fundtext, oder ein angehakter Fund war im Dokument nicht auffindbar.
- Die Datei ist ein umgewandeltes Foto oder ein Bild-Scan, oder ein Lichtbild auf einer
  Ausweiskopie ist nicht abgedeckt.
- Eine Scan-Seite ist kaum lesbar, die Texterkennung hat Buchstabensalat gelesen oder auf einer
  Seite, die nicht nachweislich leer ist, nichts gelesen – oder es ist gar kein Text lesbar.
- Die Textebene ist unlesbar, das Dokument ist ein XFA-Formular, oder eine Seite ist gedreht
  gespeichert und die Lage der Schwärzungen unsicher.
- Die Datei war beschädigt und wurde repariert, oder ein Bild darin ist beschädigt.
- Personendaten stehen nur in versteckten Teilen (Metadaten, Anhänge …), oder diese ließen
  sich nur teilweise entfernen.
- Die Namenserkennung ist inaktiv (Sprachmodell fehlt), eine Erkennungsregel oder die
  Bildprüfung ist ausgefallen.
- Auf einer Scan-Seite steht hinter einem Schlüsselwort wie „IBAN“ oder „Geburtsdatum“ ein
  Wert, der nicht geschwärzt ist (z. B. wegen eines Lesefehlers).
- Das Dokument liest sich beim Schwärzen anders als bei der Analyse, oder eine andere Warnung
  betrifft die Ausgabe.

Die Restrisiko-Prüfung meldet lieber zu viel als zu wenig: Viele `_PRUEFEN`-Dateien enthalten
kein echtes Leck. Umgekehrt heißt „fertig“ nicht fehlerfrei – angesehen wird jede Ausgabe.

**Keine Ausgabe** entsteht nur, wenn sich eine Datei nicht bearbeiten lässt: keine PDF,
Kennwort nicht eingegeben, Datei lässt sich nicht öffnen, Abbruch, eine Seite lässt sich weder
schwärzen noch als Bild neu erzeugen, die Datei musste erst beim Schwärzen repariert werden,
oder die Ausgabe ist nicht schreibbar. Das Programm nennt diese Dateien im Abschlussdialog unter
„OHNE Ausgabedatei“ – das Original dieser Dateien nicht weitergeben.

Was jede Ausgabe sonst noch auszeichnet:

- Formularfelder und Anmerkungen werden vor der Analyse in den Seiteninhalt eingebrannt
  (damit auch Feldinhalte geprüft werden).
- Entfernt werden versteckte Teile: Dateieigenschaften und XMP-Metadaten (auch an Seiten und
  Bildern), Lesezeichen, Links, eingebettete Dateien und Anhänge, Formular- und XFA-Daten,
  JavaScript und Aktionen, Seitenbeschriftungen, Strukturbaum und Ersatztexte, Ebenennamen,
  Miniaturbilder, Inhalte außerhalb des sichtbaren Bereichs, abgeschnittener Text sowie
  EXIF-/XMP-Daten in eingebetteten Fotos.
- Bilder, die keine Seite anzeigt (z. B. ein ungeschwärztes Original, das in der Datei noch
  mitgespeichert war), werden in jeder Schutzstufe geleert.
- Bei Scans werden die Bildpixel unter einer Fundstelle gelöscht, nicht nur übermalt.
  Geschwärzte Bilder werden wieder kompakt als JPEG gespeichert; Fotos über 24 Megapixel
  (z. B. Handyfotos mit 48 Megapixeln), in denen geschwärzt wurde, dabei auf 24 Megapixel
  verkleinert. Die Ausgabe ist deshalb nicht pixelgleich mit dem Original. Bilder ohne
  Schwärzung behalten ihre Auflösung.

Die **Zuordnungsdatei** – welche Ausgabe zu welchem Original gehört, z. B.
`anonym_01.pdf  <-  Antrag_Mustermann.pdf  (2026-11-09 14:32)` – liegt **neben** dem
Ausgabeordner, nicht darin: im Standardfall als `_zuordnung_anonymisiert.txt` neben den
Originalen, bei einem gemeinsamen Zielordner `D:\Upload` als `D:\_zuordnung_Upload.txt`. So
wird sie nicht versehentlich mit hochgeladen; sie enthält die Original-Dateinamen und bleibt
im Büro. Freigeben, Verwerfen und Nachschwärzen tragen sich dort selbst nach. Ist der
Zielordner ein ganzes Laufwerk oder eine Freigabe (z. B. `E:\` auf einem USB-Stick oder
`\\server\freigabe\`), gibt es kein „daneben“: Dann liegt sie im Einstellungsordner des
Programms, z. B. `%APPDATA%\PDF-Anonymisierer\Zuordnungen\_zuordnung_Laufwerk_E.txt` (der
genaue Ort steht im Protokoll). Eine `_zuordnung.txt` älterer Versionen im Ausgabeordner wird
beim nächsten Schwärzen übernommen und dort gelöscht – auch wenn sie im Editor in einer
anderen Kodierung (ANSI, „Unicode“) gespeichert wurde. Nur wenn nirgends daneben geschrieben
werden kann (z. B. schreibgeschützter Ordner), landet sie als `_zuordnung.txt` im
Ausgabeordner – dann warnt das Programm deutlich („ACHTUNG Zuordnungsdatei“), sie beim
Hochladen nicht mit auszuwählen.

## Wo das Programm Dateien ablegt

| Was | Wo |
|---|---|
| Ausgaben | Unterordner `anonymisiert` neben dem Original (bzw. direkt im gemeinsamen Zielordner): `anonym_NN.pdf` oder `anonym_NN_PRUEFEN.pdf` |
| Zuordnungsdatei | neben dem Ausgabeordner: `_zuordnung_<Name des Ausgabeordners>.txt`; bei einem Laufwerk oder einer Freigabe als Zielordner in `%APPDATA%\PDF-Anonymisierer\Zuordnungen`; nur notfalls (mit Warnung) als `_zuordnung.txt` im Ausgabeordner |
| Einstellungen (Schutzstufe, Kategorien, Listen, Zielordner, „Freigabe vor Weitergabe“, Fenstergröße, Hinweis gelesen) | `%APPDATA%\PDF-Anonymisierer\einstellungen.json` |
| Kundenliste (nur Prüfwerte, kein Klartext; unter Windows nur mit dem eigenen Windows-Konto verwendbar) | `%APPDATA%\PDF-Anonymisierer\kundenliste.dat` |
| Sperrdatei gegen einen zweiten Programmstart | `%APPDATA%\PDF-Anonymisierer\instanz.lock` |
| Arbeitskopien (umgewandelte Fotos, entschlüsselte PDFs) | `%LOCALAPPDATA%\PDF-Anonymisierer\temp\sitzung_…` – nur während der Sitzung |
| Kopie der OCR-Sprachdatei mit den Leseeinstellungen (keine Dokumentdaten) | `%TEMP%\pdf-anonymisierer-ocr` |
| `fehler.log` | Skript-Version: neben `pdf_anonymisierer.py`, wenn der Ordner beschreibbar ist, sonst `%LOCALAPPDATA%\PDF-Anonymisierer\fehler.log`; EXE-Version: immer dort |
| Laufprotokoll (Datei → „Protokoll speichern …“) | wo Sie es speichern; vorgeschlagen wird `PDF-Anonymisierer_Protokoll_<Datum>.txt` |

## Weitergabe an Kollegen: die EXE-Version

`EXE-bauen.bat` erzeugt mit PyInstaller einen eigenständigen Programmordner
`dist\PDF-Anonymisierer\` (mit `PDF-Anonymisierer.exe`, Sprachmodell, OCR-Sprachdatei, den
Wortlisten und allen Erkennungsmodulen sowie den Lizenztexten) und packt ihn als
`dist\PDF-Anonymisierer-<Version>-windows-x64.zip`. Empfänger brauchen **weder Python noch
Tesseract** – nur den entpackten Ordner.

- Den Bau macht ein Rechner, auf dem `Installieren.bat` gelaufen ist (x64-Windows).
  Das Skript prüft vorher, dass Sprachmodell und Sprachdatei vorhanden sind – eine EXE
  ohne Namenserkennung wird nicht gebaut. Fehlt nur PyInstaller, wird nur das nachgeladen
  (`requirements-dev.txt`), nicht erneut das Sprachmodell.
- Alternativ baut die GitHub-Action die EXE mit genau diesem Skript: unter „Actions“ →
  „Tests“ → „Run workflow“ oder automatisch für jeden Versions-Tag `v…`. Die ZIP liegt dann
  als Artefakt beim Lauf (vorher geprüft: Sprachmodell, Sprachdatei, Lizenztexte, Probestart).
- Weitergabe über **Netzlaufwerk, OneDrive/SharePoint oder USB**. Per E-Mail geht es
  nicht: Outlook blockiert `.exe`-Dateien, auch in ZIP-Archiven, und die Datei ist für
  Mail-Anhänge ohnehin zu groß (mehrere hundert MB).
- Der Ordner gehört zusammen: Die `.exe` allein läuft nicht; der Ordner `_internal`
  muss daneben liegen. Empfänger entpacken z. B. nach `Dokumente\PDF-Anonymisierer` und
  legen sich eine Verknüpfung auf `PDF-Anonymisierer.exe`. Fehlt im Ordner ein
  Erkennungsmodul oder das Sprachmodell, meldet das Programm das, statt still weniger zu
  erkennen (die Ausgaben heißen dann `_PRUEFEN`) – dann den Ordner vollständig neu entpacken.
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
- Lizenz bei Weitergabe: Der Ordner enthält PyMuPDF/MuPDF (AGPL-3.0). `EXE-bauen.bat` legt
  `LICENSE.txt`, `THIRD_PARTY_NOTICES.md`, `README.md` und den vollständigen AGPL-Text
  (`licenses\AGPL-3.0.txt`) in den Ordner – sie sind damit in der ZIP und bleiben beim
  Weitergeben dabei (nicht herauslöschen). Innerhalb des eigenen Unternehmens ist das
  unkritisch; bei Weitergabe an Dritte zusätzlich den Link zu diesem Repository mitgeben
  (siehe [Lizenz](#lizenz)).

## Problemlösung

| Symptom | Ursache und Abhilfe |
|---|---|
| `Installieren.bat` meldet „Pakete konnten nicht installiert werden“ | Die eigentliche pip-Meldung steht darüber. **Kein Internet** → Verbindung prüfen. **`CERTIFICATE_VERIFY_FAILED` / `ProxyError`** → Firmen-Proxy oder TLS-Prüfung; IT bitten, `pypi.org`, `files.pythonhosted.org` und `github.com` freizugeben, oder die EXE-Version nutzen. **`No matching distribution found`** → meist erreicht pip `pypi.org` nicht (Proxy, siehe davor); seltener gibt es für dieses Python bzw. diesen Prozessor kein fertiges Paket (z. B. ARM64 mit Python 3.10) → Python 3.12 (64-Bit) installieren oder die EXE-Version nutzen. **`PermissionError` / `Access is denied`** → Ordner z. B. nach `Dokumente` verschieben, Virenscanner prüfen. |
| „Sprachmodell konnte nicht installiert werden“ | Das Modell kommt von `github.com` – auch der zweite Versuch über `spacy download`. Im Firmennetz gesperrt → einmalig über ein anderes Netz (Hotspot) installieren, den [Offline-Weg](#installation-windows) nutzen (Datei `de_core_news_md-3.8.0-py3-none-any.whl` in den Programmordner legen) oder die EXE-Version nutzen. Ohne Modell gibt es keine Namenserkennung, deshalb bricht die Installation hier bewusst ab; schon installierte Pakete werden beim nächsten Lauf nicht neu geladen. |
| „Python konnte nicht automatisch installiert werden“ | `winget` fehlt oder ist gesperrt, oder `python` ist nur der Store-Alias von Windows. Python 3.12 (64-Bit) von [python.org](https://www.python.org/downloads/windows/) installieren (Haken „Add python.exe to PATH“), dann `Installieren.bat` erneut starten. Den Store-Alias schaltet man unter Einstellungen → Apps → Erweiterte App-Einstellungen → „Aliase für die App-Ausführung“ aus. |
| Keine Desktop-Verknüpfung, obwohl alles andere lief | PowerShell ist durch Firmenrichtlinien eingeschränkt. Programm über `Starten.bat` starten (Rechtsklick → „Senden an“ → „Desktop (Verknüpfung erstellen)“). |
| Doppelklick auf die Verknüpfung – nichts passiert | Ordner verschoben oder Python aktualisiert. `Installieren.bat` erneut ausführen, oder `Starten.bat` benutzen. Steht in `fehler.log` etwas? (siehe unten) |
| Meldung „PDF-Anonymisierer läuft bereits“ | Das Programm ist schon geöffnet (Taskleiste). Es läuft bewusst nur einmal je Benutzer, damit sich Einstellungen und Ausgabenummern nicht gegenseitig überschreiben. |
| Protokoll meldet „Namenserkennung inaktiv“ oder „Namenserkennung konnte nicht geladen werden“ | Sprachmodell fehlt oder ist beschädigt; Ausgaben heißen dann immer `_PRUEFEN`. Skript-Version: `Installieren.bat` erneut ausführen. EXE-Version: den kompletten Programmordner neu entpacken bzw. eine neue ZIP anfordern – der Ordner `_internal` gehört dazu. |
| Meldung „Erkennungsmodul … fehlt in diesem Programmordner“ | Der Programmordner ist unvollständig; die Angaben dieses Moduls wurden nicht gesucht, die Ausgaben heißen `_PRUEFEN`. Skript-Version: die ZIP neu herunterladen und entpacken, dann `Installieren.bat`. EXE-Version: den Ordner vollständig neu entpacken. |
| OCR liest Scans auf Englisch / Umlaute falsch | Die deutsche Sprachdatei fehlt: in der Skript-Version `tessdata\deu.traineddata` im Programmordner, in der EXE-Version `_internal\tessdata\deu.traineddata`. Den Ordner vollständig (neu) entpacken. |
| Datei wird als „keine PDF“ / „NICHT geprüft“ gemeldet | Das Programm prüft am Inhalt: Word, Excel, Mails, HEIC-, WEBP- und GIF-Bilder werden nicht verarbeitet – auch mit der Endung `.pdf`. Im Ursprungsprogramm als PDF speichern (z. B. Drucken → „Microsoft Print to PDF“) und diese PDF hinzufügen. |
| Fast jede Ausgabe heißt `_PRUEFEN` | So gewollt: „Freigabe vor Weitergabe erforderlich“ ist eingeschaltet (Standard). In der Vorschau prüfen und „Freigeben“ drücken. Ohne die Option heißt eine Ausgabe nur bei einem konkreten Grund `_PRUEFEN` (Fotos immer). |
| Eine `_PRUEFEN`-Datei lässt sich nicht (mehr) freigeben | Freigeben geht nur in der Sitzung, in der geschwärzt wurde, solange die Datei in der Liste steht. Original erneut hinzufügen, analysieren, schwärzen, prüfen und freigeben; die alte `_PRUEFEN`-Datei nicht weitergeben. |
| Zuordnungsdatei liegt nicht im Ausgabeordner | Sie liegt neben dem Ausgabeordner (`_zuordnung_anonymisiert.txt`), bei einem Laufwerk als Zielordner in `%APPDATA%\PDF-Anonymisierer\Zuordnungen` – siehe [Ausgabedateien](#ausgabedateien). |
| Geschwärztes Foto ist kleiner als das Original | Geschwärzte Bilder werden neu als JPEG gespeichert, Fotos über 24 Megapixel dabei auf 24 Megapixel verkleinert. |
| Fenster zu groß für den Bildschirm | Das Fenster passt sich der Bildschirmgröße an und ist ab ca. 640 × 520 Pixel nutzbar. Auf Laptop-Bildschirmen (z. B. 1366 × 768) und bei hoher Windows-Skalierung startet es maximiert. In einem niedrigen Fenster blendet das Programm Titel, Untertitel und den Bedienhinweis über der Fundliste aus, das Protokoll zeigt 3 statt 5 Zeilen; reicht der Platz dann noch nicht, wird der Hinweiskasten einzeilig (ein Klick zeigt alle Grenzen), „1 · PDF-Dateien“ und die blaue Fläche teilen sich eine Zeile und die Knöpfe werden flacher. Die Zeile mit den NICHT geprüften Dateien bleibt sichtbar; alle Hinweise stehen weiter unter Hilfe → „Was wird nicht erkannt?“ und „Hinweise vor der Nutzung …“. |
| `fehler.log` finden | Skript-Version: neben `pdf_anonymisierer.py`, wenn der Ordner beschreibbar ist, sonst `%LOCALAPPDATA%\PDF-Anonymisierer\fehler.log`. EXE-Version: immer `%LOCALAPPDATA%\PDF-Anonymisierer\fehler.log`, nie neben der EXE. Hilfe → „Ordner des Fehlerprotokolls öffnen“ öffnet den Ordner; der Fehlerdialog und Hilfe → „Über PDF-Anonymisierer“ nennen den genauen Pfad. Ordner sind darin gekürzt, Dateinamen nicht. |
| Für Rückfragen | Skript-Version: `python werkzeuge\pruefe_installation.py` im Programmordner ausführen und die Ausgabe mitschicken (Python-Version, Pakete und ob ihre Versionen zu `requirements.txt` passen, Sprachdatei, Log-Pfad). EXE-Version: den Text aus Hilfe → „Über PDF-Anonymisierer“ und die `fehler.log` mitschicken. Hilfreich ist auch das Laufprotokoll (Datei → „Protokoll speichern …“) – es enthält keine Dokumentinhalte und keine Original-Dateinamen. |

## Technik

- **Python 3.10–3.15**, Oberfläche mit tkinter (+ tkinterdnd2 für Drag & Drop).
- **PyMuPDF** (MuPDF) für Textextraktion, echte Schwärzung (`apply_redactions` mit
  Bildpixel-Löschung), das Entfernen versteckter Teile und für die eingebaute
  Tesseract-OCR; deutsche Sprachdatei `tessdata/deu.traineddata` (tessdata_fast) liegt im
  Repository. Die OCR läuft in eigenen Prozessen, die Oberfläche bleibt bedienbar; Fortschritt
  je Seite, Abbrechen jederzeit.
- **Seitenmodell** (`seitenmodell.py`): Text jeder Seite mit Lage – aus der Textebene oder per
  OCR. Analyse, Vorschau und Schwärzung arbeiten auf demselben Modell.
- **Erkennung:** Erkennungsregeln als Module in `anonymisierer/detektoren/` (Muster mit
  Prüfziffern, Tabellen, Formulare, Briefe und Anschriften, Ausweise, Faxkopf, Kammfelder,
  OCR-Lesefehler, Kundenliste); **spaCy** mit dem Modell `de_core_news_md` für Personennamen;
  eine Wissensbasis in `anonymisierer/daten/` (Wortlisten mit Vor- und Nachnamen, Berufen,
  Diagnosen, Medikamenten, Etiketten, Versicherern und Organisationen; Quellen in
  `daten/QUELLEN.md`). Feste Pseudonyme je Person; Varianten und Namensbestandteile werden
  zusammengeführt. Prüfziffern (IBAN Mod 97, Steuer-ID nach § 139b AO, ICAO bei Ausweisen …)
  bestimmen meist nur die Sicherheit eines Funds; ohne Etikett verlangen Steuer-ID und
  Ausweisnummer eine gültige Prüfziffer. Ganzwort-Prüfung bei der Schwärzung: Ein Fund darf
  nicht Teil eines längeren Wortes sein.
- **Zwei Kontrollen nach dem Schwärzen:** Die Selbstkontrolle sucht die geschwärzten Texte in
  der Ausgabe (bei Scans per erneuter OCR). Die Restrisiko-Prüfung (`restrisiko.py`) liest die
  Ausgabe als unabhängige zweite Linie mit eigenen Regeln – ohne die Erkennungsregeln und ohne
  das Sprachmodell – und meldet alles, was nach Personendaten aussieht. Eine zentrale
  Statusregel (`analyse.WARNUNGS_CODES`, `analyse.ist_leckrelevant`) entscheidet für jede
  Meldung, ob die Ausgabe `_PRUEFEN` heißt.
- **Bilder:** `fotos.py` (Fotobereiche und Lichtbilder), `bilder.py` (Neukodierung,
  Bildreste), `nebenkanaele.py` (versteckte Teile lesen und entfernen).
- Code und Oberfläche sind deutsch. Paketaufbau `anonymisierer/`: `analyse.py`,
  `schwaerzung.py`, `seitenmodell.py`, `detektoren/`, `muster.py` (Kategorien, Muster,
  Schutzstufen), `namen.py` (spaCy), `wissen.py` + `daten/`, `kundenliste.py`,
  `restrisiko.py`, `ocr.py`, `fotos.py`, `bilder.py`, `nebenkanaele.py`, `vorschau.py`,
  `vorschau_fenster.py`, `gui.py`, `gui_attrappen.py`, `dateien.py`; Startskript
  `pdf_anonymisierer.py`.
- Kommentare im Code verweisen teils auf interne Entwicklerunterlagen („Vertrag Abschnitt …“,
  `CONTRACT_V2.md`, `BENCHMARK_SCHEMA.md`), die nicht im Repository liegen.

## Mitentwickeln und Tests

```bash
python -m pip install --only-binary=:all: -r requirements.txt -r requirements-dev.txt
python -m pytest -q --timeout=300 tests/
```

Unter Linux brauchen die Oberflächentests ein Display (z. B. `xvfb-run -a python -m pytest …`);
die Layout-Tests starten für die geprüften Bildschirmgrößen bei Bedarf eigene Xvfb-Displays
(Paket `xvfb`). Die OCR findet die Sprachdatei im Ordner `tessdata` selbst. Die GitHub-Action
`.github/workflows/tests.yml` führt die Tests auf Ubuntu und Windows aus (Zeitgrenze 300 s je
Test, dafür `pytest-timeout` aus `requirements-dev.txt`), sichert Layout-Screenshots und den
Bericht des Benchmark-Tests als Artefakte und baut auf Wunsch bzw. für Versions-Tags `v…` die
Windows-EXE mit `EXE-bauen.bat`.

Werkzeuge in `werkzeuge/`:

- `pruefe_installation.py` – zeigt für Rückfragen Python, Pakete, Sprachdatei und Log-Pfad.
- `selbsttest.py` – Selbsttest mit eigenen, echten Dokumenten: analysiert und schwärzt einen
  Ordner wie die Oberfläche und gibt **nur Zählwerte** aus (keine Namen, Nummern, Datei- oder
  Ordnernamen). Die Ausgaben liegen in einem temporären Ordner und werden danach gelöscht,
  außer mit `--behalten <ordner>`. Aufruf (Schutzstufe wahlweise `ausgewogen`, `hoch` oder
  `maximal`): `python werkzeuge/selbsttest.py <ordner> --profil hoch`.
- `readme_tabelle.py` – erzeugt die Erkennungstabelle dieser README.
- `benchmark.py` mit dem Paket `benchmark/` – Entwicklungs-Benchmark: erzeugt Testdokumente
  mit bekannter Wahrheit und bewertet die Ausgaben; `tests/test_benchmark.py` nutzt ihn als
  Qualitätstor.
- `wissen_pflegen.py` – Wortlisten der Wissensbasis prüfen und einsortieren;
  `programmsymbol.py` – erzeugt `icon.ico`; `verknuepfung.py` – legt die Desktop-Verknüpfung an
  (wird von `Installieren.bat` aufgerufen).

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
  Repository erfüllt das) und auf den Lizenztext (`licenses/AGPL-3.0.txt`, liegt auch der
  EXE-ZIP bei). Firmeninterne Nutzung löst keine Pflichten aus; bei kommerzieller
  Weitergabe an Dritte die Artifex-Lizenz prüfen.
- **Tesseract-Sprachdatei** `tessdata/deu.traineddata` (tessdata_fast): Apache-2.0.
- **spaCy** und das Modell **de_core_news_md**: MIT.
- **tkinterdnd2**: MIT; die darin enthaltene Tk-Erweiterung **TkDND**: BSD-artige Lizenz im
  Stil von Tcl/Tk.

Hinweis zur Historie: Der erste Commit enthielt eine Apache-2.0-LICENSE, die danach
gelöscht wurde; die README nannte MIT. Seit Version 0.2.0 liegt der MIT-Text als
`LICENSE` bei. Änderungen stehen in [CHANGELOG.md](CHANGELOG.md).
