# Gegenprüfung Sparte Person, Teil 4: Buchungscodes nur aus Buchstaben hinter bekanntem Etikett. Erfundene Codes.
def F(name, zeilen, geheim, scans=(), **kw):
    d = dict(name=name, zeilen=zeilen, geheim=geheim, scans=scans)
    d.update(kw)
    return d


FAELLE = [
    F("b7_buchstaben_bekannt", [
        "Buchungsbestätigung Pauschalreise",
        "Buchungscode: KXQRZM",
    ], ["KXQRZM"]),
    F("b7_pnr_buchstaben", [
        "Flugbuchung",
        "PNR: KXQRZN",
    ], ["KXQRZN"]),
]
