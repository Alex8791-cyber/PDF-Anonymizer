"""Wissensbasierte Detektoren mit Personenkontext (Vertrag Abschnitt 3, Schutzstufen Abschnitt 9).

    wissen.gesundheit  Diagnosen, Medikamente (Listen der Wissensbasis), ICD-10-Codes und Körpermaße – nur mit
                       Gesundheitskontext (Diagnose:, leidet an, Medikation:, ICD-Code, Dosierung)
                       -> Kategorien "diagnose", "medikament". In „maximal“ geschwärzt; in „hoch“ erkennt die
                       Analyse sie als Hinweis (muster.hinweis_kategorien) und bietet sie abgewählt an.
                       Stützt sich ein Treffer nur auf allgemeine Wörter (Therapie, ambulant, Krankenhaus, Reha …),
                       die genauso in Tarif- und Leistungsübersichten stehen, ist er nur vermutet: Quelle
                       "wissen.gesundheit.vermutet", Sicherheit 0.5 (erkannt wird er trotzdem).
    wissen.beruf       Beruf hinter einem Etikett (Beruf:, ausgeübte Tätigkeit:) oder im Satz (arbeitet als,
                       ist … von Beruf), in der Spalte "Beruf"/"Tätigkeit" einer Personentabelle und unter dem
                       Etikett eines Kastenformulars ("Beruf (genaue Tätigkeit)" ⏎ "Pflegehelferin"), auch in einer
                       Formularzeile aus Feldbezeichnern mit der Wertzeile darunter (Scan: "Telefon ⇥⇥ Beruf" ⏎
                       "08631 98765 ⇥⇥ Pflegehelferin") -> "beruf"; die Nachbarzelle einer Kopfzeile ist kein Beruf
    org.arbeitgeber    Organisation hinter "Arbeitgeber:" oder im Satz (beschäftigt bei, arbeitet … bei der …)
                       -> "arbeitgeber"; Versicherer, Banken und Behörden der Erlaubnisliste bleiben IMMER stehen
    ort                Ort ohne PLZ: Ort-Datum-Zeilen ("St. Ingbert, 03.04.2025"), Geburts-/Wohnort hinter einem
                       Etikett oder "geboren in", "wohnhaft in" -> "ort"
    international      ausländische Anschriften (NL, PL, CZ, IT, FR, ES, HU, TR, DK/SE/NO, UK …) und Kennzeichen
                       hinter einem Etikett -> "international"
    wissen.geburt      Datum ohne Stichwort direkt hinter einem Namen ("Max Mustermann, 02.09.61"), Alter in
                       Klammern hinter einem Namen ("Anna Berg (54)"); im Familien- und Versichertenkontext
                       (personenkontext: "Kind 2: Bastian Leutgeb, 30.06.2018", Kinderliste unter "Kinder:") in jedem
                       Alter, nicht hinter Behandlern; in „maximal“ zusätzlich jedes plausible Geburtsdatum außerhalb
                       von Vertragsdaten -> "geburt"

Die Text-Funktionen (berufe_stellen, …) arbeiten auf normalisiertem Text und liefern [(start, ende)]; muster.py
nutzt sie für die Text-Schnittstelle (Formularfelder, Werkzeuge).
"""

from __future__ import annotations

import datetime
import re

from .. import kennungsformen, muster, personenkontext, wissen
from . import ALLE_PROFILE, Treffer, detektor, entfernen

_GROSS = "A-ZÄÖÜÀ-ÖØ-ÞĀĂĄĆČĎĐĒĖĘĚĞĢĪĮİĶĹĻĽŁŃŅŇŌŐŒŔŘŚŞŠŢŤŪŮŰŲŹŻŽ"
_KLEIN = "a-zäöüßà-öø-ÿāăąćčďđēėęěğģīįıķĺļľłńņňōőœŕřśşšţťūůűųźżžșț"
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
# Genitiv hinter "Beruf": wessen Beruf ("Beruf des Ehepartners", "Beruf der versicherten Person", "Beruf der zu
# versichernden Person") – höchstens ein kleingeschriebenes Wort vor dem großgeschriebenen Rollenwort
_BERUF_GENITIV = r"(?:[ \t]+(?:des|der)(?:[ \t]+(?:zu[ \t]+)?[a-zäöüß]+)?[ \t]+[A-ZÄÖÜ][\wäöüß\-]*)"
_BERUF_ETIKETT_RE = re.compile(
    r"(?<![\wäöüß])(?i:(?:ausgeübte[rn]?|derzeitige[rn]?|jetzige[rn]?|erlernte[rn]?|aktuelle[rn]?|"
    r"zuletzt[ \t]+ausgeübte[rn]?)[ \t]+)?"
    rf"(?:Beruf{_BERUF_GENITIV}?|Berufsbezeichnung|Berufsstand|Berufsgruppe|(?i:Tätigkeit)|berufliche[ \t]+Tätigkeit|"
    r"Stellung[ \t]+im[ \t]+Beruf|"
    r"Occupation|Profession)(?P<ag>[ \t]*/[ \t]*(?:Tätigkeit|Arbeitgeber|Stellung|Branche))?(?![\wäöüß])"
    r"(?:[ \t]*\([^)\n]{1,20}\))?(?:[ \t]*:[ \t]*|\t+[ \t]*)")
_BERUF_VOR_RE = re.compile(
    # Verb und "als" mit bis zu vier Wörtern dazwischen ("arbeitet in Teilzeit als Hufschmiedin", "ist seit 2019 bei uns
    # als Monteur beschäftigt"; Nachprüfung NP-12) – der Beruf dahinter muss in der Wissensbasis stehen
    r"(?<![\wäöüß])(?:arbeitet(?:e)?|arbeiten|jobbt|beschäftigt|angestellt|eingestellt)"
    r"(?:[ \t]+[^\s.,;:!?]+){1,4}?[ \t]+als[ \t]+"
    r"|(?<![\wäöüß])(?:[Aa]rbeitet(?:e)?|[Aa]rbeiten|[Tt]ätig(?:[ \t]+(?:ist|war|sind))?|[Bb]eschäftigt|[Aa]ngestellt|"
    r"[Ee]ingestellt|[Ss]elbst(?:st)?ändig|[Ff]reiberuflich|[Aa]usgebildet(?:e[rn]?)?|Ausbildung|Tätigkeit|Arbeit|"
    r"Anstellung|Beschäftigung|Stelle|Job|Lehre|Umschulung|[Bb]eruflich|[Ee]hemals|[Ff]rüher)"
    r"[ \t]+(?:als|zum|zur)[ \t]+"
    r"|(?<![\wäöüß])(?:ist|war|bin|sind|wird|wurde|Beruf:?)[ \t]+"
    # Zeitangaben und Adverbien zwischen "ist"/"war" und dem Beruf ("Sie war früher Lehrerin", "Er ist seit 2015
    # Busfahrer", "Sie ist inzwischen Rentnerin"; Abnahme 5 A5-12)
    r"(?:(?:früher|frueher|damals|inzwischen|mittlerweile|jetzt|nun|bereits|schon|noch|zuletzt|wieder|seit[ \t]+"
    r"(?:\d{4}|Jahren|kurzem|langem)|lange|gelernte[rn]?|eigentlich)[ \t]+){0,2}(?:von[ \t]+Beruf[ \t]+)?"
    r"|(?<![\wäöüß])von[ \t]+Beruf[ \t]+"
    # weitere Satzstellungen (Abnahme 2 V3): "Von Beruf ist er Schreiner", "übt den Beruf der Floristin aus",
    # "hauptberuflich Zimmerer", "ist nebenberuflich als Kellner tätig"
    r"|(?<![\wäöüß])[Vv]on[ \t]+Beruf[ \t]+(?:ist|war|wird|wurde|bin|sind)[ \t]+(?:er|sie|ich|wir)[ \t]+"
    r"|(?<![\wäöüß])(?:übt|übte|üben|übten|ausübt|ausübte)(?:[ \t]+[^\s.,;:!?]+){0,3}?[ \t]+(?:den|einen|seinen|ihren)"
    r"[ \t]+Beruf[ \t]+"
    r"(?:der|des|eines|einer|als)[ \t]+"
    # "Er hat den Beruf des Bäckers erlernt.", "Sie lernt den Beruf der Floristin." (Abnahme 4 AB4-18)
    r"|(?<![\wäöüß])(?:den|einen|seinen|ihren)[ \t]+Beruf[ \t]+(?:des|der|eines|einer)[ \t]+"
    r"|(?<![\wäöüß])(?:(?:[Hh]aupt|[Nn]eben)beruflich|[Nn]ebenbei|[Nn]ebenher)(?:[ \t]+als)?[ \t]+"
    # Lebensunterhalt ("Sie verdient ihr Geld als Hebamme"; Abnahme N3)
    r"|(?<![\wäöüß])(?:verdient(?:e)?|verdienen|bestreitet|bestritt)[ \t]+(?:ihr(?:en)?|sein(?:en)?|das|den)[ \t]+"
    r"(?:Geld|Lebensunterhalt|Unterhalt|Brot)[ \t]+als[ \t]+")
