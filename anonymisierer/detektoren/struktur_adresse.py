"""Anschriften: »struktur.adressblock«, »struktur.anschriftfeld« und die Firmen-Entscheidung für die
Muster »muster.strasse« / »muster.plzort« (Vertrag Abschnitt 3, Gutachten EQ-15).

Kunde oder Organisation? Anschriften von Versicherern, Banken, Behörden und Firmen sind keine
Personendaten; schwärzt man sie, verliert die KI den Zusammenhang und die Nutzerin muss sie einzeln
abhaken. Ein Anschriftenteil gehört zu einer Organisation, wenn seine Zeile, sein Block oder (bei
einem Block ohne Person) der Block direkt darüber eine Rechtsform (GmbH, AG, VVaG, a.G. …), ein
Organisationswort (…versicherung, …kasse, Bank, Amtsgericht, Kundenservice …), Registerangaben (HRB,
Sitz, Vorstand, USt-IdNr.), eine Web-Adresse oder eine Organisation der Erlaubnisliste
(wissen.ist_allowlist, daten/versicherer_und_organisationen.txt) enthält – und keine Anredezeile
(Herrn, Frau, Familie) dabeisteht. Kundenanschriften gehen IMMER weg.

Umsetzung: »muster.strasse« und »muster.plzort« werden mit ersetzt=True neu registriert – dieselben
Muster, aber als Stellen (muster.stellen; keine Stelle über einen Spaltentrenner, dazu die zeilenweise
Lesart; ohne Stellen-Schnittstelle der bisher registrierte Detektor), danach entfallen Treffer in
Firmenkontext und offensichtliche Fehlgriffe ("HRB 16963 / Vorstand" ist keine PLZ mit Ort). Unbekannte Firmen-
anschriften (Firmenhinweis, aber keine Organisation der Erlaubnisliste) bleiben stehen und werden als
Vorschlag in dok.struktur_vorschlaege vermerkt, damit die Oberfläche sie zeigen kann.

»struktur.adressblock«: Block bzw. Zeilenfolge, deren letzte Zeile PLZ + Ort ist (auch Postfach, c/o,
eingerückte "neue Anschrift"), und Zeilen mit Trennern ("Name · Straße 1 · 12345 Ort", "Name, Straße 1,
12345 Ort, Tel. …"): die Zeile davor ist die Straße – auch ohne Straßenwort ("Alt-Moabit 63", "Platz
der Republik 99 a") –, die Zeilen davor sind Namen.
»struktur.anschriftfeld«: das Anschriftfeld nach DIN 5008 (Form A: 27–72 mm, Form B: 45–90 mm von oben,
20–105 mm von links, ±8 mm Toleranz) auf der ersten Seite und Seiten mit Briefkopf: Empfängerzeilen
(ohne Anrede- und Firmenzeilen) sind Namen, Straße, Ort.
"""

from __future__ import annotations

import functools
import re

from ..seitenmodell import SPALTENTRENNER
from . import REGISTER, Treffer, detektor, registrieren
from .struktur import (lage, namen_spanne, ort_verlaengern, plz_ort_kappen, plz_ort_spannen, strasse_spanne,
                       _muster, _wissen)

MM = 72 / 25.4

# Rechtsformen und Organisationswörter (ganze Wörter bzw. Wortenden)
_RECHTSFORM_RE = re.compile(
    r"(?<![\wäöüß])(?:GmbH|gGmbH|mbH|AG|KG|KGaA|OHG|oHG|GbR|SE|eG|e\.[ ]?G\.|e\.[ ]?V\.|a\.[ ]?G\.|VVaG|"
    r"V\.a\.G\.|AöR|KdöR|Ltd\.?|Inc\.?|Corp\.?|S\.A\.|S\.p\.A\.|B\.V\.|N\.V\.|PartG(?:mbB)?|UG)(?![\wäöüß])"
    r"|&[ ]?Co\.")
