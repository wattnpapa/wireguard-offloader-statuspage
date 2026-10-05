#!/usr/bin/env python3
# Erfundene Daten, um die Seite ohne Server auszuprobieren:
#   python3 tools/demo.py --server   →  http://localhost:8098/  (live.json bleibt dabei frisch)
# Nutzt config.example.toml; schreibt nur ins Verzeichnis demo/.
import json, math, os, random, shutil, sys, time
WURZEL = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
os.environ.setdefault("OFFLOADER_STATUS_KONFIG", os.path.join(WURZEL, "config.example.toml"))
sys.path.insert(0, os.path.join(WURZEL, "lib"))
from offloader_status import konfig

K = konfig.K
ZIEL = os.path.join(WURZEL, "demo")
os.makedirs(ZIEL, exist_ok=True)
random.seed(3)
now = int(time.time()) // 300 * 300
inet, wg = K["hub"]["internet"], K["hub"]["tunnel"]
S = konfig.STANDORTE


def welle(t, basis, tag=1.0):
    h = time.localtime(t).tm_hour + time.localtime(t).tm_min / 60
    return max(0, basis * (0.35 + 0.65 * tag * (1 + math.sin((h - 9) / 24 * 2 * math.pi)) / 2) * random.uniform(.6, 1.4))


# acct.json: 14 Tage 5-Minuten-Volumen
names = konfig.zaehler()
samples = []
for t in range(now - 14 * 86400, now + 1, 300):
    v = {n: 0 for n in names}
    for i, s in enumerate(S):
        rein, raus = welle(t, 4e7 / (i + 1)), welle(t, 1.2e7 / (i + 1))
        v[f"f_inet_{s}"], v[f"f_{s}_inet"] = int(rein), int(raus)
        for o in S:
            if o != s: v[f"f_{s}_{o}"] = int(welle(t, 2e6))
        v[f"{s}_tx"] = v[f"f_inet_{s}"] + sum(v.get(f"f_{o}_{s}", 0) for o in S)
        v[f"{s}_rx"] = v[f"f_{s}_inet"] + sum(v.get(f"f_{s}_{o}", 0) for o in S)
    rein = sum(v[f"f_inet_{s}"] for s in S); raus = sum(v[f"f_{s}_inet"] for s in S)
    v[f"{inet}_rx4"], v[f"{inet}_tx4"] = int(raus * .8), int(rein * .8)
    v[f"{inet}_rx6"], v[f"{inet}_tx6"] = int(raus * .2), int(rein * .2)
    v[f"{wg}_rx4"], v[f"{wg}_tx4"] = sum(v[f"{s}_rx"] for s in S), sum(v[f"{s}_tx"] for s in S)
    if K["dienst"]:
        anteile = [.6, .1, .05, .05][:len(K["dienst"])]
        for d, a in zip(K["dienst"], anteile):
            v[f"s_{d['port']}_in"], v[f"s_{d['port']}_out"] = int(rein * a), int(raus * a)
        v["s_other_in"], v["s_other_out"] = int(rein * (1 - sum(anteile))), int(raus * (1 - sum(anteile)))
    samples.append([t] + [v[n] for n in names])

# data.json im Format von vnstat --json (nur was die Seite nutzt)
def eintrag(t, rx, tx):
    lt = time.localtime(t)
    return {"date": {"year": lt.tm_year, "month": lt.tm_mon, "day": lt.tm_mday}, "time": {"hour": lt.tm_hour, "minute": lt.tm_min},
            "rx": int(rx), "tx": int(tx)}
ix = names.index(f"{inet}_rx4") + 1
fünf = [eintrag(s[0], s[ix] + s[ix + 2], s[ix + 1] + s[ix + 3]) for s in samples]
def bündeln(sek, fmt):
    m = {}
    for s, e in zip(samples, fünf):
        k = time.strftime(fmt, time.localtime(s[0]))
        if k not in m: m[k] = dict(e, rx=0, tx=0)
        m[k]["rx"] += e["rx"]; m[k]["tx"] += e["tx"]
    return list(m.values())
