"""KI-Zweitprüfung über LM Studio (anonymisierer/ki.py, detektoren/ki_zweitpruefung.py) gegen einen nachgebauten
LM-Studio-Server auf 127.0.0.1 (kein echtes Modell nötig).

Geprüft: nur der eigene Rechner, kein Proxy; das GELADENE Modell wird gefunden (neue und alte Schnittstelle,
Einbettungsmodelle nicht); nur wörtliche, sichere Werte werden geschwärzt; die KI nimmt nie etwas weg; ohne LM Studio
arbeitet das Programm wie ohne KI und sagt es; Verdachtsstellen entfallen nur mit Urteil „nein“, ganze Seiten nie.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import fitz
import pytest

from anonymisierer import analyse, ki
from anonymisierer import muster as mu
from anonymisierer.analyse import analysiere_pdf, analysiere_text
from anonymisierer.detektoren import ki_zweitpruefung as kd
from anonymisierer.restrisiko import Verdacht


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.modelle_v1 = {"models": [
            {"type": "embedding", "key": "text-embedding-nomic", "loaded_instances": [{"id": "emb"}]},
            {"type": "llm", "key": "qwen-nicht-geladen", "loaded_instances": []},
            {"type": "llm", "key": "qwen3-27b", "loaded_instances": [{"id": "qwen3-27b"}]},
        ]}
        self.modelle_v0 = None              # None -> 404
        self.modelle_openai = None
        self.funde = []                     # Antwort auf Fund-Anfragen
        self.urteile = []                   # Antwort auf Urteils-Anfragen
        self.schema_ablehnen = False        # alte Fassung: response_format -> 400
        self.inhalt_roh = None              # Antworttext statt JSON (z. B. mit <think>)
        self.anfragen = []

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_address[1]}"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _senden(self, code, daten):
        roh = json.dumps(daten).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(roh)))
        self.end_headers()
        self.wfile.write(roh)

    def do_GET(self):
        s = self.server
        antwort = {"/api/v1/models": s.modelle_v1, "/api/v0/models": s.modelle_v0,
                   "/v1/models": s.modelle_openai}.get(self.path)
        if antwort is None:
            self._senden(404, {"error": "unbekannt"})
        else:
            self._senden(200, antwort)

    def do_POST(self):
        s = self.server
        laenge = int(self.headers.get("Content-Length") or 0)
        daten = json.loads(self.rfile.read(laenge).decode("utf-8"))
        s.anfragen.append(daten)
        if self.path != "/v1/chat/completions":
            self._senden(404, {"error": "unbekannt"})
            return
        if s.schema_ablehnen and "response_format" in daten:
            self._senden(400, {"error": "response_format nicht unterstützt"})
            return
        auftrag = daten["messages"][-1]["content"]
        if "Beurteile jede Stelle" in auftrag:
            inhalt = json.dumps({"urteile": s.urteile})
        else:
            inhalt = s.inhalt_roh if s.inhalt_roh is not None else json.dumps({"funde": s.funde})
        self._senden(200, {"choices": [{"message": {"role": "assistant", "content": inhalt}}]})


@pytest.fixture
def lmstudio(monkeypatch):
    server = _Server()
    faden = threading.Thread(target=server.serve_forever, daemon=True)
    faden.start()
    monkeypatch.setenv("PDFA_KI_URL", server.url)
    monkeypatch.setitem(ki.EINSTELLUNG, "aktiv", True)
    ki.zuruecksetzen()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        ki.zuruecksetzen()


@pytest.fixture
def ki_aus(monkeypatch):
    monkeypatch.setitem(ki.EINSTELLUNG, "aktiv", False)
    monkeypatch.delenv("PDFA_KI", raising=False)
    ki.zuruecksetzen()
    yield
    ki.zuruecksetzen()


# ----------------------------------------------------------------------
# Datenschutz: nur der eigene Rechner, kein Proxy
# ----------------------------------------------------------------------
@pytest.mark.parametrize("url", ["http://127.0.0.1:1234", "http://localhost:1234/", "http://[::1]:1234"])
def test_nur_der_eigene_rechner_ist_erlaubt(url):
    assert ki.basis_url(url) == url.rstrip("/")


@pytest.mark.parametrize("url", ["http://192.168.1.20:1234", "https://api.example.com", "http://lmstudio:1234",
                                 "file:///etc/passwd", "http://127.0.0.1.example.com:1234"])
def test_fremde_adressen_werden_abgelehnt(url):
    with pytest.raises(ValueError):
        ki.basis_url(url)


def test_fremde_adresse_in_der_umgebung_schaltet_die_ki_ab(monkeypatch):
    monkeypatch.setenv("PDFA_KI_URL", "http://10.0.0.5:1234")
    monkeypatch.setitem(ki.EINSTELLUNG, "aktiv", True)
    ki.zuruecksetzen()
    try:
        assert ki.dienst() is None
        assert "unzulässige Adresse" in ki.status()
    finally:
        ki.zuruecksetzen()


def test_ein_systemproxy_wird_nie_benutzt(lmstudio, monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")       # ein Proxy, der nicht antwortet
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    assert ki.geladenes_modell(lmstudio.url) == ki.Modell("qwen3-27b", False)


# ----------------------------------------------------------------------
# Das geladene Modell
# ----------------------------------------------------------------------
def test_geladenes_modell_neue_schnittstelle(lmstudio):
    assert ki.geladenes_modell(lmstudio.url) == ki.Modell("qwen3-27b", False)


def test_geladenes_modell_alte_schnittstelle(lmstudio):
    lmstudio.modelle_v1 = None
    lmstudio.modelle_v0 = {"data": [
        {"id": "nomic-embed", "type": "embeddings", "state": "loaded"},
        {"id": "gemma-3-12b", "type": "vlm", "state": "not-loaded"},
        {"id": "qwen2.5-vl-7b", "type": "vlm", "state": "loaded"},
    ]}
    assert ki.geladenes_modell(lmstudio.url) == ki.Modell("qwen2.5-vl-7b", True)


def test_geladenes_modell_openai_liste_als_letzter_rueckfall(lmstudio):
    lmstudio.modelle_v1 = None
    lmstudio.modelle_openai = {"data": [{"id": "mistral-small", "object": "model"}]}
    assert ki.geladenes_modell(lmstudio.url).kennung == "mistral-small"


def test_kein_modell_geladen(lmstudio):
    lmstudio.modelle_v1 = {"models": [{"type": "llm", "key": "qwen3-27b", "loaded_instances": []}]}
    assert ki.geladenes_modell(lmstudio.url) is None
    assert "kein Modell geladen" in ki.status()


def test_lm_studio_laeuft_nicht(monkeypatch):
    monkeypatch.setenv("PDFA_KI_URL", "http://127.0.0.1:9")          # Port 9: niemand hört zu
    monkeypatch.setitem(ki.EINSTELLUNG, "aktiv", True)
    ki.zuruecksetzen()
    try:
        assert ki.geladenes_modell() is None
        assert "nicht erreichbar" in ki.status()
    finally:
        ki.zuruecksetzen()


def test_status_nennt_das_modell(lmstudio):
    assert ki.status() == "KI-Zweitprüfung mit qwen3-27b (LM Studio, nur auf diesem Rechner)"


def test_ki_aus_fragt_nie_an(lmstudio, monkeypatch):
    monkeypatch.setitem(ki.EINSTELLUNG, "aktiv", False)
    analysiere_text("Herr Quirin Sedlbauer, Am Anger 3, 84028 Landshut", set(mu.PROFILE["hoch"]["aktive"]), [], [],
                    profil="hoch")
    assert lmstudio.anfragen == []
    assert ki.status() == "KI-Zweitprüfung aus"


# ----------------------------------------------------------------------
# Antworten des Modells
# ----------------------------------------------------------------------
def test_nur_woertliche_werte_zaehlen(lmstudio):
    lmstudio.funde = [{"text": "Quirin  Sedlbauer", "art": "name", "sicher": True},       # Leerraum egal
                      {"text": "Quirin Sedelbauer", "art": "name", "sicher": True},       # erfunden/umformuliert
                      {"text": "Landshut", "art": "unbekannt", "sicher": True},          # unbekannte Art
                      {"text": "Am Anger 3", "art": "anschrift", "sicher": False}]
    funde = ki.dienst().personendaten("Rückruf an Quirin\nSedlbauer, Am Anger 3, 84028 Landshut")
    assert funde == [{"text": "Quirin Sedlbauer", "art": "name", "sicher": True},
                     {"text": "Am Anger 3", "art": "anschrift", "sicher": False}]


def test_antwort_wird_zwischengespeichert(lmstudio):
    lmstudio.funde = [{"text": "Quirin Sedlbauer", "art": "name", "sicher": True}]
    d = ki.dienst()
    d.personendaten("Quirin Sedlbauer ruft an")
    d.personendaten("Quirin Sedlbauer ruft an")
    assert len(lmstudio.anfragen) == 1
    assert lmstudio.anfragen[0]["model"] == "qwen3-27b" and lmstudio.anfragen[0]["temperature"] == 0


def test_alte_fassung_ohne_json_schema(lmstudio):
    lmstudio.schema_ablehnen = True
    lmstudio.funde = [{"text": "Quirin Sedlbauer", "art": "name", "sicher": True}]
    assert ki.dienst().personendaten("Quirin Sedlbauer ruft an")[0]["text"] == "Quirin Sedlbauer"
    assert "response_format" in lmstudio.anfragen[0] and "response_format" not in lmstudio.anfragen[1]


def test_denkteil_und_codezaun_werden_ignoriert(lmstudio):
    lmstudio.inhalt_roh = ('<think>Ich prüfe den Text …</think>\n```json\n'
                           '{"funde": [{"text": "Quirin Sedlbauer", "art": "name", "sicher": true}]}\n```')
    assert ki.dienst().personendaten("Quirin Sedlbauer ruft an")[0]["text"] == "Quirin Sedlbauer"


def test_unbrauchbare_antwort_ist_ein_ki_fehler(lmstudio):
    lmstudio.inhalt_roh = "Ich kann dabei nicht helfen."
    with pytest.raises(ki.KiFehler):
        ki.dienst().personendaten("Quirin Sedlbauer ruft an")


def test_auftrag_schliesst_organe_in_fusszeilen_aus():
    """Entscheidung des Maklers vom 27.11.: Namen von Vorstand, Aufsichtsrat und Geschäftsführung in Fußzeilen
    bleiben lesbar – das Modell soll sie nicht nennen."""
    assert "Geschäftsführern, Vorständen oder Aufsichtsräten in der Fußzeile" in ki._AUFTRAG_FUNDE


# ----------------------------------------------------------------------
# Detektor
# ----------------------------------------------------------------------
@pytest.mark.parametrize("art, wert, erwartet", [
    ("name", "Herr Dr. Quirin Sedlbauer", [("namen", "Quirin Sedlbauer", "Quirin Sedlbauer")]),
    ("name", "Frau von Stetten", [("namen", "von Stetten", "von Stetten")]),
    ("name", "Sedlbauer", [("namen", "Sedlbauer", "Sedlbauer")]),
    ("name", "Herr Wald", [("namen", "Wald", "Herr Wald"), ("namen", "Wald", "Herrn Wald")]),  # nur mit Anrede
    ("name", "Frau Regen", [("namen", "Regen", "Frau Regen")]),
    ("name", "Wald", []),
    ("name", "der Versicherungsnehmer", []),                 # Artikel/Rolle: kein Name
    ("name", "Versicherungsnehmer", []),
    ("name", "Allianz", []),                                 # Organisation der Erlaubnisliste
    ("name", "Sedlbauer 3", []),                             # Ziffer: kein Name
    ("anschrift", "Am Anger 3, 84028 Landshut", [("strasse", "Am Anger 3", "Am Anger 3"),
                                                 ("plzort", "84028 Landshut", "84028 Landshut")]),
    ("anschrift", "Landshut", []),                           # Ort ohne PLZ: zu unscharf
    ("kennung", "LA-QS 123", [("kfz", "LA-QS 123", "LA-QS 123")]),
    ("kennung", "KV-2024-88812", [("vertrag", "KV-2024-88812", "KV-2024-88812")]),
    ("geburtsdatum", "12.03.1971", [("geburt", "12.03.1971", "12.03.1971")]),
    ("gesundheit", "Lumboischialgie", [("diagnose", "Lumboischialgie", "Lumboischialgie")]),
])
def test_zerlegen(art, wert, erwartet):
    assert kd.zerlegen(art, wert) == erwartet


def test_alltagswort_als_name_nur_mit_anrede(lmstudio):
    """Die KI-Regel selbst setzt ein Alltagswort als Namen nur dort, wo die Anrede davor steht („im Wald“ nicht;
    die Weitergabe der Regeln entscheidet darüber unabhängig von der KI)."""
    from anonymisierer.detektoren import Kontext
    from anonymisierer.seitenmodell import dokument_aus_text
    lmstudio.funde = [{"text": "Herr Wald", "art": "name", "sicher": True}]
    text = "Herr Wald meldet den Sturmschaden. Ein Baum im Wald fiel auf das Carport von Herrn Wald."
    dok = dokument_aus_text(text)
    treffer = kd.ki_zweitpruefung(dok, Kontext(set(mu.PROFILE["hoch"]["aktive"]), "hoch"))
    assert sorted(t.start for t in treffer) == [text.index("Wald"), text.rindex("Wald")]
    assert all(dok.text[t.start:t.ende] == "Wald" and t.kategorie == "namen" for t in treffer)


def test_ki_fund_wird_geschwaerzt(lmstudio):
    lmstudio.funde = [{"text": "Quirin Sedlbauer", "art": "name", "sicher": True},
                      {"text": "Bergl", "art": "name", "sicher": False}]          # unsicher: nicht geschwärzt
    funde = analysiere_text("Rückfrage von Quirin Sedlbauer zum Schaden am Bergl.",
                            set(mu.PROFILE["hoch"]["aktive"]), [], [], profil="hoch")
    namen = {f["text"]: f for f in funde if f["kategorie"] == "namen"}
    assert "Quirin Sedlbauer" in namen and kd.QUELLE in namen["Quirin Sedlbauer"]["quellen"]
    assert all(st["an"] for st in namen["Quirin Sedlbauer"]["stellen"])
    assert not any("Bergl" in t for t in namen)


def test_ki_fund_in_nicht_angehakter_kategorie_bleibt_stehen(lmstudio):
    lmstudio.funde = [{"text": "Quirin Sedlbauer", "art": "name", "sicher": True}]
    funde = analysiere_text("Rückfrage von Quirin Sedlbauer zum Schaden.", {"telefon", "email"}, [], [],
                            profil="hoch")
    assert not [f for f in funde if f["kategorie"] == "namen"]


def test_ki_nimmt_nie_etwas_weg(lmstudio):
    text = "Versicherungsnehmer: Thomas Meier, IBAN DE89 3704 0044 0532 0130 00"
    aktive = set(mu.PROFILE["hoch"]["aktive"])
    lmstudio.funde = []                                     # das Modell findet nichts
    mit = {(f["kategorie"], f["text"]) for f in analysiere_text(text, aktive, [], [], profil="hoch")}
    ki.EINSTELLUNG["aktiv"] = False
    ohne = {(f["kategorie"], f["text"]) for f in analysiere_text(text, aktive, [], [], profil="hoch")}
    assert ohne and ohne <= mit


def test_ki_ausfall_waehrend_der_analyse(lmstudio):
    lmstudio.inhalt_roh = "kein JSON"
    funde = analysiere_text("Versicherungsnehmer: Thomas Meier", set(mu.PROFILE["hoch"]["aktive"]), [], [],
                            profil="hoch")
    assert any(f["text"] == "Thomas Meier" for f in funde)
    assert ki.dienst().fehler


def _pdf(tmp_path, text):
    pfad = tmp_path / "brief.pdf"
    doc = fitz.open()
    seite = doc.new_page()
    seite.insert_text((72, 100), text, fontsize=11)
    doc.save(pfad)
    doc.close()
    return pfad


def test_pdf_analyse_meldet_modell_und_liest_vorab(lmstudio, tmp_path):
    lmstudio.funde = [{"text": "Quirin Sedlbauer", "art": "name", "sicher": True}]
    fortschritt = []
    ergebnis = analysiere_pdf(_pdf(tmp_path, "Rückfrage von Quirin Sedlbauer zum Schaden."),
                              set(mu.PROFILE["hoch"]["aktive"]), [], [], melde=fortschritt.append, profil="hoch")
    assert ergebnis["fehler"] is None
    meldung = next(m for m in ergebnis["meldungen"] if m["code"] == "KI_ZWEITPRUEFUNG")
    assert meldung["art"] == "hinweis" and "qwen3-27b" in meldung["text"]
    assert any("KI-Zweitprüfung (qwen3-27b): Teil 1 von 1" in t for t in fortschritt)
    assert len(lmstudio.anfragen) == 1                      # Detektor nutzt den Zwischenspeicher
    assert any(f["text"] == "Quirin Sedlbauer" for f in ergebnis["funde"])
    assert not analyse.ist_leckrelevant(meldung)


def test_pdf_analyse_ohne_lm_studio(monkeypatch, tmp_path):
    monkeypatch.setenv("PDFA_KI_URL", "http://127.0.0.1:9")
    monkeypatch.setitem(ki.EINSTELLUNG, "aktiv", True)
    ki.zuruecksetzen()
    try:
        ergebnis = analysiere_pdf(_pdf(tmp_path, "Versicherungsnehmer: Thomas Meier"),
                                  set(mu.PROFILE["hoch"]["aktive"]), [], [], profil="hoch")
    finally:
        ki.zuruecksetzen()
    assert ergebnis["fehler"] is None
    assert any(f["text"] == "Thomas Meier" for f in ergebnis["funde"])
    text = next(m["text"] for m in ergebnis["meldungen"] if m["code"] == "KI_ZWEITPRUEFUNG")
    assert "nicht möglich" in text and "nur die Regeln" in text


def test_abbruch_waehrend_das_modell_antwortet():
    abbruch = threading.Event()
    gestartet = threading.Event()

    def langsam():
        gestartet.set()
        threading.Event().wait(5)
        return "zu spät"

    threading.Timer(0.3, abbruch.set).start()
    with pytest.raises(ki.KiAbbruch):
        ki._mit_abbruch(langsam, abbruch)
    assert gestartet.is_set()


def test_teile_langer_seiten_ueberlappen():
    class S:
        def __init__(self, text):
            self.text = text

    class D:
        seiten = [S(""), S("\n".join(f"Zeile {i:05d} mit etwas Text" for i in range(800)))]

    teile = ki.teile(D())
    assert len(teile) >= 3 and all(len(t) <= ki.MAX_ZEICHEN_TEIL for t in teile)
    for a, b in zip(teile, teile[1:]):
        assert a[-100:] in b                                # Überlappung: kein Wert geht an der Grenze verloren


# ----------------------------------------------------------------------
# Verdachtsstellen der Selbstkontrolle
# ----------------------------------------------------------------------
def _v(seite, start, text, grund="möglicher Name"):
    return Verdacht(seite, start, start + max(len(text), 1) if start >= 0 else -1, text, grund, [])


def test_verdacht_entfaellt_nur_mit_urteil_nein(lmstudio):
    lmstudio.urteile = [{"nr": 1, "urteil": "nein"}, {"nr": 2, "urteil": "unsicher"}, {"nr": 3, "urteil": "ja"}]
    verdacht = [_v(0, 10, "Regen"), _v(0, 40, "Wald"), _v(0, 60, "Kranich"), _v(1, -1, "", "Seite kaum lesbar")]
    texte = {0: "Bei starkem Regen lief Wasser ein. Herr Wald meldet den Schaden. Kranich", 1: ""}
    bleibt, weg = ki.verdacht_filtern(verdacht, texte)
    assert [v.text for v in weg] == ["Regen"]
    assert [v.text for v in bleibt] == ["Wald", "Kranich", ""]       # ganze Seite bleibt immer
    auftrag = lmstudio.anfragen[0]["messages"][-1]["content"]
    assert "Bei starkem Regen lief Wasser ein" in auftrag            # mit Zusammenhang gefragt


def test_verdacht_bleibt_bei_ki_fehler(lmstudio):
    lmstudio.inhalt_roh = "kaputt"
    lmstudio.urteile = None
    verdacht = [_v(0, 10, "Regen")]
    bleibt, weg = ki.verdacht_filtern(verdacht, {0: "Bei starkem Regen"})
    assert bleibt == verdacht and weg == []


def test_verdacht_ohne_ki_unveraendert(ki_aus):
    verdacht = [_v(0, 10, "Regen")]
    assert ki.verdacht_filtern(verdacht, {0: "Bei starkem Regen"}) == (verdacht, [])


def test_schwaerzung_meldet_entfallene_verdachtsstellen(lmstudio):
    from anonymisierer import schwaerzung

    class Lauf:
        def __init__(self):
            self.modell = None
            self.analyse_modell = None
            self.abbruch = None
            self.meldungen = []

        def melden(self, art, code, text, seite=None):
            self.meldungen.append({"art": art, "code": code, "text": text})

        def abbruch_pruefen(self):
            pass

    lmstudio.urteile = [{"nr": 1, "urteil": "nein"}]
    lauf = Lauf()
    bleibt = schwaerzung._ki_verdacht_filtern(lauf, [_v(0, 10, "Regen"), _v(2, -1, "", "Seite ungelesen")])
    assert [v.text for v in bleibt] == [""]
    assert lauf.meldungen[0]["code"] == "KI_ZWEITPRUEFUNG" and "„Regen“" in lauf.meldungen[0]["text"]
