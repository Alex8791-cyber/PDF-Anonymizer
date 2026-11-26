"""Nachbesserung 7 nach der fünften Abnahme von integration-r7 (Stand 5efcc0c).

Je Befund der Abnahme (Lecks A5-01 bis A5-15, Über-Schwärzung, Laufzeit und Doku AB5U-01 bis AB5U-14) die Zeilen der
Abnahme, eigene Abwandlungen und nicht geheime Gegenproben. Grundsätze: eine Ausnahme stuft einen möglichen geheimen
Wert höchstens von „schwärzen“ auf „melden“ herab (P1); mehrdeutige Fälle werden gemeldet, geschwärzt nur mit sicherem
Beleg, frei gelassen nur mit sicherem Gegenbeleg (P2); allgemeine Regeln statt Wortlisten (P3). Alle Personen, Codes,
Nummern und Anschriften sind frei erfunden."""

import pytest

from anonymisierer import detektoren, kennungsformen, muster, personenkontext, seitenmodell, wissen
from anonymisierer.analyse import analysiere_text
from anonymisierer.detektoren import Kontext
from anonymisierer.restrisiko import pruefe_text

ALLE = {k for k, _, _, _, an in muster.KATEGORIEN if an}


# ----------------------------------------------------------------------
# Hilfsfunktionen (wie tests/test_abnahme4_r7.py)
# ----------------------------------------------------------------------
def _funde(text, profil="hoch"):
    return analysiere_text(text, ALLE, [], [], profil=profil)


def _stellen(funde, kategorie=None) -> set:
    return {st["text"] for f in funde if kategorie is None or f["kategorie"] == kategorie
            for st in f["stellen"] if st.get("an", True)}


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


def _zustand(text, wert) -> str:
    """weg (geschwärzt), gemeldet (Verdacht der Selbstkontrolle an der Stelle) oder frei."""
    aus, ph = _ausgabe(text)
    if wert not in aus:
        return "weg"
    if any(wert in t or (len(t) >= 3 and t in wert) for t, _ in _verdacht(aus, platzhalter=ph)):
        return "gemeldet"
    return "frei"


def _kamm(text):
    """Treffer von struktur.kammfeld auf der Textebene."""
    funktion = next(e for e in detektoren.REGISTER if e.name == "struktur.kammfeld").funktion
    dok = seitenmodell.dokument_aus_text(text)
    return {(t.kategorie, dok.text[t.start:t.ende]) for t in funktion(dok, Kontext(ALLE, "hoch"))}


# ----------------------------------------------------------------------
# A5-01, AB5U-01: Ziffern in Jahresform hinter "mit" an einem Schloss – geschwärzt mit Verb der Sicherung oder
# Bedienung; frei nur vor einem gebeugten attributiven Partizip mit Hauptwort ("mit 2021 erneuerter Heizung")
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert", [
    ("Die Tiefgarage ist mit 1984 gesichert.", "1984"),
    ("Der Waffenschrank ist mit 2009 verschlossen.", "2009"),
    ("Das Rolltor ist mit 2012 verriegelt, bitte danach wieder schließen.", "2012"),
    ("Die Haustür lässt sich mit 1990 aufschließen.", "1990"),
    ("Die Garage ist mit 2015 abgesperrt.", "2015"),                       # Abwandlung
])
def test_a5_01_jahresform_hinter_mit_geschwaerzt(text, wert):
    assert _zustand(text, wert) == "weg", _verdacht(_ausgabe(text)[0])


@pytest.mark.parametrize("text, wert", [
    ("Der Kellerraum ist mit 1986 gesperrt.", "1986"),
    ("Das Tor ist mit 1999 eingestellt worden.", "1999"),
])
def test_a5_01_jahresform_mindestens_gemeldet(text, wert):
    assert _zustand(text, wert) in ("weg", "gemeldet")


@pytest.mark.parametrize("text, wert", [
    ("Das Gebäude ist mit 2021 erneuerter Heizung ausgestattet.", "2021"),
    ("Die Halle ist mit 2019 eingebauten Rolltoren ausgestattet.", "2019"),
    ("Das Haus wurde mit 2020 eingebautem Aufzug modernisiert.", "2020"),
])
def test_ab5u_01_jahr_vor_gebeugtem_partizip_frei(text, wert):
    assert _zustand(text, wert) == "frei"


# ----------------------------------------------------------------------
# A5-02: Geräte-Grundwort allein mit Artikel und Personenverb gemeldet; Kompositum und Gerät mit Geräteschaden frei
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, name", [
    ("Der Kocher hat angerufen.", "Kocher"),
    ("Den Unfall verursachte der Bohrer.", "Bohrer"),
    ("Die Regler hat den Unfall gemeldet.", "Regler"),
    ("Der Sender sagte, die Ampel sei rot gewesen.", "Sender"),
    ("Der Melder hat die Schadenanzeige unterschrieben.", "Melder"),
    ("Der Melder rammte das Garagentor.", "Melder"),
])
def test_a5_02_geraete_grundwort_als_name_gemeldet(text, name):
    assert _zustand(text, name) in ("weg", "gemeldet")


@pytest.mark.parametrize("text, wort", [
    ("Der Hochdruckreiniger hat die Fassadendämmung beschädigt.", "Hochdruckreiniger"),
    ("Der Toaster verursachte den Küchenbrand am Morgen.", "Toaster"),
    ("Der Marder beschädigte die Zündkabel im Motorraum.", "Marder"),
])
def test_a5_02_geraet_und_tier_frei(text, wort):
    assert _zustand(text, wort) == "frei", _verdacht(text)


@pytest.mark.parametrize("text, wort", [
    ("Vom Gabelstapler kam der Anruf wegen des Hagelschadens.", "Gabelstapler"),
    ("Vom Steinkocher kam der Anruf wegen des Hagelschadens.", "Steinkocher"),
    ("Beim Steinkocher ist der Stadel abgebrannt.", "Steinkocher"),
])
def test_n7_geraete_kompositum_hinter_vom_gemeldet(text, wort):
    """Selbstprüfung P1 (Nachbesserung 7): ein Geräte-Kompositum hinter "beim"/"vom"/"zum" schwärzt hofnamen nicht
    (Gabelstapler blieb auf 5efcc0c ungeschwärzt), ist aber kein sicherer Gegenbeleg gegen einen Hausnamen – das
    Grundwort ("Kocher") ist auch ein Familienname. Gemeldet wie auf 5efcc0c (dort Hofname-Kandidat)."""
    assert _zustand(text, wort) == "gemeldet", _verdacht(text)


def test_a5_02_geraete_kompositum():
    assert personenkontext.geraete_kompositum("Gabelstapler")
    assert personenkontext.geraete_kompositum("Hochdruckreiniger")
    assert not personenkontext.geraete_kompositum("Kocher")              # das Grundwort allein: auch ein Name


# ----------------------------------------------------------------------
# A5-03: Tätigkeit hinter einem Satzgegenstand, der keine Sache ist
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert", [
    ("Der Verletzte arbeitet als Lagerhilfe.", "Lagerhilfe"),
    ("Die Bevollmächtigte arbeitet als Bürokraft.", "Bürokraft"),
    ("Der Fahrzeugführer arbeitet als Paketbote.", "Paketbote"),
    ("Die Pflegebedürftige arbeitete früher als Putzfrau.", "Putzfrau"),
])
def test_a5_03_taetigkeit_hinter_person(text, wert):
    assert _zustand(text, wert) in ("weg", "gemeldet")


# ----------------------------------------------------------------------
# A5-04: kurzer Wert auch an weiteren Stellen (Ortskontext, hinter "Haus")
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert", [
    ("Geburtsort: Au\nSie wuchs in Au bei Freising auf.", "Au"),
    ("Wohnort: Ay\nDer Unfall geschah in Ay an der Kreuzung.", "Ay"),
    ("Hausnummer: 7\nDas Haus 7 hat einen Wasserschaden.", "7"),
])
def test_a5_04_kurzer_wert_weitergegeben(text, wert):
    aus, _ = _ausgabe(text)
    assert aus.count(wert) == 0 or _zustand(text, wert) in ("weg", "gemeldet"), aus


@pytest.mark.parametrize("text, wert", [
    ("Hausnummer: 8\nDie Halle 8 ist gesperrt.", "Halle 8"),
    ("Hausnummer: 8\nBitte Tor 8 benutzen.", "Tor 8"),
])
def test_a5_04_gegenproben(text, wert):
    aus, _ = _ausgabe(text)
    assert wert in aus, aus


# ----------------------------------------------------------------------
# A5-05, AB5U-04: Allerweltswort hinter Personenwort bzw. mit Artikel und Personenverb gemeldet; Familiennamen mit
# einem Allerweltswort darin bleiben mindestens gemeldet
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, name", [
    ("Nachbar Wasser hat angerufen.", "Wasser"),
    ("Laut Nachbarin Regen war die Tür offen.", "Regen"),
    ("Der Wasser hat den Schaden gemeldet.", "Wasser"),
    ("Der Wagen des Nachbarn Regen stand vor der Garage.", "Regen"),        # Genitiv: kein Satzteil
    ("Mit freundlichen Grüßen\nRegensburger", "Regensburger"),
    ("Viele Grüße\nIhr Wasserbauer", "Wasserbauer"),
    ("Rückfragen bitte an Regenauer (Durchwahl -24).", "Regenauer"),
])
def test_a5_05_allerweltswort_als_name_gemeldet(text, name):
    assert _zustand(text, name) in ("weg", "gemeldet")


@pytest.mark.parametrize("text, wort", [
    ("Er hat dem Nachbarn Wasser abgegraben.", "Wasser"),
    ("Beim Nachbarn Regen gemessen.", "Regen"),
    ("Den Schaden meldete der Versicherungsnehmer.", "Versicherungsnehmer"),
    ("Der Teilnehmer hat angerufen.", "Teilnehmer"),
])
def test_a5_05_gegenproben(text, wort):
    assert _zustand(text, wort) == "frei", _verdacht(text)


