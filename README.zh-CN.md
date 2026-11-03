# MetaCube RGB Web v2.0.0（PVE / Debian 13）

这是针对 **METAPHYUNI MetaCube / M11 Series-HPT** 的 Linux 原生 WMI 控制中心。基于你提供的 Windows「玄机中枢」ControlCenter 安装包，独立实现原厂可见的机身 RGB 编辑界面、系统设置和监控能力。

> **重要：这是 v2.0 实验性升级，不是完全验证的正式固件驱动。** 你实际验证成功的是 v1.0 的单色、亮度与模式。v2 新增的多色、速度、方向、循环、渐变以及性能/按键灯控制已经按原厂程序的指令结构实现，但尚未在你的机器上验证实际效果。首次请在维护窗口测试；不要直接在承载关键虚拟机业务时测试新固件指令。

## 包含哪些功能

- `metacube-rgb web` 启动本地加密令牌认证的 Web 控制台，全部 HTML/CSS/JS 随源码提供，无需前端安装依赖。
- 机身氛围灯：呼吸 / 常亮 / 旋转 / 关闭；1–6 色 RGB；亮度 0–255；旋转速度、方向；0–11 级颜色循环；渐变开关。支持**点击「应用到设备」后一次性写入**和 WMI 回读校验。
- 五个可保存/恢复的本地灯光预设，取代原 Windows 软件的 `.dat` 保存方式（无法直接导入 Windows 的二进制预设）。
- 系统：静音 / 均衡 / Turbo 档位、按键灯 0–3 级；这两种写入**默认锁定**，需显式 `--enable-platform-writes` 才能开启；Turbo 额外要求固件确认圆口适配器。
- 主机监控：Linux CPU 使用率 / 频率 / 负载、内存、磁盘、硬件温度与风扇；系统信息显示实际 PVE 主机而非虚拟机。
- WMI 能力检测：GPU 模式、Fn Lock、触摸板、RGB 键盘和其他原厂函数的**按需只读**查询。未验证的 GPU 切换、风扇强制转速、CPU 功耗等危险操作不开放。
- DKMS 自动编译 + 你已经注册的 MOK 证书签名 + 可选的 systemd 开机恢复。

完整对照：[docs/OEM_FEATURE_MATRIX.md](docs/OEM_FEATURE_MATRIX.md)。

## 安装（已有 v1.0 用户）

1. 先备份当前灯光设置：

```bash
metacube-rgb status --json > /root/metacube-rgb-backup.json
cp /etc/metacube-rgb.conf /root/metacube-rgb.conf.bak 2>/dev/null || true
```

2. 将 ZIP 上传 PVE 的 `/root/`，解压并安装：

```bash
apt update
apt install -y dkms build-essential python3 mokutil proxmox-default-headers "proxmox-headers-$(uname -r)"
cd /root
unzip -o metacube-rgb-web-v2.0.0.zip
cd metacube-rgb-web-v2.0.0
bash install.sh --enable-writes
```

**安装程序不会主动修改灯光或 PVE 引导配置。** 它先构建 v2 DKMS，确认编译后再替换现有的 v1 模块。成功时卸载旧 DKMS 版本的注册，避免未来两个版本同时构建；保留 `/usr/src/metacube-ambient-1.0.0` 作为旧版源码备份。不会删除 MOK 私钥或公钥。

如果只是维护当前 RGB 功能，**不要**在首次安装时加 `--enable-platform-writes`。若此前 v1 已设 `allow_writes=1`，省略参数会尝试继承现有权限；为明确起见仍建议显式提供 `--enable-writes`。

## 直接启动 Web

```bash
metacube-rgb web
```

默认监听 `127.0.0.1:8765`。通过 SSH 端口转发，在你的电脑上执行：

```bash
ssh -L 8765:127.0.0.1:8765 root@192.168.18.99
```

然后在浏览器打开 `http://127.0.0.1:8765`。

网页登录令牌在 PVE 上读取：

```bash
cat /etc/metacube-rgb/web.token
```

