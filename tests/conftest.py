"""Gemeinsame Test-Einstellungen: Projektwurzel importierbar machen, Umgebungsprüfungen."""

import functools
import os
import sys
import unicodedata
import warnings
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parent.parent
if str(WURZEL) not in sys.path:
    sys.path.insert(0, str(WURZEL))

warnings.filterwarnings("ignore", category=FutureWarning)  # "fitz" API deprecated (PyMuPDF 2.x)


def _modell_vorhanden() -> bool:
    try:
        import spacy
        spacy.load("de_core_news_md")
        return True
    except Exception:
        return False


def _tessdata_vorhanden() -> bool:
    try:
        from anonymisierer.ocr import _tessdata_finden
        return _tessdata_finden() is not None
    except Exception:
        return False


# Bevorzugte Schriften in fester Reihenfolge (gleiche Wahl bei jedem Lauf), danach jede andere installierte
# TrueType-Schrift: Ein Test wird nur übersprungen, wenn KEINE installierte Schrift die Zeichen hat.
_SCHRIFTEN = ("DejaVuSans.ttf", "arial.ttf", "segoeui.ttf", "times.ttf", "calibri.ttf", "tahoma.ttf", "verdana.ttf",
              "Arial.ttf")
_SCHRIFT_ORDNER = ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/usr/share/fonts/TTF",
                   str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"),
                   str(Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Microsoft" / "Windows" / "Fonts"),
                   "/System/Library/Fonts/Supplemental", "/Library/Fonts", str(Path.home() / "Library" / "Fonts"))
_SCHRIFT_BAEUME = ("/usr/share/fonts", "/usr/local/share/fonts", str(Path.home() / ".local" / "share" / "fonts"),
                   str(Path.home() / ".fonts"))           # Linux: Schriften liegen in Unterordnern


def _schrift_kandidaten():
    gesehen = set()
    for ordner in _SCHRIFT_ORDNER:
        for name in _SCHRIFTEN:
            pfad = Path(ordner) / name
            if pfad.is_file() and pfad not in gesehen:
                gesehen.add(pfad)
                yield pfad
    for ordner, rekursiv in [(o, False) for o in _SCHRIFT_ORDNER] + [(o, True) for o in _SCHRIFT_BAEUME]:
        try:
            dateien = sorted((Path(ordner).rglob if rekursiv else Path(ordner).glob)("*"))
        except OSError:
            continue
        for pfad in dateien:
            if pfad.suffix.lower() == ".ttf" and pfad not in gesehen and pfad.is_file():
                gesehen.add(pfad)
                yield pfad


def textebene_fehlt(pdf, zeichen: str) -> str:
    """Die Zeichen aus `zeichen`, die die rohe Textebene von `pdf` (Pfad oder geöffnetes Dokument) NICHT als eigene,
    sichtbare Zeichen liefert – leer, wenn alle da sind. Sichtbar heißt: Breite > 0,01 pt (dieselbe Schwelle wie
    Vertrag 12.7). Liest direkt mit MuPDF (Leerraum und Ligaturen erhalten), unabhängig vom Seitenmodell: Eine
    Änderung am Programm kann diese Prüfung nicht verschieben."""
    import pymupdf as fitz
    flags = fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_PRESERVE_LIGATURES
    gesehen = set()
    doc = pdf if isinstance(pdf, fitz.Document) else fitz.open(pdf)
    try:
        for seite in doc:
            for block in seite.get_text("rawdict", flags=flags)["blocks"]:
                for zeile in block.get("lines", ()):
                    for span in zeile["spans"]:
                        gesehen.update(z["c"] for z in span["chars"] if z["bbox"][2] - z["bbox"][0] > 0.01)
    finally:
        if doc is not pdf:
            doc.close()
    return "".join(z for z in dict.fromkeys(zeichen) if z not in gesehen)


@functools.lru_cache(maxsize=None)
def _textebene_unterscheidet(pfad: Path, zeichen: frozenset) -> bool:
    """Kommt jedes Zeichen, mit dieser Schrift geschrieben, als eigenes, sichtbares Zeichen aus der Textebene zurück?
    Teilen sich Codepunkte eine Glyphe, schreibt MuPDF für die Glyphe nur EINEN davon (den höchsten) in die
    ToUnicode-Tabelle – die anderen kommen in der Textebene nie an. Probe: je Zeichen eine Zeile "x<Zeichen>x"."""
    import pymupdf as fitz
    doc = fitz.open()
    try:
        seite = doc.new_page()
        for i, z in enumerate(sorted(zeichen)):
            seite.insert_text((50, 60 + 20 * i), f"x{z}x", fontsize=11, fontname="F0", fontfile=str(pfad))
        with fitz.open(stream=doc.tobytes(), filetype="pdf") as gespeichert:
            return not textebene_fehlt(gespeichert, "".join(sorted(zeichen)))
    finally:
        doc.close()


