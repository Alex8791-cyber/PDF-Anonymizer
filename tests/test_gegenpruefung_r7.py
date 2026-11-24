"""Nachbesserung nach der Gegenprüfung der Zusammenführung (Runde 5, integration-r7).

Je Befund: die Zeile der Prüfer (Leck bzw. Über-Schwärzung), Abwandlungen und Gegenproben – nicht geheime Nachbarn
bleiben lesbar. Wo eine Regel der Erkennung neu greift, prüft ein Test auch die Selbstkontrolle (restrisiko.py): bliebe
der Wert stehen, muss sie ihn melden. Alle Personen, Nummern und Anschriften sind frei erfunden."""

import pymupdf as fitz
import pytest

from conftest import braucht_ocr
from anonymisierer import muster
from anonymisierer.analyse import analysiere_pdf, analysiere_text
from anonymisierer.restrisiko import pruefe_text
from anonymisierer.schwaerzung import schwaerze_pdf

ALLE = {k for k, _, _, _, an in muster.KATEGORIEN if an}


# ----------------------------------------------------------------------
# Hilfsfunktionen
# ----------------------------------------------------------------------
def _funde(text, profil="hoch"):
    return analysiere_text(text, ALLE, [], [], profil=profil)


def _stellen(funde, kategorie=None) -> set:
    """Texte aller angehakten Stellen (optional nur einer Kategorie)."""
    return {st["text"] for f in funde if kategorie is None or f["kategorie"] == kategorie
            for st in f["stellen"] if st.get("an", True)}


def _geschwaerzt(text, wert, kategorie=None) -> bool:
    return any(wert in s for s in _stellen(_funde(text), kategorie))


def _beruehrt(text, wert) -> bool:
    """Wird der Wert oder ein Teil davon geschwärzt?"""
    return any(wert in s or (len(s) >= 2 and s in wert) for s in _stellen(_funde(text)))


def _verdacht(text, **kw) -> list:
    return [(v.text, v.grund) for v in pruefe_text(text, **kw)]


def _gemeldet(text, wert, **kw) -> bool:
    return any(wert in t or (len(t) >= 3 and t in wert) for t, _ in _verdacht(text, **kw))


def _pdf(pfad, seiten, groesse=10):
    """PDF aus Seiten; je Seite Elemente (x, y, text)."""
    doc = fitz.open()
    for elemente in seiten:
        seite = doc.new_page(width=595, height=842)
        for x, y, text in elemente:
            seite.insert_text((x, y), text, fontsize=groesse, fontname="helv")
    doc.save(pfad)
    doc.close()
    return pfad


def _zeilen(zeilen, y=80, abstand=16, xs=(60, 250, 420)):
    """Zeilen mit "\\t\\t" als Spaltentrenner an den Spaltenpositionen xs."""
    aus = []
    for i, zeile in enumerate(zeilen):
        teile = zeile.split("\t\t")
        for k, teil in enumerate(teile):
            aus.append((xs[k] if len(teile) > 1 else xs[0], y + i * abstand, teil))
    return aus


def _pdf_funde(pfad):
    erg = analysiere_pdf(pfad, ALLE, [], [])
    assert not erg.get("fehler"), erg.get("fehler")
    return erg


def _pdf_stellen(erg, kategorie=None) -> set:
    return {st["text"] for f in erg["funde"] if kategorie is None or f["kategorie"] == kategorie
            for st in f["stellen"] if st.get("an", True)}


def _ausgabe_ohne(tmp_path, pdf, ohne_text):
    """Schwärzt die Datei mit allen Funden außer denen, deren Text `ohne_text` enthält (eine verfehlte Erkennung
    nachgestellt), und liefert den Verdacht der Selbstkontrolle auf der Ausgabe."""
    erg = _pdf_funde(pdf)
    funde = [f for f in erg["funde"] if ohne_text not in f["text"]]
    aus = schwaerze_pdf(pdf, funde, modell=erg.get("modell"), ziel_ordner=tmp_path / "aus")
    return [(v.text, v.grund) for v in aus.get("verdacht") or []]


# ----------------------------------------------------------------------
# Integration: Ort hinter der Person eines Personen-Etiketts (Domäne klinik_entlassbrief, „Gaimersheim“)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("zeile, ort", [
    ("Einweisender Arzt: Dr. Petra Ullrich-Habermann, Gaimersheim", "Gaimersheim"),     # Zeile der Domäne
    ("Hausarzt: Dr. med. Kurt Weinzierl, Kolbermoor", "Kolbermoor"),
    ("Zeuge: Hans Maierhofer, Rosenheim", "Rosenheim"),
    ("Fahrer: Max Wimmer, Pfaffenhofen a. d. Ilm", "Pfaffenhofen a. d. Ilm"),
])
def test_ort_hinter_person_im_personenfeld(zeile, ort):
    assert _geschwaerzt(zeile, ort), zeile


@pytest.mark.parametrize("zeile, bleibt", [
    ("Zeuge: Hans Maierhofer, Polizeibeamter", "Polizeibeamter"),       # Beruf
    ("Tierarzt: Dr. Anna Huber, Kleintierpraxis", "Kleintierpraxis"),     # zusammengesetztes Hauptwort
    ("Gutachter: Dipl.-Ing. Kurt Weber, DEKRA", "DEKRA"),                 # Organisation
    ("Ehepartner: Anna Huber, Hausfrau", "Hausfrau"),
    ("Arbeitgeber: Huber Bau, Kösching", "Kösching"),                     # Firmenort
])
def test_ort_hinter_person_gegenproben(zeile, bleibt):
    assert not _stellen(_funde(zeile), "ort") & {bleibt}, zeile


def test_ort_hinter_person_selbstkontrolle_meldet_ort_neben_platzhalter(tmp_path):
    # Die Erkennung verfehlt den Ort (nachgestellt: der Fund fehlt) – die Selbstkontrolle sieht in der Ausgabe
    # "Dr. [PERSON B], Gaimersheim" (Komma zwischen grauem Rechteck und Wort) und meldet den Ort
    pdf = _pdf(tmp_path / "klinik.pdf", [_zeilen([
        "Klinikum Ingolstadt - Klinik für Unfallchirurgie",
        "Patient: Gregor Wollnitz, *19.07.1964",
        "Einweisender Arzt: Dr. Petra Ullrich-Habermann, Gaimersheim"])])
    verdacht = _ausgabe_ohne(tmp_path, pdf, "Gaimersheim")
    assert any("Gaimersheim" in t for t, _ in verdacht), verdacht


# ----------------------------------------------------------------------
# Integration: Name hinter einer Berufsbezeichnung im Satz (Domäne phv_fliesstext_nachbar, „Eibl“)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("satz, name", [
    ("Der Glaser Eibl hat bereits ein Angebot über 640,00 EUR erstellt.", "Eibl"),     # Zeile der Domäne
    ("Unser Monteur Zwickl kam um 8 Uhr.", "Zwickl"),
    ("Die Gutachterin Hechenberger, die den Schaden aufnahm, war pünktlich.", "Hechenberger"),
    ("Laut dem Hausmeister Kowalczyk war die Tür offen.", "Kowalczyk"),
])
def test_name_hinter_beruf_im_satz(satz, name):
    assert _geschwaerzt(satz, name, "namen"), satz
    assert _gemeldet(satz, name), satz


