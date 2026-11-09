"""Briefstruktur (Vertrag Abschnitt 3): »struktur.anrede_gruss«, »struktur.betreff«, »struktur.ort_datum«
und »struktur.kopf_fuss«.

struktur.anrede_gruss
    "Sehr geehrte(r) Frau/Herr <Name>", "Liebe(r) <Name>", "Hallo <Name>", "Guten Tag <Name>"; die
    Grußformel ("Mit freundlichen Grüßen" …) und die folgenden kurzen Zeilen (Name, Funktion –
    Firmenzeilen und Abteilungen bleiben), "i. A. / i. V. / gez. / ppa. <Name>"; Unterschriftszeilen
    mit Namen über Rollen-Etiketten ("Emily Kelly | Burak Kurt" über "Mandant | Makler").
struktur.betreff
    Betreffzeile (über der Anrede bzw. hinter "Betreff:"/"Betr.:"): Kennungen ohne Etikett
    ("Auszahlung aus Ihrem Vertrag 47.897.336.2") – keine Daten, Beträge, Paragrafen, Jahreszahlen.
struktur.ort_datum
    Unterschriftszeile "<Ort>, [den] <Datum>": der Ort, außer er gehört zu einer Organisation dieses
    Dokuments ("Stuttgart, 14.03.2025" im Brief eines Stuttgarter Versicherers bleibt).
struktur.kopf_fuss
    Kopf-/Fußzeilen, die auf mehreren Seiten wiederkehren: Kennungen darin (ohne Register-, Bank- und
    Telefonangaben der Firma).
"""

from __future__ import annotations

import re

from . import Treffer, detektor
from .struktur import (etiketten, ist_kennungsform, kennung_spanne, lage, namen_spanne,
                       ort_spanne, plz_ort_spannen, ueberlappung)
from .struktur_adresse import firmen_beleg, firmenkontext

# ----------------------------------------------------------------------
# Anrede und Gruß
# ----------------------------------------------------------------------
_ANREDE_RE = re.compile(
    r"(?i:sehr[ ]+geehrte[rs]?|hochverehrte[r]?|liebe[rs]?|hallo|guten[ ]+(?:tag|morgen|abend)|moin|servus|"
    r"grüß[ ]+gott|dear|hi)[ ,]+(?:(?:Frau|Herrn?|Fr\.|Hr\.)[ ]+)?")
_GRUSS_RE = re.compile(
    r"^[ \t]*(?:mit[ ]+(?:freundlichen|freundlichem|besten|herzlichen|lieben|kollegialen|vielen)[ ]+"
    r"gr(?:ü|ue)(?:ß|ss)(?:en|e)?"
    r"|(?:freundliche|viele|beste|herzliche|liebe|schöne|sonnige|kollegiale)[ ]+gr(?:ü|ue)(?:ß|ss)e"
    r"|hochachtungsvoll|mfg|lg|vg|gruß|grüße|best[ ]+regards|kind[ ]+regards|regards|cordialement"
    r"|mit[ ]+freundlichem[ ]+gruß|freundlichst)[ ]*[,.!]?[ \t]*$", re.IGNORECASE)
_HERR_FRAU_RE = re.compile(r"(?<![\wäöüß])(?:Herrn?|Frau|Hr\.|Fr\.)[ ]+(?=[^\W\d_])")
_UNTERZEICHNER_RE = re.compile(r"(?:i\.[ ]?A\.|i\.[ ]?V\.|gez\.|ppa\.|p\.[ ]?p\.|per[ ]+Prokura|im[ ]+Auftrag|"
                               r"in[ ]+Vertretung)[ ]+")
QUELLE_ANREDE = "struktur.anrede_gruss"


