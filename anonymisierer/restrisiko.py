"""Restrisiko-Prüfung: die zweite, unabhängige Verteidigungslinie (Vertrag Abschnitt 7).

Nach dem Schwärzen wird die AUSGABE noch einmal gelesen – Textebene, bei Scans und Bildbereichen die OCR (aus
dem Zwischenspeicher des OCR-Dienstes, mit derselben Ausrichtung wie die Selbstkontrolle; unveränderte Seiten
mit den OCR-Wörtern der Analyse, also ohne zweiten OCR-Lauf) – und nach allem durchsucht, was nach
personenbezogenen Daten aussieht. Was die Erkennung übersehen hat, darf das Haus nie still verlassen: jeder
Verdacht macht die Ausgabe zu _PRUEFEN, die Vorschau zeigt ihn orange, „Nachschwärzen“ übernimmt ihn.

Unabhängigkeit: Bewusst NICHT benutzt werden das Detektor-Register, namen.py, muster.py und das Sprachmodell –
eine zweite Verteidigungslinie darf nicht dieselben blinden Flecken haben wie die erste. Benutzt werden nur die
Listen der Wissensbasis (anonymisierer.wissen), das Seitenmodell (dieselbe Lesart der Seite), die gemeinsame Regel
„Etikett + Wert“ für eVB-Nummer, Transferticket, Kartenprüfnummer und Geburtsname (anonymisierer.kennungsformen –
mit der Erkennung geteilt, damit beide dieselben Schreibweisen kennen: getrennt gebaut, hatten beide dieselben
Lücken, Gegenprüfung Runde 4c), der Familien- und Versichertenkontext für Geburtsdaten ohne Stichwort, Wohn- und
Nachbarschaftsangaben, Tierangaben, die USt-IdNr. von Einzelkaufleuten, die Felder C.1.1/C.1.2 der
Zulassungsbescheinigung und Namen einer GbR (anonymisierer.personenkontext, ebenso geteilt), die Gattungswörter vor
einem Ort (wissen.ortsname_hinter_gattung) und eigene, einfache Formregeln mit eigenen Prüfziffer-Rechnungen – dazu
für den Seitenverdacht das Pixelmaß „Seite nachweislich leer“ (analyse.seite_nachweislich_leer, keine Erkennung:
dieselbe Entscheidung „leere Rückseite“ wie beim Status der Schwärzung).

Was gemeldet wird (jede Regel liefert Stelle + Grund):
  * Kennungen: Ziffernfolgen ab 5 Ziffern – auch in Gruppen ("6 259 674 059", "0170 318 40 11") und mit
    Buchstaben ("KF007952512", "LV-2014-697971") –, außer Beträgen, Datumsangaben, Uhrzeiten, Paragrafen,
    Prozent- und Maßangaben, Verhältnissen ("300/150"), Diagnoseschlüsseln ("I25.11"; nur aus Ziffern – so liest die
    OCR das I – auf OCR-Zeilen, auf der Textebene nur in Klammern oder neben einer Diagnose), Handelsregister-, USt-
    und Gläubiger-Nummern, Service-Rufnummern (0800 …), Hausnummer + PLZ ("Platz 21 - 81675 München": eine Anschrift)
    und den Angaben einer Organisation in ihren Organisationsbereichen. Datumsförmige Ziffern sind nur dann kein
    Verdacht, wenn sie ein Datum sein können: auf OCR-Zeilen auch verlesen ("0.04.2025", "81.07.2018"), auf der
    Textebene – dort ist nichts verlesen – nur mit Monat bis 12, Tag bis 31 und Jahr 19xx/20xx oder direkt an einer
    Schwärzung; "12.34.5678" oder eine Ziffernfolge hinter einem Kennungs-Etikett bleibt eine Kennung.
  * Organisationsbereiche (_Seitenpruefung._org_bereiche): Fußbereich einer juristischen Person (Zeilen am unteren
    Rand, auf der Textebene kleiner als der Brieftext, mit Pflichtangaben wie Amts-/Registergericht, HRB, USt-IdNr.,
    Vorstand, Geschäftsführer; Rechtsform oder Organisationswort im Bereich, keine Merkmale einer natürlichen Person
    wie Inhaber, Praxis, Kanzlei, Dr. med. oder ein Personen-Platzhalter außerhalb der Organ-Angaben), Briefkopf und
    Anschrift einer Organisation (Zellen unter ihrem Namen in derselben Spalte) – Anschriften, Telefon-, Register-,
    Steuer- und Kontonummern, USt-IdNr., IBAN/BIC hinter ihrer Bankangabe (Fußbereich) und Internetadressen dort
    sind keine Personenangaben. Der Fußbereich wächst nicht über Fließtext, Kundenangaben ("Kontoinhaber", "Ihre
    Kundennummer"), SEPA-Mandate und private Fußzeilen am Seitenende. Nie ausgenommen: Namen und Werte hinter
    Kennungs-, Personen- und Geburtsdatum-Etiketten ("Kunden-Nr. 4711" in einer laufenden Fußzeile) und eine
    persönliche Steuer-ID (Prüfziffer).
  * Formen mit Prüfziffer: IBAN (auch in Kästchenschrift "D E  6 9  9 1 4 9 …" und so, wie die OCR handschriftlich
    ausgefüllte Kästchen liest), Steuer-ID, SV-Nummer, Krankenversichertennummer, FIN, Kreditkarte, Ausweis.
    Gemeldet wird die FORM; eine gültige Prüfziffer verstärkt nur den Grund (OCR-Verleser lassen Prüfziffern
    scheitern). Dazu Kfz-Kennzeichen-Form, BIC-Form (hinter "BIC"/"SWIFT", einer IBAN, einem Banknamen oder einem
    Bank-Etikett derselben Zelle: "Kreditinstitut (Name und BIC): Postbank Ndl. Mitte PBNKDEFF") und Werte hinter
    Kennungs-Etiketten ("Az. 123 C 45/24"); hinter den Etiketten einer eVB-Nummer, eines Transfertickets und einer
    Kartenprüfnummer ("CVC 123"; "Prüfnummer" allein nur mit einer Kartenangabe daneben) zählt deren eigene Form,
    auch kurz und mit nur einer Ziffer – in derselben Zeile, hinter Zwischenwörtern desselben Satzes bis zu einer
    Ankündigung ("Die eVB-Nummer Ihres neuen Fahrzeugs lautet: …") oder hinter wenigen Wörtern am Zeilenende
    ("Prüfziffer hinten 739"), am Anfang der nächsten Zeile, in der Zelle daneben und in einer Tabellenspalte (auch
    unter einem Kopf über zwei Zeilen); dazu Kartendaten ohne Etikett (Kartennummer bzw. ihr Platzhalter,
    Ablaufdatum, drei oder vier Ziffern).
  * Kontakt: "@" (außer Funktionspostfächern wie info@ oder schaden@), "+Ländervorwahl", Namen in
    Internetadressen.
  * Datum mit plausiblem Geburtsjahr (Alter 14-110), außer hinter Vertragsdaten-Etiketten (Beginn, Ablauf,
    Datum …, auch als Tabellenspalte) und in Zeiträumen; hinter Geburtsdatum-Etiketten jedes vergangene Datum.
    Jünger als 14 Jahre nur im Familien- und Versichertenkontext (personenkontext: "Kind 2:", "Tochter:",
    "Mitversicherte Person:", "Reisende:" in der Zeile vor dem Namen oder als Überschrift des Blocks) direkt an einer
    Person – einem Personen-Platzhalter oder einem Vor-/Nachnamen der Wissensbasis, getrennt durch Komma, Klammer,
    Stern oder Tabulator ("Kind 2: [PERSON A], 30.06.2018"); nicht an einem Behandler (Titel, Praxis, Klinik davor)
    und nicht vor einem Behandlungstext ("…, 03.11.2012: Meniskusoperation"). Jedes andere Datum der letzten 14 Jahre
    (Rechnungs-, Schadens-, Vertragsdaten) bleibt ohne Verdacht. Dazu ein Geburtsjahr hinter "Geburtsjahr",
    "Geb.-Jahr", "Jahrgang" ("Geburtsjahr der versicherten Person: 1979").
  * Namen: Vor- und Nachnamen der Wissensbasis (eindeutige immer, mehrdeutige mit Personenkontext; nicht als
    Modellname hinter einer Marke: "Seat Leon"), unbekannte Eigennamen in Personenkontext (Herr/Frau/Titel,
    Etiketten wie "Name:", "Vorstand:", direkt hinter einem Vornamen, neben einem Personen-Platzhalter, im
    Unterschriftsblock unter einer Grußformel, als Geburtsname hinter "geb."/"geborene" (auch "gab." zwischen zwei
    Namen: so liest die OCR "geb.") oder hinter dem Feld "Geburtsname" ("Familienname (Geburtsname): [PERSON A]
    (Quarnstedt)") – nicht ein Ort, ein Funktionswort oder das nächste Feld-Etikett), Monats-/Wochentagsnamen
    direkt hinter einem Vornamen, Namen der Wissensbasis hinter einer Geschäftsbezeichnung ("Werkstatt Weiß" – auf
    Scans auch klein gelesen). OCR-Wörter, die mit l + Konsonant beginnen, werden mit großem I gelesen ("llir" ->
    "Ilir").
  * Anschriften: Straße + Hausnummer, Postfach, PLZ + Ort, Werte hinter Anschrift-Etiketten ("Ort: Jena").
  * Reste neben Anschrift-Platzhaltern ("Untere [ADRESSE]", "[PLZ ORT] i.d.OPf.") – auch auf Scans, wo
    Platzhalter (Textebene) und OCR-Wörter nur über die Lage auf der Seite benachbart sind – und Bruchstücke mit
    Ziffern, die ein graues Schwärzungsrechteck berühren ("-WXV09-07": Wert mitten im Wort abgeschnitten).
  * Ort-Datum-Zeilen ("Tübingen, 14. Januar 2025": meist der Wohnort der Unterzeichnenden).
  * Formularfelder des Originals (von der Schwärzung übergeben), deren Wert in der Ausgabe noch lesbar ist – außer
    bloßen Merkmalen aus einem geschlossenen Wortschatz (Familienstand und Geschlecht: "ledig", "weiblich"), die auf
    niemanden hinweisen; eine Staatsangehörigkeit ("polnisch") und ein klein getippter Name oder Ort ("müller",
    "berlin") bleiben Verdacht.
  * Scan-Seiten: dichte Tinte in Unterschriftsblöcken (unter der Grußformel – auch so, wie die OCR sie liest,
    auch schräg –, über/neben "Unterschrift", über Rollenzeilen wie "Mandant" | "Makler"), neben Personenangaben
    (hinter "Name:", neben einem Personen-Platzhalter) und hinter Bank- und Kontoangaben ("Kreditinstitut (Name und
    BIC):", "IBAN:" – handschriftlich ausgefüllte Mandate), die die OCR nicht VERLÄSSLICH gelesen hat: gar nicht, mit
    einem Wortkasten, der nicht zum Text passt (viel höher als die Schrift: Unterschriftszug, Wort samt Zug; viel
    breiter als die Zeichen: ein Zug, als "Med" oder "az" gelesen), als
    Buchstabensalat – oder als Wort, das ein Name sein kann (dort macht die Lesung die Tinte nicht harmlos:
    "DeLuca" unter "Mit freundlichen Grüßen", vom Unterschriftszug durchkreuzt; Berufsangaben, Organisationswörter
    und Kürzel wie "Facharzt für Innere Medizin", "Hauptagentur Nord", "& Partner", "LL.M." sind keine Namen).
    Bereiche in Leserichtung (OCR-Ausrichtung 0/90/180/270°, Schräglage aus der OCR); Tinte relativ zum Papier (auch
    blasse Kugelschreiber-Striche), Linien und GERADE Reste von Unter-/Durchstreichungen zählen nicht; Rechteck je
    Tintengruppe, "bitte ansehen". Der Unterschriftszug zu einem GESCHWÄRZTEN gedruckten Namen (über dem
    Personen-Platzhalter oder ihn kreuzend) ist kein Verdacht: ein Zug ist keine lesbare Angabe, und der Name, zu dem
    er gehört, ist schon ersetzt; ohne geschwärzten Namen daneben bleibt Tinte im Unterschriftsfeld Verdacht (dort kann
    ein ungelesener Name stehen).
Seitenverdacht (ohne Rechteck, „Seite selbst durchsehen“): eine Scan-Seite, auf der die OCR (fast) nichts gelesen
hat und die nicht nachweislich leer ist (analyse.seite_nachweislich_leer – sieht auch hell gedruckten Text und
Bleistift: ein hellgrauer Scan ohne OCR-Wörter ist kein leeres Blatt), eine kaum lesbare Scan-Seite (mehr als 20 %
OCR-Bruchstücke wie "|", "\\", ".", Einzelzeichen – Fax, starke Kompression) und eine Scan-Seite, deren Lesung nach
dem Maß der OCR unplausibel ist (Buchstabensalat einer verdrehten Seite, Handschrift): dort kann die Prüfung nicht
verlässlich lesen, also muss ein Mensch hinsehen.
Nie Verdacht: Platzhaltertext ([PERSON A], [GESCHWÄRZT] …), die NIE-Liste der Nutzerin und bewusst abgewählte
Stellen (Entscheidung der Nutzerin). Die Prüfung ist in jeder Schutzstufe gleich empfindlich (profil wird nur
durchgereicht).

Öffentliche Schnittstelle:
    Verdacht(seite, start, ende, text, grund, rechtecke)   seite 0-basiert; start/ende im Seitentext der Ausgabe
                                                           (-1 = ganze Seite); rechtecke in Seitenkoordinaten
                                                           (nach remove_rotation), [] = Lage unbekannt
    restrisiko_pruefen(ausgabe_pfad, ocr=None, platzhalter=None, profil="hoch", nie=None, wissen=None, *,
                       ocr_modus=None, winkel=None, bildbereiche=None, ocr_woerter=None, abgewaehlt=None,
                       felder=None, abbruch=None) -> list[Verdacht]
    pruefe_text(text, platzhalter=None, nie=None, wissen=None) -> list[Verdacht]   (reiner Text: Tests, Werkzeuge)
    verdacht_als_dict(v) -> dict                           (JSON-taugliche Form, Rechtecke als Listen)
"""

from __future__ import annotations

import datetime
import difflib
import re
import unicodedata
from bisect import bisect_left
from pathlib import Path
from typing import NamedTuple

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen kennen nur den Namen "fitz"
    import fitz

from . import kennungsformen
from . import personenkontext
from . import ocr as _ocr
from . import seitenmodell as sm

OCR_DPI = sm.OCR_DPI
ALTER_MIN = 14                 # plausibles Geburtsjahr: Alter 14 bis 110 Jahre (ohne Geburts-Etikett)
ALTER_MAX = 110
MIN_ZIFFERN = 5                # Ziffernfolgen ab so vielen Ziffern sind ein Verdacht
SPALTE_ZEILEN = 40             # so weit sucht die Spaltenkopf-Regel nach oben (Zeilen)
SCAN_MIN_WOERTER = 3           # weniger OCR-Wörter: Scan-Seite gilt als ungelesen, außer sie ist nachweislich leer
SCAN_RAUSCHEN_MAX = 0.20       # mehr OCR-Bruchstücke ("|", "\\", "u", "0.") als dieser Anteil: Scan kaum lesbar
SCAN_RAUSCHEN_MIN_WOERTER = 40  # … erst ab so vielen OCR-Wörtern bewertet
FUELLFARBE = (0.92, 0.92, 0.92)  # Füllfarbe der Schwärzungsrechtecke (schwaerzung.FUELLFARBE)
# Organisationsbereiche (Briefkopf, Anschrift und Fußzeile eines Unternehmens, _Seitenpruefung._org_bereiche)
FUSS_ANTEIL = 0.72             # Fußbereich: Zeilen unterhalb dieses Anteils der Seitenhöhe (in Leserichtung) …
FUSS_LUECKE = 1.2              # … höchstens so viele Zeilenhöhen voneinander entfernt …
FUSS_SCHRIFT = 1.35            # … und Schrift höchstens so viel größer als die größte darunter (Fließtext ist größer;
FUSS_SCHRIFT_MIN = 8.0         #     verglichen mit mindestens dieser Höhe – OCR-Kästen schwanken) …
FUSS_BRIEFTEXT = 0.95          # … auf der Textebene auch kleiner als der Brieftext (Median der Zeilen darüber)
ORGAN_ZEILEN = 4.0             # Namen hinter "Vorstand:" o. Ä.: bis so viele Zeilenhöhen darunter in derselben Spalte
ORGAN_ABSTAND = 250            # … oder in derselben Zeile höchstens so weit (pt) rechts vom Etikett
ORGAN_NAME_BREITE = 80         # "(Vorsitzende)" hinter dem ersten Namen: die Namensliste beginnt bis so weit (pt) links
ORG_BLOCK_ZEILEN = 4           # Organisationsblock: so viele Zellen unter dem Namen der Organisation …
ORG_BLOCK_LUECKE = 1.2         # … mit höchstens so viel Abstand (Zeilenhöhen) …
ORG_BLOCK_SCHRIFT = 1.3        # … und Schrift höchstens so viel größer als die Zelle darüber
SCHRIFT_OCR = 1.9              # auf OCR-Zeilen statt FUSS_SCHRIFT/ORG_BLOCK_SCHRIFT: Wortkästen schwanken mit Ober-/
                               # Unterlängen und zusammengelesenen Spalten (gemessen: 6-13 pt für eine 7-pt-Fußzeile)

GRUND_SEITE_UNGELESEN = ("Scan-Seite konnte nicht gelesen werden (keine Texterkennung) – Seite selbst "
                         "durchsehen")
GRUND_SEITE_RAUSCHEN = ("Scan-Seite ist kaum lesbar (viele OCR-Bruchstücke) – nicht erkannte Angaben möglich, "
                        "Seite selbst durchsehen")
GRUND_SEITE_UNPLAUSIBEL = ("Scan-Seite ist nicht verlässlich lesbar (Texterkennung liefert Buchstabensalat – Seite "
                           "verdreht, Handschrift oder unleserlich) – Seite selbst durchsehen")


class Verdacht(NamedTuple):
    seite: int             # 0-basiert
    start: int             # Offsets im Seitentext (Seitenmodell) der AUSGABE; -1 = ganze Seite
    ende: int
    text: str
    grund: str
    rechtecke: list        # fitz.Rect je Zeile (Koordinaten nach remove_rotation); [] = Lage unbekannt


def verdacht_als_dict(v) -> dict:
    """Verdacht (NamedTuple oder dict) als JSON-taugliches dict (Rechtecke als [x0, y0, x1, y1])."""
    felder = dict(v) if isinstance(v, dict) else v._asdict()
    felder["rechtecke"] = [[round(float(x), 2) for x in fitz.Rect(r)] for r in (felder.get("rechtecke") or [])]
    return felder


# ----------------------------------------------------------------------
# Feste Wortlisten der Regeln (klein und allgemein – keine Kopie der Erkennung)
# ----------------------------------------------------------------------
_MONATE = {"januar": 1, "jan": 1, "jänner": 1, "februar": 2, "feb": 2, "märz": 3, "mär": 3, "maerz": 3,
           "april": 4, "apr": 4, "mai": 5, "juni": 6, "jun": 6, "juli": 7, "jul": 7, "august": 8, "aug": 8,
           "september": 9, "sep": 9, "sept": 9, "oktober": 10, "okt": 10, "november": 11, "nov": 11,
           "dezember": 12, "dez": 12}
_KALENDERWOERTER = frozenset({
    "januar", "februar", "märz", "april", "mai", "juni", "juli", "august", "september", "oktober", "november",
    "dezember", "montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonnabend", "sonntag",
    "ostern", "pfingsten", "weihnachten"})
# Großgeschriebene Funktionswörter und allgemeine Personenwörter: nie ein Name (auch nicht am Satzanfang)
# Artikel und Begleiter direkt vor einem großgeschriebenen Wort: ein Substantiv, kein Name ("Die Scheibe ist …")
_ARTIKEL = frozenset({"der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem", "einer", "eines",
                      "kein", "keine", "keinen", "keinem", "keiner", "diese", "dieser", "dieses", "diesen", "jede",
                      "jeder", "jedes", "unsere", "unser", "ihre", "seine", "meine", "deren", "dessen"})
_STOPPWOERTER = frozenset("""
der die das den dem des ein eine einen einem einer eines und oder aber doch sondern denn weil da dass daß wenn
als wie ob mit ohne für gegen um durch bis von vom zu zum zur bei beim nach aus auf an am in im über unter vor
hinter neben zwischen seit ab wegen trotz während ich du er sie es wir ihr ihre ihren ihrem ihres ihrer ihnen ihm
ihn mich mir dich dir uns euch sich sein
seine seinen seinem seiner mein meine meinen meinem meiner unser unsere unseren unserem unserer euer eure dieser
diese dieses diesen diesem jeder jede jedes jeden alle allen keine kein keinen bitte danke sehr herzliche
herzlichen freundliche freundlichen viele vielen beste besten liebe lieber hallo guten tag ja nein nicht auch
noch schon nur hier dort heute morgen gestern bereits außerdem zudem daher deshalb somit also hiermit hierbei
dazu damit dabei danach davon darauf dafür leider gerne gern selbstverständlich anbei beiliegend anlage anlagen
betreff seite nr datum ort uhr euro person personen kunde kunden kundin mandant mandantin partner partnerin
kollege kollegin kollegen doktor professor team abteilung firma familie ehemann ehefrau mann frau kind kinder
sohn tochter vater mutter herr herren damen dame grüße gruß zeichen unterschrift name vorname nachname
versicherte versicherter versicherten vertreter vertreterin inhaber inhaberin makler maklerin geb gez sitz
vorstand vorsitz vorsitzender vorsitzende aufsichtsrat geschäftsführer geschäftsführung bzw usw etc
gmbh ag kg mbh se ohg gbr ug kgaa vvag ev
""".split())
# Marken (Fahrzeuge, Geräte), die zugleich Familiennamen sind – hinter "Hersteller/Typ" kein Personenname
_MARKEN = frozenset({"renault", "ford", "opel", "peugeot", "porsche", "ferrari", "lamborghini", "bentley", "jaguar",
                     "chevrolet", "cadillac", "lincoln", "dodge", "chrysler", "honda", "mazda", "suzuki", "toyota",
                     "nissan", "hyundai", "skoda", "dacia", "fiat", "volvo", "saab", "tesla", "mercedes", "benz",
                     "daimler", "audi", "bosch", "siemens", "miele", "philips", "maybach", "borgward", "lancia",
                     "citroen", "citroën", "cupra", "mitsubishi", "subaru", "lexus", "landrover", "seat", "kia",
                     "mini", "smart", "jeep", "alfa", "volkswagen", "infiniti", "iveco", "rover", "chery", "polestar"})
_ANREDEN = frozenset({"herr", "herrn", "frau", "divers", "firma", "familie", "eheleute", "mr", "mrs", "ms", "miss",
                      "monsieur", "madame", "signor", "signora", "señor", "señora", "keine", "keine angabe"})
# Wörter, die hinter Herr/Frau stehen, aber kein Name sind
_ANREDE_ZUSATZ = frozenset({"kollege", "kollegin", "doktor", "professor", "rechtsanwalt", "rechtsanwältin",
                            "notar", "notarin", "pfarrer", "pfarrerin", "bürgermeister", "bürgermeisterin",
                            "direktor", "direktorin", "präsident", "präsidentin", "minister", "ministerin",
                            "abgeordneter", "abgeordnete", "vorsitzender", "vorsitzende", "dekan", "dekanin"})
# Funktionspostfächer: keine Person dahinter
_FUNKTIONSPOSTFAECHER = frozenset({
    "info", "infos", "service", "kundenservice", "kundendienst", "kontakt", "kontakte", "schaden", "schaeden",
    "schadenservice", "schadenmeldung", "schadensmeldung", "post", "poststelle", "postfach", "mail", "email",
    "office", "buero", "zentrale", "vertrieb", "datenschutz", "datenschutzbeauftragter", "dsb", "noreply",
    "no-reply", "donotreply", "support", "hilfe", "leistung", "leistungen", "leistungsservice", "antrag",
    "antraege", "vertrag", "vertraege", "makler", "maklerservice", "maklerbetreuung", "partner", "presse",
    "beschwerde", "beschwerden", "beschwerdemanagement", "buchhaltung", "rechnung", "rechnungen", "inkasso",
    "beitrag", "beitraege", "kfz", "leben", "kranken", "sach", "haftpflicht", "rechtsschutz", "unfall",
    "verwaltung", "sekretariat", "empfang", "anfrage", "anfragen", "bestand", "bestandsservice", "termin",
    "termine", "bewerbung", "karriere", "personal", "webmaster", "admin", "kundencenter", "servicecenter",
    "ombudsmann", "aufsicht", "kanzlei", "praxis", "team",
})
# Rechtsformen und Wörter, die eine Organisation kennzeichnen (Briefkopf/Fußzeile eines Unternehmens)
# Rechtsform einer juristischen Person direkt hinter dem Wort ("Hausverwaltung Inntal GmbH": ein Firmenname, kein
# Familienname einer Person; Personengesellschaften wie KG, OHG, GbR, e.K. nennen oft Personen)
_JURISTISCH_DANACH_RE = re.compile(r"[ \t]+(?:GmbH|gGmbH|AG|SE|KGaA|mbH|UG|e\.[ \t]?V\.|eG|VVaG|a\.[ \t]?G\.)"
                                   r"(?![\wäöüß])")
_RECHTSFORM_RE = re.compile(
    r"(?<![\w])(?:AG|GmbH|mbH|SE|KG|KGaA|OHG|GbR|e\.\s?V\.|eG|e\.\s?G\.|VVaG|V\.V\.a\.G\.|a\.\s?G\.|AöR|KdöR|"
    r"Ltd\.?|S\.A\.|N\.V\.|B\.V\.|Inc\.|PartG(?:mbB)?|UG|(?i:v{1,3}a[gq]|gmbh|kgaa))(?![\w])")
_ORG_WORT_RE = re.compile(
    r"(?i)(?:versicherung|versicherungen|versicherer|assekuranz|bank|banken|sparkasse|volksbank|raiffeisenbank|"
    r"kasse|krankenkasse|bausparkasse|pensionskasse|rentenversicherung|berufsgenossenschaft|finanzamt|amtsgericht|"
    r"landgericht|gericht|behörde|bundesagentur|agentur für arbeit|polizei|polizeiinspektion|polizeipräsidium|"
    r"klinikum|universität|hochschule|verband|kammer|stadtwerke|holding|konzern|stiftung|versicherungsgruppe)"
    r"(?![a-zäöüß])")
# Pflichtangaben eines Unternehmens (sie lösen den Fußbereich aus; ob es einer juristischen Person gehört, prüft
# _fussbereich) – auch so, wie die OCR sie liest ("USt-ldhr."). Nicht dabei: Bankverbindung, Gläubiger-ID, "Sitz:"
# und "Umsatzsteuer" allein – die stehen auch auf Belegen von Privatleuten und mitten in Sätzen ("Meine
# Bankverbindung lautet")
_PFLICHTANGABE_RE = re.compile(
    r"(?i)(?<![\w])(?:Registergericht|Handelsregister|Amtsgericht|Sitz\s+der\s+Gesellschaft|"
    r"HR\s?[AB](?![a-zäöüß])[\s.:]{0,2}\d|U\s?St[\s.-]{0,2}[I1l|ı][dD]|Umsatzsteuer[\s-]?Id|Vorstand|Vorstände|"
    r"Aufsichtsrat|Gesch[äa]ftsf[üu]hr|BaFin|Vermittlerregister|Komplementär|Vereinsregister|Genossenschaftsregister)")
# Merkmale einer JURISTISCHEN Person (nur deren Fußbereich ist ein Organisationsbereich): Rechtsform einer
# Kapitalgesellschaft, eines Vereins, einer Genossenschaft, des öffentlichen Rechts, HRB, ein Vorstand oder
# Aufsichtsrat. Nicht e.K., HRA, GbR, OHG, KG, PartG und nicht "Geschäftsführer" allein: dahinter können natürliche
# Personen stehen – deren Anschrift, Telefon und Bankverbindung sind Personenangaben (Handwerker-, Werkstatt-,
# Arztrechnung)
_RECHTSFORM_JUR_RE = re.compile(
    r"(?<![\w])(?:AG|GmbH|gGmbH|mbH|SE|KGaA|eG|e\.\s?G\.|e\.\s?V\.|VVaG|V\.V\.a\.G\.|a\.\s?G\.|AöR|KdöR|Ltd\.?|S\.A\.|"
    r"N\.V\.|B\.V\.|Inc\.|UG|(?i:v{1,3}a[gq]|gmbh|kgaa))(?![\w])"
    r"|(?i:(?<![\w])(?:Anstalt|Körperschaft)\s+des\s+öffentlichen\s+Rechts)")
_JURISTISCH_RE = re.compile(
    _RECHTSFORM_JUR_RE.pattern + r"|(?i:(?<![\w])HR\s?B(?![a-zäöüß])[\s.:]{0,2}\d"
    r"|(?<![\w])(?:\w*vorstand\w*|vorstände|\w*aufsichtsrat\w*|vereinsregister|genossenschaftsregister))")
# Organe und Vertreter einer Organisation: Namen dahinter (in derselben Zeile oder darunter in derselben Spalte) sind
# Organmitglieder, keine Inhaber ("Vorstand: [PERSON A], [PERSON B]", "Vorsitz Aufsichtsrat:" / "[PERSON C]")
_ORGAN_RE = re.compile(r"(?i)(?<![\w])(?:\w*vorstand\w*|vorstände|\w*aufsichtsrat\w*|vorsitz\w*|gesch[äa]ftsf[üu]hr\w*|"
                       r"komplementär\w*|prokur\w*|verwaltungsrat\w*|beirat\w*)")
# … für den unscharfen Vergleich mit OCR-Wörtern ("Vorszand:", "Aufsichterat")
_ORGAN_WOERTER = ("vorstand", "vorstände", "vorstands", "aufsichtsrat", "aufsichtsrats", "vorsitz", "vorsitzender",
                  "vorsitzende", "geschäftsführer", "geschäftsführerin", "geschäftsführung")
# Merkmale einer natürlichen Person als Trägerin: Inhaber, Einzelkaufmann, freie Berufe, Praxis, Kanzlei, Titel,
# Personengesellschaften – steht eines davon außerhalb der Organe, gehört der Bereich (auch) einem Menschen
_NATUERLICH_RE = re.compile(
    r"(?i)(?<![\w])(?:Inhaber(?:in|innen)?|Inh\.|e\.\s?K(?:fm|fr)?\.|Einzelunternehm\w*|\w*praxis|Praxisgemeinschaft|"
    r"\w*kanzlei|Rechtsanw[äa]lt(?:in|innen|e|en)?|Fachanw[äa]lt(?:in|innen|e|en)?|Notar(?:in|innen|e)?|"
    r"Steuerberater(?:in|innen)?|Heilpraktiker(?:in|innen)?|(?:Fach|Zahn|Tier|Haus)?(?:arzt|ärztin|ärzte)|"
    r"Physiotherap\w*|GbR|OHG|PartG(?:mbB)?)(?![\w])|(?<![\w])(?:Dr|Prof|Dipl)\.")
# Bankangaben (Bankverbindung, Name der Bank, IBAN, BIC): sie nennen eine Bank, nicht den Träger des Bereichs
_BANK_RE = re.compile(r"(?i)bank|sparkasse|kreditinstitut|geldinstitut|(?<![\w])(?:IBAN|BIC|SWIFT|BLZ|Konto\w*|Kto)"
                      r"(?![\w])")
_BANKNAME_RE = re.compile(r"(?i)bank|sparkasse|kreditinstitut|geldinstitut")
_SEGMENT_RE = re.compile(r"\t+| {3,}|\s?[·|•]\s?")
# Besitz- und Kundenwörter vor einer Kontoangabe: "Ihre IBAN", "von Ihrem Konto", "Kontoinhaber" – Angabe des Kunden
_KUNDE_KONTO_RE = re.compile(r"(?i)(?<![\w])(?:ihr\w*|mein\w*|kunde\w*|kundin\w*|kontoinhaber\w*|zahler\w*|"
                             r"zahlungspflichtig\w*|versicherungsnehmer\w*|mandat\w*|lastschrift\w*)(?![\w])")
# Besitz- und Kundenwörter in einer Zeile am Seitenende: eine Angabe zum Kunden ("Ihr Fahrzeug KS-AB 1234 · Seite 1",
# "Ihre IBAN: …", "Meine Bankverbindung lautet"), keine Pflichtangabe der Organisation – der Fußbereich endet davor
_KUNDE_FUSS_RE = re.compile(r"(?i)(?<![\w])(?:ihr|ihre|ihren|ihrem|ihres|ihrer|mein|meine|meinen|meinem|meines|meiner|"
                            r"kontoinhaber\w*|versicherungsnehmer\w*|zahlungspflichtig\w*|mandatsreferenz)(?![\w])")
# Kleinwörter, die auch in Pflichtangaben stehen ("Sitz der Gesellschaft", "Bank für Kirche und Diakonie", "eingetragen
# beim Amtsgericht … unter HRB", "Versicherungsvermittler mit Erlaubnis nach § 34d GewO") – zählen nicht als Fließtext
_FUSS_KLEINWOERTER = frozenset({"für", "und", "der", "des", "die", "im", "am", "an", "auf", "zu", "zur", "zum", "von",
                                "vom", "in", "bei", "beim", "mit", "nach", "unter", "gemäß", "gem", "sowie", "oder",
                                "eingetragen", "zugelassen", "registriert", "seit", "aus", "mbh", "ev", "eg", "ag"})
# Kontakt-Etiketten, die auch eine Organisation in ihrer Fußzeile führt: sie beenden den Fußbereich nicht (Werte
# dahinter prüft org_kontext trotzdem wie überall); andere Personen-, Anschrift- und Kontakt-Etiketten schon
_ORG_KONTAKT_ETIKETTEN = frozenset({"telefon", "tel", "telefax", "fax", "e-mail", "email", "mail", "internet", "web",
                                    "homepage", "kontakt", "zentrale", "service", "hotline", "servicetelefon"})
# Etiketten, hinter denen im Organisationsbereich eine Angabe der Organisation steht: nur eindeutig
# organisationsbezogene (USt-IdNr., Register, Bankleitzahl, BIC, Gläubiger-ID, BaFin, Vermittlerregister,
# Steuernummer) – nie Kunden-, Versicherungs-, Vertrags- oder Beitragskonto, Steuer-IdNr. oder „Ihr …“
_ORG_ETIKETT_RE = re.compile(
    r"(?i)(?:U\s?St[\s.-]{0,2}[I1l|ı][dD](?:[\s.-]{0,2}[NnHh]r)?\.?|"
    r"Umsatzsteuer[\s-]?(?:Identifikations)?(?:nummer|ID)|"
    r"VAT(?:[\s-]?(?:ID|No\.?))?|HR\s?[AB]|Handelsregister(?:nummer)?|Registergericht|Register-?Nr\.?|Registernummer|"
    r"BLZ|Bankleitzahl|BIC(?:/SWIFT)?|SWIFT(?:-Code)?|Gläubiger[\s-]?(?:ID|Identifikationsnummer|Identnummer)"
    r"(?:[\s-]?Nr\.?)?|BaFin(?:[\s-]?(?:ID|Reg\.?[\s-]?Nr\.?))?|VU[\s-]?Nr\.?|Vermittlerregister(?:nummer)?|"
    r"Vermittler-?Nr\.?|Steuer-?Nr\.?|Steuernummer|St\.?-?Nr\.?)")
# Kontoetiketten: Angabe der Organisation nur in deren Bankverbindung (Bankname davor, kein "Ihr", "Kunden-")
_KONTO_ETIKETT_RE = re.compile(r"(?i)(?:IBAN|Konto(?:[\s-]?Nr\.?|-?Nummer|nummer)?|Kto\.?(?:[\s-]?Nr\.?)?|"
                               r"Kontoverbindung|Bankverbindung)")
# USt-IdNr.-Etikett direkt vor einem Wert – auch so, wie die OCR es liest ("USt-ldhr.", "uat-ıdNr.")
_UST_ETIKETT_RE = re.compile(r"(?i)(?<![^\W\d_])[uü][\s.]?[sa5][t7][\s.\-]{0,3}[i1lı|!][dḍ](?:[\s.\-]{0,3}[nh]r)?\.?"
                             r"[\s.:#]*$")
_STEUERNUMMER_ETIKETT_RE = re.compile(r"(?i)(?<![\w])(?:Steuer-?Nr\.?|Steuernummer|St\.?-?Nr\.?)[\s.:#]*$")
_UST_ID_RE = re.compile(r"DE ?\d{3} ?\d{3} ?\d{3}")       # Form der USt-IdNr. (persönliche Steuer-ID: 11 Ziffern)
# kleingeschriebene Wörter, die im Namen einer Organisation stehen dürfen ("Bank für Kirche und Diakonie")
_ORG_VERBINDER = frozenset({"für", "und", "der", "des", "die", "im", "am", "an", "auf", "zu", "zur", "zum", "von",
                            "vom", "in", "bei", "mbh", "eg", "ev", "ag", "se", "kg", "a.g", "a. g", "v. d", "v.d"})
