"""Kennungen mit eigener Wertform hinter ihrem Etikett – eVB-Nummer und Transferticket der Kfz-Versicherung,
Kartenprüfnummer (CVC/CVV) einer Zahlungskarte –, der Geburtsname hinter seinem Feld-Etikett und (seit Runde 5) jede
andere Kennung hinter ihrem Kennungs-Etikett (Abschnitt „Allgemeine Kennungen“ unten).

EINE Regel für die Erkennung (muster.py, namen.py, detektoren/struktur*.py) und die Selbstkontrolle
(restrisiko.py): beide lesen hier dieselben Etiketten, Wertformen und dieselbe Regel „Etikett + Wert“, damit sie
nicht auseinanderlaufen. Die Gegenprüfung der Runde 4 fand in beiden Seiten dieselben Lücken – getrennt gebaut, aber
gleich gedacht (Zwischenwörter nur klein, keine Klammer, kein Zeilenumbruch); gemeinsam gepflegt schließt eine
Korrektur beide.

Regel „Etikett + Wert“ (wert_hinter_etikett):
  * direkt: hinter dem Etikett Trennzeichen (: . = # - – — * | → » > " „ “ ' ‚ ; , _ …), Füllwörter ("lautet",
    "ist", "Nr."), eine kurze Klammer ("(eVB)", "(gültig 6 Monate)") und höchstens ein Zeilenumbruch bzw. eine
    Zellgrenze – dann der Wert; trifft dort die Wertform ein Wort ("EVB-NUMMER ANGEBEN: …", "GEBURTSNAME, FALLS
    ABWEICHEND: …") oder einen Teil des Etiketts ("Geburtsname abweichend: …"), ist es ein Zwischenwort;
  * hinter Zwischenwörtern DESSELBEN Satzes bis zu einer Ankündigung (":", "=", "lautet", "lauten", "lautend auf",
    "ist", "sind") oder einer Zellgrenze: beliebige Wörter, auch groß geschrieben ("Ihres neuen Fahrzeugs"),
    Klammern bis 80 Zeichen ("(Kennzeichen M-AB 123)"), Abkürzungen mit Punkt ("amtl.", "Kfz.", "lt.") und ein
    Zeilenumbruch mitten im Satz. Abbruch am Satzende (Punkt vor einem großen Anfangsbuchstaben, außer hinter einer
    Abkürzung; "!", "?", ";"), an einem anderen Etikett (eines der Kennungs- oder Geburtsnamen-Etiketten hier, oder
    hinter einem Komma ein Feld-Etikett der Wissensbasis mit Doppelpunkt: "…, Ihre Kundennummer: …") und nach
    höchstens MAX_ZWISCHENWOERTER Wörtern;
  * ohne Ankündigung (nur Kennungen) hinter höchstens OHNE_ANKUENDIGUNG Wörtern ohne Ziffer, wenn der Wert in
    derselben Zeile steht und Zeile oder Satz beendet ("Prüfziffer hinten 739") – nicht hinter einem Verweiswort
    ("CVC auf Seite 123", "seit 2015");
  * Geburtsname: steht sein Etikett in der Klammer eines anderen ("Familienname (Geburtsname): Weber (Quarnstedt)"),
    ist der Name in der Klammer des Werts gemeint – derselben Person wie der Wert davor;
  * der Wert hat die Form der Kennung und ist kein Wort (wissen.ist_wortgestalt), kein Datum, kein Betrag, keine
    Einheit (kennungen: Prüfung je Art).

Öffentliche Schnittstelle:
    ETIKETT_RE, GEBURTSNAME_ETIKETT_RE, WERT_RE, NAME_RE
    etikett_art(text)                    Art eines ganzen Etiketts ("evb", "ticket", "cvc", "pruef") oder None
    wert_hinter_etikett(text, pos, wert_re, ...) -> Wertfund | None
    kennungen(text, ...) -> [Kennungsfund]   alle eVB-Nummern, Transfertickets, Kartenprüfnummern hinter Etiketten
    kennungsform(wert)                   hat ein Wert hinter einem dieser Etiketten die allgemeine Form einer Kennung?
    kartenbezug(text, s, e, extra=None)  Kartenangabe oder Kartennummer in der Nähe?
    kartendaten(text)                    Kartenangabe oder Kartennummer mit gültiger Prüfziffer in text?
    etikett_zeile(text, s, e)            Etikettzeile (Doppelpunkt dahinter, höchstens zwei Wörter davor)?
    ist_funktionswort(wort), ist_abkuerzung(wort, danach)
    geburtsname_hinter_etikett(text, m, ...) -> Geburtsnamenfund | None   Name hinter einem Geburtsnamen-Etikett
    weitere_geburtsnamen(text, m, ende, ...) -> [Geburtsnamenfund]      weitere Namen hinter "Geburtsnamen:"
    geburtsname_moeglich(text, s, e), feld_etikett(text, s, e)          Name möglich? / selbst ein Feld-Etikett?
  Allgemeine Kennungen (Runde 5, Domänen-Durchsicht):
    kennungs_etiketten(text, …) -> [Kennungsetikett]   Etiketten der Wissensbasis, Nummern-Wörter ("BG-Nummer",
                                                        "Vorg.-Nr."), "Nummer der/des …", Kürzel vor "Nr." ("HKP Nr.")
    allgemeine_kennung(text, s, e, …) -> Kennungswert | None   Wert hinter einem Kennungs-Etikett (Regel oben, für
                                                        jedes Etikett: Zwischenwörter, Laufnummer, Ergänzung)
    allgemeine_kennungen(text, …) -> [(Kennungsetikett, Kennungswert)]   alle Werte einer Seite (Selbstkontrolle)
    kennungswert(text, pos, grenze, etikett, …)   Wertform hinter dem Etikett (kennung_spanne mit Tausenderpunkt-
                                                        Gruppen, code_spanne, buchungscode, Dokumentnummer)
    kennung_spanne, kennung_token, code_spanne, buchungscode, wert_ausgeschlossen, fahrzeugschluessel,
    nummern_wort, stamm_vor_nr, stamm_der_nummer, ausweis_wort, punkte_erlaubt
    kennungen_ohne_etikett(text) -> [(start, ende, art)]   MAC-Adresse, EID einer eSIM, MaStR-Nummer, Aktenzeichen
                                                        eines Gerichts
    katalognummer(text, s, e)          Pharmazentralnummer (PZN) – keine Telefonnummer, keine Kennung einer Person
    einzelkaufmann_block(text, pos), einzelkaufmann_register(text)   HRA/USt-IdNr. eines Einzelkaufmanns (Person)
    einzelkaufmann_erwaehnt(text)      Vorprüfung: "e.K.", "Inhaber:" im Text
    vorschrift(text, s, e)             Nummer einer Vorschrift ("§ 34d", "8 34d Abs. 1 GewO") – kein Wert
  Kfz, Anschriften und neue Kategorien (Runde 5, Paket K2):
    KFZ_ETIKETT_RE, kfz_etikett(etikett), kfz_wert(text, pos, grenze), KFZ_WERTFORM   Kfz-Etiketten mit Fahrzeugbezug
                                        ("Versicherungskennzeichen", "Kurzzeitkennzeichen") und der Kennzeichen-Wert
    kennzeichen_stellen(text, sperre)  deutsche Kennzeichen ohne Etikett, nur mit amtlichem Unterscheidungszeichen
    kennzeichen_im_satz(text)          ausländische Kennzeichen hinter einem Fahrzeugwort (mit Länderhinweis?)
    unterscheidungszeichen(kuerzel), fahrzeugmarke(wort)
    LAND_RE, STRASSENKLASSE_RE, strassen_vorn, plz6_mit_land, plz4_ausland, ort_at_ch   ausländische Anschriften,
                                        Straßenklassen ("Auf der A 8": keine Anschrift)
    ip_adressen, koordinaten, email_verschleiert, zugangsdaten, profilnamen, grundbuch, religion   (start, ende) der
                                        neuen Kategorien bzw. Formen
"""

from __future__ import annotations

import re
from typing import Callable, NamedTuple

MAX_ZWISCHENWOERTER = 14          # so viele Wörter dürfen zwischen Etikett und Ankündigung stehen
MAX_KLAMMER = 80                  # Klammern bis zu so vielen Zeichen zählen als ein Zwischenwort
OHNE_ANKUENDIGUNG = 3             # so viele Zwischenwörter ohne Ankündigung ("Prüfziffer hinten 739")
_SUCHFENSTER = 400                # so weit hinter dem Etikett wird gesucht (Zeichen; begrenzt die Laufzeit)

# ----------------------------------------------------------------------
# Etiketten
# ----------------------------------------------------------------------
_UE = r"(?:ü|ue|u)"               # Umlaut, wie ihn die OCR liest ("Kartenprufnummer", "Versicherungsbestatigung")
_AE = r"(?:ä|ae|a)"
_M = r"(?:m|rn)"                  # die OCR liest "m" als "rn" ("eVB-Nurnmer", "Geburtsnarne")
_NU = rf"nu{_M}{_M}[ec]r"         # "Nummer", OCR auch "Nurnmer", "Nummcr" ("e" als "c" gelesen)
_NUMMER = rf"(?:nr\.?|{_NU}[n]?|no\.?)"
# eVB-Nummer: "eVB", "e-VB", "eV8" (OCR), "VB-Nr."/"VB-Nummer" (nicht "VB" allein: Verhandlungsbasis),
# "(elektronische) Versicherungsbestätigung(en/s)", mit Nummer-Zusatz in Einzahl und Mehrzahl ("eVB-Nummern") und in
# einer Betreffzeile als Anfrage oder Mitteilung ("AW: eVB-Anfrage – K7H3M9P"; nicht "eVB-Hotline"); nicht "EVB-IT"
# (Vertragsbedingungen der IT-Beschaffung)
_EVB = (rf"(?:(?i:e-?v[b8])|VB(?=[ \t]*[-.]?[ \t]*(?i:nr\b|{_NU}|no\b))"
        rf"|(?i:(?:elektronische[nrs]?[ \t]+)?versicherungsbest{_AE}tigung)(?i:en|s)?)"
        rf"(?:[ \t]*[-.]?[ \t]*(?i:{_NUMMER}|code))?"
        r"(?:-(?:Anfrage|Anforderung|Bestätigung|Mitteilung|Zuteilung|Erteilung|Daten))?(?!-[A-Za-zÄÖÜäöü])")
# Transferticket (Wechsel des Kfz-Versicherers): auch "Transfer-Ticket", "SF-Transferticket", Mehrzahl – nicht als
# Bestimmungswort einer fremden Zusammensetzung ("Transferticket-Verfahren", "eVB-Hotline")
_TICKET = (rf"(?:[A-Za-z]{{1,4}}-)?(?i:transfer[ \t]?-?[ \t]?tickets?)(?:[ \t]*[-.]?[ \t]*(?i:{_NUMMER}|code|id))?"
           r"(?!-[A-Za-zÄÖÜäöü])")
# Kartenprüfnummer, eindeutig: CVC/CVV (auch "C.V.C.", "CVC 2"), CAV (JCB), Zusammensetzungen mit "Karte(n)"
# ("Kartenprüfnr.", "Kreditkarten-Prüfnummer", "Kartensicherheitscode", "Kartenverifikationsnummer"), englisch "Card
# Verification Code", "Prüfnummer der Karte" / "Sicherheitscode (der Kreditkarte)"; hinter CAV stehen drei Ziffern
_KARTE_VOR = r"(?:kredit|debit|zahlungs|bank|giro|ec)?-?karten-?"
_PRUEF_WORT = (rf"(?:pr{_UE}f(?:{_NU}|nr\.?|ziffer|zahl|code|z\.)|sicherheits-?(?:code|{_NU}|ziffer|zahl)"
               rf"|kontroll-?(?:ziffer|{_NU}|zahl|code)|verifi(?:zierungs|kations)(?:{_NU}|code))")
_CVC = (r"(?:(?i:c\.?v\.?[cv]\.?)(?:[ \t]?2(?![\d]))?|CAV2?|CSC"
        rf"|(?i:{_KARTE_VOR}(?:pr{_UE}f|verifi(?:zierungs|kations)|sicherheits)-?(?:{_NU}|nr\.?|ziffer|zahl"
        r"|code|wert))"
        r"|(?i:card[ \t]+(?:verification|security)[ \t]+(?:code|value|number))"
        rf"|(?i:{_PRUEF_WORT}|security[ \t]+code)[ \t]*\(?[ \t]*(?i:der|ihrer|meiner|ihre|of[ \t]+the)[ \t]+"
        r"(?i:(?:kredit|debit|bank|zahlungs|giro|ec)-?)?(?i:karte|card)[ \t]*\)?)"
        r"(?:[ \t]*/[ \t]*(?i:cvc|cvv)2?)?"
        rf"(?:[ \t]*-?[ \t]*(?i:code|{_NU}|nr\.?|pr{_UE}fnummer|pr{_UE}fziffer|pr{_UE}fcode|wert|zahl))?")
# Kartenprüfnummer nur mit Kartenangabe in der Nähe: "Prüfnummer", "Prüfnr.", "Sicherheitscode", "Security Code",
# "CID" (American Express), "CVN", "CV2" – und "CVC", wie die Texterkennung es auch liest ("CVG", "CV C")
_PRUEF = rf"(?<!-)(?:(?i:{_PRUEF_WORT}|security[ \t]+code|cvn|cv2|cid)|KPN|CVG|CV[ ][CV])(?!-[A-Za-zÄÖÜäöü])"
ETIKETT_RE = re.compile(
    r"(?<![\wäöüß])(?:"
    rf"(?P<evb>{_EVB})|(?P<ticket>{_TICKET})|(?P<cvc>{_CVC})|(?P<pruef>{_PRUEF})"
    r")(?![\wäöüß])")
# Geburtsname als Feld-Etikett: "Geburtsname(n)", "Mädchenname(n)", "Name vor der Ehe", "Familienname vor der
# Eheschließung", "Geb.-Name", "Geb.Name", "Geb. Name", "GEB.-NAME", "Geburtsn.", wie die Texterkennung es liest
# ("Geburtsnarne", "Gcburtsname", "Geburlsname", "Geburtsnamc"); die Kurzformen nur als Feld (Doppelpunkt, Zellgrenze,
# Klammer oder Zeilenende dahinter, oder ein Leerzeichen vor einem Namen: "Geb.-Name Quarnstedt"), nicht im Satz
_E = r"[ec]"                      # die OCR liest "e" als "c" ("Gcburtsname", "Geburtsnamc", "eVB-Nummcr")
GEBURTSNAME_ETIKETT_RE = re.compile(
    rf"(?<![\wäöüß.\-])(?:(?i:(?:g{_E}bur[tl]s|m{_AE}dchen)na{_M}{_E}n?"
    r"|(?:familien|nach)?name[ \t]+vor[ \t]+der[ \t]+(?:ehe(?:schlie(?:ß|ss)ung)?|heirat))"
    rf"|(?i:geb\.?[ \t]?-?[ \t]?na{_M}e|geburtsn\.)(?=[ \t]*(?::|\t\t|\(|\n|$)|[ ][A-ZÄÖÜ][a-zäöüß]))"
    r"(?![\wäöüß])")
# "geb.", wie die Texterkennung es liest ("gab.", "gcb.", "qeb."): nur zwischen zwei Namen ein Geburtsnamen-Etikett
# (namen.geburtsnamen, restrisiko) – "gab." ist auch ein Wort ("… die ihm Frau Weber gab. Müller kam später")
GEB_VERLESEN = r"gab|GAB|gcb|qeb|qcb|qab"
# Etikett in der Mehrzahl: dahinter auch mehrere Namen ("Geburtsnamen: Quarnstedt, Ellerbrok")
_GEBURTSNAMEN_MEHRZAHL_RE = re.compile(rf"(?i:(?:g{_E}bur[tl]s|m{_AE}dchen)na{_M}{_E}n)")

# Wertformen: eVB 7 Zeichen aus Großbuchstaben und Ziffern (O/0 und I/1 gehören dazu: die OCR-Lesart hat dieselbe
# Form); Transferticket 8 bis 20 Buchstaben/Ziffern, auch in Gruppen; Kartenprüfnummer 3 oder 4 Ziffern – auch
# als Kammfeld mit einer Ziffer je Kästchen ("7 3 9", "7 | 3 | 9", untereinander)
_KAMM_TRENNER = r"(?:[ ]{1,3}|[ \t]*[|\n][ \t]*|\t\t|\][ ]?\[)"
_KAMM_TRENNER_ZEILE = r"(?:[ ]{1,3}|[ \t]*\|[ \t]*|\t\t)"      # Kammfeld in einer Zeile (eVB: 7 Kästchen nebeneinander)
WERT_RE = {
    "evb": re.compile(rf"(?<![\w\-/.])(?:[A-Z0-9]{{7}}|[A-Z0-9](?:{_KAMM_TRENNER_ZEILE}[A-Z0-9]){{6}})"
                      r"(?![\w]|[-/.][A-Za-z0-9])"),
    "ticket": re.compile(r"(?<![\w\-/.])[A-Za-z0-9](?:[A-Za-z0-9]|[-/.](?=[A-Za-z0-9])){7,25}"
                         r"(?![\w]|[-/.][A-Za-z0-9])"),
    "cvc": re.compile(rf"(?<![\d.,/\-])(?:\d{{3,4}}|\[?\d(?:{_KAMM_TRENNER}\d){{2,3}}\]?)(?![\d]|[-.,:/]\d)"),
}
WERT_RE["pruef"] = WERT_RE["cvc"]
# eVB, wie die OCR sie mit eingefügten Zeichen liest ("K7/H3MY9P", "/RT4ZU9", "K7H3MJ9P"): 6 bis 9 Buchstaben/Ziffern
EVB_RAUSCH_RE = re.compile(r"(?<![\w\-/.])[/|]?[A-Z0-9](?:[A-Z0-9]|[/|](?=[A-Z0-9])){4,9}(?![\w]|[-/.][A-Za-z0-9])")
# Name hinter einem Geburtsnamen-Etikett: großer Anfangsbuchstabe, Bindestrich-Teile, Apostroph ("O'Neill",
# "d'Alessandro"), davor höchstens zwei Partikel ("von der Quarnstedt")
_GROSS = "A-ZÄÖÜÀ-ÖØ-ÞĀĂĄĆČĎĐĒĖĘĚĞĢĪĮİĶĹĻĽŁŃŅŇŌŐŒŔŘŚŞŠŢŤŪŮŰŲŹŻŽȘȚ"
_PARTIKEL_WORT = (r"(?:von|van|de|der|den|zu|zur|vom|ten|ter|da|di|dos|das|del|della|du|la|le|al|el|"
                  r"VON|VAN|DE|DER|DEN|ZU|ZUR|VOM|DA|DI|DOS|DEL|DU|LA|LE|AL|EL)")
NAME_RE = re.compile(r"(?:" + _PARTIKEL_WORT + r"[ ]+){0,2}(?:[dDlL]['’])?[" + _GROSS + r"][\wäöüß'’]+(?:-["
                     + _GROSS + r"][\wäöüß'’]+)*(?![\wäöüß'’\-])")

_ART_ZU_FORM = {"evb": "evb", "ticket": "ticket", "cvc": "cvc", "pruef": "cvc"}


def etikett_art(text: str) -> str | None:
    """Art eines ganzen Etiketts ("eVB-Nr.", "Transferticket", "CVC", "Prüfnr.": "evb", "ticket", "cvc", "pruef")
    oder None. "pruef" ("Prüfnummer", "Sicherheitscode", "CID" …) ist nur mit einer Kartenangabe in der Nähe eine
    Kartenprüfnummer."""
    t = (text or "").strip().rstrip(":").strip()
    m = ETIKETT_RE.fullmatch(t) if t else None
    return m.lastgroup if m else None


def wissen_etikett(phrase: str) -> bool:
    """Ist die Phrase ein Feld-Etikett der Wissensbasis (Person, Kennung, Anschrift, Kontakt, Geburt, Vertragsdaten)?
    Ohne Wissensbasis: nein."""
    try:
        from . import wissen
        for art in wissen.ETIKETTEN_ARTEN:
            index = wissen.index(f"etiketten_{art}")
            if index.eintrag_fuer(phrase) is not None or index.eintrag_fuer(phrase.rstrip(".:")) is not None:
                return True
    except Exception:  # pragma: no cover - Wissensbasis fehlt
        return False
    return False


# ----------------------------------------------------------------------
# Satz und Wörter
# ----------------------------------------------------------------------
# Funktionswörter: nie ein Name hinter "geb." ("geb. In Köln", "GEB. IN KÖLN", "geb. Laut Urkunde") und kein Bezug
# einer Prüfnummer auf etwas anderes ("Ihre Prüfnummer")
FUNKTIONSWOERTER = frozenset("""
in im am an auf aus bei mit nach laut lt vom zum zur für fuer gegen durch ohne über ueber unter vor hinter neben
zwischen seit bis ab als wie und oder sowie bzw sie er es wir ihr ihre ihrer ihres ihren ihrem ihnen uns unser
unsere die der das den dem des ein eine einer eines einem einen erste erster ersten zweite zweiter dritte neue neuer
neu alt alte bitte hier dort siehe nicht kein keine keiner noch schon ja nein auch nur sehr so dann falls wenn
sofern ggf jeweils
""".split())
# Spaltenköpfe, Feld-Etiketten und Sachwörter, die hinter einem leeren Feld "Geburtsname" oder in der Nachbarzelle eines
# Tabellenkopfs stehen, nie ein Name ("Geburtsname ⇥⇥ Status", "Geburtsname:" ⏎ "Typ", "Geb.-Name ⇥⇥ Sport") – auch
# wenn sie zugleich Nachnamen sind ("Grund", "Größe")
_KOPFWOERTER = frozenset("""
status art typ rolle bemerkung bemerkungen hinweis hinweise datum ort nummer nr beginn ende ablauf tarif beitrag
summe betrag anzahl klasse gruppe kategorie sparte produkt wert code kennung stand angaben angabe feld unterschrift
vermerk abschnitt teil seite anlage punkt ziffer größe groesse gewicht grund zweck anlass sport sportart hobby hobbys
freizeit agentur geschäftsstelle geschaeftsstelle raucher nichtraucher kasse krankenkasse beruf tätigkeit
taetigkeit branche einkommen gehalt familienstand geschlecht anrede sprache muttersprache religion konfession
nationalität nationalitaet staatsangehörigkeit staatsangehoerigkeit land kreis bundesland ortsteil zusatz
vorerkrankungen erkrankungen diagnose diagnosen medikamente allergien behinderung pflegegrad kinder eltern
haarfarbe augenfarbe statur kfz pkw fahrzeug kennzeichen fahrerlaubnis führerschein fuehrerschein
""".casefold().split())
# Kopf eines zusammengesetzten Feld-Etiketts oder Sachworts – kein Nachname endet so ("Künstlername", "Ordensname",
# "Geburtsland", "Doktorgrad", "Adresszusatz", "Vorerkrankungen", "Haarfarbe", "Schuhgröße", "Hauptversicherter")
_SACH_KOPF_RE = re.compile(
    r"(?i)^(?:[a-zäöüß]{3,}(?:name|namen|grad|titel|zusatz|zahl|datum|nummer|angabe|angaben|farbe|größe|groesse"
    r"|gewicht|erkrankung|erkrankungen|krankheit|krankheiten|beschwerden|versicherte|versicherter|versicherten|status"
    r"|nehmer|nehmerin|berechtigte|berechtigter)"
    r"|[a-zäöüß]*(?:geburts|herkunfts|heimat|bundes|wohn|abstammungs|einsatz)(?:land|ort|staat))$")


def etikettwort(wort: str) -> bool:
    """Ist das Wort ein Spaltenkopf oder zusammengesetztes Feld-Etikett (_KOPFWOERTER, _SACH_KOPF_RE: "Sport",
    "Agentur", "Künstlername", "Geburtsland") – kein Name, wenn es nicht als Nachname bekannt ist (Prüfung beim
    Aufrufer)?"""
    w = (wort or "").strip(".,;:()")
    return bool(w) and (w.casefold() in _KOPFWOERTER or bool(_SACH_KOPF_RE.match(w)))


def sachwort(wort: str) -> bool:
    """Ist das Wort ein Feld-Etikett oder Sachwort statt eines Namens – Spaltenkopf (_KOPFWOERTER), zusammengesetztes
    Etikett (_SACH_KOPF_RE) oder Sachwort der Namensprüfung (namen: "Pflichtangabe", "Folgendes", "Beruf",
    "Abweichender")?"""
    w = (wort or "").strip(".,;:()")
    if not w:
        return False
    if w.casefold() in _KOPFWOERTER or _SACH_KOPF_RE.match(w):
        return True
    if herkunftsname(w):
        return False                                    # "Landauer" endet auf "-dauer", ist aber ein Herkunftsname
    try:
        from .namen import _ist_sachwort
        return bool(_ist_sachwort(_titelform(w)))
    except Exception:  # pragma: no cover - Namensmodul nicht ladbar
        return False


def mehrdeutiger_geburtsname(wort: str, frage=None) -> bool:
    """Bezeichnet der Geburtsname auch etwas anderes – einen Ort ("Linz", "Polen"), eine Herkunft ("Mainzer Straße"),
    ein gewöhnliches Wort (mehrdeutiger Nachname "Deutsch", Allerweltswort) oder ein Feld-Etikett? Dann wird er nur an
    seiner Stelle und in Personenkontext geschwärzt, nicht im übrigen Text ("Korrespondenzsprache: Deutsch")."""
    frage = frage or _wissen_frage
    k = _titelform((wort or "").strip(".,;:()"))
    if not k or len(k.split()) != 1:
        return False
    return bool(frage("ist_ort", k) or herkunftsname(k, frage) or frage("ist_mehrdeutig", k)
                or frage("ist_allerweltswort", k) or etikettwort(k))


def herkunftsname(wort: str, frage=None) -> bool:
    """Ist das Wort die Einwohnerbezeichnung eines Orts ("Mainzer", "Danziger", "Landauer", "Pariser") – als Name ein
    Herkunftsname?"""
    k = _titelform((wort or "").strip(".,;:()"))
    if not k.endswith("er") or len(k) < 6:
        return False
    frage = frage or _wissen_frage
    return bool(frage("ist_ort", k[:-2]) or frage("ist_nachname", k[:-2]))
# Abkürzungen mit Punkt, hinter denen ein Satz weitergeht ("amtl. Kennzeichen", "Kfz. M-AB 123", "lt. Ausweis",
# "Kennz. M-AB 123", "Fa. Humbaur", "auf der Rücks. ist …")
_ABKUERZUNGEN = frozenset("""
amtl kfz fzg gem lt nr bzw ggf evtl inkl zzgl ca vgl sog usw etc abs art str tel hr fr frl dr prof st vers kd geb
ff bd jg lfd max min mind zul pkw lkw ust mwst ziff verw verh gesch eingetr reg ref betr bzgl abt kennz fa fam gebr
inh kto rücks ruecks ehem stellv stv zt ges allg pers priv dipl ing spez vorm ehel led verst
""".split())


def ist_funktionswort(wort: str) -> bool:
    return (wort or "").strip(".,;:()").casefold() in FUNKTIONSWOERTER


def ist_abkuerzung(wort: str, danach: str = "") -> bool:
    """Ist `wort` (ohne seinen Punkt) eine Abkürzung, hinter der der Satz weitergeht? Bekannte Abkürzungen, Wörter mit
    Punkt im Inneren ("z.B", "u.a"), klein geschriebene Kürzel bis vier Buchstaben ("gem", "bzgl"), und jedes Wort bis
    drei Buchstaben, hinter dem klein oder mit einer Ziffer weitergeschrieben wird."""
    w = (wort or "").strip("(\"'„“")
    k = w.casefold()
    if k in _ABKUERZUNGEN or "." in w or k.rsplit("-", 1)[-1] in _ABKUERZUNGEN:
        return True                                     # auch "Fahrzeug-Ident-Nr.", "Vers.-Nr."
    if w.isalpha() and w.islower() and len(w) <= 4:
        return True
    naechstes = danach.lstrip(" \t")[:1]
    return len(w) <= 3 and w.isalpha() and bool(naechstes) and (naechstes.islower() or naechstes.isdigit())


# Wörter, hinter denen eine Zahl ein Verweis ist, kein Wert ("CVC auf Seite 123", "Prüfziffer in Anlage 2")
_VERWEISWOERTER = frozenset("""
seite seiten s anlage anlagen kapitel abschnitt absatz abs punkt ziffer ziff tel telefon fax zimmer raum filiale
version vers jahr jahre ab seit bis vom von am
""".split())
_FUELLWORT_RE = re.compile(r"(?i:lautet|lauten|lautend(?:[ \t]+auf)?|ist|sind|nr\.?|nummer|no\.?)(?![\wäöüß])")
_ANKUENDIGUNG_RE = re.compile(r"(?i:lautet|lauten|lautend(?:[ \t]+auf)?|ist|sind|heißt|heisst|lautete)(?![\wäöüß])")
# Ankündigung einer Kennung mitten im Satz: das Nummer-Wort ("hat die Nummer K7H3M9P", "trägt die Nr. …", "unter der
# Kennung …") – und, schwächer, eine Präposition direkt vor dem Wert ("unter K7H3M9P erstellt", "mit K7H3M9P"): dort
# zählt nur ein Wert aus Buchstaben UND Ziffern (nicht "unter 0800123")
_ANKUENDIGUNG_KENNUNG_RE = re.compile(
    r"(?:(?i:lautet|lauten|lautend(?:[ \t]+auf)?|ist|sind|heißt|heisst|lautete)"
    r"|Nummer|Nr\.|NUMMER|NR\.|Kennung|KENNUNG|Code|CODE|ID)(?![\wäöüß])")
