"""Exercise the production approval slot, session routing, and shell quoting."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "NotchBuddy/Sources/App"


class HookSafetyChecks(unittest.TestCase):
    @unittest.skipUnless(shutil.which("swiftc"), "Swift compiler required")
    def test_request_session_and_command_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            main = Path(temp) / "main.swift"
            main.write_text(r'''
import Foundation

var slot = HookApprovalSlot()
let first = slot.open(fd: 7, taskId: "integration_codex", sessionId: "A")!
precondition(slot.open(fd: 8, taskId: "integration_claude", sessionId: "B") == nil)
precondition(slot.matches(id: first.id, fd: 7))
precondition(slot.take(id: UUID()) == nil)
precondition(slot.take(id: first.id)?.taskId == "integration_codex")
let second = slot.open(fd: 7, taskId: "integration_claude", sessionId: "B")!
precondition(!slot.matches(id: first.id, fd: 7)) // OS reused the descriptor
precondition(slot.take(id: first.id) == nil)       // stale card or timer
precondition(slot.take(id: second.id)?.taskId == "integration_claude")

var router = HookSessionRouter()
let codex = "integration_codex"
precondition(router.accepts(taskId: codex, sessionId: "A", turnId: "a1", event: "UserPromptSubmit", currentlyActive: false))
let oldRevision = router.revision(for: codex)
precondition(!router.accepts(taskId: codex, sessionId: "B", turnId: nil, event: "SessionStart", currentlyActive: true))
precondition(router.accepts(taskId: codex, sessionId: "B", turnId: "b1", event: "UserPromptSubmit", currentlyActive: true))
precondition(router.revision(for: codex) != oldRevision)
precondition(!router.accepts(taskId: codex, sessionId: "A", turnId: "a1", event: "Stop", currentlyActive: true))
precondition(!router.accepts(taskId: codex, sessionId: "A", turnId: nil, event: "SessionEnd", currentlyActive: true))
precondition(!router.accepts(taskId: codex, sessionId: "B", turnId: "a1", event: "PostToolUse", currentlyActive: true))
precondition(router.accepts(taskId: codex, sessionId: "B", turnId: "b1", event: "Stop", currentlyActive: true))

let tricky = #"/tmp/codex-$(printf UNSAFE)`printf BAD`\backslash'quote\"double"#
let process = Process()
process.executableURL = URL(fileURLWithPath: "/bin/sh")
process.arguments = ["-c", "printf '%s' " + HookCommand.quoted(tricky)]
let output = Pipe()
process.standardOutput = output
try process.run()
process.waitUntilExit()
precondition(process.terminationStatus == 0)
precondition(String(data: output.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) == tricky)
''')
            executable = Path(temp) / "checks"
            cmd = [shutil.which("swiftc"), *map(str, (
                APP / "HookApprovalSlot.swift", APP / "HookSessionRouter.swift", APP / "HookCommand.swift", main,
            )), "-o", str(executable)]
            result = subprocess.run(cmd, text=True, capture_output=True, check=False, timeout=90)
            if result.returncode and "SDK is not supported by the compiler" in result.stderr:
                for version in ("MacOSX26.5.sdk", "MacOSX26.sdk", "MacOSX15.4.sdk"):
                    sdk = Path("/Library/Developer/CommandLineTools/SDKs") / version
                    if sdk.exists():
                        result = subprocess.run(cmd + ["-sdk", str(sdk)], text=True,
                                                capture_output=True, check=False, timeout=90)
                        if result.returncode == 0:
                            break
            self.assertEqual(0, result.returncode, result.stderr)
            result = subprocess.run([str(executable)], text=True, capture_output=True,
                                    check=False, timeout=5)
            self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
