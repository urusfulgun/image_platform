"""The asset-service S3 client is built from settings, not literals."""

from asset_service.s3 import client as s3_client


def test_get_s3_client_uses_settings(mocker, monkeypatch):
    settings = s3_client.settings
    monkeypatch.setattr(settings, "s3_endpoint_url", "http://s3.test:9000")
    monkeypatch.setattr(settings, "s3_access_key", "key-from-env")
    monkeypatch.setattr(settings, "s3_secret_key", "secret-from-env")
    monkeypatch.setattr(settings, "s3_region", "eu-test-1")
    boto_client = mocker.patch.object(s3_client.boto3, "client")

    assert s3_client.get_s3_client() is boto_client.return_value

    args, kwargs = boto_client.call_args
    assert args == ("s3",)
    assert kwargs["endpoint_url"] == "http://s3.test:9000"
    assert kwargs["aws_access_key_id"] == "key-from-env"
    assert kwargs["aws_secret_access_key"] == "secret-from-env"
    assert kwargs["region_name"] == "eu-test-1"
    assert kwargs["config"].signature_version == "s3v4"
