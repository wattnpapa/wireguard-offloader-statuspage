# Konfiguration aus /etc/offloader-status/config.toml (anderer Pfad über OFFLOADER_STATUS_KONFIG).
# Fehlende Werte kommen aus STANDARD. Aus derselben Datei entstehen die Zählernamen, die nftables-Regeln
# und die config.json für die Seite – Standorte stehen also nur an einer Stelle.
import copy, ipaddress, os, re, tomllib

PFAD = os.environ.get("OFFLOADER_STATUS_KONFIG", "/etc/offloader-status/config.toml")

PORTS = [21, 22, 23, 25, 53, 80, 81, 110, 139, 143, 443, 445, 465, 587, 993, 995, 1883, 3000, 3389, 5000, 5001, 5432,
         6789, 7070, 7443, 8000, 8080, 8081, 8123, 8443, 8444, 8843, 8880, 8883, 9000, 9443, 10443, 11443]
FARBEN = ["#7ac943", "#e0a030", "#c04bd6", "#2bb5a8", "#d9534f", "#5bc0de", "#f0e040", "#ff8fb0"]

STANDARD = {
    "seite": {
        "titel": "Offloader Traffic",
        "web_verzeichnis": "/var/www/offloader-status",
        "https_adresse": "",            # z. B. "https://status.example.org" – nur für Hinweise (Standort braucht HTTPS)
    },
    "hub": {
        "name": "Offloader",
        "ort": "",                      # Beschriftung auf der Karte, z. B. "Rechenzentrum Frankfurt (Lage ungefähr)"
        "lat": None, "lng": None,
        "internet": "eth0",             # Schnittstelle zum Internet (auch der vnStat-Reiter)
        "internet_weitere": [],         # weitere Wege ins Internet für die Flusszähler, z. B. ["nat64"]
        "tunnel": "wg0",
        "oeffentlich": [],              # öffentliche Adressen, nur zur Anzeige unter "Internet"
        "tunnel_netz": "",              # z. B. "10.0.0.0/24": trennt in der Anzeige Tunnel-Adresse und Netze
    },
    "daten": {
        "verzeichnis": "/var/lib/offloader-status",
        "aufbewahren_tage": 400,        # 5-Minuten-Volumen
        "probe_tage": 90,               # Erreichbarkeit und Latenz
    },
    "nftables": {
        "tabelle": "accounting",
        "datei": "/etc/offloader-status/accounting.nft",
    },
    "portwaechter": {                   # prüft langsam, welche TCP-Ports eines Hosts von hier aus offen sind; leer = aus
        "host": "", "name": "", "erwartet": [], "ports": PORTS, "intervall_s": 900, "hinweis": "",
    },
    "mastblick": {
        "standort": "",                 # Schlüssel des mobilen Standorts, dessen Ort mastblick liefert (API unter api/mast)
    },
    "dienst": [],                       # [[dienst]] port, name, farbe: Internet ↔ Standorte nach Zielport zählen
    "standort": [],                     # [[standort]] siehe config.example.toml
}


class Fehler(ValueError):
    pass


def _mischen(basis, neu):
    for k, v in neu.items():
        if isinstance(v, dict) and isinstance(basis.get(k), dict):
            _mischen(basis[k], v)
        else:
            basis[k] = v
    return basis


