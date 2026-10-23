from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def client_for(tmp_path):
    settings = Settings(data_dir=tmp_path)
    return TestClient(create_app(settings))


def _claim(member_id, hospital_id, diagnosis, treatment, estimated, room, days, document_text, admitted="2026-10-14T09:30:00"):
    return {
        "member_id": member_id,
        "hospital_id": hospital_id,
        "admitted_at": admitted,
        "diagnosis": diagnosis,
        "treatment": treatment,
        "estimated_amount": estimated,
        "room_rent_per_day": room,
        "stay_days": days,
        "document_name": "admission-form.txt",
        "document_text": document_text,
    }


FORM = "Admission form\nHospital: CityCare Hospital\nDiagnosis recorded and signed.\n"


def test_health_uses_local_standins(tmp_path):
    with client_for(tmp_path) as client:
        health = client.get("/api/health").json()
    assert health["sql"] == "sqlite"
    assert health["cosmos"] == "file"
    assert health["documents"] == "local"
    assert health["coverage"] == "rules"


def test_routine_surgery_is_approved_and_confirmed(tmp_path):
    with client_for(tmp_path) as client:
        created = client.post(
            "/api/claims",
            json=_claim("MBR-1001", "HSP-CITY", "Acute appendicitis", "Laparoscopic appendectomy", 85000, 4000, 3, FORM),
        )
        assert created.status_code == 200
        body = created.json()
        assert body["outcome"] == "Approved"
        assert body["payable_amount"] == 85000
        assert body["patient_share"] == 0
        assert "assess_coverage" in {step["node"] for step in body["trace"]}
        assert {clause["clause_id"] for clause in body["cited_clauses"]} >= {"CL-SURG"}
        confirmed = client.post(f"/api/claims/{body['id']}/confirm", json={"officer_name": "Duty officer"})
        assert confirmed.status_code == 200
        assert confirmed.json()["status"] == "Confirmed"
        assert confirmed.json()["confirmed_by"] == "Duty officer"


def test_room_rent_above_cap_is_partial(tmp_path):
    with client_for(tmp_path) as client:
        created = client.post(
            "/api/claims",
            json=_claim("MBR-1002", "HSP-CITY", "Dengue fever", "Inpatient medical management", 96000, 8000, 4, FORM),
        )
        body = created.json()
    assert body["outcome"] == "Partial"
    assert body["payable_amount"] == 76000
    assert body["patient_share"] == 20000
    assert "CL-ROOM" in {clause["clause_id"] for clause in body["cited_clauses"]}


def test_waiting_period_skips_the_model(tmp_path):
    with client_for(tmp_path) as client:
        created = client.post(
            "/api/claims",
            json=_claim(
                "MBR-1003",
                "HSP-CITY",
                "Knee arthroscopy",
                "Arthroscopic repair",
                140000,
                4500,
                2,
                FORM,
                admitted="2026-10-10T09:30:00",
            ),
        )
        body = created.json()
    assert body["outcome"] == "Denied"
    assert body["payable_amount"] == 0
    assert body["coverage_provider"] == "not_called"
    assert "assess_coverage" not in {step["node"] for step in body["trace"]}
    assert "CL-WAIT" in {clause["clause_id"] for clause in body["cited_clauses"]}


def test_unreadable_form_is_referred(tmp_path):
    with client_for(tmp_path) as client:
        created = client.post(
            "/api/claims",
            json=_claim("MBR-1004", "HSP-CITY", "Chest pain", "Observation", 42000, 4000, 2, ""),
        )
        body = created.json()
    assert body["outcome"] == "Referred"
    assert body["coverage_provider"] == "not_called"
    assert "assess_coverage" not in {step["node"] for step in body["trace"]}


def test_out_of_network_is_denied(tmp_path):
    with client_for(tmp_path) as client:
        created = client.post(
            "/api/claims",
            json=_claim("MBR-1001", "HSP-LAKE", "Acute appendicitis", "Laparoscopic appendectomy", 85000, 4000, 3, FORM),
        )
        body = created.json()
    assert body["outcome"] == "Denied"
    assert "CL-NET" in {clause["clause_id"] for clause in body["cited_clauses"]}


def test_return_then_second_action_conflicts(tmp_path):
    with client_for(tmp_path) as client:
        created = client.post(
            "/api/claims",
            json=_claim("MBR-1001", "HSP-CITY", "Acute appendicitis", "Laparoscopic appendectomy", 85000, 4000, 3, FORM),
        )
        claim_id = created.json()["id"]
        returned = client.post(f"/api/claims/{claim_id}/return")
        assert returned.json()["status"] == "Returned"
        again = client.post(f"/api/claims/{claim_id}/confirm", json={"officer_name": "Duty officer"})
        assert again.status_code == 409
