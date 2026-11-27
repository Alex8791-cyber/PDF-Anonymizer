"""Nachbesserung 9 nach der siebten Abnahme von integration-r7 (Stand 6f2d08f, Abschlussrunde: nur Verschärfungen).

Je Befund der Abnahme (Lecks A7-01 bis A7-19, Über-Schwärzung, Laufzeit und Doku A7U-01 bis A7U-14) die Zeilen der
Abnahme, eigene Abwandlungen und Gegenproben. Grundsatz P0: für jeden möglichen geheimen Wert ist das Ergebnis mindestens
so schützend wie auf 6f2d08f (geschwärzt > gemeldet > frei); Ausnahmen der Nachbesserungen 7 und 8, die still frei
ließen, stufen nur noch auf "melden" herab; gegen Über-Schwärzung nur schwärzen -> melden. Alle Personen, Codes,
Nummern und Anschriften sind frei erfunden."""

import re

import pytest

from anonymisierer import detektoren, kammraster, kennungsformen, muster, restrisiko, seitenmodell
from anonymisierer.analyse import analysiere_text
from anonymisierer.detektoren import Kontext, struktur_adresse
from anonymisierer.restrisiko import pruefe_text

ALLE = {k for k, _, _, _, an in muster.KATEGORIEN if an}


# ----------------------------------------------------------------------
# Hilfsfunktionen (wie tests/test_abnahme6_r7.py)
# ----------------------------------------------------------------------
def _funde(text, profil="hoch"):
    return analysiere_text(text, ALLE, [], [], profil=profil)


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
    # ein Wert aus einem Buchstaben steckt sonst im Platzhalter ("A" in "[NAMEN]")
    rest = re.sub(r"\[[A-ZÄÖÜ_]+\]", "", aus)
    if not re.search(r"(?<![\wäöüß])" + re.escape(wert) + r"(?![\wäöüß])", rest):
        return "weg"
    if any(wert in t or (len(t) >= 3 and t in wert) for t, _ in _verdacht(aus, platzhalter=ph)):
        return "gemeldet"
    return "frei"


def _kamm(text):
    """Treffer von struktur.kammfeld auf der Textebene."""
    funktion = next(e for e in detektoren.REGISTER if e.name == "struktur.kammfeld").funktion
    dok = seitenmodell.dokument_aus_text(text)
    return {(t.kategorie, dok.text[t.start:t.ende]) for t in funktion(dok, Kontext(ALLE, "hoch"))}


def _wachstum(klein, gross, faktor, schranke):
    import zeitmessung
    klein()
    return zeitmessung.wachstum_messen(klein, gross, faktor, wiederholungen=1, schranke=schranke)


