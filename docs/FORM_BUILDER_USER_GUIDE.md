# Visual Form Builder - User Guide

## Introduction

The Visual Form Builder is a drag-and-drop interface that lets you create and edit forms without writing any code. This guide will walk you through using the builder to create your first form.

## Accessing the Form Builder

### For New Forms

1. Log in to Django Admin
2. Navigate to **Forms Workflows** → **Form Definitions**
3. Click **Add Form Definition** (top right)
4. Fill in basic form information
5. Click **Save** to create the form
6. Click **Open Visual Form Builder** button (top right)

### For Existing Forms

1. Log in to Django Admin
2. Navigate to **Forms Workflows** → **Form Definitions**
3. Click on the form you want to edit
4. Click **Open Visual Form Builder** button (top right)

OR

1. In the Form Definitions list view
2. Click the **Visual Builder** link in the row

## Understanding the Interface

The Form Builder has four main areas:

```
┌─────────────────────────────────────────────────────────┐
│                    Form Settings                         │
├──────────┬──────────────────────────┬───────────────────┤
│          │                          │                   │
│  Field   │      Form Canvas         │   Live Preview    │
│  Palette │                          │                   │
│          │                          │                   │
└──────────┴──────────────────────────┴───────────────────┘
│                    Save Bar                              │
└─────────────────────────────────────────────────────────┘
```

### 1. Form Settings (Top)

Configure basic form properties:
- **Form Name** - Display name (e.g., "Equipment Request")
- **Form Slug** - URL identifier (auto-generated from name)
- **Description** - Brief description shown to users
- **Instructions** - Detailed instructions at top of form
- **Active** - Whether form is visible to users
- **Requires Login** - Whether users must be logged in
- **Allow Save Draft** - Whether users can save incomplete forms
- **Allow Withdrawal** - Whether users can withdraw submissions

💡 **Tip:** The slug is auto-generated from the name. You can edit it if needed.

### 2. Field Palette (Left)

Drag field types from here to the canvas:

**Basic Fields:**
- 📝 Text Input - Single-line text
- 📧 Email - Email address with validation
- 🔢 Number - Numeric input
- 📄 Textarea - Multi-line text
- 📋 Select Dropdown - Choose one option
- ⚪ Radio Buttons - Choose one option (radio style)
- ☑️ Checkboxes - Choose multiple options
- ✅ Single Checkbox - Yes/No checkbox

**Advanced Fields:**
- 📅 Date - Date picker
- ⏰ Time - Time picker
- 📅⏰ Date & Time - Combined picker
- 📎 File Upload - Attach files
- 🔗 URL - Website address
- 📞 Phone Number - Phone with validation
- 💰 Decimal/Currency - Money amounts

**New Field Types:**
- ⭐ Rating - Star rating (1–N stars). Set *Max Value* to control the number of stars (default 5). The submitted value is stored as a number string.
- 🎚️ Slider - Range slider backed by a decimal field. Set *Min Value*, *Max Value*, and *Default Value* (step size). Rendered with a live value readout.
- 🏠 Address - Free-text address area (up to 500 characters). The JS enhancement layer splits it into labelled sub-inputs (Street, City, State, ZIP, Country) on the client side.
- 🔲 Matrix / Grid - Questionnaire-style grid. Provide *Choices* as JSON: `{"rows": ["Statement A", "Statement B"], "columns": ["Agree", "Neutral", "Disagree"]}`. Each row becomes a separate radio group. Falls back to a plain textarea when no rows/columns are configured.

**Layout:**
- 📑 Section Header - Visual separator

#### Palette Search

Type in the **search box** at the top of the palette to filter field types by name. The list updates instantly, making it easy to find a specific field type in large builders.

### 3. Form Canvas (Center)

This is where you build your form:
- **Drag fields** from the palette to add them
- **Drag fields** up/down to reorder
- **Click Edit** (pencil icon) to configure field
- **Click Delete** (trash icon) to remove field

The field count shows how many fields you've added.

### 4. Live Preview (Right)

See how your form will look to users. Updates automatically as you build.

### 5. Save Bar (Bottom)

- **Save Status** - Shows if you have unsaved changes
- **Cancel** - Discard changes and return to admin
- **Save Form** - Save your changes

