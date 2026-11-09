"""wissen.namen – Personennamen aus Wissensbasis und Zusammenhang (Vertrag Abschnitt 3), ergänzt die KI ("ner").

Regeln (jede liefert Stellen der Kategorie "namen", Quelle "wissen.namen"):
  R1  "Nachname, Vorname" – auch in Versalien, mit Laufnummer davor ("2 Aßmann, Torsten"), Partikel vorn
      oder hinten ("van Dijk, Maarten", "Heyde, Anna von der"); der Vorname steht in der Liste
  R2  Vorname (Liste) + Nachname: "Sana Siddiqui", "Eckhard Freitag", "Erika Mai" (mehrdeutige Wörter nur, wenn
      der andere Teil eindeutig ein Name ist), auch über EINEN Zeilenumbruch ("Faisal⏎Patel"), unbekannter
      Vorname + bekannter Nachname ("Conceição Ferreira"), Initiale + Nachname ("A. Schmid", "V. De Luca")
  R3  Anrede/Titel + Name: "Herr Ågren", "Frau de Vries", "Frau Dr. rer. nat. von Stetten", "Herr Li"
  R4  Namen in Firmenbezeichnungen: "Werkstatt Berger", "Siddiqui & Partner GmbH", "Becker GmbH"
  R5  Personenlisten hinter Vorstand/Aufsichtsrat/Geschäftsführer (Fußzeilen der Versicherer)
  R6  Rolle + Name im Satz: "Der Zeuge Patel", "der Geschäftsführer Sana Siddiqui"
  R7  Nachnamen in Internetadressen ("www.praxis-yilmaz.de")
Mehrdeutige Nachnamen (Klein, Wolf, Koch …) zählen nur mit Zusammenhang (Anrede, Vorname, Rolle).
Versicherer, Banken und Behörden der Erlaubnisliste werden nie als Name gemeldet.
"""

from __future__ import annotations

import functools
import re

from .. import wissen
from . import ALLE_PROFILE, Treffer, detektor

_GROSS = "A-ZÄÖÜÀ-ÖØ-ÞĀĂĄĆČĎĐĒĖĘĚĞĢĪĮİĶĹĻĽŁŃŅŇŌŐŒŔŘŚŞŠŢŤŪŮŰŲŹŻŽȘȚ"
_KLEIN = "a-zäöüßà-öø-ÿāăąćčďđēėęěğģīįıķĺļľłńņňōőœŕřśşšţťūůűųźżžșț"
_TOKEN_RE = re.compile(f"(?<![{_KLEIN}{_GROSS}0-9])[{_KLEIN}{_GROSS}][{_KLEIN}{_GROSS}'’]*(?:-[{_KLEIN}{_GROSS}][{_KLEIN}{_GROSS}'’]*)*\\.?")
_PARTIKEL = {"von", "van", "de", "der", "den", "dem", "di", "da", "del", "della", "du", "le", "la", "ter", "ten",
             "zu", "zum", "zur", "vom", "dos", "das", "al", "el", "bin", "ibn", "y", "freiherr", "freifrau", "graf",
             "gräfin", "und", "op", "het", "'t", "d'", "mac", "mc", "st."}
_PARTIKEL_GROSS = {"De", "Di", "Da", "Del", "Della", "Van", "Von", "Dos", "Du", "Le", "La", "El", "Al", "Ter", "Ten",
                   "Mac", "Mc", "Bin", "Ibn"}
_ANREDE_RE = re.compile(r"(?<![\wäöüß])(?:Herrn?|Frau|Fräulein|Hr\.|Fr\.|HERRN?|FRAU|Mr\.|Mrs\.|Ms\.|Monsieur|Madame|"
                        r"Signor[ae]?|Señora?|Pan|Pani)[ \t]+$")
_TITEL_RE = re.compile(r"(?:(?:Prof|Dr|Dipl|Mag|Ing|Med|Jur|Rer|Nat|Phil|Habil|Univ|Dent|Vet|RA|StB|PD|"
                       r"med|rer|nat|jur|phil|dent|vet|habil|univ|pol|oec|sc|h\.c|"
                       r"Dipl\.-(?:Ing|Kfm|Kffr|Jur|Psych|Betriebsw|Inf|Math|Phys|Chem|Biol|Päd|Soz|Volksw|Verw\.-Wiss|Ök)"
                       r"|B\.A|M\.A|M\.Sc|B\.Sc|LL\.M|MBA|PhD)\.?[ \t]+)+")
_ROLLE_RE = re.compile(
    r"(?<![\wäöüß])(?i:der|die|den|dem|des|ihr|ihre|ihren|ihrem|ihrer|unser|unsere|unseren|unserem|unserer|"
    r"mein|meine|meinen|meinem|meiner|sein|seine|seinen|seinem|seiner)[ \t]+"
    r"(?:Zeuge|Zeugin|Gutachter|Gutachterin|Sachverständige[rn]?|Geschäftsführer|Geschäftsführerin|Inhaber|Inhaberin|"
    r"Sachbearbeiter|Sachbearbeiterin|Fahrer|Fahrerin|Halter|Halterin|Mieter|Mieterin|Vermieter|Vermieterin|"
    r"Nachbar|Nachbarin|Kollege|Kollegin|Arzt|Ärztin|Hausarzt|Hausärztin|Zahnarzt|Zahnärztin|Anwalt|Anwältin|"
    r"Rechtsanwalt|Rechtsanwältin|Makler|Maklerin|Vermittler|Vermittlerin|Berater|Beraterin|Betreuer|Betreuerin|"
    r"Unfallgegner|Unfallgegnerin|Geschädigte[rn]?|Versicherungsnehmer|Versicherungsnehmerin|Antragsteller|"
    r"Antragstellerin|Patient|Patientin|Ehemann|Ehefrau|Sohn|Tochter|Mutter|Vater|Bruder|Schwester|Enkel|Enkelin|"
    r"Lebensgefährte|Lebensgefährtin|Partner|Partnerin|Mitarbeiter|Mitarbeiterin|Ansprechpartner|"
    r"Ansprechpartnerin|Kunde|Kundin|Mandant|Mandantin|Erbe|Erbin|Verstorbene[rn]?|Prokurist|Prokuristin|"
    r"Vorstand|Vorsitzende[rn]?|Bevollmächtigte[rn]?|Betroffene[rn]?)[ \t]+")