def _zeile(baustein, n):
    return baustein * max(1, n // len(baustein))


# ----------------------------------------------------------------------
# Zeilen der Abnahme 7 und eigene Abwandlungen je Befund. Art:
#   g (geheim): soll "weg" -> geschwärzt; soll "gemeldet" -> geschwärzt oder gemeldet, nie still.
#   m (mehrdeutig, geheim oder nicht): genau gemeldet – nie still, nie geschwärzt (Tausch weg -> gemeldet gegen einen
#     Bezugsstand oder Gestalt eines nicht geheimen Werts der Über-Proben).
#   b (nicht geheim): soll "frei" -> frei; soll "gemeldet" -> frei oder gemeldet, nie geschwärzt.
# ----------------------------------------------------------------------
FAELLE = [
    # A7-01: Bedienung eines Alarms mit Person/Rolle/Name als Satzgegenstand -> geschwärzt; fremdes Ding -> gemeldet
    ("A7-01", "Den Feueralarm schaltete der Hausmeister mit dem Code 3407 ab.", "3407", "g", "weg"),
    ("A7-01", "Den Rauchalarm schaltet Frau Gruber mit Code 6614 aus.", "6614", "g", "weg"),
    ("A7-01", "Den Brandalarm hat der Techniker gestern mit dem Code 8519 abgeschaltet.", "8519", "g", "gemeldet"),
    ("A7-01", "Den Feueralarm schaltete Herr Xyzzl mit dem Code 4410 ab.", "4410", "g", "weg"),
    ("A7-01", "Den Rauchalarm schaltete unsere Nachbarin Wimmer mit dem Code 2391 aus.", "2391", "g", "gemeldet"),
    ("A7-01", "Den Feueralarm schaltete die Feuerwehr mit dem Code 5530 ab.", "5530", "g", "weg"),
    ("A7-01", "Den Probealarm schaltete der Wachdienst mit dem Code 7712 ab.", "7712", "g", "weg"),
    ("A7-01", "Nach dem Rauchalarm schaltete die Feuerwehr die Lüftung mit dem Code 4471 ab.", "4471", "m", ""),
    ("A7-01", "Nach dem Rauchalarmcode 4471 schaltete die Feuerwehr die Lüftung ab.", "4471", "b", "gemeldet"),
    # A7-02: Alarmcode mit Protokoll, Bericht oder Uhrzeit -> gemeldet wie auf 6c0c464; mit Übergabe, Empfänger oder
    # Geheimhaltung im Satz (auch im Satzteil hinter ";") ein Zugangscode -> geschwärzt wie auf fbd755b
    ("A7-02", "Der Feueralarmcode 3418 steht im Übergabeprotokoll für den neuen Hausmeister.", "3418", "g", "weg"),
    ("A7-02", "Den Rauchalarmcode 5306 hat der Hausmeister um 18:30 Uhr erhalten.", "5306", "g", "weg"),
    ("A7-02", "Der Brandmeldeanlagecode 6873 ist im Wartungsbericht vermerkt; bitte vertraulich behandeln.", "6873", "g",
     "weg"),
    ("A7-02", "Brandalarm-Code 8871 wurde im Einweisungsprotokoll an die Mieter weitergegeben.", "8871", "g", "weg"),
    ("A7-02", "Feueralarmcode 4805 – Ursache für die Änderung: neuer Hausmeister.", "4805", "g", "weg"),
    ("A7-02", "Feueralarmcode 5888 (nur für Haus 2)", "5888", "m", ""),
    ("A7-02", "Der Brandalarm-Code 2297 wurde um 14:20 Uhr ausgelöst.", "2297", "m", ""),
    ("A7-02", "Fehlalarmcode 7310 laut Protokoll der Brandmeldeanlage, Ursache Wasserdampf.", "7310", "m", ""),
    ("A7-02", "Feueralarmcode 3401", "3401", "m", ""),
    ("A7-02", "Zum Abschalten des Feueralarms: 3401", "3401", "g", "weg"),
    ("A7-02", "Der Feueralarm wird mit dem Code 1412 quittiert.", "1412", "g", "weg"),
    ("A7-02", "Bei der Wartung wurde der Sabotagealarm (Code 2297) ausgelöst und protokolliert.", "2297", "g", "weg"),
    # A7-03: Schlüssel-, Mieter-, Dienstplan-Liste und Baustelle sind kein Planbezug; Planbezug nur -> melden
    ("A7-03", "Der Werkstattcode 4429 für die Baustelle wurde geändert.", "4429", "g", "weg"),
    ("A7-03", "Kellercode 1127 laut Schlüsselliste", "1127", "g", "weg"),
    ("A7-03", "Lagercode 7748 gemäß Dienstplan an Herrn Krause übergeben.", "7748", "g", "weg"),
    ("A7-03", "Zugangscode Kellerabteil 5518 laut Mieterliste", "5518", "g", "weg"),
    ("A7-03", "Raumcode 2017 laut Raumbuch", "2017", "m", ""),
    ("A7-03", "Lagercode 4410 laut Kostenstellenplan", "4410", "m", ""),
    ("A7-03", "Werkstattcode 4420 für die Abrechnung", "4420", "m", ""),
    ("A7-03", "PIN für Heizungsraum 3845 laut Einsatzplan", "3845", "g", "weg"),
    ("A7-03", "PIN für Lagerraum 2923 laut Belegungsplan", "2923", "g", "weg"),
    # A7-04: Störungswort nur Herabstufung, Bedienung im Satz -> geschwärzt
    ("A7-04", "Für die Garage gilt der Code GT48, laut Hausmeister seit der Störung neu.", "GT48", "g", "weg"),
    ("A7-04", "Die Hintertür öffnet man mit dem Code QW62; der Fehler am Türöffner ist behoben.", "QW62", "g", "weg"),
    ("A7-04", "Der Code der Haustür lautet KM317 (nach dem Defekt neu vergeben).", "KM317", "g", "weg"),
    ("A7-04", "Garage: Code GT48 (nach der Störung neu)", "GT48", "g", "weg"),
    ("A7-04", "Code Hoftür KZ700 – seit dem Ausfall der Klingel neu.", "KZ700", "g", "weg"),
    ("A7-04", "Code E-04 an der Türsprechanlage, Elektriker beauftragt.", "E-04", "b", "gemeldet"),
    ("A7-04", "Das Rolltor hat den Code E125, laut Hersteller Überlast am Motor.", "E125", "b", "gemeldet"),
    # A7-05, A7U-01: Allerweltswort hinter Personenwort vor Verb des Gebens -> nie frei
    ("A7-05", "Danach Kunde Regen zur Prüfung übergeben.", "Regen", "m", ""),
    ("A7-05", "Heute Mieterin Wald zur Unterschrift vorgelegt.", "Wald", "m", ""),
    ("A7-05", "Gestern Kunde Morgen per Post zugeschickt.", "Morgen", "m", ""),
    ("A7U-01", "Die Schlüssel haben wir gestern Nachbar Wasser übergeben.", "Wasser", "g", "weg"),
    ("A7U-01", "Den Kostenvoranschlag hat Kollegin Regen erhalten.", "Regen", "g", "weg"),
    ("A7U-01", "Den Schlüssel heute Nachbarin Regen übergeben.", "Regen", "g", "weg"),
    ("A7U-01", "Die Vollmacht wurde Kunde Morgen vorgelegt.", "Morgen", "m", ""),
    ("A7U-01", "Heute Nachbar Wasser geschickt.", "Wasser", "m", ""),
    ("A7U-01", "Heute Nachbarin Regen gegeben.", "Regen", "m", ""),
    ("A7U-01", "Heute Kunde Bescheid gegeben.", "Bescheid", "b", "gemeldet"),
    ("A7U-01", "Gestern Kollege Vorgang erläutert und Wiedervorlage gesetzt.", "Vorgang", "b", "frei"),
    ("A7U-01", "Gestern Kollege Vorgang erläutert und Wiedervorlage gesetzt.", "Wiedervorlage", "b", "frei"),
    # A7U-02: Genitiv dahinter ist kein Gegenbeleg
    ("A7U-02", "Wir haben Mieter Wasser des Erdgeschosses informiert.", "Wasser", "m", ""),
    ("A7U-02", "Wir haben Mieterin Regen des Hinterhauses informiert.", "Regen", "g", "weg"),
    ("A7U-02", "Wir empfehlen Kunden Abschluss einer Elementarschadenversicherung.", "Abschluss", "b", "gemeldet"),
    # A7-06: Geheimnis-Hauptwort hinter der Jahreszahl ("Kombination", "Ziffernfolge", "Kennwort")
    ("A7-06", "Der Tresor ist mit 1984 eingestellter Kombination verschlossen.", "1984", "g", "weg"),
    ("A7-06", "Das Schließfach wird mit 2011 eingegebener Ziffernfolge geöffnet.", "2011", "g", "weg"),
    ("A7-06", "Die Garage öffnen Sie mit 1975 programmierter Zahlenkombination.", "1975", "g", "weg"),
    ("A7-06", "Das Hoftor öffnet man mit 2008 hinterlegtem Kennwort.", "2008", "g", "weg"),
    ("A7-06", "Das Einfahrtstor öffnen Sie mit 1968 vereinbartem Zahlenschlüssel.", "1968", "g", "weg"),
    ("A7-06", "Die Lagerhalle ist mit 2021 neu installierter Alarmanlage gesichert.", "2021", "b", "gemeldet"),
    ("A7-06", "Das Lager ist mit 2021 erneuerter elektronischer Schließanlage gesichert.", "2021", "b", "frei"),
    ("A7-06", "Die Scheune ist mit 1998 sanierten Toren verschlossen.", "1998", "b", "frei"),
    # A7-07, A7U-03: Hofname aus gewöhnlichem Wort oder Beruf -> gemeldet wie auf 6c0c464
    ("A7-07", "Beim Waldhof ist der Stadel abgebrannt.", "Waldhof", "m", ""),
    ("A7-07", "Vom Seehof kam der Anruf wegen des Hagelschadens.", "Seehof", "m", ""),
    ("A7-07", "Zum Feldhof fährt der Gutachter morgen.", "Feldhof", "m", ""),
    ("A7U-03", "Vom Schmiedhof kam der Anruf wegen des Hagelschadens.", "Schmiedhof", "m", ""),
    ("A7U-03", "Beim Jägerhof ist der Stadel abgebrannt.", "Jägerhof", "m", ""),
    ("A7U-03", "Vom Wirtshof meldete sich die Tochter wegen des Schadens.", "Wirtshof", "m", ""),
    ("A7U-03", "Beim Gärtnerhof ist der Stadel abgebrannt.", "Gärtnerhof", "m", ""),
    ("A7U-03", "Die Kühe vom Nachbarhof standen auf der Straße.", "Nachbarhof", "b", "gemeldet"),
    # vorbestehend (auch auf 6c0c464 still): Hofname mit einem Schadenswort in der Zeile -> gemeldet
    ("A7U-03", "Beim Gärtnerhof wurden die Gewächshäuser beschädigt.", "Gärtnerhof", "m", ""),
    ("A7U-03", "Beim Metzgerhof wurde das Hoftor beschädigt.", "Metzgerhof", "m", ""),
    ("A7U-03", "Vom Försterhof wurden zwei Gewächshäuser zerstört.", "Försterhof", "m", ""),
    ("A7U-03", "Beim Transport wurden die Gewächshäuser beschädigt.", "Transport", "b", "gemeldet"),
    ("A7U-03", "Beim Umzug wurde der Schrank beschädigt.", "Umzug", "b", "frei"),
    ("A7U-03", "Beim Rangieren wurde das Hoftor beschädigt.", "Rangieren", "b", "frei"),
    ("A7U-03", "Beim Gärtnerhof gibt es frisches Gemüse.", "Gärtnerhof", "b", "gemeldet"),
    # A7-08: Endungsmuster einer Einrichtung ist kein Gegenbeleg
    ("A7-08", "Der Lapp hat angerufen.", "Lapp", "m", ""),
    ("A7-08", "Die Happ hat den Schaden gemeldet.", "Happ", "m", ""),
    ("A7-08", "Der Bahn hat angerufen.", "Bahn", "m", ""),
    ("A7-08", "Die Stapp hat den Schaden gemeldet.", "Stapp", "m", ""),
    ("A7-08", "Der Rostor hat angerufen.", "Rostor", "m", ""),
    ("A7-08", "Die Bank hat angerufen und um die Unterlagen gebeten.", "Bank", "b", "gemeldet"),
    # A7-09: Geräte-Grundwort allein mit Geräteschaden -> gemeldet
    ("A7-09", "Der Mixer hat den Kabelbrand verursacht.", "Mixer", "m", ""),
    ("A7-09", "Der Zünder verursachte den Kurzschluss.", "Zünder", "m", ""),
    ("A7-09", "Der Trimmer hat den Kurzschluss verursacht.", "Trimmer", "m", ""),
    ("A7-09", "Der Sauger hat den Kabelbrand verursacht.", "Sauger", "m", ""),
    ("A7-09", "Der Mäher hat den Kurzschluss verursacht.", "Mäher", "m", ""),
    ("A7-09", "Der Hochdruckreiniger hat die Fassadendämmung beschädigt.", "Hochdruckreiniger", "b", "frei"),
    # A7-10: finites Bedienverb vor "mit <Jahreszahl>" -> geschwärzt trotz Beiwortgruppe dahinter
    ("A7-10", "Die Kellertür öffnen Sie mit 1990 bitte nur bei geschlossener Haustür.", "1990", "g", "weg"),
    ("A7-10", "Die Hintertür sperrt man mit 1987 auf, bei starkem Regen bitte die Seitentür nehmen.", "1987", "g", "weg"),
    ("A7-10", "Das Garagentor öffnet sich mit 2014 nur bei eingeschalteter Beleuchtung.", "2014", "g", "weg"),
    ("A7-10", "Den Tresor öffnen Sie mit 1963 nur unter fachkundiger Aufsicht.", "1963", "g", "weg"),
    ("A7-10", "Das Hoftor lässt sich mit 1973 und nach erfolgter Anmeldung öffnen.", "1973", "g", "weg"),
    ("A7-10", "Der Tresor lässt sich mit 1984 und bei geschlossener Haustür öffnen.", "1984", "g", "weg"),
    # A7-11, A7U-13 a: Subjekt eines Personenverbs bzw. Person als Gegenstand -> geschwärzt
    ("A7-11", "Gestern hat Nachbar Regen den Schaden gemeldet.", "Regen", "g", "weg"),
    ("A7-11", "Am Montag hat Kundin Wasser die Unterlagen unterschrieben.", "Wasser", "g", "weg"),
    ("A7-11", "Danach will Vermieter Regen die Rechnung einreichen.", "Regen", "g", "weg"),
    ("A7-11", "Laut Akte hat Vermieter Wasser das Protokoll gemeldet.", "Wasser", "g", "weg"),
    ("A7-11", "Er zeigte Kollegen Fotos.", "Fotos", "b", "gemeldet"),
    ("A7U-13", "Gestern Nachbar Regen angerufen.", "Regen", "g", "weg"),
    ("A7U-13", "Heute Zeuge Wasser vernommen.", "Wasser", "g", "weg"),
    # A7-12: Gerät zeigt "uns" den Code, Bedienung im selben Satz -> geschwärzt
    ("A7-12", "Das Garagentor meldete uns den Code 3017, damit lässt es sich öffnen.", "3017", "g", "weg"),
    ("A7-12", "Die Schließanlage zeigte uns den Code 4402, mit dem wir die Tür öffneten.", "4402", "g", "weg"),
    ("A7-12", "Das Garagentor meldete uns den Code 3017, der Monteur kommt morgen.", "3017", "b", "frei"),
    # A7-14: Bestimmungswort + Verb nur mit gewöhnlichem Bestimmungswort ein substantiviertes Verb
    ("A7-14", "Beim Wollesen ist der Stadel abgebrannt.", "Wollesen", "m", ""),
    ("A7-14", "Vom Friessen kam der Anruf wegen des Hagelschadens.", "Friessen", "m", ""),
    ("A7-14", "Beim Hollesen ist in der Nacht eingebrochen worden.", "Hollesen", "m", ""),
    ("A7-14", "Beim Radfahren ist der Kunde gestürzt.", "Radfahren", "b", "frei"),
    # A7-15: unbekanntes Wort hinter Präposition und Artikel -> gemeldet (Kehrseite: unbekannte Sachwörter auch)
    ("A7-15", "Laut dem Pfanzelt hat der Nachbar den Unfall verursacht.", "Pfanzelt", "m", ""),
    ("A7-15", "Mit dem Kolat war der Kunde verabredet.", "Kolat", "m", ""),
    ("A7-15", "Neben dem Waltig parkte der Lieferwagen.", "Waltig", "m", ""),
    ("A7-15", "Mit dem Laptop hat der Kunde gearbeitet.", "Laptop", "b", "frei"),
    ("A7-15", "Neben dem Carport parkte der Lieferwagen.", "Carport", "b", "frei"),
    ("A7-15", "Beim Aushub für die Bodenplatte beschädigte der Bagger die Leitung.", "Bodenplatte", "b", "gemeldet"),
    # A7-16: Zugangscode ohne Doppelpunkt
    ("A7-16", "Zugangscode 3309", "3309", "g", "weg"),
    ("A7-16", "Hinweis für den Handwerker\nZugangscode 3309", "3309", "g", "weg"),
    ("A7-16", "Ort: Gartenhaus, Zugangscode 3310", "3310", "g", "weg"),
    ("A7-16", "Für den Paketdienst Zugangscode 5527 verwenden.", "5527", "g", "weg"),
    ("A7-16", "Zugangs-Code 2290 bitte nicht weitergeben.", "2290", "g", "weg"),
    # A7-17: Anrede + Amt + Allerweltswort vor Partizip – Tausch (gleiche Gestalt wie "Herrn Rechtsanwalt Unterlagen
    # übermittelt" der Über-Proben): gemeldet wie auf 6f2d08f, nie still
    ("A7-17", "Die Unterlagen wurden Herrn Notar Regen übergeben.", "Regen", "m", ""),
    # Differenzprobe der Nachbesserung 9 (Abnahme-7-Klassen, auf einem Bezugsstand geschwärzt oder gemeldet)
    ("D9", "Laut Herrn Vorsitzender Regen fehlt die Rechnung.", "Regen", "g", "weg"),
    ("D9", "Frau Vorsitzender Abend hat den Schaden bestätigt.", "Abend", "g", "weg"),
    ("D9", "Vom Hohenlaufen kam der Anruf.", "Hohenlaufen", "m", ""),
    ("D9", "Herr Notar Regen und Frau Notarin Wasser haben unterschrieben.", "Wasser", "g", "weg"),
    # A7-19: Sach-Grundwort nur mit vollständigem Bestimmungswort ("Talbot" ist kein Bot)
    ("A7-19", "Der Talbot arbeitet als Lagerhilfe.", "Lagerhilfe", "g", "weg"),
    ("A7-19", "Der Clift arbeitet als Lagerhilfe.", "Lagerhilfe", "g", "weg"),
    ("A7-19", "Der Lapp arbeitet als Lagerhilfe.", "Lagerhilfe", "g", "weg"),
    ("A7-19", "Die Software arbeitet als Eingabehilfe.", "Eingabehilfe", "b", "frei"),
    ("A7-19", "Die Rampe arbeitet als Einstiegshilfe.", "Einstiegshilfe", "b", "frei"),
    # A7U-04: Sparte ist keine Organisation – die Anschrift darunter wird erkannt
    ("A7U-04", "Hausratversicherung\nBirkenweg 7, 83022 Rosenheim", "Birkenweg 7", "g", "weg"),
    ("A7U-04", "Notiz Hausratversicherung – Umzug\nBirkenweg 7, 83022 Rosenheim", "83022 Rosenheim", "g", "weg"),
    ("A7U-04", "Aktennotiz\nWohngebäudeversicherung – Eigentümerwechsel\nObjekt: Einfamilienhaus Lindenstraße 12, "
               "84028 Landshut", "Lindenstraße 12", "g", "weg"),
    ("A7U-04", "Allianz Versicherungs-AG\nKöniginstraße 28, 80802 München", "Königinstraße 28", "b", "frei"),
    ("A7U-04", "Deutsche Rentenversicherung Bund\nRuhrstraße 2, 10709 Berlin", "Ruhrstraße 2", "b", "frei"),
    # A7U-05: Allerweltswort hinter Anrede + Amt mit Objektzusammenhang -> gemeldet statt geschwärzt
    ("A7U-05", "Wir haben Herrn Notar Unterlagen und Vollmacht übersandt.", "Unterlagen", "b", "gemeldet"),
    ("A7U-05", "Wir haben Herrn Rechtsanwalt Unterlagen übermittelt.", "Unterlagen", "b", "gemeldet"),
    ("A7U-05", "Wie mit Herrn Notar Termin vereinbart, kommen wir am Montag.", "Termin", "b", "gemeldet"),
    ("A7U-05", "Wir haben Frau Notarin Grundbuchauszug übersandt.", "Grundbuchauszug", "b", "gemeldet"),
    ("A7U-05", "Wie Herr Notar Regen sagte, ist alles in Ordnung.", "Regen", "g", "weg"),
    ("A7U-05", "Laut Herrn Rechtsanwalt Regen ist die Frist gewahrt.", "Regen", "g", "weg"),
    # A7U-06: Bedienung + Zahl nur mit Alarm-, Schloss- oder Raumgegenstand geschwärzt, sonst gemeldet
    ("A7U-06", "Zum Aktivieren des Bonusprogramms 2026 bitte die Karte vorlegen.", "2026", "b", "gemeldet"),
    ("A7U-06", "Zum Abschalten der Heizung 2024 musste der Notdienst kommen.", "2024", "b", "gemeldet"),
    ("A7U-06", "Zum Einschalten der Notheizung 1800 Watt bereitstellen.", "1800", "b", "gemeldet"),
    ("A7U-06", "Zum Entriegeln der Kellertür: 4455", "4455", "g", "weg"),
    ("A7U-06", "Probealarm: Code zum Ausschalten 7329", "7329", "g", "weg"),
    # A7U-07: Beruf des X ohne Person (Pronomen, "beginnt") -> gemeldet statt geschwärzt
    ("A7U-07", "Für den Beruf des Spenglers gilt die Berufsgruppe 4, sie wird jährlich überprüft.", "Spenglers", "b",
     "gemeldet"),
    ("A7U-07", "Für den Beruf des Physiotherapeuten gilt der Grundtarif, er beginnt bei 120 EUR.", "Physiotherapeuten",
     "b", "gemeldet"),
    ("A7U-07", "Sein Sohn strebt den Beruf des Polizisten an.", "Polizisten", "g", "weg"),
    ("A7U-07", "Für den Beruf des Bäckers hat sich Herr Huber entschieden.", "Bäckers", "g", "weg"),
    ("A7U-07", "Er bereitet sich auf den Beruf des Chirurgen vor.", "Chirurgen", "g", "weg"),
    ("A7U-07", "Sie bereitet sich auf den Beruf der Floristin vor.", "Floristin", "g", "weg"),
    ("A7U-07", "Im Beruf des Schreiners arbeitete Ihre Tochter zwölf Jahre.", "Schreiners", "g", "weg"),
    ("A7U-07", "Für den Beruf des Polizisten gilt die Gefahrengruppe B.", "Polizisten", "b", "gemeldet"),
]


@pytest.mark.parametrize("befund, text, wert, art, soll", FAELLE,
                         ids=[f"{b}-{i}" for i, (b, *_r) in enumerate(FAELLE)])
def test_n9_zeilen_der_abnahme(befund, text, wert, art, soll):
    ist = _zustand(text, wert)
    if art == "g":
        erlaubt = ("weg",) if soll == "weg" else ("weg", "gemeldet")
    elif art == "m":
        erlaubt = ("gemeldet",)
    else:
        erlaubt = ("frei",) if soll == "frei" else ("frei", "gemeldet")
    assert ist in erlaubt, (befund, text, wert, ist)


# ----------------------------------------------------------------------
# A7-01: ein fremdes Ding zwischen "schalt…" und "ab/aus" nur mit einem Beleg einer Sache
# ----------------------------------------------------------------------
@pytest.mark.parametrize("wort, ding", [
    ("Lüftung", True), ("Heizung", True), ("Hausmeister", False), ("Feuerwehr", False), ("Gruber", False),
    ("Xyzzl", False), ("Frau", False), ("Feueralarm", False),
])
def test_a7_01_fremdes_ding_nur_mit_sachbeleg(wort, ding):
    assert kennungsformen._alarm_fremdes_ding(wort) is ding


# ----------------------------------------------------------------------
# A7-03: Planbezug – Listen der Schlüssel, Codes, Mieter und "-stelle" (außer Kostenstelle) sind kein Gegenbeleg
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, beleg", [
    ("laut Raumbuch", True), ("laut Kostenstellenplan", True), ("für die Abrechnung", True),
    ("laut Schlüsselliste", False), ("laut Mieterliste", False), ("gemäß Dienstplan", False),
    ("für die Baustelle", False), ("für die Kostenstelle", True),
])
def test_a7_03_planbezug(text, beleg):
    assert kennungsformen._plan_bezug(text, 0, len(text)) is beleg


