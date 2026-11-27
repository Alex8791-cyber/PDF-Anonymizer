"""Nachbesserung 5 nach der dritten Abnahme von integration-r7 (Stand 818990e).

Je Befund der Abnahme (AB3-01 bis AB3-08) die Zeilen der Abnahme, eigene Abwandlungen und nicht geheime Gegenproben.
Grundsatz der Nachbesserung: Wo eine Regel eng gefasst ist, um nicht geheimen Text frei zu lassen, meldet die
Selbstkontrolle (restrisiko.py) jeden ausgenommenen Fall, der ein geheimer Wert sein kann, an seiner Stelle – auf der
Textebene und auf OCR-Seiten. Alle Personen, Nummern und Anschriften sind frei erfunden."""

import pymupdf as fitz
import pytest

from anonymisierer import muster
from anonymisierer.analyse import analysiere_pdf, analysiere_text
from anonymisierer.restrisiko import pruefe_text, restrisiko_pruefen
from conftest import braucht_modell

ALLE = {k for k, _, _, _, an in muster.KATEGORIEN if an}


# ----------------------------------------------------------------------
# Hilfsfunktionen (wie tests/test_abnahme2_r7.py)
# ----------------------------------------------------------------------
def _funde(text, profil="hoch"):
    return analysiere_text(text, ALLE, [], [], profil=profil)


def _stellen(funde, kategorie=None) -> set:
    return {st["text"] for f in funde if kategorie is None or f["kategorie"] == kategorie
            for st in f["stellen"] if st.get("an", True)}


def _geschwaerzt(text, wert, kategorie=None) -> bool:
    return any(wert in s for s in _stellen(_funde(text), kategorie))


def _beruehrt(text, wert) -> bool:
    return any(wert in s or (len(s) >= 2 and s in wert) for s in _stellen(_funde(text)))


def _verdacht(text, **kw) -> list:
    return [(v.text, v.grund) for v in pruefe_text(text, **kw)]


def _ausgabe(text) -> tuple:
    spannen = sorted((st["start"], st["ende"], f["kategorie"].upper()) for f in _funde(text)
                     for st in f["stellen"] if st.get("an", True) and "start" in st)
    aus, pos, ph = [], 0, set()
    for s, e, k in spannen:
        if s < pos:
            continue
        aus += [text[pos:s], f"[{k}]"]
        ph.add(f"[{k}]")
        pos = e
    aus.append(text[pos:])
    return "".join(aus), sorted(ph)


def _weg_oder_gemeldet(text, wert) -> bool:
    aus, ph = _ausgabe(text)
    if wert not in aus:
        return True
    return any(wert in t or (len(t) >= 3 and t in wert) for t, _ in _verdacht(aus, platzhalter=ph))


def _gemeldet_nicht_geschwaerzt(text, wert) -> bool:
    aus, ph = _ausgabe(text)
    return wert in aus and any(wert in t or (len(t) >= 3 and t in wert) for t, _ in _verdacht(aus, platzhalter=ph))


def _lesbar_ohne_meldung(text, wert) -> bool:
    """Weder geschwärzt noch in der Ausgabe gemeldet."""
    aus, ph = _ausgabe(text)
    return wert in aus and not any(wert in t or (len(t) >= 3 and t in wert)
                                   for t, _ in _verdacht(aus, platzhalter=ph))


def _scan_pdf(pfad, zeilen, dpi=200):
    vorlage = fitz.open()
    s = vorlage.new_page()
    for i, z in enumerate(zeilen):
        s.insert_text((60, 90 + 24 * i), z, fontsize=12, fontname="helv")
    pix = s.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    doc = fitz.open()
    p = doc.new_page(width=s.rect.width, height=s.rect.height)
    p.insert_image(p.rect, stream=pix.tobytes("png"))
    doc.save(pfad)
    doc.close()
    vorlage.close()
    return pfad


class OcrAttrappe:
    """OcrDienst-Ersatz: liefert die Wörter der gedruckten Zeilen als OCR-Wörter (wie tests/test_kennungen_makler.py)."""

    def __init__(self, woerter):
        self.woerter_je_seite = woerter

    def woerter(self, pdf_pfad, seite_nr0, dpi=300, clip=None, winkel=None, **_):
        return list(self.woerter_je_seite.get(seite_nr0, [])), None

    def schliessen(self):
        pass


def _scan_mit_ocr_woertern(pfad, zeilen):
    """Scan-Seite aus Textzeilen und die OCR-Wörter (5-Tupel) der gedruckten Zeilen."""
    vorlage = fitz.open()
    s = vorlage.new_page()
    for i, z in enumerate(zeilen):
        s.insert_text((60, 100 + 24 * i), z, fontsize=12, fontname="helv")
    woerter = [tuple(w[:5]) for w in s.get_text("words")]
    pix = s.get_pixmap(dpi=200, colorspace=fitz.csGRAY)
    doc = fitz.open()
    p = doc.new_page(width=s.rect.width, height=s.rect.height)
    p.insert_image(p.rect, stream=pix.tobytes("png"))
    doc.save(pfad)
    doc.close()
    vorlage.close()
    return pfad, woerter