@pytest.mark.parametrize("text, name", [
    ("Nachbar Wasser hat angerufen.", "Wasser"),                            # E2E faelle_a5d: auf 0230782 geschwärzt
    ("Laut Nachbarin Regen war die Tür offen.", "Regen"),
    ("Zeugin Regen hat den Unfall gesehen.", "Regen"),                      # Abwandlung
])
def test_a5_05_allerweltswort_im_starken_personenkontext_geschwaerzt(text, name):
    assert _zustand(text, name) == "weg", _stellen(_funde(text))


@pytest.mark.parametrize("text, wort, erwartet", [
    ("Er hat dem Nachbarn Wasser abgegraben.", "Wasser", ("frei",)),        # Begleiter: Satzteil
    ("Kollege Außendienst ruft zurück.", "Außendienst", ("gemeldet",)),     # Abteilung (AB4U-01)
    ("Nachbar Morgen kommt vorbei.", "Morgen", ("gemeldet", "frei")),       # Zeitwort
    ("Laut Nachbar Wasserschaden war alles nass.", "Wasserschaden", ("frei", "gemeldet")),  # Kompositum
    ("Nachbar Sturmschaden hat das Dach abgedeckt.", "Sturmschaden", ("frei", "gemeldet")),  # Kompositum, Verb dahinter
    ("Laut Mieter Leitungswasser war der Keller nass.", "Leitungswasser", ("frei", "gemeldet")),
])
def test_a5_05_starker_kontext_gegenproben(text, wort, erwartet):
    assert _zustand(text, wort) in erwartet, (_stellen(_funde(text)), _verdacht(text))


# Abwandlungen: "Wasser" und "Regen" standen auf 0230782 nicht in der Liste der Allerweltswörter und wurden hinter einem
# Personenwort ohne Begleiter wie ein unbekanntes Wort geschwärzt – auch mitten im Satz, mit Kontaktangabe und in einer
# Aufzählung (auf 5efcc0c und vor dieser Regel frei)
@pytest.mark.parametrize("text, name", [
    ("Rücksprache mit Nachbar Wasser am Montag.", "Wasser"),
    ("Termin mit Kollegin Regen vereinbart.", "Regen"),
    ("Gestern rief Nachbar Regen an.", "Regen"),
    ("Heute kam Kollegin Wasser vorbei.", "Wasser"),
    ("Wie Nachbar Regen berichtete, war das Tor offen.", "Regen"),
    ("Nachbar Wasser, Tel. 0171 2345678", "Wasser"),
    ("Zeugen: Nachbar Wasser und Nachbarin Regen", "Wasser"),
    ("Zeugen: Nachbar Wasser und Nachbarin Regen", "Regen"),
])
def test_a5_05_allerweltswort_mitten_im_satz_geschwaerzt(text, name):
    assert _zustand(text, name) == "weg", _stellen(_funde(text))


@pytest.mark.parametrize("text, wort, erwartet", [
    # hinter "Mieter" (Einzahl wie Mehrzahl) kann es ein Satzteil sein: gemeldet
    ("Die Kosten trägt Mieter Wasser selbst.", "Wasser", ("weg", "gemeldet")),
    ("Für Mieter Strom und Wasser inklusive.", "Strom", ("frei", "gemeldet")),
    # Stockwerk, Kanal, Sparte, Gewerk hinter einem Personenwort: ein Zusatz der Rolle (AB4U-01), nur gemeldet
    ("Mieter Erdgeschoss meldet Feuchtigkeit an der Wand.", "Erdgeschoss", ("frei", "gemeldet")),
    ("Mieterin Erdgeschoss hat den Schaden gemeldet.", "Erdgeschoss", ("frei", "gemeldet")),
    ("Mieter Dachgeschoss kam erst abends nach Hause.", "Dachgeschoss", ("frei", "gemeldet")),
    ("Mieter Souterrain hat Wasser im Keller bemerkt.", "Souterrain", ("frei", "gemeldet")),
    ("Mitarbeiter Hotline hat den Schaden aufgenommen.", "Hotline", ("frei", "gemeldet")),
    ("Kunde Gewerbe will den Vertrag zum Jahreswechsel erweitern.", "Gewerbe", ("frei", "gemeldet")),
    ("Monteur Fernwärme kam am Dienstag.", "Fernwärme", ("frei", "gemeldet")),
    ("Rücksprache mit Kunde Empfang am Montag.", "Empfang", ("frei", "gemeldet")),
    # hinter gebeugten Formen und "als" Name oder Satzteil: gemeldet (P2) – auf 0230782 wurden "Wasser" und "Regen"
    # dort geschwärzt, ein gewöhnliches Wort ("Fotos") blieb frei
    ("Er telefonierte mit Kollegen Wasser.", "Wasser", ("weg", "gemeldet")),
    ("Wir haben Kunden Regen informiert.", "Regen", ("weg", "gemeldet")),
    ("Er stellte sich als Nachbar Wasser vor.", "Wasser", ("weg", "gemeldet")),
    ("Er zeigte Kollegen Fotos.", "Fotos", ("gemeldet",)),
    ("Er gab Kunden Rabatt.", "Rabatt", ("gemeldet",)),
    ("Sie macht als Gutachterin Hausbesuche.", "Hausbesuche", ("gemeldet",)),
    # Genitiv auf "-s" (Besitz) und Feldname: ein Satzteil
    ("Nachbars Garten ist verwildert.", "Garten", ("frei",)),
    ("Mieter Dachgeschoss: kein Schaden", "Dachgeschoss", ("frei", "gemeldet")),
])
def test_a5_05_allerweltswort_mitten_im_satz_gegenproben(text, wort, erwartet):
    assert _zustand(text, wort) in erwartet, (_stellen(_funde(text)), _verdacht(text))


# ----------------------------------------------------------------------
# widerlegt: Keine Regression gegenüber fbd755b – ein Name am Satzanfang hinter einem Personenwort mit dem Zustand einer
# Person dahinter ("wird morgen", "ist seit", "war gestern", "wurde befragt") ist der Name wie mit einem Verb einer Person
# (auf fbd755b geschwärzt, auf 0230782 und 5efcc0c nur gemeldet; E2E faelle_a4b b_zeuge_tremml_wird)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, name", [
    ("Unfallbericht\nZeuge Tremml wird morgen zurückrufen.", "Tremml"),
    ("Kollegin Tremml war gestern krank.", "Tremml"),
    ("Onkel Raffl wurde befragt.", "Raffl"),
    ("Nachbar Pfnürl ist seit Montag im Urlaub.", "Pfnürl"),
    ("Nachbar Regen ist seit Montag im Urlaub.", "Regen"),          # Allerweltswort, wie A5-05
])
def test_fbd_name_mit_zustand_einer_person_geschwaerzt(text, name):
    assert _zustand(text, name) == "weg", _stellen(_funde(text))


@pytest.mark.parametrize("text, wort, erwartet", [
    ("Chef Sekretariat ist heute besetzt.", "Sekretariat", ("frei", "gemeldet")),       # Abteilung (AB4U-01)
    ("Kollege Vertrieb ist heute nicht erreichbar.", "Vertrieb", ("frei", "gemeldet")),
    ("Mitarbeiterin Poststelle ist heute nicht da.", "Poststelle", ("frei", "gemeldet")),
    ("Kunde Gewerbe ist seit 2019 versichert.", "Gewerbe", ("frei", "gemeldet")),
    ("Mieter Wohnung ist seit Montag leer.", "Wohnung", ("frei", "gemeldet")),
    ("Chef Sekretariat ist ab 9 Uhr besetzt.", "Sekretariat", ("frei", "gemeldet")),
])
def test_fbd_name_mit_zustand_gegenproben(text, wort, erwartet):
    assert _zustand(text, wort) in erwartet, (_stellen(_funde(text)), _verdacht(text))


def test_n7_allerweltswort_selbstkontrolle_waechst_linear():
    """Selbstkontrolle personenwort_allerwelt: Begleiter, "laut" und "als" nur im Fenster vor dem Personenwort (Eingriff
    N11: ganzer Text davor)."""
    baustein = "Die Kosten trägt Mieter Wasser selbst und Mieter Strom auch, "
    klein, gross = _zeile(baustein, 8000), _zeile(baustein, 64000)
    assert personenkontext.personenwort_allerwelt(klein, wissen)
    wachstum, _, zeit = _wachstum(lambda: personenkontext.personenwort_allerwelt(klein, wissen),
                                  lambda: personenkontext.personenwort_allerwelt(gross, wissen), 8, 2.0)
    assert wachstum < 2.0, f"personenwort_allerwelt wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


# ----------------------------------------------------------------------
# A5-06: Code und Möbelstück – ein Möbel mit Code ist ein Schloss
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert", [
    ("Code Badschrank: 8815", "8815"),
    ("Küchenschrank (Code 2207)", "2207"),
    ("Der Wandschrank im Flur hat den Code 6142.", "6142"),
    ("Code Waffenschrank: 4471", "4471"),
])
def test_a5_06_moebel_mit_code_geschwaerzt(text, wert):
    assert _zustand(text, wert) == "weg"


@pytest.mark.parametrize("text, wert", [
    ("Der Kleiderschrank aus dem Katalog hat den Code 4471.", "4471"),
    ("Der Badschrank (Modell Lina) hat den Code 2207.", "2207"),
    ("Laut Lieferschein hat der Badschrank den Code 2207.", "2207"),
    ("Laut Rechnung des Möbelhauses trägt der Kleiderschrank den Code 66130.", "66130"),
])
def test_n7_moebel_mit_produkt_gemeldet(text, wert):
    """Selbstprüfung P1 (Nachbesserung 7): ein Möbel mit Kauf oder Produkt im Satz nimmt den Code nur vom Schwärzen aus
    (AB4U-05) – Produkt- oder Schlosscode, gemeldet (auf 0230782 geschwärzt, auf 5efcc0c bei "Katalog" still)."""
    assert _zustand(text, wert) == "gemeldet", _verdacht(text)      # Grund bei "Rechnung …": test_ab4u_05_06


