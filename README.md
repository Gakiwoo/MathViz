<div align="center">

<img src="docs/showcase/assets/continuous-geometric-picture.gif" alt="MathViz 动画展示" width="760" />

# MathViz

### 输入一个问题 → 得到一部教学动画

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3b82f6)](https://www.python.org/)
[![Manim CE](https://img.shields.io/badge/Manim-CE-f59e0b)](https://www.manim.community/)
[![OpenAI Agents SDK](https://img.shields.io/badge/OpenAI-Agents%20SDK-111827)](https://openai.github.io/openai-agents-python/)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e)](LICENSE)

[动画画廊](docs/showcase/README.md) · [文档目录](docs/README.md)

<br />

<p align="center">
  <a href="docs/showcase/README.md"><img src="docs/showcase/assets/rhombicosidodecahedron.gif" alt="Rhombicosidodecahedron" width="24%" /></a>
  <a href="docs/showcase/README.md"><img src="docs/showcase/assets/cosmic-gravity-3d.gif" alt="Cosmic gravity 3D" width="24%" /></a>
  <a href="docs/showcase/README.md"><img src="docs/showcase/assets/continuous-geometric-picture.gif" alt="GRPO manifold" width="24%" /></a>
  <a href="docs/showcase/README.md"><img src="docs/showcase/assets/derivative-visualization.gif" alt="Derivative" width="24%" /></a>
</p>

<p align="center">
  <a href="docs/showcase/README.md"><img src="docs/showcase/assets/prolip-scene.gif" alt="ProLIP" width="24%" /></a>
  <a href="docs/showcase/README.md"><img src="docs/showcase/assets/lorenz-attractor.gif" alt="Lorenz" width="24%" /></a>
  <a href="docs/showcase/README.md"><img src="docs/showcase/assets/hopf-fibration.gif" alt="Hopf fibration" width="24%" /></a>
  <a href="docs/showcase/README.md"><img src="docs/showcase/assets/fourier-epicycles.gif" alt="Fourier epicycles" width="24%" /></a>
</p>

**MathViz 帮助教师、家教和家长将数学问题转化为可审查、可编辑、可复用的视觉化教学动画。**

</div>

---

## 教师控制台

一键启动 Web 界面，无需命令行操作：

```bash
./scripts/start-teacher-console.sh   # macOS / Linux
scripts\start-teacher-console.bat    # Windows
```

启动后浏览器打开 `http://127.0.0.1:7860`，你会看到一个三栏式工作台：

| 区域 | 功能 |
|------|------|
| **左侧栏** | 选择 AI 模型（DeepSeek/Qwen/Kimi/GLM/豆包）、输入 API Key |
| **中间工作区** | 输入数学问题 → 点击「生成」→ 查看生成的 Manim 代码 |
| **右侧面板** | 渲染预览、健康检查、运行历史 |

所有渲染依赖（Python、FFmpeg、Manim、LaTeX）由脚本自动检测安装，首次启动约 2-5 分钟。

---

## 使用案例

### 案例一：微积分入门 — 导数即斜率

```
输入：解释导数为什么是斜率
风格：清晰课堂
受众：高中生
```

**生成产物**：
- 知识图谱标注了「平均变化率→割线→极限→切线斜率」四条前置路径
- 故事板分 3 幕：坐标系登场 → 两点连线 → 割线收紧为切线
- 最终输出 45 秒 Manim 动画，逐帧展示 `difference quotient → limit → tangent slope`

### 案例二：几何证明 — 勾股定理

```
输入：用面积法证明勾股定理
风格：几何
受众：初中生
```

**生成产物**：
- 自动拆解为直角三角形的三个正方形构图
- `a² + b² = c²` 通过面积重排可视化
- 验证报告确认无外部图片依赖，全部使用 Manim 原生图形

### 案例三：傅里叶分析 — 旋转向量

```
输入：用旋转向量解释傅里叶级数
风格：电影级
受众：大学生
```

**生成产物**：
- 本轮（epicycle）从圆心扩展到多层旋转载体
- 每层旋转频率递增，最终复现目标曲线的轨迹
- 渲染输出 MP4 + GIF 双格式

> 💡 以上案例均为真实生成结果，完整产物存档于 `runs/` 目录下。

---

## 这是什么

MathViz 是一个**从问题到教学动画**的 AI 流水线。你输入一个数学问题，它不会直接跳到代码，而是先走完一整套教学设计流程：

```
问题
  → 意图分析：学生真正想问的是什么？
  → 知识图谱：需要先理解哪些前置概念？
  → 课程编排：按什么顺序讲才能让人「恍然大悟」？
  → 数学包：关键定义、公式、例题
  → 故事板：屏幕上应该发生什么？
  → 场景规格：需要哪些 Manim 对象和动画步骤？
  → 生成代码：生成可执行的 Manim Python 代码
  → 静态验证：语法检查 + 安全沙箱
  → Manim 渲染：输出 MP4 视频
  → 视频审查 + 打包
```

每一步都输出**类型化的 JSON 产物**，可以随时停下来审查、修改中间阶段，然后重新渲染——视频不再是黑盒。

设计原则：**故事先于符号，几何先于代数，产物先于副作用。**

---

## 快速开始

### 1. 安装

```bash
git clone https://github.com/Gakiwoo/MathViz.git
cd MathViz

# 创建虚拟环境并安装
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

### 2. 启动教师控制台（推荐）

浏览器界面，支持 DeepSeek / Qwen / Kimi / GLM / 豆包等国内模型：

```bash
# macOS / Linux
./scripts/start-teacher-console.sh

# Windows
scripts\start-teacher-console.bat
```

浏览器自动打开 `http://127.0.0.1:7860`。在里面选择模型、输入 API Key，即可一键生成教学方案 + Manim 代码。

### 3. 命令行快速冒烟（无需 API Key）

```bash
math-to-manim generate "解释导数为什么是斜率" --deterministic --no-render
```

### 4. 使用 AI 模型生成

```bash
export OPENAI_API_KEY="sk-..."
math-to-manim generate "用旋转向量解释傅里叶级数" --no-render
```

### 5. 安装渲染依赖（生成 MP4 视频）

```bash
# macOS
pip install -e ".[dev,render]"
./scripts/bootstrap-render-macos.sh

# Linux (Debian/Ubuntu)
pip install -e ".[dev,render]"
sudo xargs -a requirements-system.txt apt-get install -y
```

---

## 一次生成会产出什么

每次运行在 `runs/<时间戳>-<标题>/` 目录下留下完整记录：

```text
runs/20260527T120000Z-derivatives-as-slopes/
├── request.json              # 原始请求
├── intent.json               # 意图分析
├── knowledge_graph.json      # 知识图谱
├── curriculum.json           # 课程编排
├── math_packet.json          # 数学定义与公式
├── storyboard.json           # 视觉故事板
├── scene_spec.json           # 场景规格（可手动编辑）
├── generated_code.json       # 生成的代码
├── generated_scene.py        # 可执行的 Manim 脚本
├── validation_report.json    # 静态验证报告
├── render_result.json        # 渲染结果
├── review_report.json        # 视频审查
├── animation_package.json    # 完整打包
└── manifest.json             # 清单
```

---

## 代码仓库结构

```
math_to_manim/
├── agents/       # 流水线阶段适配器（意图、图谱、课程、数学、故事板、场景规格、代码生成、审查、渲染、打包）
├── schemas/      # Pydantic 产物契约（所有阶段的类型定义）
├── pipeline/     # 流水线编排、状态管理、追踪、修复循环
├── tools/        # 确定性工具（AST 验证、图谱操作、场景发现、Manim 修复）
├── rendering/    # Manim 和 FFmpeg 命令行封装
├── providers/    # 代码生成提供者（OpenAI Agents SDK + Codex CLI）
├── review/       # 静态审查和视频评分
└── app/          # 教师控制台（FastAPI + 原生 JS 前端）
```

---

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| 语言 | Python 3.10+ | 类型标注全覆盖 |
| 数据模型 | Pydantic v2 | 严格模式 + 契约校验 |
| AI 生成 | OpenAI Agents SDK | 结构化输出 + 多模型支持 |
| 动画引擎 | Manim CE 0.20+ | 社区版数学动画 |
| 视频处理 | FFmpeg | 格式转换 + GIF 导出 |
| 公式渲染 | LaTeX (可选) | 缺省时自动降级为纯文本 |
| Web 前端 | FastAPI + Uvicorn | 教师控制台 |
| 代码质量 | ruff + pytest | lint + 244 测试 |

---

## 支持的 AI 模型

教师控制台内置以下国内模型预设：

- **DeepSeek** (V3 / R1)
- **Qwen** (通义千问)
- **Kimi** (月之暗面)
- **GLM** (智谱)
- **豆包** (字节跳动)

以上均为 OpenAI 兼容接口，直接填入 API Key 即可使用。也可以通过 `OPENAI_API_KEY` 和 `OPENAI_MODEL` 环境变量使用任何兼容接口。

---

## Windows 注意事项

如果仓库通过 iCloud、百度网盘等在 macOS 和 Windows 间同步，`.venv/bin/` 下的 macOS shell 脚本可能导致 Windows 上运行 `manim` 时报 `[WinError 193]`。解决方法：

```powershell
Remove-Item .venv/bin/manim, .venv/bin/manimce, .venv/bin/dvisvgm -ErrorAction SilentlyContinue
Remove-Item .venv/bin/math-to-manim, .venv/bin/m2m2 -ErrorAction SilentlyContinue
```

---

## 许可证

MIT