_ORGANISATION_RE = re.compile(
    r"(?i)(?<![\wäöüß])[\wäöüß\-]*(?:versicherung|versicherungen|versicherungs-ag|assekuranz|kasse|bank|"
    r"genossenschaft|gericht|finanzamt|landratsamt|bürgeramt|standesamt|stadtverwaltung|gemeindeverwaltung|"
    r"kreisverwaltung|ministerium|bundesamt|landesamt|jobcenter|polizeipräsidium|polizeidirektion|"
    r"polizeiinspektion|polizeirevier|klinikum|krankenhaus|universität|hochschule|stiftung|verband|kammer|"
    r"kundenservice|servicecenter|service-center|hauptverwaltung|niederlassung|geschäftsstelle|direktion|"
    r"versicherungsgruppe|konzern|holding|rentenversicherung)(?![\wäöüß])"
    r"|(?<![\wäöüß])(?:www\.|https?://)|service-?telefon|hotline|(?<![\wäöüß])(?:HRB|HRA)(?![\wäöüß])|"
    r"amtsgericht|registergericht|handelsregister|sitz der gesellschaft|(?<![\wäöüß])sitz:|vorstand|"
    r"aufsichtsrat|geschäftsführ|ust-?id")
_ANREDE_ZEILE_RE = re.compile(r"^(?:An[ ]+)?(?:Herrn?|Frau|Familie|Fam\.|Eheleute|Herrn und Frau|Frau und Herrn|"
                              r"Herr und Frau)(?![\wäöüß])")
_TRENNER_RE = re.compile(r"[ ]+[·•|][ ]+|[ ]*[·•][ ]*|,[ ]+|[ ]+[-–][ ]+|[ ]+:[ ]+")
_REGISTER_DAVOR_RE = re.compile(r"(?i)(?:HRB|HRA|GnR|VR|PR|Nr\.?|Reg\.?|Register\w*|Amtsgericht[ \w]*)[ :]*$")


# ----------------------------------------------------------------------
# Firmenkontext je Seite
# ----------------------------------------------------------------------
_SEGMENT_RE = re.compile(r"[ ]*(?:[·•|,;:\t]|[ ][-–][ ])[ ]*")


@functools.lru_cache(maxsize=8192)
def _allowlist_in(zeile: str) -> bool:
    """Ist ein Abschnitt der Zeile (zwischen "·", ",", "|" …) ganz eine Organisation der Erlaubnisliste
    ("Debeka", "HUK-COBURG Allgemeine Versicherung AG", "Allianz Lebensversicherungs-AG")? Einzelne Wörter
    zählen nur, wenn sie kein Vor- oder Nachname sind; Kürzel der Liste (ING, AO) nur in Versalien und
    nicht als Teil eines Titels ("Dipl.-Ing.")."""
    if _wissen is None or not zeile.strip():
        return False
    try:
        for teil in _SEGMENT_RE.split(zeile):
            teil = teil.strip(" .()")
            if len(teil) < 3 or not any(c.isalpha() for c in teil) or any(c.isdigit() for c in teil):
                continue
            ohne_form = _RECHTSFORM_RE.sub("", teil).strip(" .,")
            kandidat = ohne_form or teil
            if not _wissen.ist_allowlist(kandidat):
                continue
            woerter = kandidat.split()
            if len(woerter) == 1:
                w = woerter[0]
                eintrag = _wissen.index("versicherer_und_organisationen").eintrag_fuer(w) or ""
                if eintrag.isupper() and not w.isupper():
                    continue                          # "Ing" ist nicht die Bank ING
                if len(w) < 4 and not w.isupper():
                    continue
                if _wissen.ist_nachname(w) or _wissen.ist_vorname(w):
                    continue
            return True
    except Exception:
        return False
    return False


def firmen_beleg(zeile: str) -> str | None:
    """Art des Firmenbelegs einer Zeile: "rechtsform", "organisation", "allowlist" oder None."""
    if _RECHTSFORM_RE.search(zeile):
        return "rechtsform"
    if _ORGANISATION_RE.search(zeile):
        return "organisation"
    if _allowlist_in(zeile):
        return "allowlist"
    return None


def _ist_personenzeile(text: str) -> bool:
    inhalt = text.strip()
    if not inhalt or any(c.isdigit() for c in inhalt):
        return False
    sp = namen_spanne(inhalt, 0, len(inhalt))
    return bool(sp and (sp.bekannt or sp.woerter >= 2) and sp.ende - sp.start >= 0.7 * len(inhalt.rstrip(",. ")))


_REGISTER_RE = re.compile(r"(?i)(?<![\wäöüß])(?:HRB|HRA)(?![\wäöüß])|amtsgericht|registergericht|handelsregister|"
                          r"sitz der gesellschaft|(?<![\wäöüß])sitz:|vorstand|aufsichtsrat|geschäftsführ|ust-?id|"
                          r"(?<![\wäöüß])www\.|https?://|service-?telefon|bankverbindung")