# Etiketten, hinter denen eine Nummer zu einer Organisation gehört (kein Personenbezug)
_ORG_NUMMER_RE = re.compile(
    r"(?i)(?:HR\s?[AB]|Handelsregister|Registergericht|Register-?Nr\.?|Registernummer|Amtsgericht\s+[\w\-.]+|"
    r"USt\.?[\s-]?Id(?:\.?[\s-]?Nr)?\.?|USt-?IdNr\.?|U\s?St[\s.-]{0,2}[I1l|][dD](?:[\s.-]{0,2}[NnHh]r)?\.?|"
    r"Umsatzsteuer[\s-]?(?:Identifikations)?(?:nummer|ID)|VAT|"
    r"BLZ|Bankleitzahl|Gläubiger[\s-]?(?:ID|Identifikations(?:nummer)?|Ident(?:nummer)?)(?:[\s-]?Nr\.?)?|"
    r"Gläubiger-ID-Nr\.?|BaFin[\s-]?(?:ID|Reg\.?[\s-]?Nr\.?)?|VU[\s-]?Nr\.?|BSNR|"
    r"Betriebsstätten[\s-]?(?:nr\.?|nummer)|"
    r"IK[\s-]?(?:Nr\.?|Nummer)?|Institutionskennzeichen|"
    r"Formular(?:[\s-]?Nr\.?)?|Vordruck(?:[\s-]?Nr\.?)?|Druckstück|Form\.?[\s-]?Nr\.?)"
    r"[\s.:#]*$")
_SERVICE_NUMMER_RE = re.compile(r"^(?:\+49\s?\(?0?\)?\s?|0049\s?|0)(?:800|180\d?|900|137|700)(?!\d)|^11[56]\d{0,3}$")
# Einheiten hinter Zahlen (Maße, Mengen, Zeiträume) – keine Kennung
_EINHEIT_RE = re.compile(
    r"^\s?(?:%|‰|€|EUR|Euro|USD|CHF|T€|TEUR|Mio\.?|Mrd\.?|km|m²|m2|qm|cm|mm|m\b|kg|g\b|t\b|ccm|cm³|kW|kWh|"
    r"PS|l\b|"
    r"Liter|Stück|Stk\.?|Monate?n?|Jahre?n?|Tage?n?|Wochen?|Stunden?|Std\.?|Minuten?|Min\.?|Punkte?n?|Uhr|"
    r"Personen|Seiten|Zeichen|dpi|px|Prozent|Promille)(?![\w])", re.IGNORECASE)
_WAEHRUNG_VOR_RE = re.compile(r"(?:€|EUR|Euro|USD|CHF|Betrag|Summe)\s?:?\s?$", re.IGNORECASE)
_STRASSEN_ENDUNG = (r"(?:straße|strasse|str\.|str\b|weg|platz|allee|gasse|ring|damm|ufer|chaussee|steig|pfad|"
                    r"stieg|graben|markt|wall|kamp|deich|anger|promenade|zeile|berg|hof|feld|garten|park|"
                    r"brücke|tor|gang|winkel|höhe|aue|bogen|wiese|grund|redder|twiete|siedlung|terrasse)")
_STRASSE_RE = re.compile(
    r"(?<![\w\-])((?:[A-ZÄÖÜ][\wäöüßÄÖÜ'.]*[\s\-]){0,3}[A-ZÄÖÜ]?[\wäöüßÄÖÜ\-]*" + _STRASSEN_ENDUNG +
    r")[ \t]{0,2}(\d{1,4}(?:[ ]?[a-zA-Z](?![\w]))?(?:[ ]?[-/][ ]?\d{1,4}[a-zA-Z]?)?)(?![\w,.]\d|[\d])",
    re.IGNORECASE)
_STRASSE_PRAEP_RE = re.compile(
    r"(?<![\w\-])((?:Am|An der|An den|An dem|Auf der|Auf dem|Auf den|Im|In der|In den|In dem|Zum|Zur|"
    r"Hinter der|Hinter dem|Hinter den|Unter den|Unter der|Vor dem|Vor den|Über der|Bei der|Platz der|"
    r"Platz des|Alt|Neue|Alte|Obere|Untere|Kleine|Große|Lange|Hohe)[\s\-]"
    r"(?:[A-ZÄÖÜ][\wäöüßÄÖÜ\-]+[ ]){0,2}[A-ZÄÖÜ][\wäöüßÄÖÜ\-]+)[ \t]{1,2}"
    r"(\d{1,4}(?:[ ]?[a-zA-Z](?![\w]))?)"
    r"(?![\w,.]\d|[\d])", re.IGNORECASE)
# Straßenname ohne Hausnummer als ganze Zelle (Zellumbruch: die Hausnummer steht am Anfang der Zeile darunter)
_STRASSENNAME_ZELLE_RE = re.compile(
    r"(?:[A-ZÄÖÜ][\wäöüßÄÖÜ'.]*[\s\-]){0,3}[A-ZÄÖÜ]?[\wäöüßÄÖÜ\-]*" + _STRASSEN_ENDUNG + r"\.?"
    r"|(?:Am|An der|An den|An dem|Auf der|Auf dem|Auf den|Im|In der|In den|In dem|Zum|Zur|Hinter der|Hinter dem|"
    r"Hinter den|Unter den|Unter der|Vor dem|Vor den|Über der|Bei der|Platz der|Platz des|Alt|Neue|Alte|Obere|"
    r"Untere|Kleine|Große|Lange|Hohe)[\s\-](?:[A-ZÄÖÜ][\wäöüßÄÖÜ\-]+[ ]){0,2}[A-ZÄÖÜ][\wäöüßÄÖÜ\-]+",
    re.IGNORECASE)
_HAUSNUMMER_VORN_RE = re.compile(r"[ \t]*(\d{1,4}(?:[ ]?[a-zA-Z])?)(?![\w.])")
# ganze Zelle in Betragsform ohne Nachkommastellen ("7.712.345") – unter einem Kennungs-Spaltenkopf eine Nummer
_BETRAGSFORM_ZELLE_RE = re.compile(r"\d{1,3}(?:\.\d{3})+")
# Wörter, mit denen ein Straßenname beginnen kann, die aber auch gewöhnliche Wörter sind ("Straße des 17. Juni")
_STRASSEN_ANFANG = frozenset({"straße", "strasse", "str", "platz", "weg", "allee", "gasse", "ring", "damm", "ufer",
                              "chaussee", "am", "an", "auf", "im", "in", "zum", "zur", "unter", "hinter", "vor",
                              "alt", "alte", "alter", "neue", "neuer", "obere", "untere", "kleine", "große", "lange",
                              "hohe", "hoher"})
_POSTFACH_RE = re.compile(r"(?i)(?<![\w])Postfach[ \t:]+(\d[\d ]{2,10}\d)")
_PLZ_ORT_RE = re.compile(r"(?<![\w\-/.,])(?:D[-\s])?(\d{5})[ \t]{1,2}([A-ZÄÖÜ][\wäöüßÄÖÜ.\-]+"
                         r"(?:[ \t](?:am|an|im|in|bei|ob|v\.|vor|der|d\.|a\.|i\.|"
                         r"[A-ZÄÖÜ(][\wäöüßÄÖÜ.\-)]*)){0,4})")
# Ort-Datum-Zeile ("Tübingen, 14. Januar 2025", "St. Ingbert, 11.08.2025") – Gruppe 1: der Ort
_ORT_DATUM_RE = re.compile(r"(?:^|(?<=\t))[ ]*((?:[A-ZÄÖÜ][\wäöüßÄÖÜ.\-]*|St\.)"
                           r"(?:[ ](?:am|an|im|in|bei|ob|der|v\.|d\.|i\.|[A-ZÄÖÜ(][\wäöüßÄÖÜ.\-)]*)){0,4}),[ ]?"
                           r"(?:den\s+)?\d{1,2}\.\s?(?:\d{1,2}\.\s?\d{2,4}|[A-ZÄÖÜa-zäöü]+\.?\s\d{4})")

# Datumsformen (Tag, Monat, Jahr) und Bereiche
_DATUM_RES = (
    (re.compile(r"(?<![\d.,/])(\d{1,2})\.[ ]?(\d{1,2})\.[ ]?(\d{4}|\d{2})(?![\d]|\.\d)"), "tmj"),
    (re.compile(r"(?<![\d.,/-])(\d{4})-(\d{1,2})-(\d{1,2})(?![\d])"), "jmt"),
    (re.compile(r"(?<![\d.,/])(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})(?![\d/])"), "tmj"),
    (re.compile(r"(?<![\d.])(\d{1,2})\.?[ ]?(Jan(?:uar)?|Jänner|Feb(?:ruar)?|März|Mär|Maerz|Apr(?:il)?|Mai|"
                r"Juni?|Juli?|Aug(?:ust)?|Sept?(?:ember)?|Okt(?:ober)?|Nov(?:ember)?|Dez(?:ember)?)\.?[ ]?"
                r"(\d{4})(?![\d])", re.IGNORECASE), "tMj"),
)
# OCR: Datum mit einer angehängten Ziffer (Tabellenlinie oder Fleck als Ziffer gelesen: "01.07.20836") – und mitten in
# einer Ziffernfolge oder mit verlesenem Trenner ("120.01.2025" mit "|" als "1" davor, "01.04:2022")
_DATUM_OCR_RES = ((re.compile(r"(?<![\d.,/])(\d{1,2})\.(\d{1,2})\.(\d{4})\d(?![\d])"), "tmj"),
                  (re.compile(r"(\d{1,2})[.:,](\d{1,2})[.:,](\d{4})(?![\d])"), "tmj"))
# Form eines Datums (auch ungültig verlesen: "0.04.2025", "06.36.1896") – keine Telefon- oder Kennnummer
_DATUMSFORM_RE = re.compile(r"\d{1,2}[.:,]\d{1,2}[.:,](?:\d{2}|\d{4,5})|(?:0?[1-9]|1[0-2])[.:/](?:19|20)\d{2}")
# … davon nur die Formen, die ein Datum sein KÖNNEN: Tag bis 31, Monat bis 12 (auf der Textebene vierstelliges Jahr
# 19xx/20xx, auf OCR-Zeilen auch zwei- oder fünfstellig verlesen) – oder Monat/Jahr ("08.1987")
_DATUMSFORM_TMJ_RE = re.compile(r"(\d{1,2})[.:,](\d{1,2})[.:,](\d{2}|\d{4,5})")
_MONAT_JAHR_RE = re.compile(r"(?:0?[1-9]|1[0-2])[.:/](?:19|20)\d{2}")
# Monat/Jahr als Partner eines Zeitraums ("08.1987 31.12.1989"), auf OCR-Zeilen auch ein verlesenes Datum
_MONAT_JAHR_IN_ZEILE_RE = re.compile(r"(?<![\d.,/])(?:0?[1-9]|1[0-2])[./](?:19|20)\d{2}(?![\d]|[.,/]\d)")
_DATUM_VERLESEN_RE = re.compile(r"(?<![\d])\d{1,2}[.,:]{1,2}\d{1,2}[.,:]{1,2}\d{2,5}(?![\d])")
_OCR_RAND = " \t‚„,.'’`´|;:"           # Krümel der OCR vor/hinter einem Wert ("‚01.12.1990")
# Diagnosekontext für Diagnoseschlüssel ohne Buchstaben ("125.11" als OCR-Lesung von "I25.11")
_DIAGNOSE_RE = re.compile(r"(?i)diagnos|icd|befund|krankheit|erkrankung|syndrom|störung|leiden|beschwerden|"
                          r"hypertonie|insuffizienz|fraktur|arthrose|entzündung|infekt")
# Geburtsjahr hinter seinem Etikett ("Geburtsjahr: 1983", "Geb.-Jahr 1979", "Geburtsjahr der versicherten Person:
# 1979", "Jahrgang 1961", "Jg. 1961") – dieselben Etiketten wie die Erkennung (muster._JAHRGANG_RE)
_GEBURTSJAHR_RE = re.compile(
    r"(?<![\wäöüß])(?:(?i:jg\.|jahrgang)[ \t]*|(?i:geburtsjahr(?:gang)?|geb\.-?[ \t]?jahr)"
    r"(?:[ \t]+(?:des|der)[ \t]+[^\W\d_]+(?:[ \t]+[^\W\d_]+)?)?[ \t]*:?[ \t]*)((?:19|20)\d{2})(?![\d/\-]|[.,]\d)")
# Datum direkt an einer Person (Familienkontext): Trenner zwischen Name/Platzhalter und Datum
_FAMILIE_TRENNER_RE = re.compile(r"(?:[ \t]*(?:,|\(|\*)[ \t]*|[ \t]*\t[ \t]*|[ \t]+[-–][ \t]+|[ \t]+)$")
_PERSON_PLATZHALTER_ENDE_RE = re.compile(r"\[(?:PERSON|P|FAMILIE|F|NAME)\b[^\]\n]{0,12}\]$")
_BEREICH_DANACH_RE = re.compile(r"^\s?(?:-|–|—|bis(?:\s+zum)?|to)\s?\d")
_BEREICH_DAVOR_RE = re.compile(r"(?:-|–|—|\bbis(?:\s+zum)?|\bvon|\bvom|\bab|\bseit|\bzwischen|\bperiod)\s?$",
                               re.IGNORECASE)
_UHRZEIT_RE = re.compile(r"(?<![\d.:])\d{1,2}[:.]\d{2}(?::\d{2})?\s?(?:Uhr|h\b)"
                         r"|(?<![\d.:])\d{1,2}:\d{2}(?::\d{2})?(?![\d])")
_BETRAG_RE = re.compile(r"(?<![\d.,])(?!0\d)(?:\d{1,3}(?:\.\d{3})+,\d{1,2}|\d{1,3}(?:\.\d{3})+(?![.,]?\d)"
                        r"|\d+,\d{1,2}|\d+,[-–]{1,2})(?![\d])")
_PARAGRAF_RE = re.compile(r"(?:§§?|Art\.|Artikel|Abs\.|Absatz)\s?\d+[a-z]?(?:\s?(?:Abs\.|Satz|S\.|Nr\.|Ziff\.|"
                          r"lit\.)\s?\d+[a-z]?)*")
_JAHRESBEREICH_RE = re.compile(r"(?<![\d])(?:19|20)\d{2}\s?[/\-–]\s?(?:19|20)?\d{2}(?![\d])")
_PROZENT_RE = re.compile(r"\d+(?:,\d+)?\s?%")
# Diagnoseschlüssel nach ICD-10 ("I25.11", "S93.40") – die OCR liest den Buchstaben oft als Ziffer oder Klammer
_ICD_RE = re.compile(r"\(?[A-Z0-9(]\d{2}\.\d{1,2}[A-Z!*+]?\)?")
# Kennungsartige Zeichenfolgen (Buchstaben/Ziffern mit inneren Trennern)
_TOKEN_RE = re.compile(r"[0-9A-Za-zÀ-ÖØ-öø-ɏ]+(?:(?:[./\-]|(?<=\d):(?=\d))[0-9A-Za-zÀ-ÖØ-öø-ɏ]+)*")
_LUECKE_KETTE = frozenset(" /-()")
_IBAN_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z]{2}[ ]?\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,4})?)"
                      r"(?![A-Za-z0-9])")
_IBAN_DE_LOSE_RE = re.compile(r"(?<![A-Za-z0-9])(DE[ ]?\d{2}(?:[ ]?\d){18})(?![0-9])")
# IBAN in Kästchen (Kammfeld eines gedruckten Formulars): jedes Zeichen einzeln, Gruppen durch Spaltentrenner
_IBAN_KAMM_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z][ \t]{1,3}[A-Z](?:[ \t]{1,3}\d){2}(?:[ \t]{1,3}[A-Z0-9]){10,30})"
                           r"(?![A-Za-z0-9])")
# … von der OCR gelesen: handschriftlich in Kästchen, die Kästchen verschmelzen und Ziffern werden zu Buchstaben
# ("D/E  6 9 j0 3 8 8  5i2 4 3") – eine deutsche IBAN, auch wenn nur ein Teil lesbar ist (_kamm_iban_ocr)
_IBAN_KAMM_OCR_RE = re.compile(r"(?<![A-Za-z0-9])(D[ \t/|.]{0,3}E(?:[ \t]{1,3}[0-9OoQDIl|!ijJSsBZz]{1,3}){4,})"
                               r"(?![A-Za-z0-9])")
_ZIFFERNAEHNLICH = str.maketrans("OoQDIl|!ijJSsBZz", "0000111111155822")
_GLAEUBIGER_ID_RE = re.compile(r"[A-Z]{2}\d{2}\s?ZZZ")
_GLAEUBIGER_ETIKETT_RE = re.compile(r"(?i)Gläubiger[\s-]?(?:ID|Identifikations(?:nummer)?|Ident(?:nummer)?)"
                                    r"(?:[\s-]?Nr\.?)?[\s.:#]*$")
_SVNR_RE = re.compile(r"(?<![\dA-Za-z])(\d{2}[ ]?\d{6}[ ]?[A-Za-z][ ]?\d{2}[ ]?\d)(?![\dA-Za-z])")
_KVNR_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z][ ]?\d{3}[ ]?\d{3}[ ]?\d{3})(?![A-Za-z0-9])")
_FIN_RE = re.compile(r"(?<![A-Za-z0-9])((?=[A-HJ-NPR-Z0-9]{17}(?![A-Za-z0-9]))(?=[A-HJ-NPR-Z0-9]*\d)"
                     r"(?=[A-HJ-NPR-Z0-9]*[A-HJ-NPR-Z])[A-HJ-NPR-Z0-9]{17})")
_KARTE_RE = re.compile(r"(?<![\d])((?:\d{4}[ \-]?){3}\d{1,4}|\d{4}[ \-]?\d{6}[ \-]?\d{5})(?![\d])")
_KFZ_RE = re.compile(r"(?<![\wÄÖÜäöü\-/.])([A-ZÄÖÜ]{1,3})([- ])([A-Z]{1,2})[ ]?(\d{1,4})([EH])?(?![\w\-/.])")
_KFZ_SPERRE = frozenset({
    "AVB", "AKB", "AHB", "AGB", "ARB", "AUB", "ABB", "ALB", "BGB", "DIN", "ISO", "SGB", "VVG", "VAG", "HGB",
    "EWG", "VO", "KFZ", "PKW", "LKW", "SF", "PKV", "GKV", "DRV", "BMW", "VW", "ABS", "PDF", "PIN", "TAN", "IBAN",
    "BIC", "BLZ", "TEL", "FAX", "VON", "ZUM", "ZUR", "EU", "UN", "USA", "EDV", "USB", "GPS", "TÜV", "GDV", "BU",
    "KV", "LV", "RV", "KH", "VK", "TK", "HR", "HRB", "HRA", "NR", "AZ", "GZ", "ST", "ART", "IV", "VI", "II",
    "III", "XL", "CO", "UND", "ODER", "DIE", "DER", "DAS", "MIT", "FÜR", "AUF", "AUS", "BEI",
})
_BIC_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z]{4}(?:DE|AT|CH|LI|LU|FR|IT|ES|NL|BE|PL|GB|IE|DK|SE|NO|FI|PT|CZ|SK|HU|"
                     r"HR|SI|RO|BG|GR|TR|US)[A-Z0-9]{2}(?:[A-Z0-9]{3})?)(?![A-Za-z0-9])")
_AUSWEIS_ETIKETT_RE = re.compile(
    r"(?:(?i:Personalausweis|Ausweis|Reisepass|Pass|Führerschein|Fuehrerschein|Aufenthaltstitel|"
    r"Dokumenten|Ausweisdokument|Identitätskarte)[\w\-.]*|(?<![\w-])ID)(?:[\s-]?(?i:Nr\.?|Nummer|No\.?))?"
    r"[\s.:(]*$")
# Kennungen mit eigener Wertform hinter ihrem Etikett – eVB-Nummer, Transferticket, Kartenprüfnummer: Etiketten,
# Wertformen und die Regel "Etikett + Wert" sind dieselben wie in der Erkennung (kennungsformen.py, Gegenprüfung Runde
# 4c: getrennt gebaut hatten beide dieselben Lücken); hier kommen die Kartenangabe des Platzhalters [KREDITKARTE] und
# die eVB mit Einfügungen der Texterkennung dazu ("K7/H3MY9P", auf jeder Zeile: die Ausgabe kann OCR-Text tragen)
_FORM_GRUND = {"evb": "eVB-Nummer", "ticket": "Transferticket", "cvc": "Kartenprüfnummer"}
_KREDITKARTE_PLATZHALTER_RE = re.compile(r"\[KREDITKARTE\]")
# Geburtsname direkt hinter "geb." / "geb:" / "geborene" ("[PERSON A] geb. Quarnstedt", "GEB. QUARNSTEDT") – nicht
# "Gebr." (Gebrüder), nicht "Geb." am Satz-/Zeilenanfang (Gebäude, Gebühr), nicht über eine Spaltenlücke
_GEBURTSNAME_DAVOR_RE = re.compile(
    r"(?:(?<![\wäöüß.\-])(?:geb|GEB)(?:\.:?|:|,)?|(?<=[A-Za-zÄÖÜäöüß\]][ ])Geb\.|(?<=[A-Za-zÄÖÜäöüß\]],[ ])Geb\.|"
    r"(?<![\wäöüß])(?P<geborene>geborene[rn]?|GEBORENE[RN]?|Geborene[rn]?)"
    # "gab." – so liest die Texterkennung "geb." ("[PERSON A] gab. Quarnstedt"); nur zwischen zwei Namen
    r"|(?<=[A-Za-zÄÖÜäöüß\]][ ])(?P<gab>gab|GAB)\.)"
    # Leerzeichen dahinter – direkt hinter "geb." / "geb:" auch keines ("geb.Quarnstedt")
    r"(?:[ ]{1,3}|(?<=[.:]))(?:(?:von|van|de|der|den|zu|zur|vom|ten|ter|da|di|dos|del|du|la|le|"
    r"VON|VAN|DE|DER|DEN|ZU|ZUR|VOM)[ ]+){0,2}$")
# Füllwörter hinter "geb." sind kein Geburtsname ("Familienstand: geb. Ledig", "Weber geb. Unbekannt")
_GEBURTSNAME_FUELLWORT = frozenset({"siehe", "wie", "keiner", "keine", "kein", "unbekannt", "entfällt", "entfaellt",
                                    "ledig", "verheiratet", "geschieden", "verwitwet", "gleich", "identisch", "dito",
                                    "nein", "ja", "ohne", "nicht", "oben", "unten"})
# hinter dem Wort geht ein Datum weiter ("geb. Mai 1980", "geb. Od. Dez. 1973" – OCR für "04. Dez. 1973")
_DATUM_DAHINTER_RE = re.compile(r"[ \t]*(?:\d|\.[ \t]*(?:\d|(?i:" + "|".join(sorted(_MONATE, key=len, reverse=True))
                                + r")(?![\wäöüß])))")
_URL_RE = re.compile(r"(?i)(?<![\w@])((?:https?://|www\.)[\w\-.~/%?#=&+]+|[\w\-]+\.(?:de|com|net|org|eu|info)"
                     r"(?:/[\w\-./~%?#=&+]*)?)(?![\w@])")
_EMAIL_RE = re.compile(r"(?<![\w.+\-])([\w.+\-ÄÖÜäöüß]+)\s?(?:@|\(at\)|\[at\])\s?"
                       r"([\w\-ÄÖÜäöüß]+(?:\s?\.\s?[\w\-]+)+)", re.IGNORECASE)
_PLUS_CC_RE = re.compile(r"(?<![\w+])\+\s?\d{1,3}[\s(/\-]{0,3}\d")
_NAMENSWORT_RE = re.compile(r"[^\W\d_](?:[^\W\d_]|['’](?=[^\W\d_]))*(?:-[^\W\d_](?:[^\W\d_]|['’](?=[^\W\d_]))*)*")
_PLATZHALTER_RE = re.compile(r"\[[A-ZÄÖÜẞ0-9][A-ZÄÖÜẞ0-9 .,/&+\-]{0,38}\]")
_PERSONEN_PLATZHALTER_RE = re.compile(r"\[(?:PERSON|P|FAMILIE|F|NAME)\b")
_ANSCHRIFT_PLATZHALTER_RE = re.compile(r"\[(?:ADRESSE|PLZ|STRASSE|ORT)\b")
# Bruchstücke von Platzhaltern, wie die OCR sie liest ("PERS", "ORTI", "[PLZ")
_PLATZHALTER_WOERTER = ("PERSON", "FAMILIE", "ADRESSE", "STRASSE", "TELEFON", "VERTRAGS", "GEB-DATUM", "DATUM",
                        "KENNZEICHEN", "AUSWEIS", "STEUER", "MANDATSREFERENZ", "KREDITKARTE", "GESCHWÄRZT",
                        "BEGRIFF", "E-MAIL", "KINDERGELD", "PLZ", "ORT", "IBAN", "BIC", "FIN", "SV-NR", "KV-NR")
# Rollen-/Funktionswörter, hinter denen Personennamen stehen (zusätzlich zu den Personen-Etiketten)
_ROLLEN = ("Vorstand", "Vorstände", "Vorstandsvorsitzender", "Vorstandsvorsitzende", "Aufsichtsrat",
           "Vorsitz Aufsichtsrat", "Vorsitzender des Aufsichtsrats", "Vorsitzende des Aufsichtsrats",
           "Aufsichtsratsvorsitzender", "Aufsichtsratsvorsitzende", "Geschäftsführer", "Geschäftsführerin",
           "Geschäftsführung", "Inhaber", "Inhaberin", "Prokurist", "Prokuristin", "Sachbearbeiter",
           "Sachbearbeiterin", "Ansprechpartner", "Ansprechpartnerin", "Bearbeiter", "Bearbeiterin",
           "Unterschrift", "gez.", "i. A.", "i.A.", "i. V.", "i.V.", "ppa.", "per pro", "Name", "Vorname",
           "Nachname", "Zeuge", "Zeugin", "Gutachter", "Gutachterin", "Sachverständiger", "Arzt", "Ärztin",
           "Vertreten durch", "vertreten durch")
# typische Endungen deutscher Substantive/Partizipien – unbekannte Wörter damit sind keine Namen
_NOMEN_ENDUNG = re.compile(r"(?i)(?:ung|ungen|heit|keit|schaft|tion|tionen|ität|ismus|nis|tum|ender|ende|ierte|"
                           r"ierter|ierten|isch|ische|lich|liche|chen|schein|zeichen|nummer|datum|summe|betrag|"
                           r"beitrag|vertrag|stelle|erin|innen)$")
_ORG_ENDWORT = re.compile(r"(?i)-(?:straße|strasse|str|weg|platz|allee|ring|damm|ufer|gasse|brücke|park|center|haus|"
                          r"schule|klinik|klinikum|institut|stiftung|gymnasium|apotheke|zentrum|kaserne|halle|"
                          r"stadion|preis|medaille|gesetz|verordnung|rente|plan|programm|modell|tarif)$")
_TITEL_KURZ = frozenset({"herr", "herrn", "frau", "fr", "hr", "dr", "prof", "dipl", "ing", "mag", "lic"})
_AKADEMISCH = frozenset({"med", "rer", "nat", "jur", "phil", "dent", "vet", "pol", "oec", "habil", "dipl", "ing",
                         "kfm", "sc", "techn", "theol", "agr", "h", "c", "univ", "mult"})
# Kürzel und Zeichen von Firmen-, Kanzlei- und Praxiszeilen ("Berger & Kollegen", "Co. KG", "LL.M.", "e.K."), ohne
# Punkte und klein: keine Personenangabe (Unterschriftsblöcke und Personenangaben auf Scans)
_KUERZEL = frozenset({"&", "+", "co", "cie", "llm", "llb", "mba", "msc", "bsc", "ma", "ba", "phd", "ek", "ev", "eg",
                      "dres", "partg", "partgmbb", "mbb", "ggmbh", "inh", "jun", "jr", "sen", "sr", "ua"})
# Wörter von Grußformeln (auch als eigene Zeile, wenn das Seitenmodell eine schräge Formel zerlegt)
_GRUSS_WOERTER = frozenset({"mit", "freundlichen", "freundlichem", "freundliche", "grüßen", "grüssen", "grüße",
                            "grüsse", "gruß", "gruss", "besten", "beste", "herzlichen", "herzliche", "lieben", "liebe",
                            "vielen", "viele", "kollegialen", "verbindlichen", "schöne", "hochachtungsvoll", "mfg"})
# Organisationseinheiten und Himmelsrichtungen in Funktionszeilen ("Hauptagentur Nord", "Filialdirektion Süd"), die
# die Wissensbasis nicht als Allerweltswörter führt – auch als letztes Glied eines Kompositums
_EINHEITEN = frozenset({"agentur", "hauptagentur", "generalagentur", "bezirksagentur", "direktion", "filialdirektion",
                        "bezirksdirektion", "regionaldirektion", "landesdirektion", "niederlassung", "kanzlei",
                        "sozietät", "partnerschaft", "gemeinschaftspraxis", "kollegen", "kolleginnen", "nord", "süd",
                        "ost", "west", "mitte", "nordost", "nordwest", "südost", "südwest",
                        # Sparten in Abteilungszeilen ("Leistungsabteilung Kranken", "Schadenservice Kfz")
                        "kranken", "leben", "sach", "kfz", "kraftfahrt", "unfall", "haftpflicht", "rechtsschutz",
                        "hausrat", "wohngebäude", "pflege", "komposit", "vorsorge"})
_AUFTRAG_RE = re.compile(r"(?i)(?<![\w.])(?:i\.\s?[av]\.|ppa\.|gez\.|pp\.)")
# OCR: großes I am Wortanfang als kleines l gelesen ("llir", "lrina") – kein deutsches Wort beginnt mit l + Konsonant
_OCR_KLEIN_L_RE = re.compile(r"l[bcdfghjklmnpqrstvwxzß]")
# OCR: Buchstaben, deren Groß- und Kleinform gleich aussehen – direkt hinter Anrede/Titel liest die OCR "schüßler"
_FORMGLEICH_KLEIN = frozenset("ckopsuvwxz")
# OCR: zwei Wörter ohne Leerzeichen zusammengelesen ("LukasKrause")
_ZUSAMMEN_RE = re.compile(r"([A-ZÄÖÜ][a-zäöüß]{2,})([A-ZÄÖÜ][a-zäöüß]{2,})")
GRUSS_ZEILEN = 4               # so viele Zeilen unter einer Grußformel gehören zum Unterschriftsblock (Namensregel)
# Geschäftsbezeichnungen, hinter denen oft der Familienname des Inhabers steht ("Werkstatt Weiß", "Bäckerei Hofmeister")
_GESCHAEFTE = frozenset({
    "werkstatt", "autowerkstatt", "kfz-werkstatt", "autohaus", "firma", "fa.", "bäckerei", "metzgerei", "fleischerei",
    "konditorei", "malerbetrieb", "malermeister", "schreinerei", "tischlerei", "zimmerei", "dachdeckerei", "glaserei",
    "gärtnerei", "lackiererei", "karosseriebau", "spedition", "bauunternehmen", "baufirma", "elektro", "sanitär",
    "heizungsbau", "hausverwaltung", "immobilien", "gaststätte", "restaurant", "café", "pension", "hotel",
    "reisebüro", "fahrschule", "pflegedienst", "apotheke", "kanzlei", "praxis", "zahnarztpraxis", "physiotherapie",
    "ingenieurbüro", "architekturbüro", "steuerbüro", "gutachterbüro", "sachverständigenbüro", "maklerbüro",
    "versicherungsbüro", "abschleppdienst", "schlüsseldienst", "autovermietung", "optik", "friseur", "salon"})
_UMLAUT_GRUND = {"ä": "a", "ö": "o", "ü": "u", "Ä": "A", "Ö": "O", "Ü": "U"}
# Formularwerte ohne Personenbezug, die stehen bleiben (Familienstand laut Handbuch, Geschlecht wie die Anrede) –
# eine geschlossene Liste: Staatsangehörigkeit, Konfession, Gesundheit, Namen und Orte gehören nie dazu
_MERKMALE = frozenset({"ledig", "verheiratet", "geschieden", "verwitwet", "getrennt", "getrennt lebend",
                       "dauernd getrennt lebend", "eingetragene lebenspartnerschaft", "lebenspartnerschaft",
                       "verpartnert", "aufgehobene lebenspartnerschaft", "alleinstehend", "männlich", "weiblich",
                       "divers", "keine angabe", "ohne angabe", "unbekannt"})


def _kuerzel(kern: str) -> bool:
    """Kürzel oder Zeichen einer Firmen-/Kanzleizeile ("&", "+", "Co.", "LL.M.", "e.K.")?"""
    k = re.sub(r"[.\s]", "", kern).lower()
    return bool(k) and (k in _KUERZEL or all(c in "&+" for c in k))


def _grundformen(wort: str) -> list:
    """Mögliche Grundformen eines gebeugten Hauptworts: Endung ab, Umlaut des Stamms zurück ("Rechtsanwälte" ->
    "Rechtsanwalt", "Fachärzte" -> "Facharzt", "Agenturen" -> "Agentur")."""
    aus = []
    for endung in ("innen", "en", "er", "e", "n", "s"):
        if not wort.lower().endswith(endung) or len(wort) - len(endung) < 3:
            continue
        stamm = wort[:-len(endung)]
        aus.append(stamm)
        i = max(stamm.rfind(c) for c in _UMLAUT_GRUND)
        if i >= 0:
            aus.append(stamm[:i] + _UMLAUT_GRUND[stamm[i]] + stamm[i + 1:])
    return aus


# ----------------------------------------------------------------------
# Prüfziffern (eigene Rechnungen – die Restrisiko-Prüfung teilt keinen Code mit der Erkennung)
# ----------------------------------------------------------------------
def iban_gueltig(text: str) -> bool:
    s = re.sub(r"[\s-]", "", text).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{8,30}", s):
        return False
    zahl = "".join(str(int(c, 36)) for c in s[4:] + s[:4])
    return int(zahl) % 97 == 1


def steuer_id_gueltig(text: str) -> bool:
    z = re.sub(r"\D", "", text)
    if len(z) != 11 or z[0] == "0":
        return False
    produkt = 10
    for c in z[:10]:
        summe = (int(c) + produkt) % 10 or 10
        produkt = (2 * summe) % 11
    pruef = 11 - produkt
    return (0 if pruef == 10 else pruef) == int(z[10])


def sv_nummer_gueltig(text: str) -> bool:
    s = re.sub(r"\s", "", text).upper()
    if not re.fullmatch(r"\d{8}[A-Z]\d{3}", s):
        return False
    ziffern = s[:8] + f"{ord(s[8]) - 64:02d}" + s[9:11]
    gewichte = (2, 1, 2, 5, 7, 1, 2, 1, 2, 1, 2, 1)
    summe = sum(sum(divmod(int(c) * g, 10)) for c, g in zip(ziffern, gewichte))
    return summe % 10 == int(s[11])


def kvnr_gueltig(text: str) -> bool:
    s = re.sub(r"\s", "", text).upper()
    if not re.fullmatch(r"[A-Z]\d{9}", s):
        return False
    ziffern = f"{ord(s[0]) - 64:02d}" + s[1:9]
    summe = 0
    for i, c in enumerate(ziffern):
        p = int(c) * (1 if i % 2 == 0 else 2)
        summe += p // 10 + p % 10
    return summe % 10 == int(s[9])


def luhn_gueltig(text: str) -> bool:
    ziffern = [int(c) for c in re.sub(r"\D", "", text)]
    if len(ziffern) < 12:
        return False
    summe = 0
    for i, z in enumerate(reversed(ziffern)):
        if i % 2:
            z *= 2
            if z > 9:
                z -= 9
        summe += z
    return summe % 10 == 0


def icao_gueltig(text: str) -> bool:
    """Prüfziffer (Gewichte 7-3-1) über die Zeichen davor, letzte Stelle = Prüfziffer (Ausweis/Pass)."""
    s = re.sub(r"[\s<]", "", text).upper()
    if len(s) < 8 or not s[-1].isdigit():
        return False
    werte = []
    for c in s[:-1]:
        if c.isdigit():
            werte.append(int(c))
        elif "A" <= c <= "Z":
            werte.append(ord(c) - 55)
        else:
            return False
    return sum(w * (7, 3, 1)[i % 3] for i, w in enumerate(werte)) % 10 == int(s[-1])


# ----------------------------------------------------------------------
# Wissensbasis (Zugriff mit Zwischenspeicher; ohne Wissensbasis bleiben nur die Formregeln)
# ----------------------------------------------------------------------
def _wissen_laden():
    try:
        from . import wissen
        wissen.liste("vornamen")
        return wissen
    except Exception:
        return None


