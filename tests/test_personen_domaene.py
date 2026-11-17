"""Personen, Geburtsdaten und Namenserkennung aus der Domänen-Durchsicht (Runde 5, Paket „Personen“).

Je Befund der Durchsicht: die Zeilen aus den Falldateien (Lecks bzw. Über-Schwärzung), eine abgewandelte
Schreibweise und Gegenproben gegen Über-Schwärzung (Feld-Etiketten, Überschriften, Firmen, Produkte, Orte, Beträge,
Daten, Fachwörter). Wo die Erkennung etwas neu kennt, prüft ein Test auch die Selbstkontrolle (restrisiko.py): bliebe
der Wert lesbar, muss sie ihn melden. Alle Personen, Nummern und Anschriften sind erfunden."""

import pytest

from anonymisierer import muster, wissen
from anonymisierer.analyse import analysiere_text
from anonymisierer.restrisiko import pruefe_text
from conftest import braucht_modell

ALLE = {k for k, _, _, _, an in muster.KATEGORIEN if an}


# ----------------------------------------------------------------------
# Hilfsfunktionen
# ----------------------------------------------------------------------
def _funde(text, profil="hoch"):
    return analysiere_text(text, ALLE, [], [], profil=profil)


def _geschwaerzt(funde, kategorie=None) -> set:
    """Texte aller angehakten Stellen (optional nur einer Kategorie)."""
    return {st["text"] for f in funde if kategorie is None or f["kategorie"] == kategorie
            for st in f["stellen"] if st.get("an", True)}


def _namen(text, profil="hoch") -> set:
    return _geschwaerzt(_funde(text, profil), "namen")


def _deckt(stellen: set, wert: str) -> bool:
    """Liegt `wert` in einer der Stellen?"""
    return any(wert in s for s in stellen)


def _verdacht(text, **kw) -> list:
    return [v.text for v in pruefe_text(text, **kw)]


def _gemeldet(text, wert, **kw) -> bool:
    return any(wert in t or (len(t) >= 3 and t in wert) for t in _verdacht(text, **kw))


# ----------------------------------------------------------------------
# Rollen-Etiketten: hinter jedem Personen-Etikett steht eine Person (Befunde 28, 49, 16, 45, 9, 8)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("zeile, name", [
    ("Leasingnehmerin: Kriemhild Ottenschläger", "Ottenschläger"),          # Befund 28 (Prüferzeile)
    ("Leasingnehmer/in: Jorinde Wittmannsgruber", "Wittmannsgruber"),
    ("Zusatzfahrer: Kriemhild Ottenschläger", "Ottenschläger"),
    ("Sozia: Jorinde Wittmannsgruber", "Wittmannsgruber"),
    ("Hauptfahrerin: Ortrun Haberlander", "Haberlander"),
    ("Zweitfahrer(in): Okke Brünnhuber", "Brünnhuber"),
    ("Gegner: Felsberger", "Felsberger"),                                   # Befund 49
    ("Beklagter: Felsberger", "Felsberger"),
    ("Prozessgegner: Riedlinger", "Riedlinger"),
    ("Antragsgegner: Riedlinger", "Riedlinger"),
    ("Klägerin: Oberleitner", "Oberleitner"),
    ("Gegnerin (Name, Anschrift): Riedlinger", "Riedlinger"),
    ("Stammversicherter: Albin Zwickl", "Zwickl"),                          # Befund 16
    ("Hauptversicherte(r): Konrad Hiltl", "Hiltl"),
    ("Rechnungsempfänger: Ilse Wohlgemuth-Brandl", "Wohlgemuth-Brandl"),    # Befund 8
    ("Reitbeteiligung: Lena Kortmann", "Kortmann"),
])
def test_befund_28_49_rollen_etiketten_vor_unbekannten_namen(zeile, name):
    assert _deckt(_namen(zeile), name), zeile


@pytest.mark.parametrize("zeile, name", [
    ("Leasingnehmerin: Kriemhild Ottenschläger", "Ottenschläger"),
    ("Sozius: Jendrik Wimmersberger", "Wimmersberger"),
    ("Gegner: Felsberger", "Felsberger"),
    ("Antragsgegnerin: Riedlinger", "Riedlinger"),
])
def test_befund_28_49_selbstkontrolle_kennt_die_rollen_etiketten(zeile, name):
    assert _gemeldet(zeile, name)


@pytest.mark.parametrize("zeile, wert", [
    ("Gegner: Wohnbau GmbH", "Wohnbau"),                    # juristische Person bleibt
    ("Gegnerische Versicherung: Allianz", "Allianz"),        # kein Personenfeld
    ("Kläger: unbekannt", "unbekannt"),
    ("Leasingnehmer: Muster Leasing GmbH", "Muster Leasing"),
])
def test_befund_28_49_gegenproben_firmen_und_fuellwoerter(zeile, wert):
    assert not _deckt(_namen(zeile), wert)


@braucht_modell
@pytest.mark.parametrize("zeilen, etiketten", [
    (["Stammversicherter: Albin Zwickl", "Hauptversicherter: Konrad Hiltl"],
     ["Stammversicherter", "Hauptversicherter"]),                                        # Befund 16
    (["Einweisender Arzt: Dr. Petra Ullrich", "Erstbehandelnder Arzt: Dr. Jens Abendroth"],
     ["Einweisender", "Erstbehandelnder"]),
    (["Diebstahlanzeige Kfz", "Versicherungsnehmer: Theodor Wimmersberger", "Hauptfahrer: Fokko Grübelhuber",
      "Sozius: Jendrik Wimmersberger"], ["Diebstahlanzeige", "Hauptfahrer", "Sozius"]),  # Befund 45
    (["Antrag Kfz-Versicherung – Fahrerangaben", "Hauptfahrerin: Ortrun Haberlander"], ["Hauptfahrerin"]),
])
def test_befund_16_45_etikett_und_ueberschrift_sind_kein_name(zeilen, etiketten):
    text = "\n".join(zeilen)
    namen = _namen(text)
    for e in etiketten:
        assert not _deckt(namen, e), (e, namen)
    for name in ("Zwickl", "Hiltl", "Ullrich", "Abendroth", "Wimmersberger", "Grübelhuber", "Haberlander"):
        if name in text:
            assert _deckt(namen, name), (name, namen)


