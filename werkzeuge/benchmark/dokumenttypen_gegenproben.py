"""Gegenproben-Strom des Benchmark-Generators (Generator 1.3, nur auf Anfrage: gegenproben=True bzw. --gegenproben).

Die erweiterte Verteilung (dokumenttypen_erweitert.py) misst, ob die neuen Regeln Ausweise, Faxe, Formulare und Listen
FINDEN. Ob dieselben Regeln auf Unterlagen ohne diese Merkmale etwas zerstören oder still übersehen, misst sie kaum:
die Vorlagen der Korpora s3x/s9x enthalten keine nummerierten Kfz-Listen neben dem Wort "Führerschein", keine
sechsstelligen Zahlen auf Seiten, die "Personalausweis" nennen, keine Kontaktzeilen ohne Satzzeichen auf E-Mail-
Ausdrucken, keine Versicherer-Faxe mit Markennamen, keine Ereignisort-Feldnamen in anderer Wortstellung und keine
ausgefüllten Formularzeilen mit drei Feld-Wert-Zellen in Versalien. Dieser Strom erzeugt genau solche Unterlagen –
mit vollständiger Wahrheit: die Personenangaben als zu schwärzende Einträge, alles, was eine zu weite Regel träfe,
als zu behaltende Einträge (Tarife, Daten, Summen, Versicherer, Ereignisorte, Formulartexte). Er ist KEINE
unabhängige Prüfung: seine Vorlagen entstanden zusammen mit den Korrekturen der Erkennung (Review der Runde 2b).

    gp_kfz_angebot         Angebotsvergleich Kfz mit "Führerschein" im Text und nummerierter Angebotsliste
    gp_gwg_zahlen          GwG-Legitimation ("Personalausweis") mit sechsstelligen Zahlen hinter Feldnamen
    gp_email_kontakt       E-Mail-Ausdruck ("<" im Kopf) mit Tel/Fax- und Kto/Blz-Zeilen ohne Satzzeichen
    gp_fax_versicherer     Fax eines Versicherers, Markenname als Absenderkennung
    gp_fax_kunde           Fax einer Privatperson mit Kopfzeilen realer Geräte (Sekunden, AM/PM, "S. 1/2", "Page")
    gp_versalien_zeilen    EDV-Ausdruck in Courier: Formularzeilen mit drei Feld-Wert-Zellen in Versalien, Straßen
                           mit mehreren Leerzeichen
    gp_steuernummer        Schreiben mit Steuernummern in den üblichen Schreibweisen (Genitiv, " / ", Vierergruppen)
    gp_ereignisort         gescannte Kfz-Schadenanzeige: "Ort des Schadens", "Ort der Besichtigung", "Ihrer Wahl"
    gp_td2_ausweis         Kopie eines vorläufigen Personalausweises (TD2), immer gescannt

Eigene Zufallsströme ("plan_gegenproben/<seed>", "g<seed>/<nr>/<versuch>"); Standard- und erweiterte Verteilung
bleiben unverändert.
"""

from __future__ import annotations

import datetime
import random

from . import kennungen as K
from .bausteine import Dok, Fluss, datum, name_bem, stil_waehlen
from .dokumenttypen import _betrag
from .dokumenttypen_erweitert import _versal, typ_personalausweis
from .satz import A4_B, A4_H, MM, k, m

TYPEN_REIHENFOLGE = ["gp_kfz_angebot", "gp_gwg_zahlen", "gp_email_kontakt", "gp_fax_versicherer", "gp_fax_kunde",
                     "gp_versalien_zeilen", "gp_steuernummer", "gp_ereignisort", "gp_td2_ausweis"]
