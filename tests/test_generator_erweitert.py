"""Erweiterte Verteilung des Benchmark-Generators (Generator 1.2, werkzeuge/benchmark/dokumenttypen_erweitert.py).

Die Standardverteilung bleibt unverändert: Die Pläne für Seed 1, Seed 7 und den CI-Korpus (12 Dokumente) haben
denselben Fingerabdruck wie vor der Erweiterung (Commit e165afb); die neuen Typen ziehen aus eigenen
Zufallsströmen ("plan_erweitert/<seed>", "x<seed>/<nr>/<versuch>") und nur mit erweitert=True. Byte-Gleichheit aller
erzeugten Dateien (PDF + Wahrheit) für Seed 1, Seed 7 und den CI-Korpus wurde bei der Einführung durch Erzeugen mit
beiden Checkouts geprüft – hier stehen die schriftunabhängigen Teile (Plan, Wahrheitsformat).

Dazu: MRZ nach den ICAO-9303-Mustern (TD1, TD2, TD3), Steuernummern in den Länderformaten und als ELSTER-Nummer,
Abdeckung der neuen Typen im erweiterten Plan und gültige Wahrheiten der ersten zehn erweiterten Dokumente."""

import datetime
import hashlib
import json
import re
from collections import Counter

import pytest

from anonymisierer import muster
from werkzeuge.benchmark import bewertung, generator
from werkzeuge.benchmark import dokumenttypen_erweitert as neu
from werkzeuge.benchmark import kennungen as K


def _plan_digest(plaene) -> str:
    teile = [f"{p.nr}|{p.typ}|{p.scan}|{','.join(p.neben)}" for p in plaene]
    return hashlib.sha256("\n".join(teile).encode()).hexdigest()


# ----------------------------------------------------------------------
# Standardverteilung unverändert
# ----------------------------------------------------------------------
@pytest.mark.parametrize("anzahl, seed, erwartet", [
    (80, 1, "2970cecfab919498bf1f77a51e706e95bffc3ccac2b7cc1aa9379e66ee874632"),
    (80, 7, "c1f6a421ef907f3ea092310bec18a4a1502960aa012232b3d4b2429bba196da6"),
    (12, 1, "47e82556c7b99f0c4fc81d84e591bcb44d165848751daa66d7702bbeb965c764"),
])
def test_standardplan_wie_vor_der_erweiterung(anzahl, seed, erwartet):
    plaene = generator.plane_korpus(anzahl, seed)
    assert _plan_digest(plaene) == erwartet
    assert all(p.mischung == "standard" for p in plaene)
    assert not {p.typ for p in plaene} & set(neu.NEUE_TYPEN)


def test_erweiterter_plan_beruehrt_den_standardplan_nicht():
    vorher = _plan_digest(generator.plane_korpus(80, 1))
    generator.plane_korpus(80, 1, erweitert=True)
    assert _plan_digest(generator.plane_korpus(80, 1)) == vorher
    a = generator.plane_korpus(80, 3, erweitert=True)
    b = generator.plane_korpus(80, 3, erweitert=True)
    assert _plan_digest(a) == _plan_digest(b)                     # deterministisch
    assert all(p.mischung == "erweitert" for p in a)


@pytest.mark.parametrize("seed", [3, 9])
def test_erweiterter_plan_deckt_alle_neuen_typen_ab(seed):
    plaene = generator.plane_korpus(80, seed, erweitert=True)
    je_typ = Counter(p.typ for p in plaene)
    assert set(neu.NEUE_TYPEN_REIHENFOLGE) == set(neu.NEUE_TYPEN)
    for typ in neu.NEUE_TYPEN:
        assert je_typ[typ] >= 6, (typ, je_typ[typ])
    assert {p.typ for p in plaene[:10]} == set(neu.NEUE_TYPEN)    # die ersten zehn: jeder neue Typ einmal
    assert any(p.typ not in neu.NEUE_TYPEN for p in plaene)       # alte Typen bleiben gemischt dabei
    assert any(p.scan for p in plaene if p.typ in neu.NEUE_TYPEN)


def test_standardwahrheit_ohne_mischungsfeld(tmp_path):
    plan = generator.plane_korpus(1, 1)[0]
    w = generator.erzeuge_dokument(plan, 1, tmp_path)
    assert "mischung" not in w["erzeugung"]
    assert w["erzeugung"]["generator"] != generator.GENERATOR_VERSION_ERWEITERT