# ----------------------------------------------------------------------
# A5-07, AB5U-03, A5-08: Feldnamen in Kammfeldern der Textebene
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert", [
    ("Angaben zur Person\nGeburtsdatum (Fahrer)\t\tTag 1 9\t\tMonat 0 1\t\tJahr 1 9 8 0", "1 9 8 0"),
    ("Angaben zur Person\nGeburtsdatum (Fahrer)\t\tTag 1 9\t\tMonat 0 1\t\tJahr 1 9 8 0", "0 1"),
    ("Angaben zur Person\nGeburtsdatum\t\tTag 0 6\t\tMon. 0 9\t\tJahr 1 9 6 8", "0 9"),
    ("Angaben zur Person\nGeboren am\t\tTag\t\t1 3\t\tMon.\t\t0 2\t\tJahr\t\t1 9 8 1", "0 2"),
    ("Straße\t\tB I R K E N W E G\t\tNr.\t\t6\t\t4", "6\t\t4"),
    ("Name\t\tR\t\tE\t\tVorname\t\tA N N A", "R\t\tE"),
    ("Initialen\t\tK H", "K H"),
    ("Geburtsort\t\tA U", "A U"),
])
def test_a5_08_kammfeld_textebene(text, wert):
    assert any(wert in t for _, t in _kamm(text)), _kamm(text)


@pytest.mark.parametrize("text", [
    "Pos.\t\tNr.\t\t1\t\tBezeichnung\t\tMenge",                        # Positionsnummer ohne Straße
    "Etage\t\t1\t\t2\nZimmer\t\t3\t\t4",
    "Anzahl Kinder\t\t2",
    "Seite\t\t1",
])
def test_a5_08_kammfeld_gegenproben(text):
    assert not _kamm(text), _kamm(text)


def test_a5_08_teil_feldname_mon():
    from anonymisierer import kammraster
    assert kammraster.teil_etikett("Mon.")
    assert not kammraster.teil_etikett("Montag")


# ----------------------------------------------------------------------
# A5-09, A5-10, A5-11: Zugangscode-Formen
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert", [
    ("Die Haustür hat den Code KB475.", "KB475"),
    ("Code Garagentor B4471", "B4471"),
    ("Der Tresor hat den Code XK42.", "XK42"),
    ("Zum Abschalten des Feueralarms den Code 6619 eingeben.", "6619"),
    ("Brandalarm-Code 2297", "2297"),
    ("PIN für Wohnungstür 7100", "7100"),
    ("Lagerhallecode: 9444", "9444"),
    ("Der Vermieter meldete uns den Code der Haustür: 2827", "2827"),
    ("Laut Anzeige im Display gilt für die Garage der Code 9930.", "9930"),
    ("Schadenort Dachboden, Code 7192", "7192"),
    ("Code für das Kundenportal (Typklasse 17): 0628", "0628"),
])
def test_a5_09_10_11_zugangscode_geschwaerzt_oder_gemeldet(text, wert):
    assert _zustand(text, wert) in ("weg", "gemeldet")


def test_a5_10_alarmcode_mehrdeutig_gemeldet():
    assert kennungsformen.alarm_code_mehrdeutig("Feueralarmcode 3401") != []
    assert _zustand("Feueralarmcode 3401", "3401") in ("weg", "gemeldet")


@pytest.mark.parametrize("text, wert", [
    ("Garagentor\nCode E-04 blinkt, Elektriker kommt am Montag.", "E-04"),
    ("Zugang Lagerhalle: 7-17 Uhr", "7-17"),                               # AB5U-05
    ("Zugang Haupteingang: 24/7 über die Pforte.", "24/7"),
])
def test_a5_09_ab5u_05_gegenproben_frei(text, wert):
    assert _zustand(text, wert) == "frei", _verdacht(text)


@pytest.mark.parametrize("text, wert", [
    ("Die Alarmanlage zeigte Code 4021 an, danach bitte die Anlage scharf schalten.", "4021"),
    ("Der Code der Stadthalle für den Saalplan lautet 2019-A.", "2019-A"),
    ("Lager (Code 4410 laut Kostenstellenplan) und Werkstatt (Code 4420)", "4410"),
    ("Der Code für die Anlage lautet 2207 laut Wartungsvertrag.", "2207"),
])
def test_ab5u_06_08_hoechstens_gemeldet(text, wert):
    """Über-Schwärzung der Abnahme: nicht mehr entfernt; mehrdeutig (Anzeige- oder Bediencode) gemeldet (P2)."""
    assert _zustand(text, wert) in ("frei", "gemeldet")


@pytest.mark.parametrize("text, wert", [
    ("Die Alarmanlage zeigte Code 4021 an, bitte den Code am Bedienteil eingeben.", "4021"),
    ("Das Tor meldete Code 3017, dann ihn eingeben.", "3017"),
    ("Am Display der Garage den Code 2240 eingeben.", "2240"),
])
def test_ab5u_06_gegenprobe_satzteil_nimmt_code_auf(text, wert):
    """P1-Gegenprobe zu AB5U-06: ein Verb der Nutzung in einem anderen Satzteil zählt, wenn dieser den Code wieder
    aufnimmt ("den Code", "ihn") – geschwärzt wie auf 5efcc0c."""
    assert _zustand(text, wert) == "weg", _verdacht(_ausgabe(text)[0])


def test_ab4u_05_betrag_hinter_gebaeude_kein_zugangscode():
    """AB4U-05 (Rest aus Abnahme 5): ein Betrag hinter einem Gebäude als Feldname ist kein Zugangscode – auch nicht in
    der zeilenweisen Prüfung, die Feldname und Wert als zwei Zeilen liest ("Wohnhaus:" ⏎ "450.000")."""
    text = "Versicherungssummen Nebengebäude:\nWohnhaus:\t\t450.000\t\tEUR\nGartenhaus:\t\t12.000\t\tEUR"
    assert not [v for v in _verdacht(text) if "Zugangscode" in v[1]], _verdacht(text)
    assert kennungsformen.schloss_feld_folgezeile("Wohnhaus:", "450.000") == []
    # Gegenprobe: Ziffern ohne Betragsgestalt unter einem Schloss bleiben gemeldet
    assert kennungsformen.schloss_feld_folgezeile("Tor zur Tiefgarage:", "4455") == [(0, 4)]
    assert _zustand("Wohnhaus:\n4471", "4471") == "gemeldet"


# ----------------------------------------------------------------------
# A5-12, AB5U-07: Beruf – Ehrenamt gemeldet, Rollen und Tarifsätze höchstens gemeldet
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert", [
    ("Seit 2018 ehrenamtlich als Erzieherin in der Kita tätig.", "Erzieherin"),
    ("Ehrenamtlich tätig als Schöffin am Amtsgericht.", "Schöffin"),
    ("Sie war früher Lehrerin an der Grundschule.", "Lehrerin"),
    ("Er ist seit 2015 Busfahrer bei den Stadtwerken.", "Busfahrer"),
])
def test_a5_12_beruf_geschwaerzt_oder_gemeldet(text, wert):
    assert _zustand(text, wert) in ("weg", "gemeldet")


def test_a5_12_beruf_hinter_geschwaerztem_satzgegenstand_pdf(tmp_path):
    """Ende-zu-Ende-Fall a5_ab406_schoeffin (Text und drei Scans still auf 5efcc0c und 0230782): unter „Angaben zur
    Person“ wird das erste Wort der Zeile als Name geschwärzt („Ehrenamtlich“), in der Ausgabe steht der Text des
    Platzhalters am Ende der Textebene, sein Rechteck aber vor „tätig als Schöffin …“ – der Beruf wird geschwärzt oder
    gemeldet, nie still."""
    import pymupdf as fitz
    from anonymisierer.analyse import analysiere_pdf
    from anonymisierer.schwaerzung import schwaerze_pdf
    doc = fitz.open()
    s = doc.new_page(width=595, height=842)
    s.insert_text((60, 80), "Angaben zur Person", fontsize=11, fontname="helv")
    s.insert_text((60, 98.15), "Ehrenamtlich tätig als Schöffin am Amtsgericht.", fontsize=11, fontname="helv")
    pfad = tmp_path / "schoeffin.pdf"
    doc.save(pfad)
    doc.close()
    erg = analysiere_pdf(pfad, ALLE, [], [], profil="hoch")
    aus = schwaerze_pdf(pfad, erg["funde"], ziel_ordner=tmp_path / "aus")
    with fitz.open(aus["ausgabe"]) as d:
        text = "\n".join(p.get_text() for p in d)
    verdacht = [(v.text, v.grund) for v in aus.get("verdacht") or []]
    assert "Schöffin" not in text or any("Schöffin" in t for t, _ in verdacht), (text, verdacht)


def _ausgabe_pdf_zeilen(tmp_path, zeilen, ocr_platzhalter=None):
    """Ausgabe wie die Schwärzung sie schreibt (wie tests/test_abnahme4_r7.py::_ausgabe_pdf): zeilen = [(vorn,
    geschwärzt, hinten)]; ist geschwärzt wahr, steht zwischen vorn und hinten ein graues Rechteck mit dem Platzhalter
    „[PERSON A]“ als letztem Text der Seite bzw. auf einer Scan-Seite mit dem Platzhalter als verlesenem OCR-Wort
    `ocr_platzhalter`. Rückgabe: (Pfad, Zusatz für restrisiko_pruefen)."""
    import pymupdf as fitz
    from anonymisierer import restrisiko
    doc = fitz.open()
    s = doc.new_page(width=595, height=842)
    rechtecke, y = [], 80.0
    for vorn, geschwaerzt, hinten in zeilen:
        x = 60.0
        if vorn:
            s.insert_text((x, y), vorn, fontsize=11, fontname="helv")
            x += fitz.get_text_length(vorn + " ", fontname="helv", fontsize=11)
        if geschwaerzt:
            r = fitz.Rect(x, y - 9.5, x + 70, y + 3)
            rechtecke.append(r)
            x = r.x1 + 3
        if hinten:
            s.insert_text((x, y), hinten, fontsize=11, fontname="helv")
        y += 18.15
    zusatz = {}
    if ocr_platzhalter is not None:
        woerter = [tuple(w[:5]) for w in s.get_text("words")]
        woerter += [(r.x0 + 2, r.y0 + 1, r.x1 - 2, r.y1 - 1, ocr_platzhalter) for r in rechtecke]
        pix = s.get_pixmap(dpi=200, colorspace=fitz.csGRAY)
        scan = fitz.open()
        seite = scan.new_page(width=595, height=842)
        seite.insert_image(seite.rect, stream=pix.tobytes("png"))
        doc.close()
        doc, s = scan, seite
        zusatz = {"ocr_modus": {0: "seite"}, "ocr_woerter": {0: woerter}}
    for r in rechtecke:
        s.draw_rect(r, color=None, fill=restrisiko.FUELLFARBE)
        if ocr_platzhalter is None:
            s.insert_text((r.x0 + 2, r.y1 - 3), "[PERSON A]", fontsize=8, fontname="helv")
    pfad = tmp_path / "ausgabe.pdf"
    doc.save(pfad)
    doc.close()
    return pfad, zusatz


