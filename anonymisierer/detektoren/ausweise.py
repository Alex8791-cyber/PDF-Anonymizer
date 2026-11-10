"""Ausweisdokumente: maschinenlesbare Zone (MRZ) und Führerscheinfelder ohne Feldnamen.

»ausweis.mrz« – maschinenlesbare Zone nach ICAO 9303 (öffentliche Spezifikation, Teile 3 bis 6):

    TD1  3 x 30 Zeichen   Personalausweis, Aufenthaltstitel   Zeile 1 Art/Staat/Nummer, 2 Daten, 3 Name
    TD2  2 x 36 Zeichen   vorläufiger/alter Ausweis, Visa     Zeile 1 Art/Staat/Name, 2 Nummer/Daten
    TD3  2 x 44 Zeichen   Reisepass                           Zeile 1 "P<"/Staat/Name, 2 Nummer/Daten

Felder kleben ohne Trenner aneinander (Nummer + Prüfziffer + Staatsangehörigkeit, Geburtsdatum + Prüfziffer +
Geschlecht + Ablauf …), Füllzeichen ist "<". Erkannt wird zeilenweise auf der Normalform (ohne Leerraum, Lesarten
des Füllzeichens « ‹ ( [ und K-Ketten der OCR als "<", Kleinbuchstaben – in der MRZ nie gültig, auf Scans
verlesene Füllzeichen – ebenfalls). Eine Zone gilt, wenn eine Datenzeile ein Datum JJMMTT mit stimmender
Prüfziffer trägt (Gewichte 7-3-1; Ziffernlesarten O/Q/D=0, I/L=1, Z=2, S=5, G=6, B=8 nur für die Prüfung) oder eine
Namenszeile mit Dokumentkopf ("P<D<<", "IDD<<", "I<UTO") neben einer Datenzeile mit Ziffern steht. Geschwärzt
werden alle persönlichen Felder: die Namen (namen, ohne den Kopf aus Art und Staat), das Zeichenstück mit dem
Geburtsdatum (geburt) und alle übrigen Zeichenstücke der Datenzeilen (ausweis: Nummer, Ablauf, Staatsangehörigkeit,
optionale Daten, Prüfziffern) – nur Füllzeichen und der Dokumentkopf bleiben stehen.

»ausweis.fuehrerschein« – EU-Kartenführerschein (Richtlinie 2006/126/EG, Anhang I): die Werte stehen hinter
Feldnummern statt Feldnamen ("1. MUSTERMANN", "2. ERIKA", "3. 12.08.1983 MÜNCHEN", "4a./4b." Daten, "4c." Behörde,
"4d." Kennziffer, "5." Führerscheinnummer, "8." Wohnort, "9." Klassen). Nur auf Seiten, die sich als Führerschein
ausweisen (Wortlaut der Mitgliedstaaten) und deren Felder die passende Wertform tragen: 3 ein Datum, 1 oder 2 einen
Namen, 4a/4b ein Datum oder 5 eine Nummer – "1. Versicherungsnehmer", "3. Ihr Fahrzeug" in einer Schadenanzeige
(die "Führerschein-Nr." abfragt) bleiben unberührt. Ausstellungs- und Ablaufdatum (4a, 4b) und Klassen (9) bleiben
stehen; 1 und 2 -> namen, 3 -> geburt + ort, 4c -> ort, 4d und 5 -> ausweis, 8 -> strasse/plzort.
"""

from __future__ import annotations

import re

from . import ALLE_PROFILE, Treffer, detektor

QUELLE_MRZ = "ausweis.mrz"
QUELLE_FS = "ausweis.fuehrerschein"

# ----------------------------------------------------------------------
# MRZ
# ----------------------------------------------------------------------
_MRZ_WERT = {**{str(i): i for i in range(10)}, **{chr(65 + i): 10 + i for i in range(26)}, "<": 0}
_ZIFFER_LESART = str.maketrans({"O": "0", "Q": "0", "D": "0", "U": "0", "I": "1", "L": "1", "Z": "2", "S": "5",
                                "G": "6", "B": "8", "T": "7"})
