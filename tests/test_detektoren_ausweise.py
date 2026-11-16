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


# ----------------------------------------------------------------------
# Review-Befund 11: Kontakt- und Kontozeilen auf E-Mail-Ausdrucken sind keine MRZ (Kleinbuchstaben gelten nur neben
# einem echten Füllzeichen-Lauf als Füllzeichen, eine Zone braucht Dokumentkopf, zwei MRZ-Zeilen oder zwei Prüfziffern;
# die Sichtzone nur mit bestätigten Angaben)
# ----------------------------------------------------------------------
_MAIL_KOPF = ("Von: Maklerbüro Sommer <info@sommer-makler.de>\nAn: Kunde <kunde@example.de>\n"
              "Gesendet: Montag, 13.11.2023 10:15\nBetreff: Ihr neuer Vertrag\n")


def test_kontaktzeilen_eines_mailausdrucks_sind_keine_mrz():
    text = (_MAIL_KOPF + "Ihr neuer Vertrag beginnt am 13.11.2023, die Abbuchung erfolgt zum 13.11.2023.\n"
            "Mit freundlichen Grüßen\nTel 0221 2311137 Fax 0221 2311138\nKto 2311137805 Blz 37040044\n"
            "Ihr Konto 2311137805 BLZ 37040044\nTelefon 0221 2311137 Telefax 0221 2311138")
    assert _treffer(text, "ausweis.mrz") == []


def test_kontaktzeilen_quote_falscher_zonen_ist_null():
    import random
    rng = random.Random(11)
    falsch = 0
    for _ in range(300):
        zeilen = [f"Tel 0221 {rng.randint(10 ** 6, 10 ** 7 - 1)} Fax 0221 {rng.randint(10 ** 6, 10 ** 7 - 1)}",
                  f"Kto {rng.randint(10 ** 9, 10 ** 10 - 1)} Blz {rng.randint(10 ** 7, 10 ** 8 - 1)}",
                  f"Mobil 0171 {rng.randint(10 ** 6, 10 ** 7 - 1)} Tel 089 {rng.randint(10 ** 6, 10 ** 7 - 1)}"]
        falsch += bool(_treffer(_MAIL_KOPF + "\n".join(zeilen), "ausweis.mrz"))
    assert falsch == 0


# ----------------------------------------------------------------------
# Review-Befund 2: vorläufiger Personalausweis (TD2) auf Scans – Randzeichen der Kartenkante, verlesener Zeilenanfang,
# Namenszeile ohne Datenzeile
# ----------------------------------------------------------------------
_TD2 = ("IDD<<BEGIC<<AMRA<<<<<<<<<<<<<<<<<<<<", "C620741523D<<8708265<2506274<<<<<<<0")


def test_td2_mit_randzeichen_der_kartenkante():
    text = "Vorläufiger Personalausweis\n" + _TD2[0] + "\n\\." + _TD2[1]
    paare = {(k, t) for k, t, _, _ in _treffer(text, "ausweis.mrz")}
    assert ("ausweis", _TD2[1]) in paare and ("geburt", "8708265") in paare
    assert ("namen", "BEGIC<<AMRA") in paare


def test_td2_verlesener_zeilenanfang_wird_mitgeschwaerzt():
    # die OCR liest den Anfang der Nummer als Kleinbuchstaben: die Stelle beginnt am Zeilenanfang, das Geburtsdatum
    # kommt aus dem Datumspaar (Geburt + Geschlecht + Ablauf), nicht aus der Zeilenlänge
    text = _TD2[0] + "\nee 10D<<8708265<2506274<<<<<<<0"
    paare = {(k, t) for k, t, _, _ in _treffer(text, "ausweis.mrz")}
    assert ("ausweis", "ee 10D<<8708265<2506274<<<<<<<0") in paare
    assert ("geburt", "8708265") in paare


def test_td2_nummer_aus_dem_datumspaar_und_sichtzone():
    # ein verlesenes Zeichen vor der Nummer verschiebt die Zeile: die Nummer steht 13 Stellen vor dem Geburtsdatum
    text = ("VORLÄUFIGER PERSONALAUSWEIS\nC62074152\nGeburtstag 26.08.1987\n" + _TD2[0] + "\nx" + _TD2[1])
    treffer = _treffer(text, "ausweis.mrz")
    sicht = {(k, t) for k, t, q, _ in treffer if q == "ausweis.mrz.sichtzone"}
    assert ("ausweis", "C62074152") in sicht and ("geburt", "26.08.1987") in sicht


