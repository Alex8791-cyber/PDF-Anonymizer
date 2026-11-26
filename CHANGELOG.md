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
- **Sechs neue Kategorien** (mit den fünf aus Runde 5, siehe unten, 31 statt 20): ausländische Anschriften und
  Kennzeichen `[AUSLAND]`, Orte ohne PLZ `[ORT]`, Beruf `[BERUF]` und Arbeitgeber `[ARBEITGEBER]` (bei Personen),
  Diagnosen und ICD-Codes `[DIAGNOSE]`, Medikamente `[MEDIKAMENT]`. Gesundheitsdaten erkennt das Programm nur
  als bekannte Begriffe der Wortlisten, ICD-10-Codes und Körpermaße, jeweils im Gesundheitszusammenhang.
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
- **Erkennung: Kennungen allgemein (Domänen-Durchsicht aller Maklersparten).** Dieselbe Regel „Etikett + Wert“ gilt
  jetzt für JEDES Kennungs-Etikett, in Erkennung und Restrisiko-Prüfung gleich (`kennungsformen.allgemeine_kennung`):
  Zwischenwörter bis zu einer Ankündigung („Personalnummer beim Arbeitgeber: 4711“, „Vertragsnummer beim
  Vorversicherer: …“, „Seriennummer laut Rechnung: …“, „Führerschein Klasse 3 vom 12.04.1985, Nr. 355/85“), Schluss am
  Satzende, an einem anderen Etikett oder Feld und nach 8 Wörtern. Neue Wertformen hinter einem Etikett:
  Tausenderpunkt-Gruppen ohne Währung („Kundennummer: 4.711.208“, auch in der Spalte unter „Vertragsnr.“), Codes mit
  Trennern und wenigen Ziffern („Geräte-ID: TLX-KQ8B-ZR3M“), Buchungscodes („PNR: KXQRZN“, nie ein Wort wie
  „STORNO“), „#“ als Trenner, eine Laufnummer vor dem Wert („IMEI 1: …“); ohne Etikett MAC-Adresse, EID einer eSIM,
  Nummer im Marktstammdatenregister („SEE912345678901“), gruppierte Steuer-ID mit gültiger Prüfziffer und
  Aktenzeichen eines Gerichts mit Gerichtswort im Satz („Das Verfahren 3 C 456/24 …“). Rund 190 neue Etiketten
  (Ausweis- und Fahrzeugpapiere ohne „Nr.“ mit Dokumentform, Konten, Geräte, Tiere, Register, Reise, „BG-Nummer“,
  „Vorg.-Nr.“, „Nummer der Bedarfsgemeinschaft“, „HKP Nr.“),
  Tabellen mit nur einem Kennungs-Etikett im Kopf („Gegenstand ⇥ Kaufpreis ⇥ Seriennummer“), HRA-Nummer und USt-IdNr.
  eines Einzelkaufmanns (e.K., „Inhaber:“), die FIN auf Scans mit O statt 0 („WFOEXX…“) und die Passnummer der
  Sichtzone über eine verlesene MRZ. Weniger Über-Schwärzung: Gebühren- und Katalogspalten (GOZ, GOÄ, EBM, BEL) und die
  Pharmazentralnummer (PZN, keine Telefonnummer mehr), Fahrzeugschlüssel (HSN/TSN, „Schlüssel-Nr. 2.1/2.2“),
  Flug-, Sitzplatz- und Zimmernummern, die Nummer einer Vorschrift hinter einem Etikett („Registrierungsnummer: § 34d
  Abs. 1 GewO“, auf Scans „8 34d …“); eine IMEI ist eine Kennung, keine Kreditkarte.
- **Fünf neue Kategorien (Domänen-Durchsicht, Runde 5):** IP-Adressen `[IP-ADRESSE]` (IPv4 mit gültigen Oktetten und
  IP-Bezug, IPv6 – nicht direkt hinter einem Versionswort, keine Vertragsnummern mit Punkten), Zugangsdaten `[ZUGANGSDATEN]`
  (Benutzername/-kennung, Kennwort, PIN, Aktivierungs- und Freischaltcode hinter ihrem Etikett), Profil- und Kontonamen
  `[PROFIL]` (@-Namen, „eBay-Name:“, „Telegram:“, Profil-Links, Kunden-, Vertrags- und Namensangaben in Links),
  Standort-Koordinaten `[STANDORT]` – alle vier in jeder Schutzstufe angehakt – und Religion/Konfession `[RELIGION]`
  (Kirchensteuermerkmal „rk“/„ev“, auch unter dem Spaltenkopf „Konf.“) wie Gesundheitsdaten: in „Ausgewogen“ und „Hoch“
  nur angeboten (Meldung RELIGION), in „Maximal“ angehakt. Eine kurze PIN und ein Kirchensteuermerkmal gelten wie die
  Kartenprüfnummer nur hinter ihrem Etikett („4711“ anderswo im Dokument bleibt stehen). Gespeicherte Einstellungen
  bleiben gültig; die neuen Kategorien gelten dort als an, Religion wie oben nur in „Maximal“. Außerdem: verschleierte E-Mail-Adressen („name (at) web
  (punkt) de“) und Flurstück, Grundbuchblatt und Gemarkungsnummer.
- **Kfz-Kennzeichen (Runde 5):** Versicherungskennzeichen („435 GHT“, „435GHT“, zweizeilig) hinter Kfz-Etiketten, im
  Satz und in Spalten mit Kfz-Kopf; Komposita mit Fahrzeugbezug als Kfz-Etikett (Versicherungs-, Kurzzeit-, Oldtimer-,
  Saison-, Ausfuhr-, Händler-, Wechselkennzeichen, Versicherungsplakette, „Kennzeichen-Nr.“) – nicht Gefahrgut-, Prüf-
  oder Qualitätskennzeichen; Kurzzeit-, rote und Ausfuhrkennzeichen; „RO - KL 2207“, „ro-xt 913“ und die Kompaktform
  „ROKL2207“ hinter einem Kfz-Wort. Ohne Etikett gilt ein Kennzeichen nur mit amtlichem Unterscheidungszeichen (neue
  Liste in der Wissensbasis): Modellcodes wie „KTM RC 390“ oder „DAF XF 480“ bleiben stehen, ebenso Marke und Modell als
  Name („Suzuki GSX-R“). Ausländische Kennzeichen im Satz hinter einem Fahrzeugwort werden mit Länderhinweis geschwärzt,
  sonst von der Restrisiko-Prüfung gemeldet. Ein Datum hinter dem Etikett („Kennzeichen AM 29.03.2025“ in Versalien) ist
  kein Kennzeichen.
- **Anschriften (Runde 5):** vierstellige PLZ mit Ort (Österreich, Schweiz) hinter einer Straße, mit Länderhinweis oder
  einem Ort der Nachbarländer („8002 Zürich“, auch mehrteilig ganz: „6060 Hall in Tirol“, „4820 Bad Ischl“; ein Ort, der
  zugleich ein deutsches Wort ist, nur am Ende der Angabe – nicht „1500 Zug um Zug“, „5000 Meilen gutgeschrieben“),
  Straßen mit vorangestelltem Straßentyp („Str. Memorandumului nr. 27“, „Calea Victoriei nr. 12“, „bul. Vitosha 15“),
  sechsstellige PLZ mit Länderhinweis. Nicht mehr als Anschrift: Straßenklassen mit Nummer („Auf der A 8“, „B 15“, „L
  2080“, „BAB 9“); PLZ ⇥⇥ Ort über einen Spaltentrenner nur mit Straße davor (auch mit Hausnummernbereich „33-35“),
  unter dem Spaltenkopf „PLZ“ oder mit bekanntem Ort – in „Kd.-Nr. ⇥⇥ Name“ ist „10471 ⇥⇥ Ruhstorfer“ keine Anschrift.
  Hinter „Unfallort:“ ist „BAB 9, km 381,2“ weder Straße noch Ort.

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
- **Ausgefüllte Kammfelder auf Scans** (Kästchen „je Kästchen ein Zeichen“, Block- und Handschrift): Die
  Texterkennung las sie meist nicht – die Kästchen galten ihr als Grafik, Werte und oft auch die Feldnamen daneben
  fehlten, die Werte blieben unbemerkt lesbar. Jetzt sucht die OCR Kästchenreihen im Bild (geschlossen, als Kamm mit
  kurzen Wänden, unten offen; auch schräg, mit Gruppenlücken wie bei der IBAN und als Fax mit unterbrochenen Linien –
  ein Raster ganz ohne Linien, dessen Wände an Ober- und Unterkante keine Tinte tragen, wird nicht erkannt), übermalt
  nur deren Linien und liest die Felder ein zweites Mal für sich. In der Stufe „Hoch“
  wird der Inhalt eines Felds hinter einem Feldnamen für Personenangaben geschwärzt (Name, Anschrift, Telefon,
  Geburtsdatum, Kennungen – auch verlesene Feldnamen). Felder mit einem Feldnamen ohne Personenbezug und einem Wert
  in dessen Form (Antragsdatum der letzten 30 Jahre, Anzahl, Betrag, Kilometerstand, Tarifgruppe) und leere Felder –
  auch mit vorgedrucktem Ausfüllhinweis („TTMMJJJJ“) oder einem Kreuzchen – bleiben lesbar und ohne Verdacht; Teile
  eines Datums („Tag“, „Monat“, „Jahr“) gelten mit dem Feldnamen davor bzw. darüber („Geburtsdatum“). Was in der
  Ausgabe in einem gefüllten Kästchen noch zu sehen ist – hinter einem Personen-Feldnamen, ohne erkennbaren Feldnamen
  oder unlesbar –, meldet die Restrisiko-Prüfung an dieser Stelle (Ausgabe `_PRUEFEN`); dafür bekommt sie Lage und
  Füllung der Felder aus dem Original. Textzeilen und Schreiblinien mit Handschrift darauf gelten nicht als Kammfeld;
  eine Tabelle mit gleich breiten schmalen Zellen (bis 12 mm) kann als Kammfeld gelten – ihr Inhalt wird dann wie der
  eines Kammfelds behandelt (meist gemeldet). Gemessen auf neun Kammfeld-Scans der Entwicklungskorpora: Kernwerte
  entfernt 29 → 92 von 106, stille Lecks 0; auf eigenen und neu erzeugten Formularen siehe Abschnitt „Für Entwickler“.
- **Kurze Werte in Kammfeldern der Textebene und Kundenblöcke von EDV-Ausdrucken:** Eine Hausnummer mit ein oder
  zwei Zeichen allein in ihrem Kammfeld („1 3“ unter „Hausnr.“) blieb lesbar – gesperrte Folgen zählten erst ab drei
  Zeichen. Jetzt wird ein so kurzer Wert hinter einem Feldnamen geschwärzt, wenn er als Hausnummer (Ziffer, ggf.
  mit Buchstabe) bzw. als Name aus zwei Buchstaben passt; Zählfelder, Kürzel und Kreuzchen bleiben lesbar. Stehen
  über einem Kammfeld mehrere Feldnamen derselben Art („Straße, Hausnr.“ über Straßen- und Hausnummernfeld), gilt
  die Zeile als Feldname (vorher: mehrdeutig, Wert ungeschwärzt). Auf gescannten EDV-Ausdrucken galt die
  Kundenanschrift als Firmenanschrift, wenn die OCR den Namen hinter „VERSICHERUNGSNEHMER“ in zwei Zellen las
  („NWOSU, ⇥ TESFAY“) und im Block „BANKVERBINDUNG“ stand; breite Lücken im Namen zählen jetzt wie ein Leerzeichen.
  Mitarbeiterzeilen („Ansprechpartner“) und Briefköpfe mit Registerangaben behalten ihre Firmenanschrift.
- **Gegenprüfung der Zusammenführung (Runde 5):** Was die zwei Prüfer am zusammengeführten Stand fanden, ist allgemein
  behoben – je Befund mit Abwandlungen und Gegenproben in `tests/test_gegenpruefung_r7.py`:
  - Verluste der Zusammenführung: der Ort hinter der Person eines Personen-Etiketts („Einweisender Arzt: Dr. …,
    Gaimersheim“), der Name hinter einer Berufsbezeichnung im Satz („Der Glaser Eibl hat …“, auch in der
    Selbstkontrolle) und Folgeseiten einer Tabelle ohne Kopf (nur mit Hinweis „Fortsetzung“ oder bis zum Seitenende).
  - Wieder geschwärzt bzw. gemeldet wie vor der Runde: Mannheimer Quadrate („L 14, 16“ hinter „Anschrift:“, in der
    Anschriftenzeile und im Feld C.1.3); Familiennamen, die zugleich Marke oder Rasse sind („Neff“, „Miele“,
    „Kreidler“) im Grußblock, in Personenspalten, im Feld C.1.1 und hinter Personen-Etiketten – eine Sache nur mit
    Sachbeleg in der Zelle („Mofa Simson“); eine Person in der Spalte „Versicherer“/„Anbieter“/„Krankenkasse“ (Vor- und
    Nachname, „(privat)“, „(Vermittler)“); dort bleibt nur der Versicherer selbst lesbar, auch als Markenkern
    („Adam Riese“ aus „Adam Riese Versicherung“). Die Selbstkontrolle bestimmt Spalte, Grußblock und Personen-Etikett
    nach der Lage auf der Ausgabeseite.
  - Formulare in Spaltenblöcken (Texterkennung liest Feldcodes, Feldnamen und Werte je als eigenen Block): der Wert
    rechts auf derselben Höhe gehört zum Feldnamen; „Name oder Firmenname“ ist ein Personen-Etikett. Nur eine Wertzelle
    zählt: Ankreuzzeilen der Nachbarspalte eines Unfallberichts („Do parkte“, „El fuhr auf“) werden nicht mehr als Name
    neben „Name“/„Vorname“ geschwärzt; ein Wert mit Rechtsform („Elektro Schuster e.K.“) bleibt ein Wert.
  - Wochentag oder Monat als Familienname („Nachname: Freitag“, „Familienname: Mai“) wird hinter einem Namensfeld
    geschwärzt, auch auf Scans; als Datumsangabe („Rückruf am Freitag, 12.03.2025“, „Montag bis Freitag“, „im Mai 2025“,
    „Freitag, den 14.03.“) gibt die Weitergabe den Namen nicht mehr weiter – die Stelle bleibt als abgewählte Stelle
    sichtbar, außer mit Personenkontext in derselben Zeile („Termin mit Herrn Freitag“).
  - Ein Datum mit einem als Komma verlesenen oder vertippten Trenner und vierstelligem Jahr („17,03.1968“ in der
    Spalte „GEB-DATUM“ eines Scans, „Geburtsdatum: 17.03,1968“) wird wie „17.03.1968“ erkannt und von der
    Selbstkontrolle auch auf der Textebene gemeldet; Beträge („17,03 EUR“) bleiben stehen.
  - Zugangsdaten mit Zwischenwörtern („Kennwort für telefonische Auskünfte: …“), als Kompositum („WPA2-Kennwort“,
    „Router-Kennwort“, „App-Login“, „Administrator-Konto“), ohne Doppelpunkt mit Ziffer oder Sonderzeichen („Router-
    Kennwort Zirbe-Stube-77“), Geheimzahl, Zahlen- und Entsperrcode, „Code der Alarmanlage“ und „PIN“ als Spaltenkopf.
  - Kennung hinter einem Fundort („Mitgliedsnummer im Formular: …“, „… laut Anlage: …“), USt-IdNr. eines
    Versicherungsmaklers ohne „e.K.“, Profilnamen hinter Zwischenwörtern, Discord-Namen und Profil-Links ohne Protokoll
    („tiktok.com/@…“), Schweizer Anschriften mit Kantonskürzel („3600 Thun BE“), ein mehrdeutiger Vorname in einer
    Kinderliste („Max, 05.09.2016“), Berufe der Wissensbasis unter dem Spaltenkopf „Tätigkeit“ (der Nachbarkopf
    „Arbeitgeber“ wird nicht mehr als Beruf geschwärzt), die IP-Adresse in „Received:“-Kopfzeilen und die Anschrift in
    der Formularzeile des Kunden unter einer Spartenüberschrift („Kfz-Versicherung“ ⏎ „Versicherungsnehmer: …, …“);
    ein Adresszusatz zwischen Straße und PLZ derselben Zeile („Kaiserstraße 17, 3. OG links, 83022 Rosenheim“); ein
    Rest der Texterkennung („i“) zwischen zwei Reihen einer Scan-Tabelle beendet die Tabelle nicht mehr.
  - Weniger Über-Schwärzung: Spartenkürzel mit SF-Klasse bzw. Selbstbeteiligung („HP SF 12“, „RS SB 150“) sind keine
    Kennzeichen; Einzelwerte hinter „Breite“/„Länge“ mit Maßeinheit (auch ausgeschrieben: „Meter“, „lfm“, „Fuß“, „±“),
    „@“-Tarife ohne Plattform und Kalenderwörter im Familienkontext bleiben stehen; Viererpunktzahlen hinter Artikel-,
    Bestell- und Positionsnummern gelten nicht als IP-Adresse (eine Bestellnummer bleibt als Kennung geschwärzt);
    Konfession nur in „Maximal“ als Verdacht und nur, wenn die Kategorie gewählt ist.
  - Laufzeit: Unterschriftslinien aus Unterstrichen und lange Zeilen ohne Leerzeichen oder mit riesigen Lücken
    wachsen wieder linear (16 000 Zeichen „Ab-…“ 15,5 s → 0,6 s, „:“ 27,9 s → 0,3 s, Leerzeichen 5,9 s → 0,7 s,
    Tabulatoren 4,3 s → 0,7 s).
