"""Nachbesserung 4 nach der zweiten Abnahme von integration-r7 (Stand fbd755b).

Je Befund der Abnahme (Linse Lecks: R1, R2, V1–V8; Linse Über-Schwärzung/Laufzeit/Doku: A2-01 bis A2-15) die Zeilen
der Abnahme, Abwandlungen und Gegenproben – nicht geheime Nachbarn bleiben lesbar. Wo eine Regel der Erkennung greift,
prüft ein Test auch die Selbstkontrolle (restrisiko.py) auf dem Ausgabetext. Alle Personen, Nummern und Anschriften
sind frei erfunden."""

import pymupdf as fitz
import pytest

from anonymisierer import muster
from anonymisierer.analyse import analysiere_pdf, analysiere_text
from anonymisierer.restrisiko import pruefe_text

ALLE = {k for k, _, _, _, an in muster.KATEGORIEN if an}


# ----------------------------------------------------------------------
# Hilfsfunktionen (wie tests/test_abnahme_r7.py)
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


def _gemeldet_in_ausgabe(text, wert) -> bool:
    aus, ph = _ausgabe(text)
    return any(wert in t or (len(t) >= 3 and t in wert) for t, _ in _verdacht(aus, platzhalter=ph))


def _weg_oder_gemeldet(text, wert) -> bool:
    aus, ph = _ausgabe(text)
    if wert not in aus:
        return True
    return any(wert in t or (len(t) >= 3 and t in wert) for t, _ in _verdacht(aus, platzhalter=ph))


def _lesbar_ohne_meldung(text, wert) -> bool:
    """Weder geschwärzt noch in der Ausgabe gemeldet."""
    aus, ph = _ausgabe(text)
    return wert in aus and not any(wert in t or (len(t) >= 3 and t in wert)
                                   for t, _ in _verdacht(aus, platzhalter=ph))


def _pdf_stellen(pfad, kategorie=None) -> set:
    erg = analysiere_pdf(pfad, ALLE, [], [], profil="hoch")
    assert not erg.get("fehler"), erg.get("fehler")
    return {st["text"] for f in erg["funde"] if kategorie is None or f["kategorie"] == kategorie
            for st in f["stellen"] if st.get("an", True)}


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


# ----------------------------------------------------------------------
# R1: Klammer, Anführungszeichen, doppelter Gedankenstrich oder Pfeil am Gegenstand vor "Code" (Regression aus bb30a80)
# ----------------------------------------------------------------------
R1_FORMEN = [
    ("(Haustür) Code 1357", "1357"),
    ("Haustür) Code 1357", "1357"),
    ("Garage (Tor) Code 4419", "4419"),
    ("Schlüsselbox (links neben der Tür) Code 2468", "2468"),
    ("Im Schlafzimmer steht ein Tresor (Möbeltresor) Code 3141", "3141"),
    ("Die Eingangstür–– Code 8264 (neu)", "8264"),
    ("Bitte das Hoftor benutzen (Hoftor) Code 2244", "2244"),
    ("(Wohnungstür) Code: 5577", "5577"),
    ("Haustür -- Code 1357", "1357"),
    ("„Haustür“ Code 1357", "1357"),
    ("Haustür -> Code 1357", "1357"),
    ("Haustür / Code 1357", "1357"),
    ("Alarmanlage --> Code 2580", "2580"),
    # OCR liest den Doppelstrich als Bindestriche direkt am Wort (Probe r1_doppelstrich auf dem Scan)
    ("Die Eingangstür-- Code 8264 (neu)", "8264"),
    ("Die Eingangstür- Code 8264", "8264"),
    ("Die Eingangstür--Code 8264", "8264"),
    ("Garagen-Tor-- Code 4419", "4419"),
]


@pytest.mark.parametrize("text, wert", R1_FORMEN)
def test_r1_code_hinter_gegenstand_mit_klammer_oder_strich(text, wert):
    assert _geschwaerzt(text, wert, "zugangsdaten"), _stellen(_funde(text))
    assert any(wert in t for t, _ in _verdacht(text)), _verdacht(text)       # Selbstkontrolle: dieselbe Regel


@pytest.mark.parametrize("text, wert", [
    ("(Tarif) Code 1357", "1357"),
    ("Garage (Tarif) Code 1357", "1357"),
    ("Schaden an der Garage, Code 4711", "4711"),
    ("Inspektor (Code 2207) hat aufgenommen.", "2207"),
    ("Haustür-Sprechanlage Code 8264 laut Typenschild", "8264"),
    ("Rabatt-- Code 8264", "8264"),
])
def test_r1_gegenproben(text, wert):
    assert not _geschwaerzt(text, wert, "zugangsdaten"), _stellen(_funde(text))


def test_r1_scan(tmp_path):
    pdf = _scan_pdf(tmp_path / "r1.pdf", ["Hinweise für den Handwerker", "(Haustür) Code 1357",
                                          "Garage (Tor) Code 4419", "Tresor (Keller) Code 3141"])
    stellen = _pdf_stellen(pdf, "zugangsdaten")
    for wert in ("1357", "4419", "3141"):
        assert any(wert in s for s in stellen), (wert, stellen)


# ----------------------------------------------------------------------
# V1: Gegenstand vor einem Klammerzusatz, mit Nummer, in der Zeile davor; Schlüsselbox, Keller, Einfahrt; Bedienung
# "mit <Ziffern>"; Code ohne sicheren Gegenstand: gemeldet
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert", [
    ("Tresor (Keller) Code 3141", "3141"),
    ("Wohnungstür (2. OG) Code 5577", "5577"),
    ("Briefkasten (Haus 2) Code 5566", "5566"),
    ("Schlüsselbox Code 8642", "8642"),
    ("Tor 2: Code 1593", "1593"),
    ("Garage 3 – Code 4419", "4419"),
    ("Tiefgarage – Einfahrt: Code 6620", "6620"),
    ("Haustür:\nCode 1357", "1357"),
    ("Zum Heizungskeller kommen Sie mit dem Code 9911.", "9911"),
    ("Die Alarmanlage im Flur schaltet man mit 6482 aus.", "6482"),
    ("Das Garagentor öffnet sich mit 4455.", "4455"),
    ("Code der Keller: 9911", "9911"),
])
def test_v1_zugangscode_weitere_formen(text, wert):
    assert _geschwaerzt(text, wert, "zugangsdaten"), _stellen(_funde(text))


