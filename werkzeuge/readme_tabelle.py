#!/usr/bin/env python3
"""Erzeugt die Erkennungstabelle der README aus anonymisierer.muster.KATEGORIEN und muster.PROFILE.

Damit README und Code nicht auseinanderlaufen:
    python werkzeuge/readme_tabelle.py             # Tabelle anzeigen
    python werkzeuge/readme_tabelle.py --schreiben # Tabelle in README.md ersetzen

In der README steht die Tabelle zwischen den Markierungen
<!-- TABELLE-ANFANG --> und <!-- TABELLE-ENDE -->. Die Spalte „Angehakt ab Stufe“ kommt aus den Schutzstufen
(muster.PROFILE), Beispiele und Hinweise aus BEISPIELE und ERLAEUTERUNG unten. tests/test_auslieferung.py prüft,
dass die README-Tabelle genau dieser Ausgabe entspricht und dass jedes Beispiel von seiner Kategorie erkannt wird.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROGRAMM_ORDNER = Path(__file__).resolve().parent.parent
if str(PROGRAMM_ORDNER) not in sys.path:
    sys.path.insert(0, str(PROGRAMM_ORDNER))

README = PROGRAMM_ORDNER / "README.md"
ANFANG = "<!-- TABELLE-ANFANG -->"
ENDE = "<!-- TABELLE-ENDE -->"

# Beispiele je Kategorie-Schlüssel (für Kategorien ohne Eintrag erscheint "–"). Jedes Beispiel muss die Erkennung
# seiner Kategorie finden (tests/test_auslieferung.py); Personennamen erkennt das Sprachmodell (tests/test_namen.py).
BEISPIELE = {
    "namen": "Max Mustermann",
    "iban": "DE89 3704 0044 0532 0130 00",
    "email": "max.mustermann@example.de",
    "telefon": "0171 2345678",
    "geburt": "geb. am 02.09.1983",
    "strasse": "Hauptstraße 12a",
    "plzort": "90402 Nürnberg",
    "vertrag": "Versicherungsschein-Nr. LV-2024-887766",
    "svnr": "12 345678 A 123",
    "steuerid": "91064389278",
    "steuernr": "Steuernummer: 181/815/08155",
    "kvnr": "A123456780",
    "kindergeld": "009FK407160",
    "kfz": "N-XY 123",
    "fin": "WVWZZZ1JZXW000001",
    "ausweis": "Ausweisnummer: L01X00T47",
    "mandat": "Mandatsreferenz MR-2024-0815",
    "bic": "COBADEFFXXX",
    "kreditkarte": "4111 1111 1111 1111",
    "ip": "IP-Adresse: 84.123.45.67",
    "zugangsdaten": "Benutzername: maxmuster82",
    "profilname": "Instagram @max.muster",
    "standort": "GPS: 48.13715, 11.57612",
    "international": "Kerkstraat 12, 1017 GC Amsterdam",
    "ort": "Musterstadt, 03.04.2025",
    "beruf": "Beruf: Elektriker",
    "arbeitgeber": "Arbeitgeber: Muster Bau GmbH",
    "diagnose": "Diagnose: Diabetes mellitus (E11.9)",
    "medikament": "Medikation: Metformin 500 mg",
    "religion": "Konfession: römisch-katholisch",
    "datum": "15.03.2024",
}
ERLAEUTERUNG = {
    "namen": "KI-Modell (spaCy), Namenslisten und Regeln; gleiche Person = gleicher Platzhalter im Dokument – auch "
             "für den Geburtsnamen hinter „geb.“/„geborene“ („Anna Weber geb. Schulz“)",
    "iban": "auch mit falscher Prüfziffer, wenn sie eindeutig wie eine IBAN aussieht (Hinweis „Lesefehler?“)",
    "email": "auch verschleiert („name (at) web (punkt) de“, „name [at] gmx [dot] de“)",
    "geburt": "hinter „geb.“, „Geburtsdatum“, „Geburt des Kindes am“ … oder hinter einem Namen mit Komma, Stern "
              "oder Klammer („Max Mustermann, 02.09.1983“) – bei Kindern und Mitversicherten („Kind 2: Lea Brandl, "
              "30.06.2018“) in jedem Alter; in „Maximal“ zusätzlich Daten wie „02.09.1983“, die mindestens 14 Jahre "
              "zurückliegen – außer kurz hinter Wörtern wie „am“, „vom“, „seit“ oder „Beginn“",
    "vertrag": "Nummer hinter einem Etikett wie „Vertrags-Nr.“ oder in einer Tabellenspalte mit solchem Kopf – auch "
               "hinter Zwischenwörtern („Personalnummer beim Arbeitgeber: 4711“), mit Tausenderpunkten („Kundennummer: "
               "4.711.208“, „7.712.345“ unter „Vertrag“) oder als Code („Geräte-ID: TLX-KQ8B-ZR3M“); auch eVB-Nummer "
               "(elektronische Versicherungsbestätigung) und Transferticket der Kfz-Versicherung; ohne Etikett "
               "MAC-Adresse, EID einer eSIM, Nummer im Marktstammdatenregister, Aktenzeichen eines Gerichts („3 C "
               "456/24“), Flurstück und Grundbuchblatt; nicht Gebühren- und Katalogziffern (GOZ, GOÄ, PZN), "
               "Fahrzeugschlüssel (HSN/TSN) und Paragrafen („§ 34d GewO“)",
    "steuerid": "ohne Beschriftung nur mit gültiger Prüfziffer, auch gruppiert („30 268 175 922“)",
    "steuernr": "ohne Etikett nur mit Schrägstrichen; USt-IdNr. nur mit Etikett und nicht die einer Firma (die von "
                "Einzelkaufleuten, Inhabern und Freiberuflern schon)",
    "ausweis": "mit Etikett; Ausweis- und Passnummern auch ohne Etikett, wenn die Prüfziffer stimmt; auf "
               "Ausweiskopien auch die maschinenlesbare Zone",
    "mandat": "nur hinter einem Etikett",
    "bic": "hinter „BIC“, neben einer IBAN oder in eindeutiger Form (11 Zeichen auf „XXX“ oder mit Ziffer im Ortscode)",
    "kreditkarte": "auch die Kartenprüfnummer (CVC/CVV, „Kartenprüfnr.“, „CID“) hinter ihrem Etikett und in "
                   "Kartendaten („…, gültig bis 12/27, 739“) – nur dort, nicht dieselben Ziffern an anderer Stelle; "
                   "„Prüfnummer“ allein nur neben einer Kartenangabe (keine TÜV- oder Gutachten-Prüfnummer)",
    "kfz": "nur mit amtlichem Unterscheidungszeichen (nicht Modellcodes wie „KTM RC 390“), auch „RO - KL 2207“ und "
           "klein geschrieben; hinter einem Kfz-Etikett („Versicherungskennzeichen:“, „Kurzzeitkennzeichen“, "
           "„Versicherungsplakette Nr.“) auch Versicherungs-, Kurzzeit-, rote und Ausfuhrkennzeichen („435 GHT“, "
           "„RO-04 1287“) und ausländische Kennzeichen",
    "ip": "IPv4 mit gültigen Oktetten (ohne Etikett nur mit IP-Bezug in der Zeile oder in der Kopfzeile einer "
          "E-Mail „Received: from …“; direkt hinter einem Versionswort wie „Version 10.0.19045.1234“ nie) und IPv6",
    "zugangsdaten": "Benutzername/-kennung, Kennwort, PIN, Geheimzahl, Aktivierungs-, Freischalt-, Zahlen- und "
                    "Entsperrcode hinter ihrem Etikett (auch „WPA2-Kennwort“, „Kennwort für das Portal: …“, als "
                    "Spaltenkopf „PIN“); ein Zugangscode aus Ziffern hinter „Code“ mit einem Schloss davor, im Satz "
                    "oder dahinter („Haustür: Code 1357“, „(Haustür) Code 1357“, „Die Garage hat den Code 1199.“, "
                    "„Code 4455 für die Tiefgarage“, „schaltet man mit 6482 aus“, „Das Hoftor geht mit 2601 auf.“) – "
                    "auch hinter Gebäuden und Behältern mit Schloss („Gartenhaus: Code 9090“, „Geräteschuppen – Code "
                    "3016“, Scheune, Stall, Carport, Wallbox, Spind); ohne sicheres Schloss meldet die Selbstkontrolle "
                    "die Ziffern („Waschküche: Code 6161“, „Code lautet 5656.“, „Bitte im Keller nachsehen.⏎Code "
                    "9595“) – nicht „Passwort vergessen?“, "
                    "„PIN: siehe separates Schreiben“, Fehler- und Anzeigecodes von Geräten („Der Motor meldet den "
                    "Code P0300“, „Das Garagentor zeigte den Code 3017“) oder Tarif- und Rabattcodes",
    "profilname": "@-Namen, Nutzer- und Profilnamen hinter Plattform-Etiketten („eBay-Name:“, „Telegram:“), der "
                  "Pfad eines Profil-Links („facebook.com/vorname.nachname“) und Kunden-, Vertrags- und Namensangaben "
                  "in Links („?kdnr=4711081&name=…“) – nicht die Seite einer Firma",
    "standort": "Koordinaten als Dezimalgrad-Paar, in Grad/Minuten/Sekunden und als Einzelwert hinter „Breite“/"
                "„Länge“ (ohne Maßeinheit dahinter)",
    "international": "auch Straßen mit vorangestelltem Straßentyp („Str. Memorandumului nr. 27“, „Calea …“), "
                     "vierstellige PLZ mit Ort hinter einer Straße oder mit Länderhinweis („8002 Zürich“), "
                     "sechsstellige PLZ mit Länderhinweis und ausländische Kennzeichen im Satz mit Länderhinweis",
    "ort": "Ort-Datum-Zeile, „geboren in …“, „wohnhaft in …“",
    "beruf": "hinter „Beruf:“, im Satz („arbeitet als …“, „ist als … tätig“, „verdient ihr Geld als …“, „übt den "
             "Beruf der … aus“, auch gebeugt „des Schreiners“, „seit sie Lehrerin ist“, „Ihr Mann, der Polizist ist, "
             "…“, Tätigkeiten wie „arbeitet als Putzfrau“), in der Spalte „Beruf“/„Tätigkeit“ einer Personenliste, im "
             "Beruf-Feld eines Kastenformulars (Wert unter dem Feldbezeichner, auch unter „Beruf des Ehepartners“) "
             "und auf Scans rechts neben dem Feldnamen „Beruf“ – nicht die Rolle des Maklers, einer Firma oder eines "
             "Vereins („Wir sind als Versicherungsmakler für Sie tätig“), Vertretungs- und Ehrenämter („als Betreuer "
             "seiner Mutter“, „ehrenamtlich als Trainer“) und Ausfüllhinweise („bitte genau angeben“)",
    "arbeitgeber": "hinter „Arbeitgeber:“ oder im Satz; bekannte Versicherer, Banken und Behörden bleiben stehen",
    "diagnose": "nur bekannte Begriffe und ICD-Codes mit Gesundheitsbezug; in „Ausgewogen“ und „Hoch“ nur angeboten "
                "(⚕, nicht angehakt)",
    "medikament": "nur bekannte Begriffe mit Gesundheitsbezug; in „Ausgewogen“ und „Hoch“ nur angeboten "
                  "(⚕, nicht angehakt)",
    "religion": "Konfession bzw. Kirchensteuermerkmal („rk“, „ev“) hinter ihrem Etikett oder unter einem "
                "Spaltenkopf „Konf.“; besondere Kategorie nach Art. 9 DSGVO – in „Ausgewogen“ und „Hoch“ nur "
                "angeboten (nicht angehakt)",
    "datum": "Vorsicht: auch Vertrags- und Briefdaten",
}
# Schutzstufen von der mildesten zur strengsten (Schlüssel in muster.PROFILE, Name in der Tabelle)
STUFEN = (("ausgewogen", "Ausgewogen"), ("hoch", "Hoch"), ("maximal", "Maximal"))
NUR_VON_HAND = "– (nur von Hand)"


def angehakt_ab(schluessel: str, profile=None) -> str:
    """Mildeste Schutzstufe, die die Kategorie anhakt („Ausgewogen“ = in jeder Stufe), NUR_VON_HAND, wenn keine
    Stufe sie anhakt. Haken die Stufen sie nicht von einer Stufe an aufwärts an: „nur …“ mit den einzelnen Stufen."""
    if profile is None:
        from anonymisierer.muster import PROFILE as profile
    stufen = [name for schluessel_stufe, name in STUFEN if schluessel in profile[schluessel_stufe]["aktive"]]
    if not stufen:
        return NUR_VON_HAND
    namen = [name for _, name in STUFEN]
    if stufen == namen[len(namen) - len(stufen):]:
        return stufen[0]
    return "nur " + ", ".join(stufen)


def tabelle() -> str:
    from anonymisierer.muster import KATEGORIEN, PROFILE

    zeilen = ["| Kategorie | Beispiel | Wird ersetzt durch | Angehakt ab Stufe | Hinweis |",
              "|---|---|---|---|---|"]
    for schluessel, anzeige, platzhalter, _funktion, _an in KATEGORIEN:
        ersatz = platzhalter or "[PERSON A], [PERSON B] …"
        zeilen.append(f"| {anzeige} | {BEISPIELE.get(schluessel, '–')} | `{ersatz}` | "
                      f"{angehakt_ab(schluessel, PROFILE)} | {ERLAEUTERUNG.get(schluessel, '')} |")
    return "\n".join(zeilen)


def readme_aktualisieren(pfad: Path = README) -> bool:
    """Ersetzt die Tabelle zwischen den Markierungen. Rückgabe: wurde etwas geändert?"""
    text = pfad.read_text(encoding="utf-8")
    a, e = text.find(ANFANG), text.find(ENDE)
    if a < 0 or e < 0 or e < a:
        raise SystemExit(f"Markierungen {ANFANG} / {ENDE} fehlen in {pfad}")
    neu = text[:a + len(ANFANG)] + "\n" + tabelle() + "\n" + text[e:]
    if neu == text:
        return False
    pfad.write_text(neu, encoding="utf-8")
    return True


if __name__ == "__main__":
    if "--schreiben" in sys.argv[1:]:
        print("README aktualisiert." if readme_aktualisieren() else "README war schon aktuell.")
    else:
        print(tabelle())
