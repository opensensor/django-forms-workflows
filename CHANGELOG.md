# Changelog

All notable changes to Django Forms Workflows will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.61.1] - 2026-04-02

### Fixed
- **Withdrawal notifications broken** — `withdraw_submission` view imported the
  removed legacy function `_notify_workflow_notification_with_cadence`; a bare
  `except Exception` silently swallowed the `ImportError`, so `form_withdrawn`
  notification rules never fired for any form. Replaced with a direct call to
  `_dispatch_notification_rules(submission, "form_withdrawn")`.

## [0.61.0] - 2026-04-02

### Added
- **Triggering Stage option** for notification rules — new `use_triggering_stage` boolean
  auto-scopes the rule to whichever stage fired the event at runtime, eliminating
  the need to create a separate rule per stage.
- **Workflow-scoped notification rules** — when a notification event is associated with
  a specific task, rules are now filtered to only the task's workflow instead of firing
  rules from every workflow attached to the form definition.
- Migration `0087`.

## [0.60.0] - 2026-04-02

### Added
- **Embeddable Forms** — Embed DFW forms on any external website via iframe:
  - `dfw-embed.js` loader script: creates responsive iframe with auto-resize via `postMessage` (`dfw:loaded`, `dfw:resize`, `dfw:submitted`), configurable theme, accent color, callbacks.
  - `embed_base.html` minimal layout (no navbar/footer) + `form_embed.html` with full field JS support + `embed_success.html` inline success state.
  - `form_embed` view with `@xframe_options_exempt`, `SameSite=None; Secure` CSRF cookie, rate limiting for anonymous submissions, submission controls (close date, max submissions).
  - `embed_enabled` BooleanField on `FormDefinition`.
  - Admin: embed code panel on FormDefinition change form with three tabs (JS Embed, iframe Fallback, WordPress Shortcode) with copy-to-clipboard buttons.
  - Form builder: "Embeddable" checkbox in Submission Controls.
  - sync_api export/import and clone support.
  - Migration `0086`.
- **WordPress Plugin** (`wordpress/dfw-forms/`):
  - `[dfw_form]` shortcode with full attribute sanitization.
  - Gutenberg block (apiVersion 3, no build step) with live preview and sidebar controls.
  - Settings page at Settings > DFW Forms with server URL and "Test Connection" button.
  - JS and iframe embed modes; WordPress.com compatibility notes.

### Fixed
- **CodeQL #25**: DOM text reinterpreted as HTML in workflow-builder.js — validate workflowId and use `URL()` constructor.
- **CodeQL #26-28**: Clear-text logging of form slugs in sync_api.py — removed user-supplied values from log messages.
- **CodeQL #23**: Information exposure via ValidationError in workflow_builder_views.py — log server-side only, return generic error.

### Documentation
- `docs/EMBEDDING.md` — full embedding guide: JS loader, iframe fallback, WordPress plugin, security considerations (CORS, CSP, CSRF, rate limiting).

### Tests
- 14 new embed tests: GET/POST, disabled/inactive, theme, accent color sanitisation, closed form, max submissions, audit log, success message piping, no-redirect behavior.

## [0.58.0] - 2026-04-02

### Added
- **Pluggable Payment System** — Collect payments as part of the form submission flow with a three-layer architecture:
  - `PaymentProvider` ABC (`payments/base.py`) with `PaymentFlow` (INLINE/REDIRECT), `PaymentStatus` enum, and `PaymentResult` dataclass.
  - Provider registry (`payments/registry.py`) with `register_provider()` for self-registration in `AppConfig.ready()`.
  - Built-in **Stripe provider** (`payments/stripe_provider.py`) using PaymentIntents with `automatic_payment_methods`.
  - `PaymentRecord` model tracking payment lifecycle per submission (provider, transaction_id, amount, currency, status, idempotency_key).
  - 7 payment config fields on `FormDefinition`: `payment_enabled`, `payment_provider`, `payment_amount_type`, `payment_fixed_amount`, `payment_amount_field`, `payment_currency`, `payment_description_template`.
  - `pending_payment` status on `FormSubmission`.
  - 5 URL endpoints: initiate, confirm, return (redirect flow), cancel, webhook.
  - Admin: `PaymentRecordAdmin` (read-only), `PaymentRecordInline` on submissions, "Payment" fieldset on `FormDefinitionAdmin`.
  - Form builder: payment settings panel with provider dropdown, amount type, currency.
  - Sync export/import and clone support for payment fields.
  - `payment-stripe.js` for Stripe Elements integration.
  - Templates: `payment_collect.html`, `payment_error.html`.
  - Migration `0085`.

### Documentation
- `docs/PAYMENTS.md` — full payment system guide covering architecture, Stripe setup, webhook configuration, custom provider authoring, admin/builder integration, and sync behavior.

### Tests
- 28 new tests covering PaymentRecord model (CRUD, constraints, cascades, ordering), FormDefinition payment fields, pending_payment status, provider registry (register, get, choices, auto-registration), payment views (initiate, cancel), Stripe provider (name, flow, availability, config), and data structures (enums, dataclass).

## [0.57.0] - 2026-04-02

### Added
- **Shared Option Lists** — Centrally managed reusable choice lists:
  - `SharedOptionList` model with `name`, `slug`, `items` (JSON), `is_active`, and `get_choices()` method.
  - `shared_option_list` FK on `FormField` — when set, overrides inline choices for select, radio, multiselect, and checkboxes fields.
  - Choice resolution priority: database prefill source → shared option list → inline choices.
  - `SharedOptionListAdmin` with list display, search, prepopulated slug, JSON editor.
  - Form builder UI: "Shared Option List" dropdown in field properties for choice-based fields.
  - Builder API endpoints: list, save, delete shared lists (admin-only).
  - Sync export/import support (by slug).
  - Migration `0084`.

### Documentation
- `docs/SHARED_OPTION_LISTS.md` — feature guide covering model, choice resolution, admin, builder, sync, and usage examples.

### Tests
- 16 new tests covering SharedOptionList model (CRUD, get_choices with string/dict/mixed/empty items, unique slug, FK relationship, SET_NULL on delete, ordering) and form choice resolution (override, radio, checkboxes, fallback, deleted list fallback).

## [0.56.0] - 2026-04-02

### Added
- **Dependent Workflow Trigger** — `start_trigger` field on `WorkflowDefinition` with two options:
  - `on_submission` (default) — starts immediately when the form is submitted.
  - `on_all_complete` — starts only after every `on_submission` workflow on the form has completed.
  - Enables "gate" patterns: parallel approval tracks converge, then a final review workflow runs.
  - Engine: `create_workflow_tasks` filters out deferred workflows; `_try_finalize_all_tracks` starts deferred workflows when on_submission tracks complete via new `_start_deferred_workflows()` helper.
  - Admin: exposed in `WorkflowDefinitionInline` and `WorkflowDefinitionAdmin` (list_display, list_filter).
  - Sync, clone, and form builder serialization support.
  - Migration `0083`.

### Documentation
- `docs/WORKFLOWS.md` — new "Dependent workflows" section with example and comparison to sub-workflows.

## [0.54.0] - 2026-04-01

### Added
- **Success Pages** — Three new fields on `FormDefinition` control post-submission routing, evaluated in priority order:
  - `success_redirect_rules` (JSONField) — array of conditional redirect rules; first match wins. Each rule combines a `url` with any condition the existing evaluate-conditions engine understands (simple field equality, compound AND/OR, etc.).
  - `success_redirect_url` (CharField) — static redirect URL, applied when no rule matches.
  - `success_message` (TextField) — custom HTML rendered at `/submissions/<id>/success/` when no redirect is configured.
  - New `submission_success` URL (`forms_workflows:submission_success`) and view; template `submission_success.html` with "My Submissions" / "Back to Forms" navigation.