def erste_passende_schrift(kandidaten, zeichen: frozenset, unterscheidbar: frozenset = frozenset()):
    """Die erste Schrift aus `kandidaten`, die alle Zeichen aus `zeichen` und `unterscheidbar` als Glyphe hat und
    deren Textebene die Zeichen aus `unterscheidbar` als eigene, sichtbare Zeichen liefert – sonst None."""
    import pymupdf as fitz
    for pfad in kandidaten:
        try:
            schrift = fitz.Font(fontfile=str(pfad))
            if not all(schrift.has_glyph(ord(z)) for z in zeichen | unterscheidbar):
                continue
            if unterscheidbar and not _textebene_unterscheidet(Path(pfad), unterscheidbar):
                continue
        except Exception:
            continue
        return pfad
    return None


@functools.lru_cache(maxsize=None)
def _schrift_fuer(zeichen: frozenset, unterscheidbar: frozenset = frozenset()):
    return erste_passende_schrift(_schrift_kandidaten(), zeichen, unterscheidbar)


def _ohne_steuerzeichen(zeichen: str) -> frozenset:
    return frozenset(z for z in zeichen if unicodedata.category(z) != "Cc")


def schrift_mit_zeichen(zeichen: str, unterscheidbar: str = ""):
    """Pfad einer installierten TrueType-Schrift, die ALLE angegebenen Zeichen enthält (unter Linux DejaVu Sans,
    unter Windows Arial/Segoe UI/Calibri/…), sonst None. Für Tests, die Sonderzeichen wie das Versal-ß (ẞ),
    Ligaturen oder die Windows-Sonderzeichen (NBSP, weicher Trennstrich, U+2011) in eine PDF schreiben müssen –
    die eingebauten Base-14-Schriften kennen sie nicht. Steuerzeichen (z. B. Zeilenumbrüche) zählen nicht mit,
    man kann also ganze Testzeilen übergeben.

    `unterscheidbar`: Zeichen, deren Regel der Test prüft und die deshalb in der Textebene als EIGENE, sichtbare
    Zeichen ankommen müssen. Manche Schriften legen z. B. weichen Trennstrich, U+2010 und U+2011 auf eine Glyphe;
    die Textebene liefert den weichen Trennstrich dann als U+2011, und eine Regel für U+00AD liefe mit dieser
    Schrift nie – der Test würde grün, ohne zu prüfen. Solche Schriften werden übersprungen (nächste Schrift)."""
    pfad = _schrift_fuer(_ohne_steuerzeichen(zeichen), _ohne_steuerzeichen(unterscheidbar))
    if unterscheidbar:
        _SCHRIFTWAHL.add((" ".join(f"U+{ord(z):04X}" for z in sorted(_ohne_steuerzeichen(unterscheidbar))), pfad))
    return pfad


_SCHRIFTWAHL = set()   # (unterscheidbare Zeichen, gewählte Schrift) – am Ende des Testlaufs ausgegeben


def pytest_terminal_summary(terminalreporter):
    for zeichen, pfad in sorted(_SCHRIFTWAHL, key=str):
        terminalreporter.write_line(f"Schriftwahl, Textebene unterscheidet {zeichen}: "
                                    f"{pfad or 'keine Schrift – diese Tests sind übersprungen'}")