@pytest.mark.parametrize("ocr_platzhalter", [None, "IPERSONAI", "|PERSON A|"])
@pytest.mark.parametrize("vorn, hinten, beruf", [
    ("", "tätig als Schöffin am Amtsgericht.", "Schöffin"),
    ("Seit 2019 ist", "als Erzieherin in der Kita tätig.", "Erzieherin"),           # Abwandlung: mitten im Satz
    ("Als Schöffin am Amtsgericht arbeitet", ".", "Schöffin"),                      # am Satzende vor dem Punkt
])
def test_a5_12_beruf_neben_personen_platzhalter_der_ausgabe(tmp_path, ocr_platzhalter, vorn, hinten, beruf):
    from anonymisierer import restrisiko
    pfad, zusatz = _ausgabe_pdf_zeilen(tmp_path, [("Angaben zur Person", False, ""), (vorn, True, hinten)],
                                       ocr_platzhalter)
    v = [(x.text, x.grund) for x in restrisiko.restrisiko_pruefen(pfad, platzhalter=["[PERSON A]"], **zusatz)]
    assert any(t == beruf and "Person" in g for t, g in v), v


@pytest.mark.parametrize("ocr_platzhalter", [None, "IPERSONAI"])
def test_a5_12_platzhalter_in_anderem_satz_gegenprobe(tmp_path, ocr_platzhalter):
    """Gegenprobe: der Personen-Platzhalter steht in einem anderen Satz (Zeile darüber) – „Die Stelle als Schöffin am
    Amtsgericht ist frei.“ spricht von keiner Person und bleibt ohne Verdacht."""
    from anonymisierer import restrisiko
    pfad, zusatz = _ausgabe_pdf_zeilen(tmp_path, [("", True, "hat angerufen."),
                                                  ("Die Stelle als Schöffin am Amtsgericht ist frei.", False, "")],
                                       ocr_platzhalter)
    v = [(x.text, x.grund) for x in restrisiko.restrisiko_pruefen(pfad, platzhalter=["[PERSON A]"], **zusatz)]
    assert not any(t == "Schöffin" for t, _ in v), v


@pytest.mark.parametrize("text, wert", [
    ("Er ist Trainer der F-Jugend beim TSV Inzell.", "Trainer"),
    ("Sie ist Betreuerin ihrer Mutter in Rosenheim.", "Betreuerin"),
    ("Für den Beruf des Dachdeckers gilt die Gefahrengruppe B.", "Dachdeckers"),
])
def test_ab5u_07_rolle_hoechstens_gemeldet(text, wert):
    assert _zustand(text, wert) in ("frei", "gemeldet")


# ----------------------------------------------------------------------
# A5-13: Familienname mit Artikel bzw. hinter einem (gebeugten) Personenwort
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, name", [
    ("Laut Polizei hat der Schwarzl den Unfall gemeldet.", "Schwarzl"),
    ("Laut Polizei hat der Gsödl den Unfall gemeldet.", "Gsödl"),
    ("Kollege Pfarrer hat angerufen.", "Pfarrer"),
    ("Nachbarin Pfarrer hat angerufen.", "Pfarrer"),
    ("Rücksprache mit Mieter Käufer am Montag.", "Käufer"),
    ("Kunde Halter wurde befragt.", "Halter"),
    ("Der Nachbar beschuldigte die Zeitlhofer.", "Zeitlhofer"),
    ("Die Polizei befragte den Zeitlhofer am Unfallort.", "Zeitlhofer"),
    ("Der Fahrer übersah die Moierl beim Abbiegen.", "Moierl"),
    ("Der Schlüssel liegt bei dem Mandanten Kreuzl.", "Kreuzl"),
    ("Die Kaution des Onkels Tremml ist offen.", "Tremml"),
    ("Der Wagen des Vermieters Leser stand vor der Garage.", "Leser"),
    ("Den Schaden meldete der Fink.", "Fink"),
    ("Am Steuer saß der Hase.", "Hase"),
    ("Der Wastl hat angerufen.", "Wastl"),
    ("Der Bock hat den Zaun beschädigt.", "Bock"),
    ("Der Tremml fuhr zu schnell.", "Tremml"),
    ("Laut Zimmerer Hinterseer ist das Dach dicht.", "Hinterseer"),
    ("Laut Nachbar Händler war das Fenster offen.", "Händler"),
])
def test_a5_13_name_mit_artikel_oder_personenwort_gemeldet(text, name):
    assert _zustand(text, name) in ("weg", "gemeldet")


@pytest.mark.parametrize("text, wort", [
    ("Der Hund beschädigte die Couch.", "Hund"),
    ("Die Katze hat den Vorhang beschädigt.", "Katze"),
    ("Der Hagel hat den Schaden verursacht.", "Hagel"),
    ("Den Zaun hat der Sturm beschädigt.", "Sturm"),
    ("Den Zaun rammte der Wagen.", "Wagen"),
    ("Der Wagen fuhr zu schnell.", "Wagen"),
    ("Er übersah den Traktor.", "Traktor"),
    ("Am Steuer saß der Winter.", "Winter"),
    ("Sohn Auszubildender, Tochter Studentin", "Studentin"),
    ("Die Fräse beschädigte das Erdkabel der Telekom.", "Fräse"),            # AB5U-09
    ("Beim Aushub für die Bodenplatte beschädigte der Bagger eine Wasserleitung.", "Bodenplatte"),
])
def test_a5_13_gegenproben(text, wort):
    assert _zustand(text, wort) == "frei", _verdacht(text)


@pytest.mark.parametrize("text, name", [
    ("Die Kaution des Mandanten Wolf ist offen.", "Wolf"),
    ("Die Kaution des Mandanten Fuchs ist offen.", "Fuchs"),
    ("Der Wagen der Mieterin Wolf stand vor der Garage.", "Wolf"),
])
def test_a5_13_genitiv_mehrdeutig_bleibt_geschwaerzt(text, name):
    """Differenztest (id 19595): Die gebeugten Personenwörter erweitern die Ausnahme "Familienname, der zugleich ein
    gewöhnliches Wort ist, hinter einem Begleiter: nur melden" (AB3-04) nicht auf den Genitiv – dort ist das Wort der
    Name und bleibt geschwärzt wie auf 5efcc0c, 0230782, 818990e und fbd755b."""
    assert _zustand(text, name) == "weg", _stellen(_funde(text))


def test_a5_13_satzteil_begleiter_bleibt_gemeldet():
    """Gegenprobe: hinter einem Begleiter im Dativ kann das Wort ein Satzteil sein (Tausch seit 818990e, AB3-04)."""
    assert _zustand("Beim Nachbarn Fuchs brannte Licht.", "Fuchs") == "gemeldet"
    assert _zustand("Die Schlüssel liegen beim Nachbarn Winter.", "Winter") == "gemeldet"


def test_a5_13_gebeugte_personenwoerter():
    for wort in ("Onkels", "Mandanten", "Vermieters", "Mieters", "Patienten", "Neffen"):
        assert personenkontext.ist_personenwort(wort), wort


# ----------------------------------------------------------------------
# A5-14: bekannter Familienname auf -er hinter beim/vom/zum – Besuch, Entfernung, Weg, Besitz
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, name", [
    ("Wir waren gestern beim Gruber zum Essen.", "Gruber"),
    ("Zum Wimmer sind es nur zwei Kilometer.", "Wimmer"),
    ("Zum Gruber fahren wir am Montag.", "Gruber"),
    ("Der Traktor vom Wimmer stand quer auf der Fahrbahn.", "Wimmer"),
    ("Die Kühe vom Gruber standen auf der Straße.", "Gruber"),
])
def test_a5_14_bekannter_name_geschwaerzt(text, name):
    assert _zustand(text, name) == "weg"


@pytest.mark.parametrize("text, name", [
    ("Zum Grebl fahren wir am Montag.", "Grebl"),
    ("Die Kühe vom Gsödl standen auf der Straße.", "Gsödl"),
    ("Das Auto vom Moierl wurde beschädigt.", "Moierl"),
    ("Zum Tremml sind es zwei Kilometer.", "Tremml"),
])
def test_a5_14_unbekannter_name_gemeldet(text, name):
    assert _zustand(text, name) in ("weg", "gemeldet")


@pytest.mark.parametrize("text, wort", [
    ("Anbei das Foto vom Kratzer.", "Kratzer"),
    ("Er fuhr zum Discounter nach Rosenheim.", "Discounter"),
])
def test_a5_14_gegenproben_nicht_geschwaerzt(text, wort):
    assert not _beruehrt(text, wort)


# ----------------------------------------------------------------------
# AB5U-02: Hofname-Kandidaten mit sicheren Gegenbelegen frei
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wort", [
    ("Zum Glück griff das Feuer nicht über.", "Glück"),
    ("Beim Grillen fing die Markise Feuer.", "Grillen"),
    ("Beim Rangieren touchierte er den Pfosten.", "Rangieren"),
    ("Beim Einkaufen wurde das Rad gestohlen.", "Einkaufen"),
])
def test_ab5u_02_gegenbeleg_frei(text, wort):
    assert _zustand(text, wort) == "frei", _verdacht(text)


def test_ab5u_02_ausrufezeichen_kein_gegenbeleg():
    """Nachbesserung 8 (Abnahme 6 A6-03, AB6U-01): ein Ausrufe- oder Fragezeichen hinter dem Wort ist kein Gegenbeleg –
    "Vom Kalt! kam der Anruf …" wird wie auf 5efcc0c gemeldet (vorher hier frei verlangt; Zielkonflikt nach P1 zum
    Melden entschieden)."""
    assert _zustand("Vom Kalt! kam der Anruf wegen des Hagelschadens.", "Kalt") == "gemeldet"


