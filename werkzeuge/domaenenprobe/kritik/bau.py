"""Eigene Seitenbauer für die Kritik-Fälle: freie Positionen, Schriftgrößen, Drehung, mehrere Seiten.
Element = (x, y, text[, groesse[, drehung]]); Tabelle = Zellen an festen x-Positionen.

Schriften: e2e.py sucht DejaVu Sans und DejaVu Sans Mono (unter Windows ersatzweise Arial bzw. Consolas) und gibt die
Pfade über DOMAENENPROBE_SCHRIFT und DOMAENENPROBE_SCHRIFT_MONO weiter; ohne diese Variablen gelten die Linux-Pfade."""
import os
import tempfile

import pymupdf as fitz

DEJAVU = os.environ.get("DOMAENENPROBE_SCHRIFT") or "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def pdf(pfad, seiten, schrift=DEJAVU):
    doc = fitz.open()
    for elemente in seiten:
        s = doc.new_page(width=595, height=842)
        for el in elemente:
            x, y, text = el[:3]
            g = el[3] if len(el) > 3 else 10
            rot = el[4] if len(el) > 4 else 0
            if not text:
                continue
            if schrift:
                s.insert_text((x, y), text, fontsize=g, fontname="dv", fontfile=schrift, rotate=rot)
            else:
                s.insert_text((x, y), text, fontsize=g, fontname="helv", rotate=rot)
    doc.save(pfad)
    doc.close()


def zeilen(x, y, texte, groesse=10, abstand=None):
    """Untereinander gesetzte Zeilen ab (x, y)."""
    abstand = abstand or groesse * 1.5
    return [(x, y + i * abstand, t, groesse) for i, t in enumerate(texte)]


def tabelle(y, xs, reihen, groesse=8, abstand=None):
    """Reihen (Listen von Zellen) an den Spaltenpositionen xs."""
    abstand = abstand or groesse * 1.6
    aus = []
    for i, reihe in enumerate(reihen):
        for x, zelle in zip(xs, reihe):
            aus.append((x, y + i * abstand, zelle, groesse))
    return aus


def bauer(seiten, schrift=DEJAVU):
    return lambda pfad: pdf(pfad, seiten, schrift)


MONO = os.environ.get("DOMAENENPROBE_SCHRIFT_MONO") or "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


def pdf2(pfad, seiten):
    """Wie pdf(), aber je Element eigene Schrift: (x, y, text, groesse, drehung, schriftdatei)."""
    doc = fitz.open()
    for elemente in seiten:
        s = doc.new_page(width=595, height=842)
        for el in elemente:
            x, y, text = el[:3]
            g = el[3] if len(el) > 3 else 10
            rot = el[4] if len(el) > 4 else 0
            datei = el[5] if len(el) > 5 else DEJAVU
            if not text:
                continue
            name = "dvm" if datei == MONO else "dv"
            s.insert_text((x, y), text, fontsize=g, fontname=name, fontfile=datei, rotate=rot)
    doc.save(pfad)
    doc.close()


def _seite_als_bild(seiten, dpi=200):
    import io
    from PIL import Image
    with tempfile.TemporaryDirectory(prefix="domaenenprobe_") as ordner:    # nicht im Werkzeugordner
        tmp = os.path.join(ordner, f"_tmp_bild_{os.getpid()}.pdf")
        pdf2(tmp, seiten)
        with fitz.open(tmp) as d:
            pix = d[0].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
    return img


def _koeffizienten(ziel, quelle):
    """Perspektive: Koeffizienten für Image.transform (ziel- und quellpunkte je 4)."""
    import numpy as np
    m = []
    for (x, y), (u, v) in zip(ziel, quelle):
        m.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        m.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    a = np.array(m, dtype=float)
    b = np.array(quelle, dtype=float).reshape(8)
    return list(np.linalg.solve(a, b))


def foto(seiten, winkel=2.0, jpeg=72):
    """Handyfoto-Nachbildung: leichte Trapezverzerrung, Drehung, Helligkeitsverlauf, JPEG – als Bild-PDF."""
    def bauen(pfad):
        import io
        from PIL import Image
        img = _seite_als_bild(seiten)
        w, h = img.size
        d = 0.03
        ziel = [(0, 0), (w, 0), (w, h), (0, h)]
        quelle = [(-d * w, 0), (w * (1 + d), 0), (w, h), (0, h)]   # oben breiter aufgenommen -> oben schmaler
        img = img.transform((w, h), Image.PERSPECTIVE, _koeffizienten(ziel, quelle), Image.BICUBIC, fillcolor=235)
        img = img.rotate(winkel, expand=False, fillcolor=235, resample=Image.BICUBIC)
        verlauf = Image.linear_gradient("L").resize((w, h)).point(lambda p: 255 - int(p * 0.22))
        img = Image.composite(img, Image.new("L", (w, h), 0), Image.new("L", (w, h), 255))
        from PIL import ImageChops
        img = ImageChops.multiply(img, verlauf)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=jpeg)
        doc = fitz.open()
        p = doc.new_page(width=595, height=842)
        p.insert_image(p.rect, stream=buf.getvalue())
        doc.save(pfad)
        doc.close()
    return bauen


def mit_bild(seite, bild_seiten, rect, dpi=200):
    """Textseite (Elemente) mit eingebettetem Rasterbild einer zweiten Seite im Rechteck rect."""
    def bauen(pfad):
        import io
        img = _seite_als_bild(bild_seiten, dpi)
        buf = io.BytesIO()
        img.crop((0, 0, img.size[0], int(img.size[1] * 0.25))).save(buf, format="PNG")
        tmp = str(pfad) + ".tmp.pdf"
        pdf2(tmp, [seite])
        doc = fitz.open(tmp)
        doc[0].insert_image(fitz.Rect(*rect), stream=buf.getvalue())
        doc.save(str(pfad))
        doc.close()
        os.unlink(tmp)
    return bauen
