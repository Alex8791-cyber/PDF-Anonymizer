"""Gesundheitsdaten in der Schutzstufe „Hoch“ (Entscheidung des Maklers vom 27.11.): angehakt und geschwärzt.

Nur vermutete Fachbegriffe ohne Etikett in einem Dokument ohne jeden Personenbezug (Tarif- und Leistungsübersicht)
bleiben angeboten (⚕, nicht angehakt) – sonst würden Leistungsbeschreibungen geschwärzt (Präzision). In „Ausgewogen“
werden alle Gesundheitsdaten weiter nur angeboten (tests/test_analyse.py), die Konfession bleibt in „Hoch“ angeboten.
"""
import pytest

from anonymisierer import analyse
from anonymisierer import muster as mu
from anonymisierer.analyse import analysiere_text


def _gesundheit(funde):
    return [f for f in funde if f["kategorie"] in mu.GESUNDHEIT]


def test_profil_hoch_schwaerzt_gesundheitsdaten_und_bietet_konfession_an():
    hoch = set(mu.PROFILE["hoch"]["aktive"])
    assert mu.GESUNDHEIT <= hoch and "religion" not in hoch
    assert mu.hinweis_kategorien("hoch", hoch) == {"religion"}
    assert mu.GESUNDHEIT <= mu.hinweis_kategorien("ausgewogen", mu.PROFILE["ausgewogen"]["aktive"])
    assert "Gesundheitsdaten" in mu.PROFILE["hoch"]["beschreibung"]


@pytest.mark.parametrize("satz", [
    "Herr Meier leidet an Diabetes mellitus Typ 2.",
    "Diagnose: Lumboischialgie links (M54.4)\nPhysiotherapie 2x wöchentlich",
    "Medikation: Bisoprolol 2,5 mg 1-0-0",
    "Die Patientin ist seit 2019 in Psychotherapie.",
])
def test_gesundheitsdaten_mit_bezug_werden_in_hoch_geschwaerzt(satz):
    meldungen = []
    funde, _ = analyse._analysiere(satz, set(mu.PROFILE["hoch"]["aktive"]), [], [], profil="hoch",
                                   meldungen=meldungen)
    gesundheit = _gesundheit(funde)
    assert gesundheit, funde
    assert all(st["an"] for f in gesundheit for st in f["stellen"]), gesundheit
    assert not any(analyse.HINWEIS_GESUNDHEIT in str(f.get("hinweis") or "") for f in gesundheit)
    assert not any(m["code"] == "GESUNDHEITSDATEN" for m in meldungen), meldungen


@pytest.mark.parametrize("satz", [
    "Ihr Tarif: Krankenhaustagegeld 50 EUR, Zahnersatz 80 %, Brillen bis 300 EUR.",
    "Tarif A: Ambulant 100 %, Psychotherapie bis 30 Sitzungen je Jahr.",
])
def test_tarifbegriffe_ohne_person_bleiben_in_hoch_angeboten(satz):
    meldungen = []
    funde, _ = analyse._analysiere(satz, set(mu.PROFILE["hoch"]["aktive"]) - {"namen"}, [], [], profil="hoch",
                                   meldungen=meldungen)
    gesundheit = _gesundheit(funde)
    assert gesundheit and not any(st["an"] for f in gesundheit for st in f["stellen"]), gesundheit
    assert all(analyse.gesundheit_nur_vermutet(f) for f in gesundheit)
    text = next(m["text"] for m in meldungen if m["code"] == "GESUNDHEITSDATEN")
    assert text.startswith("Das Dokument enthält möglicherweise Gesundheitsdaten")


def test_leistungsbegriffe_mit_person_im_dokument_werden_in_hoch_geschwaerzt():
    funde, _ = analyse._analysiere("Versicherte Person: Herr Thomas Meier, geb. 12.03.1971\n"
                                   "Physiotherapie 6 Sitzungen, erstattet 180,00 EUR", set(mu.PROFILE["hoch"]["aktive"]),
                                   [], [], profil="hoch")
    gesundheit = _gesundheit(funde)
    assert gesundheit and all(st["an"] for f in gesundheit for st in f["stellen"]), gesundheit


def test_maximal_schwaerzt_auch_vermutete_fachbegriffe():
    funde, _ = analyse._analysiere("Tarif A: Ambulant 100 %, Psychotherapie bis 30 Sitzungen je Jahr.",
                                   set(mu.PROFILE["maximal"]["aktive"]) - {"namen"}, [], [], profil="maximal")
    gesundheit = _gesundheit(funde)
    assert gesundheit and all(st["an"] for f in gesundheit for st in f["stellen"]), gesundheit


def test_textschnittstelle_mit_standardkategorien_schwaerzt_diagnose():
    funde = analysiere_text("Diagnose: Asthma bronchiale (J45.9) bei Frau Müller",
                            set(mu.PROFILE["hoch"]["aktive"]), [], [], profil="hoch")
    assert any(f["kategorie"] == "diagnose" and all(st["an"] for st in f["stellen"]) for f in funde), funde