# ----------------------------------------------------------------------
# "Name des/der <Rolle>" allgemein abgeleitet (Befund 57)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("etikett", ["Name des Hundehalters", "Name der Geschädigten", "NAME DES TIERHALTERS",
                                     "Vorname der Mieterin", "Name des mitversicherten Kindes",
                                     "Unterschrift des Leasingnehmers", "Nachname des Beklagten"])
def test_befund_57_name_des_rolle_ist_personen_etikett(etikett):
    assert wissen.index("etiketten_person").eintrag_fuer(etikett) is not None
    assert [v.text for v in wissen.finde(f"{etikett}: Felsberger", "etiketten_person")] == [etikett]


@pytest.mark.parametrize("etikett", ["Name des Hundes", "Name der Bank", "Name des Pferdes", "Name der Schule"])
def test_befund_57_name_des_sache_ist_kein_abgeleitetes_etikett(etikett):
    assert wissen.index("etiketten_person").eintrag_fuer(etikett) is None


@pytest.mark.parametrize("zeile, name", [
    ("Name des Hundehalters: Felsberger        Vorname: Rainer", "Felsberger"),     # Prüferzeile
    ("Name der Geschädigten: Riedlinger        Vorname: Anna", "Riedlinger"),
    ("Name des Tierhalters: Kranzbühler", "Kranzbühler"),
])
def test_befund_57_name_des_rolle_erkannt(zeile, name):
    assert _deckt(_namen(zeile), name)


@pytest.mark.parametrize("zeile, name", [
    ("Name des Hundehalters: Felsberger        Vorname: [PERSON A]", "Felsberger"),
    ("Name der Geschädigten: Riedlinger        Vorname: [PERSON A]", "Riedlinger"),
    ("Name: Felsberger        Vorname: [PERSON A]", "Felsberger"),
])
def test_befund_57_selbstkontrolle_etikett_je_feld(zeile, name):
    assert _gemeldet(zeile, name, platzhalter=["[PERSON A]"])


# ----------------------------------------------------------------------
# Geburtsdaten ohne Stichwort im Familien-/Versichertenkontext (Befunde 2, 3, 10) und Gegenprobe Befund 14
# ----------------------------------------------------------------------
@pytest.mark.parametrize("zeilen, daten", [
    (["Kind 2: Bastian Leutgeb, 30.06.2018", "Mitversicherte Person: Oskar Hufnagl, 21.11.2019"],
     ["30.06.2018", "21.11.2019"]),                                                     # Befund 2 (Prüferzeilen)
    (["Familienversicherung - Änderungsmeldung", "Tochter: Mia Schöllhorn, 14.08.2017"], ["14.08.2017"]),
    (["Familienversicherung - mitversicherte Angehörige", "Kinder: Ben (02.05.2019) und Lotta (17.10.2021)"],
     ["02.05.2019", "17.10.2021"]),
    (["Reiserücktrittsversicherung", "Mitreisendes Kind: Brenner, Lina, 05.05.2019"], ["05.05.2019"]),
    (["Kinder:", "1.\t\tLiv Ostermeier\t\t09.09.2017", "2.\t\tJakob Ostermeier\t\t13.01.2020"],
     ["09.09.2017", "13.01.2020"]),                                                     # Befund 3
    (["Mitzuversichernde Kinder:", "Lina Brenner\t\t05.05.2019\t\tTochter", "Jonte Brenner\t\t22.07.2021\t\tSohn"],
     ["05.05.2019", "22.07.2021"]),
    (["Reiserücktrittsversicherung - versicherte Reisende",
      "Reisende: Kranich, Detlef, 12.04.1969; Kranich, Jona, 17.02.2014;", "Kranich, Emma, 05.05.2019"],
     ["12.04.1969", "17.02.2014", "05.05.2019"]),                                       # Befund 10
    (["Gruppenreiseversicherung - Teilnehmerliste",
      "Versicherte Personen: Seidl, Anton, 03.07.1962; Seidl, Maria, 21.01.1965"], ["03.07.1962", "21.01.1965"]),
    (["Zahnzusatz Junior", "Mitversichert ist unser Sohn Lukas Schöllhorn (04.03.2016)."], ["04.03.2016"]),
    (["Ehegatte: Sven Tannhäuser * 22.11.1979"], ["22.11.1979"]),
])
def test_befund_2_3_10_geburtsdatum_im_familienkontext(zeilen, daten):
    geburt = _geschwaerzt(_funde("\n".join(zeilen)), "geburt")
    for d in daten:
        assert d in geburt, (d, geburt)


