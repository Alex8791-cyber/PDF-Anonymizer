# Wissensbasis: Herkunft, Aufbau und Pflege

Dieser Ordner enthält die Wortlisten, die `anonymisierer/wissen.py` lädt. Sie gehören zum
PDF-Anonymisierer und stehen wie der übrige Code unter der **MIT-Lizenz** (siehe `LICENSE`,
© 2026 Alex8791-cyber und Mitwirkende). Weitergabe und Änderung sind unter den Bedingungen
der MIT-Lizenz frei; für die Listen gelten keine zusätzlichen Bedingungen Dritter.

## Herkunft

- **Eigenständig zusammengestellt.** Die Einträge wurden 2026 für dieses Projekt aus
  allgemeinem Wissen über die deutsche Sprache, die Namensgebung der Menschen in Deutschland,
  Österreich und der Schweiz, die Berufswelt, die Medizin und den Versicherungsmarkt
  zusammengetragen – mit Unterstützung eines KI-Assistenten (Claude, Anthropic) und danach
  maschinell und von Hand geprüft (siehe „Qualitätssicherung“).
- **Nichts aus geschützten Sammlungen übernommen.** Keine Liste wurde aus einem
  urheberrechtlich oder als Datenbank geschützten Verzeichnis kopiert oder ausgezogen, weder
  ganz noch auszugsweise. Insbesondere stammen die Listen nicht aus Namensdatenbanken oder
  Telefonverzeichnissen, nicht aus Wörterbüchern, nicht aus amtlichen Katalogtexten
  (ICD-10-GM, OPS, KldB 2010, BERUFENET), nicht aus Arzneimittelverzeichnissen (Rote Liste,
  Gelbe Liste, ABDA-Datenbank) und nicht aus Unternehmensverzeichnissen (BaFin, GDV,
  Handelsregister).
- **Fakten sind frei.** Einzelne Vor- und Familiennamen, Wörter, Berufsbezeichnungen,
  Krankheits-, Wirkstoff- und Firmennamen sind Tatsachen bzw. Allgemeingut der Sprache und
  als solche nicht urheberrechtlich geschützt. Schutz kann allenfalls an Auswahl und
  Anordnung einer bestimmten Sammlung bestehen (§ 4 und §§ 87a ff. UrhG); Auswahl, Gliederung
  und Anordnung dieser Listen sind eigene Arbeit.
- **Marken.** Arzneimittel-Handelsnamen sowie Namen von Versicherern, Banken und Produkten
  sind Kennzeichen ihrer Inhaber. Sie stehen hier nur als Suchwörter (zum Schwärzen bzw. zum
  bewussten Nicht-Schwärzen) und drücken keine Verbindung zu den Inhabern aus.

### Hilfsmittel: Vokabular der spaCy-Wortvektoren (CC0)

Zur Prüfung – nicht als Vorlage für Namen, Berufe, Diagnosen oder Organisationen – diente
das Vokabular der Wortvektoren im spaCy-Modell `de_core_news_md` 3.8.0, das der
Anonymisierer ohnehin mitbringt: 500 000 Wortformen der „Explosion fastText Vectors (cbow,
OSCAR Common Crawl + Wikipedia)“, Lizenz **CC0** (das Modell selbst: MIT). Verwendet wurden
nur die Wortformen, weder Vektoren noch Trainingsdaten des Modells (TIGER, WikiNER):

1. **Belegprüfung:** Kommt jedes Wort eines Eintrags (ab drei Buchstaben) im Vokabular vor?
   Nicht belegte deutsche Namen und Allerweltswörter wurden einzeln gesichtet, zweifelhafte
   gestrichen; bei den übrigen Listen wurde stichprobenartig gesichtet (Quoten siehe unten).
2. **Kollisionssuche:** Namen, deren Vergleichsform mit einem häufigen deutschen Wort
   zusammenfällt (Klein, Wolf, Mai, Ernst …), wurden in die `*_mehrdeutig`-Listen
   aufgenommen.
