# 📋 Demo Recording Checklist

**Print this out and check off items as you go!**

---

## 🎯 Pre-Recording Setup (30 minutes before)

### Environment Setup
- [ ] Virtual environment activated
- [ ] Dependencies installed (`pip install -e ..`)
- [ ] Database migrated (`python manage.py migrate`)
- [ ] Demo data loaded (`python manage.py seed_farm_demo`)
- [ ] Superuser created (admin/admin123)
- [ ] Server running (`python manage.py runserver`)
- [ ] Server accessible at http://localhost:8000

### Browser Setup
- [ ] Two browser windows/profiles open
  - [ ] Window 1: Logged in as admin
  - [ ] Window 2: Logged in as farmer@example.com
- [ ] Browser zoom set to 125%
- [ ] Bookmarks bar hidden
- [ ] Browser cache cleared
- [ ] All unnecessary tabs closed
- [ ] Browser extensions disabled (or use incognito)

### Computer Setup
- [ ] Screen resolution: 1920x1080 or 1280x720
- [ ] All unnecessary applications closed
- [ ] Notifications disabled (Do Not Disturb mode)
- [ ] Desktop clean (hide personal files)
- [ ] Adequate lighting (if showing face)
- [ ] Quiet environment (close windows, turn off fans)

### Recording Software
- [ ] Recording software open and tested
- [ ] Frame rate: 30fps
- [ ] Audio input selected (microphone)
- [ ] Audio levels tested (not too quiet, not clipping)
- [ ] Cursor highlighting enabled (if available)
- [ ] Recording area selected (full screen or window)
- [ ] Output folder selected (enough disk space)

### Reference Materials
- [ ] DEMO_SCRIPT.md open on second monitor
- [ ] DEMO_QUICK_REFERENCE.md printed or on tablet
- [ ] DEMO_TROUBLESHOOTING.md accessible
- [ ] Water/beverage nearby
- [ ] Phone on silent

---

## ✅ Final Pre-Recording Check (5 minutes before)

### Technical Verification
- [ ] Visit http://localhost:8000/admin/ - loads correctly
- [ ] Visit http://localhost:8000/forms/ - loads correctly
- [ ] Login as admin works
- [ ] Login as farmer@example.com works
- [ ] At least 2 forms visible in forms list
- [ ] Can create a test form in admin
- [ ] Can submit a test form as user

### Audio/Video Test
- [ ] Record 30 seconds of test footage
- [ ] Play back test recording
- [ ] Audio is clear and loud enough
- [ ] Video is smooth (no lag)
- [ ] Cursor is visible
- [ ] Text is readable
- [ ] No background noise

### Personal Readiness
- [ ] Comfortable seating position
- [ ] Good posture
- [ ] Relaxed and ready
- [ ] Script reviewed one more time
- [ ] Know your opening line
- [ ] Know your closing line

---

## 🎬 Recording Checklist

### During Recording
- [ ] Speak slowly and clearly
- [ ] Pause between sections (easier to edit)
- [ ] Explain what you're clicking before clicking
- [ ] Show, don't just tell
- [ ] Smile (it shows in your voice!)
- [ ] If you make a mistake, pause and restart that section

### Sections to Record (check off as completed)

#### Part 1: Introduction (0:00-0:30)
- [ ] Show GitHub repo page
- [ ] Explain what django-forms-workflows is
- [ ] Mention key features
- [ ] Set expectations for demo

#### Part 2: Admin Interface Tour (0:30-2:30)
- [ ] Login to admin
- [ ] Show Form Definitions
- [ ] Show Workflow Definitions
- [ ] Show Prefill Sources
- [ ] Show Post Submission Actions
- [ ] Show Form Submissions

#### Part 3: Creating a Form (2:30-4:00)
- [ ] Click "Add Form Definition"
- [ ] Fill in form name and description
- [ ] Add equipment_type field (Select)
- [ ] Add reason field (Textarea)
- [ ] Add duration_days field (Number)
- [ ] Save form

#### Part 4: Workflow Configuration (4:00-5:30)
- [ ] Click "Add Workflow Definition"
- [ ] Fill in workflow name
- [ ] Select form
- [ ] Add Step 1: Farm Manager Review
- [ ] Add Step 2: Operations Director Approval
- [ ] Save workflow

#### Part 5: Prefill Sources Demo (5:30-7:00)
- [ ] Navigate to Prefill Sources
- [ ] Show existing sources
- [ ] Explain different source types
- [ ] Show Farmer Contact Update form
- [ ] Explain how prefill works

#### Part 6: User Experience (7:00-9:00)
- [ ] Switch to user browser window
- [ ] Show forms list
- [ ] Open Farmer Contact Update form
- [ ] Show prefilled data
- [ ] Update and submit
- [ ] Open Equipment Request form
- [ ] Fill out form
- [ ] Submit form
- [ ] Show confirmation

#### Part 7: Approval Workflow (9:00-11:00)
- [ ] Switch to admin window
- [ ] Navigate to Form Submissions
- [ ] Click on new submission
- [ ] Show submission details
- [ ] Navigate to Approval Tasks
- [ ] Show pending task
- [ ] Approve task with comment
- [ ] Show next task created