_BERUF_NEBENSATZ_RE = re.compile(r"(?<![\wäöüß])(?:er|sie|ich|Mann|Frau|Ehemann|Ehefrau|Sohn|Tochter|Vater|Mutter|"
                                 r"Partner(?:in)?|Lebensgefährt(?:e|in))[ \t]+(?=[A-ZÄÖÜ])")
_BERUF_RELATIVSATZ_RE = re.compile(r",[ \t]*(?:der|die)[ \t]+(?=[A-ZÄÖÜ])")
# Rollen in einem Vorgang, die im Relativsatz keine Berufsangabe sind ("Der Zeuge, der Fahrer war, …")
_ROLLE_IM_VORGANG = frozenset({"fahrer", "fahrerin", "beifahrer", "beifahrerin", "halter", "halterin", "zeuge",
                               "zeugin", "eigentümer", "eigentümerin", "mieter", "mieterin", "vermieter", "vermieterin"})
_NEBENSATZ_VERB_RE = re.compile(r"[ \t]+(?:ist|war|wurde|wird|geworden[ \t]+ist|gewesen[ \t]+ist)[ \t]*(?:[.,;!?)]|$)",
                                re.MULTILINE)
# "als <Beruf>" mit einem Verb der Erwerbstätigkeit dahinter ("ist als Dachdecker tätig", "war bis 2020 als Schreiner
# tätig", "hat als Monteur gearbeitet"; Abnahme N3) – ohne dieses Verb ist "als Fahrer" eine Rolle, kein Beruf
_ALS_RE = re.compile(r"(?<![\wäöüß])als[ \t]+")
_ERWERB_DANACH_RE = re.compile(r"(?:[ \t]+[^\s.,;:!?]+){0,4}?[ \t]+(?:tätig|beschäftigt|angestellt|eingestellt|"
                               r"gearbeitet|arbeitet|arbeitete|selbst(?:st)?ändig|verbeamtet)(?![\wäöüß])")
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


# Rollen statt Berufen im Satz: die eigene Rolle des Maklers, Vertretungs- und Verwaltungsrollen, Ehrenämter
# ("Wir sind als Versicherungsmakler für Sie tätig", "Die Kanzlei ist als Insolvenzverwalter tätig", "Der Sohn ist als
# Betreuer seiner Mutter tätig", "ist ehrenamtlich als Trainer tätig"; Abnahme 2 A2-03) – die Selbstkontrolle meldet
# sie, wenn der Satz von einer Person und ihrer Arbeit spricht
_ROLLE_ENDUNGEN = ("makler", "maklerin", "vermittler", "vermittlerin", "verwalter", "verwalterin", "betreuer",
                   "betreuerin", "bevollmächtigter", "bevollmächtigte", "veranstalter", "veranstalterin", "trainer",
                   "trainerin", "schiedsrichter", "schiedsrichterin", "sachverständiger", "sachverständige", "vormund",
                   "treuhänder", "treuhänderin", "testamentsvollstrecker", "testamentsvollstreckerin")
# Satz einer Organisation oder des Schreibers in der Mehrzahl: Subjekt am Satzanfang ("Wir sind …", "Die Kanzlei Dr.
# Reitmayr ist …", "Der Verein verdient sein Geld …", "Die GmbH …")
_ORG_SATZANFANG_RE = re.compile(
    r"(?:^|[.!?;:\n])[ \t]*(?:(?:[Ww]ir|[Uu]ns)(?![\wäöüß])|(?:(?:[Dd]er|[Dd]ie|[Dd]as|[Uu]nser\w{0,2}|[Ii]hr\w{0,2})[ \t]+)?"
    r"(?:Kanzlei|Verein|Gesellschaft|Firma|Betrieb|Unternehmen|Hausverwaltung|Verwaltung|Agentur|Büro|Praxis|"
    r"Genossenschaft|Stiftung|Gemeinde|Stadt|Behörde|Versicherung|Versicherer|Bank|Sparkasse|Gruppe|Holding|"
    r"GmbH|AG|KG|OHG|GbR|UG)(?![\wäöüß]))")
_EHRENAMT_RE = re.compile(r"(?i)(?<![\wäöüß])(?:ehrenamtlich\w{0,2}|im[ \t]+ehrenamt|unentgeltlich)(?![\wäöüß])")


# Abkürzungen mit Punkt beenden keinen Satz ("Die Kanzlei Dr. Reitmayr ist …", "Fa. Huber")
_ABKUERZUNG_VOR_PUNKT_RE = re.compile(r"(?<![\wäöüß])(?:Dr|Prof|Dipl|Ing|med|jur|rer|nat|Nr|Fa|St|Hr|Fr|Str|bzw|ca|"
                                      r"vgl|ggf|inkl|zzgl|evtl|usw|Mio|Tsd|Abs|Art|Ziff|Pos|Kfm|Gebr|Inh|[A-ZÄÖÜ])$")


def satz_anfang(text: str, pos: int, fenster: int = 200) -> int:
    """Anfang des Satzes, in dem pos steht: hinter dem letzten Satzzeichen bzw. Zeilenumbruch im Fenster davor –
    ein Punkt hinter einer Abkürzung zählt nicht."""
    anfang = max(0, pos - fenster)
    i = pos
    while i > anfang:
        i -= 1
        c = text[i]
        if c in "!?;\n" or (c == "." and not _ABKUERZUNG_VOR_PUNKT_RE.search(text, max(anfang, i - 6), i)):
            return i + 1
    return anfang


# Der Beruf direkt hinter "ist"/"war"/"von Beruf"/"hauptberuflich" ("Er ist Fitnesstrainer in Rosenheim.", "Sie ist von
# Beruf Versicherungsmaklerin.", "Sie ist hauptberuflich Kinderbetreuerin."): eine Berufsangabe, auch mit Rollen-Endung
# (Abnahme 4 AB4-06, AB4-18)
_BERUF_DIREKT_DAVOR_RE = re.compile(r"(?i)(?<![\wäöüß])(?:(?:ist|war|bin|sind|wird|wurde)[ \t]+(?:von[ \t]+Beruf[ \t]+)?|"
                                    r"von[ \t]+Beruf[ \t]+|(?:haupt|neben)beruflich[ \t]+)$")