@pytest.mark.parametrize("text, name", [
    ("Beim Kohlhändler ist der Stadel abgebrannt.", "Kohlhändler"),
    ("Gestern brannte es beim Holzhändler in Waging.", "Holzhändler"),
    ("Vom Kaltl kam der Anruf wegen des Hagelschadens.", "Kaltl"),
])
def test_ab5u_02_nie_still(text, name):
    assert _zustand(text, name) in ("weg", "gemeldet")


@pytest.mark.parametrize("text, name", [
    ("Beim Kaltenbrunnen ist der Stadel abgebrannt.", "Kaltenbrunnen"),
    ("Vom Mitterhofen kam der Anruf wegen des Hagelschadens.", "Mitterhofen"),
    ("Beim Moosgraben ist der Stadel abgebrannt.", "Moosgraben"),
    ("Vom Achleiten kam der Anruf wegen des Hagelschadens.", "Achleiten"),
    ("Beim Untermoosen ist der Stadel abgebrannt.", "Untermoosen"),
    ("Vom Hinterhuben kam der Anruf wegen des Hagelschadens.", "Hinterhuben"),
    ("Beim Holzhausen ist der Stadel abgebrannt.", "Holzhausen"),
])
def test_n7_flurname_kein_gegenbeleg(text, name):
    """Selbstprüfung P1 (Nachbesserung 7): ein Flur-, Orts- oder Hofname nach seinem Grundwort ("-brunnen", "-hofen",
    "-graben", "-leiten", "-moosen", "-huben", "-hausen") ist kein substantiviertes Verb und kein gewöhnliches
    Kompositum – gemeldet wie auf 5efcc0c (der Gegenbeleg "-en" ließ ihn frei)."""
    assert _zustand(text, name) in ("weg", "gemeldet"), _verdacht(text)


@pytest.mark.parametrize("text, wort", [
    ("Beim Graben stieß der Bagger auf ein Kabel.", "Graben"),   # Grundwort allein: ein substantiviertes Verb
    ("Beim Grillen fing die Markise Feuer.", "Grillen"),
    ("Beim Steinschlag auf der A8 brach die Scheibe.", "Steinschlag"),
])
def test_n7_flurname_gegenproben_frei(text, wort):
    assert _zustand(text, wort) == "frei", _verdacht(text)


# ----------------------------------------------------------------------
# A5-15: Postleitzahl links neben einem geschwärzten Ort
# ----------------------------------------------------------------------
def test_a5_15_plz_neben_ort_platzhalter_gemeldet():
    v = _verdacht("Wohnort: 72070 [PLZ ORT]", platzhalter=["[PLZ ORT]"])
    assert any("72070" in t for t, _ in v), v


def test_a5_15_gegenprobe_hausnummer_rechts():
    v = _verdacht("Anschrift: [ADRESSE] 12", platzhalter=["[ADRESSE]"])
    assert not any("Postleitzahl" in g for _, g in v), v


def _scan_anschrift(tmp_path, plz_wort=None, kritzel=False, rechts=False, etikett="PLZ, Ort:", platzhalter="[ORT]"):
    """Ausgabe einer Scan-Seite „PLZ, Ort: … [ORT]“ wie die Schwärzung sie schreibt: graues Rechteck mit dem
    Platzhalter „[ORT]“ auf der Textebene, davor (rechts=True: dahinter) die Postleitzahl als OCR-Wort `plz_wort` – so,
    wie die Kontroll-OCR sie liest – bzw. als Handschrift, die die OCR nicht liest (kritzel). Kammfeld-Korpus g7717 der
    Abnahme 5, Dokument 070: handschriftlich „72070“ auf einem Fax, gelesen als „F2O7O“. Rückgabe: (Pfad, Zusatz für
    restrisiko_pruefen)."""
    import pymupdf as fitz
    from anonymisierer import restrisiko
    vorlage = fitz.open()
    s = vorlage.new_page()
    s.insert_text((60, 100), "Antrag auf Leistungen aus der Hausratversicherung", fontsize=12, fontname="helv")
    if etikett:
        s.insert_text((60, 140), etikett, fontsize=12, fontname="helv")
    woerter = [tuple(w[:5]) for w in s.get_text("words")]
    box = fitz.Rect(120, 128, 180, 143) if rechts else fitz.Rect(190, 128, 250, 143)
    wort = fitz.Rect(184, 129, 220, 142) if rechts else fitz.Rect(150, 129, 186, 142)
    if kritzel:
        form = s.new_shape()
        for k in range(4):
            form.draw_bezier((wort.x0 + 2 + 8 * k, 138), (wort.x0 + 4 + 8 * k, 126), (wort.x0 + 7 + 8 * k, 146),
                             (wort.x0 + 9 + 8 * k, 132))
        form.finish(color=(0.1, 0.1, 0.4), width=1.3)
        form.commit()
    if plz_wort:
        woerter.append((wort.x0, wort.y0, wort.x1, wort.y1, plz_wort))
    pix = s.get_pixmap(dpi=150, colorspace=fitz.csGRAY)
    doc = fitz.open()
    p = doc.new_page(width=s.rect.width, height=s.rect.height)
    p.insert_image(p.rect, stream=pix.tobytes("png"))
    p.draw_rect(box, color=None, fill=restrisiko.FUELLFARBE)
    p.insert_text((box.x0 + 4, 139), platzhalter, fontsize=8, fontname="helv")
    vorlage.close()
    pfad = tmp_path / "anschrift.pdf"
    doc.save(pfad)
    doc.close()
    return pfad, {"ocr_modus": {0: "seite"}, "ocr_woerter": {0: woerter}}


@pytest.mark.parametrize("plz_wort", ["72070", "F2O7O", "7Z07O"])
@pytest.mark.parametrize("etikett", ["PLZ, Ort:", ""])
def test_a5_15_plz_neben_ort_auf_scan_gemeldet(tmp_path, plz_wort, etikett):
    """Auf einem Scan steht das OCR-Wort im Seitentext hinter dem Text der Platzhalter – links oder rechts zählt nach
    der Lage auf der Seite; auch eine verlesene Postleitzahl (Länge einer Postleitzahl, mindestens zwei Ziffern) wird
    gemeldet, ohne Feldnamen davor (wie im Fax 070) mit dem Grund der Postleitzahl."""
    from anonymisierer import restrisiko
    pfad, zusatz = _scan_anschrift(tmp_path, plz_wort, etikett=etikett)
    v = [(x.text, x.grund) for x in restrisiko.restrisiko_pruefen(pfad, platzhalter=["[ORT]"], **zusatz)]
    assert any(t == plz_wort for t, _ in v), v
    if not etikett and not plz_wort.isdigit():
        assert (plz_wort, "Postleitzahl neben einem geschwärzten Ort") in v, v


@pytest.mark.parametrize("plz_wort, rechts", [
    ("Lehrerin", False),                 # ein Wort ohne Ziffern ist keine Postleitzahl
    ("F2O7O", True),                     # rechts hinter dem Ort steht keine Postleitzahl
    ("2O", False),                       # zu kurz für eine Postleitzahl
])
def test_a5_15_plz_neben_ort_auf_scan_gegenproben(tmp_path, plz_wort, rechts):
    from anonymisierer import restrisiko
    pfad, zusatz = _scan_anschrift(tmp_path, plz_wort, rechts=rechts)
    v = [(x.text, x.grund) for x in restrisiko.restrisiko_pruefen(pfad, platzhalter=["[ORT]"], **zusatz)]
    assert not any(g == "Postleitzahl neben einem geschwärzten Ort" for _, g in v), v


@pytest.mark.parametrize("platzhalter, rechts", [
    ("[ORT]", False),                    # Postleitzahl vor dem Ort
    ("[PLZ ORT]", False),
    ("[STRASSE]", True),                 # Hausnummer hinter der Straße
])
def test_a5_15_handschrift_ohne_lesung_neben_anschrift_gemeldet(tmp_path, platzhalter, rechts):
    """Liest die OCR die Handschrift neben der geschwärzten Anschrift gar nicht, meldet die Tintenprüfung die Stelle
    („Schrift neben einer geschwärzten Anschrift …“); ohne Handschrift bleibt die Seite ohne diesen Verdacht."""
    import pymupdf as fitz
    from anonymisierer import restrisiko
    pfad, zusatz = _scan_anschrift(tmp_path, kritzel=True, rechts=rechts, platzhalter=platzhalter)
    v = [x for x in restrisiko.restrisiko_pruefen(pfad, platzhalter=[platzhalter], **zusatz)
         if x.grund == restrisiko.GRUND_ANSCHRIFTTINTE]
    stelle = fitz.Rect(184, 126, 220, 146) if rechts else fitz.Rect(150, 126, 186, 146)
    assert v and any(fitz.Rect(r).intersects(stelle) for r in v[0].rechtecke), v
    pfad, zusatz = _scan_anschrift(tmp_path, rechts=rechts, platzhalter=platzhalter)
    v = [x for x in restrisiko.restrisiko_pruefen(pfad, platzhalter=[platzhalter], **zusatz)
         if x.grund == restrisiko.GRUND_ANSCHRIFTTINTE]
    assert not v, v


# ----------------------------------------------------------------------
# AB5U-12: Amtsbezeichnung hinter einer Anrede – höchstens gemeldet; der Name hinter einem Personenwort allein
# ----------------------------------------------------------------------
def test_ab5u_12_kollege_nicht_im_namen():
    assert not _beruehrt("Wie Herr Kollege Maier sagte, ist der Schaden gemeldet.", "Kollege")
    assert _zustand("Wie Herr Kollege Maier sagte, ist der Schaden gemeldet.", "Maier") == "weg"


@pytest.mark.parametrize("text, name", [
    ("Wir haben Frau Pfarrer informiert.", "Pfarrer"),
    ("Der Brief an Herrn Pfarrer kam zurück.", "Pfarrer"),
])
def test_ab5u_12_beruf_hinter_anrede_bleibt_geschwaerzt(text, name):
    """Gegenprobe (P1): eine Amts- oder Berufsbezeichnung allein hinter einer Anrede kann ein Familienname sein – sie
    bleibt geschwärzt wie auf allen Vorständen (die Über-Schwärzung „Herr Bürgermeister“ bleibt vorbestehend)."""
    assert _zustand(text, name) == "weg"


