"""Tests der Ausweisregeln (anonymisierer/detektoren/ausweise.py): maschinenlesbare Zone nach ICAO 9303 (TD1, TD2,
TD3) mit Prüfziffern und OCR-Lesarten, Sichtzone mit den Angaben der MRZ, Führerscheinfelder ohne Feldnamen.

Gegenproben: Text mit "<<" ohne gültige Datenzeile, Ortsangaben in Versalien mit Datum, nummerierte Abschnitte einer
Schadenanzeige, die nach der Führerscheinnummer fragt."""

import pytest

from anonymisierer import detektoren, seitenmodell
from anonymisierer.detektoren import Kontext
from anonymisierer.detektoren import ausweise as aw
from anonymisierer.muster import KATEGORIEN

ALLE = {k[0] for k in KATEGORIEN if k[4]}


def _treffer(text, name):
    dok = seitenmodell.dokument_aus_text(text)
    funktion = next(e for e in detektoren.REGISTER if e.name == name).funktion
    return [(t.kategorie, dok.text[t.start:t.ende], t.quelle, t.gruppe) for t in funktion(dok, Kontext(ALLE, "hoch"))]


def _texte(text, name, kategorie=None):
    return {t for k, t, _, _ in _treffer(text, name) if kategorie is None or k == kategorie}


def test_ausweisdetektoren_registriert():
    namen = {e.name for e in detektoren.REGISTER}
    assert {"ausweis.mrz", "ausweis.fuehrerschein"} <= namen


def test_pruefziffer_icao():
    assert aw.pruefziffer("L898902C3") == 6
    assert aw.pruefziffer("740812") == 2
    assert aw.pruefziffer("120415") == 9
    assert aw.pruefziffer("D23145890") == 7


# ----------------------------------------------------------------------
# MRZ
# ----------------------------------------------------------------------
def test_td3_reisepass_deutsch():
    text = "REISEPASS\nP<D<<MUSTERMANN<<ERIKA<<<<<<<<<<<<<<<<<<<<<<\nC01X00T478D<<6408125F2702283<<<<<<<<<<<<<<<4"
    treffer = _treffer(text, "ausweis.mrz")
    namen = [(t, g) for k, t, q, g in treffer if k == "namen" and q == "ausweis.mrz"]
    assert namen == [("MUSTERMANN<<ERIKA", "Erika Mustermann")]            # ohne Kopf "P<D<<"
    assert ("ausweis", "C01X00T478D<<6408125F2702283<<<<<<<<<<<<<<<4") in {(k, t) for k, t, _, _ in treffer}
    assert "6408125F2702283" in _texte(text, "ausweis.mrz", "geburt")


def test_td3_icao_muster_mit_angeklebtem_staat():
    text = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<\nL898902C36UTO7408122F1204159ZE184226B<<<<<10"
    namen = _texte(text, "ausweis.mrz", "namen")
    assert "UTOERIKSSON<<ANNA<MARIA" in namen                              # Staat klebt am Nachnamen: ganzes Stück
    assert "L898902C36UTO7408122F1204159ZE184226B<<<<<10" in _texte(text, "ausweis.mrz", "ausweis")


def test_td1_personalausweis_mit_sichtzone():
    text = ("PERSONALAUSWEIS\nName MUSTERMANN\nVornamen ERIKA\nGeburtstag 12.08.1964\n"
            "IDD<<T22000129<<<<<<<<<<<<<<<\n6408125<2010315D<<<<<<<<<<<<<4\nMUSTERMANN<<ERIKA<<<<<<<<<<<<<")
    treffer = _treffer(text, "ausweis.mrz")
    paare = {(k, t) for k, t, _, _ in treffer}
    assert ("namen", "MUSTERMANN<<ERIKA") in paare
    assert ("ausweis", "T22000129") in paare                               # Nummer ohne Kopf "IDD<<"
    assert ("geburt", "6408125") in paare
    sicht = {(k, t) for k, t, q, _ in treffer if q == "ausweis.mrz.sichtzone"}
    assert ("namen", "MUSTERMANN") in sicht and ("namen", "ERIKA") in sicht
    assert ("geburt", "12.08.1964") in sicht


