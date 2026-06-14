#!/usr/bin/env python3
"""
NoneBot2 好友申请处理插件（被动/可控模式）
功能：提供命令手动处理好友申请，并可配置关键词自动同意
作者：根据用户需求编写
日期：2026-01-03
"""

from nonebot import on_request, on_command, get_driver
from nonebot.adapters.onebot.v11 import Bot, FriendRequestEvent, Message, PrivateMessageEvent
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.log import logger
from typing import Dict, List, Set
import time

# 存储待处理的好友申请
# 结构: {flag: {"user_id": int, "comment": str, "time": float}}
pending_requests: Dict[str, Dict] = {}

# 配置类
class FriendConfig:
    def __init__(self):
        self.auto_approve_keywords: Set[str] = set()  # 自动同意的关键词
        self.enable_auto_approve: bool = False  # 是否启用自动同意
    
    def update_keywords(self, keywords: List[str]):
        """更新自动同意关键词"""
        self.auto_approve_keywords = set(keyword for keyword in keywords if keyword)
        logger.success(f"自动同意关键词已更新: {self.auto_approve_keywords}")

friend_config = FriendConfig()

# 创建事件响应器
friend_request = on_request(priority=5, block=False)

# 创建命令响应器
list_requests = on_command("待处理好友", permission=SUPERUSER, aliases={"查看好友申请"}, priority=1)
approve_friend = on_command("同意好友", permission=SUPERUSER, aliases={"通过好友"}, priority=1)
reject_friend = on_command("拒绝好友", permission=SUPERUSER, aliases={"拒绝好友申请"}, priority=1)
auto_approve = on_command("自动同意", permission=SUPERUSER, priority=1)

@friend_request.handle()
async def handle_friend_request(bot: Bot, event: FriendRequestEvent):
    """
    处理好友申请事件 - 被动模式
    """
    try:
        user_id = event.user_id
        flag = event.flag
        comment = event.comment or "无验证信息"
        
        # 存储申请信息
        pending_requests[flag] = {
            "user_id": user_id,
            "comment": comment,
            "time": time.time()
        }
        
        logger.info(f"收到好友申请：QQ{user_id}，验证信息：{comment}")
        
        # 如果启用自动同意且验证信息包含关键词
        if friend_config.enable_auto_approve and friend_config.auto_approve_keywords:
            for keyword in friend_config.auto_approve_keywords:
                if keyword in comment:
                    try:
                        await bot.set_friend_add_request(flag=flag, approve=True)
                        del pending_requests[flag]  # 清理已处理的申请
                        logger.success(f"已自动同意QQ{user_id}的好友申请（关键词: {keyword}）")
                        
                        # 可选：发送欢迎消息
                        welcome_msg = f"你好！我是机器人，已通过你的好友申请。你的验证信息包含关键词'{keyword}'。"
                        await bot.send_private_msg(user_id=user_id, message=welcome_msg)
                        return
                    except Exception as e:
                        logger.error(f"自动同意QQ{user_id}时出错: {str(e)}")
        
        # 通知管理员有新申请（如果不是自动同意的）
        for superuser in get_driver().config.superusers:
            try:
                notice = f"新的好友申请:\nQQ: {user_id}\n验证信息: {comment}\n使用命令处理。"
                await bot.send_private_msg(user_id=int(superuser), message=notice)
                logger.info(f"已通知管理员{superuser}处理好友申请")
            except Exception as e:
                logger.error(f"通知管理员失败: {str(e)}")
                
    except Exception as e:
        logger.error(f"处理好友申请时出现错误：{str(e)}")

@list_requests.handle()
async def handle_list_requests(bot: Bot, event: PrivateMessageEvent):
    """查看待处理的好友申请"""
    if not pending_requests:
        await list_requests.finish("当前没有待处理的好友申请")
    
    message = "待处理的好友申请:\n"
    for i, (flag, req) in enumerate(pending_requests.items(), 1):
        time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(req["time"]))
        message += f"{i}. QQ{req['user_id']} | 验证: {req['comment']} | 时间: {time_str}\n"
        message += f"   处理命令: 同意好友 {i} 或 拒绝好友 {i}\n"
    
    await list_requests.finish(message)