@pytest.mark.parametrize("satz, bleibt", [
    ("Wir haben dem Glaser Bescheid gegeben.", "Bescheid"),
    ("Der Monteur Notdienst kam erst am Abend.", "Notdienst"),
    ("Der Maler Montag ist krank.", "Montag"),
    ("Der Elektriker Strom abgestellt.", "Strom"),
    ("Der Dachdecker Reparatur erfolgte am Montag.", "Reparatur"),
])
def test_name_hinter_beruf_gegenproben(satz, bleibt):
    assert not _beruehrt(satz, bleibt), satz


def test_beruf_vor_personen_platzhalter_ist_kein_verdacht():
    # Ausgabe "Der Glaser [PERSON C] hat …": "Glaser" ist der Beruf (auch ein Familienname), kein Rest des Namens
    text = "Der Glaser [PERSON C] hat bereits ein Angebot über 640,00 EUR erstellt."
    assert not _gemeldet(text, "Glaser", platzhalter=["[PERSON C]"])


# ----------------------------------------------------------------------
# Integration: Fortsetzungsseite einer Tabelle ohne wiederholten Kopf (Domäne k4_forts_ohne_kopf, Befund LK-13)
# ----------------------------------------------------------------------
_XS = (36, 130, 290, 380, 470)
_KOPF = "Vertrag\t\tVersicherungsnehmer\t\tSparte\t\tBeginn\t\tJahresbeitrag"


def test_fortsetzungsseite_ohne_kopf_kennungen_und_namen(tmp_path):
    s1 = [(36, 50, "Bestandsliste Kunde/Vertrag – Stand 12.11.2026")] + _zeilen([
        _KOPF, "HR-7740-2291-05\t\tKraxenberger, Wendelin\t\tHausrat\t\t01.12.2020\t\t186,40",
        "PHV-0071-4471\t\tBrandlhuber, Gerlinde\t\tPHV\t\t01.11.2019\t\t89,90"], y=80, abstand=11, xs=_XS)
    s2 = [(36, 40, "Bestandsliste Kunde/Vertrag – Stand 12.11.2026 – Seite 2")] + _zeilen([
        "PHV 447118\t\tWiesenhofer, Baltasar\t\tPHV\t\t01.11.2019\t\t89,90",
        "4471-0815\t\tPichlmeier, Notburga\t\tHausrat\t\t01.12.2020\t\t186,40",
        "RS 0815\t\tRuhstorfer Kunigunde\t\tRechtsschutz\t\t01.03.2018\t\t298,30",
        "7.712.345\t\tOberprieler, Severin\t\tUnfall\t\t15.10.2026\t\t142,80"], y=70, abstand=11, xs=_XS)
    erg = _pdf_funde(_pdf(tmp_path / "forts.pdf", [s1, s2], groesse=8))
    stellen = _pdf_stellen(erg)
    for wert in ("PHV 447118", "4471-0815", "RS 0815", "7.712.345", "Wiesenhofer", "Oberprieler"):
        assert any(wert in s for s in stellen), (wert, stellen)
    for bleibt in ("Hausrat", "Rechtsschutz", "186,40", "01.12.2020"):
        assert not any(bleibt in s for s in stellen), (bleibt, stellen)


def test_fortsetzungsseite_geburtsdaten_ohne_kopf(tmp_path):
    xs = (40, 170, 300)
    s1 = _zeilen(["Teilnehmerliste", "Name\t\tVorname\t\tGeburtsdatum", "Hagenberger\t\tFabian\t\t11.03.1985"],
                 xs=xs)
    s2 = _zeilen(["Fortsetzung", "Hagenberger\t\tLiesl\t\t02.02.2014", "Hagenberger\t\tToni\t\t17.09.2016"], xs=xs)
    stellen = _pdf_stellen(_pdf_funde(_pdf(tmp_path / "forts2.pdf", [s1, s2])), "geburt")
    assert {"02.02.2014", "17.09.2016"} <= stellen, stellen


def test_fortsetzung_gegenprobe_andere_seite_ohne_hinweis(tmp_path):
    # Kurze Tabelle auf Seite 1, auf Seite 2 ein Fließtext mit Datumsangaben ohne Fortsetzungshinweis: die Spalten
    # der Seite 1 gelten dort nicht
    xs = (40, 170, 300)
    s1 = _zeilen(["Teilnehmerliste", "Name\t\tVorname\t\tGeburtsdatum", "Hagenberger\t\tFabian\t\t11.03.1985"],
                 xs=xs)
    s2 = _zeilen(["Termine\t\tRaum\t\tDatum", "Kursbeginn\t\tAula\t\t02.02.2027", "Prüfung\t\tHalle\t\t17.09.2027"],
                 xs=xs)
    stellen = _pdf_stellen(_pdf_funde(_pdf(tmp_path / "forts3.pdf", [s1, s2])))
    assert not any("2027" in s for s in stellen), stellen


# ----------------------------------------------------------------------
# LK-01: Mannheimer Quadrate sind Anschriften, keine Straßenklassen
# ----------------------------------------------------------------------
@pytest.mark.parametrize("zeile, quadrat", [
    ("Anschrift: L 14, 16, 68161 Mannheim", "L 14, 16"),                    # Zeile der Prüfer
    ("Risikoort: E 3, 1, 68159 Mannheim", "E 3, 1"),
    ("Neue Anschrift: K 1, 5 in Mannheim", "K 1, 5"),
    ("C.1.3 Anschrift: L 14, 16, 68161 Mannheim", "L 14, 16"),
    ("Bisheriger Halter: Brettschneider, Annemarie, Q 3, 7, 68161 Mannheim", "Q 3, 7"),
    ("Versicherungsnehmerin: Frau Leonie Strobl\nB 2, 9\n68159 Mannheim", "B 2, 9"),
])
def test_lk01_quadrat_ist_anschrift(zeile, quadrat):
    assert _geschwaerzt(zeile, quadrat, "strasse"), zeile


@pytest.mark.parametrize("zeile, quadrat", [
    ("Anschrift: L 14, 16, [PLZ ORT]", "L 14, 16"),                          # Ausgabe: PLZ und Ort ersetzt
    ("Neue Anschrift: K 1, 5 in [ORT]", "K 1, 5"),
    ("[PERSON A]\nB 2, 9\n[PLZ ORT]", "B 2, 9"),
])
def test_lk01_selbstkontrolle_meldet_quadrat(zeile, quadrat):
    assert _gemeldet(zeile, quadrat, platzhalter=["[PERSON A]"]), zeile