@pytest.mark.parametrize("zeilen, datum", [
    (["Angaben zu Arztbesuchen der letzten 10 Jahre", "Dr. Ute Kranzfelder, 03.11.2012: Meniskusoperation links"],
     "03.11.2012"),                                                                     # Befund 14 (Prüferzeile)
    (["Gesundheitsfragen - Erläuterungen", "Dr. med. Sabine Ortlieb, 21.03.2015: Arthroskopie Knie rechts"],
     "21.03.2015"),
    (["Angaben zu Arztbesuchen", "Dr. Jens Abendroth, 14.05.2024: Kontrolle ohne Befund"], "14.05.2024"),
    (["Kinder:", "Dr. Holger Sauerbier\t\t15.08.2025\t\t214,50 €"], "15.08.2025"),
    (["Kinder:", "Brille Lina\t\t15.08.2025\t\t214,50 €"], "15.08.2025"),
    (["Tochter: Mia, Vertragsbeginn 01.09.2023"], "01.09.2023"),
    (["Kinder: Lea (Zahnzusatz seit 01.01.2024)"], "01.01.2024"),
    (["Ehefrau Anna Weber, Unfall am 03.03.2024"], "03.03.2024"),
    (["Kinder: 2 (Stand 01.01.2026)"], "01.01.2026"),
    (["Kindergeld: Lina Brenner, ausgezahlt 15.03.2024"], "15.03.2024"),
    (["Rechnung Praxis Dr. Fuchsberger", "Datum\t\tGeb.-Nr.\t\tBetrag", "09.09.2025\t\t0410\t\t19,82 €"],
     "09.09.2025"),
    (["Zahnärztliche Rechnung", "Datum\t\tGeb.-Ziffer\t\tBetrag", "16.10.2025\t\t2120\t\t104,83 €"], "16.10.2025"),
])
def test_befund_14_behandlungs_vertrags_und_rechnungsdaten_bleiben(zeilen, datum):
    geburt = _geschwaerzt(_funde("\n".join(zeilen)), "geburt")
    assert datum not in geburt, geburt


@pytest.mark.parametrize("zeile, datum", [
    ("Geb. 03.11.1975", "03.11.1975"), ("Geb.-Datum: 03.11.1975", "03.11.1975"),
    ("Anna Weber, geb. 14.07.2015", "14.07.2015"),
])
def test_befund_14_geburtsdatum_hinter_geb_bleibt_erkannt(zeile, datum):
    assert datum in _geschwaerzt(_funde(zeile), "geburt")


@pytest.mark.parametrize("zeilen, datum", [
    (["Kind 2: [PERSON A], 30.06.2018"], "30.06.2018"),
    (["Familienversicherung", "Tochter: [PERSON A], 14.08.2017"], "14.08.2017"),
    (["Kinder: [P A] (02.05.2019) und [P B] (17.10.2021)"], "17.10.2021"),
    (["Kinder:", "1.\t\t[PERSON A]\t\t09.09.2017"], "09.09.2017"),
    (["Mitreisendes Kind: [PERSON B], 05.05.2019"], "05.05.2019"),
    (["Kinder: Ben (02.05.2019)"], "02.05.2019"),
])
def test_befund_2_3_selbstkontrolle_meldet_kinder_geburtsdatum(zeilen, datum):
    text = "\n".join(zeilen)
    platzhalter = [p for p in ("[PERSON A]", "[PERSON B]", "[P A]", "[P B]") if p in text]
    assert _gemeldet(text, datum, platzhalter=platzhalter)


@pytest.mark.parametrize("zeilen, datum", [
    (["Rechnung vom 14.05.2024", "Kind 2: [PERSON A]"], "14.05.2024"),
    (["Dr. [PERSON A], 14.05.2024: Kontrolle ohne Befund", "Tochter: [PERSON B]"], "14.05.2024"),
    (["Kinder:", "Brille\t\t15.08.2025\t\t214,50 €"], "15.08.2025"),
    (["Schaden vom 03.03.2024, Kind 2 war nicht beteiligt"], "03.03.2024"),
    (["Versicherungsnehmer: [PERSON A], 01.09.2023"], "01.09.2023"),
])
def test_befund_2_3_selbstkontrolle_gegenproben_ohne_familienperson(zeilen, datum):
    text = "\n".join(zeilen)
    platzhalter = [p for p in ("[PERSON A]", "[PERSON B]") if p in text]
    assert not _gemeldet(text, datum, platzhalter=platzhalter)


# ----------------------------------------------------------------------
# Geburt als Ereignis (Befund 4) und Geburtsjahr (Befund 5)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("zeilen, datum", [
    (["Kindernachversicherung", "Geburt des Kindes am 02.10.2026", "Name des Kindes: Emil Hufnagl"], "02.10.2026"),
    (["Betreff: Kindernachversicherung", "hiermit zeige ich die Geburt unserer Tochter am 14.09.2026 an"],
     "14.09.2026"),
    (["Anmeldung zur Kindernachversicherung", "Entbindung am 21.08.2026 im Klinikum Traunstein"], "21.08.2026"),
    (["Kindernachversicherung", "Unsere Tochter Frieda wurde am 14.09.2026 geboren."], "14.09.2026"),
    (["Kindernachversicherung", "Tag der Geburt: 02.10.2026"], "02.10.2026"),
])
def test_befund_4_geburt_als_ereignis(zeilen, datum):
    text = "\n".join(zeilen)
    assert datum in _geschwaerzt(_funde(text), "geburt")
    assert _gemeldet(text, datum)


@pytest.mark.parametrize("zeile, datum", [
    ("Geburtsvorbereitungskurs am 03.11.2025", "03.11.2025"),
    ("Geburtstermin laut Mutterpass: 15.12.2026", "15.12.2026"),
    ("Die Geburt ist voraussichtlich am 15.12.2026", "15.12.2026"),
    ("Geburtshilfe: Rechnung vom 03.11.2025", "03.11.2025"),
])
def test_befund_4_gegenproben_komposita_und_kuenftige_daten(zeile, datum):
    assert datum not in _geschwaerzt(_funde(zeile), "geburt")


