"""Wissensbasierte Detektoren mit Personenkontext (Vertrag Abschnitt 3, Schutzstufen Abschnitt 9).

    wissen.gesundheit  Diagnosen, Medikamente (Listen der Wissensbasis), ICD-10-Codes und Körpermaße – nur mit
                       Gesundheitskontext (Diagnose:, leidet an, Medikation:, ICD-Code, Dosierung)
                       -> Kategorien "diagnose", "medikament". In „maximal“ geschwärzt; in „hoch“ erkennt die
                       Analyse sie als Hinweis (muster.hinweis_kategorien) und bietet sie abgewählt an.
                       Stützt sich ein Treffer nur auf allgemeine Wörter (Therapie, ambulant, Krankenhaus, Reha …),
                       die genauso in Tarif- und Leistungsübersichten stehen, ist er nur vermutet: Quelle
                       "wissen.gesundheit.vermutet", Sicherheit 0.5 (erkannt wird er trotzdem).
    wissen.beruf       Beruf hinter einem Etikett (Beruf:, ausgeübte Tätigkeit:) oder im Satz (arbeitet als,
                       ist … von Beruf) -> "beruf"
    org.arbeitgeber    Organisation hinter "Arbeitgeber:" oder im Satz (beschäftigt bei, arbeitet … bei der …)
                       -> "arbeitgeber"; Versicherer, Banken und Behörden der Erlaubnisliste bleiben IMMER stehen
    ort                Ort ohne PLZ: Ort-Datum-Zeilen ("St. Ingbert, 03.04.2025"), Geburts-/Wohnort hinter einem
                       Etikett oder "geboren in", "wohnhaft in" -> "ort"
    international      ausländische Anschriften (NL, PL, CZ, IT, FR, ES, HU, TR, DK/SE/NO, UK …) und Kennzeichen
                       hinter einem Etikett -> "international"
    wissen.geburt      Datum ohne Stichwort direkt hinter einem Namen ("Max Mustermann, 02.09.61"), Alter in
                       Klammern hinter einem Namen ("Anna Berg (54)"); in „maximal“ zusätzlich jedes plausible
                       Geburtsdatum außerhalb von Vertragsdaten -> "geburt"

Die Text-Funktionen (berufe_stellen, …) arbeiten auf normalisiertem Text und liefern [(start, ende)]; muster.py
nutzt sie für die Text-Schnittstelle (Formularfelder, Werkzeuge).
"""

from __future__ import annotations

import datetime
import re

from .. import muster, wissen
from . import ALLE_PROFILE, Treffer, detektor, entfernen

_GROSS = "A-ZÄÖÜÀ-ÖØ-ÞĀĂĄĆČĎĐĒĖĘĚĞĢĪĮİĶĹĻĽŁŃŅŇŌŐŒŔŘŚŞŠŢŤŪŮŰŲŹŻŽ"
_KLEIN = "a-zäöüßà-öø-ÿāăąćčďđēėęěğģīįıķĺļľłńņňōőœŕřśşšţťūůűųźżž"
_WORT_GROSS = f"[{_GROSS}][{_KLEIN}{_GROSS}'’\\-]*"
_ZEILENENDE_RE = re.compile(r"[\n]")


def _zeilen_grenzen(text: str, pos: int) -> tuple:
    a = text.rfind("\n", 0, pos) + 1
    e = text.find("\n", pos)
    return a, (len(text) if e < 0 else e)


def _zelle_ende(text: str, pos: int, grenze: int = 120) -> int:
    """Ende eines Werts ab pos: Zeilenende, Tabulator, zwei Leerzeichen oder Semikolon."""
    m = re.compile(r"\n|\t|[ ]{2,}|;").search(text, pos, min(len(text), pos + grenze))
    return m.start() if m else min(len(text), pos + grenze)


def _rstrip_stelle(text: str, s: int, e: int, zeichen: str = " \t.,;:") -> tuple:
    while e > s and text[e - 1] in zeichen:
        e -= 1
    while s < e and text[s] in " \t":
        s += 1
    return s, e


# ======================================================================
# Gesundheit
# ======================================================================
_ICD_RE = re.compile(r"(?<![\w.])([A-TV-Z][0-9]{2}(?:\.[0-9]{1,2}[A-Z!*+]?)?)(?:[ \t]?[GVZA])?(?:[ \t]?[LRB])?"
                     r"(?![\w.])")
_ICD_KONTEXT_RE = re.compile(r"(?i:icd(?:-?10(?:-gm)?)?|diagnose[n]?|dg\.|befund|diagnoseschlüssel)[ \t:.\-]*$")
_GESUNDHEIT_ETIKETT_RE = re.compile(
    r"(?im)^[ \t•·\-–*]*(?:\d+[.)][ \t]*)?(?:(?:Haupt|Neben|Entlassungs|Aufnahme|Verdachts|Einweisungs|Dauer)?"
    r"[Dd]iagnose[n]?|Befund[e]?|Anamnese|Vorerkrankung(?:en)?|Erkrankung(?:en)?|Beschwerden|"
    r"Behandlung(?:en)?(?:[ \t]*\([^)\n]{0,20}\))?|Gesundheitsfrage[n]?|Gesundheitszustand|Krankheit(?:en)?|"
    r"Medikation|Medikamente|Dauermedikation|Arzneimittel|Therapie|Procedere|Epikrise|Familienanamnese)"
    r"[ \t]*:")
_GESUNDHEIT_PROSA_RE = re.compile(
    r"(?i:leidet|litt|leiden|erkrankt|erkrankung|diagnose|diagnostiziert|befund|patient(?:in)?|behandelt|behandlung|"
    r"therapie|anamnese|zustand[ \t]+nach|z\.[ \t]?n\.|v\.[ \t]?a\.|verdacht[ \t]+auf|vorerkrankung|beschwerden|"
    r"symptom|arbeitsunfähig|krankgeschrieben|operiert|operation|eingenommen|verordnet|medikation|einnahme|"
    r"stationär|ambulant|klinik|krankenhaus|reha(?:bilitation)?|gesundheitsfrage|attest|arztbrief|facharzt|"
    r"hausarzt|ärztlich)")
# Wörter mit Bezug zu einer Person oder einem Krankheitsgeschehen (Teilmenge von _GESUNDHEIT_PROSA_RE) und eine
# Anrede mit Namen („Herr Meier“). Die übrigen Kontextwörter (Therapie, Behandlung, ambulant, stationär, Klinik,
# Krankenhaus, Reha, Operation, Erkrankung …) stehen genauso in Tarif- und Leistungsübersichten
# („Psychotherapie 30 Sitzungen, ambulant 100 %“).
_GESUNDHEIT_PERSON_RE = re.compile(
    r"(?i:leidet|litt|leiden|erkrankt|diagnose|diagnostiziert|befund|patient(?:in)?|behandelt|anamnese|"
    r"zustand[ \t]+nach|z\.[ \t]?n\.|v\.[ \t]?a\.|verdacht[ \t]+auf|vorerkrankung|beschwerden|symptom|"
    r"arbeitsunfähig|krankgeschrieben|operiert|eingenommen|verordnet|medikation|einnahme|attest|arztbrief)"
    r"|(?<![\wäöüß])(?:Herrn?|Frau)[ \t]+[A-ZÄÖÜ]")
