"""Tests für die wissensbasierten Detektoren (detektoren/wissen_namen.py, wissen_kontext.py), die Muster-Detektoren
mit Stellen (muster_spans.py), die Schutzstufen und die Unicode-Robustheit (Vertrag 12.7) bis in die Ausgabe."""

from pathlib import Path

import pytest

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

from anonymisierer import detektoren, muster
from anonymisierer.analyse import _analysiere_dokument, analysiere_pdf, analysiere_text
from anonymisierer.detektoren import Kontext, alle_treffer
from anonymisierer.detektoren import wissen_kontext as wk
from anonymisierer.detektoren import wissen_namen as wn
from anonymisierer.seitenmodell import dokument_aus_text
from conftest import braucht_modell

STANDARD = {k for k, _, _, _, an in muster.KATEGORIEN if an}
LIBERATION = Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf")
DEJAVU = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def _namen(text):
    return [text[t.start:t.ende] for t in wn.namen_stellen(text)]


def _texte(funktion, text):
    return [text[s:e] for s, e in funktion(text)]


# ---------------------------------------------------------------------- Register
def test_register_ohne_ladefehler_und_mit_ersatz():
    assert detektoren.LADEFEHLER == []
    namen = {e.name: e for e in detektoren.REGISTER}
    for name in ("wissen.namen", "wissen.gesundheit", "wissen.beruf", "org.arbeitgeber", "ort", "international",
                 "wissen.geburt", "kundenliste", "unbekannte_eigennamen", "muster.iban", "muster.telefon"):
        assert name in namen, name
    assert namen["muster.iban"].funktion.__module__.endswith("muster_spans")
    for alt in ("muster.beruf", "muster.diagnose", "muster.ort", "muster.international"):
        assert alt not in namen                     # keine Doppel-Erkennung über die Text-Schnittstelle
    assert namen["unbekannte_eigennamen"].profile == frozenset({"maximal"})


def test_muster_detektor_liefert_stellen_mit_lesefehler_quelle():
    dok = dokument_aus_text("Konto DE89 3704 0044 0532 0130 01 und DE89 3704 0044 0532 0130 00")
    treffer = [t for t in alle_treffer(dok, Kontext({"iban"})) if t.kategorie == "iban"]
    quellen = sorted((dok.text[t.start:t.ende], t.quelle) for t in treffer)
    assert quellen == [("DE89 3704 0044 0532 0130 00", "muster.iban"),
                       ("DE89 3704 0044 0532 0130 01", "muster.iban.lesefehler")]


def test_muster_detektor_tabellenzellen_nicht_verbinden():
    dok = dokument_aus_text("90402\t\tNürnberg-Mitte\t\tTarif")
    treffer = alle_treffer(dok, Kontext({"telefon"}))
    assert treffer == []


# ---------------------------------------------------------------------- wissen.namen
@pytest.mark.parametrize("text, erwartet", [
    ("Kołodziej, Grzegorz", ["Kołodziej, Grzegorz"]),
    ("STOJANOVIĆ, MIRELA", ["STOJANOVIĆ, MIRELA"]),
    ("2 Aßmann, Torsten", ["Aßmann, Torsten"]),
    ("van Dijk, Maarten", ["van Dijk, Maarten"]),
    ("26 GRAF, LISELOTTE", ["GRAF, LISELOTTE"]),
    ("5 VON WOLZOGEN-BRANDT,\nDIETER-CHRISTIAN", ["VON WOLZOGEN-BRANDT,\nDIETER-CHRISTIAN"]),
    ("Heyde, Anna von der", ["Heyde, Anna von der"]),
])
def test_r1_nachname_komma_vorname(text, erwartet):
    assert _namen(text) == erwartet


def test_r1_kein_phantom_hinter_anrede_und_ort():
    assert "Krüger, Max" not in _namen("Sehr geehrte Frau Krüger, Max Mustermann ist versichert.")
    assert "Berlin, Anna" not in _namen("Viele Grüße aus Berlin, Anna wird sich melden.")
    assert _namen("Sitz München Biedermann, Liselotte") == ["Biedermann, Liselotte"]


