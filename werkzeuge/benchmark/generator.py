"""Deterministischer Generator des Entwicklungskorpus (realistische deutsche Versicherungsunterlagen).

    from werkzeuge.benchmark.generator import erzeuge_korpus
    wahrheiten = erzeuge_korpus(Path("korpus"), anzahl=60, seed=1)

Für jedes Dokument entstehen <name>.pdf und <name>.wahrheit.json (Schema: BENCHMARK_SCHEMA.md,
zusätzlich je Eintrag "woerter" = Wortrechtecke in Anzeige-Koordinaten für den Pixelvergleich).

Ablauf je Dokument:
  1. Plan (Typ, Scan-Variante, Nebenkanäle) – die ersten 15 Dokumente decken alle Typen und die
     wichtigsten Varianten fest ab (auch kleine Testläufe enthalten Scans und ein Formular),
     danach wird zufällig (aus dem Seed) gemischt.
  2. Dokumenttyp setzen (dokumenttypen.py), Kopf-/Fußzeilen, Nebenkanal-Inhalte vorbereiten.
  3. Kollisionsprüfung: Steht ein zu schwärzender Wert zufällig auch im übrigen Text (Nachname
     „Lange“ und „so lange“, Vorname „Mai“ und der Monat Mai), wird das Dokument mit dem nächsten
     Unter-Seed neu erzeugt – sonst wäre die Leck-Prüfung mehrdeutig.
  4. Optional rastern (scan.py), Nebenkanäle anbringen, Schriften verkleinern, speichern.

Alles ist frei erfunden; derselbe Seed liefert dieselben Dokumente und dieselbe Wahrheit.
"""

import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen
    import fitz

from . import SCHEMA_VERSION
from . import kennungen as K
from . import scan as SC
from .bausteine import Dok, ascii_name, datum, name_bem
from .dokumenttypen import TYPEN, typ_antrag_formular
from .normalisierung import Gefaltet

GENERATOR_VERSION = "1.0"

# ----------------------------------------------------------------------
# Scan-Varianten (Wertebereiche werden je Dokument aus dem Seed gezogen)
# ----------------------------------------------------------------------
SCAN_VARIANTEN = {
    "scan_300_gut": dict(dpi=300, jpeg=(80, 85), schraeg=(0.0, 0.5), rauschen=(0, 3)),
    "scan_200_schraeg": dict(dpi=200, jpeg=(65, 80), schraeg=(1.0, 3.0), rauschen=(3, 8)),
    "scan_150_rauschen": dict(dpi=150, jpeg=(50, 65), schraeg=(0.0, 2.0), rauschen=(8, 14), unschaerfe=(0.3, 0.6)),
    "scan_120_schlecht": dict(dpi=120, jpeg=(40, 50), schraeg=(0.5, 2.5), rauschen=(8, 15), unschaerfe=(0.4, 0.7),
                              flecken=(0.0004, 0.001)),
    "scan_rotate_90": dict(dpi=200, jpeg=(60, 80), rotate=90, schraeg=(0.0, 1.5), rauschen=(2, 6)),
    "scan_rotate_180": dict(dpi=200, jpeg=(60, 80), rotate=180, schraeg=(0.0, 1.0), rauschen=(2, 6)),
    "scan_rotate_270": dict(dpi=250, jpeg=(60, 80), rotate=270, schraeg=(0.0, 1.0), rauschen=(2, 6)),
    "scan_kopfstehend": dict(dpi=200, jpeg=(60, 80), kopfstehend=True, schraeg=(0.0, 1.0), rauschen=(2, 6)),
    "fax": dict(dpi=204, dpi_y=98, fax=True, jpeg=None, schraeg=(0.0, 1.0), rauschen=(4, 10), flecken=(0.0002, 0.0006)),
    "scan_durchsuchbar": dict(dpi=[200, 300], jpeg=(60, 80), durchsuchbar=True, schraeg=(0.0, 1.0), rauschen=(2, 6)),
    "scan_farbig": dict(dpi=200, jpeg=(55, 75), farbig=True, schraeg=(0.0, 1.0), rauschen=(2, 6)),
}
# Reihenfolge, in der Scan-Varianten ab Dokument 16 vergeben werden (alle kommen vor)
_SCAN_FOLGE = ["fax", "scan_rotate_180", "scan_kopfstehend", "scan_120_schlecht", "scan_300_gut", "scan_rotate_270",
               "scan_150_rauschen", "gemischt", "scan_farbig", "scan_200_schraeg", "scan_durchsuchbar",
               "scan_rotate_90"]