- **Answer piping** — `{field_name}` token substitution available in three places:
  - *Success messages & redirect URLs* — `_pipe_answer_tokens()` helper resolves tokens server-side from `form_data`; list-valued fields are comma-joined; unknown tokens become empty strings.
  - *Notification subjects* — `subject_template` on `NotificationRule` now resolves `{field_name}` tokens alongside `{form_name}` and `{submission_id}` via a `defaultdict(str)` (fail-open: unknown tokens → empty string).
  - *Live form labels* — new JS block in `form_submit.html` scans `<label>`, `<small>`, and `.form-text` elements for tokens, attaches `input`/`change` listeners, and replaces them in real-time as the user types.
- **`form_data` in notification email context** — the full `form_data` dict is now passed to every notification template so HTML templates can reference `{{ form_data.field_name }}` directly.
- **Form builder: Success Page settings panel** — redirect URL input, conditional rules JSON editor, success message textarea with piping syntax hints, and a CAPTCHA toggle; all values round-trip through `form_builder_load` / `form_builder_save`.
- **Migration `0081`** (`0081_add_success_page_fields`) — adds `success_message`, `success_redirect_url`, and `success_redirect_rules` to `FormDefinition`.

### Documentation
- `docs/POST_SUBMISSION_ACTIONS.md` — new **Success Pages** and **Answer Piping** sections.
- `docs/NOTIFICATIONS.md` — new **Answer Piping in Subjects** section; `form_data` template context documented.
- `docs/FORM_BUILDER_USER_GUIDE.md` — Submission Controls panel, Success Page settings panel, palette search, and four new field types documented.
- `docs/CLIENT_SIDE_ENHANCEMENTS.md` — new **Real-Time Answer Piping** section (§ 6).

### Tests
- New tests in `tests/test_views.py`: `TestPipeAnswerTokens` (9 cases), `TestSubmissionSuccessView` (5 cases), `TestSuccessRouting` (10 cases).
- New tests in `tests/test_notifications.py`: 5 cases covering subject piping, unknown-field fail-open, built-in placeholders, list-value comma-join, and `form_data` in template context.

## [0.53.0] - 2026-04-01

### Added
- **Rating field** (`field_type = "rating"`) — star-based rating widget rendered via a CSS-only radio button group. `max_value` controls the star count (default 5). Stored as a string `"1"`–`"5"` (or up to the configured max).
- **Slider field** (`field_type = "slider"`) — range slider input backed by `DecimalField`. `min_value`/`max_value` set the range; `default_value` sets the step size. Live value badge updates as the user drags. Rendered with Bootstrap's `form-range` class.
- **Address field** (`field_type = "address"`) — structured address stored as free-text (up to 500 chars). The JS form-enhancements layer splits the textarea into labelled sub-inputs (street, city, state, ZIP, country) on the client side.
- **Matrix / Grid field** (`field_type = "matrix"`) — questionnaire-style grid defined by `choices = {"rows": [...], "columns": [...]}`. Each row becomes a separate `RadioSelect` sub-field; answers are collected as a hidden marker field. Falls back to a plain `Textarea` when no rows/columns are configured.
- **Submission controls on `FormDefinition`** — three new fields enforced at the view layer before any form is rendered or submitted:
  - `close_date` (`DateTimeField`, nullable) — stops accepting submissions after the configured date/time.
  - `max_submissions` (`PositiveIntegerField`, nullable) — caps the total number of non-draft submissions.
  - `one_per_user` (`BooleanField`, default `False`) — restricts each authenticated user to a single non-draft, non-withdrawn submission.
- **CAPTCHA support** (`enable_captcha` on `FormDefinition`) — when enabled, injects a hidden `captcha_token` field and a `<div data-captcha-widget>` placeholder. The JS layer dynamically loads either Google reCAPTCHA v2/v3 or hCaptcha (detected by script tag). Server-side verification via `DynamicForm._verify_captcha_token()` calls the provider's `siteverify` endpoint using `FORMS_WORKFLOWS_CAPTCHA_SECRET_KEY` / `FORMS_WORKFLOWS_CAPTCHA_VERIFY_URL` settings; fails open when the key is not configured.
- **Analytics CSV export** — new `/analytics/export/` endpoint (`analytics_export_csv`) returns a CSV of all non-draft submissions in the selected time range, filterable by form slug. Columns: Date, Form, Status, Submitter, Submission ID.
- **Analytics period-over-period comparison** — the analytics dashboard now computes the previous equivalent period and exposes `total_change`, `approved_change`, `rejected_change`, and `approval_rate` / `approval_rate_change` context variables for trend indicators.
- **Form builder: Submission Controls panel** — close date picker, max-submissions input, and one-per-user / CAPTCHA checkboxes added to the form-settings panel in the visual form builder; values round-trip through `form_builder_load` / `form_builder_save`.
- **Form builder: palette search** — live filter input in the field-palette panel narrows the displayed field types as the user types.
- **Migration `0080`** — adds `close_date`, `max_submissions`, `one_per_user`, `enable_captcha` to `FormDefinition`; extends `FormField.field_type` choices with `rating`, `matrix`, `address`, `slider`.

### Fixed
- **QR code view: inactive form now returns 404 before 501** — `form_qr_code` previously checked for the `segno` package before resolving the form, so requests for inactive or non-existent slugs returned 501 (Not Implemented) instead of 404 when `segno` was not installed. The `get_object_or_404` call is now performed first.

### Tests
- 156 new test cases across `tests/test_forms.py` and `tests/test_views.py` covering all four new field types, CAPTCHA injection and verification, all three submission controls (positive and negative paths), the analytics dashboard context keys and period comparison, and the CSV export (content, headers, filtering, filename).

## [0.49.0] - 2026-04-01

### Added
- **Visual workflow builder parity expanded** — The builder now supports workflow track selection, workflow/stage trigger conditions, notification rules, ordered stage approval groups, and approval-only stage fields without dropping into Django Admin.

### Changed
- **Visual workflow builder UX and validation pass** — Added inline validation summaries, node-level warnings/errors, safer save feedback, and backend validation for common builder misconfigurations such as missing approver sources, duplicate approval-only fields, and invalid notification cadence settings.

## [0.48.0] - 2026-04-01

### Added
- **Settings-based callback handler registry** — New `FORMS_WORKFLOWS_CALLBACKS` setting maps short handler names to dotted Python paths. Custom handlers can now be referenced by name (e.g. `"id_photo_copy"`) in `PostSubmissionAction.custom_handler_path` instead of full module paths. The executor resolves names from the registry first, then falls back to direct import for backward compatibility.
- **`callback_registry` module** — `register_handler(name, handler)`, `get_handler(name)`, `get_registered_names()`, `is_registered(name)`, and `clear()` APIs for programmatic handler registration (e.g. in `AppConfig.ready()`).
- **Auto-loading from settings** — `DjangoFormsWorkflowsConfig.ready()` calls `load_from_settings()` to bulk-register handlers from the `FORMS_WORKFLOWS_CALLBACKS` dict on startup.

## [0.47.3] - 2026-03-31

### Fixed
- **PDF/detail: stage-scoped section headers leaking into main form data** — Section-type fields with `workflow_stage_id` set (e.g. "ADMISSIONS COUNSELOR REVIEW", "HR REVIEW") were rendered in the main form data table because the section check fired before the stage-scope check. The `workflow_stage_id` filter now runs first, so stage section headers AND stage-scoped data fields are both excluded from the main table.
- **`_build_ordered_form_data` also fixed** — The submission detail view's ordered form data builder now also excludes stage-scoped fields and their indexed variants from the main data, matching the PDF fix.
- **Null-safe submitter check in `submission_detail`** — Fixed `submission.submitter == request.user` crash for anonymous submissions.

## [0.47.2] - 2026-03-31

### Fixed
- **Full name assignee lookup: disambiguate duplicate names** — When multiple Django users share the same first/last name (e.g. `lnickerson` and `logan.nickerson` both named "Logan Nickerson"), the lookup now narrows by stage approval group membership. If exactly one matching user is in the approval group, that user is assigned. If still ambiguous, falls back to group assignment with a warning log.

## [0.47.1] - 2026-03-31

