"""
myami_driver.py — MYAMi 电源 Modbus RTU 驱动（纯库，无 CLI）

实测寄存器布局（raw 扫描 + 按键监控确认）：
  Modbus 设备地址: 始终为 1
  通道块基址: CH_BASE = 0x0064 + (channel - 1) * 0x0064
    channel=1 → 0x0064,  channel=2 → 0x00C8,  channel=3 → 0x012C

  块内偏移:
    +0x00  status   读写: 通道 ON/OFF（写1开启/写0关闭，同时是状态位）
    +0x02  dec_cfg  只读: 小数位配置 0x0223（V:2位, I:2位）
    +0x03  max_v    只读: 最大额定电压 (÷100 = V)
    +0x04  max_i    只读: 最大额定电流 (÷100 = A)
    +0x05  disp_v   只读: 实际输出电压 (÷100 = V)，输出OFF时为0
    +0x06  disp_i   只读: 实际输出电流 (÷100 = A)，无负载时为0
    +0x09  setv_w   读写: 设定电压 (×100)
    +0x0A  seti_w   读写: 设定电流 (×100, 精度0.01A)
    +0x0B  ovp      读写: 过压保护阈值 (×100)
    +0x0D  ocp      读写: 过流保护阈值 (×100)

公开 API:
  set_channel(channel, voltage_v, current_a, output_on=True) → bool
  set_voltage(channel, voltage_v)   → bool
  set_current(channel, current_a)   → bool
  set_output(channel, on)           → bool
  set_ovp(channel, voltage_v)       → bool
  set_ocp(channel, current_a)       → bool
  read_status(channel)              → ChannelStatus | None
  read_volt_set(channel)            → float | None
  read_volt_real(channel)           → float | None
  read_curr_set(channel)            → float | None
  read_curr_real(channel)           → float | None
  scan(max_channels=8)              → list[int]
"""

import time
from dataclasses import dataclass
from typing import Optional

from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException

_MODBUS_DEVICE = 1
_CH_BASE       = 0x0064
_CH_STRIDE     = 0x0064

# 0x0000 = 全局状态（任一通道开启时为1），只读，不用于控制

# 通道块内偏移
_OFF_STATUS = 0x00    # 读写: 通道 ON/OFF（写1开启，写0关闭；同时也是状态读取）
_OFF_DEC_CFG= 0x02    # 只读: 小数位配置 (0x0223)
_OFF_MAX_V  = 0x03    # 只读: 最大额定电压 (×100)
_OFF_MAX_I  = 0x04    # 只读: 最大额定电流 (×100)
_OFF_DISP_V = 0x05    # 只读: 实际电压 (×100)，输出OFF时为0
_OFF_DISP_I = 0x06    # 只读: 实际电流 (×100)，无负载时为0
_OFF_SETV_W = 0x09    # 读写: 设定电压 (×100)
_OFF_SETI_W = 0x0A    # 读写: 设定电流 (×100, 2位小数)
_OFF_OVP    = 0x0B    # 读写: 过压保护阈值 (×100)
_OFF_OCP    = 0x0D    # 读写: 过流保护阈值 (×100)

_CMD_DELAY  = 0.05


def _ch_addr(channel: int, offset: int) -> int:
    return _CH_BASE + (channel - 1) * _CH_STRIDE + offset


@dataclass
class ChannelStatus:
    channel:  int
    actual_v: float
    actual_i: float
    set_v:    float
    set_i:    float
    on:       bool

    def __str__(self) -> str:
        state = "ON " if self.on else "OFF"
        return (
            f"[CH{self.channel}] {state}  "
            f"实际: {self.actual_v:.2f}V / {self.actual_i:.2f}A  "
            f"设定: {self.set_v:.2f}V / {self.set_i:.2f}A"
        )