class _Wissen:
    """Einzelwort-Einordnung mit Zwischenspeicher je Lauf (ein Wort wird nur einmal nachgeschlagen)."""

    ARTEN = ("ist_vorname", "ist_nachname", "ist_vorname_mehrdeutig", "ist_mehrdeutig", "ist_allerweltswort",
             "ist_anrede_titel", "ist_allowlist", "ist_partikel")

    def __init__(self, modul):
        self.modul = modul
        self._cache: dict = {}
        self._indizes: dict = {}
        self._etikett_cache: dict = {}
        self._berufswoerter = None

    def _frage(self, name: str, wort: str) -> bool:
        f = getattr(self.modul, name, None) if self.modul is not None else None
        if f is None:
            return False
        try:
            return bool(f(wort))
        except Exception:
            return False

    def art(self, wort: str) -> tuple:
        """(vorname, nachname, vorname_mehrdeutig, nachname_mehrdeutig, allerweltswort, titel, allowlist,
        partikel) eines Worts."""
        a = self._cache.get(wort)
        if a is None:
            a = tuple(self._frage(n, wort) for n in self.ARTEN)
            self._cache[wort] = a
        return a

    def grossstadt(self, wort: str) -> bool:
        """Deutsche Großstadt (wissen.ist_grossstadt)? Ohne Wissensbasis: nein."""
        schluessel = ("grossstadt", wort)
        if schluessel not in self._cache:
            self._cache[schluessel] = self._frage("ist_grossstadt", wort)
        return self._cache[schluessel]

    def frage(self, name: str, wort: str) -> bool:
        """Frage an die Wissensbasis (ist_nachname, ist_ort …) mit Zwischenspeicher; ohne Wissensbasis: nein."""
        schluessel = (name, wort)
        if schluessel not in self._cache:
            self._cache[schluessel] = self._frage(name, wort)
        return self._cache[schluessel]

    def wortgestalt(self, wort: str) -> bool:
        """Ein Wort statt eines Codes ohne Ziffer (wissen.ist_wortgestalt: "ERTEILT", "ALLIANZ", nicht "KXHPMTQ")?
        Ohne Wissensbasis: nein (die Prüfung bleibt vorsichtig)."""
        schluessel = ("wortgestalt", wort)
        if schluessel not in self._cache:
            self._cache[schluessel] = self._frage("ist_wortgestalt", wort)
        return self._cache[schluessel]

    def index(self, art: str):
        """Phrasenindex: Etiketten einer Art ("person", "adresse" …), "rollen", "allowlist", "berufe" oder
        "sachnamen" (oder None)."""
        if art not in self._indizes:
            index = None
            if self.modul is not None:
                try:
                    if art == "rollen":
                        index = self.modul.Phrasenindex(_ROLLEN, name="rollen")
                    elif art == "allowlist":
                        index = self.modul.index("versicherer_und_organisationen")
                    elif art in ("berufe", "sachnamen"):
                        index = self.modul.index(art)
                    else:
                        index = self.modul.index(f"etiketten_{art}")
                except Exception:
                    index = None
            self._indizes[art] = index
        return self._indizes[art]

    def berufswoerter(self) -> frozenset:
        """Wörter der Berufsliste, klein, ab vier Buchstaben – Berufe ("Leiter") und die Wörter mehrteiliger
        Berufsangaben ("Facharzt für Innere Medizin" -> facharzt, innere, medizin). Viele Berufe sind auch
        Familiennamen (Koch, Richter): Namen der Wissensbasis prüft der Aufrufer vorher."""
        if self._berufswoerter is None:
            menge = set()
            try:
                for eintrag in self.modul.liste("berufe") if self.modul is not None else ():
                    menge.update(w.lower() for w in re.findall(r"[^\W\d_]{4,}", eintrag) if w[:1].isupper())
            except Exception:
                pass
            self._berufswoerter = frozenset(menge)
        return self._berufswoerter

    def ist_etikett(self, wort: str) -> bool:
        """Ist das Wort selbst ein Etikett irgendeiner Art ("Makler", "Kennzeichen", "Anschrift")?"""
        e = self._etikett_cache.get(wort)
        if e is None:
            e = False
            arten = ("person", "adresse", "kontakt", "kennung", "datum_geburt", "vertragsdaten", "rollen")
            for art in () if ("[" in wort or "]" in wort) else arten:
                index = self.index(art)
                try:
                    if index is not None and (index.eintrag_fuer(wort) is not None
                                              or index.eintrag_fuer(wort.rstrip(".:")) is not None):
                        e = True
                        break
                except Exception:
                    continue
            self._etikett_cache[wort] = e
        return e


# ----------------------------------------------------------------------
# Kandidaten und Seitenprüfung
# ----------------------------------------------------------------------
class _Kandidat(NamedTuple):
    start: int
    ende: int
    grund: str
    art: str              # form | feld | kontakt | datum | name | anschrift | kennung | etikett | rest


def _heute() -> datetime.date:
    return datetime.date.today()


def _jahr_aus(jahr_text: str) -> int:
    jahr = int(jahr_text)
    if len(jahr_text) == 2:
        heute = _heute().year % 100
        jahr += 1900 if jahr > heute else 2000
    return jahr


def _titel(wort: str) -> str:
    """Versalien in Titelform ("QUARNSTEDT" -> "Quarnstedt") für Fragen an die Wissensbasis."""
    return wort.title() if wort.isupper() else wort


def _ziffern(text: str) -> int:
    return sum(c.isdigit() for c in text)


def _ocr_unsinn(wort: str) -> bool:
    """OCR-Salat wie "ONg" oder "ERarT": mehrere Großbuchstaben, dann klein (keine Schreibweise eines Namens)."""
    return (bool(re.match(r"[A-ZÄÖÜ]{2,}[a-zäöüß]", wort))
            or bool(re.search(r"[a-zäöüß][A-ZÄÖÜ][a-zäöüß]*[A-ZÄÖÜ]", wort)))


def _platzhalter_bruchstueck(wort: str) -> bool:
    """OCR-Bruchstück eines Platzhalters ("PERS", "ORTI]", "[PLZ")?"""
    if "[" in wort or "]" in wort:
        return True
    w = wort.strip("()|!.,:;").upper()
    if len(w) < 3 or not w.isupper():
        return False
    return any(p.startswith(w) or (len(w) >= 4 and w.startswith(p)) for p in _PLATZHALTER_WOERTER)


