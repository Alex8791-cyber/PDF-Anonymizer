"""Die Dokumenttypen des Entwicklungskorpus.

Jede Funktion typ_<name>(dok) setzt ein Dokument in dok.satz und liefert den Schema-Typ
("brief", "police", …). Personenbezogene Werte stehen IMMER in einer Auszeichnung
(m(kategorie, text, bemerkung)), Kontext, der erhalten bleiben soll, in k(text).
Unternehmensangaben (Anschrift/Telefon/Bankverbindung des Versicherers) bleiben unausgezeichnet:
Sie sind weder personenbezogen noch für das Verständnis nötig – ihre Schwärzung zählt nur als
Fehlalarm, nicht als Über-Schwärzung.
"""

import datetime

try:
    import pymupdf as fitz
except ImportError:  # ältere PyMuPDF-Versionen
    import fitz

from . import kennungen as K
from . import stammdaten as D
from . import scan as SC
from .bausteine import (Dok, Fluss, Person, anschriftfeld, datum, datum_lang, faltmarken,
                        infoblock, logo, name_bem, unternehmens_fusszeile)
from .satz import MM, A4_B, A4_H, Satz, k, m


# ----------------------------------------------------------------------
# Gemeinsame Hilfen
# ----------------------------------------------------------------------
def _betrag(rng, lo, hi) -> str:
    wert = rng.uniform(lo, hi)
    ganz, rest = divmod(round(wert * 100), 100)
    return f"{ganz:,}".replace(",", ".") + f",{rest:02d}"


def _eur(rng, lo, hi) -> str:
    form = rng.choice(["{} EUR", "{} €", "€ {}", "{} Euro"])
    return form.format(_betrag(rng, lo, hi))


def _adresszeilen(dok: Dok, p: Person, versalien: bool = False, postfach: bool = False,
                  co: Person | None = None, zusatz: bool = False) -> list:
    """Anschriftzeilen (Auszeichnungen) für das Anschriftfeld."""
    rng = dok.rng
    anrede = p.herrn_frau
    name = p.voll(titel=True)
    bem = name_bem(p, "Adressfeld")
    zeilen = []
    if versalien:
        zeilen.append(anrede.upper())
        zeilen.append(m("namen", name.upper(), bem + "; Versalien"))
    else:
        if rng.random() < 0.25:
            zeilen.append(f"{anrede} " + m("namen", name, bem))
        else:
            zeilen.append(anrede)
            zeilen.append(m("namen", name, bem))
    if co is not None:
        zeilen.append("c/o " + m("namen", f"Familie {co.nachname}", "c/o-Zeile"))
    if zusatz:
        zeilen.append(m("sonstiges", rng.choice(D.ADRESSZUSAETZE), "Adresszusatz"))
    if postfach:
        zeilen.append(m("postfach", rng.choice(D.POSTFAECHER), "Postfach im Adressfeld"))
    else:
        s = p.strasse_hnr()
        zeilen.append(m("strasse", s.upper() if versalien else s, "Adressfeld"))
    po = p.plz_ort()
    if rng.random() < 0.08 and not versalien:
        po = "D-" + po
    zeilen.append(m("plzort", po.upper() if versalien else po, "Adressfeld"))
    return zeilen


def _firmenanschrift(v: tuple) -> list:
    name, _, plz, ort, strasse, _ = v
    return [name, strasse, f"{plz} {ort}"]


def _gruss(fl: Fluss, dok: Dok, firma: str | None, person: Person | None, rolle: str | None,
           unterschrift: bool = True, ia: bool = True, gruss: str = "Mit freundlichen Grüßen"):
    """Grußformel + Firma + (i. A.) Name + Funktion; Name als Eintrag."""
    st = dok.stil
    fl.platz(st.zeilenhoehe * 7)
    fl.zeile(gruss)
    if firma:
        fl.zeile(firma)
    if unterschrift:
        fl.seite.unterschrift(fl.x0 + 5, fl.y + 8, dok.rng)
        dok.satz.merkmale.add("unterschrift_grafik")
    fl.luecke(st.zeilenhoehe * 1.6)
    if person is not None:
        r = dok.rng.random()
        if r < 0.55:
            text, bem = person.voll(titel=True), "Unterschriftsblock"
        elif r < 0.8:
            text, bem = person.initiale(), "Unterschriftsblock; Initiale"
        else:
            text, bem = person.voll(), "Unterschriftsblock"
        praefix = "i. A. " if (ia and firma and dok.rng.random() < 0.6) else ""
        fl.zeile(praefix + m("namen", text, name_bem(person, bem)))
    if rolle:
        fl.zeile(rolle, groesse=st.groesse * 0.9)


def _vorstand(dok: Dok, n: int = 3) -> tuple:
    """Vorstands- und Aufsichtsratsnamen (Personennamen in der Fußzeile)."""
    namen = []
    for i in range(n):
        p = dok.person(titel_quote=0.4)
        zusatz = " (Vorsitzender)" if i == 0 and p.geschlecht == "m" else (" (Vorsitzende)" if i == 0 else "")
        namen.append(m("namen", p.voll(titel=True), name_bem(p, "Fußzeile Vorstand")) + zusatz)
    ar = dok.person(titel_quote=0.5)
    return namen, m("namen", ar.voll(titel=True), name_bem(ar, "Fußzeile Aufsichtsrat"))


def _fusszeile_registrieren(dok: Dok, v: tuple):
    vorstand, ar = _vorstand(dok, dok.rng.randint(2, 4))
    hrb = f"Amtsgericht {v[3].split()[0]} HRB {dok.rng.randint(1000, 99999)}"
    ust = K.ust_idnr(dok.rng)
    bank = f"Bankverbindung: {dok.rng.choice(D.BANKEN)}"

    def fuss(seite, nr, gesamt):
        unternehmens_fusszeile(dok, seite, v, vorstand, ar, hrb, ust, bank)
    dok.kopf_fuss.append(fuss)


def _seitenzahl_registrieren(dok: Dok, kopf_markup_fn=None, unten: bool = True, ab_seite: int = 1):
    """'Seite x von y' und optional eine Kopfzeile mit Kennungen auf jeder Seite."""
    st = dok.stil

    def kf(seite, nr, gesamt):
        if nr < ab_seite:
            return
        breite, hoehe = seite.breite, seite.hoehe
        if kopf_markup_fn is not None:
            seite.text(25 * MM, 12 * MM, kopf_markup_fn(nr, gesamt), st.normal, 7.5, farbe=(0.25, 0.25, 0.25),
                       zusatz="Kopfzeile")
            dok.satz.merkmale.add("kopfzeile_kennung")
        if unten and gesamt > 1:
            seite.text(breite - 20 * MM, hoehe - 8 * MM, f"Seite {nr} von {gesamt}", st.normal, 7,
                       ausrichtung="rechts")
    dok.kopf_fuss.append(kf)


def _briefkopf_versicherer(dok: Dok, seite, v: tuple, form_b: bool):
    st = dok.stil
    kopf = st.kopf_familie
    logo(seite, A4_B - 40 * MM, 10 * MM, st.akzent, dok.rng)
    seite.text(25 * MM, 17 * MM, k(v[0]), kopf.fett, 14 if form_b else 13, farbe=st.akzent)
    if form_b:
        seite.text(25 * MM, 24 * MM, f"{v[4]} · {v[2]} {v[3]}", kopf.normal, 8, farbe=(0.3, 0.3, 0.3))
        seite.text(25 * MM, 28 * MM, "Service-Telefon 0800 " + str(dok.rng.randint(100, 999)) + " "
                   + str(dok.rng.randint(1000, 9999)) + " · www." + v[1].lower().replace(" ", "-") + "-versicherung.de",
                   kopf.normal, 8, farbe=(0.3, 0.3, 0.3))


def _versicherer_brief(dok: Dok, form_b: bool, empfaenger: Person, v: tuple, info: list, betreff: str,
                       anschrift=None, folgekopf=None):
    """Erste Seite eines Versichererbriefs bis einschließlich Betreff. Liefert den Fluss."""
    seite = dok.satz.neue_seite()
    faltmarken(seite, form_b)
    _briefkopf_versicherer(dok, seite, v, form_b)
    ruecksende = f"{v[0]} · {v[4]} · {v[2]} {v[3]}"
    zeilen = anschrift if anschrift is not None else _adresszeilen(
        dok, empfaenger, versalien=dok.rng.random() < 0.15, zusatz=dok.rng.random() < 0.08,
        postfach=dok.rng.random() < 0.15)
    anschriftfeld(dok, seite, form_b, zeilen, ruecksende)
    infoblock(dok, seite, form_b, info)
    y_betreff = (103.4 if form_b else 98.4) * MM
    st = dok.stil
    dok.satz.merkmale.add("din5008_form_b" if form_b else "din5008_form_a")
    fl = Fluss(dok, 25 * MM, A4_B - 20 * MM, 25 * MM, A4_H - 32 * MM, folgeseite=folgekopf, seite=seite,
               y_start=y_betreff)
    fl.absatz(betreff, schrift=st.fett, groesse=st.groesse + 0.5, abstand=st.zeilenhoehe * 1.2)
    return fl


def _folgekopf_fn(dok: Dok, kopfzeile: str):
    def folge(seite):
        seite.text(25 * MM, 15 * MM, kopfzeile, dok.stil.normal, 8, farbe=(0.3, 0.3, 0.3), zusatz="Folgeseitenkopf")
        return 25 * MM
    return folge


def _anrede(p: Person, dok: Dok) -> str:
    r = dok.rng.random()
    if r < 0.8:
        return f"{p.geehrt} " + m("namen", p.anrede_name(), name_bem(p, "Anrede")) + ","
    if r < 0.9:
        return f"Guten Tag {p.herr_frau} " + m("namen", p.anrede_name(), name_bem(p, "Anrede")) + ","
    return f"Guten Tag " + m("namen", p.voll(), name_bem(p, "Anrede mit Vor- und Nachname")) + ","


def _sachbearbeiter(dok: Dok, v: tuple) -> tuple:
    """Sachbearbeiter mit Durchwahl und dienstlicher E-Mail (Namen in der Adresse!)."""
    p = dok.person(titel_quote=0.05)
    domain = v[1].lower().replace(" ", "-").replace("ü", "ue").replace("ä", "ae").replace("ö", "oe") + "-versicherung.de"
    mail = p.email(dok.rng, firma_domain=domain)
    vorwahl, nummer = K.telefon(dok.rng)
    durchwahl = f"0{vorwahl} {nummer[:-3]}-{nummer[-3:]}"
    return p, mail, durchwahl