QUELLE_GESUNDHEIT = "wissen.gesundheit"
QUELLE_GESUNDHEIT_VERMUTET = "wissen.gesundheit.vermutet"   # nur allgemeine Fachbegriffe, kein Personenbezug
_DOSIS_RE = re.compile(
    r"(?:[ \t]*-?(?:Spray|Tabletten?|Tbl\.?|Kapseln?|Kps\.?|Tropfen|Salbe|Creme|Gel|Retard|retard|forte|"
    r"comp\.?|Inhalat(?:or|ion)|Injektion|Pen|Pflaster|Saft|Lösung|Zäpfchen))?"
    r"(?:[ \t]*\d+(?:[.,]\d+)?[ \t]?(?:mg|µg|ug|mcg|g|ml|IE|I\.E\.|%|Hub|Hübe|E)(?![\w]))?"
    r"(?:[ \t]*(?:\d(?:[.,]5)?-\d(?:[.,]5)?-\d(?:[.,]5)?(?:-\d(?:[.,]5)?)?))?"
    r"(?:[ \t]*(?:bei[ \t]+Bedarf|täglich|tgl\.|morgens|abends|mittags|zur[ \t]+Nacht|wöchentlich|"
    r"\d[ \t]?x[ \t]?(?:täglich|tgl\.|wöchentlich)|nach[ \t]+Bedarf|b\.[ \t]?B\.))?")
_KOERPER_RE = re.compile(
    r"(?<!\d)(?:\d{3}[ \t]?cm[ \t]*/[ \t]*\d{2,3}(?:[.,]\d)?[ \t]?kg"
    r"|(?:Größe|Körpergröße)[ \t]*:?[ \t]*\d{3}[ \t]?cm|(?:Gewicht|Körpergewicht)[ \t]*:?[ \t]*\d{2,3}(?:[.,]\d)?[ \t]?kg"
    r"|BMI[ \t]*:?[ \t]*\d{2}(?:[.,]\d{1,2})?)(?![\w])")
_DIAGNOSE_LINKS_RE = re.compile(f"(?:[{_GROSS}{_KLEIN}][{_KLEIN}]+(?:e|en|er|es|em)[ \t]+)$")
# Wörter, die wie ein Adjektiv enden, aber keins sind („wie Krebs“, „eine Depression“, „keine Allergie“): die Angabe
# wird nicht um sie nach links erweitert
_KEIN_DIAGNOSE_ADJEKTIV = {
    "wie", "die", "eine", "einer", "einem", "einen", "eines", "keine", "keiner", "keinem", "keinen", "keines",
    "seine", "seiner", "seinem", "seinen", "seines", "ihre", "ihrer", "ihrem", "ihren", "ihres", "meine", "meiner",
    "unsere", "unserer", "unserem", "unseren", "diese", "dieser", "diesem", "diesen", "dieses", "jede", "jeder",
    "jedem", "jeden", "jedes", "alle", "allen", "allem", "aller", "beide", "beiden", "andere", "anderen", "anderer",
    "einige", "einigen", "mehrere", "mehreren", "viele", "vielen", "welche", "welcher", "solche", "solcher",
    "oder", "aber", "unter", "über", "hinter", "wegen", "gegen", "sowie", "ohne", "habe", "hatte", "wurde",
    "werde", "leider", "wieder", "immer", "außer", "ferner", "früher", "später", "weiter", "bitte", "sehe"}
# Erweiterung nach rechts: Seite, Verlauf, Typ/Grad/Stadium, „mit/bei/des … + bis zu zwei Wörter“ (das zweite nur
# großgeschrieben: „bei Herrn Meier“, „des rechten Kniegelenks“ – nicht „nach Unfall bis“, „nach Unfall 2“)
_DIAGNOSE_RECHTS_RE = re.compile(
    r"(?:,?[ \t]+(?:links|rechts|beidseits|beidseitig|bds\.|li\.|re\.|chronisch|akut|rezidivierend|"
    r"mittelgradig|leichtgradig|schwer|leicht|primär|sekundär|paroxysmal|persistierend|"
    r"Typ[ \t]+(?:\d|I{1,3}|IV|V)[a-b]?|Grad[ \t]+(?:\d|I{1,3}|IV|V)|Stadium[ \t]+\w+|"
    r"(?:mit|ohne|bei|durch|des|der|nach)[ \t]+[\wäöüÄÖÜß\-]+(?:[ \t]+[A-ZÄÖÜ][\wäöüÄÖÜß\-]*)?|"
    r"[A-Z]\d(?:/[A-Z]?\d)?|[\wäöüÄÖÜß]+-[\wäöüÄÖÜß\-]+))*"
    r"(?:[ \t]*\((?:[A-TV-Z]\d{2}(?:\.\d{1,2})?[A-Z!*+]?(?:[ \t]?[GVZALRB])*)\))?")


def _gesundheitskontext_art(text: str, s: int, e: int, etikett_bereiche) -> str | None:
    """Gesundheitskontext einer Stelle: "sicher" (hinter einem Gesundheits-Etikett, ICD-Code in der Zeile oder ein
    Wort mit Bezug zu einer Person/einem Krankheitsgeschehen vor oder hinter der Stelle – „leidet an“, „Patientin“,
    „diagnostiziert“ …), "vermutet" (nur allgemeine Wörter wie Therapie, ambulant, Krankenhaus, Reha – auch im
    Begriff selbst; so stehen sie auch in Tarif- und Leistungsübersichten) oder None (kein Gesundheitskontext).
    Erkannt wird in beiden Fällen (dieselbe Schranke wie bisher), "vermutet" ändert nur Quelle und Wortlaut."""
    if any(a <= s < b for a, b in etikett_bereiche):
        return "sicher"
    a, b = _zeilen_grenzen(text, s)
    zeile = text[a:b]
    if _ICD_RE.search(zeile) and re.search(r"\([A-TV-Z]\d{2}", zeile):
        return "sicher"
    fenster = text[max(0, s - 140):min(len(text), e + 100)]
    if not _GESUNDHEIT_PROSA_RE.search(fenster):
        return None                              # Schranke wie bisher: ohne Kontextwort nichts erkannt
    davor, danach = text[max(0, s - 140):s], text[e:min(len(text), e + 100)]
    if _GESUNDHEIT_PERSON_RE.search(davor) or _GESUNDHEIT_PERSON_RE.search(danach):
        return "sicher"
    return "vermutet"


def _gesundheitskontext(text: str, s: int, e: int, etikett_bereiche) -> bool:
    return _gesundheitskontext_art(text, s, e, etikett_bereiche) is not None


