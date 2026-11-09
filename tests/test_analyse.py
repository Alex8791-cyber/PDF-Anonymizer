"""Tests für die Analyse (anonymisierer/analyse.py): NIE-/IMMER-Listen, Bruchstück-Filter,
Pseudonyme, Korpus-Trefferquote, Fehlalarme auf realistischen Briefen, PDF-Analyse."""

import json
import re
import threading
from pathlib import Path

import fitz
import pytest

from anonymisierer import analyse
from anonymisierer import namen as na
from anonymisierer import ocr as ocr_modul
from anonymisierer.analyse import analysiere_pdf, analysiere_text
from anonymisierer.muster import KATEGORIEN
from conftest import braucht_modell

DATEN = Path(__file__).parent / "daten"
ALLE = {k for k, *_ in KATEGORIEN}
STANDARD = {k for k, _, _, _, an in KATEGORIEN if an}
OHNE_NAMEN = ALLE - {"namen"}


def paare(funde):
    return [(f["kategorie"], f["text"]) for f in funde]


def pruefe_fund_struktur(fund):
    assert set(fund) >= {"kategorie", "anzeige", "text", "ersatz", "seiten", "anzahl", "kontext"}
    assert isinstance(fund["seiten"], list) and fund["anzahl"] >= 1
    assert "»" in fund["kontext"] and "«" in fund["kontext"] and "\n" not in fund["kontext"]


# ----------------------------------------------------------------------
# Fund-Struktur, anzahl, kontext
# ----------------------------------------------------------------------
def test_fund_struktur_anzahl_kontext():
    text = "Kunden-Nr. 4711\nIBAN DE89 3704 0044 0532 0130 00\nnochmal IBAN DE89 3704 0044 0532 0130 00 Ende"
    funde = analysiere_text(text, OHNE_NAMEN, [], [])
    for f in funde:
        pruefe_fund_struktur(f)
        assert f["seiten"] == []
    iban = next(f for f in funde if f["kategorie"] == "iban")
    assert iban["anzahl"] == 2
    assert "»DE89 3704 0044 0532 0130 00«" in iban["kontext"]
    assert iban["kontext"].startswith("…Kunden-Nr. 4711 IBAN") or "Kunden-Nr. 4711 IBAN" in iban["kontext"]


def test_anzahl_zaehlt_ganze_woerter():
    funde = analysiere_text("Herr Berg wohnt in Heidelberg, Bergstraße 1. Herr Berg zahlt.", {"namen"}, [], [])
    berg = next(f for f in funde if f["text"] == "Berg")
    assert berg["anzahl"] == 2


# ----------------------------------------------------------------------
# M-16: positionsbasierter Bruchstück-Filter und Dedup mit Kategorie-Priorität
# ----------------------------------------------------------------------
def test_bruchstueck_filter_positionsbasiert():
    f = paare(analysiere_text("Konto-Nr. 532013000, BLZ 37040044\nIBAN DE89370400440532013000", OHNE_NAMEN, [], []))
    assert ("iban", "DE89370400440532013000") in f and ("vertrag", "532013000") in f
    f = paare(analysiere_text("Versicherungsschein-Nr. 123456789\nKontonummer 0123456789", OHNE_NAMEN, [], []))
    assert ("vertrag", "123456789") in f and ("vertrag", "0123456789") in f
    f = paare(analysiere_text("Telefon 0171 2345678\nKunden-Nr. 2345678", OHNE_NAMEN, [], []))
    assert ("telefon", "0171 2345678") in f and ("vertrag", "2345678") in f
    f = paare(analysiere_text("Vertragsnummer 2024-12.05.1985-77\ngeb. 12.05.1985", OHNE_NAMEN, [], []))
    assert ("geburt", "12.05.1985") in f and ("vertrag", "2024-12.05.1985-77") in f


def test_bruchstueck_in_iban_wird_gefiltert():
    f = paare(analysiere_text("IBAN DE89 3704 0044 0532 0130 00", OHNE_NAMEN, [], []))
    assert f == [("iban", "DE89 3704 0044 0532 0130 00")]           # kein Telefon-Bruchstück


def test_dedup_spezifischere_kategorie_gewinnt():
    f = analysiere_text("Kunden-Nr. 12 345678 A 123\nSV-Nr. 12 345678 A 123", OHNE_NAMEN, [], [])
    assert paare(f) == [("svnr", "12 345678 A 123")] and f[0]["ersatz"] == "[SV-NR]"
    f = paare(analysiere_text("Kontonummer 0123456789", OHNE_NAMEN, [], []))
    assert f == [("vertrag", "0123456789")]                            # nicht [TELEFON]
    f = paare(analysiere_text("Steuernummer 048/123/45678", OHNE_NAMEN, [], []))
    assert f == [("steuernr", "048/123/45678")]
    f = paare(analysiere_text("Versicherungsnummer 65170839J008", OHNE_NAMEN, [], []))
    assert f == [("svnr", "65170839J008")]
    f = paare(analysiere_text("Kunden-Nr. 01712345678\nMobil 01712345678", OHNE_NAMEN, [], []))
    assert len(f) == 1 and f[0][1] == "01712345678"                   # gleicher Text nur einmal


# ----------------------------------------------------------------------
# M-11: NIE-Liste (Ganzwort/Ganzphrase, Mindestlänge 3, Hinweise)
# ----------------------------------------------------------------------
TEXT_NIE = ("Zeuge: Herr Karl Schmidtke, Schmidtstraße 4, 80331 München.\n"
            "IBAN DE89 3704 0044 0532 0130 00, Tel 0171 2345678, Steuer-ID 86095742719.\n"
            "Versicherungsschein-Nr. AZ 1234567 A, Kunden-Nr. 4711, Hauptstr. 7")


def test_nie_liste_kurze_und_teilstring_eintraege_wirken_nicht():
    referenz = paare(analysiere_text(TEXT_NIE, OHNE_NAMEN, [], []))
    assert ("iban", "DE89 3704 0044 0532 0130 00") in referenz
    for eintrag in (["A"], ["DE"], ["Str."], ["AG"], ["Schmidt"], ["Hauptstraße 12a, 60311 Frankfurt am Main"]):
        assert paare(analysiere_text(TEXT_NIE, OHNE_NAMEN, eintrag, [])) == referenz


def test_nie_liste_exakte_phrase_gibt_frei_mit_hinweis():
    funde, hinweise = analyse._analysiere(TEXT_NIE, OHNE_NAMEN, ["schmidtstraße 4", "80331  München"], [])
    f = paare(funde)
    assert ("strasse", "Schmidtstraße 4") not in f and ("plzort", "80331 München") not in f
    assert ("strasse", "Hauptstr. 7") in f
    assert any(h.startswith("Durch NIE-Liste freigegeben: Schmidtstraße 4") for h in hinweise)
    assert any("80331 München" in h for h in hinweise)
    # analysiere_text liefert nur die Funde (Vertrags-Signatur)
    assert paare(analysiere_text(TEXT_NIE, OHNE_NAMEN, ["schmidtstraße 4", "80331  München"], [])) == f


def _kandidaten_aus(text, *namen):
    """Feste Namenskandidaten wie namen.finde_personen sie liefert (Position = erstes Vorkommen)."""
    kandidaten = []
    for n in namen:
        n, gruppe = n if isinstance(n, tuple) else (n, None)
        start = text.find(n)
        assert start >= 0, n
        kandidaten.append({"text": n, "start": start, "ende": start + len(n), "gruppe": gruppe})
    return sorted(kandidaten, key=lambda k: k["start"])


def gedeckt(funde, text, teil, wort=None):
    """Ist `wort` (Standard: der ganze `teil`) in jedem Vorkommen von `teil` von einer Stelle überdeckt?"""
    wort = wort or teil
    stellen = [(st["start"], st["ende"]) for f in funde for st in f["stellen"]]
    vorkommen = [m.start() + teil.index(wort) for m in re.finditer(re.escape(teil), text)]
    return bool(vorkommen) and all(any(s <= a and a + len(wort) <= e for s, e in stellen) for a in vorkommen)


