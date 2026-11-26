"""Nachbesserung 8 nach der sechsten Abnahme von integration-r7 (Stand 6c0c464).

Je Befund der Abnahme (Lecks A6-01 bis A6-16, Über-Schwärzung, Laufzeit und Doku AB6U-01 bis AB6U-16) die Zeilen der
Abnahme, eigene Abwandlungen und Gegenproben. Grundsätze: eine Ausnahme stuft einen möglichen geheimen Wert höchstens
von „schwärzen“ auf „melden“ herab (P1); mehrdeutige Fälle werden gemeldet, geschwärzt nur mit sicherem Beleg, frei
gelassen nur mit sicherem Gegenbeleg (P2); Wortlisten-Einträge, die frei lassen, werden gegen die Familiennamen der
Wissensbasis geprüft (P3). Alle Personen, Codes, Nummern und Anschriften sind frei erfunden."""

import pytest

from anonymisierer import detektoren, kennungsformen, muster, personenkontext, seitenmodell, wissen
from anonymisierer.analyse import analysiere_text
from anonymisierer.detektoren import Kontext
from anonymisierer.restrisiko import pruefe_text

ALLE = {k for k, _, _, _, an in muster.KATEGORIEN if an}


# ----------------------------------------------------------------------
# Hilfsfunktionen (wie tests/test_abnahme5_r7.py)
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


def _wachstum(klein, gross, faktor, schranke):
    import zeitmessung
    klein()
    return zeitmessung.wachstum_messen(klein, gross, faktor, wiederholungen=1, schranke=schranke)