_BOARD_RE = re.compile(
    r"(?<![\wäöüß])(?:Vorstand|Vorstände|Vorstandsvorsitzende[r]?|Vorsitzende[r]?[ \t]+des[ \t]+(?:Vorstands|Aufsichtsrats|"
    r"Aufsichtsrates|Vorstandes)|Vorsitz[ \t]+(?:Aufsichtsrat|des[ \t]+Aufsichtsrats|Vorstand)|Aufsichtsrat|"
    r"Aufsichtsratsvorsitzende[r]?|Aufsichtsratsvorsitz|Vorsitzender[ \t]+des[ \t]+AR|Geschäftsführer(?:in)?|"
    r"Geschäftsführung|Geschäftsleitung|Inhaber(?:in)?|Generalbevollmächtigte[r]?|Prokurist(?:in)?|"
    r"Verantwortlich(?:[ \t]+(?:i\.[ \t]?S\.[ \t]?d\.|nach|gem\.)[^:\n]{0,30})?|V\.[ \t]?i\.[ \t]?S\.[ \t]?d\.[ \t]?P\.|"
    r"Datenschutzbeauftragte[r]?|Ombudsmann|Ombudsfrau|Vertreten[ \t]+durch)[ \t]*:[ \t]*")
_BOARD_ENDE_RE = re.compile(r"(?i:\n[ \t]*(?:USt|Ust|Umsatzsteuer|Bank|IBAN|BIC|Sitz|Registergericht|Amtsgericht|HRB|"
                            r"HRA|Handelsregister|Steuer|Telefon|Tel\.|Fax|E-Mail|www|Internet|Vorsitz|Aufsichtsrat|"
                            r"Vorstand|Geschäftsführ|Gläubiger|Seite)|\n\s*\n)")
_FIRMA_KOPF = (r"Werkstatt|Kfz-Werkstatt|Autowerkstatt|Autohaus|Kanzlei|Rechtsanwaltskanzlei|Anwaltskanzlei|Praxis|"
               r"Zahnarztpraxis|Arztpraxis|Tierarztpraxis|Physiotherapie|Ergotherapie|Logopädie|Bäckerei|Metzgerei|"
               r"Fleischerei|Malerbetrieb|Malermeister|Elektro|Elektrotechnik|Sanitär|Heizung|Dachdeckerei|"
               r"Schreinerei|Tischlerei|Zimmerei|Bestattungen|Bestattungshaus|Versicherungsmakler|Versicherungsbüro|"
               r"Versicherungsagentur|Generalagentur|Agentur|Maklerbüro|Finanzberatung|Steuerberatung|Steuerbüro|"
               r"Ingenieurbüro|Architekturbüro|Sachverständigenbüro|Gutachterbüro|Immobilien|Hausverwaltung|"
               r"Fahrschule|Friseur|Friseursalon|Salon|Gasthaus|Gaststätte|Pension|Optik|Augenoptik|Hörakustik|"
               r"Pflegedienst|Abschleppdienst|Karosseriebau|Lackiererei|Gärtnerei|Spedition|Transporte|Reinigung")
_FIRMA_VOR_RE = re.compile(rf"(?<![\wäöüß])(?:{_FIRMA_KOPF})[ \t]+(?:(?:Dr\.|Dipl\.-Ing\.)[ \t]+)?$")
_FIRMA_NACH_RE = re.compile(
    r"^[ \t]*(?:&|\+|und)[ \t]*(?:Partner|Söhne|Sohn|Co\.?|Kollegen|Kolleginnen|Tochter|Töchter)(?![\wäöüß])"
    r"|^[ \t]+(?:GmbH|KG|e\.[ \t]?K\.|OHG|GbR|UG|AG|mbH|PartG|PartGmbB)(?![\wäöüß])"
    r"|^[ \t]+(?:Bau|Elektro|Haustechnik|Immobilien|Transporte|Versicherungen|Versicherungsmakler|Finanzen|"
    r"Finanzberatung|Steuerberatung|Rechtsanwälte|Consulting|Logistik|Automobile|Autoservice|Haustechnik|"
    r"Bedachungen|Gartenbau|Holzbau|Metallbau|Malerei)[ \t]+(?:GmbH|KG|e\.[ \t]?K\.|OHG|GbR|UG|AG)(?![\wäöüß])")
_URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"']{3,120}", re.IGNORECASE)