@pytest.mark.parametrize("text, wert", [
    ("Code: 7319", "7319"),
    ("Der Schlüssel liegt in der Schlüsselbox, Code 8642.", "8642"),
    ("Schlüsselsafe an der Garage, Code 8642", "8642"),
    ("Alarmanlage ist scharf, Code 2580, bitte vor dem Betreten ausschalten.", "2580"),
    # Proben A (beide alten Stände STILL): "ist" zwischen "Code" und Wert, Schloss als Feldname ohne "Code"
    ("Der Hausmeister öffnet die Tür, Code ist 4711.", "4711"),
    ("Haustür: 1357", "1357"),
    ("Tor zur Tiefgarage: 4455", "4455"),
    ("Tor zur Tiefgarage:\n4455", "4455"),
    ("Schlüsselliste\nHaustür:\n1357\nKeller:\n2468", "2468"),
])
def test_v1_zugangscode_ohne_sicheren_gegenstand_gemeldet(text, wert):
    assert _weg_oder_gemeldet(text, wert), (_stellen(_funde(text)), _verdacht(text))


@pytest.mark.parametrize("text, wert", [
    ("Garage: 120 Stellplätze", "120"),
    ("Garagentor: 2019 erneuert", "2019"),
    ("Baujahr der Garage: 2019", "2019"),
    ("Haustür: 3 Schlüssel übergeben", "3"),
    ("Garage: Fehlercode 4711", "4711"),
    ("Tiefgarage:\n120 Stellplätze auf zwei Ebenen", "120"),
])
def test_v1_schloss_feld_gegenproben(text, wert):
    assert _lesbar_ohne_meldung(text, wert), (_stellen(_funde(text)), _verdacht(text))


@pytest.mark.parametrize("text, wert", [
    ("Die Alarmanlage wurde mit 2500 Euro bezahlt.", "2500"),
    ("Das Garagentor wurde mit 1200 Euro repariert.", "1200"),
    ("Der Keller ist mit 1500 Litern vollgelaufen.", "1500"),
    ("Die Haustür hat einen Schaden, Code 4711 laut Schadenkatalog.", "4711"),
    ("Schaden an der Garage, Code 4711 laut Schadenkatalog", "4711"),
])
def test_v1_gegenproben(text, wert):
    assert _lesbar_ohne_meldung(text, wert), (_stellen(_funde(text)), _verdacht(text))


# ----------------------------------------------------------------------
# A2-01: Fehler-, Störungs-, Gutachten- und Positionscodes sind keine Zugangsdaten
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert", [
    ("Der Motor meldet den Code P0300, Zündaussetzer.", "P0300"),
    ("Code P0301 am Motor, Fahrzeug in der Werkstatt.", "P0301"),
    ("Motor: Code P0420, Katalysator.", "P0420"),
    ("Fehlerspeicher Motor: Code P0420 (Katalysator).", "P0420"),
    ("Schaden am Motor (Code P0301), Abschleppung nach Rosenheim.", "P0301"),
    ("Der Laptop zeigt beim Start den Code 0xC000021A.", "0xC000021A"),
    ("Die Türsprechanlage zeigt den Code E-04.", "E-04"),
    ("Code E-04 an der Türsprechanlage, Elektriker beauftragt.", "E-04"),
    ("Wir haben natürlich den Code K-2024 der Meldung geprüft.", "K-2024"),
    ("Der Gutachter hat abschließend den Code E25-3 notiert.", "E25-3"),
    ("Abschließend wurde der Code SV-2024-17 im Gutachten vergeben.", "SV-2024-17"),
    ("Inspektor (Code 2207) hat aufgenommen.", "2207"),
    ("Monitor (Code 2207-15) beschädigt.", "2207-15"),
    ("Code 4711 im Sektor B der Lagerhalle.", "4711"),
    ("Fehlalarmcode A-12 wurde dreimal gemeldet.", "A-12"),
    ("Der Zündschlosscode ist bei Mercedes hinterlegt.", "bei"),
    ("Die Alarmanlage meldete den Code E125 (Sabotagekontakt Fenster).", "E125"),
    ("Das Garagentor zeigte den Code 3017, laut Hersteller verschmutzte Lichtschranke.", "3017"),
    ("Am Tor blinkt Code 3017, laut Hersteller eine Störung der Lichtschranke.", "3017"),
    ("Das Garagentor meldet seit dem Sturm den Code F-21.", "F-21"),
    ("Das Handy zeigt den Code ERR-41 beim Laden.", "ERR-41"),
    ("Der Router meldet den Code DSL-651 seit dem Blitzeinschlag.", "DSL-651"),
    ("Das Tablet zeigt nach dem Sturz den Code 0x12AB.", "0x12AB"),
    ("Der Rauchmelder an der Haustür zeigt den Code E-07.", "E-07"),
    ("Code 0x80070005 am Computer nach dem Überspannungsschaden.", "0x80070005"),
])
def test_a2_01_fehlercodes_bleiben_lesbar(text, wert):
    assert not _geschwaerzt(text, wert, "zugangsdaten"), _stellen(_funde(text))
    assert not any(wert in t and "Zugang" in g for t, g in _verdacht(text)), _verdacht(text)


@pytest.mark.parametrize("text, wert", [
    ("Haustür: Code 4826", "4826"),
    ("Die Haustür hat den Code 1357.", "1357"),
    ("Das Handy hat den Code 4711.", "4711"),
    ("Code 4455 für die Tiefgarage", "4455"),
    ("Alarmanlage Code 8-4-2-6", "8-4-2-6"),
])
def test_a2_01_zugangscodes_bleiben_geschwaerzt(text, wert):
    assert _geschwaerzt(text, wert, "zugangsdaten"), _stellen(_funde(text))


@pytest.mark.parametrize("text, wert", [
    ("Der Einbruch wurde angezeigt, die Alarmanlage hat den Code 2580.", "2580"),
    ("Anzeige bei der Polizei erstattet, Haustür (Hof) Code 1357", "1357"),
    ("Schadenanzeige Einbruch: Code der Alarmanlage 2580", "2580"),
    ("Einbruch gemeldet am 3.4.; Tresor Code 4711", "4711"),
    ("Laut Schadenanzeige hat die Haustür den Code 1357.", "1357"),
])
def test_a2_01_anzeige_und_meldung_sind_kein_geraetefehler(text, wert):
    """Anzeige und Meldung sind beim Makler die Schaden- oder Strafanzeige, nicht die Anzeige eines Geräts: ein Code
    am Schloss im selben Satz bleibt ein Zugangscode (Gegenproben "zeigt", "meldet" oben)."""
    assert _geschwaerzt(text, wert, "zugangsdaten"), _stellen(_funde(text))


