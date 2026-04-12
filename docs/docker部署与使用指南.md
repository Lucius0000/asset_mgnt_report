# Docker 部署与使用指南

## 1. Docker 是什么

Docker 可以把“代码 + 依赖环境 + 启动方式”一起打包成镜像。  
别人拿到镜像后，不需要自己重新配 Python、第三方库、代理规则或目录结构，只要能运行 Docker，就能以同样方式启动项目。

对这个项目来说，Docker 主要解决四个问题：

- 跨设备迁移时环境一致
- 协作者不需要懂 Python 依赖管理
- Web UI 可以一键启动
- 输出目录和本地数据目录可以标准化挂载

## 2. 你需要理解的四个概念

### 镜像

- 可以理解为“项目安装包模板”
- 里面包含代码、依赖、启动命令

### 容器

- 可以理解为“镜像运行后的实例”
- 你每启动一次镜像，就会得到一个容器

### 卷 / 挂载

- 用来把你电脑上的文件夹映射进容器
- 本项目主要挂载：
  - `data/local`
  - `output`

### 端口

- 用来把容器里的服务暴露给你本机浏览器
- 本项目 Web UI 使用 `8501`

## 3. 本项目的 Docker 结构

本项目采用一套镜像、两种使用方式：

- `amr-ui`
  - 给不懂代码的协作者使用
  - 启动 Streamlit Web UI
- `amr-cli`
  - 给你自己或自动化场景使用
  - 运行主报表、Gainer、整体表、校验

这样做的好处是：

- 维护成本低，不需要两套镜像
- UI 和 CLI 使用同一套代码与依赖
- 协作者和你自己都能用

## 4. 安装 Docker Desktop

### Windows 安装步骤

1. 打开 Docker Desktop 官网  
   [https://www.docker.com/products/docker-desktop/](https://www.docker.com/products/docker-desktop/)
2. 下载并安装 Docker Desktop
3. 首次启动时按提示启用 WSL2
4. 安装完成后，打开 PowerShell，执行：

```powershell
docker --version
docker compose version
```

如果都能输出版本号，说明安装成功。

## 5. 构建本项目镜像

在项目根目录执行：

```powershell
docker build -t asset-mgnt-report .
```

执行原理：

- Docker 读取 `Dockerfile`
- 先拉取基础 Python 镜像
- 安装 `requirements.txt`
- 复制项目代码到镜像里
- 生成一个名为 `asset-mgnt-report` 的本地镜像

## 6. 启动 Web UI

推荐方式：

```powershell
docker compose up amr-ui
```

启动后，用浏览器访问：

```text
http://localhost:8501
```

你会看到 Streamlit 页面，可以在页面中：

- 勾选主报表模块
- 运行主报表
- 运行 Gainer
- 运行整体表
- 运行全量校验

## 7. 使用 CLI 方式运行

### 运行主报表

```powershell
docker compose run --rm amr-cli python -m scripts.entrypoints.run_main
```

### 运行 Gainer

```powershell
docker compose run --rm amr-cli python -m scripts.entrypoints.run_gainer
```

### 运行整体表

```powershell
docker compose run --rm amr-cli python -m scripts.entrypoints.run_overall
```

### 运行回归校验

```powershell
docker compose run --rm amr-cli python -m scripts.validation.validate_outputs
```

## 8. 数据和输出怎么处理

### `data/seeds`

- 这是项目内置或受版本控制的种子数据
- 一般跟代码一起进入镜像

### `data/local`

- 放本机临时输入
- 不纳入版本控制
- 推荐通过挂载进入容器

### `output`

- 存放运行结果
- 推荐通过挂载落回你本机，便于查看 Excel、图片和日志

## 9. 挂载的原理

当你把本机目录挂载到容器时：

- 容器里写入 `/app/output`
- 实际会同步写入你电脑上的 `output`

所以你不需要从容器里“拷文件出来”，运行完成后直接在本机目录看结果即可。

## 10. 分享给协作者的方法

本项目推荐用“镜像导出包”分享，而不是先要求协作者自己构建。

### 你这边导出镜像

```powershell
docker save -o asset-mgnt-report.tar asset-mgnt-report
```

把生成的 `asset-mgnt-report.tar` 发给协作者。

### 协作者导入镜像

```powershell
docker load -i asset-mgnt-report.tar
```

然后协作者就可以运行：

```powershell
docker compose up amr-ui
```

或：

```powershell
docker run --rm asset-mgnt-report python scripts/entrypoints/run_main.py
```

更稳妥的模块运行方式是：

```powershell
docker run --rm asset-mgnt-report python -m scripts.entrypoints.run_main
```

## 11. 源码分享和镜像分享的区别

### 分享源码

- 适合技术协作者
- 需要对方自己执行 `docker build`

### 分享镜像

- 适合不熟悉开发环境的人
- 对方不用重新安装 Python 依赖
- 只需要 Docker

## 12. 常见问题

### 1. `dockerDesktopLinuxEngine` 找不到

说明 Docker Desktop 没有启动，或者 Linux 容器引擎没有正常运行。

处理方式：

- 先启动 Docker Desktop
- 等到界面显示“Engine running”
- 再重新执行 `docker build` 或 `docker compose up`

### 2. 浏览器打不开 `localhost:8501`

排查顺序：

1. 确认 `docker compose up amr-ui` 没报错
2. 确认端口 `8501` 没被占用
3. 看终端里是否出现 Streamlit 已启动提示

### 3. 容器里找不到输出文件

通常是因为没有正确挂载 `output`。  
处理方式：

- 用 `docker compose` 启动，而不是手写错误的 `docker run`
- 确认本机 `output` 目录存在

### 4. FRED_API_KEY 没生效

需要把环境变量传给 Docker。  
如果你本机已经设置了环境变量，`compose` 可以直接读取；否则需要在 `.env` 或 `compose.yaml` 里显式传入。

## 13. 与 GitHub 的关系

Docker 和 GitHub 是两件事：

- GitHub 用来同步源码
- Docker 用来分发运行环境

最推荐的协作方式是：

1. 代码放在 GitHub
2. 镜像用于分享给不会搭环境的人
3. 报表结果仍落回本地 `output`

## 14. 推荐使用顺序

如果你自己使用：

1. 先准备 `data/seeds`
2. 启动 Docker Desktop
3. `docker build -t asset-mgnt-report .`
4. `docker compose up amr-ui`
5. 用浏览器操作

如果你分享给协作者：

1. 你先构建镜像
2. `docker save` 导出镜像包
3. 协作者 `docker load`
4. 协作者 `docker compose up amr-ui`

## 15. 你最需要记住的命令

```powershell
docker build -t asset-mgnt-report .
docker compose up amr-ui
docker compose run --rm amr-cli python scripts/entrypoints/run_main.py
docker compose run --rm amr-cli python -m scripts.entrypoints.run_main
docker save -o asset-mgnt-report.tar asset-mgnt-report
docker load -i asset-mgnt-report.tar
```