# ----------------------------------------------------------------------
# AB3-01: Zugangscode hinter Gebäuden und Behältern mit Schloss (…haus, …hütte, …schuppen, Scheune, Stall, Carport,
# …box, Spind, …schrank, …keller) – Regression aus A2-01 (engere Schlosswörter)
# ----------------------------------------------------------------------
AB3_01_FORMEN = [
    ("Gartenhaus: Code 9090", "9090"),
    ("Ferienhaus: Code 3141", "3141"),
    ("Gästehaus – Code 2718", "2718"),
    ("Hinterhaus Code 1618", "1618"),
    ("Bootshaus: Code 4242", "4242"),
    ("Gerätehaus: Code 2828", "2828"),
    ("Wochenendhaus: Code 5814", "5814"),
    ("Gartenhaus – Code 9090", "9090"),
    ("„Gartenhaus“ Code 9038", "9038"),
    ("(Gartenhaus) Code 9038", "9038"),
    ("Code für das Gartenhaus: 1127", "1127"),
    ("Hinweis für den Handwerker: Gartenhaus Code 7457", "7457"),
    ("Das Ferienhaus hat den Code 6137.", "6137"),
    ("Für das Ferienhaus gilt der Code 6148.", "6148"),
    ("Code 4466 für das Gartenhaus", "4466"),
    ("Gartenhütte: Code 1919", "1919"),
    ("Schuppen: Code 1717", "1717"),
    ("Geräteschuppen – Code 3016", "3016"),
    ("Scheune: Code 3131", "3131"),
    ("Heustadel: Code 3381", "3381"),
    ("Stall: Code 2121", "2121"),
    ("Pferdestall: Code 5703", "5703"),
    ("Carport: Code 4141", "4141"),
    ("Wallbox: Code 8099", "8099"),
    ("Fahrradbox: Code 9109", "9109"),
    ("Paketbox: Code 4149", "4149"),
    ("Spind: Code 1119", "1119"),
    ("Waffenschrank: Code 7731", "7731"),
    ("Fahrradkeller: Code 8181", "8181"),
    ("Die Scheune öffnet man mit 2604.", "2604"),
    ("Der Schuppen lässt sich mit 2633 öffnen.", "2633"),
]


@pytest.mark.parametrize("text, wert", AB3_01_FORMEN)
def test_ab3_01_zugangscode_hinter_gebaeude_und_behaelter(text, wert):
    assert _geschwaerzt(text, wert, "zugangsdaten"), _stellen(_funde(text))
    assert any(wert in t for t, _ in _verdacht(text)), _verdacht(text)       # Selbstkontrolle: dieselbe Regel


@pytest.mark.parametrize("text, wert", [
    ("Waschküche: Code 6161", "6161"),
    ("Dachboden: Code 5151", "5151"),
    ("Serverraum: Code 6169", "6169"),
    ("Heizraum: Code 6518", "6518"),
    ("Werkstatt: Code 3737", "3737"),
    ("Torantrieb: Code 9199", "9199"),
    ("Schranke – Code 1209", "1209"),
    ("Das Haus hat den Code 5353.", "5353"),
])
def test_ab3_01_code_hinter_feldname_ohne_sicheres_schloss_gemeldet(text, wert):
    """Ein Raum, Gerät oder Feldname direkt vor "Code" mit Ziffern: ohne sicheres Schloss nicht geschwärzt, aber
    gemeldet (Grundsatz P1)."""
    assert _weg_oder_gemeldet(text, wert), (_stellen(_funde(text)), _verdacht(text))


@pytest.mark.parametrize("text, wert", [
    ("Hausratversicherung: Code 4711", "4711"),
    ("Haushalt: Code HH-12", "HH-12"),
    ("Tarif Gartenhaus: Code GH-PLUS", "GH-PLUS"),
    ("Das Gartenhaus zeigt den Code E-21.", "E-21"),
    ("Die Wallbox meldet Code F-04.", "F-04"),
    ("Die Wallbox zeigt den Code 3017 an.", "3017"),
    ("Schaden am Gartenhaus, Code 4711 laut Schadenkatalog.", "4711"),
    ("Gartenhaus: 12 m² Grundfläche", "12"),
    ("Gartenhaus: Baujahr 1998", "1998"),
    ("Das Gartenhaus wurde mit 2500 Euro bewertet.", "2500"),
    ("Der Schuppen ist mit 1500 Litern Wasser vollgelaufen.", "1500"),
    ("Der Schuppen brannte am 12.03. ab.", "12.03."),
    ("Code 4711 im Sektor B der Lagerhalle.", "4711"),
    ("Der Code 128 steht auf dem Etikett.", "128"),
    ("Inspektor (Code 2207) hat aufgenommen.", "2207"),
])
def test_ab3_01_gegenproben(text, wert):
    assert _lesbar_ohne_meldung(text, wert), (_stellen(_funde(text)), _verdacht(text))


# Probe gen3 der Abnahme: ein Raum oder Gegenstand ohne sicheres Schloss in weiteren Formen um "Code" (in Klammern
# oder Anführung davor, "Code für den …:", "Code … für den …", als Satzgegenstand, allein in der Zeile davor – auch
# schon geschwärzt) blieb ohne Meldung
@pytest.mark.parametrize("text, wert", [
    ("(Fahrradraum) Code 3603", "3603"),
    ("„Heizungsraum“ Code 5590", "5590"),
    ("Code für die Werkstatt: 5029", "5029"),
    ("Code zum Lagerraum: 9054", "9054"),
    ("Code 6573 für das Lager", "6573"),
    ("Der Technikraum hat den Code 3389.", "3389"),
    ("Die Werkstatt hat einen neuen Code 7741.", "7741"),
    ("Werkstatt\nCode 9079", "9079"),
    ("Müllraum\nCode 2648", "2648"),
])
def test_ab3_01_code_mit_raum_in_weiteren_formen_gemeldet(text, wert):
    assert _weg_oder_gemeldet(text, wert), (_stellen(_funde(text)), _verdacht(text))


