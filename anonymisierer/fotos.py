"""Fotobereiche erkennen: Halbtonflächen (Fotos, Lichtbilder) gegenüber Text, Strichgrafik, Logos und Stempeln.

Ein Foto unterscheidet sich von allem anderen auf einer Dokumentseite durch seine Halbtöne: eine zusammenhängende,
nicht papierhelle Fläche mit vielen, stetig verteilten Grauwerten und Struktur (Haut, Haare, Stoff, Lack, Himmel).
Text, Linien, Unterschriften und Stempel sind dünne Striche auf Papier, Logos, Diagramme und Tabellen wenige
gleichmäßige Farbflächen, Kartenhintergründe von Ausweisen blasse, gleichmäßige Flächen. Die Erkennung arbeitet ohne
zusätzliche Pakete auf einem Graustufenbild der Seite (PyMuPDF und numpy – numpy kommt mit spaCy und PyMuPDF 2.x und
liegt auch in der EXE):

  1. Seite (bzw. Ausschnitt) mit FOTO_DPI in Graustufen rendern (nie feiner, Riesenseiten gröber), 3 x 3 glätten
     (Scanrauschen, JPEG-Artefakte); Schwarzweiß-Scans (gerasterte Fotos) stärker glätten.
  2. Dunkle Striche bis STRICH_MM Breite entfernen (Graustufen-Schließen): Schrift, Linien, Stempel und
     Unterschriften verschwinden im Untergrund, Fotos bleiben.
  3. Zellen von ZELLE_MM: deutlich dunkler als das Papier = Inhalt; zusammenhängende Inhaltszellen bilden Flächen.
  4. Je Fläche: Ist sie überwiegend EIN heller Farbton (Ausweiskarte, getöntes Feld), zählt nur, was sich davon
     abhebt (das Lichtbild auf der Karte); die Fläche selbst wird als „Karte“ vermerkt.
  5. Eine Fläche ist ein Foto, wenn ihre Zellen viele stetig verteilte Helligkeiten tragen (Tonumfang, besetzte
     Stufen – keine wenigen Flächenfarben wie bei Logos und Diagrammen) und das geglättete Bild darin Struktur hat
     (ein Verlauf oder eine Schattenkante auf Papier hat keine). Dazu Mindestgröße, Lage (schmale Streifen am
     Seitenrand sind Scannerränder) und Text-Veto (wo die OCR viele lesbare Wörter gelesen hat, ist Text).

Öffentliche Schnittstelle:
    fotobereiche(seite, clip=None, woerter=None, dpi=None) -> list[Fotobereich]   (Seitenkoordinaten)
    fotobereiche_im_bild(grau, px_je_mm, woerter_px=None) -> list[Fotobereich]    (Pixel eines Graustufenbilds)
    verfuegbar() -> bool                                                          numpy vorhanden
Fotobereich(rect, karte, hochformat): rect = Fotobereich (mit Sicherheitsrand), karte = umgebende einfarbige Fläche
(Ausweiskarte) oder None, hochformat = Höhe/Breite passt zu einem Passbild.
"""

from __future__ import annotations

import re
from typing import NamedTuple

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen kennen nur den Namen "fitz"
    import fitz

from . import bilder as _bilder

FOTO_DPI = 100               # Analyseauflösung: ein Lichtbild (25 x 32 mm) hat rund 100 x 125 Pixel
FOTO_MAX_PIXEL = 3_000_000    # höchstens so viele Pixel je Analyse (Riesenseiten werden gröber gelesen)
ZELLE_MM = 2.0                # Kantenlänge einer Zelle
STRICH_MM = 1.2               # dunkle Striche bis zu dieser Breite (Schrift bis ~20 pt fett, Linien, Stempel,
                              # Unterschriften) werden vor der Zellprüfung entfernt
PAPIER_ABSTAND = 14           # Zelle mit Inhalt: ihr Median (nach dem Schließen) liegt so weit unter dem Papierweiß
# Fläche mit einem vorherrschenden hellen Farbton (Ausweiskarte, getöntes Feld): es zählt nur, was sich abhebt
GRUND_ANTEIL = 0.40           # so viele Zellen der Fläche liegen beim häufigsten Farbton (± GRUND_TOLERANZ) …
GRUND_TOLERANZ = 8
GRUND_MAX_ABSTAND = 70        # … der höchstens so weit unter dem Papierweiß liegt (helle Fläche)
GRUND_ABHEBUNG = 18           # abgehoben ist eine Zelle, deren Median so weit vom Grundton abweicht
# Fotofläche:
BEREICH_MIN_MM = 7.0          # kleinere Flächen zeigen kein erkennbares Gesicht (Lichtbilder sind >= 20 mm breit,
                              # auf einer verkleinerten Ausweiskopie >= 10 mm)
BEREICH_MIN_ZELLEN = 3        # bei sehr groben Analysen (Riesenseiten): mindestens 3 Zellen je Richtung
BEREICH_MAX_SEITENVERHAELTNIS = 5.0   # schmalere Streifen sind Scannerränder, Schatten, Trennlinien
RAND_STREIFEN = 0.10          # Fläche am Rand des Bilds, schmaler als 10 % davon: Scannerrand/Schatten
TON_MIN_UMFANG = 16           # 10.-90. Perzentil der Zellhelligkeiten: Fotos haben Schatten und Lichter
KANTE = 20                    # Zelle mit Kante: 10.-90. Perzentil ihrer Pixel (geschlossenes Bild) liegt so weit auseinander
GLATT_MIN = 0.15              # so viele ruhige Zellen (ohne Kante) hat ein Foto mindestens (Hintergrund, Haut, Himmel)
TON_UMFANG_KANTIG = 40        # eine kontrastarme Fläche (Umfang darunter) ist nur dann ein Foto, wenn sie überwiegend
GLATT_KONTRASTARM = 0.5       # ruhig ist (blasses Foto) – dichte Schrift in Tabellen ist kontrastarm UND kantig
FLAECHENFARBEN = 3            # die häufigsten Helligkeiten der ruhigen Zellen einer Fläche …
FLAECHENFARBEN_TOLERANZ = 5   # … (± so viel) …
FLAECHENFARBEN_ANTEIL = 0.97  # … decken bei Logos, Balken, Stempeln, Schrift (fast) alle ruhigen Zellen ab – bei
                              # Fotos weniger (Verläufe, Schattierung)
INNENKANTEN_MIN = 3           # Kanten-Zellen im Inneren: Verläufe und Schatten auf Papier haben keine
EBENE_MAX = 0.93              # erklärt eine schiefe Ebene die ruhigen Zellen fast ganz, ist es ein Verlauf (Logo)
BEREICH_MAX_WORTANTEIL = 0.30  # deckt die OCR mehr als 30 % der Fläche mit lesbaren Wörtern ab, ist es Text
BEREICH_RAND_MM = 1.0         # Sicherheitsrand um jeden Bereich …
BEREICH_RAND_ANTEIL = (0.02, 0.02, 0.02)     # … zuzüglich 2 % seiner Höhe/Breite (oben, seitlich, unten) …
BEREICH_RAND_PORTRAET = (0.10, 0.06, 0.03)   # … bei Passbildern mehr: Hintergrund über dem Kopf und neben ihm
BEREICH_MAX_RAND_MM = 4.0     # … höchstens so viel
LOCH_MIN_ANTEIL = 0.10        # umschließt eine Fotofläche ein so großes helles Loch (fotografiertes Blatt auf einer
                              # Tischplatte), wird nur die Fläche selbst abgedeckt, das Blatt bleibt frei
HOCHFORMAT = (1.10, 1.75)     # Höhe/Breite eines Passbilds (35 x 45 mm: 1,29) samt Schwankung der Erkennung
ZUSAMMENFASSEN_UEBERLAPPUNG = 0.2   # Fotobereiche verschmelzen, wenn sie sich so weit überlappen (Anteil des kleineren)
CLIP_RAND_MM = 6.0            # Umgebung eines Ausschnitts (eingebettetes Bild), die für das Papierweiß mitgelesen wird

