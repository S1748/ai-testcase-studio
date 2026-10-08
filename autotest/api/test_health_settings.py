"""健康检查与系统设置接口。"""

import pytest


@pytest.mark.smoke
def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["mock_mode"] is True  # 测试环境必须运行在 mock 模式


def test_get_settings_fields(client):
    resp = client.get("/settings")
    assert resp.status_code == 200
    body = resp.json()
    for field in ("llm_base_url", "llm_model", "llm_mock_mode", "use_mock_llm",
                  "eval_llm_model", "embedding_model"):
        assert field in body


def test_update_llm_model_persists(client):
    resp = client.patch("/settings", json={"llm_model": "test-model-x"})
    assert resp.status_code == 200
    assert client.get("/settings").json()["llm_model"] == "test-model-x"


def test_update_does_not_clear_other_fields(client):
    before = client.get("/settings").json()
    client.patch("/settings", json={"eval_llm_model": "judge-model"})
    after = client.get("/settings").json()
    assert after["eval_llm_model"] == "judge-model"
    assert after["llm_base_url"] == before["llm_base_url"]  # 未提交的字段保持不变
