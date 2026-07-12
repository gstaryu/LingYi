# 数据管道说明

## 概述

`data_pipeline/` 负责将 TCM 古籍文本清洗、切分为结构化的 Chunk，用于 RAG 检索。

## 切分策略

| 书籍 | 策略 | ID 前缀 |
|---|---|---|
| 伤寒论 | 按 `###` 章节 + 段落切分 | `SHL_` |
| 金匮要略 | 去重 + 按章节切分 | `JGYL_` |
| 温病条辨 | 按中文编号条目切分 | `WBD_` |
| 神农本草经 | 按药物条目切分 | `SNBCJ_` |
| 脉经 | 按章节 + `一曰` 子切分 | `MJ_` |
| 黄帝内经-素问 | 去重 + 按章节切分 | `SW_` |

## 使用方法

```bash
# 输出 JSON 到 storage/chunks/
python -m data_pipeline.ingest

# 生成 mock RAG 测试数据
python -m data_pipeline.ingest --mode mock
```

## 添加新书

1. 在 `data_pipeline/chunkers/` 下创建 `my_book.py`
2. 实现 `BaseChunker` 子类
3. 在 `registry.py` 中注册
4. 在 `ingest.py` 的 `TCM_FILES` 中添加映射