def _name_nach(text: str, pos: int, ende: int, streng: bool, komma: bool = False):
    """Name ab pos. Hinter Anrede, Gruß und "i. A." gilt die Form "Nachname, Vorname" nicht – in "Sehr
    geehrter Herr Müller, Max Müller ist versichert" ist "Müller, Max" keine Person (Gutachten EQ-10)."""
    sp = namen_spanne(text, pos, ende, komma=komma)
    if sp is None:
        return None
    if streng and not (sp.bekannt or sp.woerter >= 2):
        return None
    return sp


def _zeile_ist_name(text: str, z) -> list:
    """Namen einer kurzen Zeile im Unterschriftsbereich (je Zelle; Zeilen mit Ziffern, Firmenwörtern,
    Feldbezeichnern bleiben)."""
    zt = text[z.start:z.ende]
    if not zt.strip() or firmen_beleg(zt) or len(zt.split()) > 12:
        return []
    aus = []
    for teil in re.finditer(r"[^\t]+", zt):
        s, e = z.start + teil.start(), z.start + teil.end()
        inhalt = text[s:e].strip()
        if not inhalt or any(c.isdigit() for c in inhalt):
            continue
        m = _UNTERZEICHNER_RE.match(inhalt)
        anfang = s + (len(text[s:e]) - len(text[s:e].lstrip()))
        if m:
            anfang += m.end()
        sp = _name_nach(text, anfang, e, streng=not m, komma=not m)
        if sp is None:
            continue
        if sp.ende - sp.start < 0.6 * len(text[anfang:e].strip()):
            continue
        aus.append((sp.start, sp.ende, "namen", text[sp.start:sp.ende] if sp.woerter > 1 else None))
    return aus


@detektor(QUELLE_ANREDE, {"namen"})
def anrede_gruss(dok, kontext):
    """Namen in Anrede, Grußformel/Unterschriftsblock, i. A./gez.-Zeilen und Unterschriftszeilen."""
    treffer = []
    for nr, seite in enumerate(dok.seiten):
        text = seite.text
        if not text.strip():
            continue
        lg = lage(seite)
        werte = []
        zeilen = {z.id: z for z in seite.zeilen}
        for z in seite.zeilen:
            zt = text[z.start:z.ende]
            # Anrede
            for m in _ANREDE_RE.finditer(text, z.start, z.ende):
                sp = _name_nach(text, m.end(), z.ende, streng=False)
                if sp is None:
                    continue
                rest = text[sp.ende:z.ende].lstrip()
                if rest and rest[0] not in ",!.:" and len(rest.split()) > 0 and not rest.startswith("und"):
                    if sp.woerter < 2 and not sp.bekannt:
                        continue
                werte.append((sp.start, sp.ende, "namen", text[sp.start:sp.ende] if sp.woerter > 1 else None))
            # "Herr/Frau <Name>" im Fließtext (auch mit Partikel oder Titel: "Frau de Vries", "Herr Dr. Ågren")
            for m in _HERR_FRAU_RE.finditer(text, z.start, z.ende):
                sp = _name_nach(text, m.end(), z.ende, streng=False)
                if sp is None or sp.start - m.end() > 30:
                    continue
                werte.append((sp.start, sp.ende, "namen", text[sp.start:sp.ende] if sp.woerter > 1 else None))
            # i. A. / gez. irgendwo in der Zeile
            for m in _UNTERZEICHNER_RE.finditer(text, z.start, z.ende):
                vorn = text[z.start:m.start()]
                if vorn.strip() and not vorn.endswith(("\t", "  ")):
                    continue
                sp = _name_nach(text, m.end(), z.ende, streng=False)
                if sp is not None:
                    werte.append((sp.start, sp.ende, "namen", text[sp.start:sp.ende] if sp.woerter > 1 else None))
            # Grußformel -> folgende kurze Zeilen
            if _GRUSS_RE.match(zt):
                h = max(lg.hoehe, 4.0)
                box = lg.zeilen_box.get(z.id)
                gezaehlt = 0
                for zid in lg.zeilen_darunter(z.id, 7.0 * h):
                    zb = lg.zeilen_box.get(zid)
                    if zb is None or box is None or zb[0] > box[0] + 30 * h or zb[2] < box[0] - h:
                        continue
                    z2 = zeilen[zid]
                    inhalt = text[z2.start:z2.ende].strip()
                    if not inhalt:
                        continue
                    gezaehlt += 1
                    if gezaehlt > 4 or len(inhalt.split()) > 12 or (inhalt.endswith(".") and len(inhalt.split()) > 4):
                        break
                    werte += _zeile_ist_name(text, z2)
        # Unterschriftszeilen: Namen über Rollen-Etiketten
        werte += _namen_ueber_rollen(seite, lg)
        for a, b, kat, gruppe in werte:
            treffer.append(Treffer(dok.global_(nr, a), dok.global_(nr, b), kat, QUELLE_ANREDE, 0.75, gruppe))
    return treffer


