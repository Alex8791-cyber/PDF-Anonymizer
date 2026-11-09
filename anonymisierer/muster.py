"""Muster-Erkennung (reguläre Ausdrücke mit Validierung) und Kategorienliste.

Alle Suchfunktionen nehmen den Dokumenttext und liefern die Fundtexte so, wie sie
im Text stehen (die Schwärzung sucht später genau diese Zeichenketten). Die Muster
laufen bewusst nicht über Zeilenumbrüche (Ausnahme: IBAN und PLZ+Ort, dort genau
ein Umbruch), und alle Wiederholungen sind nach oben begrenzt, damit lange Zeilen
nicht zu quadratischer Laufzeit führen.
"""

import datetime
import re
from collections import Counter


def _suche(muster, text, flags=0):
    return [m.group(0) for m in re.finditer(muster, text, flags)]


def _heute():
    return datetime.date.today()


def _eindeutig(treffer):
    """Doppelte Fundtexte entfernen, Reihenfolge beibehalten."""
    gesehen, aus = set(), []
    for t in treffer:
        if t not in gesehen:
            gesehen.add(t)
            aus.append(t)
    return aus


# ----------------------------------------------------------------------
# IBAN
# ----------------------------------------------------------------------
# Länge je Länderkürzel (Zeichen ohne Leerraum). Damit wird ein Kandidat genau
# auf die IBAN gekürzt, statt dass ein Folgewort (BIC, EUR, Jahreszahl) die
# Prüfsumme kippt.
IBAN_LAENGEN = {
    "DE": 22, "AT": 20, "CH": 21, "LI": 21, "LU": 20, "BE": 16, "NL": 18, "FR": 27,
    "IT": 27, "ES": 24, "PT": 25, "PL": 28, "CZ": 24, "SK": 24, "HU": 28, "DK": 18,
    "SE": 24, "NO": 15, "FI": 18, "IE": 22, "GB": 22, "HR": 21, "SI": 19, "RO": 24,
    "BG": 22, "GR": 27, "TR": 26, "EE": 20, "LV": 21, "LT": 20, "MT": 31, "CY": 28,
    "IS": 26, "MC": 27, "SM": 27, "AD": 24, "GI": 23, "FO": 18, "GL": 18, "UA": 29,
    "RS": 22, "BA": 20, "ME": 22, "MK": 19, "AL": 28, "MD": 24, "GE": 22, "IL": 23,
    "SA": 24, "AE": 23, "QA": 29, "KW": 30, "BH": 22, "TN": 24, "BR": 29,
}


def _iban_gueltig(iban: str) -> bool:
    """Prüfziffern-Kontrolle (Modulo 97) — filtert Zufallstreffer heraus."""
    s = re.sub(r"\s", "", iban).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", s):
        return False
    umgestellt = s[4:] + s[:4]
    zahl = "".join(str(int(z, 36)) for z in umgestellt)
    return int(zahl) % 97 == 1


def _iban_pruefen(kandidat: str) -> bool:
    """Prüfsumme — zusätzlich tolerant gegen typische OCR-Verleser (O statt 0, I/l statt 1)
    hinter dem Länderkürzel."""
    if _iban_gueltig(kandidat):
        return True
    kopf, rest = kandidat[:2], kandidat[2:]
    korrigiert = rest.replace("O", "0").replace("o", "0").replace("I", "1").replace("l", "1")
    return korrigiert != rest and _iban_gueltig(kopf + korrigiert)


_IBAN_RE = re.compile(
    r"(?<![A-Za-z0-9])[A-Za-z]{2}\d{2}(?:\s?[A-Za-z0-9]{4}){2,7}(?:\s?[A-Za-z0-9]{1,4})?(?![A-Za-z0-9])")


def finde_iban(text):
    ergebnisse, pos = [], 0
    while True:
        m = _IBAN_RE.search(text, pos)
        if not m:
            break
        kandidat = m.group(0)
        soll = IBAN_LAENGEN.get(kandidat[:2].upper())
        if soll is None:
            if _iban_pruefen(kandidat):
                ergebnisse.append(kandidat)
                pos = m.end()
            else:
                pos = m.start() + 1
            continue
        # Kandidat auf die Soll-Länge des Landes kürzen
        gezaehlt, ende = 0, None
        for i, zeichen in enumerate(kandidat):
            if not zeichen.isspace():
                gezaehlt += 1
            if gezaehlt == soll:
                ende = i + 1
                break
        if ende is not None and _iban_pruefen(kandidat[:ende]):
            ergebnisse.append(kandidat[:ende])
            pos = m.start() + ende          # direkt dahinter weitersuchen (zweite IBAN!)
        else:
            pos = m.start() + 1
    return ergebnisse


# ----------------------------------------------------------------------
# E-Mail
# ----------------------------------------------------------------------
_EMAIL_RE = re.compile(
    r"(?<![\w.\-+%])[\w.\-+%]{1,64}"
    r"(?:@|[ \t]?[\(\[][ \t]?at[ \t]?[\)\]][ \t]?)"            # auch "(at)"-Schreibweise
    r"[\w\-]{1,63}(?:\.[\w\-]{1,63}){0,4}\.[A-Za-z]{2,24}(?![\wäöüß])",
    re.IGNORECASE)


def finde_email(text):
    return [m.group(0) for m in _EMAIL_RE.finditer(text)]


