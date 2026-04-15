# Decode Lab: Context Migration Between Agent Sessions

This document captures reusable patterns for transferring working context from
one AI agent session to another when approaching quota limits. The patterns here
are optimised for the `patra-darpan-pdf-semantic-index` project but apply to
any session that involves a technical pipeline with specific CLI commands,
branch state, and in-progress decisions.

## Single-Turn Intent Prompt

Use the following template instead of the two-turn "permission check" approach
(asking whether you may share a file, then sharing it in a follow-up). Combining
the intent and the attachment into one message preserves your remaining quota for
the actual work.

```
I am sharing a Warp terminal log from `~/tmp/warp-patra-darap-14-apr` for the
`patra-darpan-pdf-semantic-index` project. I am nearing my quota limit and need
to migrate this context to a secondary agent.

Please generate a high-density technical summary including:
1. **System State:** The current branch, completed milestones, and active build
   environment.
2. **CLI Commands:** Specific `uv run` or shell commands used for extraction and
   evaluation.
3. **Technical Decisions:** Decisions regarding model tiers (Flex vs. Standard)
   and context caching thresholds.
4. **Roadmap:** Clear next steps for a coding agent to execute.

Keep the output structured and minimalist to avoid context bloat in the next
session.
```

## Why the Single-Turn Structure Is Better

**Eliminates handshaking.** Sharing the intent and the file simultaneously saves
a full turn of dialogue, preserving your remaining quota for the actual task.

**Contextual framing.** Telling the model that the output is for "another agent"
forces it to prioritise technical tokens—commands, flags, logic—over
conversational filler or high-level explanations.

**Defined extraction criteria.** Listing specific categories such as "CLI
Commands" and "Technical Decisions" prevents the model from summarising
irrelevant environment noise or system paths that are not critical to the
roadmap.

**Constraint awareness.** Mentioning the quota limit and the need to avoid
"context bloat" instructs the model to be brief and structured. This is
especially helpful when using a "Thinking" model that might otherwise be overly
verbose.

## Pro-Tip for Warp Logs

When sharing terminal logs, mention the specific directory or branch name in the
prompt. For example:

```
patra-darpan-pdf-semantic-index/.build~/decode-lab on 🌱 feat/pdf-semantic-index
```

Grounding the model in the correct project root immediately reduces the chance
of hallucinated file paths in the generated commands.

Current active branches for reference:

```
* feat/pdf-semantic-index
+ main
  safe-main-before-link-source-chips
  safety/main-before-cahc-p60
```

## When to Use This Pattern

Apply this pattern whenever:
- you are approaching your token or request quota in a long working session
- you need to hand off a partially complete pipeline task to a fresh agent
- you want a compressed, agent-readable checkpoint of the current session state

Do not use this pattern as a substitute for durable documentation. Decisions
that should survive across sessions belong in
[docs/spasta-corpus-decisions.md](spasta-corpus-decisions.md), not only in a
terminal log summary.
