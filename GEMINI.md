# GEMINI.md — SamForGeophysics 项目配置与操作边界

> 本文档是 Antigravity / Gemini agent 在此项目中工作的全局配置文件。
> 任何 agent 在修改代码或文档前，**必须先读完本文件**。

---

## 一、项目定位

**SamForGeophysics** — Kiroween 2026 Hackathon（Frankenstein 类别）参赛项目。

> Slogan：*"With lower frequencies and a cleaner platform, reach for deep targets once deemed 'unhearable' — quiet yourself first, then hear the Earth."*

把视觉基础模型 **SAM**（为自然图像而生）缝合到**地震解释**（从未被训练的领域），通过低频优先与低噪声条件化，让原本"听不见"的深部弱目标变得可解释。

三个核心差异点（**H1/H2/H3**，缺一即削弱创新得分）：

| ID | 差异点 | 状态 |
|---|---|---|
| H1 | 低频优先条件化（`lowfreq_service.py`） | ❌ 未实现，Wave 2 P0 |
| H2 | 低噪声平台对照（合成数据高/低噪两版） | ✅ 数据已生成 |
| H3 | QC 自改进解释循环（2–3 轮，逐轮日志） | ❌ 未实现，Wave 3 P0 |

---

## 二、仓库信息

| 项 | 值 |
|---|---|
| **GitHub** | https://github.com/luziqing/seismic-exploration-system |
| **分支策略** | `main` = 稳定提交；`kiro` = 比赛提交分支（Kiroween 评委看这个） |
| **本地路径** | `D:\26tmp\KiroProject\SamForGeophysics-kiro-handoff\SamForGeophysics\` |
| **License** | MIT（`LICENSE` 文件已存在，GitHub About 区须可见） |
| **Kiro 版本** | IDE 1.4.121 / CLI 3.1.0 / Crew 0.12.0 |

---

## 三、比赛硬约束（违反即失资格）

来源：https://kiroween.devpost.com/rules （已于 2026-11-08 核实，存档于 `docs/COMPETITION_RULES.md`）

| 约束 | 状态 |
|---|---|
| 新仓库，首次提交在 Oct 30, 2026 09:00 PT 之后 | ✅ 2026-11-08 首次 commit |
| 公开 GitHub 仓库（非 GitLab/Bitbucket） | ⏳ 需推送到 `github.com/luziqing/seismic-exploration-system` |
| 仓库根目录含 `/.kiro`，且不在 `.gitignore` | ✅ 已验证（preflight 绿） |
| 开源 License 在仓库 About 区可见 | ⏳ 推送后确认 |
| 演示视频 < 3 分钟，YouTube 公开 | ❌ 未制作 |
| 所有提交材料为英文 | ✅ README / docs 均为英文 |
| 提供公开可运行的 Working App URL | ❌ 未部署 |
| Kiro 使用说明（README 中明确段落） | ✅ 已写入 README |
| 提交截止：2026-12-04 14:00 PT（北京时间 2026-12-05 06:00） | ⏳ 26 天倒计时 |

**评审维度（各 20%，共 5 项）**：
- Technological Implementation — Kiro 用得有多深？
- Design — 完整产品体验，非 POC
- Innovation / Idea — 与 prior work 的差异
- Presentation — 端到端演示视频
- Potential Impact（注：搜索结果显示评审为 4×25% 或 5×20%，以官方 `docs/COMPETITION_RULES.md` 为准）

> ⚠️ **一票否决**：Insufficient use of Kiro will result in disqualification.

---

## 四、核心操作边界（所有 agent 必须遵守）

### 1. 诚实性红线

- **禁止**声称"首次 SAM + 地震"。Prior work 已存在并核实：
  - *Seismic Fault SAM* — arXiv:2407.14121（Chen 等，2024，微调做断层）
  - *Domain-Guided Prompting of SAM for Seismic Interpretation* — arXiv:2606.15786（Ahmad 等，2026，零样本混合提示）
- **禁止**编造数字。任何对外数字必须能由 `scripts/` 内固定种子脚本复现。
- **禁止**把 UAV/量子传感写成已实现硬件；仅作背景叙事。
- **禁止**把在演示数据上调出来的 QC 阈值包装成通用基准。

### 2. 数据合规

- 仅使用公开/合成数据。
- 仓库内不得有模型权重（`*.pt`/`*.pth`）、大体积数据（`data/npy/`）、第三方专有材料。
- 均已在 `.gitignore` 中排除，`preflight.py` 也会检查。

### 3. `/.kiro` 保护

- `/.kiro` 必须始终在仓库根目录且已提交。
- **绝对禁止** 在 `.gitignore` 中加任何忽略 `.kiro` 的规则。
- 任何修改 `.gitignore` 的操作后，必须重新跑 `python scripts/preflight.py --check kiro`。

### 4. 分支规则

- **`main`** — 日常开发稳定提交
- **`kiro`** — 比赛提交分支，评委查看。推送到此分支前必须：
  1. `python scripts/generate_synthetic_seismic.py --verify-only` → PASS
  2. `python scripts/preflight.py --check all` → 三绿
  3. `node --check src/static/js/*.js` → 无语法错误

### 5. 验证命令（任务完成前必跑）

```bash
# 数据确定性校验
python scripts/generate_synthetic_seismic.py --verify-only

# 合规三项检查（.kiro 可见性 / 禁用措辞 / 数据合规）
python scripts/preflight.py --check all

# 前端语法检查（无需 npm）
node --check src/static/js/app.js
node --check src/static/js/canvas.js
node --check src/static/js/sam-client.js
node --check src/static/js/sgy-client.js
node --check src/static/js/storage.js
node --check src/static/js/llm-client.js

# Python 语法检查（无需后端依赖）
python -c "import ast,pathlib; [ast.parse(p.read_text(encoding='utf-8')) for p in pathlib.Path('src').rglob('*.py')]"
```

---

## 五、代码地图

| 路径 | 职责 |
|---|---|
| `index.html` | 前端入口（无构建步骤，classic scripts） |
| `src/server.py` | FastAPI 路由；服务静态资源 + `/api/npy/...` 切片端点 |
| `src/npy_service.py` | 数据体读取：memmap、meta.json、list_volumes |
| `src/sam_service.py` | SAM 加载 / 嵌入 / 预测；权重外置于 `data/weights/` |
| `src/validation_service.py` | IoU / Dice / Precision / Recall（纯函数，最干净的层） |
| `src/llm_service.py` | 可选 LLM 辅助（无 key 时核心路径不受影响） |
| `src/static/js/` | app.js / canvas.js / sam-client.js / sgy-client.js / storage.js |
| `scripts/generate_synthetic_seismic.py` | 确定性合成数据体 + truth masks + `--verify-only` |
| `scripts/preflight.py` | 合规检查，被 `.kiro/hooks/` 自动调用 |
| `.kiro/specs/samforgeophysics-mvp/` | requirements.md / design.md / tasks.md（任务进度权威来源） |
| `.kiro/steering/` | product / tech / structure / competition / seismic-domain / sources |
| `.kiro/hooks/` | competition-guards / data-provenance / synthetic-data |

**待实现文件**（Wave 2–3 P0）：

| 文件 | 状态 | 说明 |
|---|---|---|
| `src/lowfreq_service.py` | ❌ | 频谱加权条件化，纯 NumPy，不改原始卷 |
| `src/qc_service.py` | ❌ | 断层连续性 + 层位闭合差，复用 `validation_service` |
| `src/refine_service.py` | ❌ | 2–3 轮自改进驱动，逐轮日志 |

---

## 六、数据契约（固定不变）

```
data/npy/<name>/amplitude.npy   — C-order float32, shape [nIL, nXL, nSamples]
data/npy/<name>/meta.json       — 键：source_file, il_range, xl_range, ilines,
                                   xlines, samples, n_inlines, n_crosslines,
                                   n_samples, dt_us, shape
data/npy/<name>/truth/          — fault_mask.npy / horizon_mask.npy /
                                   deep_target_mask.npy（boolean，同 shape）
```

**切片 API**（`?mode=raw`默认，`?mode=lowfreq` 为 Wave 2 新增）：
```
GET /api/npy/{vol}/slice/inline/{i}[?mode=lowfreq]
GET /api/npy/{vol}/slice/crossline/{j}[?mode=lowfreq]
GET /api/npy/{vol}/slice/timeslice/{k}[?mode=lowfreq]
```
响应契约：二进制 `float32` + `X-Rows` / `X-Cols` 头（新端点必须遵守，不得引入 JSON 变体）。

---

## 七、Wave 进度（权威来源：`.kiro/specs/samforgeophysics-mvp/tasks.md`）

| Wave | 内容 | 状态 | 目标完成 |
|---|---|---|---|
| 1 | 仓库骨架 / `.kiro` / 合成数据 / 合规检查 | ✅ 完成（commit `70c1b42`） | 2026-11-08 |
| 2 | `lowfreq_service` + `qc_service` + 前端切换 | ⏳ 未开始 | 2026-11-16 |
| 3 | 自改进循环 + 逐轮面板 | ⏳ 未开始 | 2026-11-23 |
| 4 | UI 打磨 + 部署 + 降级路径 | ⏳ 未开始 | 2026-11-30 |
| 5 | 视频 + README + 提交 | ⏳ 未开始 | 2026-12-04 |

---

## 八、待确认的阻塞项（需 niky 拍板）

| ID | 问题 | 影响 | 状态 |
|---|---|---|---|
| A1 | 资格口径：如何在 README 描述与 SGSeg 的技术底座关系 | Eligibility note 措辞 | ❓ 待确认 |
| A2 | GitHub 账号确认：推送到 `github.com/luziqing/seismic-exploration-system` | 提交链接 | ✅ 已知（本文档） |
| A4 | 部署方案（Render / HF Spaces / Railway）| Working App URL（高风险 R2） | ❓ 待确认 |
| A3 | 评委获取 SAM 权重的方式，或是否仅展示降级模式 | F8 路径 | ❓ 待确认 |
| A7 | 视频出镜/旁白/英文配音方式 | 制作排期 | ❓ 待确认 |

---

## 九、环境说明

| 项 | 值 |
|---|---|
| OS | Windows 11 |
| Python（脚本层）| 3.13（系统 Python，可运行 `scripts/` 和语法检查） |
| Python（后端）| 须 3.10+，`requirements.txt` 中 `numpy<2.0` |
| 后端依赖 | **本机未安装**（无 fastapi / torch）→ 服务无法启动，pytest 无法跑 |
| SAM 权重 | 外置于 `data/weights/sam3.pt`，不提交；缺失须降级可用 |
| Kiro | IDE 1.4.121、CLI 3.1.0、Crew 0.12.0（已安装） |

> ⚠️ 本机无后端依赖，所有新模块（如 `lowfreq_service.py`）必须附带可独立运行的 standalone verify 脚本（纯 NumPy），不依赖 fastapi / torch。

---

## 十、变更日志

| 日期 | 内容 |
|---|---|
| 2026-11-08 | Wave 1 完成：仓库骨架、`.kiro`、合成数据生成器、合规检查三绿 |
| 2026-11-09 | P0 安全修复（删 `/static_root` 挂载）+ CDN 移除 + 文档对齐（commit `70c1b42`） |
| 2026-11-09 | git init；关联 `github.com/luziqing/seismic-exploration-system`；创建 `kiro` 分支；写入 `GEMINI.md` |