# ----------------------------------------------------------------------
# Telefon
# ----------------------------------------------------------------------
_TEL_RE = re.compile(
    r"(?<![\d\-/])"
    r"(?:\+49[ \t\-/]?(?:\(0\)[ \t]?)?(?:\d{2,5}|\(\d{2,5}\))"   # +49 911 / +49 (0) 171 / +49 (911)
    r"|\((?:0|O)\d{1,5}\)"                                 # (0911)
    r"|(?:0|O(?=\d))(?:\d{1,5}|[ \t]\d{2,3})(?:[ \t]\d{2,3})?)"   # 0911 / 0 89 / 09 11 / 0049 911
    r"[ \t]*(?:[/\-–][ \t]*)?"                             # Trenner
    r"\d{2,}(?:[ \t\-/–]\d{2,})*"                          # Ziffergruppen — kein Zeilenumbruch
    r"(?:[ \t]?-[ \t]?\d{1,3})?"                           # Durchwahl -0 / -12
    r"(?!\d)")


def finde_telefon(text):
    """Deutsche Schreibweisen: 0911 / 123 45 67, (0911) 123456, +49 (0) 171 2345678,
    0171-2345678, 0 89 / 12 34 56 78 … Mindestens 8, höchstens 15 Ziffern."""
    ergebnisse = []
    for m in _TEL_RE.finditer(text):
        ziffern = len(re.sub(r"[^\dO]", "", m.group(0)))
        if 8 <= ziffern <= 15:
            ergebnisse.append(m.group(0))
    return ergebnisse


# ----------------------------------------------------------------------
# Geburtsdatum
# ----------------------------------------------------------------------
_MONATE = {
    "januar": 1, "jan": 1, "februar": 2, "feb": 2, "märz": 3, "maerz": 3, "mär": 3, "mrz": 3,
    "april": 4, "apr": 4, "mai": 5, "juni": 6, "jun": 6, "juli": 7, "jul": 7, "august": 8,
    "aug": 8, "september": 9, "sep": 9, "sept": 9, "oktober": 10, "okt": 10, "november": 11,
    "nov": 11, "dezember": 12, "dez": 12,
}
_MONAT_RE = "(?:" + "|".join(sorted((re.escape(m) for m in _MONATE), key=len, reverse=True)) + r")\.?"

_DATUM_RE = re.compile(
    r"(?<!\d)(?:"
    r"\d{1,2}\.[ \t]?\d{1,2}\.[ \t]?(?:19|20)?\d{2}"                 # 02.09.1983 / 2.9.83
    r"|\d{1,2}\.[ \t]?" + _MONAT_RE + r"[ \t]?(?:19|20)\d{2}"        # 2. September 1983
    r"|(?:19|20)\d{2}-\d{2}-\d{2}"                                    # 1983-09-02
    r"|\d{1,2}/\d{1,2}/(?:19|20)\d{2}"                                # 02/09/1983
    r")(?!\d)", re.IGNORECASE)

_GEB_STICHWORT_RE = re.compile(
    r"(?<![\wäöüßÄÖÜ])(?:geb\.|geb(?=[ \t])|geboren|Geburtsdatum|Geburtsdaten|Geburtstag|"
    r"Geb\.-?[Dd]at(?:um|\.)?|Geburts-?[ \t]?[Dd]atum|GEBURTSDATUM|Geb\.|GEB\.)(?![\wäöüß])"
    r"|\*(?=[ \t]?\d)")
# Vertragsvokabular zwischen Stichwort und Datum -> kein Geburtsdatum
_GEB_STOPP_ZEILE_RE = re.compile(
    r"(?<![\wäöüß])(?:vom|ab|zum|seit|bis|am Ende)(?![\wäöüß])"
    r"|(?i:beginn|ablauf|fällig|gültig|kündig|datum|stand(?![\wäöüß])|rechnung|angebot|zahlung)")
_GEB_STOPP_FOLGE_RE = re.compile(
    r"(?<![\wäöüß])(?:vom|ab|zum|seit|bis|Beginn|Ablauf|Stand|Datum|fällig|gültig|Fälligkeit)(?![\wäöüß])")


def _datum_zerlegen(datum: str):
    """Liefert (Tag, Monat, Jahr) oder None."""
    d = datum.strip()
    m = re.fullmatch(r"(\d{1,2})\.[ \t]?(\d{1,2})\.[ \t]?(\d{2,4})", d)
    if m:
        t, mo, j = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.fullmatch(r"(\d{1,2})\.[ \t]?([A-Za-zäöüÄÖÜ]+)\.?[ \t]?(\d{4})", d)
        if m:
            mo = _MONATE.get(m.group(2).lower())
            if mo is None:
                return None
            t, j = int(m.group(1)), int(m.group(3))
        else:
            m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", d)
            if m:
                j, mo, t = int(m.group(1)), int(m.group(2)), int(m.group(3))
            else:
                m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", d)
                if not m:
                    return None
                t, mo, j = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if j < 100:
        j += 1900 if j > _heute().year % 100 else 2000
    return t, mo, j


def _geburtsdatum_plausibel(datum: str) -> bool:
    """Gültiges Datum, Jahr zwischen heute-110 und heute."""
    teile = _datum_zerlegen(datum)
    if not teile:
        return False
    t, mo, j = teile
    heute = _heute()
    if not (1 <= t <= 31 and 1 <= mo <= 12 and heute.year - 110 <= j <= heute.year):
        return False
    try:
        return datetime.date(j, mo, t) <= heute
    except ValueError:
        return False


def _geburtsdaten_spalten(text):
    """Tabellenlayout: 'Geburtsdatum' als Spaltenkopf, Werte in den Folgezeilen in
    derselben Spalte (z. B. Versicherungsschein mit Personentabelle)."""
    ergebnisse = []
    zeilen = text.split("\n")
    for i, zeile in enumerate(zeilen):
        for m in re.finditer(r"(?<![\wäöüß])(?:Geburtsdatum|Geb\.-?Dat\.?|Geb\.-?Datum)(?![\wäöüß])", zeile):
            if _DATUM_RE.search(zeile, m.end()):
                continue                      # Wert steht in derselben Zeile -> Fenster-Regel
            spalte = m.start()
            leer = 0
            for folge in zeilen[i + 1:i + 60]:
                if not folge.strip():
                    leer += 1
                    if leer > 1:
                        break
                    continue
                daten = [(d.start(), d.group(0)) for d in _DATUM_RE.finditer(folge)]
                if not daten:
                    break
                start, datum = min(daten, key=lambda p: abs(p[0] - spalte))
                if abs(start - spalte) > 12:
                    break
                if _geburtsdatum_plausibel(datum):
                    ergebnisse.append(datum)
    return ergebnisse


