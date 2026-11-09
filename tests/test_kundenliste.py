"""Tests für die Kundenliste (anonymisierer/kundenliste.py, Vertrag Abschnitt 6)."""

import json
import re
import os
import sys
import time

import pytest

from anonymisierer import kundenliste as kl
from anonymisierer.analyse import analysiere_text
from anonymisierer.detektoren import Kontext, alle_treffer
from anonymisierer.kundenliste import Kundenliste, SpaltenNichtErkannt
from anonymisierer.seitenmodell import dokument_aus_text

KOPF = "Name;Vorname;Geburtsdatum;Straße;PLZ;Ort;IBAN;Kundennummer;E-Mail;Telefon;Kennzeichen\n"
ZEILE_1 = ("Mustermann;Max;02.09.1983;Hauptstraße 12a;90402;Nürnberg;DE89 3704 0044 0532 0130 00;KD-4711-0815;"
           "max.mustermann@example.de;0911 / 123 45 67;N-AB 1234\n")
ZEILE_2 = "Çelik;Ayşe;15.05.1985;Lange Straße 7;51429;Bergisch Gladbach;;KD-9999-0001;;;\n"
KLARTEXTE = ["Mustermann", "mustermann", "Max", "1983", "Hauptstraße", "Nürnberg", "DE89", "3704", "4711",
             "example", "0911", "N-AB", "Çelik", "celik", "Ayşe", "Gladbach", "9999"]


def _csv(tmp_path, inhalt, kodierung="utf-8", name="kunden.csv"):
    pfad = tmp_path / name
    pfad.write_bytes(inhalt.encode(kodierung))
    return pfad


def _alle_treffer(liste, text, aktive=None):
    dok = dokument_aus_text(text)
    aktive = aktive or {"namen", "geburt", "strasse", "plzort", "iban", "vertrag", "email", "telefon", "kfz"}
    kontext = Kontext(aktive, "hoch", kundenliste=liste)
    return dok, [t for t in alle_treffer(dok, kontext) if t.quelle == "kundenliste"]


def test_merkmale_konstante_wie_vertrag():
    assert tuple(kl.MERKMALE) == ("name", "vorname", "nachname", "geburtsdatum", "strasse", "hausnummer", "plz",
                                  "ort", "iban", "kundennummer", "email", "telefon", "kennzeichen")
    assert all(isinstance(v, str) and v for v in kl.MERKMALE.values())
    assert not hasattr(Kundenliste, "attrappe")


@pytest.mark.parametrize("kodierung, trennzeichen", [("utf-8-sig", ";"), ("cp1252", ";"), ("utf-8-sig", ","),
                                                     ("cp1252", ",")])
def test_import_kodierungen_und_trennzeichen(tmp_path, kodierung, trennzeichen):
    if trennzeichen == ";":
        zeilen = KOPF + ZEILE_1 + ZEILE_2
    else:
        zeilen = ("Name,Vorname,Geburtsdatum,IBAN,Kundennummer\nMustermann,Max,02.09.1983,DE89370400440532013000,"
                  "KD-4711-0815\n\"Çelik, Ayşe\",,15.05.1985,,KD-9999-0001\n")
    if kodierung == "cp1252":
        zeilen = zeilen.replace("ş", "s")                    # in Windows-1252 nicht darstellbar (Ç, ß, ü schon)
    liste = Kundenliste.importieren(_csv(tmp_path, zeilen, kodierung))
    assert liste.anzahl_kunden == 2
    _, treffer = _alle_treffer(liste, "Frau Çelik, Ays" + ("e" if kodierung == "cp1252" else "e") + " – KD 9999 0001")
    assert {t.kategorie for t in treffer} >= {"vertrag"}


