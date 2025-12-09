from nonebot import on_keyword
from nonebot.adapters.onebot.v11 import Message
import platform
import psutil
system_ready = on_keyword({"/系统状态"})
@system_ready.handle()
async def _():
   os_name = platform.system()
   os_version = platform.version()
   processor_name = platform.processor()
   processor_architecture = platform.architecture()
   python_version = platform.python_version()
   python_implementation = platform.python_implementation()
   cpu_count_logical = psutil.cpu_count()
   cpu_count_physical = psutil.cpu_count(logical=False)
   cpu_percent = psutil.cpu_percent(interval=1)
   memory_info = psutil.virtual_memory()
   # await weather.send("天气是...")
   network_info = psutil.net_io_counters()
   disk_partitions = psutil.disk_partitions()
   await system_ready.finish(f"系统状态:\n系统信息:\n系统名称:{os_name}\n系统版本:{os_version}\n处理器信息:\n处理器名称:{processor_name}\n处理器架构:{processor_architecture}\n处理器逻辑核心:{cpu_count_logical}\n处理器物理核心:{cpu_count_physical}\n处理器占用{cpu_percent}\n内存信息:\n总内存: {memory_info.total / (1024 ** 3):.2f} GB\n已使用内存: {memory_info.used / (1024 ** 3):.2f} GB\n内存使用率: {memory_info.percent}%\n磁盘信息:\n分区: {disk_partitions}\n网络信息:\n发送字节数: {network_info.bytes_sent}\n接收字节数: {network_info.bytes_recv}\n关于Python\nPython版本:{python_version}\nPython解释器名称: {python_implementation}")
