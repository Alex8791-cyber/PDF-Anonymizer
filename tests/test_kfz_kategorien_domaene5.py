"""Runde 5, Paket „Kfz, neue Kategorien, Anschriften“: Befunde der Domänen-Durchsicht aller Maklersparten (Nummern
der Befunde aus der Durchsicht). Je Befund die Zeile der Falldatei und eine abgewandelte Schreibweise; dazu
Gegenproben gegen Über-Schwärzung (Beträge mit Tausenderpunkt, Daten, Uhrzeiten, Versionen, Modell- und Produktcodes,
Normen, Zahlen mit Einheit, Feld-Etiketten) und die Selbstkontrolle: Was die Erkennung kennt, meldet sie, wenn es
lesbar bliebe.

Gemeinsame Ursachen (allgemein behoben; Erkennung und Selbstkontrolle lesen dieselben Regeln aus kennungsformen.py):
  * Kfz-Kennzeichen: eine Wertform hinter Kfz-Etiketten (deutsche Form auch mit Leerzeichen um den Bindestrich,
    Sonderformen 03–07 und Ausfuhr, Versicherungskennzeichen 3 Ziffern + 3 Buchstaben, ausländische Formen),
    Komposita auf -kennzeichen mit Fahrzeugbezug als Etikett, die amtlichen Unterscheidungszeichen der Wissensbasis
    (Kompaktform „ROKL2207“, Ausschluss von Modellcodes „KTM RC 390“) – Befunde 19–26, 41, 44;
  * neue Kategorien IP-Adresse, Zugangsdaten, Profil-/Kontoname, Standort und Religion/Konfession, verschleierte
    E-Mail-Adressen und Grundbuchangaben – Befunde 37, 69, 70, 71, 81, 88, 99–103;
  * Anschriften: vierstellige PLZ in Österreich und der Schweiz, ausländische Straßen mit vorangestelltem Straßentyp,
    Straßenklassen mit Nummer („Auf der A 8“), PLZ ⇥⇥ Ort nur mit Straße oder Spaltenköpfen – Befunde 29, 40, 46, 94.
Alle Werte sind erfunden."""

import re

import pymupdf as fitz
import pytest

from anonymisierer import analyse, muster
from anonymisierer.analyse import analysiere_text
from anonymisierer.restrisiko import pruefe_text, restrisiko_pruefen
from test_kennungen_makler import _paare

ALLE = {k for k, _, _, _, an in muster.KATEGORIEN if an}


def _norm(t: str) -> str:
    return re.sub(r"[\s|_.,;:\"'„“”‚‘’»«→()\[\]#/-]", "", t).upper()


def _funde(text, aktive=None, profil=None):
    return analysiere_text(text, ALLE if aktive is None else aktive, [], [], profil=profil)


def _angehakt(funde) -> list:
    return sorted((st["start"], st["ende"]) for f in funde for st in f["stellen"] if st.get("an", True))


def _abgedeckt(text: str, wert: str, funde=None) -> bool:
    """Ist jedes Vorkommen von `wert` in `text` ganz geschwärzt (jedes Zeichen aus Buchstaben/Ziffern in einer
    angehakten Stelle)?"""
    funde = _funde(text) if funde is None else funde
    spannen = _angehakt(funde)
    vorkommen = [m.start() for m in re.finditer(re.escape(wert), text)]
    assert vorkommen, f"{wert!r} steht nicht im Text"
    for a in vorkommen:
        for i in range(a, a + len(wert)):
            if text[i].isalnum() and not any(s <= i < e for s, e in spannen):
                return False
    return True


def _wort_abgedeckt(text: str, wert: str, funde=None) -> bool:
    """Wie _abgedeckt, aber nur für die Vorkommen als ganzes Wort ("rk" in "Konf.: rk", nicht in "Merkmale")."""
    funde = _funde(text) if funde is None else funde
    spannen = _angehakt(funde)
    vorkommen = [m.start() for m in re.finditer(r"(?<![\wäöüß])" + re.escape(wert) + r"(?![\wäöüß])", text)]
    assert vorkommen, f"{wert!r} steht nicht als Wort im Text"
    return all(any(s <= i < e for s, e in spannen) for a in vorkommen for i in range(a, a + len(wert))
               if text[i].isalnum())


def _nicht_geschwaerzt(text: str, wert: str, funde=None) -> bool:
    """Bleibt jedes Vorkommen von `wert` ganz stehen (kein Zeichen in einer angehakten Stelle)?"""
    funde = _funde(text) if funde is None else funde
    spannen = _angehakt(funde)
    for m in re.finditer(re.escape(wert), text):
        if any(s < m.end() and m.start() < e for s, e in spannen):
            return False
    return True


def _gemeldet(text: str, wert: str) -> bool:
    """Meldet die Selbstkontrolle den GANZEN Wert (im ungeschwärzten Text)?"""
    w = _norm(wert)
    return any(w in _norm(v.text) for v in pruefe_text(text))


def _nicht_gemeldet(text: str, wert: str) -> bool:
    """Meldet die Selbstkontrolle keinen Teil des Werts?"""
    w = _norm(wert)
    return not any(_norm(v.text) and (_norm(v.text) in w or w in _norm(v.text)) for v in pruefe_text(text))


def _kategorie(text: str, wert: str, funde=None) -> set:
    funde = _funde(text) if funde is None else funde
    return {f["kategorie"] for f in funde for st in f["stellen"] if st.get("an", True) and wert in st["text"]}


def _tabelle(pfad, zeilen, spalten=(60, 250, 420), groesse=11):
    """PDF mit Textebene wie in der Domänen-Durchsicht (domaene/e2e.py): Zellen "⇥⇥" an festen Spalten."""
    doc = fitz.open()
    seite = doc.new_page(width=595, height=842)
    for zi, zeile in enumerate(zeilen):
        teile = zeile.split("\t\t")
        for si, zelle in enumerate(teile):
            x = spalten[si] if len(teile) > 1 else 60
            seite.insert_text((x, 80 + 18 * zi), zelle, fontsize=groesse, fontname="helv")
    doc.save(pfad)
    doc.close()
    return pfad


def _pdf_funde(pfad, profil="hoch", aktive=None):
    e = analyse.analysiere_pdf(str(pfad), ALLE if aktive is None else aktive, [], [], profil=profil)
    assert e["fehler"] is None
    return e["funde"], {st["text"] for f in e["funde"] for st in f["stellen"] if st.get("an", True)}


def _pdf_gemeldet(pfad) -> set:
    return {_norm(v.text) for v in restrisiko_pruefen(str(pfad))}


# ======================================================================
# Befund 19 (hoch): Versicherungskennzeichen (3 Ziffern + 3 Buchstaben) hinter Kfz-Etiketten
# ======================================================================
VKZ_ETIKETT = [
    ("Versicherungskennzeichen: 435 GHT (Verkehrsjahr 2025/2026, blau)", "435 GHT"),
    ("Versicherungskennzeichen-Nr.: 287 LMV", "287 LMV"),
    ("Ihr Versicherungskennzeichen 2026: 146 RXT", "146 RXT"),
    ("Versicherungskennzeichen: 435GHT", "435GHT"),
    ("Kennzeichen: 519 TWA", "519 TWA"),
    # abgewandelt
    ("Vers.-Kennzeichen: 731 HMP", "731 HMP"),
    ("Versicherungs-Kennzeichen (Verkehrsjahr 2026): 902 KZL", "902 KZL"),
    ("Mopedkennzeichen: 118 FAW", "118 FAW"),
    ("Kennzeichen-Nr. 287 LMV", "287 LMV"),
]


@pytest.mark.parametrize("zeile, wert", VKZ_ETIKETT)
def test_b19_versicherungskennzeichen_hinter_etikett(zeile, wert):
    text = f"Mopedversicherung – Ihr Versicherungsschein\n{zeile}\nVersicherungsbeginn: 01.03.2025"
    funde = _funde(text)
    assert _abgedeckt(text, wert, funde), _paare(funde)
    assert "kfz" in _kategorie(text, wert, funde), _paare(funde)


@pytest.mark.parametrize("zeile, wert", VKZ_ETIKETT)
def test_b19_versicherungskennzeichen_selbstkontrolle(zeile, wert):
    assert _gemeldet(zeile, wert), [(v.text, v.grund) for v in pruefe_text(zeile)]