def _etikett_bereiche(text: str) -> list:
    """Bereiche hinter Gesundheits-Etiketten: Rest der Zeile und – bei Listen – die Folgezeilen bis zur
    nächsten Leerzeile oder dem nächsten Etikett ("Diagnosen:" ⏎ "- Lumboischialgie …")."""
    bereiche = []
    for m in _GESUNDHEIT_ETIKETT_RE.finditer(text):
        ende = text.find("\n", m.end())
        ende = len(text) if ende < 0 else ende
        # Folgezeilen (Aufzählung), höchstens 12
        pos = ende
        for _ in range(12):
            if pos >= len(text):
                break
            n = text.find("\n", pos + 1)
            n = len(text) if n < 0 else n
            zeile = text[pos + 1:n]
            if not zeile.strip() or re.match(r"[ \t]*[\wÄÖÜäöüß /\-]{2,40}:[ \t]*$", zeile) \
                    or re.match(r"[ \t]*[A-ZÄÖÜ][\wäöüß]+(?:[ \t]+[\wäöüß]+){0,3}:", zeile) and \
                    not re.match(r"[ \t]*[•·\-–*]|\d+[.)]", zeile):
                break
            if not re.match(r"[ \t]*(?:[•·\-–*]|\d+[.)])", zeile):
                break
            pos = n
        bereiche.append((m.start(), max(ende, pos)))
    return bereiche


def _icd_stellen(text: str, etikett_bereiche) -> list:
    aus = []
    for m in _ICD_RE.finditer(text):
        s, e = m.start(1), m.end(1)
        davor = text[max(0, s - 25):s]
        in_klammer = s > 0 and text[s - 1] == "(" or text[max(0, s - 2):s] == "( "
        if in_klammer or _ICD_KONTEXT_RE.search(davor) or any(a <= s < b for a, b in etikett_bereiche):
            aus.append((m.start(), m.end()))
    return aus


def _diagnosen_mit_art(text: str) -> list:
    """Wie diagnosen_stellen, je Stelle mit Art: [(start, ende, sicher)] – sicher = Etikett, ICD-Code, Körpermaß
    oder Personenbezug; sonst nur vermutet (siehe _gesundheitskontext_art)."""
    if not text:
        return []
    bereiche = _etikett_bereiche(text)
    aus = []
    for v in wissen.index("diagnosen").finde(text):
        kurz = len(v.text) <= 4 or v.text.isupper()
        a, b = _zeilen_grenzen(text, v.start)
        icd_folgt = re.search(r"\([A-TV-Z]\d{2}", text[v.ende:min(b, v.ende + 70)])
        in_etikett = any(x <= v.start < y for x, y in bereiche)
        if kurz and not (in_etikett or icd_folgt):
            continue
        art = "sicher" if in_etikett or icd_folgt else _gesundheitskontext_art(text, v.start, v.ende, bereiche)
        if art is None:
            continue
        s, e = v.start, v.ende
        links = _DIAGNOSE_LINKS_RE.search(text[a:s])
        if links and links.group(0).strip().casefold() not in _KEIN_DIAGNOSE_ADJEKTIV:
            s = a + links.start()
        rechts = _DIAGNOSE_RECHTS_RE.match(text, e)
        if rechts and rechts.end() <= b:
            e = rechts.end()
        if icd_folgt and e < v.ende + icd_folgt.start():
            # alles bis einschließlich der ICD-Klammer gehört zur Angabe ("Koronare Herzkrankheit,
            # Ein-Gefäß-Erkrankung (I25.11)")
            schluss = text.find(")", v.ende + icd_folgt.start(), b)
            if schluss > 0:
                e = schluss + 1
        aus.append((s, e, art == "sicher"))
    aus.extend((s, e, True) for s, e in _icd_stellen(text, bereiche))
    for m in _KOERPER_RE.finditer(text):
        aus.append((m.start(), m.end(), True))
    return _vereinigen_mit_art(aus)


def diagnosen_stellen(text: str) -> list:
    """Diagnosen (Wissensbasis) mit Gesundheitskontext, auf die ganze Angabe erweitert ("Generalisierte
    Angststörung (F41.1)", "Lumboischialgie links (M54.4)"), ICD-10-Codes und Körpermaße."""
    return [(s, e) for s, e, _ in _diagnosen_mit_art(text)]


def _medikamente_mit_art(text: str) -> list:
    """Wie medikamente_stellen, je Stelle mit Art: [(start, ende, sicher)] – sicher = Dosierung, Etikett oder
    Personenbezug; sonst nur vermutet."""
    if not text:
        return []
    bereiche = _etikett_bereiche(text)
    aus = []
    for v in wissen.index("medikamente").finde(text):
        if len(v.text) < 4:
            continue
        dosis = _DOSIS_RE.match(text, v.ende)
        mit_dosis = dosis is not None and dosis.end() > v.ende and re.search(r"\d|Bedarf|täglich|Spray",
                                                                              dosis.group(0))
        if mit_dosis or any(x <= v.start < y for x, y in bereiche):
            art = "sicher"
        else:
            art = _gesundheitskontext_art(text, v.start, v.ende, bereiche)
            if art is None:
                continue
        e = dosis.end() if dosis is not None else v.ende
        s, e = _rstrip_stelle(text, v.start, e)
        aus.append((s, e, art == "sicher"))
    return _vereinigen_mit_art(aus)


def medikamente_stellen(text: str) -> list:
    """Medikamente (Wissensbasis) mit Dosierung oder im Medikationskontext ("Ibuprofen 600 mg bei Bedarf")."""
    return [(s, e) for s, e, _ in _medikamente_mit_art(text)]


def _vereinigen(stellen: list) -> list:
    aus = []
    for s, e in sorted(stellen):
        if aus and s < aus[-1][1]:
            aus[-1] = (aus[-1][0], max(aus[-1][1], e))
        else:
            aus.append((s, e))
    return aus


def _vereinigen_mit_art(stellen: list) -> list:
    """Wie _vereinigen für (start, ende, sicher): eine vereinigte Stelle ist sicher, wenn ein Teil es ist."""
    aus = []
    for s, e, sicher in sorted(stellen):
        if aus and s < aus[-1][1]:
            aus[-1] = (aus[-1][0], max(aus[-1][1], e), aus[-1][2] or sicher)
        else:
            aus.append((s, e, sicher))
    return aus


@detektor("wissen.gesundheit", {"diagnose", "medikament"}, ALLE_PROFILE)
def gesundheit(dok, kontext):
    """Gesundheitsdaten (Art. 9 DSGVO): Diagnosen, ICD-10, Körpermaße -> diagnose; Medikamente -> medikament.
    Nur vermutete Treffer (allgemeine Fachbegriffe ohne Etikett, ICD-Code, Dosierung oder Personenbezug) tragen die
    Quelle QUELLE_GESUNDHEIT_VERMUTET und Sicherheit 0.5 – die Analyse formuliert ihren Hinweis vorsichtiger."""
    text = dok.text
    treffer = []
    for kategorie, stellen in (("diagnose", _diagnosen_mit_art(text)), ("medikament", _medikamente_mit_art(text))):
        for s, e, sicher in stellen:
            treffer.append(Treffer(s, e, kategorie, QUELLE_GESUNDHEIT if sicher else QUELLE_GESUNDHEIT_VERMUTET,
                                   0.7 if sicher else 0.5))
    return treffer