_SCHWACHE_ANKUENDIGUNG_RE = re.compile(r"(?i:unter|mit)(?![\wäöüß])")
# Füllung in einer Klammer vor dem Wert: "(Nr. K7H3M9P)", "(Nummer: K7H3M9P)", "(ID TT0815AB4711)"
_KLAMMER_FUELLUNG_RE = re.compile(r"\([ \t]*(?i:nr\.?|nummer|no\.?|id|code)[ \t]*[:.#]?[ \t]*")
_TRENNER = frozenset(" \t:.=#-–—*|→»>\"„“”'‚‘’;,_…)•·▪◦‣")
# Aufzählungszeichen am Anfang einer Zeile ("•", "-", "1.", "2)", "a)")
_LISTENZEICHEN_RE = re.compile(r"(?:[•·▪◦‣*–—-]|\d{1,2}[.)]|[a-z][.)])[ \t]+")
_KURZE_KLAMMER_RE = re.compile(r"\([^()\n]{1,30}\)")
_KLAMMER_RE = re.compile(r"\([^()]{1,%d}\)" % MAX_KLAMMER)
_WORT_RE = re.compile(r"[^\s()]+")


class Wertfund(NamedTuple):
    start: int
    ende: int
    darunter: bool          # der Wert beginnt die nächste Zeile, direkt unter einem Etikett am Zeilenende
    zelle: bool             # der Wert steht in der Zelle hinter dem Etikett ("\t\t")
    zwischen: str           # Zwischenwörter ("für die Zulassung Ihres Pkw"), sonst ""
    ankuendigung: str       # "" (direkt), ":" / "=" / "zelle" oder das Ankündigungswort ("lautet", "ist")


def _fuellung(text: str, i: int, grenze: int, wert_re: re.Pattern):
    """(Ende der direkten Füllung ab i, Zeilenumbruch dabei?, Zellgrenze dabei?) – bei einem zweiten Zeilenumbruch
    (None, …). Eine Klammer, die selbst mit dem Wert beginnt ("eVB-Nummer (K7H3M9P)"), ist keine Füllung."""
    umbruch = zelle = False
    while i < grenze:
        c = text[i]
        if c == "\n":
            if umbruch or zelle:
                return None, umbruch, zelle
            umbruch = True
            i += 1
            while i < grenze and text[i] in " \t":
                i += 1
            n = _LISTENZEICHEN_RE.match(text, i, grenze)
            if n is not None:
                i = n.end()                             # "eVB-Nummern:" ⏎ "1. K7H3M9P"
        elif c == "\t" and text.startswith("\t\t", i):
            if umbruch or zelle:
                return None, umbruch, zelle
            zelle = True
            i += 2
        elif c in _TRENNER:
            i += 1
        elif c == "(":
            f = _KLAMMER_FUELLUNG_RE.match(text, i)
            if f is not None and wert_re.match(text, f.end()):
                i = f.end()                             # "(Nr. K7H3M9P)": der Wert steht hinter "Nr." in der Klammer
                break
            k = _KURZE_KLAMMER_RE.match(text, i)
            if k is None or wert_re.match(text, i + 1):
                if wert_re.match(text, i + 1):
                    i += 1                              # "(K7H3M9P)": der Wert steht in der Klammer
                break
            i = k.end()
        else:
            m = _FUELLWORT_RE.match(text, i)
            if m is None:
                break
            i = m.end()
    return i, umbruch, zelle


def _satzende(text: str, wort_start: int, wort_ende: int) -> bool:
    """Endet mit dem Wort text[wort_start:wort_ende] der Satz ("hinterlegt." vor "Bitte", "!", "?", ";")?"""
    wort = text[wort_start:wort_ende]
    if wort[-1:] in "!?;":
        return True
    if not wort.endswith("."):
        return False
    kern = wort.rstrip(".")
    if kern.isdigit() and len(kern) <= 2:
        return False                                    # Ordnungszahl ("IdNr. des 2. Kindes", "am 3. Tag")
    danach = text[wort_ende:wort_ende + 40]
    naechstes = danach.lstrip(" \t")[:1]
    if not naechstes or naechstes == "\n":
        return not ist_abkuerzung(kern, "")
    if naechstes.islower() or naechstes.isdigit():
        return False                                    # "vom 12. März", "ca. drei": der Satz geht weiter
    if _CODE_DANACH_RE.match(danach):
        return False                                    # "Kennz. M-AB 123": ein Code beginnt keinen Satz
    return not ist_abkuerzung(kern, danach)


# ein Code aus Großbuchstaben (mit Bindestrich oder Ziffer) – kein Satzanfang ("Kennz. M-AB 123", "FIN WVWZZZ1…")
_CODE_DANACH_RE = re.compile(r"[ \t]*(?=[A-ZÄÖÜ0-9\-]*[\d\-])[A-ZÄÖÜ][A-ZÄÖÜ0-9]*-?[A-ZÄÖÜ0-9]+(?![a-zäöüß])")


def _anderes_etikett(text: str, i: int, nach_komma: bool, ist_etikett) -> bool:
    """Beginnt bei i ein anderes Etikett: eines der Kennungs- oder Geburtsnamen-Etiketten, oder – hinter einem Komma,
    Semikolon oder einer breiten Lücke – ein Feld-Etikett der Wissensbasis mit Doppelpunkt dahinter ("…, Ihre
    Kundennummer: …")?"""
    return _eigenes_etikett(text, i) or _fremdes_feld(text, i, nach_komma, ist_etikett) is not None


def _eigenes_etikett(text: str, i: int) -> bool:
    """Beginnt bei i eines der Kennungs- oder Geburtsnamen-Etiketten dieses Moduls (mit eigenem Wert)?"""
    return bool(ETIKETT_RE.match(text, i) or GEBURTSNAME_ETIKETT_RE.match(text, i))


def _fremdes_feld(text: str, i: int, nach_komma: bool, ist_etikett) -> int | None:
    """Position hinter dem Doppelpunkt, wenn bei i – hinter einem Komma, Semikolon oder Zeilenumbruch – ein
    Feld-Etikett der Wissensbasis mit Doppelpunkt beginnt ("…, Ihre Kundennummer: …", "…, Kennzeichen: …"), sonst
    None."""
    if not nach_komma or ist_etikett is None:
        return None
    m = re.match(r"([^\s:()]{2,40}(?:[ ][^\s:()]{2,40}){0,2})[ \t]*:", text[i:i + 90])
    if m is None:
        return None
    teile = m.group(1).split(" ")
    for k in range(len(teile)):
        try:
            if ist_etikett(" ".join(teile[k:])):
                return i + m.end()
        except Exception:
            return None
    return None


# Gegenstände mit eigenen Nummern oder Codes: steht eines davon direkt vor einem Doppelpunkt hinter einem Kennungs-
# Etikett, gehört der Wert ihm ("Transferticket für Tarif: PREMIUM2024", "Transferticket – Hotline: 0800-…") – ebenso
# ein Kennungs- oder Kontakt-Etikett der Wissensbasis ("Kennzeichen:", "Kundennummer:"); nicht ein Zweck ("für die
# Zulassung: …")
_FREMDE_GEGENSTAENDE = frozenset("""
tarif tarife tarifcode tarifkennung produkt hotline service servicetelefon kundenservice telefon tel fax telefax
durchwahl rückfragen rueckfragen internet online homepage webseite website mail e-mail email portal postfach
kennzeichen kennz typ modell fin laufzeit versicherungsjahr jahr zeitraum beitrag gebühr gebuehr klasse sf-klasse
vertrag police konto iban kundennummer
""".split())


def fremder_gegenstand(wort: str) -> bool:
    """Ist das Wort ein Gegenstand mit eigener Nummer oder eigenem Code ("Tarif", "Hotline", "Kennzeichen", "Laufzeit")
    – dann gehört ein Wert hinter ihm nicht zu einem eVB- oder Transferticket-Etikett davor?"""
    k = (wort or "").strip(".,;:()[]\"'„“").casefold()
    if not k or not wort.strip(".,;:()[]\"'„“")[:1].isupper():
        return False
    if k in _FREMDE_GEGENSTAENDE or k.rsplit("-", 1)[-1] in _FREMDE_GEGENSTAENDE:
        return True
    try:
        from . import wissen
        for art in ("kennung", "kontakt"):
            if wissen.index(f"etiketten_{art}").eintrag_fuer(wort.strip(".,;:()")) is not None:
                return True
    except Exception:  # pragma: no cover - Wissensbasis fehlt
        return False
    return False


def kennung_neutral(zwischen: str) -> bool:
    """Ordnen die Zwischenwörter einen Wert ohne Ankündigung keinem anderen Gegenstand zu? Klein geschriebene Wörter,
    Funktionswörter und Anreden ("bitte", "hinten", "erhalten Sie") – kein groß geschriebenes Sachwort ("Hotline",
    "Tarif", "Versicherungsjahr", "Kfz": "Transferticket Hotline 0800-1234567")."""
    for w in re.findall(r"[^\W\d_][\w\-]*", zwischen or ""):
        if w[:1].isupper() and not ist_funktionswort(w) and w.casefold() not in ("nr", "nummer", "code", "id"):
            return False
    return True


def _letztes_wort(text: str, pos: int, k: int) -> str:
    teile = text[pos:k].split()
    return teile[-1].strip(".,;:()") if teile else ""


def _wert_ueberspringen(text: str, i: int, grenze: int) -> int:
    """Ende des Werts eines fremden Felds ab i: bis zum nächsten Komma, Semikolon oder Zeilenende."""
    m = re.compile(r"[^,;\n]*").match(text, i, grenze)
    return m.end() if m else i


def wert_hinter_etikett(text: str, pos: int, wert_re: re.Pattern, *, grenze: int | None = None, ist_etikett=None,
                        max_woerter: int = MAX_ZWISCHENWOERTER, zwischenwort=None,
                        ohne_ankuendigung: int = 0, kennung: bool = False, fremd_pruefen=None,
                        anderes_etikett=None) -> Wertfund | None:
    """Wert der Form `wert_re` hinter einem Etikett, das bei `pos` endet (Regel im Modulkopf): direkt hinter Füllung
    oder hinter Zwischenwörtern desselben Satzes bis zu einer Ankündigung. ist_etikett(phrase): Feld-Etikett der
    Wissensbasis (für den Abbruch an einem anderen Etikett); ohne sie zählen nur die Etiketten dieses Moduls.
    zwischenwort(start, ende, umbruch): ist ein Treffer der Wertform direkt hinter dem Etikett in Wahrheit ein
    Zwischenwort ("GEBURTSNAME, FALLS ABWEICHEND: …", "eVB-Nummer ANGEBEN: …")? Dann gilt der Weg über die
    Zwischenwörter – wie bei klein geschriebenen Wörtern, die die Wertform gar nicht erst trifft.
    ohne_ankuendigung: hinter so vielen Zwischenwörtern ohne Ziffer gilt ein Wert der Form auch ohne Ankündigung,
    wenn er in derselben Zeile steht und Zeile oder Satz beendet ("Prüfziffer hinten 739") – ankuendigung "frei".
    kennung: der Wert ist eine Kennung (eVB, Transferticket, Kartenprüfnummer) – dann kündigt auch das Nummer-Wort
    im Satz an ("hat die Nummer K7H3M9P"), schwächer eine Präposition direkt davor ("unter K7H3M9P erstellt": nur
    ein Wert aus Buchstaben und Ziffern); ein Wert hinter einem Gegenstand mit eigener Nummer ("Transferticket für
    Tarif: PREMIUM2024", "…, Kennzeichen: M-AB 123, lautet: …") gehört diesem, und ohne Ankündigung zählt ein Wert
    nur hinter neutralen Zwischenwörtern (kennung_neutral: nicht "Transferticket Hotline 0800-1234567").
    fremd_pruefen(wort): eigene Prüfung auf einen Gegenstand mit eigener Nummer (Standard fremder_gegenstand);
    anderes_etikett(i): beginnt bei i ein anderes Etikett (Abbruch, zusätzlich zu den Etiketten dieses Moduls – hinter
    einem Zeilenumbruch auch als erstes Wort)?"""
    fremd_pruefen = fremd_pruefen or fremder_gegenstand
    ende_suche = min(len(text), grenze if grenze is not None else len(text), pos + _SUCHFENSTER)
    i, umbruch, zelle = _fuellung(text, pos, ende_suche, wert_re)
    if i is not None and i < ende_suche:
        m = wert_re.match(text, i)
        if m and not (zwischenwort is not None and zwischenwort(m.start(), m.end(), umbruch)):
            return Wertfund(m.start(), m.end(), umbruch, zelle, "", "")
    # Zwischenwörter desselben Satzes bis zu einer Ankündigung
    k, woerter, umbruch, nach_komma, fremd = pos, 0, False, False, False
    ankuendigung_re = _ANKUENDIGUNG_KENNUNG_RE if kennung else _ANKUENDIGUNG_RE
    while k < ende_suche and woerter <= max_woerter:
        c = text[k]
        if c in " \t" and not text.startswith("\t\t", k):
            k += 1
            continue
        if text.startswith("\t\t", k):
            if not woerter or umbruch:
                return None                             # Zellgrenze direkt hinter dem Etikett: oben geprüft; in der
                                                        # nächsten Zeile ein anderes Feld ("Geburtsland ⇥⇥ Polen")
            return _nach_ankuendigung(text, k + 2, ende_suche, wert_re, pos, k, "zelle")
        if c == "\n":
            if umbruch:
                return None                             # höchstens ein Umbruch ("die Prüfziffer" ⏎ "hinten lautet")
            umbruch = nach_komma = True                 # eine neue Zeile kann ein neues Feld beginnen
            k += 1
            continue
        if c in ":=":
            if kennung and woerter and fremd_pruefen(_letztes_wort(text, pos, k)):
                k, fremd = _wert_ueberspringen(text, k + 1, ende_suche), True   # "Transferticket für Tarif: …"
                continue
            fund = _nach_ankuendigung(text, k + 1, ende_suche, wert_re, pos, k, c)
            if fund is not None:
                return fund
            k += 1
            continue
        if c in ",–—-":
            nach_komma = nach_komma or c == ","
            k += 1
            continue
        if c in "!?;":
            return None
        if c == "(":
            kl = _KLAMMER_RE.match(text, k, ende_suche)
            if kl is None or text.count("\n", k, kl.end()) > 1:
                return None
            woerter += 1
            k = kl.end()
            continue
        w = _WORT_RE.match(text, k, ende_suche)
        if w is None:
            k += 1
            continue
        if woerter and (_eigenes_etikett(text, k) or (anderes_etikett is not None and anderes_etikett(k))):
            return None
        if umbruch and anderes_etikett is not None and anderes_etikett(k):
            return None                                 # die neue Zeile beginnt mit einem anderen Feld
        feld = _fremdes_feld(text, k, nach_komma, ist_etikett) if woerter else None
        if feld is not None:
            if not kennung:
                return None
            k, fremd = _wert_ueberspringen(text, feld, ende_suche), True     # "…, Kennzeichen: M-AB 123, lautet: …"
            continue
        if 0 < woerter <= ohne_ankuendigung and not umbruch and not fremd and (
                not kennung or kennung_neutral(text[pos:k])):
            v = wert_re.match(text, k)
            if v is not None and WERT_ENDE_RE.match(text, v.end()) and not re.search(r"\d", text[pos:k]) \
                    and text[pos:k].split()[-1].strip(".,:").casefold() not in _VERWEISWOERTER:
                return Wertfund(v.start(), v.end(), False, False, " ".join(text[pos:k].split()).strip(" ,"), "frei")
        a = ankuendigung_re.match(text, k)
        if a is not None:
            fund = _nach_ankuendigung(text, a.end(), ende_suche, wert_re, pos, k, a.group(0).casefold())
            if fund is not None:
                return fund
        if kennung and woerter:
            a = _SCHWACHE_ANKUENDIGUNG_RE.match(text, k)
            if a is not None:
                j = a.end()
                while j < ende_suche and text[j] in " \t":
                    j += 1
                v = wert_re.match(text, j)
                if v is not None and re.search(r"[A-Za-z]", v.group(0)) and re.search(r"\d", v.group(0)):
                    return Wertfund(v.start(), v.end(), False, False, " ".join(text[pos:k].split()).strip(" ,"),
                                    a.group(0).casefold())
        wort_ende = w.end()
        roh = w.group(0)
        if roh.endswith(":") and len(roh) > 1:
            wort_ende -= len(roh) - len(roh.rstrip(":"))  # der Doppelpunkt kündigt an (nächster Durchlauf)
        elif roh[-1:] in ",;!?" and len(roh) > 1:
            wort_ende -= 1
        if roh.rstrip(",:;")[-1:] in "!?" or _satzende(text, k, wort_ende):
            return None
        woerter += 1
        k = wort_ende
    return None


_LEERZEILE_RE = re.compile(r"[ \t:]*\n[ \t]*\n[ \t]*")


def _nach_ankuendigung(text: str, i: int, grenze: int, wert_re, pos: int, k: int, art: str) -> Wertfund | None:
    """Wert direkt hinter einer Ankündigung (Füllzeichen davor erlaubt, ein Zeilenumbruch – oder eine Leerzeile, wenn
    der Wert dann allein in seiner Zeile steht: "Ihre eVB-Nummer lautet:" ⏎ ⏎ "K7H3M9P")."""
    j, umbruch, zelle = _fuellung(text, i, grenze, wert_re)
    if j is None:
        leer = _LEERZEILE_RE.match(text, i, grenze)
        m = wert_re.match(text, leer.end(), grenze) if leer is not None else None
        if m is not None and WERT_ENDE_RE.match(text, m.end()) and text[m.end():m.end() + 1] in ("\n", ""):
            return Wertfund(m.start(), m.end(), True, False, " ".join(text[pos:k].split()).strip(" ,"), art)
        return None
    if j >= grenze:
        return None
    m = wert_re.match(text, j)
    if m is None:
        return None
    zwischen = " ".join(text[pos:k].split()).strip(" ,")
    return Wertfund(m.start(), m.end(), False, zelle or art == "zelle", zwischen, art)


# Aufzählung hinter einem Wert: Zusatz zum Wert ("(Pkw)", "– VW Golf", "für den Golf"), Trenner (Komma, Semikolon,
# Schrägstrich, "und", "sowie", Zeilenumbruch – auch zusammen: ",⏎"), Aufzählungszeichen am Zeilenanfang, Zuordnung vor
# dem nächsten Wert ("Pkw: …", "Fahrzeug 2: …", "M-AB 123: …", "VW Golf (M-AB 123): …", "für den Polo: …") oder ein
# Bezug ohne Doppelpunkt ("…, die für den Polo R7T2W9K")
_ZUSATZ_RE = re.compile(
    r"[ \t]*(?:\([^()\n]{1,40}\)"
    r"|[–—-][ \t]+[^\n,;()]{1,40}?(?=[ \t]*(?:[,;]|\n|$))"
    r"|(?i:für|fuer|zum|zur)[ \t]+(?:(?i:den|die|das|dem|ihren|ihr|ihre|ihrem)[ \t]+)?[^\s,;()]{1,30}"
    r"(?=[ \t]*(?:[,;.]|\bund\b|\bsowie\b|\n|$)))")
_FOLGE_TRENNER_RE = re.compile(r"[ \t]*(?:(?:[,;/]|\bund\b|\bsowie\b)[ \t]*(?:\n[ \t]*)?|\n[ \t]*)")
_ZUORDNUNG_RE = re.compile(r"(?:(?i:für|fuer)[ \t]+(?:(?i:den|die|das|dem)[ \t]+)?)?[^\n:;,()]{1,30}"
                           r"(?:[ \t]*\([^()\n]{1,30}\))?[ \t]*:[ \t]*")
_BEZUG_RE = re.compile(r"(?i:die|der|das)[ \t]+(?i:für|fuer)[ \t]+(?:(?i:den|die|das|dem)[ \t]+)?[^\s,;()]{1,30}[ \t]+"
                       r"(?:(?i:lautet|ist)[ \t]+)?")
# Mehrzahl eines Etiketts ("eVB-Nummern", "eVB-Nummer(n)", "Transfertickets", "Versicherungsbestätigungen")
_MEHRZAHL_RE = re.compile(r"(?i)(?:nummern|nummer\(n\)|nr\.?n|tickets|bestätigungen|bestaetigungen|codes)\b")


def mehrzahl(etikett: str) -> bool:
    return bool(_MEHRZAHL_RE.search(etikett or ""))


def folgewerte(text: str, ende: int, wert_re: re.Pattern, grenze: int | None = None, zuordnung: bool = False) -> list:
    """Weitere Werte einer Aufzählung hinter einem Wert ("eVB-Nummern: M3N4P5Q, R7T2W9K", untereinander, mit
    Aufzählungszeichen, mit Zusatz "K7H3M9P (Pkw), R7T2W9K (Anhänger)", "K7H3M9P – VW Golf" ⏎ "R7T2W9K – BMW 320d",
    "… lautet K7H3M9P, die für den Polo R7T2W9K"): [(start, ende, Zeilenumbruch davor?)]. zuordnung: auch hinter
    einer Zuordnung mit Doppelpunkt ("Pkw: …", "für den Polo: …") – hinter einem Mehrzahl-Etikett oder wenn schon der
    erste Wert so zugeordnet war; nie hinter einem Gegenstand mit eigener Nummer ("Tarif: KH2024A"). Eine Leerzeile
    beendet die Aufzählung."""
    aus = []
    grenze = min(len(text), grenze if grenze is not None else len(text))
    for _ in range(12):
        z = _ZUSATZ_RE.match(text, ende, grenze)
        i = z.end() if z is not None else ende
        t = _FOLGE_TRENNER_RE.match(text, i, grenze)
        if t is None or t.end() == i:
            break
        neue_zeile = "\n" in t.group(0)
        j = t.end()
        if neue_zeile:
            b = _LISTENZEICHEN_RE.match(text, j, grenze)
            if b is not None:
                j = b.end()
        m = wert_re.match(text, j, grenze)
        if m is None and zuordnung:
            zu = _ZUORDNUNG_RE.match(text, j, grenze)
            kopf = text[j:zu.end()].rstrip(" \t:").split() if zu is not None else []
            if kopf and not fremder_gegenstand(kopf[-1].strip("()")):
                m = wert_re.match(text, zu.end(), grenze)
        if m is None:
            bz = _BEZUG_RE.match(text, j, grenze)
            if bz is not None:
                m = wert_re.match(text, bz.end(), grenze)
        if m is None:
            break
        aus.append((m.start(), m.end(), neue_zeile))
        ende = m.end()
    return aus


def blockwerte(text: str, etikett_ende: int, wert_re: re.Pattern, grenze: int | None = None) -> list:
    """Werte einer Liste unter einer Titelzeile mit Mehrzahl-Etikett, deren Zeile selbst keinen Wert hat ("eVB-Nummern
    Ihres Fuhrparks" ⏎ "M-AB 123 ⇥⇥ VW Golf ⇥⇥ K7H3M9P" ⏎ "M-CD 456 ⇥⇥ BMW 320d ⇥⇥ R7T2W9K"): je Zeile bis zur
    Leerzeile (höchstens zwölf) jedes Wort einer Zelle mit genau der Wertform – [(start, ende)]; die Prüfung je Art
    (mit Ziffer, kein Wort) macht der Aufrufer."""
    grenze = min(len(text), grenze if grenze is not None else len(text))
    i = text.find("\n", etikett_ende, grenze)
    aus = []
    for _ in range(12):
        if i < 0 or i >= grenze:
            break
        i += 1
        j = text.find("\n", i, grenze)
        j = grenze if j < 0 else j
        if not text[i:j].strip():
            break
        for w in re.finditer(r"[^\s|•·▪◦‣:;,()]+", text[i:j]):
            if wert_re.fullmatch(w.group(0)):
                aus.append((i + w.start(), i + w.end()))
        i = j
    return aus


# ----------------------------------------------------------------------
# Prüfung der Werte
# ----------------------------------------------------------------------
_DATUM_RE = re.compile(r"\d{1,2}\.\d{1,2}\.\d{2,4}|\d{4}-\d{2}-\d{2}")
_DATUM_KURZ_RE = re.compile(r"\d{1,2}[/.]\d{2,4}")
_JAHRESBEREICH_RE = re.compile(r"(?:19|20)(\d\d)[ ]?[/\-][ ]?(?:19|20)?(\d\d)")
_BETRAG_RE = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+,\d{1,2}")
# hinter einer Kartenprüfnummer steht nie eine Einheit ("1500 EUR Selbstbeteiligung", "250 qm")
EINHEIT_DANACH_RE = re.compile(r"[ \t]*(?:€|%|(?i:eur|euro|prozent|stk|stück|qm|m²|km|kg|jahre?n?|monate?n?|tage?n?"
                               r"|std|stunden?|wochen?|ziffern|stellen|stellig|-stellig|zeichen)(?![\wäöüß]))")
# ein Wert unter seinem Etikett beendet seine Zeile bzw. Zelle ("CVC" ⏎ "123"); geht die Zeile weiter, ist es
# Fließtext ("… die CVC" ⏎ "2024 wurde der Vertrag umgestellt", "Kartenprüfnummer:" ⏎ "8001 Zürich")
WERT_ENDE_RE = re.compile(r"[ \t]*(?:$|\n|\t\t|[.,;)](?=[ \t\n]|$))")
# englische Statuswörter (die Wortgestalt kennt deutsche Wörter): "eVB: EXPIRED", "Transferticket: REQUESTED"
_STATUSWOERTER = frozenset("""
expired pending issued active inactive invalid valid requested approved rejected declined cancelled canceled
received created deleted blocked unknown missing open closed none
""".split())


def versalien(text: str) -> bool:
    """Überwiegend Großbuchstaben (oder gar keine Buchstaben)?"""
    buchstaben = [c for c in text if c.isalpha()]
    return not buchstaben or sum(c.isupper() for c in buchstaben) > 0.7 * len(buchstaben)


def _versalien_kontext(text: str, s: int, e: int, etikett_start: int) -> bool:
    """Steht die Stelle s:e in Versalien geschriebenem Text (Zeile des Etiketts und des Werts ohne den Wert)? Dort ist
    ein Wort aus Großbuchstaben ohne Ziffer kein Code ("EVB-NUMMER ANFRAGE")."""
    a = text.rfind("\n", 0, etikett_start) + 1
    b = text.find("\n", e)
    return versalien(text[a:s] + " " + text[e:b if b >= 0 else len(text)])


def _wortartig(wert: str, wortgestalt) -> bool:
    """Ist ein Wert ohne Ziffer ein Wort ("ERTEILT", "BERLIN-TEGEL", "EXPIRED") statt eines Codes ("KXHPMTQ")?"""
    if wert.casefold() in _STATUSWOERTER:
        return True
    if wortgestalt is None:
        try:
            from . import wissen
            wortgestalt = wissen.ist_wortgestalt
        except Exception:  # pragma: no cover - Wissensbasis fehlt
            return False
    try:
        return bool(wortgestalt(wert))
    except Exception:
        return False


# Gestalten, die keine eVB und kein Transferticket sind: Telefonnummer ("0800-1234567", "0221/123456-0"),
# Internetadresse ("www.huk24.de", "verti24.de"), Tarif- oder Produktcode aus einem Wort und einer Jahreszahl
# ("PREMIUM2024", "KOMFORT-2025")
_TELEFON_FORM_RE = re.compile(r"(?:(?:\+|00)\d{1,3}[-/]?\d{2,5}|0\d{2,5})[-/]\d{3,9}(?:-\d{1,5})?")
_INTERNET_FORM_RE = re.compile(r"(?i)(?:^|[./])www\.|\.(?:de|com|net|org|eu|info|biz|at|ch|io|co|uk|fr|it|nl|es|be|lu"
                               r"|pl|online|shop)$")
_WORT_JAHR_RE = re.compile(r"(?:^|[^A-Za-zÄÖÜäöüß])([A-Za-zÄÖÜäöüß]{5,})[-]?(?:19|20)\d\d(?!\d)"
                           r"|(?<!\d)(?:19|20)\d\d[-]?([A-Za-zÄÖÜäöüß]{5,})(?:$|[^A-Za-zÄÖÜäöüß])")


def andere_gestalt(wert: str, wortgestalt=None) -> bool:
    """Hat der Wert die Gestalt von etwas anderem als einer eVB-Nummer oder einem Transferticket – Telefonnummer,
    Internetadresse, Zeitraum ("2024/2025", "2024-2026", "12/2025"), Datum, Betrag oder ein Tarif-/Produktcode aus einem
    Wort und einer Jahreszahl ("PREMIUM2024")? (Gegenprüfung 4d: "Transferticket Hotline 0800-1234567",
    "Transferticket Versicherungsjahr 2024/2025", "… anfordern unter www.huk24.de" waren Kennungen.)"""
    w = (wert or "").strip()
    if _TELEFON_FORM_RE.fullmatch(w) or _INTERNET_FORM_RE.search(w) or zeitraum(w) or _DATUM_RE.fullmatch(w) \
            or _BETRAG_RE.fullmatch(w):
        return True
    m = _WORT_JAHR_RE.search(w)
    return m is not None and _wortartig(m.group(1) or m.group(2), wortgestalt)