@pytest.mark.parametrize("zeile, frei", [
    ("Kennzeichen: 100 EUR Selbstbeteiligung", "100 EUR"),
    ("Versicherungskennzeichen: 125 CCM Roller", "125 CCM"),
    ("Kennzeichen-Nr.: 350 KWH Speicher", "350 KWH"),
    ("Versicherungskennzeichen: siehe Anlage 2", "Anlage 2"),
    ("Die Versicherungskennzeichen kosten 2026 nur 54 EUR.", "54 EUR"),
    ("Beitrag für das Verkehrsjahr 2026/2027: 54,90 EUR", "54,90 EUR"),
    ("Selbstbeteiligung 150 CHF je Schaden", "150 CHF"),
])
def test_b19_gegenproben(zeile, frei):
    text = f"Mopedversicherung\n{zeile}"
    assert _nicht_geschwaerzt(text, frei), _paare(_funde(text))


# ======================================================================
# Befund 20: Versicherungskennzeichen im Fließtext hinter „(Versicherungs-)Kennzeichen“
# ======================================================================
VKZ_SATZ = [
    ("Ihr neues Versicherungskennzeichen für das Verkehrsjahr 2026 lautet 712 KRB.", "712 KRB"),
    ("Der E-Scooter des Unfallgegners trug das Versicherungskennzeichen 604 RMX (blau).", "604 RMX"),
    ("anbei erhalten Sie Ihr Versicherungskennzeichen 358 BWZ sowie die Versicherungsbescheinigung.", "358 BWZ"),
    ("Der Mofafahrer (Kennzeichen 604 RMX) fuhr ohne Licht auf dem Gehweg und stieß gegen mein Rad.", "604 RMX"),
    # abgewandelt
    ("Das Versicherungskennzeichen Ihres Mopeds lautet ab März 2026: 245 TKD.", "245 TKD"),
    ("Bitte bringen Sie das neue Kennzeichen 731 HMP bis zum 01.03.2026 an.", "731 HMP"),
]


@pytest.mark.parametrize("zeile, wert", VKZ_SATZ)
def test_b20_versicherungskennzeichen_im_satz(zeile, wert):
    text = f"Sehr geehrte Frau Zehetbauer,\n{zeile}\nMit freundlichen Grüßen"
    funde = _funde(text)
    assert _abgedeckt(text, wert, funde), _paare(funde)
    assert "kfz" in _kategorie(text, wert, funde), _paare(funde)


@pytest.mark.parametrize("zeile, wert", VKZ_SATZ)
def test_b20_selbstkontrolle(zeile, wert):
    assert _gemeldet(zeile, wert), [(v.text, v.grund) for v in pruefe_text(zeile)]


@pytest.mark.parametrize("zeile, frei", [
    ("Das Kennzeichen kostet 2026 nur 120 EUR.", "120 EUR"),
    ("Ihr Versicherungskennzeichen gilt ab 01.03.2026 für 365 Tage.", "365 Tage"),
    ("Roller mit Versicherungskennzeichen, Hubraum 125 CCM.", "125 CCM"),
])
def test_b20_gegenproben(zeile, frei):
    assert _nicht_geschwaerzt(zeile, frei), _paare(_funde(zeile))


# ======================================================================
# Befund 21 (hoch): Versicherungskennzeichen in Tabellenspalten mit Kfz-Kopf
# ======================================================================
@pytest.mark.parametrize("zeilen, werte, frei", [
    (["Kleinkraftrad-Versicherung 2025/2026 – Ihre neuen Kennzeichen",
      "Versicherungsnehmer\t\tKennzeichen\t\tFarbe",
      "Arnulf Zehetbauer\t\t519 TWA\t\tblau",
      "Wiltrud Zehetbauer\t\t520 TWA\t\tblau"], ["519 TWA", "520 TWA"], []),
    (["Bestandsübersicht Kleinfahrzeuge",
      "Fahrzeug\t\tVers.-Kennzeichen\t\tVerkehrsjahr",
      "Mofa Simson S51\t\t388 ZLP\t\t2025/26",
      "E-Scooter Ninebot G2\t\t389 ZLP\t\t2025/26"], ["388 ZLP", "389 ZLP"], ["2025/26", "Verkehrsjahr"]),
    # abgewandelt: Kompaktform in der Spalte
    (["Bestand Mofas",
      "Fahrzeug\t\tVersicherungskennzeichen\t\tBeitrag",
      "Piaggio Ciao\t\t112FKL\t\t54,90 EUR"], ["112FKL"], ["54,90 EUR"]),
])
def test_b21_versicherungskennzeichen_in_spalte(tmp_path, zeilen, werte, frei):
    pdf = _tabelle(tmp_path / "vkz.pdf", zeilen)
    funde, texte = _pdf_funde(pdf)
    for w in werte:
        assert any(_norm(w) == _norm(t) or _norm(w) in _norm(t) for t in texte), (w, _paare(funde))
        assert any(f["kategorie"] == "kfz" and _norm(w) in _norm(f["text"]) for f in funde), _paare(funde)
    for f in frei:
        assert not any(f in t for t in texte), (f, _paare(funde))
    gemeldet = _pdf_gemeldet(pdf)
    for w in werte:
        assert any(_norm(w) in g for g in gemeldet), (w, gemeldet)


# ======================================================================
# Befund 22: Klammerzusatz zwischen Etikett und Wert, „Versicherungsplakette Nr.“, „Kennzeichen-Nr.“
# ======================================================================
@pytest.mark.parametrize("zeile, wert", [
    ("Kennzeichen (Versicherungskennzeichen): 388 ZLP", "388 ZLP"),
    ("Versicherungsplakette Nr. 712 KRB", "712 KRB"),
    ("Kennzeichen-Nr.: 388 ZLP", "388 ZLP"),
    ("Kennzeichen (Mofa): 287 LMV", "287 LMV"),
    # abgewandelt
    ("Kennzeichen (amtlich, Anhänger): RO-KL 22", "RO-KL 22"),
    ("Kennzeichen (Ausland): WGM 4471K", "WGM 4471K"),
    ("Versicherungsplakette: 245 TKD", "245 TKD"),
])
def test_b22_klammer_plakette_kennzeichen_nr(zeile, wert):
    text = f"Mopedversicherung – Ihre Unterlagen für 2026\n{zeile}"
    funde = _funde(text)
    assert _abgedeckt(text, wert, funde), _paare(funde)
    assert _gemeldet(zeile, wert), [(v.text, v.grund) for v in pruefe_text(zeile)]


def test_b22_plakette_ist_kein_name():
    funde = _funde("Mopedversicherung – Ihre Unterlagen für 2026\nVersicherungsplakette Nr. 712 KRB")
    assert not any(f["kategorie"] == "namen" and "plakette" in f["text"].lower() for f in funde), _paare(funde)


@pytest.mark.parametrize("zeile", [
    "Kennzeichen (bitte in Druckbuchstaben): ________",
    "Kennzeichen (falls vorhanden): wird nachgereicht",
])
def test_b22_gegenproben(zeile):
    assert not [f for f in _funde(zeile) if f["kategorie"] in ("kfz", "international", "vertrag")]


# ======================================================================
# Befund 23: ausländische Kennzeichen hinter Zwischenwörtern – der ganze Wert
# ======================================================================
@pytest.mark.parametrize("zeile, wert", [
    ("Kennzeichen des gegnerischen Fahrzeugs: WGM 4471K (PL)", "WGM 4471K"),
    ("Kennzeichen der Zugmaschine: WGM 4471K", "WGM 4471K"),
    ("Kennzeichen vom Auflieger: WGM 2280P", "WGM 2280P"),
    ("Kennzeichen des italienischen Lkw: FX 482 KL", "FX 482 KL"),
    # abgewandelt
    ("Kennzeichen des niederländischen Wohnmobils: 67-BDK-1", "67-BDK-1"),
    ("Kennzeichen des Anhängers aus Frankreich: AB-123-CD", "AB-123-CD"),
])
def test_b23_auslaendisches_kennzeichen_hinter_zwischenwoertern(zeile, wert):
    text = f"Angaben zum Unfallgegner (Ausland)\n{zeile}\nVersicherer des Unfallgegners: PZU SA, Warschau"
    funde = _funde(text)
    assert _abgedeckt(text, wert, funde), _paare(funde)
    assert _gemeldet(zeile, wert), [(v.text, v.grund) for v in pruefe_text(zeile)]


def test_b23_gegenprobe_ohne_wert():
    text = "Angaben zum Unfallgegner\nKennzeichen des Fahrzeugs: wird nachgereicht\nSchadentag: 12.11.2025"
    assert not [f for f in _funde(text) if f["kategorie"] in ("kfz", "international")]


