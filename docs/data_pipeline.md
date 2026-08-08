# 数据管道

## 概述

`data_pipeline/` 负责将 TCM 古籍文本清洗、切分为结构化的 Chunk 用于 RAG 检索，以及填充结构化知识库种子数据。包含两个模块：

| 模块 | 文件 | 职责 |
|---|---|---|
| 文本入库 | `ingest.py` | 古籍文本清洗、切分为 Chunk，写入 ChromaDB 或生成 Mock 数据 |
| 知识库种子 | `seed_knowledge.py` | 结构化知识库（本草/方剂/禁忌）种子数据填充 |

原始数据位于 `TCM_data/` 目录。

## 文本入库（ingest.py）

### 功能

读取 `TCM_data/` 目录下的古籍文本文件，使用专用 chunker 切分为 Chunk，根据 `--mode` 参数选择输出方式：

| 模式 | 说明 | 输出 |
|---|---|---|
| `json`（默认） | 切分结果保存为 JSON 文件 | `storage/chunks/{书名}.json` |
| `mock` | 从切分结果采样生成 Mock RAG 数据 | `storage/mock_rag_data.json` |
| `chroma` | 异步批量嵌入并写入 ChromaDB | `storage/chroma_db/` |

### 用法

```bash
# 输出 JSON 到 storage/chunks/
python -m data_pipeline.ingest

# 写入 ChromaDB（需 embedding 模型）
python -m data_pipeline.ingest --mode chroma

# 生成 Mock 数据
python -m data_pipeline.ingest --mode mock
```

### 命令行参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--mode` | `json` | 输出模式: json / chroma / mock |
| `--tcm-dir` | `TCM_data/` | 原始数据目录 |
| `--output-dir` | `storage/chunks/` | JSON 输出目录 |

### 支持的古籍

| 古籍 | 文件名 |
|---|---|
| 伤寒论 | 伤寒论_完整清洗版.txt |
| 金匮要略 | 金匮要略_完整清洗版.txt |
| 温病条辨 | 温病条辨_完整清洗版.txt |
| 神农本草经 | 神农本草经_完整清洗版.txt |
| 脉经 | 脉经_完整清洗版.txt |
| 黄帝内经-素问 | 黄帝内经-素问_完整清洗版.txt |

### ChromaDB 入库流程

`ingest_to_chroma(all_chunks, settings)` 异步入库：

1. 使用 `settings` 中的 embedding 配置创建嵌入模型（`create_embeddings`）
2. 创建 `ChromaRAGClient` 实例
3. 按书籍遍历，每批 `BATCH_SIZE = 64` 条文档调用 `client.add_documents()`
4. 文档 ID 用 content 的 MD5 哈希（幂等 upsert）
5. 使用 `tqdm` 显示进度

### Mock 数据生成

`generate_mock_data(all_chunks, output_path)` 从切分结果中采样生成预设检索数据：

- 每本书采样 2 条 Chunk
- 包含预设查询模式（脾胃虚寒、感冒发热等）及对应结果
- 输出到 `storage/mock_rag_data.json`

### 切分器

`data_pipeline/chunkers/` 目录包含各古籍的专用切分器，通过 `get_chunker(book_name)` 工厂获取。每个 Chunk 包含：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | `str` | 唯一标识 |
| `content` | `str` | 文本内容 |
| `metadata` | `dict` | 元数据（书名、章节等） |

## 知识库种子（seed_knowledge.py）

### 功能

将结构化的中医知识库种子数据（本草、方剂、禁忌）写入 `storage/patient_profiles.db` 的 `herbs`、`formulas`、`contraindications` 表。

### 用法

```bash
# 使用默认 db_path
python -m data_pipeline.seed_knowledge

# 指定数据库路径（测试用）
python -m data_pipeline.seed_knowledge --db-path /tmp/test.db
```

### 种子数据

| 类别 | 数量 | 数据来源 |
|---|---|---|
| 本草（Herbs） | 33 味 | 《神农本草经》、《中药学》教材 |
| 方剂（Formulas） | 22 首 | 《伤寒论》、《金匮要略》 |
| 禁忌（Contraindications） | 14 条 | 十八反/十九畏配伍 + 体质禁忌 |

### 数据模型

#### Herb（本草）

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | `str` | 药材正名 |
| `aliases` | `list[str]` | 别名 |
| `nature_flavor` | `str` | 性味 |
| `meridians` | `list[str]` | 归经 |
| `efficacy` | `str` | 功效 |
| `indications` | `list[str]` | 主治 |
| `dosage` | `str` | 用量 |
| `processing` | `str` | 炮制 |
| `contraindications` | `str` | 禁忌 |

#### Formula（方剂）

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | `str` | 方剂名 |
| `source` | `str` | 出处 |
| `composition` | `list[FormulaComponent]` | 组成（herb + dosage） |
| `indication` | `str` | 主治 |

#### Contraindication（禁忌）

| 字段 | 类型 | 说明 |
|---|---|---|
| `herb` | `str` | 药材名 |
| `type` | `str` | 类型: 体质 / 配伍 |
| `detail` | `str` | 详细说明 |
| `severity` | `str` | 严重程度: 禁用 / 慎用 |

### 禁忌数据构成

14 条禁忌由两部分组成：

| 类型 | 数量 | 说明 |
|---|---|---|
| 体质/证候禁忌 | 6 | 人参、麻黄、大黄、石膏、黄连、熟地黄 |
| 配伍禁忌 | 8 | 十八反/十九畏关键药对 |

### 幂等性

使用 upsert 语义（`INSERT ON CONFLICT DO UPDATE`），可重复运行而不会产生重复数据。

### 写入流程

```python
storage = SQLiteStorage(db_path)
await storage.init_db()

for herb in HERBS:
    await storage.upsert_herb(herb)
for formula in FORMULAS:
    await storage.upsert_formula(formula)
for ci in CONTRAINDICATIONS:
    await storage.add_contraindication(ci)

await storage.close()
```

## 原始数据目录

`TCM_data/` 存放中医古籍的清洗版纯文本文件，由 `data_pipeline/ingest.py` 读取。文件命名格式为 `{书名}_完整清洗版.txt`。
