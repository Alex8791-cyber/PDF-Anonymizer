"""Personenkontext – EINE Regel für die Erkennung (detektoren/wissen_kontext.py) und die Selbstkontrolle
(restrisiko.py), damit beide dieselben Rollen und dieselbe Form kennen (wie kennungsformen.py für Kennungen):

Familien- und Versichertenkontext für Geburtsdaten ohne Stichwort (Domänen-Durchsicht Runde 5): In
Familienversicherung, Kindertarif, Reise- und Gruppenversicherung stehen Geburtsdaten oft ohne "geb." direkt am Namen
("Kind 2: Bastian Leutgeb, 30.06.2018", "Kinder: Ben (02.05.2019) und Lotta (17.10.2021)", "Reisende: Kranich,
Detlef, 12.04.1969; …", die Kinderliste mit Tabstopps unter "Kinder:"). Ein Datum direkt am Namen ist dort ein
Geburtsdatum in jedem Alter – aber nur mit einer Familien-/Versichertenrolle in derselben Zeile vor dem Namen oder als
Überschrift des Blocks darüber und nicht als Behandlungsdatum: Titel, Praxis oder Klinik vor dem Namen UND ein
Behandlungstext hinter dem Datum ("Dr. Ute Kranzfelder, 03.11.2012: Meniskusoperation"). Eines allein genügt nicht:
"Versicherungsnehmer: Dr. Anna Weber, 12.03.1965" und "Max Mustermann, 02.09.1961: Antrag unterschrieben" nennen
Geburtsdaten.

Dazu weitere geteilte Personenregeln derselben Durchsicht: Namen in Wohn- und Nachbarschaftsangaben ("unseres
Nachbarn Felsberger", "EG links (Hackenschmied)"), Tierangaben, medizinische Fachwörter, Marken, Modelle und
Modellcodes (keine Personen – Treffer nur innerhalb einer Tabellenzelle), die Felder C.1.1/C.1.2 der
Zulassungsbescheinigung Teil I und Familiennamen einer GbR oder Erbengemeinschaft. Die USt-IdNr. von
Einzelkaufleuten, Inhabern und Freiberuflern (eine Angabe der Person) prüft kennungsformen.ust_id_der_firma
bzw. kennungsformen.einzelkaufmann_block – eine Regel für Erkennung und Selbstkontrolle.

Öffentliche Schnittstelle:
    FAMILIE_RE, FAMILIE_KOPF_RE, BEHANDLER_DAVOR_RE, BETRAG_IN_ZEILE_RE
    familien_kontext(text, zeilenanfang, name_start) -> bool
    familien_rolle_in_zeile(text, zeilenanfang, name_start) -> bool
    behandlungsdatum(davor_bis_name, text, datum_ende) -> bool
    wohn_kontext_namen(text) -> [(start, ende)], namensgestalt(wort, wissen) -> bool
    tierangabe(text, start) -> bool, medizinisch(wort, text, start, wissen) -> bool,
    fachwort_medizin(wort, wissen) -> bool, diagnose(wort, wissen) -> bool
    MODELLCODE_DANACH_RE, modellcode_danach(text, ende, wortgestalt) -> bool,
    sachnamen_stellen(zeile, wissen) -> [(start, ende)]
    zb1_seite(text) -> bool, zb1_personenfelder(text) -> [(start, ende)], zb1_anschrift_etiketten(text),
    zb1_anschriftfelder(text) -> [(start, ende)], ZB1_FELDCODE_RE
    gemeinschaft_namen(text, sachwort) -> [(start, ende)], personengruppe(wort) -> bool
    ORG_SPALTEN, organisations_spalte(text, pos) -> bool
"""

from __future__ import annotations

import re

from .kennungsformen import FUNKTIONSWOERTER

# Rollen der Familien- und Versichertenangaben (Groß-/Kleinschreibung wie im Formular: Substantive groß, die
# Wortgruppen "mitversicherte Person", "versicherte Kinder" auch klein)
_FAMILIE = (r"Kind(?:er)?|Sohn|Söhne|Tochter|Töchter|Enkel(?:in|kind|kinder)?|Ehe(?:frau|mann|gatte|gattin|partner|"
            r"partnerin)|Lebens(?:partner|partnerin|gefährte|gefährtin)|Familienangehörige[rn]?|"
            r"Familienmitglied(?:er)?|Angehörige[rn]?|(?:Mit)?[Rr]eisende[rsn]?|Reiseteilnehmer(?:in|innen)?|"
            r"Mitversicherte[rn]?|Mitzuversichernde[rn]?|Versicherte[rn]?|"
            r"(?:[Mm]it)?[Vv]ersicherte[sn]?[ \t]+(?:Person(?:en)?|Kind(?:er)?|Angehörige)|"
            r"[Mm]itzuversichernde[sn]?[ \t]+(?:Person(?:en)?|Kind(?:er)?)")