# Scan-Wahrscheinlichkeit und Varianten je Typ
SCAN = {
    "gp_kfz_angebot": (0.3, ["scan_300_gut", "scan_200_schraeg"]),
    "gp_gwg_zahlen": (0.5, ["scan_300_gut", "scan_200_schraeg", "scan_150_rauschen"]),
    "gp_email_kontakt": (0.2, ["scan_300_gut"]),
    "gp_fax_versicherer": (0.6, ["fax", "fax_fein"]),
    "gp_fax_kunde": (0.6, ["fax", "fax_fein"]),
    "gp_versalien_zeilen": (0.4, ["scan_300_gut", "scan_200_schraeg"]),
    "gp_steuernummer": (0.3, ["scan_300_gut", "fax"]),
    "gp_ereignisort": (1.0, ["scan_300_gut", "scan_200_schraeg", "scan_150_rauschen"]),
    "gp_td2_ausweis": (1.0, ["scan_300_gut", "scan_200_schraeg", "scan_150_rauschen", "scan_farbig"]),
}
_MARKEN = ["HUK-COBURG", "ERGO", "SIGNAL IDUNA", "Debeka", "Provinzial", "Gothaer", "ALLIANZ", "Alte Leipziger"]
_TARIFE = [("Allianz", "Kfz Komfort"), ("HUK-COBURG", "Classic Plus"), ("ERGO", "Kfz Smart"),
           ("DEVK", "Kfz Premium"), ("Gothaer", "Autoschutz Plus"), ("AXA", "Kfz Kompakt")]
_STRASSEN_ZWEIWORT = ["BERLINER", "HOHE", "FRANKFURTER", "ALTE", "BREITE", "LANGE", "KÖLNER", "MÜNCHNER"]
_STRASSEN_WORT = ["STRASSE", "STRASSE", "ALLEE", "WEG", "PLATZ"]


def plane_gegenproben(anzahl: int, seed: int) -> list:
    """Plan des Gegenproben-Stroms: die Typen reihum (jeder Typ in jedem Block von neun Dokumenten), Scans nach SCAN."""
    from .generator import Plan
    rng = random.Random(f"plan_gegenproben/{seed}")
    plaene = []
    for nr in range(1, anzahl + 1):
        typ = TYPEN_REIHENFOLGE[(nr - 1) % len(TYPEN_REIHENFOLGE)]
        quote, varianten = SCAN[typ]
        scan = rng.choice(varianten) if rng.random() < quote else None
        plaene.append(Plan(nr, typ, scan, (), mischung="gegenproben",
                           variante="td2" if typ == "gp_td2_ausweis" else None))
    return plaene


def dok_fuer(typ: str, rng, kennung: str, scan: str | None, variante: str | None = None) -> Dok:
    stil = None
    if typ == "gp_versalien_zeilen":
        stil = stil_waehlen(rng, familie=rng.choice(["mono", "cour"]), groesse=rng.choice([9, 10]))
        stil.blocksatz = False
        stil.trennung = False
    dok = Dok(rng, kennung, stil=stil)
    dok.scan_geplant = scan
    dok.variante = variante
    return dok


def _anschrift(fl: Fluss, p) -> None:
    fl.zeile(m("namen", p.voll(), name_bem(p, "Anschriftfeld")))
    fl.zeile(m("strasse", p.strasse_hnr(), "Anschriftfeld"))
    fl.zeile(m("plzort", p.plz_ort(), "Anschriftfeld"))
    fl.luecke(fl.dok.stil.zeilenhoehe * 2)


def _anrede(p) -> str:
    return ("Sehr geehrter Herr " if p.geschlecht == "m" else "Sehr geehrte Frau ") + \
        m("namen", p.nachname, name_bem(p, "Anrede")) + ","


def _fluss(dok: Dok) -> Fluss:
    return Fluss(dok, 25 * MM, A4_B - 20 * MM, 20 * MM, A4_H - 20 * MM)


def typ_kfz_angebot(dok: Dok) -> str:
    """Angebotsvergleich des Maklers: "Führerschein" im Fließtext, nummerierte Liste mit Tarifen, Beginn, Beitrag –
    nichts davon ist ein Führerscheinfeld."""
    rng = dok.rng
    p = dok.person(alter=(22, 75))
    dok.hauptperson = p
    fl = _fluss(dok)
    _anschrift(fl, p)
    fl.ueberschrift(k("Angebotsvergleich Kfz-Versicherung"))
    fl.absatz(_anrede(p))
    fl.absatz("anbei unser Vergleich für Ihr Fahrzeug. Die Prüfung des Führerscheins erfolgt bei Vertragsabschluss; "
              "bitte halten Sie dafür eine Kopie bereit. Unsere Empfehlungen im Überblick:")
    (a1, t1), (a2, t2) = rng.sample(_TARIFE, 2)
    beginn = datum(dok.heute + datetime.timedelta(days=rng.randint(20, 60)))
    zeilen = ["1. " + k(f"{a1} {t1}"), "2. " + k(f"{a2} {t2}"), "3. " + k(beginn) + " " + k("Beginn aller Angebote"),
              "5. " + k(f"Beiträge ab {_betrag(rng, 280, 900)} EUR jährlich"), "8. " + k("Werkstattbindung optional")]
    for z in zeilen:
        fl.zeile(z)
    fl.luecke(dok.stil.zeilenhoehe)
    fl.absatz("Mit freundlichen Grüßen")
    dok.satz.merkmale.add("gegenprobe_fuehrerschein")
    dok.titel = "Angebotsvergleich"
    return "gp_kfz_angebot"


