"""Programmsymbol icon.ico erzeugen (M-27/M-67) – ohne PIL.

Die Zeichnung (ein Blatt mit umgeknickter Ecke, schwarzen Balken und grauen Textzeilen) macht PyMuPDF:
anonymisierer.gui.programm_symbol_png – dieselbe Funktion setzt zur Laufzeit das Fenstersymbol. Dieses Skript
schreibt daraus den ICO-Container selbst:
  * 16, 32 und 48 Pixel als 32-Bit-Bitmap mit Alphakanal (so lesen es alle Windows-Versionen, Tk und PyInstaller),
  * 256 Pixel als PNG (üblich seit Windows Vista).

Aufruf (im Projektordner):   python werkzeuge/programmsymbol.py [Zielpfad]
Standard-Ziel ist icon.ico im Projektordner. EXE-bauen.bat bettet icon.ico in die EXE ein (--icon), die
Desktop-Verknüpfung (werkzeuge/verknuepfung.py) zeigt es ebenfalls.
"""

import struct
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
GROESSEN = (16, 32, 48, 256)
PNG_AB = 256                      # ab dieser Größe als PNG gespeichert, darunter als Bitmap


def _fitz():
    try:
        import pymupdf as fitz
    except ImportError:  # ältere PyMuPDF-Versionen kennen nur den Namen "fitz"
        import fitz
    return fitz


def _rgba(png: bytes) -> tuple[int, int, bytes]:
    """PNG -> (Breite, Höhe, RGBA-Bytes ohne vormultiplizierten Alphakanal), zeilenweise von oben."""
    fitz = _fitz()
    pix = fitz.Pixmap(png)
    if pix.n != 4 or not pix.alpha:
        pix = fitz.Pixmap(fitz.csRGB, pix, 1)
    roh = pix.samples
    aus = bytearray(len(roh))
    for i in range(0, len(roh), 4):
        r, g, b, a = roh[i], roh[i + 1], roh[i + 2], roh[i + 3]
        if 0 < a < 255:                         # MuPDF speichert vormultipliziert, ICO erwartet „gerade“ Werte
            r, g, b = (min(255, round(c * 255 / a)) for c in (r, g, b))
        elif a == 0:
            r = g = b = 0
        aus[i:i + 4] = bytes((r, g, b, a))
    return pix.width, pix.height, bytes(aus)


def bitmap_eintrag(png: bytes) -> bytes:
    """Ein ICO-Bild als 32-Bit-Bitmap (BITMAPINFOHEADER, Zeilen von unten, BGRA, dazu die 1-Bit-UND-Maske)."""
    breite, hoehe, rgba = _rgba(png)
    zeilen_farbe = []
    zeilen_maske = []
    masken_breite = ((breite + 31) // 32) * 4
    for y in range(hoehe - 1, -1, -1):
        farbe = bytearray()
        maske = bytearray(masken_breite)
        for x in range(breite):
            i = (y * breite + x) * 4
            r, g, b, a = rgba[i:i + 4]
            farbe += bytes((b, g, r, a))
            if a == 0:
                maske[x // 8] |= 0x80 >> (x % 8)
        zeilen_farbe.append(bytes(farbe))
        zeilen_maske.append(bytes(maske))
    daten = b"".join(zeilen_farbe) + b"".join(zeilen_maske)
    kopf = struct.pack("<IiiHHIIiiII", 40, breite, 2 * hoehe, 1, 32, 0, len(daten), 0, 0, 0, 0)
    return kopf + daten


def ico_bauen(bilder: dict[int, bytes]) -> bytes:
    """ICO-Container aus {Größe: PNG}; Größen ab PNG_AB als PNG, kleinere als Bitmap."""
    eintraege = []
    for groesse in sorted(bilder):
        png = bilder[groesse]
        eintraege.append((groesse, png if groesse >= PNG_AB else bitmap_eintrag(png)))
    kopf = struct.pack("<HHH", 0, 1, len(eintraege))
    verzeichnis = b""
    versatz = 6 + 16 * len(eintraege)
    for groesse, daten in eintraege:
        mass = 0 if groesse >= 256 else groesse
        verzeichnis += struct.pack("<BBBBHHII", mass, mass, 0, 0, 1, 32, len(daten), versatz)
        versatz += len(daten)
    return kopf + verzeichnis + b"".join(daten for _, daten in eintraege)


def ico_lesen(daten: bytes) -> list[dict]:
    """Einträge eines ICO-Containers: [{"groesse", "art" ("png"|"bitmap"), "daten"}] – für die Tests."""
    reserviert, typ, anzahl = struct.unpack_from("<HHH", daten, 0)
    if reserviert != 0 or typ != 1:
        raise ValueError("keine ICO-Datei")
    eintraege = []
    for nr in range(anzahl):
        breite, hoehe, _, _, ebenen, bits, laenge, versatz = struct.unpack_from("<BBBBHHII", daten, 6 + 16 * nr)
        bild = daten[versatz:versatz + laenge]
        if len(bild) != laenge:
            raise ValueError("ICO-Datei abgeschnitten")
        eintraege.append({"groesse": breite or 256, "hoehe": hoehe or 256, "bits": bits,
                          "art": "png" if bild.startswith(b"\x89PNG") else "bitmap", "daten": bild})
    return eintraege


def symbol_erzeugen(ziel: Path | None = None) -> Path:
    """icon.ico (bzw. ziel) neu schreiben und den Pfad liefern."""
    if str(WURZEL) not in sys.path:
        sys.path.insert(0, str(WURZEL))
    from anonymisierer.gui import programm_symbol_png
    ziel = Path(ziel) if ziel else WURZEL / "icon.ico"
    ziel.write_bytes(ico_bauen({g: programm_symbol_png(g) for g in GROESSEN}))
    return ziel


if __name__ == "__main__":
    pfad = symbol_erzeugen(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
    print(f"Programmsymbol geschrieben: {pfad} ({pfad.stat().st_size} Byte, Größen {', '.join(map(str, GROESSEN))})")