def test_td2_namenszeile_ohne_datenzeile():
    # die OCR (Seitensegmentierung) liefert die Datenzeile nicht: die Namenszeile mit Dokumentkopf allein ist eine Zone
    paare = {(k, t) for k, t, _, _ in _treffer("Vorläufiger Personalausweis\n" + _TD2[0], "ausweis.mrz")}
    assert ("namen", "BEGIC<<AMRA") in paare


def _ocr_dok(zeilen):
    """OCR-Seite aus [(text, x0, y0, x1, y1)] je Zeile (Wörter gleichmäßig über die Zeilenbox verteilt)."""
    try:
        import pymupdf as fitz
    except ImportError:  # ältere PyMuPDF-Versionen
        import fitz
    doc = fitz.open()
    seite = doc.new_page(width=595, height=842)
    woerter = []
    for zi, (text, x0, y0, x1, y1) in enumerate(zeilen):
        breite = (x1 - x0) / max(1, len(text))
        x = x0
        for wi, w in enumerate(text.split(" ")):
            woerter.append((x, y0, x + breite * len(w), y1, w, 0, zi, wi))
            x += breite * (len(w) + 1)
    s = seitenmodell.seite_aufbauen(seite, 0, ocr_woerter=woerter, ocr_quelle="ocr")
    doc.close()
    return seitenmodell.Dokument(None, [s])


def _ocr_treffer(dok, name="ausweis.mrz"):
    funktion = next(e for e in detektoren.REGISTER if e.name == name).funktion
    return [(t.kategorie, dok.text[t.start:t.ende], t.quelle) for t in funktion(dok, Kontext(ALLE, "hoch"))]


def test_td2_bruchstuecke_unter_der_namenszeile_nach_lage():
    dok = _ocr_dok([("VORLÄUFIGER PERSONALAUSWEIS", 120, 100, 300, 112), (_TD2[0], 120, 300, 330, 311),
                    ("J6910900", 120, 316, 175, 327), ("Kopie für die Akte", 120, 420, 230, 431)])
    treffer = _ocr_treffer(dok)
    assert ("namen", "BEGIC<<AMRA", "ausweis.mrz") in treffer
    assert ("ausweis", "J6910900", "ausweis.mrz") in treffer
    assert not any("Kopie" in t for _, t, _ in treffer)


# ----------------------------------------------------------------------
# Review-Befund 13: eine Zonenzeile mit hoher OCR-Box. Ein erster Ansatz verwarf Zeilen, deren Box höher als 3,6
# Zeichenbreiten war ("Schwärzung an falscher Stelle"). Gemessen (eigener Entwicklungskorpus, Generator 1.3) sind
# solche Boxen aber meist echt: schräge Scans und Boxen über zwei Zonenzeilen (3,6 bis 5,3 Zeichenbreiten), und auch
# eine entartete Box (10 Zeichenbreiten) überdeckte die echte Zeile – verworfen blieben Ausweisnummer und
# Geburtsdatum lesbar. Ob die OCR eine Zeile in ein falsches Band setzte, lässt sich im Detektor nicht sicher
# erkennen (Ursache in ocr.py); geschwärzt wird deshalb jede Zonenzeile.
# ----------------------------------------------------------------------
def test_mrz_zeile_mit_hoher_box_wird_geschwaerzt():
    zeile = "8110022<2901271D<<<<<<<<<<<d"
    gut = _ocr_treffer(_ocr_dok([("BUNDESREPUBLIK DEUTSCHLAND", 150, 70, 300, 80), (zeile, 150, 505, 316, 516)]))
    assert ("ausweis", "8110022<2901271D", "ausweis.mrz") in gut
    # Box über zwei Zonenzeilen bzw. schräger Scan: 21,6 pt hoch bei 5,7 pt Zeichenbreite (3,8)
    zwei = _ocr_treffer(_ocr_dok([("IDD<<T220001293<<<<<<<<<<<<<<<", 144, 652, 315, 662),
                                  ("4702151<3011065D<<<<<<<<<<<<<2", 144, 674, 315, 696),
                                  ("HERRMANN<<HEIKE<<<<<<<<<<<<<<<", 144, 674, 315, 696)]))
    assert ("ausweis", "4702151<3011065D<<<<<<<<<<<<<2", "ausweis.mrz") in zwei
    assert ("geburt", "4702151", "ausweis.mrz") in zwei
    # entartete Box (69 pt hoch), die die echte Zeile überdeckt: lieber eine Fläche zu viel als eine Nummer zu wenig
    entartet = _ocr_treffer(_ocr_dok([("IDD<<SCHOLZ<<CLAUDIA<<<<<<<<<<<<<<<<", 118, 321, 435, 339),
                                      ("H444888403D<6607065<2603036<<<<<<<<8", 112, 315, 465, 384)]))
    assert any(k == "ausweis" and t.startswith("H444888403D") for k, t, _ in entartet)
    # auch eine Box im Band des Kartenkopfs wird geschwärzt: ohne weitere Zonenzeilen ist die Fehllage nicht belegt
    # (die Restrisiko-Prüfung liest die Ausgabe neu und meldet eine stehen gebliebene Zone)
    kopf = _ocr_treffer(_ocr_dok([("BUNDESREPUBLIK DEUTSCHLAND", 150, 120, 300, 130),
                                  (zeile, 148, 65, 315, 110)]))   # 45 pt hoch bei 6 pt Zeichenbreite
    assert ("ausweis", "8110022<2901271D", "ausweis.mrz") in kopf