NEBENKANAELE = ("anmerkung", "lesezeichen", "metadaten", "anhang", "dateiname")


@dataclass
class Plan:
    nr: int
    typ: str
    scan: str | None = None            # Schlüssel aus SCAN_VARIANTEN oder "gemischt" (nur letzte Seite)
    neben: tuple = ()

    def name(self, hauptname: str | None = None) -> str:
        basis = f"{self.nr:03d}_{self.typ}"
        if "dateiname" in self.neben and hauptname:
            basis += "_" + hauptname
        return basis + ".pdf"


# Die ersten 15 Dokumente: alle Typen, zwei Scans und ein Formular schon in den ersten zwölf
_BASIS = [
    ("brief_form_a", None, ("metadaten",)),
    ("versicherungsschein", None, ("lesezeichen",)),
    ("kfz_schadenmeldung", "scan_200_schraeg", ()),
    ("antrag_formular", None, ("anmerkung",)),
    ("arztbrief", None, ()),
    ("leistungsabrechnung", None, ("anhang",)),
    ("kuendigung", "scan_rotate_90", ("dateiname",)),
    ("beitragsrechnung", None, ()),
    ("email_ausdruck", None, ("metadaten",)),
    ("bestandsliste", None, ()),
    ("mahnung", None, ("anmerkung",)),
    ("maklervollmacht", None, ("dateiname",)),
    ("brief_form_b", "scan_durchsuchbar", ()),
    ("rentenauskunft", None, ("lesezeichen", "metadaten")),
    ("zweispaltig", None, ("anhang",)),
]
_TYP_GEWICHTE = {"brief_form_a": 10, "brief_form_b": 8, "versicherungsschein": 8, "beitragsrechnung": 6,
                 "kfz_schadenmeldung": 7, "antrag_formular": 6, "arztbrief": 6, "leistungsabrechnung": 6,
                 "rentenauskunft": 4, "kuendigung": 7, "maklervollmacht": 5, "mahnung": 5, "zweispaltig": 4,
                 "email_ausdruck": 6, "bestandsliste": 4}


def plane_korpus(anzahl: int, seed: int) -> list:
    """Deterministischer Plan für `anzahl` Dokumente."""
    plaene = []
    rng = random.Random(f"plan/{seed}")
    scan_index = 0
    for nr in range(1, anzahl + 1):
        if nr <= len(_BASIS):
            typ, scan, neben = _BASIS[nr - 1]
            plaene.append(Plan(nr, typ, scan, tuple(neben)))
            continue
        typen = list(_TYP_GEWICHTE)
        typ = rng.choices(typen, [_TYP_GEWICHTE[t] for t in typen])[0]
        scan = None
        if rng.random() < 0.32:
            scan = _SCAN_FOLGE[scan_index % len(_SCAN_FOLGE)]
            scan_index += 1
        neben = tuple(n for n in NEBENKANAELE if rng.random() < 0.15)
        plaene.append(Plan(nr, typ, scan, neben))
    return plaene