@pytest.mark.parametrize("zeile", [
    # Korpus-Messung s3x (Dokument 078, Kündigung): in der geschwärzten Ausgabe folgt auf das Etikett direkt
    # „AM 29.03.2025“ – die ausländische Form las „AM“ (Versalien der Texterkennung) mit dem Datum als Kennzeichen
    "Ich habe mein Fahrzeug mit dem amtlichen Kennzeichen AM 29.03.2025 verkauft.",
    "ICH HABE MEIN FAHRZEUG MIT DEM AMTLICHEN KENNZEICHEN AM 29.03.2025 VERKAUFT.",
    # abgewandelt
    "Kennzeichen: AM 29.03.2025 abgemeldet",
    "Kfz-Kennzeichen VOM 01.02.24 bis heute ruhend",
])
def test_b23_datum_hinter_kfz_etikett_ist_kein_kennzeichen(zeile):
    datum = re.search(r"\d{1,2}\.\d{2}\.\d{2,4}", zeile).group(0)
    funde = _funde(zeile)
    assert not [f for f in funde if f["kategorie"] in ("kfz", "international")], _paare(funde)
    assert _nicht_gemeldet(zeile, datum), [(v.text, v.grund) for v in pruefe_text(zeile)]
    # Gegenprobe: echte ausländische Kennzeichen hinter demselben Etikett bleiben erkannt
    for wert in ("WGM 4471K", "FX 482 KL"):
        text = zeile.replace(re.search(r"(?:AM|VOM) " + re.escape(datum), zeile).group(0), wert)
        funde = _funde(text)
        assert _abgedeckt(text, wert, funde) and _gemeldet(text, wert), (text, _paare(funde))


# ======================================================================
# Befund 24: ausländische Kennzeichen im Fließtext – mit Länderhinweis geschwärzt, sonst mindestens Verdacht
# ======================================================================
@pytest.mark.parametrize("text, werte", [
    ("Schilderung des Unfallhergangs durch den Versicherungsnehmer:\n"
     "Auf der A 8 Richtung Salzburg wechselte ein polnischer Sattelzug (Zugmaschine WGM 4471K,\n"
     "Auflieger WGM 2280P) ohne zu blinken auf meine Spur und streifte meinen Pkw.", ["WGM 4471K", "WGM 2280P"]),
    ("Schilderung des Unfallhergangs:\n"
     "Ein italienischer Kleintransporter (FX 482 KL) fuhr beim Spurwechsel in meine Fahrerseite.", ["FX 482 KL"]),
    # abgewandelt
    ("Ein tschechischer Pkw (1A2 3456) parkte quer vor der Einfahrt.", ["1A2 3456"]),
    ("Der französische Lkw mit dem Kennzeichen AB-123-CD bog ohne zu blinken ab.", ["AB-123-CD"]),
])
def test_b24_auslaendisches_kennzeichen_im_fliesstext(text, werte):
    funde = _funde(text)
    for w in werte:
        assert _abgedeckt(text, w, funde), (w, _paare(funde))
        assert _gemeldet(text, w), (w, [(v.text, v.grund) for v in pruefe_text(text)])


@pytest.mark.parametrize("text, werte", [
    ("Ein Sattelzug (Zugmaschine WGM 4471K) wechselte die Spur.", ["WGM 4471K"]),
])
def test_b24_ohne_laenderhinweis_verdacht(text, werte):
    for w in werte:
        assert _gemeldet(text, w), (w, [(v.text, v.grund) for v in pruefe_text(text)])


@pytest.mark.parametrize("text, frei", [
    ("Lkw: DAF XF 480 FT", ["XF 480", "DAF"]),
    ("Krad: KTM RC 390; Yamaha YZF-R1; Suzuki GSX-R 750", ["RC 390", "GSX-R 750"]),
    ("Ein polnischer Lkw vom Typ Volvo FH 500 fuhr auf.", ["FH 500"]),
    ("Der italienische Händler lieferte den Scania R 450 mit 450 PS.", ["R 450"]),
    ("Fahrzeug: Mercedes-Benz Sprinter 316 CDI, Baujahr 2019", ["316 CDI"]),
])
def test_b24_gegenproben_modellcodes(text, frei):
    funde = _funde(text)
    for f in frei:
        assert _nicht_geschwaerzt(text, f, funde), (f, _paare(funde))
        assert _nicht_gemeldet(text, f), (f, [(v.text, v.grund) for v in pruefe_text(text)])


# ======================================================================
# Befund 25: Kurzzeit-, rote 06/07- und Ausfuhrkennzeichen; Komposita auf -kennzeichen als Kfz-Etikett
# ======================================================================
SONDERFORMEN = [
    ("Kurzzeitkennzeichen: RO-04 1287, gültig bis 21.11.2025", "RO-04 1287"),
    ("Fahrzeug: Oldtimer Mercedes-Benz W 123, rotes Oldtimerkennzeichen RO-07 451", "RO-07 451"),
    ("Ausfuhrkennzeichen: HH 4711 A, Ablaufdatum 30.11.2025", "HH 4711 A"),
    ("Kennzeichen: M-04 2290 (Kurzzeitkennzeichen, 5 Tage)", "M-04 2290"),
    ("Händlerkennzeichen: RO-06 3315, Versicherungsbeginn 01.01.2026", "RO-06 3315"),
    # abgewandelt
    ("Saisonkennzeichen: M-AB 123 (04-10)", "M-AB 123"),
    ("Wechselkennzeichen: RO-W 77", "RO-W 77"),
    ("Exportkennzeichen: B 1234 C", "B 1234 C"),
    ("Überführung mit dem roten Kennzeichen TS-06 118 am 12.11.2025", "TS-06 118"),
]


@pytest.mark.parametrize("zeile, wert", SONDERFORMEN)
def test_b25_sonderformen(zeile, wert):
    text = f"Antrag Kfz-Haftpflicht für Überführungsfahrten\n{zeile}"
    funde = _funde(text)
    assert _abgedeckt(text, wert, funde), _paare(funde)
    assert "kfz" in _kategorie(text, wert, funde), _paare(funde)
    assert _gemeldet(zeile, wert), [(v.text, v.grund) for v in pruefe_text(zeile)]


@pytest.mark.parametrize("zeile, frei", [
    ("Gefahrgutkennzeichen: 33 1203", "33 1203"),
    ("Prüfkennzeichen: 0123 4567", "0123 4567"),
    ("Qualitätskennzeichen: DIN 1234", "DIN 1234"),
    ("CE-Kennzeichen 0197 auf dem Typenschild", "0197"),
])
def test_b25_gegenproben_kennzeichen_ohne_fahrzeugbezug(zeile, frei):
    text = f"Sachversicherung – Angaben zum Gerät\n{zeile}"
    funde = _funde(text)
    assert not any(f["kategorie"] == "kfz" and frei in f["text"] for f in funde), _paare(funde)


# ======================================================================
# Befund 26: Kennzeichen mit Leerzeichen um den Bindestrich, mit Gedankenstrich und klein geschrieben
# ======================================================================
@pytest.mark.parametrize("zeile, werte", [
    ("Hallo Herr Seidlmeier, mein Auto (RO - KL 2207) wurde gestern angefahren.", ["RO - KL 2207"]),
    ("Der andere Fahrer hat einen Zettel mit seinem Kennzeichen hinterlassen: ro-xt 913.", ["ro-xt 913"]),
    ("Mein Auto, RO – KL 2207, stand ordnungsgemäß in der Parkbucht.", ["RO – KL 2207"]),
    ("das Kennzeichen von dem anderen war ro xt 913, glaube ich.", ["ro xt 913"]),
    # abgewandelt
    ("Mein Wagen (m - ab 123) wurde auf dem Parkplatz beschädigt.", ["m - ab 123"]),
    ("Der Unfallgegner fuhr einen roten Golf mit dem Kennzeichen B–XY 987.", ["B–XY 987"]),
])
def test_b26_laienschreibweise(zeile, werte):
    text = f"Betreff: Parkschaden an meinem Auto\n{zeile}"
    funde = _funde(text)
    for w in werte:
        assert _abgedeckt(text, w, funde), (w, _paare(funde))
        assert "kfz" in _kategorie(text, w, funde), (w, _paare(funde))
        assert _gemeldet(zeile, w), (w, [(v.text, v.grund) for v in pruefe_text(zeile)])


@pytest.mark.parametrize("zeile, frei", [
    ("Bitte lesen Sie Seite 2 – 4 der Bedingungen.", "2 – 4"),
    ("das auto war ca 15 jahre alt und hatte 120 tkm.", "ca 15"),
    ("Die Sparte S - BU 2024 wird ab Januar neu berechnet.", "BU 2024"),
    ("das ging für ca 15 Euro weg.", "ca 15"),
    ("Mein Auto stand bis zu 20 Minuten im Halteverbot.", "zu 20"),
])
def test_b26_gegenproben(zeile, frei):
    funde = _funde(zeile)
    assert not any(f["kategorie"] == "kfz" for f in funde), _paare(funde)
    assert _nicht_geschwaerzt(zeile, frei, funde), _paare(funde)


