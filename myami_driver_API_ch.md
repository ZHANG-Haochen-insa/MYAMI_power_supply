# myami_driver.py — API 参考

> 适用硬件：MYAMi 多通道模块化电源（实测 3 通道）
> 通信协议：Modbus RTU over RS485（USB-to-RS485 适配器，CH340 芯片）
> 依赖：`pip install "pymodbus>=3.0"`（**必须 3.x**，2.x 导入路径和参数不兼容）

---

## 目录

1. [寄存器布局说明](#1-寄存器布局说明)
2. [实例化](#2-实例化)
3. [连接管理](#3-连接管理)
4. [写操作](#4-写操作)
5. [读操作](#5-读操作)
6. [ChannelStatus 数据类](#6-channelstatus-数据类)
7. [scan() — 通道探测](#7-scan--通道探测)
8. [错误处理](#8-错误处理)
9. [完整示例](#9-完整示例)
10. [CLI 交互模式](#10-cli-交互模式)
11. [寄存器地址速查](#11-寄存器地址速查)

---

## 1. 寄存器布局说明

该设备所有通道共用同一个 **Modbus 物理地址 1**，通道由寄存器块偏移区分：

```
CH_BASE  = 0x0064 + (channel - 1) × 0x0064
```

| channel | 寄存器块起始 |
|---------|------------|
| 1       | 0x0064     |
| 2       | 0x00C8     |
| 3       | 0x012C     |

每个块内的关键偏移：

| 偏移   | 含义       | 方向 | 换算        |
|--------|-----------|------|------------|
| +0x00  | ON/OFF     | 读写 | 1=ON, 0=OFF（同时也是状态读取）|
| +0x02  | 小数位配置 | 只读 | 固定 0x0223 (V:2, I:2) |
| +0x03  | 额定最大电压 | 只读 | raw ÷ 100 = V |
| +0x04  | 额定最大电流 | 只读 | raw ÷ 100 = A |
| +0x05  | 实际电压   | 只读 | raw ÷ 100 = V（输出 OFF 时为 0）|
| +0x06  | 实际电流   | 只读 | raw ÷ 100 = A（无负载时为 0）|
| +0x09  | 设定电压   | 读写 | raw ÷ 100 = V |
| +0x0A  | 设定电流   | 读写 | raw ÷ 100 = A（**2位小数**，非3位）|
| +0x0B  | OVP 阈值   | 读写 | raw ÷ 100 = V |
| +0x0D  | OCP 阈值   | 读写 | raw ÷ 100 = A |

> 以上偏移均为**实测确认**地址（监控前面板按键 + FC03 扫描）。出厂文档地址在此设备上不适用。

---

## 2. 实例化

```python
supply = MYAMiPowerSupply(port, baudrate=9600, timeout=1.0, debug=False)
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `port` | `str` | **必填** | 串口号，如 `"COM8"` 或 `"/dev/ttyUSB0"` |
| `baudrate` | `int` | `9600` | 波特率，通常无需修改 |
| `timeout` | `float` | `1.0` | 单次读操作超时（秒） |
| `debug` | `bool` | `False` | `True` 时打印每帧 TX/RX 原始字节，用于排查通信问题 |

实例化**不建立连接**，仅保存参数。

---

## 3. 连接管理

### `connect()` — 打开串口

```python
ok: bool = supply.connect()
```

返回 `True` 表示成功，`False` 表示串口不存在或被占用。

### `disconnect()` — 关闭串口

```python
supply.disconnect()
```

未连接时调用安全，不报错。

### `with` 语句（推荐）

```python
with MYAMiPowerSupply(port="COM8") as supply:
    supply.set_voltage(channel=1, voltage_v=5.0)
# 离开 with 块后自动断开，无论是否发生异常
```

`with` 块内若 `connect()` 失败，抛出 `RuntimeError`。

---

## 4. 写操作

所有写方法失败时静默返回 `False`，不抛异常。

---

### `set_channel()` — 同时设定电压、电流并可开启输出

```python
ok: bool = supply.set_channel(channel, voltage_v, current_a, output_on=True)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `channel` | `int` | 通道号（1、2、3…） |
| `voltage_v` | `float` | 目标电压（V），精度 0.01V |
| `current_a` | `float` | 目标电流（A），精度 0.01A |
| `output_on` | `bool` | `True` = 同时发送 ON 指令；`False` = 仅更新数值 |

```python
supply.set_channel(channel=1, voltage_v=5.0, current_a=1.5)
supply.set_channel(channel=2, voltage_v=3.3, current_a=0.5, output_on=False)
```

---

### `set_voltage()` — 仅修改电压

```python
ok: bool = supply.set_voltage(channel, voltage_v)
```

不影响电流设定和输出状态。

---

### `set_current()` — 仅修改电流

```python
ok: bool = supply.set_current(channel, current_a)
```

精度 0.01A（2位小数）。不影响电压设定和输出状态。

---

### `set_output()` — 单独控制输出开关

```python
ok: bool = supply.set_output(channel, on)
```

不修改电压/电流设定值。

```python
supply.set_output(channel=1, on=True)   # 开启 CH1
supply.set_output(channel=2, on=False)  # 关闭 CH2
```

---

### `set_ovp()` — 设置过压保护阈值

```python
ok: bool = supply.set_ovp(channel, voltage_v)
```

建议设为额定电压上限的 110%，避免阈值为 0 时保护持续触发。

---

### `set_ocp()` — 设置过流保护阈值

```python
ok: bool = supply.set_ocp(channel, current_a)
```

---

## 5. 读操作

所有读方法每次调用都向设备发起 Modbus 请求，驱动内部不缓存。通信失败返回 `None`。

---

### `read_status()` — 读取通道完整状态

```python
st: ChannelStatus | None = supply.read_status(channel)
```

一次性读取 14 个寄存器，返回 `ChannelStatus`（见第 6 节）。通信失败返回 `None`。

```python
st = supply.read_status(channel=1)
if st:
    print(st)
    # [CH1] ON   实际: 5.01V / 1.00A  设定: 5.00V / 1.00A
```

---

### `read_volt_set()` — 读取设定电压

```python
v: float | None = supply.read_volt_set(channel)
```

返回设定目标电压（V），2位小数，如 `5.00`。

---

### `read_volt_real()` — 读取实际输出电压

```python
v: float | None = supply.read_volt_real(channel)
```

返回设备实测的输出电压（V），受负载影响，与设定值略有差异。

---

### `read_curr_set()` — 读取设定电流

```python
i: float | None = supply.read_curr_set(channel)
```

返回设定电流限值（A），2位小数，如 `1.50`。

---

### `read_curr_real()` — 读取实际输出电流

```python
i: float | None = supply.read_curr_real(channel)
```

返回设备实测的输出电流（A）。

---

## 6. ChannelStatus 数据类

```python
@dataclass
class ChannelStatus:
    channel:  int
    actual_v: float   # 实际电压 (V)
    actual_i: float   # 实际电流 (A)
    set_v:    float   # 设定电压 (V)
    set_i:    float   # 设定电流 (A)
    on:       bool    # 输出状态
```

`str(st)` 输出格式：

```
[CH1] ON   实际: 5.01V / 1.00A  设定: 5.00V / 1.00A
[CH2] OFF  实际: 0.00V / 0.00A  设定: 3.30V / 0.50A
```

---

## 7. scan() — 通道探测

```python
channels: list[int] = supply.scan(max_channels=8)
```

探测通道 1～`max_channels`，通过读取各通道的 `dec_cfg` 寄存器（固定非零值 `0x0223`）判断通道是否存在。返回有响应的通道编号列表。

```python
with MYAMiPowerSupply(port="COM8") as supply:
    channels = supply.scan()   # 例如返回 [1, 2, 3]
```

扫描期间自动静默（不打印 TX/RX 日志），结束后重连以清除失败计数。

---

## 8. 错误处理

| 情况 | 行为 |
|------|------|
| `connect()` 失败 | 返回 `False`，不抛异常 |
| `with` 语句内 `connect()` 失败 | 抛出 `RuntimeError` |
| 未调用 `connect()` 就写/读 | 抛出 `RuntimeError` |
| 通信中途超时 / CRC 错误 | 写返回 `False`，读返回 `None`，不抛异常 |
| 连接被 pymodbus 内部关闭 | 下次操作前自动尝试重连 |

---

## 9. 完整示例

```python
from myami_driver import MYAMiPowerSupply, ChannelStatus  # ChannelStatus 按需导入
import time

with MYAMiPowerSupply(port="COM8") as supply:

    # 探测通道
    channels = supply.scan()
    print(f"发现通道: {channels}")   # [1, 2, 3]

    # 初始化保护阈值
    supply.set_ovp(channel=1, voltage_v=40.0)
    supply.set_ocp(channel=1, current_a=20.0)

    # 设定并开启
    supply.set_channel(channel=1, voltage_v=5.0, current_a=1.0)
    time.sleep(1.0)

    # 读取状态
    st = supply.read_status(channel=1)
    if st:
        print(st)

    # 单独调整电压
    supply.set_voltage(channel=1, voltage_v=3.3)

    # 关闭输出
    supply.set_output(channel=1, on=False)
```

---

## 10. CLI 交互模式

运行独立的交互控制台脚本（端口固定为 `COM8`，可在文件顶部修改 `PORT`）：

```
python test_cli.py
```

启动后自动扫描通道并进入提示符，支持以下命令：

| 命令 | 说明 | 示例 |
|------|------|------|
| `1` / `2` / `3` | 切换当前通道 | `2` |
| `v <值>` | 设定电压（V） | `v 5.0` |
| `v ?` | 查询当前设定电压 | |
| `vr` | 查询实际输出电压 | |
| `i <值>` | 设定电流（A） | `i 1.5` |
| `i ?` | 查询当前设定电流 | |
| `ir` | 查询实际输出电流 | |
| `ovp <值>` | 设置过压保护（V） | `ovp 30` |
| `ocp <值>` | 设置过流保护（A） | `ocp 10` |
| `on` | 开启当前通道输出（写入后立即回读确认）| |
| `off` | 关闭当前通道输出（写入后立即回读确认）| |
| `s` | 读取当前通道完整状态 | |
| `q` / `exit` | 退出 | |
| `?` | 显示帮助 | |

---

## 11. 寄存器地址速查

所有地址为实测有效地址（通道 1，Modbus PDU 0-based）。

| 功能 | 寄存器地址（CH1） | 方向 | 换算 |
|------|-----------------|------|------|
| **ON/OFF 控制 / 状态** | `0x0064` (+0x00) | **读写** | 1=ON, 0=OFF |
| 小数位配置 | `0x0066` (+0x02) | 只读 | 固定 `0x0223` (V:2, I:2) |
| 额定最大电压 | `0x0067` (+0x03) | 只读 | raw ÷ 100 = V |
| 额定最大电流 | `0x0068` (+0x04) | 只读 | raw ÷ 100 = A |
| **实际电压** | `0x0069` (+0x05) | 只读 | raw ÷ 100 = V（OFF 时为 0）|
| **实际电流** | `0x006A` (+0x06) | 只读 | raw ÷ 100 = A（无负载时为 0）|
| 设定电压 | `0x006D` (+0x09) | 读写 | raw ÷ 100 = V |
| 设定电流 | `0x006E` (+0x0A) | 读写 | raw ÷ 100 = A |
| OVP 阈值 | `0x006F` (+0x0B) | 读写 | raw ÷ 100 = V |
| OCP 阈值 | `0x0071` (+0x0D) | 读写 | raw ÷ 100 = A |

通道 2 起始地址为 `0x00C8`，通道 3 为 `0x012C`，块内偏移完全相同。

> **注意**：ON/OFF 控制和通道状态共用同一寄存器（+0x00，即块基址）。写 1 开启，写 0 关闭；读取该寄存器也反映当前输出状态。