3. **Kandidatenquelle für Allerweltswörter:** 3 445 der Rohkandidaten von
   `allerweltswoerter_gross.txt` sind großgeschriebene Komposita aus diesem Vokabular, deren
   letztes Glied ein typisches Kopfwort aus Versicherungs-, Rechts- und Verwaltungsschreiben
   ist (-versicherung, -vertrag, -antrag, -bescheid, -leistung, -kosten …). Jeder Kandidat
   wurde durchgesehen; verworfen wurden Eigennamen, Marken, Orte, Personennamen, Verben,
   Adjektive, Gesundheitsbegriffe und Wörter aus Werbe- und Glücksspieltexten.

### Regelbasiert erzeugte Formen

Die Listen sind das Original und werden direkt gepflegt; die folgenden Formen wurden beim
ersten Aufbau nach festen Regeln erzeugt und stehen ausgeschrieben in den Dateien:

- **Berufe:** aus rund 1 550 Rohzeilen; zu jeder männlichen Grundform die weibliche Form
  nach Regeln (Kopfwort vor „für“, „im“, „in“ … umformen; -mann → -frau; Arzt/Anwalt/Koch
  mit Umlaut; -e → -in; substantivierte Adjektive Angestellter → Angestellte; vorangestellte
  Adjektive -er → -e; „Maler und Lackierer“ → „Malerin und Lackiererin“). Unregelmäßige
  Paare und neutrale Formen wurden von Hand angegeben (Beamter/Beamtin, Hausmann/Hausfrau,
  Fußballprofi, selbstständig).
- **Etiketten für Kennungen:** zu 71 Stämmen die Schreibweisen „Stammnummer“,
  „Stamm-Nummer“, „Stamm-Nr.“, „Stamm Nr.“ und „Stammnr.“ (Vertragsnummer, Vertrags-Nr. …).
- **Etiketten für Personen:** zu Rollenwörtern mit „(in)“ die Formen „Fahrer“, „Fahrerin“,
  „Fahrer/in“, „Fahrer(in)“, „Fahrer/-in“.
- **Familiennamen:** 265 weibliche Formen ostslawischer und bulgarischer Namen
  (-ow → -owa, -ev → -eva, -in → -ina, -skij → -skaja …); polnische, tschechische,
  slowakische und griechische Namen stehen von Hand in beiden Formen, unveränderliche
  ukrainische Namen nur einmal.

## Inhalt