# ----------------------------------------------------------------------
# AB5U-13: auf Scans ist ein Satz hinter einem Personenwort kein Rohwert eines Formularfelds ("Mitarbeiter Vertrieb
# meldet sich bis Freitag.") – wie auf der Textebene geht der Satzgegenstand über die Personenwort-Regeln
# ----------------------------------------------------------------------
def _ocr_dok(zeilen):
    """OCR-Seite wie in tests/test_detektoren_formen.py: Zellen durch "\t\t", Wörter durch " "."""
    import fitz
    doc = fitz.open()
    seite = doc.new_page(width=595, height=842)
    woerter, y = [], 80.0
    for zi, zeile in enumerate(zeilen):
        x, wi = 50.0, 0
        for ci, zelle in enumerate(zeile.split("\t\t")):
            if ci:
                x += 60
            for w in zelle.split(" "):
                if not w:
                    x += 5
                    continue
                breite = 6.0 * len(w)
                woerter.append((x, y, x + breite, y + 12, w, 0, zi, wi))
                wi += 1
                x += breite + 4
        y += 18
    s = seitenmodell.seite_aufbauen(seite, 0, ocr_woerter=woerter, ocr_quelle="ocr")
    doc.close()
    return seitenmodell.Dokument(None, [s])


def _ocr_stellen(zeile) -> set:
    from anonymisierer import analyse
    dok = _ocr_dok([zeile])
    funde = analyse._analysiere_dokument(dok, ALLE, [], [], profil="hoch")
    return {dok.text[st["start"]:st["ende"]] for f in funde for st in f["stellen"]
            if st.get("an", True) and "start" in st}


@pytest.mark.parametrize("zeile, rest", [
    ("Mitarbeiter Vertrieb meldet sich bis Freitag.", "meldet sich bis Freitag"),
    ("Nachbar Gegenüber sah den Rauch zuerst.", "sah den Rauch zuerst"),
    ("Mitarbeiter Vertrieb Süd meldet sich.", "meldet sich"),                # Abwandlung: zwei Wörter vor dem Verb
    ("Nachbarin Gegenüber ist seit Montag verreist.", "seit Montag verreist"),
])
def test_ab5u_13_satz_hinter_personenwort_kein_rohwert(zeile, rest):
    gefunden = _ocr_stellen(zeile)
    assert not any(rest in s or "Vertrieb" in s or "Gegenüber" in s for s in gefunden), gefunden


@pytest.mark.parametrize("zeile, name", [
    ("Nachbar Xyzzl meldet sich bis Freitag.", "Xyzzl"),                    # unbekannter Name: wie Textebene weg
    ("Mitarbeiter Gsödl Anton meldet sich.", "Gsödl"),
    ("Mitarbeiterin Zach ist erreichbar.", "Zach"),
    ("Kontoinhaber Zeidler Thomas", "Zeidler"),                              # Feldwert ohne Verb: bleibt Rohwert/Wert
    ("Name Mxrkovic Jlena", "Mxrkovic"),
    ("Mitarbeiter: Vertrieb meldet sich bis Freitag.", "Vertrieb"),         # Feld mit Doppelpunkt: weiter geschwärzt
])
def test_ab5u_13_gegenproben_name_bleibt_geschwaerzt(zeile, name):
    """P1: frei wird nur der Satz hinter einem Personenwort im Fließtext; ein Name darin bleibt über die Personenwort-
    Regeln geschwärzt, ein Feld mit Doppelpunkt oder ohne Verb bleibt ein Feld."""
    assert any(name in s for s in _ocr_stellen(zeile)), _ocr_stellen(zeile)


def test_ab5u_13_abteilung_gemeldet():
    for text, wort in (("Mitarbeiter Vertrieb meldet sich bis Freitag.", "Vertrieb"),
                       ("Nachbar Gegenüber sah den Rauch zuerst.", "Gegenüber")):
        assert _zustand(text, wort) == "gemeldet", _verdacht(text)


# ----------------------------------------------------------------------
# AB5U-10: Laufzeit – hofnamen und hofnamen_kandidaten linear auf einer langen Zeile, Jahr unter Spaltenkopf mit
# Zeilengrenze; neue Schleifen dieser Nachbesserung (Wachstumstests erkennen die eingebauten Regressionen R6, R7)
# ----------------------------------------------------------------------
def _wachstum(klein, gross, faktor, schranke):
    import zeitmessung
    klein()
    return zeitmessung.wachstum_messen(klein, gross, faktor, wiederholungen=1, schranke=schranke)