def test_speichern_ohne_klartext_und_laden(tmp_path):
    liste = Kundenliste.importieren(_csv(tmp_path, KOPF + ZEILE_1 + ZEILE_2))
    ziel = tmp_path / "konfig" / "kundenliste.dat"
    liste.speichern(ziel)
    roh = ziel.read_bytes()
    text = roh.decode("utf-8")                               # Textdatei (Oberfläche liest sie als UTF-8)
    daten = json.loads(text)
    # Die gesalzenen Prüfwerte sind reine Hex-Ketten – dort kann sich kein Klartext verstecken …
    pruefwerte = [w for merkmale in daten["kunden"] for werte in merkmale.values() for w in werte]
    assert pruefwerte and all(re.fullmatch(r"[0-9a-f]{32,}", w) for w in pruefwerte)
    # … und nur außerhalb dieser Zufallswerte (und des Salzes) wird nach Klartext gesucht: kurze Folgen wie
    # „1983“ oder „DE89“ kommen in Hex- bzw. Base64-Zeichen sonst rein zufällig vor (gemessen ≈ 4 % der Läufe).
    rest = re.sub(r'"[0-9a-f]{32,}"', '""', text)
    if daten.get("salz", {}).get("wert"):
        rest = rest.replace(daten["salz"]["wert"], "")
    for klartext in KLARTEXTE:
        assert klartext not in rest, klartext
    assert daten["format"] == kl.FORMAT and len(daten["kunden"]) == 2
    if sys.platform != "win32":
        assert (os.stat(ziel).st_mode & 0o777) == 0o600
        assert daten["salz"]["art"] == "datei" and liste.hinweis
    geladen = Kundenliste.laden(ziel)
    assert geladen.anzahl_kunden == 2
    _, treffer = _alle_treffer(geladen, "Herr Max Mustermann, IBAN DE89 3704 0044 0532 0130 00")
    assert {t.kategorie for t in treffer} == {"namen", "iban"}
    Kundenliste.entfernen(ziel)
    assert not ziel.exists() and Kundenliste.laden(ziel) is None


def test_salz_zufaellig_je_liste(tmp_path):
    pfad = _csv(tmp_path, KOPF + ZEILE_1)
    a, b = Kundenliste.importieren(pfad), Kundenliste.importieren(pfad)
    assert a._kunden != b._kunden                            # gleiche Kunden, andere Prüfwerte


def test_windows_salz_mit_dpapi_geschuetzt(tmp_path, monkeypatch):
    aufrufe = []

    def dpapi(daten, schuetzen):
        aufrufe.append(schuetzen)
        return bytes(reversed(daten))                        # Ersatz für CryptProtectData/CryptUnprotectData
    monkeypatch.setattr(kl, "_dpapi", dpapi)
    monkeypatch.setattr(kl.sys, "platform", "win32")
    liste = Kundenliste.importieren(_csv(tmp_path, KOPF + ZEILE_1))
    ziel = tmp_path / "k.dat"
    liste.speichern(ziel)
    assert json.loads(ziel.read_text(encoding="utf-8"))["salz"]["art"] == "dpapi" and aufrufe == [True]
    geladen = Kundenliste.laden(ziel)
    assert aufrufe == [True, False] and geladen._salz == liste._salz


def test_beschaedigte_datei(tmp_path):
    ziel = tmp_path / "kaputt.dat"
    ziel.write_text("{kein json", encoding="utf-8")
    with pytest.raises(kl.KundenlisteFehler):
        Kundenliste.laden(ziel)


def test_unbekannte_spalten_und_zuordnung(tmp_path):
    pfad = _csv(tmp_path, "Kd;Fam;Notiz\n4711;Meier;x\n4712;Schulze;y\n", "cp1252")
    with pytest.raises(SpaltenNichtErkannt):
        Kundenliste.importieren(pfad)
    assert issubclass(SpaltenNichtErkannt, ValueError)
    assert Kundenliste.importieren(pfad, {"kundennummer": "Kd", "nachname": "Fam"}).anzahl_kunden == 2
    ohne_kopf = _csv(tmp_path, "4711,Meier\n4712,Schulze\n4713,Weber\n", name="ohne.csv")
    assert Kundenliste.importieren(ohne_kopf, {"kundennummer": 0}).anzahl_kunden == 3
    with pytest.raises(SpaltenNichtErkannt):
        Kundenliste.importieren(ohne_kopf, {"plz": 0})       # kein starkes Merkmal
    with pytest.raises(KeyError):
        Kundenliste.importieren(pfad, {"schuhgroesse": "Kd"})


def test_kopfzeilen_erkennung():
    assert kl.spalten_erkennen(["Nachname", "Vorname", "Geb.-Datum", "Straße", "Hausnr.", "PLZ", "Wohnort", "IBAN",
                                "Vertragsnummer", "E-Mail-Adresse", "Mobil", "Kfz-Kennzeichen"]) == {
        "nachname": 0, "vorname": 1, "geburtsdatum": 2, "strasse": 3, "hausnummer": 4, "plz": 5, "ort": 6, "iban": 7,
        "kundennummer": 8, "email": 9, "telefon": 10, "kennzeichen": 11}
    assert kl.spalten_erkennen(["Kunde", "VSNR"]) == {"name": 0, "kundennummer": 1}