# ----------------------------------------------------------------------
# 1/2) Brief nach DIN 5008 Form A oder B
# ----------------------------------------------------------------------
def typ_brief(dok: Dok, form_b: bool = False) -> str:
    rng = dok.rng
    st = dok.stil
    anlass = rng.choice(["ablauf", "beitragsanpassung", "regulierung", "adressaenderung", "nachweis",
                         "jahresgespraech"])
    if anlass == "jahresgespraech":
        return _maklerbrief(dok, form_b)
    sparte = {"ablauf": "leben", "beitragsanpassung": "kranken", "regulierung": "sach",
              "adressaenderung": None, "nachweis": "leben"}[anlass]
    v = dok.versicherer(sparte)
    kunde = dok.person(alter=(28, 82))
    dok.hauptperson = kunde
    sb, sb_mail, sb_tel = _sachbearbeiter(dok, v)
    vnr = K.vertragsnummer(rng, {"leben": "LV", "kranken": "KV", "sach": "HR"}.get(sparte or "sach", "VS"))
    knr = K.kundennummer(rng)
    info = [("Ihr Zeichen", rng.choice(["–", "Ihr Schreiben vom " + datum(dok.heute - datetime.timedelta(days=12))])),
            ("Unser Zeichen", f"{rng.choice('ABCDEFGHKLMNPRS')}{rng.choice('ABCDEFGHKLMNPRS')}/"
                              f"{rng.choice('abcdefghkl')}{rng.choice('abcdefghkl')}"),
            ("Kundennummer", m("vertrag", knr, "Informationsblock Kundennummer")),
            ("Ansprechpartner" if sb.geschlecht == "m" else "Ansprechpartnerin",
             m("namen", sb.voll(), name_bem(sb, "Sachbearbeitung"))),
            ("Telefon", m("telefon", sb_tel, "Durchwahl Sachbearbeitung")),
            ("E-Mail", m("email", sb_mail, "dienstliche E-Mail mit Namen")),
            ("Datum", datum(dok.heute))]
    betreff_vertrag = m("vertrag", vnr, "Betreffzeile")
    betreffe = {
        "ablauf": f"Ihre Lebensversicherung Nr. {betreff_vertrag} – Ablauf zum " + k(datum(dok.heute + datetime.timedelta(days=60))),
        "beitragsanpassung": f"Beitragsanpassung Ihrer Krankenversicherung, Versicherungsnummer {betreff_vertrag}",
        "regulierung": f"Ihr Schaden vom {datum(dok.heute - datetime.timedelta(days=40))}, Schaden-Nr. "
                       + m("vertrag", K.schadennummer(rng, 'HR'), "Betreffzeile Schadennummer"),
        "adressaenderung": f"Änderung Ihrer Anschrift – Vertrag {betreff_vertrag}",
        "nachweis": f"Auszahlung aus Ihrem Vertrag {betreff_vertrag} – fehlende Angaben",
    }
    kopfzeile = f"{v[0]} · Kundennummer " + m("vertrag", knr, "Folgeseitenkopf")
    fl = _versicherer_brief(dok, form_b, kunde, v, info, betreffe[anlass], folgekopf=_folgekopf_fn(dok, kopfzeile))
    fl.absatz(_anrede(kunde, dok), abstand=st.zeilenhoehe * 0.6)
    if anlass == "ablauf":
        ehe = dok.familienmitglied(kunde, "ehe", alter=(30, 85))
        geb, gbem = dok.geburtsdatum_text(ehe.geburtsdatum)
        produkt = rng.choice(D.PRODUKTE["leben"])
        fl.absatz(f"Ihre Lebensversicherung im Tarif {k(produkt)} läuft am "
                  + k(datum(dok.heute + datetime.timedelta(days=60))) + " planmäßig ab. Die Ablaufleistung beträgt "
                  f"voraussichtlich {k(_eur(rng, 8000, 90000))} einschließlich der Überschussbeteiligung "
                  f"nach {k('§ 153 VVG')}. Die endgültige Höhe teilen wir Ihnen mit der Abrechnung mit.")
        fl.absatz("Bezugsberechtigt für den Todesfall ist laut Vertrag Ihr Ehepartner "
                  + m("namen", ehe.voll(), name_bem(ehe, "Fließtext; Bezugsrecht ~trennen"))
                  + ", geboren am " + m("geburt", geb, f"Fließtext; {gbem}") + ". Für den Erlebensfall sind Sie "
                  "selbst bezugsberechtigt.")
        fl.absatz("Wir überweisen den Betrag auf Ihr bei uns hinterlegtes Konto IBAN "
                  + m("iban", dok.iban_text(), "Fließtext") + " (BIC " + m("bic", K.bic(rng), "Fließtext")
                  + "), sofern Sie uns bis zum " + k(datum(dok.heute + datetime.timedelta(days=30)))
                  + " nichts anderes mitteilen. Für die Meldung an das Finanzamt benötigen wir Ihre "
                  "Steuer-Identifikationsnummer; bei uns ist die " + m("steuerid", K.steuer_id_formatieren(
                      K.steuer_id(rng), rng.choice(["gruppen", "kompakt"])), "Fließtext ohne Etikett")
                  + " gespeichert.")
    elif anlass == "beitragsanpassung":
        kind = dok.familienmitglied(kunde, "kind", alter=(2, 17))
        tarif1, tarif2 = rng.sample(D.PRODUKTE["kranken"], 2)
        fl.absatz("nach " + k("§ 203 Abs. 2 VVG") + " sind wir verpflichtet, die Beiträge zu überprüfen. Für "
                  "die versicherten Personen Ihres Vertrags ergeben sich zum " + k("01.01.2026")
                  + " folgende Änderungen:")
        geb1, b1 = dok.geburtsdatum_text(kunde.geburtsdatum, "punkt")
        geb2, b2 = dok.geburtsdatum_text(kind.geburtsdatum, "punkt")
        fl.tabelle([("Versicherte Person", 62 * MM, "links"), ("Geburtsdatum", 26 * MM, "links"),
                    ("Tarif", 38 * MM, "links"), ("bisher", 20 * MM, "rechts"), ("neu", 20 * MM, "rechts")],
                   [[m("namen", kunde.voll(), name_bem(kunde, "Tabelle")), m("geburt", geb1, "Tabellenspalte Geburtsdatum"),
                     k(tarif1), k(_betrag(rng, 200, 700)), k(_betrag(rng, 200, 750))],
                    [m("namen", kind.voll(), name_bem(kind, "Tabelle; Kind")), m("geburt", geb2, "Tabellenspalte Geburtsdatum; Kind"),
                     k(tarif2), k(_betrag(rng, 50, 200)), k(_betrag(rng, 50, 220))]],
                   groesse=max(7.5, st.groesse - 1))
        fl.absatz("Die Gründe für die Anpassung erläutern wir in der Anlage. Sie können innerhalb von zwei "
                  "Monaten in einen gleichartigen Tarif mit geringerem Beitrag wechseln (" + k("§ 204 VVG") + ").")
    elif anlass == "regulierung":
        gutachter = dok.person(titel_quote=0.0)
        fl.absatz("wir haben Ihren Wasserschaden in der Wohnung " + m("strasse", kunde.strasse_hnr(), "Fließtext; Schadenort")
                  + " geprüft. Der Gutachter " + m("namen", "Dipl.-Ing. " + gutachter.voll(), name_bem(gutachter, "Fließtext; Gutachter"))
                  + " hat den Schaden am " + k(datum(dok.heute - datetime.timedelta(days=20))) + " besichtigt.")
        fl.absatz(f"Wir erstatten {k(_eur(rng, 800, 12000))} abzüglich der vereinbarten Selbstbeteiligung von "
                  f"{k(_eur(rng, 150, 500))}. Der Betrag wird in den nächsten Tagen auf das Konto "
                  + m("iban", dok.iban_text(), "Fließtext") + " überwiesen. Kontoinhaberin laut Ihren Angaben: "
                  + m("namen", kunde.liste(), name_bem(kunde, "Nachname, Vorname; Kontoinhaber")) + ".")
        nachbar = dok.person()
        fl.absatz("Den Schaden in der darunterliegenden Wohnung Ihrer Nachbarin "
                  + m("namen", f"{nachbar.herr_frau} {nachbar.voll()}", name_bem(nachbar, "Fließtext mit Anrede"))
                  + " regulieren wir über Ihre Privathaftpflicht. Ihre Nachbarin erreichen wir unter "
                  + m("telefon", dok.telefon(nachbar), "Fließtext") + ".")
    elif anlass == "adressaenderung":
        neu = dok.person(alter=(30, 60))
        fl.absatz("vielen Dank für Ihre Mitteilung. Wir haben Ihre neue Anschrift ab dem "
                  + k(datum(dok.heute - datetime.timedelta(days=10))) + " gespeichert:")
        fl.absatz(m("strasse", neu.strasse_hnr(), "neue Anschrift, eingerückt") + "\n"
                  + m("plzort", neu.plz_ort(), "neue Anschrift, eingerückt"), x0=fl.x0 + 15 * MM)
        alt = dok.person()
        fl.absatz("Ihre bisherige Anschrift " + m("strasse", alt.strasse_hnr(), "Fließtext; alte Anschrift") + ", "
                  + m("plzort", alt.plz_ort(), "Fließtext; alte Anschrift")
                  + " haben wir gelöscht. Bitte prüfen Sie, ob auch Ihre Telefonnummer "
                  + m("telefon", dok.telefon(kunde, mobil=True), "Fließtext; Mobilnummer") + " noch aktuell ist.")
    else:  # nachweis
        fl.absatz("für die Auszahlung aus Ihrem Vertrag fehlen uns noch Angaben. Bitte bestätigen Sie uns Ihre "
                  "Identität mit einer Kopie Ihres Personalausweises. Die von Ihnen genannte Ausweisnummer "
                  + m("ausweis", K.personalausweisnummer(rng, rng.random() < 0.4), "Fließtext ohne Etikett")
                  + " stimmt nicht mit unseren Unterlagen überein.")
        fl.absatz("Außerdem benötigen wir Ihre Sozialversicherungsnummer (Rentenversicherungsnummer). Bisher ist "
                  "bei uns die Nummer " + m("svnr", K.sv_formatieren(K.sv_nummer(rng, kunde.geburtsdatum,
                                                                                 kunde.geburtsname or kunde.nachname,
                                                                                 kunde.geschlecht), "gruppen"), "Fließtext")
                  + " hinterlegt. Bitte prüfen Sie diese anhand Ihres Sozialversicherungsausweises.")
        if rng.random() < 0.5:
            kind = dok.familienmitglied(kunde, "kind", (1, 17))
            fl.absatz("Für die Kinderzulage zu Ihrem Riester-Vertrag benötigen wir die Kindergeldnummer Ihres Kindes "
                      + m("namen", kind.vornamen, "Fließtext nur Vorname") + ". In Ihrem Antrag ist die Nummer "
                      + m("kindergeld", K.kindergeldnummer(rng), "Fließtext ohne Etikett direkt davor")
                      + " angegeben; die Familienkasse kennt diese Nummer nicht.")
        if rng.random() < 0.6:
            fl.absatz("Da Sie selbstständig tätig sind, geben Sie bitte auch Ihre Steuernummer an. Ihr Finanzamt "
                      "führt Sie unter der Steuernummer " + m("steuernr", K.steuernummer(rng), "Fließtext mit Etikett")
                      + "; die Umsatzsteuer-Identifikationsnummer lautet " + m("steuernr", K.ust_idnr(rng), "USt-IdNr. im Fließtext") + ".")
    fl.absatz("Haben Sie Fragen? " + m("namen", sb.voll(), name_bem(sb, "Fließtext; Sachbearbeitung"))
              + " erreichen Sie montags bis freitags von 8 bis 18 Uhr.")
    _gruss(fl, dok, v[0], sb, rng.choice(["Kundenservice", "Leistungsabteilung", "Vertragsservice Leben",
                                          "Schadenservice"]))
    if rng.random() < 0.35:
        _anlage_vertragsuebersicht(dok, fl, kunde, kopfzeile)
    _fusszeile_registrieren(dok, v)
    _seitenzahl_registrieren(dok)
    dok.titel = {"ablauf": "Ablaufmitteilung", "beitragsanpassung": "Beitragsanpassung", "regulierung": "Schadenregulierung",
                 "adressaenderung": "Adressänderung", "nachweis": "Nachforderung"}[anlass]
    return "brief"


def _anlage_vertragsuebersicht(dok: Dok, fl: Fluss, kunde: Person, kopfzeile: str):
    """Anlage auf einer Folgeseite: Übersicht der Verträge und mitversicherten Personen."""
    rng = dok.rng
    fl.neue_seite()
    fl.ueberschrift(k("Anlage: Ihre Verträge im Überblick"))
    zeilen = []
    for _ in range(rng.randint(3, 6)):
        sparte = rng.choice(["leben", "kranken", "sach", "kfz", "recht"])
        zeilen.append([m("vertrag", K.vertragsnummer(rng, rng.choice(["LV", "KV", "HR", "KF"])), "Anlage-Tabelle ohne Etikett"),
                       k(rng.choice(D.PRODUKTE[sparte])), k(_betrag(rng, 8, 300)),
                       k(datum(datetime.date(rng.randint(2010, 2024), rng.randint(1, 12), 1)))])
    fl.tabelle([("Vertrag", 40 * MM, "links"), ("Tarif", 60 * MM, "links"), ("Beitrag EUR", 25 * MM, "rechts"),
                ("Beginn", 25 * MM, "links")], zeilen, groesse=max(7, dok.stil.groesse - 1))
    partner = dok.familienmitglied(kunde, "ehe", (25, 80))
    geb, gbem = dok.geburtsdatum_text(partner.geburtsdatum)
    fl.absatz("Mitversicherte Person: " + m("namen", partner.voll(), name_bem(partner, "Anlage")) + " (geb. "
              + m("geburt", geb, gbem) + "), Anschrift wie Versicherungsnehmer. Beitragszahler ist "
              + m("namen", f"{kunde.herr_frau} {kunde.nachname}", name_bem(kunde, "Anlage mit Anrede")) + ".")


def _maklerbrief(dok: Dok, form_b: bool) -> str:
    """Brief eines Maklerbüros (Name des Maklers im Briefkopf) an eine Kundin/einen Kunden."""
    rng = dok.rng
    st = dok.stil
    makler = dok.person(titel_quote=0.05, alter=(35, 65))
    kunde = dok.person(alter=(25, 75))
    dok.hauptperson = kunde
    seite = dok.satz.neue_seite()
    faltmarken(seite, form_b)
    kopf = st.kopf_familie
    firma = f"Versicherungsmakler {makler.voll()} e.K."
    seite.text(25 * MM, 17 * MM, "Versicherungsmakler " + m("namen", makler.voll(), name_bem(makler, "Briefkopf Firmenname"))
               + " e.K.", kopf.fett, 13, farbe=st.akzent)
    seite.text(25 * MM, 23 * MM, m("strasse", makler.strasse_hnr(), "Briefkopf Makler") + " · "
               + m("plzort", makler.plz_ort(), "Briefkopf Makler") + " · Tel. "
               + m("telefon", dok.telefon(makler, art="din"), "Briefkopf Makler"), kopf.normal, 8)
    ruecksende = ("Versicherungsmakler " + m("namen", makler.voll(), name_bem(makler, "Rücksendeangabe")) + " · "
                  + m("strasse", makler.strasse_hnr(), "Rücksendeangabe") + " · "
                  + m("plzort", makler.plz_ort(), "Rücksendeangabe"))
    anschriftfeld(dok, seite, form_b, _adresszeilen(dok, kunde), ruecksende)
    infoblock(dok, seite, form_b, [("Ihr Ansprechpartner", m("namen", makler.voll(), name_bem(makler, "Informationsblock"))),
                                   ("Telefon", m("telefon", dok.telefon(makler, mobil=True), "Informationsblock Mobil")),
                                   ("E-Mail", m("email", makler.email(rng), "Informationsblock")),
                                   ("IHK-Registernummer", m("vertrag", K.ihk_registernummer(rng), "Vermittlerregister")),
                                   ("Datum", datum_lang(dok.heute))])
    dok.satz.merkmale.add("din5008_form_b" if form_b else "din5008_form_a")
    fl = Fluss(dok, 25 * MM, A4_B - 20 * MM, 25 * MM, A4_H - 25 * MM, seite=seite,
               y_start=(103.4 if form_b else 98.4) * MM)
    fl.absatz("Ihr Versicherungsordner – Ergebnisse unseres Jahresgesprächs", schrift=st.fett)
    fl.absatz(rng.choice([f"Liebe {kunde.herr_frau} ", f"{kunde.geehrt} "])
              + m("namen", kunde.anrede_name(), name_bem(kunde, "Anrede")) + ",")
    kind = dok.familienmitglied(kunde, "kind", alter=(14, 24))
    v1, v2 = rng.sample(D.ECHTE_VERSICHERER_KURZ, 2)
    fl.absatz("vielen Dank für das angenehme Gespräch am " + k(datum(dok.heute - datetime.timedelta(days=9)))
              + ". Wie besprochen fasse ich die Ergebnisse zusammen. Ihre Privathaftpflicht bei der " + k(v1)
              + " deckt auch Ihren Sohn bzw. Ihre Tochter " + m("namen", kind.vorname1, "Fließtext; nur Vorname")
              + " bis zum Ende der ersten Ausbildung ab. Bei der Berufsunfähigkeitsversicherung der " + k(v2)
              + " empfehle ich, die Rente auf " + k(_eur(rng, 1500, 2500)) + " monatlich zu erhöhen.")
    beruf = rng.choice(D.BERUFE)
    ag = rng.choice(D.ARBEITGEBER)
    fl.absatz("Da Sie seit dem Wechsel zur " + m("arbeitgeber", ag, "Fließtext") + " als "
              + m("beruf", beruf, "Fließtext") + " tätig sind, muss die Berufsgruppe im Vertrag angepasst werden. "
              "Bitte senden Sie mir dazu die Gehaltsabrechnung mit Ihrer Personalnummer "
              + m("vertrag", str(rng.randint(10000, 999999)), "Fließtext ohne Etikett") + ".")
    fl.absatz("Für Rückfragen erreichen Sie mich unter " + m("telefon", dok.telefon(makler, mobil=True), "Fließtext; Mobil")
              + " oder per E-Mail an " + m("email", makler.email(rng), "Fließtext") + ".")
    _gruss(fl, dok, None, makler, "Versicherungsmakler (§ 34d Abs. 1 GewO)", gruss=rng.choice(
        ["Mit freundlichen Grüßen", "Herzliche Grüße",
         "Viele Grüße aus " + m("sonstiges", makler.ort, "Ort in Grußformel")]))
    _seitenzahl_registrieren(dok)
    dok.titel = "Jahresgespräch"
    return "brief"


