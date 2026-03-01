import os
from pathlib import PurePosixPath
from pathlib import Path
import uuid


def get_s3_object_key(project_id: str, file_name: str) -> str:
    # Build S3 object key
    s3_key = f"{project_id}/{uuid.uuid4()}/{file_name}"
    return s3_key


def extract_filename(path_string: str) -> str:
    return os.path.basename(path_string)


def get_new_s3_path(project_id: str, original_s3_path: str, sufix: str) -> str:
    original_filename = extract_filename(original_s3_path)
    filename = PurePosixPath(original_filename).with_suffix(sufix)
    return get_s3_object_key(project_id, filename)
