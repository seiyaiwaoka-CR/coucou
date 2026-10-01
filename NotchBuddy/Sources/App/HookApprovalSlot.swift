import Foundation

/// A file descriptor can be reused by the OS. Decisions and expiry therefore
/// require the unique card ID as well as any captured descriptor.
struct HookApprovalSlot {
    struct Request {
        let id: UUID
        let fd: Int32
        let taskId: String
        let sessionId: String
    }

    private(set) var request: Request?

    var isOccupied: Bool { request != nil }

    mutating func open(fd: Int32, taskId: String, sessionId: String) -> Request? {
        guard request == nil else { return nil }
        let next = Request(id: UUID(), fd: fd, taskId: taskId, sessionId: sessionId)
        request = next
        return next
    }

    func matches(id: UUID, fd: Int32? = nil) -> Bool {
        guard let request, request.id == id else { return false }
        return fd == nil || request.fd == fd
    }

    mutating func take(id: UUID) -> Request? {
        guard matches(id: id) else { return nil }
        defer { request = nil }
        return request
    }
}
