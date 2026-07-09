import os
import json
import base64
import tempfile
import unittest
from copy import deepcopy

import analytics_worker as aw


class KillPv2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.orig_db_path = aw.DB_PATH
        self.orig_xray_config = aw.XRAY_CONFIG_PATH
        self.orig_combined = deepcopy(aw.PANEL_DATABASE)
        self.orig_snapshot = deepcopy(aw.LAST_STATS_SNAPSHOT)
        self.orig_save_database = aw.save_database
        self.orig_spawn_private = aw.spawn_private_tunnel_for_user
        aw.DB_PATH = os.path.join(self.tmp.name, "panel_db.json")
        aw.XRAY_CONFIG_PATH = os.path.join(self.tmp.name, "config.json")
        aw.PANEL_DATABASE = {}
        aw.LAST_STATS_SNAPSHOT = {}

    def tearDown(self):
        aw.DB_PATH = self.orig_db_path
        aw.XRAY_CONFIG_PATH = self.orig_xray_config
        aw.PANEL_DATABASE = self.orig_combined
        aw.LAST_STATS_SNAPSHOT = self.orig_snapshot
        aw.save_database = self.orig_save_database
        aw.spawn_private_tunnel_for_user = self.orig_spawn_private
        self.tmp.cleanup()

    def test_parse_stats_query_output(self):
        raw = '''
        stat: <name: "user>>>alice>>>traffic>>>uplink" value: 1024 >
        stat: <name: "user>>>alice>>>traffic>>>downlink" value: 2048 >
        '''
        parsed = aw.parse_stats_query_output(raw)
        self.assertEqual(parsed["user>>>alice>>>traffic>>>uplink"], 1024)
        self.assertEqual(parsed["user>>>alice>>>traffic>>>downlink"], 2048)

    def test_refresh_user_usage_from_xray_stats(self):
        aw.PANEL_DATABASE = {
            "alice": aw.normalize_panel_record("alice", {"real_traffic": True, "uuid": "u1"}),
            "bob": aw.normalize_panel_record("bob", {"real_traffic": False, "uuid": "u2"}),
        }
        aw.query_xray_stats_raw = lambda: 'name: "user>>>alice>>>traffic>>>uplink" value: 500\nname: "user>>>alice>>>traffic>>>downlink" value: 1500'
        ok = aw.refresh_user_usage_from_xray_stats(force=True)
        self.assertTrue(ok)
        self.assertEqual(aw.PANEL_DATABASE["alice"]["used_bytes"], 2000)
        self.assertEqual(aw.PANEL_DATABASE["bob"]["used_bytes"], 0)

    def test_bootstrap_private_tunnels_refreshes_host(self):
        aw.PANEL_DATABASE = {
            "alice": aw.normalize_panel_record("alice", {
                "private_tunnel_enabled": True,
                "private_tunnel_host": "old.trycloudflare.com",
                "active": True,
            })
        }
        saved_snapshots = []
        def fake_save_database():
            saved_snapshots.append(deepcopy(aw.PANEL_DATABASE))
        aw.save_database = fake_save_database
        aw.spawn_private_tunnel_for_user = lambda username: "new.trycloudflare.com"
        aw.bootstrap_private_tunnels_on_startup()
        self.assertEqual(aw.PANEL_DATABASE["alice"]["private_tunnel_host"], "new.trycloudflare.com")
        self.assertGreaterEqual(len(saved_snapshots), 2)
        self.assertEqual(saved_snapshots[0]["alice"]["private_tunnel_host"], "")

    def test_build_subscription_uses_custom_host(self):
        rec = aw.normalize_panel_record("alice", {
            "uuid": "1234",
            "clean_ip": "1.1.1.1",
            "custom_host": "sub.example.com",
            "active": True,
            "optimization": True,
        })
        payload = aw.build_user_subscription_payload("alice", rec, include_info=False)
        self.assertIn("sub.example.com", payload)
        self.assertIn("alice_⚡Opt", payload)

    def test_load_database_restores_from_xray_backup(self):
        restored = {
            "alice": aw.normalize_panel_record("alice", {"uuid": "u-restore", "custom_host": "restored.example.com"})
        }
        with open(aw.XRAY_CONFIG_PATH, "w") as f:
            json.dump({"_killpv2_db_backup": base64.b64encode(json.dumps(restored).encode()).decode()}, f)
        loaded = aw.load_database()
        self.assertIn("alice", loaded)
        self.assertEqual(loaded["alice"]["custom_host"], "restored.example.com")
        self.assertTrue(os.path.exists(aw.DB_PATH))

    def test_workflow_contains_safe_concurrency(self):
        workflow_path = os.path.join(os.path.dirname(__file__), "data-sync.yml")
        with open(workflow_path, "r", encoding="utf-8") as f:
            text = f.read()
        self.assertIn("cancel-in-progress: false", text)
        self.assertIn("fetch-depth: 0", text)


if __name__ == "__main__":
    unittest.main()
