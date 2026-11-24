"""Ende-zu-Ende-Probe: PDFs aus Fallbeschreibungen bauen (Textebene / Scan), analysieren, schwärzen, Ausgabe per
Textextraktion und OCR prüfen. Wird von messen.py je Falldatei als eigener Prozess gestartet.

Aufruf: python e2e.py <faelle.py> <arbeitsordner> [--repo <checkout>] [--weg engine|oberflaeche] [--nur fall1,fall2]
                      [--ocr tesseract|pymupdf] [--tesseract <programm>]

--repo       Programmcode (Paket anonymisierer), der gemessen wird; Vorgabe: dieses Checkout.
--weg        engine: jeder Fund der Analyse geht an die Schwärzung; oberflaeche: Auftrag wie die Oberfläche ohne
             Eingriff (Häkchen der Fundliste, Schutzstufe „Hoch“, „Freigabe vor Weitergabe“). Vorgabe engine wie
             im ursprünglichen Harness; messen.py misst immer oberflaeche.
--ocr        Lesbarkeit der Ausgabe per OCR: tesseract (Vorgabe, Tesseract-Kommandozeile mit PSM 3 – so ist die
             Referenz gemessen) oder pymupdf (in PyMuPDF eingebautes Tesseract, für Rechner ohne Kommandozeile;
             mit der Referenz nicht vergleichbar).
--tesseract  Tesseract-Programm; sonst DOMAENENPROBE_TESSERACT, PATH, unter Windows die üblichen Installationsordner.

Ergebnis: <arbeitsordner>/ergebnis_<weg>.json (je geheimem Wert textebene/ocr/status/gemeldet/still) und je Fall
ein Unterordner mit den gebauten PDFs und der Ausgabe.
"""
import argparse
import io
import json
import os
import re
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

import pymupdf as fitz

HIER = Path(__file__).resolve().parent
WURZEL = HIER.parents[1]                 # Vorgabe für --repo: das Checkout, in dem dieses Werkzeug liegt
SPALTEN = [60, 250, 420]

# Gesetzt von _vorbereiten() (wie die Modulvariablen des ursprünglichen Harness)
muster = analyse = schwaerzung = OcrDienst = None
FAELLE = ARBEIT = WEG = NUR = ALLE = DEJAVU = None
OCR_ART = "tesseract"
TESSERACT = None

# Schriften: DejaVu wie bei der Referenzmessung (Linux); unter Windows ersatzweise Arial/Consolas (Bericht nennt es)
_SCHRIFTEN = {"DejaVuSans.ttf": ("DOMAENENPROBE_SCHRIFT", ("arial.ttf", "Arial.ttf", "segoeui.ttf")),
              "DejaVuSansMono.ttf": ("DOMAENENPROBE_SCHRIFT_MONO", ("consola.ttf", "cour.ttf", "Courier New.ttf"))}


def _schrift_ordner():
    ordner = ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/usr/share/fonts/TTF",
              "/usr/share/fonts/truetype/msttcorefonts", "/usr/local/share/fonts",
              str(Path.home() / ".local" / "share" / "fonts"), str(Path.home() / ".fonts"),
              str(Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts")]
    if os.environ.get("LOCALAPPDATA"):
        ordner.append(str(Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "Windows" / "Fonts"))
    return ordner + ["/Library/Fonts", str(Path.home() / "Library" / "Fonts"), "/System/Library/Fonts/Supplemental"]


def schriften():
    """{Dateiname: (Pfad oder None, Ersatz?)} für DejaVu Sans und DejaVu Sans Mono. Eine gesetzte Umgebungsvariable
    (DOMAENENPROBE_SCHRIFT, DOMAENENPROBE_SCHRIFT_MONO) geht vor; sonst die üblichen Schriftordner, zuletzt der
    Ersatz."""
    aus = {}
    for name, (variable, ersatz) in _SCHRIFTEN.items():
        vorgabe = os.environ.get(variable)
        if vorgabe:
            aus[name] = (vorgabe, Path(vorgabe).name != name)
            continue
        pfad = next((str(Path(o) / name) for o in _schrift_ordner() if (Path(o) / name).is_file()), None)
        if pfad:
            aus[name] = (pfad, False)
            continue
        pfad = next((str(Path(o) / e) for e in ersatz for o in _schrift_ordner() if (Path(o) / e).is_file()), None)
        aus[name] = (pfad, pfad is not None)
    return aus


def tesseract_programm(vorgabe=None):
    """Pfad der Tesseract-Kommandozeile oder None. Reihenfolge: Vorgabe, DOMAENENPROBE_TESSERACT, PATH, unter Windows
    die Installationsordner von Tesseract-OCR (UB Mannheim)."""
    for kandidat in (vorgabe, os.environ.get("DOMAENENPROBE_TESSERACT")):
        if kandidat:
            return shutil.which(kandidat) or (str(Path(kandidat)) if Path(kandidat).is_file() else None)
    gefunden = shutil.which("tesseract")
    if gefunden or os.name != "nt":
        return gefunden
    for basis in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                  os.environ.get("LOCALAPPDATA") and str(Path(os.environ["LOCALAPPDATA"]) / "Programs")):
        if basis and (Path(basis) / "Tesseract-OCR" / "tesseract.exe").is_file():
            return str(Path(basis) / "Tesseract-OCR" / "tesseract.exe")
    return None