- **Nachprüfung der Zusammenführung (Runde 5, zweite Nachbesserung):** Was zwei frische Prüfer (Lecks; Über-Schwärzung,
  Laufzeit, Robustheit, Windows) und die Prüfung der Entwicklungskorpora fanden, ist allgemein behoben – je Befund mit
  Abwandlungen und Gegenproben in `tests/test_nachpruefung_r7.py`:
  - Stille Lecks: Mannheimer Quadrate hinter „Risikoort“, „Versicherungsort“, „Hauptwohnsitz“, „Halter“, „Abstellort“,
    im Feld C.1.3 und hinter „wohnt … in“ (ein doppelt belegtes Muster hatte die Etikett-Regel abgeschaltet; ein Test
    verbietet doppelte Muster je Modul); ein Wochentag oder Monat als Name hinter Personen-Etiketten, in Grußblock,
    Personenspalte und Kinderaufzählung, wenn kein Datumswort davor steht („Gesprächspartner: Freitag, 14.11.2026“, „Die
    Kinder August (9) und Juni (6)“); Familiennamen, die zugleich Marke sind, unter weiteren Grußformeln
    („Freundlichst“, „Servus“, „Danke und Grüße“), unter Personen-Spaltenköpfen („Anrufer“, „Mitglied“,
    „Gesprächspartner“) und im Satz („Kollege Hengst“); Personen in Organisations-Spalten („beim Vater Rauschenbach“,
    „Gruber Sepp“, „GbR Seidlmayr“, ein einzelner Familienname); Profilnamen im Satz („auf Instagram unter …“); Berufe
    im Satz („arbeitet in Teilzeit als …“); Zugangsdaten mit „ist ab sofort“, hinter „Displaysperre“, „WLAN-Schlüssel“
    und hinter einem Gegenstand („Garagentoröffner Code 1199“); Hof- und Hausnamen („Hof Hintermoser“, „beim
    Stögerbauer“ im Orts- oder Ereigniskontext, auch am Satz- oder Feldanfang: „Beim Stögerbauer ereignete sich …“,
    „Schadenort: Beim Stögerbauer“) und die mundartliche Folge „die Kölbl Resi“; die USt-IdNr. eines Vermittlers oder
    Freiberuflers so, wie die Texterkennung sie liest („DE28765432]“, „DE2876S4321“, „DE 2876 5432 1“ – nur hinter dem
    Etikett, mindestens sieben echte Ziffern); ein Kfz-Kennzeichen mit Mittel- oder Aufzählungspunkt als Trenner („RO ·
    KL 2207“ – so setzt eine Standardschrift ohne Gedankenstrich „RO – KL 2207“; dieselben Ausnahmen wie für das
    Leerzeichen); Kopf- oder Allerweltswörter
    als Familienname hinter „Familienname:“/„Geburtsname:“ und in Datenzeilen einer Namensspalte mit Vornamen oder
    Geburtsdatum („Stand“, „Summe“, „Termin“); Geburtsdaten mit Komma und zweistelligem Jahr hinter einem
    Geburts-Etikett („geb. 05.09,16“); Kinderlisten mit Orts- oder Monatsnamen („Paris, 02.02.2011“; nur Einträge direkt
    unter der Überschrift – „Aschaffenburg, 10.07.2025“ über der Unterschrift eines Antrags bleibt Ort und Datum); die
    Fortsetzung einer Tabelle, die die Vorseite ankündigt („Weitere Kinder siehe Folgeseite.“); die Hausnummer in der
    Folgezeile einer Scan-Zelle (eine Ziffer ist kein Rest der Texterkennung); Grad und Dezimalminuten, Plus Codes,
    „Green Card“ und „SNR“ (Seriennummer); ein Adresszusatz, der selbst ein Anschrift-Etikett ist, hinter „Neue
    Anschrift:“ („Lindenweg 9, Hinterhaus, 83229 …“); ein Straßenname allein auf seiner Zeile oder in seiner
    Tabellenzelle mit der Hausnummer vor der PLZ darunter („Edelweißstraße“ ⏎ „4, 83080 Oberaudorf“, auch auf Scans).
  - Selbstkontrolle: abgewählte Gesundheitsdaten oder Konfession nennen einen eigenen Grund für `_PRUEFEN`; ein Datum in
    einer Reihe aus lauter geschwärzten Namen (Folgeseite ohne Kopf; mit nur einem Namen, wenn das Datum direkt dahinter
    steht – „Rieke Moosbichler 22.02.2016“ – oder die Nachbarreihe genauso aussieht; das Briefdatum neben dem
    geschwärzten Empfänger zählt nicht), ein Familienname mit Artikel vor oder
    hinter einem Personen-Verb („war der Brandstetter am Steuer“, „saß der Haslbeck“), Marken im Personenkontext – auch
    unter einem Tabellenkopf mit nur einem Personen-Etikett („Anrufer ⇥ Anliegen ⇥ Rückruf bis“) –, Personen in
    Organisations-Spalten und dort auch eine Versicherer-Marke mit Vor- und Familienname („Adam Riese“), wenn die Zeile
    auf eine Person deuten kann („Kautionsbürgschaft“, Darlehen, „privat“ als eigenes Wort oder „Privatperson“; sie
    bleibt stehen, in Vergleichslisten und neben Sparten wie „Privathaftpflicht“ ohne Meldung) werden verortet gemeldet; eine Marke in einer Personenspalte bleibt gemeldet, wenn auf der Ausgabeseite die
    Platzhalter die Zellen einer Reihe verschieben („VW Caddy ⇥ Miele“ unter „Fahrzeug ⇥ Fahrer“ – die Lage auf der
    Seite entscheidet, nicht die Zellenzahl im Text); ein Platzhalter („[GEB-DATUM]“) gilt nicht mehr als Spaltenkopf,
    „Mitglied der …“ im Satz nicht als Etikett; Maße mit ausgeschriebener Einheit und Leerwörter („Geburtsname:
    Entfällt“) werden nicht gemeldet.
  - Weniger Über-Schwärzung: Ort hinter einer Person nur mit Ortsbeleg (Fachrichtungen wie „Orthopädie“ bleiben stehen);
    Adresszusatz nur mit Merkmal (OG, Whg., Hinterhaus, c/o …; „Augenzeugin“, „Privatkunde“ bleiben stehen); Quadrate
    nur mit Etikett, Wohnwort oder Mannheim direkt dahinter (AKB-Gliederung, Sitzplatz, Skizzenfeld, „A 8, 3 km“ bleiben
    stehen); Zugangsdaten ohne Mengen- und Längenangaben („3-mal“, „4-stellig“) und ohne Tarif- oder Rabattcodes;
    „Signal Iduna“ ist kein Profil-Etikett; Versionen hinter „from“/„von“ ohne Zugriffs- oder Host-Wort sind keine
    IP-Adresse; die Tätigkeit in einer Betriebstabelle (Firma, Umsatz) ist kein Beruf; Organisationssignaturen („Neff
    Kundendienst Süd“, „Ihr Miele Team“) und Privatbanken in der Spalte „Anbieter“ bleiben stehen; eine Präposition am
    Anfang eines Ortsfelds ist kein Ortsname („Schadenort: Vor dem Haus“, „Ort: Zum …“, „Unfallort: Hinter der
    Scheune“ – vorher wurde „Vor“, „Zum“, „Hinter“ als Ort geschwärzt).
  - Laufzeit: Quadrat-, Profil-, Beruf- und Ortsregeln und die Spaltensuche rechts neben Etiketten arbeiten in
    begrenzten Fenstern – linear auch bei 16 000 Zeichen je Zeile. Beim Schwärzen vieler Stellen in einer Zeile prüfen
    ein Gitter aus Höhenstreifen und Spalten (bereits geschwärzte Rechtecke, Nachbarwörter), je Zeile sortierte
    Buchstabenboxen (Freiraum der Platzhalter) und eine Menge statt einer Liste nur noch die Nachbarschaft: eine Zeile
    mit 800 Fundstellen 8,1 s → 3,6 s, drei Zeilen mit je 1100 Fundstellen 148 s → etwa 100 s. Den Rest kostet das
    Anlegen der Schwärzungs-Anmerkungen in PyMuPDF (jede neue Anmerkung durchsucht die vorhandenen); Seiten mit weniger
    als einigen hundert Fundstellen merken davon nichts.
- **Abnahme der Zusammenführung (Runde 5, dritte Nachbesserung):** Was die Abnahme an Abwandlungen der behobenen
  Befunde fand, ist allgemein behoben – je Befund mit Abwandlungen und Gegenproben in `tests/test_abnahme_r7.py`:
  - Stille Lecks: Zugangsdaten hinter einem Gegenstand mit Doppelpunkt, Komma, Gedankenstrich oder Klammer („Haustür:
    Code 1357“, „Tor zur Tiefgarage: Code 4455“, „Garage, Code 1199“, „Haustür (Code 1357)“), mit dem Gegenstand im
    Satzteil davor oder dahinter („Die Haustür hat den Code 1357.“, „Code 4455 für die Tiefgarage“, „Code Haustür:
    1357“) und als Zusammensetzung („Tiefgaragen-Code“, „Kellertürcode“) – nicht hinter einem anderen Substantiv
    („Alarmanlage defekt Fehler Code 4711“) oder einer Einordnung („Der Tarif hat den Code 1357.“); Hausnamen bei
    einem Schadenwort, auch als Zusammensetzung oder Verb („Wasserschaden beim Stögerbauer in Inzell“, „In der Nacht
    brannte es beim Moarhofer“), und mit einer Ortsangabe direkt dahinter („zum Huberbauer nach Anger“ – nur mit der
    Endung eines Hausnamens oder als bekannter Familienname: „zum Discounter nach Rosenheim“ bleibt stehen); Berufe im
    Satz mit „als … tätig“, „beschäftigt“ oder „gearbeitet“, „Tätig als …“ am Satzanfang und „verdient ihr Geld als …“
    („als Fahrer am Unfall beteiligt“ bleibt stehen); ein Mannheimer Quadrat hinter „nach“, „in“, „von“ oder „aus“ mit
    dem Umzug dahinter („ist im Mai nach S 2, 15 umgezogen“, „ist von S 2, 15 nach T 4, 12 umgezogen“); Namen unter
    einer Grußformel mit Herkunft („Grüße aus dem Allgäu“, „Schöne Grüße aus dem Urlaub“, „Gruß vom Chiemsee“ – in
    Erkennung, Briefstruktur und Selbstkontrolle gleich); ein Name direkt hinter einem Personenwort ohne Begleiter
    („Laut Nachbar Grohe war …“, „Rücksprache mit Nachbar Grohe“ – nicht über eine Tabellenzelle hinweg: „Mieter ⇥
    Objekt“ bleibt Kopfzeile).
  - Scans: Steht ein Feldname allein in einer Spalte aus Feldnamen, gilt der Eintrag rechts daneben auf derselben Höhe
    als Rohwert, wenn die Texterkennung ihn nicht als Wert lesen kann („Steuer-ID:“ ⇥ „Bız11sar066“, „Geburtsdatum:“ ⇥
    „110.11.1984“ mit dem Kästchenrand als „1“, eine E-Mail-Adresse mit Leerzeichen) – mit denselben Ausschlüssen wie
    der Rohwert darunter (Füllwerte, Hinweise, das nächste Feld) und nur für einen Feldnamen am Anfang seiner Zeile
    („6. Versicherungsnehmer: Name“ ist eine Überschrift; das Kästchen „☐ parkte“ der Unfallumstände rechts daneben
    bleibt stehen). Ebenso gilt ein Beruf der Wissensbasis rechts neben dem Feldnamen „Beruf“ als Wert („6 ⇥ Beruf“ |
    „Hufschmiedin selbständig“): Wurde ein anderer Wert desselben Formulars geschwärzt, fiel dessen Verdachtsmeldung
    weg, und der nicht erkannte Beruf blieb still. Im Entwicklungskorpus s7 werden so 11 weitere Kernwerte entfernt
    (Anträge 036 und 037), in s3x 2 (Antrag 043: BIC, Kindergeldnummer); die Steuer-ID in 037 war in allen Ständen ein
    Leck.
  - Selbstkontrolle: ein unbekannter Familienname auf „-er“ oder „-erin“ direkt hinter „saß der“, „lenkte die“,
    „gefahren ist der“ … („Am Steuer saß der Hinterstoißer“, „… die Hinterstoißerin“) und ein Quadrat hinter „nach“
    werden verortet gemeldet; „Beifahrer“, „Fahrer“, „Gutachter“, „Mieter“, mehrdeutige Nachnamen („saß der Winter“)
    und Rollen-, Fahrzeug- und Gerätewörter auf „-er“ („rief der Anwohner“, „fuhr der Radler“, „fuhr der Bagger“ –
    „Anwohner“ und „Mitbewohner“ wurden vorher über die Namensgestalt gemeldet) bleiben ohne Meldung. Ein Beruf der
    Wissensbasis hinter „als“ in einem Satz über eine Person wird gemeldet, auch ohne Wort der Erwerbstätigkeit („Sie
    ist als Hebamme bei der Klinik in Traunstein.“, „Er hilft am Wochenende als Kellner aus.“) – nicht Rollen im
    Vorgang oder in einer Firma („als Fahrer am Unfall beteiligt“, „als Makler für Sie tätig“, „als Inhaber“) und
    nicht ohne Person im Satz („Als Arzt im Sinne dieser Bedingungen gilt …“). „Fortsetzung umseitig“ und „umstehend“
    kündigen die Fortsetzung einer Tabelle an (vorher nur verortet gemeldet).
  - Laufzeit: Die Regel „Gegenstand vor Code“ sucht nur in einem Fenster vor „Code“ (eine Zeile aus 3 000 „Code der
    Alarmanlage“ 12,9 s → 1,9 s); der Firmenbeleg einer Anschrift wird je Zeile einmal bestimmt statt je Treffer über
    den Zeilenanfang (32 000 Zeichen Kennzeichen-Kandidaten 17,3 s → 2,7 s, 16 000 Zeichen Anschriften in einer Zeile
    6,2 s → 0,5 s); Etiketten einer Zeile und das nächste Etikett unter einem Wert werden über sortierte Anfänge
    gefunden (32 000 Zeichen „Name“-Zeilen 12,0 s → 4,3 s); eine E-Mail-Adresse beginnt nur am Wortanfang (ein langes
    Wort ohne „@“ wuchs quadratisch). Neue Wachstumstests (Analyse 2 000 gegen 16 000 Zeichen, einzelne Regeln 4 000
    gegen 32 000) prüfen diese Formen und die der Nachprüfung B.
