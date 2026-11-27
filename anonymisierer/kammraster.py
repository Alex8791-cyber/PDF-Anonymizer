"""Kammfelder auf Scans: Kästchenreihen „je Kästchen ein Zeichen“ im Bild einer Seite finden.

Formulare in Druckbuchstaben tragen ihre Werte in Kästchen (geschlossen, als Kamm mit kurzen Wänden auf einer
Grundlinie oder unten offen). Die Linien stören die Texterkennung: die Seitenaufteilung von Tesseract (PSM 3) hält
Kästchenreihen für Grafik und verwirft ganze Blöcke samt Werten und Feldnamen, und was sie liest, ist mit „|“
durchsetzt („Rı ZZ O“). Gemessen auf neun Kammfeld-Scans der Entwicklungskorpora (150-300 dpi, JPEG, Rauschen, Fax
204 x 98 dpi): ohne Linien liest die OCR 70 von 92 Werten genau und überdeckt jedes gefüllte Kästchen mit einem Wort
(779/779), vorher fast keinen.

Erkennung (numpy, auf einem Bild mit ERKENNUNG_DPI, Minimum je Pixelblock – dünne Linien bleiben erhalten):
  1. Waagerechte Linien: Tintenläufe ab LINIE_MIN_MM (Lücken bis 4 Pixel geschlossen – Faxe übertragen Linien
     punktiert), dünner als LINIE_MAX_DICKE_MM, flacher als ~3°; Mittellinie als Gerade (Schräglage).
  2. Wände: senkrechte Striche, die an der Linie ansetzen (nach oben und nach unten), STRICH_MIN_MM bis
     STRICH_MAX_MM lang und schmal.
  3. Kästchen: Folgen von Wänden gleicher Teilung (TEILUNG_MIN_MM bis TEILUNG_MAX_MM, ±TEILUNG_TOLERANZ) und
     ähnlicher Höhe; Gruppenlücken (IBAN in Vierergruppen) erlaubt. Bruchstücke derselben Zeile (Ober- und
     Unterkante, unterbrochene Linien und Wände) werden verbunden, fehlende Kästchen auf dem Raster ergänzt; ein Feld
     hat mindestens MIN_KAESTEN Kästchen – zwei nur mit einem Feld derselben Bauart in seiner Zeile (geteiltes Datum
     „Tag [..] Monat [..] Jahr [....]“, Hausnummer neben der Straße).
  4. Gegenkante (geschlossene Kästchen): erkannte Linie in der erwarteten Lage oder Tinte entlang der Kante.
  5. Ohne durchgehende Linie (Fax 204 x 98 dpi: dünne Linien kommen nur stückweise an): Wände ab WAND_MIN_MM, gleich
     hoch und in regelmäßiger Teilung, je Kästchen Tinte an Ober- oder Unterkante (_wandfelder).
Nicht erkannt (bewusst): einzelne Kästchen und Paare ohne gleichartiges Feld daneben (Ankreuzfelder), unregelmäßige
Tabellen, Raster ohne Linie.

Öffentliche Schnittstelle:
    kammfelder_finden(grau, dpi) -> [Kammfeld]          Pixel des Bilds (2D uint8, Schrift dunkel)
    linien_entfernen(grau, felder)                      Wände und Linien weiß übermalen (in place)
    fuellung_bestimmen(grau, felder, dpi) -> [Kammfeld] gefuellt je Kästchen (Tinte im Innenraum)
    nur_felder(grau, felder) -> Bild                    weißes Bild, nur die Felder (für den zweiten OCR-Lauf)
    feld_bereich(feld) -> (x0, y0, x1, y1)              Rahmen samt Innenräumen
    verfuegbar() -> bool                                numpy vorhanden (sonst finden die Funktionen nichts)
Felder in Seitenkoordinaten (Wörterbücher {"rahmen", "kaesten", "gefuellt", "offen"}, ocr.py):
    im_feld(feld, x, y) -> bool                         liegt der Punkt in einem Kästchen (samt Wand)?
    kopfkasten(feld) -> (x0, y0, x1, y1)                erstes Kästchen (Zeile und Anfang des Felds)
Felder ohne Personenbezug (geteilt von Erkennung und Selbstkontrolle, wie kennungsformen.py):
    wert_ohne_personenbezug(feldname, wert) -> bool     Feldname ohne Personenbezug (Antragsdatum, Anzahl, Betrag,
                                                        Kilometerstand, Tarifgruppe …) UND der Wert hat dessen Form
Ein schräg gelesenes Feld ist in Seitenkoordinaten ein schräges Band – sein umschließendes Rechteck („rahmen“) reicht
bei langen Feldern bis in die Zeile darüber (330 pt bei 1,7°: 10 pt). Wer fragt, ob ein Wort im Feld steht, fragt
deshalb die Kästchen, nicht den Rahmen.
"""
from __future__ import annotations

import bisect
import datetime
import math
import re
from typing import NamedTuple

ERKENNUNG_DPI = 150          # Linien werden auf einem verkleinerten Bild gesucht (Minimum je Pixelblock)
LINIE_MIN_MM = 10.0          # eine waagerechte Linie ist mindestens so lang (drei Kästchen ab 3,3 mm)
LINIE_MAX_DICKE_MM = 1.2     # dicker: Balken, Fläche, Schrift – keine Linie
WAND_FREI_MM = 0.5           # neben einer Kästchenwand bleibt so breit Papier (das Zeichen steht in der Mitte) …
WAND_FREI_ANTEIL = 0.75      # … in so vielen ihrer Zeilen (Median über die Wände); Buchstaben einer Textzeile haben
                             # neben ihren Grundstrichen Bögen und Querstriche (gemessen: Textzeilen auf Scans und
                             # Faxen 0,25–0,67, Kämme mit Block- und Handschrift 0,88–1,0)
WAND_BELEG_ANTEIL = 0.6      # ein Feld trägt an so vielen seiner Kästchengrenzen eine erkannte Wand – Bruchstücke einer
                             # Textzeile, auf dem Raster verbunden und verlängert, nicht (4 Wände für 32 „Kästchen“, 3 für
                             # 12 in 20-pt-Schrift; Grund- und Serifenlinie einer Antiqua als „zwei Linien“: 3 für 17).
                             # Gemessen an 57 Kammfeld-Scans: echte Felder 0,8 und mehr
SCHWAERZUNG_GRAU = (200, 249)  # Grauwerte der Schwärzungsrechtecke einer Ausgabe (schwaerzung.FUELLFARBE: 235); ein Feld
                             # mit zwei Linien, dessen Kästchen darunter liegen, gilt ohne Wandbeleg (Kontroll-OCR)
MIN_KAESTEN_WAND = 4         # ein Feld nur aus Wänden (ohne Ober- und Unterlinie, nicht offen) hat mindestens so viele
                             # Kästchen – drei sind auch "1111" in großer Schrift
KAMM_MAX_DICKE_MM = 0.8      # Kamm (Grundlinie mit kurzen Wänden nach oben): die Linie höchstens so dick – eine
                             # Schreiblinie, auf der Handschrift steht, ist dicker (die Buchstaben berühren sie;
                             # gemessen: Kämme 0,17–0,51 mm, Schreiblinien mit Handschrift 1,19 mm)
STRICH_MIN_MM = 1.5          # Kästchenwand (senkrechter Strich an der Linie): mindestens so lang …
STRICH_MAX_MM = 15.0         # … höchstens so lang
STRICH_MAX_BREITE_MM = 1.0   # … und höchstens so breit
TEILUNG_MIN_MM = 3.0         # Kästchenbreite (Mitte zu Mitte)
TEILUNG_MAX_MM = 12.0
TEILUNG_TOLERANZ = 0.15      # Abweichung der Kästchenbreiten von ihrem Median
HOEHE_TOLERANZ = 0.30        # Abweichung benachbarter Wandhöhen
MIN_KAESTEN = 3              # ein Feld hat mindestens drei Kästchen …
MIN_TEIL = 2                 # … Bruchstücke ab zwei Kästchen zählen nur, wenn sie sich zu einem Feld verbinden oder
                             # ein Feld derselben Bauart in ihrer Zeile steht (_zeilen_geschwister)