_BERUFLICH_DAVOR_RE = re.compile(r"(?i)(?<![\wäöüß])(?:von[ \t]+Beruf|(?:haupt|neben)?beruflich)[ \t]+$")
# Person als Objekt im Satz einer Organisation ("Die Firma hat sie 2019 als Hebamme eingestellt.", "Die Stadt
# beschäftigt ihn seit 2015 als Schreiner."): der Beruf dieser Person (AB4-06)
_PERSON_OBJEKT_RE = re.compile(r"(?<![\wäöüß])(?:ihn|sie|ihm|ihr|Herrn|Frau|Herr)(?![\wäöüß])")


def rolle_allein(wort: str) -> bool:
    """Ist das Wort eine Rolle der Liste _ROLLE_ENDUNGEN ohne Bestimmungswort ("Trainer", "Betreuerin", "Verwalter")?
    Ein Kompositum mit Rollen-Endung ist eine Berufsbezeichnung ("Fitnesstrainer", "Kinderbetreuerin",
    "Vermögensverwalterin", "Insolvenzverwalter", "Immobilienmakler"; Abnahme 4 AB4-06)."""
    return (wort or "").casefold() in _ROLLE_ENDUNGEN


# "den Beruf des Bäckers erlernt", "übt den Beruf der Floristin aus": ein Verb des Erlernens oder Ausübens macht "Beruf
# des X" zum Beruf einer Person; ohne es ist der Satz eine allgemeine Einstufung ("Für den Beruf des Dachdeckers gilt
# die Gefahrengruppe B."; Abnahme 5 AB5U-07) – die Selbstkontrolle meldet ihn dann (Grundsatz P1)
_BERUF_DES_RE = re.compile(r"(?i)(?<![\wäöüß])(?:den|einen|seinen|ihren|vom|zum|im|dem)[ \t]+Beruf[ \t]+(?:des|der|eines|einer)[ \t]+$")
# Nachbesserung 8 (Abnahme 6 A6-06, AB6U-10): "hat" allein ist kein Verb des Erlernens ("Für den Beruf des Dachdeckers
# hat der Versicherer die Gefahrengruppe B festgelegt."); eine Person im Satz macht den Beruf zu ihrem ("Sein Sohn
# strebt den Beruf des Polizisten an.", "Ihr Sohn bewirbt sich auf den Beruf des Soldaten.")
_BERUF_LERNEN_RE = re.compile(r"(?i)(?<![\wäöüß])(?:\w*lern\w*|\w*übt\w*|\w*uebt\w*|ausgeübt|ausgeuebt|ergriffen|"
                              r"ergreift|ergreifen|studiert\w*|absolviert\w*|ausbildung\w*|ausgebildet\w*|gewechselt|"
                              r"wechselt\w*|wollte|will|möchte|moechte|ausüben|ausueben|strebt\w*|anstreb\w*|"
                              r"bewirbt|beworben|bewerb\w*|plant|plante|träumt\w*|traeumt\w*|gewählt|gewaehlt|wählt\w*|"
                              r"waehlt\w*|aufgegeben|aufgibt|beginnt|begonnen|begann|ausgeübt)(?![\wäöüß])")
_BERUF_DES_PERSON_RE = re.compile(r"(?<![\wäöüß])(?:[Ee]r|[Ss]ie|[Ii]ch|[Ss]ein(?:e|en|em|er|es)?|[Ii]hr(?:e|en|em|er|es)?|"
                                  r"[Mm]ein(?:e|en|em|er|es)?|Herr|Herrn|Frau|Sohn|Tochter|Ehemann|Ehefrau|Enkel|Enkelin|"
                                  r"Neffe|Nichte|Kind|Bruder|Schwester|Vater|Mutter)(?![\wäöüß])")
# Rolle direkt hinter "ist"/"war" mit einer Ergänzung im Genitiv oder mit Possessiv ("Er ist Trainer der F-Jugend.",
# "Sie ist Betreuerin ihrer Mutter."): ein Ehrenamt oder eine familiäre Rolle – gemeldet, nicht geschwärzt (AB5U-07)
_ROLLE_ERGAENZUNG_RE = re.compile(r"[ \t]+(?:der|des|ihrer|ihres|seiner|seines|meiner|meines|unserer|unseres|deren|"
                                  r"dessen|eurer)[ \t]+[\wÄÖÜäöüß]")


def beruf_des_ohne_person(text: str, m, start: int) -> bool:
    """Ist der Treffer von _BERUF_VOR_RE "den Beruf des X" ohne ein Verb des Erlernens oder Ausübens im Satz?"""
    if not _BERUF_DES_RE.search(m.group(0)):
        return False
    a = satz_anfang(text, start)
    hinten = re.search(r"[.!?;\n]", text[start:start + 200])
    ende = start + (hinten.start() if hinten else min(200, len(text) - start))
    if _BERUF_LERNEN_RE.search(text, a, ende) is not None:
        return False
    return _BERUF_DES_PERSON_RE.search(text, a, ende) is None and not any(
        personenkontext.ist_personenwort(w) for w in re.findall(r"[A-ZÄÖÜ][a-zäöüß]+", text[a:ende]))


def rolle_mit_ergaenzung(text: str, start: int, ende: int) -> bool:
    """Ist text[start:ende] eine Rolle ohne Bestimmungswort (rolle_allein) mit einer Ergänzung dahinter?"""
    return rolle_allein(text[start:ende]) and _ROLLE_ERGAENZUNG_RE.match(text, ende) is not None


def beruf_satz_ausgenommen(text: str, start: int, ende: int) -> bool:
    """Ist der Beruf text[start:ende] in seinem Satz eine Rolle statt des Berufs einer Person: eine Rolle der Liste
    _ROLLE_ENDUNGEN ohne Bestimmungswort (rolle_allein) – außer direkt hinter "ist", "von Beruf", "hauptberuflich" –,
    ein Ehrenamt ("ist ehrenamtlich als Kassiererin im Verein tätig"; die Selbstkontrolle meldet ihn, wenn der Satz von
    einer Person spricht) oder der Satz einer Organisation bzw. des
    Schreibers ("Wir sind als Versicherungsmakler für Sie tätig") ohne Person als Objekt ("Die Firma hat sie als
    Hebamme eingestellt" ist der Beruf dieser Person)? Für die Sätze der Erkennung (nicht hinter einem Etikett) und die
    Selbstkontrolle."""
    wort = text[start:ende]
    direkt = bool(_BERUF_DIREKT_DAVOR_RE.search(text, max(0, start - 40), start))
    # "von Beruf" bzw. "haupt-/nebenberuflich" direkt davor: die Rolle ist der Beruf einer Person, auch mit Ergänzung
    # ("Er ist von Beruf Trainer der F-Jugend."; Nachbesserung 8 nach Abnahme 6 A6-05)
    beruflich = bool(_BERUFLICH_DAVOR_RE.search(text, max(0, start - 40), start))
    if rolle_allein(wort) and (not direkt or (rolle_mit_ergaenzung(text, start, ende) and not beruflich)):
        return True
    satz_anfang_ = satz_anfang(text, start)
    hinten = re.search(r"[.!?;\n]", text[ende:ende + 200])
    satz_ende = ende + (hinten.start() if hinten else min(200, len(text) - ende))
    if _EHRENAMT_RE.search(text, satz_anfang_, satz_ende):
        return True                             # Ehrenamt: die Selbstkontrolle meldet den Beruf einer Person (AB4-06)
    return org_satz(text, satz_anfang_, start) and not _PERSON_OBJEKT_RE.search(text, satz_anfang_ + 1, start)