@pytest.mark.parametrize("text, erwartet", [
    ("vertreten durch den Geschäftsführer Sana Siddiqui", ["Sana Siddiqui"]),
    ("Mit freundlichen Grüßen Eckhard Freitag", ["Eckhard Freitag"]),
    ("Unterschrift: Erika Mai", ["Erika Mai"]),
    ("Holger EHRLICH hat das Verschulden eingeräumt.", ["Holger EHRLICH"]),
    ("Liridona Shala, Kastanienweg 17", ["Liridona Shala"]),
    ("Conceição Ferreira\t\t25.10.2021", ["Conceição Ferreira"]),
    ("A. Schmid\nV. De Luca", ["A. Schmid", "V. De Luca"]),
])
def test_r2_vorname_nachname(text, erwartet):
    for name in erwartet:
        assert name in _namen(text), (name, _namen(text))


def test_r2_ueber_zeilenumbruch_je_zeile_eine_stelle():
    text = "Vorstand: Dirk Weber, Faisal\nPatel"
    treffer = [t for t in wn.namen_stellen(text) if "Faisal" in text[t.start:t.ende] or "Patel" in text[t.start:t.ende]]
    assert sorted(text[t.start:t.ende] for t in treffer) == ["Faisal", "Patel"]
    assert {t.gruppe for t in treffer} == {"Faisal Patel"}


@pytest.mark.parametrize("text", ["Mercedes Benz Kundenservice", "Hersteller/Typ: Seat Leon ST", "Rosa Beispielwort",
                                  "Klaus Bahnhofstraße 5", "Simon Straße", "Versicherungsmakler Siddiqui hilft"])
def test_r2_keine_fehltreffer(text):
    assert not any(" " in n and n.split()[0] in ("Mercedes", "Seat", "Rosa", "Klaus", "Simon", "Versicherungsmakler")
                   for n in _namen(text)), _namen(text)


@pytest.mark.parametrize("text, erwartet", [
    ("Fragen beantwortet Ihnen gern Herr Ågren.", "Ågren"),
    ("Fragen beantwortet Ihnen gern Frau de Vries.", "de Vries"),
    ("Sehr geehrte Frau Dr. rer. nat. von Stetten,", "von Stetten"),
    ("Sehr geehrter Herr Dr. med. dent. Di Stefano,", "Di Stefano"),
    ("Herr Li ist Kunde.", "Li"),
])
def test_r3_anrede(text, erwartet):
    assert erwartet in _namen(text)


def test_r3_keine_rollenwoerter():
    assert _namen("Herrn Kollegen\nSehr geehrte Frau Kollegin,") == []


def test_r4_namen_in_firmen():
    assert "Berger" in _namen("anbei die Rechnung der Werkstatt Berger und die Fotos")
    assert "Siddiqui" in _namen("Versicherungsmakler Siddiqui & Partner GmbH")
    assert "Becker" in _namen("Becker GmbH, Industriestraße 9")
    assert _namen("Allianz Versicherungs-AG") == []


def test_r5_personenlisten_in_fusszeilen():
    text = ("Vorstand: Dr. jur. Aminata Haile (Vorsitzende), Dr. med. dent.\nDennis Wagner, Elke Wendt\n"
            "Vorsitz Aufsichtsrat:\nDr. jur. Horst Martin\nUSt-IdNr. DE640052347")
    namen = _namen(text)
    for name in ("Aminata Haile", "Dennis Wagner", "Elke Wendt", "Horst Martin"):
        assert name in namen, (name, namen)
    assert not any("USt" in n or "DE64" in n for n in namen)


def test_r5_personenliste_nie_ueber_spaltentrenner_und_ohne_komma_geteilt():
    """Fußzeile im Scan: Spalten durch "\\t\\t" getrennt, die OCR hat ein Aufzählungskomma verschluckt."""
    text = ("Vorstand: Monika Voigt, Witali\t\tVorsitz Aufsichtsrat:\n"
            "Marktplatz 6\t\t95632 Wunsiedel\t\tRempel, Carmela Marino\t\tPetr Kfiz\n"
            "Vorstand: Dipl.-Ing. Jörg Ziegler Ursula Frank\nSitz: Freiburg")
    namen = _namen(text)
    assert not any("\t" in n for n in namen), namen
    for name in ("Carmela Marino", "Petr Kfiz", "Jörg Ziegler", "Ursula Frank"):
        assert name in namen, (name, namen)
    assert "Jörg Ziegler Ursula Frank" not in namen


