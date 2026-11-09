"""„Scans“ aus Vektorseiten erzeugen – mit nachgeführten Wortrechtecken für den Pixelvergleich.

Eine Vektorseite (aus satz.py) wird gerastert (dpi, optional anisotrop wie beim Fax 204x98 dpi),
leicht gedreht (Schräglage), verrauscht, weichgezeichnet und als JPEG (Qualität 40-85), PNG oder
1-Bit-Bild in eine neue Seite gesetzt. Varianten: /Rotate 90/180/270 (Bild gegenläufig gedreht
gespeichert, Anzeige aufrecht), kopfstehend ohne /Rotate, durchsuchbarer Scan mit unsichtbarer,
leicht versetzter Textebene (wie von Kopierern/Scan-Software erzeugt).

Für jeden Eintrag werden die Wortrechtecke durch dieselbe Abbildung (Rasterung -> Bildpixel ->
Seitenkoordinaten -> Anzeige nach /Rotate) in Anzeige-Koordinaten der neuen Seite umgerechnet.
Die Bewertung kann damit prüfen, ob an dieser Stelle in der Ausgabe noch die Original-Pixel stehen.
"""

from dataclasses import dataclass, field

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen
    import fitz

try:
    import numpy as np
except ImportError:  # ohne numpy: Scans ohne Rauschen/Unschärfe
    np = None


@dataclass
class ScanParameter:
    dpi: int = 200
    dpi_y: int | None = None          # abweichende vertikale Auflösung (Fax 98 dpi)
    jpeg: int | None = 75             # JPEG-Qualität; None = verlustfrei (PNG bzw. 1 Bit)
    schraeg: float = 0.0              # Schräglage in Grad
    rauschen: float = 0.0             # Standardabweichung in Graustufen
    unschaerfe: float = 0.0           # Anteil weichgezeichnet (0..1)
    flecken: float = 0.0              # Anteil Staubpunkte
    rotate: int = 0                   # /Rotate der Seite (Bild gegenläufig gespeichert)
    kopfstehend: bool = False         # Bild um 180° gedreht, ohne /Rotate
    fax: bool = False                 # 1-Bit-Schwelle
    farbig: bool = False              # RGB statt Graustufen
    durchsuchbar: bool = False        # unsichtbare Textebene (Render-Modus 3)
    versatz: tuple = (0.0, 0.0)       # Versatz der unsichtbaren Textebene in pt
    papier: int = 246                 # Grauwert des Papiers
    seed: int = 0
    merkmale: list = field(default_factory=list)

    def beschreibung(self) -> list:
        """Merkmale für die Wahrheitsdatei."""
        m = ["scan"]
        if self.fax:
            m.append("fax")
        m.append(f"dpi_{self.dpi}" if not self.dpi_y else f"dpi_{self.dpi}x{self.dpi_y}")
        if self.dpi <= 150 or (self.dpi_y and self.dpi_y <= 150):
            m.append("scan_niedrige_aufloesung")
        if self.jpeg is not None:
            m.append(f"jpeg_q{self.jpeg // 10 * 10}")
            if self.jpeg <= 50:
                m.append("jpeg_stark_komprimiert")
        if abs(self.schraeg) >= 0.5:
            m.append(f"schraeg_{int(round(abs(self.schraeg)))}grad")
        if self.rauschen >= 6 or self.flecken > 0:
            m.append("rauschen")
        if self.unschaerfe >= 0.3:
            m.append("unschaerfe")
        if self.rotate:
            m.append(f"rotate_{self.rotate}")
        if self.kopfstehend:
            m.append("kopfstehend")
        if self.durchsuchbar:
            m.append("durchsuchbarer_scan")
        return m + list(self.merkmale)


def _bearbeiten(pix, p: ScanParameter):
    """Papierton, Unschärfe, Rauschen, Flecken, ggf. 1-Bit-Schwelle (numpy)."""
    if np is None:
        return pix
    rng = np.random.default_rng(p.seed)
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n).astype(np.float32)
    # Papierton: Weiß -> leicht grau, Schwarz bleibt dunkel
    a = a * (p.papier / 255.0)
    if p.unschaerfe > 0:
        g = np.pad(a, ((1, 1), (1, 1), (0, 0)), mode="edge")
        weich = sum(g[dy:dy + a.shape[0], dx:dx + a.shape[1]] for dy in range(3) for dx in range(3)) / 9.0
        a = (1 - p.unschaerfe) * a + p.unschaerfe * weich
    if p.rauschen > 0:
        a = a + rng.normal(0.0, p.rauschen, a.shape[:2])[:, :, None]
    if p.flecken > 0:
        maske = rng.random(a.shape[:2]) < p.flecken
        a[maske] = rng.uniform(0, 90)
    if p.fax:
        a = np.where(a.mean(axis=2, keepdims=True) < 150, 0.0, 255.0).repeat(pix.n, axis=2)
    a = np.clip(a, 0, 255).astype(np.uint8)
    cs = fitz.csRGB if pix.n == 3 else fitz.csGRAY
    return fitz.Pixmap(cs, pix.width, pix.height, a.tobytes(), False)