def _adressartig(text: str) -> bool:
    """Kann die Zeile zu einem Anschriftenblock gehören (Name, Firma, Abteilung, Straße, c/o)? Nicht:
    Formularzeilen mit "Etikett:", nummerierte Überschriften, Sätze."""
    t = text.strip()
    if not t or len(t) > 70 or len(t.split()) > 7:
        return False
    if re.search(r"[A-Za-zÄÖÜäöüß)][ ]?:(?:[ \t]|$)", t) and not re.match(r"(?i)z\.[ ]?hd|c/o", t):
        return False
    if re.match(r"\d{1,2}\.[ ]", t):
        return False
    if t.endswith(".") and len(t.split()) > 3 and not _RECHTSFORM_RE.search(t):
        return False
    return True


class _Firmenkontext:
    """Je Zeile der Seite: gehört eine Anschrift in dieser Zeile zu einer Organisation?

    Beleg in der Zeile selbst (vor bzw. in der Anschrift), in den Zeilen des Anschriftenblocks darüber
    (gleiche Spalte, kleine Lücken, nur blockartige Zeilen – keine Formularzeilen, Überschriften, Sätze)
    oder – im Briefkopf und in der Fußzeile – Registerangaben im selben Block. Eine Anredezeile oder ein
    Personenname im Block darüber macht die Anschrift zur Personenanschrift."""

    def __init__(self, seite):
        self.seite = seite
        text = seite.text
        self.zeilen = {z.id: z for z in seite.zeilen}
        self.zeilen_text = {z.id: text[z.start:z.ende] for z in seite.zeilen}
        self.beleg = {zid: firmen_beleg(t) for zid, t in self.zeilen_text.items()}
        je_block: dict = {}
        for z in seite.zeilen:
            je_block.setdefault(z.block, []).append(z.id)
        self.block_von = {z.id: z.block for z in seite.zeilen}
        # Registerangaben zählen nur in kleinen Blöcken (Briefkopf, Fußzeilen-Spalte), nicht in einem Block,
        # der die ganze Seite umfasst (reiner Text: eine Seite = ein Block)
        self.block_register = {b: len(ids) <= 6 and any(_REGISTER_RE.search(self.zeilen_text[zid]) for zid in ids)
                               for b, ids in je_block.items()}
        self.lg = lage(seite)
        self._firma: dict = {}

    def firma(self, zid: int, bis: int | None = None) -> bool:
        """bis: Ende der Anschrift in der Zeile (Seitenoffset) – nur der Text davor zählt als Beleg."""
        schluessel = (zid, bis)
        if schluessel not in self._firma:
            self._firma[schluessel] = self._berechnen(zid, bis)
        return self._firma[schluessel]

    def _berechnen(self, zid: int, bis: int | None) -> bool:
        z = self.zeilen.get(zid)
        if z is None:
            return False
        eigen = self.zeilen_text[zid] if bis is None else self.seite.text[z.start:max(z.start, min(bis, z.ende))]
        if firmen_beleg(eigen):
            return True
        lg = self.lg
        box = lg.zeilen_box.get(zid)
        if box is None:
            return False
        # Briefkopf und Fußzeile: Registerangaben im selben Block
        hoehe = lg.hoehe_seite
        if (box[1] < 0.2 * hoehe or box[3] > 0.85 * hoehe) and self.block_register.get(self.block_von.get(zid)):
            return True
        # Anschriftenblock darüber
        h = max(lg.hoehe, 4.0)
        aktuell = zid
        for _ in range(4):
            oben = None
            for kandidat in lg.zeilen_darueber(aktuell, 2.2 * h):
                ob = lg.zeilen_box.get(kandidat)
                if ob is None or ob[2] < box[0] - h or ob[0] > box[0] + 3 * h:
                    continue
                oben = kandidat
                break
            if oben is None:
                return False
            t = self.zeilen_text.get(oben, "")
            if not _adressartig(t):
                return False
            if _ANREDE_ZEILE_RE.match(t.strip()) or re.match(r"(?i)c/o\b", t.strip()):
                return False                          # Anrede oder "c/o <Person>": Postanschrift einer Person
            if self.beleg.get(oben):
                return True
            if _ist_personenzeile(t):
                return False
            aktuell = oben
        return False


def firmenkontext(seite) -> _Firmenkontext:
    zw = getattr(seite, "_struktur_firmen", None)
    if zw is None or zw.seite.text is not seite.text:
        zw = _Firmenkontext(seite)
        try:
            seite._struktur_firmen = zw
        except AttributeError:
            pass
    return zw