_WORT_RE = re.compile(r"[^\W_]{3,}")


class Fotobereich(NamedTuple):
    rect: object              # fitz.Rect (Seitenkoordinaten) bzw. (x0, y0, x1, y1) in Pixeln
    karte: object             # umgebende einfarbige Fläche (Ausweiskarte) oder None
    hochformat: bool          # Seitenverhältnis eines Passbilds


def _numpy():
    try:
        import numpy
        return numpy
    except Exception:          # numpy fehlt (kommt sonst mit PyMuPDF 2.x und spaCy): keine Fotoerkennung
        return None


def verfuegbar() -> bool:
    """Kann die Fotoerkennung laufen (numpy vorhanden)?"""
    return _numpy() is not None


# ----------------------------------------------------------------------
# Rendern
# ----------------------------------------------------------------------
def analyse_dpi(rect, dpi: float = FOTO_DPI, max_pixel: int = FOTO_MAX_PIXEL) -> float:
    """Auflösung der Analyse für ein Rechteck (pt): FOTO_DPI, bei Riesenseiten so weit weniger, dass höchstens
    max_pixel Pixel entstehen."""
    flaeche = max(1.0, abs(fitz.Rect(rect)))
    grenze = 72.0 * (max_pixel / flaeche) ** 0.5
    return max(4.0, min(float(dpi), grenze))


def grau_rendern(seite, clip=None, dpi: float | None = None):
    """(Graustufen-Array, (x0, y0, pt je Pixel)) der Seite bzw. des Ausschnitts; (None, None) ohne numpy."""
    np = _numpy()
    if np is None:
        return None, None
    bereich = fitz.Rect(clip) & seite.rect if clip is not None else fitz.Rect(seite.rect)
    if bereich.is_empty or bereich.is_infinite:
        return None, None
    dpi = analyse_dpi(bereich) if dpi is None else dpi
    faktor = dpi / 72.0
    pix = seite.get_pixmap(matrix=fitz.Matrix(faktor, faktor), clip=bereich, colorspace=fitz.csGRAY, alpha=False,
                           annots=False)
    if pix.width < 4 or pix.height < 4:
        return None, None
    a = np.frombuffer(pix.samples_mv, dtype=np.uint8).reshape(pix.height, pix.stride)[:, :pix.width].copy()
    del pix
    return a, (bereich.x0, bereich.y0, 1.0 / faktor)


# ----------------------------------------------------------------------
# Bildoperationen (numpy, ohne weitere Pakete)
# ----------------------------------------------------------------------
def _kasten(np, a, r: int):
    """Mittelwert über (2r+1) x (2r+1), Ränder wiederholt (über kumulierte Summen, float32)."""
    if r <= 0:
        return a.astype(np.float32)
    aus = a.astype(np.float32)
    for achse in (0, 1):
        breite = [(0, 0), (0, 0)]
        breite[achse] = (r + 1, r)
        p = np.pad(aus, breite, mode="edge")
        c = np.cumsum(p, axis=achse, dtype=np.float64)
        n = aus.shape[achse]
        if achse == 0:
            aus = ((c[2 * r + 1:2 * r + 1 + n] - c[:n]) / (2 * r + 1)).astype(np.float32)
        else:
            aus = ((c[:, 2 * r + 1:2 * r + 1 + n] - c[:, :n]) / (2 * r + 1)).astype(np.float32)
    return aus


def _filter_max_min(np, a, k: int, funktion, fuellung):
    """Maximum bzw. Minimum über k x k (getrennt nach Zeilen und Spalten)."""
    r = k // 2
    h, w = a.shape
    p = np.pad(a, ((0, 0), (r, r)), mode="constant", constant_values=fuellung)
    aus = p[:, 0:w].copy()
    for dx in range(1, k):
        funktion(aus, p[:, dx:dx + w], out=aus)
    p = np.pad(aus, ((r, r), (0, 0)), mode="constant", constant_values=fuellung)
    aus2 = p[0:h].copy()
    for dy in range(1, k):
        funktion(aus2, p[dy:dy + h], out=aus2)
    return aus2


def _schliessen(np, g, k: int):
    """Graustufen-Schließen (erst Maximum, dann Minimum über k x k): dunkle Striche schmaler als k Pixel – Schrift,
    Linien, Stempel, Unterschriften – verschwinden im Untergrund; breite dunkle Flächen (Fotos) bleiben."""
    return _filter_max_min(np, _filter_max_min(np, g, k, np.maximum, -1.0), k, np.minimum, 256.0)


def _zellen(np, a, z: int):
    """Array (hb, wb, z*z) der Zellen (Rest am Rand fällt weg)."""
    hb, wb = a.shape[0] // z, a.shape[1] // z
    return a[:hb * z, :wb * z].reshape(hb, z, wb, z).transpose(0, 2, 1, 3).reshape(hb, wb, z * z)


def _komponenten(np, m, acht: bool = True) -> list:
    """Zusammenhängende Zellgruppen: [(y0, x0, y1, x1, Maske im Hüllrechteck)] (y1/x1 exklusiv)."""
    hb, wb = m.shape
    gesehen = np.zeros(m.shape, dtype=bool)
    nachbarn = ((-1, 0), (1, 0), (0, -1), (0, 1)) + (((-1, -1), (-1, 1), (1, -1), (1, 1)) if acht else ())
    aus = []
    ys, xs = np.nonzero(m)
    for y, x in zip(ys.tolist(), xs.tolist()):
        if gesehen[y, x]:
            continue
        stapel = [(y, x)]
        gesehen[y, x] = True
        punkte = []
        while stapel:
            cy, cx = stapel.pop()
            punkte.append((cy, cx))
            for dy, dx in nachbarn:
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < hb and 0 <= nx < wb and m[ny, nx] and not gesehen[ny, nx]:
                    gesehen[ny, nx] = True
                    stapel.append((ny, nx))
        py = np.fromiter((p[0] for p in punkte), dtype=np.int64, count=len(punkte))
        px = np.fromiter((p[1] for p in punkte), dtype=np.int64, count=len(punkte))
        y0, y1, x0, x1 = int(py.min()), int(py.max()) + 1, int(px.min()), int(px.max()) + 1
        maske = np.zeros((y1 - y0, x1 - x0), dtype=bool)
        maske[py - y0, px - x0] = True
        aus.append((y0, x0, y1, x1, maske))
    return aus


def _vereinigen(rechtecke: list, mindestanteil: float = 0.0) -> list:
    """Sich überlappende Rechtecke zusammenfassen (wiederholt, bis nichts mehr zusammenwächst); mit mindestanteil nur,
    wenn die Überlappung so viel der Fläche des kleineren ausmacht."""
    def flaeche(r):
        return max(0, r[2] - r[0]) * max(0, r[3] - r[1])
    rs = [list(r) for r in rechtecke]
    geaendert = True
    while geaendert:
        geaendert = False
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                a, b = rs[i], rs[j]
                schnitt = (max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1])))
                if schnitt > 0 and schnitt >= mindestanteil * min(flaeche(a), flaeche(b)):
                    rs[i] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                    del rs[j]
                    geaendert = True
                    break
            if geaendert:
                break
    return [tuple(r) for r in rs]