### Fixed
- **Prevent silent auto-approval when stage trigger conditions don't match** — When a workflow has stages with approval groups but no first-order stage trigger conditions match the submission data, the submission now stays `pending_approval` instead of being silently auto-approved. A warning is logged to help admins detect misconfigured triggers (e.g. form choices renamed but stage triggers not updated).
- **PDF regression: approval-step fields leaking into main form data** — Stage-scoped field values (including sub-workflow indexed variants like `field_name_1`) no longer appear in the main form data table of PDFs. They are properly confined to their dedicated approval-step sections.
- **PDF privacy: `hide_approval_history` now fully respected** — When `hide_approval_history` is enabled and the viewer is the submitter, approval-step sections are suppressed in both single and bulk PDFs. Previously, stage-scoped field data could leak through the fallback "unseen keys" loop.
- **Null-safe submitter checks in PDF views** — Fixed `submission.submitter == request.user` comparisons that would crash for anonymous submissions; now uses `submitter_id` comparison.

## [0.47.0] - 2026-03-31

### Added
- **Public form support** — Forms with `requires_login=False` are now fully accessible to anonymous (unauthenticated) users. Anonymous users can:
  - Browse the form list (only public forms are shown)
  - Submit public forms
  - See a confirmation page after submission
- **Rate limiting for anonymous submissions** — IP-based rate limiting using Django's cache framework prevents abuse. Configurable via `settings.FORMS_WORKFLOWS_PUBLIC_RATE_LIMIT` (default: `"10/hour"`). Format: `"<count>/<period>"` where period is `minute`, `hour`, or `day`. Returns a 429 page when exceeded.
- **Anonymous submission handling** — `FormSubmission.submitter` is now nullable. Anonymous submissions store IP address and user agent for audit purposes. Auto-save and draft saving are disabled for anonymous users.

### Changed
- `FormSubmission.submitter` is now `null=True, blank=True` (migration included)
- `AuditLog.user` is now `null=True, blank=True` for anonymous submission logging
- `form_list` view no longer requires login — shows public forms to anonymous users, full list to authenticated users
- `form_submit` view uses conditional authentication instead of `@login_required`
- `form_auto_save` returns 403 for unauthenticated requests instead of redirecting to login
- All templates (submission detail, approve, PDF, email, reassign) handle null submitter gracefully
- Workflow engine guards `requires_manager_approval` against null submitter

## [0.46.0] - 2026-03-31

### Added
- **Advanced reporting analytics dashboard** — New `/analytics/` page with:
  - Summary cards: total submissions, pending, approved, rejected, withdrawn, overdue tasks
  - Approval turnaround metrics: average, fastest, slowest
  - **Charts** (via Chart.js): submissions over time (line), monthly volume (bar), submissions by form (horizontal bar), status breakdown (doughnut)
  - **Bottleneck stages** table: stages with the most pending tasks
  - **Stage turnaround** table: average approval time per stage
  - **Top approvers** table: most active approvers in the period
  - Filter by form and time range (30d / 90d / 6mo / 1yr)
  - Nav link added for staff users (visible between Approvals and Admin)
- **Form versioning marked as shipped** — ChangeHistory model, sync API snapshots, and admin diff viewer action provide full versioning capability.

## [0.45.0] - 2026-03-31

### Added
- **Signature field: Type mode** — Users can now choose between Draw (freehand) and Type (name → cursive font) when signing. Four handwriting-style Google Fonts are available: Elegant (Dancing Script), Formal (Great Vibes), Casual (Caveat), Classic (Sacramento). The typed text is rendered onto the canvas so the stored value is always a base64 PNG data URI regardless of input method.

### Fixed
- **Signature canvas border visibility** — Reinforced the canvas container border with inline styles (`2px solid #6c757d`) and CSS `!important` to prevent framework overrides from making the drawing area invisible.

## [0.44.1] - 2026-03-31

### Fixed
- **Suppress audit logs for auto-saves** — Removed `AuditLog` creation and `ChangeHistory` signal tracking from the `form_auto_save` view. Auto-saves fire every ~30 seconds and were generating excessive database rows. Explicit "Save Draft" and "Submit" actions still create audit entries as before.

### Added
- **`_skip_change_history` opt-out flag** — Any code can now set `instance._skip_change_history = True` before calling `.save()` to suppress `ChangeHistory` signal tracking (useful for auto-saves, bulk imports, etc.).
- **Sync API: workflow-level notification rules** — Export and import now include workflow-scoped `NotificationRule` entries (where `stage=null`), with dedicated prefetch and diff support.
- **Sync API: `allow_edit_form_data`** — Stage serialization and diff comparison now include the `allow_edit_form_data` field.

## [0.44.0] - 2026-03-31

### Added
- **Standalone `NotificationRuleAdmin`** — Full admin interface for NotificationRule with list display, filters, search, and fieldsets. Supports browsing notification rules across all workflows.

### Changed
- **Unified batching in `send_notification_rules`** — Cadence-aware dispatch now lives inside the unified task. Removed legacy `_queue_workflow_level_notifications` and `_queue_approval_request_notifications` functions. All batching (immediate, daily, weekly, monthly, form_field_date) flows through a single code path.
- **Simplified `_notify_task_request`** — No longer has its own batching logic; delegates entirely to `_dispatch_notification_rules` + built-in `send_approval_request`.

### Removed
- **Legacy notification models** — Dropped `WorkflowNotification`, `StageFormFieldNotification`, and `WorkflowStage.notify_assignee_on_final_decision`. All configuration now uses `NotificationRule` exclusively. Legacy task stubs retained for in-flight Celery message compatibility.
- **Legacy notification functions** — Removed `send_workflow_definition_notifications`, `send_stage_form_field_notifications`, `send_submission_form_field_notifications` implementations (stubs remain as no-ops for Celery compat).

### Fixed
- **Signature field border visibility** — Changed signature pad canvas border from `#dee2e6` (nearly invisible light gray) to `#adb5bd` (clearly visible medium gray) so users can see the signature area boundary.

## [0.43.0] - 2026-03-31

### Added
- **Unified `NotificationRule` model** — Replaces `WorkflowNotification`, `StageFormFieldNotification`, and `WorkflowStage.notify_assignee_on_final_decision` with a single, generic model. All six recipient sources (submitter, email field, static emails, stage assignees, stage groups, arbitrary groups) are available on every event type, letting admins configure any combination they need.
- **New event types** — `stage_decision` (fires when an individual stage completes), `workflow_approved`, `workflow_denied`, `form_withdrawn` replace the legacy `approval_notification`, `rejection_notification`, `withdrawal_notification` names.
- **Group notifications** — `notify_stage_groups` includes all users in a stage's approval groups; `notify_groups` M2M allows notifying arbitrary Django groups independent of stage assignment.
- **Stage-scoped vs. workflow-scoped rules** — Setting the optional `stage` FK scopes `notify_stage_assignees` and `notify_stage_groups` to a specific stage. Leaving it null includes all stages.
- **Unified `send_notification_rules` Celery task** — Single dispatch entry point for all `NotificationRule` records, with full conditions evaluation, recipient resolution, and template rendering.
- **Data migration `0075`** — Automatically migrates all existing `WorkflowNotification`, `StageFormFieldNotification`, and `notify_assignee_on_final_decision` records into `NotificationRule`.
- **Comprehensive notification documentation** — `docs/NOTIFICATIONS.md` with architecture overview, model reference, 10 configuration scenarios, troubleshooting guide, and migration notes.

### Changed
- **Legacy models retained** — `WorkflowNotification` and `StageFormFieldNotification` remain for backward compatibility. The workflow engine dispatches both legacy and unified paths in parallel. Legacy models will be removed in a future release.
- **Updated `PendingNotification` and `NotificationLog` event types** — Both models now include the new event names alongside legacy names for historical records.

## [0.42.2] - 2026-03-31

### Fixed
- **WorkflowStage admin crash (`sortable_options`)** — `ChangeHistoryInline` used Django's `GenericTabularInline` but was included inside `NestedModelAdmin` views, causing `AttributeError: 'ChangeHistoryInline' object has no attribute 'sortable_options'`. Changed to `nested_admin.NestedGenericTabularInline` for compatibility.

