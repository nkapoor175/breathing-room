"""Day-1 check: list the Nemotron model IDs on Token Factory.

Run:  python -m common.check_models
Copy the exact IDs into MODELS in common/llm.py.
"""
from common.llm import client, MODELS

ids = sorted(m.id for m in client.models.list().data if "nemotron" in m.id.lower())
for i in ids:
    print(i)

print()
for role, mid in MODELS.items():
    print(f"{role:10s} {mid:45s} {'OK' if mid in ids else 'NOT FOUND - fix in common/llm.py'}")