# ======================================================================
# Beruf und Arbeitgeber
# ======================================================================
_BERUF_ETIKETT_RE = re.compile(
    r"(?<![\wäöüß])(?i:(?:ausgeübte[rn]?|derzeitige[rn]?|jetzige[rn]?|erlernte[rn]?|aktuelle[rn]?|"
    r"zuletzt[ \t]+ausgeübte[rn]?)[ \t]+)?"
    r"(?:Beruf|Berufsbezeichnung|Berufsstand|Berufsgruppe|(?i:Tätigkeit)|berufliche[ \t]+Tätigkeit|Stellung[ \t]+im[ \t]+Beruf|"
    r"Occupation|Profession)(?P<ag>[ \t]*/[ \t]*(?:Tätigkeit|Arbeitgeber|Stellung|Branche))?(?![\wäöüß])"
    r"(?:[ \t]*\([^)\n]{1,20}\))?(?:[ \t]*:[ \t]*|\t+[ \t]*)")
_BERUF_VOR_RE = re.compile(
    r"(?<![\wäöüß])(?:arbeitet(?:e)?|arbeiten|tätig(?:[ \t]+(?:ist|war|sind))?|beschäftigt|angestellt|eingestellt|"
    r"selbst(?:st)?ändig|freiberuflich|ausgebildet(?:e[rn]?)?|Ausbildung|Tätigkeit|Arbeit|Anstellung|Beschäftigung|"
    r"Stelle|Job|Lehre|Umschulung|beruflich|ehemals|früher)[ \t]+(?:als|zum|zur)[ \t]+"
    r"|(?<![\wäöüß])(?:ist|war|bin|sind|wird|wurde|Beruf:?)[ \t]+(?:von[ \t]+Beruf[ \t]+)?"
    r"|(?<![\wäöüß])von[ \t]+Beruf[ \t]+")
_BERUF_ADJEKTIV_RE = re.compile(
    r"(?:(?:eine?r?|selbst(?:st)?ändige[rn]?|angestellte[rn]?|freiberufliche[rn]?|leitende[rn]?|"
    r"verbeamtete[rn]?|gelernte[rn]?|ausgebildete[rn]?|staatlich[ \t]+anerkannte[rn]?|examinierte[rn]?|"
    r"approbierte[rn]?|niedergelassene[rn]?)[ \t]+)*")
_KLAMMER_RE = re.compile(r"[ \t]*\([^()\n]{1,30}\)")
# Berufe, die zugleich häufige Wörter in Versicherungstexten sind: nur hinter einem Etikett
_BERUF_ALLGEMEIN = {"arzt", "ärztin", "kunde", "kundin", "vermittler", "vermittlerin", "makler", "maklerin",
                    "berater", "beraterin", "inhaber", "inhaberin", "partner", "partnerin", "mitglied", "versicherer",
                    "versicherte", "versicherter", "sachbearbeiter", "sachbearbeiterin", "gutachter", "gutachterin",
                    "bevollmächtigter", "bevollmächtigte", "geschäftsführer", "geschäftsführerin", "vorstand",
                    "aufsichtsrat", "mitarbeiter", "mitarbeiterin", "rentner", "rentnerin", "student", "studentin"}


def _beruf_wert(text: str, pos: int, etikett: bool):
    """(start, ende) eines Berufs ab pos (Adjektive davor erlaubt) oder None. Hinter einem Etikett zählt auch ein
    unbekannter Beruf (Wert der Zelle), im Satz nur ein Eintrag der Wissensbasis."""
    adj = _BERUF_ADJEKTIV_RE.match(text, pos)
    p = adj.end() if adj else pos
    ende_zelle = _zelle_ende(text, p, 80)
    ausschnitt = text[p:ende_zelle]
    treffer = [v for v in wissen.index("berufe").finde(ausschnitt) if v.start <= 25]
    if treffer:
        v = min(treffer, key=lambda v: v.start)
        vor = ausschnitt[:v.start]
        if vor and not re.fullmatch(r"[\wäöüÄÖÜß]+-?|[\wäöüÄÖÜß]+-[\wäöüÄÖÜß]*", vor):
            if not etikett:
                return None
        else:
            if not etikett and v.text.casefold() in _BERUF_ALLGEMEIN:
                return None
            s, e = p, p + v.ende
            k = _KLAMMER_RE.match(text, e)
            if k and k.end() <= ende_zelle:
                e = k.end()
            return (pos if etikett else s), e
    if not etikett:
        return None
    # Etikett: Wert bis Komma/Zellenende, 1–6 Wörter, beginnt mit einem Buchstaben
    komma = text.find(",", p, ende_zelle)
    e = komma if komma >= 0 else ende_zelle
    s, e = _rstrip_stelle(text, pos, e)
    wert = text[s:e]
    if not wert or not wert[0].isalpha() or len(wert.split()) > 6 or len(wert) < 3:
        return None
    if wert.casefold() in {"ja", "nein", "keine", "keine angabe", "entfällt", "ohne", "k. a.", "k.a."}:
        return None
    return s, e


def berufe_stellen(text: str) -> list:
    """Berufsangaben hinter einem Etikett ("Beruf: Verkäuferin", "Ausgeübter Beruf:⇥⇥Pharmareferentin") oder
    im Satz ("arbeitet als Zahnärztin", "ist von Beruf Schreiner", "Schreiner von Beruf")."""
    if not text:
        return []
    aus = []
    for m in _BERUF_ETIKETT_RE.finditer(text):
        w = _beruf_wert(text, m.end(), True)
        if w:
            aus.append(w)
    for m in _BERUF_VOR_RE.finditer(text):
        w = _beruf_wert(text, m.end(), False)
        if w:
            aus.append(w)
    for m in re.finditer(r"[ \t]+von[ \t]+Beruf(?![\wäöüß])", text):
        a = text.rfind("\n", 0, m.start()) + 1
        vor = [v for v in wissen.index("berufe").finde(text[a:m.start()]) if a + v.ende == m.start()]
        if vor:
            aus.append((a + vor[-1].start, a + vor[-1].ende))
    return _vereinigen(aus)


_RECHTSFORM = (r"(?:GmbH[ \t]*&[ \t]*Co\.?[ \t]*KG(?:aA)?|gGmbH|GmbH|mbH|AG|KGaA|KG|OHG|GbR|UG(?:[ \t]*\(haftungsbeschränkt\))?|"
               r"e\.[ \t]?K\.|e\.[ \t]?Kfm\.|e\.[ \t]?Kfr\.|e\.[ \t]?V\.|eG|SE|Ltd\.?|Inc\.?|S\.A\.|S\.p\.A\.|B\.V\.|"
               r"PartG(?:mbB)?|Stiftung)")