# ----------------------------------------------------------------------
# Kern: Fotobereiche in einem Graustufenbild
# ----------------------------------------------------------------------
def _flaechenfarben(np, werte) -> float:
    """Anteil der Zellen, die auf den FLAECHENFARBEN häufigsten Helligkeiten (± Toleranz) liegen."""
    gerundet = np.round(werte).astype(np.int64)
    abgedeckt = np.zeros(gerundet.size, dtype=bool)
    for _ in range(FLAECHENFARBEN):
        offen = gerundet[~abgedeckt]
        if not offen.size:
            break
        w_, n_ = np.unique(offen, return_counts=True)
        # häufigster Wert mit Nachbarn (Fenster ± Toleranz), nicht nur der exakte Wert
        fenster = np.convolve(np.bincount(offen - w_.min(), minlength=w_.max() - w_.min() + 1).astype(np.float64),
                              np.ones(2 * FLAECHENFARBEN_TOLERANZ + 1), mode="same")
        haeufig = int(np.argmax(fenster)) + int(w_.min())
        abgedeckt |= np.abs(gerundet - haeufig) <= FLAECHENFARBEN_TOLERANZ
    return float(abgedeckt.mean())


def merkmale(np, medianen, spannen, innen, ys=None, xs=None) -> dict:
    """Kennzahlen einer Fläche aus ihren Zellen (geschlossenes Bild): medianen/spannen je Zelle, innen = Zelle liegt
    nicht am Rand der Fläche.
      umfang:          10.-90. Perzentil der Zell-Medianen (Schatten und Lichter eines Fotos)
      glatt:           Anteil der Zellen ohne Kante (Spanne < KANTE) – Fotos haben ruhige Flächen (Hintergrund, Haut)
      flaechenfarben:  Anteil der ruhigen Zellen auf den häufigsten Helligkeiten – Logos, Balken, Stempel, Schrift:
                       wenige feste Töne; Fotos: Verläufe
      innenkanten:     Anteil der Kanten-Zellen im Inneren – ein Verlauf oder Schatten hat keine, ein Foto schon"""
    q10, q90 = np.percentile(medianen, (10, 90))
    glatt = spannen < KANTE
    m = {"umfang": float(q90 - q10), "glatt": float(glatt.mean()), "glatt_zellen": int(glatt.sum()),
         "flaechenfarben": _flaechenfarben(np, medianen[glatt]) if glatt.sum() >= 4 else 1.0,
         "innenkanten": float((~glatt & innen).sum() / max(1, innen.sum())),
         "innenkanten_zahl": int((~glatt & innen).sum()), "ebene": 0.0}
    if ys is not None and glatt.sum() >= 8:
        # Wie gut erklärt eine schiefe Ebene (Verlauf) die Helligkeit der ruhigen Zellen? Verlaufslogo: fast ganz
        a = np.stack([np.ones(int(glatt.sum())), ys[glatt].astype(np.float64), xs[glatt].astype(np.float64)], axis=1)
        b = medianen[glatt].astype(np.float64)
        koeff, *_ = np.linalg.lstsq(a, b, rcond=None)
        rest = b - a @ koeff
        varianz = float(b.var())
        m["ebene"] = float(1.0 - rest.var() / varianz) if varianz > 1e-6 else 1.0
    return m


def _ist_foto(m: dict) -> bool:
    return (m["umfang"] >= TON_MIN_UMFANG and m["glatt"] >= GLATT_MIN and m["glatt_zellen"] >= 4
            and (m["umfang"] >= TON_UMFANG_KANTIG or m["glatt"] >= GLATT_KONTRASTARM)
            and m["flaechenfarben"] < FLAECHENFARBEN_ANTEIL and m["innenkanten_zahl"] >= INNENKANTEN_MIN
            and m["ebene"] < EBENE_MAX)


def _hochformat(breite: float, hoehe: float) -> bool:
    return breite > 0 and HOCHFORMAT[0] <= hoehe / breite <= HOCHFORMAT[1]


def _rechtecke_aus_maske(maske) -> list:
    """Zellmaske in wenige Rechtecke zerlegen (Zeilenläufe, senkrecht gleiche Läufe zusammengefasst):
    [(y0, x0, y1, x1)] relativ zur Maske (y1/x1 exklusiv)."""
    aus = []
    offen: dict = {}                       # (x0, x1) -> y0 des laufenden Rechtecks
    for y in range(maske.shape[0] + 1):
        laeufe = set()
        if y < maske.shape[0]:
            zeile = maske[y].tolist()
            x = 0
            while x < len(zeile):
                if zeile[x]:
                    x0 = x
                    while x < len(zeile) and zeile[x]:
                        x += 1
                    laeufe.add((x0, x))
                else:
                    x += 1
        for lauf in list(offen):
            if lauf not in laeufe:
                aus.append((offen.pop(lauf), lauf[0], y, lauf[1]))
        for lauf in laeufe:
            offen.setdefault(lauf, y)
    return aus


def _ausdehnen(maske, schritte: int):
    """Zellmaske um `schritte` Zellen ausdehnen (8er-Nachbarschaft)."""
    m = maske.copy()
    for _ in range(schritte):
        n = m.copy()
        n[1:] |= m[:-1]
        n[:-1] |= m[1:]
        n[:, 1:] |= m[:, :-1]
        n[:, :-1] |= m[:, 1:]
        m = n
    return m


def _grosses_loch(np, maske) -> bool:
    """Umschließt die Fläche ein großes Loch (zusammenhängende Nicht-Inhalt-Zellen, die den Rand des Hüllrechtecks nicht
    berühren, mindestens LOCH_MIN_ANTEIL des Hüllrechtecks)? Buchten am Rand (heller Passbild-Hintergrund neben dem
    Kopf) zählen nicht."""
    h, w = maske.shape
    mindest = max(9, LOCH_MIN_ANTEIL * h * w)
    if (~maske).sum() < mindest:
        return False
    for y0, x0, y1, x1, loch in _komponenten(np, ~maske, acht=False):
        if y0 > 0 and x0 > 0 and y1 < h and x1 < w and loch.sum() >= mindest:
            return True
    return False