- **Zweite Abnahme der Zusammenführung (Runde 5, vierte Nachbesserung):** Zwei Regeln der dritten Nachbesserung ließen
  Werte durch, die vorher geschwärzt oder gemeldet waren, und mehrere neue Regeln schwärzten zu viel. Behoben, je
  Befund mit Abwandlungen und Gegenproben in `tests/test_abnahme2_r7.py`:
  - Stille Lecks (Regressionen): Ein Zugangscode hinter einem Gegenstand in Klammern oder Anführungszeichen, mit
    doppeltem Gedankenstrich, Pfeil oder Schrägstrich („(Haustür) Code 1357“, „Garage (Tor) Code 4419“, „Schlüsselbox
    (links neben der Tür) Code 2468“, „Eingangstür–– Code 8264“, „Haustür -> Code 1357“) wird wieder geschwärzt, auch
    wenn die OCR den Gedankenstrich als Bindestriche direkt am Wort liest („Eingangstür-- Code 8264“). Ein
    unbekannter Familienname mit Artikel, der auf ein Rollenwort endet („saß der Kirchsteiger“, „lenkte der
    Hochsteiger“, „fuhr der Grubhalter“), wird wieder gemeldet: Nur ganze Rollen-, Fahrzeug- und Gerätewörter bleiben
    ohne Meldung – das Grundwort allein („Schwager“, „Radler“), mit Vorsilben („Anwohner“, „Mitbewohner“, „Aufsteiger“)
    oder hinter einem Bestimmungswort mit Vorsilbe („Hausbewohner“), nicht schon jede Endung.
  - Weitere Lecks: Zugangscode hinter einem Gegenstand mit Nummer, Klammerzusatz oder in der Zeile davor („Tor 2: Code
    1593“, „Tresor (Keller) Code 3141“, „Haustür:⏎Code 1357“), hinter Schlüsselbox, -safe, Keller und Einfahrt und mit
    der Bedienung eines Schlosses („Die Alarmanlage schaltet man mit 6482 aus.“); ohne sicheren Gegenstand („Code:
    7319“, „Schlüsselsafe an der Garage, Code 8642“, „…öffnet die Tür, Code ist 4711.“) und hinter einem Schloss als
    Feldname ohne „Code“ („Haustür: 1357“, „Tor zur Tiefgarage:⏎4455“) meldet die Selbstkontrolle die Ziffern. Hausnamen auch ohne Ereignis
    hinter „beim“/„vom“/„zum“ mit der Endung eines Hausnamens, auch gebeugt („Er arbeitet beim Wastlbauer“, „beim
    Gruberwirt“, „beim Kammerloher“, „Hof des Zellerbauern“). Berufe auch in „übt den Beruf der … aus“, „Von Beruf ist er
    …“, „hauptberuflich …“, „nebenbei …“ und im Nebensatz („seit sie Lehrerin ist“). Quadrate hinter „aus … ausgezogen“, „Umzug von“,
    „kommt aus“, mit einem Umzugsverb auch ohne Person im Satz („ist nach S 2, 15 umgezogen“, „Zum 1. Mai nach T 4, 12
    verzogen.“) und hinter einem Namen in Briefkopf oder Absender („Resi Huber · Q 5, 12“); die Selbstkontrolle meldet
    Quadrate auch hinter „an“ („Zustellung bitte an R 3, 4“). Unterzeichner in der
    Grußzeile selbst („Grüße von Grohe“, „Viele Grüße aus dem Allgäu, Rowenta“) und Grüße mit längerer Herkunft. Eine
    angekündigte Fortsetzung einer Personentabelle zählt auch mit einer einzigen Reihe auf der Folgeseite.
    Ein Doppelname zählt hinter einem Personenwort als Name, wenn ein Teil ein Name ist und keiner ein Sachwort
    („Nachbarin Fischbacher-Zöttl rief die Feuerwehr.“; nicht „Kunden Service-Center“).
    Hinter einem Personenwort mit Begleiter entscheidet die Wortart im Satz (Sprachmodell): ein Eigenname wird
    geschwärzt („beim Nachbarn Grohe war alles trocken“, „mit dem Zeugen Grohe telefoniert“), ein Substantiv bleibt
    stehen („dem Nachbarn Wasser abgegraben“, „dem Kollegen Geld geliehen“). Ein Zugangscode unter einer Zeile, die nur
    ein Schloss nennt („Haustür⏎Code 1357“, „Tor zur Tiefgarage⏎Code 4455“), wird geschwärzt.
    Selbstkontrolle: Familienname mit Zwischenwörtern („saß wohl der …“, „Gefahren ist laut Polizei die …“, „saß nach
    Angaben der Polizei der …“, „Gefahren hat das Auto der …“) und am
    Satzanfang („Der Lackner hat den Wagen gefahren.“), Rollen wie Fahrer, Betreuerin, Vertreter als Beruf, wenn der
    Satz von Arbeit spricht („fährt nachts als Fahrer für einen Paketdienst“, „als Berater bei einer Bank“), Name in
    einer Partnerschaft („Waldherr & Partner“), ein Code am Anfang eines Satzes oder einer Zeile hinter einem Satz mit
    einem Schloss (‚Haustür". Code 1357‘, „Der Schlüssel liegt im Tresor. Code 3141.“, „Bitte an der Haustür
    klingeln⏎Code 1357“), ein mehrdeutiger Name der Wissensbasis hinter „laut“ oder „gemäß“ („laut Vorwerk war der
    Keller trocken“) und ein unbekannter Vorname vor einem Familiennamen nach seiner Gestalt („Kreszenz Moosbichler aus
    Inzell hat angerufen“; nicht hinter einem gebeugten Adjektiv und nicht vor einer Marke oder Abkürzung:
    „Erfahrene Bergsteiger“, „Typ Mercedes-Benz“, „Hund OP-Schutz“).
  - Über-Schwärzung: Fehler- und Anzeigecodes von Geräten bleiben lesbar („Der Motor meldet den Code P0300“, „Der
    Laptop zeigt den Code 0xC000021A“, „Am Tor blinkt Code 3017“; eine Schaden- oder Strafanzeige im Satz macht aus
    dem Code am Schloss keinen Gerätefehler: „Der Einbruch wurde angezeigt, die Alarmanlage hat den Code 2580.“
    bleibt geschwärzt) – ohne Doppelpunkt hinter „Code“ zählt nur eine
    Ziffernfolge, und Gegenstände sind nur Schlösser als ganzes Grundwort („Haustür“, „Hoftor“, nicht „natürlich“,
    „Motor“, „Inspektor“, „abschließend“). „umseitig“ und „umstehend“ kündigen eine Fortsetzung nur in einer
    Fortsetzungsformel an („Fortsetzung umseitig“, „Weitere Kinder umseitig“ – nicht „Es gelten die Bedingungen
    umstehend.“), und unter einer neuen Überschrift setzt sich eine Personentabelle nur mit einem bekannten Namen fort
    (Tarif- und Leistungstabellen der Folgeseite bleiben lesbar). Berufe nicht für die Rolle des Maklers, einer Firma
    oder eines Vereins, nicht für Vertretungs- und Ehrenämter und nicht in allgemeinen Produkttexten mit „Sie“ („Als
    Handwerker benötigen Sie …“). Hinter einem Personenwort am Anfang einer Notiz oder mit Begleiter wird nur ein Wort mit
    Namensbeleg geschwärzt („Chef Sekretariat ist besetzt“, „Patient Visite um 10 Uhr“, „Ehefrau Mitversichert: ja“
    bleiben stehen); eine bekannte Marke hinter dem Personenwort wird gemeldet statt geschwärzt („Laut Monteur Buderus
    …“ – Monteur oder Hersteller?); ein Beruf direkt vor dem Platzhalter eines Namens ist für die Selbstkontrolle kein unbekannter
    Eigenname mehr („Monteur [PERSON A] kam …“ – bisher je Zeile eine Meldung). Quadrate mit „gemeldet“, „lebt“ oder
    „gezogen“ nur mit einer Person im Satz („Der Sanitätsdienst ist
    in B 4, 1 gemeldet.“ bleibt stehen), kein Verdacht hinter „nach“ im Sinn von „gemäß“ („Die Leistung nach B 1, 4“).
    Organisationseinheiten unter einem Gruß („Allgäuer Versicherungsdienst“, „Maklerbetreuung Bayern“), Betriebe statt
    Hausnamen („beim Holzhändler in Waging“, „beim Gartencenter“) und Ausfüllhinweise rechts neben dem Feldnamen „Beruf“
    auf Scans („Kaufmann reicht nicht, bitte genau“; in einer Spalte solcher Hinweise auch einer ohne Hinweiswort:
    „Landwirt mit Fläche in Hektar“) und Anweisungen in der Zeile unter einem Beruf-Feld bleiben stehen.
  - Laufzeit: Ein Gegenstand vor oder hinter „Code“ hat höchstens 40 Zeichen (eine Zeile „Code für die“ mit einem
    langen Wort lief quadratisch zurück: 64 000 Zeichen 9,6 s → 0,6 s); die Kopfzeilen-Suche einer Tabelle und die
    Wendung vor einem Personen-Etikett arbeiten in Fenstern statt über die ganze Zelle (64 000 Zeichen „Laut Nachbar
    Grohe“ 7,3 s → 3,5 s). Neue Wachstumstests decken das E-Mail-Muster mit größerer Spreizung (4 000 gegen 32 000
    Zeichen) und den Rohwert neben Feldnamen auf einem Formular ohne Werte ab; beide werden rot, wenn die Maßnahme
    zurückgenommen wird. Schwärzen langer Zeilen mit vielen Kästen: Der Abgleich der Zeichen einer Zeile vor und nach
    dem Entfernen (Lage des Platzhalters, M-31) ordnet die verbliebenen Zeichen der Reihe nach zu, statt jede
    Zeichenfolge mit jeder zu vergleichen, und die Prüfungen auf verdeckte und beschädigte Nachbarwörter suchen nur in
    Reichweite des Worts (drei Zeilen zu 8 000 Zeichen mit 810 Codes: Schwärzen 98 s → 12 s CPU, mit 1 260 Namen 191 s →
    19 s; der Rest ist das Anlegen und Anwenden der Schwärzungen in PyMuPDF). Mit dem genauen
    Abgleich rückt der Kasten auch auf Zeilen mit mehr als 13 Kästen an die verschobene Stelle (bisher blieben die
    Folgewörter dort teilweise unter dem Kasten, mit Hinweis).