FAMILIE_RE = re.compile(rf"(?<![\wäöüß])(?:{_FAMILIE})(?![\wäöüß])")
# Überschrift eines Personenblocks: Rolle am Zeilenanfang mit Doppelpunkt ("Kinder:", "Mitzuversichernde Kinder:",
# "Versicherte Personen:", "Reisende: Kranich, Detlef, …;")
FAMILIE_KOPF_RE = re.compile(rf"^[ \t]*(?:\d{{1,2}}[.)][ \t]*)?(?:[^\W\d_]+[ \t]+)?(?:{_FAMILIE})(?![\wäöüß])"
                             r"[^:\n]{0,25}:", re.IGNORECASE)
# Titel, Praxis oder Klinik direkt vor dem Namen: ein Behandler ("Dr. Ute Kranzfelder, 03.11.2012: …")
BEHANDLER_DAVOR_RE = re.compile(r"(?:(?<![\wäöüß])(?:Dr|Prof|Dipl|Med|med|Dent|dent|PD)\.[\w.\-]*|Praxis|Klinik|"
                                r"Klinikum|Krankenhaus|Zahnarzt|Zahnärztin|Arzt|Ärztin|Fachärztin|Facharzt|"
                                r"Therapeut|Therapeutin)[ \t]*$")
# hinter dem Datum ein Behandlungs- oder Ereignistext ("03.11.2012: Meniskusoperation links")
_TEXT_DAHINTER_RE = re.compile(r"[ \t]*:[ \t]*[^\W\d_]")
# Betrag in der Zeile: eine Leistungs- oder Rechnungsliste, keine Personenliste
BETRAG_IN_ZEILE_RE = re.compile(r"\d,\d{2}(?!\d)[ \t]*(?:€|EUR)?|€|(?<![\wäöüß])EUR(?![\wäöüß])")
BLOCK_ZEILEN = 8                   # so viele Zeilen unter einer Überschrift gehören zum Personenblock


def familien_kontext(text: str, zeilenanfang: int, name_start: int) -> bool:
    """Steht vor dem Namen eine Familien-/Versichertenrolle – in derselben Zeile ("Kind 2: …", "unser Sohn …") oder
    als Überschrift über dem Block (bis BLOCK_ZEILEN Zeilen höher, ohne Leerzeile dazwischen)?"""
    if FAMILIE_RE.search(text, zeilenanfang, max(zeilenanfang, name_start)):
        return True
    ende = zeilenanfang - 1
    for _ in range(BLOCK_ZEILEN):
        if ende <= 0:
            return False
        anfang = text.rfind("\n", 0, ende) + 1
        zeile = text[anfang:ende]
        if not zeile.strip():
            return False
        if FAMILIE_KOPF_RE.match(zeile):
            return True
        ende = anfang - 1
    return False


def familien_rolle_in_zeile(text: str, zeilenanfang: int, name_start: int) -> bool:
    """Steht die Familien-/Versichertenrolle in derselben Zeile vor dem Namen (nicht nur als Überschrift)?"""
    return bool(FAMILIE_RE.search(text, zeilenanfang, max(zeilenanfang, name_start)))


# Name (oder sein Platzhalter) am Ende des Texts vor dem Datum, samt Trenner ("Dr. med. [PERSON A], ")
_NAME_AM_ENDE_RE = re.compile(r"(?:\[[^\]\n]{1,20}\]|(?:[^\W\d_][\w'’\-]*[ \t]+){0,3}[^\W\d_][\w'’\-]*)"
                              r"[ \t]*[,(*\-–]?[ \t]*$")


def behandler_vor_name(davor: str) -> bool:
    """Steht ein Titel, eine Praxis oder Klinik direkt vor dem Namen? davor: der Text bis zum Namen ("Dr. ") oder bis
    zum Datum ("Dr. [PERSON A], ") – ein Name bzw. Platzhalter am Ende wird übersprungen."""
    m = _NAME_AM_ENDE_RE.search(davor)
    return bool(BEHANDLER_DAVOR_RE.search(davor[:m.start()] if m else davor))