def _kodieren(pix, p: ScanParameter) -> bytes:
    if p.fax:
        return pix.tobytes("pbm")
    if p.jpeg is None:
        return pix.tobytes("png")
    return pix.tobytes("jpeg", jpg_quality=int(p.jpeg))


class _Abbildung:
    """Vektorseite -> Anzeige-Koordinaten der Scan-Seite."""

    def __init__(self, matrix, pix_x, pix_y, zx, zy, ziel_seite):
        self.matrix = matrix
        self.pix_x, self.pix_y = pix_x, pix_y
        self.zx, self.zy = zx, zy
        self.rot = ziel_seite.rotation_matrix

    def unrotiert(self, punkt) -> "fitz.Point":
        q = fitz.Point(punkt) * self.matrix
        return fitz.Point((q.x - self.pix_x) / self.zx, (q.y - self.pix_y) / self.zy)

    def anzeige(self, punkt) -> "fitz.Point":
        return self.unrotiert(punkt) * self.rot

    def rechteck(self, r) -> list:
        r = fitz.Rect(r)
        ecken = [self.anzeige(e) for e in (r.tl, r.tr, r.bl, r.br)]
        xs, ys = [e.x for e in ecken], [e.y for e in ecken]
        return [min(xs), min(ys), max(xs), max(ys)]


def seite_scannen(quelle_page, ziel_doc, p: ScanParameter, eintraege: list, schrift_unsichtbar=None):
    """Rastert `quelle_page` und hängt die Scan-Seite an `ziel_doc` an. Die Wortrechtecke der
    `eintraege` (Liste der Eintrag-Dicts dieser Seite) werden auf die neue Seite umgerechnet,
    ihr Kanal wird 'scan'. Liefert die neue Seite."""
    zx = p.dpi / 72.0
    zy = (p.dpi_y or p.dpi) / 72.0
    winkel = p.schraeg + (180.0 if p.kopfstehend else 0.0) - p.rotate
    matrix = fitz.Matrix(zx, zy).prerotate(winkel)
    farbraum = fitz.csRGB if p.farbig else fitz.csGRAY
    pix = quelle_page.get_pixmap(matrix=matrix, colorspace=farbraum, alpha=False)
    bearbeitet = _bearbeiten(pix, p)
    bild = _kodieren(bearbeitet, p)
    breite, hoehe = pix.width / zx, pix.height / zy
    seite = ziel_doc.new_page(width=breite, height=hoehe)
    seite.insert_image(seite.rect, stream=bild, keep_proportion=False)
    if p.rotate:
        seite.set_rotation(p.rotate)
    abb = _Abbildung(matrix, pix.x, pix.y, zx, zy, seite)
    for e in eintraege:
        e["kanal"] = "scan"
        e["woerter"] = [abb.rechteck(w[:4]) + [w[4]] for w in e["woerter"]]
    if p.durchsuchbar and not p.rotate:
        _textebene(quelle_page, seite, abb, p, schrift_unsichtbar)
    return seite


def _textebene(quelle_page, seite, abb: _Abbildung, p: ScanParameter, schrift):
    """Unsichtbare Textebene (Render-Modus 3) aus dem Vektortext, leicht versetzt."""
    dx, dy = p.versatz
    for block in quelle_page.get_text("dict")["blocks"]:
        for zeile in block.get("lines", []):
            for span in zeile["spans"]:
                text = span["text"]
                if not text.strip():
                    continue
                ursprung = abb.unrotiert(span["origin"])
                groesse = span["size"]
                if schrift is None:
                    seite.insert_text((ursprung.x + dx, ursprung.y + dy), text, fontsize=groesse,
                                      fontname="helv", render_mode=3)
                else:
                    schrift.setzen(seite, ursprung.x + dx, ursprung.y + dy, schrift.darstellbar(text),
                                   groesse, unsichtbar=True)


def bild_einfuegen(quelle_page, ziel_page, rechteck, p: ScanParameter, eintraege: list):
    """Rastert `quelle_page` (z. B. einen Praxisstempel) und setzt das Bild in `rechteck` der
    Zielseite (Textseite mit Bild). Wortrechtecke der Einträge werden umgerechnet (Kanal 'scan')."""
    zx = zy = p.dpi / 72.0
    matrix = fitz.Matrix(zx, zy).prerotate(p.schraeg)
    pix = quelle_page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB if p.farbig else fitz.csGRAY,
                                 alpha=False)
    bild = _kodieren(_bearbeiten(pix, p), p)
    r = fitz.Rect(rechteck)
    ziel_page.insert_image(r, stream=bild, keep_proportion=False)
    sx, sy = r.width / pix.width, r.height / pix.height
    for e in eintraege:
        e["kanal"] = "scan"
        neu = []
        for w in e["woerter"]:
            ecken = [fitz.Point(pt) * matrix for pt in (fitz.Rect(w[:4]).tl, fitz.Rect(w[:4]).tr,
                                                         fitz.Rect(w[:4]).bl, fitz.Rect(w[:4]).br)]
            xs = [r.x0 + (e2.x - pix.x) * sx for e2 in ecken]
            ys = [r.y0 + (e2.y - pix.y) * sy for e2 in ecken]
            neu.append([min(xs), min(ys), max(xs), max(ys), w[4]])
        e["woerter"] = neu
