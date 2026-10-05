# Tests mit erfundener Konfiguration: python3 -m unittest discover -s tests
import copy, json, os, sys, tempfile, unittest

HIER = os.path.dirname(os.path.abspath(__file__))
WURZEL = os.path.dirname(HIER)
os.environ["OFFLOADER_STATUS_KONFIG"] = os.path.join(WURZEL, "config.example.toml")
sys.path.insert(0, os.path.join(WURZEL, "lib"))

from offloader_status import konfig  # noqa: E402


class Beispiel(unittest.TestCase):
    def test_standorte_und_standardwerte(self):
        self.assertEqual(konfig.STANDORTE, ["nord", "sued"])
        nord = konfig.K["standort"][0]
        self.assertEqual(nord["ping"], "10.0.0.2")                   # Ping-Ziel ist ohne Angabe der Peer
        self.assertFalse(nord["mobil"])
        self.assertEqual(konfig.peers(), {"10.0.0.2/32": "nord", "10.0.0.3/32": "sued"})

    def test_zaehler(self):
        z = konfig.zaehler()
        for n in ("eth0_rx4", "wg0_tx6", "nord_rx", "f_inet_sued", "f_nord_sued", "f_sued_nord", "s_443_in", "s_other_out"):
            self.assertIn(n, z)
        self.assertEqual(len(z), len(set(z)))

    def test_nft_enthaelt_jeden_zaehler_einmal_als_regel(self):
        t = konfig.nft()
        for n in konfig.zaehler():
            self.assertIn(f"counter {n} {{}}", t)
            self.assertEqual(t.count(f'counter name "{n}"'), 1, n)
        self.assertIn("set nord { type ipv4_addr; flags interval; elements = { 10.0.0.2, 192.168.10.0/24 } }", t)
        self.assertIn("proto-dst != { 80, 443 }", t)

    def test_seite_ohne_interna(self):
        s = json.dumps(konfig.seite())
        self.assertNotIn("10.0.0.2\"", s.replace("10.0.0.2/", ""))   # Ping-Ziele und Peers stehen nicht in config.json
        self.assertNotIn("/var/lib", s)


class Pruefung(unittest.TestCase):
    def k(self, **standort):
        k = copy.deepcopy(konfig.STANDARD)
        k["standort"] = [dict({"schluessel": "a", "peer": "10.0.0.2"}, **standort)]
        return k

    def test_ungueltige_schluessel(self):
        for s in ("A", "a_b", "inet", "", "x" * 17):
            with self.assertRaises(konfig.Fehler):
                konfig.pruefen(self.k(schluessel=s))

    def test_ungueltige_adressen(self):
        with self.assertRaises(konfig.Fehler):
            konfig.pruefen(self.k(peer="10.0.0.300"))
        with self.assertRaises(konfig.Fehler):
            konfig.pruefen(self.k(netze=["192.168.1.0/33"]))

    def test_mastblick_standort_muss_existieren(self):
        k = self.k(); k["mastblick"]["standort"] = "b"
        with self.assertRaises(konfig.Fehler):
            konfig.pruefen(k)
        k["mastblick"]["standort"] = "a"
        self.assertTrue(konfig.pruefen(k)["standort"][0]["mobil"])


class Spalten(unittest.TestCase):
    def test_neue_spalten_hinten_alte_bleiben(self):
        p = os.path.join(tempfile.mkdtemp(), "spalten.json")
        self.assertEqual(konfig.spalten(p, ["a", "b"]), ["a", "b"])
        self.assertEqual(konfig.spalten(p, ["c", "a"]), ["a", "b", "c"])   # b fällt nicht weg, c kommt hinten dazu
        with open(p) as f:
            self.assertEqual(json.load(f), ["a", "b", "c"])


if __name__ == "__main__":
    unittest.main()
