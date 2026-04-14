r"""Set `company_id` custom claim on a Firebase Auth user via Admin SDK.

Used for Test 2.5's positive-case counterpart (Test 9.2) — a protected endpoint
returns 200 when the token carries a valid `company_id` claim.

Web research (docs/research/zettel-firestore-multi-tenant.md) confirmed that
custom claims can only be set server-side via the Admin SDK; the client JS SDK
cannot set them. This script is the project's canonical way to attach
`company_id` to a test user during Sprint 0 integration testing, and will also
be used as a reference pattern for the Cloud Function that sets claims on
real user signup in Tier 2/3.

IMPORTANT CAVEAT: custom claims do not auto-refresh client-side. After running
this script, the client must force a token refresh (`currentUser.getIdToken(True)`)
or wait up to one hour. Newly-fetched ID tokens will carry the new claim.

Usage:
    uv run python scripts/set_custom_claims.py --uid <firebase-uid> --company-id <tenant-id>

Against the Firebase Auth emulator:
    FIREBASE_AUTH_EMULATOR_HOST=localhost:9099 \
      uv run python scripts/set_custom_claims.py --uid test_u_1 --company-id comp_1

Against production Firebase (requires GOOGLE_APPLICATION_CREDENTIALS pointing at
the service-account JSON or ADC configured):
    uv run python scripts/set_custom_claims.py --uid <real-uid> --company-id <tenant-id>
"""

from __future__ import annotations

import argparse
import sys

import firebase_admin
from firebase_admin import auth, credentials


def _init_firebase_admin() -> None:
    """Initialize firebase_admin if not already initialized.

    Against the emulator, FIREBASE_AUTH_EMULATOR_HOST must be set before the
    Admin SDK reads it. This is the caller's responsibility.

    Against production, Application Default Credentials (ADC) or
    GOOGLE_APPLICATION_CREDENTIALS env var must be set.
    """
    if not firebase_admin._apps:
        try:
            firebase_admin.initialize_app()
        except Exception as exc:
            # Emulator path: Admin SDK can init without ADC if emulator host set.
            # If both fail, credentials are missing.
            try:
                firebase_admin.initialize_app(credentials.ApplicationDefault())
            except Exception:
                raise RuntimeError(
                    "firebase_admin could not initialize. Set ADC or "
                    "GOOGLE_APPLICATION_CREDENTIALS, or FIREBASE_AUTH_EMULATOR_HOST "
                    "for emulator use."
                ) from exc


def set_company_claim(uid: str, company_id: str) -> None:
    """Attach `company_id` custom claim to a Firebase Auth user."""
    _init_firebase_admin()
    auth.set_custom_user_claims(uid, {"company_id": company_id})


def main() -> int:
    """CLI entry: parse args, set the claim, print next-steps."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uid", required=True, help="Firebase Auth user UID")
    parser.add_argument(
        "--company-id",
        required=True,
        help="Tenant identifier — stamped onto the user's ID token as a custom claim",
    )
    args = parser.parse_args()

    try:
        set_company_claim(args.uid, args.company_id)
    except auth.UserNotFoundError:
        print(f"user not found: {args.uid}", file=sys.stderr)
        return 1

    print(f"set company_id={args.company_id} on user {args.uid}")
    print("Client must force a token refresh to see the new claim:")
    print("  JS:     await currentUser.getIdToken(true)")
    print("  Python: user.reload() then auth.verify_id_token(new_token)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
