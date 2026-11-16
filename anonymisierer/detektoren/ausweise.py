"""Ausweisdokumente: maschinenlesbare Zone (MRZ) und Führerscheinfelder ohne Feldnamen.

»ausweis.mrz« – maschinenlesbare Zone nach ICAO 9303 (öffentliche Spezifikation, Teile 3 bis 6):

    TD1  3 x 30 Zeichen   Personalausweis, Aufenthaltstitel   Zeile 1 Art/Staat/Nummer, 2 Daten, 3 Name
    TD2  2 x 36 Zeichen   vorläufiger/alter Ausweis, Visa     Zeile 1 Art/Staat/Name, 2 Nummer/Daten
    TD3  2 x 44 Zeichen   Reisepass                           Zeile 1 "P<"/Staat/Name, 2 Nummer/Daten

Felder kleben ohne Trenner aneinander (Nummer + Prüfziffer + Staatsangehörigkeit, Geburtsdatum + Prüfziffer +
Geschlecht + Ablauf …), Füllzeichen ist "<". Erkannt wird zeilenweise auf der Normalform (ohne Leerraum und ohne
Randzeichen der Kartenkante wie "\\." oder ")", Lesarten des Füllzeichens « ‹ ( [ und K-Ketten der OCR als "<",
Kleinbuchstaben – in der MRZ nie gültig, auf Scans verlesene Füllzeichen – ebenfalls, aber nur in Zeilen mit einem
echten Füllzeichen-Lauf). Eine Zone gilt mit Dokumentkopf ("P<D<<", "IDD<<", "I<UTO") und Datum/Ziffern, mit zwei
Zeilen in MRZ-Länge und einem Datum JJMMTT mit stimmender Prüfziffer (Gewichte 7-3-1; Ziffernlesarten O/Q/D=0,
I/L=1, Z=2, S=5, G=6, B=8 nur für die Prüfung), mit einem Datumspaar Geburt/Ablauf (zwei Prüfziffern) – oder als
TD2/TD3-Namenszeile mit Dokumentkopf allein, wenn die OCR die Datenzeile verlor (deren Bruchstücke direkt darunter
werden nach der Lage geschwärzt). Kontakt- und Kontozeilen eines E-Mail-Ausdrucks ("Tel 0221 2311137 Fax …") sind keine
Zone. Geschwärzt werden alle persönlichen Felder: die Namen (namen, ohne den Kopf aus Art und Staat), das
Zeichenstück mit dem Geburtsdatum (geburt) und die Datenzeilen ab ihrem ersten Zeichen (ausweis: Nummer – auch ein
von der OCR verlesener Anfang –, Ablauf, Staatsangehörigkeit, optionale Daten, Prüfziffern) – nur Füllzeichen und der
Dokumentkopf bleiben stehen. Jede Zonenzeile wird geschwärzt, auch wenn ihre OCR-Box höher als eine Zeile ist
(schräger Scan, Box über zwei Zonenzeilen, entartete Box): eine verworfene Zeile bliebe sicher lesbar. Die Sichtzone
(gedruckte Nummer, Geburtsdatum, Namen) wird nur mit bestätigten Angaben gesucht. Die Zugangsnummer (CAN) nur auf
einer Kartenvorderseite (Kartenkopf als eigene Zeile, Zone einer Ausweiskarte) allein in ihrer Zeile oder hinter
"Zugangsnummer"/"CAN".

»ausweis.fuehrerschein« – EU-Kartenführerschein (Richtlinie 2006/126/EG, Anhang I): die Werte stehen hinter
Feldnummern statt Feldnamen ("1. MUSTERMANN", "2. ERIKA", "3. 12.08.1983 MÜNCHEN", "4a./4b." Daten, "4c." Behörde,
"4d." Kennziffer, "5." Führerscheinnummer, "8." Wohnort, "9." Klassen). Nur mit Kartenmerkmalen in einem dichten
Block von Feldnummern: 4a/4b mit Datum, 3 mit plausiblem Geburtsdatum und höchstens dem Geburtsort, 1 oder 2 mit
Namen (kein Versicherer der Erlaubnisliste) – dazu der Kartenkopf als eigene Zeile, die Klassenliste oder die ganze
Feldfolge. "1. Versicherungsnehmer", "3. Ihr Fahrzeug" in einer Schadenanzeige und nummerierte Angebots- oder
Schadenlisten auf Seiten, die "Führerschein" erwähnen, bleiben unberührt. Ausstellungs- und Ablaufdatum (4a, 4b) und
Klassen (9) bleiben stehen; 1 und 2 -> namen, 3 -> geburt + ort, 4c -> ort, 4d und 5 -> ausweis, 8 -> strasse.
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
_KARTEN_ART = frozenset({"ID", "I<", "IR", "IP", "AR", "AC", "C<"})
_K_KETTE_RE = re.compile(r"K{3,}")


def pruefziffer(feld: str) -> int:
    """ICAO-9303-Prüfziffer (Gewichte 7, 3, 1; A=10 … Z=35, '<' = 0)."""
    return sum(_MRZ_WERT.get(c, 0) * (7, 3, 1)[i % 3] for i, c in enumerate(feld)) % 10


# echter Füllzeichen-Lauf: zwei Füllzeichen-Lesarten, davon mindestens eine "<"-artig, oder eine K-Kette der OCR –
# erst dann gelten Kleinbuchstaben als verlesene Füllzeichen ("Tel 0221 2311137 Fax 0221 2311138" ist keine MRZ)
_ECHTE_FUELLUNG_RE = re.compile(r"[<«‹≤〈][<«‹≤〈(\[{|]|[(\[{|][<«‹≤〈]|K{3,}")
_RAND_HOECHSTENS = 3              # Randzeichen der Kartenkante je Zeilenende ("\\", ".", ")", "|")


def _kern_bereich(zeile: str) -> tuple:
    """(a, b) der Zeile ohne Randzeichen: Leerraum und bis zu drei Zeichen je Ende, die weder Buchstabe/Ziffer noch
    "<"-Lesart sind – auf Scans liest die OCR die Kartenkante mit ("\\.C620741523D<<8708265<…", "…<<<<<<<<<<(")."""
    a, b = 0, len(zeile)
    n = 0
    while a < b and (zeile[a].isspace() or (n < _RAND_HOECHSTENS and not zeile[a].isalnum()
                                            and zeile[a] not in "<«‹≤〈")):
        n += not zeile[a].isspace()
        a += 1
    n = 0
    while b > a and (zeile[b - 1].isspace() or (n < _RAND_HOECHSTENS and not zeile[b - 1].isalnum()
                                                and zeile[b - 1] not in "<«‹≤〈")):
        n += not zeile[b - 1].isspace()
        b -= 1
    return a, b


def normalform(zeile: str) -> tuple:
    """(Normalform, Abbildung) einer möglichen MRZ-Zeile: Randzeichen (_kern_bereich) und Leerraum entfallen,
    Füllzeichen-Lesarten werden '<', Kleinbuchstaben – in der MRZ nie gültig, auf Scans verlesene Füllzeichen und
    Anfangszeichen – ebenfalls, Großbuchstaben/Ziffern bleiben; sonstige Zeichen werden '<'. None, wenn die Zeile
    Buchstaben mit Diakritika enthält (in der MRZ nie gültig, also Fließtext)."""
    nf, abb = [], []
    a, b = _kern_bereich(zeile)
    for i in range(a, b):
        c = zeile[i]
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
    10 Zeichen; mindestens ein echter Füllzeichen-Lauf ("<<", "«<", K-Kette – Kleinbuchstaben zählen dafür nicht);
    höchstens ein fremdes Satzzeichen ohne die Randzeichen der Kartenkante ("." , ":", "/" … – eine Zeile "STADT
    KÖLN  23.07.2024" ist keine MRZ); kaum Leerraum."""
    if nf is None or len(nf) > 52:
        return False
    if len(nf) < (20 if any(c.isdigit() for c in nf) else 10):
        return False
    a, b = _kern_bereich(zeile)
    sichtbar = [c for c in zeile[a:b] if not c.isspace()]
    if not sichtbar:
        return False
    fremd = sum(1 for c in sichtbar if not (("A" <= c <= "Z") or c.isdigit() or c in _FUELL_LESARTEN
                                            or "a" <= c <= "z"))
    if fremd > 1:
        return False
    if not _ECHTE_FUELLUNG_RE.search("".join(sichtbar)):
        return False
    gross = sum(1 for c in sichtbar if ("A" <= c <= "Z") or c.isdigit() or c in _FUELL_LESARTEN)
    if gross / len(sichtbar) < 0.6:
        return False
    if len(zeile[a:b].split()) > 6:
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


