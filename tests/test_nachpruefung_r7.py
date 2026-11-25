"""Nachbesserung 2 nach der Nachprüfung von integration-r7 (frische Gegenprüfer „Lecks“ A und „Über-Schwärzung,
Laufzeit, Robustheit, Windows“ B, dazu die Prüfung des Hauptagenten C).

Je Befund: die Zeile der Prüfer, Abwandlungen und Gegenproben – nicht geheime Nachbarn bleiben lesbar. Wo eine Regel
der Erkennung neu greift oder eine Ausnahme enger wird, prüft ein Test auch die Selbstkontrolle (restrisiko.py). Die
IDs nennen den Prüfer: A/NP-xx (Lecks), B/NP-xx (Über-Schwärzung u. a.), LK-xx/U-x/V-x die alten Befunde.
Alle Personen, Nummern und Anschriften sind frei erfunden."""

import ast
import pathlib
import time

import pymupdf as fitz
import pytest

from anonymisierer import auftrag, muster, personenkontext
from anonymisierer.analyse import analysiere_pdf, analysiere_text
from anonymisierer.restrisiko import pruefe_text
from anonymisierer.schwaerzung import schwaerze_pdf

ALLE = {k for k, _, _, _, an in muster.KATEGORIEN if an}
REPO = pathlib.Path(__file__).resolve().parent.parent


# ----------------------------------------------------------------------
# Hilfsfunktionen
# ----------------------------------------------------------------------
def _funde(text, profil="hoch"):
    return analysiere_text(text, ALLE, [], [], profil=profil)


def _stellen(funde, kategorie=None) -> set:
    """Texte aller angehakten Stellen (optional nur einer Kategorie)."""
    return {st["text"] for f in funde if kategorie is None or f["kategorie"] == kategorie
            for st in f["stellen"] if st.get("an", True)}


def _geschwaerzt(text, wert, kategorie=None, profil="hoch") -> bool:
    return any(wert in s for s in _stellen(_funde(text, profil), kategorie))


def _beruehrt(text, wert) -> bool:
    """Wird der Wert oder ein Teil davon geschwärzt?"""
    return any(wert in s or (len(s) >= 2 and s in wert) for s in _stellen(_funde(text)))


def _verdacht(text, **kw) -> list:
    return [(v.text, v.grund) for v in pruefe_text(text, **kw)]


def _gemeldet(text, wert, **kw) -> bool:
    return any(wert in t or (len(t) >= 3 and t in wert) for t, _ in _verdacht(text, **kw))


def _ausgabe(text) -> tuple:
    """(Ausgabetext mit Platzhaltern [KATEGORIE], Platzhalter) – wie die Schwärzung die angehakten Stellen ersetzt."""
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


def _ausgabe_verdacht(text) -> list:
    """Verdacht der Selbstkontrolle auf dem Ausgabetext (die angehakten Stellen ersetzt)."""
    aus, ph = _ausgabe(text)
    return _verdacht(aus, platzhalter=ph)


def _pdf(pfad, seiten, groesse=10, xs=(60, 220, 380)):
    """PDF aus Seiten; je Seite Zeilen, "\\t\\t" trennt die Spalten (x-Lagen xs)."""
    doc = fitz.open()
    for zeilen in seiten:
        seite = doc.new_page(width=595, height=842)
        for i, zeile in enumerate(zeilen):
            teile = zeile.split("\t\t")
            for k, teil in enumerate(teile):
                if teil:
                    seite.insert_text((xs[k] if len(teile) > 1 else xs[0], 80 + 16 * i), teil, fontsize=groesse,
                                      fontname="helv")
    doc.save(pfad)
    doc.close()
    return pfad


def _pdf_stellen(pfad, kategorie=None) -> set:
    erg = analysiere_pdf(pfad, ALLE, [], [], profil="hoch")
    assert not erg.get("fehler"), erg.get("fehler")
    return {st["text"] for f in erg["funde"] if kategorie is None or f["kategorie"] == kategorie
            for st in f["stellen"] if st.get("an", True)}


# ----------------------------------------------------------------------
# A/NP-01 (Kalenderwort als Name): ein Datum dahinter allein macht den Wochentag nicht zum Datum
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, name", [
    ("Gesprächspartner: Freitag, 14.11.2026", "Freitag"),
    ("Anrufer: Mai, 03.02.2026, Rückfrage zur Police", "Mai"),
    ("Mit freundlichen Grüßen\nJuni", "Juni"),
    ("Von: Benedikt Oktober <b.oktober@example.de>", "Oktober"),
])
def test_np01_kalenderwort_als_name(text, name):
    assert _geschwaerzt(text, name, "namen"), _stellen(_funde(text))


@pytest.mark.parametrize("text", [
    "Termin: Freitag, 14.11.2026",
    "Rückruf am Freitag, 12.03.2026 erbeten.",
    "Sprechzeiten Montag bis Freitag, 8 bis 16 Uhr",
    "Beginn im Mai 2026",
])
def test_np01_gegenprobe_kalenderwort_als_datum(text):
    assert not ({"Freitag", "Mai", "Montag"} & _stellen(_funde(text), "namen")), _stellen(_funde(text))


def test_np01_kalenderwort_regel_kontext_davor():
    t = "Gesprächspartner: Freitag, 14.11.2026"
    s = t.index("Freitag")
    assert not personenkontext.kalenderwort_als_datum(t, s, s + 7)       # Datum dahinter allein: kein Datum
    t2 = "Rückruf am Freitag, 14.11.2026"
    s2 = t2.index("Freitag")
    assert personenkontext.kalenderwort_als_datum(t2, s2, s2 + 7)