def _vorschlag(dok, start: int, ende: int, kategorie: str, grund: str):
    """Nicht geschwärzte Firmenanschrift für die Oberfläche vermerken (dok.struktur_vorschlaege)."""
    try:
        liste = dok.__dict__.setdefault("struktur_vorschlaege", [])
    except AttributeError:
        return
    eintrag = {"start": start, "ende": ende, "kategorie": kategorie, "quelle": "struktur.firmenanschrift",
               "grund": grund}
    if eintrag not in liste:
        liste.append(eintrag)


# ----------------------------------------------------------------------
# Muster-Treffer prüfen: Firmenkontext und Fehlgriffe
# ----------------------------------------------------------------------
def _plz_ort_bereinigen(dok, t: Treffer):
    """Fehlgriffe des PLZ-Musters: Registernummer davor ("HRB 16963"), Etikett oder Allerweltswort als Ort
    ("17205 USt-IdNr", "16963\\nVorstand"); Ort, der in die Nachbarspalte läuft, wird gekürzt.
    Liefert den (ggf. gekürzten) Treffer oder None."""
    text = dok.text
    roh = text[t.start:t.ende]
    m = re.match(r"(?:(?:D|DE|A|AT|CH|L|FL)[-\s])?\d{4,5}", roh)
    if not m:
        return t
    davor = text[max(0, t.start - 40):t.start].rsplit("\n", 1)[-1]
    if _REGISTER_DAVOR_RE.search(davor):
        return None
    ende = plz_ort_kappen(text, t.start, t.ende)
    if ende is None:
        return None
    if ende == t.ende:
        zeile_ende = text.find("\n", ende)
        ende = ort_verlaengern(text, ende, zeile_ende if zeile_ende >= 0 else len(text))
    if ende != t.ende:
        return t._replace(ende=ende)
    return t


def firmen_filter(dok, treffer: list, kategorie: str) -> list:
    """Muster-Treffer ohne Firmenanschriften und Fehlgriffe."""
    aus = []
    for t in treffer:
        if kategorie == "plzort":
            t = _plz_ort_bereinigen(dok, t)
            if t is None:
                continue
        nr = dok.seite_von(t.start)
        seite = dok.seiten[nr]
        lokal = t.start - dok.seiten_start[nr]
        zeile = seite.zeile_von(lokal)
        if zeile is None:
            aus.append(t)
            continue
        fk = firmenkontext(seite)
        bis = min(t.ende - dok.seiten_start[nr], zeile.ende)
        if fk.firma(zeile.id, bis):
            if not _bekannte_organisation(fk, zeile.id):
                _vorschlag(dok, t.start, t.ende, t.kategorie, "vermutlich Firmenanschrift – nicht geschwärzt")
            continue
        aus.append(t)
    return aus


def _bekannte_organisation(fk: _Firmenkontext, zid: int) -> bool:
    """Organisation der Erlaubnisliste in der Zeile oder den zwei Zeilen darüber?"""
    if _allowlist_in(fk.zeilen_text.get(zid, "")):
        return True
    h = max(fk.lg.hoehe, 4.0)
    return any(_allowlist_in(fk.zeilen_text.get(o, "")) for o in fk.lg.zeilen_darueber(zid, 2.5 * h)[:2])


def _filter_detektor(alt, kategorie: str):
    def erkennen(dok, kontext):
        return firmen_filter(dok, list(alt(dok, kontext) or []), kategorie)
    erkennen.__name__ = f"muster_{kategorie}_ohne_firmen"
    erkennen.__doc__ = (f"Muster »{kategorie}« wie bisher, ohne Anschriften von Organisationen "
                        f"(Briefkopf, Fußzeile, Firmenblock) und ohne Fehlgriffe.")
    return erkennen


_BETRAG_DANACH_RE = re.compile(r"[,.]\d")


def _zeilenweise(text: str) -> str | None:
    """Text mit jeder Tabellenzelle auf eigener Zeile (Spaltentrenner -> Leerzeichen + Umbruch, längentreu)."""
    if SPALTENTRENNER not in text:
        return None
    return text.replace(SPALTENTRENNER, " " * (len(SPALTENTRENNER) - 1) + "\n")