def finde_geburtsdaten(text):
    """Datumsangaben bei 'geb.', 'geboren', 'Geburtsdatum', '*' … in einem Fenster von
    bis zu 80 Zeichen (auch über Zeilenumbrüche, z. B. Formularlayouts), außerdem
    Tabellenspalten unter einem Spaltenkopf 'Geburtsdatum'. Formate TT.MM.JJJJ, T.M.JJ,
    TT/MM/JJJJ, JJJJ-MM-TT, 'T. Monat JJJJ'. Datumsangaben hinter Vertragsvokabular
    (vom, ab, seit, Beginn, Ablauf …) werden nicht als Geburtsdatum gewertet."""
    ergebnisse = []
    for m in _GEB_STICHWORT_RE.finditer(text):
        if m.group(0) == "*":
            davor = text[:m.start()].rstrip()
            if davor and davor[-1].isdigit():
                continue                      # "5 * 14.03.2025" ist eine Multiplikation
        fenster = text[m.end():m.end() + 100]
        d = _DATUM_RE.search(fenster)
        if not d:
            continue
        zwischen = fenster[:d.start()]
        if len(zwischen) > 80 or any(c.isdigit() for c in zwischen):
            continue
        gleiche_zeile, _, folgezeilen = zwischen.partition("\n")
        if _GEB_STOPP_ZEILE_RE.search(gleiche_zeile) or _GEB_STOPP_FOLGE_RE.search(folgezeilen):
            continue
        if _geburtsdatum_plausibel(d.group(0)):
            ergebnisse.append(d.group(0))
    ergebnisse.extend(_geburtsdaten_spalten(text))
    return _eindeutig(ergebnisse)


def finde_alle_daten(text):
    """Optional: ALLE Datumsangaben (Vorsicht — auch Vertragsdaten!)."""
    return _suche(r"\b\d{1,2}\.\s?\d{1,2}\.\s?(?:19|20)\d{2}\b", text)


# ----------------------------------------------------------------------
# Straße + Hausnummer
# ----------------------------------------------------------------------
_WORT = r"[A-ZÄÖÜ][\wäöüß]{0,40}(?:\.?-[\wäöüßA-ZÄÖÜ]{1,40}){0,4}\.?"
_SUFFIX_WORT = (r"(?i:Straße|Strasse|Str\.?|Weg|Platz|Allee|Ring|Gasse|Damm|Ufer|Chaussee|"
                r"Promenade|Markt|Steig|Pfad|Stieg)(?![A-Za-zäöüßÄÖÜ])")
_SUFFIX_ANGEHAENGT = (r"(?i:straße|strasse|str\.|str(?![\wäöüß])|weg|platz|gasse|allee|ring|damm|"
                      r"ufer|hof|steig|pfad|chaussee|promenade|markt|stieg)(?![A-Za-zäöüßÄÖÜ])")
_PRAEPOSITION = (r"(?:Am|An der|An dem|Im|In der|In den|Auf dem|Auf der|Auf den|Unter den|Unter der|"
                 r"Hinter dem|Hinter der|Hinter den|Zum|Zur|Bei der|Beim|Vor dem|Vor der|Über den)")
_KEIN_STRASSENWORT = (r"(?!(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|"
                      r"Dezember|Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag|Jahr|Jahre|"
                      r"Jahren|Monat|Monate|Monaten|Tag|Tage|Tagen|Woche|Wochen|Fall|Falle|Schadenfall|"
                      r"Leistungsfall|Todesfall|Versicherungsfall|Rahmen|Übrigen|Beispiel|Wesentlichen|"
                      r"Zeitraum|Durchschnitt|Vergleich|Ergebnis|Alter|Anhang|Anschluss|Auftrag|Namen|"
                      r"Sinne|Zweifel|Laufe|Wert|Höhe|Betrag|Beitrag|Zeitpunkt|Umfang|Falle|Voraus|"
                      r"Zuge|Hinblick|Gegensatz|Vordergrund|Folgenden|Weiteren|Übrigen|Regelfall|"
                      r"Einzelfall|Zusammenhang|Vertrag|Tarif|Antrag|Abschnitt|Absatz|Punkt|Kapitel)(?![\wäöüß]))")
_KEINE_EINHEIT = r"(?![ \t]*(?:Uhr|Jahre?n?|Monate?n?|Tage?n?|Wochen?|Prozent|%|EUR|Euro|€|km|Stunden?|Minuten?|Personen|Kinder|mal|Mio|Mrd|Stück|Jahres)(?![\wäöüß]))"
_HAUSNUMMER = (r"[ \t]*\d{1,4}(?:[ \t]?[a-hA-H](?![\wäöüß]))?"
               r"(?:[ \t]?[-–/][ \t]?\d{1,4}(?:[ \t]?[a-h](?![\wäöüß]))?)?(?![\wäöüß])")