_ORG_KOPF = (r"(?:Bäckerei|Metzgerei|Fleischerei|Konditorei|Autohaus|Kfz-Werkstatt|Werkstatt|Kita|Kindergarten|"
             r"Kindertagesstätte|Klinikum|Klinik|Krankenhaus|Praxis|Gemeinschaftspraxis|Zahnarztpraxis|Arztpraxis|"
             r"Physiotherapie|Apotheke|Stadtwerke|Spedition|Brauerei|Maschinenfabrik|Fabrik|Logistikzentrum|Pflegedienst|"
             r"Pflegeheim|Altenheim|Seniorenstift|Seniorenheim|Grundschule|Gesamtschule|Realschule|Gymnasium|Schule|"
             r"Hochschule|Universität|Softwarehaus|Metallbau|Elektro|Dachbau|Bauunternehmen|Baugesellschaft|"
             r"Kanzlei|Rechtsanwaltskanzlei|Steuerbüro|Steuerberatung|Ingenieurbüro|Architekturbüro|Malerbetrieb|"
             r"Schreinerei|Tischlerei|Zimmerei|Friseursalon|Salon|Restaurant|Gasthaus|Hotel|Supermarkt|Markt|"
             r"Stadtverwaltung|Gemeindeverwaltung|Landratsamt|Rathaus|Firma|Fa\.|Gärtnerei|Druckerei|Reinigung|"
             r"Sanitätshaus|Optiker|Hörgeräte|Fahrschule|Taxiunternehmen|Reisebüro|Agentur|Handwerksbetrieb|Betrieb|"
             r"Werk|Lager|Logistik|Transporte|Bau|Holzbau|Gartenbau|Landschaftsbau|Pflege|Sozialstation|Diakonie|"
             r"Caritas|Lebenshilfe)")
_ORG_RE = re.compile(
    rf"(?:{_ORG_KOPF}|[{_GROSS}][\w&\-.'’]*)(?:[ \t]+(?:&|und|am|an[ \t]+der|im|in|für|zum|zur|der|des|"
    rf"{_RECHTSFORM}|[{_GROSS}][\w&\-.'’]*|\d{{1,4}})){{0,6}}")
_AG_ETIKETT_RE = re.compile(
    r"(?<![\wäöüß])(?i:(?:derzeitige[rn]?|jetzige[rn]?|aktuelle[rn]?|letzte[rn]?|früherer?)[ \t]+)?"
    r"(?:Arbeitgeber(?:in)?|Arbeitgeber(?:\(in\)|/in|/-in)|Dienstherr|Beschäftigungsbetrieb|Ausbildungsbetrieb|"
    r"Arbeitsstelle|Beschäftigungsstelle|Dienststelle|Employer|Firma[ \t]+des[ \t]+Arbeitgebers|"
    r"Name[ \t]+des[ \t]+Arbeitgebers)(?![\wäöüß])(?:[ \t]*:[ \t]*|\t+[ \t]*)")
_AG_PROSA_RE = re.compile(r"(?<![\wäöüß])(?:bei|beim)[ \t]+(?:(?:der|dem|den|die|einer|einem)[ \t]+)?")
_AG_VERB_RE = re.compile(
    r"(?<![\wäöüß])(?i:arbeitet|arbeitete|arbeiten|tätig|beschäftigt|angestellt|eingestellt|mitarbeiter(?:in)?|"
    r"angestellte[rn]?|beschäftigte[rn]?|ausbildung|lehre|praktikum|gekündigt|arbeitsverhältnis|arbeitgeber|"
    r"dienstverhältnis|beschäftigungsverhältnis)(?![\wäöüß])")


_ABKUERZUNG_PUNKT = {"Gebr.", "Inh.", "Co.", "Fa.", "St.", "Dr.", "Prof.", "Ing.", "Kfm.", "Nachf.", "Gesch."}


def _org_wert(text: str, pos: int, etikett: bool):
    m = _ORG_RE.match(text, pos)
    if not m:
        return None
    s, e = _rstrip_stelle(text, m.start(), m.end())
    # nicht über das Zellen-/Zeilenende hinaus
    e = min(e, _zelle_ende(text, s, 120))
    # nicht über ein Satzende hinaus ("… Versicherungs-AG. Ihr Vertrag"): ein Wort mit Schlusspunkt, das keine
    # Abkürzung ist, beendet die Organisation
    for t in re.finditer(r"\S+", text[s:e]):
        wort = t.group(0)
        if wort.endswith(".") and len(wort) > 4 and wort not in _ABKUERZUNG_PUNKT \
                and not re.fullmatch(r"(?:\w\.){2,}", wort):
            e = s + t.end()
            break
    s, e = _rstrip_stelle(text, s, e)
    wert = text[s:e]
    if len(wert) < 3:
        return None
    woerter = wert.split()
    if not etikett:
        hat_form = re.search(rf"(?<![\w]){_RECHTSFORM}(?![\w])", wert) is not None
        hat_kopf = re.match(_ORG_KOPF + r"(?![\wäöüß])", wert) is not None
        if not (hat_form or hat_kopf) or len(woerter) < 2:
            return None
    try:
        if wissen.ist_allowlist(wert) or wissen.ist_allowlist(re.sub(rf"[ \t]+{_RECHTSFORM}$", "", wert)):
            return None                                   # Versicherer, Banken, Behörden bleiben stehen
    except Exception:
        pass
    return s, e


def arbeitgeber_stellen(text: str) -> list:
    """Arbeitgeber hinter "Arbeitgeber:" (beliebige Organisation) oder im Satz ("arbeitet als Zahnärztin bei der
    Bäckerei Hofmeister", "beschäftigt bei der Autohaus Lindner GmbH") – nur mit Rechtsform oder typischem
    Betriebswort. Versicherer, Banken und Behörden der Erlaubnisliste bleiben stehen."""
    if not text:
        return []
    aus = []
    for m in _AG_ETIKETT_RE.finditer(text):
        if re.search(r"/[ \t]*$", text[max(0, m.start() - 4):m.start()]):
            continue                                       # "Beruf / Arbeitgeber:" – unten getrennt behandelt
        w = _org_wert(text, m.end(), True)
        if w:
            aus.append(w)
    for m in _AG_PROSA_RE.finditer(text):
        satz_anfang = max(text.rfind(".", 0, m.start() - 1), text.rfind("\n\n", 0, m.start()), m.start() - 120)
        if not _AG_VERB_RE.search(text[max(0, satz_anfang):m.start()]):
            continue
        w = _org_wert(text, m.end(), False)
        if w:
            aus.append(w)
    # "Beruf / Arbeitgeber: Polier, Esposito Bau GmbH": zweiter Teil ist der Arbeitgeber
    for m in _BERUF_ETIKETT_RE.finditer(text):
        if m.group("ag") and "arbeitgeber" in m.group("ag").lower():
            ende = _zelle_ende(text, m.end(), 120)
            komma = text.find(",", m.end(), ende)
            if komma > 0:
                w = _org_wert(text, komma + 1 + (len(text[komma + 1:ende]) - len(text[komma + 1:ende].lstrip())),
                              True)
                if w:
                    aus.append(w)
    return _vereinigen(aus)


@detektor("wissen.beruf", {"beruf"}, ALLE_PROFILE)
def beruf(dok, kontext):
    """Beruf bei Personen (Etikett oder Satz)."""
    return [Treffer(s, e, "beruf", "wissen.beruf", 0.6) for s, e in berufe_stellen(dok.text)]


@detektor("org.arbeitgeber", {"arbeitgeber"}, ALLE_PROFILE)
def arbeitgeber(dok, kontext):
    """Arbeitgeber bei Personen (Etikett oder Satz); Erlaubnisliste bleibt stehen."""
    return [Treffer(s, e, "arbeitgeber", "org.arbeitgeber", 0.6) for s, e in arbeitgeber_stellen(dok.text)]


