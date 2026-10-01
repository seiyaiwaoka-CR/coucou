import Foundation

enum HookCommand {
    /// A hook command is evaluated by a POSIX shell. Single quotes keep valid
    /// file names containing $, backticks, backslashes or spaces literal.
    static func quoted(_ path: String) -> String {
        "'" + path.replacingOccurrences(of: "'", with: "'\"'\"'") + "'"
    }
}
