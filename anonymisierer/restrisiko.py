"""Restrisiko-Prüfung: die zweite, unabhängige Verteidigungslinie (Vertrag Abschnitt 7).

Nach dem Schwärzen wird die AUSGABE noch einmal gelesen – Textebene, bei Scans und Bildbereichen die OCR (aus
dem Zwischenspeicher des OCR-Dienstes, mit derselben Ausrichtung wie die Selbstkontrolle; unveränderte Seiten
mit den OCR-Wörtern der Analyse, also ohne zweiten OCR-Lauf) – und nach allem durchsucht, was nach
personenbezogenen Daten aussieht. Was die Erkennung übersehen hat, darf das Haus nie still verlassen: jeder
Verdacht macht die Ausgabe zu _PRUEFEN, die Vorschau zeigt ihn orange, „Nachschwärzen“ übernimmt ihn.

Unabhängigkeit: Bewusst NICHT benutzt werden das Detektor-Register, namen.py, muster.py und das Sprachmodell –
eine zweite Verteidigungslinie darf nicht dieselben blinden Flecken haben wie die erste. Benutzt werden nur die
Listen der Wissensbasis (anonymisierer.wissen), das Seitenmodell (dieselbe Lesart der Seite) und eigene, einfache
Formregeln mit eigenen Prüfziffer-Rechnungen.

Was gemeldet wird (jede Regel liefert Stelle + Grund):
  * Kennungen: Ziffernfolgen ab 5 Ziffern – auch in Gruppen ("6 259 674 059", "0170 318 40 11") und mit
    Buchstaben ("KF007952512", "LV-2014-697971") –, außer Beträgen, Datumsangaben, Uhrzeiten, Paragrafen,
    Prozent- und Maßangaben, Verhältnissen ("300/150"), Handelsregister-, USt- und Gläubiger-Nummern,
    Service-Rufnummern (0800 …) und PLZ/Telefon/Straße in Firmenanschriften (Briefkopf, Fußzeile).
  * Formen mit Prüfziffer: IBAN, Steuer-ID, SV-Nummer, Krankenversichertennummer, FIN, Kreditkarte, Ausweis.
    Gemeldet wird die FORM; eine gültige Prüfziffer verstärkt nur den Grund (OCR-Verleser lassen Prüfziffern
    scheitern). Dazu Kfz-Kennzeichen- und BIC-Form und Werte hinter Kennungs-Etiketten ("Az. 123 C 45/24").
  * Kontakt: "@" (außer Funktionspostfächern wie info@ oder schaden@), "+Ländervorwahl", Namen in
    Internetadressen.
  * Datum mit plausiblem Geburtsjahr (Alter 14-110), außer hinter Vertragsdaten-Etiketten (Beginn, Ablauf,
    Datum …, auch als Tabellenspalte) und in Zeiträumen; hinter Geburtsdatum-Etiketten jedes vergangene Datum.
  * Namen: Vor- und Nachnamen der Wissensbasis (eindeutige immer, mehrdeutige mit Personenkontext), unbekannte
    Eigennamen in Personenkontext (Herr/Frau/Titel, Etiketten wie "Name:", "Vorstand:", direkt hinter einem
    Vornamen oder neben einem Personen-Platzhalter), Monats-/Wochentagsnamen direkt hinter einem Vornamen.
  * Anschriften: Straße + Hausnummer, Postfach, PLZ + Ort, Werte hinter Anschrift-Etiketten ("Ort: Jena").
  * Reste neben Anschrift-Platzhaltern ("Untere [ADRESSE]", "[PLZ ORT] i.d.OPf.") – auch auf Scans, wo
    Platzhalter (Textebene) und OCR-Wörter nur über die Lage auf der Seite benachbart sind – und Bruchstücke mit
    Ziffern, die ein graues Schwärzungsrechteck berühren ("-WXV09-07": Wert mitten im Wort abgeschnitten).
  * Ort-Datum-Zeilen ("Tübingen, 14. Januar 2025": meist der Wohnort der Unterzeichnenden).
  * Formularfelder des Originals (von der Schwärzung übergeben), deren Wert in der Ausgabe noch lesbar ist.
  * Scan-Seiten: dichte Tinte in Unterschriftsblöcken (unter der Grußformel – auch so, wie die OCR sie liest –,
    über/neben "Unterschrift") und neben Personenangaben (hinter "Name:", neben einem Personen-Platzhalter), die
    die OCR nicht VERLÄSSLICH gelesen hat: gar nicht, als Unterschriftszug (Wortkasten viel höher als die
    Schrift), als Buchstabensalat – oder als Wort, das ein Name sein kann (dort macht die Lesung die Tinte nicht
    harmlos: "DeLuca" unter "Mit freundlichen Grüßen", vom Unterschriftszug durchkreuzt). Bereiche in
    Leserichtung (OCR-Ausrichtung 0/90/180/270°, Schräglage); Tinte relativ zum Papier (auch blasse
    Kugelschreiber-Striche), Linien und Reste von Unter-/Durchstreichungen zählen nicht; Rechteck je Tintengruppe,
    "bitte ansehen".
Seitenverdacht (ohne Rechteck, „Seite selbst durchsehen“): eine Scan-Seite mit Tinte, aber ohne gelesene Wörter,
eine kaum lesbare Scan-Seite (mehr als 20 % OCR-Bruchstücke wie "|", "\\", ".", Einzelzeichen – Fax, starke
Kompression) und eine Scan-Seite, deren Lesung nach dem Maß der OCR unplausibel ist (Buchstabensalat einer
verdrehten Seite, Handschrift): dort kann die Prüfung nicht verlässlich lesen, also muss ein Mensch hinsehen.
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
from pathlib import Path
from typing import NamedTuple

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen kennen nur den Namen "fitz"
    import fitz

from . import ocr as _ocr
from . import seitenmodell as sm

OCR_DPI = sm.OCR_DPI
ALTER_MIN = 14                 # plausibles Geburtsjahr: Alter 14 bis 110 Jahre (ohne Geburts-Etikett)
ALTER_MAX = 110
MIN_ZIFFERN = 5                # Ziffernfolgen ab so vielen Ziffern sind ein Verdacht
SPALTE_ZEILEN = 40             # so weit sucht die Spaltenkopf-Regel nach oben (Zeilen)
SCAN_MIN_WOERTER = 3           # liefert die OCR einer Scan-Seite weniger Wörter: Seite gilt als ungelesen
SCAN_RAUSCHEN_MAX = 0.20       # mehr OCR-Bruchstücke ("|", "\\", "u", "0.") als dieser Anteil: Scan kaum lesbar
SCAN_RAUSCHEN_MIN_WOERTER = 40  # … erst ab so vielen OCR-Wörtern bewertet
FUELLFARBE = (0.92, 0.92, 0.92)  # Füllfarbe der Schwärzungsrechtecke (schwaerzung.FUELLFARBE)

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
_STOPPWOERTER = frozenset("""
der die das den dem des ein eine einen einem einer eines und oder aber doch sondern denn weil da dass daß wenn
als wie ob mit ohne für gegen um durch bis von vom zu zum zur bei beim nach aus auf an am in im über unter vor
hinter neben zwischen seit ab wegen trotz während ich du er sie es wir ihr ihre ihren ihrem ihres ihrer sein
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
                     "citroen", "citroën", "cupra", "mitsubishi", "subaru", "lexus", "landrover"})
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
_RECHTSFORM_RE = re.compile(
    r"(?<![\w])(?:AG|GmbH|mbH|SE|KG|KGaA|OHG|GbR|e\.\s?V\.|eG|e\.\s?G\.|VVaG|V\.V\.a\.G\.|a\.\s?G\.|AöR|KdöR|"
    r"Ltd\.?|S\.A\.|N\.V\.|B\.V\.|Inc\.|PartG(?:mbB)?|UG)(?![\w])")