# ----------------------------------------------------------------------
# A7-13: Lage der Feldnamen einer Seite nach ihrem Rand (kammraster.feldnamen_lage) und die Zuordnung danach
# (restrisiko._kamm_etikett wie kammfelder.etikett_text_zum_feld)
# ----------------------------------------------------------------------
def _feld(y0, x0=60.0, n=8, breite=12.0, hoehe=16.0):
    kaesten = [(x0 + breite * k, y0, x0 + breite * (k + 1), y0 + hoehe) for k in range(n)]
    return {"kaesten": kaesten, "rahmen": (x0, y0, x0 + breite * n, y0 + hoehe), "gefuellt": [True] * n}


def _seite_unten_eng():
    """Feldnamen unter den Feldern, das nächste Feld eng darunter (Verhältnis der Abstände um 1,5)."""
    felder = [_feld(100.0), _feld(129.0), _feld(158.0)]
    woerter = [(60.0, 118.0, 140.0, 126.0, "Geburtsdatum"), (60.0, 147.0, 150.0, 155.0, "Kilometerstand"),
               (60.0, 176.0, 110.0, 184.0, "Baujahr")]
    return felder, woerter


def _seite_oben_haengend():
    """Feldnamen über den Feldern, nah am eigenen Feld (Verhältnis der Abstände um 3)."""
    felder = [_feld(100.0), _feld(140.0), _feld(180.0)]
    woerter = [(60.0, 88.0, 150.0, 96.0, "Familienname"), (60.0, 128.0, 120.0, 136.0, "Vorname"),
               (60.0, 168.0, 130.0, 176.0, "Geburtsort")]
    return felder, woerter


