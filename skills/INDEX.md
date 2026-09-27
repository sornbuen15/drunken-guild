# Skill Index

Map task keywords to their absolute skill file paths. Load ONLY the relevant skill before executing.

- `project-docs` — Use when a step has to find, create or reconcile a project's own documents — "where does this project keep its PRD?", "there are two PRD.md files, which one win
  Path: $HOME/.claude/skills/project-docs/SKILL.md

- `audit` (`/audit`) — Use when a day's work ends, after tasks merge, or before anyone calls a requirement done — "what actually shipped today?", "does every Must have a passing test
  Path: $HOME/.claude/skills/audit/SKILL.md

- `breakdown` (`/breakdown`) — Use when agreed requirements need a backlog, or a bug found mid-flight needs a ticket — "turn the PRD into Jira tickets", "cut the backlog, a day per task", "fi
  Path: $HOME/.claude/skills/breakdown/SKILL.md

- `build` (`/build`) — Use when a Task or Bug ticket is picked up for work — "pick up DG-… and implement it", "fix the bug in this ticket and open a PR", "take the next card". Execute
  Path: $HOME/.claude/skills/build/SKILL.md

- `clarify` (`/clarify`) — Use when a PRD reads cleanly but is not actually decided, after /prd and before /ddd — "what in the requirements is still undecided?", "ask me whatever you need
  Path: $HOME/.claude/skills/clarify/SKILL.md

- `ddd` (`/ddd`) — Use when a clarified PRD needs its domain modelled before /breakdown, or when one concept goes by two names — "work out the bounded contexts for this project",
  Path: $HOME/.claude/skills/ddd/SKILL.md

- `prd` (`/prd`) — Use when a project is starting, when the Boss describes something to build, or when a requirement is added before any backlog exists — "help me write down what
  Path: $HOME/.claude/skills/prd/SKILL.md

- `replan` (`/replan`) — Use when a requirement is added, cut or changed after the backlog exists — "we also need…", "drop REQ-… and the tickets under it", "the customer changed their m
  Path: $HOME/.claude/skills/replan/SKILL.md

- `ask-boss` — Use when an action is destructive, irreversible or merge-worthy and needs the Boss's OK — "you need my approval before dropping that database", "I'm away this a
  Path: $HOME/.claude/skills/ask-boss/SKILL.md

- `git-workflow` (`/git-workflow`) — Use when creating a branch, writing a commit, opening a PR, merging or releasing — "what should I name this branch?", "how should I commit this?", "which merge
  Path: $HOME/.claude/skills/git-workflow/SKILL.md

- `jira-tickets` — Use when writing, labelling, moving or closing a Jira ticket in this project — "what sections does a Bug ticket need?", "can I mark this Done now the PR is open
  Path: $HOME/.claude/skills/jira-tickets/SKILL.md

- `think-analyze-isolate` (`/isolate`) — Use when running, starting, deploying or integrating something, when a backgrounded command is reported working without evidence, or when a fix fails the same w
  Path: $HOME/.claude/skills/think-analyze-isolate/SKILL.md
