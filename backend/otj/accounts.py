"""FAKE accounts for local testing. The same password for everyone on purpose; never use this on a shared server.

Imported by otj/seed_users.py (creates them) and otj/fake_users.py (logs in as them).
"""

import os

PASSWORD = "Test@12345"

# The owner account uses your own email, read from the environment so it never has to be committed.
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "owner@example.com")

ACCOUNTS = [
    {"name": "Sanjeev Chauhan", "email": OWNER_EMAIL, "level": "advanced"},  # the project owner
    {"name": "Amit Sharma", "email": "amit@example.com", "level": "beginner"},
    {"name": "Priya Nair", "email": "priya@example.com", "level": "advanced"},
    {"name": "Rahul Verma", "email": "rahul@example.com", "level": "expert"},
    {"name": "Sneha Iyer", "email": "sneha@example.com", "level": "beginner"},
]
