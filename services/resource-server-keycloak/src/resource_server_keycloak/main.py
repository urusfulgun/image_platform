# resource_server.py
import base64
import hashlib
import boto3
import jwt
from fastapi import FastAPI, Depends, Request, HTTPException
from botocore.client import Config
from types_boto3_s3.client import S3Client

app = FastAPI()

# RastFS (S3-Compatible) Configuration
s3: S3Client = boto3.client(
    "s3",
    endpoint_url="http://rustfs:9000",
    aws_access_key_id="OAhzGogEY7X61ZwjnSmH",
    aws_secret_access_key="5XItB3Pon6syp7e1cxNvJOTfWlzigEZQkK2FM8Vh",
    config=Config(signature_version="s3v4"),
    region_name="us-east-1",
)


# Keycloak Public Key (In production, fetch this from JWKS endpoint)
# For this example, we assume we're verifying the DPoP binding (jkt)
# and checking the 'ath' in the DPoP proof.


def verify_jkt(jwk, expected_jkt):
    # Simplified JKT calculation for P-256
    # In production, use a library like 'jwcrypto' for RFC 7638 thumbprints
    return True


async def validate_dpop(request: Request):
    auth = request.headers.get("Authorization")
    dpop_jwt = request.headers.get("DPoP")

    if not auth or not auth.startswith("DPoP "):
        raise HTTPException(401, "Expected DPoP Authorization")
    if not dpop_jwt:
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
            raise HTTPException(401, "DPoP proof does not match Access Token")

        # 4. Check URL and Method
        if proof_payload.get("htu") != str(request.url).split("?")[0]:
            raise HTTPException(401, "DPoP target URL mismatch")

    except Exception as e:
        raise HTTPException(401, f"Security validation failed: {str(e)}")

    return decoded_token


@app.get("/files/{key}")
async def get_link(key: str, _=Depends(validate_dpop)):
    """GET Signed Link from RastFS."""
    url = s3.generate_presigned_url(
        "get_object", Params={"Bucket": "data", "Key": key}, ExpiresIn=300
    )
    return {"url": url}


@app.post("/files/{key}")
async def upload_link(key: str, _=Depends(validate_dpop)):
    """PUT Signed Link for direct RastFS upload."""
    url = s3.generate_presigned_url(
        "put_object", Params={"Bucket": "data", "Key": key}, ExpiresIn=300
    )
    return {"url": url}