def _namen_ueber_rollen(seite, lg) -> list:
    """Zeile mit Personen-Rollen ("Mandant | Makler", "Versicherungsnehmer", "Unterschrift") unter einer
    Zeile mit Namen in derselben Spalte (Unterschriftsblock)."""
    text = seite.text
    aus = []
    ets = [et for et in etiketten(seite) if "person" in et.arten]
    if not ets:
        return aus
    gesehen = set()
    for et in ets:
        zelle = lg.zelle_bei(et.start)
        if zelle is None or zelle.zeile in gesehen:
            continue
        rest = text[zelle.start:zelle.ende]
        # die Zelle besteht nur aus Rollenwörtern ("Mandant", "(Unterschrift Versicherungsnehmer)")
        if len(rest.split()) > 4 or any(c.isdigit() for c in rest):
            continue
        h = max(zelle.hoehe, 4.0)
        for zid in lg.zeilen_darueber(zelle.zeile, 2.2 * h):
            for c in lg.zellen_je_zeile.get(zid, ()):
                if ueberlappung(c.x0, c.x1, zelle.x0 - h, zelle.x1 + h) <= 0:
                    continue
                inhalt = text[c.start:c.ende].strip()
                if not inhalt or any(ch.isdigit() for ch in inhalt) or firmen_beleg(inhalt):
                    continue
                sp = namen_spanne(text, c.start, c.ende)
                if sp and sp.ende - sp.start >= 0.6 * len(inhalt) and (sp.bekannt or sp.woerter >= 2):
                    aus.append((sp.start, sp.ende, "namen", text[sp.start:sp.ende] if sp.woerter > 1 else None))
            break
    return aus


# ----------------------------------------------------------------------
# Betreff
# ----------------------------------------------------------------------
_BETREFF_ETIKETT_RE = re.compile(r"(?i)^[ \t]*(?:betreff|betr\.|betrifft|subject|re|aw|wg|fwd?)[ \t]*:")
_KEINE_KENNUNG_DAVOR_RE = re.compile(r"(?i)(?:§+|art\.|abs\.|nr\.|ziffer|seite|tel\.?|telefon|fax|vom|bis|ab|"
                                     r"zum|am|hrb|hra|iban|bic)[ \t]*$")
QUELLE_BETREFF = "struktur.betreff"


def _betreff_zeilen(seite, lg) -> list:
    """Zeilen-IDs der Betreffzeile(n): hinter "Betreff:" oder die 1–2 Zeilen direkt über der Anrede."""
    text = seite.text
    aus = []
    for z in seite.zeilen:
        zt = text[z.start:z.ende]
        if _BETREFF_ETIKETT_RE.match(zt):
            aus.append(z.id)
            continue
        if _ANREDE_RE.match(zt.strip()) and re.match(r"(?i)[ \t]*(?:sehr|liebe|hallo|guten)", zt):
            h = max(lg.hoehe, 4.0)
            box = lg.zeilen_box.get(z.id)
            for zid in lg.zeilen_darueber(z.id, 4.0 * h)[:2]:
                zb = lg.zeilen_box.get(zid)
                if zb is None or box is None or abs(zb[0] - box[0]) > 2 * h:
                    continue
                inhalt = text[seite.zeilen[zid].start:seite.zeilen[zid].ende] if zid < len(seite.zeilen) else ""
                if plz_ort_spannen(text, seite.zeilen[zid].start, seite.zeilen[zid].ende):
                    break
                if inhalt.strip():
                    aus.append(zid)
    return aus


