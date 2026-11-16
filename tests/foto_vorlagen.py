"""Synthetische Prüfbilder für die Fotobereich-Erkennung (tests/test_fotos.py, Messung der Erkennung).

Keine echten Gesichter: Porträts entstehen aus Verläufen, Rauschen und Formen (Kopf-Ellipse mit Schattierung, Haare,
Schultern, Augen), Ausweise als Karte mit Sicherheitsmuster, Lichtbild, Feldern und maschinenlesbarer Zone (MRZ),
Gegenstandsfotos (Schadenfotos) aus Rauschfeldern und Körpern mit Glanz. Dazu Dinge, die KEIN Foto sind: Text,
Logos aus Flächenfarben, Stempel, Diagramme, Unterschriften.

Alles ist mit numpy und PyMuPDF gebaut (keine weiteren Pakete) und mit dem Zufallsgenerator `rng` wiederholbar.
Bilder sind uint8-Arrays (Höhe, Breite, 3) bzw. (Höhe, Breite) für Grau.
"""

from __future__ import annotations

import math

import numpy as np

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen
    import fitz

MM = 72 / 25.4                      # pt je mm
A4 = (595.0, 842.0)


# ----------------------------------------------------------------------
# Grundbausteine
# ----------------------------------------------------------------------
def _box(a: np.ndarray, r: int) -> np.ndarray:
    """Kastenfilter (Radius r) entlang beider Achsen, mit Randwiederholung."""
    if r <= 0:
        return a
    a = a.astype(np.float32)
    for achse in (0, 1):
        pad = [(0, 0)] * a.ndim
        pad[achse] = (r + 1, r)
        p = np.pad(a, pad, mode="edge")
        c = np.cumsum(p, axis=achse, dtype=np.float64)
        n = a.shape[achse]
        hinten = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=achse)
        vorn = np.take(c, np.arange(0, n), axis=achse)
        a = ((hinten - vorn) / (2 * r + 1)).astype(np.float32)
    return a


def glaetten(a: np.ndarray, sigma: float) -> np.ndarray:
    """Näherung einer Gauß-Unschärfe (drei Kastenfilter)."""
    if sigma <= 0.3:
        return a.astype(np.float32)
    r = max(1, int(round(sigma * 0.8)))
    b = a.astype(np.float32)
    for _ in range(3):
        b = _box(b, r)
    return b


def rauschfeld(rng, h: int, w: int, skalen=(64, 16, 4), gewichte=(1.0, 0.5, 0.25)) -> np.ndarray:
    """Glattes Zufallsfeld (-1 … 1) aus hochskaliertem Rauschen mehrerer Größen (wie Wolken, Stoff, Lack)."""
    feld = np.zeros((h, w), np.float32)
    for skala, gewicht in zip(skalen, gewichte):
        gh, gw = max(2, h // skala + 2), max(2, w // skala + 2)
        grob = rng.standard_normal((gh, gw)).astype(np.float32)
        ys = np.linspace(0, gh - 1.001, h)
        xs = np.linspace(0, gw - 1.001, w)
        y0, x0 = ys.astype(int), xs.astype(int)
        fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]
        a = grob[y0][:, x0]
        b = grob[y0][:, x0 + 1]
        c = grob[y0 + 1][:, x0]
        d = grob[y0 + 1][:, x0 + 1]
        feld += gewicht * (a * (1 - fy) * (1 - fx) + b * (1 - fy) * fx + c * fy * (1 - fx) + d * fy * fx)
    feld /= max(1e-6, float(np.abs(feld).max()))
    return feld


def _ellipse(h, w, cy, cx, ry, rx, weich=2.0) -> np.ndarray:
    """Weiche Ellipsenmaske 0..1."""
    y, x = np.ogrid[:h, :w]
    d = np.sqrt(((y - cy) / max(ry, 1e-3)) ** 2 + ((x - cx) / max(rx, 1e-3)) ** 2)
    rand = weich / max(1.0, min(ry, rx))
    return np.clip((1.0 - d) / max(rand, 1e-3), 0.0, 1.0).astype(np.float32)


def _mischen(bild: np.ndarray, maske: np.ndarray, farbe) -> None:
    """Farbe (RGB-Tupel oder (h, w, 3)-Array) mit der Maske in das Bild mischen (in-place, float)."""
    m = maske[:, :, None]
    bild *= (1 - m)
    bild += m * np.asarray(farbe, np.float32)


def u8(a) -> np.ndarray:
    return np.clip(a, 0, 255).astype(np.uint8)