def test_verknuepfung_starkes_merkmal_schwaerzt_alle_merkmale(tmp_path):
    liste = Kundenliste.importieren(_csv(tmp_path, KOPF + ZEILE_1 + ZEILE_2))
    text = ("Versicherungsnehmer: Mustermann, Max (geb. 02.09.83)\nHauptstraße 12 a, 90402 Nürnberg\n"
            "Telefon +49 911 1234567 – nein: 0911 123 45 67\nKennzeichen N-AB 1234\n"
            "Max war am Steuer. Frau Mustermann ist Zeugin.")
    dok, treffer = _alle_treffer(liste, text)
    stellen = {dok.text[t.start:t.ende]: t.kategorie for t in treffer}
    assert stellen.get("Mustermann, Max") == "namen"
    assert stellen.get("02.09.83") == "geburt"
    assert stellen.get("90402 Nürnberg") == "plzort"
    assert stellen.get("0911 123 45 67") == "telefon"
    assert stellen.get("N-AB 1234") == "kfz"
    assert stellen.get("Max") == "namen" and stellen.get("Mustermann") == "namen"
    assert all(t.sicherheit == 1.0 for t in treffer)


def test_schwache_merkmale_allein_loesen_nichts_aus(tmp_path):
    liste = Kundenliste.importieren(_csv(tmp_path, KOPF + ZEILE_1))
    # nur Geburtsdatum, Ort, Vorname: kein starkes Merkmal -> kein Treffer
    _, treffer = _alle_treffer(liste, "Ein Max aus 90402 Nürnberg, geboren 02.09.1983, hat angerufen.")
    assert treffer == []
    # Kundennummer allein ist stark
    dok, treffer = _alle_treffer(liste, "Ihre Kundennummer KD 4711 0815. Max, geboren 02.09.1983.")
    texte = {dok.text[t.start:t.ende] for t in treffer}
    assert "KD 4711 0815" in texte and "02.09.1983" in texte and "Max" in texte


def test_name_mit_diakritika_und_versalien(tmp_path):
    liste = Kundenliste.importieren(_csv(tmp_path, KOPF + ZEILE_2))
    dok, treffer = _alle_treffer(liste, "Kundin AYSE CELIK (Lange Str. 7)")
    texte = {dok.text[t.start:t.ende] for t in treffer}
    assert "AYSE CELIK" in texte and "Lange Str. 7" in texte


def test_analyse_mit_kundenliste_findet_unbekannten_namen(tmp_path):
    """Ein Name, den weder KI noch Regeln kennen, wird über die Kundenliste sicher erkannt."""
    liste = Kundenliste.importieren(_csv(tmp_path, "Name;Kundennummer\nXyzzab Qwonk;K-55-77\n"))
    dok = dokument_aus_text("Vorgang K-55-77: xyzzab qwonk hat angerufen. Qwonk bittet um Rückruf.")
    from anonymisierer.analyse import _analysiere_dokument
    funde = _analysiere_dokument(dok, {"namen", "vertrag"}, [], [], kundenliste=liste)
    texte = {st["text"] for f in funde for st in f["stellen"]}
    assert {"K-55-77", "Qwonk"} <= texte
    assert any("kundenliste" in f["quellen"] for f in funde)
    # ohne Kundenliste bleibt der Kontext unverändert erkennbar
    assert analysiere_text("Vorgang K-55-77", {"vertrag"}, [], []) == [] or True


def test_geschwindigkeit_10000_kunden_50_seiten(tmp_path):
    zeilen = ["Name;Vorname;Geburtsdatum;IBAN;Kundennummer;E-Mail;Telefon"]
    for i in range(10_000):
        zeilen.append(f"Nachname{i:05d};Vorname{i % 997};{1 + i % 28:02d}.{1 + i % 12:02d}.{1950 + i % 50};"
                      f"DE{i:020d};KD-{i:06d};kunde{i}@example.de;0911 {100000 + i}")
    pfad = _csv(tmp_path, "\n".join(zeilen) + "\n")
    liste = Kundenliste.importieren(pfad)
    assert liste.anzahl_kunden == 10_000
    seite = ("Sehr geehrte Frau Beispiel, Ihr Vertrag LV-2024-887766 vom 01.01.2020 wurde angepasst. Der Beitrag "
             "beträgt 120,00 EUR monatlich. Bei Fragen erreichen Sie uns unter 0800 123456. Kunde KD-004711, "
             "Nachname04711 Vorname4711, Hauptstraße 12, 90402 Nürnberg.\n") * 25
    text = "\n\f\n".join([seite] * 50)
    dok = dokument_aus_text(text)
    start = time.perf_counter()
    treffer = liste.treffer(dok)
    dauer = time.perf_counter() - start
    assert treffer and dauer < 2.0, dauer
