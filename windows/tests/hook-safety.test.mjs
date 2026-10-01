import assert from "node:assert/strict";
import test from "node:test";
import { ApprovalClickBinding, HookSessionRouter, decisionTask } from "../src/island/hookSafety.ts";

test("a visible Codex approval can only decide its own request and provider", () => {
  const codex = { requestId: "req-A", taskId: "integration_codex", sessionId: "session-A" };
  const replacement = { requestId: "req-B", taskId: "integration_claude", sessionId: "session-B" };
  assert.equal(decisionTask(codex, "req-A"), "integration_codex");
  assert.equal(decisionTask(replacement, "req-A"), null);
  assert.equal(decisionTask(null, "req-A"), null); // expired card
  assert.equal(decisionTask(replacement, "req-B"), "integration_claude");
  const button = new ApprovalClickBinding();
  button.show("req-A");
  button.press();
  button.show("req-B");
  assert.equal(decisionTask(replacement, button.release()), null);
  button.show("req-B");
  button.press();
  button.show(null); // expiry before pointer up
  assert.equal(decisionTask(null, button.release()), null);
});

test("an older session cannot finish or clear the selected provider pill", () => {
  const router = new HookSessionRouter();
  const codex = "integration_codex";
  const claude = "integration_claude";
  assert.equal(router.accepts(codex, "A", "turn-A", "UserPromptSubmit", false), true);
  const revisionA = router.revision(codex);
  assert.equal(router.accepts(codex, "B", undefined, "SessionStart", true), false);
  assert.equal(router.accepts(codex, "B", "turn-B", "UserPromptSubmit", true), true);
  assert.notEqual(router.revision(codex), revisionA);
  assert.equal(router.accepts(codex, "A", "turn-A", "Stop", true), false);
  assert.equal(router.accepts(codex, "A", undefined, "SessionEnd", true), false);
  assert.equal(router.accepts(codex, "B", "turn-A", "PostToolUse", true), false);
  assert.equal(router.accepts(codex, "B", "turn-B", "Stop", true), true);
  assert.equal(router.accepts(claude, "C", undefined, "UserPromptSubmit", false), true);
  assert.equal(router.accepts(codex, "B", undefined, "SessionEnd", false), true);
  assert.equal(router.accepts(claude, "C", undefined, "Stop", true), true);
});
