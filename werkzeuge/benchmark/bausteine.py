"""Bausteine für die Dokumenttypen: Personen, Stil, Seitenfluss, Briefkopf nach DIN 5008.

Ein Dokument (Klasse Dok) bündelt Zufallsquelle, Satz (PDF + Wahrheitseinträge), Stil und die
im Dokument vorkommenden Personen. Personen liefern ihre Namen in allen Schreibweisen, die in
Versicherungsunterlagen vorkommen (mit Titel, „Nachname, Vorname“, Versalien, Initiale,
transliteriert) – jeweils mit passender Bemerkung für die Wahrheitsdatei.
"""

import datetime
import re
import unicodedata
from dataclasses import dataclass, field

from . import kennungen as K
from . import stammdaten as D
from . import satz as S
from .satz import MM, A4_B, A4_H

MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
          "November", "Dezember"]
MONATE_KURZ = ["Jan.", "Feb.", "Mrz.", "Apr.", "Mai", "Jun.", "Jul.", "Aug.", "Sep.", "Okt.", "Nov.", "Dez."]


def datum_lang(d: datetime.date, mit_null: bool = False) -> str:
    return f"{d.day:02d}. {MONATE[d.month - 1]} {d.year}" if mit_null else f"{d.day}. {MONATE[d.month - 1]} {d.year}"


def datum(d: datetime.date) -> str:
    return f"{d:%d.%m.%Y}"


def ascii_name(text: str) -> str:
    """Für E-Mail-Adressen: Umlaute als ae/oe/ue, ß als ss, sonstige Diakritika entfernt."""
    ersetzt = (text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("Ä", "Ae")
               .replace("Ö", "Oe").replace("Ü", "Ue").replace("ß", "ss").replace("ı", "i").replace("ł", "l")
               .replace("Ł", "L").replace("ø", "o").replace("æ", "ae").replace("đ", "d").replace("Đ", "D"))
    zerlegt = unicodedata.normalize("NFKD", ersetzt)
    return "".join(c for c in zerlegt if not unicodedata.combining(c))


# ----------------------------------------------------------------------
# Personen
# ----------------------------------------------------------------------
@dataclass
class Person:
    geschlecht: str
    herkunft: str
    vornamen: str
    nachname: str
    titel: str
    geburtsdatum: datetime.date
    strasse: str
    hausnummer: str
    plz: str
    ort: str
    vorwahl: str
    geburtsname: str | None = None
    zusatz: str | None = None
    rolle: str = ""
    extra: dict = field(default_factory=dict)

    # -- Anreden -------------------------------------------------------
    @property
    def herr_frau(self) -> str:
        return "Herr" if self.geschlecht == "m" else "Frau"

    @property
    def herrn_frau(self) -> str:
        return "Herrn" if self.geschlecht == "m" else "Frau"

    @property
    def geehrt(self) -> str:
        return "Sehr geehrter Herr" if self.geschlecht == "m" else "Sehr geehrte Frau"

    # -- Namensformen --------------------------------------------------
    def voll(self, titel: bool = False) -> str:
        t = f"{self.titel} " if (titel and self.titel) else ""
        return f"{t}{self.vornamen} {self.nachname}"

    def anrede_name(self) -> str:
        """Was hinter 'Herr/Frau' steht: 'Dr. Groß', 'von der Heyde'."""
        return f"{self.titel} {self.nachname}" if self.titel else self.nachname

    def liste(self, partikel_hinten: bool = False) -> str:
        """'Nachname, Vorname' – bei Adelspartikeln wahlweise 'Heyde, Anna von der'."""
        mo = re.match(r"^((?:Freiherr |Freifrau )?(?:von und zu|von der|von|zu|van den|van der|van|de))\s+(.+)$",
                      self.nachname)
        if partikel_hinten and mo:
            return f"{mo.group(2)}, {self.vornamen} {mo.group(1)}"
        return f"{self.nachname}, {self.vornamen}"

    def initiale(self) -> str:
        teile = re.split(r"([- ])", self.vornamen)
        kurz = "".join(t[0] + "." if t not in ("-", " ") and t else ("-" if t == "-" else "") for t in teile)
        return f"{kurz} {self.nachname}"

    @property
    def vorname1(self) -> str:
        return re.split(r"[- ]", self.vornamen)[0]

    def email(self, rng, firma_domain: str | None = None) -> str:
        v = ascii_name(self.vorname1).lower()
        n = ascii_name(self.nachname).lower().replace(" ", "").replace("'", "")
        n = re.sub(r"[^a-z\-]", "", n)
        if firma_domain:
            muster = rng.choice([f"{v}.{n}", f"{v[0]}.{n}", f"{n}"])
            return f"{muster}@{firma_domain}"
        jahr = f"{self.geburtsdatum.year % 100:02d}"
        muster = rng.choice([f"{v}.{n}", f"{v[0]}.{n}", f"{n}.{v}{jahr}", f"{v}{n}", f"{v}_{n}",
                             f"{n}{rng.randint(1, 999)}", f"{v}.{n}{self.geburtsdatum.year}"])
        return f"{muster}@{rng.choice(D.MAILANBIETER)}"

    def strasse_hnr(self) -> str:
        return f"{self.strasse} {self.hausnummer}"

    def plz_ort(self) -> str:
        return f"{self.plz} {self.ort}"