_ORG_WORT_RE = re.compile(
    r"(?i)(?:versicherung|versicherungen|versicherer|assekuranz|bank|banken|sparkasse|volksbank|raiffeisenbank|"
    r"kasse|krankenkasse|bausparkasse|pensionskasse|rentenversicherung|berufsgenossenschaft|finanzamt|amtsgericht|"
    r"landgericht|gericht|behörde|bundesagentur|agentur für arbeit|polizei|polizeiinspektion|polizeipräsidium|"
    r"klinikum|universität|hochschule|verband|kammer|stadtwerke|holding|konzern|stiftung|versicherungsgruppe)"
    r"(?![a-zäöüß])")
# Etiketten, hinter denen eine Nummer zu einer Organisation gehört (kein Personenbezug)
_ORG_NUMMER_RE = re.compile(
    r"(?i)(?:HR\s?[AB]|Handelsregister|Registergericht|Register-?Nr\.?|Registernummer|Amtsgericht\s+[\w\-.]+|"
    r"USt\.?[\s-]?Id(?:\.?[\s-]?Nr)?\.?|USt-?IdNr\.?|Umsatzsteuer[\s-]?(?:Identifikations)?(?:nummer|ID)|VAT|"
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
_POSTFACH_RE = re.compile(r"(?i)(?<![\w])Postfach[ \t:]+(\d[\d ]{2,10}\d)")
_PLZ_ORT_RE = re.compile(r"(?<![\w\-/.,])(?:D[-\s])?(\d{5})[ \t]{1,2}([A-ZÄÖÜ][\wäöüßÄÖÜ.\-]+"
                         r"(?:[ \t](?:am|an|im|in|bei|ob|v\.|vor|der|d\.|a\.|i\.|"
                         r"[A-ZÄÖÜ(][\wäöüßÄÖÜ.\-)]*)){0,4})")

# Datumsformen (Tag, Monat, Jahr) und Bereiche
_DATUM_RES = (
    (re.compile(r"(?<![\d.,/])(\d{1,2})\.[ ]?(\d{1,2})\.[ ]?(\d{4}|\d{2})(?![\d]|\.\d)"), "tmj"),
    (re.compile(r"(?<![\d.,/-])(\d{4})-(\d{1,2})-(\d{1,2})(?![\d])"), "jmt"),
    (re.compile(r"(?<![\d.,/])(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})(?![\d/])"), "tmj"),
    (re.compile(r"(?<![\d.])(\d{1,2})\.?[ ]?(Jan(?:uar)?|Jänner|Feb(?:ruar)?|März|Mär|Maerz|Apr(?:il)?|Mai|"
                r"Juni?|Juli?|Aug(?:ust)?|Sept?(?:ember)?|Okt(?:ober)?|Nov(?:ember)?|Dez(?:ember)?)\.?[ ]?"
                r"(\d{4})(?![\d])", re.IGNORECASE), "tMj"),
)
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
# Kennungsartige Zeichenfolgen (Buchstaben/Ziffern mit inneren Trennern)
_TOKEN_RE = re.compile(r"[0-9A-Za-zÀ-ÖØ-öø-ɏ]+(?:(?:[./\-]|(?<=\d):(?=\d))[0-9A-Za-zÀ-ÖØ-öø-ɏ]+)*")
_LUECKE_KETTE = frozenset(" /-()")
_IBAN_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z]{2}[ ]?\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,4})?)"
                      r"(?![A-Za-z0-9])")