def _scan_parameter(variante: str, rng, seite: int = 0) -> SC.ScanParameter:
    spec = SCAN_VARIANTEN[variante]

    def wert(schl, standard=None):
        v = spec.get(schl, standard)
        if isinstance(v, list):
            return rng.choice(v)
        if isinstance(v, tuple):
            if all(isinstance(x, int) for x in v):
                return rng.randint(*v)
            return rng.uniform(*v)
        return v
    schraeg = wert("schraeg", 0.0) * rng.choice([-1, 1])
    p = SC.ScanParameter(dpi=wert("dpi", 200), dpi_y=spec.get("dpi_y"), jpeg=wert("jpeg", 75), schraeg=schraeg,
                         rauschen=wert("rauschen", 0.0), unschaerfe=wert("unschaerfe", 0.0),
                         flecken=wert("flecken", 0.0), rotate=spec.get("rotate", 0),
                         kopfstehend=spec.get("kopfstehend", False), fax=spec.get("fax", False),
                         farbig=spec.get("farbig", False), durchsuchbar=spec.get("durchsuchbar", False),
                         versatz=(rng.uniform(1.0, 4.0) * rng.choice([-1, 1]), rng.uniform(-3.0, 3.0)),
                         papier=rng.randint(236, 252), seed=rng.randint(0, 2**31 - 1) + seite)
    return p