def test_b26_ocr_geteilte_ziffern_hinter_etikett():
    """Korpus-Messung s1 (Dokument 038, Scan): die Texterkennung liest „F-YY 5311“ als „F-YY 531 1“ – hinter einem
    Kfz-Etikett gehört die abgetrennte Ziffergruppe dazu (höchstens vier Ziffern, keine Einheit dahinter)."""
    text = "Mein Kennzeichen ist F-YY 531 1, die Fahrzeug-Identnummer folgt."
    funde = _funde(text)
    assert _abgedeckt(text, "F-YY 531 1", funde), _paare(funde)
    text = "Kennzeichen: M-AB 12 3 km vor der Ausfahrt"
    funde = _funde(text)
    assert _abgedeckt(text, "M-AB 12", funde) and _nicht_geschwaerzt(text, "3 km", funde), _paare(funde)


# ======================================================================
# Befund 41: Kompaktform ohne Trenner mit amtlichem Unterscheidungszeichen und Kfz-Wort davor
# ======================================================================
@pytest.mark.parametrize("zeile, werte", [
    ("Risiko: Pkw ROKL2207, VW Golf VIII, Vollkasko SB 300 / TK SB 150", ["ROKL2207"]),
    ("Risiko: Anhänger ROKL22, Böckmann TPV, nur Haftpflicht", ["ROKL22"]),
    ("Risiko: Krad ROXT913, Yamaha MT-07, Teilkasko SB 150", ["ROXT913"]),
    # abgewandelt
    ("Fahrzeuge: Pkw MAB1234E (Elektro), Wohnmobil BGLHK77", ["MAB1234E", "BGLHK77"]),
    ("Kfz-Kennzeichen ROKL2207, Halter Arnulf Zehetbauer", ["ROKL2207"]),
])
def test_b41_kompaktform(zeile, werte):
    text = f"Kundenakte (Export Maklerverwaltungsprogramm) – Kfz-Verträge\n{zeile}"
    funde = _funde(text)
    for w in werte:
        assert _abgedeckt(text, w, funde), (w, _paare(funde))
        assert "kfz" in _kategorie(text, w, funde), (w, _paare(funde))
        assert _gemeldet(zeile, w), (w, [(v.text, v.grund) for v in pruefe_text(zeile)])


@pytest.mark.parametrize("zeile, frei", [
    ("Pkw: Mercedes GLC300, Audi RS6, BMW X5", ["GLC300", "RS6"]),
    ("Tarif VK300, SB150, TK150 – Beitrag 612,40 EUR", ["VK300", "SB150", "TK150"]),
    ("Artikelnummer XQZ123 im Warenkorb", ["XQZ123"]),
])
def test_b41_gegenproben(zeile, frei):
    funde = _funde(zeile)
    for f in frei:
        assert not any(fu["kategorie"] == "kfz" and f in fu["text"] for fu in funde), _paare(funde)


# ======================================================================
# Befund 44: Modellcodes sind keine Kennzeichen (amtliche Liste, Hubraum mit Dezimalteil)
# ======================================================================
MODELLE = [
    ("Pkw: Toyota C-HR 1.8 Hybrid; Honda CR-V 2.0 i-MMD", ["C-HR 1", "CR-V 2"]),
    ("Krad: KTM RC 390; Yamaha YZF-R1; Suzuki GSX-R 750", ["RC 390", "YZF-R1", "GSX-R 750"]),
    ("Lkw: DAF XF 480 FT", ["XF 480"]),
    ("Pkw: Honda HR-V 1.5 e:HEV; Nissan GT-R 3.8 V6; Renault ZOE R135", ["HR-V 1", "GT-R 3", "ZOE R135"]),
    ("Krad: Yamaha YZF-R125; Suzuki GSX-S 1000", ["YZF-R125", "GSX-S 1000"]),
    ("Lkw: DAF CF 450 FT", ["CF 450"]),
]


@pytest.mark.parametrize("zeile, frei", MODELLE)
def test_b44_modellcodes_bleiben(zeile, frei):
    text = f"Fahrzeugübersicht für das Flottenangebot\n{zeile}"
    funde = _funde(text)
    assert not [f for f in funde if f["kategorie"] == "kfz"], _paare(funde)
    for f in frei:
        assert _nicht_geschwaerzt(text, f, funde), (f, _paare(funde))


@pytest.mark.parametrize("zeile, frei", MODELLE)
def test_b44_selbstkontrolle_ohne_fehlverdacht(zeile, frei):
    for f in frei:
        assert _nicht_gemeldet(zeile, f), (f, [(v.text, v.grund) for v in pruefe_text(zeile)])


def test_b44_geraete_id_ist_kein_kennzeichen():
    funde = _funde("Willkommen im Telematik-Tarif, Ihr Stecker ist aktiviert.\nGeräte-ID: TLX-PW48-HX73")
    assert not any(f["kategorie"] == "kfz" for f in funde), _paare(funde)


@pytest.mark.parametrize("zeile, wert", [
    ("Fahrzeug: VW Golf RO-KL 2207, Erstzulassung 03/2019", "RO-KL 2207"),
    ("Toyota C-HR, Kennzeichen RO-KL 2207", "RO-KL 2207"),
    ("Fahrzeug: Honda CR-V, RO-AB 123", "RO-AB 123"),
    ("Der Wagen mit dem Kennzeichen GT-R 3 stand vor der Tür.", "GT-R 3"),
    ("Unfallgegner: Opel Corsa, B-XY 987", "B-XY 987"),
])
def test_b44_echte_kennzeichen_bleiben_erkannt(zeile, wert):
    funde = _funde(zeile)
    assert _abgedeckt(zeile, wert, funde), _paare(funde)


# ======================================================================
# Befund 46: Straßenklassen mit Nummer („Auf der A 8“) sind keine Anschrift
# ======================================================================
@pytest.mark.parametrize("zeile, frei", [
    ("Auf der A 8 Richtung Salzburg kam es zum Stau.", "A 8"),
    ("Auf der A 94 bei km 12,5 kam es zum Auffahrunfall; Umleitung über die St 2089.", "A 94"),
    ("Auf der B 15 kurz vor Rosenheim flog ein Stein gegen die Windschutzscheibe.", "B 15"),
    ("Unfallort: Auf der A 99, Höhe Ausfahrt Haar", "A 99"),
    ("Ich fuhr auf der B 304 Richtung Wasserburg.", "B 304"),
    # abgewandelt
    ("Auf der L 2080 zwischen Haag und Albaching geriet ich ins Schleudern.", "L 2080"),
    ("Auf der K 12 kam mir ein Traktor entgegen.", "K 12"),
    ("Auf der BAB 9 bei Kilometer 112 platzte ein Reifen.", "BAB 9"),
    ("Auf der E 45 Richtung Süden war Stau.", "E 45"),
    # Korpus-Messung s3x (Unfallbericht): hinter „Unfallort:“ weder Straße noch Ort („BAB“ wurde [PLZ ORT])
    ("Unfallort: BAB 9, km 381,2", "BAB 9"),
])
def test_b46_strassenklasse_ist_keine_anschrift(zeile, frei):
    text = f"Unfallschilderung (ohne Personenangaben)\n{zeile}"
    funde = _funde(text)
    assert not [f for f in funde if f["kategorie"] == "strasse"], _paare(funde)
    assert _nicht_geschwaerzt(text, frei, funde), _paare(funde)
    assert _nicht_gemeldet(zeile, frei), [(v.text, v.grund) for v in pruefe_text(zeile)]


@pytest.mark.parametrize("zeile, wert", [
    ("Wohnhaft Am Bahnhof 3 in Haag", "Am Bahnhof 3"),
    ("Anschrift: Auf der Heide 12, 83527 Haag", "Auf der Heide 12"),
    ("Herr Max Mustermann, An der Alten Mühle 4, 83512 Wasserburg", "An der Alten Mühle 4"),
    ("Frau Erika Muster, Auf dem Berg 7, 83043 Bad Aibling", "Auf dem Berg 7"),
])
def test_b46_gegenproben_echte_strassen(zeile, wert):
    funde = _funde(zeile)
    assert _abgedeckt(zeile, wert, funde), _paare(funde)