# Wörter, die nie ein Namensteil sind (zusätzlich zu Allerweltswörtern)
_KEIN_NAME = {
    "herr", "herrn", "frau", "familie", "fam", "eheleute", "firma", "sehr", "geehrte", "geehrter", "liebe", "lieber",
    "hallo", "guten", "tag", "mit", "freundlichen", "grüßen", "gruß", "grüße", "viele", "beste", "und", "oder",
    "str", "straße", "strasse", "weg", "platz", "allee", "gasse", "ring", "damm", "postfach", "gmbh", "ag", "kg",
    "mbh", "ohg", "gbr", "se", "co", "versicherung", "versicherungen", "bank", "sparkasse", "kasse", "tel",
    "telefon", "fax", "mobil", "handy", "email", "e-mail", "iban", "bic", "nr", "nummer", "seite", "datum",
    "anlage", "anlagen", "betreff", "betr", "kunde", "kundin", "vertrag", "police", "antrag", "schaden",
    "vorsitzender", "vorsitzende", "vorstand", "aufsichtsrat", "geschäftsführer", "geschäftsführerin",
    "abteilung", "team", "service", "kundenservice", "leistung", "leistungen", "the", "of", "von", "der", "die",
    "das", "den", "dem", "des", "ein", "eine", "im", "am", "an", "in", "zu", "zum", "zur", "bei", "für", "auf",
    "januar", "februar", "märz", "april", "juni", "juli", "august", "september", "oktober", "november",
    "dezember", "montag", "dienstag", "mittwoch", "donnerstag", "samstag", "sonntag", "ihr", "ihre", "ihren",
    "ihrem", "ihrer", "sie", "wir", "uns", "unser", "unsere", "kollege", "kollegin", "kollegen", "zeuge", "zeugin",
    "dr", "prof", "med", "dipl", "ing", "rer", "nat", "jur", "dent", "hausnummer", "ort", "plz", "name", "vorname",
    "nachname", "geburtsdatum", "anschrift", "unterschrift", "stempel", "kennzeichen", "deutschland", "germany",
    "wohnhaft", "geboren", "geb", "verstorben", "jun", "sen", "junior", "senior",
}
# Marken, die wie Vorname + Nachname aussehen ("Mercedes Benz", "Seat Leon")
_MARKEN = {"mercedes", "porsche", "ferrari", "tesla", "dacia", "lamborghini", "maserati", "bugatti", "seat", "skoda",
           "opel", "ford", "fiat", "renault", "peugeot", "citroen", "citroën", "toyota", "nissan", "mazda", "honda",
           "hyundai", "kia", "volvo", "audi", "bmw", "vw", "volkswagen", "mini", "smart", "cupra", "suzuki",
           "mitsubishi", "subaru", "jeep", "jaguar", "lancia", "alfa", "chevrolet", "chrysler", "dodge", "saab",
           "lexus", "infiniti", "genesis", "polestar", "byd", "mg", "lada"}
# Etiketten, hinter denen kein Personenname steht (Gutachten EQ-04): Typ, Hersteller, Tarif, Beruf …
_SACH_ETIKETT_RE = re.compile(
    r"(?<![\wäöüß])(?:Beruf|Tätigkeit|Berufsbezeichnung|Tarif|Tarifname|Produkt|Produktname|Sparte|Marke|Typ|"
    r"Modell|Hersteller|Fahrzeug|Fahrzeugtyp|Diagnose|Verwendungszweck|Leistungsart|Optionen|Bausteine?|"
    r"Deckung|Zahlweise|Vertragsart|Versicherungsart|Dokumentart|Status|Kostenträger|Versicherer|Gesellschaft|"
    r"Krankenkasse|Bank|Kreditinstitut|Arbeitgeber|Firma)(?:[ \t]*/[ \t]*[\wäöüß]+)?[ \t]*:?[ \t]*$")


def _sach_etikett_davor(text: str, start: int) -> bool:
    """Steht die Stelle direkt hinter einem Sach-Etikett ("Hersteller/Typ: Seat Leon")?"""
    a = text.rfind("\n", 0, start) + 1
    return bool(_SACH_ETIKETT_RE.search(text[max(a, start - 60):start]))
_STRASSENENDE_RE = re.compile(r"(?i:straße|strasse|str\.?|weg|platz|allee|gasse|ring|damm|ufer|markt|chaussee)$")


@functools.lru_cache(maxsize=65536)
def _art(wort: str) -> tuple:
    """(vorname, vorname_mehrdeutig, nachname, nachname_mehrdeutig, allerweltswort, allowlist) eines Worts."""
    w = wort.rstrip(".")
    if not w:
        return (False,) * 6
    try:
        vor = wissen.ist_vorname(w)
        vor_m = vor and wissen.ist_vorname_mehrdeutig(w)
        nach = wissen.ist_nachname(w)
        nach_m = nach and wissen.ist_mehrdeutig(w)
        allerwelt = wissen.ist_allerweltswort(w) if len(w) >= 4 else False
        allow = wissen.ist_allowlist(w)
    except Exception:  # pragma: no cover - Wissensbasis fehlt
        return (False,) * 6
    return vor, vor_m, nach, nach_m, allerwelt, allow


def _ist_gross(wort: str) -> bool:
    return bool(wort) and wort[0].isupper()


def _versal(wort: str) -> bool:
    buchstaben = [c for c in wort if c.isalpha()]
    return len(buchstaben) >= 2 and all(c.isupper() for c in buchstaben)


def _sicherer_vorname(wort: str) -> bool:
    vor, vor_m, nach, nach_m, allerwelt, allow = _art(wort)
    return vor and not vor_m and not allow and wort.rstrip(".").casefold() not in _KEIN_NAME


def _sicherer_nachname(wort: str) -> bool:
    vor, vor_m, nach, nach_m, allerwelt, allow = _art(wort)
    return nach and not nach_m and not allow and wort.rstrip(".").casefold() not in _KEIN_NAME


def _nachname_moeglich(wort: str, streng: bool) -> bool:
    """Kann das Wort ein Nachname sein? streng=False (Kontext stark): jedes großgeschriebene Wort außer
    Allerweltswörtern/Stoppwörtern/Straßen; bekannte Nachnamen (auch mehrdeutige) immer."""
    w = wort.rstrip(".")
    if len(w) < 2 or not _ist_gross(w) or w.casefold() in _KEIN_NAME or _STRASSENENDE_RE.search(w):
        return False
    vor, vor_m, nach, nach_m, allerwelt, allow = _art(w)
    if allow:
        return False
    if nach:
        return True
    if streng:
        return False
    return not allerwelt and len(w) >= 3


class _Token:
    __slots__ = ("start", "ende", "text", "naechster_trenner")

    def __init__(self, start, ende, text):
        self.start, self.ende, self.text = start, ende, text
        self.naechster_trenner = ""


