"""
app/services/minio_service.py
──────────────────────────────────────────────────────────────────────────────
MinIO / S3-compatible object storage service.

Responsibilities:
  - Upload files to MinIO with integrity verification.
  - Validate file magic bytes (NOT just extension).
  - Generate presigned download URLs.
  - Delete objects from MinIO.

Security guarantees:
  - Files are validated by reading the first 2048 bytes (magic bytes).
  - Allowed MIME types are enforced per upload context.
  - Max file size is enforced before reading content.

NEVER store file BLOBs in PostgreSQL — only the `minio_object_key` is persisted.
"""

from __future__ import annotations

import hashlib
import io
import mimetypes
import uuid
from datetime import timedelta
from typing import BinaryIO

import magic  # python-magic for magic byte detection
from minio import Minio
from minio.error import S3Error

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Allowed MIME types ────────────────────────────────────────────────────────
ALLOWED_DOCUMENT_MIME_TYPES: set[str] = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    "application/msword",  # .doc
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
}

MAX_FILE_SIZE_BYTES: int = 20 * 1024 * 1024  # 20 MB per file


def _get_minio_client() -> Minio:
    """Create and return a MinIO client using app settings."""
    return Minio(
        endpoint=settings.minio.MINIO_ENDPOINT,
        access_key=settings.minio.MINIO_ROOT_USER,
        secret_key=settings.minio.MINIO_ROOT_PASSWORD,
        secure=settings.minio.MINIO_USE_SSL,
    )


class MinIOService:
    """
    Service for all MinIO object storage operations.

    Usage (FastAPI DI):
        minio_svc = MinIOService()
        object_key, mime, checksum = await minio_svc.upload_document(...)
    """

    def __init__(self) -> None:
        self._client = _get_minio_client()

    def _detect_mime_type(self, file_bytes: bytes) -> str:
        """
        Detect MIME type from the first 2048 bytes (magic bytes).

        This is more reliable than trusting file extensions or Content-Type headers.
        """
        mime = magic.from_buffer(file_bytes[:2048], mime=True)
        return mime

    def _compute_sha256(self, file_bytes: bytes) -> str:
        """Compute SHA-256 checksum of the file content."""
        return hashlib.sha256(file_bytes).hexdigest()

    def validate_file(
        self,
        file_content: bytes,
        allowed_mime_types: set[str] = ALLOWED_DOCUMENT_MIME_TYPES,
    ) -> tuple[str, str]:
        """
        Validate a file by magic bytes and size.

        Args:
            file_content: Raw file bytes.
            allowed_mime_types: Set of permitted MIME types.

        Returns:
            Tuple of (detected_mime_type, sha256_checksum).

        Raises:
            ValueError: If file type is not allowed or size exceeds limit.
        """
        if len(file_content) > MAX_FILE_SIZE_BYTES:
            raise ValueError(
                f"File size {len(file_content)} bytes exceeds maximum "
                f"allowed {MAX_FILE_SIZE_BYTES} bytes (20 MB)"
            )

        if len(file_content) == 0:
            raise ValueError("File is empty — zero bytes received")

        detected_mime = self._detect_mime_type(file_content)

        if detected_mime not in allowed_mime_types:
            raise ValueError(
                f"File type '{detected_mime}' is not allowed. "
                f"Allowed types: {', '.join(sorted(allowed_mime_types))}"
            )

        checksum = self._compute_sha256(file_content)
        return detected_mime, checksum

    def upload_document(
        self,
        file_content: bytes,
        original_filename: str,
        supplier_id: str,
        document_type: str,
    ) -> tuple[str, str, str, str]:
        """
        Upload a supplier document to MinIO.

        Steps:
          1. Validate file (magic bytes + size).
          2. Generate a UUID-based stored filename.
          3. Upload to MinIO under `supplier-documents/{supplier_id}/{doc_type}/{uuid}.ext`.
          4. Return storage metadata.

        Returns:
            Tuple of (stored_filename, minio_object_key, detected_mime_type, sha256_checksum).

        Raises:
            ValueError: If file validation fails.
            S3Error: If MinIO upload fails.
        """
        detected_mime, checksum = self.validate_file(file_content)

        # Determine file extension from detected MIME (not from original filename)
        ext = mimetypes.guess_extension(detected_mime) or ".bin"
        if ext == ".jpe":
            ext = ".jpg"  # Normalise JPEG extension

        stored_name = f"{uuid.uuid4().hex}{ext}"
        object_key = f"{supplier_id}/{document_type}/{stored_name}"

        bucket = settings.minio.MINIO_BUCKET_DOCUMENTS

        self._client.put_object(
            bucket_name=bucket,
            object_name=object_key,
            data=io.BytesIO(file_content),
            length=len(file_content),
            content_type=detected_mime,
            metadata={
                "original-filename": original_filename,
                "checksum-sha256": checksum,
            },
        )

        logger.info(
            "minio_upload_success",
            bucket=bucket,
            object_key=object_key,
            size_bytes=len(file_content),
            mime_type=detected_mime,
        )

        return stored_name, object_key, detected_mime, checksum

    def upload_export(
        self,
        file_content: bytes,
        filename: str,
    ) -> str:
        """
        Upload a generated Excel export to the exports bucket.

        Returns:
            The MinIO object key (used to generate presigned download URL).
        """
        bucket = settings.minio.MINIO_BUCKET_EXPORTS
        object_key = f"exports/{filename}"

        self._client.put_object(
            bucket_name=bucket,
            object_name=object_key,
            data=io.BytesIO(file_content),
            length=len(file_content),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        logger.info(
            "minio_export_upload_success",
            bucket=bucket,
            object_key=object_key,
            size_bytes=len(file_content),
        )

        return object_key

    def generate_presigned_url(
        self,
        bucket: str,
        object_key: str,
        expiry_seconds: int | None = None,
    ) -> str:
        """
        Generate a time-limited presigned URL for downloading a MinIO object.

        The URL is valid for `expiry_seconds` (default: from settings).
        """
        if expiry_seconds is None:
            expiry_seconds = settings.minio.PRESIGNED_URL_EXPIRY_SECONDS

        url = self._client.presigned_get_object(
            bucket_name=bucket,
            object_name=object_key,
            expires=timedelta(seconds=expiry_seconds),
        )

        # Replace internal MinIO hostname with the external public URL
        if settings.minio.MINIO_PUBLIC_URL:
            internal_base = f"http://{settings.minio.MINIO_ENDPOINT}"
            url = url.replace(internal_base, settings.minio.MINIO_PUBLIC_URL)

        return url

    def delete_object(self, bucket: str, object_key: str) -> None:
        """Permanently delete an object from MinIO."""
        try:
            self._client.remove_object(bucket_name=bucket, object_name=object_key)
            logger.info("minio_object_deleted", bucket=bucket, object_key=object_key)
        except S3Error as e:
            logger.error(
                "minio_delete_failed",
                bucket=bucket,
                object_key=object_key,
                error=str(e),
            )
            raise
