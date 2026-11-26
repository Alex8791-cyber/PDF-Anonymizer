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

from .kennungsformen import FUNKTIONSWOERTER, KEIN_NAMENSWERT

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


# Eintrag einer Personenliste: Name und dahinter ein Datum, ein Jahr oder ein Alter in Klammern ("Max, 05.09.2016",
# "- Juni (6)", "Dakota, 2019"), höchstens 60 Zeichen bis dorthin
_LISTENEINTRAG_RE = re.compile(r"[ \t]*(?:[-–•*·][ \t]*)?[^\W\d_][^\n]{0,60}?(?:\d{1,2}\.[ ]?\d{1,2}\.[ ]?\d{2,4}|"
                               r"(?<!\d)(?:19|20)\d{2}(?!\d)|\([ \t]*\d{1,2}[ \t]*\))")


def kinderliste_direkt(text: str, zeilenanfang: int, zeilen: int = 12) -> bool:
    """Steht die Zeile in einer Liste direkt unter einer Familien-Überschrift ("Kinder:", "Mitversicherte Personen:")
    – darüber nur weitere Einträge (Name mit Datum, Jahr oder Alter), keine Leerzeile, kein anderer Text? Nur dort ist
    ein Orts-, Monats- oder unbekanntes Wort am Zeilenanfang ein Vorname (kinderlisten_vorname); "Aschaffenburg,
    10.07.2025" über der Unterschrift eines Antrags mit "Kind: Geburtsdatum:" weiter oben ist Ort und Datum."""
    ende = zeilenanfang - 1
    for _ in range(zeilen):
        if ende <= 0:
            return False
        anfang = text.rfind("\n", 0, ende) + 1
        zeile = text[anfang:ende]
        if not zeile.strip():
            return False
        kopf = FAMILIE_KOPF_RE.match(zeile)
        if kopf and not zeile[kopf.end():].strip():
            return True
        if not _LISTENEINTRAG_RE.match(zeile):
            return False
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
                                  r"bauer|schmied|schmid|bach|stein|feld|ow|ski|sky|ić|vić|escu|oglu|oğlu|yan|ian|"
                                  # Herkunftsnamen und bairische Verkleinerungsformen ("Zwickelsdorfer",
                                  # "Wimmelbacher", "Hinterstoißer", "Zirngibl", "Hingerl"; Abnahme 2 A2-04, V7)
                                  r"dorfer|bacher|moser|sser|bl|gl|stl|rl|dl|ndl)$")
# typische Endungen gewöhnlicher Substantive und Partizipien – kein Name
_SUBSTANTIV_ENDUNG_RE = re.compile(r"(?i)(?:ung|ungen|heit|keit|schaft|tion|ität|ismus|nis|tum|chen|ierte[nr]?|"
                                   r"ende[nr]?)$")
# Grundwörter von Geräten, Maschinen, Tieren und Rollen auf "-er", die mit beliebigem Bestimmungswort ein Sachwort bleiben
# ("Hochdruckreiniger", "Kondenstrockner", "Heizlüfter", "Gabelstapler", "Spaziergänger", "Marder"; Abnahme 4 AB4U-04) –
# geteilt mit der Selbstkontrolle (restrisiko._sachwort_er)
ER_GERAET_GRUNDWORT = ("reiniger", "trockner", "lüfter", "luefter", "stapler", "gänger", "gaenger", "strahler",
                       "kocher", "sauger", "spüler", "spueler", "trimmer", "mäher", "maeher", "toaster", "marder",
                       "enthärter", "enthaerter", "boiler", "kühler", "kuehler", "verteiler", "zünder", "zuender",
                       "erhitzer", "wärmer", "waermer", "fräser", "fraeser", "bohrer", "rasierer", "föhner",
                       "foehner", "mixer", "kompressor", "generator", "regler", "melder", "sender", "empfänger",
                       "lautsprecher", "verstärker", "verstaerker", "akkuschrauber", "hamster")


def geraete_kompositum(wort: str) -> bool:
    """Ist das Wort ein Kompositum aus einem Bestimmungswort und einem Geräte-Grundwort ("Gabelstapler",
    "Hochdruckreiniger", "Heizlüfter")? Das Grundwort allein ("Kocher", "Regler") ist auch ein Familienname und zählt
    nicht (Abnahme 5 A5-02)."""
    k = (wort or "").casefold()
    return any(k.endswith(g) and len(k) >= len(g) + 3 for g in ER_GERAET_GRUNDWORT)


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
        if "-" in w:
            # Doppelname: ein Teil mit Namensbeleg, kein Teil ein Sachwort ("Huber-Brandlhuber", "Fischbacher-Zöttl";
            # nicht "Service-Center", "Kunden-Hotline")
            teile = [t for t in w.split("-") if t]
            if len(teile) < 2 or not all(t[:1].isupper() for t in teile) or any(_sachteil(t, wissen) for t in teile):
                return False
            return any(namensgestalt(t, wissen) or _nur_name(t, wissen) for t in teile)
        if (wissen.ist_allerweltswort(w) or wissen.ist_allowlist(w) or wissen.ist_ort(w) or wissen.ist_beruf(w)
                or wissen.ist_vorname(w) or wissen.ist_anrede_titel(w)):
            return False
        if any(wissen.index(f"etiketten_{art}").eintrag_fuer(w) is not None for art in wissen.ETIKETTEN_ARTEN):
            return False
    except Exception:  # pragma: no cover - Wissensbasis beschädigt
        return False
    return len(w) >= 7 and bool(_NACHNAMEN_ENDUNG_RE.search(w.casefold())) and not _SUBSTANTIV_ENDUNG_RE.search(w)


def _sachteil(w: str, wissen) -> bool:
    """Ist der Teil eines Doppelworts ein Sachwort: Allerwelts-, Orts-, Berufs- oder Etikettwort, Substantiv-Endung?"""
    try:
        return bool(wissen.ist_allerweltswort(w) or wissen.ist_ort(w) or wissen.ist_beruf(w)
                    or _SUBSTANTIV_ENDUNG_RE.search(w)
                    or any(wissen.index(f"etiketten_{art}").eintrag_fuer(w) is not None
                           for art in wissen.ETIKETTEN_ARTEN))
    except Exception:  # pragma: no cover - Wissensbasis beschädigt
        return True