def _zeile(baustein, n):
    return baustein * max(1, n // len(baustein))


def test_ab5u_10_hofnamen_lange_zeile_waechst_linear():
    """R6 der Abnahme (Zeilenkontext ohne Zwischenspeicher) wächst 8k gegen 64k um den Faktor 40 statt 8."""
    klein, gross = _zeile("beim Rangieren und vom Spielen und ", 8000), _zeile("beim Rangieren und vom Spielen und ", 64000)
    wachstum, _, zeit = _wachstum(lambda: personenkontext.hofnamen(klein, wissen),
                                  lambda: personenkontext.hofnamen(gross, wissen), 8, 2.0)
    assert wachstum < 2.0, f"hofnamen wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_ab5u_10_hofnamen_kandidaten_lange_zeile_waechst_linear():
    baustein = "beim Kaltl und vom Zachl, zum Grebl und "
    klein, gross = _zeile(baustein, 8000), _zeile(baustein, 64000)
    wachstum, _, zeit = _wachstum(lambda: personenkontext.hofnamen_kandidaten(klein, wissen),
                                  lambda: personenkontext.hofnamen_kandidaten(gross, wissen), 8, 2.0)
    assert wachstum < 2.0, f"hofnamen_kandidaten wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_ab5u_10_jahr_unter_spaltenkopf_waechst_linear():
    """R7 der Abnahme (Suche nach dem Spaltenkopf ohne Zeilengrenze) wächst um den Faktor 50 statt 8."""
    def tabelle(n):
        return "Gebäude\t\tBaujahr\t\tBauart\n" + _zeile("Lagerhalle:\t\t1998\t\tMassiv\n", n)
    klein, gross = tabelle(8000), tabelle(64000)
    wachstum, _, zeit = _wachstum(lambda: kennungsformen.zugangscode_verdacht(klein),
                                  lambda: kennungsformen.zugangscode_verdacht(gross), 8, 2.0)
    assert wachstum < 2.0, f"zugangscode_verdacht wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_n7_personenwort_rollenwort_waechst_linear():
    baustein = "Laut Nachbar Händler und mit der Tante Halter, Kunde Pfarrer wurde befragt; "
    klein, gross = _zeile(baustein, 8000), _zeile(baustein, 64000)
    wachstum, _, zeit = _wachstum(lambda: personenkontext.personenwort_rollenwort(klein, wissen),
                                  lambda: personenkontext.personenwort_rollenwort(gross, wissen), 8, 2.0)
    assert wachstum < 2.0, f"personenwort_rollenwort wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_n7_allerweltswort_als_name_waechst_linear():
    """A5-05: Allerweltswort im starken Personenkontext – Begleiter und "laut" nur im Fenster vor dem Personenwort
    (ohne Fenster, Eingriff N10, wächst die Prüfung auf einer langen Zeile quadratisch)."""
    baustein = "Laut Nachbar Wasser war alles nass und Nachbarin Regen hat angerufen, "
    klein, gross = _zeile(baustein, 8000), _zeile(baustein, 64000)
    assert personenkontext.personenwort_namen(klein)                    # die Regel greift im Baustein
    wachstum, _, zeit = _wachstum(lambda: personenkontext.personenwort_namen(klein),
                                  lambda: personenkontext.personenwort_namen(gross), 8, 2.0)
    assert wachstum < 2.0, f"personenwort_namen wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_n7_moebel_code_lange_zeile_waechst_linear():
    """moebel_code_mehrdeutig sucht Zeile und Satz nur im Fenster um "Code" (Eingriff N12: Zeilenanfang ohne Fenster
    wächst auf einer langen Zeile quadratisch)."""
    baustein = "Der Kleiderschrank aus dem Katalog hat den Code 4471 und "
    klein, gross = _zeile(baustein, 8000), _zeile(baustein, 64000)
    assert kennungsformen.moebel_code_mehrdeutig(klein)                 # die Regel greift im Baustein
    wachstum, _, zeit = _wachstum(lambda: kennungsformen.moebel_code_mehrdeutig(klein),
                                  lambda: kennungsformen.moebel_code_mehrdeutig(gross), 8, 2.0)
    assert wachstum < 2.0, f"moebel_code_mehrdeutig wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def _ausgabe_platzhalter_saetze(pfad, mit_platzhalter):
    """Ausgabe-Seite mit je einem Satz „tätig als Schöffin am Amtsgericht i.“ je Eintrag von mit_platzhalter, 40 Sätze
    je Zeile; ist der Eintrag wahr, steht davor ein graues Rechteck, der Platzhalter-Text „[PERSON A]“ am Ende der
    Textebene (wie die Schwärzung sie schreibt)."""
    import pymupdf as fitz
    from anonymisierer import restrisiko
    doc = fitz.open()
    s = doc.new_page(width=3000, height=40 + 6 * (len(mit_platzhalter) // 40 + 1))
    rechtecke, x, y = [], 10.0, 20.0
    for i, ph in enumerate(mit_platzhalter):
        if i and i % 40 == 0:
            x, y = 10.0, y + 6
        if ph:
            r = fitz.Rect(x, y - 3, x + 14, y + 1)
            rechtecke.append(r)
            x = r.x1 + 1.5
        t = f"tätig als Schöffin am Amtsgericht {i}."
        s.insert_text((x, y), t, fontsize=3, fontname="helv")
        x += 2 + fitz.get_text_length(t + " ", fontname="helv", fontsize=3)
    for r in rechtecke:
        s.draw_rect(r, color=None, fill=restrisiko.FUELLFARBE)
        s.insert_text((r.x0 + 0.5, r.y1 - 0.8), "[PERSON A]", fontsize=2, fontname="helv")
    doc.save(pfad)
    doc.close()


def test_n7_beruf_neben_platzhalter_lange_zeile_waechst_linear(tmp_path):
    """_personen_platzhalter_im_satz prüft nur die Wörter des Satzes um „als“ (Eingriff N13: alle Wörter vom
    Seitenanfang an – wächst auf einer langen Zeile, in der nur der letzte Satz einen Platzhalter hat, quadratisch)."""
    from anonymisierer import restrisiko
    alle = tmp_path / "alle.pdf"
    _ausgabe_platzhalter_saetze(alle, [True] * 20)
    v = restrisiko.restrisiko_pruefen(alle, platzhalter=["[PERSON A]"])
    assert sum(x.text == "Schöffin" for x in v) == 20, [(x.text, x.grund) for x in v][:5]
    klein, gross = tmp_path / "klein.pdf", tmp_path / "gross.pdf"
    _ausgabe_platzhalter_saetze(klein, [False] * 39 + [True])
    _ausgabe_platzhalter_saetze(gross, [False] * 319 + [True])
    v = restrisiko.restrisiko_pruefen(klein, platzhalter=["[PERSON A]"])
    assert sum(x.text == "Schöffin" for x in v) == 1, [(x.text, x.grund) for x in v][:5]
    wachstum, _, zeit = _wachstum(lambda: restrisiko.restrisiko_pruefen(klein, platzhalter=["[PERSON A]"]),
                                  lambda: restrisiko.restrisiko_pruefen(gross, platzhalter=["[PERSON A]"]), 8, 2.0)
    assert wachstum < 2.0, f"Beruf neben Platzhalter wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_n7_alarmcode_lange_zeile_waechst_linear():
    baustein = "Feueralarmcode 3401 und Brandalarm-Code 2297, "
    klein, gross = _zeile(baustein, 8000), _zeile(baustein, 64000)
    wachstum, _, zeit = _wachstum(lambda: kennungsformen.alarm_code_mehrdeutig(klein),
                                  lambda: kennungsformen.alarm_code_mehrdeutig(gross), 8, 2.0)
    assert wachstum < 2.0, f"alarm_code_mehrdeutig wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_n7_artikel_person_lange_zeile_waechst_linear():
    baustein = "hat der Schwarzl den Unfall gemeldet und der Fink rammte das Tor, "
    klein, gross = _zeile(baustein, 8000), _zeile(baustein, 64000)
    wachstum, _, zeit = _wachstum(lambda: pruefe_text(klein), lambda: pruefe_text(gross), 8, 2.0)
    assert wachstum < 2.0, f"pruefe_text (Artikel + Person) wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_n7_kammfeld_feldname_darunter_waechst_linear():
    """Feldname links, über oder unter dem Wert: die Zeilen darüber/darunter und die Feldnamen davor über einen Index
    (je Wert sonst alle Zeilen bzw. alle Feldnamen der Seite)."""
    funktion = next(e for e in detektoren.REGISTER if e.name == "struktur.kammfeld").funktion

    def dok(n):
        return seitenmodell.dokument_aus_text(_zeile("M U S T E R M A N N\nName\n", n))
    klein_dok, gross_dok = dok(4000), dok(64000)
    kontext = Kontext(ALLE, "hoch")
    # gemessen ohne Regression 0,7 bis 1,0; mit den Eingriffen N5 (Feldnamen je Zeile ohne Zwischenspeicher) 16 und N6
    # (Feldname links davor je Wert über alle Feldnamen der Seite, wie bis 5efcc0c) 3,0
    wachstum, _, zeit = _wachstum(lambda: funktion(klein_dok, kontext), lambda: funktion(gross_dok, kontext), 16, 2.0)
    assert wachstum < 2.0, f"kammfeld wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


# ----------------------------------------------------------------------
# Kammfelder auf Scans: eigener Feldname der Zeile (AB5U-03) und Feldname unter dem Feld (A5-07) – über Indizes nach der
# Höhe statt je Feld über alle Wörter bzw. Felder der Seite; Ergebnis gleich der direkten Suche (zufällige Seiten)
# ----------------------------------------------------------------------
def _kamm_seite(zeilen: int, versatz: float = 0.0):
    """Gedachte Scan-Seite: je Zeile ein Feldname links ("Name") und ein Feld aus vier Kästchen mit einem Buchstaben
    darin – Wörter als (start, ende, x0, y0, x1, y1) wie kammfelder._woerter, Felder wie kammraster."""
    from types import SimpleNamespace
    teile, woerter, felder, pos = [], [], [], 0
    for i in range(zeilen):
        y = 20.0 + 20.0 * i + versatz
        for wort, x0, x1 in (("Name", 40.0, 70.0), ("A", 203.0, 208.0)):
            woerter.append((pos, pos + len(wort), x0, y + 2.0, x1, y + 10.0))
            teile.append(wort + " ")
            pos += len(wort) + 1
        kaesten = [(200.0 + 12.0 * k, y, 211.0 + 12.0 * k, y + 12.0) for k in range(4)]
        felder.append({"kaesten": kaesten, "rahmen": (200.0, y, 247.0, y + 12.0), "gefuellt": [True] * 4})
    seite = SimpleNamespace(text="".join(teile))
    seite._kamm_woerter = (seite.text, woerter)
    return seite, felder


def _eigener_direkt(seite, feld, felder) -> bool:
    from anonymisierer import kammraster
    from anonymisierer.detektoren import kammfelder
    x0, y0, _, y1 = kammraster.kopfkasten(feld)
    hoehe = max(y1 - y0, 4.0)
    for w in seite._kamm_woerter[1]:
        mitte = (w[3] + w[5]) / 2.0
        if y0 - 0.3 * hoehe <= mitte <= y1 + 0.3 * hoehe and w[4] <= x0 + kammfelder.FELD_RAND_PT \
                and not any(kammfelder._im_feld(w, f) for f in felder) \
                and any(c.isalpha() for c in seite.text[w[0]:w[1]]) \
                and not kammraster.teil_etikett(seite.text[w[0]:w[1]].strip(".:;,()")):
            return True
    return False


def _darunter_direkt(feld, felder, oberkante, unterkante) -> bool:
    from anonymisierer import kammraster
    x0, _, _, y1 = kammraster.kopfkasten(feld)
    # Abstand zum Feld darunter höchstens UNTER_FAKTOR mal der zum eigenen Feld (Nachbesserung 8, Abnahme 6 A6-08:
    # enger Zeilenabstand) – dieselbe Regel wie kammraster.gehoert_zum_feld_darunter, hier ohne Index über alle Felder
    abstand_eigen = max(oberkante - y1, kammraster.UNTER_FAKTOR * (oberkante - y1))
    for f in felder:
        fx0, fy0, _, _ = kammraster.kopfkasten(f)
        if f is not feld and fy0 >= unterkante - 1.0 and min(feld["rahmen"][2], f["rahmen"][2]) - max(x0, fx0) > -10.0 \
                and fy0 - unterkante <= abstand_eigen:
            return True
    return False


def test_n7_kamm_indizes_wie_direkte_suche():
    import random
    from anonymisierer import kammraster
    from anonymisierer.detektoren import kammfelder
    zufall = random.Random(5)
    for durchgang in range(30):
        seite, felder = _kamm_seite(12, versatz=zufall.uniform(0, 5))
        # Wörter und Felder durcheinander verschieben: manche Zeilen ohne Feldnamen, manche Felder höher/tiefer
        woerter = [(s, e, x0 + zufall.uniform(-30, 150), y0 + zufall.uniform(-8, 8), x1 + zufall.uniform(-30, 150),
                    y1 + zufall.uniform(-8, 8)) for s, e, x0, y0, x1, y1 in seite._kamm_woerter[1]]
        seite._kamm_woerter = (seite.text, woerter)
        for f in felder:
            dy = zufall.uniform(-6, 6)
            f["kaesten"] = [(k[0], k[1] + dy, k[2], k[3] + dy) for k in f["kaesten"]]
            f["rahmen"] = (f["rahmen"][0], f["rahmen"][1] + dy, f["rahmen"][2], f["rahmen"][3] + dy)
        for f in felder:
            assert kammfelder._eigener_feldname(seite, f, felder) == _eigener_direkt(seite, f, felder)
            for ober in (2.0, 8.0, 15.0):
                o = kammraster.kopfkasten(f)[3] + ober
                assert kammraster.gehoert_zum_feld_darunter(f, felder, o, o + 8.0) == \
                    _darunter_direkt(f, felder, o, o + 8.0), (durchgang, ober)


def test_n7_kamm_eigener_feldname_waechst_linear():
    """Je Feld nur die Wörter und Felder auf seiner Höhe (Eingriffe N7: alle Wörter je Feld, N8: alle Felder je Wort)."""
    from anonymisierer.detektoren import kammfelder
    klein, gross = _kamm_seite(250), _kamm_seite(2000)

    def lauf(sf):
        seite, felder = sf
        return [kammfelder._eigener_feldname(seite, f, felder) for f in felder]
    assert all(lauf(klein))
    wachstum, _, zeit = _wachstum(lambda: lauf(klein), lambda: lauf(gross), 8, 2.0)
    assert wachstum < 2.0, f"_eigener_feldname wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_n7_kamm_feld_darunter_waechst_linear():
    """Je Feld nur die Felder mit passender Oberkante (Eingriff N9: alle Felder der Seite je Feld)."""
    from anonymisierer import kammraster
    klein, gross = _kamm_seite(250)[1], _kamm_seite(2000)[1]

    def lauf(felder):
        return [kammraster.gehoert_zum_feld_darunter(f, felder, f["rahmen"][3] + 2.0, f["rahmen"][3] + 7.0)
                for f in felder]
    assert any(lauf(klein))
    wachstum, _, zeit = _wachstum(lambda: lauf(klein), lambda: lauf(gross), 8, 2.0)
    assert wachstum < 2.0, f"gehoert_zum_feld_darunter wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


# ----------------------------------------------------------------------
# Kammfeld-Probe der Abnahme 5 (k01, k04): Datumsteile nicht weitergeben, Etage keine Hausnummer, unlesbarer eigener
# Feldname unter einem Anschrift-Feldnamen der Zeile
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, kurz", [
    ("04", True), ("Monat O0 4", True), ("Tg25", True), ("O1", True),
    ("1981", False), ("25.04.1981", False), ("25041981", False), ("14 03 1987", False),
])
def test_k01_datumsteil_nur_an_seiner_stelle(text, kurz):
    from anonymisierer import analyse
    assert analyse._nur_am_etikett("geburt", text) is kurz


def test_k01_geburtsmonat_nicht_im_versicherungsbeginn():
    """Der Monat des Geburtsdatums (OCR "O0 4") wird nicht an den gleichen Monat des Versicherungsbeginns
    weitergegeben; die Teile des Geburtsdatums selbst bleiben geschwärzt."""
    text = ("Geburtsdatum\t\tTag 2 5\t\tMonat O0 4\t\tJahr 1 9 8 1\n"
            "Versicherungsbeginn\t\tTag 0 1\t\tMonat O0 4\t\tJahr 2 0 2 6")
    funde = _funde(text)
    zweite = text.index("Versicherungsbeginn")
    for f in funde:
        for st in f["stellen"]:
            if st.get("an", True) and "start" in st and f["kategorie"] == "geburt":
                assert st["start"] < zweite, (st, f["kategorie"])
    assert any("1 9 8 1" in s for s in _stellen(funde))


def _zeilenformular(zeilen):
    """Vektorseite: je Zeile ein Feldname links, dahinter Teil-Feldnamen mit Kästchen (wie die Kammfeld-Probe k04)."""
    import pymupdf as fitz
    mm = 72 / 25.4
    doc = fitz.open()
    seite = doc.new_page(width=595, height=842)
    seite.insert_text((57, 60), "Musterkasse Versicherung AG", fontsize=11, fontname="helv")
    y = 120
    for zeile, teile in zeilen:
        seite.insert_text((57, y + 13), zeile, fontsize=9, fontname="helv")
        x = 200
        for teil, wert, n in teile:
            seite.insert_text((x, y + 13), teil, fontsize=9, fontname="helv")
            x += fitz.get_text_length(teil, fontname="helv", fontsize=9) + 8
            form = seite.new_shape()
            kaesten = [fitz.Rect(x + i * 5 * mm, y, x + (i + 1) * 5 * mm, y + 6.4 * mm) for i in range(n)]
            for k in kaesten:
                form.draw_rect(k)
            form.finish(color=(0.2, 0.2, 0.25), width=0.5)
            form.commit()
            for k, c in zip(kaesten, wert):
                g = 0.62 * k.height
                b = fitz.get_text_length(c, fontname="hebo", fontsize=g)
                seite.insert_text(((k.x0 + k.x1) / 2 - b / 2, k.y1 - (k.height - 0.72 * g) / 2), c, fontsize=g,
                                  fontname="hebo")
            x = kaesten[-1].x1 + 14
        y += 6.4 * mm + 18
    return doc


@pytest.fixture(scope="module")
def _ocr():
    from anonymisierer.ocr import OcrDienst
    with OcrDienst(prozesse=1) as dienst:
        yield dienst


def _scan_funde(doc, pfad, dienst):
    import pymupdf as fitz
    from anonymisierer.analyse import analysiere_pdf
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(200 / 72, 200 / 72), colorspace=fitz.csGRAY)
    ziel = fitz.open()
    s = ziel.new_page(width=pix.width * 72 / 200, height=pix.height * 72 / 200)
    s.insert_image(s.rect, stream=pix.tobytes("png"))
    ziel.save(pfad)
    ziel.close()
    return analysiere_pdf(pfad, ALLE, [], [], ocr=dienst)["funde"]