def evb_gueltig(wert: str, versalien_umgebung: bool, wortgestalt=None) -> bool:
    """eVB: mit Ziffer – ohne Ziffer nur in gemischt geschriebenem Text und nur, wenn der Wert kein Wort ist; nie mit
    der Gestalt von etwas anderem (andere_gestalt)."""
    if andere_gestalt(wert, wortgestalt):
        return False
    if any(c.isdigit() for c in wert):
        return True
    return not versalien_umgebung and not _wortartig(wert, wortgestalt)


def ticket_gueltig(wert: str, versalien_umgebung: bool, wortgestalt=None) -> bool:
    """Transferticket: 8 bis 20 Buchstaben/Ziffern, kein Datum, kein Betrag, keine Telefonnummer, keine
    Internetadresse, kein Zeitraum (andere_gestalt); gemischt geschrieben mit mindestens zwei Ziffern ("beantragen" ist
    ein Wort), in Großbuchstaben mit Ziffer – ohne Ziffer nur in gemischt geschriebenem Text und nur, wenn der Wert
    kein Wort ist ("ANGEFORDERT", "SF-KLASSE")."""
    zeichen = [c for c in wert if c.isalnum()]
    ziffern = sum(c.isdigit() for c in zeichen)
    if not 8 <= len(zeichen) <= 20 or andere_gestalt(wert, wortgestalt):
        return False
    if any(c.islower() for c in wert):
        return ziffern >= 2
    if ziffern:
        return True
    return not versalien_umgebung and not _wortartig(wert, wortgestalt)


def jahresbereich(wert: str) -> bool:
    """Zwei aufeinanderfolgende Jahre ("2024/2025", "2025/26") – ein Zeitraum, keine Kennung ("2024/12" bleibt eine)."""
    m = _JAHRESBEREICH_RE.fullmatch((wert or "").strip())
    return m is not None and (int(m.group(1)) + 1) % 100 == int(m.group(2))


def evb_rauschen_gueltig(wert: str) -> bool:
    """eVB mit Einfügungen der Texterkennung: 6 bis 9 Buchstaben/Ziffern, mindestens zwei Ziffern, kein Datum und kein
    Jahresbereich ("12/2025", "2025/2026")."""
    kern = re.sub(r"[/|]", "", wert)
    ziffern = sum(c.isdigit() for c in kern)
    return (6 <= len(kern) <= 9 and ziffern >= 2 and not _DATUM_KURZ_RE.fullmatch(wert)
            and not jahresbereich(wert))


def etikett_zeile(text: str, s: int, e: int) -> bool:
    """Ist die Zeile des Etiketts s:e eine Etikettzeile – Doppelpunkt hinter dem Etikett oder höchstens zwei Wörter
    davor in seiner Zelle ("Ihre eVB-Nummer", "Kreditkarte ⇥⇥ CVC") – und kein Satz, der zufällig mit dem Etikett
    endet ("Bitte geben Sie im Online-Portal die CVC")?"""
    zeilenende = text.find("\n", e)
    if ":" in text[e:zeilenende if zeilenende >= 0 else len(text)]:
        return True
    zeilenanfang = text.rfind("\n", 0, s) + 1
    zellanfang = max(zeilenanfang, text.rfind("\t\t", zeilenanfang, s) + 2)
    return len(re.findall(r"[^\W\d_]+", text[zellanfang:s])) <= 2


# Kartenangabe in der Nähe einer "Prüfnummer"/eines "Sicherheitscodes" (Kartennummer: Luhn-Prüfung)
KARTENANGABE_RE = re.compile(
    r"(?i:kredit-?kart|karten-?n(?:umme)?r|karteninhaber|zahlungskart|debit-?kart|bankkart|girocard|ec-karte"
    r"|karten-?r(?:ü|ue|u)ck|kartendaten)"
    r"|(?<![\wäöüß])(?i:visa|master-?card|maestro|american[ \t]+express|amex|diners(?:[ \t]+club)?|jcb)(?![\wäöüß])")
# Wörter, die eine Prüfnummer keinem anderen Gegenstand zuordnen (zwischen Etikett und Wert, in einer Klammer dahinter):
# klein geschriebene Wörter, Kartenangaben, "Rückseite", "Ziffern", "stellig" ("Sicherheitscode (3 Ziffern):",
# "Prüfnummer (3-stellig)") – nicht "(TÜV)", "der HU", "für Ihr Online-Postfach"
_KARTEN_NEUTRAL_RE = re.compile(r"(?i:karte|card|kredit|debit|visa|master|maestro|amex|express|diners|jcb|cvc|cvv"
                                r"|csc|cav|cid|r(?:ü|ue|u)cks|vorderseite|ziffer|stellig|stellen|unterschrift"
                                r"|sicherheit|kontroll|pr(?:ü|ue|u)f)")
# ganze Wörter, die eine Prüfnummer keinem anderen Gegenstand zuordnen ("Code: 739", "PIN: 739", "die drei Zahlen
# hinten", "die 3-stellige Nummer") – nicht als Teil eines Worts ("Kundennummer")
_KARTEN_NEUTRAL_WOERTER = frozenset({"code", "pin", "zahl", "zahlen", "nummer", "nr", "kpn", "gültig", "gueltig",
                                     "ablauf"})
# Gegenstände, deren Prüfnummer keine Kartenprüfnummer ist (in der Zeile des Etiketts, der Zeile davor, einer Klammer
# oder hinter dem Wert: "Prüfbericht Nr. 4711, Prüfnummer 0815", "DIN EN ISO 9001" ⏎ "Prüfnummer 4102",
# "Prüfnummer 4567 vom TÜV", "Sicherheitscode: 4711 (Tür)")
_FREMDER_GEGENSTAND_RE = re.compile(
    r"(?i:t(?:ü|ue|u)v|dekra|gt(?:ü|ue|u)|k(?:ü|ue|u)s\b|hauptuntersuchung|abgasuntersuchung|plakette"
    r"|pr(?:ü|ue|u)fbericht|pr(?:ü|ue|u)fstelle|pr(?:ü|ue|u)fzeichen|pr(?:ü|ue|u)fstand|gutachten"
    r"|sachverst(?:ä|ae|a)ndig|zertifi|norm\b"
    r"|zulassung|typpr(?:ü|ue|u)f|bauart|ger(?:ä|ae|a)t|fahrzeug|t(?:ü|ue|u)r\b|tor\b|schlo(?:ss|ß)|tresor|alarm"
    r"|online|portal|postfach|passwort|kennwort|zugang|login|konto\b|app\b)"
    r"|(?<![\wäöüß])(?:HU|AU|DIN|ISO|EN|VDE|GS|CE)(?![\wäöüß])")
_BEZUGSWORT_DAVOR_RE = re.compile(r"(?<![\wäöüß])([A-ZÄÖÜ][\wäöüß]*)[ \t]*[,–\-]?[ \t]+$")
_KLAMMER_DANACH_RE = re.compile(r"[ \t]*\(([^()\n]{1,40})\)")


def kartenneutral(woerter: str) -> bool:
    """Ordnen diese Wörter eine Prüfnummer keinem anderen Gegenstand zu (siehe _KARTEN_NEUTRAL_RE)?"""
    if _FREMDER_GEGENSTAND_RE.search(woerter or ""):
        return False
    for w in re.findall(r"[^\W\d_][\w\-]*", woerter or ""):
        if w[:1].isupper() and not ist_funktionswort(w) and not _KARTEN_NEUTRAL_RE.search(w) \
                and w.casefold() not in _KARTEN_NEUTRAL_WOERTER:
            return False
    return True


def _luhn(ziffern: str) -> bool:
    if not 13 <= len(ziffern) <= 19:
        return False
    summe, doppelt = 0, False
    for c in reversed(ziffern):
        n = int(c)
        if doppelt:
            n = n * 2 - 9 if n > 4 else n * 2
        summe += n
        doppelt = not doppelt
    return summe % 10 == 0


_KARTENNUMMER_RE = re.compile(r"(?<!\d)\d(?:[ \-]?\d){12,18}(?!\d)")
# Kartendaten ohne Etikett der Prüfnummer: Kartennummer, Ablaufdatum, dann drei oder vier Ziffern am Ende ihrer Zeile –
# auch über Zeilen ("Mastercard" ⏎ "5555 5555 5555 4444" ⏎ "11/26" ⏎ "739", "Kartennummer: …" ⏎ "Gültig bis: 12/27" ⏎
# "739") und hinter Etiketten, die eine Prüfnummer der Karte nicht fremd zuordnen ("Code: 739", "Rückseite: 739",
# "Ziffern hinten: 739", "PIN: 739"); ohne Ablaufdatum nur mit einem Hinweis darauf ("…, die drei Zahlen hinten: 739")
_KF_TRENNER = r"[ \t]*[,;/–\-]?[ \t]*\(?[ \t]*(?:\n[ \t]*)?"
_KF_ABLAUF_RE = re.compile(
    _KF_TRENNER + r"(?:(?i:g(?:ü|ue|u)ltig(?:[ \t]+bis)?|exp\.?|expiry|ablauf(?:datum)?|valid[ \t]+thru)"
    r"[ \t]*:?[ \t]*)?"
    r"(?:0[1-9]|1[0-2])(?:[ \t]?/[ \t]?(?:\d{2}|20\d{2})|\d{2})(?!\d)[ \t]*\)?")
_KF_TRENNER_RE = re.compile(_KF_TRENNER)
_KF_PRUEFNUMMER_RE = re.compile(r"(?<![\d/.,\-])(\d{3,4})(?=[ \t]*[.,;)]?[ \t]*$)")
_KF_HINWEIS_RE = re.compile(r"(?i)r(?:ü|ue|u)cks|hinten|ziffer|zahl|code|csc|cvc|cvv|cid|pr(?:ü|ue|u)f|sicherheit"
                            r"|kontroll|pin|stellig|nummer")


def _kartenfolge(text: str, e: int, grenze: int) -> tuple | None:
    """(start, ende) der Kartenprüfnummer in den Kartendaten hinter einer Kartennummer, die bei e endet, oder None."""
    i = e
    ablauf = _KF_ABLAUF_RE.match(text, i, grenze)
    if ablauf is not None:
        i = ablauf.end()
    i = _KF_TRENNER_RE.match(text, i, grenze).end()
    zeilenende = text.find("\n", i, grenze)
    zeilenende = grenze if zeilenende < 0 else zeilenende
    zelle = text.find("\t\t", i, zeilenende)
    if zelle >= 0 and text[i:zelle].rstrip().endswith(":"):
        zelle = text.find("\t\t", zelle + 2, zeilenende)  # "Code: ⇥⇥ 739": der Wert in der Zelle hinter dem Etikett
    rest = text[i:zelle if zelle >= 0 else zeilenende]
    p = _KF_PRUEFNUMMER_RE.search(rest)
    if p is None:
        return None
    woerter = rest[:p.start()].strip(" \t:–-,(")
    ohne_stellig = re.sub(r"\d-?stellig\w*", "", woerter)
    if len(woerter.split()) > 8 or re.search(r"\d", ohne_stellig) or not kartenneutral(woerter):
        return None
    if woerter and woerter.split()[-1].strip(".,:").casefold() in _VERWEISWOERTER:
        return None                                     # "Die CVC gibt es seit 2015."
    if ablauf is None and (not _KF_HINWEIS_RE.search(woerter) or re.fullmatch(r"(?:19|20)\d\d", p.group(1))):
        return None
    s0, e0 = i + p.start(1), i + p.end(1)
    if EINHEIT_DANACH_RE.match(text, e0):
        return None
    return s0, e0


def _luhn_ende(text: str, s: int, e: int) -> int | None:
    """Ende der längsten Kartennummer mit gültiger Prüfziffer (13 bis 19 Ziffern) am Anfang von text[s:e] – auch wenn
    die Ziffern dahinter weitergehen ("5555 5555 5555 4444 11/26": der Monat des Ablaufdatums) – oder None."""
    stellen = [i for i in range(s, e) if text[i].isdigit()]
    for n in range(min(19, len(stellen)), 12, -1):
        ende = stellen[n - 1] + 1
        if (n == len(stellen) or not text[ende].isdigit()) and _luhn("".join(text[i] for i in stellen[:n])):
            return ende
    return None


def kartendaten(text: str) -> bool:
    """Stehen in text Kartendaten – eine Kartenangabe ("Kreditkarte", "Kartennummer", "Visa", "Mastercard") oder eine
    Kartennummer mit gültiger Prüfziffer?"""
    if KARTENANGABE_RE.search(text):
        return True
    return any(_luhn(re.sub(r"\D", "", m.group(0))) for m in _KARTENNUMMER_RE.finditer(text))


def kartenbezug(text: str, s: int, e: int, extra: re.Pattern | None = None) -> bool:
    """Kartenangabe ("Kreditkarte", "Kartennummer", "Visa") oder Kartennummer mit gültiger Prüfziffer in der Zeile der
    Stelle, den zwei Zeilen darüber oder der Zeile darunter; extra: weiteres Muster (Platzhalter [KREDITKARTE])."""
    a = s
    for _ in range(3):
        a = text.rfind("\n", 0, a)
        if a < 0:
            break
    a = max(0, a + 1)
    b = text.find("\n", e)
    if b >= 0:
        b = text.find("\n", b + 1)
    fenster = text[a:b if b >= 0 else len(text)]
    return kartendaten(fenster) or (extra is not None and extra.search(fenster) is not None)


def _fremder_bezug(text: str, s: int, e: int, wert_ende: int) -> bool:
    """Gehört die Prüfnummer hinter dem Etikett s:e zu etwas anderem? Ein großgeschriebenes Bezugswort direkt davor
    ("TÜV Prüfnummer", "Zulassung, Prüfnummer"), ein fremder Gegenstand in der Zeile davor bzw. derselben Zeile vor dem
    Etikett, in einer Klammer dahinter oder hinter dem Wert ("Prüfnummer 4567 vom TÜV", "4711 (Tür)")."""
    m = _BEZUGSWORT_DAVOR_RE.search(text, max(0, s - 40), s)
    if m is not None and not ist_funktionswort(m.group(1)) and not KARTENANGABE_RE.search(m.group(1)):
        return True
    zeilenanfang = text.rfind("\n", 0, s) + 1
    vorher = text.rfind("\n", 0, max(0, zeilenanfang - 1)) + 1
    if _FREMDER_GEGENSTAND_RE.search(text, vorher, s):
        return True
    k = _KLAMMER_DANACH_RE.match(text, e)
    if k is not None and not kartenneutral(k.group(1)):
        return True
    zeilenende = text.find("\n", wert_ende)
    rest = text[wert_ende:zeilenende if zeilenende >= 0 else len(text)]
    return bool(_FREMDER_GEGENSTAND_RE.search(rest[:60]))


# Monat/Jahr ("12/2025", "3/25", "12.2024") – nicht "12/345" (dreistelliges Jahr), nicht "42/2024" (kein Monat)
_MONAT_JAHR_RE = re.compile(r"(?:0?[1-9]|1[0-2])[/.](?:\d{2}|(?:19|20)\d{2})")
# Zwei Jahre ("2024-2026", "2024/2025") – ein Zeitraum, auch wenn sie nicht aufeinander folgen
_JAHRESSPANNE_RE = re.compile(r"(?:19|20)\d\d[ ]?[/\-][ ]?(?:19|20)\d\d")
# Kürzel vor einer Zifferngruppe ("KH 0815", "KFZ-VB 12345", "SF-TT 4711 0815", "KFZVB 12345")
_KUERZEL_RE = re.compile(r"[A-ZÄÖÜ]{1,6}(?:-[A-ZÄÖÜ]{1,6})?")


def zeitraum(wert: str) -> bool:
    """Monat/Jahr ("12/2025"), Jahresbereich ("2024/25") oder zwei Jahre ("2024-2026")?"""
    w = (wert or "").strip()
    return bool(_MONAT_JAHR_RE.fullmatch(w) or jahresbereich(w) or _JAHRESSPANNE_RE.fullmatch(w))


def kennungsform(wert: str, zeitraum_erlaubt: bool = False) -> bool:
    """Siehe kennung_teil: hat der Wert die allgemeine Form einer Kennung?"""
    return kennung_teil(wert, zeitraum_erlaubt) is not None


def kennung_teil(wert: str, zeitraum_erlaubt: bool = False) -> str | None:
    """Hat ein Wert hinter dem Etikett einer eVB, eines Transfertickets oder einer Kartenprüfnummer die allgemeine Form
    einer Kennung – das erste Wort mit Ziffer oder ein Kürzel aus Großbuchstaben vor einer Zifferngruppe ("KFZ-VB
    12345"), zusammen mindestens drei Ziffern, keine Einheit dahinter ("12345", "TT-12345", "KH 0815 4471", "12/345")?
    Nicht: "SF 12 / SF 8", "Tarif KH 12", "Hotline 0800 1234567", "3-4 Ziffern", "250 Euro", "Capital Partners 2024",
    ein Betrag, ein Datum und – außer mit zeitraum_erlaubt (hinter "Nr.": eine laufende Nummer mit Jahr) – ein
    Zeitraum ("12/2025", "2024/2025")."""
    teile = (wert or "").split()
    kennung: list = []
    for i, t in enumerate(teile):
        kern = t.rstrip(".,;:)")
        if any(c.isdigit() for c in kern):
            if _BETRAG_RE.fullmatch(kern) or _DATUM_RE.fullmatch(kern) or (
                    not zeitraum_erlaubt and zeitraum(kern)):
                break                                   # Betrag, Datum, Zeitraum ("12/2025", "2024/2025")
            kennung.append(kern)
        elif not kennung and _KUERZEL_RE.fullmatch(kern) and i + 1 < len(teile) \
                and any(c.isdigit() for c in teile[i + 1]):
            kennung.append(kern)
        else:
            break
        if kern != t:
            break
    if not kennung or not any(c.isdigit() for c in kennung[0] + (kennung[1] if len(kennung) > 1 else "")):
        return None
    rest = " ".join(teile[len(kennung):])
    if rest and EINHEIT_DANACH_RE.match(" " + rest):
        return None
    return " ".join(kennung) if sum(c.isdigit() for c in "".join(kennung)) >= 3 else None


# Nummer-Wort als Abkürzung ("Nr.", "-Nr.", "No.", "-ID") oder als Teil eines zusammengesetzten Worts
# ("Versicherungsbestätigungsnummer", "Kartenprüfnummer", "Kartenprüfnr.")
_ALLGEMEINES_NUMMER_WORT_RE = re.compile(r"(?i)(?:(?:nr|no)\.?|[-_]id|(?<=[a-zäöüß])nu(?:m|rn){2}ern?)$")


def allgemeines_nummer_etikett(etikett: str) -> bool:
    """Ist das Etikett mit eigener Wertform zugleich ein allgemeines Kennungs-Etikett – sein Nummer-Wort eine
    Abkürzung oder Teil eines zusammengesetzten Worts ("Versicherungsbestätigung Nr.", "eVB-Nr.", "VB-Nr.",
    "Transferticket-Nr.", "Versicherungsbestätigungsnummer", "Kartenprüfnummer")? Hinter diesen Etiketten las der
    allgemeine Kennungsweg schon vor Runde 4 jede Kennung, auch eine laufende Nummer mit Jahr ("3/2025", "2024/25",
    "12/345"); "eVB-Nummer", "VB-Nummer", "Transferticket-Nummer" (ausgeschriebenes Nummer-Wort hinter Bindestrich)
    kennt erst die Runde 4."""
    return bool(_ALLGEMEINES_NUMMER_WORT_RE.search((etikett or "").strip().rstrip(":").strip()))


def allgemeiner_wert(etikett: str, wert: str) -> bool:
    """Gilt hinter dem Etikett einer eigenen Wertform (eVB, Transferticket, Kartenprüfnummer) für `wert` ZUSÄTZLICH der
    allgemeine Kennungsweg? Nur hinter einem Nummer-Etikett (nummer_etikett): hinter einem allgemeinen Nummer-Etikett
    (allgemeines_nummer_etikett) jeder Wert, den der allgemeine Weg liest – wie vor Runde 4, auch "3/2025",
    "2024/25", "KFZ-VB 12345" –, sonst nur ein Wert mit der Form einer Kennung ohne Zeitraum (kennungsform: nicht
    "eVB-Nummer 2024/2025")."""
    if not nummer_etikett(etikett):
        return False
    return allgemeines_nummer_etikett(etikett) or kennungsform(wert)


# ----------------------------------------------------------------------
# Alle Kennungen eines Texts
# ----------------------------------------------------------------------
class Kennungsfund(NamedTuple):
    art: str                # "evb", "ticket" oder "cvc" (auch hinter "Prüfnummer" mit Kartenbezug)
    start: int
    ende: int
    etikett_start: int
    etikett_ende: int
    etikett: str            # Text des Etiketts ("eVB-Nummer")
    sicherheit: float
    rauschen: bool = False  # eVB mit Einfügungen der Texterkennung ("K7/H3MY9P")


# Wert des allgemeinen Kennungswegs direkt hinter einem Nummer-Etikett ("VB-Nr. 2024/25", "eVB-Nr. KFZ-VB 12345")
_ALLGEMEIN_WERT_RE = re.compile(r"[A-ZÄÖÜ0-9][A-Za-zÄÖÜ0-9\-./]*(?:[ ][A-ZÄÖÜ0-9][A-Za-zÄÖÜ0-9\-./]*){0,3}")


def _allgemein(text: str, m: re.Match, grenze: int, neu) -> None:
    """Wert des allgemeinen Kennungswegs hinter dem Nummer-Etikett m (allgemeiner_wert) als Art "allgemein"."""
    if not nummer_etikett(m.group(0)):
        return
    i, umbruch, _ = _fuellung(text, m.end(), min(grenze, m.end() + 60), _ALLGEMEIN_WERT_RE)
    if i is None or umbruch:
        return                                          # nur in der Zeile des Etiketts ("Kartenprüfnummer:"
                                                        # ⏎ "8001 Zürich")
    w = _ALLGEMEIN_WERT_RE.match(text, i, grenze)
    if w is None:
        return
    teil = kennung_teil(w.group(0), zeitraum_erlaubt=allgemeines_nummer_etikett(m.group(0)))
    if teil:
        neu("allgemein", w.start(), w.start() + len(teil), m, 0.7)


def drei_ziffern(etikett: str) -> bool:
    """Etiketten, hinter denen eine Kartenprüfnummer genau drei Ziffern hat: CAV (JCB) – "CAV 2019" ist eine
    Jahreszahl."""
    return bool(re.match(r"CAV", (etikett or "").strip()))


def nummer_etikett(etikett: str) -> bool:
    """Etikett mit Nummer-Wort ("Versicherungsbestätigung Nr.", "eVB-Nr.", "Transferticket-Nummer", "Kartenprüfnummer"):
    dort kündigt das Etikett eine Nummer an – neben der eigenen Form gilt auch der allgemeine Kennungsweg (vor Runde 4
    der einzige: "Versicherungsbestätigung Nr. 123/24", "Transferticket-Nr.: TT-12345")."""
    return bool(re.search(r"(?i)(?:nr|nummer|nummern|nurnmer|no|id)\.?:?$", (etikett or "").strip()))


def _cvc_passt(text: str, m: re.Match, t: Wertfund, art: str) -> bool:
    """Passt der Wert hinter einem Kartenprüfnummer-Etikett? Nie mit einer Einheit dahinter ("1500 EUR"); in der Zeile
    unter dem Etikett nur, wenn dessen Zeile eine Etikettzeile ist und der Wert seine Zeile bzw. Zelle beendet; hinter
    einem Ankündigungswort ("Die Kartenprüfnummer ist 2024 eingeführt worden") nur am Ende des Satzes; ohne
    Ankündigung keine Jahreszahl ("Die CVC gibt es seit 2015."); hinter "CAV" drei Ziffern."""
    if EINHEIT_DANACH_RE.match(text, t.ende):
        return False
    ziffern = sum(c.isdigit() for c in text[t.start:t.ende])
    if not 3 <= ziffern <= 4:
        return False
    if drei_ziffern(m.group(0)) and ziffern != 3:
        return False
    if t.darunter:
        return etikett_zeile(text, m.start(), m.end()) and bool(WERT_ENDE_RE.match(text, t.ende))
    if t.ankuendigung == "frei" and re.fullmatch(r"(?:19|20)\d\d", text[t.start:t.ende]):
        return False                                    # "Die CVC gibt es seit 2015."
    if t.ankuendigung and t.ankuendigung not in (":", "=", "zelle"):
        # hinter Zwischenwörtern und "lautet"/"ist" kein Satz, der weitergeht ("Die Kartenprüfnummer der neuen Karten
        # ist 2024 eingeführt worden") – wohl aber eine Aufzählung oder Klammer ("… ist 739 und steht hinten")
        return not _satz_geht_weiter(text, t.ende)
    if not t.ankuendigung and re.fullmatch(r"(?:19|20)\d\d", text[t.start:t.ende]) \
            and _ANKUENDIGUNG_RE.search(text, m.end(), t.start):
        return not _satz_geht_weiter(text, t.ende)      # "Die Kartenprüfnummer ist 2024 eingeführt worden"
    return True


def _satz_geht_weiter(text: str, i: int) -> bool:
    """Geht der Satz hinter text[:i] mit einem klein geschriebenen Wort weiter (außer "und", "oder", "sowie")?"""
    weiter = re.match(r"[ \t]*([^\W\d_]+)", text[i:i + 40])
    return weiter is not None and weiter.group(1)[:1].islower() and weiter.group(1) not in ("und", "oder", "sowie")


_VORAUSWAHL_RE = re.compile(r"(?i)v[b8]|ticket|c\.?v|cav|cid|pr(?:ü|ue|u)f|sicherheit|verifi|security|card"
                            r"|best(?:ä|ae|a)tigung")