def test_np06_kinder_mit_alter_und_tabelle():
    assert {"August", "Juni"} <= _stellen(_funde("Die Kinder August (9) und Juni (6) sind mitversichert."), "namen")
    text = "Name\t\tVorname\t\tGeburtsdatum\nHuber\t\tMai\t\t24.05.2020"
    assert _geschwaerzt(text, "Mai", "namen"), _stellen(_funde(text))


# ----------------------------------------------------------------------
# A/NP-02 = B/NP-05, A/NP-07, B/NP-09, B/NP-10: Mannheimer Quadrate
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert", [
    ("Risikoort: E 3, 1", "E 3, 1"),
    ("Versicherungsort: L 2, 9", "L 2, 9"),
    ("Hauptwohnsitz: L 14, 16", "L 14, 16"),
    ("C.1.3: Q 7, 22", "Q 7, 22"),
    ("Die Kundin wohnt seit März 2019 in R 3, 4 im zweiten Stock.", "R 3, 4"),
    ("Bisheriger Halter: Brettschneider, Annemarie, Q 3, 7", "Q 3, 7"),
    ("Abstellort des Fahrzeugs: Tiefgarage K 3, 22", "K 3, 22"),
    ("Zweitwohnsitz: M2, 9a", "M2, 9a"),
])
def test_quadrat_hinter_etikett_und_wohnen(text, wert):
    assert _beruehrt(text, wert), _stellen(_funde(text))


@pytest.mark.parametrize("text, wert", [
    ("Absender: Kanzlei, 68165 Mannheim\nEs gelten insbesondere A 1, 2 und A 2, 5 sowie B 3, 4 der AKB.", "A 2, 5"),
    ("Abflug Mannheim\nSitzplatz: Reihe F 12, 14", "F 12, 14"),
    ("Schadenskizze (Mannheim): Feld B 3, 4 und Feld C 5, 2", "B 3, 4"),
    ("Raum B 2, 7 im Erdgeschoss", "B 2, 7"),
    ("Unfall auf der A 8, 3 km vor der Ausfahrt", "A 8, 3"),
])
def test_quadrat_gegenproben(text, wert):
    assert not _beruehrt(text, wert), _stellen(_funde(text))
    assert not any(wert in t for t, _ in _ausgabe_verdacht(text)), _ausgabe_verdacht(text)


def test_quadrat_ohne_etikett_wird_gemeldet():
    # ohne Etikett und ohne Mannheim: die Selbstkontrolle meldet das Quadrat hinter "in"
    assert _gemeldet("Treffpunkt in U 1, 19 am Eingang.", "U 1, 19") \
        or _beruehrt("Treffpunkt in U 1, 19 am Eingang.", "U 1, 19")


def test_quadrat_keine_doppelte_modulvariable():
    """Ein Modul darf eine Variable auf oberster Ebene nicht zweimal belegen (die zweite überschrieb die erste und
    machte eine Regel wirkungslos: A/NP-02)."""
    for datei in ("kennungsformen.py", "personenkontext.py", "restrisiko.py", "namen.py", "muster.py",
                  "detektoren/struktur.py", "detektoren/struktur_tabelle.py", "detektoren/struktur_adresse.py",
                  "detektoren/wissen_kontext.py"):
        baum = ast.parse((REPO / "anonymisierer" / datei).read_text(encoding="utf-8"))
        gesehen = {}
        for knoten in baum.body:
            ziele = knoten.targets if isinstance(knoten, ast.Assign) else []
            for ziel in ziele:
                if isinstance(ziel, ast.Name) and ziel.id.endswith("_RE"):
                    assert ziel.id not in gesehen, f"{datei}: {ziel.id} doppelt (Zeilen {gesehen[ziel.id]}, " \
                                                   f"{knoten.lineno})"
                    gesehen[ziel.id] = knoten.lineno


# ----------------------------------------------------------------------
# A/NP-03, A/NP-04 (Marken und Personen in Organisations-Spalten), B/NP-13 (Gegenproben)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, name", [
    ("Freundlichst\nDyson", "Dyson"),
    ("Servus\nJunkers", "Junkers"),
    ("Danke und Grüße\nKrups", "Krups"),
    ("Rücksprache mit Kollege Hengst am Montag.", "Hengst"),
    ("Krankenkasse\t\tBeitrag\nbeim Vater Rauschenbach\t\t120,00 EUR", "Rauschenbach"),
    ("Anbieter\t\tBetrag\nBrandhuber\t\t2.000 EUR", "Brandhuber"),
    ("Darlehensgeber\t\tBetrag\nGruber Sepp\t\t5.000 EUR", "Gruber"),
])
def test_np03_np04_namen_an_personenorten(text, name):
    assert _beruehrt(text, name), _stellen(_funde(text))


@pytest.mark.parametrize("text, wert", [
    ("Mit freundlichen Grüßen\nNeff Kundendienst Süd", "Neff"),
    ("Viele Grüße\nIhr Miele Team", "Miele"),
    ("Versicherer\t\tBeitrag\nSignal Iduna\t\t120,00 EUR", "Signal Iduna"),
    ("Anbieter\t\tBetrag\nMax Heinr. Sutor\t\t2.000 EUR", "Sutor"),
    ("Hausratliste: Waschmaschine Miele, Kühlschrank Liebherr", "Miele"),
])
def test_np13_organisationen_bleiben_lesbar(text, wert):
    assert not _beruehrt(text, wert), _stellen(_funde(text))


def test_np03_marke_laut_wird_gemeldet():
    assert _gemeldet("Laut Wallach ist der Schaden nicht gedeckt.", "Wallach") \
        or _beruehrt("Laut Wallach ist der Schaden nicht gedeckt.", "Wallach")


