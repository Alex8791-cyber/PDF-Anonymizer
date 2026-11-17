"""Kennungen mit eigener Wertform hinter ihrem Etikett – eVB-Nummer und Transferticket der Kfz-Versicherung,
Kartenprüfnummer (CVC/CVV) einer Zahlungskarte – und der Geburtsname hinter seinem Feld-Etikett.

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
                        ohne_ankuendigung: int = 0, kennung: bool = False) -> Wertfund | None:
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
    nur hinter neutralen Zwischenwörtern (kennung_neutral: nicht "Transferticket Hotline 0800-1234567")."""
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
            if kennung and woerter and fremder_gegenstand(_letztes_wort(text, pos, k)):
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
        if woerter and _eigenes_etikett(text, k):
            return None
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
