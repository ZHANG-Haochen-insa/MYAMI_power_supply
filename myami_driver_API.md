# myami_driver.py — API Reference

> Hardware: MYAMi multi-channel modular power supply (3 channels confirmed)
> Protocol: Modbus RTU over RS485 (USB-to-RS485 adapter, CH340 chip)
> Dependency: `pip install "pymodbus>=3.0"` (**version 3.x required** — import paths and `device_id=` parameter are incompatible with 2.x)

---

## Table of Contents

1. [Register Layout](#1-register-layout)
2. [Instantiation](#2-instantiation)
3. [Connection Management](#3-connection-management)
4. [Write Operations](#4-write-operations)
5. [Read Operations](#5-read-operations)
6. [ChannelStatus Dataclass](#6-channelstatus-dataclass)
7. [scan() — Channel Detection](#7-scan--channel-detection)
8. [Error Handling](#8-error-handling)
9. [Complete Example](#9-complete-example)
10. [Interactive CLI](#10-interactive-cli)
11. [Register Address Quick Reference](#11-register-address-quick-reference)

---

## 1. Register Layout

All channels share the same **Modbus device address 1**. Channels are distinguished by a register block offset:

```
CH_BASE  = 0x0064 + (channel - 1) × 0x0064
```

| Channel | Block Base Address |
|---------|--------------------|
| 1       | 0x0064             |
| 2       | 0x00C8             |
| 3       | 0x012C             |

Key offsets within each block:

| Offset | Meaning             | Access     | Conversion                          |
|--------|---------------------|------------|-------------------------------------|
| +0x00  | ON/OFF              | Read/Write | 1 = ON, 0 = OFF (also status read)  |
| +0x02  | Decimal config      | Read only  | Fixed 0x0223 (V:2 decimals, I:2 decimals) |
| +0x03  | Rated max voltage   | Read only  | raw ÷ 100 = V                       |
| +0x04  | Rated max current   | Read only  | raw ÷ 100 = A                       |
| +0x05  | Actual voltage      | Read only  | raw ÷ 100 = V (0 when output OFF)   |
| +0x06  | Actual current      | Read only  | raw ÷ 100 = A (0 with no load)      |
| +0x09  | Set voltage         | Read/Write | raw ÷ 100 = V                       |
| +0x0A  | Set current         | Read/Write | raw ÷ 100 = A (**2 decimal places**, not 3) |
| +0x0B  | OVP threshold       | Read/Write | raw ÷ 100 = V                       |
| +0x0D  | OCP threshold       | Read/Write | raw ÷ 100 = A                       |

> All offsets above are **experimentally confirmed** (front-panel button monitoring + FC03 scan). Factory documentation addresses do not apply to this device.

---

## 2. Instantiation

```python
supply = MYAMiPowerSupply(port, baudrate=9600, timeout=1.0, debug=False)
```

| Parameter  | Type    | Default      | Description |
|------------|---------|--------------|-------------|
| `port`     | `str`   | **required** | Serial port, e.g. `"COM8"` (Windows) or `"/dev/ttyUSB0"` (Linux) |
| `baudrate` | `int`   | `9600`       | Baud rate — do not change unless instructed |
| `timeout`  | `float` | `1.0`        | Per-read timeout in seconds |
| `debug`    | `bool`  | `False`      | If `True`, prints raw TX/RX bytes for every frame — useful for troubleshooting |

Instantiation **does not open a connection**; it only stores the parameters.

---

## 3. Connection Management

### `connect()` — open the serial port

```python
ok: bool = supply.connect()
```

Returns `True` on success, `False` if the port does not exist or is already in use.

### `disconnect()` — close the serial port

```python
supply.disconnect()
```

Safe to call when already disconnected — no error is raised.

### `with` statement (recommended)

```python
with MYAMiPowerSupply(port="COM8") as supply:
    supply.set_voltage(channel=1, voltage_v=5.0)
# port is closed automatically on exit, even if an exception occurs
```

If `connect()` fails inside a `with` block, a `RuntimeError` is raised.

---

## 4. Write Operations

All write methods return `False` silently on failure — no exceptions are raised.

---

### `set_channel()` — set voltage and current, optionally enable output

```python
ok: bool = supply.set_channel(channel, voltage_v, current_a, output_on=True)
```

| Parameter   | Type    | Description |
|-------------|---------|-------------|
| `channel`   | `int`   | Channel number (1, 2, 3…) |
| `voltage_v` | `float` | Target voltage (V), resolution 0.01 V |
| `current_a` | `float` | Target current (A), resolution 0.01 A |
| `output_on` | `bool`  | `True` = also send ON command; `False` = update values only |

```python
supply.set_channel(channel=1, voltage_v=5.0, current_a=1.5)
supply.set_channel(channel=2, voltage_v=3.3, current_a=0.5, output_on=False)
```

---

### `set_voltage()` — update voltage only

```python
ok: bool = supply.set_voltage(channel, voltage_v)
```

Does not affect the current setpoint or output state.

---

### `set_current()` — update current only

```python
ok: bool = supply.set_current(channel, current_a)
```

Resolution 0.01 A (2 decimal places). Does not affect the voltage setpoint or output state.

---

### `set_output()` — control output on/off independently

```python
ok: bool = supply.set_output(channel, on)
```

Does not modify voltage or current setpoints.

```python
supply.set_output(channel=1, on=True)   # enable CH1
supply.set_output(channel=2, on=False)  # disable CH2
```

---

### `set_ovp()` — set over-voltage protection threshold

```python
ok: bool = supply.set_ovp(channel, voltage_v)
```

Recommended: set to 110% of the rated voltage ceiling to prevent the protection from triggering continuously when the threshold is 0.

---

### `set_ocp()` — set over-current protection threshold

```python
ok: bool = supply.set_ocp(channel, current_a)
```

---

## 5. Read Operations

Every read method sends a fresh Modbus request to the device — no caching. Returns `None` on communication failure.

---

### `read_status()` — read full channel state

```python
st: ChannelStatus | None = supply.read_status(channel)
```

Reads 14 registers in a single request and returns a `ChannelStatus` object (see section 6). Returns `None` on failure.

```python
st = supply.read_status(channel=1)
if st:
    print(st)
    # [CH1] ON   实际: 5.01V / 1.00A  设定: 5.00V / 1.00A
```

---

### `read_volt_set()` — read voltage setpoint

```python
v: float | None = supply.read_volt_set(channel)
```

Returns the programmed target voltage (V), 2 decimal places, e.g. `5.00`.

---

### `read_volt_real()` — read actual output voltage

```python
v: float | None = supply.read_volt_real(channel)
```

Returns the measured output voltage (V). May differ slightly from the setpoint under load.

---

### `read_curr_set()` — read current setpoint

```python
i: float | None = supply.read_curr_set(channel)
```

Returns the programmed current limit (A), 2 decimal places, e.g. `1.50`.

---

### `read_curr_real()` — read actual output current

```python
i: float | None = supply.read_curr_real(channel)
```

Returns the measured output current (A). Returns `0.00` when no load is connected.

---

## 6. ChannelStatus Dataclass

```python
@dataclass
class ChannelStatus:
    channel:  int
    actual_v: float   # measured output voltage (V)
    actual_i: float   # measured output current (A)
    set_v:    float   # voltage setpoint (V)
    set_i:    float   # current setpoint (A)
    on:       bool    # output state
```

`str(st)` output format:

```
[CH1] ON   实际: 5.01V / 1.00A  设定: 5.00V / 1.00A
[CH2] OFF  实际: 0.00V / 0.00A  设定: 3.30V / 0.50A
```

> Note: the labels in the string output (`实际` = actual, `设定` = setpoint) are in Chinese as defined in the driver source. Field values are plain floats accessible programmatically via `st.actual_v`, `st.set_v`, etc.

---

## 7. scan() — Channel Detection

```python
channels: list[int] = supply.scan(max_channels=8)
```

Probes channels 1 through `max_channels` by reading the `dec_cfg` register of each block (fixed non-zero value `0x0223` when the channel exists). Returns a list of responding channel numbers.

```python
with MYAMiPowerSupply(port="COM8") as supply:
    channels = supply.scan()   # e.g. [1, 2, 3]
```

TX/RX debug output is automatically suppressed during the scan. A reconnect is performed at the end to reset pymodbus's internal error counter.

---

## 8. Error Handling

| Situation | Behaviour |
|-----------|-----------|
| `connect()` fails | Returns `False`, no exception |
| `connect()` fails inside `with` block | Raises `RuntimeError` |
| Read/write called before `connect()` | Raises `RuntimeError` |
| Communication timeout or CRC error | Write → `False`; Read → `None`; no exception |
| Connection dropped internally by pymodbus | Auto-reconnect attempted before the next operation |

---

## 9. Complete Example

```python
from myami_driver import MYAMiPowerSupply, ChannelStatus  # ChannelStatus import optional
import time

with MYAMiPowerSupply(port="COM8") as supply:

    # Detect available channels
    channels = supply.scan()
    print(f"Channels found: {channels}")   # [1, 2, 3]

    # Set protection thresholds
    supply.set_ovp(channel=1, voltage_v=40.0)
    supply.set_ocp(channel=1, current_a=20.0)

    # Configure and enable output
    supply.set_channel(channel=1, voltage_v=5.0, current_a=1.0)
    time.sleep(1.0)

    # Read full status
    st = supply.read_status(channel=1)
    if st:
        print(st)
        print(f"Actual: {st.actual_v} V / {st.actual_i} A")

    # Adjust voltage only
    supply.set_voltage(channel=1, voltage_v=3.3)

    # Turn off output
    supply.set_output(channel=1, on=False)
```

---

## 10. Interactive CLI

Run the standalone interactive console script (port is configured via `PORT` at the top of the file):

```
python test_cli.py
```

Channels are scanned automatically on startup, then the command prompt appears:

| Command      | Description                                          | Example  |
|--------------|------------------------------------------------------|----------|
| `1` / `2` / `3` | Switch active channel                             | `2`      |
| `v <value>`  | Set voltage (V)                                      | `v 5.0`  |
| `v ?`        | Query current voltage setpoint                       |          |
| `vr`         | Query actual output voltage                          |          |
| `i <value>`  | Set current (A)                                      | `i 1.5`  |
| `i ?`        | Query current setpoint                               |          |
| `ir`         | Query actual output current                          |          |
| `ovp <value>`| Set over-voltage protection threshold (V)            | `ovp 30` |
| `ocp <value>`| Set over-current protection threshold (A)            | `ocp 10` |
| `on`         | Enable output (writes then immediately reads back to confirm) | |
| `off`        | Disable output (writes then immediately reads back to confirm) | |
| `s`          | Read full status of the active channel               |          |
| `q` / `exit` | Quit                                                 |          |
| `?`          | Show help                                            |          |

---

## 11. Register Address Quick Reference

All addresses experimentally verified for channel 1 (Modbus PDU, 0-based).

| Function                   | Address CH1      | Access     | Conversion                        |
|----------------------------|------------------|------------|-----------------------------------|
| **ON/OFF control / status**| `0x0064` (+0x00) | **R/W**    | 1 = ON, 0 = OFF                   |
| Decimal config             | `0x0066` (+0x02) | Read only  | Fixed `0x0223` (V:2, I:2)         |
| Rated max voltage          | `0x0067` (+0x03) | Read only  | raw ÷ 100 = V                     |
| Rated max current          | `0x0068` (+0x04) | Read only  | raw ÷ 100 = A                     |
| **Actual voltage**         | `0x0069` (+0x05) | Read only  | raw ÷ 100 = V (0 when OFF)        |
| **Actual current**         | `0x006A` (+0x06) | Read only  | raw ÷ 100 = A (0 with no load)    |
| Set voltage                | `0x006D` (+0x09) | R/W        | raw ÷ 100 = V                     |
| Set current                | `0x006E` (+0x0A) | R/W        | raw ÷ 100 = A                     |
| OVP threshold              | `0x006F` (+0x0B) | R/W        | raw ÷ 100 = V                     |
| OCP threshold              | `0x0071` (+0x0D) | R/W        | raw ÷ 100 = A                     |

Channel 2 base: `0x00C8` — Channel 3 base: `0x012C` — offsets are identical.

> **Important**: The ON/OFF control register and the channel status register are the **same address** (+0x00, the block base). Write 1 to enable output, write 0 to disable; reading the same register returns the current output state.
