# Release Guide for Django Forms Workflows

This guide provides step-by-step instructions for releasing a new version of django-forms-workflows to PyPI.

## Prerequisites

Before releasing, ensure you have:

1. ✅ All changes committed and pushed to the main branch
2. ✅ All tests passing in CI
3. ✅ Documentation updated
4. ✅ CHANGELOG.md updated with all changes
5. ✅ PyPI API token configured in GitHub Secrets (see `.github/PYPI_SETUP.md`)

## Release Checklist

### 1. Update Version Numbers

Update the version in **all** of these files:

- [ ] `django_forms_workflows/__init__.py`
- [ ] `setup.py`
- [ ] `pyproject.toml`

**Example for version 0.2.0:**

```python
# django_forms_workflows/__init__.py
__version__ = '0.2.0'
```

```python
# setup.py
setup(
    name='django-forms-workflows',
    version='0.2.0',
    ...
)
```

```toml
# pyproject.toml
[tool.poetry]
name = "django-forms-workflows"
version = "0.2.0"
```

### 2. Update CHANGELOG.md

- [ ] Move changes from `[Unreleased]` to a new version section
- [ ] Add release date
- [ ] Update version comparison links at the bottom

**Example:**

```markdown
## [0.2.0] - 2025-11-01

### Added
- Configurable prefill sources with PrefillSource model
- Post-submission actions for updating external systems
- Database, LDAP, and API handlers

### Enhanced
- Comprehensive documentation
- Farm demo with examples

[0.2.0]: https://github.com/opensensor/django-forms-workflows/compare/v0.1.0...v0.2.0
```

### 3. Update Documentation

- [ ] Review and update README.md
- [ ] Ensure all new features are documented
- [ ] Update any version-specific references
- [ ] Check all links work

### 4. Test the Build Locally

```bash
# Clean previous builds
rm -rf dist/ build/ *.egg-info

# Build with poetry
poetry build

# Or build with setuptools
python -m build

# Verify the build
ls -lh dist/
```

You should see:
- `django_forms_workflows-X.Y.Z-py3-none-any.whl`
- `django_forms_workflows-X.Y.Z.tar.gz`

### 5. Test the Package Locally

```bash
# Create a test virtual environment
python -m venv test_env
source test_env/bin/activate  # On Windows: test_env\Scripts\activate

# Install the built package
pip install dist/django_forms_workflows-X.Y.Z-py3-none-any.whl

# Test import
python -c "import django_forms_workflows; print(django_forms_workflows.__version__)"

# Deactivate and clean up
deactivate
rm -rf test_env
```

### 6. Commit Version Changes

```bash
# Add all version changes
git add django_forms_workflows/__init__.py setup.py pyproject.toml CHANGELOG.md

# Commit with a clear message
git commit -m "Bump version to 0.2.0"

# Push to main
git push origin main
```

### 7. Create and Push Git Tag

```bash
# Create an annotated tag
git tag -a v0.2.0 -m "Release version 0.2.0

Major changes:
- Configurable prefill sources
- Post-submission actions
- Enhanced documentation
"

# Verify the tag
git tag -l -n9 v0.2.0

# Push the tag to GitHub
git push origin v0.2.0
```

### 8. Monitor GitHub Actions

1. Go to https://github.com/opensensor/django-forms-workflows/actions
2. Find the "Publish to PyPI" workflow run
3. Monitor the progress
4. Verify all steps complete successfully:
   - ✅ Checkout code
   - ✅ Set up Python
   - ✅ Verify version matches tag
   - ✅ Build distribution packages
   - ✅ Check distribution packages
   - ✅ Publish to PyPI
   - ✅ Create GitHub Release

### 9. Verify PyPI Publication

1. Check PyPI: https://pypi.org/project/django-forms-workflows/
2. Verify the new version is listed
3. Check the package metadata
4. Test installation:

```bash
pip install django-forms-workflows==0.2.0
```

### 10. Verify GitHub Release

1. Go to https://github.com/opensensor/django-forms-workflows/releases
2. Verify the new release is created
3. Check the release notes
4. Verify distribution files are attached

### 11. Announce the Release

- [ ] Update project documentation site (if applicable)
- [ ] Post announcement on social media (if applicable)
- [ ] Notify users via mailing list (if applicable)
- [ ] Update any dependent projects

## Release Types

### Stable Release (Production)

**Tag format:** `v0.2.0`, `v1.0.0`, etc.

**Publishes to:** PyPI + GitHub Release

```bash
git tag -a v0.2.0 -m "Release version 0.2.0"
git push origin v0.2.0
```

### Release Candidate (Testing)

**Tag format:** `v0.2.0-rc1`, `v1.0.0-rc2`, etc.

**Publishes to:** Test PyPI only

```bash
git tag -a v0.2.0-rc1 -m "Release candidate 0.2.0-rc1"
git push origin v0.2.0-rc1
```

### Beta Release

**Tag format:** `v0.2.0-beta1`, `v1.0.0-beta2`, etc.

**Publishes to:** Test PyPI only