def pruefen(k):
    """Standorte und Dienste vervollständigen und prüfen; Fehler mit verständlicher Meldung."""
    gesehen = set()
    for i, s in enumerate(k["standort"]):
        sl = s.get("schluessel", "")
        # Schlüssel landen in Zählernamen der Form f_<von>_<nach>, deshalb ohne Unterstrich
        if not re.fullmatch(r"[a-z][a-z0-9]{0,15}", sl) or sl in ("inet", "hub", "server", "flows", "ts"):
            raise Fehler(f"standort {i + 1}: schluessel {sl!r} ungültig (a–z, 0–9, max. 16 Zeichen, nicht inet/hub)")
        if sl in gesehen:
            raise Fehler(f"standort {sl}: schluessel doppelt")
        gesehen.add(sl)
        try:
            ipaddress.IPv4Address(s.get("peer", ""))
            for n in s.get("netze", []):
                ipaddress.IPv4Network(n, strict=False)
        except ValueError as e:
            raise Fehler(f"standort {sl}: {e}")
        s.setdefault("name", sl)
        s.setdefault("tab", s["name"])
        s.setdefault("netze", [])
        s.setdefault("ping", s["peer"])
        s.setdefault("ping_tcp", 0)
        s.setdefault("farbe", FARBEN[i % len(FARBEN)])
        s.setdefault("notiz", "")
        s["mobil"] = sl == k["mastblick"]["standort"]
        if (s.get("lat") is None) != (s.get("lng") is None):
            raise Fehler(f"standort {sl}: lat und lng nur zusammen angeben")
    mb = k["mastblick"]["standort"]
    if mb and mb not in gesehen:
        raise Fehler(f"mastblick.standort {mb!r} ist kein konfigurierter Standort")
    for d in k["dienst"]:
        if not isinstance(d.get("port"), int) or not 0 < d["port"] < 65536:
            raise Fehler(f"dienst: port {d.get('port')!r} ungültig")
        d.setdefault("name", f"Port {d['port']}")
        d.setdefault("farbe", "#888")
    for n in (k["hub"]["internet"], k["hub"]["tunnel"], *k["hub"]["internet_weitere"]):
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,15}", n):
            raise Fehler(f"Schnittstellenname {n!r} ungültig")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", k["nftables"]["tabelle"]):
        raise Fehler("nftables.tabelle ungültig")
    return k


def laden(pfad=PFAD):
    k = copy.deepcopy(STANDARD)
    if os.path.exists(pfad):
        with open(pfad, "rb") as f:
            _mischen(k, tomllib.load(f))
    return pruefen(k)


K = laden()
DATEN = K["daten"]["verzeichnis"]
WEB = K["seite"]["web_verzeichnis"]
STANDORTE = [s["schluessel"] for s in K["standort"]]


def datei(name):
    """Pfad einer Datei im Datenverzeichnis."""
    return os.path.join(DATEN, name)


def web(name):
    """Pfad einer Datei, die die Seite abruft."""
    return os.path.join(WEB, name)


def peers(k=None):
    """AllowedIP des Peers → Standortschlüssel, so wie `wg show dump` sie ausgibt."""
    return {f'{s["peer"]}/32': s["schluessel"] for s in (k or K)["standort"]}


def spalten(pfad, gewuenscht):
    """Spaltenreihenfolge einer CSV-Datei: bisherige bleiben an ihrem Platz, neue kommen hinten dazu.
    So bleiben alte Zeilen gültig, wenn Standorte oder Dienste hinzukommen oder wegfallen."""
    import json
    alt = []
    if os.path.exists(pfad):
        with open(pfad) as f:
            alt = json.load(f)
    neu = alt + [n for n in gewuenscht if n not in alt]
    if neu != alt:
        with open(pfad + ".tmp", "w") as f:
            json.dump(neu, f)
        os.replace(pfad + ".tmp", pfad)
    return neu


def zaehler(k=None):
    """Alle Zählernamen in fester Reihenfolge: Schnittstellen je IP-Version, je Standort, Flüsse, Dienste."""
    k = k or K
    h, st = k["hub"], [s["schluessel"] for s in k["standort"]]
    n = [x for i in (h["internet"], h["tunnel"]) for x in (f"{i}_rx4", f"{i}_tx4", f"{i}_rx6", f"{i}_tx6")]
    n += [f"{s}_{r}" for s in st for r in ("rx", "tx")]
    n += [f"f_{a}_{b}" for s in st for a, b in (("inet", s), (s, "inet"))]
    n += [f"f_{a}_{b}" for a in st for b in st if a != b]
    if k["dienst"]:
        for r in ("in", "out"):
            n += [f"s_{d['port']}_{r}" for d in k["dienst"]] + [f"s_other_{r}"]
    return n


def _ifs(namen):
    return f'"{namen[0]}"' if len(namen) == 1 else "{ " + ", ".join(f'"{x}"' for x in namen) + " }"


