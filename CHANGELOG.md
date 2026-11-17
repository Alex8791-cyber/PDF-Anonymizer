# Änderungen

Alle nennenswerten Änderungen am PDF-Anonymisierer. Das Format folgt
[Keep a Changelog](https://keepachangelog.com/de/1.1.0/); die Versionsnummer steht in
`anonymisierer/__init__.py`.

## [Unreleased]

Seit 0.2.0 sind Erkennung, Schwärzung, die Prüfung der Ausgabe und die Oberfläche in großen Teilen neu
gebaut. Zuerst steht, was sich an der gewohnten Arbeit ändert, danach Neues, weitere Änderungen,
Fehlerbehebungen und Sicherheit, dann ein kurzer Teil für Entwickler. Am Ende folgen die Änderungen aus dem
Review „Auslieferung/Doku“ (AD-01 … AD-08).

### Geändert – bitte beachten
- **Jede Ausgabe heißt zuerst `_PRUEFEN`.** Neue Einstellung „Freigabe vor Weitergabe erforderlich“
  (Standard: an): Die Ausgabe heißt `anonym_NN_PRUEFEN.pdf`, bis sie in der Vorschau mit „Freigeben“ zu
  `anonym_NN.pdf` wird. Die Einstellung lässt sich abschalten; Ausgaben umgewandelter Fotos und Bild-Scans
  brauchen die Freigabe trotzdem. Freigeben geht nur in derselben Programmsitzung – also vor dem Beenden
  prüfen und freigeben. Stehen beim Beenden noch Dateien mit nicht freigegebener Ausgabe in der Liste,
  fragt das Programm nach („Freigabe noch offen“, Voreinstellung „Nein“) – während eines Laufs in der
  Rückfrage „Lauf läuft noch“, die dann auch die schon fertigen Ausgaben des laufenden Laufs nennt;
  freigeben lässt sich erst nach dem Ende des Laufs.
- **`_PRUEFEN` hat viele neue Gründe**, z. B. ein Verdacht der neuen Restrisiko-Prüfung, ein kaum lesbarer
  Scan, eine unlesbare Textebene, eine beschädigte Datei oder ein beschädigtes Bild, Personendaten nur in
  versteckten Teilen der Datei, eine ausgefallene Erkennungsregel oder eine Namenserkennung ohne
  Sprachmodell. Die Gründe stehen in der Fundliste und im Abschlussdialog. Nicht jeder Prüffall ist ein
  echtes Leck; mit deutlich mehr `_PRUEFEN`-Dateien ist zu rechnen.
- **Jede lesbare Datei bekommt eine Ausgabe**, auch ohne Fund (vorher: keine Ausgabe). Sie ist bereinigt
  (Metadaten, Anhänge, Formulardaten u. a. entfernt) und geprüft. Ohne Ausgabe bleiben nur Dateien, die sich
  nicht bearbeiten lassen; der Abschlussdialog nennt sie unter „OHNE Ausgabedatei“. Regel: nur aus dem
  Ausgabeordner hochladen, nie das Original.
- **Die Zuordnungsdatei liegt neben dem Ausgabeordner** statt darin und heißt `_zuordnung_<Ausgabeordner>.txt`,
  im Normalfall also `_zuordnung_anonymisiert.txt` neben den Originalen. Ist der Zielordner eine Laufwerks-
  oder Freigabe-Wurzel (z. B. `E:\`), liegt sie unter `%APPDATA%\PDF-Anonymisierer\Zuordnungen`. Lässt sie
  sich am vorgesehenen Ort nicht schreiben (z. B. ohne Schreibrecht), liegt sie ausnahmsweise doch im
  Ausgabeordner (`_zuordnung.txt`); der Abschlussdialog warnt dann – diese Datei nicht mit hochladen. Eine alte
  `_zuordnung.txt` im Ausgabeordner wird beim nächsten Schwärzen übernommen und gelöscht.
- **Mehr wird geschwärzt oder angeboten:** Die Standardstufe „Hoch“ schwärzt zusätzlich Beruf, Arbeitgeber,
  ausländische Anschriften und Orte ohne PLZ. Lichtbilder auf Ausweiskopien werden gesucht und abgedeckt –
  aber nicht immer gefunden. Diagnosen und Medikamente stehen nicht angehakt in der Fundliste (Zeichen ⚕).
  Anschriften von Firmen, Versicherern und Behörden bleiben dagegen jetzt stehen; unbekannte
  Firmenanschriften erscheinen als abgewählter Fund „vermutlich Firmenanschrift“. Wirkt ein Briefkopf wie der
  einer Firma (z. B. mit Webadresse oder Bankverbindung, wie oft bei Selbständigen), wird die Anschrift darin
  nur geschwärzt, wenn davor ein Name steht, den das Programm als Vor- oder Nachnamen kennt, und auch dann nicht
  immer (z. B. nicht mit einer Zeile wie „Mitglied der Handwerkskammer …“ zwischen Name und Anschrift); sonst
  steht sie abgewählt als „vermutlich Firmenanschrift“ in der Fundliste. Bei Selbständigen jeden solchen Fund
  prüfen und anhaken, wenn es ihre Anschrift ist – auch wenn ihr Name davorsteht.
- **Lichtbilder und Freigabe:** Bleibt ein gefundenes Lichtbild sichtbar (abgewählt oder als unsicherer
  Treffer nicht angehakt) oder ist auf einer erkannten Ausweiskopie (Ausweistext wie „PERSONALAUSWEIS“ im Bild
  lesbar) kein Lichtbild abgedeckt, heißt die Ausgabe `_PRUEFEN` – auch bei abgeschalteter
  Freigabe-Einstellung. Lichtbilder werden aber nicht immer gefunden: Ausweiskopien immer selbst in der
  Vorschau ansehen.
- **Dateien werden am Inhalt geprüft, nicht an der Endung.** Fotos und Bild-Scans werden nach Rückfrage in
  eine PDF umgewandelt, auch wenn sie die Endung `.pdf` tragen. Office-Dateien, Mails, Webseiten, HEIC, WEBP
  und GIF werden nicht aufgenommen und als „NICHT geprüft“ gemeldet, auch mit der Endung `.pdf`. Ausnahme: Eine
  als `.pdf` gespeicherte Textdatei (z. B. eine Mail im Textformat) kommt in die Liste, wird aber nicht
  bearbeitet und bekommt keine Ausgabe. Bei kennwortgeschützten PDFs fragt das Programm nach dem Kennwort; die
  Ausgabe hat dann kein Kennwort. Eine Ausgabe des Programms wird nur nach Rückfrage als Eingabe aufgenommen.
- **„Markierte nachschwärzen“ erzeugt eine neue Ausgabe** mit der nächsten freien Nummer und löscht die alte;
  in der Nummernfolge entstehen Lücken.
- **Geänderte Einstellungen setzen die Analyse zurück:** Nach einer Änderung an Schutzstufe, Kategorien,
  NIE-/IMMER-Liste oder Kundenliste muss neu analysiert werden; manuelle Markierungen aus der Vorschau gehen
  dabei verloren.
- **Geschwärzte Bilder werden neu gespeichert**, meist als JPEG in der Qualität des Originals (höchstens
  85); geschwärzte JPEG-Fotos über 24 Megapixel werden auf 24 Megapixel verkleinert. Die Ausgabe wird
  kleiner, ist aber nicht pixelgleich mit dem Original.
- **Nur ein Programmfenster:** Ein zweiter Start meldet „PDF-Anonymisierer läuft bereits“.
- **Kleine Bildschirme:** Auf 1366×768 und auf 1920×1080 ab 125 % Skalierung startet das Fenster maximiert.
  Im kleinen Fenster entfallen großer Titel, Untertitel und Bedienhinweis. Reicht der Platz für die Fundliste
  dann nicht, rücken der Reihe nach – nur so weit wie nötig – Titel „1 · PDF-Dateien“ und Ablagefläche in eine
  Zeile (wenn beide nebeneinander passen), die Knöpfe werden flacher, und zuletzt zeigt der Hinweiskasten eine
  Kurzfassung in höchstens zwei Zeilen mit den Kernaussagen (ein Klick zeigt alle Grenzen). Die Grenzen der
  Erkennung stehen weiter unter Hilfe → „Was wird nicht erkannt?“ und „Hinweise vor der Nutzung …“; den
  Bedienhinweis über der Fundliste (Leertaste, Doppelklick, Rechtsklick) gibt es nur im normal großen Fenster.
- **Rechenzeit und Arbeitsspeicher:** Restrisiko-Prüfung und Fotoerkennung kosten zusätzlich Zeit. Auf dem
  Entwicklungsrechner brauchten Scan-Seiten mehrere Sekunden je Seite und ein großes Handyfoto rund 1 GB
  Arbeitsspeicher.
- **Umstieg von 0.2.0:** Gespeicherte Einstellungen erscheinen als Stufe „Benutzerdefiniert“ (bei
  unveränderter Auswahl mit denselben Häkchen wie „Hoch“); ein Klick auf „Hoch (Standard)“ stellt die
  Standardstufe ein.

### Hinzugefügt
- **Schutzstufen** „Ausgewogen“, „Hoch (Standard)“, „Maximal“ und „Benutzerdefiniert“ über den Häkchen; die
  Häkchen folgen der Stufe, die Wahl wird gespeichert. „Maximal“ schwärzt zusätzlich Diagnosen, Medikamente,
  alle plausiblen Geburtsdaten und unbekannte Eigennamen bei Personen und deckt Bilder auf Textseiten und
  Fotobereiche auf Scans ab. Stehen bleiben winzige Bilder, Vektorgrafiken und der Text über einem Bild
  (gefundene Angaben darin werden wie sonst geschwärzt); von einem Bild über mindestens die halbe Textseite
  werden nur die Fotos darin abgedeckt. Unterschriften und Handschrift auf Scans bleiben auch in „Maximal“
  stehen.
- **Sechs neue Kategorien** (26 statt 20): ausländische Anschriften und Kennzeichen `[AUSLAND]`, Orte ohne PLZ
  `[ORT]`, Beruf `[BERUF]` und Arbeitgeber `[ARBEITGEBER]` (bei Personen), Diagnosen und ICD-Codes
  `[DIAGNOSE]`, Medikamente `[MEDIKAMENT]`. Gesundheitsdaten erkennt das Programm nur als bekannte Begriffe
  der Wortlisten, ICD-10-Codes und Körpermaße, jeweils im Gesundheitszusammenhang.
- **Vorschau-Fenster** (Doppelklick auf eine Datei, Knopf „Vorschau …“ oder Alt+V). „Geplante Schwärzung“:
  rot = wird geschwärzt, grau gestrichelt = nicht, blau = manuell; ein Klick schaltet eine Stelle um oder
  schwärzt ein nicht erkanntes Wort, ein gezogener Rahmen schwärzt einen Bereich. „Ergebnis (Ausgabe)“: die
  Ausgabe mit Verdachtsstellen (orange) und den Knöpfen „Freigeben“, „Markierte nachschwärzen“ und
  „Verwerfen (Ausgabe löschen)“.
- **Restrisiko-Prüfung:** Eine zweite, von der Erkennung unabhängige Prüfung liest jede Ausgabe noch einmal
  (bei Scans per Texterkennung) und meldet, was noch nach Personendaten aussieht – Nummern, Namen,
  Anschriften, Geburtsdaten, auf Scans ungelesene Tinte in Unterschriftsblöcken sowie Scan-Seiten, die sich
  nicht verlässlich lesen lassen. Jeder Verdacht macht die Ausgabe `_PRUEFEN`. Einzelne abgewählte Stellen
  eines angehakten Funds meldet sie nicht. Einen ganz abgewählten Fund im Text (z. B. „vermutlich
  Firmenanschrift“) gibt die Oberfläche dagegen gar nicht an die Schwärzung; sieht er nach Personendaten aus,
  meldet die Prüfung ihn deshalb meist weiter als Verdacht. Darauf ist aber kein Verlass: Hält die Prüfung einen
  Briefkopf für den einer Organisation (z. B. mit einer eigenen Zeile „Mitglied der Handwerkskammer …“ über der
  Anschrift), bleibt die lesbare Privatanschrift einer Selbständigen ohne Verdacht. Nach Gesundheitsdaten, Beruf
  und Arbeitgeber sucht sie nicht.
- **Kundenliste** (Menü „Kundenliste“): Import einer CSV-Datei mit Kundendaten. Gespeichert werden nur nicht
  umkehrbare Prüfwerte, kein Klartext. Passt ein starkes Merkmal (voller Name, Kunden- oder Vertragsnummer,
  IBAN, E-Mail), sucht das Programm alle Angaben dieses Kunden.
- **Namenserkennung mit Wortlisten und Dokumentaufbau:** rund 6 200 Vornamen und 8 500 Nachnamen, Regeln für
  Tabellen, Formularfelder, Anschriftfelder sowie Anrede und Grußformel. In Firmenbezeichnungen wie
  „Werkstatt Berger“ wird der Name geschwärzt, Rechtsform und Betriebswort bleiben.
- **Ausweiskopien und weitere Nummern:** maschinenlesbare Zone, Zugangsnummer und Führerscheinfelder;
  Personalausweis- und Passnummern auch ohne Etikett, wenn die Prüfziffer stimmt; BIC ohne Etikett in
  eindeutiger Form; Steuernummern in den Formaten der Bundesländer und als ELSTER-Nummer; Nummern ohne Etikett
  in Betreffzeilen und in Kopf- und Fußzeilen, die auf mehreren Seiten wiederkehren; Kammfelder (ein Zeichen
  je Kästchen) und Fax-Kopfzeilen; Geburtsdaten auch als „Jg. 1961“ oder direkt hinter dem Namen.
- **Lichtbilder auf Ausweiskopien** werden gesucht und als angehakter Fund `[LICHTBILD]` abgedeckt – aber nicht
  immer gefunden. In Fundliste und Vorschau sind sie abwählbar; ein unsicherer Treffer steht nicht angehakt
  in der Liste.
- **Fotos und Bild-Scans** (JPEG, PNG, TIFF, BMP) werden nach Rückfrage in eine PDF-Arbeitskopie umgewandelt
  und per Texterkennung geprüft – das ist unsicherer als bei echten PDFs. Unterschriften und Handschrift
  darauf bleiben stehen, Gesichter ebenso (außer gefundenen Lichtbildern; „Maximal“ deckt Fotobereiche ab).
  **Kennwortgeschützte PDFs** werden nach Eingabe des Kennworts geprüft; das Kennwort wird weder gespeichert
  noch protokolliert. Arbeitskopien liegen unter `%LOCALAPPDATA%\PDF-Anonymisierer\temp` und werden beim
  Entfernen aus der Liste und beim Beenden gelöscht. Reste nach einem Absturz löscht der nächste
  Programmstart, manchmal erst ein Start nach 7 Tagen; eine entschlüsselte Arbeitskopie enthält das ganze
  Original.
- **Bedienung:** Menüs „Datei“ und „Kundenliste“, unterstrichene Zugriffstasten (Alt+A Analysieren, Alt+S
  Schwärzen starten, Alt+V Vorschau), „Datei → Protokoll speichern …“ (Laufprotokoll ohne Dokumentinhalte,
  Originaldateinamen und Ordner), ein Hinweis beim ersten Start (später unter Hilfe → „Hinweise vor der
  Nutzung …“) und ein Programmsymbol.
- **`werkzeuge/selbsttest.py`** (Kommandozeile, nur mit Python-Installation): prüft einen Ordner eigener
  Dokumente und gibt nur Zählwerte aus, nie Inhalte.
- **Erkennung: Kennungen aus dem Makler-Alltag.** eVB-Nummer (elektronische Versicherungsbestätigung, 7 Zeichen hinter
  „eVB“, „eVB-Nr.“, „VB-Nummer“, „Versicherungsbestätigung …“) und Transferticket der Kfz-Versicherung werden als
  `[VERTRAGS-NR]` geschwärzt, die Kartenprüfnummer einer Zahlungskarte (CVC/CVV, „CVC-Code“, „Kartenprüfnummer“) als
  `[KREDITKARTE]` – „Prüfnummer“ oder „Sicherheitscode“ allein nur neben einer Kartenangabe; die Prüfnummer einer
  TÜV-Plakette, Zulassung oder eines Gutachtens wird nie zur Kartenprüfnummer. Auch mit Zwischenwörtern („Ihre
  eVB-Nummer für die Zulassung lautet: …“, „eVB-Nummer vom 12.03.2025: …“, „Die eVB-Nummer, die Sie für die Zulassung
  brauchen, lautet …“, „Sicherheitscode auf der Kartenrückseite: …“) und auf Scans, wenn die Texterkennung Zeichen
  einfügt („K7/H3MY9P“) oder das Etikett verliest („eV8-Nummer“). Ein Wort in Versalien hinter dem Etikett ist keine
  Kennung („eVB: ERTEILT“, „Transferticket: ANGEFORDERT“, „Versicherungsbestätigung ALLIANZ“), eine Zahl der
  Folgezeile im Fließtext keine Kartenprüfnummer („… die CVC“ ⏎ „1500 EUR …“). Eine Kartenprüfnummer wird nur hinter
  ihrem Etikett geschwärzt, nie dieselben drei oder vier Ziffern an anderer Stelle oder in anderen Dokumenten des
  Laufs (Beträge, Seitenzahlen). Der Geburtsname hinter „geb.“ oder „geborene“ direkt hinter einem Namen bekommt den
  Platzhalter seiner Person („[PERSON A] geb. [PERSON A]“, auch „Frau Weber geb. …“, „Weber, Anna geb. …“, mehrteilig
  „geb. Garcia Lopez“; trägt ihn auch eine andere Person, `[FAMILIE A]`), hinter dem Feld „Geburtsname“ wird er
  geschwärzt (eigener Platzhalter); Datum, Ort, Füllwörter und Feldkürzel hinter „geb.“
  („geb. Hamburg“, „geb. Ledig“, „Geburtsname: siehe oben“, „GEB.DAT.“), „Gebr.“ und „Geb.“ für Gebäude oder Gebühr
  bleiben wie bisher. Erkannt in derselben Zeile, in der nächsten Zeile, in der Tabellenzelle bzw. -spalte und auf
  Scans; die Restrisiko-Prüfung meldet einen lesbar gebliebenen Wert hinter diesen Etiketten (Ausgabe `_PRUEFEN`),
  auch mit Lesefehlern der Texterkennung („Kartenprufnummer“). Auf Scans ist „geb.“ vor einem geschwärzten
  Geburtsnamen kein Grund mehr für die Warnung „Schlüsselwort ohne Fund“.
  Erkennung und Restrisiko-Prüfung lesen diese Kennungen nach derselben Regel „Etikett + Wert“ (neues Modul
  `anonymisierer/kennungsformen.py`): der Wert direkt hinter dem Etikett, in der nächsten Zeile, in der Zelle daneben
  oder hinter Zwischenwörtern desselben Satzes bis zu einer Ankündigung – auch groß geschrieben, mit Klammern,
  Abkürzungen und Zeilenumbruch („Die eVB-Nummer Ihres neuen Fahrzeugs lautet: …“, „… für die Zulassung Ihres Pkw
  (Kennzeichen M-AB 123) lautet: …“, „Die CVC auf der⏎Rückseite ist 739.“); Schluss am Satzende, an einem anderen
  Etikett und nach 14 Wörtern. Dazu: Mehrzahl („eVB-Nummern: …, …“, „Transfertickets:“), zweizeilige Spaltenköpfe
  („Versicherungs-“⏎„bestätigung“), „Kreditkartenprüfnummer“, „Kreditkarten-Prüfnummer“, „Kartenprüfnr.“, „Prüfnr.“
  (auch als Spaltenkopf), „Sicherheitscode (3 Ziffern):“, „CID:“, „Card Verification Code“, Kammfelder mit einer Ziffer
  je Kästchen, Kartendaten ohne Etikett („Visa 4111 …, gültig bis 12/27, 739“), wenige Wörter ohne Ankündigung in
  Kunden-Mails („…, Prüfziffer hinten 739“), „Geburtsname, falls abweichend: …“ (auch in Versalien), „Geburtsname
  (falls vom Familiennamen abweichend): …“, „Geb.-Name ⇥⇥ …“, „Familienname (Geburtsname): Weber (Quarnstedt)“
  (derselbe Platzhalter wie „Weber“), Spaltenköpfe unter einer Titelzeile und Lesefehler wie „eVB-Nurnmer“ und
  „Anna Weber gab. Quarnstedt“.
  Nach der zweiten Gegenprüfung außerdem: Herkunftsnamen hinter „geb.“ und Geburtsnamen-Etiketten („geb. Mainzer“,
  „Danziger“, „Landauer“, „Geburtsname: Linz“); ein Ort direkt hinter „Name geb.“ („Anna Weber geb. Linz“) bleibt
  stehen, weil er auch der Geburtsort sein kann, die Restrisiko-Prüfung meldet ihn. Weitere Etiketten: „Mädchenname“,
  „Geburtsn.“, „Name vor der Ehe“, „Familienname vor der Eheschließung“, „Geb.-Name Quarnstedt“ und mehrere Namen
  hinter „Geburtsnamen:“. eVB-Aufzählungen mit Aufzählungszeichen, Nummern und Zuordnungen („Pkw: …“, „… – VW Golf“,
  „die für den Polo …“, eine Liste unter „eVB-Nummern Ihres Fuhrparks“), eVB in Briefsätzen („Die eVB (Nr. …)“, „hat
  die Nummer …“, „unter … erstellt“), die Kartenprüfnummer hinter Kartendaten über mehrere Zeilen und hinter „Code:“,
  „Rückseite:“, „CSC:“, „Sicherheitsziffer:“, „Kontrollziffer:“, „Prüfz.:“, in Kartentabellen ohne Kartenangabe im
  Kopf („Karte ⇥ Nummer ⇥ Sicherheitscode“ über Kartendaten; ohne erkannte Tabelle meldet sie die Restrisiko-Prüfung),
  Festbreiten-Listen auf Scans („ANNA GEB. ⇥ AMBERGER“), Kammfelder mit weit auseinander stehenden Kästchen auf der
  Textebene (auch für die eVB) und Lesefehler wie „gcb.“, „qeb.“, „eVB-Nummcr“, „CVG“, „CV C“, „Gcburtsname“,
  „Geburtsnamc“ und „[7][3][9]“. Auf Scans meldet die Restrisiko-Prüfung Schrift hinter einem
  Kennungs-Etikett, die die Texterkennung nicht lesen konnte – etwa ein Kammfeld mit einer Ziffer je Kästchen
  („Kennungsangabe: Schrift hinter einem Kennungs-Etikett … nicht verlässlich lesbar“, Ausgabe `_PRUEFEN`).

### Geändert
- **Prüfziffern sind nur noch ein Indiz:** Eine IBAN mit falscher Prüfziffer wird trotzdem geschwärzt, wenn
  sie eindeutig wie eine IBAN aussieht, und trägt den Hinweis „Prüfziffer ungültig (Lesefehler?)“ (⚑).
- **Scans:** Die Texterkennung teilt Seiten in Spalten und Blöcke auf (zweispaltige Briefköpfe werden nicht
  mehr vermischt), rückt schräge Scans gerade und erkennt die Lage gedrehter Seiten an der Plausibilität der
  gelesenen Wörter. Typische Lesefehler (O/0, I/1, S/5 …) und verlesene Feldnamen werden nur bei gescanntem
  Text berücksichtigt. Bei durchsuchbaren Scans entfernt jeder Treffer Text und Bildpunkte an derselben
  Stelle.
- **Weitergabe im Lauf:** Namen und Kennungen aus einem Dokument werden in allen Dokumenten derselben Analyse
  gesucht; Abgewähltes bleibt abgewählt.
- **NIE-Liste:** Nummern gelten unabhängig von Leerzeichen („DE89 3704 …“ gibt auch „DE893704…“ frei).
- **Versteckte Teile der Datei** (Metadaten, Lesezeichen, Anhänge samt Inhalt, Formular- und XFA-Daten,
  JavaScript, Link-Ziele, Seitenbeschriftungen) werden mit denselben Regeln geprüft und gemeldet; die Ausgabe
  entfernt sie.
- **Fundliste:** Die Dateizeile zeigt den Status der Ausgabe („fertig“ oder „prüfen“) und den Grund; ⚑
  markiert Funde mit Hinweis, ⚕ nur angebotene Gesundheitsdaten; die Leertaste schaltet einen Fund um; lange
  Dateinamen werden in der Mitte gekürzt. Die Hinweiszeile nennt NICHT geprüfte Dateien.
- **Abschlussdialog:** nennt die Gründe für `_PRUEFEN`, Dateien ohne Ausgabe und NICHT geprüfte Dateien und
  bietet an, die Vorschau der ersten zu prüfenden Datei zu öffnen (sonst den Ergebnisordner).
- **Aktionsleiste:** „Analysieren – Funde anzeigen“ steht neben „Schwärzen starten“, der Fortschrittsbalken
  in einer eigenen Zeile; das Sprachmodell wird im Hintergrund vorgeladen.
- **EXE:** `EXE-bauen.bat` packt die Wortlisten und alle Erkennungsregeln mit; fehlt in der EXE eine Regel,
  meldet die Analyse das, und die Ausgabe wird `_PRUEFEN`. Hilfetexte nennen in der EXE „Programmordner neu
  entpacken“ statt `Installieren.bat`.

### Behoben
- Bilder, Webseiten und andere Dateien, die keine PDF sind, aber die Endung `.pdf` tragen, konnten das ganze
  Programm zum Absturz bringen; sie werden jetzt vor dem Öffnen erkannt.
- Gedrehte Scans (90°, 180°, 270°) werden zuverlässiger in der richtigen Lage gelesen; bleibt der gelesene
  Text unplausibel, meldet das Programm das, und die Ausgabe wird `_PRUEFEN`.
- Sehr große Seiten (Handyfotos, Pläne) ließen sich teils gar nicht bearbeiten oder brauchten mehrere
  Gigabyte Arbeitsspeicher; sie werden jetzt mit begrenzter Auflösung gelesen. Reicht der Arbeitsspeicher
  trotzdem nicht, liest das Programm die Seite mit halber Auflösung und warnt; die Ausgabe wird dann
  `_PRUEFEN`.
- Ließ sich eine Seite wegen eines Fehlers im Aufbau der PDF nicht schwärzen, endete die Bearbeitung der Datei
  ohne Ausgabe. Jetzt wird die Seite als Bild neu erzeugt und dabei geschwärzt (ihr Text lässt sich danach
  nicht mehr markieren, bleibt aber lesbar); gelingt auch das nicht, entsteht keine Ausgabe.
- Ein bestimmter Fehler im inneren Aufbau mancher PDFs ließ das Lesen einer Seite über zehn Minuten hängen;
  Analyse, Vorschau und Fotoerkennung umgehen ihn jetzt.
- Schräg eingescannte Seiten: Die Schwärzung folgt der schrägen Zeile und trifft Nachbarzeilen deutlich
  seltener.
- Textseiten: Die grauen Kästen sitzen an der Stelle, die geschwärzt wurde; vorher verdeckten sie teils
  Nachbarwörter zur Hälfte. Ist ein Nachbarwort doch teilweise verdeckt, meldet das Programm das als Hinweis.
- Unter Windows werden Nummern und Namen gefunden, in denen besondere Leer- oder Trennzeichen stehen (z. B. ein
  geschütztes Leerzeichen oder ein weicher Trennstrich).
- Sehr lange Ordner- und Dateinamen (Pfade über 260 Zeichen) funktionieren unter Windows beim Hinzufügen,
  Analysieren, Schwärzen und in der Zuordnungsdatei; was im Ordner nicht lesbar ist, steht mit Grund unter
  „nicht lesbar“.
- Texterkennung: Stürzt sie bei einer Seite ab, reißt sie das Programm nicht mehr mit; nach dem Beenden – auch
  nach einem Absturz des Programms – läuft sie nicht im Hintergrund weiter; mehrseitige Scans werden schneller
  gelesen (10-seitiger Scan auf dem Entwicklungsrechner: 18 statt 46 Sekunden).
- In „NACHNAME, VORNAME GEB. …“ wurde „GEB“ als Teil des Namens geschwärzt; der Geburtsname dahinter galt als
  eigene Person.
- Hinter „Versicherungsbestätigung Nr.“, „VB-Nr.“, „eVB-Nr.“, „Transferticket-Nr.“ und „Kartenprüfnummer“ blieb
  eine Nummer, die nicht die Form einer eVB, eines Transfertickets oder einer Kartenprüfnummer hat („123/24“,
  „HR-4711-B“, „TT-12345“), seit der neuen Erkennung lesbar; sie wird wieder geschwärzt.
- Ein leeres Feld „Geburtsname“ machte das nächste Feld-Etikett („PLZ, Ort:“, „Status“) zur Person, die im ganzen
  Lauf geschwärzt wurde; hinter „geb.“ wurden auch Wörter wie „In“, „Lt.“, Länder und Orte („geb. Polen“, „geb.
  Wien“, „Als geborener Kölner …“) und „Geb.“ für Gebäude („Standort Köln, Geb. Kantine“) zum Namen. Ein Feld-Etikett
  ist nie ein Geburtsname; Orte erkennt die Wissensbasis (neue Liste `orte.txt`).
- Hinter „Versicherungsbestätigung Nr.“, „VB-Nr.“, „eVB-Nr.“, „Transferticket-Nr.“, „…nummer:“ und
  „Kartenprüfnummer:“ blieben laufende Nummern mit Jahr („3/2025“, „12/345“, „2024/25“, „2023/2024“, „2019-20“) und mit
  Buchstabenvorsatz („KFZ-VB 12345“, „SF-TT 4711 0815“) auch nach der ersten Korrektur lesbar und ungemeldet; sie
  werden wieder geschwärzt, und die Restrisiko-Prüfung meldet sie.
- Hinter „Transferticket“ und „eVB“ wurden Telefonnummern, Internetadressen, Jahresbereiche, Datumsangaben, Beträge
  und Tarifcodes („PREMIUM2024“, „Transferticket: 2024/2025“, auch in einer Spalte „Transferticket“) als Kennung
  geschwärzt und im ganzen Lauf weitergegeben; der Wert eines anderen Etiketts davor („Hotline:“, „Tarif:“,
  „Kennzeichen:“) gehört diesem.
- Ein leeres Feld „Geb.-Name“ oder „Geburtsnamen“ machte das nächste Feld-Etikett („Geburtsland“, „Künstlername“)
  zur Person, „GEB.“ als Spaltenkopf einer Festbreiten-Liste den nächsten Kopf („STATUS“, „KLASSE“), und das Etikett
  „Prüfnr.“ wurde als Name geschwärzt – jeweils im ganzen Lauf. Ein Geburtsname, der zugleich ein Ort oder ein
  gewöhnliches Wort ist („geb. Deutsch“, „geb. Mallorca“), wird nur an seiner Stelle und in Personenkontext
  geschwärzt, nicht mehr in fremden Stellen („Korrespondenzsprache: Deutsch“). Die Restrisiko-Prüfung meldet keinen
  „möglichen Geburtsnamen“ mehr in Erläuterungen („Geburtsname ist Pflichtangabe.“) und hinter leeren Feldern
  („Geburtsname“ ⏎ „Beruf“, „Geburtsname: ⇥ Größe:“).
- Die Restrisiko-Prüfung meldete hinter „Transferticket“, „eVB“ und „CVC“ Tarifangaben als Wert („SF 12 / SF 8“,
  „250 Euro“), eine TÜV- oder DIN-Prüfnummer neben einer Kartenangabe galt als Kartenprüfnummer, eine kurze
  Kartennummer („Karten-Nr.: 1234“) wurde nicht mehr weitergegeben, und große Tabellen mit eVB- oder CVC-Spalte
  wurden quadratisch langsamer geprüft.
- Statuszeile: Nach dem Hinzufügen von Dateien zu einer schon analysierten Liste blieb dort „Dateien werden
  geprüft …“ stehen. Jetzt steht dort, wie viele Dateien noch nicht analysiert sind; kam keine neue Datei
  hinzu, bleibt die Meldung der Analyse stehen. Sie folgt derselben Regel wie die Sperre vor dem Schwärzen:
  Nach einer abgebrochenen Analyse steht dort nicht mehr „die bisherige Analyse gilt weiter“, und wird die
  neue Datei wieder entfernt, verschwindet „noch nicht analysiert“.
- Beenden während einer Schwärzung („Lauf läuft noch“ → „Ja“): Das Fenster schloss sofort, und im
  Ausgabeordner konnte ein Zwischenstand `.anonym_tmp_…_a.pdf` liegen bleiben – bei großen Scans die ersten
  Seiten geschwärzt, die übrigen wie im Original. Jetzt bricht das Programm den Lauf ab und schließt erst,
  wenn er aufgeräumt hat (höchstens etwa 20 Sekunden), und löscht beim Beenden zusätzlich eigene
  Zwischendateien, wo noch welche liegen können (in den Ordnern, in die der abgebrochene Lauf schrieb, oder
  wo sich nach einem Lauf eine nicht löschen ließ) – in Hintergrund-Threads: Auf ein nicht erreichbares
  Netzlaufwerk wartet das Löschen höchstens zwei Sekunden, der Ordner bleibt dann für den nächsten Start
  vermerkt (die Prüfung auf wartende Freigaben kann das Schließen dort trotzdem verzögern). Nach einem
  gewöhnlichen Lauf liest das Beenden keinen Ausgabeordner.
  Zwischenstände liegen nicht mehr im Ausgabeordner, sondern im Ordner für Arbeitskopien; Hilfsdateien enden
  auf `.tmp`, nie auf `.pdf`. Reste nach einem Absturz löschen der nächste Start (in den Ausgabeordnern, in
  die gerade geschwärzt wurde, und im gemeinsamen Zielordner, wenn er eingeschaltet ist), das Hinzufügen des
  Ordners oder das nächste Schwärzen dorthin – mit Meldung im Protokoll.
- Gemeinsam genutzte Ordner (Netzwerkfreigabe): Als verwaist galt eine Hilfsdatei, deren Prozess auf diesem
  Rechner nicht lief – das trifft auf die eines anderen Rechners praktisch immer zu. So konnten Programmstart,
  Hinzufügen und Schwärzen die Hilfsdatei eines Kollegen mitten in seinem Lauf löschen (seine Datei endete ohne
  Ausgabe mit Fehler), und der Start meldete das als eigenen Absturz. Jetzt enthält der Name jeder Hilfsdatei
  eine Kennung des Rechners (kurzer Hash des Rechnernamens); die eines anderen Rechners – und eine ohne Kennung
  aus einer älteren Testversion – gilt erst nach 24 Stunden als verwaist. Als Rest eines eigenen Absturzes
  meldet der Start nur noch Hilfsdateien der eigenen abgestürzten Sitzung.
- **Visual-C++-Laufzeit (Skript-Version):** PyMuPDF braucht `msvcp140.dll` aus der „Microsoft Visual C++
  2015-2022 Redistributable (x64)“; Python bringt nur `vcruntime140.dll` und `vcruntime140_1.dll` selbst mit.
  Fehlte die Laufzeit (frisch eingerichtete Rechner, Windows-Sandbox, schlanke Firmen-Rechner), installierte
  `Installieren.bat` bei jedem Lauf alles neu und nannte eine falsche Ursache; das Startskript meldete „Paket
  fehlt“. Jetzt prüft `Installieren.bat` die Laufzeit vor den Paketen – das gefundene Python lädt die DLLs zur
  Probe selbst, so wie PyMuPDF sie sucht: zuerst im Ordner von python.exe, dann im Systemordner. Ein Rechner,
  auf dem `vcruntime140_1.dll` nur neben python.exe liegt (VC++ 2015/2017) oder der die Laufzeit im eigenen
  Ordner hat (conda), wird also nicht abgewiesen. Fehlt sie, bietet `Installieren.bat` die Installation per
  winget an; ohne winget nennt die Meldung zuerst `vc_redist.x64.exe` von Microsoft. `EXE-bauen.bat`
  prüft die Laufzeit vor dem Bau ebenso. Startskript und `werkzeuge/pruefe_installation.py` nennen bei „DLL
  load failed“ die Laufzeit als Ursache; das Prüfskript gibt die Abhilfe je Paket an (PyMuPDF, spaCy, tkinter).
  Andere Fehler beim Laden von PyMuPDF (z. B. eine vom Virenscanner gesperrte Datei) landen wie jeder
  unerwartete Fehler mit Details in der `fehler.log`. Die EXE bringt die Laufzeit weiterhin mit;
  `EXE-bauen.bat` und der EXE-Job der GitHub-Action prüfen das jetzt.
- **OCR-Sprachdatei:** Die mitgelieferte `deu.traineddata` geht wieder vor (wie seit 0.2.0 beschrieben). Hatte
  der Rechner eine andere Tesseract-Installation, deren `TESSDATA_PREFIX` nur `eng.traineddata` enthielt, las
  das Programm alle Scans englisch, jede Scan-Ausgabe hieß `_PRUEFEN`, und die Warnung riet fälschlich zum
  Neu-Entpacken. `TESSDATA_PREFIX` ist jetzt nur Ersatz, wenn die mitgelieferte Datei fehlt; die Warnung und
  `pruefe_installation.py` nennen den Ordner, aus dem die OCR tatsächlich liest.
- **Netzwerkfreigaben:** `Installieren.bat` und `EXE-bauen.bat` laufen auch aus einem per UNC-Pfad
  (`\\server\freigabe\…`) geöffneten Ordner (`pushd` statt `cd /d`); vorher meldeten sie fälschlich „Dateien
  fehlen – ZIP komplett entpacken“. `Starten.bat` arbeitet mit vollständigen Pfaden.
- **Schreibgeschützter Programmordner:** Ließ sich `.python_pfad.txt` nicht schreiben, brach die Einrichtung
  der Desktop-Verknüpfung mit einem Python-Fehler ab, und `Installieren.bat` nannte PowerShell als Ursache.
  Jetzt bleibt es bei einem Hinweis (`Starten.bat` sucht Python selbst), und die Verknüpfung wird angelegt.

### Sicherheit
- Manche PDFs (z. B. aus LibreOffice) enthielten nach dem Schwärzen das ungeschwärzte Originalbild unsichtbar
  weiter – etwa einen ganzen Scan mit Gesicht, Name und Anschrift –, ohne dass das Programm warnte. Solche
  Bilder werden jetzt in jeder Schutzstufe entfernt, und die gespeicherte Ausgabe wird darauf noch einmal
  geprüft.
- Beschädigte PDFs werden vor dem Schwärzen repariert; die Ausgabe heißt dann `_PRUEFEN`. Zeigt sich der
  Schaden erst während des Schwärzens, entsteht keine Ausgabe, weil dabei Schwärzungen verloren gehen können.
- Seiten, deren Text in der PDF falsch gespeichert ist (die Datei enthält nicht die Zeichen, die auf der Seite
  zu sehen sind), werden per Texterkennung gelesen und geschwärzt; sonst blieben dort z. B. Name und IBAN
  lesbar. Die Ausgabe heißt dann `_PRUEFEN`.
- Text, den die Schwärzung sonst nicht erreicht, wird per Texterkennung gelesen bzw. entfernt: als Grafik
  gezeichneter Text, Text in Füllmustern, Text außerhalb des sichtbaren Seitenbereichs und abgeschnittener
  Text (z. B. ein zu langer Eintrag in einem Formularfeld).
- Gedrehte Seiten, von denen nur ein Ausschnitt sichtbar ist, zeigen in der Ausgabe genau denselben
  Ausschnitt; Weggeschnittenes wird nicht sichtbar.
- Die Ausgabe entfernt weitere versteckte Angaben, in denen Namen oder Nummern stehen können: unsichtbare
  Ersatztexte im Seiteninhalt (z. B. für Vorleseprogramme), Seitenbeschriftungen, als E-Rechnungsdaten
  angehängte Dateien (ZUGFeRD), Angaben wie Autor oder Titel an eingebetteten Bildern, Kamera- und
  Aufnahmeangaben in eingebetteten Fotos sowie die Kennung der Datei.
- `fehler.log` kürzt Pfade meist auf den Dateinamen; manche Windows-Pfade (z. B. sehr lange) stehen aber noch
  vollständig darin, und Dateinamen enthalten oft Kundennamen – `fehler.log` vor dem Weiterleiten ansehen.

### Für Entwickler (Tests, CI, Messwerkzeuge)
- Neuer Aufbau: ein Seitenmodell für Analyse, Schwärzung und Selbstkontrolle (`seitenmodell.py`),
  Erkennungsregeln als Module mit Register und Rückfallliste für die EXE (`anonymisierer/detektoren/`),
  Wissensbasis (`wissen.py`, 17 Wortlisten in `anonymisierer/daten/`), dazu `kundenliste.py`,
  `restrisiko.py`, `nebenkanaele.py`, `bilder.py`, `fotos.py`, `vorschau.py`, `vorschau_fenster.py` und
  `auftrag.py` (welche Funde und Stellen die Oberfläche an die Schwärzung gibt; auch für
  `werkzeuge/benchmark.py --weg oberflaeche`).
- Technik hinter den Korrekturen: Seiten werden ohne Strukturbaum gerendert (ein Zyklus darin ließ MuPDF 1.28
  über zehn Minuten hängen); scheitert `apply_redactions` an einer Seite (z. B. zyklische Form-XObjects),
  wird sie mit 200 dpi als Bild geschwärzt (`SEITE_ALS_BILD`); `analyse.reparatur_erzwingen` lässt MuPDF vor
  der ersten Änderung reparieren (`DATEI_REPARIERT`); Textebenen ohne gültige ToUnicode-Zuordnung
  (`TEXTEBENE_UNLESBAR`), Vektortext und Text in Kachelmustern gehen über die OCR; `bilder.bildreste_entfernen`
  leert vor dem Speichern jedes Bild, das keine Seite zeichnet (geerbte oder geteilte Ressourcen), und prüft
  die gespeicherte Datei nach; graue Kästen werden nach `apply_redactions` an der gemessenen Lage der Zeichen
  gezeichnet (MuPDF 1.28 verschiebt den Rest einer TJ-Zeile); OCR-Arbeitsprozesse haben einen Eltern-Wächter
  und fallen nach einem Absturz nicht mehr in den Hauptprozess zurück. Neu entfernte Nebenkanäle
  (`nebenkanaele.py`; Strukturbaum, Ebenennamen, JavaScript und Aktionen sowie XMP an Seiten entfernte schon
  0.2.0): /ActualText-, /Alt- und /E-Ersatztexte in Inhaltsströmen, PageLabels, /AF-Anhänge (ZUGFeRD),
  Artikelthreads, XMP an Bildern und Schriften, EXIF/XMP/IPTC in JPEG/JPX, Inhalte außerhalb von
  CropBox/MediaBox, /ID.
- Tests: von 382 auf über 3000, u. a. Layouts für 1366×768, 1024×768 und 1920×1080 bei mehreren
  Skalierungen sowie Windows-Pfade und -Schriften; Laufzeittests prüfen das Wachstum über die CPU-Zeit
  (`tests/zeitmessung.py`).
- CI: Zeitgrenze 300 s je Test (`pytest-timeout`, neu in `requirements-dev.txt`), die 15 langsamsten Tests im
  Bericht, unter Windows `-v`, Benchmark-Bericht als Artefakt `benchmark-bericht-<os>` auch bei Fehlschlag.
- Werkzeuge: Der Entwicklungs-Benchmark `werkzeuge/benchmark.py` (Paket `werkzeuge/benchmark/`) erzeugt
  synthetische Versicherungsdokumente samt Scans und versteckten Teilen und bewertet die Ausgabe über alle
  Kanäle; `tests/test_benchmark.py` nutzt ihn als Qualitätstor (12 Dokumente). Dazu
  `werkzeuge/wissen_pflegen.py` (Wortlisten) und `werkzeuge/programmsymbol.py` (`icon.ico`).
- Kommentare im Code verweisen auf Entwicklungsunterlagen (`CONTRACT_V2.md`, `BENCHMARK_SCHEMA.md`, „Vertrag
  Abschnitt …“), die nicht im Repository liegen.

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
- Neuer Job **`exe`** (windows-latest; für jeden Pull Request, von Hand oder für Tags `v*`): führt
  `EXE-bauen.bat` aus, prüft OCR-Sprachdatei, Sprachmodell, Lizenztexte und ZIP-Inhalt, startet die
  EXE probeweise (Fenster da, keine `fehler.log`) und lädt die ZIP als Artefakt hoch.
- Layout-Test: Auf Bildschirmen unter 1366×768 (Windows-Runner: oft 1024×768) werden nur die
  Skalierungen übersprungen, die Windows dort gar nicht anbietet (mindestens 720 Bildzeilen
  nach Skalierung); ab 1366×768 und im 1366×768-Szenario prüft der Test unverändert.
- Actions auf die Node-24-Ausgaben angehoben (`actions/checkout@v5`, `actions/setup-python@v6`,
  `actions/upload-artifact@v6`); die Node-20-Warnung im Protokoll entfällt.

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