# ======================================================================
# Befund 29: vierstellige PLZ (Österreich, Schweiz) mit Ort hinter einer Straße oder mit Ort der Nachbarländer
# ======================================================================
@pytest.mark.parametrize("zeile, werte", [
    ("Frau Gesche Oberrauch, Seestrasse 12, 8002 Zürich", ["8002 Zürich"]),
    ("Halter des zweiten Fahrzeugs: Herr Okke Lindlbauer, Museumstraße 7, 6020 Innsbruck", ["6020 Innsbruck"]),
    ("der Unfallgegner, Herr Ing. Volkhard Lindlbauer aus 4040 Linz (Hauptstraße 44/3/12),", ["4040 Linz"]),
    # abgewandelt
    ("Herr Notker Rieplhuber, Bahnhofstrasse 45, 3011 Bern", ["3011 Bern"]),
    ("Die Halterin ist wohnhaft in 5020 Salzburg.", ["5020 Salzburg"]),
    ("Zustellung an: Kirchgasse 3, 6900 Bregenz", ["6900 Bregenz"]),
])
def test_b29_plz4_ausland(zeile, werte):
    text = f"Angaben zur Unfallgegnerin\n{zeile}"
    funde = _funde(text)
    for w in werte:
        assert _abgedeckt(text, w, funde), (w, _paare(funde))
        assert _gemeldet(zeile, w), (w, [(v.text, v.grund) for v in pruefe_text(zeile)])


@pytest.mark.parametrize("zeile, frei", [
    ("Seit 2019 Mitglied, Bestand 2025 Hamburg und Umland", "2025 Hamburg"),
    ("Hauptstraße 12, 1500 Euro Anzahlung geleistet", "1500 Euro"),
    ("Hauptstraße 12, 2026 Umzug nach Berlin geplant", "2026 Umzug"),
    ("Kostenstelle 4711 Vertrieb, Abteilung 3020 Schaden", "4711 Vertrieb"),
])
def test_b29_gegenproben(zeile, frei):
    funde = _funde(zeile)
    assert _nicht_geschwaerzt(zeile, frei, funde), _paare(funde)


@pytest.mark.parametrize("zeile, frei", [
    # Orte der Nachbarländer, die zugleich deutsche Wörter sind (daten/orte_at_ch_mehrdeutig.txt), mitten im Satz
    ("Ihrem Bonuskonto wurden 5000 Meilen gutgeschrieben.", "5000 Meilen"),
    ("Nach 1500 Meilen Fahrt fiel die Klimaanlage aus.", "1500 Meilen"),
    ("Sturmschaden im Forst: 1200 Eschen umgestürzt.", "1200 Eschen"),
    ("Lieferung von 1200 Planken für die Terrasse", "1200 Planken"),
    ("Der Restbetrag von 1500 Zug um Zug gegen Übergabe des Fahrzeugs.", "1500 Zug"),
    # ein Ortsname als Anfang eines Kompositums
    ("Rechnung 4711 Bern-Express Kurier", "4711 Bern-Express"),
    ("Lieferung von 1200 Muri-Platten", "1200 Muri-Platten"),
])
def test_b29_ortsname_als_wort_ist_keine_anschrift(zeile, frei):
    funde = _funde(zeile)
    assert _nicht_geschwaerzt(zeile, frei, funde), _paare(funde)
    assert _nicht_gemeldet(zeile, frei), [(v.text, v.grund) for v in pruefe_text(zeile)]


@pytest.mark.parametrize("zeile, wert", [
    ("Frau Gesche Oberrauch, 6300 Zug", "6300 Zug"),           # mehrdeutiger Ort am Ende der Angabe
    ("Frau Gesche Oberrauch, Seestrasse 12, 6300 Zug", "6300 Zug"),
    ("Herr Kurt Bühler, 8706 Meilen, Schweiz", "8706 Meilen"),
    ("Zustellanschrift: CH-6300 Zug", "CH-6300 Zug"),
    ("Herr Okke Lindlbauer, 4540 Bad Hall", "4540 Bad Hall"),   # „Bad“ allein ist ein Wort, „Bad Hall“ ein Ort
    ("Kurhausstraße 3, 4820 Bad Ischl", "4820 Bad Ischl"),
    ("aus 6060 Hall in Tirol", "6060 Hall in Tirol"),           # ein mehrteiliger Ort ganz
    ("Hauptplatz 3, 8600 Bruck an der Mur", "8600 Bruck an der Mur"),
    # ein Anschrift-Etikett direkt davor trägt auch den mehrdeutigen Ort mitten im Satz
    ("Die Halterin ist wohnhaft in 8706 Meilen am Zürichsee.", "8706 Meilen"),
    ("Zustellanschrift: 6300 Zug, bitte nur werktags", "6300 Zug"),
])
def test_b29_orte_der_nachbarlaender(zeile, wert):
    text = f"Angaben zur Unfallgegnerin\n{zeile}"
    funde = _funde(text)
    assert _abgedeckt(text, wert, funde), _paare(funde)
    assert _gemeldet(zeile, wert), [(v.text, v.grund) for v in pruefe_text(zeile)]


# ======================================================================
# Befund 40: ausländische Straßen mit vorangestelltem Straßentyp, sechsstellige PLZ mit Länderhinweis
# ======================================================================
@pytest.mark.parametrize("text, werte", [
    ("Angaben zum Fahrer des Lkw (Unfallverursacher):\n"
     "Ionuț-Cristian Bălănescu, wohnhaft Str. Memorandumului nr. 27,\n"
     "400114 Cluj-Napoca, Rumänien, Tel. +40 744 123 456", ["Memorandumului nr. 27", "400114 Cluj-Napoca"]),
    ("Anschrift: Strada Avram Iancu 14, 500058 Brașov, Rumänien", ["Avram Iancu 14", "500058 Brașov"]),
    # abgewandelt
    ("Adresse des Unfallgegners: Calea Victoriei nr. 12, 010061 București, Rumänien",
     ["Victoriei nr. 12", "010061 București"]),
    ("Anschrift: bul. Vitosha 15, 1000 Sofia, Bulgarien", ["Vitosha 15", "1000 Sofia"]),
])
def test_b40_auslaendische_strasse_vorangestellt(text, werte):
    funde = _funde(text)
    for w in werte:
        assert _abgedeckt(text, w, funde), (w, _paare(funde))
        assert _gemeldet(text, w), (w, [(v.text, v.grund) for v in pruefe_text(text)])


@pytest.mark.parametrize("zeile, frei", [
    ("Artikel 123456 Bohrmaschine, Preis 89,00 EUR", "123456 Bohrmaschine"),
    ("Bestellnummer 400114 Ersatzteil", "400114 Ersatzteil"),
])
def test_b40_gegenproben(zeile, frei):
    funde = _funde(zeile)
    assert not any(f["kategorie"] in ("international", "plzort") for f in funde), _paare(funde)


# ======================================================================
# Befund 94: PLZ ⇥⇥ Ort über einen Spaltentrenner nur mit Straße davor oder Spaltenköpfen PLZ/Ort
# ======================================================================
KUNDENLISTE = ["Kundenliste – Export Maklerverwaltung (Filter: PLZ 83*, Stand 12.11.2026)",
               "Kd.-Nr.\t\tName\t\tVorname\t\tStraße\t\tPLZ\t\tOrt\t\tGeb.-Dat.\t\tTelefon",
               "10471\t\tRuhstorfer\t\tKunigunde\t\tUntere Bachgasse 5\t\t83512\t\tWasserburg a. Inn\t\t21.06.1949"
               "\t\t08071 12345",
               "10472\t\tKraxenberger\t\tWendelin\t\tHölzlweg 12\t\t83626\t\tValley\t\t14.05.1971\t\t08024 47119"]


def test_b94_kundennummer_ist_keine_plz():
    assert muster.finde_plz_ort("10471\t\tRuhstorfer\t\tKunigunde") == []
    text = "\n".join(KUNDENLISTE)
    plz = [st for st in muster.finde_plz_ort_stellen(text)]
    assert not any("10471" in text[s:e] or "10472" in text[s:e] for s, e in plz), [text[s:e] for s, e in plz]
    assert any(text[s:e].startswith("83512") for s, e in plz), [text[s:e] for s, e in plz]


def test_b94_kundenliste_im_pdf(tmp_path):
    pdf = _tabelle(tmp_path / "kunden.pdf", KUNDENLISTE, spalten=(30, 72, 140, 192, 290, 322, 410, 468),
                   groesse=7)
    funde, texte = _pdf_funde(pdf)
    assert not any(f["kategorie"] == "plzort" and ("10471" in f["text"] or "Ruhstorfer" in f["text"])
                   for f in funde), _paare(funde)
    for w in ("10471", "Ruhstorfer", "83512"):
        assert any(w in t for t in texte), (w, _paare(funde))


