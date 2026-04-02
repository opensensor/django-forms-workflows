# WordPress Plugin — DFW Forms

The **DFW Forms** WordPress plugin lets you embed Django Forms Workflows forms on any WordPress page or post using a shortcode or Gutenberg block. All form rendering, validation, and submission happens on your DFW server — WordPress only hosts the iframe container.

## Prerequisites

Before using the plugin, you need:

1. A running Django Forms Workflows server accessible via HTTPS (e.g. `https://forms.example.com`)
2. At least one form with **embed_enabled** checked (Django Admin → Form Definition → API & Embedding → Embed enabled)
3. For public forms, **requires_login** should be unchecked so anonymous visitors can submit

## Installation

### Self-hosted WordPress (WordPress.org)

1. Download or clone the `wordpress/dfw-forms/` folder from the [django-forms-workflows repository](https://github.com/opensensor/django-forms-workflows).
2. Copy the entire `dfw-forms/` folder into your WordPress installation at `/wp-content/plugins/`:

   ```
   wp-content/
   └── plugins/
       └── dfw-forms/
           ├── dfw-forms.php
           ├── includes/
           ├── blocks/
           ├── assets/
           ├── uninstall.php
           └── readme.txt
   ```

3. In WordPress admin, go to **Plugins** and activate **DFW Forms**.

### WordPress.com

- **Business plan or higher**: Upload via **Plugins → Add New → Upload Plugin** (zip the `dfw-forms/` folder first). Use `mode="iframe"` in shortcodes since WordPress.com may strip external `<script>` tags.
- **Free / Personal / Premium plans**: Custom plugins are not supported. Use the [plain iframe method](EMBEDDING.md#iframe-fallback) in a Custom HTML block instead.

## Configuration

After activation, go to **Settings → DFW Forms**:

1. Enter your **DFW Server URL** — the base URL without a trailing slash (e.g. `https://forms.example.com`).
2. Click **Test Connection** to verify the server is reachable.
3. Click **Save Changes**.

The settings page also shows a quick-reference table of all shortcode attributes.

## Usage

### Method 1: Shortcode

Add the `[dfw_form]` shortcode to any page, post, or widget area:

```
[dfw_form slug="contact-us"]
```

#### Shortcode attributes

| Attribute | Required | Default | Description |
|-----------|----------|---------|-------------|
| `slug` | **Yes** | — | Form slug from your DFW server |
| `server` | No | Settings value | Override the global server URL for this specific form |
| `theme` | No | — | `light` or `dark` |
| `accent_color` | No | — | Hex color for primary buttons (e.g. `#0d6efd`) |
| `min_height` | No | `300` | Minimum iframe height in pixels |
| `loading_text` | No | `Loading form...` | Text shown while the form loads |
| `mode` | No | `js` | `js` (auto-resize) or `iframe` (plain fallback) |
| `on_submit` | No | — | JavaScript function name called after successful submission |
| `on_load` | No | — | JavaScript function name called when the form finishes loading |

#### Examples

Basic embed:
```
[dfw_form slug="contact-us"]
```

Dark theme with custom accent color:
```
[dfw_form slug="feedback" theme="dark" accent_color="#ff6600"]
```

Taller form with iframe fallback (for WordPress.com):
```
[dfw_form slug="application" min_height="800" mode="iframe"]
```

With JavaScript callback for analytics:
```
[dfw_form slug="survey" on_submit="trackFormSubmission"]
```

```html
<script>
function trackFormSubmission(data) {
    // data.submissionId is available
    gtag('event', 'form_submit', {
        form_slug: data.formSlug,
        submission_id: data.submissionId
    });
}
</script>
```

Using a different server for one form:
```
[dfw_form slug="external-form" server="https://other-server.example.com"]
```

### Method 2: Gutenberg Block

1. In the WordPress block editor, click **+** (Add Block).
2. Search for **DFW Form**.
3. Enter the form slug and click **Embed Form**.
4. The block shows a **live preview** of the form inside the editor.
5. Use the **block sidebar** (Settings panel on the right) to configure:
   - **Form Slug** — change the embedded form
   - **Theme** — Default, Light, or Dark
   - **Accent Color** — hex color for buttons
   - **Minimum Height** — slider from 100 to 1200px
   - **Embed Mode** — JS (auto-resize) or iframe (plain fallback)

The block renders server-side using the same shared rendering logic as the shortcode, so the output is identical.

### Multiple forms on one page

Both methods support multiple forms on the same page. Each instance gets a unique container and operates independently:

```
[dfw_form slug="contact-us"]

[dfw_form slug="feedback" theme="dark"]

[dfw_form slug="newsletter-signup" accent_color="#28a745"]
```

## How it works

Understanding the architecture helps with troubleshooting:

1. **JS mode** (`mode="js"`, the default): The plugin outputs a `<div>` container and a `<script>` tag pointing to `dfw-embed.js` on your DFW server. When the page loads, the script creates an `<iframe>` inside the container pointing to `https://your-server/forms/<slug>/embed/`. A `ResizeObserver` inside the iframe detects content height changes and sends `dfw:resize` messages via `postMessage` to the parent page, which adjusts the iframe height automatically.

2. **iframe mode** (`mode="iframe"`): The plugin outputs a plain `<iframe>` tag directly. No JavaScript is involved — the iframe has a fixed `min-height`. This is the fallback for environments that strip external scripts.

In both modes, **no form data passes through WordPress**. The iframe points directly to your DFW server, and all form validation, submission, file uploads, and payment processing happen server-side on the DFW server.

## Troubleshooting

### Form doesn't appear

- Verify the form slug is correct — it must match exactly (check Django admin → Form Definitions → slug field)
- Ensure **embed_enabled** is checked on the form in Django admin
- Ensure the form **is_active** is checked
- Check that the DFW server URL in WordPress settings is correct and reachable (use the **Test Connection** button)
- Check the browser console for errors (F12 → Console)

### Form appears but can't be submitted

- For public forms, ensure **requires_login** is unchecked in Django admin
- Check that your DFW server uses HTTPS — the embed view sets `SameSite=None; Secure` on the CSRF cookie, which requires HTTPS
- If using a Content Security Policy on your WordPress site, add your DFW server to the `frame-src` directive:
  ```
  Content-Security-Policy: frame-src https://forms.example.com;
  ```

### Form doesn't auto-resize (JS mode)

- Check the browser console for `postMessage` errors
- Verify the DFW server URL uses the correct protocol (http vs https)
- Some WordPress security plugins block inline scripts — try `mode="iframe"` as a workaround

### WordPress.com specific

- External `<script>` tags may be stripped on some plans — always use `mode="iframe"` on WordPress.com
- The Gutenberg block works on Business plans and above
- Free/Personal/Premium plans: use the [plain iframe method](EMBEDDING.md#iframe-fallback) in a Custom HTML block

## Uninstalling

Deactivating the plugin removes the shortcode and block registration. Deleting the plugin (via WordPress admin or by removing the `dfw-forms/` folder) also cleans up the `dfw_forms_server_url` option from the WordPress database via the `uninstall.php` hook.

## Plugin file structure

```
dfw-forms/
├── dfw-forms.php                    # Main plugin file, activation + registration
├── includes/
│   ├── class-dfw-render.php         # Shared HTML rendering (JS + iframe modes)
│   ├── class-dfw-settings.php       # Settings page (Settings → DFW Forms)
│   └── class-dfw-shortcode.php      # [dfw_form] shortcode handler
├── blocks/
│   └── dfw-form/
│       ├── block.json               # Gutenberg block metadata + attributes
│       ├── edit.js                   # Block editor component (no build step)
│       ├── render.php               # Server-side render for the block
│       └── editor.css               # Editor-specific styles
├── assets/
│   ├── css/admin.css                # Admin settings page styles
│   └── js/admin.js                  # Test Connection button logic
├── uninstall.php                    # Cleanup on plugin deletion
└── readme.txt                       # WordPress.org-style readme
```

## Security

All shortcode attributes are sanitized:

| Attribute | Sanitization |
|-----------|-------------|
| `slug` | `sanitize_title()` — only lowercase alphanumeric and hyphens |
| `server` | `esc_url()` — must be a valid URL |
| `theme` | Whitelist: `light`, `dark`, or empty |
| `accent_color` | Regex: must match `#[0-9a-fA-F]{3,8}` |
| `min_height` | `absint()` — positive integer only |
| `loading_text` | `sanitize_text_field()` — strips tags and encoding |
| `on_submit` / `on_load` | Regex: valid JS identifier chars only (`[a-zA-Z_$][a-zA-Z0-9_$.]*`) |
| `mode` | Whitelist: `js` or `iframe` |

The plugin does not execute any user-supplied JavaScript directly. Callback names are validated but only passed as `data-*` attributes — the `dfw-embed.js` script on the DFW server handles the actual function lookup via `window[callbackName]`.

## Related docs

- [Embedding Guide](EMBEDDING.md) — JS loader, iframe fallback, postMessage protocol
- [Payments](PAYMENTS.md) — payment collection in embedded forms
- [Workflows](WORKFLOWS.md) — approval workflows triggered by embed submissions