def test_a2_10_code_mit_langem_wort_waechst_linear():
    """"Code für die " + "alarm" × n: das Muster eines Schlosses lief auf dem Wort dahinter quadratisch zurück (64k: 9,6 s
    statt 0,4 s); jetzt hat ein Gegenstand höchstens 40 Zeichen."""
    import zeitmessung
    from anonymisierer import kennungsformen
    for erzeuge in (lambda n: "Code für die " + "alarm" * (n // 5) + "-x",
                    lambda n: "Code 1234 für die " + "tür" * (n // 3) + "-x",
                    lambda n: "tresor" * (n // 6) + "-x Code 1234"):
        k, g = erzeuge(4000), erzeuge(32000)
        kennungsformen.zugangsdaten(k)
        wachstum, _, zeit = zeitmessung.wachstum_messen(lambda: kennungsformen.zugangsdaten(k),
                                                        lambda: kennungsformen.zugangsdaten(g), 8,
                                                        wiederholungen=1, schranke=2.0)
        assert wachstum < 2.0, f"zugangsdaten wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


# ----------------------------------------------------------------------
# R2 / A2-09: Familienname mit Artikel und Sachwort-Endung hinter einem Personen-Verb – gemeldet
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, name", [
    ("Am Steuer saß der Kirchsteiger und telefonierte.", "Kirchsteiger"),
    ("Laut Polizei lenkte der Hochsteiger den Wagen.", "Hochsteiger"),
    ("Dann rief der Hofsteiger die Polizei.", "Hofsteiger"),
    ("Am Steuer saß der Oberhalter, daneben seine Frau.", "Oberhalter"),
    ("Den Traktor fuhr der Grubhalter.", "Grubhalter"),
    ("Es sagte der Eckhalter, er habe gebremst.", "Eckhalter"),
    ("Laut Zeugin war der Kirchsteiger am Steuer.", "Kirchsteiger"),
    ("Den Traktor lenkte der Wurmhalter auf dem Feldweg.", "Wurmhalter"),
    ("Dann rief der Gschwendwohner die Feuerwehr.", "Gschwendwohner"),
    ("Zuletzt erklärte der Wimmspieler, er habe nichts gesehen.", "Wimmspieler"),
    ("Am Steuer saß die Kirchsteigerin.", "Kirchsteigerin"),
    ("wie die Hochsteigerin sagte", "Hochsteigerin"),
    ("Den Traktor steuerte die Hofsteigerin.", "Hofsteigerin"),
])
def test_r2_familienname_mit_sachwort_endung_gemeldet(text, name):
    assert _weg_oder_gemeldet(text, name), _verdacht(text)


@pytest.mark.parametrize("text, wort", [
    ("Dann rief der Hausbewohner die Polizei.", "Hausbewohner"),
    ("Dann rief der Bewohner die Polizei.", "Bewohner"),
    ("Dann rief der Einwohner die Polizei.", "Einwohner"),
    ("Am Steuer saß der Untermieter.", "Untermieter"),
    ("Dann rief der Vorbesitzer an.", "Vorbesitzer"),
    ("Am Steuer saß der Mitfahrer.", "Mitfahrer"),
    ("Dann rief der Aufsteiger die Polizei.", "Aufsteiger"),
    ("Danach erklärte der Betreiber der Anlage, er habe keine Wartung beauftragt.", "Betreiber"),
])
def test_r2_gegenproben_rollenwoerter(text, wort):
    assert not any(wort in t for t, _ in _verdacht(text)), _verdacht(text)


# V5: Zwischenwörter zwischen Verb und Artikel, Familienname am Satzanfang
@pytest.mark.parametrize("text, name", [
    ("Am Steuer saß wohl der Grubmüller.", "Grubmüller"),
    ("Gefahren ist dann aber der Stockinger.", "Stockinger"),
    ("Erzählt hat es die Wimmerin.", "Wimmerin"),
    ("Der Lackner hat den Wagen gefahren.", "Lackner"),
    ("Am Steuer saß zum Unfallzeitpunkt der Moosleitner.", "Moosleitner"),
    ("Gefahren ist laut Polizei die Hinterstoißerin.", "Hinterstoißerin"),
    ("Bestätigt hat das der Fellner.", "Fellner"),
    # Sonde A: Präpositionalgruppe oder Objekt zwischen Verb und Artikel
    ("Am Steuer saß nach Angaben der Polizei der Hinterstoißer.", "Hinterstoißer"),
    ("Das Fahrzeug lenkte zu diesem Zeitpunkt der Kollmannsberger.", "Kollmannsberger"),
    ("Gefahren hat das Auto der Brunnhuber.", "Brunnhuber"),
])
def test_v5_familienname_mit_zwischenwoertern(text, name):
    assert _weg_oder_gemeldet(text, name), _verdacht(text)


@pytest.mark.parametrize("text, wort", [
    ("Der Fahrer hat den Wagen gefahren.", "Fahrer"),
    ("Am Steuer saß zum Unfallzeitpunkt der Beifahrer.", "Beifahrer"),
    ("Der Anwohner hat die Polizei gerufen.", "Anwohner"),
    ("Der Versicherungsnehmer hat den Schaden gemeldet.", "Versicherungsnehmer"),
    ("Am Steuer saß nach Angaben der Polizei der Beifahrer.", "Beifahrer"),
    ("Gefahren ist nach Angaben der Polizei der Wagen.", "Wagen"),
    ("Gefahren hat das Auto der Fahrlehrer.", "Fahrlehrer"),
])
def test_v5_gegenproben(text, wort):
    assert not any(wort in t for t, _ in _verdacht(text)), _verdacht(text)


# ----------------------------------------------------------------------
# A2-02, N8/V8: Fortsetzung einer Personentabelle auf der Folgeseite
# ----------------------------------------------------------------------
_KINDER = ["Name\t\tVorname\t\tgeb. am", "Hinterwimmer\t\tLuisa\t\t14.03.2014",
           "Hinterwimmer\t\tMaximilian\t\t02.09.2016"]
_TARIFE = ["Übersicht der gewählten Tarifbausteine", "Zahnersatz\t\tRegelversorgung\t\t01.01.2026",
           "Sehhilfen\t\tBrillengestell\t\t01.07.2026", "Heilpraktiker\t\tNaturheilkunde\t\t01.01.2027"]


def _pdf_seiten(pfad, seiten, xs=(60, 220, 380)):
    doc = fitz.open()
    for zeilen in seiten:
        seite = doc.new_page(width=595, height=842)
        for i, zeile in enumerate(zeilen):
            teile = zeile.split("\t\t")
            for k, teil in enumerate(teile):
                if teil:
                    seite.insert_text((xs[k] if len(teile) > 1 else xs[0], 80 + 16 * i), teil, fontsize=10,
                                      fontname="helv")
    doc.save(pfad)
    doc.close()
    return pfad


@pytest.mark.parametrize("hinweis", ["Es gelten die Bedingungen umstehend.", "Die Tarifbausteine finden Sie umseitig.",
                                     "Die Tarifbausteine finden Sie auf der Folgeseite.",
                                     "Die Tarifbausteine sind beigefügt."])
def test_a2_02_tariftabelle_auf_folgeseite_bleibt_lesbar(tmp_path, hinweis):
    pdf = _pdf_seiten(tmp_path / "tarif.pdf", [_KINDER + [hinweis], _TARIFE])
    stellen = _pdf_stellen(pdf)
    assert not ({"Regelversorgung", "Brillengestell", "01.01.2026", "01.07.2026", "Naturheilkunde"} & stellen), stellen
    assert {"14.03.2014", "02.09.2016"} <= stellen, stellen


@pytest.mark.parametrize("hinweis", ["Fortsetzung umseitig", "Weitere Kinder umseitig", "Weitere Kinder siehe Folgeseite.",
                                     "Fortsetzung auf Seite 2"])
def test_v8_fortsetzung_mit_einer_zeile(tmp_path, hinweis):
    """Kündigt die Vorseite die Fortsetzung an, zählt auch eine einzelne Reihe mit einem bekannten Namen."""
    pdf = _pdf_seiten(tmp_path / "kinder.pdf", [_KINDER + [hinweis], ["Gschwendtner\t\tKreszenz\t\t09.09.2014"]])
    assert "09.09.2014" in _pdf_stellen(pdf), _pdf_stellen(pdf)


# ----------------------------------------------------------------------
# A2-03: Rolle, Organisation, "wir" und das höfliche "Sie" – kein Beruf einer Person; V3: weitere Satzstellungen
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wort", [
    ("Wir sind als Versicherungsmakler für Sie tätig.", "Versicherungsmakler"),
    ("Die Gesellschaft ist als Versicherungsmakler tätig und im Vermittlerregister eingetragen.", "Versicherungsmakler"),
    ("Als Versicherungsmakler sind wir verpflichtet, Sie umfassend zu beraten.", "Versicherungsmakler"),
    ("Als Handwerker benötigen Sie eine Betriebshaftpflicht mit Mietsachschäden.", "Handwerker"),
    ("Als Beamter haben Sie Anspruch auf Beihilfe.", "Beamter"),
    ("Als Landwirt profitieren Sie von günstigen Beiträgen.", "Landwirt"),
    ("Als Arzt sind Sie verpflichtet, eine Berufshaftpflicht nachzuweisen.", "Arzt"),
    ("Die Kanzlei Dr. Reitmayr ist als Insolvenzverwalter tätig.", "Insolvenzverwalter"),
    ("Der Sohn ist als Betreuer seiner Mutter tätig, Bestallungsurkunde anbei.", "Betreuer"),
    ("Frau Kathrin Haslinger ist als Bevollmächtigte tätig.", "Bevollmächtigte"),
    ("Die Hausverwaltung ist als Verwalter der Wohnanlage tätig.", "Verwalter"),
    ("Der Verein verdient sein Geld als Veranstalter von Konzerten.", "Veranstalter"),
    ("Herr Lorenz Thalhammer ist ehrenamtlich als Trainer im Sportverein tätig.", "Trainer"),
    ("Er ist ehrenamtlich als Schiedsrichter im Kreis Traunstein tätig.", "Schiedsrichter"),
    ("Die Jugendleiterin ist als Betreuerin bei den Zeltlagern tätig.", "Betreuerin"),
    ("Die GmbH verdient ihr Geld als Zulieferer der Automobilindustrie.", "Zulieferer"),
    ("Ich bin als öffentlich bestellter Sachverständiger für Holzbau tätig.", "Sachverständiger"),
    ("Er war als Fahrer des Fahrzeugs am Unfall beteiligt.", "Fahrer"),
    ("Seit sie Kundin ist, zahlt sie pünktlich.", "Kundin"),
])
def test_a2_03_rollen_und_organisationen_ohne_beruf(text, wort):
    assert _lesbar_ohne_meldung(text, wort), (_stellen(_funde(text)), _verdacht(text))