# ----------------------------------------------------------------------
# Review-Befund 9: Zugangsnummer nur auf einer Kartenvorderseite (Kartenkopf als eigene Zeile, Zone einer Karte) oder
# hinter dem Feldnamen – nie eine sechsstellige Zahl mit anderem Feldnamen auf einer Seite, die "Personalausweis" nennt
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "Legitimation nach dem GwG\nArt des Ausweises:\t\tPersonalausweis\nKilometerstand\t\t123456\n"
    "Tarifnummer\t\t310200\nVersicherungssumme (EUR)\t\t250000\nVermittlernummer\t\t104711",
    "Schadenmeldung\nGeschätzte Schadenhöhe\t\t125000\nVersicherungssumme\t\t650000\n"
    "Bitte fügen Sie eine Kopie Ihres Personalausweises bei.",
    "Aufenthaltstitel: unbefristet\nJahresbeitrag\t\t142300\nAgenturnummer\t\t870015",
    "Ausweisart:\nVorläufiger Personalausweis\nSchadennummer\n220415",
])
def test_zugangsnummer_gegenproben(text):
    assert not any(q.endswith("zugangsnummer") for _, _, q, _ in _treffer(text, "ausweis.mrz"))


def test_zugangsnummer_auf_der_kartenvorderseite():
    text = ("BUNDESREPUBLIK DEUTSCHLAND\nPERSONALAUSWEIS · IDENTITY CARD · CARTE D'IDENTITÉ\nName / Surname / Nom\n"
            "MUSTERMANN\n582913")
    assert ("ausweis", "582913") in {(k, t) for k, t, q, _ in _treffer(text, "ausweis.mrz")
                                     if q.endswith("zugangsnummer")}
    # auf dem Scan liest die OCR neben der Nummer Bruchstücke von Unterschrift und Kartenkante
    ocr = "PERSONALAUSWEIS - IDENTITY CARD - CARTE D/IDENTITE\nName / Surname / Nom\nMUSTERMANN\nVe\t\t556841 )"
    assert "556841" in {t for _, t, q, _ in _treffer(ocr, "ausweis.mrz") if q.endswith("zugangsnummer")}
    # mit Feldnamen auch ohne Karte
    assert "582913" in {t for _, t, q, _ in _treffer("Zugangsnummer: 582913", "ausweis.mrz")}
    # Kopie von Vorder- und Rückseite, Kartenkopf unleserlich und Staatscode der Zone verlesen ("IDO<<"): die
    # dreizeilige Zone mit Dokumentart "ID" belegt die Ausweiskarte
    kopie = ("Name / Surname / Nom\nMUSTERMANN\n582913\nIDO<<T220001293<<<<<<<<<<<<<<<\n"
             "6408125<2010315D<<<<<<<<<<<<<4\nMUSTERMANN<<ERIKA<<<<<<<<<<<<<")
    assert "582913" in {t for _, t, q, _ in _treffer(kopie, "ausweis.mrz") if q.endswith("zugangsnummer")}
    # Zeile 1 unleserlich: die Datenzeile mit dem Datumspaar am Anfang ist die TD1-Zeile 2 einer Ausweiskarte;
    # neben der Nummer ein längeres OCR-Bruchstück der Unterschrift in eigener Zelle ("wen")
    karte = ("Name / Surname / Nom\nZEIDLER\nwen\t\t425330\nIDD<<MR7H)JEt\t\tREDE\n"
             "4806299<2708126D<<<<<<<<<<<<<0\nZEIDLER<<FRAUKE<<<<<<<<<<<<<<<")
    assert "425330" in {t for _, t, q, _ in _treffer(karte, "ausweis.mrz") if q.endswith("zugangsnummer")}
    # ... aber nie neben einem Feldnamen in einer anderen Zelle
    feld = karte.replace("wen\t\t425330", "Kilometerstand\t\t425330")
    assert "425330" not in {t for _, t, q, _ in _treffer(feld, "ausweis.mrz") if q.endswith("zugangsnummer")}


