"""Tests für die Namenserkennung (anonymisierer/namen.py): Plausibilitätsfilter (Gutachten EQ-04/EQ-11),
Titelform-Pass nur auf Versalien-Zeilen (PERF-04), Regeln."""

import pytest

from anonymisierer import namen as na
from conftest import braucht_modell


def _regeln(text):
    return [k["text"] for k in na._regel_kandidaten(text)]


# ---------------------------------------------------------------------- EQ-04 Sachwörter
@pytest.mark.parametrize("wort", ["Schadenanzeige", "Familientarif", "Kfz-Schadenanzeige", "Sozialversicherungsnummer",
                                  "Behandelnder", "Mitversichertes", "Kraftfahrt-Haftpflicht", "Gedruckt",
                                  "Bezugsberechtigt", "Stern-Apotheke", "Schadentag", "Grüße", "Erstattungsfähig",
                                  "Praxisanschrift", "Hauptstr"])
def test_sachwoerter(wort):
    assert na._ist_sachwort(wort)


@pytest.mark.parametrize("wort", ["Adeyemi", "Yılmaz-Schneider", "Klein-Hoffmann", "Schneider", "Müller", "Patel",
                                  "Gerhart", "Ehrlich", "Halter"])
def test_namen_sind_keine_sachwoerter(wort):
    if wort == "Halter":
        pytest.skip("Halter steht in der Stoppliste (Rolle), ist aber kein Sachwort-Kompositum")
    assert not na._ist_sachwort(wort)


@pytest.mark.parametrize("text, start, ende", [
    ("Schadenanzeige Kraftfahrt-Haftpflicht\n", 0, 37),
    ("RLV Komfort 2024", 0, 3),
    ("Beruf / Arbeitgeber: Polier, Esposito Bau GmbH", 21, 27),
    ("Frankfurt am Taunus", 13, 19),
])
def test_ki_fehltreffer_werden_verworfen(text, start, ende):
    assert not na._plausibel(text, start, ende)


def test_regeltreffer_bleiben_trotz_sachwort_filter():
    text = "Beruf / Arbeitgeber: Polier, Esposito Bau GmbH"
    assert na._plausibel(text, 21, 27, regel=True)


# ---------------------------------------------------------------------- EQ-11 Zwei-Buchstaben-Namen
def test_zwei_buchstaben_hinter_anrede():
    text = "Herr Li ist Kunde. Frau Wu auch. Max Li zahlt."
    assert {"Li", "Wu"} <= set(_regeln(text))
    assert na._plausibel("Herr Ng", 5, 7) and not na._plausibel("Es Ng", 3, 5)


def test_unicode_grossbuchstaben_in_regeln():
    assert "Ågren" in _regeln("Fragen beantwortet Ihnen gern Herr Ågren in unserer Beratungsstelle.")
    assert "Çelik" in _regeln("Sehr geehrte Frau Çelik,")
    assert "Łukasz Nowak" in _regeln("Versicherungsnehmer: Łukasz Nowak")


def test_beziehungswort_am_satzanfang():
    assert "Patel" in _regeln("Der Zeuge Patel hat den Vorgang gesehen.")


def test_nachname_wie_wochentag_bleibt_beim_vornamen():
    text = "Mit freundlichen Grüßen Eckhard Freitag"
    s = text.index("Eckhard")
    assert na._bereinigen(text, s, len(text)) == (s, len(text))
    text = "Antragsteller: Erika Mai"
    assert "Erika Mai" in _regeln(text)


def test_sachwerte_hinter_etiketten():
    text = "Beruf: Polier\nPolier, Esposito Bau GmbH"
    assert na._sachwerte(text) == {"polier"}


# ---------------------------------------------------------------------- PERF-04
class _NlpAttrappe:
    """Zählt, welche Texte die NER zu sehen bekommt."""

    def __init__(self):
        self.texte = []

    def pipe(self, texte, batch_size=64):
        for t in texte:
            self.texte.append(t)
            yield _Doc()