def kennungen(text: str, *, ocr: bool = False, wortgestalt: Callable | None = None, ist_etikett=wissen_etikett,
              kartenbezug_extra: re.Pattern | None = None, start: int = 0, ende: int | None = None,
              allgemein: bool = False) -> list:
    """Alle eVB-Nummern, Transfertickets und Kartenprüfnummern hinter ihrem Etikett in text[start:ende] (Regel im
    Modulkopf) als [Kennungsfund]. ocr: auch die eVB mit Einfügungen der Texterkennung ("K7/H3MY9P").
    wortgestalt(wert): Wort statt Code (Standard wissen.ist_wortgestalt); ist_etikett(phrase): Feld-Etikett der
    Wissensbasis (Abbruch an einem anderen Etikett); kartenbezug_extra: weiteres Muster für die Kartenangabe.
    allgemein: auch Werte des allgemeinen Kennungswegs hinter einem Nummer-Etikett ohne eigene Wertform ("VB-Nr.
    2024/25", "eVB-Nr. 12/345": Art "allgemein", allgemeiner_wert) – für die Selbstkontrolle.
    Aufzählungen hinter dem ersten Wert (folgewerte) und, hinter einem Mehrzahl-Etikett ohne Wert in seiner Zeile, die
    Werte der Liste darunter (blockwerte).

    Prüfung je Art: eine eVB bzw. ein Transferticket in der Zeile unter dem Etikett nur mit Ziffer, ohne Ziffer nur in
    gemischt geschriebenem Text und nur, wenn der Wert kein Wort ist; eine Kartenprüfnummer nie vor einer Einheit, unter
    dem Etikett nur unter einer Etikettzeile und als Ende ihrer Zeile; hinter "Prüfnummer"/"Sicherheitscode"/"CID" nur
    mit Kartenangabe in der Nähe (oder in den Zwischenwörtern) und ohne fremden Bezug ("TÜV Prüfnummer", "Prüfnummer
    (TÜV)", "Prüfbericht Nr. 4711, Prüfnummer 0815")."""
    ende = len(text) if ende is None else ende
    if not _VORAUSWAHL_RE.search(text, start, ende) and not re.search(r"\d{4}[ \-]?\d{4}", text[start:ende]) \
            and not (kartenbezug_extra is not None and kartenbezug_extra.search(text, start, ende)):
        return []
    aus: list = []
    gesehen: set = set()

    def neu(art, s, e, m, sicherheit, rauschen=False):
        if (s, e) not in gesehen:
            gesehen.add((s, e))
            aus.append(Kennungsfund(art, s, e, m.start(), m.end(), m.group(0), sicherheit, rauschen))

    for m in ETIKETT_RE.finditer(text, start, ende):
        art = m.lastgroup
        form = _ART_ZU_FORM[art]
        pruefen = evb_gueltig if form == "evb" else ticket_gueltig

        def zwischenwort(s, e, umbruch, m=m, pruefen=pruefen):
            # ein Wort ohne Ziffer, das keine Kennung ist ("EVB-NUMMER ANGEBEN: K7H3M9P")
            w = text[s:e]
            return not any(c.isdigit() for c in w) and not pruefen(
                w, umbruch or _versalien_kontext(text, s, e, m.start()), wortgestalt)

        t = wert_hinter_etikett(text, m.end(), WERT_RE[form], grenze=ende, ist_etikett=ist_etikett,
                                zwischenwort=None if form == "cvc" else zwischenwort,
                                ohne_ankuendigung=OHNE_ANKUENDIGUNG, kennung=True)
        if form == "cvc":
            if t is None or not _cvc_passt(text, m, t, art):
                if allgemein:
                    _allgemein(text, m, ende, neu)
                continue
            if art == "pruef":
                if _fremder_bezug(text, m.start(), m.end(), t.ende) or not kartenneutral(t.zwischen):
                    if not KARTENANGABE_RE.search(t.zwischen):
                        continue                        # "TÜV Prüfnummer", "Prüfnummer der HU:", "… vom TÜV"
                klammer = _KLAMMER_DANACH_RE.match(text, m.end())
                if not (kartenbezug(text, m.start(), t.ende, kartenbezug_extra)
                        or re.search(r"(?i)karte|card", t.zwischen)
                        or (klammer is not None and re.search(r"(?i)karte|card", klammer.group(1)))):
                    continue                            # "Sicherheitscode (Rückseite der Karte): 739" zählt
            neu("cvc", t.start, t.ende, m, 0.9 if art == "cvc" else 0.75)
            continue
        if t is not None:
            wert = text[t.start:t.ende]
            umgebung = t.darunter or _versalien_kontext(text, t.start, t.ende, m.start())
            if pruefen(wert, umgebung, wortgestalt):
                neu(form, t.start, t.ende, m, 0.9)
                zuordnung = mehrzahl(m.group(0)) or (t.ankuendigung == ":" and bool(t.zwischen))
                for s2, e2, umbruch in folgewerte(text, t.ende, WERT_RE[form], ende, zuordnung):
                    w2 = text[s2:e2]
                    if pruefen(w2, umbruch or _versalien_kontext(text, s2, e2, m.start()), wortgestalt):
                        neu(form, s2, e2, m, 0.85)
                continue
        if mehrzahl(m.group(0)):
            # Titelzeile über einer Liste ("eVB-Nummern Ihres Fuhrparks" ⏎ "M-AB 123 ⇥⇥ VW Golf ⇥⇥ K7H3M9P"):
            # Werte mit Ziffer in den Zeilen darunter
            for s2, e2 in blockwerte(text, m.end(), WERT_RE[form], ende):
                if any(c.isdigit() for c in text[s2:e2]) and pruefen(text[s2:e2], True, wortgestalt):
                    neu(form, s2, e2, m, 0.8)
        if allgemein and t is None:
            _allgemein(text, m, ende, neu)
        if ocr and form == "evb":
            # Einfügungen der Texterkennung ("K7/H3MY9P", "K7H3MJ9P"); die genaue Form prüft der Weg oben
            r = wert_hinter_etikett(text, m.end(), EVB_RAUSCH_RE, grenze=ende, ist_etikett=ist_etikett)
            if r is not None and "\t\t" not in text[m.end():r.start]:
                wert = text[r.start:r.ende]
                if (wert != re.sub(r"[/|]", "", wert) or len(wert) != 7) and evb_rauschen_gueltig(wert):
                    neu("evb", r.start, r.ende, m, 0.6, True)
    # Kartendaten ohne Etikett: Kartennummer (Luhn) bzw. ihr Platzhalter, Ablaufdatum, Kartenprüfnummer am Ende
    anker = []
    for k in _KARTENNUMMER_RE.finditer(text, start, ende):
        e = _luhn_ende(text, k.start(), k.end())
        if e is not None:
            anker.append((k, e))
    if kartenbezug_extra is not None:
        anker += [(k, k.end()) for k in kartenbezug_extra.finditer(text, start, ende)]
    for k, e in anker:
        f = _kartenfolge(text, e, ende)
        if f is not None:
            neu("cvc", f[0], f[1], k, 0.75)
    aus.sort(key=lambda f: (f.start, f.ende))
    return aus


# ----------------------------------------------------------------------
# Geburtsname
# ----------------------------------------------------------------------
def _wissen_frage(name: str, wort: str) -> bool:
    try:
        from . import wissen
        return bool(getattr(wissen, name)(wort))
    except Exception:  # pragma: no cover - Wissensbasis fehlt
        return False


def _titelform(wort: str) -> str:
    return wort.title() if wort.isupper() else wort


def feld_etikett(text: str, s: int, e: int, ist_etikett=wissen_etikett) -> bool:
    """Ist text[s:e] selbst ein Feld-Etikett – ein Doppelpunkt dahinter (auch hinter einer Klammer: "PLZ (Wohnort):",
    hinter einer Ergänzung mit Funktionswort: "Art der Versicherung:" oder hinter einem weiteren Wort derselben Zeile:
    "Abweichender Halter:", "Versichert seit:") oder ein Etikett der Wissensbasis ("PLZ", "Postleitzahl", "Status")?
    Hinter einem leeren Feld "Geburtsname:" steht oft das nächste Feld, nie ein Geburtsname."""
    if re.match(r"[ \t]*(?:\([^()\n]{0,40}\))?[ \t]*:", text[e:e + 50]) or _ERGAENZUNG_RE.match(text[e:e + 90]) \
            or _ETIKETT_PHRASE_RE.match(text[e:e + 70]):
        return True
    wort = text[s:e]
    try:
        return bool(ist_etikett is not None and (ist_etikett(wort) or ist_etikett(_titelform(wort))))
    except Exception:
        return False


_ERGAENZUNG_RE = re.compile(r"[ \t]+(?i:der|des|die|dem|den|vom|zur|zum|für|im|am|bei)[ \t]+[^\s:()]{2,30}"
                            r"(?:[ \t]+[^\s:()]{2,30})?[ \t]*(?:\([^()\n]{0,40}\))?[ \t]*:")
# ein Etikett aus zwei oder drei Wörtern: "Abweichender Halter:", "Versichert seit:", "Akad. Titel:" (Zeilenende
# dahinter)
_ETIKETT_PHRASE_RE = re.compile(r"\.?[ ]+[^\s:()]{2,30}(?:[ ]+[^\s:()]{2,30})?[ \t]*:[ \t]*(?:\n|\t\t|$)")


def _ankuendigung_folgt(text: str, i: int) -> bool:
    """Folgt hinter i in derselben Zeile und Zelle eine Ankündigung (":", "lautet", "ist")?"""
    zeile = re.match(r"[^\n]{0,100}", text[i:]).group(0).split("\t\t")[0]
    return ":" in zeile or _ANKUENDIGUNG_RE.search(zeile) is not None


def kopfzeile(text: str, s: int, ist_etikett=wissen_etikett) -> bool:
    """Steht das Etikett bei s in der Kopfzeile einer Tabelle – ist die Zelle davor selbst ein Etikett ("Person ⇥⇥
    Geburtsname ⇥⇥ Status")?"""
    zeilenanfang = text.rfind("\n", 0, s) + 1
    davor = text[zeilenanfang:s]
    if "\t\t" not in davor:
        return False
    zellen = [z.strip() for z in davor.split("\t\t")]
    vorige = next((z for z in reversed(zellen[:-1]) if z), "") if not zellen[-1] else ""
    if not vorige or ist_etikett is None:
        return False
    try:
        return bool(ist_etikett(vorige.rstrip(":")))
    except Exception:
        return False


def geburtsname_moeglich(text: str, s: int, e: int, frage=None, ort_erlaubt: bool = False) -> bool:
    """Kann das Wort text[s:e] hinter "geb." oder "Geburtsname" ein (Geburts-)Name sein? Nicht: ein Funktionswort ("geb.
    In Köln", "GEB. IN KÖLN", "geb. Laut Urkunde", "Erste"), eine Abkürzung mit Punkt ("geb. Lt. Ausweis"), ein Wort aus
    zwei Buchstaben, das kein Nachname der Wissensbasis ist, ein Kürzel aus drei Großbuchstaben ("GEB. KFZ"), ein
    Feld-Etikett oder Sachwort (sachwort: "GEB. STATUS", "GEB. HAUPTVERSICHERTER", "Geburtsname ist Pflichtangabe"), ein
    Ort aus mehreren Wörtern ("Bad Homburg", "St. Ingbert") und eine deutsche Großstadt ("Hamburg": der Geburtsort) –
    außer sie ist zugleich ein Nachname ("Hagen", "Essen"). Ein anderer Ort ("Linz", "Polen") kann Geburtsname oder
    Geburtsort sein: hinter "geb." nur mit ort_erlaubt (die Selbstkontrolle meldet ihn), hinter einem Geburtsnamen-
    Etikett ja. Die Einwohnerbezeichnung eines Orts ("Mainzer", "Danziger", "Linzer") ist hier ein Herkunftsname, also
    ein Name (Gegenprüfung 4d) – das Eigenschaftswort ("eine geborene Kölnerin") schließt der Zusammenhang aus.
    frage(name, wort): Frage an die Wissensbasis (ist_nachname, ist_ort, ist_grossstadt; Standard das Modul wissen)."""
    frage = frage or _wissen_frage
    wort = text[s:e].strip()
    teile = wort.split()
    if not teile:
        return False
    kern = teile[-1]
    buchstaben = sum(c.isalpha() for c in kern)
    k = _titelform(kern)
    nachname = frage("ist_nachname", k)
    if ist_funktionswort(kern) and not nachname:
        return False
    if text[e:e + 1] == "." and buchstaben <= 3 and not nachname:
        return False                                    # "Lt.", "St.", "Bd.": Abkürzung
    if buchstaben <= 2 and not nachname:
        return False
    if nachname:
        return True
    if (kern.isupper() and buchstaben <= 3) or sachwort(k):
        return False                                    # "GEB. KFZ", "GEB. STATUS", "Geburtsname ist Pflichtangabe"
    naechstes = re.match(r"[ \t]+([A-ZÄÖÜ][\wäöüß\-]+)", text[e:e + 40])
    if naechstes is not None and frage("ist_ort", k + " " + _titelform(naechstes.group(1))):
        return False                                    # "Bad Homburg", "Frankfurt am Main" (erstes Wort)
    if frage("ist_grossstadt", k):
        return False                                    # "Anna Weber geb. Hamburg": der Geburtsort
    return ort_erlaubt or not frage("ist_ort", k)


def geburtsname_ort(text: str, s: int, e: int, frage=None) -> bool:
    """Ist das Wort hinter "geb." ein Ort, der auch Geburtsname sein kann ("Anna Weber geb. Linz")? Dann wird es nicht
    geschwärzt, aber gemeldet (geburtsname_moeglich mit ort_erlaubt)."""
    frage = frage or _wissen_frage
    kern = _titelform((text[s:e].split() or [""])[-1])
    return bool(kern) and frage("ist_ort", kern) and geburtsname_moeglich(text, s, e, frage, ort_erlaubt=True)


def _etikett_mit_wert(text: str, e: int, ist_etikett) -> bool:
    """Steht hinter dem Wort (Ende e) in derselben Zeile eine weitere Zelle, die selbst kein Etikett ist ("Geburtsland
    ⇥⇥ Polen", "Sport ⇥⇥ Tennis")? Dann ist das Wort das Etikett dieser Zelle – Etiketten und Werte wechseln sich in
    einer Formularzeile ab; hinter einem Wert steht das nächste Etikett ("Quarnstedt ⇥⇥ Geburtsdatum ⇥⇥ …")."""
    m = re.match(r"[ ]*\t\t[ \t]*([^\t\n]+)", text[e:e + 120])
    if m is None:
        return False
    zelle = m.group(1).strip()
    if not zelle or zelle.endswith(":") or zelle[:1].isdigit() or _SACH_KOPF_RE.match(zelle.split()[0]) \
            or zelle.split()[0].casefold() in _KOPFWOERTER:
        return False                                    # Etikett ("Geburtsdatum"), Datum oder Nummer: ein Wert davor
    try:
        return not (ist_etikett is not None and (ist_etikett(zelle) or ist_etikett(zelle.split()[0])))
    except Exception:
        return False


class Geburtsnamenfund(NamedTuple):
    start: int
    ende: int
    getrennt: bool          # in der Zeile darunter oder der Zelle daneben (nicht hinter Doppelpunkt/Ankündigung)
    person: tuple | None = None  # (start, ende) des Namens derselben Person ("Weber (Quarnstedt)": "Weber")


def _rest_der_zelle(text: str, e: int) -> tuple:
    """(Anfang, Ende) des Texts hinter e bis zum Ende seiner Zelle bzw. Zeile, ohne Leerraum am Rand."""
    ende = len(text)
    for trenner in ("\n", "\t\t"):
        i = text.find(trenner, e)
        if 0 <= i < ende:
            ende = i
    while e < ende and text[e] in " \t":
        e += 1
    while ende > e and text[ende - 1] in " \t":
        ende -= 1
    return e, ende


# "Familienname (Geburtsname): Weber (Quarnstedt)", "Name, Vorname (ggf. Geburtsname): Weber, Anna (Quarnstedt)":
# das Etikett steht in der Klammer eines anderen Etiketts – sein Wert ist die Klammer des Werts
_KLAMMER_DAVOR_RE = re.compile(r"\([^()\n]{0,30}$")
_KLAMMER_WERT_RE = re.compile(r"[^()\n:]{0,30}\)[ \t]*:[ \t]*(?P<person>[^()\n:]{1,60}?)[ \t]*\([ \t]*")
_PERSON_VOR_KLAMMER_RE = re.compile(r"[" + _GROSS + r"][\wäöüß'’\-]+(?:,?[ ]+[" + _GROSS + r"][\wäöüß'’\-]+){0,3}")


def _geburtsname_in_klammer(text: str, m: re.Match, name_re: re.Pattern, ist_etikett, frage):
    """(start, ende, Person) des Geburtsnamens in der Klammer des Werts, wenn das Etikett m selbst in der Klammer
    eines Etiketts steht ("Familienname (Geburtsname): Weber (Quarnstedt)") – sonst None; "" ohne Namen in der
    Wertklammer. Person: (start, ende) des Namens vor der Klammer ("Weber", "Weber, Anna") oder None."""
    if not _KLAMMER_DAVOR_RE.search(text, max(0, m.start() - 31), m.start()):
        return None
    k = _KLAMMER_WERT_RE.match(text, m.end())
    if k is None:
        return ""
    n = name_re.match(text, k.end())
    if n is None or not re.match(r"[ \t]*\)", text[n.end():n.end() + 4]) \
            or feld_etikett(text, n.start(), n.end(), ist_etikett) \
            or not geburtsname_moeglich(text, n.start(), n.end(), frage, ort_erlaubt=True):
        return ""
    p = _PERSON_VOR_KLAMMER_RE.fullmatch(k.group("person"))
    return n.start(), n.end(), (k.start("person"), k.end("person")) if p is not None else None


def geburtsname_hinter_etikett(text: str, m: re.Match, name_re: re.Pattern = NAME_RE, ist_etikett=wissen_etikett,
                               frage=None) -> Geburtsnamenfund | None:
    """Name hinter einem Geburtsnamen-Etikett m (GEBURTSNAME_ETIKETT_RE) nach der Regel „Etikett + Wert“ – direkt
    dahinter, in der Zelle daneben ("Geb.-Name ⇥⇥ Quarnstedt"), hinter Zwischenwörtern bis zu einer Ankündigung
    ("Geburtsname, falls abweichend: …", "Geburtsname (falls vom Familiennamen abweichend): …", "Ihr Geburtsname
    lautet …") – oder None. Nicht: das nächste Feld-Etikett hinter einem leeren Feld ("Geburtsname:" ⏎ "PLZ, Ort: …",
    feld_etikett), ein Wort in der Zeile unter einem Satz ("… den Geburtsname" ⏎ "Ihnen ist bekannt"), die nächste
    Zelle einer Kopfzeile ("Person ⇥⇥ Geburtsname ⇥⇥ Status") und kein Nicht-Name (geburtsname_moeglich). Steht der
    Name getrennt vom Etikett (Zeile darunter, Zelle daneben), ist er seine ganze Zelle: kein Spaltenkopf, kein
    Allerweltswort, kein Teil eines Feld-Etiketts ("Früherer Name", "Vorherige Anschrift:", "Akad. Grad"). Steht
    das Etikett in der Klammer eines anderen ("Familienname (Geburtsname): Weber (Quarnstedt)"), ist der Name in der
    Klammer des Werts gemeint – ohne sie keiner (der Wert davor gehört zum anderen Etikett)."""
    klammer = _geburtsname_in_klammer(text, m, name_re, ist_etikett, frage)
    if klammer is not None:
        return Geburtsnamenfund(klammer[0], klammer[1], False, klammer[2]) if klammer else None

    def zwischenwort(s, e, umbruch):
        # Teil des Etiketts statt Name: "GEBURTSNAME, FALLS ABWEICHEND: …", "Geburtsname Mutter: …", "GEBURTSNAME
        # ABWEICHEND: …", "GEBURTSNAME DER VERSICHERTEN PERSON: …" – aber nicht das nächste Feld hinter einem leeren
        # ("Geburtsname: Status: ledig") und nicht "Geburtsname zur Mühlen"
        if feld_etikett(text, s, e, ist_etikett):
            return not re.search(r"[:\n]|\t\t", text[m.end():s])
        teile = text[s:e].split()
        if ist_funktionswort(teile[0]):
            return len(teile) == 1 or (_ankuendigung_folgt(text, e)
                                       and not (frage or _wissen_frage)("ist_nachname", _titelform(teile[-1])))
        return not geburtsname_moeglich(text, s, e, frage, ort_erlaubt=True)

    t = wert_hinter_etikett(text, m.end(), name_re, ist_etikett=ist_etikett, zwischenwort=zwischenwort)
    if t is None:
        return None
    getrennt = t.darunter or (t.zelle and t.ankuendigung in ("", "zelle"))
    if t.darunter and not etikett_zeile(text, m.start(), m.end()):
        return None
    if t.zelle and kopfzeile(text, m.start(), ist_etikett):
        return None
    if feld_etikett(text, t.start, t.ende, ist_etikett) \
            or not geburtsname_moeglich(text, t.start, t.ende, frage, ort_erlaubt=True):
        return None
    if getrennt:
        frage = frage or _wissen_frage
        kern = _titelform(text[t.start:t.ende].split()[-1])
        nachname = frage("ist_nachname", kern)
        if kern.casefold() in _KOPFWOERTER or (frage("ist_allerweltswort", kern) and not nachname):
            return None                                 # "Geburtsname ⇥⇥ Status", "Geburtsname:" ⏎ "Art"
        if _etikett_mit_wert(text, t.ende, ist_etikett):
            return None                                 # "Geb.-Name ⇥⇥ Geburtsland ⇥⇥ Polen": das nächste Feld
        rs, re_ = _rest_der_zelle(text, t.ende)
        rest = text[rs:re_]
        if rest:
            erstes = re.match(r"[^\s:,;()]+", rest)
            if (rest.endswith(":") or rest[:1] in ".:" or rest[:1].islower()
                    or (erstes is not None and feld_etikett(text, rs, rs + erstes.end(), ist_etikett))):
                return None                             # "Früherer Name", "Vorherige Anschrift:", "Akad. Grad"
    return Geburtsnamenfund(t.start, t.ende, getrennt)


# Trenner zwischen mehreren Namen derselben Zelle: Komma, Schrägstrich, Semikolon, "und", "u.", "bzw.", "sowie"
_NAMEN_TRENNER_RE = re.compile(r"[ ]*[,/;][ ]*(?:(?:und|u\.|bzw\.)[ ]+)?|[ ]+(?:und|u\.|bzw\.|sowie)[ ]+")


def weitere_geburtsnamen(text: str, m: re.Match, ende: int, getrennt: bool, name_re: re.Pattern = NAME_RE,
                         ist_etikett=wissen_etikett, frage=None, verlaengern=None) -> list:
    """Weitere Namen hinter dem ersten (Ende `ende`), wenn das Etikett m in der Mehrzahl steht ("Geburtsnamen:
    Quarnstedt, Ellerbrok", "Geburtsnamen der Eltern: Quarnstedt und Ellerbrok"): je ein Geburtsnamenfund, solange
    hinter einem Trenner derselben Zelle ein möglicher Name steht – kein Feld-Etikett ("…, Geburtsort: Linz"), kein
    Nicht-Name (geburtsname_moeglich); die Folge endet am ersten anderen Wort. Höchstens fünf. verlaengern(s, e):
    Ende eines mehrteiligen Namens ("Garcia Lopez") oder None für ein Wort, das hier kein Name ist (eigene Prüfung
    des Aufrufers); ohne verlaengern das Ende des Treffers von name_re."""
    if not _GEBURTSNAMEN_MEHRZAHL_RE.fullmatch(m.group(0)):
        return []
    aus = []
    while len(aus) < 5:
        t = _NAMEN_TRENNER_RE.match(text, ende)
        n = name_re.match(text, t.end()) if t is not None else None
        if n is None or feld_etikett(text, n.start(), n.end(), ist_etikett) \
                or not geburtsname_moeglich(text, n.start(), n.end(), frage, ort_erlaubt=True):
            break
        ende = verlaengern(n.start(), n.end()) if verlaengern is not None else n.end()
        if ende is None:
            break
        aus.append(Geburtsnamenfund(n.start(), ende, getrennt))
    return aus


# ======================================================================
# Allgemeine Kennungen (Runde 5): die Regel „Etikett + Wert“ für JEDES Kennungs-Etikett
# ======================================================================
# Die Domänen-Durchsicht aller Maklersparten fand dieselbe Lücke in vielen Formen: zwischen einem bekannten
# Kennungs-Etikett und seinem Wert stehen Zwischenwörter ("Personalnummer beim Arbeitgeber: 4711", "Vertragsnummer
# beim Vorversicherer: …", "Führerschein Klasse 3 vom 12.04.1985, Nr. 355/85"), der Wert hat eine Form, die die
# Wertregel nicht kannte (Tausenderpunkt-Gruppen "4.711.208", Codes mit wenigen Ziffern "TLX-KQ8B-ZR3M", "#A-4711",
# Laufnummer "IMEI 1: …"), oder das Etikett hatte eine Form, die die Etikettregel nicht kannte ("BG-Nummer",
# "Vorg.-Nr.", "Nummer der Bedarfsgemeinschaft", "HKP Nr."). Erkennung (detektoren/struktur*.py, muster.py) und
# Selbstkontrolle (restrisiko.py) lesen die Etiketten, Wertformen und die Brücke über Zwischenwörter hier.
MAX_ZWISCHEN_KENNUNG = 8          # so viele Zwischenwörter zwischen einem Kennungs-Etikett und der Ankündigung
OHNE_ANKUENDIGUNG_KENNUNG = 3     # … ohne Ankündigung: eine Ergänzung mit Artikel/Präposition ("der Karte")

# -- Wertform einer Kennung (Erkennung und Selbstkontrolle) -------------------------------------------------------
KENNUNG_TOKEN_RE = re.compile(r"[A-Za-zÄÖÜäöü0-9][A-Za-zÄÖÜäöüß0-9\-./]*")
BETRAG_RE = re.compile(r"[-+]?\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|[-+]?\d+,\d{1,2}|[-+]?\d{1,3}(?:'\d{3})+")
DATUM_VOLL_RE = re.compile(r"\d{1,2}\.\d{1,2}\.(?:\d{4}|\d{2})|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/(?:\d{4}|\d{2})|"
                           r"\d{1,2}\.\d{4}|\d{2}/\d{4}")
# Kürzel in Großbuchstaben, die nie Teil einer Kennung sind (Währungen, Einheiten, Rechtsformen, Funktionswörter) –
# nicht "AB": vor einer Zifferngruppe ist es das Kürzel eines Dokuments ("Fahrzeugschein Nr. AB 1234567"), vor einem
# Datum endet der Wert ohnehin (ein Kürzel am Ende zählt nicht)
KENNUNG_SPERRE = frozenset({"EUR", "USD", "CHF", "GBP", "IBAN", "BIC", "BLZ", "NR", "TEL", "FAX", "UHR", "KM", "AG",
                            "KG", "SE", "GMBH", "VVG", "SGB", "BGB", "AVB", "PS", "KW", "CM", "MM", "QM", "ST", "STK",
                            "MIO", "MRD", "TSD", "CO", "BZW", "UND", "VON", "VOM", "BIS", "AM", "IM", "IN", "ZU",
                            "DE", "DM", "PDF", "ID", "NO", "ABS", "NRN", "SEITE"})
# Tausenderpunkt-Gruppen ohne Dezimalkomma, mindestens zwei Gruppen ("4.711.208", "123.456.789"): hinter einem
# Nummer-Etikett eine Kennung, kein Betrag (Domänen-Befunde 1, 67) – nie mit Währung oder Einheit dahinter
PUNKTE_RE = re.compile(r"\d{1,3}(?:\.\d{3}){2,}")
# Registerzeichen in Aktenzeichen von Gerichten und Staatsanwaltschaften ("12 Js 345/23", "3 Ca 123/24")
REGISTERZEICHEN = frozenset({"Js", "UJs", "Ds", "Cs", "Ls", "KLs", "Gs", "Ks", "Ns", "Qs", "Ss", "Ws", "Bs", "Hs",
                             "AR", "VRs", "BRs", "Ca", "Sa", "Ta", "OWi", "StR", "ZR", "ZB"})
# Gliederungs- und Versionsnummern ("3.2.1", "4.2"): Gruppen aus höchstens zwei Ziffern – keine Kennung
_VERSION_RE = re.compile(r"\d{1,2}(?:\.\d{1,2}){1,3}")
# Normen ("DIN EN ISO 9001", "VDE 0100") sind keine Kennung einer Person
_NORM_RE = re.compile(r"(?:DIN|EN|ISO|IEC|VDE|ÖNORM|DVGW|VdS)(?![\w])")
# Verweis auf eine Vorschrift ("§ 34d Abs. 1 GewO") – auch so, wie die Texterkennung das Paragrafenzeichen verliest
# ("8 34d Abs. 1 GewO", "S 34d GewO"): ein Absatz bzw. Gesetz direkt dahinter oder "§"/"Art." direkt davor. Kein Wert
# hinter einem Etikett, wenn der eigentliche Wert fehlt oder schon ersetzt ist ("Registrierungsnummer: ███ 8 34d Abs.
# 1 GewO" auf einem Scan)
_VORSCHRIFT_TEIL = (r"(?:Abs\.|Absatz(?![\w-])|(?:GewO|BGB|HGB|VVG|VAG|SGB|ZPO|StGB|StPO|EStG|UStG|BDSG|DSGVO|PflVG|"
                    r"StVG|StVO|FZV|GwG|KWG|ZAG|RDG|BetrAVG|VersVermV)(?![\w-]))")
_VORSCHRIFT_DANACH_RE = re.compile(r"[ \t]*" + _VORSCHRIFT_TEIL)
_VORSCHRIFT_IM_WERT_RE = re.compile(r"(?<![\w])" + _VORSCHRIFT_TEIL)
_VORSCHRIFT_DAVOR_RE = re.compile(r"(?:§§?|(?<![\w])Art\.|(?<![\w])Artikel)[ \t]*$")


def ist_betrag(tok: str) -> bool:
    return bool(BETRAG_RE.fullmatch(tok))


def ist_datum_text(tok: str) -> bool:
    return bool(DATUM_VOLL_RE.fullmatch(tok))


def kennung_token(tok: str, erstes: bool, naechstes: str = "", punkte: bool = False) -> bool:
    """Gehört das Token zu einer Kennung: mit Ziffer (kein Betrag, kein Datum, kein Prozent – mit `punkte` auch eine
    Tausenderpunkt-Gruppe), ein Kürzel aus Großbuchstaben, ein Registerzeichen vor einer Zifferngruppe ("12 Js 345/23")
    oder ein einzelner Großbuchstabe zwischen Zifferngruppen ("03 241061 C 515")?"""
    if not tok:
        return False
    if len(tok) == 1 and tok.isalpha():
        return tok.isupper() and any(c.isdigit() for c in naechstes)
    if any(c.isdigit() for c in tok):
        if punkte and PUNKTE_RE.fullmatch(tok):
            return True
        if ist_betrag(tok) or ist_datum_text(tok):
            return False
        return not tok.endswith("%")
    if tok in REGISTERZEICHEN and any(c.isdigit() for c in naechstes):
        return True
    if not tok.isalpha():
        # Buchstaben mit Trennern, aber ohne Ziffer ("KH-AB"): nur als Präfix
        teile = [t for t in re.split(r"[-./]", tok) if t]
        return bool(teile) and all(t.isupper() and len(t) <= 4 for t in teile) and erstes
    return tok.isupper() and len(tok) <= 4 and tok not in KENNUNG_SPERRE


