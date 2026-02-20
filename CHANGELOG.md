# Changelog

All notable changes to Django Forms Workflows will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.13.0] - 2026-02-20

### Added
- **Nested `FormCategory` hierarchy** — `FormCategory` now has a nullable self-referential `parent` FK (`SET_NULL` on delete), enabling arbitrary category nesting for more granular organisation and access control
- **`FormCategory.get_ancestors()`** — returns the ordered list of ancestor categories from root to direct parent; useful for breadcrumbs and permission checks
- **`FormCategory.full_path()`** — returns a `" > "`-separated string of the full category path (e.g. `"HR > Benefits > Leave Requests"`)
- **Migration `0018_add_form_category_parent`** — adds `parent_id` column using the safe `IF NOT EXISTS` SQL pattern; fully backward-compatible, existing flat categories remain top-level
- **Hierarchical form-list UI** — `_build_grouped_forms()` now produces a category-tree structure; sub-categories are rendered as nested Bootstrap accordions inside their parent section using the new `_category_node.html` recursive partial
- **Admin hierarchy support** — `FormCategoryAdmin` now exposes a **Hierarchy** fieldset with `parent` (via `autocomplete_fields`), `parent` in `list_display`, and `list_filter` by parent category

## [0.9.0] - 2026-02-20

### Added
- **Staged / hybrid approval workflows** — `WorkflowDefinition` now supports an ordered set of `WorkflowStage` rows; each stage has its own `approval_logic` (`all` / `any` / `sequence`) and its own set of `approval_groups`, enabling multi-stage pipelines where each stage can use a different parallel or sequential strategy (e.g. Stage 1: any department head, Stage 2: all directors)
- **`WorkflowStage` model** — new model with fields `name`, `order`, `approval_logic`, `approval_groups` (M2M), `requires_manager_approval`; stages are processed strictly in `order` ascending
- **`ApprovalTask.workflow_stage` / `stage_number`** — new FK and denormalised integer on `ApprovalTask` so tasks carry their stage reference even after a stage is later edited
- **Migration 0015** — `add_workflowstage_staged_approvals`; fully backward-compatible, existing workflows without stages continue to use the legacy flat mode
- **Stage-aware approval engine** — `workflow_engine.py` rewritten with helpers `_create_stage_tasks()` and `_advance_to_next_stage()`; when all tasks for a stage satisfy the stage's `approval_logic` the engine automatically creates tasks for the next stage
- **`WorkflowStageInline` in admin** — stages are editable directly on the `WorkflowDefinition` change page with a `filter_horizontal` widget for `approval_groups`
- **Stage context in `approve_submission` view** — `workflow_mode` (`"staged"` / `"sequence"` / `"all"` / `"any"` / `"none"`), `approval_stages`, `current_stage_number`, and `total_stages` are now passed to `approve.html`
- **Stage-grouped approval history in `submission_detail`** — when a submission has staged tasks the Approval History section renders one colour-coded card per stage showing the stage name, approval logic badge, `X/N approved` counter, and a task table; legacy flat-table display is kept for non-staged workflows
- **Site name in all email templates** — all six email templates now use `{{ site_name }}` (sourced from `FORMS_WORKFLOWS['SITE_NAME']` in settings) instead of the hardcoded string "Django Forms Workflows"
- **Stage context in approval-request emails** — `approval_request.html` shows stage name, stage progress (`Stage N of M`), approval logic, and total parallel approver count when the task belongs to a stage
- **Improved email templates** — `approval_reminder.html` and `escalation_notification.html` reworked with structured `<table>` layouts; all templates render URLs as clickable links

### Fixed
- **`"any"`-mode rejection bug** — in `"any"` approval-logic mode a single rejection no longer immediately rejects the whole submission; the submission is only rejected when every task in scope has been acted on and none approved
- **Rejection handling in views** — duplicate inline rejection code in `approve_submission` replaced with a single call to `workflow_engine.handle_rejection()`

## [0.8.5] - 2026-02-19

