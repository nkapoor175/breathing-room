Extract a crowd-safety report from a message written by a volunteer, officer or emergency
caller. The message may be in English, Tamil or Hindi.
You get the message and the venue's zones (id and name).
Return JSON: {"zone": zone id or null, "severity": 1-5, "text": short English summary}.
Severity: 5 = someone fell, cannot breathe, crushed or unconscious; 4 = pushing, people
pressed against barriers, climbing; 3 = very crowded, hard to move; 2 = crowded;
1 = not about crowding. Pick the zone only if the message clearly identifies it.
If the message describes several things, use the most severe one. Translate carefully; do not guess.