_IBAN_DE_LOSE_RE = re.compile(r"(?<![A-Za-z0-9])(DE[ ]?\d{2}(?:[ ]?\d){18})(?![0-9])")
_GLAEUBIGER_ID_RE = re.compile(r"[A-Z]{2}\d{2}\s?ZZZ")
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

    def index(self, art: str):
        """Phrasenindex: Etiketten einer Art ("person", "adresse" …), "rollen" oder "allowlist" (oder None)."""
        if art not in self._indizes:
            index = None
            if self.modul is not None:
                try:
                    if art == "rollen":
                        index = self.modul.Phrasenindex(_ROLLEN, name="rollen")
                    elif art == "allowlist":
                        index = self.modul.index("versicherer_und_organisationen")
                    else:
                        index = self.modul.index(f"etiketten_{art}")
                except Exception:
                    index = None
            self._indizes[art] = index
        return self._indizes[art]

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
                 schwaerzungen=()):
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
        """Zeilen über z (nächste zuerst), nach der Lage auf der Seite."""
        if z is None or z.rect is None:
            return []
        oben = [y for y in self.m.zeilen if y.rect is not None and y.rect.y1 <= z.rect.y0 + 1 and y.id != z.id]
        oben.sort(key=lambda y: -y.rect.y1)
        return oben[:anzahl]

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
        """Steht die Stelle in einer Firmenanschrift (Briefkopf, Fußzeile: Rechtsform, Versicherung, Bank …
        oder ein Eintrag der Allowlist in derselben Zeile oder bis zu drei Zeilen davor/danach im selben Block)?"""
        z = self.zeile(pos)
        if z is None:
            return False
        ergebnis = self._org.get(z.id)
        if ergebnis is None:
            ergebnis = self._org_zeile(z) or any(self._org_zeile(y) for y in self._block_nachbarn(z, 2))
            self._org[z.id] = ergebnis
        if ergebnis and self._etikett_vor(z, pos):
            return False                              # "Anschrift: 27568 Bremerhaven" (Formularwert)
        return ergebnis

    def _etikett_vor(self, z, pos: int) -> bool:
        """Steht vor pos in derselben Zeile ein Anschrift-/Personen-/Kontakt-Etikett mit Doppelpunkt?"""
        vor = self.text[z.start:pos]
        for treffer in re.finditer(r"([^\W\d_][\w./\- ]{1,40}?)\s?:", vor):
            if self._etikett_in(treffer.group(1).split("\t")[-1], ("adresse", "person", "kontakt")):
                return True
        return False

    def _block_nachbarn(self, z, anzahl: int) -> list:
        zeilen = [y for y in self.m.zeilen if y.block == z.block]
        try:
            i = next(k for k, y in enumerate(zeilen) if y.id == z.id)
        except StopIteration:
            return []
        return zeilen[max(0, i - anzahl):i]

    def _org_zeile(self, z) -> bool:
        schluessel = ("zeile", z.id)
        if schluessel in self._org:
            return self._org[schluessel]
        t = _URL_RE.sub(" ", _EMAIL_RE.sub(" ", self.zeilen_text(z)))
        ergebnis = bool(_RECHTSFORM_RE.search(t) or _ORG_WORT_RE.search(t))
        if not ergebnis:
            index = self.w.index("allowlist")
            try:
                ergebnis = index is not None and any(len(v.text) >= 4 and v.text[:1].isupper()
                                                     for v in index.finde(t))
            except Exception:
                ergebnis = False
        self._org[schluessel] = ergebnis
        return ergebnis

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
            maske = self._maske(zeile)
            self._kennungen(z, zeile, maske)
            self._formen(z, zeile, maske)
            self._daten(z, zeile)
            self._kontakt(z, zeile)
            self._anschriften(z, zeile)
        self._namen()
        self._reste_neben_platzhaltern()
        self._ort_datum()
        return self.kandidaten

    def _ort_datum(self):
        """Ort-Datum-Zeile ("Tübingen, 14. Januar 2025", "St. Ingbert, 11.08.2025"): der Ort ist meist der
        Wohnort der Unterzeichnenden."""
        datum = r"(?:den\s+)?\d{1,2}\.\s?(?:\d{1,2}\.\s?\d{2,4}|[A-ZÄÖÜa-zäöü]+\.?\s\d{4})"
        muster = re.compile(r"(?:^|(?<=\t))[ ]*((?:[A-ZÄÖÜ][\wäöüßÄÖÜ.\-]*|St\.)"
                            r"(?:[ ](?:am|an|im|in|bei|ob|der|"
                            r"v\.|d\.|i\.|[A-ZÄÖÜ(][\wäöüßÄÖÜ.\-)]*)){0,4}),[ ]?" + datum)
        for z in self.m.zeilen:
            zeile = self.zeilen_text(z)
            if "," not in zeile:
                continue
            for m in muster.finditer(zeile):
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
    def _maske(self, zeile: str) -> list:
        maske = [False] * len(zeile)
        for regex in (_BETRAG_RE, _UHRZEIT_RE, _PARAGRAF_RE, _PROZENT_RE, _JAHRESBEREICH_RE):
            for m in regex.finditer(zeile):
                for i in range(m.start(), m.end()):
                    maske[i] = True
        for regex, art in _DATUM_RES:
            for m in regex.finditer(zeile):
                if self._datum(m, art) is not None:
                    for i in range(m.start(), m.end()):
                        maske[i] = True
        return maske

    def _kennungen(self, z, zeile: str, maske: list):
        """Ziffernfolgen ab MIN_ZIFFERN Ziffern (Gruppen über Leerzeichen, / und - verbunden)."""
        tokens = [(m.start(), m.end()) for m in _TOKEN_RE.finditer(zeile)
                  if not any(maske[m.start():m.end()]) and _ziffern(m.group(0))]
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
                            and not any(maske[tokens[j][1]:ns])):
                        j += 1
                    else:
                        break
            anfang = s
            while anfang > 0 and zeile[anfang - 1] in "+(" and not maske[anfang - 1]:
                anfang -= 1                          # "+49" / "(0" davor gehört dazu
            self._kennung_bewerten(z, zeile, anfang, tokens[j][1])
            i = j + 1

    def _kennung_bewerten(self, z, zeile: str, s: int, e: int):
        stueck = zeile[s:e]
        ziffern = _ziffern(stueck)
        if ziffern < MIN_ZIFFERN:
            return
        g_s, g_e = z.start + s, z.start + e
        davor = zeile[max(0, s - 40):s]
        if _ORG_NUMMER_RE.search(davor) or _GLAEUBIGER_ID_RE.match(stueck):
            return                                   # Handelsregister, USt-IdNr., BLZ, Gläubiger-ID, Formular
        if _EINHEIT_RE.match(zeile[e:e + 14]) or _WAEHRUNG_VOR_RE.search(davor):
            return
        if re.fullmatch(r"\d{1,3}/\d{1,3}", stueck):
            return                                   # Verhältnis/Tarifstufe "300/150"
        kompakt = re.sub(r"[\s()/\-.]", "", stueck)
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
        if kompakt.isdigit() and len(kompakt) == 11 and steuer_id_gueltig(kompakt):
            self.neu(g_s, g_e, "Steuer-ID (Prüfziffer gültig)", "form")
        elif kompakt.isdigit() and 13 <= len(kompakt) <= 19 and luhn_gueltig(kompakt):
            self.neu(g_s, g_e, "Kreditkartennummer (Prüfziffer gültig)", "form")
        else:
            self.neu(g_s, g_e, "Ziffernfolge (mögliche Kunden-, Vertrags- oder Kennnummer)", "kennung")

    def _formen(self, z, zeile: str, maske: list):
        """Formen mit Prüfziffer, Kfz-Kennzeichen, BIC, Ausweis-/ID-artige Werte, Werte hinter Kennungs-Etiketten."""
        o = z.start
        for m in _IBAN_RE.finditer(zeile):
            if _GLAEUBIGER_ID_RE.match(m.group(1)):
                continue                             # Gläubiger-Identifikationsnummer eines Unternehmens
            if m.group(1)[:2] == "DE" or iban_gueltig(m.group(1)) or _ziffern(m.group(1)) >= 10:
                grund = "IBAN (Prüfziffer gültig)" if iban_gueltig(m.group(1)) else "IBAN-Form"
                self.neu(o + m.start(1), o + m.end(1), grund, "form")
        for m in _IBAN_DE_LOSE_RE.finditer(zeile):
            self.neu(o + m.start(1), o + m.end(1), "IBAN-Form", "form")
        for m in _SVNR_RE.finditer(zeile):
            grund = ("Sozialversicherungsnummer (Prüfziffer gültig)" if sv_nummer_gueltig(m.group(1))
                     else "Sozialversicherungsnummer-Form")
            self.neu(o + m.start(1), o + m.end(1), grund, "form")
        for m in _KVNR_RE.finditer(zeile):
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
                continue
            self.neu(o + m.start(), o + m.end(), "Kfz-Kennzeichen-Form", "form")
        for m in _BIC_RE.finditer(zeile):
            davor = zeile[max(0, m.start() - 40):m.start()]
            if re.search(r"(?i)(BIC|SWIFT)[\s.:]*$", davor) or re.search(r"\b[A-Z]{2}\d{2}[\s\dA-Z]{8,}\s*$", davor):
                if not self.org_kontext(o + m.start(1)):
                    self.neu(o + m.start(1), o + m.end(1), "BIC hinter IBAN/Etikett", "form")
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
            if mit_etikett or id_artig:
                if icao_gueltig(wert):
                    grund = "Ausweisnummer (Prüfziffer gültig)"
                elif mit_etikett:
                    grund = "Ausweis-/Dokumentnummer hinter Etikett"
                else:
                    grund = "kennungsartige Zeichenfolge (Ausweis-/Dokumentnummer?)"
                self.neu(o + m.start(1), o + m.end(1), grund, "form")
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
            if (_ziffern(w) < mindest or len(w) < 3 or _ORG_NUMMER_RE.search(zeile[:v.ende])
                    or re.fullmatch(r"[\d\s.,]+[€%]?", w) or any(maske[s:s + len(w)]) or _GLAEUBIGER_ID_RE.match(w)
                    or self.ist_platzhalter_bei(o + s, o + s + len(w))):
                continue
            self.neu(o + s, o + s + len(w), f"Wert hinter Etikett »{v.text}«", "etikett")

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
        alle = []
        for regex, art in _DATUM_RES:
            for m in regex.finditer(zeile):
                datum = self._datum(m, art)
                if datum is not None:
                    alle.append((m.start(), m.end(), datum))
        alle.sort()
        for k, (ms, me, datum) in enumerate(alle):
            if datum > heute:
                continue
            alter = heute.year - datum.year - ((heute.month, heute.day) < (datum.month, datum.day))
            s, e = z.start + ms, z.start + me
            etikett = None
            if re.match(r"\s?\(?(?:geboren|geb\.|Geburtsdatum|Geburtstag)", zeile[me:me + 16], re.IGNORECASE):
                etikett = ("datum_geburt", "geboren")
            if etikett is None:
                etikett = self.etikett_davor(s, e, ("datum_geburt", "vertragsdaten"))
            if etikett is None:
                etikett = self.spaltenkopf(s, e, ("datum_geburt", "vertragsdaten"), streng=False)
            if etikett is not None and etikett[0] == "datum_geburt":
                if alter <= 120:
                    self.neu(s, e, f"Datum hinter Etikett »{etikett[1]}«", "datum")
                continue
            if etikett is not None or not (ALTER_MIN <= alter <= ALTER_MAX):
                continue
            # Zeitraum: "01.09.1985 – 31.08.1988", "von … bis …", zwei Daten nebeneinander in einer Tabellenzeile
            if _BEREICH_DANACH_RE.match(zeile[me:me + 8]) or _BEREICH_DAVOR_RE.search(zeile[max(0, ms - 10):ms]):
                continue
            nachbarn = [x for x in (alle[k - 1] if k else None, alle[k + 1] if k + 1 < len(alle) else None) if x]
            if any(not zeile[min(me, x[1]):max(ms, x[0])].strip(" \t-–—/|[]\\") for x in nachbarn):
                continue
            self.neu(s, e, "Datum mit möglichem Geburtsjahr", "datum")

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
            if "@" in zeile[max(0, m.start() - 1):m.start()]:
                continue
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
            vn, nn, vnm, nnm, aw, tit, allow, _ = self.w.art(erstes)
            if aw or tit or allow or erstes.lower() in _STOPPWOERTER or self.w.ist_etikett(erstes) \
                    or self.org_kontext(o + s):
                continue
            self.neu(o + s, o + s + len(text), f"Angabe hinter Etikett »{v.text}«", "anschrift")

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
            woerter.append((m.start(), m.end(), m.group(0), k))
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
            Medizin") und nicht in einer Kopfzeile aus lauter Etiketten?"""
            s = woerter[i][0]
            z = self.zeile(s)
            if z is None:
                return False
            ende = etikett_zeilen.get(z.id)
            if ende is None:
                ende = -1
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
                            ende = max(ende, z.start + v.ende)
                etikett_zeilen[z.id] = ende
            if not (0 <= ende <= s):
                return False
            zwischen = text[ende:s]
            if "(" in zwischen and ")" not in zwischen[zwischen.rfind("("):]:
                return False                            # in Klammern: "(Vorsitzender)"
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
            for t in teile:
                vn, nn, vnm, nnm, aw, tit, allow, part = self.w.art(t)
                if ((vn and not vnm) or (nn and not nnm)) and not aw and not allow and len(t) >= 3:
                    return True
            return False

        def firma_danach(i) -> bool:
            rest = text[woerter[i][1]:woerter[i][1] + 30]
            return bool(re.match(r"[\s,&+\w.\-]{0,20}?(?<![\w])(?:GmbH|AG|KG|OHG|GbR|SE|mbH|e\.\s?V\.|UG|Partner|"
                                 r"Partnerschaft|& Co)(?![\w])", rest)) \
                or "&" in text[max(0, woerter[i][0] - 3):woerter[i][0]]

        for i, (s, e, w, k) in enumerate(woerter):
            if not gross(i) or not namenswort(i) or w.lower() in _STOPPWOERTER:
                continue
            if self.ist_gesperrt(s, e) or self.ist_platzhalter_bei(s, e) or _platzhalter_bruchstueck(w):
                continue
            vn, nn, vnm, nnm, aw, tit, allow, part = arten[i]
            if tit or part:
                continue
            if _ORG_ENDWORT.search(w) or self._strassenwort(i, woerter):
                continue
            platzhalter = self.neben_platzhalter(s, e, _PERSONEN_PLATZHALTER_RE) is not None
            titel = titel_davor(i)
            etikett = etikett_kontext(i)
            links_vorname = direkt(i, i - 1) and vorname_stark(i - 1)
            rechts_nachname = direkt(i, i + 1) and nachname_stark(i + 1) and vn
            komma_paar = ((direkt(i, i + 1, komma=True) and "," in luecke(i, i + 1) and vorname_stark(i + 1) and nn)
                          or (direkt(i, i - 1, komma=True) and "," in luecke(i, i - 1)
                              and nachname_stark(i - 1) and vn))
            kontext = titel or platzhalter or etikett or links_vorname or rechts_nachname or komma_paar
            if vorname_stark(i) or nachname_stark(i) or doppelname(i):
                stark_kontext = titel or platzhalter or links_vorname
                if (allow or firma_danach(i) or w.lower() in _MARKEN) and not stark_kontext:
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
            if titel or (platzhalter and len(w) <= 14) or (etikett and not ocr_wort):
                self.neu(s, e, "unbekannter Eigenname im Personenkontext", "name")

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
            if not kern or self.ist_gesperrt(s, e) or _platzhalter_bruchstueck(roh):
                continue
            s += roh.find(kern)
            e = s + len(kern)
            if sum(c.isalnum() for c in kern) >= 3 and _ziffern(kern) \
                    and self._quelle(s) == "text" and self.an_schwaerzung(s, e):
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
            if ocr_wort and not (vn or nn) and (len(wort) < 4 or wort.isupper() or self._kompositum(wort)):
                continue                                # OCR-Bruchstück ("Dau", "MIRD", "Unfallherg")
            self.neu(s, e, "Rest neben Platzhalter", "rest")

    def lesung_harmlos(self, s: int, e: int, lese_hoehe: float, uebliche_hoehe: float, fliesstext=False) -> bool:
        """Macht die OCR-Lesung eines Worts (Textstelle s:e) seine Tinte unverdächtig? Für Unterschriftsblöcke und
        Personenangaben auf Scans: Nein, wenn der Wortkasten viel höher ist als die übliche Schrift (ein
        Unterschriftszug, als "Wort" gelesen), wenn die Lesung Bruchstück oder Buchstabensalat ist oder wenn das
        Wort ein Name sein kann (großgeschriebener Name der Wissensbasis, auch mehrdeutig; unbekanntes
        großgeschriebenes Wort) – an dieser Stelle steht eine Person. Ja für Platzhalter, NIE-Liste, abgewählte
        Stellen, Wörter mit Ziffern (die prüfen die Textregeln), kleingeschriebene Wörter, Fließtext und
        Grußformel (fliesstext=True: die Textregeln prüfen ihn mit Namenslisten und Kontext), Firmenzeilen,
        häufige Wörter, Titel, Partikel, Etiketten, Hauptwörter; zusammengesetzte Wörter ("Kundenservice-Team"),
        wenn jeder Teil harmlos ist."""
        if self.ist_gesperrt(s, e):
            return True
        kern = self.text[s:e].strip("()[]{},;:.!?\"'„“”‚‘’«»|/\\-–")
        if sum(c.isalnum() for c in kern) < 2:
            return False
        teile = [t for t in re.split(r"[-/]", kern) if t]
        if lese_hoehe > WORT_HOEHE_MAX * uebliche_hoehe:
            # viel höher als die Schrift: ein als "Wort" gelesener Unterschriftszug ("Dee") – es sei denn, die Lesung
            # ist ein bekanntes Wort (Fax mit halber senkrechter Auflösung: hohe Wortkästen um gewöhnliche Wörter)
            return bool(teile) and all(t.isalpha() and self._bekanntes_wort(t) for t in teile)
        if any(c.isdigit() for c in kern):
            return True
        z = self.zeile(s)
        if z is not None and self._org_zeile(z):
            return True                                 # Firmenzeile ("Donau Leben AG", "… VVaG")
        if _ocr_unsinn(kern) or not kern[:1].isalpha():
            return False
        buchstaben = [c.lower() for c in kern if c.isalpha()]
        if len(buchstaben) >= 3 and not any(c in "aeiouyäöüéèáàóíú" for c in buchstaben):
            return False                                # Buchstabensalat ("Dzrk")
        if kern[:1].islower() or fliesstext:
            return True
        return bool(teile) and all(self._wort_harmlos(t) for t in teile)

    def _bekanntes_wort(self, wort: str) -> bool:
        """Wort der festen Listen – Funktions- und Kalenderwort, Anrede, Titel, akademischer Grad, häufiges Wort,
        Partikel, Allowlist, Etikett – und kein Name der Wissensbasis."""
        klein = wort.lower().rstrip(".")
        if (klein in _STOPPWOERTER or klein in _KALENDERWOERTER or klein in _ANREDEN or klein in _ANREDE_ZUSATZ
                or klein in _AKADEMISCH or klein in _TITEL_KURZ):
            return True
        vn, nn, vnm, nnm, aw, tit, allow, part = self.w.art(wort)
        if (vn or nn) and not tit:
            return False                                # Name der Wissensbasis – hier steht eine Person
        return bool(tit or part or aw or allow or self.w.ist_etikett(wort))

    def _wort_harmlos(self, wort: str) -> bool:
        """Einzelwort ohne Ziffern: kein möglicher Name (siehe lesung_harmlos)? Bekanntes Wort, sonst – wenn es kein
        Name der Wissensbasis ist – kleingeschrieben, Hauptwort-Endung oder zusammengesetztes Hauptwort."""
        if self._bekanntes_wort(wort):
            return True
        vn, nn = self.w.art(wort)[:2]
        if vn or nn:
            return False
        return bool(wort[:1].islower() or _NOMEN_ENDUNG.search(wort) or self._kompositum(wort))

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
        anzeige = re.sub(r"\s+", " ", str(name)).strip(" :")[:40] or "ohne Namen"
        pruefung.neu(s, e, f"Formularfeld »{anzeige}« nicht geschwärzt", "feld")