### Fixed
- **Presigned file URL expiry** — file URLs in submission detail and approval pages were expiring after 1 hour because presigned S3/DigitalOcean Spaces URLs were being generated at upload time and stored permanently in the `form_data` JSON field in the database.  URLs are no longer persisted; instead, a new `_resolve_form_data_urls()` helper generates fresh presigned URLs on every view render so files are always accessible regardless of how long ago they were uploaded.

### Changed
- `serialize_form_data()` no longer stores a `url` key in file-upload entries — only `filename`, `path`, `size`, and `content_type` are persisted.  This is a **data-format change**: existing database records that contain a stale `url` key are handled correctly because the views now always regenerate the URL from the stored `path`.

## [0.8.4] - 2026-02-19

### Added
- **Configurable site name** — deployers can set `FORMS_WORKFLOWS = {'SITE_NAME': 'My Org Workflows'}` in Django settings to replace the default "Django Forms Workflows" brand across all page titles, the navbar brand, and the footer copyright line
- **Context processor** — `django_forms_workflows.context_processors.forms_workflows` injects `site_name` into every template context; add it to `TEMPLATES['OPTIONS']['context_processors']` in your settings to enable custom branding
- **Rich approval inbox template** — the generic `approval_inbox.html` is now feature-complete: category filter bar with counts and icons, form-level drill-down bar (indented, only visible when a category is active), dynamic page header showing task count and `Category › Form` breadcrumb, a Category column in the table (hidden when filtering by category), and context-aware empty-state messages

## [0.8.3] - 2026-02-19

### Added
- **Form name search on the landing page** — `form_list` view accepts `?q=<text>` to filter the visible forms by name (case-insensitive); a search box with a clear button is rendered in the page header alongside the heading; result count is shown when a query is active
- **Form-level drill-down on submissions page** — when a category filter is active on `my_submissions`, a second pill bar appears (indented under the category bar) listing every form the user has submissions for within that category; selecting a pill appends `&form=<slug>` to the URL and narrows the table to that form; the page header shows `Category › Form` breadcrumb text and a targeted clear link
- **Form-level drill-down on approval inbox** — same drill-down behaviour as submissions: after selecting a category, a form pill bar appears so approvers can focus on a single form's queue; context variables `form_counts`, `form_slug`, and `active_form` are passed to the template

## [0.8.2] - 2026-02-19

### Added
- **Category-aware submissions page** — `my_submissions` view now accepts `?category=<slug>` query parameter to filter the submission table to a single form category; template context includes `category_counts`, `active_category`, `category_slug`, and `total_submissions_count` for rendering a filter-pill bar with per-category submission counts
- **Category column in submissions table** — the submissions table now shows the form category (icon + name) for each row; the column is hidden when a category filter is active since it would be redundant

## [0.8.1] - 2026-02-19

### Fixed
- **`form_categories.html`** — replaced multiline `{# ... #}` comment (Django only supports single-line `{#}` comments) with `{% comment %}...{% endcomment %}` tags to prevent the comment block from rendering as raw text on the page

## [0.8.0] - 2026-02-19

### Added
- **FormCategory model** — new `FormCategory` grouping primitive with `name`, `slug`, `description`, `order`, `icon`, `is_collapsed_by_default`, and `allowed_groups` (M2M) fields; migration `0014_add_form_category`
- **Category-grouped form list** — `form_list` view now passes `grouped_forms` (ordered list of `(FormCategory | None, [FormDefinition, ...])` tuples) and enforces category-level `allowed_groups` access control for non-staff users; new `form_categories.html` template
- **Category-aware approval inbox** — `approval_inbox` view accepts `?category=<slug>` query parameter to filter the task table to a single category; template context now includes `category_counts`, `active_category`, `category_slug`, and `total_tasks_count` for rendering a filter-pill bar with per-category pending counts
- **`forms_workflows_tags` templatetag additions** — new tags supporting the grouped form list and category header rendering

