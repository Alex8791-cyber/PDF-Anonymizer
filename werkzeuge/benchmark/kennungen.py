"""Synthetische Kennungen mit gültigen Prüfziffern (wo es Prüfziffern gibt).

Alle Werte werden aus einem übergebenen random.Random erzeugt (deterministisch je Seed) und
sind frei erfunden. Gültig heißt: Die Prüfsumme stimmt (IBAN Mod-97, Steuer-ID nach § 139b AO,
SV-Nummer, KVNR, Ausweis-Seriennummer ICAO 9303, Kreditkarte Luhn, USt-IdNr., FIN-Prüfziffer) –
so, wie echte Nummern in Dokumenten stehen. Steuernummern und Führerscheinnummern haben je
Bundesland bzw. Behörde eigene Prüfverfahren; dort stimmt nur das Format (im Bericht vermerkt).
"""

import datetime

# ----------------------------------------------------------------------
# IBAN / BIC
# ----------------------------------------------------------------------
IBAN_LAENGE = {"DE": 22, "AT": 20, "CH": 21, "NL": 18, "FR": 27, "IT": 27, "ES": 24, "PL": 28,
               "BE": 16, "LU": 20}


def _ziffern(rng, n: int) -> str:
    return "".join(rng.choice("0123456789") for _ in range(n))


def _iban_pruefziffer(land: str, bban: str) -> str:
    umgestellt = bban + land + "00"
    zahl = int("".join(str(int(c, 36)) for c in umgestellt))
    return f"{98 - zahl % 97:02d}"


def iban_gueltig(iban: str) -> bool:
    s = iban.replace(" ", "").upper()
    if len(s) < 15:
        return False
    zahl = int("".join(str(int(c, 36)) for c in s[4:] + s[:4]))
    return zahl % 97 == 1


def _rib_schluessel(bank: str, schalter: str, konto: str) -> str:
    """Französischer RIB-Schlüssel (Konto nur aus Ziffern)."""
    wert = 89 * int(bank) + 15 * int(schalter) + 3 * int(konto)
    return f"{97 - wert % 97:02d}"


def _cin(abi: str, cab: str, konto: str) -> str:
    """Italienischer CIN-Kontrollbuchstabe."""
    ungerade = [1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18, 20, 11, 3, 6, 8, 12, 14, 16, 10, 22, 25, 24, 23]
    zeichen = abi + cab + konto
    summe = 0
    for i, c in enumerate(zeichen):
        wert = int(c) if c.isdigit() else ord(c.upper()) - 65
        summe += ungerade[wert] if i % 2 == 0 else wert
    return chr(65 + summe % 26)


def _es_dc(bank: str, filiale: str, konto: str) -> str:
    gewichte = [1, 2, 4, 8, 5, 10, 9, 7, 3, 6]

    def ziffer(s):
        z = 11 - sum(int(c) * g for c, g in zip(s.rjust(10, "0"), gewichte)) % 11
        return {10: 1, 11: 0}.get(z, z)
    return f"{ziffer('00' + bank + filiale)}{ziffer(konto)}"


def _pl_bank(rng) -> str:
    sieben = _ziffern(rng, 7)
    gewichte = [3, 9, 7, 1, 3, 9, 7]
    pruef = (10 - sum(int(c) * g for c, g in zip(sieben, gewichte)) % 10) % 10
    return sieben + str(pruef)