# ----------------------------------------------------------------------
# 3) Versicherungsschein mit Personentabelle (mehrseitig)
# ----------------------------------------------------------------------
def typ_versicherungsschein(dok: Dok) -> str:
    rng = dok.rng
    st = dok.stil
    sparte = rng.choice(["leben", "kranken", "kfz", "leben"])
    v = dok.versicherer(sparte)
    vn = dok.person(alter=(25, 70))
    dok.hauptperson = vn
    vsnr = K.vertragsnummer(rng, {"leben": "LV", "kranken": "KV", "kfz": "KF"}[sparte])
    knr = K.kundennummer(rng)
    versalien = rng.random() < 0.35

    def kopf(nr, gesamt):
        return (f"{v[1]} · Versicherungsschein-Nr. " + m("vertrag", vsnr, "Kopfzeile jede Seite")
                + " · Kunden-Nr. " + m("vertrag", knr, "Kopfzeile jede Seite") + f" · Seite {nr}/{gesamt}")
    _seitenzahl_registrieren(dok, kopf, unten=False)
    _fusszeile_registrieren(dok, v)
    seite = dok.satz.neue_seite()
    logo(seite, A4_B - 40 * MM, 16 * MM, st.akzent, rng)
    seite.text(25 * MM, 25 * MM, k(v[0]), st.kopf_familie.fett, 13, farbe=st.akzent)
    fl = Fluss(dok, 25 * MM, A4_B - 20 * MM, 22 * MM, A4_H - 32 * MM, seite=seite, y_start=38 * MM)
    fl.ueberschrift(k("Versicherungsschein"), groesse=st.groesse + 6)
    fl.kv("Versicherungsschein-Nr.:", m("vertrag", vsnr, "Schlüssel-Wert-Zeile"), fuell="." if rng.random() < 0.3 else None)
    fl.kv("Ausfertigungsdatum:", k(datum(dok.heute)))
    fl.luecke(st.zeilenhoehe * 0.5)
    fl.zeile("Versicherungsnehmer", schrift=st.fett)
    name = vn.liste().upper() if versalien else vn.voll(titel=True)
    fl.zeile(m("namen", name, name_bem(vn, "Versicherungsnehmer" + ("; Versalien, Nachname, Vorname" if versalien else ""))))
    fl.zeile(m("strasse", vn.strasse_hnr().upper() if versalien else vn.strasse_hnr(), "Versicherungsnehmer"))
    fl.zeile(m("plzort", vn.plz_ort().upper() if versalien else vn.plz_ort(), "Versicherungsnehmer"))
    geb, gbem = dok.geburtsdatum_text(vn.geburtsdatum)
    fl.zeile(rng.choice(["geb. am ", "geboren am ", "Geburtsdatum: ", "* "]) + m("geburt", geb, gbem))
    if rng.random() < 0.5:
        fl.zeile("Beruf: " + m("beruf", rng.choice(D.BERUFE), "Schlüssel-Wert"))
    fl.luecke(st.zeilenhoehe * 0.6)
    # Personentabelle
    personen = [(vn, "VN / versicherte Person")]
    if sparte in ("leben", "kranken"):
        ehe = dok.familienmitglied(vn, "ehe", alter=(25, 70))
        personen.append((ehe, "versicherte Person"))
        for _ in range(rng.randint(0, 2)):
            personen.append((dok.familienmitglied(vn, "kind", alter=(0, 17)), "mitversichertes Kind"))
    zeilen = []
    for p, rolle in personen:
        geb, gbem = dok.geburtsdatum_text(p.geburtsdatum, rng.choice(["punkt", "punkt", "kurz", "iso"]))
        nach = p.nachname.upper() if versalien else p.nachname
        vor = p.vornamen.upper() if versalien else p.vornamen
        zus = "; Versalien" if versalien else ""
        zeilen.append([m("namen", nach, name_bem(p, "Tabellenzelle Name" + zus)),
                       m("namen", vor, "Tabellenzelle Vorname" + zus),
                       m("geburt", geb, f"Tabellenspalte Geburtsdatum; {gbem}"), rolle])
    fl.zeile("Versicherte Personen", schrift=st.fett)
    fl.tabelle([("Name", 45 * MM, "links"), ("Vorname", 38 * MM, "links"),
                (rng.choice(["Geburtsdatum", "Geb.-Datum", "geboren am"]), 30 * MM, "links"),
                ("Rolle", 50 * MM, "links")], zeilen, groesse=max(7, st.groesse - 1), zebra=rng.random() < 0.5)
    # Vertragsdaten
    fl.zeile("Vertragsdaten", schrift=st.fett)
    beginn = datetime.date(rng.randint(2010, 2024), rng.randint(1, 12), 1)
    produkt = rng.choice(D.PRODUKTE["kfz" if sparte == "kfz" else sparte])
    fl.kv("Tarif:", k(produkt))
    fl.kv("Versicherungsbeginn:", k(datum(beginn)))
    fl.kv("Ablauf:", k(datum(beginn.replace(year=beginn.year + rng.choice([1, 12, 20, 25, 30])))))
    fl.kv("Beitrag (monatlich):", k(_eur(rng, 20, 400)))
    if sparte == "kfz":
        kz = K.kennzeichen(rng)
        fl.kv("Amtl. Kennzeichen:", m("kfz", kz, "Schlüssel-Wert"))
        fl.kv("Fahrzeug:", k(rng.choice(D.FAHRZEUGE)))
        fl.kv("FIN:", m("fin", K.fin(rng), "Schlüssel-Wert"))
        fl.kv("SF-Klasse Haftpflicht:", k(f"SF {rng.randint(1, 35)}"))
    elif sparte == "leben":
        fl.kv("Versicherungssumme:", k(_eur(rng, 20000, 300000)))
        fl.kv("Dynamik:", k(f"{rng.choice([3, 5])} % jährlich"))
    fl.luecke(st.zeilenhoehe * 0.4)
    # Bezugsrecht / Beitragszahler
    if sparte == "leben":
        bez = personen[1][0]
        text = ("Bezugsrecht im Todesfall: " + m("namen", bez.voll(), name_bem(bez, "Bezugsrecht")))
        if bez.geburtsname:
            text += " geb. " + m("namen", bez.geburtsname, "Geburtsname")
        geb, gbem = dok.geburtsdatum_text(bez.geburtsdatum)
        text += ", geboren am " + m("geburt", geb, gbem) + ", widerruflich."
        fl.absatz(text)
    if sparte == "leben" and rng.random() < 0.8:
        kinder = [p for p, r in personen if r == "mitversichertes Kind"] or [dok.familienmitglied(vn, "kind", (3, 17))]
        fl.absatz("Zulageberechtigt nach " + k("§ 10a EStG") + ". Steuer-ID der versicherten Person: "
                  + m("steuerid", K.steuer_id_formatieren(K.steuer_id(rng), rng.choice(["gruppen", "kompakt"])), "mit Etikett")
                  + "; Kindergeldnummer für " + m("namen", kinder[0].vorname1, "nur Vorname") + ": "
                  + m("kindergeld", K.kindergeldnummer(rng), "mit Etikett") + ".")
    # SEPA
    fl.zeile("Zahlungsweise: SEPA-Lastschrift", schrift=st.fett)
    inhaber = vn.voll() if rng.random() < 0.7 else personen[-1][0].voll()
    fl.kv("Kontoinhaber:", m("namen", inhaber, "Kontoinhaber"))
    land = rng.choice(["DE"] * 6 + ["AT", "NL", "LU"])
    fl.kv("IBAN:", m("iban", dok.iban_text(land), "Schlüssel-Wert" + ("" if land == "DE" else f"; IBAN {land}")))
    fl.kv("BIC:", m("bic", K.bic(rng, land), "Schlüssel-Wert"))
    fl.kv("Mandatsreferenz:", m("mandat", K.mandatsreferenz(rng), "Schlüssel-Wert"))
    fl.kv("Gläubiger-ID:", K.glaeubiger_id(rng))
    # Beiblatt (Seite 2)
    fl.neue_seite()
    fl.ueberschrift(k("Besondere Vereinbarungen"))
    for _ in range(rng.randint(3, 5)):
        par = rng.choice(["§ 1", "§ 2", "§ 5", "§ 8", "§ 12", "§ 14"])
        fl.absatz(f"Abweichend von {k(par + ' der Allgemeinen Versicherungsbedingungen')} gilt: "
                  + rng.choice(["Der Versicherungsschutz beginnt mit Zahlung des ersten Beitrags.",
                                "Die Wartezeiten entfallen für Unfälle.",
                                "Die Überschussbeteiligung wird verzinslich angesammelt.",
                                "Beitragsfreistellung ist jederzeit zum Monatsende möglich.",
                                "Der Vertrag verlängert sich jeweils um ein Jahr, wenn er nicht gekündigt wird."]))
    vm = dok.person(titel_quote=0.05)
    fl.absatz("Ihre Vermittlerin/Ihr Vermittler: " + m("namen", vm.voll(), name_bem(vm, "Vermittler"))
              + ", Vermittlernummer " + m("vertrag", K.vermittlernummer(rng), "Vermittlernummer")
              + ", Telefon " + m("telefon", dok.telefon(vm), "Vermittler") + ".")
    dok.titel = "Versicherungsschein"
    return "police"


# ----------------------------------------------------------------------
# 4) Beitragsrechnung
# ----------------------------------------------------------------------
def typ_beitragsrechnung(dok: Dok) -> str:
    rng = dok.rng
    st = dok.stil
    sparte = rng.choice(["kfz", "sach", "sach"])
    v = dok.versicherer(sparte)
    kunde = dok.person()
    dok.hauptperson = kunde
    form_b = rng.random() < 0.5
    rnr = K.rechnungsnummer(rng)
    vnr = K.vertragsnummer(rng, "KF" if sparte == "kfz" else "SV")
    info = [("Rechnungsnummer", m("vertrag", rnr, "Rechnungsnummer")),
            ("Versicherungsnummer", m("vertrag", vnr, "Informationsblock")),
            ("Datum", datum(dok.heute))]
    fl = _versicherer_brief(dok, form_b, kunde, v, info, k(f"Beitragsrechnung {dok.heute.year}"))
    fl.absatz(_anrede(kunde, dok))
    fl.absatz("für Ihre Versicherungen berechnen wir für den Zeitraum " + k(f"01.01.{dok.heute.year} – 31.12.{dok.heute.year}")
              + " folgende Beiträge:")
    zeilen = []
    gesamt = 0.0
    for _ in range(rng.randint(2, 4)):
        produkt = rng.choice(D.PRODUKTE[sparte])
        netto = rng.uniform(40, 900)
        gesamt += netto * 1.19
        zeilen.append([k(produkt), m("vertrag", K.vertragsnummer(rng, "SV"), "Tabellenzelle ohne Etikett"),
                       k(f"{netto:.2f}".replace(".", ",")), k(f"{netto * 0.19:.2f}".replace(".", ",")),
                       k(f"{netto * 1.19:.2f}".replace(".", ","))])
    fl.tabelle([("Tarif", 50 * MM, "links"), ("Vertrag", 38 * MM, "links"), ("Netto", 22 * MM, "rechts"),
                ("VersSt 19 %", 22 * MM, "rechts"), ("Brutto", 24 * MM, "rechts")], zeilen,
               groesse=max(7, st.groesse - 1))
    fuell = "." if rng.random() < 0.5 else None
    fl.kv("Gesamtbetrag", k(f"{gesamt:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")), fuell=fuell,
          fett_schluessel=True)
    if sparte == "kfz":
        fl.kv("Fahrzeug", m("kfz", K.kennzeichen_schreibweise(K.kennzeichen(rng), rng.choice(["bindestrich", "leer"])),
                            "Kennzeichen hinter Etikett Fahrzeug"), fuell=fuell)
    fl.luecke(st.zeilenhoehe * 0.5)
    if rng.random() < 0.45:
        marke, _, nummer = K.kreditkarte(rng)
        fl.absatz(f"Der Betrag wird am {k(datum(dok.heute + datetime.timedelta(days=14)))} Ihrer {marke} "
                  + m("kreditkarte", nummer, "Fließtext") + " (gültig bis " + f"{rng.randint(1, 12):02d}/{rng.randint(26, 30)}"
                  + ") belastet. Karteninhaber: " + m("namen", kunde.voll().upper(), name_bem(kunde, "Versalien; Karteninhaber")) + ".")
    else:
        fl.absatz("Wir buchen den Betrag am " + k(datum(dok.heute + datetime.timedelta(days=14)))
                  + " von Ihrem Konto ab:")
        fl.kv("Kontoinhaber", m("namen", kunde.liste(), name_bem(kunde, "Nachname, Vorname")), fuell=fuell)
        fl.kv("IBAN", m("iban", dok.iban_text(), "Schlüssel-Wert"), fuell=fuell)
        fl.kv("BIC", m("bic", K.bic(rng), "Schlüssel-Wert"), fuell=fuell)
        fl.kv("Mandatsreferenz", m("mandat", K.mandatsreferenz(rng), "Schlüssel-Wert"), fuell=fuell)
    fl.absatz("Bitte prüfen Sie die Angaben. Änderungen Ihrer Bankverbindung teilen Sie uns bitte mindestens "
              "zwei Wochen vor Fälligkeit mit.")
    _gruss(fl, dok, v[0], None, "Ihr Beitragsservice", unterschrift=False)
    _fusszeile_registrieren(dok, v)
    _seitenzahl_registrieren(dok)
    dok.titel = "Beitragsrechnung"
    return "beitragsrechnung"