def test_nie_liste_namen(monkeypatch):
    """Neue Semantik (Vertrag v2, Abschnitt 3): NIE-Einträge sind Schutzhüllen – was ganz darin liegt,
    bleibt stehen; Namensbestandteile sind nur noch eigene Funde, wo sie allein stehen."""
    text = ("Sehr geehrter Herr Peter Schmidt, Ihre Beraterin Sabine Schmidt hat den Antrag von Karl Schmidtke "
            "erhalten. Herr Schmidtke und Herr Schmidt bestätigen.")
    kandidaten = _kandidaten_aus(text, "Peter Schmidt", "Sabine Schmidt", "Karl Schmidtke")
    monkeypatch.setattr(na, "finde_personen", lambda t: kandidaten)
    # Eintrag "Schmidt": nur der nackte Nachname wird freigegeben, Vollnamen und "Schmidtke" bleiben
    funde = analysiere_text(text, {"namen"}, ["Schmidt"], [])
    f = paare(funde)
    assert ("namen", "Peter Schmidt") in f and ("namen", "Sabine Schmidt") in f and ("namen", "Karl Schmidtke") in f
    assert ("namen", "Schmidt") not in f and ("namen", "Schmidtke") in f
    assert not gedeckt(funde, text, "Herr Schmidt bestätigen")
    # Eintrag "Sabine Schmidt": Vollname frei (ihr Nachname bleibt dort stehen), Bestandteil "Schmidt" von
    # Peter Schmidt wird allein stehend geschwärzt
    funde, hinweise = analyse._analysiere(text, {"namen"}, ["Sabine Schmidt"], [])
    f = paare(funde)
    assert ("namen", "Sabine Schmidt") not in f and ("namen", "Peter Schmidt") in f and ("namen", "Schmidt") in f
    assert "Durch NIE-Liste freigegeben: Sabine Schmidt" in hinweise
    s = text.index("Sabine Schmidt")
    assert not any(st["start"] < s + 14 and s < st["ende"] for x in funde for st in x["stellen"])
    # Firmenname (kommt im Text nicht vor) gibt keinen Bestandteil frei
    f = paare(analysiere_text(text, {"namen"}, ["Schmidt Versicherungsmakler GmbH"], []))
    assert ("namen", "Schmidt") in f


# ----------------------------------------------------------------------
# M-47: IMMER-Begriffe
# ----------------------------------------------------------------------
def test_immer_begriffe(monkeypatch):
    monkeypatch.setattr(na, "finde_personen", lambda text: _kandidaten_aus(text, "Max Mustermann"))
    text = ("Allianz Lebensversicherungs-AG, Vertrag LV-1 für Max Mustermann. Die Allianz zahlt. "
            "Kostenstelle 4711, Filiale Nürnberg Süd, Allianzarena.")
    funde = analysiere_text(text, ALLE, [], ["Allianz", "Kostenstelle 4711", "Nürnberg Süd", "NichtImText"])
    begriffe = [f for f in funde if f["kategorie"] == "begriff"]
    assert [f["text"] for f in begriffe] == ["Allianz", "Kostenstelle 4711", "Nürnberg Süd"]
    assert all(f["ersatz"] == "[BEGRIFF]" and f["anzeige"] == analyse.ANZEIGE_BEGRIFF for f in begriffe)
    assert begriffe[0]["anzahl"] == 2                                   # "Allianzarena" zählt nicht (Ganzwort)
    # keine Zerlegung in Bestandteile, Personen-Buchstaben unabhängig
    texte = [f["text"] for f in funde]
    assert "4711" not in texte and "Kostenstelle" not in texte and "Lebensversicherungs" not in texte
    assert next(f for f in funde if f["text"] == "Max Mustermann")["ersatz"] == "[PERSON A]"
    # Ohne Namen-Häkchen funktionieren die Begriffe weiterhin
    f = paare(analysiere_text(text, OHNE_NAMEN, [], ["Allianz"]))
    assert ("begriff", "Allianz") in f


# ----------------------------------------------------------------------
# M-23: Pseudonyme (ohne Modell, über feste Kandidaten)
# Neue Semantik (Vertrag v2): ein Fund je Schreibweisen-Klasse (Groß/Klein egal), Namensbestandteile
# sind eigene Funde nur, wo sie allein stehen (sonst gehen sie in der Stelle des Vollnamens auf).
# ----------------------------------------------------------------------
def _mit_kandidaten(monkeypatch, text, *namen):
    kandidaten = _kandidaten_aus(text, *namen)
    monkeypatch.setattr(na, "finde_personen", lambda t: kandidaten)
    return {f["text"]: f["ersatz"] for f in analysiere_text(text, {"namen"}, [], [])}


def _stellen_ersatz(monkeypatch, text, *namen):
    """{Text jeder geschwärzten Stelle: Platzhalter} – was am Ende im Dokument steht."""
    kandidaten = _kandidaten_aus(text, *namen)
    monkeypatch.setattr(na, "finde_personen", lambda t: kandidaten)
    aus = {}
    for f in analysiere_text(text, {"namen"}, [], []):
        for st in f["stellen"]:
            aus.setdefault(st["text"], set()).add(f["ersatz"])
    return aus


def test_pseudonyme_reihenfolge_und_familie(monkeypatch):
    text = ("Sehr geehrter Herr Mustermann,\nIhre Ehefrau Anna Mustermann ist eingetragen. Ihr Sohn Ben Mustermann "
            "ist mitversichert. Ihr Vermittler Peter Schmidt hat uns die Unterlagen vorgelegt.\nFrau Mustermann erhält "
            "die Rente. Anna unterschreibt, Herr Schmidt bestätigt.")
    e = _mit_kandidaten(monkeypatch, text, "Mustermann", "Anna Mustermann", "Ben Mustermann", "Peter Schmidt")
    assert e["Anna Mustermann"] == "[PERSON A]" and e["Ben Mustermann"] == "[PERSON B]" and e["Peter Schmidt"] == "[PERSON C]"
    assert e["Mustermann"] == "[FAMILIE A]"                            # mehrere Träger -> Familie
    assert e["Anna"] == "[PERSON A]" and e["Schmidt"] == "[PERSON C]"   # allein stehende Bestandteile
    assert "Ben" not in e, "steht nur im Vollnamen -> geht in dessen Stelle auf"


def test_pseudonyme_varianten_derselben_person(monkeypatch):
    text = ("Der Vertrag von Dr. Max Mustermann wurde geprüft. Mustermann, Max ist Versicherungsnehmer. "
            "Herr Mustermann erhält die Leistung. MAX MUSTERMANN unterschreibt. Max zahlt.")
    funde = []
    kandidaten = _kandidaten_aus(text, "Max Mustermann", "Mustermann, Max", "Mustermann", "MAX MUSTERMANN")
    monkeypatch.setattr(na, "finde_personen", lambda t: kandidaten)
    funde = analysiere_text(text, {"namen"}, [], [])
    e = {f["text"]: f for f in funde}
    assert {f["ersatz"] for f in funde} == {"[PERSON A]"}
    assert {"Max Mustermann", "Mustermann, Max", "Mustermann", "Max"} <= set(e)
    assert "MAX MUSTERMANN" not in e, "Versalien sind eine Stelle desselben Funds (KQ-01)"
    assert [st["text"] for st in e["Max Mustermann"]["stellen"]] == ["Max Mustermann", "MAX MUSTERMANN"]
    assert e["Max Mustermann"]["anzahl"] == 2
    text = "Versicherungsnehmer: MAX MÜLLER\nSehr geehrter Herr Müller, Max Müller ist versichert."
    kandidaten2 = _kandidaten_aus(text, "MAX MÜLLER", "Müller", "Max Müller")
    monkeypatch.setattr(na, "finde_personen", lambda t: kandidaten2)
    funde = analysiere_text(text, {"namen"}, [], [])
    e = {f["text"]: f for f in funde}
    assert {f["ersatz"] for f in funde} == {"[PERSON A]"}
    assert set(e) == {"MAX MÜLLER", "Müller"}, "auch Umlaut-Versalien: ein Fund, zwei Stellen"
    assert [st["text"] for st in e["MAX MÜLLER"]["stellen"]] == ["MAX MÜLLER", "Max Müller"]


