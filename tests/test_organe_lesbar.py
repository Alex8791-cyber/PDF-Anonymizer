"""Entscheidung des Maklers vom 27.11., Nr. 6: Namen von Vorstand, Aufsichtsrat und Geschäftsführung in den
Pflichtangaben eines Unternehmens (Fuß- oder Kopfzeile eines Geschäftsbriefs) bleiben lesbar – als abgewählt
angebotene Funde (Hinweis „Organ eines Unternehmens …“), ohne Meldung und ohne Verdacht der Selbstkontrolle.

Grenzen der Regel (bleiben geschwärzt): dieselbe Person steht auch anderswo (Kunde, Ansprechpartner); das Etikett
steht ohne weitere Pflichtangabe (Formularfeld „Geschäftsführer:“ in einem Antrag); die Liste nennt Personenmerkmale
(geb., wohnhaft, Telefon); Inhaber, Prokura, Ansprechpartner und Datenschutzbeauftragte sind keine Organe.
"""
import fitz
import pytest

from anonymisierer import analyse, personenkontext
from anonymisierer import muster as mu
from anonymisierer.analyse import analysiere_pdf, analysiere_text
from conftest import braucht_modell

HOCH = set(mu.PROFILE["hoch"]["aktive"])
FUSS_AG = ("Alpenland Versicherung AG · Sitz München · Amtsgericht München HRB 12345 · USt-IdNr. DE123456789\n"
           "Vorstand: Dr. Bernd Wallner (Vorsitzender), Sabine Ortlieb, Jörg Ziegler\n"
           "Vorsitzender des Aufsichtsrats: Prof. Dr. Ulrich Haberl")
FUSS_GMBH = "Maklerbüro Alpenblick GmbH · Geschäftsführer: Tobias Sonnleitner · Registergericht Augsburg HRB 4711"


def _namen(funde):
    return {f["text"]: f for f in funde if f["kategorie"] == "namen"}


def _an(f) -> bool:
    return any(st["an"] for st in f["stellen"])


@braucht_modell
@pytest.mark.parametrize("fuss, organe", [
    (FUSS_AG, ["Bernd Wallner", "Sabine Ortlieb", "Jörg Ziegler", "Ulrich Haberl"]),
    (FUSS_GMBH, ["Tobias Sonnleitner"]),
])
def test_organe_in_pflichtangaben_bleiben_lesbar(fuss, organe):
    text = "Sehr geehrter Herr Sedlbauer,\nanbei Ihr Versicherungsschein KV-2024-88812.\n\n" + fuss
    namen = _namen(analysiere_text(text, HOCH, [], [], profil="hoch"))
    assert _an(namen["Sedlbauer"])                               # der Kunde bleibt geschwärzt
    for organ in organe:
        f = namen[organ]
        assert not _an(f), f
        assert analyse.HINWEIS_ORGAN in f["hinweis"] and analyse.QUELLE_ORGAN in f["quellen"]


@braucht_modell
def test_firma_mit_dem_familiennamen_des_organs_bleibt_geschwaerzt():
    """Trägt die Firma den Familiennamen des Geschäftsführers („Maklerbüro Sonnleitner GmbH“), schwärzt die Regel für
    Namen in Firmenbezeichnungen ihn dort – dann bleibt die Person überall geschwärzt (vorsichtig)."""
    text = "Sehr geehrte Frau Kranich,\nanbei das Angebot.\n\n" + FUSS_GMBH.replace("Alpenblick", "Sonnleitner")
    namen = _namen(analysiere_text(text, HOCH, [], [], profil="hoch"))
    assert _an(namen["Tobias Sonnleitner"]), namen


@braucht_modell
def test_organ_das_auch_kunde_ist_bleibt_ueberall_geschwaerzt():
    text = ("Sehr geehrter Herr Sonnleitner,\nwir bestätigen Ihre Betriebshaftpflicht.\n\n" + FUSS_GMBH)
    namen = _namen(analysiere_text(text, HOCH, [], [], profil="hoch"))
    assert all(_an(f) for t, f in namen.items() if "Sonnleitner" in t), namen


