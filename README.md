# MYAMI Power Supply 驱动

## 项目简介

这是一个用于控制 MYAMI 电源（示例驱动）的 Python 项目，包含驱动实现与 API 文档（英文与中文）。本仓库旨在提供简明的安装、使用示例以及 API 参考，方便开发者快速上手。

## 文件说明

- [myami_driver.py](myami_driver.py)：驱动实现主文件。
- [myami_driver_API.md](myami_driver_API.md)：API 英文说明。
- [myami_driver_API_ch.md](myami_driver_API_ch.md)：API 中文说明。

## 依赖与环境

- Python 3.8+
- 建议使用虚拟环境 (venv 或 conda)

安装依赖（如有 requirements.txt，请使用它）：

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# 或 macOS / Linux
# source .venv/bin/activate
pip install -r requirements.txt  # 如果存在
```

## 快速开始

以下为示例用法（示例为通用示范，具体 API 请参见文档）：

```python
# 导入驱动（根据 myami_driver.py 中的类/函数调整）
import myami_driver

# 初始化/创建驱动实例（示例）
driver = myami_driver.MyamiDriver(port='COM3', baudrate=9600)

driver.connect()
# 查询电源输出状态
status = driver.get_output_status()
print(status)

# 设置电压电流（示例）
driver.set_voltage(12.0)
driver.set_current(1.5)

# 断开连接
driver.disconnect()
```

> 注意：示例中的类名、方法名仅为示范，请参阅 [myami_driver.py](myami_driver.py) 与 API 文档获取准确接口。

## API 参考

详细接口说明请参阅：

- [myami_driver_API.md](myami_driver_API.md)
- [myami_driver_API_ch.md](myami_driver_API_ch.md)

## 测试

编写一个简单脚本 `examples/test_connection.py` 来验证与设备的通信（示例同上）。

## 贡献指南

欢迎提交 issue 与 PR。请在提交前确保代码风格一致，并附带必要的说明与最小复现用例。

## 许可

仓库当前未包含许可证文件。若需开源许可，请添加 LICENSE 文件并在此处说明。

---

如果你希望我根据 `myami_driver.py` 的实际内容把 README 中的示例代码改成真实可运行的示例，我可以读取并分析该文件然后更新 README。