# resource_server.py
import base64
import hashlib
import logging
from typing import Annotated
import boto3
import jwt
from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from botocore.client import Config
from pydantic import BaseModel, Field, StringConstraints, field_validator
from types_boto3_s3.client import S3Client

# Configuration for your RustFS (MinIO/S3 compatible)
S3_ENDPOINT_INTERNAL = "http://rustfs:9000"  # How Python talks to RustFS
S3_ENDPOINT_PUBLIC = "http://localhost:4200/storage"  # How the Browser talks to RustFS


class PresignedUrlRequest(BaseModel):
    # Matches { "fileName": "..." } from Angular
    file_name: str = Field(alias="fileName")

    @field_validator("file_name")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Filename cannot be empty")
        # Basic security: prevent path traversal
        if "/" in v or "\\" in v:
            raise ValueError("Filename cannot contain directory paths")
        return v


class PresignedUrlResponse(BaseModel):
    url: str


app = FastAPI()

origins = [
    "http://localhost:4200",
    "http://rustfs:9000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],  # PUT is critical for S3 uploads
    allow_headers=["Content-Type", "Authorization", "DPoP"],
)

# RastFS (S3-Compatible) Configuration
s3: S3Client = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT_INTERNAL,
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


# Define a type for the key to ensure it's not empty and lacks path traversal
S3Key = Annotated[str, StringConstraints(min_length=1, pattern=r"^[a-zA-Z0-9.\-_/]+$")]


@app.get("/files/{key:path}")
async def get_download_link(key: S3Key, _=Depends(validate_dpop)):
    """
    Generates a presigned URL for downloading a file from RustFS.
    Using {key:path} allows for keys that contain slashes (folders).
    """
    try:
        url = s3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": "data",
                "Key": key,
            },
            ExpiresIn=300,
        )
        return {"url": url}
    except Exception as e:
        logging.error(f"Failed to generate get_link: {e}")
        raise HTTPException(status_code=500, detail="Could not generate download link")


@app.post("/api/presign", response_model=PresignedUrlResponse)
async def upload_link(
    request_data: PresignedUrlRequest, _=Depends(validate_dpop)
):
    """PUT Signed Link for direct RastFS upload."""
    # Ensure this isn't hardcoded!
    target_key = request_data.file_name
    url = s3.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": "data",
            "Key": target_key,
            "ContentType": "application/octet-stream",
        },
        ExpiresIn=300,
    )
    # 2. CRITICAL STEP: Swap the internal hostname for the Nginx public path
    # This ensures the browser calls http://localhost/storage/...
    # public_url = url.replace(S3_ENDPOINT_INTERNAL, S3_ENDPOINT_PUBLIC)
    public_url = url
    return {"url": public_url}