# ----------------------------------------------------------------------
# 5) Kfz-Schadenmeldung mit Zeugen und Kennzeichen
# ----------------------------------------------------------------------
def typ_kfz_schadenmeldung(dok: Dok) -> str:
    rng = dok.rng
    st = dok.stil
    v = dok.versicherer("kfz")
    vn = dok.person(alter=(20, 80))
    dok.hauptperson = vn
    fahrer = vn if rng.random() < 0.6 else dok.familienmitglied(vn, "ehe", alter=(20, 80))
    gegner = dok.person()
    zeugen = [dok.person() for _ in range(rng.randint(1, 2))]
    snr = K.schadennummer(rng, "KH")
    seite = dok.satz.neue_seite()
    logo(seite, A4_B - 40 * MM, 12 * MM, st.akzent, rng)
    seite.text(20 * MM, 20 * MM, k(v[0]), st.kopf_familie.fett, 12, farbe=st.akzent)
    fl = Fluss(dok, 20 * MM, A4_B - 18 * MM, 20 * MM, A4_H - 20 * MM, seite=seite, y_start=32 * MM)
    fl.ueberschrift(k("Kfz-Schadenanzeige"), groesse=st.groesse + 5)
    fl.kv("Schaden-Nr.:", m("vertrag", snr, "Schlüssel-Wert"), tab=40 * MM)
    fl.kv("Versicherungsschein-Nr.:", m("vertrag", K.vertragsnummer(rng, "KH"), "Schlüssel-Wert"), tab=40 * MM)
    schadentag = dok.heute - datetime.timedelta(days=rng.randint(3, 30))
    fl.kv("Schadentag / Uhrzeit:", k(datum(schadentag)) + f", {rng.randint(6, 21):02d}:{rng.choice(['05', '15', '30', '45'])} Uhr",
          tab=40 * MM)
    fl.kv("Schadenort:", k(f"Kreuzung {rng.choice(['Bamberger Straße', 'Ringstraße', 'Hauptstraße'])} / "
                           f"{rng.choice(['Kirchenweg', 'Am Anger', 'Schulstraße'])}"), tab=40 * MM)
    tab = 42 * MM

    def abschnitt(titel):
        fl.luecke(st.zeilenhoehe * 0.3)
        fl.zeile(titel, schrift=st.fett, groesse=st.groesse + 0.5)

    abschnitt("1. Versicherungsnehmer")
    fl.kv("Name, Vorname:", m("namen", vn.liste(), name_bem(vn, "Formular Nachname, Vorname")), tab=tab)
    fl.kv("Anschrift:", m("strasse", vn.strasse_hnr(), "Formularzeile") + ", " + m("plzort", vn.plz_ort(), "Formularzeile"), tab=tab)
    fl.kv("Telefon:", m("telefon", dok.telefon(vn), "Formularzeile"), tab=tab)
    fl.kv("E-Mail:", m("email", vn.email(rng), "Formularzeile"), tab=tab)
    abschnitt("2. Fahrer zum Unfallzeitpunkt")
    if fahrer is vn:
        fl.zeile("wie Versicherungsnehmer")
    else:
        fl.kv("Name:", m("namen", fahrer.voll(), name_bem(fahrer, "Formularzeile Fahrer")), tab=tab)
    geb, gbem = dok.geburtsdatum_text(fahrer.geburtsdatum)
    fl.kv("Geburtsdatum:", m("geburt", geb, gbem), tab=tab)
    fl.kv("Führerschein-Nr.:", m("ausweis", K.fuehrerscheinnummer(rng), "Führerscheinnummer mit Etikett"), tab=tab)
    abschnitt("3. Ihr Fahrzeug")
    kz = K.kennzeichen(rng, rng.choice(["standard"] * 8 + ["e", "h"]))
    fl.kv("Amtl. Kennzeichen:", m("kfz", K.kennzeichen_schreibweise(kz, rng.choice(["bindestrich", "bindestrich", "leer", "kompakt"])),
                                  "Kennzeichen"), tab=tab)
    fl.kv("Hersteller/Typ:", k(rng.choice(D.FAHRZEUGE)), tab=tab)
    fl.kv("Fahrzeug-Ident-Nr.:", m("fin", K.fin(rng), "FIN"), tab=tab)
    abschnitt("4. Unfallgegner")
    fl.kv("Name:", m("namen", f"{gegner.herr_frau} {gegner.voll()}", name_bem(gegner, "mit Anrede")), tab=tab)
    if rng.random() < 0.3:
        land, akz = K.kennzeichen_ausland(rng)
        fl.kv("Kennzeichen:", m("auslaendisch", akz, f"ausländisches Kennzeichen ({land})"), tab=tab)
        strasse, ort = rng.choice(D.AUSLANDSADRESSEN)
        fl.kv("Anschrift:", m("auslaendisch", strasse, "ausländische Anschrift") + ", " + m("auslaendisch", ort, "ausländische Anschrift"), tab=tab)
        fl.kv("Telefon:", m("auslaendisch", K.telefon_ausland(rng), "ausländische Telefonnummer"), tab=tab)
    else:
        fl.kv("Kennzeichen:", m("kfz", K.kennzeichen(rng), "Kennzeichen Unfallgegner"), tab=tab)
        fl.kv("Anschrift:", m("strasse", gegner.strasse_hnr(), "Formularzeile") + ", " + m("plzort", gegner.plz_ort(), "Formularzeile"), tab=tab)
        fl.kv("Telefon:", m("telefon", dok.telefon(gegner, mobil=True), "Formularzeile"), tab=tab)
    fl.kv("Versicherer des Gegners:", k(rng.choice(D.ECHTE_VERSICHERER_KURZ)) + ", VS-Nr. "
          + m("vertrag", K.vertragsnummer(rng, "KH"), "VS-Nr. des Gegners"), tab=tab)
    abschnitt("5. Zeugen")
    for z in zeugen:
        r = rng.random()
        if r < 0.3:
            land_tel = m("auslaendisch", K.telefon_ausland(rng), "ausländische Telefonnummer")
        else:
            land_tel = m("telefon", dok.telefon(z, mobil=rng.random() < 0.5), "Zeuge")
        fl.absatz(m("namen", z.voll(), name_bem(z, "Zeuge")) + ", " + m("strasse", z.strasse_hnr(), "Zeuge") + ", "
                  + m("plzort", z.plz_ort(), "Zeuge") + ", Tel. " + land_tel, abstand=2)
    abschnitt("6. Unfallhergang")
    art = rng.choice(D.UNFALLARTEN)
    z0 = zeugen[0]
    fl.absatz(f"Unfallart: {k(art)}. " + m("namen", f"{fahrer.herr_frau} {fahrer.nachname}", name_bem(fahrer, "Fließtext mit Anrede"))
              + " fuhr stadtauswärts und musste verkehrsbedingt anhalten. Das nachfolgende Fahrzeug mit dem Kennzeichen "
              + m("kfz", K.kennzeichen_schreibweise(K.kennzeichen(rng), "bindestrich"), "Fließtext")
              + ", gesteuert von " + m("namen", gegner.voll(), name_bem(gegner, "Fließtext ~trennen"))
              + ", fuhr auf. Der Zeuge " + m("namen", z0.nachname, name_bem(z0, "Fließtext nur Nachname"))
              + " hat den Vorgang von der Bushaltestelle aus beobachtet. Die Polizei ("
              + k(rng.choice(D.POLIZEI)) + ", Aktenzeichen " + m("vertrag", K.aktenzeichen(rng), "Aktenzeichen Polizei")
              + ") nahm den Unfall auf.")
    fl.absatz("Verletzt wurde niemand. " + m("namen", gegner.vorname1 + " " + gegner.nachname.upper(),
                                              name_bem(gegner, "Nachname in Versalien"))
              + " hat das Verschulden vor Ort eingeräumt.")
    fl.luecke(st.zeilenhoehe)
    fl.zeile(m("sonstiges", vn.ort, "Wohnort ohne PLZ in Ort-Datum-Zeile") + ", " + k(datum(dok.heute)))
    fl.seite.unterschrift(fl.x0 + 60 * MM, fl.y - 2, rng)
    fl.zeile("(Unterschrift Versicherungsnehmer)", groesse=7)
    _seitenzahl_registrieren(dok, lambda nr, g: f"Schadenanzeige · Schaden-Nr. " + m("vertrag", snr, "Kopfzeile jede Seite"), ab_seite=2)
    dok.titel = "Schadenanzeige Kfz"
    return "schadenmeldung"


# ----------------------------------------------------------------------
# 6) Antrag als ausgefülltes AcroForm-Formular
# ----------------------------------------------------------------------
def typ_antrag_formular(dok: Dok, formular: bool = True) -> str:
    """Antragsformular mit Formularfeldern (nicht eingebrannt). Mit formular=False werden die Werte
    als normaler Text gesetzt (z. B. für einen eingescannten Papierantrag)."""
    rng = dok.rng
    st = dok.stil
    v = dok.versicherer(rng.choice(["leben", "kranken"]))
    p = dok.person(alter=(20, 60))
    dok.hauptperson = p
    seite = dok.satz.neue_seite()
    satz: Satz = dok.satz
    st_label = st.normal
    seite.text(20 * MM, 18 * MM, k(v[0]), st.kopf_familie.fett, 12, farbe=st.akzent)
    titel = rng.choice(["Antrag auf Berufsunfähigkeitsversicherung", "Antrag auf private Krankenversicherung",
                        "Antrag auf Riester-Rente", "Antrag auf Riester-Rente"])
    seite.text(20 * MM, 27 * MM, k(titel), st.fett, 13)
    seite.text(20 * MM, 33 * MM, "Antragsnummer: " + m("vertrag", K.vertragsnummer(rng, "AN"), "Antragsnummer (Text)"),
               st.normal, 9)
    felder = []   # (Label, Wert, Kategorie oder None, Bemerkung, Breite)
    geb, gbem = dok.geburtsdatum_text(p.geburtsdatum, "punkt")
    felder += [("Anrede", p.herr_frau, None, "", 25), ("Titel", p.titel or "", "namen" if p.titel else None, "Titel-Feld", 25),
               ("Vorname", p.vornamen, "namen", name_bem(p, "Formularfeld Vorname"), 50),
               ("Nachname", p.nachname, "namen", name_bem(p, "Formularfeld Nachname"), 60),
               ("Geburtsname", p.geburtsname or "", "namen" if p.geburtsname else None, "Formularfeld Geburtsname", 50),
               ("Geburtsdatum", geb, "geburt", "Formularfeld", 30),
               ("Geburtsort", rng.choice(D.GEBURTSORTE), "sonstiges", "Geburtsort im Formularfeld", 45),
               ("Staatsangehörigkeit", D.STAATSANGEHOERIGKEIT[p.herkunft], "sonstiges", "Staatsangehörigkeit", 40),
               ("Straße, Hausnummer", p.strasse_hnr(), "strasse", "Formularfeld", 80),
               ("PLZ", p.plz, "plzort", "Formularfeld PLZ (Ort in eigenem Feld)", 20),
               ("Ort", p.ort, "plzort", "Formularfeld Ort (PLZ in eigenem Feld)", 60),
               ("Telefon", dok.telefon(p), "telefon", "Formularfeld", 45),
               ("Mobil", dok.telefon(p, mobil=True), "telefon", "Formularfeld Mobil", 45),
               ("E-Mail", p.email(rng), "email", "Formularfeld", 80),
               ("Ausgeübter Beruf", rng.choice(D.BERUFE), "beruf", "Formularfeld", 70),
               ("Arbeitgeber", rng.choice(D.ARBEITGEBER), "arbeitgeber", "Formularfeld", 80),
               ("Steuer-ID", K.steuer_id(rng), "steuerid", "Formularfeld", 40),
               ("Sozialversicherungsnummer", K.sv_formatieren(K.sv_nummer(rng, p.geburtsdatum, p.geburtsname or p.nachname, p.geschlecht),
                                                              rng.choice(["gruppen", "kompakt", "gruppen2"])), "svnr", "Formularfeld", 45),
               ("Ausweisnummer", K.personalausweisnummer(rng, rng.random() < 0.5), "ausweis", "Formularfeld Personalausweis", 35),
               ("IBAN", dok.iban_text(rng.choice(["DE", "DE", "DE", "AT", "CH", "PL", "IT", "ES", "FR", "BE"])), "iban", "Formularfeld", 80),
               ("BIC", K.bic(rng), "bic", "Formularfeld", 35),
               ("Kontoinhaber", p.voll(), "namen", name_bem(p, "Formularfeld Kontoinhaber"), 60),
               ("Körpergröße / Gewicht", f"{rng.randint(152, 198)} cm / {rng.randint(48, 125)} kg", "sonstiges",
                "Gesundheitsangabe", 40),
               ]
    if rng.random() < 0.6:
        felder.append(("Steuernummer (Selbstständige)", K.steuernummer(rng), "steuernr", "Formularfeld", 40))
    if "Kranken" in titel or rng.random() < 0.4:
        felder.append(("KV-Nummer (gesetzlich)", K.kvnr(rng), "kvnr", "Formularfeld", 30))
    if "Riester" in titel:
        kind = dok.familienmitglied(p, "kind", (1, 17))
        kgeb, _ = dok.geburtsdatum_text(kind.geburtsdatum, "punkt")
        felder += [("Kind: Vorname", kind.vornamen, "namen", name_bem(kind, "Formularfeld Kind"), 40),
                   ("Kind: Geburtsdatum", kgeb, "geburt", "Formularfeld Kind", 30),
                   ("Kindergeldnummer", K.kindergeldnummer(rng), "kindergeld", "Formularfeld", 40)]
    behandler = dok.person(titel_quote=1.0)
    diagnose = rng.choice(D.DIAGNOSEN)
    felder += [("Behandlungen (5 Jahre)", diagnose, "diagnose", "Gesundheitsfrage", 110),
               ("Behandelnder Arzt", behandler.voll(titel=True), "namen", name_bem(behandler, "Formularfeld Arzt"), 90)]
    y = 42 * MM
    x_label, x_feld = 20 * MM, 72 * MM
    groesse = max(8.0, min(10.0, st.groesse))
    for label, wert, kat, bem, breite in felder:
        if y > A4_H - 40 * MM:
            seite = dok.satz.neue_seite()
            y = 25 * MM
        seite.text(x_label, y + groesse, label + ":", st_label, groesse * 0.95)
        rect = fitz.Rect(x_feld, y, x_feld + breite * MM * 0.95, y + groesse * 1.6)
        if formular:
            from .satz import Schrift
            helv = Schrift("helv")
            dargestellt = helv.darstellbar(wert)
            w = fitz.Widget()
            w.field_name = "f_" + "".join(c for c in label if c.isalnum())[:24] + f"_{len(felder)}_{int(y)}"
            w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
            w.rect = rect
            w.field_value = dargestellt
            w.text_font = "Helv"
            w.text_fontsize = groesse
            w.border_color = (0.6, 0.6, 0.6)
            w.fill_color = (0.94, 0.96, 1.0)
            seite.page.add_widget(w)
            if kat and dargestellt.strip():
                b = bem + ("; transliteriert" if dargestellt != wert else "")
                e = satz.eintrag(dargestellt, kat, seite.nr, kanal="formular", bemerkung=b)
                e["woerter"] = [[rect.x0 + 2, rect.y0 + 1, rect.x0 + 2 + helv.breite(t, groesse), rect.y1 - 1, t]
                                for t in dargestellt.split()]
            elif dargestellt.strip():
                satz.klartext_merken(seite.nr, dargestellt)
        else:
            seite.rechteck(rect, farbe=(0.6, 0.6, 0.6))
            markup = m(kat, wert, bem) if (kat and wert) else wert
            if wert:
                seite.text(rect.x0 + 2, rect.y0 + groesse * 1.15, markup, st.normal, groesse)
        y += groesse * 2.2
    # Kontrollkästchen ohne Personenbezug
    if formular:
        for i, label in enumerate(["Raucher/in", "Gefährliche Hobbys", "Vorversicherung vorhanden"]):
            seite.text(x_label, y + groesse, label, st_label, groesse * 0.95)
            w = fitz.Widget()
            w.field_name = f"cb_{i}"
            w.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
            w.rect = fitz.Rect(x_feld, y + 1, x_feld + 10, y + 11)
            w.field_value = rng.random() < 0.5
            seite.page.add_widget(w)
            y += groesse * 2.0
        satz.merkmale.add("formular")
    seite.text(x_label, y + 3 * groesse, m("sonstiges", p.ort, "Wohnort ohne PLZ in Ort-Datum-Zeile") + ", " + k(datum(dok.heute)),
               st.normal, groesse)
    seite.unterschrift(x_feld + 30 * MM, y + 3 * groesse, rng)
    seite.text(x_feld + 30 * MM, y + 4.4 * groesse, "Unterschrift Antragsteller/in", st.normal, 7)
    _seitenzahl_registrieren(dok)
    dok.titel = titel
    return "antrag_formular"