@pytest.mark.parametrize("zeile, jahr", [
    ("Geburtsjahr: 1983\t\tEintrittsalter: 43", "1983"),
    ("Geburtsjahr der versicherten Person: 1979", "1979"),
    ("Geb.-Jahr 1961", "1961"),
])
def test_befund_5_geburtsjahr(zeile, jahr):
    assert jahr in _geschwaerzt(_funde(zeile), "geburt")
    assert _gemeldet(zeile, jahr)


@pytest.mark.parametrize("zeile, wert", [
    ("Baujahr: 1983", "1983"), ("Beitragsjahr 2024", "2024"), ("Eintrittsalter: 43", "43"),
    ("Geburtsjahrgänge 1950 bis 1960 erhalten Rabatt", "1950"),
])
def test_befund_5_gegenproben_baujahr_alter(zeile, wert):
    assert wert not in _geschwaerzt(_funde(zeile), "geburt")


# ----------------------------------------------------------------------
# Parteien im Kurzrubrum (Befunde 49, 61), Rollen im Satz und Wohnungslagen (Befund 50)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("zeilen, namen", [
    (["Ihr VN: Josef Kranzbühler", "In Sachen Kranzbühler ./. Felsberger wegen Mietminderung",
      "der Vermieter Felsberger verweigert die Beseitigung des Schimmels."], ["Felsberger"]),     # Befund 49
    (["Amtsgericht Ebersberg", "In dem Rechtsstreit Kranzbühler, Josef ./. Felsberger, Rainer"],
     ["Kranzbühler", "Felsberger"]),                                                         # Befund 61
    (["Weber ./. Riedlinger wegen Nachbarschaftsstreit"], ["Weber", "Riedlinger"]),
    (["In dem Rechtsstreit Kranzbühler, Josef gegen Felsberger, Rainer wird Termin bestimmt."],
     ["Kranzbühler, Josef", "Felsberger, Rainer"]),
])
def test_befund_49_61_parteien_im_kurzrubrum(zeilen, namen):
    gefunden = _namen("\n".join(zeilen))
    for n in namen:
        assert _deckt(gefunden, n), (n, gefunden)
    assert not any("gegen" in g for g in gefunden), gefunden        # keine Spanne über "gegen" hinweg


@pytest.mark.parametrize("zeile, wert", [
    ("Müller ./. Allianz Versicherungs-AG", "Allianz"),
    ("Kranzbühler ./. Stadt Ebersberg", "Stadt"),
    ("Wohnbau GmbH ./. Riedlinger", "Wohnbau"),
])
def test_befund_49_rubrum_gegenproben_firmen_und_behoerden(zeile, wert):
    assert not _deckt(_namen(zeile), wert)


@pytest.mark.parametrize("zeile, name", [
    ("In Sachen Kranzbühler ./. Felsberger wegen Mietminderung", "Felsberger"),
    ("Gegnerin: Riedlinger", "Riedlinger"),
])
def test_befund_49_selbstkontrolle_parteien(zeile, name):
    assert _gemeldet(zeile, name)


@pytest.mark.parametrize("zeilen, namen", [
    (["Mein Sohn schoss den Ball in das Wohnzimmerfenster unseres Nachbarn Felsberger."], ["Felsberger"]),
    (["Bei Felsberger im 1. OG ist das Wasser durch die Decke getreten.",
      "Betroffen sind die Wohnungen EG links (Hackenschmied) und 1. OG links (Rauchenberger)."],
     ["Felsberger", "Hackenschmied", "Rauchenberger"]),
    (["Die Mieterin Riedlinger aus dem Erdgeschoss war Zeugin."], ["Riedlinger"]),
    (["Beim Nachbarn Unterholzner sind Decke und Parkett beschädigt."], ["Unterholzner"]),
    (["Laut Aussage des Vermieters Oberleitner war die Leitung alt."], ["Oberleitner"]),
])
def test_befund_50_gebeugte_rollen_und_wohnungslagen(zeilen, namen):
    text = "\n".join(zeilen)
    gefunden = _namen(text)
    for n in namen:
        assert _deckt(gefunden, n), (n, gefunden)
        assert _gemeldet(text, n), n


@pytest.mark.parametrize("zeile, wert", [
    ("Wir haben dem Nachbarn Bescheid gegeben.", "Bescheid"),
    ("Er hat dem Nachbarn Wasser abgegraben.", "Wasser"),
    ("Beim Nachbarn Regen gemessen.", "Regen"),
    ("Bei Regen im 1. OG tropft es.", "Regen"),
    ("Betroffen ist das EG links (Küche).", "Küche"),
    ("Die Mieterin Anna zahlt pünktlich.", "zahlt"),
])
def test_befund_50_gegenproben_substantive_hinter_rollen(zeile, wert):
    assert not _deckt(_namen(zeile), wert)
    assert not _gemeldet(zeile, wert)


# ----------------------------------------------------------------------
# Dienstgrade und Amtsbezeichnungen vor bzw. hinter Namen (Befund 54), RA ohne Punkt (Befund 61)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("zeilen, name", [
    (["Polizeiinspektion Poing", "Rückfragen richten Sie bitte an KHKin Sedlmayr (K 33)."], "Sedlmayr"),
    (["Ihre Anzeige wurde von PHKin Reithmeier aufgenommen."], "Reithmeier"),
    (["Ausgefertigt", "Eibl, JAng", "Urkundsbeamtin der Geschäftsstelle"], "Eibl"),
    (["Kollmannsberger, JOSin", "als Urkundsbeamtin der Geschäftsstelle"], "Kollmannsberger"),
    (["Für Rückfragen steht Ihnen KOK Unterholzner zur Verfügung."], "Unterholzner"),
    (["Sachbearbeitung: POM Gstettner, PI Grafing"], "Gstettner"),
    (["Gegnerischer Anwalt: RA Rauchenberger, Ebersberg"], "Rauchenberger"),
    (["Rechtspflegerin Oberprieler"], "Oberprieler"),
])
def test_befund_54_61_dienstgrad_amtsbezeichnung_vor_namen(zeilen, name):
    text = "\n".join(zeilen)
    gefunden = _namen(text)
    assert _deckt(gefunden, name), gefunden
    assert _gemeldet(text, name)
    assert not any(g in ("KOK", "JAng", "Ausgefertigt") for g in gefunden), gefunden


