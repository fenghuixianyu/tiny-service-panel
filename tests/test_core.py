import unittest
from tiny_service_panel.core import (
    parse_systemctl_list,
    parse_ps,
    merge_units_with_processes,
    sort_units,
    is_allowed_unit_name,
    render_systemd_units,
    is_common_noisy_unit,
    apply_user_metadata,
)


class CoreTests(unittest.TestCase):
    def test_parse_systemctl_list_extracts_units(self):
        raw = """UNIT LOAD ACTIVE SUB DESCRIPTION\nssh.service loaded active running OpenBSD Secure Shell server\nexample-tunnel.service loaded active running Example Tunnel\ncockpit.socket loaded active listening Cockpit Socket\n"""
        units = parse_systemctl_list(raw)
        self.assertEqual([u["unit"] for u in units], ["ssh.service", "example-tunnel.service", "cockpit.socket"])
        self.assertEqual(units[1]["active"], "active")
        self.assertEqual(units[2]["description"], "Cockpit Socket")

    def test_parse_ps_groups_rss_by_systemd_unit(self):
        raw = """UNIT PID COMM RSS %CPU\nexample-app.service 100 python 120000 3.5\nexample-app.service 101 python 30000 0.5\nsing-box.service 200 sing-box 74000 1.0\n- 300 kthreadd 0 0.0\n"""
        proc = parse_ps(raw)
        self.assertEqual(proc["example-app.service"]["rss_kb"], 150000)
        self.assertEqual(proc["example-app.service"]["cpu_percent"], 4.0)
        self.assertEqual(proc["example-app.service"]["process_count"], 2)
        self.assertEqual(proc["sing-box.service"]["rss_kb"], 74000)

    def test_merge_and_sort_by_memory_desc(self):
        units = [
            {"unit": "a.service", "load": "loaded", "active": "active", "sub": "running", "description": "A"},
            {"unit": "b.service", "load": "loaded", "active": "inactive", "sub": "dead", "description": "B"},
        ]
        proc = {
            "a.service": {"rss_kb": 1024, "cpu_percent": 1.0, "process_count": 1},
            "b.service": {"rss_kb": 4096, "cpu_percent": 0.0, "process_count": 0},
        }
        merged = merge_units_with_processes(units, proc)
        sorted_units = sort_units(merged, "memory", "desc")
        self.assertEqual([u["unit"] for u in sorted_units], ["b.service", "a.service"])
        self.assertEqual(sorted_units[0]["memory_mb"], 4.0)

    def test_rejects_unsafe_unit_names(self):
        self.assertTrue(is_allowed_unit_name("ssh.service"))
        self.assertTrue(is_allowed_unit_name("cockpit.socket"))
        self.assertFalse(is_allowed_unit_name("../../evil.service"))
        self.assertFalse(is_allowed_unit_name("ssh.service;reboot"))
        self.assertFalse(is_allowed_unit_name(""))

    def test_render_systemd_units_uses_socket_activation(self):
        files = render_systemd_units(port=8765, user="root", app_dir="/opt/tiny-service-panel")
        self.assertIn("tiny-service-panel.socket", files)
        self.assertIn("ListenStream=127.0.0.1:8765", files["tiny-service-panel.socket"])
        self.assertIn("Accept=no", files["tiny-service-panel.socket"])
        self.assertIn("StandardInput=socket", files["tiny-service-panel.service"])
        self.assertIn("EnvironmentFile=-/etc/tiny-service-panel/auth.env", files["tiny-service-panel.service"])
        self.assertIn("ExecStart=/usr/bin/python3 /opt/tiny-service-panel/server.py --systemd-socket", files["tiny-service-panel.service"])

    def test_render_systemd_units_can_bind_public_address(self):
        files = render_systemd_units(port=9876, user="root", app_dir="/opt/tiny-service-panel", bind_host="0.0.0.0")
        self.assertIn("ListenStream=0.0.0.0:9876", files["tiny-service-panel.socket"])

    def test_common_noisy_units_are_detected_but_user_services_are_kept(self):
        self.assertTrue(is_common_noisy_unit("systemd-journald.service", "Journal Service"))
        self.assertTrue(is_common_noisy_unit("user@1000.service", "User Manager for UID 1000"))
        self.assertTrue(is_common_noisy_unit("dbus.socket", "D-Bus socket"))
        self.assertFalse(is_common_noisy_unit("example.service", "Example Service"))
        self.assertFalse(is_common_noisy_unit("example-app.service", "Example App"))

    def test_apply_user_metadata_adds_favorite_note_and_display_name(self):
        units = [{"unit": "example.service", "description": "Example Service"}]
        meta = {"favorites": ["example.service"], "notes": {"example.service": "示例服务"}}
        out = apply_user_metadata(units, meta)
        self.assertTrue(out[0]["favorite"])
        self.assertEqual(out[0]["note"], "示例服务")
        self.assertEqual(out[0]["display_unit"], "example.service（示例服务）")


if __name__ == "__main__":
    unittest.main()