@braucht_modell
@pytest.mark.parametrize("text, name", [
    # Formularfeld ohne weitere Pflichtangabe
    ("Antrag Betriebshaftpflicht\nFirma: Huber Bau GmbH\nGeschäftsführer: Josef Huber\nBeginn: 01.01.2027", "Josef Huber"),
    # Personenmerkmal in der Liste
    ("Gesellschafterliste · Amtsgericht München HRB 9876\nGeschäftsführer: Josef Huber, geb. 12.03.1971, wohnhaft "
     "in Erding", "Josef Huber"),
    # kein Organ
    ("Alpenland Versicherung AG · Amtsgericht München HRB 12345\nAnsprechpartner: Petra Lindner", "Petra Lindner"),
    ("Alpenland Versicherung AG · Amtsgericht München HRB 12345\nDatenschutzbeauftragter: Klaus Brunnhuber",
     "Klaus Brunnhuber"),
])
def test_grenzen_der_organregel(text, name):
    namen = _namen(analysiere_text(text, HOCH, [], [], profil="hoch"))
    assert name in namen and _an(namen[name]), namen


def test_organ_spannen_enden_an_etikett_spalte_und_pflichtangabe():
    text = "Vorstand: A Bertram, C Dorn\t\tSitz der Gesellschaft: München\nAufsichtsrat: E Faber · HRB 1\nX: Y"
    spannen = personenkontext.organ_spannen(text)
    teile = [text[a:b] for a, b in spannen]
    assert teile[0].strip() == "A Bertram, C Dorn"
    assert teile[1].strip(" ·") == "E Faber"


@braucht_modell
def test_ansprechpartner_ist_kein_name_hinter_geschaeftsfuehrer():
    """Nebenbefund: die Liste hinter „Geschäftsführer:“ lief in die nächste Etikettzeile – „Ansprechpartner“ galt als
    Name."""
    funde = analysiere_text("Geschäftsführer: Tobias Sonnleitner\nAnsprechpartner: Frau Petra Lindner", HOCH, [], [],
                            profil="hoch")
    assert "Ansprechpartner" not in _namen(funde)


@braucht_modell
def test_pdf_fusszeile_lesbar_ohne_verdacht(tmp_path):
    from anonymisierer.schwaerzung import schwaerze_pdf
    pdf = tmp_path / "brief.pdf"
    doc = fitz.open()
    s = doc.new_page(width=595, height=842)
    y = 80
    for z in ["Alpenland Versicherung AG", "Prinzregentenplatz 21, 81675 München", "", "Herrn Quirin Sedlbauer",
              "Am Anger 3", "84028 Landshut", "", "Sehr geehrter Herr Sedlbauer,", "anbei Ihr Versicherungsschein.",
              "", "Mit freundlichen Grüßen", "Ihre Alpenland Versicherung"]:
        s.insert_text((60, y), z, fontsize=11)
        y += 16
    y = 780
    for z in FUSS_AG.split("\n"):
        s.insert_text((60, y), z, fontsize=7)
        y += 10
    doc.save(pdf)
    doc.close()
    e = analysiere_pdf(pdf, HOCH, [], [], profil="hoch")
    assert not [m for m in e["meldungen"] if m["art"] == "warnung"], e["meldungen"]
    funde = [f for f in e["funde"] if any(st["an"] for st in f["stellen"])]
    r = schwaerze_pdf(pdf, funde, ziel_ordner=tmp_path / "aus", profil="hoch", modell=e.get("modell"))
    assert not r.get("verdacht"), r.get("verdacht")
    with fitz.open(r["ausgabe"]) as d:
        text = d[0].get_text()
    assert "Bernd Wallner" in text and "Ulrich Haberl" in text and "Sedlbauer" not in text
