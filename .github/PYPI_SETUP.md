# PyPI Publishing Setup Guide

This guide explains how to set up automated publishing to PyPI when you push a version tag.

## Prerequisites

1. **PyPI Account** - Create an account at https://pypi.org
2. **Test PyPI Account** (optional but recommended) - Create an account at https://test.pypi.org
3. **GitHub Repository Access** - Admin access to configure secrets

## Step 1: Generate PyPI API Tokens

### For Production PyPI

1. Log in to https://pypi.org
2. Go to Account Settings → API tokens
3. Click "Add API token"
4. Set the token name: `django-forms-workflows-github-actions`
5. Set the scope: 
   - **Option A (Recommended):** Scope to project `django-forms-workflows` (after first manual upload)
   - **Option B:** Scope to entire account (less secure)
6. Click "Add token"
7. **IMPORTANT:** Copy the token immediately (starts with `pypi-`)
8. Store it securely - you won't be able to see it again

### For Test PyPI (Optional)

1. Log in to https://test.pypi.org
2. Follow the same steps as above
3. Token name: `django-forms-workflows-github-actions-test`
4. Copy and store the token

## Step 2: Add Secrets to GitHub Repository

1. Go to your GitHub repository
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add the following secrets:

### Required Secret

**Name:** `PYPI_API_TOKEN`  
**Value:** The PyPI API token you generated (starts with `pypi-`)

### Optional Secret (for testing)

**Name:** `TEST_PYPI_API_TOKEN`  
**Value:** The Test PyPI API token you generated

## Step 3: First Manual Upload (Recommended)

For the first release, it's recommended to manually upload to PyPI to register the project:

```bash
# Install build tools
pip install build twine

# Build the package
python -m build

# Upload to Test PyPI (optional - for testing)
twine upload --repository testpypi dist/*

# Upload to PyPI
twine upload dist/*
```

You'll be prompted for your PyPI username and password/token:
- Username: `__token__`
- Password: Your API token (including the `pypi-` prefix)

## Step 4: Publishing a New Version

Once the GitHub Actions workflow is set up, publishing is automatic:

### 1. Update Version Numbers

Update the version in these files:
- `django_forms_workflows/__init__.py`
- `setup.py`
- `pyproject.toml`
- `CHANGELOG.md`

Example for version 0.2.0:

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

Document all changes in `CHANGELOG.md`:

```markdown
## [0.2.0] - 2025-11-01

### Added
- New feature X
- New feature Y

### Changed
- Updated feature Z

### Fixed
- Bug fix A
```

### 3. Commit and Push Changes

```bash
git add .
git commit -m "Bump version to 0.2.0"
git push origin main
```

### 4. Create and Push a Tag

```bash
# Create an annotated tag
git tag -a v0.2.0 -m "Release version 0.2.0"

# Push the tag to GitHub
git push origin v0.2.0
```

### 5. Automated Publishing

The GitHub Actions workflow will automatically:
1. ✅ Verify the tag version matches the package version
2. ✅ Build the distribution packages (wheel and source)
3. ✅ Check the packages with twine
4. ✅ Publish to PyPI (for stable releases)
5. ✅ Create a GitHub Release with the distribution files

## Release Types

### Stable Release

Tag format: `v0.2.0`, `v1.0.0`, etc.

```bash
git tag -a v0.2.0 -m "Release version 0.2.0"
git push origin v0.2.0
```

This will publish to **PyPI** and create a **GitHub Release**.

### Release Candidate (Test)

Tag format: `v0.2.0-rc1`, `v1.0.0-rc2`, etc.

```bash
git tag -a v0.2.0-rc1 -m "Release candidate 0.2.0-rc1"
git push origin v0.2.0-rc1
```

This will publish to **Test PyPI** only (if configured).

## Monitoring the Workflow

1. Go to your GitHub repository
2. Click on the **Actions** tab
3. Find the "Publish to PyPI" workflow run
4. Monitor the progress and check for any errors

## Troubleshooting

### Error: Version mismatch

**Problem:** Tag version doesn't match package version

**Solution:** Ensure all version numbers are updated:
- `django_forms_workflows/__init__.py`
- `setup.py`
- `pyproject.toml`

### Error: Package already exists

**Problem:** Version already published to PyPI

**Solution:** 
- You cannot overwrite a published version
- Increment the version number and create a new tag
- Consider using patch versions (e.g., 0.2.1)

### Error: Invalid credentials

**Problem:** PyPI API token is incorrect or expired

**Solution:**
1. Generate a new API token on PyPI
2. Update the `PYPI_API_TOKEN` secret in GitHub
3. Re-run the workflow

### Error: Package name already taken

**Problem:** Another package with the same name exists

**Solution:**
- Choose a different package name
- Update `name` in `setup.py` and `pyproject.toml`
- Update all references in documentation

## Best Practices

1. **Test First** - Always test with Test PyPI before publishing to production
2. **Semantic Versioning** - Follow semver (MAJOR.MINOR.PATCH)
3. **Changelog** - Always update CHANGELOG.md before releasing
4. **Git Tags** - Use annotated tags with descriptive messages
5. **Version Consistency** - Ensure all version numbers match
6. **Review Changes** - Review the diff before tagging
7. **CI Passing** - Ensure all CI checks pass before releasing

## Version Numbering Guide

Follow [Semantic Versioning](https://semver.org/):

- **MAJOR** (1.0.0) - Breaking changes
- **MINOR** (0.2.0) - New features, backward compatible
- **PATCH** (0.2.1) - Bug fixes, backward compatible

Examples:
- `0.1.0` - Initial release
- `0.2.0` - Added prefill sources and post-submission actions
- `0.2.1` - Bug fix for database handler
- `1.0.0` - First stable release with breaking changes

## Security Notes

1. **Never commit API tokens** to the repository
2. **Use scoped tokens** - Limit token scope to the specific project
3. **Rotate tokens** - Regenerate tokens periodically
4. **Monitor usage** - Check PyPI for unexpected uploads
5. **Enable 2FA** - Enable two-factor authentication on PyPI

## Additional Resources

- [PyPI Help](https://pypi.org/help/)
- [Twine Documentation](https://twine.readthedocs.io/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Semantic Versioning](https://semver.org/)
- [Keep a Changelog](https://keepachangelog.com/)

## Support

If you encounter issues:
1. Check the GitHub Actions logs
2. Review the PyPI upload history
3. Consult the PyPI help documentation
4. Open an issue in the repository