ZWEIER_TOLERANZ = 0.2        # Teilung und Kästchenhöhe eines Zweierfelds und seines Nachbarn: höchstens so verschieden
KURZ_ANTEIL = 0.8            # Wände kürzer als 0,8 x Teilung: Kamm (offene Seite, die Zeichen ragen hinaus)
TINTE_ABSTAND = 45           # Tinte: so viel dunkler als das Papier (75. Perzentil) …
TINTE_MAX = 185              # … und höchstens so hell
GEGENLINIE_ANTEIL = 0.5      # so viel der Gegenkante muss Tinte tragen, damit sie als Linie gilt
LINIE_KONZENTRATION = 0.8    # so viel Tinte ihres Bands liegt bei einer Linie dicht an der Geraden (Text: verteilt)
INNEN_MIN_MM = 2.0           # ein Kästchen muss ein Zeichen fassen können: Innenraum mindestens so hoch
WAND_MIN_MM = 4.0            # Wände ohne durchgehende Linie (Fax): mindestens so hoch (höher als Druckbuchstaben) …
WAND_KANTE_ANTEIL = 0.4      # … und je Kästchen trägt die Ober- oder Unterkante zu diesem Anteil Tinte …
WAND_KANTE_KAESTEN = 0.4     # … bei so vielen Kästchen des Felds (Fax mit Schräglage: die Kanten nur stückweise) …
WAND_KANTE_BAND_MM = 0.7     # … gesucht so weit über und unter dem Wandende (Fax: eine Faxzeile 0,26 mm, Schräglage)
FUELLUNG_MIN_MM2 = 0.4       # gefülltes Kästchen: mindestens so viel Tinte (mm²) im Innenraum …
FUELLUNG_MIN_ANTEIL = 0.015  # … und dieser Anteil seiner Fläche (Staub, JPEG-Reste und Linienreste zählen nicht)


class Kammfeld(NamedTuple):
    """Ein Kammfeld in Pixeln des untersuchten Bilds.
    kaesten: Innenräume [(x0, y0, x1, y1)] von links nach rechts; rahmen: (x0, y0, x1, y1) samt Wänden;
    gefuellt: je Kästchen Tinte im Innenraum (fuellung_bestimmen); waende: senkrechte Striche [(x0, y0, x1, y1)];
    linien: waagerechte Linien [(a, b, dicke, x0, x1)] mit Mittellinie y = a * x + b; offen: "" (geschlossen),
    "oben" (Kamm: kurze Wände stehen auf der Grundlinie) oder "unten" (kurze Wände hängen an der Oberkante);
    zwei_linien: Ober- und Unterkante als durchgehende Linien erkannt (sonst nur Wände oder eine Linie)."""
    kaesten: list
    rahmen: tuple
    gefuellt: list
    waende: list
    linien: list
    offen: str
    zwei_linien: bool = False


def _np():
    try:
        import numpy
        return numpy
    except Exception:          # numpy fehlt (kommt sonst mit PyMuPDF 2.x und spaCy): keine Kammfelder
        return None


def verfuegbar() -> bool:
    return _np() is not None


def _verkleinern(np, grau, faktor: int):
    """Minimum je Block faktor x faktor. Über versetzte Teilbilder statt reshape(...).min(axis=(1, 3)) – das Ergebnis
    ist dasselbe, die Laufzeit bei 300 dpi ein Zehntel (Abnahme 4 AB4U-08: die Hälfte der Suche)."""
    if faktor <= 1:
        return grau
    h, w = grau.shape
    h2, w2 = h // faktor, w // faktor
    g = grau[:h2 * faktor, :w2 * faktor]
    aus = np.array(g[0::faktor, 0::faktor])
    for i in range(faktor):
        for j in range(faktor):
            if i or j:
                np.minimum(aus, g[i::faktor, j::faktor], out=aus)
    return aus


def _perzentil_75(np, bild) -> float:
    """np.percentile(bild, 75) (lineare Interpolation) für ein uint8-Bild über das Histogramm – ohne Sortieren."""
    if bild.dtype != np.uint8:
        return float(np.percentile(bild, 75))
    zaehlung = np.cumsum(np.bincount(bild.ravel(), minlength=256))
    n = int(zaehlung[-1])
    if n == 0:
        return 0.0
    pos = 0.75 * (n - 1)
    k = int(pos)
    unten = int(np.searchsorted(zaehlung, k, side="right"))
    oben = int(np.searchsorted(zaehlung, min(k + 1, n - 1), side="right"))
    return float(unten + (pos - k) * (oben - unten))


def _laeufe(np, maske):
    """Waagerechte Läufe von True: Arrays (zeile, start, ende) – ende exklusiv, zeilenweise geordnet."""
    h, w = maske.shape
    p = np.zeros((h, w + 2), dtype=np.int8)
    p[:, 1:-1] = maske
    d = np.diff(p, axis=1)
    sz, ss = np.nonzero(d == 1)
    _, ee = np.nonzero(d == -1)
    return sz, ss, ee


def _waagerecht_schliessen(np, maske, luecke: int):
    """Lücken bis `luecke` Pixel in waagerechten Läufen füllen (ein Bild schmaler als die Lücke bleibt, wie es ist)."""
    aus = maske.copy()
    w = maske.shape[1]
    for k in range(2, min(luecke + 2, w)):   # k = Abstand zweier Tintenpixel über die Lücke
        beide = np.zeros_like(maske)
        beide[:, :w - k] = maske[:, :w - k] & maske[:, k:]
        for j in range(1, k):
            aus[:, j:w - k + j] |= beide[:, :w - k]
    return aus


def _linien(np, tinte, px_mm):
    """Waagerechte Linien: [(x0, x1, a, b, dicke)] mit Mittellinie y = a * x + b (Pixel des kleinen Bilds)."""
    dick = tinte.copy()
    dick[1:] |= tinte[:-1]
    dick[:-1] |= tinte[1:]
    dick = _waagerecht_schliessen(np, dick, 4)
    z, s, e = _laeufe(np, dick)
    lang = (e - s) >= LINIE_MIN_MM * px_mm
    gruppen, offen = [], []
    for zz, ss, ee in zip(z[lang].tolist(), s[lang].tolist(), e[lang].tolist()):
        treffer = None
        for g in offen:
            if g["z1"] >= zz - 1 and min(ee, g["x1"]) > max(ss, g["x0"]):
                treffer = g
                break
        if treffer is None:
            treffer = {"z0": zz, "z1": zz, "x0": ss, "x1": ee}
            gruppen.append(treffer)
            offen.append(treffer)
        treffer["z1"] = zz
        treffer["x0"] = min(treffer["x0"], ss)
        treffer["x1"] = max(treffer["x1"], ee)
        offen = [g for g in offen if g["z1"] >= zz - 1]
    aus = []
    for g in gruppen:
        x0, x1, y0, y1 = g["x0"], g["x1"], g["z0"], g["z1"] + 1
        band = tinte[y0:y1, x0:x1]
        n = band.sum(axis=0)
        ok = n > 0
        if ok.sum() < 0.6 * (x1 - x0):
            continue
        ys = np.arange(y0, y1, dtype=np.float64)[:, None]
        mitte = (band * ys).sum(axis=0)[ok] / n[ok]
        xs = np.arange(x0, x1, dtype=np.float64)[ok]
        a, b = (np.polyfit(xs, mitte, 1) if len(xs) > 8 and xs[-1] > xs[0] else (0.0, float(mitte.mean())))
        dicke = float(np.median(n[ok]))
        if abs(a) > 0.05 or dicke > LINIE_MAX_DICKE_MM * px_mm:
            continue                              # steiler als ~3° oder ein Balken: keine Kästchenlinie
        # eine Linie ist schmal: fast alle Tinte des Bands liegt dicht an der Geraden – eine Textzeile (deren Läufe
        # nach dem Schließen der Lücken auch lang sind) verteilt sich über die Höhe ihrer Buchstaben
        abstand = np.abs(ys - (a * np.arange(x0, x1, dtype=np.float64)[None, :] + b))
        nah = (band & (abstand <= dicke / 2.0 + 1.0)).sum()
        if nah < LINIE_KONZENTRATION * max(int(band.sum()), 1):
            continue
        aus.append((x0, x1, float(a), float(b), dicke))
    return aus


def _striche(np, tinte, linie, richtung: int, px_mm: float) -> list:
    """Senkrechte Striche, die an der Linie ansetzen und in `richtung` (-1 nach oben, +1 nach unten) laufen:
    [(x0, x1, laenge)] in Pixeln des kleinen Bilds."""
    h, w = tinte.shape
    x0, x1, a, b, dicke = linie
    hmax = int(STRICH_MAX_MM * px_mm) + 1
    xs = np.arange(x0, x1)
    ylin = a * xs + b
    versatz = int(math.ceil(dicke / 2.0))
    ks = np.arange(hmax)[:, None]
    Y = np.round(ylin[None, :] + richtung * (versatz + ks)).astype(np.int64)
    gueltig = (Y >= 0) & (Y < h)
    Yc = np.clip(Y, 0, h - 1)
    X = np.broadcast_to(xs[None, :], Y.shape)
    G = tinte[Yc, X] | tinte[Yc, np.clip(X - 1, 0, w - 1)] | tinte[Yc, np.clip(X + 1, 0, w - 1)]
    G &= gueltig
    G[1:-1] |= G[:-2] & G[2:]                     # Lücken von einem Pixel (Rauschen, JPEG)
    leer = ~G
    laenge = np.where(leer.any(axis=0), leer.argmax(axis=0), hmax)
    ist = laenge >= STRICH_MIN_MM * px_mm
    striche = []
    i, n = 0, len(xs)
    breit_max = STRICH_MAX_BREITE_MM * px_mm
    while i < n:
        if not ist[i]:
            i += 1
            continue
        j = i
        while j < n and ist[j]:
            j += 1
        if j - i <= breit_max:
            striche.append((int(xs[i]), int(xs[j - 1]) + 1, int(np.median(laenge[i:j]))))
        i = j
    return striche