def test_a7_13_feldnamen_lage_unten_und_oben():
    felder, woerter = _seite_unten_eng()
    assert kammraster.feldnamen_lage(felder, [w[:4] for w in woerter]) == "unten"
    felder, woerter = _seite_oben_haengend()
    assert kammraster.feldnamen_lage(felder, [w[:4] for w in woerter]) == "oben"
    # ohne Beleg am Rand (Text über dem ersten und unter dem letzten Feld): nicht sicher
    felder, woerter = _seite_unten_eng()
    woerter = woerter + [(60.0, 88.0, 140.0, 96.0, "Antragsdaten")]
    assert kammraster.feldnamen_lage(felder, [w[:4] for w in woerter]) is None


def test_a7_13_feldname_unter_dem_feld_bei_engem_folgeabstand():
    felder, woerter = _seite_unten_eng()
    assert [restrisiko._kamm_etikett(woerter, f, felder) for f in felder] == \
        ["Geburtsdatum", "Kilometerstand", "Baujahr"]


def test_a7_13_haengender_feldname_ueber_dem_feld():
    felder, woerter = _seite_oben_haengend()
    assert [restrisiko._kamm_etikett(woerter, f, felder) for f in felder] == ["Familienname", "Vorname", "Geburtsort"]


# ----------------------------------------------------------------------
# A7-18: Buchstaben hinter einem Feldnamen, der Buchstaben eines Namens verlangt, sind ein Name – Parteibuchstaben nur
# ohne solchen Feldnamen
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert", [
    ("Kürzel der Fahrerin\t\tA\t\tB", "A\t\tB"),
    ("Schadenmeldung\nKürzel der Fahrerin\t\tA\t\tB", "A\t\tB"),
    ("Initialen des Versicherungsnehmers\t\tA\t\tB", "A\t\tB"),
    ("Namenskürzel des Kindes\t\tA\t\tB", "A\t\tB"),
    ("Handzeichen des Sachbearbeiters\t\tK\t\tM", "K\t\tM"),
])
def test_a7_18_namensbuchstaben_hinter_feldname(text, wert):
    assert ("namen", wert) in _kamm(text)


