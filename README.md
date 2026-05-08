# EnvAgent - 环境新闻智能采集与报告生成系统

基于多Agent协作的环境领域新闻自动采集、智能筛选与专业报告生成系统。

## 功能特点

- **多引擎搜索轮换**：搜狗 + 360 双引擎自适应轮换，自动阻断检测与冷却恢复
- **三阶段内容过滤**：搜索（高召回）→ LLM筛选评分（平衡）→ 全文浏览+摘要（高精度）
- **双层编辑Agent**：总编Agent设计大纲 + 栏目编辑Agent筛选/摘要/撰写，模拟新闻编辑室分工
- **事件驱动工作流**：基于Agently TriggerFlow的三级嵌套流程，支持并发控制与失败降级
- **环境领域专用**：YAML提示词注入环境政策、生态保护、气候变化等专业知识
- **Web交互界面**：FastAPI + SSE实时进度推送，浏览器端操作与报告查看
- **多模型兼容**：支持所有OpenAI Compatible接口的模型（DeepSeek、GPT、Claude等）

## 系统架构

```
┌──────────────────────────────────────────────────┐
│              Web界面层 (FastAPI + SSE)             │
├──────────────────────────────────────────────────┤
│            业务逻辑层 (EnvNewsCollector)            │
├──────────────────────────────────────────────────┤
│          工作流编排层 (Agently TriggerFlow)         │
│   主流程 → 栏目子流程(×N) → 摘要子流程(×M)         │
├──────────────────────────────────────────────────┤
│              工具抽象层 (Protocol)                  │
│  SearchTool(Sogou+360) │ BrowseTool │ RSSFeedTool │
└──────────────────────────────────────────────────┘
```

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/cpeterz/EnvAgent.git
cd EnvAgent
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的 LLM API 信息：

```env
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_API_KEY=your-api-key-here
```

支持任何 OpenAI Compatible 接口，例如：

| 模型 | BASE_URL | MODEL |
|------|----------|-------|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| GPT-4o | `https://api.openai.com/v1` | `gpt-4o` |
| 本地模型 | `http://localhost:8000/v1` | `your-model-name` |

### 4. 启动服务

```bash
python app.py
```

浏览器访问 `http://localhost:8080`，输入环境主题（如"碳排放政策"、"大气污染防治"），点击"开始采集"即可。

## 项目结构

```
EnvAgent/
├── app.py                    # 入口：启动Web服务
├── SETTINGS.yaml             # 全局配置
├── requirements.txt          # Python依赖
├── .env.example              # 环境变量模板
│
├── news_collector/           # 核心业务层
│   ├── config.py             # 配置加载
│   ├── collector.py          # 主类：串联Agent + 工具 + 工作流
│   ├── markdown.py           # 报告Markdown渲染
│   └── logging_utils.py      # 日志配置
│
├── tools/                    # 数据采集工具层
│   ├── base.py               # Protocol接口定义
│   ├── search.py             # 搜狗+360多引擎搜索
│   ├── browse.py             # 网页内容抓取
│   └── rss_feed.py           # RSS源采集
│
├── workflow/                 # TriggerFlow工作流层
│   ├── common.py             # 共享配置与Agent创建
│   ├── env_news.py           # 主流程图构建
│   ├── report_chunks.py      # 大纲生成、报告渲染
│   ├── column_chunks.py      # 栏目搜索、筛选、撰写
│   └── summary_chunks.py     # 摘要批处理
│
├── prompts/                  # YAML提示词模板
│   ├── create_outline.yaml   # 大纲生成
│   ├── pick_news.yaml        # 新闻筛选
│   ├── summarize_news.yaml   # 新闻摘要
│   └── write_column.yaml     # 栏目撰写
│
├── web/                      # Web界面层
│   ├── server.py             # FastAPI服务器
│   ├── routes.py             # API路由 + SSE
│   ├── templates/index.html  # 页面模板
│   └── static/               # CSS + JS
│
├── docs/                     # 文档
│   └── 技术报告.md            # 技术报告
│
└── outputs/                  # 生成的报告
```

## 配置说明

`SETTINGS.yaml` 主要配置项：

| 配置 | 说明 | 默认值 |
|------|------|--------|
| `MODEL.provider` | 模型提供商 | `OpenAICompatible` |
| `SEARCH.max_results` | 每组搜索最大结果数 | `10` |
| `SEARCH.timelimit` | 搜索时间范围（d=日/w=周/m=月） | `d` |
| `RSS.enabled` | 是否启用RSS源采集 | `true` |
| `WORKFLOW.max_column_num` | 最大栏目数 | `3` |
| `WORKFLOW.max_news_per_column` | 每栏目最大新闻数 | `4` |
| `WORKFLOW.output_language` | 输出语言 | `Chinese` |
| `WORKFLOW.column_concurrency` | 栏目并发数 | `1` |
| `WORKFLOW.summary_concurrency` | 摘要并发数 | `3` |
| `OUTLINE.use_customized` | 使用自定义大纲 | `false` |
| `WEB.port` | Web服务端口 | `8080` |

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | Web主页面 |
| `POST` | `/api/collect` | 触发新闻采集（body: `{"topic": "碳排放政策"}`） |
| `GET` | `/api/status/{task_id}` | SSE实时进度推送 |
| `GET` | `/api/reports` | 获取历史报告列表 |
| `GET` | `/api/reports/{filename}` | 获取单篇报告内容 |

## 工作流程

```
用户输入主题
    │
    ▼
总编Agent生成大纲（栏目标题 + 搜索关键词）
    │
    ▼
┌───────────── 对每个栏目 ─────────────┐
│  搜索引擎(Sogou/360) + RSS 并行采集   │
│           │                          │
│           ▼                          │
│  栏目编辑Agent筛选评分 → 选取Top-N     │
│           │                          │
│           ▼                          │
│  ┌─── 对每条新闻（并发=3）───┐         │
│  │  浏览全文 → Agent摘要生成  │         │
│  │  失败 → 调度备用候选       │         │
│  └───────────────────────┘         │
│           │                          │
│           ▼                          │
│  栏目编辑Agent撰写导语 + 精炼评语       │
└─────────────────────────────────────┘
    │
    ▼
渲染Markdown报告 → 保存至 outputs/
```

## 输出示例

系统生成的报告包含结构化的新闻简报，示例标题：

- 碳排放政策日报：全国碳市场扩围、地方配套细则与企业减排压力同步升温
- 大气污染防治日报：政策执法、重点区域治理与减排进展
- 环保督察日报：政策整改、地方落实与典型问题追踪

每条新闻包含：标题、来源链接、专业摘要、推荐理由。

## 技术栈

- **Agent框架**：[Agently](https://github.com/AgentEra/Agently) (TriggerFlow事件驱动)
- **Web框架**：FastAPI + Jinja2 + SSE
- **搜索引擎**：搜狗 + 360（httpx + BeautifulSoup解析）
- **网页浏览**：Agently内置Browse工具（BS4/Playwright）
- **RSS解析**：feedparser
- **LLM接口**：OpenAI Compatible（支持DeepSeek/GPT/Claude等）

## License

MIT