@pytest.mark.parametrize("zeile", [
    "Unfallort: BAB 9, km 381,2",
    "Unfallort: Auf der A 8 Richtung Salzburg",
    "Unfallort: A 8, 12 km vor Rosenheim",
    "Tarifklasse B 2, 9 Punkte",
])
def test_lk01_gegenproben_fahrbahn_und_klassen_bleiben(zeile):
    assert not _stellen(_funde(zeile), "strasse"), zeile
    assert not any(g == "Anschrift (Straße + Hausnummer)" for _, g in _verdacht(zeile)), zeile


# ----------------------------------------------------------------------
# LK-02: Familienname, der zugleich Marke, Modell oder Rasse ist, an einem Ort für Personen
# ----------------------------------------------------------------------
def test_lk02_gruss_block_familienname_mit_markennamen():
    text = "Sehr geehrte Damen und Herren,\nanbei die Unterlagen zur Kündigung.\nMit freundlichen Grüßen\nNeff"
    assert _gemeldet(text, "Neff")


def test_lk02_gruss_block_ohne_ki_gemeldet():
    assert _gemeldet("Beste Grüße aus Prien\nPiaggio", "Piaggio")


@pytest.mark.parametrize("text, name", [
    ("Bestandsliste\nKunde\t\tPLZ\t\tOrt\t\tVertragsnr.\nHuber, Anton\t\t83259\t\tSchleching\t\t7.712.347\n"
     "Pommer\t\t83246\t\tUnterwössen\t\t7.712.349", "Pommer"),
    ("Fuhrparkliste\nKennzeichen\t\tFahrzeug\t\tFahrer\nRO-AB 1207\t\tVW Crafter Kasten\t\tHuber\n"
     "RO-AB 1208\t\tVW Caddy\t\tMiele", "Miele"),
])
def test_lk02_personenspalte_meldet_markennamen(text, name):
    assert _gemeldet(text, name), _verdacht(text)


@pytest.mark.parametrize("text, sache", [
    ("Gestohlen wurde ein Mofa Simson S51 aus der Garage.", "Simson"),
    ("Hersteller: Miele, Baujahr 2019", "Miele"),
    ("Fahrer\t\tFahrzeug\nHuber, Anton\t\tMofa Simson", "Simson"),            # Sachbeleg in der Zelle
])
def test_lk02_gegenproben_marken_mit_sachbeleg_bleiben(text, sache):
    assert not _beruehrt(text, sache), text


def test_lk02_tabelle_mit_ueberschrift_ueber_dem_kopf(tmp_path):
    # Überschrift über dem Spaltenkopf wird nicht Teil eines zweizeiligen Kopfs: "Tissot" steht in der Spalte "Name"
    pdf = _pdf(tmp_path / "tissot.pdf", [_zeilen(["Mitversicherte Personen", "Name\t\tVorname\t\tgeb. am",
                                                    "Huber\t\tWalburga\t\t03.08.1958",
                                                    "Tissot\t\tAnnika\t\t19.12.1990"])])
    assert "Tissot" in _pdf_stellen(_pdf_funde(pdf), "namen")


# ----------------------------------------------------------------------
# LK-03/LK-04: Personen in Organisations-Spalten (Versicherer, Anbieter, Krankenkasse); Spaltenkopf "Fahrzeug"
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, name", [
    ("Vorversicherungen\nSparte\t\tVersicherer\t\tVertragsnummer\nPHV\t\tGebhard Lindinger (privat)\t\t–",
     "Lindinger"),
    ("Vorversicherungen\nSparte\t\tVersicherer\t\tVertragsnummer\nPHV\t\tGebhard Lindinger\t\t–", "Gebhard"),
    ("Sparte\t\tAnbieter\t\tVertragsnummer\nPHV\t\tKurt Wendlinger (Vermittler)\t\t–", "Kurt"),
    ("Kind\t\tGeburtsdatum\t\tKrankenkasse\nMathilda Rauschmayr\t\t02.05.2017\t\tfamilienversichert über Lorenz "
     "Rauschmayr, BKK", "Lorenz"),
    ("Fahrer\t\tFahrzeug\t\tKennzeichen\nWeidemann\t\tPkw\t\tRO-WE 330\nHuber\t\tLkw\t\tRO-WE 331", "Weidemann"),
])
def test_lk03_lk04_person_in_organisations_spalte(text, name):
    assert _geschwaerzt(text, name, "namen"), text
    assert _gemeldet(text, name), text


def test_lk03_gegenprobe_versicherer_bleiben():
    text = ("Sparte\t\tVersicherer\t\tTarif\nPHV\t\tAdam Riese\t\tXXL\nHausrat\t\tRoland\t\tKomfort\n"
            "KFZ\t\tHUK-COBURG Versicherung\t\tPlus")
    for wert in ("Adam", "Riese", "Roland", "HUK"):
        assert not _beruehrt(text, wert), wert
    assert not _verdacht(text), _verdacht(text)


# ----------------------------------------------------------------------
# L1: Unterschriftslinien aus Unterstrichen – Nummern-Etiketten ohne exponentielles Zurückgehen
# ----------------------------------------------------------------------
@pytest.mark.parametrize("zeile", [
    "Ort, Datum " + "_" * 40 + "   Unterschrift " + "_" * 40,
    "Unterschrift" + "_" * 60,
    "_".join(["Teil"] * 30) + ".pdf",                                         # Dateiname aus Unterstrich-Teilen
])
def test_l1_unterstriche_linear(zeile):
    # vorher exponentiell: 34 Unterstriche 6–23 s, 40 Unterstriche über 100 s (Gegenprüfung L1); jetzt Millisekunden
    import zeitmessung
    from anonymisierer import kennungsformen
    analysiere_text("Vertragsnummer: 12345 Max Mustermann", ALLE, [], [], profil="hoch")   # Modell laden
    _, zeit = zeitmessung.cpu_sekunden(lambda: (kennungsformen.kennungs_etiketten(zeile),
                                                kennungsformen.allgemeine_kennungen(zeile),
                                                analysiere_text(zeile, ALLE, [], [], profil="hoch"),
                                                pruefe_text(zeile)), wiederholungen=2)
    assert zeit < 1.0, f"{zeit:.2f} s CPU-Zeit für {len(zeile)} Zeichen"


@pytest.mark.parametrize("wort", ["Bestandsnummer", "Mitglieds-ID", "BG-Nummer", "Vorg.-Nr.", "Ser.-Nr.",
                                  "Rahmen-Nummer", "Kunden_Nr", "Akten_Zeichen_Nummer", "Geräte-ID"])
def test_l1_nummern_woerter_unveraendert(wort):
    from anonymisierer import kennungsformen
    assert kennungsformen.NUMMERN_WORT_RE.fullmatch(wort), wort


