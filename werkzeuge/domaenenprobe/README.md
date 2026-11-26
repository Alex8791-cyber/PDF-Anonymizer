# Domänen-Probe

Synthetische Fälle aus dem Alltag eines Versicherungsmaklers – Kfz, Personenversicherungen und Gesundheit,
Sach/Haftpflicht/Recht, Finanzen/Behörden/Digitales sowie Briefverkehr, Listen und Scans („kritik“) – laufen Ende
zu Ende durch das Programm: PDF bauen, analysieren, schwärzen wie in der Oberfläche ohne Eingriff, Ausgabe lesen.
Gezählt wird für jeden geheimen Wert, ob er danach noch lesbar ist.

**Eine Regressionsprobe für die Entwicklung, keine Blindprüfung.** Die Fälle stammen aus der Domänen-Durchsicht
(Runde 5); die Erkennungsregeln wurden an genau diesen Fällen verbessert, viele Fälle sind gezielte Nachproben zu
einzelnen Befunden. Die Zahlen zeigen deshalb nur, ob sich an diesen Fällen etwas verschlechtert oder verbessert.
Über unbekannte Dokumente sagen sie nichts – dafür gibt es die Blindkorpora der Schlussmessung, die nicht im
Repository liegen.

Alle Namen, Anschriften, Nummern, E-Mail-Adressen und Benutzernamen sind frei erfunden (Nummern teils mit gültigen
Prüfziffern oder bekannten Musterwerten); Versicherer, Behörden, Banken und Firmen kommen nur als Umfeld vor. Neue
Fälle ebenso: nie Werte aus echten Dokumenten, von echten Personen oder aus den Blindkorpora.

## Inhalt

| Ordner | Sparte im Bericht | Dateien | Schwerpunkte |
|---|---|---:|---|
| `faelle_domaene.py` | `lauf1` | 1 | erste Probe quer durch die Sparten: Gerätenummern, Kennzeichen, Grundbuch, Zugangsdaten, Rollen |
| `kfz/`, `kfz_gegen/` | `kfz` | 2 + 4 | Versicherungs-, Kurzzeit- und Auslandskennzeichen, FIN, Führerschein, ZB I/II, Telematik, Leasing, Unfallgegner |
| `person/`, `person_gegen/` | `person` | 2 + 4 | PKV/GKV, BU/LV, Unfall, Pflege, Familienversicherung, Reise, Kennungen mit Tausenderpunkten |
| `sach/`, `sach_gegen/` | `sach` | 3 + 3 | Rechtsschutz, Gericht, Polizei, Tiere, Hausrat (Seriennummern), Wohngebäude, Gewerbe |
| `digital/`, `digital/runden/`, `digital_gegen/` | `digital` | 2 + 4 + 3 | Bank, Steuer, Sozialleistungen, Ausweise, E-Mail-Ausdrucke, Portale, Messenger, IP-Adressen |
| `kritik/` | `kritik` | 13 | Layouts: Kastenformulare, Infoblöcke, Bezugszeichen, Folgeseiten, Listen und CSV, Ausweise mit MRZ, Schräglage, Handyfoto, Querformat, PDF-Kommentare |

`…_gegen/` sind Gegenprüfungen der Befunde (die Zeile des Prüfers, eine leicht andere Schreibweise, Kontrollen);
`digital/runden/` sind frühere Fassungen der digitalen Fälle mit teils anderen Werten. `kritik/bau.py` baut die
Seiten der Kritik-Fälle (freie Positionen, Tabellen, Drehung, Foto-Nachbildung). Zusammen 41 Falldateien, 691 Fälle,
660 Textebenen- und 72 Scan-Varianten, 2261 geheime Werte.

## Aufruf

Aus der Projektwurzel, mit dem Python, in dem die Pakete aus `requirements.txt` installiert sind:

    python werkzeuge/domaenenprobe/messen.py <ausgabeordner>

