"""Regression checks for the generated hook relay and Codex config merge.

Everything runs in temporary homes and sockets; no real agent settings are touched.
"""

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOOK_SOURCE = (ROOT / "NotchBuddy/Sources/App/HookServer.swift").read_text()


def embedded(name):
    marker = f'private let {name} = """\n'
    value = HOOK_SOURCE.split(marker, 1)[1].split('\n"""', 1)[0]
    # Swift escapes backslashes in these multiline Python and shell literals.
    return value.replace('\\\\', '\\') + '\n'


class RelayChecks(unittest.TestCase):
    def setUp(self):
        # A Unix socket has a short path limit on macOS.
        self.temp = tempfile.TemporaryDirectory(prefix="coucou-", dir="/tmp")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.bin = self.home / "coucou"
        self.bin.mkdir()
        (self.bin / "nb-hook").write_text(embedded("nbHookShellWrapper"))
        (self.bin / "nb-hook.py").write_text(embedded("nbHookPythonGitHub"))
        (self.bin / "nb-hook").chmod(0o755)
        self.socket_path = self.home / "Library/Application Support/NotchBuddy/nb.sock"
        self.socket_path.parent.mkdir(parents=True)

    def run_hook(self, payload, *args):
        env = {**os.environ, "HOME": str(self.home)}
        return subprocess.run(
            ["/bin/sh", str(self.bin / "nb-hook"), *args],
            input=json.dumps(payload), text=True, capture_output=True,
            env=env, timeout=5, check=False,
        )

    def one_request(self, reply):
        result = {}
        ready = threading.Event()

        def serve():
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
                listener.bind(str(self.socket_path))
                listener.listen(1)
                ready.set()
                client, _ = listener.accept()
                with client:
                    data = b""
                    while not data.endswith(b"\n"):
                        data += client.recv(4096)
                    result["payload"] = json.loads(data)
                    client.sendall(json.dumps({"permissionDecision": reply}).encode() + b"\n")

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        self.assertTrue(ready.wait(2))
        return result, thread

    def test_unavailable_app_exits_zero_without_approval(self):
        completed = self.run_hook({"hook_event_name": "PermissionRequest"}, "codex")
        self.assertEqual(0, completed.returncode)
        self.assertEqual("", completed.stdout)

    def test_explicit_codex_allow_and_deny_and_provider_isolation(self):
        for decision in ("allow", "deny"):
            if self.socket_path.exists():
                self.socket_path.unlink()
            received, thread = self.one_request(decision)
            completed = self.run_hook({
                "hook_event_name": "PermissionRequest",
                "coucou_agent": "claude",  # input must not override the installed provider
                "tool_name": "Bash",
            }, "codex")
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual("codex", received["payload"]["coucou_agent"])
            self.assertEqual(0, completed.returncode)
            output = json.loads(completed.stdout)["hookSpecificOutput"]["decision"]
            self.assertEqual(decision, output["behavior"])
            self.assertNotIn("updatedPermissions", output)

    def test_app_store_relay_uses_container_socket(self):
        (self.bin / "nb-hook.py").write_text(embedded("nbHookPythonAppStore"))
        self.socket_path = self.home / "Library/Containers/fr.louisraille.Coucou/Data/nb.sock"
        self.socket_path.parent.mkdir(parents=True)
        received, thread = self.one_request("allow")
        completed = self.run_hook({"hook_event_name": "PermissionRequest"}, "codex")
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual("codex", received["payload"]["coucou_agent"])
        self.assertEqual("allow", json.loads(completed.stdout)["hookSpecificOutput"]["decision"]["behavior"])
        self.assertIn('"$@"', embedded("nbHookShellWrapper"))