### Planned Features
- Form builder UI (drag-and-drop)
- REST API for form submission
- Webhook support
- Custom field types (signature, location, etc.)
- Advanced reporting and analytics
- Multi-tenancy support

## [0.5.5] - 2026-01-18

### Added
- **Multi-Column Database Prefill Templates**
  - Added `db_columns` (JSONField) and `db_template` (CharField) to PrefillSource model
  - Allows combining multiple database columns into a single prefill value
  - Example: `db_columns=["FIRST_NAME", "LAST_NAME"]`, `db_template="{FIRST_NAME} {LAST_NAME}"` produces "John Smith"
  - New `DatabaseDataSource.get_template_value()` method for template-based lookups
  - Migration `0010_add_prefillsource_template_fields`

## [0.5.4] - 2026-01-18

### Fixed
- **Database Prefill User Field Lookup**
  - Fixed `DatabaseDataSource._get_user_id()` to first check direct user attributes (e.g., `username`, `email`) before checking the user profile
  - This allows database prefill to use `user.username` for lookup when `db_user_field` is set to `username`

## [0.5.3] - 2026-01-18

### Added
- **Readonly Form Fields**
  - Added `readonly` boolean field to FormField model
  - Readonly fields are rendered with disabled styling and cannot be modified by users
  - Migration `0009_add_formfield_readonly` adds the new field

## [0.4.1] - 2025-11-11

### Added
- **Configurable LDAP TLS Certificate Verification**
  - Added `configure_ldap_connection()` helper function in `ldap_backend.py`
  - Support for `LDAP_TLS_REQUIRE_CERT` environment variable with options: `never`, `allow`, `try`, `demand` (default)
  - Updated all LDAP connection initialization points to use configurable TLS settings
  - Added `_configure_ldap_connection()` helper in `ldap_handler.py` with fallback implementation

### Changed
- **LDAP Backend Improvements**
  - All LDAP connections now respect the `LDAP_TLS_REQUIRE_CERT` environment variable
  - Updated `get_user_manager()`, `search_ldap_users()`, and `get_ldap_user_attributes()` functions
  - Updated `LDAPUpdateHandler` to use configurable TLS settings

### Documentation
- Added `LDAP_TLS_CONFIGURATION.md` with comprehensive documentation on TLS configuration options
- Documented security considerations for different TLS verification levels
- Added deployment instructions for Kubernetes environments

## [0.4.0] - 2025-11-06

### Added - Enterprise Integration Features
- **Enhanced UserProfile Model**
  - Added `ldap_last_sync` timestamp field for tracking LDAP synchronization
  - Added database indexes to `employee_id` and `external_id` fields for better performance
  - Added `id_number` property as backward-compatible alias for `employee_id`
  - Added `full_name` and `display_name` properties for convenient user display
  - Enhanced help text for LDAP attribute fields

- **LDAP Integration Enhancements**
  - New `signals.py` module with automatic LDAP attribute synchronization
  - `sync_ldap_attributes()` function for syncing LDAP data to UserProfile
  - `get_ldap_attribute()` helper function for retrieving LDAP attributes
  - Auto-sync on user login (configurable via `FORMS_WORKFLOWS['LDAP_SYNC']`)
  - Signal handlers for automatic UserProfile creation on user creation
  - Configurable LDAP attribute mappings in settings

- **Database Introspection Utilities**
  - `DatabaseDataSource.test_connection()` - Test external database connections
  - `DatabaseDataSource.get_available_tables()` - List tables in a schema
  - `DatabaseDataSource.get_table_columns()` - Get column information for a table
  - Support for SQL Server, PostgreSQL, MySQL, and SQLite introspection

- **Utility Functions**
  - `get_user_manager()` - Get user's manager from LDAP or UserProfile
  - `user_can_view_form()` - Check if user can view a form
  - `user_can_view_submission()` - Check if user can view a submission
  - `check_escalation_needed()` - Check if submission needs escalation
  - `sync_ldap_groups()` - Synchronize LDAP groups to Django groups

