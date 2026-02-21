#!/usr/bin/env bash
# Usage: ./scripts/bump_version.sh <new_version>
# Example: ./scripts/bump_version.sh 0.13.4
#
# This script:
#   1. Updates the version in pyproject.toml (the single source of truth)
#   2. Runs ruff format on the package (to keep CI clean)
#   3. Commits the change
#   4. Creates a git tag
#   5. Pushes main + the tag  →  triggers the PyPI publish workflow
set -euo pipefail

NEW_VERSION="${1:-}"
if [[ -z "$NEW_VERSION" ]]; then
  echo "Usage: $0 <new_version>  (e.g. $0 0.13.4)"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_DIR"

# Detect current version from pyproject.toml
OLD_VERSION=$(python3 -c "import tomllib; data=tomllib.load(open('pyproject.toml','rb')); print(data['tool']['poetry']['version'])")
echo "Bumping $OLD_VERSION → $NEW_VERSION"

# 1. Update pyproject.toml
sed -i "s/^version = \"$OLD_VERSION\"/version = \"$NEW_VERSION\"/" pyproject.toml

# Verify the substitution worked
VERIFY=$(python3 -c "import tomllib; data=tomllib.load(open('pyproject.toml','rb')); print(data['tool']['poetry']['version'])")
if [[ "$VERIFY" != "$NEW_VERSION" ]]; then
  echo "ERROR: pyproject.toml version is '$VERIFY', expected '$NEW_VERSION'. Aborting."
  exit 1
fi

# 2. Format (keeps ruff --check happy in CI)
ruff format django_forms_workflows/ 2>/dev/null && echo "ruff format OK" || true

# 3. Commit
PRE_COMMIT_ALLOW_NO_CONFIG=1 git add pyproject.toml
# Also stage any ruff-formatted files
git diff --name-only django_forms_workflows/ | xargs -r git add
PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m "chore: bump version $OLD_VERSION → $NEW_VERSION"

# 4. Tag
git tag "v$NEW_VERSION"

# 5. Push main + tag  →  triggers publish-to-pypi.yml
PRE_COMMIT_ALLOW_NO_CONFIG=1 git push origin main --tags

echo ""
echo "✅  Version bumped to $NEW_VERSION, tag v$NEW_VERSION pushed."
echo "    PyPI publish workflow will start shortly:"
echo "    https://github.com/opensensor/django-forms-workflows/actions"