# ----------------------------------------------------------------------
# A/NP-05 und V1: abgewählte Art.-9-Daten nennen einen Prüfgrund; Religion nur geprüft, wenn angehakt
# ----------------------------------------------------------------------
def test_np05_art9_abgewaehlt_wird_parameter_und_grund(tmp_path):
    pdf = _pdf(tmp_path / "bu.pdf", [["Antrag Berufsunfähigkeit", "Versicherte Person: Kreszentia Gschwandtner",
                                      "Diagnose: Diabetes mellitus Typ 2 seit 2019"]])
    e = analysiere_pdf(pdf, ALLE, [], [], profil="hoch")
    a, _ = auftrag.standard_auftrag(e, schwaerze_pdf)
    assert a.get("art9_abgewaehlt"), a.get("art9_abgewaehlt")
    p = auftrag.schwaerz_parameter(a, True, "hoch", schwaerze_pdf)
    assert p.get("art9_abgewaehlt") == sorted(a["art9_abgewaehlt"])
    s = schwaerze_pdf(pdf, a["funde"], ziel_ordner=tmp_path / "aus", **p)
    assert any("Art. 9" in g for g in s["pruefen_gruende"]), s["pruefen_gruende"]


def test_v1_religion_nur_mit_kategorie():
    text = "Kirchensteuermerkmal: rk"
    assert _gemeldet(text, "rk", profil="maximal")
    assert not _gemeldet(text, "rk", profil="maximal", aktive=sorted(muster.PROFILE["maximal"]["aktive"] - muster.RELIGION))
    assert not _gemeldet(text, "rk", profil="hoch")


# ----------------------------------------------------------------------
# A/NP-08 und B/NP-02 (Adresszusatz), B/NP-01 (Ort hinter Person)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, zusatz", [
    ("Zeuge: Max Wimmer, Kaiserstraße 17, Hinterhaus, 3. OG links, 83022 Rosenheim", "Hinterhaus"),
    ("Anschrift: Lindenstraße 4 (Gartenhaus), 83022 Rosenheim", "Gartenhaus"),
    ("Anschrift: Lindenstraße 4, Einliegerwohnung UG, 83022 Rosenheim", "Einliegerwohnung UG"),
    ("Schusterweg 12\nRückgebäude, 1. OG\n83229 Aschau", "Rückgebäude"),
])
def test_np08_adresszusatz(text, zusatz):
    assert _beruehrt(text, zusatz), _stellen(_funde(text))


@pytest.mark.parametrize("zusatz", ["Augenzeugin", "Mo-Fr 9-12 Uhr", "Leitungswasser", "Privatkunde", "Hausmeister"])
def test_b_np02_kein_adresszusatz(zusatz):
    text = f"Zeugin: Anna Berg, Kaiserstraße 17, {zusatz}, 83022 Rosenheim"
    assert not _beruehrt(text, zusatz), _stellen(_funde(text))


@pytest.mark.parametrize("text, wert", [
    ("Behandelnder Arzt: Dr. Klaus Brenner, Orthopädie", "Orthopädie"),
    ("Hausarzt: Dr. med. Petra Huber, Allgemeinmedizin", "Allgemeinmedizin"),
    ("Zeuge: Hans Maier, Linienbus", "Linienbus"),
])
def test_b_np01_kein_ort_hinter_person(text, wert):
    assert not _beruehrt(text, wert), _stellen(_funde(text))


def test_b_np01_ort_hinter_person_bleibt():
    assert _geschwaerzt("Einweisender Arzt: Dr. Anton Rieger, Gaimersheim", "Gaimersheim")


# ----------------------------------------------------------------------
# A/NP-09: Fortsetzung einer Tabelle auf der Folgeseite, angekündigt auf der Vorseite; ohne Ankündigung gemeldet
# ----------------------------------------------------------------------
_KINDER_SEITE1 = ["Kinder des Versicherungsnehmers", "", "Name\t\tVorname\t\tGeburtsdatum",
                  "Kreuzpointner\t\tLorenz\t\t03.03.2012", ""]
_KINDER_SEITE2 = ["Edelhauser\t\tAmalia\t\t16.04.2016", "Fischbacher\t\tBalthasar\t\t22.08.2019"]


@pytest.mark.parametrize("hinweis", ["Weitere Kinder siehe Folgeseite.", "Fortsetzung auf Seite 2",
                                     "Bitte wenden"])
def test_np09_fortsetzung_angekuendigt(tmp_path, hinweis):
    pdf = _pdf(tmp_path / "kinder.pdf", [_KINDER_SEITE1 + [hinweis], _KINDER_SEITE2])
    assert {"16.04.2016", "22.08.2019"} <= _pdf_stellen(pdf, "geburt")


def test_np09_ohne_ankuendigung_keine_fortsetzung_aber_verdacht(tmp_path):
    pdf = _pdf(tmp_path / "kinder.pdf", [_KINDER_SEITE1 + ["Unterschrift des Antragstellers"], _KINDER_SEITE2])
    erg = analysiere_pdf(pdf, ALLE, [], [], profil="hoch")
    a, _ = auftrag.standard_auftrag(erg, schwaerze_pdf)
    p = auftrag.schwaerz_parameter(a, True, "hoch", schwaerze_pdf)
    s = schwaerze_pdf(pdf, a["funde"], ziel_ordner=tmp_path / "aus", **p)
    gemeldet = {v.text for v in s["verdacht"]}
    for datum in ("16.04.2016", "22.08.2019"):
        with fitz.open(s["ausgabe"]) as aus:
            if datum in aus[1].get_text():
                assert datum in gemeldet, s["verdacht"]