def typ_gwg_zahlen(dok: Dok) -> str:
    """GwG-Legitimation ("Personalausweis") mit sechsstelligen Zahlen hinter anderen Feldnamen – keine Zugangsnummer."""
    rng = dok.rng
    p = dok.person(alter=(20, 80))
    dok.hauptperson = p
    fl = _fluss(dok)
    fl.ueberschrift(k("Legitimationsprüfung nach dem Geldwäschegesetz"))
    tab = 60 * MM
    fl.kv("Kunde (Name, Vorname):", m("namen", p.liste(), name_bem(p, "GwG")), tab=tab)
    geb, gbem = dok.geburtsdatum_text(p.geburtsdatum, "punkt")
    fl.kv("Geburtsdatum:", m("geburt", geb, "GwG; " + gbem), tab=tab)
    fl.kv("Art des Ausweises:", k("Personalausweis"), tab=tab)
    fl.kv("Ausweisnummer:", m("ausweis", K.personalausweisnummer(rng, False), "GwG Ausweisnummer"), tab=tab)
    zahlen = rng.sample(range(100000, 999999), 4)
    fl.kv("Tarifnummer:", k(str(zahlen[0])), tab=tab)
    fl.kv("Versicherungssumme (EUR):", k(str(zahlen[1])), tab=tab)
    fl.kv("Kilometerstand:", k(str(zahlen[2])), tab=tab)
    fl.kv("Vermittlernummer:", k(str(zahlen[3])), tab=tab)
    fl.luecke(dok.stil.zeilenhoehe)
    fl.absatz("Bitte fügen Sie eine Kopie Ihres Personalausweises bei.")
    dok.satz.merkmale.add("gegenprobe_zugangsnummer")
    dok.titel = "GwG-Legitimation"
    return "gp_gwg_zahlen"


def typ_email_kontakt(dok: Dok) -> str:
    """E-Mail-Ausdruck: "<" im Kopf, Kontakt- und Kontozeilen ohne Satzzeichen in der Signatur. Die Kontonummer beginnt
    wie das Datum der Mail in MRZ-Schreibweise mit Prüfziffer (JJMMTT + Prüfziffer) – eine zu weite MRZ-Regel hielte
    sie für ein Geburtsdatum und schwärzte das Datum im ganzen Dokument."""
    rng = dok.rng
    p = dok.person(alter=(22, 80))
    dok.hauptperson = p
    fl = _fluss(dok)
    gesendet = dok.heute
    jjmmtt = f"{gesendet:%y%m%d}"
    konto = jjmmtt + K.mrz_pruefziffer(jjmmtt) + "".join(rng.choice("0123456789") for _ in range(3))
    fl.zeile("Von: Maklerbüro Sommer <info@sommer-makler.de>")
    fl.zeile("An: " + m("email", p.email(rng), "E-Mail-Kopf"))
    fl.zeile("Gesendet: " + k(datum(gesendet)) + " 10:15")
    fl.zeile("Betreff: Ihr neuer Vertrag")
    fl.luecke(dok.stil.zeilenhoehe)
    fl.absatz(_anrede(p))
    fl.absatz("Ihr neuer Vertrag beginnt am " + k(datum(gesendet)) + ", die erste Abbuchung erfolgt zum "
              + k(datum(gesendet)) + ".")
    fl.zeile("Mit freundlichen Grüßen")
    fl.zeile("Maklerbüro Sommer")
    vorwahl = rng.choice(["0221", "0911", "089"])
    fl.zeile(f"Tel {vorwahl} {rng.randint(10 ** 6, 10 ** 7 - 1)} Fax {vorwahl} {rng.randint(10 ** 6, 10 ** 7 - 1)}")
    fl.zeile(f"Kto {konto} Blz {rng.randint(10 ** 7, 10 ** 8 - 1)}")
    dok.satz.merkmale.add("gegenprobe_mrz")
    dok.titel = "E-Mail"
    return "gp_email_kontakt"