# ----------------------------------------------------------------------
# Stil
# ----------------------------------------------------------------------
@dataclass
class Stil:
    familie: S.Familie
    groesse: float
    zeilenabstand: float
    blocksatz: bool
    trennung: bool
    akzent: tuple
    kopf_familie: S.Familie

    @property
    def normal(self):
        return self.familie.normal

    @property
    def fett(self):
        return self.familie.fett

    @property
    def zeilenhoehe(self):
        return self.groesse * self.zeilenabstand

    def merkmale(self) -> set:
        mm = {"eingebettete_schrift" if self.familie.eingebettet or self.kopf_familie.eingebettet else "base14"}
        if not self.familie.eingebettet or not self.kopf_familie.eingebettet:
            mm.add("base14")
        if self.groesse <= 8.5:
            mm.add("kleine_schrift")
        if self.zeilenabstand <= 1.1:
            mm.add("enger_zeilenabstand")
        if self.zeilenabstand >= 1.4:
            mm.add("weiter_zeilenabstand")
        if self.blocksatz:
            mm.add("blocksatz")
        return mm


FAMILIEN_GEWICHTE = [("helv", 18), ("tiro", 9), ("cour", 5), ("sans", 24), ("serif", 14), ("carlito", 16),
                     ("dejavu", 7), ("mono", 4)]


def stil_waehlen(rng, groesse=None, zeilenabstand=None, familie=None) -> Stil:
    namen = [n for n, _ in FAMILIEN_GEWICHTE]
    gewichte = [g for _, g in FAMILIEN_GEWICHTE]
    fam = familie or rng.choices(namen, gewichte)[0]
    kopf = rng.choice(["sans", "helv", "carlito", fam])
    if groesse is None:
        groesse = rng.choice([7.5, 8, 8.5, 9, 9, 9.5, 10, 10, 10, 10.5, 11, 11, 11.5, 12])
    if zeilenabstand is None:
        zeilenabstand = rng.choice([1.0, 1.05, 1.1, 1.15, 1.2, 1.2, 1.25, 1.3, 1.35, 1.4, 1.5])
    return Stil(familie=S.Familie(fam), groesse=groesse, zeilenabstand=zeilenabstand,
                blocksatz=rng.random() < 0.3, trennung=rng.random() < 0.75,
                akzent=rng.choice([(0.0, 0.22, 0.45), (0.55, 0.05, 0.1), (0.0, 0.35, 0.2), (0.2, 0.2, 0.2),
                                   (0.35, 0.1, 0.45), (0.0, 0.3, 0.55)]),
                kopf_familie=S.Familie(kopf))