def iban(rng, land: str = "DE") -> str:
    """IBAN (ohne Leerzeichen) mit gültiger Prüfsumme und landestypischem Aufbau."""
    if land == "DE":
        bban = _ziffern(rng, 8) + _ziffern(rng, 10)
    elif land == "AT":
        bban = _ziffern(rng, 5) + _ziffern(rng, 11)
    elif land == "CH":
        bban = "00" + _ziffern(rng, 3) + _ziffern(rng, 12)
    elif land == "NL":
        bban = "".join(rng.choice("ABCDEFGHJKLMNPRSTUVWXZ") for _ in range(4)) + _ziffern(rng, 10)
    elif land == "FR":
        bank, schalter, konto = _ziffern(rng, 5), _ziffern(rng, 5), _ziffern(rng, 11)
        bban = bank + schalter + konto + _rib_schluessel(bank, schalter, konto)
    elif land == "IT":
        abi, cab, konto = _ziffern(rng, 5), _ziffern(rng, 5), _ziffern(rng, 12)
        bban = _cin(abi, cab, konto) + abi + cab + konto
    elif land == "ES":
        bank, filiale, konto = _ziffern(rng, 4), _ziffern(rng, 4), _ziffern(rng, 10)
        bban = bank + filiale + _es_dc(bank, filiale, konto) + konto
    elif land == "PL":
        bban = _pl_bank(rng) + _ziffern(rng, 16)
    elif land == "BE":
        basis = _ziffern(rng, 10)
        pruef = int(basis) % 97 or 97
        bban = basis + f"{pruef:02d}"
    elif land == "LU":
        bban = _ziffern(rng, 3) + _ziffern(rng, 13)
    else:
        raise ValueError(f"Land {land} nicht vorgesehen")
    ergebnis = land + _iban_pruefziffer(land, bban) + bban
    assert len(ergebnis) == IBAN_LAENGE[land] and iban_gueltig(ergebnis), ergebnis
    return ergebnis


def iban_formatieren(iban_roh: str, art: str = "gruppen") -> str:
    """'gruppen' (DIN 5008: Vierergruppen), 'kompakt' (ohne Leerzeichen)."""
    if art == "kompakt":
        return iban_roh
    return " ".join(iban_roh[i:i + 4] for i in range(0, len(iban_roh), 4))


def bic(rng, land: str = "DE") -> str:
    """Formal korrekter BIC (Bankkürzel + Land + Ort [+ Filiale]); BICs haben keine Prüfziffer."""
    buchstaben = "ABCDEFGHIJKLMNOPRSTUVWXYZ"
    bank = "".join(rng.choice(buchstaben) for _ in range(4))
    ort = rng.choice(buchstaben) + rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ123456789")
    if rng.random() < 0.55:
        return bank + land + ort + rng.choice(["XXX", "".join(rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ0123456789")
                                                          for _ in range(3))])
    return bank + land + ort


# ----------------------------------------------------------------------
# Steuer-ID, Steuernummer, USt-IdNr.
# ----------------------------------------------------------------------
def _mod11_10(ziffern: str) -> int:
    produkt = 10
    for z in ziffern:
        summe = (int(z) + produkt) % 10 or 10
        produkt = (2 * summe) % 11
    pruef = 11 - produkt
    return 0 if pruef == 10 else pruef


def steuer_id(rng) -> str:
    """Steuer-Identifikationsnummer (11 Ziffern, § 139b AO): erste Ziffer nicht 0, in den
    ersten zehn Ziffern genau eine Ziffer doppelt oder dreifach (dreifach nie direkt
    hintereinander), Prüfziffer nach ISO 7064 MOD 11,10."""
    while True:
        dreifach = rng.random() < 0.3
        ziffern = list("0123456789")
        rng.shuffle(ziffern)
        if dreifach:
            basis = ziffern[:8]
            doppelt = rng.choice(basis)
            folge = basis + [doppelt, doppelt]
        else:
            basis = ziffern[:9]
            doppelt = rng.choice(basis)
            folge = basis + [doppelt]
        rng.shuffle(folge)
        if folge[0] == "0":
            continue
        text = "".join(folge)
        if dreifach and doppelt * 3 in text:
            continue
        return text + str(_mod11_10(text))


def steuer_id_formatieren(nummer: str, art: str) -> str:
    if art == "gruppen":
        return f"{nummer[:2]} {nummer[2:5]} {nummer[5:8]} {nummer[8:]}"
    return nummer