_STRASSE_RE = re.compile(
    r"(?<![\wäöüß])(?:"
    # Am Bahnhof 3, Unter den Linden 1, An der Alten Mühle 4
    + _PRAEPOSITION + r"[ \t]+" + _KEIN_STRASSENWORT + _WORT + r"(?:[ \t]+" + _WORT + r"){0,2}"
    r"[ \t]+\d{1,3}(?![\d])(?:[ \t]?[a-hA-H](?![\wäöüß]))?" + _KEINE_EINHEIT +
    # Berliner Straße 5, Fürther Str. 120, Berliner Platz 1
    r"|" + _WORT + r"(?:[ \t]+" + _WORT + r")?[ \t]+" + _SUFFIX_WORT + _HAUSNUMMER +
    # Hauptstraße 12a, Von-der-Tann-Str. 3, Schillerstr.12, HAUPTSTRASSE 12
    r"|[A-ZÄÖÜ][\wäöüß\-.]{0,60}?" + _SUFFIX_ANGEHAENGT + _HAUSNUMMER +
    # Straße des 17. Juni 135
    r"|Straße des \d{1,2}\. [A-ZÄÖÜ][a-zäöü]+[ \t]+\d{1,4}(?![\wäöüß])"
    # Postfach 10 11 12
    r"|Postfach[ \t]*\d{1,3}(?:[ \t]?\d{2,4}){0,3}(?!\d)"
    r")")


def finde_strasse(text):
    return [m.group(0) for m in _STRASSE_RE.finditer(text)]


# ----------------------------------------------------------------------
# PLZ + Ort
# ----------------------------------------------------------------------
_ORT_STOPP = (r"(?!(?:Tel|Telefon|Telefax|Fax|Mobil|Handy|E-Mail|Mail|Internet|Web|Deutschland|Germany|"
              r"Datum|Den|Am|Im|Vers|Versicherung|Versicherungen|Versicherungsnehmer|Versicherungsschein|"
              r"Herr|Herrn|Frau|Firma|Seite|Postfach|Euro|EUR|EURO|USD|CHF|Kilometer|Stück|Prozent|Punkte|"
              r"Meter|Liter|Jahre|Monate|Tage|Personen|Beginn|Nr|Sehr|Ihr|Ihre|Ihren|Ihrem|Ihrer|Wir|Sie|"
              r"Die|Der|Das|Dem|Des|Ein|Eine|Einen|Einem|Einer|Bitte|Mit|Vielen|Betreff|Betrifft|Sitz|"
              r"Gesamt|Summe|Zahlung|Zahlbar|Kontonummer|Konto|BLZ|IBAN|BIC|Vertrag|Kunden|Kunde|Antrag|"
              r"Rechnung|Vom|Bis|Ab|Zum|Zur|Und|Oder|Für|Bei|Von|Nach|Über|Unter|Zwischen|Beitrag|Stand|"
              r"Vertragsnummer|Kundennummer|Schaden|Leistung|Deckung|Fahrleistung|Laufzeit|Tarif|Police|"
              r"Angebot|Kennzeichen|Baujahr|Erstzulassung|Punkten|Teilnehmer|Mitarbeiter|Kinder|Zeichen|"
              r"Minuten|Stunden|Sekunden|Mio|Mrd|Tsd|Dollar|Franken|Pfund|Prämie|Zinsen|Monat|Jahr|Tag|"
              r"Uhr|Mal|Wert|Wohnfläche|Quadratmeter|Qm|Einwohner|Haushalte|Fahrzeuge|Verträge|Kunden|"
              r"Schäden|Fälle|Stunde|Minute|Zeilen|Seiten|Blatt|Exemplare|Ausfertigungen|Bytes|Kb|Mb|Gb)"
              r"(?![\wäöüß]))"
              r"(?![\wäöüß]{0,40}(?i:straße|strasse|str\.|weg|allee|gasse)(?![\wäöüß]))")
_ORT_WORT = (r"(?:[A-ZÄÖÜ][a-zäöü]{1,2}\.|[A-ZÄÖÜ][\wäöüß]{1,30}(?:-[\wäöüßA-ZÄÖÜ]{1,30}){0,3}"
             r"|\([A-ZÄÖÜ][\wäöüß]{1,30}\)"
             r"|(?:am|an der|bei|im|ob der|a\.[ \t]?d\.|v\.[ \t]?d\.|i\.[ \t]?d\.|b\.|an)[ \t]+[A-ZÄÖÜ][\wäöüß]{1,30})")
_PLZ_ORT_RE = re.compile(
    r"(?<![\d\-/.,])"
    r"(?:(?:D|DE)[-\s]?(?!00)\d{5}|(?:A|CH|L|FL)[-\s]\d{4}|(?!00)\d{5})(?!\d)"
    r"(?:[ \t]+|[ \t]*\n[ \t]*)"                               # höchstens EIN Zeilenumbruch
    + _ORT_STOPP + _ORT_WORT + r"(?:[ \t]+" + _ORT_STOPP + _ORT_WORT + r"){0,3}(?![\wäöüß])")
_PLZ_ETIKETT_DAVOR_RE = re.compile(
    r"(?i:nr\.?|nummer|summe|betrag|wert|eur|€|euro|leistung|deckung|beitrag|fahrleistung|vertrag|"
    r"kunden|konto|zeichen|ref\.?|referenz|position|pos\.?|artikel|menge|anzahl|seite|blatt|"
    r"kennung|id|code|schlüssel|key)[ \t:.]*$")
_ORT_DATUM_DANACH_RE = re.compile(r"^[ \t]*,?[ \t]*(?:den[ \t]+|im[ \t]+|am[ \t]+)?\d{1,2}\.")


def finde_plz_ort(text):
    """PLZ + Ort, auch mehrteilig (Frankfurt am Main, Bad Homburg v. d. Höhe, St. Ingbert,
    Frankfurt (Oder), Neu-Ulm), in Versalien (90402 NÜRNBERG) und mit Länderkürzel
    (D-90402, A-1010, CH-8001). Keine Beträge ('50000 Euro') und keine Nummern vor
    einem Zeilenumbruch ('Vermittler-Nr. 55123 / Stuttgart, 14.03.2025')."""
    ergebnisse = []
    for m in _PLZ_ORT_RE.finditer(text):
        treffer = m.group(0)
        davor = text[max(0, m.start() - 40):m.start()].rsplit("\n", 1)[-1]
        if _PLZ_ETIKETT_DAVOR_RE.search(davor):
            continue
        if "\n" in treffer:
            # Umbruch zwischen PLZ und Ort: Folgezeile darf keine Ort-Datum-Zeile sein
            if _ORT_DATUM_DANACH_RE.match(text[m.end():m.end() + 30]):
                continue
        ergebnisse.append(treffer)
    return ergebnisse