def _datumspaar(nf: str, felder: list) -> int | None:
    """Geburtsdatum aus dem Paar Geburtsdatum + Geschlecht + Ablaufdatum: zwei gültige Datumsfelder im Abstand 8, an
    der Stelle dazwischen das Geschlecht (M, F, X oder "<") – in TD1-Zeile 2 und TD2/TD3-Zeile 2 gleich, unabhängig
    davon, wie viele Zeichen die OCR am Zeilenanfang verliert oder dazuliest."""
    gesetzt = set(felder)
    for pos in felder:
        if pos + 8 in gesetzt and nf[pos + 7] in "MFX<":
            return pos
    return None


# Länge der Zeilen von TD1, TD2 und TD3 (mit Spielraum für verlorene oder dazugelesene Zeichen der OCR)
_MRZ_LAENGEN = ((27, 33), (33, 39), (41, 47))


def _mrz_laenge(nf: str) -> bool:
    return any(a <= len(nf) <= b for a, b in _MRZ_LAENGEN)


def _geburtsfeld(nf: str, felder: list, format_: str | None = None) -> int | None:
    """Welches der gültigen Datumsfelder ist das Geburtsdatum? Zuerst das Datumspaar (_datumspaar), sonst nach der
    Lage in der Zeile: TD1-Zeile 2 (30 Zeichen) beginnt damit, in TD2/TD3-Zeile 2 steht es an Stelle 14 (das
    Ablaufdatum 8 Zeichen dahinter). `format_` ("td1" bzw. "td23") kommt aus der Zone (Dokumentkopf der Namenszeile,
    Zahl der Zeilen) und geht vor der Zeilenlänge – eine TD2-Zeile, deren Anfang die OCR verlor, ist kürzer. Liest die
    OCR das Geburtsdatum falsch, bleibt nur das Ablaufdatum gültig – das ist dann KEIN Geburtsdatum (Ablauf "341208"
    wäre sonst der 08.12.1934)."""
    paar = _datumspaar(nf, felder)
    if paar is not None:
        return paar
    td1 = format_ == "td1" if format_ else len(nf) <= 32
    for pos in felder:
        if td1:
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