def org_satz(text: str, satz_anfang_: int, bis: int) -> bool:
    """Beginnt der Satz ab satz_anfang_ mit einer Organisation oder "wir" als Subjekt?"""
    return bool(_ORG_SATZANFANG_RE.match(text, max(0, satz_anfang_ - 1), bis))


# Grundwort einer Tätigkeit, die in der Wissensbasis fehlen kann ("Putzfrau", "Putzkraft", "Paketbote",
# "Reinigungsfachkraft") – nur hinter einem Wort der Erwerbstätigkeit ("arbeitet als", "ist als … tätig"; Abnahme 3
# AB3-06)
_TAETIGKEIT_GRUNDWORT_RE = re.compile(r"[A-ZÄÖÜ][a-zäöüß]{2,30}(?:frau|mann|kraft|bote|botin|hilfe|helfer|helferin)"
                                      r"(?![\wäöüß\-])")
# Erwerbstätigkeit im Satzteil vor "als" ("arbeitet als", "ist als … tätig", "jobbt als")
_ERWERB_IM_TREFFER_RE = re.compile(r"(?i)arbeit|jobbt|beschäftigt|angestellt|eingestellt|tätig|verdien")


def _beruf_gebeugt_stelle(text: str, p: int, ende_zelle: int):
    """(start, ende) eines gebeugten Berufs der Wissensbasis direkt ab p ("des Schreiners", "des Bäckers", "dem
    Maurern"; Abnahme 3 AB3-06) oder None."""
    m = re.match(r"[A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)*", text[p:ende_zelle])
    if m is None:
        return None
    wort = m.group(0)
    for endung in ("es", "s", "en", "n"):
        if wort.endswith(endung) and len(wort) - len(endung) >= 4 and wissen.ist_beruf(wort[:-len(endung)]):
            if wort[:-len(endung)].casefold() in _BERUF_ALLGEMEIN:
                return None
            return p, p + len(wort)
    return None


# Satzgegenstand aus Artikel und Hauptwort ("Die Software arbeitet als Eingabehilfe …"): nur ein Programm, Gerät, eine
# Anlage oder ein System nach seinem Grundwort ist eine Sache – eine Tätigkeit nach ihrem Grundwort ("-hilfe", "-kraft")
# ist dann kein Beruf (Abnahme 4, Altbefund AB3-06). Jeder andere Satzgegenstand kann eine Person sein, auch ein
# substantiviertes Beiwort oder eine Rolle ("Der Verletzte arbeitet als Lagerhilfe.", "Die Bevollmächtigte arbeitet als
# Bürokraft.", "Der Beifahrer …"; Abnahme 5 A5-03)
_SACH_SUBJEKT_RE = re.compile(r"[ \t]*(?:Der|Die|Das|Dieser|Diese|Dieses|Unser|Unsere|Ihr|Ihre)[ \t]+"
                              r"([A-ZÄÖÜ][\wäöüß\-]{2,40})[ \t]")
# "bot" nur als Programm ("Chatbot", "Bots") – nicht "-bote" ("Der Eilbote arbeitet als Lagerhilfe."; Abnahme 6 A6-09)
_SACH_SUBJEKT_GRUNDWORT_RE = re.compile(r"(?i)[\wäöüß\-]*(?:software|programm|app|anwendung|tool|system|modul|"
                                        r"funktion|plattform|gerät|geraet|maschine|anlage|roboter|automat|sensor|"
                                        r"steuerung|computer|rechner|server|algorithmus|schnittstelle|"
                                        r"technik|lösung|loesung|datenbank|maske|oberfläche|oberflaeche|"
                                        r"vorlage|formular|"
                                        # Hilfsmittel und Hebezeuge ("Die Rampe arbeitet als Einstiegshilfe …", "Die
                                        # Hebebühne arbeitet als Montagehilfe …"; Abnahme 6 AB6U-10 b)
                                        r"rampe|hebebühne|hebebuehne|bühne|buehne|lift|aufzug|kran|stapler|rollator|"
                                        r"rollstuhl|treppenlift|gerüst|geruest|vorrichtung|halterung|schiene|"
                                        r"hilfsmittel|werkzeug|fahrzeug|pumpe|kamera|drohne)(?:e|en|s|n)?|"
                                        r"[\wäöüß\-]*bots?")


def _sache_als_subjekt(text: str, pos: int) -> bool:
    """Beginnt der Satz vor pos mit Artikel und einem Programm, Gerät, einer Anlage oder einem System nach seinem
    Grundwort (_SACH_SUBJEKT_GRUNDWORT_RE: "Die Software …", "Das Programm …")?"""
    m = _SACH_SUBJEKT_RE.match(text, satz_anfang(text, pos), pos)
    if m is None:
        return False
    w = m.group(1)
    return bool(_SACH_SUBJEKT_GRUNDWORT_RE.fullmatch(w)) and not (
        personenkontext.ist_personenwort(w) or wissen.ist_beruf(w) or wissen.ist_nachname(w) or wissen.ist_vorname(w))


def _beruf_wert(text: str, pos: int, etikett: bool, grundwort: bool = False):
    """(start, ende) eines Berufs ab pos (Adjektive davor erlaubt) oder None. Hinter einem Etikett zählt auch ein
    unbekannter Beruf (Wert der Zelle), im Satz nur ein Eintrag der Wissensbasis – auch gebeugt ("des Schreiners") –
    und mit grundwort hinter einem Wort der Erwerbstätigkeit eine Tätigkeit nach ihrem Grundwort ("arbeitet als
    Putzfrau")."""
    adj = _BERUF_ADJEKTIV_RE.match(text, pos)
    p = adj.end() if adj else pos
    ende_zelle = _zelle_ende(text, p, 80)
    ausschnitt = text[p:ende_zelle]
    treffer = [v for v in wissen.index("berufe").finde(ausschnitt) if v.start <= 25]
    if not treffer and not etikett:
        gebeugt = _beruf_gebeugt_stelle(text, p, ende_zelle)
        if gebeugt is not None:
            return gebeugt
        if grundwort:
            g = _TAETIGKEIT_GRUNDWORT_RE.match(text, p, ende_zelle)
            if g is not None and not wissen.ist_vorname(g.group(0)) and not wissen.ist_nachname(g.group(0)) \
                    and not _sache_als_subjekt(text, pos):
                return g.span()
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


_ZELLE_RE = re.compile(r"[^\t\n]+")
# Kopfzeile einer Personentabelle: eine Zelle für den Namen der Person
_PERSONEN_KOPF_RE = re.compile(r"(?i)(?<![\wäöüß])(?:name|vorname|nachname|versicherte[rn]?|mitarbeiter(?:in)?|"
                               r"person|teilnehmer(?:in)?)(?![\wäöüß])")
