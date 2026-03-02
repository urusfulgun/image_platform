import base64
import hashlib
import json
import logging
import jwt
import jwt.algorithms
from keycloak import KeycloakOpenID
from fastapi import HTTPException, Request
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Initialize Keycloak
keycloak_openid = KeycloakOpenID(
    server_url="http://keycloak:8080",
    realm_name="image-platform",
    client_id="bff-client",
)


def get_jkt(jwk_dict):
    """Calculate the JWK Thumbprint (RFC 7638) for 'cnf' validation."""
    # Required fields for EC keys in lexicographical order
    thumbprint_data = {
        "crv": jwk_dict["crv"],
        "kty": jwk_dict["kty"],
        "x": jwk_dict["x"],
        "y": jwk_dict["y"],
    }
    json_data = json.dumps(
        thumbprint_data, separators=(",", ":"), sort_keys=True
    ).encode()
    return (
        base64.urlsafe_b64encode(hashlib.sha256(json_data).digest())
        .decode()
        .rstrip("=")
    )


async def validate_dpop(request: Request):
    log.info('DPoP validation')
    auth = request.headers.get("Authorization")
    dpop_jwt = request.headers.get("DPoP")

    if not auth or not dpop_jwt:
        log.warning(
            f"Missing Security Headers. Expected DPoP Authorization header. Got {auth} And DPoP JWT. Got {dpop_jwt}"
        )
        raise HTTPException(401, "Missing Security Headers")
    if not auth.startswith("DPoP "):
        log.warning(f"Expected DPoP Authorization header. Got {auth}")
        raise HTTPException(401, "Expected DPoP Authorization")
    if not dpop_jwt:
        log.warning(f"Expected DPoP Proof header. Got {dpop_jwt}")
        raise HTTPException(401, "Missing DPoP Proof")

    token = auth.split(" ")[1]

    try:
        # 1. Verify Access Token (Keycloak)
        # python-keycloak handles the EC public key format automatically
        raw_key_base64 = keycloak_openid.public_key()
        log.info(f"Public Raw key {raw_key_base64}")
        # public_key_pem = f"-----BEGIN PUBLIC KEY-----\n{raw_key}\n-----END PUBLIC KEY-----"

        key_der = base64.b64decode(raw_key_base64.encode())

        # Load the key to check its type (Fixes your "Invalid Key type" error)
        key_obj = serialization.load_der_public_key(key_der)
        
        # Determine algorithm based on the actual key type returned by Keycloak
        # If Keycloak returns RSA, use RS256. If EC, use ES256.
        # token_alg = "RS256" if "RSA" in str(type(key_obj)) else "ES256"
        # token_algs = ["ES256"]

        # log.info(f"Token algorithm aquared from keycloak is {token_alg}")
        log.info(f"Token key obj {str(type(key_obj))}")

        decoded_token = keycloak_openid.decode_token(token)

        # 2. Verify DPoP Proof (Ephemeral ES256 Key)
        dpop_header = jwt.get_unverified_header(dpop_jwt)
        ephemeral_jwk = dpop_header["jwk"]

        log.info(f"Ephemeral jwk of DPoP JWT {ephemeral_jwk}")

        # Load the ephemeral EC public key from the header
        ephemeral_key = jwt.algorithms.ECAlgorithm.from_jwk(ephemeral_jwk)

        proof_payload = jwt.decode(dpop_jwt, ephemeral_key, algorithms=["ES256"])

        log.info(f"Proof payload {proof_payload}")

        # 3. THE CRITICAL STEP: Verify 'jkt' Binding
        # This confirms the token owner is the one who signed the DPoP proof
        jkt_in_token = decoded_token.get("cnf", {}).get("jkt")
        actual_jkt = get_jkt(ephemeral_jwk)

        if jkt_in_token != actual_jkt:
            log.warning(
                f"Token is not bound to this DPoP key. jkt in token {jkt_in_token} and actual jkt {actual_jkt}"
            )
            raise HTTPException(401, "Token is not bound to this DPoP key")

        # 4. Standard DPoP Claims (ath, htm, htu)
        ath_calculated = (
            base64.urlsafe_b64encode(hashlib.sha256(token.encode()).digest())
            .decode()
            .rstrip("=")
        )

        if proof_payload.get("ath") != ath_calculated:
            log.warning(
                f"DPoP proof does not match Access Token. Expected sha256: {proof_payload.get('ath')}. Got: {ath_calculated}"
            )
            raise HTTPException(401, "DPoP 'ath' mismatch")

        # Check URL and Method
        if proof_payload.get("htu") != str(request.url).split("?")[0]:
            log.warning(
                f"DPoP target URL mismatch. Expected {proof_payload.get('htu')} as statet in claims. Got {str(request.url).split('?')[0]}"
            )
            raise HTTPException(401, "DPoP target URL mismatch")

        if proof_payload.get("htm") != request.method:
            log.warning(
                f"DPoP method mismatch. Expected {proof_payload.get('htm')} as statet in claims. Got {str(request.method)}"
            )
            raise HTTPException(401, "DPoP 'htm' mismatch")

    except Exception as e:
        log.warning(f"Security validation failed: {str(e)}")
        raise HTTPException(401, f"DPoP Validation Failed: {str(e)}")

    return decoded_token
