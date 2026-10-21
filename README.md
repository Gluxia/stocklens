# StockLens

**在线演示（Live Demo）：[打开 StockLens](https://stocklens-bv4o.onrender.com)**

**公开源码：[Gluxia/stocklens](https://github.com/Gluxia/stocklens)**

StockLens 是一款证据优先的 A 股研究助手，帮助个人研究者理解企业经营并核验研究依据。当前版本支持贵州茅台（`600519.SH`）、宁德时代（`300750.SZ`）、比亚迪（`002594.SZ`）三家公司，以真实扶摇（Fuyao）财务报表和历史日线为基础，由 Python 确定性计算指标，再按配置提供受约束的 AI 解读。产品不提供买卖建议或收益保证，也不以示例数据冒充真实公司结果。

## 在线体验与核心流程

[Render 在线演示](https://stocklens-bv4o.onrender.com)已发布支持三家公司的 Phase 3。本次 Explore 推荐优化尚未合并或部署。在线演示可尝试以下问题：

- “贵州茅台的营收和净利润增长表现有何差异？”
- “贵州茅台过去一个月的股价表现如何？”
- “贵州茅台的经营表现与近期股价变化是否一致？”

核心流程是 **Ask → Plan → Diagnose → Verify → Explore**：

1. **提问（Ask）**：选择股票，输入自然语言研究问题。
2. **规划（Plan）**：通过中英文关键词规则选择研究维度，展示理由及可用范围。
3. **诊断（Diagnose）**：获取真实数据、计算指标，区分客观事实、分析解读与未知信息。
4. **核验（Verify）**：点击结论，沿证据 ID、公式和输入记录追溯原始字段。
5. **探索（Explore）**：点击后续问题，发起新的研究请求和计划。建议从审核目录中优先选择经营、盈利和股价研究方向，过滤原问题、相同语义主题及当前报告已回答的问题。最多四项，不凑数量；待验证问题最多一项并排在末尾。默认使用确定性推荐，可选 Gemini 辅助排序。

股价问题优先展开历史行情，将年度指标收进“补充财务背景”；财务问题优先显示年度指标；明确同时询问两者时展开两个区块。年度报告期与近期价格区间分别标注，不据此推断相关性或因果关系。

AI 仅在调用和校验成功时显示为 AI 解读；不可用时明确回退为确定性事实摘要。公网服务尚无服务端限流或响应缓存，请避免连续重复请求。当前状态及人工检查边界见[测试记录](TESTING.md#latest-release-validation-2026-10-21)。

## 交付材料

| 必交要求 | 对应材料 | 内容与状态 |
| --- | --- | --- |
| 可访问、可使用的公网 Web 产品 | [在线演示](https://stocklens-bv4o.onrender.com) | Phase 3 已部署；此前链接检查返回 HTTP 200，供应商状态见测试记录 |
| 公开源码及完整 README | [GitHub 仓库](https://github.com/Gluxia/stocklens)及本文 | 公开仓库；本文提供安装、配置、架构、设计取舍和限制说明 |
| AI 使用与验证记录 | [AI_USAGE_AND_VALIDATION.md](AI_USAGE_AND_VALIDATION.md#development-assistance-and-documented-human-review) | 区分 Codex 辅助开发、Gemini 运行时行为、人工审阅迭代与具体纠错记录 |
| 主流程、故障与边界测试 | [TESTING.md](TESTING.md#submission-test-coverage-and-evidence-types) | 记录自动化测试、有限真实调用、公网展示检查及待验收交互 |

## 功能与产品取舍

- **三股票选择**：目录由后端 `GET /api/stocks` 提供，默认贵州茅台；切换公司会清空旧问题、报告、错误和证据抽屉，取消旧请求，拒绝身份不符的响应。
- **财务研究**：营业收入同比增长率、合并口径净利润同比增长率、净利润率；缺失年份、无效基数和过时报告期均明确处理。
- **历史行情**：真实日线图、观测区间价格涨跌幅、最高价、最低价和有效交易观测数，显示实际日期、币种、复权方式及获取时间。
- **证据分类**：正面、负面、矛盾与混合、未知与待验证信息。仅在数据支持时分类；不会为了填满类别而编造结论，正净利润率也不自动代表有利评价。
- **证据追溯**：证据 ID → 公式 → 有序输入 ID → 原始字段、JSON 路径、报告期、单位、获取时间、原始响应及哈希。摘要保留两位小数，证据面板保留完整精度。
- **受约束解读**：AI 从 Python 验证后的目录中选择和排序解读，不自由生成财务数值；收入与利润增长的同区间比较引用两项证据，重复或近似重复解读会被拒绝。
- **清晰的失败状态**：缺失、部分可用、未支持、接口失败及 AI 回退均有说明，不生成替代行情图或虚假财务数据。

产品围绕有限白名单公司的“提问到核验”闭环设计。Python 计算数值，证据目录约束 AI 表述，数据不足时保留未知状态。相比扩充指标数量，当前更重视结果能否复算、结论能否追溯。

## Phase 3 Lite：有限三股票研究范围

| 股票 | 预设研究类型 | 分类依据 |
| --- | --- | --- |
| 贵州茅台 `600519.SH` | 白酒消费企业 | [公司官网业务简介](https://www.moutai.com.cn/mtgf/qygk/gsjj/index.html) |
| 宁德时代 `300750.SZ` | 电池与储能制造企业 | [企业公开简介](https://www.catl.com/about/profile/) |
| 比亚迪 `002594.SZ` | 汽车及多元制造企业 | [企业公开简介](https://www.bydglobal.com/cn/about) |

侧边栏显示“当前支持 3 家 A 股公司”。研究分类根据企业公开业务资料人工设置，不代表官方行业分类；不提供全市场搜索或自动行业识别。两只新增股票的证券身份、年度报表和日线已通过前期有限真实查询验证，扩展沿用现有接口与计算公式。

研究计划由用户问题与公司类型共同决定，页面“当前诊断重点”根据计划动态生成，不是固定公司介绍。问题中明确指定的维度优先；没有明确意图时，公司类型决定默认关注顺序。宁德时代优先成长、盈利及制造业证据边界；比亚迪优先盈利、成长及制造业证据边界。研发、产能、销量、订单等未实现的制造业指标明确标为未知，不输出新数值。所有财务指标仍为合并报表口径，不代表某业务分部。

目录、计划、请求及数据来源必须对应当前股票；财务源记录和日线身份继续校验，AI 只接受当前公司可用证据。后续问题沿用当前股票，切换时旧异步成功或失败均不能覆盖新状态。缺失数据与供应商失败仍明确降级，不新增指标、图表、同行比较或跨股票排名。

## 技术架构与选择原因

| 层次 | 技术 | 采用原因 |
| --- | --- | --- |
| 前端 | React、TypeScript、Vite | 支持可维护组件、类型检查和快速构建 |
| 样式与图表 | Tailwind CSS、本地 CSS、Recharts | 保持简洁的中文研究报告界面，仅对真实日线绘图 |
| 后端 | FastAPI、Python、Decimal | 复用已验证的数据逻辑，以确定性计算和结构化接口建立证据 |
| 数据源 | Fuyao API | 获取真实年度合并利润表与历史日线，不硬编码公司结果 |
| 产品内 AI | Google Gemini、OpenAI-compatible Chat Completions | 仅选择已有解读目录和证据引用；不承担指标计算 |
| 部署 | Docker、Render | 多阶段构建前端，由同一个 FastAPI 服务提供页面与 API，减少部署组件 |

OpenAI Codex 是开发阶段的实现、调试、测试和文档辅助工具；Gemini 是产品运行时的可选解读选择模型。两者角色及人工审阅边界见 [AI 使用记录](AI_USAGE_AND_VALIDATION.md)。

```text
backend/app/       Fuyao 客户端、财务和行情计算、证据、研究编排与 AI 校验
backend/tests/     计算、供应商、路由、引用、回退与 API 测试
frontend/src/      React 页面、运行时校验、行情图、证据抽屉及交互测试
frontend/          Vite/Tailwind 配置、package.json 与 lockfile
Dockerfile         前端构建及单一 FastAPI 运行环境
render.yaml        Render Docker 服务 Blueprint
```

原始 `test_api.py`、`test_financial.py`、`calculate_metrics.py` 保持不变；`pytest.ini` 不会自动收集这些真实调用脚本。财务契约和公式见 [backend/README.md](backend/README.md#source-verification-and-calculation-policy)。

## 本地安装与运行

需要 Python 3.10+（已有记录使用 3.13 验证）、Node 22.12+ 或 24，以及有效的 Fuyao key。从项目根目录执行：

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
```

已有 `.env` 时保留原文件；否则将 [.env.example](.env.example) 复制为 `.env`，填写 `FUYAO_API_KEY`。不要把真实 key 写入前端或 Git。

```sh
npm --prefix frontend ci
npm --prefix frontend run build
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

打开 <http://127.0.0.1:8000>。先构建前端，再启动后端；首次构建后需重启已有后端进程，以注册静态资源路由。无需独立生产前端服务、跨域配置或数据库。

如 npm 缓存权限异常，可用 `npm --prefix frontend ci --cache /tmp/stocklens-npm-cache`，无需修改无关目录的所有权。

### 开发时热更新

终端 1，在根目录执行：

```sh
source .venv/bin/activate
python -m uvicorn backend.app.main:app --reload --port 8000
```

终端 2，在根目录执行：

```sh
npm --prefix frontend run dev
```

打开 <http://127.0.0.1:5173>。Vite 将 `/api` 代理到 `127.0.0.1:8000`；生产环境由 FastAPI 同源提供页面与 API，前端不直接请求 Fuyao 或 LLM。

## 环境变量与密钥安全

根目录 `.env` 仅供本地使用，线上值放在 Render 的环境设置中。已导出的环境变量优先于 `.env`。真实凭据不得进入 Git、截图、前端 `VITE_*` 变量或 Docker build arguments。

| 变量 | 要求与用途 |
| --- | --- |
| `FUYAO_API_KEY` | 真实财务与行情请求必需，仅后端使用 |
| `LLM_API_KEY` | 可选 AI 密钥，需与 `LLM_MODEL` 同时配置 |
| `LLM_MODEL` | 供应商已开放的模型 ID；记录中验证过 `gemini-3.5-flash-lite` |
| `LLM_BASE_URL` | HTTPS OpenAI-compatible 基础地址，默认 `https://api.openai.com/v1` |
| `LLM_FOLLOW_UP_ENABLED` | 默认 `false`；设为 `true` 后允许一次独立的后续问题排序调用，仅在本轮 AI 解读成功且问题不触发合规过滤时执行 |
| `PORT` | 容器监听端口，默认 8000；Render 提供实际端口 |

通用 AI 配置示例：

```dotenv
LLM_API_KEY=your-server-side-key
LLM_MODEL=your-provider-model-id
LLM_BASE_URL=https://api.openai.com/v1
```

Gemini 使用 `https://generativelanguage.googleapis.com/v1beta/openai`。模型需支持 Chat Completions 的 `response_format=json_schema`。未配置 key/model 或模型不兼容时，系统回退为事实摘要，不伪装 AI 成功；不假定默认模型。修改配置后需重启 FastAPI。自动化测试无需真实供应商凭据。

后续问题推荐使用独立的结构化选择请求，不改变现有 AI 解读契约。默认不增加模型调用；开启后每轮最多额外一次，不重试，连接／读取超时分别为 3／8 秒。模型只能返回候选 ID，失败时保留确定性排序；原始用户问题不发送给推荐模型，其影响通过关键词路由、候选过滤和排序体现。估值、研发、产能和现金流等缺少数据的问题明确标为“待验证”，不会新增数据接口。此前一次真实集成验证中，Gemini 解读成功，推荐请求超时后返回了四项确定性建议；尚未验证真实成功的 Gemini 推荐响应。

## 数据来源、计算与更新范围

年度财务来自 Fuyao 的 `GET /api/a-share/financials/income-statements`，读取年度合并报表。`operating_income` 为营业收入，`net_profit` 为合并净利润，不等同于 `parent_holder_net_profit`。金额按契约核验为原币元，A 股为 CNY；报告期末按 `Asia/Shanghai` 解释。

后端请求最近最多 4 条年度记录，选择最新有效年度及紧邻上一自然年度，缺年不跨年冒充同比。营业收入和净利润同比均按 `(current - previous) / previous * 100` 计算；净利润率按 `net_profit / operating_income * 100` 计算。使用 Decimal、精度 38 和 `ROUND_HALF_EVEN`，不将二进制浮点引入财务计算。

报告按请求重新获取，不缓存或持久化。获取时间不等于披露时间，也不代表当前经营状态；最新年度早于上一自然年度时提示过时。系统未核验更近的中期报告，不提供实时流式行情。

<a id="phase-2-historical-price-research"></a>
### 历史行情方法

接口为 `GET /api/a-share/prices/historical`：每次一个 `thscode`，`interval=1d`，毫秒 Unix 时间戳 `start`/`end`，显式 `adjust=none`。契约见 [Fuyao 行情文档](https://fuyao.aicubes.cn/docs/api-reference/prices/)和[官方完整文档](https://fuyao.aicubes.cn/llms-full.txt)。真实响应已验证 `data.item[].date_ms`、OHLC，以及 `data.thscode`、`interval`、`adjust`；身份、周期或复权元数据缺失或不一致时安全拒绝。

默认窗口从上月同日（月底按实际天数截取）到北京时间的昨日，排除今日未结束日线。暂不解析其他自然语言时间范围；页面始终分别展示请求区间、实际交易观测日期和数据获取时间，均以北京时间解释；获取时间明确标注“北京时间”，不等同于交易日期。内部使用 `Asia/Shanghai`，原始时间戳不变。

- 区间价格涨跌幅：`(last_close / first_close - 1) * 100`，不含分红收益。
- 最高／最低价：有效日线 `high_price` 的最大值及 `low_price` 的最小值。
- 有效观测数：通过数值、日期和 OHLC 关系校验的唯一日线数量。

**交易日历完整性尚未核验**，因此可用行情标记为 `partial`，只描述实际返回的观测区间。无效行排除并提示；重复日期拒绝整组；不足两条不计算涨跌幅；零条不生成图表。最新观测距请求结束超过 7 个自然日时提示可能过时，这不是基于交易所日历的结论。

价格证据保留原始路径、完整数值、日期、公式和输入引用。仅图表坐标转换为 Number。图表连接已返回观测点，不插补缺失交易日；年度财务与日线不能直接构成同期因果研究。

## API

| 路径 | 功能 |
| --- | --- |
| `GET /api/stocks` | 后端统一三股票目录、公司类型、分类依据与来源；不调用供应商 |
| `GET /api/health` | 进程健康检查，不调用供应商、不消耗其额度 |
| `GET /api/diagnosis?stock_code=600519.SH` | 保留 Phase 1 财务接口 |
| `POST /api/plan` | 确定性研究计划，不请求 Fuyao |
| `POST /api/research` | 财务研究、按问题选择的历史行情、可选 AI 解读 |
| `GET /docs` | 交互式 API 文档 |

```sh
curl -X POST http://127.0.0.1:8000/api/research \
  -H 'Content-Type: application/json' \
  -d '{"stock_code":"600519.SH","question":"Compare revenue and net profit growth"}'
```

响应包含 `plan`、原有 `diagnosis`、`findings`、`observations`、`interpretations`、模式／状态、时效性及后续问题。选择价格维度时，`price_analysis` 包含行情、指标、来源和证据，否则为 null。

财务接口保留 Phase 1 的状态码与脱敏错误；研究接口可在财务或价格一侧失败时保留另一侧结果。空数据明确不可用，缺失元数据或重复记录不静默推断。HTTP 429 明确提示限流或额度问题，不绕过额度、不补造数据；重复后续研究仍会消耗真实请求。

## Docker 与现有 Render 部署

本地 Docker 可用时，从根目录执行：

```sh
docker build -t stocklens:latest .
docker run --detach --name stocklens --restart unless-stopped \
  --env-file .env -p 8000:8000 stocklens:latest
curl --fail http://127.0.0.1:8000/api/health
```

多阶段镜像构建 React，安装后端运行依赖和时区数据，以非 root 用户运行。`.env` 不进入镜像，密钥仅在运行时注入。无需持久卷，因为 MVP 不保存研究报告。

现有公网地址为 [StockLens on Render](https://stocklens-bv4o.onrender.com)，源码在 [GitHub](https://github.com/Gluxia/stocklens)。当前公网已发布 Phase 3，本次 Explore 优化尚未发布；以下配置说明以仓库中的 `Dockerfile` 和 `render.yaml` 为准。

维护或复制部署时：

1. 使用现有仓库和预期分支，当前发布版本为 `main`。检查待提交文件，不纳入 `.env`、日志、数据库或凭据；保留 `frontend/package-lock.json`。忽略规则不能清除已进入 Git 历史的密钥。
2. 在 Render 选择 **New → Blueprint**，使用根目录 `render.yaml`；或 **New → Web Service** 选择 **Docker**。Root Directory 留空，Dockerfile Path 为 `./Dockerfile`，Docker Build Context Directory 为 `.`，Health Check Path 为 `/api/health`，Docker Command override 留空。Blueprint 声明 Free 方案；复制部署时需确认账户实际可用方案。
3. 在 Render 环境设置中私密填写 `FUYAO_API_KEY`、`LLM_API_KEY`，并按需设置 `LLM_MODEL=gemini-3.5-flash-lite`、`LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai`。Blueprint 的密钥采用 `sync: false`；已有服务新增密钥应手动设置。不要上传 `.env`、传入含密钥的构建参数或设置前端 API 密钥。
4. 选择 **Deploy Blueprint**／**Create Web Service** 后，Dockerfile 执行 `npm ci` 和前端类型检查／构建，将 `frontend/dist` 复制到 Python 镜像并启动组合应用。无需单独部署前端或增加自定义构建命令。
5. 部署后检查健康状态、实际研究结果、证据和 AI 回退。复制服务时替换下方主机名：

```sh
curl --fail https://stocklens-bv4o.onrender.com/api/health
```

预期健康响应为 `{"status":"ok"}`，仅代表进程健康，不代表供应商可用。生产启动等价于：

```sh
exec python -m uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
```

`EXPOSE 8000` 是镜像元数据；进程和容器健康检查读取实际 `PORT`。生产环境不使用 Vite 开发服务器或 `--reload`。Render 在无覆盖命令时使用镜像 CMD。

部署参考：[Docker deployment](https://render.com/docs/docker)、[Web Services](https://render.com/docs/web-services)、[Blueprint specification](https://render.com/docs/blueprint-spec)、[Blueprint secrets](https://render.com/docs/blueprint-spec#prompting-for-secret-values)。

<a id="deliberate-scope-limits"></a>
## 已知限制与改进方向

- 仅支持三股票白名单、默认近一个自然月的不复权日线；交易日历完整性尚未核验。
- 估值、同行对比、新闻、导出、账户、保存报告、广泛行业分类及流式行情尚未实现。估值、现金流等问题会显示缺失证据和可用年度背景。
- 公司类型来自三股票目录中的已审阅预设，不是实时行业识别。公司类型与关键词路由不等于完整语义理解；后续问题限于审核候选目录，使用规则筛选及可选 AI 排序，不自由生成问题。
- Gemini 受供应商可用性、模型权限、延迟和额度影响；失败、拒绝、输出不合规或引用无效时保留确定性摘要。
- 无用户认证、服务端请求限流、响应缓存或分布式限流；按钮禁用无法阻止外部直接调用 API。
- 开发工具依赖审计、构建体积及依赖注释仍有告警；部分浏览器交互尚待人工验收，见 [TESTING.md](TESTING.md#interactions-still-requiring-manual-checks)。

后续优先完善交易日历覆盖核验、时间范围解析、限流缓存和更丰富的审核研究建议，再审慎扩展白名单之外的股票及诊断维度。

### 公网请求预算建议（尚未实现）

可从每客户端每分钟 5 次、全局每分钟 20 次供应商请求、最多 2 个并行研究任务开始，按实际额度调整。在可信入口或应用层同时保护 `/api/research` 和 `/api/diagnosis`，豁免健康检查和静态资源。这些数值是待实施的应用层预算建议，需结合供应商额度调整。

可按供应商、股票、期间和参数缓存成功年度报表 10 分钟，保留原获取时间及哈希，不缓存错误或冒充重新获取。AI 选择缓存还需绑定精确证据快照／ID、模型及目录版本，限制容量和有效期。单实例内存方案重启即清空；多实例需协调，当前演示默认单 worker。

## 验证状态与中文展示

本次 Explore 优化完整回归为后端 **247 项通过**、前端 **55 项通过**，TypeScript 和生产构建通过。Explore 集成验证前另执行了 **21 项后端局部测试**，不作为完整回归计数。此前凭据扫描未在可发布文件及浏览器产物中发现已配置密钥值。本次优化使用 mock 与离线测试，尚未执行新的真实 API 或浏览器验收。

页面使用 `zh-CN` 和“看清企业经营，追溯每条结论。”。`frontend/src/zh-CN.ts` 仅映射已知计划、发现和解读模板；未知模型文字不会被当作已核验结论翻译。原始字段、路径、公式、ID、用户输入及 JSON 保持原样。显示值用 decimal.js 保留两位小数，证据保留完整精度。

历次测试、真实 API 成败实验、Docker 环境限制及待完成交互检查见 [TESTING.md](TESTING.md) 和 [AI_USAGE_AND_VALIDATION.md](AI_USAGE_AND_VALIDATION.md)。