@detektor(QUELLE_BETREFF, {"vertrag"})
def betreff(dok, kontext):
    """Kennungen ohne Etikett in der Betreffzeile."""
    treffer = []
    for nr, seite in enumerate(dok.seiten):
        text = seite.text
        if not text.strip():
            continue
        lg = lage(seite)
        zeilen = {z.id: z for z in seite.zeilen}
        for zid in dict.fromkeys(_betreff_zeilen(seite, lg)):
            z = zeilen.get(zid)
            if z is None:
                continue
            pos = z.start
            while pos < z.ende:
                m = re.compile(r"[A-Za-z0-9ÄÖÜ]").search(text, pos, z.ende)
                if not m:
                    break
                p = m.start()
                if p > z.start and (text[p - 1].isalnum() or text[p - 1] in "-/."):
                    pos = p + 1
                    continue
                sp = kennung_spanne(text, p, z.ende, 4)
                if sp is None:
                    nxt = re.compile(r"[ \t,;:()]").search(text, p, z.ende)
                    pos = nxt.end() if nxt else z.ende
                    continue
                wert = text[sp[0]:sp[1]]
                if _KEINE_KENNUNG_DAVOR_RE.search(text[z.start:sp[0]]) or not _betreff_kennung(wert):
                    pos = sp[1]
                    continue
                treffer.append(Treffer(dok.global_(nr, sp[0]), dok.global_(nr, sp[1]), "vertrag", QUELLE_BETREFF,
                                       0.7))
                pos = sp[1]
    return treffer


def _betreff_kennung(wert: str) -> bool:
    """Kennungsform im Betreff: mindestens 5 Ziffern; gemischt oder mit Trennern, sonst lang."""
    ziffern = sum(c.isdigit() for c in wert)
    if ziffern < 5:
        return False
    kompakt = wert.replace(" ", "")
    if kompakt.isdigit():
        return len(kompakt) >= 6
    return True


# ----------------------------------------------------------------------
# Ort, Datum
# ----------------------------------------------------------------------
_ORT_DATUM_RE = re.compile(
    r"(?:^|(?<=\t))[ \t]*(?P<ort>[A-ZÄÖÜ][^\t\n,]{1,40}?)[ \t]*,[ \t]*(?:den[ \t]+|am[ \t]+)?"
    r"(?:\d{1,2}\.[ ]?(?:\d{1,2}\.|[A-ZÄÖÜa-zäöü]{3,9}\.?)[ ]?(?:19|20)?\d{2}(?!\d)|\d{4}-\d{2}-\d{2})",
    re.MULTILINE)
QUELLE_ORT = "struktur.ort_datum"


_SITZ_RE = re.compile(r"(?i)sitz(?:[ ]der[ ]gesellschaft)?[ ]*:?[ ]*([A-ZÄÖÜ][\wäöüß.\- ]{1,40}?)(?=[ ]*[·,|;\t]|$)")


def firmen_orte(dok) -> set:
    """Orte (Vergleichsform), die zu einer Organisation des Dokuments gehören: PLZ + Ort in
    Firmenzeilen, "Sitz: <Ort>"."""
    zw = getattr(dok, "_struktur_firmen_orte", None)
    if zw is not None and zw[0] is dok.text:
        return zw[1]
    orte = set()
    for seite in dok.seiten:
        text = seite.text
        fk = firmenkontext(seite)
        for z in seite.zeilen:
            zt = text[z.start:z.ende]
            for m in _SITZ_RE.finditer(zt):
                orte.add(_ortsform(m.group(1)))
            if not re.search(r"\d{4,5}", zt):
                continue
            for a, b in plz_ort_spannen(text, z.start, z.ende):
                if fk.firma(z.id, b):
                    ort = re.sub(r"^\D*\d{4,5}[ \t]*", "", text[a:b])
                    orte.add(_ortsform(ort))
    try:
        dok._struktur_firmen_orte = (dok.text, orte)
    except AttributeError:
        pass
    return orte