# ----------------------------------------------------------------------
# Vertrags-/Kunden-/Schein-Nummern (Etikett + Wert)
# ----------------------------------------------------------------------
_NR_ETIKETT_RE = re.compile(
    r"(?<![\wäöüß])(?:"
    r"(?:Versicherungsschein|Versicherungs|Versicherten|Versicherung|Vers\.?|VS|Vertrags?|Kunden|Kd\.?|"
    r"Schadens?|Schaden|Antrags?|Policen?|Police|Personal|Mitglieds?|Depot|Konto|Zulagen?|Vorgangs?|"
    r"Vorgang|Referenz|Tagebuch|Bearbeitungs|Schein|Partner|Vermittler|Bestands?|Auftrags?|Kassen|"
    r"Akten|Geschäfts|Fall|Leistungs|Versorgungs|Renten|Riester|Vorsorge|Zugangs|Registrier|"
    r"Bestell|Rechnungs|Beleg|Rechnung)"
    r"[ \t]*[-.]?[ \t]*\n?[ \t]*(?:Nr\.?|Nummer|nummer|No\.?)"
    r"|Aktenzeichen|Referenz|Geschäftszeichen|Gz\.?|Unser Zeichen|Ihr Zeichen|(?-i:Az\.?|AZ|VSNR|VS-Nr\.?)"
    r")(?![\wäöüß])(?:[ \t]+(?:lautet|ist))?",
    re.IGNORECASE)
_NR_TRENNER_RE = re.compile(r"([ \t]*)([:.]?)([ \t]*)")
_NR_TOKEN_SPERRE = {"BLZ", "BIC", "IBAN", "EUR", "USD", "CHF", "DM", "UHR", "KM", "TEL", "FAX", "NR",
                    "BZW", "UND", "AG", "KG", "SE", "EG", "VON", "VOM", "BIS", "AB", "GMBH", "MIO",
                    "MRD", "TSD", "CO", "QM", "ST", "STK", "KW", "PS", "CM", "MM", "KG", "LTR"}
_NR_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-./]*")
_NR_BETRAG_RE = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+,\d{1,2}")
_NR_DATUM_RE = re.compile(r"\d{1,2}\.\d{1,2}\.\d{2,4}|\d{4}-\d{2}-\d{2}")


def _nummern_token(token: str) -> bool:
    """Ein Token gehört zu einer Nummer, wenn es eine Ziffer enthält oder ein kurzes
    Großbuchstaben-Kürzel (LV, KH, AZ, O) ist — nie ein Wort, Betrag oder Datum."""
    if not _NR_TOKEN_RE.fullmatch(token):
        return False
    if token.upper() in _NR_TOKEN_SPERRE:
        return False
    if _NR_BETRAG_RE.fullmatch(token) or _NR_DATUM_RE.fullmatch(token):
        return False
    if any(c.isdigit() for c in token):
        return True
    return len(token) <= 3 and token.isupper()


def _nummer_aus_zeile(zeile: str):
    """Liest vom Zeilenanfang die Nummern-Tokens (bis Wort, Satzzeichen, Doppel-Leerzeichen)."""
    abschnitt = re.split(r"[ \t]{2,}|\t", zeile)[0]
    tokens = []
    for roh in abschnitt.split(" "):
        token = roh.rstrip(".,;:)")
        if not token or not _nummern_token(token):
            break
        tokens.append(token)
        if token != roh:
            break                                 # Satzzeichen beendet den Wert
    while tokens and tokens[-1].isalpha():
        tokens.pop()                              # kein nacktes Kürzel am Ende ("KH" von "KH 2008"? nein: Ziffern fehlen)
    wert = " ".join(tokens).strip("-/. ")
    ziffern = sum(c.isdigit() for c in wert)
    if ziffern < 3 or len(wert) < 4:
        return None
    return wert


def _nummer_in_folgezeilen(text, pos, spalte):
    """Tabellenlayout: Etikett als Spaltenkopf, Wert in einer der nächsten Zeilen —
    entweder eine Zeile, die nur aus der Nummer besteht, oder das Token an derselben Spalte."""
    zeilen = text[pos:].split("\n")[1:5]
    for zeile in zeilen:
        if not zeile.strip():
            continue
        if _NR_DATUM_RE.fullmatch(zeile.strip()):
            continue
        wert = _nummer_aus_zeile(zeile.strip())
        if wert and wert == zeile.strip().rstrip(".,;:"):
            return wert                           # ganze Zeile ist die Nummer
        for m in re.finditer(r"(?<![^\s])[^\s]+(?:[ \t][^\s]+)*?(?=[ \t]{2,}|$)", zeile):
            if abs(m.start() - spalte) <= 6:
                wert = _nummer_aus_zeile(m.group(0))
                if wert:
                    return wert
                break
    return None