_FUELL_LESARTEN = set("<«‹≤〈([{|")
_KOPF_RE = re.compile(r"[PIACV][A-Z<][A-Z<]{3}")
_K_KETTE_RE = re.compile(r"K{3,}")
# Ausweiskarte (Wortlaut der Vorderseite) und Zugangsnummer: sechs Ziffern als eigene Zeile/Zelle
_KARTE_RE = re.compile(r"(?i)personalausweis|identity\s+card|carte\s+d['’ ]?identit|aufenthaltstitel|"
                       r"residence\s+permit|titre\s+de\s+s[ée]jour")
_CAN_RE = re.compile(r"(?:^|(?<=\t)|(?<=\n))[ ]*(\d{6})[ ]*(?=\t|\n|$)", re.MULTILINE)


def pruefziffer(feld: str) -> int:
    """ICAO-9303-Prüfziffer (Gewichte 7, 3, 1; A=10 … Z=35, '<' = 0)."""
    return sum(_MRZ_WERT.get(c, 0) * (7, 3, 1)[i % 3] for i, c in enumerate(feld)) % 10


def normalform(zeile: str) -> tuple:
    """(Normalform, Abbildung) einer möglichen MRZ-Zeile: Leerraum entfällt, Füllzeichen-Lesarten und
    Kleinbuchstaben werden '<', Großbuchstaben/Ziffern bleiben; sonstige Zeichen werden '<'. None, wenn die Zeile
    Buchstaben mit Diakritika enthält (in der MRZ nie gültig, also Fließtext)."""
    nf, abb = [], []
    for i, c in enumerate(zeile):
        if c in " \t":
            continue
        if "A" <= c <= "Z" or "0" <= c <= "9":
            nf.append(c)
        elif c in _FUELL_LESARTEN or ("a" <= c <= "z"):
            nf.append("<")
        elif c.isalpha():
            return None, None
        else:
            nf.append("<")
        abb.append(i)
    text = "".join(nf)
    text = _K_KETTE_RE.sub(lambda mo: "<" * len(mo.group(0)), text)
    return text, abb


def _mrz_artig(zeile: str, nf: str) -> bool:
    """Grobe Form einer MRZ-Zeile: Datenzeilen ab 20, Namenszeilen (auch von der OCR abgetrennte Stücke) ab
    10 Zeichen; mindestens ein Doppel-Füllzeichen "<<" aus echten Füllzeichen-Lesarten; höchstens ein fremdes
    Satzzeichen (".", ":", "/" … – eine Zeile "STADT KÖLN  23.07.2024" ist keine MRZ); kaum Leerraum."""
    if nf is None or len(nf) > 52:
        return False
    if len(nf) < (20 if any(c.isdigit() for c in nf) else 10):
        return False
    sichtbar = [c for c in zeile if not c.isspace()]
    fremd = sum(1 for c in sichtbar if not (("A" <= c <= "Z") or c.isdigit() or c in _FUELL_LESARTEN
                                            or "a" <= c <= "z"))
    if fremd > 1:
        return False
    fuell = re.sub(r"K{3,}", lambda mo: "<" * len(mo.group(0)),
                   "".join("<" if (c in _FUELL_LESARTEN or "a" <= c <= "z") else c for c in sichtbar))
    if "<<" not in fuell:
        return False
    gross = sum(1 for c in sichtbar if ("A" <= c <= "Z") or c.isdigit() or c in _FUELL_LESARTEN)
    if gross / len(sichtbar) < 0.6:
        return False
    if len(zeile.split()) > 6:
        return False                                  # Fließtext mit vielen Wörtern
    return sum(c.isalnum() for c in nf) >= 2


def _datumsfelder(nf: str) -> list:
    """Positionen gültiger Datumsfelder JJMMTT + Prüfziffer (mit Ziffernlesarten) in Lesereihenfolge."""
    aus = []
    for i in range(0, len(nf) - 6):
        roh = nf[i:i + 7]
        if "<" in roh:
            continue
        z = roh.translate(_ZIFFER_LESART)
        if not z.isdigit():
            continue
        if sum(c.isdigit() for c in roh) < 5:
            continue                                  # überwiegend Buchstaben: kein Datum
        mm, tt = int(z[2:4]), int(z[4:6])
        if not (1 <= mm <= 12 and 1 <= tt <= 31):
            continue
        if pruefziffer(z[:6]) == int(z[6]):
            aus.append(i)
    return aus


