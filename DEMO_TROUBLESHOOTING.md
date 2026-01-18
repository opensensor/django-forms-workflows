# Demo Troubleshooting Guide

## 🚨 Quick Fixes for Common Demo Issues

---

## Database Issues

### Problem: "No such table" error
```bash
# Solution: Run migrations
python manage.py migrate
```

### Problem: Demo data not showing
```bash
# Solution: Re-run seed command
python manage.py seed_farm_demo

# Or start fresh:
rm db.sqlite3
python manage.py migrate
python manage.py seed_farm_demo
```

### Problem: Can't login as admin
```bash
# Solution: Create superuser
python manage.py createsuperuser
# Username: admin
# Email: admin@example.com
# Password: admin123
```

---

## Form Issues

### Problem: Form doesn't appear in forms list
**Checklist:**
- [ ] Is "Active" checked in Form Definition?
- [ ] Did you save the form?
- [ ] Refresh the page (Ctrl+F5)
- [ ] Check user has permission to view form

**Quick Fix:**
```python
# In Django admin, check Form Definition:
Active: ✓ (must be checked)
```

### Problem: Form fields not showing
**Checklist:**
- [ ] Did you add fields to the form?
- [ ] Are fields marked as active?
- [ ] Check field order numbers
- [ ] Save the form definition

### Problem: Prefill not working
**Checklist:**
- [ ] Is Prefill Source active?
- [ ] Does source_key match field name exactly?
- [ ] Is user logged in?
- [ ] Check user profile has data

**Debug:**
```python
# Check in Django shell:
python manage.py shell

from django.contrib.auth.models import User
user = User.objects.get(username='farmer@example.com')
print(user.email)  # Should show email
print(user.first_name)  # Should show name
```

---

## Workflow Issues

### Problem: Approval task not created
**Checklist:**
- [ ] Is workflow assigned to the form?
- [ ] Is "Requires Approval" checked on form?
- [ ] Are approval steps configured?
- [ ] Are groups created and assigned?

**Quick Fix:**
```python
# Check in admin:
Form Definition → Requires Approval: ✓
Workflow Definition → Form Definition: [Select your form]
Approval Steps → At least one step configured
```

### Problem: Can't approve task
**Checklist:**
- [ ] Is user in the assigned group?
- [ ] Is task status "Pending"?
- [ ] Is it the current step in workflow?

**Quick Fix:**
```python
# Add user to group in admin:
Users → [Select user] → Groups → Add to correct group
```

### Problem: Workflow stuck on one step
**Checklist:**
- [ ] Was previous step approved?
- [ ] Check approval task status
- [ ] Verify step order numbers are sequential

---

## Server Issues

### Problem: Server won't start
```bash
# Check if port 8000 is in use:
lsof -i :8000  # Mac/Linux
netstat -ano | findstr :8000  # Windows

# Kill the process or use different port:
python manage.py runserver 8001
```

### Problem: Static files not loading
```bash
# Collect static files:
python manage.py collectstatic --noinput

# Or in development, make sure DEBUG=True in settings.py
```

### Problem: CSS/styling broken
**Quick Fix:**
```bash
# Clear browser cache: Ctrl+Shift+Delete
# Or hard refresh: Ctrl+F5 (Cmd+Shift+R on Mac)
```

---

## User/Authentication Issues

### Problem: Can't login
**Checklist:**
- [ ] Username is email address (farmer@example.com)
- [ ] Password is correct (demo123 for demo users)
- [ ] User account is active

**Reset password:**
```bash
python manage.py shell

from django.contrib.auth.models import User
user = User.objects.get(username='farmer@example.com')
user.set_password('demo123')
user.save()
```

### Problem: User doesn't have permissions
```bash
# Make user superuser:
python manage.py shell

from django.contrib.auth.models import User
user = User.objects.get(username='admin')
user.is_superuser = True
user.is_staff = True
user.save()
```

---

## Recording Issues

### Problem: Screen recording laggy
**Solutions:**
- Close unnecessary applications
- Lower screen resolution to 1280x720
- Reduce browser zoom to 100%
- Close browser tabs you're not using
- Disable browser extensions
- Use hardware encoding if available

### Problem: Audio quality poor
**Solutions:**
- Move closer to microphone
- Reduce background noise
- Use headphones to prevent echo
- Test audio levels before recording
- Record in a quiet room
- Use a pop filter if available

### Problem: Mouse cursor not visible
**Solutions:**
- Enable cursor highlighting in recording software
- Use larger cursor size (System Preferences)
- Move mouse slower
- Use cursor highlighting tools (e.g., PointerFocus)

---

## Browser Issues