# ----------------------------------------------------------------------
# 7) Arztbrief (mit Praxisstempel als Bild)
# ----------------------------------------------------------------------
def _praxisstempel(dok: Dok, seite, rect, arzt: Person, fach: str, praxis_strasse: str, praxis_ort: str):
    """Praxisstempel als Rasterbild auf einer Textseite (Namen nur im Bild lesbar)."""
    rng = dok.rng
    hilfs = Satz("stempel")
    hilfs.doc = fitz.open()
    s = hilfs.neue_seite(180, 62)
    fam = dok.stil.kopf_familie
    s.rechteck((2, 2, 178, 60), farbe=(0.1, 0.1, 0.5), breite=1.2)
    s.text(8, 16, m("namen", arzt.voll(titel=True), name_bem(arzt, "Stempelbild")), fam.fett, 10, farbe=(0.1, 0.1, 0.5))
    s.text(8, 28, fach, fam.normal, 8, farbe=(0.1, 0.1, 0.5))
    s.text(8, 39, praxis_strasse + " · " + praxis_ort, fam.normal, 8, farbe=(0.1, 0.1, 0.5))
    s.text(8, 51, "LANR " + m("sonstiges", K.lanr(rng), "LANR im Stempelbild") + " · BSNR " + str(rng.randint(10**8, 10**9 - 1)),
           fam.normal, 8, farbe=(0.1, 0.1, 0.5))
    p = SC.ScanParameter(dpi=rng.choice([150, 200, 300]), jpeg=rng.choice([60, 75, 85]), schraeg=rng.uniform(-4, 4),
                         rauschen=rng.uniform(0, 6), farbig=True, seed=rng.randint(0, 10**6))
    SC.bild_einfuegen(s.page, seite.page, rect, p, hilfs.eintraege)
    for e in hilfs.eintraege:
        e["seite"] = seite.nr
        e["bemerkung"] = (e["bemerkung"] + "; " if e["bemerkung"] else "") + "Bild auf Textseite"
        dok.satz.eintraege.append(e)
    for txt in sum(hilfs.klartext.values(), []):
        dok.satz.klartext_merken(seite.nr, txt)
    dok.satz.merkmale.add("stempel_bild")


def typ_arztbrief(dok: Dok) -> str:
    rng = dok.rng
    st = dok.stil
    arzt1 = dok.person(titel_quote=0.0, alter=(35, 66))
    arzt1.titel = "Dr. med."
    arzt2 = dok.person(titel_quote=0.0, alter=(35, 66))
    arzt2.titel = rng.choice(["Dr. med.", "Dr. med.", "Prof. Dr. med."])
    fach = rng.choice(D.FACHRICHTUNGEN)
    patient = dok.person(alter=(18, 85))
    dok.hauptperson = patient
    praxis_ort = dok.ort(ausser=(patient.ort,))
    praxis_strasse = f"{rng.choice(D.STRASSEN)} {rng.randint(1, 60)}"
    form_b = rng.random() < 0.5
    seite = dok.satz.neue_seite()
    faltmarken(seite, form_b)
    kopf = st.kopf_familie
    seite.text(25 * MM, 15 * MM, "Gemeinschaftspraxis " + m("namen", arzt1.voll(titel=True), name_bem(arzt1, "Briefkopf Praxis"))
               + " & " + m("namen", arzt2.voll(titel=True), name_bem(arzt2, "Briefkopf Praxis")), kopf.fett, 11, farbe=st.akzent)
    seite.text(25 * MM, 21 * MM, fach + " · " + praxis_strasse + " · " + praxis_ort[0] + " " + praxis_ort[1], kopf.normal, 8)
    empf_arzt = dok.person(titel_quote=0.0)
    empf_arzt.titel = "Dr. med."
    anschrift = ["Herrn Kollegen" if empf_arzt.geschlecht == "m" else "Frau Kollegin",
                 m("namen", empf_arzt.voll(titel=True), name_bem(empf_arzt, "Adressfeld Arzt")),
                 m("strasse", empf_arzt.strasse_hnr(), "Adressfeld Praxis"),
                 m("plzort", empf_arzt.plz_ort(), "Adressfeld Praxis")]
    anschriftfeld(dok, seite, form_b, anschrift, f"Gemeinschaftspraxis · {praxis_strasse} · {praxis_ort[0]} {praxis_ort[1]}")
    infoblock(dok, seite, form_b, [("Datum", datum(dok.heute)), ("Fallnummer", m("vertrag", f"{dok.heute.year}-{rng.randint(10000, 99999)}", "Fallnummer"))])
    dok.satz.merkmale.add("din5008_form_b" if form_b else "din5008_form_a")
    fl = Fluss(dok, 25 * MM, A4_B - 20 * MM, 25 * MM, A4_H - 25 * MM, seite=seite,
               y_start=(103.4 if form_b else 98.4) * MM)
    geb, gbem = dok.geburtsdatum_text(patient.geburtsdatum)
    fl.absatz("Betr.: Ihre Patientin/Ihr Patient " + m("namen", patient.voll(), name_bem(patient, "Betreff Patient"))
              + ", geb. " + m("geburt", geb, gbem) + ", wohnhaft " + m("strasse", patient.strasse_hnr(), "Betreff")
              + ", " + m("plzort", patient.plz_ort(), "Betreff"), schrift=st.fett)
    fl.kv("Versichertennummer:", m("kvnr", K.kvnr(rng), "KVNR mit Etikett"), tab=45 * MM)
    fl.kv("Kostenträger:", k(rng.choice(["AOK", "Techniker Krankenkasse", "BARMER", "DAK-Gesundheit", "IKK classic",
                                         "Knappschaft", "BKK Mobil"])), tab=45 * MM)
    fl.absatz(f"Sehr geehrte{'r Herr' if empf_arzt.geschlecht == 'm' else ' Frau'} Kollege{'' if empf_arzt.geschlecht == 'm' else 'in'} "
              + m("namen", empf_arzt.nachname, name_bem(empf_arzt, "Anrede Kollege")) + ",")
    fl.absatz("vielen Dank für die Überweisung. Wir sahen " + m("namen", f"{patient.herr_frau} {patient.nachname}",
                                                                   name_bem(patient, "Fließtext mit Anrede"))
              + " am " + k(datum(dok.heute - datetime.timedelta(days=5))) + " in unserer Sprechstunde.")
    fl.zeile("Diagnosen:", schrift=st.fett)
    for d in rng.sample(D.DIAGNOSEN, rng.randint(2, 4)):
        fl.absatz("– " + m("diagnose", d, "Diagnoseliste mit ICD-10"), x0=fl.x0 + 4 * MM, abstand=1)
    fl.zeile("Anamnese:", schrift=st.fett)
    ag = rng.choice(D.ARBEITGEBER)
    mutter = dok.person(geschlecht="w", herkunft=patient.herkunft, alter=(60, 90), titel_quote=0)
    fl.absatz("Seit etwa drei Monaten bestehen belastungsabhängige Beschwerden. Familienanamnese: Die Mutter, "
              + m("namen", f"Frau {mutter.voll()}", name_bem(mutter, "Fließtext Angehörige ~trennen")) + ", leidet an "
              + m("diagnose", rng.choice(D.DIAGNOSEN), "Diagnose einer Angehörigen") + ". Die Patientin/der Patient arbeitet als "
              + m("beruf", rng.choice(D.BERUFE), "Fließtext") + " bei der " + m("arbeitgeber", ag, "Fließtext")
              + ("" if ag.endswith(".") else "."))
    fl.zeile("Medikation:", schrift=st.fett)
    for med in rng.sample(D.MEDIKAMENTE, rng.randint(1, 3)):
        fl.absatz("• " + m("diagnose", med, "Medikation"), x0=fl.x0 + 4 * MM, abstand=1)
    fl.absatz("Wir empfehlen eine Kontrolle in sechs Wochen. Für Rückfragen erreichen Sie uns unter "
              + m("telefon", "0" + praxis_ort[2] + " " + str(rng.randint(100000, 999999)), "Praxistelefon") + ".")
    _gruss(fl, dok, None, arzt2, fach, gruss="Mit freundlichen kollegialen Grüßen")
    if rng.random() < 0.75:
        fl.platz(70)
        r = fitz.Rect(fl.x0 + 70 * MM, fl.y - 55, fl.x0 + 70 * MM + 180 * 0.8, fl.y - 55 + 62 * 0.8)
        if r.y1 < A4_H - 15 * MM:
            _praxisstempel(dok, fl.seite, r, arzt2, fach, praxis_strasse, f"{praxis_ort[0]} {praxis_ort[1]}")
    _seitenzahl_registrieren(dok, lambda nr, g: "Patient/in: " + m("namen", patient.liste(), name_bem(patient, "Kopfzeile Folgeseite")), ab_seite=2)
    dok.titel = "Arztbrief"
    return "arztbrief"