#### Part 8: Post-Submission Actions (11:00-12:00)
- [ ] Navigate to Post Submission Actions
- [ ] Show example actions
- [ ] Explain database updates
- [ ] Explain API calls
- [ ] Explain LDAP updates

#### Part 9: Reporting & Audit (12:00-12:30)
- [ ] Navigate to Audit Logs
- [ ] Show recent logs
- [ ] Explain what's tracked
- [ ] Show filter options
- [ ] Demonstrate filtering

#### Part 10: Closing (12:30-13:00)
- [ ] Show GitHub repo page
- [ ] Recap key features
- [ ] Show installation command
- [ ] Call to action (star on GitHub)
- [ ] Thank viewers

---

## 📝 Post-Recording Checklist

### Immediate Review
- [ ] Watch entire recording
- [ ] Check audio quality throughout
- [ ] Check video quality throughout
- [ ] Note any sections that need re-recording
- [ ] Verify no personal information visible
- [ ] Verify no sensitive data shown

### Re-Recording (if needed)
- [ ] List sections that need re-recording:
  - [ ] _______________________
  - [ ] _______________________
  - [ ] _______________________
- [ ] Re-record problem sections
- [ ] Verify re-recorded sections are better

### Editing Checklist
- [ ] Import footage into editor
- [ ] Cut out long pauses
- [ ] Cut out mistakes/restarts
- [ ] Add intro title card (3-5 seconds)
- [ ] Add outro with links (5-10 seconds)
- [ ] Add chapter markers
- [ ] Add text overlays for key points
- [ ] Add zoom effects for important UI elements
- [ ] Adjust audio levels (normalize)
- [ ] Add background music (low volume)
- [ ] Add transitions between sections
- [ ] Color correction (if needed)

### Export Settings
- [ ] Export in 1080p (1920x1080)
- [ ] Export in 720p (1280x720) - optional
- [ ] Frame rate: 30fps
- [ ] Format: MP4 (H.264)
- [ ] Audio: AAC, 128kbps or higher
- [ ] Bitrate: 8-12 Mbps for 1080p

### Thumbnail Creation
- [ ] Create custom thumbnail
- [ ] Use clear, readable text
- [ ] Use high contrast colors
- [ ] Include project logo/name
- [ ] Size: 1280x720 pixels
- [ ] Format: JPG or PNG
- [ ] File size: Under 2MB

### Video Description
- [ ] Write compelling title
- [ ] Write detailed description
- [ ] Add timestamps for all sections
- [ ] Add links (GitHub, PyPI, docs)
- [ ] Add installation instructions
- [ ] Add key features list
- [ ] Add relevant hashtags
- [ ] Add contact information

### Captions/Subtitles
- [ ] Auto-generate captions
- [ ] Review and correct captions
- [ ] Export SRT file
- [ ] Upload captions with video

---

## 🚀 Publishing Checklist

### YouTube (if applicable)
- [ ] Upload video
- [ ] Add title
- [ ] Add description with timestamps
- [ ] Add thumbnail
- [ ] Add to playlist
- [ ] Set visibility (Public/Unlisted)
- [ ] Add end screen elements
- [ ] Add cards for links
- [ ] Add to relevant playlists
- [ ] Set category (Science & Technology)
- [ ] Add tags

### GitHub
- [ ] Add video link to README.md
- [ ] Create release announcement
- [ ] Post in Discussions (if enabled)
- [ ] Update documentation with video link

### Social Media
- [ ] Tweet about video
- [ ] Post on LinkedIn
- [ ] Post on Reddit (r/django, r/Python)
- [ ] Post on Dev.to
- [ ] Post on Hacker News (if appropriate)

### Documentation
- [ ] Add video to docs site
- [ ] Update README with video embed
- [ ] Add to project homepage

---

## 📊 Post-Launch Monitoring

### First 24 Hours
- [ ] Monitor view count
- [ ] Respond to comments
- [ ] Check for technical issues reported
- [ ] Track GitHub stars increase
- [ ] Track PyPI downloads

### First Week
- [ ] Analyze watch time metrics
- [ ] Check audience retention graph
- [ ] Review comments and feedback
- [ ] Make note of common questions
- [ ] Consider creating follow-up content

---

## 💡 Notes Section

**Things that went well:**
_______________________________________
_______________________________________
_______________________________________

**Things to improve next time:**
_______________________________________
_______________________________________
_______________________________________

**Ideas for follow-up videos:**
_______________________________________
_______________________________________
_______________________________________

**Viewer feedback to address:**
_______________________________________
_______________________________________
_______________________________________

---

## 🎉 Celebration Checklist

After publishing:
- [ ] Share with team/friends
- [ ] Celebrate your hard work! 🎊
- [ ] Take a break - you earned it!
- [ ] Plan next demo/tutorial

---

**Remember:** Done is better than perfect! 

Your first demo doesn't have to be flawless. The important thing is to get it out there and iterate based on feedback.

**You've got this! 🚀**

---

## Quick Reference URLs

```
Local Admin: http://localhost:8000/admin/
Local Forms: http://localhost:8000/forms/
GitHub Repo: https://github.com/opensensor/django-forms-workflows
PyPI Package: https://pypi.org/project/django-forms-workflows/
```

## Quick Reference Credentials

```
Admin: admin / admin123
Farmer: farmer@example.com / demo123
Manager: manager@example.com / demo123
Director: director@example.com / demo123
```