def test_b94_hausnummernbereich_und_verrutschte_spalten():
    """Korpus-Messung s9x (Dokument 072, Excel-Bestandsliste als Scan): die Texterkennung zieht laufende Nummer und
    Namen in eine Zelle, die Zellen verrutschen gegen den Kopf. Vor der PLZ-Zelle steht eine Straße mit
    Hausnummernbereich („Am Stadtpark 33-35“) – das genügt; der verrutschte Kopf („Straße“ über der PLZ) zählt nicht
    dagegen."""
    text = ("Nr.\t\tName\t\tVorname\t\tGeb.\t\tStraße\t\tPLZ Ort\t\tTelefon\n"
            "37 Strauß\t\tTill\t\t02.11.80\t\tAm Stadtpark 33-35\t\t76829\t\tLandau in der Pfalz\t\t06341/9925 91")
    plz = [text[s:e] for s, e in muster.finde_plz_ort_stellen(text)]
    assert "76829\t\tLandau in der Pfalz" in plz, plz


# ======================================================================
# Befund 37: Standort/Koordinaten (Dezimalgrad-Paar, Grad/Minuten/Sekunden)
# ======================================================================
@pytest.mark.parametrize("zeile, werte", [
    ("Standort (GPS): 47.85612, 12.12857 – Fahrzeug RO-VL 77", ["47.85612", "12.12857"]),
    ("Unfallort laut eCall: 47°51'22.0\"N 12°07'42.9\"E", ["47°51'22.0\"N", "12°07'42.9\"E"]),
    # abgewandelt
    ("Koordinaten: 48.137154, 11.576124", ["48.137154", "11.576124"]),
    ("Position des Fahrzeugs: 52.5200 N, 13.4050 O", ["52.5200 N", "13.4050 O"]),
    ("Breitengrad 47.85612, Längengrad 12.12857", ["47.85612", "12.12857"]),
])
def test_b37_standort(zeile, werte):
    text = f"Automatische Unfallmeldung (Telematik-Tarif)\n{zeile}"
    funde = _funde(text)
    for w in werte:
        assert _abgedeckt(text, w, funde), (w, _paare(funde))
        assert "standort" in _kategorie(text, w, funde), (w, _paare(funde))
        assert _gemeldet(zeile, w), (w, [(v.text, v.grund) for v in pruefe_text(zeile)])


@pytest.mark.parametrize("zeile, frei", [
    ("Schadenhöhe 12.500, Selbstbeteiligung 1.500, Beitrag 1.234,56 EUR", "12.500"),
    ("Version 4.18, Firmware 2.31.1004", "4.18"),
    ("Temperatur 47.5 Grad, Luftfeuchte 12.1 %", "47.5"),
    ("Messwert 12.12857 laut Protokoll", "12.12857"),
    ("Werte 147.85612, 212.12857 aus der Tabelle", "147.85612"),
    ("Kontostand 47.856,12 EUR, Zinsen 12.128,57 EUR", "47.856,12"),
])
def test_b37_gegenproben(zeile, frei):
    funde = _funde(zeile)
    assert not any(f["kategorie"] == "standort" for f in funde), _paare(funde)
    assert _nicht_geschwaerzt(zeile, frei, funde), _paare(funde)


# ======================================================================
# Befunde 69, 100: Zugangsdaten (Benutzer, Kennung, Kennwort, PIN, Aktivierungscode)
# ======================================================================
ZUGANG = [
    ("Ihr Zugang zum Kundenportal \"MeineVersicherung\"\nBenutzerkennung: zwackelq\nIhr Aktivierungscode: 7HXK-92LQ\n"
     "Der Code ist 14 Tage gültig.", ["zwackelq", "7HXK-92LQ"]),
    ("Zugangsdaten für die Service-App\nIhre Zugangskennung: brezelg\nFreischaltcode: QM7Z-K4XR",
     ["brezelg", "QM7Z-K4XR"]),
    ("Ihre Zugangsdaten zum Kundenportal:\nBenutzer: k.hoffmeister\nKennwort: Sommer2024!",
     ["k.hoffmeister", "Sommer2024!"]),
    ("Ihre Zugangsdaten\nBenutzerkennung: zwackel1959\nBenutzerkennung (alt): hoffk7\nAktivierungscode: 48213957",
     ["zwackel1959", "hoffk7", "48213957"]),
    # abgewandelt
    ("Online-Antrag, elektronisch unterschrieben\nBenutzername: maxmuster82", ["maxmuster82"]),
    ("Passwort: Gx7#kP2!q\nPIN: 4711", ["Gx7#kP2!q", "4711"]),
    ("Ihr Kennwort für das Kundenportal lautet: Sommer2024! Bitte ändern Sie es.", ["Sommer2024!"]),
    ("Login: m.zwackel / Initialpasswort: Wh8tz-Lm2", ["m.zwackel", "Wh8tz-Lm2"]),
    ("Ihr Registrierungscode lautet: 8KQ2-PL4M.", ["8KQ2-PL4M"]),
]


@pytest.mark.parametrize("text, werte", ZUGANG)
def test_b69_b100_zugangsdaten(text, werte):
    funde = _funde(text)
    for w in werte:
        assert _abgedeckt(text, w, funde), (w, _paare(funde))
        assert "zugangsdaten" in _kategorie(text, w, funde), (w, _paare(funde))
        assert _gemeldet(text, w), (w, [(v.text, v.grund) for v in pruefe_text(text)])


def test_b69_b88_kurze_werte_nur_hinter_etikett():
    """Wie die Kartenprüfnummer gelten eine PIN und ein Kirchensteuermerkmal nur hinter ihrem Etikett: dieselben
    Zeichen anderswo im Dokument („4711 Cent“, „Seite 4711“, „Kennung rk 12“) werden nicht mitgeschwärzt."""
    text = "Ihre Zugangsdaten\nPIN: 4711\nBitte überweisen Sie 4711 Cent bis Seite 4711."
    spannen = _angehakt(_funde(text))
    pin = text.index("4711")
    assert any(a <= pin < e for a, e in spannen), spannen
    for anderswo in [m.start() for m in re.finditer("4711", text)][1:]:
        assert not any(a <= anderswo < e for a, e in spannen), (anderswo, spannen)
    text = "Konf.: rk\nKennung rk 12 laut Liste"
    spannen = _angehakt(_funde(text, aktive=muster.PROFILE["maximal"]["aktive"], profil="maximal"))
    assert any(a <= 7 < e for a, e in spannen) and not any(a <= text.index("rk 12") < e for a, e in spannen)


@pytest.mark.parametrize("text", [
    "Passwort vergessen? Klicken Sie auf „Neues Passwort anfordern“.",
    "Kennwort: wird separat per Post zugesandt",
    "PIN: siehe separates Schreiben",
    "Benutzername: Ihre E-Mail-Adresse",
    "Das Benutzerhandbuch finden Sie auf Seite 12.",
    "Kennwortregeln: mindestens 8 Zeichen, eine Ziffer",
    "Die PIN erhalten Sie in einem gesonderten Brief.",
    "Benutzer: Herr Max Mustermann",
    "Passwort ändern | Abmelden | Hilfe",
])
def test_b69_b100_gegenproben(text):
    funde = _funde(text)
    assert not [f for f in funde if f["kategorie"] == "zugangsdaten"], _paare(funde)


# ======================================================================
# Befunde 70, 99: Profil- und Kontonamen (@-Name, Plattform-Etiketten, Messenger)
# ======================================================================
PROFIL = [
    ("Verkäufer auf Kleinanzeigen, Nutzername: rumpelmayr_hilde\nMein eBay-Mitgliedsname: hilde.rumpel57\n"
     "Profilname auf Vinted: HildeR1957", ["rumpelmayr_hilde", "hilde.rumpel57", "HildeR1957"]),
    ("Kleinanzeigen-Profil: zeitlhofer_korbi\neBay-Name: korbinian.z84\nNutzer-Name bei Vinted: KorbiZ1984",
     ["zeitlhofer_korbi", "korbinian.z84", "KorbiZ1984"]),
    ("Erreichbarkeit des Kunden\nTelegram: t.me/lenchen_wiese82\nSnapchat: lenchenwiese\n"
     "Signal-Benutzername: lenchen.82", ["lenchen_wiese82", "lenchenwiese", "lenchen.82"]),
    ("Kontaktwege laut Kundenbogen\nTelegram-Name: korbi_zeitl84\nSnapchat-Name: korbizeitl\nSignal: korbi.84",
     ["korbi_zeitl84", "korbizeitl", "korbi.84"]),
    ("Kontakt: Instagram @lena.wiesengrund, WhatsApp +49 151 23456789", ["@lena.wiesengrund"]),
    # abgewandelt
    ("TikTok: @korbi_zeitl84 – bitte nur dort anschreiben", ["@korbi_zeitl84"]),
    ("Der Betrüger nannte sich auf Kleinanzeigen „Nutzername: sonnenschein_77“.", ["sonnenschein_77"]),
]