def _stellen_detektor(kategorie: str, alt):
    """Muster »kategorie« als Stellen (muster.stellen) statt als wiedergesuchte Fundtexte: Stellen über einen
    Spaltentrenner zählen nicht (sie verschlucken Nachbarzellen), dazu die zeilenweise Lesart – wie bei den
    übrigen Mustern (detektoren/muster_spans.py). Ohne Stellen-Schnittstelle (z. B. Muster in Tests ersetzt)
    gilt der bisherige Detektor `alt`."""
    def erkennen(dok, kontext):
        funktion = next((e[3] for e in getattr(_muster, "KATEGORIEN", ()) if e[0] == kategorie), None)
        if _muster is None or not hasattr(_muster, "stellen") or kategorie not in getattr(_muster, "SPANNEN", {}) \
                or getattr(funktion, "kategorie", None) != kategorie:
            return list(alt(dok, kontext) or []) if alt is not None else []
        text = dok.text
        gesehen = {}
        for lesart in (text, _zeilenweise(text)):
            if lesart is None:
                continue
            for st in _muster.stellen(kategorie, lesart, nur_streng=True):
                if st.ende <= st.start or SPALTENTRENNER in text[st.start:st.ende]:
                    continue
                if kategorie == "strasse" and _BETRAG_DANACH_RE.match(text, st.ende):
                    continue                          # "Am Kurpark 946,21": Betrag, keine Hausnummer
                gesehen.setdefault((st.start, st.ende), st)
        return [Treffer(s, e, kategorie, f"muster.{kategorie}", st.sicherheit if st.sicherheit is not None else 0.75)
                for (s, e), st in sorted(gesehen.items())]
    return erkennen


def _rueckfall_detektor(kategorie: str):
    """Falls kein Muster-Detektor registriert ist: muster.finde_* über den Vergleicher verorten."""
    from ..seitenmodell import ganzwort_stellen

    def erkennen(dok, kontext):
        if _muster is None:
            return []
        funktion = _muster.finde_strasse if kategorie == "strasse" else _muster.finde_plz_ort
        treffer = []
        for t in dict.fromkeys(x.strip() for x in funktion(dok.text) if x and x.strip()):
            for s, e in ganzwort_stellen(dok, t, "begriff"):
                treffer.append(Treffer(s, e, kategorie, f"muster.{kategorie}", 0.75))
        return treffer
    return erkennen


def _neu_registrieren():
    for kategorie in ("strasse", "plzort"):
        name = f"muster.{kategorie}"
        alt = next((e for e in REGISTER if e.name == name), None)
        funktion = alt.funktion if alt is not None else _rueckfall_detektor(kategorie)
        if getattr(funktion, "__name__", "").endswith("_ohne_firmen"):
            continue                                  # schon umhüllt (erneuter Import)
        registrieren(name, alt.kategorien if alt else {kategorie}, alt.profile if alt else None,
                     _filter_detektor(_stellen_detektor(kategorie, funktion), kategorie), ersetzt=True)


_neu_registrieren()


# ----------------------------------------------------------------------
# Adressblöcke
# ----------------------------------------------------------------------
QUELLE_BLOCK = "struktur.adressblock"
QUELLE_FELD = "struktur.anschriftfeld"


def _zeilen_text(seite, z) -> str:
    return seite.text[z.start:z.ende]


def _segment_werte(seite, start: int, ende: int, fk: _Firmenkontext, zid: int) -> list:
    """Zeile mit Trennern ("Name · Straße 1 · 12345 Ort"): Werte der Segmente vor PLZ + Ort."""
    text = seite.text
    segmente = []
    pos = start
    for m in _TRENNER_RE.finditer(text, start, ende):
        if m.start() > pos:
            segmente.append((pos, m.start()))
        pos = m.end()
    if pos < ende:
        segmente.append((pos, ende))
    if len(segmente) < 2:
        return []
    aus = []
    for k, (s, e) in enumerate(segmente):
        plz = plz_ort_spannen(text, s, e)
        if not plz or plz[0][0] - s > 2:
            continue
        aus.append((plz[0][0], plz[0][1], "plzort", None))
        if k >= 1:
            s2, e2 = segmente[k - 1]
            st = strasse_spanne(text, s2, e2)
            if st and st[1] >= e2 - 1:
                aus.append((st[0], st[1], "strasse", None))
                if k >= 2:
                    s3, e3 = segmente[k - 2]
                    sp = namen_spanne(text, s3, e3)
                    if sp and sp.ende >= e3 - 1 and sp.start - s3 <= 25:
                        aus.append((sp.start, sp.ende, "namen", text[sp.start:sp.ende] if sp.woerter > 1 else None))
        break
    return aus


