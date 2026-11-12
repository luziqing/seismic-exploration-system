# CLAUDE.md — SamForGeophysics (Kiroween 2026 · Frankenstein)

> 面向接手本项目的 Claude / Kiro agent。与 `GEMINI.md` 定位相同，但以 **2026-11-09 的代码实况** 为准，并给出到截止日为止的总体规划。
> 硬规则以 `AGENTS.md` 和 `.kiro/steering/*.md` 为准；本文与它们冲突时，以它们为准。

---

## 0. 阅读顺序

1. `AGENTS.md`：不可违反的规则。
2. `.kiro/steering/`：`product.md` / `tech.md` / `structure.md` / `competition.md` 常驻注入；`seismic-domain.md` 自动加载；`sources.md` 手动引用（`#sources`）。
3. `.kiro/specs/samforgeophysics-mvp/`：`requirements.md` → `design.md` → `tasks.md`（任务勾选以此为准）。
4. `docs/COMPETITION_RULES.md`（2026-11-08 核实的官方规则摘要）、`docs/PROJECT_PLAN.md`（范围、演示分镜、风险）。
5. `HANDOFF.md`、`GEMINI.md`：历史交接，部分内容已过时（见 §3）。

---

## 1. 项目一句话

把视觉基础模型 SAM 缝合到地震解释上，借助 **低频优先条件化（H1）**、**低噪声"干净平台"对照数据（H2）** 和 **QC 驱动的自改进提示循环（H3）**，让深部弱目标变得可解释。参赛 Frankenstein 赛道。

不声称首次把 SAM 用于地震（先例：arXiv:2407.14121、arXiv:2606.15786）。UAV / 量子传感仅为背景叙事，从未实现。

---

## 2. 功能清单（实况，2026-11-09）

状态说明：**已提交** = 在 `kiro` 分支 git 历史中；**未提交** = 工作区里其他 agent 的改动，尚未提交；**缺失** = 尚无代码。实测结果见 §2.4。

### 2.1 数据与合规底座（Wave 1，已提交）

| 功能 | 位置 | 状态 |
|---|---|---|
| 确定性合成体（高噪 `synthetic_deep_v1` / 低噪 `synthetic_deep_v1_clean`）+ 真值 mask（fault / horizon / deep_target） | `scripts/generate_synthetic_seismic.py` | 已提交，`--verify-only` 字节级复验 |
| 合规自检（`.kiro` 可见性、禁用表述、数据来源） | `scripts/preflight.py` | 已提交 |
| 3 个 hook 文件（全部为 `PostFileSave`，调用 preflight / 生成器复验，另有 1 个 agent 提示） | `.kiro/hooks/*.json` | 已提交 |
| 1 个 spec + 6 个 steering | `.kiro/specs/`、`.kiro/steering/` | 已提交 |
| npm 统一脚本（`start` / `test` / `check` / `data:*` / `preflight`），端口 9339 | `package.json`、`scripts/run.js` | 已提交 |
| 首次打开自动加载卷 + 卷切换器 | 前端 | 已提交（`f0ad826`） |

### 2.2 继承自 SGSeg 的解释平台（已提交）

| 功能 | 位置 |
|---|---|
| npy 卷浏览：inline / crossline / timeslice，二进制 float32 + `X-Rows`/`X-Cols` | `src/npy_service.py`、`src/server.py` |
| SEG-Y 上传转换；Zarr / VDS 备用后端（不在演示路径上） | `src/sgy_service.py`、`zarr_service.py`、`vds_service.py` |
| SAM 嵌入 + 点提示推理（`/api/embed`、`/api/predict`、`/api/status`、`/api/devices`） | `src/sam_service.py`、`src/static/js/sam-client.js` |
| 拾取、GeoJSON/CSV 导出与导入、SQLite 会话 + localStorage 崩溃恢复 | `src/database.py`、`src/static/js/storage.js` |
| IoU / Dice / Precision / Recall | `src/validation_service.py` |
| 可选 LLM 解释助手（无 key 也应可用） | `src/llm_service.py`、`llm-client.js` |

### 2.3 Wave 2 及之后（多为未提交或缺失）