| Option | Wirkung |
|---|---|
| `--jobs N` | N Falldateien gleichzeitig, jede in einem eigenen Prozess mit einem OCR-Arbeitsprozess (Vorgabe 2) |
| `--repo <checkout>` | Programmcode (`anonymisierer/`) aus einem anderen Checkout oder Export messen; Vorgabe: dieses Checkout. Die Probe selbst stammt immer aus diesem Ordner |
| `--vergleich <ergebnis.json>` | mit einer früheren Messung statt mit `referenz.json` vergleichen; `--ohne-vergleich` vergleicht nicht |
| `--faelle <datei> …` | nur diese Falldateien (relativ zum aktuellen Ordner oder zu diesem, z. B. `kfz/faelle_kfz_1.py`); Dateien von außerhalb zählen als Sparte `extern` |
| `--nur <fall,…>` | nur diese Fälle (Namen aus `FAELLE`) |
| `--ocr pymupdf` | OCR-Prüfung mit dem in PyMuPDF eingebauten Tesseract statt der Kommandozeile – für Rechner ohne Tesseract-Kommandozeile; nicht mit der Referenz vergleichbar |
| `--tesseract <programm>` | Tesseract-Kommandozeile; sonst `DOMAENENPROBE_TESSERACT`, `PATH` und unter Windows `…\Tesseract-OCR\tesseract.exe` in den Programmordnern |
| `--pdfs-behalten` | gebaute PDFs und Ausgaben behalten (Vorgabe: nach jeder Falldatei löschen, nur Protokolle bleiben) |
| `--als-referenz` | danach `referenz.json` und `referenz.md` durch diese Messung ersetzen (siehe unten) |

Exit-Code 1, wenn eine Falldatei nicht durchlief (Bericht: „Fehler:“, Protokoll in `arbeit/…/lauf.txt`); 2 bei
falschem Aufruf oder ohne Tesseract-Kommandozeile. Endet die Tesseract-Kommandozeile mit einem Fehler, bricht die
Falldatei ab – ein leerer OCR-Text würde sonst jeden Wert als „weg“ zählen.

Voraussetzungen:

- **Tesseract-Kommandozeile** für die OCR-Prüfung der Ausgabe (Linux: Paket `tesseract-ocr`; Windows: Tesseract-OCR
  der UB Mannheim). Die deutsche Sprachdatei liefert das gemessene Checkout (`tessdata/`): Das Programm setzt
  `TESSDATA_PREFIX`, die Kommandozeile erbt es.
- **Schriften DejaVu Sans und DejaVu Sans Mono** für Fälle mit Sonderzeichen und die Kritik-Seiten (Linux: Paket
  `fonts-dejavu-core`). Fehlen sie (Windows ohne DejaVu), nimmt die Probe Arial bzw. Consolas, schreibt einen Hinweis
  ins Protokoll und vermerkt die Ersatzschrift im Bericht; die Ergebnisse sind dann nur eingeschränkt mit der
  Referenz vergleichbar. `DOMAENENPROBE_SCHRIFT` und `DOMAENENPROBE_SCHRIFT_MONO` geben andere Schriftdateien vor.
- **Pillow** (`python -m pip install --only-binary=:all: pillow`) für die Scan-Varianten der Fälle (Drehung,
  JPEG). Das Programm selbst braucht es nicht; deshalb steht es weder in `requirements.txt` noch in
  `requirements-dev.txt`.
- Unter Linux laufen die Messprozesse mit `nice -n 15`, unter Windows mit niedriger Priorität; Unterprozesse
  starten ohne Shell, Protokolle und Ergebnisse sind UTF-8.

## Was gemessen wird

Je Falldatei startet `messen.py` den Harness `e2e.py` als eigenen Prozess. Er baut je Fall eine PDF mit Textebene
(Helvetica, bei `unicode` DejaVu Sans; die Kritik-Fälle mit `kritik/bau.py`) und daraus die angegebenen
Scan-Varianten (Seite mit 200 dpi in Graustufen gerendert, ggf. gedreht und als JPEG). Jede Variante geht durch
Analyse und Schwärzung wie in der Oberfläche ohne Eingriff der Nutzerin (`anonymisierer/auftrag.py`: Häkchen der
Fundliste, Schutzstufe „Hoch“, „Freigabe vor Weitergabe“ an). Die Ausgabe wird zweimal gelesen: die Textebene
(`get_text`) und die mit 300 dpi gerenderten Seiten per OCR (Tesseract, PSM 3, Sprache deu).