def _tokens(text: str) -> list:
    aus = [_Token(m.start(), m.end(), m.group(0)) for m in _TOKEN_RE.finditer(text)]
    for a, b in zip(aus, aus[1:]):
        a.naechster_trenner = text[a.ende:b.start]
    return aus


def _trenner_ok(trenner: str, umbruch: bool) -> bool:
    if trenner in (" ", "\t"):
        return True
    if umbruch and trenner.strip(" \t") == "\n" and trenner.count("\n") == 1:
        return True
    return False


def _partikel(wort: str) -> bool:
    return wort.casefold() in _PARTIKEL or wort in _PARTIKEL_GROSS


def _treffer(s, e, text, si, gruppe=None) -> Treffer:
    return Treffer(s, e, "namen", "wissen.namen", si, gruppe)


# ----------------------------------------------------------------------
# R1 "Nachname, Vorname"
# ----------------------------------------------------------------------
_W = f"[{_GROSS}][{_KLEIN}{_GROSS}'’]*(?:-[{_GROSS}{_KLEIN}][{_KLEIN}{_GROSS}'’]*)*"
_PART_RE = r"(?:(?:von|van|de|der|den|di|da|del|della|du|le|la|ter|ten|zu|zum|zur|vom|al|el|Freiherr|Freifrau|Graf|" \
           r"VON|VAN|DE|DER|DEN|FREIHERR|FREIFRAU|GRAF|ZU|VOM)[ \t]+)"
_KOMMA_RE = re.compile(
    rf"(?<![{_KLEIN}{_GROSS}\-])(?P<nach>{_PART_RE}*{_W}(?:[ \t]+{_W})?)[ \t]*,[ \t]*(?:\n[ \t]*)?"
    rf"(?P<vor>{_W}(?:[ \t]+{_W})?)(?P<partikel>(?:[ \t]+(?:von|van|de|der|den|di|da|zu|zum|zur|vom|ter|ten)"
    rf"(?:[ \t]+(?:der|den|dem|de|la))?)?)(?![{_KLEIN}{_GROSS}])")


def _komma_namen(text: str) -> list:
    aus = []
    for m in _KOMMA_RE.finditer(text):
        nach, vor = m.group("nach"), m.group("vor")
        vor_woerter = vor.split()
        nach_woerter = [w for w in nach.split() if not _partikel(w)] or nach.split()[-1:]   # "GRAF, LISELOTTE"
        if "\n" in text[m.end("nach"):m.start("vor")] and not (_versal(vor) or _art(nach_woerter[-1])[2]):
            continue                                       # Komma am Zeilenende: nur Versalien/bekannter Nachname
        if not nach_woerter or not vor_woerter:
            continue
        erster_vor = vor_woerter[0]
        if not (_art(erster_vor)[0] and not _art(erster_vor)[5]):
            continue                                       # Vorname muss bekannt sein
        s = m.start("nach")
        if len(nach_woerter) == 2 and not (nach.split()[0] in _PARTIKEL_GROSS
                                           or all(_art(w)[2] for w in nach_woerter)):
            # "München Biedermann, Liselotte": nur das letzte Wort gehört zum Namen
            s = m.start("nach") + nach.rindex(nach_woerter[-1])
            nach_woerter = nach_woerter[-1:]
        if _ANREDE_RE.search(text[max(0, s - 12):s]) or nach.split()[0].casefold() in ("herr", "herrn", "frau"):
            continue                                       # "Frau Krüger, Max Mustermann …" (Gutachten EQ-10)
        if any(w.casefold() in _KEIN_NAME or _art(w)[4] and not _art(w)[2] for w in nach_woerter):
            continue
        vor_gekuerzt = len(vor_woerter) == 2 and not (_art(vor_woerter[1])[0] or _versal(vor_woerter[1]))
        if vor_gekuerzt:
            vor_ende = m.start("vor") + len(vor_woerter[0])
        else:
            vor_ende = m.end("vor")
        nach_bekannt = any(_art(w)[2] for w in nach_woerter)
        vor_mehrdeutig = _art(erster_vor)[1]
        zeilenanfang = text.rfind("\n", 0, m.start()) + 1
        davor = text[zeilenanfang:m.start()]
        zellenanfang = (not davor.strip() or davor.endswith("\t") or re.fullmatch(r"[ \t]*\d{1,4}\.?[ \t]+", davor)
                        or davor.rstrip().endswith(":"))
        if vor_mehrdeutig and not nach_bekannt:
            continue
        if not nach_bekannt and not zellenanfang:
            continue                                       # unbekannter Nachname nur am Zeilen-/Zellenanfang
        if any(_STRASSENENDE_RE.search(w) for w in nach_woerter):
            continue
        if _sach_etikett_davor(text, s):
            continue
        # Aufzählung "Dirk Weber, Faisal Patel": vor dem Nachnamen steht ein Vorname bzw. hinter dem Vornamen ein
        # bekannter Nachname -> zwei Personen, kein "Nachname, Vorname"
        davor_wort = re.search(rf"([{_GROSS}][{_KLEIN}]+)[ \t]+$", text[max(0, s - 40):s])
        if len(nach_woerter) == 1 and davor_wort and _sicherer_vorname(davor_wort.group(1)):
            continue
        danach_wort = re.match(rf"[ \t\n]+([{_GROSS}][{_KLEIN}{_GROSS}'’\-]+)", text[vor_ende:vor_ende + 40])
        if not vor_gekuerzt and danach_wort and _art(danach_wort.group(1))[2] and not _art(danach_wort.group(1))[0] \
                and not _versal(vor):
            continue
        ende = m.end("partikel") if m.group("partikel") and not vor_gekuerzt else vor_ende
        voll = text[s:ende]
        aus.append(_treffer(s, ende, text, 0.75 if nach_bekannt else 0.65, voll))
    return aus