# ----------------------------------------------------------------------
# 8) PKV-Leistungsabrechnung
# ----------------------------------------------------------------------
def typ_leistungsabrechnung(dok: Dok) -> str:
    rng = dok.rng
    st = dok.stil
    v = dok.versicherer("kranken")
    vn = dok.person(alter=(28, 75))
    dok.hauptperson = vn
    kind = dok.familienmitglied(vn, "kind", (1, 17))
    vsnr = f"{rng.randint(100, 999)} {rng.randint(100, 999)} {rng.randint(100, 999)}-{rng.randint(0, 9)}"
    form_b = rng.random() < 0.5
    info = [("Versicherungsnummer", m("vertrag", vsnr, "Informationsblock")),
            ("Abrechnung vom", k(datum(dok.heute))),
            ("Seite", "1")]
    kopf = (f"Leistungsabrechnung vom {datum(dok.heute)} · Versicherungsnummer "
            + m("vertrag", vsnr, "Folgeseitenkopf"))
    fl = _versicherer_brief(dok, form_b, vn, v, info, k("Ihre Leistungsabrechnung"), folgekopf=_folgekopf_fn(dok, kopf))
    fl.absatz(_anrede(vn, dok))
    fl.absatz("wir haben die eingereichten Rechnungen geprüft und erstatten wie folgt:")
    zeilen = []
    viele = rng.random() < 0.3
    for person in (vn, kind) if rng.random() < 0.7 else (vn,):
        for _ in range(rng.randint(8, 14) if viele else rng.randint(2, 4)):
            r = rng.random()
            if r < 0.5:
                arzt = dok.person(titel_quote=0)
                arzt.titel = rng.choice(["Dr. med.", "Dr. med. dent.", "Dr."])
                erbringer = m("namen", arzt.voll(titel=True), name_bem(arzt, "Leistungserbringer in Tabelle"))
            elif r < 0.7:
                thera = dok.person(titel_quote=0)
                erbringer = "Physiotherapie " + m("namen", thera.nachname, name_bem(thera, "Name in Firmenbezeichnung"))
            elif r < 0.85:
                erbringer = k(rng.choice(D.APOTHEKEN))
            else:
                erbringer = k(rng.choice(D.KLINIKEN))
            betrag = rng.uniform(25, 1800)
            tarif = rng.choice(D.PRODUKTE["kranken"])
            zeilen.append([m("namen", person.vorname1, "Tabellenzelle nur Vorname"),
                           k(datum(dok.heute - datetime.timedelta(days=rng.randint(10, 120)))), erbringer,
                           k(f"{betrag:.2f}".replace(".", ",")), k(f"{betrag * rng.choice([1, 0.8, 0.7]):.2f}".replace(".", ",")),
                           k(tarif)])
    fl.tabelle([("Person", 22 * MM, "links"), ("Datum", 21 * MM, "links"), ("Leistungserbringer", 48 * MM, "links"),
                ("Betrag", 18 * MM, "rechts"), ("Erstattung", 20 * MM, "rechts"), ("Tarif", 33 * MM, "links")], zeilen,
               groesse=max(7, st.groesse - 1.5), zebra=True)
    fl.absatz("Die Erstattung von " + k(_eur(rng, 200, 4000)) + " überweisen wir auf Ihr Konto "
              + m("iban", dok.iban_text(), "Fließtext") + ". Ihre Selbstbeteiligung für "
              + k(str(dok.heute.year)) + " ist mit " + k(_eur(rng, 100, 900)) + " ausgeschöpft.")
    fl.absatz("Versicherte Personen dieser Abrechnung: " + m("namen", vn.voll(), name_bem(vn, "Fließtext"))
              + " (geb. " + m("geburt", dok.geburtsdatum_text(vn.geburtsdatum, "punkt")[0], "TT.MM.JJJJ") + ") und "
              + m("namen", kind.voll(), name_bem(kind, "Fließtext; Kind")) + " (geb. "
              + m("geburt", dok.geburtsdatum_text(kind.geburtsdatum, "kurz")[0], "TT.MM.JJ") + ").")
    fl.absatz("Hinweis nach " + k("§ 192 VVG") + ": Erstattet werden Aufwendungen für medizinisch notwendige "
              "Heilbehandlungen im tariflichen Umfang.")
    sb, _, sb_tel = _sachbearbeiter(dok, v)
    _gruss(fl, dok, v[0], sb, "Leistungsabteilung Kranken")
    fl.zeile("Durchwahl: " + m("telefon", sb_tel, "Durchwahl unter Unterschrift"))
    _fusszeile_registrieren(dok, v)
    _seitenzahl_registrieren(dok)
    dok.titel = "Leistungsabrechnung"
    return "leistungsabrechnung"


# ----------------------------------------------------------------------
# 9) Renteninformation / Rentenauskunft
# ----------------------------------------------------------------------
def typ_rentenauskunft(dok: Dok) -> str:
    rng = dok.rng
    st = dok.stil
    p = dok.person(alter=(27, 66))
    dok.hauptperson = p
    sv = K.sv_formatieren(K.sv_nummer(rng, p.geburtsdatum, p.geburtsname or p.nachname, p.geschlecht),
                          rng.choice(["gruppen", "gruppen", "kompakt"]))
    seite = dok.satz.neue_seite()
    form_b = False
    faltmarken(seite, form_b)
    seite.text(25 * MM, 17 * MM, k("Rentenversicherung Rhein-Weser"), st.kopf_familie.fett, 13, farbe=st.akzent)
    seite.text(25 * MM, 22 * MM, k("Träger der gesetzlichen Rentenversicherung"), st.kopf_familie.normal, 8)
    anschriftfeld(dok, seite, form_b, _adresszeilen(dok, p, versalien=rng.random() < 0.3),
                  "Rentenversicherung Rhein-Weser · 32423 Minden")
    infoblock(dok, seite, form_b, [("Versicherungsnummer", m("svnr", sv, "Informationsblock")),
                                   ("Datum", datum(dok.heute))])
    dok.satz.merkmale.add("din5008_form_a")
    fl = Fluss(dok, 25 * MM, A4_B - 20 * MM, 25 * MM, A4_H - 22 * MM, seite=seite, y_start=98.4 * MM,
               folgeseite=_folgekopf_fn(dok, "Versicherungsnummer " + m("svnr", sv, "Folgeseitenkopf")))
    fl.absatz(k("Renteninformation") + " – mit Angaben zu Ihrer Rente", schrift=st.fett, groesse=st.groesse + 1)
    fl.absatz(_anrede(p, dok))
    geb, gbem = dok.geburtsdatum_text(p.geburtsdatum)
    fl.absatz("diese Renteninformation erhalten Sie, weil Sie das 27. Lebensjahr vollendet haben. Grundlage sind die "
              "bei uns gespeicherten Daten. Geburtsdatum laut unseren Unterlagen: " + m("geburt", geb, gbem) + ".")
    regel = p.geburtsdatum.replace(year=p.geburtsdatum.year + 67)
    fl.kv("Regelaltersrente ab:", k(datum(regel.replace(day=1))), tab=70 * MM)
    fl.kv("Rente wegen voller Erwerbsminderung:", k(_eur(rng, 600, 2000)), tab=70 * MM)
    fl.kv("Höhe Ihrer künftigen Regelaltersrente:", k(_eur(rng, 900, 2600)), tab=70 * MM)
    fl.zeile("Ihr Versicherungsverlauf (Auszug)", schrift=st.fett)
    zeilen = []
    jahr = p.geburtsdatum.year + 16
    for _ in range(rng.randint(3, 6)):
        dauer = rng.randint(1, 8)
        art = rng.choice(["Pflichtbeitragszeit (Beschäftigung)", "Ausbildung", "Kindererziehung",
                          "Arbeitslosigkeit", "Pflichtbeitragszeit (Beschäftigung)"])
        ag = m("arbeitgeber", rng.choice(D.ARBEITGEBER), "Tabellenzelle Arbeitgeber") if "Beschäftigung" in art or art == "Ausbildung" else "–"
        zeilen.append([k(f"01.{rng.randint(1, 12):02d}.{jahr}"), k(f"31.12.{jahr + dauer}"), k(art), ag])
        jahr += dauer + 1
    fl.tabelle([("von", 24 * MM, "links"), ("bis", 24 * MM, "links"), ("Zeitart", 60 * MM, "links"),
                ("Arbeitgeber", 55 * MM, "links")], zeilen, groesse=max(7, st.groesse - 1))
    fl.absatz("Für die Besteuerung der Rente haben wir Ihre Steuer-Identifikationsnummer "
              + m("steuerid", K.steuer_id_formatieren(K.steuer_id(rng), rng.choice(["gruppen", "kompakt"])), "Fließtext mit Etikett")
              + " gespeichert. Die Rente wird auf das Konto " + m("iban", dok.iban_text(), "Fließtext") + " gezahlt.")
    berater = dok.person(titel_quote=0)
    fl.absatz("Fragen beantwortet Ihnen gern " + m("namen", f"{berater.herr_frau} {berater.nachname}", name_bem(berater, "Fließtext mit Anrede"))
              + " in unserer Auskunfts- und Beratungsstelle, Telefon " + m("telefon", dok.telefon(berater, art="din_durchwahl"), "Fließtext") + ".")
    _gruss(fl, dok, "Rentenversicherung Rhein-Weser", None, None, unterschrift=False)
    _seitenzahl_registrieren(dok)
    dok.titel = "Renteninformation"
    return "rentenauskunft"


# ----------------------------------------------------------------------
# 10) Kündigung (Kundenbrief)
# ----------------------------------------------------------------------
def typ_kuendigung(dok: Dok) -> str:
    rng = dok.rng
    st = dok.stil
    p = dok.person(alter=(20, 85))
    dok.hauptperson = p
    v = dok.versicherer()
    seite = dok.satz.neue_seite()
    form_b = rng.random() < 0.5
    faltmarken(seite, form_b)
    # Absenderblock oben rechts oder links
    x_abs = 120 * MM if rng.random() < 0.5 else 25 * MM
    y = 15 * MM
    for z in [m("namen", p.voll(titel=True), name_bem(p, "Absenderblock")), m("strasse", p.strasse_hnr(), "Absenderblock"),
              m("plzort", p.plz_ort(), "Absenderblock"), "Tel. " + m("telefon", dok.telefon(p), "Absenderblock"),
              m("email", p.email(rng), "Absenderblock")]:
        seite.text(x_abs, y, z, st.normal, max(8, st.groesse - 1))
        y += st.groesse * 1.15
    ruecksende = (m("namen", p.voll(), name_bem(p, "Rücksendeangabe")) + " · " + m("strasse", p.strasse_hnr(), "Rücksendeangabe")
                  + " · " + m("plzort", p.plz_ort(), "Rücksendeangabe"))
    anschriftfeld(dok, seite, form_b, [v[0], "Kundenservice", rng.choice(D.POSTFAECHER) if rng.random() < 0.4 else v[4],
                                       f"{v[2]} {v[3]}"], ruecksende)
    dok.satz.merkmale.add("din5008_form_b" if form_b else "din5008_form_a")
    fl = Fluss(dok, 25 * MM, A4_B - 20 * MM, 25 * MM, A4_H - 20 * MM, seite=seite, y_start=(96 if form_b else 90) * MM)
    fl.zeile(m("sonstiges", p.ort, "Wohnort ohne PLZ in Ort-Datum-Zeile") + ", " + k(datum_lang(dok.heute)),
             x=A4_B - 20 * MM, ausrichtung="rechts")
    fl.luecke(st.zeilenhoehe)
    sparte = rng.choice(["Hausratversicherung", "Privathaftpflichtversicherung", "Kfz-Versicherung",
                         "Rechtsschutzversicherung", "Zahnzusatzversicherung"])
    vnr = K.vertragsnummer(rng, "HR")
    fl.absatz(f"Kündigung meiner {k(sparte)}, Versicherungsschein-Nr. " + m("vertrag", vnr, "Betreffzeile"),
              schrift=st.fett)
    fl.absatz("Sehr geehrte Damen und Herren,")
    termin = datetime.date(dok.heute.year, 12, 31)
    grund = rng.choice(["umzug", "tod", "frist", "verkauf"])
    if grund == "umzug":
        neu = dok.person()
        fl.absatz("hiermit kündige ich den oben genannten Vertrag wegen meines Umzugs zum " + k(datum(termin)) + ". Ab dem "
                  + k(datum(dok.heute + datetime.timedelta(days=30))) + " lautet meine neue Anschrift: "
                  + m("strasse", neu.strasse_hnr(), "neue Anschrift im Fließtext") + ", "
                  + m("plzort", neu.plz_ort(), "neue Anschrift im Fließtext") + ".")
    elif grund == "tod":
        verst = dok.familienmitglied(p, "ehe", (60, 95))
        fl.absatz("mein Ehemann/meine Ehefrau " + m("namen", verst.voll(), name_bem(verst, "Fließtext; verstorben ~trennen"))
                  + ", geboren am " + m("geburt", dok.geburtsdatum_text(verst.geburtsdatum)[0], "Fließtext") + ", ist am "
                  + k(datum(dok.heute - datetime.timedelta(days=20))) + " verstorben. Ich kündige daher den Vertrag zum nächstmöglichen "
                  "Zeitpunkt. Die Sterbeurkunde liegt bei.")
    elif grund == "verkauf":
        kz = K.kennzeichen(rng)
        fl.absatz("ich habe mein Fahrzeug mit dem amtlichen Kennzeichen " + m("kfz", kz, "Fließtext")
                  + " am " + k(datum(dok.heute - datetime.timedelta(days=4))) + " verkauft und kündige den Vertrag nach "
                  + k("§ 95 VVG") + ". Käufer ist " + m("namen", dok.person().voll(), "Fließtext; Käufer") + ".")
    else:
        fl.absatz("hiermit kündige ich den oben genannten Vertrag fristgerecht zum " + k(datum(termin))
                  + ", hilfsweise zum nächstmöglichen Zeitpunkt.")
    fl.absatz("Bitte bestätigen Sie mir die Kündigung und den Beendigungszeitpunkt schriftlich oder per E-Mail an "
              + m("email", p.email(rng), "Fließtext") + ". Ein eventuelles Guthaben überweisen Sie bitte auf mein Konto "
              + m("iban", dok.iban_text(rng.choice(["DE", "DE", "DE", "NL", "AT"])), "Fließtext") + ".")
    if rng.random() < 0.2:
        marke, _, nummer = K.kreditkarte(rng)
        fl.absatz(f"Die Beiträge wurden zuletzt von meiner {marke} " + m("kreditkarte", nummer, "Fließtext")
                  + " abgebucht – bitte stoppen Sie die Belastung.")
    fl.absatz("Einer telefonischen Kontaktaufnahme zu Rückgewinnungszwecken widerspreche ich.")
    _gruss(fl, dok, None, p, None, ia=False)
    if rng.random() < 0.4:
        fl.zeile("Anlage: Kopie Personalausweis (Nr. " + m("ausweis", K.personalausweisnummer(rng, False), "Ausweisnummer in Klammern")
                 + ")", groesse=st.groesse * 0.9)
    _seitenzahl_registrieren(dok)
    dok.titel = "Kündigung"
    return "kuendigung"