| 功能 | 位置 | 状态 |
|---|---|---|
| 低频条件化：沿时间轴 RFFT × 余弦锥形权重（≤14 Hz 全通，≥30 Hz 衰减到 0.05）× IRFFT | `src/lowfreq_service.py`、`tests/test_lowfreq.py` | **未提交**；`tasks.md` 已勾选；**尚未接入任何端点或 UI** |
| 体 mask：把 SAM 的 2D mask 回映射到体网格，存 `data/npy/<vol>/masks/` | `src/volume_mask_service.py`、`tests/test_volume_mask.py` | **未提交**，spec 中无对应条目 |
| 跨切片传播：用上一张 mask 自动生成点提示，逐张推理，IoU 防漂移 | `src/propagation_service.py`、`tests/test_propagation.py` | **未提交**，spec 中无对应条目；新增 `scipy` 依赖 |
| 体 mask / 传播 API：`POST /api/npy/{vol}/mask`、`POST .../propagate`、`GET .../masks`、`GET .../mask/{name}/info`、`GET .../mask/{name}/slice/{dir}/{i}` | `src/server.py` | **未提交** |
| 前端"🔁 传播"按钮 + 范围设置面板；SAM 结果自动写入体 mask | `index.html`、`sam-client.js` | **未提交** |
| `?mode=lowfreq` 切片参数 | `src/server.py` | **缺失** |
| Raw / Low-freq 切换与并排对照 | 前端 | **缺失** |
| 高噪 / 低噪一键对照（H2 的 UI 表达） | 前端 | **缺失**（目前只能靠卷切换器手动切） |
| `qc_service.py`：断层连续性、层位闭合差 | — | **缺失** |
| 自改进循环（≤3 轮、提前停止、保留最佳轮、轮次日志 API + UI 面板） | — | **缺失**（H3，演示高光） |
| 可复现的度量脚本（任何对外数字的来源） | `scripts/` | **缺失** |
| 公网可访问的运行实例 | — | **缺失** |
| 英文 UI | 前端 | **缺失**（按钮、状态文案多为中文） |

### 2.4 实测结果（2026-11-09，本机 RTX 4090 D）

环境：`.venv` 为 Python 3.12.7、NumPy 1.26.4、FastAPI 0.137.0、torch 2.6.0+cu124（CUDA 可用）、scipy 1.17.1。`HANDOFF.md` 中"本机未装 fastapi / torch"已过时。

| 检查 | 结果 |
|---|---|
| `npm run check`（JS 语法 + Python AST + preflight） | 通过 |
| `npm test`（preflight + 数据确定性复验） | 通过 |
| `.venv` 下 `pytest tests` | 79 passed（含三个新测试文件） |
| 启动服务 `python src/server.py`（端口 9339） | 正常；仅警告 openvds 未安装（不在演示路径上） |
| `GET /api/npy/list` | 返回两个合成卷，48×48×256 |
| 三个切片端点 | 200；inline / crossline 为 256×48，timeslice 为 48×48，均为二进制 float32 |
| `scripts/test_sam_inference.py`（5 条 inline，embed → predict → 写体 mask → 读回） | 通过。单次 embed 约 7.5 s（首次 14.7 s，含模型加载），单次 predict 约 3 s |
| `POST /api/npy/{vol}/propagate`（种子 inline 20，±2） | 首次实测：接口返回 200，但 mask 为空，没有写入切片，耗时 32 s。**修复后**：`scripts/test_propagation_e2e.py` 全部通过（见下方第 1 条） |

由实测得出的问题（只作内部记录，不对外宣传任何数字）：

1. ~~传播功能实际不可用~~ **已修复（11-09 晚）**：根因同第 2 条。修复后 `scripts/test_propagation_e2e.py` 在种子 ±5 内写入 10 张非空切片，耗时约 3 s。`total_voxels` 变化不是 bug：该脚本第二段会在同一个 mask 上重新点种子，种子切片被重写。
2. ~~SAM 延迟偏高~~ **已修复（11-09 晚）**：Ultralytics 的 `Predictor.set_image` 不在 `inference_mode` 下运行，缓存的编码器特征挂着整张 autograd 图（单次嵌入约 35 GB 显存）。`sam_service._encode_image` 现已包 `torch.inference_mode()`，回归测试见 `tests/test_sam_service.py`。修复后进程内 embed 约 0.3 s，缓存 predict 约 0.04 s；HTTP predict 约 0.4 s，多出来的时间主要是 1024×768 mask 的 JSON 序列化。另外，测试脚本原先用 `localhost`，在 Windows 上每个请求会因先试 IPv6 多等约 2 s；两个 e2e 脚本已改用 `127.0.0.1`。
3. **SAM 在弱目标上的覆盖不稳定**：逐切片 IoU 约 0.34–0.60，mask 横向铺满整个 XL 范围（0–47）。这正是 H1 和 H3 要改善的地方，但只能用固定种子的脚本来测量改善幅度。
4. **`GET /api/npy/list` 返回服务器本地绝对路径**（`path` 字段）。上公网前应去掉。

