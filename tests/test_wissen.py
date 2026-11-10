"""Tests für die Wissensbasis (anonymisierer/wissen.py und anonymisierer/daten/*.txt)."""

import random
import sys
import time
import unicodedata
from pathlib import Path

import pytest

from anonymisierer import wissen as w

DATEN = Path(w.__file__).resolve().parent / "daten"

MINDESTGROESSE = {
    "vornamen": 6000,
    "nachnamen": 8000,
    "nachnamen_mehrdeutig": 400,
    "berufe": 2500,
    "diagnosen": 1500,
    "medikamente": 500,
    "versicherer_und_organisationen": 600,
    "etiketten_person": 250,
    "etiketten_kennung": 350,
    "allerweltswoerter_gross": 8000,
    "partikel": 40,
    "vornamen_mehrdeutig": 30,
    "etiketten_datum_geburt": 30,
    "etiketten_adresse": 60,
    "etiketten_kontakt": 40,
    "etiketten_vertragsdaten": 100,
    "anreden_titel": 150,
}


def _caches_leeren():
    for funktion in (w._liste, w._index, w._menge, w._partikel_folgen, w.etiketten):
        funktion.cache_clear()


# ----------------------------------------------------------------------
# Dateien: Kodierung, Form, Sortierung, Dubletten
# ----------------------------------------------------------------------
@pytest.mark.parametrize("name", sorted(w.LISTEN))
def test_listendatei_form(name):
    pfad = DATEN / w.LISTEN[name]
    roh = pfad.read_bytes()
    assert not roh.startswith(b"\xef\xbb\xbf"), "ohne BOM speichern"
    text = roh.decode("utf-8")                                   # strenges UTF-8
    assert "\r" not in text, "Unix-Zeilenenden"
    zeilen = text.splitlines()
    kopf = [z for z in zeilen if z.startswith("#")]
    assert kopf and any("QUELLEN.md" in z for z in kopf), "Kopfkommentar mit Verweis auf QUELLEN.md"
    eintraege, im_kopf = [], True
    for z in zeilen:
        if z.startswith("#"):
            assert im_kopf, f"Kommentar mitten in der Liste: {z!r}"
            continue
        im_kopf = False
        assert z, "keine Leerzeilen zwischen den Einträgen"
        assert z == z.strip() and "  " not in z, f"Leerraum: {z!r}"
        assert unicodedata.normalize("NFC", z) == z, f"nicht NFC: {z!r}"
        assert not any(unicodedata.category(c) in ("Cc", "Cf") for c in z), f"Steuerzeichen: {z!r}"
        eintraege.append(z)
    assert eintraege == sorted(eintraege, key=w.sortierschluessel), "Datei ist nicht sortiert"
    assert len(eintraege) == len(set(eintraege)), "Dubletten"
    assert len({e.casefold() for e in eintraege}) == len(eintraege), "Dubletten bis auf Groß-/Kleinschreibung"
    assert tuple(eintraege) == w.liste(name)


@pytest.mark.parametrize("name,minimum", sorted(MINDESTGROESSE.items()))
def test_mindestgroesse(name, minimum):
    assert len(w.liste(name)) >= minimum


def test_alle_listen_haben_mindestgroesse_eingetragen():
    assert set(MINDESTGROESSE) == set(w.LISTEN)


def test_eintraege_ohne_ziffern_in_namenslisten():
    for name in ("vornamen", "nachnamen", "partikel", "nachnamen_mehrdeutig", "vornamen_mehrdeutig"):
        for e in w.liste(name):
            assert not any(c.isdigit() for c in e), (name, e)
            assert all(c.isalpha() or c in " -'’." for c in e), (name, e)


def test_vornamen_und_allerweltswoerter_beginnen_gross():
    for name in ("vornamen", "allerweltswoerter_gross", "vornamen_mehrdeutig", "nachnamen_mehrdeutig"):
        for e in w.liste(name):
            assert e[0].isupper(), (name, e)


def test_nachnamen_beginnen_gross_ausser_partikel():
    for e in w.liste("nachnamen"):
        if not e[0].isupper():
            assert w.ist_partikel(w.woerter(e)[0]), e