# ----------------------------------------------------------------------
# L2: lange Einzelzeile (Formularfeldtext) – Marken-/Tier-Prüfungen je Zeile einmal statt je Kandidat
# ----------------------------------------------------------------------
def test_l2_lange_zeile_mit_versalnamen_waechst_linear():
    import zeitmessung
    gross = " ".join(["HERR", "KORBINIAN", "ZWACKL", "FRAU", "ROSA", "HUBER"] * 240)       # gut 8 000 Zeichen
    klein = " ".join(["HERR", "KORBINIAN", "ZWACKL", "FRAU", "ROSA", "HUBER"] * 30)
    analysiere_text("Vertragsnummer: 12345 Max Mustermann", ALLE, [], [], profil="hoch")    # Modell laden
    wachstum, _, zeit = zeitmessung.wachstum_messen(lambda: analysiere_text(klein, ALLE, [], [], profil="hoch"),
                                                    lambda: analysiere_text(gross, ALLE, [], [], profil="hoch"), 8,
                                                    wiederholungen=1, schranke=1.6)
    print(f"lange Zeile: {zeit:.2f} s CPU, wachstum {wachstum:.2f}")
    assert wachstum < 1.6, f"Laufzeit wächst auf einer langen Zeile um {wachstum:.2f} x linear"


@pytest.mark.parametrize("zelle", ["Ab" * 1000 + "weg", "Ab-" * 666])
def test_l2_l3_lange_zelle_ohne_leerzeichen_in_der_selbstkontrolle(zelle):
    # vorher: "Ab-" * 666 in einer Zelle unter "Anschrift" 30 s CPU (Kompositum-Prüfung je Trennstelle über das ganze
    # Wort), die Straßennamen-Form über eine lange Zelle (Gegenprüfung L2/L3)
    import zeitmessung
    pruefe_text("Max Mustermann")
    text = "Kopf\t\tAnschrift\nWert\t\t" + zelle
    _, zeit = zeitmessung.cpu_sekunden(lambda: pruefe_text(text), wiederholungen=2)
    assert zeit < 1.0, f"{zeit:.2f} s CPU-Zeit"


# ----------------------------------------------------------------------
# V1: Religion wie Gesundheitsdaten – in „Hoch“/„Ausgewogen“ angeboten, dann auch kein Verdacht der Ausgabe
# ----------------------------------------------------------------------
@pytest.mark.parametrize("profil, gemeldet", [("hoch", False), ("ausgewogen", False), ("maximal", True)])
def test_v1_religion_verdacht_nur_wo_sie_geschwaerzt_wird(profil, gemeldet):
    text = "Lohnsteuerbescheinigung 2025\nKirchensteuermerkmale: rk\nKonfession des Ehegatten: ev"
    verdacht = [g for _, g in _verdacht(text, profil=profil) if "Religion" in g]
    assert bool(verdacht) is gemeldet, (profil, verdacht)


# ----------------------------------------------------------------------
# U1–U6: Über-Schwärzung und Fehlverdacht der neuen Kategorien
# ----------------------------------------------------------------------
@pytest.mark.parametrize("zeile, bleibt", [
    ("Abmessungen: Länge 4.689 mm, Breite 1.829 mm, Höhe 1.468 mm", "4.689"),       # U1 Fahrzeugmaße
    ("Carport: Länge 5.000 mm, Breite 3.000 mm", "3.000"),
    ("IP-Kamera Modell 2.4.1.8 im Carport", "2.4.1.8"),                              # U2
    ("Außenleuchte Schutzart IP44, Artikel 3.10.25.1, 2 Stück", "3.10.25.1"),
    ("Videoüberwachung (IP-basiert), Rekorder Typ 4.1.2.0", "4.1.2.0"),
    ("Neu: Tarif @home-Paket mit Fahrradschutz und Elementar", "home"),             # U3
    ("Zugang zum Kundenportal – bitte ausfüllen: Benutzername: Kennwort: E-Mail:", "E-Mail"),   # U4
    ("Benutzername: Kennzeichen: Konto: IMEI: PIN:", "Kennzeichen"),
])
def test_u1_bis_u4_keine_ueberschwaerzung(zeile, bleibt):
    assert not _beruehrt(zeile, bleibt), _stellen(_funde(zeile))
    assert not any(bleibt in t for t, _ in _verdacht(zeile)), _verdacht(zeile)


@pytest.mark.parametrize("zeile, wert", [
    ("Breitengrad 47.85612", "47.85612"),                                          # Gegenproben: echte Werte
    ("Breite: 47.856°, Länge: 12.128°", "47.856"),
    ("Länge 12.12857", "12.12857"),
    ("Zugriff von IP 84.123.45.67", "84.123.45.67"),
    ("Absender-IP: 84.123.45.67", "84.123.45.67"),
    ("Er schrieb als @schattenwolf auf Instagram", "@schattenwolf"),
    ("Bitte an @korbi_zeitl84 weiterleiten", "@korbi_zeitl84"),
    ("Benutzername: maxmuster82", "maxmuster82"),
])
def test_u1_bis_u4_gegenproben_werte_bleiben_erkannt(zeile, wert):
    assert _geschwaerzt(zeile, wert), _stellen(_funde(zeile))


@pytest.mark.parametrize("text, wert", [
    ("Versicherte Person: [PERSON A]\nBehandlungstag: Montag, 03.06.2024", "03.06.2024"),             # U5
    ("Leistungen bei Entbindung im Krankenhaus ab 01.01.2025 zu 100 %", "01.01.2025"),              # U6
])
def test_u5_u6_kein_fehlverdacht(text, wert):
    assert not _gemeldet(text, wert, platzhalter=["[PERSON A]"]), _verdacht(text, platzhalter=["[PERSON A]"])


@pytest.mark.parametrize("text, wert", [
    ("Entbindung am 21.08.2026 im Klinikum Traunstein", "21.08.2026"),
    ("Kinder: Lena Koch, 12.03.2014", "12.03.2014"),
])
def test_u5_u6_gegenproben_bleiben_verdacht(text, wert):
    assert _gemeldet(text, wert), _verdacht(text)


# ----------------------------------------------------------------------
# LK-02/LK-17: ZB I als Scan in Spaltenblöcken (Feldcodes, Feldnamen und Werte je ein Block der Texterkennung) – der
# Wert rechts auf derselben Höhe gehört zum Feldnamen („Name oder Firmenname“ … „Kreidler“)
# ----------------------------------------------------------------------
@braucht_ocr
def test_lk02_zb1_scan_spaltenbloecke(tmp_path):
    from anonymisierer.ocr import OcrDienst
    zeilen = [("Zulassungsbescheinigung Teil I – Abschrift für den Versicherer", None, None),
              ("A", "Amtliches Kennzeichen", "MA-KL 4412"), ("B", "Datum der Erstzulassung", "17.06.2021"),
              ("C.1.1", "Name oder Firmenname", "Kreidler"), ("C.1.2", "Vorname(n)", "Ludwig Anselm"),
              ("C.1.3", "Anschrift", "L 14, 16, 68161 Mannheim"), ("P.3", "Kraftstoff", "Benzin")]
    vorlage = fitz.open()
    s = vorlage.new_page()
    for i, (a, b, c) in enumerate(zeilen):
        y = 90 + 22 * i
        s.insert_text((50, y), a, fontsize=11, fontname="helv")
        if b:
            s.insert_text((110, y), b, fontsize=11, fontname="helv")
            s.insert_text((330, y), c, fontsize=11, fontname="helv")
    pix = s.get_pixmap(dpi=200, colorspace=fitz.csGRAY)
    doc = fitz.open()
    p = doc.new_page(width=s.rect.width, height=s.rect.height)
    p.insert_image(p.rect, stream=pix.tobytes("png"))
    pdf = tmp_path / "zb1_scan.pdf"
    doc.save(pdf)
    doc.close()
    vorlage.close()
    with OcrDienst(prozesse=1) as dienst:
        e = analysiere_pdf(pdf, ALLE, [], [], ocr=dienst)
    stellen = _pdf_stellen(e)
    assert any("Kreidler" in t for t in stellen), stellen
    assert not any(t in ("Benzin", "Kraftstoff", "Anschrift") for t in stellen), stellen


