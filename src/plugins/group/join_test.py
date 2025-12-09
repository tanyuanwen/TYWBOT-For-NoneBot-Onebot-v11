import random
import asyncio
from datetime import datetime, timedelta
from nonebot import CommandGroup
from typing import Dict, Tuple, Optional
from nonebot import on_notice, on_command, on_message
from nonebot.adapters.onebot.v11 import (
    Bot, 
    GroupIncreaseNoticeEvent,
    GroupMessageEvent,
    GROUP_ADMIN,
    GROUP_OWNER
    
)
from nonebot.rule import to_me
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot.params import CommandArg
from nonebot.adapters import Message
from nonebot.matcher import Matcher
from litebot_utils.blacklist.black import bl_manager
from litebot_utils.rule import is_global_admin
from src.plugins.menu.models import MatcherData
jointest = CommandGroup("进群验证", permission=is_global_admin)
join_test = jointest.command(
    "group",
    state=MatcherData(
        rm_name="进群验证", rm_usage="进群验证 [on|off]", rm_desc="用于确定用户是否是真人"
    ).model_dump(),
)
__plugin_meta__ = PluginMetadata(
    name="进群验证",
    description="进群需要完成100以内加减法验证",
    usage="管理员发送 进群验证 on 开启验证，进群验证 off 关闭验证",
    extra={"version": "1.0.0"}
)

# 存储配置和验证数据的字典
group_config: Dict[int, bool] = {}  # 群验证开关
verification_data: Dict[int, Dict[str, any]] = {}  # 验证数据
# 超管QQ号
SUPERUSER_QQ = 3671199392

# 生成验证问题
def generate_question() -> Tuple[str, int]:
    a = random.randint(1, 100)
    b = random.randint(1, 100)
    if random.choice([True, False]):  # 加减法随机
        return f"{a} + {b} = ?", a + b
    else:
        # 确保减法结果不为负数
        a, b = max(a, b), min(a, b)
        return f"{a} - {b} = ?", a - b

# 处理进群通知
group_increase = on_notice(priority=5, block=False)

@group_increase.handle()
async def handle_group_increase(bot: Bot, event: GroupIncreaseNoticeEvent):
    group_id = event.group_id
    user_id = event.user_id
    
    # 检查是否开启了验证
    if not group_config.get(group_id, False):
        return
    
    # 跳过管理员和超管
    member_info = await bot.get_group_member_info(group_id=group_id, user_id=user_id)
    if member_info.get("role") in ["admin", "owner"] or user_id == SUPERUSER_QQ:
        return
    
    # 生成验证问题
    question, answer = generate_question()
    
    # 存储验证数据
    verification_data[user_id] = {
        "group_id": group_id,
        "answer": answer,
        "start_time": datetime.now(),
        "question": question
    }
    
    # 发送验证问题
    await bot.send_group_msg(
        group_id=group_id,
        message=f"[CQ:at,qq={user_id}]\n欢迎新成员！请完成以下验证（直接发送答案）：\n{question}\n（5分钟内完成，否则将被移出群聊）"
    )
    
    # 设置5分钟超时任务
    asyncio.create_task(verify_timeout(bot, user_id, group_id))

# 超时检查任务
async def verify_timeout(bot: Bot, user_id: int, group_id: int):
    await asyncio.sleep(300)  # 5分钟
    
    # 检查是否还在验证中
    if user_id in verification_data and verification_data[user_id]["group_id"] == group_id:
        try:
            # 移出群聊
            await bot.set_group_kick(group_id=group_id, user_id=user_id)
            await bot.send_group_msg(
                group_id=group_id,
                message=f"用户{user_id}验证超时，已被移出群聊"
            )
        except Exception as e:
            # 如果踢人失败（可能是权限不足），发送提示
            await bot.send_group_msg(
                group_id=group_id,
                message=f"用户{user_id}验证超时，但踢人失败：{e}"
            )
        finally:
            # 清理验证数据
            if user_id in verification_data:
                del verification_data[user_id]

# 处理用户验证消息
verify_message = on_message(priority=10, block=False)

@verify_message.handle()
async def handle_verify(bot: Bot, event: GroupMessageEvent):
    user_id = event.user_id
    group_id = event.group_id
    
    # 检查是否是验证中的用户
    if user_id not in verification_data:
        return
    
    data = verification_data[user_id]
    if data["group_id"] != group_id:
        return
    
    # 获取用户输入
    try:
        user_answer = int(str(event.get_message()).strip())
    except ValueError:
        await bot.send_group_msg(
            group_id=group_id,
            message=f"[CQ:at,qq={user_id}] 请输入数字答案！"
        )
        return
    
    # 验证答案
    if user_answer == data["answer"]:
        # 验证通过
        await bot.send_group_msg(
            group_id=group_id,
            message=f"[CQ:at,qq={user_id}] 验证通过！欢迎加入本群！"
        )
        # 清理验证数据
        del verification_data[user_id]
    else:
        # 答案错误
        await bot.send_group_msg(
            group_id=group_id,
            message=f"[CQ:at,qq={user_id}] 答案错误，请重新输入！\n问题：{data['question']}"
        )

# 管理员控制命令
gjy_cmd = on_command("进群验证", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

@gjy_cmd.handle()
async def handle_gjy(bot: Bot, event: GroupMessageEvent, matcher: Matcher, args: Message = CommandArg()):
    group_id = event.group_id
    cmd = args.extract_plain_text().strip().lower()
    
    if cmd == "on":
        group_config[group_id] = True
        await matcher.finish(f"✅ 进群验证已开启")
    elif cmd == "off":
        group_config[group_id] = False
        # 清理该群的验证数据
        to_remove = []
        for user_id, data in verification_data.items():
            if data["group_id"] == group_id:
                to_remove.append(user_id)
        for user_id in to_remove:
            del verification_data[user_id]
        await matcher.finish(f"✅ 进群验证已关闭，并清理了验证队列")
    else:
        status = "开启" if group_config.get(group_id, False) else "关闭"
        await matcher.finish(f"当前进群验证状态：{status}\n使用 /gjy on 开启\n使用 /gjy off 关闭")

# 添加一个状态查询命令
status_cmd = on_command("gjy_status", priority=1, block=True, permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER)

@status_cmd.handle()
async def handle_status(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    status = "开启" if group_config.get(group_id, False) else "关闭"
    
    # 统计当前验证中的人数
    verifying_count = sum(1 for data in verification_data.values() if data["group_id"] == group_id)
    
    await status_cmd.finish(
        f"📊 进群验证状态\n"
        f"当前状态：{status}\n"
        f"验证中人数：{verifying_count}\n"
        f"超管QQ：{SUPERUSER_QQ}"
    )

# 超管强制关闭所有验证
force_off = on_command("gjy_force_off", priority=1, block=True, permission=SUPERUSER)

@force_off.handle()
async def handle_force_off(matcher: Matcher):
    global group_config, verification_data
    group_config.clear()
    verification_data.clear()
    await matcher.finish("✅ 已强制关闭所有群的验证，并清空所有验证数据")
