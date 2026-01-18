# Django Forms Workflows - Demo Script

## 🎬 Demo Overview

**Duration:** 8-10 minutes  
**Audience:** Django developers, enterprise teams  
**Goal:** Showcase the power of database-driven forms with approval workflows and external data integration

---

## 🎯 Demo Scenario: Farm Management System

**Story:** A farm cooperative needs to manage equipment requests with approval workflows and integrate with their existing systems.

---

## 📋 Pre-Demo Setup Checklist

### Environment Setup
```bash
# 1. Clone and setup
git clone https://github.com/opensensor/django-forms-workflows.git
cd django-forms-workflows/example_project

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -e ..

# 4. Setup database
python manage.py migrate

# 5. Load demo data
python manage.py seed_farm_demo

# 6. Create superuser (if not created by seed)
python manage.py createsuperuser
# Username: admin
# Email: admin@example.com
# Password: admin123

# 7. Start server
python manage.py runserver
```

### Browser Setup
- Open two browser windows/profiles:
  - **Window 1:** Admin user (admin@example.com)
  - **Window 2:** Regular user (farmer@example.com / password: demo123)
- Clear browser cache
- Zoom to 125% for better visibility in recording

### Screen Recording Setup
- Resolution: 1920x1080 or 1280x720
- Frame rate: 30fps
- Audio: Clear microphone, minimal background noise
- Close unnecessary applications
- Hide desktop clutter

---

## 🎬 Demo Script

### INTRO (30 seconds)

**[Screen: GitHub repo page]**

> "Hi! Today I'm going to show you Django Forms Workflows - an enterprise-grade, database-driven form builder with approval workflows and external data integration."

**[Screen: README.md features section]**

> "Unlike traditional form builders, everything here is database-driven. You can create complex forms, define multi-step approval workflows, and integrate with external systems - all through Django's admin interface, no code required."

---

### PART 1: Admin Interface Tour (2 minutes)

**[Screen: Login to Django admin as admin]**

> "Let me show you the admin interface. I'm logging in as an administrator."

**[Navigate to: Django Forms Workflows section]**

> "Here's our main dashboard. Notice we have several key components:"

**[Click through each model briefly]**

1. **Form Definitions**
   > "Form Definitions - where we design our forms"

2. **Workflow Definitions**
   > "Workflow Definitions - where we set up approval chains"

3. **Prefill Sources**
   > "Prefill Sources - for pulling data from external systems"

4. **Post Submission Actions**
   > "Post Submission Actions - for pushing data back to external systems"

5. **Form Submissions**
   > "And Form Submissions - where we track everything"

---

### PART 2: Creating a Form (2 minutes)

**[Click: Form Definitions → Add Form Definition]**

> "Let's create a new form. I'll make an Equipment Request form."

**[Fill in form details]**
- **Name:** `Equipment Request`
- **Description:** `Request farm equipment for seasonal work`
- **Active:** ✓ Checked
- **Requires Approval:** ✓ Checked

**[Scroll to Form Fields section]**

> "Now I'll add some fields. Notice the variety of field types available."

**[Add Field 1]**
- **Field Name:** `equipment_type`
- **Field Label:** `Equipment Type`
- **Field Type:** `Select`
- **Choices:** `Tractor\nHarvester\nIrrigation System\nOther`
- **Required:** ✓ Checked
- **Order:** `1`

**[Add Field 2]**
- **Field Name:** `reason`
- **Field Label:** `Reason for Request`
- **Field Type:** `Textarea`
- **Required:** ✓ Checked
- **Order:** `2`

**[Add Field 3]**
- **Field Name:** `duration_days`
- **Field Label:** `Duration (days)`
- **Field Type:** `Number`
- **Required:** ✓ Checked
- **Order:** `3`

**[Save form]**

> "Great! Our form is created. Now let's set up an approval workflow."

---

### PART 3: Workflow Configuration (1.5 minutes)

**[Navigate to: Workflow Definitions → Add Workflow Definition]**

> "I'll create a simple two-step approval workflow."

**[Fill in workflow details]**
- **Name:** `Equipment Approval Workflow`
- **Description:** `Farm manager → Operations director`
- **Form Definition:** `Equipment Request`

