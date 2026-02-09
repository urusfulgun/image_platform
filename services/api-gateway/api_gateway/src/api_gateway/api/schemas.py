from datetime import datetime
import re
from api_gateway.utils.utc import get_utc_now
from pydantic import (
    BaseModel,
    HttpUrl,
    ValidationInfo,
    field_validator,
    model_validator,
    Field,
    ConfigDict,
)

import uuid
from typing import Annotated, Literal, Optional, Self

# Define the set of valid resolutions allowed by the system
VALID_RESOLUTIONS = {"NORMAL", "PREVIEW", "THUMBNAIL"}
ALLOWED_PLACEHOLDERS = {"{original_filename}", "{res_type}", "{uuid}", "{index}"}


class ProjectCreate(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True, str_strip_whitespace=True, extra="forbid"
    )

    name: Annotated[
        str, Field(min_length=1, max_length=255, examples=["E-commerce Summer Batch"])
    ]

    naming_template: Optional[Annotated[str, Field(max_length=500)]] = (
        "{original_filename}_{res_type}"
    )

    target_resolutions: list[str] = Field(
        default_factory=lambda: ["NORMAL"],
        min_length=1,
        description="Options: NORMAL, PREVIEW, THUMBNAIL",
    )

    @field_validator("target_resolutions")
    @classmethod
    def validate_resolutions(cls, v: list[str]) -> list[str]:
        # Normalize to uppercase and remove duplicates
        normalized = list(set(res.upper() for res in v))
        invalid = set(normalized) - VALID_RESOLUTIONS
        if invalid:
            raise ValueError(
                f"Unsupported resolutions: {invalid}. Allowed: {VALID_RESOLUTIONS}"
            )
        return normalized

    @field_validator("naming_template")
    @classmethod
    def validate_template_syntax(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v

        # 1. Check for illegal filesystem/S3 characters to prevent path traversal
        if any(char in v for char in ("..", "/", "\\", "\0")):
            raise ValueError(
                "naming_template contains illegal characters or path traversal sequences."
            )

        # 2. Validate placeholders using regex
        placeholders = re.findall(r"\{[a-zA-Z0-9_]+\}", v)
        invalid_placeholders = set(placeholders) - ALLOWED_PLACEHOLDERS
        if invalid_placeholders:
            raise ValueError(
                f"Invalid placeholders found: {invalid_placeholders}. Allowed: {ALLOWED_PLACEHOLDERS}"
            )

        return v

    @model_validator(mode="after")
    def ensure_at_least_one_resolution(self) -> Self:
        if not self.target_resolutions:
            raise ValueError("At least one target resolution must be specified.")
        return self


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,  # Automatically clean whitespace
        extra="forbid",  # Prevent injection of unknown fields
    )

    name: str | None = Field(default=None, min_length=1, max_length=255)

    naming_template: str | None = Field(
        default=None,
        max_length=500,
        description="Template for generated filenames, e.g., '{original}_{res}'",
    )

    target_resolutions: list[str] | None = Field(
        default=None,
        min_length=1,  # Cannot be an empty list if provided
    )

    @field_validator("target_resolutions")
    @classmethod
    def validate_resolutions(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v

        # Convert to uppercase for consistency
        v = [res.upper() for res in v]

        # Check against the allowed set
        invalid = set(v) - VALID_RESOLUTIONS
        if invalid:
            raise ValueError(
                f"Invalid resolutions: {invalid}. Must be from {VALID_RESOLUTIONS}"
            )

        return v


class ImageRename(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    # We use a pattern that allows spaces, dots, dashes, and underscores
    # but prevents characters that mess with HTTP headers or shell commands.
    new_display_name: Annotated[
        str,
        Field(
            min_length=1,
            max_length=500,
            pattern=r"^[a-zA-Z0-9_\-\. ]+$",
            examples=["Summer_Vacation_2026", "Product_Hero_Shot.v1"],
        ),
    ]

    @field_validator("new_display_name")
    @classmethod
    def prevent_dangerous_names(cls, v: str) -> str:
        # 1. Prevent "reserved" filenames in various OS/Environments
        reserved_names = {"CON", "PRN", "AUX", "NUL", "COM1", "LPT1"}
        name_stem = v.split(".")[0].upper()
        if name_stem in reserved_names:
            raise ValueError(f"'{v}' is a reserved system filename.")

        # 2. Prevent "dot-only" or "hidden" file names if desired
        if v.startswith(".") and len(v.strip(".")) == 0:
            raise ValueError("Display name cannot consist only of dots.")

        # 3. Security: Prevent multiple consecutive dots (path-like behavior)
        if ".." in v:
            raise ValueError("Display name cannot contain consecutive dots.")

        return v


class AccessGrant(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    # The internal UUID7 of the grantee
    target_user_id: uuid.UUID = Field(
        description="The internal UUID7 of the user receiving access."
    )

    # We use a literal or Enum for strictly defined roles
    access_level: str = Field(
        default="READ_ONLY",
        pattern="^(READ_ONLY|ADMIN)$",
        description="The permission level. Currently only READ_ONLY is supported.",
    )

    @model_validator(mode="after")
    def validate_grant_logic(self, info: ValidationInfo) -> Self:
        # 1. Access the current_user_id from the context (passed by the endpoint)
        current_user_id = info.context.get("current_user_id") if info.context else None

        # 2. Prevent self-sharing
        if current_user_id and self.target_user_id == current_user_id:
            raise ValueError("You cannot share a project with yourself.")

        return self


class ImageUploadIntentResponse(BaseModel):
    """
    Schema returned to the Angular frontend to facilitate
    direct-to-S3 (RustFS) uploads.
    """

    image_id: uuid.UUID = Field(
        ..., description="The UUID7 identifier generated for the image metadata."
    )
    upload_url: HttpUrl = Field(
        ..., description="The presigned S3 URL valid for a PUT request."
    )
    method: Literal["PUT"] = Field(
        default="PUT", description="The HTTP method required for the upload_url."
    )

    class Config:
        # Ensures that UUIDs and HttpUrls are serialized to strings in the JSON output
        from_attributes = True
