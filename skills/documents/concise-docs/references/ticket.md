# Example — ticket

FINDING/SCOPE/ACCEPTANCE, nothing narrated in between.

**FINDING**
A bad Jira credential returns `200` with an empty list, read by the doctor as success.

**SCOPE**
1. Doctor checks the credential resolves to a real user, not just a `200`.
2. One test seen failing against today's code, then green after the fix.

**ACCEPTANCE**
1. A bad token fails `doctor.py`'s check with a named reason.
2. A good token still passes.