Lesbar heißt: Nach Entfernen von Leerraum und Satzzeichen (`. , ; : _ | " ' ( ) [ ] -`, typografische
Anführungszeichen, `→`) und in Großbuchstaben steht der Wert im Text – oder, bei mehr als vier Zeichen, ein
Ausschnitt mit einem Zeichen mehr, gleich vielen oder einem weniger ähnelt ihm zu mindestens 86 %
(`difflib.SequenceMatcher`), damit OCR-Verleser nicht als „weg“ zählen.

| Zustand | Bedeutung |
|---|---|
| **weg** | weder in der Textebene noch per OCR lesbar |
| **sichtbar** (`_PRUEFEN`) | lesbar, aber sichtbar gemacht: Die Restrisiko-Prüfung meldet einen Verdacht zu diesem Wert, oder die Ausgabe heißt aus einem anderen Grund als der bloßen „Freigabe vor Weitergabe“ `_PRUEFEN` |
| **STILL** | lesbar, kein Verdacht zu diesem Wert, und die Ausgabe heißt höchstens wegen der Freigabe `_PRUEFEN` – ein stilles Leck, das nur die Sichtprüfung der Nutzerin findet |

Ein Verdacht gilt für einen Wert, wenn sein Text den Wert enthält oder (ab drei Zeichen) im Wert steht.

Im Ausgabeordner:

- `ergebnis.json` – je Eintrag `Datei|Fall|Art|Wert` (Art `text` oder `scan<dpi>/<winkel>/<jpeg>`) die Sparte, der
  Zustand und der Status der Ausgabe;
- `bericht.md` – Stand, Umgebung und Dauer, Tabelle je Sparte (Werte, weg, sichtbar, STILL), Vergleich;
- `arbeit/<sparte>_<ordner>_<datei>/lauf.txt` – je Wert eine Zeile (`weg`, `LECK+PRUEFEN` = sichtbar, `STILL`) mit
  Textebene/OCR getrennt, dazu je Variante Funde, Verdacht und Meldungen; `ergebnis_oberflaeche.json` – dieselben
  Rohdaten maschinenlesbar.

## Vergleich mit der Referenz

`referenz.json` ist die `ergebnis.json` einer vollen Messung; `referenz.md` nennt Stand, Umgebung und Zahlen. Ohne
`--vergleich` oder `--ohne-vergleich` vergleicht `messen.py` damit. Rangfolge weg < sichtbar < STILL: Unter
„Verschlechtert“ steht jeder Eintrag mit höherem Rang als in der Referenz (z. B. `weg -> sichtbar`,
`sichtbar -> still`), unter „Verbessert“ die umgekehrten; dazu die Zahl der gemeinsamen Einträge und der Einträge,
die nur in einer der beiden Messungen vorkommen (geänderte oder neue Fälle; im Teillauf mit `--faelle`/`--nur`
erwartet). Ein Statuswechsel ohne Zustandswechsel zählt nicht.

Vergleichbar sind nur Messungen in derselben Umgebung wie die Referenz (`referenz.md`: Linux, Tesseract-
Kommandozeile, DejaVu-Schriften, Versionen von PyMuPDF und spaCy). Eine andere Tesseract- oder PyMuPDF-Version, eine
Ersatzschrift oder `--ocr pymupdf` verschieben einzelne Einträge, ohne dass sich das Programm geändert hat. In
derselben Umgebung ist die Messung wiederholbar: Drei Läufe auf ef90382 (die Integrationsmessung mit dem Skript der
Domänen-Durchsicht und zwei Läufe dieses Werkzeugs) ergaben Byte für Byte dieselbe `ergebnis.json`.

Die Referenz erneuern – nach einer gewollten Änderung am Programm oder an den Fällen, auf dem Stand, der
eingecheckt wird:

    python werkzeuge/domaenenprobe/messen.py <ausgabeordner> --jobs 2 --als-referenz

Das geht nur mit einem vollen Lauf mit der Tesseract-Kommandozeile und ohne Fehler; danach `referenz.json` und
`referenz.md` mit einchecken. `tests/test_domaenenprobe.py` prüft, dass `referenz.json` genau die Einträge der
Falldateien hat – wer Fälle ändert, muss die Referenz erneuern.