# ----------------------------------------------------------------------
# Dokument-Kontext
# ----------------------------------------------------------------------
class Dok:
    """Kontext eines Dokuments: Zufall, Satz, Stil, Personen, Datum."""

    def __init__(self, rng, kennung: str, stil: Stil | None = None, querformat: bool = False):
        self.rng = rng
        self.satz = S.Satz(kennung)
        self.stil = stil or stil_waehlen(rng)
        self.format = (A4_H, A4_B) if querformat else (A4_B, A4_H)
        self.heute = datetime.date(2025, 1, 2) + datetime.timedelta(days=rng.randint(0, 300))
        self._vornamen: set = set()
        self._nachnamen: set = set()
        self._orte: set = set()
        self.kopf_fuss = []        # Funktionen (seite, nr, gesamt) für Kopf-/Fußzeilen
        self.neben: list = []      # Nebenkanal-Aufträge (vom Generator ausgeführt)
        self.titel = ""            # für Metadaten/Lesezeichen
        self.hauptperson = None

    # -- Personen ------------------------------------------------------
    def _herkunft(self) -> str:
        namen = list(D.HERKUNFT_GEWICHTE)
        return self.rng.choices(namen, [D.HERKUNFT_GEWICHTE[n] for n in namen])[0]

    def ort(self, ausser=()) -> tuple:
        for _ in range(50):
            o = self.rng.choice(D.ORTE)
            if o[1] not in self._orte and o[1] not in ausser:
                self._orte.add(o[1])
                return o
        return self.rng.choice(D.ORTE)

    def person(self, geschlecht: str | None = None, herkunft: str | None = None, alter=(22, 85),
               titel_quote: float = 0.12, nachname: str | None = None, ort=None, adel_quote: float = 0.04,
               doppel_quote: float = 0.06) -> Person:
        rng = self.rng
        geschlecht = geschlecht or rng.choice("mw")
        herkunft = herkunft or self._herkunft()
        m_liste, w_liste = D.VORNAMEN[herkunft]
        for _ in range(60):
            vor = rng.choice(m_liste if geschlecht == "m" else w_liste)
            if vor.split()[0].split("-")[0] not in self._vornamen:
                break
        if herkunft == "de" and rng.random() < 0.06 and " " not in vor and "-" not in vor:
            zweit = rng.choice(m_liste if geschlecht == "m" else w_liste)
            if zweit != vor and "-" not in zweit and " " not in zweit:
                vor = f"{vor}{rng.choice(['-', ' '])}{zweit}"
        if nachname is None:
            for _ in range(60):
                zufall = rng.random()
                if herkunft == "de" and zufall < adel_quote:
                    nachname = rng.choice(D.ADELSNAMEN)
                elif herkunft == "de" and zufall < adel_quote + doppel_quote:
                    a, b = rng.sample(D.DOPPEL_TEILE, 2)
                    nachname = f"{a}-{b}"
                else:
                    nachname = rng.choice(D.NACHNAMEN[herkunft])
                    if geschlecht == "w" and herkunft in D.WEIBLICHE_FORMEN:
                        nachname = D.WEIBLICHE_FORMEN[herkunft](nachname)
                if nachname.split()[-1] not in self._nachnamen:
                    break
        self._vornamen.add(vor.split()[0].split("-")[0])
        self._nachnamen.add(nachname.split()[-1])
        titel = rng.choice(D.TITEL) if rng.random() < titel_quote else ""
        a = rng.randint(*alter)
        geb = self.heute - datetime.timedelta(days=a * 365 + rng.randint(0, 364))
        plz, ort_name, vorwahl = ort or self.ort()
        hnr = str(rng.randint(1, 140))
        zufall = rng.random()
        if zufall < 0.18:
            hnr += rng.choice("abcd")
        elif zufall < 0.24:
            hnr += " " + rng.choice("ab")
        elif zufall < 0.28:
            hnr = f"{hnr}-{int(hnr) + 2}"
        strasse = rng.choice(D.STRASSEN)
        p = Person(geschlecht=geschlecht, herkunft=herkunft, vornamen=vor, nachname=nachname, titel=titel,
                   geburtsdatum=geb, strasse=strasse, hausnummer=hnr, plz=plz, ort=ort_name, vorwahl=vorwahl)
        if geschlecht == "w" and rng.random() < 0.25 and a > 25:
            p.geburtsname = rng.choice(D.NACHNAMEN["de"] if herkunft == "de" else D.NACHNAMEN[herkunft])
            if p.geburtsname.split()[-1] in self._nachnamen or p.geburtsname == nachname:
                p.geburtsname = None
            else:
                self._nachnamen.add(p.geburtsname.split()[-1])
        return p

    def familienmitglied(self, haupt: Person, rolle: str, alter=(1, 17)) -> Person:
        """Kind/Ehepartner mit demselben Nachnamen und derselben Anschrift."""
        geschlecht = self.rng.choice("mw") if rolle != "ehe" else ("w" if haupt.geschlecht == "m" else "m")
        p = self.person(geschlecht=geschlecht, herkunft=haupt.herkunft, alter=alter, titel_quote=0.0,
                        nachname=haupt.nachname, ort=(haupt.plz, haupt.ort, haupt.vorwahl))
        p.strasse, p.hausnummer = haupt.strasse, haupt.hausnummer
        p.rolle = rolle
        return p

    def versicherer(self, sparte: str | None = None) -> tuple:
        kandidaten = [v for v in D.VERSICHERER if sparte is None or v[5] == sparte]
        for _ in range(30):
            v = self.rng.choice(kandidaten)
            if v[3] not in self._orte:
                self._orte.add(v[3])
                return v
        return self.rng.choice(kandidaten)

    # -- Formatvarianten mit Bemerkung -----------------------------------
    def telefon(self, person: Person | None = None, mobil: bool = False, art: str | None = None) -> str:
        if person is not None and not mobil and self.rng.random() < 0.8:
            vorwahl = person.vorwahl
            nummer = str(self.rng.randint(2, 9)) + "".join(self.rng.choice("0123456789")
                                                          for _ in range(5 + (len(vorwahl) <= 3)))
        else:
            vorwahl, nummer = K.telefon(self.rng, mobil=mobil)
        art = art or self.rng.choice(K.TELEFON_FORMATE)
        return K.telefon_formatieren(vorwahl, nummer, art)

    def geburtsdatum_text(self, d: datetime.date, art: str | None = None) -> tuple:
        """(Text, Bemerkung) in einer üblichen Schreibweise."""
        art = art or self.rng.choice(["punkt", "punkt", "punkt", "kurz", "lang", "lang0", "iso", "slash",
                                      "punkt_ohne_null", "monat_kurz"])
        if art == "punkt":
            return f"{d:%d.%m.%Y}", "TT.MM.JJJJ"
        if art == "kurz":
            return f"{d:%d.%m.%y}", "TT.MM.JJ"
        if art == "lang":
            return datum_lang(d), "ausgeschriebener Monat"
        if art == "lang0":
            return datum_lang(d, True), "ausgeschriebener Monat"
        if art == "iso":
            return f"{d:%Y-%m-%d}", "ISO-Format"
        if art == "slash":
            return f"{d:%d/%m/%Y}", "TT/MM/JJJJ"
        if art == "punkt_ohne_null":
            return f"{d.day}.{d.month}.{d.year}", "T.M.JJJJ"
        return f"{d.day:02d}. {MONATE_KURZ[d.month - 1]} {d.year}", "abgekürzter Monat"

    def iban_text(self, land: str = "DE") -> str:
        roh = K.iban(self.rng, land)
        return K.iban_formatieren(roh, "kompakt" if self.rng.random() < 0.2 else "gruppen")

    def name_variante(self, p: Person, kontext: str) -> tuple:
        """(Text, Bemerkung) einer zufälligen Namensform für Fließtext/Listen."""
        r = self.rng.random()
        if r < 0.45:
            return p.voll(titel=bool(p.titel) and self.rng.random() < 0.6), "Vor- und Nachname"
        if r < 0.6:
            return p.liste(partikel_hinten=self.rng.random() < 0.5), "Nachname, Vorname"
        if r < 0.72:
            return p.voll().upper(), "Versalien"
        if r < 0.84:
            return p.initiale(), "Initiale"
        if r < 0.92:
            return p.liste().upper(), "Nachname, Vorname in Versalien"
        return p.voll(titel=True), "mit Titel"