# ----------------------------------------------------------------------
# Nebenkanäle (Metadaten, Lesezeichen, Anmerkungen, Anhänge, Dateiname)
# ----------------------------------------------------------------------
def _nebenkanaele_vorbereiten(dok: Dok, plan: Plan) -> tuple:
    """Legt die Einträge der Nebenkanäle an und liefert (Operationen für das fertige PDF,
    Namensteil für den Dateinamen)."""
    rng = dok.rng
    satz = dok.satz
    hp = dok.hauptperson or dok.person()
    ops = []
    dateiname_teil = None
    seiten = len(satz.seiten)
    if "metadaten" in plan.neben:
        autor = dok.person(titel_quote=0.0)
        vnr = K.vertragsnummer(rng, "VS")
        titel = f"{dok.titel or 'Dokument'} {hp.voll()}"
        satz.eintrag(hp.voll(), "namen", 1, kanal="metadaten", bemerkung=name_bem(hp, "Info-Dict Titel und XMP dc:title"))
        satz.eintrag(autor.voll(), "namen", 1, kanal="metadaten", bemerkung=name_bem(autor, "Info-Dict Autor und XMP dc:creator"))
        satz.eintrag(vnr, "vertrag", 1, kanal="metadaten", bemerkung="Info-Dict Stichwörter")
        satz.klartext_merken(0, dok.titel or "Dokument")
        satz.klartext_merken(0, "Versicherungsunterlagen Bestand")

        def op_meta(doc, titel=titel, autor=autor.voll(), vnr=vnr):
            doc.set_metadata({"title": titel, "author": autor, "subject": "Versicherungsunterlagen",
                              "keywords": f"Bestand, {vnr}", "creator": "Bestandsführung",
                              "producer": "Benchmark-Generator", "creationDate": "D:20250301120000+01'00'",
                              "modDate": "D:20250301120000+01'00'"})
            xmp = ('<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?><x:xmpmeta xmlns:x="adobe:ns:meta/">'
                   '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description rdf:about="" '
                   'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title><rdf:Alt><rdf:li xml:lang="x-default">'
                   f'{escape(titel)}</rdf:li></rdf:Alt></dc:title><dc:creator><rdf:Seq><rdf:li>{escape(autor)}'
                   '</rdf:li></rdf:Seq></dc:creator></rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end="w"?>')
            doc.set_xml_metadata(xmp)
        ops.append(op_meta)
    if "lesezeichen" in plan.neben:
        nn = hp.liste()
        satz.eintrag(nn, "namen", 1, kanal="lesezeichen", bemerkung=name_bem(hp, "Lesezeichen Nachname, Vorname"))
        toc = [[1, f"{dok.titel or 'Dokument'} – {nn}", 1]]
        if seiten > 1:
            zweit = dok.person()
            satz.eintrag(zweit.voll(), "namen", 2, kanal="lesezeichen", bemerkung=name_bem(zweit, "Lesezeichen Seite 2"))
            toc.append([1, f"Anlage zu Vorgang {zweit.voll()}", 2])
        satz.klartext_merken(0, dok.titel or "Dokument")
        satz.klartext_merken(0, "Anlage zu Vorgang")
        ops.append(lambda doc, toc=toc: doc.set_toc(toc))
    if "anmerkung" in plan.neben:
        sb = dok.person(titel_quote=0.0)
        tel = dok.telefon(hp)
        notiz = f"Rückruf bei {hp.herr_frau} {hp.nachname} unter {tel} – Unterlagen fehlen noch"
        seite_nr = rng.randint(1, seiten)
        satz.eintrag(hp.nachname, "namen", seite_nr, kanal="anmerkung", bemerkung=name_bem(hp, "Notiz-Anmerkung (Popup)"))
        satz.eintrag(tel, "telefon", seite_nr, kanal="anmerkung", bemerkung="Notiz-Anmerkung (Popup)")
        satz.eintrag(sb.initiale(), "namen", seite_nr, kanal="anmerkung", bemerkung=name_bem(sb, "Autor der Anmerkung; Initiale"))
        satz.klartext_merken(0, "Rückruf bei – Unterlagen fehlen noch")
        frei = None
        gedreht = plan.scan in ("scan_rotate_90", "scan_rotate_180", "scan_rotate_270")
        if rng.random() < 0.6 and not gedreht:      # FreeText nur auf ungedrehten Seiten
            bearbeiter = dok.person(titel_quote=0.0)
            frei = f"Eingang {datum(dok.heute)} – bearbeitet: {bearbeiter.nachname}"
            satz.eintrag(bearbeiter.nachname, "namen", seite_nr, kanal="anmerkung",
                         bemerkung=name_bem(bearbeiter, "sichtbare FreeText-Anmerkung (Eingangsstempel)"))
            satz.klartext_merken(0, f"Eingang {datum(dok.heute)} – bearbeitet:")

        def op_annot(doc, seite_nr=seite_nr, notiz=notiz, autor=sb.initiale(), frei=frei):
            page = doc[seite_nr - 1]
            r = page.rect
            a = page.add_text_annot((r.width - 40, 40), notiz, icon="Note")
            a.set_info(title=autor, subject="Notiz")
            a.update()
            if frei and page.rotation == 0:
                f = page.add_freetext_annot(fitz.Rect(r.width - 210, r.height - 75, r.width - 25, r.height - 55), frei,
                                            fontsize=8, text_color=(0.7, 0.0, 0.0))
                f.update()
        ops.append(op_annot)
    if "anhang" in plan.neben:
        iban = dok.iban_text()
        tel = dok.telefon(hp, mobil=True)
        datei = f"Gespraechsnotiz_{ascii_name(hp.nachname).replace(' ', '_')}.txt"
        satz.eintrag(ascii_name(hp.nachname).replace(" ", "_"), "namen", 1, kanal="anhang",
                     bemerkung=name_bem(hp, "Dateiname des Anhangs"))
        satz.eintrag(hp.voll(), "namen", 1, kanal="anhang", bemerkung=name_bem(hp, "Inhalt des Anhangs"))
        satz.eintrag(tel, "telefon", 1, kanal="anhang", bemerkung="Inhalt des Anhangs")
        satz.eintrag(iban, "iban", 1, kanal="anhang", bemerkung="Inhalt des Anhangs")
        inhalt = (f"Gesprächsnotiz vom {datum(dok.heute)}\nKunde: {hp.voll()}\nRückrufnummer: {tel}\n"
                  f"Neue Bankverbindung: IBAN {iban}\nBitte Vertrag anpassen.\n")
        satz.klartext_merken(0, "Gesprächsnotiz vom Kunde: Rückrufnummer: Neue Bankverbindung: IBAN Bitte Vertrag anpassen.")

        def op_anhang(doc, datei=datei, inhalt=inhalt):
            doc.embfile_add(datei, inhalt.encode("utf-8"), filename=datei, desc="Notiz")
            # feste Zeitstempel, damit derselbe Seed byte-gleiche Dateien liefert
            for xref in range(1, doc.xref_length()):
                try:
                    if "/EmbeddedFile" not in (doc.xref_object(xref) or ""):
                        continue
                    for schl in ("Params/CreationDate", "Params/ModDate", "CreationDate", "ModDate"):
                        if doc.xref_get_key(xref, schl)[0] != "null":
                            doc.xref_set_key(xref, schl, "(D:20250301120000)")
                except Exception:
                    pass
        ops.append(op_anhang)
    if "dateiname" in plan.neben:
        dateiname_teil = re.sub(r"[^A-Za-z0-9]", "", ascii_name(hp.nachname)) or "Kunde"
        satz.eintrag(dateiname_teil, "namen", 1, kanal="dateiname", bemerkung=name_bem(hp, "Nachname im Dateinamen"))
    return ops, dateiname_teil