@pytest.mark.parametrize("text, wert", [
    ("Name oder Firmenname: Kreidler", "Kreidler"),                       # Feldname der ZB I als Personen-Etikett
    ("Fahrer: Miele", "Miele"),
])
def test_lk02_personen_etikett_vor_markenname(text, wert):
    assert _geschwaerzt(text, wert) or _gemeldet(text, wert), (_stellen(_funde(text)), _verdacht(text))


def test_lk03_markenkern_eines_versicherers_nur_in_der_versicherer_spalte():
    # "Adam Riese" steht nicht als Person in der Erlaubnisliste, nur der Versicherer "Adam Riese Versicherung": als
    # Markenkern gilt der Name allein in einer Organisations-Spalte – hinter einem Personen-Etikett bleibt er Person
    assert not _beruehrt("Versicherer\t\tTarif\nAdam Riese\t\tXXL", "Riese")
    assert _geschwaerzt("Versicherungsnehmer: Adam Riese", "Adam Riese")
    assert _geschwaerzt("Sparte\t\tVersicherer\nPHV\t\tGebhard Lindinger", "Lindinger")


# ----------------------------------------------------------------------
# LK-06/LK-07/LK-05: Zugangsdaten mit Zwischenwörtern, Kompositum, ohne Doppelpunkt, im Satz; Geheimzahlen und Codes
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert", [
    ("Kennwort für telefonische Auskünfte: Gartenzwerg", "Gartenzwerg"),
    ("Passwort für das Kundenportal: Hufeisen#27", "Hufeisen#27"),
    ("WPA2-Kennwort: Kuckucksuhr!1983", "Kuckucksuhr!1983"),
    ("Router-Kennwort Zirbe-Stube-77", "Zirbe-Stube-77"),
    ("Ihr Benutzername lautet EBUERSTNER61, Ihr Initialkennwort Kx7#mQ2v.", "Kx7#mQ2v"),
    ("Benutzername für das Bürgerkonto: valentina.grieshaber", "valentina.grieshaber"),
    ("App-Login (Benutzer): ikastenmueller", "ikastenmueller"),
    ("Kennwort der App laut Begrüßungsschreiben: Blasmusik!77", "Blasmusik!77"),
    ("Administrator-Konto: adm-tabbert", "adm-tabbert"),
    ("Kennwort des Administrators vor dem Vorfall: Werkbank&Hobel1990", "Werkbank&Hobel1990"),
    ("Ihre persönliche Geheimzahl lautet 8034.", "8034"),
    ("Code der Alarmanlage: 1357", "1357"),
    ("Schlüssel im Schlüsseltresor neben der Haustür, Zahlencode 2580.", "2580"),
    ("Plakettencode der Stempelplakette hinten: B4R7ZT", "B4R7ZT"),
    ("Entsperrcode des Handys: 482916", "482916"),
    ("Karten-PIN 7713", "7713"),
])
def test_lk06_lk07_zugangsdaten(text, wert):
    assert _geschwaerzt(text, wert, "zugangsdaten"), _stellen(_funde(text))
    assert _gemeldet(text, wert), _verdacht(text)            # dieselbe Regel in der Selbstkontrolle


def test_lk07_pin_als_spaltenkopf(tmp_path):
    zeilen = ["Kartenübersicht", "Karte\t\tPIN\t\tgültig bis", "girocard\t\t4713\t\t12/2028"]
    assert _geschwaerzt("\n".join(zeilen), "4713", "zugangsdaten")
    pdf = _pdf(tmp_path / "pin.pdf", [_zeilen(zeilen)])
    assert "4713" in _pdf_stellen(_pdf_funde(pdf), "zugangsdaten")
    verdacht = _ausgabe_ohne(tmp_path, pdf, "4713")          # verfehlte Erkennung: die Selbstkontrolle meldet
    assert any("4713" in t for t, _ in verdacht), verdacht
    assert not any("girocard" in t or "2028" in t for t, _ in verdacht), verdacht


@pytest.mark.parametrize("text, bleibt", [
    ("Kennwort ändern", "ändern"),
    ("PIN eingeben und bestätigen", "eingeben"),
    ("Code der Bestellung: 4711-22", "4711-22"),
    ("Die Kennwortregeln: mindestens 8 Zeichen", "mindestens"),
    ("Kennwort bitte nicht weitergeben: Ihre Bank", "Bank"),
    ("Fehlercode: E-401", "E-401"),
    ("Karte\t\tPIN\ngirocard\t\twird separat zugesandt", "separat"),
])
def test_lk06_lk07_gegenproben(text, bleibt):
    assert not _beruehrt(text, bleibt), _stellen(_funde(text))


def test_lk06_gegenprobe_kompositum_ist_kein_kennwort():
    # "Passwort-Manager" ist kein Kennwort-Etikett: kein Zugangsdatum dahinter (den Produktnamen schwärzt dort
    # unabhängig davon die Namenserkennung, wie schon vorher)
    assert not _stellen(_funde("Passwort-Manager: Bitwarden"), "zugangsdaten")


# ----------------------------------------------------------------------
# LK-08: Kennung hinter "im Formular"/"im Vordruck"/"laut Anlage" – ein Fundort, kein Gegenstand mit eigener Nummer
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert", [
    ("Mitgliedsnummer im Formular: 88 1290 4473", "88 1290 4473"),
    ("Versicherungsnummer im Vordruck: 55 1290 4475", "55 1290 4475"),
    ("Versicherungsscheinnummer laut Anlage: 44 712 908", "44 712 908"),
    ("Kundennummer im beiliegenden Formular: 4471 2290", "4471 2290"),
])
def test_lk08_kennung_hinter_fundort(text, wert):
    assert _geschwaerzt(text, wert), _stellen(_funde(text))


@pytest.mark.parametrize("text, bleibt", [
    ("Nummer der Seite: 12", "12"),                                      # die Nummer der Seite selbst
    ("Versicherungsnummer im Tarif: KOMFORT 2024", "KOMFORT"),            # Tarif bleibt Gegenstand mit eigenem Wert
])
def test_lk08_gegenproben(text, bleibt):
    assert not _beruehrt(text, bleibt), _stellen(_funde(text))


