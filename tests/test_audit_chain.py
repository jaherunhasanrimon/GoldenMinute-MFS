"""Tests for SHA-256 Cryptographic Audit Hash Chain and Tamper Detection."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from goldenminutes.api.main import create_app
from goldenminutes.api.store import AuditLogRecord, get_db_store


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_audit_chain_verification_on_clean_store():
    store = get_db_store()
    is_valid, total, genesis, last, err = store.verify_audit_chain()
    assert is_valid is True
    assert err is None


def test_audit_chain_links_consecutive_records():
    store = get_db_store()

    # Generate 5 test audit entries
    with store.get_session() as session:
        for i in range(5):
            store.record_audit_log(
                session=session,
                event_type="test_event",
                user_id=f"USR-{i}",
                resource_type="test_resource",
                resource_id=f"RES-{i}",
                action="execute_test",
                details={"step": i},
            )
        session.commit()

    is_valid, total, genesis, last, err = store.verify_audit_chain()
    assert is_valid is True
    assert err is None
    assert total >= 5


def test_tamper_detection_breaks_hash_chain():
    store = get_db_store()

    # Add test record
    with store.get_session() as session:
        audit = store.record_audit_log(
            session=session,
            event_type="sensitive_action",
            user_id="analyst_karim",
            resource_type="alert",
            resource_id="A_TAMPER_TEST",
            action="release_funds",
            details={"approved_amount": 75000.0},
        )
        session.commit()
        tamper_seq = audit.sequence_number

    # Prior to tampering, verify chain is valid
    is_valid, _, _, _, _ = store.verify_audit_chain()
    assert is_valid is True

    # Intentionally tamper with record details in the database
    with store.get_session() as session:
        target = session.query(AuditLogRecord).filter(AuditLogRecord.sequence_number == tamper_seq).first()
        assert target is not None
        # Mutate the user_id (simulating unauthorized modification by DBA or attacker)
        target.user_id = "malicious_actor"
        session.commit()

    # Now verify_audit_chain MUST detect tampering and fail loudly!
    is_valid, total, genesis, last, err = store.verify_audit_chain()
    assert is_valid is False
    assert err is not None
    assert f"sequence {tamper_seq}" in err
    assert "Tampered record" in err or "Broken chain" in err

    # Restore legitimate state
    with store.get_session() as session:
        target = session.query(AuditLogRecord).filter(AuditLogRecord.sequence_number == tamper_seq).first()
        if target:
            target.user_id = "analyst_karim"
            session.commit()


def test_audit_verify_api_endpoint(client: TestClient):
    # 1. Login as senior analyst
    login_resp = client.post(
        "/v1/auth/login",
        json={"username": "senior_ayesha", "password": "SeniorPass123!"},
    )
    token = login_resp.json()["access_token"]

    # 2. Call /v1/audit/verify
    verify_resp = client.get(
        "/v1/audit/verify",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert verify_resp.status_code == 200
    data = verify_resp.json()
    assert "valid" in data
    assert "total_records" in data
    assert "genesis_hash" in data
    assert "last_hash" in data