def _seite_pruefen(m, wissen: _Wissen, platzhalter=(), nie=(), abgewaehlt=(), profil="hoch", felder=(),
                   schwaerzungen=(), scan_seite=None) -> list:
    """Alle Regeln einer Seite. scan_seite: die PDF-Seite einer Scan-Seite (OCR der ganzen Seite) – dann zusätzlich
    die Tinte in Unterschriftsblöcken und neben Personenangaben (_unterschrift_pruefen; deren Verdacht steht vorn)."""
    pruefung = _Seitenpruefung(m, wissen, platzhalter, nie, abgewaehlt, profil, schwaerzungen)
    pruefung.pruefen()
    _felder_pruefen(pruefung, felder)
    aus = [Verdacht(m.nr, s, e, m.text[s:e], grund, _rechtecke(m, s, e)) for s, e, grund in _zusammenfassen(pruefung)]
    if scan_seite is not None:
        aus = _unterschrift_pruefen(scan_seite, m, schwaerzungen, pruefung, aus) + aus
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
    """OCR-Wörter so angefordert wie von der Selbstkontrolle (gleicher Schlüssel -> Treffer im Zwischenspeicher)."""
    if ocr is None:
        return []
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
UNTERSCHRIFT_ZEILEN = 6        # so viele Zeilenhöhen unter der Grußformel gehören zum Unterschriftsblock
UNTERSCHRIFT_BREITE = 300      # … ab 15 pt links der Grußformel so breit (pt, in Leserichtung)
TINTE_DPI = 72                 # Auflösung der Tintenprüfung (1 Pixel = 1 pt)
TINTE_DUNKEL = 110             # Grauwert, unter dem ein Pixel sicher Tinte ist (Kern eines Strichs) – gezählt wird …
TINTE_ABSTAND_PAPIER = 60      # … jedes Pixel, das um so viel dunkler ist als das Papier (Median der Seite), höchstens
TINTE_DUNKEL_MAX = 180         #     bis zu diesem Grauwert (graue Schwärzungsrechtecke 235 nie): dünne, blasse Striche
                               #     (Kugelschreiber) zählen so mit; eine Zelle braucht aber auch ein Kernpixel – der
                               #     helle Rand erklärter Wörter jenseits ihres OCR-Kastens zählt nicht