# ----------------------------------------------------------------------
# R2 Vorname + Nachname, Initiale + Nachname, unbekannter Vorname + bekannter Nachname
# ----------------------------------------------------------------------
def _vorname_nachname(text: str, tokens: list) -> list:
    aus = []
    n = len(tokens)
    i = 0
    while i < n:
        t = tokens[i]
        w = t.text.rstrip(".")
        start = None
        if _ist_gross(w) and len(w) >= 2:
            vor, vor_m, nach, nach_m, allerwelt, allow = _art(w)
            if vor and not allow and w.casefold() not in _KEIN_NAME:
                start = i
        if start is None:
            i += 1
            continue
        # weitere Vornamen ("Frank Dieter Köhler", "Anna-Lena Maria Schmidt")
        j = i
        vornamen = [i]
        while j + 1 < n and len(vornamen) < 3 and _trenner_ok(tokens[j].naechster_trenner, False) \
                and _ist_gross(tokens[j + 1].text) and _art(tokens[j + 1].text.rstrip("."))[0] \
                and not _art(tokens[j + 1].text.rstrip("."))[2]:
            j += 1
            vornamen.append(j)
        # Partikel
        k = j
        partikel = []
        while k + 1 < n and _trenner_ok(tokens[k].naechster_trenner, False) and _partikel(tokens[k + 1].text) \
                and len(partikel) < 3:
            k += 1
            partikel.append(k)
        if k + 1 >= n:
            i = j + 1
            continue
        umbruch_erlaubt = not partikel
        trenner = tokens[k].naechster_trenner
        if not _trenner_ok(trenner, umbruch_erlaubt):
            i = j + 1
            continue
        nt = tokens[k + 1]
        nw = nt.text.rstrip(".")
        alle_vor_mehrdeutig = all(_art(tokens[x].text.rstrip("."))[1] for x in vornamen)
        nach_bekannt = _art(nw)[2]
        if "\n" in trenner and (not (nach_bekannt and not _art(nw)[3] and not alle_vor_mehrdeutig)
                                or _versal(t.text) or _versal(nw)):
            i = j + 1
            continue                                         # über einen Umbruch nur eindeutige Namen
        if alle_vor_mehrdeutig and (not nach_bekannt or w.casefold() in _MARKEN):
            i = j + 1
            continue                                         # "Rosa Beispiel": mehrdeutig ohne bekannten Nachnamen
        versal = _versal(t.text) or _versal(nw)
        gemischt = (not _versal(t.text) and _versal(nw) and not alle_vor_mehrdeutig and len(nw) >= 3
                    and nw.isalpha() and not _art(nw)[5])           # "Holger EHRLICH": Nachname in Versalien
        if versal and not gemischt and not (nach_bekannt and _art(w)[0] and _versal(t.text) == _versal(nw)):
            i = j + 1
            continue                                         # Versalien nur, wenn beide Teile Listen-Namen sind
        if not _nachname_moeglich(nw, streng=False) or w.casefold() in _MARKEN or _sach_etikett_davor(text, t.start):
            i = j + 1
            continue
        if not nach_bekannt and (partikel == [] and _art(nw)[0] and not _art(nw)[2]):
            i = j + 1
            continue                                         # zwei Vornamen ohne Nachnamen
        s, e = t.start, nt.ende
        if nt.text.endswith(".") and not nt.text[:-1].isupper():
            e -= 1
        si = 0.75 if nach_bekannt and not alle_vor_mehrdeutig else 0.6
        if "\n" in trenner:
            # über einen Zeilenumbruch ("Faisal⏎Patel"): je Zeile eine Stelle, gemeinsam als eine Person
            voll = " ".join(text[s:e].split())
            aus.append(_treffer(s, tokens[k].ende, text, si, voll))
            aus.append(_treffer(nt.start, e, text, si, voll))
        else:
            aus.append(_treffer(s, e, text, si))
        i = k + 2
    return aus


_INITIALE_RE = re.compile(rf"(?<![{_KLEIN}{_GROSS}.])([{_GROSS}])\.(?:[ \t]?[{_GROSS}]\.)?[ \t]?"
                          rf"((?:(?:de|De|di|Di|van|Van|von|da|Da|del|Del|le|Le|La)[ \t]+)?{_W})")


def _initiale_nachname(text: str) -> list:
    aus = []
    for m in _INITIALE_RE.finditer(text):
        name = m.group(2)
        teile = name.split()
        kern = teile[-1]
        mit_partikel = len(teile) > 1
        if _sicherer_nachname(kern) or (mit_partikel and _art(kern)[2]) or \
                (mit_partikel and _nachname_moeglich(kern, streng=False)):
            if re.match(r"[ \t]*(?:\d|[a-zäöü])", text[m.end():m.end() + 2]) and not mit_partikel:
                pass
            aus.append(_treffer(m.start(), m.end(), text, 0.65))
    return aus


def _unbekannter_vorname(text: str, tokens: list) -> list:
    """"Conceição Ferreira": großgeschriebenes Wort (kein Allerweltswort, kein Ort-/Straßenwort) direkt vor einem
    eindeutigen Nachnamen der Liste, am Zeilen-/Zellenanfang oder hinter einem Komma/Doppelpunkt."""
    aus = []
    for a, b in zip(tokens, tokens[1:]):
        if a.naechster_trenner not in (" ", "\t"):
            continue
        if not _sicherer_nachname(b.text.rstrip(".")):
            continue
        w = a.text
        if not _ist_gross(w) or _versal(w) or len(w) < 3 or w.casefold() in _KEIN_NAME or _art(w)[4] or _art(w)[5]:
            continue
        if w.endswith(".") or _TITEL_RE.match(w + " ") or wissen.ist_anrede_titel(w):
            continue                                         # "Dr. Müller": Titel, kein Vorname
        if w.casefold() in _MARKEN or _sach_etikett_davor(text, a.start):
            continue                                         # "Hersteller/Typ: Seat Leon"
        if _art(w)[0] or _art(w)[2]:
            continue                                         # bekannte Namen erledigt R2
        if wissen.ist_beruf(w) or re.match(_FIRMA_KOPF + r"$", w) or re.search(
                r"(?:ung|heit|keit|schaft|büro|makler|amt|kasse|verband|verein|gesellschaft|zentrum|haus)$", w):
            continue                                         # "Versicherungsmakler Siddiqui": Beruf/Firma
        davor = text[text.rfind("\n", 0, a.start) + 1:a.start]
        if davor.strip() and not davor.rstrip().endswith((",", ":", ";", "\t")) and not davor.endswith("\t"):
            continue
        aus.append(_treffer(a.start, b.ende, text, 0.55))
    return aus