# Berufsangabe allein auf ihrer Zeile, der Wert in der Zeile darunter (Kastenformular: "Beruf (genaue Tätigkeit)" ⏎
# "Pflegehelferin")
_BERUF_KOPF_ZEILE_RE = re.compile(
    r"(?m)^[ \t]*(?i:(?:ausgeübte[rn]?|derzeitige[rn]?|jetzige[rn]?|erlernte[rn]?|aktuelle[rn]?)[ \t]+)?"
    rf"(?:Beruf{_BERUF_GENITIV}?|Berufsbezeichnung|(?i:Tätigkeit)|berufliche[ \t]+Tätigkeit)"
    r"(?:[ \t]*\([^)\n]{1,30}\))?[ \t]*\n"
    r"[ \t]*(?=[^\W\d_])")


def _zellen(zeile: str, versatz: int) -> list:
    """(start, ende, text) der Zellen einer Zeile (getrennt durch Tabulatoren)."""
    return [(versatz + z.start(), versatz + z.end(), z.group(0).strip()) for z in _ZELLE_RE.finditer(zeile)
            if z.group(0).strip()]


def _feldbezeichner(wert: str) -> bool:
    """Ist der Text ein Feldbezeichner der Wissensbasis ("Telefon", "Arbeitgeber", "PLZ", "Geburtsdatum")?"""
    try:
        return any(wissen.index(f"etiketten_{art}").eintrag_fuer(wert) for art in wissen.ETIKETTEN_ARTEN)
    except Exception:
        return False


# Anweisung an den Ausfüllenden in der Zeile unter einem Beruf-Feld ("Kaufmann reicht nicht, bitte genau", "Arzt
# bitte Fachrichtung angeben"; Abnahme 2 A2-08) – nur Wörter einer Aufforderung, kein "nicht" oder "kein" (die stehen
# auch in einem Wert: "Lehrerin, nicht verbeamtet")
_ANWEISUNG_RE = re.compile(r"(?i)(?<![\wäöüß])(?:bitte|angeben|anzugeben|eintragen|einzutragen|ankreuzen|nennen|"
                           r"reicht[ \t]+nicht|z\.[ \t]?b\.|zum[ \t]+beispiel)(?![\wäöüß])")


def _kein_beruf(wert: str) -> bool:
    """Ziffern, Ankreuzwerte, Feldbezeichner, eine Ausfüllanweisung oder mehr als fünf Wörter: kein Beruf."""
    if not wert or not wert[0].isalpha() or any(c.isdigit() for c in wert) or len(wert.split()) > 5:
        return True
    if _ANWEISUNG_RE.search(wert):
        return True
    if wert.casefold() in {"ja", "nein", "keine", "keine angabe", "entfällt", "ohne", "k. a.", "k.a.", "-"}:
        return True
    return _feldbezeichner(wert)


_KOPF_NACHBAR_RE = re.compile(r"(?i)^(?:arbeitgeber(?:in)?|tätigkeit|beruf|branche|stellung|firma|betrieb)\b")
# Nachbarkopf eines Betriebs und Kennzahlen eines Betriebs in der Kopfzeile: eine Betriebstabelle ("Tätigkeit ⇥⇥ Firma
# ⇥⇥ Umsatz") – die Tätigkeit beschreibt dort den Betrieb, nicht den Beruf einer Person (Nachprüfung B/NP-12)
_KOPF_BETRIEB_RE = re.compile(r"(?i)^(?:branche|firma|betrieb|unternehmen)\b")
_BETRIEBS_KENNZAHL_RE = re.compile(
    r"(?i)(?<![\wäöüß])(?:(?:jahres|gesamt|honorar|netto|brutto)?umsatz\w*|umsätze|lohnsumme\w*|gehaltssumme\w*|"
    r"(?:anzahl[ \t]+)?(?:mitarbeiter|beschäftigte)(?:zahl|anzahl)?|betriebsart|betriebsgröße|rechtsform|"
    r"gründungsjahr|filialen|standorte)(?![\wäöüß])")


def _bekannter_beruf(wert: str) -> bool:
    """Ist die ganze Zelle ein Beruf der Wissensbasis ("Spieleentwickler", "Zahnärztin")?"""
    try:
        return any(v.start == 0 and v.ende == len(wert) for v in wissen.index("berufe").finde(wert))
    except Exception:
        return False


def _beruf_spalte(text: str, m):
    """Steht das Beruf-Etikett als ganze Zelle in der Kopfzeile einer Tabelle? In einer Personentabelle ("Name, Vorname
    ⇥⇥ Geb.-Datum ⇥⇥ Beruf ⇥⇥ Eintritt") jede Zelle dieser Spalte in den Zeilen darunter (Befund 87 der Domänen-
    Durchsicht); in einer anderen Kopfzeile – die Nachbarzelle ist selbst ein Feldbezeichner ("Angaben zur Tätigkeit ⇥⇥
    Tätigkeit ⇥⇥ Arbeitgeber") – die Berufe der Wissensbasis darunter (Gegenprüfung LK-15); sonst None. Die
    Nachbarzelle der Kopfzeile ist kein Beruf. In einer Betriebstabelle (Nachbarkopf Firma/Betrieb/Branche und eine
    Kennzahl des Betriebs wie Umsatz in der Kopfzeile) beschreibt die Tätigkeit den Betrieb: keine Stelle."""
    if ":" in text[m.start():m.end()] or "\t" not in text[m.start():m.end()]:
        return None
    za = text.rfind("\n", 0, m.start()) + 1
    ze = text.find("\n", m.start())
    ze = len(text) if ze < 0 else ze
    kopf = _zellen(text[za:ze], za)
    nr = next((i for i, (a, b, _) in enumerate(kopf) if a <= m.start() < b), None)
    if nr is None or len(kopf) < 2 or any(c.isdigit() for c in text[za:ze]):
        return None
    personen = len(kopf) >= 3 and any(_PERSONEN_KOPF_RE.search(t) for _, _, t in kopf)
    if not personen:
        nachbar = kopf[nr + 1][2] if nr + 1 < len(kopf) else ""
        if nachbar and (_KOPF_BETRIEB_RE.match(nachbar) or _BETRIEBS_KENNZAHL_RE.match(nachbar)) \
                and any(_BETRIEBS_KENNZAHL_RE.search(t) for _, _, t in kopf):
            return []                              # Betriebstabelle: "Tätigkeit ⇥⇥ Firma ⇥⇥ Umsatz" – Kopfzeile,
                                                   # aber kein Beruf darunter (und die Nachbarzelle kein Wert)
        if not nachbar or not (_feldbezeichner(nachbar) or _KOPF_NACHBAR_RE.match(nachbar)):
            return None                            # "Beruf ⇥⇥ Schreiner": Etikett und Wert in einer Zeile
    aus = []
    pos = ze + 1
    while pos < len(text):
        ende = text.find("\n", pos)
        ende = len(text) if ende < 0 else ende
        zellen = _zellen(text[pos:ende], pos)
        if len(zellen) != len(kopf):
            break
        a, b, wert = zellen[nr]
        if not _kein_beruf(wert) and (personen or _bekannter_beruf(wert)):
            s0 = a + (len(text[a:b]) - len(text[a:b].lstrip()))
            aus.append((s0, s0 + len(wert)))
        pos = ende + 1
    return aus


def _beruf_unter_etikett(text: str) -> list:
    """Kastenformular: Beruf-Etikett allein auf seiner Zeile, der Wert als ganze Zeile darunter – ein Eintrag der
    Berufsliste oder ein kurzer Wert ohne Ziffern, der kein Feldbezeichner ist ("Arbeitgeber" bei leerem Feld)."""
    aus = []
    for m in _BERUF_KOPF_ZEILE_RE.finditer(text):
        ende = text.find("\n", m.end())
        ende = len(text) if ende < 0 else ende
        wert = text[m.end():ende].strip()
        if "\t" in wert or _kein_beruf(wert):
            continue
        aus.append((m.end(), m.end() + len(wert)))
    return aus