@pytest.mark.parametrize("text", [
    "Unterschrift der Fahrer\nA\t\tB", "Fahrzeug\t\tA\t\tB", "Versicherungsnehmer\t\tA\t\tB", "Länderkürzel\t\tD\t\tA",
    "Kfz-Kürzel\t\tM",
])
def test_a7_18_gegenproben_parteibuchstaben_und_sachkuerzel(text):
    assert not any(k == "namen" for k, _ in _kamm(text)), _kamm(text)


# ----------------------------------------------------------------------
# A7U-04: eine Versicherungssparte allein ist kein Organisationsbeleg
# ----------------------------------------------------------------------
@pytest.mark.parametrize("zeile, beleg", [
    ("Hausratversicherung", None), ("Wohngebäudeversicherung – Eigentümerwechsel", None),
    ("Kfz-Versicherung – Schadenmeldung", None), ("Allianz Versicherungs-AG", "rechtsform"),
    ("Bayerische Versicherungskammer", "organisation"), ("Deutsche Rentenversicherung Bund", "organisation"),
    ("Hausratversicherung der Sparkasse", "organisation"),
])
def test_a7u_04_sparte_kein_firmenbeleg(zeile, beleg):
    assert struktur_adresse.firmen_beleg(zeile) == beleg


# ----------------------------------------------------------------------
# Laufzeit (A7U-10, A7U-11 und die in dieser Nachbesserung neuen bzw. geänderten Schleifen): 8k gegen 64k Zeichen,
# Schranke 2,0 (zeitmessung.wachstum_messen). Lange Zeilen ohne Satzzeichen – die Fenster müssen dann greifen.
# ----------------------------------------------------------------------
def test_a7u_10_geraet_code_lange_zeile_ohne_satzzeichen_waechst_linear():
    """F5 der Abnahme: geraet_code_mehrdeutig sucht Zeilen- und Satzanfang nur im Fenster vor dem Code."""
    baustein = "das Bedienteil zeigte Code 0811 an und "
    klein, gross = _zeile(baustein, 8000), _zeile(baustein, 64000)
    wachstum, _, zeit = _wachstum(lambda: kennungsformen.geraet_code_mehrdeutig(klein),
                                  lambda: kennungsformen.geraet_code_mehrdeutig(gross), 8, 2.0)
    assert wachstum < 2.0, f"geraet_code_mehrdeutig wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_a7u_10_raumcode_planbezug_lange_zeile_waechst_linear():
    """F7 der Abnahme: _raum_codes.ablegen sucht den Satzanfang nur im Fenster vor dem Wert (auch _plan_bezug)."""
    baustein = "Raumcode 2017 laut Raumbuch und "
    klein, gross = _zeile(baustein, 8000), _zeile(baustein, 64000)
    wachstum, _, zeit = _wachstum(lambda: kennungsformen._raum_codes(klein, []),
                                  lambda: kennungsformen._raum_codes(gross, []), 8, 2.0)
    assert wachstum < 2.0, f"_raum_codes wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def _jahr_formen(text):
    return [kennungsformen._jahr_vor_attribut(text, m.start(1), m.end(1)) for m in re.finditer(r"mit (\d{4})", text)]