def behandlungsdatum(davor: str, text: str, datum_ende: int) -> bool:
    """Ist das Datum ein Behandlungsdatum: ein Behandler vor dem Namen (behandler_vor_name) UND ein Behandlungstext
    hinter dem Datum ("Dr. Ute Kranzfelder, 03.11.2012: Meniskusoperation links")? Eines allein genügt nicht – das
    Geburtsdatum einer Person mit Doktortitel ("Versicherungsnehmer: Dr. Anna Weber, 12.03.1965") und ein Datum mit
    Ereignis ("Max Mustermann, 02.09.1961: Antrag unterschrieben") bleiben Geburtsdaten."""
    return bool(_TEXT_DAHINTER_RE.match(text, datum_ende)) and behandler_vor_name(davor)


# ----------------------------------------------------------------------
# Rollen im Satz, auch gebeugt, und Wohnungslagen (Befund 50 der Durchsicht)
# ----------------------------------------------------------------------
# Begleiter einer Rolle im Satz: Artikel, Possessiva (auch im Genitiv: "unseres Nachbarn") und verschmolzene
# Präpositionen ("beim Nachbarn", "vom Vermieter")
BEGLEITER = (r"(?i:der|die|den|dem|des|ihr|ihre|ihren|ihrem|ihrer|ihres|unser|unsere|unseren|unserem|unserer|"
             r"unseres|mein|meine|meinen|meinem|meiner|meines|sein|seine|seinen|seinem|seiner|seines|beim|vom|zum|"
             r"zur|bei[ \t]+(?:der|dem)|von[ \t]+(?:der|dem))")
# Rollen rund um Wohnung und Grundstück; gebeugt mit -s/-n/-en ("des Mieters", "dem Nachbarn")
_WOHN_ROLLEN = (r"Nachbar|Nachbarin|Mieter|Mieterin|Untermieter|Untermieterin|Vermieter|Vermieterin|Eigentümer|"
                r"Eigentümerin|Miteigentümer|Miteigentümerin|Wohnungseigentümer|Wohnungseigentümerin|Bewohner|"
                r"Bewohnerin|Hausmeister|Hausmeisterin|Hausverwalter|Hausverwalterin")
WOHN_ROLLE_RE = re.compile(rf"(?<![\wäöüß]){BEGLEITER}[ \t]+(?:{_WOHN_ROLLEN})(?:s|n|en)?[ \t]+(?=[^\W\d_])")
# Wohnungs- und Stockwerkslage: "Bei Felsberger im 1. OG", "EG links (Hackenschmied)"
_LAGE = r"(?:\d{1,2}\.[ \t]*)?(?:OG|EG|DG|UG|KG|Obergeschoss|Erdgeschoss|Dachgeschoss|Untergeschoss|Stock|Etage)"
BEI_NAME_IN_LAGE_RE = re.compile(rf"(?<![\wäöüß])(?:[Bb]ei|[Bb]eim|[Vv]on)[ \t]+(?P<name>[^\W\d_][\w'’\-]*)[ \t]+"
                                 rf"(?:im|in[ \t]+der|in[ \t]+dem)[ \t]+{_LAGE}(?![\wäöüß])")
NAME_HINTER_LAGE_RE = re.compile(rf"(?<![\wäöüß]){_LAGE}(?:[ \t]+(?:links|rechts|Mitte|mitte|vorne|hinten|li\.|re\.))?"
                                 r"[ \t]*\((?P<name>[^\W\d_][\w'’\-]*)\)")
# typische Endungen von Familiennamen ("Felsberger", "Riedlinger", "Unterholzner", "Hackenschmied")
_NACHNAMEN_ENDUNG_RE = re.compile(r"(?:berger|burger|inger|ner|ger|ler|ter|mann|maier|meier|mayr|mayer|huber|hofer|"
                                  r"bauer|schmied|schmid|bach|stein|feld|ow|ski|sky|ić|vić|escu|oglu|oğlu|yan|ian)$")
# typische Endungen gewöhnlicher Substantive und Partizipien – kein Name
_SUBSTANTIV_ENDUNG_RE = re.compile(r"(?i)(?:ung|ungen|heit|keit|schaft|tion|ität|ismus|nis|tum|chen|ierte[nr]?|"
                                   r"ende[nr]?)$")