@pytest.mark.parametrize("text, werte", PROFIL)
def test_b70_b99_profilnamen(text, werte):
    funde = _funde(text)
    for w in werte:
        assert _abgedeckt(text, w, funde), (w, _paare(funde))
        assert "profilname" in _kategorie(text, w, funde), (w, _paare(funde))
        assert _gemeldet(text, w), (w, [(v.text, v.grund) for v in pruefe_text(text)])


def test_b99_plattform_ist_kein_name():
    funde = _funde("Kontakt: Instagram @lena.wiesengrund, WhatsApp +49 151 23456789")
    assert not any(f["kategorie"] == "namen" and "Instagram" in f["text"] for f in funde), _paare(funde)


def test_b70_snapchat_gegenprobe_kundenbogen_kein_name():
    funde = _funde("Kontaktwege laut Kundenbogen\nTelegram-Name: korbi_zeitl84")
    assert not any(f["kategorie"] == "namen" and "Kundenbogen" in f["text"] for f in funde), _paare(funde)


@pytest.mark.parametrize("text, frei", [
    ("Telegram: nein\nSignal: nicht vorhanden\nSnapchat: keine Angabe", ["nein", "nicht vorhanden", "keine"]),
    ("WhatsApp: +49 151 23456789", []),
    ("Kontakt über Signal möglich, Instagram nutzt der Kunde nicht.", ["Signal", "Instagram"]),
    ("E-Mail: lena.wiesengrund@web.de", []),
    ("Preis @ 5 EUR je Stück; Treffen @ Büro", ["5 EUR", "Büro"]),
    # Korpus-Messung s3x (Schreibmaschinen-Scan): ein verlesenes „@“ vor einem Datum ist kein @-Name
    ("Der Vertrag ist gültig ab @1.12.2034 laut Nachtrag.", ["1.12.2034"]),
])
def test_b70_b99_gegenproben(text, frei):
    funde = _funde(text)
    assert not [f for f in funde if f["kategorie"] == "profilname"], _paare(funde)
    for f in frei:
        assert _nicht_geschwaerzt(text, f, funde), (f, _paare(funde))


# ======================================================================
# Befund 81: Kennungen und Namen in Profil-Links und Parametern von Links
# ======================================================================
@pytest.mark.parametrize("text, werte, frei", [
    ("Kontaktdaten des Kunden (Stammdatenblatt)\nFacebook: facebook.com/quirin.zwackelhuber\n"
     "https://portal.mv-versich.de/dok?kdnr=4711081&vsnr=LV2024887766&name=Zwackelhuber",
     ["quirin.zwackelhuber", "4711081", "LV2024887766", "Zwackelhuber"], ["portal.mv-versich.de"]),
    ("Kontaktdaten des Kunden (Stammdatenblatt)\nFacebook-Profil: https://www.facebook.com/hildegard.rumpelmayr.7\n"
     "Ihr Dokument: https://kundenportal.example-vers.de/akte?vn=Rumpelmayr&police=HR-2291-0047",
     ["hildegard.rumpelmayr.7", "Rumpelmayr", "HR-2291-0047"], ["kundenportal.example-vers.de"]),
    # abgewandelt
    ("Profil: instagram.com/korbi_zeitl84 und linkedin.com/in/korbinian-zeitlhofer-4711",
     ["korbi_zeitl84", "korbinian-zeitlhofer-4711"], ["instagram.com", "linkedin.com"]),
])
def test_b81_kennungen_in_links(text, werte, frei):
    funde = _funde(text)
    for w in werte:
        assert _abgedeckt(text, w, funde), (w, _paare(funde))
        assert _gemeldet(text, w), (w, [(v.text, v.grund) for v in pruefe_text(text)])
    for f in frei:
        assert _nicht_geschwaerzt(text, f, funde), (f, _paare(funde))


@pytest.mark.parametrize("text", [
    "Folgen Sie uns: facebook.com/HUKCOBURG und instagram.com/allianz.de",
    "Newsletter: https://www.example-vers.de/aktion?ref=newsletter&utm_source=mail&id=2025",
    "Mehr unter www.verbraucherzentrale.de/versicherungen",
])
def test_b81_gegenproben_firmenseiten(text):
    funde = _funde(text)
    assert not [f for f in funde if f["kategorie"] in ("profilname", "vertrag", "namen")], _paare(funde)


# ======================================================================
# Befunde 71, 102: IP-Adressen (IPv4 mit Oktettprüfung, IPv6)
# ======================================================================
IP = [
    ("Online-Antrag, elektronisch unterschrieben\nIP-Adresse: 84.123.45.67, Zeitstempel 12.03.2024 14:03",
     ["84.123.45.67"]),
    ("Zustimmung erteilt am 12.03.2025 um 14:08 Uhr von 2001:db8:85a3::8a2e:370", ["2001:db8:85a3::8a2e:370"]),
    ("Unterzeichnet am 12.03.2025 14:08 von IP-Adresse 2a02:8070:a2c1:4f00:d5e3:91b2:7c4a:1e08",
     ["2a02:8070:a2c1:4f00:d5e3:91b2:7c4a:1e08"]),
    ("Unterzeichnet am 12.03.2025 14:08, IP: 2003:c2:7f1a:9e00:b5d4:3c2e:8e7f:42a1",
     ["2003:c2:7f1a:9e00:b5d4:3c2e:8e7f:42a1"]),
    ("erteilt am 12.03.2025 von fe80::1c4b:a2ff:fe3d:9b7e (Mobilgerät)", ["fe80::1c4b:a2ff:fe3d:9b7e"]),
    ("Signaturprotokoll\nIP-Adresse: 2a01:598:b1a2:4c3d:1d2e:3f4a:5b6c:7d8e",
     ["2a01:598:b1a2:4c3d:1d2e:3f4a:5b6c:7d8e"]),
    ("Signaturprotokoll\nIPv6: 2a00:20:c0d2:ee1f:b9a1:fe5c:a3d4:e8f2", ["2a00:20:c0d2:ee1f:b9a1:fe5c:a3d4:e8f2"]),
    # abgewandelt
    ("Zugriff von 192.168.178.23 am 12.03.2024 um 09:15 Uhr", ["192.168.178.23"]),
    ("IPv4: 10.0.0.12 (Heimnetz)", ["10.0.0.12"]),
    ("Absender-IP 1.2.3.4", ["1.2.3.4"]),
]


@pytest.mark.parametrize("text, werte", IP)
def test_b71_b102_ip_adresse(text, werte):
    funde = _funde(text)
    for w in werte:
        assert _abgedeckt(text, w, funde), (w, _paare(funde))
        assert "ip" in _kategorie(text, w, funde), (w, _paare(funde))
        assert _gemeldet(text, w), (w, [(v.text, v.grund) for v in pruefe_text(text)])


@pytest.mark.parametrize("text, frei", [
    ("Betriebssystem Version 10.0.19045.1234", "10.0.19045.1234"),
    ("siehe Abschnitt 1.2.3.4 der Bedingungen", "1.2.3.4"),
    ("Firmware-Release 4.18.0.147 installiert", "4.18.0.147"),
    ("Uhrzeit 14:08:30, Verhältnis 1:2:3", "14:08:30"),
    ("Datum 12.03.2024, Betrag 1.234.567,89 EUR", "1.234.567,89"),
    ("Nummer 300.447.112.5 laut Liste", "300.447.112.5"),
])
def test_b71_b102_gegenproben(text, frei):
    funde = _funde(text)
    assert not [f for f in funde if f["kategorie"] == "ip"], _paare(funde)


def test_b71_punktierte_vertragsnummer_ist_keine_ip():
    """Korpus-Messung s1/s7 (Bestandsliste): eine Vertragsnummer mit Punkten ("95.137.189.6") hat vier gültige
    Oktette – ohne IP-Bezug in der Zeile ist sie keine IP-Adresse (Platzhalter [VERTRAGS-NR], nicht [IP-ADRESSE])."""
    text = "Vertragsnummer\t\tSparte\t\tBeitrag\n95.137.189.6\t\tLeben\t\t45,90 EUR"
    funde = _funde(text)
    assert not any(f["kategorie"] == "ip" for f in funde), _paare(funde)
    assert _abgedeckt(text, "95.137.189.6", funde), _paare(funde)


def test_b71_mac_adresse_bleibt_kennung():
    text = "Router: MAC-Adresse 3C:22:FB:9A:1B:7E, Seriennummer 4711-0815"
    funde = _funde(text)
    assert _abgedeckt(text, "3C:22:FB:9A:1B:7E", funde), _paare(funde)
    assert "ip" not in _kategorie(text, "3C:22:FB:9A:1B:7E", funde)