@pytest.mark.parametrize("text, wert", [
    ("Code 4711 für die Bestellung", "4711"),
    ("(Tarif) Code 2207", "2207"),
    ("Der Artikel hat den Code 4711.", "4711"),
    ("Fehlerspeicher:\nCode 1234", "1234"),
    ("Störung\nCode 1234", "1234"),
    ("Code 3017 für die Störung", "3017"),
    ("Fahrzeug (Typ) Code 7272", "7272"),
])
def test_ab3_01_code_mit_raum_gegenproben(text, wert):
    assert _lesbar_ohne_meldung(text, wert), (_stellen(_funde(text)), _verdacht(text))


def test_ab3_01_scan(tmp_path):
    pdf = _scan_pdf(tmp_path / "ab3_01.pdf", ["Hinweise für den Handwerker", "Gartenhaus: Code 9184",
                                              "Geräteschuppen – Code 3016", "Carport: Code 4185"])
    erg = analysiere_pdf(pdf, ALLE, [], [], profil="hoch")
    assert not erg.get("fehler"), erg.get("fehler")
    stellen = {st["text"] for f in erg["funde"] if f["kategorie"] == "zugangsdaten" for st in f["stellen"]
               if st.get("an", True)}
    for wert in ("9184", "3016", "4185"):
        assert any(wert in s for s in stellen), (wert, stellen)


# ----------------------------------------------------------------------
# AB3-07 (V1): Code hinter einem Satz mit Schloss in der Zeile davor (auch mit Satzzeichen), "Code ist/lautet",
# Bedienung mit trennbarem Verb
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert", [
    ("Bitte im Keller nachsehen.\nCode 9595", "9595"),
    ("Bitte an der Kellertür klingeln.\nCode 9538", "9538"),
    ("Schlüssel liegt im Schuppen.\nCode 9549", "9549"),
    ("Der Schlüssel hängt im Gartenhaus.\nCode: 9562", "9562"),
    ("Code lautet 5656.", "5656"),
    ("Der Code lautet 5629, bitte nicht weitergeben.", "5629"),
    ("Der Code ist 7878.", "7878"),
    ("Haustür, Code lautet 5631.", "5631"),
])
def test_ab3_07_code_weitere_formen_gemeldet(text, wert):
    assert _weg_oder_gemeldet(text, wert), (_stellen(_funde(text)), _verdacht(text))
    assert any(wert in t for t, _ in _verdacht(text)), _verdacht(text)


@pytest.mark.parametrize("text, wert", [
    ("Das Hoftor geht mit 2601 auf.", "2601"),
    ("Das Gartentor geht mit 2622 auf.", "2622"),
    ("Die Garage macht man mit 4433 auf.", "4433"),
])
def test_ab3_07_bedienung_mit_trennbarem_verb(text, wert):
    assert _geschwaerzt(text, wert, "zugangsdaten"), _stellen(_funde(text))


@pytest.mark.parametrize("text, wert", [
    ("Der Code ist 14 Tage gültig.", "14"),
    ("Das Garagentor zeigt einen Fehler.\nCode 3017", "3017"),
    ("Schaden an der Haustür.\nCode 4711 laut Schadenkatalog.", "4711"),
    ("Der Keller geht mit 1500 Litern Wasser voll.", "1500"),
    ("Die Tiefgarage mit 120 Stellplätzen ist voll.", "120"),
])
def test_ab3_07_gegenproben(text, wert):
    assert _lesbar_ohne_meldung(text, wert), (_stellen(_funde(text)), _verdacht(text))


# ----------------------------------------------------------------------
# AB3-02, AB3-03 (A2-04): Name hinter einem Personenwort – am Satzanfang mit einem Verb einer Person der Name (auch
# eine Marke, auch ohne Namensbeleg), ohne solches Verb gemeldet; Selbstkontrolle auf OCR-Seiten wie auf der Textebene
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, name", [
    ("Monteur Grohe kam am 03.03. um 9 Uhr.", "Grohe"),
    ("Monteur Hansgrohe kam am Montag.", "Hansgrohe"),
    ("Monteur Rowenta kam am Montag.", "Rowenta"),
    ("Monteur Buderus kam am 03.03. um 9 Uhr.", "Buderus"),
    ("Monteur Grohe hat die Leitung repariert.", "Grohe"),
    ("Mieter Liebherr hat gekündigt.", "Liebherr"),
    ("Nachbar Zettl hat den Brand gemeldet.", "Zettl"),
    ("Nachbar Wudy hat den Brand gemeldet.", "Wudy"),
    ("Nachbar Hoiß hat den Brand gemeldet.", "Hoiß"),
    ("Zeuge Pfaffl hat den Unfall gesehen.", "Pfaffl"),
    ("Notiz: Kollegin Pointl ruft zurück.", "Pointl"),
    ("Brandschaden – Telefonnotiz\nNachbar Kinz hat den Brand gemeldet.\nRückruf am Montag.", "Kinz"),
    ("Gestern kam Monteur Grohe vorbei.", "Grohe"),
    ("Heute rief Nachbar Moik an.", "Moik"),
    ("Monteur Grohe, Tel. 0171 2345678", "Grohe"),
    ("Der Nachbar Rauch hat angerufen.", "Rauch"),
    ("Der Mieter Sturm hat den Schaden gemeldet.", "Sturm"),
])
def test_ab3_02_name_hinter_personenwort_mit_verb_oder_kontakt(text, name):
    assert _geschwaerzt(text, name, "namen"), _stellen(_funde(text))


