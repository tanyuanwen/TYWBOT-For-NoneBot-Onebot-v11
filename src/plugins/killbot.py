from nonebot import on_message, get_driver
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, PrivateMessageEvent, MessageEvent
from nonebot.plugin import PluginMetadata
from nonebot import logger
from typing import Set, Dict, Any
import time

# 插件元信息
__plugin_meta__ = PluginMetadata(
    name="智能消息撤回管理器",
    description="支持多用户、条件判断的智能消息撤回系统",
    usage="自动触发，无需命令",
    type="application",
)

# 配置：目标QQ号列表（可以配置多个用户）
TARGET_QQ_SET = {"31415926","114514"}  # 主目标用户
# 可以添加更多用户：TARGET_QQ_SET = {"3383731514", "123456789", "987654321"}

# 高级配置选项
class RecallConfig:
    def __init__(self):
        self.enable_group = True  # 启用群消息撤回
        self.enable_private = False  # 启用私聊消息撤回（可能受限）
        self.delay_seconds = 0  # 延迟撤回时间（秒）
        self.notify_admin = True  # 通知管理员
        self.admin_qq = "3671199392"  # 管理员QQ号（用于通知）

config = RecallConfig()

# 创建消息事件处理器
recall_monitor = on_message(priority=1, block=False)

# 消息记录（用于防止频繁操作）
message_history: Dict[str, float] = {}
RATE_LIMIT = 5  # 5秒内不对同一用户重复操作

@recall_monitor.handle()
async def smart_recall_handler(bot: Bot, event: MessageEvent):
    """
    智能消息撤回处理器
    """
    sender_qq = str(event.get_user_id())
    
    # 检查是否为目标用户
    if sender_qq not in TARGET_QQ_SET:
        return
    
    # 频率限制检查
    current_time = time.time()
    
    
    # 更新操作时间
    message_history[sender_qq] = current_time
    
    try:
        # 延迟处理
        if config.delay_seconds > 0:
            import asyncio
            await asyncio.sleep(config.delay_seconds)
        
        # 执行撤回操作
        await recall_message(bot, event, sender_qq)
        
    except Exception as e:
        logger.error(f"撤回用户 {sender_qq} 的消息失败: {e}")
        await notify_admin(bot, f"撤回用户 {sender_qq} 的消息失败: {e}")

async def recall_message(bot: Bot, event: MessageEvent, sender_qq: str):
    """执行消息撤回操作"""
    message_id = event.message_id
    
    if isinstance(event, GroupMessageEvent) and config.enable_group:
        await bot.delete_msg(message_id=message_id)
        logger.info(f"已撤回用户 {sender_qq} 在群 {event.group_id} 发送的消息")
        
        # 通知管理员
        if config.notify_admin:
            await notify_admin(
                bot, 
                f"已撤回用户 {sender_qq} 在群 {event.group_id} 发送的消息"
            )
            
    elif isinstance(event, PrivateMessageEvent) and config.enable_private:
        await bot.delete_msg(message_id=message_id)
        logger.info(f"已撤回用户 {sender_qq} 的私聊消息")

async def notify_admin(bot: Bot, message: str):
    """通知管理员"""
    if config.notify_admin and config.admin_qq:
        try:
            await bot.send_private_msg(user_id=int(config.admin_qq), message=message)
        except Exception as e:
            logger.error(f"通知管理员失败: {e}")

# 可选：添加手动控制命令
from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11 import Message

control = on_command("recall_control", priority=2)

@control.handle()
async def handle_control(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    """手动控制撤回功能"""
    command = args.extract_plain_text().strip()
    
    if command == "status":
        await control.finish(f"当前监控用户: {', '.join(TARGET_QQ_SET)}")
    elif command == "reload":
        # 重新加载配置的逻辑
        await control.finish("配置重载完成")