# ----------------------------------------------------------------------
# Überschneidungen zwischen den Listen
# ----------------------------------------------------------------------
def test_allerweltswoerter_enthalten_keine_namen_berufe_diagnosen():
    gesperrt = set()
    for name in ("vornamen", "nachnamen", "berufe", "diagnosen", "medikamente"):
        gesperrt |= w.menge(name)
    kollisionen = [e for e in w.liste("allerweltswoerter_gross")
                   if w.normalisieren(e) in gesperrt or w.normalisieren_umschrift(e) in gesperrt
                   or w.ist_vorname(e) or w.ist_nachname(e)]
    assert kollisionen == []


def test_kein_name_gilt_als_allerweltswort():
    """Auch über die Beugungsregel von ist_allerweltswort darf kein Name als
    Allerweltswort durchgehen (sonst würde eine Regel echte Namen verwerfen)."""
    falsch = [n for n in w.liste("vornamen") + w.liste("nachnamen") if w.ist_allerweltswort(n)]
    assert falsch == []


def test_mehrdeutige_nachnamen_sind_nachnamen():
    fehlend = [e for e in w.liste("nachnamen_mehrdeutig") if not w.ist_nachname(e)]
    assert fehlend == []


def test_mehrdeutige_vornamen_sind_vornamen():
    assert [e for e in w.liste("vornamen_mehrdeutig") if not w.ist_vorname(e)] == []


def test_berufe_die_nachnamen_sind_gelten_als_mehrdeutig():
    falsch = [b for b in w.liste("berufe") if w.ist_nachname(b) and not w.ist_mehrdeutig(b)]
    assert falsch == []


def test_einzelwoerter_der_erlaubnisliste_mit_namensgleichheit_sind_mehrdeutig():
    falsch = []
    for e in w.liste("versicherer_und_organisationen"):
        if len(w.woerter(e)) == 1:
            if w.ist_nachname(e) and not w.ist_mehrdeutig(e):
                falsch.append(e)
            if w.ist_vorname(e) and not w.ist_vorname_mehrdeutig(e):
                falsch.append(e)
    assert falsch == []


def test_erlaubnisliste_enthaelt_keine_personen():
    for e in w.liste("versicherer_und_organisationen"):
        teile = w.woerter(e)
        # "Vorname Nachname" als ganzer Eintrag wäre eine Person
        assert not (len(teile) == 2 and w.ist_vorname(teile[0]) and w.ist_nachname(teile[1])
                    and not w.ist_vorname_mehrdeutig(teile[0])), e


# ----------------------------------------------------------------------
# Pflichtinhalte aus der Aufgabenstellung (Stichproben)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("wort", ["Mehmet", "Ayşe", "Yusuf", "Łukasz", "Lukasz", "Małgorzata", "Mohammed",
                                  "Muhammad", "Mohamed", "Søren", "Jürgen", "Anna-Lena", "Hans-Peter",
                                  "Oleksandr", "Sergej", "Sergey", "Dragan", "Ardian", "Giorgos",
                                  "Xiaoming", "Min-jun", "Haruto", "Priya", "Chinedu", "Kwame", "Tesfaye",
                                  "Abdirahman", "Zeynep", "Fatemeh", "Gulalai", "Thủy", "Thuy"])
def test_vornamen_stichproben(wort):
    assert w.ist_vorname(wort), wort


@pytest.mark.parametrize("wort", ["Müller", "Mueller", "Meyer", "Maier", "Mayer", "Meier", "Mayr", "Schmidt",
                                  "Schmitt", "Yılmaz", "Yilmaz", "Öztürk", "Kowalski", "Kowalska",
                                  "Nowak", "Iwanow", "Ivanova", "Schewtschenko", "Shevchenko", "Popescu",
                                  "Horvat", "Krasniqi", "Papadopoulos", "Papadopoulou", "Rossi",
                                  "García", "Silva", "de Vries", "van Dijk", "Nguyễn", "Nguyen", "Kim",
                                  "Patel", "Perera", "Okafor", "Mensah", "Tesfay", "Gruber", "Wüthrich"])
