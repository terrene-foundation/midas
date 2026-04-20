# Midas Worktree Policy

## MUST: Isolated Worktrees for Agent Sessions

Every Claude Code session working on the Midas project MUST use an isolated git worktree. Working directly on `main` in the shared repository is BLOCKED.

**Why:** The shared `training/midas` repository is used by multiple agents (e.g., `zai`, `mm`, `glm`) and the human owner. Direct work on `main` creates merge conflicts, overwrites uncommitted changes, and makes it impossible to attribute changes to specific agents.

## Branch Naming Convention

| Agent/Branch | Purpose | Owner |
|---|---|---|
| `main` | Production-ready code, human-reviewed | Human owner |
| `zai` | Claude Opus agent worktree | Claude (Opus) |
| `mm` | Gemini agent worktree | Gemini |
| `glm` | GLM agent worktree | GLM |

Agents MUST NOT push to `main` directly. All changes merge via PR or explicit human approval.

## Worktree Creation

When starting a session:
```
EnterWorktree(name="zai")  # Creates .claude/worktrees/zai
git merge main --no-edit   # Catch up to latest main
```

When ending a session:
```
git add -A && git commit   # Commit all work
ExitWorktree(action="keep")  # Keep work for future sessions
```

## Conflict Resolution

- If `git merge main` has conflicts, the agent resolves them in favor of `main`'s intent unless the agent's branch has spec-backed reasoning for the divergence.
- Stashed changes (`git stash list`) from prior sessions should be checked before starting new work.

## Historical Context

- Prior sessions worked directly on `main`, which worked when there was only one agent. As of 2026-04-20, multiple agents operate on this repo simultaneously.
- The `mm` branch diverged from the initial commit with its own history (phase 01-02). The `zai` branch has 3 commits ahead of main from prior sessions.

**Origin:** Round 9 red team session (2026-04-20). User requested isolation after discovering potential cross-agent interference.