def test_r6_rolle_und_r7_url():
    assert "Patel" in _namen("Der Zeuge Patel hat den Vorgang beobachtet.")
    assert "Thomas Weber" in _namen("Anna Weber ist die Ehefrau von Thomas Weber.")
    assert "yilmaz" in _namen("Mehr unter www.praxis-yilmaz.de")


def test_unbekannte_eigennamen_nur_maximal():
    text = "Zeuge: Herr Xyzzab Qwonk, wohnhaft in der Nähe\nDer Vertrag gilt weiter."
    assert [text[t.start:t.ende] for t in wn.unbekannte_eigennamen(text)] == ["Xyzzab", "Qwonk"]
    dok = dokument_aus_text(text)
    hoch = alle_treffer(dok, Kontext({"namen"}, "hoch"))
    maximal = alle_treffer(dok, Kontext({"namen"}, "maximal"))
    assert not any(t.quelle == "unbekannte_eigennamen" for t in hoch)
    assert any(t.quelle == "unbekannte_eigennamen" for t in maximal)


# ---------------------------------------------------------------------- Gesundheit
def test_gesundheit_diagnosen_medikamente_icd():
    text = ("Diagnosen:\n- Lumboischialgie links (M54.4)\n- Generalisierte Angststörung (F41.1)\n"
            "Familienanamnese: Die Mutter leidet an Koronare Herzkrankheit, Ein-Gefäß-Erkrankung (I25.11).\n"
            "Medikation:\n· Salbutamol-Spray bei Bedarf\n· Bisoprolol 2,5 mg 1-0-0\n"
            "Körpergröße / Gewicht:\t\t186 cm / 90 kg")
    diagnosen = _texte(wk.diagnosen_stellen, text)
    assert diagnosen == ["Lumboischialgie links (M54.4)", "Generalisierte Angststörung (F41.1)",
                         "Koronare Herzkrankheit, Ein-Gefäß-Erkrankung (I25.11)", "186 cm / 90 kg"]
    assert _texte(wk.medikamente_stellen, text) == ["Salbutamol-Spray bei Bedarf", "Bisoprolol 2,5 mg 1-0-0"]


@pytest.mark.parametrize("text", ["Es gelten die AHB 2016 und die Kur ist mitversichert.",
                                  "Die Reha-Leistungen sind im Tarif enthalten.",
                                  "Vitamin B12 ist im Angebot"])
def test_gesundheit_ohne_kontext_nichts(text):
    assert wk.diagnosen_stellen(text) == []


def test_gesundheit_nur_maximal_aktiv():
    dok = dokument_aus_text("Diagnose: Asthma bronchiale (J45.9)")
    assert not any(t.kategorie == "diagnose" for t in alle_treffer(dok, Kontext(muster.PROFILE["hoch"]["aktive"])))
    assert any(t.kategorie == "diagnose" for t in alle_treffer(dok, Kontext(muster.PROFILE["maximal"]["aktive"],
                                                                            "maximal")))


# ---------------------------------------------------------------------- Beruf, Arbeitgeber
def test_beruf_und_arbeitgeber():
    text = ("Ausgeübter Beruf:\t\tPharmareferentin\nArbeitgeber:\t\tBäckerei Hofmeister\n"
            "Beruf: Lehrerin (verbeamtet)\nDie Patientin arbeitet als Zahnärztin bei der Bäckerei Hofmeister.\n"
            "Beruf / Arbeitgeber: Polier, Esposito Bau GmbH\nEr ist von Beruf Schreiner.")
    assert _texte(wk.berufe_stellen, text) == ["Pharmareferentin", "Lehrerin (verbeamtet)", "Zahnärztin", "Polier",
                                              "Schreiner"]
    assert _texte(wk.arbeitgeber_stellen, text) == ["Bäckerei Hofmeister", "Bäckerei Hofmeister", "Esposito Bau GmbH"]