# ======================================================================
# Orte ohne PLZ
# ======================================================================
_ORTSNAME = (rf"(?:(?:Bad|St\.|Sankt|Groß|Klein|Neu|Alt|Hohen|Ober|Unter|Nieder)[ \t]+)?[{_GROSS}][{_KLEIN}]+"
             rf"(?:-[{_GROSS}][{_KLEIN}]+){{0,3}}"
             rf"(?:[ \t]+(?:am|an[ \t]+der|im|ob[ \t]+der|bei|in[ \t]+der|v\.[ \t]?d\.|a\.[ \t]?d\.|i\.[ \t]?d\.|"
             rf"vor[ \t]+der)[ \t]+[{_GROSS}][{_KLEIN}]+(?:[ \t]+[{_GROSS}][{_KLEIN}]+)?)?"
             rf"(?:[ \t]*\([{_GROSS}][{_KLEIN}]+\))?")
_DATUM_KURZ = r"\d{1,2}\.[ \t]?(?:\d{1,2}\.|[A-ZÄÖÜa-zäöü]{3,9}\.?)[ \t]?(?:19|20)?\d{2}"
_ORT_JUNK = "[ \\t'\"‚‘’|.:;=_\\-]{0,4}"           # OCR-Reste vor dem Ort ("' Bremerhaven, 17.08.2025")
_ORT_DATUM_RE = re.compile(rf"(?:^|(?<=\t)|(?<=[ ]{{2}})|(?<=\d{{2}}[ ])){_ORT_JUNK}({_ORTSNAME})[ \t]*,[ \t]*"
                           rf"(?:den[ \t]+|am[ \t]+|im[ \t]+)?{_DATUM_KURZ}(?!\d)", re.MULTILINE)
_ORT_ETIKETT_RE = re.compile(
    rf"(?<![\wäöüß])(?:Geburtsort|Wohnort|Wohnsitz|Geburtsstadt|Ort|Stadt|Gemeinde|Heimatort)"
    rf"(?:[ \t]*/[ \t]*(?:Land|Staat|Kreis))?(?![\wäöüß])[ \t]*(?::[ \t]*|\t+[ \t]*)({_ORTSNAME})(?![\wäöüß])")
_ORT_SATZ_RE = re.compile(rf"(?<![\wäöüß])(?:geboren|geb\.|wohnhaft|wohnt|lebt|aufgewachsen|ansässig)[ \t]+"
                          rf"(?:(?:am[ \t]+{_DATUM_KURZ}[ \t]+)?in|in)[ \t]+({_ORTSNAME})(?![\wäöüß])")
_KEIN_ORT = {"datum", "stand", "ort", "unterschrift", "montag", "dienstag", "mittwoch", "donnerstag", "freitag",
             "samstag", "sonntag", "januar", "februar", "märz", "april", "mai", "juni", "juli", "august",
             "september", "oktober", "november", "dezember", "rechnung", "antrag", "hinweis", "beginn", "ende",
             "ablauf", "gültig", "heute", "kündigung", "vertrag", "schreiben", "mitteilung", "eingang", "ausgang",
             "druck", "gedruckt", "erstellt", "geändert", "angelegt", "ausgestellt", "vom", "seit", "bis", "ab",
             "zahlung", "fällig", "termin", "frist", "stichtag", "unfall", "schaden", "schadentag", "geboren",
             "zugang", "versand", "einzug", "lastschrift", "abbuchung", "zahlbar", "beitrag", "ausgabe", "seite",
             "bescheid", "hamburg-mannheimer", "nachtrag", "änderung", "stornierung", "vorgang", "bearbeitet",
             "geprüft", "freigegeben", "gesendet", "empfangen", "versandt", "ausgefertigt", "unterschrieben",
             "im", "am", "in", "und", "der", "die", "das"}


def _ort_ok(name: str) -> bool:
    erstes = name.split()[0].strip(".,").casefold()
    return erstes not in _KEIN_ORT and name.casefold() not in _KEIN_ORT and len(name) >= 3


_FIRMA_RE = re.compile(rf"(?<![\w]){_RECHTSFORM}(?![\w])|(?<![\wäöüß])(?:\w*[Vv]ersicherung(?:en|s-?AG)?|Versicherer|Bank|"
                       r"Sparkasse|\w*[Kk]asse|Rentenversicherung|Amt|Gericht|Behörde|Finanzamt|Agentur|Klinikum|"
                       r"Krankenhaus|Universität|Hochschule|Stadtverwaltung|Landratsamt|Postfach)(?![\wäöüß])")


def _ort_schluessel(name: str) -> str:
    return " ".join(name.replace("-", " ").casefold().split())


def _firmenorte(text: str) -> set:
    """Orte, die nur in Firmenanschriften vorkommen (Briefkopf/Fußzeile des Versicherers: Zeile mit Rechtsform,
    Versicherungs-/Bankwort oder Erlaubnislisten-Namen in der Anschrift oder bis zu zwei Zeilen davor)."""
    firma, person = set(), set()
    for s, e in muster.finde_plz_ort_stellen(text):
        stadt = _ort_schluessel(re.sub(r"^\D*\d{4,5}\s*", "", text[s:e]))
        if not stadt:
            continue
        a = s
        for _ in range(3):
            a = text.rfind("\n", 0, max(0, a - 1))
            if a < 0:
                a = 0
                break
        z = text.find("\n", e)
        block = text[a:z if z >= 0 else len(text)]
        ist_firma = bool(_FIRMA_RE.search(block))
        if not ist_firma:
            try:
                ist_firma = bool(wissen.index("versicherer_und_organisationen").finde(block))
            except Exception:  # pragma: no cover
                ist_firma = False
        (firma if ist_firma else person).add(stadt)
    return firma - person


def orte_stellen(text: str) -> list:
    """Orte ohne PLZ: Ort-Datum-Zeilen ("St. Ingbert, 03.04.2025", auch zweispaltig hinter einem Tabulator),
    Ort/Wohnort/Geburtsort hinter einem Etikett und "geboren in X", "wohnhaft in X". Ort-Datum-Zeilen mit dem Ort
    einer Firmenanschrift (Briefdatum des Versicherers: "Stuttgart, 14.03.2025") bleiben stehen."""
    if not text:
        return []
    aus = []
    firmenorte = None
    for m in _ORT_DATUM_RE.finditer(text):
        if not _ort_ok(m.group(1)):
            continue
        if firmenorte is None:
            firmenorte = _firmenorte(text)
        if _ort_schluessel(m.group(1)) in firmenorte:
            continue
        aus.append((m.start(1), m.end(1)))
    for regex in (_ORT_ETIKETT_RE, _ORT_SATZ_RE):
        for m in regex.finditer(text):
            if not _ort_ok(m.group(1)) or wissen.ist_allerweltswort(m.group(1).split()[0]):
                continue
            a, b = _zeilen_grenzen(text, m.start())
            zeile = text[a:b]
            if ":" not in text[m.start():m.start(1)] and zeile.count("\t\t") >= 2 and not any(
                    c.isdigit() for c in zeile):
                continue                                   # Kopfzeile einer Tabelle "PLZ / Ort ⇥ Sparte ⇥ …"
            aus.append((m.start(1), m.end(1)))
    return _vereinigen([_rstrip_stelle(text, s, e) for s, e in aus])