LINIE_DICKE = 4                # Rest einer geraden Linie (Unter-/Durchstreichung zwischen erklärten Wörtern): höchstens
LINIE_STEIGUNG = 0.09          # so viele Pixel stark und höchstens ~5° geneigt
TINTE_ZELLE = 6                # Zellen (Pixel) für die Tintendichte
TINTE_MIN_PIXEL = 5            # nicht erklärte Tintenpixel, ab denen eine Zelle zählt
TINTE_MIN_ZELLEN = 4           # so viele zusammenhängende Zellen sind ein Verdacht (Punkte, Striche nicht)
LINIE_MIN_PIXEL = 40           # dunkle Läufe ab dieser Länge (waagerecht/senkrecht) sind Linien, keine Schrift
WORT_HOEHE_MAX = 1.8           # OCR-Wortkasten höher als 1,8 x die übliche Worthöhe: Unterschriftszug, keine Schrift
                               # (außer die Lesung ist ein bekanntes Wort – Fax: hohe Kästen um gewöhnliche Wörter)


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


def _linienrest(pixel) -> bool:
    """Ist eine Tintengruppe der Rest einer geraden Linie – eine Unter- oder Durchstreichung, deren Stücke zwischen
    erklärten Wörtern stehen bleiben? Dünn (je Spalte bzw. Zeile höchstens LINIE_DICKE Pixel) und gerade (höchstens
    ~5° geneigt). Schrift hat dickere Stellen (Grundstriche), ein Unterschriftszug schwingt auf und ab."""
    xs = [x for x, _ in pixel]
    ys = [y for _, y in pixel]
    breite, hoehe = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
    for lang, kurz, quer in ((breite, hoehe, xs), (hoehe, breite, ys)):
        if lang >= 2 * TINTE_ZELLE and kurz <= LINIE_DICKE + LINIE_STEIGUNG * lang:
            dicke: dict = {}
            for k in quer:
                dicke[k] = dicke.get(k, 0) + 1
            if max(dicke.values()) <= LINIE_DICKE:
                return True
    return False