# ----------------------------------------------------------------------
# LK-10: USt-IdNr. eines Versicherungsmaklers (natürliche Person) ohne "e.K."
# ----------------------------------------------------------------------
def test_lk10_ust_id_des_maklers():
    text = "Versicherungsmakler Benno Viessmann · USt-IdNr. DE298765431"
    assert _geschwaerzt(text, "DE298765431"), _stellen(_funde(text))
    for firma in ("Allianz Versicherungs-AG · USt-IdNr. DE298765431",
                  "Versicherungsmakler GmbH · USt-IdNr. DE298765431"):
        assert not _beruehrt(firma, "DE298765431"), firma


# ----------------------------------------------------------------------
# LK-11: Profilnamen hinter Zwischenwörtern, Discord-Namen, Profil-Link ohne Protokoll
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert", [
    ("Instagram-Konto der Betroffenen: romana_pointner_08", "romana_pointner_08"),
    ("Täterprofil: tiktok.com/@romana.pntr (gefälschtes Profil)", "romana.pntr"),
    ("Discord-Name des Mitschülers: Schattenwolf#4471", "Schattenwolf#4471"),
])
def test_lk11_profilnamen(text, wert):
    assert _geschwaerzt(text, wert), _stellen(_funde(text))


@pytest.mark.parametrize("text, bleibt", [
    ("Instagram: privat", "privat"),
    ("Instagram-Konto der Firma ist gesperrt: nein", "nein"),
    ("Besuchen Sie uns auf facebook.com/HUKCOBURG", "HUKCOBURG"),
])
def test_lk11_gegenproben(text, bleibt):
    assert not _beruehrt(text, bleibt), _stellen(_funde(text))


# ----------------------------------------------------------------------
# LK-12: Schweizer Anschrift mit Kantonskürzel hinter dem Ort
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert", [
    ("Neue Anschrift: Bälliz 3, 3600 Thun BE, Tel. +41 33 2211447", "3600 Thun"),
    ("Arbeitgeber in 8706 Meilen ZH seit 2019", "8706 Meilen"),
])
def test_lk12_kantonskuerzel(text, wert):
    assert _geschwaerzt(text, wert), _stellen(_funde(text))


@pytest.mark.parametrize("text", ["Es wurden 5000 Meilen gutgeschrieben.", "Wir fahren 1500 Zug um Zug."])
def test_lk12_gegenproben(text):
    assert not _stellen(_funde(text), "international"), _stellen(_funde(text))


# ----------------------------------------------------------------------
# LK-13: Kinderliste unter "Kinder:" – auch ein mehrdeutiger Vorname am Anfang des Listeneintrags
# ----------------------------------------------------------------------
def test_lk13_kinderliste_mehrdeutiger_vorname():
    text = "Kinder:\nLena, 12.03.2014\nMax, 05.09.2016"
    for datum in ("12.03.2014", "05.09.2016"):
        assert _geschwaerzt(text, datum, "geburt"), _stellen(_funde(text))
    assert not _stellen(_funde("Termine:\nMax, 05.09.2016"), "geburt")    # ohne Kinderliste kein Geburtsdatum


# ----------------------------------------------------------------------
# LK-15: Beruf der Wissensbasis unter dem Spaltenkopf "Tätigkeit" – der Nachbarkopf ist kein Beruf
# ----------------------------------------------------------------------
def test_lk15_beruf_in_taetigkeitsspalte():
    text = "Angaben zur Tätigkeit\t\tTätigkeit\t\tArbeitgeber\nseit 2014\t\tSpieleentwickler\t\tPixelhaus Studios"
    assert _geschwaerzt(text, "Spieleentwickler", "beruf"), _stellen(_funde(text))
    assert not ({"Tätigkeit", "Arbeitgeber"} & _stellen(_funde(text))), _stellen(_funde(text))
    assert _geschwaerzt("Beruf\t\tSchreiner", "Schreiner", "beruf")       # Etikett und Wert in einer Zeile


# ----------------------------------------------------------------------
# LK-16: IP-Adresse in den Kopfzeilen eines E-Mail-Ausdrucks
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "Received: from [91.12.34.59] by mout.gmx.net with ESMTPSA",
    "Received: from mail.example.de (mail.example.de [91.12.34.59]) by mx.example.net",
    "X-Originating-IP: [91.12.34.59]",
])
def test_lk16_received_ip(text):
    assert _geschwaerzt(text, "91.12.34.59"), _stellen(_funde(text))


def test_lk16_gegenprobe_vertragsnummer_mit_punkten():
    assert not _stellen(_funde("Vertrag 95.137.189.6 vom 01.02.2024"), "ip")


# ----------------------------------------------------------------------
# U7: Spartenkürzel mit SF-Klasse bzw. Selbstbeteiligung sind keine Kennzeichen
# ----------------------------------------------------------------------
def test_u7_sparten_mit_sf_und_sb_bleiben():
    text = "HP SF 12 (35 %), RS SB 150, GL SB 0, HR SB 500"
    assert not _stellen(_funde(text), "kfz"), _stellen(_funde(text))


@pytest.mark.parametrize("text, wert", [
    ("Kennzeichen: HP SF 12", "HP SF 12"),                               # hinter dem Kfz-Etikett
    ("Unfallgegner GL-SB 150 fuhr auf", "GL-SB 150"),                    # mit Bindestrich ein Kennzeichen
    ("Das Fahrzeug GL AB 150 parkte vor dem Haus", "GL AB 150"),
])
def test_u7_gegenproben_kennzeichen(text, wert):
    assert _geschwaerzt(text, wert, "kfz"), _stellen(_funde(text))


# ----------------------------------------------------------------------
# K1: Anschrift in der Formularzeile des Kunden unter einer Spartenüberschrift ist keine Firmenanschrift
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "Kfz-Versicherung\nVersicherungsnehmer: Annelie Stöberl, Kastanienallee 9, 85354 Freising",
    "Hausratversicherung\nLeasingnehmerin: Annelie Stöberl, Kastanienallee 9, 85354 Freising",
])
def test_k1_anschrift_des_kunden_unter_sparte(text):
    stellen = _stellen(_funde(text))
    assert "Kastanienallee 9" in stellen and "85354 Freising" in stellen, stellen


def test_k1_gegenprobe_firmenanschrift_bleibt():
    text = "Allianz Versicherungs-AG\nAnsprechpartner: Herr Kurt Maier, Königinstraße 28, 80802 München"
    assert not ({"Königinstraße 28", "80802 München"} & _stellen(_funde(text))), _stellen(_funde(text))


