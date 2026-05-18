---
description: Run the unit test suite
allowed-tools:
  - Bash(python -m unittest*)
model: haiku
---

Run the unit tests and report the results:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

Report how many tests passed, how many failed, and paste any failure tracebacks in full.