def kennung_spanne(text: str, pos: int, grenze: int, min_ziffern: int = 3, punkte: bool = False):
    """Kennung ab pos (führender Leerraum wird übersprungen): Folge von Tokens mit Ziffern bzw. kurzen
    Großbuchstaben-Kürzeln ("KH 0815 4471 2", "LV/24/4058468", "D-Y3TV-NW64X-52", "7 111 562 795", "12 Js 345/23"),
    durch einfache Leerzeichen getrennt. Endet an Wort, Satzzeichen, Tabulator, Zeilenende. Keine Daten, Beträge,
    Jahreszahlen – mit `punkte` (hinter einem Nummer-Etikett) aber Tausenderpunkt-Gruppen ("4.711.208"). Liefert
    (start, ende) oder None."""
    i = pos
    while i < grenze and text[i] in " \t":
        i += 1
    tokens = []
    j = i
    while j < grenze:
        m = KENNUNG_TOKEN_RE.match(text, j, grenze)
        if not m:
            break
        roh = m.group(0)
        kern = roh.rstrip(".-/")
        if punkte and PUNKTE_RE.match(roh) and PUNKTE_RE.fullmatch(roh.rstrip(".")):
            kern = roh.rstrip(".")
        n = KENNUNG_TOKEN_RE.match(text, m.end() + 1, grenze) if m.end() < grenze and text[m.end()] == " " else None
        if not kennung_token(kern, not tokens, n.group(0) if n else "", punkte):
            break
        tokens.append((m.start(), m.start() + len(kern)))
        j = m.end()
        if len(kern) != len(roh):
            break                                   # Satzzeichen am Ende beendet den Wert
        if j + 1 < grenze and text[j] == " " and text[j + 1] not in " \t\n":
            j += 1
            continue
        break
    while tokens and not any(c.isdigit() for c in text[tokens[-1][0]:tokens[-1][1]]):
        tokens.pop()
    if not tokens:
        return None
    s, e = tokens[0][0], tokens[-1][1]
    wert = text[s:e]
    ziffern = sum(c.isdigit() for c in wert)
    if ziffern < min_ziffern or len(wert) < 4:
        return None
    kompakt = wert.replace(" ", "")
    if kompakt.isdigit() and len(kompakt) == 4 and kompakt[:2] in ("19", "20"):
        return None                                 # Jahreszahl
    if ist_datum_text(kompakt) or (ist_betrag(wert) and not (punkte and PUNKTE_RE.fullmatch(wert))):
        return None
    return s, e


# Code mit Trennern und wenigen Ziffern ("TLX-KQ8B-ZR3M", "QX-7RT2-MKP"): mindestens zwei Gruppen aus
# Großbuchstaben/Ziffern, zusammen mindestens sechs Zeichen, mit Buchstaben und Ziffer (Domänen-Befund 27)
_CODE_RE = re.compile(r"(?<![\w\-/.])[A-Z0-9]{1,8}(?:-[A-Z0-9]{1,8}){1,5}(?![\w]|[-/.][A-Za-z0-9])")


def code_spanne(text: str, pos: int, grenze: int):
    """(start, ende) eines Codes mit Trennern ab pos (siehe _CODE_RE) oder None – kein Datum, kein Zeitraum, keine
    Telefonnummer."""
    m = _CODE_RE.match(text, pos, grenze)
    if m is None:
        return None
    w = m.group(0)
    kern = w.replace("-", "")
    if len(kern) < 6 or not any(c.isdigit() for c in kern) or sum(c.isalpha() for c in kern) < 2:
        return None
    if _TELEFON_FORM_RE.fullmatch(w) or zeitraum(w) or _DATUM_RE.fullmatch(w):
        return None
    return m.start(), m.end()


# Etiketten, hinter denen ein Saldo steht, keine Nummer ("Darlehenskonto: 1.500.000", "Beitragskonto"): dort ist
# eine Tausenderpunkt-Gruppe ein Betrag
_SALDO_ETIKETT_RE = re.compile(r"(?i)(?:konto|kontos|summe|betrag|saldo|guthaben|wert|preis|beitrag|kosten)[ \t.:]*$")
# Ausweis-Wörter ohne Nummer-Wort ("Reisepass CF9JKRTN7", "Führerschein: N1907WW3L41"): direkt dahinter nur die Form
# einer amtlichen Dokumentnummer (8 bis 11 Großbuchstaben/Ziffern mit Buchstabe und mindestens zwei Ziffern); hinter
# "Nr."/"Nummer" jede Kennung ("Führerschein Klasse 3 vom 12.04.1985, Nr. 355/85")
_AUSWEIS_WORT_RE = re.compile(r"(?i)^(?:personal)?ausweis(?:es)?$|^(?:reise)?pass(?:es)?$"
                              r"|^f(?:ü|ue)hrerschein(?:s|es)?$|^aufenthaltstitel(?:s)?$|^ausweisdokument(?:s|es)?$")
_DOKUMENTNUMMER_RE = re.compile(r"(?<![\w\-/.])(?=[A-Z0-9]*\d[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{8,11}"
                                r"(?![\w]|[-/.]\w)")


# Feldverweis der Zulassungsbescheinigung hinter "Schlüsselnummer"/"Schlüssel-Nr." ("2.1/2.2", "zu 2.1", "(zu 2.2)"):
# Hersteller- und Typschlüssel (HSN/TSN) beschreiben den Fahrzeugtyp, keine Person (Domänen-Befund 47) – die Nummer
# eines Fahrzeugschlüssels ("Schlüsselnummer des Ersatzschlüssels: …") bleibt eine Kennung
_FELDVERWEIS_RE = re.compile(r"[ \t]*\(?[ \t]*(?:zu[ \t]+)?2\.[12](?:[ \t]*/[ \t]*2\.[12])?[ \t]*\)?")
_SCHLUESSEL_ETIKETT_RE = re.compile(r"(?i)schl(?:ü|ue|u)ssel")


def fahrzeugschluessel(text: str, etikett: str, e: int) -> bool:
    """Steht hinter dem Schlüssel-Etikett (Ende e) ein Feldverweis der Zulassungsbescheinigung ("Schlüssel-Nr.
    2.1/2.2: 0005/CXY", "Schlüsselnummer zu 2.2: 123")? Dann ist der Wert ein Fahrzeugschlüssel, keine Kennung."""
    return bool(_SCHLUESSEL_ETIKETT_RE.search(etikett or "")) and bool(_FELDVERWEIS_RE.match(text, e)) \
        and bool(re.match(r"[ \t]*\(?[ \t]*(?:zu[ \t]+)?\d", text[e:e + 12]))


def punkte_erlaubt(etikett: str) -> bool:
    """Ist hinter dem Etikett eine Tausenderpunkt-Gruppe eine Kennung ("Kundennummer: 4.711.208") – nicht hinter
    einem Saldo-Etikett ("Darlehenskonto: 1.500.000")?"""
    return not _SALDO_ETIKETT_RE.search((etikett or "").strip())


# Buchungscodes einer Reise (Filekey, Buchungsreferenz, Buchungsnummer, Reservierungscode, PNR, Booking reference,
# Record locator): 5 bis 8 Großbuchstaben/Ziffern, auch ganz ohne Ziffer ("KXQRZN") – kein Wort ("STORNO", "OFFEN",
# "PENDING": wissen.ist_wortgestalt), keine Ziffernfolge allein (die liest kennung_spanne), Domänen-Befund 7
_BUCHUNG_ETIKETT_RE = re.compile(r"(?i)buchung|booking|reservierung|reservation|file[ -]?key|\bpnr\b|locator")
_BUCHUNGSCODE_RE = re.compile(r"(?<![\w\-/.])[A-Z0-9]{5,8}(?![\w]|[-/.][A-Za-z0-9])")


def buchungscode(text: str, i: int, grenze: int, etikett: str):
    """(start, ende) eines Buchungscodes ab i hinter einem Buchungs-Etikett (_BUCHUNG_ETIKETT_RE) oder None."""
    if not _BUCHUNG_ETIKETT_RE.search(etikett or ""):
        return None
    m = _BUCHUNGSCODE_RE.match(text, i, grenze)
    if m is None or m.group(0).isdigit() or _wortartig(m.group(0), None):
        return None
    return m.start(), m.end()


def ausweis_wort(etikett: str) -> bool:
    """Ist das Etikett ein Ausweis-Wort ohne Nummer-Wort ("Reisepass", "Personalausweises", "Führerschein")?"""
    return bool(_AUSWEIS_WORT_RE.match(" ".join((etikett or "").split()).strip(" .:")))


def kennungswert(text: str, pos: int, grenze: int, etikett: str = "", streng: bool = False, nr: bool = False):
    """(start, ende) der Kennung ab pos hinter dem Kennungs-Etikett `etikett` – oder None. Wertform: kennung_spanne
    (mindestens drei Ziffern; hinter einem Nummer-Etikett auch Tausenderpunkt-Gruppen ohne Währung/Einheit dahinter),
    sonst ein Code mit Trennern (code_spanne) und hinter einem Buchungs-Etikett ein Buchungscode (buchungscode: "PNR:
    KXQRZN"); ein "#" davor gehört zum Trenner ("Ticket #A-4711"). Hinter einem Ausweis-Wort ohne "Nr." (nr=False) nur
    die Form einer Dokumentnummer. Nie eine Gliederungs- oder Versionsnummer ("3.2.1") und keine Norm ("DIN EN ISO
    9001"). streng: ohne Trennzeichen zwischen Etikett und Wert gilt eine reine Ziffernfolge erst ab fünf Ziffern
    ("Konto 2024 abgeschlossen") – außer das Etikett endet auf ein Nummer-Wort, das den Wert selbst ankündigt
    ("Mdt.-Nr. 1024", "Hundemarke Nr. 1187")."""
    i = pos
    while i < grenze and text[i] in " \t":
        i += 1
    if i < grenze and text[i] == "#":
        i += 1
    if i >= grenze or _NORM_RE.match(text, i, grenze):
        return None
    if ausweis_wort(etikett) and not nr:
        m = _DOKUMENTNUMMER_RE.match(text, i, grenze)
        return (m.start(), m.end()) if m is not None else None
    punkte = punkte_erlaubt(etikett)
    sp = kennung_spanne(text, i, grenze, 3, punkte=punkte)
    if sp is not None:
        kompakt = text[sp[0]:sp[1]].replace(" ", "")
        if wert_ausgeschlossen(text, sp[0], sp[1]) or (streng and kompakt.isdigit() and len(kompakt) < 5
                                                         and not nummer_etikett(etikett)):
            return None
        return sp
    sp = code_spanne(text, i, grenze) or buchungscode(text, i, grenze, etikett)
    return None if sp is None or vorschrift(text, sp[0], sp[1]) else sp


def vorschrift(text: str, s: int, e: int) -> bool:
    """Ist text[s:e] die Nummer eines Paragrafen bzw. Artikels – "§"/"Art." direkt davor oder ein Absatz bzw. Gesetz
    direkt dahinter oder im Wert selbst ("8 34d Abs. 1 GewO", "S 34d GewO": das Paragrafenzeichen verlesen)?"""
    return bool(_VORSCHRIFT_DANACH_RE.match(text, e) or _VORSCHRIFT_IM_WERT_RE.search(text, s, e)
                or _VORSCHRIFT_DAVOR_RE.search(text, max(0, s - 10), s))


def wert_ausgeschlossen(text: str, s: int, e: int) -> bool:
    """Ist der Wert text[s:e] trotz Kennungsform keine Kennung – eine Gliederungs- oder Versionsnummer ("3.2.1"), eine
    Norm ("DIN EN ISO 9001"), die Nummer einer Vorschrift ("§ 34d", "8 34d Abs. 1 GewO") oder eine Zahl mit Währung
    bzw. Einheit dahinter ("4.711.208 EUR", "300 EUR Selbstbeteiligung")?"""
    wert = text[s:e]
    if _VERSION_RE.fullmatch(wert) or _NORM_RE.match(wert) or vorschrift(text, s, e):
        return True
    kompakt = wert.replace(" ", "")
    return (kompakt.replace(".", "").isdigit() or bool(PUNKTE_RE.fullmatch(wert))) \
        and bool(EINHEIT_DANACH_RE.match(text, e))


# Katalognummern ohne Personenbezug: die Pharmazentralnummer (PZN, sieben oder acht Ziffern) hinter "PZN" bzw.
# "Pharmazentralnummer" in derselben Zelle oder in der Spalte unter einem Kopf "PZN" – keine Telefonnummer und keine
# Kennung einer Person (Domänen-Befund 17: "PZN 04884569 Pantoprazol 20 mg", Apothekenquittung)
_PZN_ETIKETT_RE = re.compile(r"(?i)(?<![\w])(?:PZN|Pharmazentral(?:nummer|nr\.?))(?:[ \t.\-]*(?:Nr\.?|Nummer))?"
                             r"[ \t:.#]*$")
_PZN_WERT_RE = re.compile(r"0?\d{7}")
_KATALOG_ZEILEN = 30              # so weit nach oben wird der Spaltenkopf gesucht (Zeilen)


def katalognummer(text: str, s: int, e: int) -> bool:
    """Ist text[s:e] eine Pharmazentralnummer – hinter "PZN" in derselben Zelle ("PZN 04884569", "PZN-Nr.:
    01126111") oder als ganze Zelle in der Spalte unter dem Kopf "PZN" (Zellen durch Tabulatoren getrennt)?"""
    if not _PZN_WERT_RE.fullmatch(text[s:e].replace(" ", "")):
        return False
    zeilenanfang = text.rfind("\n", 0, s) + 1
    davor = text[zeilenanfang:s]
    if _PZN_ETIKETT_RE.search(davor.rsplit("\t", 1)[-1]):
        return True
    if davor.strip() and not davor.endswith("\t"):
        return False                                    # nur eine ganze Zelle steht unter einem Spaltenkopf
    spalte = len(re.split(r"\t+", davor)) - 1 if davor.strip() else 0
    oben = zeilenanfang - 1
    for _ in range(_KATALOG_ZEILEN):
        if oben <= 0:
            return False
        anfang = text.rfind("\n", 0, oben) + 1
        zeile = text[anfang:oben]
        if not zeile.strip():
            return False                                # Absatz: die Tabelle ist zu Ende
        zellen = re.split(r"\t+", zeile.strip())
        if spalte < len(zellen) and re.fullmatch(r"(?i)PZN(?:[ .\-]*(?:Nr\.?|Nummer))?:?|Pharmazentral(?:nummer|nr\.?)",
                                                  zellen[spalte].strip()):
            return True
        oben = anfang - 1
    return False


# -- Kennungen mit eigener Form ohne Etikett ----------------------------------------------------------------------
# MAC-Adresse eines Geräts: sechs Gruppen aus je zwei Hex-Zeichen mit ":" oder "-" ("3C:22:FB:9A:1B:7E"); mit "-" nur
# mit mindestens einem Buchstaben A-F (sonst eine gegliederte Zahl) – Uhrzeiten haben höchstens drei Gruppen
# (Domänen-Befund 56)
MAC_RE = re.compile(r"(?<![\w:\-])(?P<mac>[0-9A-Fa-f]{2}(?P<t>[:\-])(?:[0-9A-Fa-f]{2}(?P=t)){4}[0-9A-Fa-f]{2})"
                    r"(?![\w:\-])")
# EID einer eSIM: 32 Ziffern, beginnend mit 89 (Telekommunikation) – keine andere Zahl hat diese Länge
EID_RE = re.compile(r"(?<![\d.,])89\d{30}(?![\d.,])")
# Nummer im Marktstammdatenregister (MaStR): Kürzel der Art (Einheit SEE/SNE/SGE, Anlage EEG, Akteur ABR) und zwölf
# Ziffern ("SEE912345678901") – benennt die Anlage bzw. ihren Betreiber, bei einer privaten Photovoltaik-Anlage eine
# Person (Domänen-Befund 62)
MASTR_RE = re.compile(r"(?<![\w])(?:SEE|SNE|SGE|EEG|ABR)\d{12}(?![\w])")
# Aktenzeichen eines Gerichts oder einer Staatsanwaltschaft ohne Etikett: Zahl, Registerzeichen aus der geschlossenen
# Liste, Aktennummer/Jahr ("3 C 456/24", "210 Js 345/24", "14 S 2211/24", "VI ZR 123/24") – nur mit einem Gerichts-
# oder Verfahrenswort in derselben Zeile (Domänen-Befund 51); Normzitate ("§ 3 Abs. 2") und Tarifstufen ("300/150")
# haben kein Registerzeichen
_REGISTER_EINZELN = ("C", "O", "S", "U", "F", "T", "K", "L", "E", "W", "M")
AKTENZEICHEN_RE = re.compile(
    r"(?<![\w/.\-])(?:\d{1,4}|[IVX]{1,5})[ ](?:" + "|".join(sorted(set(REGISTERZEICHEN) | set(_REGISTER_EINZELN),
                                                                  key=len, reverse=True))
    + r")[ ]\d{1,6}/\d{2,4}(?![\w/]|[.\-]\d)")
_GERICHT_WORT_RE = re.compile(
    r"(?i)(?<![\wäöüß])(?:verfahren\w*|rechtsstreit\w*|rechtssache|sache|klage\w*|urteil\w*|beschluss\w*|"
    r"gericht\w*|amtsgericht\w*|landgericht\w*|oberlandesgericht\w*|arbeitsgericht\w*|sozialgericht\w*|"
    r"verwaltungsgericht\w*|staatsanwaltschaft\w*|ermittlungsverfahren\w*|strafsache|zivilsache|mahnverfahren|"
    r"az|aktenzeichen|geschäftszeichen|ag|lg|olg|bgh|stA|vergleich|termin|berufung|vollstreckung\w*)"
    r"(?![\wäöüß])")


def kennungen_ohne_etikett(text: str) -> list:
    """(start, ende, art) der Kennungen mit eigener, eindeutiger Form ohne Etikett: MAC-Adresse ("mac"), EID einer eSIM
    ("eid"), Nummer im Marktstammdatenregister ("mastr"), Aktenzeichen eines Gerichts oder einer Staatsanwaltschaft
    mit Gerichtswort in der Zeile ("aktenzeichen") und Angaben aus Grundbuch und Kataster ("grundbuch": Flurstück,
    Grundbuchblatt, Gemarkungsnummer)."""
    aus = []
    for m in MAC_RE.finditer(text):
        if m.group("t") == ":" or re.search(r"[A-Fa-f]", m.group("mac")):
            aus.append((m.start("mac"), m.end("mac"), "mac"))
    for m in EID_RE.finditer(text):
        aus.append((m.start(), m.end(), "eid"))
    for m in MASTR_RE.finditer(text):
        aus.append((m.start(), m.end(), "mastr"))
    for m in AKTENZEICHEN_RE.finditer(text):
        zeilenanfang = text.rfind("\n", 0, m.start()) + 1
        zeilenende = text.find("\n", m.end())
        zeile = text[zeilenanfang:zeilenende if zeilenende >= 0 else len(text)]
        if _GERICHT_WORT_RE.search(zeile):
            aus.append((m.start(), m.end(), "aktenzeichen"))
    aus += [(s, e, "grundbuch") for s, e in grundbuch(text)]
    return aus


# Einzelkaufmann (e.K., e.Kfm., e.Kfr.) bzw. Betrieb mit Inhaber: Handelsregisternummer (HRA) und USt-IdNr. sind dort
# Angaben einer natürlichen Person (Domänen-Befund 55) – nicht im Block einer Kapitalgesellschaft (GmbH, AG, SE, UG,
# KGaA, "GmbH & Co. KG", HRB) und nicht in einer Fußzeile mit Pflichtangaben ("Amtsgericht … · USt-IdNr. …")
_EINZELKAUFMANN_RE = re.compile(r"(?<![\w])(?:e\.[ ]?K(?:fm|fr)?\.|Inhaber(?:in)?[ \t]*:|Inh\.[ \t]*[A-ZÄÖÜ])")
_KAPITALGESELLSCHAFT_RE = re.compile(r"(?<![\w])(?:GmbH|gGmbH|mbH|AG(?![ \t]+[A-ZÄÖÜ][a-zäöü])|SE|UG|KGaA|eG|"
                                     r"e\.[ ]?V\.|VVaG|Ltd\.?|Inc\.|HR[ ]?B)(?![\w])")   # "AG Traunstein": Amtsgericht
_HRA_RE = re.compile(r"(?<![\w])HR[ ]?A[ ]?\d{1,6}(?:[ ]?[A-Z])?(?![\w])")
UST_ID_WERT_RE = re.compile(r"(?<![\w])DE[ \t]?\d{3}[ \t]?\d{3}[ \t]?\d{3}(?![\w])")
_BLOCK_ZEILEN = 8                 # so viele Zeilen um die Stelle gehören höchstens zu ihrem Angabenblock


def einzelkaufmann_block(text: str, pos: int) -> bool:
    """Steht pos im Angabenblock eines Einzelkaufmanns bzw. Betriebs mit Inhaber (Zeilen bis zur nächsten Leerzeile,
    höchstens _BLOCK_ZEILEN davor und danach): "e.K."/"Inhaber:" darin, keine Kapitalgesellschaft, und die Zeile ist
    keine Fußzeile mit Trennpunkten?"""
    zeilenanfang = text.rfind("\n", 0, pos) + 1
    zeilenende = text.find("\n", pos)
    zeilenende = len(text) if zeilenende < 0 else zeilenende
    if re.search(r"[·•|]", text[zeilenanfang:zeilenende]):
        return False
    a = zeilenanfang
    for _ in range(_BLOCK_ZEILEN):
        if a <= 0:
            break
        vor = text.rfind("\n", 0, a - 1) + 1
        if not text[vor:a - 1].strip():
            break
        a = vor
    b = zeilenende
    for _ in range(_BLOCK_ZEILEN):
        if b >= len(text):
            break
        nach = text.find("\n", b + 1)
        nach = len(text) if nach < 0 else nach
        if not text[b + 1:nach].strip():
            break
        b = nach
    block = text[a:b]
    return bool(_EINZELKAUFMANN_RE.search(block)) and not _KAPITALGESELLSCHAFT_RE.search(block)


def einzelkaufmann_erwaehnt(text: str) -> bool:
    """Nennt der Text einen Einzelkaufmann bzw. Inhaber ("e.K.", "e. Kfm.", "Inhaber:", "Inh. Name")? Vorprüfung
    vor einzelkaufmann_block, für Erkennung und Selbstkontrolle gleich."""
    return bool(_EINZELKAUFMANN_RE.search(text))


def einzelkaufmann_register(text: str) -> list:
    """(start, ende) der Handelsregisternummern (HRA) im Angabenblock eines Einzelkaufmanns (einzelkaufmann_block)."""
    if not einzelkaufmann_erwaehnt(text):
        return []
    return [(m.start(), m.end()) for m in _HRA_RE.finditer(text) if einzelkaufmann_block(text, m.start())]


# -- Etiketten ----------------------------------------------------------------------------------------------------
# Zusammengesetzte Nummern-Etiketten, die in keiner Liste stehen ("Bestandsnummer", "Mitglieds-ID", "BG-Nummer",
# "Vorg.-Nr.", "Ser.-Nr.", "Rahmen-Nummer") – auch mit Trenner vor "Nummer" und Punkt vor "-Nr."
NUMMERN_WORT_RE = re.compile(
    r"(?<![\w.\-])([A-ZÄÖÜa-zäöü][\wäöüß]*?(?:[-._][\wäöüßÄÖÜ]+)*?"
    r"(?:[-._]?(?:[Nn]ummer|NUMMER)|\.?[-_]?(?:[Nn]r\.?|NR\.?)|[-_](?:ID|Id)|[Kk]ennung|KENNUNG|[Kk]ennziffer))"
    r"(?![\w])")
# … deren Wert nicht zur Person gehört: Rufnummern, Anschrift, Kataloge (Artikel, Gebührenordnungen GOZ/GOÄ/EBM/BEL,
# Pharmazentralnummer PZN), Fahrzeugschlüssel (Hersteller-/Typschlüssel, HSN/TSN/KBA), Gliederung (Seite, Kapitel,
# Position, laufende Nummer), Produkt und Tarif. "kenn" nur für Kennzeichen/Kennziffer ("Kennnummer der Karte" ist eine
# Kennung), "geräte" nur für Gerätetyp/-art/-klasse ("Geräte-ID" ist eine), "post" nur für Postfach/Postleitzahl
# ("Postnummer" der Packstation ist eine)
NUMMERN_FREMD = re.compile(
    r"(?i)^(?:telefon|tel|fax|telefax|ruf|handy|mobil|mobilfunk|festnetz|haus|artikel|art|position|pos|seiten?|"
    r"version|tarif|produkt|bankleit|material|modell|typ|zimmer|raum|kapitel|absatz|paragraph|ziffer|zeilen?|"
    r"lfd|laufende|fortlaufende|kennz|bestell|best\.|serien|ger(?:ä|ae|a)te(?:typ|art|klasse)|z(?:ä|a)hler|"
    r"post(?:fach|leit|anschrift|eingang|ausgang)|hnr|nr|"
    r"(?:goz|go(?:ä|ae)|ebm|bel|beb|got|pzn|hsn|tsn|kba)(?![a-zäöüß])|geb(?:ühr|uehr|\.)|hersteller|service|hotline|"
    r"zentrale|notruf|info|flug|flight|gleis|sitzplatz|stellplatz|zug(?=[-.]?(?:nr|nummer)))[-.]?")
# Kennungs-Etiketten, deren Wert nicht zur Person gehört (Gläubiger-ID, Bankleitzahl, Umsatzsteuer der Firma)
KENNUNG_FREMD_RE = re.compile(r"(?i)gl(?:ä|ae|a)ubiger|bankleitzahl|\bblz\b|\bust\b|umsatzsteuer|wirtschafts[ -]?ident"
                              r"|\bw[ -]?idnr\b")
# "Nummer der Bedarfsgemeinschaft", "Nr. des Nationalpasses", "Nummer Ihrer Police": die Nummer eines Gegenstands
NUMMER_DER_RE = re.compile(r"(?<![\wäöüß])(?:Nummer|Nr\.|NUMMER|NR\.)[ \t]+(?:der|des|Ihrer|Ihres|ihrer|ihres|seiner|"
                           r"seines|meiner|meines)[ \t]+([A-ZÄÖÜ][\wäöüß\-]{3,})")
# Kürzel oder Substantiv vor "Nr." ("HKP Nr.", "KVA Nr.", "Lebensversicherung Nr."): ein Kennungs-Etikett, außer das
# Wort benennt eine Gliederung oder einen Katalog ("Tel. Nr.", "Pos. Nr.", "GOÄ Nr.", "PZN Nr.", "Seite Nr.")
_VOR_NR_RE = re.compile(r"(?<![\wäöüß\-.])([A-ZÄÖÜ][\wäöüß\-]{3,}|[A-ZÄÖÜ]{2,4})[ \t]+(?:Nr\.|NR\.|No\.)(?![\w])")
_VOR_NR_FREMD_RE = re.compile(r"(?i)(?:str|straße|strasse|weg|platz|allee|gasse|ring|damm|ufer|haus|zimmer|raum|seite|"
                              r"position|artikel|tarif|produkt|anlage|ziffer|abschnitt|paragraph|kapitel|formular|"
                              r"vordruck|muster|blatt|band|heft|ausgabe|liste|tabelle|spalte|zeile|punkt|frage|"
                              r"aufgabe|filiale|zweigstelle|geschäftsstelle|gleis|bahnsteig|flug|gate|sitz|platz|"
                              r"flight|seat|room|page|item|row|reihe|wagen|zug)$")
_KUERZEL_FREMD = frozenset({"HS", "ZI", "KW", "DIN", "ISO", "EN", "VDE", "IEC", "BGB", "VVG", "SGB", "HGB", "AVB",
                            "AKB", "ABS", "UST", "EUR", "PLZ", "LFD", "POS", "TEL", "FAX", "ART", "GOZ", "GOÄ", "EBM",
                            "BEL", "PZN", "HSN", "TSN", "KBA", "TOP", "LV", "AZ", "NR", "ST", "BLZ", "RVO", "ZPO",
                            "STPO"})


def nummern_wort(wort: str) -> bool:
    """Ist das Wort ein zusammengesetztes Nummern-Etikett einer Kennung ("Bestandsnummer", "BG-Nummer", "Vorg.-Nr.")
    – kein Etikett einer Rufnummer, Anschrift, Gliederung, eines Katalogs oder Fahrzeugschlüssels (NUMMERN_FREMD)?"""
    return (len(wort or "") >= 5 and NUMMERN_WORT_RE.fullmatch(wort) is not None
            and not NUMMERN_FREMD.match(wort) and not KENNUNG_FREMD_RE.search(wort))


def stamm_vor_nr(wort: str) -> bool:
    """Macht das Wort vor "Nr." diese zu einem Kennungs-Etikett ("HKP Nr.", "Lebensversicherung Nr.") – kein
    Gliederungs-, Katalog- oder Straßenwort ("Seite Nr.", "Pos. Nr.", "GOÄ Nr.", "Hauptstraße Nr.")?"""
    w = (wort or "").strip(" .-")
    if not w or _VOR_NR_FREMD_RE.search(w) or NUMMERN_FREMD.match(w) or w.upper() in _KUERZEL_FREMD:
        return False
    return not ist_funktionswort(w) and not KENNUNG_FREMD_RE.search(w)


def stamm_der_nummer(wort: str) -> bool:
    """Ist "Nummer der/des <wort>" eine Kennung ("Nummer der Bedarfsgemeinschaft", "Nr. des Nationalpasses") – nicht
    die Nummer einer Seite, eines Paragraphen, einer Hotline oder Zentrale?"""
    w = (wort or "").strip(" .-")
    if not stamm_vor_nr(w):
        return False
    return not re.search(r"(?i)hotline|service|zentrale|notruf|telefon|fax|polizei|feuerwehr|seite|paragraph", w)


class Kennungsetikett(NamedTuple):
    start: int
    ende: int
    etikett: str             # Text des Etiketts ("Personalnummer", "Nummer der Bedarfsgemeinschaft", "HKP Nr.")


def _wissen_kennungs_etiketten(text: str, start: int, ende: int) -> list:
    try:
        from . import wissen
        return [(start + v.start, start + v.ende) for v in wissen.finde(text[start:ende].replace("\t", "\n"),
                                                                        "etiketten_kennung")]
    except Exception:  # pragma: no cover - Wissensbasis fehlt
        return []


