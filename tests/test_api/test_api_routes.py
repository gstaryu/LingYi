"""
API 路由集成测试 - health / auth / chat / threads / profiles。

使用 TestClient + dependency_overrides（桩 agent、临时 storage），走真实 JWT 认证流程。
"""

from fastapi.testclient import TestClient


class TestHealthRoute:
    """健康检查（无需认证）。"""

    def test_health_ok(self, api_client: TestClient):
        resp = api_client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "rag_mode" in body


class TestAuthRoute:
    """认证流程。"""

    def test_register_and_login(self, api_client: TestClient):
        """注册后应能登录并获取 token。"""
        r = api_client.post("/api/register", json={"username": "newuser", "password": "pass1234"})
        assert r.status_code == 200

        r = api_client.post("/api/login", json={"username": "newuser", "password": "pass1234"})
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_login_wrong_password(self, api_client: TestClient):
        """错误密码应返回 401。"""
        api_client.post("/api/register", json={"username": "u2", "password": "pass1234"})
        r = api_client.post("/api/login", json={"username": "u2", "password": "wrong"})
        assert r.status_code == 401

    def test_register_duplicate(self, api_client: TestClient):
        """重复用户名应返回 400。"""
        api_client.post("/api/register", json={"username": "dup", "password": "pass1234"})
        r = api_client.post("/api/register", json={"username": "dup", "password": "pass1234"})
        assert r.status_code == 400


class TestChatRoute:
    """聊天端点（需认证，agent 已注入桩）。"""

    def test_chat_without_auth_returns_401(self, api_client: TestClient):
        """无 Bearer token 应被拒绝。"""
        r = api_client.post("/api/chat", json={"message": "你好"})
        assert r.status_code == 401

    def test_chat_with_auth(self, api_client: TestClient, auth_headers: dict):
        """带 token 的请求应返回桩 agent 的回复。"""
        r = api_client.post("/api/chat", json={"message": "你好"}, headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["response"] == "测试回复"
        assert body["thread_id"]

    def test_chat_invalid_token_returns_401(self, api_client: TestClient):
        """无效 token 应返回 401。"""
        r = api_client.post(
            "/api/chat",
            json={"message": "你好"},
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert r.status_code == 401


class TestThreadsRoute:
    """线程管理（需认证，按用户隔离）。"""

    def test_create_and_list_threads(self, api_client: TestClient, auth_headers: dict):
        """创建线程后应能在列表中查到。"""
        r = api_client.post("/api/threads", json={"title": "测试会话"}, headers=auth_headers)
        assert r.status_code == 200
        thread_id = r.json()["thread_id"]

        r = api_client.get("/api/threads", headers=auth_headers)
        assert r.status_code == 200
        ids = [t["thread_id"] for t in r.json()]
        assert thread_id in ids

    def test_threads_require_auth(self, api_client: TestClient):
        """无认证不应访问线程列表。"""
        r = api_client.get("/api/threads")
        assert r.status_code == 401


class TestProfilesRoute:
    """画像端点（需认证）。"""

    def test_get_profile_default(self, api_client: TestClient, auth_headers: dict):
        """未建档的画像应返回默认值。"""
        r = api_client.get("/api/profiles/apiuser", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["constitution"] == "未知"
        assert body["allergies"] == "无"
