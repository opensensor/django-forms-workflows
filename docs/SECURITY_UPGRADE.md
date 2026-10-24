# Security upgrade notes

This update fixes the security audit's account linking, submission receipt,
upload ownership, PDF resource fetching, embedded-form authentication, builder
permissions, analytics visibility, inactive API user, and public rate-limit issues.

## Runtime and dependencies

Use Python 3.11 or newer. Python 3.10 has reached end of life, and the patched
Pillow 13 PDF dependency requires Python 3.11. Django security minimums are
5.2.18, 6.0.9, and 6.1.2. The package rejects earlier vulnerable 6.x patch releases.
The lock resolves 5.2 LTS on Python 3.11–3.12 and 6.1 on Python 3.13+; deployments
remaining on LTS should explicitly constrain `Django>=5.2.18,<5.3`.

Regenerate deployed environments from the updated dependencies/lock, including
optional PDF dependencies. Vitest and the development dependency jaraco.context
are updated too. Run `python scripts/audit_lock.py` with pip-audit installed to
check every locked version, including alternative Python-version resolutions.
No database schema migration is required by these fixes.

## Identity and permissions

Configure explicit SSO provider/subject bindings using [SSO_CONFIGURATION.md](SSO_CONFIGURATION.md).
Review existing social-auth associations before upgrading: removing automatic
linking does not undo an association previously created by unsafe matching.
SAML accounts require explicit bindings, and disabled accounts cannot authenticate
through either bindings or personal API tokens.

Custom builder endpoints now require staff status **and** model permissions.
Grant `view_formdefinition` for viewing forms, `add_formdefinition` for creation
and cloning, and `change_formdefinition` for updates. A form definition is the
builder's aggregate: its fields are managed through that form's permission.
Workflow saves also require `change_formdefinition` and add/change permission on
`workflowdefinition`. Document-template and shared-list endpoints require the
corresponding model permissions; document changes also require change access to
the form. Sync import/pull require form add/change permissions. Review-only staff
accounts can no longer mutate these resources just by knowing the endpoint URL.

Analytics now uses submission visibility: submitters see their own records,
assigned approvers and form admin/reviewer groups see permitted records, and
superusers see all records. Restricted metadata is excluded from chart data,
form filters, approval statistics, and CSV exports.

## Public forms, receipts, and uploads

Embedding honors `requires_login` and `one_per_user`. Public forms must explicitly
set `requires_login=False`. An anonymous success receipt is available only to the
submitting session for one hour. Other users and anonymous visitors receive a
non-disclosing 404 for private receipts. HTML answer tokens are escaped and the
resulting success message is sanitized, including URL attributes.

Upload recovery is stored in the session for one hour, scoped to user and form.
Browser-supplied `_stashed_files` is ignored, so a page opened before the upgrade
may require the user to select the file again. Draft/autosave requests cannot
supply storage metadata. Existing files in an owned draft remain available.
New uploads are validated before storage, including draft uploads; the default
maximum is 32 MiB per file, configurable via `FORMS_WORKFLOWS_MAX_UPLOAD_MB`.
Form-specific extension/size limits also apply. File names used in storage gain
random identifiers; original display names are retained and HTML-escaped.

Previously stored data is not automatically trusted merely because the application
has been patched. Review suspicious pre-upgrade file metadata and revoke exposed
storage URLs where appropriate. Serve uploads through private storage or protected
media delivery; never expose the entire media directory on the application origin.

## PDF templates

Template answer values are HTML-escaped. Both individual and bulk PDF rendering
block HTTP(S), local files, SVG data URLs, and other resource URLs by default.
Inline base64 PNG/JPEG images are supported up to 5 MiB via
`FORMS_WORKFLOWS_PDF_MAX_RESOURCE_BYTES`. Embed logos as bounded raster data URLs;
remote stylesheets/fonts and file-based images no longer load automatically.

A deployment that needs more resources may set `FORMS_WORKFLOWS_PDF_URL_FETCHER`
to a dotted path to a **zero-argument factory** returning a fetcher compatible
with its installed WeasyPrint version. This is a trusted extension point: enforce
strict destination allowlists, validate redirect targets and resolved addresses,
and bound response size and time. Never configure WeasyPrint's unrestricted
fetcher for templates containing user data.

## Rate limiting and example deployment

Use a shared Redis or Memcached cache with atomic `add`/`incr` operations:

```python
CACHES = {'default': {
    'BACKEND': 'django.core.cache.backends.redis.RedisCache',
    'LOCATION': 'redis://127.0.0.1:6379/1',
}}
FORMS_WORKFLOWS_RATE_LIMIT_CACHE = 'default'
FORMS_WORKFLOWS_PUBLIC_RATE_LIMIT = '10/hour'
# Only proxies you control. Leave empty for direct connections.
FORMS_WORKFLOWS_TRUSTED_PROXIES = ['10.0.0.10/32']
```

Install the Redis client with `pip install 'django-forms-workflows[cache]'`.
Without trusted proxies, only `REMOTE_ADDR` is used. With trusted proxies, the
forwarded chain is walked from the right to the first untrusted address. Configure
the proxy to append/replace the actual client address. Cache failures reject public
submissions. Limits use fixed windows, and deployment checks flag caches that do
not provide shared atomic counters.

The example defaults to production security settings. Set `DJANGO_SECRET_KEY` to
a private random secret, `DJANGO_ALLOWED_HOSTS` to your hostnames, and
`DJANGO_CACHE_URL` to your Redis endpoint. It enables HTTPS redirect, secure cookies,
and one-year HSTS for that host. After confirming that all subdomains require
HTTPS, set `DJANGO_HSTS_INCLUDE_SUBDOMAINS=1`; set `DJANGO_HSTS_PRELOAD=1` only if
that domain is intended for browser preloading. Django reports W005/W021 until
these explicit opt-ins are set. Configure proxy HTTPS detection in settings only
when the proxy strips untrusted forwarding headers. Do not expose seeded demo
accounts. For local development only, set `DJANGO_DEBUG=1`.

Run `python manage.py check --deploy` with actual production settings before
rollout. Django 6.1's example uses `MAILERS`; older supported branches retain
`EMAIL_BACKEND`. Production uses SMTP: configure `DJANGO_EMAIL_HOST`,
`DJANGO_EMAIL_PORT`, `DJANGO_EMAIL_USER`, `DJANGO_EMAIL_PASSWORD`, and
`DJANGO_DEFAULT_FROM_EMAIL`. STARTTLS is enabled unless `DJANGO_EMAIL_USE_TLS=0`.
Set `FORMS_WORKFLOWS_BASE_URL` to the public HTTPS URL for notification links.