def nft(k=None):
    """nftables-Datei mit allen Zählern. Ersetzt die Tabelle komplett (Zähler beginnen dabei bei 0,
    die Sammler erkennen das)."""
    k = k or K
    h, t, S = k["hub"], k["nftables"]["tabelle"], k["standort"]
    inet, wg, ins = h["internet"], h["tunnel"], _ifs([h["internet"], *h["internet_weitere"]])
    z = ["# Erzeugt von offloader-status-einrichten aus config.toml – nicht von Hand ändern.",
         "# rx = auf der Schnittstelle bzw. vom Standort kommend, tx = hinausgehend",
         f"table inet {t} {{}}", f"delete table inet {t}", f"table inet {t} {{"]
    z += [f"  counter {n} {{}}" for n in zaehler(k)]
    for s in S:
        el = ", ".join([s["peer"], *s["netze"]])
        z.append(f'  set {s["schluessel"]} {{ type ipv4_addr; flags interval; elements = {{ {el} }} }}')
    z += ["  chain pre {", "    type filter hook prerouting priority -300; policy accept;"]
    for i in (inet, wg):
        z += [f'    iifname "{i}" meta nfproto ipv4 counter name "{i}_rx4"', f'    iifname "{i}" meta nfproto ipv6 counter name "{i}_rx6"']
    z += [f'    iifname "{wg}" ip saddr @{s["schluessel"]} counter name "{s["schluessel"]}_rx"' for s in S]
    z += ["  }", "  chain post {", "    type filter hook postrouting priority 300; policy accept;"]
    for i in (inet, wg):
        z += [f'    oifname "{i}" meta nfproto ipv4 counter name "{i}_tx4"', f'    oifname "{i}" meta nfproto ipv6 counter name "{i}_tx6"']
    z += [f'    oifname "{wg}" ip daddr @{s["schluessel"]} counter name "{s["schluessel"]}_tx"' for s in S]
    z += ["  }", "  # f_<von>_<nach>: weitergeleiteter Verkehr; s_<port>: Internet ↔ Standort nach Zielport der Verbindung",
          "  chain flows {", "    type filter hook forward priority 10; policy accept;"]
    for s in S:
        x = s["schluessel"]
        z += [f'    iifname {ins} oifname "{wg}" ip daddr @{x} counter name "f_inet_{x}"',
              f'    iifname "{wg}" oifname {ins} ip saddr @{x} counter name "f_{x}_inet"']
    for a in S:
        for b in S:
            if a is not b:
                z.append(f'    iifname "{wg}" oifname "{wg}" ip saddr @{a["schluessel"]} ip daddr @{b["schluessel"]} '
                         f'counter name "f_{a["schluessel"]}_{b["schluessel"]}"')
    if k["dienst"]:
        alle = "{ " + ", ".join(str(p) for p in sorted(d["port"] for d in k["dienst"])) + " }"
        for r, (i, o) in (("in", (ins, f'"{wg}"')), ("out", (f'"{wg}"', ins))):
            for d in k["dienst"]:
                z.append(f'    iifname {i} oifname {o} meta l4proto {{ tcp, udp }} ct original proto-dst {d["port"]} counter name "s_{d["port"]}_{r}"')
            z.append(f'    iifname {i} oifname {o} meta l4proto {{ tcp, udp }} ct original proto-dst != {alle} counter name "s_other_{r}"')
    z += ["  }", "}", ""]
    return "\n".join(z)


def seite(k=None):
    """Öffentlicher Teil der Konfiguration für die Seite (config.json) – keine Pfade, keine Ping-Ziele."""
    k = k or K
    h, pw = k["hub"], k["portwaechter"]
    return {
        "titel": k["seite"]["titel"], "https_adresse": k["seite"]["https_adresse"],
        "hub": {"name": h["name"], "ort": h["ort"], "lat": h["lat"], "lng": h["lng"], "oeffentlich": h["oeffentlich"],
                "tunnel_netz": h["tunnel_netz"]},
        "internet": h["internet"],
        "standorte": [{x: s.get(x) for x in ("schluessel", "name", "tab", "farbe", "lat", "lng", "notiz", "mobil", "schema")}
                      for s in k["standort"]],
        "dienste": [[str(d["port"]), d["name"], d["farbe"]] for d in k["dienst"]],
        "portwaechter": {"name": pw["name"] or pw["host"], "hinweis": pw["hinweis"]} if pw["host"] else None,
        "mastblick": k["mastblick"]["standort"] or None,
    }