def _nummer_lesen(nf: str, ab: int) -> str | None:
    """Dokumentnummer (9 Zeichen ab `ab`) mit stimmender Prüfziffer dahinter, sonst None."""
    if ab < 0 or len(nf) < ab + 10:
        return None
    feld, pruef = nf[ab:ab + 9], nf[ab + 9]
    kern = feld.rstrip("<")
    if pruef.translate(_ZIFFER_LESART).isdigit() and len(kern) >= 6 and "<" not in kern \
            and pruefziffer(feld) == int(pruef.translate(_ZIFFER_LESART)):
        return kern
    return None


def mrz_zonen(zeilen: list, angaben: list | None = None) -> list:
    """zeilen: [(start, text)] in Lesereihenfolge. Liefert [(start, ende, kategorie, sicherheit, gruppe)] als
    Stellen im Bezugstext (start + Index in der Zeile). `angaben` (Liste) bekommt je Zone ein Dict mit den
    gelesenen Angaben (nachname, vornamen, nummer, geburt JJMMTT; kopf: Dokumentkopf gelesen; karte: Ausweiskarte
    TD1/TD2; namenszeile_ohne_daten: (start, ende) einer TD2/TD3-Namenszeile, deren Datenzeile die OCR nicht
    lieferte) für den Abgleich mit der Sichtzone.

    Eine Zone gilt nur mit einem der Belege: Dokumentkopf mit bekanntem Staat ("IDD<<", "P<D<<", "I<UTO") und einem
    gültigen Datum oder Ziffern; zwei Zeilen in MRZ-Länge (30/36/44 Zeichen, ±3) mit einem gültigen Datum; ein
    Datumspaar Geburt/Ablauf mit zwei stimmenden Prüfziffern; oder die Namenszeile mit Dokumentkopf allein (die OCR
    verliert die Datenzeile eines vorläufigen Ausweises oft ganz). Ein einzelnes Datum mit stimmender Prüfziffer in
    einer Kontakt- oder Kontozeile ("Tel 0221 2311137 Fax 0221 2311138" – jede zehnte Ziffernfolge hat eine
    passende Prüfziffer) ist keine Zone."""
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
        kopf_namen = [k for k in namen if _kopf_laenge(k[3], True)]
        kopf_daten = [k for k, _ in daten if _kopf_laenge(k[3], False)]
        kopf = bool(kopf_namen or kopf_daten)
        geprueft = any(felder for _, felder in daten)
        paar = any(_datumspaar(k[3], felder) is not None for k, felder in daten)
        mrz_zeilen = sum(1 for k in zone if _mrz_laenge(k[3]))
        ziffern = any(sum(c.isdigit() for c in k[3]) >= 6 for k, _ in daten)
        if not ((kopf and (geprueft or (ziffern and (namen or len(daten) >= 2))))
                or (kopf_namen and not daten) or (mrz_zeilen >= 2 and geprueft) or paar):
            continue
        # Format der Zone: TD2/TD3-Namenszeilen beginnen mit dem Dokumentkopf, TD1 hat ihn in Datenzeile 1
        if kopf_namen or any(len(k[3]) >= 34 for k, _ in daten):
            format_ = "td23"
        elif kopf_daten or len(zone) >= 3:
            format_ = "td1"
        else:
            format_ = None
        sicherheit = 0.95 if geprueft else 0.85
        gruppe = None
        # Ausweiskarte (TD1/TD2: Dokumentart I, A, C) – auch wenn die OCR den Staatscode verliest: dreizeilige Zone
        # oder Art "ID"/"I<"/"IR"/"AR"/"C<" am Zeilenanfang einer belegten Zone (ein Pass "P<" hat keine Zugangsnummer)
        angabe = {"nachname": [], "vornamen": [], "nummer": None, "geburt": None, "kopf": kopf,
                  "karte": any(k[3][0] in "IAC" for k in kopf_namen) or bool(kopf_daten) or format_ == "td1"
                  or any(k[3][:2] in _KARTEN_ART for k in zone)}
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
            if ab and not daten:
                angabe["namenszeile_ohne_daten"] = (start + abb[0], start + abb[-1] + 1)
        for k, felder in daten:
            idx, start, text, nf, abb = k
            geburt = _geburtsfeld(nf, felder, format_)
            if geburt is not None and angabe["geburt"] is None:
                angabe["geburt"] = nf[geburt:geburt + 6].translate(_ZIFFER_LESART)
            kopf_hier = _kopf_laenge(nf, False)
            if angabe["nummer"] is None:
                if kopf_hier:
                    angabe["nummer"] = _nummer_lesen(nf, kopf_hier)          # TD1 Zeile 1
                elif format_ != "td1":
                    # TD2/TD3 Zeile 2: Nummer vor Prüfziffer und Staatsangehörigkeit, 13 Stellen vor dem Geburtsdatum
                    # (verliert die OCR Zeichen am Zeilenanfang, verschiebt sich nur der Anfang)
                    p = _datumspaar(nf, felder)
                    angabe["nummer"] = _nummer_lesen(nf, p - 13) if p is not None and p >= 13 else None
                    angabe["nummer"] = angabe["nummer"] or _nummer_lesen(nf, 0)
            stuecke = [(s, e) for s, e in _stuecke(nf, kopf_hier) if any(c.isalnum() for c in nf[s:e])]
            if not stuecke:
                continue
            # die ganze Datenzeile ab dem ersten persönlichen Feld (Nummer, Daten, Prüfziffern) als EINE Stelle –
            # ohne Dokumentkopf ab dem ersten Zeichen der Zeile: was die OCR am Anfang verliest ("ee 10D<<…",
            # "wa1543D"), ist der Anfang der Nummer –, das Zeichenstück, das mit dem Geburtsdatum beginnt, zusätzlich
            # als Geburtsdatum
            s0, e0 = (stuecke[0][0] if kopf_hier else 0), stuecke[-1][1]
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