def grau(rgb: np.ndarray) -> np.ndarray:
    if rgb.ndim == 2:
        return rgb
    return u8(rgb[:, :, 0] * 0.299 + rgb[:, :, 1] * 0.587 + rgb[:, :, 2] * 0.114)


# ----------------------------------------------------------------------
# Fotos
# ----------------------------------------------------------------------
HAUTTOENE = ((224, 182, 158), (205, 160, 135), (176, 128, 98), (141, 96, 70), (102, 70, 52), (236, 200, 180))
HAARFARBEN = ((40, 28, 20), (95, 65, 40), (160, 120, 70), (200, 170, 110), (25, 25, 28), (130, 130, 130))
HINTERGRUENDE = ((215, 220, 228), (200, 205, 210), (232, 232, 232), (180, 200, 225), (225, 215, 200))


def portraet(rng, breite: int = 280, hoehe: int = 360) -> np.ndarray:
    """Passbild-artiges Porträt (RGB) aus Formen und Verläufen: heller Hintergrund mit Verlauf, Schultern, Hals,
    Kopf mit Schattierung, Haare, Augen, Brauen, Mund – mit Rauschen und leichter Unschärfe."""
    h, w = hoehe, breite
    y, x = np.mgrid[:h, :w].astype(np.float32)
    hg = np.asarray(HINTERGRUENDE[rng.integers(len(HINTERGRUENDE))], np.float32)
    bild = np.empty((h, w, 3), np.float32)
    bild[:] = hg
    bild *= (0.92 + 0.10 * (1 - y / h))[:, :, None]                       # Verlauf von oben nach unten
    bild += 6 * rauschfeld(rng, h, w, (48, 12), (1.0, 0.4))[:, :, None]
    haut = np.asarray(HAUTTOENE[rng.integers(len(HAUTTOENE))], np.float32)
    haar = np.asarray(HAARFARBEN[rng.integers(len(HAARFARBEN))], np.float32)
    kleid = rng.uniform(20, 200, 3).astype(np.float32)
    cx = w * rng.uniform(0.46, 0.54)
    kopf_ry, kopf_rx = h * rng.uniform(0.26, 0.31), w * rng.uniform(0.27, 0.33)
    kopf_cy = h * rng.uniform(0.40, 0.46)
    # Schultern und Kleidung (mit Falten aus Rauschen)
    schulter = _ellipse(h, w, h * 1.08, cx, h * 0.36, w * 0.62, 3)
    falten = rauschfeld(rng, h, w, (40, 10), (1.0, 0.5))
    _mischen(bild, schulter, kleid[None, None, :] * (0.85 + 0.25 * falten[:, :, None]))
    # Hals
    hals = np.clip(1 - np.abs(x - cx) / (w * 0.11), 0, 1) * (y > kopf_cy) * (y < h * 0.86)
    _mischen(bild, np.clip(hals * 4, 0, 1).astype(np.float32), haut * 0.85)
    # Haare hinter dem Kopf (etwas größer, oben)
    haare = _ellipse(h, w, kopf_cy - kopf_ry * 0.18, cx, kopf_ry * 1.12, kopf_rx * 1.12, 3)
    strähnen = rauschfeld(rng, h, w, (24, 6, 2), (0.6, 0.6, 0.4))
    _mischen(bild, haare, haar[None, None, :] * (0.8 + 0.35 * strähnen[:, :, None]))
    # Kopf mit Schattierung (heller in der Mitte, Seiten dunkler, leichtes Licht von links)
    kopf = _ellipse(h, w, kopf_cy, cx, kopf_ry, kopf_rx, 3)
    d = np.sqrt(((y - kopf_cy) / kopf_ry) ** 2 + ((x - cx) / kopf_rx) ** 2)
    licht = (1.08 - 0.30 * d ** 2 - 0.10 * (x - cx) / kopf_rx)[:, :, None]
    _mischen(bild, kopf, haut[None, None, :] * licht + 4 * rauschfeld(rng, h, w, (8, 3), (1, 0.5))[:, :, None])
    # Pony / Haaransatz
    pony = _ellipse(h, w, kopf_cy - kopf_ry * 0.95, cx, kopf_ry * 0.42, kopf_rx * 0.95, 3)
    _mischen(bild, pony, haar[None, None, :] * (0.8 + 0.3 * strähnen[:, :, None]))
    # Augen, Brauen, Nase, Mund
    for seite in (-1, 1):
        ax, ay = cx + seite * kopf_rx * 0.38, kopf_cy - kopf_ry * 0.08
        _mischen(bild, _ellipse(h, w, ay, ax, kopf_ry * 0.07, kopf_rx * 0.17, 1.5), (235, 235, 230))
        _mischen(bild, _ellipse(h, w, ay, ax, kopf_ry * 0.065, kopf_rx * 0.07, 1.2), (60, 45, 35))
        _mischen(bild, _ellipse(h, w, ay - kopf_ry * 0.17, ax, kopf_ry * 0.035, kopf_rx * 0.22, 1.5), haar * 0.8)
    nase = _ellipse(h, w, kopf_cy + kopf_ry * 0.18, cx + kopf_rx * 0.05, kopf_ry * 0.16, kopf_rx * 0.07, 2)
    _mischen(bild, nase * 0.35, haut * 0.75)
    mund = _ellipse(h, w, kopf_cy + kopf_ry * 0.50, cx, kopf_ry * 0.06, kopf_rx * 0.32, 1.5)
    _mischen(bild, mund, (160, 80, 75))
    bild = glaetten(bild.reshape(h, w * 3), 0).reshape(h, w, 3)
    for k in range(3):
        bild[:, :, k] = glaetten(bild[:, :, k], 1.0)
    bild += rng.normal(0, 3.0, bild.shape).astype(np.float32)
    return u8(bild)