def steuernummer(rng) -> str:
    """Steuernummer in einem Länderformat (nur Format, Prüfverfahren je Land nicht nachgebildet)."""
    art = rng.choice(["by", "bw", "nrw", "he", "ni", "be"])
    if art == "by":
        return f"{_ziffern(rng, 3)}/{_ziffern(rng, 3)}/{_ziffern(rng, 5)}"
    if art == "bw":
        return f"{_ziffern(rng, 2)}/{_ziffern(rng, 3)}/{_ziffern(rng, 5)}"
    if art == "nrw":
        return f"{_ziffern(rng, 3)}/{_ziffern(rng, 4)}/{_ziffern(rng, 4)}"
    if art == "he":
        return f"0{_ziffern(rng, 2)} {_ziffern(rng, 3)} {_ziffern(rng, 5)}"
    if art == "ni":
        return f"{_ziffern(rng, 2)}/{_ziffern(rng, 3)}/{_ziffern(rng, 5)}"
    return f"{_ziffern(rng, 2)}/{_ziffern(rng, 3)}/{_ziffern(rng, 5)}"


def ust_idnr(rng) -> str:
    acht = str(rng.randint(1, 9)) + _ziffern(rng, 7)
    return "DE" + acht + str(_mod11_10(acht))


# ----------------------------------------------------------------------
# Sozialversicherungsnummer, Krankenversichertennummer, Kindergeld
# ----------------------------------------------------------------------
_BEREICHE = ["02", "03", "04", "08", "09", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19",
             "20", "21", "23", "24", "25", "26", "28", "29", "38", "39", "40", "42", "43", "44", "45",
             "46", "47", "48", "49", "50", "51", "52", "53", "54", "55", "56", "57", "58", "59", "60",
             "61", "62", "63", "64", "65", "66", "67", "68", "69", "70", "71", "72", "73", "74", "75",
             "76", "77", "78", "79", "80", "81", "82", "89"]


def sv_pruefziffer(ohne_pruef: str) -> int:
    """Prüfziffer der Rentenversicherungsnummer (Buchstabe als zweistellige Zahl,
    Gewichte 2,1,2,5,7,1,2,1,2,1,2,1, Quersummen, Summe mod 10)."""
    ziffern = ohne_pruef[:8] + f"{ord(ohne_pruef[8].upper()) - 64:02d}" + ohne_pruef[9:11]
    gewichte = [2, 1, 2, 5, 7, 1, 2, 1, 2, 1, 2, 1]
    summe = 0
    for z, g in zip(ziffern, gewichte):
        p = int(z) * g
        summe += p // 10 + p % 10
    return summe % 10


def sv_nummer(rng, geburtsdatum: datetime.date, geburtsname: str, geschlecht: str) -> str:
    """Rentenversicherungsnummer: Bereich (2) + Geburtsdatum TTMMJJ + Anfangsbuchstabe des
    Geburtsnamens + Seriennummer (00-49 männlich, 50-99 weiblich) + Prüfziffer."""
    buchstabe = next((c for c in geburtsname.upper() if "A" <= c <= "Z"), "X")
    serie = rng.randint(0, 49) + (50 if geschlecht == "w" else 0)
    ohne = f"{rng.choice(_BEREICHE)}{geburtsdatum:%d%m%y}{buchstabe}{serie:02d}"
    return ohne + str(sv_pruefziffer(ohne))


def sv_formatieren(nummer: str, art: str) -> str:
    if art == "gruppen":
        return f"{nummer[:2]} {nummer[2:8]} {nummer[8]} {nummer[9:]}"
    if art == "gruppen2":
        return f"{nummer[:2]} {nummer[2:8]} {nummer[8]}{nummer[9:]}"
    return nummer


def kvnr(rng) -> str:
    """Krankenversichertennummer: Buchstabe + 8 Ziffern + Prüfziffer (Gewichte 1,2,1,2 …,
    Buchstabe als zweistellige Zahl, Quersummen, Summe mod 10)."""
    buchstabe = rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    acht = _ziffern(rng, 8)
    ziffern = f"{ord(buchstabe) - 64:02d}" + acht
    summe = 0
    for i, z in enumerate(ziffern):
        p = int(z) * (1 if i % 2 == 0 else 2)
        summe += p // 10 + p % 10
    return buchstabe + acht + str(summe % 10)