# Kartenkopf der Vorderseite als eigene Zeile in Versalien ("PERSONALAUSWEIS · IDENTITY CARD · CARTE D'IDENTITÉ",
# "VORLÄUFIGER PERSONALAUSWEIS"; OCR auch "- IDENTITY CARD - CARTE D/IDENTITE") – das Wort im Fließtext oder als Wert
# eines Formulars ("Ausweisart: Personalausweis", "Kopie Ihres Personalausweises") zählt nicht
_KARTEN_WORT = (r"(?:vorl[äa]ufiger\s+)?personalausweis|identity\s+card|carte\s+d['’ /]?\s?identit[ée]|"
                r"aufenthaltstitel|residence\s+permit|titre\s+de\s+s[ée]jour")
_KARTENKOPF_RE = re.compile(r"(?i)^[\W_]{0,3}(?:(?:bundesrepublik\s+deutschland|" + _KARTEN_WORT + r")"
                            r"(?:[\s·•\-–/|,.]+|$))+[\W_]{0,3}$")
_KARTEN_WORT_RE = re.compile(r"(?i)" + _KARTEN_WORT)
# Zugangsnummer mit Feldnamen (Formulare, Abschriften): überall
_CAN_ETIKETT_RE = re.compile(r"(?i:zugangsnummer|card[ \t]+access[ \t]+number|(?-i:\bCAN\b))[ \t]*[:.]?[ \t]*"
                             r"(\d{6})(?![\d])")
# Bruchstücke, die die OCR neben der Zugangsnummer aus Unterschrift und Kartenkante liest ("Ve", "le", ")")
_KARTEN_REST_RE = re.compile(r"[^\w]*\w{0,2}[^\w]*")


def _kartenkopf(seite) -> bool:
    """Steht auf der Seite der Kopf einer Ausweiskarte als eigene Zeile in Versalien?"""
    text = seite.text
    for z in seite.zeilen:
        zeile = text[z.start:z.ende].strip()
        if not zeile or len(zeile) > 90 or zeile.upper() != zeile:
            continue
        if _KARTENKOPF_RE.match(zeile) and _KARTEN_WORT_RE.search(zeile):
            return True
    return False


