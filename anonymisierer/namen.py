"""KI-Namenserkennung (spaCy) plus Regeln für Briefe, Formulare und Tabellen,
Plausibilitätsfilter gegen Fehlalarme und Stopplisten.

Öffentliche Namen: lade_ner, finde_personen_ner (Menge von Namenstexten, wie bisher),
finde_personen (Kandidaten mit Position und Zusammengehörigkeit), personen_teilen (mehrere Personen ohne
Komma an Vornamen trennen – "Jörg Ziegler Ursula Frank"), verlesenes_etikett_statt_name (von der OCR
verlesener Feldbezeichner statt Name – nur für OCR-Text), geburtsnamen (Geburtsname hinter "geb."/"geborene"/
"Geburtsname", mit der Person davor verbunden), geburtsname_teilen, NAMEN_STOPPLISTE, ner_fehler.

Die Filter dieses Moduls kennen die Herkunft der Zeichen nicht und gelten deshalb für jeden Text gleich; eine
Toleranz für OCR-Lesefehler gehört nicht hierher (detektoren/ocr_lesart.py prüft die Quelle).
"""

import functools
import re

from . import kennungsformen, personenkontext

_NLP = None          # das geladene Sprachmodell (oder None)
_NLP_FEHLER = None   # Begründung, falls nicht verfügbar
_STUECK_LAENGE = 60_000   # Zeichen je spaCy-Aufruf (Stücke enden an Zeilenumbrüchen)


def lade_ner():
    """Lädt das deutsche spaCy-Modell für die Namenserkennung (einmalig).
    Der Parser bleibt aktiv: ohne Satzgrenzen verliert die NER Namen."""
    global _NLP, _NLP_FEHLER
    if _NLP is not None or _NLP_FEHLER is not None:
        return _NLP
    try:
        import spacy
        for modell in ("de_core_news_md", "de_core_news_sm"):
            try:
                _NLP = spacy.load(modell, disable=["lemmatizer", "tagger"])
                _NLP.max_length = max(_NLP.max_length, 2_000_000)
                return _NLP
            except OSError:
                continue
        _NLP_FEHLER = ("Deutsches Sprachmodell fehlt "
                       "(Installieren.bat erneut ausführen).")
    except ImportError:
        _NLP_FEHLER = "Paket 'spacy' fehlt (Installieren.bat erneut ausführen)."
    return None


def ner_fehler():
    """Begründung, falls die Namenserkennung nicht verfügbar ist (sonst None)."""
    return _NLP_FEHLER


# ----------------------------------------------------------------------
# Wortlisten
# ----------------------------------------------------------------------
# Wörter, die die Namenserkennung gern fälschlich als Person meldet (klein geschrieben)
NAMEN_STOPPLISTE = {
    "gmbh", "co", "kg", "ag", "mbh", "versicherung", "lebensversicherung",
    "herr", "frau", "herrn", "sehr", "geehrte", "geehrter", "grüßen",
    "freundlichen", "mit", "und",
    # Kopfzeilen von E-Mails und Grußformeln
    "gesendet", "weitergeleitet", "antwort", "grüße", "gruß", "herzliche", "herzlichen", "freundliche",
    "beste", "besten", "liebe", "lieben", "viele", "vielen",
    # Feldbezeichner / Rollen
    "steuer", "steuer-id", "steuerid", "kindergeld", "kindergeld-nr", "zulage", "zulagen",
    "zulagennummer", "zulagenummer", "person", "personen", "sohn", "tochter", "kind", "kinder",
    "angebot", "kunde", "kundin", "kunden", "versicherte", "versicherter", "versicherten",
    "versicherungsnehmer", "versicherungsnehmerin", "bezugsberechtigter", "bezugsberechtigte",
    "vermittler", "vermittlerin", "bearbeiter", "bearbeiterin", "sachbearbeiter", "sachbearbeiterin",
    "vorstand", "kundenbetreuung", "leistungsabteilung", "schadenregulierung", "schadenabteilung",
    "abteilung", "vermerk", "interner", "interne", "intern", "betreff", "anlage", "anlagen", "seite",
    "datum", "ort", "unterschrift", "stempel", "zeuge", "zeugin", "fahrer", "fahrerin", "halter",
    "halterin", "unfallgegner", "unfallgegnerin", "ehefrau", "ehemann", "ehepartner", "ehepartnerin",
    "partner", "partnerin", "familie", "eheleute", "antragsteller", "antragstellerin", "patient",
    "patientin", "kontoinhaber", "kontoinhaberin", "vollmachtgeber", "bevollmächtigter",
    "geschädigter", "geschädigte", "mitversichert", "mitversicherte", "name", "vorname", "nachname",
    "geburtsname", "geburtsdatum", "geschlecht", "beruf", "staatsangehörigkeit", "familienstand",
    "geb", "geborene", "geborener", "geborenen",
    "anschrift", "adresse", "telefon", "mobil", "fax", "e-mail", "email", "iban", "bic", "blz",
    "konto", "kontonummer", "kennzeichen", "fahrzeug", "typ", "marke", "modell", "tel", "tel.",
    "telefax", "handy", "mitbehandler", "behandler", "hausarzt", "hausärztin", "ansprechpartner",
    "ansprechpartnerin", "kontakt", "empfänger", "empfängerin", "absender", "absenderin", "betreuer",
    "betreuerin", "vormund", "auftraggeber", "auftraggeberin", "mieter", "mieterin", "vermieter",
    "vermieterin", "käufer", "käuferin", "verkäufer", "verkäuferin", "erbe", "erbin", "schuldner",
    "schuldnerin", "zahlungspflichtiger", "beitragszahler", "berater", "beraterin", "makler", "maklerin",
    "lebensgefährtin", "lebensgefährte", "datenschutzbeauftragte", "datenschutzbeauftragter",
    "verantwortlicher", "verantwortliche", "arzt", "ärztin", "fachärztin", "facharzt", "nachbar",
    "nachbarin", "mandant", "mandantin", "kollege", "kollegin", "mitarbeiter", "mitarbeiterin",
    "geschäftsführer", "geschäftsführerin", "inhaber", "inhaberin", "leiter", "leiterin", "anwalt",
    "anwältin", "rechtsanwalt", "rechtsanwältin", "notar", "notarin", "steuerberater", "steuerberaterin",
    "zahlungsempfänger", "versicherer", "gesellschaft", "unternehmen", "firma", "betrieb", "arbeitgeber",
    "arbeitnehmer", "angestellter", "angestellte", "rentner", "rentnerin", "student", "studentin",
    "schüler", "schülerin", "kunden-nr", "vertrags-nr", "schein-nr", "vs-nr", "versicherungsnummer",
    # Funktionswörter (großgeschrieben am Satzanfang oder als Anrede-Pronomen)
    "ihr", "ihre", "ihren", "ihrem", "ihrer", "ihres", "sie", "wir", "er", "es", "der", "die", "das",
    "den", "dem", "des", "ein", "eine", "einen", "einem", "einer", "dieser", "diese", "dieses", "oder",
    "aber", "auch", "dank", "hochachtungsvoll", "hiermit", "bezüglich", "wegen", "für", "von", "vom",
    "am", "im", "zum", "zur", "nach", "bei", "über", "unter", "wie", "als", "wenn", "dass", "nicht",
    "kein", "keine", "alle", "jeder", "jede", "jedes", "unser", "unsere", "unseren", "mein", "meine",
    "sein", "seine", "seinen", "dessen", "deren", "welche", "welcher", "hallo", "guten", "liebe", "lieber",
    "sehr geehrte", "sehr geehrter",
    # Produkte / Sparten / Alltagswörter
    "basisrente", "riester-rente", "riesterrente", "privatrente", "rürup-rente", "rüruprente",
    "kapitallebensversicherung", "krankenversicherung", "rentenversicherung", "haftpflicht",
    "privathaftpflicht", "hausrat", "hausratversicherung", "vollkasko", "teilkasko", "berufsunfähigkeit",
    "berufsunfähigkeitsversicherung", "dynamik", "komfortdynamik", "tarif", "beitrag", "rente",
    "leistung", "leistungen", "deckung", "police", "vertrag", "antrag", "schaden", "rechnung",
    "mahnung", "kündigung", "widerruf", "vollmacht", "gutachten", "gutachter", "werkstatt", "praxis",
    "klinikum", "krankenhaus", "finanzamt", "amtsgericht", "landgericht", "gericht", "sparkasse",
    "volksbank", "bank", "straße", "strasse", "str", "weg", "platz", "allee", "gasse", "ring",
    "hauptstraße", "postfach", "deutsche", "deutschland", "bund", "nordbayern", "süd", "nord", "ost",
    "west", "mitte", "januar", "februar", "märz", "april", "mai", "juni", "juli", "august",
    "september", "oktober", "november", "dezember", "montag", "dienstag", "mittwoch", "donnerstag",
    "freitag", "samstag", "sonntag", "uhr", "euro", "eur", "prozent", "jahr", "jahre", "monat",
    "ergebnis", "prüfung", "hinweis", "wichtig", "bitte", "danke", "anbei", "zahlung", "überweisung",
    "lastschrift", "mandat", "sepa", "mandatsreferenz", "gläubiger", "stand", "beginn", "ablauf",
    "ende", "laufzeit", "summe", "kapital", "garantie", "überschuss", "überschussbeteiligung",
    "rentenfaktor", "eigenbeitrag", "zusatzbaustein", "todesfall", "leistungsfall", "schadenfall",
    "hinterbliebene", "bezugsrecht", "beitragsbefreiung", "selbstbeteiligung", "schadenfreiheitsklasse",
    "rückstufung", "kostenvoranschlag", "restwert", "regelaltersrente", "rentenanwartschaft",
    # Fehlalarme des Entwicklungs-Benchmarks (Feldbezeichner, Überschriften, Fußzeilen)
    "vorsitz", "vorsitzender", "vorsitzende", "aufsichtsrat", "aufsichtsratsvorsitzender", "brutto", "netto",
    "sparte", "kollegen", "kollegin", "kollege", "gedruckt", "raucher", "nichtraucher", "behandelnder",
    "behandelnde", "bezugsberechtigt", "stadtauswärts", "stadteinwärts", "zeitart", "schadentag", "schadenort",
    # mehrsprachige Feldnamen auf Ausweisen und Pässen (ICAO 9303: Landessprache + Englisch/Französisch)
    "surname", "given", "names", "given names", "nom", "prénoms", "prenoms", "prénom", "prenom", "nationality",
    "nationalité", "nationalite", "sex", "sexe", "authority", "autorité", "autorite", "birth", "naissance",
    "date of birth", "place of birth", "date of issue", "date of expiry", "issue", "expiry", "passport",
    "passeport", "identity", "carte", "identité", "identite", "d'identité", "d'identite", "card", "ausweisart",
    "reisepass", "personalausweis", "führerschein", "kode", "code", "typ/type", "licence", "permis", "date",
}

# Adjektive, die Straßennamen einleiten (Lange Straße) — als Einzelwort kein Name,
# außer hinter Herr/Frau (Herr Große, Frau Lange)
_STRASSEN_ADJEKTIVE = {"lange", "alte", "neue", "kurze", "große", "grosse", "kleine", "obere", "untere",
                       "hohe", "breite", "hintere", "vordere", "mittlere", "innere", "äußere", "schöne",
                       "interner", "interne", "weitere", "folgende", "sonstige", "allgemeine"}

# Versicherer- und Produktnamen, die als Person gemeldet werden (klein geschrieben)
VERSICHERER_NAMEN = {
    "allianz", "ergo", "huk", "huk-coburg", "huk24", "debeka", "dkv", "signal iduna", "signal-iduna",
    "gothaer", "generali", "continentale", "nürnberger", "württembergische", "hallesche", "barmenia",
    "swiss life", "canada life", "standard life", "die bayerische", "bayerische", "hdi", "axa", "r+v",
    "hanse merkur", "hansemerkur", "alte leipziger", "volkswohl bund", "lv 1871", "lv1871", "condor",
    "zurich", "stuttgarter", "basler", "baloise", "dialog", "ideal", "universa", "inter", "wwk",
    "helvetia", "münchener verein", "interrisk", "hannoversche", "lvm", "provinzial", "vhv", "devk",
    "arag", "cosmos", "cosmosdirekt", "europa", "targo", "versicherungskammer", "mecklenburgische",
    "concordia", "itzehoer", "ostangler", "vgh", "öffentliche", "badische", "landeskrankenhilfe", "lkh",
    "deutsche rentenversicherung", "drv", "bafin", "gdv", "riester", "rürup", "janitos", "kravag",
    "würzburger", "bavaria", "bayern-versicherung", "sv sparkassenversicherung", "deutsche familienversicherung",
    "dfv", "getsafe", "ottonova", "mylife", "neodigital", "wefox", "clark", "check24", "verivox", "friday",
    "nexible", "admiral direkt", "da direkt", "deutscher herold", "central", "deutscher ring", "securvita",
    "bkk", "aok", "tk", "techniker", "barmer", "dak", "ikk", "knappschaft", "pkv", "gkv", "haftpflichtkasse",
    "die haftpflichtkasse", "allianz lebensversicherungs-ag", "allianz versicherungs-ag",
    "nürnberger lebensversicherung", "ergo vorsorge", "generali deutschland", "gothaer allgemeine",
    "swiss life select", "canada life assurance europe", "alte leipziger lebensversicherung",
    "hannoversche lebensversicherung", "dialog lebensversicherung", "volkswohl bund lebensversicherung",
    "wwk lebensversicherung", "deutsche bank", "commerzbank", "postbank", "ing", "ing-diba", "dkb",
    "comdirect", "consorsbank", "n26", "sparda", "psd", "fondsdepot bank", "ebase", "fil", "dws", "union investment",
    "deka", "vwl", "rente", "pflege", "privat", "komfort", "basis", "plus", "premium", "klassik", "invest",
}
_VERSICHERER_EINZELWORT = {v for v in VERSICHERER_NAMEN if " " not in v}