def test_pseudonyme_verschiedene_personen(monkeypatch):
    text = "Sehr geehrte Frau Anna Berg, Ihr Nachbar Herr Bergmann hat den Schaden gemeldet. Frau Berg und Herr Bergmann."
    e = _mit_kandidaten(monkeypatch, text, "Anna Berg", "Bergmann", "Berg")
    assert e["Anna Berg"] == "[PERSON A]" and e["Berg"] == "[PERSON A]" and e["Bergmann"] == "[PERSON B]"
    text = "Versicherungsnehmer Max Mustermann, mitversichert sein Sohn Maximilian Mustermann. Max und Maximilian."
    e = _mit_kandidaten(monkeypatch, text, "Max Mustermann", "Maximilian Mustermann", "Max", "Maximilian")
    assert e["Max Mustermann"] == "[PERSON A]" and e["Maximilian Mustermann"] == "[PERSON B]"
    assert e["Max"] == "[PERSON A]" and e["Maximilian"] == "[PERSON B]"
    assert "Mustermann" not in e, "Nachname steht nirgends allein"
    text = "Anna Weber ist die Ehefrau von Thomas Weber. Frau Weber erhält Leistungen, Herr Weber nicht."
    e = _mit_kandidaten(monkeypatch, text, "Anna Weber", "Thomas Weber", "Weber")
    assert e["Weber"] == "[FAMILIE A]" and e["Anna Weber"] == "[PERSON A]" and e["Thomas Weber"] == "[PERSON B]"
    text = "Versicherungsnehmer: Hans Müller. Bezugsberechtigt: Hans Müller junior. Gutachter: Dr. Müller."
    e = _mit_kandidaten(monkeypatch, text, "Hans Müller", "Hans Müller junior", "Müller")
    assert set(e.values()) == {"[PERSON A]"}


def test_pseudonyme_gruppe_aus_tabelle_und_adressfenster(monkeypatch):
    text = "Herrn\nProf. Dr. Hans-Jürgen\nWeber\nLindenallee 7\n90402 Nürnberg\nSehr geehrter Herr Weber,"
    e = _mit_kandidaten(monkeypatch, text, ("Hans-Jürgen", "Hans-Jürgen Weber"), ("Weber", "Hans-Jürgen Weber"))
    assert e == {"Hans-Jürgen": "[PERSON A]", "Weber": "[PERSON A]"}
    text = "Name      Vorname\nMustermann   Max\nMustermann   Erika\n"
    e = _mit_kandidaten(monkeypatch, text, ("Mustermann", "Max Mustermann"), ("Max", "Max Mustermann"),
                        ("Erika", "Erika Mustermann"))
    assert e["Max"] == "[PERSON A]" and e["Erika"] == "[PERSON B]" and e["Mustermann"] == "[FAMILIE A]"


def test_bestandteile_mindestlaenge_und_partikel(monkeypatch):
    text = ("Versicherungsnehmer: Dr. med. Hans-Peter van der Berg und Frau Li Wu. Hans-Peter unterschreibt, "
            "Herr Berg zahlt, Peter ruft an, Wu bleibt.")
    e = _mit_kandidaten(monkeypatch, text, "Dr. med. Hans-Peter van der Berg", "Li Wu")
    assert "van" not in e and "der" not in e and "med." not in e and "Dr." not in e
    assert e["Hans-Peter"] == "[PERSON A]" and e["Berg"] == "[PERSON A]" and e["Peter"] == "[PERSON A]"
    assert "Li" not in e and "Wu" not in e and e["Li Wu"] == "[PERSON B]"   # < 3 Zeichen kein Bestandteil


def test_pseudonyme_genitiv_doppelname_und_komma_regel(monkeypatch):
    """Gutachten EQ-10: Genitiv derselben Person, Teil eines Doppelnamens, keine Komma-Vorname-Phantome."""
    text = "Herr Max Mustermann hat unterschrieben. Herr Max Mustermanns Vertrag läuft. Mustermanns Antrag."
    e = _stellen_ersatz(monkeypatch, text, "Max Mustermann", "Max Mustermanns")
    assert e == {"Max Mustermann": {"[PERSON A]"}, "Max Mustermanns": {"[PERSON A]"}, "Mustermanns": {"[PERSON A]"}}
    text = "Zeugin Sandra Klein-Hoffmann sah den Unfall. Frau Hoffmann bestätigt. Herr Weber auch."
    e = _stellen_ersatz(monkeypatch, text, "Sandra Klein-Hoffmann", "Hoffmann", "Weber")
    assert e["Sandra Klein-Hoffmann"] == e["Hoffmann"] == {"[PERSON A]"} and e["Weber"] == {"[PERSON B]"}
    text = "Sehr geehrte Frau Krüger, Max Mustermann ist versichert."
    kandidaten = [{"text": "Krüger", "start": 18, "ende": 24, "gruppe": "Krüger, Max"},
                  {"text": "Krüger, Max", "start": 18, "ende": 29, "gruppe": "Krüger, Max"},
                  {"text": "Max", "start": 26, "ende": 29, "gruppe": "Krüger, Max"},
                  {"text": "Max Mustermann", "start": 26, "ende": 40, "gruppe": None}]
    monkeypatch.setattr(na, "finde_personen", lambda t: kandidaten)
    funde = analysiere_text(text, {"namen"}, [], [])
    e = {f["text"]: f["ersatz"] for f in funde}
    assert "Krüger, Max" not in e
    assert e == {"Krüger": "[PERSON A]", "Max Mustermann": "[PERSON B]"}


def test_mehrdeutige_bestandteile_nicht_am_satzanfang(monkeypatch):
    """Vertrag Abschnitt 3: mehrdeutige Bestandteile nur mit Großschreibung und nicht am Satzanfang ohne
    Personenkontext ("Lange Zeit ..."), nie als Teil eines fremden Bindestrich-Worts."""
    text = ("Versicherungsnehmerin ist Petra Lange. Lange Zeit war unklar, wie lange es dauert. Frau Lange zahlt. "
            "Die Kraftfahrt-Versicherung von Herrn Kraftfahrt Moser zahlt.")
    funde = []
    kandidaten = _kandidaten_aus(text, "Petra Lange", "Kraftfahrt Moser")
    monkeypatch.setattr(na, "finde_personen", lambda t: kandidaten)
    funde = analysiere_text(text, {"namen"}, [], [])
    assert gedeckt(funde, text, "Frau Lange zahlt", "Lange"), "mit Anrede"
    assert not gedeckt(funde, text, "Lange Zeit", "Lange"), "Satzanfang ohne Personenkontext"
    assert not gedeckt(funde, text, "lange es", "lange"), "kleingeschrieben nie"
    assert not gedeckt(funde, text, "Kraftfahrt-Versicherung", "Kraftfahrt")
    assert gedeckt(funde, text, "Kraftfahrt Moser")