def kindergeldnummer(rng) -> str:
    return f"{rng.randint(1, 999):03d}FK{_ziffern(rng, 6)}"


# ----------------------------------------------------------------------
# Ausweise
# ----------------------------------------------------------------------
_AUSWEIS_ZEICHEN = "CFGHJKLMNPRTVWXYZ0123456789"


def icao_pruefziffer(text: str) -> int:
    gewichte = [7, 3, 1]
    summe = 0
    for i, c in enumerate(text):
        wert = int(c) if c.isdigit() else ord(c) - 55
        summe += wert * gewichte[i % 3]
    return summe % 10


def personalausweisnummer(rng, mit_pruefziffer: bool) -> str:
    """Seriennummer des Personalausweises: 9 Zeichen aus dem zulässigen Alphabet (erstes
    Zeichen ein Buchstabe), optional mit Prüfziffer nach ICAO 9303 (wie in der MRZ)."""
    erstes = rng.choice("LMNPRTVWXYZ")
    rest = "".join(rng.choice(_AUSWEIS_ZEICHEN) for _ in range(8))
    nummer = erstes + rest
    return nummer + str(icao_pruefziffer(nummer)) if mit_pruefziffer else nummer


def reisepassnummer(rng) -> str:
    nummer = "C" + "".join(rng.choice(_AUSWEIS_ZEICHEN) for _ in range(8))
    return nummer


def fuehrerscheinnummer(rng) -> str:
    """Führerscheinnummer (11 Zeichen, nur Format)."""
    return (rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ") + _ziffern(rng, 3)
            + "".join(rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ0123456789") for _ in range(5))
            + _ziffern(rng, 1) + rng.choice("123456789"))


# ----------------------------------------------------------------------
# Kreditkarte, Mandatsreferenz, FIN
# ----------------------------------------------------------------------
def luhn_gueltig(nummer: str) -> bool:
    ziffern = [int(c) for c in nummer if c.isdigit()]
    summe = 0
    for i, z in enumerate(reversed(ziffern)):
        if i % 2 == 1:
            z *= 2
            if z > 9:
                z -= 9
        summe += z
    return summe % 10 == 0


def _luhn_ergaenzen(praefix: str, laenge: int, rng) -> str:
    rumpf = praefix + _ziffern(rng, laenge - len(praefix) - 1)
    for p in "0123456789":
        if luhn_gueltig(rumpf + p):
            return rumpf + p
    raise AssertionError("keine Luhn-Ziffer")


def kreditkarte(rng) -> tuple:
    """(Marke, Nummer ohne Trenner, formatierte Nummer) mit gültiger Luhn-Prüfsumme."""
    marke = rng.choice(["Visa", "Mastercard", "Mastercard", "American Express", "Visa"])
    if marke == "Visa":
        nummer = _luhn_ergaenzen("4", 16, rng)
        teile = [nummer[i:i + 4] for i in range(0, 16, 4)]
    elif marke == "Mastercard":
        nummer = _luhn_ergaenzen(rng.choice(["51", "52", "53", "54", "55", "2221", "2720"]), 16, rng)
        teile = [nummer[i:i + 4] for i in range(0, 16, 4)]
    else:
        nummer = _luhn_ergaenzen(rng.choice(["34", "37"]), 15, rng)
        teile = [nummer[:4], nummer[4:10], nummer[10:]]
    trenner = rng.choice([" ", " ", "-"])
    return marke, nummer, trenner.join(teile)


def mandatsreferenz(rng) -> str:
    art = rng.randint(0, 3)
    if art == 0:
        return f"MR-{rng.randint(2015, 2025)}-{_ziffern(rng, 7)}"
    if art == 1:
        return f"{_ziffern(rng, 10)}{rng.randint(1, 9)}"
    if art == 2:
        return f"ML{_ziffern(rng, 9)}"
    return f"SEPA{_ziffern(rng, 6)}-{_ziffern(rng, 3)}"


_FIN_WERT = {**{str(i): i for i in range(10)},
             **dict(zip("ABCDEFGH", range(1, 9))), **dict(zip("JKLMN", range(1, 6))), "P": 7, "R": 9,
             **dict(zip("STUVWXYZ", range(2, 10)))}
_FIN_GEWICHT = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]
_WMI = ["WVW", "WBA", "WDD", "WAU", "VF1", "ZFA", "TMB", "YV1", "SAL", "WF0", "VSS", "KMH", "JTD",
        "UU1", "W0L", "VF3", "WMW", "SJN", "TRU", "WP0"]
