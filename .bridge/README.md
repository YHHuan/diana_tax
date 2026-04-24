# Claude <-> Codex Bridge

Single source of truth: `.bridge/bridge.md`

Protocol:
1. Update `Task ID` whenever a new task is assigned.
2. Set `Assignee` to `claude`, `codex`, or `shared`.
3. Set `Status` to `todo`, `doing`, `blocked`, or `done`.
4. Keep `Summary` short. Put actionable detail under `Details`.
5. Append a short note to `Activity Log` whenever work starts, blocks, or finishes.

Codex monitor behavior:
- Watches `.bridge/bridge.md` for changes.
- Only executes tasks where `Assignee: codex` or `Assignee: shared`.
- Ignores task IDs it already handled.
- After finishing a task, writes the result back into the bridge and keeps watching.

Current repo state at initialization:
- Remote `main` is empty.
- Bridge files were created locally on 2026-04-24.