@pytest.mark.parametrize("zeile, wert", [
    ("Abfahrt um 3 PM Abfahrt laut Plan", "Abfahrt"), ("KK Barmer, Mitgliedsnummer folgt", "Barmer"),
    ("StA München, Az. 12 Js 345/23", "München"), ("RD Schadenabteilung", "Schadenabteilung"),
])
def test_befund_54_gegenproben_kuerzel_vor_sachen(zeile, wert):
    assert not _deckt(_namen(zeile), wert)


# ----------------------------------------------------------------------
# Name in Versalien mit Schrägstrich (Befund 9, Teil Person), Initialen in Listen (Befund 86)
# ----------------------------------------------------------------------
def test_befund_9_passagiername_nachname_schraegstrich_vorname():
    namen = _namen("PASSENGER: KRANICH/BIRGIT MRS\nTICKET NUMBER: 220 2345678901")
    assert _deckt(namen, "KRANICH") and _deckt(namen, "BIRGIT"), namen
    assert not any("TICKET" in n or "MRS" in n for n in namen), namen


@pytest.mark.parametrize("zeilen, name", [
    (["VSNR\t\tVersicherungsnehmer\t\tProdukt", "HR-7740-2291-05\t\tKraxenberger, Wendelin\t\tHausrat Plus",
      "PHV-0071-4471\t\tOberprieler, S.\t\tPrivathaftpflicht", "U-2026-5512\t\tPichlmeier, N.\t\tUnfall Komfort"],
     "Oberprieler"),                                                                      # Befund 86 (Prüferzeilen)
    (["VSNR\t\tVersicherungsnehmer\t\tProdukt", "HR-7740-2291-05\t\tKraxenberger, Wendelin\t\tHausrat Plus",
      "PHV-0071-4471\t\tOberprieler, S.\t\tPrivathaftpflicht", "U-2026-5512\t\tPichlmeier, N.\t\tUnfall Komfort"],
     "Pichlmeier"),
    (["Bestandsliste", "1\t\tGstettner, A.\t\tKV 12/3456789-0"], "Gstettner"),
])
def test_befund_86_nachname_mit_initiale_in_listen(zeilen, name):
    assert _deckt(_namen("\n".join(zeilen)), name)


@pytest.mark.parametrize("zeile, wert", [
    ("Tarif, A. gilt ab sofort", "Tarif"), ("Hausrat, S.\t\tx", "Hausrat"), ("München, S. 12", "München"),
])
def test_befund_86_gegenproben_sachwort_mit_buchstabe(zeile, wert):
    assert not _deckt(_namen(zeile), wert)


