def events(client, request_id):
    return client.get(f"/api/v1/requests/{request_id}/events").json()


def test_low_cost_request_is_auto_approved_with_explanation(client, make_request):
    req = make_request(estimated_cost=20, justification="Need a USB-C adapter for demos")
    assert req["status"] == "approved"
    assert req["decision_rule"] == "low-cost"
    assert req["estimated_cost"] == 20
    assert req["allowed_transitions"] == ["cancelled", "provisioning"]

    log = events(client, req["id"])
    assert [(e["from_status"], e["to_status"], e["actor"]) for e in log] == [
        (None, "pending", "E100"),
        ("pending", "approved", "policy-engine"),
    ]
    assert log[1]["reason"].startswith("[low-cost]")


def test_over_budget_request_is_auto_rejected(make_request):
    req = make_request(estimated_cost=12000)
    assert (req["status"], req["decision_rule"]) == ("rejected", "budget-cap")
    assert req["allowed_transitions"] == []


def test_full_happy_path(client, make_request):
    req = make_request()
    assert req["status"] == "pending"
    rid = req["id"]

    steps = [
        ("approve", {"actor": "M1", "reason": "budget OK"}, "approved"),
        ("provision", {"actor": "it-bot"}, "provisioning"),
        ("fail", {"actor": "it-bot", "reason": "vendor out of stock"}, "failed"),
        ("provision", {"actor": "it-bot", "reason": "retry with other vendor"}, "provisioning"),
        ("complete", {"actor": "it-bot"}, "fulfilled"),
    ]
    for action, body, expected in steps:
        resp = client.post(f"/api/v1/requests/{rid}/{action}", json=body)
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == expected

    assert [e["to_status"] for e in events(client, rid)] == [
        "pending", "approved", "provisioning", "failed", "provisioning", "fulfilled"]


def test_invalid_transition_returns_409(client, make_request):
    rid = make_request()["id"]
    resp = client.post(f"/api/v1/requests/{rid}/complete", json={"actor": "it-bot"})
    assert resp.status_code == 409
    assert "pending" in resp.json()["detail"]
    assert len(events(client, rid)) == 1  # nothing recorded for the failed attempt


def test_cannot_approve_own_request(client, make_request):
    rid = make_request(employee_id="E100")["id"]
    resp = client.post(f"/api/v1/requests/{rid}/approve", json={"actor": "E100"})
    assert resp.status_code == 403


def test_only_requester_can_cancel(client, make_request):
    rid = make_request(employee_id="E100")["id"]
    assert client.post(f"/api/v1/requests/{rid}/cancel", json={"actor": "E999"}).status_code == 403
    resp = client.post(f"/api/v1/requests/{rid}/cancel", json={"actor": "E100"})
    assert resp.json()["status"] == "cancelled"


def test_reject_requires_reason(client, make_request):
    rid = make_request()["id"]
    assert client.post(f"/api/v1/requests/{rid}/reject", json={"actor": "M1"}).status_code == 422
    resp = client.post(f"/api/v1/requests/{rid}/reject", json={"actor": "M1", "reason": "no budget"})
    assert resp.json()["status"] == "rejected"
    assert events(client, rid)[-1]["reason"] == "no budget"


def test_list_filters_and_pagination(client, make_request):
    make_request(employee_id="A", estimated_cost=10)   # approved
    make_request(employee_id="A")                       # pending
    make_request(employee_id="B")                       # pending

    page = client.get("/api/v1/requests", params={"status": "pending"}).json()
    assert page["total"] == 2
    page = client.get("/api/v1/requests", params={"employee_id": "A", "limit": 1}).json()
    assert page["total"] == 2 and len(page["items"]) == 1
    assert client.get("/api/v1/requests", params={"status": "bogus"}).status_code == 422


def test_unknown_request_returns_404(client):
    assert client.get("/api/v1/requests/999").status_code == 404
    assert client.get("/api/v1/requests/999/events").status_code == 404
    assert client.post("/api/v1/requests/999/approve", json={"actor": "M1"}).status_code == 404


def test_input_validation(client):
    bad = {"employee_id": "E1", "resource_type": "laptop", "justification": "x", "estimated_cost": -5}
    assert client.post("/api/v1/requests", json=bad).status_code == 422


def test_policy_endpoints(client):
    policy = client.get("/api/v1/policy").json()
    assert policy["rules"][0]["id"] == "budget-cap"
    decision = client.post("/api/v1/policy/evaluate", json={
        "employee_id": "E1", "resource_type": "admin-rights",
        "justification": "need sudo for builds", "estimated_cost": 0}).json()
    assert decision == {"outcome": "require_manager", "rule_id": "privileged-access",
                        "reason": decision["reason"]}
    assert client.get("/api/v1/requests").json()["total"] == 0  # dry run didn't persist
