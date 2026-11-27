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
  `_PRUEFEN` mehr im Namen trägt (`anonym_NN.pdf`) – nie das Original und nie eine unfertige
  Zwischendatei `.anonym_tmp_…`.
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

Beim ersten Start zeigt das Programm die wichtigsten Grenzen als „Bitte vor der ersten Nutzung
lesen“ – nicht alle Punkte dieser Liste. Später finden Sie die Hinweise jederzeit unter Hilfe →
„Hinweise vor der Nutzung …“ und Hilfe → „Was wird nicht erkannt?“.

## Was wird erkannt?

### Schutzstufen

Über den Häkchen der Kategorien wählen Sie eine Schutzstufe. Die Häkchen folgen der Stufe;
die Wahl wird gespeichert.

| Schutzstufe | Was angehakt wird |
|---|---|
| Ausgewogen | Direkte Kennungen: Namen, Anschriften, Geburtsdaten, IBAN, BIC, E-Mail, Telefon, Vertrags-, Steuer-, Sozialversicherungs-, Krankenversicherten-, Ausweis- und Fahrzeugnummern, Kennzeichen, IP-Adressen, Zugangsdaten, Profilnamen, Standort-Koordinaten … – mehr Zusammenhang für die KI. |
| **Hoch (Standard, empfohlen)** | Zusätzlich Beruf, Arbeitgeber, ausländische Anschriften, Orte ohne PLZ und Gesundheitsdaten (Diagnosen, Medikamente). |
| Maximal | Zusätzlich Konfession, Daten wie „02.09.1983“, die mindestens 14 Jahre zurückliegen (außer kurz hinter Wörtern wie „am“, „vom“ oder „Beginn“), unbekannte Eigennamen bei Personen – und Bilder sowie erkannte Fotos werden abgedeckt (siehe [unten](#bilder-fotos-und-lichtbilder)). Größter Schutz, am wenigsten Zusammenhang für die KI. |
| Benutzerdefiniert | Erscheint, sobald Ihre Häkchen zu keiner Stufe passen, die mindestens so streng ist wie die zuletzt gewählte. Es gelten dann weiter deren Erkennungsregeln – wer in „Maximal“ die Diagnosen abwählt, behält also z. B. das Abdecken der Bilder. |

**Gesundheitsdaten** (Diagnosen, Medikamente) sucht das Programm in jeder Stufe. In „Hoch“
und „Maximal“ sind sie angehakt und werden geschwärzt. In „Hoch“ bleiben nur allgemeine
Fachbegriffe ohne Etikett in Dokumenten ohne jeden Personenbezug (z. B. „Physiotherapie“ in
einer Tarifübersicht) nicht angehakt (Zeichen ⚕). In „Ausgewogen“ stehen alle Gesundheitsdaten
**nicht angehakt** in der Fundliste und bleiben lesbar, solange Sie sie nicht anhaken – der
Abschlussdialog der Analyse weist darauf hin. Die **Konfession** (Religion, Kirchensteuermerkmal
„rk“, „ev“ – eine besondere Kategorie nach Art. 9 DSGVO) ist in „Ausgewogen“ und „Hoch“ nur
angeboten, in „Maximal“ angehakt.

Ändern Sie nach der Analyse die Schutzstufe, ein Häkchen, eine Liste oder die Kundenliste,
wird die Fundliste zurückgesetzt: Dann bitte erneut analysieren. In der Vorschau gesetzte
Markierungen gehen dabei verloren.

### Kategorien

Die Tabelle wird aus dem Programm selbst erzeugt und passt deshalb zu ihm. „Angehakt ab Stufe“
nennt die mildeste Schutzstufe, in der die Kategorie angehakt ist („Ausgewogen“ heißt also: in
jeder Stufe). Jedes Häkchen lässt sich auch einzeln setzen. Was die Erkennung nicht leistet,
steht unter [Was NICHT erkannt wird](#was-nicht-erkannt-wird).

<!-- TABELLE-ANFANG -->
| Kategorie | Beispiel | Wird ersetzt durch | Angehakt ab Stufe | Hinweis |
|---|---|---|---|---|
| Personennamen (KI-Erkennung) | Max Mustermann | `[PERSON A], [PERSON B] …` | Ausgewogen | KI-Modell (spaCy), Namenslisten und Regeln; gleiche Person = gleicher Platzhalter im Dokument – auch für den Geburtsnamen hinter „geb.“/„geborene“ („Anna Weber geb. Schulz“) |
| IBANs | DE89 3704 0044 0532 0130 00 | `[IBAN]` | Ausgewogen | auch mit falscher Prüfziffer, wenn sie eindeutig wie eine IBAN aussieht (Hinweis „Lesefehler?“) |
| E-Mail-Adressen | max.mustermann@example.de | `[E-MAIL]` | Ausgewogen | auch verschleiert („name (at) web (punkt) de“, „name [at] gmx [dot] de“) |
| Telefonnummern | 0171 2345678 | `[TELEFON]` | Ausgewogen |  |
| Geburtsdaten | geb. am 02.09.1983 | `[GEB-DATUM]` | Ausgewogen | hinter „geb.“, „Geburtsdatum“, „Geburt des Kindes am“ … oder hinter einem Namen mit Komma, Stern oder Klammer („Max Mustermann, 02.09.1983“) – bei Kindern und Mitversicherten („Kind 2: Lea Brandl, 30.06.2018“) in jedem Alter; in „Maximal“ zusätzlich Daten wie „02.09.1983“, die mindestens 14 Jahre zurückliegen – außer kurz hinter Wörtern wie „am“, „vom“, „seit“ oder „Beginn“ |
| Straße + Hausnummer, Postfach | Hauptstraße 12a | `[ADRESSE]` | Ausgewogen |  |
| PLZ + Ort | 90402 Nürnberg | `[PLZ ORT]` | Ausgewogen |  |
| Vertrags-/Kunden-/Schein-/Aktenzeichen | Versicherungsschein-Nr. LV-2024-887766 | `[VERTRAGS-NR]` | Ausgewogen | Nummer hinter einem Etikett wie „Vertrags-Nr.“ oder in einer Tabellenspalte mit solchem Kopf – auch hinter Zwischenwörtern („Personalnummer beim Arbeitgeber: 4711“), mit Tausenderpunkten („Kundennummer: 4.711.208“, „7.712.345“ unter „Vertrag“) oder als Code („Geräte-ID: TLX-KQ8B-ZR3M“); auch eVB-Nummer (elektronische Versicherungsbestätigung) und Transferticket der Kfz-Versicherung; ohne Etikett MAC-Adresse, EID einer eSIM, Nummer im Marktstammdatenregister, Aktenzeichen eines Gerichts („3 C 456/24“), Flurstück und Grundbuchblatt; nicht Gebühren- und Katalogziffern (GOZ, GOÄ, PZN), Fahrzeugschlüssel (HSN/TSN) und Paragrafen („§ 34d GewO“) |
| Sozialversicherungsnummern | 12 345678 A 123 | `[SV-NR]` | Ausgewogen |  |
| Steuer-IDs | 91064389278 | `[STEUER-ID]` | Ausgewogen | ohne Beschriftung nur mit gültiger Prüfziffer, auch gruppiert („30 268 175 922“) |
| Steuernummern / USt-IdNr. | Steuernummer: 181/815/08155 | `[STEUER-NR]` | Ausgewogen | ohne Etikett nur mit Schrägstrichen; USt-IdNr. nur mit Etikett und nicht die einer Firma (die von Einzelkaufleuten, Inhabern und Freiberuflern schon) |
| Krankenversichertennummern | A123456780 | `[KV-NR]` | Ausgewogen |  |
| Kindergeldnummern | 009FK407160 | `[KINDERGELD-NR]` | Ausgewogen |  |
| Kfz-Kennzeichen | N-XY 123 | `[KENNZEICHEN]` | Ausgewogen | nur mit amtlichem Unterscheidungszeichen (nicht Modellcodes wie „KTM RC 390“), auch „RO - KL 2207“ und klein geschrieben; hinter einem Kfz-Etikett („Versicherungskennzeichen:“, „Kurzzeitkennzeichen“, „Versicherungsplakette Nr.“) auch Versicherungs-, Kurzzeit-, rote und Ausfuhrkennzeichen („435 GHT“, „RO-04 1287“) und ausländische Kennzeichen |
| Fahrzeug-Identnummern (FIN) | WVWZZZ1JZXW000001 | `[FIN]` | Ausgewogen |  |
| Ausweis-/Pass-/Führerscheinnummern | Ausweisnummer: L01X00T47 | `[AUSWEIS-NR]` | Ausgewogen | mit Etikett; Ausweis- und Passnummern auch ohne Etikett, wenn die Prüfziffer stimmt; auf Ausweiskopien auch die maschinenlesbare Zone |
| SEPA-Mandatsreferenzen | Mandatsreferenz MR-2024-0815 | `[MANDATSREFERENZ]` | Ausgewogen | nur hinter einem Etikett |
| BIC (bei IBAN oder Etikett) | COBADEFFXXX | `[BIC]` | Ausgewogen | hinter „BIC“, neben einer IBAN oder in eindeutiger Form (11 Zeichen auf „XXX“ oder mit Ziffer im Ortscode) |
| Kreditkartennummern | 4111 1111 1111 1111 | `[KREDITKARTE]` | Ausgewogen | auch die Kartenprüfnummer (CVC/CVV, „Kartenprüfnr.“, „CID“) hinter ihrem Etikett und in Kartendaten („…, gültig bis 12/27, 739“) – nur dort, nicht dieselben Ziffern an anderer Stelle; „Prüfnummer“ allein nur neben einer Kartenangabe (keine TÜV- oder Gutachten-Prüfnummer) |
| IP-Adressen | IP-Adresse: 84.123.45.67 | `[IP-ADRESSE]` | Ausgewogen | IPv4 mit gültigen Oktetten (ohne Etikett nur mit IP-Bezug in der Zeile oder in der Kopfzeile einer E-Mail „Received: from …“; direkt hinter einem Versionswort wie „Version 10.0.19045.1234“ nie) und IPv6 |
| Zugangsdaten (Benutzer, Kennwort, PIN, Code) | Benutzername: maxmuster82 | `[ZUGANGSDATEN]` | Ausgewogen | Benutzername/-kennung, Kennwort, PIN, Geheimzahl, Aktivierungs-, Freischalt-, Zahlen- und Entsperrcode hinter ihrem Etikett (auch „WPA2-Kennwort“, „Kennwort für das Portal: …“, als Spaltenkopf „PIN“); ein Zugangscode aus Ziffern hinter „Code“ mit einem Schloss davor, im Satz oder dahinter („Haustür: Code 1357“, „(Haustür) Code 1357“, „Die Garage hat den Code 1199.“, „Code 4455 für die Tiefgarage“, „schaltet man mit 6482 aus“, „Das Hoftor geht mit 2601 auf.“) – auch hinter Gebäuden und Behältern mit Schloss („Gartenhaus: Code 9090“, „Geräteschuppen – Code 3016“, Scheune, Stall, Carport, Wallbox, Spind, ein Möbel mit Code: „Code Badschrank: 8815“); an einem sicheren Schloss auch Buchstaben und Ziffern („Die Haustür hat den Code KB475.“) und eine Zahl in Jahresform mit einem Verb der Sicherung („Die Tiefgarage ist mit 1984 gesichert.“), „PIN für Wohnungstür 7100“, „Lagerhallecode: 9444“ und der Code eines Alarms, auch einer Brandmeldeanlage, mit seiner Bedienung oder nur für eine Person („Zum Abschalten des Feueralarms den Code 6619 eingeben.“, „Brandmeldeanlagecode 6881 (nur für den Hausmeister)“); ohne sicheres Schloss meldet die Selbstkontrolle die Ziffern („Waschküche: Code 6161“, „Code lautet 5656.“, „Bitte im Keller nachsehen.⏎Code 9595“, „Feueralarmcode 3401“) – nicht geschwärzt werden „Passwort vergessen?“, „PIN: siehe separates Schreiben“, Fehler- und Anzeigecodes von Geräten („Der Motor meldet den Code P0300“, „Code E-04 blinkt, Elektriker kommt“, „Das Garagentor meldete uns den Code 3017, der Monteur kommt morgen.“; zeigt ein Schloss einen Code ohne Wort einer Störung oder Reparatur – „Das Garagentor zeigte den Code 3017“ – oder trägt es einen kurzen Code aus Buchstaben und Ziffern – „Garagentor: Code DH2“ –, meldet die Selbstkontrolle ihn), Ereigniscodes eines Alarms („Fehlalarmcode 7310 laut Protokoll“, „Feueralarmcode 3401“ – die Selbstkontrolle meldet sie; mit Bedienung, Übergabe, Empfänger oder Geheimhaltung im Satz, z. B. „… an die Mieter weitergegeben“, „bitte vertraulich behandeln“, und als Code in Klammern hinter dem Alarm – „Sabotagealarm (Code 2297) ausgelöst“ – werden sie geschwärzt), Raum- und Hallencodes mit Bezug auf einen Plan, ein Raumbuch oder eine Gebäudeliste ohne Ankündigung „lautet“ oder Doppelpunkt („Raumcode 2017 laut Raumbuch“ und Listenzeilen unter einer Gebäude- oder Raumliste meldet die Selbstkontrolle; Listen der Schlüssel, Codes oder Mieter und eine PIN für einen Raum gelten nicht als Planbezug und werden geschwärzt), Öffnungszeiten („Zugang Lagerhalle: 7-17 Uhr“, „24/7“), ein Baujahr vor einem gebeugten Partizip („mit 2021 erneuerter Heizung“) oder Tarif- und Rabattcodes |
| Profil-/Kontonamen (@-Name, Plattformen) | Instagram @max.muster | `[PROFIL]` | Ausgewogen | @-Namen, Nutzer- und Profilnamen hinter Plattform-Etiketten („eBay-Name:“, „Telegram:“), der Pfad eines Profil-Links („facebook.com/vorname.nachname“) und Kunden-, Vertrags- und Namensangaben in Links („?kdnr=4711081&name=…“) – nicht die Seite einer Firma |
| Standort/Koordinaten (GPS) | GPS: 48.13715, 11.57612 | `[STANDORT]` | Ausgewogen | Koordinaten als Dezimalgrad-Paar, in Grad/Minuten/Sekunden und als Einzelwert hinter „Breite“/„Länge“ (ohne Maßeinheit dahinter) |
| Ausländische Anschriften und Kennzeichen | Kerkstraat 12, 1017 GC Amsterdam | `[AUSLAND]` | Hoch | auch Straßen mit vorangestelltem Straßentyp („Str. Memorandumului nr. 27“, „Calea …“), vierstellige PLZ mit Ort hinter einer Straße oder mit Länderhinweis („8002 Zürich“), sechsstellige PLZ mit Länderhinweis und ausländische Kennzeichen im Satz mit Länderhinweis |
| Orte ohne PLZ (Ort-Datum-Zeile, Geburtsort) | Musterstadt, 03.04.2025 | `[ORT]` | Hoch | Ort-Datum-Zeile, „geboren in …“, „wohnhaft in …“ |
| Beruf (bei Personen) | Beruf: Elektriker | `[BERUF]` | Hoch | hinter „Beruf:“, im Satz („arbeitet als …“, „ist als … tätig“, „verdient ihr Geld als …“, „übt den Beruf der … aus“, auch gebeugt „des Schreiners“, „seit sie Lehrerin ist“, „Ihr Mann, der Polizist ist, …“, Tätigkeiten wie „arbeitet als Putzfrau“), in der Spalte „Beruf“/„Tätigkeit“ einer Personenliste, im Beruf-Feld eines Kastenformulars (Wert unter dem Feldbezeichner, auch unter „Beruf des Ehepartners“) und auf Scans rechts neben dem Feldnamen „Beruf“ – nicht die Rolle des Maklers, einer Firma oder eines Vereins („Wir sind als Versicherungsmakler für Sie tätig“), Vertretungs- und Ehrenämter („als Betreuer seiner Mutter“, „ehrenamtlich als Trainer“) und Ausfüllhinweise („bitte genau angeben“) |
| Arbeitgeber (bei Personen) | Arbeitgeber: Muster Bau GmbH | `[ARBEITGEBER]` | Hoch | hinter „Arbeitgeber:“ oder im Satz; bekannte Versicherer, Banken und Behörden bleiben stehen |
| Diagnosen, ICD-Codes (Gesundheitsdaten) | Diagnose: Diabetes mellitus (E11.9) | `[DIAGNOSE]` | Hoch | nur bekannte Begriffe und ICD-Codes mit Gesundheitsbezug; in „Ausgewogen“ nur angeboten (⚕, nicht angehakt), in „Hoch“ nur ohne Personenbezug im Dokument angeboten |
| Medikamente (Gesundheitsdaten) | Medikation: Metformin 500 mg | `[MEDIKAMENT]` | Hoch | nur bekannte Begriffe mit Gesundheitsbezug; in „Ausgewogen“ nur angeboten (⚕, nicht angehakt), in „Hoch“ nur ohne Personenbezug im Dokument angeboten |
| Religion/Konfession (Art. 9 DSGVO) | Konfession: römisch-katholisch | `[RELIGION]` | Maximal | Konfession bzw. Kirchensteuermerkmal („rk“, „ev“) hinter ihrem Etikett oder unter einem Spaltenkopf „Konf.“; besondere Kategorie nach Art. 9 DSGVO – in „Ausgewogen“ und „Hoch“ nur angeboten (nicht angehakt) |
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
| `[FOTO]` | erkannter Fotobereich auf einer Scan-Seite oder einem Foto (nur „Maximal“) |

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
  die einer dem Programm unbekannten Firma steht als nicht angehakter Fund „vermutlich
  Firmenanschrift – nicht geschwärzt, bitte prüfen“ in der Liste. Die Anschrift einer Person
  im eigenen Briefkopf wird geschwärzt – wirkt der Briefkopf aber wie der einer Firma (z. B. mit
  Webadresse, Bankverbindung oder USt-IdNr., wie oft bei Selbständigen), nur dann, wenn davor
  ein Name steht, den die Namenslisten des Programms als Vor- oder Nachnamen kennen, und auch
  dann nicht immer (z. B. nicht, wenn eine Zeile wie „Mitglied der Handwerkskammer …“ zwischen
  Name und Anschrift steht). Sonst steht auch sie nicht angehakt als „vermutlich
  Firmenanschrift“ in der Liste. Bei Selbständigen deshalb jeden solchen Fund prüfen und
  anhaken, wenn es ihre Anschrift ist – auch wenn ihr Name davorsteht.
- **Versteckte Teile** der Datei – Dateieigenschaften, Lesezeichen, Anhänge, Formulardaten,
  Skripte – prüft die Analyse mit denselben Regeln. Die Ausgabe enthält sie nicht mehr.
- **Scans und Fotos** liest die eingebaute Texterkennung (OCR); schräge Scans werden gerade
  gerückt, gedrehte Seiten erkannt. Auf so gelesenem Text gleicht das Programm typische
  Lesefehler aus (O/0, I/1 …) – nicht aber bei Text, der in der PDF selbst gespeichert ist (die
  „Textebene“, z. B. bei am Computer erstellten PDFs); den liest es direkt.
- **Kundenliste (optional):** Über Menü „Kundenliste“ → „Kundenliste importieren …“ (oder
  „Importieren …“ in Schritt 2) lesen Sie eine CSV-Datei aus Ihrem Verwaltungsprogramm ein.
  Spalten werden möglichst automatisch erkannt, sonst ordnen Sie sie im Dialog zu. Gespeichert
  werden keine Namen oder Nummern im Klartext, nur Prüfwerte, an denen das Programm sie
  wiedererkennt. Passt in einem Dokument ein starkes Merkmal eines Kunden (voller Name,
  Kunden-/Vertragsnummer, IBAN oder E-Mail), sucht das Programm alle seine Merkmale – auch
  Geburtsdatum, Anschrift, Telefon, Kennzeichen sowie Vor- und Nachname einzeln.

### Bilder, Fotos und Lichtbilder

- **Lichtbilder auf Ausweiskopien** (Personalausweis, Pass, Führerschein …) sucht das
  Programm in jeder Schutzstufe – auf Scan-Seiten und in eingebetteten Bildern. Ein Treffer
  steht als angehakter Fund „Lichtbild (Ausweis)“ in der Liste und wird mit `[LICHTBILD]`
  abgedeckt.
- Ist ein Foto auf einer ausweisartigen Fläche nicht sicher ein Lichtbild (z. B. eine stark
  vergrößerte Kopie), steht es **nicht angehakt** in der Liste: ansehen und anhaken, wenn es
  ein Gesicht zeigt.
- Bleibt ein gefundenes Lichtbild sichtbar (abgewählt, oder unsicher und nicht angehakt) oder
  findet das Programm auf einer erkannten Ausweiskopie kein Lichtbild, heißt die Ausgabe immer
  `_PRUEFEN` – auch ohne „Freigabe vor Weitergabe“. Eine Ausweiskopie erkennt es am Ausweistext
  auf dem Bild (z. B. der maschinenlesbaren Zone oder der Überschrift „Personalausweis“).
  Findet es weder Lichtbild noch Ausweistext (etwa auf einem unscharfen Scan), entfällt dieser
  Schutz – deshalb „Freigabe vor Weitergabe“ eingeschaltet lassen.
- Andere Gesichter und Fotos (z. B. Schadenfotos) bleiben in „Ausgewogen“ und „Hoch“ stehen.
- **„Maximal“** deckt zusätzlich jedes Bild auf Textseiten ab (`[BILD]`) und auf Scan-Seiten
  und Fotos die Fotobereiche, die die Fotoerkennung findet (`[FOTO]`). Ein Foto, das sie nicht
  als Foto erkennt (z. B. ein sehr blasses Foto oder eines mit viel Text darauf), bleibt stehen.
  Weitere Ausnahmen: winzige Bilder (Symbole, Linien) bleiben; ein Bild, das mindestens die
  halbe Seite bedeckt (Hintergrund, fotografiertes Blatt), bleibt wie ein Scan stehen –
  abgedeckt werden nur die Fotos darin; Text, der über einem Bild liegt, bleibt lesbar. Jede
  Abdeckung lässt sich in Fundliste und Vorschau abwählen.
- **Unterschriften und Handschrift auf Scans bleiben auch in „Maximal“ stehen** – die
  Fotoerkennung blendet Striche bewusst aus. Nur eine Unterschrift, die als eigenes Bild in
  einer digitalen PDF steckt, deckt „Maximal“ als `[BILD]` ab.

## Was NICHT erkannt wird

Bitte vor dem Einsatz lesen – das sind die Grenzen des Werkzeugs:

- **Unterschriften, Handschrift, Stempel** – werden nicht geschwärzt, auf Scans auch in
  „Maximal“ nicht. Die Texterkennung (OCR) liest Handschrift nicht zuverlässig. Die
  Restrisiko-Prüfung meldet auf Scans nicht gelesene Tinte in Unterschriftsfeldern, neben
  Personenangaben, neben einer geschwärzten Anschrift (etwa eine handschriftliche Postleitzahl
  vor dem geschwärzten Ort), hinter Bankangaben und hinter dem Etikett einer eVB-Nummer, eines
  Transfertickets oder einer Kartenprüfnummer (etwa ein Kammfeld mit einer Ziffer je Kästchen)
  als Verdacht; ein Unterschriftszug neben einem schon geschwärzten Namen gilt nicht als
  Verdacht. Als Linien gezeichnete Unterschriften, Stempel oder Logos in digitalen PDFs nennt
  nur ein Hinweis („Grafiken/Zeichnungen …, die nicht geprüft werden“). Abhilfe: in der
  Vorschau einen Rahmen darüberziehen.
- **Gesichter und Fotos** – gesucht werden nur Lichtbilder auf Ausweiskopien, und die nicht
  immer. Andere Gesichter und Fotos bleiben in „Ausgewogen“ und „Hoch“ stehen. In „Maximal“
  bleiben winzige Bilder, Bilder über mindestens die halbe Seite (nur die Fotos darin werden
  abgedeckt), gezeichnete Grafiken sowie Fotos, die die Fotoerkennung nicht als Foto erkennt.
- **Diagnosen, Krankheiten, Medikamente** – erkannt werden nur bekannte Begriffe aus den
  Wortlisten des Programms und ICD-10-Codes, und nur mit Gesundheitsbezug (z. B. hinter
  „Diagnose:“ oder „leidet an“). In „Ausgewogen“ sind sie nur angeboten (⚕, nicht angehakt)
  und bleiben lesbar, wenn Sie sie nicht anhaken; ab „Hoch“ werden sie geschwärzt.
- **Beruf und Arbeitgeber** – nur mit Etikett („Beruf:“, „Arbeitgeber:“) oder im Satz
  („arbeitet als …“) und erst ab „Hoch“. **Familienstand und Einkommen** werden nicht erkannt.
- **Namen hinter Personenwörtern** – „Nachbar Zettl hat den Brand gemeldet.“, „Monteur Grohe kam
  …“, „Elektriker Miele kam …“ oder „Rücksprache mit Mieter Liebherr“ werden geschwärzt. Ist das
  Wort zugleich ein gewöhnliches Wort hinter einem Begleiter („beim Mieter Schimmel festgestellt“), steht
  dahinter nur „ist“ oder „war“ („Monteur Grohe war vor Ort“) oder ist es eine Marke hinter dem
  Personenwort einer Firma („Laut Monteur Buderus …“), bleibt es stehen und wird als Verdacht gemeldet
  (`_PRUEFEN`) – bitte in der Vorschau ansehen. Ohne Begleiter gilt auch ein gewöhnliches Wort als Name
  („Rücksprache mit Nachbar Wasser am Montag“, „Laut Nachbarin Regen …“), ebenso ein Wort am Satzanfang mit
  dem Zustand einer Person dahinter („Zeuge Tremml wird morgen zurückrufen.“, „… ist seit Montag im Urlaub“). Das gilt auch für einen echten Namen dieser Art ohne Verb einer Person („mit
  dem Kollegen Wolf telefoniert“). Abteilungs-, Orts- und Firmenwörter hinter einem Personenwort
  („Kollege Außendienst“, „Nachbar Gegenüber“, „Techniker Wasserversorger“, „Mieter Erdgeschoss“, „Kunde Gewerbe“)
  werden nicht geschwärzt, nur gemeldet. Gemeldet (nicht geschwärzt) werden außerdem ein Familienname mit Artikel im Satz einer Person („Laut
  Polizei hat der Schwarzl den Unfall gemeldet.“), ein Beruf, Titel oder eine Rolle hinter einem Personenwort („Kollege
  Pfarrer hat angerufen.“, „Kunde Halter wurde befragt.“), ein Wort mit Artikel, das zugleich Tier, Marke, Gerät oder
  Rufname ist, mit der Tat einer Person („Den Schaden meldete der Fink.“, „Der Kocher hat angerufen.“) und ein
  unbekanntes Wort hinter „beim“, „vom“, „zum“ („Zum Grebl fahren wir am Montag.“); ein bekannter Familienname dort
  wird mit Besuch, Entfernung, Weg oder Besitz geschwärzt („Wir waren beim Gruber zum Essen.“, „Die Kühe vom Gruber …“).
  Dabei meldet die Selbstkontrolle auch Wörter, die kein Name sind („Vom Sturm …“, „beim Holzhändler in Waging“) –
  feste Wendungen und Infinitive („Zum Glück“, „Beim Grillen“) bleiben frei.
- **Kammfelder** (je Kästchen ein Zeichen) auf Scans: Steht der Feldname über dem Feld und liest die
  Texterkennung ihn nicht, wird der Inhalt nur gemeldet, nicht geschwärzt. Nicht als Kammfeld erkannt
  werden Raster ganz ohne Linien (etwa ein Fax, auf dem die Kästchenlinien fehlen), Felder mit nur zwei
  Kästchen ohne ein gleichartiges Feld in derselben Zeile („Tag [..] Monat [..] Jahr [....]“ wird erkannt,
  ein einzelnes Feld mit zwei Kästchen nicht – dessen Inhalt prüfen die übrigen Regeln und die
  Restrisiko-Prüfung) und Seiten, deren Bild für die Texterkennung größer als 15 Megapixel wird (etwa A3
  bei 300 dpi). Eine Tabelle mit gleich breiten schmalen Zellen kann als Kammfeld gelten; ihr Inhalt wird
  dann meist gemeldet. Ein Feldname zwischen zwei Feldern gilt für das Feld darunter, solange sein Abstand
  dazu höchstens das 2,4-Fache des Abstands zum Feld darüber ist; steht ein Formular mit Feldnamen unter den
  Kästchen enger, kann ein Feld den Feldnamen des nächsten Felds bekommen. Liest die Texterkennung einen
  eigenen Feldnamen ohne Personenbezug falsch („Make“ statt „Marke“ unter „Fahrzeughalter“), wird das Feld
  gemeldet statt geschwärzt.
- **Nummern ohne Beschriftung** – SEPA-Mandatsreferenzen, USt-IdNr., Führerscheinnummern
  (außerhalb einer Führerscheinkopie), Steuernummern ohne Schrägstriche und BICs, die weder
  neben einer IBAN stehen noch eindeutig geformt sind (z. B. „COBADEFF“ ohne Ziffer), werden
  nur hinter einem Etikett gefunden („Mandatsreferenz“, „USt-IdNr.“, „Führerscheinnummer“,
  „Steuernummer“, „BIC“ …). Steht so eine Nummer nur ohne Beschriftung im Dokument, bleibt sie
  stehen – ebenso hausinterne Nummern ohne festes Format (ggf. über „IMMER schwärzen“ oder die
  Kundenliste). Ist sie an einer Stelle mit Etikett erkannt, wird sie auch an allen anderen
  Stellen des Dokuments geschwärzt. An ihrem Aufbau erkannt werden dagegen auch ohne Etikett:
  IBAN (bei eindeutiger Form auch mit falscher Prüfziffer), Steuer-ID und Personalausweis-
  bzw. Passnummer (nur mit gültiger Prüfziffer), Krankenversicherten-, Fahrzeug-Ident- und
  Kreditkartennummern, Steuernummern mit Schrägstrichen, eine BIC in eindeutiger Form sowie
  auf Ausweiskopien die maschinenlesbare Zone (siehe Tabelle).
- **Geburtsdaten ohne Etikett** – erkannt hinter „geb.“, „Geburtsdatum“ … (auch als
  Spaltenkopf) und hinter einem Namen mit Komma, Stern oder Klammer („Max Mustermann,
  02.09.1983“). Ohne ein solches Zeichen („Max Mustermann 02.09.1983“, etwa in einer Tabelle)
  bleibt das Datum in „Ausgewogen“ und „Hoch“ stehen; die Restrisiko-Prüfung meldet es meist
  als Verdacht. „Maximal“ schwärzt zusätzlich Daten wie „02.09.1983“ oder „2. September 1983“
  (nicht „1983-09-02“ oder „02/09/1983“), die mindestens 14 Jahre zurückliegen – außer kurz
  hinter Wörtern wie „am“, „den“, „vom“, „seit“, „bis“, „Beginn“ oder „Datum“, auch als
  Wortende („Er kam am 02.09.1983“, „Anna Linden 02.09.1983“). Das Geburtsdatum eines Kindes
  bleibt ohne Etikett meist stehen, auch in „Maximal“ („Mitversichert: Tochter 14.03.2015“),
  und die Restrisiko-Prüfung meldet es bewusst nicht (sonst wäre jedes jüngere Rechnungs- oder
  Schadendatum ein Verdacht). Bitte selbst darauf achten.
- **Ungewöhnliche Schreibweisen** – seltene oder unbekannte Namen ohne Zusammenhang,
  ausländische Anschriften in ungewohntem Format sowie Text in Bildern, Logos, Handyfotos und
  schlechten Scans können durchrutschen. Die Kundenliste hilft nur für bekannte Kunden – und
  nur, wenn im Dokument ein starkes Merkmal passt.
- **Unlesbarer gespeicherter Text, XFA-Formulare** – Ist der in einer PDF gespeicherte Text
  (die Textebene) unlesbar (Zeichensalat), liest das Programm die Seite per OCR und schwärzt
  über die gelesenen Wörter; der unlesbare Text bleibt aber in der Ausgabe. Inhalte von
  XFA-Formularen (einer besonderen Art ausfüllbarer PDF-Formulare) lassen sich nicht prüfen.
  Beides macht die Ausgabe `_PRUEFEN`.

Kaum lesbare, unplausibel gelesene oder ganz ungelesene Scan-Seiten werden nicht still
übersprungen: Die Ausgabe heißt dann `_PRUEFEN`, und der Grund (z. B. „Seite 2: kein Text
erkannt bzw. Texterkennung fehlgeschlagen“) steht in der Liste und im Abschlussdialog. Meist
umrahmt die Vorschau die ganze Seite als Verdacht – auch einen hellen Scan (blasser Druck,
Bleistift), auf dem die Texterkennung (fast) nichts gelesen hat. Aber nicht immer: Liest die
Texterkennung auf einer Seite mit viel Handschrift nur ein paar gedruckte Wörter (Grund „Scan
kaum lesbar“), kann der Rahmen fehlen. Deshalb jede Seite selbst ansehen.

## Voraussetzungen

- Windows 10 oder 11, **64-Bit (x64)**. 32-Bit-Windows geht nicht (für spaCy gibt es keine
  32-Bit-Pakete). ARM64-Geräte (Snapdragon, Surface Pro X) sind **ungetestet**: Für
  ARM64-Python 3.11 bis 3.15 gibt es inzwischen alle Pakete fertig (PyMuPDF dort 1.28.x),
  `Installieren.bat` versucht die Installation; die EXE-Version läuft unter Windows 11 in der
  x64-Emulation.
- Python 3.10 bis 3.15 – wird vom Installationsskript automatisch mitinstalliert
  (Python 3.12, nur für das eigene Benutzerkonto, keine Administratorrechte nötig).
- Die **Visual-C++-Laufzeit** von Microsoft („Microsoft Visual C++ 2015-2022 Redistributable (x64)“):
  PyMuPDF braucht daraus `msvcp140.dll`. Python bringt `vcruntime140.dll` und `vcruntime140_1.dll`
  selbst mit, `msvcp140.dll` aber nicht – die legt erst dieses Paket in den Windows-Systemordner.
  Auf den meisten Rechnern ist sie schon da; auf frisch eingerichteten Rechnern, in der
  Windows-Sandbox und auf schlanken Firmen-Rechnern fehlt sie oft. `Installieren.bat` prüft das –
  das gefundene Python lädt die Dateien zur Probe so, wie PyMuPDF sie später lädt – und bietet die
  Installation an (`winget install --id Microsoft.VCRedist.2015+.x64 -e`, einmalig, braucht
  Administratorrechte). Ohne winget, oder wer es lieber von Hand macht: `vc_redist.x64.exe` von
  Microsoft (<https://aka.ms/vs/17/release/vc_redist.x64.exe>). Die EXE-Version bringt die Laufzeit mit.
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
   2. Rechner prüfen (64-Bit, Prozessor, Visual-C++-Laufzeit – fehlt sie, bietet das Skript die
      Installation an),
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

Der Programmordner darf auch auf einer Netzwerkfreigabe liegen, die im Explorer über ihren
Pfad (`\\server\freigabe\…`) geöffnet ist: `Installieren.bat` verbindet sie dafür vorübergehend
mit einem freien Laufwerksbuchstaben und gibt ihn am Ende wieder frei; `Starten.bat` arbeitet mit
vollständigen Pfaden.

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
   die blaue Fläche ziehen – oder „Dateien auswählen …“ / „Ordner auswählen …“. Kann das
   Programm Dateien nicht prüfen, meldet die Zeile unter den Knöpfen ihre Anzahl („… werden
   NICHT geprüft – Namen im Protokoll“); Namen und Grund stehen im Protokoll und in den
   Abschlussdialogen – siehe [Welche Dateien gehen?](#welche-dateien-gehen).
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
halbe Ausgabedateien zu hinterlassen. Das gilt auch beim Schließen des Fensters während eines
Laufs: Nach „Lauf läuft noch“ → „Ja“ bricht das Programm den Lauf ab und schließt erst, wenn
seine unfertigen Dateien gelöscht sind (höchstens etwa 20 Sekunden; die Statuszeile sagt, worauf
es wartet). Beim Löschen von Hilfsdateien auf einem nicht erreichbaren Netzlaufwerk (z. B. VPN
getrennt) wartet das Fenster höchstens zwei Sekunden; was dort noch zu löschen ist, löscht das
Programm danach im Hintergrund oder beim nächsten Start. Die Prüfung, ob Ausgaben auf diesem
Laufwerk noch auf die Freigabe warten, kann das Schließen aber verzögern. Nach einem Absturz löscht der nächste
Start, das nächste Hinzufügen oder Schwärzen des Ordners liegen gebliebene Zwischendateien und
meldet sie im Protokoll. Eine Hilfsdatei, die ein anderer Rechner in einen gemeinsam genutzten
Ordner (Netzwerkfreigabe) gelegt hat, löscht es erst, wenn sie älter als 24 Stunden ist – dort
läuft vielleicht noch der Lauf eines Kollegen. Nach dem Schwärzen steht in der Zeile jeder Datei
„✔ fertig“ oder „⚠ prüfen“ mit dem Namen der Ausgabe, der Grund in der Spalte „Kontext“.
Menü Datei → „Protokoll speichern …“ sichert ein Laufprotokoll der Sitzung – ohne
Dokumentinhalte, Original-Dateinamen und Ordner.

Das Programm läuft nur einmal je Benutzer: Ein zweiter Start meldet „PDF-Anonymisierer läuft
bereits“ und öffnet kein zweites Fenster.

### KI-Zweitprüfung mit LM Studio (freiwillig)

Wer [LM Studio](https://lmstudio.ai) auf demselben Rechner nutzt, kann ein lokales Sprachmodell mitlesen lassen:

1. LM Studio starten, ein Modell laden und den lokalen Server einschalten (Reiter „Developer“ → „Start Server“,
   Port 1234).
2. Im Anonymisierer in Schritt 1 „KI-Zweitprüfung mit LM Studio“ anhaken. Daneben steht das geladene Modell: Das
   Programm nutzt immer das Modell, das gerade in LM Studio geladen ist – ein Modellwechsel braucht keine Einstellung.
3. Wie gewohnt analysieren und schwärzen.

Was die KI tut:

- **Zweite Erkennung:** Das Modell liest jede Seite und nennt personenbezogene Daten. Was es eindeutig erkennt und
  was wörtlich im Text steht, wird zusätzlich geschwärzt – nur in angehakten Kategorien. Die Regeln bleiben
  maßgeblich: Die KI nimmt nie eine Schwärzung weg.
- **Weniger, aber genauere Meldungen:** Stellen, die die Selbstkontrolle nur vorsichtshalber meldet („Regen“ – Name
  oder Wetter?), beurteilt das Modell im Zusammenhang. Nur was es sicher als „kein Personenbezug“ einstuft, wird
  nicht mehr gemeldet; das Protokoll nennt diese Stellen. Ganze Seiten (ungelesen, kaum lesbar) bleiben immer
  gemeldet.

Datenschutz: Das Programm verbindet sich nur mit dem eigenen Rechner (127.0.0.1), nie über einen Proxy; eine andere
Adresse lehnt es ab. Kein Text verlässt den Rechner. Dauer: Ein großes Modell braucht je Seite einige Sekunden bis
Minuten (je nach Grafikkarte); Fortschritt und „Abbrechen“ funktionieren wie gewohnt. Läuft LM Studio nicht oder ist
kein Modell geladen, arbeitet das Programm wie ohne KI und sagt das im Protokoll. Für Fachleute: andere Adresse auf
dem eigenen Rechner über die Umgebungsvariable `PDFA_KI_URL`, Einschalten für Werkzeuge mit `PDFA_KI=1`.

### Welche Dateien gehen?

- **PDFs**, auch eingescannte. Ob eine Datei eine PDF ist, prüft das Programm am Inhalt, nicht
  an der Endung.
- **Fotos und Bild-Scans** (JPEG, PNG, TIFF – auch mehrseitige Faxe –, BMP): Nach einer
  Rückfrage wandelt das Programm sie in eine PDF um und liest sie per Texterkennung. Die
  Ausgabe heißt zunächst `anonym_NN_PRUEFEN.pdf` und muss **immer** in der Vorschau
  freigegeben werden. Sie liegt wie bei PDFs im Ordner `anonymisiert` neben dem Foto bzw. im
  gemeinsamen Zielordner.
- **PDFs mit Kennwort:** Das Programm fragt nach dem Kennwort („Überspringen“ ist möglich).
  Das Kennwort wird nicht gespeichert; die Ausgabe hat **kein** Kennwort mehr.
- **Nicht** verarbeitet werden Word-, Excel- und andere Office-Dateien, E-Mails, iPhone-Fotos
  (HEIC), WEBP- und GIF-Bilder – auch nicht, wenn sie die Endung `.pdf` tragen. Solche
  Dateien zuerst als PDF speichern (z. B. Drucken → „Microsoft Print to PDF“). Die Hinweiszeile
  zählt sie als „NICHT geprüft“; mit Grund stehen sie im Protokoll und in den
  Abschlussdialogen.
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
   Verdachtsstellen der Restrisiko-Prüfung. Konnte eine Seite nicht verlässlich gelesen
   werden, ist sie meist ganz umrahmt. Der Rahmen kann aber fehlen, z. B. bei einer Seite mit
   viel Handschrift, auf der die Texterkennung nur ein paar gedruckte Wörter liest; der Grund
   („Scan kaum lesbar“) steht dann nur in der Liste und im Abschlussdialog.
3. **Steht noch etwas Persönliches da und ist es als Verdacht markiert:** in der Liste
   markieren und „Markierte nachschwärzen“. Es entsteht eine neue Ausgabe mit der nächsten
   freien Nummer; die alte wird gelöscht. Das geht nicht bei einer ganz umrahmten Seite (dafür
   kennt das Programm keine genaue Stelle) – dann wie in Schritt 5 vorgehen.
4. **Ist nichts Persönliches mehr zu sehen: „Freigeben“.** Vor dem Freigeben fragt das
   Programm nach, bei offenen Verdachtsstellen mit einer Warnung. Die Datei heißt dann
   `anonym_NN.pdf` (dieselbe Nummer, wenn sie frei ist), die Zuordnungsdatei wird
   nachgetragen, und die Vorschau springt zur nächsten zu prüfenden Datei.
5. **Fehlt eine Schwärzung, die nicht als Verdacht markiert ist** (z. B. eine Unterschrift
   oder eine ganze unlesbare Seite): „Verwerfen (Ausgabe löschen)“ – die Vorschau zeigt dann
   wieder die geplante Schwärzung –, dort per Klick oder Rahmen nachbessern und erneut
   „Schwärzen starten“. Das schwärzt **alle** Dateien der Liste noch einmal, jede unter der
   nächsten freien Nummer. Deshalb vorher die übrigen Ausgaben prüfen und freigeben (oder
   verwerfen) und diese Dateien mit „Datei aus Liste entfernen“ herausnehmen. Sonst entsteht
   für jede eine weitere Ausgabe, und eine alte, noch nicht freigegebene `_PRUEFEN`-Datei lässt
   sich danach nicht mehr freigeben.

**Freigeben geht nur, solange die Datei in dieser Programmsitzung in der Liste steht.** Nach
einem Neustart, nach „Liste leeren“ oder „Datei aus Liste entfernen“ kann das Programm eine
ältere `_PRUEFEN`-Ausgabe nicht mehr freigeben. Dann das Original erneut hinzufügen,
analysieren, schwärzen und die neue Ausgabe prüfen und freigeben; die alte `_PRUEFEN`-Datei
nicht weitergeben. Deshalb vor dem Beenden alle Ausgaben prüfen und freigeben. Stehen beim
Beenden noch Dateien mit nicht freigegebener Ausgabe in der Liste, fragt das Programm nach
(„Freigabe noch offen“, Voreinstellung „Nein“ – das Programm bleibt dann offen). Läuft dabei
gerade eine Analyse oder Schwärzung, nennt die Rückfrage „Lauf läuft noch“ diese Dateien mit –
auch die Ausgaben, die die laufende Schwärzung schon fertig geschrieben hat (Voreinstellung dann
ebenfalls „Nein“). Mit „Nein“ läuft der Lauf weiter; freigeben lässt sich erst nach seinem Ende.

Fotos und Bild-Scans brauchen die Freigabe immer, ebenso Ausgaben mit einem gefundenen, nicht
abgedeckten Lichtbild oder einer erkannten Ausweiskopie ohne Lichtbild (eine nicht erkannte
Ausweiskopie fällt nicht darunter, siehe
[Bilder, Fotos und Lichtbilder](#bilder-fotos-und-lichtbilder)) – auch wenn „Freigabe vor
Weitergabe“ ausgeschaltet ist. Ohne die Option heißt eine Ausgabe sonst nur dann `_PRUEFEN`,
wenn das Programm einen Grund findet (siehe [Ausgabedateien](#ausgabedateien)); geprüft
werden sollte sie trotzdem.

## Ausgabedateien

Die Originale bleiben unverändert. Die einfache Regel lautet: **Hochladen nur aus dem
Ausgabeordner – nie das Original.** Dafür bekommt **jede** lesbare PDF eine bereinigte
Ausgabe, auch eine Datei, in der nichts zu schwärzen war (z. B. ein Bedingungswerk). Neben
jeder Eingabedatei entsteht ein Unterordner `anonymisiert`; mit „Alle Ergebnisse in einen
gemeinsamen Zielordner“ landen die Ausgaben direkt in diesem Ordner. Dort nur die
`anonym_….pdf`-Dateien wählen: Eine `.anonym_tmp_…`-Datei ist unfertig und liegt dort nur,
solange geschwärzt wird (siehe Tabelle).

| Datei | Bedeutung |
|---|---|
| `anonym_01.pdf`, `anonym_02.pdf`, … | Freigegebene bzw. fertige Ausgaben. Die Namen sind absichtlich neutral – der Original-Dateiname (oft ein Kundenname!) soll nicht mit zur KI wandern. Bestehende Dateien werden nie überschrieben, es wird immer die nächste freie Nummer genommen. |
| `anonym_03_PRUEFEN.pdf` | Diese Ausgabe ist noch **nicht** zur Weitergabe freigegeben. Mit „Freigabe vor Weitergabe“ (Standard) heißt zunächst jede Ausgabe so; bei einer Datei ohne Fund steht dann „keine personenbezogenen Daten gefunden – Freigabe ausstehend“. Dazu kommen die Gründe unten. Erst in der Vorschau prüfen, ggf. nachschwärzen und dort „Freigeben“ drücken. |
| `.anonym_tmp_….tmp` | Unfertige Hilfsdatei, solange eine Ausgabe geprüft und abgelegt wird – **nie weitergeben**. Sie verschwindet mit dem Ende des Laufs, auch beim Abbrechen und beim Schließen des Fensters; nach einem Absturz löscht das Programm sie beim nächsten Start, Hinzufügen oder Schwärzen dieses Ordners. Ihr Name enthält eine Kennung des Rechners (ein kurzer Hash des Rechnernamens): Die Hilfsdatei eines anderen Rechners – etwa eines Kollegen, der in denselben Ordner einer Netzwerkfreigabe schwärzt – löscht das Programm erst, wenn sie älter als 24 Stunden ist. |

Außerdem heißt eine Ausgabe immer `_PRUEFEN`, wenn mindestens einer dieser Gründe zutrifft
(der Grund steht in der Liste neben der Datei und im Abschlussdialog):

- Die Restrisiko-Prüfung meldet Verdacht oder ist ausgefallen, die Selbstkontrolle findet
  noch Fundtext, oder ein angehakter Fund war im Dokument nicht auffindbar.
- Die Datei ist ein umgewandeltes Foto oder ein Bild-Scan, ein gefundenes Lichtbild ist nicht
  abgedeckt, oder auf einer erkannten Ausweiskopie wurde kein Lichtbild gefunden.
- Eine Scan-Seite ist kaum lesbar, die Texterkennung hat Buchstabensalat gelesen oder auf einer
  Seite, die nicht nachweislich leer ist, nichts gelesen – oder es ist gar kein Text lesbar.
- Der in der PDF gespeicherte Text (Textebene) ist unlesbar, das Dokument ist ein
  XFA-Formular, oder eine Seite ist gedreht gespeichert und die Lage der Schwärzungen unsicher.
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

**Keine Ausgabe** bekommen nur Dateien, die das Programm nicht übernimmt oder nicht bearbeiten
kann. Der Abschlussdialog nennt sie in zwei Blöcken:

- **„NICHT geprüft“** – Dateien, die gar nicht erst in die Liste kommen: keine PDF (z. B. eine
  Word-Datei), Kennwort nicht eingegeben, Foto nicht übernommen, nicht lesbar …
- **„OHNE Ausgabedatei“** – Dateien aus der Liste, für die keine Ausgabe entstand: Datei lässt
  sich nicht öffnen, Abbruch, eine Seite lässt sich weder schwärzen noch als Bild neu erzeugen,
  die Datei musste erst beim Schwärzen repariert werden, oder die Ausgabe ist nicht
  schreibbar.

In beiden Fällen das Original nicht weitergeben.

Was jede Ausgabe sonst noch auszeichnet:

- Formularfelder und Anmerkungen werden vor der Analyse in den Seiteninhalt eingebrannt
  (damit auch Feldinhalte geprüft werden).
- Versteckte Teile werden entfernt – etwa Dateieigenschaften, Lesezeichen, Links, Anhänge,
  Formulardaten, Skripte, Miniaturbilder, Inhalte außerhalb des sichtbaren Bereichs und die
  Aufnahmedaten eingebetteter Fotos (vollständige Liste unter [Technik](#technik)).
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
beim nächsten Schwärzen übernommen und dort gelöscht. Nur wenn nirgends daneben geschrieben
werden kann (z. B. schreibgeschützter Ordner), landet sie als `_zuordnung.txt` im
Ausgabeordner – dann warnt das Programm deutlich („ACHTUNG Zuordnungsdatei“), sie beim
Hochladen nicht mit auszuwählen.

## Wo das Programm Dateien ablegt

| Was | Wo |
|---|---|
| Ausgaben | Unterordner `anonymisiert` neben dem Original (bzw. direkt im gemeinsamen Zielordner): `anonym_NN.pdf` oder `anonym_NN_PRUEFEN.pdf`; solange eine Ausgabe geprüft und abgelegt wird, eine Hilfsdatei `.anonym_tmp_….tmp` (nie weitergeben, siehe [Ausgabedateien](#ausgabedateien)) |
| Zwischenstände beim Schwärzen großer Scans (nur teilweise geschwärzt) und, solange geschwärzt wird, ein Vermerk der Ausgabeordner (für das Aufräumen nach einem Absturz; nach dem Beenden nur, wenn in einem Ausgabeordner noch etwas zu löschen blieb, z. B. weil er nicht erreichbar war) | `%LOCALAPPDATA%\PDF-Anonymisierer\temp\sitzung_…` – nie im Ausgabeordner; gelöscht am Ende des Laufs, beim Beenden bzw. nach einem Absturz beim nächsten Start |
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
Tesseract** – nur den entpackten Ordner. Auch die Visual-C++-Laufzeit liegt darin
(`_internal\msvcp140.dll`, `_internal\vcruntime140_1.dll`); `EXE-bauen.bat` prüft das nach dem Bau.

- Den Bau macht ein Rechner, auf dem `Installieren.bat` gelaufen ist (x64-Windows).
  Das Skript prüft vorher, dass Sprachmodell und Sprachdatei vorhanden sind – eine EXE
  ohne Namenserkennung wird nicht gebaut. Fehlt nur PyInstaller, wird nur das nachgeladen
  (`requirements-dev.txt`), nicht erneut das Sprachmodell.
- Alternativ baut die GitHub-Action die EXE mit genau diesem Skript: unter „Actions“ →
  „Tests“ → „Run workflow“ oder automatisch für jeden Pull Request und jeden Versions-Tag `v…`.
  Die ZIP liegt dann als Artefakt beim Lauf (vorher geprüft: Sprachmodell, Sprachdatei,
  Lizenztexte, Probestart).
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
| `Installieren.bat` meldet „Die Visual-C++-Laufzeit von Microsoft fehlt“; beim Start erscheint „PyMuPDF lässt sich nicht laden“ oder oben steht „DLL load failed“ | Auf dem Rechner fehlt die Laufzeit, die PyMuPDF braucht („Microsoft Visual C++ 2015-2022 Redistributable (x64)“, vor allem `msvcp140.dll` – `vcruntime140.dll` und `vcruntime140_1.dll` bringt Python selbst mit), oder sie ist veraltet – typisch für frisch eingerichtete Rechner, die Windows-Sandbox und schlanke Firmen-Rechner. Pakete neu zu installieren hilft dann nicht. Einmalig mit Administratorrechten installieren: `winget install --id Microsoft.VCRedist.2015+.x64 -e` (bietet `Installieren.bat` selbst an) oder `vc_redist.x64.exe` von Microsoft (<https://aka.ms/vs/17/release/vc_redist.x64.exe>), danach `Installieren.bat` erneut starten. Ohne Administratorrechte: die IT fragen oder die EXE-Version nutzen – sie bringt die Laufzeit mit. `python werkzeuge\pruefe_installation.py` zeigt unter „Visual C++“, ob dieses Python die Dateien laden kann und aus welchem Ordner; scheitern statt PyMuPDF andere Pakete (spaCy, tkinter) an einer DLL, nennt es die passende Abhilfe. |
| `Installieren.bat` meldet „Der Programmordner lässt sich nicht als Arbeitsordner öffnen“ | Der Ordner liegt auf einer Netzwerkfreigabe (`\\server\freigabe\…`), und Windows konnte ihr keinen freien Laufwerksbuchstaben zuordnen oder hat den Zugriff verweigert (die Meldung von Windows steht darüber). Den Ordner auf den eigenen Rechner kopieren (z. B. nach `Dokumente`) oder die Freigabe als Netzlaufwerk verbinden (Explorer: Dieser PC → „Netzlaufwerk verbinden“) und von dort starten. |
| „Python konnte nicht automatisch installiert werden“ | `winget` fehlt oder ist gesperrt, oder `python` ist nur der Store-Alias von Windows. Python 3.12 (64-Bit) von [python.org](https://www.python.org/downloads/windows/) installieren (Haken „Add python.exe to PATH“), dann `Installieren.bat` erneut starten. Den Store-Alias schaltet man unter Einstellungen → Apps → Erweiterte App-Einstellungen → „Aliase für die App-Ausführung“ aus. |
| Keine Desktop-Verknüpfung, obwohl alles andere lief | Die Ursache steht im Fenster in der Zeile „FEHLER:“ – meist ist PowerShell durch Firmenrichtlinien eingeschränkt, seltener fehlt der Desktop-Ordner oder ist nicht beschreibbar. Programm über `Starten.bat` starten (Rechtsklick → „Senden an“ → „Desktop (Verknüpfung erstellen)“). Ein schreibgeschützter Programmordner (z. B. Netzlaufwerk nur mit Leserecht) verhindert die Verknüpfung nicht: Dann fehlt nur `.python_pfad.txt` (Hinweis im Fenster), und `Starten.bat` sucht Python in den üblichen Installationsordnern. |
| Doppelklick auf die Verknüpfung – nichts passiert | Ordner verschoben oder Python aktualisiert. `Installieren.bat` erneut ausführen, oder `Starten.bat` benutzen. Steht in `fehler.log` etwas? (siehe unten) |
| Meldung „PDF-Anonymisierer läuft bereits“ | Das Programm ist schon geöffnet (Taskleiste). Es läuft bewusst nur einmal je Benutzer, damit sich Einstellungen und Ausgabenummern nicht gegenseitig überschreiben. |
| Protokoll meldet „Namenserkennung inaktiv“ oder „Namenserkennung konnte nicht geladen werden“ | Sprachmodell fehlt oder ist beschädigt; Ausgaben heißen dann immer `_PRUEFEN`. Skript-Version: `Installieren.bat` erneut ausführen. EXE-Version: den kompletten Programmordner neu entpacken bzw. eine neue ZIP anfordern – der Ordner `_internal` gehört dazu. |
| Meldung „Erkennungsmodul … fehlt in diesem Programmordner“ | Der Programmordner ist unvollständig; die Angaben dieses Moduls wurden nicht gesucht, die Ausgaben heißen `_PRUEFEN`. Skript-Version: die ZIP neu herunterladen und entpacken, dann `Installieren.bat`. EXE-Version: den Ordner vollständig neu entpacken. |
| OCR liest Scans auf Englisch / Umlaute falsch | Die deutsche Sprachdatei fehlt: in der Skript-Version `tessdata\deu.traineddata` im Programmordner, in der EXE-Version `_internal\tessdata\deu.traineddata`. Den Ordner vollständig (neu) entpacken. Das Programm nimmt immer zuerst diese mitgelieferte Datei; eine andere Tesseract-Installation auf dem Rechner (Umgebungsvariable `TESSDATA_PREFIX`) dient nur als Ersatz, wenn sie fehlt. Die Warnung nennt den Ordner, aus dem die OCR tatsächlich liest; `python werkzeuge\pruefe_installation.py` zeigt ihn unter „OCR liest mit“. |
| Datei wird als „keine PDF“ / „NICHT geprüft“ gemeldet | Das Programm prüft am Inhalt: Word, Excel, Mails, HEIC-, WEBP- und GIF-Bilder werden nicht verarbeitet – auch mit der Endung `.pdf`. Im Ursprungsprogramm als PDF speichern (z. B. Drucken → „Microsoft Print to PDF“) und diese PDF hinzufügen. |
| Fast jede Ausgabe heißt `_PRUEFEN` | So gewollt: „Freigabe vor Weitergabe erforderlich“ ist eingeschaltet (Standard). In der Vorschau prüfen und „Freigeben“ drücken. Ohne die Option heißt eine Ausgabe nur bei einem konkreten Grund `_PRUEFEN` (Fotos immer). |
| Eine `_PRUEFEN`-Datei lässt sich nicht (mehr) freigeben | Freigeben geht nur in der Sitzung, in der geschwärzt wurde, solange die Datei in der Liste steht. Original erneut hinzufügen, analysieren, schwärzen, prüfen und freigeben; die alte `_PRUEFEN`-Datei nicht weitergeben. |
| Zuordnungsdatei liegt nicht im Ausgabeordner | Sie liegt neben dem Ausgabeordner (`_zuordnung_anonymisiert.txt`), bei einem Laufwerk als Zielordner in `%APPDATA%\PDF-Anonymisierer\Zuordnungen` – siehe [Ausgabedateien](#ausgabedateien). |
| Geschwärztes Foto ist kleiner als das Original | Geschwärzte Bilder werden neu als JPEG gespeichert, Fotos über 24 Megapixel dabei auf 24 Megapixel verkleinert. |
| Fenster zu groß für den Bildschirm | Das Fenster passt sich dem Bildschirm an und startet auf kleinen Bildschirmen (z. B. Laptops mit 1366 × 768) und bei hoher Windows-Skalierung maximiert. Wird es eng, blendet das Programm Überschriften und Bedienhinweise aus und rückt zusammen; die Zeile mit den NICHT geprüften Dateien bleibt sichtbar. Alle Hinweise stehen weiter unter Hilfe → „Was wird nicht erkannt?“ und „Hinweise vor der Nutzung …“. |
| `fehler.log` finden | Skript-Version: neben `pdf_anonymisierer.py`, wenn der Ordner beschreibbar ist, sonst `%LOCALAPPDATA%\PDF-Anonymisierer\fehler.log`. EXE-Version: immer `%LOCALAPPDATA%\PDF-Anonymisierer\fehler.log`, nie neben der EXE. Hilfe → „Ordner des Fehlerprotokolls öffnen“ öffnet den Ordner; der Fehlerdialog und Hilfe → „Über PDF-Anonymisierer“ nennen den genauen Pfad. Ordner sind darin gekürzt, Dateinamen nicht. |
| Für Rückfragen | Skript-Version: `python werkzeuge\pruefe_installation.py` im Programmordner ausführen und die Ausgabe mitschicken (Python-Version, Visual-C++-Laufzeit, Pakete und ob ihre Versionen zu `requirements.txt` passen, Sprachdatei und mit welcher Sprache aus welchem Ordner die OCR liest, Log-Pfad). EXE-Version: den Text aus Hilfe → „Über PDF-Anonymisierer“ und die `fehler.log` mitschicken. Hilfreich ist auch das Laufprotokoll (Datei → „Protokoll speichern …“) – es enthält keine Dokumentinhalte und keine Original-Dateinamen. |

## Technik

- **Python 3.10–3.15**, Oberfläche mit tkinter (+ tkinterdnd2 für Drag & Drop). Mit Python
  3.11 bis 3.14 kommt PyMuPDF 2.x, mit 3.10 und 3.15 PyMuPDF 1.28.x; verlangt wird mindestens
  PyMuPDF 1.24.10. Die GitHub-Action testet mit Python 3.12, also mit PyMuPDF 2.x.
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
  Diagnosen, Medikamenten, Etiketten, Versicherern und Organisationen, Orten; Quellen in
  `daten/QUELLEN.md`). Feste Pseudonyme je Person; Varianten und Namensbestandteile werden
  zusammengeführt. Prüfziffern (IBAN Mod 97, Steuer-ID nach § 139b AO, ICAO bei Ausweisen …)
  bestimmen meist nur die Sicherheit eines Funds; ohne Etikett verlangen Steuer-ID und
  Ausweisnummer eine gültige Prüfziffer. Ganzwort-Prüfung bei der Schwärzung: Ein Fund darf
  nicht Teil eines längeren Wortes sein.
- **Zwei Kontrollen nach dem Schwärzen:** Die Selbstkontrolle sucht die geschwärzten Texte in
  der Ausgabe (bei Scans per erneuter OCR). Die Restrisiko-Prüfung (`restrisiko.py`) liest die
  Ausgabe als unabhängige zweite Linie mit eigenen Regeln – ohne die Erkennungsregeln und ohne
  das Sprachmodell – und meldet, was nach Personendaten aussieht. Gemeinsam mit der
  Erkennung nutzt sie nur die Regel „Etikett + Wert“ für jedes Kennungs-Etikett, die
  Kennungsformen ohne Etikett und die USt-IdNr. von Einzelkaufleuten (`kennungsformen.py`)
  sowie die Personenregeln für Geburtsdaten im Familienkontext, Nachbarschaftsangaben, die
  Zulassungsbescheinigung und GbR-Namen (`personenkontext.py`), damit beide dieselben
  Schreibweisen kennen. Eine zentrale
  Statusregel (`analyse.WARNUNGS_CODES`, `analyse.ist_leckrelevant`) entscheidet für jede
  Meldung, ob die Ausgabe `_PRUEFEN` heißt.
- **Bilder:** `fotos.py` (Fotobereiche und Lichtbilder), `bilder.py` (Neukodierung,
  Bildreste), `nebenkanaele.py` (versteckte Teile lesen und entfernen).
- **Versteckte Teile**, die jede Ausgabe verliert: Dateieigenschaften und XMP-Metadaten (auch
  an Seiten und Bildern), Lesezeichen, Links, eingebettete Dateien und Anhänge, Formular- und
  XFA-Daten, JavaScript und Aktionen, Seitenbeschriftungen, Strukturbaum und Ersatztexte
  (`/ActualText`, `/Alt`), Ebenennamen, Miniaturbilder, Inhalte außerhalb des sichtbaren
  Bereichs, abgeschnittener Text sowie EXIF-/XMP-Daten in eingebetteten Fotos.
- **Kundenliste** (`kundenliste.py`): gespeichert werden nur gesalzene SHA-256-Prüfwerte
  normalisierter Werte; das Salz ist unter Windows mit DPAPI geschützt (nur dieses
  Windows-Konto kann es entschlüsseln).
- **Kleine Bildschirme** (`gui.py`): Unter 760 Pixel Fensterhöhe (bei 100 %) entfallen Titel,
  Untertitel und Bedienhinweis, das Protokoll zeigt 3 statt 5 Zeilen. Reicht der Platz für die
  Fundliste dann noch nicht, greifen der Reihe nach und nur so weit wie nötig die Kompaktstufen
  (`KOMPAKT_STUFEN`): Titel „1 · PDF-Dateien“ und Ablagefläche in einer Zeile (nur, wenn beide
  nebeneinander passen), flachere Knöpfe, zuletzt eine Kurzfassung des Hinweiskastens –
  höchstens zwei Zeilen mit den Kernaussagen; ein Klick zeigt alle Grenzen.
- Code und Oberfläche sind deutsch. Paketaufbau `anonymisierer/`: `analyse.py`,
  `schwaerzung.py`, `seitenmodell.py`, `detektoren/`, `muster.py` (Kategorien, Muster,
  Schutzstufen), `kennungsformen.py`, `personenkontext.py`, `namen.py` (spaCy), `wissen.py` +
  `daten/`, `kundenliste.py`, `ki.py` (KI-Zweitprüfung über LM Studio, nur auf diesem Rechner),
  `restrisiko.py`, `ocr.py`, `kammraster.py` (Kästchenfelder auf Scans), `fotos.py`, `bilder.py`,
  `nebenkanaele.py`, `vorschau.py`,
  `vorschau_fenster.py`, `gui.py`, `gui_attrappen.py`, `auftrag.py` (welche Funde und Stellen
  die Oberfläche an die Schwärzung gibt), `dateien.py`; Startskript `pdf_anonymisierer.py`.
- Kommentare im Code verweisen teils auf interne Entwicklerunterlagen („Vertrag Abschnitt …“,
  `CONTRACT_V2.md`, `BENCHMARK_SCHEMA.md`), die nicht im Repository liegen.

## Mitentwickeln und Tests

```bash
python -m pip install --only-binary=:all: -r requirements.txt -r requirements-dev.txt pyyaml pillow
python -m pytest -q --timeout=300 tests/
```

`pyyaml` und `Pillow` brauchen nur die Tests (Prüfung der GitHub-Action, Scans mit Schräglage) und die
Domänen-Probe. Sie stehen bewusst nicht in `requirements-dev.txt`, weil der EXE-Bau diese Datei installiert und
PyInstaller Pillow sonst mit in die EXE packen würde.

Unter Linux brauchen die Oberflächentests ein Display (z. B. `xvfb-run -a python -m pytest …`);
die Layout-Tests starten für die geprüften Bildschirmgrößen bei Bedarf eigene Xvfb-Displays
(Paket `xvfb`). Die OCR findet die Sprachdatei im Ordner `tessdata` selbst. Die GitHub-Action
`.github/workflows/tests.yml` führt die Tests auf Ubuntu und Windows aus (Zeitgrenze 300 s je
Test, dafür `pytest-timeout` aus `requirements-dev.txt`), sichert Layout-Screenshots und den
Bericht des Benchmark-Tests als Artefakte und baut danach – für jeden Pull Request, auf Wunsch
und für Versions-Tags `v…` – die Windows-EXE mit `EXE-bauen.bat` samt Probestart (die ZIP liegt
als Artefakt beim Lauf).

Werkzeuge in `werkzeuge/`:

- `pruefe_installation.py` – zeigt für Rückfragen Python, Pakete, Sprachdatei und Log-Pfad.
- `selbsttest.py` – Selbsttest mit eigenen, echten Dokumenten: analysiert und schwärzt einen
  Ordner und gibt **nur Zählwerte** aus (keine Namen, Nummern, Datei- oder Ordnernamen).
  Geschwärzt wird, was die Fundliste nach der Analyse angehakt hat – aber nicht ganz wie in der
  Oberfläche: jedes Dokument für sich (ohne Weitergabe im Lauf und ohne Kundenliste, NIE- und
  IMMER-Liste nur mit `--einstellungen`), ohne „Freigabe vor Weitergabe“ (`_PRUEFEN` zählt nur
  Ausgaben mit einem Grund), und ganz abgewählte Funde (z. B. „vermutlich Firmenanschrift“)
  gehen mit an die Schwärzung, sodass die Restrisiko-Prüfung sie nicht meldet. Die Ausgaben
  liegen in einem temporären Ordner und werden danach gelöscht, außer mit `--behalten <ordner>`.
  Aufruf (Schutzstufe wahlweise `ausgewogen`, `hoch` oder `maximal`):
  `python werkzeuge/selbsttest.py <ordner> --profil hoch`.
- `readme_tabelle.py` – erzeugt die Erkennungstabelle dieser README
  (`python werkzeuge/readme_tabelle.py --schreiben`); Beispiele und Hinweise stehen im
  Werkzeug, `tests/test_auslieferung.py` vergleicht die Tabelle mit seiner Ausgabe.
- `benchmark.py` mit dem Paket `benchmark/` – Entwicklungs-Benchmark: erzeugt Testdokumente
  mit bekannter Wahrheit und bewertet die Ausgaben; `tests/test_benchmark.py` nutzt ihn als
  Qualitätstor.
- `domaenenprobe/` – Domänen-Probe: 41 Falldateien mit synthetischen Fällen aus allen
  Maklersparten (2261 frei erfundene geheime Werte auf Textebene und Scans) laufen Ende zu Ende
  wie in der Oberfläche; gezählt wird je Wert, ob er danach noch lesbar ist (weg, sichtbar mit
  `_PRUEFEN`, STILL), verglichen mit `referenz.json`. Eine Regressionsprobe für die Entwicklung,
  keine Blindprüfung: Die Regeln wurden an genau diesen Fällen verbessert, die Zahlen sagen nichts
  über unbekannte Dokumente. Aufruf: `python werkzeuge/domaenenprobe/messen.py <ordner>` (braucht
  die Tesseract-Kommandozeile); Einzelheiten in `werkzeuge/domaenenprobe/README.md`. Die
  GitHub-Action misst sie nur von Hand („Run workflow“ mit Haken „domaenenprobe“, Bericht als
  Artefakt); `tests/test_domaenenprobe.py` prüft Falldateien und Referenz und lässt einen kleinen
  Fall Ende zu Ende laufen.
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