# Beruf-Etikett als ganze Zelle einer Formularzeile ("Telefon ⇥⇥ Beruf (genaue Tätigkeit)")
_BERUF_ZELLE_RE = re.compile(
    r"(?i:(?:ausgeübte[rn]?|derzeitige[rn]?|jetzige[rn]?|erlernte[rn]?|aktuelle[rn]?)[ \t]+)?"
    rf"(?:Beruf{_BERUF_GENITIV}?|Berufsbezeichnung|(?i:Tätigkeit)|berufliche[ \t]+Tätigkeit)"
    r"(?:[ \t]*\([^)\n]{1,30}\))?[ \t]*:?")


def _beruf_in_formularzeile(text: str) -> list:
    """Kastenformular mit mehreren Feldern je Zeile, wie die OCR es vom Scan liest: eine Zeile nur aus
    Feldbezeichnern ("Telefon ⇥⇥ Beruf (genaue Tätigkeit)"), darunter die Werte in gleich vielen Zellen
    ("08631 98765 ⇥⇥ Pflegehelferin"). Die Zelle unter einem Beruf-Etikett ist der Beruf (Befund 87), auch unter
    mehreren ("Beruf des Ehepartners ⇥⇥ Beruf" ⏎ "Erzieherin ⇥⇥ Pflegehelferin"). Ist eine andere Kopfzelle kein
    Feldbezeichner oder passt die Zellenzahl nicht (leeres Feld), gilt nichts. Unter dem mehrdeutigen „Tätigkeit“
    (auch eine Arbeit: „Datum ⇥⇥ Tätigkeit“ ⏎ „12.03.2026 ⇥⇥ Beratung“) muss der Wert einen Beruf der Wissensbasis
    enthalten."""
    aus = []
    zeilen = text.split("\n")
    anfang = 0
    for i, zeile in enumerate(zeilen[:-1]):
        za, anfang = anfang, anfang + len(zeile) + 1
        if "\t" not in zeile or not _BERUF_ZELLE_RE.search(zeile):
            continue
        kopf = _zellen(zeile, za)
        nr = [k for k, (_, _, t) in enumerate(kopf) if _BERUF_ZELLE_RE.fullmatch(t)]
        if len(kopf) < 2 or not nr:
            continue
        if not all(_feldbezeichner(t.rstrip(":").strip()) for k, (_, _, t) in enumerate(kopf) if k not in nr):
            continue
        werte = _zellen(zeilen[i + 1], anfang)
        if len(werte) != len(kopf):
            continue
        for k in nr:
            a, b, wert = werte[k]
            if _kein_beruf(wert):
                continue
            etikett = re.sub(r"\([^)]*\)", "", kopf[k][2])
            if not re.search(r"(?i)beruf", etikett) and not wissen.index("berufe").finde(wert):
                continue                               # "Tätigkeit": nur mit Beruf der Wissensbasis
            s0 = a + (len(text[a:b]) - len(text[a:b].lstrip()))
            aus.append((s0, s0 + len(wert)))
    return aus


def berufe_stellen(text: str) -> list:
    """Berufsangaben hinter einem Etikett ("Beruf: Verkäuferin", "Ausgeübter Beruf:⇥⇥Pharmareferentin") oder
    im Satz ("arbeitet als Zahnärztin", "ist von Beruf Schreiner", "Schreiner von Beruf")."""
    if not text:
        return []
    aus = []
    for m in _BERUF_ETIKETT_RE.finditer(text):
        spalte = _beruf_spalte(text, m)
        if spalte is not None:
            aus += spalte                          # Spaltenkopf einer Tabelle: die Werte stehen darunter
            continue
        w = _beruf_wert(text, m.end(), True)
        if w:
            aus.append(w)
    aus += _beruf_unter_etikett(text)
    aus += _beruf_in_formularzeile(text)
    for m in _BERUF_VOR_RE.finditer(text):
        grundwort = "als" in m.group(0) and bool(_ERWERB_IM_TREFFER_RE.search(m.group(0)))
        w = _beruf_wert(text, m.end(), False, grundwort=grundwort)
        if w and not beruf_satz_ausgenommen(text, w[0], w[1]) and not beruf_des_ohne_person(text, m, w[0]):
            aus.append(w)
    if "als" in text:
        for m in _ALS_RE.finditer(text):
            w = _beruf_wert(text, m.end(), False, grundwort=True)
            if w and _ERWERB_DANACH_RE.match(text, w[1], min(len(text), w[1] + 80)) \
                    and not beruf_satz_ausgenommen(text, w[0], w[1]):
                aus.append(w)
    # Nebensatz mit dem Beruf vor dem Verb ("seit sie Lehrerin ist", "deren Mann Polizist ist", "weil er Beamter war";
    # Abnahme 2 V3), auch als Relativsatz ("Ihr Mann, der Polizist ist, …"; Abnahme 3 AB3-06): Person bzw. Relativ-
    # pronomen, Beruf der Wissensbasis, "ist"/"war"/"wurde" am Ende des Satzteils
    for m in list(_BERUF_NEBENSATZ_RE.finditer(text)) + list(_BERUF_RELATIVSATZ_RE.finditer(text)):
        w = _beruf_wert(text, m.end(), False)
        if w and _NEBENSATZ_VERB_RE.match(text, w[1]) and not beruf_satz_ausgenommen(text, w[0], w[1]) \
                and not (m.group(0).startswith(",") and text[w[0]:w[1]].casefold() in _ROLLE_IM_VORGANG):
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


# Scan mit einer Spalte aus Feldnamen: "6 ⇥⇥ Beruf" allein in seiner Zeile, der Wert rechts daneben in einer eigenen
# Zeile derselben Höhe – so liest die Texterkennung Formulare mit Kästchen um die Werte (Nachprüfung A s01: "6 ⇥⇥ Beruf"
# | "Hufschmiedin selbständig"); auf der Textebene stehen Etikett und Wert in einer Zeile (berufe_stellen)
_BERUF_ALLEIN_RE = re.compile(
    r"(?m)^[ \t]*(?:\d{1,2}(?:\.\d{1,2})*[.)]?[ \t]+)?(?P<etikett>(?i:(?:ausgeübte[rn]?|derzeitige[rn]?|jetzige[rn]?|"
    r"erlernte[rn]?|aktuelle[rn]?)[ \t]+)?(?:Beruf|Berufsbezeichnung|berufliche[ \t]+Tätigkeit))[ \t]*:?[ \t]*$")


# Ausfüllhinweis statt eines Werts rechts neben dem Feldnamen ("Kaufmann reicht nicht, bitte genau", "Angestellte bitte
# Arbeitgeber nennen", "z. B. Dachdecker")
_AUSFUELLHINWEIS_RE = re.compile(r"(?i)(?<![\wäöüß])(?:bitte|nennen|angeben|eintragen|ankreuzen|reicht|genau|"
                                 r"z\.[ \t]?b\.|zum[ \t]+beispiel|beispiel\w{0,2}|etwa|nicht|kein\w{0,2}|ggf\.|"
                                 r"falls|wenn)(?![\wäöüß])")


class _Stelle:
    """Anfang eines Feldnamens für struktur._zelle_rechts_daneben (braucht nur .start)."""
    __slots__ = ("start",)

    def __init__(self, start: int):
        self.start = start


