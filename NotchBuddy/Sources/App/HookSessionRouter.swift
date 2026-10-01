import Foundation

/// One visible session per provider. A newer prompt can take the pill; events
/// from the previous session cannot finish or clear the new one.
struct HookSessionRouter {
    private struct Owner {
        let sessionId: String
        let turnId: String?
        let revision: Int
    }
    private var owners: [String: Owner] = [:]
    private var nextRevision = 0

    func revision(for taskId: String) -> Int? { owners[taskId]?.revision }

    private mutating func select(taskId: String, sessionId: String, turnId: String?) {
        nextRevision += 1
        owners[taskId] = Owner(sessionId: sessionId, turnId: turnId, revision: nextRevision)
    }

    mutating func accepts(taskId: String, sessionId: String, turnId: String?,
                          event: String, currentlyActive: Bool) -> Bool {
        let owner = owners[taskId]
        let sameSession = owner?.sessionId == sessionId
        switch event {
        case "UserPromptSubmit", "PermissionRequest":
            select(taskId: taskId, sessionId: sessionId, turnId: turnId)
            return true
        case "SessionStart":
            guard owner == nil || sameSession || !currentlyActive else { return false }
            if !sameSession { select(taskId: taskId, sessionId: sessionId, turnId: turnId) }
            return true
        case "PreToolUse":
            guard owner == nil || sameSession || !currentlyActive else { return false }
            if !sameSession { select(taskId: taskId, sessionId: sessionId, turnId: turnId) }
            return matchesTurn(owner: owners[taskId], turnId: turnId)
        default:
            guard sameSession, matchesTurn(owner: owner, turnId: turnId) else { return false }
            if event == "SessionEnd" { owners.removeValue(forKey: taskId) }
            return true
        }
    }

    private func matchesTurn(owner: Owner?, turnId: String?) -> Bool {
        guard let old = owner?.turnId, let turnId else { return true }
        return old == turnId
    }
}
