# Security policy

## Supported versions

Security fixes are released for the latest version only. If you can, check that the issue is still there in the
latest release before reporting it.

## Reporting a vulnerability

Please don't report a vulnerability in a public issue, discussion or pull request.

Report it privately through GitHub instead: open the repository's
[Security tab](https://github.com/Tecktron/django-dynamic-configs/security) and choose **Report a vulnerability**.

Keep the report short:

- what the issue is, and what an attacker could do with it
- how to reproduce it, ideally with a small proof of concept
- the versions involved: django-dynamic-configs, Django and Python, and any optional extra or cache backend
- a fix, if you have one

If you used AI tools to find the issue or write the report, say so, and check every claim yourself before sending it.

## What happens next

- You'll get a reply within 14 days. The reply acknowledges the report; it isn't a date for the fix.
- If the issue is confirmed, the fix is prepared in a private GitHub security advisory, where you can follow it and
  help.
- The fixed version is released, then the advisory is published, with a CVE when one is warranted. You're credited
  unless you'd rather not be.
- If it isn't a vulnerability, the reply says why.

Please keep the issue private until the fix is released, or for 90 days after your report, whichever comes first.

## Scope

This policy covers the code in this repository and the package published from it. Django and the other packages this
one works with have their own security policies; report their issues to them (Django's is at
https://www.djangoproject.com/security/).

These work as designed, so they aren't vulnerabilities:

- The `DYNAMIC_CONFIGS` setting, custom types included, is code the project trusts, like the rest of its settings.
- Anyone with change permission on configs in the admin can change their values; the project's permissions decide who
  has it.