def _folgen(striche: list, px_mm: float) -> list:
    """Regelmäßige Folgen von Wänden: [[(linke Wand, rechte Wand) je Kästchen]]."""
    n = len(striche)
    if n < MIN_TEIL + 1:
        return []
    mitten = [(s0 + s1) / 2.0 for s0, s1, _ in striche]
    hoehen = [hh for _, _, hh in striche]
    abst = [mitten[i + 1] - mitten[i] for i in range(n - 1)]
    tmin, tmax = TEILUNG_MIN_MM * px_mm, TEILUNG_MAX_MM * px_mm
    aus = []
    i = 0
    while i < n - 1:
        lokal = sorted(d for d in abst[i:i + 6] if tmin <= d <= tmax)
        if not lokal:
            i += 1
            continue
        teilung = lokal[len(lokal) // 2]
        kaesten = []
        j = i
        while j < n - 1:
            d = abst[j]
            if abs(d - teilung) <= TEILUNG_TOLERANZ * teilung and \
                    abs(hoehen[j] - hoehen[j + 1]) <= HOEHE_TOLERANZ * max(hoehen[j], hoehen[j + 1]):
                kaesten.append((striche[j], striche[j + 1]))
                j += 1
            elif (kaesten and d <= 0.6 * teilung and j + 2 < n
                  and abs(abst[j + 1] - teilung) <= TEILUNG_TOLERANZ * teilung):
                j += 1                            # Gruppenlücke (IBAN in Vierergruppen)
            else:
                break
        if len(kaesten) >= MIN_TEIL:
            aus.append(kaesten)
            i = j
        else:
            i += 1
    return aus


def _anteil_auf_linie(np, tinte, a, b, x0, x1) -> float:
    h, w = tinte.shape
    xs = np.arange(max(0, int(x0)), min(w, int(x1)))
    if not len(xs):
        return 0.0
    ys = np.round(a * xs + b).astype(np.int64)
    treffer = np.zeros(len(xs), dtype=bool)
    for d in (-1, 0, 1):
        yy = np.clip(ys + d, 0, h - 1)
        treffer |= tinte[yy, xs]
    return float(treffer.mean())


def _gegenlinie(np, tinte, linien, i, richtung, hoehe, xa, xb, px_mm):
    """Gegenkante eines Felds (geschlossene Kästchen): (a, b, dicke, x0, x1) der Linie gegenüber der Grundlinie i
    oder None (offenes Feld). Gesucht wird eine erkannte Linie in der erwarteten Lage, sonst Tinte entlang der
    erwarteten Kante (unterbrochene Linien eines Faxes)."""
    x0l, x1l, a, b, dicke = linien[i]
    xm = (xa + xb) / 2.0
    erwartet = a * xm + b + richtung * (math.ceil(dicke / 2.0) + hoehe - dicke / 2.0)
    toleranz = max(3.0, 0.2 * hoehe)
    beste = None
    for j, (x0, x1, a2, b2, d2) in enumerate(linien):
        if j == i:
            continue
        abstand = abs(a2 * xm + b2 - erwartet)
        if abstand <= toleranz and min(x1, xb) - max(x0, xa) >= 0.5 * (xb - xa):
            if beste is None or abstand < beste[0]:
                beste = (abstand, (a2, b2, d2, x0, x1))
    if beste is not None:
        return beste[1]
    besser = None
    for d in range(-int(toleranz), int(toleranz) + 1):
        b2 = erwartet - a * xm + d
        anteil = _anteil_auf_linie(np, tinte, a, b2, xa, xb)
        if besser is None or anteil > besser[0]:
            besser = (anteil, b2)
    if besser is not None and besser[0] >= GEGENLINIE_ANTEIL:
        return (a, besser[1], dicke, xa, xb)
    return None


def _zusammenlegen(folgen: list) -> list:
    """Folgen derselben Linie und Richtung, die mit gleicher Teilung aneinander anschließen (fehlende Wand dazwischen,
    unterbrochene Linie), zu einer Folge verbinden; fehlende Kästchen werden auf dem Raster ergänzt."""
    if len(folgen) < 2:
        return folgen
    folgen = sorted(folgen, key=lambda f: f[0][0][0])
    aus = [folgen[0]]
    for f in folgen[1:]:
        vorige = aus[-1]
        t1 = (vorige[-1][1][0] + vorige[-1][1][1]) / 2.0 - (vorige[-1][0][0] + vorige[-1][0][1]) / 2.0
        t2 = (f[0][1][0] + f[0][1][1]) / 2.0 - (f[0][0][0] + f[0][0][1]) / 2.0
        teilung = (t1 + t2) / 2.0
        ende = (vorige[-1][1][0] + vorige[-1][1][1]) / 2.0
        anfang = (f[0][0][0] + f[0][0][1]) / 2.0
        luecke = anfang - ende
        anzahl = round(luecke / teilung) if teilung > 0 else -1
        if abs(t1 - t2) <= TEILUNG_TOLERANZ * teilung and 0 <= anzahl <= 4 and \
                abs(luecke - anzahl * teilung) <= max(0.25 * teilung, 0.2 * teilung * anzahl):
            fuell = []
            wand = vorige[-1][1]
            hoehe = min(vorige[-1][0][2], f[0][0][2])
            for k in range(1, anzahl + 1):
                mitte = ende + k * luecke / max(anzahl, 1)
                neue = (int(mitte) - 1, int(mitte) + 1, hoehe) if k < anzahl else f[0][0]
                fuell.append((wand, neue))
                wand = neue
            aus[-1] = vorige + fuell + f
        else:
            aus.append(f)
    return aus


def _waende(np, tinte, px_mm: float) -> list:
    """Senkrechte Striche von WAND_MIN_MM bis STRICH_MAX_MM Länge, höchstens STRICH_MAX_BREITE_MM breit:
    [(x0, x1, y0, y1)] (ende exklusiv)."""
    t = tinte.copy()
    t[1:-1] |= tinte[:-2] & tinte[2:]              # Lücken von einem Pixel
    sx, sy0, sy1 = _laeufe(np, t.T)                 # Läufe je Spalte: (x, y0, y1)
    lang = ((sy1 - sy0) >= WAND_MIN_MM * px_mm) & ((sy1 - sy0) <= STRICH_MAX_MM * px_mm)
    laeufe = sorted(zip(sx[lang].tolist(), sy0[lang].tolist(), sy1[lang].tolist()))
    striche, offen = [], []
    for x, y0, y1 in laeufe:
        ziel = None
        for st in offen:
            if st[1] >= x - 1 and min(y1, st[3]) - max(y0, st[2]) > 0.7 * min(y1 - y0, st[3] - st[2]):
                ziel = st
                break
        if ziel is None:
            ziel = [x, x + 1, y0, y1]
            striche.append(ziel)
        else:
            ziel[1] = x + 1
            ziel[2], ziel[3] = min(ziel[2], y0), max(ziel[3], y1)
        offen = [st for st in striche if st[1] >= x - 1]
    # Fax: eine Wand, die das Rauschen in zwei Stücke geteilt hat, die sich in der Höhe überlappen (y 317-358 und
    # 336-372, eine Spalte versetzt), ist EINE Wand – sonst passen Ober- und Unterkante nicht zu den Nachbarn
    ganz: list = []
    for st in sorted(striche):
        for g in ganz:
            if st[0] <= g[1] + 1 and g[0] <= st[1] + 1 and min(st[3], g[3]) - max(st[2], g[2]) > 0:
                g[0], g[1], g[2], g[3] = min(g[0], st[0]), max(g[1], st[1]), min(g[2], st[2]), max(g[3], st[3])
                break
        else:
            ganz.append(list(st))
    return [tuple(st) for st in ganz if st[1] - st[0] <= STRICH_MAX_BREITE_MM * px_mm
            and st[3] - st[2] <= STRICH_MAX_MM * px_mm]


def _kante_anteil(np, tinte, x0: int, x1: int, y: int, h: int, rand: int = 2) -> float:
    """Anteil der Spalten x0..x1 mit Tinte in den Zeilen y-rand..y+rand (eine waagerechte Kante, auch punktiert)."""
    if x1 <= x0:
        return 0.0
    band = tinte[max(0, y - rand):min(h, y + rand + 1), x0:x1]
    return float(band.any(axis=0).mean()) if band.size else 0.0


def _wandfelder(np, tinte, px_mm: float) -> list:
    """Kästchenreihen aus ihren Wänden, ohne durchgehende Linie (Fax: Linien punktiert oder nur stückweise
    übertragen): Wände gleicher Höhe (Ober- und Unterkante je Nachbar höchstens 3 Pixel versetzt), regelmäßige Teilung,
    und je Kästchen Tinte an der Ober- oder Unterkante. [(Kästchen [(x0, y0, x1, y1)], Wände, oben, unten)] in Pixeln
    des kleinen Bilds; oben/unten: (a, b) der Kanten y = a * x + b."""
    h = tinte.shape[0]
    band = max(2, int(round(WAND_KANTE_BAND_MM * px_mm)))
    striche = sorted(_waende(np, tinte, px_mm))
    if len(striche) < MIN_KAESTEN + 1:
        return []
    # Ketten: Nachbarn rechts (höchstens TEILUNG_MAX_MM) mit gleicher Ober- und Unterkante
    naechster: dict = {}
    for i, a in enumerate(striche):
        for j in range(i + 1, len(striche)):
            b = striche[j]
            if b[0] - a[1] > TEILUNG_MAX_MM * px_mm:
                break
            if abs(b[2] - a[2]) <= 3 and abs(b[3] - a[3]) <= 3:
                naechster[i] = j
                break
    hat_vorgaenger = set(naechster.values())
    aus = []
    for start in range(len(striche)):
        if start in hat_vorgaenger or start not in naechster:
            continue
        kette, i = [striche[start]], start
        while i in naechster:
            i = naechster[i]
            kette.append(striche[i])
        for kaesten in _folgen([(x0, x1, y1 - y0) for x0, x1, y0, y1 in kette], px_mm):
            enden = {(st[0], st[1]) for k in kaesten for st in k}      # linke und rechte Wände (Gruppenlücken)
            waende_px = sorted(w for w in kette if (w[0], w[1]) in enden)
            innen, kanten = [], 0
            for (l0, l1, _), (r0, r1, _) in kaesten:
                wl = next(w for w in waende_px if w[0] == l0)
                wr = next(w for w in waende_px if w[0] == r0)
                y0, y1 = max(wl[2], wr[2]), min(wl[3], wr[3])
                if max(_kante_anteil(np, tinte, l1, r0, y0, h, band), _kante_anteil(np, tinte, l1, r0, y1 - 1, h, band)) \
                        >= WAND_KANTE_ANTEIL:
                    kanten += 1
                innen.append((l1, y0, r0, y1))
            if kanten < WAND_KANTE_KAESTEN * len(kaesten):
                continue                          # Striche ohne Kanten: Schrift, Strichcode, kein Kästchen
            xs = np.array([(w[0] + w[1]) / 2.0 for w in waende_px])
            oben = np.polyfit(xs, np.array([w[2] for w in waende_px], dtype=float), 1) if len(xs) > 1 else (0.0, 0.0)
            unten = np.polyfit(xs, np.array([w[3] for w in waende_px], dtype=float), 1) if len(xs) > 1 else (0.0, 0.0)
            aus.append((innen, waende_px, (float(oben[0]), float(oben[1])), (float(unten[0]), float(unten[1]))))
    return aus


def kammfelder_finden(grau, dpi: float) -> list:
    """Kammfelder in einem Graustufenbild (2D uint8, Schrift dunkel) mit der Auflösung dpi. Rückgabe: [Kammfeld] in
    Pixeln des Bilds (gefuellt leer – siehe fuellung_bestimmen), von oben nach unten. Ohne numpy: []."""
    np = _np()
    if np is None or grau is None or grau.size == 0 or dpi <= 0:
        return []
    faktor = max(1, int(round(dpi / ERKENNUNG_DPI)))
    klein = _verkleinern(np, grau, faktor)
    px_mm = dpi / faktor / 25.4
    if klein.ndim != 2 or min(klein.shape) < 2 or klein.shape[1] < LINIE_MIN_MM * px_mm:
        return []                                 # kleiner als eine Linie: kein Kammfeld (Abnahme 4 AB4U-10)
    papier = _perzentil_75(np, klein)
    tinte = klein < min(TINTE_MAX, papier - TINTE_ABSTAND)
    linien = _linien(np, tinte, px_mm)
    kandidaten = []
    for i, linie in enumerate(linien):
        for richtung in (-1, 1):
            for kaesten in _zusammenlegen(_folgen(_striche(np, tinte, linie, richtung, px_mm), px_mm)):
                kandidaten.append((i, richtung, kaesten))
    felder = []
    f = faktor
    for i, richtung, kaesten in sorted(kandidaten, key=lambda k: -len(k[2])):
        x0l, x1l, a, b, dicke = linien[i]
        hoehe = sorted(min(l[2], r[2]) for l, r in kaesten)[len(kaesten) // 2]
        xa, xb = kaesten[0][0][0], kaesten[-1][1][1]
        ym = a * (xa + xb) / 2.0 + b
        ya, yb = sorted((ym, ym + richtung * (hoehe + dicke)))
        gegen = _gegenlinie(np, tinte, linien, i, richtung, hoehe, xa, xb, px_mm)
        rand = dicke / 2.0 + 1.0
        linien_f = [(a, b * f + (f - 1) / 2.0, dicke * f, min(x0l, xa) * f, max(x1l, xb) * f)]
        if gegen is not None:
            ga, gb, gd, gx0, gx1 = gegen
            linien_f.append((ga, gb * f + (f - 1) / 2.0, gd * f, min(gx0, xa) * f, max(gx1, xb) * f))
        teilung = (xb - xa) / max(1, len(kaesten))
        innen, waende = [], []
        for (l0, l1, lh), (r0, r1, rh) in kaesten:
            mx = (l1 + r0) / 2.0
            yl = a * mx + b
            if gegen is not None:
                yg = gegen[0] * mx + gegen[1]
                ys = sorted((yl + richtung * rand, yg - richtung * (gegen[2] / 2.0 + 1.0)))
            elif hoehe < KURZ_ANTEIL * teilung:          # Kamm mit kurzen Wänden: die Zeichen ragen darüber hinaus
                ys = sorted((yl + richtung * rand, yl + richtung * (max(lh, rh, 0.9 * teilung) + rand)))
            else:                                 # Wände bis zur (nicht erkannten) Gegenkante
                ende = math.ceil(dicke / 2.0) + max(lh, rh) - dicke - 1.0
                ys = sorted((yl + richtung * rand, yl + richtung * max(ende, rand + 2)))
            innen.append((l1 * f, int(ys[0] * f), r0 * f, int(math.ceil(ys[1] * f))))
        for s0, s1, sh in [k[0] for k in kaesten] + [kaesten[-1][1]]:
            yl = a * (s0 + s1) / 2.0 + b
            ys = sorted((yl - richtung * rand, yl + richtung * (sh + rand)))
            waende.append(((s0 - 1) * f, int(ys[0] * f), (s1 + 1) * f, int(math.ceil(ys[1] * f))))
        if gegen is not None:
            yg = gegen[0] * (xa + xb) / 2.0 + gegen[1]
            ya, yb = sorted((ym - richtung * dicke / 2.0, yg + richtung * gegen[2] / 2.0))
        rahmen = (xa * f, int(ya * f), xb * f, int(math.ceil(yb * f)))
        kurz = hoehe < KURZ_ANTEIL * teilung
        offen = "" if gegen is not None or not kurz else ("oben" if richtung < 0 else "unten")
        if offen == "oben" and (dicke > KAMM_MAX_DICKE_MM * px_mm
                                or _waende_frei(np, tinte, kaesten, a, b, dicke, richtung, px_mm) < WAND_FREI_ANTEIL):
            continue                              # Schreiblinie mit Handschrift darauf, Textzeile: kein Kamm
        if sorted(k[3] - k[1] for k in innen)[len(innen) // 2] < INNEN_MIN_MM * px_mm * f:
            continue                              # zu flach für ein Zeichen (Schriftzeile, Raster)
        felder.append(Kammfeld(innen, rahmen, [], waende, linien_f, offen, gegen is not None))
    for innen, waende_px, oben, unten in _wandfelder(np, tinte, px_mm):
        rand = 1.5
        kaesten_f = [(int((x0 + 1) * f), int((y0 + rand) * f), int(x1 * f), int(math.ceil((y1 - rand) * f)))
                     for x0, y0, x1, y1 in innen]
        if sorted(k[3] - k[1] for k in kaesten_f)[len(kaesten_f) // 2] < INNEN_MIN_MM * px_mm * f:
            continue
        xa, xb = waende_px[0][0], waende_px[-1][1]
        linien_f = [(a, b * f + (f - 1) / 2.0, 2.0 * f, xa * f, xb * f) for a, b in (oben, unten)]
        waende_f = [((w[0] - 1) * f, (w[2] - 1) * f, (w[1] + 1) * f, (w[3] + 1) * f) for w in waende_px]
        rahmen = (xa * f, min(w[2] for w in waende_px) * f, xb * f, max(w[3] for w in waende_px) * f)
        felder.append(Kammfeld(kaesten_f, rahmen, [], waende_f, linien_f, ""))
    verbunden = _felder_verbinden(sorted(felder, key=lambda k: (k.rahmen[0], k.rahmen[1])))
    verbunden = _felder_verbinden([_verlaengern(np, tinte, k, f) for k in verbunden])
    gueltig = [k for k in verbunden if len(k.kaesten) >= MIN_TEIL
               and (_wandbeleg(k) >= WAND_BELEG_ANTEIL or (k.zwei_linien and _geschwaerzt(np, grau, k)))
               and (k.zwei_linien or k.offen or len(k.kaesten) >= MIN_KAESTEN_WAND)]
    return [k for k in gueltig if len(k.kaesten) >= MIN_KAESTEN or _zeilen_geschwister(k, gueltig)]


def _zeilen_geschwister(feld, felder: list) -> bool:
    """Steht in derselben Zeile ein anderes Feld derselben Bauart (Teilung, Kästchenhöhe, offen/zwei Linien)? Dann zählt
    auch ein Feld aus zwei Kästchen – die Teile eines geteilten Datums („Tag [..] Monat [..] Jahr [....]“) oder eine
    Hausnummer neben der Straße (Abnahme 4 AB4-01: zwei Kästchen „Tag“ und „Monat“ blieben ungelesen und still)."""
    t = _teilung(feld)
    y0, y1 = _hoehe(feld)
    h = y1 - y0
    if t <= 0 or h <= 0:
        return False
    for g in felder:
        if g is feld or g.offen != feld.offen or g.zwei_linien != feld.zwei_linien:
            continue
        tg = _teilung(g)
        g0, g1 = _hoehe(g)
        hg = g1 - g0
        if tg <= 0 or hg <= 0 or abs(tg - t) > ZWEIER_TOLERANZ * t or abs(hg - h) > ZWEIER_TOLERANZ * h:
            continue
        if min(y1, g1) - max(y0, g0) >= 0.6 * min(h, hg):
            return True
    return False


def _geschwaerzt(np, grau, feld) -> bool:
    """Liegt ein Kästchen zur Hälfte unter einer gleichmäßig grauen Fläche – dem Schwärzungsrechteck einer Ausgabe, das
    die Wände verdeckt? Gleichmäßig heißt: jedes Pixel gleich seinen vier Nachbarn (Scans rauschen, Papier ist weiß)."""
    for x0, y0, x1, y1 in feld.kaesten:
        teil = grau[max(0, y0):max(0, y1), max(0, x0):max(0, x1)].astype(np.int16)
        if teil.shape[0] < 3 or teil.shape[1] < 3:
            continue
        mitte = teil[1:-1, 1:-1]
        flach = ((mitte == teil[:-2, 1:-1]) & (mitte == teil[2:, 1:-1]) & (mitte == teil[1:-1, :-2])
                 & (mitte == teil[1:-1, 2:]) & (mitte >= SCHWAERZUNG_GRAU[0]) & (mitte <= SCHWAERZUNG_GRAU[1]))
        if flach.mean() >= 0.5:
            return True
    return False


def _wandbeleg(feld) -> float:
    """Anteil der Kästchengrenzen eines Felds (n Kästchen: n + 1), an denen eine Wand erkannt wurde (dieselbe Wand aus
    zwei Bruchstücken zählt einmal)."""
    t = _teilung(feld) or 1.0
    mitten = sorted((w[0] + w[2]) / 2.0 for w in feld.waende)
    eigene = []
    for m in mitten:
        if not eigene or m - eigene[-1] > 0.3 * t:
            eigene.append(m)
    return len(eigene) / float(len(feld.kaesten) + 1)


def _waende_frei(np, tinte, kaesten, a: float, b: float, dicke: float, richtung: int, px_mm: float) -> float:
    """Median über die Wände: Anteil ihrer Zeilen (von der Linie bis zum Wandende), in denen links und rechts neben der
    Wand WAND_FREI_MM breit keine Tinte steht (ein Abstand von einem Pixel zählt zur Wand)."""
    h, w = tinte.shape
    breite = max(2, int(round(WAND_FREI_MM * px_mm)))
    werte = []
    for s0, s1, sh in [k[0] for k in kaesten] + [kaesten[-1][1]]:
        yl = a * (s0 + s1) / 2.0 + b
        ya, yb = sorted((yl + richtung * (dicke / 2.0 + 1.0), yl + richtung * sh))
        ya, yb = max(0, int(round(ya))), min(h, int(round(yb)))
        if yb - ya < 2:
            continue
        links = tinte[ya:yb, max(0, s0 - 1 - breite):max(0, s0 - 1)]
        rechts = tinte[ya:yb, min(w, s1 + 1):min(w, s1 + 1 + breite)]
        frei = ~(links.any(axis=1) if links.size else np.zeros(yb - ya, dtype=bool))
        frei &= ~(rechts.any(axis=1) if rechts.size else np.zeros(yb - ya, dtype=bool))
        werte.append(float(frei.mean()))
    return float(np.median(werte)) if werte else 0.0


def _kasten_beleg(np, tinte, x0: float, y0: float, x1: float, y1: float, aussen: int) -> bool:
    """Steht im kleinen Bild an dieser Stelle ein Kästchen? Eine Wand an seiner äußeren Kante (aussen +1: rechts,
    -1: links – die innere Kante ist die Wand des Nachbarn) mit Tinte über mindestens 40 % der Höhe, oder eine
    Ober- bzw. Unterkante mit Tinte über mindestens der Hälfte der Breite."""
    h, w = tinte.shape
    xa, xb, ya, yb = int(x0), int(math.ceil(x1)), int(y0), int(math.ceil(y1))
    if xa < 0 or ya < 0 or xb > w or yb > h or xb - xa < 3 or yb - ya < 3:
        return False
    rand = max(2, (xb - xa) // 6)
    kante = xb if aussen > 0 else xa
    wand = tinte[ya:yb, max(0, kante - rand):min(w, kante + rand)]
    if wand.size and wand.sum(axis=0).max() >= 0.4 * (yb - ya):
        return True
    return max(_kante_anteil(np, tinte, xa, xb, ya, h), _kante_anteil(np, tinte, xa, xb, yb - 1, h)) >= 0.5


def _verlaengern(np, tinte, feld, f: int):
    """Ein Feld nach rechts und links auf seinem Raster verlängern, solange dort Kästchen stehen (_kasten_beleg) – ein
    Fax verliert einzelne Wände und Linienstücke, die erkannten Bruchstücke enden dann vor dem Feldende."""
    t = _teilung(feld)
    if not t or len(feld.kaesten) < MIN_TEIL:
        return feld
    kaesten = list(feld.kaesten)
    for richtung in (1, -1):
        for _ in range(40):
            k = kaesten[-1] if richtung > 0 else kaesten[0]
            neu = (k[0] + richtung * t, k[1], k[2] + richtung * t, k[3])
            if not _kasten_beleg(np, tinte, neu[0] / f, (neu[1] - 2 * f) / f, neu[2] / f, (neu[3] + 2 * f) / f,
                                 richtung):
                break
            if richtung > 0:
                kaesten.append(tuple(int(round(v)) for v in neu))
            else:
                kaesten.insert(0, tuple(int(round(v)) for v in neu))
    if len(kaesten) == len(feld.kaesten):
        return feld
    rahmen = (min(feld.rahmen[0], kaesten[0][0]), feld.rahmen[1], max(feld.rahmen[2], kaesten[-1][2]), feld.rahmen[3])
    return feld._replace(kaesten=kaesten, rahmen=rahmen)


def _teilung(feld) -> float:
    mitten = [(k[0] + k[2]) / 2.0 for k in feld.kaesten]
    abst = sorted(b - a for a, b in zip(mitten, mitten[1:]))
    return abst[len(abst) // 2] if abst else 0.0


def _hoehe(feld) -> tuple:
    ys0 = sorted(k[1] for k in feld.kaesten)
    ys1 = sorted(k[3] for k in feld.kaesten)
    return ys0[len(ys0) // 2], ys1[len(ys1) // 2]


def _verbindbar(g, f) -> bool:
    tg, tf = _teilung(g), _teilung(f)
    if not tg or not tf or abs(tg - tf) > TEILUNG_TOLERANZ * max(tg, tf):
        return False
    (g0, g1), (f0, f1) = _hoehe(g), _hoehe(f)
    if min(g1, f1) - max(g0, f0) < 0.6 * max(1, min(g1 - g0, f1 - f0)):
        return False                              # nicht dieselbe Zeile
    t = (tg + tf) / 2.0
    if min(g.rahmen[2], f.rahmen[2]) > max(g.rahmen[0], f.rahmen[0]):
        return True                               # überlappende Bruchstücke
    links, rechts = (g, f) if g.rahmen[0] < f.rahmen[0] else (f, g)
    if rechts.kaesten[0][0] - links.kaesten[-1][2] <= 0.6 * t:
        return True                               # Gruppenlücke (IBAN in Vierergruppen)
    d = ((rechts.kaesten[0][0] + rechts.kaesten[0][2]) - (links.kaesten[-1][0] + links.kaesten[-1][2])) / 2.0 / t
    return 1 <= round(d) <= 5 and abs(d - round(d)) <= 0.3


def _verbinden(g, f):
    t = (_teilung(g) + _teilung(f)) / 2.0
    kaesten = []
    for k in sorted(g.kaesten + f.kaesten, key=lambda k: k[0] + k[2]):
        if kaesten and abs((k[0] + k[2]) - (kaesten[-1][0] + kaesten[-1][2])) / 2.0 < 0.5 * t:
            v = kaesten[-1]                       # dasselbe Kästchen aus zwei Bruchstücken
            kaesten[-1] = (max(v[0], k[0]), min(v[1], k[1]), min(v[2], k[2]), max(v[3], k[3]))
            continue
        if kaesten:
            v = kaesten[-1]
            d = ((k[0] + k[2]) - (v[0] + v[2])) / 2.0 / t
            n = round(d)
            if n >= 2 and abs(d - n) <= 0.3:      # fehlende Wände: Kästchen auf dem Raster ergänzen
                breite = ((v[2] - v[0]) + (k[2] - k[0])) / 2.0
                for j in range(1, n):
                    m = (v[0] + v[2]) / 2.0 + j * ((k[0] + k[2]) - (v[0] + v[2])) / 2.0 / n
                    kaesten.append((int(m - breite / 2.0), min(v[1], k[1]), int(math.ceil(m + breite / 2.0)),
                                    max(v[3], k[3])))
        kaesten.append(k)
    rahmen = (min(g.rahmen[0], f.rahmen[0]), min(g.rahmen[1], f.rahmen[1]),
              max(g.rahmen[2], f.rahmen[2]), max(g.rahmen[3], f.rahmen[3]))
    offen = "" if "" in (g.offen, f.offen) else g.offen
    return Kammfeld(kaesten, rahmen, [], g.waende + f.waende, g.linien + f.linien, offen, g.zwei_linien or f.zwei_linien)


def _felder_verbinden(felder: list) -> list:
    """Bruchstücke eines Felds verbinden – dasselbe Feld von Ober- und Unterkante aus, unterbrochene Linien und
    Wände eines Faxes: gleiche Zeile, gleiche Teilung, überlappend oder mit einer Lücke von höchstens vier Kästchen auf
    dem Raster (fehlende Kästchen werden ergänzt)."""
    felder = list(felder)
    geaendert = True
    while geaendert:
        geaendert = False
        for i in range(len(felder)):
            for j in range(i + 1, len(felder)):
                if _verbindbar(felder[i], felder[j]):
                    felder[i] = _verbinden(felder[i], felder[j])
                    del felder[j]
                    geaendert = True
                    break
            if geaendert:
                break
    return sorted(felder, key=lambda k: (k.rahmen[1], k.rahmen[0]))


def linien_entfernen(grau, felder, weiss: int = 255):
    """Wände und Linien der Kammfelder im Bild (in place) mit Papierweiß übermalen; die Zeichen bleiben. Übermalt wird
    das ganze Raster: erkannte Linien auf ihrer ganzen Länge und je Kästchen die Kanten ringsum (auch dort, wo ein Fax
    die Linie nur punktiert überträgt) – außer der offenen Seite eines Kamms mit kurzen Wänden."""
    np = _np()
    if np is None or not felder:
        return grau
    h, w = grau.shape
    for f in felder:
        dicke = max([d for _, _, d, _, _ in f.linien] or [2.0])
        rand = int(math.ceil(dicke / 2.0)) + 1
        for a, b, d, x0, x1 in f.linien:
            r = int(math.ceil(d / 2.0)) + 1
            xs = np.arange(max(0, int(x0) - 1), min(w, int(math.ceil(x1)) + 2))
            ys = np.round(a * xs + b).astype(np.int64)
            for k in range(-r, r + 1):
                yy = ys + k
                ok = (yy >= 0) & (yy < h)
                grau[yy[ok], xs[ok]] = weiss
        for x0, y0, x1, y1 in f.waende:
            grau[max(0, y0):min(h, y1), max(0, x0):min(w, x1)] = weiss
        kaesten = f.kaesten
        for i, (x0, y0, x1, y1) in enumerate(kaesten):
            links = kaesten[i - 1][2] if i else x0 - 2 * rand
            rechts = kaesten[i + 1][0] if i + 1 < len(kaesten) else x1 + 2 * rand
            # Wände: vom Innenraum bis zum Nachbarn (bzw. eine Wandbreite nach außen)
            xa, xb = max(0, min(x0, links + 1) - 1), min(w, max(x1, rechts - 1) + 1)
            ya, yb = max(0, y0 - 2 * rand), min(h, y1 + 2 * rand)
            if f.offen == "oben":
                ya = max(0, y0)
            elif f.offen == "unten":
                yb = min(h, y1)
            grau[ya:yb, xa:min(w, x0 + 1)] = weiss
            grau[ya:yb, max(0, x1 - 1):xb] = weiss
            # Kanten oben und unten
            if f.offen != "oben":
                grau[max(0, y0 - 2 * rand):max(0, y0 + 1), xa:xb] = weiss
            if f.offen != "unten":
                grau[min(h, y1 - 1):min(h, y1 + 2 * rand), xa:xb] = weiss
    return grau


def fuellung_bestimmen(grau, felder, dpi: float) -> list:
    """Felder mit gefuellt je Kästchen (Bild nach linien_entfernen): Tinte im Innenraum."""
    np = _np()
    if np is None or not felder:
        return felder
    papier = _perzentil_75(np, grau)
    schwelle = min(TINTE_MAX, papier - TINTE_ABSTAND)
    px_mm = dpi / 25.4
    aus = []
    for f in felder:
        gef = []
        for x0, y0, x1, y1 in f.kaesten:
            teil = grau[max(0, y0):max(0, y1), max(0, x0):max(0, x1)]
            n = int((teil < schwelle).sum()) if teil.size else 0
            gef.append(n >= max(FUELLUNG_MIN_MM2 * px_mm * px_mm, FUELLUNG_MIN_ANTEIL * max(teil.size, 1)))
        aus.append(f._replace(gefuellt=gef))
    return aus


def nur_felder(grau, felder, rand: int = 4):
    """Weißes Bild in der Größe von grau, in dem nur die Felder (Rahmen samt Innenräumen) aus grau stehen – für einen
    zweiten OCR-Lauf, der nur die Kästcheninhalte liest (keine Feldnamen, keine Linien daneben)."""
    np = _np()
    aus = np.full_like(grau, 255)
    h, w = grau.shape
    for f in felder:
        x0, y0, x1, y1 = feld_bereich(f)
        x0, y0, x1, y1 = max(0, x0 - rand), max(0, y0 - rand), min(w, x1 + rand), min(h, y1 + rand)
        aus[y0:y1, x0:x1] = grau[y0:y1, x0:x1]
    return aus


def feld_bereich(feld) -> tuple:
    """(x0, y0, x1, y1): Rahmen und Innenräume eines Felds (bei einem Kamm ragen die Zeichen über die Wände)."""
    xs0 = [feld.rahmen[0]] + [k[0] for k in feld.kaesten]
    ys0 = [feld.rahmen[1]] + [k[1] for k in feld.kaesten]
    xs1 = [feld.rahmen[2]] + [k[2] for k in feld.kaesten]
    ys1 = [feld.rahmen[3]] + [k[3] for k in feld.kaesten]
    return (int(min(xs0)), int(min(ys0)), int(math.ceil(max(xs1))), int(math.ceil(max(ys1))))


def im_feld(feld: dict, x: float, y: float, rand_x: float = 2.0, rand_y: float = 1.5) -> bool:
    """Liegt der Punkt (Seitenkoordinaten) in einem Kästchen des Felds – waagerecht um rand_x erweitert (die Wand
    zwischen zwei Kästchen), senkrecht um rand_y?"""
    for k in feld.get("kaesten") or ():
        if k[0] - rand_x <= x <= k[2] + rand_x and k[1] - rand_y <= y <= k[3] + rand_y:
            return True
    return False


def kopfkasten(feld: dict) -> tuple:
    """Das erste (linke) Kästchen eines Felds in Seitenkoordinaten – Höhe und Anfang des Felds für die Suche nach
    seinem Feldnamen."""
    kaesten = feld.get("kaesten") or ()
    if not kaesten:
        return tuple(feld["rahmen"])
    return tuple(min(kaesten, key=lambda k: k[0]))


# ----------------------------------------------------------------------
# Felder ohne Personenbezug: Feldname und Form des Werts (sicherer Gegenbeleg)
# ----------------------------------------------------------------------
# Ein Wert bleibt nur dann frei, wenn BEIDES passt: der Feldname gehört zu einer Angabe ohne Personenbezug, und der
# Wert hat genau deren Form (ein Datum unter „Antragsdatum“, eine kleine Zahl unter „Anzahl“). Eine Telefonnummer im
# Feld „Anzahl“ oder ein Name unter „Tarifgruppe“ bleiben, was die übrigen Regeln aus ihnen machen.
DATUM_JAHRE = 30             # ein Datum ohne Personenbezug liegt höchstens so viele Jahre zurück
_DATUM_FORM = (r"(?:0?[1-9]|[12]\d|3[01])[.\-/ ]?(?:0?[1-9]|1[0-2])[.\-/ ]?(?:19|20)?\d{2}")
_OHNE_PERSONENBEZUG = (
    (re.compile(r"(?i)^(?:antrags|ausstellungs|ausfertigungs|eingangs|unterschrifts|schadens?|unfall|abschluss|"
                r"beginn|ablauf|änderungs|anderungs|zulassungs|erstzulassungs|vertrags|kündigungs|kundigungs)?"
                r"(?:datum|beginn|ablauf)\b|^datum\b|^(?:versicherungs|vertrags)?(?:beginn|ablauf)\b|"
                r"^(?:gültig|gultig)\s+(?:ab|bis)\b|^(?:erst)?zulassung\b"), _DATUM_FORM),
    (re.compile(r"(?i)^(?:anzahl|menge|stück|stueck|stückzahl)\b"), r"\d{1,3}"),
    (re.compile(r"(?i)^(?:betrag|summe|gesamtbetrag|beitrag|jahresbeitrag|monatsbeitrag|preis|kosten|"
                r"selbstbeteiligung|versicherungssumme|deckungssumme|prämie|pramie)\b"),
     r"\d{1,3}(?:[.]?\d{3}){0,3}(?:[,.]\d{1,2})?"),
    (re.compile(r"(?i)^(?:kilometerstand|km-stand|kmstand|laufleistung|fahrleistung|jahresfahrleistung)\b"),
     r"\d{1,3}(?:[.]?\d{3}){0,2}"),
    (re.compile(r"(?i)^(?:tarif|tarifgruppe|tarifstufe|beitragsgruppe|beitragsstufe|gruppe|klasse|"
                r"schadenfreiheitsklasse|sf-klasse|typklasse|regionalklasse|stufe)\b"), r"[A-Z0-9]{1,5}"),
    (re.compile(r"(?i)^(?:baujahr|jahr|kalenderjahr|beitragsjahr)\b"), r"(?:19|20)\d{2}"),
    (re.compile(r"(?i)^(?:leistung|kw|ps|hubraum|ccm)\b"), r"\d{1,5}"),
)
_PERSONEN_WORT = re.compile(r"(?i)geburt|geb\.|name|anschrift|straße|strasse|telefon|mail|iban|konto|kennzeichen|"
                            r"versicherungsn|vertragsn|steuer|ausweis|führerschein|fuhrerschein|ort\b|plz")
# Feldname eines Teils einer Angabe, die erst der übergeordnete Feldname bestimmt: ein Datum in Feldern für Tag, Monat
# und Jahr ("Geburtsdatum ⇥ Tag [2|5] Monat [0|4] Jahr [2|0|1|6]"; Abnahme 4 AB4-01) – "Jahr" allein ist kein Baujahr
_TEIL_ETIKETT_RE = re.compile(r"(?i)^(?:tag|monat|mon|jahr|tt|mm|jj|jjjj|datum)\.?$")
# ein Teil ohne eigenes Datum ("Jahr" mit "2016"): ohne übergeordneten Feldnamen nie frei; "Datum" allein ("Ort ⇥ Datum")
# ist ein Datum wie "Antragsdatum" – nur unter einem Geburts-Feldnamen eine Personenangabe (AB4-01)
_TEIL_OHNE_DATUM_RE = re.compile(r"(?i)^(?:tag|monat|mon|jahr|tt|mm|jj|jjjj)\.?$")
# vorgedruckter Ausfüllhinweis in einem leeren Feld ("TTMMJJJJ", "TT.MM.JJJJ", "MM/JJ"): kein Wert (AB4U-03)
_AUSFUELLHINWEIS_RE = re.compile(r"(?i)^(?:t{1,2}[.\-/]?m{1,2}[.\-/]?(?:j{2}|j{4}|y{2}|y{4})|m{1,2}[.\-/]?(?:j{2}|j{4})|"
                                 r"(?:j{2}|j{4}|y{2}|y{4})|t{1,2}[.\-/]?m{1,2}|d{1,2}[.\-/]?m{1,2}[.\-/]?(?:y{2}|y{4}))$")
# … mit Jahresteil (TTMMJJJJ, MMJJ, JJJJ): nur so darf ein Rest einer Kästchenwand dazwischen stehen ("TTMMJJJIJ" bei
# 300 dpi JPEG) – ein Name wie „TIM“ wird ohne sein „I“ nicht zum Hinweis „TM“
_AUSFUELLHINWEIS_JAHR_RE = re.compile(r"(?i)^(?:t{1,2}[.\-/]?m{1,2}[.\-/]?(?:j{2}|j{4}|y{2}|y{4})|m{1,2}[.\-/]?(?:j{2}|j{4})|"
                                      r"j{4}|y{4}|d{1,2}[.\-/]?m{1,2}[.\-/]?(?:y{2}|y{4}))$")
_WANDREST_RE = re.compile(r"[Il1!]")
# ein Kreuzchen ist ein Ankreuzwert, kein Feldinhalt (AB4U-02)
_KREUZCHEN = frozenset("x X ✓ ✔ ✗ ✘ ☒ ☑ ⊠".split())


def teil_etikett(feldname: str) -> bool:
    """Ist der Feldname nur der Teil einer Angabe (Tag, Monat, Jahr, TT, MM, JJJJ, Datum) – die Art bestimmt dann der
    übergeordnete Feldname davor bzw. darüber ("Geburtsdatum ⇥ Tag … Monat … Jahr …")?"""
    name = " ".join(re.sub(r"[(\[{][^()\[\]{}]{0,40}[)\]}]?", " ", feldname or "").replace(":", " ").split())
    return bool(_TEIL_ETIKETT_RE.match(name))


def teil_ohne_datum(feldname: str) -> bool:
    """Teil-Feldname ohne eigenes Datum (Tag, Monat, Jahr, TT, MM, JJJJ – nicht „Datum“): jeder übergeordnete
    Feldname für Personenangaben macht ihn zur Personenangabe; „Datum“ nur ein Geburts-Feldname (AB4-01)."""
    name = " ".join(re.sub(r"[(\[{][^()\[\]{}]{0,40}[)\]}]?", " ", feldname or "").replace(":", " ").split())
    return bool(_TEIL_OHNE_DATUM_RE.match(name))


def ausfuellhinweis(wert: str) -> bool:
    """Ist der gelesene Inhalt eines Felds ein vorgedruckter Ausfüllhinweis ("TTMMJJJJ", "TT.MM.JJJJ") oder ein
    Kreuzchen – kein Wert, den es zu schwärzen oder zu melden gibt?"""
    kompakt = re.sub(r"[\s|]+", "", wert or "")
    if not kompakt:
        return False
    if kompakt in _KREUZCHEN or _AUSFUELLHINWEIS_RE.match(kompakt):
        return True
    # die Texterkennung liest Reste der Kästchenwände als I, l, 1 oder ! mit ("TTMMJJJIJ")
    bereinigt = _WANDREST_RE.sub("", kompakt)
    return 1 <= len(kompakt) - len(bereinigt) <= 2 and len(bereinigt) >= 4 \
        and bool(_AUSFUELLHINWEIS_JAHR_RE.match(bereinigt))


def wert_ohne_personenbezug(feldname: str, wert: str) -> bool:
    """Ist der Wert eines Kammfelds frei – Feldname ohne Personenbezug (Antragsdatum, Anzahl, Betrag, Kilometerstand,
    Tarifgruppe, Baujahr …, nicht „Geburtsdatum“ oder „Name“) UND der Wert hat genau dessen Form?"""
    name = " ".join(re.sub(r"[(\[{][^()\[\]{}]{0,40}[)\]}]?", " ", feldname or "").replace(":", " ").split())
    kompakt = re.sub(r"[\s|]+", "", wert or "")
    if not name or not kompakt or _PERSONEN_WORT.search(name) or _TEIL_OHNE_DATUM_RE.match(name):
        return False                              # "Jahr" allein: erst der Feldname davor sagt, wessen Jahr
    for etikett, form in _OHNE_PERSONENBEZUG:
        if etikett.search(name):
            if re.fullmatch(form, kompakt) is None:
                return False
            if form is _DATUM_FORM:
                # ein Datum ohne Personenbezug liegt nah an heute (Antrag, Schaden, Zulassung) – ein Datum vor
                # Jahrzehnten kann ein Geburtsdatum im falschen Feld sein
                jahr = int(re.findall(r"\d{2}", kompakt)[-1]) if len(kompakt) in (6, 8) and kompakt.isdigit() \
                    else int(re.findall(r"\d+", kompakt)[-1])
                heute = datetime.date.today().year
                if jahr < 100:
                    jahr += 2000 if jahr <= heute % 100 + 5 else 1900
                return heute - DATUM_JAHRE <= jahr <= heute + 5
            return True
    return False


# die zuletzt gefragte Feldliste mit ihren Feldern nach der Oberkante des ersten Kästchens (gehoert_zum_feld_darunter
# fragt je Feld einer Seite mit derselben Liste)
_FELDER_OBERKANTE = None


def _felder_nach_oberkante(felder) -> tuple:
    """(Oberkanten, Felder) nach der Oberkante des ersten Kästchens (kopfkasten) sortiert – einmal je Feldliste."""
    global _FELDER_OBERKANTE
    zw = _FELDER_OBERKANTE
    if zw is not None and zw[0] is felder and zw[1] == len(felder):
        return zw[2]
    paare = sorted(((kopfkasten(f)[1], i) for i, f in enumerate(felder)), key=lambda p: p[0])
    idx = ([p[0] for p in paare], [felder[p[1]] for p in paare])
    _FELDER_OBERKANTE = (felder, len(felder), idx)
    return idx


UNTER_FAKTOR = 2.4

# die zuletzt gefragte Feldliste mit ihren Feldern nach der Unterkante des ersten Kästchens (gehoert_zum_feld_darueber)
_FELDER_UNTERKANTE = None


def _felder_nach_unterkante(felder) -> tuple:
    """(Unterkanten, Felder) nach der Unterkante des ersten Kästchens (kopfkasten) sortiert – einmal je Feldliste."""
    global _FELDER_UNTERKANTE
    zw = _FELDER_UNTERKANTE
    if zw is not None and zw[0] is felder and zw[1] == len(felder):
        return zw[2]
    paare = sorted(((kopfkasten(f)[3], i) for i, f in enumerate(felder)), key=lambda p: p[0])
    idx = ([p[0] for p in paare], [felder[p[1]] for p in paare])
    _FELDER_UNTERKANTE = (felder, len(felder), idx)
    return idx


def gehoert_zum_feld_darueber(feld, felder: list, oberkante: float, unterkante: float) -> bool:
    """Steht der Text über einem Feld (oberkante/unterkante) unter einem anderen Feld und gehört er nach
    gehoert_zum_feld_darunter zu diesem – ist er also dessen Feldname unter den Kästchen, nicht der Feldname dieses Felds
    ("Name" unter [KRAUS], darunter mit Abstand [45678] mit "Kilometerstand" darunter; Kamm-Probe 6 a02)? Gesucht wird
    das nächste Feld darüber, dessen Unterkante höchstens zwei Kästchenhöhen über dem Text liegt (bisect)."""
    x0, y0, _, y1 = kopfkasten(feld)
    x1 = feld["rahmen"][2]
    hoehe = max(y1 - y0, 4.0)
    unten_y, sortiert = _felder_nach_unterkante(felder)
    beste = None
    for f in sortiert[bisect.bisect_left(unten_y, oberkante - 2.0 * hoehe):bisect.bisect_right(unten_y, oberkante + 1.0)]:
        if f is not feld and min(x1, f["rahmen"][2]) - max(x0, kopfkasten(f)[0]) > -10.0:
            if beste is None or kopfkasten(f)[3] > kopfkasten(beste)[3]:
                beste = f
    return beste is not None and not gehoert_zum_feld_darunter(beste, felder, oberkante, unterkante)


# die zuletzt bestimmte Lage der Feldnamen einer Seite (feldnamen_lage): (erstes Feld, letztes Feld, Zahl der Felder, Zahl
# der Wörter, Lage) – die Aufrufer fragen je Feld derselben Seite (auch mit einer Kopie der Feldliste)
_FELDNAMEN_LAGE = None


def feldnamen_lage(felder: list, boxen: list):
    """Stehen die Feldnamen der Seite über ("oben") oder unter ("unten") ihren Kammfeldern – oder ist das nicht sicher
    (None)? Zwischen zwei Feldern ist ein Text nach dem Abstand allein nicht zuzuordnen: ein Feldname unter dem Feld mit
    engem Folgeabstand und ein hängender Feldname über dem Feld stehen gleich (Abnahme 7 A7-13: Verhältnis 1,3–2,3
    bzw. 2,7–4,0 auf beiden Seiten). Belege gibt es nur am Rand: ein Feld, über dem kein anderes Feld steht, mit Text
    direkt darüber spricht für "oben"; ein Feld, unter dem kein anderes steht, mit Text direkt darunter für "unten".
    Nur ein Beleg einer Seite entscheidet (Nachbesserung 9). boxen: (x0, y0, x1, y1) der Wörter außerhalb der Felder.
    Je Seite einmal bestimmt; Felder darüber bzw. darunter und Wörter per bisect über die sortierten Kanten (je Feld
    alle Felder bzw. Wörter zu prüfen wüchse quadratisch)."""
    global _FELDNAMEN_LAGE
    if not felder:
        return None
    zw = _FELDNAMEN_LAGE
    if zw is not None and zw[0] is felder[0] and zw[1] is felder[-1] and zw[2] == len(felder) and zw[3] == len(boxen):
        return zw[4]
    kopf = [kopfkasten(f) + (f["rahmen"][2],) for f in felder if f.get("kaesten")]
    nach_ok = sorted(kopf, key=lambda k: k[1])
    ok = [k[1] for k in nach_ok]
    nach_uk = sorted(kopf, key=lambda k: k[3])
    uk = [k[3] for k in nach_uk]
    nach_oben = sorted(((b[1], b) for b in boxen), key=lambda t: t[0])
    oben_y = [t[0] for t in nach_oben]
    nach_unten = sorted(((b[3], b) for b in boxen), key=lambda t: t[0])
    unten_y = [t[0] for t in nach_unten]
    oben_beleg = unten_beleg = 0
    for x0, y0, _, y1, x1 in kopf:
        hoehe = max(y1 - y0, 4.0)
        reich = 1.2 * hoehe

        def ueberlappt(a0, a1):
            return min(x1, a1) - max(x0, a0) > -10.0

        feld_oben = any(ueberlappt(k[0], k[4])
                        for k in nach_uk[bisect.bisect_left(uk, y0 - 3.0 * hoehe):bisect.bisect_right(uk, y0 - 0.5)])
        feld_unten = any(ueberlappt(k[0], k[4])
                         for k in nach_ok[bisect.bisect_left(ok, y1 + 0.5):bisect.bisect_right(ok, y1 + 3.0 * hoehe)])
        if not feld_oben:
            for _, b in nach_unten[bisect.bisect_left(unten_y, y0 - reich):bisect.bisect_right(unten_y, y0 + 1.5)]:
                if x0 - 10.0 <= b[0] <= x0 + 0.5 * (x1 - x0):
                    oben_beleg += 1
                    break
        if not feld_unten:
            for _, b in nach_oben[bisect.bisect_left(oben_y, y1 - 1.5):bisect.bisect_right(oben_y, y1 + reich)]:
                if x0 - 10.0 <= b[0] <= x0 + 0.5 * (x1 - x0):
                    unten_beleg += 1
                    break
    lage = "oben" if oben_beleg and not unten_beleg else "unten" if unten_beleg and not oben_beleg else None
    _FELDNAMEN_LAGE = (felder[0], felder[-1], len(felder), len(boxen), lage)
    return lage


def gehoert_zum_feld_darunter(feld, felder: list, oberkante: float, unterkante: float) -> bool:
    """Steht der Text unter einem Feld (oberkante/unterkante) näher am nächsten Feld darunter als am Feld selbst – dann
    ist er dessen Feldname ("Antragsdatum" über dem nächsten Feld), nicht der Feldname unter diesem (Abnahme 5 A5-07).
    Gesucht wird nur unter den Feldern, deren Oberkante zwischen dem Text und dem Abstand zum eigenen Feld liegt
    (bisect über die sortierten Oberkanten; je Feld alle Felder der Seite wüchse quadratisch)."""
    x0, _, _, y1 = kopfkasten(feld)
    x1 = feld["rahmen"][2]
    # Nachbesserung 8 (Abnahme 6 A6-08, AB6U-16): der Text gehört zum Feld darunter, solange er nicht deutlich näher am
    # Feld darüber steht – Abstand zum Feld darunter höchstens UNTER_FAKTOR mal der zum Feld darüber. Gemessen
    # (n8_arbeit/skripte/kamm_abstand.py): enger Zeilenabstand mit Feldname über dem Feld 1,06–1,95 (eigen606_eng,
    # auch c023), Feldname unter dem Feld 2,89–4,42 (Kamm-Probe 6 a02 auf Scans)
    abstand_eigen = max(oberkante - y1, UNTER_FAKTOR * (oberkante - y1))
    oben, sortiert = _felder_nach_oberkante(felder)
    for f in sortiert[bisect.bisect_left(oben, unterkante - 1.0):bisect.bisect_right(oben, unterkante + abstand_eigen)]:
        if f is not feld and min(x1, f["rahmen"][2]) - max(x0, kopfkasten(f)[0]) > -10.0:
            return True
    return False
