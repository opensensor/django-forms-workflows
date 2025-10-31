# Post-Submission Actions - Configuration Guide

## Overview

Post-Submission Actions allow you to automatically update external systems with form data after submission or approval. This completes the data integration loop:

1. **Prefill** - Pull data from external sources to populate form fields
2. **Submit** - User fills out and submits the form
3. **Approve** - Optional approval workflow
4. **Post-Submit** - **Update external sources with the new data**

## Supported Action Types

### 1. Database Updates
Update external databases with form data after submission or approval.

**Use Cases:**
- Update employee records in HR database
- Sync contact information to CRM
- Update student records in campus database
- Log form submissions to data warehouse

### 2. LDAP Updates
Update LDAP/Active Directory attributes with form data.

**Use Cases:**
- Update user phone numbers in Active Directory
- Sync department changes to LDAP
- Update employee titles and managers
- Maintain directory information

### 3. API Calls
Make HTTP API calls to external services with form data.

**Use Cases:**
- Send data to third-party services
- Trigger webhooks
- Update cloud applications
- Send notifications to external systems

### 4. Custom Handlers
Execute custom Python code for complex integrations.

**Use Cases:**
- Complex business logic
- Multi-step integrations
- Custom data transformations
- Integration with proprietary systems

## Trigger Types

Actions can be triggered at different points in the workflow:

- **on_submit** - Execute immediately when form is submitted
- **on_approve** - Execute when form is approved
- **on_reject** - Execute when form is rejected
- **on_complete** - Execute when workflow is complete (after all approvals)

## Quick Start

### 1. Create a Post-Submission Action

**Admin → Post-Submission Actions → Add Post-Submission Action**

#### Example: Update Contact Database

```
Name: Update Contact Database
Action Type: Database Update
Trigger: On Approval
Description: Update external contact database with new information

Database Configuration:
  - DB Alias: hr_database
  - DB Schema: public
  - DB Table: contacts
  - DB Lookup Field: employee_id
  - DB User Field: employee_id
  - Field Mappings:
    [
      {"form_field": "email", "db_column": "email"},
      {"form_field": "phone", "db_column": "phone"},
      {"form_field": "address", "db_column": "mailing_address"}
    ]

Error Handling:
  - Fail Silently: No (block approval if update fails)
  - Retry on Failure: Yes
  - Max Retries: 3
```

### 2. Configure Database Connection

Add the external database to your Django settings:

```python
# settings.py

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    },
    'hr_database': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'hr_system',
        'USER': 'app_user',
        'PASSWORD': 'password',
        'HOST': 'hr-db.example.com',
        'PORT': '5432',
    },
}
```

### 3. Test the Action

1. Submit a form with the configured action
2. Approve the form (if trigger is on_approve)
3. Check the external database for updates
4. Review logs for execution results

## Configuration Examples

### Example 1: API Call to External Service

```
Name: Send to CRM
Action Type: API Call
Trigger: On Approval

API Configuration:
  - Endpoint: https://api.crm.example.com/contacts
  - Method: POST
  - Headers:
    {
      "Authorization": "Bearer YOUR_API_TOKEN",
      "Content-Type": "application/json"
    }
  - Body Template:
    {
      "contact": {
        "email": "{email}",
        "first_name": "{first_name}",
        "last_name": "{last_name}",
        "phone": "{phone}",
        "source": "employee_form",
        "submitted_by": "{username}"
      }
    }

Error Handling:
  - Fail Silently: Yes
  - Retry on Failure: Yes
  - Max Retries: 3
```

### Example 2: LDAP Attribute Update

```
Name: Update AD Phone Number
Action Type: LDAP Update
Trigger: On Approval

LDAP Configuration:
  - DN Template: CN={username},OU=Users,DC=example,DC=com
  - Field Mappings:
    [
      {"form_field": "phone", "ldap_attribute": "telephoneNumber"},
      {"form_field": "mobile", "ldap_attribute": "mobile"},
      {"form_field": "department", "ldap_attribute": "department"}
    ]

Error Handling:
  - Fail Silently: No
  - Retry on Failure: Yes
  - Max Retries: 2
```

### Example 3: Conditional Database Update

```
Name: Update High-Value Orders
Action Type: Database Update
Trigger: On Approval

Database Configuration:
  - DB Alias: orders_db
  - DB Schema: sales
  - DB Table: orders
  - DB Lookup Field: order_id
  - DB User Field: employee_id
  - Field Mappings:
    [
      {"form_field": "status", "db_column": "order_status"},
      {"form_field": "notes", "db_column": "approval_notes"}
    ]

Conditional Execution:
  - Condition Field: order_amount
  - Condition Operator: Greater Than
  - Condition Value: 10000

Error Handling:
  - Fail Silently: No
  - Retry on Failure: Yes
  - Max Retries: 3
```

### Example 4: Custom Handler

```python
# myapp/handlers.py

def custom_integration_handler(action, submission):
    """
    Custom handler for complex integration logic.
    
    Args:
        action: PostSubmissionAction instance
        submission: FormSubmission instance
        
    Returns:
        dict: {'success': bool, 'message': str, 'data': dict}
    """
    try:
        # Access form data
        form_data = submission.form_data
        user = submission.submitter
        
        # Custom business logic
        result = perform_complex_integration(form_data, user)
        
        return {
            'success': True,
            'message': f'Integration completed: {result}',
            'data': {'result': result}
        }
    except Exception as e:
        return {
            'success': False,
            'message': f'Integration failed: {str(e)}'
        }
```