| Datei | Einträge | Inhalt | Belegt¹ |
|---|---:|---|---:|
| `vornamen.txt` | 6 205 | Vornamen aller in Deutschland, Österreich und der Schweiz verbreiteten Herkünfte (Rohzahlen je Gruppe²: deutsch/österreichisch/schweizerisch 1 341, Ost- und Südosteuropa 1 350, West-, Süd- und Nordeuropa, englischsprachige Länder, hebräisch 1 136, arabisch/persisch/afghanisch/somalisch/eritreisch/äthiopisch/westafrikanisch 1 130, Ost- und Südasien 765, türkisch/kurdisch 526, Kurzformen, international verbreitete Namen, Kaukasus, Zentralasien, Südostasien, Lateinamerika, Roma und Sinti 410); Kurz- und Doppelformen, Diakritika erhalten | 68,3 % |
| `vornamen_mehrdeutig.txt` | 64 | Vornamen, die zugleich gewöhnliche Wörter sind (Rosa, Ernst, Frank, Mai, Kai, An) | 100 % |
| `nachnamen.txt` | 8 552 | Familiennamen derselben Herkunftsbreite (Rohzahlen je Gruppe²: deutsch einschließlich regionaler Formen und Schreibvarianten wie Meyer/Maier/Mayer/Meier 2 787, Österreich und Schweiz 535, Ost- und Südosteuropa 1 725, West-, Süd- und Nordeuropa 1 175, Türkei, Kurdistan, arabische Länder, Iran, Afghanistan 722, Asien, Kaukasus und Afrika 866, Ergänzungen verschiedener Herkunft 913, Kerne von Partikelnamen 63) | 68,0 % |
| `partikel.txt` | 107 | Namenspartikel und Adelsbestandteile (von, van der, de la, al-, bin, ibn, Freiherr von) | 100 % |
| `nachnamen_mehrdeutig.txt` | 568 | Familiennamen, die zugleich Wörter, Orts- oder Firmennamen sind (Klein, Wolf, Koch, Winter, Hagen, Nürnberger); jeder Eintrag steht auch in `nachnamen.txt` | 100 % |
| `berufe.txt` | 2 959 | Berufe und berufliche Stellung, männlich und weiblich (Zahnarzt/Zahnärztin, Polier/Polierin, Beamter/Beamtin, Rentner/Rentnerin, Auszubildende/Auszubildender, Student/Studentin, Hausfrau/Hausmann, selbstständig) | 65,2 % |
| `diagnosen.txt` | 2 014 | Diagnosen, Krankheits- und Zustandsbezeichnungen, Verletzungen, Eingriffe, Behandlungs- und Pflegestatus (Gesundheitsdaten nach Art. 9 DSGVO) | 73,6 % |
| `medikamente.txt` | 1 508 | 750 Wirkstoffe und 758 in Deutschland gebräuchliche Handelsnamen | 28,1 % |
| `versicherer_und_organisationen.txt` | 1 343 | **Erlaubnisliste**: Versicherer, Pools, Maklerverbünde, Behörden, Sozialversicherungsträger, Krankenkassen, Banken, Verbände, Produkt-, Tarif- und Rechtsbegriffe | 88,2 % |
| `etiketten_person.txt` | 620 | Feldbezeichner und Rollenwörter vor Personen (Versicherungsnehmer, Name, Zeuge) | 92,3 % |
| `etiketten_kennung.txt` | 582 | Feldbezeichner vor Kennungen (Vertrags-, Kunden-, Schadennummer, Aktenzeichen, Steuer-ID, Kennzeichen) | 66,5 % |
| `etiketten_datum_geburt.txt` | 64 | Feldbezeichner für Geburts-, Sterbe- und Heiratsdaten | 95,3 % |
| `etiketten_adresse.txt` | 128 | Feldbezeichner vor Anschriften und Orten einer Person | 85,2 % |
| `etiketten_kontakt.txt` | 82 | Feldbezeichner für Telefon, Fax, E-Mail, Messenger, Profile | 96,3 % |
| `etiketten_vertragsdaten.txt` | 213 | Feldbezeichner für Vertrags- und Vorgangsdaten (Beginn, Ablauf, Stand): ein Datum dahinter ist kein Geburtsdatum | 84,0 % |
| `allerweltswoerter_gross.txt` | 9 296 | Großgeschriebene Wörter aus Versicherungs-, Rechts-, Medizin- und Verwaltungsschreiben, die eine Namenserkennung leicht für Personen hält; enthält **keine** Vor- und Nachnamen, Berufe, Diagnosen und Medikamente (maschinell geprüft) | 92,0 % |
| `anreden_titel.txt` | 303 | Anreden, Grußformeln, akademische, berufliche und Adelstitel, Rollenkürzel (Herr, Frau, Dr. med., Prof., Dipl.-Ing., RA, i. A., gez.) | 93,4 % |

¹ Anteil der Einträge, deren Wörter (ab drei Buchstaben) alle im CC0-Vokabular vorkommen.
Eine niedrige Quote heißt nicht „falsch“: lange Komposita, Abkürzungen, Handelsnamen und
seltene Umschriften fremdsprachiger Namen fehlen in einem allgemeinen Vokabular naturgemäß.
Für die deutschen, österreichischen und schweizerischen Familiennamen liegt die Quote bei
97,7 % (3 120 Rohnamen), für die deutschen, österreichischen und schweizerischen Vornamen
bei 98,4 % (1 341 Rohnamen).

² Gezählt vor dem Zusammenführen der Gruppen; Namen, die in mehreren Gruppen vorkommen
(Anna, Martin, Bauer), stehen in der Datei nur einmal.