# Firmenbestandteile: steht so ein Wort im Kandidaten, ist es eine Organisation
_FIRMENWOERTER = {"gmbh", "ag", "kg", "mbh", "e.v.", "ev", "se", "co", "co.", "inc", "inc.", "ltd", "ltd.",
                  "ohg", "gbr", "ug", "eg", "a.g.", "plc", "sa", "nv", "bv", "versicherung", "versicherungen",
                  "lebensversicherung", "krankenversicherung", "versicherungs-ag", "lebensversicherungs-ag",
                  "versicherungsverein", "krankenversicherungsverein", "bank", "sparkasse", "gruppe",
                  "group", "holding", "verein", "kasse", "krankenkasse", "makler", "versicherungsmakler",
                  "finanz", "finanzdienstleistungen", "consulting", "allgemeine", "assurance", "life",
                  "select", "direkt", "versicherungs", "lebensversicherungs"}

# Anreden und Titel (werden vorn abgestreift, zählen nicht als Namensbestandteil)
ANREDEN = {"herr", "herrn", "frau", "fräulein", "fam", "fam.", "familie", "eheleute", "ehepaar", "firma",
           "fa.", "hr.", "fr.", "z.hd.", "z.h.", "c/o", "an", "sehr", "geehrte", "geehrter", "liebe", "lieber"}
TITEL = {"dr", "dr.", "prof", "prof.", "med", "med.", "dipl", "dipl.", "dipl.-ing", "dipl.-ing.", "dipl.-kfm",
         "dipl.-kfm.", "dipl.-kffr.", "dipl.-jur", "dipl.-jur.", "dipl.-psych.", "dipl.-betriebsw.", "rer",
         "rer.", "nat", "nat.", "jur", "jur.", "phil", "phil.", "pol.", "oec.", "h.c.", "mag", "mag.", "ing",
         "ing.", "b.a.", "m.a.", "m.sc.", "b.sc.", "mba", "ll.m.", "rechtsanwalt", "rechtsanwältin", "ra",
         "stb", "wp", "pfarrer", "pastor", "dent", "dent.", "vet", "vet.", "habil", "habil.", "univ.",
         "i.", "a.", "v.", "i.a.", "i.v.", "gez.", "ppa.", "p.p.", "jun.", "sen.", "junior", "senior"}
# Namenspartikel (klein geschrieben): gehören zum Nachnamen, sind aber kein eigener Bestandteil
PARTIKEL = {"von", "van", "de", "der", "den", "dem", "des", "zu", "zur", "zum", "da", "di", "del", "della",
            "dos", "das", "du", "la", "le", "el", "al", "bin", "ibn", "ten", "ter", "und", "y", "of", "auf",
            "vom", "vor", "unter", "ober", "nieder", "sankt", "st."}

# Großgeschriebene Wörter, die einen Namen beenden (Regel-Treffer werden dort abgeschnitten)
_NAMENSENDE = {"tel", "tel.", "telefon", "telefax", "fax", "mobil", "handy", "kennzeichen", "geb", "geb.",
               "geboren", "geburtsdatum", "iban", "bic", "konto", "kontonummer", "str", "str.", "straße",
               "strasse", "weg", "platz", "allee", "gasse", "postfach", "versicherungsnummer",
               "versicherungsschein", "versicherungsschein-nr.", "vertragsnummer", "kundennummer",
               "schadennummer", "steuer-id", "e-mail", "email", "mail", "web", "www", "tochter", "sohn",
               "kind", "ehefrau", "ehemann", "vn", "versicherungsnehmer", "versicherungsmakler", "makler",
               "wohnhaft", "geschäftsführer", "inhaber", "vorstand", "leiter", "leiterin"}
# Straßenwort am Wortende – "str" auch ohne Punkt ("Habsburgerstr": die OCR verliert den Punkt gern)
_STRASSENSUFFIX_RE = re.compile(r"(?i:straße|strasse|str\.?|weg|allee|platz|gasse|ring|damm|ufer|markt|chaussee)$")
_KFZ_RE = re.compile(r"^[A-ZÄÖÜ]{1,3}-[A-Z]{1,2}$")
_BIC_FORM_RE = re.compile(r"^[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?$")
_ORT_DATUM_RE = re.compile(r",[ \t]*(?:den[ \t]+|im[ \t]+|am[ \t]+)?\d{1,2}\.[ \t]?(?:\d{1,2}\.|[A-ZÄÖÜ][a-zä]+)[ \t]?\d{2,4}")
_VORHER_ANREDE_RE = re.compile(r"(?:Herrn?|Frau|Hr\.|Fr\.|Fräulein|Familie|Fam\.|Eheleute)[ \t]*$")
_ABKUERZUNGEN_GROSS = {"IBAN", "BIC", "SEPA", "GMBH", "EUR", "USD", "CHF", "PDF", "AGB", "AVB", "AKB", "BLZ",
                       "PLZ", "KFZ", "PKW", "LKW", "MWST", "UST", "BGB", "VVG", "SGB", "DIN", "ISO", "HUK",
                       "DKV", "HDI", "AXA", "WWK", "LVM", "ERGO", "VHV", "DEVK", "ARAG", "ADAC", "DRV", "GDV",
                       "BAFIN", "LEI", "UID", "VIN", "FIN", "HSN", "TSN", "SF", "USA", "EU"}

# Großbuchstaben aller lateinischen Schriften (Ågren, Çelik, Łukasz, Šimić, Ørsted …)
_GROSS = "A-ZÄÖÜÀ-ÖØ-ÞĀĂĄĆČĎĐĒĖĘĚĞĢĪĮİĶĹĻĽŁŃŅŇŌŐŒŔŘŚŞŠŢŤŪŮŰŲŹŻŽȘȚ"

# Komposita-Endungen von Sachwörtern (Schadenanzeige, Familientarif, Praxisanschrift, Hundehalter …);
# gilt nur für Wörter, die mindestens 3 Zeichen länger sind als die Endung (Halter/Partner/Zeit bleiben Namen)
_SACHWORT_ENDUNGEN = (
    "nummer", "schein", "bescheid", "anzeige", "meldung", "tarif", "verlust", "anschrift", "pflicht", "fähig",
    "frei", "heit", "keit", "schaft", "protokoll", "auskunft", "rechnung", "abrechnung", "vermerk", "abteilung",
    "schutz", "summe", "beitrag", "datum", "bereich", "stelle", "dauer", "antrag", "vertrag", "police",
    "versicherung", "erklärung", "bestätigung", "mitteilung", "übersicht", "angaben", "angabe", "daten", "halter",
    "nehmer", "geber", "steller", "zahler", "empfänger", "partner", "person", "personen", "kosten", "gebühr",
    "leistung", "leistungen", "zahlung", "zeit", "zeitraum", "beginn", "ablauf", "betrag", "quote", "klasse",
    "stufe", "option", "optionen", "baustein", "bausteine", "paket", "variante", "tätigkeit", "beruf",
    "unterlagen", "nachweis", "formular", "fragebogen", "hinweise", "bedingungen", "grundlage", "verfahren",
    "apotheke", "praxis", "klinik", "tag", "ort", "termin", "wert", "werte", "fall", "berechtigt",
    "pflichtig", "stand", "gebiet", "amt",
    "straße", "strasse", "str", "weg", "platz", "allee", "gasse",      # Straßennamen ohne Hausnummer (Hauptstr)
    # Domänen-Durchsicht Runde 5: Berichte, Konten, Bögen, Reise, Geräte ("Durchgangsarztbericht", "Zweitkonto",
    # "Bruttoarbeitslohn", "Kundenbogen", "Doppelzimmer", "Rückflug", "Meerblick", "Gasgrill", "Krankenzusatz")
    "bericht", "konto", "lohn", "bogen", "zimmer", "flug", "blick", "plakette", "schilderung", "jahr", "grill",
    "zusatz", "grafie", "graphie", "vermietung", "anzeige",
)
# Adjektiv-/Partizipstämme, die großgeschrieben vor Rollenwörtern stehen ("Betreuender Vermittler",
# "Mitversichertes Kind", "Fälliger Beitrag", "Erstattungsfähig")
_SACHWORT_STAEMME = {
    "fällig", "betreuend", "zuständig", "versichert", "mitversichert", "erstattungsfähig", "beitragsfrei", "gültig",
    "folgend", "weiter", "sonstig", "allgemein", "besonder", "jährlich", "monatlich", "einmalig", "laufend",
    "bisherig", "gesamt", "voraussichtlich", "garantiert", "möglich", "zusätzlich", "abweichend", "ehemalig",
    "derzeitig", "aktuell", "vorläufig", "endgültig", "verstorben", "geschieden", "verheiratet", "ledig",
    "verwitwet", "selbstständig", "selbständig", "angestellt", "berufstätig", "arbeitslos", "erwerbstätig",
    "pflegebedürftig", "beitragspflichtig", "leistungspflichtig", "steuerpflichtig", "nachstehend", "vorstehend",
    "obig", "unterzeichnend", "unterzeichnet", "betroffen", "geschädigt", "beteiligt", "berechtigt", "verpflichtet",
    "beauftragt", "bevollmächtigt", "behandelnd", "begutachtend", "vertretend", "ausstellend", "einreichend",
    "antragstellend", "leistend", "zahlend", "haftend", "mitwirkend", "erforderlich", "notwendig", "wichtig",
    # Feldbezeichner ohne passende Endung
    "optionen", "zahlweise", "dokumentart", "vorversicherer", "versicherer", "erwerbsminderung", "zahlungsart",
}
# Etiketten, hinter denen kein Personenname steht (Beruf: Polier, Tarif: Komfort, Marke: Opel …)
_SACHETIKETT_RE = re.compile(
    r"(?<![\wäöüß])(?:Beruf|Tätigkeit|Berufsbezeichnung|Tarif|Tarifname|Produkt|Produktname|Sparte|Marke|Typ|"
    r"Modell|Hersteller|Fahrzeug|Diagnose|Verwendungszweck|Leistungsart|Optionen|Bausteine?|Deckung|Zahlweise|"
    r"Vertragsart|Versicherungsart|Dokumentart|Status)(?:[ \t]*/[ \t]*[\wäöüß]+)?[ \t]*:[ \t]*$")
_SACHETIKETT_WERT_RE = re.compile(
    r"(?<![\wäöüß])(?:Beruf|Tätigkeit|Berufsbezeichnung|Tarif|Tarifname|Produkt|Produktname|Sparte|Marke|Typ|"
    r"Modell|Hersteller|Fahrzeug|Diagnose|Verwendungszweck|Leistungsart|Zahlweise|Vertragsart|Versicherungsart|"
    r"Dokumentart|Status)(?:[ \t]*/[ \t]*[\wäöüß]+)?[ \t]*:[ \t]*([A-ZÄÖÜ][\wäöüß\-]{1,40})")


# hinter einem Einzelwort: es ist Teil eines Firmennamens ("Taunus Krankenversicherung AG", "Harz Leben")
_FIRMA_DANACH_RE = re.compile(
    r"[ \t]+(?:[A-ZÄÖÜ][a-zäöüß]*(?:versicherung(?:en)?|versicherungs-?ag|kasse|bank|gruppe)|Versicherung(?:en)?|"
    r"Rechtsschutz|Versicherer|Bank|Sparkasse|Assekuranz|Leben|Allgemeine|Gruppe|Holding|AG|SE|GmbH|KG|VVaG|"
    r"a\.[ \t]?G\.|e\.[ \t]?V\.)(?![\wäöüß])")


def _sachwerte(text: str) -> set:
    """Einzelwörter, die im Text als Wert hinter einem Sach-Etikett stehen ("Beruf: Polier",
    "Tarif: Komfort") — sie sind auch an anderer Stelle (Formularfeld ohne Etikett) kein Name."""
    return {m.group(1).casefold() for m in _SACHETIKETT_WERT_RE.finditer(text)}


@functools.lru_cache(maxsize=32768)
def _wissen_art(wort: str) -> tuple:
    """(bekannter Name?, Allerweltswort?, Diagnose/Beruf?, Etikett?) aus der Wissensbasis (ohne Wissensbasis: alles
    False). Etikett: das Wort ist selbst ein Feldbezeichner einer Etikett-Liste ("Hauptfahrer", "Sozius",
    "Stammversicherter") – ein Etikett ist nie ein Name."""
    try:
        from . import wissen
    except Exception:  # pragma: no cover
        return False, False, False, False
    w = wort.strip(".,;:()[]\"'")
    if not w:
        return False, False, False, False
    try:
        name = wissen.ist_vorname(w) or wissen.ist_nachname(w)
        allerwelt = len(w) >= 4 and wissen.ist_allerweltswort(w)
        sache = bool(wissen.index("diagnosen").eintrag_fuer(w) or wissen.index("berufe").eintrag_fuer(w))
        etikett = len(w) >= 4 and any(wissen.index(f"etiketten_{art}").eintrag_fuer(w) is not None
                                      for art in wissen.ETIKETTEN_ARTEN)
    except Exception:  # pragma: no cover - Wissensbasis beschädigt
        return False, False, False, False
    return name, allerwelt, sache, etikett