def test_a7u_10_jahr_vor_attribut_lange_zeile_waechst_linear():
    """F8 der Abnahme: _jahr_vor_attribut sucht das Satzende nur in 200 Zeichen."""
    baustein = "mit 2019 eingebauten Rolltoren und "
    klein, gross = _zeile(baustein, 8000), _zeile(baustein, 64000)
    wachstum, _, zeit = _wachstum(lambda: _jahr_formen(klein), lambda: _jahr_formen(gross), 8, 2.0)
    assert wachstum < 2.0, f"_jahr_vor_attribut wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_a7_10_bedienverb_vor_jahr_lange_zeile_waechst_linear():
    """_finites_bedienverb_davor und die Zwischenwort-Regel der Jahresform: Satzanfang im Fenster (zugangsdaten)."""
    baustein = "die Kellertür öffnen Sie mit 1990 bitte nur bei geschlossener Haustür und "
    klein, gross = _zeile(baustein, 8000), _zeile(baustein, 64000)
    wachstum, _, zeit = _wachstum(lambda: kennungsformen.zugangsdaten(klein),
                                  lambda: kennungsformen.zugangsdaten(gross), 8, 2.0)
    assert wachstum < 2.0, f"zugangsdaten (Jahresform) wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_a7u_11_moebel_code_lange_zeile_waechst_linear():
    """A7U-11: Produkt-Kontext je Zeile einmal gesucht (_bereich_hat) – 8k gegen 64k auf 6f2d08f ×36."""
    baustein = "Code für den Spiegelschrank (Artikel 7731): 3074 und "
    klein, gross = _zeile(baustein, 8000), _zeile(baustein, 64000)
    wachstum, _, zeit = _wachstum(lambda: _funde(klein), lambda: _funde(gross), 8, 2.0)
    assert wachstum < 2.0, f"analysiere_text (Möbelcode) wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"
    wachstum, _, zeit = _wachstum(lambda: pruefe_text(klein), lambda: pruefe_text(gross), 8, 2.0)
    assert wachstum < 2.0, f"pruefe_text (Möbelcode) wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_a7_04_code_form_lange_zeile_waechst_linear():
    """_code_form sucht Störungs- und Nutzungswörter nur im Umkreis des Codes (CODE_BELEG_FENSTER) – je Satz ein Code
    mit Störungswort und ohne Bedienung bis zum Zeilenende (Eingriff: die ganze Zeile je Code)."""
    baustein = "Tor Code GT48 nach der Störung; "
    klein, gross = _zeile(baustein, 8000), _zeile(baustein, 64000)
    wachstum, _, zeit = _wachstum(lambda: kennungsformen.zugangsdaten(klein),
                                  lambda: kennungsformen.zugangsdaten(gross), 8, 2.0)
    assert wachstum < 2.0, f"zugangsdaten (Fehlercode-Gestalt) wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_a7_13_feldnamen_lage_viele_felder_waechst_linear():
    """feldnamen_lage: Felder darüber/darunter per bisect (je Feld alle Felder wüchse quadratisch)."""
    def seite(n):
        felder, boxen = [], []
        for i in range(n):
            r, c = divmod(i, 4)
            f = _feld(40.0 + 40.0 * r, x0=50.0 + 130.0 * c)
            felder.append(f)
            boxen.append((f["rahmen"][0], f["rahmen"][3] + 2.0, f["rahmen"][0] + 60.0, f["rahmen"][3] + 10.0))
        return felder, boxen
    fk, bk = seite(250)
    fg, bg = seite(2000)

    def lauf(felder, boxen):
        kammraster._FELDNAMEN_LAGE = None              # die Merkliste der Seite soll nicht greifen
        return kammraster.feldnamen_lage(felder, boxen)

    wachstum, _, zeit = _wachstum(lambda: lauf(fk, bk), lambda: lauf(fg, bg), 8, 2.0)
    assert wachstum < 2.0, f"feldnamen_lage wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_a7u_04_sparte_lange_zeile_waechst_linear():
    """firmen_beleg prüft jede Organisationsangabe der Zeile einmal (finditer statt search)."""
    baustein = "Hausratversicherung und Kfz-Versicherung, "
    klein, gross = _zeile(baustein, 8000), _zeile(baustein, 64000)
    wachstum, _, zeit = _wachstum(lambda: struktur_adresse.firmen_beleg(klein),
                                  lambda: struktur_adresse.firmen_beleg(gross), 8, 2.0)
    assert wachstum < 2.0, f"firmen_beleg wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"
