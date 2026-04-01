# Roadmap

This document describes what has been delivered, what is actively being worked on, and what is planned next. Items are ordered by priority within each tier.

---

## ✅ Delivered (current: v0.48.0)

<details>
<summary>Click to expand full delivery list</summary>

| Version | Feature |
|---|---|
| v0.9 | Multi-stage approval workflows (any / all / sequence per stage) |
| v0.13 | Nested `FormCategory` hierarchy with group-based access control |
| v0.13 | Cross-instance form sync — push, pull, JSON import/export, CLI commands |
| v0.14 | WeasyPrint PDF export with multi-column field layout |
| v0.14 | Approval inbox column picker with persistent `localStorage` preferences |
| v0.14 | Bulk XLSX export of submissions |
| v0.32 | **Send Back for Correction** — return to any prior `allow_send_back` stage |
| v0.33 | **Calculated / formula fields** with live JS + server-side re-evaluation |
| v0.33 | **Spreadsheet upload** field (CSV, XLS, XLSX) stored as structured JSON |
| v0.35 | **Dynamic individual assignees** — resolve approver from form field at runtime |
| v0.35 | **Conditional workflow & stage trigger logic** — skip whole tracks or stages |
| v0.45 | **Signature field type** (drawn or typed) with four Google Font options |
| v0.45 | **Form versioning** — ChangeHistory tracking, sync API snapshots, admin diff viewer |
| v0.46 | **Advanced reporting dashboard** — submission analytics, approval turnaround, bottleneck stages |
| v0.48 | **Settings-based callback handler registry** (`FORMS_WORKFLOWS_CALLBACKS`) — register custom handlers by name |
| v0.49 | **First-class workflow webhooks** — signed async delivery, retry/backoff, admin config, delivery logs, cloning, and sync support |
| all | LDAP/AD integration with profile sync, SSO attribute mapping |
| all | Configurable prefill sources (user, LDAP, database, API, system values) |
| all | Post-submission actions (email, database, LDAP, API, custom) with retries |
| all | Managed file uploads with approval lifecycle and presigned S3/Spaces URLs |
| all | Conditional field visibility (client-side, no page reload) |
| all | Form templates and cloning |
| all | Complete audit logging (who, what, when, IP address) |
| all | Configurable site branding via `FORMS_WORKFLOWS['SITE_NAME']` |
| all | 298-test suite covering engine, models, views, sync, conditions, utils |

</details>

---

## 🚧 Near-Term (next 1–3 releases)

### 1. REST API for Programmatic Form Submission

**Why:** Many integration patterns need to submit forms without a browser (CI pipelines, mobile apps, third-party systems). Currently only a sync HTTP API exists.

**Scope:**
- `GET /api/forms/` — list active forms the authenticated user can submit
- `POST /api/forms/{slug}/submit/` — submit form data, returns submission ID + status
- `GET /api/submissions/{id}/` — poll submission status, approval tasks, and history
- Token + session authentication; respects existing `user_can_submit_form` permissions
- Django REST Framework or lightweight `JsonResponse` views (no new mandatory dependency)

**Complexity:** Medium. The main challenge is serialising `form_data` consistently with the existing `serialize_form_data` pipeline.

---

### 2. Submission Dashboard & Analytics

**Why:** Administrators and form owners need visibility into form throughput, approval bottlenecks, and SLA compliance — currently only raw Django Admin lists are available.

**Scope:**
- Per-form summary card: total submissions, pending, approved, rejected (last 30 days)
- Average time-to-approval per stage (highlights bottleneck stages)
- Overdue tasks (past `due_date`) count and list
- Exportable as CSV/Excel
- Accessible at `/forms/dashboard/` (staff only)

**Complexity:** Low-Medium. Primarily aggregation queries on existing models.

---

## 📋 Medium-Term

### 4. ✅ Signature Field Type — *Shipped in v0.45.0*

### 5. ✅ Form Versioning with Diff Viewer — *Shipped in v0.45.0*

### 6. Plugin / Custom Handler Marketplace

**Why:** The `FORMS_WORKFLOWS_CALLBACKS` setting and `register_handler()` API (v0.48) provide handler registration, but there is no discoverability mechanism or standardised packaging for third-party handlers.

**Scope:**
- `django-forms-workflows-handler-{name}` packaging convention
- `entry_points` auto-discovery — handlers register themselves via `[django_forms_workflows.handlers]` entry point group
- Handler metadata schema: `name`, `description`, `config_schema` (JSON Schema for admin UI generation), `supported_triggers`
- Example reference handler packages: `dfw-handler-slack`, `dfw-handler-servicenow`

**Complexity:** Medium (protocol design) + Low (per-handler implementation).

---

## 🔭 Long-Term / Exploratory

| Idea | Notes |
|---|---|
| Full workflow-builder parity | Extend the existing visual builder to cover multi-track workflows, trigger conditions, notification rules, and the remaining admin-only workflow settings |
| AI-assisted form creation | Natural-language prompt → generates a `FormDefinition` + `WorkflowDefinition` via LLM |
| Barcode / QR field type | Scan and decode during submission; useful for asset-tracking workflows |
| Location field type | GPS coordinates or address autocomplete via browser Geolocation API |
| Native mobile app | React Native or Flutter shell embedding the form engine via REST API |
| Read-the-Docs site | Sphinx-based docs site auto-generated from this `docs/` folder |

---

## Contributing

If you'd like to work on any of these items, please open a GitHub Discussion first to align on design before sending a PR. See [CONTRIBUTING.md](../CONTRIBUTING.md) for development setup and conventions.