def _ist_sachwort(wort: str) -> bool:
    """Großgeschriebenes Nicht-Namenswort: Stopplisten-Eintrag (auch gebeugt: Mitversichertes, Kunden),
    Allerweltswort der Wissensbasis, Etikett der Wissensbasis (Hauptfahrer, Sozius), Kompositum mit Sachwort-Endung
    (Schadenanzeige, Hundehalter), Adjektiv/Partizip (Betreuender, Gedruckt) oder gängige Abkürzung (Kfz, Pkw). Bei
    Bindestrich-Wörtern genügt ein Sachwort-Teil (Kraftfahrt-Haftpflicht, Kfz-Versicherungsschein). Bekannte
    Vor-/Nachnamen sind nie Sachwörter."""
    w = wort.lower().strip(".,;:()[]\"'")
    name, allerwelt, sache, etikett = _wissen_art(wort)
    if name and "-" not in w:
        return False
    if allerwelt or ((sache or etikett) and not name):
        return True
    for teil in (t for t in w.split("-") if t):
        if teil in NAMEN_STOPPLISTE or teil in _NAMENSENDE or teil in _FIRMENWOERTER or teil in _SACHWORT_STAEMME:
            return True
        if teil.upper() in _ABKUERZUNGEN_GROSS:
            return True                       # "Kfz", "Pkw", "AVB": Abkürzungen, keine Namen
        for n in (1, 2):                      # Beugung abstreifen: Mitversichertes -> mitversicherte
            stamm = teil[:-n]
            if len(stamm) >= 4 and (stamm in NAMEN_STOPPLISTE or stamm in _SACHWORT_STAEMME):
                return True
        if any(teil.endswith(e) and len(teil) >= len(e) + 3 for e in _SACHWORT_ENDUNGEN):
            return True
        if _wissen_art(teil)[1]:
            return True
    # Kein Abgleich mit verlesenen Etiketten: _ist_sachwort gilt für jeden Text, auch für die Textebene eines PDFs,
    # und ein unbekannter Nachname ("Ehmann", "Wohnert") liegt oft nur einen Buchstaben neben einem Feldbezeichner
    # ("Ehemann", "Wohnort"). Verlesene Etiketten prüft verlesenes_etikett_statt_name – nur für OCR-Text.
    return False


# Partizip II ("Ausgefertigt", "Beglaubigt", "Festgesetzt", "Gezeichnet", "Legitimiert") und Adjektiv auf -isch
# ("Gegnerischer", "Medizinische"): keine Namen
_PARTIZIP_RE = re.compile(r"(?:[A-ZÄÖÜ][a-zäöü]{1,6}ge|Ge)[a-zäöüß]{3,}t|(?:Be|Ver|Ent|Er|Zer)[a-zäöüß]{3,}igt|"
                          r"[A-ZÄÖÜ][a-zäöüß]{3,}iert")
_ISCH_RE = re.compile(r"[A-ZÄÖÜ][a-zäöüß]{4,}isch(?:e|er|es|en|em)")
# medizinische Wendungen: "Morbus …" und Adjektive vor Diagnosen ("Chronische Lumbalgie"); "M." nur vor einer
# Diagnose ("M. Parkinson", nicht "M. Weber"), Endungen von Fachwörtern in personenkontext.fachwort_medizin
_MEDIZIN_ANFANG = frozenset({"morbus", "chronisch", "chronische", "chronischer", "chronisches", "akut", "akute",
                             "akuter", "akutes", "rezidivierend", "rezidivierende", "rezidivierender", "distal",
                             "distale",
                             "distaler", "proximal", "proximale", "proximaler", "arteriell", "arterielle", "essentiell",
                             "essentielle", "essenzielle", "beidseitig", "beidseitige", "degenerativ", "degenerative",
                             "posttraumatisch", "posttraumatische", "idiopathisch", "idiopathische", "obstruktive",
                             "obstruktiver", "diabetische", "allergische", "allergisches"})
# Organisationswörter in einer Firmenbezeichnung ("Europcar Autovermietung", "Stadtwerke Rosenheim", "Spedition
# Wimmer", "Rosenheimer Verkehrsbetriebe", "Buchbinder Rent-a-Car") – Namen darin findet R4 (wissen.namen)
_ORG_TEIL_RE = re.compile(r"(?i)(?:vermietung|spedition|stadtwerke|verkehrsbetriebe|betriebe|automobile?|leasing|"
                          r"rent-a-car|autohaus|logistik|transporte|kanzlei|rechtsanwälte|partnerschaft)$")
# Rechtsform direkt dahinter in derselben Zelle (auch hinter mehreren Wörtern): "Sixt GmbH & Co Autovermietung KG" –
# nicht in der nächsten Tabellenzelle ("Kranzbühler ./. Felsberger ⇥⇥ AG München": das Amtsgericht)
_RECHTSFORM_DANACH_RE = re.compile(r"[ ,]*(?:GmbH|gGmbH|mbH|AG|SE|KG|KGaA|OHG|UG|e\.[ \t]?V\.|eG|VVaG|Ltd\.?|Inc\.?|"
                                   r"&[ \t]*Co\.?)(?![\wäöüß])")
_DATEI_DANACH_RE = re.compile(r"(?i)\.(?:pdf|docx?|xlsx?|pptx?|jpe?g|png|tiff?|txt|msg|eml|zip|odt)(?![\w])")
_DATEI_ENDE_RE = re.compile(r"(?i)\.(?:pdf|docx?|xlsx?|pptx?|jpe?g|png|tiff?|txt|msg|eml|zip|odt)$")
_GRUSS_DANACH_RE = re.compile(r"[ \t]+(?i:regards|wishes|greetings)(?![\w])")


def _wissen_modul():
    """Die Wissensbasis (Modul anonymisierer.wissen) oder None, wenn sie fehlt."""
    try:
        from . import wissen
        return wissen
    except Exception:  # pragma: no cover - Wissensbasis fehlt
        return None


def _sachname_stellen(zeile: str) -> list:
    """(start, ende) der Eigennamen von Sachen und Tieren (Wissensbasis "sachnamen") in einer Zeile – je Zelle
    (personenkontext.sachnamen_stellen, wie die Selbstkontrolle)."""
    return personenkontext.sachnamen_stellen(zeile, _wissen_modul())


def _personen_paar(teile: list) -> bool:
    """Vorname + Nachname der Wissensbasis (beide eindeutig) – ein Personenbeleg."""
    if len(teile) < 2:
        return False
    return (_wissen_wort("ist_vorname", teile[0]) and not _wissen_wort("ist_vorname_mehrdeutig", teile[0])
            and _wissen_wort("ist_nachname", teile[-1]) and not _wissen_wort("ist_mehrdeutig", teile[-1]))


def _code_wort(wort: str) -> bool:
    """Modell- oder Typkürzel in Versalien ("TPV", "MCV", "GSR", "DDLE"), kein Name und keine Wortgestalt."""
    if not re.fullmatch(r"[A-Z]{2,5}", wort) or _wissen_art(wort.title())[0]:
        return False
    return not _wissen_wort("ist_wortgestalt", wort)


_TITEL_DAVOR_RE = re.compile(r"(?<![^\W\d_])(?:Dr|Prof|Dipl\.-\w+)[.,][ \t]*"
                             r"(?:(?:med|rer|nat|jur|phil|dent|vet|oec|habil)[.,][ \t]*){0,3}$")


def _ner_sachtreffer(text: str, start: int, ende: int, teile: list) -> bool:
    """Ist ein reiner Treffer der KI (ohne Anrede) eine Sache statt einer Person: eine Marke, ein Modell oder eine
    Tierrasse der Wissensbasis ("Kalkhoff", "Jack Russell" in "Jack Russell Terrier", "Junghans Max Bill"), ein
    Modellcode im oder hinter dem Treffer ("Böckmann TPV", "Tabbert Rossini 540"), eine Firma (Rechtsform dahinter,
    Organisationswort darin), eine medizinische Wendung ("Morbus Scheuermann", "Chronische Lumbalgie"), ein Partizip
    oder Adjektiv ("Ausgefertigt", "Gegnerischer"), ein Dateiname ("Bescheid.pdf") oder eine englische Grußformel?
    Ein Personenbeleg aus Vor- und Nachnamen der Wissensbasis bleibt ein Name, außer eine Sache umfasst ihn ganz und
    reicht über ihn hinaus ("Jack Russell Terrier")."""
    # ein akademischer Titel direkt davor ist ein Personenbeleg – auch verlesen ("Dr, med. Neina-Josat Haustier" für
    # "Dr. med. Heinz-Josef Häußler"): dann zählen Marken, Rassen und Modellcodes nicht
    paar = _personen_paar(teile) or bool(_TITEL_DAVOR_RE.search(text, max(0, start - 24), start))
    zeilenanfang = text.rfind("\n", 0, start) + 1
    zeilenende = text.find("\n", ende)
    zeilenende = len(text) if zeilenende < 0 else zeilenende
    zeile = text[zeilenanfang:zeilenende]
    s, e = start - zeilenanfang, ende - zeilenanfang
    for a, b in _sachname_stellen(zeile):
        if a <= s and e <= b and (not paar or b - a > e - s):
            return True                                   # ganz in einer Marke, einem Modell, einer Rasse
        if a < e and s < b and not paar:
            rest = [t for t in teile if not (a <= zeile.find(t, s) < b)]
            if all(not _wissen_art(t)[0] or _code_wort(t) for t in rest):
                return True                               # "Mofa Simson", "AEG DDLE"
    if len(teile) >= 2 and any(_code_wort(t) for t in teile[1:]) and not paar:
        return True                                       # "Böckmann TPV", "Logan MCV", "Bosch GSR"
    # Modellcode dahinter in derselben Zelle (personenkontext, wie die Selbstkontrolle) – "PHV" oder "540" in der
    # nächsten Tabellenspalte gehört nicht zum Namen
    # (Datum, Jahreszahl, Betrag oder Telefonnummer dahinter sind kein Modellcode: "Jendrik Wimmersberger 14.05.1979")
    if not paar and personenkontext.modellcode_danach(text, ende, lambda code: not _code_wort(code), teile):
        return True                                       # "Tabbert Rossini 540", "Fronius Symo 10.0-3-M"; nicht "FAX"
    if _RECHTSFORM_DANACH_RE.match(text, ende) or any(_ORG_TEIL_RE.search(t) for t in teile):
        return True                                       # "Sixt GmbH …", "Stadtwerke Rosenheim"
    if _DATEI_DANACH_RE.match(text, ende) or _DATEI_ENDE_RE.search(text[start:ende]) \
            or _GRUSS_DANACH_RE.match(text, ende):
        return True                                       # "Bescheid.pdf", "Best regards"
    if personenkontext.tierangabe(text, start):
        return True                                       # "Abstammung: v. Gribaldi", "Name des Pferdes:"
    namen = [t for t in teile if _wissen_art(t)[0]]
    if teile[0].casefold() in _MEDIZIN_ANFANG and len(namen) < len(teile):
        return True                                       # "Morbus Scheuermann", "Chronische Lumbalgie"
    wissen = _wissen_modul()
    if len(teile) == 2 and teile[0] == "M." and personenkontext.diagnose(teile[1], wissen):
        return True                                       # "M. Parkinson" – nicht "M. Weber"
    if any(personenkontext.fachwort_medizin(t, wissen) for t in teile):
        return True                                       # "Rezidivierende Lumboischialgie"; nicht "Rimas Petraitis"
    # nur ein Wort allein: in "Okke Gesslert" ist das zweite Wort ein Familienname, kein Partizip
    if not namen and len(teile) == 1 and (_PARTIZIP_RE.fullmatch(teile[0]) or _ISCH_RE.fullmatch(teile[0])):
        return True                                       # "Ausgefertigt", "Beglaubigt", "Gegnerischer"
    return False


def _feld_etikett_stellung(text: str, start: int, ende: int) -> bool:
    """Steht die Stelle allein am Anfang ihrer Zeile oder Zelle (höchstens eine Laufnummer davor) und direkt dahinter
    ein Doppelpunkt ("Hergang: …", "1. Unfallschilderung:")? So steht ein Feldbezeichner, kein Name."""
    if not re.match(r"[ \t]*(?:\([^()\n]{0,25}\)[ \t]*)?:", text[ende:ende + 30]):
        return False
    zeilenanfang = text.rfind("\n", 0, start) + 1
    davor = text[zeilenanfang:start]
    if "\t" in davor:
        davor = davor[davor.rfind("\t") + 1:]
    return not davor.strip(" \t0123456789.)(-–•*")