# ----------------------------------------------------------------------
# 11) Maklervollmacht
# ----------------------------------------------------------------------
def typ_maklervollmacht(dok: Dok) -> str:
    rng = dok.rng
    st = dok.stil
    p = dok.person(alter=(20, 80))
    dok.hauptperson = p
    makler = dok.person(alter=(35, 65), titel_quote=0.05)
    firma_kern = f"{makler.nachname} & Partner"
    seite = dok.satz.neue_seite()
    fl = Fluss(dok, 22 * MM, A4_B - 22 * MM, 22 * MM, A4_H - 22 * MM, seite=seite, y_start=24 * MM,
               folgeseite=lambda s: (s.text(22 * MM, 14 * MM, "Maklervollmacht · Mandant/in: " + m("namen", p.liste(), name_bem(p, "Kopfzeile Folgeseite")),
                                            st.normal, 7.5, zusatz="Folgeseitenkopf"), 22 * MM)[1])
    fl.ueberschrift(k("Maklervertrag und Maklervollmacht"), groesse=st.groesse + 5)
    fl.zeile("zwischen", groesse=st.groesse * 0.9)
    geb, gbem = dok.geburtsdatum_text(p.geburtsdatum)
    fl.absatz(m("namen", p.voll(titel=True), name_bem(p, "Vertragspartei")) + ", geboren am " + m("geburt", geb, gbem) + "\n"
              + m("strasse", p.strasse_hnr(), "Vertragspartei") + ", " + m("plzort", p.plz_ort(), "Vertragspartei") + "\n"
              + "Telefon " + m("telefon", dok.telefon(p), "Vertragspartei") + " · E-Mail " + m("email", p.email(rng), "Vertragspartei"),
              x0=fl.x0 + 8 * MM)
    fl.zeile("– nachfolgend „Mandant“ genannt – und", groesse=st.groesse * 0.9)
    fl.absatz("Versicherungsmakler " + m("namen", makler.nachname, name_bem(makler, "Name in Firmenbezeichnung")) + " & Partner GmbH, "
              "vertreten durch den Geschäftsführer " + m("namen", makler.voll(titel=True), name_bem(makler, "Geschäftsführer")) + "\n"
              + "Registrierungsnummer " + m("vertrag", K.ihk_registernummer(rng), "IHK-Register") + " (" + k("§ 34d Abs. 1 GewO") + ")",
              x0=fl.x0 + 8 * MM)
    fl.zeile("– nachfolgend „Makler“ genannt.", groesse=st.groesse * 0.9)
    absaetze = [
        "Der Mandant beauftragt den Makler mit der Vermittlung, Verwaltung und Betreuung seiner Versicherungsverträge. "
        "Der Makler ist berechtigt, Willenserklärungen gegenüber Versicherern abzugeben und entgegenzunehmen.",
        "Die Vollmacht umfasst insbesondere die Kündigung bestehender Verträge, die Einholung von Auskünften über "
        "Vertrags- und Schadendaten sowie die Korrespondenz mit Versicherern nach " + k("§ 7 VVG") + ".",
        "Der Makler verarbeitet personenbezogene Daten des Mandanten auf Grundlage von " + k("Art. 6 Abs. 1 lit. b DSGVO")
        + ". Gesundheitsdaten werden nur mit ausdrücklicher Einwilligung nach " + k("Art. 9 Abs. 2 lit. a DSGVO") + " verarbeitet.",
        "Der Vertrag ist auf unbestimmte Zeit geschlossen und kann von beiden Seiten mit einer Frist von einem Monat "
        "zum Monatsende gekündigt werden.",
        "Die Haftung des Maklers ist auf die Mindestversicherungssumme der Berufshaftpflichtversicherung nach "
        + k("§ 9 VersVermV") + " beschränkt, soweit nicht Vorsatz oder grobe Fahrlässigkeit vorliegt.",
    ]
    for i, a in enumerate(absaetze, 1):
        fl.absatz(f"§ {i} " + a)
    if rng.random() < 0.5:
        fl.absatz("Zur Legitimation hat der Mandant seinen Personalausweis vorgelegt (Ausweis-Nr. "
                  + m("ausweis", K.personalausweisnummer(rng, rng.random() < 0.5), "Ausweisnummer mit Etikett") + ", gültig bis "
                  + k(datum(dok.heute + datetime.timedelta(days=rng.randint(200, 3000)))) + ").")
    # Unterschriftsblöcke in zwei Spalten
    fl.platz(st.zeilenhoehe * 8)
    y = fl.y + st.zeilenhoehe * 2
    s = fl.seite
    links, rechts = fl.x0, fl.x0 + 90 * MM
    s.text(links, y, m("sonstiges", p.ort, "Ort-Datum-Zeile Mandant") + ", " + k(datum(dok.heute)), st.normal, st.groesse)
    s.text(rechts, y, m("sonstiges", makler.ort, "Ort-Datum-Zeile Makler") + ", " + k(datum(dok.heute)), st.normal, st.groesse)
    s.unterschrift(links + 5, y + 22, rng)
    s.unterschrift(rechts + 5, y + 22, rng)
    s.linie(links, y + 28, links + 70 * MM, y + 28, 0.4)
    s.linie(rechts, y + 28, rechts + 70 * MM, y + 28, 0.4)
    s.text(links, y + 38, m("namen", p.voll(), name_bem(p, "Unterschriftsblock zweispaltig")), st.normal, st.groesse * 0.9)
    s.text(rechts, y + 38, m("namen", makler.voll(), name_bem(makler, "Unterschriftsblock zweispaltig")), st.normal, st.groesse * 0.9)
    s.text(links, y + 38 + st.groesse * 1.1, "Mandant", st.normal, st.groesse * 0.8)
    s.text(rechts, y + 38 + st.groesse * 1.1, "Makler", st.normal, st.groesse * 0.8)
    dok.satz.merkmale.add("unterschrift_grafik")
    if rng.random() < 0.5:
        fl.neue_seite()
        fl.ueberschrift(k("Einwilligung in die Datenverarbeitung"))
        fl.absatz("Ich, " + m("namen", p.voll(), name_bem(p, "Fließtext Einwilligung")) + ", geboren am "
                  + m("geburt", dok.geburtsdatum_text(p.geburtsdatum)[0], "Fließtext Einwilligung")
                  + ", willige ein, dass der Makler meine Gesundheitsdaten an Versicherer übermittelt, soweit dies "
                  "für die Prüfung von Anträgen erforderlich ist (" + k("§ 213 VVG") + ").")
        fl.absatz("Die Einwilligung gilt auch für meine mitversicherten Angehörigen: "
                  + m("namen", dok.familienmitglied(p, "ehe", (20, 80)).voll(), "Fließtext Angehörige") + " und "
                  + m("namen", dok.familienmitglied(p, "kind", (2, 17)).vornamen, "Fließtext nur Vorname") + ".")
        fl.absatz("Die Einwilligung kann jederzeit mit Wirkung für die Zukunft widerrufen werden. Ein Widerruf ist zu "
                  "richten an: " + m("namen", makler.voll(), name_bem(makler, "Fließtext")) + ", "
                  + m("email", makler.email(rng), "Fließtext") + ".")
        fl.luecke(dok.stil.zeilenhoehe * 2)
        fl.zeile(m("sonstiges", p.ort, "Ort-Datum-Zeile Einwilligung") + ", " + k(datum(dok.heute)))
        fl.seite.unterschrift(fl.x0 + 70 * MM, fl.y - 4, rng)
        fl.zeile("Unterschrift " + m("namen", p.initiale(), name_bem(p, "Unterschriftszeile; Initiale")))
    _seitenzahl_registrieren(dok)
    dok.titel = "Maklervollmacht"
    return "vollmacht"


# ----------------------------------------------------------------------
# 12) Mahnung
# ----------------------------------------------------------------------
def typ_mahnung(dok: Dok) -> str:
    rng = dok.rng
    st = dok.stil
    v = dok.versicherer()
    p = dok.person()
    dok.hauptperson = p
    form_b = rng.random() < 0.5
    knr = K.kundennummer(rng)
    stufe = rng.choice(["Zahlungserinnerung", "1. Mahnung", "Qualifizierte Mahnung nach § 38 VVG"])
    info = [("Kundennummer", m("vertrag", knr, "Informationsblock")), ("Datum", datum(dok.heute))]
    fl = _versicherer_brief(dok, form_b, p, v, info, k(stufe))
    fl.absatz(_anrede(p, dok))
    fl.absatz("leider konnten wir für die folgenden Beiträge keinen Zahlungseingang feststellen:")
    zeilen = []
    for _ in range(rng.randint(1, 3)):
        zeilen.append([m("vertrag", K.vertragsnummer(rng, "SV"), "Tabellenzelle ohne Etikett"),
                       k(datum(dok.heute - datetime.timedelta(days=rng.randint(20, 80)))), k(_betrag(rng, 15, 600)),
                       k(_betrag(rng, 0, 5))])
    fl.tabelle([("Vertragsnummer", 45 * MM, "links"), ("fällig seit", 30 * MM, "links"), ("Beitrag EUR", 28 * MM, "rechts"),
                ("Mahngebühr EUR", 30 * MM, "rechts")], zeilen, groesse=max(7, st.groesse - 1))
    fl.absatz("Die Lastschrift von Ihrem Konto " + m("iban", dok.iban_text(), "Fließtext") + " (Mandatsreferenz "
              + m("mandat", K.mandatsreferenz(rng), "Mandatsreferenz in Klammern") + ") wurde von Ihrer Bank zurückgegeben.")
    if "§ 38" in stufe:
        fl.absatz("Wir setzen Ihnen hiermit eine Zahlungsfrist von zwei Wochen. Nach Ablauf der Frist besteht nach "
                  + k("§ 38 Abs. 2 VVG") + " kein Versicherungsschutz; wir sind dann berechtigt, den Vertrag nach "
                  + k("§ 38 Abs. 3 VVG") + " fristlos zu kündigen.")
    betreuer = dok.person(titel_quote=0.05)
    fl.absatz("Bei Zahlungsschwierigkeiten wenden Sie sich bitte an Ihren Betreuer " + m("namen", betreuer.voll(), name_bem(betreuer, "Fließtext ~trennen"))
              + " (Telefon " + m("telefon", dok.telefon(betreuer, mobil=True), "Fließtext in Klammern") + ").")
    _gruss(fl, dok, v[0], None, "Inkasso / Beitragsservice", unterschrift=False)
    _fusszeile_registrieren(dok, v)
    _seitenzahl_registrieren(dok)
    dok.titel = "Mahnung"
    return "mahnung"


# ----------------------------------------------------------------------
# 13) Zweispaltige Kundeninformation
# ----------------------------------------------------------------------
def typ_zweispaltig(dok: Dok) -> str:
    rng = dok.rng
    st = dok.stil
    v = dok.versicherer("leben")
    p = dok.person(alter=(30, 80))
    dok.hauptperson = p
    vnr = K.vertragsnummer(rng, "LV")
    seite = dok.satz.neue_seite()
    seite.text(20 * MM, 18 * MM, k(v[0]), st.kopf_familie.fett, 12, farbe=st.akzent)
    seite.text(20 * MM, 28 * MM, k(f"Ihre persönliche Jahresmitteilung {dok.heute.year - 1}"), st.fett, st.groesse + 5)
    seite.linie(20 * MM, 31 * MM, A4_B - 20 * MM, 31 * MM, 0.8, st.akzent)
    mitte = A4_B / 2
    links = Fluss(dok, 20 * MM, mitte - 4 * MM, 20 * MM, A4_H - 20 * MM, seite=seite, y_start=40 * MM)
    rechts = Fluss(dok, mitte + 4 * MM, A4_B - 20 * MM, 20 * MM, A4_H - 20 * MM, seite=seite, y_start=40 * MM)
    seite.linie(mitte, 36 * MM, mitte, A4_H - 25 * MM, 0.3, (0.6, 0.6, 0.6))
    links.zeile("Ihre Vertragsdaten", schrift=st.fett)
    links.kv("Versicherungsnehmer", m("namen", p.voll(titel=True), name_bem(p, "Spalte links")), tab=33 * MM)
    links.kv("Vertragsnummer", m("vertrag", vnr, "Spalte links"), tab=33 * MM)
    links.kv("Versicherte Person", m("namen", p.initiale(), name_bem(p, "Initiale")), tab=33 * MM)
    links.kv("Geburtsdatum", m("geburt", dok.geburtsdatum_text(p.geburtsdatum)[0], "Spalte links"), tab=33 * MM)
    links.kv("Tarif", k(rng.choice(D.PRODUKTE["leben"])), tab=33 * MM)
    links.luecke(st.zeilenhoehe)
    links.absatz(f"{p.geehrt} " + m("namen", p.anrede_name(), name_bem(p, "Anrede, zweispaltig")) + ",")
    links.absatz("Ihr Vertrag hat sich im vergangenen Jahr gut entwickelt. Der Wert Ihrer Versicherung beträgt zum "
                 + k(f"31.12.{dok.heute.year - 1}") + " insgesamt " + k(_eur(rng, 4000, 80000))
                 + ". Darin enthalten ist die Überschussbeteiligung von " + k(_eur(rng, 100, 2500)) + ".")
    links.absatz("Die laufende Verzinsung lag bei " + k(f"{rng.uniform(1.5, 3.5):.2f} %".replace(".", ","))
                 + ". Die Garantieleistung zum Ablauf bleibt unverändert.")
    ehe = dok.familienmitglied(p, "ehe", (30, 85))
    rechts.zeile("Was sich geändert hat", schrift=st.fett)
    rechts.absatz("Im Berichtsjahr haben Sie das Bezugsrecht geändert. Bezugsberechtigt ist jetzt "
                  + m("namen", ehe.voll(), name_bem(ehe, "Fließtext zweispaltig ~trennen")) + ". Die Änderung haben wir am "
                  + k(datum(dok.heute - datetime.timedelta(days=200))) + " bestätigt.")
    rechts.absatz("Ihre Beiträge zahlen Sie per Lastschrift von dem Konto " + m("iban", dok.iban_text(), "Fließtext zweispaltig")
                  + ". Die Beiträge sind nach " + k("§ 10 Abs. 1 Nr. 2 EStG") + " als Vorsorgeaufwendungen absetzbar.")
    vm = dok.person(titel_quote=0.05)
    rechts.absatz("Ihre Vermittlerin/Ihr Vermittler " + m("namen", vm.voll(), name_bem(vm, "Fließtext zweispaltig"))
                  + " berät Sie gern zu Zuzahlungen und Dynamik. Sie erreichen sie/ihn unter "
                  + m("telefon", dok.telefon(vm), "Fließtext zweispaltig") + " oder " + m("email", vm.email(rng), "Fließtext zweispaltig") + ".")
    rechts.absatz("Hinweis: Diese Mitteilung ersetzt keine Steuerbescheinigung. Bewahren Sie sie bitte bei Ihren "
                  "Vertragsunterlagen auf.")
    dok.satz.merkmale.add("zweispaltig")
    _seitenzahl_registrieren(dok)
    dok.titel = "Jahresmitteilung"
    return "sonstiges"


