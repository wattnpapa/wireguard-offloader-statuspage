#!/bin/sh
# Offloader-Statusseite installieren bzw. aktualisieren (Debian/Ubuntu mit systemd, als root ausführen).
# Legt den Systembenutzer offloader-status an, kopiert nach /opt/offloader-status, richtet /etc/offloader-status,
# das Daten- und das Webverzeichnis ein und installiert die systemd-Dienste. Konfiguration und Daten bleiben erhalten.
set -eu
[ "$(id -u)" = 0 ] || { echo "bitte als root ausführen" >&2; exit 1; }
cd "$(dirname "$0")"
python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' || { echo "Python 3.11 oder neuer nötig" >&2; exit 1; }
for p in wg nft vnstat ping; do command -v $p >/dev/null || { echo "$p fehlt (apt install wireguard-tools nftables vnstat iputils-ping)" >&2; exit 1; }; done

id offloader-status >/dev/null 2>&1 || useradd --system --home-dir /var/lib/offloader-status --shell /usr/sbin/nologin offloader-status
install -d -m 755 /opt/offloader-status
cp -r bin lib web /opt/offloader-status/
chmod 755 /opt/offloader-status/bin/*
install -d -m 755 /etc/offloader-status
if [ ! -e /etc/offloader-status/config.toml ]; then
  install -m 644 config.example.toml /etc/offloader-status/config.toml
  echo "Beispielkonfiguration nach /etc/offloader-status/config.toml kopiert – anpassen und install.sh erneut ausführen."
  exit 0
fi
wert() { OFFLOADER_STATUS_LIB=/opt/offloader-status/lib python3 -c "from offloader_status import konfig; print(konfig.$1)"; }
DATEN=$(wert DATEN); WEB=$(wert WEB)
install -d -o offloader-status -g offloader-status -m 755 "$DATEN"
install -d -o offloader-status -g offloader-status -m 755 "$WEB"
# Seite aktualisieren, eine abweichende alte Fassung bleibt als Sicherung liegen
if [ -e "$WEB/index.html" ] && ! cmp -s web/index.html "$WEB/index.html"; then cp "$WEB/index.html" "$WEB/index.html.bak-$(date +%F-%H%M)"; fi
install -m 644 web/index.html "$WEB/index.html"
OFFLOADER_STATUS_LIB=/opt/offloader-status/lib /opt/offloader-status/bin/offloader-status-einrichten
install -m 644 systemd/*.service systemd/*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable offloader-status-live.service offloader-status-probe.service offloader-status-sammeln.timer
cat <<T
Installiert. Noch zu tun bzw. nach Änderungen an der Konfiguration:
  1. offloader-status-einrichten --anwenden   (lädt die Zähler-Tabelle; dauerhaft per include in /etc/nftables.conf)
  2. systemctl restart offloader-status-live offloader-status-probe; systemctl start offloader-status-sammeln.timer
  3. Webserver auf $WEB zeigen lassen (nginx/offloader-status.conf.example)
T