# ----------------------------------------------------------------------
# Kollisionsprüfung
# ----------------------------------------------------------------------
def kollisionen(dok: Dok) -> list:
    """Zu schwärzende Werte, die zusätzlich im unausgezeichneten Text oder in einem
    Kontext-Eintrag stehen (an Wortgrenzen, gefaltet)."""
    texte = [" ".join(stuecke) for stuecke in dok.satz.klartext.values()]
    texte += [e["text"] for e in dok.satz.eintraege if e["erwartung"] == "behalten"]
    gefaltet = [Gefaltet(t) for t in texte]
    treffer = []
    gesehen = set()
    for e in dok.satz.eintraege:
        if e["erwartung"] != "schwaerzen":
            continue
        nadel = Gefaltet(e["text"])
        if not nadel.kette or nadel.kette in gesehen:
            continue
        gesehen.add(nadel.kette)
        if any(g.enthaelt(nadel) for g in gefaltet):
            treffer.append(e["text"])
    return treffer


# ----------------------------------------------------------------------
# Rastern
# ----------------------------------------------------------------------
def _scannen(dok: Dok, plan: Plan) -> list:
    alt = dok.satz.doc
    neu = fitz.open()
    n = len(alt)
    scan_seiten = {n - 1} if plan.scan == "gemischt" else set(range(n))
    variante = "scan_200_schraeg" if plan.scan == "gemischt" else plan.scan
    merkmale = set()
    basis_rng = random.Random(f"scan/{dok.satz.kennung}")
    for i in range(n):
        eintraege = [e for e in dok.satz.eintraege if e["seite"] == i + 1 and e["kanal"] in ("text", "scan", "formular")]
        if i in scan_seiten:
            p = _scan_parameter(variante, basis_rng, i)
            SC.seite_scannen(alt[i], neu, p, eintraege, schrift_unsichtbar=dok.stil.normal)
            merkmale.update(p.beschreibung())
        else:
            neu.insert_pdf(alt, from_page=i, to_page=i)
    if plan.scan == "gemischt":
        merkmale.add("gemischt_text_und_scan")
    dok.satz.doc = neu
    alt.close()
    return sorted(merkmale)


# ----------------------------------------------------------------------
# Ein Dokument / ganzer Korpus
# ----------------------------------------------------------------------
def _merkmale_aus_eintraegen(eintraege: list) -> set:
    mm = set()
    for e in eintraege:
        b = e.get("bemerkung", "")
        if "Versalien" in b:
            mm.add("versalien")
        if "Diakritika" in b:
            mm.add("diakritika")
        if "Silbentrennung" in b:
            mm.add("silbentrennung")
        if e["kanal"] in ("anmerkung", "lesezeichen", "metadaten", "anhang", "dateiname"):
            mm.add(e["kanal"])
    return mm