def finde_vertragsnummern(text):
    """Nummern hinter verräterischen Etiketten (Versicherungsnummer, Vers.-Nr., VS-Nr.,
    Schein-Nr., Kunden-Nr., Vorgangsnummer, Aktenzeichen, Referenz …). Der Wert endet am
    Zeilenende, bei doppeltem Leerzeichen, Satzzeichen oder dem nächsten Wort; Spaltenköpfe
    ('Vertragsnummer | Beginn | Ablauf') nehmen die Nummer aus der Folgezeile."""
    treffer = []       # (anfang, ende, wert)
    for m in _NR_ETIKETT_RE.finditer(text):
        zeile = text[m.end():].partition("\n")[0]
        trenner = _NR_TRENNER_RE.match(zeile)
        leerraum = trenner.group(1) + trenner.group(3)
        # Spaltenkopf: nichts mehr in der Zeile, oder ohne Doppelpunkt ein breiter Abstand
        rest = zeile[trenner.end():]
        spaltenkopf = (not rest.strip()
                       or (not trenner.group(2) and (len(leerraum) >= 2 or "\t" in leerraum)))
        wert = None if spaltenkopf else _nummer_aus_zeile(rest)
        if wert is None and spaltenkopf:
            zeilenanfang = text.rfind("\n", max(0, m.start() - 400), m.start()) + 1
            wert = _nummer_in_folgezeilen(text, m.start(), m.start() - zeilenanfang)
        if wert:
            anfang = text.find(wert, m.end())
            treffer.append((anfang, anfang + len(wert), wert))
    # Werte, die in einem anderen Wert liegen ("345/24" in "12 AZ 345/24"), entfallen
    ergebnisse = [w for a, e, w in treffer
                  if not any((a2 <= a and e <= e2 and (a2, e2) != (a, e)) for a2, e2, _ in treffer)]
    return _eindeutig(ergebnisse)


# ----------------------------------------------------------------------
# Sozialversicherungs-/Rentenversicherungsnummer
# ----------------------------------------------------------------------
def finde_sv_nummer(text):
    return _suche(r"(?<![\dA-Za-z])\d{2}[ \t]?\d{6}[ \t]?[A-Za-z][ \t]?\d{3}(?![\dA-Za-z])", text)


# ----------------------------------------------------------------------
# Steuer-ID (IdNr) und Steuernummer
# ----------------------------------------------------------------------
def _steuer_id_gueltig(nummer: str) -> bool:
    """Amtliche Prüfziffern-Kontrolle der Steuer-IdNr (§ 139b AO).
    Damit erkennen wir 11-stellige IDs auch OHNE Beschriftung davor,
    ohne zufällige Zahlenkolonnen zu erwischen."""
    z = re.sub(r"\D", "", nummer)
    if len(z) != 11 or z[0] == "0":
        return False
    produkt = 10
    for ziffer in z[:10]:
        summe = (int(ziffer) + produkt) % 10
        if summe == 0:
            summe = 10
        produkt = (2 * summe) % 11
    pruef = 11 - produkt
    if pruef == 10:
        pruef = 0
    return pruef == int(z[10])


def _steuer_id_struktur(nummer: str) -> bool:
    """Amtliche Strukturregel: In den ersten zehn Ziffern kommt genau eine Ziffer doppelt
    oder dreifach vor, alle anderen genau einmal (senkt die Zufallsrate von ~9 % auf ~1 %)."""
    z = re.sub(r"\D", "", nummer)
    mehrfach = [n for n in Counter(z[:10]).values() if n > 1]
    return len(mehrfach) == 1 and mehrfach[0] in (2, 3)


def finde_steuer_id(text):
    ergebnisse = []
    # 1) Mit Beschriftung — auch Formularlayouts wie "Identifikationsnummer (4)"
    #    mit bis zu 12 Zeichen zwischen Etikett und Nummer (inkl. Zeilenumbruch)
    for m in re.finditer(r"(?:Steuer[\s\-]?(?:ID|Id|id|IdNr\.?|Identifikationsnummer)|IdNr\.?|"
                         r"Identifikationsnummer|TIN)"
                         r"[^\d\n]{0,12}?\n?[^\d\n]{0,12}?(\d[\d ]{9,13}\d)(?!\d)", text):
        ergebnisse.append(m.group(1).strip())
    # 2) Ohne Beschriftung: freistehende 11-stellige Nummer mit gültiger Prüfziffer + Struktur
    for m in re.finditer(r"(?<!\d)(\d{11})(?!\d)", text):
        if _steuer_id_gueltig(m.group(1)) and _steuer_id_struktur(m.group(1)):
            ergebnisse.append(m.group(1))
    return _eindeutig(ergebnisse)


def finde_steuernummer(text):
    """Steuernummern 123/4567/8901 bzw. 12/345/67890 (auch ohne Etikett), 13-stellig oder
    mit Leerzeichen nur mit Etikett (Steuernummer, St.-Nr.), außerdem USt-IdNr. DE123456789."""
    ergebnisse = _suche(r"(?<![\d/])\d{2,3}/\d{3,4}/\d{4,5}(?![\d/])", text)
    for m in re.finditer(r"(?i:Steuernummer|Steuer-?Nr\.?|St\.-?Nr\.?|StNr\.?)[ \t]*:?[ \t]*"
                         r"(\d{13}|\d{2,3}[ \t]\d{3,4}[ \t]\d{4,5}|\d{10,11})(?!\d)", text):
        ergebnisse.append(m.group(1))
    for m in re.finditer(r"(?i:USt[-\s]?Id(?:Nr)?\.?|Umsatzsteuer-?(?:Identifikationsnummer|ID|IdNr\.?))"
                         r"[ \t]*:?[ \t]*(DE[ \t]?\d{9})(?!\d)", text):
        ergebnisse.append(m.group(1))
    return ergebnisse


# ----------------------------------------------------------------------
# Weitere Kennnummern
# ----------------------------------------------------------------------
def finde_kindergeldnummer(text):
    """Kindergeldnummern wie 009FK407160 (Format: 3 Ziffern + FK + 6 Ziffern)."""
    return _suche(r"(?<![\dA-Za-z])\d{3}[ \t]?FK[ \t]?\d{6}(?![\dA-Za-z])", text, re.IGNORECASE)