## [0.42.1] - 2026-03-31

### Fixed
- **WorkflowNotification `__str__` and `clean()` crash** — Removed stale references to a `notify_assignees` field that was never added to the model, causing `AttributeError` on any admin page that rendered a `WorkflowNotification` instance. Updated docstring to reflect the stage-level flag.

## [0.42.0] - 2026-03-31

### Added
- **Stage-level `notify_assignee_on_final_decision` flag** — New boolean field on `WorkflowStage` that controls whether a stage's dynamically-assigned approver (resolved via `assignee_form_field`) is included as a recipient on final approval/rejection notifications. Defaults to `False`, making dynamic assignee notification opt-in per stage rather than the previous unconditional inclusion. This gives administrators granular control over which stage assignees receive final decision emails.

## [0.38.6] - 2026-03-30

### Fixed
- **Workflow-level submission/final-decision notifications dispatched too early** — Submission-received and workflow-level final approval/rejection notifications are now dispatched on transaction commit so Celery does not race uncommitted submission/task state. This restores `submission_received` notifications for active workflows like Online Tuition Remission where approval requests were being sent but workflow-level notifications were missing from the notification log.
- **Final decision recipients now include dynamic advisor/counselor assignees** — Final approval and rejection notifications now include direct assignees from workflow tasks backed by `assignee_form_field`, ensuring assigned advisors/counselors receive the final decision email alongside the submitter and any configured recipients.
- **Approval comment help text clarified** — The approval page still warns that decision comments are public, but no longer tells end users to add a private field they cannot configure themselves.

## [0.38.5] - 2026-03-30

### Fixed
- **Send-back stage actions missing from approval workflows** — The visual workflow builder now round-trips the stage-level `allow_send_back` flag, so stages configured as send-back targets persist correctly and the approval UI once again shows **Send Back for Correction** where applicable. Older saved visual workflow JSON is backfilled from `WorkflowStage.allow_send_back` to avoid silently losing the button on existing workflows.
- **Submission PDF visibility/privacy alignment** — Reviewer-group members are now treated like other elevated users for `post_approval` PDF access, and submitter-only PDF views now respect `WorkflowDefinition.hide_approval_history` so approval-step details are hidden consistently in generated PDFs.

## [0.38.0] - 2026-03-27

### Added
- **Batching for all WorkflowNotification event types** — `notification_cadence` now applies to every workflow-conclusion event (`approval_notification`, `rejection_notification`, `withdrawal_notification`) in addition to the existing `submission_received`. Previously only `submission_received` and `approval_request` were batched; the other three always fired immediately regardless of cadence.
- **`_queue_workflow_level_notifications(submission, workflow, notification_type)`** — replaces the old `_queue_submission_notifications` helper. Resolves every matching `WorkflowNotification` rule (evaluating conditions and all three recipient sources — `notify_submitter`, `email_field`, `static_emails`) and creates one `PendingNotification` row per resolved recipient, correctly honouring per-rule conditions and the full recipient resolution logic.
- **`_dispatch_conclusion_digest`** — new batch-dispatch function for `approval_notification`, `rejection_notification`, and `withdrawal_notification` digests, reusing the existing `notification_digest.html` template with a verb/label context (`approved`/`rejected`/`withdrawn`).
- **`_notify_workflow_notification_with_cadence(submission, notification_type)`** — shared helper in `workflow_engine.py` that checks `notification_cadence` and either queues via `_queue_workflow_level_notifications` or fires `send_workflow_definition_notifications` immediately. Used by `_notify_submission_created`, `_notify_final_approval`, `_notify_rejection`, and the withdrawal view.

### Changed
- `PendingNotification.NOTIFICATION_TYPES` expanded with `approval_notification`, `rejection_notification`, `withdrawal_notification`.
- `send_batched_notifications` dispatch block handles all five notification types; unknown types are logged and skipped rather than silently dropped.
- Stage `StageFormFieldNotification` events always fire immediately regardless of cadence — this is unchanged and intentional.

## [0.37.17] - 2026-03-27

### Fixed
- **Row field vertical alignment** — When fields sharing a row have labels of different lengths (e.g. one wraps to two lines), the input controls no longer drift to different heights. Both the `half`-width paired row and the `third`/`fourth`-width grouped row now emit `align-items-end` on the Bootstrap row element so all inputs in a shared row land on the same baseline.

## [0.37.16] - 2026-03-27

### Removed
- **`WorkflowDefinition.notify_on_submission/approval/rejection/withdrawal`** — four legacy boolean columns dropped from the database (migration `0068`). All submitter notifications are now configured via `WorkflowNotification` rows with `notify_submitter=True` (created by migration `0067` for every previously-enabled flag).
- **`WorkflowDefinition.additional_notify_emails`** — legacy comma-separated CC field dropped. Static addresses have been migrated to `WorkflowNotification.static_emails`.
- **`send_rejection_notification`, `send_approval_notification`, `send_submission_notification`, `send_withdrawal_notification` Celery tasks** — fully removed. These are replaced by `send_workflow_definition_notifications` which handles all workflow-level submitter and additional-recipient emails via `WorkflowNotification` rules.
- **Legacy call sites** in `workflow_engine.py` (`_notify_submission_created_immediate`, `_notify_final_approval`, `_notify_rejection`) and `views.py` (withdrawal) — the `try/except` blocks that imported and dispatched the removed tasks are gone; those functions now call only `_notify_workflow_level_recipients` (→ `send_workflow_definition_notifications`).
- **Auto-approval task** (`check_auto_approve_deadlines`) now calls `send_workflow_definition_notifications.delay(submission_id, "approval_notification")` instead of the removed `send_approval_notification`.
- **Admin deprecated fieldset** for legacy notifications removed from `WorkflowDefinitionAdmin`.
- **`diff_views`, `form_builder_views`, `sync_api`, `workflow_builder_views`** — all references to the five dropped columns removed.
- **`tests/test_builders.py`** — assertions about `notify_on_*` fields removed.
- **`workflows/` management commands and `create_test_form_with_db_prefill.py`** — legacy field kwargs removed from all `WorkflowDefinition.objects.create()` calls.

## [0.37.15] - 2026-03-27

### Fixed
- **`third`/`fourth` width fields rendering on separate lines** — The `_setup_layout` method now collects consecutive same-width fields into a shared `Row` (up to 3 for `third`/`col-md-4`, up to 4 for `fourth`/`col-md-3`), exactly like the existing `half` grouping logic. Previously each field got its own `Row`, forcing them onto individual lines regardless of width.

### Added
- **`WorkflowNotification.notify_submitter`** — New boolean field (default `False`). When checked, the submission's submitter email is always included as a recipient alongside any `email_field` or `static_emails`. This is the replacement for the legacy `notify_on_*` flags.
- **Schema migration `0066`** — Adds `notify_submitter` to `WorkflowNotification`.
- **Data migration `0067`** — Converts existing `WorkflowDefinition.notify_on_*` flags into `WorkflowNotification` rows with `notify_submitter=True` and `static_emails` copied from `additional_notify_emails`. Idempotent: skips if a matching row already exists.
- **`_collect_notification_recipients` handles `notify_submitter`** — Passes through a `submission` parameter; prepends `submission.submitter.email` when `notify_submitter=True`.
- **Legacy tasks defer to `WorkflowNotification`** — `send_rejection_notification`, `send_approval_notification`, `send_submission_notification`, and `send_withdrawal_notification` now check for an existing `WorkflowNotification` row with `notify_submitter=True` for the matching event type. If found, they return early to avoid sending duplicate emails alongside the new system.
- **Admin updates** — `WorkflowNotificationInline` and `WorkflowNotificationAdmin` both expose `notify_submitter` in fieldsets and list view. The legacy notifications fieldset is now labelled `⚠️ Deprecated` with an explanatory banner directing admins to the new `WorkflowNotification` inline.
- **`WorkflowNotification.clean()` validation** — Raises `ValidationError` if none of `notify_submitter`, `email_field`, or `static_emails` is set.

