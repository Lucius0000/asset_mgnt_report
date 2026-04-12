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

## 5.1 当前项目对应的 Dockerfile 占用空间及位置

以下数据为当前机器在 `2026-04-12` 的实测结果：

- `Dockerfile` 文件位置：
  - `C:\Users\Lucius\Desktop\asset_mgnt_report\codex\Dockerfile`
- `Dockerfile` 文件大小：
  - `448 Bytes`
- 当前项目已构建镜像：
  - `asset-mgnt-report:latest`
  - `asset-mgnt-report:test`
- 每个镜像显示大小：
  - `1.53 GB`

需要注意两点：

- `Dockerfile` 本身只是一个很小的文本文件，几乎不占空间
- 真正占空间的是它构建出来的镜像、容器和 Build Cache

当前项目镜像数据实际存放在 Docker Desktop 的数据盘里，而不是直接散落在项目目录中：

- Docker Desktop 数据盘：
  - `C:\Users\Lucius\AppData\Local\Docker\wsl\disk\docker_data.vhdx`

## 5.2 项目修改后，什么时候需要改 Dockerfile

### 不需要修改 Dockerfile 的情况

如果你改的是下面这些内容，通常**不需要改 Dockerfile**：

- Python 脚本逻辑
- `src/`、`scripts/` 下的算法和报表代码
- `Readme.md`
- `docs/`
- `data/seeds/` 中的数据文件
- Streamlit 页面逻辑
- `compose.yaml` 以外的普通项目文件

这类修改通常只需要重新构建镜像并重启容器：

```powershell
docker compose up -d --build amr-ui
```

### 可能需要修改 Dockerfile 的情况

如果你改的是下面这些内容，就要考虑修改 Dockerfile：

- 新增了 Python 依赖，且安装方式发生变化
- 新增的依赖需要 Linux 系统库，例如：
  - 编译器
  - `libpng`
  - `freetype`
  - 数据库客户端库
- 需要安装新的系统工具，例如：
  - `git`
  - `curl`
  - `ffmpeg`
- 想更换基础 Python 版本
- 想改容器默认启动命令
- 想改容器内部的工作目录、默认环境变量、暴露端口

### 会自动修改吗

不会。

- Docker 不会根据你的项目代码自动改写 `Dockerfile`
- `Dockerfile` 是你手工维护的一份构建说明书
- 项目代码变了，Docker 最多只能在你重新构建时重新执行它，不能自己推断你要怎样改

### 如果需要手动修改，怎么改

常见修改方式如下：

#### 1. 增加 Python 依赖

一般先改：

- `requirements.txt`

如果只是普通 Python 包，通常不需要改 Dockerfile，只要重新构建：

```powershell
docker build -t asset-mgnt-report .
```

#### 2. 增加系统级依赖

如果某个包在 Linux 里需要编译或依赖系统库，就要改 Dockerfile 里的 `apt-get install` 段，例如：

```dockerfile
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        pkg-config \
        libfreetype6-dev \
        libpng-dev \
    && rm -rf /var/lib/apt/lists/*
```

#### 3. 修改默认启动命令

如果你想把默认启动从主报表改成 Web UI 或别的脚本，需要改 Dockerfile 末尾的 `CMD`，或者改 `compose.yaml` 中的 `command`

### 修改后怎么应用

修改 `Dockerfile` 或 `requirements.txt` 后，不会自动生效，必须重新构建镜像并重建容器：

```powershell
docker compose up -d --build amr-ui
```

如果只想更新镜像、不立即启动，也可以：

```powershell
docker build -t asset-mgnt-report .
```

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
docker compose run --rm amr-cli python -m scripts.main
```

### 运行 Gainer

```powershell
docker compose run --rm amr-cli python -m scripts.gainer
```

### 运行整体表

```powershell
docker compose run --rm amr-cli python -m scripts.overall
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
docker run --rm asset-mgnt-report python scripts/main.py
```

更稳妥的模块运行方式是：

```powershell
docker run --rm asset-mgnt-report python -m scripts.main
```

## 11. 源码分享和镜像分享的区别

### 分享源码

- 适合技术协作者
- 需要对方自己执行 `docker build`

### 分享镜像

- 适合不熟悉开发环境的人
- 对方不用重新安装 Python 依赖
- 只需要 Docker

## 11.1 当前电脑的 Docker 程序总占用空间及位置

以下数据为当前机器在 `2026-04-12` 的实测结果：

### 1. Docker Desktop 程序安装目录

- 路径：
  - `C:\Program Files\Docker`
- 当前目录大小：
  - `3.63 GB`

这部分主要是：

- Docker Desktop 程序本体
- CLI 插件
- 内置组件

### 2. Docker 数据盘

- 路径：
  - `C:\Users\Lucius\AppData\Local\Docker\wsl\disk\docker_data.vhdx`
- 当前文件大小：
  - `4.02 GB`

这部分主要存放：

- 镜像层
- 容器可写层
- Build Cache
- Docker 内部数据

### 3. 当前 Docker 内部对象占用

根据 `docker system df` 的结果：

- Images：
  - `2.572 GB`
- Containers：
  - `23.36 MB`
- Local Volumes：
  - `0 B`
- Build Cache：
  - `1.396 GB`

### 4. 当前已知总占用

如果按“程序安装目录 + 数据盘”粗略估算，当前机器 Docker 相关占用约为：

- `3.63 GB + 4.02 GB ≈ 7.65 GB`

注意：

- 这是当前时点的实测值，不是固定值
- 以后构建更多镜像、产生更多缓存后，这个数字还会继续增长

## 11.2 当前电脑的 Docker 配置

以下为当前机器的关键 Docker 配置快照：

### Docker Engine / Desktop

- Docker Server Version：
  - `29.0.1`
- 运行环境：
  - `Docker Desktop`
- 容器类型：
  - `Linux`
- 架构：
  - `x86_64`
- Storage Driver：
  - `overlayfs`
- Docker Root Dir：
  - `/var/lib/docker`

### 资源配置

- 可用 CPU：
  - `16`
- 可用内存：
  - `8187473920 Bytes`，约 `7.62 GB`

### 代理配置

- HTTP Proxy：
  - 已配置
- HTTPS Proxy：
  - 已配置
- No Proxy：
  - 已配置 Docker 内部域名例外规则

### Docker Desktop 用户设置文件

- 路径：
  - `C:\Users\Lucius\AppData\Roaming\Docker\settings-store.json`

当前能确认的关键设置包括：

- `AutoStart = false`
- `EnableDockerAI = true`
- `UseContainerdSnapshotter = true`

### 本项目当前 compose 运行方式

- 服务数量：
  - `2`
- 服务名称：
  - `amr-ui`
  - `amr-cli`
- 对外端口：
  - `8501`
- 挂载目录：
  - `./data/local -> /app/data/local`
  - `./output -> /app/output`
  - `../main -> /baseline_main`（只读，用于 main / codex 对比）

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
docker compose run --rm amr-cli python scripts/main.py
docker compose run --rm amr-cli python -m scripts.main
docker save -o asset-mgnt-report.tar asset-mgnt-report
docker load -i asset-mgnt-report.tar
```