# ----------------------------------------------------------------------
# 14) E-Mail-Ausdruck
# ----------------------------------------------------------------------
def typ_email_ausdruck(dok: Dok) -> str:
    rng = dok.rng
    st = dok.stil
    v = dok.versicherer()
    p = dok.person(alter=(20, 75))
    dok.hauptperson = p
    sb, sb_mail, sb_tel = _sachbearbeiter(dok, v)
    cc = dok.familienmitglied(p, "ehe", (20, 75))
    p_mail, cc_mail = p.email(rng), cc.email(rng)
    snr = K.schadennummer(rng, rng.choice(["KH", "HR", "GL"]))
    fl = Fluss(dok, 18 * MM, A4_B - 18 * MM, 22 * MM, A4_H - 18 * MM)
    gedruckt = datum(dok.heute) + f" {rng.randint(7, 20):02d}:{rng.randint(0, 59):02d}"

    def kf(seite, nr, gesamt):
        seite.text(18 * MM, 10 * MM, m("namen", p.voll(), name_bem(p, "Kopfzeile E-Mail-Programm")), st.normal, 7.5, zusatz="Kopfzeile")
        seite.text(A4_B - 18 * MM, A4_H - 8 * MM, f"Gedruckt am {gedruckt} – Seite {nr} von {gesamt}", st.normal, 7,
                   ausrichtung="rechts")
    dok.kopf_fuss.append(kf)
    tab = 24 * MM
    absender_name = m("namen", p.voll(), name_bem(p, "E-Mail-Kopf"))
    fl.kv("Von:", absender_name + " <" + m("email", p_mail, "E-Mail-Kopf") + ">", tab=tab, fett_schluessel=True)
    fl.kv("Gesendet:", f"{rng.choice(['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag'])}, {datum_lang(dok.heute)} "
          f"{rng.randint(7, 22):02d}:{rng.randint(0, 59):02d}", tab=tab, fett_schluessel=True)
    fl.kv("An:", "schaden@" + v[1].lower().replace(" ", "-") + "-versicherung.de", tab=tab, fett_schluessel=True)
    fl.kv("Cc:", m("namen", cc.voll(), name_bem(cc, "E-Mail-Kopf Cc")) + " <" + m("email", cc_mail, "E-Mail-Kopf Cc") + ">",
          tab=tab, fett_schluessel=True)
    fl.kv("Betreff:", "AW: Ihr Schaden " + m("vertrag", snr, "Betreff ohne Etikett Nr.") + " – Rückfrage", tab=tab, fett_schluessel=True)
    fl.kv("Anlagen:", f"Foto_{rng.randint(1000, 9999)}.jpg; Rechnung_Werkstatt.pdf", tab=tab, fett_schluessel=True)
    fl.seite.linie(fl.x0, fl.y - st.groesse * 0.5, fl.x1, fl.y - st.groesse * 0.5, 0.5)
    fl.luecke(st.zeilenhoehe)
    fl.absatz(rng.choice([f"Hallo {sb.herr_frau} ", f"Sehr geehrte{'r' if sb.geschlecht == 'm' else ''} {sb.herr_frau} "])
              + m("namen", sb.nachname, name_bem(sb, "Anrede E-Mail")) + ",")
    werkstatt = dok.person(titel_quote=0)
    fl.absatz("anbei wie besprochen die Rechnung der Werkstatt " + m("namen", werkstatt.nachname, name_bem(werkstatt, "Name in Firmenbezeichnung"))
              + " und die Fotos. Der Schaden ist am " + k(datum(dok.heute - datetime.timedelta(days=12)))
              + " in der Tiefgarage passiert. Meine Frau bzw. mein Mann " + m("namen", cc.vorname1, name_bem(cc, "nur Vorname"))
              + " hat den Wagen dort geparkt; der Nachbar, Herr " + m("namen", dok.person(geschlecht="m").nachname, "Fließtext mit Anrede")
              + ", hat den Schaden bemerkt.")
    fl.absatz("Die Reparaturkosten betragen " + k(_eur(rng, 400, 6000)) + ". Bitte überweisen Sie den Betrag auf mein Konto "
              + m("iban", dok.iban_text(), "E-Mail-Text") + ". Bei Fragen bin ich unter "
              + m("telefon", dok.telefon(p, mobil=True), "E-Mail-Text") + " erreichbar.")
    if rng.random() < 0.5:
        marke, _, nummer = K.kreditkarte(rng)
        fl.absatz(f"Den Abschleppdienst habe ich vor Ort mit meiner {marke} " + m("kreditkarte", nummer, "E-Mail-Text")
                  + " bezahlt (Beleg anbei).")
    if rng.random() < 0.3:
        # längerer Verlauf: mehrere zitierte Nachrichten (Ausdruck über zwei Seiten)
        for runde in range(rng.randint(3, 5)):
            alt_d = dok.heute - datetime.timedelta(days=4 + runde * 3)
            fl.absatz(f"Am {datum(alt_d)} schrieb " + m("namen", p.voll(), name_bem(p, "Zitatkopf älterer Nachricht"))
                      + " <" + m("email", p_mail, "Zitatkopf älterer Nachricht") + ">:", farbe=(0.25, 0.25, 0.25))
            fl.absatz("> > Sehr geehrte Damen und Herren, anbei die Unterlagen zu meinem Schaden. Mein Kennzeichen ist "
                      + m("kfz", K.kennzeichen(rng), "zitierter Text") + ", die Fahrzeug-Identnummer "
                      + m("fin", K.fin(rng), "zitierter Text") + ". Meine Telefonnummer: "
                      + m("telefon", dok.telefon(p), "zitierter Text") + ". Bitte rufen Sie mich zwischen 9 und 12 Uhr an.",
                      farbe=(0.25, 0.25, 0.25))
    fl.absatz("Viele Grüße\n" + m("namen", p.voll(), name_bem(p, "E-Mail-Signatur")) + "\n"
              + m("strasse", p.strasse_hnr(), "E-Mail-Signatur") + "\n" + m("plzort", p.plz_ort(), "E-Mail-Signatur") + "\n"
              + "Tel.: " + m("telefon", dok.telefon(p), "E-Mail-Signatur") + "\n"
              + "Mobil: " + m("telefon", dok.telefon(p, mobil=True, art=rng.choice(["plus49", "din", "plus49_null"])), "E-Mail-Signatur"))
    fl.luecke(st.zeilenhoehe * 0.5)
    alt = dok.heute - datetime.timedelta(days=3)
    fl.absatz(f"Am {datum(alt)} um {rng.randint(8, 17):02d}:{rng.randint(10, 59):02d} schrieb "
              + m("namen", sb.voll(), name_bem(sb, "Zitatkopf")) + " <" + m("email", sb_mail, "Zitatkopf") + ">:",
              farbe=(0.25, 0.25, 0.25))
    zitat = [f"> {p.geehrt} " + m("namen", p.anrede_name(), name_bem(p, "zitierte Anrede")) + ",",
             "> vielen Dank für Ihre Schadenmeldung. Für die Bearbeitung benötigen wir noch die",
             "> Reparaturrechnung und Fotos des Schadens. Bitte geben Sie bei Antworten immer die",
             "> Schadennummer " + m("vertrag", snr, "Zitat mit Etikett") + " an.",
             "> Mit freundlichen Grüßen",
             "> " + m("namen", sb.voll(), name_bem(sb, "Zitat-Signatur")),
             "> Schadenservice, Durchwahl " + m("telefon", sb_tel, "Zitat-Signatur")]
    for z in zitat:
        fl.zeile(z, farbe=(0.25, 0.25, 0.25), groesse=st.groesse * 0.95)
    fl.luecke(st.zeilenhoehe)
    fl.absatz("Diese E-Mail enthält vertrauliche Informationen. Wenn Sie nicht der richtige Adressat sind, informieren Sie "
              "bitte sofort den Absender und vernichten Sie diese E-Mail.", groesse=st.groesse * 0.8, farbe=(0.4, 0.4, 0.4))
    dok.titel = "E-Mail Schaden"
    return "email_ausdruck"


# ----------------------------------------------------------------------
# 15) Bestandsliste (tabellenlastig, Querformat, mehrseitig)
# ----------------------------------------------------------------------
def typ_bestandsliste(dok: Dok) -> str:
    rng = dok.rng
    st = dok.stil
    makler = dok.person(alter=(35, 65))
    dok.hauptperson = makler
    stand = datum(dok.heute)
    fl = Fluss(dok, 12 * MM, dok.format[0] - 12 * MM, 22 * MM, dok.format[1] - 14 * MM,
               folgeseite=lambda s: 22 * MM)

    def kf(seite, nr, gesamt):
        seite.text(12 * MM, 10 * MM, "Maklerbüro " + m("namen", makler.voll(), name_bem(makler, "Kopfzeile jede Seite"))
                   + f" – Bestandsliste Privatkunden – Stand {stand}", st.normal, 7.5, zusatz="Kopfzeile")
        seite.text(seite.breite - 12 * MM, seite.hoehe - 7 * MM, f"Seite {nr}/{gesamt} – vertraulich", st.normal, 7,
                   ausrichtung="rechts")
    dok.kopf_fuss.append(kf)
    zeilen = []
    for i in range(rng.randint(18, 32)):
        p = dok.person(alter=(18, 88), titel_quote=0.06, adel_quote=0.05)
        r = rng.random()
        if r < 0.15:
            name, bem = p.liste().upper(), "Nachname, Vorname in Versalien"
        elif r < 0.25 and p.titel:
            name, bem = f"{p.nachname}, {p.titel} {p.vornamen}", "Nachname, Titel Vorname"
        elif r < 0.32:
            name, bem = p.liste(partikel_hinten=True), "Nachname, Vorname (Partikel hinten)"
        else:
            name, bem = p.liste(), "Nachname, Vorname"
        geb, gbem = dok.geburtsdatum_text(p.geburtsdatum, rng.choice(["punkt", "punkt", "kurz"]))
        sparte = rng.choice(["Hausrat", "PHV", "Kfz", "BU", "Leben", "Wohngebäude", "Rechtsschutz", "PKV", "Unfall"])
        vers = rng.choice(D.ECHTE_VERSICHERER_KURZ + [x[1] for x in D.VERSICHERER])
        zeilen.append([str(i + 1), m("namen", name, name_bem(p, f"Tabellenspalte Kunde; {bem}")),
                       m("geburt", geb, f"Tabellenspalte Geb.-Datum; {gbem}"),
                       m("plzort", p.plz_ort(), "Tabellenspalte PLZ/Ort"), k(sparte), k(vers),
                       m("vertrag", K.vertragsnummer(rng, rng.choice(["LV", "KF", "HR", "BU"])), "Tabellenspalte Vertragsnummer"),
                       k(_betrag(rng, 30, 2400)), k(datum(datetime.date(rng.randint(2025, 2045), rng.randint(1, 12), 1)))])
    breiten = [9, 58, 22, 48, 22, 30, 38, 20, 22]
    koepfe = ["Nr.", "Kunde (Name, Vorname)", rng.choice(["Geb.-Datum", "Geburtsdatum", "geb."]), "PLZ / Ort", "Sparte",
              "Versicherer", "Vertragsnummer", "Beitrag p.a.", "Ablauf"]
    ausr = ["rechts", "links", "links", "links", "links", "links", "links", "rechts", "links"]
    fl.tabelle(list(zip(koepfe, [b * MM for b in breiten], ausr)), zeilen, groesse=min(st.groesse, rng.choice([7, 7.5, 8])),
               zebra=rng.random() < 0.6, gitter=rng.random() < 0.7, zeilenabstand=1.1)
    dok.satz.merkmale.update({"querformat"})
    dok.titel = "Bestandsliste"
    return "tabelle"


TYPEN = {
    "brief_form_a": lambda dok: typ_brief(dok, form_b=False),
    "brief_form_b": lambda dok: typ_brief(dok, form_b=True),
    "versicherungsschein": typ_versicherungsschein,
    "beitragsrechnung": typ_beitragsrechnung,
    "kfz_schadenmeldung": typ_kfz_schadenmeldung,
    "antrag_formular": typ_antrag_formular,
    "arztbrief": typ_arztbrief,
    "leistungsabrechnung": typ_leistungsabrechnung,
    "rentenauskunft": typ_rentenauskunft,
    "kuendigung": typ_kuendigung,
    "maklervollmacht": typ_maklervollmacht,
    "mahnung": typ_mahnung,
    "zweispaltig": typ_zweispaltig,
    "email_ausdruck": typ_email_ausdruck,
    "bestandsliste": typ_bestandsliste,
}
