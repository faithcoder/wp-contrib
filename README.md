# wp-contrib

`wp-contrib` is a minimal local CLI for investigating and fixing open-source WordPress plugin issues. It performs Git, GitHub, validation, state, and publishing work deterministically. A configurable local coding agent is invoked once for code investigation and modification. Nothing is pushed and no pull request is created until you run `approve` and explicitly confirm.

## Prerequisites

- Python 3.11 or newer
- Git
- [GitHub CLI](https://cli.github.com/)
- One supported coding agent: [OpenCode](https://opencode.ai/docs/), [Codex CLI](https://developers.openai.com/codex/cli/), or a compatible custom CLI

Authenticate GitHub:

```bash
gh auth login
gh auth status
```

Install and authenticate the agent you want to use. For OpenCode, use its own setup instructions and confirm it works with:

```bash
opencode --version
opencode models
```

For Codex, install the Codex CLI, authenticate it, and verify the session:

```bash
codex login
codex login status
codex --version
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

## Choose the coding agent

OpenCode is the default. To keep it, create `config.yaml` containing:

```yaml
agent:
  provider: opencode
  max_attempts: 2
```

To use Codex instead:

```yaml
agent:
  provider: codex
  max_attempts: 2
```

The Codex integration runs this non-interactive equivalent inside the cloned repository:

```bash
codex exec --sandbox workspace-write "TASK"
```

It does not use the dangerous sandbox/approval bypass option. Codex reads its existing local authentication and user configuration. The stable `codex exec` command and `workspace-write` sandbox are documented in the [official OpenAI Codex CLI reference](https://developers.openai.com/codex/cli/reference).

For another local AI agent, configure a subprocess argument template:

```yaml
agent:
  provider: custom
  max_attempts: 2
  command:
    - your-agent-command
    - --non-interactive
    - "{prompt}"
```

The command must be installed and available on `PATH`. `{prompt}` is replaced with the compact issue task. Arguments are executed directly without a shell, so shell operators, pipes, aliases, and redirection are not interpreted. Adjust the arguments to the agent's documented non-interactive interface.

## Step-by-step: first contribution

Run these commands in your normal Terminal. You do not need to start Codex or OpenCode separately: `wp-contrib solve` starts the provider selected in `config.yaml` when coding work is needed.

### 1. Open the project and activate Python

Every time you open a new Terminal window:

```bash
cd /Users/arif/Downloads/wp-contrib
source .venv/bin/activate
```

The prompt usually shows `(.venv)` after activation.

### 2. Authenticate GitHub

This is normally required only once:

```bash
gh auth login
gh auth status
```

### 3. Confirm the required tools

```bash
python --version
git --version
gh --version
# Run the one that you configured:
opencode --version
codex --version
```

Python must be version 3.11 or newer.

### 4. Solve an issue

Replace the URL with the open GitHub issue you want to fix:

```bash
wp-contrib solve "https://github.com/owner/repository/issues/123"
```

For example:

```bash
wp-contrib solve "https://github.com/WordPress/two-factor/issues/956"
```

During application development, the equivalent command is:

```bash
python main.py solve "https://github.com/owner/repository/issues/123"
```

The command validates prerequisites and authentication, retrieves the open issue, checks for potentially related open PRs, clones or verifies the repository under `workspaces/`, refuses a dirty tree, creates a sanitized issue branch, and runs one non-interactive coding-agent session. It then detects repository-provided Composer, PHPUnit, PHPCS, PHPStan, and npm validation and shows a review report.

The selected agent is told to inspect repository instructions, make the smallest safe fix, test it where practical, and never commit, push, or open a PR. Issue content is not sent to a model before this coding phase, and the repository itself is not embedded in the prompt.

### While the coding agent is running

The current version captures the agent's output, so the original Terminal may look quiet while Codex or OpenCode investigates and edits the repository. This can be normal. An agent may inspect files for several minutes before creating a visible diff.

Open a second Terminal window and check the saved workflow state:

```bash
cd /Users/arif/Downloads/wp-contrib
source .venv/bin/activate
wp-contrib status
```

Check whether an agent process is running:

```bash
ps aux | grep -E "codex exec|opencode run"
```

Inspect the workspace directly without changing anything:

```bash
cd /Users/arif/Downloads/wp-contrib/workspaces/REPOSITORY_NAME
git status --short
git diff
```

Do not run another `wp-contrib solve` for the same issue while the first command is still running. Do not interrupt the agent merely because the diff is initially empty.

### Why `wp-contrib solve` should run from Terminal

For the normal issue workflow, run `wp-contrib solve` directly in your regular Terminal:

```text
Terminal → wp-contrib → configured coding agent
```

Do not open Codex or OpenCode first and ask it to execute `wp-contrib solve`. That creates a nested workflow:

```text
Coding agent → wp-contrib → another coding-agent process
```

Nesting can cause confusing permissions, duplicate agent sessions, and unnecessary token usage. Start an agent directly only when revising an already-created PR or doing deliberate manual work inside its existing workspace.

### 5. Review the coding agent's work

After `solve` finishes, run each command separately:

```bash
wp-contrib status
```

```bash
wp-contrib diff
```

```bash
wp-contrib test
```

`status` shows the issue and workflow state. `diff` shows the actual uncommitted code changes without an AI summary. `test` reruns validation detected from the repository. Read the diff and test failures before continuing.

State is atomically persisted in `.wp-contrib-state.json`, so these commands still work after closing and reopening the CLI. Validation failures block approval.

### 6. Approve and create the pull request

Only after you are satisfied with the changes and validation:

```bash
wp-contrib approve
```

Review the summary one more time. At the confirmation prompt, type `y` only if you want to commit, push to your fork, and create the PR. Typing `n` leaves everything local.

Only after confirmation does the command stage and commit changes, create or reuse your GitHub fork, configure `upstream` and `origin`, push without force, and create a PR against the upstream default branch. The PR description is generated from deterministic state and Git output.

### 7. Check the pull request

Open the URL printed by `wp-contrib approve`. You can also list your PRs with:

```bash
gh pr status
```

Do not delete the local workspace or issue branch while the PR is under review.

## Responding to pull-request feedback

A PR commonly needs one or more revisions. Keep using the same local workspace and branch. Do not run `wp-contrib solve` again for the same issue, because the workflow and branch already exist.

### 1. Read and copy the feedback

Read the review on GitHub. To inspect it from Terminal, use the PR number shown in the PR URL:

```bash
gh pr view PR_NUMBER --repo owner/repository --comments
```

### 2. Ask your selected agent to make the requested revision

Move into the cloned repository. For issue `956` in `WordPress/two-factor`, that is:

```bash
cd /Users/arif/Downloads/wp-contrib/workspaces/two-factor
```

If your provider is OpenCode, run one focused task containing the reviewer feedback:

```bash
opencode run "Address the following review feedback on the current PR. Read AGENTS.md and CONTRIBUTING.md if present, inspect the existing branch and diff, make only the requested changes, update tests when appropriate, run relevant tests, and do not commit, push, or create a PR. Reviewer feedback: PASTE_FEEDBACK_HERE"
```

If your provider is Codex, run:

```bash
codex exec --sandbox workspace-write "Address the following review feedback on the current PR. Read AGENTS.md and CONTRIBUTING.md if present, inspect the existing branch and diff, make only the requested changes, update tests when appropriate, run relevant tests, and do not commit, push, or create a PR. Reviewer feedback: PASTE_FEEDBACK_HERE"
```

For a custom provider, use the same focused task with that tool's non-interactive command. This manual revision step does not change the provider stored in `config.yaml`.

You can also edit the files yourself instead of using an AI agent.

### 3. Return to wp-contrib and review again

```bash
cd /Users/arif/Downloads/wp-contrib
source .venv/bin/activate
```

Then repeat the review commands:

```bash
wp-contrib status
```

```bash
wp-contrib diff
```

```bash
wp-contrib test
```

### 4. Approve the revision

If the new diff is correct and validation passes:

```bash
wp-contrib approve
```

Confirm with `y`. Because the workflow already contains a PR URL, `wp-contrib` commits and pushes the revision to the same branch and updates the existing PR. It does not create a second PR. GitHub automatically adds the new commit to the open PR.

Repeat this feedback → edit → diff → test → approve cycle until the PR is accepted.

If the maintainer requests a rebase or the upstream branch has moved significantly, handle that carefully inside the workspace. Never force-push unless the project maintainer explicitly requires it; `wp-contrib` itself never force-pushes.

## Tracking all contributions

The contribution dashboard discovers pull requests authored by your authenticated GitHub account. It does not use an AI agent or consume model tokens.

Authenticate GitHub first:

```bash
gh auth login
gh auth status
```

Fetch the latest PR data and display the terminal dashboard:

```bash
cd /Users/arif/Downloads/wp-contrib
source .venv/bin/activate
wp-contrib prs --refresh
```

The top grid shows total, open, draft, needs-attention, merged, and closed counts. The list below shows repository, PR number, title, status, review or feedback state, checks, and last update. PR numbers are clickable in supported terminals.

Every refresh also creates a standalone local dashboard page:

```text
/Users/arif/Downloads/wp-contrib/CONTRIBUTIONS.md
```

The page contains a Markdown statistics grid and the complete PR list with GitHub links. It is generated data, ignored by Git, and overwritten on each refresh.

Show the cached dashboard without contacting GitHub:

```bash
wp-contrib prs
```

Refresh automatically while the Terminal remains open:

```bash
wp-contrib prs --watch
```

Watch mode refreshes every five minutes by default. Choose another interval of at least 30 seconds:

```bash
wp-contrib prs --watch --interval 60
```

Stop watch mode with `Ctrl-C`. You can limit how many recently updated authored PRs are tracked:

```bash
wp-contrib prs --refresh --limit 250
```

On the first refresh, existing comments and reviews establish the baseline. Later refreshes label a PR `New feedback` when its combined review/comment count increases. A persistent `Changes requested` review decision remains in the needs-attention count. Check results are summarized as passing, pending, failing, not configured, or unknown.

Watch mode is automatic only while its Terminal process is running. When `wp-contrib` is closed, nothing runs in the background. GitHub notifications remain the source for immediate email/mobile alerts; a future optional macOS `launchd` or Linux systemd timer can provide background refresh and desktop notifications without adding a permanent application server.

## Stop or abandon local work

To stop without deleting the workspace or branch:

```bash
wp-contrib abort
```

## Safety and troubleshooting

- Existing repositories, branches, and uncommitted changes are never deleted or overwritten.
- There is no force push and no automatic dependency installation.
- `gh` uses credentials established by `gh auth login`; OpenCode, Codex, or the custom agent uses its own local authentication. Secrets are not read into application state or logs.
- If a tool is missing, the CLI prints its installation URL. If GitHub access fails, run `gh auth status` and verify repository access.
- If validation reports a missing executable such as `vendor/bin/phpunit`, install the repository's dependencies according to its `CONTRIBUTING.md` or `README.md`, then run `wp-contrib test`.
- If the coding agent fails or times out, its actionable error is shown and state remains available for inspection. No publishing occurs.