def schrift_mit_geteilten_glyphen(quelle, ziel, teilung: dict) -> Path:
    """Schreibt nach `ziel` eine Kopie der TrueType-Schrift `quelle`, in der jeder Codepunkt k aus `teilung` die
    Glyphe von teilung[k] bekommt – Zeichen teilen sich dann eine Glyphe wie in Windows-Schriften (z. B.
    {0x2D: 0xAD}: Bindestrich auf der Glyphe des weichen Trennstrichs). Ersetzt die cmap durch EINE Unicode-Tabelle
    (Format 12, Plattform 3/Kodierung 10); alle anderen Tabellen bleiben Byte für Byte erhalten (eine digitale
    Signatur DSIG entfällt, sie passte nicht mehr). Nur für Tests – ohne zusätzliche Bibliothek."""
    import struct

    import pymupdf as fitz
    daten = Path(quelle).read_bytes()
    schrift = fitz.Font(fontfile=str(quelle))
    # ganze Grundebene (BMP) abfragen: Font.valid_codepoints() liefert in PyMuPDF 1.24.x eine leere Liste
    codepunkte = set(range(0x20, 0x10000)) | set(getattr(schrift, "valid_codepoints", list)() or ())
    abbildung = {cp: g for cp in sorted(codepunkte) if (g := schrift.has_glyph(cp))}
    for von, nach in teilung.items():
        if not schrift.has_glyph(nach):
            raise ValueError(f"{Path(quelle).name} hat keine Glyphe für U+{nach:04X}")
        abbildung[von] = schrift.has_glyph(nach)
    gruppen = []                                   # (erster, letzter Codepunkt, Glyphe des ersten)
    for cp in sorted(abbildung):
        g = abbildung[cp]
        if gruppen and cp == gruppen[-1][1] + 1 and g == gruppen[-1][2] + cp - gruppen[-1][0]:
            gruppen[-1][1] = cp
        else:
            gruppen.append([cp, cp, g])
    format12 = struct.pack(">HHIII", 12, 0, 16 + 12 * len(gruppen), 0, len(gruppen))
    format12 += b"".join(struct.pack(">III", *gr) for gr in gruppen)
    if daten[:4] == b"ttcf":
        raise ValueError(f"{Path(quelle).name} ist eine Schriftsammlung (TTC), keine einzelne TrueType-Schrift")
    version, anzahl = struct.unpack(">IH", daten[:6])
    tabellen = {}
    for i in range(anzahl):
        tag, _, versatz, laenge = struct.unpack(">4sIII", daten[12 + 16 * i:28 + 16 * i])
        tabellen[tag] = daten[versatz:versatz + laenge]
    tabellen[b"cmap"] = struct.pack(">HHHHI", 0, 1, 3, 10, 12) + format12
    tabellen.pop(b"DSIG", None)
    namen = sorted(tabellen)
    potenz = 1 << (len(namen).bit_length() - 1)
    kopf = struct.pack(">IHHHH", version, len(namen), 16 * potenz, potenz.bit_length() - 1, 16 * (len(namen) - potenz))
    versatz = 12 + 16 * len(namen)
    verzeichnis, inhalt = [], []
    for tag in namen:
        tabelle = tabellen[tag] + b"\0" * (-len(tabellen[tag]) % 4)
        pruefsumme = sum(struct.unpack(f">{len(tabelle) // 4}I", tabelle)) & 0xFFFFFFFF
        verzeichnis.append(struct.pack(">4sIII", tag, pruefsumme, versatz, len(tabellen[tag])))
        inhalt.append(tabelle)
        versatz += len(tabelle)
    Path(ziel).write_bytes(kopf + b"".join(verzeichnis) + b"".join(inhalt))
    return Path(ziel)


# Windows-Schriften (Arial, Segoe UI …) legen Leerzeichen und geschütztes Leerzeichen auf DIESELBE Glyphe, je nach
# Schrift auch Bindestrich, weichen Trennstrich und U+2010/U+2011. Die Textebene liefert dann für jede dieser Glyphen
# nur EINEN Codepunkt (MuPDF: den höchsten): Aus geschriebenem "Frau Groß" und "51-633867" wird beim Auslesen z. B.
# "Frau\xa0Groß" und "51\xad633867" bzw. "51\u2011633867"; mit DejaVu Sans (eigene Glyphen) bleibt es, wie es war.
# Das Angleichen gilt nur für Vergleiche des ausgelesenen Texts. Ein Test, der eine Regel für genau diese Zeichen
# prüft, wählt seine Schrift mit schrift_mit_zeichen(…, unterscheidbar=…) – sonst liefe die Regel womöglich nie.
_WINDOWS_TEXTEBENE = str.maketrans({"\xa0": " ", "\xad": "-", "\u2010": "-", "\u2011": "-"})


def textebene_angleichen(text: str) -> str:
    """Vereinheitlicht ausgelesenen Text für Vergleiche, die mit jeder Schrift dasselbe bedeuten sollen:
    geschütztes Leerzeichen -> Leerzeichen; weicher Trennstrich, U+2010 und U+2011 -> Bindestrich."""
    return text.translate(_WINDOWS_TEXTEBENE)


braucht_modell = pytest.mark.skipif(not _modell_vorhanden(), reason="spaCy-Modell de_core_news_md fehlt")
braucht_ocr = pytest.mark.skipif(not _tessdata_vorhanden(), reason="Tesseract-Sprachdaten fehlen")


@pytest.fixture
def tmp_pdf_ordner(tmp_path):
    """Leerer Ordner für Test-PDFs."""
    return tmp_path
