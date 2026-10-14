# Optional SDLC Practices

> These are reusable tools and recommendations, not company policy. Use them when they help the
> project or when its owner asks. A project's own approved process takes precedence.

Drunken Guild offers optional ways to make release, deployment and security work more deliberate.
It does not require every project to adopt these steps, add a new approval gate, or claim that a
check proves a system is secure.

## Keep the lifecycle boundaries clear

| Activity | Purpose | Useful result |
|---|---|---|
| Release preparation | Decide what is ready to distribute and explain the change | Readiness summary and proposed release notes |
| Version and tag | Identify a particular build when the project benefits from a stable identifier | Project-defined version or tag, when used |
| Deployment preparation | Work out how an approved release reaches a named environment | Target-specific preflight, verification and rollback plan |
| Deployment | Apply the project-approved procedure to the target | Observed deployment result |

A release note is not a deployment plan. A tag is useful when installs, artifacts or support need
an immutable version reference; a project may use another release identifier or no tag. A merge,
release and deployment are different events.

## Optional security touchpoints

| SDLC point | Optional practice | Existing support in this repository |
|---|---|---|
| Requirements | Note important assets, abuse cases, likelihood and impact beside the requirement or in a separate assessment | `/secure` can produce a small risk assessment; it does not assign requirement IDs or change an accepted PRD by itself |
| Design | Sketch trust boundaries and data flows; use STRIDE or another suitable threat lens; compare mitigations and residual risk | `/secure` supports a focused threat model; `/ddd` remains about domain concepts |
| Development | Run relevant static, dependency and secret checks available to the project | CI currently uses Ruff, mypy, Bandit, pip-audit and Gitleaks; use the project's own commands and report actual results |
| Review and test | Review security-sensitive changes and add tests for the identified abuse cases | The reviewer role can do a focused security review when requested or required by project guidance |
| Security assessment | Inspect the target configuration, access boundaries, secret references and operational assumptions | `/secure` can assess the files and evidence provided; never copy secret values into the assessment |

Choose only practices that fit the change. If a concern looks material, the agent may explain why
and offer the relevant skill or tool; it should not silently turn that suggestion into a project
requirement or block unrelated work. A project owner can adopt any practice as local policy.

## Skill and tool boundaries

- **Skills** help people reason, prepare checklists and record findings. `/secure` covers optional
  security assessment across lifecycle points; `/release-notes` prepares a release summary;
  `/prepare-deployment` separates target preparation from deployment execution.
- **Tools** perform repeatable checks. Prefer tools already configured by the project. Do not
  install tools or claim a check ran when it did not.
- **Project instructions** define any mandatory gates, approvers, release identifiers and target
  procedures. When those instructions exist, follow them; otherwise keep recommendations optional.
- **Publishing and deployment** remain explicit actions. A preparation skill produces a plan or
  report; it does not publish a release, create a tag, merge code or change a live environment.

## How to use

Install the skills only if useful:

```bash
drunken-install extras --only secure-by-design,release-notes-writer,deployment-preparation --apply
```

Or read the skill file directly from `plugins/drunken-extras/skills/` in a clone. The installation
command copies skills; it does not make them company policy.