class MYAMiPowerSupply:
    """MYAMi 多通道电源 Modbus RTU 驱动"""

    def __init__(self, port: str, baudrate: int = 9600,
                 timeout: float = 1.0, debug: bool = False):
        self.port     = port
        self.baudrate = baudrate
        self.timeout  = timeout
        self.debug    = debug
        self._client: Optional[ModbusSerialClient] = None

    def _log(self, msg: str):
        if self.debug:
            print(f"[MYAMi] {msg}")

    def _trace_packet(self, sending: bool, data: bytes) -> bytes:
        self._log(f"  {'TX' if sending else 'RX'}: {data.hex(' ').upper()}")
        return data

    # ── 连接管理 ────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        self._client = ModbusSerialClient(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=self.timeout,
            retries=1,
            trace_packet=self._trace_packet if self.debug else None,
        )
        try:
            ok = self._client.connect()
        except Exception as e:
            self._log(f"Connect EXCEPTION: {e}")
            self._client = None
            return False
        if ok:
            print(f"[MYAMi] Connected: {self.port} @ {self.baudrate} 8N1")
        else:
            self._client = None
        return ok

    def disconnect(self):
        if self._client:
            self._client.close()
            self._client = None
            print("[MYAMi] Disconnected")

    def __enter__(self):
        if not self.connect():
            raise RuntimeError(
                f"MYAMiPowerSupply: 无法连接串口 {self.port}"
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    # ── 内部底层 ────────────────────────────────────────────────────────────

    def _assert_connected(self):
        if self._client is None:
            raise RuntimeError("MYAMiPowerSupply: 未连接，请先调用 connect()")

    def _ensure_connected(self):
        if self._client and not self._client.connected:
            self._log("Connection lost, reconnecting...")
            self._client.connect()

    def _write(self, address: int, value: int) -> bool:
        self._assert_connected()
        self._ensure_connected()
        try:
            r = self._client.write_register(
                address=address, value=value, device_id=_MODBUS_DEVICE
            )
            time.sleep(_CMD_DELAY)
            ok = not r.isError()
            self._log(f"FC06 0x{address:04X} ← {value}  {'OK' if ok else f'ERR {r}'}")
            return ok
        except (ModbusException, Exception) as e:
            self._log(f"FC06 0x{address:04X} ← {value}  EXCEPTION {e}")
            self._ensure_connected()
            return False

    def _read(self, address: int, count: int = 1) -> Optional[list]:
        self._assert_connected()
        self._ensure_connected()
        try:
            r = self._client.read_holding_registers(
                address=address, count=count, device_id=_MODBUS_DEVICE
            )
            time.sleep(_CMD_DELAY)
            if r.isError():
                self._log(f"FC03 0x{address:04X} ×{count}  ERR {r}")
                return None
            self._log(f"FC03 0x{address:04X} ×{count}  → {r.registers}")
            return r.registers
        except (ModbusException, Exception) as e:
            self._log(f"FC03 0x{address:04X} ×{count}  EXCEPTION {e}")
            self._ensure_connected()
            return None

    # ── 写操作 API ──────────────────────────────────────────────────────────

    def set_voltage(self, channel: int, voltage_v: float) -> bool:
        return self._write(_ch_addr(channel, _OFF_SETV_W), round(voltage_v * 100))

    def set_current(self, channel: int, current_a: float) -> bool:
        return self._write(_ch_addr(channel, _OFF_SETI_W), round(current_a * 100))

    def set_ovp(self, channel: int, voltage_v: float) -> bool:
        return self._write(_ch_addr(channel, _OFF_OVP), round(voltage_v * 100))

    def set_ocp(self, channel: int, current_a: float) -> bool:
        return self._write(_ch_addr(channel, _OFF_OCP), round(current_a * 100))

    def set_output(self, channel: int, on: bool) -> bool:
        return self._write(_ch_addr(channel, _OFF_STATUS), 1 if on else 0)

    def set_channel(self, channel: int, voltage_v: float, current_a: float,
                    output_on: bool = True) -> bool:
        ok  = self.set_voltage(channel, voltage_v)
        ok &= self.set_current(channel, current_a)
        if output_on:
            ok &= self.set_output(channel, True)
        return bool(ok)

    # ── 读操作 API ──────────────────────────────────────────────────────────

    def read_status(self, channel: int) -> Optional[ChannelStatus]:
        regs = self._read(_ch_addr(channel, 0), count=14)
        if regs is None or len(regs) < 14:
            return None
        return ChannelStatus(
            channel=channel,
            actual_v=round(regs[_OFF_DISP_V] / 100.0, 2),
            actual_i=round(regs[_OFF_DISP_I] / 100.0, 2),
            set_v=   round(regs[_OFF_SETV_W] / 100.0, 2),
            set_i=   round(regs[_OFF_SETI_W] / 100.0, 2),
            on=      bool(regs[_OFF_STATUS]),
        )

    def read_volt_set(self, channel: int) -> Optional[float]:
        raw = self._read(_ch_addr(channel, _OFF_SETV_W))
        return round(raw[0] / 100.0, 2) if raw else None

    def read_volt_real(self, channel: int) -> Optional[float]:
        raw = self._read(_ch_addr(channel, _OFF_DISP_V))
        return round(raw[0] / 100.0, 2) if raw else None

    def read_curr_set(self, channel: int) -> Optional[float]:
        raw = self._read(_ch_addr(channel, _OFF_SETI_W))
        return round(raw[0] / 100.0, 2) if raw else None

    def read_curr_real(self, channel: int) -> Optional[float]:
        raw = self._read(_ch_addr(channel, _OFF_DISP_I))
        return round(raw[0] / 100.0, 2) if raw else None

    # ── 工具方法 ────────────────────────────────────────────────────────────

    def scan(self, max_channels: int = 8) -> list[int]:
        """探测通道 1~max_channels，返回有响应的通道列表"""
        self._assert_connected()
        found = []
        saved_debug = self.debug
        self.debug = False
        for ch in range(1, max_channels + 1):
            r = self._read(_ch_addr(ch, _OFF_DEC_CFG))
            if r is not None and r[0] != 0:
                found.append(ch)
        self.debug = saved_debug
        if self._client:
            self._client.close()
            self._client.connect()
        return found