**Admin Configuration:**
```
Name: Complex Integration
Action Type: Custom Handler
Trigger: On Complete

Custom Handler Configuration:
  - Handler Path: myapp.handlers.custom_integration_handler
  - Handler Config:
    {
      "api_key": "YOUR_API_KEY",
      "endpoint": "https://api.example.com"
    }
```

## Field Mapping

### Database Field Mappings

JSON array of mappings from form fields to database columns:

```json
[
  {"form_field": "email", "db_column": "EMAIL_ADDRESS"},
  {"form_field": "phone", "db_column": "PHONE_NUMBER"},
  {"form_field": "department", "db_column": "DEPT_CODE"}
]
```

### LDAP Field Mappings

JSON array of mappings from form fields to LDAP attributes:

```json
[
  {"form_field": "phone", "ldap_attribute": "telephoneNumber"},
  {"form_field": "title", "ldap_attribute": "title"},
  {"form_field": "manager_email", "ldap_attribute": "manager"}
]
```

## Conditional Execution

Execute actions only when certain conditions are met:

### Available Operators

- **equals** - Field value equals the condition value
- **not_equals** - Field value does not equal the condition value
- **contains** - Field value contains the condition value
- **greater_than** - Field value is greater than the condition value (numeric)
- **less_than** - Field value is less than the condition value (numeric)
- **is_true** - Field value is truthy
- **is_false** - Field value is falsy

### Example: Only Update for High Amounts

```
Condition Field: amount
Condition Operator: Greater Than
Condition Value: 5000
```

This action will only execute if the `amount` field is greater than 5000.

## Error Handling

### Fail Silently

- **Yes** - Errors won't block submission/approval, logged only
- **No** - Errors will prevent submission/approval from completing

### Retry on Failure

- **Yes** - Retry failed actions up to max_retries times
- **No** - Don't retry, fail immediately

### Max Retries

Number of retry attempts (default: 3)

## Execution Order

Multiple actions for the same trigger are executed in order:

1. Sort by `order` field (ascending)
2. Then by `name` (alphabetically)

Set the `order` field to control execution sequence.

## Security Considerations

### Database Updates

- Use read-write database users with minimal permissions
- Validate all field mappings
- Use parameterized queries (automatic)
- SQL injection protection (automatic)

### LDAP Updates

- Use service accounts with limited write permissions
- Validate DN templates
- Test in non-production environment first

### API Calls

- Use HTTPS endpoints only
- Store API keys in environment variables
- Implement rate limiting
- Validate responses

### Custom Handlers

- Review custom code carefully
- Implement proper error handling
- Log all actions
- Test thoroughly

## Monitoring and Logging

All post-submission actions are logged:

```python
import logging

logger = logging.getLogger('django_forms_workflows.handlers')
```

### Log Levels

- **INFO** - Successful execution
- **WARNING** - Retries, skipped actions
- **ERROR** - Failed execution

### Example Log Output

```
INFO: PostSubmissionAction success: Update Contact Database (submission 123): Updated 1 record(s) in public.contacts
WARNING: PostSubmissionAction warning: Send to CRM (submission 124): Retrying (attempt 2/3)
ERROR: PostSubmissionAction error: Update AD Phone (submission 125): LDAP update failed: Connection timeout
```

## Best Practices

1. **Test in Development** - Always test actions in a non-production environment first
2. **Use Fail Silently Wisely** - Only use for non-critical updates
3. **Enable Retries** - Network issues are common, retries help
4. **Monitor Logs** - Regularly review logs for failures
5. **Keep Mappings Simple** - Complex transformations belong in custom handlers
6. **Document Actions** - Use the description field to explain what each action does
7. **Use Conditions** - Avoid unnecessary API calls or updates
8. **Order Matters** - Set execution order for dependent actions

## Troubleshooting

### Action Not Executing

1. Check `is_active` is True
2. Verify trigger type matches workflow event
3. Check conditional execution settings
4. Review logs for errors

### Database Update Failing

1. Verify database connection in settings
2. Check user has write permissions
3. Validate field mappings
4. Ensure lookup field exists in database
5. Check user profile has required field

### LDAP Update Failing

1. Verify LDAP configuration in settings
2. Check service account permissions
3. Validate DN template
4. Ensure LDAP server is accessible

### API Call Failing

1. Check endpoint URL is correct
2. Verify API credentials
3. Check network connectivity
4. Review API response in logs
5. Validate request body format

## Demo

The farm demo includes example post-submission actions:

```bash
python manage.py seed_farm_demo
```

This creates:
- API call action (disabled by default)
- Database update action (disabled by default)

Enable them in Admin → Post-Submission Actions to test.

## Next Steps

- Review the [Prefill Sources Guide](PREFILL_SOURCES.md) for data input
- Check the [Configuration Guide](CONFIGURATION.md) for settings
- Explore the [Quickstart Guide](QUICKSTART.md) for basic setup