def _fax_kopfzeile(dok: Dok, kennung_markup: str, nummer_markup: str, form: int):
    zeit = f"{dok.heute:%d.%m.%Y} {dok.rng.randint(7, 20):02d}:{dok.rng.randint(0, 59):02d}"
    sek = dok.rng.randint(0, 59)

    def kopf(seite, nr, gesamt):
        texte = [f"{zeit}   {kennung_markup}   FAX {nummer_markup}   S. {nr:02d}/{gesamt:02d}",
                 f"{zeit}   {kennung_markup}   {nummer_markup}   S. {nr}/{gesamt}",
                 f"{dok.heute:%d/%m/%Y} {zeit[-5:]}  FROM: {kennung_markup}  {nummer_markup}  "
                 f"PAGE {nr:02d}/{gesamt:02d}",
                 f"{zeit}:{sek:02d}   {kennung_markup}   Fax {nummer_markup}   Seite {nr}/{gesamt}",
                 f"{zeit}   {kennung_markup}   {nummer_markup}   Page {nr} of {gesamt}"]
        seite.text(8 * MM, 6 * MM, texte[form % len(texte)], dok.stil.normal, 7.5, zusatz="Fax-Kopfzeile")
    dok.kopf_fuss.append(kopf)


def typ_fax_versicherer(dok: Dok) -> str:
    """Fax eines Versicherers: Markenname als Absenderkennung (bleibt), Schreiben an einen Kunden."""
    rng = dok.rng
    marke = rng.choice(_MARKEN)
    p = dok.person(alter=(25, 80))
    dok.hauptperson = p
    _fax_kopfzeile(dok, k(marke), "0" + rng.choice(["9561", "221", "89", "40"]) + " "
                   + "".join(rng.choice("0123456789") for _ in range(6)), rng.randint(0, 4))
    fl = _fluss(dok)
    fl.luecke(dok.stil.zeilenhoehe)
    _anschrift(fl, p)
    fl.ueberschrift("Ihr Schaden Nr. " + m("vertrag", K.schadennummer(rng, "HR"), "Betreff"))
    fl.absatz(_anrede(p))
    fl.absatz("die " + k(marke) + " übernimmt die Kosten der Reparatur. Bitte senden Sie uns die Rechnung zu.")
    fl.zeile("Mit freundlichen Grüßen")
    fl.zeile("Ihre " + k(marke))
    dok.satz.merkmale.update({"fax_kopfzeile", "gegenprobe_faxkopf"})
    dok.titel = "Telefax"
    return "gp_fax_versicherer"


def typ_fax_kunde(dok: Dok) -> str:
    """Fax einer Privatperson mit der Kopfzeile eines realen Geräts (ohne "Fax", mit Sekunden, englisch)."""
    rng = dok.rng
    p = dok.person(alter=(25, 85), titel_quote=0.0)
    dok.hauptperson = p
    kennung = rng.choice([_versal(f"{p.nachname} {p.vorname1}"), _versal(p.voll())])
    tel = dok.telefon(p, art=rng.choice(["din", "plus49", "strich", "gruppen"]))
    _fax_kopfzeile(dok, m("namen", kennung, name_bem(p, "Fax-Kopfzeile Absender")),
                   m("telefon", tel, "Fax-Kopfzeile Faxnummer"), rng.randint(1, 4))
    fl = _fluss(dok)
    fl.luecke(dok.stil.zeilenhoehe)
    fl.ueberschrift(k("TELEFAX"))
    fl.kv("Von:", m("namen", p.voll(), name_bem(p, "Fax-Deckblatt")), tab=30 * MM)
    fl.kv("Vertrag:", m("vertrag", K.vertragsnummer(rng, "KF"), "Fax-Deckblatt"), tab=30 * MM)
    fl.absatz("Sehr geehrte Damen und Herren, anbei die unterschriebene Erklärung zurück.")
    fl.absatz("Mit freundlichen Grüßen")
    dok.satz.merkmale.update({"fax_kopfzeile", "gegenprobe_faxkopf"})
    dok.titel = "Telefax"
    return "gp_fax_kunde"


