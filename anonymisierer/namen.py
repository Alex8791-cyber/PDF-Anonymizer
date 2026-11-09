"""KI-Namenserkennung (spaCy) plus Regeln für Briefe, Formulare und Tabellen,
Plausibilitätsfilter gegen Fehlalarme und Stopplisten.

Öffentliche Namen: lade_ner, finde_personen_ner (Menge von Namenstexten, wie bisher),
finde_personen (Kandidaten mit Position und Zusammengehörigkeit), NAMEN_STOPPLISTE,
ner_fehler.
"""

import functools
import re

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
_STRASSENSUFFIX_RE = re.compile(r"(?i:straße|strasse|str\.|weg|allee|platz|gasse|ring|damm|ufer|markt|chaussee)$")
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
    """(bekannter Name?, Allerweltswort?, Diagnose/Beruf?) aus der Wissensbasis (ohne Wissensbasis: alles False)."""
    try:
        from . import wissen
    except Exception:  # pragma: no cover
        return False, False, False
    w = wort.strip(".,;:()[]\"'")
    if not w:
        return False, False, False
    try:
        name = wissen.ist_vorname(w) or wissen.ist_nachname(w)
        allerwelt = len(w) >= 4 and wissen.ist_allerweltswort(w)
        sache = bool(wissen.index("diagnosen").eintrag_fuer(w) or wissen.index("berufe").eintrag_fuer(w))
    except Exception:  # pragma: no cover - Wissensbasis beschädigt
        return False, False, False
    return name, allerwelt, sache


def _ist_sachwort(wort: str) -> bool:
    """Großgeschriebenes Nicht-Namenswort: Stopplisten-Eintrag (auch gebeugt: Mitversichertes, Kunden),
    Allerweltswort der Wissensbasis, Kompositum mit Sachwort-Endung (Schadenanzeige, Hundehalter) oder
    Adjektiv/Partizip (Betreuender, Gedruckt). Bei Bindestrich-Wörtern genügt ein Sachwort-Teil
    (Kraftfahrt-Haftpflicht, Kfz-Versicherungsschein). Bekannte Vor-/Nachnamen sind nie Sachwörter."""
    w = wort.lower().strip(".,;:()[]\"'")
    name, allerwelt, sache = _wissen_art(wort)
    if name and "-" not in w:
        return False
    if allerwelt or (sache and not name):
        return True
    for teil in (t for t in w.split("-") if t):
        if teil in NAMEN_STOPPLISTE or teil in _NAMENSENDE or teil in _FIRMENWOERTER or teil in _SACHWORT_STAEMME:
            return True
        for n in (1, 2):                      # Beugung abstreifen: Mitversichertes -> mitversicherte
            stamm = teil[:-n]
            if len(stamm) >= 4 and (stamm in NAMEN_STOPPLISTE or stamm in _SACHWORT_STAEMME):
                return True
        if any(teil.endswith(e) and len(teil) >= len(e) + 3 for e in _SACHWORT_ENDUNGEN):
            return True
        if _wissen_art(teil)[1]:
            return True
    return False


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
                or _STRASSENSUFFIX_RE.search(wort) or any(c.isdigit() for c in wort)):
            ende = start + m.start()
        else:
            break
    while ende > start and text[ende - 1] in " \t\n\r,.;:()[]\"'*":
        ende -= 1
    return (start, ende) if ende > start else None


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
    if re.search(r"-(?:ID|Nr|No|Id)\.?$", name, re.IGNORECASE) or _KFZ_RE.match(name):
        return False
    norm = re.sub(r"\s+", " ", name.lower()).strip()
    if regel and _kalendername(text, start, norm):
        return True                           # "Frau Mai", "Nachname: Freitag"
    if norm in NAMEN_STOPPLISTE or (norm in VERSICHERER_NAMEN and not mit_anrede):
        return False
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
    bereich = _bereinigen(text, start, ende)
    if bereich and _plausibel(text, *bereich, regel=regel):
        kandidaten.append({"text": text[bereich[0]:bereich[1]], "start": bereich[0],
                           "ende": bereich[1], "gruppe": gruppe})
        return True
    return False


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
# Öffentliche Schnittstelle
# ----------------------------------------------------------------------
def finde_personen(text: str) -> list:
    """Personennamen per KI-Modell und Regeln.
    Liefert Kandidaten {text, start, ende, gruppe}; gruppe ist ein zusammengesetzter Vollname,
    wenn Bestandteile zusammengehören (Tabellenzeile Name/Vorname, Adressfenster über zwei
    Zeilen), sonst None. Ohne Modell greifen nur die Regeln."""
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
                    and not _VORHER_ANREDE_RE.search(text[max(0, k["start"] - 12):k["start"]])):
                # (hinter "Frau Krüger," beginnt ein Satz, keine Nachname-Vorname-Folge)
                voll = text[k["start"]:m.end(1)]
                kandidaten.append({"text": voll, "start": k["start"], "ende": m.end(1), "gruppe": voll})
                kandidaten.append({"text": m.group(1), "start": m.start(1), "ende": m.end(1), "gruppe": voll})
                k["gruppe"] = voll
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