## [0.37.14] - 2026-03-27

### Fixed
- **Double `workflow` DB query in 4 notification tasks** — `send_rejection_notification`, `send_approval_notification`, `send_submission_notification`, and `send_withdrawal_notification` each already resolve `workflow = getattr(submission.form_definition, "workflow", None)` for the toggle check. The subsequent `_get_hide_approval_history(submission)` call was redundantly calling `workflows.first()` a second time. The flag is now read directly from the local `workflow` variable with `bool(getattr(workflow, "hide_approval_history", False))`.
- **Extra `workflow` fetch in `send_submission_form_field_notifications` and `send_workflow_definition_notifications`** — neither task had a local `workflow` variable, so every iteration of their notification loop called `_get_hide_approval_history(submission)` → `workflows.first()`. Both tasks now resolve `workflow` once at the top and pre-compute `hide_approval_history` before the loop; the per-notif context dict reads the pre-computed value.
- **`WorkflowNotificationAdmin` list page N+1** — `workflow_form()` accessed `obj.workflow.form_definition.name` without any join, causing 2 extra queries per row. Added `list_select_related = ("workflow__form_definition",)` so the list page is served in a single query.

## [0.37.13] - 2026-03-27

### Fixed
- **`WorkflowNotification` admin integration** — multiple improvements:
  - `WorkflowNotificationInline` changed from `NestedTabularInline` to `NestedStackedInline` with a proper two-fieldset layout so the `conditions` JSON field is fully editable and the `Conditions (optional)` fieldset collapses for cleaner UX.
  - Added standalone `@admin.register(WorkflowNotification)` (`WorkflowNotificationAdmin`) with `list_display`, `list_filter`, `search_fields`, and `autocomplete_fields` — notification rules can now be searched, filtered, and managed independently of their parent workflow.
  - Added `notification_rule_count` column (blue badge) to `WorkflowDefinitionAdmin.list_display` and `hide_approval_history` to `list_filter`.
  - Renamed the legacy "Notifications" fieldset to **"Legacy Notifications (submitter + additional emails)"** and added a description explaining the difference between the legacy toggles and the new granular `WorkflowNotification` inline rows.
- **`hide_approval_history` not passed to email template contexts** — added `_get_hide_approval_history()` helper and wired the flag into every notification task's template context: `send_rejection_notification`, `send_approval_notification`, `send_submission_notification`, `send_withdrawal_notification`, `send_submission_form_field_notifications`, and `send_workflow_definition_notifications`.
- **`rejection_notification.html` ignored `hide_approval_history`** — the rejection-reason comments block (which exposed `ApprovalTask.comments` and thus implicit approval-step identity) is now wrapped in `{% if not hide_approval_history %}`.  When the flag is set, the submitter receives the rejection status without any stage-level detail.

## [0.37.12] - 2026-03-27

### Added
- **`WorkflowNotification` model** — granular, per-event notification rules attached directly to a `WorkflowDefinition` (the workflow-definition-level equivalent of `StageFormFieldNotification`).  Each rule is fully independent and supports:
  - **Four trigger events**: `submission_received`, `approval_notification` (final approval), `rejection_notification` (final rejection), `withdrawal_notification`.
  - **Dynamic recipients** via `email_field` — slug of the form field whose submitted value is the recipient email (varies per submission, e.g. `advisor_email`).
  - **Static recipients** via `static_emails` — comma-separated fixed addresses.  Both fields can be combined; the union is notified.
  - **Conditional sending** via `conditions` — same JSON format as `WorkflowStage.trigger_conditions`; evaluated against `form_data` before dispatch.  Leave blank to always send.
  - **Custom subject** via `subject_template` — supports `{form_name}` and `{submission_id}` placeholders; falls back to a sensible default.
  - **Separate email per recipient** — each rule fires its own message so different recipient groups receive tailored content rather than being bundled onto the submitter's notification.
  - Multiple independent rules per workflow — approve to one address, reject to a different one, CC a third party on all events, etc.
- **`WorkflowNotificationInline`** admin inline — added to both `WorkflowDefinitionInline` (FormDefinition change page) and `WorkflowDefinitionAdmin` (standalone WorkflowDefinition change page).
- **`send_workflow_definition_notifications` Celery task** — dispatches the new rules; called automatically from all three workflow-engine notification hooks (`_notify_submission_created_immediate`, `_notify_final_approval`, `_notify_rejection`) and from the `withdraw_submission` view.
- **`send_withdrawal_notification` Celery task** — sends a withdrawal confirmation email to the submitter (and `additional_notify_emails`), respecting the existing `notify_on_withdrawal` flag.  Previously the flag existed on the model but no email was ever dispatched on withdrawal.
- **`withdrawal_notification.html` email template** — new template matching the visual style of the existing approval/rejection templates.
- **Migration `0065_workflownotification`**.

## [0.37.11] - 2026-03-27

### Added
- **Phone field format** — `phone` field type now enforces the `(###) ###-####` format with an optional international country-code prefix (`+## `). The HTML `pattern` attribute, the server-side `RegexValidator`, the placeholder, and the error message all reflect the new format. Valid examples: `(555) 867-5309`, `+1 (555) 867-5309`, `+44 (555) 867-5309`.
- **Discard Draft on submission detail page** — when a user views their own draft via `submission_detail`, the action bar now shows a **Continue Editing** button (links back to the form to resume editing) and a **Discard Draft** button (links to the existing confirmation page at `submissions/<id>/discard/`). Both buttons are only shown when `submission.submitter == user`.

## [0.37.10] - 2026-03-27

### Added
- **Server-side conditional validation** — `DynamicForm.clean()` now evaluates each field's `conditional_rules` against the submitted data and applies the correct server-side behaviour:
  - Fields with `action: show` whose condition is **not** met are treated as hidden: any required-field error is cleared and the field value is removed from `cleaned_data` so it is never persisted.
  - Fields with `action: hide` whose condition **is** met are handled identically.
  - Fields with `action: require` whose condition **is** met are enforced as required even when the database field has `required=False`, closing the JS-bypass loophole described in the admin note.
  - Both single-rule (`{}`) and multi-rule (`[…]`) `conditional_rules` formats are supported.
- **Tests** — `TestDynamicFormConditionalValidation` added to `tests/test_forms.py` covering all four action/condition combinations plus list-format rules and the `cleaned_data` drop behaviour (7 new tests, all passing).

## [0.37.9] - 2026-03-26

### Added
- **Discard Draft** — users can now permanently delete a draft they no longer want.
  - New `discard_draft` view at `submissions/<id>/discard/` (GET shows confirmation, POST deletes and audits).
  - New URL name `forms_workflows:discard_draft`.
  - New `discard_draft_confirm.html` confirmation page matching the style of the existing `withdraw_confirm.html`.
  - **"Discard Draft" button** on the form submission page, shown in the bottom bar alongside "Back to Forms" whenever the user is editing an existing draft (`is_draft=True`). The view now passes `draft_id` to the template so the button can link to the correct URL.
  - **"Discard" action button** in the My Submissions DataTable, shown next to "Continue" for every draft row.

## [0.37.8] - 2026-03-26

### Fixed
- **CSRF token stored in draft/auto-save form data** — `performAutoSave()` iterated `FormData` without filtering, so the hidden `csrfmiddlewaretoken` input (plus any submit button names) was included in the JSON payload sent to the server and persisted in `FormSubmission.form_data`. Fixed in two places: the JS loop now skips a `AUTOSAVE_SKIP_KEYS` set (`csrfmiddlewaretoken`, `save_draft`, `submit`) before building the data object; the `form_auto_save` view also strips the same keys server-side as defense-in-depth.
- **Save Draft blocked when required fields are empty** — the `form_submit` view called `form.is_valid()` unconditionally before checking for `save_draft`, so any partially-filled form (with empty required fields) failed validation and the draft was never saved. The draft-save path is now checked first: if `save_draft` is present in `request.POST`, the raw POST data is collected (excluding the same skip-list of keys), stored directly via `update_or_create`, and an early redirect issued — `is_valid()` is only called on the full-submission path. The `formnovalidate` attribute on the button continues to prevent the browser's own HTML5 validation from blocking the POST.