def tesseract_version(programm):
    try:
        r = subprocess.run([programm, "--version"], capture_output=True, encoding="utf-8", errors="replace",
                           timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        return f"nicht startbar ({e})"
    zeilen = (r.stdout + r.stderr).strip().splitlines()
    return zeilen[0].strip() if zeilen else f"unbekannt (Exit-Code {r.returncode})"


def text_pdf(pfad, zeilen, schrift=None, groesse=11, felder=(), font="helv"):
    doc = fitz.open()
    s = doc.new_page(width=595, height=842)
    y = 80
    for z in zeilen:
        teile = z.split("\t\t")
        for i, t in enumerate(teile):
            x = SPALTEN[i] if len(teile) > 1 else 60
            if schrift:
                s.insert_text((x, y), t, fontsize=groesse, fontname="dv", fontfile=schrift)
            else:
                s.insert_text((x, y), t, fontsize=groesse, fontname=font)
        y += groesse * 1.65
    for f in felder:          # (name, rect, wert)
        w = fitz.Widget()
        w.field_name, w.field_type = f[0], fitz.PDF_WIDGET_TYPE_TEXT
        w.rect, w.field_value = fitz.Rect(*f[1]), f[2]
        w.text_fontsize = 10
        s.add_widget(w)
    doc.save(pfad)
    doc.close()


def scan_pdf(quelle, pfad, dpi=200, winkel=0.0, jpeg=None):
    from PIL import Image
    with fitz.open(quelle) as d:
        pix = d[0].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
    if winkel:
        img = img.rotate(winkel, expand=False, fillcolor=255, resample=Image.BICUBIC)
    buf = io.BytesIO()
    if jpeg:
        img.save(buf, format="JPEG", quality=jpeg)
    else:
        img.save(buf, format="PNG")
    doc = fitz.open()
    p = doc.new_page(width=595, height=842)
    p.insert_image(p.rect, stream=buf.getvalue())
    doc.save(pfad)
    doc.close()


def _ocr_pymupdf(seite, dpi):
    """Ersatz ohne Tesseract-Kommandozeile: in PyMuPDF eingebautes Tesseract mit der Sprachdatei des Programms
    (TESSDATA_PREFIX setzt der OcrDienst), mit PSM 3 wie die Kommandozeile, soweit das Programm die Einstellung
    kennt."""
    tessdata = os.environ.get("TESSDATA_PREFIX")
    try:
        from anonymisierer.ocr import tessdata_mit_einstellungen
        tessdata = tessdata_mit_einstellungen(tessdata, "deu") or tessdata
    except ImportError:
        pass
    pix = seite.get_pixmap(dpi=dpi, colorspace=fitz.csRGB, alpha=False)
    pix.set_dpi(dpi, dpi)
    with fitz.open("pdf", pix.pdfocr_tobytes(compress=False, language="deu", tessdata=tessdata)) as d:
        return d[0].get_text()


def ocr_text(pdf, dpi=300):
    texte = []
    with fitz.open(pdf) as d:
        for i, s in enumerate(d):
            if OCR_ART == "pymupdf":
                texte.append(_ocr_pymupdf(s, dpi))
                continue
            png = ARBEIT / f"_ocr_{os.getpid()}.png"
            s.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY).save(png)
            r = subprocess.run([TESSERACT, str(png), "-", "-l", "deu", "--psm", "3"], capture_output=True,
                               encoding="utf-8", errors="replace", env=dict(os.environ, OMP_THREAD_LIMIT="1"))
            png.unlink()
            if r.returncode != 0:    # sonst wäre der OCR-Text leer und jeder Wert hieße still „weg“
                raise RuntimeError(f"Tesseract-Kommandozeile mit Exit-Code {r.returncode}: {r.stderr.strip()[:500]}")
            texte.append(r.stdout)
    return "\n".join(texte)


