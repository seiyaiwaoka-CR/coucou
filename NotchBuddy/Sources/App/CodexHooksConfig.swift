import Foundation

/// The Codex configuration edit is kept independent of the UI and the user's home directory.
/// This also lets regression tests exercise the exact merge and removal code on fixtures.
enum CodexHooksConfig {
    static let events: [(name: String, timeout: Int)] = [
        ("SessionStart", 10), ("SessionEnd", 3),
        ("UserPromptSubmit", 10),
        ("PreToolUse", 10), ("PostToolUse", 10),
        ("PermissionRequest", 130),
        ("Stop", 10),
        ("SubagentStart", 10), ("SubagentStop", 10),
        ("Interrupt", 3),
    ]

    enum ConfigError: LocalizedError {
        case invalidJSON
        case invalidHooks
        case changedSincePreview

        var errorDescription: String? {
            switch self {
            case .invalidJSON: return "hooks.json is not a JSON object; no changes were written."
            case .invalidHooks: return "hooks.json has an unsupported hooks structure; no changes were written."
            case .changedSincePreview: return "hooks.json changed since the preview. Review it again before writing."
            }
        }
    }

    static func isManaged(_ command: String, expected: String) -> Bool {
        // The first PR used a direct App Store script without /bin/sh. Recognize that
        // exact old command as well so an update or uninstall can clean it up.
        command == expected || (expected.hasPrefix("/bin/sh ") && command == String(expected.dropFirst(8)))
    }

    static func containsManagedHook(_ data: Data?, command: String) -> Bool {
        guard let data,
              let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let hooks = root["hooks"] as? [String: Any] else { return false }
        return hooks.values.contains { value in
            guard let matchers = value as? [[String: Any]] else { return false }
            return matchers.contains { matcher in
                guard let entries = matcher["hooks"] as? [[String: Any]] else { return false }
                return entries.contains { isManaged($0["command"] as? String ?? "", expected: command) }
            }
        }
    }

    static func merged(existing: Data?, command: String) throws -> Data {
        var (root, hooks) = try parse(existing)
        for event in events {
            var matchers = try matcherList(hooks[event.name])
            matchers = removingManaged(from: matchers, command: command)
            matchers.append(["hooks": [["type": "command", "command": command, "timeout": event.timeout]]])
            hooks[event.name] = matchers
        }
        root["hooks"] = hooks
        return try JSONSerialization.data(withJSONObject: root, options: [.prettyPrinted, .sortedKeys])
    }

    static func removing(existing: Data, command: String) throws -> Data {
        var (root, hooks) = try parse(existing)
        for (event, value) in hooks {
            let matchers = removingManaged(from: try matcherList(value), command: command)
            if matchers.isEmpty { hooks.removeValue(forKey: event) }
            else { hooks[event] = matchers }
        }
        if hooks.isEmpty { root.removeValue(forKey: "hooks") }
        else { root["hooks"] = hooks }
        return try JSONSerialization.data(withJSONObject: root, options: [.prettyPrinted, .sortedKeys])
    }

    private static func parse(_ data: Data?) throws -> ([String: Any], [String: Any]) {
        guard let data else { return ([:], [:]) }
        guard let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw ConfigError.invalidJSON
        }
        guard root["hooks"] == nil || root["hooks"] is [String: Any] else {
            throw ConfigError.invalidHooks
        }
        let hooks = root["hooks"] as? [String: Any] ?? [:]
        for value in hooks.values { _ = try matcherList(value) }
        return (root, hooks)
    }

    private static func matcherList(_ value: Any?) throws -> [[String: Any]] {
        guard let value else { return [] }
        guard let matchers = value as? [[String: Any]],
              matchers.allSatisfy({ $0["hooks"] is [[String: Any]] }) else {
            throw ConfigError.invalidHooks
        }
        return matchers
    }

    private static func removingManaged(from matchers: [[String: Any]], command: String) -> [[String: Any]] {
        matchers.compactMap { matcher in
            guard let entries = matcher["hooks"] as? [[String: Any]] else { return matcher }
            let remaining = entries.filter { !isManaged($0["command"] as? String ?? "", expected: command) }
            guard !remaining.isEmpty else { return nil }
            var kept = matcher
            kept["hooks"] = remaining
            return kept
        }
    }
}
