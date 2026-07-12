"""
test_api 公共 fixtures - 构建无 lifespan 的测试用 FastAPI 应用。

通过 dependency_overrides 注入桩 agent 与临时 storage，使 API 测试不依赖真实
LLM/向量库，且不产生 lifespan 副作用（不创建真实 storage/agent）。
认证走真实 JWT 流程（register -> login -> token），以验证 get_current_user。
"""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from lingyi.api.deps import get_agent, get_storage
from lingyi.api.routes import auth, chat, health, profiles, threads
from lingyi.storage.sqlite import SQLiteStorage


class StubAgent:
    """桩 Agent - ainvoke 返回固定 AI 消息；aget_state 返回 None（无历史）。"""

    async def ainvoke(self, state, config=None):
        return {
            "messages": [AIMessage(content="测试回复")],
            "intent_type": "chat",
            "symptoms": [],
        }

    async def aget_state(self, config):
        return None


@pytest.fixture
def api_client(tmp_path):
    """构建测试用 FastAPI 客户端（无 lifespan，依赖已注入桩）。"""
    storage = SQLiteStorage(str(tmp_path / "api_test.db"))
    asyncio.run(storage.init_db())

    app = FastAPI()
    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(threads.router, prefix="/api")
    app.include_router(profiles.router, prefix="/api")

    # 注入桩：storage 用临时库，agent 用桩（get_current_user 不覆盖，走真实 JWT）
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_agent] = lambda: StubAgent()

    client = TestClient(app)
    yield client

    asyncio.run(storage.close())


@pytest.fixture
def auth_token(api_client):
    """注册并登录一个测试用户，返回 Bearer token 字符串。"""
    api_client.post("/api/register", json={"username": "apiuser", "password": "pass1234"})
    resp = api_client.post("/api/login", json={"username": "apiuser", "password": "pass1234"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
def auth_headers(auth_token):
    """返回带 Bearer token 的请求头。"""
    return {"Authorization": f"Bearer {auth_token}"}