@pytest.mark.parametrize("text, name", [
    ("Monteur Grohe war am Freitag vor Ort.", "Grohe"),
    ("Laut Monteur Buderus wurde der Brenner falsch eingestellt.", "Buderus"),
])
def test_ab3_02_ohne_sicheren_beleg_gemeldet(text, name):
    assert _weg_oder_gemeldet(text, name), (_stellen(_funde(text)), _verdacht(text))


@pytest.mark.parametrize("text, wort", [
    ("Chef Sekretariat ist ab 9 Uhr besetzt, bitte Termine dort abstimmen.", "Sekretariat"),
    ("Kunden Service-Center ist am Brückentag geschlossen.", "Service-Center"),
    ("Nachbarin Frühstückspension Seeblick hat den Brand gemeldet.", "Frühstückspension"),
    ("Zeuge Unbekannt hat den Rauch im Keller zuerst bemerkt.", "Unbekannt"),
    ("Patient Visite um 10 Uhr: Wundheilung ohne Befund.", "Visite"),
    ("Ehefrau Mitversichert: ja, Tarif Komfort", "Mitversichert"),
    ("Nachbar Landgasthof Post hat Löschwasser bereitgestellt.", "Landgasthof"),
    ("Kunden Magazin Herbst 2025 liegt bei.", "Magazin"),
])
def test_ab3_02_gegenproben_bleiben_ungeschwaerzt(text, wort):
    """Die Gegenproben der Abnahme 2 (A2-04): nicht geschwärzt – gemeldet werden dürfen sie (kein sicherer Gegenbeleg
    für ein unbekanntes Wort hinter einem Personenwort)."""
    assert not _beruehrt(text, wort), _stellen(_funde(text))


@pytest.mark.parametrize("text, name", [
    ("Elektriker Miele kam am Montag.", "Miele"),
    ("Installateur Vaillant hat die Therme getauscht.", "Vaillant"),
    ("Techniker Neff, Tel. 0171 2345678", "Neff"),
    ("Mechaniker Viessmann rief zurück.", "Viessmann"),
    ("Der Elektriker Miele kam am Montag.", "Miele"),
    ("Termin: Elektriker Liebherr kam um 9 Uhr.", "Liebherr"),
])
def test_ab3_02_name_hinter_berufswort_mit_verb_geschwaerzt(text, name):
    """AB3-02 "hinter jedem Personenwort, auch hinter Berufen": am Satzanfang mit einem Verb einer Person oder einer
    Kontaktangabe dahinter ist das Wort hinter einem Berufswort der Name, wenn es selbst für einen Namen spricht (bekannte
    Marke, Vor- oder Familienname) – auf fbd755b und 818990e still."""
    assert _geschwaerzt(text, name, "namen"), _stellen(_funde(text))


@pytest.mark.parametrize("text, name", [
    ("Handwerker Grohe kam am Montag.", "Grohe"),
    ("Techniker Rowenta kam am Montag.", "Rowenta"),
])
def test_ab3_02_unbekanntes_wort_hinter_berufswort_mit_verb_gemeldet(text, name):
    assert _weg_oder_gemeldet(text, name), (_stellen(_funde(text)), _verdacht(_ausgabe(text)[0]))


@pytest.mark.parametrize("text, wort", [
    ("Elektriker Arbeiten wurden am Montag erledigt.", "Arbeiten"),
    ("Mechaniker Ausbildung hat drei Jahre gedauert.", "Ausbildung"),
    ("Handwerker Rechnung kam per Post.", "Rechnung"),
    ("Schreiner Holz kam per Lkw.", "Holz"),
    ("Gärtner Pflege kam teurer als gedacht.", "Pflege"),
    ("Laut Monteur Buderus wurde der Brenner falsch eingestellt.", "Buderus"),
])
def test_ab3_02_sachwort_hinter_berufswort_bleibt_ungeschwaerzt(text, wort):
    assert not _beruehrt(text, wort), _stellen(_funde(text))


@pytest.mark.parametrize("zeilen, name", [
    (["Brandschaden – Telefonnotiz", "Nachbar Wudy war gestern Abend da.", "Rückruf am Montag."], "Wudy"),
    (["Unfallhergang", "Zeuge Kinz war Beifahrer."], "Kinz"),
    (["Notiz", "Monteur Grohe war am Freitag vor Ort."], "Grohe"),
    (["Gutachten Leitungswasser", "Der Gutachter hat beim Mieter Schimmel festgestellt."], "Schimmel"),
])
def test_ab3_03_selbstkontrolle_auf_ocr_seiten_wie_textebene(tmp_path, zeilen, name):
    """Auf einer Scan-Seite meldet die Selbstkontrolle den Namen hinter dem Personenwort wie auf der Textebene – auch mit
    vier Buchstaben (vorher auf OCR-Seiten nur 5 bis 14 Zeichen und ohne Rollen-Kontext; Abnahme 3 AB3-03)."""
    text = "\n".join(zeilen)
    assert any(name in t for t, _ in _verdacht(text)), _verdacht(text)
    pdf, woerter = _scan_mit_ocr_woertern(tmp_path / "ocr.pdf", zeilen)
    verdacht = restrisiko_pruefen(pdf, ocr=OcrAttrappe({0: woerter}), ocr_modus={0: "seite"})
    assert any(name in v.text for v in verdacht), verdacht


