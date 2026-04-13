# 本机 GUI 自动化工具

当前仓库已经补充了一个可复用的本机 Edge 自动化脚本：

- `@C:\Users\Lucius\Desktop\asset_mgnt_report\codex\scripts\tools\local_edge_gui.py`

## 适用场景

- 复现“点击后白屏”“按钮无响应”这类本地 Web UI 问题
- 自动打开本机浏览器并执行点击、等待、截图
- 对修复后的页面做浏览器实测，而不是只看代码或只跑单元测试

## 运行前提

当前机器上已经补齐以下本地依赖，并放在用户目录下，后续可直接复用：

- Selenium Python 包目录：`C:\Users\Lucius\AppData\Local\codex_pytools`
- 浏览器：Microsoft Edge

脚本会默认把 `C:\Users\Lucius\AppData\Local\codex_pytools` 加入 `sys.path`，所以在这台电脑上通常不需要额外设置。

## 命令格式

```powershell
python scripts\tools\local_edge_gui.py --url <URL> --step expect=<文本> --step click=<按钮文案> --step expect=<文本> --step shot=<截图名>
```

支持的步骤类型：

- `expect=文本`
  - 等待页面上出现包含该文本的元素
- `click=按钮文案`
  - 点击包含该文案的按钮
- `shot=截图名`
  - 保存当前页面截图到 `output/playwright`

## 当前项目的复用示例

### 1. 验证主页可以正常打开

```powershell
python scripts\tools\local_edge_gui.py ^
  --url http://127.0.0.1:8532 ^
  --step expect=资产管理报表控制台 ^
  --step shot=home
```

### 2. 验证主报表工作台可打开并可返回主页

```powershell
python scripts\tools\local_edge_gui.py ^
  --url http://127.0.0.1:8532 ^
  --step expect=资产管理报表控制台 ^
  --step click=打开 主报表工作台 ^
  --step expect=主报表模块 ^
  --step shot=main-workspace ^
  --step click=返回概览 ^
  --step expect=资产管理报表控制台 ^
  --step shot=back-home
```

### 3. 验证清空结果面板不会打空页面

```powershell
python scripts\tools\local_edge_gui.py ^
  --url http://127.0.0.1:8532 ^
  --step expect=资产管理报表控制台 ^
  --step click=清空结果面板 ^
  --step expect=资产管理报表控制台 ^
  --step shot=clear-result
```

## 输出位置

默认截图输出到：

- `@C:\Users\Lucius\Desktop\asset_mgnt_report\codex\output\playwright`

也可以用 `--output-dir` 指定其他目录。

## 复用方法

后续如果你要排查别的本地页面，只需要改三类参数：

1. `--url`
   - 改成目标页面地址
2. `expect=...`
   - 改成你希望页面出现的关键文本
3. `click=...`
   - 改成你要点击的按钮文案

也就是说，这个脚本不是只给当前 Web UI 用的，而是可以反复用于：

- 本地 Streamlit 页面
- 本地 Flask / FastAPI / Django 页面
- 其他能在 Edge 中打开的本机网页

## 注意事项

- 这个脚本依赖页面按钮文案做定位，所以按钮文字变了，命令里的 `click=` 文本也要一起改。
- 如果页面启动较慢，可以把 `--timeout` 调大，例如 `--timeout 40`。
- 如果你只想后台验证，不弹出浏览器窗口，可以加 `--headless`。