def _zugangsnummern(seite, karte: bool) -> list:
    """(start, ende) der Zugangsnummer (CAN): sechs Ziffern hinter "Zugangsnummer"/"CAN" – oder, auf einer Seite mit
    Ausweiskarte (Kartenkopf als eigene Zeile, Zone einer Ausweiskarte), sechs Ziffern allein in ihrer Zeile (neben
    höchstens OCR-Bruchstücken aus Unterschrift und Kartenkante): so steht die Nummer unten rechts auf der
    Vorderseite. Steht in der Zeile ein Feldname ("Kilometerstand", "Tarifnummer 310200", "Versicherungssumme"),
    ist es ein anderer Wert."""
    text = seite.text
    aus = [(m.start(1), m.end(1)) for m in _CAN_ETIKETT_RE.finditer(text)]
    if not karte:
        return aus
    for z in seite.zeilen:
        zeile = text[z.start:z.ende]
        for m in re.finditer(r"(?<![\w.,/-])(\d{6})(?![\w.,/-])", zeile):
            rest = zeile[:m.start(1)] + " " + zeile[m.end(1):]
            if all(_KARTEN_REST_RE.fullmatch(teil) for teil in rest.split()):
                stelle = (z.start + m.start(1), z.start + m.end(1))
                if stelle not in aus:
                    aus.append(stelle)
    return aus


def _datenzeile_unter_namenszeile(seite, lg, ns: tuple) -> list:
    """Zeile(n) direkt unter einer TD2/TD3-Namenszeile, deren Datenzeile die OCR nicht als MRZ lieferte: ihre
    Bruchstücke ("J6910900", "10D<<8604…") sind die Datenzeile mit Nummer und Geburtsdatum – nach der LAGE schwärzen
    (mit Ziffern; Fließtext darunter bleibt)."""
    if lg is None:
        return []
    zelle = lg.zelle_bei(ns[0])
    if zelle is None:
        return []
    box = lg.zeilen_box.get(zelle.zeile)
    if box is None:
        return []
    h = max(box[3] - box[1], 4.0)
    text = seite.text
    aus = []
    for zid in lg.zeilen_darunter(zelle.zeile, 2.4 * h)[:2]:
        ws = lg.je_zeile.get(zid, ())
        if not ws:
            continue
        bx = lg.zeilen_box[zid]
        if min(bx[2], box[2]) - max(bx[0], box[0]) <= 0:
            continue                                  # nicht unter der Zone
        a, b = min(w.start for w in ws), max(w.ende for w in ws)
        inhalt = text[a:b]
        if re.search(r"[a-zäöüß]{4,}", inhalt) or sum(c.isdigit() for c in inhalt) < 2 or \
                sum(c.isalnum() for c in inhalt) < 5:
            continue
        aus.append((a, b))
    return aus


@detektor(QUELLE_MRZ, {"namen", "geburt", "ausweis"}, ALLE_PROFILE)
def mrz(dok, kontext):
    """Maschinenlesbare Zone von Ausweis und Pass (ICAO 9303) – Namen, Geburtsdatum, Nummer und alle Daten."""
    treffer = []
    angaben = []
    try:
        from .struktur import lage
    except Exception:  # pragma: no cover
        lage = None
    for nr, seite in enumerate(dok.seiten):
        text = seite.text
        karte = False
        if "<" in text or "«" in text or "KKK" in text or "‹" in text:
            zeilen = [(z.start, text[z.start:z.ende]) for z in seite.zeilen if z.ende > z.start]
            vorher = len(angaben)
            zonen = mrz_zonen(zeilen, angaben)
            lg = lage(seite) if (zonen and lage is not None) else None
            # Jede Zonenzeile wird geschwärzt, auch mit hoher OCR-Box: schräge Scans und Boxen über zwei Zonenzeilen
            # sind die Regel, und auch eine entartete Box überdeckt meist die echte Zeile. Ob die OCR eine Zeile in
            # ein falsches Band setzte, lässt sich hier nicht sicher erkennen (Ursache in ocr.py); eine verworfene
            # Zeile bliebe dagegen sicher lesbar.
            for s, e, kat, si, gruppe in zonen:
                treffer.append(Treffer(dok.global_(nr, s), dok.global_(nr, e), kat, QUELLE_MRZ, si, gruppe))
            for angabe in angaben[vorher:]:
                if angabe.get("namenszeile_ohne_daten"):
                    for s, e in _datenzeile_unter_namenszeile(seite, lg, angabe["namenszeile_ohne_daten"]):
                        treffer.append(Treffer(dok.global_(nr, s), dok.global_(nr, e), "ausweis", QUELLE_MRZ, 0.7))
            karte = any(a.get("karte") for a in angaben[vorher:])
        karte = karte or _kartenkopf(seite)
        for s, e in _zugangsnummern(seite, karte):
            treffer.append(Treffer(dok.global_(nr, s), dok.global_(nr, e), "ausweis", QUELLE_MRZ + ".zugangsnummer",
                                   0.8))
    for angabe in angaben:
        # Sichtzone nur mit bestätigten Angaben (Prüfziffer): Nummer UND Geburtsdatum, oder eines von beiden mit
        # gelesenem Dokumentkopf (verliest die OCR eine Ziffer des Geburtsdatums, sucht ein Pass mit Kopf "P<D<<"
        # und geprüfter Nummer trotzdem die gedruckte Nummer); die Namen der Namenszeile nur mit Dokumentkopf oder
        # Bestätigung. Ein Datum mit zufällig stimmender Prüfziffer allein (Kontaktzeile) sucht nichts.
        kopf = bool(angabe.get("kopf"))
        nummer_ok = bool(angabe["nummer"]) and (kopf or bool(angabe["geburt"]))
        geburt_ok = bool(angabe["geburt"]) and (kopf or bool(angabe["nummer"]))
        if not (nummer_ok or geburt_ok or kopf):
            continue
        angabe = dict(angabe, nummer=angabe["nummer"] if nummer_ok else None,
                      geburt=angabe["geburt"] if geburt_ok else None)
        gruppe = " ".join(t.capitalize() for t in angabe["vornamen"] + angabe["nachname"]) or None
        for s, e, kat in sichtzone_stellen(dok.text, angabe):
            treffer.append(Treffer(s, e, kat, QUELLE_MRZ + ".sichtzone", 0.9, gruppe if kat == "namen" else None))
    return treffer