def typ_versalien_zeilen(dok: Dok) -> str:
    """EDV-Ausdruck in Courier: Formularzeilen mit drei Feld-Wert-Zellen in Versalien (kurze Werte wie "UWE", "BONN"),
    Feldname und Wert auch in eigenen Zellen ("NAME | ZOLT | VORNAME | ILKA"), Straßen mit mehreren Leerzeichen."""
    rng = dok.rng
    st = dok.stil
    p = dok.person(alter=(25, 85))
    dok.hauptperson = p
    zweit = dok.person(alter=(25, 85))
    seite = dok.satz.neue_seite()
    g = min(st.groesse, 9.5)
    x0, dx, y = 15 * MM, 62 * MM, 22 * MM
    seite.text(x0, y, k(rng.choice(["SCHADENANZEIGE HAUSRAT", "KUNDENSTAMMBLATT", "AENDERUNGSMITTEILUNG"])), st.normal,
               g + 1)
    y += 2 * g * 1.4
    u = lambda t: _versal(t, umschrift=True)  # noqa: E731
    ort = u(p.ort.split(" (")[0])
    zeilen = [
        [("NAME: ", m("namen", u(p.nachname), name_bem(p, "Versalien-Formularzeile"))),
         ("VORNAME: ", m("namen", u(p.vorname1), "Versalien-Formularzeile")),
         ("ORT: ", m("plzort", ort, "Versalien-Formularzeile"))],
        [("NACHNAME: ", m("namen", u(zweit.nachname), name_bem(zweit, "Versalien-Formularzeile Mitversicherte"))),
         ("VORNAME: ", m("namen", u(zweit.vorname1), "Versalien-Formularzeile Mitversicherte")),
         ("GEBURTSORT: ", m("sonstiges", u(rng.choice(["KAUFBEUREN", "MEMMINGEN", "PFAFFENHOFEN", "AURICH"])),
                            "Versalien-Formularzeile Geburtsort"))],
    ]
    for zellen in zeilen:
        for i, (etikett, wert) in enumerate(zellen):
            seite.text(x0 + i * dx, y, etikett + wert, st.normal, g)
        y += g * 1.6
    # Feldname und Wert in eigenen Zellen
    drei = dok.person(alter=(25, 85))
    paare = [("NAME", m("namen", u(drei.nachname), name_bem(drei, "Versalien eigene Zelle"))),
             ("VORNAME", m("namen", u(drei.vorname1), "Versalien eigene Zelle")),
             ("ORT", m("plzort", u(drei.ort.split(" (")[0]), "Versalien eigene Zelle"))]
    for i, (etikett, wert) in enumerate(paare):
        seite.text(x0 + i * dx, y, etikett, st.normal, g)
        seite.text(x0 + i * dx + 22 * MM, y, wert, st.normal, g)
    y += g * 2.2
    strasse = (rng.choice(_STRASSEN_ZWEIWORT) + " " * rng.choice([3, 3, 4]) + rng.choice(_STRASSEN_WORT) + " "
               + str(rng.randint(1, 140)))
    seite.text(x0, y, "ANSCHRIFT" + " " * 13 + m("strasse", strasse, "EDV-Zeile; mehrere Leerzeichen"), st.normal, g)
    y += g * 1.6
    seite.text(x0, y, "PLZ/ORT" + " " * 15 + m("plzort", p.plz + " " + ort, "EDV-Zeile"), st.normal, g)
    y += g * 1.6
    geb = f"{p.geburtsdatum:%d.%m.%Y}"
    seite.text(x0, y, "KUNDEN-NR.: " + m("vertrag", K.kundennummer(rng), "EDV-Zeile"), st.normal, g)
    seite.text(x0 + dx, y, "GEB.-DATUM: " + m("geburt", geb, "EDV-Zeile"), st.normal, g)
    seite.text(x0 + 2 * dx, y, "TELEFON: " + m("telefon", dok.telefon(p), "EDV-Zeile"), st.normal, g)
    dok.satz.merkmale.update({"versalien", "gegenprobe_kopfzeile"})
    dok.titel = "EDV-Ausdruck"
    return "gp_versalien_zeilen"