# ----------------------------------------------------------------------
# Fachwörter, Marken, Modelle, Tiere, Firmen und Partizipien sind keine Namen (Befunde 15, 18, 42, 43, 60, 64, 65,
# 82, 92, 104)
# ----------------------------------------------------------------------
@braucht_modell
@pytest.mark.parametrize("zeilen, wert", [
    (["Behandlung: Baker-Zyste rechts, Dupuytren-Kontraktur links, Morbus Scheuermann"], "Scheuermann"),  # 15
    (["Chronische Lumbalgie seit 2019"], "Lumbalgie"),
    (["Rezidivierende Lumboischialgie"], "Lumboischialgie"),
    (["Vermieter: Sixt GmbH & Co Autovermietung KG"], "Sixt"),                                          # 42
    (["Vermieter: Europcar Autovermietung GmbH"], "Europcar"),
    (["Werkstatt: A.T.U Auto-Teile-Unger GmbH & Co. KG"], "Unger"),
    (["Halter: Stadtwerke Rosenheim GmbH & Co. KG"], "Rosenheim"),
    (["Wohnwagen Tabbert Rossini 540"], "Rossini"),                                                    # 43
    (["Fahrzeug: Dacia Logan MCV"], "Logan"),
    (["E-Bikes: Riese & Müller, Haibike, Kalkhoff, Gazelle"], "Kalkhoff"),
    (["Mofa Simson"], "Simson"),
    (["Hund\t\tCavalier King Charles Spaniel\t\tHündin"], "Charles"),                                  # 60
    (["Hund\t\tDobermann\t\tRüde"], "Dobermann"),
    (["Rasse: Jack Russell Terrier"], "Russell"),
    (["Geschlecht: Wallach"], "Wallach"),
    (["Abstammung: Vater: Sandro Hit / Muttervater: Donnerhall"], "Sandro"),
    (["Name des Pferdes: Don Camillo"], "Camillo"),
    (["Rasse: Trakehner, Geschlecht: Stute, Abstammung: v. Gribaldi a.d. Kassandra"], "Kassandra"),
    (["Gasgrill\t\tWeber Genesis II E-315"], "Gasgrill"),                                              # 64
    (["Akkuschrauber\t\tBosch GSR 18V-55"], "Bosch"),
    (["Armbanduhr Junghans Max Bill"], "Junghans"),
    (["Wechselrichter: Fronius Symo 10.0-3-M"], "Fronius"),
    (["Warmwasser: Stiebel Eltron DHB-E 18 Sli"], "Stiebel"),
    (["Durchlauferhitzer: AEG DDLE 18 Basis"], "DDLE"),
    (["Patientenbesitzer: Familie Feldhoff"], "Patientenbesitzer"),                                    # 65
    (["Ausgefertigt", "Beglaubigt"], "Ausgefertigt"),
    (["Ausgefertigt", "Beglaubigt"], "Beglaubigt"),
    (["Hergang: Beim Fußballspielen schoss mein Sohn Lukas den Ball in die Scheibe."], "Ball"),
    (["Hergang: Beim Fußballspielen schoss mein Sohn Lukas den Ball in die Scheibe."], "Hergang"),
    (["Festgesetzt werden: Einkommensteuer 4.812,00 EUR"], "Festgesetzt"),                             # 82
    (["Bruttoarbeitslohn\t\t41.250,00 EUR"], "Bruttoarbeitslohn"),
    (["Anlagen: Bescheid.pdf"], "Bescheid"),
    (["Zweitkonto der Ehefrau: AT84 1200 0100 0012 3456"], "Zweitkonto"),
    (["Best regards, Irmtraud Ölschläger"], "regards"),
    (["\t\tMandatsref. MV-0815-4711-01"], "Mandatsref"),
    (["Legitimiert durch Personalausweis"], "Legitimiert"),
    (["Kontaktwege laut Kundenbogen"], "Kundenbogen"),
    (["Oldtimer: amtl. Kennz. HH-XY 77H"], "Kennz"),                                                   # 104
    (["Kontakt: Instagram @kranich_reisen"], "Instagram"),
    (["Versicherer\t\tTarif\t\tDeckungssumme", "Haftpflichtkasse\t\tEinfach Komplett\t\t50 Mio. EUR"], "Mio"),  # 92
    (["Produkt\t\tBeitrag", "Krankenzusatz\t\t48,20"], "Krankenzusatz"),
    (["Hotel: Hotel Cala Ratjada Mar, 7 Nächte, Doppelzimmer Meerblick", "Rückflug: 19.07.2026 EW 7583"],
     "Meerblick"),                                                                                      # 18
    (["Hotel: Hotel Cala Ratjada Mar, 7 Nächte, Doppelzimmer Meerblick", "Rückflug: 19.07.2026 EW 7583"],
     "Rückflug"),
])
def test_befunde_ner_sachwoerter_sind_keine_namen(zeilen, wert):
    assert not _deckt(_namen("\n".join(zeilen)), wert)


@braucht_modell
@pytest.mark.parametrize("zeilen, name", [
    (["Best regards, Irmtraud Ölschläger"], "Ölschläger"),
    (["Patientenbesitzer: Familie Feldhoff"], "Feldhoff"),
    (["Reitbeteiligung: Lena Kortmann (Mitreiterin)"], "Kortmann"),
    (["Hergang: Beim Fußballspielen schoss mein Sohn Lukas den Ball in die Scheibe."], "Lukas"),
    (["Kanzlei Dr. Moosreiner & Kollegen - Rechtsanwälte - Fachanwälte"], "Moosreiner"),
])
def test_befunde_ner_gegenproben_personen_bleiben(zeilen, name):
    assert _deckt(_namen("\n".join(zeilen)), name)


# ----------------------------------------------------------------------
# Unfallort: Gattungswörter vor dem Ort überspringen (Befund 18)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("zeile, ort, gattung", [
    ("Unfallort: Turnhalle der Mittelschule Erding", "Erding", "Turnhalle"),
    ("Unfallort: Skigebiet Sudelfeld, Bayrischzell", "Sudelfeld", "Skigebiet"),
    ("Schadenort: Tiefgarage Parkhaus Nord, Lindenstraße 4", "Lindenstraße 4", "Tiefgarage"),
])
def test_befund_18_unfallort_hinter_gattungswort(zeile, ort, gattung):
    stellen = _geschwaerzt(_funde(zeile))
    assert _deckt(stellen, ort), stellen
    assert not any(gattung in s for s in stellen), stellen
    assert _gemeldet(zeile, ort.split()[0])


@pytest.mark.parametrize("zeile, ort", [("Unfallort: Erding", "Erding"), ("Wohnort: Holzkirchen", "Holzkirchen")])
def test_befund_18_gegenprobe_ort_allein_bleibt_erkannt(zeile, ort):
    assert _deckt(_geschwaerzt(_funde(zeile)), ort)


def test_befund_18_nur_gattungswoerter_kein_ort_kein_verdacht():
    zeile = "Unfallort: Turnhalle der Grundschule"
    assert not _geschwaerzt(_funde(zeile), "plzort")
    assert not _verdacht(zeile)


# ----------------------------------------------------------------------
# Kundenzeile mit Personen-Etikett unter einer Firmenzeile (Befunde 8, 58)
# ----------------------------------------------------------------------
def _anschrift_angehakt(text) -> dict:
    return {st["text"]: st.get("an", True) for f in _funde(text) if f["kategorie"] in ("strasse", "plzort")
            for st in f["stellen"]}


@pytest.mark.parametrize("zeilen, anschrift", [
    (["Privatärztliche Verrechnungsstelle Südbayern GmbH",
      "Rechnungsempfänger: Ilse Wohlgemuth-Brandl, Am Mühlbach 12, 83646 Bad Tölz"], "Am Mühlbach 12"),  # Befund 8
    (["Kreisklinik Altötting gGmbH", "Rechnungsanschrift: Anton Seidl, Fichtenstr. 9, 94036 Passau"],
     "Fichtenstr. 9"),
    (["Antrag Hundekrankenversicherung", "Tierhalter: Sabine Ollenbrock, Am Mühlbach 3, 85570 Markt Schwaben"],
     "Am Mühlbach 3"),                                                                                     # Befund 58
])
def test_befund_8_58_kundenanschrift_hinter_personen_etikett(zeilen, anschrift):
    stellen = _anschrift_angehakt("\n".join(zeilen))
    assert stellen.get(anschrift) is True, stellen


