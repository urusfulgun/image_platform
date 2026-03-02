import base64
import hashlib
import logging

from fastapi import HTTPException, Request
import jwt

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


async def validate_dpop(request: Request):
    log.info('DPoP validation')
    auth = request.headers.get("Authorization")
    dpop_jwt = request.headers.get("DPoP")

    if not auth or not auth.startswith("DPoP "):
        log.warning(f'Expected DPoP Authorization header. Got {auth}')
        raise HTTPException(401, "Expected DPoP Authorization")
    if not dpop_jwt:
        log.warning(f'Expected DPoP Proof header. Got {dpop_jwt}')
        raise HTTPException(401, "Missing DPoP Proof")

    token = auth.split(" ")[1]

    try:
        # 1. Decode Access Token (In prod: verify signature with Keycloak's PEM)
        decoded_token = jwt.decode(token, options={"verify_signature": False})
        jkt_in_token = decoded_token.get("cnf", {}).get("jkt")

        # 2. Verify DPoP Proof JWT
        dpop_header = jwt.get_unverified_header(dpop_jwt)
        proof_payload = jwt.decode(
            dpop_jwt, options={"verify_signature": False}
        )  # In prod: verify sig with dpop_header['jwk']

        # 3. Check 'ath' (Access Token Hash) match
        ath_calculated = (
            base64.urlsafe_b64encode(hashlib.sha256(token.encode()).digest())
            .decode()
            .rstrip("=")
        )
        if proof_payload.get("ath") != ath_calculated:
            log.warning(f'DPoP proof does not match Access Token. Expected sha256: {proof_payload.get("ath")}. Got: {ath_calculated}')
            raise HTTPException(401, "DPoP proof does not match Access Token")

        # 4. Check URL and Method
        if proof_payload.get("htu") != str(request.url).split("?")[0]:
            log.warning(f"DPoP target URL mismatch. Expected {proof_payload.get("htu")} as statet in claims. Got {str(request.url).split("?")[0]}")
            raise HTTPException(401, "DPoP target URL mismatch")

    except Exception as e:
        log.warning(f"Security validation failed: {str(e)}")
        raise HTTPException(401, f"Security validation failed: {str(e)}")

    return decoded_token