def norm(t):
    return re.sub(r"[\s|_.,;:\"'„“”‚‘’»«→()\[\]-]", "", t).upper()


def lesbar(geheim, text):
    g, t = norm(geheim), norm(text)
    if g in t:
        return True
    if len(g) <= 4:
        return False
    from difflib import SequenceMatcher
    for n in (len(g) - 1, len(g), len(g) + 1):
        for i in range(0, max(0, len(t) - n) + 1):
            if SequenceMatcher(None, g, t[i:i + n]).ratio() >= 0.86:
                return True
    return False


def oberflaeche_lauf(pdf, dienst, ziel):
    from anonymisierer import auftrag as A
    aktive = A.standard_kategorien()
    erg = analyse.analysiere_pdf(pdf, aktive, [], [], ocr=dienst, profil=A.STANDARD_PROFIL,
                                 lauf=analyse.LaufWissen())
    au, zust = A.standard_auftrag(dict(erg, funde=list(erg["funde"])), schwaerzung.schwaerze_pdf)
    par = A.schwaerz_parameter(au, A.STANDARD_FREIGABE, A.STANDARD_PROFIL, schwaerzung.schwaerze_pdf)
    out = schwaerzung.schwaerze_pdf(pdf, au["funde"], ocr=dienst, ziel_ordner=ziel, **par)
    status = A.ausgabe_status(dict(out, fehler=out.get("fehler")))
    nur_frei = out.get("status") == "pruefen" and A.nur_freigabe_offen(out, status)
    return erg, out, nur_frei


def _argumente(argv):
    ap = argparse.ArgumentParser(description="Ende-zu-Ende-Probe einer Falldatei der Domänen-Probe")
    ap.add_argument("faelle", help="Falldatei (Python, definiert FAELLE)")
    ap.add_argument("arbeit", help="Arbeitsordner für PDFs, Ausgaben und ergebnis_<weg>.json")
    ap.add_argument("--repo", default=str(WURZEL), help="Checkout, dessen Programmcode gemessen wird")
    ap.add_argument("--weg", choices=("engine", "oberflaeche"), default="engine")
    ap.add_argument("--nur", default="", help="nur diese Fälle (Namen, durch Komma getrennt)")
    ap.add_argument("--ocr", choices=("tesseract", "pymupdf"), default="tesseract")
    ap.add_argument("--tesseract", default=None, help="Tesseract-Programm (Kommandozeile)")
    return ap.parse_args(argv)