def test_k04_etage_keine_hausnummer_unbekannter_teilname_anschrift(tmp_path, _ocr):
    """"Lage der Wohnung ⇥ Etage [3]": eine Etage ist keine Hausnummer (gemeldet statt geschwärzt); "Anschrift ⇥ Srae
    [LINDENWEG] ⇥ Hausnr. [14]": der unlesbare eigene Feldname ("Srae") nimmt den Feldnamen der Zeile – geschwärzt."""
    from conftest import _tessdata_vorhanden
    if not _tessdata_vorhanden():
        pytest.skip("Tesseract-Sprachdaten fehlen")
    doc = _zeilenformular([("Lage der Wohnung", [("Etage", "3", 2), ("Zimmer", "4", 2)]),
                           ("Anschrift", [("Srae", "LINDENWEG", 12), ("Hausnr.", "14", 2)])])
    stellen = [st["text"] for f in _scan_funde(doc, tmp_path / "k04.pdf", _ocr) for st in f["stellen"]
               if st.get("an", True)]
    assert any("LINDENWEG" in s.replace(" ", "").upper() for s in stellen), stellen
    assert any("14" in s.replace(" ", "") for s in stellen), stellen
    assert not any("Etage" in s or s.strip() in ("3", "4") for s in stellen), stellen


def _kamm_ocr_seite(zeilen, felder):
    """OCR-Seite aus Wörtern [(x0, y0, x1, y1, text, zeile)] und Kammfeldern [(x0, y0, n, wert)] (je Kästchen 12 pt)."""
    import pymupdf as fitz
    doc = fitz.open()
    seite = doc.new_page(width=595, height=842)
    woerter = [(x0, y0, x1, y1, w, 0, z, i) for i, (x0, y0, x1, y1, w, z) in enumerate(zeilen)]
    s = seitenmodell.seite_aufbauen(seite, 0, ocr_woerter=woerter, ocr_quelle="ocr")
    doc.close()
    s.kammfelder = [{"kaesten": [(x0 + 12 * i, y0, x0 + 12 * (i + 1), y0 + 16) for i in range(n)],
                     "rahmen": (x0, y0, x0 + 12 * n, y0 + 16), "gefuellt": [True] * n} for x0, y0, n, _ in felder]
    return seitenmodell.Dokument(None, [s])


def _kamm_scan_treffer(dok):
    funktion = next(e for e in detektoren.REGISTER if e.name == "struktur.kammfeld_scan").funktion
    return {(t.kategorie, dok.text[t.start:t.ende]) for t in funktion(dok, Kontext(ALLE, "hoch"))}


def test_k04_unlesbarer_teilname_nimmt_feldnamen_der_zeile():
    """k04 scan200r: "Anschrift ⇥ See" in einer Zeile, der Wert als eigene Zeile im Feld – mit dem Feldnamen der Zeile
    ("Anschrift") geschwärzt (auf 5efcc0c nur gemeldet, auf 0230782 geschwärzt)."""
    dok = _kamm_ocr_seite([(57, 110, 100, 122, "Anschrift", 0), (200, 110, 218, 122, "See", 0),
                           (274, 111, 400, 121, "LINDENWEG", 1)], [(270, 108, 12, "LINDENWEG")])
    assert ("strasse", "LINDENWEG") in _kamm_scan_treffer(dok), _kamm_scan_treffer(dok)


@pytest.mark.parametrize("teil, wert, erwartet", [
    ("Hausnr.", "2&1", True),        # eigen505 b008: "27" als "2&1" gelesen (auf 0230782 geschwärzt, 5efcc0c gemeldet)
    ("Hausnummer", "1S", True),
    ("Hausnummer", "4l", True),
    ("Nr.", "4l", False),            # "Nr." ohne Straße: eine Positionsnummer (wie bisher)
    ("Etage", "2&1", False),         # kein Feldname der Hausnummer
    ("Hausnr.", "&", False),         # ohne Ziffer: gemeldet
])
def test_kamm_hausnummer_verlesen(teil, wert, erwartet):
    """Ein kurzes Kammfeld unter dem Feldnamen einer Hausnummer mit einer Ziffer gilt als Hausnummer, auch wenn die
    Texterkennung ein Zeichen verliest (Kammfeld-Korpus eigen505 der Abnahme 5)."""
    dok = _kamm_ocr_seite([(57, 110, 150, 122, "Anschrift", 0), (200, 110, 250, 122, teil, 0),
                           (274, 111, 292, 121, wert, 0)], [(270, 108, 2, wert)])
    assert (("strasse", wert) in _kamm_scan_treffer(dok)) is erwartet, _kamm_scan_treffer(dok)


@pytest.mark.parametrize("zeile, teil, wert, erwartet", [
    ("Anschrift", "", "14", True),                   # ohne Teil-Feldnamen: eine Hausnummer (5efcc0c, 0230782)
    ("Straße und Hausnummer", "", "14", True),
    ("Wohnanschrift", "Haus-Nr.", "7", True),
    ("Anschrift", "Etage", "3", False),              # Teil der Wohnung: keine Hausnummer
    ("Wohnung", "Zimmer", "4", False),
])
def test_n7_kurzer_wert_im_anschriftfeld(zeile, teil, wert, erwartet):
    """Selbstprüfung P1 (Nachbesserung 7): die Ausnahme für kurze Werte im Anschriftfeld gilt nur unter einem
    Feldnamen für einen Teil der Wohnung (Etage, Zimmer, Stock …), nicht für jeden Wert ohne Hausnummer-Feldnamen."""
    woerter = [(57, 110, 150, 122, zeile, 0)] + ([(200, 110, 250, 122, teil, 0)] if teil else []) \
        + [(274, 111, 292, 121, wert, 0)]
    dok = _kamm_ocr_seite(woerter, [(270, 108, 2, wert)])
    assert (("strasse", wert) in _kamm_scan_treffer(dok)) is erwartet, _kamm_scan_treffer(dok)


@pytest.mark.parametrize("teil, erwartet", [("Etage", False), ("Hausnr.", True)])
def test_k04_kurzer_wert_nur_unter_hausnummer(teil, erwartet):
    dok = _kamm_ocr_seite([(57, 110, 150, 122, "Wohnung", 0), (200, 110, 226, 122, teil, 0),
                           (274, 111, 280, 121, "3", 0)], [(270, 108, 2, "3")])
    assert (("strasse", "3") in _kamm_scan_treffer(dok)) is erwartet, _kamm_scan_treffer(dok)