def namensgestalt(wort: str, wissen=None) -> bool:
    """Hat ein einzelnes unbekanntes Wort hinter einer Rolle die Gestalt eines Familiennamens: ein Nachname der
    Wissensbasis, oder großgeschrieben, ab sieben Buchstaben, mit einer typischen Endung von Familiennamen ("-berger",
    "-inger", "-ner", "-mann") – kein Allerwelts- oder Etikettwort, kein Ort, keine Substantiv-Endung? So bleiben
    "dem Nachbarn Wasser", "beim Nachbarn Regen", "dem Vermieter Bescheid" stehen."""
    w = (wort or "").strip(".,;:()")
    if len(w) < 3 or not w[:1].isupper() or w.isupper():
        return False
    if wissen is None:
        try:
            from . import wissen as wissen_modul
            wissen = wissen_modul
        except Exception:  # pragma: no cover - Wissensbasis fehlt
            return False
    try:
        if wissen.ist_nachname(w) and not wissen.ist_mehrdeutig(w):
            return True
        if (wissen.ist_allerweltswort(w) or wissen.ist_allowlist(w) or wissen.ist_ort(w) or wissen.ist_beruf(w)
                or wissen.ist_vorname(w) or wissen.ist_anrede_titel(w)):
            return False
        if any(wissen.index(f"etiketten_{art}").eintrag_fuer(w) is not None for art in wissen.ETIKETTEN_ARTEN):
            return False
    except Exception:  # pragma: no cover - Wissensbasis beschädigt
        return False
    return len(w) >= 7 and bool(_NACHNAMEN_ENDUNG_RE.search(w.casefold())) and not _SUBSTANTIV_ENDUNG_RE.search(w)


def wohn_kontext_namen(text: str) -> list:
    """(start, ende) einzelner Namen in Wohn- und Nachbarschaftsangaben: hinter einer Rolle im Satz ("unseres Nachbarn
    Felsberger", "Die Mieterin Riedlinger", "Beim Nachbarn Unterholzner"), hinter "bei/von … im 1. OG" ("Bei
    Felsberger im 1. OG") und in Klammern hinter einer Wohnungslage ("EG links (Hackenschmied)") – nur Wörter mit der
    Gestalt eines Familiennamens (namensgestalt)."""
    aus = []
    for m in WOHN_ROLLE_RE.finditer(text):
        w = re.match(r"[^\W\d_][\w'’\-]*", text[m.end():])
        if w and namensgestalt(w.group(0)):
            aus.append((m.end(), m.end() + w.end()))
    for regex in (BEI_NAME_IN_LAGE_RE, NAME_HINTER_LAGE_RE):
        for m in regex.finditer(text):
            if namensgestalt(m.group("name")):
                aus.append((m.start("name"), m.end("name")))
    return aus


# ----------------------------------------------------------------------
# Tiere: Abstammung und Name eines Tiers sind keine Personen (Befund 60 der Durchsicht)
# ----------------------------------------------------------------------
# Zeile mit der Abstammung eines Tiers ("Abstammung: v. Gribaldi a.d. Kassandra", "Vater: Sandro Hit / Muttervater:
# Donnerhall")
TIERZEILE_RE = re.compile(r"[ \t]*(?:Abstammung|Pedigree|Ahnentafel)(?![\wäöüß])"
                          r"|.*(?<![\wäöüß])Muttervater(?![\wäöüß])")
# Etikett mit dem Namen eines Tiers direkt vor der Stelle ("Name des Pferdes: Don Camillo", "Rufname des Hundes:")
TIERNAME_DAVOR_RE = re.compile(r"(?:Name|Rufname|Zuchtname)[ \t]+(?:des|der)[ \t]+(?:Pferdes|Hundes|Tieres|Katze|"
                               r"Katers|Ponys|Fohlens|Welpen|Haustiers)[ \t]*:[ \t]*(?:[^\W\d_][\w'’\-]*[ \t]+){0,2}$")


_ABSTAMMUNG_RE = re.compile(r"(?<![\wäöüß])(?:Abstammung|Pedigree|Ahnentafel)(?![\wäöüß])")


def tierangabe(text: str, start: int) -> bool:
    """Steht die Stelle in der Abstammung eines Tiers (hinter "Abstammung" in derselben Zeile, in einer Zeile mit
    "Muttervater") oder direkt hinter dem Namens-Etikett eines Tiers ("Name des Pferdes:")?"""
    zeilenanfang = text.rfind("\n", 0, start) + 1
    zeilenende = text.find("\n", start)
    zeile = text[zeilenanfang:len(text) if zeilenende < 0 else zeilenende]
    if _ABSTAMMUNG_RE.search(text, zeilenanfang, start) or TIERZEILE_RE.match(zeile):
        return True
    return bool(TIERNAME_DAVOR_RE.search(text, max(zeilenanfang, start - 40), start))


