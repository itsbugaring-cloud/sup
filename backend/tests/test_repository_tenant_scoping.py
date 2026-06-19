from __future__ import annotations

import unittest

from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.supplier_document_repository import SupplierDocumentRepository
from app.repositories.supplier_repository import SupplierRepository
from app.schemas.audit_log import AuditLogFilter
from app.schemas.supplier import SupplierFilter


class RepositoryTenantScopingTest(unittest.TestCase):
    def test_repositories_accept_tenant_id_from_dependencies(self) -> None:
        tenant_id = "tenant-123"

        supplier_repo = SupplierRepository(object(), tenant_id=tenant_id)
        audit_repo = AuditLogRepository(object(), tenant_id=tenant_id)
        document_repo = SupplierDocumentRepository(object(), tenant_id=tenant_id)

        self.assertEqual(supplier_repo.tenant_id, tenant_id)
        self.assertEqual(audit_repo.tenant_id, tenant_id)
        self.assertEqual(document_repo.tenant_id, tenant_id)

    def test_supplier_filter_stmt_includes_tenant_clause(self) -> None:
        repo = SupplierRepository(object(), tenant_id="tenant-123")

        statement = repo._build_filter_stmt(SupplierFilter())

        self.assertIn("suppliers.tenant_id", str(statement))

    def test_audit_filter_stmt_includes_tenant_clause(self) -> None:
        repo = AuditLogRepository(object(), tenant_id="tenant-123")

        statement = repo._build_filter_stmt(AuditLogFilter())

        self.assertIn("audit_logs.tenant_id", str(statement))
