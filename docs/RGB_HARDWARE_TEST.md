# MetaCube M11 RGB 实机验收清单（v2.1）

> 本文件是人工测试计划，**不是已经完成的硬件测试结果**。当前 MetaCube 实机确认的是 WMI 读写、单色、部分模式、亮度；旋转、多色、速度、方向、循环、渐变仍需要在实机上逐项观察。

## 操作前

1. 在 PVE 业务低峰进行，确保能使用本地控制台恢复；不要同时让 Windows 原厂程序和 Linux 驱动操作同一个 EC。
2. 先记录并保存原来的 RGB 状态：

   ```bash
   metacube-rgb status --json > /root/metacube-rgb-before-rgb-test.json
   metacube-rgb save
   metacube-rgb apply --dry-run
   ```

3. 打开 Web「光效工作室」，确认 Web 显示的颜色、模式、亮度与实际 LED 一致。
4. 每次只改变一个参数。提交前可点击「查看 WMI 数据包」，它**不发送** WMI SET。
5. **固件回读一致不等于灯珠物理效果一定一致**，必须人工观察。

## 逐项验收

| 序号 | 项目 | 推荐操作 | 硬件观察 | 状态 |
|---|---|---|---|---|
| 1 | 基准单色 | 常亮 / `FF0000` / 亮度 `160` | 应为红色常亮 | 已有单色写入实机证据，当前 v2.1 尚未实测 |
| 2 | 关闭 / 恢复 | `off` 再 `steady` | 关闭后灯灭，再恢复颜色 | 待测当前 v2.1 |
| 3 | 呼吸 | `breath` | 灯光明暗周期性变化 | 待测当前 v2.1 |
| 4 | 多色两组 | `FF0000`, `0000FF` | 确认两个颜色实际参与效果 | 待测 |
| 5 | 多色六组 | 6 个不同颜色 | 检查顺序、数量、覆盖与丢色 | 待测 |
| 6 | 旋转 | `spin` | 观察是否真的沿机身灯带旋转 | 待测 |
| 7 | 速度 | `speed 30` 与 `speed 200` | 两个速度有可见差异，记录快慢方向 | 待测 |
| 8 | 旋转方向 | `direction 0` 与 `direction 1` | 顺逆时针方向改变 | 待测 |
| 9 | 循环参数 | `cycle 0`, `6`, `11` | 记录不同档位实际含义 | 待测 |
| 10 | 渐变 | `transition 0` 与 `1` | 记录颜色切换是否平滑 | 待测 |
| 11 | 5 组预设 | 草稿保存→载入编辑器→立即应用 | 预设可保存和恢复；保存草稿不改变设备 | Web 模拟测试通过，实机待测 |
| 12 | 开机恢复 | 冷启动 / 重启后 `metacube-rgb status` | BIOS 和 systemd 行为记录 | 待测 |

可优先使用 **一次性原子设置命令**，避免发送多条固件写入：

```bash
# 仅预览计划发送的 32 字节请求，不写固件
metacube-rgb set --mode spin --colors FF0000 00FF00 0000FF \
  --brightness 160 --speed 45 --direction 0 --cycle 0 --transition 1 --dry-run

# 只有经过维护窗口确认后，去掉 --dry-run 才真正修改固件
metacube-rgb set --mode spin --colors FF0000 00FF00 0000FF \
  --brightness 160 --speed 45 --direction 0 --cycle 0 --transition 1

# 实时回读（仍需观察实际灯效）
metacube-rgb status --json
```

## 恢复及故障排查

```bash
# 重新应用测试前的保存配置（会写入固件）
metacube-rgb apply

# 查看驱动最近错误
journalctl -k -b --no-pager | grep -Ei 'metacube_ambient|WMI SET|WMI method' | tail -n 50

# 检查驱动、签名和 DKMS
modinfo -F version metacube_ambient
modinfo -F signer metacube_ambient
dkms status -m metacube-ambient
```

如果出现 WMI 错误、灯光不按预期变化、PVE 主机异常，停止后续写入，保存原始回读、日志和操作步骤。不要连续重试固件命令，也不要在同一时刻使用两个 RGB 控制程序。

**特别说明**：Windows 中的键盘 RGB 函数（0x10–0x12）仅为原厂库接口，未确认 MetaCube M11 板载有可用 RGB 键盘，因此不属于上述机身氛围灯验收范围。