@pytest.mark.parametrize("text, wort", [
    ("Familienanamnese: Mutter Morbus Parkinson; Vater Alzheimer-Demenz", "Alzheimer-Demenz"),
    ("Vorerkrankungen: Vater Lumboischialgie, Mutter Gastritis", "Lumboischialgie"),
    ("Vorerkrankungen: Vater Lumboischialgie, Mutter Gastritis", "Gastritis"),
    ("Befund: Patient Baker-Zyste links, Kontrolle in 6 Wochen", "Baker-Zyste"),
])
def test_ab3_03_fachwort_der_medizin_hinter_personenwort_kein_namensverdacht(text, wort):
    """Ein Fachwort der Medizin hinter einem Personenwort ("Vater Alzheimer-Demenz") ist eine Diagnose (eigene Kategorie)
    und kein möglicher Name – Gegenprobe der Domänen-Probe (person_gegen/gegen3)."""
    assert not any(wort in t and "Personenwort" in g for t, g in _verdacht(text)), _verdacht(text)


@pytest.mark.parametrize("text, name", [
    ("Familienanamnese: Vater Zirngibl, Mutter Morbus Parkinson", "Zirngibl"),
    ("Patient Kranawetter, Befund: Baker-Zyste links", "Kranawetter"),
])
def test_ab3_03_name_neben_fachwort_der_medizin_gemeldet(text, name):
    assert any(name in t for t, _ in _verdacht(text)), _verdacht(text)


@pytest.mark.parametrize("text, name", [
    ("Wir waren beim Nachbarn Koch zu Besuch.", "Koch"),
    ("Wir waren beim Nachbarn Schreiner zu Besuch.", "Schreiner"),
    ("Wir waren beim Nachbarn Gärtner zu Besuch.", "Gärtner"),
    ("Wir waren beim Nachbarn Richter zu Besuch.", "Richter"),
    ("Die Schlüssel liegen beim Kollegen Maurer.", "Maurer"),
])
def test_ab3_03_berufswort_als_familienname_hinter_personenwort_gemeldet(text, name):
    """Ein Berufswort, das zugleich ein Familienname ist, hinter einem Personenwort: die Erkennung nimmt es als Beruf
    aus, die Selbstkontrolle meldet es (vorher auf fbd755b und 818990e still)."""
    assert _weg_oder_gemeldet(text, name), (_stellen(_funde(text)), _verdacht(_ausgabe(text)[0]))


@pytest.mark.parametrize("text, wort", [
    ("Sohn Auszubildender, Tochter Studentin", "Auszubildender"),
    ("Sohn Auszubildender, Tochter Studentin", "Studentin"),
    ("Kinder Mitversichert bis zum 25. Lebensjahr", "Mitversichert"),
])
def test_ab3_03_berufswort_ohne_familiennamen_kein_namensverdacht(text, wort):
    assert not any(wort in t and "Personenwort" in g for t, g in _verdacht(text)), _verdacht(text)


# ----------------------------------------------------------------------
# Offener Punkt der vierten Nachbesserung (A2-04, Probe p07): eine bekannte Marke hinter "laut"/"gemäß" und dem
# Personenwort einer Firma wird gemeldet, auch wenn die KI sie als Person liest (auch mit dem Personenwort in ihrer
# Spanne); mit einem Verb einer Person, einer Kontaktangabe, hinter "mit" und hinter Personenwörtern des privaten
# Umfelds bleibt sie der Name
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, marke", [
    ("Laut Monteur Viessmann ist der Kessel defekt.", "Viessmann"),
    ("Laut Sachbearbeiterin Dyson ist das Gerät defekt.", "Dyson"),
    ("Gemäß Mitarbeiter Gardena ist der Schlauch undicht.", "Gardena"),
    ("Laut Monteur Neff ist das Gerät defekt.", "Neff"),
    ("Laut Mitarbeiter Hilti ist das Gerät defekt.", "Hilti"),
    ("Laut Monteur Buderus wurde der Brenner falsch eingestellt.", "Buderus"),
])
def test_n4_bekannte_marke_hinter_laut_und_firmen_personenwort_gemeldet(text, marke):
    assert not _geschwaerzt(text, marke), _stellen(_funde(text))
    assert any(marke == t for t, _ in _verdacht(text)), _verdacht(text)


@braucht_modell
@pytest.mark.parametrize("text, name", [
    ("Laut Nachbar Viessmann war das Fenster offen.", "Viessmann"),
    ("Rücksprache mit Monteur Viessmann am Montag.", "Viessmann"),
    ("Monteur Viessmann kam am Montag.", "Viessmann"),
    ("Laut Monteur Viessmann, Tel. 0171 2345678, ist der Kessel defekt.", "Viessmann"),
    ("Wir haben mit Sachbearbeiterin Dyson telefoniert.", "Dyson"),
    ("Laut Monteur Bosch ist die Kartusche baugleich.", "Bosch"),
    ("Laut Monteur Zirngibl ist die Kartusche baugleich.", "Zirngibl"),
])
def test_n4_marke_mit_personenbeleg_bleibt_geschwaerzt(text, name):
    assert _geschwaerzt(text, name), _stellen(_funde(text))