# ----------------------------------------------------------------------
# M-15 / M-22: Namenserkennung mit Modell
# ----------------------------------------------------------------------
@braucht_modell
@pytest.mark.parametrize("text, erwartet", [
    ("Versicherungsnehmer: MAX MUSTERMANN", {"MAX MUSTERMANN"}),
    ("Antragsteller: MUSTERMANN, MAX", {"MUSTERMANN, MAX"}),
    ("Mit freundlichen Grüßen\ni. A. Sabine Krüger\nSchmidt Finanz GmbH", {"Sabine Krüger"}),
    ("Zeugin des Unfalls war Frau Schulze aus der Nachbarschaft.", {"Schulze"}),
    ("Herrn\nProf. Dr. Hans-Jürgen\nWeber\nLindenallee 7\n90402 Nürnberg", {"Hans-Jürgen", "Weber"}),
    ("Sehr geehrter Herr Mustermann,\nIhr Sohn Ben ist mitversichert.", {"Mustermann", "Ben"}),
    ("Bearbeiter: Frau Weber, Tel. 0911 123456", {"Weber"}),
    ("Unfallgegner: Frau Katarzyna Nowak, Kennzeichen M-X 1E, Tel. 0911 / 123 45 67", {"Katarzyna Nowak"}),
    ("Praxis Dr. med. Anna Berg, Fachärztin für Innere Medizin", {"Anna Berg"}),
    ("Dr. Klaus Weber                 Sabine Lang\nVorstand                        Kundenbetreuung", {"Klaus Weber", "Sabine Lang"}),
])
def test_ner_findet_namen(text, erwartet):
    assert erwartet <= na.finde_personen_ner(text)


@braucht_modell
def test_ner_tabelle_und_adressfenster():
    tabelle = ("Name                  Vorname      Geburtsdatum   Rolle\n"
               "Mustermann            Max          02.09.1983     VN\n"
               "Mustermann            Erika        15.05.1985     Ehepartner\n"
               "Nguyen                Thi Lan      12.07.1990     Partnerin\n")
    k = {x["text"]: x["gruppe"] for x in na.finde_personen(tabelle)}
    assert {"Mustermann", "Max", "Erika", "Nguyen", "Thi Lan"} <= set(k)
    assert k["Max"] == "Max Mustermann" and k["Thi Lan"] == "Thi Lan Nguyen"
    assert not any("  " in t for t in k)                              # keine Zellen-übergreifenden Entitäten
    adresse = "Herrn\nMax Mustermann\nLange Straße 12\n90402 Nürnberg\n\nSehr geehrter Herr Mustermann,"
    namen = na.finde_personen_ner(adresse)
    assert "Max Mustermann" in namen and not any("Straße" in n or "Lange" in n for n in namen)


@braucht_modell
@pytest.mark.parametrize("text", [
    "Steuer-ID: 86095742719\nZulagennummer: 86 123456 M 789\nKindergeld-Nr: 009FK407160",
    "Wir empfehlen Ihnen Rürup. Gothaer hat uns geschrieben. Basisrente (Rürup) und PrivatRente.",
    "Versicherte Person geb. 02.09.1983", "Kennzeichen HD-XY 987", "Allianz Lebensversicherungs-AG",
    "Interner Vermerk Schadenabteilung", "IBAN: DE89 3704 0044 0532 0130 00\nBIC: COBADEFFXXX",
    "Vergleichsangebote hatten Sie auch von der Alten Leipziger, der Hannoverschen, Swiss Life, Canada Life, "
    "der Bayerischen, HDI, Debeka, DKV, Signal Iduna, Gothaer, Württembergische, Hallesche, Barmenia, "
    "Continentale, Stuttgarter, LV 1871, Condor, Ergo, Zurich, Generali, Axa, R+V und Hanse Merkur eingeholt.",
])
def test_ner_fehlalarme_gefiltert(text):
    assert na.finde_personen_ner(text) == set()


@braucht_modell
def test_ner_versicherer_hinter_anrede_bleibt_person():
    assert "Nürnberger" in na.finde_personen_ner("Sehr geehrter Herr Nürnberger, vielen Dank.")
    assert "Angebot Nürnberger" not in na.finde_personen_ner("Angebot Nürnberger: Eva Berg")


# ----------------------------------------------------------------------
# Korpus-Trefferquote (Audit-Korpus, 53 Schnipsel, 252 PII-Elemente)
# ----------------------------------------------------------------------
def _fold(s):
    return re.sub(r"[A-Z]", lambda m: m.group(0).lower(), s)


def _spannen(nadel, text):
    return [(m.start(), m.end()) for m in re.finditer(re.escape(_fold(nadel)), _fold(text))]


def _abgedeckt(item, text, funde):
    """Ist das erwartete Element vollständig von Stellen (beliebiger Funde) überdeckt? Neue Semantik
    (Vertrag v2): gezählt werden die STELLEN, die geschwärzt würden – ein Fund kann Stellen in mehreren
    Schreibweisen haben ("0911-123456" und "(0911) 123456" sind eine Nummer)."""
    s = item["text"]
    if "kontext" in item:
        ka = text.index(item["kontext"])
        a = ka + item["kontext"].index(s)
    else:
        a = _spannen(s, text)[0][0]
    b = a + len(s)
    gedeckt = [False] * (b - a)
    for f in funde:
        for st in f["stellen"]:
            for i in range(max(a, st["start"]), min(b, st["ende"])):
                gedeckt[i - a] = True
    rest = "".join(c for c, g in zip(s, gedeckt) if not g)
    return not re.sub(r"[^0-9A-Za-zÄÖÜäöüß]", "", rest)


def _korpus_quote(aktive, nur_kategorien=None):
    korpus = json.loads((DATEN / "korpus_erkennung.json").read_text(encoding="utf-8"))
    statistik = {}
    for sn in korpus:
        funde = analysiere_text(sn["text"], aktive, [], [])
        for item in sn["erwartet"]:
            if nur_kategorien is not None and item["kategorie"] not in nur_kategorien:
                continue
            d = statistik.setdefault(item["kategorie"], [0, 0])
            d[1] += 1
            d[0] += _abgedeckt(item, sn["text"], funde)
    return statistik


# Trefferquote vor der Überarbeitung (Audit, Standard-Kategorien): gesamt 138/252, darunter
# telefon 15/27, geburt 10/26, strasse 13/32, plzort 13/25, vertrag 13/34, kfz 0/7, kindergeld 0/2.
MINDESTQUOTE = {
    "iban": 1.0, "email": 1.0, "telefon": 0.95, "geburt": 0.9, "strasse": 0.95, "plzort": 0.95, "vertrag": 0.95,
    "svnr": 1.0, "steuerid": 1.0, "kfz": 1.0, "kindergeld": 1.0, "steuernr": 1.0, "kvnr": 1.0, "fin": 1.0,
    "bic": 1.0, "kreditkarte": 1.0, "ausweis": 1.0, "mandat": 1.0, "postfach": 1.0,
}


def test_korpus_muster_trefferquote():
    statistik = _korpus_quote(OHNE_NAMEN, nur_kategorien=set(MINDESTQUOTE))
    gesamt = sum(v[1] for v in statistik.values())
    gefunden = sum(v[0] for v in statistik.values())
    assert gesamt == 196
    fehlschlaege = {k: v for k, v in statistik.items() if v[0] / v[1] < MINDESTQUOTE[k]}
    assert not fehlschlaege, fehlschlaege
    assert gefunden / gesamt >= 0.98


@braucht_modell
def test_korpus_namen_trefferquote():
    statistik = _korpus_quote(STANDARD, nur_kategorien={"namen"})
    gefunden, gesamt = statistik["namen"]
    assert gesamt == 56
    assert gefunden / gesamt >= 0.9, statistik        # vorher 46/56


# ----------------------------------------------------------------------
# Fehlalarme: realistische Briefe (Versicherer, Beträge, Paragrafen bleiben stehen)
# ----------------------------------------------------------------------
def _briefe():
    return json.loads((DATEN / "briefe_fehlalarme.json").read_text(encoding="utf-8"))


def _ueberdeckt_phrase(text, phrase, funde):
    """Überschneidet ein Fund eine Fundstelle der Phrase?"""
    treffer = []
    for a, b in _spannen(phrase, text):
        for f in funde:
            for fa, fb in analyse._spannen(text, f["text"]):
                if fa < b and a < fb:
                    treffer.append((phrase, f["kategorie"], f["text"]))
    return treffer