@pytest.mark.parametrize("text, beruf", [
    ("Sie übt den Beruf der Floristin aus.", "Floristin"),
    ("Von Beruf ist er Schreiner.", "Schreiner"),
    ("Er ist hauptberuflich Zimmerer.", "Zimmerer"),
    ("Die Nachbarin, deren Mann Polizist ist, hat angerufen.", "Polizist"),
    ("Seit sie Lehrerin ist, hat sie wenig Zeit.", "Lehrerin"),
    ("Er ist nebenberuflich als Kellner tätig.", "Kellner"),
    ("Herr Huber ist als Fahrer bei einer Spedition angestellt.", "Fahrer"),
    ("Bei der Firma Huber ist er als Elektriker tätig.", "Elektriker"),
    ("Er ist hauptberuflich Zimmerer, nebenbei Landwirt.", "Landwirt"),            # Sonde A
    ("Sie arbeitet nebenher als Kellnerin.", "Kellnerin"),
])
def test_v3_beruf_weitere_satzstellungen(text, beruf):
    assert _geschwaerzt(text, beruf, "beruf"), _stellen(_funde(text))


@pytest.mark.parametrize("text, beruf", [
    ("Er fährt nachts als Fahrer für einen Paketdienst.", "Fahrer"),
    ("Sie hilft im Altenheim als Betreuerin aus.", "Betreuerin"),
    ("Er ist als Vertreter für Landmaschinen unterwegs.", "Vertreter"),
    ("Herr Huber ist als Versicherungsvertreter tätig.", "Versicherungsvertreter"),
    ("Als Dachdecker ist er oft auf Dächern unterwegs.", "Dachdecker"),
])
def test_v3_rolle_als_beruf_gemeldet(text, beruf):
    assert _weg_oder_gemeldet(text, beruf), (_stellen(_funde(text)), _verdacht(text))


# ----------------------------------------------------------------------
# A2-04, V7: Wort hinter einem Personenwort – ohne Präposition davor und mit Begleiter nur mit Namensbeleg
# ----------------------------------------------------------------------
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
def test_a2_04_substantiv_hinter_personenwort_bleibt(text, wort):
    assert not _beruehrt(text, wort), _stellen(_funde(text))


@pytest.mark.parametrize("text, name", [
    ("Zeuge Hinterstoißer hat den Brand gemeldet.", "Hinterstoißer"),
    ("Nachbar Hingerl hat den Brand gemeldet.", "Hingerl"),
    ("Beim Nachbarn Zirngibl lief das Wasser durch die Decke.", "Zirngibl"),
    ("Wir haben mit dem Zeugen Pröbstl telefoniert.", "Pröbstl"),
    ("Kollegin Brandlhuber kommt später.", "Brandlhuber"),
    ("Nachbarin Fischbacher-Zöttl rief die Feuerwehr.", "Fischbacher-Zöttl"),   # Sonde A: auf fbd755b geschwärzt
])
def test_a2_04_v7_name_mit_namensbeleg(text, name):
    assert _geschwaerzt(text, name, "namen"), _stellen(_funde(text))


@pytest.mark.parametrize("text, marke", [
    ("Laut Monteur Buderus wurde der Brenner falsch eingestellt.", "Buderus"),
    ("Laut Monteur Vaillant ist der Wärmetauscher verkalkt.", "Vaillant"),
])
def test_a2_04_bekannte_marke_hinter_personenwort_gemeldet(text, marke):
    """Probe p01 (Prüfer B): eine bekannte Marke hinter dem Personenwort wird nicht geschwärzt, sondern gemeldet (wie auf
    1b5130a) – ein unbekanntes Wort ("Laut Nachbar Grohe", N7) und ein Nachname ("Monteur Bosch") bleiben geschwärzt."""
    assert not _geschwaerzt(text, marke), _stellen(_funde(text))
    assert any(marke == t for t, _ in _verdacht(text)), _verdacht(text)