## Creating Your First Form

Let's create a simple "Contact Request" form:

### Step 1: Configure Form Settings

1. Click the **Form Settings** header to expand (if collapsed)
2. Enter form details:
   - **Name:** Contact Request
   - **Slug:** contact-request (auto-filled)
   - **Description:** Submit a contact request to our team
   - **Instructions:** Please fill out all required fields
3. Leave checkboxes at default (all checked)

### Step 2: Add Fields

#### Add Name Field
1. Drag **Text Input** from palette to canvas
2. Click the **Edit** (pencil) button
3. Configure:
   - **Field Label:** Full Name
   - **Field Name:** full_name (auto-filled)
   - **Required:** ✓ (checked)
   - **Help Text:** Enter your first and last name
   - **Placeholder:** John Doe
   - **Width:** Full
4. Click **Save Field**

#### Add Email Field
1. Drag **Email** from palette to canvas
2. Click **Edit**
3. Configure:
   - **Field Label:** Email Address
   - **Field Name:** email
   - **Required:** ✓
   - **Help Text:** We'll use this to contact you
   - **Placeholder:** john@example.com
4. Click **Save Field**

#### Add Subject Field
1. Drag **Select Dropdown** from palette
2. Click **Edit**
3. Configure:
   - **Field Label:** Subject
   - **Field Name:** subject
   - **Required:** ✓
   - **Choices:** (one per line)
     ```
     General Inquiry
     Technical Support
     Sales Question
     Feedback
     Other
     ```
4. Click **Save Field**

#### Add Message Field
1. Drag **Textarea** from palette
2. Click **Edit**
3. Configure:
   - **Field Label:** Message
   - **Field Name:** message
   - **Required:** ✓
   - **Help Text:** Please provide details about your request
   - **Placeholder:** Type your message here...
4. Click **Save Field**

### Step 3: Save the Form

1. Click **Save Form** button (bottom right)
2. Wait for "Saved successfully" message
3. Your form is now ready to use!

## Advanced Features

### Reordering Fields

Simply drag fields up or down in the canvas to change their order.

### Field Width Options

Control how much horizontal space a field takes:
- **Full** - 100% width (default)
- **Half** - 50% width (two fields per row)
- **Third** - 33% width (three fields per row)

💡 **Tip:** Use Half or Third width for short fields like "First Name" and "Last Name"

### Prefill Sources

Automatically populate fields with data:

1. In field properties, find **Prefill Source**
2. Select a source from dropdown:
   - Current User - Email
   - Current User - First Name
   - Current User - Last Name
   - LDAP - Department
   - Database - Employee ID
   - (and more...)
3. The field will auto-fill when users open the form

### Section Headers

Organize long forms into sections:

1. Drag **Section Header** from palette
2. Edit the field label to set section title
3. Fields below it will appear under that section

Example:
```
Section: Personal Information
  - First Name
  - Last Name
  - Email

Section: Request Details
  - Subject
  - Message
```

### CSS Classes

Add custom styling to fields:

1. In field properties, find **CSS Class**
2. Enter Bootstrap classes or custom classes:
   - `text-uppercase` - Force uppercase
   - `text-danger` - Red text
   - `bg-light` - Light background
   - Your custom classes

## Submission Controls

The **Submission Controls** panel in Form Settings lets you restrict who can submit and when:

| Setting | Description |
|---------|-------------|
| **Close Date** | Forms stop accepting new submissions at this date/time. Submitters see an error message and are redirected. Leave blank for no deadline. |
| **Max Submissions** | Total cap on non-draft submissions across all users. Leave blank for unlimited. |
| **One Submission Per User** | When checked, each authenticated user may submit only once. Draft and withdrawn submissions do not count. |

These controls are enforced at the view layer on both GET (form load) and POST (submission attempt).

## Success Page Settings

The **Success Page** panel in Form Settings controls what happens after a form is submitted. Settings are evaluated in the following order of priority:

1. **Conditional redirect rules** — JSON array evaluated in order; first match wins
2. **Redirect URL** — Static URL (overrides success message if set)
3. **Success message** — Custom HTML rendered on the built-in `/submissions/<id>/success/` page
4. **Default** — Authenticated users go to My Submissions; anonymous users see the public confirmation page

### Redirect URL