def test_arbeitgeber_nie_versicherer_und_kein_beruf_ohne_kontext():
    text = "Er ist seit Jahren beschäftigt bei der Allianz Versicherungs-AG. Ihr Vertrag bei der Muster AG."
    assert _texte(wk.arbeitgeber_stellen, text) == []
    assert _texte(wk.berufe_stellen, "Der Kunde ist Mitglied. Ein Arzt ist zuständig.") == []


# ---------------------------------------------------------------------- Orte
def test_orte():
    text = ("St. Ingbert, 11.08.2025\t\tHofheim am Taunus, 11.08.2025\nDuisburg, 19.05.2025 Hildesheim, 19.05.2025\n"
            "' Bremerhaven, 17.08.2025 = | ak\nOrt:\t\tFrankfurt am Main\nGeburtsort:\t\tDebrecen\n"
            "geboren in Görlitz\nMontag, 12.05.2025\nPLZ / Ort\t\tSparte\t\tVersicherer")
    assert _texte(wk.orte_stellen, text) == ["St. Ingbert", "Hofheim am Taunus", "Duisburg", "Hildesheim",
                                             "Bremerhaven", "Frankfurt am Main", "Debrecen", "Görlitz"]


def test_ort_des_versicherers_bleibt():
    text = ("Allianz Lebensversicherungs-AG\nReinsburgstraße 19, 70178 Stuttgart\n\nHerrn\nMax Mustermann\n"
            "Bergstraße 7\n69117 Heidelberg\n\nStuttgart, 14.03.2025\n\nHeidelberg, 15.03.2025")
    assert _texte(wk.orte_stellen, text) == ["Heidelberg"]


# ---------------------------------------------------------------------- Ausland
def test_ausland():
    text = ("Kennzeichen:\t\t67-BDK-1\nAnschrift:\t\tPrinsengracht 263, 1016 GV Amsterdam\nKennzeichen: LU 946067\n"
            "ul. Marszałkowska 10/12, 00-590 Warszawa\n12 rue de la Paix, 75002 Paris\nVia Roma 15\n"
            "Váci utca 21, 1052 Budapest\nKennzeichen: N-AB 1234\nDie Route führte über Weimar.")
    gefunden = _texte(wk.ausland_stellen, text)
    for erwartet in ("67-BDK-1", "Prinsengracht 263", "1016 GV Amsterdam", "LU 946067", "ul. Marszałkowska 10/12",
                     "00-590 Warszawa", "12 rue de la Paix", "Via Roma 15", "Váci utca 21", "1052 Budapest"):
        assert erwartet in gefunden, (erwartet, gefunden)
    assert "N-AB 1234" not in gefunden and not any("Route" in g for g in gefunden)


# ---------------------------------------------------------------------- Geburtsdatum ohne Stichwort (EQ-20)
def test_geburt_ohne_stichwort():
    text = ("Antragsteller: Max Mustermann, 02.09.61\nAnna Berg (54) ist mitversichert.\n"
            "Unterschrift: Max Mustermann, 01.02.2025")
    gefunden = [(text[s:e], si) for s, e, si in wk.geburt_ohne_stichwort(text)]
    assert ("02.09.61", 0.65) in gefunden and ("54", 0.55) in gefunden
    assert not any(t == "01.02.2025" for t, _ in gefunden)          # Unterschriftsdatum, keine Geburt
    text = "Vertrag vom 01.01.1990. Ereignis 12.03.1975."
    alle = [text[s:e] for s, e, _ in wk.geburt_ohne_stichwort(text, True)]
    assert alle == ["12.03.1975"]


# ---------------------------------------------------------------------- Vertrag 12.7 bis in die Ausgabe
WINDOWS_ZEILEN = ["Versicherungsnehmerin Noémie Bonnet",
                  "Kundennummer 51­633867, Telefon 0421 3498­936",
                  "E-Mail a.krause@schwarzwald­versicherung.de",
                  "IBAN DE89 3704 0044 0532 0130 00",
                  "Mobil 0171‑2345678"]