def test_a2_04_doppelname_mit_namensteil_ohne_sachwort():
    from anonymisierer import personenkontext
    assert not personenkontext.namensgestalt("Service-Center")
    assert not personenkontext.namensgestalt("Kunden-Hotline")
    assert personenkontext.namensgestalt("Huber-Brandlhuber")
    assert personenkontext.namensgestalt("Fischbacher-Zöttl")              # ein Namensteil, kein Sachwort


@pytest.mark.parametrize("text, wort", [
    ("Monteur [PERSON A] kam am 03.03. um 9 Uhr.", "Monteur"),
    ("Mechaniker [PERSON B] hat den Schaden aufgenommen.", "Mechaniker"),
    ("Installateur [PERSON A], Tel. 0171 2345678", "Installateur"),
    ("Monteurin [PERSON A] kam.", "Monteurin"),
])
def test_a2_04_beruf_vor_personen_platzhalter_ohne_meldung(text, wort):
    """Großprobe personenwort_20s (Prüfer B): "Monteur Grohe kam …" wird jetzt geschwärzt; der Beruf vor dem
    Platzhalter ist kein unbekannter Eigenname (vorher je Zeile eine Meldung "Monteur")."""
    assert not any(wort == t for t, _ in _verdacht(text, platzhalter=["[PERSON A]", "[PERSON B]"])), \
        _verdacht(text, platzhalter=["[PERSON A]", "[PERSON B]"])


@pytest.mark.parametrize("text, wort", [
    ("Müller [PERSON A] kam.", "Müller"),
    ("Bauer [PERSON A] kam.", "Bauer"),
    ("Schreiner [PERSON A] kam.", "Schreiner"),
])
def test_a2_04_beruf_und_nachname_vor_platzhalter_gemeldet(text, wort):
    """Gegenprobe: ein Beruf, der auch ein Nachname der Wissensbasis ist, bleibt neben dem Platzhalter gemeldet."""
    assert any(wort == t for t, _ in _verdacht(text, platzhalter=["[PERSON A]"])), _verdacht(text, platzhalter=["[PERSON A]"])


# ----------------------------------------------------------------------
# A2-05, V4: Mannheimer Quadrat
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert", [
    ("Unser Stand ist in Halle B 2, 4 gemeldet, Fläche 48 Quadratmeter.", "B 2, 4"),
    ("Die Exponate wurden von Halle A 1, 2 nach B 2, 4 umgezogen.", "B 2, 4"),
    ("Lagerung der Leergutkisten in C 3, 1 gemeldet bei der Messeleitung.", "C 3, 1"),
    ("Ware in G 4, 2 gemeldet als beschädigt, Rest einwandfrei.", "G 4, 2"),
    ("Der Brand breitete sich von D 3, 2 nach E 4, 1 aus und lebte dort wieder auf.", "E 4, 1"),
    ("Die Glutnester wurden in F 2, 2 gemeldet und gelöscht.", "F 2, 2"),
    ("Der Sanitätsdienst ist in B 4, 1 gemeldet.", "B 4, 1"),
    ("Die Position ist in B 3, 4 gemeldet und wird nach Tabelle reguliert.", "B 3, 4"),
    ("Die Mitarbeiter sind in C 3, 4 der Liste gemeldet.", "C 3, 4"),
    ("Die Brandausbruchstelle liegt in Planquadrat D 3, 2 der Lageskizze.", "D 3, 2"),
])
def test_a2_05_quadrat_ohne_person_nicht_geschwaerzt(text, wert):
    assert not _beruehrt(text, wert), _stellen(_funde(text))


@pytest.mark.parametrize("text, wert", [
    ("Die Leistung nach B 1, 4 wurde dem Kunden mitgeteilt.", "B 1, 4"),
    ("Die Abrechnung erfolgt nach K 1, 2 der Tarifbestimmungen.", "K 1, 2"),
    ("Regulierung nach M 1, 2 abgeschlossen am 30.09.2025.", "M 1, 2"),
    ("Notausgänge befinden sich nach D 2, 3 und D 2, 4 hin.", "D 2, 3"),
])
def test_a2_05_nach_im_sinn_von_gemaess_ohne_meldung(text, wert):
    assert _lesbar_ohne_meldung(text, wert), (_stellen(_funde(text)), _verdacht(text))


@pytest.mark.parametrize("text, wert", [
    ("Zustellung bitte an R 3, 4 (Hinterhaus).", "R 3, 4"),                        # Sonde A
    ("Das Paket ging an P 7, 20 statt an die Firma.", "P 7, 20"),
])
def test_v4_quadrat_hinter_an_gemeldet(text, wert):
    assert _weg_oder_gemeldet(text, wert), (_stellen(_funde(text)), _verdacht(text))


@pytest.mark.parametrize("text, wert", [
    ("Die Paletten wurden von Regal R 2, 4 nach Regal R 3, 1 verzogen.", "R 3, 1"),
    ("Die Exponate wurden von Halle A 1, 2 nach B 2, 4 umgezogen.", "B 2, 4"),
])
def test_a2_05_umzug_von_sachen_mit_gegenbeleg(text, wert):
    assert not _beruehrt(text, wert), _stellen(_funde(text))


@pytest.mark.parametrize("text, wert", [
    ("Herr Brandl ist zum 1. Juli nach R 7, 3 verzogen.", "R 7, 3"),
    ("Die Familie ist in K 4, 12 gemeldet.", "K 4, 12"),
    ("Die Mieterin ist aus C 4, 9 ausgezogen.", "C 4, 9"),
    ("Umzug von G 7, 14 in die Neckarstadt geplant.", "G 7, 14"),
    ("Der Versicherte kommt aus U 3, 18 und zieht nach Viernheim.", "U 3, 18"),
    ("Resi Huber · Q 5, 12", "Q 5, 12"),
    ("Abs.: R. Huber, T 6, 3", "T 6, 3"),
    # Umzugsverben belegen die Anschrift auch ohne Person im Satz (Großprobe lang_quadrat_umzug: auf 1b5130a über das
    # "umgezogen" des vorigen Satzes geschwärzt, auf dem Zwischenstand nur gemeldet)
    ("ist nach S 2, 15 umgezogen", "S 2, 15"),
    ("Zum 1. Mai nach T 4, 12 verzogen.", "T 4, 12"),
    ("Umgezogen nach S 2, 15 am 01.05.", "S 2, 15"),
])
def test_a2_05_v4_quadrat_mit_person_geschwaerzt(text, wert):
    assert _geschwaerzt(text, wert), _stellen(_funde(text))