# ======================================================================
# Befund 103: verschleierte E-Mail-Adressen ((at), [at], [dot], (punkt))
# ======================================================================
@pytest.mark.parametrize("text, werte", [
    ("Bitte schreiben Sie mir an quirin.zw [at] web [dot] de / quirin.zw(at)web(punkt)de",
     ["quirin.zw [at] web [dot] de", "quirin.zw(at)web(punkt)de"]),
    ("Bitte schreiben Sie mir an q.zwackelhuber(at)gmx.de oder quirin.zw [at] web [dot] de",
     ["q.zwackelhuber(at)gmx.de", "quirin.zw [at] web [dot] de"]),
    ("Antwort bitte an quirin.zw(at)web(dot)de", ["quirin.zw(at)web(dot)de"]),
    ("Antwort bitte an hilde.rumpel [at] t-online.de", ["hilde.rumpel [at] t-online.de"]),
    # abgewandelt
    ("Erreichbar unter hilde.rumpel {at} gmx {punkt} de", ["hilde.rumpel {at} gmx {punkt} de"]),
    ("Mail: korbi.zeitl (ät) web (punkt) de", ["korbi.zeitl (ät) web (punkt) de"]),
])
def test_b103_verschleierte_email(text, werte):
    funde = _funde(text)
    for w in werte:
        assert _abgedeckt(text, w, funde), (w, _paare(funde))
        assert "email" in _kategorie(text, w, funde), (w, _paare(funde))
        assert _gemeldet(text, w), (w, [(v.text, v.grund) for v in pruefe_text(text)])


@pytest.mark.parametrize("text", [
    "Wir treffen uns (at) Messe München am Stand 4.",
    "Rabatt (at) home – nur online",
    "Das Dokument [dot] pdf liegt bei.",
])
def test_b103_gegenproben(text):
    assert not [f for f in _funde(text) if f["kategorie"] == "email"], _paare(_funde(text))


# ======================================================================
# Befund 101: Grundbuch, Flurstück, Flur, Blatt
# ======================================================================
@pytest.mark.parametrize("text, werte", [
    ("Wohngebäudeversicherung, Risikoort:\nFlurstück 123/4, Gemarkung Unterhaching\n"
     "Grundbuch von Unterhaching, Blatt 5678", ["123/4", "5678"]),
    # abgewandelt
    ("Flst.-Nr. 1187/12, Flur 3, Gemarkung Haar", ["1187/12"]),
    ("Grundbuchblatt 9921, Flurstücke 445/2 und 445/3", ["9921", "445/2", "445/3"]),
    ("eingetragen im Grundbuch des Amtsgerichts München von Haar Blatt 4471", ["4471"]),
])
def test_b101_grundbuch(text, werte):
    funde = _funde(text)
    for w in werte:
        assert _abgedeckt(text, w, funde), (w, _paare(funde))
        assert _gemeldet(text, w), (w, [(v.text, v.grund) for v in pruefe_text(text)])


@pytest.mark.parametrize("text, frei", [
    ("Blatt 2 von 3", "2 von 3"),
    ("Flur und Treppenhaus wurden gestrichen (Seite 5, Blatt 7).", "Blatt 7"),
    ("Das Grundbuch ist beim Amtsgericht einzusehen, Gebühr 20 EUR.", "20 EUR"),
])
def test_b101_gegenproben(text, frei):
    funde = _funde(text)
    assert _nicht_geschwaerzt(text, frei, funde), _paare(funde)


# ======================================================================
# Befund 88: Religion/Konfession – wie Gesundheitsdaten (in „Hoch“ angeboten, in „Maximal“ geschwärzt)
# ======================================================================
@pytest.mark.parametrize("text, wert", [
    ("Lohnsteuerbescheinigung 2025\nKirchensteuermerkmale: rk", "rk"),
    ("Steuerklasse 3, KiSt ev, Kinderfreibetrag 1,0", "ev"),
    ("Konfession: römisch-katholisch", "römisch-katholisch"),
    ("Religion: evangelisch", "evangelisch"),
    ("Konf.: rk", "rk"),
])
def test_b88_religion_in_maximal_geschwaerzt(text, wert):
    funde = _funde(text, aktive=muster.PROFILE["maximal"]["aktive"], profil="maximal")
    assert any(f["kategorie"] == "religion" and wert in f["text"] for f in funde), _paare(funde)
    assert _wort_abgedeckt(text, wert, funde), _paare(funde)


@pytest.mark.parametrize("text, wert", [
    ("Lohnsteuerbescheinigung 2025\nKirchensteuermerkmale: rk", "rk"),
    ("Konfession: römisch-katholisch", "römisch-katholisch"),
])
def test_b88_religion_in_hoch_nur_angeboten(text, wert):
    funde = _funde(text, aktive=muster.PROFILE["hoch"]["aktive"], profil="hoch")
    religion = [f for f in funde if f["kategorie"] == "religion"]
    assert religion and all(not st["an"] for f in religion for st in f["stellen"]), _paare(funde)
    assert "Art. 9" in religion[0]["hinweis"]


def test_b88_entgeltabrechnung_spalte_konfession(tmp_path):
    exs = (40, 95, 160, 195, 245, 285, 360)
    pdf = _tabelle(tmp_path / "entgelt.pdf", [
        "Abrechnung der Brutto/Netto-Bezüge für November 2026",
        "Personal-Nr.\t\tGeburtsdatum\t\tStKl\t\tKi.Frbtr.\t\tKonf.\t\tSV-Nummer\t\tKrankenkasse",
        "00471\t\t17.09.1966\t\t3\t\t1,0\t\trk\t\t65170966G014\t\tAOK Bayern"], spalten=exs, groesse=7)
    funde, texte = _pdf_funde(pdf, profil="maximal", aktive=muster.PROFILE["maximal"]["aktive"])
    assert any(f["kategorie"] == "religion" and f["text"] == "rk" for f in funde), _paare(funde)
    funde_hoch, _ = _pdf_funde(pdf, profil="hoch", aktive=muster.PROFILE["hoch"]["aktive"])
    assert any(f["kategorie"] == "religion" and not any(st["an"] for st in f["stellen"]) for f in funde_hoch)


@pytest.mark.parametrize("text", [
    "Konfession: keine Angabe",
    "Religion: siehe Personalbogen",
    "Ev. Krankenhaus Rosenheim, Station 3",
    "rk-Wert laut Gutachten 0,4",
    "Lohnsteuer 312,00 EUR, KiSt 28,08 EUR, Soli 0,00 EUR",
])
def test_b88_gegenproben(text):
    funde = _funde(text, aktive=muster.PROFILE["maximal"]["aktive"], profil="maximal")
    assert not [f for f in funde if f["kategorie"] == "religion"], _paare(funde)


# ======================================================================
# Neue Kategorien: Liste, Platzhalter, Schutzstufen, alte Einstellungen
# ======================================================================
NEU = {"ip": "[IP-ADRESSE]", "zugangsdaten": "[ZUGANGSDATEN]", "profilname": "[PROFIL]", "standort": "[STANDORT]",
       "religion": "[RELIGION]"}


def test_neue_kategorien_mit_platzhalter_und_prioritaet():
    eintraege = {k: (anzeige, platzhalter, f, an) for k, anzeige, platzhalter, f, an in muster.KATEGORIEN}
    for k, p in NEU.items():
        assert k in eintraege and eintraege[k][1] == p and eintraege[k][2] is not None
        assert k in muster.KATEGORIE_PRIORITAET
    assert all(eintraege[k][3] for k in ("ip", "zugangsdaten", "profilname", "standort"))
    assert eintraege["religion"][3] is False


def test_neue_kategorien_in_allen_schutzstufen():
    for stufe in ("ausgewogen", "hoch", "maximal"):
        aktive = muster.PROFILE[stufe]["aktive"]
        assert {"ip", "zugangsdaten", "profilname", "standort"} <= aktive, stufe
    assert "religion" not in muster.PROFILE["ausgewogen"]["aktive"]
    assert "religion" not in muster.PROFILE["hoch"]["aktive"]
    assert "religion" in muster.PROFILE["maximal"]["aktive"]
    assert "religion" in muster.hinweis_kategorien("hoch", muster.PROFILE["hoch"]["aktive"])
    assert "religion" in muster.hinweis_kategorien("ausgewogen", muster.PROFILE["ausgewogen"]["aktive"])
    assert "religion" not in muster.hinweis_kategorien("maximal", muster.PROFILE["maximal"]["aktive"])


def test_neue_kategorien_beim_ersten_start_an():
    from anonymisierer import auftrag
    assert {"ip", "zugangsdaten", "profilname", "standort"} <= auftrag.standard_kategorien()
    assert "religion" not in auftrag.standard_kategorien()


def test_readme_tabelle_nennt_neue_platzhalter():
    from pathlib import Path
    readme = (Path(muster.__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")
    for p in NEU.values():
        assert f"`{p}`" in readme, p