def test_np09_gegenprobe_andere_tabelle_auf_folgeseite(tmp_path):
    pdf = _pdf(tmp_path / "termine.pdf", [_KINDER_SEITE1 + ["Unterschrift des Antragstellers"],
                                          ["Beratung\t\tHausrat\t\t16.04.2026", "Angebot\t\tKfz\t\t18.04.2026"]])
    assert not ({"Beratung", "16.04.2026"} & _pdf_stellen(pdf))


def test_np09_selbstkontrolle_personenzeile():
    ph = ["[PERSON A]", "[PERSON B]"]
    assert _gemeldet("[PERSON A]\t\t[PERSON B]\t\t16.04.2016", "16.04.2016", platzhalter=ph)
    assert not _gemeldet("[PERSON A]\t\t[PERSON B]\t\tSchaden\t\t16.04.2016", "16.04.2016", platzhalter=ph)
    assert not _gemeldet("Name\t\tVorname\t\tSchadentag\n[PERSON A]\t\t[PERSON B]\t\t16.04.2016", "16.04.2016",
                         platzhalter=ph)


# ----------------------------------------------------------------------
# A/NP-10: Komma-Datum mit zweistelligem Jahr hinter einem Geburts-Etikett
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, datum", [
    ("Kinder: Franziska (geb. 05.09,16)", "05.09,16"),
    ("Geburtsdatum: 17.03,68", "17.03,68"),
    ("Geburtsdatum: 17,03.68", "17,03.68"),
    ("Name\t\tGeb.-Datum\nAnna Huber\t\t05.09,16", "05.09,16"),
])
def test_np10_komma_datum_kurzes_jahr(text, datum):
    assert _geschwaerzt(text, datum, "geburt"), _stellen(_funde(text))


@pytest.mark.parametrize("text", ["Betrag: 5.09,16 EUR", "Rate: 05.09,16"])
def test_np10_gegenprobe_betrag(text):
    assert not _stellen(_funde(text), "geburt")


# ----------------------------------------------------------------------
# A/NP-11 (Profil im Satz), A/NP-12 (Beruf im Satz), A/NP-13 (Zugangsdaten), U3, U4
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert", [
    ("Die Tochter ist auf Instagram unter resi_wimmerl_88 zu finden.", "resi_wimmerl_88"),
    ("Er nennt sich auf TikTok als bergfex.1990 und postet dort.", "bergfex.1990"),
])
def test_np11_profil_im_satz(text, wert):
    assert _geschwaerzt(text, wert, "profilname"), _stellen(_funde(text))


@pytest.mark.parametrize("text", ["Tarif @home: Beitrag wird vom Konto abgebucht.", "Signal Iduna: Kfz-Haftpflicht",
                                  "Ich bin bei Instagram unter Vorbehalt aktiv."])
def test_np11_u3_gegenproben_profil(text):
    assert not _stellen(_funde(text), "profilname"), _stellen(_funde(text))


@pytest.mark.parametrize("text, beruf", [
    ("Die Ehefrau arbeitet in Teilzeit als Hufschmiedin.", "Hufschmiedin"),
    ("Er ist seit 2019 beschäftigt als Zahntechniker.", "Zahntechniker"),
])
def test_np12_beruf_im_satz(text, beruf):
    assert _geschwaerzt(text, beruf, "beruf"), _stellen(_funde(text))


@pytest.mark.parametrize("text, wert", [
    ("Ihr neues Passwort ist ab sofort Hollerbusch2027.", "Hollerbusch2027"),
    ("Displaysperre des Diensthandys: 2468", "2468"),
    ("WLAN-Schlüssel der Ferienwohnung: Bergblick!2026", "Bergblick!2026"),
    ("Garagentoröffner Code 1199", "1199"),
    ("Haustür Code: 1357", "1357"),
])
def test_np13_zugangsdaten(text, wert):
    assert _geschwaerzt(text, wert, "zugangsdaten"), _stellen(_funde(text))


@pytest.mark.parametrize("text, wert", [
    ("Nach 3-mal falscher Eingabe wird die Karte gesperrt.", "3-mal"),
    ("Die PIN ist 4-stellig.", "4-stellig"),
    ("Tarif-Code: HR-PREMIUM", "HR-PREMIUM"),
    ("Das Netz ist WPA2-geschützt.", "WPA2-geschützt"),
    ("Gerät\t\tPIN\t\tStatus\nRouter\t\tgeändert\t\taktiv", "Status"),
])
def test_np13_u4_gegenproben_zugangsdaten(text, wert):
    assert wert not in _stellen(_funde(text)), _stellen(_funde(text))


# ----------------------------------------------------------------------
# A/NP-14 (Hof- und Hausnamen), LK-14 (Familienname mit Artikel)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, name", [
    ("Unfallort: Zufahrt zum Hof Hintermoser bei Siegsdorf", "Hintermoser"),
    ("Unfallort: Einfahrt zum Hof Rottmoser in Frasdorf", "Rottmoser"),
    ("Der Unfall geschah beim Stögerbauer in Inzell.", "Stögerbauer"),
    ("Schadenort: Anwesen Gschwandtner, Ruhpolding", "Gschwandtner"),
])
def test_np14_hofname(text, name):
    assert _geschwaerzt(text, name, "namen"), _stellen(_funde(text))


@pytest.mark.parametrize("text", ["Beim Einparken stieß er gegen die Mauer.", "Der Unfall geschah beim Abbiegen.",
                                  "Wir haben den Hof Süd besichtigt.", "Amtsgericht Hof, Zivilabteilung",
                                  "Der Schaden entstand beim Oktoberfest."])