### Changed
- **README** — version badge updated to 0.37.8; REST API and bulk export moved from Roadmap into Delivered; four-tier RBAC (`reviewer_groups` / `admin_groups`) and improved auto-save/draft behaviour added to Delivered; comparison table gains REST API and bulk export rows; Near-term roadmap trimmed accordingly; advanced reporting kept in Planned.

## [0.37.7] - 2026-03-26

### Fixed
- **`admin_groups` members now see submissions in list views** — `admin_groups` is documented as "Groups that can view all submissions", but the list-view queries in `my_submissions`, `my_submissions_ajax`, `completed_approvals`, and `completed_approvals_ajax` only checked `reviewer_groups`. Members of `admin_groups` could access an individual submission detail page (if they knew the URL) but the submissions never appeared in any list. All five queryset sites (including the cross-tab `completed_count` badge in `approval_inbox`) now union `admin_groups` with `reviewer_groups` when building the set of privileged form IDs, so both groups behave consistently throughout the application.

## [0.37.6] - 2026-03-26

### Fixed
- **Double cloud icon after auto-save** — `createAutoSaveIndicator` placed a static `<i class="bi bi-cloud-check">` before the `#autoSaveStatus` span, then `performAutoSave` set `status.innerHTML` to another icon-plus-text string. Every status update resulted in two icons side by side. The static icon is removed; the span now owns the icon as part of its initial text.
- **Save Draft blocked by HTML5 validation** — the Save Draft `Submit` button is a plain `type="submit"`, so the browser runs HTML5 `required`-field validation before the POST is sent, preventing a draft save until all required fields are filled. Added `formnovalidate=""` to the button so validation is bypassed for draft saves while still applying normally to the Submit button.

## [0.37.5] - 2026-03-26

### Fixed
- **Auto-save 500 on first save** — `form_auto_save` used `get_or_create` without including `form_data` in `defaults`. Because `form_data` is a NOT NULL `JSONField` with no database default, the INSERT on the very first autosave for a user raised an `IntegrityError`, which the broad `except Exception` block caught and returned as a 500. Switched to `update_or_create` with `form_data` included in `defaults`, which both fixes the NOT NULL violation and removes the now-redundant separate `.save()` call.
- **Invalid `AuditLog` action value** — the auto-save view wrote `action="auto_save"`, which is not in `AuditLog.ACTION_TYPES`. Changed to the valid `"update"` choice.

## [0.37.4] - 2026-03-26

### Fixed
- **Auto-save no longer always fails** — `get_enhancements_config` built the auto-save endpoint as `/forms/<slug>/auto-save/`, but the URL pattern is `/<slug>/auto-save/` (no `/forms/` prefix). Every fetch therefore hit a 404, which is a non-OK response, landing in the error branch and permanently displaying the "Save failed" indicator. The endpoint is now resolved with `django.urls.reverse("forms_workflows:form_auto_save", ...)` so it can never drift from the URL configuration again.

## [0.37.3] - 2026-03-26

### Fixed
- **Approval History cross-tab badge now matches actual page count** — The "Approval History" badge displayed on the Pending tab was computed with stale logic (only approved/rejected/withdrawn statuses, only ApprovalTask-assigned submissions). After the v0.37.0–v0.37.2 changes the Approval History page itself counts more submissions (pending_approval included, reviewer_groups included), causing the badge to read 2 while the page showed 4. The `completed_count` query in `approval_inbox` now mirrors `base_submissions` in `completed_approvals` exactly, so both sides of the tab bar always agree.

## [0.37.2] - 2026-03-26

### Fixed
- **Pending approvals now appear in Approval History** — `completed_approvals` and `completed_approvals_ajax` previously only matched `ApprovalTask` rows with status `approved` or `rejected`, so a submission still awaiting action (task status `pending`) was visible on the Pending tab but invisible on the History tab when filtered to "pending approval". The task-status filter now includes `"pending"`, making the two tabs consistent for approvers.

## [0.37.1] - 2026-03-26

### Fixed
- **`reviewer_groups` now visible in Approval History** — `completed_approvals` and `completed_approvals_ajax` previously built their base queryset exclusively from `ApprovalTask` records, so reviewer-group members were never shown any submissions (a form with zero approval steps produces no `ApprovalTask` rows). Both views now union the task-based results with all non-draft submissions for forms the user can review, matching the behaviour of My Submissions.

## [0.37.0] - 2026-03-26

### Added
- **`reviewer_groups` permission level on `FormDefinition`** — a new M2M field that grants named groups read-only access to all submissions and their full approval history for a form, without the management capabilities of `admin_groups`.
  - Members of a `reviewer_groups` group will see all submitted/pending/approved/rejected/withdrawn submissions for that form under **My Submissions** (alongside their own), so they can navigate to them without needing a direct URL.
  - The full approval history is always visible to reviewers even when `hide_approval_history` is enabled on the workflow (matching the behaviour for approvers and admins).
  - Access is enforced consistently across `submission_detail`, `sub_workflow_detail`, `submission_pdf`, `bulk_export_submissions`, `bulk_export_submissions_pdf`, and the `user_can_view_submission` utility.
  - The field is exposed in Django Admin under the **Access Control** fieldset with a horizontal filter widget, and is preserved when cloning a form.
  - Migration `0064_add_reviewer_groups` adds the underlying join table.

## [0.36.5] - 2026-03-26

### Fixed
- **`email_to_field` / `email_cc_field` now support comma-separated addresses** — `EmailActionHandler._get_recipients` and `_get_cc_list` previously appended the raw field value as a single address, silently discarding all but the first recipient when multiple addresses were entered. Both methods now split on commas and validate each address individually, so a faculty-emails field with `prof1@sjcme.edu, prof2@sjcme.edu` correctly delivers to all listed recipients.

## [0.36.4] - 2026-03-26

### Added
- **Dynamic dropdown choices from database** — select, multiselect, multiselect_list, radio, and checkboxes fields can now have their options populated live from any SQL query defined in `FORMS_WORKFLOWS_DATABASE_QUERIES`. Mark a query with `"return_choices": True` (and no user parameter) to return multiple rows; each row's first column becomes the option value and the second column (if present) becomes the display label. Wire it up by pointing the field's PrefillSource at the query key — the stored `choices` JSON is used as a fallback if the DB is unavailable.
- `DatabaseDataSource.execute_choices_query(query_key)` — new method that executes a choices query without a user parameter and returns `[(value, label), ...]`.
- `_get_choices_from_prefill_source(field_def)` — new helper on both form classes that detects `return_choices` queries and calls `execute_choices_query`; returns `None` when not applicable so callers fall back to stored choices.
- `execute_custom_query` now warns and returns `None` if called on a `return_choices` query, preventing accidental single-value use.

## [0.36.3] - 2026-03-26

### Fixed
- **Cross-instance sync missing newer fields** — `sync_api.serialize_form` and `_serialize_field` were not including several fields added after the serializer was first written, meaning push/pull/diff silently dropped their values on the receiving instance:
  - `FormDefinition.allow_batch_import` (spreadsheet/Excel batch upload toggle, migration 0062)
  - `FormDefinition.is_listed` (hide-from-list-page flag, migration 0051)
  - `FormDefinition.allow_resubmit` (re-submission from rejected/withdrawn, migration 0024)
  - `FormDefinition.api_enabled` (REST API exposure flag, migration 0063)
  - `FormField.formula` (formula expression for Calculated field types, migration 0056)
  All five fields are now serialized on export and restored on import. The diff summary in `diff_views._build_summary` is also updated to detect changes to all four FormDefinition flags.

## [0.33.1] - 2026-03-23

