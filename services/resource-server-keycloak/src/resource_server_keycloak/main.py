# resource_server.py
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


def validate_dpop(request: Request):
    auth = request.headers.get("Authorization")
    dpop_jwt = request.headers.get("DPoP")

    if not auth or not auth.startswith("DPoP "):
        raise HTTPException(401, "Expected DPoP Authorization")

    token = auth.split(" ")[1]
    # 1. Decode Access Token (Verify signature/expiry)
    decoded_token = jwt.decode(
        token, options={"verify_signature": False}
    )  # use Keycloak public key in prod

    # 2. Check DPoP Binding (cnf claim)
    jkt_in_token = decoded_token.get("cnf", {}).get("jkt")

    # 3. Verify DPoP Proof signature and 'ath' hash
    dpop_headers = jwt.get_unverified_header(dpop_jwt)
    # verify dpop_jwt signature with dpop_headers['jwk']
    # then check if jkt(dpop_headers['jwk']) == jkt_in_token
    return True


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