def test_mrz_nachbarzeile_mit_verlesenen_fuellzeichen():
    """Schwacher Scan: die OCR liest die Füllzeichen der Datenzeile fast alle als Kleinbuchstaben
    ("7409255<2911168D<e<ca<e<cccach") – neben einer belegten Zonenzeile genügen zwei einzelne Füllzeichen. Allein
    (ohne belegte Nachbarzeile) reicht das nie: eine Kontaktzeile bleibt keine Zone."""
    text = "IDD<<PCYRMJ2380<<<<<<e<eccuuce\n7409255<2911168D<e<ca<e<cccach\n<c<cececn«"
    treffer = {(k, t) for k, t, q, _ in _treffer(text, "ausweis.mrz") if q == "ausweis.mrz"}
    assert ("geburt", "7409255") in treffer
    assert any(k == "ausweis" and t.startswith("7409255<2911168D") for k, t in treffer)
    allein = "Mit freundlichen Grüßen <info@makler.de>\n7409255<2911168D<e<ca<e<cccach"
    assert not [q for _, _, q, _ in _treffer(allein, "ausweis.mrz") if q == "ausweis.mrz"]


# ----------------------------------------------------------------------
# Review-Befund 8: Führerschein nur mit Kartenmerkmalen in EINEM Block (4a/4b mit Datum, plausibles Geburtsdatum in
# Feld 3, Kartenkopf als eigene Zeile oder Klassenliste) – nummerierte Listen auf Kfz-Seiten bleiben unberührt
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    # Angebotsvergleich des Maklers, der das Wort "Führerschein" enthält
    "Angebotsvergleich Kfz-Versicherung\nDie Prüfung des Führerscheins erfolgt bei Abschluss.\n"
    "1. Allianz Kfz Komfort\n2. HUK-COBURG Classic Plus\n3. 01.04.2025 Beginn aller Angebote\n"
    "5. Beiträge ab 389,00 EUR jährlich\n8. Werkstattbindung optional",
    # Schadenablauf eines Versicherers
    "Schadenablauf\nPrüfung des Führerscheins abgeschlossen\n1. Schadenmeldung Allianz Direct\n"
    "2. Gutachten DEKRA Niederlassung\n3. 18.03.2024 Besichtigung durch Gutachter\n"
    "5. 02.04.2024 Zahlung 2.345,67 EUR an die Werkstatt",
    # Deckungssummen und Tarife
    "Fahrer mit Führerschein seit 2005\n1. Tarif Allianz Kfz Premium\n2. Teilkasko Komfort\n"
    "3. 100.000.000 EUR Deckungssumme pauschal\n5. Teilkasko mit 150 EUR Selbstbeteiligung",
    # Checkliste
    "Bitte reichen Sie ein:\n1. Personalausweis\n2. Führerschein\n3. Fahrzeugschein\n5. Kopie der Police",
    # nummerierte Chronologie mit Daten
    "Führerschein\n1. 12.03.2024 Meldung\n2. 14.03.2024 Rückfrage\n3. 18.03.2024 Besichtigung\n5. 02.04.2024 Zahlung",
])
def test_fuehrerschein_gegenproben_kfz_seiten(text):
    assert _treffer(text, "ausweis.fuehrerschein") == []