### Fixed
- **Formula/calculated field causes 500 error** — `DynamicForm.__init__` never stored `initial_data` as `self.initial_data`, but `add_field` referenced `self.initial_data` when building a `calculated` field type, resulting in `AttributeError` and a 500 on any form that contains a calculated field. Fixed by adding `self.initial_data = initial_data or {}` to `__init__`.
- **File upload field type not working in approval step** — `ApprovalStepForm._create_field` had no handler for `field_type = "file"`, so file-upload fields assigned to a workflow stage silently fell through to a plain `CharField`, preventing files from being uploaded during approval. Added a proper `FileField` / `ClearableFileInput` branch (respecting `allowed_extensions`). Also fixed `get_updated_form_data` to serialize uploaded file objects to storage (via `_serialize_single_file`) before merging into the submission's `form_data` JSON, consistent with how `serialize_form_data` handles files on normal form submission.

## [0.33.0] - 2026-03-19

### Added
- **Calculated / Formula field type** (`field_type = "calculated"`) — reads a `formula` template string (e.g. `{dept_code} - {job_type}`) stored on `FormField.formula` and produces a read-only computed value. Live client-side evaluation via injected vanilla JS in `form_submit.html`; authoritative server-side re-evaluation via `_re_evaluate_calculated_fields()` called after `serialize_form_data` at submit time. Formula exposed in both `FormFieldInline` ("Choices & Defaults" fieldset) and standalone `FormFieldAdmin` ("Formula" collapsed fieldset).
- **Spreadsheet Upload field type** (`field_type = "spreadsheet"`) — accepts `.csv`, `.xls`, `.xlsx` uploads. CSV parsed with stdlib `csv`; Excel parsed with `openpyxl` (already in the `excel` optional extra). Stored in `form_data` as `{"headers": [...], "rows": [{...}, ...]}`. Available in both `DynamicForm` and `ApprovalStepForm`.
- **Migration 0056** — adds `FormField.formula` (TextField, blank, default `""`) and extends `FormField.field_type` choices to include the two new types.

### Fixed
- **File upload in approval step** — `ApprovalStepForm` was instantiated without `files=request.FILES` in the POST branch of `approve_submission`, so uploaded files were silently ignored and the field always failed validation. Fixed by passing `files=request.FILES`. Also added `enctype="multipart/form-data"` to the approval step `<form>` tag in `approve.html`.
- **Sub-workflow spawning on parent form submission** — `create_workflow_tasks` was blindly iterating every `WorkflowDefinition` attached to the form, including child/template workflows referenced by `SubWorkflowDefinition.sub_workflow`. Those are now excluded via the existing `used_as_sub_workflow` reverse relation (`not w.used_as_sub_workflow.exists()`), so sub-workflow templates only activate through the controlled `_spawn_sub_workflows_for_trigger` path and never auto-start at submission time. No model or migration change needed.

## [0.32.1] - 2026-03-17

### Fixed
- **`FormFieldAdmin` missing `readonly` field** — the standalone FormField admin page (`/admin/django_forms_workflows/formfield/`) did not expose the `readonly` flag. Added `readonly` alongside `required` in the "Field Configuration" fieldset, added it to `list_display`, and added it to `list_filter`. It was already present in `FormFieldInline` (when editing fields inline from the parent FormDefinition page).

## [0.32.0] - 2026-03-17

### Added
- **Send Back for Correction** — a new third decision path on the approval screen that returns a staged workflow to any prior stage without terminating the submission.
  - `WorkflowStage.allow_send_back` (`BooleanField`, default `False`) — opt-in per stage via Django Admin; only stages with this flag enabled appear as send-back targets for downstream approvers.
  - `ApprovalTask.status` extended with `"returned"` (Returned for Correction) — records the closed task without triggering rejection hooks.
  - `AuditLog.action` extended with `"send_back"` — full audit trail entry written on every send-back with target stage name and reason.
  - `handle_send_back(submission, task, target_stage)` in `workflow_engine.py` — cancels sibling pending tasks at the current stage, re-creates tasks at the target stage via the existing `_create_stage_tasks` helper; `FormSubmission.status` remains `pending_approval` throughout.
  - `handle_sub_workflow_send_back(task, target_stage)` — identical logic scoped to a `SubWorkflowInstance` using `_create_sub_workflow_stage_tasks`.
  - `approve_submission` view updated to accept `decision=send_back`; validates target stage belongs to the same workflow, has a lower `order`, and that a non-empty reason was supplied.
  - `approve.html` — collapsible **Send Back for Correction** card (Bootstrap warning colour, collapsed by default) injected after the main decision buttons in both the step-fields and standard approval forms; hidden when no prior `allow_send_back` stages exist.
  - Migration `0055_add_send_back` covering all model changes above.

## [0.14.12] - 2026-03-06

### Fixed
- **Column picker (cog wheel) completely broken on approval inbox & approval history** — v0.14.9 moved column hiding to `columnDefs` at DataTables init time, but `colIndexMap` was still built AFTER init by querying `$('th.extra-form-col')`. DataTables removes hidden `<th>` elements from the DOM, so the selector found nothing and `colIndexMap` was empty — making select/deselect all and individual checkbox toggles no-ops. Fixed by building `colIndexMap` BEFORE DataTables init.
- **Horizontal scrollbar caused by column picker dropdown** — the `d-none` class was removed from the out-of-grid `#colPickerDropdown` element before it was moved into `#searchContainer`, causing a brief layout overflow. Now `d-none` is removed only after the element is repositioned.
- **XLSX export spinner stays forever (project base.html)** — the project's `templates/base.html` override was missing the `data-no-spinner` check added to the package base in v0.14.9. Added `form.hasAttribute('data-no-spinner')` guard.
- **Package base.html `data-no-spinner` check was ineffective** — `form.dataset.noSpinner` returns `""` (empty string, falsy) for a valueless attribute. Changed to `form.hasAttribute('data-no-spinner')` which correctly returns `true`.

## [0.14.10] - 2026-03-06

### Changed
- **PDF engine switched from xhtml2pdf to WeasyPrint** — WeasyPrint has full CSS3 support (including `table-layout: fixed`, `colgroup` column widths, `:nth-child` selectors, and CSS Paged Media `@page` margin boxes) making multi-column form layouts render correctly without colspan hacks.
  - `pyproject.toml` / `requirements.txt`: `xhtml2pdf>=0.2.11` → `weasyprint>=60.0`
  - `Dockerfile`: added `libpango-1.0-0`, `libpangoft2-1.0-0`, `libgdk-pixbuf2.0-0`, `libffi-dev`, `shared-mime-info` (WeasyPrint OS-level dependencies; `libcairo2-dev` was already present)
  - `views.py`: `pisa.CreatePDF()` replaced with `HTML(string=..., base_url=...).write_pdf()`
  - `submission_pdf.html`: completely rewritten — 4-column `<colgroup>` (`col-label 22%` / `col-value 28%` × 2) with `table-layout: fixed`; all row types (section, full, pair, triple) use the same 4-column grid via `colspan`; alternating row tint via `tr:nth-child(even)`; running page footer (`Page N of M · date`) via `@page @bottom-left/@bottom-right` — no more HTML footer table

## [0.14.9] - 2026-03-06

### Fixed
- **Approval inbox column picker — columns not toggling / table layout broken** — `DataTables.column(jQueryObject)` does not reliably resolve column indices once columns have been hidden or shown. Replaced the jQuery-wrapper approach with a `colIndexMap` dictionary built at DataTable init time using `table.column(rawDOMNode).index()`. All subsequent visibility calls now use the stable integer index, fixing both the picker not working and the resulting spaced-out table.
- **Bulk export spinner never dismissed** — the base template's `form[method="post"]` submit handler unconditionally activated the loading overlay, but file-download responses do not navigate the page so the overlay was never cleared. Added a `data-no-spinner` attribute check: forms that carry this attribute skip the overlay entirely. Both `#bulkExportForm` instances (`completed_approvals.html`, `my_submissions.html`) now include `data-no-spinner`.

### Notes
- Multi-form-type bulk export already produces one Excel sheet per form definition (server-side grouping by `form_definition` was in place from the initial implementation). No change needed.

