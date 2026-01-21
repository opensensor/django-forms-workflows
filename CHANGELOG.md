# Changelog

All notable changes to Django Forms Workflows will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