def test_np14_gegenproben(text):
    assert not _stellen(_funde(text), "namen"), _stellen(_funde(text))


def test_lk14_artikel_familienname_vorname():
    text = "Laut Aussage vom Nachbarn war der Brandstetter am Steuer, nicht die Kölbl Resi."
    assert _geschwaerzt(text, "Kölbl Resi", "namen"), _stellen(_funde(text))
    assert _gemeldet(_ausgabe(text)[0], "Brandstetter", platzhalter=_ausgabe(text)[1]), _ausgabe_verdacht(text)
    assert _geschwaerzt("Wir waren beim Gruber Sepp zum Essen.", "Gruber Sepp", "namen")


@pytest.mark.parametrize("text", ["Der Brenner der Heizung war defekt, die Scheibe ist gesprungen.",
                                  "Die Firma liefert die Teile."])
def test_lk14_gegenproben(text):
    assert not _stellen(_funde(text), "namen")
    assert not _ausgabe_verdacht(text), _ausgabe_verdacht(text)


@pytest.mark.parametrize("text, name", [
    ("Am Steuer saß der Haslbeck, daneben die Wimmer Vroni.", "Haslbeck"),
    ("Gefahren ist laut Zeugin nicht er, es lenkte der Brandstetter.", "Brandstetter"),
    ("Am Telefon bestätigte die Kölbl, dass der Wagen stand.", "Kölbl"),
])
def test_lk14_artikel_name_hinter_verb(text, name):
    """Familienname mit Artikel hinter einem Verb des Fahrens oder Sagens ("saß der Haslbeck"): geschwärzt oder in
    der Selbstkontrolle gemeldet (Nachprüfung A, Probe i03: ohne Verb dahinter still)."""
    aus, ph = _ausgabe(text)
    assert _geschwaerzt(text, name) or _gemeldet(aus, name, platzhalter=ph), (_stellen(_funde(text)),
                                                                             _ausgabe_verdacht(text))


@pytest.mark.parametrize("text", ["Dann war der Brenner defekt und die Scheibe gesprungen.",
                                  "Danach fuhr der Lieferwagen weiter.", "Am Steuer saß der Fahrer des Lieferdienstes.",
                                  "Zuletzt bestätigte die Versicherung den Eingang."])
def test_lk14_artikel_hinter_verb_gegenproben(text):
    assert not _stellen(_funde(text), "namen"), _stellen(_funde(text))
    assert not _ausgabe_verdacht(text), _ausgabe_verdacht(text)


# ----------------------------------------------------------------------
# Probe z1 der Nachprüfung A: Anschriftzusatz, der selbst ein Anschrift-Etikett ist, hinter "Neue Anschrift:"
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, zusatz", [
    ("Neue Anschrift: Lindenweg 9, Hinterhaus, 83229 Aschau im Chiemgau", "Hinterhaus"),
    ("Anschrift: Bergstraße 4, Rückgebäude, 83209 Prien am Chiemsee", "Rückgebäude"),
])
def test_z1_zusatz_hinter_anschrift_etikett(text, zusatz):
    assert _geschwaerzt(text, zusatz), _stellen(_funde(text))


def test_z1_gegenprobe_ort_bleibt_ort():
    text = "Neue Anschrift: Lindenweg 9, Hinterhaus, 83229 Aschau im Chiemgau\nBitte die Police neu ausstellen."
    assert not any("Police" in s for s in _stellen(_funde(text))), _stellen(_funde(text))


# ----------------------------------------------------------------------
# Probe m02 der Nachprüfung A: Tabellenkopf mit nur einem Personen-Etikett ("Anrufer ⇥⇥ Anliegen ⇥⇥ Rückruf bis")
# ----------------------------------------------------------------------
RUECKRUF = ("Rückrufliste Schadenabteilung KW 47\nAnrufer\t\tAnliegen\t\tRückruf bis\n"
            "{a}\t\tWasserschaden Küche\t\t21.11.2026\n{b}\t\tSturmschaden Carport\t\t22.11.2026")


@pytest.mark.parametrize("a, b", [("Viessmann", "Buderus"), ("Buderus", "Viessmann")])
def test_m02_marke_in_spalte_mit_einem_personen_etikett(a, b):
    """Ab der zweiten Datenzeile stand die Marke außerhalb jeder Personenspalte: weder geschwärzt noch gemeldet."""
    text = RUECKRUF.format(a=a, b=b)
    aus, ph = _ausgabe(text)
    for name in (a, b):
        assert _geschwaerzt(text, name, "namen") or _gemeldet(aus, name, platzhalter=ph), (name, aus,
                                                                                         _ausgabe_verdacht(text))


def test_m02_kopfregel():
    assert personenkontext.kopf_mit_personen_etikett(["Anrufer", "Anliegen", "Rückruf bis"], ["person", None, None])
    # zwei Zellen, Ziffern, Satzzeichen oder lange Zellen: kein Kopf
    assert not personenkontext.kopf_mit_personen_etikett(["Anrufer", "Anliegen"], ["person", None])
    assert not personenkontext.kopf_mit_personen_etikett(["Anrufer", "KW 47", "Rückruf bis"], ["person", None, None])
    assert not personenkontext.kopf_mit_personen_etikett(["Ehefrau", "Gstettner, Afra", "Hausfrau"],
                                                         ["person", None, None])
    assert not personenkontext.kopf_mit_personen_etikett(["Kunde", "seit langem treuer Kunde", "Rabatt"],
                                                         ["person", None, None])
    assert not personenkontext.kopf_mit_personen_etikett(["Hersteller", "Gerät", "Standort"], [None, None, "adresse"])