def test_td2_vorlaeufiger_ausweis():
    text = "I<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<\nD231458907UTO7408122F1204159<<<<<<<6"
    paare = {(k, t) for k, t, _, _ in _treffer(text, "ausweis.mrz")}
    assert ("namen", "UTOERIKSSON<<ANNA<MARIA") in paare                  # Staat klebt am Nachnamen
    assert any(k == "ausweis" and "D23145890" in t for k, t in paare)


def test_mrz_mit_ocr_lesarten():
    # Füllzeichen als «, K-Ketten, O statt 0 – die Prüfziffern stimmen nach der Ziffernlesart
    text = "IDD«T22000129«««««««««««««««\n64O8125<2O1O315D<<<<<<<<KKK<4\nMUSTERMANN<<ERIKAKKKKKKKKKKK"
    paare = {(k, t) for k, t, _, _ in _treffer(text, "ausweis.mrz")}
    assert ("namen", "MUSTERMANN<<ERIKA") in paare
    assert ("geburt", "64O8125") in paare
    assert any(k == "ausweis" and "T22000129" in t for k, t in paare)


@pytest.mark.parametrize("text", [
    "Bitte <<hier>> unterschreiben und zurücksenden.",
    "STADT WIESBADEN 23.07.2024\nLANDKREIS EBERSBERG 01.02.2020",
    "ABC<<DEF<<GHI 1234567890\nXYZ<<UVW",
    "Ihre Vertragsnummer lautet LV<<123456 – bitte stets angeben.",
])
def test_mrz_gegenproben(text):
    assert _treffer(text, "ausweis.mrz") == []


# ----------------------------------------------------------------------
# Führerschein
# ----------------------------------------------------------------------
_FUEHRERSCHEIN = ("FÜHRERSCHEIN\nBUNDESREPUBLIK DEUTSCHLAND\n1. MUSTERMANN\n2. ERIKA\n3. 12.08.1983 MÜNCHEN\n"
                  "4a. 15.03.2015\n4b. 14.03.2030\n4c. Landratsamt Ebersberg\n4d. 091745\n5. B072RRE2I55\n"
                  "8. HAUPTSTRASSE 5, 85560 EBERSBERG\n9. AM/B/L")


def test_fuehrerschein_felder():
    paare = {(k, t) for k, t, _, _ in _treffer(_FUEHRERSCHEIN, "ausweis.fuehrerschein")}
    assert {("namen", "MUSTERMANN"), ("namen", "ERIKA"), ("geburt", "12.08.1983"), ("ort", "MÜNCHEN"),
            ("ausweis", "B072RRE2I55"), ("ausweis", "091745"),
            ("strasse", "HAUPTSTRASSE 5, 85560 EBERSBERG")} <= paare
    texte = {t for _, t in paare}
    assert "15.03.2015" not in texte and "14.03.2030" not in texte and "AM/B/L" not in texte


def test_fuehrerschein_ohne_wortlaut_nur_mit_vollstaendiger_feldfolge():
    ohne_wort = _FUEHRERSCHEIN.replace("FÜHRERSCHEIN\n", "")
    assert _treffer(ohne_wort, "ausweis.fuehrerschein")                    # alle Felder mit passender Form
    teil = "1. MUSTERMANN\n2. ERIKA\n3. 12.08.1983 MÜNCHEN"
    assert _treffer(teil, "ausweis.fuehrerschein") == []


def test_schadenanzeige_mit_nummerierten_abschnitten_ist_kein_fuehrerschein():
    text = ("Kfz-Schadenanzeige\n1. Versicherungsnehmer\nName: Hans Müller\n2. Fahrer zum Unfallzeitpunkt\n"
            "Führerschein-Nr.: B072RRE2I55\n3. Ihr Fahrzeug\nAmtl. Kennzeichen: M-AB 123\n4. Schadenhergang\n"
            "5. Zeugen\nkeine")
    assert _treffer(text, "ausweis.fuehrerschein") == []
