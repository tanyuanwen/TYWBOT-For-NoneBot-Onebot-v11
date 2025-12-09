import re
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.rule import to_me
from nonebot.log import logger

# 超级管理员QQ号
SUPER_ADMIN = 3671199392

# 注册禁言命令处理器
mute = on_command("mute", priority=10, block=True)

@mute.handle()
async def handle_mute(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    # 检查发送者权限
    sender_qq = event.user_id
    sender_role = event.sender.role
    
    # 只有管理员、群主或超级管理员可以使用该命令
    if sender_role not in ["admin", "owner"] and sender_qq != SUPER_ADMIN:
        await mute.finish("⚠️ 抱歉，只有群管理员或超级管理员可以使用禁言功能")
    
    # 解析参数
    arg_str = args.extract_plain_text().strip()
    if not arg_str:
        await mute.finish("❌ 参数格式错误！正确格式：/mute QQ号/@的人 禁言秒数\n示例：/mute 123456 60 或 /mute @某人 300")
    
    # 解析QQ号和禁言时间
    try:
        # 判断是否通过@提及方式
        at_target = None
        time_seconds = None
        
        # 提取消息中的CQ码（@信息）
        message_segments = args
        for segment in message_segments:
            if segment.type == "at":
                at_target = segment.data.get("qq", "")
                if at_target:
                    at_target = int(at_target)
        
        # 如果通过@方式，从文本中提取时间
        if at_target:
            # 提取所有数字，最后一个数字是时间
            numbers = re.findall(r'\d+', arg_str)
            if len(numbers) >= 1:
                time_seconds = int(numbers[-1])
        else:
            # 如果是直接输入QQ号，前两个数字分别是QQ号和时间
            numbers = re.findall(r'\d+', arg_str)
            if len(numbers) >= 2:
                at_target = int(numbers[0])
                time_seconds = int(numbers[1])
        
        if not at_target or time_seconds is None:
            await mute.finish("❌ 参数格式错误！请指定要禁言的用户和禁言时间\n格式：/mute QQ号 秒数 或 /mute @某人 秒数")
        
        # 检查目标是否为自己
        if at_target == sender_qq:
            await mute.finish("❌ 您不能禁言自己！")
        
        # 检查目标是否为超级管理员
        if at_target == SUPER_ADMIN:
            await mute.finish("❌ 无法对超级管理员执行禁言操作")
        
        # 检查目标是否在群中（可选，增加健壮性）
        group_id = event.group_id
        try:
            group_member_info = await bot.get_group_member_info(
                group_id=group_id, 
                user_id=at_target, 
                no_cache=False
            )
            target_role = group_member_info.get("role", "member")
            
            # 检查目标权限（避免下级管理员禁言上级）
            if target_role in ["admin", "owner"] and sender_role != "owner":
                await mute.finish("❌ 管理员只能禁言普通成员，无法禁言其他管理员")
                
        except Exception as e:
            logger.warning(f"获取群成员信息失败: {e}")
            # 继续执行，依赖API本身的错误处理
        
        # 执行禁言操作
        try:
            await bot.set_group_ban(
                group_id=group_id,
                user_id=at_target,
                duration=time_seconds
            )
            
            # 生成成功消息
            time_display = format_time(time_seconds)
            await mute.finish(f"✅ 禁言成功！\n用户：{at_target}\n禁言时间：{time_display}")
            
        except Exception as e:
            logger.error(f"禁言操作失败: {e}")
            await mute.finish("❌ 禁言操作失败，可能是权限不足或用户不存在")
    
    except ValueError as e:
        logger.error(f"参数解析错误: {e}")
        await mute.finish("❌ 参数格式错误！请确保QQ号和禁言时间都是数字\n格式：/mute QQ号 秒数")

def format_time(seconds: int) -> str:
    """将秒数格式化为易读的时间字符串"""
    if seconds < 60:
        return f"{seconds}秒"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes}分钟"
    elif seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}小时{minutes}分钟" if minutes > 0 else f"{hours}小时"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{days}天{hours}小时"

# 可选：添加解禁命令
unmute = on_command("unmute", priority=10, block=True)

@unmute.handle()
async def handle_unmute(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    """解禁命令"""
    sender_qq = event.user_id
    sender_role = event.sender.role
    
    if sender_role not in ["admin", "owner"] and sender_qq != SUPER_ADMIN:
        await unmute.finish("⚠️ 抱歉，只有群管理员或超级管理员可以使用解禁功能")
    
    arg_str = args.extract_plain_text().strip()
    if not arg_str:
        await unmute.finish("❌ 参数格式错误！正确格式：/unmute QQ号/@的人")
    
    try:
        # 解析QQ号（支持@和直接输入）
        target_qq = None
        message_segments = args
        for segment in message_segments:
            if segment.type == "at":
                target_qq = segment.data.get("qq", "")
                if target_qq:
                    target_qq = int(target_qq)
                    break
        
        if not target_qq:
            numbers = re.findall(r'\d+', arg_str)
            if numbers:
                target_qq = int(numbers[0])
        
        if not target_qq:
            await unmute.finish("❌ 请指定要解禁的用户QQ号或使用@提及")
        
        # 执行解禁（禁言0秒即为解禁）
        await bot.set_group_ban(
            group_id=event.group_id,
            user_id=target_qq,
            duration=0
        )
        
        await unmute.finish(f"✅ 解禁成功！用户 {target_qq} 已被解除禁言")
    
    except Exception as e:
        logger.error(f"解禁操作失败: {e}")
        await unmute.finish("❌ 解禁操作失败，可能是权限不足或用户不存在")