def test_nachnamen_stichproben(wort):
    assert w.ist_nachname(wort), wort


@pytest.mark.parametrize("wort", ["von", "van", "de", "del", "della", "di", "du", "le", "la", "al-",
                                  "el-", "bin", "ibn", "ter", "ten", "zu", "von und zu",
                                  "Freiherr von", "Graf von", "van der", "de la"])
def test_partikel_stichproben(wort):
    assert w.ist_partikel(wort), wort


@pytest.mark.parametrize("wort", ["Klein", "Groß", "Lange", "Wolf", "Fuchs", "Koch", "Bauer", "Braun",
                                  "Weiß", "Schwarz", "Frank", "Hahn", "Vogel", "Winter", "Sommer",
                                  "Berg", "Stein", "Busch", "Graf", "Kaiser", "König", "Jung", "Alt",
                                  "Hagen", "Nürnberger", "Schütz", "Bär", "Das", "Nur"])
def test_mehrdeutig_stichproben(wort):
    assert w.ist_mehrdeutig(wort), wort


@pytest.mark.parametrize("wort", ["Müller", "Neumann", "Schneider", "Yılmaz", "Kowalski"])
def test_klare_nachnamen_sind_nicht_mehrdeutig(wort):
    assert w.ist_nachname(wort) and not w.ist_mehrdeutig(wort)


@pytest.mark.parametrize("wort", ["Zahnarzt", "Zahnärztin", "Polier", "Polierin", "Beamter", "Beamtin",
                                  "Rentner", "Rentnerin", "selbstständig", "Hausfrau", "Hausmann",
                                  "Auszubildender", "Auszubildende", "Student", "Studentin",
                                  "Kaufmann für Versicherungen und Finanzen",
                                  "Kauffrau für Versicherungen und Finanzen", "Medizinische Fachangestellte",
                                  "Kfz-Mechatroniker", "Kfz-Mechatronikerin", "Rechtsanwältin", "Köchin"])
def test_berufe_stichproben(wort):
    assert w.index("berufe").eintrag_fuer(wort), wort


@pytest.mark.parametrize("wort", ["Bandscheibenvorfall", "Diabetes mellitus Typ 2", "Depression", "Burnout",
                                  "Mammakarzinom", "Kreuzbandriss", "Hüft-TEP", "Schizophrenie",
                                  "posttraumatische Belastungsstörung", "Multiple Sklerose",
                                  "Schwangerschaftsabbruch", "HIV-Infektion", "Pflegegrad 3"])
def test_diagnosen_stichproben(wort):
    assert w.index("diagnosen").eintrag_fuer(wort), wort


@pytest.mark.parametrize("wort", ["Ibuprofen", "Metformin", "Ramipril", "Sertralin", "Tavor", "Lyrica",
                                  "Ozempic", "Humira", "Methadon", "L-Thyroxin"])
def test_medikamente_stichproben(wort):
    assert w.index("medikamente").eintrag_fuer(wort), wort


@pytest.mark.parametrize("wort", [
    "Allianz Lebensversicherungs-AG", "AXA", "ERGO", "HUK-COBURG", "R+V", "Debeka", "Signal Iduna",
    "Generali", "Zurich", "Gothaer", "Hallesche", "Barmenia", "Continentale", "Alte Leipziger",
    "Volkswohl Bund", "LV 1871", "Swiss Life", "Canada Life", "Stuttgarter", "WWK", "Nürnberger",
    "Hannoversche", "Die Bayerische", "HDI", "Condor", "Interrisk", "Ammerländer", "VHV", "DEVK",
    "Provinzial", "Sparkassen-Versicherungen", "uniVersa", "Inter", "Basler", "Helvetia", "Baloise",
    "Dialog", "Ideal", "Münchener Verein", "Hanse Merkur", "DKV", "Württembergische", "Wüstenrot",
    "blau direkt", "Fonds Finanz", "Jung DMS", "Netfonds", "Deutsche Rentenversicherung Bund",
    "Finanzamt", "Familienkasse", "Bundesagentur für Arbeit", "Zulagenstelle für Altersvermögen",
    "BaFin", "IHK", "AOK Bayern", "TK", "Barmer", "DAK-Gesundheit", "IKK classic", "KKH", "hkk", "BKK",
    "Sparkasse", "Volksbank", "Raiffeisenbank", "Commerzbank", "Deutsche Bank", "ING", "DKB", "Postbank",
    "Comdirect", "Consorsbank", "Riester-Rente", "Rürup-Rente", "Basisrente",
    "Berufsunfähigkeitsversicherung", "Risikolebensversicherung", "PrivatRente", "KomfortDynamik",
    "Kfz-Haftpflicht", "Teilkasko", "Vollkasko", "Hausrat", "Wohngebäude", "Unfallversicherung", "AVB",
    "VVG", "BGB", "SGB"])