def _geburtsfeld(nf: str, felder: list) -> int | None:
    """Welches der gültigen Datumsfelder ist das Geburtsdatum? Nach der Lage in der Zeile: TD1-Zeile 2 (30 Zeichen)
    beginnt damit, in TD2/TD3-Zeile 2 steht es an Stelle 14 (das Ablaufdatum 8 Zeichen dahinter). Liest die OCR das
    Geburtsdatum falsch, bleibt nur das Ablaufdatum gültig – das ist dann KEIN Geburtsdatum (Ablauf "341208" wäre
    sonst der 08.12.1934)."""
    for pos in felder:
        if len(nf) <= 32:
            if pos <= 3:
                return pos
        elif 9 <= pos <= 16:
            return pos
    return None


def _namenszeile(nf: str) -> bool:
    if any(c.isdigit() for c in nf):
        return False
    buchstaben = sum(c.isalpha() for c in nf)
    return buchstaben >= 2 and ("<<" in nf.strip("<") or nf.endswith("<<<"))


def _stuecke(nf: str, ab: int = 0) -> list:
    """Zeichenstücke (Start, Ende) ohne Füllzeichen ab Position `ab` (ein Stück, das den Kopf überlappt, beginnt
    bei `ab`: "P<POLJABLONSKI" -> "JABLONSKI")."""
    return [(ab + m.start(), ab + m.end()) for m in re.finditer(r"[^<]+", nf[ab:])]


# Ausstellende Staaten/Organisationen (ICAO-Codes, Auswahl: EU/EWR, Nachbarn, häufige Herkunftsländer, Sondercodes)
# Staatscodes nach ICAO 9303 / ISO 3166-1 alpha-3 (Auswahl; "D<<" Deutschland, "UTO" der Musterstaat der Norm)
_STAATEN = frozenset("""
D<< AUT BEL BGR HRV CYP CZE DNK EST FIN FRA GRC HUN IRL ITA LVA LTU LUX MLT NLD POL PRT ROU SVK SVN ESP SWE
GBR CHE NOR ISL LIE MCO SMR AND TUR RUS UKR BLR MDA SRB BIH MKD ALB MNE RKS GEO ARM AZE KAZ UZB KGZ TJK TKM
SYR IRQ IRN AFG PAK IND BGD LKA NPL CHN VNM THA PHL IDN MYS KOR JPN USA CAN MEX BRA ARG COL PER CHL VEN CUB
EGY MAR DZA TUN LBY SDN ERI ETH SOM KEN NGA GHA CMR SEN GIN CIV COG COD AGO ZAF TZA UGA ISR LBN JOR SAU ARE
QAT KWT YEM AUS NZL EUE UNO XXA XXB XXC XXX UTO
""".split())


def _kopf_laenge(nf: str, namenszeile: bool) -> int:
    """Länge des Dokumentkopfs am Zeilenanfang (Art + ausstellender Staat, 5 Zeichen), sonst 0. Namenszeilen von
    TD2/TD3 beginnen damit ("P<D<<", "IDD<<", "I<UTO", "P<TUR"); verlangt wird ein bekannter Staatscode – eine von
    der OCR abgeschnittene Namenszeile ("ABLONSKI<<…") oder die TD1-Namenszeile ("PETERSEN<<HANS") hat keinen.
    Klebt ein dreibuchstabiger Code am Nachnamen ("P<TURAKGUEL"), beginnt die Namensstelle schon beim Code (2).
    Datenzeilen: nur Zeile 1 von TD1 ("IDD<<T22…", 30 Zeichen)."""
    if not _KOPF_RE.match(nf) or nf[2:5] not in _STAATEN:
        return 0
    if namenszeile:
        return 2 if nf[4] != "<" else 5
    return 5 if nf[0] in "IAC" and 26 <= len(nf) <= 33 and not any(c.isdigit() for c in nf[:5]) else 0