class ConfigChecks(unittest.TestCase):
    @unittest.skipUnless(shutil.which("swiftc"), "Swift compiler required")
    def test_merge_remove_and_invalid_config(self):
        with tempfile.TemporaryDirectory() as temp:
            harness = Path(temp) / "main.swift"
            harness.write_text('''
import Foundation

func parse(_ data: Data) -> [String: Any] {
    try! JSONSerialization.jsonObject(with: data) as! [String: Any]
}
let own = "\\\"/tmp/Coucou/nb-hook\\\" codex"
let foreign = "\\\"/tmp/coucou-helper/nb-hook\\\" codex"
let original: [String: Any] = [
    "other": ["keep": true],
    "hooks": ["SessionStart": [[
        "matcher": "fixture",
        "hooks": [["type": "command", "command": foreign],
                  ["type": "command", "command": own]],
    ]]],
]
let input = try JSONSerialization.data(withJSONObject: original)
let merged = try CodexHooksConfig.merged(existing: input, command: own)
let root = parse(merged)
precondition((root["other"] as! [String: Bool])["keep"] == true)
let hooks = root["hooks"] as! [String: Any]
let starts = hooks["SessionStart"] as! [[String: Any]]
precondition(starts.count == 2)
precondition((starts[0]["hooks"] as! [[String: Any]]).count == 1)
precondition(((starts[0]["hooks"] as! [[String: Any]])[0]["command"] as! String) == foreign)
precondition(CodexHooksConfig.containsManagedHook(merged, command: own))
let removed = try CodexHooksConfig.removing(existing: merged, command: own)
let left = (parse(removed)["hooks"] as! [String: Any])["SessionStart"] as! [[String: Any]]
precondition(left.count == 1)
precondition(((left[0]["hooks"] as! [[String: Any]])[0]["command"] as! String) == foreign)
precondition(!CodexHooksConfig.containsManagedHook(removed, command: own))
let configDir = URL(fileURLWithPath: CommandLine.arguments[1])
let configURL = configDir.appendingPathComponent("hooks.json")
try input.write(to: configURL)
try CodexHooksConfig.writeReviewed(merged, original: input, to: configURL)
let written = try Data(contentsOf: configURL)
precondition(written == merged)
let firstBackup = try FileManager.default.contentsOfDirectory(atPath: configDir.path)
    .filter { $0.hasPrefix("hooks.json.bak-") }
precondition(firstBackup.count == 1)
let backupContents = try Data(contentsOf: configDir.appendingPathComponent(firstBackup[0]))
precondition(backupContents == input)
do {
    try CodexHooksConfig.writeReviewed(removed, original: input, to: configURL)
    fatalError("overwrote an edit made after preview")
} catch CodexHooksConfig.ConfigError.changedSincePreview { }
let stillWritten = try Data(contentsOf: configURL)
precondition(stillWritten == merged)
try CodexHooksConfig.removeInstalled(at: configURL, command: own)
let afterRemoval = try Data(contentsOf: configURL)
precondition(!CodexHooksConfig.containsManagedHook(afterRemoval, command: own))
let backups = try FileManager.default.contentsOfDirectory(atPath: configDir.path)
    .filter { $0.hasPrefix("hooks.json.bak-") }
precondition(backups.count == 2)
for malformed in [Data("{".utf8), Data("{\\\"hooks\\\":[]}".utf8)] {
    do { _ = try CodexHooksConfig.merged(existing: malformed, command: own); fatalError("accepted malformed config") }
    catch CodexHooksConfig.ConfigError.invalidJSON { }
    catch CodexHooksConfig.ConfigError.invalidHooks { }
}
print("Codex config fixture checks passed")
''')
            executable = Path(temp) / "checks"
            compile_command = [
                shutil.which("swiftc"),
                str(ROOT / "NotchBuddy/Sources/App/CodexHooksConfig.swift"),
                str(harness), "-o", str(executable),
            ]
            compile_result = subprocess.run(compile_command, text=True, capture_output=True, check=False, timeout=90)
            if compile_result.returncode and "SDK is not supported by the compiler" in compile_result.stderr:
                # A partial local Xcode update can leave the default SDK ahead of swiftc.
                for version in ("MacOSX26.5.sdk", "MacOSX26.sdk", "MacOSX15.4.sdk"):
                    sdk = Path("/Library/Developer/CommandLineTools/SDKs") / version
                    if sdk.exists():
                        compile_result = subprocess.run(
                            compile_command + ["-sdk", str(sdk)],
                            text=True, capture_output=True, check=False, timeout=90,
                        )
                        if compile_result.returncode == 0:
                            break
            self.assertEqual(0, compile_result.returncode, compile_result.stderr)
            result = subprocess.run([str(executable), temp], text=True, capture_output=True, check=False, timeout=5)
            self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