def name_bem(p: Person, basis: str) -> str:
    """Bemerkung um Namensmerkmale ergänzen (Titel, Partikel, Doppelname, Diakritika, Herkunft)."""
    teile = [basis] if basis else []
    if p.titel:
        teile.append("Titel")
    if re.search(r"\b(von|zu|van|de|der|den)\b", p.nachname):
        teile.append("Adelspartikel/Namenszusatz")
    if "-" in p.nachname:
        teile.append("Doppelname")
    if "-" in p.vornamen or " " in p.vornamen:
        teile.append("zwei Vornamen")
    if any(ord(c) > 255 for c in p.vornamen + p.nachname):
        teile.append("Diakritika")
    if p.herkunft != "de":
        teile.append(f"Herkunft {p.herkunft}")
    return "; ".join(teile)


# ----------------------------------------------------------------------
# Seitenfluss
# ----------------------------------------------------------------------
class Fluss:
    """Setzt Inhalte fortlaufend untereinander und beginnt bei Bedarf eine neue Seite."""

    def __init__(self, dok: Dok, x0: float, x1: float, y_oben: float, y_unten: float, folgeseite=None,
                 seite=None, y_start: float | None = None):
        self.dok = dok
        self.x0, self.x1 = x0, x1
        self.y_oben, self.y_unten = y_oben, y_unten
        self.folgeseite = folgeseite          # Funktion(seite) -> y_oben für Folgeseiten
        self.seite = seite
        self.y = y_start
        if self.seite is None:
            self.neue_seite()

    def neue_seite(self):
        self.seite = self.dok.satz.neue_seite(*self.dok.format)
        oben = self.y_oben
        if self.folgeseite is not None and len(self.dok.satz.seiten) > 1:
            oben = self.folgeseite(self.seite) or oben
        self.y = oben + self.dok.stil.groesse

    def platz(self, hoehe: float):
        if self.y + hoehe > self.y_unten:
            self.neue_seite()

    def luecke(self, pt: float):
        self.y += pt

    def absatz(self, markup: str, groesse=None, schrift=None, abstand=None, x0=None, x1=None,
               blocksatz=None, trennung=None, farbe=(0, 0, 0), zusatz="", zeilenabstand=None):
        st = self.dok.stil
        g = groesse or st.groesse
        s = schrift or st.normal
        zl = zeilenabstand or st.zeilenabstand
        x0 = self.x0 if x0 is None else x0
        x1 = self.x1 if x1 is None else x1
        tr = st.trennung if trennung is None else trennung
        hoehe = self.seite.absatz_hoehe(markup, x0, x1, s, g, zl, tr)
        self.platz(hoehe)
        self.y = self.seite.absatz(markup, x0, x1, self.y, s, g, zl, st.blocksatz if blocksatz is None else blocksatz,
                                   tr, farbe, zusatz)
        self.y += g * 0.6 if abstand is None else abstand

    def zeile(self, markup: str, groesse=None, schrift=None, x=None, abstand=None, farbe=(0, 0, 0),
              ausrichtung="links", zusatz=""):
        st = self.dok.stil
        g = groesse or st.groesse
        self.platz(g * st.zeilenabstand)
        self.seite.text(self.x0 if x is None else x, self.y, markup, schrift or st.normal, g, farbe,
                        ausrichtung=ausrichtung, zusatz=zusatz)
        self.y += g * st.zeilenabstand if abstand is None else abstand

    def kv(self, schluessel: str, wert: str, tab: float | None = None, fuell: str | None = None,
           groesse=None, fett_schluessel=False, zusatz=""):
        st = self.dok.stil
        g = groesse or st.groesse
        self.platz(g * st.zeilenabstand)
        tab_x = self.x0 + (tab if tab is not None else 55 * MM)
        self.seite.kv(self.x0, self.y, schluessel, wert, tab_x, st.normal, g,
                      fett=st.fett if fett_schluessel else None, fuellzeichen=fuell, zusatz=zusatz)
        self.y += g * st.zeilenabstand

    def ueberschrift(self, markup: str, groesse=None, abstand=None):
        st = self.dok.stil
        g = groesse or st.groesse + 2
        self.platz(g * 2.5)
        self.seite.text(self.x0, self.y + g * 0.3, markup, st.fett, g, farbe=st.akzent)
        self.y += g * 1.6 if abstand is None else abstand

    def tabelle(self, spalten, zeilen, groesse=None, gitter=True, zebra=False, kopf_wiederholen=True,
                zusatz_je_spalte=None, zeilenabstand=1.15):
        st = self.dok.stil
        g = groesse or st.groesse
        rest = list(zeilen)
        erste = True
        while True:
            self.platz(g * 4)
            y_oben = self.y - g
            y, n = self.seite.tabelle(self.x0, y_oben, spalten, rest, st.normal, st.fett, g, self.y_unten,
                                      zeilenabstand=zeilenabstand, gitter=gitter, zebra=zebra,
                                      kopf=erste or kopf_wiederholen, zusatz_je_spalte=zusatz_je_spalte)
            rest = rest[n:]
            self.y = y + g * 1.9
            if not rest:
                break
            if n == 0 and not erste:
                raise RuntimeError("Tabellenzeile passt auf keine Seite")
            erste = False
            self.neue_seite()
        self.dok.satz.merkmale.add("tabelle")