### Problem: Browser window too small
```
Recommended settings:
- Resolution: 1920x1080 or 1280x720
- Browser zoom: 125-150%
- Hide bookmarks bar
- Use full screen mode (F11)
```

### Problem: Forms not submitting
**Checklist:**
- [ ] Check browser console for errors (F12)
- [ ] Disable browser extensions
- [ ] Try different browser
- [ ] Clear cookies and cache

---

## Demo Data Issues

### Problem: Wrong demo data showing
```bash
# Reset demo data:
python manage.py flush  # WARNING: Deletes all data!
python manage.py migrate
python manage.py seed_farm_demo
```

### Problem: Need to add more demo users
```bash
python manage.py shell

from django.contrib.auth.models import User, Group

# Create new user
user = User.objects.create_user(
    username='newuser@example.com',
    email='newuser@example.com',
    password='demo123',
    first_name='New',
    last_name='User'
)

# Add to group
group = Group.objects.get(name='Farmers')
user.groups.add(group)
```

---

## Performance Issues

### Problem: Admin interface slow
**Solutions:**
- Reduce number of inline forms
- Use `list_select_related` in admin
- Add database indexes
- Use pagination

### Problem: Forms loading slowly
**Solutions:**
- Reduce number of prefill sources
- Cache prefill data
- Optimize database queries
- Use select_related/prefetch_related

---

## Emergency Reset

### Nuclear Option: Start Completely Fresh
```bash
# WARNING: This deletes everything!

# 1. Stop server (Ctrl+C)

# 2. Delete database
rm db.sqlite3

# 3. Delete migrations (optional, if really broken)
find . -path "*/migrations/*.py" -not -name "__init__.py" -delete
find . -path "*/migrations/*.pyc" -delete

# 4. Recreate everything
python manage.py makemigrations
python manage.py migrate
python manage.py seed_farm_demo
python manage.py createsuperuser

# 5. Restart server
python manage.py runserver
```

---

## Pre-Demo Verification Script

Run this before starting your demo:

```bash
#!/bin/bash
# demo_check.sh

echo "🔍 Checking demo environment..."

# Check if server is running
if curl -s http://localhost:8000 > /dev/null; then
    echo "✅ Server is running"
else
    echo "❌ Server is NOT running - start with: python manage.py runserver"
    exit 1
fi

# Check if admin user exists
python manage.py shell -c "
from django.contrib.auth.models import User
try:
    User.objects.get(username='admin')
    print('✅ Admin user exists')
except:
    print('❌ Admin user missing - create with: python manage.py createsuperuser')
"

# Check if demo data exists
python manage.py shell -c "
from django_forms_workflows.models import FormDefinition
count = FormDefinition.objects.count()
if count > 0:
    print(f'✅ Demo data loaded ({count} forms)')
else:
    print('❌ No demo data - run: python manage.py seed_farm_demo')
"

echo "✅ Demo environment ready!"
```

---

## During-Demo Fixes

### If something breaks during recording:

1. **Don't panic!** Take a breath
2. **Pause recording** if possible
3. **Check this guide** for quick fix
4. **If quick fix available:** Fix and continue
5. **If no quick fix:** Say "Let me show you something else..." and move on
6. **Edit it out later** in post-production

### Smooth Recovery Phrases:

> "Let me refresh this page..."
> "While that's loading, let me show you..."
> "Here's another interesting feature..."
> "Let me demonstrate this a different way..."

---

## Post-Demo Checklist

After recording, verify:
- [ ] Audio is clear throughout
- [ ] No personal information visible
- [ ] All features demonstrated work
- [ ] No long awkward pauses
- [ ] Cursor is visible
- [ ] Text is readable
- [ ] No notification popups

---

## Contact for Help

If you're really stuck:

1. **Check Django docs:** https://docs.djangoproject.com/
2. **Check project README:** Local README.md file
3. **Check example settings:** example_project/settings.py
4. **Django shell debugging:**
   ```bash
   python manage.py shell
   # Import and inspect models
   ```

---

## Remember

- **Most issues are simple** - usually just need to refresh or restart
- **Have a backup plan** - Know what to skip if something breaks
- **Practice makes perfect** - Do a dry run first
- **It's okay to make mistakes** - Shows it's authentic
- **You can edit later** - Don't stress about perfection

---

## 🎬 Good Luck!

You've got this! The demo script is solid, the app works great, and you know your stuff. Just breathe, smile, and show off what you've built!

**Quick Pre-Recording Mantra:**
> "Server running? ✓"
> "Demo data loaded? ✓"
> "Users working? ✓"
> "I've got this! ✓"

**Now go make an awesome demo! 🚀**

