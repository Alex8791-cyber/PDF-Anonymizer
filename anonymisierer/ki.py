"""KI-Zweitprüfung über LM Studio – nur auf dem eigenen Rechner.

Das Programm fragt den lokalen LM-Studio-Server, welches Sprachmodell gerade geladen ist, und nutzt genau dieses
(heute z. B. ein Qwen-Modell, morgen ein anderes – ohne Einstellung). Zwei Aufgaben:

1. Zweitprüfung der Analyse (detektoren/ki_zweitpruefung.py): Das Modell liest den Text jeder Seite und nennt
   personenbezogene Daten. Was es eindeutig erkennt und was wörtlich im Text steht, wird wie ein Fund der Regeln
   geschwärzt.
2. Entscheidung unklarer Verdachtsfälle der Selbstkontrolle (verdacht_filtern): Stellen, die die Regeln nur
   vorsichtshalber melden („Regen“ – Name oder Wetter?), beurteilt das Modell im Zusammenhang. Nur was es sicher
   als „kein Personenbezug“ einstuft, entfällt als Meldung – weniger, aber präzisere Meldungen.

Datenschutz: Verbunden wird ausschließlich mit dem eigenen Rechner (127.0.0.1, localhost, ::1), ohne Proxy. Eine
andere Adresse lehnt das Modul ab. Läuft LM Studio nicht oder ist kein Modell geladen, arbeitet das Programm wie
ohne KI und sagt das im Protokoll.

Schnittstellen (LM Studio): GET /api/v1/models (ab 0.4), Rückfall GET /api/v0/models und GET /v1/models;
Antworten über POST /v1/chat/completions (OpenAI-kompatibel, mit JSON-Schema, Rückfall ohne Schema).
Ein- und Ausschalten: EINSTELLUNG["aktiv"] (Oberfläche) oder Umgebungsvariable PDFA_KI=1 (Werkzeuge);
Adresse: PDFA_KI_URL (Vorgabe http://127.0.0.1:1234).
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import NamedTuple

STANDARD_URL = "http://127.0.0.1:1234"
ERLAUBTE_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
ZEIT_SUCHE_S = 2.0              # Modellabfrage (LM Studio antwortet sofort oder läuft nicht)
ZEIT_ANFRAGE_S = 240.0          # eine Antwort des Modells (großes Modell, lange Seite)
MODELL_GUELTIG_S = 60.0         # so lange gilt die Antwort auf „welches Modell ist geladen?“
MAX_ZEICHEN_TEIL = 6000         # Text je Anfrage (eine Seite, lange Seiten in Teilen)
MAX_VERDACHT_JE_ANFRAGE = 20

EINSTELLUNG = {"aktiv": False}  # von der Oberfläche gesetzt; PDFA_KI=1 schaltet für Werkzeuge ein

# Arten der Antwort -> Kategorien des Programms (Schwärzung nur in angehakten Kategorien)
ARTEN = ("name", "anschrift", "geburtsdatum", "telefon", "email", "iban", "kennung", "gesundheit")
_KATEGORIE = {"name": "namen", "geburtsdatum": "geburt", "telefon": "telefon", "email": "email", "iban": "iban",
              "kennung": "vertrag", "gesundheit": "diagnose"}


class Modell(NamedTuple):
    kennung: str                # Modellkennung für die Anfrage (wie LM Studio sie meldet)
    bild: bool = False          # Vision-Modell (kann Bilder lesen)


class KiFehler(Exception):
    """LM Studio nicht erreichbar, kein Modell geladen oder Antwort unbrauchbar."""


def aktiv() -> bool:
    """Ist die KI-Zweitprüfung eingeschaltet (Oberfläche oder PDFA_KI=1)?"""
    return bool(EINSTELLUNG.get("aktiv")) or os.environ.get("PDFA_KI", "").strip() in ("1", "ja", "an", "true")


def basis_url(url: str | None = None) -> str:
    """Adresse des LM-Studio-Servers; nur der eigene Rechner ist erlaubt (sonst ValueError)."""
    url = (url or os.environ.get("PDFA_KI_URL") or STANDARD_URL).strip().rstrip("/")
    teile = urllib.parse.urlsplit(url)
    if teile.scheme not in ("http", "https") or (teile.hostname or "").lower() not in ERLAUBTE_HOSTS:
        raise ValueError(f"KI-Adresse {url!r} ist nicht der eigene Rechner – aus Datenschutzgründen nicht erlaubt")
    return url


# Ohne Proxy: eine Anfrage an 127.0.0.1 darf nie über einen (System-)Proxy laufen
_OEFFNER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _anfrage(url: str, daten=None, zeit: float = ZEIT_SUCHE_S):
    """JSON-Anfrage an LM Studio. Ein Abbruch mitten in der Antwort (LM Studio beendet, Modell entladen) kommt als
    http.client.HTTPException – er wird wie jeder Verbindungsfehler zu URLError, damit die Aufrufer ihn wie
    „nicht erreichbar“ behandeln (die Analyse fällt auf die Regeln zurück, statt abzubrechen)."""
    kopf = {"Accept": "application/json"}
    roh = None
    if daten is not None:
        roh = json.dumps(daten).encode("utf-8")
        kopf["Content-Type"] = "application/json"
    anfrage = urllib.request.Request(url, data=roh, headers=kopf, method="POST" if roh is not None else "GET")
    try:
        with _OEFFNER.open(anfrage, timeout=zeit) as antwort:
            return json.loads(antwort.read().decode("utf-8") or "null")
    except http.client.HTTPException as e:
        raise urllib.error.URLError(f"Verbindung abgebrochen ({type(e).__name__})") from e


def _modelle_aus(antwort, nur_geladene: bool = True) -> list:
    """Modelle aus einer Antwort von /api/v1/models, /api/v0/models oder /v1/models (verschiedene Formen)."""
    if isinstance(antwort, dict):
        eintraege = antwort.get("data") or antwort.get("models") or []
    else:
        eintraege = antwort if isinstance(antwort, list) else []
    modelle = []
    for e in eintraege:
        if not isinstance(e, dict):
            continue
        kennung = next((str(e[s]) for s in ("id", "key", "model_key", "modelKey", "identifier", "path")
                        if e.get(s)), "")
        art = str(e.get("type") or "").lower()
        if not kennung or art in ("embedding", "embeddings"):
            continue
        instanzen = e.get("loaded_instances") or e.get("loadedInstances")
        geladen = (str(e.get("state") or "").lower() == "loaded" or bool(instanzen) or e.get("loaded") is True
                   or e.get("isLoaded") is True)
        if nur_geladene and not geladen:
            continue
        faehig = e.get("capabilities")
        bild = (art == "vlm" or bool(e.get("vision"))
                or (isinstance(faehig, (list, tuple)) and any("vision" in str(f).lower() for f in faehig))
                or (isinstance(faehig, dict) and bool(faehig.get("vision"))))
        if isinstance(instanzen, list) and instanzen and isinstance(instanzen[0], dict):
            kennung = str(instanzen[0].get("id") or instanzen[0].get("identifier") or kennung)
        modelle.append(Modell(kennung, bild))
    return modelle


def geladenes_modell(url: str | None = None) -> Modell | None:
    """Das in LM Studio geladene Sprachmodell (erstes geladenes, kein Einbettungsmodell) oder None.

    Antwortet unter der Adresse gar nichts (Verbindung abgelehnt, Zeitüberschreitung, Abbruch), werden die übrigen
    Pfade nicht mehr gefragt – sie liegen auf demselben Server. Unter Windows dauert jeder abgelehnte
    Verbindungsversuch rund 2 s; ohne laufendes LM Studio wartet das Programm so einmal statt dreimal."""
    basis = basis_url(url)
    # /v1/models: ältere Fassungen, OpenAI-kompatible Liste (ohne Ladezustand – sie nennt geladene Modelle)
    for pfad, nur_geladene in (("/api/v1/models", True), ("/api/v0/models", True), ("/v1/models", False)):
        try:
            modelle = _modelle_aus(_anfrage(basis + pfad), nur_geladene=nur_geladene)
        except urllib.error.HTTPError:
            continue                    # der Server läuft, kennt den Pfad aber nicht (andere Fassung)
        except (urllib.error.URLError, OSError):
            return None                 # kein Server unter der Adresse
        except ValueError:              # auch json.JSONDecodeError: Antwort unlesbar
            continue
        if modelle:
            return modelle[0]
    return None


def _json_aus_text(text: str):
    """JSON aus einer Modellantwort (auch mit Denkteil <think>…</think>, Codezaun oder Vor-/Nachtext)."""
    text = re.sub(r"(?s)<think>.*?</think>", "", text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        anfang, ende = text.find("{"), text.rfind("}")
        if anfang >= 0 and ende > anfang:
            return json.loads(text[anfang:ende + 1])
        raise


class KiAbbruch(Exception):
    """Die Nutzerin hat den Lauf abgebrochen, während das Modell noch antwortete."""


def _mit_abbruch(funktion, abbruch=None):
    """funktion() ausführen; ist abbruch (threading.Event) gesetzt, sofort KiAbbruch (die Anfrage läuft im Hintergrund
    zu Ende und wird verworfen – eine Antwort des Modells lässt sich nicht unterbrechen)."""
    if abbruch is None:
        return funktion()
    ergebnis: dict = {}

    def ausfuehren():
        try:
            ergebnis["wert"] = funktion()
        except BaseException as e:  # noqa: BLE001 - wird im aufrufenden Faden weitergeworfen
            ergebnis["fehler"] = e

    faden = threading.Thread(target=ausfuehren, name="ki-anfrage", daemon=True)
    faden.start()
    while faden.is_alive():
        faden.join(0.2)
        if abbruch.is_set():
            raise KiAbbruch()
    if "fehler" in ergebnis:
        raise ergebnis["fehler"]
    return ergebnis.get("wert")


def teile(dok) -> list:
    """Texte, die das Modell liest: je Seite einer, lange Seiten in Teilen von höchstens MAX_ZEICHEN_TEIL Zeichen an
    Zeilengrenzen, mit 300 Zeichen Überlappung (ein Wert an der Grenze steht in einem Teil ganz)."""
    aus = []
    for seite in getattr(dok, "seiten", None) or []:
        text = getattr(seite, "text", "") or ""
        if not text.strip():
            continue
        anfang = 0
        while anfang < len(text):
            ende = min(len(text), anfang + MAX_ZEICHEN_TEIL)
            if ende < len(text):
                umbruch = text.rfind("\n", anfang + MAX_ZEICHEN_TEIL // 2, ende)
                if umbruch > anfang:
                    ende = umbruch
            aus.append(text[anfang:ende])
            if ende >= len(text):
                break
            anfang = max(anfang + 1, ende - 300)
    return aus


def vorab(dok, melde=None, abbruch=None) -> str | None:
    """Alle Teile des Dokuments vom Modell lesen lassen (mit Fortschritt und Abbruch) – der Detektor findet die
    Antworten danach im Zwischenspeicher. Rückgabe: Text für das Protokoll oder None (KI aus)."""
    if not aktiv():
        return None
    d = dienst()
    if d is None:
        return "KI-Zweitprüfung nicht möglich: unzulässige Adresse (nur der eigene Rechner ist erlaubt)."
    modell = d.modell()
    if modell is None:
        return ("KI-Zweitprüfung nicht möglich: LM Studio ist nicht erreichbar oder es ist kein Modell geladen – "
                "es gelten nur die Regeln.")
    alle = teile(dok)
    for i, teil in enumerate(alle, 1):
        if abbruch is not None and abbruch.is_set():
            raise KiAbbruch()
        if melde:
            melde(f"   KI-Zweitprüfung ({modell.kennung}): Teil {i} von {len(alle)} …")
        try:
            d.personendaten(teil, abbruch=abbruch)
        except KiAbbruch:
            raise
        except Exception as e:  # noqa: BLE001 - die KI ist eine Zugabe: ihr Ausfall darf die Analyse nie verhindern
            d.fehler.append(str(e))
            return f"KI-Zweitprüfung unvollständig ({e}) – für den Rest gelten nur die Regeln."
    return f"KI-Zweitprüfung mit {modell.kennung}: {len(alle)} Textteil(e) gelesen (nur auf diesem Rechner)."


_SYSTEM = ("Du prüfst Texte aus den Unterlagen eines Versicherungsmaklers auf personenbezogene Daten natürlicher "
           "Personen (DSGVO). Du antwortest ausschließlich mit JSON nach dem vorgegebenen Schema.")

_AUFTRAG_FUNDE = (
    "Nenne alle Stellen im Text zwischen <<< und >>>, die eine natürliche Person bezeichnen oder über sie Auskunft "
    "geben: Namen von Personen, Anschriften (Straße mit Hausnummer, Postleitzahl mit Ort), Geburtsdaten, "
    "Telefonnummern, E-Mail-Adressen, IBAN, Kennungen (Versicherungsschein-, Vertrags-, Kunden-, Schaden-, "
    "Ausweisnummern, Kfz-Kennzeichen) und Gesundheitsangaben über eine Person.\n"
    "NICHT nennen: Firmen, Versicherer, Banken, Behörden, Produkt- und Tarifnamen, allgemeine Begriffe, Wetter, "
    "Sachen, Platzhalter in eckigen Klammern wie [PERSON A], und Namen von Geschäftsführern, Vorständen oder "
    "Aufsichtsräten in der Fußzeile eines Firmenbriefs.\n"
    "Gib jeden Wert genau so zurück, wie er im Text steht (Zeichen für Zeichen, ohne Ergänzung). "
    "art: name, anschrift, geburtsdatum, telefon, email, iban, kennung oder gesundheit. "
    "sicher: true nur, wenn es eindeutig ein personenbezogenes Datum ist.\n\n<<<\n{text}\n>>>")

_SCHEMA_FUNDE = {
    "type": "object",
    "properties": {"funde": {"type": "array", "items": {
        "type": "object",
        "properties": {"text": {"type": "string"}, "art": {"type": "string", "enum": list(ARTEN)},
                       "sicher": {"type": "boolean"}},
        "required": ["text", "art", "sicher"]}}},
    "required": ["funde"],
}

_AUFTRAG_URTEIL = (
    "Die Selbstkontrolle hat in anonymisierten Unterlagen Stellen gefunden, die personenbezogen sein KÖNNTEN. "
    "Beurteile jede Stelle im angegebenen Zusammenhang: Ist der markierte Text ein personenbezogenes Datum einer "
    "natürlichen Person (Name, Anschrift, Kennung, Geburtsdatum, Gesundheitsangabe …)?\n"
    "urteil: \"ja\", \"nein\" oder \"unsicher\". \"nein\" nur, wenn sicher KEIN Personenbezug besteht (z. B. Wetter, "
    "Sache, Firma, Ort ohne Person, allgemeiner Begriff, Platzhalter). Im Zweifel \"unsicher\".\n\n{stellen}")

_SCHEMA_URTEIL = {
    "type": "object",
    "properties": {"urteile": {"type": "array", "items": {
        "type": "object",
        "properties": {"nr": {"type": "integer"}, "urteil": {"type": "string", "enum": ["ja", "nein", "unsicher"]}},
        "required": ["nr", "urteil"]}}},
    "required": ["urteile"],
}


class Dienst:
    """Verbindung zu LM Studio mit dem jeweils geladenen Modell (Modellabfrage höchstens alle MODELL_GUELTIG_S)."""

    def __init__(self, url: str | None = None, zeit_anfrage: float = ZEIT_ANFRAGE_S):
        self.url = basis_url(url)
        self.zeit_anfrage = zeit_anfrage
        self._modell = None
        self._modell_zeit = -1e9
        self._sperre = threading.Lock()
        self._zwischenspeicher: dict = {}
        self.anfragen = 0
        self.fehler: list = []

    def modell(self) -> Modell | None:
        with self._sperre:
            jetzt = time.monotonic()
            if jetzt - self._modell_zeit > MODELL_GUELTIG_S:
                self._modell = geladenes_modell(self.url)
                self._modell_zeit = jetzt
            return self._modell

    def _modell_neu_suchen(self) -> None:
        """Nach einem Ausfall die gemerkte Modellabfrage verwerfen: Die nächste Anfrage fragt erst kurz (ZEIT_SUCHE_S),
        ob LM Studio noch läuft und welches Modell geladen ist – statt erneut bis zu ZEIT_ANFRAGE_S auf ein hängendes
        oder beendetes LM Studio zu warten (und ein inzwischen gewechseltes Modell wird sofort genutzt)."""
        with self._sperre:
            self._modell_zeit = -1e9

    def _chat_json(self, auftrag: str, schema: dict, max_tokens: int = 4096, abbruch=None):
        modell = self.modell()
        if modell is None:
            raise KiFehler("LM Studio ist nicht erreichbar oder es ist kein Modell geladen")
        daten = {"model": modell.kennung, "temperature": 0, "max_tokens": max_tokens, "stream": False,
                 "messages": [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": auftrag}],
                 "response_format": {"type": "json_schema",
                                     "json_schema": {"name": "antwort", "strict": True, "schema": schema}}}
        self.anfragen += 1
        url = self.url + "/v1/chat/completions"
        try:
            try:
                antwort = _mit_abbruch(lambda: _anfrage(url, daten, self.zeit_anfrage), abbruch)
            except urllib.error.HTTPError as e:
                if e.code not in (400, 422):
                    self._modell_neu_suchen()
                    raise KiFehler(f"LM Studio antwortet mit Fehler {e.code}") from e
                daten.pop("response_format")            # ältere Fassung ohne JSON-Schema
                antwort = _mit_abbruch(lambda: _anfrage(url, daten, self.zeit_anfrage), abbruch)
        except (urllib.error.URLError, OSError) as e:
            self._modell_neu_suchen()
            raise KiFehler(f"LM Studio nicht erreichbar oder Verbindung abgebrochen ({e})") from e
        except ValueError as e:
            raise KiFehler(f"Antwort von LM Studio unlesbar ({e})") from e
        try:
            inhalt = antwort["choices"][0]["message"]["content"]
            return _json_aus_text(inhalt)
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise KiFehler("Antwort des Modells ist kein gültiges JSON") from e

    def personendaten(self, text: str, abbruch=None) -> list:
        """Personenbezogene Werte in text: [{"text", "art", "sicher"}] – nur Werte, die (bis auf Leerraum) wörtlich
        im Text stehen; erfundene oder umformulierte Werte des Modells entfallen. Zwischengespeichert je Modell und
        Text (eine zweite Analyse derselben Datei fragt nicht erneut)."""
        modell = self.modell()
        schluessel = hashlib.sha256(f"F|{modell.kennung if modell else ''}|{text}".encode("utf-8")).hexdigest()
        if schluessel in self._zwischenspeicher:
            return self._zwischenspeicher[schluessel]
        antwort = self._chat_json(_AUFTRAG_FUNDE.format(text=text), _SCHEMA_FUNDE, abbruch=abbruch)
        flach = " ".join(text.split())
        funde = []
        for f in (((antwort or {}).get("funde") or []) if isinstance(antwort, dict) else []):
            if not isinstance(f, dict):
                continue
            wert, art = " ".join(str(f.get("text") or "").split()), str(f.get("art") or "").lower()
            if art in ARTEN and len(wert) >= 2 and wert in flach:
                funde.append({"text": wert, "art": art, "sicher": f.get("sicher") is True})
        self._zwischenspeicher[schluessel] = funde
        return funde

    def urteile(self, stellen: list, abbruch=None) -> list:
        """Urteil je Stelle [(text, zusammenhang, grund)] -> ["ja" | "nein" | "unsicher", …] (gleiche Länge)."""
        ergebnis = ["unsicher"] * len(stellen)
        for anfang in range(0, len(stellen), MAX_VERDACHT_JE_ANFRAGE):
            teil = stellen[anfang:anfang + MAX_VERDACHT_JE_ANFRAGE]
            liste = "\n".join(f"{i}. Text: «{t}» – Zusammenhang: «{z}» – Grund der Meldung: {g}"
                              for i, (t, z, g) in enumerate(teil, 1))
            antwort = self._chat_json(_AUFTRAG_URTEIL.format(stellen=liste), _SCHEMA_URTEIL, max_tokens=2048,
                                      abbruch=abbruch)
            for u in ((antwort or {}).get("urteile") or []) if isinstance(antwort, dict) else []:
                if not isinstance(u, dict):
                    continue
                try:
                    nr = int(u.get("nr"))
                except (TypeError, ValueError, AttributeError):
                    continue
                if 1 <= nr <= len(teil) and u.get("urteil") in ("ja", "nein", "unsicher"):
                    ergebnis[anfang + nr - 1] = u["urteil"]
        return ergebnis


_DIENST = None
_DIENST_SPERRE = threading.Lock()


def dienst() -> Dienst | None:
    """Gemeinsamer Dienst (None bei unzulässiger Adresse)."""
    global _DIENST
    with _DIENST_SPERRE:
        if _DIENST is None:
            try:
                _DIENST = Dienst()
            except ValueError:
                return None
        return _DIENST


def zuruecksetzen() -> None:
    """Dienst neu aufbauen (andere Adresse, Tests)."""
    global _DIENST
    with _DIENST_SPERRE:
        _DIENST = None


def status() -> str:
    """Kurzer Zustandstext für Oberfläche und Protokoll."""
    if not aktiv():
        return "KI-Zweitprüfung aus"
    d = dienst()
    if d is None:
        return "KI-Zweitprüfung: unzulässige Adresse (nur der eigene Rechner ist erlaubt)"
    m = d.modell()
    if m is None:
        return "KI-Zweitprüfung: LM Studio nicht erreichbar oder kein Modell geladen – es gelten nur die Regeln"
    return f"KI-Zweitprüfung mit {m.kennung} (LM Studio, nur auf diesem Rechner)"


def kategorie_fuer(art: str, wert: str) -> str | None:
    """Kategorie des Programms für eine Art der Antwort (Anschrift: Straße oder PLZ/Ort nach Gestalt)."""
    if art == "anschrift":
        return "plzort" if re.match(r"^\d{4,5}\s+\S", wert) else "strasse"
    return _KATEGORIE.get(art)


def verdacht_filtern(verdacht: list, seitentexte: dict, abbruch=None) -> tuple:
    """Verdachtsstellen der Selbstkontrolle vom Modell beurteilen lassen.

    Entfällt nur eine Stelle mit Urteil „nein“ (sicher kein Personenbezug); ganze Seiten (start = -1) und Stellen
    ohne Text bleiben immer. seitentexte: {seite: Text der Ausgabe} für den Zusammenhang.
    Rückgabe (bleibende Verdachtsstellen, entfallene Verdachtsstellen)."""
    d = dienst() if aktiv() else None
    if d is None or not verdacht:
        return list(verdacht), []
    pruefbar = []
    for i, v in enumerate(verdacht):
        text = str(_feld(v, "text") or "").strip()
        if _feld(v, "start", -1) < 0 or len(text) < 2:
            continue
        seite = str(seitentexte.get(_feld(v, "seite", 0)) or "")
        pos = seite.find(text)
        zusammenhang = seite[max(0, pos - 160):pos + len(text) + 160] if pos >= 0 else text
        pruefbar.append((i, (text, " ".join(zusammenhang.split()), str(_feld(v, "grund") or ""))))
    if not pruefbar:
        return list(verdacht), []
    try:
        urteile = d.urteile([s for _, s in pruefbar], abbruch=abbruch)
    except KiFehler as e:
        d.fehler.append(str(e))
        return list(verdacht), []
    weg = {i for (i, _), u in zip(pruefbar, urteile) if u == "nein"}
    return [v for i, v in enumerate(verdacht) if i not in weg], [v for i, v in enumerate(verdacht) if i in weg]


def _feld(v, name, vorgabe=None):
    return v.get(name, vorgabe) if isinstance(v, dict) else getattr(v, name, vorgabe)
