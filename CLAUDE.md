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
| 体 mask：把 SAM 的 2D mask 回映射到体网格，存 `data/npy/<vol>/masks/` | `src/volume_mask_service.py`、`tests/test_volume_mask.py` | 已提交（`5d7499f`）；spec 见 `.kiro/specs/volume-propagation/` |
| 跨切片传播：用上一张 mask 自动生成点提示，逐张推理，IoU 防漂移 | `src/propagation_service.py`、`tests/test_propagation.py` | 已提交（`5d7499f`）；spec 同上；新增 `scipy` 依赖 |
| 体 mask / 传播 API：`POST /api/npy/{vol}/mask`、`POST .../propagate`、`GET .../masks`、`GET .../mask/{name}/info`、`GET .../mask/{name}/slice/{dir}/{i}` | `src/server.py` | **未提交** |
| 前端"🔁 传播"按钮 + 范围设置面板；SAM 结果自动写入体 mask | `index.html`、`sam-client.js` | **未提交** |
| `?mode=raw|lowfreq` 切片参数 | `src/server.py`、`tests/test_slice_modes.py` | 已实现（11-12，scope S1） |
| Raw / Low-freq 切换与并排对照 | `src/static/js/compare.js` | 已实现（11-12，scope S2） |
| 高噪 / 低噪一键对照（H2 的 UI 表达） | `src/static/js/compare.js` | 已实现（11-12，scope S2：一键切换 + 并排对照） |
| `qc_service.py`：断层连续性、层位闭合差 | — | **缺失** |
| 自改进循环（≤3 轮、提前停止、保留最佳轮、轮次日志 API + UI 面板） | — | **缺失**（H3，演示高光） |
| 可复现的度量脚本（任何对外数字的来源） | `scripts/measure_lowfreq.py`、`docs/MEASUREMENTS.md` | H1/H2 已实现（11-12，scope S3）；H3 待 S5 |
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
2. ~~范围漂移~~ **已处理（A2）**：体 mask + 跨切片传播已补 spec `.kiro/specs/volume-propagation/`（事后补写，未完成项列在其 `tasks.md`）。
3. **依赖与约定**：`scipy`、新端点和新模块已登记到 `tech.md` / `structure.md`。`propagation_service.py` / `volume_mask_service.py` 的注释和报错仍为中文（已列入 volume-propagation 的 Wave 5）。
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

## 5. 开发规划与边界

**以 `.kiro/steering/scope.md` 为准**（2026-11-12 依据官方规则 PDF 全文制定，常驻注入）。要点：

- 交付方式：**test build**（公开仓库 + 测试说明），不做公网实例；规则允许"a website, functioning demo, or a test build"。项目须可运行到评审结束 **2027-01-29**。
- 范围：S1–S12 功能项 + E1–E7 稳定性 / 可执行性项；体 mask 与传播冻结；其余见 scope §3.3"不做"清单。
- 里程碑（北京时间）：M1 H1/H2 11-16 → M2 H3 11-23 → M3 产品化 + test build 11-29 → **11-30 功能冻结** → M4 12-03 提交，12-04 只作缓冲。
- Kiro 使用说明要回答规则列出的 8 个问题（IDE/CLI/Web/Crew、自定义 agent、hooks、spec 驱动、steering、MCP、PBT、powers），只写真实做过的事。

## 6. 需要人来决定的事项

见 `scope.md` §8（决策）与 §9（只能由所有者完成的事项：确认 SGSeg 归属、申请 Kiro credits、仓库公开、SAM3 权重获取渠道、第二台机器、YouTube 与 Devpost）。

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
