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


def test_nie_liste_namen(monkeypatch):
    kandidaten = [{"text": "Peter Schmidt", "start": 20, "ende": 33, "gruppe": None},
                  {"text": "Sabine Schmidt", "start": 50, "ende": 64, "gruppe": None},
                  {"text": "Karl Schmidtke", "start": 90, "ende": 104, "gruppe": None}]
    monkeypatch.setattr(analyse, "finde_personen", lambda text: kandidaten)
    text = "Sehr geehrter Herr Peter Schmidt, Ihre Beraterin Sabine Schmidt hat den Antrag von Karl Schmidtke erhalten."
    # Eintrag "Schmidt": nur der nackte Bestandteil wird freigegeben, Vollnamen bleiben
    f = paare(analysiere_text(text, {"namen"}, ["Schmidt"], []))
    assert ("namen", "Peter Schmidt") in f and ("namen", "Sabine Schmidt") in f and ("namen", "Karl Schmidtke") in f
    assert ("namen", "Schmidt") not in f and ("namen", "Schmidtke") in f
    # Eintrag "Sabine Schmidt": Vollname frei, Bestandteil "Schmidt" bleibt (von Peter Schmidt)
    funde, hinweise = analyse._analysiere(text, {"namen"}, ["Sabine Schmidt"], [])
    f = paare(funde)
    assert ("namen", "Sabine Schmidt") not in f and ("namen", "Peter Schmidt") in f and ("namen", "Schmidt") in f
    assert "Durch NIE-Liste freigegeben: Sabine Schmidt" in hinweise
    # Firmenname gibt keinen Bestandteil frei
    f = paare(analysiere_text(text, {"namen"}, ["Schmidt Versicherungsmakler GmbH"], []))
    assert ("namen", "Schmidt") in f


# ----------------------------------------------------------------------
# M-47: IMMER-Begriffe
# ----------------------------------------------------------------------
def test_immer_begriffe(monkeypatch):
    monkeypatch.setattr(analyse, "finde_personen",
                        lambda text: [{"text": "Max Mustermann", "start": text.find("Max"), "ende": 0, "gruppe": None}])
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
# ----------------------------------------------------------------------
def _mit_kandidaten(monkeypatch, text, *namen):
    kandidaten = []
    for n in namen:
        if isinstance(n, tuple):
            n, gruppe = n
        else:
            gruppe = None
        kandidaten.append({"text": n, "start": text.find(n), "ende": text.find(n) + len(n), "gruppe": gruppe})
    monkeypatch.setattr(analyse, "finde_personen", lambda t: sorted(kandidaten, key=lambda k: k["start"]))
    return {f["text"]: f["ersatz"] for f in analysiere_text(text, {"namen"}, [], [])}


def test_pseudonyme_reihenfolge_und_familie(monkeypatch):
    text = ("Sehr geehrter Herr Mustermann,\nIhre Ehefrau Anna Mustermann ist eingetragen. Ihr Sohn Ben Mustermann "
            "ist mitversichert. Ihr Vermittler Peter Schmidt hat uns die Unterlagen vorgelegt.\nFrau Mustermann erhält die Rente.")
    e = _mit_kandidaten(monkeypatch, text, "Mustermann", "Anna Mustermann", "Ben Mustermann", "Peter Schmidt")
    assert e["Anna Mustermann"] == "[PERSON A]" and e["Ben Mustermann"] == "[PERSON B]" and e["Peter Schmidt"] == "[PERSON C]"
    assert e["Mustermann"] == "[FAMILIE A]"                            # mehrere Träger -> Familie
    assert e["Anna"] == "[PERSON A]" and e["Ben"] == "[PERSON B]" and e["Schmidt"] == "[PERSON C]"


def test_pseudonyme_varianten_derselben_person(monkeypatch):
    text = ("Der Vertrag von Dr. Max Mustermann wurde geprüft. Mustermann, Max ist Versicherungsnehmer. "
            "Herr Mustermann erhält die Leistung. MAX MUSTERMANN unterschreibt.")
    e = _mit_kandidaten(monkeypatch, text, "Max Mustermann", "Mustermann, Max", "Mustermann", "MAX MUSTERMANN")
    assert set(e.values()) == {"[PERSON A]"}
    assert {"Max Mustermann", "Mustermann, Max", "Mustermann", "Max"} <= set(e)
    assert "MAX MUSTERMANN" not in e           # reine ASCII-Versalien deckt die Suche im PDF ohnehin mit ab
    text = "Versicherungsnehmer: MAX MÜLLER\nSehr geehrter Herr Müller, Max Müller ist versichert."
    e = _mit_kandidaten(monkeypatch, text, "MAX MÜLLER", "Müller", "Max Müller")
    assert set(e.values()) == {"[PERSON A]"}
    assert {"MAX MÜLLER", "Max Müller", "Müller"} <= set(e)   # Umlaut-Versalien bleiben eigener Fund
    assert ("Max" in e) != ("MAX" in e)                        # ASCII-Bestandteil nur einmal


def test_pseudonyme_verschiedene_personen(monkeypatch):
    text = "Sehr geehrte Frau Anna Berg, Ihr Nachbar Herr Bergmann hat den Schaden gemeldet. Frau Berg und Herr Bergmann."
    e = _mit_kandidaten(monkeypatch, text, "Anna Berg", "Bergmann", "Berg")
    assert e["Anna Berg"] == "[PERSON A]" and e["Berg"] == "[PERSON A]" and e["Bergmann"] == "[PERSON B]"
    text = "Versicherungsnehmer Max Mustermann, mitversichert sein Sohn Maximilian Mustermann. Max und Maximilian."
    e = _mit_kandidaten(monkeypatch, text, "Max Mustermann", "Maximilian Mustermann", "Max", "Maximilian")
    assert e["Max Mustermann"] == "[PERSON A]" and e["Maximilian Mustermann"] == "[PERSON B]"
    assert e["Max"] == "[PERSON A]" and e["Maximilian"] == "[PERSON B]" and e["Mustermann"] == "[FAMILIE A]"
    text = "Anna Weber ist die Ehefrau von Thomas Weber. Frau Weber erhält Leistungen, Herr Weber nicht."
    e = _mit_kandidaten(monkeypatch, text, "Anna Weber", "Thomas Weber", "Weber")
    assert e["Weber"] == "[FAMILIE A]" and e["Anna"] == "[PERSON A]" and e["Thomas"] == "[PERSON B]"
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
    text = "Versicherungsnehmer: Dr. med. Hans-Peter van der Berg und Frau Li Wu."
    e = _mit_kandidaten(monkeypatch, text, "Dr. med. Hans-Peter van der Berg", "Li Wu")
    assert "van" not in e and "der" not in e and "med." not in e and "Dr." not in e
    assert e["Hans-Peter"] == "[PERSON A]" and e["Berg"] == "[PERSON A]"
    assert "Li" not in e and "Wu" not in e and e["Li Wu"] == "[PERSON B]"   # < 3 Zeichen kein Bestandteil


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
    """Ist das erwartete Element vollständig von Funden (beliebiger Kategorie) überdeckt?"""
    s = item["text"]
    if "kontext" in item:
        ka = text.index(item["kontext"])
        a = ka + item["kontext"].index(s)
    else:
        a = _spannen(s, text)[0][0]
    b = a + len(s)
    gedeckt = [False] * (b - a)
    for f in funde:
        for fa, fb in _spannen(f["text"], text):
            for i in range(max(a, fa), min(b, fb)):
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
