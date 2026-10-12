# Example — guide

What it is, in one sentence, then the steps to get there. No narrative between them.

## Install the CLI

Needs `uv` and Git.

```bash
uv tool install git+https://example.com/some-tool@v1.0.0
some-tool init
some-tool doctor
```

`some-tool doctor` confirms it: green means the install resolved, not that every feature works.

| step | what it does |
|---|---|
| `init` | writes the config file |
| `doctor` | checks the config authenticates |

Next: [GETTING_STARTED.md](#) covers the first real task.