@pytest.mark.parametrize("text", [
    "Übergabeprotokoll\nBearbeiter\t\tVorgang\t\tStatus\nZentrale\t\tNeuanlage\t\terledigt 01.12.2026\n"
    "Außendienst\t\tKündigung\t\toffen 02.12.2026",
    "Inventar Werkstatt\nHersteller\t\tGerät\t\tBaujahr\nBosch\t\tBohrhammer\t\t2019\nMakita\t\tAkkuschrauber\t\t2021",
])
def test_m02_gegenproben(text):
    assert not _stellen(_funde(text), "namen"), _stellen(_funde(text))
    assert not _ausgabe_verdacht(text), _ausgabe_verdacht(text)


# ----------------------------------------------------------------------
# Probe o12 der Nachprüfung A (A/NP-04): Versicherer-Marke mit der Gestalt "Vorname Familienname" in einer
# Organisations-Spalte – bleibt als Versicherer stehen, wird aber gemeldet (ein Bürge dieses Namens ist möglich)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "Sicherheiten\nArt\t\tVersicherer\t\tBetrag\nKautionsbürgschaft\t\tAdam Riese\t\t3.600 EUR",
    "Vorversicherungen\nSparte\t\tVorversicherer\t\tBemerkung\nBürgschaft\t\tAdam Riese\t\tSchwiegervater",
])
def test_o12_marke_in_personengestalt_gemeldet(text):
    aus, ph = _ausgabe(text)
    assert _geschwaerzt(text, "Adam Riese") or _gemeldet(aus, "Adam Riese", platzhalter=ph), (aus,
                                                                                            _ausgabe_verdacht(text))


# ----------------------------------------------------------------------
# LK-12 (Probe tab03 der ersten Gegenprüfung): Straßenname allein auf seiner Zeile bzw. in seiner Zelle, die
# Hausnummer vor der PLZ in der Zeile bzw. Tabellenreihe darunter ("Edelweißstraße" ⏎ "4, 83080 Oberaudorf")
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, werte", [
    ("Anschrift\nEdelweißstraße\n4, 83080 Oberaudorf", ["Edelweißstraße", "4"]),
    ("Neue Anschrift ab 01.12.2026:\nAm Lindenweg\n12a, 83229 Aschau im Chiemgau", ["Am Lindenweg", "12a"]),
])
def test_lk12_strasse_ueber_zwei_zeilen(text, werte):
    stellen = _stellen(_funde(text), "strasse")
    assert all(w in stellen for w in werte), _stellen(_funde(text))


def test_lk12_strasse_ueber_zwei_tabellenreihen(tmp_path):
    pfad = _pdf(str(tmp_path / "zellumbruch.pdf"), [[
        "Antragsübersicht Familie", "Versicherungsnehmer\t\tAnschrift\t\tKonto",
        "Eheleute\t\tEdelweißstraße\t\tDE91 7115 0000", "Gschwandtner\t\t4, 83080 Oberaudorf\t\t0000 4471 22"]],
        xs=(40, 220, 400))
    stellen = _pdf_stellen(pfad)
    assert {"Edelweißstraße", "4"} <= stellen, stellen


@pytest.mark.parametrize("text", ["Bitte beachten Sie den Fußweg\n4, 83080 Oberaudorf",
                                  "Lieferanschrift\nLagerplatz Nord\n4, 83080 Oberaudorf",
                                  "Wegbeschreibung: über den Ring\n2, 83022 Rosenheim"])
def test_lk12_strasse_ueber_zwei_zeilen_gegenproben(text):
    assert not _stellen(_funde(text), "strasse"), _stellen(_funde(text))


def test_lk12_tabelle_gegenprobe(tmp_path):
    pfad = _pdf(str(tmp_path / "objekte.pdf"), [[
        "Objekte", "Versicherungsnehmer\t\tAnschrift\t\tWohnfläche", "Huber\t\tHauptstraße\t\t84 qm",
        "Maier\t\t3 Zimmer, 2. OG\t\t62 qm"]], xs=(40, 220, 400))
    assert not _pdf_stellen(pfad, "strasse"), _pdf_stellen(pfad)


def test_o12_regel_und_gegenproben():
    text = "Art\t\tVersicherer\t\tBetrag\nKautionsbürgschaft\t\tAdam Riese\t\t3.600 EUR\nHausrat\t\tGothaer\t\t120 EUR"
    spannen = personenkontext.org_marken_in_personengestalt(text)
    assert [text[a:b] for a, b in spannen] == ["Adam Riese"]
    for gegen in ("Versicherer\t\tSparte\t\tBeitrag\nAllianz\t\tHausrat\t\t120 EUR\nGothaer\t\tKfz\t\t300 EUR",
                  # Vergleichs- und Bestandslisten: die Marke ist der Versicherer (Domänen-Befund 92, LK-03)
                  "Sparte\t\tVersicherer\t\tTarif\nPHV\t\tAdam Riese\t\tXXL\nHausrat\t\tAdam Riese\t\tgekündigt"):
        assert not personenkontext.org_marken_in_personengestalt(gegen)
        assert not _ausgabe_verdacht(gegen), _ausgabe_verdacht(gegen)
    # außerhalb einer Organisations-Spalte gilt der Name wie bisher als Person (geschwärzt)
    assert _geschwaerzt("Der Schwiegervater Adam Riese hat die Bürgschaft übernommen.", "Adam Riese", "namen")