# ----------------------------------------------------------------------
# A2-06, V6: Grußformel mit Herkunft – Organisationseinheit darunter; Unterzeichner in der Grußzeile
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert", [
    ("Sehr geehrte Damen und Herren,\nanbei die Unterlagen.\n\nGrüße aus dem Allgäu\nAllgäuer Versicherungsdienst\n"
     "Abteilung Gewerbe", "Versicherungsdienst"),
    ("Hallo zusammen,\nTreffpunkt Stand 214.\n\nGrüße von der Messe\nIhr Vertriebsteam Süd\nMaklerbetreuung Bayern",
     "Maklerbetreuung"),
    ("Sehr geehrte Damen und Herren,\nneue Courtagesätze.\n\nGrüße aus der Zentrale\nMaklerservice\n"
     "Produktmanagement Sach", "Produktmanagement"),
    ("Hallo Team,\ndie Unterlagen sind online.\n\nGruß vom Chiemsee\nKundenservice Traunstein\nArbeitskreis Gewerbe",
     "Kundenservice"),
    ("Sehr geehrte Damen und Herren,\nder Schaden wurde dokumentiert.\n\nGrüße von der Baustelle\n"
     "Bauleitung Wohnpark Ost", "Bauleitung"),
])
def test_a2_06_organisation_unter_gruss_bleibt(text, wert):
    assert _lesbar_ohne_meldung(text, wert), (_stellen(_funde(text)), _verdacht(text))


@pytest.mark.parametrize("text, name", [
    ("Viele Grüße aus dem Allgäu, Rowenta", "Rowenta"),
    ("Grüße von Grohe", "Grohe"),
    ("Liebe Grüße von Kreszenz Moosbichler aus Inzell", "Moosbichler"),
    ("Liebe Grüße aus der Reha in Bad Aibling\nPröbstl", "Pröbstl"),
    ("Mit freundlichen Grüßen\nMax Huber\nKundenservice", "Huber"),
])
def test_v6_unterzeichner_in_oder_unter_der_grusszeile(text, name):
    assert _weg_oder_gemeldet(text, name), (_stellen(_funde(text)), _verdacht(_ausgabe(text)[0]))


@pytest.mark.parametrize("text", ["Grüße von der Messe", "Liebe Grüße von Herzen", "Viele Grüße, Ihr Team"])
def test_v6_gegenproben(text):
    assert not _stellen(_funde(text), "namen"), _stellen(_funde(text))


# ----------------------------------------------------------------------
# A2-07, V2: Hausname hinter "beim"/"vom"/"zum" – nicht ein Betrieb
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wort", [
    ("In der Nacht brannte es beim Holzhändler in Waging, Lagerhalle zerstört.", "Holzhändler"),
    ("Hagelschaden beim Gartencenter in Rosenheim, Glasdach beschädigt.", "Gartencenter"),
    ("Das zweite Rad wurde beim Fahrradhändler in Prien gestohlen.", "Fahrradhändler"),
    ("Diebstahl beim Getränkemarkt in Freilassing, Leergut gestohlen.", "Getränkemarkt"),
])
def test_a2_07_betrieb_kein_hausname(text, wort):
    assert not _beruehrt(text, wort), _stellen(_funde(text))


@pytest.mark.parametrize("text, name", [
    ("Hagelschaden beim Gruberwirt in Siegsdorf.", "Gruberwirt"),
    ("Rohrbruch beim Kasererwirt, die Gaststube ist überflutet.", "Kasererwirt"),
    ("Unfall vor dem Hof des Zellerbauern in Bergen.", "Zellerbauern"),
    ("Wir waren beim Kammerloher in Grassau.", "Kammerloher"),
    ("Die Kühe vom Lechnerbauer stehen auf der Weide.", "Lechnerbauer"),
    ("Er arbeitet beim Wastlbauer als Knecht.", "Wastlbauer"),
    ("Beim Brandlhuber war das Hoftor offen.", "Brandlhuber"),
    ("Der Weg führt zum Zellerbauern hinauf.", "Zellerbauern"),
])
def test_v2_hausname(text, name):
    assert _geschwaerzt(text, name, "namen"), _stellen(_funde(text))


# ----------------------------------------------------------------------
# A2-08: Ausfüllhinweis rechts neben dem Feldnamen "Beruf" auf einem Scan
# ----------------------------------------------------------------------
def _ocr_formular_stellen(paare):
    from anonymisierer import analyse, seitenmodell
    doc = fitz.open()
    seite = doc.new_page(width=595, height=842)
    woerter, y = [], 400.0
    for zi, (feld, wert) in enumerate(paare):
        x = 64.0
        for wi, w in enumerate(feld.split()):
            woerter.append((x, y, x + 5.5 * len(w), y + 7, w, 0, zi, wi))
            x += 5.5 * len(w) + 3
        if wert:
            x = 211.0
            for wi, w in enumerate(wert.split()):
                woerter.append((x, y - 1, x + 5.0 * len(w), y + 14, w, 1, zi, wi))
                x += 5.0 * len(w) + 3
        y += 19
    s = seitenmodell.seite_aufbauen(seite, 0, ocr_woerter=woerter, ocr_quelle="ocr")
    doc.close()
    funde = analyse._analysiere_dokument(seitenmodell.Dokument(None, [s]), ALLE, [], [])
    return {st["text"] for f in funde for st in f["stellen"] if st.get("an", True)}


@pytest.mark.parametrize("hinweis", ["Kaufmann reicht nicht, bitte genau", "Angestellte bitte Arbeitgeber nennen",
                                     "Landwirt bitte mit Betriebsnummer"])
def test_a2_08_ausfuellhinweis_rechts_neben_beruf(hinweis):
    paare = [("Vertragsnummer", "7712-449 alt"), ("6 Beruf", hinweis), ("Familienstand", "")]
    stellen = _ocr_formular_stellen(paare)
    assert not any(w in s for s in stellen for w in ("Kaufmann", "Angestellte", "Landwirt", "Arzt")), stellen


def test_a2_08_beruf_rechts_daneben_bleibt():
    paare = [("Vertragsnummer", "7712-449 alt"), ("6 Beruf", "Hufschmiedin selbständig"), ("Familienstand", "")]
    assert any("Hufschmiedin" in s for s in _ocr_formular_stellen(paare))


