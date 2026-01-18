# Demo Quick Reference Card

## 🎬 Keep This Open During Recording!

---

## ⏱️ Timeline (10 min total)

| Time | Section | Key Points |
|------|---------|------------|
| 0:00-0:30 | Intro | What is it? Why use it? |
| 0:30-2:30 | Admin Tour | Show all models, explain purpose |
| 2:30-4:00 | Create Form | Add 3 fields, make it visual |
| 4:00-5:30 | Workflow | 2-step approval, explain flow |
| 5:30-7:00 | Prefill Demo | Show auto-population magic |
| 7:00-9:00 | User Submit | Fill form, submit, show status |
| 9:00-11:00 | Approval | Approve as manager, show next step |
| 11:00-12:00 | Post-Actions | Show external integrations |
| 12:00-12:30 | Audit & Close | Logs, filters, call-to-action |

---

## 🔑 Key Talking Points

### Opening Hook
> "Database-driven forms with approval workflows - all through Django admin, no code required!"

### Main Value Props
1. **No Code Required** - Everything in admin interface
2. **External Integration** - Pull and push data automatically
3. **Complete Audit Trail** - Track everything
4. **Enterprise Ready** - Multi-step approvals, permissions

### Closing CTA
> "pip install django-forms-workflows - Star us on GitHub!"

---

## 👤 Demo Users

| Username | Password | Role | Use For |
|----------|----------|------|---------|
| admin | admin123 | Superuser | Admin tasks, approvals |
| farmer@example.com | demo123 | Farmer | Form submission |
| manager@example.com | demo123 | Manager | First approval |
| director@example.com | demo123 | Director | Final approval |

---

## 📋 Form to Create: "Equipment Request"

```
Field 1:
  Name: equipment_type
  Label: Equipment Type
  Type: Select
  Choices: Tractor\nHarvester\nIrrigation System\nOther
  Required: ✓
  Order: 1

Field 2:
  Name: reason
  Label: Reason for Request
  Type: Textarea
  Required: ✓
  Order: 2

Field 3:
  Name: duration_days
  Label: Duration (days)
  Type: Number
  Required: ✓
  Order: 3
```

---

## 🔄 Workflow to Create: "Equipment Approval"

```
Workflow Name: Equipment Approval Workflow
Description: Farm manager → Operations director
Form: Equipment Request

Step 1:
  Name: Farm Manager Review
  Order: 1
  Group: Farm Managers
  Can Edit: ✓

Step 2:
  Name: Operations Director Approval
  Order: 2
  Group: Directors
  Can Edit: ✗
```

---

## 💬 Sample Submission Data

```
Equipment Type: Tractor
Reason: Need to plow the north field for spring planting
Duration: 5 days
```

**Approval Comment:**
> "Approved - north field needs attention before planting season"

---

## 🎯 Don't Forget to Show

- ✅ Form field validation (try submitting empty form)
- ✅ Prefill in action (Farmer Contact Update form)
- ✅ Approval task creation (automatic)
- ✅ Audit log entries (who, what, when)
- ✅ Filter options (status, date, user)
- ✅ Post-submission actions (external integration)

---

## 🎨 Visual Tips

- **Zoom browser to 125%** for visibility
- **Slow down mouse movements**
- **Pause after each click** (let UI load)
- **Highlight with cursor** (circle important items)
- **Read aloud what you're clicking**

---

## 🗣️ Narration Reminders

- **Speak slowly and clearly**
- **Explain WHY, not just WHAT**
- **Use real-world context** ("Imagine you're a farm manager...")
- **Show enthusiasm!**
- **Pause between sections** (easier to edit)

---

## 🚨 Common Mistakes to Avoid

- ❌ Going too fast
- ❌ Not explaining clicks
- ❌ Assuming Django knowledge
- ❌ Forgetting to save forms
- ❌ Not showing validation errors
- ❌ Skipping the "why it matters"

---

## 🔧 Troubleshooting

### If form doesn't show up:
- Check "Active" is checked
- Refresh the forms list page

### If approval doesn't work:
- Check user is in correct group
- Check workflow is assigned to form

### If prefill doesn't work:
- Check prefill source is active
- Check source_key matches field name

---

## 📱 URLs to Have Ready

```
Admin: http://localhost:8000/admin/
Forms List: http://localhost:8000/forms/
GitHub: https://github.com/opensensor/django-forms-workflows
PyPI: https://pypi.org/project/django-forms-workflows/
```

---

## 🎬 Recording Checklist

**Before Recording:**
- [ ] Close all unnecessary apps
- [ ] Enable Do Not Disturb
- [ ] Clear browser cache
- [ ] Test microphone levels
- [ ] Check screen resolution (1920x1080)
- [ ] Have water nearby
- [ ] Practice run-through once

**During Recording:**
- [ ] Speak clearly and slowly
- [ ] Pause between sections
- [ ] Show, don't just tell
- [ ] Smile (it shows in your voice!)

**After Recording:**
- [ ] Review for mistakes
- [ ] Check audio quality
- [ ] Add chapter markers
- [ ] Create thumbnail
- [ ] Write description with timestamps

---

## 💡 Pro Tips

1. **Record in segments** - Easier to fix mistakes
2. **Use two monitors** - Script on one, demo on other
3. **Have backup plan** - If something breaks, have alternative
4. **Test everything first** - Do a complete dry run
5. **Keep it real** - Small mistakes are okay, shows it's authentic

---

## 🎯 Success Metrics

After publishing, track:
- Views in first 24 hours
- Average watch time (aim for >60%)
- Click-through to GitHub
- GitHub stars increase
- PyPI downloads increase

---

## 📞 Emergency Contacts

If you need help during demo:
- Django docs: https://docs.djangoproject.com/
- Project README: Check local README.md
- Example project: Check example_project/settings.py

---

## 🎉 You've Got This!

Remember: You're showing off something awesome that you built. Be proud, be enthusiastic, and have fun!

**Final check before hitting record:**
- ✅ Server running?
- ✅ Demo data loaded?
- ✅ Browser windows ready?
- ✅ Microphone working?
- ✅ Screen recording software ready?

**GO TIME! 🚀**

