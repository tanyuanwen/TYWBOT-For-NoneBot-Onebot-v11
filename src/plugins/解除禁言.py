from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, PrivateMessageEvent
from nonebot.params import CommandArg
from nonebot.typing import T_State
import re

# 超级管理员QQ号
SUPERUSER_QQ = "3671199392"

# 注册命令处理器
unban = on_command("admin unmute", priority=5, block=True)

@unban.handle()
async def handle_unban(bot: Bot, event: PrivateMessageEvent, state: T_State, args = CommandArg()):
    # 检查是否为超级管理员
    if event.get_user_id() != SUPERUSER_QQ:
        await unban.finish("抱歉，您没有权限执行此命令")
    
    # 解析参数
    arg_str = args.extract_plain_text().strip()
    
    # 使用正则表达式提取群号和QQ号
    match = re.match(r'(\d+)(?:\s+(\S+))?', arg_str)  # 修改为\S+以匹配"all"
    
    if not match:
        await unban.finish("命令格式错误，请使用：/admin unmute 群号 [QQ号|all]")
    
    group_id = match.group(1)
    qq_id = match.group(2)
    
    # 如果没有提供QQ号，默认使用超级管理员自己的QQ号
    if not qq_id:
        qq_id = SUPERUSER_QQ
    
    try:
        # 判断是否是解除全体禁言
        if qq_id.lower() == 'all':
            # 调用解除全体禁言API[1,2](@ref)
            await bot.set_group_whole_ban(
                group_id=int(group_id),
                enable=False  # False表示关闭全体禁言
            )
            await unban.finish(f"已成功解除群 {group_id} 的全体禁言")
        else:
            # 调用解除单个用户禁言API
            await bot.set_group_ban(
                group_id=int(group_id),
                user_id=int(qq_id),
                duration=0  # 禁言时长为0表示解除禁言
            )
            await unban.finish(f"已成功解除群 {group_id} 中用户 {qq_id} 的禁言")
        
    except Exception as e:
        await unban.finish(f"操作失败：{str(e)}")

# 可选的帮助信息
__plugin_name__ = '解除禁言'
__plugin_usage__ = '''
超级管理员私聊命令：
/admin unmute <群号> [QQ号|all]

示例：
/admin unmute 123456789          # 解除超级管理员在群123456789中的禁言
/admin unmute 123456789 987654321 # 解除用户987654321在群123456789中的禁言
/admin unmute 123456789 all       # 解除群123456789的全体禁言
'''