- **Dritte Abnahme der Zusammenführung (Runde 5, fünfte Nachbesserung):** Drei Verengungen der vierten Nachbesserung
  ließen Werte still durch, die vorher geschwärzt waren, eine schwärzte gewöhnliche Wörter. Grundsatz jetzt: Wo eine
  Regel eng gefasst ist, um nicht geheimen Text stehen zu lassen, meldet die Selbstkontrolle jeden ausgenommenen Fall,
  der ein geheimer Wert sein kann, an seiner Stelle – auf der Textebene und auf Scans gleich. Je Befund mit Abwandlungen
  und Gegenproben in `tests/test_abnahme3_r7.py`:
  - Zugangscodes hinter Gebäuden und Behältern mit Schloss werden wieder geschwärzt („Gartenhaus: Code 9090“,
    „Ferienhaus – Code 3141“, „Das Ferienhaus hat den Code 6137.“, „Geräteschuppen – Code 3016“, Gartenhütte, Scheune,
    Heustadel, Stall, Carport, Wallbox, Paketbox, Spind, Waffenschrank, Fahrradkeller; „Haus“ nur als Grundwort, nicht
    „Hausratversicherung“), ebenso die Bedienung mit trennbarem Verb („Das Hoftor geht mit 2601 auf.“). Ohne sicheres
    Schloss meldet die Selbstkontrolle die Ziffern: hinter einem Raum, Gerät oder Feldnamen direkt vor „Code“
    („Waschküche: Code 6161“, „Serverraum Code 6169“), hinter „Code ist/lautet“ („Code lautet 5656.“, „Der Code ist
    7878.“), hinter einem Gegenstand im Satz davor und hinter einem Satz mit Schloss in der Zeile davor, auch wenn diese
    mit einem Punkt endet („Bitte im Keller nachsehen.⏎Code 9595“). Ebenso in weiteren Formen um „Code“ mit einem
    Raum oder Gegenstand: in Klammern oder Anführung davor („(Fahrradraum) Code 3603“), „Code für die Werkstatt: 5029“,
    „Code 6573 für das Lager“, als Satzgegenstand („Der Technikraum hat den Code 3389.“) und allein in der Zeile davor
    („Werkstatt⏎Code 9079“, auch wenn das Wort dort schon geschwärzt ist) – in der Probe gen3 der Abnahme waren 28
    solche Zeilen still, jetzt 4: der Raum als Feldname mit den Ziffern allein in der nächsten Zeile („Werkstatt:⏎7144“)
    ist von „Baujahr:⏎1998“ nicht zu unterscheiden. Fehler- und Anzeigecodes, Tarif-, Rabatt- und Katalogcodes, Mengen
    („mit 2500 Euro“, „mit 120 Stellplätzen“) und „Code 128 auf dem Etikett“ bleiben ohne Meldung.
  - Name hinter einem Personenwort: Am Satz- oder Notizanfang mit einem Verb einer Person dahinter ist das Wort der Name
    („Monteur Grohe kam am 03.03.“, „Nachbar Zettl hat den Brand gemeldet.“, „Kollegin Pointl ruft zurück“, „Mieter
    Liebherr hat gekündigt.“), auch eine Marke und ein unbekanntes Wort ohne Namensbeleg; ebenso mitten im Satz ohne
    Begleiter („Gestern kam Monteur Grohe vorbei.“) und mit einer Kontaktangabe dahinter („Monteur Grohe, Tel. …“). Eine
    bekannte Marke bleibt nur hinter dem Personenwort einer Firma ohne Verb stehen und wird gemeldet („Laut Monteur
    Buderus …“) – hinter „laut“/„gemäß“ jetzt auch dann, wenn die KI sie als Person liest („Laut Monteur Viessmann ist
    der Kessel defekt.“, offener Punkt der vierten Nachbesserung); hinter „mit“ („Rücksprache mit Monteur …“) und hinter
    Nachbar, Mieter und Co. ist sie der Name („Laut Nachbar Miele …“). Eine Marke, die die Wissensbasis nicht kennt
    („Laut Monteur Hansgrohe …“), bleibt wie ein unbekannter Name geschwärzt. Wie hinter einem Personenwort auch hinter
    einem Berufswort am Satzanfang mit einem Verb einer Person oder einer Kontaktangabe: eine bekannte Marke oder ein
    Name ist der Name („Elektriker Miele kam am Montag.“, „Der Installateur Vaillant hat …“; auf fbd755b und 818990e
    still), ein anderes Wort wird gemeldet („Handwerker Grohe kam am Montag.“). „ist“ und „war“ zählen nicht als Beleg
    („Chef Sekretariat ist ab 9 Uhr besetzt“ wird nicht geschwärzt, nur gemeldet; ebenso „Monteur Grohe war vor
    Ort“). Die
    Selbstkontrolle meldet jedes Wort hinter einem Personenwort, das ein Name sein kann und in der Ausgabe noch lesbar
    ist – auf Scans ohne die bisherige Längengrenze und auch ohne Rollen-Etikett („Nachbar Wudy hat …“ auf Scan 200 dpi
    war still), auch ein Berufswort, das zugleich ein Familienname ist („Wir waren beim Nachbarn Koch zu Besuch.“ war
    still); ein Fachwort der Medizin dahinter („Vater Alzheimer-Demenz“) ist eine Diagnose, kein möglicher Name.
  - Über-Schwärzung: Ein Familienname, der zugleich ein gewöhnliches Wort ist (Wissensbasis „mehrdeutig“: Schimmel,
    Rauch, Holz, Frost, Hagel, Rost …), hinter einem Personenwort mit Begleiter wird gemeldet statt geschwärzt – auch
    nicht über die KI („Der Gutachter hat beim Mieter Schimmel festgestellt.“, „Er hat dem Nachbarn Holz gebracht.“);
    mit einem Verb dahinter am Satzanfang bleibt er ein Name („Der Nachbar Rauch hat angerufen.“). Die Kehrseite: Ein
    echter Familienname dieser Art ohne ein solches Verb wird ebenfalls nur gemeldet („Er hat mit dem Kollegen Wolf
    telefoniert.“) – die Wortart des Sprachmodells unterscheidet das nicht sicher. Hinter „beim“/„vom“/„zum“ ohne
    Ortskontext zählt nur die Endung eines Hausnamens, nicht jeder Nachname der Wissensbasis („Anbei das Foto vom
    Kratzer.“ bleibt stehen und wird gemeldet).
  - Selbstkontrolle: Familienname mit Artikel auch mit den Verben eines Schadens oder seiner Meldung („Der Gruber hat den
    Schaden gemeldet.“, „Den Unfall verursachte der Riedhalter.“, „Den Schaden meldete der Holzwohner.“) und in der
    weiblichen Form auf „-erin“ am Satzanfang („Die Wimmerin hat angerufen.“), am Satzanfang auch ein unbekannter
    Familienname auf „-er“ ohne Namensgestalt („Der Mooshammer hat angerufen.“; nicht „Der Absender hat …“, „Der
    Versicherer hat …“); ein unbekanntes Wort hinter „als“ in einem Satz über Erwerbsarbeit und eine Rolle mit
    gewohnter Tätigkeit („Sie macht als Gutachterin Hausbesuche.“).
    Ein Familienname aus einem unbekannten Bestimmungswort und dem Grundwort eines Rollenworts hinter einem Verb
    einer Person blieb ohne Meldung („Am Steuer saß der Kirchhelfer, als …“, „Laut Polizei fuhr der Haslbecher zu
    schnell.“; offener Punkt der vierten Nachbesserung, 9 von 20 Namen der Probe) und wird jetzt gemeldet; mit einem
    gewöhnlichen Wort davor bleibt es ein Rollenwort ohne Meldung („der Unfallfahrer“, „der Fahrradfahrer“,
    „der Grundstücksbesitzer“), ein seltenes Rollenwort wird gemeldet („der Hausbesitzer“).
  - Beruf: auch gebeugt („übt den Beruf des Schreiners aus“, „übt seit Jahren den Beruf des Maurers aus“), im
    Relativsatz („Ihr Mann, der Polizist ist, …“; nicht Rollen wie „der Fahrer war“) und Tätigkeiten nach ihrem
    Grundwort hinter einem Wort der Erwerbstätigkeit („arbeitet als Putzfrau“, „ist als Putzkraft tätig“, „arbeitet als
    Paketbote“).
  - Laufzeit: Die Selbstkontrolle fragt Platzhalter und gesperrte Bereiche über die sortierten Spannen ab (bisect)
    statt über alle Platzhalter je Wort; eine Zeile mit 600 Platzhaltern (58 600 Zeichen) braucht 3,7 s statt 14,6 s
    bei gleichem Ergebnis, und ein Wachstumstest (75 gegen 600 Platzhalter) wird rot, wenn die Abfrage wieder über alle
    läuft.
- **Vierte Abnahme der Zusammenführung (Runde 5, sechste Nachbesserung):** Der Kammfeld-Strang ließ ein auf Felder
  „Tag“, „Monat“, „Jahr“ verteiltes Geburtsdatum still durch und schwärzte Kreuzchen, Ausfüllhinweise und kurze Werte
  an allen gleichen Stellen des Dokuments; mehrere Verengungen früherer Runden ließen Werte ohne Meldung stehen, die
  fbd755b noch geschwärzt hatte. Je Befund mit Abwandlungen und Gegenproben in `tests/test_abnahme4_r7.py`:
  - Kammfelder: Teil-Feldnamen („Tag“, „Monat“, „Jahr“, „TT“, „JJJJ“) gelten nie für sich als Feldname ohne
    Personenbezug – es zählt der Feldname davor in der Zeile bzw. darüber („Geburtsdatum ⇥ Tag [..] Monat [..] Jahr
    [....]“), auf Scans und auf der Textebene; unter einem Geburts-Feldnamen werden die Teile geschwärzt, sonst
    bleiben sie lesbar („Antragsdatum“, „Versicherungsbeginn“). „Datum“ allein bleibt ein Datum wie „Antragsdatum“.
    Die Selbstkontrolle meldet die Teile auch dann, wenn die Kästchen nicht als Kammfeld gelten. Liest die
    Texterkennung bei Schräglage „Geburtsdatum ⇥ Tag“ und den Rest der Reihe als eigene Zeile („2,35, ⇥ Monat 0.4 ⇥
    Jahr ⇥ 2016“), gilt das kurze Stück vor dem ersten Teil-Feldnamen als Wert des Tags; verlesene Ziffern in Kästchen
    („O 1“, „0.4“) zählen als Teil-Wert. Auf Scans gilt ein Feld aus zwei Kästchen als Kammfeld, wenn in seiner Zeile
    ein Feld derselben Bauart steht („Tag [..] Monat [..] Jahr [....]“, „TT [..] MM [..] JJ [..]“ – vorher blieben
    „03“ und „02“ ungelesen und still); ein Ankreuzpaar allein bleibt keines. Kurze Werte mit Tabulatoren zwischen den
    Kästchen der Textebene („Hausnr. ⇥ 1 ⇥ 3“, „Vorname ⇥ L ⇥ I“) werden geschwärzt. Kreuzchen und vorgedruckte
    Ausfüllhinweise („TTMMJJJJ“, auch mit einem als „I“ gelesenen Wandrest: „TTMMJJJIJ“) sind keine Werte, kurze
    Kammfeld-Werte (bis zwei Zeichen) werden nur als Hausnummer oder Name geschwärzt und nie an andere Stellen
    weitergegeben – auch eine kurze Hausnummer hinter „Hausnummer:“ nicht mehr an „Halle 8“, „Tor 8“, „Seite 1 von 8“.
    Auf Scans zählt dabei die Zahl der gefüllten Kästchen mit: Liest die Texterkennung weniger Zeichen, als Kästchen
    gefüllt sind („LI“ als „L“ bei 300 dpi JPEG, eine Telefonnummer als „08“), gilt der Wert als so lang wie seine
    Kästchen und wird geschwärzt; ein einzelner gelesener Buchstabe eines Namens wird nicht weitergegeben
    („Konfektionsgröße L“ bleibt). Mengen- und Betragsfelder („Wohnfläche (m²)“, „Progression in %“, „Unfallrente
    monatlich“, „Jahresfahrleistung“) mit einer Zahl darin meldet die Prüfung nicht mehr – auch nicht als
    „Ziffernfolge“ über die Textregeln. Kleinstbilder (1–3 Pixel breit) lösen keine Ausnahme mehr aus.
  - Zugangscodes: Ein Schloss wird an seinem Grundwort erkannt („Feuerschutztür-Code“, „Code Doppelgarage“,
    „Hintertor (Code …)“, „Türsprechanlage“, „Gittertor:⏎6312“), der Vorgriff auf ein Fehlerwort gilt nur vor „alarm“
    (Fehlalarmcode bleibt frei); bei sicherem Schloss auch ein Code aus Buchstaben und Ziffern („Kellertür – Code
    7A3B“), nicht in Fehlercode-Gestalt („P0300“). Melde- und Anzeigewörter heben den Code an einem Schloss nicht mehr
    auf („Der Vermieter meldete den neuen Code der Kellertür: 8034“, „Am Display der Garage den Code 2240 eingeben.“);
    „PIN/Zugang/Zahlencode + Schloss:“ und ein Raum nach seinem Grundwort werden geschwärzt bzw. gemeldet, ein bloßes
    Schadenwort davor („Zum Schaden in der Ferienwohnung: …“) ordnet den Code nicht ein. „Der Code für das Postfach
    lautet …“ wird gemeldet, wenn das Wort hinter „für“ ein Raum, Schloss oder Zugang ist (nicht „Der Code für den
    Prospekt lautet 3344.“). Frei bleiben Beträge, Baujahre (auch in der Spalte „Baujahr“ einer Tabelle: „Wohnhaus: ⇥
    1974 ⇥ Massiv“) und Jahreszahlen vor einem gebeugten Partizip mit seinem Hauptwort („mit 1890 gebautem
    Dachstuhl“; ein ungebeugtes Partizip wie „gesichert“ bedient das Schloss, siebte Nachbesserung), Möbelcodes
    ohne Bedienung, Tarif-, Typklassen-, Gebührenordnungs- und Kostenstellencodes (auch als Grundwort).
  - Namen: Wörter hinter einem Personenwort, die die Wissensbasis als gewöhnliche Wörter kennt oder die ohne Beleg
    hinter einem Begleiter stehen („Zeugin Ledig“, „mit dem Onkel Grebl“), werden gemeldet; ein Titel- oder Berufswort,
    das zugleich Familienname ist („Maler Kaplan“, „Onkel Kaplan“), ein Allerweltswort hinter Herr/Frau („Herrn
    Halter“), ein Doppelname mit gewöhnlichem Teil („Zeugin Bauer-Kaltl“: geschwärzt), ein Familienname mit Artikel und
    einem Satzteil einer Person (auch ohne „-er“: „Gesehen hat es der Hafl.“, „Die Scheibe hat der Wimmer beschädigt.“,
    „Die Becherin hat angerufen.“), ein Wort mit Namensbeleg hinter einem Berufswort auch ohne Verb („Glaser Frost ist
    erst nächste Woche frei.“, „Laut Klempner Dyson …“), ein Hausname mit Besuchs- oder Ereigniskontext („Vom Kaltl
    kam der Anruf …“, „Wir waren beim Pfnürl zum Essen.“) und ein Organisationswort mit unbekanntem Wort unter einem
    Gruß („Agentur Moik“) werden gemeldet. Die Kehrseite nach P2: Gemeldet werden dort auch unbekannte und bekannte
    Wörter, die kein Name sind („brannte es beim Holzhändler in Waging“, „Vom Sturm …“, „Den Traktor lenkte der …“,
    „dem Nachbarn Brot gebracht“; auf 5efcc0c 131 bis 140 von 333 Nomen der Hof-Probe der fünften Abnahme, nach der
    siebten Nachbesserung 96 bis 98); im Differenztest sind es gegenüber 0230782 159 neue und 65 weggefallene
    Meldungen nicht geheimer Wörter, 82 der neuen hinter beim/vom/zum. Ein bekannter Familienname hinter beim/vom/zum
    wird wieder geschwärzt
    („Wir waren beim Brandl zum Essen.“). Abteilungs-, Orts- und Firmenwörter hinter einem Personenwort („Kollege
    Außendienst“, „Nachbar Gegenüber“, „Techniker Wasserversorger“) werden nicht mehr geschwärzt, nur gemeldet;
    Geräte, Tiere und Fahrzeuge in Schadensätzen („Der Marder beschädigte …“, „Der Hund beschädigte die Couch.“,
    „Gefahren ist der Wagen.“) sind keine Familiennamen, soweit die Wissensbasis sie als Tier, Marke oder Sachwort
    kennt oder das Verb „fahren“ oder „rammen“ ist („Der Waschbär beschädigte die Dämmung.“ und „Der Wagen hat den
    Unfall verursacht.“ werden gemeldet). Ebenso wenig ist es das Objekt hinter dem Verb, wenn davor ein Subjekt im
    Nominativ steht („Der Saugroboter beschädigte die Stehlampe.“, „Er bemerkte die Gardine.“; nach „Die …“ oder
    „Das …“ bleibt die Meldung, dort kann das Wort auch das Subjekt sein).
  - Beruf: Ein Beruf mit Rollen-Endung hinter „ist“, „von Beruf“, „hauptberuflich“ („Er ist Fitnesstrainer“), der
    Beruf einer Person im Satz einer Organisation („Die Firma hat sie als Hebamme eingestellt.“) und „den Beruf des
    Bäckers erlernt“ werden geschwärzt; im Ehrenamt („ehrenamtlich als Erzieherin tätig“), beim höflichen „Sie“ mit
    Arbeit oder Einstufung („da Sie als Krankenschwester im Schichtdienst arbeiten“) meldet die Selbstkontrolle den
    Beruf. Eine Tätigkeit nach ihrem Grundwort gilt nicht für eine Sache als Satzgegenstand („Die Software arbeitet als
    Eingabehilfe …“). Quadrate (Mannheim) mit Wohnwort oder Person im Satz werden geschwärzt bzw. gemeldet.
  - Texterkennung: Die Selbstkontrolle liest auf Scans ein Ausrufezeichen am Wortende vor einem klein geschriebenen
    Wort als „l“ („Vom Kalt! kam der Anruf“ bei 300 dpi JPEG: der Hausname wird gemeldet) und ein an das Wort davor
    angeklebtes „nach“ vor einem Quadrat als Präposition („per Postnach K1, 5“; nicht demnach, hernach, hiernach).
    Liegt der Platzhalter eines Namens links vor einem Wort, sein Text aber am Ende der Textebene (so schreibt die
    Schwärzung), gilt er als links („[PERSON A] Bauer-Hinterseer hat angerufen.“ war kein „Beruf vor dem Namen“); auf
    Scans zählt auch ein Schwärzungsrechteck, in dem die Kontroll-OCR den Platzhalter verliest („IPERSONAI“), und die
    Längengrenze für OCR-Wörter gilt je Teil eines Doppelnamens. „Wasser“ und „Regen“ stehen als gewöhnliche Wörter in
    der Wissensbasis („dem Nachbarn Wasser abgegraben“ wird nicht gemeldet); für die Selbstkontrolle ist ein am
    Zeilenende getrenntes Wort hinter „Herr“ („Herr Versiche-“ ⏎ „rer“) kein Familienname – die Erkennung schwärzt
    „Versiche“ weiter als Namen (vorbestehend, auf der Textebene und im Textlayer-PDF).
  - Laufzeit: Die Kontroll-OCR liest eine Scan-Seite, deren Original kein Kammfeld hatte, ohne Kammfeld-Suche; die
    Suche selbst verkleinert das Bild über versetzte Teilbilder und bestimmt die Papierhelligkeit über das Histogramm
    (gleiches Ergebnis, bei 300 dpi 0,22 s → 0,11 s je Seite). Neue Wachstumstests (8 000 gegen 64 000 Zeichen ohne
    Zeilenumbruch für „mit + Ziffern“, Personenwort + Verb und Berufswort + Verb; 600 gegen 2 400 Platzhalter).
    Gemessen auf dem Probensatz der vierten Abnahme (CPU-Zeit je Scan-Seite einschließlich Texterkennung,
    Oberflächen-Weg, je zwei Runden im Wechsel; 38 Maklerdokumente als Scan mit 200 dpi, 24 Kammfeld-Scans): ohne
    Kammfeld 2,13 s gegen 1,76 s auf 818990e (+21 %) und 2,27 s auf 0230782, mit Kammfeldern 3,18 s gegen 1,78 s auf
    818990e (+79 %) und 3,59 s auf 0230782. Gegenüber 818990e bleibt damit ein Mehraufwand: auf Kammfeld-Seiten Suche
    und Lesen der Kästchen in der Analyse und in der Kontroll-OCR, die mehr Seiten liest, weil mehr geschwärzt wird,
    dazu die Kammfeld-Prüfung der Selbstkontrolle; auf den übrigen Scan-Seiten die Kammfeld-Suche (etwa 0,1 s je
    Seite), die Kontroll-OCR der zusätzlich geschwärzten Seiten und die neuen Regeln der Selbstkontrolle (etwa 0,1 s
    je Datei).