def _zeile(baustein, n):
    return baustein * max(1, n // len(baustein))


# ----------------------------------------------------------------------
# Zeilen der Abnahme 6 und eigene Abwandlungen je Befund (Gruppe = Probe der Nachbesserung 8):
#   jahr (A6-01, AB6U-08), hof (A6-02, A6-03, AB6U-01), praep (A6-04), beruf (A6-05, A6-06, A6-09, AB6U-10 d),
#   regen (A6-10, A6-16), allerwelt (AB6U-03, d6), aw_meldung/titel/einrichtung (AB6U-07),
#   geraet_meldet (AB6U-05), geraetecode/a612_613/raumcode/alarm_raum (A6-12, A6-13, AB6U-04, AB6U-07),
#   kamm_klammer (AB6U-02), moebel_beruf (AB6U-10 a, b), hof_beruf (AB6U-10 c), ab6u15 (AB6U-15, A6-15 Textzeilen).
# Art g (geheim): geschwärzt oder gemeldet, nie still; was die Nachbesserung schwärzt, bleibt geschwärzt.
# Art b (nicht geheim): frei, wo der beste Bezugsstand frei ist; sonst höchstens gemeldet, nie geschwärzt.
# ----------------------------------------------------------------------
FAELLE = [
    ('a612_613', 'Das Bedienteil meldete Code 6624, danach die Haustür entriegeln.', '6624', 'g', 'gemeldet'),
    ('a612_613', 'Das Garagentor blinkte mit Code 3815; dann das Tor mit dem Handsender öffnen.', '3815', 'g', 'gemeldet'),
    ('a612_613', 'Der Code des Gemeindesaals für den Belegungsplan lautet 7718.', '7718', 'g', 'gemeldet'),
    ('a612_613', 'Der Code des Bootshauses für den Belegungsplan lautet 7719.', '7719', 'g', 'gemeldet'),
    ('a612_613', 'Zum Abschalten des Feueralarms: 3401', '3401', 'g', 'weg'),
    ('a612_613', 'Hinterhofcode 4471', '4471', 'g', 'weg'),
    ('a612_613', 'Zugangscode Kellerabteil 5512', '5512', 'g', 'weg'),
    ('a612_613', 'PIN für Waschküche 2290', '2290', 'g', 'weg'),
    ('a612_613', 'Der Küchenschrank (Artikel 7731) lässt sich mit dem Code 6631 öffnen.', '6631', 'g', 'weg'),
    ('a612_613', 'Schadenort Waschküche, Code 9917', '9917', 'g', 'gemeldet'),
    ('a612_613', 'Die Hintertür hat den Code ZT77.', 'ZT77', 'g', 'weg'),
    ('a612_613', 'Die Hintertür hat den Code ZT 77.', 'ZT 77', 'g', 'gemeldet'),
    ('a612_613', 'Schadenort: Heizungsraum, Code 5207', '5207', 'g', 'gemeldet'),
    ('a612_613', 'Garagentor: Code DH2', 'DH2', 'g', 'gemeldet'),
    ('a612_613', 'Probealarm: Code zum Ausschalten 7329', '7329', 'g', 'weg'),
    ('a612_613', 'Waschküche\nCode 4410', '4410', 'g', 'gemeldet'),
    ('a612_613', 'Wintergarten: Code 7781', '7781', 'g', 'gemeldet'),
    ('ab6u15', 'Name des Versicherungsnehmers\t\tK R A U S', 'K R A U S', 'g', 'weg'),
    ('ab6u15', 'Name des Versicherungsnehmers: K R A U S', 'K R A U S', 'g', 'weg'),
    ('ab6u15', 'Wohnort seit 2019: Traunreut, Am Kirchsteig 4', 'Traunreut', 'g', 'gemeldet'),
    ('ab6u15', 'Wohnort seit 2019: Traunreut, Am Kirchsteig 4', 'Am Kirchsteig 4', 'g', 'weg'),
    ('ab6u15', 'Wohnhaft seit 2019 in Traunreut, Am Kirchsteig 4', 'Traunreut', 'g', 'gemeldet'),
    ('ab6u15', 'Geburtsdatum ........ 27.10.1997', '27.10.1997', 'g', 'weg'),
    ('ab6u15', 'Zeuge war Thu Trang Bui', 'Thu Trang Bui', 'g', 'weg'),
    ('alarm_raum', 'Der Brandalarm-Code 2297 wurde um 14:20 Uhr ausgelöst, die Feuerwehr setzte die Anlage danach zurück.', '2297', 'b', 'frei'),
    ('alarm_raum', 'Feueralarmcode 3401 ausgelöst; der Hausmeister hat die Anlage anschließend zurückgesetzt.', '3401', 'b', 'frei'),
    ('alarm_raum', 'Der Probealarmcode 1001 wird jeden ersten Montag im Monat ausgelöst.', '1001', 'b', 'frei'),
    ('alarm_raum', 'Fehlalarmcode 7310 laut Protokoll der Brandmeldeanlage, Ursache Wasserdampf.', '7310', 'b', 'frei'),
    ('alarm_raum', 'Brand in der Werkstatt, Code 2210 laut Feuerwehrbericht (Kleinbrand).', '2210', 'b', 'gemeldet'),
    ('alarm_raum', 'Gebäudecode 1101 (Wohngebäude, Massivbauweise) laut Gebäudeliste.', '1101', 'b', 'frei'),
    ('alarm_raum', 'Raumcode 2017 laut Raumbuch: Besprechungsraum im 2. OG.', '2017', 'b', 'frei'),
    ('alarm_raum', 'Lagercode 4410 laut Kostenstellenplan, Lagerort Regal 3.', '4410', 'b', 'frei'),
    ('alarm_raum', 'Werkstattcode 4420 für die Abrechnung der Arbeitsstunden.', '4420', 'b', 'frei'),
    ('alarm_raum', 'Hallencode 0302 im Lageplan des Gewerbeparks.', '0302', 'b', 'frei'),
    ('alarm_raum', 'Kellercode 1120 laut Wohnungsübergabeprotokoll (Kellerabteil Nr. 12).', '1120', 'b', 'frei'),
    ('alarm_raum', 'Feueralarmcode 3401', '3401', 'g', 'gemeldet'),
    ('alarm_raum', 'Der Feueralarmcode lautet 7781.', '7781', 'g', 'gemeldet'),
    ('alarm_raum', 'Feueralarmcode 3437 (nur für den Hausmeister)', '3437', 'g', 'weg'),
    ('alarm_raum', 'Brandalarm-Code 2297, damit wird der Alarm am Bedienteil quittiert.', '2297', 'g', 'weg'),
    ('alarm_raum', 'Werkstattcode: 4420', '4420', 'g', 'weg'),
    ('alarm_raum', 'Kellercode 1120', '1120', 'g', 'weg'),
    ('alarm_raum', 'Der Kellercode lautet 1120 laut Übergabeprotokoll.', '1120', 'g', 'weg'),
    ('alarm_raum', 'Der Kellercode lautet 1120 laut Übergabeprotokoll.', '1120', 'g', 'weg'),
    ('alarm_raum', 'Der Kellercode lautet 1120.', '1120', 'g', 'weg'),
    ('alarm_raum', 'Der Werkstattcode ist 4420.', '4420', 'g', 'weg'),
    ('alarm_raum', 'Der Lagercode lautet: 4410', '4410', 'g', 'weg'),
    ('allerwelt', 'Zeugenliste\nZeuge Wasser Anna hat den Brand gesehen.', 'Wasser', 'g', 'weg'),
    ('allerwelt', 'Zeuge Wasser Anna hat den Brand gesehen.', 'Wasser', 'g', 'weg'),
    ('allerwelt', 'Mieter Regen: kein Schaden', 'Regen', 'g', 'gemeldet'),
    ('allerwelt', 'Nachbar Sonne: kein Schaden', 'Sonne', 'g', 'gemeldet'),
    ('allerwelt', 'Rücksprache mit Nachbar Wasser am Montag.', 'Wasser', 'g', 'weg'),
    ('allerwelt', 'Gestern rief Kollegin Regen an.', 'Regen', 'g', 'weg'),
    ('allerwelt', 'Die Kosten trägt Mieter Wasser selbst.', 'Wasser', 'g', 'gemeldet'),
    ('allerwelt', 'Nachbar Wasser hat den Rauch gesehen.', 'Wasser', 'g', 'weg'),
    ('allerwelt', 'Laut Nachbarin Regen war die Tür offen.', 'Regen', 'g', 'weg'),
    ('allerwelt', 'Wir haben Nachbar Wasser den Schlüssel gegeben.', 'Wasser', 'g', 'gemeldet'),
    ('allerwelt', 'Heute Kunde Bescheid gegeben, Unterlagen folgen per Post.', 'Bescheid', 'b', 'frei'),
    ('allerwelt', 'Am Montag Nachbar Schlüssel übergeben, damit der Handwerker in die Wohnung kann.', 'Schlüssel', 'b', 'frei'),
    ('allerwelt', 'Rücksprache mit Kunde Montag, danach Kollege Akte übergeben.', 'Akte', 'b', 'frei'),
    ('allerwelt', '14.03.: Telefonat, anschließend Kunde Unterlagen zugeschickt.', 'Unterlagen', 'b', 'frei'),
    ('allerwelt', 'Wir haben Kunde Kopie der Police geschickt.', 'Kopie', 'b', 'gemeldet'),
    ('allerwelt', 'Bitte Kollege Bescheid geben, sobald die Liste eingegangen ist.', 'Bescheid', 'b', 'frei'),
    ('allerwelt', 'Danach Kundin Formular zur Stehlgutliste gemailt.', 'Formular', 'b', 'frei'),
    ('allerwelt', 'Nach dem Gespräch Kunde Angebot für die Elementarversicherung geschickt.', 'Angebot', 'b', 'frei'),
    ('allerwelt', 'Ich habe Mandant Vollmacht zur Kündigung vorgelegt.', 'Vollmacht', 'b', 'frei'),
    ('allerwelt', 'Mieter Wohnung: EG links', 'Wohnung', 'b', 'frei'),
    ('allerwelt', 'Ehefrau Mitversichert: ja', 'Mitversichert', 'b', 'frei'),
    ('aw_meldung', 'Er zeigte Kollegen Fotos vom Hagelschaden am Wintergarten.', 'Fotos', 'b', 'gemeldet'),
    ('aw_meldung', 'Wir empfehlen Kunden Abschluss einer Elementarschadenversicherung.', 'Abschluss', 'b', 'frei'),
    ('aw_meldung', 'Wir haben Kunde Kopie der Police geschickt.', 'Kopie', 'b', 'gemeldet'),
    ('aw_meldung', 'Die Kosten trägt Mieter Anteil laut Nebenkostenabrechnung selbst.', 'Anteil', 'b', 'gemeldet'),
    ('aw_meldung', 'Die Kosten trägt Mieter Wasser selbst.', 'Wasser', 'g', 'gemeldet'),
    ('aw_meldung', 'Er telefonierte mit Kollegen Wasser.', 'Wasser', 'g', 'gemeldet'),
    ('aw_meldung', 'Der Wagen des Nachbarn Regen der Familie stand vor der Tür.', 'Regen', 'g', 'gemeldet'),
    ('aw_meldung', 'Wir haben Nachbar Regen der Versicherung gemeldet.', 'Regen', 'g', 'gemeldet'),
    ('beruf', 'Er ist von Beruf Trainer der F-Jugend.', 'Trainer', 'g', 'weg'),
    ('beruf', 'Er ist hauptberuflich Trainer der F-Jugend beim TSV Inzell.', 'Trainer', 'g', 'weg'),
    ('beruf', 'Sie ist nebenberuflich Betreuerin ihrer Nachbarin.', 'Betreuerin', 'g', 'weg'),
    ('beruf', 'Herr Sanftl ist von Beruf Makler seines Onkels.', 'Makler', 'g', 'gemeldet'),
    ('beruf', 'Er war hauptberuflich Verwalter der Erbengemeinschaft.', 'Verwalter', 'g', 'gemeldet'),
    ('beruf', 'Er ist inzwischen Trainer der F-Jugend.', 'Trainer', 'g', 'gemeldet'),
    ('beruf', 'Sie war damals Betreuerin ihrer Mutter.', 'Betreuerin', 'g', 'gemeldet'),
    ('beruf', 'Er ist Trainer der F-Jugend beim TSV Inzell.', 'Trainer', 'g', 'gemeldet'),
    ('beruf', 'Sein Sohn strebt den Beruf des Polizisten an.', 'Polizisten', 'g', 'weg'),
    ('beruf', 'Ihr Sohn bewirbt sich auf den Beruf des Soldaten.', 'Soldaten', 'g', 'weg'),
    ('beruf', 'Für den Beruf des Architekten gilt die Gefahrengruppe A.', 'Architekten', 'g', 'gemeldet'),
    ('beruf', 'Ihre Tochter hat den Beruf der Floristin erlernt.', 'Floristin', 'g', 'weg'),
    ('beruf', 'Er übt den Beruf des Bäckers aus.', 'Bäckers', 'g', 'weg'),
    ('beruf', 'Für den Beruf des Piloten gilt ein Zuschlag.', 'Piloten', 'g', 'gemeldet'),
    ('beruf', 'Den Beruf des Chirurgen hat er nach dem Unfall aufgegeben.', 'Chirurgen', 'g', 'gemeldet'),
    ('beruf', 'Der Eilbote arbeitet als Lagerhilfe.', 'Lagerhilfe', 'g', 'weg'),
    ('beruf', 'Der Fahrradbote arbeitet als Aushilfskraft.', 'Aushilfskraft', 'g', 'weg'),
    ('beruf', 'Der Kurierbote arbeitet als Packhilfe.', 'Packhilfe', 'g', 'weg'),
    ('beruf', 'Der Verletzte arbeitet als Lagerhilfe.', 'Lagerhilfe', 'g', 'weg'),
    ('beruf', 'Für den Beruf des Dachdeckers gilt die Gefahrengruppe B.', 'Dachdeckers', 'b', 'gemeldet'),
    ('beruf', 'Für den Beruf des Dachdeckers hat der Versicherer die Gefahrengruppe B festgelegt.', 'Dachdeckers', 'b', 'gemeldet'),
    ('beruf', 'Die Software arbeitet als Eingabehilfe für die Sachbearbeitung.', 'Eingabehilfe', 'b', 'frei'),
    ('beruf', 'Der Chatbot arbeitet als Auskunftshilfe.', 'Auskunftshilfe', 'b', 'frei'),
    ('beruf', 'Als Landwirt profitieren Sie von unserem Tarif.', 'Landwirt', 'b', 'frei'),
    ('einrichtung', 'Die Bank hat angerufen und um die Unterlagen gebeten.', 'Bank', 'b', 'frei'),
    ('einrichtung', 'Der Versicherer hat den Schaden gemeldet und einen Gutachter beauftragt.', 'Versicherer', 'b', 'frei'),
    ('einrichtung', 'Die Schule hat angerufen, das Kind hat sich beim Sport verletzt.', 'Schule', 'b', 'frei'),
    ('einrichtung', 'Die Kasse hat die Kostenübernahme bestätigt.', 'Kasse', 'b', 'frei'),
    ('einrichtung', 'Der Motor meldete uns den Code P0300.', 'Motor', 'b', 'frei'),
    ('einrichtung', 'Das Rolltor meldete uns per App den Code 2210 als Störung.', 'Rolltor', 'b', 'frei'),
    ('einrichtung', 'Die Alarmanlage meldete uns am Morgen den Code 4021, Ursache war ein offenes Fenster.', 'Alarmanlage', 'b', 'frei'),
    ('einrichtung', 'Die Hausverwaltung hat angerufen.', 'Hausverwaltung', 'b', 'frei'),
    ('einrichtung', 'Der Wasser hat den Schaden gemeldet.', 'Wasser', 'g', 'gemeldet'),
    ('einrichtung', 'Die Hinterstoißer hat angerufen.', 'Hinterstoißer', 'g', 'gemeldet'),
    ('einrichtung', 'Der Brandstetter hat den Schaden gemeldet.', 'Brandstetter', 'g', 'gemeldet'),
    ('einrichtung', 'Die Wimmer hat angerufen.', 'Wimmer', 'g', 'weg'),
    ('geraet_meldet', 'Das Garagentor meldete uns den Code 3017, der Monteur kommt morgen.', '3017', 'b', 'frei'),
    ('geraet_meldet', 'Das Rolltor meldete uns per App den Code 2210 als Störung.', '2210', 'b', 'frei'),
    ('geraet_meldet', 'Die Alarmanlage meldete uns am Morgen den Code 4021, Ursache war ein offenes Fenster.', '4021', 'b', 'frei'),
    ('geraet_meldet', 'Das Rolltor hat den Code E125, laut Hersteller Überlast am Motor.', 'E125', 'b', 'gemeldet'),
    ('geraet_meldet', 'Nach dem Rauchalarmcode 4471 schaltete die Feuerwehr die Lüftung ab.', '4471', 'b', 'gemeldet'),
    ('geraet_meldet', 'Störalarmcode 5120 – betrifft nur für Zone B die Sprinkleranlage.', '5120', 'b', 'gemeldet'),
    ('geraet_meldet', 'Das Garagentor zeigte uns den Code 3017.', '3017', 'b', 'gemeldet'),
    ('geraet_meldet', 'Die Heizung zeigte mir gestern den Code 3342, der Kundendienst ist informiert.', '3342', 'b', 'frei'),
    ('geraet_meldet', 'Der Router meldete uns den Code 4410 als Fehler.', '4410', 'b', 'frei'),
    ('geraet_meldet', 'Der Vermieter meldete uns den Code der Haustür: 2827', '2827', 'g', 'weg'),
    ('geraet_meldet', 'Bei Fehlalarm bitte Code 6203 am Bedienteil eingeben.', '6203', 'g', 'weg'),
    ('geraet_meldet', 'Die Hausverwaltung nannte uns den Code 5591 für das Garagentor.', '5591', 'g', 'weg'),
    ('geraet_meldet', 'Frau Huber schickte uns den Code 7712 für die Alarmanlage.', '7712', 'g', 'weg'),
    ('geraet_meldet', 'Der Nachbar sagte mir den Code 1987 für das Tor.', '1987', 'g', 'weg'),
    ('geraet_meldet', 'Das Schloss hat den Code 4815.', '4815', 'g', 'weg'),
    ('geraet_meldet', 'Die Haustür hat den Code 2580, bitte nicht weitergeben.', '2580', 'g', 'weg'),
    ('geraet_meldet', 'Zum Abschalten des Feueralarms: 3401', '3401', 'g', 'weg'),
    ('geraet_meldet', 'Feueralarm abschalten mit Code 3409', '3409', 'g', 'weg'),
    ('geraet_meldet', 'Rauchalarmcode 4471, damit schaltet man den Alarm ab.', '4471', 'g', 'weg'),
    ('geraet_meldet', 'Feueralarmcode 3437 (nur für den Hausmeister)', '3437', 'g', 'weg'),
    ('geraet_meldet', 'Brandalarmcode 2297 nur für Herrn Maier', '2297', 'g', 'weg'),
    ('geraet_meldet', 'Mit dem Feueralarmcode 3409 schaltet man die Sirene ab.', '3409', 'g', 'weg'),
    ('geraet_meldet', 'Am Morgen meldete uns die Alarmanlage den Code 4021, Ursache war ein offenes Fenster.', '4021', 'b', 'frei'),
    ('geraet_meldet', 'Am Tor zeigte uns der Verwalter den Code 4711.', '4711', 'g', 'weg'),
    ('geraet_meldet', 'Die Alarmanlage meldete uns den Code 4021, danach bitte den Code am Bedienteil eingeben.', '4021', 'g', 'weg'),
    ('geraet_meldet', 'Das Rolltor hat den Code E125.', 'E125', 'g', 'weg'),
    ('geraet_meldet', 'Die Kellertür hat den Code K2580, bitte nicht weitergeben.', 'K2580', 'g', 'weg'),
    ('geraet_meldet', 'Garagentor: Code KB475', 'KB475', 'g', 'weg'),
    ('geraetecode', 'Das Bedienteil meldete Code 9942; danach den Code eingeben.', '9942', 'g', 'gemeldet'),
    ('geraetecode', 'Das Garagentor blinkte mit Code 3815; dann das Tor mit dem Handsender öffnen.', '3815', 'g', 'gemeldet'),
    ('geraetecode', 'Das Bedienteil meldete Code 6624, danach die Haustür entriegeln.', '6624', 'g', 'gemeldet'),
    ('geraetecode', 'Das Codeschloss meldete Code 6263, bitte dann die Batterie tauschen.', '6263', 'g', 'gemeldet'),
    ('geraetecode', 'Der Tresor meldete Code 4900; dann das Tor mit dem Handsender öffnen.', '4900', 'g', 'gemeldet'),
    ('geraetecode', 'Die Alarmanlage zeigte den Code 7892; danach den Hausmeister verständigen.', '7892', 'g', 'gemeldet'),
    ('geraetecode', 'Die Kellertür hat den Code ZT-77, der Elektriker kommt morgen.', 'ZT-77', 'g', 'gemeldet'),
    ('geraetecode', 'Die Haustür hat den Code AB-12, der Elektriker kommt morgen.', 'AB-12', 'g', 'gemeldet'),
    ('geraetecode', 'Der Tresor hat den Code XY-88, laut Hersteller ab Werk.', 'XY-88', 'g', 'gemeldet'),
    ('geraetecode', 'Probealarm, Code 6925', '6925', 'g', 'gemeldet'),
    ('geraetecode', 'Feuerwehralarm, Code 3947', '3947', 'g', 'gemeldet'),
    ('geraetecode', 'Der Motor meldet den Code P0300, Zündaussetzer.', 'P0300', 'b', 'frei'),
    ('geraetecode', 'Die Türsprechanlage zeigt den Code E-04.', 'E-04', 'b', 'frei'),
    ('geraetecode', 'Code E-04 an der Türsprechanlage, Elektriker beauftragt.', 'E-04', 'b', 'frei'),
    ('geraetecode', 'Die Alarmanlage meldete den Code E125 (Sabotagekontakt Fenster).', 'E125', 'b', 'frei'),
    ('geraetecode', 'Das Garagentor zeigte den Code 3017, laut Hersteller verschmutzte Lichtschranke.', '3017', 'b', 'frei'),
    ('geraetecode', 'Am Tor blinkt Code 3017, laut Hersteller eine Störung der Lichtschranke.', '3017', 'b', 'gemeldet'),
    ('geraetecode', 'Das Garagentor meldet seit dem Sturm den Code F-21.', 'F-21', 'b', 'frei'),
    ('geraetecode', 'Der Rauchmelder an der Haustür zeigt den Code E-07.', 'E-07', 'b', 'frei'),
    ('geraetecode', 'Der Router meldet den Code DSL-651 seit dem Blitzeinschlag.', 'DSL-651', 'b', 'frei'),
    ('hof', 'Beim Sönksen ist der Stadel abgebrannt.', 'Sönksen', 'g', 'gemeldet'),
    ('hof', 'Vom Momsen kam der Anruf wegen des Hagelschadens.', 'Momsen', 'g', 'gemeldet'),
    ('hof', 'Beim Hölken ist in der Nacht eingebrochen worden.', 'Hölken', 'g', 'gemeldet'),
    ('hof', 'Wir waren gestern beim Diecken zum Essen.', 'Diecken', 'g', 'gemeldet'),
    ('hof', 'Beim Steinmaurer ist der Stadel abgebrannt.', 'Steinmaurer', 'g', 'gemeldet'),
    ('hof', 'Vom Lohgerber kam der Anruf wegen des Hagelschadens.', 'Lohgerber', 'g', 'gemeldet'),
    ('hof', 'Beim Holten ist der Stadel abgebrannt.', 'Holten', 'g', 'gemeldet'),
    ('hof', 'Beim Thielen brannte gestern Licht im Stall.', 'Thielen', 'g', 'gemeldet'),
    ('hof', 'Vom Knutsen kam der Anruf wegen des Sturmschadens.', 'Knutsen', 'g', 'gemeldet'),
    ('hof', 'Beim Tammeln ist der Stadel abgebrannt.', 'Tammeln', 'g', 'gemeldet'),
    ('hof', 'Vom Knutern kam der Anruf wegen des Hagelschadens.', 'Knutern', 'g', 'gemeldet'),
    ('hof', 'Beim Blitz wurde letzte Woche eingebrochen.', 'Blitz', 'g', 'gemeldet'),
    ('hof', 'Vom Wind kam der Anruf wegen des Hagelschadens.', 'Wind', 'g', 'gemeldet'),
    ('hof', 'Beim Sturz brannte gestern der Stadel.', 'Sturz', 'g', 'gemeldet'),
    ('hof', 'Vom Kühlergrill kam der Anruf wegen des Hagelschadens.', 'Kühlergrill', 'g', 'gemeldet'),
    ('hof', 'Beim Pfnürl! Dort hat es gestern gebrannt.', 'Pfnürl', 'g', 'gemeldet'),
    ('hof', 'Zum Tremml! Die Zufahrt ist seit dem Unwetter gesperrt.', 'Tremml', 'g', 'gemeldet'),
    ('hof', 'Beim Kaltl? Dort wurde eingebrochen.', 'Kaltl', 'g', 'gemeldet'),
    ('hof', 'Wir waren gestern beim Kaltl!', 'Kaltl', 'g', 'gemeldet'),
    ('hof', 'Waren Sie beim Kaltl?', 'Kaltl', 'g', 'gemeldet'),
    ('hof', 'Ich war gestern beim Gsödl!', 'Gsödl', 'g', 'gemeldet'),
    ('hof', 'Vom Kalt! kam der Anruf wegen des Hagelschadens.', 'Kalt', 'g', 'gemeldet'),
    ('hof', 'Ich war gestern beim Einkaufen und habe den Schaden gemeldet.', 'Einkaufen', 'b', 'frei'),
    ('hof', 'Ich war gestern beim Rangieren und habe den Schaden gemeldet.', 'Rangieren', 'b', 'frei'),
    ('hof', 'Ich war gestern beim Grillen und habe den Schaden gemeldet.', 'Grillen', 'b', 'frei'),
    ('hof', 'Ich war gestern beim Schwimmen und habe den Schaden gemeldet.', 'Schwimmen', 'b', 'frei'),
    ('hof', 'Ich war gestern beim Skifahren und habe den Schaden gemeldet.', 'Skifahren', 'b', 'frei'),
    ('hof', 'Ich war gestern beim Segeln und habe den Schaden gemeldet.', 'Segeln', 'b', 'frei'),
    ('hof', 'Ich war gestern beim Wandern und habe den Schaden gemeldet.', 'Wandern', 'b', 'frei'),
    ('hof', 'Ich war gestern beim Aufräumen und habe den Schaden gemeldet.', 'Aufräumen', 'b', 'frei'),
    ('hof', 'Ich war gestern beim Unfall dabei und habe den Schaden gemeldet.', 'Unfall', 'b', 'frei'),
    ('hof', 'Vom Hochwasser kam der Schaden im Keller.', 'Hochwasser', 'b', 'frei'),
    ('hof', 'Ich war gestern beim Baumarkt und habe den Schaden gemeldet.', 'Baumarkt', 'b', 'frei'),
    ('hof', 'Zum Glück ist niemand verletzt worden.', 'Glück', 'b', 'frei'),
    ('hof', 'Ich war gestern beim Rasenmähen und habe den Schaden gemeldet.', 'Rasenmähen', 'b', 'frei'),
    ('hof_beruf', 'Wir gehen nachher zum Fischer, frischen Fisch für das Fest kaufen.', 'Fischer', 'b', 'gemeldet'),
    ('hof_beruf', 'Den Anhänger fahren wir am Samstag zum Wagner zur Reparatur.', 'Wagner', 'b', 'gemeldet'),
    ('hof_beruf', 'Der Traktor vom Lohnunternehmer stand quer auf dem Feldweg.', 'Lohnunternehmer', 'b', 'frei'),
    ('hof_beruf', 'Die Kühe vom Nachbarhof standen auf der Straße.', 'Nachbarhof', 'b', 'frei'),
    ('hof_beruf', 'Der Unfall geschah beim Fischer in Inzell.', 'Fischer', 'g', 'weg'),
    ('hof_beruf', 'Wir waren gestern beim Wagner zum Essen.', 'Wagner', 'g', 'weg'),
    ('hof_beruf', 'Zum Gruber fahren wir am Montag.', 'Gruber', 'g', 'weg'),
    ('hof_beruf', 'Der Traktor vom Wimmer stand quer auf der Fahrbahn.', 'Wimmer', 'g', 'weg'),
    ('hof_beruf', 'Die Kühe vom Moarhof standen auf der Straße.', 'Moarhof', 'g', 'gemeldet'),
    ('hof_beruf', 'Der Traktor vom Kaltl stand quer auf dem Feldweg.', 'Kaltl', 'g', 'gemeldet'),
    ('hof_beruf', 'Die Kühe vom Bauernhof standen auf der Straße.', 'Bauernhof', 'b', 'frei'),
    ('jahr', 'Die Kellertür mit 1990 öffnen Sie bitte nur tagsüber.', '1990', 'g', 'weg'),
    ('jahr', 'Das Garagentor mit 1966 öffnen Mieter selbst.', '1966', 'g', 'weg'),
    ('jahr', 'Den Tresor mit 1958 öffnen Mitarbeiter der Filiale.', '1958', 'g', 'weg'),
    ('jahr', 'Den Heizungskeller mit 2011 betreten Handwerker nach Absprache.', '2011', 'g', 'gemeldet'),
    ('jahr', 'Das Schließfach mit 1972 öffnen Kunden selbst.', '1972', 'g', 'weg'),
    ('jahr', 'Die Tiefgarage mit 1770 betreten Frau Ostendorp selbst.', '1770', 'g', 'gemeldet'),
    ('jahr', 'Die Wohnungstür mit 1806 erreichten Bewohner bitte nur tagsüber.', '1806', 'g', 'gemeldet'),
    ('jahr', 'Mit 1563 schalten Herr Lohmeyer die Tiefgarage.', '1563', 'g', 'weg'),
    ('jahr', 'Mit 2016 bedienen Mieter das Rolltor.', '2016', 'g', 'weg'),
    ('jahr', 'Die Nebeneingangstür mit 1849 starten Nachbarn bitte nur tagsüber.', '1849', 'g', 'gemeldet'),
    ('jahr', 'Hinweis: Die Tiefgarage mit 1681 öffneten Handwerker auch am Wochenende.', '1681', 'g', 'weg'),
    ('jahr', 'Das Einfahrtstor mit 1751 betraten Mitarbeiter selbst.', '1751', 'g', 'gemeldet'),
    ('jahr', 'Den Tresor mit 9321 erreichten Sie selbst.', '9321', 'g', 'gemeldet'),
    ('jahr', 'Die Garage mit 1984 öffnen Gäste nur nach Rücksprache.', '1984', 'g', 'weg'),
    ('jahr', 'Den Keller mit 2003 aufsperren Monteure selbst.', '2003', 'g', 'weg'),
    ('jahr', 'Die Tiefgarage ist mit 1984 gesichert.', '1984', 'g', 'weg'),
    ('jahr', 'Die Haustür lässt sich mit 1990 aufschließen.', '1990', 'g', 'weg'),
    ('jahr', 'Das Gebäude ist mit 2021 erneuerter Heizung ausgestattet und mit 4471 gesichert.', '4471', 'g', 'gemeldet'),
    ('jahr', 'Das Gebäude ist mit 2021 erneuerter Heizung ausgestattet und mit 4471 gesichert.', '2021', 'b', 'frei'),
    ('jahr', 'Die Halle ist mit 2019 eingebauten Rolltoren gesichert.', '2019', 'b', 'frei'),
    ('jahr', 'Der Stall ist mit 1890 gebautem Dachstuhl versichert.', '1890', 'b', 'frei'),
    ('jahr', 'Die Lagerhalle ist mit 2019 modernisierter Einbruchmeldeanlage gesichert.', '2019', 'b', 'frei'),
    ('jahr', 'Die Garage ist mit 1998 sanierten Schiebetoren verschlossen.', '1998', 'b', 'frei'),
    ('jahr', 'Die Werkstatt ist mit 2015 abgesicherten Fenstern verschlossen.', '2015', 'b', 'frei'),
    ('jahr', 'Die Lagerhalle ist mit 2021 neu installierter Alarmanlage gesichert.', '2021', 'b', 'gemeldet'),
    ('jahr', 'Die Scheune ist mit 2019 komplett erneuerter Schließanlage gesichert.', '2019', 'b', 'gemeldet'),
    ('jahr', 'Das Lager ist mit 2018 zusätzlich montierten Gitterrosten gesichert.', '2018', 'b', 'gemeldet'),
    ('jahr', 'Die Halle ist mit 2021 erneuerter elektronischer Schließanlage gesichert.', '2021', 'b', 'frei'),
    ('jahr', 'Die Garage ist mit 2022 neuer Alarmanlage gesichert.', '2022', 'b', 'gemeldet'),
    ('jahr', 'Das Tor ist mit 2020 eingebauten, zertifizierten Rolltoren gesichert.', '2020', 'b', 'frei'),
    ('jahr', 'Die Halle ist mit 2017 vom Fachbetrieb eingebauter Stahltür gesichert.', '2017', 'b', 'gemeldet'),
    ('kamm_klammer', 'Datum (Geburt)\t\tTag 1 9\t\tMonat 0 1\t\tJahr 1 9 8 0', '1 9', 'g', 'weg'),
    ('kamm_klammer', 'Datum (Geburt)\t\tTag 1 9\t\tMonat 0 1\t\tJahr 1 9 8 0', '0 1', 'g', 'weg'),
    ('kamm_klammer', 'Datum (Geburt)\t\tTag 1 9\t\tMonat 0 1\t\tJahr 1 9 8 0', '1 9 8 0', 'g', 'weg'),
    ('kamm_klammer', 'Datum (Geburtstag)\t\tTag 2 5\t\tMonat 0 4\t\tJahr 1 9 8 1', '2 5', 'g', 'weg'),
    ('kamm_klammer', 'Datum (Geburtstag)\t\tTag 2 5\t\tMonat 0 4\t\tJahr 1 9 8 1', '0 4', 'g', 'weg'),
    ('kamm_klammer', 'Datum (Geburtstag)\t\tTag 2 5\t\tMonat 0 4\t\tJahr 1 9 8 1', '1 9 8 1', 'g', 'weg'),
    ('kamm_klammer', 'Datum (geb.)\t\tTag 2 5\t\tMonat 0 4\t\tJahr 1 9 8 1', '2 5', 'g', 'weg'),
    ('kamm_klammer', 'Datum (geb.)\t\tTag 2 5\t\tMonat 0 4\t\tJahr 1 9 8 1', '0 4', 'g', 'weg'),
    ('kamm_klammer', 'Datum (geb.)\t\tTag 2 5\t\tMonat 0 4\t\tJahr 1 9 8 1', '1 9 8 1', 'g', 'weg'),
    ('kamm_klammer', 'Datum der Geburt\t\tTag 2 5\t\tMonat 0 4\t\tJahr 1 9 8 1', '2 5', 'g', 'weg'),
    ('kamm_klammer', 'Datum der Geburt\t\tTag 2 5\t\tMonat 0 4\t\tJahr 1 9 8 1', '0 4', 'g', 'weg'),
    ('kamm_klammer', 'Datum der Geburt\t\tTag 2 5\t\tMonat 0 4\t\tJahr 1 9 8 1', '1 9 8 1', 'g', 'weg'),
    ('kamm_klammer', 'Kind (Geburtsdatum)\t\tTag 0 3\t\tMonat 1 1\t\tJahr 2 0 1 6', '0 3', 'g', 'weg'),
    ('kamm_klammer', 'Kind (Geburtsdatum)\t\tTag 0 3\t\tMonat 1 1\t\tJahr 2 0 1 6', '1 1', 'g', 'weg'),
    ('kamm_klammer', 'Kind (Geburtsdatum)\t\tTag 0 3\t\tMonat 1 1\t\tJahr 2 0 1 6', '2 0 1 6', 'g', 'weg'),
    ('kamm_klammer', 'Geburtsdatum (Fahrer)\t\tTag 1 9\t\tMonat 0 1\t\tJahr 1 9 8 0', '1 9', 'g', 'weg'),
    ('kamm_klammer', 'Geburtsdatum (Fahrer)\t\tTag 1 9\t\tMonat 0 1\t\tJahr 1 9 8 0', '0 1', 'g', 'weg'),
    ('kamm_klammer', 'Geburtsdatum (Fahrer)\t\tTag 1 9\t\tMonat 0 1\t\tJahr 1 9 8 0', '1 9 8 0', 'g', 'weg'),
    ('kamm_klammer', 'Datum (Antrag)\t\tTag 0 1\t\tMonat 1 0\t\tJahr 2 0 2 6', '2 0 2 6', 'b', 'frei'),
    ('kamm_klammer', 'Versicherungsbeginn (Datum)\t\tTag 0 1\t\tMonat 0 7\t\tJahr 2 0 2 6', '2 0 2 6', 'b', 'frei'),
    ('moebel_beruf', 'Der Küchenschrank hat den Code 2207, Farbe Eiche hell.', '2207', 'b', 'gemeldet'),
    ('moebel_beruf', 'Badschrank Code 8815 laut Aufbauanleitung, Spiegel mit LED.', '8815', 'b', 'gemeldet'),
    ('moebel_beruf', 'Der Kleiderschrank (Code 4471) wurde beim Umzug beschädigt.', '4471', 'b', 'gemeldet'),
    ('moebel_beruf', 'Wohnzimmerschrank Code 3360 – Glasfront gesprungen, Ersatz über den Händler.', '3360', 'b', 'gemeldet'),
    ('moebel_beruf', 'Die Rampe arbeitet als Einstiegshilfe für Rollstuhlfahrer.', 'Einstiegshilfe', 'b', 'frei'),
    ('moebel_beruf', 'Die Hebebühne arbeitet als Montagehilfe in der Werkstatt.', 'Montagehilfe', 'b', 'frei'),
    ('moebel_beruf', 'Code Badschrank: 8815', '8815', 'g', 'weg'),
    ('moebel_beruf', 'Küchenschrank (Code 2207)', '2207', 'g', 'weg'),
    ('moebel_beruf', 'Der Küchenschrank (Farbe weiß) lässt sich mit Code 2207 öffnen.', '2207', 'g', 'weg'),
    ('moebel_beruf', 'Der Verletzte arbeitet als Lagerhilfe.', 'Lagerhilfe', 'g', 'weg'),
    ('moebel_beruf', 'Die Bevollmächtigte arbeitet als Bürokraft.', 'Bürokraft', 'g', 'weg'),
    ('praep', 'Neben der Kreuzl saß der Fahrer.', 'Kreuzl', 'g', 'gemeldet'),
    ('praep', 'Laut dem Pfnürl hat der Nachbar den Unfall verursacht.', 'Pfnürl', 'g', 'gemeldet'),
    ('praep', 'Wegen dem Tremml kam die Feuerwehr zweimal.', 'Tremml', 'g', 'gemeldet'),
    ('praep', 'Seit dem Kreidlmayr weggezogen ist, steht das Haus leer.', 'Kreidlmayr', 'g', 'gemeldet'),
    ('praep', 'Mit der Tremml hat der Nachbar telefoniert.', 'Tremml', 'g', 'gemeldet'),
    ('praep', 'Für den Gsödl hat die Nachbarin unterschrieben.', 'Gsödl', 'g', 'gemeldet'),
    ('praep', 'Bei der Zeitlhofer meldete sich niemand.', 'Zeitlhofer', 'g', 'gemeldet'),
    ('praep', 'Ohne den Weichselbaumer wäre der Brand nicht entdeckt worden.', 'Weichselbaumer', 'g', 'gemeldet'),
    ('praep', 'Gegen die Kreidlmayr hat der Vermieter Klage erhoben.', 'Kreidlmayr', 'g', 'gemeldet'),
    ('praep', 'Laut der Pointnerin war das Fenster offen.', 'Pointnerin', 'g', 'gemeldet'),
    ('praep', 'Hinter dem Zachl fuhr der Lieferwagen.', 'Zachl', 'g', 'gemeldet'),
    ('praep', 'Beim Aushub für die Bodenplatte beschädigte der Bagger die Leitung.', 'Bodenplatte', 'b', 'frei'),
    ('praep', 'Beim Aushub für die Bodenplatte beschädigte der Bagger die Leitung.', 'Bagger', 'b', 'frei'),
    ('praep', 'Mit dem Bagger hat der Fahrer die Leitung beschädigt.', 'Bagger', 'b', 'frei'),
    ('praep', 'Nach dem Sturm hat der Nachbar den Schaden gemeldet.', 'Sturm', 'b', 'gemeldet'),
    ('praep', 'Wegen dem Hagel kam die Feuerwehr.', 'Hagel', 'b', 'frei'),
    ('praep', 'Laut dem Gutachten war das Fenster offen.', 'Gutachten', 'b', 'frei'),
    ('praep', 'Mit der Hotline hat der Kunde telefoniert.', 'Hotline', 'b', 'frei'),
    ('praep', 'Bei der Allianz meldete sich niemand.', 'Allianz', 'b', 'frei'),
    ('praep', 'Von der Feuerwehr stammt das Foto vom Schaden.', 'Feuerwehr', 'b', 'frei'),
    ('praep', 'Seit dem Umzug steht das Haus leer.', 'Umzug', 'b', 'frei'),
    ('praep', 'Über den Makler hat sich der Kunde beschwert.', 'Makler', 'b', 'frei'),
    ('praep', 'Wegen dem Wasserschaden kam der Installateur.', 'Wasserschaden', 'b', 'frei'),
    ('praep', 'Mit dem Navi hat der Fahrer den Weg gesucht.', 'Navi', 'b', 'frei'),
    ('praep', 'Mit dem Fuchs hat der Jäger Ärger.', 'Fuchs', 'b', 'frei'),
    ('raumcode', 'Zum Abschalten des Feueralarms: 3401', '3401', 'g', 'weg'),
    ('raumcode', 'Probealarm: Code zum Ausschalten 7329', '7329', 'g', 'weg'),
    ('raumcode', 'Hinterhofcode 4471', '4471', 'g', 'weg'),
    ('raumcode', 'Zugangscode Kellerabteil 5512', '5512', 'g', 'weg'),
    ('raumcode', 'PIN für Waschküche 2290', '2290', 'g', 'weg'),
    ('raumcode', 'Der Küchenschrank (Artikel 7731) lässt sich mit dem Code 6631 öffnen.', '6631', 'g', 'weg'),
    ('raumcode', 'Schadenort Waschküche, Code 9917', '9917', 'g', 'gemeldet'),
    ('raumcode', 'Schadenort: Heizungsraum, Code 5207', '5207', 'g', 'gemeldet'),
    ('raumcode', 'Code für den Wintergarten: 8841', '8841', 'g', 'weg'),
    ('raumcode', 'Die Hintertür hat den Code ZT77.', 'ZT77', 'g', 'weg'),
    ('raumcode', 'Gebäudecode 1101 (Wohngebäude, Massivbauweise) laut Gebäudeliste.', '1101', 'b', 'frei'),
    ('raumcode', 'Raumcode 2017 laut Raumbuch: Besprechungsraum im 2. OG.', '2017', 'b', 'frei'),
    ('raumcode', 'Lagercode 4410 laut Kostenstellenplan, Lagerort Regal 3.', '4410', 'b', 'frei'),
    ('raumcode', 'Werkstattcode 4420 für die Abrechnung der Arbeitsstunden.', '4420', 'b', 'frei'),
    ('raumcode', 'Hallencode 0302 im Lageplan des Gewerbeparks.', '0302', 'b', 'frei'),
    ('raumcode', 'Kellercode 1120 laut Wohnungsübergabeprotokoll (Kellerabteil Nr. 12).', '1120', 'b', 'frei'),
    ('raumcode', 'Lagerhallecode: 9444', '9444', 'g', 'weg'),
    ('regen', 'Wie Herr Notar Regen sagte, ist der Antrag vollständig.', 'Regen', 'g', 'weg'),
    ('regen', 'Wie Herr Pfarrer Regen sagte, ist der Antrag vollständig.', 'Regen', 'g', 'weg'),
    ('regen', 'Wie Frau Notarin Wasser sagte, ist der Antrag vollständig.', 'Wasser', 'g', 'weg'),
    ('regen', 'Laut Herrn Rechtsanwalt Regen ist die Frist gewahrt.', 'Regen', 'g', 'weg'),
    ('regen', 'Herr Bürgermeister Wasser hat zugestimmt.', 'Wasser', 'g', 'weg'),
    ('regen', 'Den Zaun rammte der Wasser.', 'Wasser', 'g', 'gemeldet'),
    ('regen', 'Am Steuer saß der Wasser.', 'Wasser', 'g', 'gemeldet'),
    ('regen', 'Der Wasser hat den Zaun beschädigt.', 'Wasser', 'g', 'gemeldet'),
    ('regen', 'Am Steuer saß der Regen.', 'Regen', 'g', 'gemeldet'),
    ('regen', 'Die Wasser hat den Schaden gemeldet.', 'Wasser', 'g', 'gemeldet'),
    ('regen', 'Kundin Morgen ist ab Montag erreichbar.', 'Morgen', 'g', 'gemeldet'),
    ('regen', 'Rückrufbitte\nKundin Morgen ist ab Montag erreichbar.', 'Morgen', 'g', 'gemeldet'),
    ('regen', 'Nachbar Abend hat den Schaden gemeldet.', 'Abend', 'g', 'gemeldet'),
    ('regen', 'Den Zaun hat der Sturm beschädigt.', 'Sturm', 'b', 'frei'),
    ('regen', 'Das Wasser lief in den Keller.', 'Wasser', 'b', 'frei'),
    ('regen', 'Der Regen hat den Keller geflutet.', 'Regen', 'b', 'frei'),
    ('regen', 'Das Feuer hat den Stadel zerstört.', 'Feuer', 'b', 'frei'),
    ('regen', 'Den Zaun beschädigte das Unwetter.', 'Unwetter', 'b', 'frei'),
    ('regen', 'Morgen ist der Kunde erreichbar.', 'Morgen', 'b', 'frei'),
    ('regen', 'Kunde morgen erreichbar.', 'morgen', 'b', 'frei'),
    ('titel', 'Unser Mitarbeiter Herr Brandstätter meldet sich nächste Woche bei Ihnen.', 'Brandstätter', 'g', 'weg'),
    ('titel', 'Unser Mitarbeiter Herr Brandstätter meldet sich nächste Woche bei Ihnen.', 'Herr', 'b', 'frei'),
    ('titel', 'Ihre Sachbearbeiterin Frau Oberholzer ist ab Montag wieder im Büro.', 'Oberholzer', 'g', 'weg'),
    ('titel', 'Ihre Sachbearbeiterin Frau Oberholzer ist ab Montag wieder im Büro.', 'Frau', 'b', 'frei'),
    ('titel', 'Der Gutachter Dipl.-Ing. Rauchenberger besichtigt das Dach am Donnerstag.', 'Rauchenberger', 'g', 'weg'),
    ('titel', 'Der Gutachter Dipl.-Ing. Rauchenberger besichtigt das Dach am Donnerstag.', 'Dipl', 'b', 'frei'),
    ('titel', 'Ihre Kollegin Frau Dr. Seeberger hat die Unterlagen bereits geprüft.', 'Seeberger', 'g', 'weg'),
    ('titel', 'Ihre Kollegin Frau Dr. Seeberger hat die Unterlagen bereits geprüft.', 'Frau', 'b', 'frei'),
    ('titel', 'Wir haben Ihren Vermieter Herrn Huberbauer informiert.', 'Huberbauer', 'g', 'weg'),
    ('titel', 'Wir haben Ihren Vermieter Herrn Huberbauer informiert.', 'Herrn', 'b', 'frei'),
    ('titel', 'Der Hausmeister Herr Zellhuber öffnet am Montag den Heizungsraum.', 'Zellhuber', 'g', 'weg'),
    ('titel', 'Der Hausmeister Herr Zellhuber öffnet am Montag den Heizungsraum.', 'Herr', 'b', 'frei'),
    ('titel', 'Unser Kunde Herr Wasser bittet um Rückruf.', 'Wasser', 'g', 'weg'),
    ('titel', 'Unser Kunde Herr Wasser bittet um Rückruf.', 'Herr', 'b', 'frei'),
    ('titel', 'Nachbarin Pfarrer hat angerufen.', 'Pfarrer', 'g', 'gemeldet'),
    ('titel', 'Rücksprache mit Mieter Käufer am Montag.', 'Käufer', 'g', 'gemeldet'),
    ('titel', 'Kunde Halter wurde befragt.', 'Halter', 'g', 'gemeldet'),
]


@pytest.mark.parametrize("gruppe, text, wert, art, soll", FAELLE,
                         ids=[f"{g}-{i}" for i, (g, *_r) in enumerate(FAELLE)])
def test_n8_zeilen_der_abnahme(gruppe, text, wert, art, soll):
    ist = _zustand(text, wert)
    if art == "g":
        erlaubt = ("weg",) if soll == "weg" else ("weg", "gemeldet")
    else:
        erlaubt = ("frei",) if soll == "frei" else ("frei", "gemeldet")
    assert ist in erlaubt, (gruppe, text, wert, ist)


# ----------------------------------------------------------------------
# d6 der Differenzprobe: Allerweltswort zwischen Personenwort und Vorname ist der Familienname
# ----------------------------------------------------------------------
def test_d6_zeuge_allerweltswort_vor_vorname_geschwaerzt():
    assert _zustand("Zeuge Wasser Anna hat den Brand gesehen.", "Wasser") == "weg"
    assert _zustand("Zeugenliste\nZeuge Wasser Anna hat den Brand gesehen.", "Wasser") == "weg"


def test_d6_aussage_hinter_doppelpunkt_gemeldet_lage_frei():
    assert _zustand("Mieter Regen: kein Schaden", "Regen") == "gemeldet"
    assert _zustand("Nachbar Sonne: kein Schaden", "Sonne") == "gemeldet"
    assert _zustand("Mieter Dachgeschoss: kein Schaden", "Dachgeschoss") == "frei"
    assert _zustand("Ehefrau Mitversichert: ja", "Mitversichert") == "frei"


# ----------------------------------------------------------------------
# AB6U-09: Fahrzeug- bzw. Parteibuchstaben A und B über Spaltentrennern sind kein Name aus zwei Buchstaben – ein
# Name in weit gesetzten Kästchen ("L ⇥⇥ I", Abnahme 4 AB4-17) bleibt ein Wert
# ----------------------------------------------------------------------
def test_ab6u_09_parteibuchstaben_kein_name():
    assert not any(k == "namen" for k, _ in _kamm("Unterschrift der Fahrer\nA\t\tB"))
    assert not any(k == "namen" for k, _ in _kamm("Fahrer\t\tFahrzeug A\t\tFahrzeug B\nVersicherungsnehmer\t\tA\t\tB"))
    assert _zustand("Unterschrift der Fahrer\nA\t\tB", "A") == "frei"


def test_ab6u_09_gegenprobe_initialen_in_kaesten():
    assert ("namen", "L\t\tI") in _kamm("Name\t\tL\t\tI")
    assert ("namen", "K H") in _kamm("Initialen\t\tK H")


# ----------------------------------------------------------------------
# AB6U-15: gesperrter Name hinter einem langen Feldnamen in derselben Höhe – die Zeilenbildung legt beide in eigene
# Zeilen, der Feldname gilt trotzdem (Textebene ohne Kästchen)
# ----------------------------------------------------------------------
def test_ab6u_15_gesperrter_name_neben_langem_feldnamen_pdf(tmp_path):
    import pymupdf as fitz
    from anonymisierer.analyse import analysiere_pdf
    doc = fitz.open()
    s = doc.new_page(width=595, height=842)
    feld = "Name des Versicherungsnehmers"
    breite = fitz.get_text_length(feld, fontname="helv", fontsize=10.5)
    s.insert_text((50, 70), "Antragsdatum", fontsize=10.5, fontname="helv")
    s.insert_text((50 + breite + 20, 70), "0 1 1 0 2 0 2 6", fontsize=10.5, fontname="helv")
    s.insert_text((50, 86.8), feld, fontsize=10.5, fontname="helv")
    s.insert_text((50 + breite - 12, 86.8), "K R A U S", fontsize=10.5, fontname="helv")  # Feldname reicht in den Wert
    pfad = tmp_path / "kraus.pdf"
    doc.save(pfad)
    doc.close()
    erg = analysiere_pdf(pfad, ALLE, [], [], profil="hoch")
    seite = erg["modell"].seiten[0]
    assert "\nK R A U S" in seite.text, repr(seite.text)            # die Zeilenbildung trennt Feldname und Wert
    werte = {st["text"] for f in erg["funde"] if f["kategorie"] == "namen" for st in f["stellen"] if st.get("an", True)}
    assert "K R A U S" in werte, erg["funde"]


def test_ab6u_15_ineinandergeschobener_feldname_gemeldet():
    """Rücken Feldname und Wert auf der Textebene zusammen ("…nehmersK R A U S"), findet die Erkennung den Feldnamen
    nicht – die Selbstkontrolle meldet die Sperrschrift; Stempel wie "M U S T E R" nicht."""
    assert any("K R A U S" in t for t, _ in _verdacht("Name des VersicherungsnehmersK R A U S"))
    assert any("W E B E R" in t for t, _ in _verdacht("Fahrer\nW E B E R"))
    for text in ("M U S T E R", "K O P I E", "Schadenklasse A B C D", "Kennzeichen X X X X"):
        assert not _verdacht(text), text


# ----------------------------------------------------------------------
# AB6U-06: ein lesbarer eigener Feldname ohne Personenbezug erbt nicht den Personen-Feldnamen der Zeile
# ----------------------------------------------------------------------
@pytest.mark.parametrize("feldname, sache", [
    ("Marke", True), ("Modell", True), ("Bank", True), ("Farbe", True), ("Tarif", True), ("Tarifgruppe:", True),
    ("See", False), ("Straße", False), ("Name", False), ("", False),
])
def test_ab6u_06_sach_feldname(feldname, sache):
    from anonymisierer.detektoren import kammfelder
    assert kammfelder._sach_feldname(feldname) is sache


# ----------------------------------------------------------------------
# Laufzeit (AB6U-11, AB6U-12 und die neuen bzw. geänderten Schleifen dieser Nachbesserung): 8k gegen 64k Zeichen,
# Schranke 2,0 (zeitmessung.wachstum_messen)
# ----------------------------------------------------------------------
def test_ab6u_11_langes_wort_hinter_beim_waechst_linear():
    """Form a6_hof_langwort der Abnahme ("Beim Abbb… ist der Stadel abgebrannt.", 2k gegen 16k Zeichen): Flurname- und
    Kompositum-Prüfung nur über das Wortende (Eingriff: alle Endstücke des Worts)."""
    klein = "Beim A" + "b" * 2000 + " ist der Stadel abgebrannt."
    gross = "Beim A" + "b" * 16000 + " ist der Stadel abgebrannt."
    wachstum, _, zeit = _wachstum(lambda: pruefe_text(klein), lambda: pruefe_text(gross), 8, 2.0)
    assert wachstum < 2.0, f"pruefe_text (Langwort hinter Beim) wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_ab6u_12_beruf_des_ohne_person_waechst_linear():
    """beruf_des_ohne_person sucht die Person im Satz (Eingriff E9 der Abnahme: im ganzen Text davor)."""
    baustein = "Für den Beruf des Bäckers gilt die Gefahrengruppe A, "
    klein, gross = _zeile(baustein, 8000), _zeile(baustein, 64000)
    wachstum, _, zeit = _wachstum(lambda: _funde(klein), lambda: _funde(gross), 8, 2.0)
    assert wachstum < 2.0, f"analysiere_text (Beruf des) wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_ab6u_11_hof_gegenbeleg_langes_wort_waechst_linear():
    """_hof_gegenbeleg allein mit einem langen Wort (2k gegen 16k Zeichen; Eingriff: ungeankerte Grundwort-Regex)."""
    klein_w, gross_w = "A" + "b" * 2000, "A" + "b" * 16000
    klein, gross = "Beim " + klein_w + " ist", "Beim " + gross_w + " ist"
    wachstum, _, zeit = _wachstum(lambda: personenkontext._hof_gegenbeleg(klein, 5, klein_w, wissen),
                                  lambda: personenkontext._hof_gegenbeleg(gross, 5, gross_w, wissen), 8, 2.0)
    assert wachstum < 2.0, f"_hof_gegenbeleg wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_n8_hofname_beruf_mit_geschaeft_lange_zeile_waechst_linear():
    """Geschäft in der Zeile je Zeile einmal gesucht (Eingriff: je Treffer die ganze Zeile)."""
    baustein = "zum Fischer frischen Fisch kaufen und beim Wagner zur Reparatur, "
    klein, gross = _zeile(baustein, 8000), _zeile(baustein, 64000)
    wachstum, _, zeit = _wachstum(lambda: personenkontext.hofnamen(klein, wissen),
                                  lambda: personenkontext.hofnamen(gross, wissen), 8, 2.0)
    assert wachstum < 2.0, f"hofnamen wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_n8_geraet_meldet_uns_langer_satz_waechst_linear():
    """Satzgegenstand vor "meldete uns" nur im Fenster davor (Eingriff: der ganze Satz davor)."""
    baustein = "das Garagentor meldete uns den Code 3017 und der Vermieter zeigte uns den Code 2827 "
    klein, gross = _zeile(baustein, 8000), _zeile(baustein, 64000)
    wachstum, _, zeit = _wachstum(lambda: kennungsformen.zugangsdaten(klein),
                                  lambda: kennungsformen.zugangsdaten(gross), 8, 2.0)
    assert wachstum < 2.0, f"zugangsdaten wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_n8_geraet_und_alarm_code_mehrdeutig_lange_zeile_waechst_linear():
    baustein = "Garagentor: Code DH2, Feueralarmcode 3401; Gartenhaus-Code DG453; "
    klein, gross = _zeile(baustein, 8000), _zeile(baustein, 64000)

    def lauf(t):
        return kennungsformen.geraet_code_mehrdeutig(t), kennungsformen.alarm_code_mehrdeutig(t)
    wachstum, _, zeit = _wachstum(lambda: lauf(klein), lambda: lauf(gross), 8, 2.0)
    assert wachstum < 2.0, f"geraet/alarm_code_mehrdeutig wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_n8_personenwort_allerwelt_genitiv_waechst_linear():
    baustein = "Wir empfehlen Kunden Abschluss einer Versicherung und Mieter Regen: kein Schaden, "
    klein, gross = _zeile(baustein, 8000), _zeile(baustein, 64000)
    wachstum, _, zeit = _wachstum(lambda: personenkontext.personenwort_allerwelt(klein, wissen),
                                  lambda: personenkontext.personenwort_allerwelt(gross, wissen), 8, 2.0)
    assert wachstum < 2.0, f"personenwort_allerwelt wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_n8_kammfeld_feldname_gleiche_hoehe_waechst_linear():
    """Feldname am Ende der vorigen Zeile über den Index der Feldnamen (Eingriff: alle Feldnamen der Seite je Wert);
    gemessen wird nur die Zuordnung je Wert, Seitenmodell und Feldnamen sind vorab gebildet."""
    from anonymisierer.detektoren import kammfelder, struktur

    def vorbereiten(n):
        seite = seitenmodell.dokument_aus_text("Name\nK R A U S\n" * max(1, n // 15)).seiten[0]
        ets = [et for et in struktur.etiketten(seite) if et.arten]
        vorige = {id(z): seite.zeilen[i - 1] for i, z in enumerate(seite.zeilen) if i}
        werte = [(z, z.start, z.ende) for z in seite.zeilen if seite.text[z.start:z.ende] == "K R A U S"]
        return seite, ets, kammfelder._ets_index(ets), vorige, werte

    def lauf(v):
        seite, ets, idx, vorige, werte = v
        return [kammfelder._etikett_gleiche_hoehe(seite, ets, idx, seite.text, vorige.get(id(z)), s, e)
                for z, s, e in werte]
    klein, gross = vorbereiten(8000), vorbereiten(64000)
    lauf(klein)
    wachstum, _, zeit = _wachstum(lambda: lauf(klein), lambda: lauf(gross), 8, 2.0)
    assert wachstum < 2.0, f"_etikett_gleiche_hoehe wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_n8_sperrschrift_neben_platzhaltern_waechst_linear():
    """Sperrschrift-Meldung: gesperrte Bereiche über den Index (Eingriff: alle Platzhalter je Treffer); gemessen wird
    nur _gesperrte_folge, die Seitenprüfung ist vorab gebildet."""
    from anonymisierer import restrisiko

    def vorbereiten(n):
        m = seitenmodell.dokument_aus_text(_zeile("[NAME] W E B E R, ", n)).seiten[0]
        return restrisiko._Seitenpruefung(m, restrisiko._Wissen(restrisiko._wissen_laden()))

    def lauf(p):
        p.kandidaten = []
        p._gesperrte_folge()
        return p.kandidaten
    klein, gross = vorbereiten(8000), vorbereiten(64000)
    assert lauf(klein)
    wachstum, _, zeit = _wachstum(lambda: lauf(klein), lambda: lauf(gross), 8, 2.0)
    assert wachstum < 2.0, f"_gesperrte_folge wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


def test_n8_selbstkontrolle_lange_zeile_waechst_linear():
    """Selbstkontrolle über eine lange Zeile mit den neuen Meldungen (Einrichtung, Titel, Doppelpunkt-Aussage)."""
    baustein = ("Die Bank hat angerufen. Unser Mitarbeiter Herr [NAME] meldet sich. Nachbar Sonne: kein Schaden. "
                "Fahrer W E B E R und [NAME], ")
    klein, gross = _zeile(baustein, 8000), _zeile(baustein, 64000)
    wachstum, _, zeit = _wachstum(lambda: pruefe_text(klein), lambda: pruefe_text(gross), 8, 2.0)
    assert wachstum < 2.0, f"pruefe_text wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


# ----------------------------------------------------------------------
# Nachbesserung 8, zweiter Schnappschuss (Über-Probe der Abnahme 6 Ende zu Ende): Anrede vor einem geschwärzten Namen,
# Telegrammstil vor einem Verb des Gebens, Raumcode mit Planbezug, Feldname unter dem Feld, Namen-Zeile, Sperrschrift
# ----------------------------------------------------------------------
def test_ab6u_07_anrede_vor_platzhalter_in_der_ausgabe_kein_verdacht(tmp_path):
    """In der Ausgabe steht der Platzhalter nicht im Seitentext ("Herr ⇥⇥ begleitet"): Anrede und Titel vor dem
    geschwärzten Namen sind kein möglicher Name (Über-Probe t01/t02/t06/x03: Verdacht auf „Herr“, „Frau“, „Dipl“)."""
    import pymupdf as fitz
    from anonymisierer import auftrag as A
    from anonymisierer.analyse import analysiere_pdf
    from anonymisierer.schwaerzung import schwaerze_pdf
    zeilen = ["Sehr geehrte Damen und Herren,",
              "der Gutachter Dipl.-Ing. Rauchenberger besichtigt das Dach am Donnerstag.",
              "Unser Mitarbeiter Herr Brandstätter begleitet den Termin.",
              "Ihre Sachbearbeiterin Frau Oberholzer ist ab Montag wieder im Büro."]
    doc = fitz.open()
    s = doc.new_page(width=595, height=842)
    for i, z in enumerate(zeilen):
        s.insert_text((50, 80 + 18 * i), z, fontsize=10, fontname="helv")
    pfad = tmp_path / "brief.pdf"
    doc.save(pfad)
    doc.close()
    erg = analysiere_pdf(pfad, A.standard_kategorien(), [], [], profil="hoch")
    aus = schwaerze_pdf(pfad, erg["funde"], ziel_ordner=tmp_path / "aus")
    with fitz.open(aus["ausgabe"]) as d:
        text = d[0].get_text()
    assert not any(n in text for n in ("Rauchenberger", "Brandstätter", "Oberholzer")), text
    verdacht = [v.text for v in aus.get("verdacht") or []]
    assert not any(v in ("Herr", "Frau", "Dipl") for v in verdacht), verdacht


@pytest.mark.parametrize("text, wert, soll", [
    ("Heute Nachbar Regen angerufen, er hat den Rauch gesehen.", "Regen", "gemeldet"),
    ("Heute Kunde Regen Bescheid gegeben.", "Regen", "gemeldet"),
    ("Gestern Kollegin Wasser Unterlagen zugeschickt.", "Wasser", "gemeldet"),
    ("Danach Nachbar Wasser zur Rücksprache angerufen.", "Wasser", "gemeldet"),
    ("Wir haben Nachbar Wasser den Schlüssel gegeben.", "Wasser", "gemeldet"),
    ("Leider konnte Mitarbeiter Auskunft zum Stand nicht geben, Rückruf folgt.", "Auskunft", "frei"),
    ("Heute Vermieterin Nachweis über den Austausch der Zylinder angefordert.", "Nachweis", "frei"),
    ("Danach Kunde Fragebogen zur Invalidität zugeschickt.", "Fragebogen", "frei"),
    ("Heute Kunde Kopie der Polizeianzeige erhalten und Stehlgutliste angefordert.", "Kopie", "gemeldet"),
])
def test_ab6u_03_telegrammstil_geben_frei_person_gemeldet(text, wert, soll):
    """Vor einem Verb des Gebens oder Schickens ist das Wort hinter dem Personenwort das Ding (frei); mit einem weiteren
    Hauptwort dazwischen oder vor einem Verb, das eine Person zum Gegenstand hat, bleibt es gemeldet (Regen, Wasser)."""
    ist = _zustand(text, wert)
    if soll == "frei":
        assert ist == "frei", (text, ist)
    else:
        assert ist in ("weg", "gemeldet"), (text, ist)


@pytest.mark.parametrize("text, wert, soll", [
    ("Raumcode 2017 laut Raumbuch: Besprechungsraum im 2. OG.", "2017", "frei"),
    ("Hallencode 0302 im Lageplan des Gewerbeparks.", "0302", "frei"),
    ("Der Kellercode lautet 1120.", "1120", "weg"),
    ("Der Kellercode ist 1120, siehe Übergabeprotokoll.", "1120", "weg"),
    ("Lagerhallecode: 9444 (laut Schlüsselliste)", "9444", "weg"),
    ("Werkraumcode 2045 bitte nicht weitergeben.", "2045", "weg"),
])
def test_ab6u_04_raumcode_mit_planbezug_frei(text, wert, soll):
    ist = _zustand(text, wert)
    assert ist == soll if soll == "frei" else ist in ("weg",), (text, ist)


def _feld(y0, hoehe=18.0, x0=57.0, n=6):
    kaesten = [(x0 + 14.0 * k, y0, x0 + 14.0 * (k + 1), y0 + hoehe) for k in range(n)]
    return {"kaesten": kaesten, "rahmen": (x0, y0, x0 + 14.0 * n, y0 + hoehe), "gefuellt": [True] * n}


@pytest.mark.parametrize("ueber, unter, soll", [
    (3.2, 11.3, False),     # Feldname unter dem Feld (Kamm-Probe 6 a02): bleibt beim Feld darüber
    (2.9, 10.6, False),
    (3.0, 5.8, True),       # enger Zeilenabstand, Feldname über dem Feld (eigen606_eng, c023): gehört zum Feld darunter
    (4.3, 7.9, True),
    (5.0, 5.3, True),
])
def test_a6_08_ab6u_16_feldname_unter_dem_feld_nach_abstandsverhaeltnis(ueber, unter, soll):
    from anonymisierer import kammraster
    oben = _feld(100.0)
    oberkante = 118.0 + ueber
    unterkante = oberkante + 7.0
    unten = _feld(unterkante + unter)
    assert kammraster.gehoert_zum_feld_darunter(oben, [oben, unten], oberkante, unterkante) is soll


@pytest.mark.parametrize("text, soll", [("Vomame", True), ("Nanne", True), ("Geburtsnarne", True), ("Fate", False),
                                        ("Br", False), ("Make", False), ("Tat", False), ("Moll", False),
                                        ("Fabte", False)])
def test_ab6u_06_eigener_feldname_wie_namensteil(text, soll):
    from anonymisierer.detektoren import kammfelder
    assert kammfelder._wie_namensteil(text) is soll


def test_ab6u_06_sperrschrift_hinter_sach_feldname_frei():
    assert not [v for v in _verdacht("Fahrzeughalter\t\tMarke\t\tO P E L\t\tModell\t\tA S T R A")
                if "Sperrschrift" in v[1]]
    assert not _verdacht("Versicherungsnehmer\t\tTarif\t\tK O M F O R T\t\tFarbe\t\tS I L B E R")
    assert any("Sperrschrift" in v[1] for v in _verdacht("Fahrer\t\tK R A U S"))


def test_ab6u_03_ding_vor_gebeverb_lange_zeile_waechst_linear():
    """Telegrammstil vor einem Verb des Gebens: nur die 80 Zeichen hinter dem Wort (Eingriff E10: Satzteil ohne
    Grenze – auf einer Zeile ohne Satzzeichen der ganze Resttext je Treffer)."""
    baustein = "Heute Kunde Unterlagen zur Trocknung zugeschickt und Kunde Regen Bescheid gegeben und "
    klein, gross = _zeile(baustein, 8000), _zeile(baustein, 64000)
    assert personenkontext.personenwort_allerwelt(klein)
    wachstum, _, zeit = _wachstum(lambda: personenkontext.personenwort_allerwelt(klein),
                                  lambda: personenkontext.personenwort_allerwelt(gross), 8, 2.0)
    assert wachstum < 2.0, f"personenwort_allerwelt wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


@pytest.mark.parametrize("text, werte, soll", [
    ("Geburtsdaten der mitversicherten Kinder\nKind 1\t\tTag 1 2\t\tMonat 0 5\t\tJahr 2 0 1 7\n"
     "Kind 2\t\tTag 3 0\t\tMonat 0 9\t\tJahr 2 0 2 0", ("1 2", "0 5", "2 0 1 7", "3 0", "0 9", "2 0 2 0"), True),
    ("Geburtsdatum der versicherten Personen\nPartner/in\t\tTag 0 8\t\tMonat 0 3\t\tJahr 1 9 7 9",
     ("0 8", "0 3", "1 9 7 9"), True),
    ("Geburtsdatum\nKind 1\t\tTag 0 5\t\tMonat 0 9\t\tJahr 2 0 1 7", ("0 5", "0 9", "2 0 1 7"), True),
    ("Versicherungsbeginn\nKind 1\t\tTag 0 1\t\tMonat 1 2\t\tJahr 2 0 2 6", ("0 1", "1 2", "2 0 2 6"), False),
    ("Antragsdatum\nKind 1\t\tTag 0 1\t\tMonat 1 2\t\tJahr 2 0 2 6", ("0 1", "1 2", "2 0 2 6"), False),
])
def test_a6_14_teilzeilen_mit_zeilentext_unter_geburtsdatum(text, werte, soll):
    """Zeilen "Kind 1 ⇥ Tag [..] Monat [..] Jahr [....]" unter einer Überschrift mit Geburtsdatum: die Teile sind ein
    Geburtsdatum (vorher auf allen Ständen lesbar); unter "Versicherungsbeginn" oder "Antragsdatum" nicht."""
    gefunden = {st["text"] for f in _funde(text) for st in f["stellen"] if st.get("an", True) and f["kategorie"] == "geburt"}
    if soll:
        assert all(w in gefunden for w in werte), (text, gefunden)
    else:
        assert not gefunden, (text, gefunden)


@pytest.mark.parametrize("text, wert, soll", [
    ("Gebäudeliste zum Sammelvertrag Gewerbe\nGebäudecode 1101 (Wohngebäude, Massivbauweise), Versicherungssumme "
     "1.200.000 EUR\nGebäudecode 2203 (Lagerhalle, Stahlbau), Versicherungssumme 860.000 EUR", "2203", "gemeldet"),
    ("Code- und Schlüsselliste\nKellercode 4711\nGaragencode 0815", "0815", "weg"),
    ("Mieterliste\nKellercode 4711 (Familie Huber)", "4711", "weg"),
    ("Hausordnung\nKellercode 4711", "4711", "weg"),
])
def test_ab6u_04_raumcode_unter_gebaeudeliste_nicht_geschwaerzt(text, wert, soll):
    """Listenzeilen "<Raum>code N …" unter einer Gebäude-, Raum- oder Inventarliste: Ordnungsnummern, nicht geschwärzt
    (die Selbstkontrolle prüft zeilenweise und meldet sie); unter einer Code-, Schlüssel- oder Mieterliste geschwärzt."""
    ist = _zustand(text, wert)
    assert ist == soll if soll == "weg" else ist in ("frei", "gemeldet"), (text, ist)


def test_ab6u_04_liste_darueber_lange_liste_waechst_linear():
    """Überschrift einer Liste über vielen Zeilen "<Raum>code N": je Wert höchstens zwölf Zeilen und 300 Zeichen
    zurück (Eingriff E13: ohne die Grenze von zwölf Zeilen läuft jeder Wert bis zur Überschrift zurück)."""
    baustein = "Gebäudecode 1101 (Wohngebäude), Summe 1.000 EUR\n"
    klein, gross = "Gebäudeliste\n" + _zeile(baustein, 8000), "Gebäudeliste\n" + _zeile(baustein, 64000)
    wachstum, _, zeit = _wachstum(lambda: kennungsformen.zugangsdaten(klein),
                                  lambda: kennungsformen.zugangsdaten(gross), 8, 2.0)
    assert wachstum < 2.0, f"zugangsdaten (Raumcode-Liste) wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


@pytest.mark.parametrize("ueber, unter, soll", [
    (3.2, 11.3, True),      # "Name" unter [KRAUS], [45678] erst 11,3 pt darunter: Feldname des Felds darüber (a02)
    (3.0, 5.8, False),      # enger Zeilenabstand: der Feldname des Felds darunter (eigen606_eng)
    (16.0, 4.0, False),     # Feldname mit Abstand unter dem Feld darüber und direkt über dem Feld (k6)
])
def test_ab6u_16_feldname_ueber_dem_feld_gehoert_zum_feld_darueber(ueber, unter, soll):
    from anonymisierer import kammraster
    oben = _feld(100.0)
    oberkante = 118.0 + ueber
    unterkante = oberkante + 7.0
    feld = _feld(unterkante + unter)
    assert kammraster.gehoert_zum_feld_darueber(feld, [oben, feld], oberkante, unterkante) is soll


def test_ab6u_16_feld_darueber_viele_felder_waechst_linear():
    """Feld über dem Feldnamen über den Index der Unterkanten (Eingriff E14: alle Felder der Seite je Feld)."""
    from anonymisierer import kammraster

    def felder(n):
        return [_feld(100.0 + 30.0 * i) for i in range(n)]
    klein, gross = felder(250), felder(2000)

    def lauf(fs):
        return [kammraster.gehoert_zum_feld_darueber(f, fs, kammraster.kopfkasten(f)[1] - 8.0,
                                                     kammraster.kopfkasten(f)[1] - 4.0) for f in fs]
    lauf(klein)
    wachstum, _, zeit = _wachstum(lambda: lauf(klein), lambda: lauf(gross), 8, 2.0)
    assert wachstum < 2.0, f"gehoert_zum_feld_darueber wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


@pytest.mark.parametrize("text, wert, soll", [
    ("Geburtsdatum Antragsteller\t\t1 2 0 5 1 9 7 9", "1 2 0 5 1 9 7 9", "geburt"),
    ("Geburtsdatum der versicherten Person\t\t0 5 0 3 1 9 8 4", "0 5 0 3 1 9 8 4", "geburt"),
    ("Name des Antragstellers\t\tW A L L N E R", "W A L L N E R", "namen"),
])
def test_a6_14_geburtsdatum_mit_person_als_feldname(text, wert, soll):
    """"Geburtsdatum Antragsteller ⇥⇥ 1 2 0 5 1 9 7 9": die Person ergänzt den Feldnamen des Geburtsdatums (auf allen
    Ständen lesbar bzw. nur über den Verdacht anderer Werte gemeldet)."""
    gefunden = {(st["text"], f["kategorie"]) for f in _funde(text) for st in f["stellen"] if st.get("an", True)}
    assert (wert, soll) in gefunden, gefunden


@pytest.mark.parametrize("text, erwartet", [("(wie im Ausweis)", True), ("(TT MM JJJJ)", True), ("|Druckbuchstaben|", True),
                                            ("Hausnummer", False), ("Datum im Format TTMMJJJJ", False)])
def test_a6_07_hinweis_in_klammern_kein_feldname(text, erwartet):
    from anonymisierer.detektoren import kammfelder
    assert (kammfelder._KLAMMER_HINWEIS_RE.fullmatch(text) is not None) is erwartet


def test_ab6u_07_titel_vor_platzhalter_viele_anreden_waechst_linear():
    """Anrede oder Titel vor einem Personen-Platzhalter (_titel_vor_platzhalter, neu im Rollenwort-Durchlauf der
    Selbstkontrolle): je Kandidat nur der Platzhalter direkt daneben über den Index der Seitenprüfung, kein Durchlauf
    über alle Platzhalter der Seite. Gemessen wird nur der Aufruf je Kandidat, die Seitenprüfung ist vorab gebildet."""
    from anonymisierer import restrisiko

    def vorbereiten(n):
        # "Herr" hinter "Mitarbeiter" ist ein Rollenwort-Kandidat; der Platzhalter folgt hinter einem Komma
        m = seitenmodell.dokument_aus_text(_zeile("Unser Mitarbeiter Herr, [NAME] meldet sich. ", n)).seiten[0]
        p = restrisiko._Seitenpruefung(m, restrisiko._Wissen(restrisiko._wissen_laden()))
        return p, personenkontext.personenwort_rollenwort(p.text, p.w.modul)

    def lauf(pk):
        p, kandidaten = pk
        return [p._titel_vor_platzhalter(s, e) for s, e in kandidaten]
    klein, gross = vorbereiten(8000), vorbereiten(64000)
    assert klein[1] and all(lauf(klein))
    wachstum, _, zeit = _wachstum(lambda: lauf(klein), lambda: lauf(gross), 8, 2.0)
    assert wachstum < 2.0, f"_titel_vor_platzhalter wächst um {wachstum:.2f} x linear ({zeit:.3f} s)"


# ----------------------------------------------------------------------
# Abnahme 5 AB5U-03 (Kamm-Probe k04): eine Lage im Haus mit Nummer als ganzer Wert hinter einem Anschrift-Feldnamen ist
# keine Straße ("Lage der Wohnung ⇥ Etage 3"); mit Straße oder PLZ im Wert und echte Straßennamen bleiben Anschrift
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert, soll", [
    ("Lage der Wohnung\tEtage 3", "Etage 3", "frei"),
    ("Lage der Wohnung: Etage 3", "Etage 3", "frei"),
    ("Lage der Wohnung\tZimmer 4", "Zimmer 4", "gemeldet"),     # die Selbstkontrolle meldet die Angabe
    ("Anschrift: 3. OG", "3. OG", "frei"),
    ("Lage der Wohnung: Etage 3, Zimmer 4", "Etage 3", "frei"),
    ("Anschrift: 3. OG links", "3. OG links", "frei"),
    ("Anschrift: Mitte 3", "Mitte 3", "weg"),
    ("Wohnung: Whg. 12", "Whg. 12", "gemeldet"),
    ("Anschrift: Zimmermann 4", "Zimmermann 4", "weg"),
    ("Anschrift: Etagenweg 3", "Etagenweg 3", "weg"),
    ("Anschrift: Raumer Str. 4", "Raumer Str. 4", "weg"),
    ("Anschrift: Etage 3, Hauptstraße 5, 83022 Rosenheim", "Hauptstraße 5", "weg"),
    ("Anschrift: Etage 3, Hauptstraße 5, 83022 Rosenheim", "83022", "weg"),
])
def test_ab5u_03_lage_im_haus_keine_strasse(text, wert, soll):
    assert _zustand(text, wert) == soll


# ----------------------------------------------------------------------
# Abnahme 6 A6-13 (Reste von A5-06 und A5-10, auf allen Ständen lesbar): eine Brandmeldeanlage ist ein Feueralarm, ihr
# Code mit Bedienung oder "nur für" eine Person wird geschwärzt, sonst gemeldet; der Code eines Schranks mit Artikel
# in Klammern dahinter wird gemeldet (Produkt- oder Schlosscode)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert, soll", [
    ("Brandmeldeanlagecode 6881 (nur für den Hausmeister)", "6881", "weg"),
    ("Brandmeldeanlagencode 6881 nur für den Hausmeister", "6881", "weg"),
    ("Brandmeldeanlagecode: 6881", "6881", "gemeldet"),
    ("Brandmeldeanlage, Code 6881", "6881", "gemeldet"),
    ("Brandmeldeanlage-Code 6881 wurde um 14:20 Uhr ausgelöst.", "6881", "frei"),
    ("Die Brandmeldeanlage wurde 2019 erneuert.", "2019", "frei"),
    ("Code für den Spiegelschrank (Artikel 7731): 3074", "3074", "gemeldet"),
    ("Code für den Spiegelschrank (Art. 7731) 3074", "3074", "gemeldet"),
    ("Code für den Spiegelschrank: 3074", "3074", "weg"),
    ("Der Kleiderschrank, Art. 4471, kam beschädigt an.", "4471", "frei"),
])
def test_a6_13_brandmeldeanlage_und_schrank_mit_artikel(text, wert, soll):
    assert _zustand(text, wert) == soll