# ----------------------------------------------------------------------
# AB3-04 (V7, V2): Alltags- und Schadenwörter mit Familiennamen-Eintrag hinter einem Personenwort mit Begleiter – ohne
# sicheren Namensbeleg gemeldet statt geschwärzt; "vom Kratzer" ist kein Hausname
# ----------------------------------------------------------------------
AB3_04_WOERTER = ["Rauch", "Schimmel", "Holz", "Licht", "Sturm", "Frost", "Hagel", "Brand", "Rost", "Ruß", "Schnee",
                  "Putz", "Mauer", "Staub", "Schutt", "Fleck", "Stein", "Keller", "Moos", "Nebel"]


@braucht_modell
@pytest.mark.parametrize("wort", AB3_04_WOERTER)
def test_ab3_04_schadenwort_hinter_personenwort_gemeldet_nicht_geschwaerzt(wort):
    for text in (f"Der Gutachter hat beim Mieter {wort} festgestellt.", f"Er hat dem Nachbarn {wort} gezeigt."):
        assert _gemeldet_nicht_geschwaerzt(text, wort), (text, _stellen(_funde(text)), _verdacht(_ausgabe(text)[0]))


@braucht_modell
@pytest.mark.parametrize("text, wort", [
    ("Er hat dem Nachbarn Wasser abgegraben.", "Wasser"),
    ("Wir haben dem Vermieter Bescheid gegeben.", "Bescheid"),
    ("Er hat dem Kollegen Geld geliehen.", "Geld"),
    ("Er schickte dem Sachbearbeiter Fotos.", "Fotos"),
    ("Anbei das Foto vom Kratzer.", "Kratzer"),
    ("Anbei das Foto vom Kleber.", "Kleber"),
])
def test_ab3_04_substantiv_bleibt_ungeschwaerzt(text, wort):
    assert not _beruehrt(text, wort), _stellen(_funde(text))


@braucht_modell
@pytest.mark.parametrize("text, name", [
    ("Beim Nachbarn Zirngibl lief das Wasser durch die Decke.", "Zirngibl"),
    ("Der Vermieter Kranawetter hat gekündigt.", "Kranawetter"),
    ("Beim Nachbarn Rauch hat es gebrannt.", "Rauch"),
    ("Laut Nachbar Rauch war das Fenster offen.", "Rauch"),
    ("Er arbeitet beim Wastlbauer als Knecht.", "Wastlbauer"),
])
def test_ab3_04_name_mit_beleg_bleibt_geschwaerzt(text, name):
    assert _geschwaerzt(text, name), _stellen(_funde(text))


@pytest.mark.parametrize("text, name", [
    ("Er hat mit dem Kollegen Wolf telefoniert.", "Wolf"),
    ("Beim Nachbarn Fuchs brannte Licht.", "Fuchs"),
    ("Die Schlüssel liegen beim Nachbarn Winter.", "Winter"),
    ("Wir haben dem Mieter Bauer gekündigt.", "Bauer"),
])
def test_ab3_04_mehrdeutiger_name_hinter_begleiter_nie_still(text, name):
    """Die Kehrseite von AB3-04: ein echter Familienname, der zugleich ein gewöhnliches Wort ist, hinter einem
    Personenwort mit Begleiter ist ohne Verb einer Person nicht sicher ein Name – er wird dann gemeldet, nie still
    gelassen (Wortart des Sprachmodells ist hier kein sicherer Beleg)."""
    assert _weg_oder_gemeldet(text, name), (_stellen(_funde(text)), _verdacht(_ausgabe(text)[0]))


# ----------------------------------------------------------------------
# AB3-05 (V5): Familienname mit Artikel am Satzanfang mit Verben eines Schadens, weibliche Form auf "-erin"
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, name", [
    ("Der Gruber hat den Schaden gemeldet.", "Gruber"),
    ("Der Hintermoser hat den Schaden gemeldet.", "Hintermoser"),
    ("Der Lackner hat den Unfall verursacht.", "Lackner"),
    ("Die Wimmerin hat angerufen.", "Wimmerin"),
    ("Die Moserin hat den Wagen gefahren.", "Moserin"),
    ("Die Huberin hat den Unfall gesehen.", "Huberin"),
    ("Den Unfall verursachte der Riedhalter.", "Riedhalter"),
    ("Den Schaden meldete der Holzwohner.", "Holzwohner"),
    ("Gemeldet hat den Schaden der Brandstätter.", "Brandstätter"),
    ("Der Haslinger meldete den Schaden am Montag.", "Haslinger"),
])
def test_ab3_05_familienname_mit_schadenverb_gemeldet(text, name):
    assert _weg_oder_gemeldet(text, name), (_stellen(_funde(text)), _verdacht(text))


@pytest.mark.parametrize("text, wort", [
    ("Der Hagel hat den Schaden verursacht.", "Hagel"),
    ("Der Sturm hat den Schaden verursacht.", "Sturm"),
    ("Die Feuerwehr hat den Schaden gemeldet.", "Feuerwehr"),
    ("Der Mieter hat den Schaden gemeldet.", "Mieter"),
    ("Den Schaden meldete der Mieter.", "Mieter"),
    ("Den Unfall verursachte der Fahrer.", "Fahrer"),
    ("Den Unfall verursachte der Anhänger.", "Anhänger"),
    ("Die Nachbarin hat angerufen.", "Nachbarin"),
    ("Die Kollegin hat angerufen.", "Kollegin"),
    ("Die Lehrerin hat angerufen.", "Lehrerin"),
])
def test_ab3_05_gegenproben(text, wort):
    assert _lesbar_ohne_meldung(text, wort), (_stellen(_funde(text)), _verdacht(text))