_FIN_ZEICHEN = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"


def fin(rng) -> str:
    """Fahrzeug-Identifizierungsnummer (17 Zeichen ohne I, O, Q) mit Prüfziffer an Stelle 9."""
    rumpf = list(rng.choice(_WMI) + "".join(rng.choice(_FIN_ZEICHEN) for _ in range(5)) + "0"
                 + rng.choice("ABCDEFGHJKLMNPRSTVWXY123456789") + rng.choice(_FIN_ZEICHEN)
                 + _ziffern(rng, 6))
    summe = sum(_FIN_WERT[c] * g for c, g in zip(rumpf, _FIN_GEWICHT))
    rest = summe % 11
    rumpf[8] = "X" if rest == 10 else str(rest)
    return "".join(rumpf)


# ----------------------------------------------------------------------
# Kfz-Kennzeichen
# ----------------------------------------------------------------------
KFZ_KUERZEL = ["N", "M", "B", "HH", "K", "F", "S", "ER", "FÜ", "BA", "BT", "A", "R", "WÜ", "KA", "HD",
               "MA", "DA", "OF", "GI", "MR", "H", "HB", "HRO", "DD", "L", "EF", "J", "MD", "HAL", "PB",
               "BI", "MS", "DO", "E", "BO", "D", "W", "KR", "MG", "AC", "BN", "SU", "KO", "TR", "SB",
               "KL", "LU", "MZ", "WI", "RV", "FN", "UL", "AA", "ES", "LB", "BB", "TÜ", "RT", "PF", "VS",
               "OG", "FR", "LÖ", "NM", "IN", "PA", "LA", "DEG", "REG", "CHA", "AM", "WEN", "NEA", "AN",
               "FO", "CO", "KC", "KU", "HO", "WUN", "TIR", "NEW", "AS", "SAD", "RH", "LAU", "SC", "ROW",
               "GÖ", "OS", "OL", "HI", "WOB", "CE", "STD", "PI", "SE", "OD", "RZ", "HL", "SN", "PCH",
               "GÜ", "NB", "HST", "LDS", "MOL", "OHV", "TF", "BAR", "OPR", "GT", "LIP", "HF", "MI", "GE",
               "RE", "WES", "KLE", "VIE", "NE", "GL", "SIM", "ERB", "MTK", "HG", "LM", "DÜW", "SÜW",
               "KUS", "MYK", "AW", "NR", "AK", "WW"]
_ERKENNUNG = "ABCDEFGHJKLMNPRSTUVWXYZ"


def kennzeichen(rng, art: str = "standard") -> str:
    """Deutsches Kennzeichen in Schreibweise mit Bindestrich: 'N-AB 1234', 'M-X 123E', 'HH-AB 12H'."""
    kuerzel = rng.choice(KFZ_KUERZEL)
    buchst = "".join(rng.choice(_ERKENNUNG) for _ in range(rng.choice([1, 2, 2])))
    max_ziffern = max(1, min(4, 8 - len(kuerzel) - len(buchst)))
    ziffern = str(rng.randint(1, 10 ** rng.randint(1, max_ziffern) - 1))
    zusatz = ""
    if art == "e":
        zusatz = "E"
    elif art == "h":
        zusatz = "H"
    return f"{kuerzel}-{buchst} {ziffern}{zusatz}"


