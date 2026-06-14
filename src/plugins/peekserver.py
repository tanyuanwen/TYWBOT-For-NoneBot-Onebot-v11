import os
import tempfile
from PIL import ImageGrab
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, MessageSegment, GroupMessageEvent, PrivateMessageEvent
from nonebot.permission import SUPERUSER
from nonebot.typing import T_State

# 定义超级管理员QQ号
SUPERUSER_QQ = ["3671199392","3961190512"]

# 注册命令，只有超级管理员可以使用
peekserver = on_command("peekserver", permission=SUPERUSER, priority=5)

@peekserver.handle()
async def handle_peekserver(bot: Bot, event: MessageEvent, state: T_State):
    """处理/peekserver命令，获取屏幕截图并发送"""
    
    # 检查用户是否为指定的超级管理员
    user_id = str(event.get_user_id())
    if user_id not in SUPERUSER_QQ:
        await peekserver.finish("权限不足，只有超级管理员可以使用此命令")
    
    try:
        # 发送处理中的提示
        await peekserver.send("正在获取屏幕截图，请稍候...")
        
        # 创建临时文件保存截图
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
            screenshot_path = tmp_file.name
        
        # 获取屏幕截图
        screenshot = ImageGrab.grab(all_screens=True)  # 捕获所有屏幕
        screenshot.save(screenshot_path, 'PNG')
        
        # 发送截图
        if isinstance(event, GroupMessageEvent):
            # 群聊中发送
            await bot.send_group_msg(
                group_id=event.group_id,
                message=MessageSegment.image(f"file:///{screenshot_path}") + "\n屏幕截图获取完成"
            )
        elif isinstance(event, PrivateMessageEvent):
            # 私聊中发送
            await bot.send_private_msg(
                user_id=event.get_user_id(),
                message=MessageSegment.image(f"file:///{screenshot_path}") + "\n屏幕截图获取完成"
            )
        else:
            # 其他情况（如频道）
            await peekserver.finish(MessageSegment.image(f"file:///{screenshot_path}") + "\n屏幕截图获取完成")
        
        # 清理临时文件
        os.unlink(screenshot_path)
        
    except ImportError:
        await peekserver.finish("截图功能需要PIL库，请安装: pip install Pillow")
    except Exception as e:
        await peekserver.finish(f"截图失败: {str(e)}")

# 可选：添加命令别名和帮助信息
peekserver.__doc__ = """
/peekserver - 获取服务器屏幕截图（仅超级管理员可用）
"""

# 设置插件元信息（NoneBot2需要）
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="屏幕截图插件",
    description="获取服务器屏幕截图的插件，仅超级管理员可用",
    usage="/peekserver - 获取屏幕截图",
    extra={
        "author": "AI Assistant",
        "version": "1.0.0",
        "superusers": SUPERUSER_QQ
    }
)