# Fachwörter der Medizin (Endungen) und Eponyme hinter "Morbus": keine Namen ("Baker-Zyste", "Alzheimer-Demenz",
# "Morbus Scheuermann", "Lumboischialgie"; Befund 15). Diese Endungen tragen keine Familiennamen. "-itis" und "-ose(n)"
# tragen auch Namen ("Petraitis", "Politis", "Klose", "Rose", "Ambrose"): ein Wort damit ist nur ein Fachwort, wenn es
# selbst in der Diagnosenliste der Wissensbasis steht ("Gastritis", "Arthrose"). Ein Vor- oder Nachname der
# Wissensbasis ist nie seiner Endung wegen ein Fachwort (Korpusmessung Runde 5).
MEDIZIN_ENDUNG_RE = re.compile(r"(?i)(?:algie|algien|fraktur|pathie|ektomie|ämie|zyste|syndrom|demenz|karzinom|plasie|"
                               r"sklerose|kontraktur|krankheit|erkrankung|tumor|lähmung)$")
MEDIZIN_ENDUNG_MEHRDEUTIG_RE = re.compile(r"(?i)(?:itis|ose|osen)$")
# "Morbus" vor dem Eponym; die Abkürzung "M." nur vor einer Diagnose der Liste ("M. Parkinson") – sonst ist "M." die
# Initiale eines Vornamens ("Ihr Ansprechpartner: M. Weber")
EPONYM_DAVOR_RE = re.compile(r"(?<![\wäöüß])Morbus[ \t]+$")
M_PUNKT_DAVOR_RE = re.compile(r"(?<![\wäöüß])M\.[ \t]*$")


def _frage(wissen, frage: str, wort: str):
    """Frage an die Wissensbasis (Modul anonymisierer.wissen oder None), Versalien in Titelform; Fehler: None."""
    if wissen is None or not wort:
        return None
    try:
        return getattr(wissen, frage)(wort.title() if wort.isupper() else wort)
    except Exception:
        return None


def diagnose(wort: str, wissen) -> bool:
    """Steht das Wort selbst als Eintrag in der Diagnosenliste der Wissensbasis ("Gastritis", "Parkinson")?"""
    if wissen is None or not wort:
        return False
    try:
        return wissen.index("diagnosen").eintrag_fuer(wort) is not None
    except Exception:
        return False


def fachwort_medizin(wort: str, wissen=None) -> bool:
    """Fachwort der Medizin nach seiner Endung, auch als Teil eines Bindestrich-Worts ("Baker-Zyste",
    "Lumboischialgie"; "Gastritis" nur mit der Diagnosenliste) – nie ein Vor- oder Nachname der Wissensbasis
    ("Klose", "Schmidt-Rose")?"""
    teile = [t for t in wort.split("-") if t]
    for t in (teile[1:] if len(teile) > 1 else teile):
        if _frage(wissen, "ist_vorname", t) or _frage(wissen, "ist_nachname", t):
            continue
        if MEDIZIN_ENDUNG_RE.search(t) or (MEDIZIN_ENDUNG_MEHRDEUTIG_RE.search(t) and diagnose(t, wissen)):
            return True
    return False


def medizinisch(wort: str, text: str = "", start: int = 0, wissen=None) -> bool:
    """Fachwort der Medizin (fachwort_medizin) oder Eponym hinter "Morbus" bzw. Diagnose hinter "M."
    ("M. Parkinson", nicht "M. Weber")?"""
    if fachwort_medizin(wort, wissen):
        return True
    if not text:
        return False
    a = max(0, start - 10)
    return bool(EPONYM_DAVOR_RE.search(text, a, start)) or (bool(M_PUNKT_DAVOR_RE.search(text, a, start))
                                                            and diagnose(wort, wissen))


# ----------------------------------------------------------------------
# Sachen: Marken, Modelle und Tierrassen der Wissensbasis und Modellcodes (Befunde 43, 60, 64 der Durchsicht)
# ----------------------------------------------------------------------
# Modellcode direkt hinter einem Wort IN DERSELBEN ZELLE ("Böckmann TPV", "Rossini 540", "Symo 10.0-3-M", "GSR 18V-55"):
# nur Leerzeichen dazwischen – ein Kürzel oder eine Zahl in der nächsten Tabellenzelle ("Tschernyschow ⇥⇥ PHV",
# "Szczepanski ⇥⇥ 540") gehört nicht zum Wort davor (Korpusmessung Runde 5). Gruppe "code": ein Kürzel in Versalien –
# ein Modellcode nur ohne Wortgestalt ("FAX" ist keiner; prüft der Aufrufer)
MODELLCODE_DANACH_RE = re.compile(r" +(?:(?P<code>[A-Z]{2,5})(?=[ \t,;.]|$)|[A-Z]{1,5}-?\d|"
                                  r"\d+[A-Za-z]{1,3}(?![\wäöüß])|\d{1,4}(?:[.,\-/]\d+)+|\d{3,4}(?![\d.,]))")