def fotobereiche_im_bild(grau, px_je_mm: float = FOTO_DPI / 25.4, woerter_px=None, protokoll=None,
                         papier: float | None = None) -> list:
    """Fotobereiche in einem Graustufenbild (uint8-Array): [Fotobereich] mit Rechtecken (x0, y0, x1, y1) in Pixeln.

    woerter_px: OCR-Wörter [(x0, y0, x1, y1, Text)] in Pixeln dieses Bilds – Flächen, die überwiegend aus lesbaren
    Wörtern bestehen, sind Text. px_je_mm: Pixel je Millimeter. papier: Helligkeit des Papiers, wenn bekannt (sonst
    das 92. Perzentil des Bilds). protokoll: Liste, an die je geprüfter Fläche (Rechteck, Merkmale, Urteil)
    angehängt wird (Messung)."""
    np = _numpy()
    if np is None or grau is None or grau.ndim != 2:
        return []
    z = max(4, int(round(ZELLE_MM * px_je_mm)))
    if min(grau.shape) < 3 * z:
        return []
    roh = grau.astype(np.float32)
    schwarzweiss = float(((roh < 40) | (roh > 215)).mean()) > 0.97
    g = _kasten(np, roh, max(1, z // 3) if schwarzweiss else 1)       # Rasterpunkte zu Halbtönen, Rauschen weg
    del roh
    if papier is None:
        papier = float(np.percentile(g[::3, ::3], 92))
    k = max(3, int(round(STRICH_MM * px_je_mm)) | 1)
    c = _schliessen(np, g, k)
    del g
    zc = np.sort(_zellen(np, c, z), axis=2)
    del c
    hb, wb = zc.shape[:2]
    nz = z * z
    med = zc[:, :, nz // 2]
    spanne = zc[:, :, min(nz - 1, int(0.9 * nz))] - zc[:, :, int(0.1 * nz)]
    del zc
    inhalt = med <= papier - PAPIER_ABSTAND
    if not inhalt.any():
        return []
    min_zellen = max(BEREICH_MIN_ZELLEN, int(BEREICH_MIN_MM * px_je_mm / z + 0.999))
    wortmaske = None
    if woerter_px:
        wortmaske = np.zeros((hb, wb), np.float32)
        for wort in woerter_px:
            if len(wort) < 5 or not _WORT_RE.search(str(wort[4])):
                continue
            x0, y0 = int(max(0, wort[0] // z)), int(max(0, wort[1] // z))
            x1, y1 = int(min(wb, wort[2] / z + 1)), int(min(hb, wort[3] / z + 1))
            if x1 > x0 and y1 > y0:
                wortmaske[y0:y1, x0:x1] = 1.0
    rand_px = BEREICH_RAND_MM * px_je_mm
    max_rand_px = BEREICH_MAX_RAND_MM * px_je_mm

    def pixelrechteck(y0, x0, y1, x1, rand=None):
        """Zellrechteck -> Pixelrechteck; rand = (oben, seitlich, unten) als Anteil der Höhe/Breite."""
        h, w = (y1 - y0) * z, (x1 - x0) * z
        if rand is None:
            oben = unten = rx = 0.0
        else:
            oben = min(max_rand_px, rand_px + rand[0] * h)
            unten = min(max_rand_px, rand_px + rand[2] * h)
            rx = min(max_rand_px, rand_px + rand[1] * w)
        return (max(0, int(x0 * z - rx)), max(0, int(y0 * z - oben)), min(grau.shape[1], int(x1 * z + rx + 0.999)),
                min(grau.shape[0], int(y1 * z + unten + 0.999)))

    def pruefen(y0, x0, y1, x1, maske, karte, tiefe=0) -> list:
        bh, bw = y1 - y0, x1 - x0
        if bh < min_zellen or bw < min_zellen:
            return []
        medianen = med[y0:y1, x0:x1][maske]
        if tiefe == 0 and medianen.size >= 4 * min_zellen * min_zellen:
            # vorherrschender heller Farbton (Ausweiskarte, Sicherheitsuntergrund, getöntes Feld)?
            gerundet = np.round(medianen).astype(np.int64)
            zaehl = np.bincount(gerundet - gerundet.min()).astype(np.float64)
            fenster = np.convolve(zaehl, np.ones(2 * GRUND_TOLERANZ + 1), mode="same")
            grundton = float(np.argmax(fenster) + gerundet.min())
            if fenster.max() >= GRUND_ANTEIL * medianen.size and grundton >= papier - GRUND_MAX_ABSTAND:
                abgehoben = maske & (np.abs(med[y0:y1, x0:x1] - grundton) >= GRUND_ABHEBUNG)
                karte_neu = pixelrechteck(y0, x0, y1, x1)
                aus = []
                for sy0, sx0, sy1, sx1, sm in _komponenten(np, abgehoben):
                    aus += pruefen(y0 + sy0, x0 + sx0, y0 + sy1, x0 + sx1, sm, karte_neu, tiefe + 1)
                return aus
        if max(bh / bw, bw / bh) > BEREICH_MAX_SEITENVERHAELTNIS:
            return []
        am_rand = y0 == 0 or x0 == 0 or y1 == hb or x1 == wb
        if am_rand and (bh < RAND_STREIFEN * hb or bw < RAND_STREIFEN * wb):
            return []                                  # Scannerrand, Schatten am Bildrand
        innen = maske.copy()
        innen[1:] &= maske[:-1]
        innen[:-1] &= maske[1:]
        innen[:, 1:] &= maske[:, :-1]
        innen[:, :-1] &= maske[:, 1:]
        ys, xs = np.nonzero(maske)
        m = merkmale(np, medianen, spanne[y0:y1, x0:x1][maske], innen[maske], ys, xs)
        foto = _ist_foto(m)
        if foto and wortmaske is not None and float(wortmaske[y0:y1, x0:x1][maske].mean()) > BEREICH_MAX_WORTANTEIL:
            foto = False
        if protokoll is not None:
            protokoll.append((pixelrechteck(y0, x0, y1, x1), m, foto))
        if not foto:
            return []
        # Passbild auf einer Karte (oder sonst hochkant): erkannt wird die Silhouette (Kopf, Schultern); der helle
        # Hintergrund darüber und daneben gehört zum Bild -> oben und seitlich mehr Rand
        hochkant = _hochformat(bw, bh)
        rand = BEREICH_RAND_PORTRAET if (karte is not None or hochkant) else BEREICH_RAND_ANTEIL
        if not _grosses_loch(np, maske):
            return [Fotobereich(pixelrechteck(y0, x0, y1, x1, rand), karte, hochkant)]
        # Ring um eine große helle Fläche (Tischplatte um ein fotografiertes Blatt): nur die Fläche selbst, in
        # Rechtecke zerlegt – das Blatt in der Mitte bleibt lesbar
        teile = _rechtecke_aus_maske(_ausdehnen(maske, 1))
        return [Fotobereich(pixelrechteck(y0 + ty0, x0 + tx0, y0 + ty1, x0 + tx1, (0.0, 0.0, 0.0)), karte, False)
                for ty0, tx0, ty1, tx1 in teile]

    bereiche = []
    for y0, x0, y1, x1, maske in _komponenten(np, inhalt):
        bereiche += pruefen(y0, x0, y1, x1, maske, None)
    return _zusammenfassen(bereiche)


def _zusammenfassen(bereiche: list) -> list:
    """Deutlich überlappende Fotobereiche zu einem zusammenfassen (Karte und Hochformat vom größten); Teile einer
    zerlegten Fläche (Ring um ein Blatt) berühren sich nur an den Ecken und bleiben getrennt."""
    if len(bereiche) < 2:
        return bereiche
    rechtecke = _vereinigen([b.rect for b in bereiche], ZUSAMMENFASSEN_UEBERLAPPUNG)
    aus = []
    for r in rechtecke:
        teile = [b for b in bereiche if b.rect[0] < r[2] and r[0] < b.rect[2] and b.rect[1] < r[3] and r[1] < b.rect[3]]
        groesster = max(teile, key=lambda b: (b.rect[2] - b.rect[0]) * (b.rect[3] - b.rect[1]))
        aus.append(Fotobereich(r, groesster.karte, groesster.hochformat if len(teile) == 1 else
                               _hochformat(r[2] - r[0], r[3] - r[1])))
    return aus


def fotobereiche(seite, clip=None, woerter=None, dpi: float | None = None, protokoll=None) -> list:
    """Fotobereiche der Seite (bzw. im Ausschnitt `clip`) in Seitenkoordinaten: [Fotobereich(fitz.Rect, Karte als
    fitz.Rect oder None, hochformat)].

    clip (z. B. ein eingebettetes Bild): gelesen wird mit CLIP_RAND_MM Umgebung – das Papier daneben gibt das
    Papierweiß (ein Foto, das den Ausschnitt ganz füllt, hat selbst keins); Ergebnisse auf den Ausschnitt beschnitten.
    woerter: OCR-Wörter der Seite [(x0, y0, x1, y1, Text, …)] in Seitenkoordinaten (Text-Veto, optional)."""
    innen = None
    bereich = None
    if clip is not None:
        innen = fitz.Rect(clip) & seite.rect
        if innen.is_empty or innen.is_infinite:
            return []
        rand = CLIP_RAND_MM * 72 / 25.4
        bereich = (innen + (-rand, -rand, rand, rand)) & seite.rect
    grau, abbildung = grau_rendern(seite, bereich, dpi)
    if grau is None:
        return []
    np = _numpy()
    ox, oy, pt_je_px = abbildung
    px_je_pt = 1.0 / pt_je_px
    papier = None
    if innen is not None:
        ring = np.ones(grau.shape, dtype=bool)
        ix0, iy0 = int((innen.x0 - ox) * px_je_pt), int((innen.y0 - oy) * px_je_pt)
        ix1, iy1 = int((innen.x1 - ox) * px_je_pt + 0.999), int((innen.y1 - oy) * px_je_pt + 0.999)
        ring[max(0, iy0):max(0, iy1), max(0, ix0):max(0, ix1)] = False
        if ring.sum() >= 400:
            papier = float(np.percentile(grau[ring], 92))
        del ring
    woerter_px = None
    if woerter:
        woerter_px = [((w[0] - ox) * px_je_pt, (w[1] - oy) * px_je_pt, (w[2] - ox) * px_je_pt,
                       (w[3] - oy) * px_je_pt, w[4]) for w in woerter if len(w) >= 5]
    px_je_mm = px_je_pt * 72.0 / 25.4
    roh = fotobereiche_im_bild(grau, px_je_mm, woerter_px, protokoll, papier)
    del grau
    grenze = innen if innen is not None else fitz.Rect(seite.rect)

    def seitenrect(r):
        return fitz.Rect(ox + r[0] * pt_je_px, oy + r[1] * pt_je_px, ox + r[2] * pt_je_px,
                         oy + r[3] * pt_je_px) & grenze
    aus = []
    for b in roh:
        r = seitenrect(b.rect)
        if not r.is_empty:
            aus.append(Fotobereich(r, seitenrect(b.karte) if b.karte is not None else None, b.hochformat))
    if protokoll is not None:
        protokoll[:] = [(seitenrect(r), m, f) for r, m, f in protokoll]
    return aus


# ======================================================================
# Bildfunde: Lichtbilder (alle Schutzstufen), Bilder und Fotobereiche („maximal“)
# ======================================================================
# Ein Bildfund ist ein Fund wie jeder andere (Fundliste, Vorschau, an/aus je Stelle), nur dass seine Stellen keine
# Textstellen sind, sondern Rechtecke: {"seite", "start": 0, "ende": 0, "an", "text": "", "bereich": [x0, y0, x1, y1]}
# (start = ende = 0: Text-Werkzeuge sehen eine leere Stelle). Die Schwärzung deckt ein angehaktes Lichtbild ab wie einen
# in der Vorschau gezogenen Rahmen (Text UND Bildpixel, Platzhalter darin) – ebenso Bilder und Fotos („maximal“) auf
# Scans. Auf Textseiten verlieren Bilder und Fotos nur ihre Bildpixel: Text darüber bleibt (Hintergrund, Wasserzeichen),
# gefüllt und beschriftet wird nur ein Bereich ohne Text (Befund 5 der Runde 3a).
KAT_LICHTBILD = "lichtbild"   # Foto mit Ausweis-Kontext (Personalausweis, Pass, Führerschein …)
KAT_FOTO = "foto"             # sonstiger Fotobereich einer Scan-Seite (nur „maximal“)
KAT_BILD = "bild"             # eingebettetes Rasterbild einer Textseite (nur „maximal“)
BILD_KATEGORIEN = (KAT_LICHTBILD, KAT_FOTO, KAT_BILD)
ANZEIGE = {KAT_LICHTBILD: "Lichtbild (Ausweis)", KAT_FOTO: "Foto", KAT_BILD: "Bild"}
PLATZHALTER = {KAT_LICHTBILD: "[LICHTBILD]", KAT_FOTO: "[FOTO]", KAT_BILD: "[BILD]"}
KONTEXT_TEXT = {KAT_LICHTBILD: "Foto auf einer Ausweiskopie", KAT_FOTO: "Foto auf einer Scan-Seite",
                KAT_BILD: "eingebettetes Bild"}
HINWEIS_LICHTBILD = ("Lichtbild einer Ausweiskopie – wird abgedeckt. Abgewählt bleibt das Gesicht sichtbar; die "
                     "Ausgabe muss dann in der Vorschau freigegeben werden.")
HINWEIS_MAXIMAL = "Schutzstufe „Maximal“: Bilder und Fotos werden abgedeckt (in der Vorschau abwählbar)."
QUELLE = "fotos"
# Winzige Bilder bleiben auch in „maximal“ stehen (Aufzählungszeichen, Häkchen, Symbole, Linien): ein Gesicht ist erst
# ab etwa 24 x 24 Pixeln zu erkennen, eine Unterschrift oder eine Textzeile erst ab etwa 6 Pixeln Höhe. Bewusst
# NICHT nach der Größe auf der Seite: ein Lichtbild in einem Brief nimmt oft nur 2 % der Seite ein, und auch ein
# winzig dargestelltes Bild lässt sich in voller Auflösung aus der PDF ziehen.
BILD_WINZIG_PIXEL = 24 * 24
BILD_WINZIG_KANTE = 6
WENIG_WOERTER = 40            # Scan-Seite mit weniger OCR-Wörtern: Ausweisbild auch ohne lesbaren Ausweistext suchen
KARTE_SEITENVERHAELTNIS = (1.30, 1.80)   # ID-1 (Personalausweis, Führerschein) 1,59; ID-3 (Pass) 1,42
# Ein Bild ist „die Seite selbst“ (Scan, Foto als PDF), wenn es mindestens die Hälfte der Seite bedeckt – oder auf einer
# Scan-Seite als Streifen fast die ganze Breite bzw. Höhe einnimmt (Streifen-Scans). Dort werden in „maximal“ die
# Fotobereiche abgedeckt, nicht das ganze Bild (sonst bliebe eine leere Seite).
SEITENBILD_ANTEIL = 0.5
SEITENBILD_KANTE = 0.8
# Nimmt ein Fotobereich mindestens die Hälfte eines eingebetteten Bilds ein, ist das Bild ein Foto (Passbild, Porträt):
# dann wird das ganze Bild abgedeckt – die Erkennung lässt sonst Ränder stehen (Schultern, heller Hintergrund). Ein
# eingebetteter Ausweis (Lichtbild etwa ein Viertel der Karte) bleibt bis auf das Lichtbild lesbar.
FOTO_GANZES_BILD = 0.5


def bild_winzig(breite, hoehe) -> bool:
    """Ist ein Rasterbild (Pixelgröße) so klein, dass es keine Person zeigen kann?"""
    try:
        b, h = int(breite or 0), int(hoehe or 0)
    except (TypeError, ValueError):
        return False
    return b * h < BILD_WINZIG_PIXEL or min(b, h) < BILD_WINZIG_KANTE


# ----------------------------------------------------------------------
# Ausweis-Kontext aus dem Text der Seite
# ----------------------------------------------------------------------
KONTEXT_KEINER, KONTEXT_SCHWACH, KONTEXT_STARK = 0, 1, 2
_TITEL = (r"personalausweis\w*|kinderreisepass\w*|reisepass\w*|f[uü]hrerschein\w*|aufenthaltstitel\w*|"
          r"aufenthaltserlaubnis\w*|niederlassungserlaubnis\w*|identity\s*card|passport|residence\s*permit|"
          r"driving\s*licen[cs]e|carte\s*d.\s*identit[eé]|passeport|permis\s*de\s*conduire|carta\s*d.\s*identit[aà]")
_TITEL_RE = re.compile(r"(?i)(?<![\w])(?:" + _TITEL + r")")
_TITEL_GROSS_RE = re.compile(r"(?<![\w])(?:PERSONALAUSWEIS|KINDERREISEPASS|REISEPASS|F[UÜ]HRERSCHEIN|"
                             r"AUFENTHALTSTITEL|IDENTITY\s*CARD|PASSPORT|RESIDENCE\s*PERMIT|DRIVING\s*LICEN[CS]E|"
                             r"PASSEPORT|PERMIS\s*DE\s*CONDUIRE)(?![a-zäöüß])")
_NUR_TITEL_RE = re.compile(r"(?i)(?:" + _TITEL + r")[\s.:]*")
_AUSWEIS_SCHWACH_RE = re.compile(r"(?i)(?<![\w])(?:ausweis\w*|lichtbild\w*|passfoto\w*)")
# englische Feldbeschriftungen zweisprachiger Ausweise – deutsche Formulare (Antrag, Police) tragen sie nicht
_FELD_RE = re.compile(r"(?i)(?<![\w])(surname|given\s*names?|date\s*of\s*birth|place\s*of\s*birth|nationality|"
                      r"date\s*of\s*expiry|date\s*of\s*issue|colou?r\s*of\s*eyes|religious\s*name)(?![\w])")
_MRZ_ZEICHEN = "<«‹"
_MRZ_RE = re.compile(r"[A-Z0-9<«‹]{20,}")


def _mrz(zeile: str) -> bool:
    """Maschinenlesbare Zone: eine Zeile aus Großbuchstaben, Ziffern und vielen Füllzeichen „<“ (die OCR liest sie
    auch als „«“ oder trennt die Zeile in Stücke)."""
    kompakt = re.sub(r"\s+", "", zeile)
    if sum(kompakt.count(c) for c in _MRZ_ZEICHEN) < 5 or not re.search(r"[<«‹]{3,}", kompakt):
        return False
    return (any(sum(t.count(c) for c in _MRZ_ZEICHEN) >= 4 for t in _MRZ_RE.findall(kompakt))
            or re.search(r"[<«‹]{5,}", kompakt) is not None)


def ausweis_kontext(text: str) -> int:
    """KONTEXT_STARK: maschinenlesbare Zone, Ausweistitel als Überschrift (Großbuchstaben, kurze Zeile oder mit
    Gegenstück in einer zweiten Sprache: „PERSONALAUSWEIS / IDENTITY CARD“) oder zwei englische Ausweis-
    Feldbeschriftungen; KONTEXT_SCHWACH: ein Ausweiswort irgendwo im Text („Kopie meines Personalausweises“);
    sonst KONTEXT_KEINER."""
    if not text:
        return KONTEXT_KEINER
    schwach = False
    felder: set = set()
    for zeile in text.splitlines():
        if _mrz(zeile):
            return KONTEXT_STARK
        titel = _TITEL_RE.findall(zeile)
        if titel:
            schwach = True
            # Überschrift: in Großbuchstaben, zweisprachig, oder die Zeile ist nur der Titel („Reisepass“) – nicht aber
            # ein Feld „Führerschein-Nr.:“ oder „Kopie Ihres Reisepasses“
            if _TITEL_GROSS_RE.search(zeile) or len(titel) >= 2 or _NUR_TITEL_RE.fullmatch(zeile.strip()):
                return KONTEXT_STARK
        elif _AUSWEIS_SCHWACH_RE.search(zeile):
            schwach = True
        felder.update(re.sub(r"\s+", " ", f.lower()) for f in _FELD_RE.findall(zeile))
        if len(felder) >= 2:
            return KONTEXT_STARK
    return KONTEXT_SCHWACH if schwach else KONTEXT_KEINER


def _kartenartig(karte) -> bool:
    if karte is None:
        return False
    r = fitz.Rect(karte)
    if r.is_empty or min(r.width, r.height) <= 0:
        return False
    v = max(r.width, r.height) / min(r.width, r.height)
    return KARTE_SEITENVERHAELTNIS[0] <= v <= KARTE_SEITENVERHAELTNIS[1]


def ist_lichtbild(bereich: Fotobereich, kontext: int) -> bool:
    """Ist ein Fotobereich ein Lichtbild? Mit starkem Ausweis-Kontext jedes Foto der Seite; mit schwachem ein Foto
    im Passbild-Format oder auf einer Karte; ohne Text nur ein Passbild auf einer ausweisgroßen Karte."""
    if kontext >= KONTEXT_STARK:
        return True
    if kontext == KONTEXT_SCHWACH:
        return bool(bereich.hochformat or bereich.karte is not None)
    return bool(bereich.hochformat and _kartenartig(bereich.karte))


# ----------------------------------------------------------------------
# Analyse: Bildfunde einer Seite und des Dokuments
# ----------------------------------------------------------------------
def _bildtext(m) -> str:
    """Text einer Modellseite, der aus Bildern gelesen wurde (OCR einer Scan-Seite oder ihrer Bildbereiche)."""
    if getattr(m, "ocr_modus", "nein") == "seite":
        return m.text
    return "".join(z.c if z.quelle != "text" or z.c == "\n" else " " for z in m.zeichen)


def bilder_der_seite(seite) -> list:
    """[(Rechteck, xref, Breite, Höhe)] aller sichtbar gezeichneten Rasterbilder der Seite – auch Inline-Bilder,
    Bildmasken, Bilder in Form-XObjects und Kachelmustern (get_image_info sieht, was gezeichnet wird)."""
    aus = []
    try:
        infos = seite.get_image_info(xrefs=True)
    except Exception:
        return aus
    seitenrect = fitz.Rect(seite.rect)
    for info in infos:
        r = fitz.Rect(info.get("bbox")) & seitenrect
        if r.is_empty or r.is_infinite:
            continue
        aus.append((r, int(info.get("xref") or 0), int(info.get("width") or 0), int(info.get("height") or 0)))
    return aus


def seite_pruefen(seite, m, profil: str = "hoch", woerter=None) -> dict:
    """Bildfunde einer Seite. seite: vorbereitete PyMuPDF-Seite, m: Modellseite (seitenmodell.Seite) derselben Seite,
    woerter: OCR-Wörter der Seite (Text-Veto der Fotoerkennung).
    Rückgabe: {"lichtbild": [Rect], "foto": [Rect], "bild": [(Rect, [xrefs])], "kontext": 0|1|2,
               "ausweis_ohne_lichtbild": bool}."""
    from . import muster as _muster
    maximal = _muster.option(profil, "bilder_schwaerzen")
    aus = {KAT_LICHTBILD: [], KAT_FOTO: [], KAT_BILD: [], "kontext": KONTEXT_KEINER,
           "ausweis_ohne_lichtbild": False}
    modus = getattr(m, "ocr_modus", "nein")
    if modus not in ("seite", "bilder") and not maximal:
        return aus
    kontext = ausweis_kontext(m.text)
    aus["kontext"] = kontext
    seitenrect = fitz.Rect(seite.rect)
    flaeche = max(1.0, abs(seitenrect))

    def ist_seitenbild(r) -> bool:
        """Ist das Bild die Seite selbst (Scan, Foto als Seite) bzw. ein Streifen davon?"""
        return (abs(r) >= SEITENBILD_ANTEIL * flaeche
                or (modus == "seite" and (r.width >= SEITENBILD_KANTE * seitenrect.width
                                          or r.height >= SEITENBILD_KANTE * seitenrect.height)))
    bilder = [b for b in bilder_der_seite(seite) if not bild_winzig(b[2], b[3])] if maximal else []
    seitenbilder = [b[0] for b in bilder if ist_seitenbild(b[0])]
    if modus in ("seite", "bilder") or seitenbilder:
        bereiche = []
        # gesucht wird mit Ausweis-Kontext, in „maximal“ und auf Bildern mit wenig lesbarem Text (eine Ausweiskarte,
        # deren Schrift die OCR nicht liest) – nicht auf jedem gut lesbaren Scan
        if verfuegbar() and (maximal or kontext or int(getattr(m, "ocr_woerter", 0) or 0) < WENIG_WOERTER):
            if modus == "seite":
                bereiche = fotobereiche(seite, woerter=woerter)
            else:
                for r in list(getattr(m, "bilder", None) or []) + [s for s in seitenbilder if modus == "nein"]:
                    r = fitz.Rect(r) & seitenrect
                    gefunden = fotobereiche(seite, clip=r, woerter=woerter)
                    if not ist_seitenbild(r):
                        # überwiegend Foto: das ganze Bild (1 pt Rand – MuPDF entfernt ein Bild nur dann ganz, wenn
                        # die Schwärzung es vollständig überdeckt)
                        ganz = (r + (-1, -1, 1, 1)) & seitenrect
                        gefunden = [b._replace(rect=fitz.Rect(ganz))
                                    if abs(fitz.Rect(b.rect) & r) >= FOTO_GANZES_BILD * abs(r) else b
                                    for b in gefunden]
                    bereiche += gefunden
        for b in bereiche:
            if ist_lichtbild(b, kontext):
                aus[KAT_LICHTBILD].append(fitz.Rect(b.rect))
            elif maximal and (modus == "seite" or any(fitz.Rect(b.rect).intersects(s) for s in seitenbilder)):
                aus[KAT_FOTO].append(fitz.Rect(b.rect))
        # Ausweiskopie (Ausweistext auf dem Bild selbst), aber kein Lichtbild gefunden: das Gesicht kann trotzdem da
        # sein – die Schwärzung verlangt dann die Freigabe in der Vorschau
        aus["ausweis_ohne_lichtbild"] = (modus in ("seite", "bilder") and not aus[KAT_LICHTBILD]
                                         and ausweis_kontext(_bildtext(m)) >= KONTEXT_STARK)
    if maximal:
        # „maximal“: jedes Rasterbild, das nicht die Seite selbst ist, verschwindet (Lichtbild, Unterschrift als Bild,
        # fotografiertes Dokument, Logo …); auf der Seite selbst (Scan) zählen die Fotobereiche
        gruppen: list = []
        for r, xref, _breite, _hoehe in bilder:
            if ist_seitenbild(r):
                continue
            for eintrag in gruppen:
                if eintrag[0].intersects(r):              # Kacheln eines Musters, überlappende Bilder: ein Bereich
                    eintrag[0] |= r
                    eintrag[1].add(xref)
                    break
            else:
                gruppen.append([fitz.Rect(r), {xref}])
        # 1 pt Rand: MuPDF entfernt ein Bild nur dann ganz, wenn die Schwärzung es vollständig überdeckt
        aus[KAT_BILD] = [((r + (-1, -1, 1, 1)) & seitenrect, sorted(x for x in xrefs if x > 0)) for r, xrefs in gruppen]
        # Ein Bild über mindestens die Hälfte einer TEXTseite (Formular- oder Briefhintergrund, fotografiertes Blatt)
        # bleibt wie ein Scan stehen – abgedeckt werden die Fotos darin; das wird ausdrücklich gemeldet (Befund 6)
        aus["seitenbild_bleibt"] = modus != "seite" and bool(seitenbilder)
    return aus


def _rect_liste(r) -> list:
    return [round(float(v), 2) for v in fitz.Rect(r)]


def funde_bilden(befunde: dict, start_id: int = 1) -> list:
    """Bildfunde (ein Fund je Art, Stellen = Bereiche) aus {Seite: seite_pruefen(...)}."""
    funde = []
    for kategorie in BILD_KATEGORIEN:
        stellen = []
        for nr in sorted(befunde):
            for eintrag in befunde[nr].get(kategorie) or ():
                rect, xrefs = (eintrag if kategorie == KAT_BILD else (eintrag, []))
                stelle = {"seite": nr, "start": 0, "ende": 0, "an": True, "text": "", "bereich": _rect_liste(rect)}
                if xrefs:
                    stelle["bildxrefs"] = list(xrefs)
                stellen.append(stelle)
        if not stellen:
            continue
        seiten = sorted({st["seite"] + 1 for st in stellen})
        kontext = (KONTEXT_TEXT[kategorie] + " (Seite " + ", ".join(map(str, seiten[:6]))
                   + (" …" if len(seiten) > 6 else "") + ")")
        funde.append({"id": f"b{start_id + len(funde)}", "kategorie": kategorie, "anzeige": ANZEIGE[kategorie],
                      "text": "", "ersatz": PLATZHALTER[kategorie], "seiten": seiten, "anzahl": len(stellen),
                      "kontext": kontext, "stellen": stellen, "quellen": [f"{QUELLE}.{kategorie}"],
                      "sicherheit": 0.8 if kategorie == KAT_LICHTBILD else 1.0,
                      "hinweis": HINWEIS_LICHTBILD if kategorie == KAT_LICHTBILD else HINWEIS_MAXIMAL})
    return funde


def dokument_pruefen(doc, dok, profil: str = "hoch", ocr_cache=None) -> dict:
    """Bildfunde aller Seiten: {"funde": [...], "meldungen": [(art, code, text, seite)]}. Fehler einer Seite brechen
    die Analyse nie ab – sie werden als Warnung gemeldet: ein Lichtbild darauf kann unbemerkt stehen bleiben, die
    Ausgabe muss deshalb in der Vorschau freigegeben werden (BILDER_UNGEPRUEFT wirkt bis in die Ausgabe)."""
    befunde: dict = {}
    meldungen = []
    for nr, m in enumerate(getattr(dok, "seiten", []) or []):
        if nr >= len(doc):
            break
        try:
            befunde[nr] = seite_pruefen(doc[nr], m, profil, (ocr_cache or {}).get(nr))
        except Exception as e:                   # nie die Analyse abbrechen
            meldungen.append(("warnung", "BILDER_UNGEPRUEFT", f"Seite {nr + 1}: Bildprüfung fehlgeschlagen "
                                                               f"({type(e).__name__}) – Fotos und Lichtbilder darauf "
                                                               f"bitte selbst ansehen.", nr))
    funde = funde_bilden(befunde)
    for nr, b in sorted(befunde.items()):
        if b[KAT_LICHTBILD]:
            meldungen.append(("hinweis", "LICHTBILD", f"Seite {nr + 1}: Lichtbild einer Ausweiskopie erkannt – es wird "
                                                     f"abgedeckt (in der Vorschau abwählbar).", nr))
        elif b["ausweis_ohne_lichtbild"]:
            meldungen.append(("warnung", "AUSWEIS_OHNE_LICHTBILD",
                              f"Seite {nr + 1} sieht aus wie eine Ausweiskopie, ein Lichtbild wurde aber nicht sicher "
                              f"erkannt – bitte in der Vorschau ansehen und einen Rahmen über das Gesicht ziehen. Die "
                              f"Ausgabe muss in der Vorschau freigegeben werden.", nr))
    anzahl = {k: sum(len(b[k]) for b in befunde.values()) for k in (KAT_BILD, KAT_FOTO)}
    if anzahl[KAT_BILD] or anzahl[KAT_FOTO]:
        meldungen.append(("hinweis", "BILDER_ABGEDECKT",
                          f"Schutzstufe „Maximal“: {anzahl[KAT_BILD]} Bild(er) und {anzahl[KAT_FOTO]} Fotobereich(e) "
                          f"werden abgedeckt (in der Fundliste bzw. Vorschau abwählbar). Text über einem Bild bleibt "
                          f"lesbar.", None))
    for nr, b in sorted(befunde.items()):
        if b.get("seitenbild_bleibt"):
            meldungen.append(("hinweis", "BILDER_ABGEDECKT",
                              f"Seite {nr + 1}: Ein Bild bedeckt mindestens die Hälfte der Seite (Hintergrund oder "
                              f"fotografiertes Blatt) – es bleibt wie ein Scan stehen; abgedeckt werden nur die Fotos "
                              f"darin und die gefundenen Angaben. Bitte in der Vorschau ansehen.", nr))
    return {"funde": funde, "meldungen": meldungen}


# ----------------------------------------------------------------------
# Schwärzung: Bildfunde abtrennen, Gründe für die Freigabe, Reste in „maximal“
# ----------------------------------------------------------------------
def ist_bildfund(fund: dict) -> bool:
    return fund.get("kategorie") in BILD_KATEGORIEN and any("bereich" in st for st in fund.get("stellen") or ())


class Bildbereich(tuple):
    """(Rechteck, Platzhalter) eines Bildfunds – die Schwärzung verarbeitet ihn wie einen manuellen Bereich (zwei Werte
    entpacken). nur_bild: auf einer Textseite nur die Bildpixel entfernen, Text und Linien darüber bleiben (Bilder und
    Fotos in „maximal“, Befund 5 der Runde 3a); ein Lichtbild wird immer ganz abgedeckt."""

    def __new__(cls, rect, ersatz, kategorie=KAT_BILD):
        obj = super().__new__(cls, (rect, ersatz))
        obj.kategorie = kategorie
        obj.nur_bild = kategorie in (KAT_BILD, KAT_FOTO)
        return obj

    def __reduce__(self):
        return (Bildbereich, (self[0], self[1], self.kategorie))


def bildfunde_trennen(funde: list) -> tuple:
    """(Textfunde, Auftrag): Bildfunde werden zu Bereichen {Seite: [Bildbereich(Rect, Platzhalter)]} (nur angehakte
    Stellen);
    der Auftrag merkt sich je Art die abgedeckten und die abgewählten Bereiche, die Bilder (xrefs) abgewählter
    Bildbereiche und die Seiten mit abgewählten Bild- oder Fotobereichen – beides lässt auch die Nachkontrolle in
    „maximal“ stehen."""
    text, auftrag = [], {"bereiche": {}, "abgedeckt": {k: [] for k in BILD_KATEGORIEN},
                         "abgewaehlt": {k: [] for k in BILD_KATEGORIEN}, "behalten_xrefs": set(),
                         "abgewaehlt_seiten": set()}
    for fund in funde or ():
        if not ist_bildfund(fund):
            text.append(fund)
            continue
        kategorie = fund.get("kategorie")
        ersatz = fund.get("ersatz") or PLATZHALTER.get(kategorie, "[BILD]")
        for st in fund.get("stellen") or ():
            try:
                nr, r = int(st["seite"]), fitz.Rect(st["bereich"])
            except (KeyError, TypeError, ValueError):
                continue
            if r.is_empty:
                continue
            if st.get("an", True):
                auftrag["bereiche"].setdefault(nr, []).append(Bildbereich(r, ersatz, kategorie))
                auftrag["abgedeckt"][kategorie].append((nr, r))
            else:
                auftrag["abgewaehlt"][kategorie].append((nr, r))
                auftrag["behalten_xrefs"].update(int(x) for x in st.get("bildxrefs") or ())
                auftrag["abgewaehlt_seiten"].add(nr)
    return text, auftrag


def text_ueber_bereich(rect, woerter) -> bool:
    """Liegt Text der Textebene über dem Bereich – mindestens ein Wort mit seiner Mitte darin? Dann ist das Bild dort
    ein Hintergrund (Wasserzeichen, Formular- oder Briefhintergrund): es verschwindet, der Bereich wird aber nicht
    gefüllt. woerter: get_text("words") der Seite."""
    r = fitz.Rect(rect) + (1, 1, -1, -1)
    if r.is_empty:
        return False
    for w in woerter or ():
        if len(w) >= 5 and str(w[4]).strip() and r.contains(fitz.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)):
            return True
    return False


def freigabe_gruende(auftrag: dict, dok) -> list:
    """[(Code, Seite, Text)]: Warum braucht die Ausgabe die Freigabe in der Vorschau? Ein abgewähltes Lichtbild bleibt
    sichtbar; eine Ausweiskopie (Ausweistext auf dem Bild selbst) ohne abgedecktes Lichtbild kann ein Gesicht zeigen,
    das die Erkennung nicht gefunden hat."""
    gruende: dict = {}
    for nr, _ in (auftrag or {}).get("abgewaehlt", {}).get(KAT_LICHTBILD, ()):
        gruende.setdefault(nr, ("LICHTBILD_SICHTBAR", nr, f"Seite {nr + 1}: Lichtbild nicht abgedeckt"))
    abgedeckt = {nr for nr, _ in (auftrag or {}).get("abgedeckt", {}).get(KAT_LICHTBILD, ())}
    for nr, m in enumerate(getattr(dok, "seiten", []) or []):
        if nr in gruende or nr in abgedeckt or getattr(m, "ocr_modus", "nein") not in ("seite", "bilder"):
            continue
        try:
            if ausweis_kontext(_bildtext(m)) >= KONTEXT_STARK:
                gruende[nr] = ("AUSWEIS_OHNE_LICHTBILD", nr,
                               f"Seite {nr + 1}: Ausweiskopie – Lichtbild bitte selbst prüfen")
        except Exception:
            continue
    return [gruende[nr] for nr in sorted(gruende)]


# --- „maximal“: Bilder, die apply_redactions nicht erreicht (Kachelmuster, Type3-Schriften, ungenutzte Ressourcen)
# Nicht angezeigte Bilder (auch in geerbten oder geteilten Ressourcen) leert in JEDER Schutzstufe
# bilder.bildreste_entfernen vor dem Speichern (Befund 1 der Runde 3a).
bild_leeren = _bilder.bild_leeren


def bilder_in_ressourcen(doc, seite_xref: int) -> set:
    """Alle Bild-XObjects, die die Seite über ihre (auch geerbten) Ressourcen erreicht – über Form-XObjects,
    Kachelmuster, Type3-Schriften, weiche Masken und Anmerkungen, auch ungenutzte (bilder.erreichbare_bilder)."""
    return set(_bilder.erreichbare_bilder(doc, seite_xref))


def bilder_nachkontrolle(doc, seiten, behalten_xrefs=(), seiten_behalten=()) -> int:
    """„maximal“, nach dem Schwärzen: Bilder, die eine Textseite in einem Kachelmuster, einer Type3-Schrift, einer
    weichen Maske oder einer Anmerkung zeichnet (dort erreicht apply_redactions sie nicht), werden geleert – außer
    winzigen, bewusst abgewählten (behalten_xrefs; seiten_behalten: Seiten mit abgewählten Bildbereichen) und solchen,
    die auch eine andere Seite (Scan, Seite mit Abwahl) zeichnet.
    Bilder, die eine Textseite direkt zeichnet, entscheiden die Bildfunde – Vorschau, Fundliste und Abwahl gelten auch
    in der Ausgabe; ein Wörterbuch, das eine Textseite mit einer Scan-Seite teilt, leert nie deren Seitenbild; nicht
    angezeigte Bilder leert bilder.bildreste_entfernen (Befund 6 der Runde 3a).
    seiten: Seitenindizes der Textseiten. Rückgabe: Anzahl geleerter Bilder."""
    behalten = set(behalten_xrefs or ())
    seiten_behalten = set(seiten_behalten or ())
    textseiten = [nr for nr in sorted(set(seiten)) if 0 <= nr < len(doc) and nr not in seiten_behalten]
    andere: set = set()                        # was eine andere Seite zeichnet, bleibt (auch bei Lesefehlern)
    for nr in range(len(doc)):
        if nr in textseiten:
            continue
        try:
            andere |= _bilder.gezeichnet_auf_seite(doc, doc[nr])[0]
        except Exception:
            try:
                andere |= set(_bilder.erreichbare_bilder(doc, doc[nr].xref))
            except Exception:
                return 0                       # unklar, was die Seite zeigt: lieber nichts leeren
    geleert = 0
    for nr in textseiten:
        try:
            erreichbar = _bilder.erreichbare_bilder(doc, doc[nr].xref)
        except Exception:
            continue
        for x in sorted(x for x, indirekt in erreichbar.items() if indirekt):
            if x in behalten or x in andere:
                continue
            try:
                breite = int(doc.xref_get_key(x, "Width")[1] or 0)
                hoehe = int(doc.xref_get_key(x, "Height")[1] or 0)
            except (ValueError, TypeError):
                breite = hoehe = 0
            if breite and hoehe and bild_winzig(breite, hoehe):
                continue
            if bild_leeren(doc, x):
                geleert += 1
    return geleert