安装器生成 36 字节随机密钥的 URL-safe 表示，只在本机 root 可读取，**不会打印到 systemd 日志中**。令牌存储在浏览器的会话存储里，关闭该标签的会话后需要再次输入。

如希望直接从局域网访问，可以启动：

```bash
metacube-rgb web --host 0.0.0.0 --port 8765
```

**注意：明文 HTTP 会暴露认证令牌和控制请求。** 不要对公网开放 PVE 的 8765 端口。推荐 SSH 转发；若需要外部访问，应在受控的内网或 HTTPS 反向代理之后使用，并同时启用访问控制和防火墙。

## 开机自动启动 Web（可选）

默认不启用 systemd Web 服务。可执行：

```bash
systemctl enable --now metacube-rgb-web.service
systemctl status metacube-rgb-web.service
```

它同样只监听 `127.0.0.1:8765`。若需要自定义监听地址：

```bash
cat > /etc/default/metacube-rgb-web <<'EOF'
METACUBE_WEB_HOST=127.0.0.1
METACUBE_WEB_PORT=8765
EOF
systemctl restart metacube-rgb-web.service
```

停用服务：`systemctl disable --now metacube-rgb-web.service`。

**安全设计说明**：Web 服务需要写入 root 所有的 WMI sysfs 文件，所以以 root 启动，但监听默认限制为 loopback，并使用 Bearer token、同源校验和请求白名单。不要在未经隔离的网络上直接运行 root Web 服务。

## CLI（保留 v1 命令）

```bash
metacube-rgb status
metacube-rgb mode breath
metacube-rgb color FF0000
metacube-rgb brightness 160

# v2 扩展
metacube-rgb colors FF0000 00FF00 0000FF
metacube-rgb mode spin
metacube-rgb speed 45
metacube-rgb direction 1
metacube-rgb cycle 6
metacube-rgb transition 1

# 5 组本地预设
metacube-rgb preset save 1 --name '银河'
metacube-rgb preset list
metacube-rgb preset apply 1
metacube-rgb preset delete 1

# 系统与 OEM 诊断
metacube-rgb system
metacube-rgb oem
```

切换**性能模式或按键灯**需显式二次授权，然后重新运行安装脚本使模块参数在下次启动仍生效：

```bash
cd /root/metacube-rgb-web-v2.0.0
bash install.sh --enable-writes --enable-platform-writes
metacube-rgb platform system_mode balanced
metacube-rgb platform button_brightness 2
```

这个写入能力未在你的主机上验证，请慎用；Turbo 仅在主板 WMI 读取到圆孔适配器类型时才允许。

## 开机恢复灯光（可选）

```bash
metacube-rgb save
metacube-rgb apply --dry-run
systemctl enable --now metacube-rgb-restore.service
```

旧版 `/etc/metacube-rgb.conf` 的单色模式继续兼容。若主板能自行持久保存配置，不需要启动服务。

## DKMS 验证与回滚

```bash
uname -r
dkms status -m metacube-ambient
modinfo -F version metacube_ambient
modinfo -F signer metacube_ambient
metacube-rgb status
```

应显示 `metacube-ambient/2.0.0` 已安装、签名者仍为 `DKMS module signing key`。未来更新 PVE 内核时需要新内核 Headers，否则 DKMS 不能成功构建。升级前请通过 `dkms status` 验证新内核条目。

卸载：

```bash
cd /root/metacube-rgb-web-v2.0.0
bash uninstall.sh
```

默认保留 Web token、5 组预设和开机灯光配置；加 `--purge-user-data` 才清除这些文件。卸载不触碰 MOK 密钥、PVE 引导项或 EFI 配置。旧版源代码位于 `/usr/src/metacube-ambient-1.0.0`，可根据旧版安装包重新安装 v1.0。

## 运行测试

```bash
cd /root/metacube-rgb-web-v2.0.0
PYTHONPATH=. python3 -m unittest discover -s tests -v
bash -n install.sh && bash -n uninstall.sh
```

测试会使用模拟设备，不触发任何真实 WMI 调用。`tests/visual_check.py` 是需要 Chromium/Playwright 环境的可选 UI 视觉检查，不会在 PVE 上自动运行。