# ----------------------------------------------------------------------
# R3 Anrede/Titel + Name
# ----------------------------------------------------------------------
_ANREDE_NAME_RE = re.compile(
    rf"(?<![\wäöüß])(?:Herrn?|Frau|Fräulein|Hr\.|Fr\.|HERRN?|FRAU)[ \t]+(?:{_TITEL_RE.pattern})?"
    rf"(?P<name>(?:(?:von|van|de|der|den|di|da|del|della|du|le|la|ter|ten|zu|zum|zur|vom|al|el|De|Di|Da|Del|Van|Von|"
    rf"Le|La|Dos|El|Al)[ \t]+){{0,3}}[{_GROSS}][{_KLEIN}{_GROSS}'’]*(?:-[{_GROSS}{_KLEIN}][{_KLEIN}{_GROSS}'’]*)*"
    rf"(?:[ \t]+[{_GROSS}][{_KLEIN}{_GROSS}'’]*(?:-[{_GROSS}][{_KLEIN}{_GROSS}'’]*)*)?)")


def _anrede_namen(text: str) -> list:
    aus = []
    for m in _ANREDE_NAME_RE.finditer(text):
        name = m.group("name")
        woerter = name.split()
        kern = [w for w in woerter if not _partikel(w)]
        if not kern:
            continue
        # zweites Wort nur, wenn es ein Name sein kann ("Frau Anna Schmidt", nicht "Frau Schmidt Sie")
        if len(kern) == 2 and not (_art(kern[1])[2] or (_art(kern[0])[0] and _nachname_moeglich(kern[1], False))):
            ende_wort = m.start("name") + name.index(kern[0]) + len(kern[0])
            kern = kern[:1]
        else:
            ende_wort = m.end("name")
        letzter = kern[-1]
        if letzter.casefold() in _KEIN_NAME or _art(letzter)[5]:
            continue
        if len(letzter) == 2 and not _art(letzter)[2]:
            continue                                         # zwei Buchstaben nur als bekannter Nachname (Li, Wu)
        if len(kern) == 1 and _art(letzter)[4] and not _art(letzter)[2] and not _art(letzter)[0]:
            continue                                         # "Frau Kollegin", "Herr Kollege"
        aus.append(_treffer(m.start("name"), ende_wort, text, 0.75))
    return aus


# ----------------------------------------------------------------------
# R4 Namen in Firmenbezeichnungen
# ----------------------------------------------------------------------
def _firmen_namen(text: str, tokens: list) -> list:
    aus = []
    for t in tokens:
        w = t.text.rstrip(".")
        if len(w) < 3:
            continue
        vor, vor_m, nach, nach_m, allerwelt, allow = _art(w)
        if not nach or allow or w.casefold() in _KEIN_NAME:
            continue
        davor = text[max(0, t.start - 40):t.start]
        danach = text[t.ende:t.ende + 40]
        gross = _ist_gross(w)
        if _FIRMA_VOR_RE.search(davor) and (gross or not nach_m):
            if re.match(r"[ \t]+(?:GmbH|AG|KG|SE)(?![\wäöüß])", danach) and wissen.ist_allowlist(text[t.start:t.ende + 6]):
                continue
            aus.append(_treffer(t.start, t.ende - (1 if t.text.endswith(".") else 0), text, 0.65))
        elif gross and _FIRMA_NACH_RE.match(danach) and (not nach_m or re.match(r"[ \t]*(?:&|\+|und)", danach)):
            firma = text[t.start:t.ende + 30].split("\n")[0]
            if wissen.ist_allowlist(firma):
                continue
            aus.append(_treffer(t.start, t.ende - (1 if t.text.endswith(".") else 0), text, 0.65))
    return aus


# ----------------------------------------------------------------------
# R5 Personenlisten hinter Vorstand/Aufsichtsrat/Geschäftsführer
# ----------------------------------------------------------------------
_LISTEN_NAME_RE = re.compile(
    rf"(?:{_TITEL_RE.pattern})?(?P<name>(?:[{_GROSS}]\.[ \t]?)?(?:(?:von|van|de|der|den|di|da|zu|vom|De|Di|Van|Von)[ \t]+){{0,3}}"
    rf"[{_GROSS}][{_KLEIN}{_GROSS}'’]*(?:-[{_GROSS}][{_KLEIN}{_GROSS}'’]*)*"
    rf"(?:[ \t\n]+(?:(?:von|van|de|der|den|di|da|zu|vom|De|Di|Van|Von)[ \t]+){{0,3}}[{_GROSS}][{_KLEIN}{_GROSS}'’]*"
    rf"(?:-[{_GROSS}][{_KLEIN}{_GROSS}'’]*)*){{0,3}})")


