# wp-contrib

`wp-contrib` is a minimal local CLI for investigating and fixing open-source WordPress plugin issues. It performs Git, GitHub, validation, state, and publishing work deterministically. OpenCode is invoked once as the coding worker. Nothing is pushed and no pull request is created until you run `approve` and explicitly confirm.

## Prerequisites

- Python 3.11 or newer
- Git
- [GitHub CLI](https://cli.github.com/)
- [OpenCode](https://opencode.ai/docs/)

Authenticate GitHub:

```bash
gh auth login
gh auth status
```

Install OpenCode using its current installation instructions, then configure a provider using OpenCode's own authentication flow. Confirm it works with:

```bash
opencode --version
opencode models
```

## Installation

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
wp-contrib --help
```

For development:

```bash
pip install -e '.[dev]'
pytest
```

Copy `config.example.yaml` to `config.yaml` to override defaults. `config.yaml`, local state, logs, environment files, and workspace contents are ignored by Git.

## Workflow

Start work with:

```bash
wp-contrib solve "https://github.com/owner/repository/issues/123"
# or
python main.py solve "https://github.com/owner/repository/issues/123"
```

The command validates prerequisites and authentication, retrieves the open issue, checks for potentially related open PRs, clones or verifies the repository under `workspaces/`, refuses a dirty tree, creates a sanitized issue branch, and runs one non-interactive OpenCode coding session. It then detects repository-provided Composer, PHPUnit, PHPCS, PHPStan, and npm validation and shows a review report.

OpenCode is told to inspect repository instructions, make the smallest safe fix, test it where practical, and never commit, push, or open a PR. Issue content is not sent to a model before this coding phase, and the repository itself is not embedded in the prompt.

Inspect and re-run deterministic work at any time:

```bash
wp-contrib status
wp-contrib diff
wp-contrib test
```

State is atomically persisted in `.wp-contrib-state.json`, so these commands survive restarting the CLI. Validation failures are reported and block approval.

After reviewing the raw diff and validation output:

```bash
wp-contrib approve
```

The command displays the issue, branch, changed files, and validation results, then asks for explicit confirmation. Only after confirmation does it stage and commit the changes, create or reuse your GitHub fork, configure `upstream` and `origin`, push without force, and create a PR against the upstream default branch. The PR description is generated from deterministic state and Git output.

To stop without deleting the workspace or branch:

```bash
wp-contrib abort
```

## Safety and troubleshooting

- Existing repositories, branches, and uncommitted changes are never deleted or overwritten.
- There is no force push and no automatic dependency installation.
- `gh` uses credentials established by `gh auth login`; OpenCode uses its own configuration. Secrets are not read into application state or logs.
- If a tool is missing, the CLI prints its installation URL. If GitHub access fails, run `gh auth status` and verify repository access.
- If validation reports a missing executable such as `vendor/bin/phpunit`, install the repository's dependencies according to its `CONTRIBUTING.md` or `README.md`, then run `wp-contrib test`.
- If OpenCode fails or times out, its actionable error is shown and state remains available for inspection. No publishing occurs.