# ----------------------------------------------------------------------
# EU-Kartenführerschein: Feldnummern statt Feldnamen
# ----------------------------------------------------------------------
_FS_WORT = (r"f[uü]e?hrerschein|driving\s+licen[cs]e|permis\s+de\s+conduire|prawo\s+jazdy|patente\s+di\s+guida|"
            r"rijbewijs|f[uü]hrerausweis|permiso\s+de\s+conducci[oó]n|carta\s+de\s+condu[cç][aã]o|"
            r"[rř]idi[cč]sk[yý]\s+pr[uů]kaz|voza[cč]ka\s+dozvola|jogos[ií]tv[aá]ny|k[oö]rkort|ajokortti|k[oø]rekort")
_FS_WORT_RE = re.compile(r"(?i)" + _FS_WORT)
# Kartenkopf als eigene Zeile: "FÜHRERSCHEIN", OCR "/FÜHRERSCHEIN" oder "(5FÜHRERSCHEIN" (Bruchstücke der Kartenkante
# und des Kartenmusters davor), "PERMIS DE CONDUIRE · FÜHRERSCHEIN", dahinter höchstens das Länderkennzeichen
# ("FÜHRERSCHEIN   D") – nicht "Kopie Führerschein (Vorder- und Rückseite)", nicht "2. Führerschein" (Listennummer
# einer Checkliste), nicht das Wort im Fließtext eines Kfz-Schreibens
_FS_KOPF_RE = re.compile(r"(?i)^(?![ \t]*\d{1,2}[.)][ \t])[\W\d_]{0,3}(?:EU[\s\-]?)?(?:" + _FS_WORT +
                         r")(?:[\s/·|,.\-–]+(?:" + _FS_WORT + r"))*(?:[\s/·|,.\-–]+[A-Z]{1,3})?[^\w]{0,3}$")
# Feldnummer am Zeilen- oder Zellenanfang bzw. hinter breiter Lücke: "1.", "4a.", OCR auch "4a," / "1 ."
_FS_FELD_RE = re.compile(r"(?:^|(?<=\t)|(?<=  ))[ \t]*(1|2|3|4a|4b|4c|4d|5|8|9)[ ]?[.,](?=[ \t]|$)", re.MULTILINE)
_DATUM_RE = re.compile(r"\d{1,2}[./]\d{1,2}[./](?:\d{4}|\d{2})")
# Führerscheinklassen (Feld 9, Rückseite): "AM/B/L", "B/BE/C1/C1E/L" – mit den Lesarten der OCR für die Ziffer 1
# und 2 ("AL"/"AI" für A1, "CIE" für C1E, "AZ" für A2)
_FS_KLASSE = r"(?:AM|A1|AI|Al|AL|A2|AZ|A|B1|BI|Bl|BE|B|C1E|CIE|ClE|C1|CI|Cl|CE|C|D1E|DIE|DlE|D1|DI|Dl|DE|D|L|T|M)"
_FS_KLASSEN_RE = re.compile(r"(?<![\w/])" + _FS_KLASSE + r"(?:[ ]?/[ ]?" + _FS_KLASSE + r"){1,12}(?![\w/])")
# Zeilen ohne Feldnummer zwischen zwei Feldzeilen desselben Blocks (OCR-Bruchstücke, Unterschrift, Feld 7)
_FS_LUECKE_ZEILEN = 3


_FS_FUNKTIONSWORT = frozenset("für und oder der die das den dem des zum zur im am an auf aus bei mit nach vom von zu "
                               "durch über unter vor ab bis ihr ihre ihren ihrer sie wir unser unsere aller alle "
                               "jährlich monatlich optional".split())
# Zusätze im Namen eines Geburtsorts ("FRANKFURT AM MAIN", "HALLE AN DER SAALE", "BAD HOMBURG V. D. HÖHE") – auch
# Funktionswörter, im Ortsnamen aber erlaubt
_FS_ORTSZUSATZ = frozenset("am an der den dem im in ob bei vor unter auf a d v i b u".split())


