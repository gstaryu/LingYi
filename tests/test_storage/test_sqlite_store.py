"""
SQLite 存储测试 — 验证用户、画像、线程的 CRUD 操作。
"""

import pytest
from lingyi.storage.sqlite import SQLiteStorage


class TestSQLiteStorage:
    """SQLiteStorage 测试套件。"""

    @pytest.fixture
    async def storage(self, tmp_path):
        """创建临时存储实例。"""
        db_path = str(tmp_path / "test.db")
        s = SQLiteStorage(db_path)
        await s.init_db()
        return s

    @pytest.mark.asyncio
    async def test_create_and_verify_user(self, storage):
        """创建用户后应能验证密码。"""
        result = await storage.create_user("testuser", "password123")
        assert result is True
        verified = await storage.verify_user("testuser", "password123")
        assert verified is True

    @pytest.mark.asyncio
    async def test_duplicate_user(self, storage):
        """重复创建用户应返回 False。"""
        await storage.create_user("testuser", "password123")
        result = await storage.create_user("testuser", "password456")
        assert result is False

    @pytest.mark.asyncio
    async def test_wrong_password(self, storage):
        """错误密码应验证失败。"""
        await storage.create_user("testuser", "password123")
        verified = await storage.verify_user("testuser", "wrongpassword")
        assert verified is False

    @pytest.mark.asyncio
    async def test_get_profile_default(self, storage):
        """不存在的画像应返回默认值。"""
        profile = await storage.get_profile("nonexistent")
        assert profile.constitution == "未知"
        assert profile.allergies == "无"
        assert profile.past_history == []

    @pytest.mark.asyncio
    async def test_update_and_get_profile(self, storage):
        """更新画像后应能正确读取。"""
        await storage.update_profile("patient1", {
            "constitution": "阳虚",
            "allergies": "花粉",
            "new_record": "风寒感冒，处方桂枝汤",
        })
        profile = await storage.get_profile("patient1")
        assert profile.constitution == "阳虚"
        assert profile.allergies == "花粉"
        assert len(profile.past_history) == 1

    @pytest.mark.asyncio
    async def test_thread_crud(self, storage):
        """线程 CRUD 应正常工作。"""
        await storage.add_thread("user1", "thread1")
        threads = await storage.get_threads("user1")
        assert len(threads) == 1
        assert threads[0].thread_id == "thread1"

        await storage.rename_thread("thread1", "新标题")
        threads = await storage.get_threads("user1")
        assert threads[0].title == "新标题"

        await storage.delete_thread("thread1")
        threads = await storage.get_threads("user1")
        assert len(threads) == 0
