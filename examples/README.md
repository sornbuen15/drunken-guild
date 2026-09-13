# Examples & Walkthrough

Reference output for the flow, using a fictional app called **TaskFlow**.

> **TaskFlow** is a cross-platform mobile task manager (iOS + Android) with a Node.js/PostgreSQL
> backend. It's simple enough to understand at a glance, complex enough to demonstrate every part
> of the flow.

---

## Who This Is For

| You are... | Start here |
|---|---|
| New to this — want to try it on your own project | Read [`GETTING_STARTED.md`](../GETTING_STARTED.md) first, then use these examples as reference |
| Curious what the output looks like before running anything | Read the stages below |
| Writing a new skill or agent | Go to [`contributing/`](./contributing/) |

---

## The flow

```
/prd        →  PRD.md: the brief and the requirements in one file,
               every requirement carrying an id REQ-xxx and a MoSCoW class

/clarify    →  a short ranked list of decisions only the Boss can make,
               answered back into PRD.md

/ddd        →  DOMAIN.md: bounded contexts, shared vocabulary, core entities.
               Each context becomes an Epic

/breakdown  →  the Jira hierarchy — REQ → Epic → Story → Task → Subtask —
               every level labelled req:REQ-xxx. Nothing is created until
               the Boss approves the printed plan

/build      →  one task, one branch, one PR. The test comes from the ticket's
               acceptance and is seen failing first. The Boss merges

/audit      →  every requirement traced to a task and to a test that passes on
               the merged tree. Gaps become tickets; the day's report is written
```

---

## Stages

- [`00-setup/`](./00-setup/) — filled project context files for TaskFlow
- [`contributing/`](./contributing/) — how to write a new skill or agent, annotated

Recorded output for each of the six commands is not here yet. The three stage directories that
used to sit alongside `00-setup/` were the output of `/init-project`, `/refine` and `/estimate` — <!-- drift-ok: naming the retired commands is what this sentence is for -->
skills retired with the old flow — and a recorded walkthrough of commands that no longer exist is
worse than none. `RETIRED.md` names the commit they are recoverable from.