def _hinweis_formular_stellen(zeilen):
    """OCR-Seite wie die Probe r02 (Prüfer B) auf dem Scan: links die Feldnamen (ein Block), im Kästchen ein Wert,
    rechts daneben Ausfüllhinweise (eigener Block) – die OCR liest erst die Feldnamen, dann die Hinweise;
    zeilen = [(feld, wert, hinweis)]."""
    from anonymisierer import analyse, seitenmodell
    links, mitte, rechts, y = [], [], [], 140.0
    for zi, (feld, wert, hinweis) in enumerate(zeilen):
        x = 50.0
        for wi, w in enumerate(feld.split()):
            links.append((x, y - 9, x + 5.5 * len(w), y + 2, w, 1, zi, wi))
            x += 5.5 * len(w) + 3
        for teile, x, liste, block in ((wert, 166.0, mitte, 2), (hinweis, 300.0, rechts, 3)):
            for wi, w in enumerate((teile or "").split()):
                liste.append((x, y - 9, x + 5.0 * len(w), y + 2, w, block, zi, wi))
                x += 5.0 * len(w) + 3
        y += 34
    links.append((50.0, y - 9, 120.0, y + 2, "Unterschrift", 1, len(zeilen), 0))
    doc = fitz.open()
    seite = doc.new_page(width=595, height=842)
    s = seitenmodell.seite_aufbauen(seite, 0, ocr_woerter=links + mitte + rechts, ocr_quelle="ocr")
    doc.close()
    funde = analyse._analysiere_dokument(seitenmodell.Dokument(None, [s]), ALLE, [], [])
    return {st["text"] for f in funde for st in f["stellen"] if st.get("an", True)}


_HINWEIS_ZEILEN = [("1. Antragsteller", None, ""), ("Beruf", None, "Kaufmann reicht nicht, bitte genau"),
                   ("2. Ehepartner", None, ""), ("Beruf", None, "Beamte bitte Dienstherrn nennen"),
                   ("3. Mitversicherte Person", None, ""), ("Beruf", None, "Arzt bitte Fachrichtung angeben"),
                   ("4. Hofnachfolger", None, ""), ("Beruf", None, "Landwirt mit Fläche in Hektar")]


def test_a2_08_hinweisspalte_neben_mehreren_berufsfeldern():
    """Probe r02 (Prüfer B): vier Beruf-Felder mit leerem Kästchen, rechts daneben je ein Ausfüllhinweis; der letzte
    ("Landwirt mit Fläche in Hektar") trägt kein Hinweiswort, steht aber in derselben Hinweisspalte."""
    stellen = _hinweis_formular_stellen(_HINWEIS_ZEILEN)
    assert not any(w in s for s in stellen for w in ("Kaufmann", "Beamte", "Arzt", "Landwirt")), stellen


def test_a2_08_wert_im_kaestchen_neben_hinweisspalte():
    """Gegenprobe: ein eingetragener Wert im Kästchen steht näher am Feldnamen und bleibt geschwärzt."""
    zeilen = list(_HINWEIS_ZEILEN)
    zeilen[7] = ("Beruf", "Landwirt", "Landwirt mit Fläche in Hektar")
    stellen = _hinweis_formular_stellen(zeilen)
    assert "Landwirt" in stellen, stellen


def test_a2_08_werte_ohne_hinweis_bleiben_geschwaerzt():
    paare = [("1. Antragsteller", ""), ("Beruf", "Landwirt mit Viehhaltung"), ("2. Ehepartner", ""),
             ("Beruf", "Erzieherin")]
    stellen = _ocr_formular_stellen(paare)
    assert any("Landwirt" in s for s in stellen) and any("Erzieherin" in s for s in stellen), stellen


# ----------------------------------------------------------------------
# A2-11 (B/NP-15): Schwärzen langer, gleichförmiger Zeilen mit vielen Kästen – der Abgleich der Zeichen einer Zeile
# vor/nach apply_redactions (Platzhalter-Verschiebung, M-31) lief über difflib quadratisch (Großprobe
# lang_code_schloss: 810 Kästen auf drei Zeilen zu je 8 000 Zeichen, Schwärzen 99,6 s, davon 207 s im Profil difflib)
# ----------------------------------------------------------------------
def _codezeile(n_saetze):
    vorher = list("".join("Die Haustür hat den Code 1357.".replace(" ", "") for _ in range(n_saetze)))
    return vorher, [c.isdigit() for c in vorher]


def test_a2_11_zeichenabgleich_regelfall():
    from anonymisierer.schwaerzung import _zeichen_abgleich
    weg = [False] * 3 + [True] * 2 + [False] * 3
    assert _zeichen_abgleich(list("abcXYdef"), list("abcdef"), weg) == (
        [(0, 0), (1, 1), (2, 2), (5, 3), (6, 4), (7, 5)], True)
    vorher, weg = _codezeile(300)
    nachher = [c for c, w in zip(vorher, weg) if not w]
    paare, genau = _zeichen_abgleich(vorher, nachher, weg)
    assert genau and [b for _, b in paare] == list(range(len(nachher))) and all(not weg[a] for a, _ in paare)


@pytest.mark.parametrize("saetze", [5, 60, 300])
def test_a2_11_zeichenabgleich_mit_abweichung(saetze):
    """Fehlt anderes als erwartet (ein Nachbarzeichen mit entfernt), gleicht die längste gemeinsame Teilfolge ab –
    auf langen Zeilen abschnittsweise: jedes verbliebene Zeichen bekommt sein Gegenstück, in Reihenfolge."""
    from anonymisierer.schwaerzung import _zeichen_abgleich
    vorher, weg = _codezeile(saetze)
    nachher = [c for c, w in zip(vorher, weg) if not w]
    del nachher[7::53]
    paare, genau = _zeichen_abgleich(vorher, nachher, weg)
    assert genau
    assert all(vorher[a] == nachher[b] for a, b in paare)
    assert all(a1 < a2 and b1 < b2 for (a1, b1), (a2, b2) in zip(paare, paare[1:]))
    assert len(paare) == len(nachher)


def test_a2_11_zeichenabgleich_waechst_linear():
    import zeitmessung
    from anonymisierer.schwaerzung import _zeichen_abgleich

    def fall(n):
        vorher, weg = _codezeile(n)
        nachher = [c for c, w in zip(vorher, weg) if not w]
        del nachher[7::97]                              # abweichend: Abgleich über die Teilfolge
        return vorher, nachher, weg
    k, g = fall(150), fall(1200)
    wachstum, _, zeit = zeitmessung.wachstum_messen(lambda: _zeichen_abgleich(*k), lambda: _zeichen_abgleich(*g), 8,
                                                    wiederholungen=1, schranke=2.0)
    assert wachstum < 2.0, f"_zeichen_abgleich wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def _geschwaerzte_codezeile(n):
    """Eine Zeile mit n Zugangscodes (3 pt auf 14 400 pt Breite), die Codes mit apply_redactions entfernt: (doc,
    seite, zeilen_vorher wie _platzhalter_zeilen_vorher, Kästen)."""
    from anonymisierer import seitenmodell as sm
    doc = fitz.open()
    seite = doc.new_page(width=14400, height=200)
    seite.insert_text((10, 100), " ".join(f"Die Haustür hat den Code {1000 + i}." for i in range(n)), fontsize=3,
                      fontname="helv")
    glyphen, grund = [], None
    for b in seite.get_text("rawdict", flags=sm.TEXT_FLAGS)["blocks"]:
        for z in b.get("lines", []):
            for sp in z["spans"]:
                for ch in sp["chars"]:
                    if not ch["c"].isspace():
                        glyphen.append((ch["bbox"][0], ch["bbox"][2], ch["c"]))
                        grund = ch["origin"][1]
    glyphen.sort()
    kaesten = [r for i in range(n) for r in seite.search_for(str(1000 + i))]
    for r in kaesten:
        seite.add_redact_annot(r)
    seite.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, text=fitz.PDF_REDACT_TEXT_REMOVE)
    box = fitz.Rect(glyphen[0][0], 90, glyphen[-1][1], 102)
    return doc, seite, {0: {"glyphen": glyphen, "grundlinie": grund, "groesse": 3.0, "box": box}}, kaesten