# Zahlen hinter einem Namen, die kein Modellcode sind: Datum ("Jendrik Wimmersberger 14.05.1979" – oft das
# Geburtsdatum), Uhrzeit, Betrag, Jahreszahl ("… 2019 erstmals") und Telefonnummer ("… 0151 22334455")
_KEIN_MODELLCODE_RE = re.compile(r"(?:0?[1-9]|[12]\d|3[01])[./](?:0?[1-9]|1[0-2])[./](?:\d{4}|\d{2})?(?!\d)"
                                 r"|\d{1,2}:\d{2}(?!\d)|\d{1,3}(?:\.\d{3})*,\d{2}(?!\d)|(?:19|20)\d{2}(?![\d.,\-])"
                                 r"|0\d")


_NUR_ZAHL_RE = re.compile(r"\d{3,4}(?![\d.,\-/\wäöüß])")


def modellcode_danach(text: str, ende: int, wortgestalt=None, woerter=()) -> bool:
    """Steht direkt hinter der Stelle (nur Leerzeichen dazwischen, dieselbe Zelle) ein Modellcode ("Rossini 540",
    "Symo 10.0-3-M", "GSR 18V-55", "Böckmann TPV")? Ein Kürzel in Versalien nur ohne Wortgestalt (wortgestalt(code)
    -> bool: "FAX" ist keiner); Datum, Uhrzeit, Betrag, Jahreszahl und Telefonnummer sind nie ein Modellcode – sonst
    verlöre ein Name davor seinen Personenbezug. Eine bloße Zahl ("4711") zählt nicht hinter einem Wort mit der
    Gestalt eines Familiennamens (woerter: die Wörter der Stelle; "Fokko Grübelhuber 4711"). Eine Regel für
    Erkennung (namen.py) und Selbstkontrolle."""
    m = MODELLCODE_DANACH_RE.match(text, ende)
    if m is None:
        return False
    if m.group("code") is not None:
        return not (wortgestalt is not None and wortgestalt(m.group("code")))
    pos = ende
    while pos < len(text) and text[pos] == " ":
        pos += 1
    if _KEIN_MODELLCODE_RE.match(text, pos):
        return False
    return not (_NUR_ZAHL_RE.match(text, pos) and any(namensgestalt(w) for w in woerter))


def sachnamen_stellen(zeile: str, wissen) -> list:
    """(start, ende) der Marken, Modelle und Tierrassen der Wissensbasis (Liste sachnamen) in einer Zeile – nur
    innerhalb einer Zelle: ein Treffer über einen Tabulator hinweg ("Seat ⇥⇥ Leon Wawrzyniak": Fahrzeug und Fahrer in
    zwei Spalten) zählt nicht."""
    if wissen is None:
        return []
    try:
        treffer = wissen.finde(zeile, "sachnamen")
    except Exception:
        return []
    return [(v.start, v.ende) for v in treffer if "\t" not in zeile[v.start:v.ende]]


# Zulassungsbescheinigung Teil I (Befund 32): die Feldcodes C.1.1 (Name oder Firma) und C.1.2 (Vornamen) sind dort
# Personen-Etiketten – auch für einen einzelnen Nachnamen in Versalien. Nur auf einer erkennbaren
# Zulassungsbescheinigung (das Wort oder mindestens drei ihrer Feldcodes am Zeilen- bzw. Zellenanfang), sonst sind
# "C.1.1" Gliederungsnummern
# ("C.1.1 Was ist versichert?").
_ZB1_WORT_RE = re.compile(r"(?i)zulassungsbescheinigung|fahrzeugschein")
_ZB1_CODE_RE = re.compile(r"(?m)(?:^|\t)[ \t]*(?:A|B|E|J|K|C[.,][ ]?1[.,][ ]?[1-3]|D[.,][ ]?[1-3]|2[.,][ ]?[12]|"
                          r"P[.,][ ]?[1-4]|F[.,][ ]?[12])[ \t]{2,}\S")
# Feldcode auch verlesen ("0.1.1", "O.1.2" für "C.1.1", "C.1.2")
ZB1_PERSONENFELD_RE = re.compile(r"(?m)(?:^|\t)[ \t]*[C0O][.,][ ]?[1lI][.,][ ]?(?P<feld>[12])[ \t:]+"
                                 r"(?:(?i:Name(?:[ \t]+oder[ \t]+Firmenname)?|Vorname\(?n?\)?)[ \t:]+)?"
                                 r"(?P<wert>[^\W\d_][^\t\n]*)")