def test_erlaubnisliste_stichproben(wort):
    assert w.ist_allowlist(wort), wort


@pytest.mark.parametrize("art,wort", [
    ("person", "Versicherungsnehmer"), ("person", "Versicherungsnehmerin"), ("person", "versicherte Person"),
    ("person", "Beitragszahler"), ("person", "Kontoinhaber"), ("person", "Antragsteller"),
    ("person", "Unfallgegner"), ("person", "Zeuge"), ("person", "Zeugin"), ("person", "Fahrer"),
    ("person", "Halter"), ("person", "Patient"), ("person", "Ehepartner"), ("person", "Lebenspartner"),
    ("person", "Kind"), ("person", "Bezugsberechtigter"), ("person", "Erbe"), ("person", "Sachbearbeiter"),
    ("person", "Ansprechpartner"), ("person", "Vermittler"), ("person", "Makler"), ("person", "Inhaber"),
    ("person", "Mieter"), ("person", "Vermieter"), ("person", "Geschädigter"), ("person", "Verursacher"),
    ("person", "behandelnder Arzt"), ("person", "Name"), ("person", "Vorname"), ("person", "Nachname"),
    ("person", "Familienname"), ("person", "Geburtsname"), ("person", "Kontoinhaber/in"),
    ("kennung", "Versicherungsschein-Nr."), ("kennung", "Vertragsnummer"), ("kennung", "Kunden-Nr."),
    ("kennung", "Schaden-Nr."), ("kennung", "Aktenzeichen"), ("kennung", "Az."), ("kennung", "Geschäftszeichen"),
    ("kennung", "Unser Zeichen"), ("kennung", "Ihr Zeichen"), ("kennung", "Referenz"),
    ("kennung", "Mandatsreferenz"), ("kennung", "Personalnummer"), ("kennung", "Mitgliedsnummer"),
    ("kennung", "Rentenversicherungsnummer"), ("kennung", "Krankenversichertennummer"),
    ("kennung", "Steuernummer"), ("kennung", "IdNr"), ("kennung", "Rechnungsnummer"),
    ("kennung", "Belegnummer"), ("kennung", "Vorgangsnummer"), ("kennung", "Kennzeichen"),
    ("kennung", "Fahrgestellnummer"), ("kennung", "FIN"), ("kennung", "Policennummer"),
    ("kennung", "Antragsnummer"), ("kennung", "Depotnummer"), ("kennung", "Kontonummer"),
    ("kennung", "Zulagenummer"), ("kennung", "Kindergeldnummer"), ("kennung", "Personalausweisnummer"),
    ("kennung", "Reisepassnummer"), ("kennung", "Führerscheinnummer"), ("kennung", "Versichertennummer"),
    ("kennung", "Patienten-ID"), ("kennung", "Fallnummer"), ("kennung", "Auftragsnummer"),
    ("datum_geburt", "geb."), ("datum_geburt", "Geburtsdatum"), ("datum_geburt", "geboren am"),
    ("adresse", "Anschrift"), ("adresse", "PLZ/Ort"), ("adresse", "Straße und Hausnummer"),
    ("kontakt", "Telefon"), ("kontakt", "Tel."), ("kontakt", "Mobil"), ("kontakt", "Handy"),
    ("kontakt", "Fax"), ("kontakt", "E-Mail"),
    ("vertragsdaten", "Beginn"), ("vertragsdaten", "Ablauf"), ("vertragsdaten", "Fälligkeit"),
    ("vertragsdaten", "Stand"), ("vertragsdaten", "gültig ab")])