# Probe gen3 der Abnahme: unbekannter Familienname auf "-er" ohne Namensgestalt am Satzanfang (männliche Form)
@pytest.mark.parametrize("text, name", [
    ("Der Mooshammer hat angerufen.", "Mooshammer"),
    ("Der Hinterstocker hat den Schaden gemeldet.", "Hinterstocker"),
    ("Der Kreuthammer hat den Unfall verursacht.", "Kreuthammer"),
])
def test_ab3_05_familienname_auf_er_am_satzanfang_gemeldet(text, name):
    assert _weg_oder_gemeldet(text, name), (_stellen(_funde(text)), _verdacht(text))


@pytest.mark.parametrize("text, wort", [
    ("Der Vater hat angerufen.", "Vater"),
    ("Der Absender hat den Brief geschickt.", "Absender"),
    ("Der Versicherer hat den Schaden reguliert.", "Versicherer"),
    ("Der Hersteller hat geantwortet.", "Hersteller"),
    ("Der Teilnehmer hat angerufen.", "Teilnehmer"),
    ("Der Unfallgegner hat angerufen.", "Unfallgegner"),
])
def test_ab3_05_bekanntes_wort_auf_er_am_satzanfang_ohne_meldung(text, wort):
    assert _lesbar_ohne_meldung(text, wort), (_stellen(_funde(text)), _verdacht(text))


# Offener Punkt der vierten Nachbesserung (Probe leck_er_endung, 9 still): ein unbekannter Familienname aus
# Bestimmungswort und dem Grundwort eines Rollenworts auf "-er" hinter einem Verb einer Person und Artikel war von
# einem Rollenwort nicht zu unterscheiden und blieb ohne Meldung. Grundsatz: im Zweifel melden.
@pytest.mark.parametrize("text, name", [
    ("Am Steuer saß der Leitgeber, als der Unfall passierte.", "Leitgeber"),
    ("Den Unfall verursachte der Kirchhelfer.", "Kirchhelfer"),
    ("Dann rief der Bergleser die Polizei.", "Bergleser"),
    ("Laut Polizei fuhr der Haslbecher zu schnell.", "Haslbecher"),
    ("Am Steuer saß die Pointweckerin, als es krachte.", "Pointweckerin"),
    ("Den Schaden meldete der Lechdrucker am Montag.", "Lechdrucker"),
    ("Wie der Hinterführer sagte, war die Ampel rot.", "Hinterführer"),
    ("Am Steuer saß der Kreuzläufer.", "Kreuzläufer"),
    ("Gefahren ist der Brunnfahrer, nicht seine Frau.", "Brunnfahrer"),
])
def test_n4_familienname_aus_bestimmungswort_und_rollenwort_gemeldet(text, name):
    assert _weg_oder_gemeldet(text, name), (_stellen(_funde(text)), _verdacht(text))


@pytest.mark.parametrize("text, wort", [
    ("Am Steuer saß der Beifahrer, als der Unfall passierte.", "Beifahrer"),
    ("Am Steuer saß der Mitfahrer.", "Mitfahrer"),
    ("Den Unfall verursachte der Radfahrer.", "Radfahrer"),
    ("Den Schaden meldete der Versicherungsnehmer.", "Versicherungsnehmer"),
    ("Laut Polizei fuhr der Busfahrer zu schnell.", "Busfahrer"),
    ("Dann rief der Anwohner die Polizei.", "Anwohner"),
    ("Dann fuhr der Bagger weg.", "Bagger"),
    ("Dann rief der Untermieter an.", "Untermieter"),
    ("Den Schaden verursachte der Mitarbeiter.", "Mitarbeiter"),
    ("Am Steuer saß die Beifahrerin.", "Beifahrerin"),
    ("Gefahren ist der Unfallfahrer.", "Unfallfahrer"),                  # gewöhnliches Wort + Rollen-Grundwort
    ("Am Steuer saß der Fahrradfahrer.", "Fahrradfahrer"),
    ("Am Steuer saß der Lieferwagenfahrer.", "Lieferwagenfahrer"),
    ("Den Schaden meldete der Grundstücksbesitzer.", "Grundstücksbesitzer"),
])
def test_n4_rollenwort_auf_er_ohne_namensverdacht(text, wort):
    assert _lesbar_ohne_meldung(text, wort), (_stellen(_funde(text)), _verdacht(text))


@pytest.mark.parametrize("text, wort", [
    ("Den Schaden meldete der Hausbesitzer.", "Hausbesitzer"),
    ("Am Steuer saß der Schulbusfahrer.", "Schulbusfahrer"),
])
def test_n4_seltenes_rollenwort_auf_er_hoechstens_gemeldet(text, wort):
    """Die Kehrseite: ein Rollenwort, dessen Bestimmungswort die Wissensbasis nicht kennt, wird gemeldet, aber nie
    geschwärzt."""
    assert not _beruehrt(text, wort), _stellen(_funde(text))
    assert _gemeldet_nicht_geschwaerzt(text, wort), _verdacht(text)