def test_briefe_muster_keine_fehlalarme():
    for brief in _briefe():
        funde = analysiere_text(brief["text"], STANDARD - {"namen"}, [], [])
        kollisionen = [k for p in brief["behalten"] for k in _ueberdeckt_phrase(brief["text"], p, funde)]
        assert not kollisionen, (brief["id"], kollisionen)
        for pflicht in brief["pflicht"]:
            if pflicht["kategorie"] == "namen":
                continue
            assert any(f["kategorie"] == pflicht["kategorie"] and pflicht["text"] in f["text"] for f in funde), \
                (brief["id"], pflicht)


@braucht_modell
def test_briefe_namen_keine_fehlalarme():
    for brief in _briefe():
        funde = analysiere_text(brief["text"], STANDARD, [], [])
        kollisionen = [k for p in brief["behalten"] for k in _ueberdeckt_phrase(brief["text"], p, funde)]
        assert not kollisionen, (brief["id"], kollisionen)
        namen = {f["text"] for f in funde if f["kategorie"] == "namen"}
        for pflicht in brief["pflicht"]:
            if pflicht["kategorie"] == "namen":
                assert pflicht["text"] in namen, (brief["id"], pflicht, namen)
        for falsch in ("Rürup", "Zulagennummer", "HD-XY", "Coburg", "Steuer-ID", "Steuer", "Sohn", "Person"):
            assert falsch not in namen, (brief["id"], falsch)
        # Pseudonyme eindeutig je Person: ein Platzhalter gehört nie zu zwei verschiedenen Nachnamen
        nach_platzhalter = {}
        for f in funde:
            if f["kategorie"] == "namen" and f["anzeige"] == "Name" and " " in f["text"]:
                nach_platzhalter.setdefault(f["ersatz"], set()).add(f["text"].split()[-1])
        assert all(len(v) == 1 for v in nach_platzhalter.values()), nach_platzhalter


# ----------------------------------------------------------------------
# PDF-Analyse
# ----------------------------------------------------------------------
def _text_pdf(pfad: Path, *seiten, feld=None):
    doc = fitz.open()
    for inhalt in seiten:
        seite = doc.new_page()
        seite.insert_text((50, 72), inhalt, fontsize=11)
    if feld:
        seite = doc[-1]
        w = fitz.Widget()
        w.field_name, w.field_type = "feld", fitz.PDF_WIDGET_TYPE_TEXT
        w.rect, w.field_value = fitz.Rect(50, 300, 400, 320), feld
        seite.add_widget(w)
    doc.save(pfad)
    doc.close()
    return pfad


def test_analysiere_pdf_seiten_und_formularfeld(tmp_path):
    pdf = _text_pdf(tmp_path / "brief.pdf",
                    "Herrn\nMax Mustermann\nHauptstraße 12a\n90402 Nürnberg\nVersicherungsschein-Nr.: LV-2024-887766",
                    "Sehr geehrter Herr Mustermann,\nIBAN DE89 3704 0044 0532 0130 00\nTel. 0911 / 123 45 67",
                    feld="geb. 02.09.1983")
    meldungen, schritte = [], []
    e = analysiere_pdf(pdf, OHNE_NAMEN, [], ["LV-2024-887766"], melde=meldungen.append,
                       fortschritt=lambda a, b: schritte.append((a, b)))
    assert e["fehler"] is None and e["seiten"] == 2 and e["ocr_seiten"] == 0 and e["ocr_cache"] == {}
    assert set(e) >= {"datei", "funde", "warnungen", "hinweise", "fehler", "seiten", "ocr_seiten", "ocr_cache"}
    assert schritte == [(1, 2), (2, 2)]
    nach_text = {f["text"]: f for f in e["funde"]}
    for f in e["funde"]:
        pruefe_fund_struktur(f)
    assert nach_text["Hauptstraße 12a"]["seiten"] == [1]
    assert nach_text["90402 Nürnberg"]["seiten"] == [1]
    assert nach_text["DE89 3704 0044 0532 0130 00"]["seiten"] == [2]
    assert nach_text["0911 / 123 45 67"]["seiten"] == [2]
    assert nach_text["02.09.1983"]["seiten"] == [2]                     # Formularfeld nach doc.bake()
    assert nach_text["LV-2024-887766"]["kategorie"] == "begriff" and nach_text["LV-2024-887766"]["seiten"] == [1]


def test_analysiere_pdf_abbruch_und_fehler(tmp_path):
    pdf = _text_pdf(tmp_path / "a.pdf", "Hallo")
    ev = threading.Event()
    ev.set()
    e = analysiere_pdf(pdf, STANDARD, [], [], abbruch=ev)
    assert e["fehler"] == "Abgebrochen" and e["funde"] == []
    kaputt = tmp_path / "kaputt.pdf"
    kaputt.write_bytes(b"kein pdf")
    assert analysiere_pdf(kaputt, STANDARD, [], [])["fehler"].startswith("Konnte nicht geöffnet werden")


def test_analysiere_pdf_xfa_warnung(tmp_path):
    pfad = tmp_path / "xfa.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((50, 72), "Formular")
    doc.xref_set_key(doc.pdf_catalog(), "AcroForm", "<</XFA (dummy)>>")
    doc.save(pfad)
    doc.close()
    e = analysiere_pdf(pfad, OHNE_NAMEN, [], [])
    assert "XFA-Formular: Feldinhalte können nicht geprüft werden" in e["warnungen"]


def _bild_pdf(pfad: Path):
    doc = fitz.open()
    seite = doc.new_page()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 100, 100), False)
    pix.clear_with(255)
    seite.insert_image(seite.rect, pixmap=pix)
    doc.save(pfad)
    doc.close()
    return pfad


class _FakeDienst:
    """OcrDienst-Attrappe nach Vertrag: woerter(pdf_pfad, seite_nr0, dpi=300, clip=None)."""

    def __init__(self):
        self.aufrufe = []

    def woerter(self, pdf_pfad, seite_nr0, dpi=300, clip=None):
        self.aufrufe.append((seite_nr0, clip))
        return [(50, 70, 80, 82, "Max"), (85, 70, 150, 82, "Mustermann"), (50, 90, 100, 102, "IBAN"),
                (105, 90, 300, 102, "DE89"), (305, 90, 340, 102, "3704"), (345, 90, 380, 102, "0044"),
                (385, 90, 420, 102, "0532"), (425, 90, 460, 102, "0130"), (465, 90, 480, 102, "00"),
                (50, 110, 100, 122, "Tel."), (105, 110, 200, 122, "0911"), (205, 110, 260, 122, "123456")], None

    def schliessen(self):
        pass


def test_analysiere_pdf_ocr_neue_schnittstelle(tmp_path, monkeypatch):
    pdf = _bild_pdf(tmp_path / "scan.pdf")
    monkeypatch.setattr(ocr_modul, "ocr_noetig", lambda seite: "seite", raising=False)
    dienst = _FakeDienst()
    e = analysiere_pdf(pdf, OHNE_NAMEN, [], [], ocr=dienst)
    assert e["fehler"] is None and e["ocr_seiten"] == 1 and dienst.aufrufe == [(0, None)]
    assert 0 in e["ocr_cache"] and e["ocr_cache"][0][0][4] == "Max"
    f = paare(e["funde"])
    assert ("iban", "DE89 3704 0044 0532 0130 00") in f and ("telefon", "0911 123456") in f
    assert all(x["seiten"] == [1] for x in e["funde"])
    assert any("per OCR gelesen" in w for w in e["warnungen"])


def test_analysiere_pdf_ocr_bildbereiche(tmp_path, monkeypatch):
    pdf = _bild_pdf(tmp_path / "bild.pdf")
    monkeypatch.setattr(ocr_modul, "ocr_noetig", lambda seite: "bilder", raising=False)
    dienst = _FakeDienst()
    e = analysiere_pdf(pdf, OHNE_NAMEN, [], [], ocr=dienst)
    assert len(dienst.aufrufe) == 1 and dienst.aufrufe[0][1] is not None       # clip auf den Bildbereich
    assert ("iban", "DE89 3704 0044 0532 0130 00") in paare(e["funde"])
    assert any("Text in Bildern per OCR" in h for h in e["hinweise"])