def objektfoto(rng, breite: int = 640, hoehe: int = 480) -> np.ndarray:
    """Schadenfoto-artiges Bild: Himmel- bzw. Wandverlauf, strukturierter Boden, ein Körper mit Lack-Glanz und
    Rädern, eine Delle (dunkler Fleck) – Farbe, viele Zwischentöne."""
    h, w = hoehe, breite
    y, x = np.mgrid[:h, :w].astype(np.float32)
    oben = rng.uniform(120, 230, 3).astype(np.float32)
    unten = rng.uniform(60, 160, 3).astype(np.float32)
    t = (y / h)[:, :, None]
    bild = oben * (1 - t) + unten * t
    bild += 14 * rauschfeld(rng, h, w, (80, 20, 5), (1.0, 0.6, 0.3))[:, :, None]
    boden = (y > h * rng.uniform(0.55, 0.7)).astype(np.float32)
    boden = glaetten(boden, 2)
    asphalt = 90 + 30 * rauschfeld(rng, h, w, (30, 6, 2), (0.5, 0.7, 0.8))
    _mischen(bild, boden, np.repeat(asphalt[:, :, None], 3, axis=2))
    lack = rng.uniform(30, 220, 3).astype(np.float32)
    korper = _ellipse(h, w, h * 0.52, w * 0.5, h * 0.22, w * 0.40, 4)
    glanz = (1.0 + 0.45 * np.exp(-((y - h * 0.42) / (h * 0.05)) ** 2) - 0.25 * ((y - h * 0.52) / (h * 0.22)))
    _mischen(bild, korper, lack[None, None, :] * glanz[:, :, None] + 8 * rauschfeld(rng, h, w, (10,), (1,))[:, :, None])
    for rx in (0.27, 0.73):
        _mischen(bild, _ellipse(h, w, h * 0.70, w * rx, h * 0.10, h * 0.10, 2), (25, 25, 28))
        _mischen(bild, _ellipse(h, w, h * 0.70, w * rx, h * 0.045, h * 0.045, 2), (150, 150, 155))
    delle = _ellipse(h, w, h * rng.uniform(0.45, 0.55), w * rng.uniform(0.35, 0.65), h * 0.05, w * 0.07, 6)
    _mischen(bild, delle * 0.6, lack * 0.45)
    for k in range(3):
        bild[:, :, k] = glaetten(bild[:, :, k], 0.8)
    bild += rng.normal(0, 3.5, bild.shape).astype(np.float32)
    return u8(bild)


def dokumentfoto_hintergrund(rng, breite: int, hoehe: int) -> np.ndarray:
    """Tischplatte (Holzmaserung) für ein Handyfoto eines Briefs."""
    h, w = hoehe, breite
    y, x = np.mgrid[:h, :w].astype(np.float32)
    maserung = np.sin((x * 0.05 + 6 * rauschfeld(rng, h, w, (60, 15), (1, 0.4))) * 2.0)
    basis = np.asarray((150, 105, 70), np.float32)
    bild = basis[None, None, :] * (0.85 + 0.12 * maserung[:, :, None])
    bild += 10 * rauschfeld(rng, h, w, (20, 4), (1, 0.6))[:, :, None]
    return u8(bild)