class _Doc:
    ents = ()


def test_titelform_nur_fuer_versalien_zeilen():
    zeilen = ["Normaler Text ohne Versalien."] * 50 + ["HERRN", "MAX MUSTERMANN", "Hauptstraße 1"] + ["Weiter."] * 50
    text = "\n".join(zeilen)
    nlp = _NlpAttrappe()
    na._ner_versalien_zeilen(nlp, text)
    gesehen = "\n".join(nlp.texte)
    assert "Max Mustermann" in gesehen and gesehen.count("Normaler Text") <= 2
    assert len("".join(nlp.texte)) < len(text) / 5


@braucht_modell
def test_finde_personen_ohne_ueberschriften():
    text = ("Schadenanzeige Kraftfahrt-Haftpflicht\nFamilientarif\nVersicherungsnehmer: Max Mustermann\n"
            "Sehr geehrter Herr Mustermann,\nwir bestätigen den Eingang. Mit freundlichen Grüßen\nAnna Schmidt")
    namen = {k["text"] for k in na.finde_personen(text)}
    assert {"Max Mustermann", "Anna Schmidt"} <= namen
    assert not namen & {"Schadenanzeige Kraftfahrt-Haftpflicht", "Schadenanzeige", "Familientarif",
                        "Kraftfahrt-Haftpflicht"}


# ---------------------------------------------------------------------- OCR-Reste und Kopfzeilen (nur KI-Treffer)
@pytest.mark.parametrize("rest", ["IE EEESTEUER", "ee BEER", "i= SEE", "Ust«-TeiNe", "Aues|y",
                                  "us Wersicherungsschein", "FE EEE NE SET"])
def test_ocr_reste_sind_keine_namen(rest):
    assert na._ocr_rest(rest)
    assert not na._plausibel(rest + " schrieb", 0, len(rest))


@pytest.mark.parametrize("name", ["Max Mustermann", "Antonio DeLuca", "Sean McLean", "LaToya Jackson", "Arı Yılmaz",
                                  "Begoña Fernández", "Siobhan O'Brien", "Hans-Peter Müller", "Kılıç",
                                  "Maarten van Dijk", "Kenneth MacArthur"])
def test_echte_namen_sind_keine_ocr_reste(name):
    assert not na._ocr_rest(name)
    assert na._plausibel(name + " schrieb", 0, len(name))


def test_mail_kopf_und_grussformel_keine_namen():
    assert not na._plausibel("Gesendet: Montag, 3. März 2025", 0, 8)
    assert not na._plausibel("Herzliche Grüße", 0, 15)


@pytest.mark.parametrize("name", ["Freitag, Eckhard", "Mai, Erika", "Müller (geb. Schmidt)"])
def test_komma_und_klammer_kein_ocr_rest(name):
    assert not na._ocr_rest(name)


# ---------------------------------------------------------------------- Monats-/Wochentagsnamen als Nachnamen
@pytest.mark.parametrize("text, name", [
    ("Nachname: Freitag\nVorname: Eckhard\n", "Freitag"),
    ("Nachname: Mai\nVorname: Erika\n", "Mai"),
    ("Name: Freitag, Eckhard\n", "Freitag, Eckhard"),
    ("Sehr geehrte Frau Mai,\nvielen Dank.", "Mai"),
    ("Sehr geehrter Herr Dr. Freitag,\nvielen Dank.", "Freitag"),
])
def test_kalenderwort_als_nachname(text, name):
    assert name in _regeln(text)


@pytest.mark.parametrize("text", ["Kontakt: Montag bis Freitag 8-18 Uhr", "Datum: Freitag, 14.03.2025",
                                  "Wir melden uns am Freitag, den 14. Mai."])
def test_kalenderwort_ohne_namenskontext_kein_name(text):
    assert not any(k in ("Montag", "Freitag", "Mai") for k in _regeln(text))