def test_etiketten_stichproben(art, wort):
    assert w.index(f"etiketten_{art}").eintrag_fuer(wort), (art, wort)


@pytest.mark.parametrize("wort", ["Herr", "Herrn", "Frau", "Dr.", "Dr. med.", "Prof.", "Dipl.-Ing.", "RA",
                                  "StB", "i. A.", "i. V.", "gez."])
def test_anreden_titel_stichproben(wort):
    assert w.ist_anrede_titel(wort), wort


@pytest.mark.parametrize("wort", ["Schadenanzeige", "Familientarif", "Schlüsselverlust", "Praxisanschrift",
                                  "Erstattungsfähig", "Versicherungsschutz", "Beitragsrechnung",
                                  "Leistungsabrechnung", "Kostenvoranschlag", "Bescheinigung"])
def test_allerweltswoerter_stichproben(wort):
    assert w.ist_allerweltswort(wort), wort


# ----------------------------------------------------------------------
# Normalisierung
# ----------------------------------------------------------------------
@pytest.mark.parametrize("roh,erwartet", [
    ("Çelik", "celik"), ("Łukasz", "lukasz"), ("STRAUSS", "strauss"), ("Strauß", "strauss"),
    ("Müller", "muller"), ("Øre", "ore"), ("İbrahim", "ibrahim"), ("Yılmaz", "yilmaz"),
    ("Đorđe", "dorde"), ("Nguyễn", "nguyen"), ("Ærø", "aero"), ("  Zwei   Wörter ", "zwei worter"),
    ("O’Brien", "o'brien"), ("Müller", "muller"), ("Versiche­rung", "versicherung"),
])
def test_normalisieren(roh, erwartet):
    assert w.normalisieren(roh) == erwartet


def test_normalisieren_umschrift():
    assert w.normalisieren_umschrift("Müller") == "mueller"
    assert w.normalisieren_umschrift("Söderberg") == "soederberg"
    assert w.normalisieren_umschrift("Søren") == "soeren"
    assert w.normalisieren_umschrift("Ågård") == "aagaard"


def test_sortierschluessel_ordnet_diakritika_zum_grundbuchstaben():
    worte = ["Zander", "Ärztin", "Arzt", "Öl", "Ost", "Ufer", "Übel"]
    assert sorted(worte, key=w.sortierschluessel) == ["Arzt", "Ärztin", "Öl", "Ost", "Übel", "Ufer", "Zander"]


# ----------------------------------------------------------------------
# Einzelwort-Prüfungen
# ----------------------------------------------------------------------
def test_ist_vorname():
    assert w.ist_vorname("Lisa-Marie")          # Teile sind Vornamen
    assert w.ist_vorname("MEHMET")
    assert w.ist_vorname("Ayse")                 # ohne Diakritika
    assert not w.ist_vorname("Versicherung")
    assert not w.ist_vorname("")


def test_ist_nachname_mit_partikeln_und_doppelnamen():
    assert w.ist_nachname("van Dijk") and w.ist_nachname("Dijk")
    assert w.ist_nachname("Al-Hassan") and w.ist_nachname("al Hassan")
    assert w.ist_nachname("von Weber")           # Partikel + Kern
    assert w.ist_nachname("Müller-Schmidt")      # beide Teile bekannt
    assert not w.ist_nachname("Müller-Straße")
    assert not w.ist_nachname("von")
    assert not w.ist_nachname("Schadenanzeige")