def _block_werte(seite, lg, z_plz, plz_spanne, fk: _Firmenkontext, im_fenster: bool) -> list:
    """Zeilen über einer PLZ-Zeile (gleiche Spalte, kleine Lücken): Straße, dann 1–3 Namenszeilen."""
    text = seite.text
    aus = []
    box = lg.zeilen_box.get(z_plz.id)
    if box is None:
        return aus
    h = max(lg.hoehe, 4.0)
    zeilen_nach_id = {z.id: z for z in seite.zeilen}
    oben = []
    aktuell = z_plz.id
    for _ in range(5):
        kandidat = None
        for zid in lg.zeilen_darueber(aktuell, 1.9 * h):
            ob = lg.zeilen_box.get(zid)
            if ob is None:
                continue
            if abs(ob[0] - box[0]) <= 2.0 * h:
                kandidat = zid
                break
        if kandidat is None:
            break
        oben.append(kandidat)
        aktuell = kandidat
    if not oben:
        return aus
    # Straße / Postfach
    z_str = zeilen_nach_id[oben[0]]
    zt = _zeilen_text(seite, z_str)
    if fk.firma(z_str.id, z_str.ende):
        return aus
    st = strasse_spanne(text, z_str.start, z_str.ende)
    rest = 1
    if st and st[1] >= z_str.ende - 1 and len(zt.strip()) <= 60:
        aus.append((st[0], st[1], "strasse", None))
    elif re.match(r"(?i)c/o|z\.[ ]?hd", zt.strip()):
        rest = 0
    else:
        return aus
    # Namen darüber (bis Anrede, Firmenzeile, Lücke)
    for zid in oben[rest:rest + 3]:
        z = zeilen_nach_id[zid]
        zt = _zeilen_text(seite, z).strip()
        if not zt or _ANREDE_ZEILE_RE.match(zt) and len(zt.split()) <= 3 and not namen_spanne(text, z.start, z.ende):
            break
        if firmen_beleg(zt):
            break
        m = re.match(r"(?i)(?:c/o|z\.[ ]?hd\.?|zu händen)[ ]*", zt)
        anfang = z.start + (len(_zeilen_text(seite, z)) - len(_zeilen_text(seite, z).lstrip()))
        if m:
            anfang += m.end()
        sp = namen_spanne(text, anfang, z.ende)
        if sp is None:
            if _ANREDE_ZEILE_RE.match(zt):
                break
            continue
        if sp.ende - sp.start < 0.6 * len(text[anfang:z.ende].strip()):
            break
        if not (im_fenster or sp.bekannt or sp.woerter >= 2):
            break
        aus.append((sp.start, sp.ende, "namen", text[sp.start:sp.ende] if sp.woerter > 1 else None))
        if _ANREDE_ZEILE_RE.match(zt):
            break
    return aus


def _anschriftfeld(seite, y0: float, x1: float) -> bool:
    """Liegt eine Zeile im Anschriftfeld nach DIN 5008 (Form A oder B, ±8 mm)?"""
    return 19 * MM <= y0 <= 98 * MM and x1 <= 125 * MM


@detektor(QUELLE_BLOCK, {"namen", "strasse", "plzort"})
def adressblock(dok, kontext):
    """Kundenanschriften: Block mit PLZ-Zeile am Ende, Zeilen mit Trennern; Firmenanschriften bleiben."""
    treffer = []
    for nr, seite in enumerate(dok.seiten):
        text = seite.text
        if not text.strip() or _muster is None:
            continue
        lg = lage(seite)
        fk = firmenkontext(seite)
        for z in seite.zeilen:
            zt = text[z.start:z.ende]
            if not re.search(r"\d{4,5}", zt):
                continue
            plz = plz_ort_spannen(text, z.start, z.ende)
            if not plz:
                continue
            if fk.firma(z.id, plz[0][1]):
                continue
            werte = []
            segmente = _segment_werte(seite, z.start, z.ende, fk, z.id)
            werte += segmente
            erste = plz[0]
            if erste[0] - z.start <= 3 and not segmente:
                box = lg.zeilen_box.get(z.id)
                im_fenster = bool(box) and nr == 0 and _anschriftfeld(seite, box[1], box[2])
                werte.append((erste[0], erste[1], "plzort", None))
                werte += _block_werte(seite, lg, z, erste, fk, im_fenster)
            quelle = QUELLE_BLOCK
            for a, b, kat, gruppe in werte:
                if kat not in kontext.aktive and kontext.aktive:
                    continue
                treffer.append(Treffer(dok.global_(nr, a), dok.global_(nr, b), kat, quelle, 0.75, gruppe))
    return treffer
