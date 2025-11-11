# LDAP TLS Certificate Configuration

## Overview

This document describes the changes made to support configurable LDAP TLS certificate verification via the `LDAP_TLS_REQUIRE_CERT` environment variable.

## Problem

The application was hardcoded to use `ldap.OPT_X_TLS_NEVER` for TLS certificate verification, which meant it would never verify SSL/TLS certificates when connecting to LDAP servers. This was not configurable and could cause issues in different environments.

## Solution

Made the LDAP TLS certificate verification configurable via the `LDAP_TLS_REQUIRE_CERT` environment variable, allowing different verification levels based on deployment needs.

## Environment Variable

### `LDAP_TLS_REQUIRE_CERT`

Controls how strictly the LDAP client verifies SSL/TLS certificates.

**Possible Values:**
- `never` - Don't require or verify certificates (use for self-signed certs or testing)
- `allow` - Allow connection without certificate verification
- `try` - Try to verify but proceed if verification fails
- `demand` (default) - Require valid certificate (most secure)
- `hard` - Same as `demand`

**Example:**
```bash
export LDAP_TLS_REQUIRE_CERT=never
```

Or in Kubernetes:
```bash
kubectl set env deployment/form-workflows-app -n default LDAP_TLS_REQUIRE_CERT=never
```

## Files Modified

### 1. `django_forms_workflows/ldap_backend.py`

**Changes:**
- Added `configure_ldap_connection(conn)` helper function that reads `LDAP_TLS_REQUIRE_CERT` environment variable and configures the LDAP connection accordingly
- Updated three LDAP connection initialization points to use the helper:
  - `get_user_manager()` function (line 281)
  - `search_ldap_users()` function (line 359)
  - `get_ldap_user_attributes()` function (line 443)

**Key Function:**
```python
def configure_ldap_connection(conn):
    """
    Configure LDAP connection with TLS settings from environment variables.
    
    Environment Variables:
        LDAP_TLS_REQUIRE_CERT: TLS certificate verification level
            - 'never': Don't require or verify certificates
            - 'allow': Allow connection without cert verification
            - 'try': Try to verify but proceed if verification fails
            - 'demand' or 'hard': Require valid certificate (default)
    """
    tls_require_cert = os.getenv('LDAP_TLS_REQUIRE_CERT', 'demand').lower()
    
    if tls_require_cert == 'never':
        conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
    elif tls_require_cert == 'allow':
        conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_ALLOW)
    elif tls_require_cert == 'try':
        conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_TRY)
    else:  # 'demand' or 'hard' or any other value
        conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_DEMAND)
    
    conn.set_option(ldap.OPT_REFERRALS, 0)
```

### 2. `django_forms_workflows/handlers/ldap_handler.py`

**Changes:**
- Added `_configure_ldap_connection(conn)` helper function that imports and uses the main `configure_ldap_connection` function from `ldap_backend`
- Includes fallback implementation if `ldap_backend` is not available
- Updated LDAP connection initialization in `_update_ldap_entry()` method (line 217)

### 3. `form-workflows/config/settings.py`

**Changes:**
- Modified the LDAP configuration section to read `LDAP_TLS_REQUIRE_CERT` from environment using `config()` function
- Dynamically sets `tls_cert_option` based on the environment variable value
- Updated `AUTH_LDAP_CONNECTION_OPTIONS` to use the dynamic `tls_cert_option` instead of hardcoded `ldap.OPT_X_TLS_NEVER`

**Before:**
```python
AUTH_LDAP_CONNECTION_OPTIONS = {
    ldap.OPT_DEBUG_LEVEL: 0,
    ldap.OPT_REFERRALS: 0,
    ldap.OPT_X_TLS_REQUIRE_CERT: ldap.OPT_X_TLS_NEVER,  # Hardcoded
    ldap.OPT_NETWORK_TIMEOUT: 5,
    ldap.OPT_TIMEOUT: 5,
}
```