- **Management Commands**
  - `sync_ldap_profiles` - Bulk sync LDAP attributes for all users
    - Supports `--username` for single user sync
    - Supports `--dry-run` for testing without changes
    - Supports `--verbose` for detailed output
  - `test_db_connection` - Test external database connections
    - Supports `--database` to specify database alias
    - Supports `--verbose` for detailed connection information
    - Works with SQL Server, PostgreSQL, MySQL, and SQLite

### Changed
- Updated version to 0.4.0 to reflect significant new features
- Enhanced UserProfile model with LDAP-specific fields and properties
- Improved database source with introspection capabilities
- Expanded utility functions for better LDAP and permission handling

### Migration Notes
- Run `python manage.py migrate django_forms_workflows` to apply UserProfile enhancements
- Configure LDAP sync in settings:
  ```python
  FORMS_WORKFLOWS = {
      'LDAP_SYNC': {
          'enabled': True,
          'sync_on_login': True,
          'attributes': {
              'employee_id': 'extensionAttribute1',
              'department': 'department',
              'title': 'title',
              'phone': 'telephoneNumber',
              'manager_dn': 'manager',
          }
      }
  }
  ```
- Use `python manage.py sync_ldap_profiles` to bulk sync existing users

## [0.2.2] - 2025-10-31

### Changed
- **Code Quality Improvements**
  - Migrated from Black to Ruff for code formatting and linting
  - Fixed all import ordering and type annotation issues
  - Added comprehensive ruff.toml configuration
  - Updated CI workflow to use Ruff instead of Black/isort/flake8
  - Improved LDAP availability checks using importlib.util.find_spec

### Fixed
- Removed all references to "Campus Cafe" from codebase and documentation
- Updated example database references to use generic "hr_database" naming
- Cleaned up unused imports in LDAP handlers

## [0.2.1] - 2025-10-31

### Fixed
- Corrected author email in package metadata from `opensource@opensensor.ai` to `matt@opensensor.io`

## [0.2.0] - 2025-10-31

### Added - Configurable Prefill Sources
- **PrefillSource Model** - Database-driven prefill source configuration
  - Support for User, LDAP, Database, API, System, and Custom source types
  - Flexible database field mapping with configurable lookup fields
  - Custom user field mapping (employee_id, email, external_id, etc.)
  - Active/inactive toggle and display ordering
  - Backward compatible with legacy text-based prefill_source field
- **Enhanced Database Prefill** - Generic database lookups with custom field mappings
  - Configurable DB lookup field (ID_NUMBER, EMAIL, EMPLOYEE_ID, etc.)
  - Configurable user profile field for matching
  - Makes library truly generic and adaptable to different deployments
- **Admin Interface** - Comprehensive admin for managing prefill sources
  - Dropdown selection of prefill sources in FormField admin
  - Inline editing and filtering
  - Helpful descriptions and examples
- **Demo Integration** - Farm-themed demo showcasing prefill functionality
  - "Farmer Contact Update" form with multiple prefill sources
  - Seed command for creating demo prefill sources
  - Examples of User, System, and Database prefill types

### Added - Post-Submission Actions
- **PostSubmissionAction Model** - Configurable actions to update external systems
  - Support for Database, LDAP, API, and Custom handler action types
  - Four trigger types: on_submit, on_approve, on_reject, on_complete
  - Flexible field mapping for all action types
  - Conditional execution based on form field values
  - Robust error handling with retries and fail-silently options
  - Execution ordering for dependent actions
- **Database Update Handler** - Update external databases after form submission/approval
  - Custom field mappings from form fields to database columns
  - Configurable lookup fields and user fields
  - SQL injection protection with parameterized queries
  - Identifier validation for table and column names
- **LDAP Update Handler** - Update Active Directory attributes
  - DN template support with placeholders
  - Field mapping from form fields to LDAP attributes
  - Service account integration
- **API Call Handler** - Make HTTP API calls to external services
  - Support for GET, POST, PUT, PATCH methods
  - Template-based request bodies with field placeholders
  - Custom headers support
  - Response validation