@detektor("ort", {"ort"}, ALLE_PROFILE)
def ort(dok, kontext):
    """Orte ohne PLZ in Ort-Datum-Zeilen, hinter Etiketten und als Geburts-/Wohnort im Satz."""
    return [Treffer(s, e, "ort", "wissen.ort", 0.6) for s, e in orte_stellen(dok.text)]


# ======================================================================
# Ausland
# ======================================================================
_CAP = rf"[{_GROSS}][{_KLEIN}{_GROSS}'’\-]+"
_STADT = rf"{_CAP}(?:[ \t]+(?:{_CAP}|\d{{1,2}}))?"
_AUSLAND_RE = re.compile(
    r"(?<![\w\-/])(?:"
    # Postleitzahl + Ort: NL "1016 GV Amsterdam", PL "00-590 Warszawa", CZ/SK "120 00 Praha 2"
    rf"\d{{4}}[ \t]?[A-Z]{{2}}[ \t]+{_STADT}"
    rf"|\d{{2}}-\d{{3}}[ \t]+{_STADT}"
    rf"|\d{{3}}[ \t]\d{{2}}[ \t]+{_STADT}"
    # Straßen: FR/BE/CH "12 rue de la Paix", "Rue du Rhône 42"
    rf"|(?:\d{{1,4}}(?:[ \t]?(?:bis|ter))?,?[ \t]+)?(?:[Rr]ue|[Aa]venue|[Bb]oulevard|Bd\.|[Pp]lace|[Cc]hemin|[Aa]llée|"
    rf"[Qq]uai|[Ii]mpasse)"
    rf"[ \t]+(?:(?:de[ \t]+la|de[ \t]+l'|du|des|de|d')[ \t]*)?{_CAP}(?:[ \t]+{_CAP}){{0,2}}(?:[ \t]+\d{{1,4}}[a-z]?)?"
    # IT "Via Roma 15", ES "Calle Mayor 8", PT "Rua Augusta 10"
    rf"|(?:Via|Viale|Piazza|Piazzale|Corso|Largo|Vicolo|Calle|Avenida|Avda\.|Plaza|Paseo|Carrer|Camino|Rua|Praça|"
    rf"Travessa)[ \t]+(?:(?:de[ \t]+la|de[ \t]+los|de[ \t]+las|del|de|da|do|dos|das|della|delle|dei)[ \t]+)?"
    rf"{_CAP}(?:[ \t]+{_CAP}){{0,2}},?[ \t]+\d{{1,4}}(?:[ \t]?[a-zA-Z](?![\w]))?"
    # PL "ul. Marszałkowska 10/12"
    rf"|(?:ul\.|ulica|al\.|aleja|pl\.|plac|os\.)[ \t]+{_CAP}(?:[ \t]+{_CAP})?[ \t]+\d{{1,4}}(?:/\d{{1,4}})?"
    # HU "Váci utca 21"
    rf"|{_CAP}[ \t]+(?:utca|út|tér|körút)[ \t]+\d{{1,4}}(?:/[A-Za-z0-9]{{1,4}})?"
    # NL "Prinsengracht 263", "Coolsingel 40"
    rf"|{_CAP}(?:straat|gracht|laan|plein|kade|singel|dijk|steeg)[ \t]+\d{{1,4}}(?:[ \t]?[a-zA-Z](?![\w]))?"
    # TR "Atatürk Cad. No: 12"
    rf"|{_CAP}[ \t]+(?:Cad\.|Caddesi|Sok\.|Sokak|Sk\.|Bulvarı|Blv\.)(?:[ \t]+No:?[ \t]*\d{{1,4}}(?:/\d{{1,4}})?)?"
    # DK/SE/NO "Østergade 12", "Storgatan 5"
    rf"|{_CAP}(?:vej|gade|gatan|vägen|veien|gata)[ \t]+\d{{1,4}}[a-zA-Z]?"
    # UK/IE "10 Downing Street"
    rf"|\d{{1,4}}[ \t]+{_CAP}(?:[ \t]+{_CAP})?[ \t]+(?:Street|Road|Avenue|Lane|Drive|Close|Square|Crescent|Terrace)"
    r")(?![\w])")
_AUSLAND_PLZ4_RE = re.compile(rf"(?<![\w\-/.,])(?:\d{{4}})[ \t]+({_STADT})(?![\w])")
_LAND_RE = re.compile(r"(?i:österreich|schweiz|niederlande|holland|belgien|luxemburg|frankreich|italien|spanien|"
                      r"portugal|polen|tschechien|slowakei|ungarn|dänemark|schweden|norwegen|türkei|kroatien|"
                      r"slowenien|rumänien|bulgarien|griechenland|austria|switzerland|netherlands|belgium|france|"
                      r"italy|spain|poland|czech|hungary|denmark|sweden|norway|turkey|united[ \t]+kingdom|"
                      r"großbritannien|england|irland|ireland)")
_KENNZEICHEN_ETIKETT_RE = re.compile(
    r"(?<![\wäöüß])(?i:amtl(?:iches|\.)?[ \t]+)?(?i:Kfz-?)?(?i:Kennzeichen|Kennz\.|Nummernschild|Plate)"
    r"(?:[ \t]*\((?P<land>[A-Z]{1,3})\))?(?:[ \t]+des[ \t]+\w+)?[ \t]*(?::[ \t]*|\t+[ \t]*)"
    r"(?P<wert>[A-Z0-9ÄÖÜ]{1,4}(?:[ \t\-·.][A-Z0-9ÄÖÜ]{1,6}){0,3})(?:[ \t]*\((?P<land2>[A-Z]{1,3})\))?(?![\w])")
_DEUTSCHES_KENNZEICHEN_RE = re.compile(r"[A-ZÄÖÜ]{1,3}[-\s][A-Z]{1,2}[ \t]?\d{1,4}[EH]?")


def ausland_stellen(text: str) -> list:
    """Ausländische Anschriften (Straße und PLZ+Ort typischer Nachbarländer) und ausländische Kennzeichen hinter
    einem Etikett ("Kennzeichen: 67-BDK-1", "LU 946067")."""
    if not text:
        return []
    aus = []
    for m in _AUSLAND_RE.finditer(text):
        wert = m.group(0)
        if re.fullmatch(r"\d{3}[ \t]\d{2}[ \t]+.*", wert) and not _LAND_RE.search(
                text[max(0, m.start() - 120):m.end() + 60]):
            continue                                       # "120 00 Praha" nur mit Länderhinweis
        aus.append((m.start(), m.end()))
    # vierstellige PLZ (A, CH, BE, DK, HU, LU, NO …) nur mit Länderhinweis oder ausländischer Straße davor
    belegt = list(aus)
    for m in _AUSLAND_PLZ4_RE.finditer(text):
        land = _LAND_RE.search(text[max(0, m.start() - 120):m.end() + 60])
        nach_strasse = any(a < m.start() and 0 <= m.start() - b < 6 for a, b in belegt)
        if land or nach_strasse:
            stadt = m.group(1)
            if stadt.split()[0].casefold() in _KEIN_ORT or wissen.ist_allerweltswort(stadt.split()[0]):
                continue
            aus.append((m.start(), m.end()))
    for m in _KENNZEICHEN_ETIKETT_RE.finditer(text):
        wert = m.group("wert")
        if not any(c.isdigit() for c in wert) or sum(c.isalnum() for c in wert) < 4:
            continue
        if _DEUTSCHES_KENNZEICHEN_RE.fullmatch(wert) and not (m.group("land") or m.group("land2")):
            continue                                       # deutsches Kennzeichen: Kategorie kfz
        aus.append((m.start("wert"), m.end("wert")))
    return _vereinigen(aus)