# ----------------------------------------------------------------------
# A/NP-15: Kopf- oder Allerweltswort als Familienname hinter dem Etikett und in Datenzeilen der Namensspalte
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, name", [
    ("Geburtsname: Stand", "Stand"),
    ("Familienname: Summe", "Summe"),
    ("Geburtsname: Rolle", "Rolle"),
    ("Name: Jansen, Petra\nGeburtsname: Feld", "Feld"),
    ("GEBURTSNAME: STAND", "STAND"),
    ("Nachname\t\tVorname\t\tGeburtsdatum\nStand\t\tLudmilla\t\t03.05.1970", "Stand"),
    ("Nachname\t\tVorname\t\tGeburtsdatum\nSumme\t\tWalburga\t\t12.12.1961", "Summe"),
    ("Name\t\tVorname\t\tGeb.-Datum\nStatus\t\tKreszentia\t\t04.04.1944", "Status"),
])
def test_np15_kopfwort_als_familienname(text, name):
    assert _geschwaerzt(text, name, "namen"), _stellen(_funde(text))


@pytest.mark.parametrize("text, wort", [
    ("Geburtsname: Entfällt", "Entfällt"),
    ("Geburtsname: Vorname", "Vorname"),
    ("Geburtsname:\t\tStatus", "Status"),
    ("Geburtsname:\nArt", "Art"),
    ("Geburtsname: Stand: 01.2025", "Stand"),
    ("Name\t\tVorname\t\tGeb.-Datum\nKeine Angabe\t\t\t\t", "Keine"),
    ("Name\t\tBetrag\nSumme\t\t1.234,00 EUR", "Summe"),
    ("Nachname: Ort", "Ort"),
])
def test_np15_gegenproben_leeres_feld(text, wort):
    assert not any(wort in s for s in _stellen(_funde(text), "namen")), _stellen(_funde(text))


def test_np15_leerwort_nicht_gemeldet():
    assert not _gemeldet("Geburtsname: Entfällt", "Entfällt")


# ----------------------------------------------------------------------
# A/NP-16: Hausnummer in der Folgezeile einer Scan-Zelle ist kein OCR-Rest
# ----------------------------------------------------------------------
def test_np16_ziffer_in_folgezeile_der_zelle(tmp_path):
    pdf = tmp_path / "risikoorte.pdf"
    doc = fitz.open()
    s = doc.new_page(width=595, height=842)
    for x, y, t in [(54, 103, "Nr."), (104, 103, "Anschrift"), (304, 103, "PLZ / Ort"),
                    (54, 125, "1"), (104, 125, "Sonnleitnerstraße"), (104, 137, "112 a"), (304, 125, "83122 Samerberg"),
                    (54, 161, "2"), (104, 161, "Zollhäuslweg"), (104, 173, "7"), (304, 161, "83098 Brannenburg")]:
        s.insert_text((x, y), t, fontsize=9, fontname="helv")
    doc.save(pdf)
    doc.close()
    stellen = _pdf_stellen(pdf, "strasse")
    assert any("Zollhäuslweg" in t for t in stellen) and "7" in stellen, stellen


# ----------------------------------------------------------------------
# B/NP-17: Kinderliste mit Orts-/Monatsnamen; der Grund des Verdachts nennt kein fremdes Etikett
# ----------------------------------------------------------------------
def test_b_np17_kinderliste_daten():
    text = "Kinder:\nMax, 05.09.2016\nParis, 02.02.2011\nJuni, 11.11.2020"
    assert {"05.09.2016", "02.02.2011", "11.11.2020"} <= _stellen(_funde(text), "geburt")


def test_b_np17_platzhalter_ist_kein_spaltenkopf():
    gruende = _verdacht("Kinder:\n[PERSON A], [GEB-DATUM]\nParis, 02.02.2011",
                        platzhalter=["[PERSON A]", "[GEB-DATUM]"])
    assert gruende and not any("GEB-DATUM" in g for _, g in gruende), gruende


# ----------------------------------------------------------------------
# B/NP-11, U1, U2: Versionen und Maße
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert", [
    ("Firmware updated from 1.2.0.4 to 1.2.0.5", "1.2.0.4"),
    ("Upgrade from 2.1.0.3 completed", "2.1.0.3"),
    ("Strahler IP 65, Bestell-Nr. 10.20.30.40", "10.20.30.40"),
    ("IP 44 Leuchte, Position 2.1.3.4", "2.1.3.4"),
])
def test_b_np11_u2_keine_ip(text, wert):
    assert not _stellen(_funde(text), "ip"), _stellen(_funde(text))
    assert not any(wert in t and "IP" in g for t, g in _ausgabe_verdacht(text)), _ausgabe_verdacht(text)


@pytest.mark.parametrize("text", ["Zugriff von 84.123.45.67 auf das Kundenportal",
                                  "Received: from [93.184.21.17] by mx.example.net", "Login from 93.184.21.17"])
def test_b_np11_ip_bleibt(text):
    assert _stellen(_funde(text), "ip"), _stellen(_funde(text))


@pytest.mark.parametrize("text, wert", [
    ("Länge 6.0000 Meter, Breite 3.0000 Meter", "6.0000"),
    ("Zaun 1.2500 lfm", "1.2500"),
    ("Breite 0.9000 Fuß", "0.9000"),
    ("Toleranz 4.6895 ± 0.5 mm", "4.6895"),
])
def test_u1_mass_ausgeschrieben(text, wert):
    assert not _beruehrt(text, wert), _stellen(_funde(text))
    assert not _gemeldet(text, wert), _verdacht(text)