# ----------------------------------------------------------------------
# Kein Foto: Logo, Stempel, Diagramm, Unterschrift
# ----------------------------------------------------------------------
def logo(rng, breite: int = 300, hoehe: int = 120, verlauf: bool = False) -> np.ndarray:
    """Firmenlogo aus Flächenfarben (Kreis, Balken, Schriftzug-Klötzchen); mit `verlauf` ein Farbverlauf im Kreis."""
    h, w = hoehe, breite
    bild = np.full((h, w, 3), 255, np.float32)
    farbe = rng.uniform(0, 200, 3).astype(np.float32)
    zweit = rng.uniform(0, 255, 3).astype(np.float32)
    kreis = _ellipse(h, w, h * 0.5, h * 0.5, h * 0.42, h * 0.42, 1.0)
    if verlauf:
        y, x = np.mgrid[:h, :w].astype(np.float32)
        t = np.clip(x / max(1.0, h), 0, 1)[:, :, None]
        _mischen(bild, kreis, farbe[None, None, :] * (1 - t) + zweit[None, None, :] * t)
    else:
        _mischen(bild, kreis, farbe)
    _mischen(bild, _ellipse(h, w, h * 0.5, h * 0.5, h * 0.22, h * 0.22, 1.0), (255, 255, 255))
    x0 = int(h * 1.05)
    for i in range(int(rng.integers(5, 9))):
        bw = int(rng.integers(w // 30, w // 14))
        bh = int(h * rng.uniform(0.35, 0.6))
        y0 = int(h * 0.5 - bh / 2)
        bild[y0:y0 + bh, x0:x0 + bw] = zweit if i % 3 == 0 else farbe
        x0 += bw + int(w * 0.02)
        if x0 > w - 10:
            break
    return u8(bild)


def stempel(rng, breite: int = 260, hoehe: int = 260) -> np.ndarray:
    """Rundstempel in einer Farbe (Ring, Innenring, Schriftzeichen als Striche), mit Fehlstellen der Farbe."""
    h, w = hoehe, breite
    bild = np.full((h, w, 3), 255, np.float32)
    tinte = np.asarray([(30, 50, 170), (190, 30, 40), (40, 40, 40)][rng.integers(3)], np.float32)
    y, x = np.mgrid[:h, :w].astype(np.float32)
    d = np.sqrt((y - h / 2) ** 2 + (x - w / 2) ** 2) / (min(h, w) / 2)
    ring = ((np.abs(d - 0.92) < 0.04) | (np.abs(d - 0.70) < 0.025)).astype(np.float32)
    winkel = np.arctan2(y - h / 2, x - w / 2)
    zeichen = ((np.abs(d - 0.81) < 0.06) & (np.sin(winkel * 38) > 0.35)).astype(np.float32)
    mitte = ((np.abs(y - h / 2) < h * 0.04) & (np.abs(x - w / 2) < w * 0.3) & (np.sin(x * 0.6) > -0.2))
    maske = np.clip(ring + zeichen + mitte.astype(np.float32), 0, 1)
    maske *= (rng.random((h, w)) > 0.12)                                   # Fehlstellen der Stempelfarbe
    maske = np.clip(glaetten(maske, 0.7) * 1.4, 0, 1)
    _mischen(bild, maske, tinte)
    return u8(bild)


def diagramm(rng, breite: int = 480, hoehe: int = 320) -> np.ndarray:
    """Balkendiagramm mit Achsen, Gitter und Flächenfarben."""
    h, w = hoehe, breite
    bild = np.full((h, w, 3), 255, np.float32)
    bild[int(h * 0.9), int(w * 0.08):] = 0
    bild[:int(h * 0.9), int(w * 0.08)] = 0
    for g in range(1, 5):
        bild[int(h * 0.9 * g / 5), int(w * 0.08):] = 200
    farben = [rng.uniform(0, 230, 3) for _ in range(3)]
    n = int(rng.integers(5, 9))
    for i in range(n):
        x0 = int(w * 0.12 + i * w * 0.85 / n)
        bw = int(w * 0.85 / n * 0.6)
        bh = int(h * 0.85 * rng.uniform(0.15, 0.95))
        bild[int(h * 0.9) - bh:int(h * 0.9), x0:x0 + bw] = farben[i % 3]
    return u8(bild)


def tabelle(rng, breite: int = 640, hoehe: int = 420) -> np.ndarray:
    """Tabelle mit getönter Kopfzeile, abwechselnd hinterlegten Zeilen, Gitterlinien und „Wörtern“ (kurze dunkle
    Balken in Schrifthöhe) – Flächenfarben und Schrift, kein Foto."""
    h, w = hoehe, breite
    bild = np.full((h, w, 3), 255, np.float32)
    zeilen = int(rng.integers(8, 14))
    zh = h // (zeilen + 1)
    kopf = rng.uniform(150, 215, 3).astype(np.float32)
    streifen = np.asarray([rng.uniform(228, 245)] * 3, np.float32)
    bild[:zh] = kopf
    for z in range(1, zeilen + 1):
        if z % 2 == 0:
            bild[z * zh:(z + 1) * zh] = streifen
    spalten = np.sort(rng.choice(np.arange(w // 8, w - w // 8), size=3, replace=False))
    for x in spalten:
        bild[:, x:x + 1] = 120
    for z in range(zeilen + 2):
        bild[min(h - 1, z * zh):min(h, z * zh + 1)] = 120
    for z in range(zeilen + 1):
        x = 6
        while x < w - 40:
            lw = int(rng.integers(12, 60))
            y0 = z * zh + zh // 3
            bild[y0:y0 + max(2, zh // 3), x:x + lw] = 30 if z else 255
            x += lw + int(rng.integers(6, 14))
    return u8(bild)


def _text_rendern(zeilen, breite_pt: float, hoehe_pt: float, groesse: float, schrift: str, dpi: float = 150,
                  abstand: float = 1.25) -> np.ndarray:
    doc = fitz.open()
    s = doc.new_page(width=breite_pt, height=hoehe_pt)
    y = groesse * 1.1
    for z in zeilen:
        s.insert_text((6, y), z, fontsize=groesse, fontname=schrift)
        y += groesse * abstand
    a = rendern(s, dpi)
    doc.close()
    return a


def ueberschrift_bild(rng) -> np.ndarray:
    """Große fette Überschrift (36-48 pt) in zwei Zeilen – breite Striche, kein Foto."""
    groesse = float(rng.choice([36, 42, 48]))
    return _text_rendern(["VERSICHERUNGSSCHEIN", "Nr. KH 2025 0047 11"], 495, 140, groesse, "hebo")


def textblock_bild(rng) -> np.ndarray:
    """Dichter Textblock (8 pt, eng gesetzt) – viele Mitteltöne bei geringer Auflösung, kein Foto."""
    zeilen = [z for z in BRIEFTEXT if z] * 3
    return _text_rendern(zeilen, 495, 480, 8.0, "helv", abstand=1.15)


def unterschrift(rng, breite: int = 400, hoehe: int = 140) -> np.ndarray:
    """Namenszug aus Kurvenzügen (dunkle Tinte auf weiß)."""
    h, w = hoehe, breite
    maske = np.zeros((h, w), np.float32)
    t = np.linspace(0, 1, 2000)
    xs = w * (0.05 + 0.9 * t)
    ys = h * (0.55 + 0.25 * np.sin(t * rng.uniform(12, 25)) * np.cos(t * rng.uniform(2, 5)))
    for xx, yy in zip(xs.astype(int), ys.astype(int)):
        maske[max(0, yy - 2):yy + 2, max(0, xx - 1):xx + 2] = 1
    maske = np.clip(glaetten(maske, 0.8) * 1.5, 0, 1)
    bild = np.full((h, w, 3), 255, np.float32)
    _mischen(bild, maske, (20, 25, 80))
    return u8(bild)


# ----------------------------------------------------------------------
# PDF-Bausteine (PyMuPDF): Bild einfügen, Seite rendern
# ----------------------------------------------------------------------
def pixmap(a: np.ndarray):
    a = np.ascontiguousarray(a)
    if a.ndim == 2:
        return fitz.Pixmap(fitz.csGRAY, a.shape[1], a.shape[0], a.tobytes(), False)
    return fitz.Pixmap(fitz.csRGB, a.shape[1], a.shape[0], a.tobytes(), False)


def jpeg(a: np.ndarray, qualitaet: int = 85) -> bytes:
    return pixmap(a).tobytes("jpeg", jpg_quality=int(qualitaet))


def png(a: np.ndarray) -> bytes:
    return pixmap(a).tobytes("png")


def rendern(seite, dpi: float, grau_: bool = False) -> np.ndarray:
    pix = seite.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY if grau_ else fitz.csRGB, alpha=False)
    a = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
    return a[:, :, 0].copy() if grau_ else a.copy()


VORNAMEN = ("ERIKA", "MAX", "JONAS", "LEA", "MARIA", "TOBIAS", "SOPHIE", "AHMET")
NACHNAMEN = ("MUSTERMANN", "MUSTERFRAU", "BEISPIEL", "MODELL", "PROBE", "SCHABLONE", "VORLAGE")


def _mrz_zeile(text: str, laenge: int) -> str:
    return (text + "<" * laenge)[:laenge]


def ausweis_karte(rng, art: str = "personalausweis", seite: str = "vorn", foto=None, mit_text: bool = True):
    """Ausweis als kleines PDF (Kartenformat, Vektortext + Hintergrund- und Lichtbild) – zum Rendern oder Einbetten.

    art: "personalausweis" | "reisepass" | "fuehrerschein" | "aufenthaltstitel"; seite: "vorn" | "hinten".
    Rückgabe: (fitz.Document mit einer Seite, Lichtbild-Rechteck in Kartenkoordinaten (pt) oder None)."""
    if art == "reisepass":
        bw, bh = 125 * MM, 88 * MM
    else:
        bw, bh = 85.6 * MM, 54 * MM
    doc = fitz.open()
    s = doc.new_page(width=bw, height=bh)
    # Sicherheitsuntergrund: Pastellverlauf mit feinen Guillochen
    hw, hh = int(bw * 4), int(bh * 4)
    y, x = np.mgrid[:hh, :hw].astype(np.float32)
    basis = np.asarray([(214, 228, 222), (226, 214, 232), (232, 226, 206), (210, 224, 238)][rng.integers(4)],
                       np.float32)
    welle = (np.sin(x * 0.11 + 4 * np.sin(y * 0.035)) * np.sin(y * 0.09 + 3 * np.sin(x * 0.02)))
    unter = basis[None, None, :] + 10 * welle[:, :, None] + 6 * (x / hw)[:, :, None]
    s.insert_image(s.rect, stream=png(u8(unter)))
    titel = {"personalausweis": ("BUNDESREPUBLIK DEUTSCHLAND", "PERSONALAUSWEIS / IDENTITY CARD"),
             "reisepass": ("BUNDESREPUBLIK DEUTSCHLAND", "REISEPASS / PASSPORT"),
             "fuehrerschein": ("FÜHRERSCHEIN", "Bundesrepublik Deutschland"),
             "aufenthaltstitel": ("AUFENTHALTSTITEL", "RESIDENCE PERMIT")}[art]
    vorname = VORNAMEN[rng.integers(len(VORNAMEN))]
    nachname = NACHNAMEN[rng.integers(len(NACHNAMEN))]
    lichtbild = None
    if seite == "vorn":
        fb = bw * (0.30 if art != "reisepass" else 0.29)
        fh = fb * 1.28
        lichtbild = fitz.Rect(bw * 0.05, bh * 0.24, bw * 0.05 + fb, bh * 0.24 + fh)
        bild = portraet(rng) if foto is None else foto
        s.insert_image(lichtbild, stream=jpeg(bild, 90), keep_proportion=False)
        if mit_text:
            s.insert_text((bw * 0.05, bh * 0.10), titel[0], fontsize=5.5, fontname="hebo", color=(0.1, 0.2, 0.3))
            s.insert_text((bw * 0.05, bh * 0.18), titel[1], fontsize=5.0, fontname="helv", color=(0.1, 0.2, 0.3))
            x0 = lichtbild.x1 + bw * 0.05
            y0 = bh * 0.32
            felder = (("Name / Surname", nachname), ("Vornamen / Given names", vorname),
                      ("Geburtstag / Date of birth", f"{rng.integers(1, 28):02d}.{rng.integers(1, 12):02d}."
                                                     f"{rng.integers(1950, 2005)}"),
                      ("Staatsangehörigkeit / Nationality", "DEUTSCH"),
                      ("Gültig bis / Date of expiry", f"{rng.integers(1, 28):02d}.{rng.integers(1, 12):02d}."
                                                      f"{rng.integers(2027, 2035)}"))
            for etikett, wert in felder:
                s.insert_text((x0, y0), etikett, fontsize=3.2, fontname="helv", color=(0.25, 0.25, 0.3))
                s.insert_text((x0, y0 + 6.2), wert, fontsize=6.0, fontname="hebo", color=(0.05, 0.05, 0.1))
                y0 += 13.5
            s.insert_text((bw * 0.70, bh * 0.10), f"T{rng.integers(10**7, 10**8 - 1)}", fontsize=6.5,
                          fontname="cobo", color=(0.6, 0.1, 0.1))
        if art == "reisepass" and mit_text:
            z1 = _mrz_zeile(f"P<D<<{nachname}<<{vorname}", 44)
            z2 = _mrz_zeile(f"C01X00T47{rng.integers(0, 9)}D<<6408125F2702283", 43) + "4"
            for k, z in enumerate((z1, z2)):
                s.insert_text((bw * 0.04, bh * (0.86 + 0.07 * k)), z, fontsize=7.4, fontname="cour")
    else:
        if mit_text:
            s.insert_text((bw * 0.05, bh * 0.14), "Anschrift / Address", fontsize=3.2, fontname="helv")
            s.insert_text((bw * 0.05, bh * 0.22), "MUSTERSTRASSE 12, 51147 KÖLN", fontsize=5.5, fontname="hebo")
            s.insert_text((bw * 0.05, bh * 0.34), "Augenfarbe / Colour of eyes  GRÜN    Größe / Height 168 cm",
                          fontsize=3.8, fontname="helv")
            z = (_mrz_zeile(f"IDD<<T22000129{rng.integers(0, 9)}", 30),
                 _mrz_zeile("6408125<2010315D", 29) + str(rng.integers(0, 9)),
                 _mrz_zeile(f"{nachname}<<{vorname}", 30))
            for k, zeile in enumerate(z):
                s.insert_text((bw * 0.05, bh * (0.66 + 0.12 * k)), zeile, fontsize=7.6, fontname="cour")
    return doc, lichtbild


def karte_rendern(rng, art="personalausweis", seite="vorn", dpi=300, foto=None, mit_text=True):
    """Ausweis als Rasterbild (RGB) und Lichtbild-Rechteck in Bildpixeln (oder None)."""
    doc, lichtbild = ausweis_karte(rng, art, seite, foto, mit_text)
    bild = rendern(doc[0], dpi)
    doc.close()
    if lichtbild is not None:
        f = dpi / 72
        lichtbild = (lichtbild.x0 * f, lichtbild.y0 * f, lichtbild.x1 * f, lichtbild.y1 * f)
    return bild, lichtbild


BRIEFTEXT = ["Beispiel Versicherung AG · Leistungsabteilung · Postfach 10 20 30 · 50667 Köln", "",
             "Frau", "Erika Musterfrau", "Lindenallee 7", "50667 Köln", "",
             "Ihre Schadenmeldung vom 14.02.2025 – Vertrag KH-2025-004711", "",
             "Sehr geehrte Frau Musterfrau,",
             "wir bestätigen den Eingang Ihrer Unterlagen. Die Prüfung dauert in der Regel zwei",
             "bis drei Wochen. Bitte senden Sie uns noch die fehlenden Belege zu und nennen Sie",
             "uns eine Bankverbindung für die Erstattung. Rückfragen bitte telefonisch unter",
             "0221 123456-78 oder per E-Mail an leistung@beispiel-versicherung.example.", "",
             "Für Ihre Unterlagen halten wir fest: Der Schaden wurde am 12.02.2025 gemeldet und",
             "wird unter der oben genannten Nummer geführt. Die Begutachtung erfolgt durch",
             "einen unabhängigen Sachverständigen, der sich in den nächsten Tagen meldet.", "",
             "Mit freundlichen Grüßen", "", "Sabine Krüger", "Kundenservice"]


def textseite(doc, zeilen=BRIEFTEXT, y0=70.0, abstand=15.5, groesse=10.5, x0=60.0, breite=A4[0], hoehe=A4[1]):
    """Neue Textseite (Textebene) mit den Zeilen; liefert die Seite."""
    s = doc.new_page(width=breite, height=hoehe)
    y = y0
    for z in zeilen:
        if z:
            s.insert_text((x0, y), z, fontsize=groesse, fontname="helv")
        y += abstand
    return s


def textseite_bild(rng, zeilen=BRIEFTEXT, dpi=200, grau_=True, papier=250):
    """Gerenderte Textseite (A4) als Rasterbild – Grundlage eines Scans."""
    doc = fitz.open()
    s = textseite(doc, zeilen)
    a = rendern(s, dpi, grau_)
    doc.close()
    if papier < 255:
        a = u8(a.astype(np.float32) * (papier / 255.0))
    return a


def scan_effekte(rng, a: np.ndarray, rauschen: float = 5.0, unschaerfe: float = 0.6, helligkeit=(0.95, 1.0),
                 verlauf: float = 0.0) -> np.ndarray:
    """Scanner-Spuren: Unschärfe, Rauschen, ungleichmäßige Ausleuchtung."""
    b = a.astype(np.float32)
    if unschaerfe > 0.3:
        if b.ndim == 2:
            b = glaetten(b, unschaerfe)
        else:
            for k in range(b.shape[2]):
                b[:, :, k] = glaetten(b[:, :, k], unschaerfe)
    if verlauf:
        h, w = b.shape[:2]
        g = (1.0 - verlauf * np.linspace(0, 1, w, dtype=np.float32))[None, :]
        b = b * (g if b.ndim == 2 else g[:, :, None])
    b *= rng.uniform(*helligkeit)
    if rauschen > 0:
        b += rng.normal(0, rauschen, b.shape).astype(np.float32)
    return u8(b)


def scan_pdf(pfad, seiten: list, dpi: float = 200, qualitaet: int = 75, groesse=A4, als_png: bool = False) -> None:
    """PDF, dessen Seiten je EIN Bild sind (Scan); seiten: Rasterbilder (Seitengröße `groesse` in pt)."""
    doc = fitz.open()
    for a in seiten:
        s = doc.new_page(width=groesse[0], height=groesse[1])
        s.insert_image(s.rect, stream=png(a) if als_png else jpeg(a, qualitaet), keep_proportion=False)
    doc.save(pfad, garbage=3, deflate=True)
    doc.close()


def seite_komponieren(rng, teile: list, dpi: float = 200, grau_: bool = False, schraeg: float = 0.0,
                      text: list | None = None, groesse=A4):
    """A4-Seite aus Rasterbildern zusammensetzen und als Scan rendern: teile = [(Bild, Rechteck in pt)].
    Liefert (Rasterbild der Seite, [Rechtecke der Teile in pt, nach der Schräglage als Hülle])."""
    doc = fitz.open()
    s = doc.new_page(width=groesse[0], height=groesse[1])
    if text:
        y = 70.0
        for z in text:
            if z:
                s.insert_text((60, y), z, fontsize=10.5, fontname="helv")
            y += 15.5
    for bild, rect in teile:
        s.insert_image(fitz.Rect(rect), stream=png(bild), keep_proportion=False)
    rechtecke = [fitz.Rect(r) for _, r in teile]
    if abs(schraeg) > 0.01:
        ziel = fitz.open()
        z = ziel.new_page(width=groesse[0], height=groesse[1])
        z.show_pdf_page(z.rect, doc, 0, rotate=schraeg)
        # Hülle der gedrehten Rechtecke (Drehung um die Seitenmitte, show_pdf_page dreht gegen den Uhrzeigersinn)
        mitte = fitz.Point(groesse[0] / 2, groesse[1] / 2)
        m = fitz.Matrix(1, 1).prerotate(-schraeg)
        neu = []
        for r in rechtecke:
            punkte = [(p - mitte) * m + mitte for p in (r.tl, r.tr, r.bl, r.br)]
            neu.append(fitz.Rect(min(p.x for p in punkte), min(p.y for p in punkte),
                                 max(p.x for p in punkte), max(p.y for p in punkte)))
        rechtecke = neu
        a = rendern(z, dpi, grau_)
        ziel.close()
    else:
        a = rendern(s, dpi, grau_)
    doc.close()
    return a, rechtecke


def dither(a: np.ndarray) -> np.ndarray:
    """Schwarzweiß mit geordneter Rasterung (wie ein 1-Bit-Kopierer, der Fotos rastert)."""
    g = grau(a).astype(np.float32)
    bayer = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], np.float32) / 16.0 * 255
    h, w = g.shape
    schwelle = np.tile(bayer, (h // 4 + 1, w // 4 + 1))[:h, :w]
    return np.where(g > schwelle, 255, 0).astype(np.uint8)


def drehen(a: np.ndarray, grad: float, fuellung=255) -> np.ndarray:
    """Bild um seine Mitte drehen (nächster Nachbar, gleiche Größe)."""
    h, w = a.shape[:2]
    t = math.radians(grad)
    yy, xx = np.mgrid[:h, :w].astype(np.float32)
    cy, cx = h / 2, w / 2
    xs = (xx - cx) * math.cos(t) + (yy - cy) * math.sin(t) + cx
    ys = -(xx - cx) * math.sin(t) + (yy - cy) * math.cos(t) + cy
    xi, yi = np.round(xs).astype(int), np.round(ys).astype(int)
    gueltig = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
    aus = np.full_like(a, fuellung)
    aus[gueltig] = a[yi[gueltig], xi[gueltig]]
    return aus