def kennzeichen_schreibweise(kz: str, art: str) -> str:
    """Varianten: 'bindestrich' ('N-AB 1234'), 'leer' ('N AB 1234'), 'kompakt' ('N-AB1234')."""
    if art == "leer":
        return kz.replace("-", " ")
    if art == "kompakt":
        return kz.replace(" ", "")
    return kz


def kennzeichen_ausland(rng) -> tuple:
    """(Land, Kennzeichen) in landestypischer Schreibweise."""
    land = rng.choice(["AT", "CH", "NL", "PL", "FR", "IT", "TR", "CZ"])
    gross = "ABCDEFGHJKLMNPRSTUVWXYZ"
    if land == "AT":
        return land, f"{rng.choice(['W', 'G', 'L', 'S', 'I', 'KU', 'SZ', 'BR'])}-{rng.randint(100, 99999)}{rng.choice(gross)}"
    if land == "CH":
        return land, f"{rng.choice(['ZH', 'BE', 'SG', 'BS', 'LU', 'AG', 'TG'])} {rng.randint(1000, 999999)}"
    if land == "NL":
        return land, f"{rng.randint(10, 99)}-{''.join(rng.choice(gross) for _ in range(3))}-{rng.randint(1, 9)}"
    if land == "PL":
        return land, f"{rng.choice(['WA', 'PO', 'KR', 'GD', 'WR', 'SZ'])} {rng.randint(10000, 99999)}"
    if land == "FR":
        return land, f"{''.join(rng.choice(gross) for _ in range(2))}-{rng.randint(100, 999)}-{''.join(rng.choice(gross) for _ in range(2))}"
    if land == "IT":
        return land, f"{''.join(rng.choice(gross) for _ in range(2))} {rng.randint(100, 999)} {''.join(rng.choice(gross) for _ in range(2))}"
    if land == "TR":
        return land, f"{rng.randint(1, 81):02d} {''.join(rng.choice(gross) for _ in range(rng.randint(1, 3)))} {rng.randint(10, 9999)}"
    return land, f"{rng.randint(1, 9)}{rng.choice(gross)}{rng.randint(1, 9)} {rng.randint(1000, 9999)}"


# ----------------------------------------------------------------------
# Telefonnummern
# ----------------------------------------------------------------------
# (Vorwahl ohne 0, Länge der Teilnehmernummer)
VORWAHLEN = [("30", 8), ("40", 8), ("89", 8), ("911", 7), ("69", 8), ("221", 7), ("211", 7), ("711", 7),
             ("341", 7), ("351", 7), ("511", 7), ("421", 7), ("201", 7), ("231", 7), ("234", 7), ("921", 6),
             ("951", 6), ("9131", 6), ("941", 6), ("821", 7), ("731", 6), ("761", 6), ("621", 7),
             ("6221", 6), ("681", 6), ("631", 6), ("261", 6), ("651", 6), ("228", 7), ("241", 6), ("251", 6),
             ("521", 6), ("531", 6), ("551", 6), ("561", 6), ("641", 6), ("361", 6), ("3641", 6), ("391", 6),
             ("331", 6), ("381", 6), ("385", 6), ("431", 6), ("451", 6), ("4131", 6), ("8031", 6),
             ("8441", 5), ("9561", 5), ("9281", 5), ("3581", 5), ("9171", 5), ("7121", 6), ("6151", 6)]
MOBIL = ["151", "152", "157", "159", "160", "162", "163", "170", "171", "172", "173", "174", "175",
         "176", "177", "178", "179", "1511", "1520", "1522", "1523", "1525", "1577", "1590"]


def telefon(rng, mobil: bool = False) -> tuple:
    """(Vorwahl ohne 0, Teilnehmernummer) – Rohform; formatiert wird mit telefon_formatieren."""
    if mobil:
        vorwahl = rng.choice(MOBIL)
        laenge = 7 if len(vorwahl) == 3 else 7
        return vorwahl, str(rng.randint(1, 9)) + _ziffern(rng, laenge - 1)
    vorwahl, laenge = rng.choice(VORWAHLEN)
    return vorwahl, str(rng.randint(2, 9)) + _ziffern(rng, laenge - 1)


