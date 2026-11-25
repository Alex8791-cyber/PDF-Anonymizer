"""Nachbesserung 3 nach der Abnahme von integration-r7 (Stand 1b5130a).

Je Befund der Abnahme (N1–N11, dazu die widerlegten Prüfungen): die Zeile der Abnahme, Abwandlungen und Gegenproben –
nicht geheime Nachbarn bleiben lesbar. Wo eine Regel der Erkennung neu greift, prüft ein Test auch die Selbstkontrolle
(restrisiko.py) auf dem Ausgabetext. Alle Personen, Nummern und Anschriften sind frei erfunden."""

import pymupdf as fitz
import pytest

from anonymisierer import muster
from anonymisierer.analyse import analysiere_pdf, analysiere_text
from anonymisierer.restrisiko import pruefe_text

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


def _geschwaerzt(text, wert, kategorie=None, profil="hoch") -> bool:
    return any(wert in s for s in _stellen(_funde(text, profil), kategorie))


def _beruehrt(text, wert) -> bool:
    """Wird der Wert oder ein Teil davon geschwärzt?"""
    return any(wert in s or (len(s) >= 2 and s in wert) for s in _stellen(_funde(text)))


def _verdacht(text, **kw) -> list:
    return [(v.text, v.grund) for v in pruefe_text(text, **kw)]


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


def _weg_oder_gemeldet(text, wert) -> bool:
    """Ist der Wert geschwärzt – oder steht er im Ausgabetext und meldet ihn die Selbstkontrolle dort (verortet)?"""
    aus, ph = _ausgabe(text)
    if wert not in aus:
        return True
    return any(wert in t or (len(t) >= 3 and t in wert) for t, _ in _verdacht(aus, platzhalter=ph))


def _pdf(pfad, zeilen, groesse=10):
    doc = fitz.open()
    seite = doc.new_page(width=595, height=842)
    for i, zeile in enumerate(zeilen):
        seite.insert_text((60, 80 + 16 * i), zeile, fontsize=groesse, fontname="helv")
    doc.save(pfad)
    doc.close()
    return pfad


def _pdf_stellen(pfad, kategorie=None) -> set:
    erg = analysiere_pdf(pfad, ALLE, [], [], profil="hoch")
    assert not erg.get("fehler"), erg.get("fehler")
    return {st["text"] for f in erg["funde"] if kategorie is None or f["kategorie"] == kategorie
            for st in f["stellen"] if st.get("an", True)}