@detektor("international", {"international"}, ALLE_PROFILE)
def international(dok, kontext):
    """Ausländische Anschriften und Kennzeichen (Telefonnummern mit +Vorwahl erkennt muster.telefon)."""
    return [Treffer(s, e, "international", "international", 0.65) for s, e in ausland_stellen(dok.text)]


# ======================================================================
# Geburtsdaten ohne Stichwort
# ======================================================================
_DATUM_RE = re.compile(r"(?<![\d.])\d{1,2}\.[ \t]?\d{1,2}\.[ \t]?(?:19|20)?\d{2}(?![\d])"
                       r"|(?<![\d.])\d{1,2}\.[ \t]?(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|"
                       r"Oktober|November|Dezember|Jan\.|Feb\.|Mrz\.|Apr\.|Jun\.|Jul\.|Aug\.|Sep\.|Okt\.|Nov\.|Dez\.)"
                       r"[ \t]?(?:19|20)\d{2}(?!\d)")
_NAME_VOR_RE = re.compile(rf"((?:{_WORT_GROSS})(?:[ \t]+(?:von|van|de|der|den|zu|vom)?[ \t]*{_WORT_GROSS}){{1,3}})"
                          r"[ \t]*(?:,|\*|\()[ \t]*$")
_ALTER_RE = re.compile(rf"((?:{_WORT_GROSS})(?:[ \t]+{_WORT_GROSS}){{1,3}})[ \t]*(?:\([ \t]*(\d{{1,3}})"
                       r"(?:[ \t]*(?:J\.|Jahre|Jahren|jährig))?[ \t]*\)|,[ \t]*(\d{1,3})[ \t]+(?:Jahre|J\.)(?:[ \t]+alt)?"
                       r"(?=[,.;\n]))")
_VERTRAGSDATUM_RE = re.compile(
    r"(?i:beginn|ablauf|stand|datum|vom|ab|seit|bis|gültig|fällig|rechnung|zahlung|termin|frist|eingang|"
    r"schreiben|kündigung|unterschrift|antrag|policierung|zugang|versicherungsbeginn|laufzeit|ende|abschluss|"
    r"änderung|erstellt|gedruckt|druck|schadentag|unfalltag|schaden|unfall|geschehen|ausgestellt|erteilt|"
    r"heute|am|den|zum|per|vertrag|police|leistung|auszahlung|überweisung|buchung|stichtag)(?![\wäöüß])")


def _ist_name(teile: str) -> bool:
    """Mindestens zwei großgeschriebene Wörter, keines ist ein Allerweltswort, und entweder ein Wort ist ein
    eindeutiger Vor-/Nachname der Wissensbasis oder das erste ein (auch mehrdeutiger) Vorname ("Max Mustermann")."""
    woerter = [w for w in re.split(r"[ \t]+", teile) if w and w[0].isupper()]
    if len(woerter) < 2:
        return False
    if any(wissen.ist_allerweltswort(w) for w in woerter):
        return False
    if wissen.ist_vorname(woerter[0]):
        return True
    return any((wissen.ist_vorname(w) and not wissen.ist_vorname_mehrdeutig(w))
               or (wissen.ist_nachname(w) and not wissen.ist_mehrdeutig(w)) for w in woerter)


def _jahre_her(datum: str):
    teile = muster._datum_zerlegen(datum)
    if not teile:
        return None
    t, mo, j = teile
    try:
        d = datetime.date(j, mo, t)
    except ValueError:
        return None
    return (datetime.date.today() - d).days / 365.25


def geburt_ohne_stichwort(text: str, alle: bool = False) -> list:
    """[(start, ende, sicherheit)]: Datum direkt hinter einem Namen ("Max Mustermann, 02.09.61") mit plausiblem
    Geburtsjahr (mindestens 10 Jahre her – ein Unterschriftsdatum ist jünger), Alter hinter einem Namen
    ("Anna Berg (54)"); mit alle=True (Schutzstufe „maximal“) jedes Datum, das mindestens 14 Jahre zurückliegt
    und nicht hinter Vertragsvokabular steht."""
    if not text:
        return []
    aus = []
    for m in _DATUM_RE.finditer(text):
        datum = m.group(0)
        if not muster.geburtsdatum_plausibel(datum):
            continue
        jahre = _jahre_her(datum)
        if jahre is None:
            continue
        a = text.rfind("\n", 0, m.start()) + 1
        davor = text[a:m.start()]
        n = _NAME_VOR_RE.search(davor)
        if n and jahre >= 10 and _ist_name(n.group(1)) and not _VERTRAGSDATUM_RE.search(davor[n.end(1):]):
            aus.append((m.start(), m.end(), 0.65))
            continue
        if alle and jahre >= 14:
            fenster = text[max(a, m.start() - 40):m.start()]
            satz = re.search(r"[.!?;][ \t]+(?=[^.!?;]*$)", fenster)
            if satz:
                fenster = fenster[satz.end():]                 # nur der eigene Satz zählt
            if not _VERTRAGSDATUM_RE.search(fenster):
                aus.append((m.start(), m.end(), 0.45))
    for m in _ALTER_RE.finditer(text):
        alter = m.group(2) or m.group(3)
        if alter and 0 < int(alter) <= 110 and _ist_name(m.group(1)):
            g = 2 if m.group(2) else 3
            aus.append((m.start(g), m.end(g), 0.55))
    return aus


@detektor("wissen.geburt", {"geburt"}, ALLE_PROFILE)
def geburt(dok, kontext):
    """Geburtsdaten ohne Stichwort in Personenkontext; in „maximal“ alle plausiblen Geburtsdaten."""
    alle = muster.option(kontext.profil, "alle_geburtsdaten")
    return [Treffer(s, e, "geburt", "wissen.geburt", si) for s, e, si in geburt_ohne_stichwort(dok.text, alle)]


# ----------------------------------------------------------------------
# klassisch.py hängt für jede Kategorie mit Text-Funktion einen Muster-Detektor ein; für die Wissens-Kategorien
# liefern die Detektoren dieses Moduls die Stellen (sonst würde jeder Fundtext an allen Ganzwort-Stellen gesucht)
# ----------------------------------------------------------------------
for _k in ("beruf", "arbeitgeber", "diagnose", "medikament", "ort", "international"):
    entfernen(f"muster.{_k}")