- **Fünfte Abnahme der Zusammenführung (Runde 5, siebte Nachbesserung):** Einige Ausnahmen der sechsten Nachbesserung
  ließen Werte ohne Meldung stehen, die 0230782 noch geschwärzt oder gemeldet hatte (ein Zugangscode in Jahresform,
  ein Familienname gleich einem Geräte-Grundwort, eine Tätigkeit hinter einem Satzgegenstand, die weiteren Vorkommen
  kurzer Werte, „Regen“ und „Wasser“ als Namen), der Code eines Möbelschranks wurde ohne Eintrag in der Tauschliste nur
  noch gemeldet, und auf Kammfeld-Formularen verlor ein Feldname unter dem Feld gegen den Mengen-Feldnamen darüber.
  Je Befund mit Abwandlungen und Gegenproben in `tests/test_abnahme5_r7.py`:
  - Zugangscodes: Eine Zahl in Jahresform hinter „mit“ an einem Schloss wird mit einem Verb der Sicherung oder
    Bedienung geschwärzt („Die Tiefgarage ist mit 1984 gesichert.“, „Die Garage ist mit 2015 abgesperrt.“, „Die Haustür
    lässt sich mit 1990 aufschließen.“); frei bleibt sie nur vor einem gebeugten Partizip mit seinem Hauptwort („mit
    2021 erneuerter Heizung“, „mit 2019 eingebauten Rolltoren“) – erkannt an der Beugungsendung statt an einer Liste
    von Vorsilben. Ein Möbel mit Code ist ein Schloss („Code Badschrank: 8815“, „Küchenschrank (Code 2207)“); nur mit
    einem Wort des Kaufs oder Produkts im Satz und ohne Verb der Bedienung bleibt sein Code beim Melden („Laut Rechnung
    des Möbelhauses trägt der Kleiderschrank den Code 66130.“, „Der Kleiderschrank aus dem Katalog hat den Code 4471.“:
    „Code an einem Möbel (Produkt- oder Schlosscode?)“ – auf 5efcc0c blieb dieser Fall ohne Meldung). An einem
    sicheren Schloss ohne Melde- oder Anzeigewort ist auch ein Code in Fehlercode-Gestalt ein Zugangscode („Die Haustür
    hat den Code KB475.“, „Code Garagentor B4471“, „Der Tresor hat den Code XK42.“); die Schreibweise einer
    Geräteanzeige mit Bindestrich bleibt mit einem Wort der Reparatur oder Anzeige ein Fehlercode („Garagentor ⏎ Code
    E-04 blinkt, Elektriker kommt am Montag.“).
    Der Code eines Alarms als Ereignis (Feuer-, Brand-, Rauch-, Stör-, Probe-, Fehlalarm) wird mit seiner Bedienung
    geschwärzt („Zum Abschalten des Feueralarms den Code 6619 eingeben.“, „Der Feueralarm wird mit dem Code 1412
    quittiert.“), mit „lautet“ oder Doppelpunkt gemeldet, allein („Feueralarmcode 3401“) als mehrdeutig gemeldet.
    Neu erkannt werden „PIN für Wohnungstür 7100“, ein Raum als Bestimmungswort von „…code“ („Lagerhallecode: 9444“),
    Portal, Konto und Zugang als Grundwort („Code für das Kundenportal (Typklasse 17): 0628“), ein Meldewort mit
    Empfänger („Der Vermieter meldete uns den Code der Haustür: 2827“) und „gilt für die Garage der Code 9930“.
    Weniger geschwärzt: „Zugang Lagerhalle: 7-17 Uhr“ und „Zugang Haupteingang: 24/7“ sind Öffnungszeiten (ein
    Stundenbereich ohne „Uhr“ wird gemeldet); ein Verb der Nutzung hinter einem Komma gilt nicht dem Code („Die
    Alarmanlage zeigte Code 4021 an, danach bitte die Anlage scharf schalten.“), außer der Satzteil nimmt den Code
    wieder auf („…, bitte den Code am Bedienteil eingeben.“: geschwärzt), ein Code für einen Plan, eine Liste
    oder eine Buchung („Der Code der Stadthalle für den Saalplan lautet 2019-A.“) und Kostenstellen eines Plans werden
    nur gemeldet. Ein Betrag hinter einem Gebäude als Feldname meldet auch die zeilenweise Prüfung nicht mehr
    („Wohnhaus: ⇥ 450.000 ⇥ EUR“); Jahreszahlen hinter Gebäuden ohne Spaltenkopf „Baujahr“ („Wohnhaus: ⇥ 1974“,
    „Carport: ⇥ 2021“) bleiben gemeldet – ohne Kopf kann es auch ein Code sein (P2).
  - Kammfelder: Steht ein Feldname unter dem Feld und näher als der Text darüber (der Feldname des Felds davor), gilt er
    – in der Erkennung und in der Selbstkontrolle („Vorname“ unter „T H E K L A“, darüber „Wohnfläche (m²)“); der eigene
    Feldname der Zeile geht dem Feldnamen darüber vor („Letzte Hauptuntersuchung ⇥ Jahr [2024]“ unter „Fahrzeughalter
    (Name, Vorname)“ bleibt lesbar). Auf der Textebene werden geschwärzt: „Mon.“ als Teil-Feldname, ein Teil-Datum
    hinter einem Feldnamen mit Klammerzusatz („Geburtsdatum (Fahrer) ⇥⇥ Tag 1 9 …“), ein kurzer Wert hinter einer
    gesperrten Folge am Zeilenende („Straße ⇥⇥ B I R K E N W E G ⇥⇥ Nr. ⇥⇥ 6 ⇥⇥ 4“) und vor dem nächsten Feldnamen
    („Name ⇥⇥ R ⇥⇥ E ⇥⇥ Vorname ⇥⇥ A N N A“), Initialen („Initialen ⇥⇥ K H“) und ein Geburtsort aus zwei Buchstaben
    („Geburtsort ⇥⇥ A U“); „Nr.“ ohne Straße in der Zeile ist eine Positionsnummer, „Etage ⇥⇥ 1 ⇥⇥ 2“ bleibt lesbar.
    Diese Regeln brauchen die Zellgrenzen der Kästchen: liest die Textebene einer PDF die Kästchen ohne sie („Initialen
    K H“, „Name L ⏎ I“), bleiben zwei Buchstaben und Datumsteile unter einem fremden Feldnamen weiter lesbar ohne
    Meldung (wie auf 5efcc0c und 0230782; Ende-zu-Ende-Proben der fünften Abnahme). Auf Scans nimmt ein unlesbarer
    Teil-Feldname („Srae“ oder „See“ statt „Straße“) den Feldnamen der Zeile („Anschrift“: geschwärzt wie auf 0230782) –
    ein lesbarer eigener Feldname ohne Personenbezug („Marke“, „Modell“, „Bank“, „Farbe“, „Tarif“) nimmt ihn seit der
    achten Nachbesserung nicht mehr (Abnahme 6 AB6U-06) –, ein kurzer Wert im Anschriftfeld unter dem Feldnamen eines
    Teils der Wohnung ist für die Kammfeld-Regel keine Hausnummer („Wohnung ⇥ Etage [3]“, „Zimmer [4]“; die Regel
    Feldname + Wert schwärzte „Lage der Wohnung ⇥ Etage [3]“ auf Scans bis zur achten Nachbesserung als Anschrift –
    Kamm-Probe der fünften Abnahme, k04; „Anschrift [14]“ ohne eigenen Feldnamen bleibt wie auf 5efcc0c und 0230782
    geschwärzt), unter dem Feldnamen einer Hausnummer gilt er auch verlesen, wenn er eine Ziffer enthält („Hausnr.“
    unter „2&1“ statt „27“; auf 0230782 geschwärzt, auf 5efcc0c gemeldet) –, und ein kurzer Datumsteil ohne Trennzeichen
    („Monat [0 4]“ unter „Geburtsdatum“) gilt nur an seiner Stelle – der gleiche Monat im Versicherungsbeginn wird nicht
    mehr mitgeschwärzt. Damit gilt die Angabe der sechsten Nachbesserung, dass Teile eines Datums unter einem Feldnamen
    ohne Personenbezug lesbar bleiben, auch auf Scans: in der Kammfeld-Probe der fünften Abnahme wird keines der
    Teil-Felder unter „Versicherungsbeginn“ und „Hauptuntersuchung“ mehr entfernt (auf 5efcc0c 3); gemeldet werden 9
    davon (0230782: 8), wenn die Texterkennung den Inhalt oder den Feldnamen nicht lesen kann.
  - Namen: Ein Geräte-Grundwort allein („Kocher“, „Bohrer“, „Regler“, „Sender“, „Melder“) mit Artikel und einem Verb
    einer Person wird gemeldet („Der Kocher hat angerufen.“); ein Gerät als Kompositum („Hochdruckreiniger“,
    „Gabelstapler“), ein Gerät mit Geräteschaden und Maschinen auf „-e“ („Die Fräse beschädigte das Erdkabel.“) bleiben
    frei; hinter beim/vom/zum wird ein Geräte-Kompositum nicht geschwärzt, aber gemeldet („Vom Gabelstapler kam der
    Anruf …“, „Vom Steinkocher …“: das Grundwort ist auch ein Familienname). Ein Allerweltswort wie „Regen“ oder
    „Wasser“ direkt hinter einem Personenwort ohne Begleiter gilt wieder wie auf 0230782 (dort standen beide noch nicht
    in der Liste der Allerweltswörter) als Name und wird geschwärzt: am
    Satzanfang mit dem Verb oder Zustand einer Person („Nachbar Wasser hat angerufen.“), hinter „laut“ („Laut Nachbarin
    Regen war die Tür offen.“), mit Kontaktangabe oder einem weiteren Personenwort dahinter („Zeugen: Nachbar Wasser und
    Nachbarin Regen“) und mitten im Satz hinter der Grundform der Einzahl („Rücksprache mit Nachbar Wasser am Montag.“,
    „Gestern rief Nachbar Regen an.“). Hinter „Mieter“ oder „Mitarbeiter“ (Einzahl wie Mehrzahl), hinter gebeugten
    Formen und hinter „als“ kann es Name oder Satzteil sein und wird gemeldet („Die Kosten trägt Mieter Wasser
    selbst.“, „Er telefonierte mit Kollegen Wasser.“, „Er stellte sich als Nachbar Wasser vor.“, aber auch „Er zeigte
    Kollegen Fotos.“); hinter einem Genitiv auf „-s“ („Nachbars Garten“) und wie bisher hinter einem Begleiter („Er
    hat dem Nachbarn Wasser abgegraben.“) ist es ein Satzteil. Stockwerk, Gebäudeteil, Kanal, Sparte und Gewerk hinter einem Personenwort sind
    ein Zusatz der Rolle („Mieter Erdgeschoss meldet …“, „Mitarbeiter Hotline“, „Kunde Gewerbe“, „Monteur Fernwärme“)
    und bleiben wie Abteilungen beim Melden, ebenso Zeitwörter („Nachbar Morgen kommt vorbei.“) und Komposita mit einem
    Allerweltswort als Grundwort („Laut Nachbar Wasserschaden war alles nass.“); mit Artikel und Personenverb wird das
    Allerweltswort gemeldet („Der Wasser hat den Schaden gemeldet.“). Familiennamen mit einem Allerweltswort darin
    („Regensburger“, „Wasserbauer“, „Regenauer“) werden mindestens gemeldet. Wie ein Verb zählt am Satzanfang auch der
    Zustand einer Person („Zeuge Tremml wird morgen zurückrufen.“, „Onkel Raffl wurde befragt.“, „Kollegin Tremml war
    gestern krank.“: geschwärzt wie auf fbd755b, auf 0230782 und 5efcc0c nur gemeldet); Sekretariat, Registratur,
    Praxis, Redaktion, Disposition und Wörter auf „-stelle“ zählen zu den Abteilungen („Chef Sekretariat ist heute
    besetzt.“ wird gemeldet). Mindestens gemeldet wird außerdem ein
    Familienname mit Artikel im Satz einer Person („Laut Polizei hat der Schwarzl den Unfall gemeldet.“, „Der Nachbar
    beschuldigte die Zeitlhofer.“), hinter einem gebeugten Personenwort („bei dem Mandanten Kreuzl“: geschwärzt, „des
    Onkels Tremml“, „des Vermieters Leser“), ein Beruf, Titel oder eine Rolle hinter einem Personenwort („Kollege Pfarrer hat angerufen.“, „Rücksprache
    mit Mieter Käufer“, „Kunde Halter wurde befragt.“) und ein Wort mit Artikel, das zugleich Tier, Marke, Gerät oder
    Rufname ist, mit der Tat einer Person („Den Schaden meldete der Fink.“, „Am Steuer saß der Hase.“, „Der Wastl hat
    angerufen.“); frei bleiben Jahreszeiten und Kalenderwörter („Am Steuer saß der Winter.“), Wetter („Der Hagel hat
    den Schaden verursacht.“) und Fahrzeuge („Den Zaun rammte der Wagen.“). Ein bekannter Familienname hinter
    beim/vom/zum wird mit Besuch, Entfernung, Weg oder Besitz geschwärzt („Wir waren gestern beim Gruber zum Essen.“,
    „Zum Wimmer sind es nur zwei Kilometer.“, „Der Traktor vom Wimmer …“, „Die Kühe vom Gruber …“), ein unbekannter
    gemeldet; „Zum Glück“ und Infinitive („Beim Grillen“, „Beim Rangieren“, „Beim Einkaufen“) sind sichere Gegenbelege
    und bleiben frei, nie aber ein Familienname der Wissensbasis, ein Wort in Namensgestalt oder ein Flur-, Orts- oder
    Hofname nach seinem Grundwort („Beim Kaltenbrunnen …“, „Vom Mitterhofen …“, „Beim Moosgraben …“: gemeldet wie auf
    5efcc0c).
    „Herr Kollege Maier“: geschwärzt wird nur „Maier“. Die gebeugten Personenwörter erweitern die Ausnahme für einen
    Familiennamen, der zugleich ein gewöhnliches Wort ist, hinter einem Begleiter (nur gemeldet, „Beim Nachbarn Fuchs
    brannte Licht.“) nicht auf den Genitiv: „Die Kaution des Mandanten Wolf ist offen.“ bleibt geschwärzt.
  - Beruf: Eine Tätigkeit nach ihrem Grundwort zählt hinter jedem Satzgegenstand, der kein Programm, Gerät, keine
    Anlage und kein System ist („Der Verletzte arbeitet als Lagerhilfe.“, „Die Bevollmächtigte arbeitet als
    Bürokraft.“). Zeitangaben und Adverbien zwischen „ist“/„war“ und dem Beruf heben ihn nicht auf („Sie war früher
    Lehrerin an der Grundschule.“, „Er ist seit 2015 Busfahrer bei den Stadtwerken.“), ein Ehrenamt ohne Personenwort
    wird gemeldet („Seit 2018 ehrenamtlich als Erzieherin in der Kita tätig.“). Die Selbstkontrolle zählt dabei auch
    einen Personen-Platzhalter der Ausgabe, dessen Text am Ende der Textebene steht, dessen Rechteck aber im Satz
    („Angaben zur Person ⏎ [PERSON A] tätig als Schöffin am Amtsgericht.“, das erste Wort unter dem Feldnamen als Name
    geschwärzt) – dort blieb der Beruf vorher auf der Textebene und auf Scans still. Eine Rolle mit Ergänzung („Er ist
    Trainer der F-Jugend.“, „Sie ist Betreuerin ihrer Mutter.“) und „den Beruf des X“ ohne ein Verb des Erlernens oder
    Ausübens („Für den Beruf des Dachdeckers gilt die Gefahrengruppe B.“) werden nur gemeldet.
  - Weitergabe und Selbstkontrolle: Ein kurzer Wert, der nur hinter seinem Etikett gilt, wird an weitere Stellen
    weitergegeben, wo der Text ihn als Ort hinter einer Präposition des Orts („Geburtsort: Au ⏎ Sie wuchs in Au bei
    Freising auf.“) oder als Hausnummer hinter „Haus“ nennt („Hausnummer: 7 ⏎ Das Haus 7 hat einen Wasserschaden.“);
    „Halle 8“ und „Tor 8“ werden nicht geschwärzt. Eine Postleitzahl links neben einem geschwärzten Ort meldet die
    Selbstkontrolle („Wohnort: 72070 [PLZ ORT]“ – auf einem Handschrift-Fax las die Erkennung die Postleitzahl nicht),
    auf Scans nach der Lage auf der Seite (dort steht das OCR-Wort im Seitentext hinter den Platzhaltern und galt bisher
    immer als rechts), auch verlesen („F2O7O [ORT]“: Länge einer Postleitzahl, mindestens zwei Ziffern); liest die
    Erkennung die Handschrift neben einer geschwärzten Anschrift gar nicht, meldet die Tintenprüfung sie („Schrift
    neben einer geschwärzten Anschrift nicht verlässlich lesbar“).
  - Scans: Hinter einem Personenwort im Fließtext („Mitarbeiter Vertrieb meldet sich bis Freitag.“, „Nachbar
    Gegenüber sah den Rauch zuerst.“) ist der Satz kein Rohwert eines Formularfelds mehr – vorher wurde er auf allen
    Vorständen ganz geschwärzt; wie auf der Textebene wird ein Name darin über die Personenwort-Regeln geschwärzt, eine
    Abteilung oder Lage gemeldet. Ein Feld mit Doppelpunkt, Tabulator oder dem Wert darunter bleibt ein Feld.
  - Laufzeit: Hausnamen und Hausnamen-Kandidaten suchen ihren Kontext einmal je Zeile, die Jahreszahl unter einem
    Spaltenkopf sucht den Kopf nur bis zu einer Zeilengrenze, die Kammfeld-Regel der Textebene findet die Zeilen darüber
    und darunter, die Feldnamen je Zeile und den Feldnamen links vor einem Wert über einen Index (bisect) statt je Wert
    über alle Zeilen bzw. Feldnamen der Seite – auf einer Seite mit 5 120 Kammfeld-Werten 0,9 s statt 28 s auf 5efcc0c.
    Auf Scans suchen der eigene Feldname eines Kammfelds, die Felder eines Worts und das Feld unter einem Feldnamen nur
    auf ihrer Höhe (Index nach der Höhe statt je Feld über alle Wörter bzw. Felder der Seite); der Personen-Platzhalter
    neben einem Beruf wird nur unter den Wörtern des Satzes gesucht. Neue Wachstumstests (8 000 gegen 64 000 Zeichen,
    4 000 gegen 64 000 für die Kammfeld-Regel der Textebene, 250 gegen 2 000 Kammfelder auf Scans, 40 gegen 320 Sätze
    einer Ausgabe-Seite) werden rot, wenn eine dieser Schleifen wieder je Treffer über alles läuft (eingebaute
    Regressionen R6, R7 der Abnahme und dreizehn eigene, N1 bis N13). Gemessen auf dem Probensatz der fünften Abnahme
    (CPU-Zeit je Scan-Seite einschließlich Texterkennung, Oberflächen-Weg, zwei Runden mit allen drei Ständen
    gleichzeitig; 55 Maklerdokumente als Scan mit 200 dpi, 42 Kammfeld-Scans): ohne Kammfeld 2,15 s gegen 2,35 s auf
    5efcc0c (−9 %) und 1,94 s auf 818990e (+11 %), mit Kammfeldern 3,69 s gegen 3,69 s auf 5efcc0c (gleich:
    Runde 1 +0,04 s, Runde 2 −0,04 s) und 2,18 s auf 818990e (+69 %), über alle 97 Seiten 2,82 s gegen 2,93 s auf
    5efcc0c und 2,04 s auf 818990e. Gegenüber 818990e bleibt damit der Mehraufwand der Kammfeld-Seiten
    (Suche und Lesen der Kästchen in der Analyse und in der Kontroll-OCR, Kammfeld-Prüfung der Selbstkontrolle) und
    auf den übrigen Seiten der Aufwand der Kammfeld-Suche und der neuen Regeln der Selbstkontrolle.
  - Kehrseite nach P2 (gemeldet statt still): Im Differenztest (21 411 Texte, 10 819 geheime Werte) sind gegenüber
    5efcc0c 838 Werte besser gestellt (412 von lesbar auf geschwärzt, 341 von lesbar auf gemeldet, 85 von gemeldet auf
    geschwärzt) und keiner schlechter; gegenüber 0230782 stehen 3 Werte schlechter (nur gemeldet statt geschwärzt:
    Abteilungs-, Lage- und Firmenwörter hinter einem Personenwort, AB4U-01), gegenüber 818990e 21 und gegenüber
    fbd755b 105 (ebenso nur gemeldet statt geschwärzt, vor allem mehrdeutige Wörter hinter Personenwörtern, Ehrenamt,
    Alarmcodes ohne Bedienung). Kein geheimer Wert ist mehr lesbar, der auf einem der vier Stände geschwärzt oder
    gemeldet war, und geschwärzt werden 229 statt 245 nicht geheime Prüfwörter. Die Selbstkontrolle meldet dafür mehr
    nicht geheime Wörter; unter den Hof-Kandidaten der Abnahme (333 Nomen hinter beim/vom/zum in drei Satzrahmen) sind
    es 96 bis 98 statt 131 bis 140. Neu gemeldet werden dabei auch ein gewöhnliches Wort mit Artikel vor einem Verb,
    das nur eine Person tut, wenn es eine Einrichtung bezeichnet („Die Bank hat angerufen.“, „Der Versicherer hat den
    Schaden gemeldet.“; auf 5efcc0c ohne Meldung), eine Anrede oder ein abgekürzter Titel zwischen Personenwort und
    geschwärztem Namen („Ihre Nachbarin Frau …“, „Der Gutachter Dipl.-Ing. …“) und ein unbekanntes Wort in
    Namensgestalt im Personenkontext („Fichtelgebirge Feuerkasse VVaG“ hinter „Zahlungsempfänger“). In der Endmessung
    von 98a3957 (320 Dokumente der Entwicklungskorpora) sind dadurch vier Dokumente `_PRUEFEN` statt fertig; keines
    ist schlechter geschwärzt.