def _org_wort(wort: str) -> bool:
    """Name einer Organisation der Erlaubnisliste (Versicherer, Prüfdienst), der kein Personenname ist ("Allianz",
    "HUK-COBURG", "DEKRA" – nicht "Nürnberger", das auch ein Nachname ist)."""
    try:
        from .. import wissen
    except Exception:  # pragma: no cover
        return False
    try:
        return wissen.ist_allowlist(wort) and not (wissen.ist_nachname(wort) or wissen.ist_vorname(wort))
    except Exception:
        return False


def _namensartig(wert: str) -> bool:
    """Wert der Felder 1/2: Wörter mit großem Anfangsbuchstaben, keine Ziffern, kein Funktionswort, kein Versicherer
    oder Prüfdienst der Erlaubnisliste ("1. Allianz Kfz Komfort", "2. Gutachten DEKRA Niederlassung") und nicht nur
    Feldbezeichner oder Allerweltswörter ("1. Versicherungsnehmer", "2. Fahrer zum Unfallzeitpunkt")."""
    woerter = re.findall(r"[^\W\d_][^\W\d_'’\-]*", wert)
    if not woerter or any(c.isdigit() for c in wert) or not woerter[0][0].isupper():
        return False
    if any(w.casefold() in _FS_FUNKTIONSWORT for w in woerter):
        return False
    if _org_wort(wert) or any(_org_wort(w) for w in re.split(r"[ \t]+", wert.strip()) if len(w) >= 3):
        return False
    try:
        from .struktur import ist_etikett_oder_allerwelt
    except Exception:  # pragma: no cover
        return True
    return not all(ist_etikett_oder_allerwelt(w) for w in woerter if len(w) >= 3)


def _datum_lesen(text: str):
    """Datum TT.MM.JJJJ bzw. TT.MM.JJ als datetime.date (zweistellige Jahre: bis zum laufenden Jahr 20JJ) oder None."""
    import datetime
    m = re.match(r"(\d{1,2})[./](\d{1,2})[./](\d{4}|\d{2})$", text)
    if not m:
        return None
    tt, mm, jj = int(m.group(1)), int(m.group(2)), int(m.group(3))
    heute = datetime.date.today()
    if jj < 100:
        jj += 2000 if 2000 + jj <= heute.year else 1900
    try:
        return datetime.date(jj, mm, tt)
    except ValueError:
        return None


def _geburt_und_ort(wert: str):
    """Feld 3: Geburtsdatum (plausibel: 14 bis 110 Jahre) und dahinter höchstens der Geburtsort (bis zu vier Wörter
    ohne Ziffern und Funktionswörter, Ortszusätze wie "am", "an der", "v. d." ausgenommen) – "3. 01.04.2025 Beginn
    aller Angebote" ist kein Feld 3, "3. 12.08.1983 FRANKFURT AM MAIN" schon. Liefert (Datum-Match, Ortsteil-Start,
    Ortsteil-Ende) relativ zu `wert` oder None."""
    import datetime
    d = _DATUM_RE.match(wert)
    if d is None:
        return None
    datum = _datum_lesen(d.group(0))
    if datum is None:
        return None
    alter = (datetime.date.today() - datum).days / 365.25
    if not 14 <= alter <= 110:
        return None
    rest = wert[d.end():]
    a = len(rest) - len(rest.lstrip(" \t,"))
    ort = rest.strip(" \t,")
    woerter = [w for w in re.findall(r"[^\W\d_][^\W\d_'’.\-]*", ort)
               if w.rstrip(".").casefold() not in _FS_ORTSZUSATZ and len(w) >= 2]
    if any(c.isdigit() for c in ort) or len(woerter) > 4 or \
            any(w.casefold() in _FS_FUNKTIONSWORT for w in woerter):
        return None
    return d, d.end() + a, d.end() + a + len(ort)


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


def _feldbloecke(text: str, marken: list) -> list:
    """Feldnummern zu Blöcken: aufeinanderfolgende Zeilen mit Feldnummern, höchstens _FS_LUECKE_ZEILEN Zeilen ohne
    Feldnummer dazwischen (eine Karte); jede Liste enthält die Indizes in `marken`."""
    bloecke, aktuell, letzte_zeile = [], [], None
    for i, (_, a, _) in enumerate(marken):
        zeile = text.count("\n", 0, a)
        if aktuell and zeile - letzte_zeile > _FS_LUECKE_ZEILEN + 1:
            bloecke.append(aktuell)
            aktuell = []
        aktuell.append(i)
        letzte_zeile = zeile
    if aktuell:
        bloecke.append(aktuell)
    return bloecke


