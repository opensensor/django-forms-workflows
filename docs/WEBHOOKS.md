# Workflow Webhooks

`django-forms-workflows` includes a first-class outbound webhook system for workflow lifecycle events. Use webhooks when another system needs a real-time signal that a submission was created, approved, rejected, returned for correction, or assigned to a reviewer.

Unlike `PostSubmissionAction(action_type="api")`, webhook endpoints are:

- attached directly to a `WorkflowDefinition`
- subscribed to specific workflow events
- delivered asynchronously via Celery tasks (with synchronous fallback)
- signed with an HMAC secret for receiver-side verification
- logged per attempt in `WebhookDeliveryLog`

## Models

### `WebhookEndpoint`

One outbound subscription for one workflow track.

Key fields:

- `workflow` — workflow that owns the webhook
- `name` — admin-friendly label
- `url` — destination URL
- `secret` — HMAC signing secret; auto-generated if blank
- `events` — list of subscribed event keys
- `custom_headers` — optional static JSON headers
- `is_active` — toggle delivery on/off without deleting config
- `timeout_seconds` — HTTP timeout per attempt
- `retry_on_failure` / `max_retries` — retry behavior for non-2xx or transport failures

### `WebhookDeliveryLog`

Stores an audit record for each delivery attempt, including:

- event name
- endpoint name and URL
- related workflow / submission / approval task
- request headers and payload
- HTTP status code
- response body or exception text
- attempt number and timestamp

## Supported events

| Event | Fires when |
|---|---|
| `submission.created` | A submission enters the workflow engine |
| `task.created` | A new approval task is created for a workflow stage |
| `submission.approved` | The submission reaches final approval |
| `submission.rejected` | The submission is finally rejected |
| `submission.returned` | A send-back action returns the submission to an earlier stage |

## Configuration

Configure webhook endpoints in Django Admin:

1. Open the target form and workflow track.
2. In the **Webhook Endpoints** inline, add a new endpoint.
3. Enter the destination `url`.
4. Select one or more subscribed `events`.
5. Optionally add `custom_headers` as JSON.
6. Leave `secret` blank to auto-generate one, or paste your own shared secret.
7. Save the workflow.

You can also manage endpoints directly from **Admin → Webhook Endpoints** and inspect deliveries in **Admin → Webhook Delivery Logs**.

## Delivery behavior

- Deliveries are sent as `POST` requests with `Content-Type: application/json`.
- The request body is canonical JSON produced from the workflow event payload.
- A 2xx response is considered success.
- Non-2xx responses and transport exceptions are logged as failures.
- If retries are enabled, the system schedules retries with backoff up to `max_retries`.

## Request headers

Every request includes:

- `Content-Type: application/json`
- `User-Agent: django-forms-workflows/webhooks`
- `X-Forms-Workflows-Event: <event>`
- `X-Forms-Workflows-Signature: sha256=<hex digest>`

Any `custom_headers` configured on the endpoint are merged into the outbound request.

## Signature verification

The signature is computed as:

- algorithm: HMAC-SHA256
- key: `WebhookEndpoint.secret`
- message: raw JSON request body

Receiver flow:

1. read the raw request body exactly as sent
2. compute `HMAC_SHA256(secret, raw_body)`
3. compare it to `X-Forms-Workflows-Signature`
4. reject the request if they do not match

## Payload shape

Payloads share a consistent top-level structure:

- `event`
- `timestamp`
- `submission`
- `form`
- `submitter`
- `workflow`
- `task`
- `target_stage`

Notes:

- `task` is populated for `task.created` and send-back events tied to a specific approval task.
- `target_stage` is populated for `submission.returned` so receivers know where the submission was sent back.
- `workflow` identifies the specific workflow track that emitted the event.

### Example payload

```json
{
  "event": "task.created",
  "timestamp": "2026-04-01T06:20:00.000000+00:00",
  "submission": {"id": 42, "status": "pending_approval"},
  "form": {"id": 7, "name": "Travel Request", "slug": "travel-request"},
  "submitter": {"id": 3, "username": "alice", "email": "alice@example.com"},
  "workflow": {"id": 5, "name_label": "Finance Approval", "requires_approval": true},
  "task": {"id": 88, "status": "pending", "stage_number": 2, "step_name": "Finance Review"},
  "target_stage": null
}
```

Additional fields such as `created_at`, `submitted_at`, `completed_at`, assigned user/group, workflow-stage metadata, and approving user are included when available.

## Webhooks vs post-submission API actions

Use **workflow webhooks** when you need:

- one reusable event subscription per workflow
- standardized signed payloads
- event selection like `task.created` or `submission.returned`
- delivery audit logs in a dedicated model

Use **post-submission API actions** when you need:

- a one-off API call tied to `on_submit`, `on_approve`, `on_reject`, or `on_complete`
- templated request bodies specific to one integration
- ordered execution alongside database / LDAP / custom actions

## Cloning and sync behavior

- Cloning a form/workflow in admin also clones its webhook endpoints.
- Form sync export/import includes webhook endpoint definitions.

## Related docs

- [Workflows](WORKFLOWS.md)
- [Notifications](NOTIFICATIONS.md)
- [Post-Submission Actions](POST_SUBMISSION_ACTIONS.md)
- [Send Back for Correction](SEND_BACK.md)