def mrz_zonen(zeilen: list, angaben: list | None = None) -> list:
    """zeilen: [(start, text)] in Lesereihenfolge. Liefert [(start, ende, kategorie, sicherheit, gruppe)] als
    Stellen im Bezugstext (start + Index in der Zeile). `angaben` (Liste) bekommt je Zone ein Dict mit den
    gelesenen Angaben (nachname, vornamen, nummer, geburt JJMMTT) für den Abgleich mit der Sichtzone."""
    kandidaten = []
    for idx, (start, text) in enumerate(zeilen):
        nf, abb = normalform(text)
        if not _mrz_artig(text, nf):
            continue
        kandidaten.append((idx, start, text, nf, abb))
    if not kandidaten:
        return []
    # benachbarte Kandidaten zu Zonen bündeln (höchstens eine fremde Zeile dazwischen – die OCR zerlegt Zeilen)
    zonen, aktuell = [], []
    for k in kandidaten:
        if aktuell and k[0] - aktuell[-1][0] > 2:
            zonen.append(aktuell)
            aktuell = []
        aktuell.append(k)
    if aktuell:
        zonen.append(aktuell)
    aus = []
    for zone in zonen:
        if not any(len(k[3]) >= 20 for k in zone):
            continue                                  # nur Bruchstücke: keine Zone
        daten = [(k, _datumsfelder(k[3])) for k in zone if not _namenszeile(k[3])]
        namen = [k for k in zone if _namenszeile(k[3])]
        geprueft = any(felder for _, felder in daten)
        kopf = any(_kopf_laenge(k[3], True) for k in namen) or any(_kopf_laenge(k[3], False) for k, _ in daten)
        ziffern = any(sum(c.isdigit() for c in k[3]) >= 6 for k, _ in daten)
        if not (geprueft or (kopf and ziffern and (namen or len(daten) >= 2))):
            continue
        sicherheit = 0.95 if geprueft else 0.85
        gruppe = None
        angabe = {"nachname": [], "vornamen": [], "nummer": None, "geburt": None}
        for k in namen:
            idx, start, text, nf, abb = k
            ab = _kopf_laenge(nf, True)
            stuecke = _stuecke(nf, ab)
            if not stuecke:
                continue
            s, e = stuecke[0][0], stuecke[-1][1]
            kern = nf[5 if ab == 2 else s:e]
            if "<<" in kern and gruppe is None:
                nach, vor = kern.split("<<", 1)
                angabe["nachname"] = [t for t in nach.split("<") if t]
                angabe["vornamen"] = [t for t in vor.split("<") if t]
                gruppe = " ".join(t.capitalize() for t in angabe["vornamen"] + angabe["nachname"]) or None
            aus.append((start + abb[s], start + abb[e - 1] + 1, "namen", sicherheit, gruppe))
        for k, felder in daten:
            idx, start, text, nf, abb = k
            geburt = _geburtsfeld(nf, felder)
            if geburt is not None and angabe["geburt"] is None:
                angabe["geburt"] = nf[geburt:geburt + 6].translate(_ZIFFER_LESART)
            kopf = _kopf_laenge(nf, False)
            if angabe["nummer"] is None and len(nf) >= kopf + 10:
                feld, pruef = nf[kopf:kopf + 9], nf[kopf + 9]
                if (pruef.translate(_ZIFFER_LESART).isdigit() and len(feld.rstrip("<")) >= 6 and "<" not in
                        feld.rstrip("<") and pruefziffer(feld) == int(pruef.translate(_ZIFFER_LESART))):
                    angabe["nummer"] = feld.rstrip("<")
            if nf[:2] in ("ID", "I<", "IR", "IP", "AR", "AC", "C<") or (kopf and nf[0] in "IAC"):
                angabe["karte"] = True
            stuecke = [(s, e) for s, e in _stuecke(nf, kopf) if any(c.isalnum() for c in nf[s:e])]
            if not stuecke:
                continue
            # die ganze Datenzeile ab dem ersten persönlichen Feld (Nummer, Daten, Prüfziffern) als EINE Stelle,
            # das Zeichenstück, das mit dem Geburtsdatum beginnt, zusätzlich als Geburtsdatum
            s0, e0 = stuecke[0][0], stuecke[-1][1]
            aus.append((start + abb[s0], start + abb[e0 - 1] + 1, "ausweis", sicherheit, None))
            for s, e in stuecke:
                if geburt is not None and s == geburt:
                    aus.append((start + abb[s], start + abb[e - 1] + 1, "geburt", sicherheit, None))
        if angaben is not None:
            angaben.append(angabe)
    return aus