WINDOWS_WERTE = ["Noémie Bonnet", "51-633867", "0421 3498-936", "a.krause@schwarzwald-versicherung.de",
                 "DE89 3704 0044 0532 0130 00", "0171-2345678"]


def test_windows_sonderzeichen_im_reinen_text():
    funde = analysiere_text("\n".join(WINDOWS_ZEILEN), STANDARD, [], [])
    texte = {st["text"] for f in funde for st in f["stellen"]}
    for wert in WINDOWS_WERTE[1:]:
        assert any(wert == " ".join(t.split()) for t in texte), (wert, texte)


@pytest.mark.skipif(not DEJAVU.exists(), reason="DejaVuSans fehlt")
@braucht_modell
def test_windows_sonderzeichen_pdf_vollstaendig_geschwaerzt(tmp_path):
    from anonymisierer.schwaerzung import schwaerze_pdf
    pdf = tmp_path / "windows.pdf"
    doc = fitz.open()
    seite = doc.new_page()
    for i, zeile in enumerate(WINDOWS_ZEILEN):
        seite.insert_text((50, 80 + 18 * i), zeile, fontsize=11, fontname="F0", fontfile=str(DEJAVU))
    doc.save(pdf)
    doc.close()
    erg = analysiere_pdf(pdf, STANDARD, [], [])
    assert erg["fehler"] is None
    gefunden = {" ".join(st["text"].split()) for f in erg["funde"] for st in f["stellen"]}
    for wert in WINDOWS_WERTE:
        assert wert in gefunden or any(wert in g for g in gefunden), (wert, gefunden)
    aus = schwaerze_pdf(pdf, erg["funde"], ziel_ordner=tmp_path / "aus", modell=erg["modell"])
    with fitz.open(aus["ausgabe"]) as d:
        rest = "".join(s.get_text() for s in d).replace(" ", " ").replace("­", "-").replace("‑", "-")
    for wert in ("Bonnet", "633867", "3498", "krause", "0532", "2345678"):
        assert wert not in rest, (wert, rest)


def test_generator_merkmal_sonderzeichen_windows(tmp_path):
    from werkzeuge.benchmark import generator as gen
    from werkzeuge.benchmark.normalisierung import Gefaltet
    plaene = gen.plane_korpus(30, 1)
    gewaehlt = [p.nr for p in plaene if gen.sonderzeichen_gewaehlt(p, 1)]
    assert gewaehlt == [p.nr for p in plaene if gen.sonderzeichen_gewaehlt(p, 1)]      # deterministisch
    assert gewaehlt and all(not plaene[nr - 1].scan for nr in gewaehlt)
    plan = next(p for p in plaene if p.nr == 9)                                       # Textdokument, TTF-Schrift
    w = gen.erzeuge_dokument(plan, 1, tmp_path)
    assert "sonderzeichen_windows" in w["merkmale"]
    with fitz.open(tmp_path / w["dokument"]) as d:
        text = "".join(s.get_text() for s in d)
    assert {" "} <= set(text) and set(text) & {"­", "‐", "‑"}
    betroffen = [e for e in w["eintraege"] if "Sonderzeichen" in e.get("bemerkung", "")]
    assert betroffen and all(Gefaltet(e["text"]).kette for e in betroffen)


