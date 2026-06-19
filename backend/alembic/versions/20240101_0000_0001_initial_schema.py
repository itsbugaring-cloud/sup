"""
alembic/versions/20240101_0000_0001_initial_schema.py
──────────────────────────────────────────────────────────────────────────────
MIGRATION: Initial Schema
Revision: 0001
Description: Creates the foundational tables for the Supplier CRM:
  - suppliers         : Core supplier entity with soft delete
  - supplier_documents: Documents linked to suppliers (NPWP, photos, etc.)
  - audit_logs        : Immutable record of all data mutations

Tables follow strict naming conventions:
  - Table names: plural_snake_case
  - Column names: snake_case
  - Indexes: idx_[table]_[column(s)]
  - Constraints: uq_[table]_[column], fk_[table]_[ref_table]_[column]
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Alembic migration identifiers
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """
    Apply the initial schema.

    Order:
      1. Enable PostgreSQL extensions.
      2. Create enum types.
      3. Create `suppliers` table.
      4. Create `supplier_documents` table.
      5. Create `audit_logs` table.
      6. Create all indexes.
    """

    # ─────────────────────────────────────────────────────────────────────────
    # 1. PostgreSQL Extensions
    # ─────────────────────────────────────────────────────────────────────────
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')   # gen_random_uuid()
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm";')    # Trigram indexes for ILIKE searches
    op.execute('CREATE EXTENSION IF NOT EXISTS "btree_gin";')  # GIN index support for JSONB

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Custom Enum Types
    # ─────────────────────────────────────────────────────────────────────────
    supplier_status_enum = postgresql.ENUM(
        "active",
        "inactive",
        "pending_review",
        "blacklisted",
        name="supplier_status",
        create_type=True,
    )
    supplier_status_enum.create(op.get_bind(), checkfirst=True)

    document_type_enum = postgresql.ENUM(
        "npwp",
        "photo",
        "siup",
        "nib",
        "contract",
        "other",
        name="document_type",
        create_type=True,
    )
    document_type_enum.create(op.get_bind(), checkfirst=True)

    audit_action_enum = postgresql.ENUM(
        "CREATE",
        "UPDATE",
        "DELETE",
        "RESTORE",
        "EXPORT",
        "LOGIN",
        name="audit_action",
        create_type=True,
    )
    audit_action_enum.create(op.get_bind(), checkfirst=True)

    audit_actor_type_enum = postgresql.ENUM(
        "web_user",
        "telegram_bot",
        "system",
        name="audit_actor_type",
        create_type=True,
    )
    audit_actor_type_enum.create(op.get_bind(), checkfirst=True)

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Table: suppliers
    # ─────────────────────────────────────────────────────────────────────────
    op.create_table(
        "suppliers",
        # ── Identity ──────────────────────────────────────────────────────────
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
            comment="UUID v4 primary key",
        ),

        # ── Core Fields ───────────────────────────────────────────────────────
        sa.Column(
            "company_name",
            sa.String(255),
            nullable=False,
            comment="Legal company name of the supplier",
        ),
        sa.Column(
            "npwp_number",
            sa.String(30),
            nullable=True,
            unique=True,
            comment="Nomor Pokok Wajib Pajak (15-16 digit tax ID)",
        ),
        sa.Column(
            "pic_name",
            sa.String(255),
            nullable=False,
            comment="Person in charge (PIC) full name",
        ),
        sa.Column(
            "pic_phone",
            sa.String(30),
            nullable=False,
            comment="PIC phone number (E.164 format recommended)",
        ),
        sa.Column(
            "pic_email",
            sa.String(255),
            nullable=True,
            comment="PIC email address",
        ),
        sa.Column(
            "address",
            sa.Text,
            nullable=True,
            comment="Full business address",
        ),
        sa.Column(
            "city",
            sa.String(100),
            nullable=True,
            comment="City / Kota",
        ),
        sa.Column(
            "province",
            sa.String(100),
            nullable=True,
            comment="Province / Provinsi",
        ),
        sa.Column(
            "category",
            sa.String(100),
            nullable=True,
            comment="Supplier category / type of goods or services",
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "active", "inactive", "pending_review", "blacklisted",
                name="supplier_status",
                create_type=False,  # Already created above
            ),
            nullable=False,
            server_default="pending_review",
            comment="Current operational status of the supplier",
        ),
        sa.Column(
            "notes",
            sa.Text,
            nullable=True,
            comment="Internal notes about the supplier",
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default="{}",
            comment="Flexible key-value store for extra attributes (JSONB)",
        ),

        # ── Telegram Bot Tracking ────────────────────────────────────────────
        sa.Column(
            "submitted_by_telegram_id",
            sa.BigInteger,
            nullable=True,
            comment="Telegram user ID of field staff who submitted this record",
        ),
        sa.Column(
            "submitted_by_telegram_username",
            sa.String(100),
            nullable=True,
            comment="Telegram username of the submitting field staff",
        ),

        # ── Soft Delete ───────────────────────────────────────────────────────
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Soft delete timestamp; NULL = active record",
        ),
        sa.Column(
            "deleted_by",
            sa.String(255),
            nullable=True,
            comment="Identifier of the actor who performed the soft delete",
        ),

        # ── Audit Timestamps ──────────────────────────────────────────────────
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="Record creation timestamp (UTC)",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            onupdate=sa.text("NOW()"),
            comment="Record last update timestamp (UTC)",
        ),

        # ── Table Config ──────────────────────────────────────────────────────
        sa.UniqueConstraint("npwp_number", name="uq_suppliers_npwp_number"),
        comment="Core supplier entity. Uses soft delete (deleted_at).",
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Table: supplier_documents
    # ─────────────────────────────────────────────────────────────────────────
    op.create_table(
        "supplier_documents",
        # ── Identity ──────────────────────────────────────────────────────────
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),

        # ── Foreign Key ───────────────────────────────────────────────────────
        sa.Column(
            "supplier_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="FK to suppliers.id",
        ),

        # ── Document Metadata ─────────────────────────────────────────────────
        sa.Column(
            "document_type",
            postgresql.ENUM(
                "npwp", "photo", "siup", "nib", "contract", "other",
                name="document_type",
                create_type=False,
            ),
            nullable=False,
            comment="Type/category of the document",
        ),
        sa.Column(
            "original_filename",
            sa.String(500),
            nullable=False,
            comment="Original filename as uploaded by the user",
        ),
        sa.Column(
            "stored_filename",
            sa.String(500),
            nullable=False,
            comment="UUID-based filename as stored in MinIO",
        ),
        sa.Column(
            "minio_bucket",
            sa.String(255),
            nullable=False,
            comment="MinIO bucket where the file is stored",
        ),
        sa.Column(
            "minio_object_key",
            sa.String(1000),
            nullable=False,
            comment="Full object key / path within the MinIO bucket",
        ),
        sa.Column(
            "file_size_bytes",
            sa.BigInteger,
            nullable=True,
            comment="File size in bytes",
        ),
        sa.Column(
            "mime_type",
            sa.String(255),
            nullable=True,
            comment="MIME type verified from magic bytes (not file extension)",
        ),
        sa.Column(
            "checksum_sha256",
            sa.String(64),
            nullable=True,
            comment="SHA-256 checksum for file integrity verification",
        ),
        sa.Column(
            "is_verified",
            sa.Boolean,
            nullable=False,
            server_default="false",
            comment="Whether the document has been reviewed and verified",
        ),

        # ── Uploader Context ──────────────────────────────────────────────────
        sa.Column(
            "uploaded_by_telegram_id",
            sa.BigInteger,
            nullable=True,
            comment="Telegram user ID who uploaded (bot uploads)",
        ),
        sa.Column(
            "uploaded_by_web_user",
            sa.String(255),
            nullable=True,
            comment="Web dashboard user who uploaded",
        ),

        # ── Soft Delete ───────────────────────────────────────────────────────
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Soft delete timestamp for documents",
        ),

        # ── Audit Timestamps ──────────────────────────────────────────────────
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),

        # ── Constraints ───────────────────────────────────────────────────────
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
            name="fk_supplier_documents_suppliers_supplier_id",
            ondelete="CASCADE",   # Hard delete supplier → cascade delete documents
        ),
        sa.UniqueConstraint(
            "minio_object_key",
            name="uq_supplier_documents_minio_object_key",
        ),
        comment="Documents (NPWP, photos, contracts) linked to suppliers. Files stored in MinIO.",
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 5. Table: audit_logs
    # ─────────────────────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        # ── Identity ──────────────────────────────────────────────────────────
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),

        # ── What was done ─────────────────────────────────────────────────────
        sa.Column(
            "action",
            postgresql.ENUM(
                "CREATE", "UPDATE", "DELETE", "RESTORE", "EXPORT", "LOGIN",
                name="audit_action",
                create_type=False,
            ),
            nullable=False,
            comment="The type of action performed",
        ),

        # ── What was affected ─────────────────────────────────────────────────
        sa.Column(
            "entity_type",
            sa.String(100),
            nullable=False,
            comment="Name of the affected model/table (e.g., 'suppliers')",
        ),
        sa.Column(
            "entity_id",
            sa.String(255),
            nullable=True,
            comment="Primary key of the affected record (stored as string for flexibility)",
        ),

        # ── Change Payload ────────────────────────────────────────────────────
        sa.Column(
            "changes_before",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Snapshot of the record BEFORE the change (for UPDATE/DELETE)",
        ),
        sa.Column(
            "changes_after",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Snapshot of the record AFTER the change (for CREATE/UPDATE)",
        ),

        # ── Who did it ────────────────────────────────────────────────────────
        sa.Column(
            "actor_type",
            postgresql.ENUM(
                "web_user", "telegram_bot", "system",
                name="audit_actor_type",
                create_type=False,
            ),
            nullable=False,
            comment="Type of actor that performed the action",
        ),
        sa.Column(
            "actor_id",
            sa.String(255),
            nullable=False,
            comment="ID of the actor (web user email, telegram user ID, or 'system')",
        ),
        sa.Column(
            "actor_display_name",
            sa.String(255),
            nullable=True,
            comment="Human-readable display name of the actor",
        ),

        # ── Request Context ───────────────────────────────────────────────────
        sa.Column(
            "request_id",
            sa.String(36),
            nullable=True,
            comment="API request UUID for log correlation",
        ),
        sa.Column(
            "ip_address",
            sa.String(45),
            nullable=True,
            comment="Client IP address (supports both IPv4 and IPv6)",
        ),
        sa.Column(
            "user_agent",
            sa.String(500),
            nullable=True,
            comment="Client user-agent string",
        ),

        # ── Timestamp (audit logs are NEVER updated — immutable) ──────────────
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
            comment="UTC timestamp of the audit event (immutable)",
        ),

        comment=(
            "Immutable audit trail. Records every CREATE/UPDATE/DELETE/EXPORT action. "
            "No rows are ever updated or deleted from this table."
        ),
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 6. Indexes — Naming convention: idx_[table]_[column(s)]
    # ─────────────────────────────────────────────────────────────────────────

    # ── suppliers indexes ─────────────────────────────────────────────────────
    op.create_index(
        "idx_suppliers_company_name",
        "suppliers",
        ["company_name"],
    )
    # Trigram index for fast case-insensitive partial search (ILIKE '%..%')
    op.create_index(
        "idx_suppliers_company_name_trgm",
        "suppliers",
        ["company_name"],
        postgresql_ops={"company_name": "gin_trgm_ops"},
        postgresql_using="gin",
    )
    op.create_index(
        "idx_suppliers_npwp_number",
        "suppliers",
        ["npwp_number"],
    )
    op.create_index(
        "idx_suppliers_status",
        "suppliers",
        ["status"],
    )
    op.create_index(
        "idx_suppliers_city",
        "suppliers",
        ["city"],
    )
    op.create_index(
        "idx_suppliers_province",
        "suppliers",
        ["province"],
    )
    op.create_index(
        "idx_suppliers_category",
        "suppliers",
        ["category"],
    )
    op.create_index(
        "idx_suppliers_deleted_at",
        "suppliers",
        ["deleted_at"],
    )
    op.create_index(
        "idx_suppliers_submitted_by_telegram_id",
        "suppliers",
        ["submitted_by_telegram_id"],
    )
    op.create_index(
        "idx_suppliers_created_at",
        "suppliers",
        ["created_at"],
    )
    # Composite: active suppliers by status (most common query pattern)
    op.create_index(
        "idx_suppliers_status_deleted_at",
        "suppliers",
        ["status", "deleted_at"],
    )
    # JSONB GIN index for metadata field queries
    op.create_index(
        "idx_suppliers_metadata_gin",
        "suppliers",
        ["metadata"],
        postgresql_using="gin",
    )

    # ── supplier_documents indexes ────────────────────────────────────────────
    op.create_index(
        "idx_supplier_documents_supplier_id",
        "supplier_documents",
        ["supplier_id"],
    )
    op.create_index(
        "idx_supplier_documents_document_type",
        "supplier_documents",
        ["document_type"],
    )
    op.create_index(
        "idx_supplier_documents_deleted_at",
        "supplier_documents",
        ["deleted_at"],
    )
    op.create_index(
        "idx_supplier_documents_supplier_id_document_type",
        "supplier_documents",
        ["supplier_id", "document_type"],
    )
    op.create_index(
        "idx_supplier_documents_created_at",
        "supplier_documents",
        ["created_at"],
    )

    # ── audit_logs indexes ────────────────────────────────────────────────────
    op.create_index(
        "idx_audit_logs_entity_type_entity_id",
        "audit_logs",
        ["entity_type", "entity_id"],
    )
    op.create_index(
        "idx_audit_logs_actor_id",
        "audit_logs",
        ["actor_id"],
    )
    op.create_index(
        "idx_audit_logs_action",
        "audit_logs",
        ["action"],
    )
    op.create_index(
        "idx_audit_logs_created_at",
        "audit_logs",
        ["created_at"],
    )
    op.create_index(
        "idx_audit_logs_request_id",
        "audit_logs",
        ["request_id"],
    )
    # Composite for the most common audit query: "what happened to this record?"
    op.create_index(
        "idx_audit_logs_entity_type_entity_id_created_at",
        "audit_logs",
        ["entity_type", "entity_id", "created_at"],
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 7. DB-level trigger: auto-update `updated_at` on row changes
    # ─────────────────────────────────────────────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    for table in ("suppliers", "supplier_documents"):
        op.execute(f"""
            CREATE TRIGGER trg_{table}_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
        """)


def downgrade() -> None:
    """
    Revert the initial schema — drops all tables, indexes, types, and functions.
    """

    # Drop triggers first
    for table in ("suppliers", "supplier_documents"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};")

    # Drop trigger function
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column();")

    # Drop tables (cascade removes foreign keys and indexes automatically)
    op.drop_table("audit_logs")
    op.drop_table("supplier_documents")
    op.drop_table("suppliers")

    # Drop enum types
    for enum_name in (
        "audit_actor_type",
        "audit_action",
        "document_type",
        "supplier_status",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name};")

    # Note: Extensions are NOT dropped in downgrade to avoid affecting other schemas.
