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
    KALENDERWOERTER, kalenderwort_als_datum(text, start, ende) -> bool
"""

from __future__ import annotations

import functools
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


def kinderlisten_vorname(wort: str, wissen) -> bool:
    """Kann ein einzelnes Wort am Anfang eines Listeneintrags unter "Kinder:" ein Vorname sein ("- Juni, 30.06.2022",
    "Paris, 02.02.2011", "Dakota (7)")? Ein Vorname der Wissensbasis, ein Monat oder Wochentag, ein Ort oder ein
    unbekanntes Wort – kein Allerwelts-, Rollen-, Anrede- oder Etikettwort (Nachprüfung NP-06/Ü-NP-17). Eine Regel für
    Erkennung und Selbstkontrolle."""
    w = (wort or "").strip(".,;:()")
    if len(w) < 2 or not w[0].isupper() or any(c.isdigit() for c in w):
        return False
    if w.casefold() in KALENDERWOERTER:
        return True
    if wissen is None:
        return False
    try:
        if FAMILIE_RE.fullmatch(w) or wissen.ist_anrede_titel(w) or wissen.ist_allowlist(w) \
                or wissen.index("etiketten_person").eintrag_fuer(w) is not None:
            return False
        if wissen.ist_vorname(w) or wissen.ist_ort(w):
            return True
        return not wissen.ist_allerweltswort(w)
    except Exception:  # pragma: no cover - Wissensbasis beschädigt
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


# Berufsbezeichnung im Satz mit Begleiter und dahinter ein Name ("Der Glaser Eibl hat …", "unser Monteur Zwickl kam",
# "die Gutachterin Hechenberger, …"): der Name ist das Wort direkt hinter dem Beruf, gefolgt von einem kleingeschriebenen
# Wort, einem Satzzeichen oder dem Zeilenende
_BERUF_IM_SATZ_RE = re.compile(rf"(?<![\wäöüß]){BEGLEITER}[ \t]+(?P<beruf>[A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)?)"
                               rf"[ \t]+(?P<name>[A-ZÄÖÜ][a-zäöüß'’]+(?:-[A-ZÄÖÜ][a-zäöüß'’]+)?)"
                               r"(?=[ \t]+[a-zäöüß]|[ \t]*[,.;:!?)]|[ \t]*$)", re.MULTILINE)
_KALENDER = frozenset("""montag dienstag mittwoch donnerstag freitag samstag sonnabend sonntag januar februar märz april
mai juni juli august september oktober november dezember""".split())
KALENDERWOERTER = _KALENDER
# Wochentag oder Monat als Datumsangabe: hinter einer Zeitangabe ("am", "ab", "bis", "im", "jeden", "nächsten" …), einer
# Tageszahl ("12. Mai") oder einem Datums-Etikett ("Schadentag: Freitag, 06.11.2026", "Gesendet: Mittwoch, 18. November"),
# ein Monat vor einer Jahreszahl ("Mai 2025"), in einer Spanne ("Montag bis Freitag") oder als "Wochentag, den Datum".
# Ein Datum allein dahinter belegt nichts: "Gesprächspartner: Freitag, 14.11.2026" und "Mai, 12.03.2026 – Rückruf …"
# sind ein Name mit Datum (Nachprüfung NP-01)
_KALENDER_DAVOR_RE = re.compile(
    r"(?:(?<![\wäöüß])(?i:am|ab|bis|seit|jeden|jede[mn]|jeweils|nächste[mnrs]?|naechste[mnrs]?|übernächste[mnrs]?|"
    r"kommende[mnrs]?|letzte[mnrs]?|vergangene[mnrs]?|diese[mnrs]|vorige[mnrs]?|im|anfang|ende|mitte|zum|vom|"
    r"außer|ausser)"
    r"|(?<![\d.])\d{1,2}\.)[ \t]+$"
    r"|(?i:datum|tag|termin|zeitpunkt|frist|beginn|ablauf|gesendet|versendet|sent|date|erstellt|geändert|eingang)"
    r"[ \t]*:[ \t]*$")
_KALENDER_WORT = r"(?i:" + "|".join(sorted(_KALENDER)) + r")"
_KALENDER_SPANNE_RE = re.compile(r"[ \t]*(?:bis|-|–)[ \t]*" + _KALENDER_WORT + r"(?![\wäöüß])")
_KALENDER_SPANNE_DAVOR_RE = re.compile(r"(?<![\wäöüß])" + _KALENDER_WORT + r"[ \t]*(?:bis|-|–)[ \t]*$")
# Aufzählung von Tagen ("am Montag, Mittwoch und Freitag"): das erste Glied trägt die Zeitangabe
_KALENDER_AUFZAEHLUNG_DAVOR_RE = re.compile(r"(?<![\wäöüß])(" + _KALENDER_WORT + r")[ \t]*(?:,|und|oder|sowie)[ \t]*$")
_MONATE = frozenset("januar februar märz april mai juni juli august september oktober november dezember".split())
_KALENDER_JAHR_RE = re.compile(r"[ \t]+\d{4}(?!\d)")
_WOCHENTAG_DEN_RE = re.compile(r"[ \t]*,?[ \t]*den[ \t]+\d{1,2}\.")


def kalenderwort_als_datum(text: str, start: int, ende: int) -> bool:
    """Steht das Wort text[start:ende] – ein Wochentag oder Monat – als Datumsangabe da ("am Freitag, 12.03.2025",
    "Montag bis Freitag", "im Mai 2025", "12. Mai", "Schadentag: Freitag, 06.11.2026", "am Montag und Freitag")? Dann
    ist es kein Familienname ("Freitag", "Mai"): die Weitergabe eines solchen Namens überspringt diese Stelle. Ein Datum
    dahinter allein genügt nicht ("Gesprächspartner: Freitag, 14.11.2026", "Mai, 12.03.2026 – Rückruf …": ein bekannter
    Name mit Datum, Nachprüfung NP-01)."""
    wort = text[start:ende].casefold()
    if wort not in _KALENDER:
        return False
    zeilenanfang = text.rfind("\n", 0, start) + 1
    s = start
    for _ in range(6):                                # Aufzählung zurück bis zu ihrem ersten Glied
        davor = text[max(zeilenanfang, s - 40):s]
        if _KALENDER_DAVOR_RE.search(davor) or _KALENDER_SPANNE_DAVOR_RE.search(davor):
            return True
        m = _KALENDER_AUFZAEHLUNG_DAVOR_RE.search(davor)
        if m is None:
            break
        s = max(zeilenanfang, s - 40) + m.start(1)
    if _KALENDER_SPANNE_RE.match(text, ende):
        return True                                   # "Montag bis Freitag"
    if wort in _MONATE and _KALENDER_JAHR_RE.match(text, ende):
        return True                                   # "Mai 2025"
    return wort not in _MONATE and bool(_WOCHENTAG_DEN_RE.match(text, ende))     # "Freitag, den 14.03."


def _beruf_gebeugt(wissen, wort: str) -> bool:
    """Berufsbezeichnung der Wissensbasis, auch gebeugt ("des Glasers", "dem Monteur", "den Gutachtern")?"""
    for endung in ("", "s", "es", "n", "en"):
        if endung and not wort.endswith(endung):
            continue
        kern = wort[:len(wort) - len(endung)] if endung else wort
        if len(kern) >= 4 and wissen.ist_beruf(kern):
            return True
    return False


def _name_hinter_beruf(wissen, wort: str) -> bool:
    """Ist ein großgeschriebenes Wort hinter einer Berufsbezeichnung ein Name: ein Nachname der Wissensbasis oder ein
    unbekanntes Wort – kein Allerwelts-, Orts-, Berufs-, Vor-, Anrede-, Etikett-, Kalender- oder Sachwort (Marke,
    Modell), keine Substantiv-Endung, kein zusammengesetztes Hauptwort ("Notdienst")?"""
    if len(wort) < 3 or len(wort) > 40 or wort.isupper() or wort.casefold() in _KALENDER:
        return False                                   # über 40 Zeichen ist kein Name (lineare Laufzeit, Ü-NP-14)
    try:
        if wissen.ist_nachname(wort) and not wissen.ist_mehrdeutig(wort):
            return True
        if (wissen.ist_allerweltswort(wort) or wissen.ist_allowlist(wort) or wissen.ist_ort(wort)
                or wissen.ist_beruf(wort) or wissen.ist_vorname(wort) or wissen.ist_anrede_titel(wort)
                or wissen.index("sachnamen").finde(wort)):
            return False
        if any(wissen.index(f"etiketten_{art}").eintrag_fuer(wort) is not None for art in wissen.ETIKETTEN_ARTEN):
            return False
        for i in range(max(3, len(wort) - 30), len(wort) - 3):    # "Notdienst", "Kundendienst": Kompositum
            rest = wort[i].upper() + wort[i + 1:]
            if not wort[i].isupper() and len(rest) >= 4 and wissen.ist_allerweltswort(rest):
                return False
    except Exception:  # pragma: no cover - Wissensbasis beschädigt
        return False
    return not _SUBSTANTIV_ENDUNG_RE.search(wort)


def beruf_kontext_namen(text: str, wissen=None) -> list:
    """(start, ende) eines Namens direkt hinter einer Berufsbezeichnung im Satz ("Der Glaser Eibl hat bereits ein
    Angebot erstellt", "unser Monteur Zwickl kam um 8 Uhr"): Begleiter (Artikel, Possessiv) + Beruf der Wissensbasis +
    ein Wort, das ein Name sein kann (_name_hinter_beruf) – auch ein kurzer unbekannter Familienname. Erkennung und
    Selbstkontrolle nutzen dieselbe Regel."""
    if not text:
        return []
    if wissen is None:
        try:
            from . import wissen as wissen_modul
            wissen = wissen_modul
        except Exception:  # pragma: no cover - Wissensbasis fehlt
            return []
    aus = []
    for m in _BERUF_IM_SATZ_RE.finditer(text):
        try:
            if not _beruf_gebeugt(wissen, m.group("beruf")):
                continue
        except Exception:  # pragma: no cover - Wissensbasis beschädigt
            return []
        if _name_hinter_beruf(wissen, m.group("name")):
            aus.append((m.start("name"), m.end("name")))
    return aus


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


@functools.lru_cache(maxsize=128)
def _tierzeile(zeile: str) -> tuple:
    """(Ende des ersten "Abstammung"/"Pedigree" in der Zeile oder -1, Zeile der Abstammung bzw. mit "Muttervater") –
    je Zeile einmal (Laufzeit L2: lange Einzelzeilen mit vielen Kandidaten)."""
    m = _ABSTAMMUNG_RE.search(zeile)
    return (m.end() if m else -1), bool(TIERZEILE_RE.match(zeile))


def tierangabe(text: str, start: int) -> bool:
    """Steht die Stelle in der Abstammung eines Tiers (hinter "Abstammung" in derselben Zeile, in einer Zeile mit
    "Muttervater") oder direkt hinter dem Namens-Etikett eines Tiers ("Name des Pferdes:")?"""
    zeilenanfang = text.rfind("\n", 0, start) + 1
    zeilenende = text.find("\n", start)
    zeile = text[zeilenanfang:len(text) if zeilenende < 0 else zeilenende]
    abstammung_ende, tierzeile = _tierzeile(zeile)
    if tierzeile or 0 <= abstammung_ende <= start - zeilenanfang:
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


# Sachbeleg für eine Marke, ein Modell oder eine Rasse in derselben Zelle (Gegenprüfung LK-02): Fahrzeug-, Geräte-,
# Werkzeug-, Uhren-, Elektronik- und Tierwörter sowie Sach-Etiketten ("Hersteller", "Marke", "Rasse")
SACHWORT_RE = re.compile(
    r"(?i)(?<![\wäöüß])(?:pkw|lkw|kfz|krad|kraftrad|motorrad|mofa|moped|roller|motorroller|leichtkraftrad|"
    r"kleinkraftrad|quad|wohnmobil|wohnwagen|caravan|anh(?:ä|ae)nger|transporter|fahrzeug(?:e|s|typ)?|auto|"
    r"fahrrad|e-bike|ebike|pedelec|marke|hersteller|modell|typ|fabrikat|gerät(?:e|s)?|haushaltsgerät|"
    r"waschmaschine|waschtrockner|trockner|wäschetrockner|geschirrspüler|spülmaschine|kühlschrank|gefrierschrank|"
    r"herd|backofen|kochfeld|dunstabzugshaube|mikrowelle|kaffeevollautomat|kaffeemaschine|staubsauger|heizung|"
    r"therme|gastherme|heizkessel|kessel|wärmepumpe|boiler|durchlauferhitzer|klimaanlage|säge|kettensäge|"
    r"motorsäge|rasenmäher|mähroboter|bohrmaschine|bohrhammer|akkuschrauber|werkzeug|uhr|armbanduhr|"
    r"chronograph|fernseher|laptop|notebook|smartphone|handy|tablet|kamera|drucker|grill|gasgrill|hund|hündin|"
    r"rüde|welpe|katze|pferd|pony|stute|fohlen|rasse|tierart|mischling)(?![\wäöüß])")
# Grußformel über einem Unterschriftsblock ("Mit freundlichen Grüßen", "Beste Grüße aus Prien", "Hochachtungsvoll",
# "Mit herzlichem Gruß", "Danke und Grüße") – irgendwo in der Zeile
GRUSS_RE = re.compile(r"(?i)(?<![\wäöüß])(?:mit[ \t]+(?:freundlichen|besten|herzlichen|lieben|vielen|kollegialen|"
                      r"verbindlichen|sonnigen)[ \t]+gr[üu](?:ß|ss)en|mit[ \t]+(?:freundlichem|herzlichem|bestem|"
                      r"liebem|kollegialem)[ \t]+gru(?:ß|ss)|"
                      r"(?:freundliche|beste|viele|herzliche|liebe|schöne|sonnige|kollegiale)[ \t]+gr[üu](?:ß|ss)e|"
                      r"(?:danke|vielen[ \t]+dank|besten[ \t]+dank)(?:[ \t]+und|[ \t]*,)[ \t]+"
                      r"(?:viele[ \t]+|beste[ \t]+|liebe[ \t]+)?gr[üu](?:ß|ss)e|"
                      r"hochachtungsvoll|mfg)(?![\wäöüß])")
# kurze Grußformel als ganze Zeile ("Gruß", "Grüße", "Freundlichst", "Herzlichst", "Servus", "Tschüss", "LG") – nicht
# mitten im Satz ("Gruß an die Familie"; Nachprüfung NP-03)
GRUSS_ZEILE_RE = re.compile(r"(?i)^[ \t]*(?:gru(?:ß|ss)|gr[üu](?:ß|ss)e|freundlichst|herzlichst|servus|tsch[üu]ss?|"
                            r"ciao|bis[ \t]+bald|lg|vg|best[ \t]+regards|kind[ \t]+regards|regards)[ \t]*[,.!]?[ \t]*$")


def ist_gruss_zeile(zeile: str) -> bool:
    """Enthält die Zeile eine Grußformel (GRUSS_RE) oder ist sie eine kurze Grußformel (GRUSS_ZEILE_RE)?"""
    return bool(GRUSS_RE.search(zeile or "") or GRUSS_ZEILE_RE.match(zeile or ""))


def _zelle_um(text: str, start: int, ende: int) -> tuple:
    """(Anfang, Ende) der Tabellenzelle bzw. Zeile um [start, ende) – Zellen trennt ein Tabulator."""
    a = max(text.rfind("\n", 0, start), text.rfind("\t", 0, start)) + 1
    b = len(text)
    for zeichen in ("\n", "\t"):
        k = text.find(zeichen, ende)
        if 0 <= k < b:
            b = k
    return a, b


def sachbeleg(text: str, start: int, ende: int, wissen=None, direkt: bool = False) -> bool:
    """Belegt die Zelle um [start, ende) eine Sache: ein Sachwort ("Waschmaschine Miele", "Mofa Simson", "Rasse:
    Holsteiner") außerhalb der Stelle oder eine Marke, ein Modell bzw. eine Rasse der Wissensbasis, die über die Stelle
    hinausreicht ("Jack Russell Terrier")? Mit direkt=True (an einem Ort für Personen: Personenspalte, Unterschrift,
    Personen-Etikett) zählt ein Sachwort nur direkt davor oder dahinter, ohne Satzzeichen dazwischen ("Waschmaschine
    Miele", "Miele Waschmaschine") – in "Krups (Geschirrspüler)" und "Opel, Transporter-Fahrer" beschreibt es den
    Vorgang der Person (Nachprüfung NP-03)."""
    a, b = _zelle_um(text, start, ende)
    for m in SACHWORT_RE.finditer(text, a, b):
        if m.end() <= start or m.start() >= ende:
            if not direkt:
                return True
            zwischen = text[m.end():start] if m.end() <= start else text[ende:m.start()]
            if not zwischen.strip(" "):
                return True
    for x, y in sachnamen_stellen(text[a:b], wissen):
        if a + x <= start and ende <= a + y and (y - x) > (ende - start):
            return True
    return False


# Personenwort direkt vor einem Namen im Satz ("mit Kollege Hengst", "unser Nachbar Wallach", "die Zeugin Grundig"):
# das Wort dahinter ist eine Person, auch wenn es zugleich Marke, Modell oder Rasse ist (Nachprüfung NP-03)
PERSONENWORT_DAVOR_RE = re.compile(
    r"(?<![\wäöüß])(?:Kollegen?|Kollegin|Nachbarn?|Nachbarin|Zeugen?|Zeugin|Mitarbeiter(?:in)?|Chef(?:in)?|Kunden?|"
    r"Kundin|Mieter(?:in)?|Vermieter(?:in)?|Sachbearbeiter(?:in)?|Monteur(?:in)?|Hausmeister(?:in)?|Schwager|"
    r"Schwägerin|Onkel|Tante|Cousine?|Neffe|Nichte|Ehemann|Ehefrau|Sohn|Tochter|Vater|Mutter|Bruder|Schwester|"
    r"Opa|Oma|Enkel(?:in)?|Patient(?:in)?|Mandant(?:in)?|Vermittler(?:in)?|Makler(?:in)?|Gutachter(?:in)?|"
    r"Anrufer(?:in)?|Unfallgegner(?:in)?|Geschädigte[rn]?)[ \t]+$")
# schwächerer Hinweis im Satz: "laut Wallach ist …" – für die Selbstkontrolle (Verdacht statt Schwärzung)
PERSON_LAUT_DAVOR_RE = re.compile(r"(?i)(?<![\wäöüß])(?:laut|lt\.|gemäß|nach[ \t]+angaben[ \t]+von)[ \t]+$")


# Organisationswort in der Zeile ("Neff Kundendienst Süd", "Ihr Miele Team", "Vaillant Werkskundendienst"): eine Marke
# darin ist die Firma, die grüßt oder liefert – kein Familienname (Nachprüfung Ü-NP-13)
ORG_ZEILE_RE = re.compile(r"(?i)(?<![\wäöüß])(?:[\wäöüß]*kundendienst|kundenservice|[\wäöüß]*service|team|center|zentrale|"
                          r"filiale|niederlassung|hotline|vertrieb|abteilung|werkstatt|autohaus|support|shop|store)"
                          r"(?![\wäöüß])")


def org_zeile(text: str, pos: int) -> bool:
    """Steht in der Zeile bzw. Zelle um pos ein Organisationswort (ORG_ZEILE_RE)?"""
    a, b = _zelle_um(text, pos, pos)
    return bool(ORG_ZEILE_RE.search(text, a, b))


def person_im_satz(text: str, start: int) -> bool:
    """Steht direkt vor der Stelle ein Personenwort ("Kollege", "Nachbarin", "Zeuge" …, PERSONENWORT_DAVOR_RE)?"""
    za = text.rfind("\n", 0, start) + 1
    return bool(PERSONENWORT_DAVOR_RE.search(text[max(za, start - 40):start]))


def sach_spalte(text: str, pos: int, zeilen: int = 40) -> bool:
    """Steht die Stelle in einer Tabellenspalte, deren Kopf ein Sachwort ist ("Hersteller", "Marke", "Gerät",
    "Fahrzeug", "Rasse")? Dann ist eine Marke darin eine Sache, auch ohne Sachwort in der Zelle."""
    za = text.rfind("\n", 0, pos) + 1
    ze = text.find("\n", pos)
    zeile = text[za:len(text) if ze < 0 else ze]
    if len(re.split(r"\t+", zeile)) < 2:
        return False
    k = len(re.split(r"\t+", text[za:pos])) - 1
    a = za
    for _ in range(zeilen):
        if a == 0:
            return False
        b = a - 1
        a = text.rfind("\n", 0, b) + 1
        kopf = re.split(r"\t+", text[a:b])
        if len(kopf) < 2 or k >= len(kopf):
            continue
        if any(c.isdigit() for c in text[a:b]):
            continue                                     # Datenzeile
        return bool(SACHWORT_RE.fullmatch(kopf[k].strip().rstrip(":").strip()))
    return False


def im_grussblock(text: str, pos: int) -> bool:
    """Steht die Stelle in einer kurzen Zeile höchstens drei Zeilen unter einer Grußformel (Unterschriftsblock: "Mit
    freundlichen Grüßen" ⏎ "Neff") oder in derselben Zeile hinter ihr?"""
    za = text.rfind("\n", 0, pos) + 1
    ze = text.find("\n", pos)
    ze = len(text) if ze < 0 else ze
    if len(text[za:ze].split()) > 6:
        return False
    if GRUSS_RE.search(text, za, pos):
        return True
    a = za
    for _ in range(5):                                   # Name unter Firma, Abteilung und Sachbearbeitung (NP-03)
        if a == 0:
            return False
        b = a - 1
        a = text.rfind("\n", 0, b) + 1
        zeile = text[a:b]
        if ist_gruss_zeile(zeile):
            return True
        if len(zeile.split()) > 8:
            return False                                 # Fließtext dazwischen: kein Unterschriftsblock
    return False


def _etikett_art(wissen, zelle: str):
    """Art des Etiketts, das die ganze Zelle ist ("Kunde", "Name:", "Fahrzeug"), oder None."""
    z = zelle.strip().rstrip(":").strip()
    if not z or len(z) > 40 or any(c.isdigit() for c in z):
        return None
    for art in getattr(wissen, "ETIKETTEN_ARTEN", ()):
        try:
            if wissen.index(f"etiketten_{art}").eintrag_fuer(z) is not None:
                return art
        except Exception:
            return None
    return None


_KOPFWORT_RE = re.compile(r"[A-ZÄÖÜ][^\d,;:()\[\]/]*")


def kopf_mit_personen_etikett(zellen: list, arten: list) -> bool:
    """Kopfzeile einer Tabelle mit genau einem Etikett, einem Personen-Etikett ("Anrufer ⇥⇥ Anliegen ⇥⇥ Rückruf
    bis"): mindestens drei Zellen, die übrigen kurze Kopfwörter (höchstens drei Wörter, groß beginnend, ohne Ziffern,
    Satzzeichen oder Platzhalter) – wie die Stehlgutliste mit einem Kennungs-Etikett (Domänen-Befund 48). Sonst
    zählte nur eine Zeile mit zwei Etiketten als Kopf, und ab der zweiten Datenzeile stand eine Marke oder ein
    unbekannter Familienname in der Spalte "Anrufer" außerhalb jeder Personenspalte (Nachprüfung A, Probe m02)."""
    if not 3 <= len(zellen) <= 8 or [a for a in arten if a] != ["person"]:
        return False
    for zelle, art in zip(zellen, arten):
        t = zelle.strip()
        if art is None and (len(t.split()) > 3 or not _KOPFWORT_RE.fullmatch(t)):
            return False
    return True


def personen_spalte(text: str, pos: int, wissen=None, zeilen: int = 40) -> bool:
    """Steht die Stelle in einer Tabellenspalte, deren Kopf (die nächste Zeile darüber mit Etiketten an derselben
    Spaltennummer, Zellen getrennt durch Tabulatoren) ein Personen-Etikett ist ("Kunde", "Fahrer", "Name")? Ein Kopf
    mit nur diesem einen Etikett zählt mit kurzen Kopfwörtern daneben (kopf_mit_personen_etikett)."""
    if wissen is None:
        return False
    za = text.rfind("\n", 0, pos) + 1
    ze = text.find("\n", pos)
    zeile = text[za:len(text) if ze < 0 else ze]
    zellen = [z for z in re.split(r"\t+", zeile)]
    if len(zellen) < 2:
        return False
    k = len([z for z in re.split(r"\t+", text[za:pos])]) - 1
    a = za
    for _ in range(zeilen):
        if a == 0:
            return False
        b = a - 1
        a = text.rfind("\n", 0, b) + 1
        kopf = re.split(r"\t+", text[a:b])
        if len(kopf) < 2 or k >= len(kopf):
            continue
        arten = [_etikett_art(wissen, z) for z in kopf]
        if sum(1 for x in arten if x) < 2 and not kopf_mit_personen_etikett(kopf, arten):
            continue                                     # keine Kopfzeile (Datenzeile, Überschrift)
        return arten[k] == "person"
    return False


def personenbeleg(text: str, start: int, wissen=None) -> bool:
    """Spricht der Ort der Stelle für eine Person: ein Unterschriftsblock unter einer Grußformel, eine Personenspalte
    einer Tabelle oder das Feld C.1.1/C.1.2 der Zulassungsbescheinigung? Dann ist ein Familienname, der zugleich
    Marke, Modell oder Rasse ist ("Neff", "Miele", "Pommer", "Kreidler"), ohne Sachbeleg ein Name (Gegenprüfung
    LK-02)."""
    if im_grussblock(text, start) or personen_spalte(text, start, wissen):
        return True
    return any(a <= start < b for a, b in zb1_personenfelder(text))


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


# Organisationswort oder Rechtsform in einem Zellteil einer Organisations-Spalte ("HUK-COBURG Versicherung", "BKK",
# "Sparkasse Rosenheim", "Muster AG"): eine Organisation
_ORG_WORT_RE = re.compile(r"(?i)(?<![\wäöüß])(?:\w*versicherung(?:en|s-?ag)?|versicherer|assekuranz|\w*bank|"
                          r"\w*kasse|sparkasse|bkk|aok|ikk|dak|lkk|knappschaft|barmer|gesellschaft|konzern|gruppe|"
                          r"ag|gmbh|mbh|se|vvag|a\.[ \t]?g\.|eg|kg|ohg|ltd|inc|s\.[ \t]?a\.)(?![\wäöüß])")
# Hinweis auf eine Person in der Zelle ("Gebhard Lindinger (privat)", "Kurt Wendlinger (Vermittler)", "Herr Maier")
_PERSON_HINWEIS_RE = re.compile(r"(?i)(?<![\wäöüß])(?:privat|privatperson|privatdarlehen|privatkredit|"
                                r"vermittler(?:in)?|makler(?:in)?|herrn?|frau|inhaber(?:in)?|familienversichert|"
                                r"mitversichert|über|beim|bei[ \t]+(?:der|dem)|vater|mutter|eltern(?:teil)?|ehemann|"
                                r"ehefrau|ehegatt(?:e|in)|ehepartner(?:in)?|lebenspartner(?:in)?|sohn|tochter|bruder|"
                                r"schwester|großvater|großmutter|nachbar(?:in|n)?|bürge|bürgin|schwager|schwägerin|"
                                r"onkel|tante)(?![\wäöüß])")
# Gesellschaft bürgerlichen Rechts bzw. Gemeinschaft natürlicher Personen mit dem Namen dahinter ("GbR Seidlmayr",
# "Erbengemeinschaft Riedlinger"): die Gesellschafter sind Personen (Nachprüfung NP-04)
_PERSONEN_GESELLSCHAFT_RE = re.compile(r"(?<![\wäöüß])(?:GbR|(?:Erben|Grundstücks|Bruchteils)gemeinschaft)"
                                       r"[ \t]+[A-ZÄÖÜ]")
_ZELLTEIL_RE = re.compile(r"[^,;/()]+")


@functools.lru_cache(maxsize=4)
def _org_kerne(wissen) -> frozenset:
    """Markenkerne der Organisationen der Wissensbasis: ein Eintrag aus Marke und Organisationswort oder Rechtsform
    ("Gothaer Versicherung", "Adam Riese Versicherung") ohne dieses Schlusswort ("gothaer", "adam riese"). Nur in einer
    Organisations-Spalte eine Organisation: die Erlaubnisliste selbst enthält keine Vor-/Nachnamen-Paare (sonst bliebe
    eine Person dieses Namens überall lesbar, test_wissen)."""
    kerne = set()
    try:
        eintraege = wissen.liste("versicherer_und_organisationen")
    except Exception:
        return frozenset()
    for eintrag in eintraege:
        woerter = eintrag.split()
        while len(woerter) > 1 and _ORG_WORT_RE.fullmatch(woerter[-1]):
            woerter.pop()
            kerne.add(" ".join(woerter).casefold())
    return frozenset(kerne)


def _org_zellteil(teil: str, zelle: str, wissen) -> bool:
    """Ist der Zellteil einer Organisations-Spalte eine Organisation: eine Organisation der Wissensbasis ("HUK-COBURG")
    oder ihr Markenkern ("Adam Riese", _org_kerne), ein Organisationswort oder eine Rechtsform darin – oder ein
    einzelnes Wort ohne Hinweis auf eine Person ("Roland")? Vor- und Nachname ("Gebhard Lindinger") und ein Personen-Hinweis in der Zelle ("(privat)",
    "Vermittler", "familienversichert über …") sind eine Person (Gegenprüfung LK-03/LK-04)."""
    t = " ".join(teil.split())
    if not t:
        return True
    try:
        if wissen is not None and (wissen.ist_allowlist(t) or any(True for _ in wissen.finde(t,
                                                                    "versicherer_und_organisationen"))):
            return True
    except Exception:
        return True
    if _PERSONEN_GESELLSCHAFT_RE.search(t):
        return False                         # "GbR Seidlmayr": Familienname der Gesellschafter
    if _ORG_WORT_RE.search(t):
        return True
    if _PERSON_HINWEIS_RE.search(zelle):
        return False                         # "beim Vater Rauschenbach", "Privatdarlehen Hirschbichler"
    if wissen is not None and t.casefold() in _org_kerne(wissen):
        return True                          # Markenkern eines Versicherers ("Adam Riese" aus "Adam Riese Versicherung")
    woerter = re.findall(r"[^\W\d_][\w'’\-]*", t)
    grosse = [w for w in woerter if w[:1].isupper()]
    if len(grosse) >= 2 and wissen is not None:
        try:
            # Vor- und Nachname in beiden Folgen ("Gebhard Lindinger", bairisch "Gruber Sepp"): eine Person
            if any(wissen.ist_vorname(a) and not wissen.ist_allerweltswort(b) for a, b in zip(grosse, grosse[1:])):
                return False
            if any(wissen.ist_vorname(b) and not wissen.ist_allerweltswort(a)
                   and (wissen.ist_nachname(a) or namensgestalt(a, wissen)) for a, b in zip(grosse, grosse[1:])):
                return False
        except Exception:
            return True
    if len(grosse) == 1 and len(woerter) == 1 and wissen is not None:
        # ein einzelnes Wort mit der Gestalt eines Familiennamens ("Brandhuber" als Anbieter eines Privatdarlehens):
        # eine Person – ein Firmenname ohne diese Gestalt ("Roland", "Hiscox") bleibt eine Organisation
        try:
            if (wissen.ist_nachname(t) and not wissen.ist_mehrdeutig(t)) or namensgestalt(t, wissen):
                return False
        except Exception:
            return True
    return True


def org_spalte_art(text: str, pos: int):
    """Steht die Stelle pos in einer Tabellenspalte, deren Kopfzelle eine Organisation ankündigt ("Versicherer",
    "Anbieter", "Krankenkasse")? None: keine solche Spalte; True: der Zellteil ist eine Organisation (_org_zellteil);
    False: er ist eine Person ("beim Vater Rauschenbach", "GbR Seidlmayr", "Gruber Sepp", "Brandhuber")."""
    za = text.rfind("\n", 0, pos) + 1
    ze = text.find("\n", pos)
    zeile = text[za:len(text) if ze < 0 else ze]
    if "\t" not in zeile:
        return None
    zellen = _zellen(zeile)
    nr = next((i for i, (a, b) in enumerate(zellen) if a <= pos - za < b), None)
    if nr is None:
        return None
    ende = za - 1
    for _ in range(ORG_SPALTE_ZEILEN):
        if ende <= 0:
            return None
        anfang = text.rfind("\n", 0, ende) + 1
        oben = text[anfang:ende]
        if not oben.strip():
            return None                      # Leerzeile: die Tabelle ist zu Ende
        kopf = _zellen(oben)
        if len(kopf) == len(zellen):
            a, b = kopf[nr]
            if _ORG_SPALTE_RE.fullmatch(oben[a:b].strip()):
                za0, zb0 = zellen[nr]
                zelle = zeile[za0:zb0]
                teil = next((m.group(0) for m in _ZELLTEIL_RE.finditer(zelle)
                             if m.start() <= pos - za - za0 < m.end()), zelle)
                try:
                    from . import wissen as wissen_modul
                except Exception:  # pragma: no cover - Wissensbasis fehlt
                    wissen_modul = None
                return _org_zellteil(teil, zelle, wissen_modul)
        ende = anfang - 1
    return None


def organisations_spalte(text: str, pos: int) -> bool:
    """Steht die Stelle pos in einer Tabellenspalte, deren Kopfzelle eine Organisation ankündigt ("Versicherer" ⏎
    "Adam Riese"), und ist ihr Zellteil eine Organisation (_org_zellteil)? Dieselbe Regel für die Erkennung (namen.py,
    wissen_namen) und die Selbstkontrolle."""
    return org_spalte_art(text, pos) is True


# Wörter einer Zelle, die auf eine Person hinweisen, aber selbst kein Name sind ("Privatdarlehen", "beim", "Vater",
# "GbR", "Erbengemeinschaft")
_KEIN_NAME_IN_ORG_ZELLE_RE = re.compile(
    r"(?i)^(?:privat\w*|beim|bei|der|dem|den|die|von|vom|über|vater|mutter|eltern\w*|ehe\w+|lebenspartner\w*|sohn|"
    r"tochter|bruder|schwester|groß\w+|nachbar\w*|bürge|bürgin|schwager|schwägerin|onkel|tante|herrn?|frau|"
    r"inhaber\w*|vermittler\w*|makler\w*|familienversichert|mitversichert|gbr|\w*gemeinschaft|darlehen|kredit)$")


# Hof- und Hausnamen: "Hof Hintermoser", "Anwesen Gschwandtner", "beim Stögerbauer" – der Name nennt die Familie und
# ihren Wohnort zugleich (Nachprüfung NP-14)
_HOF_KOPF_RE = re.compile(r"(?<![\wäöüß\-])(?:(Hof|Anwesen|Gehöft|Bauernhof|Hofstelle|Hofgut|Gutshof|Aussiedlerhof)|"
                          r"(beim|vom|zum))[ \t]+(?=[A-ZÄÖÜ])")
_HOF_NAME_RE = re.compile(r"[A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)?(?![\wäöüß\-])")
# Ort eines Ereignisses oder Wohnorts in derselben Zeile: ein Orts-Etikett mit Doppelpunkt oder ein Ereignis-/Wohnwort
_HOF_ORTSKONTEXT_RE = re.compile(
    r"(?i)(?<![\wäöüß])(?:(?:unfall|schadens?|ereignis|tat|risiko|versicherungs|wohn|stand|abstell|einsatz)?ort|"
    r"unfallstelle|schadenstelle|lage|anschrift|adresse|belegenheit)[ \t]*:|"
    r"(?<![\wäöüß])(?:unfall|schaden|brand|sturm|hagel|einbruch|diebstahl|zusammensto(?:ß|ss)|kollision|wildunfall|"
    r"geschah|passierte|ereignete|wohnt|wohnen|wohnte|lebt|leben|lebte|zufahrt|einfahrt|hofeinfahrt|weide|stall|"
    r"scheune|tenne)(?![\wäöüß])")


def _hofname_wort(wort: str, wissen) -> bool:
    """Kann das Wort hinter "Hof"/"Anwesen"/"beim" ein Familien- oder Hausname sein: großgeschrieben, kein Allerwelts-,
    Orts-, Berufs- oder Etikettwort, kein Vorname, keine Substantiv-Endung ("beim Einparken", "zum Hof", "Hof Süd")?"""
    if len(wort) < 4 or _SUBSTANTIV_ENDUNG_RE.search(wort):
        return False
    try:
        if wissen.ist_nachname(wort) and not wissen.ist_mehrdeutig(wort):
            return True
        if (wissen.ist_allerweltswort(wort) or wissen.ist_allowlist(wort) or wissen.ist_ort(wort)
                or wissen.ist_beruf(wort) or wissen.ist_vorname(wort) or wissen.ist_anrede_titel(wort)):
            return False
        return not any(wissen.index(f"etiketten_{art}").eintrag_fuer(wort) is not None
                       for art in wissen.ETIKETTEN_ARTEN)
    except Exception:  # pragma: no cover - Wissensbasis beschädigt
        return False


def hofnamen(text: str, wissen) -> list:
    """(start, ende) der Hof- und Hausnamen: hinter "Hof", "Anwesen", "Gehöft" … ein möglicher Familienname
    (_hofname_wort) mit Namensgestalt oder in einer Zeile mit Orts- bzw. Ereigniskontext ("Unfallort: Zufahrt zum Hof
    Hintermoser"); hinter "beim"/"vom"/"zum" nur ein Wort mit Namensgestalt in einer solchen Zeile ("Der Unfall geschah
    beim Stögerbauer"). Nicht: "beim Einparken", "zum Hof", "Hof Süd"."""
    if wissen is None:
        return []
    aus = []
    kontext_je_zeile: dict = {}
    for m in _HOF_KOPF_RE.finditer(text):
        n = _HOF_NAME_RE.match(text, m.end())
        if n is None or not _hofname_wort(n.group(0), wissen):
            continue
        za = text.rfind("\n", 0, m.start()) + 1
        if za not in kontext_je_zeile:
            ze = text.find("\n", m.start())
            kontext_je_zeile[za] = bool(_HOF_ORTSKONTEXT_RE.search(text, za, len(text) if ze < 0 else ze))
        gestalt = namensgestalt(n.group(0), wissen)
        if (m.group(1) and (gestalt or kontext_je_zeile[za])) or (m.group(2) and gestalt and kontext_je_zeile[za]):
            aus.append((n.start(), n.end()))
    return aus


# Mundartliche Namensfolge mit Artikel: "die Kölbl Resi", "der Gruber Sepp" – Familienname vor dem Rufnamen (Nachprüfung
# LK-14)
_ARTIKEL_NAME_RE = re.compile(r"(?<![\wäöüß])(?:der|die|dem|den|vom|beim|zum|zur)[ \t]+"
                              r"([A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)?)[ \t]+([A-ZÄÖÜ][a-zäöüß]+)(?![\wäöüß\-])")


def artikel_nachname_vorname(text: str, wissen) -> list:
    """(start, ende) von "Artikel + Familienname + Rufname" ("die Kölbl Resi", "der Haslbeck Wastl"): der Rufname ein
    Vorname der Wissensbasis (nicht mehrdeutig), der Familienname davor ein großgeschriebenes Wort, das kein Allerwelts-,
    Orts-, Berufs- oder Etikettwort und kein Vorname ist (_hofname_wort). Die Spanne umfasst beide Namen."""
    if wissen is None:
        return []
    aus = []
    for m in _ARTIKEL_NAME_RE.finditer(text):
        nach, vor = m.group(1), m.group(2)
        try:
            if not wissen.ist_vorname(vor) or wissen.ist_vorname_mehrdeutig(vor) or wissen.ist_allerweltswort(vor):
                continue
        except Exception:  # pragma: no cover - Wissensbasis beschädigt
            continue
        if _hofname_wort(nach, wissen):
            aus.append((m.start(1), m.end(2)))
    return aus


def _org_spalten_zellteile(text: str):
    """(Anfang, Zellteil, Zelle, Zeile) je Zellteil (getrennt durch Komma, Semikolon, Schrägstrich, Klammer) in den
    Zellen einer Organisations-Spalte – Zeile für Zeile mit dem zuletzt gesehenen Kopf je Zellenzahl (lineare Laufzeit
    auch bei großen Tabellen)."""
    koepfe: dict = {}                       # Zellenzahl -> (Zeilennummer, Spalten mit Organisations-Kopf)
    za = 0
    for nr, zeile in enumerate(text.split("\n")):
        anfang, za = za, za + len(zeile) + 1
        if not zeile.strip():
            koepfe = {}
            continue
        if "\t" not in zeile:
            continue
        zellen = _zellen(zeile)
        org = {k for k, (x, y) in enumerate(zellen) if _ORG_SPALTE_RE.fullmatch(zeile[x:y].strip())}
        if org:
            koepfe[len(zellen)] = (nr, org)
            continue
        kopf = koepfe.get(len(zellen))
        if kopf is None or nr - kopf[0] > ORG_SPALTE_ZEILEN:
            continue
        for k in kopf[1]:
            x, y = zellen[k]
            zelle = zeile[x:y]
            for teil in _ZELLTEIL_RE.finditer(zelle):
                yield anfang + x + teil.start(), teil.group(0), zelle, zeile


def _wissen_oder_modul(wissen):
    if wissen is not None:
        return wissen
    try:
        from . import wissen as wissen_modul
        return wissen_modul
    except Exception:  # pragma: no cover - Wissensbasis fehlt
        return None


def personen_in_org_spalten(text: str, wissen=None) -> list:
    """(start, ende) der Namen in Zellen einer Organisations-Spalte, die eine Person sind (_org_zellteil False):
    die großgeschriebenen Wörter außer den Hinweiswörtern ("beim Vater Rauschenbach" -> "Rauschenbach", "GbR
    Seidlmayr" -> "Seidlmayr", "Privatdarlehen Hirschbichler" -> "Hirschbichler"; Nachprüfung NP-04). Eine Regel für
    Erkennung (namen.py) und Selbstkontrolle."""
    if not text or "\t" not in text:
        return []
    wissen = _wissen_oder_modul(wissen)
    if wissen is None:
        return []
    aus = []
    for anfang, teil, zelle, _zeile in _org_spalten_zellteile(text):
        if _org_zellteil(teil, zelle, wissen) is not False:
            continue
        for m in re.finditer(r"(?<![\wäöüß'’\-])[A-ZÄÖÜ][a-zäöüß'’]+(?:-[A-ZÄÖÜ][a-zäöüß'’]+)?"
                             r"(?![\wäöüß'’])", teil):
            w = m.group(0)
            if _KEIN_NAME_IN_ORG_ZELLE_RE.match(w) or _ORG_WORT_RE.fullmatch(w):
                continue
            try:
                if (wissen.ist_allerweltswort(w) and not wissen.ist_nachname(w)) or wissen.ist_allowlist(w):
                    continue
            except Exception:
                continue
            aus.append((anfang + m.start(), anfang + m.start() + len(w)))
    return aus


# Hinweis in derselben Tabellenzeile, dass hinter einer Versicherer-Marke mit Personengestalt eine Person stehen kann
# (Bürgschaft, Darlehen, privat: "Kautionsbürgschaft ⇥⇥ Adam Riese ⇥⇥ 3.600 EUR") – auch in Zusammensetzungen
_PERSON_ZEILE_RE = re.compile(r"(?i)bürgschaft|bürge|bürgin|darlehen|privat")


def org_marken_in_personengestalt(text: str, wissen=None) -> list:
    """(start, ende) der Zellteile einer Organisations-Spalte, die der Markenkern eines Versicherers mit der Gestalt
    "Vorname Familienname" sind ("Adam Riese" aus "Adam Riese Versicherung", _org_kerne), wenn ihre Tabellenzeile auf
    eine Person deuten kann (Bürgschaft, Darlehen, privat, Personenhinweis): die Erkennung lässt sie als Versicherer
    stehen, die Selbstkontrolle meldet sie – ein Bürge dieses Namens ist dort nicht auszuschließen (Nachprüfung A,
    Probe o12). In Vergleichs- und Bestandslisten ("PHV ⇥⇥ Adam Riese ⇥⇥ XXL") bleibt die Marke ohne Meldung
    (Domänen-Befund 92, Gegenprüfung LK-03)."""
    if not text or "\t" not in text:
        return []
    wissen = _wissen_oder_modul(wissen)
    if wissen is None:
        return []
    kerne = _org_kerne(wissen)
    aus = []
    for anfang, teil, zelle, zeile in _org_spalten_zellteile(text):
        woerter = teil.split()
        if len(woerter) != 2 or " ".join(woerter).casefold() not in kerne:
            continue
        rest = zeile.replace(zelle, " ", 1)
        if not (_PERSON_ZEILE_RE.search(rest) or _PERSON_HINWEIS_RE.search(rest)):
            continue
        vor, nach = woerter
        try:
            if not wissen.ist_vorname(vor) or wissen.ist_vorname_mehrdeutig(vor) \
                    or not (wissen.ist_nachname(nach) or namensgestalt(nach, wissen)):
                continue
        except Exception:  # pragma: no cover - Wissensbasis beschädigt
            continue
        s = anfang + len(teil) - len(teil.lstrip())
        aus.append((s, s + len(teil.strip())))
    return aus


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