TELEFON_FORMATE = ["din", "din_durchwahl", "klammer", "schraeg", "schraeg_leer", "strich", "plus49",
                   "plus49_null", "null049", "gruppen", "alt_paare"]


def telefon_formatieren(vorwahl: str, nummer: str, art: str) -> str:
    """Bürotypische Schreibweisen (DIN 5008 und gängige Altformen)."""
    if art == "din":
        return f"0{vorwahl} {nummer}"
    if art == "din_durchwahl":
        return f"0{vorwahl} {nummer[:-2]}-{nummer[-2:]}"
    if art == "klammer":
        return f"(0{vorwahl}) {_paare(nummer)}"
    if art == "schraeg":
        return f"0{vorwahl}/{nummer}"
    if art == "schraeg_leer":
        return f"0{vorwahl} / {_gruppen3(nummer)}"
    if art == "strich":
        return f"0{vorwahl}-{nummer}"
    if art == "plus49":
        return f"+49 {vorwahl} {nummer}"
    if art == "plus49_null":
        return f"+49 (0){vorwahl} {nummer}"
    if art == "null049":
        return f"0049 {vorwahl} {nummer}"
    if art == "gruppen":
        return f"0{vorwahl} {_gruppen3(nummer)}"
    if art == "alt_paare":
        v = "0" + vorwahl                      # Altform: Paare von rechts ("0 89", "09 11")
        paare = []
        while v:
            paare.insert(0, v[-2:])
            v = v[:-2]
        return f"{' '.join(paare)} / {_paare(nummer)}"
    raise ValueError(art)


def _paare(nummer: str) -> str:
    if len(nummer) % 2:
        return nummer[:3] + " " + " ".join(nummer[i:i + 2] for i in range(3, len(nummer), 2))
    return " ".join(nummer[i:i + 2] for i in range(0, len(nummer), 2))


def _gruppen3(nummer: str) -> str:
    gruppen = [nummer[i:i + 3] for i in range(0, len(nummer), 3)]
    if len(gruppen) > 1 and len(gruppen[-1]) == 1:       # keine einzelne Ziffer am Ende
        gruppen[-2:] = [gruppen[-2][:2], gruppen[-2][2:] + gruppen[-1]]
    return " ".join(gruppen)


def telefon_ausland(rng) -> str:
    art = rng.randint(0, 10)
    if art == 0:
        return f"+43 1 {_ziffern(rng, 7)}"
    if art == 1:
        return f"+43 664 {_ziffern(rng, 7)}"
    if art == 2:
        return f"+41 44 {_ziffern(rng, 3)} {_ziffern(rng, 2)} {_ziffern(rng, 2)}"
    if art == 3:
        return f"+41 79 {_ziffern(rng, 3)} {_ziffern(rng, 2)} {_ziffern(rng, 2)}"
    if art == 4:
        return f"+31 20 {_ziffern(rng, 3)} {_ziffern(rng, 4)}"
    if art == 5:
        return f"+31 6 {_ziffern(rng, 8)}"
    if art == 6:
        return f"+33 1 {_ziffern(rng, 2)} {_ziffern(rng, 2)} {_ziffern(rng, 2)} {_ziffern(rng, 2)}"
    if art == 7:
        return f"+48 {rng.choice(['22', '601', '512'])} {_ziffern(rng, 3)} {_ziffern(rng, 3)}"
    if art == 8:
        return f"+90 532 {_ziffern(rng, 3)} {_ziffern(rng, 2)} {_ziffern(rng, 2)}"
    if art == 9:
        return f"+39 02 {_ziffern(rng, 4)} {_ziffern(rng, 4)}"
    return f"0043 664 {_ziffern(rng, 7)}"


