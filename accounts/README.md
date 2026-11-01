# User activity log - install guide

Records create / update / delete on ALL models (no model list to maintain), only for users you pick,
keeps the old version of every changed record and every deleted record,
moves logs older than 30 days into monthly archive files, and lets an admin
delete archives older than 1 year.

## Files in this package

Copy as-is into your project (same folder layout):

    accounts/activity.py
    accounts/activity_signals.py
    accounts/activity_views.py
    accounts/management/commands/archive_activity_logs.py   (+ the two __init__.py if you have no management folder yet)
    accounts/templates/accounts/activity_log.html
    accounts/templates/accounts/activity_archives.html

Paste into existing files (see snippets/):

    1_models_additions.py     -> accounts/models.py
    2_admin_additions.py      -> accounts/admin.py
    3_signals_hook.txt        -> last line of accounts/signals.py
    4_urls_additions.py       -> accounts/urls.py
    5_settings_additions.py   -> settings.py
    6_base_menu_links.html    -> hamburger menu in base.html
    7_view_permissions.csv    -> import on your View Permissions page (change "Admin" to your group)

## Steps

1. Copy the files and paste the snippets (order above).
2. python manage.py makemigrations accounts
3. python manage.py migrate
4. In Django admin > Tracked users, add the users you want recorded.
5. Import 7_view_permissions.csv so only your admin group can open the pages.
6. Schedule the archive job (daily is fine):
       0 2 * * * /path/to/venv/bin/python manage.py archive_activity_logs

## Good to know

- Without the ViewPermission rows (step 5) any staff user can open these pages,
  because your middleware lets views with no row through.
- Archives are never deleted automatically. After 1 year the archives page
  shows a Delete button (POST + confirmation, refused for anything younger).
- Archive files are .jsonl.gz: `zcat activity_2026-09.jsonl.gz | less`
- Excluded automatically: the log's own tables, sessions, admin LogEntry, contenttypes, migrations,
  and the last_login field. Add more with ACTIVITY_EXCLUDE_MODELS in settings.
- Deleting a record that cascades (e.g. a user) logs every cascaded record too, each with its full old copy.
- Only changes made through a web request by a tracked user are recorded.
  Shell, management commands and bulk_create / bulk_update / queryset.update()
  skip the signals.
- ManyToMany changes (e.g. ViewPermission.groups) are not captured.
- File fields store the file path, not the file; Django keeps replaced files on disk.
- Templates assume {% extends "base.html" %} with a "content" block - adjust to yours.
