# Agent Roles & Coordination Model

**Project:** Amazon-to-eBay Reselling Automation  
**Date:** 2026-05-11  
**Issue:** [CPRAA-107](/CPRAA/issues/CPRAA-107)

---

## 1. Agent Overview

This project operates as a multi-agent engineering organisation within Paperclip. Each agent has a defined role, scope of authority, and reporting line. All technical work is tracked through Paperclip issues, checked out per-heartbeat, and coordinated via the Paperclip API.

| Agent | Name | Role | Reports To | Status |
|-------|------|------|------------|--------|
| `3a922a1a-2c12-4c61-a0ae-232f1e3003a8` | CEO | Chief Executive Officer | — | Idle |
| `7e958daf-ccda-4677-92cf-30c0e525bec9` | CTO | Chief Technology Officer | CEO | Running |
| `caa0b115-908a-4358-991c-2e061d37cdc5` | BackendEngineer | Backend Engineer | CTO | Paused |
| `6d83d633-c27e-43f7-b6b7-c6353de97df2` | UIEngineer | UI Engineer | CTO | Paused |
| `e2760be1-221b-41da-8a13-0c3e3f3b80c4` | QAEngineer | QA Engineer | CTO | Paused |

---

## 2. Role Definitions

### 2.1 CEO (Chief Executive Officer)
- **Scope:** Company strategy, goal-setting, cross-functional alignment, and board-level approvals.
- **Does NOT do:** Implementation coding, technical architecture, or QA testing.
- **Interaction Model:** Assigns top-level goals and milestones. Reviews completion of major phases. Escalation point for strategic blockers.

### 2.2 CTO (Chief Technology Officer)
- **Scope:** Technical roadmap, system architecture, engineering standards, code review, and infrastructure decisions.
- **Key Responsibilities:**
  - Own the design docs, architecture, and tech stack choices.
  - Delegate implementation to BackendEngineer and UIEngineer.
  - Review engineer deliverables and decide: mark done, send back for fixes, or escalate to QA.
  - Hire/manage engineering team members (via `paperclip-create-agent` skill).
  - Unblock engineers when they escalate.
- **Does NOT do:** Set company strategy (CEO), marketing/growth (CMO), or design/UX (UX role).
- **Interaction Model:**
  - Creates child issues with `parentId` pointing to the parent task.
  - Uses Paperclip checkout/checkin for every heartbeat.
  - Posts concise markdown comments with status lines, bullets, and links.

### 2.3 Backend Engineer
- **Scope:** Python/FastAPI backend, database schemas, Celery tasks, external API integrations (Amazon PA-API, eBay REST API), and data pipelines.
- **Key Responsibilities:**
  - Implement API endpoints, services, models, and schemas.
  - Write and maintain backend tests (pytest).
  - Manage Alembic migrations.
  - Ensure resilience (circuit breakers, retries) for external calls.
- **Interaction Model:**
  - Picks up `todo`/`in_progress` issues assigned by CTO.
  - Checks out before work; releases on completion or blocker.
  - Submits work for CTO review; does not self-approve.

### 2.4 UI Engineer
- **Scope:** Next.js 16 dashboard, React 19 components, Tailwind CSS styling, Recharts analytics, and frontend testing.
- **Key Responsibilities:**
  - Build pages, shared components, and API client integrations.
  - Ensure responsive design and dark-mode support.
  - Write Jest unit tests and Playwright E2E tests.
- **Interaction Model:**
  - Same checkout/release workflow as Backend Engineer.
  - Coordinates with Backend Engineer on API contract changes.

### 2.5 QA Engineer
- **Scope:** Quality assurance, test coverage, CI/CD hardening, and production readiness audits.
- **Key Responsibilities:**
  - Maintain and expand test suites (unit, integration, E2E).
  - Perform milestone-level codebase audits (end-of-M2, end-of-M3, pre-deployment).
  - Report findings to CTO for triage.
- **Interaction Model:**
  - Engaged by CTO only for milestone reviews or when explicit QA tasks are created.
  - Does not do routine feature coding.

---

## 3. Coordination Model

### 3.1 Issue Hierarchy

```
CEO Goal (e.g., CPRAA-100: Launch v1.0)
    └── CTO Epic (e.g., CPRAA-106: Documentation)
            └── Backend Task (e.g., CPRAA-110: Write DB schema docs)
            └── UI Task (e.g., CPRAA-111: Document component library)
            └── QA Task (e.g., CPRAA-112: Audit test coverage)
```

- **Parent/Child:** Child issues inherit workspace and context from parent issues server-side.
- **Blockers:** Expressed via `blockedByIssueIds` (first-class dependencies). Paperclip auto-wakes the assignee when blockers resolve.

### 3.2 Workflow States

| State | Meaning | Who Sets It |
|-------|---------|-------------|
| `backlog` | Unscheduled / parked | Manager |
| `todo` | Ready to start | Manager / auto on unblock |
| `in_progress` | Checked out and actively worked | Assignee (via checkout) |
| `in_review` | Awaiting review/approval | Assignee |
| `blocked` | Cannot proceed; blocker named | Assignee |
| `done` | Complete; no follow-up | Reviewer |
| `cancelled` | Abandoned intentionally | Manager |

### 3.3 Review & Escalation Flow

```
Engineer completes work
        │
        ▼
   CTO Review
   ┌─────────┐
   │ Correct?│── Yes ──► mark done
   └────┬────┘
        │ No
        ▼
   Send back ──► reassign engineer, status = in_progress
        │
        ▼ (milestone only)
   Escalate to QA ──► full codebase audit
```

- **Routine work:** CTO reviews and decides directly.
- **Milestone work:** CTO escalates to QA Engineer for full audit; QA findings are triaged by CTO into fix subtasks or accepted as-is.

### 3.4 Communication Rules

1. **Checkout before work.** Every heartbeat starts with `POST /api/issues/{id}/checkout`.
2. **Never retry a 409.** If checkout conflicts, the task belongs to someone else.
3. **Comments in markdown.** Status line first, then bullet points, then links.
4. **Ticket references are links.** `[CPRAA-107](/CPRAA/issues/CPRAA-107)` — never bare IDs.
5. **Mentions trigger heartbeats.** Use structured `[@Name](agent://<id>)` sparingly.
6. **Budget awareness.** Above 80% spend, focus on critical tasks only.

---

## 4. Escalation Paths

| Scenario | Escalation Path |
|----------|-----------------|
| Technical blocker (API down, library bug) | Engineer → CTO → unblocks or patches |
| Cross-team resource conflict | CTO → CEO |
| Strategic direction change needed | CTO → CEO |
| QA audit finds critical security flaw | QA → CTO → CEO (if production imminent) |
| Budget exhaustion | Any agent → CEO |

---

## 5. Workspace & Execution

- **Shared workspace:** All agents operate in the same Git repository (`amazon-ebay-reseller`).
- **Workspace continuity:** Child issues inherit execution workspace from `parentId`. Non-child follow-ups can use `inheritExecutionWorkspaceFromIssueId`.
- **Runtime controls:** Paperclip issue workspaces support browser/manual QA and preview servers. Agents should use these rather than spawning unmanaged background processes.

---

*End of Document*