def _nur_name(w: str, wissen) -> bool:
    """Ist das Wort ein bekannter Vor- oder Nachname der Wissensbasis und kein Allerweltswort?"""
    if wissen is None:
        try:
            from . import wissen as wissen_modul
            wissen = wissen_modul
        except Exception:  # pragma: no cover - Wissensbasis fehlt
            return False
    try:
        return (wissen.ist_nachname(w) or wissen.ist_vorname(w)) and not wissen.ist_allerweltswort(w)
    except Exception:  # pragma: no cover - Wissensbasis beschädigt
        return False


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
# kurze Grußformel als ganze Zeile ("Gruß", "Grüße", "Freundlichst", "Herzlichst", "Servus", "Tschüss", "LG"), auch mit
# einer Herkunft ("Grüße aus dem Allgäu", "Schöne Grüße aus dem Urlaub", "Gruß vom Chiemsee"; Abnahme N6) – nicht
# mitten im Satz ("Gruß an die Familie"; Nachprüfung NP-03)
GRUSS_ZEILE_RE = re.compile(r"(?i)^[ \t]*(?:(?:(?:viele|liebe|beste|schöne|sonnige|herzliche|freundliche|kollegiale)"
                            r"[ \t]+)?(?:gru(?:ß|ss)|gr[üu](?:ß|ss)e)(?:[ \t]+(?:aus|von|vom|nach|in)"
                            r"(?:[ \t]+[^\W\d_][\w\-]*){1,6})?|freundlichst|herzlichst|servus|tsch[üu]ss?|"
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
# auch gebeugt ("des Onkels Tremml", "bei dem Mandanten Kreuzl", "des Vermieters Leser"; Abnahme 5 A5-13)
_PERSONENWORT = (
    r"(?:Kollegen?|Kollegin|Nachbarn?|Nachbars|Nachbarin|Zeugen?|Zeugin|Mitarbeiter(?:in|s)?|Chef(?:in|s)?|Kunden?|"
    r"Kundin|Mieter(?:in|s)?|Vermieter(?:in|s)?|Sachbearbeiter(?:in|s)?|Monteur(?:in|s|e)?|Hausmeister(?:in|s)?|"
    r"Schwagers?|Schwägerin|Onkels?|Tante|Cousine?|Cousins|Neffen?|Nichte|Ehemann(?:e?s)?|Ehefrau|Sohn(?:e?s)?|"
    r"Tochter|Vaters?|Mutter|Bruders?|Schwester|Opas?|Oma|Enkel(?:in|s)?|Patient(?:in|en)?|Mandant(?:in|en)?|"
    r"Vermittler(?:in|s)?|Makler(?:in|s)?|Gutachter(?:in|s)?|Anrufer(?:in|s)?|Unfallgegner(?:in|s)?|"
    r"Geschädigte[rn]?)")
PERSONENWORT_DAVOR_RE = re.compile(r"(?<![\wäöüß])" + _PERSONENWORT + r"[ \t]+$")
# Personenwort ohne Begleiter direkt vor einem großgeschriebenen Wort im Satz ("Laut Nachbar Grohe war …", "Rücksprache
# mit Nachbar Grohe am Montag"; Abnahme N7) – das Wort ist der Name der Person; nur mit Leerzeichen dazwischen, nicht
# über eine Tabellenzelle ("Mieter ⇥⇥ Objekt" ist ein Tabellenkopf)
_PERSONENWORT_NAME_RE = re.compile(r"(?<![\wäöüß\-])" + _PERSONENWORT +
                                   r"[ ]{1,2}([A-ZÄÖÜ][a-zäöüß]{2,}(?:-[A-ZÄÖÜ][a-zäöüß]+)?)(?![\wäöüß\-])")


# Präposition oder Satzteil vor dem Personenwort ("Laut Nachbar Grohe", "Rücksprache mit Nachbar Grohe", "über Kollege
# Wimmelbacher"): dann steht dahinter der Name der Person. Ohne sie – am Anfang einer Zeile oder Notiz ("Chef
# Sekretariat ist ab 9 Uhr besetzt", "Patient Visite um 10 Uhr", "Ehefrau Mitversichert: ja") – ist das Wort oft eine
# Sache, die mit dem Personenwort zusammengehört (Abnahme 2 A2-04)
_PRAEPOSITION_DAVOR_RE = re.compile(r"(?i)(?<![\wäöüß])(?:laut|lt\.|gemäß|gemaess|mit|von|über|ueber|an|für|fuer|bei|"
                                    r"durch|gegenüber|gegenueber|zu|und|oder|sowie|wegen|samt|nebst|ohne|via|per)"
                                    r"[ \t]+$")
def _namensbeleg_personenwort(w: str, wissen) -> bool:
    """Spricht das Wort selbst für einen Namen: bekannter Vor- oder Nachname, Gestalt eines Familiennamens oder eine
    Marke (die hinter einem Personenwort eine Person ist: "Laut Monteur Buderus")?"""
    try:
        if wissen.ist_nachname(w) or wissen.ist_vorname(w) or namensgestalt(w, wissen):
            return True
        return bool(wissen.index("sachnamen").finde(w))
    except Exception:  # pragma: no cover - Wissensbasis beschädigt
        return True


# Verb einer Person direkt hinter dem Wort ("Monteur Grohe kam am 03.03.", "Nachbar Zettl hat den Brand gemeldet",
# "Kollegin Zach ruft zurück", "Der Vermieter Kranawetter hat gekündigt"): steht das Personenwort am Satzanfang, ist das
# Wort der Name des Satzgegenstands (Abnahme 3 AB3-02, AB3-03). Nicht "ist", "war", "wird", "wurde" – so wird auch eine
# Sache beschrieben ("Chef Sekretariat ist ab 9 Uhr besetzt", "Kunden Service-Center ist geschlossen"; A2-04) – und
# keine Form, die zugleich ein Partizip ist ("Beim Nachbarn Rauch entdeckt.", "… Schimmel festgestellt.")
_PERSON_VERB_DAHINTER_RE = re.compile(
    r"[ \t]+(?:hat|hatte|hätte|haette|kam|kommt|käme|kaeme|rief|ruft|sagte|sagt|meinte|meint|meldete|meldet|fuhr|"
    r"fährt|faehrt|sah|sieht|schrieb|schreibt|bat|bittet|erklärte|erklaerte|bestätigte|bestaetigte|berichtete|"
    r"teilte|teilt|gab|gibt|will|wollte|möchte|moechte|kann|konnte|muss|musste|soll|sollte|darf|durfte|wohnt|"
    r"wohnte|lebt|lebte|arbeitet|arbeitete|schilderte|schildert|behauptete|erschien|erscheint|ging|geht|half|hilft|"
    r"brachte|bringt|holte|holt|fand|findet|wusste|weiß|weiss|telefonierte|reparierte|tauschte|tauscht|prüfte|"
    r"prüft|pruefte|prueft|verursachte|unterschrieb|unterschreibt|kündigte|kündigt|kuendigte|kuendigt|zahlte|zahlt|"
    r"stellte|stellt|kümmert|kümmerte|kuemmert|kuemmerte|fragte|fragt|antwortete|antwortet|fehlte|beauftragte|"
    r"informierte|bemerkte|entdeckte)(?![\wäöüß])")
# Personenwörter, hinter denen auch der Name einer Firma stehen kann ("Monteur Buderus", "Mitarbeiterin Vorwerk",
# "Gutachter Dekra", "Kunde Miele"): dort ist eine bekannte Marke ohne weiteren Beleg kein sicherer Name
_FIRMEN_PERSONENWORT_RE = re.compile(r"(?:Monteur(?:in|s|e)?|Mitarbeiter(?:in|s)?|Sachbearbeiter(?:in|s)?|"
                                     r"Vermittler(?:in|s)?|Makler(?:in|s)?|Gutachter(?:in|s)?|Kunden?|Kundin|"
                                     r"Anrufer(?:in|s)?)[ ]")
# Kontaktangabe direkt hinter dem Wort ("Monteur Grohe, Tel. 0171 …", "Nachbar Zettl (Handy 0160 …)"): eine Person
_KONTAKT_DAHINTER_RE = re.compile(r"[ \t]*[,(]?[ \t]*(?:Tel(?:efon)?\.?|Tel\.-Nr\.?|Handy|Mobil(?:nummer)?|Fax|"
                                  r"E-?Mail|Durchwahl)(?![a-zäöüß])")
# Satzanfang vor dem Personenwort bzw. seinem Begleiter: Zeilen- oder Zellenanfang, hinter einem Satzzeichen, einem
# Doppelpunkt ("Notiz: Kollegin Zach ruft zurück"), Strich oder Komma
_SATZANFANG_DAVOR_RE = re.compile(r"(?:^|[.!?:;,•|–—(\"„“‚\t])[ \t]*$")


def _satzanfang(text: str, pos: int) -> bool:
    """Beginnt an pos ein Satz, eine Notiz oder eine Zelle (nur Leerraum hinter einem Satzzeichen bzw. Zeilenanfang)?"""
    za = text.rfind("\n", max(0, pos - 200), pos) + 1
    return bool(_SATZANFANG_DAVOR_RE.search(text[max(za, pos - 40):pos])) or not text[za:pos].strip()


# Leer- und Verweiswörter eines Felds ("Zeuge Unbekannt", "Kinder Keine"): hinter einem Personenwort nie ein Name. Die
# Zustandswörter aus KEIN_NAMENSWERT ("ledig", "niemand", "verheiratet") sind es nur als Feldwert vor einem Doppelpunkt
# ("Ehefrau Mitversichert: ja") – im Satz können sie ein Familienname sein ("Nachbar Ledig hat angerufen."; Abnahme 4
# AB4-08) und werden wie jedes andere Wort behandelt
_KEIN_NAME_VERWEIS = KEIN_NAMENSWERT - frozenset("""mitversichert versichert unversichert verstorben ledig verheiratet
geschieden verwitwet niemand""".split())
# Lageadverbien hinter einem Personenwort ("Nachbar Gegenüber", "Mieter Nebenan"): eine Lage, kein Name (AB4U-01)
_LAGE_ADVERB = frozenset("gegenüber gegenueber nebenan drüben drueben oben unten daneben vorne vorn hinten nebendran "
                         "obendrüber".split())
# Organisationseinheit oder Firmenrolle als Grundwort ("Außendienst", "Innendienst", "Vertrieb", "Stadtwerke",
# "Backoffice", "Netzbetreiber", "Wasserversorger"): hinter einem Personenwort eine Abteilung oder Firma – geschwärzt nur
# mit eigenem Namensbeleg, sonst gemeldet (AB4U-01)
_ORG_GESTALT_RE = re.compile(r"(?i)[\wäöüß]{0,25}(?:dienst|service|betreuung|management|leitung|team|abteilung|büro|"
                             r"buero|agentur|zentrale|vertrieb|filiale|niederlassung|verwaltung|gruppe|center|kanzlei|"
                             r"werk|werke|betrieb|office|betreiber|versorger|anbieter|hersteller|lieferant|händler|"
                             r"haendler|einkauf|verkauf|technik|buchhaltung|empfang|personal|marketing|support|"
                             r"sekretariat|registratur|stelle|praxis|redaktion|disposition)")


def verb_einer_person_dahinter(text: str, pos: int, ende: int | None = None) -> bool:
    """Steht ab pos (hinter Leerraum) das Verb einer Person ("meldet", "sah", "hat", "ist erreichbar")? Für die
    Rohwert-Regel der Formulare (struktur.ocr_rohwert): ein Satz hinter einem Personenwort ist kein Feldwert."""
    ende = len(text) if ende is None else ende
    return bool(_PERSON_VERB_DAHINTER_RE.match(text, pos, ende) or _PERSON_ZUSTAND_DAHINTER_RE.match(text, pos, ende))


def org_gestalt(w: str) -> bool:
    """Öffentlich für die Selbstkontrolle: _org_gestalt."""
    return _org_gestalt(w)


def _org_gestalt(w: str) -> bool:
    """Hat das Wort die Gestalt einer Organisationseinheit, Firmenrolle oder Lage (_ORG_GESTALT_RE, _LAGE_ADVERB)?"""
    return w.casefold() in _LAGE_ADVERB or bool(_ORG_GESTALT_RE.fullmatch(w))


def _org_namensbeleg(w: str, wissen) -> bool:
    """Namensbeleg eines Worts mit Organisations-Gestalt: ein Vor- oder Nachname bzw. eine Marke der Wissensbasis – nicht
    die Gestalt eines Familiennamens, die "Wasserversorger" und "Netzbetreiber" mit "-er" schon haben (AB4U-01)."""
    try:
        return bool(wissen.ist_nachname(w) or wissen.ist_vorname(w) or wissen.index("sachnamen").finde(w))
    except Exception:  # pragma: no cover - Wissensbasis beschädigt
        return True


def _personenwort_wort(w: str, wissen, beruf_nachname: bool = False) -> bool:
    """Kann das großgeschriebene Wort hinter einem Personenwort ein Name sein – kein Allerwelts-, Berufs-, Orts-,
    Etikett-, Titel- oder Kalenderwort, keine Substantiv-Endung, kein Leer- oder Verweiswort eines Felds ("Zeuge
    Unbekannt"), kein Lageadverb ("Nachbar Gegenüber")? beruf_nachname: ein Berufswort oder Titel, das zugleich ein
    Familienname der Wissensbasis ist ("beim Nachbarn Koch", "Kollege Schreiner", "Onkel Kaplan"), zählt mit – für
    die Selbstkontrolle, die es meldet, statt es auszunehmen (Abnahme 4 AB4-13). Ein Doppelname zählt, wenn ein Teil
    ein Vor- oder Familienname ist und kein Teil ein Allerweltswort ("Bauer-Kaltl", nicht "Service-Center"; AB4-14)."""
    k = w.casefold()
    if _SUBSTANTIV_ENDUNG_RE.search(w) or k in _KALENDER or k in _KEIN_NAME_VERWEIS or k in _LAGE_ADVERB:
        return False
    try:
        if "-" in w:
            teile = [t for t in w.split("-") if t]
            if any(wissen.ist_allerweltswort(t) for t in teile):
                return False                             # "Kunden Service-Center"
            if any(wissen.ist_nachname(t) or wissen.ist_vorname(t) or namensgestalt(t, wissen) for t in teile):
                return not any(any(wissen.index(f"etiketten_{art}").eintrag_fuer(t) is not None
                                   for art in wissen.ETIKETTEN_ARTEN) for t in teile)
        nachname = beruf_nachname and wissen.ist_nachname(w)
        beruf = wissen.ist_beruf(w) and not nachname
        titel = wissen.ist_anrede_titel(w) and not nachname
        if wissen.ist_allerweltswort(w) or beruf or wissen.ist_ort(w) or titel or wissen.ist_allowlist(w):
            return False
        if any(wissen.index(f"etiketten_{art}").eintrag_fuer(w) is not None for art in wissen.ETIKETTEN_ARTEN):
            return False
    except Exception:  # pragma: no cover - Wissensbasis beschädigt
        return False
    return True


def personenwort_kandidaten(text: str, wissen=None, beruf_nachname: bool = False) -> list:
    """(start, ende, begleiter, beleg) aller Wörter direkt hinter einem Personenwort, die ein Name sein können
    (_personenwort_wort) – unabhängig davon, ob die Erkennung sie schwärzt. begleiter: ein Begleiter steht davor ("beim
    Nachbarn", "dem Zeugen"); beleg: das Wort selbst spricht für einen Namen (Vor- oder Nachname der Wissensbasis, auch
    mehrdeutig, Gestalt eines Familiennamens, Marke). Für die Selbstkontrolle: was die Erkennung nicht schwärzt, meldet
    sie an seiner Stelle – auf der Textebene und auf OCR-Seiten (Abnahme 3 AB3-03, AB3-04); mit beruf_nachname auch ein
    Berufswort, das zugleich ein Familienname ist ("Wir waren beim Nachbarn Koch zu Besuch.")."""
    if not text or not _PERSONENWORT_VORAB_RE.search(text):
        return []
    wissen = _wissen_oder_modul(wissen)
    if wissen is None:
        return []
    aus = []
    for m in _PERSONENWORT_NAME_RE.finditer(text):
        w = m.group(1)
        if not _personenwort_wort(w, wissen, beruf_nachname) \
                or text[m.end(1):m.end(1) + 3].lstrip(" \t").startswith(":"):
            continue
        begleiter = bool(_BEGLEITER_DAVOR_RE.search(text[max(0, m.start() - 20):m.start()]))
        try:
            beleg = _namensbeleg_personenwort(w, wissen) or _bekannte_marke(w, wissen)
        except Exception:  # pragma: no cover - Wissensbasis beschädigt
            beleg = True
        aus.append((m.start(1), m.end(1), begleiter, beleg))
    return aus


# Zeitwörter hinter einem Personenwort ("Nachbar Morgen kommt vorbei"): eine Zeitangabe oder ein Name – nur gemeldet
_ZEITWORT = frozenset("morgen heute gestern abend mittag nachmittag vormittag nacht früh frueh bald später spaeter jetzt "
                      "sofort gleich nachher vorhin".split())
# Zusatz einer Rolle statt eines Namens hinter einem Personenwort: Stockwerk oder Gebäudeteil ("Mieter Erdgeschoss",
# "Mieter Souterrain"), Kanal ("Mitarbeiter Hotline"), Sparte, Kundengruppe oder Gewerk ("Kunde Gewerbe", "Monteur
# Fernwärme") – wie Abteilungen und Firmenrollen (_ORG_GESTALT_RE) kein Familienname (Abnahme 4 AB4U-01)
_ROLLEN_ZUSATZ_RE = re.compile(
    r"(?i)[\wäöüß]{0,20}(?:geschoss|geschoß|etage|stockwerk|souterrain|parterre|dachboden|speicher|anbau|hinterhaus|"
    r"vorderhaus|seitenflügel|seitenfluegel|nebengebäude|nebengebaeude|hotline|telefon|schalter|gewerbe|privat|wärme|"
    r"waerme|heizung|sanitär|sanitaer|elektro|elektrik|klima|lüftung|lueftung|bereich|sparte)")
# Grundform der Einzahl eines Personenworts, die sich von Mehrzahl, Dativ und Genitiv unterscheidet ("Nachbar",
# "Kollegin", "Kunde"; nicht "Mieter", "Kollegen", "Nachbars"): mitten im Satz ohne Begleiter steht dahinter ein Name
_PERSONENWORT_EINZAHL_RE = re.compile(
    r"Kollege|Kollegin|Nachbar|Nachbarin|Zeuge|Zeugin|Mitarbeiterin|Chef|Chefin|Kunde|Kundin|Mieterin|Vermieterin|"
    r"Sachbearbeiterin|Monteur|Monteurin|Hausmeisterin|Schwägerin|Tante|Cousin|Cousine|Neffe|Nichte|Ehemann|Ehefrau|"
    r"Sohn|Tochter|Vater|Mutter|Bruder|Schwester|Opa|Oma|Enkelin|Patient|Patientin|Mandant|Mandantin|Vermittlerin|"
    r"Maklerin|Gutachterin|Anruferin|Unfallgegnerin")
# "als" vor dem Personenwort: eine Rolle ("Sie macht als Gutachterin Hausbesuche.")
_ALS_DAVOR_RE = re.compile(r"(?i)(?<![\wäöüß])als[ \t]+$")
# dahinter ein weiteres Personenwort in einer Aufzählung ("Zeugen: Nachbar Wasser und Nachbarin Regen"): eine Person
_PERSONENWORT_FOLGT_RE = re.compile(r"[ \t]*(?:,|und|oder|sowie)[ \t]+" + _PERSONENWORT + r"[ \t]")


def _allerwelt_als_name(text: str, m, wissen) -> bool:
    """Ein Allerweltswort, das ein Familienname sein kann ("Wasser", "Regen"), direkt hinter einem Personenwort ohne
    Begleiter – dort ist es der Name wie ein unbekanntes Wort (auf 0230782 standen "Wasser" und "Regen" noch nicht in der
    Liste der Allerweltswörter und wurden so geschwärzt; Abnahme 5 A5-05):
    - hinter "laut" ("Laut Nachbarin Regen war die Tür offen."), mit einer Kontaktangabe oder einem weiteren
      Personenwort einer Aufzählung dahinter ("Zeugen: Nachbar Wasser und Nachbarin Regen");
    - am Satz- oder Notizanfang mit dem Verb einer Person dahinter ("Nachbar Wasser hat angerufen.");
    - mitten im Satz hinter der Grundform der Einzahl ("Rücksprache mit Nachbar Wasser am Montag.", "Gestern rief
      Kollegin Regen an."); hinter "Mieter", "Kollegen", "Kunden" kann es ein Satzteil sein ("Er zeigte Kollegen
      Fotos.") – das meldet die Selbstkontrolle (personenwort_allerwelt) –, hinter "als" ist das Personenwort eine
      Rolle ("Sie macht als Gutachterin Hausbesuche.").
    Hinter einem Begleiter ("Er hat dem Nachbarn Wasser abgegraben.") ist es ein Satzteil; Abteilungs-, Lage-,
    Kanal-, Sparten-, Kalender-, Zeit-, Berufs-, Orts- und Feldwörter ("Mieter Erdgeschoss", "Kunde Gewerbe") und
    Komposita mit einem Allerweltswort als Grundwort ("Wasserschaden") bleiben beim Melden (AB4U-01)."""
    w = m.group(1)
    k = w.casefold()
    if "-" in w or _SUBSTANTIV_ENDUNG_RE.search(w) or k in _KALENDER or k in _KEIN_NAME_VERWEIS or k in _LAGE_ADVERB \
            or k in _ZEITWORT or _org_gestalt(w) or _ROLLEN_ZUSATZ_RE.fullmatch(w):
        return False
    try:
        if not wissen.ist_allerweltswort(w) or wissen.ist_beruf(w) or wissen.ist_ort(w) or wissen.ist_anrede_titel(w) \
                or wissen.ist_allowlist(w) or any(wissen.index(f"etiketten_{art}").eintrag_fuer(w) is not None
                                                  for art in wissen.ETIKETTEN_ARTEN):
            return False
        # ein zusammengesetztes Hauptwort, dessen Grundwort selbst ein Allerweltswort ist ("Wasserschaden" = Wasser +
        # Schaden, "Heizungsausfall"), ist kein Familienname; nur die letzten 30 Zeichen (linear je Wort)
        for i in range(max(3, len(w) - 30), len(w) - 3):
            if not w[i].isupper() and wissen.ist_allerweltswort(w[i].upper() + w[i + 1:]):
                return False
    except Exception:  # pragma: no cover - Wissensbasis beschädigt
        return False
    davor_start = max(0, m.start() - 20)
    if _BEGLEITER_DAVOR_RE.search(text, davor_start, m.start()) \
            or text[m.end(1):m.end(1) + 3].lstrip(" \t").startswith(":"):
        return False                                     # Satzteil bzw. Feldname ("Mieter Dachgeschoss: kein Schaden")
    if PERSON_LAUT_DAVOR_RE.search(text, davor_start, m.start()) or _KONTAKT_DAHINTER_RE.match(text, m.end(1)) \
            or _PERSONENWORT_FOLGT_RE.match(text, m.end(1)):
        return True
    if _satzanfang(text, m.start()):
        return verb_einer_person_dahinter(text, m.end(1))
    return (_PERSONENWORT_EINZAHL_RE.fullmatch(text[m.start():m.start(1)].rstrip()) is not None
            and not _ALS_DAVOR_RE.search(text, davor_start, m.start()))


def personenwort_namen(text: str, wissen=None, unsicher: list | None = None) -> list:
    """(start, ende) der Namen direkt hinter einem Personenwort ("Laut Nachbar Grohe", "mit Kollegin Zwickl", "Zeuge
    Hinterstoißer"; nicht "dem Nachbarn Wasser", "beim Nachbarn Regen"): ein großgeschriebenes Wort, das kein
    Allerwelts-, Berufs-, Orts-, Etikett- oder Titelwort ist und keine Substantiv-Endung trägt ("Nachbar
    Wasserschaden", "Kunden Service" nicht) – auch eine Marke ("Grohe"), die hier eine Person ist (Erkennung,
    namen.py).
    - Mitten im Satz ohne Begleiter ("Laut Nachbar Grohe", "Rücksprache mit Nachbar Grohe", "kam Monteur Grohe"): der
      Name; eine bekannte Marke hinter einer Präposition wird nur gemeldet ("Laut Monteur Buderus …"; A2-04).
    - Am Satz- oder Notizanfang mit einem Verb einer Person dahinter ("Monteur Grohe kam am 03.03.", "Nachbar Zettl hat
      den Brand gemeldet", "Der Vermieter Kranawetter hat gekündigt"): der Name, auch eine Marke oder ein mehrdeutiges
      Wort (Abnahme 3 AB3-02, AB3-03).
    - Am Satzanfang ohne solches Verb ("Chef Sekretariat ist besetzt") und hinter einem Begleiter ("beim Nachbarn
      Zirngibl"): nur mit eigenem Namensbeleg (_namensbeleg_personenwort; Abnahme 2 A2-04, V7). Ein Familienname, der
      zugleich ein gewöhnliches Wort ist, hinter einem Begleiter ("beim Mieter Schimmel", "dem Nachbarn Holz") ist kein
      sicherer Beleg: die Selbstkontrolle meldet ihn (Abnahme 3 AB3-04).
    Die Wörter hinter einem Begleiter ohne Namensbeleg ("beim Nachbarn Grohe", "dem Nachbarn Wasser") kommen in
    `unsicher`: die Erkennung entscheidet dort nach der Wortart im Satz (namen.py, Abnahme 2 V7). Was hier nicht als
    Name gilt, meldet die Selbstkontrolle (personenwort_kandidaten)."""
    if not text or not _PERSONENWORT_VORAB_RE.search(text):
        return []
    wissen = _wissen_oder_modul(wissen)
    if wissen is None:
        return []
    aus = []
    for m in _PERSONENWORT_NAME_RE.finditer(text):
        w = m.group(1)
        if not _personenwort_wort(w, wissen):
            if _allerwelt_als_name(text, m, wissen):
                aus.append((m.start(1), m.end(1)))
            continue
        davor_start = max(0, m.start() - 20)
        bm = _BEGLEITER_DAVOR_RE.search(text, davor_start, m.start())
        begleiter = bm is not None
        anfang = _satzanfang(text, bm.start() if begleiter else m.start())
        # Satzgegenstand: Personenwort am Satzanfang, dahinter ein Verb einer Person; oder eine Kontaktangabe dahinter –
        # eine Abteilung, Firmenrolle oder Lage ("Kollege Außendienst ruft zurück", "Mieter Nebenan hat …") nur mit
        # eigenem Namensbeleg, sonst gemeldet (Abnahme 4 AB4U-01)
        if (anfang and verb_einer_person_dahinter(text, m.end(1))) or _KONTAKT_DAHINTER_RE.match(text, m.end(1)):
            if not _org_gestalt(w) or _org_namensbeleg(w, wissen):
                aus.append((m.start(1), m.end(1)))
            continue
        if _org_gestalt(w) and not _org_namensbeleg(w, wissen):
            continue                                     # "Laut Kollege Vertrieb …": gemeldet, nicht geschwärzt
        # mitten im Satz ohne Begleiter: hinter einer Präposition oder einem Verb ("kam Monteur Grohe") – der Name
        sicher = not begleiter and (not anfang or bool(_PRAEPOSITION_DAVOR_RE.search(text, davor_start, m.start())))
        # eine bekannte Marke, die kein Vor- oder Nachname ist, hinter dem Personenwort einer Firma ("Laut Monteur
        # Buderus …" – der Monteur oder der Hersteller?), bleibt stehen: die Selbstkontrolle meldet sie als "Marke oder
        # Familienname im Personenkontext" (Abnahme 2, Probe p01 – auf 1b5130a gemeldet). Hinter einem Personenwort
        # des privaten Umfelds ("Laut Nachbar Miele", "Rücksprache mit Mieter Liebherr") ist sie der Name
        if _bekannte_marke(w, wissen) and _FIRMEN_PERSONENWORT_RE.match(text, m.start()):
            continue
        try:
            mehrdeutig = begleiter and wissen.ist_mehrdeutig(w)
        except Exception:  # pragma: no cover - Wissensbasis beschädigt
            mehrdeutig = False
        if mehrdeutig:
            continue                                     # "beim Mieter Schimmel": gemeldet, nicht geschwärzt
        if sicher or _namensbeleg_personenwort(w, wissen):
            aus.append((m.start(1), m.end(1)))
        elif begleiter and unsicher is not None and not text[m.end(1):m.end(1) + 3].lstrip(" \t").startswith(":"):
            unsicher.append((m.start(1), m.end(1)))
    return aus


# Berufswort am Satz- oder Notizanfang vor einem großgeschriebenen Wort ("Elektriker Miele kam am Montag.")
_GROSSWORT_VOR_GROSSWORT_RE = re.compile(r"(?<![\wäöüß\-])[A-ZÄÖÜ][a-zäöüß]{3,}(?=[ ]{1,2}[A-ZÄÖÜ])")
_NAME_DAHINTER_RE = re.compile(r"[ ]{1,2}([A-ZÄÖÜ][a-zäöüß]{2,}(?:-[A-ZÄÖÜ][a-zäöüß]+)?)(?![\wäöüß\-])")


def berufswort_namen(text: str, wissen=None, alle: bool = False, beruf_nachname: bool = False,
                     beleg_ohne_verb: bool = False) -> list:
    """(start, ende) der Namen hinter einem Berufswort der Wissensbasis am Satz- oder Notizanfang, wenn dahinter ein
    Verb einer Person oder eine Kontaktangabe steht ("Elektriker Miele kam am Montag.", "Techniker Neff, Tel. …"): wie
    hinter einem Personenwort (personenwort_namen) ist das Wort dort der Name (Abnahme 3 AB3-02: "hinter jedem
    Personenwort, auch hinter Berufen") – wenn es selbst für einen Namen spricht: eine bekannte Marke oder ein Vor- bzw.
    Familienname, der kein gewöhnliches Wort ist ("Schreiner Holz kam per Lkw." bleibt stehen). Ohne Verb oder
    Kontaktangabe bleibt es bei den übrigen Regeln. alle: auch die Wörter ohne solchen Beleg ("Handwerker Grohe kam …")
    – für die Selbstkontrolle, die sie meldet. beleg_ohne_verb (Selbstkontrolle): ein Wort mit eigenem Namensbeleg
    auch ohne Verb einer Person und hinter "laut"/"gemäß" ("Glaser Frost ist erst nächste Woche frei.", "Laut Klempner
    Dyson ist der Schaden älter."; Abnahme 4, Altbefund AB3-02) – gemeldet, nicht geschwärzt."""
    if not text:
        return []
    wissen = _wissen_oder_modul(wissen)
    if wissen is None:
        return []
    aus = []
    for m in _GROSSWORT_VOR_GROSSWORT_RE.finditer(text):
        n = _NAME_DAHINTER_RE.match(text, m.end())
        if not n:
            continue
        verb = bool(_PERSON_VERB_DAHINTER_RE.match(text, n.end(1)) or _KONTAKT_DAHINTER_RE.match(text, n.end(1)))
        if not verb and not beleg_ohne_verb:
            continue
        bm = _BEGLEITER_DAVOR_RE.search(text, max(0, m.start() - 20), m.start())    # "Der Elektriker Miele kam …"
        laut = beleg_ohne_verb and PERSON_LAUT_DAVOR_RE.search(text, max(0, m.start() - 30), m.start()) is not None
        if not laut and not _satzanfang(text, bm.start() if bm else m.start()):
            continue
        try:
            if not wissen.ist_beruf(m.group()):
                continue
        except Exception:  # pragma: no cover - Wissensbasis beschädigt
            continue
        w = n.group(1)
        if not _personenwort_wort(w, wissen, beruf_nachname):   # Selbstkontrolle: auch "Maler Kaplan kam …" (AB4-13)
            continue
        try:
            beleg = _bekannte_marke(w, wissen) or (_namensbeleg_personenwort(w, wissen) and not wissen.ist_mehrdeutig(w))
            if beleg and _org_gestalt(w) and not _org_namensbeleg(w, wissen):
                beleg = False                                   # "Techniker Wasserversorger hat …" (AB4U-01)
            if not beleg and not verb and beleg_ohne_verb:
                # ohne Verb: ein Vor- oder Nachname der Wissensbasis, auch mehrdeutig ("Glaser Frost ist …")
                beleg = (_namensbeleg_personenwort(w, wissen) or wissen.ist_nachname(w)) \
                    and not (_org_gestalt(w) and not _org_namensbeleg(w, wissen))
            if not beleg and laut:
                # hinter "laut <Beruf>" auch ein unbekanntes Wort ("Laut Zimmerer Hinterseer ist das Dach dicht."):
                # die Person, deren Angabe zitiert wird (Abnahme 5 A5-13; nur Selbstkontrolle)
                beleg = not _org_gestalt(w)
        except Exception:  # pragma: no cover - Wissensbasis beschädigt
            beleg = False
        if beleg or (alle and verb):
            aus.append(n.span(1))
    return aus


_PERSONENWORT_GANZ_RE = re.compile(_PERSONENWORT)


def ist_personenwort(wort: str) -> bool:
    """Ist das Wort ganz ein Personenwort (Nachbar, Mieterin, Kollege, Frau …)?"""
    return bool(wort) and _PERSONENWORT_GANZ_RE.fullmatch(wort) is not None


def personenwort_vor_name(text: str, start: int, ende: int, wissen=None) -> bool:
    """Ist text[start:ende] ein Personenwort, hinter dem ein möglicher Name steht ("Beim Schwager Schimmel brannte
    Licht": "Schwager" ist hier die Rolle, nicht der Familienname Schwager; Abnahme 4)? Für die KI-Spannen."""
    if not _PERSONENWORT_GANZ_RE.fullmatch(text, start, ende):
        return False
    m = _PERSONENWORT_NAME_RE.match(text, start)
    if m is None or m.start(1) <= ende:
        return False
    wissen = _wissen_oder_modul(wissen)
    return wissen is not None and _personenwort_wort(m.group(1), wissen, beruf_nachname=True)


def personenwort_allerwelt(text: str, wissen=None) -> list:
    """(start, ende) der Allerweltswörter direkt hinter einem Personenwort ohne Begleiter, die dort ein Familienname sein
    können: am Satzanfang mit einem Verb einer Person dahinter ("Nachbar Wasser hat angerufen."), hinter "laut"/"gemäß"
    ("Laut Nachbarin Regen war die Tür offen."), mitten im Satz ("Die Kosten trägt Mieter Wasser selbst.", "Er
    telefonierte mit Kollegen Wasser.") oder mit einer Kontaktangabe dahinter – für die Selbstkontrolle, die sie meldet
    (Abnahme 5 A5-05, Grundsatz P2: Alltagswort oder Familienname). Hinter einem Begleiter ("Er hat dem Nachbarn
    Wasser abgegraben.", "Beim Nachbarn Regen gemessen.") ist das Wort ein Satzteil und bleibt frei; ebenso Kalender-,
    Lage-, Leer- und Verweiswörter, Wörter mit Substantiv-Endung, Organisationswörter und Etiketten."""
    if not text or not _PERSONENWORT_VORAB_RE.search(text):
        return []
    wissen = _wissen_oder_modul(wissen)
    if wissen is None:
        return []
    aus = []
    for m in _PERSONENWORT_NAME_RE.finditer(text):
        w = m.group(1)
        k = w.casefold()
        try:
            if not wissen.ist_allerweltswort(w) or wissen.ist_beruf(w) or wissen.ist_anrede_titel(w):
                continue
        except Exception:  # pragma: no cover - Wissensbasis beschädigt
            continue
        if "-" in w or _SUBSTANTIV_ENDUNG_RE.search(w) or k in _KALENDER or k in _KEIN_NAME_VERWEIS \
                or k in _LAGE_ADVERB or _org_gestalt(w) or text[m.end(1):m.end(1) + 3].lstrip(" \t").startswith(":"):
            continue
        davor_start = max(0, m.start() - 20)
        if _BEGLEITER_SATZTEIL_DAVOR_RE.search(text, davor_start, m.start()):
            continue                                     # "dem Nachbarn Wasser abgegraben": ein Satzteil
        try:
            if any(wissen.index(f"etiketten_{art}").eintrag_fuer(w) is not None for art in wissen.ETIKETTEN_ARTEN):
                continue
        except Exception:  # pragma: no cover - Wissensbasis beschädigt
            continue
        # hinter einem Begleiter im Genitiv oder Nominativ ("Der Wagen des Nachbarn Regen …", "Die Nachbarin Wasser
        # hat …") ist das Wort kein Satzteil (Abnahme 5 A5-13)
        genitiv = _BEGLEITER_DAVOR_RE.search(text, davor_start, m.start()) is not None
        laut = PERSON_LAUT_DAVOR_RE.search(text, davor_start, m.start()) is not None
        anfang = _satzanfang(text, m.start())
        verb = anfang and verb_einer_person_dahinter(text, m.end(1))
        # mitten im Satz ohne Begleiter: der Name oder ein Satzteil ("Die Kosten trägt Mieter Wasser selbst.", "Er
        # telefonierte mit Kollegen Wasser.", "Er stellte sich als Nachbar Wasser vor.", aber auch "Er zeigte Kollegen
        # Fotos.") – gemeldet (auf 0230782 wurden "Wasser" und "Regen" dort geschwärzt); nicht hinter einem Genitiv auf
        # "-s" ("Nachbars Garten": ein Besitz)
        mitte = not anfang and not text[m.start():m.start(1)].rstrip().endswith("s")
        if genitiv or laut or verb or mitte or _KONTAKT_DAHINTER_RE.match(text, m.end(1)):
            aus.append((m.start(1), m.end(1)))
    return aus


# Zustand oder Vorgang einer Person hinter dem Wort ("Kollegin Pfarrer ist seit Montag im Urlaub.", "Kunde Halter wurde
# befragt."; Abnahme 5 A5-13) und ein Verb davor ("Gestern rief Mieter Pfarrer an.")
_PERSON_ZUSTAND_DAHINTER_RE = re.compile(r"(?i)[ \t]+(?:ist|war|wird|wurde)[ \t]+(?:seit|im|in|bei|am|nicht|noch|heute|"
                                         r"gestern|morgen|krank|verreist|erreichbar|zuständig|zustaendig|befragt|"
                                         r"informiert|angerufen|benachrichtigt|verständigt|verstaendigt|geladen|"
                                         r"vernommen|gebeten)(?![\wäöüß])")
_VERB_DAVOR_RE = re.compile(r"(?i)(?<![\wäöüß])(?:rief|ruft|kam|kommt|schrieb|schreibt|sagte|sagt|meldete|meldet|"
                            r"bestätigte|bestaetigte|erklärte|erklaerte)[ \t]+$")


def personenwort_rollenwort(text: str, wissen=None) -> list:
    """(start, ende) eines Berufs-, Titel- oder Rollenworts direkt hinter einem Personenwort, das dort ein Familienname
    sein kann ("Nachbarin Pfarrer hat angerufen.", "Rücksprache mit Mieter Käufer am Montag.", "Kunde Halter wurde
    befragt.", "Der Wagen des Mieters Pfarrer …"; Abnahme 5 A5-13) – für die Selbstkontrolle, die es meldet (P2: Rolle
    oder Name; die Erkennung nimmt Berufe, Titel und Etiketten hinter einem Personenwort aus). Ein Rollenwort aus den
    Etiketten zählt nur mit der Endung einer Person ("Käufer", "Halter"; nicht "Anschrift", "Name"); ein Allerweltswort
    hinter einem Begleiter bleibt ein Satzteil ("dem Nachbarn Wasser"); kein Wort vor einem Doppelpunkt."""
    if not text or not _PERSONENWORT_VORAB_RE.search(text):
        return []
    wissen = _wissen_oder_modul(wissen)
    if wissen is None:
        return []
    aus = []
    for m in _PERSONENWORT_NAME_RE.finditer(text):
        w = m.group(1)
        k = w.casefold()
        if "-" in w or _SUBSTANTIV_ENDUNG_RE.search(w) or k in _KALENDER or k in _KEIN_NAME_VERWEIS \
                or k in _LAGE_ADVERB or _PERSONENWORT_GANZ_RE.fullmatch(w) \
                or text[m.end(1):m.end(1) + 3].lstrip(" \t").startswith(":"):
            continue
        try:
            if wissen.ist_nachname(w) or wissen.ist_vorname(w) or wissen.ist_ort(w):
                continue                                 # Namen und Orte: die übrigen Regeln
            beruf_titel = bool(wissen.ist_beruf(w) or wissen.ist_anrede_titel(w))
            rolle = bool(re.search(r"(?:er|erin)$", w)) and any(
                wissen.index(f"etiketten_{art}").eintrag_fuer(w) is not None for art in wissen.ETIKETTEN_ARTEN)
            allerwelt = wissen.ist_allerweltswort(w)
        except Exception:  # pragma: no cover - Wissensbasis beschädigt
            continue
        if not (beruf_titel or rolle) or (_org_gestalt(w) and not beruf_titel):
            continue                                     # "Kollege Außendienst" (Organisation), "Nachbar Händler" zählt
        davor_start = max(0, m.start() - 20)
        if allerwelt and _BEGLEITER_SATZTEIL_DAVOR_RE.search(text, davor_start, m.start()):
            continue                                     # ein Satzteil hinter einem Begleiter
        # ohne Begleiter nur mit einem Beleg einer Person im Satz – eine Aufzählung beschreibt die Person ("Sohn
        # Auszubildender, Tochter Studentin"; Abnahme 3 AB3-03)
        if not _BEGLEITER_DAVOR_RE.search(text, davor_start, m.start()) \
                and not (PERSON_LAUT_DAVOR_RE.search(text, davor_start, m.start())
                         or _PRAEPOSITION_DAVOR_RE.search(text, davor_start, m.start())
                         or _PERSON_VERB_DAHINTER_RE.match(text, m.end(1))
                         or _PERSON_ZUSTAND_DAHINTER_RE.match(text, m.end(1))
                         or _KONTAKT_DAHINTER_RE.match(text, m.end(1))
                         or _VERB_DAVOR_RE.search(text, davor_start, m.start())):
            continue
        aus.append((m.start(1), m.end(1)))
    return aus


def personenwort_nur_meldung(text: str, wissen=None) -> set:
    """(start, ende) der Wörter hinter einem Personenwort, die nach personenwort_namen kein Name sind und die die
    Erkennung auch nicht über die KI schwärzt – die Selbstkontrolle meldet sie (personenwort_kandidaten):
    - hinter einem Begleiter ein Familienname, der zugleich ein gewöhnliches Wort ist ("beim Mieter Schimmel", "dem
      Nachbarn Holz", "beim Nachbarn Hagel"; Abnahme 3 AB3-04);
    - eine bekannte Marke, die kein Vor- oder Nachname ist, hinter dem Personenwort einer Firma direkt hinter "laut" oder
      "gemäß" ("Laut Monteur Hansgrohe ist die Kartusche baugleich." – der Monteur oder der Hersteller?; offener Punkt
      der vierten Nachbesserung, Probe p07). Mit einem Verb einer Person ("Monteur Hansgrohe kam …"), hinter "mit"
      ("Rücksprache mit Monteur …") und hinter Personenwörtern des privaten Umfelds ("Laut Nachbar Miele") bleibt es
      bei der Erkennung."""
    if not text or not _PERSONENWORT_VORAB_RE.search(text):
        return set()
    wissen = _wissen_oder_modul(wissen)
    if wissen is None:
        return set()
    namen_ = set(personenwort_namen(text, wissen))
    # nur hinter einem Begleiter, hinter dem das Wort ein Satzteil sein kann ("beim Mieter Schimmel festgestellt", "dem
    # Nachbarn Holz gebracht") – im Genitiv ist es der Name ("Die Kaution des Mandanten Wolf ist offen.": weiter über die
    # KI geschwärzt wie bis 5efcc0c; die gebeugten Personenwörter der siebten Nachbesserung, A5-13, erweitern die
    # Ausnahme nicht auf den Genitiv)
    satzteil = {m.span(1) for m in _PERSONENWORT_NAME_RE.finditer(text)
                if _BEGLEITER_SATZTEIL_DAVOR_RE.search(text, max(0, m.start() - 20), m.start())}
    aus = set()
    for s, e, begleiter, _ in personenwort_kandidaten(text, wissen):
        try:
            if begleiter and (s, e) in satzteil and (s, e) not in namen_ and wissen.ist_mehrdeutig(text[s:e]):
                aus.add((s, e))
        except Exception:  # pragma: no cover - Wissensbasis beschädigt
            continue
    for m in _PERSONENWORT_NAME_RE.finditer(text):
        s, e = m.span(1)
        if (s, e) in namen_ or (s, e) in aus or not _FIRMEN_PERSONENWORT_RE.match(text, m.start()):
            continue
        davor = max(0, m.start() - 25)
        if PERSON_LAUT_DAVOR_RE.search(text, davor, m.start()) and _personenwort_wort(m.group(1), wissen) \
                and _bekannte_marke(m.group(1), wissen):
            aus.add((s, e))
    return aus


def _bekannte_marke(w: str, wissen) -> bool:
    """Eine Marke der Wissensbasis, die kein Vor- oder Nachname ist ("Buderus", "Vaillant"; nicht "Bosch")?"""
    try:
        return bool(wissen.index("sachnamen").finde(w)) and not (wissen.ist_nachname(w) or wissen.ist_vorname(w))
    except Exception:  # pragma: no cover - Wissensbasis beschädigt
        return False


_PERSONENWORT_VORAB_RE = re.compile(_PERSONENWORT + r"[ ]{1,2}[A-ZÄÖÜ]")
# Begleiter vor dem Personenwort: dann ist es ein Satzteil ("dem Nachbarn Bescheid gegeben") – die Regel gilt nur ohne
_BEGLEITER_DAVOR_RE = re.compile(r"(?i)(?<![\wäöüß])(?:der|die|das|dem|den|des|beim|vom|zum|zur|im|am|ein|eine|einem|"
                                 r"einen|einer|eines|kein\w*|unser\w*|mein\w*|dein\w*|sein\w*|ihr\w*|eure?\w*|"
                                 r"dies\w*|jen\w*|jed\w*|welch\w*)[ \t]+$")
# Begleiter, hinter dem ein gewöhnliches Wort ein Satzteil sein kann ("Er hat dem Nachbarn Wasser abgegraben.", "Beim
# Nachbarn Regen gemessen.") – nicht im Genitiv oder Nominativ ("Der Wagen des Mandanten Halter", "Die Tante Halter hat
# …"; Abnahme 5 A5-13)
_BEGLEITER_SATZTEIL_DAVOR_RE = re.compile(r"(?i)(?<![\wäöüß])(?:dem|den|beim|vom|zum|zur|im|am|einem|einen|"
                                          r"(?:mein|dein|sein|ihr|unser|euer|eur|dies|jed|kein|welch)(?:em|en))[ \t]+$")
# schwächerer Hinweis im Satz: "laut Wallach ist …" – für die Selbstkontrolle (Verdacht statt Schwärzung)
PERSON_LAUT_DAVOR_RE = re.compile(r"(?i)(?<![\wäöüß])(?:laut|lt\.|gemäß|nach[ \t]+angaben[ \t]+von)[ \t]+$")


# Organisationswort in der Zeile ("Neff Kundendienst Süd", "Ihr Miele Team", "Vaillant Werkskundendienst"): eine Marke
# darin ist die Firma, die grüßt oder liefert – kein Familienname (Nachprüfung Ü-NP-13)
ORG_ZEILE_RE = re.compile(r"(?i)(?<![\wäöüß])(?:[\wäöüß]*kundendienst|kundenservice|[\wäöüß]*service|team|center|zentrale|"
                          r"filiale|niederlassung|hotline|vertrieb|abteilung|werkstatt|autohaus|support|shop|store)"
                          r"(?![\wäöüß])")


# Organisationseinheit unter einem Gruß ("Allgäuer Versicherungsdienst", "Maklerbetreuung Bayern", "Produktmanagement
# Sach", "Bauleitung Wohnpark Ost", "Ihr Vertriebsteam Süd"): kein Unterzeichner (Abnahme 2 A2-06)
ORG_EINHEIT_RE = re.compile(r"(?i)(?<![\wäöüß])[\wäöüß]{0,25}(?:dienst|service|betreuung|management|leitung|team|"
                            r"abteilung|büro|buero|agentur|kontor|zentrale|vertrieb|filiale|niederlassung|"
                            r"geschäftsstelle|arbeitskreis|verwaltung|unternehmer|gruppe|redaktion|center|kanzlei)"
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
# ihren Wohnort zugleich (Nachprüfung NP-14); "Beim"/"Vom"/"Zum" auch am Satz- und Feldanfang ("Beim Stögerbauer
# ereignete sich der Unfall", "Schadenort: Beim Stögerbauer" – Nachbesserung n2)
_HOF_KOPF_RE = re.compile(r"(?<![\wäöüß\-])(?:(Hof|Anwesen|Gehöft|Bauernhof|Hofstelle|Hofgut|Gutshof|Aussiedlerhof)"
                          # mit Genitiv: "Unfall vor dem Hof des Zellerbauern" (Abnahme 2 V2)
                          r"(?:[ \t]+(?:des|vom))?|([Bb]eim|[Vv]om|[Zz]um))[ \t]+(?=[A-ZÄÖÜ])")
_HOF_NAME_RE = re.compile(r"[A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)?(?![\wäöüß\-])")
# Ort eines Ereignisses oder Wohnorts in derselben Zeile: ein Orts-Etikett mit Doppelpunkt oder ein Ereignis-/Wohnwort,
# auch als Zusammensetzung ("Wasserschaden", "Sturmschaden", "Brandschaden") und als Verb ("brannte", "eingebrochen";
# Abnahme N2)
_HOF_ORTSKONTEXT_RE = re.compile(
    r"(?i)(?<![\wäöüß])(?:(?:unfall|schadens?|ereignis|tat|risiko|versicherungs|wohn|stand|abstell|einsatz)?ort|"
    r"unfallstelle|schadenstelle|lage|anschrift|adresse|belegenheit)[ \t]*:|"
    r"(?<![\wäöüß])(?:[\wäöüß]*(?:unfall|unfälle|schaden|schäden|brand|brände|einbruch|diebstahl)(?:s|es|n|en|e)?|"
    r"sturm|hagel|"
    r"zusammensto(?:ß|ss)|kollision|geschah|passierte|ereignete|brannte|brennt|gebrannt|abgebrannt|feuer|blitz\w*|"
    r"überschwemm\w*|hochwasser|rohrbruch|eingebrochen|einbrecher|gestohlen|unwetter|explosion|"
    r"wohnt|wohnen|wohnte|lebt|leben|lebte|zufahrt|einfahrt|hofeinfahrt|weide|stall|stadel|scheune|tenne)(?![\wäöüß])")
# Ortsangabe direkt hinter dem Hausnamen: "beim Huberbauer in Anger", "vom Moarhofer aus Teisendorf", "zum Huberbauer
# nach Anger" – der Ort darf ein kleiner sein, den die Wissensbasis nicht kennt, aber kein Allerweltswort (Abnahme N2)
_HOF_ORT_DANACH_RE = re.compile(r"[ \t]+(?:in|nach|bei|aus)[ \t]+([A-ZÄÖÜ][a-zäöüß]{2,}(?:-[A-ZÄÖÜ][a-zäöüß]+)?)"
                                r"(?![\wäöüß])")


# Endungen bairischer Haus- und Hofnamen: ohne Ereigniswort zählt die Ortsangabe dahinter nur bei einem Wort mit
# einer solchen Endung oder einem Familiennamen der Wissensbasis ("zum Huberbauer nach Anger" – nicht "zum Discounter
# nach Rosenheim")
_HAUSNAME_ENDUNG_RE = re.compile(r"(?:bauer|hofer|huber|maier|mayr|meier|mair|moser|bichler|lehner|leitner|reiter|"
                                 r"egger|wieser|bacher|berger|hauser|müller|schuster|wirt|loher|rainer|stetter|"
                                 r"stätter|staetter)$")
# gebeugte Hausnamen ("des Zellerbauern", "zum Zellerbauern", "beim Gruberwirts"; Abnahme 2 V2)
_HAUSNAME_BEUGUNG_RE = re.compile(r"(?:bauern|wirts|wirtes|hofers)$")
# Betriebe statt Hausnamen hinter "beim"/"zum" ("beim Holzhändler in Waging", "beim Gartencenter in Rosenheim";
# Abnahme 2 A2-07) – außer ein bekannter Familienname
_BETRIEB_ENDUNG = ("händler", "haendler", "center", "zentrum", "theater", "markt", "laden", "handel", "werkstatt",
                   "betrieb", "service", "verleih", "club", "verein")


def _hausname_gestalt(wort: str, wissen) -> bool:
    try:
        if wissen.ist_nachname(wort) and not wissen.ist_mehrdeutig(wort):
            return True
    except Exception:  # pragma: no cover - Wissensbasis beschädigt
        return False
    k = wort.casefold()
    return len(wort) >= 7 and bool(_HAUSNAME_ENDUNG_RE.search(k) or _HAUSNAME_BEUGUNG_RE.search(k))


def _ort_danach(text: str, pos: int, wissen) -> bool:
    m = _HOF_ORT_DANACH_RE.match(text, pos)
    if m is None:
        return False
    ort = m.group(1)
    try:
        if wissen.ist_ort(ort):
            return True
        return not (_SUBSTANTIV_ENDUNG_RE.search(ort) or wissen.ist_allerweltswort(ort) or wissen.ist_beruf(ort)
                    or wissen.ist_anrede_titel(ort))
    except Exception:  # pragma: no cover - Wissensbasis beschädigt
        return False


def _hofname_wort(wort: str, wissen) -> bool:
    """Kann das Wort hinter "Hof"/"Anwesen"/"beim" ein Familien- oder Hausname sein: großgeschrieben, kein Allerwelts-,
    Orts-, Berufs- oder Etikettwort, kein Vorname, keine Substantiv-Endung ("beim Einparken", "zum Hof", "Hof Süd")?"""
    if len(wort) < 4 or _SUBSTANTIV_ENDUNG_RE.search(wort):
        return False
    try:
        if wissen.ist_nachname(wort) and not wissen.ist_mehrdeutig(wort):
            return True
        if wort.casefold().endswith(_BETRIEB_ENDUNG):
            return False                                # "beim Holzhändler", "beim Gartencenter"
        if (wissen.ist_allerweltswort(wort) or wissen.ist_allowlist(wort) or wissen.ist_ort(wort)
                or wissen.ist_beruf(wort) or wissen.ist_vorname(wort) or wissen.ist_anrede_titel(wort)):
            return False
        return not any(wissen.index(f"etiketten_{art}").eintrag_fuer(wort) is not None
                       for art in wissen.ETIKETTEN_ARTEN)
    except Exception:  # pragma: no cover - Wissensbasis beschädigt
        return False


# Aufenthalt oder Besuch bei einer Familie bzw. einem Hof ("Wir waren beim Pfnürl zum Essen.", "Er arbeitet beim
# Kaltl als Knecht.", "Ich war gestern beim Huberbauer zu Besuch."; Abnahme 4 AB4-15)
_HOF_BESUCH_RE = re.compile(r"(?i)(?<![\wäöüß])(?:(?:war|waren|bin|sind|sei|seien|wäre|wären|arbeitet|arbeitete|"
                            r"wohnt|wohnte|übernachtete|uebernachtete)(?:[ \t]+[a-zäöüß]+){0,2}[ \t]+beim(?![\wäöüß])|"
                            r"zum[ \t]+(?:essen|kaffee|mittagessen|abendessen|frühstück)|zu[ \t]+(?:besuch|gast)|"
                            r"eingeladen)(?![\wäöüß])")
# Entfernung zu einem Hof ("Zum Wimmer sind es nur zwei Kilometer.", "Bis zum Huber fährt man zehn Minuten.")
_HOF_ENTFERNUNG_RE = re.compile(r"(?i)(?<![\wäöüß])(?:\d+|ein|eine|zwei|drei|vier|fünf|zehn|paar|wenige)[ \t]+"
                                r"(?:kilometer|km|meter|minuten|min\.?|gehminuten|fahrminuten)(?![\wäöüß])")
# Weg zu einem Hof ("Zum Gruber fahren wir am Montag.", "Beim Wimmer schauen wir vorbei.") und Besitz eines Hofs
# ("Der Traktor vom Wimmer stand quer auf der Fahrbahn.", "Die Kühe vom Gruber"): nur für ein Wort mit der Gestalt eines
# Familiennamens (Abnahme 5 A5-14; "Anbei das Foto vom Kratzer" bleibt beim Melden)
_HOF_WEG_RE = re.compile(r"(?i)(?<![\wäöüß])(?:fahren|fahre|fährt|faehrt|fuhr|fuhren|gehen|gehe|geht|ging|gingen|"
                         r"laufen|läuft|laeuft|lief|liefen|radeln|radelt|bringen|bringt|brachte|brachten|liefern|"
                         r"liefert|lieferte|hinauf|hinüber|hinueber|rüber|rueber|vorbei[a-zäöüß]*)(?![\wäöüß])")
_HOF_BESITZ_VOR_RE = re.compile(r"(?i)(?<![\wäöüß])(?:traktor|bulldog|schlepper|auto|wagen|pkw|lkw|anhänger|"
                                r"anhaenger|hund|hunde|katze|pferd|pferde|kuh|kühe|kuehe|kälber|kaelber|rinder|vieh|"
                                r"schafe|ziegen|hühner|huehner|haus|stadel|scheune|stall|garten|feld|felder|acker|"
                                r"wiese|wiesen|wald|grundstück|grundstueck|tochter|töchter|toechter|sohn|söhne|soehne|"
                                r"bub|buben|knecht|magd|bäuerin|baeuerin|leute)[ \t]+$")


def hofnamen(text: str, wissen) -> list:
    """(start, ende) der Hof- und Hausnamen: hinter "Hof", "Anwesen", "Gehöft" … ein möglicher Familienname
    (_hofname_wort) mit Namensgestalt oder in einer Zeile mit Orts- bzw. Ereigniskontext ("Unfallort: Zufahrt zum Hof
    Hintermoser"); hinter "beim"/"vom"/"zum" nur ein Wort mit Namensgestalt in einer solchen Zeile ("Der Unfall geschah
    beim Stögerbauer", "Wasserschaden beim Stögerbauer") oder mit einer Ortsangabe direkt dahinter ("zum Huberbauer
    nach Anger"; Abnahme N2). Nicht: "beim Einparken", "zum Hof", "Hof Süd", "beim Bäcker in Inzell"."""
    if wissen is None:
        return []
    aus = []
    kontext_je_zeile: dict = {}
    za, letztes_ende = 0, -1
    for m in _HOF_KOPF_RE.finditer(text):
        n = _HOF_NAME_RE.match(text, m.end())
        if n is None or not _hofname_wort(n.group(0), wissen) \
                or personenwort_vor_name(text, n.start(), n.end(), wissen):
            continue                                     # "Beim Schwager Schimmel …": Rolle vor dem Namen
        try:
            if geraete_kompositum(n.group(0)) and not wissen.ist_nachname(n.group(0)):
                continue                                 # "Vom Gabelstapler kam der Anruf …" (Abnahme 5 A5-02)
        except Exception:  # pragma: no cover - Wissensbasis beschädigt
            pass
        if m.start() > letztes_ende:                    # Zeilenanfang nur beim Zeilenwechsel suchen
            za = text.rfind("\n", 0, m.start()) + 1
        if za not in kontext_je_zeile:
            ze = text.find("\n", m.start())
            ze = len(text) if ze < 0 else ze
            letztes_ende = ze
            # Ort oder Ereignis, Besuch ("Wir waren gestern beim Gruber zum Essen.") oder Entfernung ("Zum Wimmer sind es
            # nur zwei Kilometer."): ein Hof bzw. eine Familie; ein Weg dorthin ("Zum Gruber fahren wir am Montag.")
            # zählt für "zum"/"beim" (Abnahme 5 A5-14)
            kontext_je_zeile[za] = (bool(_HOF_ORTSKONTEXT_RE.search(text, za, ze) or _HOF_BESUCH_RE.search(text, za, ze)
                                         or _HOF_ENTFERNUNG_RE.search(text, za, ze)),
                                    bool(_HOF_WEG_RE.search(text, za, ze)))
        haus = _hausname_gestalt(n.group(0), wissen)
        gestalt = namensgestalt(n.group(0), wissen) or haus
        zeile_kontext, weg = kontext_je_zeile[za]
        kontext = zeile_kontext or (_ort_danach(text, n.end(), wissen) and haus)
        if not kontext and m.group(2):
            # Weg und Besitz nur für einen Familiennamen der Wissensbasis ("Zum Gruber fahren wir", nicht "Er fuhr zum
            # Discounter"; ein unbekanntes Wort meldet hofnamen_kandidaten)
            try:
                bekannter_name = wissen.ist_nachname(n.group(0)) and not wissen.ist_mehrdeutig(n.group(0))
            except Exception:  # pragma: no cover - Wissensbasis beschädigt
                bekannter_name = False
            if not bekannter_name:
                pass
            elif m.group(2).casefold() == "vom":
                # Besitz direkt davor ("Der Traktor vom Wimmer"); die Suche ist auf 40 Zeichen begrenzt
                kontext = bool(_HOF_BESITZ_VOR_RE.search(text, max(za, m.start() - 40), m.start()))
            else:
                kontext = weg
        # hinter "beim"/"vom"/"zum" ein Wort mit der Endung eines Hausnamens auch ohne Ereignis ("Er arbeitet beim
        # Wastlbauer als Knecht", "Die Kühe vom Lechnerbauer", "zum Zellerbauern hinauf"; Abnahme 2 V2) – nur die
        # Endung, nicht jeder Nachname der Wissensbasis ("Anbei das Foto vom Kratzer/Kleber": ein Sachwort; Abnahme 3
        # AB3-04 – die Selbstkontrolle meldet den Nachnamen)
        k = n.group(0).casefold()
        endung = len(k) >= 7 and bool(_HAUSNAME_ENDUNG_RE.search(k) or _HAUSNAME_BEUGUNG_RE.search(k))
        # ein Familienname der Wissensbasis, der kein gewöhnliches Wort ist ("beim Brandl", "vom Lindinger"; Abnahme 4
        # AB4-10) – ein mehrdeutiger ("beim Schimmel") meldet die Selbstkontrolle; ein Nomen auf "-er" ohne die Endung
        # eines Familiennamens ("vom Kratzer", "vom Kleber": Kratzer und Kleber sind auch Familiennamen) braucht den
        # Kontext einer Zeile (Ort, Ereignis, Besuch, Entfernung: "beim Gruber zum Essen", "Zum Wimmer sind es zwei
        # Kilometer"; Abnahme 5 A5-14) und bleibt sonst beim Melden
        try:
            bekannt = wissen.ist_nachname(n.group(0)) and not wissen.ist_mehrdeutig(n.group(0)) \
                and not wissen.ist_vorname(n.group(0)) and not k.endswith(_BETRIEB_ENDUNG) \
                and (not k.endswith("er") or bool(_NACHNAMEN_ENDUNG_RE.search(k)))
        except Exception:  # pragma: no cover - Wissensbasis beschädigt
            bekannt = False
        if (m.group(1) and (gestalt or kontext)) or (m.group(2) and ((gestalt and kontext) or endung or bekannt)):
            aus.append((n.start(), n.end()))
    return aus




# Sichere Gegenbelege eines Worts hinter "beim"/"vom"/"zum" (Abnahme 5 AB5U-02) – nie für einen Familiennamen der
# Wissensbasis, nie für die Gestalt eines Familien- oder Hausnamens:
# - ein substantiviertes Verb: Endung "-ieren" ("beim Rangieren", "beim Renovieren"), "-eln"/"-ern" ("beim Segeln",
#   "beim Wandern"), eine abtrennbare Vorsilbe vor "-en" ("beim Einkaufen", "beim Ausparken", "beim Aufräumen") oder ein
#   Bewegungsverb als Grundwort ("beim Skifahren", "beim Spazierengehen")
# - ein Kompositum, dessen Grundwort ein gewöhnliches Wort, ein Beruf oder ein Etikett ist und kein Bestandteil eines
#   Haus- oder Familiennamens ("beim Baumarkt", "vom Volksfest", "beim Autohändler" – nicht "Huberbauer", "Moarhof")
# - ein Ereignis- oder Wetterwort, das kein Familienname ist ("vom Blitz", "beim Unfall"; "vom Sturm" bleibt gemeldet)
# - ein Bindestrich-Kompositum aus gewöhnlichen Wörtern ("zum Einbruchdiebstahl-Risiko")
# - eine feste Wendung ("zum Glück", "zum Schutz", "zum Beispiel")
_VERB_NOMINAL_RE = re.compile(r"(?:ieren|[^aeiouäöü]eln|[^aeiouäöü]ern)$")
_VERB_VORSILBE_EN_RE = re.compile(r"(?i)(?:ein|aus|auf|ab|an|um|über|ueber|unter|zurück|zurueck|durch|weg|vor|nach|"
                                  r"zu|los|mit|her|hin|heim|fest|frei|kaputt|sauber|leer|voll)[a-zäöüß]{3,}en$")
_VERB_GRUNDWORT_EN_RE = re.compile(r"(?i)[a-zäöüß]{2,}(?:fahren|gehen|laufen|steigen|springen|fallen|rutschen|"
                                   r"stürzen|stuerzen|stolpern|schieben|ziehen|tragen|heben|parken|biegen|wenden)$")
# substantivierter Infinitiv eines unbekannten Worts ("beim Grillen", "beim Schwimmen", "vom Laufen"): Mitlaut vor
# "-en" – Familien- und Hausnamen der Wissensbasis und mit Namensgestalt sind vorher ausgeschlossen (Abnahme 5 AB5U-02)
_VERB_INFINITIV_RE = re.compile(r"(?:[bcdfgklmnprstvwxzß]|ch|ck|tz|ss)en$")
HOF_EREIGNIS_WETTER = _HOF_EREIGNIS_WETTER = frozenset("""unfall einbruch diebstahl brand feuer rauch blitz blitzschlag sturm orkan hagel
regen starkregen schnee eis glatteis frost wind gewitter unwetter hochwasser überschwemmung ueberschwemmung wasser
sturz aufprall zusammenstoß zusammenstoss schimmel rost""".split())
_HOF_WENDUNG_RE = re.compile(r"(?i)(?<![\wäöüß])(?:zum[ \t]+(?:glück|glueck|schutz|beispiel|teil|schluss|thema|"
                             r"ausgleich|erhalt|ablauf|abschluss|zeitpunkt|stichtag|nachweis|vergleich|abschied|"
                             r"verkauf|kauf|wohl|ende|anfang)|beim[ \t]+(?:besten|ersten|zweiten|nächsten|naechsten)|"
                             r"vom[ \t]+(?:feinsten|besten|ersten))(?![\wäöüß])")
_HAUS_FAMILIE_GRUNDWORT_RE = re.compile(r"(?i)(?:hof|höfe|hoefe|haus|häusl|haeusl|gut|mühle|muehle|mühl|muehl|wirt|"
                                        r"bauer|bauern|huber|hofer|maier|mayr|meier|mair|moser|müller|mueller|"
                                        r"schuster|berger|bichler|lehner|leitner|reiter|egger|wieser|bacher|hauser|"
                                        r"loher|rainer|stetter|stätter|staetter|eder|auer)$")


def _hof_gegenbeleg(text: str, start: int, w: str, wissen) -> bool:
    """Spricht das Wort hinter "beim"/"vom"/"zum" sicher gegen einen Haus- oder Familiennamen (siehe oben)?"""
    try:
        if geraete_kompositum(w) and not wissen.ist_nachname(w):
            return True                                 # "Vom Gabelstapler kam der Anruf" (Abnahme 5 A5-02)
        if wissen.ist_nachname(w) or wissen.ist_vorname(w) or namensgestalt(w, wissen) or _hausname_gestalt(w, wissen):
            return bool(_HOF_WENDUNG_RE.search(text, max(0, start - 5), start + len(w)))   # "zum Glück"
    except Exception:  # pragma: no cover - Wissensbasis beschädigt
        return False
    if _HOF_WENDUNG_RE.search(text, max(0, start - 5), start + len(w)):
        return True
    k = w.casefold()
    if _VERB_NOMINAL_RE.search(k) and not _HAUSNAME_BEUGUNG_RE.search(k) and len(k) >= 6:
        return True                                     # "beim Rangieren", "beim Segeln", "beim Wandern"
    if _VERB_VORSILBE_EN_RE.fullmatch(k) or _VERB_GRUNDWORT_EN_RE.fullmatch(k):
        return True                                     # "beim Einkaufen", "beim Skifahren"
    if _VERB_INFINITIV_RE.search(k) and len(k) >= 6:
        return True                                     # "beim Grillen", "beim Schwimmen", "vom Laufen" (kein Name)
    if k in _HOF_EREIGNIS_WETTER:
        return True                                     # "vom Blitz" (Familiennamen sind oben ausgeschlossen)
    try:
        from . import namen as namen_modul
        if not _HAUS_FAMILIE_GRUNDWORT_RE.search(k) and namen_modul._ist_sachwort(w):
            return True                                 # Sachwort der Erkennung ("beim Supermarkt", "vom Baumarkt")
    except Exception:  # pragma: no cover - Wissensbasis beschädigt
        return False
    teile = [t for t in w.split("-") if t]
    try:
        if len(teile) >= 2 and all(wissen.ist_allerweltswort(t) or wissen.ist_beruf(t) or t.isupper()
                                   for t in teile[-1:]) and not any(wissen.ist_nachname(t) for t in teile):
            return True                                 # "zum Einbruchdiebstahl-Risiko", "beim Kfz-Händler"
        if _HAUS_FAMILIE_GRUNDWORT_RE.search(k):
            return False
        for i in range(3, len(w) - 2):
            grund = w[i].upper() + w[i + 1:]
            if len(grund) >= 3 and (wissen.ist_allerweltswort(grund) or wissen.ist_beruf(grund)
                                    or any(wissen.index(f"etiketten_{art}").eintrag_fuer(grund) is not None
                                           for art in wissen.ETIKETTEN_ARTEN)):
                return True                             # "beim Baumarkt", "vom Volksfest", "beim Autohändler"
    except Exception:  # pragma: no cover - Wissensbasis beschädigt
        return False
    return False


def hofnamen_kandidaten(text: str, wissen) -> list:
    """(start, ende) der Wörter hinter "beim"/"vom"/"zum", die ein Haus- oder Familienname sein können, die hofnamen
    aber nicht schwärzt (ohne Hausnamen-Endung, ohne Namensgestalt, auch ein Betrieb wie "Kohlhändler") – in einer
    Zeile mit Ereignis- oder Ortskontext bzw. mit einem Verb einer Person dahinter ("Vom Kaltl kam der Anruf wegen des
    Hagelschadens.", "Beim Kohlhändler ist der Stadel abgebrannt."): für die Selbstkontrolle, die sie meldet (Abnahme 4
    AB4-15; Grundsatz P1) – außer mit einem sicheren Gegenbeleg (_hof_gegenbeleg; Abnahme 5 AB5U-02). Der Kontext wird
    je Zeile einmal gesucht (eine lange Zeile mit vielen Treffern wächst sonst quadratisch; AB5U-10)."""
    if wissen is None or not text:
        return []
    sicher = set(hofnamen(text, wissen))
    aus = []
    za = ze = -1                                        # aktuelle Zeile [za, ze) – nur beim Zeilenwechsel neu gesucht
    zeile_kontext = zeile_weg = False
    for m in _HOF_KOPF_RE.finditer(text):
        if not m.group(2):
            continue
        n = _HOF_NAME_RE.match(text, m.end())
        if n is None or (n.start(), n.end()) in sicher or personenwort_vor_name(text, n.start(), n.end(), wissen):
            continue
        w = n.group(0)
        if not (_hofname_wort(w, wissen) or (w.casefold().endswith(_BETRIEB_ENDUNG) and len(w) >= 8
                                               and _hofname_wort(w[:1] + "x" * 8, wissen))):
            continue
        if text[n.end():n.end() + 1] in ("!", "?"):
            continue                                    # "Vom Kalt! kam …": ein Ausruf, der Satz endet dort
        if _hof_gegenbeleg(text, n.start(), w, wissen):
            continue
        if m.start() > ze:
            za = text.rfind("\n", 0, m.start()) + 1
            ze = text.find("\n", m.start())
            ze = len(text) if ze < 0 else ze
            zeile_kontext = bool(_HOF_ORTSKONTEXT_RE.search(text, za, ze) or _HOF_BESUCH_RE.search(text, za, ze)
                                 or _HOF_ENTFERNUNG_RE.search(text, za, ze))
            zeile_weg = bool(_HOF_WEG_RE.search(text, za, ze))
        # auch ein Weg dorthin ("Zum Grebl fahren wir am Montag.") und Besitz ("Die Kühe vom Gsödl", "Das Auto vom
        # Moierl wurde beschädigt."; Abnahme 5 AB5U-02/A5-14: nie still für einen unbekannten Familiennamen)
        weg_besitz = (zeile_weg if m.group(2).casefold() != "vom"
                      else _HOF_BESITZ_VOR_RE.search(text, max(za, m.start() - 40), m.start()) is not None)
        if zeile_kontext or weg_besitz or _PERSON_VERB_DAHINTER_RE.match(text, n.end()) \
                or _HOF_KAM_DAHINTER_RE.match(text, n.end(), min(ze, n.end() + 40)):
            aus.append((n.start(), n.end()))
    return aus


_HOF_KAM_DAHINTER_RE = re.compile(r"[ \t]+(?:kam|kamen|rief|riefen|meldete|meldeten)(?![\wäöüß])")


# Mundartliche Namensfolge mit Artikel: "die Kölbl Resi", "der Gruber Sepp" – Familienname vor dem Rufnamen (Nachprüfung
# LK-14)
# auch am Satzanfang ("Die Huber Zenzi saß am Steuer."; Abnahme 2 widerlegt-7)
_ARTIKEL_NAME_RE = re.compile(r"(?<![\wäöüß])(?:[Dd]er|[Dd]ie|dem|den|[Vv]om|[Bb]eim|[Zz]um|zur)[ \t]+"
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
# (Bürgschaft, Darlehen, privat: "Kautionsbürgschaft ⇥⇥ Adam Riese ⇥⇥ 3.600 EUR") – Bürgschaft und Darlehen auch in
# Zusammensetzungen, "privat" nur als eigenes Wort oder für eine Person ("Privatperson(en)", "Privatkredit"): eine
# Sparte oder Kundengruppe ("Privathaftpflicht", "Privatrechtsschutz", "Private Haftpflicht", "Privatkunden") nennt
# den Versicherer, keine Person (eigene Nachprobe mit Fall c04 der Nachprüfung B)
_PERSON_ZEILE_RE = re.compile(r"(?i)bürgschaft|bürge|bürgin|darlehen|"
                              r"(?<![\wäöüß])privat(?:person(?:en)?|leute|kredit)?(?![\wäöüß])")


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
