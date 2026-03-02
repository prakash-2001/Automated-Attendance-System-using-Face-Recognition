# Next Version Plan (Implemented)

Date: 2026-03-02

## Phase 1: Architecture Reset

1. Move from MySQL-dependent legacy script to SQLite local-first backend for easier low-end setup.
2. Replace ad-hoc route checks with reusable role-based auth decorators.
3. Introduce normalized schema with foreign keys and uniqueness constraints.

## Phase 2: Core Backend Services

1. Add robust validation for USN, username, password, subject code, semester, and time windows.
2. Build clean JSON APIs for recognition and attendance marking.
3. Implement deterministic attendance guardrails:
- one attendance per student per subject per date
- branch/semester eligibility enforcement
- staff access only to assigned subjects

## Phase 3: Face Recognition Layer

1. Add pluggable recognition engine:
- `face_recognition` backend when available
- OpenCV fallback embedding for low-end compatibility
2. Reject ambiguous captures:
- no face
- multiple faces
- invalid frames
3. Store one face profile per student with upsert behavior.

## Phase 4: UI/UX Rebuild

1. Replace fixed-position legacy pages with responsive componentized templates.
2. Add animated visual identity (gradient motion, reveal transitions, floating cards).
3. Build live camera attendance page with manual fallback and activity log.

## Phase 5: Documentation and Operability

1. Publish audit findings and rebuilt architecture decisions.
2. Add clear install/run instructions and default credentials policy.
3. Document edge cases and known operational expectations.

## Edge Cases Covered in v2

1. Duplicate attendance attempts.
2. Unauthorized access by role.
3. Invalid subject access by staff.
4. Student-subject mismatch (branch/semester).
5. Invalid data formats and empty form payloads.
6. Camera permission failures.
7. Face frame decode failure.
8. No-face and multi-face captures.
9. Missing face profiles for recognition.
10. Re-activating/deactivating staff accounts.