def zb1_seite(text: str) -> bool:
    """Ist der Text (eine Seite oder ein Dokument) eine Zulassungsbescheinigung Teil I?"""
    if _ZB1_WORT_RE.search(text):
        return True
    return len({m.group(0).split()[0] for m in _ZB1_CODE_RE.finditer(text)}) >= 3


def zb1_personenfelder(text: str) -> list:
    """(start, ende) der Werte in den Feldern C.1.1 und C.1.2 einer Zulassungsbescheinigung Teil I (höchstens fünf
    Wörter bis zum Zellen- oder Zeilenende); ohne Zulassungsbescheinigung: keine."""
    if "C" not in text or not zb1_seite(text):
        return []
    aus = []
    for m in ZB1_PERSONENFELD_RE.finditer(text):
        wert = m.group("wert").rstrip(" .,;:")
        if not wert or len(wert.split()) > 5:
            continue
        aus.append((m.start("wert"), m.start("wert") + len(wert)))
    return aus


# Feld C.1.3 (Anschrift des Halters), auch verlesen ("0.1.3", "C,1.3"): auf einer Zulassungsbescheinigung ein
# Anschrift-Etikett – der Wert steht direkt dahinter bis zum Zellen- oder Zeilenende ("C.1.3  HOFMARK 7, 84140
# GANGKOFEN"); ein Straßenname ohne Straßenwort ("Hofmark 7") wird nur über dieses Etikett erkannt
ZB1_ANSCHRIFTFELD_RE = re.compile(r"(?m)(?:^|\t)[ \t]*(?P<code>[C0O][.,][ ]?[1lI][.,][ ]?3)(?![\w.,])"
                                  r"[ \t:]*(?:(?i:Anschrift)[ \t:]+)?(?P<wert>[^\t\n]*)")
# ein Feldcode der Zulassungsbescheinigung als ganzes Wort ("C.1.3", "0.1.1", "D.2.1", "P.1") – auf ihr ein
# Feld-Etikett, kein Rest eines geschwärzten Werts (Selbstkontrolle)
ZB1_FELDCODE_RE = re.compile(r"[A-Z0][.,][ ]?[1-9lI](?:[.,][ ]?[1-9lI])?")


def zb1_anschrift_etiketten(text: str) -> list:
    """(start, ende) der Feldcodes C.1.3 einer Zulassungsbescheinigung Teil I (Anschrift-Etikett); ohne
    Zulassungsbescheinigung: keine."""
    if "1" not in text or not zb1_seite(text):
        return []
    return [(m.start("code"), m.end("code")) for m in ZB1_ANSCHRIFTFELD_RE.finditer(text)]


def zb1_anschriftfelder(text: str) -> list:
    """(start, ende) der Werte im Feld C.1.3 einer Zulassungsbescheinigung Teil I (höchstens acht Wörter bis zum
    Zellen- oder Zeilenende); ohne Zulassungsbescheinigung oder ohne Wert: keine."""
    if "1" not in text or not zb1_seite(text):
        return []
    aus = []
    for m in ZB1_ANSCHRIFTFELD_RE.finditer(text):
        wert = m.group("wert").rstrip(" .,;:")
        if not wert.strip() or len(wert.split()) > 8:
            continue
        aus.append((m.start("wert"), m.start("wert") + len(wert)))
    return aus


# Spalten mit Organisationen (Befund 92): im Angebotsvergleich steht unter "Versicherer" der Versicherer, auch wenn sein
# Name aus Vor- und Nachnamen besteht ("Adam Riese", "Roland") – keine Person. Erkannt an der Kopfzelle derselben
# Spalte (gleicher Zellenplatz in einer Kopfzeile mit gleich vielen Zellen) bis zu ORG_SPALTE_ZEILEN Zeilen höher,
# ohne Leerzeile dazwischen; Schlüssel-Wert-Felder ("Versicherer: …") behandeln die Sach-Etiketten der Namensregeln
ORG_SPALTEN = ("Versicherer", "Versicherungsgesellschaft", "Gesellschaft", "Anbieter", "Risikoträger",
               "Vorversicherer", "Bank", "Kreditinstitut", "Krankenkasse")
_ORG_SPALTE_RE = re.compile(r"(?i)(?:" + "|".join(ORG_SPALTEN) + r")[ \t]*:?")
ORG_SPALTE_ZEILEN = 40


def _zellen(zeile: str) -> list:
    """(start, ende) der nicht leeren Zellen einer Zeile (Trenner: Tabulator)."""
    return [(m.start(), m.end()) for m in re.finditer(r"[^\t]+", zeile) if zeile[m.start():m.end()].strip()]