@approve_friend.handle()
async def handle_approve_friend(bot: Bot, event: PrivateMessageEvent, args: Message = CommandArg()):
    """同意好友申请"""
    arg_text = args.extract_plain_text().strip()
    
    if not arg_text and not pending_requests:
        await approve_friend.finish("当前没有待处理的好友申请")
    
    try:
        if arg_text.isdigit():
            # 按索引处理
            index = int(arg_text) - 1
            if 0 <= index < len(pending_requests):
                flag = list(pending_requests.keys())[index]
                req = pending_requests[flag]
                
                await bot.set_friend_add_request(flag=flag, approve=True)
                del pending_requests[flag]
                
                # 发送欢迎消息
                welcome_msg = "你好！我是机器人，已通过你的好友申请。"
                await bot.send_private_msg(user_id=req["user_id"], message=welcome_msg)
                
                await approve_friend.finish(f"已同意QQ{req['user_id']}的好友申请")
            else:
                await approve_friend.finish("索引超出范围")
        else:
            # 同意所有
            count = 0
            for flag, req in list(pending_requests.items()):
                try:
                    await bot.set_friend_add_request(flag=flag, approve=True)
                    del pending_requests[flag]
                    count += 1
                    
                    # 发送欢迎消息
                    welcome_msg = "你好！我是机器人，已通过你的好友申请。"
                    await bot.send_private_msg(user_id=req["user_id"], message=welcome_msg)
                    
                except Exception as e:
                    logger.error(f"同意QQ{req['user_id']}时出错: {str(e)}")
            
            await approve_friend.finish(f"已同意{count}个好友申请")
            
    except Exception as e:
        logger.error(f"处理同意命令时出错: {str(e)}")
        await approve_friend.finish("处理失败，请检查日志")

@reject_friend.handle()
async def handle_reject_friend(bot: Bot, event: PrivateMessageEvent, args: Message = CommandArg()):
    """拒绝好友申请"""
    arg_text = args.extract_plain_text().strip()
    
    if not pending_requests:
        await reject_friend.finish("当前没有待处理的好友申请")
    
    try:
        if arg_text.isdigit():
            # 按索引拒绝
            index = int(arg_text) - 1
            if 0 <= index < len(pending_requests):
                flag = list(pending_requests.keys())[index]
                req = pending_requests[flag]
                
                await bot.set_friend_add_request(flag=flag, approve=False)
                del pending_requests[flag]
                await reject_friend.finish(f"已拒绝QQ{req['user_id']}的好友申请")
            else:
                await reject_friend.finish("索引超出范围")
        else:
            # 拒绝所有
            count = 0
            for flag, req in list(pending_requests.items()):
                try:
                    await bot.set_friend_add_request(flag=flag, approve=False)
                    del pending_requests[flag]
                    count += 1
                except Exception as e:
                    logger.error(f"拒绝QQ{req['user_id']}时出错: {str(e)}")
            
            await reject_friend.finish(f"已拒绝{count}个好友申请")
            
    except Exception as e:
        logger.error(f"处理拒绝命令时出错: {str(e)}")
        await reject_friend.finish("处理失败，请检查日志")

@auto_approve.handle()
async def handle_auto_approve(bot: Bot, event: PrivateMessageEvent, args: Message = CommandArg()):
    """管理自动同意设置"""
    arg_text = args.extract_plain_text().strip()
    
    if not arg_text:
        # 显示当前状态
        status = "开启" if friend_config.enable_auto_approve else "关闭"
        keywords = "、".join(friend_config.auto_approve_keywords) if friend_config.auto_approve_keywords else "无"
        await auto_approve.finish(f"自动同意状态: {status}\n关键词: {keywords}")
    
    elif arg_text == "开启":
        friend_config.enable_auto_approve = True
        await auto_approve.finish("已开启自动同意功能")
    
    elif arg_text == "关闭":
        friend_config.enable_auto_approve = False
        await auto_approve.finish("已关闭自动同意功能")
    
    elif arg_text.startswith("关键词"):
        # 格式: 自动同意 关键词 关键词1 关键词2
        parts = arg_text.split()
        if len(parts) > 1:
            new_keywords = parts[1:]
            friend_config.update_keywords(new_keywords)
            await auto_approve.finish(f"已设置自动同意关键词: {new_keywords}")
        else:
            await auto_approve.finish("请提供关键词，如: 自动同意 关键词 学习 技术")

# 插件元信息
__plugin_name__ = "passive_friend_approve"
__plugin_usage__ = """被动模式好友申请处理插件

命令列表:
- 待处理好友 / 查看好友申请: 查看待处理的申请
- 同意好友 [序号]/[空]: 同意指定或所有申请
- 拒绝好友 [序号]/[空]: 拒绝指定或所有申请  
- 自动同意 [开启/关闭/关键词]: 管理自动同意设置

示例:
同意好友 1    # 同意第一个申请
同意好友      # 同意所有申请
自动同意 开启 # 开启自动同意
自动同意 关键词 学习 技术 # 设置关键词
"""
__plugin_version__ = "2.0.0"
__plugin_author__ = "根据用户需求编写"
__plugin_description__ = "支持手动处理和条件自动同意的好友申请插件"