def kennungs_etiketten(text: str, start: int = 0, ende: int | None = None) -> list:
    """Alle allgemeinen Kennungs-Etiketten in text[start:ende] als [Kennungsetikett], nicht überlappend (das längere
    gewinnt), nie über eine Zellgrenze: Etiketten der Wissensbasis (daten/etiketten_kennung.txt), zusammengesetzte
    Nummern-Wörter (nummern_wort), "Nummer der/des …" (stamm_der_nummer) und ein Kürzel oder Substantiv vor "Nr."
    (stamm_vor_nr). Ohne Etiketten fremder Kennungen (Gläubiger-ID, Bankleitzahl, USt-IdNr.) und ohne die Etiketten
    mit eigener Wertform (eVB, Transferticket, Kartenprüfnummer: kennungen())."""
    ende = len(text) if ende is None else ende
    roh = _wissen_kennungs_etiketten(text, start, ende)
    for m in NUMMERN_WORT_RE.finditer(text, start, ende):
        if nummern_wort(m.group(1)):
            roh.append((m.start(1), m.end(1)))
    for m in NUMMER_DER_RE.finditer(text, start, ende):
        if stamm_der_nummer(m.group(1)):
            roh.append((m.start(), m.end()))
    for m in _VOR_NR_RE.finditer(text, start, ende):
        if stamm_vor_nr(m.group(1)):
            roh.append((m.start(), m.end()))
    if "ennz" in text or "ENNZ" in text or "lakette" in text or "child" in text or "Kfz" in text:
        roh += [(m.start(), m.end()) for m in KFZ_ETIKETT_RE.finditer(text, start, ende)]  # "Kurzzeitkennzeichen"
    aus: list = []
    for s, e in sorted(set(roh), key=lambda se: (se[0], -(se[1] - se[0]))):
        etikett = text[s:e]
        if "\n" in etikett or "\t" in etikett or (s > 0 and (text[s - 1].isalnum() or text[s - 1] in "-/&")):
            continue
        if KENNUNG_FREMD_RE.search(etikett) or ETIKETT_RE.fullmatch(etikett.rstrip(":")):
            continue
        if aus and s < aus[-1].ende:
            if e - s > aus[-1].ende - aus[-1].start:
                aus[-1] = Kennungsetikett(s, e, etikett)
            continue
        aus.append(Kennungsetikett(s, e, etikett))
    return aus


# -- Brücke über Zwischenwörter ------------------------------------------------------------------------------------
# Kandidat eines Werts (die genaue Form prüft kennungswert)
_KANDIDAT_RE = re.compile(r"#?[A-Za-zÄÖÜäöü0-9][^\s,;()]*")
# Gegenstände mit eigener Nummer, Zeit- und Geldangaben: steht eines davon direkt vor der Ankündigung, gehört der Wert
# ihm ("Versicherungsnummer im Tarif: KOMFORT 2024", "Kundennummer und Software-Version: 3.2.1")
_KENNUNG_FREMDE_GEGENSTAENDE = frozenset("""
tarif tarife tarifcode produkt hotline service servicetelefon kundenservice telefon tel fax telefax durchwahl mobil
handy internet online homepage webseite website mail e-mail email portal postfach version versionsnummer software
norm din iso modell typ kennzeichen kennz laufzeit jahr jahre zeitraum datum beginn ende ablauf frist termin uhrzeit
zeit beitrag betrag summe gebühr gebuehr preis klasse sf-klasse seite anlage formular vordruck träger trägers
kostenträger kostenträgers trägerin institution einrichtung monat monate monats jahres quartal quartals woche
""".split())
# Ergänzung ohne Ankündigung: Artikel, Präposition oder Possessiv vorn ("Kennnummer der Karte 80276 …", "Vertragsnummer
# beim Vorversicherer KH-55 667 788") – der Wert beendet die Zeile
_ERGAENZUNG_ANFANG = frozenset("""
der des die dem den beim bei im vom zum zur laut lt lt. gem gem. gemäß gemaess für fuer ihres ihrer ihrem ihren unseres
unserer seines seiner meines meiner
""".split())


def fremd_fuer_kennung(wort: str) -> bool:
    """Gehört ein Wert hinter `wort` (direkt vor der Ankündigung) zu einem anderen Gegenstand als dem Kennungs-
    Etikett davor – eine Rufnummer, ein Tarif, eine Zeit- oder Geldangabe oder ein Kennungs-, Kontakt-,
    Vertragsdaten- oder Anschrift-Etikett der Wissensbasis ("…, Kennzeichen: M-AB 123", "… Beginn: 01.04.2025")?"""
    roh = (wort or "").strip(".,;:()[]\"'„“")
    k = roh.casefold()
    if not k:
        return False
    if k in _KENNUNG_FREMDE_GEGENSTAENDE or k.rsplit("-", 1)[-1] in _KENNUNG_FREMDE_GEGENSTAENDE:
        return True
    if not roh[:1].isupper():
        return False
    try:
        from . import wissen
        for art in ("kennung", "kontakt", "vertragsdaten", "adresse"):
            if wissen.index(f"etiketten_{art}").eintrag_fuer(roh) is not None:
                return True
    except Exception:  # pragma: no cover - Wissensbasis fehlt
        return False
    return False


# Zeile eines anderen Felds ("Herstellerschlüsselnummer (HSN): 0603" unter "… Zulassungsbescheinigung Teil I"): am
# Zeilenanfang höchstens vier Wörter, eine Klammer und ein Doppelpunkt – keine Ankündigung ("Fahrzeugs lautet: …")
_FELDZEILE_RE = re.compile(r"[A-ZÄÖÜ][^\s:()]{0,40}(?:[ \t]+[^\s:()]{1,40}){0,3}[ \t]*(?:\([^()\n]{0,40}\)[ \t]*)?:")


def _anderes_kennungsfeld(text: str, i: int) -> bool:
    """Beginnt bei i (einem Wort zwischen Etikett und Wert) ein anderes Feld: ein zusammengesetztes Nummern-Etikett –
    auch eines, dessen Wert nicht zur Person gehört ("Herstellerschlüsselnummer", "Artikel-Nr.": dessen Wert ist es
    trotzdem, nicht der des Etiketts davor) – oder am Anfang einer Zeile eine Feldzeile ("Typ (TSN): AQZ")?"""
    m = NUMMERN_WORT_RE.match(text, i)
    if m is not None and len(m.group(1)) >= 5:
        return True
    zeilenanfang = text.rfind("\n", 0, i) + 1
    if text[zeilenanfang:i].strip():
        return False
    f = _FELDZEILE_RE.match(text, i)
    return f is not None and not _ANKUENDIGUNG_RE.search(text, i, f.end())


def _zeilenende(text: str, i: int, grenze: int) -> int:
    n = text.find("\n", i, grenze)
    n = grenze if n < 0 else n
    z = text.find("\t\t", i, n)
    return n if z < 0 else z


class Kennungswert(NamedTuple):
    start: int
    ende: int
    zwischen: str            # Zwischenwörter ("beim Arbeitgeber"), sonst ""
    ankuendigung: str        # "" (direkt), ":" / "zelle" / "lautet" / "nr." … oder "frei" (Ergänzung ohne Ankündigung)


def allgemeine_kennung(text: str, s: int, e: int, etikett: str | None = None, *, grenze: int | None = None,
                       ist_etikett=wissen_etikett, etikett_starts=None) -> Kennungswert | None:
    """Wert hinter dem allgemeinen Kennungs-Etikett text[s:e] nach der Regel „Etikett + Wert“ (Modulkopf), für jedes
    Kennungs-Etikett: direkt dahinter (Füllung, "#", eine Laufnummer "IMEI 1: …"), hinter Zwischenwörtern desselben
    Satzes bis zu einer Ankündigung (":", "lautet", "ist", "Nr.", eine Zellgrenze) – höchstens MAX_ZWISCHEN_KENNUNG
    Wörter, Abbruch am Satzende und an einem anderen Kennungs-Etikett (etikett_starts: Anfänge der Etiketten) – oder
    ohne Ankündigung hinter einer kurzen Ergänzung mit Artikel/Präposition vorn, wenn der Wert die Zeile beendet
    ("Kennnummer der Karte 80276 00157 0098765432"). Der Wert braucht die Form einer Kennung (kennungswert); ein Wert
    hinter einem Gegenstand mit eigener Nummer (fremd_fuer_kennung: "… und Kennzeichen: M-AB 123", "… Hotline:
    0800 …") und ein "Nr." hinter einem anderen Substantiv ("… auf Formular Nr. 12") gehören nicht dazu."""
    etikett = text[s:e] if etikett is None else etikett
    grenze = len(text) if grenze is None else min(grenze, len(text))
    if fahrzeugschluessel(text, etikett, e) or _BIC_ETIKETT_RE.search(etikett):
        return None                                     # BIC/SWIFT: eigene Wertform ohne Ziffergruppen (muster.bic)
    starts = etikett_starts if etikett_starts is not None else frozenset()   # nie kopieren: je Etikett der Seite
                                                                             # gerufen (linear bleiben)
    if kfz_etikett(etikett):
        return _kfz_hinter_etikett(text, e, grenze, ist_etikett, starts, s)

    def zwischenwort(a, b, umbruch):
        return kennungswert(text, a, _zeilenende(text, a, grenze), etikett, nr=True) is None

    def anderes_etikett(i):
        return (i != s and i in starts) or _anderes_kennungsfeld(text, i)

    t = wert_hinter_etikett(text, e, _KANDIDAT_RE, grenze=grenze, ist_etikett=ist_etikett,
                            max_woerter=MAX_ZWISCHEN_KENNUNG, zwischenwort=zwischenwort, kennung=True,
                            fremd_pruefen=fremd_fuer_kennung, anderes_etikett=anderes_etikett)
    if t is not None:
        if t.ankuendigung in ("nr.", "nr", "nummer") and _fremdes_nr(text, e, t):
            return None
        direkt = not t.zwischen and not t.ankuendigung
        trenner = text[e:t.start]
        streng = direkt and not t.zelle and not t.darunter and not re.search(r"[:=#\t]|\n", trenner)
        nr = not direkt or bool(re.search(r"(?i)\b(?:nr|nummer|no)\b", trenner))
        sp = kennungswert(text, t.start, _zeilenende(text, t.start, grenze), etikett, streng=streng, nr=nr)
        if sp is None or (not direkt and zeitangabe(text[sp[0]:sp[1]])):
            return None                                 # hinter Zwischenwörtern kein Zeitraum ("… für: 2024/2025")
        return Kennungswert(sp[0], sp[1], t.zwischen, t.ankuendigung)
    return _ergaenzung(text, e, etikett, grenze, starts)


class _Formtreffer:
    """Treffer einer Wertform-Funktion mit der Schnittstelle eines re.Match (start, end, group)."""

    __slots__ = ("_text", "_s", "_e")

    def __init__(self, text: str, s: int, e: int):
        self._text, self._s, self._e = text, s, e

    def start(self, *_):
        return self._s

    def end(self, *_):
        return self._e

    def group(self, *_):
        return self._text[self._s:self._e]


class Wertform:
    """Wertform-Funktion f(text, pos, grenze) -> (start, ende) | None als Ersatz für das re.Pattern der Regel „Etikett
    + Wert“ (wert_hinter_etikett): match(text, pos) trifft nur einen Wert, der genau bei pos beginnt. So gilt hinter
    einer Ankündigung nur ein Wert dieser Form ("… lautet ab März 2026: 245 TKD": "ab" ist kein Kennzeichen, der Satz
    wird bis zum Doppelpunkt weitergelesen)."""

    def __init__(self, funktion):
        self._funktion = funktion

    def match(self, text: str, pos: int = 0, endpos: int | None = None):
        if pos >= len(text) or text[pos] in " \t\n":
            return None
        grenze = _zeilenende(text, pos, len(text) if endpos is None else min(endpos, len(text)))
        sp = self._funktion(text, pos, grenze)
        if sp is None or sp[0] != pos:
            return None
        return _Formtreffer(text, sp[0], sp[1])


def _kfz_hinter_etikett(text: str, e: int, grenze: int, ist_etikett, starts, s: int) -> Kennungswert | None:
    """Kennzeichen hinter einem Kfz-Etikett (kfz_etikett) nach derselben Regel „Etikett + Wert“ wie jede Kennung –
    direkt dahinter ("Versicherungskennzeichen 604 RMX", "Kennzeichen (Mofa): 287 LMV"), hinter Zwischenwörtern bis
    zu einer Ankündigung ("… für das Verkehrsjahr 2026 lautet 712 KRB", "Kennzeichen des italienischen Lkw: FX 482
    KL") –, aber mit der Wertform eines Kennzeichens (kfz_wert) statt der einer Nummer."""
    def anderes_etikett(i):
        return (i != s and i in starts) or _anderes_kennungsfeld(text, i)

    t = wert_hinter_etikett(text, e, KFZ_WERTFORM, grenze=grenze, ist_etikett=ist_etikett,
                            max_woerter=MAX_ZWISCHEN_KENNUNG, kennung=True, fremd_pruefen=fremd_fuer_kennung,
                            anderes_etikett=anderes_etikett)
    if t is None or (t.zwischen and zeitangabe(text[t.start:t.ende])):
        return None
    return Kennungswert(t.start, t.ende, t.zwischen, t.ankuendigung)


# BIC/SWIFT-Etiketten: der Wert hat die eigene Form eines BIC (muster.bic, vier Buchstaben Bank, zwei Land …) – Ziffern
# dahinter ("Kreditinstitut (Name und BIC)" ⏎ "67 1 …", Kammfeld-Reste auf dem Scan) sind kein Wert dieses Etiketts
_BIC_ETIKETT_RE = re.compile(r"(?i)(?<![a-zäöü])(?:bic|swift)(?![a-zäöü])")
# Monatsbereich ("01-06/2025", "1.-3./2025") – wie Monat/Jahr und Jahresbereich ein Zeitraum, keine Kennung
_MONATSBEREICH_RE = re.compile(r"(?:0?[1-9]|1[0-2])\.?[ ]?[-–][ ]?(?:0?[1-9]|1[0-2])\.?/(?:19|20)?\d{2}")


def zeitangabe(wert: str) -> bool:
    """Ist der Wert eine Zeitangabe statt einer Kennung – Zeitraum (Monat/Jahr, Jahresbereich, zwei Jahre),
    Monatsbereich ("01-06/2025") oder Datum? Hinter Zwischenwörtern und ohne Ankündigung zählt so ein Wert nicht als
    Kennung ("Policennummer der Hausratversicherung 2024/2025"); direkt hinter "Nr." bleibt er eine laufende Nummer
    mit Jahr (Runde 4d)."""
    w = (wert or "").strip()
    return zeitraum(w) or bool(_MONATSBEREICH_RE.fullmatch(w)) or bool(_DATUM_RE.fullmatch(w))


def _fremdes_nr(text: str, e: int, t: Wertfund) -> bool:
    """Gehört das ankündigende "Nr." einem anderen Substantiv direkt davor ("Kundennummer bitte auf Formular Nr. 12
    eintragen") statt dem Etikett ("Führerschein Klasse 3 vom 12.04.1985, Nr. 355/85", "… unter der Nr. 1187/82")?"""
    vorn = text[e:t.start]
    m = re.search(r"([^\s,;:()]+)[ \t]+(?:Nr\.?|NR\.?|Nummer|NUMMER|No\.?)[ \t:.#]*$", vorn)
    if m is None:
        return False
    wort = m.group(1)
    return wort[:1].isupper() and not ist_funktionswort(wort) and not any(c.isdigit() for c in wort)


def _ergaenzung(text: str, e: int, etikett: str, grenze: int, starts: set) -> Kennungswert | None:
    """Wert ohne Ankündigung hinter einer kurzen Ergänzung ("Kennnummer der Karte 80276 00157 0098765432"): das erste
    Wort ein Artikel, eine Präposition oder ein Possessiv, keine Ziffer und kein anderes Etikett in der Ergänzung, der
    Wert (streng: reine Ziffern ab fünf) beendet die Zeile bzw. den Satz."""
    zeilenende = _zeilenende(text, e, grenze)
    for m in re.finditer(r"[ \t]+", text[e:zeilenende]):
        a = e + m.end()
        zwischen = text[e:e + m.start()].split()
        if not zwischen:
            continue
        if len(zwischen) > OHNE_ANKUENDIGUNG_KENNUNG:
            return None
        if zwischen[0].casefold() not in _ERGAENZUNG_ANFANG or any(c.isdigit() for c in "".join(zwischen)) \
                or any(c in "".join(zwischen) for c in ".:;!?") and not zwischen[0].endswith(".") \
                or any(st in starts for st in range(e + 1, a)):
            continue
        if any(fremd_fuer_kennung(w) for w in zwischen[1:]):
            return None                                 # "Beitragsnummer für das Jahr 2024/25": der Wert gehört dem
                                                        # Gegenstand der Ergänzung
        sp = kennungswert(text, a, zeilenende, etikett, streng=True, nr=True)
        if sp is not None and not any(c.isdigit() for c in text[sp[0]:sp[1]].split()[0]):
            continue                                    # ohne Ankündigung beginnt der Wert mit einer Ziffer: ein Wort
                                                        # davor gehört zur Ergänzung ("… beim Finanzamt Leipzig II
                                                        # 00934072100", von der Texterkennung als "IF" gelesen)
        if sp is not None and WERT_ENDE_RE.match(text, sp[1]) and not _satz_geht_weiter(text, sp[1]) \
                and not zeitangabe(text[sp[0]:sp[1]]):
            return Kennungswert(sp[0], sp[1], " ".join(zwischen), "frei")
    return None


def allgemeine_kennungen(text: str, start: int = 0, ende: int | None = None, ist_etikett=wissen_etikett) -> list:
    """Alle Werte hinter allgemeinen Kennungs-Etiketten (kennungs_etiketten, allgemeine_kennung) in text[start:ende]:
    [(Kennungsetikett, Kennungswert)] – für die Selbstkontrolle (restrisiko.py); die Erkennung liest dieselbe Regel je
    Etikett ihrer Lage (detektoren/struktur.py)."""
    ende = len(text) if ende is None else ende
    etiketten = kennungs_etiketten(text, start, ende)
    starts = frozenset(k.start for k in etiketten)
    aus = []
    for k in etiketten:
        w = allgemeine_kennung(text, k.start, k.ende, k.etikett, grenze=ende, ist_etikett=ist_etikett,
                               etikett_starts=starts)
        if w is not None:
            aus.append((k, w))
    return aus


# ======================================================================
# Kfz-Kennzeichen (Runde 5, Paket K2: Domänen-Befunde 19–26, 41, 44)
# ======================================================================
# Kfz-Etikett: "Kennzeichen" und seine Zusammensetzungen mit Fahrzeugbezug – Versicherungs-, Kurzzeit-, Oldtimer-,
# Saison-, Ausfuhr-, Händler-, Wechselkennzeichen, "Vers.-Kennzeichen", "Kfz-Kennzeichen", "E-/H-Kennzeichen", "rotes
# Kennzeichen", "Kennzeichen-Nr.", "Versicherungsplakette", "Nummernschild" –, nicht Gefahrgut-, Qualitäts-, Prüf-,
# CE-, Institutions- oder Personenkennzeichen (kein Fahrzeug: das Wort davor gehört zur Zusammensetzung)
_KFZ_VORSATZ = (r"versicherungs|vers\.|kurzzeit|oldtimer|saison|ausfuhr|export|zoll|h(?:ä|ae)ndler|wechsel|"
                r"(?:ü|ue)berf(?:ü|ue)hrungs|fahrzeug|kraftfahrzeug|kfz|pkw|lkw|krad|kraftrad|motorrad|mofa|moped|"
                r"roller|kleinkraftrad|anh(?:ä|ae)nger|wunsch|diplomaten|beh(?:ö|oe)rden|[eh]")
_KFZ_ADJEKTIV = (r"amtl(?:iche[sn]?|\.)|polizeiliche[sn]?|rote[sn]?|gr(?:ü|ue)ne[sn]?|neue[sn]?|alte[sn]?|"
                 r"deutsche[sn]?|ausl(?:ä|ae)ndische[sn]?|gegnerische[sn]?|vorl(?:ä|ae)ufige[sn]?")
KFZ_ETIKETT_RE = re.compile(
    r"(?<![\wäöüß.\-])(?:"
    r"(?:(?i:" + _KFZ_ADJEKTIV + r")[ \t]+)?(?:(?i:" + _KFZ_VORSATZ + r")[ \t]*-?[ \t]*)?"
    r"(?i:kennzeichen|kennz\.)(?:[ \t]*-?[ \t]*(?i:nr\.?|nummer)(?![\wäöüß]))?"
    r"|(?i:kfz-?kz\.?|kfz-zeichen|nummernschild(?:er)?|versicherungsplakette|kfz-?schild)"
    r"(?:[ \t]*-?[ \t]*(?i:nr\.?|nummer)(?![\wäöüß]))?"         # "Versicherungsplakette Nr. 712 KRB"
    r")(?![\wäöüß])")


def kfz_etikett(etikett: str) -> bool:
    """Ist das Etikett ein Kfz-Etikett (KFZ_ETIKETT_RE: "Kennzeichen", "Versicherungskennzeichen-Nr.",
    "Vers.-Kennzeichen", "rotes Oldtimerkennzeichen", "Versicherungsplakette") – dann hat sein Wert die Form eines
    Kennzeichens (kfz_wert), nicht die einer Nummer?"""
    t = " ".join((etikett or "").split()).strip(" :")
    return bool(t) and KFZ_ETIKETT_RE.fullmatch(t) is not None


def unterscheidungszeichen(kuerzel: str) -> bool:
    """Ist das Kürzel ein amtliches Unterscheidungszeichen (Wissensbasis daten/kfz_unterscheidungszeichen.txt:
    Verwaltungsbezirke, wieder zugelassene Altkennzeichen, Bund und Länder) – auch so, wie es ohne Umlaut geschrieben
    wird ("LOE", "LO" für "LÖ")? Ohne Wissensbasis gilt jedes Kürzel (wie vor Runde 5)."""
    try:
        from . import wissen
        return wissen.normalisieren(kuerzel or "") in wissen.menge("kfz_unterscheidungszeichen")
    except Exception:  # pragma: no cover - Wissensbasis fehlt
        return True


def fahrzeugmarke(wort: str) -> bool:
    """Ist das Wort eine Fahrzeugmarke der Wissensbasis (daten/fahrzeugmarken.txt: "DAF", "KTM", "Volvo")? Ein Code
    direkt dahinter ist ein Modell ("DAF XF 480", "KTM RC 390"), kein Kennzeichen."""
    w = (wort or "").strip(".,;:()[]\"'„“")
    if not w:
        return False
    try:
        from . import wissen
        return wissen.normalisieren(w) in wissen.menge("fahrzeugmarken")
    except Exception:  # pragma: no cover - Wissensbasis fehlt
        return False


# Wertformen eines Kennzeichens hinter einem Kfz-Etikett (kfz_wert) – Trenner auch mit Leerzeichen um den
# Bindestrich und als Gedankenstrich ("RO - KL 2207", "RO – KL 2207")
_KFZ_TRENNER = r"(?:[ \t]?[-–‐][ \t]?|[ \t])"
_KFZ_DE_RE = re.compile(r"([A-ZÄÖÜ]{1,3})" + _KFZ_TRENNER + r"([A-Z]{1,2})[ \t]?(\d{1,4})([EH])?(?![\wäöüß])")
_KFZ_DE_KLEIN_RE = re.compile(r"([a-zäöü]{1,3})" + _KFZ_TRENNER + r"([a-z]{1,2})[ \t]?(\d{1,4})([eh])?(?![\wäöüß])")
# Kurzzeit- und rote Kennzeichen: Erkennungsnummer ohne Buchstaben, beginnend mit 03 bis 07 ("RO-04 1287", "RO-07 451",
# "RO-06 3315")
_KFZ_SONDER_RE = re.compile(r"([A-ZÄÖÜ]{1,3})[ \t]?[-–‐][ \t]?(0[3-7])[ \t]?(\d{1,4})(?![\wäöüß])")
# Ausfuhrkennzeichen: Ziffern und ein Buchstabe ("HH 4711 A", "B 1234 C")
_KFZ_AUSFUHR_RE = re.compile(r"([A-ZÄÖÜ]{1,3})[ \t]?[-–‐]?[ \t]?(\d{1,4})[ \t]?([A-Z])(?![\wäöüß])")
# Versicherungskennzeichen (Mofa, Moped, E-Scooter): drei Ziffern über drei Buchstaben, auch kompakt und zweizeilig
_KFZ_VKZ_RE = re.compile(r"(\d{3})(?:[ \t]?|[ \t]*\n[ \t]*)([A-Z]{3})(?![\wäöüß])")
# ohne Trenner ("ROKL2207", "BGLHK77", "MAB1234E")
_KFZ_KOMPAKT_RE = re.compile(r"([A-ZÄÖÜ]{2,5})(\d{1,4})([EH])?(?![\wäöüß])")
# ausländische Formen hinter dem Etikett ("WGM 4471K", "FX 482 KL", "67-BDK-1", "LU 946067", "1A2 3456", "W-12345X")
_KFZ_AUSLAND_RE = re.compile(r"[A-Z0-9ÄÖÜ]{1,4}(?:[ \t\-·.][A-Z0-9ÄÖÜ]{1,6}){0,3}(?![\wäöüß])")
_KFZ_GRUPPE_RE = re.compile(r"[A-Z0-9ÄÖÜ]+")
# Buchstabenteile, die Währungen und Einheiten sind ("100 EUR", "125 CCM", "350 KWH"), und Funktionswörter
_KFZ_EINHEITEN = frozenset({"EUR", "USD", "CHF", "GBP", "PLN", "CZK", "HUF", "SEK", "NOK", "DKK", "RON", "BGN", "TRY",
                            "HRK", "RUB", "CCM", "KWH", "KW", "PS", "KM", "KMH", "KG", "CM", "MM", "QM", "STK", "TSD",
                            "MIO", "MRD", "UHR", "NM", "PCS", "TAGE", "LTR", "DM", "ATS", "ME", "VA", "MWH", "MPH"})
_KFZ_KLEIN_SPERRE = frozenset(FUNKTIONSWOERTER | {"ca", "tag", "tage", "km", "min", "std", "uhr", "eur", "ab", "bis",
                                                  "war", "ist", "hat", "nur", "uns", "und", "zu", "um", "so", "da",
                                                  "wo", "ob", "es", "er", "je", "pro", "mal", "nr", "s", "z", "u",
                                                  "o", "d", "v", "kg", "mm", "cm", "nm", "ps", "kw"})
_DEZIMAL_DANACH_RE = re.compile(r"[.,]\d")
# ein Datum im Wert der ausländischen Form: "AM 29.03.2025", "VOM 01.02.24" (Versalien der Texterkennung)
_DATUM_IN_WERT_RE = re.compile(r"(?<!\d)\d{1,2}\.\d{1,2}\.(?:\d{4}|\d{2})(?!\d)")


def _kfz_einheit(teile) -> bool:
    return any(t.upper() in _KFZ_EINHEITEN for t in teile)


def kfz_wert(text: str, pos: int, grenze: int | None = None):
    """(start, ende) des Kennzeichens ab pos (führender Leerraum übersprungen) hinter einem Kfz-Etikett – oder None:
    deutsche Form (auch "RO - KL 2207", "RO – KL 2207", klein "ro-xt 913"), Kurzzeit- und rote Kennzeichen ("RO-04
    1287"), Ausfuhrkennzeichen ("HH 4711 A"), Versicherungskennzeichen ("435 GHT", "435GHT", zweizeilig "435" ⏎ "GHT"),
    Kompaktform ("ROKL2207") und ausländische Formen ("WGM 4471K", "FX 482 KL", "67-BDK-1"). Hinter dem Etikett gilt
    jedes Unterscheidungszeichen (auch verlesen oder ausländisch); nie eine Zahl mit Währung oder Einheit ("100 EUR",
    "125 CCM") und nie ein Wort ohne Ziffer."""
    grenze = len(text) if grenze is None else min(grenze, len(text))
    i = pos
    while i < grenze and text[i] in " \t":
        i += 1
    if i >= grenze:
        return None
    for regel in (_KFZ_SONDER_RE, _KFZ_DE_RE, _KFZ_AUSFUHR_RE, _KFZ_VKZ_RE, _KFZ_KOMPAKT_RE):
        m = regel.match(text, i, grenze)
        if m is None or _DEZIMAL_DANACH_RE.match(text, m.end()):
            continue
        if regel is _KFZ_VKZ_RE and _kfz_einheit([m.group(2)]):
            continue
        if regel is _KFZ_DE_RE and _kfz_einheit([m.group(1), m.group(2)]):
            continue
        if regel is _KFZ_KOMPAKT_RE and (_kfz_einheit([m.group(1)]) or len(m.group(1)) + len(m.group(2)) < 4):
            continue
        if EINHEIT_DANACH_RE.match(text, m.end()):
            continue
        ende = m.end()
        if regel is _KFZ_DE_RE and not m.group(4):
            # von der Texterkennung geteilte Ziffern ("F-YY 531 1" für "F-YY 5311"): eine Ziffergruppe direkt
            # dahinter gehört dazu, solange es höchstens vier Ziffern sind und keine Einheit folgt
            rest = re.match(r"[ ](\d{1,3})(?![\w/\-]|[.,]\d)", text[ende:grenze])
            if rest is not None and len(m.group(3)) + len(rest.group(1)) <= 4 \
                    and not EINHEIT_DANACH_RE.match(text, ende + rest.end()):
                ende += rest.end()
        return m.start(), ende
    m = _KFZ_DE_KLEIN_RE.match(text, i, grenze)
    if m is not None and m.group(1) not in _KFZ_KLEIN_SPERRE \
            and (m.group(2) not in _KFZ_KLEIN_SPERRE or re.search(r"[-–‐]", text[m.end(1):m.start(2)])) \
            and not EINHEIT_DANACH_RE.match(text, m.end()) and not _DEZIMAL_DANACH_RE.match(text, m.end()):
        return m.start(), m.end()                       # "m - ab 123" mit Bindestrich, nicht "ca ab 12"
    m = _KFZ_AUSLAND_RE.match(text, i, grenze)
    if m is None:
        return None
    gruppen = _KFZ_GRUPPE_RE.findall(m.group(0))
    while len(gruppen) > 1 and gruppen[-1].isalpha() and any(len(g) > 3 for g in gruppen):
        gruppen.pop()                                   # "WGM 4471K VW": ein Wort dahinter gehört nicht dazu
    if len(gruppen) < len(_KFZ_GRUPPE_RE.findall(m.group(0))):
        ende = i
        for g in gruppen:
            ende = text.index(g, ende) + len(g)
    else:
        ende = m.end()
    wert = text[i:ende]
    alnum = [c for c in wert if c.isalnum()]
    if len(alnum) < 4 or not any(c.isdigit() for c in alnum) or not any(c.isalpha() for c in alnum):
        return None
    if _kfz_einheit(gruppen) or ist_datum_text(wert) or ist_betrag(wert) or _DEZIMAL_DANACH_RE.match(text, ende) \
            or EINHEIT_DANACH_RE.match(text, ende) or _DATUM_IN_WERT_RE.search(wert):
        return None                                     # "AM 29.03.2025" (OCR in Versalien): ein Datum
    return i, ende


