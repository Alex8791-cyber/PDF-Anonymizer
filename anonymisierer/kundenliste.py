"""Kundenliste (Vertrag Abschnitt 6): bekannte Kunden sicher erkennen – ohne ihre Daten im Klartext zu speichern.

    liste = Kundenliste.importieren("kunden.csv")            # Spalten automatisch erkannt
    liste = Kundenliste.importieren("export.csv", {"kundennummer": "Kd", "nachname": "Fam"})   # Zuordnung (GUI)
    liste.speichern()                                         # einstellungen-Ordner/kundenliste.dat
    liste = Kundenliste.laden()                               # None, wenn keine gespeichert ist
    treffer = liste.treffer(dok)                              # Treffer (Quelle "kundenliste", Sicherheit 1.0)
    Kundenliste.entfernen()

Gespeichert werden nur gesalzene SHA-256-Prüfwerte normalisierter Werte (Namen zusätzlich als Wortfolgen in beiden
Reihenfolgen, "Max Mustermann" und "Mustermann Max"). Das Salz ist zufällig je Kundenliste; unter Windows wird es mit
DPAPI (CryptProtectData, nur dieses Windows-Konto kann es entschlüsseln) geschützt, sonst steht es in der Datei, die
nur für den Benutzer lesbar ist (Rechte 0600, siehe Hinweis in `hinweis`).

Datensatz-Verknüpfung: Ein Kunde gilt im Dokument als erkannt, wenn ein starkes Merkmal passt (voller Name,
Kunden-/Vertragsnummer, IBAN, E-Mail); dann werden ALLE seine Merkmale gesucht (Geburtsdatum, Anschrift, Telefon,
Kennzeichen, Vor- und Nachname einzeln …). Schwache Merkmale allein lösen nichts aus.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import json
import os
import re
import secrets
import sys
from pathlib import Path

from . import dateien

# Merkmale (Schlüssel -> Anzeige; Reihenfolge = Spaltenauswahl der Oberfläche)
MERKMALE = {
    "name": "Name (vollständig)", "vorname": "Vorname", "nachname": "Nachname",
    "geburtsdatum": "Geburtsdatum", "strasse": "Straße (ggf. mit Hausnummer)", "hausnummer": "Hausnummer",
    "plz": "PLZ", "ort": "Ort", "iban": "IBAN", "kundennummer": "Kunden-/Vertragsnummer",
    "email": "E-Mail", "telefon": "Telefon", "kennzeichen": "Kfz-Kennzeichen",
}
# Merkmale, über die eine CSV-Zeile als Kunde zählt (Oberfläche: mindestens eines zuordnen)
STARKE_MERKMALE = ("name", "nachname", "iban", "kundennummer", "email")
# Kategorie je Prüfwert-Art
KATEGORIE = {"name": "namen", "vorname": "namen", "nachname": "namen", "geburtsdatum": "geburt",
             "strasse": "strasse", "plzort": "plzort", "iban": "iban", "kundennummer": "vertrag",
             "email": "email", "telefon": "telefon", "kennzeichen": "kfz"}
# starke Prüfwert-Arten (erkennen einen Kunden allein)
_STARK = {"name", "iban", "kundennummer", "email"}
FORMAT = "pdf-anonymisierer-kundenliste"
VERSION = 1
_PRUEFLAENGE = 16                     # Bytes je Prüfwert (128 Bit)

_KOPF_MUSTER = {
    "vorname": r"vorname[n]?|first ?name|given ?name",
    "nachname": r"nachname|familienname|zuname|last ?name|surname",
    "name": r"name|name, ?vorname|nachname, ?vorname|kunde|kundin|kundenname|versicherungsnehmer(?:in)?|vn|"
            r"inhaber|kontoinhaber|vollständiger name|full ?name",
    "geburtsdatum": r"geb(?:urts)?\.?[ -]?(?:datum|dat\.?|tag)?|geboren(?: am)?|birth ?date|date of birth|dob",
    "hausnummer": r"haus ?(?:nr|nummer)\.?|hnr\.?|hausnr\.?",
    "strasse": r"stra(?:ss|ß)e(?:,? ?(?:haus)?(?:nr|nummer)\.?)?|str\.?|anschrift|adresse|street",
    "plz": r"plz|postleitzahl|zip",
    "ort": r"ort|wohnort|stadt|city",
    "iban": r"iban|bankverbindung|konto ?\(iban\)",
    "kundennummer": r"(?:kunden|vertrags|versicherungsschein|versicherungs|vs|police|policen|mitglieds|"
                    r"schaden)[ -]?(?:nr|nummer|no)\.?|kd[ .-]?nr\.?|vsnr|kundennr|vertragsnr|kunden-?id|id",
    "email": r"e-?mail(?:[ -]?adresse)?|mail",
    "telefon": r"tel(?:efon)?\.?(?:[ -]?(?:nr|nummer)\.?)?|mobil(?:nummer)?|handy(?:nummer)?|rufnummer|phone",
    "kennzeichen": r"(?:kfz[ -]?|amtl\.? ?)?kennzeichen|nummernschild",
}


class SpaltenNichtErkannt(ValueError):
    """Die Kopfzeile der CSV-Datei enthält keine bekannten Spaltennamen – Zuordnung durch die Oberfläche."""


class KundenlisteFehler(ValueError):
    """Die gespeicherte Kundenliste ist beschädigt oder gehört zu einem anderen Windows-Konto."""


# ----------------------------------------------------------------------
# Normalisierung (eine Regel für Import und Dokument)
# ----------------------------------------------------------------------
_TITEL = {"dr", "prof", "med", "dent", "rer", "nat", "jur", "phil", "dipl", "ing", "kfm", "herr", "herrn", "frau",
          "mag", "ra", "hc", "von", "van", "de", "der", "den", "zu", "vom", "freiherr", "freifrau", "graf"}
_TOKEN_RE = re.compile(r"[^\W_]+")


def _falten(text: str) -> str:
    try:
        from . import wissen
        return wissen.normalisieren(text)
    except Exception:  # pragma: no cover - Wissensbasis fehlt
        import unicodedata
        z = unicodedata.normalize("NFKD", text.casefold().replace("ß", "ss"))
        return "".join(c for c in z if not unicodedata.combining(c))


def name_tokens(text: str) -> list:
    """Wörter eines Namens in Vergleichsform (ohne Titel, Anreden und Partikel)."""
    return [t for t in _TOKEN_RE.findall(_falten(text or "")) if t not in _TITEL]


def nummer_normal(text: str) -> str:
    """Kennung ohne Trennzeichen, Großbuchstaben ("DE89 3704 …" = "DE893704…", "N-AB 1234" = "NAB1234")."""
    return "".join(_TOKEN_RE.findall((text or "").upper())).replace("_", "")


def telefon_normal(text: str) -> str:
    """Nur Ziffern; Ländervorwahl +49/0049 wird zur 0 ("+49 (0) 911 12345" = "091112345")."""
    t = (text or "").strip()
    ziffern = re.sub(r"\D", "", t.replace("(0)", ""))
    if t.startswith("+49") or t.startswith("0049"):
        ziffern = "0" + ziffern[2:] if t.startswith("+") else "0" + ziffern[4:]
    elif t.startswith("+"):
        ziffern = "00" + ziffern
    return ziffern


_MONATE = {"jan": 1, "feb": 2, "mär": 3, "mrz": 3, "mar": 3, "apr": 4, "mai": 5, "jun": 6, "jul": 7, "aug": 8,
           "sep": 9, "okt": 10, "nov": 11, "dez": 12}


def datum_normal(text: str) -> str | None:
    """Datum in ISO-Form (JJJJ-MM-TT) aus TT.MM.JJJJ, T.M.JJ, TT/MM/JJJJ, JJJJ-MM-TT, "2. September 1983"."""
    t = (text or "").strip()
    m = re.fullmatch(r"(\d{1,2})[./][ \t]?(\d{1,2})[./][ \t]?(\d{2}|\d{4})", t)
    if m:
        tag, monat, jahr = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
        if m:
            jahr, monat, tag = int(m.group(1)), int(m.group(2)), int(m.group(3))
        else:
            m = re.fullmatch(r"(\d{1,2})\.?[ \t]*([A-Za-zäöüÄÖÜ]{3,9})\.?[ \t]*(\d{4})", t)
            if not m:
                return None
            monat = _MONATE.get(m.group(2)[:3].lower())
            if monat is None:
                return None
            tag, jahr = int(m.group(1)), int(m.group(3))
    if jahr < 100:
        jahr += 1900 if jahr > datetime.date.today().year % 100 else 2000
    try:
        return datetime.date(jahr, monat, tag).isoformat()
    except ValueError:
        return None


def strasse_normal(text: str) -> str:
    t = _falten(text or "")
    t = re.sub(r"\bstr\b\.?", "strasse", t)
    t = t.replace("straße", "strasse")
    return "".join(_TOKEN_RE.findall(t))


# ----------------------------------------------------------------------
# Salz schützen (Windows: DPAPI über ctypes; sonst Dateirechte 0600)
# ----------------------------------------------------------------------
def _dpapi(daten: bytes, schuetzen: bool) -> bytes:  # pragma: no cover - nur unter Windows ausführbar
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    puffer = ctypes.create_string_buffer(daten, len(daten))
    eingabe = DATA_BLOB(len(daten), ctypes.cast(puffer, ctypes.POINTER(ctypes.c_char)))
    ausgabe = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    CRYPTPROTECT_UI_FORBIDDEN = 0x01
    if schuetzen:
        ok = crypt32.CryptProtectData(ctypes.byref(eingabe), "PDF-Anonymisierer Kundenliste", None, None, None,
                                      CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(ausgabe))
    else:
        ok = crypt32.CryptUnprotectData(ctypes.byref(eingabe), None, None, None, None, CRYPTPROTECT_UI_FORBIDDEN,
                                        ctypes.byref(ausgabe))
    if not ok:
        raise KundenlisteFehler("Das Schlüsselmaterial der Kundenliste konnte nicht "
                                + ("geschützt" if schuetzen else "entschlüsselt (anderes Windows-Konto?)") + " werden.")
    try:
        return ctypes.string_at(ausgabe.pbData, ausgabe.cbData)
    finally:
        kernel32.LocalFree(ausgabe.pbData)


def _salz_schuetzen(salz: bytes) -> dict:
    if sys.platform == "win32":
        return {"art": "dpapi", "wert": base64.b64encode(_dpapi(salz, True)).decode("ascii")}
    return {"art": "datei", "wert": base64.b64encode(salz).decode("ascii")}


def _salz_lesen(eintrag: dict) -> bytes:
    roh = base64.b64decode(eintrag["wert"])
    if eintrag.get("art") == "dpapi":
        return _dpapi(roh, False)
    return roh


# ----------------------------------------------------------------------
# Spalten erkennen
# ----------------------------------------------------------------------
def _kopf_text(zelle) -> str:
    return " ".join(str(zelle or "").replace("_", " ").strip().strip(":").lower().split())


def spalten_erkennen(kopf) -> dict:
    """{merkmal: spaltenindex} für bekannte Spaltenüberschriften (Groß-/Kleinschreibung egal)."""
    erkannt = {}
    for index, zelle in enumerate(kopf or []):
        text = _kopf_text(zelle)
        if not text:
            continue
        for merkmal, muster in _KOPF_MUSTER.items():
            if merkmal not in erkannt and re.fullmatch(muster, text):
                erkannt[merkmal] = index
                break
    return erkannt


# ----------------------------------------------------------------------
# Die Kundenliste
# ----------------------------------------------------------------------
class Kundenliste:
    """Gesalzene Prüfwerte der Kunden; erkennt Kunden in Dokumenten (Detektor "kundenliste")."""

    def __init__(self, salz: bytes | None = None, kunden: list | None = None):
        self._salz = salz if salz is not None else secrets.token_bytes(32)
        self._kunden: list = kunden or []        # [{art: [prüfwert-hex, ...]}]
        self.hinweis: str | None = None
        self._index: dict | None = None

    # -- Prüfwerte -------------------------------------------------------
    def _pruefwert(self, art_raum: str, wert: str) -> str:
        return hashlib.sha256(self._salz + art_raum.encode() + b"\x00" + wert.encode("utf-8")).digest()[
            :_PRUEFLAENGE].hex()

    @property
    def anzahl_kunden(self) -> int:
        return len(self._kunden)

    def __len__(self):
        return self.anzahl_kunden

    def __repr__(self):
        return f"<Kundenliste: {self.anzahl_kunden} Kunden, nur Prüfwerte>"

    # -- Import ------------------------------------------------------------
    @staticmethod
    def importieren(csv_pfad, spalten: dict | None = None) -> "Kundenliste":
        """Liest eine CSV-Datei (UTF-8, UTF-8 mit BOM oder Windows-1252; Trennzeichen ; , Tab |). Ohne `spalten`
        werden die Spalten über die Kopfzeile erkannt (sonst SpaltenNichtErkannt -> Zuordnung durch die Oberfläche);
        mit `spalten` = {merkmal: Spaltenüberschrift | 0-basierter Index} (nur Indizes: Datei ohne Kopfzeile)."""
        zeilen = dateien.csv_vorschau(csv_pfad, max_zeilen=None)["zeilen"]
        if not zeilen:
            raise SpaltenNichtErkannt("Die CSV-Datei ist leer.")
        unbekannt = [m for m in (spalten or {}) if m not in MERKMALE]
        if unbekannt:
            raise KeyError(f"Unbekannte Merkmale: {', '.join(unbekannt)}")
        if spalten is None:
            zuordnung = spalten_erkennen(zeilen[0])
            if not any(m in zuordnung for m in STARKE_MERKMALE):
                raise SpaltenNichtErkannt("Spalten der Kundenliste nicht erkannt.")
            daten = zeilen[1:]
        elif any(isinstance(v, str) and not str(v).isdigit() for v in spalten.values()):
            kopf = [_kopf_text(z) for z in zeilen[0]]
            zuordnung = {}
            for merkmal, wert in spalten.items():
                if isinstance(wert, str) and not wert.isdigit():
                    if _kopf_text(wert) not in kopf:
                        raise SpaltenNichtErkannt(f"Spalte „{wert}“ steht nicht in der Kopfzeile.")
                    zuordnung[merkmal] = kopf.index(_kopf_text(wert))
                else:
                    zuordnung[merkmal] = int(wert)
            daten = zeilen[1:]
        else:
            zuordnung = {m: int(v) for m, v in spalten.items()}
            daten = zeilen
        if not any(m in zuordnung for m in STARKE_MERKMALE):
            raise SpaltenNichtErkannt("Keine Spalte mit Name, Nachname, Kundennummer, IBAN oder E-Mail zugeordnet.")
        liste = Kundenliste()
        for zeile in daten:
            werte = {m: zeile[i].strip() for m, i in zuordnung.items() if 0 <= i < len(zeile) and zeile[i].strip()}
            kunde = liste._kunde_aus(werte)
            if kunde:
                liste._kunden.append(kunde)
        return liste

    def _kunde_aus(self, werte: dict) -> dict | None:
        """Prüfwerte eines Kunden aus seinen Klartext-Werten (die Klartexte werden nicht aufbewahrt)."""
        pw: dict = {}

        def hinzu(art, raum, wert):
            if wert:
                pw.setdefault(art, [])
                p = self._pruefwert(raum, wert)
                if p not in pw[art]:
                    pw[art].append(p)

        vornamen = name_tokens(werte.get("vorname", ""))
        nachnamen = name_tokens(werte.get("nachname", ""))
        voll = werte.get("name", "")
        if voll and not (vornamen and nachnamen):
            if "," in voll:                                   # "Mustermann, Max"
                links, rechts = voll.split(",", 1)
                nachnamen = nachnamen or name_tokens(links)
                vornamen = vornamen or name_tokens(rechts)
            else:
                t = name_tokens(voll)
                if len(t) >= 2:
                    vornamen = vornamen or t[:-1]
                    nachnamen = nachnamen or t[-1:]
                elif t and not nachnamen:
                    nachnamen = t
        if vornamen and nachnamen:
            nach = " ".join(nachnamen)
            for vor in {" ".join(vornamen), vornamen[0]}:
                hinzu("name", "name", f"{vor} {nach}")
                hinzu("name", "name", f"{nach} {vor}")
            for v in vornamen:
                if len(v) >= 2:
                    hinzu("vorname", "name", v)
        for n in nachnamen:
            if len(n) >= 2:
                hinzu("nachname", "name", n)
        if len(nachnamen) > 1:
            hinzu("nachname", "name", " ".join(nachnamen))
        geb = datum_normal(werte.get("geburtsdatum", ""))
        hinzu("geburtsdatum", "datum", geb)
        strasse = werte.get("strasse", "")
        if strasse:
            if werte.get("hausnummer") and not re.search(r"\d", strasse):
                strasse = f"{strasse} {werte['hausnummer']}"
            hinzu("strasse", "strasse", strasse_normal(strasse))
        if werte.get("plz") and werte.get("ort"):
            hinzu("plzort", "plzort", f"{nummer_normal(werte['plz'])} {' '.join(name_tokens(werte['ort']))}")
        for art in ("iban", "kundennummer", "kennzeichen"):
            n = nummer_normal(werte.get(art, ""))
            if len(n) >= 4:
                hinzu(art, "nummer", n)
        mail = (werte.get("email") or "").strip().casefold()
        if "@" in mail:
            hinzu("email", "email", mail)
        tel = telefon_normal(werte.get("telefon", ""))
        if len(tel) >= 6:
            hinzu("telefon", "telefon", tel)
        if not any(a in pw for a in _STARK) and "nachname" not in pw:
            return None
        return pw

    # -- Speichern / Laden ---------------------------------------------------
    def speichern(self, pfad=None) -> Path:
        """Speichert nur Prüfwerte (JSON, UTF-8). Unter Windows ist das Salz mit DPAPI geschützt, sonst ist die
        Datei nur für den Benutzer lesbar (0600)."""
        pfad = Path(pfad) if pfad is not None else dateien.kundenliste_pfad()
        pfad.parent.mkdir(parents=True, exist_ok=True)
        inhalt = {"format": FORMAT, "version": VERSION, "salz": _salz_schuetzen(self._salz),
                  "erstellt": datetime.date.today().isoformat(), "kunden": self._kunden}
        daten = json.dumps(inhalt, ensure_ascii=True, separators=(",", ":")).encode("ascii")
        tmp = pfad.with_name(pfad.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, daten)
        finally:
            os.close(fd)
        os.replace(tmp, pfad)
        if sys.platform != "win32":
            try:
                os.chmod(pfad, 0o600)
            except OSError:  # pragma: no cover
                pass
            self.hinweis = ("Kundenliste gespeichert (nur gesalzene Prüfwerte); die Datei ist nur für Ihr "
                            "Benutzerkonto lesbar.")
        return pfad

    @staticmethod
    def laden(pfad=None) -> "Kundenliste | None":
        """Lädt die gespeicherte Kundenliste; None, wenn keine existiert. Beschädigte Datei: KundenlisteFehler."""
        pfad = Path(pfad) if pfad is not None else dateien.kundenliste_pfad()
        if not pfad.exists():
            return None
        try:
            inhalt = json.loads(pfad.read_text(encoding="utf-8"))
            if inhalt.get("format") != FORMAT:
                raise KundenlisteFehler("Unbekanntes Dateiformat der Kundenliste.")
            salz = _salz_lesen(inhalt["salz"])
            kunden = [dict(k) for k in inhalt["kunden"]]
        except KundenlisteFehler:
            raise
        except (OSError, ValueError, KeyError, TypeError) as fehler:
            raise KundenlisteFehler(f"Die gespeicherte Kundenliste ist beschädigt ({fehler}).") from None
        return Kundenliste(salz, kunden)

    @staticmethod
    def entfernen(pfad=None):
        """Löscht die gespeicherte Kundenliste."""
        pfad = Path(pfad) if pfad is not None else dateien.kundenliste_pfad()
        if pfad.exists():
            pfad.unlink()

    # -- Erkennen ------------------------------------------------------------
    def _index_bauen(self) -> dict:
        """Prüfwert -> [(kunde, art)]."""
        index: dict = {}
        for nr, kunde in enumerate(self._kunden):
            for art, werte in kunde.items():
                for p in werte:
                    index.setdefault(p, []).append((nr, art))
        return index

    def _kandidaten(self, text: str):
        """(start, ende, raum, normalisierter wert) für alle Stellen des Texts, die ein Merkmal sein könnten."""
        # Namen: Wortfolgen aus 1–4 Wörtern
        woerter = [(m.start(), m.end(), _falten(m.group(0))) for m in re.finditer(r"[^\W\d_][\w'’\-]*", text)]
        woerter = [(s, e, w) for s, e, w in woerter if w not in _TITEL]
        for i in range(len(woerter)):
            teile = []
            for k in range(i, min(i + 4, len(woerter))):
                if k > i:
                    zwischen = text[woerter[k - 1][1]:woerter[k][0]]
                    if len(zwischen) > 3 or "\n\n" in zwischen or any(c.isalnum() for c in zwischen):
                        break
                teile.append(woerter[k][2].replace("-", " "))
                yield woerter[i][0], woerter[k][1], "name", " ".join(" ".join(teile).split())
        # Nummern: Folgen aus Buchstaben/Ziffern-Gruppen (IBAN, Kunden-/Vertragsnummer, Kennzeichen, PLZ)
        gruppen = [(m.start(), m.end()) for m in re.finditer(r"[A-Za-z0-9]+", text)]
        for i in range(len(gruppen)):
            s0 = gruppen[i][0]
            kette = ""
            for k in range(i, min(i + 9, len(gruppen))):
                if k > i:
                    zwischen = text[gruppen[k - 1][1]:gruppen[k][0]]
                    if len(zwischen) > 2 or any(c not in " -./\t" for c in zwischen):
                        break
                kette += text[gruppen[k][0]:gruppen[k][1]].upper()
                if any(c.isdigit() for c in kette) and len(kette) >= 4:
                    yield s0, gruppen[k][1], "nummer", kette
        # Telefon, Datum, E-Mail, Straße, PLZ+Ort über die Muster
        from . import muster
        for s, e in muster.finde_telefon_stellen(text):
            yield s, e, "telefon", telefon_normal(text[s:e])
        for m in re.finditer(r"(?<!\d)(?:\d{1,2}[./][ \t]?\d{1,2}[./][ \t]?\d{2,4}|\d{4}-\d{1,2}-\d{1,2}|"
                             r"\d{1,2}\.?[ \t]*[A-Za-zäöüÄÖÜ]{3,9}\.?[ \t]*\d{4})(?!\d)", text):
            iso = datum_normal(m.group(0))
            if iso:
                yield m.start(), m.end(), "datum", iso
        for s, e in muster.finde_email_stellen(text):
            yield s, e, "email", re.sub(r"\s", "", text[s:e]).casefold()
        for s, e in muster.finde_strasse_stellen(text):
            yield s, e, "strasse", strasse_normal(text[s:e])
        for s, e in muster.finde_plz_ort_stellen(text):
            m = re.match(r"\D*(\d{4,5})\s+(.*)", text[s:e], re.S)
            if m:
                yield s, e, "plzort", f"{m.group(1)} {' '.join(name_tokens(m.group(2)))}"

    def treffer(self, dok) -> list:
        """Treffer für alle Merkmale der Kunden, die im Dokument über ein starkes Merkmal erkannt sind."""
        from .detektoren import Treffer
        if not self._kunden:
            return []
        if self._index is None:
            self._index = self._index_bauen()
        text = getattr(dok, "text", dok if isinstance(dok, str) else "")
        index = self._index
        cache: dict = {}
        fundstellen = []                                   # (start, ende, kunde, art)
        for s, e, raum, wert in self._kandidaten(text):
            schluessel = (raum, wert)
            p = cache.get(schluessel)
            if p is None:
                p = cache[schluessel] = self._pruefwert(raum, wert)
            for kunde, art in index.get(p, ()):
                fundstellen.append((s, e, kunde, art))
        erkannt = {kunde for _, _, kunde, art in fundstellen if art in _STARK}
        aus = []
        namen_je_kunde: dict = {}
        for s, e, kunde, art in fundstellen:
            if kunde in erkannt and art == "name":
                alt = namen_je_kunde.get(kunde)
                if alt is None or (e - s) > (alt[1] - alt[0]):
                    namen_je_kunde[kunde] = (s, e)
        gesehen = set()
        for s, e, kunde, art in fundstellen:
            if kunde not in erkannt or (s, e, art) in gesehen:
                continue
            gesehen.add((s, e, art))
            kategorie = KATEGORIE.get(art, "namen")
            gruppe = None
            if kategorie == "namen" and kunde in namen_je_kunde:
                a, b = namen_je_kunde[kunde]
                gruppe = " ".join(text[a:b].split())
            aus.append(Treffer(s, e, kategorie, "kundenliste", 1.0, gruppe))
        return aus