def _wachstum(erzeuge, klein=2000, gross=16000, schranke=2.0):
    """Wachstum der Analyse (Schutzstufe hoch) von klein auf gross Zeichen (1,0 = linear; quadratisch bis 8)."""
    import zeitmessung
    k, g = erzeuge(klein), erzeuge(gross)
    analysiere_text("Vertragsnummer: 12345 Max Mustermann", ALLE, [], [], profil="hoch")    # Modell laden
    wachstum, _, zeit = zeitmessung.wachstum_messen(lambda: analysiere_text(k, ALLE, [], [], profil="hoch"),
                                                    lambda: analysiere_text(g, ALLE, [], [], profil="hoch"),
                                                    gross // klein, wiederholungen=1, schranke=schranke)
    return wachstum, zeit


# ----------------------------------------------------------------------
# N9, N10, N11: Laufzeit langer Zeilen und vieler Zeilen – jede Form wächst linear (2 000 gegen 16 000 Zeichen)
# ----------------------------------------------------------------------
LANGE_FORMEN = {
    # N9: "Code" hinter einem Gegenstand – die Regel „Gegenstand vor Code“ durchsuchte je Treffer den Zeilenanfang
    "code_folge": lambda n: " ".join("Code der Alarmanlage" for _ in range(n // 21)),
    "code_gegenstand_folge": lambda n: " ".join("Haustür: Code 1357" for _ in range(n // 19)),
    # N11: viele Kennzeichen-Kandidaten in einer Zeile (Firmenbeleg je Treffer über den Zeilenanfang); vierstellige
    # Nummern, damit kleine und große Eingabe dieselben Treffer je Zeichen haben
    "kennzeichen_kandidaten": lambda n: " ".join(f"RO KL {1000 + i % 8999}" for i in range(n // 11)),
    # N10: die Formen der Nachprüfung B (B/NP-14..16)
    "beruf_langes_wort": lambda n: "Der Glaser X" + "a" * n + " hat",
    "ort_hinter_person_lang": lambda n: "Zeuge: Hans Maier, X" + "a" * n,
    "quadrate_zeile": lambda n: " ".join("A 1, 2" for _ in range(n // 7)),
    "quadrate_zeile_mannheim": lambda n: " ".join("A 1, 2" for _ in range(n // 7)) + " 68161 Mannheim",
    "handles_zeile": lambda n: " ".join("@home" for _ in range(n // 6)),
    "zeilenumbrueche": lambda n: "Name\n" * (n // 5),
    "segmente_folge": lambda n: ", ".join("Kaiserstraße 17" for _ in range(n // 17)) + ", 83022 Rosenheim",
    "adresszusatz_folge": lambda n: ", ".join(["Kaiserstraße 17", "3. OG links"] * (n // 30)) + ", 83022 Rosenheim",
    "geheimnis_kompositum": lambda n: " ".join("Router-Kennwort Ab-77" for _ in range(n // 21)),
    "etiketten_zeilen": lambda n: "\n".join("Vorstand: Max Muster" for _ in range(n // 21)),
}


@pytest.mark.parametrize("form", sorted(LANGE_FORMEN))
def test_n9_n10_n11_lange_formen_wachsen_linear(form):
    wachstum, zeit = _wachstum(LANGE_FORMEN[form])
    print(f"{form}: {zeit:.2f} s CPU, wachstum {wachstum:.2f}")
    assert wachstum < 2.0, f"{form}: Laufzeit wächst um {wachstum:.2f} x linear"


def _funktion_wachstum(f, erzeuge, klein, gross, schranke=2.0):
    """Wachstum einer einzelnen Funktion f(text) von klein auf gross Zeichen – ohne die Analyse drumherum, damit ein
    quadratischer Anteil nicht im linearen Rest (Texterkennung der Namen, Seitenmodell) untergeht."""
    import zeitmessung
    k, g = erzeuge(klein), erzeuge(gross)
    f(k)
    wachstum, _, zeit = zeitmessung.wachstum_messen(lambda: f(k), lambda: f(g), gross // klein, wiederholungen=1,
                                                    schranke=schranke)
    return wachstum, zeit


def _detektoren(*namen):
    """f(text): die genannten Detektoren auf einem frisch gebauten Seitenmodell des Texts (Zwischenspeicher der Seite
    zählen mit)."""
    from anonymisierer import seitenmodell, wissen
    from anonymisierer.detektoren import REGISTER, Kontext
    eintraege = [e for e in REGISTER if e.name in namen]
    assert {e.name for e in eintraege} == set(namen), [e.name for e in eintraege]
    kontext = Kontext(aktive=ALLE, profil="hoch", wissen=wissen)

    def lauf(text):
        dok = seitenmodell.dokument_aus_text(text)
        for e in eintraege:
            e.funktion(dok, kontext)
    return lauf


@pytest.mark.parametrize("form", ["code_folge", "code_gegenstand_folge"])
def test_n9_zugangsdaten_wachsen_linear(form):
    # vorher: "Code der Alarmanlage" × 3 000 in einer Zeile 12,9 s (die Regel „Gegenstand vor Code“ durchsuchte je
    # Treffer den ganzen Zeilenanfang); jetzt ein Fenster vor "Code"
    from anonymisierer import kennungsformen
    wachstum, zeit = _funktion_wachstum(kennungsformen.zugangsdaten, LANGE_FORMEN[form], 4000, 32000)
    print(f"{form}: {zeit:.3f} s CPU, wachstum {wachstum:.2f}")
    assert wachstum < 2.0, f"{form}: zugangsdaten wächst um {wachstum:.2f} x linear"


@pytest.mark.parametrize("form, namen", [
    ("zeilenumbrueche", ("struktur.etikett_wert", "struktur.adressblock")),     # Etiketten je Zeile, Kundenzeilen
    ("etiketten_zeilen", ("struktur.etikett_wert", "struktur.adressblock")),
    ("segmente_folge", ("muster.strasse", "muster.plzort")),                     # Firmenbeleg je Anschrift
    ("kennzeichen_kandidaten", ("muster.plzort", "muster.strasse")),
])
def test_n10_n11_detektoren_wachsen_linear(form, namen):
    wachstum, zeit = _funktion_wachstum(_detektoren(*namen), LANGE_FORMEN[form], 4000, 32000)
    print(f"{form} {namen}: {zeit:.3f} s CPU, wachstum {wachstum:.2f}")
    assert wachstum < 2.0, f"{form}: {namen} wachsen um {wachstum:.2f} x linear"


def test_n11_firmenbeleg_langer_zeile_wie_ausschnitt():
    """Der Firmenbeleg einer langen Zeile (_LangeZeile) gibt für jeden Anfang dasselbe Ergebnis wie firmen_beleg auf
    dem Ausschnitt – auch wenn der Schnitt in einem Beleg, mitten im Wort oder in einem Trenner liegt."""
    from anonymisierer.detektoren import struktur_adresse as SA
    zeile = ("Hauptstraße 5 · Allianz Versicherungs-AG · 80331 München, Kundenservice - Huber, Ab Ab Ab, "
             "Sparkasse Rosenheim | Müller GmbH & Co. KG; Debeka - 56073 Koblenz, Vorstand: Maier, ") * 4
    lz = SA._LangeZeile(zeile)
    for laenge in range(len(zeile)):
        assert lz.beleg_im_anfang(laenge) == bool(SA.firmen_beleg(zeile[:laenge])), (laenge, zeile[:laenge][-40:])


# ----------------------------------------------------------------------
# widerlegt-1 (s7 037): Rohwert rechts neben einem Feldnamen in einer Feldnamen-Spalte eines Scans
# ----------------------------------------------------------------------
def _ocr_formular(paare, wert_x=211.0, quelle="ocr"):
    """Seitenmodell eines gescannten Formulars mit einer Spalte aus Feldnamen (Block 0) und einer Spalte aus Werten
    (Block 1) auf denselben Höhen – so liest die Texterkennung Formulare mit Kästchen um die Werte (s7 037)."""
    from anonymisierer import seitenmodell
    doc = fitz.open()
    seite = doc.new_page(width=595, height=max(842, 500 + 19 * len(paare)))
    woerter = []
    y = 400.0
    for zi, (feld, wert) in enumerate(paare):
        x = 64.0
        for wi, w in enumerate(feld.split()):
            woerter.append((x, y, x + 5.5 * len(w), y + 7, w, 0, zi, wi))
            x += 5.5 * len(w) + 3
        if wert:
            x = wert_x
            for wi, w in enumerate(wert.split()):
                woerter.append((x, y - 1, x + 5.0 * len(w), y + 14, w, 1, zi, wi))
                x += 5.0 * len(w) + 3
        y += 19
    s = seitenmodell.seite_aufbauen(seite, 0, ocr_woerter=woerter, ocr_quelle=quelle)
    doc.close()
    return seitenmodell.Dokument(None, [s])


def test_n10_werte_rechts_daneben_wachsen_linear():
    """Viele Feldnamen links, Werte rechts daneben in eigenen Zeilen (Anhang mit Tausenden Etiketten, B/NP-16): die
    Etikett-Wert-Regel samt Rohwert rechts daneben wächst linear (100 gegen 800 Zeilen; gemessen wird die Regel, das
    Seitenmodell entsteht vorher – die Etiketten der Seite bleiben zwischengespeichert, die Werte werden je Aufruf neu
    gelesen)."""
    import zeitmessung
    from anonymisierer.detektoren import REGISTER, Kontext
    from anonymisierer import wissen
    regel = next(e for e in REGISTER if e.name == "struktur.etikett_wert")
    kontext = Kontext(aktive=ALLE, profil="hoch", wissen=wissen)

    def formular(n):
        felder = ["Kundennummer:", "Steuer-ID:", "Geburtsdatum:", "Telefon:"]
        return _ocr_formular([(felder[i % 4], f"K0 {7700 + i}-I9") for i in range(n)])
    klein, gross = formular(100), formular(800)
    regel.funktion(klein, kontext)
    regel.funktion(gross, kontext)
    wachstum, _, zeit = zeitmessung.wachstum_messen(lambda: regel.funktion(klein, kontext),
                                                    lambda: regel.funktion(gross, kontext), 8,
                                                    wiederholungen=1, schranke=2.0)
    print(f"Formular 800 Zeilen: {zeit:.3f} s CPU, wachstum {wachstum:.2f}")
    assert wachstum < 2.0, f"etikett_wert wächst um {wachstum:.2f} x linear"


def _ocr_formular_stellen(paare, kategorie=None) -> set:
    from anonymisierer import analyse
    funde = analyse._analysiere_dokument(_ocr_formular(paare), ALLE, [], [])
    return {st["text"] for f in funde if kategorie is None or f["kategorie"] == kategorie
            for st in f["stellen"] if st.get("an", True)}


_FORMULAR_037 = [("Arbeitgeber:", "Elektro Schuster eK"), ("Steuer-ID:", "Bız11sar066"),
                 ("Sozialversicherungsnummer:", "1131011841351"), ("Ausweisnummer:", "IVowemeKıX6 —")]


def test_widerlegt1_verlesener_wert_rechts_neben_feldname():
    """s7 037: Die Texterkennung liest die Steuer-ID im Kästchen als 'Bız11sar066'; keine Wertform passt, der Wert
    steht trotzdem rechts neben „Steuer-ID:“ – als Rohwert geschwärzt (wie ocr_rohwert in der Zeile oder darunter)."""
    stellen = _ocr_formular_stellen(_FORMULAR_037)
    assert any("Bız11sar066" in s for s in stellen), stellen


@pytest.mark.parametrize("feld, wert", [
    ("Steuer-ID:", "ö81 2115 47O66"),              # andere Verlesung, Leerzeichen
    ("Kundennummer:", "K0 7743-I9"),
    ("Geburtsdatum:", "110.11.1984"),               # Kästchenrand als „1“ vor dem Datum
])
def test_widerlegt1_abwandlungen(feld, wert):
    paare = [("Arbeitgeber:", "Elektro Schuster eK"), (feld, wert), ("Sozialversicherungsnummer:", "1131011841351")]
    stellen = _ocr_formular_stellen(paare)
    assert any(wert.split()[0] in s for s in stellen), stellen


@pytest.mark.parametrize("wert", ["entfällt", "siehe Anlage", "bitte angeben", "Sozialversicherungsnummer:"])
def test_widerlegt1_gegenproben_kein_rohwert(wert):
    """Füllwerte, Hinweise und das nächste Feld rechts daneben bleiben stehen."""
    paare = [("Arbeitgeber:", "Elektro Schuster eK"), ("Steuer-ID:", wert), ("Ausweisnummer:", "")]
    assert not any(wert.split()[0] in s for s in _ocr_formular_stellen(paare)), _ocr_formular_stellen(paare)


# ----------------------------------------------------------------------
# N1 (A/NP-13): Zugangsdaten hinter "<Gegenstand>: Code"
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert", [
    ("Hinweise für den Handwerker\nHaustür: Code 1357\nBitte die Tür abschließen.", "1357"),
    ("Tor zur Tiefgarage: Code 4455", "4455"),
    ("Garage: Code 1199", "1199"),
    ("Alarmanlage: Code 2580", "2580"),
    ("Schlüsselkasten am Gartentor: Code 8642", "8642"),
    ("Briefkasten: Code 0815", "0815"),
    ("Haustür: Code: 7788", "7788"),
])
def test_n1_gegenstand_mit_doppelpunkt_vor_code(text, wert):
    assert _geschwaerzt(text, wert, "zugangsdaten"), _stellen(_funde(text))
    assert _weg_oder_gemeldet(text, wert)


@pytest.mark.parametrize("text, wert", [
    ("Bestellung: Code 1234", "1234"),
    ("Tarif: Code HR-PREMIUM", "HR-PREMIUM"),
    ("Haustür: Code fehlt noch", "fehlt"),
    ("Rabatt: Code SOMMER10", "SOMMER10"),
])
def test_n1_gegenproben_kein_zugangscode(text, wert):
    assert not _geschwaerzt(text, wert, "zugangsdaten"), _stellen(_funde(text))


def test_n1_selbstkontrolle_meldet_code_hinter_gegenstand():
    """Die Selbstkontrolle nutzt dieselbe Regel: steht der Code in einer Ausgabe noch da, wird er gemeldet."""
    assert any("1357" in t for t, _ in _verdacht("Haustür: Code 1357")), _verdacht("Haustür: Code 1357")


# ----------------------------------------------------------------------
# N2 (A/NP-14): Hausname mit Schadenwort oder Ortsangabe dahinter
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, name", [
    ("Wasserschaden beim Stögerbauer in Inzell.", "Stögerbauer"),
    ("In der Nacht brannte es beim Moarhofer in Teisendorf.", "Moarhofer"),
    ("Beim Stögerbauer in Inzell brannte es.", "Stögerbauer"),
    ("Vom Huberbauer in Anger aus fuhr er los.", "Huberbauer"),
    ("Er fuhr zum Huberbauer nach Anger.", "Huberbauer"),
    ("Sturmschaden beim Wastlbauer, das Dach ist abgedeckt.", "Wastlbauer"),
    ("Hagelschaden am Stadel vom Moarhofer.", "Moarhofer"),
])
def test_n2_hausname_mit_schaden_oder_ort(text, name):
    assert _geschwaerzt(text, name, "namen"), _stellen(_funde(text))


@pytest.mark.parametrize("text, wort", [
    ("Wasserschaden beim Wertstoffhof in Inzell.", "Wertstoffhof"),
    ("Einbruch beim Bäcker in Inzell.", "Bäcker"),
    ("Er fuhr zum Wertstoffhof nach Anger.", "Wertstoffhof"),
    ("Beim Rangieren in Inzell brannte es.", "Rangieren"),
    ("Er fuhr zum Arzt nach Rosenheim.", "Arzt"),
    ("Zum Schaden kam es beim Einparken in Traunstein.", "Einparken"),
    ("Er fuhr zum Discounter nach Rosenheim.", "Discounter"),       # Ortsangabe nur mit Hausnamen-Endung
])
def test_n2_gegenproben(text, wort):
    assert not _beruehrt(text, wort), _stellen(_funde(text))


# ----------------------------------------------------------------------
# N3 (A/NP-12): Beruf im Satz – "ist als … tätig", "Tätig als …", "verdient ihr Geld als …"
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, beruf", [
    ("Die versicherte Person ist als Dachdecker tätig.", "Dachdecker"),
    ("Sie verdient ihr Geld als Hebamme.", "Hebamme"),
    ("Tätig als Dachdecker seit 2015.", "Dachdecker"),
    ("Er war bis 2020 als Schreiner tätig.", "Schreiner"),
    ("Sie ist seit März als selbständige Hebamme in Traunstein tätig.", "Hebamme"),
    ("Er hat zehn Jahre als Dachdecker gearbeitet.", "Dachdecker"),
    ("Arbeitet als Hufschmiedin im Nebenerwerb.", "Hufschmiedin"),
])
def test_n3_beruf_im_satz(text, beruf):
    assert _geschwaerzt(text, beruf, "beruf"), _stellen(_funde(text))


@pytest.mark.parametrize("text, wort", [
    ("Wir sind als Makler für Sie tätig.", "Makler"),          # Rolle des Maklers selbst (nur hinter Etikett)
    ("Herr X war als Fahrer am Unfall beteiligt.", "Fahrer"),   # Rolle im Unfall, keine Erwerbstätigkeit
    ("Er ist als Zeuge tätig geworden.", "Zeuge"),
    ("Als Gutachter wurde Herr Huber bestellt.", "Gutachter"),
])
def test_n3_gegenproben(text, wort):
    assert not _geschwaerzt(text, wort, "beruf"), _stellen(_funde(text))


# ----------------------------------------------------------------------
# N4 (A/NP-07): Mannheimer Quadrat hinter "nach"/"in" mit dem Umzug dahinter
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert", [
    ("Die Versicherungsnehmerin ist im Mai nach S 2, 15 umgezogen.", "S 2, 15"),
    ("Sie ist nach S 2, 15 gezogen.", "S 2, 15"),
    ("Herr Brandl ist zum 1. Juli nach R 7, 3 verzogen.", "R 7, 3"),
    ("Die Familie ist in K 4, 12 gemeldet.", "K 4, 12"),
])
def test_n4_quadrat_mit_umzug_dahinter(text, wert):
    assert _geschwaerzt(text, wert), _stellen(_funde(text))


@pytest.mark.parametrize("text, wert", [
    ("Es gelten A 2, 3 und B 1, 4 der AVB.", "B 1, 4"),
    ("Er fuhr nach A 8, 3 km Stau weiter.", "A 8, 3"),
    ("Wir sind nach B 2, 4 der Bedingungen verpflichtet.", "B 2, 4"),
])
def test_n4_gegenproben(text, wert):
    assert not _beruehrt(text, wert), _stellen(_funde(text))


def test_n4_selbstkontrolle_meldet_quadrat_hinter_nach():
    """Ohne Umzugswort dahinter meldet die Selbstkontrolle das Quadrat hinter "nach" verortet (wie hinter "in")."""
    text = "Die Unterlagen gehen nach S 2, 15 zur Prüfung."
    assert any("S 2, 15" in t for t, _ in _verdacht(text)), _verdacht(text)


# ----------------------------------------------------------------------
# N5 (LK-14): unbekannter Familienname auf -er hinter Personen-Verb + Artikel – verortet gemeldet
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, name", [
    ("Am Steuer saß der Hinterstoißer und telefonierte.", "Hinterstoißer"),
    ("Laut Polizei lenkte der Hinterstoißer den Wagen.", "Hinterstoißer"),
    ("Laut Polizei lenkte der Hinterstoißer.", "Hinterstoißer"),
    ("Dann sagte die Wimmer, sie habe nichts gesehen.", "Wimmer"),
])
def test_n5_familienname_hinter_personenverb_gemeldet(text, name):
    assert _weg_oder_gemeldet(text, name), _verdacht(text)


@pytest.mark.parametrize("text, wort", [
    ("Am Steuer saß der Beifahrer und telefonierte.", "Beifahrer"),
    ("Laut Polizei lenkte der Fahrer den Wagen.", "Fahrer"),
    ("Am Steuer saß der Gutachter.", "Gutachter"),
    ("Dann fuhr der Busfahrer los.", "Busfahrer"),
    ("Danach rief der Mieter die Feuerwehr.", "Mieter"),
    ("Am Steuer saß der Halter.", "Halter"),
])
def test_n5_gegenproben_keine_meldung(text, wort):
    assert not any(wort in t for t, _ in _verdacht(text)), _verdacht(text)


# ----------------------------------------------------------------------
# N6 (A/NP-03): Grußformel mit Herkunft ("Grüße aus dem Allgäu", "Schöne Grüße aus dem Urlaub")
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, name", [
    ("Liebe Frau Berger,\nanbei die Fotos vom Hagelschaden am Wintergarten.\nGrüße aus dem Allgäu\nNeff", "Neff"),
    ("Schöne Grüße aus dem Urlaub\nRowenta", "Rowenta"),
    ("Sonnige Grüße aus Rimini\nMiele", "Miele"),
    ("Gruß vom Chiemsee\nLiebherr", "Liebherr"),
    ("Grüße aus Prien am Chiemsee\nRosa Brandlhuber", "Brandlhuber"),
])
def test_n6_name_unter_gruss_mit_herkunft(text, name):
    assert _weg_oder_gemeldet(text, name), (_stellen(_funde(text)), _verdacht(_ausgabe(text)[0]))


@pytest.mark.parametrize("text, wort", [
    ("Wir senden Grüße aus dem Allgäu an alle Kunden.\nIhr Team", "Team"),
    ("Grüße aus dem Allgäu\nDie Wanderung war schön, das Wetter auch.", "Wanderung"),
])
def test_n6_gegenproben(text, wort):
    assert not _beruehrt(text, wort), _stellen(_funde(text))


def test_n6_grusszeile_erkennt_herkunft():
    from anonymisierer import personenkontext
    from anonymisierer.restrisiko import ist_grussformel
    for zeile in ("Grüße aus dem Allgäu", "Schöne Grüße aus dem Urlaub", "Gruß vom Chiemsee"):
        assert personenkontext.ist_gruss_zeile(zeile) and ist_grussformel(zeile), zeile
    for zeile in ("Gruß an die Familie und die Kinder, wir sehen uns", "Der Grüße wegen"):
        assert not personenkontext.GRUSS_ZEILE_RE.match(zeile), zeile


# ----------------------------------------------------------------------
# N7: Name hinter einem Personenwort ohne Begleiter ("Laut Nachbar Grohe …")
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, name", [
    ("Laut Nachbar Grohe war das Hoftor die ganze Nacht offen.", "Grohe"),
    ("Rücksprache mit Nachbar Grohe am Montag.", "Grohe"),
    ("Laut Zeugin Zwickelsdorfer kam der Wagen von links.", "Zwickelsdorfer"),
    ("Schadenmeldung über Kollege Wimmelbacher.", "Wimmelbacher"),
])
def test_n7_name_hinter_personenwort(text, name):
    assert _geschwaerzt(text, name, "namen"), _stellen(_funde(text))


@pytest.mark.parametrize("text, wort", [
    ("Laut Nachbar Wasserschaden war alles nass.", "Wasserschaden"),
    ("Kunden Service: 0800 123456", "Service"),
    ("Laut Zeuge Polizei war es dunkel.", "Polizei"),
    ("Kollege Montag kommt später.", "Montag"),
    ("Mieter\t\tObjekt\t\tMiete\nHuber\t\tWohnung 3\t\t850 EUR", "Objekt"),
    ("Er hat dem Nachbarn Wasser abgegraben.", "Wasser"),          # Begleiter vor dem Personenwort: ein Satzteil
    ("Beim Nachbarn Regen gemessen.", "Regen"),
])
def test_n7_gegenproben(text, wort):
    assert not _beruehrt(text, wort), _stellen(_funde(text))


# ----------------------------------------------------------------------
# N8 (A/NP-09): "Fortsetzung umseitig" kündigt die Fortsetzung einer Personentabelle an
# ----------------------------------------------------------------------
_KINDER_SEITE1 = ["Mitversicherte Kinder", "", "Familienname\t\tRufname\t\tgeboren am",
                  "Mooshammer\t\tVeronika\t\t02.02.2011"]
_KINDER_SEITE2 = ["Gschwendtner\t\tKreszenz\t\t09.09.2014", "Mooshammer\t\tLudwig\t\t21.03.2017"]


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


@pytest.mark.parametrize("hinweis", ["Fortsetzung umseitig", "Weitere Kinder umseitig", "Fortsetzung umstehend",
                                     "Fortsetzung nächste Seite", "Fortsetzung Rückseite"])
def test_n8_fortsetzung_umseitig(tmp_path, hinweis):
    pdf = _pdf_seiten(tmp_path / "kinder.pdf", [_KINDER_SEITE1 + [hinweis], _KINDER_SEITE2])
    stellen = _pdf_stellen(pdf)
    assert {"09.09.2014", "21.03.2017"} <= stellen, stellen


def test_n8_gegenprobe_umseitige_bedingungen(tmp_path):
    """"Die umseitigen Bedingungen" kündigt keine Tabelle an: eine Terminliste auf der Folgeseite bleibt lesbar."""
    pdf = _pdf_seiten(tmp_path / "termine.pdf", [_KINDER_SEITE1 + ["Es gelten die umseitigen Bedingungen."],
                                                 ["Beratung\t\tHausrat\t\t16.04.2026", "Angebot\t\tKfz\t\t18.04.2026"]])
    assert not ({"Beratung", "16.04.2026"} & _pdf_stellen(pdf))
