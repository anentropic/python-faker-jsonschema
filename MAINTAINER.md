# Maintainer Guide

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) for dependency and environment management
- [just](https://github.com/casey/just) as a command runner
- [prek](https://github.com/j178/prek) — fast, Rust-based drop-in replacement for pre-commit (used in CI)

## Setup from scratch

```bash
# Install all dev dependencies (locked versions)
uv sync --group dev

# Install pre-commit hooks
prek install

# Verify everything works
just test
```

For docs development, also sync the docs group:

```bash
uv sync --group docs
```

## Common tasks (justfile)

Run `just` with no arguments to see all available commands.

| Command | Description |
|---------|-------------|
| `just test` | Lint + run tests |
| `just pytest` | Run tests with verbose output, drops into pdb on failure |
| `just lint` | Run ruff linter |
| `just format` | Auto-format code with ruff |
| `just typecheck` | Run basedpyright type checker |
| `just shell` | Open an IPython REPL with project dependencies available |
| `just docs-build` | Build docs with mkdocs (strict mode) |
| `just docs-serve` | Serve docs locally with live reload (default port 8000) |
| `just fuzz` | Run multi-seed fuzz tests matching CI settings |

## Running tests like CI

CI runs quality gates via `prek run --all-files`, then tests across Python 3.11-3.14, plus a multi-seed fuzz matrix. Use `just fuzz` to run the full seed matrix locally.

## Pre-commit hooks

Hooks are defined in `.pre-commit-config.yaml` and run via `prek` in CI. They include:

- Trailing whitespace, EOF fixer, JSON/TOML/YAML checks
- Ruff lint + format
- uv lock check
- basedpyright type checking
- blacken-docs (formats code blocks in docs)
- detect-secrets

## Docs

Docs are built with mkdocs-material and deployed to GitHub Pages automatically on push to `main` (via `.github/workflows/docs.yml`).

```bash
just docs-serve       # preview locally at http://127.0.0.1:8000
just docs-build       # check for build errors
```

## Releasing

Releases are triggered by pushing a version tag. The workflow (`.github/workflows/release.yml`) runs quality gates, builds distributions, validates them on Python 3.11 and 3.14, publishes to PyPI (via trusted publishing), and creates a GitHub Release.

### Steps

1. Update the version in `pyproject.toml`
2. Commit the version bump
3. Tag and push:

```bash
git tag v1.0.0
git push origin main --tags
```

The tag must match `v<major>.<minor>.<patch>` with an optional pre-release suffix:

- `v1.0.0` — standard release
- `v1.0.0a1`, `v1.0.0-beta.2`, etc. — pre-release (anything after `-`)

### PyPI setup

Publishing uses [PyPI trusted publishing](https://docs.pypi.org/trusted-publishers/) (OIDC via `id-token: write` permission). The PyPI project must be configured with a trusted publisher pointing to this repo's `release.yml` workflow and the `pypi` environment.

## TODOs

- Republish improved `js-regex` as new lib
- Make regex support optional to avoid Hypothesis dependency, or implement own regex generation strategy