class _Seitenpruefung:
    """Alle Regeln für EINE Seite des Seitenmodells der Ausgabe."""

    def __init__(self, m, wissen: _Wissen, platzhalter=(), nie=(), abgewaehlt=(), profil: str = "hoch",
                 schwaerzungen=(), ausrichtung=None):
        self.m = m
        self.schwaerzungen = [fitz.Rect(r) for r in schwaerzungen or ()]
        self.text = m.text
        self.w = wissen
        self.profil = profil
        self.kandidaten: list = []
        self._zeilen_text: dict = {}
        self._zeilen_x: dict = {}
        self._org: dict = {}
        self._boxen: dict = {}
        self.gesperrt = self._sperren(platzhalter, nie, abgewaehlt)
        self.platzhalter = [(s, e) for s, e, art in self.gesperrt if art == "platzhalter"]
        self._ph_boxen = None
        self._freie_schwaerzungen: list = []
        self._ausrichtung = ausrichtung        # (Winkel, Schräglage) der OCR-Wörter, falls bekannt
        self._ocr_lage = None
        self._quelle_block = {b.id: b.quelle for b in getattr(m, "bloecke", None) or ()}
        self._org_zellen = None                # {Zeilen-ID: [(start, ende, Art)]} – Zellen in Organisationsbereichen
        self._fusszeilen = None                # Zeilen-IDs des Fußbereichs einer juristischen Person
        self._fusszellen: list = []            # dessen Zellen: (Lese-Rechteck, Zeile, start, ende, Text)

    # -- Gesperrte Bereiche: Platzhalter, NIE-Liste, abgewählte Stellen ----------------------------------
    def _sperren(self, platzhalter, nie, abgewaehlt) -> list:
        text = self.text
        gesperrt = [(m.start(), m.end(), "platzhalter") for m in _PLATZHALTER_RE.finditer(text)]
        for p in platzhalter or ():
            p = str(p or "").strip()
            i = text.find(p) if p else -1
            while i >= 0:
                gesperrt.append((i, i + len(p), "platzhalter"))
                i = text.find(p, i + len(p))
        for art, liste, modi in (("nie", nie, ("begriff", "name")), ("abgewaehlt", abgewaehlt, ("begriff", "kennung"))):
            for phrase in liste or ():
                phrase = str(phrase or "").strip()
                if not phrase:
                    continue
                for modus in modi:
                    try:
                        gesperrt += [(s, e, art) for s, e in sm.ganzwort_stellen(self.m, phrase, modus)]
                    except Exception:
                        pass
        return sorted(gesperrt)

    def ist_gesperrt(self, s: int, e: int) -> bool:
        for gs, ge, _ in self.gesperrt:
            if gs >= e:
                break
            if ge > s:
                return True
        return False

    def ist_platzhalter_bei(self, s: int, e: int) -> bool:
        return any(ps < e and pe > s for ps, pe in self.platzhalter)

    # -- Geometrie ------------------------------------------------------------------------------------
    def box(self, s: int, e: int):
        """Umschließendes Rechteck einer Textstelle (über die Glyphen) oder None."""
        schluessel = (s, e)
        if schluessel not in self._boxen:
            r = None
            try:
                for teil in self.m.rechtecke(s, e):
                    r = fitz.Rect(teil[1]) if r is None else r | teil[1]
            except Exception:
                r = None
            self._boxen[schluessel] = r
        return self._boxen[schluessel]

    def platzhalter_boxen(self) -> list:
        """[(start, ende, (x0, y0, x1, y1) des Platzhalters bzw. des grauen Schwärzungsrechtecks um ihn)]."""
        if self._ph_boxen is None:
            self._ph_boxen = []
            rechtecke = [(r.x0, r.y0, r.x1, r.y1) for r in self.schwaerzungen]
            belegt = set()
            for s, e in self.platzhalter:
                b = self.box(s, e)
                if b is None:
                    continue
                mx, my = (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2
                rand = (b.x0, b.y0, b.x1, b.y1)
                for k, (x0, y0, x1, y1) in enumerate(rechtecke):
                    if x0 <= mx <= x1 and y0 <= my <= y1:
                        rand = (min(rand[0], x0), min(rand[1], y0), max(rand[2], x1), max(rand[3], y1))
                        belegt.add(k)
                self._ph_boxen.append((s, e, rand))
            self._freie_schwaerzungen = [r for k, r in enumerate(rechtecke) if k not in belegt]
        return self._ph_boxen

    @staticmethod
    def _benachbart(b, r, faktor: float) -> bool:
        """Liegen die Box b (fitz.Rect) und das Rechteck r (Tupel) auf derselben Zeilenhöhe direkt nebeneinander?"""
        x0, y0, x1, y1 = r
        ueberlapp = min(b.y1, y1) - max(b.y0, y0)
        if ueberlapp < 0.5 * min(b.y1 - b.y0, y1 - y0):
            return False
        luecke = x0 - b.x1 if x0 >= b.x1 - 1 else b.x0 - x1
        return -1.0 <= luecke <= faktor * max(b.y1 - b.y0, 4.0)

    def neben_platzhalter(self, s: int, e: int, nur=None):
        """Platzhalter (start, ende) direkt links/rechts der Stelle – im Text (nur Leerzeichen/Bindestrich
        dazwischen) oder auf der Seite (gleiche Zeilenhöhe, kleine Lücke zum grauen Rechteck des Platzhalters:
        OCR-Wort neben Platzhalter, Formularwert in eigenem Block)."""
        text = self.text
        for ps, pe in self.platzhalter:
            if nur is not None and not nur.match(text[ps:pe]):
                continue
            if 0 <= s - pe <= 2 and set(text[pe:s]) <= {" ", "-"}:
                return ps, pe
            if 0 <= ps - e <= 2 and set(text[e:ps]) <= {" ", "-", ","}:
                return ps, pe
        boxen = self.platzhalter_boxen()
        if not boxen:
            return None
        b = self.box(s, e)
        if b is None:
            return None
        for ps, pe, rand in boxen:
            if (nur is None or nur.match(text[ps:pe])) and self._benachbart(b, rand, 0.8) \
                    and self._nichts_dazwischen(s, e, b, rand):
                return ps, pe
        return None

    def _nichts_dazwischen(self, s: int, e: int, b, rand) -> bool:
        """Steht in der eigenen Zeile kein anderes Wort zwischen der Stelle und dem Rechteck rand?"""
        z = self.zeile(s)
        if z is None:
            return True
        x0, _, x1, _ = rand
        links = x1 <= b.x0 + 1                       # das Rechteck liegt links der Stelle
        for m in re.finditer(r"\S+", self.text[z.start:z.ende]):
            ms, me = z.start + m.start(), z.start + m.end()
            if ms <= s < me or (ms < e and me > s):
                continue
            wb = self.box(ms, me)
            if wb is None:
                continue
            # ein Wort, das zu einem guten Teil in der Lücke zwischen Rechteck und Stelle liegt
            if links and min(wb.x1, b.x0) - max(wb.x0, x1) >= 2.0:
                return False
            if not links and min(wb.x1, x0) - max(wb.x0, b.x1) >= 2.0:
                return False
        return True

    def an_schwaerzung(self, s: int, e: int) -> bool:
        """Berührt die Stelle (Textebene) ein graues Schwärzungsrechteck ohne Wortabstand – ein mitten im Wort
        abgeschnittener Wert ("D-LL50" geschwärzt, "-WXV09-07" stehen geblieben)?"""
        if not self.schwaerzungen:
            return False
        b = self.box(s, e)
        if b is None:
            return False
        for r in self.schwaerzungen:
            ueberlapp = min(b.y1, r.y1) - max(b.y0, r.y0)
            if ueberlapp < 0.6 * min(b.height, r.height):
                continue
            ueber = -0.6 * b.width                 # Reste ragen oft ein Stück unter das graue Rechteck
            if ueber <= b.x0 - r.x1 <= 1.0 or ueber <= r.x0 - b.x1 <= 1.0:
                return True
        return False

    def neben_schwaerzung(self, s: int, e: int) -> bool:
        """Grenzt die Stelle auf derselben Zeilenhöhe direkt an ein Schwärzungsrechteck ohne Platzhalter?"""
        if not self.schwaerzungen:
            return False
        self.platzhalter_boxen()
        if not self._freie_schwaerzungen:
            return False
        b = self.box(s, e)
        return b is not None and any(self._benachbart(b, r, 0.8) for r in self._freie_schwaerzungen)

    # -- Zeilen und Spalten -------------------------------------------------------------------------
    def _quelle(self, pos: int) -> str:
        """Herkunft des Zeichens an pos: "text" (Textebene) oder "ocr"/"bild"."""
        abb = self.m.abbildung
        if 0 <= pos < len(abb) and abb[pos] >= 0:
            return self.m.zeichen[abb[pos]].quelle
        return "text"

    def zeile(self, pos: int):
        return self.m.zeile_von(pos)

    def zeilen_text(self, z) -> str:
        t = self._zeilen_text.get(z.id)
        if t is None:
            t = self.text[z.start:z.ende]
            self._zeilen_text[z.id] = t
        return t

    def zeichen_x(self, z) -> list:
        """[(Textindex, x-Mitte)] der sichtbaren Zeichen einer Zeile."""
        aus = self._zeilen_x.get(z.id)
        if aus is None:
            aus = []
            abb, zeichen = self.m.abbildung, self.m.zeichen
            for i in range(z.start, min(z.ende, len(abb))):
                g = abb[i]
                if g >= 0 and not self.text[i].isspace():
                    r = zeichen[g].rect
                    aus.append((i, (r.x0 + r.x1) / 2))
            self._zeilen_x[z.id] = aus
        return aus

    def zelle_ueber(self, z, x0: float, x1: float) -> tuple:
        """(Text, start, ende) der Zeile z im x-Bereich [x0, x1] (eine Tabellenzelle)."""
        teile = [i for i, xm in self.zeichen_x(z) if x0 - 2 <= xm <= x1 + 2]
        if not teile:
            return "", 0, 0
        s, e = min(teile), max(teile) + 1
        text = self.text
        trenner = "\t" if "\t" in text[z.start:z.ende] else " "
        while s > z.start and text[s - 1] != trenner and not (trenner == "\t" and text[s - 2:s] == "  "):
            s -= 1
        while e < z.ende and text[e] != trenner and not (trenner == "\t" and text[e:e + 2] == "  "):
            e += 1
        return text[s:e], s, e

    def zeilen_oberhalb(self, z, anzahl: int):
        """Zeilen über z (nächste zuerst), nach der Lage auf der Seite. Die Zeilen der Seite sind einmal nach ihrer
        Unterkante geordnet (Gegenprüfung Runde 4c: neu sortiert je Aufruf wuchs die Spaltenprüfung quadratisch)."""
        if z is None or z.rect is None:
            return []
        ordnung = self._org.get("nach_unterkante")
        if ordnung is None:
            reihe = sorted((y for y in self.m.zeilen if y.rect is not None), key=lambda y: -y.rect.y1)
            ordnung = ([-y.rect.y1 for y in reihe], reihe)
            self._org["nach_unterkante"] = ordnung
        schluessel, reihe = ordnung
        aus = []
        for y in reihe[bisect_left(schluessel, -(z.rect.y0 + 1)):]:
            if y.id != z.id:
                aus.append(y)
                if len(aus) >= anzahl:
                    break
        return aus

    def zeilen_links(self, s: int, e: int) -> list:
        """Zeilen links der Stelle auf derselben Zeilenhöhe (Formular: Etikett links, Wert rechts – im Modell der
        Ausgabe stehen eingebrannte Formularwerte oft in eigenen Blöcken), nächste zuerst."""
        b = self.box(s, e)
        if b is None:
            return []
        aus = []
        for y in self.m.zeilen:
            r = y.rect
            if r is None or r.x1 > b.x0 + 1:
                continue
            ueberlapp = min(r.y1, b.y1) - max(r.y0, b.y0)
            if ueberlapp >= 0.5 * min(r.height, b.height):
                aus.append((b.x0 - r.x1, y))
        return [y for _, y in sorted(aus, key=lambda t: t[0])]

    def org_kontext(self, pos: int) -> bool:
        """Steht die Stelle in einem Organisationsbereich (_org_bereiche: Fußbereich einer juristischen Person,
        Briefkopf oder Anschrift einer Organisation, Zelle mit Organisationsmerkmal) – auch im Fußbereich nicht hinter
        einem Anschrift-/Personen-/Kontakt-Etikett ("Anschrift: 27568 Bremerhaven" ist ein Formularwert, "Mobil:
        0171 …" über den Pflichtangaben ein Kundenwert)?"""
        z = self.zeile(pos)
        if z is None:
            return False
        self._org_bereiche()
        if z.id in self._fusszeilen:
            return not self._etikett_im_segment(z, pos)
        if not any(s <= pos < e for s, e, _ in self._org_zellen.get(z.id, ())):
            return False
        return not self._etikett_vor(z, pos)

    def im_fussbereich(self, pos: int) -> bool:
        """Steht die Stelle im Fußbereich einer juristischen Person (Pflichtangaben, Bankverbindung)?"""
        z = self.zeile(pos)
        if z is None:
            return False
        self._org_bereiche()
        return z.id in self._fusszeilen

    def org_konto(self, pos: int) -> bool:
        """Ist die IBAN an pos die Bankverbindung der Organisation: im Fußbereich einer juristischen Person hinter
        einer Bankangabe ("Bankverbindung", Name einer Bank) in derselben Zelle oder der Zelle direkt darüber – nicht
        hinter einem Personen-, Anschrift- oder Kontakt-Etikett und ohne Besitz- oder Kundenwort davor ("Ihre IBAN",
        "von Ihrem Konto", "Kontoinhaber")?"""
        z = self.zeile(pos)
        if z is None or not self.im_fussbereich(pos) or self._etikett_im_segment(z, pos):
            return False
        return self._bank_vor(pos)

    def _fusszelle(self, pos: int):
        """Zelle des Fußbereichs (Lese-Rechteck, Zeile, start, ende, Text), in der pos steht – oder None."""
        for c in self._fusszellen:
            if c[2] <= pos < c[3]:
                return c
        return None

    def _bank_vor(self, pos: int) -> bool:
        """Steht vor pos (im Fußbereich) eine Bankangabe der Organisation: "Bankverbindung" oder der Name einer Bank in
        derselben Zelle oder in der Zelle direkt darüber (dieselbe Spalte: "Bankverbindung: Kreissparkasse Talheim" /
        "IBAN DE89 …") – ohne Besitz- oder Kundenwort und nicht in einem Satz?"""
        zelle = self._fusszelle(pos)
        if zelle is None:
            return False
        vor = self.text[zelle[2]:pos]
        if _KUNDE_KONTO_RE.search(vor) or _fuss_fliesstext(vor):
            return False
        if _BANKNAME_RE.search(vor):
            return True
        r = zelle[0]
        h = max(r.height, 4.0)
        darueber = [c for c in self._fusszellen if c[0].y1 <= r.y0 + 0.5 * h and r.y0 - c[0].y1 <= 1.5 * h
                    and (min(c[0].x1, r.x1) - max(c[0].x0, r.x0) >= 0.3 * min(c[0].width, r.width)
                         or abs(c[0].x0 - r.x0) <= 2 * h)]
        if not darueber:
            return False
        naechste = max(darueber, key=lambda c: c[0].y1)
        return bool(_BANKNAME_RE.search(naechste[4])) and not _KUNDE_KONTO_RE.search(naechste[4])

    def org_wert(self, pos: int, ende: int) -> bool:
        """Ist die Ziffern-/Zeichenfolge an pos eine Angabe der Organisation selbst – Telefon-, Register-, Steuer-
        und Kontonummern im Fußbereich einer juristischen Person oder in den Zeilen unter dem Namen einer Organisation
        (Briefkopf), nicht in einer Zelle, die eine Organisation nur nennt (Bestandsliste: "Allianz 12345678" ist eine
        Vertragsnummer) – ohne Etikett oder hinter einem Etikett der Organisation (USt-IdNr., Register, BLZ, BIC,
        Steuernummer, Gläubiger-ID; Kontonummer nur in ihrer Bankverbindung). "Kunden-Nr. 4711", "Kundenkonto 98765",
        "Ihr Az. 2024" in einer laufenden Fußzeile bleiben verdächtig, ebenso Werte hinter Personen-, Anschrift- und
        Kontakt-Etiketten."""
        z = self.zeile(pos)
        if z is None:
            return False
        self._org_bereiche()
        im_fuss = z.id in self._fusszeilen
        if not im_fuss and not any(s <= pos < e and art == "block" for s, e, art in self._org_zellen.get(z.id, ())):
            return False
        if self._etikett_im_segment(z, pos) if im_fuss else self._etikett_vor(z, pos):
            return False
        vor = self.text[max(z.start, pos - 40):pos]
        if _UST_ETIKETT_RE.search(vor):
            return True                          # USt-IdNr. der Organisation (auch hinter verlesenem "USt-IdNr.")
        etikett = self.etikett_davor(pos, ende, ("kennung", "person", "datum_geburt"), fenster=30)
        if etikett is None:
            return True
        t = etikett[1].strip()
        if _ORG_ETIKETT_RE.fullmatch(t):
            return True
        # Kontoetikett ("IBAN", "Konto-Nr."): Angabe der Organisation nur in ihrer Bankverbindung im Fußbereich
        return im_fuss and bool(_KONTO_ETIKETT_RE.fullmatch(t)) and self._bank_vor(pos)

    def _etikett_vor(self, z, pos: int) -> bool:
        """Steht vor pos in derselben Zeile ein Anschrift-/Personen-/Kontakt-Etikett mit Doppelpunkt?"""
        vor = self.text[z.start:pos]
        for treffer in re.finditer(r"([^\W\d_][\w./\- ]{1,40}?)\s?:", vor):
            if self._etikett_in(treffer.group(1).split("\t")[-1], ("adresse", "person", "kontakt")):
                return True
        return False

    def _etikett_im_segment(self, z, pos: int) -> bool:
        """Fußbereich: steht vor pos im selben Abschnitt der Zeile (bis zum letzten "·", "|" oder Spaltentrenner) ein
        Anschrift-, Personen- oder Kontakt-Etikett mit Doppelpunkt ("Wohnanschrift: …", "Mobil: …", "Kontoinhaber:
        …")? Die Organe ("Vorstand:", "Vorsitz Aufsichtsrat:") zählen nicht – dahinter stehen Namen, und die prüfen
        die Namensregeln."""
        vor = re.split(r"\t|\s?[·|•]\s?", self.text[z.start:pos])[-1]
        for treffer in re.finditer(r"([^\W\d_][\w./\- ]{1,40}?)\s?:", vor):
            etikett = treffer.group(1).strip()
            if _ORGAN_RE.search(etikett):
                continue
            if self._etikett_in(etikett, ("adresse", "person", "kontakt")) \
                    or self._etikett_in(etikett.split()[0], ("adresse", "person", "kontakt")):
                return True
        return False

    def _org_zeile(self, z) -> bool:
        schluessel = ("zeile", z.id)
        if schluessel not in self._org:
            self._org[schluessel] = self._org_text(self.zeilen_text(z))
        return self._org[schluessel]

    def _org_text(self, text: str) -> bool:
        """Trägt der Text ein Organisationsmerkmal: Rechtsform, Organisationswort ("Versicherung", "Bank" …),
        Eintrag der Allowlist oder eine Pflichtangabe (Registergericht, HRB, USt-IdNr., Vorstand …)?"""
        t = _URL_RE.sub(" ", _EMAIL_RE.sub(" ", text))
        if _RECHTSFORM_RE.search(t) or _ORG_WORT_RE.search(t) or _PFLICHTANGABE_RE.search(t):
            return True
        return self._allowlist_in(t)

    def _allowlist_in(self, t: str) -> bool:
        index = self.w.index("allowlist")
        try:
            return index is not None and any(len(v.text) >= 4 and v.text[:1].isupper() for v in index.finde(t))
        except Exception:
            return False

    def _org_name(self, text: str) -> bool:
        """Ist die Zelle NUR der Name einer Organisation (Kopf eines Briefkopfs, einer Anschrift, einer Spalte der
        Fußzeile): ohne Ziffern, bis zu sechs großgeschriebene Wörter (dazu Verbindungswörter und Teile der
        Rechtsform) mit Rechtsform oder – bis zu vier Wörter – mit Organisationswort ("Kreissparkasse Talheim")? Kein
        Satz, der eine Versicherung nur erwähnt ("Die Donau Leben AG hat Ihren Antrag geprüft"), keine Zeile, die
        schon die Anschrift trägt (Rücksendeangabe: darunter folgt die Anschrift des Empfängers). Die Allowlist
        zählt hier nicht: sie führt auch Produkte und Fachwörter wie "Regelaltersrente"."""
        t = _URL_RE.sub(" ", _EMAIL_RE.sub(" ", text)).strip()
        if not t or any(c.isdigit() for c in t) or _PERSONEN_PLATZHALTER_RE.search(t) \
                or _ANSCHRIFT_PLATZHALTER_RE.search(t) or _NATUERLICH_RE.search(t):
            return False                    # auch keine Praxis, Kanzlei, kein Inhaber: dahinter steht ein Mensch
        woerter = re.findall(r"[^\W\d_][\w\-'.]*", t)
        if not woerter or not all((w[:1].isupper() and w.lower() not in _STOPPWOERTER) or _RECHTSFORM_RE.fullmatch(w)
                                  or w.lower().rstrip(".") in _ORG_VERBINDER for w in woerter):
            return False
        if _RECHTSFORM_RE.search(t):
            return len(woerter) <= 6
        if len(woerter) <= 2 and t.isupper() and len(t) >= 3 and self._ganz_allowlist(t):
            return True                     # Name des Versicherers in Versalien ("HUK-COBURG", "ARAG"; Befund 66)
        return bool(_ORG_WORT_RE.search(t)) and len(woerter) <= 4

    def _ganz_allowlist(self, t: str) -> bool:
        """Ist der ganze Text ein Eintrag der Allowlist (Versicherer, Banken, Behörden)?"""
        try:
            return bool(self.w.modul is not None and self.w.modul.ist_allowlist(t))
        except Exception:
            return False

    # -- Organisationsbereiche: Fußzeile und Briefkopf eines Unternehmens --------------------------------
    def _herkunft(self, z) -> str:
        """Herkunft einer Zeile: "text" (Textebene) oder "ocr" (OCR der Seite oder eines Bildbereichs)."""
        return "text" if self._quelle_block.get(z.block, "text") == "text" else "ocr"

    def ocr_lage(self) -> tuple:
        """(Winkel, Schräglage) der OCR-Wörter der Seite – übergeben oder wie im Seitenmodell geschätzt."""
        if self._ocr_lage is None:
            if self._ausrichtung is not None:
                self._ocr_lage = (int(self._ausrichtung[0] or 0) % 360, float(self._ausrichtung[1] or 0.0))
            else:
                stellen = _wortstellen(self.m)
                self._ocr_lage = (_ocr.ausrichtung_der_woerter([(b.x0, b.y0, b.x1, b.y1, self.text[s:e])
                                                                 for s, e, b in stellen]) if stellen else (0, 0.0))
        return self._ocr_lage

    def lese_rect(self, r, herkunft: str):
        """Rechteck in Lesekoordinaten seiner Herkunft (Textebene: Seite; OCR: gerade gerückt nach Ausrichtung)."""
        if herkunft == "text":
            return fitz.Rect(r)
        winkel, schraeg = self.ocr_lage()
        return _lesekasten(fitz.Rect(r), winkel, schraeg)

    def _org_bereiche(self) -> None:
        """Organisationsbereiche der Seite, einmal je Seite und je Herkunft (Textebene, OCR) in deren
        Lesekoordinaten (auch auf gedrehten Scans liegt die Fußzeile so unten); gearbeitet wird mit Zellen (Spalten
        einer Zeile), nicht ganzen Zeilen – eine OCR-Zeile reicht oft über mehrere Spalten:
          * Fußbereich (_fussbereich): die Zeilen am unteren Seitenrand (unterhalb FUSS_ANTEIL der Seitenhöhe, dicht
            untereinander, Schrift nicht größer als darunter, auf der Textebene kleiner als der Brieftext; das Wachsen
            nach oben endet an Fließtext, Kundenangaben und Etiketten eines Mandats), wenn eine davon eine strenge
            Pflichtangabe trägt (Amts-/Registergericht, HRA/HRB, USt-IdNr., Vorstand, Aufsichtsrat, Geschäftsführer –
            eine Bankverbindung oder Rechtsform allein steht auch in privaten Fußzeilen und Unterschriftsblöcken) UND
            der Bereich einer juristischen Person gehört (Rechtsform oder Organisationswort, keine Merkmale einer
            natürlichen Person wie Inhaber, Praxis, Kanzlei, Dr. med., kein Personen-Platzhalter außerhalb der
            Organ-Angaben "Vorstand: …") – Anschriften, Telefon-, Register- und Steuernummern sowie IBAN und BIC hinter
            ihrer Bankangabe dort sind Angaben des Unternehmens;
          * Organisationsblock (Art "block"): unter einer Zelle mit dem Namen einer Organisation (_org_name) bis zu
            ORG_BLOCK_ZEILEN Zellen direkt darunter in derselben Spalte, Schrift nicht größer (Briefkopf, Anschrift
            der Versicherung im Anschriftfeld, Spalte einer Fußzeile) – bis zu einem Personen-/Anschrift-Platzhalter,
            einer Anrede oder einem Personen-, Kennungs- oder Geburtsdatum-Etikett –, dazu reine Anschrift-Zellen
            rechts neben dem Namen (_anschrift_daneben);
          * Zelle mit eigenem Organisationsmerkmal (Art "eigen", _org_name oder _org_merkmal: "Alpenland
            Krankenversicherung a.G. · Prinzregentenplatz 21 · 81675 München") – dort gelten nur Anschrift, Telefon,
            BIC und Internetadresse als Angaben der Organisation (org_kontext), keine weiteren Nummern (org_wert):
            "Allianz 12345678" in einer Bestandsliste ist eine Vertragsnummer.
        Namen bleiben überall verdächtig (die Namensregeln fragen den Bereich nicht)."""
        if self._org_zellen is not None:
            return
        self._org_zellen, self._fusszeilen = {}, set()
        je_herkunft: dict = {}
        for z in self.m.zeilen:
            if z.rect is None:
                continue
            inhalt = self.zeilen_text(z)
            if not inhalt.strip():
                continue
            herkunft = self._herkunft(z)
            for a, b in _zellen(inhalt):
                s, e = z.start + a, z.start + b
                box = self.box(s, e)
                if box is None or box.is_empty:
                    continue
                je_herkunft.setdefault(herkunft, []).append((self.lese_rect(box, herkunft), z, s, e, inhalt[a:b]))
        for herkunft, zellen in je_herkunft.items():
            self._fussbereich(herkunft, zellen)
            nach_y = sorted(zellen, key=lambda c: c[0].y0)
            for zelle in zellen:
                name = self._org_name(zelle[4])
                if name or self._org_merkmal(zelle[4]):
                    self._org_zellen.setdefault(zelle[1].id, []).append((zelle[2], zelle[3], "eigen"))
                if name:
                    for c in self._org_block(zelle, nach_y)[1:] + self._anschrift_daneben(zelle, zellen):
                        self._org_zellen.setdefault(c[1].id, []).append((c[2], c[3], "block"))

    @staticmethod
    def _anschrift_daneben(name, zellen: list) -> list:
        """Zellen rechts neben einem Organisationsnamen in derselben Zeile, die nur eine Anschrift sind (Straße,
        Hausnummer, PLZ + Ort): die Rücksendeangabe "Taunus Krankenversicherung AG · Kaiser-Friedrich-Promenade 4 ·
        61352 Bad Homburg", von der OCR in Zellen zerlegt. Nur die unmittelbar folgenden Zellen und nur ohne weitere
        Ziffernfolgen – in einer Tabelle folgt auf den Versicherer eine Vertragsnummer, keine Anschrift."""
        aus = []
        folgende = sorted((c for c in zellen if c[1].id == name[1].id and c[2] >= name[3]), key=lambda c: c[2])
        for c in folgende[:2]:
            t = c[4]
            if _PERSONEN_PLATZHALTER_RE.search(t) or _ANSCHRIFT_PLATZHALTER_RE.search(t):
                break
            plz = _PLZ_ORT_RE.search(t)
            strasse = _STRASSE_RE.search(t) or _STRASSE_PRAEP_RE.search(t)
            if not (plz or strasse):
                break
            if any(len(g) > 4 and not (plz and g == plz.group(1)) for g in re.findall(r"\d+", t)):
                break
            aus.append(c)
        return aus

    def _org_merkmal(self, text: str) -> bool:
        """Organisationsmerkmal irgendwo in der Zelle: Rechtsform, Merkmal einer juristischen Person (HRB, Vorstand,
        Aufsichtsrat) oder Eintrag der Allowlist ("Alpenland Krankenversicherung a.G. · Prinzregentenplatz 21 · 81675
        München", "DEVK") – ein Satz, der nur eine Versicherung erwähnt ("Kündigung meiner Hausratversicherung"), ist
        keins, eine Zelle mit Merkmal einer natürlichen Person (Inhaber, Praxis, Kanzlei, Titel, e.K., GbR) oder einem
        Personen-Platzhalter auch nicht. Pflichtangaben allein (USt-IdNr., Steuernummer) belegen keine Organisation:
        "Lindenweg 7 · 34567 Kassel · USt-IdNr. …" steht auch in der Fußzeile eines Malerbetriebs."""
        t = _URL_RE.sub(" ", _EMAIL_RE.sub(" ", text))
        if _ist_fliesstext(t):
            return False                    # ein Satz: "Die Donau Leben AG hat Ihre Anschrift Hauptstr. 5 gespeichert"
        if _NATUERLICH_RE.search(t) or _PERSONEN_PLATZHALTER_RE.search(t):
            return False
        return bool(_RECHTSFORM_RE.search(t) or _JURISTISCH_RE.search(t)) or self._allowlist_in(t)

    def _fussbereich(self, herkunft: str, zellen: list) -> None:
        """Fußbereich einer JURISTISCHEN Person (siehe _org_bereiche): von der untersten Zeile nach oben, solange die
        Zeilen dicht stehen und die Schrift nicht größer wird – auf der Textebene auch kleiner als der Brieftext. Er
        endet vor einer Zeile, die keine Angabe der Organisation sein kann (_fusszeile_moeglich: Fließtext, Ort-Datum,
        Personen-/Anschrift-/privates Kontakt-Etikett, Besitz- oder Kundenwort), und vor einem Personen-Platzhalter
        außerhalb der Organe ("Malerbetrieb [PERSON A]" – "Vorstand: [PERSON A]" nicht). Ein Fußbereich ist er nur mit
        Pflichtangabe (_PFLICHTANGABE_RE), mit Merkmal einer juristischen Person (_JURISTISCH_RE: Rechtsform einer
        Kapitalgesellschaft, HRB, Vorstand, Aufsichtsrat) und ohne Merkmal einer natürlichen Person (_natuerlich:
        Inhaber, e.K., Praxis, Kanzlei, Titel, Name der Wissensbasis außerhalb der Organe): die Fußzeile eines
        Handwerkers, einer Werkstatt, einer Arztpraxis oder einer Privatperson nennt Anschrift, Telefon und
        Bankverbindung eines Menschen."""
        seite = self.lese_rect(self.m.rect, herkunft)
        grenze = seite.y0 + FUSS_ANTEIL * seite.height
        faktor = FUSS_SCHRIFT if herkunft == "text" else SCHRIFT_OCR
        zeilen: dict = {}
        for zelle in zellen:
            r, z = zelle[0], zelle[1]
            alt = zeilen.get(z.id)
            zeilen[z.id] = (alt[0] | r, z, alt[2] + [zelle]) if alt else (fitz.Rect(r), z, [zelle])
        brieftext = None
        if herkunft == "text":                     # übliche Zeilenhöhe des Brieftexts (OCR-Kästen schwanken zu sehr)
            hoehen = sorted(t[0].height for t in zeilen.values()
                            if t[0].y1 < grenze and sum(c.isalpha() for c in self.zeilen_text(t[1])) >= 15)
            brieftext = hoehen[len(hoehen) // 2] if len(hoehen) >= 3 else None
        unten = sorted((t for t in zeilen.values() if t[0].y0 >= grenze), key=lambda t: -t[0].y1)
        fuss, oben, groesste = [], None, 0.0
        for r, z, eigene in unten:
            h = max(r.height, 1.0)
            if fuss and (r.y1 < oben - max(FUSS_LUECKE * min(h, groesste), 3.0)
                         or h > faktor * max(groesste, FUSS_SCHRIFT_MIN) + 1.0):
                break                      # Abstand zum Text darüber oder größere Schrift: der Fußbereich ist zu Ende
            if (brieftext is not None and h > FUSS_BRIEFTEXT * brieftext) or not self._fusszeile_moeglich(eigene):
                break                      # Schrift des Brieftexts, Satz, Etikett einer Person, Angabe zum Kunden
            fuss.append((r, z, eigene))
            oben = r.y0 if oben is None else min(oben, r.y0)
            groesste = max(groesste, h)
        if not fuss:
            return
        organe = self._organ_stellen(fuss)
        texte = [c[4] for _, _, eigene in fuss for c in eigene]
        for k, (r, z, eigene) in enumerate(fuss):
            if any(not self._im_organ(p, organe) for p in self._personen_platzhalter(r, z, herkunft)):
                fuss = fuss[:k]            # eine Person (Inhaberin, Ärztin, Kunde): darüber kein Fußbereich mehr
                break
        # Pflichtangabe und juristische Person im ganzen Bereich (auch über dem Platzhalter: der Name der Gesellschaft
        # über ihrem Vorstand), Merkmale einer natürlichen Person in dem, was ausgenommen wird
        if not fuss or not any(_PFLICHTANGABE_RE.search(t) for t in texte):
            return                         # nur mit Pflichtangabe: eine Rechtsform steht auch im Unterschriftsblock
        if not any(_JURISTISCH_RE.search(t) for t in texte) or self._natuerlich(fuss, organe):
            return
        self._fusszeilen.update(z.id for _, z, _ in fuss)
        self._fusszellen += [c for _, _, eigene in fuss for c in eigene]

    def _fusszeile_moeglich(self, zellen) -> bool:
        """Kann eine Zeile am Seitenende (ihre Zellen) Pflichtangabe oder Kontaktangabe einer Organisation sein? Nicht:
        Fließtext ("Das Verfahren vor dem Amtsgericht …"), Ort-Datum-Zeile ("Melsungen, 30.10.2026"), ein Besitz- oder
        Kundenwort ("Ihr Fahrzeug …", "Ihre IBAN", "Meine Bankverbindung", "Kontoinhaber") und ein Personen-,
        Anschrift- oder privates Kontakt-Etikett mit Doppelpunkt ("Wohnanschrift:", "Mobil:", "Name der Bank:") –
        Organe ("Vorstand:") und Kontaktwege einer Organisation ("Telefon:", "E-Mail:") beenden den Bereich nicht."""
        for zelle in zellen:
            t = _URL_RE.sub(" ", _EMAIL_RE.sub(" ", zelle[4]))
            if _fuss_fliesstext(t) or _KUNDE_FUSS_RE.search(t) or _ORT_DATUM_RE.search(zelle[4]):
                return False
            for treffer in re.finditer(r"([^\W\d_][\w./\- ]{1,40}?)\s?:", t):
                etikett = re.split(r"\s?[·|•]\s?", treffer.group(1))[-1].strip()
                if not etikett or _ORGAN_RE.search(etikett) \
                        or etikett.lower().rstrip(".") in _ORG_KONTAKT_ETIKETTEN:
                    continue
                arten = ("adresse", "person", "kontakt")
                if self._etikett_in(etikett, arten) or self._etikett_in(etikett.split()[0], arten):
                    return False
        return True

    def _organ_stellen(self, fuss) -> list:
        """Lese-Rechtecke der Organ-Etiketten im Fußbereich ("Vorstand", "Vorsitz Aufsichtsrat", "Geschäftsführer") –
        auf OCR-Zeilen auch so, wie die OCR sie liest ("Vorszand:", "Yarstandl:", "Aufsichterat", abgeschnitten
        "Vor")."""
        aus = []
        for _, z, eigene in fuss:
            herkunft = self._herkunft(z)
            for _, _, s, e, t in eigene:
                spannen = [(m.start(), m.end()) for m in _ORGAN_RE.finditer(t)]
                if herkunft != "text":
                    if re.fullmatch(r"(?i)\s*[vy][o0a]rs?t?\s*:?\s*", t):
                        spannen.append((0, len(t)))     # "Vorstand:" abgeschnitten gelesen
                    for m in re.finditer(r"[^\W\d_]{5,}:?", t):
                        w = m.group(0).lower().rstrip(":")
                        schwelle = 0.7 if m.group(0).endswith(":") else 0.8
                        if any(difflib.SequenceMatcher(None, w, o).ratio() >= schwelle for o in _ORGAN_WOERTER):
                            spannen.append((m.start(), m.end()))
                for a, b in spannen:
                    r = self.box(s + a, s + b)
                    if r is None or r.is_empty:
                        continue
                    r = self.lese_rect(r, herkunft)
                    # "(Vorsitzende)" steht hinter dem ersten Namen: die Spalte der Namensliste beginnt links davon
                    links = ORGAN_NAME_BREITE if (a > 0 and t[a - 1] == "(") or t[b:b + 1] == ")" else 0.0
                    aus.append((r, r.x0 - links))
        return aus

    @staticmethod
    def _im_organ(p, organe) -> bool:
        """Steht die Stelle p (Lese-Rechteck) hinter einem Organ-Etikett: in derselben Zeile rechts davon (höchstens
        ORGAN_ABSTAND) oder in den Zeilen darunter (höchstens ORGAN_ZEILEN Zeilenhöhen) ab der Spalte des Etiketts – die
        Namensliste des Vorstands läuft über mehrere Zeilen ("Vorstand: [PERSON A] (Vorsitzende), Prof. Dr." /
        "med. [PERSON B], Dipl.-Ing. [PERSON C]"), der Name des Aufsichtsratsvorsitzes steht unter "Vorsitz
        Aufsichtsrat:"? Links vom Etikett beginnt eine andere Spalte (Name und Anschrift der Organisation)."""
        h = max(p.height, 4.0)
        for o, spalte in organe:
            if min(o.y1, p.y1) - max(o.y0, p.y0) >= 0.5 * min(o.height, p.height):
                if p.x0 >= spalte - 2 and p.x0 - o.x1 <= ORGAN_ABSTAND:
                    return True
            elif o.y1 <= p.y0 + 0.5 * h and p.y0 - o.y1 <= ORGAN_ZEILEN * h and p.x0 >= spalte - 2 * h:
                return True
            elif p.y1 <= o.y0 + 0.5 * h and o.y0 - p.y1 <= 1.5 * h and min(o.x1, p.x1) - max(spalte, p.x0) > -h:
                return True                 # der Name über seinem umbrochenen Zusatz "(Vorsitzender),"
        return False

    def _personen_platzhalter(self, r, z, herkunft: str) -> list:
        """Lese-Rechtecke der Personen-Platzhalter einer Zeile des Fußbereichs: auf der Textebene im Text der Zeile,
        auf Scans (Platzhalter auf der Textebene, Zeile aus der OCR) auf derselben Höhe der Seite. Nicht gezählt wird
        ein Platzhalter an der Stelle eines Orts oder Straßennamens – hinter einer PLZ, hinter "Sitz:" oder
        "Amtsgericht", vor einer Hausnummer ("Ehm-Welk-Str. 2 · 03222 [PERSON A]", "[PERSON B] 33 · 01098 Dresden"):
        dort hat die Erkennung einen Ortsnamen für einen Personennamen gehalten, eine Person nennt die Zeile nicht."""
        aus = []
        for s, e, _ in self.platzhalter_boxen():
            if not _PERSONEN_PLATZHALTER_RE.match(self.text[s:e]):
                continue
            if herkunft == "text" and not z.start <= s < z.ende:
                continue
            # die Glyphen des Platzhaltertexts (das graue Rechteck kann mehrzeilig sein, rechtecke() bringt auf Scans
            # die verknüpften OCR-Wörter mit)
            glyphen = [fitz.Rect(self.m.zeichen[g].rect) for g in self.m.glyphen(s, e)]
            if not glyphen:
                continue
            b = glyphen[0]
            for g in glyphen[1:]:
                b |= g
            p = self.lese_rect(b, herkunft)
            if herkunft != "text" and (min(p.y1, r.y1) - max(p.y0, r.y0) < 0.5 * min(p.height, r.height)
                                       or max(r.x0 - p.x1, p.x0 - r.x1) > 3 * max(p.height, 4.0)):
                continue                          # nicht auf der Höhe dieser OCR-Zeile oder weit daneben (Spalte)
            vor, nach = (self.text[z.start:s], self.text[e:z.ende]) if herkunft == "text" \
                else self._text_neben(z, p, herkunft)
            if re.search(r"(?i)(?:(?<![\d])\d{5}|\bsitz|\bamtsgericht|\bregistergericht|\bgericht)[\s:,]*$", vor) \
                    or re.match(r"\s*\d{1,4}\s?[a-zA-Z]?\s*(?:[·|•,:;*\-–]|\d{5}\b|$)", nach):
                continue
            aus.append(p)
        return aus

    def _text_neben(self, z, p, herkunft: str) -> tuple:
        """(Text links, Text rechts) des Rechtecks p (Lesekoordinaten) in der OCR-Zeile z."""
        links, rechts = z.start, z.ende
        abb, zeichen = self.m.abbildung, self.m.zeichen
        for i in range(z.start, min(z.ende, len(abb))):
            g = abb[i]
            if g < 0 or self.text[i].isspace():
                continue
            k = self.lese_rect(zeichen[g].rect, herkunft)
            if k.x1 <= p.x0 + 1:
                links = i + 1
            elif k.x0 >= p.x1 - 1 and rechts == z.ende:
                rechts = i
        return self.text[z.start:links], self.text[max(rechts, links):z.ende]

    def _natuerlich(self, fuss, organe) -> bool:
        """Trägt der Fußbereich ein Merkmal einer natürlichen Person außerhalb der Organe: Inhaber, e.K., Praxis,
        Kanzlei, Titel, freie Berufe, GbR/OHG/PartG (_NATUERLICH_RE) oder einen eindeutigen Vor- oder Nachnamen der
        Wissensbasis – nicht im Namen einer Gesellschaft (Abschnitt mit Rechtsform oder Organisationswort), nicht in
        Bankangaben, nicht als Teil eines Straßennamens?"""
        for _, z, eigene in fuss:
            herkunft = self._herkunft(z)
            for _, _, s, _, t in eigene:
                stellen = [(m.start(), m.end()) for m in _NATUERLICH_RE.finditer(t)]
                pos = 0
                for abschnitt in _SEGMENT_RE.split(t):
                    a = t.find(abschnitt, pos)
                    pos = a + len(abschnitt)
                    if not abschnitt.strip() or _RECHTSFORM_RE.search(abschnitt) or _ORG_WORT_RE.search(abschnitt) \
                            or _BANK_RE.search(abschnitt):
                        continue
                    for w in _NAMENSWORT_RE.finditer(abschnitt):
                        wort = w.group(0)
                        if len(wort) < 3 or not wort[:1].isupper() or wort.lower() in _STOPPWOERTER \
                                or re.search(r"(?i)" + _STRASSEN_ENDUNG + r"$", wort) \
                                or re.match(r"[ \-]?(?i:" + _STRASSEN_ENDUNG + r")", abschnitt[w.end():w.end() + 9]):
                            continue
                        vn, nn, vnm, nnm, aw, tit, allow, part = self.w.art(wort)
                        if ((vn and not vnm) or (nn and not nnm)) and not (aw or tit or allow or part):
                            stellen.append((a + w.start(), a + w.end()))
                for ms, me in stellen:
                    b = self.box(s + ms, s + me)
                    if b is None or b.is_empty or not self._im_organ(self.lese_rect(b, herkunft), organe):
                        return True
        return False

    def _org_block(self, start, nach_y: list) -> list:
        """Zellen direkt unter einem Organisationsnamen in derselben Spalte (siehe _org_bereiche) – nicht aus einer
        Tabellenzeile heraus (der Name ist eine von mehreren Zellen seiner Zeile: Spalte "Versicherer" einer
        Bestandsliste, darunter die nächste Zeile mit einer Vertragsnummer)."""
        gruppe, akt = [start], start
        zellen_der_zeile = [c for c in nach_y if c[1].id == start[1].id
                            and sum(ch.isalnum() for ch in c[4]) >= 3]       # OCR-Krümel ("Bu", "a") zählen nicht
        if len(zellen_der_zeile) >= 3:
            return gruppe
        for _ in range(ORG_BLOCK_ZEILEN):
            r = akt[0]
            h = max(r.height, 1.0)
            naechste = None
            for c in nach_y:
                cr = c[0]
                if cr.y0 < r.y1 - 0.5 * h or c in gruppe:
                    continue
                if cr.y0 > r.y1 + ORG_BLOCK_LUECKE * max(h, cr.height):
                    break
                ueberlapp = min(cr.x1, r.x1) - max(cr.x0, r.x0)
                if ueberlapp >= 0.3 * min(cr.width, r.width) or abs(cr.x0 - r.x0) <= 1.5 * h:
                    naechste = c
                    break
            if naechste is None:
                break
            faktor = ORG_BLOCK_SCHRIFT if self._herkunft(naechste[1]) == "text" else SCHRIFT_OCR
            if naechste[0].height > faktor * h + 1.0 or self._block_ende(naechste[4]):
                break
            gruppe.append(naechste)
            akt = naechste
        return gruppe

    def _block_ende(self, text: str) -> bool:
        """Endet ein Organisationsblock vor dieser Zelle: Personen-/Anschrift-Platzhalter (auch als OCR-Bruchstück),
        Anrede ("Herrn", "Frau"), Personen-, Kennungs- oder Geburtsdatum-Etikett ("Ansprechpartner",
        "Kundennummer"), Fließtext oder etwas, das ein Personenname sein kann (zwei, drei großgeschriebene Wörter, von
        denen eines kein gewöhnliches Wort ist: "Kristóf Vargha" – die Anschrift darunter gehört dann einer Person)?"""
        ohne_adressen = _URL_RE.sub(" ", _EMAIL_RE.sub(" ", text))
        if _PERSONEN_PLATZHALTER_RE.search(text) or _ANSCHRIFT_PLATZHALTER_RE.search(text) \
                or _ist_fliesstext(ohne_adressen) or self._org_merkmal(text):
            return True                     # eine weitere Organisation (Tabellenzeile) beginnt ihren eigenen Block
        for g in re.finditer(r"\d+", text):
            if len(g.group(0)) < 5:
                continue
            if len(g.group(0)) == 5 and re.match(r"[ \t]{1,2}[A-ZÄÖÜ]", text[g.end():g.end() + 3]):
                continue                    # PLZ + Ort
            if re.search(r"(?:\+\d{1,3}|\(?0\d{1,5}\)?)[\s/()-]{0,3}(?:\d+[\s/-]{1,2}){0,3}$", text[:g.start()]) \
                    or g.group(0).startswith("0"):
                continue                    # Teil einer Telefonnummer ("089 216012345", "+49 89 21600")
            return True                     # lange Nummer, die weder PLZ noch Telefon ist (Vertragsnummer)
        namenswoerter = re.findall(r"[^\W\d_][\w\-'.]*", text)
        if (2 <= len(namenswoerter) <= 3 and not any(c.isdigit() for c in text) and not self._org_text(text)
                and all(w[:1].isupper() for w in namenswoerter)
                and any(not self._wort_harmlos(w.rstrip(".")) for w in namenswoerter)):
            return True
        woerter = text.split()
        if not woerter:
            return True
        if any(w.strip(".,:").lower() in _ANREDEN for w in woerter) or any(
                _platzhalter_bruchstueck(w) for w in woerter if "[" in w or "]" in w or w.strip("()|!.,:;").isupper()):
            return True
        for art in ("person", "kennung", "datum_geburt"):
            index = self.w.index(art)
            try:
                if index is not None and index.finde(text):
                    return True
            except Exception:
                continue
        return False

    # -- Etiketten ----------------------------------------------------------------------------------
    def _etikett_in(self, text: str, arten):
        """(Art, Etikett), wenn der Text (ohne ":") genau ein Etikett der Arten ist."""
        t = text.strip().rstrip(":").strip()
        if not t or "[" in t or "]" in t:
            return None
        for art in arten:
            index = self.w.index(art)
            try:
                if index is not None and index.eintrag_fuer(t) is not None:
                    return art, t
            except Exception:
                continue
        return None

    def etikett_davor(self, s: int, e: int, arten, fenster: int = 45):
        """(Art, Etikett) des nächsten Etiketts links der Stelle: in derselben Textzeile, in der Zeile darüber
        (Infoblock "Geburtsdatum" / "12.03.1961") oder links auf derselben Zeilenhöhe (Formular) – sonst None."""
        z = self.zeile(s)
        if z is None:
            return None
        bester = None
        anfang = max(z.start, s - fenster)
        stueck = self.text[anfang:s]
        for ps, pe in self.platzhalter:                # "[GEB-DATUM]" ist kein Etikett
            if ps < s and pe > anfang:
                a, b = max(ps, anfang) - anfang, min(pe, s) - anfang
                stueck = stueck[:a] + " " * (b - a) + stueck[b:]
        for art in arten:
            index = self.w.index(art)
            if index is None:
                continue
            try:
                treffer = index.finde(stueck)
            except Exception:
                continue
            for v in treffer:
                zwischen = stueck[v.ende:]
                if _DATUM_RES[0][0].search(zwischen) or re.search(r"\d{3,}", zwischen):
                    continue                 # ein anderer Wert steht dazwischen
                abstand = len(stueck) - v.ende
                if bester is None or abstand < bester[0]:
                    bester = (abstand, art, v.text)
        if bester is not None:
            return bester[1], bester[2]
        if not self.text[z.start:s].strip():
            for y in self.zeilen_oberhalb(z, 1):
                if z.rect is not None and y.rect is not None and z.rect.y0 - y.rect.y1 > 2.5 * max(z.rect.height, 4):
                    break
                treffer = self._etikett_in(self.zeilen_text(y), arten)
                if treffer:
                    return treffer
            for y in self.zeilen_links(s, e)[:1]:
                treffer = self._etikett_in(re.split(r"\t+", self.zeilen_text(y).strip())[-1], arten)
                if treffer:
                    return treffer
        return None

    def _kopfzeile(self, z) -> bool:
        """Kopfzeile einer Tabelle: mindestens zwei Etiketten (beliebiger Art) in getrennten Zellen."""
        schluessel = ("kopf", z.id)
        if schluessel not in self._org:
            zeile = self.zeilen_text(z)
            zellen = [t.strip() for t in re.split(r"\t+|\s{3,}| \| ", zeile) if t.strip()]
            if len(zellen) < 2 and self._quelle(z.start) != "text":
                woerter = zeile.split()          # OCR-Zeilen kennen keine Spaltentrenner
                zellen = woerter if 3 <= len(woerter) <= 10 else zellen
            zellen = [t for t in zellen if "[" not in t and "]" not in t]
            treffer = sum(1 for t in zellen if self.w.ist_etikett(t) or self.w.ist_etikett(t.rstrip(".:")))
            self._org[schluessel] = treffer >= 2 and treffer >= 0.4 * len(zellen)
        return self._org[schluessel]

    def _datenzeile(self, z) -> bool:
        """Datenzeile einer Tabelle: mehrere Zellen, Ziffern oder Platzhalter darin, keine Kopfzeile – ihre Zellen
        sind Werte ihrer Spalten, auch die ohne Ziffern (erste Zeile einer umbrochenen Zelle, Befund 84)."""
        schluessel = ("daten", z.id)
        if schluessel not in self._org:
            zeile = self.zeilen_text(z)
            zellen = [t for t in re.split(r"\t+", zeile) if t.strip()]
            self._org[schluessel] = (len(zellen) >= 2 and not self._kopfzeile(z)
                                     and (any(c.isdigit() for c in zeile) or bool(_PLATZHALTER_RE.search(zeile))))
        return self._org[schluessel]

    def _schriftgroesse(self, z) -> float:
        """Median der Schriftgröße einer Zeile ohne Platzhalter (0.0, wenn dort nur Platzhalter stehen)."""
        zeile = self.zeilen_text(z)
        gesperrt = [(m.start(), m.end()) for m in _PLATZHALTER_RE.finditer(zeile)]
        abb, zeichen = self.m.abbildung, self.m.zeichen
        groessen = []
        for i in range(z.start, min(z.ende, len(abb))):
            if self.text[i].isspace() or any(a <= i - z.start < b for a, b in gesperrt):
                continue
            g = abb[i]
            if g >= 0 and zeichen[g].groesse:
                groessen.append(zeichen[g].groesse)
        groessen.sort()
        return groessen[len(groessen) // 2] if groessen else 0.0

    def _etikettzeile(self, z) -> bool:
        """Etikettzeile eines Kastenformulars ("Ausgeübter Beruf ⇥⇥ Arbeitgeber" über den Werten): mehrere Zellen, keine
        Ziffern und keine Platzhalter, ein Etikett der Wissensbasis in einer Zelle – und darunter die Werte: kleiner
        gesetzt als die nächste Zeile darunter oder darunter nur Platzhalter (die geschwärzten Werte). Ihre Wörter sind
        Feldbezeichner, keine Werte der Tabellenspalte darüber (Befund 90; die Erkennung beendet dort die Tabelle,
        struktur_tabelle)."""
        schluessel = ("etikettzeile", z.id)
        if schluessel in self._org:
            return self._org[schluessel]
        self._org[schluessel] = False
        zeile = self.zeilen_text(z)
        zellen = [t.strip().rstrip(":") for t in re.split(r"\t+", zeile) if t.strip()]
        if (len(zellen) < 2 or z.rect is None or any(c.isdigit() for c in zeile) or _PLATZHALTER_RE.search(zeile)
                or not any(self.w.ist_etikett(t) for t in zellen)):
            return False
        unten = self.zeile_darunter(z, z.rect.x0, z.rect.x1)
        if unten is None:
            return False
        eigen, darunter = self._schriftgroesse(z), self._schriftgroesse(unten)
        werte = re.sub(r"[\s,.;:]+", "", _PLATZHALTER_RE.sub("", self.zeilen_text(unten)))
        self._org[schluessel] = (not werte and _PLATZHALTER_RE.search(self.zeilen_text(unten)) is not None) \
            or (eigen > 0 and darunter > 0 and eigen <= 0.85 * darunter)
        return self._org[schluessel]

    def zeile_darunter(self, z, x0: float, x1: float):
        """Nächste Zeile unter z nach der Lage auf der Seite (höchstens eine Zeilenhöhe Abstand), die im x-Bereich
        [x0, x1] Zeichen hat (dieselbe Tabellenspalte), oder None."""
        if z is None or z.rect is None:
            return None
        hoehe = max(z.rect.height, 4.0)
        beste = None
        for y in self.m.zeilen:
            r = y.rect
            if r is None or y.id == z.id or r.y0 < z.rect.y1 - 0.3 * hoehe or r.y0 - z.rect.y1 > hoehe \
                    or r.x1 < x0 or r.x0 > x1:
                continue
            if (beste is None or r.y0 < beste.rect.y0) and any(x0 - 2 <= xm <= x1 + 2 for _, xm in self.zeichen_x(y)):
                beste = y
        return beste

    def spaltenkopf(self, s: int, e: int, arten, streng: bool = True):
        """Tabellenspalte: (Art, Etikett) des Spaltenkopfs über der Stelle – die Zellen darüber werden nach
        oben durchgegangen, solange sie Werte (Ziffern, Platzhalter) tragen; die erste Zelle mit einem Etikett
        entscheidet."""
        z = self.zeile(s)
        b = self.box(s, e)
        if z is None or b is None:
            return None
        eigene = self.zeilen_text(z)
        if re.match(r"\s*[^\t:]{1,40}:\s*\t", eigene) and not self._kopfzeile(z):
            return None                        # Schlüssel-Wert-Zeile ("Tarif:  ZahnPlus 80"), keine Tabelle
        if self._etikettzeile(z):
            return None                        # selbst eine Etikettzeile (Kastenformular), kein Wert der Spalte
        # eigene Zelle (zwischen Tabulatoren): ein kurzer Wert darf über Datenzeilen hinweg zu seinem Kopf, Fließtext
        # unter der Tabelle nicht ("Die Erstattung … überweisen wir auf Ihr Konto" unter "Leistungserbringer")
        rel_s, rel_e = max(0, s - z.start), max(0, e - z.start)
        ende_zelle = eigene.find("\t", rel_e)
        eigene_zelle = eigene[eigene.rfind("\t", 0, rel_s) + 1:ende_zelle if ende_zelle >= 0 else len(eigene)]
        kurzer_wert = len(eigene_zelle.split()) <= 5
        leer = 0
        oben = z.rect.y0
        hoehe = max(z.rect.height, 8.0)
        for y in self.zeilen_oberhalb(z, SPALTE_ZEILEN):
            if oben - y.rect.y1 > 2.5 * hoehe:
                return None                    # Absatz-/Abschnittsgrenze: die Tabelle ist zu Ende
            zelle, zs, ze = self.zelle_ueber(y, b.x0, b.x1)
            zelle = zelle.strip()
            if not zelle:
                leer += 1
                if leer > 2:
                    return None
                continue
            leer = 0
            oben = min(oben, y.rect.y0)
            kurz = (not streng and len(zelle.split()) <= 4 and not zelle.endswith(":")
                    and not any(c.isdigit() for c in zelle))
            if not kurz and (zelle.endswith(":") or not self._kopfzeile(y)):
                if any(c.isdigit() for c in zelle) or self.ist_platzhalter_bei(zs, ze):
                    continue
                if kurzer_wert and not zelle.endswith(":") and self._datenzeile(y):
                    continue                   # Wert einer Datenzeile derselben Spalte ("Eheleute" ⏎ "Gstettner")
                return None
            for art in arten:
                index = self.w.index(art)
                if index is None:
                    continue
                try:
                    treffer = index.finde(zelle)
                except Exception:
                    continue
                if treffer:
                    return art, treffer[0].text
            if any(c.isdigit() for c in zelle) or self.ist_platzhalter_bei(zs, ze):
                continue                       # Werte-Zeile derselben Spalte
            return None
        return None

    # -- Regeln ---------------------------------------------------------------------------------------
    def neu(self, s: int, e: int, grund: str, art: str):
        if e > s:
            self.kandidaten.append(_Kandidat(s, e, grund, art))

    def pruefen(self) -> list:
        if not self.text.strip():
            return []
        for z in self.m.zeilen:
            zeile = self.zeilen_text(z)
            if not zeile.strip():
                continue
            maske = self._maske(zeile, z)
            self._kennungen(z, zeile, maske)
            self._formen(z, zeile, maske)
            self._daten(z, zeile)
            self._kontakt(z, zeile)
            self._anschriften(z, zeile)
            if "\t" in zeile:
                self._umbrochene_strasse(z, zeile)
                self._betragsform_unter_kennungskopf(z, zeile)
        self._namen()
        self._geburtsname_etiketten()
        self._zb1_felder()
        self._gemeinschaften()
        self._reste_neben_platzhaltern()
        self._ort_datum()
        return self.kandidaten

    def _ort_datum(self):
        """Ort-Datum-Zeile ("Tübingen, 14. Januar 2025", "St. Ingbert, 11.08.2025"): der Ort ist meist der
        Wohnort der Unterzeichnenden (der Fußbereich endet vor einer solchen Zeile, _fusszeile_moeglich)."""
        for z in self.m.zeilen:
            zeile = self.zeilen_text(z)
            if "," not in zeile:
                continue
            for m in _ORT_DATUM_RE.finditer(zeile):
                ort = m.group(1)
                s, e = z.start + m.start(1), z.start + m.end(1)
                erstes = ort.split()[0].rstrip(".")
                vn, nn, vnm, nnm, aw, tit, allow, part = self.w.art(erstes)
                if (tit or allow or erstes.lower() in _STOPPWOERTER or erstes.lower() in _KALENDERWOERTER
                        or self.w.ist_etikett(ort)
                        or self.w.ist_etikett(erstes) or self.ist_gesperrt(s, e) or self.org_kontext(s)):
                    continue
                self.neu(s, e, "Ort in Ort-Datum-Zeile (Wohnort?)", "anschrift")

    # Masken: Beträge, Uhrzeiten, Paragrafen, Prozent, Jahresbereiche, Verhältnisse, Datumsangaben
    def _datumsformen(self, z) -> tuple:
        """Datumsformen einer Zeile – auf OCR-Zeilen auch mit einer angehängten Ziffer ("01.07.20836")."""
        if z is not None and self._herkunft(z) == "ocr":
            return _DATUM_RES + _DATUM_OCR_RES
        return _DATUM_RES

    def _maske(self, zeile: str, z=None) -> list:
        maske = [False] * len(zeile)
        for regex in (_BETRAG_RE, _UHRZEIT_RE, _PARAGRAF_RE, _PROZENT_RE, _JAHRESBEREICH_RE):
            for m in regex.finditer(zeile):
                for i in range(m.start(), m.end()):
                    maske[i] = True
        heute = _heute()
        for regex, art in self._datumsformen(z):
            verlesen = regex in (r for r, _ in _DATUM_OCR_RES)
            for m in regex.finditer(zeile):
                datum = self._datum(m, art)
                if datum is None:
                    continue
                if verlesen and datum <= heute and ALTER_MIN <= heute.year - datum.year <= ALTER_MAX:
                    continue                # verlesenes Datum mit möglichem Geburtsjahr: die Ziffern bleiben Verdacht
                for i in range(m.start(), m.end()):
                    maske[i] = True
        return maske

    def _kennungen(self, z, zeile: str, maske: list):
        """Ziffernfolgen ab MIN_ZIFFERN Ziffern (Gruppen über Leerzeichen, / und - verbunden)."""
        tokens = [(m.start(), m.end()) for m in _TOKEN_RE.finditer(zeile)
                  if not any(maske[m.start():m.end()]) and _ziffern(m.group(0))]
        # Ziffern einer IBAN der Organisation (ihre Bankverbindung im Fußbereich) beurteilt die IBAN-Regel (_formen)
        org_ibans = []
        if tokens and self.im_fussbereich(z.start):
            org_ibans = [(m.start(1), m.end(1)) for regex in (_IBAN_RE, _IBAN_DE_LOSE_RE) for m in regex.finditer(zeile)
                         if self.org_konto(z.start + m.start(1))]
        i = 0
        while i < len(tokens):
            s, e = tokens[i]
            j = i
            if zeile[s:e].isdigit():
                while j + 1 < len(tokens):
                    ns, ne = tokens[j + 1]
                    luecke = zeile[tokens[j][1]:ns]
                    if (zeile[ns:ne].replace("-", "").replace("/", "").isdigit() and len(luecke) <= 4
                            and set(luecke) <= _LUECKE_KETTE and luecke.count(" ") <= 2
                            and not any(maske[tokens[j][1]:ns])
                            and not (j == i and self._hausnummer_plz(zeile, s, e, ns, ne))):
                        j += 1
                    else:
                        break
            anfang = s
            while anfang > 0 and zeile[anfang - 1] in "+(" and not maske[anfang - 1]:
                anfang -= 1                          # "+49" / "(0" davor gehört dazu
            if not any(a <= anfang and tokens[j][1] <= b for a, b in org_ibans):
                self._kennung_bewerten(z, zeile, anfang, tokens[j][1])
            i = j + 1

    def _modellnummer(self, z, zeile: str, s: int) -> bool:
        """Steht die Ziffernfolge direkt hinter einer Marke oder einem Modell der Wissensbasis (sachnamen: "Dell XPS",
        "Samsung Galaxy") – höchstens ein Modellwort dazwischen ("Dell XPS 13 9340", "Lenovo ThinkPad T14")? Befund 66
        der Domänen-Durchsicht."""
        basis = max(0, s - 40)
        stellen = personenkontext.sachnamen_stellen(zeile[basis:s], self.w.modul)
        # nur Leerzeichen dazwischen: dieselbe Zelle (eine Nummer in der nächsten Spalte gehört nicht zur Marke)
        return any(re.fullmatch(r" +(?:[A-Za-z][\w\-]{0,14} +)?", zeile[basis + b:s]) for _, b in stellen)

    @staticmethod
    def _hausnummer_plz(zeile: str, s: int, e: int, ns: int, ne: int) -> bool:
        """Sind die Ziffern s:e eine Hausnummer und ns:ne die Postleitzahl dahinter ("Prinzregentenplatz 21 - 81675
        München", "Str. 33 01099 Dresden" – die OCR liest "·" als "-" oder gar nicht)? Dann ist es eine Anschrift
        (die Anschrift-Regeln prüfen Straße und PLZ + Ort), keine Kennung."""
        return (bool(re.fullmatch(r"\d{1,4}", zeile[s:e])) and bool(re.fullmatch(r"\d{5}", zeile[ns:ne]))
                and bool(re.match(r"[ \t]{1,2}[A-ZÄÖÜ][a-zäöüß]", zeile[ne:ne + 4]))
                and bool(re.search(r"(?i)(?:" + _STRASSEN_ENDUNG + r"|[a-zäöüß]{3})\.{0,2}[ \t]{0,2}$",
                                   zeile[max(0, s - 30):s])))

    def _diagnoseschluessel(self, z, zeile: str, s: int, e: int, g_s: int, g_e: int) -> bool:
        """Ist die ICD-förmige Zeichenfolge ein Diagnoseschlüssel (oder auf einer OCR-Zeile ein verlesener Betrag
        "860.26")? Mit Buchstaben ("I25.11", "S93.40") immer; nur Ziffern – so liest die OCR den Buchstaben ("125.11")
        – auf OCR-Zeilen, auf der Textebene nur in Klammern oder in einer Zeile mit Diagnose ("Koronare Herzkrankheit
        (125.11)"), nicht ohne diesen Zusammenhang ("Az. 312.45 bitte angeben"). Nie hinter einem Kennungs-Etikett."""
        stueck = zeile[s:e]
        if self.etikett_davor(g_s, g_e, ("kennung",)):
            return False
        if stueck.lstrip("(")[:1].isalpha() or self._herkunft(z) != "text":
            return True
        return stueck.startswith("(") or zeile[e:e + 1] == ")" or bool(_DIAGNOSE_RE.search(zeile))

    @staticmethod
    def _tag_monat_jahr(tag: int, monat: int, jahr: str, ocr: bool) -> bool:
        """Kann das ein Datum sein: Monat 1-12 und Tag bis 31 – auf OCR-Zeilen bei vierstelligem Jahr 19xx/20xx auch ein
        verlesener Tag ("81.07.2018" für "31.07.2018")?"""
        if not 1 <= monat <= 12:
            return False
        return tag <= 31 or (ocr and len(jahr) == 4 and jahr[:2] in ("19", "20"))

    def _datumsform(self, z, stueck: str, g_s: int, g_e: int) -> bool:
        """Ist die Ziffernfolge ein Datum, das die Datumsregeln nicht als gültiges Datum lesen – also keine Kennung?
        Monat/Jahr ("08.1987") überall; ein volles Datum nur mit Monat bis 12 und Tag bis 31 (_tag_monat_jahr): auf
        OCR-Zeilen auch verlesen ("0.04.2025", "01.07.20836", "14:03.61", "81.07.2018"), auf der Textebene – dort kann
        nichts verlesen sein – nur mit Jahr 19xx/20xx ("31.04.2025") oder direkt an einer Schwärzung (eine Ziffer mit
        dem Nachbarwert geschwärzt). Nie hinter einem Kennungs-Etikett: "Kundennummer 12.34.5678", "Vertragsnummer
        45.67.2015" sind Kennungen, ebenso "12.34.5678" oder "07.15.20335" ohne Etikett auf der Textebene."""
        if not _DATUMSFORM_RE.fullmatch(stueck) or self.etikett_davor(g_s, g_e, ("kennung",)):
            return False
        if _MONAT_JAHR_RE.fullmatch(stueck):
            return True
        m = _DATUMSFORM_TMJ_RE.fullmatch(stueck)
        ocr = self._herkunft(z) != "text"
        if m is None or not self._tag_monat_jahr(int(m.group(1)), int(m.group(2)), m.group(3), ocr):
            return False
        if ocr:
            return True
        jahr = m.group(3)
        return (len(jahr) == 4 and jahr[:2] in ("19", "20")) or self.an_schwaerzung(g_s, g_e)

    def _kennung_bewerten(self, z, zeile: str, s: int, e: int):
        stueck = zeile[s:e]
        ziffern = _ziffern(stueck)
        if ziffern < MIN_ZIFFERN:
            return
        g_s, g_e = z.start + s, z.start + e
        davor = zeile[max(0, s - 40):s]
        if _UST_ID_RE.fullmatch(stueck) and _UST_ETIKETT_RE.search(davor) \
                and personenkontext.ust_id_einer_person(personenkontext.ust_umgebung(self.text, g_s)):
            # USt-IdNr. eines Einzelkaufmanns oder Inhabers (e.K., "Inhaber", keine Rechtsform einer juristischen
            # Person) – die Erkennung schwärzt sie (personenkontext.ust_id_der_firma), bliebe sie lesbar: Verdacht
            self.neu(g_s, g_e, "USt-IdNr. einer Person (Einzelkaufmann, Inhaber)", "form")
            return
        if _ORG_NUMMER_RE.search(davor) or _GLAEUBIGER_ID_RE.match(stueck):
            return                                   # Handelsregister, USt-IdNr., BLZ, Gläubiger-ID, Formular
        if _EINHEIT_RE.match(zeile[e:e + 14]) or _WAEHRUNG_VOR_RE.search(davor):
            return
        if re.fullmatch(r"\d{1,3}/\d{1,3}", stueck) or re.fullmatch(r"\d{1,5}/(?:100|1000|10000|100000)", stueck):
            return                                   # Verhältnis/Tarifstufe "300/150", Miteigentumsanteil "125/1000"
        if self._modellnummer(z, zeile, s):
            return                                   # Modellnummer hinter Marke/Modell ("Dell XPS 13 9340")
        if _ICD_RE.fullmatch(stueck) and self._diagnoseschluessel(z, zeile, s, e, g_s, g_e):
            return                                   # Diagnoseschlüssel, auch verlesen ("(125.11" für "(I25.11")
        if self._datumsform(z, stueck, g_s, g_e):
            # Datum, auch verlesen ("0.04.2025"), oder Monat/Jahr ("08.1987"): keine Kennung – ein verlesenes Datum
            # mit möglichem Geburtsjahr bleibt aber Verdacht (die Datumsregel erkennt es nicht mehr als Datum)
            jahr = re.search(r"((?:19|20)\d{2})\d?$", stueck)
            alter = _heute().year - int(jahr.group(1)) if jahr else -1
            zeitraum = (_BEREICH_DANACH_RE.match(zeile[e:e + 8]) or _BEREICH_DAVOR_RE.search(zeile[max(0, s - 10):s])
                        or re.match(r"[ \t]+\d{1,2}[.:,]\d{1,2}[.:,]\d{2,4}", zeile[e:e + 16]))
            if ALTER_MIN <= alter <= ALTER_MAX and not zeitraum \
                    and not self.etikett_davor(g_s, g_e, ("vertragsdaten",)):
                self.neu(g_s, g_e, "verlesenes Datum mit möglichem Geburtsjahr", "datum")
            return
        kompakt = re.sub(r"[\s()/\-.]", "", stueck)
        # persönliche Steuer-ID (Prüfziffer) vor allen Ausnahmen der Organisation – außer hinter dem Etikett der
        # Steuernummer der Organisation ("Steuernummer 143/123/45678" hat kompakt auch 11 Ziffern)
        if kompakt.isdigit() and len(kompakt) == 11 and steuer_id_gueltig(kompakt) \
                and not _STEUERNUMMER_ETIKETT_RE.search(davor):
            self.neu(g_s, g_e, "Steuer-ID (Prüfziffer gültig)", "form")
            return
        if self.org_wert(g_s, g_e):
            return                                   # Telefon, PLZ, Register-, Konto-, Steuernummer der Organisation
        if (stueck.startswith(("+", "0", "(0")) and kompakt.isdigit() and ziffern >= 6) or stueck.startswith("+"):
            if _SERVICE_NUMMER_RE.search(stueck.replace("(0)", "")) or stueck.endswith("-0"):
                return                               # Service-Rufnummer, Zentrale ("-0")
            if self.org_kontext(g_s):
                return                               # Telefon/Fax im Briefkopf oder in der Fußzeile
            grund = ("internationale Telefonnummer (+Ländervorwahl)" if stueck.startswith("+")
                     else "mögliche Telefonnummer")
            self.neu(g_s, g_e, grund, "kontakt")
            return
        if stueck.isdigit() and len(stueck) == 5:
            if self.org_kontext(g_s):
                return                               # PLZ einer Firmenanschrift
            ort = _PLZ_ORT_RE.match(zeile, s) if re.match(r"[ \t]{1,2}[A-ZÄÖÜ]", zeile[e:e + 3]) else None
            if ort:
                self.neu(g_s, z.start + ort.end(), "PLZ + Ort", "anschrift")
                return
        if kompakt.isdigit() and 13 <= len(kompakt) <= 19 and luhn_gueltig(kompakt):
            self.neu(g_s, g_e, "Kreditkartennummer (Prüfziffer gültig)", "form")
        else:
            self.neu(g_s, g_e, "Ziffernfolge (mögliche Kunden-, Vertrags- oder Kennnummer)", "kennung")

    @staticmethod
    def _kamm_iban_ende(m) -> int | None:
        """Ende (Zeilenposition) einer IBAN in Kästchenschrift ("D E  6 9  9 1 4 9 …"): die längste Zeichenfolge ab dem
        Länderkürzel, die eine gültige IBAN oder eine deutsche IBAN-Form (DE + 20 Ziffern) ist – dahinter stehende
        Kästchen ("… 1 4  B I C") gehören nicht dazu. None, wenn keine solche Folge darin steht."""
        stellen = [m.start(1) + i for i, c in enumerate(m.group(1)) if not c.isspace()]
        kompakt = "".join(m.string[i] for i in stellen)
        if re.match(r"DE\d{20}", kompakt):
            return stellen[21] + 1
        for laenge in range(min(len(kompakt), 34), 14, -1):
            if iban_gueltig(kompakt[:laenge]):
                return stellen[laenge - 1] + 1
        return None

    @staticmethod
    def _kamm_iban_ocr(stueck: str) -> bool:
        """Ist die von der OCR gelesene Kästchenfolge hinter "DE" ("D/E  6 9 j0 3 8 8  5i2 4 3") ein Teil einer IBAN:
        mindestens 10 Zeichen, die Ziffern sind oder wie Ziffern aussehen (j/i/l → 1, O → 0, S → 5 …), und davon
        mindestens 7 echte Ziffern? Eine verlesene Kästchenzeile mit Buchstaben eines Namens ("D E  M U S T E R") ist
        keine."""
        rest = re.sub(r"^D[ \t/|.]{0,3}E", "", stueck)
        zeichen = re.sub(r"[ \t]", "", rest)
        return len(zeichen) >= 10 and sum(c.isdigit() for c in zeichen) >= 7 \
            and zeichen.translate(_ZIFFERNAEHNLICH).isdigit()

    def _formen(self, z, zeile: str, maske: list):
        """Formen mit Prüfziffer, Kfz-Kennzeichen, BIC, Ausweis-/ID-artige Werte, Werte hinter Kennungs-Etiketten."""
        o = z.start
        for m in _IBAN_RE.finditer(zeile):
            if _GLAEUBIGER_ID_RE.match(m.group(1)) or self.org_konto(o + m.start(1)) \
                    or _GLAEUBIGER_ETIKETT_RE.search(zeile[max(0, m.start() - 40):m.start()]):
                continue                             # Gläubiger-ID (auch "ZZZ" als "222" gelesen), Bankverbindung der
                                                     # Organisation in ihrem Fußbereich
            if m.group(1)[:2] == "DE" or iban_gueltig(m.group(1)) or _ziffern(m.group(1)) >= 10:
                grund = "IBAN (Prüfziffer gültig)" if iban_gueltig(m.group(1)) else "IBAN-Form"
                self.neu(o + m.start(1), o + m.end(1), grund, "form")
        for m in _IBAN_DE_LOSE_RE.finditer(zeile):
            if not self.org_konto(o + m.start(1)):
                self.neu(o + m.start(1), o + m.end(1), "IBAN-Form", "form")
        for m in _IBAN_KAMM_RE.finditer(zeile):         # Kästchen eines Formulars: "D E  6 9  9 1 4 9 …"
            ende = self._kamm_iban_ende(m)
            if ende is not None and not self.org_konto(o + m.start(1)):
                self.neu(o + m.start(1), o + ende, "IBAN in Kästchenschrift", "form")
        if self._herkunft(z) != "text":
            for m in _IBAN_KAMM_OCR_RE.finditer(zeile):
                if self._kamm_iban_ocr(m.group(1)) and not self.org_konto(o + m.start(1)) \
                        and not any(maske[m.start(1):m.end(1)]):
                    self.neu(o + m.start(1), o + m.end(1), "IBAN-Form in Kästchenschrift (verlesen)", "form")
        for m in _SVNR_RE.finditer(zeile):
            grund = ("Sozialversicherungsnummer (Prüfziffer gültig)" if sv_nummer_gueltig(m.group(1))
                     else "Sozialversicherungsnummer-Form")
            self.neu(o + m.start(1), o + m.end(1), grund, "form")
        for m in _KVNR_RE.finditer(zeile):
            if self.im_fussbereich(o + m.start(1)) and self.org_wert(o + m.start(1), o + m.end(1)):
                continue                             # im Fußbereich: Rest einer USt-IdNr. ("DE904950392")
            grund = ("Krankenversichertennummer (Prüfziffer gültig)" if kvnr_gueltig(m.group(1))
                     else "Krankenversichertennummer-Form")
            self.neu(o + m.start(1), o + m.end(1), grund, "form")
        for m in _FIN_RE.finditer(zeile):
            self.neu(o + m.start(1), o + m.end(1), "Fahrzeug-Identnummer (FIN)-Form", "form")
        for m in _KARTE_RE.finditer(zeile):
            if luhn_gueltig(m.group(1)):
                self.neu(o + m.start(1), o + m.end(1), "Kreditkartennummer (Prüfziffer gültig)", "form")
        for m in _KFZ_RE.finditer(zeile):
            kuerzel, trenner, ziffern = m.group(1), m.group(2), m.group(4)
            if kuerzel in _KFZ_SPERRE or any(maske[m.start():m.end()]):
                continue
            if trenner != "-" and len(ziffern) == 4 and ziffern[:2] in ("19", "20"):
                continue                             # "SGB VI 2023"
            if _ORG_NUMMER_RE.search(zeile[max(0, m.start() - 30):m.start()]):
                continue                             # Register-, Formularnummern – ein Kennzeichen hat keine
            self.neu(o + m.start(), o + m.end(), "Kfz-Kennzeichen-Form", "form")
        for m in _BIC_RE.finditer(zeile):
            davor = zeile[max(0, m.start() - 40):m.start()]
            zelle_davor = re.split(r"\t", zeile[:m.start()])[-1][-60:]
            # hinter "BIC"/"SWIFT", einer IBAN oder einer Bankangabe derselben Zelle ("Kreditinstitut (Name und BIC):
            # Postbank Ndl. Mitte JSWVDEVC") – die Bank des Kunden ist keine Angabe des Absenders
            if not (re.search(r"(?i)(BIC|SWIFT)[\s.:]*$", davor)
                    or re.search(r"\b[A-Z]{2}\d{2}[\s\dA-Z]{8,}\s*$", davor) or _BANKNAME_RE.search(zelle_davor)
                    or re.search(r"(?<![\w])(?:BIC|SWIFT)(?![\w])", zelle_davor)):
                continue
            if self.org_konto(o + m.start(1)) or (not self.im_fussbereich(o + m.start(1))
                                                  and self.org_wert(o + m.start(1), o + m.end(1))):
                continue                             # Bankverbindung der Organisation (Fußbereich, Briefkopf)
            self.neu(o + m.start(1), o + m.end(1), "BIC (Bankverbindung)", "form")
        # ID-artige Werte: 8-12 Zeichen Großbuchstaben + Ziffern; hinter einem Ausweis-Etikett auch kürzer/länger
        for m in re.finditer(r"(?<![\w\-/.])([A-Z0-9]{6,14})(?![\w\-/])", zeile):
            wert = m.group(1)
            ziffern = _ziffern(wert)
            buchstaben = len(wert) - ziffern
            if not ziffern or buchstaben < 1 or any(maske[m.start():m.end()]):
                continue
            davor = zeile[max(0, m.start() - 40):m.start()]
            if _ORG_NUMMER_RE.search(davor) or _GLAEUBIGER_ID_RE.match(wert):
                continue
            mit_etikett = bool(_AUSWEIS_ETIKETT_RE.search(davor))
            id_artig = 8 <= len(wert) <= 12 and buchstaben >= 2 and not re.fullmatch(r"[A-Z]{2,4}\d{1,3}", wert)
            if id_artig and not mit_etikett and self.org_wert(o + m.start(1), o + m.end(1)):
                continue                             # USt-IdNr., BIC, Register-Nr. der Organisation (auch verlesen)
            if mit_etikett or id_artig:
                if icao_gueltig(wert):
                    grund = "Ausweisnummer (Prüfziffer gültig)"
                elif mit_etikett:
                    grund = "Ausweis-/Dokumentnummer hinter Etikett"
                else:
                    grund = "kennungsartige Zeichenfolge (Ausweis-/Dokumentnummer?)"
                self.neu(o + m.start(1), o + m.end(1), grund, "form")
        # Kennungen mit eigener Wertform hinter ihrem Etikett (eVB-Nummer, Transferticket, Kartenprüfnummer)
        self._formen_hinter_etikett(z, zeile, maske)
        # Kennungs-Etikett + Wert mit Ziffern (auch kurze: "Az. 123 C 45/24")
        index = self.w.index("kennung")
        if index is None:
            return
        try:
            treffer = index.finde(zeile)
        except Exception:
            return
        for v in treffer:
            if v.start > 0 and zeile[v.start - 1].isalnum():
                continue
            wert = re.match(r"[ \t]*[:.#]?[ \t]*([A-ZÄÖÜ0-9][^\t]{1,30}?)(?=\t|$|[ ]{2}|,\s|;|\s[a-zäöü])",
                            zeile[v.ende:])
            if not wert:
                continue
            w = wert.group(1).strip(" .:|")
            s = v.ende + wert.start(1)
            mindest = 1 if re.search(r"(?i)kennz|kfz", v.text) else 2
            if re.match(r"(?i)(?:seite|blatt|page|s\.)\s?\d", w) or self.w.ist_etikett((w.split() or [w])[0]):
                continue
            kopf = re.match(r"([^\W\d_][\w\-]*(?:[ ][^\W\d_][\w\-]*){0,2})[ ]?:", w)
            if kopf and self.w.ist_etikett(kopf.group(1)):
                continue                                # das nächste Etikett ("Mein Zeichen: …", Befund 83)
            if (_ziffern(w) < mindest or len(w) < 3 or _ORG_NUMMER_RE.search(zeile[:v.ende])
                    or re.fullmatch(r"[\d\s.,]+[€%]?", w) or any(maske[s:s + len(w)]) or _GLAEUBIGER_ID_RE.match(w)
                    or self.ist_platzhalter_bei(o + s, o + s + len(w))):
                continue
            if kennungsformen.etikett_art(v.text) is not None and not (
                    kennungsformen.nummer_etikett(v.text) and kennungsformen.kennungsform(w)):
                continue                                # eVB/Transferticket/CVC: eigene Regel ("SF 12", "250 Euro")
            if _UST_ID_RE.fullmatch(w) and _UST_ETIKETT_RE.search(zeile[:s]):
                continue                                # USt-IdNr. hinter verlesenem Etikett ("uat-ıdNr."); hinter
                                                        # "Kundennummer" bleibt die Form DE + 9 Ziffern Verdacht
            if self.org_wert(o + s, o + s + len(w)):
                continue                                # Steuernummer, IBAN der Organisation (Fußbereich, Briefkopf)
            self.neu(o + s, o + s + len(w), f"Wert hinter Etikett »{v.text}«", "etikett")

    def _wissen_frage(self, name: str, wort: str) -> bool:
        return self.w.frage(name, wort)

    def _geburtsname_etiketten(self):
        """Name hinter dem Feld-Etikett "Geburtsname" / "Geb.-Name" – dieselbe Regel wie die Erkennung
        (kennungsformen.geburtsname_hinter_etikett): direkt dahinter, in der Zelle daneben, hinter Zwischenwörtern bis
        zu einer Ankündigung ("Geburtsname, falls abweichend: …", "Geburtsname (falls vom Familiennamen abweichend):
        …"); nicht das nächste Feld-Etikett hinter einem leeren Feld, nicht die Zelle daneben in einer Kopfzeile."""
        for m in kennungsformen.GEBURTSNAME_ETIKETT_RE.finditer(self.text):
            sp = kennungsformen.geburtsname_hinter_etikett(self.text, m, ist_etikett=self.w.ist_etikett,
                                                           frage=self._wissen_frage)
            if sp is None or self.ist_gesperrt(sp.start, sp.ende) or self.ist_platzhalter_bei(sp.start, sp.ende):
                continue
            wort = self.text[sp.start:sp.ende].split()[-1]
            if wort.casefold() in _GEBURTSNAME_FUELLWORT or self.w.art(_titel(wort))[4]:
                continue                                # "Geburtsname: Siehe oben", Allerweltswort
            if sp.getrennt and self._wort_harmlos(_titel(wort)):
                continue                                # "Geburtsname:" ⏎ "Komfort", "Wohneigentum": kein Name
            self.neu(sp.start, sp.ende, f"möglicher Geburtsname (hinter »{' '.join(m.group(0).split())}«)", "name")

    def _zb1_felder(self):
        """Name oder Vornamen in den Feldern C.1.1/C.1.2 einer Zulassungsbescheinigung Teil I – dieselbe Regel wie die
        Erkennung (personenkontext.zb1_personenfelder), auch ein einzelner Nachname in Versalien."""
        for s, e in personenkontext.zb1_personenfelder(self.text):
            stueck = self.text[s:e]
            if self.ist_platzhalter_bei(s, e) or not any(c.isalpha() for c in stueck):
                continue
            self.neu(s, e, "Name im Feld C.1.1/C.1.2 der Zulassungsbescheinigung", "name")
        # Anschrift im Feld C.1.3 (dasselbe Anschrift-Etikett wie in der Erkennung): jedes lesbare Wort außerhalb der
        # Platzhalter ("C.1.3  HOFMARK 7, [PLZ ORT]" -> "HOFMARK 7")
        for s, e in personenkontext.zb1_anschriftfelder(self.text):
            woerter = [(s + m.start(), s + m.end()) for m in re.finditer(r"[^\W_][\w.\-/]*", self.text[s:e])
                       if not (self.ist_platzhalter_bei(s + m.start(), s + m.end())
                               or self.ist_gesperrt(s + m.start(), s + m.end()))]
            if woerter:
                self.neu(woerter[0][0], woerter[-1][1], "Anschrift im Feld C.1.3 der Zulassungsbescheinigung",
                         "anschrift")

    def _sachwort(self, wort: str) -> bool:
        """Allerweltswort, Ort oder Organisation der Erlaubnisliste (wie wissen_namen._sachwort)."""
        art = self.w.art(wort)
        return art[4] or art[6] or self.w.frage("ist_ort", wort)

    def _gemeinschaften(self):
        """Familienname einer GbR oder Erbengemeinschaft ("Felsberger GbR") – dieselbe Regel wie die Erkennung
        (personenkontext.gemeinschaft_namen)."""
        for s, e in personenkontext.gemeinschaft_namen(self.text, self._sachwort):
            if not self.ist_platzhalter_bei(s, e):
                self.neu(s, e, "Name einer GbR oder Gemeinschaft", "name")

    def _formen_hinter_etikett(self, z, zeile: str, maske: list):
        """Wert hinter dem Etikett einer eVB-Nummer, eines Transfertickets oder einer Kartenprüfnummer – mit der Form
        der jeweiligen Kennung, also auch kurz und mit nur einer Ziffer ("eVB: A1BCDEF", "CVC 123"), die die Regeln
        für Ziffernfolgen und Etikett + Wert nicht melden. Dieselbe Regel wie die Erkennung (kennungsformen.kennungen):
        der Wert direkt hinter dem Etikett, am Anfang der nächsten Zeile bzw. in der Zelle daneben oder hinter
        Zwischenwörtern desselben Satzes bis zu einer Ankündigung ("Die eVB-Nummer Ihres neuen Fahrzeugs lautet: …",
        "Die CVC auf der" ⏎ "Rückseite ist 739."); eine eVB auch mit Einfügungen der Texterkennung ("K7/H3MY9P");
        "Prüfnummer" und "Sicherheitscode" allein nur mit einer Kartenangabe (auch dem Platzhalter einer Kreditkarte) in
        der Nähe und ohne fremden Bezug. Dazu Werte in Tabellenspalten mit einem solchen Etikett im Kopf
        (_spalten_kennungen)."""
        funde = self._org.get("kennungsfunde")
        if funde is None:
            funde = {}
            for f in kennungsformen.kennungen(self.text, ocr=True, wortgestalt=self.w.wortgestalt,
                                              ist_etikett=self.w.ist_etikett,
                                              kartenbezug_extra=_KREDITKARTE_PLATZHALTER_RE):
                zf = self.zeile(f.start)
                if zf is not None:
                    funde.setdefault(zf.id, []).append(
                        (f.start, f.ende, f"{_FORM_GRUND[f.art]} hinter Etikett »{' '.join(f.etikett.split())}«"))
            for s0, e0, grund in self._spalten_kennungen():
                zf = self.zeile(s0)
                if zf is not None:
                    funde.setdefault(zf.id, []).append((s0, e0, grund))
            self._org["kennungsfunde"] = funde
        for g_s, g_e, grund in funde.get(z.id, ()):
            ls, le = g_s - z.start, min(g_e, z.ende) - z.start
            if any(maske[max(0, ls):max(0, le)]) or self.ist_gesperrt(g_s, g_e) or self.ist_platzhalter_bei(g_s, g_e):
                continue
            self.neu(g_s, g_e, grund, "etikett")

    def _zeilen_nach_lage(self) -> list:
        """Zeilen mit Lage auf der Seite, von oben nach unten (zwischengespeichert)."""
        if "zeilen_lage" not in self._org:
            self._org["zeilen_lage"] = sorted((y for y in self.m.zeilen if y.rect is not None),
                                              key=lambda y: (y.rect.y0, y.rect.x0))
        return self._org["zeilen_lage"]

    def _spalten_kennungen(self) -> list:
        """(start, ende, Grund) der Werte in Tabellenspalten mit dem Etikett einer eVB-Nummer, eines Transfertickets
        oder einer Kartenprüfnummer im Kopf ("eVB-Nummer" über "KXH4PMQ"), auch mit einem Kopf über zwei Zeilen
        ("Versicherungs-" ⏎ "bestätigung"); "Prüfnr." nur in einer Kopfzeile mit Kartenangabe ("Kartennummer"). Unter
        dem Kopf zählt ein Wert nur mit Ziffer (eVB, Transferticket) bzw. als ganze Zelle ohne Einheit
        (Kartenprüfnummer). Gelesen wird von jedem Kopf abwärts bis zu einer Absatzlücke – je Kopf höchstens
        SPALTE_ZEILEN Zeilen (die Prüfung wächst linear mit der Seite)."""
        text = self.text
        if not kennungsformen.ETIKETT_RE.search(text) and "-\t" not in text and not re.search(r"-[ \t]*\n", text):
            return []
        zeilen = self._zeilen_nach_lage()
        aus = []
        for i, z in enumerate(zeilen):
            zt = self.zeilen_text(z)
            zellen = list(re.finditer(r"[^\t]+", zt))
            if len([zm for zm in zellen if zm.group(0).strip()]) < 2:
                continue                                # Kopfzeile einer Tabelle: mehrere Zellen
            for zm in zellen:
                inhalt = zm.group(0).strip()
                if not inhalt or len(inhalt) > 40 or inhalt.endswith(":"):
                    continue                            # "CVC:" ist ein Feld, kein Spaltenkopf
                cs = z.start + zm.start() + (len(zm.group(0)) - len(zm.group(0).lstrip()))
                ce = cs + len(inhalt)
                b = self.box(cs, ce)
                if b is None:
                    continue
                kopf, art, erste = inhalt, kennungsformen.etikett_art(inhalt), i + 1
                if art is None and inhalt.endswith("-") and i + 1 < len(zeilen):
                    unten, _, _ = self.zelle_ueber(zeilen[i + 1], b.x0, b.x1)
                    unten = unten.strip()
                    for v in (inhalt[:-1] + unten, inhalt + unten):
                        art = kennungsformen.etikett_art(v) if unten else None
                        if art is not None:
                            kopf, erste = v, i + 2
                            break
                if art is None:
                    continue
                if art == "pruef" and not kennungsformen.KARTENANGABE_RE.search(zt):
                    continue                            # "Prüfnr." nur neben "Kartennummer"/"Kreditkarte"
                form = "cvc" if art == "pruef" else art
                hoehe = max(z.rect.height, 8.0)
                unten_y = z.rect.y1 if erste == i + 1 else zeilen[i + 1].rect.y1
                for y in zeilen[erste:erste + SPALTE_ZEILEN]:
                    if y.rect.y0 - unten_y > 2.5 * hoehe:
                        break                           # Absatz: die Tabelle ist zu Ende
                    unten_y = max(unten_y, y.rect.y1)
                    zelle, zs, ze = self.zelle_ueber(y, b.x0, b.x1)
                    if not zelle.strip():
                        continue
                    if kennungsformen.etikett_art(zelle.strip()) is not None:
                        break                           # nächster Kopf
                    vorn = len(zelle) - len(zelle.lstrip())
                    w = kennungsformen.WERT_RE[form].match(text, zs + vorn, ze)
                    if w is None or text[w.end():ze].strip(" .,;)"):
                        continue                        # nur die ganze Zelle ("2024 wurde …" ist Fließtext)
                    wert = w.group(0)
                    if form == "evb" and not any(c.isdigit() for c in wert):
                        continue
                    if form == "ticket" and not (any(c.isdigit() for c in wert)
                                                 and kennungsformen.ticket_gueltig(wert, True)):
                        continue
                    if form == "cvc" and kennungsformen.EINHEIT_DANACH_RE.match(text, w.end(), ze):
                        continue
                    aus.append((w.start(), w.end(), f"{_FORM_GRUND[form]} in der Spalte »{' '.join(kopf.split())}«"))
        return aus

    # Datumsangaben
    def _datum(self, m, art):
        try:
            if art == "tmj":
                tag, monat, jahr = int(m.group(1)), int(m.group(2)), _jahr_aus(m.group(3))
            elif art == "jmt":
                jahr, monat, tag = int(m.group(1)), int(m.group(2)), int(m.group(3))
            else:
                tag, jahr = int(m.group(1)), int(m.group(3))
                monat = _MONATE.get(m.group(2).lower().rstrip("."), 0)
            return datetime.date(jahr, monat, tag)
        except (ValueError, TypeError):
            return None

    def _daten(self, z, zeile: str):
        heute = _heute()
        for m in _GEBURTSJAHR_RE.finditer(zeile):
            if heute.year - ALTER_MAX <= int(m.group(1)) <= heute.year:
                s, e = z.start + m.start(1), z.start + m.end(1)
                if not (self.ist_gesperrt(s, e) or self.ist_platzhalter_bei(s, e)):
                    self.neu(s, e, "Geburtsjahr hinter Etikett", "datum")
        alle = []
        for regex, art in self._datumsformen(z):
            for m in regex.finditer(zeile):
                datum = self._datum(m, art)
                if datum is not None:
                    alle.append((m.start(), m.end(), datum))
        # jedes Datum einmal: die OCR-Formen treffen ein gewöhnliches "14.03.1961" ein zweites Mal mit derselben
        # Spanne – die Kopie wäre sonst der Nachbar ohne Zwischentext, das Datum ein "Zeitraum" (kein Geburtsdatum
        # gemeldet)
        eindeutig = []
        for t in sorted(alle, key=lambda t: (t[0], -t[1])):
            if not any(a <= t[0] and t[1] <= b for a, b, _ in eindeutig):
                eindeutig.append(t)
        alle = eindeutig
        # Partner eines Zeitraums ist auch Monat/Jahr ("08.1987 31.12.1989") und auf OCR-Zeilen ein verlesenes Datum
        # ("j01..01.2004 31.12.2010", "06.36.1896 31.12.2003"); selbst kein Geburtsdatum
        formen = [_MONAT_JAHR_IN_ZEILE_RE] + ([_DATUM_VERLESEN_RE] if self._herkunft(z) != "text" else [])
        partner = sorted(alle + [(m.start(), m.end(), None) for regex in formen for m in regex.finditer(zeile)
                                 if not any(a < m.end() and m.start() < b for a, b, _ in alle)], key=lambda t: t[0])
        for ms, me, datum in alle:
            k = next(i for i, t in enumerate(partner) if t[0] == ms and t[1] == me)
            if datum > heute:
                continue
            alter = heute.year - datum.year - ((heute.month, heute.day) < (datum.month, datum.day))
            s, e = z.start + ms, z.start + me
            etikett = None
            if re.match(r"\s?\(?(?:geboren|geb\.|Geburtsdatum|Geburtstag)", zeile[me:me + 16], re.IGNORECASE):
                etikett = ("datum_geburt", "geboren")
            if etikett is None:
                etikett = self.etikett_davor(s, e, ("datum_geburt", "vertragsdaten"))
                if etikett is not None and etikett[0] == "vertragsdaten" and etikett[1].islower() \
                        and len(etikett[1]) <= 4:
                    # "am"/"vom" sind Füllwörter: "die Geburt unserer Tochter am 14.09.2026" – das Geburts-Etikett
                    # davor zählt, wenn es im selben Satzteil steht (kein Komma dazwischen) und nicht selbst schon
                    # sein Datum ankündigt ("geboren am [GEB-DATUM] ist am 31.03.2025 verstorben")
                    geburt = self.etikett_davor(s, e, ("datum_geburt",))
                    if geburt is not None and re.search(r"(?i)(?<![^\W\d_])(?:am|vom|den)$", geburt[1].strip()):
                        geburt = None
                    pos = zeile.rfind(geburt[1], 0, ms) if geburt is not None else -1
                    if pos >= 0 and not re.search(r"[,;:]", zeile[pos + len(geburt[1]):ms]):
                        etikett = geburt
            if etikett is None:
                etikett = self.spaltenkopf(s, e, ("datum_geburt", "vertragsdaten"), streng=False)
            if etikett is not None and etikett[0] == "datum_geburt":
                if alter <= 120:
                    self.neu(s, e, f"Datum hinter Etikett »{etikett[1]}«", "datum")
                continue
            if etikett is None and 0 <= alter < ALTER_MIN and self._familien_datum(z, ms, me):
                self.neu(s, e, "Datum an einer Person im Familien-/Versichertenkontext (Geburtsdatum?)", "datum")
                continue
            if etikett is not None or not (ALTER_MIN <= alter <= ALTER_MAX):
                continue
            if personenkontext.behandlungsdatum(zeile[:ms].rstrip(" \t,(*-–"), zeile, me):
                continue                    # "Dr. [PERSON A], 03.11.2012: Meniskusoperation": Behandlungsdatum
            # Zeitraum: "01.09.1985 – 31.08.1988", "von … bis …", zwei Daten nebeneinander in einer Tabellenzeile
            if _BEREICH_DANACH_RE.match(zeile[me:me + 8]) or _BEREICH_DAVOR_RE.search(zeile[max(0, ms - 10):ms]):
                continue
            nachbarn = [x for x in (partner[k - 1] if k else None, partner[k + 1] if k + 1 < len(partner) else None)
                        if x]
            if any(not zeile[min(me, x[1]):max(ms, x[0])].strip(" \t-–—/|[]\\") for x in nachbarn):
                continue
            if not zeile[:ms].strip(_OCR_RAND) and not zeile[me:].strip(_OCR_RAND) and self._datum_daneben(z, datum):
                continue                    # Datum allein in seiner Zelle, rechts daneben das Ende des Zeitraums
            self.neu(s, e, "Datum mit möglichem Geburtsjahr", "datum")

    def _familien_datum(self, z, ms: int, me: int) -> bool:
        """Steht das Datum (Zeile z, Spanne ms:me) im Familien-/Versichertenkontext direkt an einer Person: links davon
        ein Personen-Platzhalter oder ein Vor-/Nachname der Wissensbasis, dazwischen nur Komma, Klammer, Stern,
        Bindestrich oder Tabulator ("Kind 2: [PERSON A], 30.06.2018", "Kinder: Ben (02.05.2019)") – nicht an einem
        Behandler und nicht vor einem Behandlungstext (personenkontext.behandlungsdatum)?"""
        text, zeile = self.text, self.zeilen_text(z)
        davor = zeile[:ms]
        trenner = _FAMILIE_TRENNER_RE.search(davor)
        if trenner is None:
            return False
        vorn = davor[:trenner.start()]
        name_start = None
        m = _PERSON_PLATZHALTER_ENDE_RE.search(vorn)
        if m:
            name_start = m.start()
        else:
            w = re.search(r"([^\W\d_][\w'’\-]*)$", vorn)
            if w and w.group(1)[:1].isupper():
                vn, nn, vnm, nnm, aw, tit, allow, part = self.w.art(w.group(1))
                if (vn or nn) and not (aw or tit or allow):
                    name_start = w.start(1)
        if name_start is None:
            # auf der Seite: das graue Rechteck eines Personen-Platzhalters links neben dem Datum, dazwischen nur
            # Satzzeichen (die Schwärzung schreibt den Platzhalter nicht an die Stelle des Namens im Text)
            b = self.box(z.start + ms, z.start + me)
            for ps, pe, rand in (self.platzhalter_boxen() if b is not None else ()):
                if not _PERSONEN_PLATZHALTER_RE.match(text[ps:pe]) or rand[2] > b.x0 + 1:
                    continue
                if self._benachbart(b, rand, 3.0) and not any(re.search(r"[^\W_]", t) for t in
                                                              self._woerter_zwischen(z, rand[2], b.x0)):
                    name_start = len(davor[:trenner.start()].rstrip(" \t,(*-–"))
                    break
        if name_start is None:
            return False
        if personenkontext.behandlungsdatum(davor[:name_start], zeile, me):
            return False
        a = z.start
        if not personenkontext.familien_kontext(text, a, a + name_start):
            return False
        if not personenkontext.familien_rolle_in_zeile(text, a, a + name_start) \
                and personenkontext.BETRAG_IN_ZEILE_RE.search(zeile):
            return False                    # Leistungs- oder Rechnungsliste unter "Kinder:"
        return True

    def _woerter_zwischen(self, z, x0: float, x1: float) -> list:
        """Wörter der Zeile z, deren Box zum guten Teil zwischen x0 und x1 liegt."""
        aus = []
        for m in re.finditer(r"\S+", self.zeilen_text(z)):
            wb = self.box(z.start + m.start(), z.start + m.end())
            if wb is not None and min(wb.x1, x1) - max(wb.x0, x0) >= 1.0:
                aus.append(m.group(0))
        return aus

    def _datum_daneben(self, z, datum) -> bool:
        """Steht rechts neben der Zeile z in derselben Reihe (eigene Zeile des Seitenmodells: Tabellenspalte) allein ein
        späteres Datum – das Ende eines Zeitraums ("01.06.2005" | "31.05.2010" im Versicherungsverlauf)?"""
        if z.rect is None:
            return False
        for y in self.m.zeilen:
            r = y.rect
            if y.id == z.id or r is None or r.x0 < z.rect.x1 - 1 or r.x0 > z.rect.x1 + 250:
                continue
            if min(r.y1, z.rect.y1) - max(r.y0, z.rect.y0) < 0.5 * min(r.height, z.rect.height):
                continue
            inhalt = self.zeilen_text(y).strip(_OCR_RAND)
            for regex, art in _DATUM_RES:
                m = regex.match(inhalt)
                if m and m.end() >= len(inhalt.split()[0]):
                    anderes = self._datum(m, art)
                    if anderes is not None and anderes > datum:
                        return True
        return False

    # Kontakt: @, +Ländervorwahl, Namen in Internetadressen
    def _kontakt(self, z, zeile: str):
        o = z.start
        for m in _EMAIL_RE.finditer(zeile):
            lokal = m.group(1).lower().strip(".")
            if lokal in _FUNKTIONSPOSTFAECHER or re.sub(r"[\d._\-]+$", "", lokal) in _FUNKTIONSPOSTFAECHER:
                continue
            self.neu(o + m.start(), o + m.end(), "E-Mail-Adresse", "kontakt")
        for m in _PLUS_CC_RE.finditer(zeile):
            ende = m.end()
            while (ende < len(zeile) and (zeile[ende].isdigit() or zeile[ende] in " ()/-")
                   and zeile[ende:ende + 2] != "  "):
                ende += 1
            stueck = zeile[m.start():ende].rstrip(" ()/-")
            if _ziffern(stueck) < 6 or _SERVICE_NUMMER_RE.search(stueck.replace("(0)", "")) or stueck.endswith("-0"):
                continue
            if self.org_kontext(o + m.start()):
                continue
            self.neu(o + m.start(), o + m.start() + len(stueck), "internationale Telefonnummer (+Ländervorwahl)",
                     "kontakt")
        for m in _URL_RE.finditer(zeile):
            if "@" in zeile[max(0, m.start() - 1):m.start()] or self.org_kontext(o + m.start(1)):
                continue                             # Internetauftritt der Organisation (Briefkopf, Fußzeile)
            for teil in re.split(r"[./\-_~:?#=&+]+", m.group(1)):
                if len(teil) < 4 or teil.lower() in ("http", "https", "www"):
                    continue
                vn, nn, vnm, nnm, aw, *_ = self.w.art(teil.capitalize())
                if ((vn and not vnm) or (nn and not nnm)) and not aw:
                    self.neu(o + m.start(1), o + m.end(1), "Name in Internetadresse", "kontakt")
                    break

    # Anschriften
    def _anschriften(self, z, zeile: str):
        o = z.start
        for regex in (_STRASSE_RE, _STRASSE_PRAEP_RE):
            for m in regex.finditer(zeile):
                s = o + m.start()
                wort = m.group(1).strip()
                if not wort[:1].isupper() or self.org_kontext(s):
                    continue
                if re.fullmatch(r"(?i)" + _STRASSEN_ENDUNG + r"\.?", wort):
                    continue                                 # "Zeile 5", "Weg 3", "Grund 2" – kein Straßenname
                if re.match(r"(?i)(?:seite|tel|fax|nr|abs|ziff|anlage|tarif|stand|version|kapitel|punkt)\b", wort):
                    continue
                self.neu(s, o + m.end(), "Anschrift (Straße + Hausnummer)", "anschrift")
        for m in _POSTFACH_RE.finditer(zeile):
            if not self.org_kontext(o + m.start()):
                self.neu(o + m.start(), o + m.end(), "Postfach", "anschrift")
        # Werte hinter Anschrift-Etiketten ("Ort: Jena", "Wohnort Frankfurt am Main")
        index = self.w.index("adresse")
        if index is None:
            return
        try:
            treffer = index.finde(zeile)
        except Exception:
            return
        for v in treffer:
            if v.text.lower() in ("nr.", "str.", "land", "staat", "kreis", "bezirk", "zusatz", "etage", "city",
                                  "country", "bundesland", "kanton", "standort", "gemeinde", "app.", "c/o",
                                  "z. hd.", "z.hd.", "zu händen") or (v.start > 0 and zeile[v.start - 1].isalnum()):
                continue
            wert = re.match(r"[ \t]*:?[ \t]*([A-ZÄÖÜ][\wäöüßÄÖÜ.'\-]+(?:[ ](?:am|an|im|in|bei|ob|der|v\.|d\.|"
                            r"[A-ZÄÖÜ(][\wäöüßÄÖÜ.\-)]*)){0,4})", zeile[v.ende:])
            if not wert:
                continue
            s = v.ende + wert.start(1)
            text = wert.group(1)
            if self.ist_platzhalter_bei(o + s, o + s + len(text)):
                continue
            erstes = text.split()[0]
            if text.isupper() and not any(c.isdigit() for c in text) and self._quelle(o + s) != "text":
                continue                                # OCR-Salat ("EIS EFESEHE")
            if self.org_kontext(o + s) or ("\t" in zeile[v.ende:s] and self._kopfzeile(z)):
                continue                                # Kopfzeile einer Tabelle: "PLZ / Ort ⇥ Sparte ⇥ Versicherer"
            if erstes.lower().rstrip(".") in _STRASSEN_ANFANG:
                self._strassenwert(z, zeile, s, v.text)  # "Anschrift: Straße des 17. Juni 72", "Am Markt 3"
                continue
            if len(text.split()) > 1 and re.search(r"(?i)ort$", v.text.strip()) \
                    and self.w.frage("ist_ortsgattung", erstes):
                # "Unfallort: Skigebiet Sudelfeld": der Ort ist der Eigenname hinter den Gattungswörtern – dieselbe
                # Regel wie die Erkennung hinter Ort-Etiketten (wissen.ortsname_hinter_gattung)
                woerter = list(re.finditer(r"[^\s,;()/]+", text))
                try:
                    n = self.w.modul.ortsname_hinter_gattung([w.group(0) for w in woerter])
                except Exception:
                    n = 0
                if n is None:
                    continue                            # nur Gattungswörter, Einrichtung oder Straße
                s, text = s + woerter[n].start(), text[woerter[n].start():]
                erstes = text.split()[0]
                if self.ist_platzhalter_bei(o + s, o + s + len(text)):
                    continue
            vn, nn, vnm, nnm, aw, tit, allow, _ = self.w.art(erstes)
            if aw or tit or allow or erstes.lower() in _STOPPWOERTER or self.w.ist_etikett(erstes):
                continue
            self.neu(o + s, o + s + len(text), f"Angabe hinter Etikett »{v.text}«", "anschrift")

    def _umbrochene_strasse(self, z, zeile: str):
        """Straßenname am Ende einer Zelle in einer Spalte mit Anschrift-Etikett im Kopf, die Hausnummer am Anfang
        derselben Zelle in der Zeile darunter ("Am Gänsbichl" ⏎ "4, 84453 Mühldorf a. Inn": Zellumbruch einer
        Bestandsliste, Befund 84) – die Erkennung liest die Zelle als Ganzes (struktur_tabelle)."""
        o = z.start
        for m in re.finditer(r"[^\t]+", zeile):
            zelle = m.group(0).strip(" ,")
            if not zelle or len(zelle.split()) > 4 or not _STRASSENNAME_ZELLE_RE.fullmatch(zelle):
                continue
            s = o + m.start() + m.group(0).index(zelle)
            e = s + len(zelle)
            if self.ist_gesperrt(s, e) or self.org_kontext(s) or self.w.ist_etikett(zelle.split()[-1]):
                continue
            b = self.box(s, e)
            unten = self.zeile_darunter(z, b.x0, b.x1) if b is not None else None
            if unten is None:
                continue
            darunter, ds, _ = self.zelle_ueber(unten, b.x0, b.x1)
            nummer = _HAUSNUMMER_VORN_RE.match(darunter)
            if nummer is None or self.spaltenkopf(s, e, ("adresse",)) is None:
                continue
            self.neu(s, e, "Anschrift (Straße + Hausnummer)", "anschrift")
            ns, ne = ds + nummer.start(1), ds + nummer.end(1)
            if not self.ist_gesperrt(ns, ne):
                self.neu(ns, ne, "Anschrift (Straße + Hausnummer)", "anschrift")

    def _betragsform_unter_kennungskopf(self, z, zeile: str):
        """Ganze Zelle in Betragsform ohne Nachkommastellen ("7.712.345") unter einem Kennungs-Spaltenkopf
        ("Vertrag", "Vers.-Nr."): dort eine Vertrags- oder Kennnummer mit Tausenderpunkten – die Maske der Beträge
        verdeckt sie sonst. Dieselbe Regel wie die Erkennung (struktur_tabelle._nummer_in_betragsform)."""
        o = z.start
        for m in re.finditer(r"[^\t]+", zeile):
            zelle = m.group(0).strip()
            if not _BETRAGSFORM_ZELLE_RE.fullmatch(zelle) or _ziffern(zelle) < MIN_ZIFFERN:
                continue
            s = o + m.start() + m.group(0).index(zelle)
            e = s + len(zelle)
            if self.ist_gesperrt(s, e) or self.org_kontext(s) or self.spaltenkopf(s, e, ("kennung",)) is None:
                continue
            self.neu(s, e, "Ziffernfolge unter einem Kennungs-Spaltenkopf (Nummer mit Tausenderpunkten)", "kennung")

    def _platzhalter_darunter(self, z) -> bool:
        """Beginnt die Zeile unter z (auf der Seite, nicht in der Textfolge – Platzhalter stehen im Modell als eigene
        Zeilen) mit einem Platzhalter?"""
        if z.rect is None:
            return False
        h = max(z.rect.height, 4.0)
        for _, _, (x0, y0, x1, y1) in self.platzhalter_boxen():
            mitte = (y0 + y1) / 2
            if z.rect.y1 - 0.2 * h <= mitte <= z.rect.y1 + 1.6 * h and x0 <= z.rect.x0 + 3 * h:
                return True
        return False

    def _strassenwert(self, z, zeile: str, s: int, etikett: str):
        """Straßenname hinter einem Anschrift-Etikett, der mit einem gewöhnlichen Wort beginnt ("Straße des 17. Juni
        72", "Am Markt 3", "Platz der Republik 1"): der Wert bis zum Ende der Zelle; endet die Zeile mitten im
        Straßennamen (Artikel am Ende, noch keine Hausnummer), gehört der Anfang der nächsten Zeile dazu."""
        o = z.start
        wert = re.match(r"[^\t,;]*", zeile[s:])
        ende = s + len(wert.group(0).rstrip(" .:"))
        if ende <= s or self.ist_platzhalter_bei(o + s, o + ende):
            return
        fortsetzung = None
        if not any(c.isdigit() for c in zeile[s:ende]) and not zeile[ende:].strip():
            if self._platzhalter_darunter(z):
                return                                  # der Rest der Anschrift ist geschwärzt ("Am Alten" / [ADRESSE])
            a = z.ende + 1
            while a < len(self.text) and self.text[a] in " \n":
                a += 1
            treffer = re.match(r"(?:\d{1,2}\.\s?[A-ZÄÖÜ][a-zäöü]+\.?\s)?\d{1,4}\s?[a-zA-Z]?(?![\w])",
                               self.text[a:a + 40])
            if treffer and not self.ist_platzhalter_bei(a, a + treffer.end()):
                fortsetzung = (a, a + treffer.end())
        self.neu(o + s, o + ende, f"Angabe hinter Etikett »{etikett}«", "anschrift")
        if fortsetzung is not None:
            self.neu(fortsetzung[0], fortsetzung[1], f"Angabe hinter Etikett »{etikett}«", "anschrift")

    # Namen
    def _namen(self):
        text = self.text
        stuecke = [(m.start(), m.end(), m.group(0)) for m in re.finditer(r"\S+", text)]
        if not stuecke:
            return
        # Art je Stück: Titel/Anrede, akademischer Zusatz, Abkürzung/Initiale, Partikel, sonst Wort
        stueck_art = []
        for s, e, roh in stuecke:
            kern = roh.strip("()[]{},;:\"'„“”‚‘’«»")
            ohne_punkt = kern.rstrip(".")
            if kern and (self.w.art(kern)[5] or self.w.art(ohne_punkt)[5] or ohne_punkt.lower() in _TITEL_KURZ):
                stueck_art.append("titel")
            elif kern.endswith(".") and ohne_punkt.lower().replace("-", "").replace(".", "") in _AKADEMISCH:
                stueck_art.append("akademisch")
            elif kern.endswith(".") and (len(ohne_punkt) <= 4 or re.fullmatch(r"(?:[A-ZÄÖÜ]\.-?)+", kern)):
                stueck_art.append("abk")
            elif kern and self.w.art(kern)[7]:
                stueck_art.append("partikel")
            else:
                stueck_art.append("wort")
        woerter = []          # (start, ende, wort, stück-index)
        k = 0
        for m in _NAMENSWORT_RE.finditer(text):
            while k < len(stuecke) and stuecke[k][1] <= m.start():
                k += 1
            wort = m.group(0)
            if self._quelle(m.start()) != "text":
                if _OCR_KLEIN_L_RE.match(wort):
                    wort = "I" + wort[1:]               # die OCR liest ein großes I am Wortanfang als l ("llir")
                elif (wort[:1] in _FORMGLEICH_KLEIN and len(wort) >= 3 and 0 < k <= len(stueck_art)
                      and stueck_art[k - 1] == "titel"
                      and re.fullmatch(r"[ ]{1,2}", text[stuecke[k - 1][1]:m.start()])):
                    wort = wort[:1].upper() + wort[1:]  # "Herr Dipl.-Kfm. schüßler": S/s sehen gleich aus
            woerter.append((m.start(), m.end(), wort, k))
        n = len(woerter)
        arten = [self.w.art(w) for _, _, w, _ in woerter]

        def luecke(a, b) -> str:
            if a > b:
                a, b = b, a
            return text[woerter[a][1]:woerter[b][0]]

        def direkt(i, j, komma=False) -> bool:
            """Wörter i und j stehen direkt nebeneinander (Leerzeichen/Bindestrich, mit komma=True auch ", ";
            oder ein Zeilenumbruch mitten im Namen: "Petra\\nStrauß")."""
            if not (0 <= j < n):
                return False
            lu = luecke(i, j)
            if lu == "\n":
                return True
            erlaubt = set(" -,") if komma else set(" -")
            return 0 < len(lu) <= 3 and set(lu) <= erlaubt

        def namenswort(i) -> bool:
            return stueck_art[woerter[i][3]] == "wort" if woerter[i][3] < len(stueck_art) else True

        def gross(i) -> bool:
            w = woerter[i][2]
            return w[:1].isupper() and not _ocr_unsinn(w)

        def vorname_stark(i) -> bool:
            vn, nn, vnm, nnm, aw, tit, allow, part = arten[i]
            return (vn and not vnm and not aw and not tit and not allow and len(woerter[i][2]) >= 3 and gross(i)
                    and namenswort(i) and woerter[i][2].lower() not in _STOPPWOERTER)

        def nachname_stark(i) -> bool:
            vn, nn, vnm, nnm, aw, tit, allow, part = arten[i]
            return (nn and not nnm and not aw and not tit and not allow and len(woerter[i][2]) >= 3 and gross(i)
                    and namenswort(i) and woerter[i][2].lower() not in _STOPPWOERTER)

        def titel_davor(i) -> bool:
            k = woerter[i][3]
            z = self.zeile(woerter[i][0])
            for j in range(k - 1, max(-1, k - 6), -1):
                if z is not None and stuecke[j][0] < z.start:
                    return False
                if "\t" in text[stuecke[j][1]:stuecke[j + 1][0]]:
                    return False
                art = stueck_art[j]
                if art == "titel":
                    return True
                if art in ("partikel", "akademisch") or re.fullmatch(r"[A-ZÄÖÜ]\.", stuecke[j][2]):
                    continue
                return False
            return False

        etikett_zeilen: dict = {}

        def etikett_kontext(i) -> bool:
            """Steht das Wort im Wert hinter einem Personen-Etikett/einer Rolle ("Name: …", "Vorstand: …",
            "Name\\t\\tMax …") – nicht in Klammern, nicht hinter kleingeschriebenen Wörtern ("Facharzt für Innere
            Medizin") und nicht in einer Kopfzeile aus lauter Etiketten? Je Feld zählt das nächste Etikett links
            des Worts ("Name des Hundehalters: Felsberger    Vorname: Rainer": beide Werte haben ihr Etikett)."""
            s = woerter[i][0]
            z = self.zeile(s)
            if z is None:
                return False
            enden = etikett_zeilen.get(z.id)
            if enden is None:
                enden = []
                zeile = self.zeilen_text(z)
                for art in ("person", "rollen"):
                    index = self.w.index(art)
                    if index is None:
                        continue
                    try:
                        treffer = index.finde(zeile)
                    except Exception:
                        continue
                    for v in treffer:
                        vor = zeile[:v.start].rstrip(" ")
                        am_anfang = not vor or vor.endswith(("\t", ":", "·", "|", ","))
                        if (am_anfang and v.text[:1].isupper()) or zeile[v.ende:v.ende + 2].startswith(":") \
                                or v.text in ("gez.", "i. A.", "i.A.", "i. V.", "i.V.", "ppa."):
                            enden.append(z.start + v.ende)
                enden.sort()
                etikett_zeilen[z.id] = enden
            ende = max((x for x in enden if x <= s), default=-1)
            if not (0 <= ende <= s):
                return False
            zwischen = text[ende:s]
            if "(" in zwischen and ")" not in zwischen[zwischen.rfind("("):]:
                return False                            # in Klammern: "(Vorsitzender)"
            if _RECHTSFORM_RE.search(zwischen):
                return False                            # "Vermieter: Sixt GmbH & Co KG, Filiale Rosenheim": eine Firma
            if any(w[:1].islower() and not self.w.art(w)[7] for w in re.findall(r"[^\W\d_][\w\-]*", zwischen)):
                return False                            # "Facharzt für Innere Medizin"
            if "\t" in zwischen:
                if zwischen[:zwischen.find("\t")].strip(" :") or len(re.split(r"\t+", zwischen)) > 2:
                    return False                        # nur die Zelle direkt hinter dem Etikett
                zelle = re.split(r"\t+", text[s:z.ende])[0]
                if self._etikett_in(zelle, ("person", "datum_geburt", "kennung", "adresse", "kontakt",
                                            "vertragsdaten")):
                    return False                        # Kopfzeile einer Tabelle ("Kunde  Geb.-Datum")
            return True

        def geburtsname(i) -> bool:
            """Steht das Wort direkt hinter "geb.", "geb:" oder "geborene" (ein Geburtsname: "[PERSON A] geb.
            Quarnstedt", "GEB. QUARNSTEDT") – nicht vor einem Datum ("geb. Mai 1980", "geb. Od. Dez. 1973": das
            Wort ist Monat oder Tag), nicht mit Ziffer und nicht hinter "geborene" als Eigenschaftswort ("eine
            geborene Berlinerin")?"""
            s, e = woerter[i][0], woerter[i][1]
            z = self.zeile(s)
            if z is None:
                return False
            davor = text[max(z.start, s - 40):s]
            m = _GEBURTSNAME_DAVOR_RE.search(davor)
            if m is None or _DATUM_DAHINTER_RE.match(text, e) or any(c.isdigit() for c in text[s:e]):
                return False
            wort = text[s:e]
            if wort.casefold() in _GEBURTSNAME_FUELLWORT:
                return False                            # "geb. Ledig", "geb. Unbekannt"
            if self.w.grossstadt(wort) and not self.w.art(wort.title() if wort.isupper() else wort)[1]:
                return False                            # "geb. Hamburg": der Geburtsort (Großstadt, kein Nachname)
            if not kennungsformen.geburtsname_moeglich(text, s, e, self._wissen_frage) \
                    or kennungsformen.feld_etikett(text, s, e, self.w.ist_etikett):
                return False                            # "geb. In Köln", "geb. Polen", "geb. Lt. Ausweis", "PLZ:"
            if m.group("gab") and not kennungsformen.WERT_ENDE_RE.match(text, e):
                return False                            # "… die ihm Frau Weber gab. Müller kam später"
            if m.group("geborene") or m.group("gab") or m.group(0).startswith("Geb."):
                # "Geb." (Gebäude) und "geborene" (Eigenschaftswort) nur direkt hinter einem Namen oder Platzhalter
                # ("[PERSON A], geb. Schulz") – nicht "Klinikum Mitte, Geb. Nord", "Geborene Zwillinge sind …"
                vorher = re.search(r"([^\W\d_][\w'’\-]*|\])[ \t]*,?[ \t]*\(?[ \t]*$", davor[:m.start()])
                if vorher is None or (vorher.group(1) != "]" and not any(self.w.art(_titel(vorher.group(1)))[:2])):
                    return False
            return True

        spalten: dict = {}

        def spalte_person(i) -> bool:
            """Steht das Wort in einer Tabellenspalte mit Personen-Etikett im Kopf ("Vorname", "Kunde")?"""
            if i not in spalten:
                s, e = woerter[i][0], woerter[i][1]
                spalten[i] = self.spaltenkopf(s, e, ("person",)) is not None
            return spalten[i]

        def doppelname(i) -> bool:
            """Bindestrich-Name, von dem ein Teil ein eindeutiger Name ist ("Brinkmann-Müiller")."""
            teile = woerter[i][2].split("-")
            if len(teile) < 2 or not all(t[:1].isupper() for t in teile if t):
                return False
            arten_teile = [self.w.art(t) for t in teile if t]
            nicht_leer = [t for t in teile if t]
            # Komposita mit einem Sachwort oder einer Abkürzung sind keine Doppelnamen ("TAN-Verfahren", "SMS-TAN",
            # "WLAN-MAC-Adresse"; Befunde 66/83): jeder Teil muss ein Name sein können – ein Sachwort-Teil nur dann
            # nicht, wenn daneben ein eindeutiger Name in gewöhnlicher Schreibweise steht ("Schmidt-Wald")
            stark = any(((a[0] and not a[2]) or (a[1] and not a[3])) and not a[4] and not t.isupper() and len(t) >= 3
                        for t, a in zip(nicht_leer, arten_teile))
            if any((not stark and (a[4] or self.w.ist_etikett(t)))
                   or (t.isupper() and len(t) <= 4 and not (a[0] or a[1])) for t, a in zip(nicht_leer, arten_teile)):
                return False
            for t, (vn, nn, vnm, nnm, aw, tit, allow, part) in zip([t for t in teile if t], arten_teile):
                if ((vn and not vnm) or (nn and not nnm)) and not aw and not allow and len(t) >= 3:
                    return True
            return False

        def firma_danach(i) -> bool:
            rest = text[woerter[i][1]:woerter[i][1] + 30]
            return bool(re.match(r"[\s,&+\w.\-]{0,20}?(?<![\w])(?:GmbH|AG|KG|OHG|GbR|SE|mbH|e\.\s?V\.|UG|Partner|"
                                 r"Partnerschaft|& Co)(?![\w])", rest)) \
                or "&" in text[max(0, woerter[i][0] - 3):woerter[i][0]]

        gruss_zeilen = self._unterschriftszeilen()
        # Namen in Wohn- und Nachbarschaftsangaben ("unseres Nachbarn Felsberger", "Bei Felsberger im 1. OG", "EG links
        # (Hackenschmied)") – dieselbe Regel wie die Erkennung (personenkontext)
        wohn_starts = {a for a, _ in personenkontext.wohn_kontext_namen(text)} if re.search(
            r"(?i)nachbar|mieter|eigentümer|bewohner|hausmeister|verwalter|\b(?:og|eg|dg|ug)\b|geschoss|stock|etage",
            text) else set()

        sach_zeilen: dict = {}

        def sachname(i) -> bool:
            """Steht das Wort in einer Marke, einem Modell oder einer Tierrasse der Wissensbasis ("Weber Genesis",
            "Junghans Max Bill", "Jack Russell Terrier"), vor einem Modellcode ("Böckmann TPV", "Rossini 540") oder in
            der Abstammung eines Tiers – dieselben Regeln wie die Erkennung (namen.py, personenkontext)?"""
            s, e = woerter[i][0], woerter[i][1]
            z = self.zeile(s)
            if z is None:
                return False
            if z.id not in sach_zeilen:
                sach_zeilen[z.id] = [(z.start + a, z.start + b) for a, b in
                                     personenkontext.sachnamen_stellen(self.zeilen_text(z), self.w.modul)]
            if any(a <= s and e <= b for a, b in sach_zeilen[z.id]):
                return True
            if personenkontext.modellcode_danach(text, e, self.w.wortgestalt, (woerter[i][2],)):
                return True                             # nicht vor Datum, Jahr, Betrag, Telefonnummer
            return personenkontext.tierangabe(text, s)

        def artikel_davor(i) -> bool:
            """Steht direkt davor ein Artikel oder Begleiter ("Die Scheibe", "eine Weber-Grillstation")? Dann ist das
            großgeschriebene Wort ein Substantiv (Befund 66)."""
            return i > 0 and direkt(i, i - 1) and woerter[i - 1][2].lower() in _ARTIKEL

        def ortszusatz(i) -> bool:
            """Zusatz eines Ortsnamens hinter "/" ("Fürstenberg/Havel", "[PLZ ORT]/Havel", "Frankfurt/Oder")?"""
            s = woerter[i][0]
            if s < 1 or text[s - 1] != "/":
                return False
            if self.ist_platzhalter_bei(max(0, s - 3), s - 1) or \
                    self.neben_platzhalter(s - 1, s, _ANSCHRIFT_PLATZHALTER_RE) is not None:
                return True
            davor = re.search(r"([^\W\d_][\w\-]*)/$", text[max(0, s - 40):s])
            return bool(davor) and (self.w.frage("ist_ort", davor.group(1))
                                    or bool(re.search(r"\d{5}[ \t]+" + re.escape(davor.group(1)) + "/$",
                                                      text[max(0, s - 50):s])))

        def partei(i) -> bool:
            """Steht das Wort im Kurzrubrum direkt an "./." ("Kranzbühler ./. Felsberger")?"""
            s, e = woerter[i][0], woerter[i][1]
            return bool(re.search(r"\./\.[ \t]*$", text[max(0, s - 6):s])
                        or re.match(r"[ \t]*(?:,[ \t]*[^\W\d_][\w\-]*[ \t]*)?\./\.", text[e:e + 40]))

        def organisation(i) -> bool:
            """Steht das Wort in einer Tabellenspalte mit Organisations-Kopf ("Versicherer" über "Adam Riese",
            "Roland"; Befund 92) – dieselbe Regel wie die Erkennung (personenkontext.organisations_spalte)?"""
            return personenkontext.organisations_spalte(text, woerter[i][0])

        def name_amt(i) -> bool:
            """Steht hinter dem Wort ", <Amtsbezeichnung>" ("Eibl, JAng", "Kollmannsberger, JOSin")?"""
            m = re.match(r"[ \t]*,[ \t]*([A-Za-zÄÖÜäöü'’]{2,8})(?![\wäöüß])", text[woerter[i][1]:woerter[i][1] + 14])
            return bool(m) and sum(c.isupper() for c in m.group(1)) >= 2 and self.w.art(m.group(1))[5]

        def firmenname(i) -> bool:
            """Steht das Wort hinter einer Geschäftsbezeichnung – direkt oder über Namenszusätze ("Werkstatt Weiß",
            "Bäckerei Hofmeister", "Werkstatt von Arnim-Lübbenau") – und kann es ein Name sein: ein Name der
            Wissensbasis (auf OCR-Seiten auch klein gelesen: "Werkstatt weiß"), ein Doppelname oder ein unbekanntes
            großgeschriebenes Wort, das kein gewöhnliches Wort, Beruf, keine Organisation und keine Einheit ist
            ("Werkstatt Kamps", "Werkstatt Weiß-Lübbenau"; "Werkstatt Nord", "Pflegedienst Sonnenschein" nicht)?"""
            j = i - 1
            while j > 0 and direkt(j + 1, j) and woerter[j][2][:1].islower() and self.w.art(woerter[j][2])[7]:
                j -= 1                                  # Namenszusätze "von", "van der", "de"
            if not (j >= 0 and direkt(j + 1, j) and woerter[j][2].lower() in _GESCHAEFTE):
                return False
            w = woerter[i][2]
            if w[:1].islower():
                if self._quelle(woerter[i][0]) == "text":
                    return False
                w = w[:1].upper() + w[1:]
                vn, nn, vnm, nnm, aw, tit, allow, part = self.w.art(w)
                return (vn or nn) and not (aw or tit or allow or part) and len(w) >= 3 \
                    and w.lower() not in _STOPPWOERTER        # klein gelesen: nur ein Name der Wissensbasis
            vn, nn, vnm, nnm, aw, tit, allow, part = self.w.art(w)
            if aw or tit or allow or part or len(w) < 3 or w.lower() in _STOPPWOERTER or w.isupper():
                return False
            if vn or nn or doppelname(i):
                return True
            return not (self._wort_harmlos(w) or _ORG_WORT_RE.search(w) or _RECHTSFORM_RE.fullmatch(w)
                        or self._strassenwort(i, woerter) or re.search(r"(?i)" + _STRASSEN_ENDUNG + r"$", w)
                        or self.w.frage("ist_ort", w) or _JURISTISCH_DANACH_RE.match(text, woerter[i][1]))

        etikett_spannen: dict = {}

        def im_etikett(i) -> bool:
            """Steht das Wort in einem mehrteiligen Feld-Etikett der Wissensbasis ("Given names", "Lieu de naissance",
            "Place of birth" auf einer Ausweiskopie, Befund 90)? Dann ist es ein Etikettwort, kein Eigenname."""
            s, e = woerter[i][0], woerter[i][1]
            z = self.zeile(s)
            if z is None:
                return False
            spannen = etikett_spannen.get(z.id)
            if spannen is None:
                spannen = []
                zeile = self.zeilen_text(z)
                for art in ("person", "datum_geburt", "adresse", "kontakt", "kennung", "vertragsdaten"):
                    index = self.w.index(art)
                    try:
                        treffer = index.finde(zeile) if index is not None else []
                    except Exception:
                        treffer = []
                    spannen += [(z.start + v.start, z.start + v.ende) for v in treffer if " " in v.text.strip()]
                etikett_spannen[z.id] = spannen
            return any(a <= s and e <= b for a, b in spannen)

        for i, (s, e, w, k) in enumerate(woerter):
            if firmenname(i) and namenswort(i) and not (self.ist_gesperrt(s, e) or self.ist_platzhalter_bei(s, e)):
                self.neu(s, e, "Name in einer Firmenbezeichnung", "name")
                continue
            zusammen = _ZUSAMMEN_RE.fullmatch(w) if self._quelle(s) != "text" else None
            if zusammen and not self.ist_gesperrt(s, e) and all(
                    (a[0] or a[1]) and not (a[4] or a[5] or a[6]) for a in map(self.w.art, zusammen.groups())):
                self.neu(s, e, "Namen ohne Leerzeichen gelesen", "name")    # OCR: "LukasKrause"
                continue
            if not gross(i) or not namenswort(i) or w.lower() in _STOPPWOERTER:
                continue
            if self.ist_gesperrt(s, e) or self.ist_platzhalter_bei(s, e) or _platzhalter_bruchstueck(w):
                continue
            if re.match(r"-\n[a-zäöüß]", text[e:e + 3]):
                continue                                # Silbentrennung am Zeilenende ("Versiche-" / "rer")
            vn, nn, vnm, nnm, aw, tit, allow, part = arten[i]
            if tit or part:
                continue
            if _ORG_ENDWORT.search(w) or self._strassenwort(i, woerter):
                continue
            platzhalter = self.neben_platzhalter(s, e, _PERSONEN_PLATZHALTER_RE) is not None
            titel = titel_davor(i)
            etikett = etikett_kontext(i)
            links_vorname = (direkt(i, i - 1) and vorname_stark(i - 1)
                             and not (i >= 2 and direkt(i - 1, i - 2) and woerter[i - 2][2].lower() in _MARKEN))
            rechts_nachname = direkt(i, i + 1) and nachname_stark(i + 1) and vn
            komma_paar = ((direkt(i, i + 1, komma=True) and "," in luecke(i, i + 1) and vorname_stark(i + 1) and nn)
                          or (direkt(i, i - 1, komma=True) and "," in luecke(i, i - 1)
                              and nachname_stark(i - 1) and vn))
            z_wort = self.zeile(s)
            gruss = (z_wort is not None and z_wort.id in gruss_zeilen and not w.isupper()
                     and not self._org_zeile(z_wort) and not self._wort_harmlos(w))
            geboren = geburtsname(i)
            rolle = s in wohn_starts or partei(i) or name_amt(i)
            kontext = (titel or platzhalter or etikett or links_vorname or rechts_nachname or komma_paar or gruss
                       or geboren or rolle)
            if personenkontext.tierangabe(text, s) or (personenkontext.medizinisch(w, text, s, self.w.modul)
                                                       and not titel):
                continue                                # "Abstammung: v. Gribaldi", "Baker-Zyste", "Morbus Scheuermann"
            if sachname(i) and not (titel or etikett):
                continue                                # "Gasgrill Weber Genesis", "Böckmann TPV", "Jack Russell"
            if not (titel or platzhalter or etikett or rolle) and (vn or nn) and organisation(i):
                continue                                # "Adam Riese", "Versicherer" ⏎ "Roland": ein Versicherer
            if vorname_stark(i) or nachname_stark(i) or doppelname(i):
                stark_kontext = titel or platzhalter or links_vorname
                if not (stark_kontext or etikett or rolle) and (artikel_davor(i) or ortszusatz(i)):
                    continue                            # "Die Scheibe ist gesprungen", "Fürstenberg/Havel"
                marke_davor = i > 0 and direkt(i, i - 1) and woerter[i - 1][2].lower() in _MARKEN
                marke_davor = marke_davor or (k > 0 and stuecke[k - 1][2] in ("St.", "Sankt", "Hl.")
                                              and not titel_davor(i))  # "Krankenhaus St. Ansgar"
                if (allow or firma_danach(i) or w.lower() in _MARKEN or marke_davor) and not stark_kontext:
                    continue
                if w.isupper() and len(w) <= 4 and not (kontext or spalte_person(i)):
                    continue                            # kurze Versalwörter ("BEER") nur mit Kontext
                if vorname_stark(i):
                    grund = "Vorname aus der Wissensbasis"
                elif nachname_stark(i):
                    grund = "Nachname aus der Wissensbasis"
                else:
                    grund = "Doppelname mit Namen aus der Wissensbasis"
                self.neu(s, e, grund, "name")
                continue
            if not kontext and (vn or nn or not aw) and len(w) >= 4 and not allow and spalte_person(i):
                kontext = etikett = True                # Tabellenspalte "Vorname", "Name", "Kunde"
            if len(w) < 2 or (w.isupper() and len(w) <= 3 and not kontext) or w.lower() in _ANREDE_ZUSATZ:
                continue
            if im_etikett(i):
                continue                                # "Vornamen / Given names / Prénoms": Etikett, kein Name
            if (vn or nn) and kontext and not allow and not self.w.ist_etikett(w):
                self.neu(s, e, "mehrdeutiger Name im Personenkontext", "name")
                continue
            if links_vorname and not allow and (w.lower() in _KALENDERWOERTER or not aw) \
                    and not _NOMEN_ENDUNG.search(w) and not self.w.ist_etikett(w):
                self.neu(s, e, "Name direkt hinter einem Vornamen", "name")
                continue
            if aw or allow or len(w) < 4 or _NOMEN_ENDUNG.search(w) or self.w.ist_etikett(w) or firma_danach(i):
                continue
            if (w.isupper() and len(w) < 5) or text[e:e + 2].lstrip(")").startswith(":") \
                    or self._kompositum(w):
                continue                                # OCR-Bruchstück, Etikett ("(Selbstständige):"), Kompositum
            if re.search(r"(?i)" + _STRASSEN_ENDUNG + r"$", w):
                continue                                # "Hauptstr" – Anschrift, nicht Name
            ocr_wort = self._quelle(s) != "text"
            if ocr_wort and not (5 <= len(w) <= 14):
                continue                                # OCR-Bruchstücke ("Fran", "Versicherurigsnehmer")
            if titel or (platzhalter and len(w) <= 14) or (etikett and not ocr_wort) or (rolle and not ocr_wort):
                self.neu(s, e, "unbekannter Eigenname im Personenkontext", "name")
            elif geboren:
                self.neu(s, e, "möglicher Geburtsname (hinter »geb.«)", "name")
            elif gruss and len(w) <= 14:
                self.neu(s, e, "möglicher Name im Unterschriftsblock", "name")

    def _unterschriftszeilen(self) -> set:
        """IDs der Zeilen eines Unterschriftsblocks: bis zu GRUSS_ZEILEN Zeilen unter einer Grußformel (Leserichtung,
        höchstens UNTERSCHRIFT_ZEILEN Zeilenhöhen tiefer, waagerecht im Bereich der Formel, kein Fließtext) – dort
        steht der Name der Unterzeichnenden."""
        if "gruss" in self._org:
            return self._org["gruss"]
        aus: set = set()
        zeilen = []
        for z in self.m.zeilen:
            inhalt = self.zeilen_text(z)
            if z.rect is not None and inhalt.strip():
                zeilen.append((self.lese_rect(z.rect, self._herkunft(z)), z, inhalt, self._herkunft(z)))
        for r, z, inhalt, herkunft in zeilen:
            if not ist_grussformel(inhalt) or len(inhalt.split()) > 6:
                continue
            h = max(r.height, 8.0)
            darunter = sorted((t for t in zeilen if t[3] == herkunft and t[1].id != z.id and t[0].y0 >= r.y1 - 0.3 * h
                               and t[0].y0 <= r.y1 + UNTERSCHRIFT_ZEILEN * h and t[0].x0 >= r.x0 - 15
                               and t[0].x0 <= r.x0 + UNTERSCHRIFT_BREITE), key=lambda t: t[0].y0)
            for t in darunter[:GRUSS_ZEILEN]:
                if _ist_fliesstext(t[2]):
                    break
                aus.add(t[1].id)
        self._org["gruss"] = aus
        return aus

    def _strassenwort(self, i, woerter) -> bool:
        """Wort ist Teil eines Straßennamens ("Theodor-Heuss-Ring", "Goethe Straße")."""
        s, e, w = woerter[i][:3]
        if "-" in w and re.search(r"(?i)" + _STRASSEN_ENDUNG + r"$", w):
            return True
        if i + 1 < len(woerter):
            ns, ne, nw = woerter[i + 1][:3]
            if ns - e <= 2 and re.fullmatch(r"(?i)" + _STRASSEN_ENDUNG + r"\.?", nw):
                return True
        return False

    # Reste neben Platzhaltern
    def _reste_neben_platzhaltern(self):
        """Ein Wort direkt neben einem Personen- oder Anschrift-Platzhalter, das kein gewöhnliches Wort ist
        ("Untere [ADRESSE]", "[PLZ ORT] Trier"): ein vergessener Teil des geschwärzten Werts."""
        text = self.text
        if not self.platzhalter and not self.schwaerzungen:
            return
        # Feldcodes einer Zulassungsbescheinigung Teil I ("C.1.3  [ADRESSE]") sind Etiketten, kein Rest (Befund 32)
        zb1 = personenkontext.zb1_seite(text)
        for ps, pe in self.platzhalter:                # "[PLZ ORT]OPf." – ohne Leerzeichen angehängt
            if not (_ANSCHRIFT_PLATZHALTER_RE.match(text[ps:pe]) or _PERSONEN_PLATZHALTER_RE.match(text[ps:pe])):
                continue
            nach = re.match(r"[\w.'\-]*\w", text[pe:pe + 30])
            if nach and nach.group(0)[:1].isalnum():
                self.neu(pe, pe + nach.end(), "Rest neben Platzhalter", "rest")
            vor = re.search(r"\w[\w.'\-]*$", text[max(0, ps - 30):ps])
            if vor and ps > 0 and text[ps - 1].isalnum():
                self.neu(ps - len(vor.group(0)), ps, "Rest neben Platzhalter", "rest")
        for m in re.finditer(r"\S+", text):
            s, e = m.start(), m.end()
            roh = m.group(0)
            kern = roh.strip("()[]{},;:\"'„“”‚‘’«»|")
            if not kern or self.ist_gesperrt(s, e) or _platzhalter_bruchstueck(roh) \
                    or (zb1 and personenkontext.ZB1_FELDCODE_RE.fullmatch(kern)):
                continue
            s += roh.find(kern)
            e = s + len(kern)
            if sum(c.isalnum() for c in kern) >= 3 and _ziffern(kern) \
                    and self._quelle(s) == "text" and self.an_schwaerzung(s, e):
                if not self._betrag_oder_datum(kern):    # "1.714,85" in der Nachbarspalte ist kein abgeschnittener Wert
                    self.neu(s, e, "Rest direkt an einer Schwärzung (Wert abgeschnitten?)", "rest")
                continue
            nachbar = self.neben_platzhalter(s, e, _ANSCHRIFT_PLATZHALTER_RE)
            if nachbar is None:
                continue
            ps, pe = nachbar
            rechts = s >= pe or (s > ps and self.box(s, e) is not None)
            vor_stueck = text[max(0, m.start() - 4):m.start()]
            nach_stueck = text[m.end():m.end() + 4]
            if re.search(r"[·|•/]", vor_stueck + nach_stueck):
                continue                                # "Innere Medizin · [ADRESSE]" – anderer Eintrag
            ocr_wort = self._quelle(s) != "text"
            if kern.isdigit():
                if len(kern) <= 4 and rechts and not ocr_wort:
                    self.neu(s, e, "Rest neben Platzhalter", "rest")   # Hausnummer
                continue
            wort = kern.rstrip(".")
            if len(wort) < 2 or _ocr_unsinn(wort) or wort.lower() in _STOPPWOERTER:
                continue
            if not wort[:1].isupper():
                # Ortszusatz rechts vom Ort: "[PLZ ORT] i.d.OPf.", "a.M."
                if "." in kern and len(kern) <= 10 and text[ps:pe].startswith("[PLZ"):
                    self.neu(s, e, "Rest neben Platzhalter", "rest")
                continue
            if len(wort) < 3 or kern.endswith("."):
                continue
            vn, nn, vnm, nnm, aw, tit, allow, part = self.w.art(wort)
            if aw or tit or allow or part or self.w.ist_etikett(wort) or _NOMEN_ENDUNG.search(wort):
                continue
            if re.fullmatch(r"(?i)" + _STRASSEN_ENDUNG + r"\.?", wort) or self.org_kontext(s):
                continue
            if not (vn or nn) and self._wort_harmlos(wort):
                continue                                # "Fachärztin für Allgemeinmedizin · [ADRESSE]"
            if ocr_wort and not (vn or nn) and (len(wort) < 4 or wort.isupper() or self._kompositum(wort)):
                continue                                # OCR-Bruchstück ("Dau", "MIRD", "Unfallherg")
            self.neu(s, e, "Rest neben Platzhalter", "rest")

    def _betrag_oder_datum(self, kern: str) -> bool:
        """Ist das Stück vollständig ein Betrag, ein Prozentsatz oder ein (mögliches) Datum – Tag bis 31 und Monat
        bis 12 oder Monat/Jahr? "12.34.5678" an einer Schwärzung ist kein Datum, sondern ein abgeschnittener Wert."""
        if _BETRAG_RE.fullmatch(kern) or _PROZENT_RE.fullmatch(kern) or _MONAT_JAHR_RE.fullmatch(kern):
            return True
        m = _DATUMSFORM_TMJ_RE.fullmatch(kern)
        if m and int(m.group(1)) <= 31 and 1 <= int(m.group(2)) <= 12:
            return True
        for regex, art in _DATUM_RES:
            m = regex.fullmatch(kern)
            if m and self._datum(m, art) is not None:
                return True
        return False

    def lesung_harmlos(self, s: int, e: int, lese_hoehe: float, uebliche_hoehe: float, fliesstext=False,
                       lese_breite=None, hohe_kaesten=True) -> bool:
        """Macht die OCR-Lesung eines Worts (Textstelle s:e) seine Tinte unverdächtig? Für Unterschriftsblöcke und
        Personenangaben auf Scans: Nein, wenn der Wortkasten nicht zum gelesenen Text passt – viel breiter als die
        Zeichen (lese_breite: ein Zug, als "Med" oder "az" gelesen; das gilt auch für bekannte und kleingeschriebene
        Lesungen) oder viel höher als die übliche Schrift (ein Unterschriftszug, als "Wort" gelesen, oder ein Wort,
        dessen Kasten einen Zug darüber mit einschließt: "Mandant" unter dem durchkreuzten Namen; bekannte Wörter
        nur, wenn hohe_kaesten – eine Seite, auf der hohe Wortkästen üblich sind, Fax mit halber senkrechter
        Auflösung) –, wenn die Lesung Bruchstück oder Buchstabensalat ist oder wenn das Wort ein Name sein kann
        (großgeschriebener Name der Wissensbasis, auch mehrdeutig; unbekanntes großgeschriebenes Wort) – an dieser
        Stelle steht eine Person.
        Ja für Platzhalter, NIE-Liste, abgewählte Stellen, Kürzel und Zeichen von Firmen- und Kanzleizeilen ("&",
        "Co.", "LL.M."), Wörter mit Ziffern (die prüfen die Textregeln), kleingeschriebene Wörter, Fließtext und
        Grußformel (fliesstext=True: die Textregeln prüfen ihn mit Namenslisten und Kontext), Firmenzeilen,
        "i. A."/"i. V.", Wörter einer Berufsangabe der Wissensbasis ("Facharzt für Innere Medizin"), häufige
        Wörter, Titel, Partikel, Etiketten, Berufe, Organisationseinheiten ("Hauptagentur Nord"), Hauptwörter,
        auch gebeugt ("Rechtsanwälte"); zusammengesetzte Wörter, wenn jeder Teil harmlos ist ("Kundenservice-Team")
        oder der letzte Teil ein gewöhnliches Hauptwort und keiner ein Name ist ("Kfz-Schaden")."""
        if self.ist_gesperrt(s, e):
            return True
        roh = self.text[s:e].strip()
        kern = roh.strip("()[]{},;:.!?\"'„“”‚‘’«»|/\\-–")
        if not kern:
            return False
        if lese_breite is not None and lese_breite > LESUNG_BREITE_MAX * len(roh) * max(lese_hoehe, uebliche_hoehe):
            return False                                # der Kasten passt nicht zum Text: ein Zug, kein Wort
        hoch = lese_hoehe > WORT_HOEHE_MAX * uebliche_hoehe
        if not hoch and _kuerzel(kern):
            return True                                 # "&", "Co.", "LL.M." (Firmen-, Kanzlei-, Praxiszeilen)
        kern = kern.strip("&+")
        teile = [t for t in re.split(r"[-/&+.]", kern) if t]
        if hoch:
            # viel höher als die Schrift: ein als "Wort" gelesener Unterschriftszug ("Dee") oder ein Wort samt Zug – es
            # sei denn, hohe Kästen sind auf der Seite üblich und die Lesung ist ein bekanntes Wort (Fax mit halber
            # senkrechter Auflösung: hohe Wortkästen um gewöhnliche Wörter)
            return (hohe_kaesten and sum(c.isalnum() for c in kern) >= 2 and bool(teile)
                    and all(t.isalpha() and self._bekanntes_wort(t) for t in teile))
        z = self.zeile(s)
        if sum(c.isalnum() for c in kern) < 2:
            return z is not None and self._auftragskuerzel(z, s, e)    # "i. A.", "i. V."
        if any(c.isdigit() for c in kern):
            return True
        if z is not None and self._org_zeile(z):
            return True                                 # Firmenzeile ("Donau Leben AG", "… VVaG")
        if _ocr_unsinn(kern) or not kern[:1].isalpha():
            return False
        buchstaben = [c.lower() for c in kern if c.isalpha()]
        if len(buchstaben) >= 3 and not any(c in "aeiouyäöüéèáàóíú" for c in buchstaben):
            return False                                # Buchstabensalat ("Dzrk")
        if kern[:1].islower() or fliesstext:
            return True
        if z is not None and self._in_berufsangabe(z, s, e):
            return True                                 # "Facharzt für Innere Medizin", "Fachärztin für HNO-…"
        teile = [t for t in teile if sum(c.isalpha() for c in t) >= 2] or teile
        if all(self._wort_harmlos(t) for t in teile):
            return True
        # zusammengesetzt mit Bindestrich: der letzte Teil trägt die Bedeutung ("Kfz-Schaden",
        # "Hals-Nasen-Ohren-Heilkunde") – harmlos, wenn er ein gewöhnliches Hauptwort und kein Teil ein Name ist
        return (len(teile) >= 2 and self._wort_harmlos(teile[-1])
                and not any(any(self.w.art(t)[:4]) for t in teile))

    def _auftragskuerzel(self, z, s: int, e: int) -> bool:
        """Gehört das Einzelzeichen an s:e zu "i. A.", "i. V.", "ppa.", "gez." seiner Zeile?"""
        zeile = self.zeilen_text(z)
        pos = s - z.start
        return any(t.start() <= pos < t.end() for t in _AUFTRAG_RE.finditer(zeile))

    def _in_berufsangabe(self, z, s: int, e: int) -> bool:
        """Liegt die Stelle in einer mehrteiligen Berufsangabe der Wissensbasis auf ihrer Zeile ("Facharzt für Innere
        Medizin", "Fachanwältin für Versicherungsrecht")? Einteilige Berufe prüft _wort_harmlos (viele sind auch
        Familiennamen)."""
        schluessel = ("beruf", z.id)
        treffer = self._org.get(schluessel)
        if treffer is None:
            index = self.w.index("berufe")
            try:
                treffer = [(v.start, v.ende) for v in index.finde(self.zeilen_text(z))
                           if len(re.findall(r"[^\W\d_]+", v.text)) >= 2] if index is not None else []
            except Exception:
                treffer = []
            self._org[schluessel] = treffer
        a, b = s - z.start, e - z.start
        return any(ts <= a and b <= te for ts, te in treffer)

    def _bekanntes_wort(self, wort: str) -> bool:
        """Wort der festen Listen – Funktions-, Gruß- und Kalenderwort, Anrede, Titel, akademischer Grad, häufiges
        Wort, Partikel, Allowlist, Etikett – und kein Name der Wissensbasis."""
        klein = wort.lower().rstrip(".")
        if (klein in _STOPPWOERTER or klein in _KALENDERWOERTER or klein in _ANREDEN or klein in _ANREDE_ZUSATZ
                or klein in _AKADEMISCH or klein in _TITEL_KURZ or klein in _GRUSS_WOERTER):
            return True
        vn, nn, vnm, nnm, aw, tit, allow, part = self.w.art(wort)
        if (vn or nn) and not tit:
            return False                                # Name der Wissensbasis – hier steht eine Person
        return bool(tit or part or aw or allow or self.w.ist_etikett(wort))

    def _wort_harmlos(self, wort: str) -> bool:
        """Einzelwort ohne Ziffern: kein möglicher Name (siehe lesung_harmlos)? Bekanntes Wort, sonst – wenn es kein
        Name der Wissensbasis ist – kleingeschrieben, Hauptwort-Endung, Beruf oder Wort einer Berufsangabe ("Leiter",
        "Medizin"), Organisationseinheit ("Hauptagentur", "Süd"), gebeugte Form eines solchen Worts
        ("Rechtsanwälte") oder zusammengesetztes Hauptwort."""
        if self._bekanntes_wort(wort):
            return True
        if any(self.w.art(wort)[:2]):
            return False
        if wort[:1].islower() or _NOMEN_ENDUNG.search(wort) or self._kompositum(wort):
            return True
        klein = wort.lower()
        berufe = self.w.berufswoerter()
        if klein in berufe or klein in _EINHEITEN:
            return True
        if any(len(g) >= 4 and (g.lower() in berufe or g.lower() in _EINHEITEN) for g in _grundformen(wort)):
            return True                                 # gebeugt: "Rechtsanwälte", "Agenturen"
        # Kompositum mit Beruf oder Organisationseinheit als letztem Glied ("Allgemeinmedizin", "Generalagentur") –
        # nicht, wenn dieses Glied selbst ein Name sein kann ("Hof|meister")
        for i in range(3, len(klein) - 4):
            kopf = klein[i:]
            if (kopf in berufe or kopf in _EINHEITEN) and not any(self.w.art(kopf.capitalize())[:4]):
                return True
        return False

    def _kompositum(self, w: str) -> bool:
        """Zusammengesetztes Hauptwort ("Bestandsliste", "Maklerbüro", "Unfallhergang")?"""
        for i in range(3, len(w) - 3):
            rest = w[i:]
            if rest[0].isupper():
                continue
            kandidat = rest[0].upper() + rest[1:]
            if self.w.art(kandidat)[4] or self.w.ist_etikett(kandidat):
                return True
        for i in range(4, len(w) - 2):
            if (self.w.art(w[:i])[4] and i >= 5) or self.w.ist_etikett(w[:i]):
                return True
        return False


# ----------------------------------------------------------------------
# Kandidaten -> Verdacht
# ----------------------------------------------------------------------
_RANG = {"form": 0, "feld": 1, "kontakt": 2, "datum": 3, "name": 4, "anschrift": 5, "kennung": 6, "etikett": 7,
         "rest": 8}


def _zusammenfassen(pruefung: _Seitenpruefung) -> list:
    """Gesperrte Kandidaten verwerfen, überlappende/direkt benachbarte derselben Zeile zusammenfassen; Grund ist
    der des längsten Kandidaten (bei Gleichstand der spezifischere)."""
    text = pruefung.text
    kandidaten = []
    for k in pruefung.kandidaten:
        s, e = k.start, k.ende
        while s < e and (text[s].isspace() or text[s] in ",;:"):
            s += 1
        while e > s and (text[e - 1].isspace() or text[e - 1] in ",;:"):
            e -= 1
        if e <= s or pruefung.ist_gesperrt(s, e):
            continue
        kandidaten.append(_Kandidat(s, e, k.grund, k.art))
    kandidaten.sort(key=lambda k: (k.start, -k.ende))
    gruppen: list = []
    for k in kandidaten:
        if gruppen:
            g = gruppen[-1]
            luecke = text[g["ende"]:k.start] if k.start > g["ende"] else ""
            if k.start < g["ende"] or luecke in ("", " ", "-"):
                g["ende"] = max(g["ende"], k.ende)
                g["kandidaten"].append(k)
                continue
        gruppen.append({"start": k.start, "ende": k.ende, "kandidaten": [k]})
    aus = []
    for g in gruppen:
        bester = min(g["kandidaten"], key=lambda k: (-(k.ende - k.start), _RANG.get(k.art, 9)))
        aus.append((g["start"], g["ende"], bester.grund))
    return aus


def _rechtecke(m, start: int, ende: int) -> list:
    aus = []
    try:
        for teil in m.rechtecke(start, ende):
            r = fitz.Rect(teil[0])
            if r.is_empty:
                r = fitz.Rect(teil[1])
            if not r.is_empty:
                aus.append(r)
    except Exception:
        pass
    return aus


def _merkmalswert(wert: str) -> bool:
    """Ist der Feldwert ein Merkmal aus der geschlossenen Liste _MERKMALE (Familienstand, Geschlecht – sie bleiben laut
    Handbuch stehen)? Sonst ist ein nicht geschwärzter Feldwert Verdacht – auch klein getippt: ein Name
    ("frank", "koch", "max müller"), ein Ort ("köln", "bad homburg"), eine Straße ("lindenweg"), eine
    Staatsangehörigkeit ("polnisch"), eine Konfession ("römisch-katholisch") oder eine Gesundheitsangabe
    ("hiv-positiv") weisen auf eine Person hin, und die Erkennung bietet klein getippte Werte oft gar nicht an."""
    return re.sub(r"\s+", " ", wert.strip().strip(".,;:").lower()) in _MERKMALE


def _felder_pruefen(pruefung: _Seitenpruefung, felder) -> None:
    """Formularfelder des Originals: steht in der Ausgabe im Feldrechteck noch lesbarer Text (kein Platzhalter),
    wurde der Feldwert nicht geschwärzt."""
    m = pruefung.m
    text = m.text
    for feld in felder or ():
        try:
            rect = fitz.Rect(feld["rect"] if isinstance(feld, dict) else feld.rect)
            if isinstance(feld, dict):
                name = feld.get("etikett") or feld.get("name") or ""
            else:
                name = getattr(feld, "etikett", "") or getattr(feld, "name", "") or ""
        except Exception:
            continue
        innen = fitz.Rect(rect.x0 - 1, rect.y0 - 1, rect.x1 + 1, rect.y1 + 1)
        positionen = []
        for i, g in enumerate(m.abbildung):
            if g < 0 or text[i].isspace():
                continue
            r = m.zeichen[g].rect
            if innen.contains(fitz.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)):
                positionen.append(i)
        if not positionen:
            continue
        s, e = min(positionen), max(positionen) + 1
        wert = text[s:e]
        if sum(c.isalnum() for c in wert) < 2 or pruefung.ist_platzhalter_bei(s, e) or pruefung.ist_gesperrt(s, e):
            continue
        if pruefung._etikett_in(name, ("vertragsdaten",)) or wert.strip().lower() in ("ja", "nein", "x", "off", "on"):
            continue
        if all(t.lower().rstrip(".") in _ANREDEN for t in wert.split()):
            continue                                  # "Herr", "Frau" – Anrede
        if _merkmalswert(wert):
            continue                                  # "ledig", "verheiratet", "männlich": Merkmal ohne Personenbezug
        anzeige = re.sub(r"\s+", " ", str(name)).strip(" :")[:40] or "ohne Namen"
        pruefung.neu(s, e, f"Formularfeld »{anzeige}« nicht geschwärzt", "feld")


def _seite_pruefen(m, wissen: _Wissen, platzhalter=(), nie=(), abgewaehlt=(), profil="hoch", felder=(),
                   schwaerzungen=(), scan_seite=None, ausrichtung=None) -> list:
    """Alle Regeln einer Seite. scan_seite: die PDF-Seite einer Scan-Seite (OCR der ganzen Seite) – dann zusätzlich
    die Tinte in Unterschriftsblöcken und neben Personenangaben (_unterschrift_pruefen; deren Verdacht steht vorn);
    ausrichtung: (Winkel, Schräglage) der OCR-Wörter, falls bekannt (10-Tupel)."""
    pruefung = _Seitenpruefung(m, wissen, platzhalter, nie, abgewaehlt, profil, schwaerzungen, ausrichtung=ausrichtung)
    pruefung.pruefen()
    _felder_pruefen(pruefung, felder)
    aus = [Verdacht(m.nr, s, e, m.text[s:e], grund, _rechtecke(m, s, e)) for s, e, grund in _zusammenfassen(pruefung)]
    if scan_seite is not None:
        aus = _unterschrift_pruefen(scan_seite, m, schwaerzungen, pruefung, aus, ausrichtung) + aus
    return aus


def pruefe_text(text: str, platzhalter=None, nie=None, wissen=None, profil: str = "hoch",
                abgewaehlt=None) -> list:
    """Restrisiko-Prüfung eines reinen Texts (eine Seite, Zeilen aus "\\n"; dieselben Zeichenregeln wie für
    PDF-Seiten: NBSP, weiche Trennstriche, Ligaturen). Für Tests und Werkzeuge."""
    m = sm.dokument_aus_text(text or "").seiten[0]
    w = _Wissen(wissen if wissen is not None else _wissen_laden())
    return _seite_pruefen(m, w, platzhalter or (), nie or (), abgewaehlt or (), profil)


# ----------------------------------------------------------------------
# Seitenmodell der Ausgabe (Textebene + OCR)
# ----------------------------------------------------------------------
def _ocr_woerter_holen(ocr, pfad, nr: int, clip=None, winkel=None) -> list:
    """OCR-Wörter so angefordert wie von der Selbstkontrolle (gleicher Schlüssel -> Treffer im Zwischenspeicher):
    vollständig über ergebnis() – 10-Tupel mit Ausrichtung und Schräglage, damit Seitenmodell und Tintenprüfung
    schräge Scans gerade rücken –, sonst über woerter() (5-Tupel)."""
    if ocr is None:
        return []
    woerter = None
    ergebnis = getattr(ocr, "ergebnis", None)
    if callable(ergebnis):
        try:
            woerter = (ergebnis(pfad, nr, OCR_DPI, clip=clip, winkel=winkel) or {}).get("woerter")
        except TypeError:
            woerter = None
    if woerter is None:
        try:
            if clip is not None:
                woerter, _ = ocr.woerter(pfad, nr, OCR_DPI, clip=clip)
            elif winkel is not None:
                woerter, _ = ocr.woerter(pfad, nr, OCR_DPI, winkel=winkel)
            else:
                woerter, _ = ocr.woerter(pfad, nr, OCR_DPI)
        except TypeError:
            woerter, _ = ocr.woerter(pfad, nr)
    return [tuple(w) for w in (woerter or []) if len(w) >= 5 and str(w[4]).strip()]


def _platzhalter_boxen(seite, nr: int, platzhalter) -> list:
    """Rechtecke der Platzhalter auf der Textebene einer Seite (die OCR liest sie mit – sie zählen nicht)."""
    m = sm.seite_aufbauen(seite, nr)
    if not m.text.strip():
        return []
    spannen = [(x.start(), x.end()) for x in _PLATZHALTER_RE.finditer(m.text)]
    for p in platzhalter or ():
        p = str(p or "").strip()
        i = m.text.find(p) if p else -1
        while i >= 0:
            spannen.append((i, i + len(p)))
            i = m.text.find(p, i + len(p))
    boxen = []
    for s, e in spannen:
        for teil in m.rechtecke(s, e):
            boxen.append(fitz.Rect(teil[1]) + (-1.5, -1.5, 1.5, 1.5))
    return boxen


def _schwaerzungsrechtecke(seite) -> list:
    """Graue Schwärzungsrechtecke der Ausgabe (Füllfarbe der Schwärzung) – die Lage geschwärzter Werte."""
    aus = []
    try:
        for d in seite.get_drawings():
            farbe = d.get("fill")
            if farbe and len(farbe) >= 3 and all(abs(c - f) < 0.02 for c, f in zip(farbe, FUELLFARBE)):
                r = fitz.Rect(d.get("rect"))
                if not r.is_empty and r.width < 0.95 * seite.rect.width:
                    aus.append(r)
    except Exception:
        pass
    return aus


# ----------------------------------------------------------------------
# Scan-Seiten: Tinte in Unterschriftsblöcken und neben Personenangaben
# ----------------------------------------------------------------------
_GRUSS_RE = re.compile(r"(?i)\bmit\s+(?:freundlichen|besten|herzlichen|lieben|vielen)\b|\b(?:freundliche|beste|viele|"
                       r"herzliche|liebe)n?\s+gr[üu](?:ß|ss)e|\bhochachtungsvoll\b|\bmfg\b")
# Grußformeln für den unscharfen Vergleich mit OCR-Zeilen ("Mit freundlichen GrüBen", "Mlt freundllchen Grüßen")
_GRUSS_FORMELN = ("mit freundlichen grüßen", "mit freundlichem gruß", "freundliche grüße", "mit besten grüßen",
                  "beste grüße", "mit herzlichen grüßen", "herzliche grüße", "mit lieben grüßen", "liebe grüße",
                  "mit vielen grüßen", "viele grüße", "mit kollegialen grüßen", "mit freundlichen kollegialen grüßen",
                  "mit verbindlichen grüßen", "schöne grüße", "hochachtungsvoll", "mfg")
# Unterschriftsfeld: das Hauptwort ("Unterschrift", "Unterschriften", "(Unterschrift Versicherungsnehmer)", wie die OCR
# es liest: "Unterschrlft", "Unterschritt") – nicht das Verb ("bitte unterschreiben")
_UNTERSCHRIFT_ETIKETT_RE = re.compile(r"(?i)(?<![a-zäöüß])unter\s?schr[il1|!í][fſt]t?(?:en)?(?![a-zäöüß])")
GRUND_UNTERSCHRIFT = "Unterschrift/Name unter der Grußformel nicht lesbar – bitte ansehen"
GRUND_UNTERSCHRIFTSFELD = "Unterschrift/Name am Unterschriftsfeld nicht lesbar – bitte ansehen"
GRUND_PERSONENTINTE = "Schrift neben einer Personenangabe nicht verlässlich lesbar – bitte ansehen"
GRUND_BANKTINTE = "Schrift neben einer Bank- oder Kontoangabe nicht verlässlich lesbar – bitte ansehen"
# Etiketten einer Bankverbindung mit Doppelpunkt (auch mit Zusatz in Klammern, wie die OCR sie liest: "Kreditinstitut
# (Name und BIC}:") – oder allein in ihrer Zelle, ein Formularfeld ("IBAN")
_BANK_ETIKETT_RE = re.compile(r"(?i)(?<![\w])(?:kreditinstitut|geldinstitut|name\s+der\s+bank|bankname|bank|iban|bic|"
                              r"swift(?:-code)?|kontonummer|konto-?nr\.?|kto\.?(?:-?nr\.?)?)"
                              r"(?:\s*[(\[{][^()\[\]{}]{0,40}[)\]}])?(?:\s*:|\s*(?=\t|$))")
UNTERSCHRIFT_ZEILEN = 6        # so viele Zeilenhöhen unter der Grußformel gehören zum Unterschriftsblock
UNTERSCHRIFT_BREITE = 300      # … ab 15 pt links der Grußformel so breit (pt, in Leserichtung)
TINTE_DPI = 72                 # Auflösung der Tintenprüfung (1 Pixel = 1 pt)
TINTE_DUNKEL = 110             # Grauwert, unter dem ein Pixel sicher Tinte ist (Kern eines Strichs) – gezählt wird …
TINTE_ABSTAND_PAPIER = 60      # … jedes Pixel, das um so viel dunkler ist als das Papier (Median der Seite), höchstens
TINTE_DUNKEL_MAX = 180         #     bis zu diesem Grauwert (graue Schwärzungsrechtecke 235 nie): dünne, blasse Striche
                               #     (Kugelschreiber) zählen so mit; eine Zelle braucht aber auch ein Kernpixel – der
                               #     helle Rand erklärter Wörter jenseits ihres OCR-Kastens zählt nicht
LINIE_DICKE = 4                # Rest einer geraden Linie (Unter-/Durchstreichung zwischen erklärten Wörtern): höchstens
LINIE_STEIGUNG = 0.09          # so viele Pixel stark, höchstens ~5° geneigt und gerade: die Schwerpunkte der Spalten
LINIE_ABWEICHUNG = 1.5         # weichen höchstens so viele Pixel von ihrer Ausgleichsgeraden ab (gemessen: Reste von
                               # Linien 0,0-1,1 Pixel, flache Unterschriftszüge 1,8-5,7 Pixel)
TINTE_ZELLE = 6                # Zellen (Pixel) für die Tintendichte
TINTE_MIN_PIXEL = 5            # nicht erklärte Tintenpixel, ab denen eine Zelle zählt
TINTE_MIN_ZELLEN = 4           # so viele zusammenhängende Zellen sind ein Verdacht (Punkte, Striche nicht)
LINIE_MIN_PIXEL = 40           # dunkle Läufe ab dieser Länge (waagerecht/senkrecht) sind Linien, keine Schrift
WORT_HOEHE_MAX = 1.8           # OCR-Wortkasten höher als 1,8 x die übliche Worthöhe: Unterschriftszug oder Wort samt
                               # Zug, keine verlässliche Lesung (außer auf Seiten mit vielen hohen Kästen – Fax mit
HOHE_KAESTEN_ANTEIL = 0.10     # halber senkrechter Auflösung: ab diesem Anteil hoher Kästen erklärt ein bekanntes Wort
                               # seinen hohen Kasten; gemessen: Fax-Seite 35 %, sonst unter 2 %)
LESUNG_BREITE_MAX = 1.25       # OCR-Wortkasten breiter als 1,25 x Schrifthöhe je gelesenes Zeichen (Schrifthöhe: eigene
                               # oder übliche, die größere): der Kasten passt nicht zum Text – ein Zug, als "Med" oder
                               # "az" gelesen (gemessen auf Scans: gedruckte Wörter bis 1,0, gelesene Züge ab 1,3)
ZUG_ZEILEN = 5.0               # Unterschriftszug zu einem geschwärzten Namen: höchstens so viele Zeilenhöhen darüber
ROLLE_ZEILEN = 4.5             # über einer Zeile aus Rollen ("Mandant", "Makler"): so viele Zeilenhöhen – Name, Linie
                               # und der Zug darüber (Generator: Oberkante des Zugs ~4,4 Rollenhöhen über der Rolle)
# Text einer Rolle: Buchstaben, Teile nur mit Trenner (" ", "/", "/-", "-") oder "(in)" – jede Wiederholung beginnt mit
# einem Trenner, sonst liefe der Ausdruck an langen Wörtern mit Komma am Ende exponentiell zurück
_ROLLE_RE = re.compile(r"[^\W\d_]+(?:(?: |/-?|-)\(?[^\W\d_]+\)?|\([^\W\d_]+\))*\.?")


def _falten_buchstaben(text: str) -> str:
    """Kleinbuchstaben a-z ohne Diakritika (ß -> ss) – für den unscharfen Vergleich von OCR-Zeilen."""
    t = unicodedata.normalize("NFKD", (text or "").replace("ß", "ss").replace("ẞ", "ss").lower())
    return "".join(c for c in t if "a" <= c <= "z")


_GRUSS_GEFALTET = tuple(_falten_buchstaben(f) for f in _GRUSS_FORMELN)


def ist_grussformel(zeile: str) -> bool:
    """Ist die Zeile eine Grußformel – auch so, wie die OCR sie liest ("Mit freundlichen GrüBen", "Mlt freundllchen
    Grüßen")? Richtig geschrieben überall in der Zeile (_GRUSS_RE); unscharf nur als eigene, kurze Zeile: ohne
    Satz- und Leerzeichen, Diakritika gefaltet, zu mindestens 82 % gleich einer Formel."""
    if _GRUSS_RE.search(zeile or ""):
        return True
    t = _falten_buchstaben(zeile)
    if len(t) < 3:
        return False
    return any(0.75 * len(f) <= len(t) <= len(f) + 4 and difflib.SequenceMatcher(None, t, f).ratio() >= 0.82
               for f in _GRUSS_GEFALTET)


def _ist_fliesstext(zeile: str) -> bool:
    """Fließtext (mindestens zwei kleingeschriebene Wörter ab drei Buchstaben, "Verletzt wurde niemand."): seine
    Wörter prüfen die Textregeln mit Namenslisten und Kontext – großgeschriebene Wörter am Satzanfang sind hier
    keine Namen. Ein Unterschriftsblock ("i. A. Martina Schulz", "V. De Luca") ist kein Fließtext."""
    return sum(1 for w in re.findall(r"[^\W\d_]{3,}", zeile or "") if w[0].islower()) >= 2


def _fuss_fliesstext(text: str) -> bool:
    """Fließtext am Seitenende ("Das Verfahren vor dem Amtsgericht Kassel ist noch nicht abgeschlossen", "Den Beitrag
    buchen wir … ab"): zwei kleingeschriebene Wörter, die nicht auch in Pflichtangaben stehen (_FUSS_KLEINWOERTER: "Sitz
    der Gesellschaft", "Bank für Kirche und Diakonie", "eingetragen beim Amtsgericht") – ab vier Buchstaben oder ein
    Funktionswort ("den", "wir", "ist"), je ein ganzes Wort zwischen Leerzeichen; OCR-Bruchstücke ("uat-ıdNr.",
    "vor-ıunı.", "med.") zählen nicht."""
    n = 0
    for stueck in (text or "").split():
        w = stueck.strip(".,;:!?()\"'„“”‚‘’»«")
        if len(w) < 3 or not w.isalpha() or not w.islower() or "ı" in w or w in _FUSS_KLEINWOERTER:
            continue
        if len(w) >= 4 or w in _STOPPWOERTER or w in ("ist", "hat", "war", "tun", "gab", "kam", "bat"):
            n += 1
    return n >= 2


def _wortstellen(m) -> list:
    """[(start, ende, Wortkasten)] der OCR-Wörter des Seitenmodells in Textfolge (Lesefolge)."""
    stellen: dict = {}
    for i, g in enumerate(m.abbildung):
        if g < 0 or i >= len(m.text) or m.wort_ids[g] < 0:
            continue
        wid = m.wort_ids[g]
        s, e = stellen.get(wid, (i, i + 1))
        stellen[wid] = (min(s, i), max(e, i + 1))
    return sorted((s, e, fitz.Rect(m.ocr_boxen[wid])) for wid, (s, e) in stellen.items())


def _lesekasten(r, winkel: int, schraeg: float):
    """Rechteck in gerade gerückten Lesekoordinaten (Leserichtung +x, Zeilen untereinander +y)."""
    return fitz.Rect(_ocr.lesekasten((r.x0, r.y0, r.x1, r.y1), winkel, schraeg))


def _aus_lesekasten(r, winkel: int, schraeg: float):
    """Rechteck in Lesekoordinaten -> umschließendes Rechteck in Seitenkoordinaten."""
    ecken = [sm._aus_lesekoordinaten(x, y, winkel, schraeg) for x in (r.x0, r.x1) for y in (r.y0, r.y1)]
    return fitz.Rect(min(e[0] for e in ecken), min(e[1] for e in ecken),
                     max(e[0] for e in ecken), max(e[1] for e in ecken))


_LINIENLAUF_RE = re.compile(rb"\x01{%d,}" % LINIE_MIN_PIXEL)


def _linienpixel(daten, breite: int, hoehe: int, dunkel: int = TINTE_DUNKEL) -> bytearray:
    """Pixel langer dunkler Läufe (waagerecht oder senkrecht ab LINIE_MIN_PIXEL): Unterschriftslinien, Rahmen,
    Tabellenlinien – keine Schrift. Läufe über bytes.translate + regulären Ausdruck (schnell genug für ganze
    Seiten)."""
    bits = bytes(daten).translate(bytes(1 if i < dunkel else 0 for i in range(256)))
    linie = bytearray(breite * hoehe)
    for y in range(hoehe):
        for t in _LINIENLAUF_RE.finditer(bits, y * breite, (y + 1) * breite):
            linie[t.start():t.end()] = b"\x01" * (t.end() - t.start())
    for x in range(breite):
        for t in _LINIENLAUF_RE.finditer(bits[x::breite]):
            for k in range(t.start(), t.end()):
                linie[k * breite + x] = 1
    return linie


def _abweichung_von_gerade(punkte) -> float:
    """Größte Abweichung der Punkte (k, v) von ihrer Ausgleichsgeraden v = a + b·k (kleinste Quadrate)."""
    n = len(punkte)
    if n < 3:
        return 0.0
    mk = sum(k for k, _ in punkte) / n
    mv = sum(v for _, v in punkte) / n
    skk = sum((k - mk) ** 2 for k, _ in punkte)
    b = sum((k - mk) * (v - mv) for k, v in punkte) / skk if skk else 0.0
    return max(abs(v - mv - b * (k - mk)) for k, v in punkte)


def _linienrest(pixel) -> bool:
    """Ist eine Tintengruppe der Rest einer geraden Linie – eine Unter- oder Durchstreichung, deren Stücke zwischen
    erklärten Wörtern stehen bleiben? Dünn (je Spalte bzw. Zeile höchstens LINIE_DICKE Pixel), höchstens ~5°
    geneigt und GERADE: die Schwerpunkte der Spalten (bzw. Zeilen) liegen bis auf LINIE_ABWEICHUNG Pixel auf einer
    Geraden. Schrift hat dickere Stellen (Grundstriche), ein Unterschriftszug schwingt auf und ab – auch ein flacher,
    dünner Kugelschreiberzug, der in das Fenster der Neigung passt."""
    xs = [x for x, _ in pixel]
    ys = [y for _, y in pixel]
    breite, hoehe = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
    for lang, kurz, quer, laengs in ((breite, hoehe, xs, ys), (hoehe, breite, ys, xs)):
        if lang >= 2 * TINTE_ZELLE and kurz <= LINIE_DICKE + LINIE_STEIGUNG * lang:
            spalten: dict = {}
            for k, v in zip(quer, laengs):
                eintrag = spalten.setdefault(k, [0, 0])
                eintrag[0] += 1
                eintrag[1] += v
            if max(n for n, _ in spalten.values()) > LINIE_DICKE:
                continue
            schwerpunkte = [(k, s / n) for k, (n, s) in spalten.items()]
            if _abweichung_von_gerade(schwerpunkte) <= LINIE_ABWEICHUNG:
                return True
    return False


_TAB_KERN = bytes(1 if i < TINTE_DUNKEL else 0 for i in range(256))
_TAB_DUNKEL: dict = {}
_EINS_RE = re.compile(rb"\x01")


class _Seitenbild:
    """Graubild einer Seite bei TINTE_DPI – einmal je Seite gerendert, die Bereiche werden daraus geschnitten. Dazu
    EINE Maske der Seite: Linien (_linienpixel) und erklärte Rechtecke (erklaeren) – Aufwand linear in Seitengröße
    und Zahl der Rechtecke, nicht Bereiche x Rechtecke (Scan-Listen mit vielen Personen-Platzhaltern)."""

    def __init__(self, seite):
        self.rect = fitz.Rect(seite.rect)
        try:
            pix = seite.get_pixmap(dpi=TINTE_DPI, colorspace=fitz.csGRAY, alpha=False)
            self.breite, self.hoehe, self.daten = pix.width, pix.height, bytes(pix.samples)
        except Exception:
            self.breite, self.hoehe, self.daten = 0, 0, b""
        self.sx = self.breite / self.rect.width if self.rect.width else 0.0
        self.sy = self.hoehe / self.rect.height if self.rect.height else 0.0
        probe = sorted(self.daten[::7]) if self.daten else [255]
        papier = probe[len(probe) // 2]
        self.dunkel = max(TINTE_DUNKEL, min(TINTE_DUNKEL_MAX, papier - TINTE_ABSTAND_PAPIER))
        self._linie = None
        self._maske = None

    def linien(self) -> bytearray:
        """Linienmaske der ganzen Seite (einmal je Seite): eine Tabellenlinie, die einen kleinen Bereich nur kurz
        quert, ist dort als Linie erkannt."""
        if self._linie is None:
            self._linie = _linienpixel(self.daten, self.breite, self.hoehe, self.dunkel)
        return self._linie

    def erklaeren(self, rechtecke, rand: float = 1.5) -> None:
        """Erklärte Rechtecke (Seitenkoordinaten, je um `rand` vergrößert) in die Maske der Seite rastern – einmal je
        Seite; jeder Bereich schneidet sie danach nur noch aus."""
        if not self.breite or not self.hoehe:
            return
        maske = bytearray(self.linien())
        b, h = self.breite, self.hoehe
        rx, ry, sx, sy = self.rect.x0, self.rect.y0, self.sx, self.sy
        for r in rechtecke:
            try:
                x0, y0, x1, y1 = (float(v) for v in tuple(r)[:4])
            except (TypeError, ValueError):
                continue
            px0, px1 = max(0, int((x0 - rand - rx) * sx)), min(b, int((x1 + rand - rx) * sx) + 1)
            py0, py1 = max(0, int((y0 - rand - ry) * sy)), min(h, int((y1 + rand - ry) * sy) + 1)
            if px1 <= px0 or py1 <= py0:
                continue
            voll = b"\x01" * (px1 - px0)
            for y in range(py0, py1):
                maske[y * b + px0:y * b + px1] = voll
        self._maske = maske

    def ein_textband(self, kasten, winkel: int, hoehe: float) -> bool:
        """Liegt die Tinte im Kasten (Seitenkoordinaten; ohne Linien) in EINEM Band von 1,5 x `hoehe` quer zur
        Leserichtung – also nur Schrift einer Zeile, der Rest des Kastens leer (Tabellenkopf mit grauem Grund)? Nein,
        wenn sie sich darüber hinaus erstreckt: ein Wort samt Zug oder Namen darüber in EINEM hohen Kasten."""
        if not self.breite or not self.hoehe:
            return True
        x0 = max(0, int((kasten.x0 - self.rect.x0) * self.sx))
        y0 = max(0, int((kasten.y0 - self.rect.y0) * self.sy))
        x1 = min(self.breite, int((kasten.x1 - self.rect.x0) * self.sx + 0.999))
        y1 = min(self.hoehe, int((kasten.y1 - self.rect.y0) * self.sy + 0.999))
        if x1 <= x0 or y1 <= y0:
            return True
        linie = self.linien()
        senkrecht = winkel in (90, 270)                  # Zeilen laufen senkrecht: Band über die x-Achse
        profil = [0] * ((x1 - x0) if senkrecht else (y1 - y0))
        for y in range(y0, y1):
            for x in range(x0, x1):
                i = y * self.breite + x
                if self.daten[i] < self.dunkel and not linie[i]:
                    profil[(x - x0) if senkrecht else (y - y0)] += 1
        gesamt = sum(profil)
        if not gesamt:
            return True
        band = max(1, int(1.5 * hoehe * (self.sx if senkrecht else self.sy) + 0.999))
        bestes = max(sum(profil[i:i + band]) for i in range(max(1, len(profil) - band + 1)))
        return bestes >= 0.9 * gesamt

    def ausschnitt(self, bereich):
        """(Pixel, Maske, Breite, Höhe, Bereich in Seitenkoordinaten genau auf Pixelgrenzen) oder None. Maske: Linien
        der Seite und – nach erklaeren() – die erklärten Rechtecke."""
        if not self.breite or not self.hoehe:
            return None
        x0 = max(0, int((bereich.x0 - self.rect.x0) * self.sx))
        y0 = max(0, int((bereich.y0 - self.rect.y0) * self.sy))
        x1 = min(self.breite, int((bereich.x1 - self.rect.x0) * self.sx + 0.999))
        y1 = min(self.hoehe, int((bereich.y1 - self.rect.y0) * self.sy + 0.999))
        if x1 - x0 < TINTE_ZELLE or y1 - y0 < TINTE_ZELLE:
            return None
        quelle = self._maske if self._maske is not None else self.linien()
        zeilen = range(y0, y1)
        daten = b"".join(self.daten[y * self.breite + x0:y * self.breite + x1] for y in zeilen)
        maske = b"".join(bytes(quelle[y * self.breite + x0:y * self.breite + x1]) for y in zeilen)
        genau = fitz.Rect(self.rect.x0 + x0 / self.sx, self.rect.y0 + y0 / self.sy,
                          self.rect.x0 + x1 / self.sx, self.rect.y0 + y1 / self.sy)
        return daten, maske, x1 - x0, y1 - y0, genau


def _tintengruppen(bild: _Seitenbild, bereich) -> list:
    """Dichte, nicht erklärte Tinte im Bereich (Seitenkoordinaten; erklärt ist, was bild.erklaeren() und die Linien
    der Seite abdecken): Rechteck je zusammenhängender Gruppe von Tintenzellen (Zellen mit höchstens einer leeren
    Zelle dazwischen gehören zusammen); Gruppen unter TINTE_MIN_ZELLEN Zellen (Punkte, Staub, ein einzelnes Komma)
    und Reste gerader Linien (_linienrest) zählen nicht. Tinte: dunkler als bild.dunkel (relativ zum Papier, auch
    blasse Striche)."""
    teil = bild.ausschnitt(fitz.Rect(bereich) & bild.rect)
    if teil is None:
        return []
    daten, maske, breite, hoehe, bereich = teil
    sx, sy = bild.sx, bild.sy
    tabelle = _TAB_DUNKEL.get(bild.dunkel)
    if tabelle is None:
        tabelle = _TAB_DUNKEL[bild.dunkel] = bytes(1 if i < bild.dunkel else 0 for i in range(256))
    # Tintenpixel ohne Maske: Bytefolgen als ganze Zahlen verknüpft (schnell genug ohne numpy)
    n = breite * hoehe
    frei = int.from_bytes(maske, "big") ^ int.from_bytes(b"\x01" * n, "big")
    tinte = (int.from_bytes(daten.translate(tabelle), "big") & frei).to_bytes(n, "big")
    kern_bits = (int.from_bytes(daten.translate(_TAB_KERN), "big") & frei).to_bytes(n, "big")
    zellen: dict = {}
    kern: set = set()
    for t in _EINS_RE.finditer(tinte):
        y, x = divmod(t.start(), breite)
        k = (x // TINTE_ZELLE, y // TINTE_ZELLE)
        zellen.setdefault(k, []).append((x, y))
    for t in _EINS_RE.finditer(kern_bits):
        y, x = divmod(t.start(), breite)
        kern.add((x // TINTE_ZELLE, y // TINTE_ZELLE))
    offen = {k for k, p in zellen.items() if len(p) >= TINTE_MIN_PIXEL and k in kern}
    gruppen = []
    while offen:
        stapel = [offen.pop()]
        gruppe = list(stapel)
        while stapel:
            cx, cy = stapel.pop()
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    k = (cx + dx, cy + dy)
                    if k in offen:
                        offen.remove(k)
                        gruppe.append(k)
                        stapel.append(k)
        if len(gruppe) >= TINTE_MIN_ZELLEN and not _linienrest([p for k in gruppe for p in zellen[k]]):
            gruppen.append(fitz.Rect(min(k[0] for k in gruppe) * TINTE_ZELLE / sx + bereich.x0,
                                     min(k[1] for k in gruppe) * TINTE_ZELLE / sy + bereich.y0,
                                     (max(k[0] for k in gruppe) + 1) * TINTE_ZELLE / sx + bereich.x0,
                                     (max(k[1] for k in gruppe) + 1) * TINTE_ZELLE / sy + bereich.y0) & bereich)
    return sorted(gruppen, key=lambda r: (r.y0, r.x0))


def _gruss_schlusswort(zeile: str) -> bool:
    """Ist die Zeile nur das Schlusswort einer Grußformel ("Grüßen", "GrüBen," "Gruß") – eine schräg gelesene Formel,
    die das Seitenmodell in einzelne Wörter zerlegt hat?"""
    if len((zeile or "").split()) != 1:
        return False
    t = _falten_buchstaben(zeile)
    return len(t) >= 4 and any(difflib.SequenceMatcher(None, t, f).ratio() >= 0.75
                               for f in ("grussen", "grusse", "gruss"))      # "GrüBen" -> gruben: 0,77


def _grussformel_gruppen(text: str, folge: list) -> list:
    """Zeilen, die eine Grußformel bilden – je Gruppe die Zeilen-IDs. folge: [(zid, Zeile)] in Textfolge. Eine Zeile
    (ist_grussformel) oder bis zu vier aufeinanderfolgende kurze Zeilen, die erst zusammen eine Formel ergeben: ohne
    Angabe der Schräglage (OCR-Wörter als 5-Tupel) zerlegt das Seitenmodell eine schräg gelesene Zeile in einzelne
    Wörter ("Mit" | "freundlichen" | "Grüßen"); ein folgendes Schlusswort ("Grüßen") gehört zur Gruppe."""
    gruppen = []
    i, n = 0, len(folge)
    while i < n:
        inhalt = text[folge[i][1].start:folge[i][1].ende]
        ende = None
        if ist_grussformel(inhalt):
            ende = i
        elif len(inhalt.split()) <= 2:
            teile = [inhalt]
            for j in range(i + 1, min(i + 4, n)):
                naechste = text[folge[j][1].start:folge[j][1].ende]
                if len(naechste.split()) > 2:
                    break
                teile.append(naechste)
                if ist_grussformel(" ".join(teile)):
                    ende = j
                    break
        if ende is None:
            i += 1
            continue
        while ende + 1 < n and _gruss_schlusswort(text[folge[ende + 1][1].start:folge[ende + 1][1].ende]):
            ende += 1
        gruppen.append([zid for zid, _ in folge[i:ende + 1]])
        i = ende + 1
    return gruppen


def _zellen(inhalt: str) -> list:
    """[(start, ende)] der Zellen einer Zeile (getrennt durch Spaltentrenner oder drei Leerzeichen), ohne Leerraum am
    Rand."""
    aus, pos = [], 0
    for t in list(re.finditer(r"\t+| {3,}", inhalt)) + [None]:
        a, b = pos, (t.start() if t is not None else len(inhalt))
        stueck = inhalt[a:b]
        if stueck.strip():
            a += len(stueck) - len(stueck.lstrip())
            b -= len(stueck) - len(stueck.rstrip())
            aus.append((a, b))
        if t is not None:
            pos = t.end()
    return aus


def _unterschrift_pruefen(seite, m, schwaerzungen, pruefung=None, gemeldet=(), ausrichtung=None) -> list:
    """Scan-Seite: dichte Tinte in Unterschriftsblöcken und neben Personenangaben, die die OCR nicht VERLÄSSLICH
    gelesen hat – die Texterkennung kann dort nichts prüfen, also selbst ansehen.

    Bereiche (in Lesekoordinaten, also auch auf gedrehten und schrägen Scans richtig: Ausrichtung und Schräglage aus
    `ausrichtung` – (Winkel, Schräglage) der OCR-Wörter (10-Tupel), wie im Seitenmodell –, sonst aus der Lesefolge
    geschätzt, ohne Schräglage):
      * unter jeder Grußformel (UNTERSCHRIFT_ZEILEN Zeilenhöhen, UNTERSCHRIFT_BREITE breit) – auch einer, die das
        Seitenmodell in Wörter zerlegt hat (_grussformel_gruppen);
      * über und rechts neben "Unterschrift";
      * über einer Zeile aus Rollen ("Mandant" | "Makler", "Versicherungsnehmer" – zweispaltiger Unterschriftsblock:
        Ort, Datum – Zug – Linie – Name – Rolle), samt der Zeile selbst;
      * rechts hinter einem Personen-Etikett mit Doppelpunkt ("Name:", "Kontoinhaber:");
      * links und rechts neben einem Personen-Platzhalter.
    Erklärt ist Tinte unter Schwärzungsrechtecken, der Textebene (Platzhalter), schon gemeldeten Verdachtsstellen
    (`gemeldet`) und unter OCR-Wörtern, deren Lesung sie unverdächtig macht (_Seitenpruefung.lesung_harmlos); ein
    bekanntes Wort in einem hohen Kasten nur, wenn dessen Tinte in EINEM Textband liegt (_Seitenbild.ein_textband).
    Rückgabe: je Bereich mit Tinte ein Verdacht (start -1) mit einem Rechteck je Tintengruppe."""
    stellen = _wortstellen(m)
    if not stellen:
        return []
    if pruefung is None:
        pruefung = _Seitenpruefung(m, _Wissen(_wissen_laden()), schwaerzungen=schwaerzungen)
    text = m.text
    if ausrichtung is not None:
        winkel, schraeg = int(ausrichtung[0] or 0) % 360, float(ausrichtung[1] or 0.0)
    else:
        winkel, schraeg = _ocr.ausrichtung_der_woerter([(b.x0, b.y0, b.x1, b.y1, text[s:e]) for s, e, b in stellen])
    lese = [_lesekasten(b, winkel, schraeg) for _, _, b in stellen]
    hoehen = sorted(r.height for r, (s, e, _) in zip(lese, stellen) if sum(c.isalnum() for c in text[s:e]) >= 2)
    if not hoehen:
        return []
    ueblich = max(hoehen[len(hoehen) // 2], 4.0)
    hohe_kaesten = sum(1 for h in hoehen if h > WORT_HOEHE_MAX * ueblich) >= HOHE_KAESTEN_ANTEIL * len(hoehen)
    # Zeilen in Lesekoordinaten: Wörter in üblicher Schrifthöhe (ein als Wort gelesener Unterschriftszug in derselben
    # Zeile verschöbe sonst den Bereich), sonst alle Wörter der Zeile; Grußformel- und Fließtextzeilen
    zeilen: dict = {}
    alle: dict = {}
    for (s, e, _), r in zip(stellen, lese):
        z = m.zeile_von(s)
        if z is None:
            continue
        alle[z.id] = (z, r if z.id not in alle else alle[z.id][1] | r)
        if r.height <= WORT_HOEHE_MAX * ueblich:
            zeilen[z.id] = (z, r if z.id not in zeilen else zeilen[z.id][1] | r)
    for zid, eintrag in alle.items():
        zeilen.setdefault(zid, eintrag)
    folge = sorted(((zid, z) for zid, (z, _) in zeilen.items()), key=lambda t: t[1].start)
    gruss_gruppen = _grussformel_gruppen(text, folge)
    gruss = {zid for gruppe in gruss_gruppen for zid in gruppe}

    def gleiche_hoehe(a, b) -> bool:
        return min(a.y1, b.y1) - max(a.y0, b.y0) >= 0.5 * min(a.height, b.height)

    def hoehe(r) -> float:
        return max(min(r.height, 1.3 * ueblich), 8.0)

    def lesekasten_stelle(s, e):
        b = pruefung.box(s, e)
        return _lesekasten(fitz.Rect(b), winkel, schraeg) if b is not None else None

    def nur_rollen(inhalt) -> bool:
        """Besteht der Text nur aus Rollen ("Mandant", "Makler", "Versicherungsnehmer/in"), jede eine eigene Zelle
        aus Buchstaben (keine Nummer davor wie bei einer Abschnittsüberschrift "4. Unfallgegner", kein Komma oder
        Doppelpunkt dahinter wie bei einem Feldetikett "Name, Vorname")?"""
        zellen = _zellen(inhalt)
        return bool(zellen) and len(inhalt.split()) <= 6 and all(
            _ROLLE_RE.fullmatch(inhalt[a:b]) and sum(c.isalpha() for c in inhalt[a:b]) >= 4
            and pruefung._etikett_in(inhalt[a:b], ("person",)) for a, b in zellen)

    def rollenzeile(z, r) -> bool:
        """Zeile aus Rollen unter einem Unterschriftsblock: nur Rollen, daneben in der Reihe (gleiche Höhe, bis
        6 Zeilenhöhen Abstand) nichts anderes – kein Wert, kein Platzhalter wie hinter dem Feldetikett "Name" –, die
        Schrift nicht höher als üblich (keine Überschrift), außer die OCR hat die Rolle samt Zug oder Namen darüber
        als EIN hohes Wort gelesen."""
        if not nur_rollen(text[z.start:z.ende]):
            return False
        if 1.3 * ueblich < r.height <= WORT_HOEHE_MAX * ueblich:
            return False
        nah = 6 * hoehe(r)
        for y in m.zeilen:
            if y.id == z.id or y.rect is None or not text[y.start:y.ende].strip():
                continue
            ry = _lesekasten(fitz.Rect(y.rect), winkel, schraeg)
            if gleiche_hoehe(r, ry) and ry.x0 < r.x1 + nah and ry.x1 > r.x0 - nah \
                    and not nur_rollen(text[y.start:y.ende]):
                return False
        return True

    # Fließtext je sichtbarer Zeile: das Seitenmodell trennt eine Zeile an großen Lücken (Platzhalter, Spalten) –
    # "Oberfranken, Aktenzeichen" | [VERTRAGS-NR] | "nahm den Unfall auf." ist EINE Fließtextzeile
    fliesstext = set()
    for zid, (z, r) in zeilen.items():
        reihe = " ".join(text[y.start:y.ende] for y, ry in zeilen.values() if gleiche_hoehe(r, ry))
        if _ist_fliesstext(reihe):
            fliesstext.add(zid)
    bereiche = []
    for gruppe in gruss_gruppen:
        r = fitz.Rect(zeilen[gruppe[0]][1])
        for zid in gruppe[1:]:
            r |= zeilen[zid][1]
        h = max(min(min(zeilen[zid][1].height for zid in gruppe), 1.3 * ueblich), 8.0)
        bereiche.append((fitz.Rect(r.x0 - 15, r.y1 + 1, r.x0 + UNTERSCHRIFT_BREITE,
                                   r.y1 + 1 + UNTERSCHRIFT_ZEILEN * h), GRUND_UNTERSCHRIFT))
    index = pruefung.w.index("person")
    for zid, z in folge:
        if zid in gruss:
            continue
        r = zeilen[zid][1]
        h = hoehe(r)
        inhalt = text[z.start:z.ende]
        # Bereiche über einem Etikett schließen seine Zeile ein: liest die OCR das Etikett samt Zug oder Namen darüber
        # als EIN hohes Wort, liegt der Name im Kasten des Etiketts (der dann nichts erklärt)
        if _UNTERSCHRIFT_ETIKETT_RE.search(inhalt) and len(inhalt.split()) <= 8 and zid not in fliesstext:
            bereiche.append((fitz.Rect(r.x0 - 30, r.y0 - 2.5 * h, r.x1 + 150, r.y1), GRUND_UNTERSCHRIFTSFELD))
            bereiche.append((fitz.Rect(r.x1 + 1, r.y0 - 0.3 * h, r.x1 + 250, r.y1 + 0.3 * h), GRUND_UNTERSCHRIFTSFELD))
            continue
        if zid not in fliesstext and rollenzeile(z, r):
            # Zeile aus Rollen ohne Doppelpunkt ("Mandant" | "Makler"): darüber stehen Name und Unterschrift
            for a, b in _zellen(inhalt):
                k = lesekasten_stelle(z.start + a, z.start + b)
                if k is not None:
                    bereiche.append((fitz.Rect(k.x0 - 30, k.y0 - ROLLE_ZEILEN * h, k.x1 + 150, k.y1),
                                     GRUND_UNTERSCHRIFTSFELD))
            continue
        try:
            treffer = index.finde(inhalt) if index is not None else []
        except Exception:
            treffer = []
        for v in treffer:
            nach = inhalt[v.ende:v.ende + 3]
            if not nach.lstrip(" ").startswith(":") or (v.start > 0 and inhalt[v.start - 1].isalnum()):
                continue
            pos = z.start + v.ende + nach.find(":")
            g = m.abbildung[pos] if pos < len(m.abbildung) else -1
            if g < 0:
                continue
            k = _lesekasten(m.zeichen[g].rect, winkel, schraeg)
            bereiche.append((fitz.Rect(k.x1 + 1, r.y0 - 0.2 * h, k.x1 + 250, r.y1 + 0.2 * h), GRUND_PERSONENTINTE))
        # Bank- und Kontoangaben des Kunden ("Kreditinstitut (Name und BIC):", "IBAN:"): handschriftlich ausgefüllt
        # liest die OCR dort oft nichts – die Tinte dahinter ist eine Bankverbindung
        for b in _BANK_ETIKETT_RE.finditer(inhalt):
            ende = b.end()
            while ende > b.start() + 1 and inhalt[ende - 1].isspace():
                ende -= 1
            pos = z.start + ende - 1
            g = m.abbildung[pos] if pos < len(m.abbildung) else -1
            if g < 0:
                continue
            k = _lesekasten(m.zeichen[g].rect, winkel, schraeg)
            bereiche.append((fitz.Rect(k.x1 + 1, r.y0 - 0.2 * h, k.x1 + 250, r.y1 + 0.2 * h), GRUND_BANKTINTE))

    for s, e, rand in pruefung.platzhalter_boxen():
        if not _PERSONEN_PLATZHALTER_RE.match(text[s:e]):
            continue
        r = _lesekasten(fitz.Rect(rand), winkel, schraeg)
        t = lesekasten_stelle(s, e) or r                  # Zeile des Platzhaltertexts (das graue Rechteck kann
        h = hoehe(t)                                      # mehrere Zeilen hoch sein)
        mitte = (t.y0 + t.y1) / 2
        bereiche.append((fitz.Rect(r.x0 - 2.5 * h, mitte - 0.7 * h, r.x0 - 1, mitte + 0.7 * h), GRUND_PERSONENTINTE))
        bereiche.append((fitz.Rect(r.x1 + 1, mitte - 0.7 * h, r.x1 + 2.5 * h, mitte + 0.7 * h), GRUND_PERSONENTINTE))
    if not bereiche:
        return []
    bild = _Seitenbild(seite)
    erklaert = [fitz.Rect(r) for r in schwaerzungen]
    erklaert += [fitz.Rect(r) for v in gemeldet or () for r in (v.rechtecke or [])]
    erklaert += [z.rect for g, z in enumerate(m.zeichen) if m.wort_ids[g] < 0]          # Textebene: Platzhalter
    for (s, e, b), r in zip(stellen, lese):
        z = m.zeile_von(s)
        zid = z.id if z is not None else None
        art = dict(fliesstext=zid in gruss or zid in fliesstext, lese_breite=r.width)
        if pruefung.lesung_harmlos(s, e, r.height, ueblich, hohe_kaesten=hohe_kaesten, **art):
            erklaert.append(b)
        elif (r.height > WORT_HOEHE_MAX * ueblich and pruefung.lesung_harmlos(s, e, r.height, ueblich, **art)
              and bild.ein_textband(b, winkel, ueblich)):
            erklaert.append(b)          # bekanntes Wort im hohen Kasten, der Rest leer (Tabellenkopf mit grauem Grund)
    # Geschwärzte gedruckte Namen: das graue Rechteck um einen Personen-Platzhalter (die Lage des Namens im Original) –
    # die Tinte eines Unterschriftszugs darüber gehört zu diesem Namen (zug_zum_namen)
    namen = []
    for s, e, rand in pruefung.platzhalter_boxen():
        if not _PERSONEN_PLATZHALTER_RE.match(text[s:e]):
            continue
        glyphen = [fitz.Rect(m.zeichen[g].rect) for g in m.glyphen(s, e)]
        if not glyphen:
            continue
        ph = glyphen[0]
        for r in glyphen[1:]:
            ph |= r
        mitte = fitz.Point((ph.x0 + ph.x1) / 2, (ph.y0 + ph.y1) / 2)
        grau = [fitz.Rect(r) for r in schwaerzungen if fitz.Rect(r).contains(mitte)]
        name_r = grau[0] if grau else ph
        for r in grau[1:]:
            name_r |= r
        namen.append(_lesekasten(name_r, winkel, schraeg))

    def zug_zum_namen(g, zug_namen) -> bool:
        """Ist die Tintengruppe g (Seitenkoordinaten) der Unterschriftszug zu einem geschwärzten gedruckten Namen
        (zug_namen: Rechtecke der Namen in Lesekoordinaten): über dem Namen oder ihn kreuzend – sie ragt über den Namen
        hinaus, aber nicht unter ihn –, höchstens ZUG_ZEILEN Zeilenhöhen darüber und waagerecht im Bereich des Namens?
        Ein Unterschriftszug ist keine lesbare Angabe, und der Name, zu dem er gehört, ist ersetzt."""
        k = _lesekasten(g, winkel, schraeg)
        for n in zug_namen:
            h = hoehe(n)
            if k.x1 < n.x0 - 2 * h or k.x0 > n.x1 + 4 * h:
                continue
            if k.y0 < n.y0 - 0.25 * h and n.y0 - ZUG_ZEILEN * h <= k.y1 <= n.y1 + 0.5 * h:
                return True
        return False

    verdacht, bekannt, gesehen = [], [], set()
    bild.erklaeren(erklaert)
    # Nur Namen ohne ungelesenen Rest daneben: steht links oder rechts des grauen Rechtecks auf Namenshöhe noch Tinte
    # (ein Teil des Namens, den die Erkennung nicht erfasst hat – auch vom Zug gekreuzt), erklärt der Name nichts
    zug_namen = []
    for n in namen:
        h = hoehe(n)
        seiten = (fitz.Rect(n.x0 - 3 * h, n.y0 + 0.15 * n.height, n.x0 - 1, n.y1 - 0.15 * n.height),
                  fitz.Rect(n.x1 + 1, n.y0 + 0.15 * n.height, n.x1 + 3 * h, n.y1 - 0.15 * n.height))
        if not any(_tintengruppen(bild, _aus_lesekasten(r, winkel, schraeg)) for r in seiten):
            zug_namen.append(n)
    for bereich, grund in bereiche:
        schluessel = tuple(round(x) for x in bereich)
        if schluessel in gesehen:
            continue
        gesehen.add(schluessel)
        gruppen = _tintengruppen(bild, _aus_lesekasten(bereich, winkel, schraeg))
        neu = [g for g in gruppen if not any(abs(g & b) > 0.5 * abs(g) for b in bekannt)]
        zuege = [g for g in neu if zug_namen and zug_zum_namen(g, zug_namen)]
        if zuege:
            bekannt += zuege
            neu = [g for g in neu if g not in zuege]
        if neu:
            bekannt += neu
            text_v = {GRUND_PERSONENTINTE: "Personenangabe", GRUND_BANKTINTE: "Bankangabe"}.get(grund,
                                                                                                "Unterschriftsbereich")
            verdacht.append(Verdacht(m.nr, -1, -1, text_v, grund, neu))
    return verdacht


def _seite_nachweislich_leer(seite) -> bool:
    """Steht auf der Scan-Seite nachweislich nichts (leere Rückseite)? Nur dann ist „die OCR hat (fast) nichts
    gelesen“ kein Seitenverdacht. Dasselbe Maß wie beim Status der Schwärzung (analyse.seite_nachweislich_leer: jedes
    Pixel deutlich dunkler als das Papier, mit einem ebensolchen Nachbarn – sieht auch hell gedruckten Text und
    Bleistift). Befund Runde 3b: das frühere eigene Maß (Anteil der Pixel dunkler als Grau 180 bei 50 dpi über 0,0003)
    hielt gut lesbaren hellen Druck (Grau 150/160) für „keine Tinte“ – ein solcher Scan, auf dem die OCR nichts las,
    verließ die Prüfung ohne Seitenverdacht. Ein Pixelmaß, keine Erkennung: die Unabhängigkeit der Prüfung (Modulkopf)
    bleibt gewahrt. Spät importiert (kein Importzyklus mit analyse); im Zweifel (jeder Fehler, auch beim Import, und
    jede Antwort außer einem klaren Ja): nicht leer – die Seite bleibt Verdacht."""
    try:
        from .analyse import seite_nachweislich_leer
        return seite_nachweislich_leer(seite) is True
    except Exception:
        return False


def _rauschanteil(woerter: list) -> float:
    """Anteil der OCR-Wörter, die nur Bruchstücke sind (Striche, einzelne Zeichen, Satzzeichen)."""
    if not woerter:
        return 0.0
    rausch = 0
    for w in woerter:
        t = str(w[4]).strip()
        if len(t) <= 1 or not any(c.isalnum() for c in t) or re.fullmatch(r"[|\\/.,:;'‚’`´^°=_~-]+\w?", t):
            rausch += 1
    return rausch / len(woerter)


def _lesung_unplausibel(woerter) -> bool:
    """Ist die OCR-Lesung einer Scan-Seite Buchstabensalat (verdrehte Seite, Handschrift, unleserlich)?
    Maß und Schwellen der OCR selbst (anonymisierer.ocr: Anteil "starker" Wörter – häufige Wörter, Daten,
    Beträge …; aufrechte Seiten 0,12-0,60, verdrehte 0,00-0,02): ab MIN_TOKENS_WARNUNG Wörtern unplausibel,
    wenn die OCR die Lesung nicht als plausibel gelten ließe. Nötig, weil die Kontroll-OCR der Ausgabe mit der
    Ausrichtung des Originals liest und das selbst nicht meldet – hat schon die Analyse die Seite nicht lesen
    können, liest die Prüfung sonst denselben Salat, und keine Regel greift verlässlich."""
    bewertung = _ocr._lesung_bewerten([w[4] for w in woerter])
    return bewertung["tokens"] >= _ocr.MIN_TOKENS_WARNUNG and not _ocr._plausibel(bewertung)


def _ohne_platzhalter(woerter: list, boxen: list) -> list:
    """OCR-Wörter ohne die mitgelesenen Platzhalter (Wortmitte im Platzhalter oder halb überdeckt)."""
    if not boxen:
        return woerter
    kaesten = [(b.x0, b.y0, b.x1, b.y1) for b in boxen]
    aus = []
    for w in woerter:
        x0, x1 = min(w[0], w[2]), max(w[0], w[2])
        y0, y1 = min(w[1], w[3]), max(w[1], w[3])
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        flaeche = max((x1 - x0) * (y1 - y0), 1e-6)
        verdeckt = False
        for bx0, by0, bx1, by1 in kaesten:
            if bx0 <= mx <= bx1 and by0 <= my <= by1:
                verdeckt = True
                break
            breite, hoehe = min(x1, bx1) - max(x0, bx0), min(y1, by1) - max(y0, by0)
            if breite > 0 and hoehe > 0 and breite * hoehe >= 0.5 * flaeche:
                verdeckt = True
                break
        if not verdeckt:
            aus.append(w)
    return aus


def restrisiko_pruefen(ausgabe_pfad, ocr=None, platzhalter=None, profil: str = "hoch", nie=None, wissen=None, *,
                       ocr_modus=None, winkel=None, bildbereiche=None, ocr_woerter=None, abgewaehlt=None,
                       felder=None, abbruch=None) -> list:
    """Prüft die AUSGABE unabhängig von der Erkennung auf übrig gebliebene personenbezogene Daten.

    ausgabe_pfad: geschwärzte PDF; ocr: OcrDienst (oder ein Ersatz mit woerter()); platzhalter: Ersatztexte des
    Laufs (nie Verdacht); profil: Schutzstufe (die Prüfung ist in jeder Stufe gleich empfindlich); nie: NIE-Liste
    der Nutzerin; wissen: Modul der Wissensbasis (Standard: anonymisierer.wissen).
    Von der Schwärzung zusätzlich übergeben (alle optional): ocr_modus {Seite: "seite"|"bilder"} und
    bildbereiche {Seite: [Rect]} aus dem Modell des Originals, winkel {Seite: Grad} (Ausrichtung des Originals –
    die Kontroll-OCR der Selbstkontrolle liegt damit schon im Zwischenspeicher), ocr_woerter {Seite: Wörter}
    für unveränderte Seiten (OCR der Analyse, kein zweiter OCR-Lauf), abgewaehlt [(Seite, Text)] (bewusst
    nicht geschwärzte Stellen), felder [Feld] (Formularfelder des Originals), abbruch (threading.Event).
    Rückgabe: Liste von Verdacht (seite 0-basiert, Rechtecke in Seitenkoordinaten nach remove_rotation)."""
    pfad = Path(ausgabe_pfad)
    w = _Wissen(wissen if wissen is not None else _wissen_laden())
    abgewaehlt_je_seite: dict = {}
    for eintrag in abgewaehlt or ():
        try:
            nr, text = (eintrag["seite"], eintrag["text"]) if isinstance(eintrag, dict) else eintrag
            abgewaehlt_je_seite.setdefault(int(nr), []).append(str(text))
        except Exception:
            continue
    felder_je_seite: dict = {}
    for feld in felder or ():
        try:
            nr = feld["seite"] if isinstance(feld, dict) else feld.seite
            felder_je_seite.setdefault(int(nr), []).append(feld)
        except Exception:
            continue
    verdacht: list = []
    doc = fitz.open(pfad)
    try:
        for nr in range(len(doc)):
            if abbruch is not None and abbruch.is_set():
                raise sm.Abgebrochen()
            seite = doc[nr]
            if seite.rotation:
                seite.remove_rotation()
            modus = ocr_modus.get(nr, "nein") if ocr_modus is not None else sm.ocr_entscheidung(seite)
            woerter, quelle = None, "ocr"
            if modus in ("seite", "bilder"):
                quelle = "ocr" if modus == "seite" else "bild"
                if ocr_woerter is not None and nr in ocr_woerter:
                    woerter = [tuple(x) for x in ocr_woerter[nr]]
                elif ocr is not None:
                    if modus == "seite":
                        w_nr = winkel.get(nr) if isinstance(winkel, dict) else winkel
                        woerter = _ocr_woerter_holen(ocr, pfad, nr, winkel=w_nr)
                    else:
                        bereiche = (bildbereiche or {}).get(nr) if bildbereiche is not None else None
                        if bereiche is None:
                            bereiche = sm.bildbereiche(seite)
                        woerter = []
                        for bereich in bereiche:
                            woerter += _ocr_woerter_holen(ocr, pfad, nr, clip=fitz.Rect(bereich))
            schwaerzungen = _schwaerzungsrechtecke(seite)
            if modus in ("seite", "bilder"):
                if woerter:
                    woerter = _ohne_platzhalter(woerter, _platzhalter_boxen(seite, nr, platzhalter) + schwaerzungen)
                if modus == "seite" and len(woerter or []) < SCAN_MIN_WOERTER:
                    # (fast) nichts gelesen – auch ganz ohne OCR (woerter None): Verdacht, außer die Seite ist
                    # nachweislich leer. Rauschen und Buchstabensalat bewerten erst ab viel mehr Wörtern.
                    if not _seite_nachweislich_leer(seite):
                        verdacht.append(Verdacht(nr, -1, -1, f"Seite {nr + 1}", GRUND_SEITE_UNGELESEN, []))
                elif modus == "seite" and len(woerter) >= SCAN_RAUSCHEN_MIN_WOERTER \
                        and _rauschanteil(woerter) > SCAN_RAUSCHEN_MAX:
                    verdacht.append(Verdacht(nr, -1, -1, f"Seite {nr + 1}", GRUND_SEITE_RAUSCHEN, []))
                elif modus == "seite" and _lesung_unplausibel(woerter):
                    verdacht.append(Verdacht(nr, -1, -1, f"Seite {nr + 1}", GRUND_SEITE_UNPLAUSIBEL, []))
            m = sm.seite_aufbauen(seite, nr, ocr_woerter=woerter, ocr_quelle=quelle)
            # Ausrichtung und Schräglage der OCR (10-Tupel) – dieselben, mit denen das Seitenmodell die Zeilen bildet
            ausrichtung = _ocr.ausrichtung_der_woerter(woerter) if any(len(x) >= 10 for x in woerter or ()) else None
            verdacht += _seite_pruefen(m, w, platzhalter or (), nie or (), abgewaehlt_je_seite.get(nr, ()), profil,
                                       felder_je_seite.get(nr, ()), schwaerzungen,
                                       scan_seite=seite if modus == "seite" else None, ausrichtung=ausrichtung)
    finally:
        doc.close()
    return verdacht