def organisations_spalte(text: str, pos: int) -> bool:
    """Steht die Stelle pos in einer Tabellenspalte, deren Kopfzelle eine Organisation ankündigt ("Versicherer" ⏎
    "Adam Riese")? Dieselbe Regel für die Erkennung (namen.py, wissen_namen) und die Selbstkontrolle."""
    za = text.rfind("\n", 0, pos) + 1
    ze = text.find("\n", pos)
    zeile = text[za:len(text) if ze < 0 else ze]
    if "\t" not in zeile:
        return False
    zellen = _zellen(zeile)
    nr = next((i for i, (a, b) in enumerate(zellen) if a <= pos - za < b), None)
    if nr is None:
        return False
    ende = za - 1
    for _ in range(ORG_SPALTE_ZEILEN):
        if ende <= 0:
            return False
        anfang = text.rfind("\n", 0, ende) + 1
        oben = text[anfang:ende]
        if not oben.strip():
            return False                     # Leerzeile: die Tabelle ist zu Ende
        kopf = _zellen(oben)
        if len(kopf) == len(zellen):
            a, b = kopf[nr]
            if _ORG_SPALTE_RE.fullmatch(oben[a:b].strip()):
                return True
        ende = anfang - 1
    return False


# Gesellschaften bürgerlichen Rechts und Gemeinschaften natürlicher Personen (Befund 63): der Name davor bzw. dahinter
# ist der Familienname der Gesellschafter – auch unbekannt ("Felsberger GbR", "Erbengemeinschaft Riedlinger").
# Fantasie- oder Objektnamen ("Sonnenhof GbR") werden dabei mitgeschwärzt; das ist harmlos.
_NAMENSWORT = r"[A-ZÄÖÜ][a-zäöüß'’]+(?:-[A-ZÄÖÜ][a-zäöüß'’]+)?"
# Lücke zwischen den Wörtern: Leerzeichen oder ein einzelner Tabulator – nie der Spaltentrenner "\t\t" (Befund 91:
# "Grundstücksgemeinschaft ⇥⇥ Sonnleitenstraße" ist Personen- und Anschriftspalte, kein Name)
_LUECKE = r"(?:[ ]|(?<!\t)\t(?!\t))"
_GBR_RE = re.compile(rf"(?<![\w\-])(?P<name>{_NAMENSWORT}(?:{_LUECKE}*(?:&|und|\+){_LUECKE}*{_NAMENSWORT})?)"
                     rf"{_LUECKE}+GbR(?![\wäöüß])")
# Gemeinschaften natürlicher Personen: das Wort davor kündigt Familiennamen an ("Erbengemeinschaft Ruhstorfer")
_PERSONENGRUPPE = r"(?:Erben|Grundstücks|Bruchteils)gemeinschaft"
_PERSONENGRUPPE_RE = re.compile(_PERSONENGRUPPE)
_GEMEINSCHAFT_RE = re.compile(rf"(?<![\w\-]){_PERSONENGRUPPE}{_LUECKE}+(?P<name>{_NAMENSWORT})(?![\wäöüß])")


def personengruppe(wort: str) -> bool:
    """Ist das Wort eine Gemeinschaft natürlicher Personen ("Erbengemeinschaft", "Grundstücksgemeinschaft")? Dahinter
    stehen Familiennamen – auch in der nächsten Zeile einer Tabellenzelle (struktur_tabelle, Befund 84)."""
    return bool(_PERSONENGRUPPE_RE.fullmatch(wort or ""))


# Artikel, Pronomen und Sachwörter vor "GbR" ("Die GbR besteht …", "Ihre GbR", "Praxis GbR")
_KEIN_GESELLSCHAFTER = FUNKTIONSWOERTER | frozenset({"diese", "dieser", "jede", "jeder", "welche", "gesamte", "haus",
                                                     "praxis", "kanzlei", "firma", "gesellschaft", "neue", "alte"})


def gemeinschaft_namen(text: str, sachwort) -> list:
    """(start, ende) der Familiennamen vor "GbR" bzw. hinter "Erbengemeinschaft"/"Grundstücksgemeinschaft";
    sachwort(wort) -> bool schließt Allerweltswörter, Orte und Organisationen aus."""
    aus = []
    for regex in (_GBR_RE, _GEMEINSCHAFT_RE):
        for m in regex.finditer(text):
            woerter = [w for w in re.findall(r"[^\W\d_][\w'’\-]*", m.group("name")) if w != "und"]
            if not woerter or any(w.casefold() in _KEIN_GESELLSCHAFTER or sachwort(w) for w in woerter):
                continue
            aus.append((m.start("name"), m.end("name")))
    return aus