## Vergleichsregeln (kurz)

Alle Prüf- und Suchfunktionen in `wissen.py` vergleichen in einer Vergleichsform:
Groß-/Kleinschreibung und Diakritika sind egal („Çelik“ = „Celik“), ä/ö/ü passen auch auf
ae/oe/ue, ß auf ss. Verglichen werden ganze Wörter; Leerraum, Bindestrich und Punkt zwischen
Wörtern sind gleichwertig, andere Zeichen (+ & / ' ,) müssen übereinstimmen. Deshalb gehören
Schreibweisen, die sich nur darin unterscheiden, **nicht** zusätzlich in die Listen.
Abweichende Umschriften (Mohammed/Muhammad, Jurij/Yuriy) dagegen schon.

Namen mit festem Partikel stehen vollständig in `nachnamen.txt` („de Vries“, „van der
Meer“, „Al-Hassan“). Ihr Kern steht zusätzlich als eigener Eintrag („Vries“ für die
Listenform „Vries, Jan de“, „Bayati“ ohne Artikel), außer er ist zugleich Vorname oder
Allerweltswort („Marco“ aus „De Marco“, „Meer“ aus „van der Meer“); das Pflegewerkzeug
meldet fehlende Kerne.

## Pflege und Erweiterung

1. Neue Einträge in die passende Datei schreiben – ein Eintrag je Zeile, an beliebiger
   Stelle, in der üblichen Schreibweise mit Diakritika. Kommentare (`#`) nur im Dateikopf.
2. `python werkzeuge/wissen_pflegen.py --schreiben` ausführen: sortiert die Dateien,
   entfernt doppelte Einträge, vereinheitlicht Zeilenenden und prüft die Querbezüge.
   Einträge, die sich nur in Groß-/Kleinschreibung unterscheiden, meldet es nur – welche
   Schreibweise stimmt, entscheidet der Mensch. „Alles in Ordnung.“ bzw. Rückgabewert 0
   heißt: fertig. Ohne `--schreiben` wird nur geprüft.
3. `python -m pytest tests/test_wissen.py` ausführen.

Dabei gilt:

- **Name, der auch ein gewöhnliches Wort ist** (Familienname „Fuchs“, Vorname „Rosa“):
  zusätzlich in `nachnamen_mehrdeutig.txt` bzw. `vornamen_mehrdeutig.txt`.
- **Name mit Partikel** vollständig eintragen („van Bommel“) und den Kern zusätzlich
  („Bommel“), außer der Kern ist Vorname oder Allerweltswort.
- **Beruf, der auch Familienname ist** (Koch, Richter, Bauer): muss in
  `nachnamen_mehrdeutig.txt` stehen; das Pflegewerkzeug meldet fehlende Fälle.
- **Berufe** in beiden Formen ausschreiben (Zahnarzt und Zahnärztin).
- **Allerweltswörter**: nur großgeschriebene Wörter, die in keiner Namensliste stehen
  (Namen, die auch Wörter sind, gehören in die `*_mehrdeutig`-Listen). Einfache
  Beugungsformen (-e, -n, -en, -nen, -s, -es; Wortform ab sechs, Grundform ab fünf
  Buchstaben) findet `ist_allerweltswort` selbst; das Pflegewerkzeug lehnt Wörter ab, die
  so einen Namen träfen.
- **Erlaubnisliste**: nur Organisationen, Produkte und Fachbegriffe. Ein einzelnes Wort, das
  auch Vor- oder Nachname ist (Basler, Gerling, Nürnberger), muss zusätzlich in der
  passenden `*_mehrdeutig`-Liste stehen.
- **Etiketten** so, wie sie in Formularen stehen, Abkürzungen mit Punkt („Vers.-Nr.“).
- **Herkunft:** nur aufnehmen, was aus eigener Kenntnis, aus eigenen Dokumenten oder aus
  gemeinfreien bzw. CC0-Quellen stammt – keine fremden Listen kopieren.

Eine neue Liste braucht einen Eintrag in `LISTEN` (`wissen.py`) und eine Mindestgröße in
`tests/test_wissen.py`.

Für das PyInstaller-Paket muss dieser Ordner mitkopiert werden:
`--add-data "anonymisierer\daten;anonymisierer\daten"`. Fehlt eine Datei, meldet
`wissen.py` einen `WissensbasisFehler` mit Hinweis auf die unvollständige Installation.

## Qualitätssicherung

- **Formal (Pflegewerkzeug und Tests):** UTF-8 ohne BOM, LF-Zeilenenden, NFC, keine
  Steuerzeichen, sortiert nach Vergleichsform, keine Dubletten, Kopfkommentar mit Verweis
  auf diese Datei, Mindestgrößen je Liste, keine Ziffern in Namenslisten.
- **Querbezüge:** `allerweltswoerter_gross` enthält keinen Vor- oder Nachnamen, keinen Beruf,
  keine Diagnose und kein Medikament, auch nicht über die Beugungsregel; jeder Eintrag der
  `*_mehrdeutig`-Listen steht in der Grundliste; Berufe und Einzelwörter der Erlaubnisliste,
  die zugleich Namen sind, stehen in den `*_mehrdeutig`-Listen; der Kern jedes
  Partikelnamens steht als eigener Eintrag, sofern er kein Vorname oder Allerweltswort ist.
- **Stichproben:** `tests/test_wissen.py` prüft in rund 370 Fällen Einträge, die vorhanden
  sein müssen (unter anderem die großen Versicherer, Krankenkassen und Behörden, die
  Meyer/Maier/Mayer/Meier-Varianten, die Berufe Zahnärztin, Polier, Beamtin, Rentnerin,
  Auszubildende, Studentin, Hausfrau, selbstständig); Gegenproben stellen sicher, dass
  Allerweltswörter keine Namen und Namen keine Allerweltswörter sind.
- **Durchsicht:** Nicht belegte deutsche Namen und Allerweltswörter sowie alle Einträge der
  `*_mehrdeutig`-Listen wurden einzeln gesichtet. Gestrichen wurden unter anderem
  Familiennamen, die fast nur als Wort vorkommen (Herr, Mensch, Preis, Platz), Vornamen wie
  Liga oder Islam, als Diagnose missverständliche Kürzel und Wörter (ALL, ALS, Krone,
  Brücke, Geburt) sowie Berufseinträge, die fast immer Familiennamen sind (Müller,
  Schneider, Fischer, Weber).
- **Geschwindigkeit:** Die Suche einer Liste in 100 KB Text dauert wenige Millisekunden (Test:
  unter 50 ms); der Aufbau aller Suchindizes dauert unter einer Sekunde.

## Grenzen

- Keine Namensliste ist vollständig. Seltene Familiennamen, neue Vornamen und ungewöhnliche
  Umschriften fehlen; Erkennungsregeln dürfen sich daher nie allein auf diese Listen stützen,
  sondern brauchen zusätzlich Kontext (Anrede, Etikett, Satzbau, Sprachmodell).
- Viele Namen sind zugleich Wörter (Koch, Wolf, Winter, Rosa). Die `*_mehrdeutig`-Listen
  kennzeichnen die bekannten Fälle; ob ein Vorkommen ein Name ist, entscheidet erst der
  Kontext.
- Die Vergleichsform entfernt Diakritika; dadurch fallen einzelne Wörter zusammen
  (Bär/Bar). Bekannte Kollisionen mit häufigen Wörtern stehen in den
  `*_mehrdeutig`-Listen.
- Diagnosen stehen überwiegend in der Grundform; Plural- und Genitivformen sowie freie
  Komposita („Bandscheibenvorfallsoperation“) erkennt die Liste nicht von selbst.
- Am Zeilenende getrennte Wörter muss der Aufrufer vor der Suche zusammenfügen.
- Handelsnamen von Arzneimitteln ändern sich; die Liste bildet den Stand 2026 ab.