def beruf_rechts_daneben(dok) -> list:
    """(start, ende) im Dokumenttext: ein Beruf der Wissensbasis am Anfang der Zelle rechts neben einem Beruf-Etikett,
    das allein in seiner OCR-Zeile steht (höchstens eine Feldnummer davor). Nur auf gescannten Zeilen; auf der
    Textebene stehen Etikett und Wert in einer Zeile."""
    from . import struktur
    aus = []
    berufe = wissen.index("berufe")
    for nr, seite in enumerate(dok.seiten):
        text = seite.text
        if "eruf" not in text or berufe is None:
            continue
        lg = None
        kandidaten = []
        for m in _BERUF_ALLEIN_RE.finditer(text):
            lg = lg or struktur.lage(seite)
            zelle = lg.zelle_bei(m.start("etikett"))
            if zelle is None or not lg.zeilen_ocr.get(zelle.zeile):
                continue
            z = struktur._zelle_rechts_daneben(lg, _Stelle(m.start("etikett")))
            if z is None or not lg.zeilen_ocr.get(z.zeile):
                continue
            inhalt = text[z.start:z.ende]
            # "Kaufmann reicht nicht, bitte genau" (Abnahme 2 A2-08)
            kandidaten.append((z, inhalt, len(inhalt.split()) > 5 or bool(_AUSFUELLHINWEIS_RE.search(inhalt))))
        # Hinweisspalte: steht in derselben Spalte rechts neben einem anderen Beruf-Feld ein Ausfüllhinweis, sind
        # auch die übrigen Zellen dieser Spalte Hinweise ("Landwirt mit Fläche in Hektar" unter "Arzt bitte
        # Fachrichtung angeben"; ein eingetragener Wert steht näher am Feldnamen, im Kästchen)
        hinweis_x = [z.x0 for z, _, hinweis in kandidaten if hinweis]
        for z, inhalt, hinweis in kandidaten:
            if hinweis or any(abs(z.x0 - x) <= 12 for x in hinweis_x):
                continue
            vorn = len(inhalt) - len(inhalt.lstrip())
            treffer = [v for v in berufe.finde(inhalt) if v.start == vorn]
            if treffer:
                v = max(treffer, key=lambda v: v.ende)
                aus.append((dok.global_(nr, z.start + v.start), dok.global_(nr, z.start + v.ende)))
    return aus


@detektor("wissen.beruf", {"beruf"}, ALLE_PROFILE)
def beruf(dok, kontext):
    """Beruf bei Personen (Etikett oder Satz; auf Scans auch rechts neben dem Feldnamen)."""
    return [Treffer(s, e, "beruf", "wissen.beruf", 0.6) for s, e in berufe_stellen(dok.text) + beruf_rechts_daneben(dok)]


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
             "im", "am", "in", "und", "der", "die", "das",
             # Präpositionen am Feldanfang ("Ort: Zum Stögerbauer", "Ort: Hinter der Scheune") sind kein Ortsname
             "zum", "zur", "beim", "bei", "vor", "hinter", "neben", "unter", "über", "ueber", "an", "auf", "ins",
             "ans", "nach", "aus", "gegenüber", "gegenueber", "zwischen", "von", "mit"}


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
# Länderhinweis im Umkreis einer Anschrift (dieselbe Liste wie die Selbstkontrolle)
_LAND_RE = kennungsformen.LAND_RE
_KENNZEICHEN_ETIKETT_RE = re.compile(
    r"(?<![\wäöüß])(?i:amtl(?:iches|\.)?[ \t]+)?(?i:Kfz-?)?(?i:Kennzeichen|Kennz\.|Nummernschild|Plate)"
    r"(?:[ \t]*\((?P<land>[A-Z]{1,3})\))?(?:[ \t]+des[ \t]+\w+)?[ \t]*(?::[ \t]*|\t+[ \t]*)"
    r"(?P<wert>[A-Z0-9ÄÖÜ]{1,4}(?:[ \t\-·.][A-Z0-9ÄÖÜ]{1,6}){0,3})(?:[ \t]*\((?P<land2>[A-Z]{1,3})\))?(?![\w])")
_DEUTSCHES_KENNZEICHEN_RE = re.compile(r"[A-ZÄÖÜ]{1,3}[-\s][A-Z]{1,2}[ \t]?\d{1,4}[EH]?")


def ausland_stellen(text: str) -> list:
    """Ausländische Anschriften (Straße und PLZ+Ort typischer Nachbarländer) und ausländische Kennzeichen hinter
    einem Etikett ("Kennzeichen: 67-BDK-1", "LU 946067") bzw. mit Länderhinweis im Fließtext ("ein polnischer
    Sattelzug (Zugmaschine WGM 4471K)"). Runde 5: Straßen mit vorangestelltem Straßentyp ("Str. Memorandumului nr.
    27", "bul. Vitosha 15"), sechsstellige PLZ mit Länderhinweis ("400114 Cluj-Napoca, Rumänien") und vierstellige PLZ
    hinter einer Straße beliebiger Form bzw. mit einem Ort der Nachbarländer ("Seestrasse 12, 8002 Zürich", "aus 4040
    Linz") – dieselben Formen wie in der Selbstkontrolle (kennungsformen)."""
    if not text:
        return []
    aus = []
    for m in _AUSLAND_RE.finditer(text):
        wert = m.group(0)
        if re.fullmatch(r"\d{3}[ \t]\d{2}[ \t]+.*", wert) and not _LAND_RE.search(
                text[max(0, m.start() - 120):m.end() + 60]):
            continue                                       # "120 00 Praha" nur mit Länderhinweis
        aus.append((m.start(), m.end()))
    aus += kennungsformen.strassen_vorn(text)
    aus += kennungsformen.plz6_mit_land(text)
    # vierstellige PLZ (A, CH, LI, BE, DK, HU, LU, NO …) hinter einer ausländischen oder deutsch geformten Straße, vor
    # einer Straße in Klammern, mit Länderhinweis oder mit einem Ort der Nachbarländer (kennungsformen.plz4_ausland)
    strassen = list(aus) + muster.finde_strasse_stellen(text)
    for s, e in kennungsformen.plz4_ausland(text, strassen):
        stadt = re.sub(r"^\S*\d{4}[ \t]+", "", text[s:e])
        if stadt.split()[0].casefold() in _KEIN_ORT:
            continue
        aus.append((s, e))
    for m in _KENNZEICHEN_ETIKETT_RE.finditer(text):
        wert = m.group("wert")
        if not any(c.isdigit() for c in wert) or sum(c.isalnum() for c in wert) < 4:
            continue
        if _DEUTSCHES_KENNZEICHEN_RE.fullmatch(wert) and not (m.group("land") or m.group("land2")):
            continue                                       # deutsches Kennzeichen: Kategorie kfz
        sp = kennungsformen.kfz_wert(text, m.start("wert"), m.end("wert"))
        if sp is None:
            continue                                       # "Kennzeichen: 100 EUR": keine Kennzeichenform
        aus.append(sp)
    # ausländisches Kennzeichen im Fließtext direkt hinter einem Fahrzeugwort, mit Länderhinweis im Satz
    aus += [(s, e) for s, e, mit_land in kennungsformen.kennzeichen_im_satz(text) if mit_land]
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
# nur am Wortanfang (sonst auf einer Zeile aus Tausenden "Ab-Ab-…" an jeder Stelle neu, quadratisch – L3)
_ALTER_RE = re.compile(rf"(?<![{_KLEIN}{_GROSS}'’\-])((?:{_WORT_GROSS})(?:[ \t]+{_WORT_GROSS}){{1,3}})[ \t]*"
                       rf"(?:\([ \t]*(\d{{1,3}})"
                       r"(?:[ \t]*(?:J\.|Jahre|Jahren|jährig))?[ \t]*\)|,[ \t]*(\d{1,3})[ \t]+(?:Jahre|J\.)(?:[ \t]+alt)?"
                       r"(?=[,.;\n]))")
