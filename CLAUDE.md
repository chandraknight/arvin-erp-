## Commands

```bash
# Run dev server
python manage.py runserver

# Run migrations
python manage.py migrate

# Create migrations
python manage.py makemigrations

# Collect static files
python manage.py collectstatic --noinput

# Django shell
python manage.py shell

# Run tests (if added)
python manage.py test
```

## Architecture

- Feature-based: each Django app under `apps/` owns its own models, views, urls, and services.
- Business logic lives in `services/` inside each app — views stay thin.
- `apps/bookkeeping/` is the financial core; billing and payments reference it.

## Domain Knowledge

- POS = Point of Sale terminal (`apps/pos/`)
- Fiscal year and Nepali date (`nepali-datetime`) used in reports

## Don'ts

- Don't modify Django auto-generated migration files after they've been committed
- Don't bypass `apps/accounts/` auth — all views must go through Django's auth middleware

## Skill Auto-Invocation

Check these BEFORE responding to any user message. Invoke the matching skill automatically — do not ask permission first.

| Trigger words / context | Skill to invoke |
|---|---|
| Any action-oriented request: "build", "add", "create", "I want", "implement", "make", "new", "update", "change", "fix", "generate", "write", "set up", "configure", "design", "integrate", "connect", "wire", "enable", "disable", "remove", "delete", "refactor", "migrate", "deploy", "test", "add feature/module/app/page/view/model/form/endpoint/API" | `godmode` |
| "improve UI", "looks bad", "redesign", "template", "layout", "mobile", "responsive" | `uiux` |
| "qa", "audit", "check issues", "find bugs", "run qa", "quality check" | `qa` |
| "too many tokens", "optimize tokens", "rules bloated", "reduce context" | `lean` |
| Vague/ambiguous prompt, missing scope or success criteria | `prompt-optimize` |
| "security", "vulnerability", "secure", "exploit", "injection", "XSS", "CSRF", "auth bypass", "review security", "security audit", "gstack" | `security-review` |
| "missing feature", "incomplete", "not implemented", "TODO", "stub", "placeholder", "finish", "complete the feature", "code review", "review diff", "check code" | `code-review` |

**Priority order when multiple match:** `prompt-optimize` → `security-review` → `godmode` → `code-review` → `uiux` → `lean`

Only skip `godmode` when:
- User is asking a pure question with no action required
- User explicitly says "just explain" or "don't build"