def _kartenmerkmale(text: str) -> tuple:
    """(Kartenkopf als eigene Zeile, Klassenliste) der Seite."""
    kopf = any(_FS_KOPF_RE.match(z.strip()) for z in text.split("\n") if z.strip() and len(z.strip()) <= 70)
    klassen = bool(_FS_KLASSEN_RE.search(text))
    return kopf, klassen


def fuehrerschein_felder(text: str, mit_wortlaut: bool | None = None) -> list:
    """[(start, ende, kategorie)] der Werte hinter den Feldnummern eines EU-Führerscheins in `text` (eine Seite).
    mit_wortlaut: None = aus dem Text bestimmen (Kartenkopf "FÜHRERSCHEIN" als eigene Zeile), True/False erzwingt es.

    Feldnummern allein beweisen nichts – Schadenanzeigen, Angebotsvergleiche und Schadenabläufe sind ebenso
    nummeriert ("1. Versicherungsnehmer", "3. 01.04.2025 Beginn aller Angebote"), und das Wort "Führerschein" steht in
    jedem Kfz-Schreiben. Verlangt werden deshalb Kartenmerkmale in EINEM dichten Block von Feldnummern: Feld 4a oder
    4b mit Datum (verliest die OCR beide, genügt neben Kartenkopf oder Klassenliste die Nummer in Feld 5), Feld 3 mit
    plausiblem Geburtsdatum und höchstens dem Geburtsort, Feld 1 oder 2 mit Namen (kein Versicherer der
    Erlaubnisliste) – und dazu der Kartenkopf als eigene Zeile, die Klassenliste (Feld 9: "AM/B/L") oder die
    vollständige Feldfolge 1 bis 5. Geschwärzt wird nur in diesem Block."""
    marken = [(mo.group(1), mo.start(1), mo.end()) for mo in _FS_FELD_RE.finditer(text)]
    if len({mk for mk, _, _ in marken} & {"1", "2", "3", "5"}) < 3:
        return []
    kopf, klassen = _kartenmerkmale(text)
    if mit_wortlaut is not None:
        kopf = mit_wortlaut
    aus = []
    for block in _feldbloecke(text, marken):
        belegt = set()
        for i in block:
            mk = marken[i][0]
            s, w = _feldwert(text, marken, i)
            wert = text[s:w]
            if mk in ("1", "2") and _namensartig(wert):
                belegt.add(mk)
            elif mk == "3" and _geburt_und_ort(wert):
                belegt.add("3")
            elif mk in ("4a", "4b") and (_DATUM_RE.match(wert) or sum(c.isdigit() for c in wert[:12]) >= 6):
                belegt.add("4")
            elif mk == "5" and sum(c.isdigit() for c in wert) >= 2 and sum(c.isalnum() for c in wert) >= 5:
                belegt.add("5")
        # Ausstellungs-/Ablaufdatum (4a/4b) – oder, wenn die OCR beide verliest ("42.01.02.22" statt "4a. 01.02.22"),
        # die Führerscheinnummer (5) neben Kartenkopf oder Klassenliste
        if "3" not in belegt or not belegt & {"1", "2"} or \
                not ("4" in belegt or ("5" in belegt and (kopf or klassen))):
            continue
        if not (kopf or klassen or {"1", "2", "3", "4", "5"} <= belegt):
            continue
        for i in block:
            mk = marken[i][0]
            s, w = _feldwert(text, marken, i)
            if w <= s:
                continue
            wert = text[s:w]
            if mk in ("1", "2"):
                if sum(c.isalpha() for c in wert) >= 2 and _namensartig(wert):
                    aus.append((s, w, "namen"))
            elif mk == "3":
                g = _geburt_und_ort(wert)
                if g:
                    d, os_, oe = g
                    aus.append((s + d.start(), s + d.end(), "geburt"))
                    if oe > os_:
                        aus.append((s + os_, s + oe, "ort"))
            elif mk == "4c":
                if sum(c.isalpha() for c in wert) >= 3:
                    aus.append((s, w, "ort"))
            elif mk in ("4d", "5"):
                if sum(c.isalnum() for c in wert) >= 5 and sum(c.isdigit() for c in wert) >= 2:
                    aus.append((s, w, "ausweis"))
            elif mk == "8":
                # Anschrift: mit Hausnummer oder PLZ – oder, wenn die OCR die Zeile teilt ("8. FELDKIRCHENER"), ein
                # großgeschriebener Straßenname ohne Funktionswort (nicht "8. Werkstattbindung optional")
                woerter8 = re.findall(r"[^\W\d_]+", wert)
                if sum(c.isalnum() for c in wert) >= 4 and (any(c.isdigit() for c in wert) or (
                        woerter8 and woerter8[0][0].isupper()
                        and not any(x.casefold() in _FS_FUNKTIONSWORT for x in woerter8))):
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
        for s, e, kat in fuehrerschein_felder(text):
            treffer.append(Treffer(dok.global_(nr, s), dok.global_(nr, e), kat, QUELLE_FS, 0.85))
    return treffer
