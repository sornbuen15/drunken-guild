# Example — test case

What it proves, first. Then the failing assertion, seen failing before the fix existed.

**Proves:** a bad credential is reported, not treated as success.

```
tests/test_credential.py::test_bad_token_fails_doctor
AssertionError: expected status 'fail', got 'ok'
```

Seen failing on the unmodified code; green after the fix in `src/core/doctor.py`.