Neue Fälle: eine Datei `faelle_….py` oder `gegen_….py` in einem der Ordner (die Liste steht in `messen.py`,
`BEREICHE`), die `FAELLE` definiert – eine Liste von Wörterbüchern mit `name` (eindeutig in der Datei), `zeilen`
(Textzeilen; `\t\t` trennt bis zu drei Spalten) oder `bauer` (Funktion, die die PDF schreibt), `geheim` (Werte, die
danach nicht mehr lesbar sein dürfen) und wahlweise `scans` (`(dpi, winkel, jpeg_qualität oder None)`), `text`
(`False`: nur die Scan-Varianten), `felder` (Formularfelder `(name, rechteck, wert)`), `unicode` (DejaVu statt
Helvetica), `font`, `groesse` und `zeige_ocr` (OCR-Text ins Protokoll).

## Bekannte konservative Messartefakte

Die Lesbarkeitsprüfung arbeitet auf dem ganzen Seitentext ohne Leerraum und Satzzeichen und ist absichtlich
großzügig: Sie zählt einen Wert eher als lesbar als dass sie ein Leck übersieht. Deshalb steht in den Zahlen
etwas mehr „sichtbar“ und „STILL“, als wirklich stehen bleibt. In der Referenz (fd73eac) sind von 38 Einträgen, die
nicht „weg“ sind, vier solche Artefakte – der Wert selbst ist geschwärzt, gezählt wird ein anderer Text:

| Eintrag | Zustand | Woher der Treffer stammt |
|---|---|---|
| `person/faelle_person1.py`, `formularfelder_antrag`, `Ole` | STILL | Werte bis vier Zeichen zählen, sobald die Zeichenfolge irgendwo steht: „Risik**ole**bensversicherung“ in der Überschrift |
| `person/faelle_person1.py`, `kinder_fliesstext`, `Fenja` | STILL | Die OCR liest „[PERSON C] geboren [GEB-DATUM]“ (Platzhalter in kleiner Schrift) als „persone GEDOFEN jacsoArum“ – ohne Leerraum steht darin „…FENJA…“ |
| `person/faelle_person1.py`, `beihilfe_antrag`, `Xaver` | sichtbar | Unschärfe über Platzhalter hinweg: „[PERSON A] [VERTRAGSNR]“ wird zu „PERSONAVERTRAGSNR“, „AVER“ ähnelt „XAVER“ zu 89 % |
| `kritik/faelle_k3.py`, `k3_entgelt`, `84347` | sichtbar | Unschärfe auf einer ähnlichen, nicht geheimen Zahl: „84478 Waldkraiburg“ (Anschrift des Arbeitgebers) enthält „8447“ (89 %) |

Allgemein gilt dasselbe für kurze Werte (kurze Personal- oder Hundesteuermarken-Nummern, Jahreszahlen, Vornamen
bis vier Buchstaben), die als Teil eines anderen Worts oder einer anderen Zahl auf der Seite stehen, für
Werte, die einer anderen Zahl oder einem Platzhalter-Gemisch zu 86 % ähneln, und für Werte, die zusätzlich
ungeschwärzt in einem nicht geheimen Zusammenhang stehen. Wer einen Eintrag als Leck einstuft, schaut deshalb in
`lauf.txt` und, mit `--pdfs-behalten`, in die Ausgabe-PDF.

Die Prüfung hat auch Grenzen in die andere Richtung: Liest die OCR einen stehengebliebenen Wert zu stark verfälscht
(z. B. „E31K8TQ“ als „E3IKSTQ“), sieht sie ihn nicht; bei Textebene-Varianten fängt das die Textebene auf, bei
reinen Scan-Varianten zählt der Wert dann als „weg“. Geprüft werden nur Textebene und Seitenbild – Metadaten,
Anhänge und andere Nebenkanäle bewertet der Entwicklungs-Benchmark (`werkzeuge/benchmark.py`). Über-Schwärzung
misst die Probe nicht (Fälle ohne geheime Werte zählen nicht mit).

## Laufzeit und Platz

Die volle Probe dauerte auf einem Linux-Rechner mit vier Kernen 7,3 und 7,5 min mit `--jobs 2` (rund 14 min
CPU-Zeit, parallel lief eine weitere Messung). Ohne `--pdfs-behalten` bleiben rund 11 MB (Protokolle und JSON),
mit `--pdfs-behalten` rund 360 MB (1495 PDFs). `tests/test_domaenenprobe.py` lädt nur die Falldateien und lässt
einen kleinen Text-Fall laufen: wenige Sekunden.