# ----------------------------------------------------------------------
# Versicherungs-Kennungen (frei erfundene Formate, wie sie Versicherer verwenden)
# ----------------------------------------------------------------------
def vertragsnummer(rng, sparte: str = "LV") -> str:
    art = rng.randint(0, 7)
    jahr = rng.randint(2008, 2025)
    if art == 0:
        return f"{sparte}-{jahr}-{_ziffern(rng, 6)}"
    if art == 1:
        return f"{rng.randint(1, 9)} {_ziffern(rng, 3)} {_ziffern(rng, 3)} {_ziffern(rng, 3)}"
    if art == 2:
        return f"{sparte} {_ziffern(rng, 4)}-{_ziffern(rng, 4)}-{_ziffern(rng, 2)}"
    if art == 3:
        return f"{_ziffern(rng, 3)}/{_ziffern(rng, 6)}-{rng.randint(0, 9)}"
    if art == 4:
        return f"{sparte}{_ziffern(rng, 9)}"
    if art == 5:
        return f"{_ziffern(rng, 2)}.{_ziffern(rng, 3)}.{_ziffern(rng, 3)}.{_ziffern(rng, 1)}"
    if art == 6:
        return f"{sparte}/{_ziffern(rng, 2)}/{_ziffern(rng, 7)}"
    return f"{_ziffern(rng, 10)}"


def kundennummer(rng) -> str:
    art = rng.randint(0, 3)
    if art == 0:
        return _ziffern(rng, 8)
    if art == 1:
        return f"K-{_ziffern(rng, 7)}"
    if art == 2:
        return f"{_ziffern(rng, 3)} {_ziffern(rng, 3)} {_ziffern(rng, 3)}"
    return f"{_ziffern(rng, 2)}-{_ziffern(rng, 6)}"


def schadennummer(rng, sparte: str = "KH") -> str:
    art = rng.randint(0, 3)
    jahr = rng.randint(2023, 2025)
    if art == 0:
        return f"{jahr}-{sparte}-{_ziffern(rng, 6)}"
    if art == 1:
        return f"S{_ziffern(rng, 9)}"
    if art == 2:
        return f"{sparte} {_ziffern(rng, 2)}/{_ziffern(rng, 5)}/{str(jahr)[2:]}"
    return f"{_ziffern(rng, 4)}.{_ziffern(rng, 4)}.{_ziffern(rng, 2)}"


def aktenzeichen(rng) -> str:
    art = rng.randint(0, 3)
    if art == 0:
        return f"{rng.randint(1, 99)} Js {rng.randint(100, 9999)}/{rng.randint(23, 25)}"
    if art == 1:
        return f"{rng.randint(100, 999)} C {rng.randint(1, 999)}/{rng.randint(23, 25)}"
    if art == 2:
        return f"VU/{rng.randint(2023, 2025)}/{_ziffern(rng, 5)}"
    return f"ST-{_ziffern(rng, 6)}-{rng.randint(23, 25)}"


def vermittlernummer(rng) -> str:
    return f"{_ziffern(rng, 2)}/{_ziffern(rng, 3)}/{_ziffern(rng, 3)}"


def ihk_registernummer(rng) -> str:
    return f"D-{''.join(rng.choice('ABCDEFGHJKLMNPRSTUVWXYZ0123456789') for _ in range(4))}-{''.join(rng.choice('ABCDEFGHJKLMNPRSTUVWXYZ0123456789') for _ in range(5))}-{_ziffern(rng, 2)}"


def lanr(rng) -> str:
    return _ziffern(rng, 9)


def rechnungsnummer(rng) -> str:
    return f"{rng.randint(2024, 2025)}-{_ziffern(rng, 5)}"


def glaeubiger_id(rng) -> str:
    """Gläubiger-Identifikationsnummer eines Unternehmens (kein Personenbezug)."""
    rumpf = "ZZZ0" + _ziffern(rng, 10)
    return "DE" + _iban_pruefziffer("DE", rumpf.replace("ZZZ", "")) + rumpf