def erzeuge_dokument(plan: Plan, seed: int, ordner: Path, max_versuche: int = 40) -> dict:
    """Erzeugt ein Dokument nach Plan, speichert PDF + Wahrheit und liefert die Wahrheit."""
    ordner = Path(ordner)
    ordner.mkdir(parents=True, exist_ok=True)
    rest_kollisionen = []
    for versuch in range(max_versuche):
        rng = random.Random(f"{seed}/{plan.nr}/{versuch}")
        dok = Dok(rng, f"{seed}-{plan.nr:03d}", querformat=(plan.typ == "bestandsliste"))
        if plan.typ == "antrag_formular" and plan.scan:
            typ = typ_antrag_formular(dok, formular=False)       # Papierantrag, eingescannt
        else:
            typ = TYPEN[plan.typ](dok)
        gesamt = len(dok.satz.seiten)
        for s in dok.satz.seiten:
            for f in dok.kopf_fuss:
                f(s, s.nr, gesamt)
        ops, dateiname_teil = _nebenkanaele_vorbereiten(dok, plan)
        rest_kollisionen = kollisionen(dok)
        if not rest_kollisionen:
            break
    merkmale = set(dok.satz.merkmale) | dok.stil.merkmale()
    if dok.satz.trennungen:
        merkmale.add("silbentrennung")
    if len(dok.satz.seiten) > 1:
        merkmale.add("mehrseitig")
    if plan.scan:
        merkmale.update(_scannen(dok, plan))
    doc = dok.satz.doc
    for op in ops:
        op(doc)
    if "metadaten" not in plan.neben:
        doc.set_metadata({"producer": "Benchmark-Generator", "creator": "Bestandsführung",
                          "creationDate": "D:20250301120000+01'00'", "modDate": "D:20250301120000+01'00'"})
    try:
        doc.subset_fonts()
    except Exception:
        pass                               # ohne Subsetting nur größere Dateien
    name = plan.name(dateiname_teil)
    pdf_pfad = ordner / name
    doc.save(pdf_pfad, garbage=3, deflate=True, no_new_id=True)
    seiten = len(doc)
    doc.close()
    dok.satz.eintraege.sort(key=lambda e: e["seite"])
    wahrheit = dok.satz.wahrheit(name, typ, seiten)
    merkmale |= _merkmale_aus_eintraegen(wahrheit["eintraege"])
    wahrheit["merkmale"] = sorted(merkmale)
    wahrheit["erzeugung"] = {"generator": GENERATOR_VERSION, "schema": SCHEMA_VERSION, "seed": seed, "nr": plan.nr,
                             "plan_typ": plan.typ, "scan": plan.scan, "nebenkanaele": list(plan.neben),
                             "versuch": versuch, "schrift": dok.stil.familie.name,
                             "schrift_datei": Path(dok.stil.normal.datei).name if dok.stil.normal.datei else None,
                             "groesse": dok.stil.groesse, "zeilenabstand": dok.stil.zeilenabstand}
    if rest_kollisionen:
        wahrheit["erzeugung"]["kollisionen"] = rest_kollisionen
    (ordner / (Path(name).stem + ".wahrheit.json")).write_text(
        json.dumps(wahrheit, ensure_ascii=False, indent=1), encoding="utf-8")
    return wahrheit


def erzeuge_korpus(ordner: Path, anzahl: int, seed: int = 1, melde=None) -> list:
    """Erzeugt `anzahl` Dokumente in `ordner` und liefert die Wahrheiten."""
    ergebnisse = []
    for plan in plane_korpus(anzahl, seed):
        w = erzeuge_dokument(plan, seed, ordner)
        ergebnisse.append(w)
        if melde:
            melde(f"erzeugt: {w['dokument']} ({w['seiten']} S., {len(w['eintraege'])} Einträge)")
    return ergebnisse
