import Foundation

enum HookCommand {
    /// A hook command is evaluated by a POSIX shell. Single quotes keep valid
    /// file names containing $, backticks, backslashes or spaces literal.
    static func quoted(_ path: String) -> String {
        "'" + path.replacingOccurrences(of: "'", with: "'\"'\"'") + "'"
    }

    /// Exact command forms emitted before POSIX quoting was adopted.
    static func legacyCodexCommands(for path: String) -> [String] {
        let old = "\"" + path.replacingOccurrences(of: "\"", with: "\\\"") + "\" codex"
        return [old, "/bin/sh " + old]
    }
}
