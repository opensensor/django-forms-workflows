=== DFW Forms ===
Contributors: opensensor
Tags: forms, embed, django, iframe, shortcode
Requires at least: 6.0
Tested up to: 6.7
Requires PHP: 7.4
Stable tag: 1.0.0
License: LGPL-3.0-only

Embed Django Forms Workflows forms on your WordPress site via shortcode or Gutenberg block.

== Description ==

DFW Forms lets you embed forms built with [Django Forms Workflows](https://github.com/opensensor/django-forms-workflows) directly into your WordPress pages and posts.

**Features:**

* **Shortcode** — Use `[dfw_form slug="contact-us"]` in any page, post, or widget.
* **Gutenberg block** — Search for "DFW Form" in the block inserter for a visual editor with live preview.
* **Auto-resize** — Forms automatically adjust height to fit their content (JS mode).
* **Theming** — Choose light or dark theme, set a custom accent color for buttons.
* **iframe fallback** — Use `mode="iframe"` for environments where external scripts are restricted.
* **Secure** — All attributes are sanitized and escaped. No inline JavaScript injection vectors.

**How it works:**

The plugin loads the `dfw-embed.js` script from your Django Forms Workflows server, which creates a responsive iframe with automatic height adjustment via the `postMessage` API. No form data passes through WordPress — submissions go directly to your DFW server.

== Installation ==

1. Download the `dfw-forms` folder and upload it to `/wp-content/plugins/`.
2. Activate the plugin through the **Plugins** menu in WordPress.
3. Go to **Settings > DFW Forms** and enter your DFW server URL (e.g., `https://forms.example.com`).
4. Ensure the form you want to embed has **embed_enabled** checked in the Django admin.

== Usage ==

= Shortcode =

    [dfw_form slug="contact-us"]

    [dfw_form slug="feedback" theme="dark" accent_color="#ff6600" min_height="500"]

    [dfw_form slug="survey" mode="iframe"]

**Attributes:**

* `slug` (required) — The form slug from your DFW server.
* `server` — Override the global server URL for this form.
* `theme` — `light` or `dark`.
* `accent_color` — Hex color for primary buttons (e.g., `#ff6600`).
* `min_height` — Minimum iframe height in pixels (default: 300).
* `loading_text` — Text shown while the form loads.
* `mode` — `js` (default, auto-resize) or `iframe` (plain fallback).
* `on_submit` — JavaScript function name called on successful submission.
* `on_load` — JavaScript function name called when the form finishes loading.

= Gutenberg Block =

1. In the block editor, click **+** to add a block.
2. Search for **DFW Form**.
3. Enter the form slug and click **Embed Form**.
4. Use the block sidebar to configure theme, accent color, height, and embed mode.

== Frequently Asked Questions ==

= Does this work on WordPress.com? =

**WordPress.com Business or higher plans** support shortcodes and custom plugins. Use `mode="iframe"` since WordPress.com strips external script tags on lower-tier plans.

Free, Personal, and Premium WordPress.com plans do not support custom plugins.

= Do I need to modify my DFW server? =

You need to enable embedding for each form by checking **embed_enabled** in the Django admin under the "API & Embedding" section. For public forms, also ensure `requires_login` is unchecked.

= Can I embed multiple forms on one page? =

Yes. Each shortcode or block instance operates independently with its own unique container.

= How does auto-resize work? =

In JS mode, the `dfw-embed.js` script uses the `postMessage` API to communicate the iframe content height to the parent page. A `ResizeObserver` inside the iframe detects content changes and sends updated dimensions.

= What about CORS and Content Security Policy? =

Your DFW server must allow cross-origin framing. The embed view already uses `@xframe_options_exempt`. If you use a Content Security Policy, ensure `frame-src` includes your DFW server domain, or add `frame-ancestors` on the DFW server side.

== Changelog ==

= 1.0.0 =
* Initial release.
* Shortcode support with full attribute set.
* Gutenberg block with live preview and sidebar controls.
* Settings page with server URL configuration and connection test.
* JS embed mode (auto-resize) and iframe fallback mode.