def test_analysiere_pdf_ocr_alte_schnittstelle(tmp_path, monkeypatch):
    """Rückfall, solange ocr.py nur ist_scan_seite/ocr_textpage bietet."""
    pdf = _bild_pdf(tmp_path / "scan_alt.pdf")
    monkeypatch.delattr(ocr_modul, "ocr_noetig", raising=False)
    monkeypatch.delattr(ocr_modul, "OcrDienst", raising=False)
    monkeypatch.setattr(ocr_modul, "ist_scan_seite", lambda seite: True, raising=False)

    am_leben = []

    def fake_textpage(seite, melde=None):
        doc = fitz.open()
        s = doc.new_page()
        s.insert_text((50, 72), "Kunden-Nr. 4711 Tel. 0911 123456", fontsize=11)
        am_leben.append((doc, s))                 # Textpage braucht die lebende Seite
        return s.get_textpage(), "Deutsche OCR-Sprachdatei fehlt — nutze Englisch (Test)"
    monkeypatch.setattr(ocr_modul, "ocr_textpage", fake_textpage, raising=False)
    e = analysiere_pdf(pdf, OHNE_NAMEN, [], [])
    assert e["ocr_seiten"] == 1 and 0 in e["ocr_cache"]
    assert ("vertrag", "4711") in paare(e["funde"]) and ("telefon", "0911 123456") in paare(e["funde"])
    assert any("Sprachdatei" in w for w in e["warnungen"])


def test_woerter_zu_text_zeilen():
    woerter = [(50, 90, 100, 102, "IBAN"), (105, 90, 300, 102, "DE89"), (50, 70, 80, 82, "Max"), (85, 70, 150, 82, "Mustermann")]
    assert analyse._woerter_zu_text(woerter) == "Max Mustermann\nIBAN DE89"
    assert analyse._woerter_zu_text([]) == ""


def test_analysiere_pdf_ohne_text(tmp_path, monkeypatch):
    pdf = _bild_pdf(tmp_path / "leer.pdf")
    monkeypatch.setattr(ocr_modul, "ocr_noetig", lambda seite: "nein", raising=False)
    e = analysiere_pdf(pdf, OHNE_NAMEN, [], [])
    assert e["funde"] == [] and any("Kein Text lesbar" in w for w in e["warnungen"])


# ----------------------------------------------------------------------
# Phase 2: Fund-Format v2, Modell, Meldungen
# ----------------------------------------------------------------------
def _seiten_pdf(pfad: Path, *seiten, fontsize=11):
    doc = fitz.open()
    for zeilen in seiten:
        seite = doc.new_page()
        y = 72
        for z in zeilen:
            seite.insert_text((50, y), z, fontsize=fontsize, fontname="helv")
            y += fontsize * 1.5
    doc.save(pfad)
    doc.close()
    return pfad


def test_fund_format_v2_und_modell(tmp_path):
    pdf = _seiten_pdf(tmp_path / "v2.pdf", ["Kunden-Nr. 4711", "IBAN DE89 3704 0044 0532 0130 00"],
                      ["Nochmal IBAN DE89370400440532013000 und Tel. 0911 123456"])
    e = analysiere_pdf(pdf, OHNE_NAMEN, [], [])
    assert e["modell"] is not None and e["modell"].fingerabdruck and e["profil"] == "hoch"
    assert isinstance(e["meldungen"], list) and e["text_lesbar"] is True and e["felder"] == []
    ids = [f["id"] for f in e["funde"]]
    assert len(set(ids)) == len(ids) and all(re.fullmatch(r"f\d+", i) for i in ids)
    iban = next(f for f in e["funde"] if f["kategorie"] == "iban")
    assert set(iban) >= {"id", "stellen", "quellen", "sicherheit", "hinweis", "kategorie", "anzeige", "text",
                         "ersatz", "seiten", "anzahl", "kontext"}
    assert iban["anzahl"] == len(iban["stellen"]) == 2 and iban["seiten"] == [1, 2]
    assert iban["text"] == iban["stellen"][0]["text"] == "DE89 3704 0044 0532 0130 00"
    assert iban["stellen"][1]["text"] == "DE89370400440532013000" and iban["sicherheit"] == 1.0
    modell = e["modell"]
    for f in e["funde"]:
        for st in f["stellen"]:
            assert st["an"] is True and modell.seiten[st["seite"]].text[st["start"]:st["ende"]] == st["text"]
    assert "muster.iban" in iban["quellen"] and "weitergabe" in iban["quellen"]


def test_versalien_und_gemischte_schreibweise_ein_fund_alle_stellen(tmp_path):
    """Gutachten KQ-01: Adressfenster in Versalien + Anrede normal – ein Fund, beide Stellen (Analyse)."""
    pdf = _seiten_pdf(tmp_path / "versalien.pdf",
                      ["Herrn", "MAX MUSTERMANN", "Hauptstraße 12", "90402 Nürnberg", "",
                       "Sehr geehrter Herr Max Mustermann,", "Kontakt: Max.Mustermann@Example.de oder",
                       "max.mustermann@example.de, IBAN de89 3704 0044 0532 0130 00 bzw. DE89 3704 0044 0532 0130 00"])
    e = analysiere_pdf(pdf, STANDARD, [], [])
    texte = {st["text"] for f in e["funde"] for st in f["stellen"]}
    assert {"MAX MUSTERMANN", "Max Mustermann", "Max.Mustermann@Example.de", "max.mustermann@example.de",
            "de89 3704 0044 0532 0130 00", "DE89 3704 0044 0532 0130 00"} <= texte
    mails = [f for f in e["funde"] if f["kategorie"] == "email"]
    assert len(mails) == 1 and mails[0]["anzahl"] == 2


def test_silbentrennung_t02a_fund_ist_ganzes_wort():
    """Gutachten KQ-02: kein Fund 'Muster-' mehr."""
    e = analysiere_pdf(DATEN / "t02a.pdf", STANDARD, [], [])
    texte = {f["text"] for f in e["funde"]}
    assert "Mustermann" in texte and not any(t.endswith("-") for t in texte)


@pytest.mark.parametrize("text, nie", [
    ("Versicherungsnummer 12 345678 A 123", ["12 345678 A 123"]),
    ("Kunden-Nr. 0171 2345678", ["0171 2345678"]),
    ("Konto-Nr. DE89 3704 0044 0532 0130 00", ["DE89 3704 0044 0532 0130 00"]),
    ("Kunden-Nr. 0911 123456", ["0911 123456"]),
    ("Versicherungsnummer 65 170839 G 537", ["65 170839 G 537"]),
])
def test_nie_liste_bei_zwei_kategorien_stuerzt_nicht_ab(text, nie):
    """Gutachten KQ-03/EQ-03: freigegebener Text in einer zweiten Kategorie -> kein TypeError."""
    funde, hinweise = analyse._analysiere(text, ALLE, nie, [])
    assert [f for f in funde if f["kategorie"] != "plzort"] == []
    assert sum("NIE-Liste" in h for h in hinweise) >= 1


def test_nie_huelle_schuetzt_bruchstuecke():
    """Gutachten KQ-04: freigegebene eigene IBAN -> keine '[TELEFON]'-Bruchstücke darin; Schreibweise der
    NIE-Liste ohne Leerzeichen gibt die IBAN ebenfalls frei."""
    for eintrag in ("DE89 3704 0044 0532 0130 00", "DE89370400440532013000"):
        funde = analysiere_text("Konto-Nr. DE89 3704 0044 0532 0130 00", OHNE_NAMEN, [eintrag], [])
        assert funde == [], (eintrag, paare(funde))
    # Eine nicht freigegebene zweite Nummer bleibt Fund
    f = paare(analysiere_text("Konto DE89 3704 0044 0532 0130 00, Tel. 0171 2345678", OHNE_NAMEN,
                              ["DE89370400440532013000"], []))
    assert f == [("telefon", "0171 2345678")]