def test_kerne_von_partikelnamen_stehen_als_eigene_eintraege():
    # Listenform "Vries, Jan de" und arabische Namen ohne Artikel: auch finde() trifft sie
    for kern in ("Vries", "Dijk", "Heijden", "Bayati", "Dulaimi", "Santis", "Maizière", "Maiziere"):
        assert w.ist_nachname(kern), kern
    assert [t.text for t in w.finde("Vries, Jan de; Frau Bayati", "nachnamen")] == ["Vries", "Bayati"]
    assert w._partikel_kern("van der Meer") == "Meer" and w._partikel_kern("Al-Hassan") == "Hassan"
    assert w._partikel_kern("Meier") is None
    fehlend = []
    for eintrag in w.liste("nachnamen"):
        kern = w._partikel_kern(eintrag)
        if kern and not (w._im_index("nachnamen", kern) or w.ist_vorname(kern)
                         or w.ist_allerweltswort(kern)):
            fehlend.append(eintrag)
    assert fehlend == []
    # Kerne, die Vornamen oder Allerweltswörter sind, stehen nicht als Nachname da
    for wort in ("Essen", "Haar", "Vita", "Meer", "Marco", "Stefano"):
        assert not w._im_index("nachnamen", wort), wort
    assert w.ist_mehrdeutig("Velden") and w.ist_mehrdeutig("Damme")      # auch Ortsnamen


def test_ist_mehrdeutig_und_vorname_mehrdeutig():
    assert w.ist_mehrdeutig("koch") and w.ist_mehrdeutig("KOCH")
    assert w.ist_vorname_mehrdeutig("Rosa") and w.ist_vorname_mehrdeutig("Mai")
    assert not w.ist_vorname_mehrdeutig("Mehmet")


def test_ist_allerweltswort_beugung():
    assert w.ist_allerweltswort("Versicherungsnehmers")
    assert w.ist_allerweltswort("Leistungen")
    assert not w.ist_allerweltswort("Mustermann")
    assert not w.ist_allerweltswort("Müller")


def test_phrasen_pruefungen_laengster_treffer():
    assert w.ist_beruf("Beruf: Zahnärztin (angestellt)") == "Zahnärztin"
    assert w.ist_beruf("Kauffrau für Versicherungen und Finanzen") == "Kauffrau für Versicherungen und Finanzen"
    assert w.ist_beruf("Hauptstraße 5") is None
    assert w.ist_diagnose("V. a. Diabetes mellitus Typ 2") == "Diabetes mellitus Typ 2"
    assert w.ist_diagnose("Z. n. Hüft TEP rechts") == "Hüft-TEP"
    assert w.ist_medikament("Ibuprofen 600 mg 1-0-1") == "Ibuprofen"
    assert w.ist_diagnose("Bitte senden Sie uns die Unterlagen.") is None


def test_ist_allowlist():
    assert w.ist_allowlist("HUK-Coburg Allgemeine Versicherung AG")
    assert w.ist_allowlist("Deutsche Rentenversicherung Bund")
    assert not w.ist_allowlist("Max Mustermann")
    assert not w.ist_allowlist("Herr Nürnberger")       # "Herr" ist nicht auf der Liste
    assert not w.ist_allowlist("R, V")
    assert not w.ist_allowlist("")


def test_etiketten_nach_laenge_absteigend():
    for art in w.ETIKETTEN_ARTEN:
        eintraege = w.etiketten(art)
        assert list(map(len, eintraege)) == sorted(map(len, eintraege), reverse=True)
        assert set(eintraege) == set(w.liste(f"etiketten_{art}"))
    assert w.etiketten("etiketten_kontakt") == w.etiketten("kontakt")
    with pytest.raises(KeyError):
        w.etiketten("unbekannt")
    with pytest.raises(KeyError):
        w.liste("gibtsnicht")


def test_alias_namen():
    assert w.liste("allowlist") == w.liste("versicherer_und_organisationen")
    assert w.liste("mehrdeutig") == w.liste("nachnamen_mehrdeutig")


# ----------------------------------------------------------------------
# Suche im Text
# ----------------------------------------------------------------------
def test_finde_ganzwort_und_offsets():
    text = "Der Zahnarzt und der Arzt; Rentnerin seit 2020."
    treffer = w.finde(text, "berufe")
    assert [t.text for t in treffer] == ["Zahnarzt", "Arzt", "Rentnerin"]
    for t in treffer:
        assert text[t.start:t.ende] == t.text