class _Seitenbild:
    """Graubild einer Seite bei TINTE_DPI – einmal je Seite gerendert, die Bereiche werden daraus geschnitten."""

    def __init__(self, seite):
        self.rect = fitz.Rect(seite.rect)
        try:
            pix = seite.get_pixmap(dpi=TINTE_DPI, colorspace=fitz.csGRAY, alpha=False)
            self.breite, self.hoehe, self.daten = pix.width, pix.height, pix.samples
        except Exception:
            self.breite, self.hoehe, self.daten = 0, 0, b""
        self.sx = self.breite / self.rect.width if self.rect.width else 0.0
        self.sy = self.hoehe / self.rect.height if self.rect.height else 0.0
        probe = sorted(self.daten[::7]) if self.daten else [255]
        papier = probe[len(probe) // 2]
        self.dunkel = max(TINTE_DUNKEL, min(TINTE_DUNKEL_MAX, papier - TINTE_ABSTAND_PAPIER))
        self._linie = None

    def ausschnitt(self, bereich):
        """(Pixel, Linienmaske, Breite, Höhe, Bereich in Seitenkoordinaten genau auf Pixelgrenzen) oder None. Die
        Linien werden auf der ganzen Seite gesucht (einmal je Seite): eine Tabellenlinie, die einen kleinen Bereich nur
        kurz quert, ist dort als Linie erkannt."""
        if not self.breite or not self.hoehe:
            return None
        x0 = max(0, int((bereich.x0 - self.rect.x0) * self.sx))
        y0 = max(0, int((bereich.y0 - self.rect.y0) * self.sy))
        x1 = min(self.breite, int((bereich.x1 - self.rect.x0) * self.sx + 0.999))
        y1 = min(self.hoehe, int((bereich.y1 - self.rect.y0) * self.sy + 0.999))
        if x1 - x0 < TINTE_ZELLE or y1 - y0 < TINTE_ZELLE:
            return None
        if self._linie is None:
            self._linie = _linienpixel(self.daten, self.breite, self.hoehe, self.dunkel)
        zeilen = range(y0, y1)
        daten = b"".join(self.daten[y * self.breite + x0:y * self.breite + x1] for y in zeilen)
        linie = bytearray(b"".join(self._linie[y * self.breite + x0:y * self.breite + x1] for y in zeilen))
        genau = fitz.Rect(self.rect.x0 + x0 / self.sx, self.rect.y0 + y0 / self.sy,
                          self.rect.x0 + x1 / self.sx, self.rect.y0 + y1 / self.sy)
        return daten, linie, x1 - x0, y1 - y0, genau


def _tintengruppen(bild: _Seitenbild, bereich, erklaert) -> list:
    """Dichte, nicht erklärte Tinte im Bereich (Seitenkoordinaten): Rechteck je zusammenhängender Gruppe von
    Tintenzellen (Zellen mit höchstens einer leeren Zelle dazwischen gehören zusammen); Gruppen unter
    TINTE_MIN_ZELLEN Zellen (Punkte, Staub, ein einzelnes Komma) und Reste gerader Linien (_linienrest) zählen
    nicht. Tinte: dunkler als bild.dunkel (relativ zum Papier, auch blasse Striche)."""
    teil = bild.ausschnitt(fitz.Rect(bereich) & bild.rect)
    if teil is None:
        return []
    daten, maske, breite, hoehe, bereich = teil          # maske: Linien der Seite, dazu unten das Erklärte
    sx, sy = bild.sx, bild.sy
    dunkel = bild.dunkel
    for r in erklaert:
        r = fitz.Rect(r) + (-1.5, -1.5, 1.5, 1.5)
        if not r.intersects(bereich):
            continue
        x0, x1 = max(0, int((r.x0 - bereich.x0) * sx)), min(breite, int((r.x1 - bereich.x0) * sx) + 1)
        y0, y1 = max(0, int((r.y0 - bereich.y0) * sy)), min(hoehe, int((r.y1 - bereich.y0) * sy) + 1)
        if x1 > x0:
            voll = b"\x01" * (x1 - x0)
            for y in range(y0, y1):
                maske[y * breite + x0:y * breite + x1] = voll
    zellen: dict = {}
    kern: set = set()
    for y in range(hoehe):
        for x in range(breite):
            i = y * breite + x
            if daten[i] < dunkel and not maske[i]:
                k = (x // TINTE_ZELLE, y // TINTE_ZELLE)
                zellen.setdefault(k, []).append((x, y))
                if daten[i] < TINTE_DUNKEL:
                    kern.add(k)
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


def _unterschrift_pruefen(seite, m, schwaerzungen, pruefung=None, gemeldet=()) -> list:
    """Scan-Seite: dichte Tinte in Unterschriftsblöcken und neben Personenangaben, die die OCR nicht VERLÄSSLICH
    gelesen hat – die Texterkennung kann dort nichts prüfen, also selbst ansehen.

    Bereiche (in Lesekoordinaten – Ausrichtung und Schräglage aus den OCR-Wörtern wie im Seitenmodell –, also auch
    auf gedrehten und schrägen Scans richtig): unter jeder Grußformel (UNTERSCHRIFT_ZEILEN Zeilenhöhen,
    UNTERSCHRIFT_BREITE breit), über und rechts neben "Unterschrift", rechts hinter einem Personen-Etikett mit
    Doppelpunkt ("Name:", "Kontoinhaber:") und links/rechts neben einem Personen-Platzhalter.
    Erklärt ist Tinte unter Schwärzungsrechtecken, der Textebene (Platzhalter), schon gemeldeten Verdachtsstellen
    (`gemeldet`) und unter OCR-Wörtern, deren Lesung sie unverdächtig macht (_Seitenpruefung.lesung_harmlos).
    Rückgabe: je Bereich mit Tinte ein Verdacht (start -1) mit einem Rechteck je Tintengruppe."""
    stellen = _wortstellen(m)
    if not stellen:
        return []
    if pruefung is None:
        pruefung = _Seitenpruefung(m, _Wissen(_wissen_laden()), schwaerzungen=schwaerzungen)
    text = m.text
    woerter = [(b.x0, b.y0, b.x1, b.y1, text[s:e]) for s, e, b in stellen]
    winkel, schraeg = _ocr.ausrichtung_der_woerter(woerter)
    lese = [_lesekasten(b, winkel, schraeg) for _, _, b in stellen]
    hoehen = sorted(r.height for r, (s, e, _) in zip(lese, stellen) if sum(c.isalnum() for c in text[s:e]) >= 2)
    if not hoehen:
        return []
    ueblich = max(hoehen[len(hoehen) // 2], 4.0)
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
    gruss = {zid for zid, (z, _) in zeilen.items() if ist_grussformel(text[z.start:z.ende])}

    def gleiche_hoehe(a, b) -> bool:
        return min(a.y1, b.y1) - max(a.y0, b.y0) >= 0.5 * min(a.height, b.height)

    # Fließtext je sichtbarer Zeile: das Seitenmodell trennt eine Zeile an großen Lücken (Platzhalter, Spalten) –
    # "Oberfranken, Aktenzeichen" | [VERTRAGS-NR] | "nahm den Unfall auf." ist EINE Fließtextzeile
    fliesstext = set()
    for zid, (z, r) in zeilen.items():
        reihe = " ".join(text[y.start:y.ende] for y, ry in zeilen.values() if gleiche_hoehe(r, ry))
        if _ist_fliesstext(reihe):
            fliesstext.add(zid)
    bereiche = []
    index = pruefung.w.index("person")
    for zid, (z, r) in sorted(zeilen.items(), key=lambda t: t[1][0].start):
        h = max(min(r.height, 1.3 * ueblich), 8.0)
        inhalt = text[z.start:z.ende]
        if zid in gruss:
            bereiche.append((fitz.Rect(r.x0 - 15, r.y1 + 1, r.x0 + UNTERSCHRIFT_BREITE,
                                       r.y1 + 1 + UNTERSCHRIFT_ZEILEN * h), GRUND_UNTERSCHRIFT))
            continue
        if _UNTERSCHRIFT_ETIKETT_RE.search(inhalt) and len(inhalt.split()) <= 8 and zid not in fliesstext:
            bereiche.append((fitz.Rect(r.x0 - 30, r.y0 - 2.5 * h, r.x1 + 150, r.y0 - 0.5), GRUND_UNTERSCHRIFTSFELD))
            bereiche.append((fitz.Rect(r.x1 + 1, r.y0 - 0.3 * h, r.x1 + 250, r.y1 + 0.3 * h), GRUND_UNTERSCHRIFTSFELD))
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
    for s, e, rand in pruefung.platzhalter_boxen():
        if not _PERSONEN_PLATZHALTER_RE.match(text[s:e]):
            continue
        r = _lesekasten(fitz.Rect(rand), winkel, schraeg)
        b = pruefung.box(s, e)                            # Zeile des Platzhaltertexts (das graue Rechteck kann
        t = _lesekasten(fitz.Rect(b), winkel, schraeg) if b is not None else r   # mehrere Zeilen hoch sein)
        h = max(min(t.height, 1.3 * ueblich), 8.0)
        mitte = (t.y0 + t.y1) / 2
        bereiche.append((fitz.Rect(r.x0 - 2.5 * h, mitte - 0.7 * h, r.x0 - 1, mitte + 0.7 * h), GRUND_PERSONENTINTE))
        bereiche.append((fitz.Rect(r.x1 + 1, mitte - 0.7 * h, r.x1 + 2.5 * h, mitte + 0.7 * h), GRUND_PERSONENTINTE))
    if not bereiche:
        return []
    erklaert = [fitz.Rect(r) for r in schwaerzungen]
    erklaert += [fitz.Rect(r) for v in gemeldet or () for r in (v.rechtecke or [])]
    erklaert += [z.rect for g, z in enumerate(m.zeichen) if m.wort_ids[g] < 0]          # Textebene: Platzhalter
    for (s, e, b), r in zip(stellen, lese):
        z = m.zeile_von(s)
        zid = z.id if z is not None else None
        if pruefung.lesung_harmlos(s, e, r.height, ueblich, fliesstext=zid in gruss or zid in fliesstext):
            erklaert.append(b)
    verdacht, bekannt, gesehen = [], [], set()
    bild = _Seitenbild(seite)
    for bereich, grund in bereiche:
        schluessel = tuple(round(x) for x in bereich)
        if schluessel in gesehen:
            continue
        gesehen.add(schluessel)
        gruppen = _tintengruppen(bild, _aus_lesekasten(bereich, winkel, schraeg), erklaert)
        neu = [g for g in gruppen if not any(abs(g & b) > 0.5 * abs(g) for b in bekannt)]
        if neu:
            bekannt += neu
            text_v = "Unterschriftsbereich" if grund != GRUND_PERSONENTINTE else "Personenangabe"
            verdacht.append(Verdacht(m.nr, -1, -1, text_v, grund, neu))
    return verdacht


def _tintenanteil(seite) -> float:
    """Anteil dunkler Pixel der Seite (grob gerendert) – eine leere Scan-Seite ohne Text ist kein Verdacht."""
    try:
        pix = seite.get_pixmap(dpi=50, colorspace=fitz.csGRAY, alpha=False)
    except Exception:
        return 1.0
    daten = pix.samples
    return sum(1 for b in daten if b < 180) / max(1, len(daten))


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
                if modus == "seite" and len(woerter or []) < SCAN_MIN_WOERTER and _tintenanteil(seite) > 0.0003:
                    verdacht.append(Verdacht(nr, -1, -1, f"Seite {nr + 1}", GRUND_SEITE_UNGELESEN, []))
                elif modus == "seite" and len(woerter) >= SCAN_RAUSCHEN_MIN_WOERTER \
                        and _rauschanteil(woerter) > SCAN_RAUSCHEN_MAX:
                    verdacht.append(Verdacht(nr, -1, -1, f"Seite {nr + 1}", GRUND_SEITE_RAUSCHEN, []))
                elif modus == "seite" and _lesung_unplausibel(woerter):
                    verdacht.append(Verdacht(nr, -1, -1, f"Seite {nr + 1}", GRUND_SEITE_UNPLAUSIBEL, []))
            m = sm.seite_aufbauen(seite, nr, ocr_woerter=woerter, ocr_quelle=quelle)
            verdacht += _seite_pruefen(m, w, platzhalter or (), nie or (), abgewaehlt_je_seite.get(nr, ()), profil,
                                       felder_je_seite.get(nr, ()), schwaerzungen,
                                       scan_seite=seite if modus == "seite" else None)
    finally:
        doc.close()
    return verdacht