---

## 3. 已发现的不一致（接手时先处理）

1. **文档滞后**：`README.md` 的 Honest status 仍写低频"not yet implemented"；`HANDOFF.md` 写"Wave 2 not started"、"3 specs"，实际只有 1 个 spec；`GEMINI.md` 未提到体 mask / 传播。
2. **范围漂移**：体 mask + 跨切片传播是计划外功能，没有 requirement / design / task。它对 Potential Impact 有帮助（从切片走向三维解释），但必须补 spec，否则既违反"spec 驱动"约定，也浪费了它作为 Kiro 使用证据的价值。
3. **依赖与约定**：`scipy` 已进 `requirements.txt`，但 `tech.md` 未登记。`propagation_service.py` / `volume_mask_service.py` 的注释和报错为中文，`structure.md` 的代码地图也未收录它们。
4. **`tasks.md` 勾选的低频任务只完成了服务层**，端点和 UI 两项仍未勾选，这一点是对的。验证前不要再勾选。
5. **未提交改动已部分验证**（§2.4）：静态检查、79 个测试、切片接口、SAM → 体 mask 链路都通过；**传播链路实测失败**。单元测试没有发现这个问题，说明 `test_propagation.py` 没有覆盖真实 SAM 输出的坐标映射。`.venv` 已具备完整后端依赖，`HANDOFF.md` 里的环境说明已过时。
6. **preflight 的禁用表述扫描不覆盖 `CLAUDE.md` / `GEMINI.md`**（只扫 README、AGENTS、HANDOFF、docs、steering、specs）。两个文件都在公开仓库里，应加入扫描目标。
7. 工作区根目录下另有一份副本 `../SamForGeophysics-kiro-handoff/`，搜索结果会重复出现。只改 `SamForGeophysics/`。

---

## 4. 硬规则（摘要，全文见 `AGENTS.md`）

- 无脚本，不出数字。对外数字必须由 `scripts/` 中固定种子的脚本复现，并标注是在本合成模型上、用声明的启发式阈值得到的。
- 不声称首次 SAM + 地震；不把 UAV / 量子传感说成已实现。
- 仓库只放公开或合成数据。`data/` 下的 `mig304.sgy`、`inp001/`、`uploads/`、`weights/` 都只在本地，绝不提交。
- `/.kiro` 必须提交，绝不进 `.gitignore`（一票否决）。
- QC 阈值是声明的启发式常量，不在演示卷上调参后当作基准汇报。
- 切片接口只用二进制 float32 + `X-Rows`/`X-Cols`，不新增 JSON 变体。
- 前端无构建步骤、无外部 CDN；只从 `/images`、`/static` 提供静态文件。
- 缺权重、缺网络、缺 API key 时，浏览、条件化、QC 都必须可用，且 UI 明确说明缺了什么。

---

## 5. 开发规划（2026-11-09 → 2026-12-04 14:00 PST）

剩余约 25 天。原则：**先补齐 H1/H2/H3 的可见闭环，再做打磨，最后留足视频与提交时间**。评分五项各 20%，Design + Presentation 合计 40%，Technological Implementation 主要看 Kiro 用得多深多广。

### 阶段 A（11-09 → 11-15）：收口 Wave 2，让 H1 / H2 可见