# ----------------------------------------------------------------------
# L3: Zeilen ohne Leerzeichen und riesige Lücken (vorher 16 000 Zeichen: "Ab-…" 15,5 s, ":" 27,9 s, Leerzeichen 5,9 s,
# Tabulatoren 4,3 s) – NER ohne überlange Zeichenfolgen, Organisations-, Führerschein-, Ort-Datum- und Alter-Regeln ohne
# Neustart an jeder Stelle einer Folge
# ----------------------------------------------------------------------
@pytest.mark.parametrize("muster", ["Ab-", ":", " ", "\t"])
def test_l3_pathologische_zeilen_wachsen_linear(muster):
    import zeitmessung

    def zeile(n):
        return ("A" + muster * n + "B") if muster.isspace() else muster * (n // len(muster))
    gross, klein = zeile(8000), zeile(1000)
    analysiere_text("Vertragsnummer: 12345 Max Mustermann", ALLE, [], [], profil="hoch")    # Modell laden
    wachstum, _, zeit = zeitmessung.wachstum_messen(lambda: analysiere_text(klein, ALLE, [], [], profil="hoch"),
                                                    lambda: analysiere_text(gross, ALLE, [], [], profil="hoch"), 8,
                                                    wiederholungen=1, schranke=2.0)
    print(f"{muster!r}: {zeit:.2f} s CPU, wachstum {wachstum:.2f}")
    assert wachstum < 2.0, f"Laufzeit wächst um {wachstum:.2f} x linear"


@pytest.mark.parametrize("text, wert", [
    ("Anna Berg (54)", "54"),                                             # Alter hinter dem Namen weiter erkannt
    ("München, den 01.02.2024", "München"),                               # Ort-Datum-Zeile
    ("Name\t\tMünchen, 01.02.2024", "München"),
])
def test_l3_gegenproben_regeln_greifen_weiter(text, wert):
    assert _geschwaerzt(text, wert), _stellen(_funde(text))


# ----------------------------------------------------------------------
# LK-05/LK-12: Adresszusatz zwischen Straße und PLZ + Ort derselben Zeile („3. OG links“) – sonst schlägt der Status
# der Datei um, sobald die Nachbarwerte erkannt sind (vorher nur über ein anderes _PRUEFEN sichtbar)
# ----------------------------------------------------------------------
def test_lk05_adresszusatz_zwischen_strasse_und_plz():
    text = "Mieterin: Sabine Ortner, Kaiserstraße 17, 3. OG links, 83022 Rosenheim"
    stellen = _stellen(_funde(text))
    assert {"Kaiserstraße 17", "3. OG links", "83022 Rosenheim"} <= stellen, stellen


@pytest.mark.parametrize("text, bleibt", [
    ("Allianz Versicherungs-AG · Königinstraße 28 · Haus B · 80802 München", "Haus B"),   # Firmenanschrift
    ("Kaiserstraße 17, Tel. 0171 2345678, 83022 Rosenheim", "Tel."),                    # Kontakt, kein Zusatz
])
def test_lk05_adresszusatz_gegenproben(text, bleibt):
    assert not any(bleibt in s for s in _stellen(_funde(text), "strasse")), _stellen(_funde(text))


def test_lk02_titelzeile_nur_ueber_einem_kopf_ohne_ziffern(tmp_path):
    # Scan einer Personentabelle mit zerrissener Reihe: "YAW ⇥⇥ 2019-04-18 ⇥⇥ mitversichertes Kind" ist kein Kopf
    # (Ziffern), die Reihe darunter bleibt eine Datenreihe der Tabelle (s7 066 der Endmessung)
    xs = (60, 180, 300, 420)
    elemente = _zeilen(["Name\t\tVorname\t\tGeb.-Datum\t\tRolle",
                        "MEKONNEN\t\tFATOUMATA\t\t1991-05-30\t\tVN / versicherte Person",
                        "MEKONNEN\t\tABEBE\t\t19.12.1993\t\tversicherte Person"], xs=xs)
    elemente += [(60, 80 + 3 * 16, "MEKONNEN"), (180, 80 + 4 * 16, "i")]
    elemente += _zeilen(["YAW\t\t2019-04-18\t\tmitversichertes Kind"], y=80 + 5 * 16, xs=(180, 300, 420))
    elemente += _zeilen(["MEKONNEN\t\tABENA\t\t2012-01-07\t\tmitversichertes Kind"], y=80 + 6 * 16, xs=xs)
    pdf = _pdf(tmp_path / "zerrissen.pdf", [elemente])
    assert "2012-01-07" in _pdf_stellen(_pdf_funde(pdf), "geburt"), _pdf_stellen(_pdf_funde(pdf))


# ----------------------------------------------------------------------
# Endmessung s9x 007: der Wert rechts neben einem Feldnamen ist eine eigene Wertzelle – Ankreuzzeilen der anderen
# Spalte eines Unfallberichts („Do parkte“, „El fuhr auf“: Kästchen als Buchstaben gelesen) sind Fließtext, kein Name
# ----------------------------------------------------------------------
def _scan_aus(tmp_path, elemente, name="scan.pdf"):
    vorlage = fitz.open()
    s = vorlage.new_page()
    for x, y, t in elemente:
        s.insert_text((x, y), t, fontsize=11, fontname="helv")
    pix = s.get_pixmap(dpi=200, colorspace=fitz.csGRAY)
    doc = fitz.open()
    p = doc.new_page(width=s.rect.width, height=s.rect.height)
    p.insert_image(p.rect, stream=pix.tobytes("png"))
    pdf = tmp_path / name
    doc.save(pdf)
    doc.close()
    vorlage.close()
    return pdf


@braucht_ocr
def test_wert_rechts_daneben_nur_ganze_wertzelle(tmp_path):
    from anonymisierer.ocr import OcrDienst
    # Feldname „Name“ am Zeilenende, darunter ein unlesbarer Wert („SorzeW“), rechts auf derselben Höhe die
    # Ankreuzzeilen der Spalte „Umstände“
    links = [(40, 100, "6. Versicherungsnehmer:"), (200, 100, "Name"), (40, 118, "SorzeW"), (40, 140, "Vorname"),
             (40, 158, "Divine"), (40, 180, "Anschrift"), (40, 198, "Marktplatz 8")]
    rechts = [(330, 100, "Do parkte"), (330, 118, "Oo fuhr rückwärts"), (330, 140, "El fuhr auf"),
              (330, 158, "bog rechts ab"), (330, 176, "bog links ab")]
    pdf = _scan_aus(tmp_path, links + rechts, "unfallbericht.pdf")
    with OcrDienst(prozesse=1) as dienst:
        e = analysiere_pdf(pdf, ALLE, [], [], ocr=dienst)
    stellen = _pdf_stellen(e)
    assert not any(t in ("Do", "El", "Oo") for t in stellen), stellen


@braucht_ocr
def test_wert_rechts_daneben_ganze_wertzelle_bleibt_wert(tmp_path):
    # Gegenprobe: steht rechts eine ganze Wertzelle („Do“ als Familienname, „Freitag“), bleibt sie der Wert
    from anonymisierer.ocr import OcrDienst
    elemente = [(40, 100, "6. Versicherungsnehmer:"), (200, 100, "Name"), (40, 118, "SorzeW"),
                (330, 100, "Do"), (330, 118, "Oo fuhr rückwärts"), (330, 140, "bog rechts ab")]
    pdf = _scan_aus(tmp_path, elemente, "unfallbericht_name.pdf")
    with OcrDienst(prozesse=1) as dienst:
        e = analysiere_pdf(pdf, ALLE, [], [], ocr=dienst)
    assert "Do" in _pdf_stellen(e), _pdf_stellen(e)


@braucht_ocr
def test_wert_rechts_daneben_mit_rechtsform_bleibt_wert(tmp_path):
    # Gegenprobe (Endmessung s7 037): eine kleingeschriebene Rechtsform hinter dem Wert („Elektro Schuster e.K.“) oder
    # ein Geburtsname („geb. Brandl“) gehört zur Wertzelle – nur ein klein geschriebenes Wort wie „parkte“ ist Fließtext
    from anonymisierer.ocr import OcrDienst
    links = [(50, 100, "Antrag auf Riester-Rente"), (50, 130, "Vorname:"), (50, 150, "Nachname:"),
             (50, 170, "Ausgeübter Beruf:"), (50, 190, "Arbeitgeber:"), (50, 210, "Kontoinhaber:")]
    rechts = [(330, 130, "Quang"), (330, 150, "Tran"), (330, 170, "Busfahrer"), (330, 190, "Elektro Schuster e.K."),
              (330, 210, "Mai Tran geb. Brandl")]
    pdf = _scan_aus(tmp_path, links + rechts, "antrag_arbeitgeber.pdf")
    with OcrDienst(prozesse=1) as dienst:
        e = analysiere_pdf(pdf, ALLE, [], [], ocr=dienst)
    stellen = _pdf_stellen(e)
    assert any("Elektro" in t for t in stellen), stellen
    assert any("Mai Tran" in t for t in stellen), stellen


# ----------------------------------------------------------------------
# Endmessung s7 036: Wochentag oder Monat als Familienname („Nachname: Freitag“) – hinter einem Namensfeld ist das Wort
# der Name; als Datumsangabe („am Freitag, 12.03.2025“, „Montag bis Freitag“, „im Mai 2025“) wird es nicht weitergegeben
# ----------------------------------------------------------------------
def _an_stellen(text):
    """(start, ende) aller angehakten Stellen im Text."""
    aus = set()
    for f in _funde(text):
        for st in f["stellen"]:
            if st.get("an", True):
                aus.add((st["start"], st["ende"]))
    return aus


def _stelle_an(text, wert, n=0) -> bool:
    """Liegt das n-te Vorkommen von `wert` in einer angehakten Stelle?"""
    pos = -1
    for _ in range(n + 1):
        pos = text.index(wert, pos + 1)
    return any(s <= pos and pos + len(wert) <= e for s, e in _an_stellen(text))


@pytest.mark.parametrize("text, wert", [
    ("Familienname:\t\tMontag", "Montag"),
    ("Nachname:\t\tFreitag\nGeburtsdatum:\t\t31.10.1976", "Freitag"),
    ("Name:\t\tSonntag", "Sonntag"),
    ("Geburtsname:\t\tMai", "Mai"),
])
def test_kalenderwort_als_familienname_hinter_namensfeld(text, wert):
    assert _stelle_an(text, wert), _stellen(_funde(text))


@pytest.mark.parametrize("text, name_n, datum_n, wert", [
    ("Vorname:\t\tKlaus\nNachname:\t\tFreitag\nRückruf bitte am Freitag, 12.03.2025 um 10 Uhr.", 0, 1, "Freitag"),
    ("Herr Jonas Freitag\nSprechzeiten Montag bis Freitag von 8 bis 12 Uhr.", 0, 1, "Freitag"),
    ("Familienname:\t\tMai\nDer Vertrag beginnt im Mai 2025.", 0, 1, "Mai"),
    ("Sehr geehrter Herr Freitag,\nIhre Unterlagen erhalten Sie bis Freitag, den 14.03.2025.", 0, 1, "Freitag"),
])
def test_kalenderwort_als_datum_wird_nicht_weitergegeben(text, name_n, datum_n, wert):
    assert _stelle_an(text, wert, name_n), _stellen(_funde(text))
    assert not _stelle_an(text, wert, datum_n), _stellen(_funde(text))


@pytest.mark.parametrize("text, wert", [
    ("Bürozeiten:\t\tMontag", "Montag"),                                   # kein Namensfeld
    ("Erreichbar: Montag bis Freitag", "Freitag"),
    ("Zahlungsweise:\t\tjährlich zum 1. Mai", "Mai"),
])
def test_kalenderwort_gegenproben_bleiben(text, wert):
    assert not _beruehrt(text, wert), _stellen(_funde(text))


def test_kalenderwort_name_neben_datum_bleibt_name():
    # Personenkontext geht vor: „Termin mit Herrn Freitag am Montag“ – der Name bleibt geschwärzt, der Tag nicht
    text = "Sehr geehrter Herr Freitag,\nTermin mit Herrn Freitag am Montag, 17.03.2025."
    assert _stelle_an(text, "Freitag", 0) and _stelle_an(text, "Freitag", 1), _stellen(_funde(text))
    assert not _beruehrt(text, "Montag"), _stellen(_funde(text))


# ----------------------------------------------------------------------
# D (s7 018): ein Datumstrenner als Komma verlesen oder vertippt („17,03.1968“ unter „GEB-DATUM“) – Erkennung und
# Selbstkontrolle lesen das Datum mit vierstelligem Jahr wie „17.03.1968“
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert", [
    ("NAME\t\tVORNAME\t\tGEB-DATUM\t\tROLLE\nKARACA\t\tBÜSRA\t\t15.10.1975\t\tVN / versicherte Person\n"
     "KARACA\t\tMEHMET\t\t17,03.1968\t\tversicherte Person\nKARACA\t\tDERYA\t\t12.03.2021\t\tmitversichertes Kind",
     "17,03.1968"),
    ("Geburtsdatum:\t\t17,03.1968", "17,03.1968"),
    ("Geburtsdatum: 17.03,1968", "17.03,1968"),
    ("Versicherte Person: Mehmet Karaca, geb. 17,03.1968", "17,03.1968"),
])
def test_datum_mit_komma_als_trenner(text, wert):
    assert _geschwaerzt(text, wert, "geburt"), _stellen(_funde(text))


@pytest.mark.parametrize("text, wert", [
    ("Geburtsdatum:\t\t17,03.1968", "17,03.1968"),
    ("Geb.-Datum: 17.03,1968", "17.03,1968"),
])
def test_datum_mit_komma_selbstkontrolle(text, wert):
    assert _gemeldet(text, wert), _verdacht(text)


@pytest.mark.parametrize("text, bleibt", [
    ("Rechnungsbetrag: 17,03 EUR", "17,03"),
    ("Leistungszeitraum 01,03.2025 bis 31.03.2025", "01,03.2025"),       # Datum, aber kein Geburtsdatum
    ("Beitrag 1.234,05 EUR fällig", "1.234,05"),
])
def test_datum_mit_komma_gegenproben(text, bleibt):
    assert not _beruehrt(text, bleibt), _stellen(_funde(text))