def _vorbereiten(argv):
    """Entspricht dem Modulkopf des ursprünglichen Harness: Programmcode aus --repo laden, Schriften für die Fälle
    festlegen, Falldatei ausführen. Steht in einer Funktion, damit die OCR-Arbeitsprozesse (Start-Methode spawn)
    beim Laden dieses Moduls nicht alles wiederholen."""
    global muster, analyse, schwaerzung, OcrDienst, FAELLE, ARBEIT, WEG, NUR, ALLE, DEJAVU, OCR_ART, TESSERACT
    a = _argumente(argv)
    repo = Path(a.repo).resolve()
    sys.path.insert(0, str(repo))
    from anonymisierer import muster, analyse, schwaerzung
    from anonymisierer.ocr import OcrDienst
    OCR_ART = a.ocr
    if OCR_ART == "tesseract":
        TESSERACT = tesseract_programm(a.tesseract)
        if not TESSERACT:
            raise SystemExit("Tesseract-Kommandozeile nicht gefunden (--tesseract, DOMAENENPROBE_TESSERACT oder "
                             "PATH) – ohne sie misst --ocr pymupdf (nicht mit der Referenz vergleichbar).")
    for name, (pfad, ersatz) in schriften().items():
        variable = _SCHRIFTEN[name][0]
        if pfad:
            os.environ[variable] = pfad          # für kritik/bau.py, das die Falldatei gleich importiert
        if ersatz:
            print(f"Hinweis: {name} nicht gefunden, ersatzweise {pfad} – Ergebnisse nur eingeschränkt mit der "
                  f"Referenz vergleichbar", file=sys.stderr, flush=True)
    DEJAVU = os.environ.get(_SCHRIFTEN["DejaVuSans.ttf"][0]) or "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    FAELLE = runpy.run_path(str(Path(a.faelle).resolve()))["FAELLE"]
    ARBEIT = Path(a.arbeit).resolve()
    WEG = a.weg
    NUR = set(a.nur.split(",")) if a.nur else None
    ARBEIT.mkdir(parents=True, exist_ok=True)
    ALLE = {k for k, _, _, _, an in muster.KATEGORIEN if an}


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):       # Protokoll immer UTF-8 (Windows: sonst cp1252, Abbruch bei „ț“)
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    _vorbereiten(argv)
    ergebnisse = []
    with OcrDienst(prozesse=1) as dienst:
        for fall in FAELLE:
            name = fall["name"]
            if NUR and name not in NUR:
                continue
            ordner = ARBEIT / name
            ordner.mkdir(parents=True, exist_ok=True)
            roh = ordner / "text.pdf"
            if fall.get("bauer"):
                fall["bauer"](roh)
            else:
                text_pdf(roh, fall["zeilen"], schrift=DEJAVU if fall.get("unicode") else None,
                         felder=fall.get("felder", ()), font=fall.get("font", "helv"), groesse=fall.get("groesse", 11))
            varianten = []
            if fall.get("text", True):
                varianten.append(("text", roh))
            for sc in fall.get("scans", ()):
                dpi, winkel, jpeg = sc
                p = ordner / f"scan_{dpi}_{winkel}_{jpeg}.pdf"
                scan_pdf(roh, p, dpi, winkel, jpeg)
                varianten.append((f"scan{dpi}/{winkel}/{jpeg}", p))
            for art, pdf in varianten:
                ziel = ordner / ("aus_" + re.sub(r"\W", "_", art))
                if ziel.exists():
                    for alt in ziel.iterdir():
                        alt.unlink()
                if WEG == "oberflaeche":
                    erg, out, nur_frei = oberflaeche_lauf(pdf, dienst, ziel)
                else:
                    erg = analyse.analysiere_pdf(pdf, ALLE, [], [], ocr=dienst)
                    out = schwaerzung.schwaerze_pdf(pdf, erg["funde"], modell=erg.get("modell"), ocr=dienst,
                                                    ziel_ordner=ziel)
                    nur_frei = False
                ausgabe = Path(out["ausgabe"]) if out.get("ausgabe") else None
                with fitz.open(ausgabe) as d:
                    textebene = "\n".join(s.get_text() for s in d)
                ocr = ocr_text(ausgabe)
                verdacht = [(v.text, v.grund) for v in out.get("verdacht") or []]
                warn = [m.get("code") for m in (out.get("meldungen") or [])]
                for g in fall["geheim"]:
                    in_text = lesbar(g, textebene)
                    in_ocr = lesbar(g, ocr)
                    gemeldet = [v for v in verdacht if norm(g) in norm(v[0]) or (len(norm(v[0])) >= 3 and norm(v[0]) in norm(g))]
                    still = (in_text or in_ocr) and not gemeldet and (out.get("status") != "pruefen" or nur_frei)
                    ergebnisse.append(dict(fall=name, art=art, geheim=g, textebene=in_text, ocr=in_ocr,
                                           status=out.get("status"), datei=ausgabe.name if ausgabe else None,
                                           nur_freigabe=nur_frei, gemeldet=gemeldet, still=still))
                    kenn = "STILL" if still else ("LECK+PRUEFEN" if (in_text or in_ocr) else "weg")
                    print(f"{kenn:13s} {name:28s} {art:18s} {g!r:16s} text={in_text!s:5s} ocr={in_ocr!s:5s} "
                          f"status={out.get('status')} datei={ausgabe.name if ausgabe else None} frei_only={nur_frei}",
                          flush=True)
                funde = [(f["kategorie"], f["text"]) for f in erg["funde"]]
                print(f"    funde={funde}", flush=True)
                print(f"    verdacht={verdacht[:8]} meldungen={warn}", flush=True)
                if fall.get("zeige_ocr"):
                    print("    OCR-Ausgabe:", ocr.replace("\n", " | ")[:600], flush=True)
    (ARBEIT / f"ergebnis_{WEG}.json").write_text(json.dumps(ergebnisse, ensure_ascii=False, indent=1),
                                                 encoding="utf-8")


if __name__ == '__main__':
    main()