it = {"name": inet, "created": eintrag(samples[0][0], 0, 0), "updated": eintrag(now, 0, 0),
      "traffic": {"total": {"rx": sum(e["rx"] for e in fünf), "tx": sum(e["tx"] for e in fünf)}, "fiveminute": fünf,
                  "hour": bündeln(3600, "%Y%m%d%H"), "day": bündeln(86400, "%Y%m%d"), "month": bündeln(0, "%Y%m")}}

# probe.json: 30 Tage Erreichbarkeit, 48 h Latenz
ts = list(range(now - 48 * 3600, now + 1, 60))
probe = {"ts": now, "since": now - 30 * 86400, "how": {s: "icmp" for s in S}, "lat": {"ts": ts}, "days": {}, "outages": {},
         "uptime30": {}, "state": {}, "cur": {}, "endp": {}, "ports": None}
for i, s in enumerate(S):
    probe["lat"][s] = {"rtt": [round(18 + 6 * i + random.expovariate(.3), 1) for _ in ts], "loss": [0 if random.random() > .02 else 25 for _ in ts]}
    probe["days"][s] = [[time.strftime("%Y-%m-%d", time.localtime(now - d * 86400)), 100 if random.random() > .2 else round(random.uniform(97, 99.9), 2)] for d in range(29, -1, -1)]
    probe["outages"][s] = [[now - 3 * 86400 - i * 7000, now - 3 * 86400 - i * 7000 + 420]]
    probe["uptime30"][s] = 99.95
    probe["state"][s] = {"up": 1, "since": now - 2 * 86400 - i * 5000, "exact": True}
    probe["cur"][s] = {"rtt": probe["lat"][s]["rtt"][-1], "loss": 0}
    probe["endp"][s] = {"ip": f"198.51.100.{20 + i}", "since": now - 86400 * 9, "provider": "Beispiel-Provider", "changes": []}
if K["portwaechter"]["host"]:
    probe["ports"] = {"ts": now, "host": K["portwaechter"]["host"], "open": K["portwaechter"]["erwartet"],
                      "expected": K["portwaechter"]["erwartet"], "unexpected": [], "missing": []}

# live.json: ein Momentbild
live = {"ts": now, inet: {"rx_rate": 3.1e5, "tx_rate": 1.4e6}, wg: {"rx_rate": 4e5, "tx_rate": 1.5e6},
        "flows": {}, "server": {"cpu": 7.5, "load": [.21, .18, .12], "mem_total": 4 << 30, "mem_used": 1 << 30,
                                "disk_total": 64 << 30, "disk_used": 9 << 30, "uptime": 86400 * 12, "conns": 312}}
for i, s in enumerate(K["standort"]):
    k = s["schluessel"]
    live[k] = {"rx_rate": 2e5 / (i + 1), "tx_rate": 9e5 / (i + 1), "hs": now - 20 - i * 30, "nets": [f'{s["peer"]}/32', *s["netze"]]}
    live["flows"][f"inet_{k}"] = 8e5 / (i + 1); live["flows"][f"{k}_inet"] = 1.5e5 / (i + 1)

for name, inhalt in (("config.json", konfig.seite()), ("acct.json", {"names": names, "samples": samples}),
                     ("data.json", {"interfaces": [it]}), ("probe.json", probe), ("live.json", live)):
    with open(os.path.join(ZIEL, name), "w") as f:
        json.dump(inhalt, f, ensure_ascii=False)
shutil.copy(os.path.join(WURZEL, "web", "index.html"), ZIEL)
print(f"Demo in {ZIEL}")
if "--server" in sys.argv:
    import functools, http.server
    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path.split("?")[0] == "/live.json":   # Momentbild mit aktuellem Zeitstempel, leicht schwankend
                t = int(time.time()); d = dict(live, ts=t, flows={k: v * random.uniform(.3, 1.7) for k, v in live["flows"].items()})
                for s in S: d[s] = dict(live[s], hs=t - 20)
                b = json.dumps(d).encode(); self.send_response(200); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
            super().do_GET()
    print("http://localhost:8098/")
    http.server.ThreadingHTTPServer(("127.0.0.1", 8098), functools.partial(Handler, directory=ZIEL)).serve_forever()