- **Custom Handler Support** - Execute custom Python code for complex integrations
  - Dynamic handler loading via import_module
  - Configurable handler parameters
  - Standardized return format
- **Action Executor** - Coordinates execution of multiple actions
  - Filters actions by trigger type
  - Implements retry logic with configurable max attempts
  - Comprehensive error handling and logging
  - Conditional execution based on form field values
- **Workflow Integration** - Integrated with all workflow trigger points
  - on_submit trigger in create_workflow_tasks()
  - on_approve trigger in execute_post_approval_updates()
  - on_reject trigger in approve_submission view
  - on_complete trigger in _finalize_submission()
- **Admin Interface** - Comprehensive admin for managing post-submission actions
  - Collapsible fieldsets for each action type
  - List view with filtering and inline editing
  - Helpful descriptions and examples
- **Demo Integration** - Farm demo showcasing post-submission actions
  - API call action logging to httpbin.org
  - Database update action example
  - Both disabled by default for safety

### Enhanced
- **Documentation** - Comprehensive guides for new features
  - `docs/PREFILL_SOURCES.md` - Complete prefill configuration guide
  - `docs/POST_SUBMISSION_ACTIONS.md` - Complete post-submission actions guide
  - `PREFILL_ENHANCEMENTS.md` - Technical summary of prefill enhancements
  - `POST_SUBMISSION_ENHANCEMENTS.md` - Technical summary of post-submission enhancements
  - Updated README.md with new features
- **Farm Demo** - Enhanced example application
  - Showcases both prefill and post-submission actions
  - Multiple demo forms with different workflow types
  - Seed commands for easy setup
  - Farm-themed design for better UX

### Security
- **SQL Injection Protection** - Enhanced database security
  - Parameterized queries for all database operations
  - Identifier validation for table and column names
  - Whitelist-based validation
- **LDAP Security** - Secure LDAP integration
  - DN template validation
  - Service account permissions
  - Connection encryption support
- **API Security** - Secure external API calls
  - HTTPS enforcement
  - API key management
  - Request timeout protection
  - Response validation

### Migration Notes
- Run `python manage.py migrate` to apply new migrations
- Existing forms with text-based `prefill_source` continue to work
- New `prefill_source_config` field takes precedence when set
- Post-submission actions are opt-in and disabled by default
- No breaking changes to existing deployments

## [0.1.0] - 2025-10-31

### Added
- Initial release
- Database-driven form definitions
- 15+ field types (text, select, date, file upload, etc.)
- Dynamic form rendering with Crispy Forms
- Approval workflows with flexible routing
- LDAP/Active Directory integration
- External database prefill support
- Pluggable data source architecture
- Complete audit trail
- Email notifications
- File upload support
- Conditional field visibility
- Form versioning
- Draft save functionality
- Withdrawal support
- Group-based permissions
- Manager approval from LDAP hierarchy
- Conditional escalation
- Post-approval database updates
- Comprehensive documentation
- Example project

### Security
- CSRF protection
- SQL injection prevention
- File upload validation
- Parameterized database queries
- Identifier validation for SQL

### Dependencies
- Django >= 5.1
- django-crispy-forms >= 2.0
- crispy-bootstrap5 >= 2.0
- celery >= 5.3
- python-decouple >= 3.8

### Optional Dependencies
- django-auth-ldap >= 4.6 (for LDAP integration)
- python-ldap >= 3.4 (for LDAP integration)
- mssql-django >= 1.6 (for MS SQL Server)
- pyodbc >= 5.0 (for MS SQL Server)
- psycopg2-binary >= 2.9 (for PostgreSQL)
- mysqlclient >= 2.2 (for MySQL)

[Unreleased]: https://github.com/opensensor/django-forms-workflows/compare/v0.2.2...HEAD
[0.2.2]: https://github.com/opensensor/django-forms-workflows/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/opensensor/django-forms-workflows/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/opensensor/django-forms-workflows/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/opensensor/django-forms-workflows/releases/tag/v0.1.0

