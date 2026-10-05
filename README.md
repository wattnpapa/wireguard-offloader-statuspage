# wireguard-offloader-statuspage

Statusseite für einen **WireGuard-Offloader**: einen Server (z. B. ein kleiner VPS), an dem die Tunnel mehrerer
Standorte enden und über den Dienste aus dem Internet zu den Standorten weitergeleitet werden.

*English summary below.*

## Was die Seite zeigt

- **Verkehr jetzt** (alle 5 s), als Schema oder auf der Karte (OpenStreetMap):
  - Internet ↔ Offloader ↔ Standorte als animierte Spuren, die Linienstärke zeigt die Rate
  - je Standort: verbunden ja/nein, Netze, öffentliche Adresse samt Anbieter, Latenz, Volumen heute
- **Internet-Reiter**:
  - Durchsatz und Volumen der Internet-Schnittstelle (vnStat), getrennt nach IPv4/IPv6
  - Verkehr nach Dienst (Zielport) und Hochrechnung für den Monat
- **Standort-Reiter**:
  - Durchsatz und Volumen des Standorts
  - Herkunft und Ziel (Internet oder anderer Standort)
  - Verfügbarkeit pro Tag, letzte Ausfälle, Latenz und Paketverlust
- **Portwächter** (optional): prüft langsam, welche TCP-Ports eines Hosts von außen offen sind, und warnt bei unerwarteten.
- **Mobiler Standort** (optional, mit [mastblick](https://github.com/wattnpapa/mastblick)):
  - Ein Router im Auto oder Wohnmobil (z. B. FRITZ!Box LTE) erscheint mit dem Ort, den mastblick aus der Mobilfunkzelle bestimmt.
  - Dazu kommen Track, Masten, Netzabdeckung und Auswertungen.
  - mastblick ist eine eigenständige Abhängigkeit mit eigenem Repo. Die Seite spricht nur dessen API unter `api/mast` an.
  - Über den Push-Kanal von mastblick kommen auch die Live-Daten dieser Seite ohne Abfragen an.

Alle Standorte stehen an **einer** Stelle, in `/etc/offloader-status/config.toml`. Daraus entstehen:
- die nftables-Zähler,
- die Messdienste,
- die `config.json`, aus der die Seite Reiter, Farben, Karte und Schema aufbaut.

## Bausteine

| Teil | Aufgabe |
|---|---|
| `offloader-status-einrichten` | erzeugt aus der Konfiguration die nftables-Datei (Zähler je Schnittstelle, Standort, Richtung und Dienst) und `config.json` |
| `offloader-status-live` | Dienst: alle 5 s `live.json` (Raten, Handshakes, Flüsse, Serverlast) |
| `offloader-status-probe` | Dienst: jede Minute Erreichbarkeit und Latenz (`probe.json`), öffentliche Adressen, Portwächter |
| `offloader-status-sammeln` | Timer, alle 5 min: `vnstat --json` → `data.json`, Zählerstände → `acct.json` |
| `web/index.html` | die Seite (Chart.js, Leaflet) |

Die Dienste laufen als eigener Benutzer `offloader-status`. Sie haben nur die Rechte `CAP_NET_ADMIN` (für `wg show` und `nft list counters`) und `CAP_NET_RAW` (für ping).

## Installation

Voraussetzungen:
- Debian/Ubuntu mit systemd und Python ≥ 3.11
- `wireguard-tools`, `nftables`, `vnstat`, `iputils-ping`
- ein Webserver, z. B. nginx

```sh
git clone https://github.com/wattnpapa/wireguard-offloader-statuspage.git /opt/offloader-status-src
cd /opt/offloader-status-src
./install.sh                       # legt beim ersten Mal /etc/offloader-status/config.toml an
nano /etc/offloader-status/config.toml
./install.sh
/opt/offloader-status/bin/offloader-status-einrichten --anwenden
systemctl restart offloader-status-live offloader-status-probe
systemctl start offloader-status-sammeln.timer
```

- Damit die Zähler einen Neustart überstehen, die erzeugte Datei in `/etc/nftables.conf` einbinden: `include "/etc/offloader-status/accounting.nft"`.
- Der Webserver liefert das Webverzeichnis aus, siehe `nginx/offloader-status.conf.example`.
- **Die Seite zeigt Netze, Adressen und Verkehr.** Biete sie nur im Tunnel bzw. LAN an oder hinter einer Anmeldung.

Aktualisieren:

```sh
cd /opt/offloader-status-src && git pull && ./install.sh && systemctl restart offloader-status-live offloader-status-probe
```

### Konfiguration

Siehe `config.example.toml`. Das Wichtigste:

- `[[standort]]` je Standort:
  - `schluessel`: a–z und 0–9; steht in Zähler- und Dateinamen, also später nicht mehr ändern
  - `peer`: die Tunnel-Adresse, also die AllowedIP /32 des Peers
  - `netze`: die Netze hinter dem Standort
  - `lat`/`lng` für die Karte, dazu `farbe` und `notiz`
  - `ping`: anderes Ping-Ziel als der Peer
  - `ping_tcp`: misst die Latenz per TCP-Verbindungsaufbau, wenn die Gegenstelle Ping verwirft
  - `schema = [x, y, r]`: Platz im Schema festlegen; sonst stehen die Standorte im Bogen
- `[[dienst]]`: Ports, deren Verkehr Internet ↔ Standorte getrennt gezählt wird.
- `[hub] internet_weitere`: weitere Wege ins Internet, z. B. eine NAT64-Schnittstelle.
- `[mastblick] standort`: Schlüssel des mobilen Standorts.
  - Seine Position kommt dann von mastblick (`/api/mast/status`).
  - Der Webserver muss dafür `/api/mast` an mastblick weiterreichen.
  - In der mastblick-Konfiguration lassen sich `live.json`, `probe.json` und `acct.json` als Push-Dateien eintragen:
    ```toml
    [api]
    push_dateien = { live = "/var/www/offloader-status/live.json", probe = "/var/www/offloader-status/probe.json" }
    push_signale = { acct = ["/var/www/offloader-status/acct.json"] }
    ```

**Standorte hinzufügen oder entfernen:**
- Bisherige Messreihen bleiben gültig.
- Neue Spalten werden hinten angehängt (`samples-spalten.json`, `probe-spalten.json`).
- `offloader-status-einrichten --anwenden` ersetzt die Zähler-Tabelle. Die Zähler beginnen danach bei 0, das erkennen die Sammler.

## Demo ohne Server

```sh
python3 tools/demo.py --server     # erfundene Daten nach demo/, dann http://localhost:8098/
```

## Tests

```sh
python3 -m unittest discover -s tests
```

## Lizenz

EUPL-1.2, siehe `LICENSE`.

---

## English summary

A status page for a **WireGuard offloader**: a server where the tunnels of several sites end and which forwards
internet services to them.

What it shows:
- live traffic between the internet, the hub and the sites, as a diagram or on a map
- per-site volume and source/destination
- availability, latency and packet loss
- traffic per service port
- vnStat history
- optional port watcher
- optional mobile site located via its mobile cell by [mastblick](https://github.com/wattnpapa/mastblick), a separate dependency

All sites are defined once in `config.toml`. `offloader-status-einrichten` generates the nftables counters and the page configuration from it. The services run as an unprivileged user, holding only CAP_NET_ADMIN and CAP_NET_RAW.

The UI is in German. Licence: EUPL-1.2.