def test_fuehrerschein_schwaerzt_nur_im_feldblock():
    text = (_FUEHRERSCHEIN + "\nBeiblatt zur Akte\nBitte beachten Sie die Hinweise.\nDie Unterlagen liegen vor.\n"
            "Keine weiteren Angaben.\nWiedervorlage offen.\n3. Beitragsrechnung 2025 Nr. 4711\n"
            "8. Widerrufsbelehrung Allianz\n1. Hinweisblatt Datenschutz")
    paare = {(k, t) for k, t, _, _ in _treffer(text, "ausweis.fuehrerschein")}
    assert ("namen", "MUSTERMANN") in paare and ("geburt", "12.08.1983") in paare
    texte = {t for _, t in paare}
    assert not texte & {"Beitragsrechnung 2025 Nr. 4711", "Widerrufsbelehrung Allianz", "Hinweisblatt Datenschutz"}


@pytest.mark.parametrize("ort", ["FRANKFURT AM MAIN", "HALLE AN DER SAALE", "BAD HOMBURG V. D. HÖHE",
                                 "LANDAU IN DER PFALZ"])
def test_fuehrerschein_geburtsort_mit_ortszusatz(ort):
    """Ortszusätze ("am", "an der", "v. d.") sind auch Funktionswörter – im Geburtsort von Feld 3 kein Grund, die
    ganze Karte zu verwerfen."""
    text = _FUEHRERSCHEIN.replace("MÜNCHEN", ort)
    paare = {(k, t) for k, t, _, _ in _treffer(text, "ausweis.fuehrerschein")}
    assert {("namen", "MUSTERMANN"), ("geburt", "12.08.1983"), ("ort", ort), ("ausweis", "B072RRE2I55")} <= paare


def test_fuehrerschein_kartenkopf_als_eigene_zeile():
    assert aw._kartenmerkmale("/FÜHRERSCHEIN\nREPUBLIK ÖSTERREICH")[0]
    assert aw._kartenmerkmale("FÜHRERSCHEIN   D")[0]
    assert aw._kartenmerkmale("(5FÜHRERSCHEIN\nRZECZPOSPOLITA POLSKA")[0]     # OCR-Bruchstück der Kartenkante davor
    assert not aw._kartenmerkmale("Kopie Führerschein (Vorder- und Rückseite)")[0]
    assert not aw._kartenmerkmale("2. Führerschein")[0]
    assert not aw._kartenmerkmale("1. Personalausweis\n2) FÜHRERSCHEIN")[0]
    assert not aw._kartenmerkmale("Die Prüfung des Führerscheins erfolgt bei Abschluss.")[0]


def test_fuehrerschein_ocr_mit_verlesenen_feldnummern():
    """Gescannter Führerschein (eigener Entwicklungskorpus, Generator 1.3): die OCR klebt "4a." an das Datum
    ("42.01.02.22"), liest "1." als "a1.", die Klasse A1 als "AL" und setzt ein Bruchstück vor den Kartenkopf. Kopf und
    Klassen bleiben Kartenmerkmale, und neben ihnen genügt die Nummer in Feld 5 statt 4a/4b."""
    text = ("(5FÜHRERSCHEIN\nRZECZPOSPOLITA POLSKA\na1. PETERS\n2. EVA-MARIA\n42.01.02.22\n4b. 31.01.37\n"
            "5. 79178257\n5\n\\& AM/AL/B/BE/L\n8. MARKTPLATZ 8,\n3. 28.01.49 HANOI\n4c. Starosta Powiatowy")
    assert aw._kartenmerkmale(text) == (True, True)
    werte = {(k, text[s:e]) for s, e, k in aw.fuehrerschein_felder(text)}
    assert {("namen", "EVA-MARIA"), ("geburt", "28.01.49"), ("ausweis", "79178257")} <= werte
    # ohne 4a/4b genügt Feld 5 nur neben Kartenkopf oder Klassenliste – nie in einer nummerierten Kfz-Liste
    ohne_4 = "1. MÜLLER\n2. HANS\n3. 12.08.1983 MÜNCHEN\n5. B072RRE2I55"
    assert aw.fuehrerschein_felder(ohne_4, mit_wortlaut=False) == []
    mit_kopf = "FÜHRERSCHEIN\n" + ohne_4
    assert ("ausweis", "B072RRE2I55") in {(k, mit_kopf[s:e]) for s, e, k in aw.fuehrerschein_felder(mit_kopf)}
    # Feld 8, von der OCR geteilt: der Straßenname ohne Hausnummer ist trotzdem die Anschrift
    geteilt = mit_kopf + "\n4b. 31.01.2030\n8. FELDKIRCHENER\nWEG 41"
    assert ("strasse", "FELDKIRCHENER") in {(k, geteilt[s:e]) for s, e, k in aw.fuehrerschein_felder(geteilt)}