- **Sechste Abnahme der Zusammenführung (Runde 5, achte Nachbesserung):** Einige Ausnahmen der siebten Nachbesserung
  ließen Werte ohne Meldung stehen, die 5efcc0c oder 0230782 noch geschwärzt oder gemeldet hatten (ein Zugangscode in
  Jahresform vor einem finiten Verb, Familiennamen hinter beim/vom/zum mit der Endung eines Infinitivs oder vor einem
  Ausrufezeichen, ein Familienname hinter Präposition und Artikel, eine Rolle hinter „von Beruf“, der Beruf im schwachen
  Genitiv, Kammfeld-Werte unter einem fremden Feldnamen). Dafür wurden andere Wörter zu oft geschwärzt oder gemeldet. Je
  Befund mit Abwandlungen und Gegenproben in `tests/test_abnahme6_r7.py` (458 Fälle; auf 6c0c464 260 rot):
  - Zugangscodes: Eine Zahl in Jahresform hinter „mit“ bleibt nur vor einem eindeutigen gebeugten Partizip mit einem
    Hauptwort ohne Person frei („mit 2019 eingebauten Rolltoren“); vor einem finiten Verb („Die Kellertür mit 1990
    öffnen Sie …“, „Mit 2016 bedienen Mieter das Rolltor.“) wird sie geschwärzt, mit einem Wort zwischen Zahl und
    Partizip („mit 2021 neu installierter Alarmanlage“) gemeldet (wie auf 0230782). „Der Kellercode lautet 1120.“ wird
    geschwärzt (vorher auf allen Ständen lesbar). Säle und der Genitiv eines zusammengesetzten Hauses gelten
    als Gebäude („Der Code des Gemeindesaals für den Belegungsplan lautet 7718.“: gemeldet; ein bloßes „des Hauses“
    oder „des Vereinsheims“ noch nicht). Ein kurzer Code aus Buchstaben und Ziffern an einem
    Schloss („Garagentor: Code DH2“, „Gartenhaus-Code DG453“, „Die Hintertür hat den Code ZT 77.“ mit dem Leerzeichen
    der Texterkennung) wird gemeldet (vorher auf allen Ständen ohne Meldung; „Code Kellertür AG8“ ohne
    Doppelpunkt noch nicht), ein Code an einem Schloss mit Anzeigewort
    ohne Wort einer Störung („Das Garagentor zeigte den Code 3017“) ebenso. Kein Zugangscode mehr: ein Fehler- oder
    Anzeigecode, wenn ein Gerät ihn „uns“ meldet oder zeigt („Das Garagentor meldete uns den Code 3017, der Monteur
    kommt morgen.“ – nur eine Person, die einen Code meldet, macht ihn zum Zugangscode: „Der Vermieter meldete uns den
    Code der Haustür: 2827“), die Gestalt eines Fehlercodes mit einem Wort der Störung oder Ursache („Das Rolltor hat
    den Code E125, laut Hersteller Überlast am Motor.“: gemeldet), ein Alarmcode, wenn „schaltete … ab“ ein anderes Ding
    betrifft oder „nur für“ keine Person nennt („Nach dem Rauchalarmcode 4471 schaltete die Feuerwehr die Lüftung ab.“:
    gemeldet), ein Ereignis-Alarmcode mit Auslösung, Protokoll oder Ursache im Satz („Fehlalarmcode 7310 laut Protokoll
    der Brandmeldeanlage, Ursache Wasserdampf.“: frei), ein Möbelcode mit Produkt- oder Schadenwort („Farbe“,
    „Aufbauanleitung“, „beim Umzug beschädigt“, „Glasfront gesprungen“: gemeldet) und ein Raumcode mit Bezug auf einen
    Plan, eine Liste, ein Buch oder eine Abrechnung ohne Doppelpunkt, „lautet“ oder „ist“ davor („Raumcode 2017 laut
    Raumbuch“, „Hallencode 0302 im Lageplan“: frei wie auf 5efcc0c, 0230782 und 818990e; „Der Kellercode lautet 1120.“,
    „Lagerhallecode: 9444“ weiter geschwärzt); Listenzeilen „Gebäudecode 1101 (Wohngebäude), …“ unter einer Gebäude-,
    Raum- oder Inventarliste werden nicht mehr geschwärzt, die zeilenweise Selbstkontrolle meldet sie (bis zwölf Zeilen
    unter der Überschrift; unter einer Code-, Schlüssel- oder Mieterliste weiter geschwärzt). „Zum Abschalten des
    Feueralarms: 3401“, „Zugangscode Kellerabteil 5512“, „PIN für Waschküche 2290“ und „Hinterhofcode 4471“ werden
    geschwärzt (vorher auf allen Ständen lesbar). Eine Brandmeldeanlage, -zentrale oder ein Brandmelder gilt als
    Feueralarm („Brandmeldeanlagecode 6881 (nur für den Hausmeister)“: geschwärzt, „Brandmeldeanlagecode: 6881“:
    gemeldet), der Code eines Schranks mit Artikelnummer in Klammern davor wird gemeldet („Code für den Spiegelschrank
    (Artikel 7731): 3074“) – beide vorher auf allen Ständen lesbar. Ein Code am Bedienteil, Display oder an einer
    Zentrale mit einer Bedienung im selben Satz hinter dem Code wird gemeldet („Das Bedienteil zeigte Code 0811 an,
    anschließend ihn am Bedienteil eingeben.“; vorher auf allen Ständen lesbar), nicht mit einem Wort der Störung oder
    Ursache im Satz.
  - Namen: Hinter beim/vom/zum gilt nur ein Verb oder Ereignis aus einem geschlossenen Wortschatz als Gegenbeleg
    („beim Einkaufen“, „vom Hochwasser“), nicht die Endung eines Infinitivs („beim Sönksen“, „vom Holten“: gemeldet) und
    nicht ein Ausrufe- oder Fragezeichen („Vom Kalt! kam der Anruf …“: gemeldet; `tests/test_abnahme5_r7.py` und
    `tests/test_abnahme4_r7.py` verlangten dort bisher keine Meldung). Ein Berufswort, das auch Familienname ist, mit
    einem Geschäft in der Zeile („Wir gehen nachher zum Fischer, frischen Fisch kaufen.“) wird gemeldet statt
    geschwärzt; Rollen- und Ortswörter aus gewöhnlichen Teilen („vom Lohnunternehmer“, „vom Nachbarhof“) bleiben frei.
    Hinter Präposition und Artikel wird ein Wort in Namensgestalt gemeldet („Neben der Kreuzl saß der Fahrer.“).
    Ein Allerweltswort ist ein Name vor einem Vornamen („Zeuge Wasser Anna hat …“: geschwärzt), hinter Anrede und
    Amt („Wie Herr Notar Regen sagte“: geschwärzt), mit Artikel vor einem Lenk- oder Schadenverb („Am Steuer saß der
    Wasser.“: gemeldet) und vor einer Aussage hinter einem Doppelpunkt („Mieter Regen: kein Schaden“: gemeldet; eine
    Lage im Haus nicht: „Mieter Dachgeschoss: kein Schaden“). Ein gewöhnliches Wort hinter einem Personenwort im
    Telegrammstil vor einem Partizip oder Infinitiv wird nicht mehr geschwärzt; vor einem Verb des Gebens, Schickens
    oder Anforderns, direkt oder nur über eine Präpositionalgruppe („Heute Kunde Bescheid gegeben“, „Danach Kunde
    Unterlagen zur Trocknung zugeschickt.“, „Ich habe Mandant Vollmacht zur Kündigung vorgelegt.“), bleibt es frei wie
    auf 5efcc0c, 0230782 und 818990e; mit einem weiteren Hauptwort dazwischen oder vor einem Verb, das eine Person zum
    Gegenstand hat, wird es gemeldet („Heute Kunde Regen Bescheid gegeben.“, „Heute Nachbar Regen angerufen“, „Heute
    Kunde Kopie der Polizeianzeige erhalten“), vor einem Genitiv-Begleiter gar nicht („Kunden Abschluss einer
    Versicherung“). Nicht mehr gemeldet werden Anrede und Titel vor einem Namen – auch in der Selbstkontrolle der
    Ausgabe, in der der Platzhalter nicht im Seitentext steht („Unser Mitarbeiter Herr [PERSON C]“, „Der Gutachter
    Dipl.-Ing. [PERSON B]“) – und Einrichtungen, Geräte und Anlagen mit Artikel als Satzgegenstand („Die Bank hat
    angerufen.“, „Der Motor meldete uns den Code P0300.“; ein Familienname der Wissensbasis bleibt gemeldet) – beides
    nannte der Kehrseiten-Absatz der siebten Nachbesserung. Die KI hält „Brandalarm“ und „des Schreiners“ hinter
    „Beruf des“ nicht mehr für Namen. Die Wissensbasis führt Kocher, Bohrer, Sender, Regler, Kühler, Strahler und
    Hamster als mehrdeutige Familiennamen (gemeldet hinter Artikel und Verb einer Person).
  - Beruf: „von Beruf“, „haupt-“ oder „nebenberuflich“ heben die Ausnahme der Rolle auf („Er ist von Beruf Trainer der
    F-Jugend.“: geschwärzt), eine Rolle hinter „ist“ mit Zwischenwörtern wird gemeldet („Er ist inzwischen Trainer der
    F-Jugend.“; nicht „ist als Betreuer seiner Mutter tätig“), „den Beruf des Polizisten anstreben“ ist ein Beruf (auch
    der schwache Genitiv), „hat“ allein ist kein Verb des Erlernens („Für den Beruf des Dachdeckers hat der Versicherer
    … festgelegt.“: gemeldet statt geschwärzt; ebenso „Für den Beruf des Architekten gilt die Gefahrengruppe A.“, auf
    5efcc0c geschwärzt, auf 0230782 und 6c0c464 lesbar). Ein Satzgegenstand auf „-bote“ ist keine Sache mehr („Der
    Eilbote arbeitet als Lagerhilfe.“: geschwärzt), Rampe, Hebebühne und andere Hilfsmittel sind eine („Die Rampe
    arbeitet als Einstiegshilfe …“: frei). Eine Rolle hinter „ist“ mit einer Zahl dazwischen („Er ist seit 2016
    Treuhänder der Seniorengruppe.“) und „vom“, „zum“ oder „im Beruf des“ („Ihr Neffe träumt vom Beruf des Soldaten.“)
    werden gemeldet (vorher auf allen Ständen lesbar; Kehrseite: auch „Zum Beruf des Dachdeckers gehört
    Schwindelfreiheit.“).
  - Kammfelder: Ein Text zwischen zwei Feldern gehört zum Feld darunter, solange er nicht deutlich näher am Feld darüber
    steht – Abstand zum Feld darunter höchstens das 2,4-Fache des Abstands zum Feld darüber (gemessen: enger
    Zeilenabstand mit Feldname über dem Feld 1,06–1,95, Feldnamen unter den Kästchen 2,89–4,42); so gilt bei engem
    Zeilenabstand der Feldname über dem Feld (c023: Wohnort und Postleitzahl geschwärzt) und unter den Kästchen der
    eigene – ein Feldname über dem Feld, der zum Feld darüber gehört, zählt auf Scans und auf der Textebene nicht
    („Kilometerstand“, „Betrag in EUR“, „Antragsdatum“ unter dem Feld bleiben frei; Kamm-Probe 6 a02). Von zwei
    Feldnamen über und unter einem Feld gilt der untere nur, wenn er deutlich näher ist (0,8 des Abstands), und ein
    Feldname mit Personenbezug geht einem ohne vor – jetzt auch auf der Textebene („Geburtsdatum des Kindes“ über,
    „Datum im Format TTMMJJJJ“ oder „Versicherungsbeginn“ unter den Kästchen: geschwärzt statt gemeldet); ein Hinweis in
    Klammern unter dem Feld ist kein Feldname („Hausnummer“ über, „(wie im Ausweis)“ unter den Kästchen: die Hausnummer
    wird wieder geschwärzt wie auf 5efcc0c). „Geburtsdatum Antragsteller ⇥⇥ 1 2 0 5 1 9 7 9“: die Person ergänzt den
    Feldnamen des Geburtsdatums (vorher auf allen Ständen lesbar oder nur über andere Werte gemeldet). Ein lesbarer
    eigener Feldname ohne Personenbezug („Marke“, „Bank“, „Farbe“, „Tarif“) nimmt nicht den Personen-Feldnamen der
    Zeile; ein unlesbarer nur, wenn die Zeile eine Anschrift ist oder er wie ein Teil eines Namens aussieht („Vomame“) –
    unter „Fahrzeughalter“ liest die Texterkennung „Marke“ als „Make“ oder „Fate“, das Feld wird dann gemeldet statt
    geschwärzt. Zeilen „Kind 1 ⇥ Tag [..] Monat [..] Jahr [....]“ unter einer Überschrift mit Geburtsdatum werden als
    Geburtsdatum geschwärzt (vorher auf allen Ständen lesbar), unter „Versicherungsbeginn“ oder „Antragsdatum“ nicht.
    Ein Feldname in Klammern („Datum (Geburt) ⇥⇥ Tag 1 9 …“) zählt für das geteilte Datum. Die Buchstaben zweier
    Parteien über Spaltentrennern („A ⇥⇥ B“ im Unfallbericht) sind kein Name; Initialen in weit gesetzten Kästchen („L
    ⇥⇥ I“) bleiben einer. Ein gesperrter Wert neben einem langen Feldnamen in derselben Höhe wird geschwärzt („Name des
    Versicherungsnehmers ⇥⇥ K R A U S“), Sperrschrift ohne zugeordneten Feldnamen gemeldet („…nehmersK R A U S“; nicht
    „M U S T E R“ und nicht hinter einem Feldnamen ohne Personenbezug: „Marke ⇥⇥ O P E L“).
  - Anschriften: Eine Lage im Haus als ganzer Wert hinter einem Anschrift-Feldnamen ist keine Straße mehr („Lage der
    Wohnung ⇥ Etage 3“, „Etage 3, Zimmer 4“, „3. OG links“: frei, „Zimmer 4“ und „Whg. 12“ allein meldet die
    Selbstkontrolle; Kamm-Probe der fünften Abnahme k04 auf scan200: gemeldet statt entfernt, AB5U-03). Mit Straße oder
    PLZ im Wert bleibt sie Teil der Anschrift („Etage 3, Hauptstraße 5, 83022 Rosenheim“), Straßennamen wie „Zimmermann
    4“, „Etagenweg 3“ oder „Mitte 3“ bleiben Straßen.
  - Laufzeit: Das Grundwort eines Flurnamens wird nur am Wortende gesucht (ein langes Wort hinter „Beim“ wuchs
    quadratisch), Satzanfänge im Fenster ohne Satzzeichen beginnen am Fensteranfang statt am Textanfang (Alarm-,
    Raum- und Satzprüfung). Neue Wachstumstests (8 000 gegen 64 000 Zeichen, 2 000 gegen 16 000 für ein langes Wort)
    werden mit den eingebauten Regressionen E1 bis E7 und E9 bis E14 rot (E11: Anrede vor einem Platzhalter, eigener
    Test nur für den Rollenwort-Durchlauf); E8 (Fenster vor dem Verb in `_zeigen_person`) bleibt ohne Wirkung, weil
    die Aufrufer den Satz schon begrenzen. Die Form der Abnahme („Beim A…b ist der Stadel abgebrannt.“) braucht in
    der Selbstkontrolle bei 2 000/4 000/8 000 Zeichen 0,06/0,10/0,20 s (6c0c464 5,0/17,1/69,0 s). Gemessen auf dem
    Probensatz der fünften Abnahme (CPU-Zeit je Scan-Seite einschließlich Texterkennung, Oberflächen-Weg, alle drei
    Stände gleichzeitig; 55 Maklerdokumente als Scan mit 200 dpi, 42 Kammfeld-Scans und ein 30-seitiges Dokument
    aus 20 Scans und 10 Kammfeld-Scans mit 300 dpi): ohne Kammfeld 1,82 s gegen 1,96 s auf 5efcc0c (−7 %) und
    1,62 s auf 818990e (+13 %), mit Kammfeldern 3,23 s gegen 3,22 s auf 5efcc0c (drei Runden: +0,03 s, +0,01 s,
    −0,01 s; im Mittel +0,3 %, weniger als die Schwankung zwischen den Runden von 0,17 s) und 1,94 s auf 818990e
    (+67 %), 30 Seiten 2,53 s gegen 2,74 s auf 5efcc0c (−8 %) und 1,99 s auf 818990e (+27 %). Gegenüber 818990e
    bleibt damit der Mehraufwand der Kammfeld-Seiten (Suche und Lesen der Kästchen in der Analyse und in der
    Kontroll-OCR, Kammfeld-Prüfung der Selbstkontrolle) und auf den übrigen Seiten der Aufwand der Kammfeld-Suche
    und der neueren Regeln der Selbstkontrolle.
  - Kehrseiten (nach P2 gemeldet statt still, oder bewusst frei): Gemeldet statt geschwärzt wird gegenüber 6c0c464 neu
    nur „Für den Beruf des X gilt …“ ohne Person (auf 5efcc0c geschwärzt); alle 451 Werte der Differenzprobe, die der
    beste Bezugsstand schwärzt und dieser Stand nur meldet, stehen mit Grund in der Tauschliste. Ende zu Ende sind es
    fünf Fälle (je Text und Scan): Hängeschrank aus dem Katalog, Alarmanlage mit „danach scharf schalten“, „Beruf des
    Architekten gilt“, Möbelcode mit Lieferschein, „Mitarbeiter Hochstelle“. Mehr Meldungen als vorher: Hof-Kandidaten
    mit Infinitiv-Endung, „!“ oder „?“, ein Wort in Namensgestalt hinter Präposition und Artikel (K12: 162 gemeldet,
    5efcc0c 43), eine Rolle hinter „ist“ mit Zwischenwörtern, „Zum Beruf des Dachdeckers gehört …“,
    Raumcode-Listenzeilen, Sperrschrift ohne Feldnamen und Kammfelder mit verlesenem eigenen Feldnamen; in der
    Differenzprobe haben 5 213 Texte einen Verdacht (6c0c464 4 465, 5efcc0c 4 068, 0230782 3 003). Bewusst frei
    (sicherer Gegenbeleg, Gegenfälle in `tests/test_abnahme6_r7.py`): Anrede und Titel vor einem Platzhalter,
    Einrichtungen als Satzgegenstand, Raumcodes mit Plan- oder Listenbezug ohne „lautet“ oder Doppelpunkt, Codes, die
    ein Gerät „uns“ meldet, Alarmcodes mit Auslösung, Protokoll oder Ursache, gewöhnliche Wörter im Telegrammstil vor
    einem Verb des Gebens und eine Lage im Haus als ganzer Anschrift-Wert – ein echter Zugangscode oder Name in genau
    dieser Form bliebe lesbar. Weiter zu oft geschwärzt (wie auf 6c0c464): „Danach Kundin Formular zur Stehlgutliste
    gemailt (…)“, „Heute Zeuge Aussage … bestätigt“ und „Gebäudecode 2203 (Lagerhalle), Raumcode 2017
    (Besprechungsraum)“; Fachwörter wie „DIN 14675“ oder „Invaliditätsgrundsumme“ entfernen alle Stände.
  - Gemessen (Stand vor dem Commit, Proben der Abnahmen 2 bis 6): Differenzprobe mit 25 032 Texten und 14 021 geheimen
    Werten weg/gemeldet/lesbar 9 880/3 499/642 (6c0c464 9 566/2 808/1 647, 5efcc0c 8 964/2 380/2 677, 0230782 7 778/1
    728/4 515); kein Wert schlechter als der beste der fünf Bezugsstände außer 451 Tauschwerten (gemeldet statt
    geschwärzt, Tauschliste) und fünf gewollten (vier Doku-Beispiele zu Anrede und Einrichtung, ein Zählartefakt);
    berührte Prüfwörter 258 (5efcc0c 315). Ende zu Ende (29 Probendateien): kein Wert schlechter als auf 5efcc0c oder
    0230782 außer den fünf gemeldeten Tauschfällen, 26 stille Werte (je Datei höchstens so viele wie dort). Über-Probe
    der sechsten Abnahme: nicht geheime Wörter entfernt 22 (6c0c464 106, 5efcc0c 30, 0230782 28), der fünften 20
    (0230782 26). Kammfelder: Kamm-Probe 6 nicht geheim entfernt 6 (0230782 22), eigen606 geheim weg 166 von 216
    (6c0c464 103, 5efcc0c 159), c023 Wohnort und PLZ geschwärzt; Kamm-Probe 5 k01–k05 nicht geheim entfernt 2 (0230782
    2, 5efcc0c 7).
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
- **Personen und Geburtsdaten (Domänen-Durchsicht, Runde 5):** Geburtsdaten von Kindern und Mitversicherten ohne
  „geb.“ („Kind 2: Bastian Leutgeb, 30.06.2018“, Kinderlisten mit Tabstopps, „Reisende: Kranich, Detlef, 12.04.1969;
  …“), „Geburt des Kindes am …“, „Entbindung am …“ und das Geburtsjahr werden geschwärzt; Behandlungs-, Rechnungs-
  und Vertragsdaten hinter Ärzten und Familienrollen bleiben stehen. Namen hinter rund 240 weiteren Rollen
  (Leasingnehmerin, Sozius, Gegner, Beklagte, Tierhalter, Rechnungsempfänger, „Name des Hundehalters“ …), hinter
  Dienstgraden und Amtsbezeichnungen („KHKin Sedlmayr“ samt Kürzel, „Eibl, JAng“), im Kurzrubrum („Kranzbühler ./.
  Felsberger“), in Nachbarschaftsangaben, als „Nachname, V.“ in Listen, in den Feldern C.1.1/C.1.2 der
  Zulassungsbescheinigung Teil I und vor „GbR“ werden erkannt; die Anschrift in derselben Zeile hinter einem solchen
  Etikett gilt nicht mehr als Firmenanschrift. Die USt-IdNr. von Einzelkaufleuten und Freiberuflern wird geschwärzt,
  Berufe auch in der Spalte „Beruf“/„Tätigkeit“ und im Kastenformular. Nicht mehr als Namen geschwärzt werden
  Marken, Modelle und Tierrassen (neue Wortliste `sachnamen.txt`), medizinische Fachwörter, Firmen hinter
  Rollen-Etiketten, Partizipien wie „Ausgefertigt“ und Gattungswörter vor einem Unfallort („Turnhalle der
  Mittelschule Erding“) – Marke, Modellcode und Rechtsform zählen dabei nur in derselben Tabellenzelle
  („Tschernyschow ⇥ PHV“ bleibt ein Name), und Familiennamen wie „Petraitis“, „Klose“ oder die Initiale in „M.
  Weber“ gelten nie als Diagnose. Die Restrisiko-Prüfung kennt dieselben Regeln und meldet weniger Fehlverdacht
  (TAN-Komposita, „Die Scheibe …“, Miteigentumsanteile, Modellnummern, „Ihnen“).
  Nachgezogen: die Anschrift im Feld C.1.3 der Zulassungsbescheinigung (Feldcode allein ist kein Rest), Namen im
  Flugschein-Format „KRANICH/BIRGIT MRS“, Teilnehmerlisten mit Laufnummern in einer Zeile („1. Kranich, Detlef
  2. Kranich, Birgit“), unbekannte Familiennamen hinter einer Geschäftsbezeichnung („Physiotherapie Oberprieler“)
  und der Beruf unter seinem Feldbezeichner, wenn die OCR das Kastenformular als Zeile aus Feldbezeichnern liest
  („Telefon ⇥ Beruf“ ⏎ „08631 98765 ⇥ Pflegehelferin“). Personennamen in einer Versicherer-, Bank- oder
  Krankenkassen-Spalte („Adam Riese“ unter „Versicherer“) gelten als Organisation – in Erkennung und
  Restrisiko-Prüfung. Behoben wurden dabei Rückschritte derselben Runde: ein Name vor einem Datum, Jahr, einer
  Telefonnummer oder Zahl galt als Modellbezeichnung, „Max Mustermann, 02.09.1961: …“ und Geburtsdaten hinter
  „Dr.“ galten als Behandlungsdatum, Doppelnamen wie „Schmidt-Wald“ wurden nicht mehr gemeldet, und „Markt
  Schwaben“ verlor seinen Ortsnamen.