# ----------------------------------------------------------------------
# MRZ (ICAO 9303, Musterdokumente "Utopia")
# ----------------------------------------------------------------------
_GEBURT, _ABLAUF = datetime.date(1974, 8, 12), datetime.date(2012, 4, 15)


def test_mrz_td3_wie_icao_muster():
    assert K.mrz_td3("UTO", "L898902C3", _GEBURT, "F", _ABLAUF, "UTO", "Eriksson", "Anna Maria",
                     persoenlich="ZE184226B") == ["P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
                                                  "L898902C36UTO7408122F1204159ZE184226B<<<<<10"]


def test_mrz_td1_und_td2_wie_icao_muster():
    assert K.mrz_td1("UTO", "D23145890", _GEBURT, "F", _ABLAUF, "UTO", "Eriksson", "Anna Maria", art="I") == [
        "I<UTOD231458907<<<<<<<<<<<<<<<", "7408122F1204159UTO<<<<<<<<<<<6", "ERIKSSON<<ANNA<MARIA<<<<<<<<<<"]
    assert K.mrz_td2("UTO", "D23145890", _GEBURT, "F", _ABLAUF, "UTO", "Eriksson", "Anna Maria", art="I") == [
        "I<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<", "D231458907UTO7408122F1204159<<<<<<<6"]


def test_mrz_umschrift_und_namensfeld():
    assert K.mrz_umschrift("Müller-Lüdenscheidt") == "MUELLER<LUEDENSCHEIDT"
    assert K.mrz_umschrift("Ševčík") == "SEVCIK"
    assert K.mrz_umschrift("Weiß") == "WEISS"
    feld = K.mrz_namensfeld("Mustermann", "Erika Maria", 30)
    assert feld == "MUSTERMANN<<ERIKA<MARIA".ljust(30, "<") and len(feld) == 30
    assert len(K.mrz_namensfeld("Papadopoulou-Konstantinidou", "Alexandra Eleni Sofia", 30)) == 30
    assert K.mrz_pruefziffer("L898902C3") == "6" and K.mrz_pruefziffer("740812") == "2"


# ----------------------------------------------------------------------
# Steuernummern
# ----------------------------------------------------------------------
def _schema_re(schema: str) -> str:
    return "^" + "".join(r"\d" if c in "FBUP" else re.escape(c) for c in schema) + "$"


@pytest.mark.parametrize("land", sorted(K.STEUERNR_LAENDER))
def test_steuernummer_formate_der_laender(land):
    import random
    rng = random.Random(f"test/{land}")
    schema, praefix = K.STEUERNR_LAENDER[land]
    for _ in range(5):
        _, nr = K.steuernummer_land(rng, land)
        assert re.match(_schema_re(schema), nr), (land, nr)
        _, elster = K.steuernummer_land(rng, land, art="elster")
        assert re.fullmatch(r"\d{13}", elster) and elster.startswith(praefix) and elster[4] == "0", elster
        _, schraeg = K.steuernummer_land(rng, land, art="elster_schraeg")
        assert re.fullmatch(r"\d{4}/\d{3}/\d{5}", schraeg) and schraeg.startswith(praefix)
        # die Erkennung findet jede Form hinter dem Feldnamen
        for wert in (nr, elster, schraeg):
            assert wert in muster.finde_steuernummer(f"Steuernummer: {wert}"), (land, wert)


# ----------------------------------------------------------------------
# Erste zehn Dokumente der erweiterten Verteilung: Wahrheit stimmt mit dem Original überein
# ----------------------------------------------------------------------
def test_erweiterte_dokumente_haben_gueltige_wahrheit(tmp_path):
    plaene = generator.plane_korpus(10, 3, erweitert=True)
    typen = set()
    for plan in plaene:
        w = generator.erzeuge_dokument(plan, 3, tmp_path)
        typen.add(w["typ"])
        assert w["erzeugung"]["generator"] == generator.GENERATOR_VERSION_ERWEITERT
        assert w["erzeugung"]["mischung"] == "erweitert"
        assert w["dokument"].startswith(f"{plan.nr:03d}_{plan.typ}")
        kern = [e for e in w["eintraege"] if e["erwartung"] == "schwaerzen" and e["umfang"] == "kern"]
        assert kern, w["dokument"]
        assert bewertung.pruefe_wahrheit(tmp_path / w["dokument"], w) == [], w["dokument"]
        gespeichert = json.loads((tmp_path / (w["dokument"][:-4] + ".wahrheit.json")).read_text(encoding="utf-8"))
        assert gespeichert["eintraege"] == w["eintraege"]
    assert typen == set(neu.NEUE_TYPEN)
