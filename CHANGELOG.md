# Changelog

## Unreleased

### 🐛 问题修复

- **修复 `restage_run` KeyError**: `locals()[类对象]` 查表导致教师控制台"单阶段重跑"对所有合法 stage 必然崩溃；改为直接从 `_STAGE_AGENTS` 解包类对象
- **统一 `RenderStatus.skipped` 语义**: `--no-render` 与"静态验证未通过"场景下 `render_result.status` 由 `failed` 改为 `skipped`（附 `reason` 元数据），与 `render_existing` 及 CHANGELOG 声明的"跳过≠失败"语义一致；CLI 摘要不再对未请求渲染的 run 误报 `Render: failed`
- **中文 prompt 运行目录回退**: `_create_run_dir` 在非 ASCII 提示词（如中文）产生空 slug 时，由恒定的 `animation` 改为内容 hash（`prompt-<sha1前8位>`），目录名保持唯一

### 🛠️ 重构与改进

- **锁定 Pydantic v2**: 移除 `schemas/base.py` 的 v1/v2 双兼容分支与 `schemas/artifacts.py` 重复验证器，依赖收紧为 `pydantic>=2,<3`，消除运行时弃用警告
- **CI ruff 范围扩展至 `tests/`**: lint 与 format 检查覆盖测试代码，清理 17 个 lint 错误
- **CI 步骤合并**: pytest 与 coverage 合并为单次 `coverage run -m pytest`，新增 `--fail-under=85` 覆盖率门槛防止回归
- **移除未使用的 gradio 依赖**: `web` extra 不再包含 `gradio`（教师控制台为 FastAPI + 原生 JS），同步更新启动脚本回退文案
- **README 测试数同步**: 技术栈表由过期的 "84 测试" 更新为 "244 测试"

### 🧪 测试

- 新增 `restage_run` 三态单元测试 + API 端到端测试（239 → 244）
- `test_schemas_base.py` 重写为 v2-only，移除基于 mock `pydantic.VERSION` 的脆弱兼容测试
- `test_render_skipped_when_validation_fails` 断言更新为 `status == "skipped"`，与文档字符串及实现语义一致

## v0.2.0 (2026-06-05)

### 🚀 新增功能

- **教师控制台 API 增强**: 新增 `/api/runs/{run_id}/render`、`/api/runs/{run_id}/restage`、`/api/runs/{run_id}/video` 端点
- **`render_existing` 静态方法**: `AnimationPipeline.render_existing()` 支持从已有运行产物重新渲染，避免重跑全流水线
- **场景/故事板主题感知**: `SceneSpecAgent` 和 `StoryboardAgent` 根据课程主题自动生成场景标题、对象和动画规格
- **`RenderStatus` 新增 `skipped`**: 支持区分"跳过渲染"和"渲染失败"
- **4 个新测试模块 (第二批)**: `test_base_agent_extended.py` (18 tests)、`test_codex_cli_extended.py` (42 tests)、`test_pipeline_extended.py` (16 tests)、`test_schemas_base.py` (6 tests)
- **pre-commit hooks 配置**: ruff lint/format + 通用检查 + pytest 自动运行

### 🛠️ 重构与改进

- **提取 Provider 工具函数**: 将 `base.py` 中的辅助函数提取到独立的 `providers/llm_helpers.py`
- **run_summary 逻辑去重**: `render_existing_run()` 改用 `AnimationPipeline.render_existing()`，消除内联重复代码
- **修复 render_existing 缩进 bug**: 原代码中 `render_existing` 因缩进错误被嵌套在 `save_json` 函数体内，根本无法作为 `AnimationPipeline` 方法调用
- **删除死代码**: 移除 `codegen.py` 中 return 语句后的不可达代码块
- **删除未使用的 `RepairAgent`**: 移除 `agents/repair.py`

### 🐛 问题修复

- 修复 `test_start_scripts` 中 shell 脚本执行权限问题（`chmod +x`）
- 修复测试环境中的 `RenderStatus` 断言（`failed` → `skipped`）
- 修复 `render_existing` 缩进 bug — 方法被错误嵌套在 `save_json` 内部

### 🧪 测试

- 测试总数：84 → **220** (+136)
- 整体覆盖率：69.1% → **87.7%**
- `providers/codex_cli.py` 覆盖率：66.2% → **100%** ✅
- `pipeline/runner.py` 覆盖率：66.0% → **98.6%**
- `agents/base.py` 覆盖率：55.1% → **88.5%**
- `cli.py` 覆盖率：0% → **88.9%**
- `app/api.py` 覆盖率：52.0% → **83.8%**
- Ruff lint：**0 errors**

### 📚 文档

- 项目品牌更名：**Math-To-Manim → MathViz**
- README 重写（520行→约200行），中文化关键部分，新增教师控制台介绍
- 新增 `docs/ARCHITECTURE.md`
- 更新 `docs/README.md` 和 `docs/showcase/README.md`
- 清理多余的中文文档目录

### 🏗️ 工程基础

- Git 仓库初始化（13 commits）
- GitHub Actions CI 配置（Python 3.10/3.11/3.12 矩阵）
- Ruff lint/format 集成并运行（201 个自动修复 + 7 个手动修复）
- `.gitignore` 全面覆盖（.venv, runs, media, build 等）
- `requirements.txt` 依赖锁文件

---

## v0.1.0 (2026-05-19)

### 🎉 初始版本

- Math-To-Manim (M2M2) 类型化 11 阶段流水线
- Intent → KnowledgeGraph → Curriculum → Math → Storyboard → SceneSpec → CodeGen → StaticReview → Render → VideoReview → Publish
- 确定性 (deterministic) 模式，无需 API Key 即可离线运行
- AST 安全沙箱（禁止危险导入/调用）
- Manim 兼容性自动修复（Checkmark → Text, RightAngle 参数修正, LaTeX 降级）
- 修复循环机制（静态验证失败/渲染失败最多重试 3 次）
- Provider-Agnostic 架构（OpenAI Agents SDK + Codex CLI 桥接）
- 跨平台启动脚本（sh/bat/ps1）
- 16 段精选 GIF 展示画廊
- 84 个测试，69.1% 覆盖率