def test_formularfeld_geburtsdatum_neben_etikett(tmp_path):
    """Gutachten S-02/EQ-02: Feldwert neben 'Geburtsdatum:' wird als Geburtsdatum erkannt (E2E d-03)."""
    e = analysiere_pdf(DATEN / "d_antrag_formular.pdf", OHNE_NAMEN, [], [])
    geburt = {f["text"] for f in e["funde"] if f["kategorie"] == "geburt"}
    assert "30.07.1988" in geburt and "02.12.1990" in geburt
    assert {f.name for f in e["felder"]} >= {"geburtsdatum", "iban", "telefon"}


def test_kammfeld_geburtsdatum_wird_erkannt(tmp_path):
    """Gutachten S-12: Kammfeld '30071988' hinter 'Geburtsdatum:' -> Fund geburt, eine Stelle."""
    doc = fitz.open()
    seite = doc.new_page()
    seite.insert_text((50, 100), "Geburtsdatum:", fontsize=10)
    w = fitz.Widget()
    w.field_name, w.field_type, w.rect, w.field_value = "geb", fitz.PDF_WIDGET_TYPE_TEXT, fitz.Rect(150, 88, 300, 106), "30071988"
    w.field_flags, w.text_maxlen = fitz.PDF_TX_FIELD_IS_COMB, 8
    seite.add_widget(w)
    pdf = tmp_path / "kamm.pdf"
    doc.save(pdf)
    doc.close()
    e = analysiere_pdf(pdf, OHNE_NAMEN, [], [])
    geburt = [f for f in e["funde"] if f["kategorie"] == "geburt"]
    assert [f["text"] for f in geburt] == ["30071988"] and geburt[0]["anzahl"] == 1


def test_anzahl_entspricht_den_stellen():
    """Gutachten EQ-18: 'anzahl' zählt genau die Stellen, die geschwärzt werden (keine 'max.'-Abkürzung)."""
    funde = analysiere_text("Versicherungsnehmer: Max Mustermann\nmax. 10 Tage, Max. Deckung", {"namen"}, [], [])
    for f in funde:
        assert f["anzahl"] == len(f["stellen"])
    assert all(st["text"] != "max" for f in funde for st in f["stellen"])


def test_meldungen_mit_codes(tmp_path):
    pdf = tmp_path / "xfa.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((50, 72), "Formular")
    doc.xref_set_key(doc.pdf_catalog(), "AcroForm", "<</XFA (dummy)>>")
    doc.save(pdf)
    doc.close()
    e = analysiere_pdf(pdf, OHNE_NAMEN, ["Eigene Firma GmbH"], [])
    codes = {m["code"] for m in e["meldungen"]}
    assert "XFA" in codes and all(set(m) == {"art", "code", "text", "seite"} for m in e["meldungen"])
    assert all(m["code"] == m["code"].upper() and m["art"] in ("fehler", "warnung", "hinweis") for m in e["meldungen"])
    leer = _bild_pdf(tmp_path / "leer.pdf")
    import anonymisierer.ocr as o
    e2 = analysiere_pdf(leer, OHNE_NAMEN, [], [], ocr=_FakeLeer())
    assert "KEIN_TEXT" in {m["code"] for m in e2["meldungen"]} or o is None


class _FakeLeer:
    def woerter(self, pdf_pfad, seite_nr0, dpi=300, clip=None):
        return [], None

    def schliessen(self):
        pass


def test_weitergabe_zwischen_dokumenten(tmp_path, monkeypatch):
    """Vertrag Abschnitt 4: weitergabe_anwenden sucht Namen/Kennungen aus allen Dokumenten eines Laufs in den
    anderen und ergänzt Stellen (quelle "weitergabe")."""
    a = _seiten_pdf(tmp_path / "a.pdf", ["Versicherungsnehmer: Erika Musterfrau", "IBAN DE89 3704 0044 0532 0130 00"])
    b = _seiten_pdf(tmp_path / "b.pdf", ["Gesprächsnotiz", "Rückruf bei Erika Musterfrau wegen",
                                         "Konto DE89370400440532013000 bestätigt"])
    ea = analysiere_pdf(a, STANDARD - {"namen"}, [], ["Erika Musterfrau"])
    eb = analysiere_pdf(b, {"telefon"}, [], [])
    namen_funde = [{"kategorie": "namen", "anzeige": "Name", "text": "Erika Musterfrau", "ersatz": "[PERSON A]",
                    "stellen": [{"seite": 0, "start": 0, "ende": 16, "an": True, "text": "Erika Musterfrau"}],
                    "quellen": ["ner"], "sicherheit": 0.6}]
    ea["funde"].extend(namen_funde)
    assert not any(f["kategorie"] == "iban" for f in eb["funde"])
    neu = analyse.weitergabe_anwenden([ea, eb])
    assert neu >= 2
    texte = {st["text"] for f in eb["funde"] for st in f["stellen"]}
    assert "Erika Musterfrau" in texte and "DE89370400440532013000" in texte
    iban_b = next(f for f in eb["funde"] if f["kategorie"] == "iban")
    assert iban_b["quellen"] == ["weitergabe"] and iban_b["anzahl"] == 1 and iban_b["seiten"] == [1]
    assert analyse.weitergabe_anwenden([ea, eb]) == 0, "zweiter Aufruf findet nichts Neues"


def test_lauf_wissen_sammelt_personen(tmp_path):
    lauf = analyse.LaufWissen()
    pdf = _seiten_pdf(tmp_path / "l.pdf", ["IBAN DE89 3704 0044 0532 0130 00"])
    analysiere_pdf(pdf, OHNE_NAMEN, [], [], lauf=lauf)
    assert ("iban", "de89370400440532013000") in lauf.kennungen


def test_analyse_laufzeit_skaliert_linear(monkeypatch):
    """Gutachten PERF-01: keine O(Funde x Text)- oder O(Funde²)-Nachbearbeitung (Weitergabe, Zusammenführen,
    Kontext, Seitenzuordnung). Gemessen mit linearen Ersatz-Mustern, damit nur der Kern zählt: vierfache
    Menge darf höchstens etwa vierfache Zeit kosten (großzügig: Faktor 7)."""
    import time
    from anonymisierer import muster

    linear = [("iban", "IBANs", "[IBAN]", lambda t: re.findall(r"DE\d\d(?: \d{4}){4} \d\d", t), True),
              ("telefon", "Telefon", "[TELEFON]", lambda t: re.findall(r"0911 \d{7}", t), True),
              ("vertrag", "Vertrag", "[VERTRAGS-NR]", lambda t: re.findall(r"(?<=Kunden-Nr\. )\d+", t), True)]
    monkeypatch.setattr(muster, "KATEGORIEN", linear)

    def text(n):
        return "\n".join(f"Vertrag {i}: Kunden-Nr. {1000000 + i}, Tel. 0911 {2000000 + i}, "
                         f"IBAN DE89 3704 0044 {i:04d} 0130 00 Betrag {i},00 EUR" for i in range(n))
    aktive = {"iban", "telefon", "vertrag"}
    analysiere_text(text(50), aktive, [], [])                         # Aufwärmen
    t0 = time.perf_counter()
    klein = analysiere_text(text(500), aktive, [], [])
    t1 = time.perf_counter()
    gross = analysiere_text(text(2000), aktive, [], [])
    t2 = time.perf_counter()
    assert len(gross) == 4 * len(klein) == 6000
    assert (t2 - t1) < 7 * max(t1 - t0, 0.05), (t1 - t0, t2 - t1)
    assert t2 - t1 < 30


