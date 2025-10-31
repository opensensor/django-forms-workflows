# Prefill Sources - Configuration Guide

## Overview

The Prefill Sources feature allows you to configure reusable data sources that automatically populate form fields with data from various sources including:

- **User Model** - Current user's profile data
- **LDAP/Active Directory** - Enterprise directory attributes
- **External Databases** - Custom database queries with flexible field mappings
- **APIs** - External API calls
- **System Values** - Current date/time, previous submissions

This makes the library flexible for different deployment scenarios while providing a user-friendly dropdown interface for form builders.

## Key Benefits

1. **Reusable Configuration** - Define a prefill source once, use it across multiple forms
2. **Flexible Field Mapping** - Customize database lookup fields for different environments
3. **User-Friendly** - Form builders select from a dropdown instead of typing complex syntax
4. **Centralized Management** - All prefill sources managed in Django Admin
5. **Backward Compatible** - Legacy text-based prefill sources still work

## Quick Start

### 1. Seed Default Prefill Sources

Run the management command to create standard prefill sources:

```bash
python manage.py seed_prefill_sources
```

This creates sources for:
- Current User fields (email, first name, last name, username)
- LDAP attributes (department, title, manager, phone, employee ID)
- System values (current date, current datetime, last submission)

### 2. Create Custom Database Prefill Sources

For database lookups, create custom prefill sources via Django Admin:

**Admin → Prefill Sources → Add Prefill Source**

#### Example: Employee First Name from External Database

```
Name: Employee - First Name
Source Type: Database
Source Key: {{ dbo.EMPLOYEES.FIRST_NAME }}
Description: Employee's first name from external HR database

Database Configuration:
  - DB Alias: hr_database
  - DB Schema: dbo
  - DB Table: EMPLOYEES
  - DB Column: FIRST_NAME
  - DB Lookup Field: EMPLOYEE_ID
  - DB User Field: employee_id
```

#### Example: Employee Department from HR System

```
Name: Employee - Department
Source Type: Database
Source Key: {{ hr.employees.department }}
Description: Employee department from HR database

Database Configuration:
  - DB Alias: hr_database
  - DB Schema: hr
  - DB Table: employees
  - DB Column: department
  - DB Lookup Field: email
  - DB User Field: email
```

### 3. Use Prefill Sources in Forms

When creating or editing form fields in Django Admin:

1. Go to **Form Definitions** → Select a form → Edit
2. In the form field inline, expand **"Choices & Defaults"**
3. Select a prefill source from the **"Prefill source config"** dropdown
4. Save the form

The field will now automatically populate with data from the selected source when users open the form.

## Database Prefill Configuration

### Understanding Field Mappings

When configuring database prefill sources, you need to specify how to match the current user to a database record:

- **DB Lookup Field** - The column in the external database to match against (e.g., `ID_NUMBER`, `EMAIL`, `EMPLOYEE_ID`)
- **DB User Field** - The UserProfile field containing the value to match (e.g., `employee_id`, `email`, `external_id`)

### Example Scenarios

#### Scenario 1: Lookup by Employee ID

Your external database has an `ID_NUMBER` column, and your UserProfile has an `employee_id` field:

```
DB Lookup Field: ID_NUMBER
DB User Field: employee_id
```

Generated SQL:
```sql
SELECT [FIRST_NAME] 
FROM [dbo].[STBIOS] 
WHERE [ID_NUMBER] = %s  -- User's employee_id
```

#### Scenario 2: Lookup by Email

Your external database has an `EMAIL` column, and you want to match by the user's email:

```
DB Lookup Field: EMAIL
DB User Field: email
```

Generated SQL:
```sql
SELECT [department] 
FROM [hr].[employees] 
WHERE [EMAIL] = %s  -- User's email
```

#### Scenario 3: Custom External ID

Your external database has a `EXTERNAL_USER_ID` column, and your UserProfile has an `external_id` field:

```
DB Lookup Field: EXTERNAL_USER_ID
DB User Field: external_id
```

## Settings Configuration

Configure database connections in your Django settings:

```python
# settings.py

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    },
    'hr_database': {
        'ENGINE': 'mssql',
        'NAME': 'HRDatabase',
        'USER': 'readonly_user',
        'PASSWORD': 'password',
        'HOST': 'sql.example.com',
        'PORT': '1433',
        'OPTIONS': {
            'driver': 'ODBC Driver 17 for SQL Server',
        },
    },
}

# Optional: Configure default database source settings
FORMS_WORKFLOWS = {
    'DATABASE_SOURCE': {
        'database_alias': 'hr_database',
        'default_schema': 'dbo',
        'user_id_field': 'employee_id',
        'lookup_field': 'EMPLOYEE_ID',
    }
}
```

## Admin Interface

### Managing Prefill Sources

**Admin → Prefill Sources**

- **List View** - See all prefill sources, filter by type, toggle active status
- **Edit View** - Configure source details and type-specific settings
- **Order** - Control the display order in dropdowns

### Creating Forms with Prefill

**Admin → Form Definitions → [Select Form] → Form Fields**

Each form field has a **"Prefill source config"** dropdown showing all active prefill sources grouped by type.

## Migration from Legacy Prefill

If you have existing forms using the legacy text-based `prefill_source` field:

1. The old field still works (backward compatible)
2. Create matching PrefillSource records
3. Update form fields to use `prefill_source_config`
4. The new field takes precedence over the legacy field

## Example: Farm Demo

The included farm demo showcases prefill functionality:

```bash
python manage.py seed_farm_demo
```

This creates a "Farmer Contact Update" form with fields pre-filled from:
- User's first name
- User's last name
- User's email
- Current date

Try it out:
1. Login as any demo user (password: `farm123`)
2. Navigate to "Farmer Contact Update" form
3. See fields automatically populated with your user data

## API Reference

### PrefillSource Model Fields

- `name` - Display name shown in dropdown
- `source_type` - Type of source (user, ldap, database, api, system, custom)
- `source_key` - Source identifier string
- `description` - Help text for form builders
- `is_active` - Whether source appears in dropdowns
- `order` - Display order in dropdowns

#### Database-specific fields:
- `db_alias` - Django database alias
- `db_schema` - Database schema name
- `db_table` - Table name
- `db_column` - Column to retrieve
- `db_lookup_field` - Column to match against
- `db_user_field` - UserProfile field for matching

#### LDAP-specific fields:
- `ldap_attribute` - LDAP attribute name

#### API-specific fields:
- `api_endpoint` - API URL
- `api_field` - Field to extract from response

### FormField Methods

- `get_prefill_source_key()` - Returns the prefill source identifier, prioritizing `prefill_source_config` over legacy `prefill_source`

## Troubleshooting

### Prefill not working?

1. **Check UserProfile** - Ensure the user has the required field populated (e.g., `employee_id`)
2. **Check Database Connection** - Verify the database alias is configured in `DATABASES`
3. **Check Permissions** - Ensure the database user has SELECT permissions
4. **Check Logs** - Look for error messages in Django logs
5. **Test Query** - Try the SQL query manually with a known user ID

### Common Issues

**"No data found for user"**
- The user's profile field is empty or doesn't match any database records
- Check the `db_user_field` and `db_lookup_field` configuration

**"Database data source is not available"**
- The database alias is not configured in `DATABASES`
- Add the database configuration to settings.py

**"Invalid identifier"**
- SQL injection protection rejected the field name
- Ensure field names contain only letters, numbers, and underscores

## Best Practices

1. **Use Descriptive Names** - Make prefill source names clear for form builders
2. **Group by Type** - Use consistent naming (e.g., "Student - First Name", "Student - Last Name")
3. **Document Custom Sources** - Add descriptions explaining what each source does
4. **Test Before Deploying** - Verify prefill sources work with test users
5. **Secure Database Access** - Use read-only database users for external databases
6. **Monitor Performance** - Database prefills add queries; consider caching for high-traffic forms

## Next Steps

- Explore the [Configuration Guide](CONFIGURATION.md) for more settings
- Read the [Quickstart Guide](QUICKSTART.md) to create your first form
- Check out the [Value Proposition](VALUE_PROPOSITION.md) to learn more about the library