# ---------------------------------------------------------------------- Review „Integration Wissen“
@pytest.mark.parametrize("text, erwartet", [
    ("Diagnose: Diabetes mellitus Typ 2 bei Herrn Meier", ["Meier"]),
    ("Befund: Morbus Crohn bei Frau Schulz", ["Schulz"]),
    ("Patient: Hans Meier leidet an Morbus Bechterew Grad II", ["Hans", "Meier"]),
    ("Zeuge: Herr Xyzzab Qwonk, Medikation: Metformin 1000 mg", ["Xyzzab", "Qwonk"]),
    ("Frau Merve Koç, leidet an Obstruktives Schlafapnoe-Syndrom (G47.31).", ["Merve", "Koç"]),
    ("Merve Karaca, leidet an Koronare Herzkrankheit, Ein-Gefäß-Erkrankung (I25.11). Die Patientin/der Patient",
     ["Karaca"]),
    ("Patient: Diagnose Diabetes mellitus Typ 2 bei Xyzzab", ["Xyzzab"]),   # nach „bei“: Name
])
def test_unbekannte_eigennamen_nicht_in_diagnosen(text, erwartet):
    """„maximal“: Wörter einer Diagnose/eines Medikaments („Morbus Crohn“, „Diabetes mellitus Typ 2“, „Obstruktives
    Schlafapnoe-Syndrom“, „Ein-Gefäß-Erkrankung (I25.11)“) und Bezeichnungen mit Nummer („Grad II“) sind keine
    unbekannten Eigennamen – sonst stünde in einer abgewählten, also lesbaren Diagnose „Diabetes mellitus [PERSON B]
    2“. Nach „bei“ oder einer Anrede bleibt ein Wort darin ein Name."""
    assert [text[t.start:t.ende] for t in wn.unbekannte_eigennamen(text)] == erwartet


def test_gesundheit_vermutet_nur_bei_allgemeinen_fachbegriffen():
    """Erkennung unverändert, aber Treffer, die sich nur auf allgemeine Wörter stützen (Tarif-/Leistungsbegriffe:
    Therapie, ambulant, Krankenhaus, Reha …), tragen die Quelle „wissen.gesundheit.vermutet“ (Sicherheit 0.5);
    Etikett, ICD-Code, Dosierung, Körpermaß oder Bezug zu einer Person -> „wissen.gesundheit“ (0.7)."""
    def treffer(text):
        dok = dokument_aus_text(text)
        return {(dok.text[t.start:t.ende], t.quelle, t.sicherheit) for t in alle_treffer(
            dok, Kontext(muster.PROFILE["maximal"]["aktive"], "maximal")) if t.kategorie in muster.GESUNDHEIT}
    assert treffer("Tarif A: Ambulant 100 %, Psychotherapie bis 30 Sitzungen.") == {
        ("Psychotherapie", "wissen.gesundheit.vermutet", 0.5)}
    assert treffer("Leistung bei schweren Erkrankungen wie Krebs, Herzinfarkt und Schlaganfall.") == {
        ("Krebs", "wissen.gesundheit.vermutet", 0.5), ("Herzinfarkt", "wissen.gesundheit.vermutet", 0.5),
        ("Schlaganfall", "wissen.gesundheit.vermutet", 0.5)}
    assert treffer("Die Patientin ist seit 2019 in Psychotherapie.") == {("Psychotherapie", "wissen.gesundheit", 0.7)}
    assert treffer("Seit der Chemotherapie kann Herr Meier nicht arbeiten.") == {
        ("Chemotherapie", "wissen.gesundheit", 0.7)}
    assert treffer("Medikation:\n· Bisoprolol 2,5 mg 1-0-0\nDiagnose: Lumboischialgie links (M54.4)") == {
        ("Bisoprolol 2,5 mg 1-0-0", "wissen.gesundheit", 0.7),
        ("Lumboischialgie links (M54.4)", "wissen.gesundheit", 0.7)}
    assert treffer("Ibuprofen bei Rückenschmerzen nach Krankenhausaufenthalt") == {
        ("Ibuprofen", "wissen.gesundheit.vermutet", 0.5),
        ("Rückenschmerzen nach Krankenhausaufenthalt", "wissen.gesundheit.vermutet", 0.5)}
    # die Schranke bleibt: eine Anrede allein ist kein Gesundheitskontext (nur die Art eines Treffers hängt an ihr)
    assert treffer("Herr Meier hat Diabetes.") == set()
    # die Stellen selbst sind dieselben wie die der Text-Schnittstelle
    text = "Leistung bei schweren Erkrankungen wie Krebs, Herzinfarkt und Schlaganfall."
    assert _texte(wk.diagnosen_stellen, text) == ["Krebs", "Herzinfarkt", "Schlaganfall"]
