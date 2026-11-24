"""Nachbesserung nach der Gegenprüfung der Zusammenführung (Runde 5, integration-r7).

Je Befund: die Zeile der Prüfer (Leck bzw. Über-Schwärzung), Abwandlungen und Gegenproben – nicht geheime Nachbarn
bleiben lesbar. Wo eine Regel der Erkennung neu greift, prüft ein Test auch die Selbstkontrolle (restrisiko.py): bliebe
der Wert stehen, muss sie ihn melden. Alle Personen, Nummern und Anschriften sind frei erfunden."""

import pymupdf as fitz
import pytest

from anonymisierer import muster
from anonymisierer.analyse import analysiere_pdf, analysiere_text
from anonymisierer.restrisiko import pruefe_text, restrisiko_pruefen
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