# ----------------------------------------------------------------------
# Briefkopf, Anschriftfeld, Informationsblock, Fußzeile (DIN 5008)
# ----------------------------------------------------------------------
def logo(seite, x, y, farbe, rng):
    """Kleines Vektor-Logo (kein Text)."""
    if seite.satz.messmodus:
        return
    form = seite.page.new_shape()
    art = rng.randint(0, 2)
    if art == 0:
        form.draw_circle((x + 12, y + 12), 11)
        form.finish(color=farbe, fill=farbe)
        form.draw_circle((x + 12, y + 12), 5)
        form.finish(color=(1, 1, 1), fill=(1, 1, 1))
    elif art == 1:
        form.draw_polyline([(x, y + 24), (x + 12, y), (x + 24, y + 24), (x, y + 24)])
        form.finish(color=farbe, fill=farbe, closePath=True)
    else:
        form.draw_rect((x, y, x + 24, y + 24))
        form.finish(color=farbe, fill=farbe)
        form.draw_line((x + 4, y + 20), (x + 20, y + 4))
        form.finish(color=(1, 1, 1), width=2.5)
    form.commit()


def faltmarken(seite, form_b: bool):
    marken = [105 * MM, 210 * MM] if form_b else [87 * MM, 192 * MM]
    for y in marken:
        seite.linie(3 * MM, y, 8 * MM, y, 0.4, (0.4, 0.4, 0.4))
    seite.linie(3 * MM, 148.5 * MM, 10 * MM, 148.5 * MM, 0.4, (0.4, 0.4, 0.4))


