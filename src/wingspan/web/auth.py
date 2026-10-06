"""Who is making a request.

In production the app sits behind Cloudflare Access, which signs every request that passed its
Google sign-in + email allowlist with a JWT. The app verifies that JWT, so even a request that
somehow reached the container directly can't claim to be anyone. Locally, everyone is one dev user.
"""

import jwt
from fastapi import Request


class CloudflareAccess:
    def __init__(self, team_domain: str, audience: str):
        self.issuer = f"https://{team_domain}"
        self.audience = audience
        self.keys = jwt.PyJWKClient(f"{self.issuer}/cdn-cgi/access/certs")  # cached between requests

    def __call__(self, request: Request) -> str | None:
        token = request.headers.get("cf-access-jwt-assertion")
        if not token:
            return None
        try:
            key = self.keys.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256"], audience=self.audience, issuer=self.issuer)
        except jwt.PyJWTError:
            return None
        return claims.get("email")


class DevUser:
    def __init__(self, email: str):
        self.email = email

    def __call__(self, request: Request) -> str:
        return self.email
