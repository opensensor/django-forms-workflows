# Embedding Forms

Django Forms Workflows supports embedding forms on external websites via iframes. This guide covers all embedding methods: the JavaScript loader, plain iframe fallback, and the WordPress plugin.

## Enabling Embedding

1. In the Django admin, open the form you want to embed.
2. Expand the **API & Embedding** section.
3. Check **embed_enabled** and save.

For public-facing forms, also ensure **requires_login** is unchecked so anonymous visitors can submit.

Once enabled, the form is available at `/forms/<slug>/embed/` and the Django admin shows an **Embed Code** panel with ready-to-copy snippets.

## JavaScript Embed (Recommended)

The JS loader creates a responsive iframe that auto-resizes to fit the form content.

```html
<script src="https://your-server/static/django_forms_workflows/js/dfw-embed.js"
  data-form="contact-us"
  data-server="https://your-server"
></script>
```

### Attributes

| Attribute | Required | Default | Description |
|-----------|----------|---------|-------------|
| `data-form` | Yes | — | Form slug |
| `data-server` | Yes | — | Base URL of your DFW server |
| `data-target` | No | After script tag | CSS selector of the container element |
| `data-theme` | No | — | `light` or `dark` |
| `data-accent-color` | No | — | Hex color for primary buttons (e.g., `#ff6600`) |
| `data-min-height` | No | `300` | Minimum iframe height in pixels |
| `data-loading-text` | No | `Loading form...` | Text shown while the form loads |
| `data-on-submit` | No | — | Global JS function name called on successful submission |
| `data-on-load` | No | — | Global JS function name called when the form finishes loading |

### Callbacks

You can hook into form lifecycle events:

```html
<script>
function onFormLoaded(data) {
    console.log('Form loaded:', data.formSlug);
}
function onFormSubmitted(data) {
    console.log('Submission ID:', data.submissionId);
    // e.g., redirect, show a thank-you modal, fire analytics
}
</script>

<script src="https://your-server/static/django_forms_workflows/js/dfw-embed.js"
  data-form="feedback"
  data-server="https://your-server"
  data-on-load="onFormLoaded"
  data-on-submit="onFormSubmitted"
></script>
```

### PostMessage Events

The embedded form communicates with the parent page via `window.postMessage`:

| Event | Data | Description |
|-------|------|-------------|
| `dfw:loaded` | `{ type, formSlug }` | Form DOM is ready |
| `dfw:resize` | `{ type, formSlug, height }` | Content height changed |
| `dfw:submitted` | `{ type, formSlug, submissionId }` | Form submitted successfully |

## iframe Fallback

For environments where external scripts are restricted, use a plain `<iframe>`:

```html
<iframe src="https://your-server/forms/contact-us/embed/"
  style="width:100%;border:none;min-height:500px;"
  title="Contact Form"
  loading="lazy"
  allowtransparency="true"
></iframe>
```

URL parameters:
- `?theme=dark` — Dark theme
- `?accent_color=%23ff6600` — Custom accent color (URL-encode the `#`)

The iframe will not auto-resize in this mode. Set an appropriate `min-height` for your form.

## WordPress Plugin

The **DFW Forms** WordPress plugin provides a shortcode and Gutenberg block for easy embedding. For full installation, configuration, troubleshooting, and security details, see the **[WordPress Plugin Guide](WORDPRESS_PLUGIN.md)**.

### Installation

1. Copy the `wordpress/dfw-forms/` folder to your WordPress `/wp-content/plugins/` directory.
2. Activate **DFW Forms** in the WordPress Plugins menu.
3. Go to **Settings > DFW Forms** and enter your DFW server URL.

### Shortcode

```
[dfw_form slug="contact-us"]
```

Full example with all options:

```
[dfw_form slug="feedback" theme="dark" accent_color="#ff6600" min_height="500" mode="js"]
```

| Attribute | Default | Description |
|-----------|---------|-------------|
| `slug` | — | Form slug (required) |
| `server` | Settings value | Override the global server URL |
| `theme` | — | `light` or `dark` |
| `accent_color` | — | Hex color for buttons |
| `min_height` | `300` | Minimum height in pixels |
| `loading_text` | `Loading form...` | Loading indicator text |
| `mode` | `js` | `js` (auto-resize) or `iframe` (plain fallback) |
| `on_submit` | — | JS callback function name |
| `on_load` | — | JS callback function name |

### Gutenberg Block

1. In the block editor, click **+** and search for **DFW Form**.
2. Enter the form slug and click **Embed Form**.
3. Use the sidebar panel to configure theme, accent color, height, and embed mode.

### WordPress.com Compatibility

- **Business plan or higher**: Custom plugins are supported. Use `mode="iframe"` since WordPress.com strips external `<script>` tags.
- **Free / Personal / Premium plans**: Custom plugins are not supported. Use the plain iframe snippet in a Custom HTML block if available.

## Multiple Forms on One Page

Both the JS loader and WordPress plugin support multiple forms on the same page. Each embed instance operates independently with its own container and event listeners.

## Security Considerations

### Cross-Origin Framing

The embed view uses Django's `@xframe_options_exempt` decorator to allow cross-origin framing. If your server sets a global `X-Frame-Options` header, the embed endpoint overrides it.

### Content Security Policy

If your embedding site uses a Content Security Policy, add your DFW server to the `frame-src` directive:

```
Content-Security-Policy: frame-src https://your-server;
```

On the DFW server side, if you set `Content-Security-Policy`, include a `frame-ancestors` directive listing the domains allowed to embed your forms.

### CSRF and Cookies

The embed view sets the CSRF cookie with `SameSite=None; Secure=True` to support cross-origin form submission in iframes. This requires your DFW server to use HTTPS.

### Rate Limiting

Anonymous embed submissions are rate-limited to prevent spam. Configure rate limits in your Django settings.


## Related Docs

- [WordPress Plugin Guide](WORDPRESS_PLUGIN.md) — full plugin installation, usage, troubleshooting, and security
- [Payments](PAYMENTS.md) — payment collection in embedded forms
- [Shared Option Lists](SHARED_OPTION_LISTS.md) — centrally managed choice lists
- [Workflows](WORKFLOWS.md) — approval workflows that process embed submissions