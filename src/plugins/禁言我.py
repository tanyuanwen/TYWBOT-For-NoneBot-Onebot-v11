from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from nonebot.adapters.onebot.v11.permission import GROUP
from nonebot.params import CommandArg
from nonebot.typing import T_State
import random
import datetime

# 创建命令处理器
self_ban = on_command("禁言我", permission=GROUP, priority=10, block=True)

@self_ban.handle()
async def handle_self_ban(bot: Bot, event: GroupMessageEvent, state: T_State):
    # 获取用户ID和群号
    user_id = event.user_id
    group_id = event.group_id
    
    # 生成随机禁言时间（10分钟到30天之间）
    min_minutes = 10  # 10分钟
    max_minutes = 30 * 24 * 60  # 30天的分钟数
    
    # 生成随机分钟数
    random_minutes = random.randint(min_minutes, max_minutes)
    
    # 转换为秒（禁言API使用秒为单位）
    ban_seconds = random_minutes * 60
    
    try:
        # 执行禁言操作
        await bot.set_group_ban(
            group_id=group_id,
            user_id=user_id,
            duration=ban_seconds
        )
        
        # 计算禁言结束时间
        ban_duration = datetime.timedelta(minutes=random_minutes)
        
        # 发送确认消息
        await self_ban.finish(
            f"满足你！将您禁言 {random_minutes} 分钟（约 {ban_duration.days} 天 {ban_duration.seconds//3600} 小时）"
        )
        
    except Exception as e:
        print(f"禁言操作失败：{str(e)}")