@pytest.mark.parametrize("zeilen, anschrift", [
    (["Privatärztliche Verrechnungsstelle Südbayern GmbH",
      "Rechnungssteller: Dr. Hans Huber, Hauptstraße 1, 80331 München"], "Hauptstraße 1"),
    (["Kreisklinik Altötting gGmbH", "Ansprechpartner: Anton Seidl, Fichtenstr. 9, 94036 Passau"], "Fichtenstr. 9"),
])
def test_befund_8_58_gegenproben_anschrift_des_ausstellers_bleibt_firmenanschrift(zeilen, anschrift):
    assert _anschrift_angehakt("\n".join(zeilen)).get(anschrift) is False


# ----------------------------------------------------------------------
# USt-IdNr. von Einzelkaufleuten und Freiberuflern (Befund 77)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, nummer", [
    ("Brezelmeier Haustechnik e.K. · Inhaber Gottfried Brezelmeier\n"
     "Steuernummer 178/123/45678 · USt-IdNr. DE287654321", "DE287654321"),
    ("Malerbetrieb Anton Huberle e.K. · Gartenweg 3 · 86199 Augsburg\n"
     "Inhaber: Anton Huberle · Steuer-Nr. 102/234/56789 · USt-IdNr. DE312845670", "DE312845670"),
    ("Quirin Zwackelhuber · Fotografie · Lerchenfeldstraße 12 · 86150 Augsburg\nUSt-IdNr. DE298765431",
     "DE298765431"),
])
def test_befund_77_ust_idnr_einer_person(text, nummer):
    assert nummer in muster.finde_steuernummer(text)


@pytest.mark.parametrize("text, nummer", [
    ("Brezelmeier Haustechnik e.K. · Inhaber Gottfried Brezelmeier\nUSt-IdNr. DE287654321", "DE287654321"),
    ("Inhaber: Anton Huberle · Steuer-Nr. 102/234/56789 · USt-IdNr. DE312845670", "DE312845670"),
])
def test_befund_77_selbstkontrolle_meldet_ust_idnr_des_inhabers(text, nummer):
    assert _gemeldet(text, nummer)


@pytest.mark.parametrize("text, nummer", [
    ("Allianz Versicherungs-AG · Königinstraße 28 · 80802 München\nUSt-IdNr. DE129274139", "DE129274139"),
    ("Musterbau GmbH\nHauptstraße 1 · 12345 Musterstadt\nUSt-IdNr. DE123456789", "DE123456789"),
    ("Sitz der Gesellschaft: München · Amtsgericht München HRB 1234\nUSt-IdNr. DE123456789", "DE123456789"),
])
def test_befund_77_gegenproben_ust_idnr_der_firma(text, nummer):
    assert nummer not in muster.finde_steuernummer(text)
    assert not _gemeldet(text, nummer)


# ----------------------------------------------------------------------
# Zulassungsbescheinigung Teil I: Felder C.1.1/C.1.2 (Befund 32, Teil Person)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("zeilen, namen", [
    (["ZULASSUNGSBESCHEINIGUNG TEIL I", "A  RO-GW 418\t\tB  21.05.2021", "C.1.1  WIMMERSBERGER",
      "C.1.2  GUNDOLF REINMAR", "C.1.3  LERCHENWEG 4, 83043 BAD AIBLING"], ["WIMMERSBERGER", "GUNDOLF"]),
    (["ZULASSUNGSBESCHEINIGUNG TEIL I", "A  M-KS 4471\t\tB  14.09.2020", "C.1.1  STEINLECHNER", "C.1.2  GUNTRAM"],
     ["STEINLECHNER", "GUNTRAM"]),
    (["ZULASSUNGSBESCHEINIGUNG TEIL", "A M-KS 4471\t\tB 14.09.2020", "0.1.1\t\tSTEINLECHNER", "0.1.2 GUNDOLF"],
     ["STEINLECHNER"]),                                                         # verlesene Feldcodes (Scan)
])
def test_befund_32_zb1_name_und_vornamen(zeilen, namen):
    text = "\n".join(zeilen)
    gefunden = _namen(text)
    for n in namen:
        assert _deckt(gefunden, n), (n, gefunden)
    assert _gemeldet(text, namen[0])


@pytest.mark.parametrize("zeilen, wert", [
    (["Allgemeine Bedingungen", "C.1.1  Was ist versichert?", "C.1.2  Wer ist versichert?"], "Was"),
    (["Inhaltsverzeichnis", "C.1.1  Sachschäden", "C.1.2  Vermögensschäden"], "Sachschäden"),
])
def test_befund_32_gegenproben_gliederungsnummern(zeilen, wert):
    text = "\n".join(zeilen)
    assert not _deckt(_namen(text), wert)
    assert not _gemeldet(text, wert)


# ----------------------------------------------------------------------
# Familienname einer GbR oder Erbengemeinschaft (Befund 63)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("zeilen, name", [
    (["Whg.\t\tEigentümer\t\tLage", "1\t\tKranzbühler, J.\t\tEG links", "2\t\tFelsberger GbR\t\tEG rechts"],
     "Felsberger"),
    (["Whg.\t\tEigentümer\t\tMEA", "2\t\tFelsberger GbR\t\t98/1000"], "Felsberger"),
    (["Eigentümer: Erbengemeinschaft Riedlinger"], "Riedlinger"),
])
def test_befund_63_name_einer_gbr(zeilen, name):
    text = "\n".join(zeilen)
    assert _deckt(_namen(text), name)
    assert _gemeldet(text, name)