def _im_etikett(text: str, start: int, ende: int) -> bool:
    """Liegt die Stelle ganz in einem Feldbezeichner der Wissensbasis (Etikett-Listen), der in ihrer Zeile steht –
    "Einweisender" in "Einweisender Arzt: Dr. Petra Ullrich", "Sozius" in "Sozius:"? Ein Etikett ist nie ein Name;
    nur die Zeile der Stelle wird durchsucht."""
    try:
        from . import wissen
    except Exception:  # pragma: no cover
        return False
    a = text.rfind("\n", 0, start) + 1
    b = text.find("\n", ende)
    b = len(text) if b < 0 else b
    if b - a > 400:
        a, b = max(a, start - 200), min(b, ende + 200)
    zeile = text[a:b]
    s, e = start - a, ende - a
    try:
        for art in wissen.ETIKETTEN_ARTEN:
            for v in wissen.finde(zeile, f"etiketten_{art}"):
                if v.start <= s and e <= v.ende and v.ende - v.start >= 4:
                    return True
    except Exception:  # pragma: no cover - Wissensbasis beschädigt
        return False
    return False


def _verlesenes_etikett(wort: str) -> bool:
    """Von der OCR verlesener Feldbezeichner ("Vomame", "Verscherungsnchmer") nach detektoren/etiketten_unscharf.py:
    langes, großgeschriebenes Wort, das weder bekannter Name noch bekanntes Wort ist. Allein KEIN Grund, einen
    Namen zu verwerfen – siehe verlesenes_etikett_statt_name."""
    w = wort.strip(".,;:()[]\"'")
    if len(w) < 6 or not w.isalpha():
        return False
    try:
        from .detektoren.etiketten_unscharf import etikettwort_fuer
    except Exception:  # pragma: no cover - Paket nicht ladbar
        return False
    # lange Komposita ("Versicherungsnuarmmer") auch mit untypischem Lesefehler – Nachnamen sind so lang nicht
    return etikettwort_fuer(w, nachsichtig=len(w) >= _LANGES_ETIKETTWORT) is not None


# Etikett-Stellung hinter einer Namensstelle: Doppelpunkt (auch hinter einer kurzen Klammer: "Vomame (Rufname):")
_DOPPELPUNKT_DANACH_RE = re.compile(r"[ \t]*(?:\([^()\n]{0,25}\)[ \t]*)?:")
# bei langen Wörtern auch Zeilen-/Zellenende oder eine Kennung dahinter ("Kundenntimmer 76183905")
_ETIKETT_ENDE_RE = re.compile(r"[ \t]*(?:\)[ \t]*)?(?:\n|\t\t|$)"
                              r"|[ \t]*(?:Nr\.?[ \t]*)?:?[ \t]*[A-Z]{0,4}[ \t./-]?\d{2}")
_LANGES_ETIKETTWORT = 12          # so lange Wörter sind Komposita ("Verscherungsnchmer"), kaum Nachnamen


def verlesenes_etikett_statt_name(text: str, start: int, ende: int) -> bool:
    """Ist die Namensstelle text[start:ende] der KI in Wahrheit ein von der OCR verlesener Feldbezeichner
    ("Name, Vomame:", "(Unterschrift Verscherungsnchmer")?

    NUR für OCR-Text: der Aufrufer prüft, dass die Zeichen aus der OCR stammen (detektoren/ocr_lesart.py). Auf der
    Textebene eines PDFs ist ein unbekanntes Wort nie ein Lesefehler, sondern womöglich ein Name ("Ehmann",
    "Wohnert", "Portner" liegen einen Buchstaben neben "Ehemann", "Wohnort", "Partner").

    Bedingungen: alle Wörter sind Sachwörter oder verlesene Etikettwörter, mindestens eins ist verlesen, und die
    Stelle steht in Etikett-Stellung – ein Doppelpunkt direkt dahinter; bei einem langen verlesenen Wort (ab 12
    Buchstaben, ein Kompositum wie "Verscherungsnchmer") auch das Zeilen- oder Zellenende oder eine Nummer dahinter
    ("Kundenntimmer 76183905"). Ein Nachname üblicher Länge allein auf einer Zeile (Grußblock, Unterschrift), in
    einer Liste oder im Fließtext bleibt damit ein Name; verworfen wird er nur mit Doppelpunkt dahinter, wenn er
    zugleich nur einen typischen Lesefehler von einem Etikettwort entfernt und dem Sprachmodell unbekannt ist."""
    if not (0 <= start < ende <= len(text)):
        return False
    teile = _namensteile(text[start:ende])
    verlesen = [t for t in teile if _verlesenes_etikett(t)]
    if not verlesen or not all(t in verlesen or _ist_sachwort(t) for t in teile):
        return False
    if _DOPPELPUNKT_DANACH_RE.match(text, ende):
        return True
    return (any(len(t) >= _LANGES_ETIKETTWORT for t in verlesen)
            and _ETIKETT_ENDE_RE.match(text, ende) is not None)


# ----------------------------------------------------------------------
# Hilfen
# ----------------------------------------------------------------------
_NAME_WORT = "[" + _GROSS + r"][\wäöüß'’\-]{1,40}"
_TITEL_RE = (r"(?:(?:Dr|Prof|Dipl|Mag|Ing|Med|Jur|Rer|Nat|Phil|Habil|Univ|Dent|Vet|RA|StB|Dipl\.-Ing|Dipl\.-Kfm|"
             r"Dipl\.-Jur|Dipl\.-Psych|Dipl\.-Kffr|B\.A|M\.A|M\.Sc|B\.Sc|LL\.M|h\.c|med|rer|nat|jur|phil|dent|vet|"
             r"habil|univ|pol|oec)\.?[ \t]+)")


def _titelform(text: str) -> str:
    """ALL-CAPS-Wörter (MAX MUSTERMANN) in Titelform (Max Mustermann) umschreiben, ohne die
    Zeichenpositionen zu verändern. Der Original-Fundtext wird später an denselben Offsets
    aus dem Originaltext gelesen."""
    def wandeln(m):
        wort = m.group(0)
        if wort in _ABKUERZUNGEN_GROSS:
            return wort
        aus = []
        anfang = True
        for c in wort:
            if c == "-":
                aus.append(c)
                anfang = True
                continue
            if anfang:
                aus.append(c)
                anfang = False
            else:
                k = c.lower()
                aus.append(k if len(k) == 1 else c)
        return "".join(aus)
    return re.sub(r"(?<![\wäöüß])[A-ZÄÖÜ]{2,}(?:-[A-ZÄÖÜ]{2,})*(?![\wäöüß])", wandeln, text)


def _hat_versalien(text: str) -> bool:
    for m in re.finditer(r"(?<![\wäöüß])[A-ZÄÖÜ]{3,}(?![\wäöüß])", text):
        if m.group(0) not in _ABKUERZUNGEN_GROSS:
            return True
    return False