KFZ_WERTFORM = Wertform(kfz_wert)          # kfz_wert als Wertform der Regel „Etikett + Wert“


# Kennzeichen ohne Etikett (kennzeichen_stellen): die deutsche Form mit amtlichem Unterscheidungszeichen
_KFZ_FREI_RE = re.compile(
    r"(?<![\wÄÖÜäöü\-/.])([A-ZÄÖÜ]{1,3})([ \t]?[-–‐][ \t]?|[ \t])([A-Z]{1,2})[ \t]?(\d{1,4})([EH])?(?![\wäöüß])"
    r"(?![ \t]*(?:Uhr|EUR|€|%|Prozent|km|Jahre|Monate|Tage|Punkte)(?![\wäöüß]))")
_KFZ_SONDER_FREI_RE = re.compile(r"(?<![\wÄÖÜäöü\-/.])([A-ZÄÖÜ]{1,3})[ \t]?[-–‐][ \t]?(0[3-7])[ \t](\d{1,4})"
                                 r"(?![\wäöüß])")
_KFZ_KOMPAKT_FREI_RE = re.compile(r"(?<![\wÄÖÜäöü\-/.])([A-ZÄÖÜ]{2,5})(\d{1,4})([EH])?(?![\wäöüß\-/])")
_KFZ_KLEIN_FREI_RE = re.compile(r"(?<![\wÄÖÜäöü\-/.])([a-zäöü]{1,3})([ \t]?[-–‐][ \t]?|[ \t])([a-z]{1,2})[ \t]?"
                                r"(\d{1,4})([eh])?(?![\wäöüß])")
# Kfz-Wort direkt vor der Kompaktform ("Pkw ROKL2207", "Risiko: Anhänger ROKL22", "Kfz-Kennzeichen ROKL2207")
_KFZ_WORT = (r"Pkw|PKW|Lkw|LKW|Krad|KRAD|Kraftrad|Motorrad|Anh(?:ä|ae)nger|Wohnwagen|Wohnmobil|Kfz|KFZ|Fahrzeug|"
             r"Roller|Mofa|Moped|Quad|Trike|Traktor|Zugmaschine|Auflieger|Transporter|Bus|Caravan")
_KFZ_WORT_DAVOR_RE = re.compile(r"(?:(?<![\wäöüß])(?:" + _KFZ_WORT + r")|" + KFZ_ETIKETT_RE.pattern
                                + r")[ \t]*:?[ \t]*$")
# Kfz-Wörter im Satz vor einem klein geschriebenen Kennzeichen ("mein Auto (ro - kl 2207)", "… mit seinem Kennzeichen
# hinterlassen: ro-xt 913"); ohne Bindestrich zählt nur "Kennzeichen" davor ("das Kennzeichen … war ro xt 913")
_KFZ_SATZWORT_RE = re.compile(r"(?i)(?<![\wäöüß])(?:kennzeichen|kennz\.|nummernschild|auto|autos|wagen|pkw|lkw|kfz|"
                              r"fahrzeug|fahrzeugs|motorrad|roller|mofa|moped|transporter|anh(?:ä|ae)nger|wohnmobil)"
                              r"(?![\wäöüß])")
_KFZ_KENNZEICHEN_WORT_RE = re.compile(r"(?i)(?<![\wäöüß])(?:kennzeichen|kennz\.|nummernschild)(?![\wäöüß])")
_SATZ_FENSTER = 120


def _satz_davor(text: str, s: int) -> str:
    """Text vor s im selben Satz (höchstens _SATZ_FENSTER Zeichen, nicht über einen Absatz)."""
    a = max(0, s - _SATZ_FENSTER)
    davor = text[a:s]
    for trenner in ("\n\n", ". ", "! ", "? ", "; "):
        k = davor.rfind(trenner)
        if k >= 0:
            davor = davor[k + len(trenner):]
    return davor


def _kompakt_teilbar(buchstaben: str) -> bool:
    """Lässt sich die Buchstabenfolge der Kompaktform in ein amtliches Unterscheidungszeichen (1–3 Buchstaben) und eine
    Erkennung aus 1–2 Buchstaben teilen ("ROKL" = "RO" + "KL")?"""
    for n in (1, 2, 3):
        rest = len(buchstaben) - n
        if 1 <= rest <= 2 and unterscheidungszeichen(buchstaben[:n]):
            return True
    return False


def kennzeichen_stellen(text: str, sperre=frozenset()) -> list:
    """(start, ende) der deutschen Kfz-Kennzeichen ohne Etikett – gemeinsam für Erkennung (muster.kfz) und
    Selbstkontrolle (restrisiko): die Form "N-AB 1234" (auch "N AB 1234", "RO - KL 2207", "RO – KL 2207") und die
    Kurzzeit-/roten Kennzeichen ("RO-04 1287") NUR mit amtlichem Unterscheidungszeichen (unterscheidungszeichen) – das
    schließt Modellcodes aus ("KTM RC 390", "DAF XF 480", "YZF-R1"), ebenso eine Ziffer mit Dezimalteil (Hubraum: "C-HR
    1.8", "GT-R 3.8"); die Kompaktform ("ROKL2207") nur direkt hinter einem Kfz-Wort ("Pkw", "Anhänger",
    "Kennzeichen"); klein geschrieben ("ro-xt 913") nur mit einem Kfz-Wort im Satz davor, ohne Bindestrich nur hinter
    "Kennzeichen". sperre: Kürzel, die in Versicherungstexten keine Unterscheidungszeichen sind ("KH", "VK", "BU")."""
    aus = []
    for m in _KFZ_FREI_RE.finditer(text):
        kuerzel, trenner, ziffern = m.group(1), m.group(2), m.group(4)
        if kuerzel in sperre or not unterscheidungszeichen(kuerzel) or _DEZIMAL_DANACH_RE.match(text, m.end()):
            continue
        if trenner != "-" and len(ziffern) == 4 and ziffern[:2] in ("19", "20"):
            continue                                    # "SGB VI 2023", "VVG AB 2008", "S - BU 2024"
        aus.append((m.start(), m.end()))
    for m in _KFZ_SONDER_FREI_RE.finditer(text):
        if m.group(1) not in sperre and unterscheidungszeichen(m.group(1)) \
                and not _DEZIMAL_DANACH_RE.match(text, m.end()):
            aus.append((m.start(), m.end()))
    for m in _KFZ_KOMPAKT_FREI_RE.finditer(text):
        buchstaben, ziffern = m.group(1), m.group(2)
        if buchstaben in sperre or _kfz_einheit([buchstaben]) or len(buchstaben) + len(ziffern) < 5 \
                or not _kompakt_teilbar(buchstaben):
            continue
        if _KFZ_WORT_DAVOR_RE.search(text, max(0, m.start() - 40), m.start()):
            aus.append((m.start(), m.end()))
    for m in _KFZ_KLEIN_FREI_RE.finditer(text):
        kuerzel, trenner, buchstaben = m.group(1), m.group(2), m.group(3)
        if kuerzel in _KFZ_KLEIN_SPERRE or not unterscheidungszeichen(kuerzel) \
                or (buchstaben in _KFZ_KLEIN_SPERRE and not trenner.strip()) \
                or _DEZIMAL_DANACH_RE.match(text, m.end()) or EINHEIT_DANACH_RE.match(text, m.end()):
            continue                                    # "m - ab 123" mit Bindestrich ja, "m ab 123" nicht
        davor = _satz_davor(text, m.start())
        if (_KFZ_SATZWORT_RE.search(davor) if trenner.strip() else _KFZ_KENNZEICHEN_WORT_RE.search(davor)):
            aus.append((m.start(), m.end()))
    aus.sort()
    return aus


# Ausländische Kennzeichen im Fließtext (Domänen-Befund 24): Formen der Nachbarländer ("WGM 4471K" PL, "FX 482 KL" IT,
# "AB-123-CD" FR, "67-BDK-1" NL, "1A2 3456" CZ, "W-12345X" AT, "ZH 123456" CH, "34 ABC 1234" TR)
_KFZ_AUSLAND_FREI_RE = re.compile(
    r"(?<![\wÄÖÜäöü\-/.])(?:"
    r"[A-Z]{2}[ \-]\d{3}[ \-][A-Z]{2}"
    r"|[A-Z]{2,3}[ ]\d{3,5}[A-Z]{0,2}"
    r"|\d{2}-[A-Z]{2,3}-\d{1,2}|[A-Z]{2}-\d{2,3}-[A-Z]{1,2}|\d-[A-Z]{3}-\d{3}"
    r"|\d[A-Z]\d[ ]\d{4}"
    r"|[A-Z]{1,2}-\d{3,5}[A-Z]{1,2}"
    r"|\d{2}[ ][A-Z]{1,3}[ ]\d{2,4}"
    r")(?![\wäöüß\-/]|[.,]\d)")
_FAHRZEUG_WORT = (r"kennzeichen|kennz\.|nummernschild|pkw|lkw|sattelzug|zugmaschine|sattelzugmaschine|auflieger|"
                  r"sattelauflieger|anh(?:ä|ae)nger|(?:klein)?transporter|lieferwagen|kleinbus|reisebus|bus|fahrzeug|"
                  r"fahrzeugs|wagen|auto|motorrad|wohnmobil|wohnwagen|kastenwagen|tanklaster|laster|kipper|traktor")
_FAHRZEUG_WORT_RE = re.compile(r"(?i)(?<![\wäöüß])(?:" + _FAHRZEUG_WORT + r")(?![\wäöüß])")
_LAND_ADJEKTIV_RE = re.compile(
    r"(?i)(?<![\wäöüß])(?:polnisch|italienisch|tschechisch|(?:ö|oe)sterreichisch|schweizerisch|schweizer|"
    r"niederl(?:ä|ae)ndisch|holl(?:ä|ae)ndisch|franz(?:ö|oe)sisch|belgisch|luxemburgisch|d(?:ä|ae)nisch|schwedisch|"
    r"norwegisch|finnisch|spanisch|portugiesisch|rum(?:ä|ae)nisch|bulgarisch|ungarisch|slowakisch|slowenisch|"
    r"kroatisch|serbisch|bosnisch|albanisch|mazedonisch|litauisch|lettisch|estnisch|t(?:ü|ue)rkisch|griechisch|"
    r"ukrainisch|russisch|wei(?:ß|ss)russisch|belarussisch|moldauisch|englisch|britisch|irisch|ausl(?:ä|ae)ndisch)"
    r"(?:e[nrms]?)?(?![\wäöüß])"
    r"|\((?:PL|I|IT|CZ|SK|A|AT|CH|NL|F|FR|B|BE|L|LU|DK|S|N|FIN|E|ES|P|RO|BG|H|HU|SLO|HR|SRB|BIH|AL|LT|LV|EST|TR|GR|"
    r"UA|RUS|BY|MD|GB|UK|IRL)\)")
_FAHRZEUG_DIREKT_RE = re.compile(r"(?i)(?<![\wäöüß])(?:" + _FAHRZEUG_WORT + r")[ \t]*\(?[ \t]*$")


def kennzeichen_im_satz(text: str) -> list:
    """(start, ende, mit_land) der ausländischen Kennzeichen im Fließtext (_KFZ_AUSLAND_FREI_RE), die direkt hinter
    einem Fahrzeugwort stehen ("Zugmaschine WGM 4471K", "Kleintransporter (FX 482 KL)", "Pkw (1A2 3456)"); mit_land:
    im selben Satz ein Länderhinweis ("polnischer Sattelzug", "(PL)") – dann schwärzt die Erkennung (international),
    sonst meldet die Selbstkontrolle einen Verdacht. Nicht hinter einer Fahrzeugmarke ("DAF XF 480", "Volvo FH 500":
    ein Modell) und keine deutsche Form mit amtlichem Unterscheidungszeichen (die liest kennzeichen_stellen)."""
    aus = []
    for m in _KFZ_AUSLAND_FREI_RE.finditer(text):
        davor = text[max(0, m.start() - 40):m.start()]
        wort = re.search(r"([^\s(]+)[ \t]*\(?[ \t]*$", davor)
        if wort is not None and fahrzeugmarke(wort.group(1)):
            continue
        if not _FAHRZEUG_DIREKT_RE.search(davor):
            continue
        satz = _satz_davor(text, m.start()) + text[m.start():m.end() + _SATZ_FENSTER].split(". ")[0]
        gruppen = _KFZ_GRUPPE_RE.findall(m.group(0))
        if _kfz_einheit(gruppen):
            continue
        aus.append((m.start(), m.end(), bool(_LAND_ADJEKTIV_RE.search(satz))))
    return aus


# ======================================================================
# Ausländische Anschriften (Runde 5, Paket K2: Domänen-Befunde 29, 40) – gemeinsam für Erkennung (detektoren/
# wissen_kontext.py, Kategorie international) und Selbstkontrolle (restrisiko.py)
# ======================================================================
_GROSS_ORT = "A-ZÄÖÜÀ-ÖØ-ÞĀĂĄĆČĎĐĒĖĘĚĞĢĪĮİĶĹĻĽŁŃŅŇŌŐŒŔŘŚŞŠŢŤŪŮŰŲŹŻŽȘȚ"
_KLEIN_ORT = "a-zäöüßà-öø-ÿāăąćčďđēėęěğģīįıķĺļľłńņňōőœŕřśşšţťūůűųźżžșț"
_ORT_CAP = rf"[{_GROSS_ORT}][{_KLEIN_ORT}{_GROSS_ORT}'’\-]+"
_ORT_STADT = rf"{_ORT_CAP}(?:[ \t]+(?:{_ORT_CAP}|\d{{1,2}}))?"
# Länderhinweis im Umkreis einer Anschrift
LAND_RE = re.compile(r"(?i:österreich|schweiz|liechtenstein|niederlande|holland|belgien|luxemburg|frankreich|italien|"
                     r"spanien|portugal|polen|tschechien|slowakei|ungarn|dänemark|schweden|norwegen|finnland|türkei|"
                     r"kroatien|slowenien|serbien|bosnien|montenegro|albanien|nordmazedonien|mazedonien|kosovo|"
                     r"rumänien|bulgarien|griechenland|litauen|lettland|estland|ukraine|moldau|moldawien|russland|"
                     r"belarus|weißrussland|austria|switzerland|netherlands|belgium|france|italy|spain|poland|czech|"
                     r"hungary|denmark|sweden|norway|turkey|romania|bulgaria|croatia|slovenia|serbia|greece|"
                     r"united[ \t]+kingdom|großbritannien|england|irland|ireland|românia|polska|česko)")
# Straßentyp VOR dem Namen (Rumänien, Bulgarien, Kroatien, Slowenien, Polen): "Str. Memorandumului nr. 27", "Strada
# Avram Iancu 14", "Calea Victoriei nr. 12", "bul. Vitosha 15", "ul. Marszałkowska 10/12"
_STRASSENTYP_VORN_RE = re.compile(
    r"(?<![\wäöüß.\-])(?:Str\.|Strada|STR\.|Calea|Aleea|Bd\.|B-dul|Bulevardul|[ȘŞS]os\.|[ȘŞS]oseaua|Pia[țţt]a|"
    r"Splaiul|Intrarea|bul\.|Bul\.|ul\.|Ul\.|ulica|Ulica|ulitsa|ul\.|trg|Trg)[ \t]+"
    rf"(?:(?:{_ORT_CAP}|\d{{1,2}}[.]?|de|din|lui|la|cel|na|pod|kod)[ \t]+){{0,3}}{_ORT_CAP},?[ \t]+"
    r"(?:(?i:nr\.?|no\.?|br\.?|broj)[ \t]*)?\d{1,4}[a-zA-Z]?(?:[ \t]?/[ \t]?\d{1,4}[a-zA-Z]?)?(?![\w])")
# Straßenklasse mit Nummer – Autobahn, Bundes-, Landes-, Kreis-, Staatsstraße, Europastraße ("Auf der A 8", "B 15",
# "L 2080", "BAB 9", "St 2089", "E 45"): eine Fahrbahn, keine Anschrift (Domänen-Befund 46; muster.py und restrisiko.py)
STRASSENKLASSE = r"(?:A|B|L|K|S|E|St|ST|Kr|KR|BAB|Bab|AB)[ \t]?\d{1,4}"
STRASSENKLASSE_RE = re.compile(r"(?<![\wäöüß])" + STRASSENKLASSE + r"(?![\wäöüß])")
# sechsstellige PLZ mit Ort (Rumänien, Russland, Weißrussland, Kasachstan …) – nur mit Länderhinweis
_PLZ6_RE = re.compile(rf"(?<![\w\-/.,])\d{{6}}[ \t]+({_ORT_STADT})(?![\w])")
# vierstellige PLZ mit Ort (Österreich, Schweiz, Liechtenstein, Dänemark, Ungarn, Belgien …)
_PLZ4_RE = re.compile(rf"(?<![\w\-/.,])(?:(?:A|AT|CH|FL|L|B|DK|H|N)[ \t]?-[ \t]?)?(\d{{4}})[ \t]+({_ORT_STADT})"
                      r"(?![\w])")
_KEIN_PLZ_ORT = frozenset("""
euro eur chf stück stueck jahre jahren jahr monate monat tage tag wochen stunden minuten prozent personen kinder
mitarbeiter
punkte seiten seite umzug vertrieb schaden abteilung kostenstelle bestand bestände summe betrag beitrag mitglied
kunden kunde verträge vertrag fahrzeuge fahrzeug schäden euro-norm km kilometer meter liter kg mal anzahlung franken
""".split())


def _ort_nicht(wort: str) -> bool:
    """Ist das erste Wort hinter der Zahl kein Ort ("1500 Euro", "4711 Vertrieb", "2026 Umzug") – eine Einheit, ein
    Sach- oder Allerweltswort?"""
    k = (wort or "").strip(".,;:()").casefold()
    if not k or k in _KEIN_PLZ_ORT:
        return True
    try:
        from . import wissen
        return bool(wissen.ist_allerweltswort(wort.strip(".,;:()")))
    except Exception:  # pragma: no cover - Wissensbasis fehlt
        return False


def ort_at_ch(phrase: str) -> bool:
    """Ein Ort in Österreich, der Schweiz oder Liechtenstein (Wissensbasis daten/orte_at_ch.txt: "Linz", "Zürich",
    "Bregenz") – auch die ersten Wörter einer längeren Ortsangabe ("Sankt Gallen", "Krems an der Donau")?"""
    try:
        from . import wissen
        index = wissen.index("orte_at_ch")
    except Exception:  # pragma: no cover - Wissensbasis fehlt
        return False
    woerter = (phrase or "").split()
    for n in range(min(len(woerter), 4), 0, -1):
        if index.eintrag_fuer(" ".join(woerter[:n])) is not None:
            return True
    return False


def strassen_vorn(text: str) -> list:
    """(start, ende) der Straßen mit vorangestelltem Straßentyp (Rumänien, Bulgarien, Kroatien, Slowenien, Polen):
    "Str. Memorandumului nr. 27", "Calea Victoriei nr. 12", "bul. Vitosha 15" – Name und Hausnummer, der Typ gehört
    dazu."""
    return [(m.start(), m.end()) for m in _STRASSENTYP_VORN_RE.finditer(text)]


def plz6_mit_land(text: str) -> list:
    """(start, ende) der sechsstelligen PLZ mit Ort, wenn im Umkreis ein Länderhinweis steht ("400114 Cluj-Napoca,
    Rumänien") – ohne ihn ist eine sechsstellige Zahl vor einem Wort eher eine Artikel- oder Bestellnummer."""
    aus = []
    for m in _PLZ6_RE.finditer(text):
        if _ort_nicht(m.group(1).split()[0]):
            continue
        if LAND_RE.search(text, max(0, m.start() - 120), min(len(text), m.end() + 60)):
            aus.append((m.start(), m.end()))
    return aus


def plz4_ausland(text: str, strassen) -> list:
    """(start, ende) der vierstelligen PLZ mit Ort einer ausländischen Anschrift: hinter einer Straße beliebiger Form
    (strassen: [(start, ende)]; höchstens sechs Zeichen und ein Komma dazwischen: "Seestrasse 12, 8002 Zürich"), vor
    einer Straße in Klammern ("4040 Linz (Hauptstraße 44/3/12)"), mit Länderhinweis oder Länderkürzel im Umkreis
    ("CH-3011 Bern", "…, Schweiz") oder mit einem Ort der Nachbarländer ("aus 4040 Linz": daten/orte_at_ch.txt). Keine
    Einheit und kein Sachwort dahinter ("1500 Euro", "4711 Vertrieb"); eine Jahreszahl ("2025 Hamburg") nur mit Straße,
    Länderhinweis oder Länderkürzel."""
    aus = []
    enden = sorted(e for _, e in strassen)
    anfaenge = sorted(s for s, _ in strassen)
    for m in _PLZ4_RE.finditer(text):
        plz, ort = m.group(1), m.group(2)
        if _ort_nicht(ort.split()[0]):
            continue
        nach_strasse = any(0 <= m.start() - e <= 6 and "\n" not in text[e:m.start()] for e in enden
                           if m.start() - 8 <= e <= m.start())
        vor_strasse = any(0 <= s - m.end() <= 3 for s in anfaenge if m.end() <= s <= m.end() + 3)
        kuerzel = m.group(0)[:1].isalpha()
        land = bool(LAND_RE.search(text, max(0, m.start() - 120), min(len(text), m.end() + 60)))
        jahr = plz[:2] in ("19", "20")
        if not (nach_strasse or vor_strasse or kuerzel or land) and (jahr or not ort_at_ch(ort)):
            continue
        aus.append((m.start(), m.end()))
    return aus


# ======================================================================
# Neue Kategorien (Runde 5, Paket K2: Domänen-Befunde 37, 69, 70, 71, 81, 99–103) – gemeinsam für Erkennung
# (muster.py) und Selbstkontrolle (restrisiko.py)
# ======================================================================
# -- IP-Adresse -------------------------------------------------------------------------------------------------------
_IPV4_RE = re.compile(r"(?<![\w.:\-/])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?![\w]|[.:]\d)")
_IPV6_RE = re.compile(r"(?<![\w:.\-])(?=[0-9A-Fa-f:]*:[0-9A-Fa-f]*:)[0-9A-Fa-f:]{2,39}(?![\w:])")
_IP_ETIKETT_RE = re.compile(r"(?i)(?<![a-zäöüß])(?:ip(?:v[46])?(?:-?adresse)?|adresse|host|server|router|client|"
                            r"zugriff|absender|von|aus|via|quelle|source|address)[ \t]*[:=]?[ \t]*\(?[ \t]*$")
_IP_IN_ZEILE_RE = re.compile(r"(?<![A-Za-zÄÖÜäöüß])(?:IP|IPv4|IP-Adresse|IP-Adr\.|ip-adresse)(?![a-zäöüß])")
_VERSION_DAVOR_RE = re.compile(r"(?i)(?:version|vers\.|release|build|firmware|software|update|treiber|patch|"
                               r"stand|revision|rev\.|ver\.|v)[ \t\-]*[:.]?[ \t]*$")


def _ipv4_gueltig(m) -> bool:
    teile = m.groups()
    return all(int(t) <= 255 and (t == "0" or not t.startswith("0")) for t in teile)


def ip_adressen(text: str) -> list:
    """(start, ende) der IP-Adressen: IPv4 mit vier gültigen Oktetten (bis 255, ohne führende Null) nur mit IP-Bezug –
    direkt hinter einem Etikett oder Kontextwort ("IP-Adresse:", "IPv4", "Zugriff von", "Absender-IP") oder mit "IP"
    in derselben Zeile ("Zeitstempel …, IP 84.123.45.67"); ohne ihn ist "95.137.189.6" eher eine Vertragsnummer mit
    Punkten. Nie hinter einem Versionswort ("Version 10.0.19045.1234", "Firmware-Release 4.18.0.147"); IPv6 mit
    mindestens drei Gruppen, gültig nach der Norm und mit Hex-Buchstabe oder "::" (nie eine Uhrzeit "14:08:30", nie eine
    MAC-Adresse aus sechs Zweiergruppen)."""
    aus = []
    if "." in text:
        for m in _IPV4_RE.finditer(text):
            if not _ipv4_gueltig(m):
                continue
            davor = text[max(0, m.start() - 30):m.start()].rsplit("\n", 1)[-1]
            if _VERSION_DAVOR_RE.search(davor):
                continue
            a = text.rfind("\n", 0, m.start()) + 1
            e = text.find("\n", m.end())
            zeile = text[a:len(text) if e < 0 else e]
            if _IP_ETIKETT_RE.search(davor) or _IP_IN_ZEILE_RE.search(zeile):
                aus.append((m.start(), m.end()))
    if text.count(":") >= 2:
        import ipaddress
        for m in _IPV6_RE.finditer(text):
            w = m.group(0)
            gruppen = [g for g in w.split(":") if g]
            if len(gruppen) < 3 or not ("::" in w or re.search(r"[A-Fa-f]", w)):
                continue
            try:
                ipaddress.IPv6Address(w)
            except ValueError:
                continue
            aus.append((m.start(), m.end()))
    return aus


# -- Standort / Koordinaten -------------------------------------------------------------------------------------------
_GRAD_PAAR_RE = re.compile(
    r"(?<![\w.,\-])([-+]?\d{1,2}\.\d{3,8})(?:[ \t]*°)?(?:[ \t]*([NSns])(?![\w]))?[ \t]*[,;/][ \t]*"
    r"([-+]?\d{1,3}\.\d{3,8})(?:[ \t]*°)?(?:[ \t]*([EOWeow])(?![\w]))?(?![\w]|[.,]\d)")
_GRAD_EINZELN_RE = re.compile(
    r"(?i)(?<![\wäöüß])(?:breite(?:ngrad)?|l(?:ä|ae)nge(?:ngrad)?|lat(?:itude)?|lon(?:gitude)?|lng)[ \t]*[:=]?[ \t]*"
    r"([-+]?\d{1,3}\.\d{3,8})(?:[ \t]*°)?(?:[ \t]*[NSEOW](?![\w]))?(?![\w]|[.,]\d)")
_DMS_RE = re.compile(
    r"(?<![\d.,])(\d{1,3})[ \t]?°[ \t]?(\d{1,2})[ \t]?['′’][ \t]?(\d{1,2}(?:[.,]\d+)?)[ \t]?(?:[\"″”]|'')?[ \t]?"
    r"([NSEOW])(?![\wäöüß])")
_STANDORT_ETIKETT_RE = re.compile(r"(?i)(?<![\wäöüß])(?:gps|koordinaten|standort|position|geo|lage|unfallort|"
                                  r"fundort|ortung)(?![\wäöüß])")


