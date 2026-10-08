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
    resp = client.patch("/settings", json={"llm_model": "switch-model"})
    assert resp.status_code == 200
    after = client.get("/settings").json()
    assert after["llm_model"] == "switch-model"
    # 未提交的字段必须保持原值，不能被覆盖成空
    assert after["llm_base_url"] == before["llm_base_url"]
    assert after["embedding_model"] == before["embedding_model"]
    assert after["eval_llm_model"] == before["eval_llm_model"]


def test_partial_eval_model_config_is_rejected(client):
    """评测专用模型有完整性约束：地址 / Key / 模型三项必须同时填写，或同时留空。

    只填其中一项时后端返回 400，不会把配置写坏成「半套配置」。
    """
    resp = client.patch("/settings", json={"eval_llm_model": "judge-model"})
    assert resp.status_code == 400
    assert "评测专用模型" in resp.json()["detail"]