def test_finde_laengster_eintrag_zuerst():
    treffer = w.finde("Diagnose: Diabetes mellitus Typ 2, außerdem Diabetes.", "diagnosen")
    assert [t.eintrag for t in treffer] == ["Diabetes mellitus Typ 2", "Diabetes"]


def test_finde_trenner():
    assert w.finde("Kfz Haftpflicht und Kfz-Haftpflicht", "allowlist")[0].eintrag in w.liste("allowlist")
    assert len(w.finde("Kfz Haftpflicht und Kfz-Haftpflicht", "allowlist")) == 2
    assert [t.text for t in w.finde("R+V und R + V", "allowlist")] == ["R+V", "R + V"]
    assert w.finde("Kapitel R, V", "allowlist") == []
    # Punkt am Ende gehört zum Treffer, wenn der Eintrag einen hat
    treffer = w.finde("Kunden-Nr.: 4711", "etiketten_kennung")
    assert treffer and treffer[0].text == "Kunden-Nr."


def test_finde_zeilenumbruch():
    text = "Diabetes\nmellitus Typ 2"
    assert [t.eintrag for t in w.finde(text, "diagnosen")] == ["Diabetes"]
    assert [t.eintrag for t in w.finde(text, "diagnosen", zeilenuebergreifend=True)] == ["Diabetes mellitus Typ 2"]


def test_finde_nur_gross():
    assert w.finde("ein klein wenig", "nachnamen", nur_gross=True) == []
    assert [t.text for t in w.finde("Herr Klein kommt", "nachnamen", nur_gross=True)] == ["Klein"]


def test_finde_umschrift_und_zerlegte_zeichen():
    assert [t.eintrag for t in w.finde("MUELLER, Max", "nachnamen", nur_gross=True)][0] == "Müller"
    zerlegt = "Herr Müller"                      # u + kombinierendes Trema
    treffer = w.finde(zerlegt, "nachnamen")
    assert treffer and treffer[-1].text == "Müller"
    weich = "Bandscheiben­vorfall"                 # weicher Trennstrich im Wort
    assert [t.eintrag for t in w.finde(weich, "diagnosen")] == ["Bandscheibenvorfall"]


def test_phrasenindex_fuer_eigene_listen():
    idx = w.Phrasenindex(["Max Mustermann", "Projekt Blau", "A&B"])
    text = "Max  Mustermann, MAX MUSTERMANN, Projekt-Blau, A & B, A B"
    assert [t.text for t in idx.finde(text)] == ["Max  Mustermann", "MAX MUSTERMANN", "Projekt-Blau", "A & B"]
    assert "max mustermann" in idx and "Mustermann" not in idx
    assert idx.laengster("Herr Max Mustermann") == "Max Mustermann"
    assert idx.deckt_ab("Projekt Blau") and not idx.deckt_ab("Projekt Blau neu")
    assert w.Phrasenindex([]).finde("irgendwas") == []


def _beispieltext(groesse=100_000):
    zufall = random.Random(7)
    vorrat = (list(w.liste("allerweltswoerter_gross")[:2000]) + list(w.liste("nachnamen")[:300])
              + ["und", "der", "die", "mit", "für", "Herr", "Frau", "Dr.", "Nr.", "12.03.2024", "4711",
                 "Bandscheibenvorfall", "Diabetes mellitus Typ 2", "Kfz-Haftpflicht", "R+V"])
    teile, laenge = [], 0
    while laenge < groesse:
        satz = " ".join(zufall.choice(vorrat) for _ in range(12)) + ".\n"
        teile.append(satz)
        laenge += len(satz)
    return "".join(teile)[:groesse]


@pytest.mark.parametrize("name", ["nachnamen", "vornamen", "allerweltswoerter_gross", "diagnosen",
                                  "versicherer_und_organisationen", "etiketten_kennung"])
def test_finde_ist_schnell(name):
    text = _beispieltext()
    w.index(name)                                     # Aufbau zählt nicht (einmalig)
    beste = min(_dauer(lambda: w.finde(text, name)) for _ in range(3))
    assert beste < 0.050, f"{name}: {beste * 1000:.1f} ms für 100 KB"


def _dauer(funktion):
    anfang = time.perf_counter()
    funktion()
    return time.perf_counter() - anfang