def _personenlisten(text: str) -> list:
    aus = []
    for m in _BOARD_RE.finditer(text):
        ende_m = _BOARD_ENDE_RE.search(text, m.end(), min(len(text), m.end() + 400))
        ende = ende_m.start() if ende_m else min(len(text), m.end() + 400)
        abschnitt = text[m.end():ende]
        pos = 0
        for teil in re.split(r"(,|;|\bund\b|\bsowie\b|·|\|)", abschnitt):
            if teil in (",", ";", "und", "sowie", "·", "|") or not teil.strip():
                pos += len(teil)
                continue
            roh = re.sub(r"\([^)]*\)?", lambda x: " " * len(x.group(0)), teil)   # "(Vorsitzender)" weg
            n = _LISTEN_NAME_RE.search(roh)
            if n:
                name = n.group("name").rstrip()
                woerter = [w for w in name.split() if not _partikel(w) and not re.fullmatch(rf"[{_GROSS}]\.", w)]
                if woerter and 1 <= len(woerter) <= 4 and not any(w.casefold() in _KEIN_NAME for w in woerter) \
                        and not wissen.ist_allowlist(name) and (len(woerter) >= 2 or _art(woerter[0])[2]) \
                        and not (len(woerter) == 1 and (len(woerter[0]) < 3 or _versal(woerter[0]))) \
                        and not any(_STRASSENENDE_RE.search(w.rstrip(".")) or len(w) < 2 for w in woerter) \
                        and (any(_art(w)[0] or _art(w)[2] for w in woerter)
                             or not any(_art(w)[4] or _versal(w) for w in woerter)):
                    s = m.end() + pos + n.start("name")
                    if "\n" in name:
                        # Name über einen Zeilenumbruch ("Faisal⏎Patel"): je Zeile eine Stelle, eine Person
                        voll = " ".join(name.split())
                        teil_start = s
                        for zeile in name.split("\n"):
                            if zeile.strip():
                                z0 = teil_start + (len(zeile) - len(zeile.lstrip()))
                                aus.append(_treffer(z0, z0 + len(zeile.strip()), text, 0.7, voll))
                            teil_start += len(zeile) + 1
                    else:
                        aus.append(_treffer(s, s + len(name), text, 0.7))
            pos += len(teil)
    return aus


# ----------------------------------------------------------------------
# R6 Rolle + Name im Satz
# ----------------------------------------------------------------------
_ROLLE_NAME_RE = re.compile(
    _ROLLE_RE.pattern + rf"(?:(?:Herrn?|Frau)[ \t]+)?(?:{_TITEL_RE.pattern})?(?P<name>(?:(?:von|van|de|der|di|da|De|Di|Van|Von)[ \t]+)?"
    rf"[{_GROSS}][{_KLEIN}{_GROSS}'’]*(?:-[{_GROSS}][{_KLEIN}{_GROSS}'’]*)*(?:[ \t]+[{_GROSS}][{_KLEIN}{_GROSS}'’]*"
    rf"(?:-[{_GROSS}][{_KLEIN}{_GROSS}'’]*)*)?)")


def _rollen_namen(text: str) -> list:
    aus = []
    for m in _ROLLE_NAME_RE.finditer(text):
        name = m.group("name")
        s = m.start("name")
        erstes = name.split()[0]
        if _partikel(erstes) and erstes.islower() and len(name.split()) > 1 and _art(name.split()[1])[0]:
            # "die Ehefrau von Thomas Weber": "von" ist hier Präposition, kein Namensteil
            s += len(erstes) + (len(name) - len(name[len(erstes):].lstrip()) - len(erstes))
            name = name[len(erstes):].lstrip()
        woerter = [w for w in name.split() if not _partikel(w)]
        if not woerter:
            continue
        if len(woerter) == 2 and not _nachname_moeglich(woerter[1], streng=not _art(woerter[0])[0]):
            woerter = woerter[:1]
            name = name[:name.index(woerter[0]) + len(woerter[0])]
        kern = woerter[-1]
        if kern.casefold() in _KEIN_NAME or _art(kern)[5]:
            continue
        if len(woerter) == 1 and not (_art(kern)[2] or (_art(kern)[0] and not _art(kern)[1])):
            continue                                         # ein Wort: nur bekannter Name ("Der Zeuge Patel hat")
        if _art(kern)[4] and not _art(kern)[2]:
            continue
        aus.append(_treffer(s, s + len(name), text, 0.7))
    return aus


# ----------------------------------------------------------------------
# R7 Internetadressen
# ----------------------------------------------------------------------
def _url_namen(text: str) -> list:
    aus = []
    for m in _URL_RE.finditer(text):
        url = m.group(0)
        for teil in re.finditer(r"[A-Za-zäöüÄÖÜß]{4,}", url):
            w = teil.group(0)
            if w.lower() in ("http", "https", "www", "praxis", "kanzlei", "versicherung", "online", "service",
                             "kontakt", "info", "home", "index", "html", "mail"):
                continue
            kandidat = w[:1].upper() + w[1:]
            if _sicherer_nachname(kandidat) and len(w) >= 4:
                s = m.start() + teil.start()
                aus.append(_treffer(s, s + len(w), text, 0.6))
    return aus


def namen_stellen(text: str) -> list:
    """Alle Namens-Treffer der Regeln R1–R7 (Treffer mit Offsets im Text)."""
    if not text:
        return []
    tokens = _tokens(text)
    treffer = []
    treffer += _komma_namen(text)
    treffer += _vorname_nachname(text, tokens)
    treffer += _initiale_nachname(text)
    treffer += _unbekannter_vorname(text, tokens)
    treffer += _anrede_namen(text)
    treffer += _firmen_namen(text, tokens)
    treffer += _personenlisten(text)
    treffer += _rollen_namen(text)
    treffer += _url_namen(text)
    aus, gesehen = [], set()
    for t in sorted(treffer, key=lambda t: (t.start, t.ende, -t.sicherheit)):
        s, e = t.start, t.ende
        while e > s and text[e - 1] in " \t\n,.;:":
            e -= 1
        if e - s < 2 or (s, e) in gesehen:
            continue
        gesehen.add((s, e))
        aus.append(t._replace(ende=e))
    return aus


