"""Muster-Erkennung (reguläre Ausdrücke mit Validierung) und Kategorienliste."""

import re

def _iban_gueltig(iban: str) -> bool:
    """Prüfziffern-Kontrolle (Modulo 97) — filtert Zufallstreffer heraus."""
    s = re.sub(r"\s", "", iban).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", s):
        return False
    umgestellt = s[4:] + s[:4]
    zahl = "".join(str(int(z, 36)) for z in umgestellt)
    return int(zahl) % 97 == 1


# Jede Kategorie: (Anzeigename, Platzhalter, Suchfunktion)
def _suche(muster, text, flags=0):
    return [m.group(0) for m in re.finditer(muster, text, flags)]

def finde_iban(text):
    kandidaten = _suche(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?[A-Z0-9]{1,4})?\b", text)
    return [k for k in kandidaten if _iban_gueltig(k)]

def finde_email(text):
    return _suche(r"\b[\w.\-+%]+@[\w.\-]+\.[A-Za-z]{2,}\b", text)

def finde_telefon(text):
    # Deutsche Formate: 0171 1234567, +49 911 123456, (09171) 12 34 56 …
    # Der Blick zurück (?<!…) verhindert Treffer MITTEN in längeren Nummern.
    treffer = _suche(r"(?<![\d\-./])(?:\+49[\s\-/]?|0)\d{2,5}[\s\-/]?\d{3,}(?:[\s\-/]?\d{2,})*", text)
    # Mindestlänge, sonst erwischt man Vertragsnummern o. Ä.
    return [t for t in treffer if len(re.sub(r"\D", "", t)) >= 8]

def finde_geburtsdaten(text):
    """Datumsangaben, die bei 'geb.' / 'geb. am' / 'Geburtsdatum' o. Ä. stehen.
    Zwischen Stichwort und Datum dürfen bis zu 25 Zeichen liegen (auch
    Zeilenumbrüche) — deckt Formularlayouts ab wie:
    'geb. am / Geschlecht\\n02.09.1983'."""
    ergebnisse = []
    for m in re.finditer(
        r"(?:geb\.?|geboren|Geburtsdatum|Geburtstag)"
        r"[^\d]{0,25}?"
        r"(\d{1,2}\.\s?\d{1,2}\.\s?\d{2,4})", text, re.IGNORECASE | re.DOTALL):
        ergebnisse.append(m.group(1))
    return ergebnisse

def finde_alle_daten(text):
    """Optional: ALLE Datumsangaben (Vorsicht — auch Vertragsdaten!)."""
    return _suche(r"\b\d{1,2}\.\s?\d{1,2}\.\s?(?:19|20)\d{2}\b", text)

def finde_strasse(text):
    return _suche(
        r"\b[A-ZÄÖÜ][\w\.\-äöüß]*(?:straße|strasse|str\.|weg|platz|gasse|allee|"
        r"ring|damm|ufer|hof|steig|pfad|chaussee)\s+\d+\s?[a-hA-H]?\b", text)

def finde_plz_ort(text):
    return _suche(r"\b\d{5}\s+[A-ZÄÖÜ][a-zäöüß\-]+(?:\s(?:am|an\sder|bei|im)\s[A-ZÄÖÜ][a-zäöüß\-]+)?\b", text)

def finde_vertragsnummern(text):
    """Nummern, die hinter einem verräterischen Etikett stehen."""
    ergebnisse = []
    for m in re.finditer(
        r"(?:Versicherungsschein|Vertrags?|Kunden|Schaden[s]?|Antrags?|"
        r"Police[n]?|Personal|Mitglieds?|Depot|Konto|Zulage[n]?)"
        r"[\s\-]?(?:Nr\.?|Nummer|nummer)\s*[:.\s]?\s*"
        r"([A-Z0-9][A-Z0-9\-./ ]{3,24}[A-Z0-9])", text, re.IGNORECASE):
        ergebnisse.append(m.group(1).strip())
    return ergebnisse

def finde_sv_nummer(text):
    return _suche(r"\b\d{2}\s?\d{6}\s?[A-Z]\s?\d{3}\b", text)

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


def finde_steuer_id(text):
    ergebnisse = []
    # 1) Mit Beschriftung — auch Formularlayouts wie "Identifikationsnummer (4)"
    #    mit bis zu 12 Zeichen zwischen Etikett und Nummer (inkl. Zeilenumbruch)
    for m in re.finditer(r"(?:Steuer[\s\-]?(?:ID|Id|id)|IdNr\.?|Identifikationsnummer)"
                         r"[^\d]{0,12}?(\d[\d\s]{9,13}\d)", text, re.DOTALL):
        ergebnisse.append(m.group(1).strip())
    # 2) Ohne Beschriftung: freistehende 11-stellige Nummer mit gültiger Prüfziffer
    for m in re.finditer(r"(?<!\d)(\d{11})(?!\d)", text):
        if _steuer_id_gueltig(m.group(1)):
            ergebnisse.append(m.group(1))
    return ergebnisse

def finde_kindergeldnummer(text):
    """Kindergeldnummern wie 009FK407160 (Format: 3 Ziffern + FK + 6 Ziffern)."""
    return _suche(r"\b\d{3}\s?FK\s?\d{6}\b", text, re.IGNORECASE)

def finde_kennzeichen(text):
    return _suche(r"\b[A-ZÄÖÜ]{1,3}[-\s][A-Z]{1,2}\s?\d{1,4}[EH]?\b", text)


# Reihenfolge = Reihenfolge der Häkchen in der Oberfläche
KATEGORIEN = [
    # (Schlüssel, Anzeigename, Platzhalter, Funktion, standardmäßig an?)
    ("namen",    "Personennamen (KI-Erkennung)",        None,            None,                 True),
    ("iban",     "IBANs",                               "[IBAN]",        finde_iban,           True),
    ("email",    "E-Mail-Adressen",                     "[E-MAIL]",      finde_email,          True),
    ("telefon",  "Telefonnummern",                      "[TELEFON]",     finde_telefon,        True),
    ("geburt",   "Geburtsdaten",                        "[GEB-DATUM]",   finde_geburtsdaten,   True),
    ("strasse",  "Straße + Hausnummer",                 "[ADRESSE]",     finde_strasse,        True),
    ("plzort",   "PLZ + Ort",                           "[PLZ ORT]",     finde_plz_ort,        True),
    ("vertrag",  "Vertrags-/Kunden-/Schein-Nummern",    "[VERTRAGS-NR]", finde_vertragsnummern, True),
    ("svnr",     "Sozialversicherungsnummern",          "[SV-NR]",       finde_sv_nummer,      True),
    ("steuerid", "Steuer-IDs",                          "[STEUER-ID]",   finde_steuer_id,      True),
    ("kfz",      "Kfz-Kennzeichen",                     "[KENNZEICHEN]", finde_kennzeichen,    False),
    ("datum",    "ALLE Datumsangaben (Vorsicht!)",      "[DATUM]",       finde_alle_daten,     False),
]