def test_indexaufbau_aller_listen_unter_zwei_sekunden():
    _caches_leeren()
    anfang = time.perf_counter()
    for name in w.LISTEN:
        w.index(name)
    assert time.perf_counter() - anfang < 2.0


# ----------------------------------------------------------------------
# Fundort der Daten (auch im PyInstaller-Paket) und Fehlerfälle
# ----------------------------------------------------------------------
def test_daten_ordner_neben_modul():
    assert w.daten_ordner() == DATEN


def test_daten_ordner_im_pyinstaller_paket(tmp_path, monkeypatch):
    paket = tmp_path / "anonymisierer" / "daten"
    paket.mkdir(parents=True)
    (paket / "vornamen.txt").write_text("# Test QUELLEN.md\nAnna\n", encoding="utf-8")
    monkeypatch.setattr(w, "__file__", str(tmp_path / "ohne_daten" / "wissen.pyc"))
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert w.daten_ordner() == paket


def test_fehlende_liste_meldet_verstaendlichen_fehler(tmp_path, monkeypatch):
    monkeypatch.setattr(w, "daten_ordner", lambda: tmp_path)
    _caches_leeren()
    try:
        with pytest.raises(w.WissensbasisFehler, match="Wortliste fehlt"):
            w.liste("vornamen")
        with pytest.raises(w.WissensbasisFehler):
            w.ist_vorname("Anna")
    finally:
        monkeypatch.undo()
        _caches_leeren()


def test_kaputte_kodierung_meldet_fehler(tmp_path):
    pfad = tmp_path / "x.txt"
    pfad.write_bytes(b"# Kopf\nM\xfcller\n")              # Latin-1 statt UTF-8
    with pytest.raises(w.WissensbasisFehler, match="UTF-8"):
        w.lies_listendatei(pfad)


def test_pflegewerkzeug_meldet_keine_probleme(capsys):
    werkzeuge = Path(w.__file__).resolve().parent.parent / "werkzeuge"
    sys.path.insert(0, str(werkzeuge))
    try:
        import wissen_pflegen
        assert wissen_pflegen.main([]) == 0
    finally:
        sys.path.remove(str(werkzeuge))
    assert "Alles in Ordnung" in capsys.readouterr().out


def test_pflegewerkzeug_ordnet_datei(tmp_path):
    werkzeuge = Path(w.__file__).resolve().parent.parent / "werkzeuge"
    sys.path.insert(0, str(werkzeuge))
    try:
        import wissen_pflegen
    finally:
        sys.path.remove(str(werkzeuge))
    pfad = tmp_path / "liste.txt"
    pfad.write_bytes("# Kopf\r\nZoe\r\nÄrger\r\nAnna\r\nZoe\r\n".encode("utf-8"))
    probleme = wissen_pflegen.datei_aufbereiten(pfad, schreiben=True)
    assert any("CRLF" in p for p in probleme) and any("Dublette" in p for p in probleme)
    assert pfad.read_bytes() == "# Kopf\nAnna\nÄrger\nZoe\n".encode("utf-8")
    assert wissen_pflegen.datei_aufbereiten(pfad, schreiben=False) == []
    # Schreibvarianten entscheidet der Mensch: beide bleiben stehen, das Werkzeug meldet sie
    pfad.write_text("# Kopf\nAnna\nanna\n", encoding="utf-8", newline="\n")
    probleme = wissen_pflegen.datei_aufbereiten(pfad, schreiben=True)
    assert any("Groß-/Kleinschreibung" in p for p in probleme)
    assert pfad.read_text(encoding="utf-8") == "# Kopf\nAnna\nanna\n"


def test_quellen_md_beschreibt_herkunft_und_alle_listen():
    text = (DATEN / "QUELLEN.md").read_text(encoding="utf-8")
    for pflicht in ("MIT", "CC0", "wissen_pflegen.py --schreiben", "--add-data"):
        assert pflicht in text, pflicht
    for datei in w.LISTEN.values():
        assert f"`{datei}`" in text, f"{datei} fehlt in QUELLEN.md"