def test_a2_11_platzhalter_verschiebung_waechst_linear():
    """40 gegen 320 Kästen auf einer Zeile: vorher wuchs die Messung um 44 x linear (320 Kästen 44,8 s), jetzt
    linear; jeder Kasten bekommt seine Verschiebung (vorher ab dem 14. Kasten keine mehr)."""
    import zeitmessung
    from anonymisierer.schwaerzung import _platzhalter_verschiebung
    k, g = _geschwaerzte_codezeile(40), _geschwaerzte_codezeile(320)
    assert len(k[3]) == 40 and len(g[3]) == 320
    aus = _platzhalter_verschiebung(g[1], g[2], g[3])
    assert all(a[0] or a[1] for a in aus[1:]), [i for i, a in enumerate(aus) if not (a[0] or a[1])][:5]
    wachstum, _, zeit = zeitmessung.wachstum_messen(lambda: _platzhalter_verschiebung(k[1], k[2], k[3]),
                                                    lambda: _platzhalter_verschiebung(g[1], g[2], g[3]), 8,
                                                    wiederholungen=1, schranke=2.0)
    assert wachstum < 2.0, f"_platzhalter_verschiebung wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_a2_11_lange_zeile_mit_vielen_kaesten(tmp_path):
    """Eine Zeile mit 120 Zugangscodes: alle geschwärzt, kein Folgewort unter einem Platzhalter (M-31 bleibt)."""
    from anonymisierer.schwaerzung import schwaerze_pdf
    zeile = " ".join(f"Die Haustür hat den Code {1000 + i}." for i in range(120))
    doc = fitz.open()
    seite = doc.new_page(width=14400, height=200)
    seite.insert_text((10, 100), zeile, fontsize=3, fontname="helv")
    pfad = tmp_path / "lang.pdf"
    doc.save(pfad)
    doc.close()
    erg = analysiere_pdf(pfad, ALLE, [], [], profil="hoch")
    werte = {st["text"] for f in erg["funde"] for st in f["stellen"]}
    assert all(str(1000 + i) in werte for i in range(120)), sorted(werte)[:5]
    aus = schwaerze_pdf(pfad, erg["funde"], ziel_ordner=tmp_path / "aus")
    assert not aus.get("fehler"), aus.get("fehler")
    with fitz.open(aus["ausgabe"]) as d:
        text = d[0].get_text()
    assert not any(str(1000 + i) in text for i in range(120))
    assert text.count("Haustür") == 120, text.count("Haustür")
    meldungen = [str(h) for h in (aus.get("hinweise") or []) + (aus.get("warnungen") or [])]
    assert not any("NACHBARWORT_BESCHAEDIGT" in h or "teilweise unter einem Platzhalter" in h for h in meldungen), \
        meldungen


# ----------------------------------------------------------------------
# A2-13 (N10): Wachstumstests mit größerer Spreizung – E-Mail-Muster nur am Wortanfang, sortierte Feldnamen in
# ocr_rohwert (OCR-Formular ohne Werte)
# ----------------------------------------------------------------------
def test_a2_13_adresse_nur_am_wortanfang_waechst_linear():
    import zeitmessung
    from anonymisierer import analyse
    k, g = "Zeuge: Hans Maier, X" + "a" * 4000, "Zeuge: Hans Maier, X" + "a" * 32000
    wachstum, _, zeit = zeitmessung.wachstum_messen(lambda: analyse._ADRESSE_RE.sub(" ", k),
                                                    lambda: analyse._ADRESSE_RE.sub(" ", g), 8,
                                                    wiederholungen=1, schranke=2.0)
    assert wachstum < 2.0, f"_ADRESSE_RE wächst um {wachstum:.2f} x linear ({zeit:.4f} s)"


def test_a2_13_feldnamen_ohne_werte_wachsen_linear():
    """OCR-Formular mit vielen Feldnamen und leeren Kästchen (200 gegen 1600 Zeilen): der Rohwert neben dem Feldnamen
    (ocr_rohwert) sucht über die je Seite sortierten Anfänge; je Aufruf neu sortiert wuchs es 18,7- statt 10,3-fach."""
    import zeitmessung
    from anonymisierer import seitenmodell, wissen
    from anonymisierer.detektoren import REGISTER, Kontext
    regel = next(e for e in REGISTER if e.name == "struktur.etikett_wert")
    kontext = Kontext(aktive=ALLE, profil="hoch", wissen=wissen)

    def formular(n):
        doc = fitz.open()
        seite = doc.new_page(width=595, height=max(842, 500 + 19 * n))
        felder = ["Kundennummer:", "Steuer-ID:", "Geburtsdatum:", "Telefon:", "Beruf", "Name"]
        woerter, y = [], 400.0
        for zi in range(n):
            x = 64.0
            for wi, w in enumerate(felder[zi % len(felder)].split()):
                woerter.append((x, y, x + 5.5 * len(w), y + 7, w, 0, zi, wi))
                x += 5.5 * len(w) + 3
            y += 19
        s = seitenmodell.seite_aufbauen(seite, 0, ocr_woerter=woerter, ocr_quelle="ocr")
        doc.close()
        return seitenmodell.Dokument(None, [s])
    klein, gross = formular(200), formular(1600)
    regel.funktion(klein, kontext)
    regel.funktion(gross, kontext)
    wachstum, _, zeit = zeitmessung.wachstum_messen(lambda: regel.funktion(klein, kontext),
                                                    lambda: regel.funktion(gross, kontext), 8,
                                                    wiederholungen=1, schranke=2.0)
    assert wachstum < 2.0, f"etikett_wert wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


# ----------------------------------------------------------------------
# A2-15: Name in einer Partnerschaft oder Kanzlei – gemeldet
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, name", [
    ("Versicherungsnehmerin: Steuerkanzlei Waldherr & Partner, Vertragsnummer EL-7720-115", "Waldherr"),
    ("Die Kanzlei Huber und Kollegen hat geschrieben.", "Huber"),
])
def test_a2_15_name_in_partnerschaft(text, name):
    assert _weg_oder_gemeldet(text, name), (_stellen(_funde(text)), _verdacht(text))