```bash
git tag -a v0.2.0-beta1 -m "Beta release 0.2.0-beta1"
git push origin v0.2.0-beta1
```

## Semantic Versioning Guide

Follow [Semantic Versioning](https://semver.org/):

**Format:** MAJOR.MINOR.PATCH

- **MAJOR** (1.0.0) - Incompatible API changes
- **MINOR** (0.2.0) - New features, backward compatible
- **PATCH** (0.2.1) - Bug fixes, backward compatible

**Examples:**

- `0.1.0` → `0.2.0` - Added new features (prefill sources, post-submission actions)
- `0.2.0` → `0.2.1` - Bug fix in database handler
- `0.2.1` → `0.3.0` - Added REST API support
- `0.9.0` → `1.0.0` - First stable release, removed deprecated features

## Rollback Procedure

If you need to rollback a release:

### 1. Delete the Git Tag

```bash
# Delete local tag
git tag -d v0.2.0

# Delete remote tag
git push origin :refs/tags/v0.2.0
```

### 2. Delete the GitHub Release

1. Go to https://github.com/opensensor/django-forms-workflows/releases
2. Find the release
3. Click "Delete"

### 3. Note About PyPI

**Important:** You **cannot** delete or overwrite a version on PyPI once published.

**Options:**
1. **Yank the release** - Mark it as unavailable (users can still install with `==version`)
2. **Publish a patch** - Release a new version (e.g., 0.2.1) with fixes

To yank a release on PyPI:
1. Log in to https://pypi.org
2. Go to the project page
3. Click "Manage" → "Releases"
4. Find the version and click "Options" → "Yank"

## Troubleshooting

### Version Mismatch Error

**Error:** "Tag version does not match package version"

**Solution:**
1. Verify all version files are updated
2. Ensure versions match exactly (no extra spaces, etc.)
3. Delete the tag and recreate after fixing

### Build Fails

**Error:** Build fails during GitHub Actions

**Solution:**
1. Check the error logs in GitHub Actions
2. Test the build locally: `poetry build`
3. Fix any issues and push changes
4. Delete and recreate the tag

### PyPI Upload Fails

**Error:** "Invalid credentials" or "Package already exists"

**Solution:**
1. Verify `PYPI_API_TOKEN` secret is correct
2. Check if version already exists on PyPI
3. Increment version if needed

### Missing Files in Package

**Error:** Files missing from the built package

**Solution:**
1. Check `MANIFEST.in` includes the files
2. Check `pyproject.toml` includes the files
3. Rebuild and verify: `tar -tzf dist/*.tar.gz`

## Post-Release Tasks

After a successful release:

- [ ] Update the `[Unreleased]` section in CHANGELOG.md for future changes
- [ ] Create a new milestone for the next version (if using GitHub milestones)
- [ ] Close the current milestone
- [ ] Update project roadmap
- [ ] Monitor for bug reports
- [ ] Respond to user feedback

## Best Practices

1. **Test Thoroughly** - Always test locally before releasing
2. **Use Release Candidates** - Test with Test PyPI first for major releases
3. **Document Everything** - Keep CHANGELOG.md up to date
4. **Semantic Versioning** - Follow semver strictly
5. **Communicate** - Announce breaking changes clearly
6. **Monitor** - Watch for issues after release
7. **Respond Quickly** - Fix critical bugs with patch releases

## Resources

- [PyPI Help](https://pypi.org/help/)
- [Semantic Versioning](https://semver.org/)
- [Keep a Changelog](https://keepachangelog.com/)
- [GitHub Releases](https://docs.github.com/en/repositories/releasing-projects-on-github)
- [Poetry Documentation](https://python-poetry.org/docs/)

## Quick Reference

### Version Bump Commands

```bash
# Patch release (0.2.0 → 0.2.1)
# Update versions in files, then:
git commit -am "Bump version to 0.2.1"
git tag -a v0.2.1 -m "Release version 0.2.1"
git push origin main v0.2.1

# Minor release (0.2.1 → 0.3.0)
# Update versions in files, then:
git commit -am "Bump version to 0.3.0"
git tag -a v0.3.0 -m "Release version 0.3.0"
git push origin main v0.3.0

# Major release (0.3.0 → 1.0.0)
# Update versions in files, then:
git commit -am "Bump version to 1.0.0"
git tag -a v1.0.0 -m "Release version 1.0.0"
git push origin main v1.0.0
```

### Emergency Hotfix

```bash
# For critical bugs in production
# 1. Create hotfix branch from tag
git checkout -b hotfix/0.2.1 v0.2.0

# 2. Fix the bug and update version
# ... make changes ...
git commit -am "Fix critical bug"

# 3. Update version to 0.2.1
# ... update version files ...
git commit -am "Bump version to 0.2.1"

# 4. Merge to main
git checkout main
git merge hotfix/0.2.1

# 5. Tag and push
git tag -a v0.2.1 -m "Hotfix release 0.2.1"
git push origin main v0.2.1

# 6. Delete hotfix branch
git branch -d hotfix/0.2.1
```