| # | 任务 | 验收 |
|---|---|---|
| A1 | 审查并分批提交未提交改动：lowfreq / 体 mask 各一个 commit；传播先修复 §2.4 的空 mask 问题并补一个用真实 SAM 输出的回归测试，再提交 | `npm run check`、`pytest tests`、preflight 全绿；传播能在种子 ±2 内写入非空切片 |
| A1b | 排查 SAM predict 约 3 s 的延迟（是否每次重跑 encoder） | predict 降到亚秒级，或写明原因 |
| A2 | 为体 mask + 传播补 spec：新建 `.kiro/specs/volume-propagation/`（requirements / design / tasks） | spec 与现有代码一致；`structure.md`、`tech.md` 同步 |
| A3 | `server.py` 三个切片端点支持 `?mode=raw\|lowfreq`，复用 `_npy_binary_response`，SAM 嵌入也可选用低频图 | 返回 shape 与 raw 一致；原始体不变 |
| A4 | 前端 Raw / Low-freq 切换 + 并排对照；高噪 / 低噪一键对照（同一切片位置） | 演示分镜 V2、V3 可直接录 |
| A5 | `scripts/measure_lowfreq.py`：在合成体上测深部目标区与背景的对比度（raw vs lowfreq，高噪 vs 低噪），固定种子 | 输出数字可复现，作为 README/视频中唯一的 H1/H2 数字来源 |

### 阶段 B（11-16 → 11-22）：Wave 3，H3 自改进循环（演示高光）

| # | 任务 | 验收 |
|---|---|---|
| B1 | `src/qc_service.py`：断层连续性、层位闭合差、复用 `validation_service` 的重叠指标；常量置顶声明 | 在人工构造 mask 上行为单调、可测 |
| B2 | 提示改进驱动：定位最差区域 → 欠覆盖加正点 / 过覆盖加负点 → 最多 3 轮 → 不提升即停 → 保留最佳轮 | 单测覆盖提前停止与最佳轮保留 |
| B3 | `POST /api/npy/{vol}/refine` 返回 `{round, prompts, metrics, delta}` 日志并持久化 | 日志可在 SQLite 中回放 |
| B4 | 前端逐轮 QC 面板：轮次得分、纠正提示点位、最佳轮标记 | 分镜 V5 可直接录 |
| B5 | **决策点（需人确认）**：无权重时循环用什么分割器。建议加一个明确标注为"fallback, not SAM"的确定性分割器（如包络阈值 + 区域生长），让公网实例在无 GPU / 无权重时也能跑完整循环 | 见 §6 D2 |

### 阶段 C（11-23 → 11-29）：产品化、部署、Kiro 深度

| # | 任务 | 对应评分 |
|---|---|---|
| C1 | UI 全面英文化（按钮、状态、提示、报错）；首屏即有已加载剖面、明显的提示入口、状态指示 | Design、提交合规（材料须英文） |
| C2 | 降级路径：缺权重 / 缺 key 时状态栏明确提示，主流程不白屏 | Design（F8） |
| C3 | 端到端导出检查（GeoJSON + CSV + QC 报告） | Design（F7） |
| C4 | **公网实例**：选定托管方案并上线，评委可直接打开；上线前去掉 `/api/npy/list` 中的绝对路径，关闭上传等不需要的写接口 | 提交硬性要求（F10） |
| C5 | Kiro 使用深化（见下表），并保留证据（截图、hook 日志、commit 信息） | Technological Implementation |
| C6 | 一键自检入口（页面上或 `npm test`），评委可见全绿 | Design、可信度 |

**Kiro 使用深化清单**（目前只有 1 spec / 6 steering / 3 个 `PostFileSave` hook，不足以体现"多样性与实验"）：

- **Specs**：每个特性一个 spec（`lowfreq-conditioning`、`qc-refine-loop`、`volume-propagation`、`public-deployment`），每个 spec 的 tasks 由 Kiro 执行并勾选。
- **Hooks**：新增不同触发器，例如 `PostFileSave` 于 `src/*.py` 时跑对应测试；`Stop` 时跑 `preflight --check all`；`PreToolUse` 拦截 `git add data/`；`PostFileSave` 于 `src/static/js/*.js` 时跑 `npm run check:js`。
- **Custom agents**（`.kiro/agents/`）：如 `claims-auditor`（审查对外文案是否有未复现数字）、`qc-reviewer`（审查 QC 阈值是否被调参作弊）。
- **Steering**：给 `seismic-domain.md` 之外的领域知识按 `fileMatch` 条件加载，例如 QC 指标定义只在改 `qc_service.py` 时注入。
- **CLI / Crew**：用 Kiro CLI 跑无头的 spec 任务与校验；用 Kiro Crew 做并行 worker（例如 UI 英文化与 QC 服务并行）。写进 README 时如实说明各自做了什么、和 IDE 有何不同。
- **MCP / Powers**：仅在真有用时引入（例如用 Pencil 做 UI 设计稿再落地），不为凑数。