# ----------------------------------------------------------------------
# Tabellenzellen: zweiter Namens-Durchgang je Zelle, Straßen nicht über Spaltenlücken
# (Entwicklungs-Benchmark 006_leistungsabrechnung: "Physiotherapie Santoro" übersehen,
#  "Am Kurpark | 946,21" als Straße geschwärzt)
# ----------------------------------------------------------------------
def _kurzzeilen_ki(namen_je_zeile):
    """Ersatz für namen.finde_personen, der wie die Kurzzeilen-Erkennung nur auf EIGENEN kurzen Zeilen
    Namen findet: {zeileninhalt: [name, ...]}."""
    def finde(text):
        aus, pos = [], 0
        for zeile in text.split("\n"):
            for name in namen_je_zeile.get(zeile.strip(), []):
                s = pos + zeile.index(name)
                aus.append({"text": name, "start": s, "ende": s + len(name), "gruppe": None})
            pos += len(zeile) + 1
        return aus
    return finde


def test_namen_in_tabellenzellen_zweiter_durchgang(monkeypatch):
    monkeypatch.setattr(na, "lade_ner", lambda: None)          # ohne Gegenprobe der KI (eigener Test unten)
    monkeypatch.setattr(na, "finde_personen", _kurzzeilen_ki({
        "Physiotherapie Santoro": ["Santoro"], "Betrag": ["Betrag"],
        "Physiotherapie Zieliński": ["Physiotherapie Zieliński"],
        "Behandlung bei Zieliński": ["Zieliński"]}))
    text = ("Behandlung bei Zieliński\n"
            "Datum\t\tLeistungserbringer\t\tBetrag\n"
            "02.03.2025\t\tPhysiotherapie Santoro\t\t1022,88\n"
            "02.05.2025\t\tPhysiotherapie Zieliński\t\t1796,41\n")
    funde = analysiere_text(text, {"namen"}, [], [])
    texte = {f["text"]: f for f in funde}
    assert "Santoro" in texte and "ner.zelle" in texte["Santoro"]["quellen"]
    assert "Betrag" not in texte                                   # Spaltenkopf, kein Name
    assert "Zieliński" in texte and "Physiotherapie Zieliński" not in texte
    assert all("Physiotherapie" not in text[s["start"]:s["ende"]] for f in funde for s in f["stellen"])
    # ohne Spaltenlücken läuft kein zweiter Durchgang
    aufrufe = []
    monkeypatch.setattr(na, "finde_personen", lambda t: aufrufe.append(t) or [])
    analysiere_text("Physiotherapie Santoro 1022,88", {"namen"}, [], [])
    assert len(aufrufe) == 1


def test_zellentext_behaelt_offsets():
    from anonymisierer.detektoren import klassisch
    text = "Kopf\nA\t\tB C\tD\nFließtext ohne Spalten\n\f\nX\t\tY"
    z = klassisch._zellentext(text)
    assert len(z) == len(text)
    for i, c in enumerate(text):
        if c not in "\t" and z[i].strip():
            assert z[i] == c
    assert z.split("\n")[1:5] == ["A", "", "B C", "D"]
    assert klassisch._zellentext("ohne Tabulator") is None


@pytest.mark.parametrize("text, erwartet", [
    ("Rehazentrum Am Kurpark\t\t946,21\t\t662,34", []),          # Hausnummer in anderer Spalte
    ("Rehazentrum Am Kurpark 946,21 EUR", []),                    # Betrag, keine Hausnummer
    ("Anschrift: Am Kurpark 9, 12345 Berlin", ["Am Kurpark 9"]),
    ("Hauptstraße 12a\t\tTelefon", ["Hauptstraße 12a"]),
])
def test_strasse_nicht_ueber_spaltenluecken_oder_betraege(text, erwartet):
    funde = analysiere_text(text, {"strasse"}, [], [])
    assert sorted(f["text"] for f in funde if f["kategorie"] == "strasse") == erwartet


def test_zellen_namen_abkuerzungen_verworfen(monkeypatch):
    monkeypatch.setattr(na, "lade_ner", lambda: None)
    monkeypatch.setattr(na, "finde_personen", _kurzzeilen_ki({"RLV Komfort 2024": ["RLV"], "HUONG": ["HUONG"]}))
    funde = analysiere_text("Tarif:\t\tRLV Komfort 2024\nName\t\tHUONG\n", {"namen"}, [], [])
    assert {f["text"] for f in funde} == {"HUONG"}


@braucht_modell
def test_zellen_namen_gegenprobe_der_ki():
    """Gegenprobe im neutralen Satz: Namen bleiben, Spaltenköpfe/Formular-Etiketten fallen heraus."""
    from anonymisierer.detektoren import klassisch
    namen_ = {"Santoro", "Petra", "Zeynep", "Tschirner", "Giovanni", "Liselotte", "Silke von Schönau"}
    woerter = {"Familientarif", "Schlüsselverlust", "Betrag", "Gesamtbetrag", "Physiotherapie", "Hundehalter"}
    ok = klassisch._zellen_namen_bestaetigen(namen_ | woerter)
    assert ok is not None
    assert namen_ <= ok, namen_ - ok
    assert not (woerter & ok), woerter & ok


def test_muster_ueberspannen_keine_spaltentrenner():
    """Entwicklungs-Benchmark 010_bestandsliste: "78050 Villingen-Schwenningen | Kfz | Spreewald" wurde ein
    PLZ/Ort-Fund und schwärzte Sparte und Versicherer (Über-Schwärzung 6 % -> 17 %)."""
    zeile = "1 Hahn, Annika\t\t14.03.1961\t\t78050 Villingen-Schwenningen\t\tKfz\t\tSpreewald\t\t2520868691"
    funde = analysiere_text(zeile, {"plzort"}, [], [])
    assert [f["text"] for f in funde] == ["78050 Villingen-Schwenningen"]
    tabelle = "PLZ\t\tOrt\n53285\t\tBonn"
    assert any(f["text"].split() == ["53285", "Bonn"] for f in analysiere_text(tabelle, {"plzort"}, [], []))


def test_etikett_und_wert_in_nachbarzellen():
    """Entwicklungs-Benchmark 015/029_zweispaltig: "Vertragsnummer | LV/86/0439377" in einer Zeile galt dem
    Muster als Spaltenkopf (Tabulator ohne Doppelpunkt) – die zeilenweise Lesart findet den Wert."""
    funde = analysiere_text("Vertragsnummer\t\tLV/86/0439377\nBeginn 01.01.2020", {"vertrag"}, [], [])
    assert "LV/86/0439377" in {f["text"] for f in funde}
    # Spaltenkopf bleibt Spaltenkopf: Wert aus der Folgezeile
    kopf = "Vertragsnummer\t\tBeginn\t\tAblauf\nLV-2018-933486\t\t01.10.2018\t\t01.10.2034"
    assert "LV-2018-933486" in {f["text"] for f in analysiere_text(kopf, {"vertrag"}, [], [])}


def test_tabellenzelle_nachname_komma_vorname(monkeypatch):
    """Bestandsliste: "Hahn, Annika" – die KI übersieht Nachnamen, die auch Wörter sind; ist der Vorname als
    Person bekannt, wird die ganze Zelle eine Person (sonst bliebe "Hahn" stehen)."""
    monkeypatch.setattr(na, "lade_ner", lambda: None)
    monkeypatch.setattr(na, "finde_personen", _kurzzeilen_ki({"Annika hat angerufen.": ["Annika"],
                                                               "Annika": ["Annika"]}))
    text = ("Annika hat angerufen.\n"
            "Nr. Kunde (Name, Vorname)\t\tgeb.\t\tOrt\n"
            "1 Hahn, Annika\t\t14.03.1961\t\tBerlin\n"
            "2 van den Berg, Annika\t\t07.03.1968\t\tLauf\n"
            "3 Berlin, Hamburg\t\t01.01.1970\t\tKöln\n")
    funde = {f["text"]: f for f in analysiere_text(text, {"namen"}, [], [])}
    assert "Hahn, Annika" in funde and "van den Berg, Annika" in funde
    assert not any("Hamburg" in t or "Berlin" in t for t in funde)
    stellen = {text[s["start"]:s["ende"]] for f in funde.values() for s in f["stellen"]}
    assert "Hahn, Annika" in stellen