def finde_kv_nummer(text):
    """Krankenversichertennummer: ein Großbuchstabe + 9 Ziffern (A123456789)."""
    return _suche(r"(?<![A-Za-z0-9])[A-Z]\d{9}(?![A-Za-z0-9])", text)


def finde_ausweisnummer(text):
    """Personalausweis-/Reisepass-/Führerscheinnummer — nur mit Etikett."""
    ergebnisse = []
    for m in re.finditer(r"(?i:(?:Personalausweis|Ausweis|Reisepass|Pass|Führerschein|Fuehrerschein|"
                         r"Aufenthaltstitel)[-\s]?(?:Nr\.?|Nummer|nummer|No\.?))[ \t]*:?[ \t]*"
                         r"([A-Z0-9]{6,14})(?![A-Za-z0-9])", text):
        wert = m.group(1)
        if any(c.isdigit() for c in wert):
            ergebnisse.append(wert)
    return ergebnisse


def finde_mandatsreferenz(text):
    """SEPA-Mandatsreferenz — nur mit Etikett."""
    ergebnisse = []
    for m in re.finditer(r"(?i:Mandatsreferenz(?:nummer|-?Nr\.?)?|Mandats-?Nr\.?|SEPA-?Mandat(?:s)?"
                         r"[-\s]?(?:Nr\.?|Nummer|Referenz)?)[ \t]*:?[ \t]*(?:\n[ \t]*)?"
                         r"([A-Za-z0-9][A-Za-z0-9\-./]{3,34})(?![A-Za-z0-9])", text):
        wert = m.group(1).rstrip(".")
        if sum(c.isdigit() for c in wert) >= 2:
            ergebnisse.append(wert)
    return ergebnisse


def finde_fin(text):
    """Fahrzeug-Identnummer (FIN/VIN): 17 Zeichen ohne I, O, Q, mit Buchstaben UND Ziffern."""
    return _suche(r"(?<![A-Za-z0-9])(?=[A-HJ-NPR-Z0-9]{0,16}\d)(?=[A-HJ-NPR-Z0-9]{0,16}[A-HJ-NPR-Z])"
                  r"[A-HJ-NPR-Z0-9]{17}(?![A-Za-z0-9])", text)


_BIC_LAENDER = {"DE", "AT", "CH", "LI", "LU", "FR", "IT", "ES", "NL", "BE", "PL", "GB", "IE", "DK",
                "SE", "NO", "FI", "PT", "CZ", "SK", "HU", "HR", "SI", "RO", "BG", "GR", "TR", "US",
                "CA", "EE", "LV", "LT", "MT", "CY", "IS", "MC", "UA", "RS", "BA", "AU", "JP", "CN"}
_BIC_WERT_RE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{4}([A-Z]{2})[A-Z0-9]{2}(?:[A-Z0-9]{3})?(?![A-Za-z0-9])")


def finde_bic(text):
    """BIC/SWIFT — mit Etikett oder unmittelbar hinter einer IBAN (gleiche/nächste Zeile)."""
    ergebnisse = []
    for m in re.finditer(r"(?i:(?<![\wäöüß])BIC|SWIFT(?:-?(?:Code|BIC))?)[ \t]*:?[ \t]*"
                         r"([A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)(?![A-Za-z0-9])", text):
        ergebnisse.append(m.group(1))
    for iban in finde_iban(text):
        pos = text.find(iban)
        while pos >= 0:
            ende = pos + len(iban)
            fenster = text[ende:ende + 60]
            fenster = fenster.split("\n", 2)
            fenster = "\n".join(fenster[:2])               # gleiche und nächste Zeile
            for b in _BIC_WERT_RE.finditer(fenster):
                if b.group(1) in _BIC_LAENDER:
                    ergebnisse.append(b.group(0))
            pos = text.find(iban, ende)
    return _eindeutig(ergebnisse)


def _luhn_gueltig(nummer: str) -> bool:
    ziffern = [int(c) for c in re.sub(r"\D", "", nummer)]
    summe = 0
    for i, z in enumerate(reversed(ziffern)):
        if i % 2 == 1:
            z *= 2
            if z > 9:
                z -= 9
        summe += z
    return summe % 10 == 0


def finde_kreditkarte(text):
    """Kreditkartennummern (13-19 Ziffern in Gruppen, Luhn-Prüfsumme, Anfangsziffer 3-6)."""
    kandidaten = _suche(r"(?<![\d])(?:[3456]\d{3}(?:[ \-]?\d{4}){2}[ \-]?\d{1,4}|3\d{3}[ \-]?\d{6}[ \-]?\d{5})(?![\d])",
                        text)
    return [k for k in kandidaten if 13 <= len(re.sub(r"\D", "", k)) <= 19 and _luhn_gueltig(k)]