- **Tabellen und Scans (Domänen-Durchsicht, Runde 5):** Bricht eine Tabellenzelle in eine zweite Zeile um
  („Eheleute“ ⏎ „Gstettner“, „Am Gänsbichl“ ⏎ „4, 84453 Mühldorf a. Inn“), wird sie als Ganzes gelesen: Namen und
  Anschriften darin werden geschwärzt, beide Teile einer Person tragen denselben Platzhalter, und ein Bruchstück wie
  die Hausnummer „4“ wird nicht an anderen Stellen geschwärzt. Leicht schief eingezogene Scans (unter 1°) behalten
  in Kastenformularen und kleinen Tabellen ihre Spalten (PLZ, Ort, Arbeitgeber, Vers.-Nr., Geburtsdatum unter
  „geb. am“). In Kastenformularen und Abrechnungen mit mehreren Etikett- und Wertzeilen beginnt jede Etikettzeile
  einen neuen Kopf: „Kreditinstitut“ und die Sparkasse werden nicht mehr zum Arbeitgeber, das Etikett „Beruf“ nicht
  mehr Teil der Telefonnummer, die Beitragsgruppe „1111“ keine SV-Nummer; Berufe unter „Beruf des Ehepartners“
  werden geschwärzt. Namen enden am Spaltentrenner („Mooslechner, Anton ⇥ PHV“: die Sparte ist kein Vorname und
  trägt nicht mehr den Platzhalter des Kunden), eine Vertragsnummer mit Tausenderpunkten („7.712.345“) unter einem
  Kennungs-Spaltenkopf wird geschwärzt. Feld-Etiketten eines Ausweises („Given names“, „Nationality“) werden auch
  dann nicht als Namen geschwärzt, wenn die Texterkennung den Ausweis als Tabelle liest. Die Restrisiko-Prüfung meldet
  keinen Fehlverdacht mehr für Spaltenköpfe und Etikettwörter („Sparte“, „Ausgeübter Beruf“, „Given names“, „Lieu de
  naissance“), Ortsnamen in Firmennamen („Hausverwaltung Inntal GmbH“) und Fließtext unter einer Tabelle – ein solcher
  Verdacht machte die Datei `_PRUEFEN`, lag aber nicht auf dem Leck; umbrochene Straßen und Nummern mit
  Tausenderpunkten unter einem Kennungskopf meldet sie dagegen.

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
- **Kammfelder:** neues Modul `anonymisierer/kammraster.py` (Kästchenreihen im Bild finden, Linien entfernen,
  Füllung je Kästchen, `wert_ohne_personenbezug`), `ocr.py` (Linien vor der Erkennung entfernen, zweiter Lauf nur
  über die Felder, `ergebnis()["kammfelder"]`, `OcrDienst.kammfelder_falls_bekannt`), `Seite.kammfelder` im
  Seitenmodell, Erkennungsregel `struktur.kammfeld_scan` (`detektoren/kammfelder.py`), Restrisiko
  `_kammfelder_pruefen` (Parameter `kammfelder` von `restrisiko_pruefen`). Tests in
  `tests/test_kammfelder_scan.py`: Stile, Kästchenbreiten 4–8 mm, 150/200/300 dpi, Schräglage, IBAN-Gruppen, Fax
  (unterbrochene und fehlende Linien), Feldname links/oben; Gegenproben: leere Felder, Felder ohne Personenbezug,
  Tabellen, Ankreuzkästchen, Unterschriftslinie, Fließtext, Schreibmaschinenzeilen, Schrift auf Schreiblinien.
  Kammfelder der Textebene (`struktur.kammfeld`): kurze Werte (`_kurzer_lauf`, `_kurz_passt`) und mehrere
  Feldnamen derselben Kategorie darüber (`_etikett_darueber`); Kundenzeilen mit OCR-Zellen
  (`struktur_adresse.personen_formzeile`). Tests in `tests/test_kammfelder_textebene.py` mit Gegenproben
  (Zählfelder, Kürzel, Initialen, Ziffern unter Namensfeldern, Feldnamen verschiedener Art, Mitarbeiterzeile,
  Briefkopf mit Registerangaben). Gemessen je Kernwert (entfernt von allen, stille Lecks), vorher 818990e, bei den
  neun Kammfeld-Scans der Entwicklungskorpora 8aecade: Kammfeld-Scans 29 → 92 von 106, still 16 → 0; eigene
  Formulare Seed 7 (zum Abstimmen benutzt) 30 → 151 von 155, still 37 → 1 (Bewertungsartefakt); eigene Formulare
  Seed 31 (nicht abgestimmt: Kästchen 4–8 mm, zu, als Kamm oder unten offen, Feldname links oder darüber, Block- und
  Handschrift, 150/200/300 dpi, Schräglage bis 1,8°, JPEG, Rauschen, Fax) 38 → 150 von 162, still 12 → 0; neu
  erzeugte Formulare des Generators (Seed 4711 und 9090) 151 → 219 von 251, still 3 → 0. Sieben Werte gehen von
  geschwärzt auf gemeldet zurück (drei in Seed 31, je einer in Seed 4711 und 9090, zwei in s3x): Der Feldname direkt
  über einem Feld wird auf dem bereinigten Bild nicht immer gelesen. Laufzeit: Die Angabe „Scan-Seiten mit
  Kammfeldern etwa +90 %, übrige Scan-Seiten etwa +9 %“ (gepaart gemessen auf d23f173) war für die übrigen Seiten nicht
  nachvollziehbar; die vierte Abnahme maß auf 0230782 gegen 818990e (CPU je Scan-Seite einschließlich Texterkennung)
  etwa +100 % auf Kammfeld-Seiten und +29 % auf übrigen Scan-Seiten (+16 % nur für die Analyse). Den Stand nach der
  sechsten Nachbesserung nennt deren Eintrag oben.