def typ_steuernummer(dok: Dok) -> str:
    """Schreiben an den Makler mit der Steuernummer in einer der üblichen Schreibweisen."""
    rng = dok.rng
    p = dok.person(alter=(25, 75))
    dok.hauptperson = p
    fl = _fluss(dok)
    _anschrift(fl, p)
    fa = rng.choice(["Fürth", "Nürnberg-Süd", "Kiel", "Stuttgart II", "Leipzig I"])
    ziffern = "".join(rng.choice("0123456789") for _ in range(13))
    formen = [
        ("Steuernummer des Finanzamts " + fa + ": ", ziffern),
        ("Steuernummer, Finanzamt " + fa + ": ", f"{ziffern[:3]}/{ziffern[3:6]}/{ziffern[6:11]}"),
        ("Steuernummer: ", f"{ziffern[:3]} / {ziffern[3:6]} / {ziffern[6:11]}"),
        ("Steuernummer: ", f"{ziffern[:5]} / {ziffern[5:10]}"),
        ("St.-Nr.: ", f"{ziffern[:4]} {ziffern[4:8]} {ziffern[8:13]}"),
        ("Steuernummer beim FA " + fa + ": ", f"{ziffern[:4]}/{ziffern[4:7]}/{ziffern[7:12]}"),
    ]
    etikett, wert = rng.choice(formen)
    fl.ueberschrift(k("Angaben für den Gewerbe-Versicherungsantrag"))
    fl.absatz(_anrede(p))
    fl.absatz("für den Antrag benötigen Sie noch meine Steuernummer. " + etikett
              + m("steuernr", wert, "Steuernummer; " + etikett.strip(": ")) + ".")
    fl.zeile("Mit freundlichen Grüßen")
    fl.zeile(m("namen", p.voll(), name_bem(p, "Unterschrift")))
    dok.satz.merkmale.add("gegenprobe_steuernummer")
    dok.titel = "Schreiben"
    return "gp_steuernummer"


def typ_ereignisort(dok: Dok) -> str:
    """Gescannte Kfz-Schadenanzeige: Ereignisorte und Formulartexte hinter Feldnamen ("Ort des Schadens", "Ort der
    Besichtigung", "Werkstatt: Ihrer Wahl", "3. Verletzte") – keine Anschrift einer Person."""
    rng = dok.rng
    p = dok.person(alter=(22, 80))
    dok.hauptperson = p
    fl = _fluss(dok)
    fl.ueberschrift(k("Kfz-Schadenanzeige"))
    tab = 55 * MM
    fl.kv("1. Versicherungsnehmer:", m("namen", p.voll(), name_bem(p, "Schadenanzeige")), tab=tab)
    fl.kv("Anschrift:", m("strasse", p.strasse_hnr(), "Schadenanzeige") + ", "
          + m("plzort", p.plz_ort(), "Schadenanzeige"), tab=tab)
    fl.kv("Ort des Schadens:", k(rng.choice(["Parkplatz Rewe-Markt", "Tiefgarage Altstadt", "Parkhaus am Bahnhof"])),
          tab=tab)
    fl.kv("2. Ort (Land, Ort, Straße)", k("3. Verletzte: nein"), tab=tab)
    fl.kv("Ort der Besichtigung:", k(rng.choice(["Werkstatt Ihrer Wahl", "Parkplatz vor dem Haus"])), tab=tab)
    fl.kv("Werkstatt:", k("Ihrer Wahl"), tab=tab)
    fl.kv("Gutachter:", k("Ihrer Wahl"), tab=tab)
    fl.kv("Schadentag:", k(datum(dok.heute - datetime.timedelta(days=rng.randint(3, 20)))), tab=tab)
    dok.satz.merkmale.add("gegenprobe_ereignisort")
    dok.titel = "Kfz-Schadenanzeige"
    return "gp_ereignisort"


def typ_td2_ausweis(dok: Dok) -> str:
    """Kopie eines vorläufigen Personalausweises (TD2-MRZ, 2 x 36 Zeichen)."""
    dok.variante = "td2"
    typ_personalausweis(dok)
    dok.satz.merkmale.add("gegenprobe_td2")
    return "gp_td2_ausweis"


TYPEN_GEGENPROBEN = {
    "gp_kfz_angebot": typ_kfz_angebot,
    "gp_gwg_zahlen": typ_gwg_zahlen,
    "gp_email_kontakt": typ_email_kontakt,
    "gp_fax_versicherer": typ_fax_versicherer,
    "gp_fax_kunde": typ_fax_kunde,
    "gp_versalien_zeilen": typ_versalien_zeilen,
    "gp_steuernummer": typ_steuernummer,
    "gp_ereignisort": typ_ereignisort,
    "gp_td2_ausweis": typ_td2_ausweis,
}
assert list(TYPEN_GEGENPROBEN) == TYPEN_REIHENFOLGE