# ----------------------------------------------------------------------
# B/NP-12: Tätigkeit in einer Betriebstabelle ist kein Beruf einer Person
# ----------------------------------------------------------------------
def test_b_np12_betriebstabelle():
    text = ("Tätigkeit\t\tFirma\t\tUmsatz\nDachdecker\t\tBedachungen Achatz GmbH\t\t1,2 Mio. EUR\n"
            "Elektriker\t\tElektro Brunnhuber GmbH\t\t0,8 Mio. EUR")
    assert not _stellen(_funde(text), "beruf"), _stellen(_funde(text))
    text2 = "Branche\t\tTätigkeit\t\tJahresumsatz\nBau\t\tDachdecker\t\t1,2 Mio. EUR"
    assert not _stellen(_funde(text2), "beruf"), _stellen(_funde(text2))


@pytest.mark.parametrize("text, beruf", [
    ("Tätigkeit\t\tFirma\t\tZeitraum\nElektriker\t\tElektro Brunnhuber e.K.\t\t2015 - 2020", "Elektriker"),
    ("Name\t\tTätigkeit\t\tUmsatz\nMaria Pfanzelt\t\tDachdeckerin\t\t1,2 Mio", "Dachdeckerin"),
    ("Angaben zur Tätigkeit\t\tTätigkeit\t\tArbeitgeber\nseit 2014\t\tSpieleentwickler\t\tPixelhaus Studios",
     "Spieleentwickler"),
])
def test_b_np12_beruf_einer_person_bleibt(text, beruf):
    assert _geschwaerzt(text, beruf, "beruf"), _stellen(_funde(text))


# ----------------------------------------------------------------------
# LK-18: Grüne Karte, Grad-Minuten, Plus Code, Seriennummer
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert, kategorie", [
    ("Green card No.: PL/015/0099731", "PL/015/0099731", "vertrag"),
    ("Grüne Karte: D/105/4471208", "D/105/4471208", "vertrag"),
    ("Standort des Fahrzeugs: N 47° 46.205' E 012° 38.115'", "47° 46.205", "standort"),
    ("Lage: 47° 51.367' N, 12° 07.714' E", "47° 51.367", "standort"),
    ("Treffpunkt laut App: 9F4MG3X8+QR", "9F4MG3X8+QR", "standort"),
    ("Wechselrichter SNR 7731904418", "7731904418", "vertrag"),
])
def test_lk18_formen(text, wert, kategorie):
    assert _geschwaerzt(text, wert, kategorie), _stellen(_funde(text))


@pytest.mark.parametrize("text", ["Winkel 45° 30'", "Temperatur 21° 30' Neigung", "Summe 2345+67 EUR",
                                  "Tarif CC+PLUS", "SNR 30 dB"])
def test_lk18_gegenproben(text):
    assert not _stellen(_funde(text)), _stellen(_funde(text))


# ----------------------------------------------------------------------
# Selbstkontrolle: Personenwort im Satz ist kein Etikett; Einheiten hinter Zahlen
# ----------------------------------------------------------------------
def test_mitglied_im_satz_ist_kein_etikett():
    text = "Max Mustermann · Malermeister\nMitglied der Handwerkskammer Berlin"
    aus, ph = _ausgabe(text)
    assert not _gemeldet(aus, "Berlin", platzhalter=ph), _verdacht(aus, platzhalter=ph)
    assert _geschwaerzt("Mitglied\t\tEintritt\t\tFunktion\nNeff\t\t2011\t\tKassier", "Neff", "namen")


# ----------------------------------------------------------------------
# Laufzeit: die neuen Hilfsfunktionen bleiben linear (B/NP-14..16)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("zeile", [
    "Hof Hintermoser beim Stögerbauer der Kölbl Resi ",
    "Geburtsname: Stand\t\t",
    "Weitere Kinder siehe Folgeseite. ",
])
def test_laufzeit_linear(zeile):
    def dauer(n):
        text = zeile * n
        t = time.process_time()
        analysiere_text(text, ALLE, [], [], profil="hoch")
        return time.process_time() - t
    dauer(20)
    klein, gross = min(dauer(100) for _ in range(2)), min(dauer(400) for _ in range(2))
    assert gross < 8 * max(klein, 0.05), (klein, gross)


# ----------------------------------------------------------------------
# B/NP-06: Wochentage als Familiennamen in der Spalte "Name"; B/NP-03, B/NP-04: Gegenproben der neuen Regeln
# ----------------------------------------------------------------------
def test_b_np06_wochentage_in_namensspalte():
    text = ("Name\t\tVorname\t\tGeburtsdatum\nMontag\t\tPeter\t\t12.03.1975\nSonntag\t\tAnna\t\t01.02.1980\n"
            "Freitag\t\tJosef\t\t03.04.1965")
    assert {"Montag", "Sonntag", "Freitag"} <= _stellen(_funde(text), "namen"), _stellen(_funde(text))
    gegen = "Name\t\tTermin\nHuber\t\tMontag\nMaier\t\tFreitag"
    assert not ({"Montag", "Freitag"} & _stellen(_funde(gegen))), _stellen(_funde(gegen))


@pytest.mark.parametrize("text, wert", [
    ("Code der Hausratversicherung: HR-PREMIUM", "HR-PREMIUM"),
    ("Code für die Tarifgruppe Haushalt: TG3", "TG3"),
    ("Code der App-Version: 4.2.1", "4.2.1"),
    ("Versicherer: Signal Iduna, Tarif: KomfortPlus", "KomfortPlus"),
    ("Signal Iduna, Stand: 01.01.2025", "01.01.2025"),
])
def test_b_np03_np04_gegenproben(text, wert):
    assert not any(wert in s for s in _stellen(_funde(text), "zugangsdaten") | _stellen(_funde(text), "profilname")), \
        _stellen(_funde(text))