- Neuer Aufbau: ein Seitenmodell für Analyse, Schwärzung und Selbstkontrolle (`seitenmodell.py`),
  Erkennungsregeln als Module mit Register und Rückfallliste für die EXE (`anonymisierer/detektoren/`),
  Wissensbasis (`wissen.py`, 23 Wortlisten in `anonymisierer/daten/`), dazu `kundenliste.py`,
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
- Domänen-Probe als Werkzeug im Repository (`werkzeuge/domaenenprobe/`): die 41 Falldateien der
  Domänen-Durchsicht (691 Fälle mit 2261 frei erfundenen geheimen Werten aus Kfz, Personenversicherungen, Sach,
  Finanzen/Digitales und Briefverkehr/Listen/Scans), der Harness `e2e.py` und die Messung `messen.py` (je Wert weg,
  sichtbar mit `_PRUEFEN` oder STILL; Vergleich mit `referenz.json`, gemessen auf 98a3957). Die Messlogik ist
  unverändert übernommen, nur Pfade und Plattform angepasst (relative Pfade, UTF-8, Windows ohne `nice`,
  Tesseract- und Schriftsuche); eine fehlschlagende Tesseract-Kommandozeile bricht ab, statt Werte still als „weg“ zu
  zählen. Eine Regressionsprobe für die Entwicklung, keine Blindprüfung – die Regeln wurden an diesen Fällen
  verbessert. `tests/test_domaenenprobe.py` prüft Falldateien und Referenz und lässt einen kleinen Text-Fall Ende zu
  Ende laufen (OCR dort mit PyMuPDF, weil die CI keine Tesseract-Kommandozeile hat).
- Kommentare im Code verweisen auf Entwicklungsunterlagen (`CONTRACT_V2.md`, `BENCHMARK_SCHEMA.md`, „Vertrag
  Abschnitt …“), die nicht im Repository liegen.
- Zusammenführung der Runde 5 (Pakete Kennungen/Kfz und Personen/Tabellen): Regeln, die beide Pakete getrennt
  eingeführt hatten, gibt es nur einmal – für Erkennung und Restrisiko-Prüfung gemeinsam die USt-IdNr. und
  HRA-Nummer von Einzelkaufleuten, Inhabern und Freiberuflern (`kennungsformen.einzelkaufmann_block`,
  `kennungsformen.ust_id_der_firma`; ein Trennpunkt „·“ allein macht eine Fußzeile nicht zur Firmenangabe) und
  Nummern mit Tausenderpunkten unter einem Kennungs-Spaltenkopf (`kennungsformen.kennungswert`); „Marke und Modell
  sind kein Name“ prüft eine Funktion (`namen._ner_sachtreffer`). Plattformnamen (Instagram, WhatsApp …) stehen
  nur in `allerweltswoerter_gross.txt`, nicht zusätzlich in `sachnamen.txt`.

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
- Neuer Job **`domaenenprobe`** (ubuntu-latest), nur von Hand („Run workflow“ mit Haken „domaenenprobe“): misst die
  volle Domänen-Probe mit der Tesseract-Kommandozeile und lädt `bericht.md` und `ergebnis.json` als Artefakt
  `domaenenprobe-bericht` hoch. Die Jobs `pytest` und `exe` laufen unverändert.
- Der Job `pytest` installiert zusätzlich Pillow – wie pyyaml nur für Tests: `tests/test_tabellen_scans.py`
  erzeugt damit die schräg gescannten Seiten; ohne es schlugen sieben Tests mit „No module named 'PIL'“ fehl.
  Der Job `domaenenprobe` installiert es ebenfalls (Scan-Varianten der Falldateien). In `requirements-dev.txt`
  steht es bewusst nicht: `EXE-bauen.bat` installiert diese Datei, und PyInstaller packte Pillow sonst in die EXE.

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