# ----------------------------------------------------------------------
# Kfz-Kennzeichen
# ----------------------------------------------------------------------
# Abkürzungen, die KEINE Unterscheidungszeichen sind, aber in Versicherungstexten
# vor Kürzel + Zahl stehen (AVB KH 2008, DIN A 4, BMW X5 …)
_KFZ_SPERRE = {
    "AVB", "AKB", "AHB", "ABV", "AGB", "ARB", "AUB", "ABB", "ALB", "AVG", "BGB", "DIN", "ISO", "SGB", "VVG",
    "VAG", "HGB", "EWG", "VO", "KFZ", "PKW", "LKW", "SF", "PKV", "GKV", "DRV", "BMW", "VW", "KIA", "BYD",
    "GMC", "RAM", "AMG", "GTI", "TDI", "TSI", "TFSI", "GLC", "GLA", "GLE", "GLS", "CLA", "CLS", "SLK",
    "SUV", "ABS", "ESP", "PDF", "PIN", "TAN", "UID", "IBAN", "BIC", "BLZ", "VHV", "HUK", "DKV", "HDI",
    "WWK", "LVM", "AXA", "TEL", "FAX", "VON", "ZUM", "ZUR", "ICH", "SIE", "WIR", "DU", "EU", "UN", "USA",
    "EDV", "LCD", "LED", "USB", "GPS", "ADAC", "TÜV", "DEKRA", "GDV", "VVW", "BAV", "BU", "KV", "LV", "RV",
    "HUK", "ERGO", "AVB", "AKB", "SFR", "TKS", "KH", "VK", "TK",
}
# Hinweis: KH (Bad Kreuznach), VK (Völklingen), TK (Teltow? nein) stehen oben, weil sie in
# Versicherungstexten praktisch immer Sparten-Kürzel sind (KH = Kfz-Haftpflicht, VK = Vollkasko).
_KFZ_RE = re.compile(
    r"(?<![\wÄÖÜäöü\-])([A-ZÄÖÜ]{1,3})([-\s])([A-Z]{1,2})[ \t]?(\d{1,4})([EH])?"
    r"(?![\wäöüß])(?![ \t]*(?:Uhr|EUR|€|%|Prozent|km|Jahre|Monate|Tage|Punkte)(?![\wäöüß]))")
_KFZ_KLEIN_RE = re.compile(
    r"(?i:Kennzeichen)[ \t]*:?[ \t]*((?-i:[a-zäöü]{1,3}[-\s][a-z]{1,2}[ \t]?\d{1,4}[eh]?))(?![\wäöüß])")


def finde_kennzeichen(text):
    """Deutsche Kfz-Kennzeichen (N-AB 1234, B-MW 1, M-X 1E, NM-XY 123, N AB 1234) —
    nicht aber Normen/Bedingungswerke/Typen (DIN EN 1234, AVB KH 2008, BMW X5, ISO 9001)."""
    ergebnisse = []
    for m in _KFZ_RE.finditer(text):
        kuerzel, trenner, ziffern = m.group(1), m.group(2), m.group(4)
        if kuerzel in _KFZ_SPERRE:
            continue
        # "SGB VI 2023", "VVG AB 2008": Leerzeichen-Trenner + Jahreszahl -> kein Kennzeichen
        if trenner != "-" and len(ziffern) == 4 and ziffern[:2] in ("19", "20"):
            continue
        ergebnisse.append(m.group(0))
    for m in _KFZ_KLEIN_RE.finditer(text):
        ergebnisse.append(m.group(1))
    return ergebnisse


# ----------------------------------------------------------------------
# Kategorienliste
# ----------------------------------------------------------------------
# Reihenfolge = Reihenfolge der Häkchen in der Oberfläche
KATEGORIEN = [
    # (Schlüssel, Anzeigename, Platzhalter, Funktion, standardmäßig an?)
    ("namen",       "Personennamen (KI-Erkennung)",              None,               None,                  True),
    ("iban",        "IBANs",                                     "[IBAN]",           finde_iban,            True),
    ("email",       "E-Mail-Adressen",                           "[E-MAIL]",         finde_email,           True),
    ("telefon",     "Telefonnummern",                            "[TELEFON]",        finde_telefon,         True),
    ("geburt",      "Geburtsdaten",                              "[GEB-DATUM]",      finde_geburtsdaten,    True),
    ("strasse",     "Straße + Hausnummer, Postfach",             "[ADRESSE]",        finde_strasse,         True),
    ("plzort",      "PLZ + Ort",                                 "[PLZ ORT]",        finde_plz_ort,         True),
    ("vertrag",     "Vertrags-/Kunden-/Schein-/Aktenzeichen",    "[VERTRAGS-NR]",    finde_vertragsnummern, True),
    ("svnr",        "Sozialversicherungsnummern",                "[SV-NR]",          finde_sv_nummer,       True),
    ("steuerid",    "Steuer-IDs",                                "[STEUER-ID]",      finde_steuer_id,       True),
    ("steuernr",    "Steuernummern / USt-IdNr.",                 "[STEUER-NR]",      finde_steuernummer,    True),
    ("kvnr",        "Krankenversichertennummern",                "[KV-NR]",          finde_kv_nummer,       True),
    ("kindergeld",  "Kindergeldnummern",                         "[KINDERGELD-NR]",  finde_kindergeldnummer, True),
    ("kfz",         "Kfz-Kennzeichen",                           "[KENNZEICHEN]",    finde_kennzeichen,     True),
    ("fin",         "Fahrzeug-Identnummern (FIN)",               "[FIN]",            finde_fin,             True),
    ("ausweis",     "Ausweis-/Pass-/Führerscheinnummern",        "[AUSWEIS-NR]",     finde_ausweisnummer,   True),
    ("mandat",      "SEPA-Mandatsreferenzen",                    "[MANDATSREFERENZ]", finde_mandatsreferenz, True),
    ("bic",         "BIC (bei IBAN oder Etikett)",               "[BIC]",            finde_bic,             True),
    ("kreditkarte", "Kreditkartennummern",                       "[KREDITKARTE]",    finde_kreditkarte,     True),
    ("datum",       "ALLE Datumsangaben (Vorsicht!)",            "[DATUM]",          finde_alle_daten,      False),
]

# Findet dieselbe Zeichenkette in mehreren Kategorien, gewinnt die spezifischere
# (vorne in dieser Liste): eine SV-Nummer hinter "Versicherungsnummer" bleibt [SV-NR],
# eine Kontonummer mit führender 0 wird nicht zur [TELEFON].
KATEGORIE_PRIORITAET = [
    "iban", "steuerid", "svnr", "kvnr", "kindergeld", "steuernr", "fin", "kreditkarte", "bic",
    "ausweis", "mandat", "email", "geburt", "kfz", "strasse", "plzort", "vertrag", "telefon", "datum",
]