Enter any absolute URL. Answer piping tokens are supported:

```
https://portal.example.com/thanks/?name={full_name}&dept={department}
```

### Conditional Redirect Rules

JSON array of rules. Each rule has a `url` key plus condition fields:

```json
[
  {
    "url": "https://hr.example.com/onboarding/",
    "field": "department",
    "operator": "equals",
    "value": "HR"
  },
  {
    "url": "https://finance.example.com/approval/",
    "field": "amount",
    "operator": "greater_than",
    "value": "10000"
  }
]
```

The first rule whose condition matches redirects the user. If no rule matches, the Redirect URL or success message is used.

### Success Message

An HTML snippet with optional **answer piping** tokens (`{field_name}`). Tokens are replaced server-side with the submitted values. Unknown tokens become empty strings.

```html
<p>Thanks, {full_name}! Your <strong>{department}</strong> request has been submitted.</p>
<p>We'll contact you at {email} within 3 business days.</p>
```

See [Post-Submission Actions — Answer Piping](POST_SUBMISSION_ACTIONS.md#answer-piping) for the full reference.

### CAPTCHA

Enable the **CAPTCHA** toggle to require human verification before submission. The JS layer renders the CAPTCHA widget (Google reCAPTCHA v2/v3 or hCaptcha, detected automatically from your page's script tags). Configure `FORMS_WORKFLOWS_CAPTCHA_SECRET_KEY` and optionally `FORMS_WORKFLOWS_CAPTCHA_VERIFY_URL` in your Django settings.

---

## Tips & Best Practices

### 1. Use Clear Labels
✅ Good: "Email Address"
❌ Bad: "Email"

### 2. Add Help Text
Help users understand what to enter:
```
Field Label: Phone Number
Help Text: Include area code (e.g., 555-123-4567)
```

### 3. Use Placeholders
Show examples of valid input:
```
Field Label: Website
Placeholder: https://www.example.com
```

### 4. Group Related Fields
Use section headers to organize:
```
Section: Contact Information
  - Name
  - Email
  - Phone

Section: Request Details
  - Subject
  - Message
```

### 5. Mark Required Fields
Only mark fields as required if they're truly necessary.

### 6. Test Your Form
After saving:
1. Go to the form submission page
2. Fill it out as a user would
3. Check for any issues
4. Return to builder to fix

### 7. Save Frequently
Click **Save Form** regularly to avoid losing work.

## Keyboard Shortcuts

(Coming soon in future update)

## Troubleshooting

### Form Won't Save
- Check that **Form Name** and **Slug** are filled in
- Check browser console for errors
- Try refreshing the page and trying again

### Field Won't Delete
- Make sure you clicked the trash icon
- Confirm the deletion in the popup
- If stuck, refresh the page

### Preview Not Updating
- Preview updates automatically
- If stuck, try saving the form
- Refresh the page if needed

### Can't Find Form Builder Button
- Make sure you're logged in as staff/admin
- Save the form first (for new forms)
- Check that you're on the Form Definition page

## Getting Help

- 📖 [Full Documentation](https://django-forms-workflows.readthedocs.io/)
- 💬 [Community Discussions](https://github.com/opensensor/django-forms-workflows/discussions)
- 🐛 [Report Issues](https://github.com/opensensor/django-forms-workflows/issues)

## What's Next?

After creating your form:

1. **Configure Workflow** - Set up approval process
   - Go to **Workflow Definitions**
   - Create workflow for your form
   - Configure approvers and logic

2. **Set Permissions** - Control who can submit
   - Edit form in admin
   - Set **Submit Groups**, **View Groups**, **Admin Groups**

3. **Add Post-Submission Actions** - Automate tasks
   - Go to **Post Submission Actions**
   - Configure database updates, API calls, etc.

4. **Test the Form** - Submit a test
   - Go to form submission page
   - Fill out and submit
   - Check approval workflow

5. **Share with Users** - Publish the form
   - Share the form URL
   - Add to your navigation
   - Train users if needed

## Feedback

We'd love to hear your feedback on the Visual Form Builder!

- What features would you like to see?
- What's confusing or difficult?
- What works well?

Share your thoughts in our [GitHub Discussions](https://github.com/opensensor/django-forms-workflows/discussions).