# ----------------------------------------------------------------------
# Abgleich mit der Sichtzone: was die MRZ sicher liest, steht auch gedruckt auf Karte/Datenseite
# ----------------------------------------------------------------------
_MONATE = {1: "JAN|JANV|JÄN", 2: "FEB|FEV|FEVR|FÉV|FÉVR", 3: "MAR|MÄR|MRZ|MARS", 4: "APR|AVR", 5: "MAY|MAI",
           6: "JUN|JUIN", 7: "JUL|JUIL", 8: "AUG|AOU|AOÛ|AOUT|AOÛT", 9: "SEP|SEPT", 10: "OCT|OKT", 11: "NOV",
           12: "DEC|DEZ|DÉC"}
_UMSCHRIFT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
_WORT_RE = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?")


def _falten(wort: str, umschrift: bool) -> str:
    import unicodedata
    w = wort.casefold()
    if umschrift:
        w = w.translate(_UMSCHRIFT)
    w = unicodedata.normalize("NFKD", w)
    return "".join(c for c in w if not unicodedata.combining(c)).replace("ł", "l").replace("ø", "o") \
        .replace("ı", "i").replace("đ", "d")


def _hoechstens_ein_fehler(a: str, b: str) -> bool:
    """Gleich bis auf höchstens ein ersetztes, eingefügtes oder fehlendes Zeichen (OCR: "CTVHTMPJIF" = "CTVHTMPJF")."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    kurz, lang = (a, b) if len(a) < len(b) else (b, a)
    for i in range(len(lang)):
        if lang[:i] + lang[i + 1:] == kurz:
            return True
    return False


def _geburtsdatum(jjmmtt: str):
    import datetime
    try:
        jj, mm, tt = int(jjmmtt[0:2]), int(jjmmtt[2:4]), int(jjmmtt[4:6])
        heute = datetime.date.today()
        jahr = 2000 + jj if 2000 + jj <= heute.year else 1900 + jj
        return datetime.date(jahr, mm, tt)
    except (ValueError, TypeError):
        return None


def sichtzone_stellen(text: str, angabe: dict) -> list:
    """Stellen in `text`, an denen die aus der MRZ gelesenen Angaben gedruckt stehen: Dokumentnummer (auch oben rechts
    auf Karte/Datenseite), Geburtsdatum in allen Schreibweisen ("04.07.1950", "04 JUL/JUIL 50", "11 JAN 94") und die
    Namen (Umschrift egal: MRZ "AKGUEL" = "AKGÜL", "JABLONSKI" = "JABŁOŃSKI"). [(start, ende, kategorie)]."""
    aus = []
    nummer = angabe.get("nummer")
    if nummer and len(nummer) >= 6:
        ziel = nummer.translate(_ZIFFER_LESART)
        for mo in re.finditer(r"[A-Za-z0-9|]{%d,%d}" % (len(nummer) - 1, len(nummer) + 1), text):
            if (mo.start() and text[mo.start() - 1].isalnum()) or (mo.end() < len(text) and text[mo.end()].isalnum()):
                continue
            kandidat = mo.group(0).upper().translate(_ZIFFER_LESART)
            if _hoechstens_ein_fehler(kandidat, ziel):
                aus.append((mo.start(), mo.end(), "ausweis"))
    d = _geburtsdatum(angabe.get("geburt") or "")
    if d is not None:
        tt, mm = rf"0?{d.day}", rf"0?{d.month}"
        jj = rf"(?:{d.year}|{d.year % 100:02d})"
        mon = _MONATE[d.month]
        muster = (rf"(?<![\d.]){tt}[.][ ]?{mm}[.][ ]?{jj}(?![\d])|(?<![\d/]){tt}/{mm}/{jj}(?![\d/])|"
                  rf"(?<!\d){d.year}-{d.month:02d}-{d.day:02d}(?!\d)|"
                  rf"(?<![\d.]){tt}[ .]+(?i:{mon})(?:[/ ]+(?i:{mon}))?\.?[ ]+{jj}(?!\d)")
        for mo in re.finditer(muster, text):
            aus.append((mo.start(), mo.end(), "geburt"))
    teile = [t for t in angabe.get("nachname", []) + angabe.get("vornamen", []) if len(t) >= 3]
    if teile:
        gesucht = {t.casefold() for t in teile}
        for mo in _WORT_RE.finditer(text):
            w = mo.group(0)
            if not w[0].isupper() or len(w) < 3:
                continue
            if _falten(w, True) in gesucht or _falten(w, False) in gesucht:
                aus.append((mo.start(), mo.end(), "namen"))
    return aus


@detektor(QUELLE_MRZ, {"namen", "geburt", "ausweis"}, ALLE_PROFILE)
def mrz(dok, kontext):
    """Maschinenlesbare Zone von Ausweis und Pass (ICAO 9303) – Namen, Geburtsdatum, Nummer und alle Daten."""
    treffer = []
    angaben = []
    for nr, seite in enumerate(dok.seiten):
        text = seite.text
        karte = bool(_KARTE_RE.search(text))
        if "<" in text or "«" in text or "KKK" in text or "‹" in text:
            zeilen = [(z.start, text[z.start:z.ende]) for z in seite.zeilen if z.ende > z.start]
            vorher = len(angaben)
            for s, e, kat, si, gruppe in mrz_zonen(zeilen, angaben):
                treffer.append(Treffer(dok.global_(nr, s), dok.global_(nr, e), kat, QUELLE_MRZ, si, gruppe))
            karte = karte or any(a.get("karte") for a in angaben[vorher:])
        if karte:
            # Zugangsnummer (CAN) des Personalausweises: sechs Ziffern allein unten rechts auf der Vorderseite
            for z in seite.zeilen:
                for mo in _CAN_RE.finditer(text, z.start, z.ende):
                    treffer.append(Treffer(dok.global_(nr, mo.start(1)), dok.global_(nr, mo.end(1)), "ausweis",
                                           QUELLE_MRZ + ".zugangsnummer", 0.8))
    for angabe in angaben:
        gruppe = " ".join(t.capitalize() for t in angabe["vornamen"] + angabe["nachname"]) or None
        for s, e, kat in sichtzone_stellen(dok.text, angabe):
            treffer.append(Treffer(s, e, kat, QUELLE_MRZ + ".sichtzone", 0.9, gruppe if kat == "namen" else None))
    return treffer


# ----------------------------------------------------------------------
# EU-Kartenführerschein: Feldnummern statt Feldnamen
# ----------------------------------------------------------------------
_FS_WORT_RE = re.compile(
    r"(?i)f[uü]e?hrerschein|driving\s+licen[cs]e|permis\s+de\s+conduire|prawo\s+jazdy|patente\s+di\s+guida|"
    r"rijbewijs|f[uü]hrerausweis|permiso\s+de\s+conducci[oó]n|carta\s+de\s+condu[cç][aã]o|"
    r"[rř]idi[cč]sk[yý]\s+pr[uů]kaz|voza[cč]ka\s+dozvola|jogos[ií]tv[aá]ny|k[oö]rkort|ajokortti|k[oø]rekort")
# Feldnummer am Zeilen- oder Zellenanfang bzw. hinter breiter Lücke: "1.", "4a.", OCR auch "4a," / "1 ."
_FS_FELD_RE = re.compile(r"(?:^|(?<=\t)|(?<=  ))[ \t]*(1|2|3|4a|4b|4c|4d|5|8|9)[ ]?[.,](?=[ \t]|$)", re.MULTILINE)
_DATUM_RE = re.compile(r"\d{1,2}[./]\d{1,2}[./](?:\d{4}|\d{2})")


_FS_FUNKTIONSWORT = frozenset("für und oder der die das den dem des zum zur im am an auf aus bei mit nach vom von zu "
                               "ihr ihre ihren sie wir unser unsere".split())


def _namensartig(wert: str) -> bool:
    """Wert der Felder 1/2: Wörter mit großem Anfangsbuchstaben, keine Ziffern, kein Funktionswort und nicht nur
    Feldbezeichner oder Allerweltswörter ("1. Versicherungsnehmer", "2. Fahrer zum Unfallzeitpunkt")."""
    woerter = re.findall(r"[^\W\d_][^\W\d_'’\-]*", wert)
    if not woerter or any(c.isdigit() for c in wert) or not woerter[0][0].isupper():
        return False
    if any(w.casefold() in _FS_FUNKTIONSWORT for w in woerter):
        return False
    try:
        from .struktur import ist_etikett_oder_allerwelt
    except Exception:  # pragma: no cover
        return True
    return not all(ist_etikett_oder_allerwelt(w) for w in woerter if len(w) >= 3)


def _feldwert(text: str, marken: list, i: int) -> tuple:
    """(start, ende) des Werts hinter Feldnummer `i` (bis zur nächsten Feldnummer der Zeile bzw. Zeilenende)."""
    _, _, e = marken[i]
    zeilenende = text.find("\n", e)
    if zeilenende < 0:
        zeilenende = len(text)
    ende = zeilenende
    for _, a2, _ in marken[i + 1:]:
        if a2 < zeilenende:
            ende = min(ende, a2)
            break
    s = e
    while s < ende and text[s] in " \t:":
        s += 1
    w = ende
    while w > s and text[w - 1] in " \t,;":
        w -= 1
    return s, w


def fuehrerschein_felder(text: str, mit_wortlaut: bool = True) -> list:
    """[(start, ende, kategorie)] der Werte hinter den Feldnummern eines EU-Führerscheins in `text` (eine Seite).
    mit_wortlaut: die Seite nennt sich Führerschein (sonst nur bei vollständiger Feldfolge).

    Feldnummern allein beweisen nichts – Schadenanzeigen und Anträge sind ebenso nummeriert ("1. Versicherungs-
    nehmer", "3. Ihr Fahrzeug"). Gezählt werden deshalb nur Felder mit passender Wertform: 1/2 namensartig,
    3 mit Datum (Geburtsdatum), 4a/4b mit Datum, 5 eine Nummer mit Ziffern. Nötig sind Feld 3, Feld 1 oder 2
    und Feld 4a/4b oder 5 (ohne Wortlaut alle fünf)."""
    marken = []
    for mo in _FS_FELD_RE.finditer(text):
        marken.append((mo.group(1), mo.start(1), mo.end()))
    nummern = {mk for mk, _, _ in marken}
    if len(nummern & {"1", "2", "3", "5"}) < 3:
        return []
    belegt = set()
    for i, (mk, _, _) in enumerate(marken):
        s, w = _feldwert(text, marken, i)
        wert = text[s:w]
        if mk in ("1", "2") and _namensartig(wert):
            belegt.add(mk)
        elif mk in ("3", "4a", "4b") and (_DATUM_RE.match(wert) or sum(c.isdigit() for c in wert[:12]) >= 6):
            belegt.add("4" if mk != "3" else "3")
        elif mk == "5" and sum(c.isdigit() for c in wert) >= 2 and sum(c.isalnum() for c in wert) >= 5:
            belegt.add("5")
    if "3" not in belegt or not belegt & {"1", "2"} or not belegt & {"4", "5"}:
        return []
    if not mit_wortlaut and not {"1", "2", "3", "4", "5"} <= belegt:
        return []
    aus = []
    for i, (mk, a, e) in enumerate(marken):
        s, w = _feldwert(text, marken, i)
        if w <= s:
            continue
        wert = text[s:w]
        if mk in ("1", "2"):
            if sum(c.isalpha() for c in wert) >= 2 and _namensartig(wert):
                aus.append((s, w, "namen"))
        elif mk == "3":
            d = _DATUM_RE.search(wert)
            if d:
                aus.append((s + d.start(), s + d.end(), "geburt"))
                rest = wert[d.end():]
                r0 = len(rest) - len(rest.lstrip(" \t,"))
                if rest.strip(" \t,"):
                    aus.append((s + d.end() + r0, w, "ort"))
            elif sum(c.isalnum() for c in wert) >= 4:
                aus.append((s, w, "geburt"))
        elif mk == "4c":
            if sum(c.isalpha() for c in wert) >= 3:
                aus.append((s, w, "ort"))
        elif mk in ("4d", "5"):
            if sum(c.isalnum() for c in wert) >= 5:
                aus.append((s, w, "ausweis"))
        elif mk == "8":
            if sum(c.isalnum() for c in wert) >= 4:
                aus.append((s, w, "strasse"))
    return aus


@detektor(QUELLE_FS, {"namen", "geburt", "ausweis", "ort", "strasse"}, ALLE_PROFILE)
def fuehrerschein(dok, kontext):
    """Werte hinter den Feldnummern eines EU-Kartenführerscheins (ohne Feldnamen)."""
    treffer = []
    for nr, seite in enumerate(dok.seiten):
        text = seite.text
        if not text.strip():
            continue
        wortlaut = bool(_FS_WORT_RE.search(text))
        for s, e, kat in fuehrerschein_felder(text, mit_wortlaut=wortlaut):
            treffer.append(Treffer(dok.global_(nr, s), dok.global_(nr, e), kat, QUELLE_FS, 0.85))
    return treffer