def _stuecke(text: str):
    """Zerlegt langen Text an Zeilenumbrüchen in Stücke für spaCy. Liefert (offset, stueck)."""
    anfang = 0
    while anfang < len(text):
        ende = min(len(text), anfang + _STUECK_LAENGE)
        if ende < len(text):
            umbruch = text.rfind("\n", anfang + _STUECK_LAENGE // 2, ende)
            if umbruch > anfang:
                ende = umbruch + 1
        yield anfang, text[anfang:ende]
        anfang = ende


def _ner_spannen(nlp, text: str) -> set:
    """PER-Entitäten (start, end) über den ganzen Text, stückweise an Zeilenumbrüchen."""
    spannen = set()
    for offset, stueck in _stuecke(text):
        if not stueck.strip():
            continue
        doc = nlp(stueck)
        for ent in doc.ents:
            if ent.label_ == "PER":
                spannen.add((offset + ent.start_char, offset + ent.end_char))
    return spannen


def _ner_kurzzeilen(nlp, text: str) -> set:
    """Kurze Zeilen (Adressfenster, Tabellenzellen, Unterschriften) einzeln durch die NER —
    dort verschmilzt die Ganztext-Erkennung Namen mit Nachbarzeilen oder übersieht sie."""
    zeilen, offsets = [], []
    pos = 0
    for zeile in text.split("\n"):
        inhalt = zeile.strip()
        if 2 <= len(inhalt) <= 80 and re.search(r"[A-ZÄÖÜ][a-zäöüß]", inhalt) and "\x00" not in inhalt:
            zeilen.append(zeile)
            offsets.append(pos)
        pos += len(zeile) + 1
    spannen = set()
    if not zeilen:
        return spannen
    for offset, doc in zip(offsets, nlp.pipe(zeilen, batch_size=64)):
        for ent in doc.ents:
            if ent.label_ == "PER":
                spannen.add((offset + ent.start_char, offset + ent.end_char))
    return spannen


def _ner_versalien_zeilen(nlp, text: str) -> set:
    """Titelform-Pass nur für die Zeilen mit ALL-CAPS-Wörtern (MAX MUSTERMANN) samt je einer Nachbarzeile:
    dieselben Namen wie ein Titelform-Durchlauf über den Gesamttext, aber ohne die NER ein zweites Mal
    über das ganze Dokument laufen zu lassen (Gutachten PERF-04)."""
    zeilen = text.split("\n")
    offsets, pos = [], 0
    for z in zeilen:
        offsets.append(pos)
        pos += len(z) + 1
    betroffen = set()
    for i, z in enumerate(zeilen):
        if _hat_versalien(z):
            betroffen.update((i - 1, i, i + 1))
    bloecke, block = [], []
    for i in sorted(b for b in betroffen if 0 <= b < len(zeilen)):
        if block and i != block[-1] + 1:
            bloecke.append(block)
            block = []
        block.append(i)
    if block:
        bloecke.append(block)
    spannen = set()
    if not bloecke:
        return spannen
    texte = ["\n".join(_titelform(zeilen[i]) for i in b) for b in bloecke]
    for b, doc in zip(bloecke, nlp.pipe(texte, batch_size=64)):
        basis = offsets[b[0]]
        for ent in doc.ents:
            if ent.label_ == "PER":
                spannen.add((basis + ent.start_char, basis + ent.end_char))
    # Kurzzeilen in Titelform (Adressfenster in Versalien: "HERRN" ⏎ "MAX MUSTERMANN")
    kurz, kurz_offsets = [], []
    for b in bloecke:
        for i in b:
            inhalt = zeilen[i].strip()
            if 2 <= len(inhalt) <= 80 and _hat_versalien(zeilen[i]):
                kurz.append(_titelform(zeilen[i]))
                kurz_offsets.append(offsets[i])
    for basis, doc in zip(kurz_offsets, nlp.pipe(kurz, batch_size=64)):
        for ent in doc.ents:
            if ent.label_ == "PER":
                spannen.add((basis + ent.start_char, basis + ent.end_char))
    return spannen


_LUECKE_RE = re.compile(r"\n|[ \t]{2,}")


def _an_umbruechen_teilen(text: str, spannen) -> set:
    """Entitäten mit Zeilenumbruch oder breiter Lücke (Tabellenzellen) in ihre Teile zerlegen
    (Max Mustermann\\nLange Straße -> Max Mustermann | Lange Straße)."""
    aus = set()
    for start, ende in spannen:
        teil = text[start:ende]
        if not _LUECKE_RE.search(teil):
            aus.add((start, ende))
            continue
        pos = start
        for stueck in _LUECKE_RE.split(teil):
            if stueck.strip():
                aus.add((pos, pos + len(stueck)))
            pos += len(stueck)
            m = _LUECKE_RE.match(teil, pos - start)
            if m:
                pos += m.end() - m.start()
    return aus


def _bereinigen(text: str, start: int, ende: int):
    """Anreden/Titel vorn, Satzzeichen und Namensende-Wörter hinten abstreifen.
    Liefert (start, ende) oder None."""
    while start < ende and text[start] in " \t\n\r,.;:()[]\"'«»„“”*":
        start += 1
    while ende > start and text[ende - 1] in " \t\n\r,.;:()[]\"'«»„“”*":
        ende -= 1
    if start >= ende:
        return None
    mit_anrede = _VORHER_ANREDE_RE.search(text[max(0, start - 12):start]) is not None
    for _ in range(6):
        m = re.match(r"([^\s]+)[ \t]+", text[start:ende])
        if not m:
            break
        wort = m.group(1).lower().strip(".,")
        voll = m.group(1).lower()
        if (wort in ANREDEN or voll in ANREDEN or wort in TITEL or voll in TITEL
                or (wort in NAMEN_STOPPLISTE and not _kalendername(text, start, wort))
                or (voll in _VERSICHERER_EINZELWORT and not mit_anrede)):
            start += m.end()
            mit_anrede = wort in ANREDEN or voll in ANREDEN
        else:
            break
    for _ in range(6):
        m = re.search(r"[ \t]+([^\s]+)$", text[start:ende])
        if not m:
            break
        wort = m.group(1).lower().strip(".,;:")
        if (wort in NAMEN_STOPPLISTE and wort not in _NAMENSENDE
                and _nachname_hinter_vorname(text, start, start + m.start(), m.group(1))):
            break                                    # "Eckhard Freitag", "Erika Mai": Nachname, kein Wochentag
        if (wort in _NAMENSENDE or wort in NAMEN_STOPPLISTE or wort in _FIRMENWOERTER
                or _STRASSENSUFFIX_RE.search(wort) or any(c.isdigit() for c in wort) or _rang_kuerzel(m.group(1))):
            ende = start + m.start()
        else:
            break
    while ende > start and text[ende - 1] in " \t\n\r,.;:()[]\"'*":
        ende -= 1
    return (start, ende) if ende > start else None


@functools.lru_cache(maxsize=8192)
def _rang_kuerzel(wort: str) -> bool:
    """Kürzel einer Amts- oder Dienstbezeichnung der Wissensbasis ("KOK", "PHKin", "JAng", "JOSin", "RA"): gehört nicht
    zum Namen ("KOK Unterholzner", "Eibl, JAng")."""
    w = wort.strip(".,;:()")
    if not (2 <= len(w) <= 8) or sum(c.isupper() for c in w) < 2 or not re.fullmatch(r"[A-Za-zÄÖÜäöü'’]+", w):
        return False
    try:
        from . import wissen
        return wissen.ist_anrede_titel(w)
    except Exception:  # pragma: no cover - Wissensbasis fehlt
        return False


_TEILWORT_RE = re.compile(r"[^\s,;]+[,;]?")


def _wissen_wort(frage: str, wort: str) -> bool:
    """Frage an die Wissensbasis (ist_vorname, ist_nachname …) für ein Wort, Versalien in Titelform."""
    w = wort.strip(".,;:()[]\"'")
    if len(w) < 2:
        return False
    try:
        from . import wissen
        return bool(getattr(wissen, frage)(w.title() if w.isupper() else w))
    except Exception:  # pragma: no cover - Wissensbasis fehlt
        return False


def personen_teilen(text: str, start: int, ende: int) -> list:
    """Stelle mit mehreren Personen ohne Komma dazwischen an bekannten Vornamen teilen: "Jörg Ziegler Ursula
    Frank" (die OCR hat das Aufzählungskomma verschluckt) -> [(Jörg Ziegler), (Ursula Frank)].

    Geteilt wird vor einem Vornamen der Wissensbasis (oder vor einem Titel, auf den ein Vorname folgt), wenn davor
    mindestens zwei Namenswörter derselben Person stehen und das Wort davor ein Nachname ist (kein Vorname, oder
    ein mehrdeutiger Vorname, der auch Nachname ist: "Thomas Frank Ursula Wolf"). Doppelvornamen ("Anna Maria
    Schmidt", "Karl Heinz Frank") bleiben zusammen; ein Vorname ganz am Ende bildet nur dann eine eigene Person, wenn
    er eindeutig ist. Trenner zwischen den Personen sind nur Leerzeichen/Tabulatoren (kein Komma, kein Umbruch).
    Liefert [(start, ende), …] (eine Stelle, wenn nichts zu teilen ist)."""
    woerter = [(start + m.start(), start + m.end(), m.group(0)) for m in _TEILWORT_RE.finditer(text[start:ende])]
    if len(woerter) < 3:
        return [(start, ende)]

    def art(roh: str) -> str:
        w = roh.rstrip(",;")
        k = w.lower()
        if k in TITEL or k.strip(".") in TITEL or re.fullmatch(r"(?:Dipl|Prof|Dr|Mag|Ing)\.[\w.\-]*", w):
            return "titel"
        if w.islower() and (k in PARTIKEL or k.strip(".") in PARTIKEL):
            return "partikel"
        if w[:1].isupper() and len(w.strip(".")) >= 2:
            return "name"
        return "sonst"

    arten = [art(w[2]) for w in woerter]
    grenzen = []
    namen_seit = 0                                   # Namenswörter der laufenden Person
    for i, (s, e, roh) in enumerate(woerter):
        if arten[i] == "name" and namen_seit >= 2 and i >= 1:
            # Kandidat für eine neue Person: Vorname direkt hier, oder Titel(-kette) davor
            j = i
            while j > 0 and arten[j - 1] == "titel":
                j -= 1
            vorher = woerter[j - 1] if j >= 1 else None
            if (vorher is not None and arten[j - 1] == "name" and not vorher[2].endswith((",", ";"))
                    and text[vorher[1]:woerter[j][0]].strip(" \t") == ""
                    and _wissen_wort("ist_vorname", roh) and not _wissen_wort("ist_allerweltswort", roh)):
                vor_wort = vorher[2]
                nachname = (not _wissen_wort("ist_vorname", vor_wort)
                            or (_wissen_wort("ist_vorname_mehrdeutig", vor_wort)
                                and _wissen_wort("ist_nachname", vor_wort)))
                letzter = i == len(woerter) - 1
                eindeutig = not _wissen_wort("ist_vorname_mehrdeutig", roh) and not _wissen_wort("ist_nachname", roh)
                if nachname and (not letzter or eindeutig):
                    grenzen.append(j)
                    namen_seit = 1
                    continue
        if arten[i] == "name":
            namen_seit += 1
        elif arten[i] == "sonst":
            namen_seit = 0
    if not grenzen:
        return [(start, ende)]
    teile = []
    anfang = 0
    for g in grenzen + [len(woerter)]:
        stueck = woerter[anfang:g]
        if stueck:
            s, e = stueck[0][0], stueck[-1][1]
            while e > s and text[e - 1] in ",; \t":
                e -= 1
            teile.append((s, e))
        anfang = g
    return teile


def _nachname_hinter_vorname(text: str, start: int, ende: int, wort: str) -> bool:
    """Steht `wort` (großgeschrieben, bekannter Nachname) direkt hinter einem bekannten Vornamen?"""
    if not wort[:1].isupper():
        return False
    try:
        from . import wissen
        if not wissen.ist_nachname(wort.strip(".,;:")):
            return False
        davor = text[start:ende].split()
        return bool(davor) and wissen.ist_vorname(davor[-1].strip(".,;:"))
    except Exception:  # pragma: no cover
        return False


def _namensteile(name: str) -> list:
    """Tokens ohne Titel/Anreden/Partikel/Satzzeichen (für Plausibilität und Bestandteile)."""
    teile = []
    for roh in re.split(r"[\s,]+", name):
        t = roh.strip(".,;:()[]\"'")
        if not t:
            continue
        tl = t.lower()
        if tl in TITEL or roh.lower() in TITEL or tl in ANREDEN:
            continue
        if t.islower() and (tl in PARTIKEL or tl in TITEL):
            continue
        teile.append(t)
    return teile


# Monats- und Wochentagsnamen sind auch Nachnamen ("Erika Mai", "Eckhard Freitag"): hinter Herr/Frau oder einem
# Namens-Etikett ("Nachname: Freitag") gilt das Wort als Name, sonst bleibt es ein Kalenderwort
_KALENDERWOERTER = frozenset({
    "januar", "februar", "märz", "april", "mai", "juni", "juli", "august", "september", "oktober", "november",
    "dezember", "montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag"})
_NAMENSETIKETT_DAVOR_RE = re.compile(
    r"(?:(?<![\wäöüß])(?:Nachname|Familienname|Geburtsname|Name)[ \t]*:[ \t]*|"
    r"(?<![\wäöüß])(?:Herrn?|Frau|Hr\.|Fr\.)[ \t]+)(?:[A-ZÄÖÜ][a-zäöü]{0,4}\.[ \t-]*)*$")


def _kalendername(text: str, start: int, wort: str) -> bool:
    """Monats-/Wochentagsname an `start` als Nachname: direkt hinter Herr/Frau (auch mit Titel) oder einem
    Namens-Etikett ("Frau Mai", "Herrn Dr. Freitag", "Nachname: Freitag")."""
    return (wort.lower().strip(".,;:") in _KALENDERWOERTER
            and _NAMENSETIKETT_DAVOR_RE.search(text, max(0, start - 40), start) is not None)


# OCR-Reste, die die KI für Namen hält: fremde Zeichen ("i= SEE", "Ust«-TeiNe", "Aues|y"), dreifache
# Buchstaben ("IE EEESTEUER"), ein klein geschriebenes erstes Wort, das kein Namenspartikel ist ("ee BEER",
# "us Wersicherungsschein"), Großbuchstaben mitten im Wort ("TeiNe" – aber McLean, DeLuca, LaToya)
_OCR_ZEICHEN_RE = re.compile(r"[^\w\s.,'’()\-]")
_DREIFACH_RE = re.compile(r"([^\W\d_])\1\1", re.IGNORECASE)
_BINNEN_GROSS_RE = re.compile(r"[a-zäöüß][A-ZÄÖÜ]")
_BINNEN_ERLAUBT_RE = re.compile(r"(?:Mc|Mac|De|Di|Da|Du|La|Le|Van|Von|Fitz|O)[A-ZÄÖÜ][a-zäöüß]")


def _ocr_rest(name: str) -> bool:
    """Sieht der KI-Treffer wie ein OCR-Rest aus statt wie ein Name?"""
    if _OCR_ZEICHEN_RE.search(name) or _DREIFACH_RE.search(name):
        return True
    woerter = name.split()
    erstes = woerter[0].strip(".,;:()") if woerter else ""
    if erstes[:1].islower() and erstes.lower() not in PARTIKEL:
        return True
    for wort in woerter:
        for stueck in wort.split("-"):
            binnen = _BINNEN_GROSS_RE.search(stueck)
            if binnen and not (_BINNEN_ERLAUBT_RE.match(stueck) and binnen.start() <= 3
                               and not _BINNEN_GROSS_RE.search(stueck, binnen.end())):
                return True
    return False


_ANREDE_BINDESTRICH_RE = re.compile(r"(?:Herrn?|Frau)-([A-ZÄÖÜ][a-zäöüß'’]+(?:-[A-ZÄÖÜ][a-zäöüß'’]+)?)")


def _plausibel(text: str, start: int, ende: int, regel: bool = False) -> bool:
    """Plausibilitätsfilter: keine Ziffern/Kürzel, keine Feldbezeichner, keine Versicherer,
    keine Organisationen, mindestens ein großgeschriebenes Wort mit >= 3 Buchstaben (>= 2 hinter
    Herr/Frau: "Herr Li", Gutachten EQ-11). Reine KI-Treffer (regel=False) zusätzlich: keine Sachwörter
    (Überschriften, Feldbezeichner, Produkte, Allerweltswörter der Wissensbasis, Gutachten EQ-04), keine kurzen
    Versalien-Kürzel (RLV), nichts hinter Sach-Etiketten (Beruf:, Tarif:), kein Ortsteil ("am Taunus")."""
    name = text[start:ende]
    vorher = text[max(0, start - 12):start]
    mit_anrede = _VORHER_ANREDE_RE.search(vorher) is not None
    if len(name) < (2 if mit_anrede else 3) or any(c.isdigit() for c in name):
        return False
    angehaengt = _ANREDE_BINDESTRICH_RE.fullmatch(name)
    if angehaengt:
        # Anrede mit Bindestrich am Namen (OCR: "Frau-Kara fährt …"): ein Name, wenn der Rest ein Name der
        # Wissensbasis ist; geschwärzt wird die ganze Stelle samt Anrede
        return _wissen_art(angehaengt.group(1))[0]
    if re.search(r"-(?:ID|Nr|No|Id)\.?$", name, re.IGNORECASE) or _KFZ_RE.match(name):
        return False
    norm = re.sub(r"\s+", " ", name.lower()).strip()
    if regel and _kalendername(text, start, norm):
        return True                           # "Frau Mai", "Nachname: Freitag"
    if norm in NAMEN_STOPPLISTE or (norm in VERSICHERER_NAMEN and not mit_anrede):
        return False
    if not mit_anrede and personenkontext.organisations_spalte(text, start):
        return False                          # "Versicherer" ⏎ "Adam Riese": ein Versicherer, keine Person
    teile = _namensteile(name)
    if not teile:
        return False
    mindestlaenge = 2 if mit_anrede else 3
    if not any(len(re.sub(r"[^\wäöüß]", "", t)) >= mindestlaenge and t[0].isupper() for t in teile):
        return False
    if any(t.lower().strip(".") in _FIRMENWOERTER for t in teile):
        return False
    if not regel and not mit_anrede:
        if _ocr_rest(name):
            return False                      # OCR-Reste ("IE EEESTEUER", "ee BEER", "i= SEE")
        if all(_ist_sachwort(t) for t in teile):
            return False                      # "Schadenanzeige Kraftfahrt-Haftpflicht", "Familientarif"
        if _im_etikett(text, start, ende):
            return False                      # "Einweisender" in "Einweisender Arzt:": ein Etikett ist nie ein Name
        if len(teile) == 1 and _rang_kuerzel(teile[0]):
            return False                      # "JAng", "KOK": Amts- und Dienstbezeichnungen
        if len(teile) <= 2 and _feld_etikett_stellung(text, start, ende) and not any(_wissen_art(t)[0] for t in teile):
            return False                      # "Hergang:", "Unfallschilderung:" am Zeilenanfang: ein Feldbezeichner
        if _ner_sachtreffer(text, start, ende, teile):
            return False                      # Marke, Modell, Tierrasse, Firma, Fachwort, Partizip, Dateiname
        if len(teile) == 1 and teile[0].isupper() and len(teile[0]) <= 4:
            return False                      # Kürzel wie RLV, BU, KFZ (Versalien-Namen kommen über die Regeln)
        zeilenanfang = text.rfind("\n", 0, start) + 1
        if _SACHETIKETT_RE.search(text[zeilenanfang:start]):
            return False                      # "Beruf / Arbeitgeber: Polier, …"
        if len(teile) == 1 and re.search(r"(?<![\wäöüß])(?:am|an der|im|ob der|in der|vor der)[ \t]+$", vorher):
            return False                      # "Hofheim am Taunus", "Frankfurt am Main"
        if len(teile) == 1 and _FIRMA_DANACH_RE.match(text, ende):
            return False                      # "Taunus Krankenversicherung AG": Teil eines Firmennamens
    if all(t.lower().strip(".") in NAMEN_STOPPLISTE or t.lower().strip(".") in _NAMENSENDE
           or (t.lower() in _VERSICHERER_EINZELWORT and not mit_anrede) for t in teile):
        return False
    if not mit_anrede:
        if teile[0].lower() in _VERSICHERER_EINZELWORT:
            return False
        if len(teile) == 1 and teile[0].lower() in _STRASSEN_ADJEKTIVE:
            return False
    if len(teile) == 1 and _STRASSENSUFFIX_RE.search(teile[0]):
        return False
    if len(teile) == 1 and not mit_anrede and teile[0].isupper() and (
            len(teile[0]) >= 8 or _BIC_FORM_RE.match(teile[0])):
        return False                      # Codes wie COBADEFFXXX, PRODUKTKENNUNG
    if len(teile) == 1 and not mit_anrede and _ORT_DATUM_RE.match(text, ende):
        return False                      # "Coburg, 20.01.2025" ist ein Ort
    if all(t.islower() for t in teile):
        return False
    return True


# ----------------------------------------------------------------------
# Regeln (zusätzlich zur KI)
# ----------------------------------------------------------------------
_ROLLEN = (r"(?:Antragsteller(?:in)?|Versicherungsnehmer(?:in)?|VN|Name|Nachname|Vorname|Patient(?:in)?|"
           r"Kontoinhaber(?:in)?|Versicherte Person|Versicherte[r]?|Kunde|Kundin|Vollmachtgeber(?:in)?|"
           r"Bevollmächtigte[r]?|Zeuge|Zeugin|Fahrer(?:in)?|Unfallgegner(?:in)?|Mitversichert(?:e[r]?)?|"
           r"Bezugsberechtigte[r]?|Halter(?:in)?|Geschädigte[r]?|Verstorbene[r]?|Ehepartner(?:in)?|Ehefrau|"
           r"Ehemann|Kind|Sohn|Tochter|Bearbeiter(?:in)?|Ansprechpartner(?:in)?|Sachbearbeiter(?:in)?|"
           r"Vermittler(?:in)?|Makler(?:in)?|Berater(?:in)?|Gutachter(?:in)?|Arzt|Ärztin|Mieter(?:in)?|"
           r"Vermieter(?:in)?|Käufer(?:in)?|Verkäufer(?:in)?|Erbe|Erbin|Betroffene Person|"
           r"Datenschutzbeauftragte[r]?|Verantwortliche[r]?|Unterschrift|Auftraggeber(?:in)?|Zahlungspflichtige[r]?|"
           r"Beitragszahler(?:in)?|Schuldner(?:in)?|Gläubiger(?:in)?|Empfänger(?:in)?|Absender(?:in)?|"
           r"Kontakt|Ansprechperson|Behandler(?:in)?|Mitbehandler(?:in)?|Hausarzt|Hausärztin|Pflegeperson|"
           r"Betreuer(?:in)?|Vormund|Erziehungsberechtigte[r]?|Lebensgefährt(?:e|in)|Partner(?:in)?)")
_ROLLE_RE = re.compile(
    r"(?<![\wäöüß])" + _ROLLEN + r"(?:[ \t]*/[ \t]*\w+)?[ \t]*:[ \t]*"
    r"(?:(?:Herrn?|Frau|Hr\.|Fr\.)[ \t]+)?" + _TITEL_RE + r"*"
    r"(" + _NAME_WORT + r"(?:,?[ \t]+" + _TITEL_RE + r"*" + _NAME_WORT + r"){0,3})")
_ANREDE_RE = re.compile(
    r"(?<![\wäöüß])(?:Herrn?|Frau|Fräulein|Hr\.|Fr\.)[ \t]+" + _TITEL_RE + r"*"
    r"(" + _NAME_WORT + r"(?:[ \t]+" + _TITEL_RE + r"*" + _NAME_WORT + r"){0,2})")
_TITEL_NAME_RE = re.compile(
    r"(?<![\wäöüß])(?:Dr|Prof|Dipl\.-Ing|Dipl\.-Kfm|Dipl\.-Kffr|Dipl\.-Jur|Dipl\.-Psych|Dipl\.-Betriebsw|"
    r"Mag|RA|StB)\.[ \t]+" + _TITEL_RE + r"*"
    r"(" + _NAME_WORT + r"(?:[ \t]+" + _NAME_WORT + r"){0,2})(?![\wäöüß])")
_UNTERSCHRIFT_RE = re.compile(
    r"(?<![\wäöüß])(?:i\.[ \t]?A\.|i\.[ \t]?V\.|gez\.|ppa\.|p\.[ \t]?p\.)[ \t]+" + _TITEL_RE + r"*"
    r"(" + _NAME_WORT + r"(?:[ \t]+" + _NAME_WORT + r"){0,2})")
_BEZIEHUNG_RE = re.compile(
    r"(?<![\wäöüß])(?i:Ihr|Ihre|Ihren|Ihrem|Ihrer|unser|unsere|unseren|unserem|mein|meine|meinen|meinem|"
    r"sein|seine|seinen|seinem|der|die|den|dem|des)[ \t]+"
    r"(?:Sohn|Tochter|Kind|Enkel|Enkelin|Ehefrau|Ehemann|Ehegatte|Ehegattin|Lebensgefährt(?:e|in)|"
    r"Lebenspartner(?:in)?|Partner(?:in)?|Nachbar(?:in)?|Mandant(?:in)?|Kollege|Kollegin|Mitarbeiter(?:in)?|"
    r"Zeuge|Zeugin|Fahrer(?:in)?|Arzt|Ärztin|Hausarzt|Hausärztin|Vermittler(?:in)?|Berater(?:in)?|"
    r"Makler(?:in)?|Gutachter(?:in)?|Anwalt|Anwältin|Rechtsanwalt|Rechtsanwältin|Betreuer(?:in)?|"
    r"Mutter|Vater|Bruder|Schwester|Nichte|Neffe|Witwe|Witwer|Patient(?:in)?|Kunde|Kundin|"
    r"Versicherungsnehmer(?:in)?|Antragsteller(?:in)?|Versicherte[r]?)[ \t]+"
    r"(?:(?:Herrn?|Frau)[ \t]+)?" + _TITEL_RE + r"*"
    r"(" + _NAME_WORT + r"(?:[ \t]+" + _TITEL_RE + r"*" + _NAME_WORT + r")?)(?![\wäöüß])")
_KOMMA_VORNAME_RE = re.compile(r",[ \t]+(" + _NAME_WORT + r")(?![\wäöüß])")
_ANREDE_ZEILE_RE = re.compile(r"^(?:An[ \t]+)?(?:Herrn?|Frau|Familie|Fam\.|Eheleute|Herrn und Frau|Frau und Herrn)$")
_ADRESSZEILE_RE = re.compile(r"\d|(?i:straße|strasse|str\.|weg|platz|allee|gasse|postfach|postfach|c/o)")
_TABELLENKOPF_RE = re.compile(r"(?<![\wäöüß])(Name, Vorname|Nachname, Vorname|Name|Nachname|Vorname|Familienname)(?![\wäöüß])")
_ZELLE_RE = re.compile(r"^[A-ZÄÖÜ][\wäöüß'’\-]+(?:,?[ \t][A-ZÄÖÜ][\wäöüß'’\-]+){0,2}$")


def _kandidat(kandidaten, text, start, ende, gruppe=None, regel=False):
    """Kandidaten bereinigen, prüfen und eintragen (an breiten Lücken endet der Name).
    regel=True: Treffer einer Kontextregel (Rolle, Anrede, Adressfenster, Tabelle) — dort gelten
    die strengen Filter für reine KI-Treffer nicht."""
    luecke = _LUECKE_RE.search(text, start, ende)
    if luecke:
        ende = luecke.start()
    geb = _GEB_IM_NAMEN_RE.search(text, start, ende)
    if geb and geb.start() > start:
        # "Anna Weber geb. Schulz" als eine Stelle (KI): Name und Geburtsname getrennt, das Etikett bleibt stehen
        links = _kandidat(kandidaten, text, start, geb.start(), gruppe, regel)
        return _kandidat(kandidaten, text, geb.end(), ende, gruppe, regel) or links
    # mehrere Personen ohne Komma ("Jörg Ziegler Ursula Frank") werden getrennte Kandidaten; eine Spanne der KI endet an
    # einem kleingeschriebenen Wort, das kein Namenspartikel ist ("Lukas den Ball", "Kranzbühler, Josef gegen …")
    stuecke = _an_kleinwoertern_teilen(text, start, ende) if not regel and gruppe is None else [(start, ende)]
    teile = [t for a, b in stuecke for t in personen_teilen(text, a, b)] if gruppe is None else stuecke
    gefunden = False
    for s, e in teile:
        bereich = _bereinigen(text, s, e)
        if bereich and _plausibel(text, *bereich, regel=regel):
            kandidaten.append({"text": text[bereich[0]:bereich[1]], "start": bereich[0],
                               "ende": bereich[1], "gruppe": gruppe})
            gefunden = True
    return gefunden


# Artikel gehören nur hinter einem anderen Partikel zum Namen ("van den Berg", "von der Leyen"), nie allein ("Lukas den
# Ball"); die übrigen Partikel ("von", "de", "ter", "zu") auch allein ("Jan ter Horst")
_ARTIKEL_PARTIKEL = frozenset({"der", "den", "dem", "des", "die", "das", "und", "auf", "vor", "unter", "ober",
                               "nieder"})
_KLEINWORT_RE = re.compile(r"[a-zäöüß][\wäöüß'’\-]*")
# englische Grußformeln zwischen Namen ("Best regards, Irmtraud Ölschläger")
_GRUSS_KLEIN = frozenset({"regards", "wishes", "greetings"})


def _an_kleinwoertern_teilen(text: str, start: int, ende: int) -> list:
    """Spanne der KI an kleingeschriebenen Funktionswörtern teilen, die hier kein Namenspartikel sind: "Kranzbühler,
    Josef gegen Felsberger" -> [Kranzbühler, Josef], [Felsberger]; "Lukas den Ball" -> [Lukas], [Ball]. Andere
    kleingeschriebene Wörter teilen nicht – auf OCR-Seiten stehen verlesene Namensteile oft klein mitten im Namen
    ("Dr. Heinz ensmf Näußlenr", "Frau-Kara fahr"). Liefert die Stücke (start, ende), ohne leere."""
    stuecke, anfang, vorher = [], start, None
    for m in re.finditer(r"\S+", text[start:ende]):
        wort = m.group(0).strip(",;()")
        s0 = start + m.start()
        if _KLEINWORT_RE.fullmatch(wort):
            k = wort.casefold()
            partikel = k in PARTIKEL and (k not in _ARTIKEL_PARTIKEL
                                          or (vorher is not None and vorher in PARTIKEL))
            if not partikel and (k in kennungsformen.FUNKTIONSWOERTER or k in _GRUSS_KLEIN):
                if s0 > anfang:
                    stuecke.append((anfang, s0))
                anfang = start + m.end()
            vorher = k
        else:
            vorher = None
    if ende > anfang:
        stuecke.append((anfang, ende))
    return [(a, b) for a, b in stuecke if text[a:b].strip()] or [(start, ende)]


def _name_kuerzen(text: str, start: int, ende: int):
    """Regel-Treffer am ersten Namensende-Wort abschneiden ('Mustermann Hauptstraße' -> 'Mustermann')."""
    pos = start
    for m in re.finditer(r"[^\s,]+", text[start:ende]):
        wort = m.group(0).lower().strip(".,;:")
        if (wort in NAMEN_STOPPLISTE and wort not in _NAMENSENDE and pos > start
                and _nachname_hinter_vorname(text, start, start + m.start(), m.group(0))):
            pos = start + m.end()                    # "Erika Mai", "Eckhard Freitag": Nachname, kein Monat
            continue
        if pos == start and _kalendername(text, start + m.start(), wort):
            pos = start + m.end()                    # "Frau Mai", "Nachname: Freitag, Eckhard"
            continue
        if (wort in _NAMENSENDE or wort in NAMEN_STOPPLISTE or wort in _FIRMENWOERTER
                or _STRASSENSUFFIX_RE.search(wort) or any(c.isdigit() for c in wort)):
            return start, pos if pos > start else start
        pos = start + m.end()
    return start, ende


def _regel_kandidaten(text: str) -> list:
    kandidaten = []
    # 1) Rollen-Etikett: "Versicherungsnehmer: Herr Max Mustermann", "Antragsteller: MUSTERMANN, MAX"
    for m in _ROLLE_RE.finditer(text):
        s, e = _name_kuerzen(text, m.start(1), m.end(1))
        name = text[s:e]
        if _RECHTSFORM_DANACH_RE.match(text, e) or any(_ORG_TEIL_RE.search(t) for t in name.split()):
            continue                                 # "Vermieter: Sixt GmbH & Co …": eine Firma, keine Person
        za, ze = text.rfind("\n", 0, s) + 1, text.find("\n", e)
        if any(a <= s - za and e - za <= b for a, b in _sachname_stellen(text[za:len(text) if ze < 0 else ze])):
            continue                                 # "Kontakt: Instagram @…": eine Plattform, keine Person
        if "," in name:
            links, rechts = name.split(",", 1)
            if len(_namensteile(links)) != 1 or len(_namensteile(rechts)) > 2:
                e = s + len(links)                   # "Katarzyna Nowak, Kennzeichen" -> nur der Name
        _kandidat(kandidaten, text, s, e, regel=True)
    # 2) Anrede im Satz: "Frau Schulze aus der Nachbarschaft", "Herrn Dr. Hans Weber"
    for m in _ANREDE_RE.finditer(text):
        s, e = _name_kuerzen(text, m.start(1), m.end(1))
        _kandidat(kandidaten, text, s, e, regel=True)
    # 3) Unterschriften: "i. A. Sabine Krüger", "gez. Peter Schmidt"
    for m in _UNTERSCHRIFT_RE.finditer(text):
        s, e = _name_kuerzen(text, m.start(1), m.end(1))
        _kandidat(kandidaten, text, s, e, regel=True)
    # 3a) Titel: "Dr. Max Mustermann", "Prof. Dr. med. Anna Berg", "Dipl.-Ing. Max Hofer"
    for m in _TITEL_NAME_RE.finditer(text):
        s, e = _name_kuerzen(text, m.start(1), m.end(1))
        _kandidat(kandidaten, text, s, e, regel=True)
    # 3b) Beziehungswörter im Satz: "Ihr Sohn Ben", "unsere Tochter Mia", "der Zeuge Herr Weber"
    for m in _BEZIEHUNG_RE.finditer(text):
        s, e = _name_kuerzen(text, m.start(1), m.end(1))
        _kandidat(kandidaten, text, s, e, regel=True)
    # 4) Adressfenster: Zeilen zwischen "Herrn"/"Frau" und der Straßenzeile
    zeilen = text.split("\n")
    offsets, pos = [], 0
    for z in zeilen:
        offsets.append(pos)
        pos += len(z) + 1
    for i, zeile in enumerate(zeilen):
        if not _ANREDE_ZEILE_RE.match(zeile.strip()):
            continue
        namenszeilen = []
        for j in range(i + 1, min(i + 4, len(zeilen))):
            inhalt = zeilen[j].strip()
            if not inhalt or _ADRESSZEILE_RE.search(inhalt) or len(inhalt.split()) > 5:
                break
            namenszeilen.append(j)
        if not namenszeilen:
            continue
        teile = []
        for j in namenszeilen:
            bereich = _bereinigen(text, offsets[j], offsets[j] + len(zeilen[j]))
            if bereich:
                teile.append(text[bereich[0]:bereich[1]])
        gruppe = " ".join(teile) if len(teile) > 1 else None
        for j in namenszeilen:
            _kandidat(kandidaten, text, offsets[j], offsets[j] + len(zeilen[j]), gruppe, regel=True)
    # 5) Tabellen mit Spaltenkopf Name / Vorname
    for i, zeile in enumerate(zeilen):
        koepfe = [(m.start(), m.group(1)) for m in _TABELLENKOPF_RE.finditer(zeile)]
        if not koepfe or ":" in zeile:
            continue
        # Spaltenanfänge aller Kopfzellen (durch >= 2 Leerzeichen getrennt)
        spalten = sorted({m.start() for m in re.finditer(r"(?:^|(?<=[ \t]{2})|(?<=\t))[^\s]", zeile)})
        for j in range(i + 1, min(i + 60, len(zeilen))):
            datenzeile = zeilen[j]
            if not datenzeile.strip():
                break
            zeilen_kandidaten = []
            for spalte, kopf in koepfe:
                naechste = [s for s in spalten if s > spalte]
                grenze = naechste[0] if naechste else len(datenzeile)
                zelle = datenzeile[max(0, spalte - 2):grenze]
                m = re.search(r"[^\s].*?(?=[ \t]{2,}|$)", zelle)
                if not m:
                    zeilen_kandidaten = []
                    break
                inhalt = m.group(0).strip()
                if not _ZELLE_RE.match(inhalt) or inhalt.lower() in NAMEN_STOPPLISTE:
                    zeilen_kandidaten = []
                    break
                anfang = offsets[j] + max(0, spalte - 2) + m.start()
                zeilen_kandidaten.append((anfang, anfang + len(m.group(0).rstrip()), kopf, inhalt))
            if not zeilen_kandidaten:
                break
            gruppe = None
            if len(zeilen_kandidaten) >= 2:
                nach = [k[3] for k in zeilen_kandidaten if k[2] in ("Name", "Nachname", "Familienname")]
                vor = [k[3] for k in zeilen_kandidaten if k[2] == "Vorname"]
                if nach and vor:
                    gruppe = f"{vor[0]} {nach[0]}"
            for anfang, ende, kopf, inhalt in zeilen_kandidaten:
                if "," in inhalt:
                    gruppe = inhalt
                _kandidat(kandidaten, text, anfang, ende, gruppe, regel=True)
    return kandidaten


# ----------------------------------------------------------------------
# Geburtsname
# ----------------------------------------------------------------------
# Geburtsname hinter "geb." / "geb:" / "geborene(r)" / "Geburtsname" ("Anna Weber geb. Schulz", "WEBER, ANNA GEB.
# SCHULZ", "(geb. Schulz-Meyer)", "Geburtsname: Schulz"): der Nachname dahinter ist ein Personenname, auch in Versalien
# und mit Bindestrich. Nicht: ein Datum oder Ort dahinter ("geb. 12.03.1980", "geb. am …", "geb. in Köln"), "Gebr."
# (Gebrüder), "Geb." für Gebäude oder Gebühr ("Geb. 3", "Geb.-Nr.", "Geb. Ost" – großgeschrieben zählt "Geb." nur
# direkt hinter einem Namen), klein geschriebene Wörter, "geborene" als Eigenschaftswort ("eine geborene
# Berlinerin") und Spaltenköpfe ("geb. ⇥⇥ Ort": hinter "geb." zählt nur dieselbe Zelle).
_GEB_ETIKETT_RE = re.compile(
    r"(?<![\wäöüß.\-])(?:(?P<geb>geb|GEB|Geb)(?:\.:?|:|,)?|(?P<geborene>geborene[rn]?|GEBORENE[RN]?|Geborene[rn]?)"
    # "gab." – so liest die Texterkennung "geb." ("Anna Weber gab. Quarnstedt"); nur zwischen zwei Namen (unten)
    r"|(?P<gab>gab|GAB)\.)"
    # dahinter kein Wortzeichen – außer direkt hinter "geb." / "geb:" ein großer Anfangsbuchstabe ("geb.Schulz");
    # das Feld-Etikett "Geburtsname" liest kennungsformen.geburtsname_hinter_etikett (dieselbe Regel wie die
    # Selbstkontrolle)
    r"(?:(?![\wäöüß\-])|(?<=[.:])(?=[" + _GROSS + r"]))")
_GEB_PARTIKEL_WORT = (r"(?:von|van|de|der|den|zu|zur|vom|ten|ter|da|di|dos|das|del|della|du|la|le|al|el|"
                      r"VON|VAN|DE|DER|DEN|ZU|ZUR|VOM|DA|DI|DOS|DEL|DU|LA|LE|AL|EL)")
_GEB_PARTIKEL = r"(?:" + _GEB_PARTIKEL_WORT + r"[ ]+){0,2}"
_GEB_NAME_RE = re.compile(_GEB_PARTIKEL + r"(?:[dDlL]['’])?[" + _GROSS + r"][\wäöüß'’]+(?:-[" + _GROSS
                          + r"][\wäöüß'’]+)*"
                          r"(?![\wäöüß'’\-])")
# weiterer Teil eines mehrteiligen Geburtsnamens ("Garcia Lopez", "da Silva Santos", "Öztürk Demir", "Mac Allister")
_GEB_WEITER_RE = re.compile(r"[ ]+((?:" + _GEB_PARTIKEL_WORT + r"[ ]+)?[" + _GROSS + r"][\wäöüß'’]+(?:-["
                            + _GROSS + r"][\wäöüß'’]+)*)(?![\wäöüß'’\-])")
# Vorsilben, hinter denen ein Geburtsname immer weitergeht ("Mac Allister", "O' Brien", "San Martín")
_GEB_VORSILBE = frozenset({"mac", "mc", "o'", "o’", "fitz", "san", "santa", "st.", "abu", "ben", "bin", "ibn"})
_GEB_LUECKE_RE = re.compile(r"[ ]{0,8}")             # Festbreiten-Listen: "WEBER, ANNA GEB.    QUARNSTEDT"
_GEB_UMBRUCH_RE = re.compile(r"[ ]*\n[ ]*")
# hinter dem Wort geht ein Datum weiter: eine Ziffer (auch hinter einem Punkt: "Od.12.1973") oder ein Monatsname
# hinter einem Punkt ("geb. Od. Dez. 1973" – so liest die OCR "geb. 04. Dez. 1973"; das Wort ist der Tag)
_DATUM_DAHINTER_RE = re.compile(
    r"[ \t]{0,2}(?:\d|\.[ \t]*(?:\d|(?i:jan(?:uar)?|jän(?:ner)?|feb(?:ruar)?|mär(?:z)?|maerz|mrz|apr(?:il)?|mai"
    r"|jun(?:i)?|jul(?:i)?|aug(?:ust)?|sep(?:t(?:ember)?)?|okt(?:ober)?|nov(?:ember)?|dez(?:ember)?)(?![\wäöüß])))")
# Name (eines Kandidaten) direkt vor dem Etikett: nur Leerraum, Komma oder öffnende Klammer dazwischen
_VOR_GEB_RE = re.compile(r"[ \t]*,?[ \t]*\(?[ \t]*$")
_NAME_DAVOR_RE = re.compile(r"[" + _GROSS + r"][\wäöüß'’\-]+,?[ \t]*\(?$")
# Trenner Name/Geburtsname in einem Vollnamen ("Anna Weber geb. Schulz", "WEBER, ANNA (GEB. SCHULZ)")
_GEB_IM_NAMEN_RE = re.compile(r"[ \t]*[,(]?[ \t]*(?<![\wäöüß.\-])(?:(?:geb|GEB|Geb)[.:,]?|geborene[rn]?|GEBORENE[RN]?)"
                              r"(?=[ \t\n])[ \t]*\n?[ \t]*")
GEBURTSNAME_QUELLE = "ner.geburtsname"


def geburtsname_teilen(name: str) -> tuple:
    """(Name ohne Geburtsnamen, Geburtsname oder None): "Anna Weber geb. Schulz" -> ("Anna Weber", "Schulz")."""
    m = _GEB_IM_NAMEN_RE.search(name or "")
    if m is None or m.start() == 0:
        return name, None
    rest = name[m.end():].strip(" \t\n,;:()")
    return name[:m.start()].rstrip(" \t\n,("), rest or None


# Füllwörter eines Formulars hinter "geb."/"Geburtsname:" ("Geburtsname: Siehe oben", "Weber geb. Unbekannt",
# "Familienstand: geb. Ledig") und das Kürzel des Geburtsdatums ("GEB. DAT.") sind kein Geburtsname
_GEB_KEIN_NAME = frozenset({"siehe", "wie", "keiner", "keine", "kein", "unbekannt", "entfällt", "entfaellt", "ledig",
                            "verheiratet", "geschieden", "verwitwet", "gleich", "identisch", "dito", "nein", "ja",
                            "ohne", "nicht", "oben", "unten", "vorstehend", "derselbe", "dieselbe", "dasselbe",
                            "dat", "datum"})
# direkt an "geb." geschrieben ist es der zweite Teil eines Feldkürzels ("GEB.DAT.", "Geb.Ort", "geb.Tag",
# "Geb.Name", "GEB.NR."), kein Geburtsname wie in "geb.Schulz"
_GEB_KUERZEL_TEIL = frozenset({"dat", "datum", "ort", "tag", "jahr", "land", "name", "nr", "nummer", "no"})


def _geburtsname_wort(text: str, s: int, e: int) -> bool:
    """Kann text[s:e] hinter einem Geburtsnamen-Etikett ein Nachname sein? Keine Ziffer darin, kein Datum dahinter
    ("Mai 1980", "Od. Dez. 1973"), kein Feldbezeichner, Füllwort oder Sachwort ("Ort", "Ost", "Siehe", "Unbekannt",
    "Hauptgebäude"), keine Straße, kein Versicherer, keine Firma ("Schulz GmbH"), keine Großstadt, die kein Nachname
    ist ("Anna Weber geb. Hamburg": der Geburtsort). Lange Versalien gelten hier als Name ("GEB. QUARNSTEDT"): das
    Etikett davor ist Beleg genug."""
    if _DATUM_DAHINTER_RE.match(text, e) or any(c.isdigit() for c in text[s:e]):
        return False                                  # "geb. Mai 1980", "geb. Od. Dez. 1973" (OCR): ein Datum
    teile = [t for t in text[s:e].split() if t.casefold() not in PARTIKEL]
    if not teile:
        return False
    kern = teile[-1]
    k = kern.casefold()
    if any(t.casefold().strip(".") in _GEB_KEIN_NAME for t in teile):
        return False
    if (k in NAMEN_STOPPLISTE and k not in _KALENDERWOERTER) or k in _NAMENSENDE or k in _FIRMENWOERTER:
        return False
    if len(teile) == 1 and _wissen_wort("ist_grossstadt", kern) and not _wissen_wort("ist_nachname", kern):
        return False
    if k in _VERSICHERER_EINZELWORT or _STRASSENSUFFIX_RE.search(k) or _FIRMA_DANACH_RE.match(text, e):
        return False
    if re.search(r"-(?:ID|Nr|No|Id)\.?$", kern, re.IGNORECASE) or sum(c.isalpha() for c in kern) < 2:
        return False
    return not _ist_sachwort(kern) or _wissen_wort("ist_nachname", kern)


def _name_vor(text: str, pos: int, starts_je_ende: dict) -> tuple | None:
    """(start, ende) des Namens direkt vor einem Geburtsnamen-Etikett an `pos`: ein Kandidat, der dort endet (nur
    Leerraum, Komma oder öffnende Klammer dazwischen; starts_je_ende: Ende -> Anfänge der Kandidaten), oder Vor- und
    Nachname direkt davor in derselben Zeile – der längere von beiden ("Weber, Anna" statt nur "Anna"). Beginnt das
    Etikett seine Zeile ("Anna Weber" ⏎ "geb. Schulz"), zählt der Name am Ende der Zeile darüber."""
    zeilenanfang = text.rfind("\n", 0, pos) + 1
    davor = text[zeilenanfang:pos]
    if not davor.strip(" \t(") and zeilenanfang > 0:
        pos = zeilenanfang - 1
        while pos > 0 and text[pos - 1] in " \t":
            pos -= 1
        zeilenanfang = text.rfind("\n", 0, pos) + 1
        davor = text[zeilenanfang:pos]
    luecke = _VOR_GEB_RE.search(davor)
    ende = zeilenanfang + luecke.start()
    kandidat = (min(starts_je_ende[ende]), ende) if starts_je_ende.get(ende) else None   # der längste Kandidat
    woerter = _name_aus_woertern(text, zeilenanfang, ende)
    if woerter is not None and (kandidat is None or woerter[0] < kandidat[0]) and woerter[1] >= ende - 1:
        return woerter
    return kandidat


def _name_aus_woertern(text: str, zeilenanfang: int, ende: int) -> tuple | None:
    """Vor- und Nachname direkt vor `ende` ohne Kandidaten ("Sabine Krüger geb. …", "WEBER, ANNA GEB. …")."""
    # Namenswörter von rechts
    woerter = list(re.finditer(r"[^\s,()]+,?", text[zeilenanfang:ende]))
    start, anzahl, komma = None, 0, False
    for w in reversed(woerter):
        roh = w.group(0)
        kern = roh.rstrip(",")
        if roh.endswith(","):
            if komma or anzahl == 0:
                break
            komma = True                              # "WEBER, ANNA": Nachname, Vorname
        if (not re.fullmatch(r"[" + _GROSS + r"][\wäöüß'’\-]+", kern) or kern.casefold() in ANREDEN
                or kern.casefold() in TITEL or _ist_sachwort(kern) or anzahl >= 3):
            break
        if zeilenanfang + w.end() != ende and text[zeilenanfang + w.end():ende].strip(" \t") and anzahl == 0:
            break
        start = zeilenanfang + w.start()
        anzahl += 1
    if start is None or anzahl < 2:
        return None
    bereich = _bereinigen(text, start, ende)
    if not bereich or len(_namensteile(text[bereich[0]:bereich[1]])) < 2 or not _plausibel(text, *bereich, regel=True):
        return None
    return bereich


def _geburtsname_ende(text: str, s: int, e: int) -> int:
    """Ende eines mehrteiligen Geburtsnamens, der bei s:e beginnt: weitere Teile hinter einer Vorsilbe ("Mac Allister")
    oder bekannte Nachnamen ("Garcia Lopez", "da Silva Santos", "Öztürk Demir") – höchstens zwei, keiner ein Sachwort
    oder Kalenderwort und kein Datum dahinter."""
    for _ in range(2):
        w = _GEB_WEITER_RE.match(text, e)
        if w is None or "\n" in w.group(0):
            break
        teil = w.group(1).split()[-1]
        letztes = text[s:e].split()[-1].casefold()
        vorsilbe = letztes in _GEB_VORSILBE
        if not vorsilbe and not (_wissen_wort("ist_nachname", teil) and not _wissen_wort("ist_grossstadt", teil)):
            break
        if teil.casefold() in _KALENDERWOERTER or _DATUM_DAHINTER_RE.match(text, w.end()) or (
                not vorsilbe and _ist_sachwort(teil) and not _wissen_wort("ist_nachname", teil)):
            break
        danach = _GEB_WEITER_RE.match(text, w.end())
        if (not vorsilbe and _wissen_wort("ist_vorname", teil) and danach is not None
                and _wissen_wort("ist_nachname", danach.group(1).split()[-1])):
            break                                     # "geb. Schulz Peter Müller": dahinter beginnt eine Person
        e = w.end()
    return e


def geburtsnamen(text: str, kandidaten=()) -> list:
    """Geburtsnamen hinter "geb.", "geb:", "geborene" und "Geburtsname" als Kandidaten {text, start, ende, gruppe,
    quelle}. Steht direkt davor ein Name (ein Kandidat aus `kandidaten` oder Vor- und Nachname derselben Zeile), ist
    gruppe "<Name> geb. <Geburtsname>" – dieselbe Person (analyse._Personen: gleicher Platzhalter, der Geburtsname
    zählt als weiterer Nachname dieser Person); ein Name davor, der noch kein Kandidat ist, kommt als Regel-Treffer
    dazu. Hinter "geb."/"geborene" steht der Geburtsname in derselben Zelle (bei einem Namen davor auch am Anfang der
    nächsten Zeile), hinter "Geburtsname" auch in der Nachbarzelle oder der nächsten Zeile."""
    aus = []
    starts_je_ende: dict = {}
    for k in kandidaten:
        if k.get("quelle") != GEBURTSNAME_QUELLE and 0 <= k.get("start", -1) < k.get("ende", -1):
            starts_je_ende.setdefault(k["ende"], []).append(k["start"])
    for m in _GEB_ETIKETT_RE.finditer(text):
        art = m.lastgroup
        zeilenanfang = text.rfind("\n", 0, m.start()) + 1
        davor = text[zeilenanfang:m.start()]
        if art == "geb" and m.group("geb") == "Geb" and not _NAME_DAVOR_RE.search(davor.rstrip(" \t")):
            continue                                  # "Geb. 3", "Geb. Ost": Gebäude/Gebühr am Zeilen-/Satzanfang
        if art == "geborene":
            wort_davor = re.search(r"([^\W\d_]+)[ \t]*$", davor)
            if wort_davor and wort_davor.group(1)[:1].islower():
                continue                              # "eine geborene Berlinerin": Eigenschaftswort
        # "Anna Weber geb." ⏎ "Schulz" (nur mit Name davor)
        luecke = _GEB_UMBRUCH_RE.match(text, m.end()) or _GEB_LUECKE_RE.match(text, m.end())
        n = _GEB_NAME_RE.match(text, luecke.end()) if luecke else None
        if n is None or not _geburtsname_wort(text, n.start(), n.end()) \
                or not kennungsformen.geburtsname_moeglich(text, n.start(), n.end()) \
                or kennungsformen.feld_etikett(text, n.start(), n.end()):
            continue                                  # Datum, Ort, Funktionswort, Feldbezeichner …
        if n.start() == m.end() and n.group(0).casefold() in _GEB_KUERZEL_TEIL:
            continue                                  # "GEB.DAT.", "geb.Tag": Feldkürzel
        s, e = n.start(), _geburtsname_ende(text, n.start(), n.end())
        person = _name_vor(text, m.start(), starts_je_ende)
        if person is None and (m.group("geb") == "Geb" or art in ("geborene", "gab") or "\n" in luecke.group(0)):
            continue                                  # "Standort Köln, Geb. Kantine", "Als geborener Kölner …"
        if art == "gab" and ("\n" in luecke.group(0) or not kennungsformen.WERT_ENDE_RE.match(text, e)):
            continue                                  # "… die ihm Frau Weber gab. Müller kam später"
        gruppe = None
        if person is not None:
            name = text[person[0]:person[1]]
            gruppe = f"{name} geb. {text[s:e]}"
            if person[0] not in starts_je_ende.get(person[1], ()):
                aus.append({"text": name, "start": person[0], "ende": person[1], "gruppe": gruppe})
        aus.append({"text": text[s:e], "start": s, "ende": e, "gruppe": gruppe, "quelle": GEBURTSNAME_QUELLE})
    # Feld-Etikett "Geburtsname", "Geb.-Name": dieselbe Regel „Etikett + Wert“ wie die Selbstkontrolle
    # (kennungsformen.geburtsname_hinter_etikett) – auch "Geburtsname, falls abweichend: …", in der Zelle daneben
    for m in kennungsformen.GEBURTSNAME_ETIKETT_RE.finditer(text):
        sp = kennungsformen.geburtsname_hinter_etikett(text, m, _GEB_NAME_RE)
        if sp is None or not _geburtsname_wort(text, sp.start, sp.ende):
            continue
        s, e = sp.start, _geburtsname_ende(text, sp.start, sp.ende)
        gruppe = None
        if sp.person is not None:                     # "Familienname (Geburtsname): Weber (Quarnstedt)"
            ps, pe = sp.person
            gruppe = f"{text[ps:pe]} geb. {text[s:e]}"
            if ps not in starts_je_ende.get(pe, ()):
                aus.append({"text": text[ps:pe], "start": ps, "ende": pe, "gruppe": gruppe})
        aus.append({"text": text[s:e], "start": s, "ende": e, "gruppe": gruppe, "quelle": GEBURTSNAME_QUELLE})
    return aus


# ----------------------------------------------------------------------
# Öffentliche Schnittstelle
# ----------------------------------------------------------------------
def finde_personen(text: str) -> list:
    """Personennamen per KI-Modell und Regeln.
    Liefert Kandidaten {text, start, ende, gruppe}; gruppe ist ein zusammengesetzter Vollname,
    wenn Bestandteile zusammengehören (Tabellenzeile Name/Vorname, Adressfenster über zwei
    Zeilen, Geburtsname "Anna Weber geb. Schulz"), sonst None. Ohne Modell greifen nur die Regeln."""
    kandidaten = _regel_kandidaten(text)
    # Werte hinter Sach-Etiketten (Beruf: Polier) sind nirgends ein Name — außer hinter Herr/Frau
    sachwerte = _sachwerte(text)

    def sachwert(k) -> bool:
        return (k["text"].casefold() in sachwerte
                and not _VORHER_ANREDE_RE.search(text[max(0, k["start"] - 12):k["start"]]))

    if sachwerte:
        kandidaten = [k for k in kandidaten if not sachwert(k)]
    nlp = lade_ner()
    if nlp is not None and text.strip():
        spannen = _ner_spannen(nlp, text) | _ner_kurzzeilen(nlp, text)
        spannen |= _ner_versalien_zeilen(nlp, text)
        for start, ende in sorted(_an_umbruechen_teilen(text, spannen)):
            if not _kandidat(kandidaten, text, start, ende):
                continue
            k = kandidaten[-1]
            if sachwerte and sachwert(k):
                kandidaten.pop()
                continue
            if " " in k["text"]:
                continue
            m = _KOMMA_VORNAME_RE.match(text, k["ende"])
            if (m and _plausibel(text, m.start(1), m.end(1)) and m.group(1).lower() not in _NAMENSENDE
                    and not _rang_kuerzel(m.group(1))
                    and not _VORHER_ANREDE_RE.search(text[max(0, k["start"] - 12):k["start"]])):
                # (hinter "Frau Krüger," beginnt ein Satz, keine Nachname-Vorname-Folge)
                voll = text[k["start"]:m.end(1)]
                kandidaten.append({"text": voll, "start": k["start"], "ende": m.end(1), "gruppe": voll})
                kandidaten.append({"text": m.group(1), "start": m.start(1), "ende": m.end(1), "gruppe": voll})
                k["gruppe"] = voll
    # Geburtsnamen hinter "geb."/"geborene"/"Geburtsname" – vorn, damit ihre Gruppe (Name davor) beim Zusammenfassen
    # gleicher Texte erhalten bleibt
    kandidaten = geburtsnamen(text, kandidaten) + kandidaten
    # gleiche Texte zusammenfassen (erste Position, erste Gruppe)
    gesehen, aus = {}, []
    for k in sorted(kandidaten, key=lambda k: k["start"]):
        schluessel = k["text"].casefold()
        if schluessel in gesehen:
            if gesehen[schluessel]["gruppe"] is None and k["gruppe"]:
                gesehen[schluessel]["gruppe"] = k["gruppe"]
            continue
        gesehen[schluessel] = k
        aus.append(k)
    return aus


def finde_personen_ner(text: str) -> set[str]:
    """Findet Personennamen (KI + Regeln). Leere Menge nur, wenn weder Modell noch Regeln
    etwas finden."""
    return {k["text"] for k in finde_personen(text)}
