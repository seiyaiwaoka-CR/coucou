/** One visible session per provider. New prompts select a session; old events do not clear it. */
export class HookSessionRouter {
  private owners = new Map<string, { sessionId: string; turnId?: string; revision: number }>();
  private nextRevision = 0;

  revision(taskId: string): number | undefined { return this.owners.get(taskId)?.revision; }

  private select(taskId: string, sessionId: string, turnId: string | undefined): void {
    this.owners.set(taskId, { sessionId, turnId, revision: ++this.nextRevision });
  }

  accepts(taskId: string, sessionId: string, turnId: string | undefined,
          event: string, currentlyActive: boolean): boolean {
    const owner = this.owners.get(taskId);
    const sameSession = owner?.sessionId === sessionId;
    if (event === "UserPromptSubmit" || event === "PermissionRequest") {
      this.select(taskId, sessionId, turnId);
      return true;
    }
    if (event === "SessionStart" || event === "PreToolUse") {
      if (owner && !sameSession && currentlyActive) return false;
      if (!sameSession) this.select(taskId, sessionId, turnId);
      if (event === "PreToolUse" && !this.matchesTurn(this.owners.get(taskId), turnId)) return false;
      return true;
    }
    if (!sameSession || !this.matchesTurn(owner, turnId)) return false;
    if (event === "SessionEnd") this.owners.delete(taskId);
    return true;
  }

  private matchesTurn(owner: { turnId?: string } | undefined, turnId: string | undefined): boolean {
    return !owner?.turnId || !turnId || owner.turnId === turnId;
  }
}

export interface ApprovalIdentity {
  requestId: string;
  taskId: string;
  sessionId: string;
}

/** The rendered request ID is captured on pointer down, before a later hook can arrive. */
export function decisionTask(pending: ApprovalIdentity | null, displayedRequestId: string | null): string | null {
  if (!pending || !displayedRequestId || pending.requestId !== displayedRequestId) return null;
  return pending.taskId;
}

export class ApprovalClickBinding {
  private displayedRequestId: string | null = null;
  private pressedRequestId: string | null = null;

  show(requestId: string | null): void { this.displayedRequestId = requestId; }
  press(): void { this.pressedRequestId = this.displayedRequestId; }
  release(): string | null {
    const id = this.pressedRequestId ?? this.displayedRequestId;
    this.pressedRequestId = null;
    return id;
  }
}