## [0.14.8] - 2026-03-06

### Added
- **PDF field-width layout** — Generated PDFs now respect the `width` setting configured on each `FormField`:
  - `half` — consecutive half-width fields are grouped into side-by-side pairs within a single table row, matching the two-column layout seen on screen.
  - `third` — consecutive third-width fields (groups of three) are rendered side-by-side in a three-column row.
  - `full` — rendered as a standard single-field row spanning the full table width (unchanged behaviour).
  - Lone half or partial third groups (odd-count sequences) fall back gracefully to full-width rows.
- **PDF section headers** — `section` type fields now appear as bold dark-blue header rows in the PDF (they were previously omitted entirely).

### Changed
- `_build_pdf_rows()` helper added to `views.py` — walks all form fields (including sections) and groups them by width into structured row dicts passed to `submission_pdf.html`.
- `submission_pdf.html` — replaced the flat two-column table with a flexible six-column table that handles `section`, `full`, `pair`, and `triple` row types.

## [0.14.7] - 2026-03-06

### Fixed
- **Approval History — "Awaiting Co-Approver" badge** — submissions that are still `pending_approval` (waiting on a second approver) but where the current user has already completed their step now show a clear yellow "Awaiting Co-Approver" badge instead of falling through to the raw `pending_approval` string.
- **Tab label renamed** — "Completed Forms" tab renamed to "Approval History" in both `approval_inbox.html` and `completed_approvals.html` to accurately reflect that the page shows all forms the user has acted on, including those still awaiting other approvers.

## [0.14.6] - 2026-03-06

### Fixed
- **Approval inbox column picker — columns visible by default** — `DataTables` `columnDefs.targets` does not accept CSS class selectors, so the `{ visible: false, targets: '.extra-form-col' }` entry was silently ignored and all extra columns rendered visible on load. Extra columns are now hidden explicitly via `table.column().visible(false)` immediately after DataTables initialisation, before saved preferences are restored.
- **Column picker — added Select all / Deselect all** — a toggle link in the column-picker dropdown checks or unchecks all field checkboxes at once, shows/hides the corresponding DataTables columns, persists the result to `localStorage`, and updates its own label to reflect the current state.

## [0.14.5] - 2026-03-06

### Fixed
- **Approvals nav link visibility** — the *Approvals* link in the navbar is now only rendered for users who have an approver role (i.e. they or one of their groups has ever been assigned an `ApprovalTask`). Staff and superusers always see it. A new `user_is_approver` boolean is added to the template context via the `forms_workflows` context processor.
- **Completed approvals missing mid-workflow steps** — `completed_approvals` previously filtered on `FormSubmission.status IN ('approved','rejected','withdrawn')`, which hid submissions that were still in progress (e.g. waiting for a later approval stage). The view now filters on `ApprovalTask.status IN ('approved','rejected')` scoped to the requesting user/groups, so an approver can see every submission where they have already taken action — even if subsequent stages are still pending.

## [0.14.4] - 2026-03-06

### Fixed
- **Security: form submission bypassed category permissions** — `user_can_submit_form` now enforces the full category `allowed_groups` ancestor-chain check (matching the `form_list` view logic). Previously, any authenticated user who knew a form's URL slug could submit it even if the form's category restricted access to specific groups. Both `form_submit` and `form_auto_save` benefit automatically since they both call `user_can_submit_form`.
- Added `user_can_access_category` helper to `utils.py` for reusable, hierarchy-aware category access checks.

## [0.14.3] - 2026-03-06

### Added
- **Approval inbox column picker** — when the approvals queue is filtered down to a specific form, a gear icon (⚙) appears next to the search box. Clicking it opens a dropdown listing every field from that form's definition (sections and file-upload fields excluded). Checking a field adds it as a column to the table; unchecking removes it. Selected columns are remembered per-form in `localStorage` (`approvals_col_prefs_<form-slug>`) so preferences survive page reloads.

## [0.13.11] - 2026-02-24

### Fixed
- **Pull from Remote admin UI** — the form-selection table (Step 1) was showing blank Name, Slug, and Category columns for all remote forms. The template was reading `form.slug` / `form.name` / `form.category` directly from the serialized payload dict, but those fields are nested one level deeper at `form.form.slug`, `form.form.name`, and `form.category.name` respectively. The checkbox `value` attribute was also sending an empty string instead of the slug, so confirming the import would have silently imported nothing. All four references corrected in `sync_pull.html`.

### Added
- **Cross-instance form sync (push/pull)** — export and import `FormDefinition` records (including all fields, workflow, prefill sources, and post-submission actions) between multiple Django instances without shell access.
  - `sync_api.py` — serialization/deserialization core; forms are keyed by slug, groups by name for portability across instances.
  - `sync_views.py` — HTTP endpoints `GET /forms-sync/export/` and `POST /forms-sync/import/` protected by a shared `Bearer` token (`FORMS_SYNC_API_TOKEN`).
  - Management commands `pull_forms` and `push_forms` for CLI/scripted sync.
  - **Admin UI — Pull from Remote** (`/admin/.../formdefinition/sync-pull/`) — multi-step page: pick a configured remote from a dropdown (or enter URL + token manually), preview available forms with checkboxes, import selected forms with conflict-mode control.
  - **Admin UI — Push to Remote** (`/admin/.../formdefinition/sync-push/`) — accessible via the *"Push selected forms to a remote instance"* bulk action; shows forms to push, lets you pick the destination remote, and displays per-form results.
  - **Admin UI — Import JSON** (`/admin/.../formdefinition/sync-import/`) — upload a `.json` file or paste raw JSON; supports `update`, `skip`, and `new_slug` conflict modes.
  - **Admin action — Export as JSON** — downloads selected forms as a `.json` file directly from the changelist.
  - **Form Definitions changelist toolbar** now includes *↓ Pull from Remote*, *↑ Push All to Remote*, and *⤴ Import JSON* shortcut buttons.
  - New settings:
    - `FORMS_SYNC_API_TOKEN` — shared secret protecting the sync HTTP endpoints.
    - `FORMS_SYNC_REMOTES` — named list of remote instances with URL and token, enabling dropdown selection in the admin UI (ideal for Kubernetes deployments where kubectl exec is impractical).

## [0.13.4] - 2026-02-21

### Changed
- **Improved table UI layout** — moved search bar inline with filter row on both `completed_approvals.html` and `my_submissions.html` for a cleaner, more compact layout
- **Page length selector relocated** — moved the "Show X entries" dropdown from the top to the bottom of tables, positioned next to pagination controls for better UX
- **Enhanced form element styling** — improved visual design of search inputs (with icon), page length selectors, and pagination controls with better focus states and consistent Bootstrap styling

## [0.13.3] - 2026-02-21

### Added
- **DataTables on all approvals views** — `my_submissions.html`, `approval_inbox.html`, and `completed_approvals.html` now all include DataTables (Bootstrap 5 theme) for instant client-side search and column sorting. The *Actions* column is excluded from sorting; tables default to descending *Submitted* date order.
- **Cross-tab counts** — Both the *Pending* and *Completed Forms* tabs in the Approval Inbox always show a count badge so approvers can see the total in each view without switching tabs.

## [0.13.2] - 2026-02-21

### Added
- **Sortable, searchable table views** — the Submissions (`my_submissions.html`) and Approval Inbox (`approval_inbox.html`) tables now use DataTables (Bootstrap 5 theme) to provide instant client-side search filtering and click-to-sort on every column. Tables default to descending sort by the *Submitted* date; the *Actions* column is excluded from sorting.

## [0.13.1] - 2026-02-20

### Fixed
- **Category hierarchy permission inheritance** — sub-categories with no `allowed_groups` of their own now correctly inherit the restriction of the nearest ancestor that has groups set. Previously, `category_group_count=0` caused child categories (e.g. On-Campus, Online) to bypass the parent's `allowed_groups` restriction entirely. The `form_list` view now uses `_get_accessible_category_pks()` which walks the full ancestor chain.

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

