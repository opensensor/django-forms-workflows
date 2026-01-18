# Release Checklist for v0.2.2

## ✅ Completed Tasks

### 1. Code Quality & Linting
- [x] Migrated from Black to Ruff for formatting and linting
- [x] Added `ruff` as dev dependency via poetry
- [x] Created comprehensive `ruff.toml` configuration
- [x] Fixed all import ordering issues (I001 errors)
- [x] Updated type annotations from `Optional[X]` to `X | None` (UP045)
- [x] Updated type annotations from `typing.Dict` to `dict` (UP035, UP006)
- [x] Fixed LDAP import checks to use `importlib.util.find_spec`
- [x] Removed unused `ldap.modlist` import
- [x] All ruff checks passing: `poetry run ruff check django_forms_workflows/`
- [x] All ruff format checks passing: `poetry run ruff format --check django_forms_workflows/`

### 2. Client Asset Audit
- [x] Removed all "Campus Cafe" references from codebase
- [x] Updated `django_forms_workflows/models.py` - changed example from 'campus_cafe' to 'external_db'
- [x] Updated `django_forms_workflows/migrations/0003_postsubmissionaction.py` - same change
- [x] Updated `docs/PREFILL_SOURCES.md`:
  - Changed "Student First Name from Campus Database" to "Employee First Name from External Database"
  - Changed database alias from 'campus_cafe' to 'hr_database'
  - Changed database name from 'CampusCafe' to 'HRDatabase'
  - Changed table from 'STBIOS' to 'EMPLOYEES'
  - Changed lookup field from 'ID_NUMBER' to 'EMPLOYEE_ID'
- [x] Updated `docs/POST_SUBMISSION_ACTIONS.md` - changed "student records in campus database" to "customer records in external database"
- [x] Verified no "campus" references remain in package: `tar -tzf dist/django_forms_workflows-0.2.2.tar.gz | grep -i "campus"`

### 3. CI/CD Updates
- [x] Updated `.github/workflows/ci.yml` to use Ruff instead of Black/isort/flake8
- [x] Simplified lint job from 3 tools to 2 ruff commands
- [x] Fixed deprecated `actions/upload-artifact@v3` to `v4`
- [x] CI workflow now runs:
  - `ruff format --check django_forms_workflows/`
  - `ruff check django_forms_workflows/`

### 4. Version & Documentation
- [x] Updated version to 0.2.2 in all files:
  - `django_forms_workflows/__init__.py`
  - `setup.py`
  - `pyproject.toml`
- [x] Updated `CHANGELOG.md` with v0.2.2 changes
- [x] Updated version comparison links in CHANGELOG.md
- [x] Author email verified: `matt@opensensor.io`

### 5. Package Build & Verification
- [x] Built package: `poetry build`
- [x] Twine check passed: `poetry run twine check dist/*`
- [x] Verified version in package: 0.2.2
- [x] Verified author in package: Matt Davis <matt@opensensor.io>
- [x] Verified no campus references in package
- [x] Package sizes:
  - Wheel: `django_forms_workflows-0.2.2-py3-none-any.whl`
  - Source: `django_forms_workflows-0.2.2.tar.gz`

## 📋 Ready for Release

### Next Steps to Publish v0.2.2

#### Option 1: Automated Release (Recommended)
1. **Commit all changes:**
   ```bash
   git add -A
   git commit -m "Release v0.2.2: Code quality improvements and client reference cleanup"
   git push origin main
   ```

2. **Create and push tag:**
   ```bash
   git tag -a v0.2.2 -m "Release version 0.2.2"
   git push origin v0.2.2
   ```

3. **GitHub Actions will automatically:**
   - Run all CI checks (tests, linting, build)
   - Build the package
   - Publish to PyPI (requires `PYPI_API_TOKEN` secret to be configured)
   - Create GitHub Release

#### Option 2: Manual Release
1. **Upload to PyPI:**
   ```bash
   poetry run twine upload dist/django_forms_workflows-0.2.2*
   ```
   (Enter your PyPI API token when prompted)

2. **Create GitHub release:**
   - Go to https://github.com/opensensor/django-forms-workflows/releases/new
   - Tag: `v0.2.2`
   - Title: `v0.2.2 - Code Quality Improvements`
   - Copy release notes from CHANGELOG.md

## 🔑 PyPI Token Setup (For Automated Releases)

If you haven't already set up the GitHub secret for automated PyPI publishing:

1. **Create project-scoped token on PyPI:**
   - Go to https://pypi.org/manage/account/token/
   - Click "Add API token"
   - Token name: `django-forms-workflows-github-actions`
   - Scope: "Project: django-forms-workflows" (now available since package exists)
   - Copy the token (starts with `pypi-`)

2. **Add to GitHub Secrets:**
   - Go to https://github.com/opensensor/django-forms-workflows/settings/secrets/actions
   - Click "New repository secret"
   - Name: `PYPI_API_TOKEN`
   - Value: (paste the token)
   - Click "Add secret"

3. **Test automated workflow:**
   - Push a tag: `git push origin v0.2.2`
   - Watch the workflow: https://github.com/opensensor/django-forms-workflows/actions

## 📊 Release Summary

**Version:** 0.2.2  
**Type:** Patch release  
**Focus:** Code quality improvements and cleanup  

**Key Changes:**
- Migrated to Ruff for faster, more comprehensive linting
- Removed all client-specific references
- Improved code quality with modern Python type annotations
- Simplified CI pipeline

**Breaking Changes:** None  
**Migration Required:** No  

## ✨ What's New in v0.2.2

### For Developers
- **Ruff Integration**: Faster linting and formatting (10-100x faster than Black+isort+flake8)
- **Modern Type Hints**: Updated to use PEP 604 union syntax (`X | None` instead of `Optional[X]`)
- **Cleaner Imports**: All imports properly sorted and organized
- **Better LDAP Checks**: More robust availability checking using `importlib.util.find_spec`

### For Users
- **Generic Examples**: All documentation now uses generic, non-client-specific examples
- **No Functional Changes**: This is purely a code quality release

## 🎯 Post-Release Tasks

After successful release:
- [ ] Verify package on PyPI: https://pypi.org/project/django-forms-workflows/0.2.2/
- [ ] Test installation: `pip install django-forms-workflows==0.2.2`
- [ ] Verify GitHub release created
- [ ] Update any external documentation if needed
- [ ] Announce release (if applicable)

## 📝 Notes

- Package v0.2.0 was published with incorrect author email
- Package v0.2.1 corrected the author email
- Package v0.2.2 adds code quality improvements and removes client references
- All three versions are available on PyPI
- Ruff configuration is in `ruff.toml` for consistency across development environments