**After:**
```python
# Configure TLS certificate verification based on environment variable
tls_require_cert = config('LDAP_TLS_REQUIRE_CERT', default='demand').lower()

if tls_require_cert == 'never':
    tls_cert_option = ldap.OPT_X_TLS_NEVER
elif tls_require_cert == 'allow':
    tls_cert_option = ldap.OPT_X_TLS_ALLOW
elif tls_require_cert == 'try':
    tls_cert_option = ldap.OPT_X_TLS_TRY
else:  # 'demand' or 'hard' or any other value
    tls_cert_option = ldap.OPT_X_TLS_DEMAND

AUTH_LDAP_CONNECTION_OPTIONS = {
    ldap.OPT_DEBUG_LEVEL: 0,
    ldap.OPT_REFERRALS: 0,
    ldap.OPT_X_TLS_REQUIRE_CERT: tls_cert_option,  # Configurable
    ldap.OPT_NETWORK_TIMEOUT: 5,
    ldap.OPT_TIMEOUT: 5,
}
```

### 4. `form-workflows/test_ldap_connection.py`

**Changes:**
- Updated the test script to read `LDAP_TLS_REQUIRE_CERT` from environment
- Applies the same TLS configuration logic as the main application
- Displays the TLS verification level being used during testing

## Usage

### For Development/Testing (Self-Signed Certificates)

```bash
export LDAP_TLS_REQUIRE_CERT=never
python manage.py runserver
```

### For Production (Valid Certificates)

```bash
export LDAP_TLS_REQUIRE_CERT=demand
python manage.py runserver
```

### For Kubernetes Deployment

Update the deployment environment variables:

```bash
kubectl set env deployment/form-workflows-app -n default LDAP_TLS_REQUIRE_CERT=never
```

Or add to the deployment YAML:

```yaml
env:
  - name: LDAP_TLS_REQUIRE_CERT
    value: "never"
```

## Testing

After making these changes, you can test LDAP connectivity:

```bash
cd form-workflows
python test_ldap_connection.py
```

The test script will show which TLS verification level is being used.

## Security Considerations

- **Production**: Use `demand` (default) to ensure certificate verification
- **Development/Testing**: Use `never` or `allow` for self-signed certificates
- **Staging**: Use `try` to attempt verification but allow fallback

## Backward Compatibility

The default value is `demand`, which is the most secure option. However, if you were previously using the hardcoded `never` setting, you'll need to explicitly set:

```bash
export LDAP_TLS_REQUIRE_CERT=never
```

## Next Steps

1. **Rebuild the application** with these changes
2. **Set the environment variable** in your deployment
3. **Redeploy** the application
4. **Test** LDAP connectivity

### For form-workflows Deployment

```bash
# Navigate to form-workflows directory
cd form-workflows

# Rebuild the Docker image
docker build -t form-workflows:latest .

# Update Kubernetes deployment
kubectl set env deployment/form-workflows-app -n default LDAP_TLS_REQUIRE_CERT=never

# Restart the deployment to pick up code changes
kubectl rollout restart deployment/form-workflows-app -n default

# Monitor the rollout
kubectl rollout status deployment/form-workflows-app -n default
```

## Troubleshooting

### Issue: LDAP connection still fails with certificate errors

**Solution:** Verify the environment variable is set correctly:
```bash
kubectl exec -it deployment/form-workflows-app -- env | grep LDAP_TLS_REQUIRE_CERT
```

### Issue: Environment variable not being read

**Solution:** Ensure the deployment has been restarted after setting the environment variable:
```bash
kubectl rollout restart deployment/form-workflows-app -n default
```

### Issue: Still getting SSL errors

**Solution:** Try using the non-SSL LDAP URL instead:
```bash
kubectl set env deployment/form-workflows-app -n default LDAP_PRIMARY_URL=ldap://your-server:389
```

## References

- [python-ldap Documentation](https://www.python-ldap.org/en/latest/)
- [django-auth-ldap Documentation](https://django-auth-ldap.readthedocs.io/)
- [OpenLDAP TLS Configuration](https://www.openldap.org/doc/admin24/tls.html)