def anschriftfeld(dok: Dok, seite, form_b: bool, zeilen: list, ruecksende: str | None, groesse=None):
    """Anschriftfeld nach DIN 5008 (Form A: ab 27 mm, Form B: ab 45 mm; Zusatz- und Vermerkzone
    17,7 mm, Anschriftzone 27,3 mm). zeilen: Auszeichnungen der Anschriftzeilen."""
    st = dok.stil
    g = groesse or min(11.0, max(9.0, st.groesse))
    oben = (45 if form_b else 27) * MM
    x = 25 * MM
    if ruecksende:
        seite.text(x, oben + 4.2 * MM, ruecksende, st.normal, 6.5)
        seite.linie(x, oben + 5.2 * MM, x + 80 * MM, oben + 5.2 * MM, 0.3)
    y = oben + 17.7 * MM + g
    for z in zeilen:
        seite.text(x, y, z, st.normal, g, zusatz="Adressfeld")
        y += g * 1.15
    return y


def infoblock(dok: Dok, seite, form_b: bool, eintraege: list, groesse=None):
    """Informationsblock rechts (ab 125 mm): [(Bezeichnung, Wert-Auszeichnung)]."""
    st = dok.stil
    g = groesse or max(7.0, min(9.0, st.groesse - 1))
    x = 125 * MM
    y = (50 if form_b else 32) * MM + g
    for bez, wert in eintraege:
        if bez:
            seite.text(x, y, bez, st.normal, g * 0.85, farbe=(0.3, 0.3, 0.3))
            y += g * 1.05
        seite.text(x, y, wert, st.normal, g, zusatz="Informationsblock")
        y += g * 1.35
    return y


def unternehmens_fusszeile(dok: Dok, seite, versicherer: tuple, vorstand: list, aufsichtsrat,
                           hrb: str, ust: str, bank: str):
    """Fußzeile mit Pflichtangaben; Vorstands-/Aufsichtsratsnamen sind Personennamen."""
    st = dok.stil
    g = 6.0
    y = seite.hoehe - 18 * MM
    seite.linie(25 * MM, y - 2 * g, seite.breite - 20 * MM, y - 2 * g, 0.3, (0.5, 0.5, 0.5))
    name, _, plz, ort, strasse, _ = versicherer
    spalte = (seite.breite - 45 * MM) / 3
    x1, x2, x3 = 25 * MM, 25 * MM + spalte, 25 * MM + 2 * spalte
    seite.text(x1, y, name, st.normal, g)
    seite.text(x1, y + g * 1.2, f"{strasse} · {plz} {ort}", st.normal, g)
    seite.text(x1, y + g * 2.4, f"Sitz: {ort} · {hrb}", st.normal, g)
    vors = ", ".join(vorstand)
    seite.absatz("Vorstand: " + vors, x2, x2 + spalte - 4, y, st.normal, g, 1.2, trennung=False,
                 zusatz="Fußzeile")
    if aufsichtsrat:
        seite.text(x3, y, "Vorsitz Aufsichtsrat:", st.normal, g)
        seite.text(x3, y + g * 1.2, aufsichtsrat, st.normal, g, zusatz="Fußzeile")
    seite.text(x3, y + g * 2.4, f"USt-IdNr. {ust}", st.normal, g)
    seite.text(x3, y + g * 3.6, bank, st.normal, g)