def _ortsform(ort: str) -> str:
    return " ".join(ort.casefold().replace("\n", " ").split())


@detektor(QUELLE_ORT, {"plzort"})
def ort_datum(dok, kontext):
    """Ort in Unterschriftszeilen "<Ort>, den <Datum>" (nicht der Ort einer Organisation)."""
    treffer = []
    firma = None
    for nr, seite in enumerate(dok.seiten):
        text = seite.text
        if not text.strip():
            continue
        for z in seite.zeilen:
            for m in _ORT_DATUM_RE.finditer(text, z.start, z.ende):
                s = m.start("ort")
                sp = ort_spanne(text, s, m.end("ort"))
                if sp is None or sp[1] < m.end("ort") - 1:
                    continue
                ort = text[sp[0]:sp[1]]
                if len(ort.split()) > 5 or firmen_beleg(ort):
                    continue
                if firma is None:
                    firma = firmen_orte(dok)
                form = _ortsform(ort)
                if form in firma or any(form.startswith(f + " ") or f.startswith(form + " ") for f in firma):
                    continue
                treffer.append(Treffer(dok.global_(nr, sp[0]), dok.global_(nr, sp[1]), "plzort", QUELLE_ORT, 0.6))
    return treffer


# ----------------------------------------------------------------------
# Kopf- und Fußzeilen
# ----------------------------------------------------------------------
QUELLE_KOPF = "struktur.kopf_fuss"
_TOKEN_ANFANG_RE = re.compile(r"(?<![\w\-/.])[A-Za-z0-9][\w\-/.]*")
_FIRMEN_NUMMER_DAVOR_RE = re.compile(r"(?i)(?:hrb|hra|amtsgericht[\w ]*|register\w*|blz|bic|iban|tel\.?|telefon|"
                                     r"fax|telefax|ust-?id(?:nr)?\.?|steuer-?nr\.?|seite|§+|nr\.)[ \t:.]*$")


@detektor(QUELLE_KOPF, {"vertrag"})
def kopf_fuss(dok, kontext):
    """Kennungen in Kopf-/Fußzeilen, die auf mehreren Seiten wiederkehren."""
    if len(dok.seiten) < 2:
        return []
    je_form: dict = {}
    for nr, seite in enumerate(dok.seiten):
        text = seite.text
        lg = lage(seite)
        hoehe = lg.hoehe_seite
        for z in seite.zeilen:
            box = lg.zeilen_box.get(z.id)
            if box is None or not (box[3] < 0.15 * hoehe or box[1] > 0.85 * hoehe):
                continue
            form = re.sub(r"\d+", "#", " ".join(text[z.start:z.ende].split()))
            je_form.setdefault(form, []).append((nr, z))
    treffer = []
    for form, vorkommen in je_form.items():
        if len({nr for nr, _ in vorkommen}) < 2:
            continue
        for nr, z in vorkommen:
            text = dok.seiten[nr].text
            pos = z.start
            while pos < z.ende:
                m = _TOKEN_ANFANG_RE.search(text, pos, z.ende)
                if not m:
                    break
                sp = kennung_spanne(text, m.start(), z.ende, 5)
                if sp is None or not ist_kennungsform(text[sp[0]:sp[1]], 5) \
                        or _FIRMEN_NUMMER_DAVOR_RE.search(text[z.start:sp[0]]):
                    pos = m.end()
                    continue
                treffer.append(Treffer(dok.global_(nr, sp[0]), dok.global_(nr, sp[1]), "vertrag", QUELLE_KOPF, 0.6))
                pos = sp[1]
    return treffer