### 阶段 D（11-30 → 12-04）：视频与提交

| 日期 | 任务 |
|---|---|
| 11-30 → 12-01 | 按 `docs/PROJECT_PLAN.md` §4 分镜录制 ≤165 s 英文视频（实操录屏，不拼静态图），上传 YouTube 公开 |
| 12-01 | README 英文定稿：Honest status 与代码一致；"How Kiro was used"回答官方三问（IDE/CLI/Web/Crew 区别、自定义 agent、hook 自动化了什么）；所有数字指向脚本 |
| 12-02 | **代码冻结**。按 `competition.md` 清单逐项勾选；GitHub About 显示 MIT；公网实例回归测试 |
| 12-03 | 提交 Devpost（预留 1 天缓冲；截止为 12-04 14:00 PST = 12-05 06:00 北京） |
| 12-04 | 仅修提交表单问题；可选 Social Blitz（`#KiroweenHackathon26`）/ Bonus Blog |

**取舍规则**：任一评分维度看起来低于 7/10，先补该维度，再加功能。P2（奖励奖项素材、Best Kiro Crew App）只在阶段 C 全部完成后考虑。

---

## 6. 需要人来决定的事项

| ID | 事项 | 建议 |
|---|---|---|
| D1 | **参赛资格**：解释平台改编自 2026 年 6 月开始的 SGSeg。官方规则要求项目在 10-30 之后开始 | 维持 README 中的公开披露，并在 Devpost Q&A 向主办方确认；不要悄悄淡化 |
| D2 | 无权重时自改进循环的分割器 | 加一个标注清楚的确定性 fallback 分割器，保证公网实例可演示 H3 |
| D3 | 公网托管方案与模型选择。`sam3.pt` 的许可与是否可自动下载需核实；若不能在公网实例中合法、自动获取权重，考虑可自动下载的较小 SAM 变体，或仅在 fallback 模式下公开运行 | 阶段 C 开始前定案 |
| D4 | 体 mask / 跨切片传播是否进入 3 分钟演示 | 只在 H1/H2/H3 都录得出来之后，作为 10 秒以内的"三维延伸"镜头 |
| D5 | `CLAUDE.md` / `GEMINI.md` 是否保留为中文 | 提交材料须为英文；建议提交前译为英文或在 README 说明它们是内部 agent 指南 |

---

## 7. 接口与数据契约（不可改动）

- 数据体：`data/npy/<name>/amplitude.npy`，`float32`，C-order，`[nIL, nXL, nSamples]`；元数据 `meta.json`；真值 `truth/{fault,horizon,deep_target}_mask.npy`（bool，同 shape）。
- 读取：`read_inline(i)` → `(nSamples, nXL)`，`read_crossline(j)` → `(nSamples, nIL)`，`read_timeslice(k)` → `(nIL, nXL)`。
- 切片：`GET /api/npy/{vol}/slice/{inline|crossline|timeslice}/{idx}[?mode=raw|lowfreq]`，二进制 float32 + `X-Rows` / `X-Cols`。
- 体 mask：`data/npy/<vol>/masks/<name>.npy`（bool，同 shape）+ `<name>.json`（逐切片来源记录）。只写 `masks/`，绝不改写 `amplitude.npy`。

---

## 8. 完成前必跑

```bash
npm run check                                   # JS 语法 + Python AST + preflight
npm test                                        # preflight + 数据确定性复验
.venv\Scripts\python.exe -m pytest tests -q     # 全部单元测试（.venv 已有后端依赖）
# 涉及 SAM / 体 mask 时，再启动服务并跑端到端冒烟测试：
.venv\Scripts\python.exe src/server.py
.venv\Scripts\python.exe scripts/test_sam_inference.py   # 会在 data/npy/<vol>/masks/ 写测试 mask，跑完删除
```

等价的直接命令：`python scripts/generate_synthetic_seismic.py --verify-only` 与 `python scripts/preflight.py --check all`。两者都通过、并同步勾选 `tasks.md` 之后，才能宣布任务完成。