**[Add Approval Step 1]**
- **Step Name:** `Farm Manager Review`
- **Step Order:** `1`
- **Assigned Group:** `Farm Managers`
- **Can Edit:** ✓ Checked

**[Add Approval Step 2]**
- **Step Name:** `Operations Director Approval`
- **Step Order:** `2`
- **Assigned Group:** `Directors`

**[Save workflow]**

> "Perfect! Now any equipment request will go through farm manager review, then director approval."

---

### PART 4: Prefill Sources Demo (1.5 minutes)

**[Navigate to: Prefill Sources]**

> "One of the most powerful features is automatic data prefilling. Let me show you the 'Farmer Contact Update' form that's already set up."

**[Click: Farmer Contact Update form in Form Definitions]**

> "This form has fields that automatically pull data from the user's profile."

**[Show prefill source configuration]**

**[Navigate to: Prefill Sources → View existing sources]**

> "Here you can see we have sources configured for:"
- User data (email, name)
- LDAP/Active Directory
- External databases
- APIs

> "When a user opens the form, these fields are automatically populated with their current information."

---

### PART 5: User Experience - Submitting a Form (2 minutes)

**[Switch to: Regular user browser window]**

**[Navigate to: http://localhost:8000/forms/]**

> "Now let's see this from a user's perspective. I'm logged in as a regular farmer."

**[Click: Available Forms]**

> "Here are all the forms I can access. Let me open the Farmer Contact Update form first."

**[Open: Farmer Contact Update]**

> "Notice how my email and name are already filled in! This is the prefill feature in action."

**[Update phone number, save]**

> "I'll just update my phone number and submit."

**[Navigate back, open: Equipment Request]**

> "Now let me submit an equipment request."

**[Fill out form]**
- **Equipment Type:** `Tractor`
- **Reason:** `Need to plow the north field for spring planting`
- **Duration:** `5`

**[Submit form]**

> "Submitted! Notice the confirmation message and the status showing it's pending approval."

---

### PART 6: Approval Workflow in Action (2 minutes)

**[Switch to: Admin browser window]**

**[Navigate to: Form Submissions]**

> "Back in the admin, I can see the new submission."

**[Click on the submission]**

> "Here's all the details, and notice the approval tasks section."

**[Navigate to: Approval Tasks]**

> "The system automatically created approval tasks. Let's see the farm manager's task."

**[Click: Farm Manager Review task]**

**[Show task details]**
- Status: Pending
- Assigned to: Farm Managers group
- Due date: Automatically calculated

**[Click: Approve button or change status to Approved]**

> "The farm manager approves it..."

**[Add comment]**
- **Comment:** `Approved - north field needs attention before planting season`

**[Save]**

> "And now it automatically moves to the next step - the Operations Director."

**[Show: New task created for Directors group]**

> "The workflow engine automatically created the next approval task."

---

### PART 7: Post-Submission Actions (1 minute)

**[Navigate to: Post Submission Actions]**

> "Here's another powerful feature - post-submission actions. You can configure the system to automatically:"

**[Show existing actions]**
- Update external databases
- Call APIs
- Update LDAP/Active Directory
- Send data to other systems

**[Click on an example action]**

> "For example, this action automatically updates our external HR database when a contact form is approved. No manual data entry needed!"

---

### PART 8: Reporting & Audit Trail (1 minute)

**[Navigate to: Audit Logs]**

> "Everything is tracked in the audit log."

**[Show recent logs]**

> "Every submission, approval, rejection, and data change is logged with:"
- Who did it
- When they did it
- What changed
- IP address

**[Navigate to: Form Submissions → Filter options]**

> "You can filter submissions by status, date, form type, submitter..."

**[Show filters]**

> "Making it easy to generate reports and track metrics."

---

### CLOSING (30 seconds)

**[Screen: GitHub repo page]**

> "So that's Django Forms Workflows! Let me recap the key features:"

**[Show README features list]**

1. ✅ Database-driven forms - no code needed
2. ✅ Multi-step approval workflows
3. ✅ External data integration (prefill & post-submission)
4. ✅ Complete audit trail
5. ✅ Farm-themed demo included
6. ✅ Enterprise-ready

> "It's available on PyPI - just `pip install django-forms-workflows` - and it's open source under LGPL-3.0."

**[Show installation command]**

```bash
pip install django-forms-workflows
```

> "Check out the GitHub repo for documentation, examples, and to contribute. Thanks for watching!"

**[Screen: GitHub repo star button]**

> "And if you found this useful, give us a star on GitHub!"

---

## 🎨 Demo Tips

### Visual Polish
- **Use browser zoom:** 125-150% for better visibility
- **Slow down mouse movements:** Easier to follow
- **Highlight with cursor:** Circle important elements
- **Use browser dev tools:** Show network requests for API calls
- **Terminal split-screen:** Show logs while using the app

### Narration Tips
- **Speak clearly and slowly:** Pause between sections
- **Explain "why" not just "what":** Context matters
- **Use real-world examples:** "Imagine you're a farm manager..."
- **Highlight pain points solved:** "No more manual data entry..."
- **Show enthusiasm:** Your energy is contagious!

### Common Mistakes to Avoid
- ❌ Going too fast
- ❌ Not explaining what you're clicking
- ❌ Assuming knowledge (explain Django admin, etc.)
- ❌ Skipping error handling (show what happens if validation fails)
- ❌ Not showing the "why" - always explain the business value

### Advanced Demo Ideas

#### Show Error Handling
- Submit form with missing required fields
- Show validation messages
- Demonstrate field-level validation

#### Show Conditional Logic
- Create a field that only shows based on another field's value
- Use the `show_if_field` and `show_if_value` features

#### Show Email Notifications
- Configure email settings
- Show approval notification emails
- Demonstrate escalation emails

#### Show API Integration
- Configure a post-submission action to call an API
- Show the request/response in browser dev tools
- Demonstrate error handling

---

## 📊 Alternative Demo Formats

### Quick Demo (3 minutes)
1. Show admin interface (30s)
2. Submit a form as user (1m)
3. Approve as admin (1m)
4. Show audit log (30s)

### Technical Deep Dive (15 minutes)
- Code walkthrough
- Database schema explanation
- Architecture overview
- Customization examples
- Integration patterns

### Sales/Business Demo (5 minutes)
- Focus on business value
- ROI discussion
- Comparison with alternatives
- Use case examples
- Pricing (it's free!)

---

## 🎥 Post-Production Checklist

- [ ] Add intro title card (3-5 seconds)
- [ ] Add chapter markers in video description
- [ ] Add background music (low volume, non-distracting)
- [ ] Add text overlays for key points
- [ ] Add zoom-in effects for important UI elements
- [ ] Add outro with links (GitHub, PyPI, docs)
- [ ] Export in multiple resolutions (1080p, 720p, 480p)
- [ ] Add captions/subtitles
- [ ] Create thumbnail with clear text
- [ ] Write compelling video description with timestamps

---

## 📝 Video Description Template

```
Django Forms Workflows - Enterprise Form Builder with Approval Workflows

Create database-driven forms with multi-step approval workflows and external 
data integration - all through Django's admin interface, no code required!

⏱️ TIMESTAMPS:
0:00 - Introduction
0:30 - Admin Interface Tour
2:30 - Creating a Form
4:00 - Workflow Configuration
5:30 - Prefill Sources Demo
7:00 - User Experience
9:00 - Approval Workflow
11:00 - Post-Submission Actions
12:00 - Reporting & Audit Trail
12:30 - Closing

🔗 LINKS:
GitHub: https://github.com/opensensor/django-forms-workflows
PyPI: https://pypi.org/project/django-forms-workflows/
Documentation: [Add docs link]

📦 INSTALLATION:
pip install django-forms-workflows

✨ KEY FEATURES:
✅ Database-driven forms
✅ Multi-step approval workflows
✅ External data integration
✅ Complete audit trail
✅ Farm-themed demo
✅ Enterprise-ready

#Django #Python #WebDevelopment #OpenSource #FormBuilder
```

---

## 🚀 Ready to Record!

Good luck with your demo! Remember:
- **Practice first** - Do a dry run
- **Check audio levels** - Test your microphone
- **Close notifications** - Enable Do Not Disturb
- **Have fun!** - Your enthusiasm shows

If you need any adjustments to the script or want to focus on specific features, let me know!

