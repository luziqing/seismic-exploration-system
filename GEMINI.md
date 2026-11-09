# GEMINI.md — SamForGeophysics (Kiroween 2026)

> 本文档为 **SamForGeophysics** 参赛项目的核心开发与配置指南。
> 专注于 **Kiroween 2026 黑客松（Devpost, Frankenstein 赛道）** 的产品落地与竞赛交付。

---

## 一、 项目定位与核心差异点

- **定位**：将计算机视觉基础模型 **SAM** 缝合至**地震勘探解释**，通过低频优先条件化与低噪声平台，识别传统方法中弱而模糊、近乎“听不见”的深层反射目标。
- **Slogan**：*"With lower frequencies and a cleaner platform, reach for deep targets once deemed 'unhearable' — quiet yourself first, then hear the Earth."*
- **赛道**：Frankenstein（跨界缝合不相关技术）。
- **三大核心差异点（产品亮点）**：
  1. **H1 低频优先（Low-frequency first）**：深部弱信号主要残留在低频段，在输入 SAM 提示前进行保频/低频增强（`lowfreq_service.py`），同时保留原始剖面对照。
  2. **H2 干净平台（Cleaner platform）**：通过低噪声合成体（SNR=18dB vs 6dB）验证信噪比提升对弱目标提取的决定性影响。
  3. **H3 自改进解释循环（Self-improving QC loop）**：根据断层连续性（continuity）与层位闭合差（closure error）等地球物理 QC 指标，自动微调提示点/框，迭代 2–3 轮并输出逐轮得分日志。

---

## 二、 仓库与分支规范

- **公开仓库**：`https://github.com/luziqing/seismic-exploration-system.git`
- **参赛提交分支**：**`kiro`**（评委审查与 Devpost 提交分支，已跟踪 `origin/kiro`）
- **开发分支**：`main`
- **本地工作区**：`D:\26tmp\KiroProject\SamForGeophysics\`
- **开源许可证**：MIT（根目录 `LICENSE`，GitHub About 区需显示）
- **工具链要求**：Kiro IDE 1.4.121 / CLI 3.1.0 / Crew 0.12.0

---

## 三、 竞赛合规红线与评审标准

### 1. 评审五大维度（各 20%，Design + Presentation 占 40%）
- **Technological Implementation** (20%)：Kiro 深度使用（Specs / Steering / Hooks / CLI / Crew）。
- **Design** (20%)：完整产品体验，绝不仅是算法 POC（首屏直观展现、对照布局、状态反馈、无权重降级路径）。
- **Innovation / Idea** (20%)：低频 × 干净平台 × 自改进闭环的真实缝合。
- **Presentation** (20%)：< 3 分钟 YouTube 演示视频（端到端演示完整流程，拒绝静态图拼凑）。
- **Potential Impact** (20%)：切实解决深层弱目标解释痛点。

### 2. 核心红线准则
- 🚫 **绝不声称“首次 SAM + 地震”**：已有文献先例（Chen 等 2024 `arXiv:2407.14121`；Ahmad 等 2026 `arXiv:2606.15786`），我方差异点在于低频深部弱目标与自改进 QC 闭环。
- 🚫 **绝不编造未实测数字**：无脚本不出数据，所有对外展示指标均需固定随机种子可复现。
- 🚫 **UAV 与量子传感仅作背景叙事**：不可谎称已实现物理硬件。
- 🚫 **严禁上传大文件与权重**：所有 `data/*`、`*.npy`、`*.pt`、`*.ckpt`、`*.safetensors` 已由 `.gitignore` 严格排除。
- 🚫 **`/.kiro` 目录绝对保护**：根目录必须包含 `/.kiro` 且严禁进 `.gitignore`（一票否决项）。

---

## 四、 核心数据与接口契约

### 1. 地震体与切片契约
- 数据体：`data/npy/<name>/amplitude.npy`（`float32`, C-order, shape: `[nIL, nXL, nSamples]`）
- 元数据：`data/npy/<name>/meta.json`
- 标注真值：`data/npy/<name>/truth/{fault,horizon,deep_target}_mask.npy`
- 切片响应：**统一二进制 `float32` 格式**，Header 携带 `X-Rows` 与 `X-Cols`（切勿引入 JSON 变体）。

### 2. 核心切片端点
```http
GET /api/npy/{vol}/slice/inline/{i}?mode=raw|lowfreq
GET /api/npy/{vol}/slice/crossline/{j}?mode=raw|lowfreq
GET /api/npy/{vol}/slice/timeslice/{k}?mode=raw|lowfreq
```

---

## 五、 开发规划与当前任务（Wave 2 -> Wave 5）

```
[Wave 1 基础骨架]   --> [Wave 2 条件化与QC]  --> [Wave 3 自改进循环]  --> [Wave 4 产品化与部署] --> [Wave 5 视频与提交]
 (✅ 已完成全绿)           (🔥 当前主攻)              (下一步)                 (第4周)               (截止前)
```

### 当前主攻：Wave 2（低频条件化与 QC 评估）
1. `src/lowfreq_service.py`：
   - 沿时间轴做一维 RFFT，应用余弦加权窗（保留低频，衰减高频），IRFFT 还原为 float32。
   - 只读增强，绝不改写存储中的原始数据体。
   - 纯 NumPy 实现，内置独立运行验证。
2. 切片端点扩展：
   - `src/server.py` 切片端点支持 `?mode=lowfreq` 参数，返回二进制 float32。
3. `src/qc_service.py`：
   - 断层连续性度量（Fault continuity）：跨道 sample 偏差与断续惩罚。
   - 层位闭合差（Horizon closure error）：闭合测线回路追踪残差（samples / ms）。
   - Overlap 指标直接复用 `src/validation_service.py`（Dice, IoU, Precision, Recall）。
4. 前端交互支持：
   - 工具栏增加 Raw / Low-freq 视图快速切换。

---

## 六、 开发与任务验证命令（npm run 统一工作流）

项目配置了开箱即用的 npm 脚本，封装了开发启动、数据生成、语法检查与合规校验：

```bash
# 1. 启动本地开发服务 (http://localhost:8000)
npm start             # 或 npm run dev

# 2. 核心测试（自动运行 preflight 检查 + 数据确定性复验）
npm test

# 3. 一键全局静态检查（前端 JS 语法 + 后端 Python AST 解析 + 合规检查）
npm run check

# 4. 数据生成与确定性复验
npm run data:gen      # 重新生成合成数据体与真值掩膜
npm run data:verify   # 仅做字节级确定性比对

# 5. 参赛合规自检
npm run preflight     # 运行 preflight.py 检查 .kiro/claims/data
```