@detektor("wissen.namen", {"namen"}, ALLE_PROFILE)
def wissen_namen(dok, kontext):
    """Personennamen aus Wissensbasis + Zusammenhang (ergänzt die KI-Erkennung)."""
    return namen_stellen(dok.text)


# ----------------------------------------------------------------------
# Unbekannte Eigennamen (Vertrag Abschnitt 3: nur Schutzstufe „maximal“ automatisch, sonst Restrisiko)
# ----------------------------------------------------------------------
_PERSONENZEILE_RE = re.compile(
    r"(?<![\wäöüß])(?:Herrn?|Frau|Name|Nachname|Vorname|Versicherungsnehmer(?:in)?|Versicherte[r]?|"
    r"Antragsteller(?:in)?|Kunde|Kundin|Patient(?:in)?|Zeuge|Zeugin|Fahrer(?:in)?|Halter(?:in)?|Mieter(?:in)?|"
    r"Unfallgegner(?:in)?|Geschädigte[r]?|Kontoinhaber(?:in)?|Bevollmächtigte[r]?|Ehepartner(?:in)?|Kind|"
    r"Sohn|Tochter|Mutter|Vater|gez\.|i\.[ \t]?A\.|i\.[ \t]?V\.|Unterschrift)(?![\wäöüß])")


# „Typ 2“, „Grad II“, „Stadium IV“: Bezeichnung mit Nummer, kein Name (auch in Diagnosen hinter der Listenangabe)
_BEZEICHNUNGEN = {"typ", "grad", "schweregrad", "stadium", "stufe", "klasse", "phase", "gruppe", "pflegegrad"}
_BEZEICHNUNG_NUMMER_RE = re.compile(r"[ \t]+(?:\d{1,2}|[IVX]{1,4})[a-c]?(?![\w.,])")
# Innerhalb einer Gesundheitsangabe ist ein Wort nur nach „bei“ oder einer Anrede ein Name („… bei Herrn Meier“)
_PERSON_DAVOR_RE = re.compile(r"(?<![\wäöüß])(?:bei|Herrn?|Frau|Hr\.|Fr\.|Dr\.|Prof\.)"
                              r"(?:[ \t]+[A-ZÄÖÜ][\wäöüß'’\-]*\.?){0,2}[ \t]+$")


def _gesundheit_spannen(text: str) -> list:
    """Spannen von Diagnosen/Medikamenten: Listeneinträge der Wissensbasis und die ganzen erkannten Angaben
    (wissen_kontext, mit Erweiterungen wie „Obstruktives …“, „…, Ein-Gefäß-Erkrankung (I25.11)“)."""
    from . import wissen_kontext                       # spät importiert: Ladereihenfolge der Detektor-Module
    spannen = [(v.start, v.ende) for liste in ("diagnosen", "medikamente") for v in wissen.index(liste).finde(text)]
    return spannen + wissen_kontext.diagnosen_stellen(text) + wissen_kontext.medikamente_stellen(text)


def unbekannte_eigennamen(text: str) -> list:
    """Großgeschriebene Wörter in Personenzeilen, die weder Allerweltswort noch Erlaubnisliste, Beruf, Diagnose,
    Titel, Etikett oder Satzanfang sind ("Name: Xyzzab Qwonk"). Wörter innerhalb einer Diagnose oder eines
    Medikaments („Morbus Crohn“, „Diabetes mellitus Typ 2“, „Obstruktives Schlafapnoe-Syndrom“) sind keine Namen,
    außer nach „bei“ oder einer Anrede („… bei Herrn Xyzzab“); Bezeichnungen mit Nummer („Grad II“) auch nicht –
    sonst stünde in einer abgewählten, also lesbaren Diagnose „Morbus [PERSON B]“."""
    aus = []
    gesundheit = None                                   # Spannen von Diagnosen/Medikamenten, erst bei Bedarf
    for zeile_m in re.finditer(r"[^\n]+", text):
        zeile = zeile_m.group(0)
        if not _PERSONENZEILE_RE.search(zeile):
            continue
        for t in _TOKEN_RE.finditer(zeile):
            w = t.group(0).rstrip(".")
            s = zeile_m.start() + t.start()
            if len(w) < 3 or not _ist_gross(w) or (_versal(w) and len(w) <= 4) or w.casefold() in _KEIN_NAME:
                continue
            if s == zeile_m.start() or re.search(r"[.!?]\s*$", text[max(0, s - 3):s]) \
                    or re.match(r"[ \t]*:", text[s + len(w):s + len(w) + 2]):
                continue                                       # Zeilen-/Satzanfang oder selbst ein Etikett
            vor_, vor_m, nach, nach_m, allerwelt, allow = _art(w)
            if allerwelt or allow or _PERSONENZEILE_RE.fullmatch(w) or wissen.ist_beruf(w) \
                    or wissen.ist_diagnose(w) or wissen.ist_anrede_titel(w) or _STRASSENENDE_RE.search(w) \
                    or re.match("(?:" + _FIRMA_KOPF + ")$", w) or w.casefold() in _MARKEN:
                continue
            if w.casefold() in _BEZEICHNUNGEN and _BEZEICHNUNG_NUMMER_RE.match(text, s + len(w)):
                continue
            if gesundheit is None:
                gesundheit = _gesundheit_spannen(text)
            if any(a <= s and s + len(w) <= b for a, b in gesundheit) \
                    and not _PERSON_DAVOR_RE.search(text[max(0, s - 60):s]):
                continue
            aus.append(_treffer(s, s + len(w), text, 0.4))
    return aus


@detektor("unbekannte_eigennamen", {"namen"}, frozenset({"maximal"}))
def eigennamen_maximal(dok, kontext):
    """Nur Schutzstufe „maximal“: unbekannte Eigennamen in Personenzeilen (sonst meldet sie die Restrisiko-Prüfung)."""
    return [t._replace(quelle="unbekannte_eigennamen") for t in unbekannte_eigennamen(dok.text)]