_VERTRAGSDATUM_RE = re.compile(
    r"(?i:beginn|ablauf|stand|datum|vom|ab|seit|bis|gültig|fällig|rechnung|zahlung|termin|frist|eingang|"
    r"schreiben|kündigung|unterschrift|antrag|policierung|zugang|versicherungsbeginn|laufzeit|ende|abschluss|"
    r"änderung|erstellt|gedruckt|druck|schadentag|unfalltag|schaden|unfall|geschehen|ausgestellt|erteilt|"
    r"heute|am|den|zum|per|vertrag|police|leistung|auszahlung|überweisung|buchung|stichtag)(?![\wäöüß])")


# Name direkt vor dem Datum: "Vorname Nachname," / "Nachname, Vorname," / "Name (" / "Name *" / "Name ⇥"
# (Familien-/Versichertenkontext, personenkontext.py)
_FAMILIE_NAME_RE = re.compile(
    rf"(?P<name>(?:{_WORT_GROSS},[ \t]*)?{_WORT_GROSS}(?:[ \t]+(?:(?:von|van|de|der|den|zu|vom)[ \t]+)?{_WORT_GROSS})"
    r"{0,2})(?:[ \t]*(?:,|\(|\*)[ \t]*|[ \t]*\t[ \t]*|[ \t]+[-–][ \t]+)$")


def _familien_name(name: str, listeneintrag: bool = False, kinderliste: bool = False) -> bool:
    """Kann `name` ("Liv Ostermeier", "Brenner, Lina", "Ben") eine Person sein: keine Allerwelts-, Etikett- oder
    Rollenwörter, mindestens ein Vor- oder Nachname der Wissensbasis (ein einzelnes Wort: ein eindeutiger Vorname –
    am Anfang eines Listeneintrags unter "Kinder:" auch ein mehrdeutiger: "Max, 05.09.2016", Gegenprüfung LK-13)?"""
    woerter = [w for w in re.split(r"[ \t,]+", name) if w and w[0].isupper()]
    if not woerter or len(woerter) > 3:
        return False
    if kinderliste and len(woerter) == 1 and len(name.split()) == 1:
        # Listeneintrag direkt unter "Kinder:": auch ein Vorname, der ein Monat, ein Ort oder unbekannt ist ("- Juni,
        # 30.06.2022", "Paris, 02.02.2011", "Dakota, 2019"; Nachprüfung NP-06, Ü-NP-17) – nicht "Aschaffenburg,
        # 10.07.2025" über der Unterschrift (personenkontext.kinderliste_direkt)
        return personenkontext.kinderlisten_vorname(woerter[0], wissen)
    for w in woerter:
        if wissen.ist_allerweltswort(w) or personenkontext.FAMILIE_RE.fullmatch(w) or wissen.ist_anrede_titel(w) \
                or wissen.ist_allowlist(w) or wissen.index("etiketten_person").eintrag_fuer(w) is not None:
            return False
    if len(woerter) == 1:
        return wissen.ist_vorname(woerter[0]) and (listeneintrag or not wissen.ist_vorname_mehrdeutig(woerter[0]))
    return any(wissen.ist_vorname(w) or wissen.ist_nachname(w) for w in woerter)


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


def geburt_ohne_stichwort(text: str, alle: bool = False, namen: list | None = None) -> list:
    """[(start, ende, sicherheit)]: Datum direkt hinter einem Namen ("Max Mustermann, 02.09.61") mit plausiblem
    Geburtsjahr (mindestens 10 Jahre her – ein Unterschriftsdatum ist jünger), Alter hinter einem Namen
    ("Anna Berg (54)"); mit alle=True (Schutzstufe „maximal“) jedes Datum, das mindestens 14 Jahre zurückliegt
    und nicht hinter Vertragsvokabular steht. In `namen` (falls übergeben) die Namen der Listeneinträge unter
    "Kinder:" (start, ende) – auch ein Vorname, den sonst keine Regel kennt ("- Juni, 30.06.2022")."""
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
        f = _FAMILIE_NAME_RE.search(davor)
        name_start = (f.start("name") if f else n.start(1) if n else len(davor))
        if personenkontext.behandlungsdatum(davor[:name_start], text, m.end()):
            continue                    # "Dr. Ute Kranzfelder, 03.11.2012: Meniskusoperation" – ein Behandlungsdatum
        if n and jahre >= 10 and _ist_name(n.group(1)) and not _VERTRAGSDATUM_RE.search(davor[n.end(1):]):
            aus.append((m.start(), m.end(), 0.65))
            continue
        # Familien-/Versichertenkontext: das Datum direkt an einem Namen ist ein Geburtsdatum in jedem Alter ("Kind 2:
        # Bastian Leutgeb, 30.06.2018", "Kinder: Ben (02.05.2019)", "Brenner, Lina, 05.05.2019", Kinderliste mit
        # Tabstopps unter "Kinder:") – in einer Liste unter einer Überschrift nur ohne Betrag in der Zeile
        listeneintrag = f is not None and not davor[:f.start("name")].strip(" \t-–•*·")
        kinderliste = listeneintrag and personenkontext.kinderliste_direkt(text, a)
        if f and _familien_name(f.group("name"), listeneintrag, kinderliste) \
                and personenkontext.familien_kontext(text, a, a + f.start("name")):
            gleiche_zeile = personenkontext.familien_rolle_in_zeile(text, a, a + f.start("name"))
            zeile_ende = text.find("\n", m.end())
            zeile = text[a:len(text) if zeile_ende < 0 else zeile_ende]
            if gleiche_zeile or not personenkontext.BETRAG_IN_ZEILE_RE.search(zeile):
                aus.append((m.start(), m.end(), 0.6))
                if namen is not None and kinderliste:
                    namen.append((a + f.start("name"), a + f.start("name") + len(f.group("name").rstrip(" ,\t"))))
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


@detektor("wissen.geburt", {"geburt", "namen"}, ALLE_PROFILE)
def geburt(dok, kontext):
    """Geburtsdaten ohne Stichwort in Personenkontext; in „maximal“ alle plausiblen Geburtsdaten. Dazu die Vornamen
    der Listeneinträge unter "Kinder:" ("- Juni, 30.06.2022")."""
    alle = muster.option(kontext.profil, "alle_geburtsdaten")
    namen: list = []
    aus = [Treffer(s, e, "geburt", "wissen.geburt", si) for s, e, si in geburt_ohne_stichwort(dok.text, alle, namen)]
    return aus + [Treffer(s, e, "namen", "wissen.geburt", 0.6) for s, e in namen]


# ----------------------------------------------------------------------
# klassisch.py hängt für jede Kategorie mit Text-Funktion einen Muster-Detektor ein; für die Wissens-Kategorien
# liefern die Detektoren dieses Moduls die Stellen (sonst würde jeder Fundtext an allen Ganzwort-Stellen gesucht)
# ----------------------------------------------------------------------
for _k in ("beruf", "arbeitgeber", "diagnose", "medikament", "ort", "international"):
    entfernen(f"muster.{_k}")