@pytest.mark.parametrize("zeile, wert", [
    ("Die GbR besteht aus zwei Gesellschaftern.", "Die"), ("Ihre GbR ist nicht versicherungspflichtig.", "Ihre"),
    ("Haus GbR", "Haus"),
])
def test_befund_63_gegenproben_artikel_und_sachwoerter_vor_gbr(zeile, wert):
    assert not _deckt(_namen(zeile), wert)
    assert not _gemeldet(zeile, wert)


# ----------------------------------------------------------------------
# Beruf in Tabellenspalte und Kastenformular (Befund 87)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("zeilen, berufe", [
    (["Name, Vorname\t\tGeb.-Datum\t\tBeruf\t\tEintritt",
      "Pichlmeier, Notburga\t\t02.08.1958\t\tPflegehelferin\t\t01.10.2026",
      "Hölzlwimmer, Vinzenz\t\t30.11.1990\t\tDachdecker\t\t01.11.2026"], ["Pflegehelferin", "Dachdecker"]),
    (["Lfd.\t\tName, Vorname\t\tGeb.-Datum\t\tTätigkeit\t\tGefahrengruppe",
      "1\t\tHölzlwimmer, Vinzenz\t\t30.11.1990\t\tDachdecker\t\tB",
      "3\t\tKraxenberger, Liesl\t\t03.04.2001\t\tAuszubildende Zimmerin\t\tB"],
     ["Dachdecker", "Auszubildende Zimmerin"]),
    (["Beruf (genaue Tätigkeit)", "Pflegehelferin", "Arbeitgeber", "Seniorenstift St. Josef"], ["Pflegehelferin"]),
])
def test_befund_87_beruf_in_spalte_und_kastenformular(zeilen, berufe):
    gefunden = _geschwaerzt(_funde("\n".join(zeilen)), "beruf")
    for b in berufe:
        assert b in gefunden, (b, gefunden)


@pytest.mark.parametrize("zeilen, wert", [
    (["Name, Vorname\t\tGeb.-Datum\t\tBeruf\t\tEintritt",
      "Pichlmeier, Notburga\t\t02.08.1958\t\tPflegehelferin\t\t01.10.2026"], "Eintritt"),
    (["Lfd.\t\tName, Vorname\t\tGeb.-Datum\t\tTätigkeit\t\tGefahrengruppe",
      "1\t\tHölzlwimmer, Vinzenz\t\t30.11.1990\t\tDachdecker\t\tB"], "Gefahrengruppe"),
    (["Beruf (genaue Tätigkeit)", "Arbeitgeber", "Seniorenstift St. Josef"], "Arbeitgeber"),
])
def test_befund_87_gegenproben_kopfzelle_und_leeres_feld(zeilen, wert):
    assert wert not in _geschwaerzt(_funde("\n".join(zeilen)), "beruf")


# ----------------------------------------------------------------------
# Fehlverdacht der Selbstkontrolle (Befunde 66, 83)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "ARAG SE\nDie Scheibe ist gesprungen.",                                    # Befund 66
    "Korrespondenzanschrift: [ADRESSE], [PLZ ORT]/Havel",
    "Notebook: Dell XPS 13 9340",
    "WLAN-MAC-Adresse: liegt nicht vor",
    "MEA 125/1000",
    "Miteigentumsanteil: 87/1000",
    "HUK-COBURG\n96444 Coburg\nDie Scheibe war gerissen.",
    "Wir danken Ihnen für Ihre Nachricht.",
    "Ausgeführt am 12.03.2025 · TAN-Verfahren: pushTAN",                      # Befund 83
    "SMS-TAN gesendet\t\t12.03.2025 14:07:45",
    "Die TAN-Liste ist ungültig.",
    "Photo-TAN-Verfahren aktiviert",
    "Ihre Kundennummer: [KUNDEN-NR]\t\tMein Zeichen: [VERTRAGS-NR]",
])
def test_befunde_66_83_kein_fehlverdacht(text):
    platzhalter = [p for p in ("[ADRESSE]", "[PLZ ORT]", "[KUNDEN-NR]", "[VERTRAGS-NR]") if p in text]
    assert _verdacht(text, platzhalter=platzhalter) == []


@pytest.mark.parametrize("text, wert", [
    ("Sehr geehrte Frau Scheibe,", "Scheibe"),
    ("Brinkmann-Müiller", "Brinkmann-Müiller"),
    ("Unterschrift: Anna Brinkmann-Tan", "Brinkmann-Tan"),
    ("RIESTER-RENTE\nMax Huber\nHauptstr. 1\n12345 Musterstadt", "Hauptstr. 1"),
    ("Kundennummer 4471 9340", "4471 9340"),
])
def test_befunde_66_83_gegenproben_verdacht_bleibt(text, wert):
    assert _gemeldet(text, wert)


@braucht_modell
@pytest.mark.parametrize("zeilen, name", [
    (["Name, Vorname:\t\tKara, Özlem", "Unfallart: Wildunfall. Frau-Kara fahr stadtauswärts und musste anhalten."],
     "Frau-Kara"),                                  # OCR klebt die Anrede an den Namen (Korpus s1, Messung Runde 5)
])
def test_ner_anrede_mit_bindestrich_bleibt_name(zeilen, name):
    assert _deckt(_namen("\n".join(zeilen)), name)