# ----------------------------------------------------------------------
# Weitere Reste, auf allen Bezugsständen lesbar (Differenzprobe der Abnahme 6): ein Code am Bedienteil mit Bedienung
# im selben Satz (A6-12), eine Rolle hinter "ist seit 2016" (A6-05), "vom Beruf des" (A6-06) – jetzt gemeldet
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, wert, soll", [
    ("Das Bedienteil zeigte Code 0811 an, anschließend ihn am Bedienteil eingeben.", "0811", "gemeldet"),
    ("Das Bedienteil meldet den Code 2796, danach bitte die Anlage scharf schalten.", "2796", "gemeldet"),
    ("Das Bedienteil meldete Code 5859; danach den Hausmeister verständigen.", "5859", "frei"),
    ("Das Display zeigte Code 4021, Ursache Überlast, danach Gerät neu einschalten.", "4021", "frei"),
    ("Die Wallbox zeigt den Code 3017 an.", "3017", "frei"),
    ("Er ist seit 2016 Treuhänder der Seniorengruppe.", "Treuhänder", "gemeldet"),
    ("Er ist seit 2016 Mitglied im Verein.", "Mitglied", "frei"),
    ("Ihr Neffe träumt vom Beruf des Soldaten.", "Soldaten", "gemeldet"),
])
def test_n8_reste_aller_staende_gemeldet(text, wert, soll):
    assert _zustand(text, wert) == soll