# ----------------------------------------------------------------------
# AB3-06 (V3): Beruf im Genitiv, im Relativsatz, Tätigkeit nach ihrem Grundwort, Rolle mit gewohnter Tätigkeit
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, beruf", [
    ("Er übt den Beruf des Schreiners aus.", "Schreiners"),
    ("Sie übt den Beruf des Bäckers aus.", "Bäckers"),
    ("Er übt seit Jahren den Beruf des Maurers aus.", "Maurers"),
    ("Ihr Mann, der Polizist ist, war zuhause.", "Polizist"),
    ("Sie arbeitet als Putzfrau.", "Putzfrau"),
    ("Sie ist als Putzkraft tätig.", "Putzkraft"),
    ("Er arbeitet als Paketbote.", "Paketbote"),
])
def test_ab3_06_beruf_weitere_formen_geschwaerzt(text, beruf):
    assert _geschwaerzt(text, beruf), _stellen(_funde(text))


@pytest.mark.parametrize("text, beruf", [
    ("Sie macht als Gutachterin Hausbesuche.", "Gutachterin"),
    ("Er betreut als Pfleger drei Patienten.", "Pfleger"),
    ("Er jobbt als Erntehilfe in Bayern.", "Erntehilfe"),
])
def test_ab3_06_rolle_mit_gewohnter_taetigkeit_gemeldet(text, beruf):
    assert _weg_oder_gemeldet(text, beruf), (_stellen(_funde(text)), _verdacht(text))


@pytest.mark.parametrize("text, wort", [
    ("Der Zeuge, der Fahrer war, sagte aus.", "Fahrer"),
    ("Er war als Fahrer bei dem Unfall beteiligt.", "Fahrer"),
    ("Er macht als Zeuge eine Aussage.", "Zeuge"),
    ("Er war als Gutachter beim Ortstermin.", "Gutachter"),
    ("Der Gutachter des Versicherers hat den Schaden besichtigt.", "Gutachter"),
    ("Wir sind als Versicherungsmakler für Sie tätig.", "Versicherungsmakler"),
    ("Sie ist Ehefrau des Versicherungsnehmers.", "Ehefrau"),
])
def test_ab3_06_gegenproben(text, wort):
    assert _lesbar_ohne_meldung(text, wort), (_stellen(_funde(text)), _verdacht(text))


# ----------------------------------------------------------------------
# AB3-08: Selbstkontrolle bei vielen Platzhaltern in einer Zeile – Platzhalter-Abfragen über sortierte Spannen (bisect)
# ----------------------------------------------------------------------
_AB3_08_BAUSTEIN = "Haustür Code [ZUGANGSDATEN], beim Nachbarn [NAMEN] und [NAMEN], Kontakt [TELEFON]; "


def test_ab3_08_viele_platzhalter_in_einer_zeile_wachsen_linear():
    """75 gegen 600 Platzhalter auf einer Zeile: jede Abfrage "Platzhalter an der Stelle?", "Platzhalter daneben?" und
    "gesperrt?" lief über alle Platzhalter (bei 600 Kästen 15,7 s); jetzt über die sortierten Spannen."""
    import zeitmessung
    ph = ["[ZUGANGSDATEN]", "[NAMEN]", "[TELEFON]"]
    klein, gross = _AB3_08_BAUSTEIN * 19, _AB3_08_BAUSTEIN * 150
    pruefe_text(klein, platzhalter=ph)
    wachstum, _, zeit = zeitmessung.wachstum_messen(lambda: pruefe_text(klein, platzhalter=ph),
                                                    lambda: pruefe_text(gross, platzhalter=ph), 8,
                                                    wiederholungen=1, schranke=2.0)
    assert wachstum < 2.0, f"pruefe_text wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_ab3_08_platzhalter_abfragen_gleiches_ergebnis():
    """Die Abfragen über sortierte Spannen geben dasselbe wie der Durchlauf über alle Platzhalter (auch mit
    überlappenden, gleichen und anliegenden Platzhaltern)."""
    from anonymisierer import restrisiko, seitenmodell as sm
    text = "Herr [PERSON A]-[PERSON B] [NAMEN] Code [ZUGANGSDATEN] [PLZ ORT]Trier und [ADRESSE], Rest"
    m = sm.dokument_aus_text(text).seiten[0]
    p = restrisiko._Seitenpruefung(m, restrisiko._Wissen(restrisiko._wissen_laden()),
                                   platzhalter=["[PERSON A]-[PERSON B]", "[NAMEN]"])
    for s in range(len(text)):
        for e in range(s + 1, min(len(text), s + 12) + 1):
            erwartet = any(ps < e and pe > s for ps, pe in p.platzhalter)
            assert p.ist_platzhalter_bei(s, e) == erwartet, (s, e)
            erwartet = any(gs < e and ge > s for gs, ge, _ in p.gesperrt)
            assert p.ist_gesperrt(s, e) == erwartet, (s, e)
    for s, e in [(m_.start(), m_.end()) for m_ in __import__("re").finditer(r"\w+", text)]:
        alt = None
        for ps, pe in p.platzhalter:
            if 0 <= s - pe <= 2 and set(text[pe:s]) <= {" ", "-"}:
                alt = (ps, pe)
                break
            if 0 <= ps - e <= 2 and set(text[e:ps]) <= {" ", "-", ","}:
                alt = (ps, pe)
                break
        neu = p.neben_platzhalter(s, e)
        assert alt is None or neu == alt, (text[s:e], alt, neu)