def koordinaten(text: str) -> list:
    """(start, ende) der Standortangaben: ein Paar in Dezimalgrad (Breite bis 90, Länge bis 180, mindestens vier
    Nachkommastellen – hinter "GPS", "Koordinaten", "Standort", "Position" … mindestens drei: "47.85612, 12.12857",
    "52.5200 N, 13.4050 O"), Breiten- und Längengrad mit Etikett ("Breitengrad 47.85612") und Grad/Minuten/Sekunden mit
    Himmelsrichtung ("47°51'22.0\\"N"). Einzelne Messwerte mit Dezimalpunkt, Beträge und Versionen bleiben stehen."""
    aus = []
    if "." in text:
        for m in _GRAD_PAAR_RE.finditer(text):
            breite, laenge = float(m.group(1)), float(m.group(3))
            if abs(breite) > 90 or abs(laenge) > 180:
                continue
            stellen = min(len(m.group(1).split(".")[1]), len(m.group(3).split(".")[1]))
            mit_richtung = bool(m.group(2) and m.group(4))
            davor = text[max(0, m.start() - 40):m.start()].rsplit("\n", 1)[-1]
            if stellen >= 4 or (stellen >= 3 and (mit_richtung or _STANDORT_ETIKETT_RE.search(davor))):
                aus.append((m.start(1), m.end()))
        for m in _GRAD_EINZELN_RE.finditer(text):
            if abs(float(m.group(1))) <= 180 and not any(a <= m.start(1) < b for a, b in aus):
                aus.append((m.start(1), m.end()))
    if "°" in text:
        for m in _DMS_RE.finditer(text):
            grad = int(m.group(1))
            if grad <= (90 if m.group(4) in "NS" else 180) and int(m.group(2)) < 60:
                aus.append((m.start(), m.end()))
    return sorted(set(aus))


# -- Verschleierte E-Mail-Adresse -------------------------------------------------------------------------------------
_AT_RE = r"[ \t]?(?:[\(\[\{][ \t]?(?:at|ät|AT|@)[ \t]?[\)\]\}]|[ \t]@[ \t])[ \t]?"
_DOT_RE = r"(?:[ \t]?[\(\[\{][ \t]?(?:dot|DOT|punkt|PUNKT|pkt)[ \t]?[\)\]\}][ \t]?|\.)"
EMAIL_VERSCHLEIERT_RE = re.compile(
    r"(?<![\w.\-+%])[\w.\-+%]{1,64}" + _AT_RE + r"[\w\-]{1,63}(?:" + _DOT_RE + r"[\w\-]{1,63}){0,3}" + _DOT_RE
    + r"(?:de|com|net|org|eu|at|ch|info|biz|io|nl|fr|it|es|pl|tr|uk|co|me|email|online|mail|be|lu|dk|se|no|fi|cz|"
      r"hu|ro|gr|ru|us|li)(?![\wäöüß])")


def email_verschleiert(text: str) -> list:
    """(start, ende) der verschleierten E-Mail-Adressen: "(at)", "[at]", "{at}", "(ät)" statt "@", "[dot]", "(punkt)"
    statt des Punkts ("quirin.zw [at] web [dot] de", "quirin.zw(at)web(punkt)de") – nur mit bekannter Endung ("(at)
    Messe" ist keine Adresse)."""
    if "at" not in text and "ät" not in text and "AT" not in text and " @ " not in text:
        return []
    return [(m.start(), m.end()) for m in EMAIL_VERSCHLEIERT_RE.finditer(text)]


# -- Zugangsdaten -----------------------------------------------------------------------------------------------------
# Etiketten eines Zugangs (Kundenportal, App): Benutzer/-name/-kennung, Login, Kennwort/Passwort, PIN, Aktivierungs-,
# Freischalt-, Zugangs- und Registrierungscode – nicht als Bestimmungswort ("Benutzerhandbuch", "Kennwortregeln") und
# nicht hinter einer Plattform ("Signal-Benutzername": ein Profilname)
_ZUGANG_ETIKETT_RE = re.compile(
    r"(?<![\wäöüß\-./])(?:"
    r"(?i:benutzer(?:name|kennung|konto|-?id)?|nutzerkennung|anmelde(?:name|kennung)|login(?:-?(?:name|id|kennung))?|"
    r"username|user(?:-?id)?|zugangs(?:kennung|name|code|nummer|daten)|kunden-?login)"
    r"|(?i:(?:initial|einmal|start|erst|transport|online)?-?(?:kennwort|passwort|password|passwd))"
    r"|(?:PIN|Pin)(?:-?(?:Nr\.?|Nummer|Code))?"
    r"|(?i:aktivierungs(?:code|schl(?:ü|ue)ssel|nummer|kennung)|freischalt(?:code|nummer|schl(?:ü|ue)ssel)|"
    r"registrierungs(?:code|schl(?:ü|ue)ssel|nummer)|zugangsschl(?:ü|ue)ssel|einmalcode|tan)"
    r")(?:[ \t]*\([^()\n]{1,20}\))?(?![\wäöüß\-])")
_ZUGANG_WERT_RE = re.compile(r"[^\s,;\"„“”«»<>|]{3,64}")
_ZUGANG_FUELLWORT = frozenset("""
wird werden wurde ist sind siehe s. vgl. folgt folgen separat gesondert per bitte nicht kein keine keinen unbekannt
vergessen ändern aendern zurücksetzen zuruecksetzen ihr ihre ihren ihrem ihres der die das den dem des ein eine einen
wie laut lt. gemäß gemaess noch erhalten erhalten. mitgeteilt mitgeteilt. herr frau firma eingeben eingabe hier unten
oben vorhanden nein ja leer offen beantragt angefordert neu alt automatisch generiert gültig gueltig
""".split())
_ZUGANG_ANKUENDIGUNG_RE = re.compile(r"(?i)[ \t]*(?:lautet|lauten|ist)(?![\wäöüß])[ \t]*:?[ \t]*")


def _zugang_wert(text: str, i: int, grenze: int):
    """(start, ende) eines Zugangswerts ab i: ein Token ohne Leerzeichen (3–64 Zeichen) mit Buchstabe oder Ziffer, das
    kein Füllwort ist und hinter dem der Satz nicht klein weitergeht ("wird separat zugesandt")."""
    while i < grenze and text[i] in " \t":
        i += 1
    m = _ZUGANG_WERT_RE.match(text, i, grenze)
    if m is None:
        return None
    s, e = m.start(), m.end()
    while e > s and text[e - 1] in ".,:;)»“”'\"":
        e -= 1
    wert = text[s:e]
    if len(wert) < 3 or not any(c.isalnum() for c in wert) or wert.startswith(("[", "(", "http", "www.")):
        return None
    if wert.casefold() in _ZUGANG_FUELLWORT or wert.casefold().rstrip(".:") in _ZUGANG_FUELLWORT:
        return None
    if "@" in wert and "." in wert.split("@")[-1]:
        return None                                     # E-Mail-Adresse: eigene Kategorie
    rest = text[m.end():min(grenze, m.end() + 40)]
    naechstes = re.match(r"[ \t]+([^\s]+)", rest)
    if naechstes is not None and naechstes.group(1)[:1].islower() and wert.isalpha() \
            and not naechstes.group(1).startswith(("/", "|")):
        return None                                     # "Kennwort: wird separat zugesandt", "PIN: siehe Brief"
    if wert[:1].isupper() and wert.isalpha() and wert[1:].islower() and len(wert) > 3:
        try:
            from . import wissen
            if wissen.ist_allerweltswort(wert) or wissen.ist_anrede_titel(wert) or wissen.ist_vorname(wert) \
                    or wissen.ist_nachname(wert):
                return None                             # "Benutzer: Herr …", "Benutzername: Max Mustermann"
        except Exception:  # pragma: no cover - Wissensbasis fehlt
            pass
    return s, e


def zugangsdaten(text: str) -> list:
    """(start, ende) der Zugangsdaten hinter ihrem Etikett (Benutzer, Benutzerkennung, Login, Kennwort, Passwort, PIN,
    Aktivierungs-, Freischalt-, Zugangs-, Registrierungscode, Initialpasswort): mit Trennzeichen (":", "=", Zellgrenze,
    eine Klammer "(alt)" davor) oder hinter "lautet"/"ist" desselben Satzes (höchstens sechs Wörter Abstand:
    "Ihr Kennwort für das Kundenportal lautet: Sommer2024!"); ein Etikett am Zeilenende mit Doppelpunkt nimmt den
    Wert am Anfang der nächsten Zeile. Kein Füllwort ("Kennwort: wird separat zugesandt", "PIN: siehe Brief"), kein
    Name, keine E-Mail-Adresse."""
    aus = []
    for m in _ZUGANG_ETIKETT_RE.finditer(text):
        e = m.end()
        zeilenende = text.find("\n", e)
        zeilenende = len(text) if zeilenende < 0 else zeilenende
        t = re.match(r"[ \t]*(?:[:=]|\t\t)[ \t]*", text[e:zeilenende + 1])
        if t is not None:
            i = e + t.end()
            if i >= zeilenende and text[e:zeilenende].strip().startswith(":"):
                folge = text.find("\n", zeilenende + 1)
                sp = _zugang_wert(text, zeilenende + 1, len(text) if folge < 0 else folge)
                if sp is not None and not text[sp[1]:(len(text) if folge < 0 else folge)].strip():
                    aus.append(sp)
                continue
            sp = _zugang_wert(text, i, zeilenende)
            if sp is not None:
                aus.append(sp)
            continue
        # "Ihr Kennwort für das Kundenportal lautet: …": Ankündigung im selben Satz
        satz = text[e:min(zeilenende, e + 120)]
        for k, wort in enumerate(re.finditer(r"\S+", satz)):
            if k > 6 or wort.group(0)[-1:] in ".!?;" and not wort.group(0).endswith(":"):
                break
            a = _ZUGANG_ANKUENDIGUNG_RE.match(satz, wort.start())
            if a is not None and a.end() > wort.start():
                sp = _zugang_wert(text, e + a.end(), zeilenende)
                if sp is not None:
                    aus.append(sp)
                break
    return sorted(set(aus))


# -- Profil- und Kontonamen -------------------------------------------------------------------------------------------
_PLATTFORM = (r"eBay|Ebay|EBAY|Kleinanzeigen|Vinted|Instagram|Facebook|TikTok|Tiktok|Snapchat|Signal|Telegram|Threema|"
              r"Skype|Discord|Twitter|LinkedIn|Linkedin|Xing|XING|YouTube|Youtube|Twitch|Reddit|Pinterest|WhatsApp|"
              r"Whatsapp|Steam|PayPal|Paypal|Mastodon|Bluesky|Tinder|Etsy|Wallapop|Shpock|Willhaben|Mobile\.de|"
              r"Autoscout24|Vinted\.de|Momox|Rebuy|Amazon|Airbnb|Booking|Spotify|Netflix|Telegram-Kanal")
_PROFIL_NAMENSWORT = (r"(?:Nutzer|Benutzer|Mitglieds|Profil|Anzeige|Konto|Account|Verk(?:ä|ae)ufer|K(?:ä|ae)ufer|"
                      r"Spieler|Kanal|Spitz|Anzeigen|User)-?[Nn]ame|Nickname|Alias|Handle|Profil|Konto|Account|Name|"
                      r"Benutzer|Nutzer|Kennung|ID|Id|Kanal")
_PROFIL_ETIKETT_RE = re.compile(
    r"(?<![\wäöüß\-])(?:"
    # "eBay-Name", "Signal-Benutzername"
    r"(?:" + _PLATTFORM + r")[ \t]*-[ \t]*(?:" + _PROFIL_NAMENSWORT + r")"
    r"|(?:" + _PROFIL_NAMENSWORT.split("|Nickname")[0] + r"|Nickname)"               # "Nutzername", "Profilname"
    r"(?:[ \t]+(?:auf|bei|in|im)[ \t]+(?:" + _PLATTFORM + r"))?"                       # "Profilname auf Vinted"
    r"|(?:Snapchat|Signal|Telegram|Threema|Discord|TikTok|Tiktok|Instagram|Skype|Twitter|Mastodon|Bluesky|Xing|XING)"
    r")(?![\wäöüß\-])")
_PROFIL_WERT_RE = re.compile(r"@?[A-Za-z0-9ÄÖÜäöüß][A-Za-z0-9ÄÖÜäöüß._\-]{1,40}(?<![._\-])")
# "@"-Name mit mindestens einem Buchstaben ("@lena.wiesengrund", "@korbi_zeitl84") – nie ein Datum oder eine Zahl hinter
# einem verlesenen "@" ("@1.12.2034" auf einem Schreibmaschinen-Scan)
_HANDLE_RE = re.compile(r"(?<![\w@.\-+%/])@(?=[\w.]*[A-Za-z])"
                        r"([A-Za-z0-9_](?:[A-Za-z0-9_.]{1,38}[A-Za-z0-9_]))(?![\w@]|\.[A-Za-z])")
_PROFIL_URL_RE = re.compile(
    r"(?i)(?<![\w.\-/])(?:https?://)?(?:www\.|m\.|de\.|mobile\.)?"
    r"(?:facebook\.com|fb\.com|instagram\.com|t\.me|telegram\.me|tiktok\.com/@?|twitter\.com|x\.com|threads\.net/@?|"
    r"linkedin\.com/in|xing\.com/profile|youtube\.com/@?|youtube\.com/(?:c|user|channel)|twitch\.tv|"
    r"reddit\.com/u(?:ser)?|pinterest\.(?:com|de)|snapchat\.com/add|vinted\.de/member|vinted\.de/members|"
    r"kleinanzeigen\.de/s-bestandsliste\.html\?userId=|github\.com|onlyfans\.com|mastodon\.social/@?)/"
    r"(@?[A-Za-z0-9ÄÖÜäöüß][A-Za-z0-9ÄÖÜäöüß._\-]{1,60})")
_URL_RE = re.compile(r"(?i)(?<![\w@])(?:https?://|www\.)[^\s<>\"'„“”]+|"
                     r"(?<![\w@./])[\w\-]+(?:\.[\w\-]+)*\.(?:de|com|net|org|eu|info|at|ch|io|me|app)/[^\s<>\"'„“”]*")
# Parameter von Links mit Personenbezug ("?kdnr=4711081&vsnr=LV2024887766&name=Zwackelhuber")
_URL_PARAMETER_RE = re.compile(
    r"(?i)[?&;](?:kdnr|kd|kdnummer|kundennr|kundennummer|kunde|kundenid|kunden_id|vsnr|vsnummer|versnr|vertrag|"
    r"vertragsnr|vertragsnummer|police|policennr|policennummer|polizze|vn|vp|name|nachname|vorname|fullname|email|"
    r"mail|e-mail|user|username|benutzer|login|iban|gebdat|geburtsdatum|geb|telefon|tel|mobil|plz|strasse|str|ort|"
    r"schadennr|schadennummer|antragsnr|antragsnummer|az|aktenzeichen)=([^&#\s\"'<>]+)")
_PROFIL_FUELLWORT = frozenset("""
nein ja keine keiner keins nicht vorhanden unbekannt siehe k.a. n/a na entfällt entfaellt kein privat aktiv inaktiv
gelöscht geloescht gesperrt offen folgt
""".split())


def _personenartig(teil: str) -> bool:
    """Sieht der Pfadteil eines Profil-Links nach einer Person aus – Trenner zwischen Wortteilen ("quirin.zwackelhuber",
    "korbi_zeitl84"), Ziffern oder ein Vor-/Nachname der Wissensbasis – und nicht nach einer Organisation der
    Erlaubnisliste ("allianz.de", "HUKCOBURG")?"""
    t = teil.lstrip("@")
    woerter = [w for w in re.split(r"[._\-]+", t) if w]
    try:
        from . import wissen
        if any(wissen.ist_allowlist(w) for w in woerter if len(w) >= 3) or wissen.ist_allowlist(t):
            return False
        bekannt = any(wissen.ist_vorname(w.capitalize()) or wissen.ist_nachname(w.capitalize()) for w in woerter
                      if len(w) >= 3)
    except Exception:  # pragma: no cover - Wissensbasis fehlt
        bekannt = False
    return len(woerter) >= 2 or any(c.isdigit() for c in t) or bekannt


def profilnamen(text: str) -> list:
    """(start, ende) der Profil- und Kontonamen: "@"-Namen ("@lena.wiesengrund", nicht in einer E-Mail-Adresse), Werte
    hinter Profil-Etiketten ("Nutzername:", "Mitgliedsname:", "Profilname auf Vinted:", "eBay-Name:", "Signal-
    Benutzername:", "Snapchat:", "Telegram:" – eine Telefonnummer dahinter liest die Telefonregel), der Pfad eines
    Profil-Links ("facebook.com/quirin.zwackelhuber", "t.me/lenchen_wiese82") – nur mit personenartigem Teil, nie die
    Seite einer Organisation ("facebook.com/HUKCOBURG") – und die Werte personenbezogener Parameter eines Links
    ("?kdnr=4711081&name=Zwackelhuber"). Kein Füllwort ("Telegram: nein", "Signal: nicht vorhanden")."""
    aus = []
    if "@" in text:
        aus += [(m.start(), m.end()) for m in _HANDLE_RE.finditer(text)]
    for m in _PROFIL_ETIKETT_RE.finditer(text):
        t = re.match(r"[ \t]*(?:[:=]|\t\t)[ \t]*", text[m.end():m.end() + 6])
        if t is None:
            continue
        i = m.end() + t.end()
        u = _PROFIL_URL_RE.match(text, i)
        if u is not None:
            continue                                    # der Link: unten
        w = _PROFIL_WERT_RE.match(text, i)
        if w is None:
            continue
        wert = w.group(0)
        if wert.casefold().lstrip("@") in _PROFIL_FUELLWORT or re.fullmatch(r"[+\d][\d ()/\-]*", wert):
            continue                                    # Füllwort; eine Telefonnummer liest die Telefonregel
        rest = re.match(r"[ \t]+([^\s]+)", text[w.end():w.end() + 30])
        if rest is not None and rest.group(1)[:1].islower() and wert.isalpha():
            continue                                    # "Signal: nicht vorhanden" (klein weiter: ein Satz)
        if wert[:1].isupper() and wert.isalpha() and wert[1:].islower():
            continue                                    # "Name: Weber" liest die Namensregel; "Profil: Privat"
        aus.append((w.start(), w.end()))
    if "/" in text:
        for m in _PROFIL_URL_RE.finditer(text):
            if _personenartig(m.group(1)):
                aus.append((m.start(1), m.end(1)))
        if "=" in text:
            for u in _URL_RE.finditer(text):
                for m in _URL_PARAMETER_RE.finditer(u.group(0)):
                    wert = m.group(1)
                    if len(wert) >= 3 and any(c.isalnum() for c in wert):
                        aus.append((u.start() + m.start(1), u.start() + m.end(1)))
    return sorted(set(aus))


# -- Grundbuch und Liegenschaftskataster ------------------------------------------------------------------------------
_FLURSTUECK_RE = re.compile(
    r"(?<![\wäöüß])(?:Flurst(?:ü|ue)ck(?:e|s)?|Flst\.?|FlSt\.?|Flurst\.)(?:[ \t]*-?[ \t]*(?:Nr\.?|Nummer|nummer|"
    r"Nrn\.?))?[ \t]*:?[ \t]*")
_FLURSTUECK_WERT_RE = re.compile(r"\d{1,5}(?:[ \t]?/[ \t]?\d{1,4})?(?![\w/])")
_GRUNDBUCHBLATT_RE = re.compile(r"(?<![\wäöüß])Grundbuch(?:-?[Bb]latt|blatt)(?:[ \t]*-?[ \t]*(?:Nr\.?|Nummer))?"
                                r"[ \t]*:?[ \t]*(\d{1,6})(?![\w/])")
_GRUNDBUCH_BLATT_RE = re.compile(r"(?<![\wäöüß])Grundbuch(?:es|s)?(?![\wäöüß])[^\n.;]{0,90}?(?<![\wäöüß])"
                                 r"(?:Blatt|Bl\.)[ \t]*(?:Nr\.?[ \t]*)?(\d{1,6})(?![\w/])")
_GEMARKUNGSNUMMER_RE = re.compile(r"(?<![\wäöüß])Gemarkung(?:snummer|s-Nr\.?|-Nr\.?|[ \t]+Nr\.?)[ \t]*:?[ \t]*"
                                  r"(\d{3,6})(?![\w/])")


def grundbuch(text: str) -> list:
    """(start, ende) der Angaben aus Grundbuch und Liegenschaftskataster, die ein Grundstück und damit seinen
    Eigentümer bestimmen: Flurstücksnummer ("Flurstück 123/4", "Flst.-Nr. 1187/12", "Flurstücke 445/2 und 445/3"),
    Grundbuchblatt ("Grundbuch von Unterhaching, Blatt 5678", "Grundbuchblatt 9921") und Gemarkungsnummer; nicht
    "Blatt 2 von 3", nicht "Flur und Treppenhaus". Die Flur allein ("Flur 3") bleibt stehen: eine ein- bis
    zweistellige Zahl würde als Wert im ganzen Dokument weitergegeben, und ohne Flurstück bestimmt sie kein
    Grundstück."""
    if "lurst" not in text and "rundbuch" not in text and "Flst" not in text and "FlSt" not in text \
            and "Gemarkung" not in text:
        return []
    aus = []
    for m in _FLURSTUECK_RE.finditer(text):
        i = m.end()
        for _ in range(6):                              # "Flurstücke 445/2 und 445/3", "123/4, 123/5"
            w = _FLURSTUECK_WERT_RE.match(text, i)
            if w is None or (not aus and EINHEIT_DANACH_RE.match(text, w.end())):
                break
            aus.append((w.start(), w.end()))
            folge = re.match(r"[ \t]*(?:,|;|und|u\.|sowie|bzw\.)[ \t]*", text[w.end():w.end() + 12])
            if folge is None:
                break
            i = w.end() + folge.end()
    for regel in (_GRUNDBUCHBLATT_RE, _GRUNDBUCH_BLATT_RE, _GEMARKUNGSNUMMER_RE):
        aus += [(m.start(1), m.end(1)) for m in regel.finditer(text)]
    return sorted(set(aus))


# -- Religion und Konfession (Art. 9 DSGVO) ---------------------------------------------------------------------------
# Kirchensteuermerkmale der Lohnsteuer (rk, ev, lt, rf, ak, fr, die frei- und israelitischen Gemeinden) und
# ausgeschriebene Bekenntnisse – nur hinter einem Etikett bzw. unter einem Spaltenkopf, nie allein ("Ev. Krankenhaus",
# "rk-Wert")
_RELIGION_KUERZEL = frozenset("rk ev lt rf ak fr fa fb fg fm fs ib ih il is iw jd jh".split())
_RELIGION_WORT = (
    r"r(?:ö|oe)misch[ \-]?katholisch|r(?:ö|oe)m\.?[ \-]?kath\.?|r\.[ ]?k\.|katholisch|kath\.|"
    r"evangelisch(?:[ \-](?:lutherisch|reformiert|freikirchlich))?|ev\.[ \-]?(?:luth|ref)\.|evang\.|ev\.|"
    r"lutherisch|reformiert|franz(?:ö|oe)sisch[ \-]reformiert|alt[ \-]?katholisch|freireligi(?:ö|oe)s|"
    r"j(?:ü|ue)disch|israelitisch|islamisch|muslimisch|sunnitisch|schiitisch|alevitisch|jesidisch|"
    r"(?:griechisch|russisch|serbisch|rum(?:ä|ae)nisch|bulgarisch|syrisch|armenisch|koptisch)[ \-]?"
    r"(?:orthodox|apostolisch)|orthodox|koptisch|buddhistisch|hinduistisch|neuapostolisch|mennonitisch|baptistisch|"
    r"methodistisch|freikirchlich|anglikanisch|zeugen[ ]jehovas|konfessionslos|ohne[ ](?:konfession|bekenntnis)|"
    r"katholik(?:in)?|protestant(?:in)?|protestantisch|muslim(?:a|in)?|christ(?:in)?|christlich|jude|j(?:ü|ue)din|"
    r"islam|christentum|judentum|buddhismus|hinduismus|atheist(?:in)?|atheistisch")
_RELIGION_WERT_RE = re.compile(r"(?i)(?<![\wäöüß])(?:" + _RELIGION_WORT + r")(?![\wäöüß])")
_RELIGION_KUERZEL_RE = re.compile(r"(?<![\wäöüß.\-])(" + "|".join(sorted(_RELIGION_KUERZEL))
                                  + r"|" + "|".join(k.upper() for k in sorted(_RELIGION_KUERZEL))
                                  + r")(?![\wäöüß\-]|[.,]\d)")
_RELIGION_ETIKETT = (
    r"konfession|konf\.|bekenntnis|religion(?:szugeh(?:ö|oe)rigkeit|szugeh\.|sgemeinschaft|sbekenntnis|"
    r"sangeh(?:ö|oe)rigkeit)?|rel\.|glaubens(?:richtung|gemeinschaft|zugeh(?:ö|oe)rigkeit)|"
    r"kirchen(?:zugeh(?:ö|oe)rigkeit|steuer(?:[ \-]?merkmal(?:e)?)?|steuermerkmal(?:e)?)|kirche|"
    r"kist(?:[ \-]?merkmal(?:e)?|m)?\.?|ki\.?[ ]?st\.?(?:[ \-]?merkmal(?:e)?)?|kirchensteuerabzugsmerkmal(?:e)?")
_RELIGION_ETIKETT_RE = re.compile(r"(?i)(?<![\wäöüß])(?:" + _RELIGION_ETIKETT + r")(?![\wäöüß])")
_RELIGION_KOPF_RE = re.compile(r"(?i)(?:" + _RELIGION_ETIKETT + r")(?:[ ]?\(?(?:ag|an|stpfl\.?|ehegatte|ehefrau|"
                               r"ehemann|partner)\)?)?:?")
_RELIGION_TRENNER_RE = re.compile(r"(?:[ \t]+(?:der|des|von|vom|ihre[rs]?|seine[rs]?)[ \t]+[\wäöüß.\-]+)?"
                                  r"[ \t]*(?P<ankuendigung>[:=]|\t\t)?[ \t]*")
# Etiketten, hinter denen ein Wert auch ohne Doppelpunkt steht ("KiSt ev", "Konf. rk", "Kirchensteuer ev 9 %") – hinter
# "Bekenntnis", "Kirche", "Rel." nur mit Doppelpunkt ("ein klares Bekenntnis ev. zu …": eventuell)
_RELIGION_OHNE_DOPPELPUNKT_RE = re.compile(r"(?i)kist|ki\.?[ ]?st|kirchensteuer|konf|religion$")
_RELIGION_FOLGE_RE = re.compile(r"[ \t]*(?:/|,|;|und|u\.)[ \t]*")
_RELIGION_ZEILEN = 40             # so viele Zeilen unter einem Spaltenkopf "Konf." werden gelesen


def _religion_wert(text: str, i: int):
    """(start, ende) eines Bekenntnisses ab i (Kürzel oder ausgeschriebenes Wort) oder None."""
    m = _RELIGION_WERT_RE.match(text, i)
    if m is not None:
        return m.start(), m.end()
    m = _RELIGION_KUERZEL_RE.match(text, i)
    if m is not None:
        return m.start(), m.end()
    return None


def religion(text: str) -> list:
    """(start, ende) der Angaben zur Religion bzw. Konfession (Art. 9 DSGVO): Wert hinter einem Etikett
    ("Konfession: römisch-katholisch", "Kirchensteuermerkmale: rk/ev", "KiSt ev", "Konf.: rk") und unter einem
    Spaltenkopf ("Konf." ⇥⇥ … , darunter in derselben Zelle "rk"). Nur Bekenntnisse und die Kirchensteuermerkmale –
    nicht "Konfession: keine Angabe", "KiSt 28,08 EUR", "Ev. Krankenhaus", "rk-Wert"."""
    if not _RELIGION_ETIKETT_RE.search(text):
        return []
    aus = []
    for m in _RELIGION_ETIKETT_RE.finditer(text):
        t = _RELIGION_TRENNER_RE.match(text, m.end())
        if t is None:
            continue
        if t.group("ankuendigung") is None and (t.group(0).strip()
                                                 or not _RELIGION_OHNE_DOPPELPUNKT_RE.match(m.group(0))):
            continue
        i = t.end()
        for _ in range(3):                              # "rk/ev", "ev, rk"
            w = _religion_wert(text, i)
            if w is None:
                break
            aus.append(w)
            f = _RELIGION_FOLGE_RE.match(text, w[1])
            if f is None:
                break
            i = f.end()
    if "\t\t" in text:
        aus += _religion_spalten(text)
    return sorted(set(aus))


def _religion_spalten(text: str) -> list:
    """Werte unter einem Spaltenkopf "Konf."/"Konfession"/"KiSt" (Zellen durch "⇥⇥" getrennt): in den folgenden
    Zeilen die Zelle mit derselben Nummer, wenn sie ein Bekenntnis bzw. Kirchensteuermerkmal ist."""
    aus = []
    zeilen = []
    pos = 0
    for zeile in text.split("\n"):
        zeilen.append((pos, zeile))
        pos += len(zeile) + 1
    for zi, (z0, zeile) in enumerate(zeilen):
        if "\t\t" not in zeile:
            continue
        zellen = zeile.split("\t\t")
        koepfe = [k for k, zelle in enumerate(zellen) if _RELIGION_KOPF_RE.fullmatch(zelle.strip())]
        if not koepfe:
            continue
        for z1, folge in zeilen[zi + 1:zi + 1 + _RELIGION_ZEILEN]:
            if "\t\t" not in folge:
                if folge.strip():
                    break
                continue
            werte = folge.split("\t\t")
            if len(werte) != len(zellen):
                continue
            versatz = z1
            starts = []
            for w in werte:
                starts.append(versatz)
                versatz += len(w) + 2
            for k in koepfe:
                zelle = werte[k]
                kern = zelle.strip()
                if not kern:
                    continue
                a = starts[k] + zelle.index(kern)
                w = _religion_wert(text, a)
                if w is not None and w[1] == a + len(kern):
                    aus.append(w)
    return aus
