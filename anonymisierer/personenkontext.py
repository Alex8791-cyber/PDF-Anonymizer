"""Personenkontext – EINE Regel für die Erkennung (detektoren/wissen_kontext.py) und die Selbstkontrolle
(restrisiko.py), damit beide dieselben Rollen und dieselbe Form kennen (wie kennungsformen.py für Kennungen):

Familien- und Versichertenkontext für Geburtsdaten ohne Stichwort (Domänen-Durchsicht Runde 5): In
Familienversicherung, Kindertarif, Reise- und Gruppenversicherung stehen Geburtsdaten oft ohne "geb." direkt am Namen
("Kind 2: Bastian Leutgeb, 30.06.2018", "Kinder: Ben (02.05.2019) und Lotta (17.10.2021)", "Reisende: Kranich,
Detlef, 12.04.1969; …", die Kinderliste mit Tabstopps unter "Kinder:"). Ein Datum direkt am Namen ist dort ein
Geburtsdatum in jedem Alter – aber nur mit einer Familien-/Versichertenrolle in derselben Zeile vor dem Namen oder als
Überschrift des Blocks darüber, ohne Titel, Praxis oder Klinik vor dem Namen (ein Behandler: sein Datum ist ein
Behandlungsdatum) und ohne Behandlungstext hinter dem Datum ("…, 03.11.2012: Meniskusoperation").

Dazu weitere geteilte Personenregeln derselben Durchsicht: Namen in Wohn- und Nachbarschaftsangaben ("unseres
Nachbarn Felsberger", "EG links (Hackenschmied)"), Tierangaben und medizinische Fachwörter (keine Personen), die
USt-IdNr. von Einzelkaufleuten und Inhabern (eine Angabe der Person), die Felder C.1.1/C.1.2 der
Zulassungsbescheinigung Teil I und Familiennamen einer GbR oder Erbengemeinschaft.

Öffentliche Schnittstelle:
    FAMILIE_RE, FAMILIE_KOPF_RE, BEHANDLER_DAVOR_RE, BETRAG_IN_ZEILE_RE
    familien_kontext(text, zeilenanfang, name_start) -> bool
    familien_rolle_in_zeile(text, zeilenanfang, name_start) -> bool
    behandlungsdatum(davor_bis_name, text, datum_ende) -> bool
    wohn_kontext_namen(text) -> [(start, ende)], namensgestalt(wort, wissen) -> bool
    tierangabe(text, start) -> bool, medizinisch(wort, text, start) -> bool
    ust_umgebung(text, start) -> str, ust_id_der_firma(umgebung) -> bool, ust_id_einer_person(umgebung) -> bool
    zb1_seite(text) -> bool, zb1_personenfelder(text) -> [(start, ende)]
    gemeinschaft_namen(text, sachwort) -> [(start, ende)]
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


def behandlungsdatum(davor_bis_name: str, text: str, datum_ende: int) -> bool:
    """Ist das Datum ein Behandlungsdatum: Titel, Praxis oder Klinik vor dem Namen, oder ein Behandlungstext hinter
    dem Datum ("Dr. Ute Kranzfelder, 03.11.2012: Meniskusoperation links")?"""
    return bool(BEHANDLER_DAVOR_RE.search(davor_bis_name)) or bool(_TEXT_DAHINTER_RE.match(text, datum_ende))


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
# "Morbus Scheuermann", "Lumboischialgie")
MEDIZIN_ENDUNG_RE = re.compile(r"(?i)(?:itis|algie|algien|ose|osen|fraktur|pathie|ektomie|ämie|zyste|syndrom|demenz|"
                               r"karzinom|plasie|sklerose|ischialgie|kontraktur|krankheit|erkrankung|tumor|lähmung)$")
EPONYM_DAVOR_RE = re.compile(r"(?<![\wäöüß])(?:Morbus|M\.)[ \t]+$")


def medizinisch(wort: str, text: str = "", start: int = 0) -> bool:
    """Fachwort der Medizin (auch als Teil eines Bindestrich-Worts: "Baker-Zyste") oder Eponym hinter "Morbus"?"""
    teile = [t for t in wort.split("-") if t]
    if any(MEDIZIN_ENDUNG_RE.search(t) for t in teile[1:]) or (len(teile) == 1 and MEDIZIN_ENDUNG_RE.search(wort)):
        return True
    return bool(text) and bool(EPONYM_DAVOR_RE.search(text, max(0, start - 10), start))


# USt-IdNr. einer Firma oder einer natürlichen Person (Befund 77): Firmenmerkmale in der Zeile der Nummer und den zwei
# Zeilen davor – Rechtsform einer juristischen Person, Register, Organisationswörter. Ein Trennzeichen ("·") allein ist
# kein Firmenmerkmal (Signaturen von Handwerkern und Freiberuflern), und Einzelkaufleute ("e.K.", "Inhaber") ohne
# juristische Rechtsform sind natürliche Personen – auch mit HRA-Eintrag.
_JURISTISCHE_FORM_RE = re.compile(r"(?<![\wäöüß])(?:GmbH|gGmbH|AG|SE|KG|KGaA|OHG|mbH|UG|e\.[ \t]?V\.|eG|VVaG|"
                                  r"a\.[ \t]?G\.|gAG)(?![\wäöüß])")
_ORGANISATION_UST_RE = re.compile(r"(?<![\wäöüß])(?:Versicherung\w*|Versicherer|Bank|Sparkasse|HRB|HRA|Registergericht|"
                                  r"Amtsgericht|Handelsregister|Vorstand|Aufsichtsrat\w*|Geschäftsführ\w*|"
                                  r"Sitz(?:[ \t]+der[ \t]+Gesellschaft)?)(?![\wäöüß])")
EINZELKAUFMANN_RE = re.compile(r"(?<![\wäöüß])(?:e\.[ \t]?K(?:fm|fr)?\.|Inh\.|Inhaber(?:in)?)(?![\wäöüß])")


def ust_umgebung(text: str, start: int) -> str:
    """Zeile der Stelle und die zwei Zeilen davor."""
    anfang = start
    for _ in range(3):
        anfang = text.rfind("\n", 0, max(0, anfang - 1))
        if anfang < 0:
            anfang = 0
            break
    ende = text.find("\n", start)
    return text[anfang:len(text) if ende < 0 else ende]


def ust_id_der_firma(umgebung: str) -> bool:
    """Gehört eine USt-IdNr. in dieser Umgebung (ust_umgebung) einer Firma? Ja mit der Rechtsform einer juristischen
    Person; sonst nein bei Einzelkaufleuten und Inhabern; sonst ja mit Register- oder Organisationswort."""
    if _JURISTISCHE_FORM_RE.search(umgebung):
        return True
    if EINZELKAUFMANN_RE.search(umgebung):
        return False
    return bool(_ORGANISATION_UST_RE.search(umgebung))


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


# Gesellschaften bürgerlichen Rechts und Gemeinschaften natürlicher Personen (Befund 63): der Name davor bzw. dahinter
# ist der Familienname der Gesellschafter – auch unbekannt ("Felsberger GbR", "Erbengemeinschaft Riedlinger").
# Fantasie- oder Objektnamen ("Sonnenhof GbR") werden dabei mitgeschwärzt; das ist harmlos.
_NAMENSWORT = r"[A-ZÄÖÜ][a-zäöüß'’]+(?:-[A-ZÄÖÜ][a-zäöüß'’]+)?"
_GBR_RE = re.compile(rf"(?<![\w\-])(?P<name>{_NAMENSWORT}(?:[ \t]*(?:&|und|\+)[ \t]*{_NAMENSWORT})?)[ \t]+GbR"
                     r"(?![\wäöüß])")
_GEMEINSCHAFT_RE = re.compile(rf"(?<![\w\-])(?:Erben|Grundstücks|Bruchteils)gemeinschaft[ \t]+(?P<name>{_NAMENSWORT})"
                              r"(?![\wäöüß])")


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


def ust_id_einer_person(umgebung: str) -> bool:
    """Belegt die Umgebung einer USt-IdNr. eine natürliche Person – Einzelkaufmann oder Inhaber ohne Rechtsform einer
    juristischen Person? (Für die Selbstkontrolle: eine USt-IdNr. ohne jeden Beleg bleibt dort unkritisch.)"""
    return bool(EINZELKAUFMANN_RE.search(umgebung)) and not _JURISTISCHE_FORM_RE.search(umgebung)
