from nonebot import on_command, on_message, on_request
from nonebot.adapters.onebot.v11 import (
    Bot, Event, Message, MessageSegment, 
    GroupMessageEvent, PrivateMessageEvent, MessageEvent,
    FriendRequestEvent
)
from nonebot.rule import to_me
from nonebot.matcher import Matcher
from nonebot.params import CommandArg, ArgPlainText
from nonebot.permission import SUPERUSER
from nonebot.typing import T_State
import asyncio
import random
import time
from typing import Dict, List, Set, Optional

# ============================ 游戏核心数据与配置 ============================
games: Dict[int, Dict] = {}
user_current_group: Dict[int, int] = {}
SUPER_ADMINS = {3671199392}

# 计时器任务存储
game_timers: Dict[int, asyncio.Task] = {}
painter_timers: Dict[int, asyncio.Task] = {}  # 画师上传计时器

THEMES = [
    "猫咪", "星空", "海洋", "森林", "城市", "食物", "运动", "音乐", "书籍", "季节",
    "动物", "植物", "交通工具", "职业", "电影", "游戏", "国家", "历史", "科学", "艺术",
    "电脑", "手机", "河流", "山脉", "雨伞", "书包", "眼镜", "时钟", "桥梁", "飞机",
    "火车", "轮船", "自行车", "汽车", "月亮", "星星", "太阳", "云朵", "彩虹", "雪花",
    "火焰", "水滴", "石头", "沙滩", "沙漠", "草原", "岛屿", "城堡", "宫殿", "寺庙",
    "学校", "医院", "商场", "公园", "花园", "农场", "果园", "菜园", "厨房", "卧室",
    "客厅", "餐厅", "浴室", "办公室", "工厂", "车站", "机场", "港口", "码头", "道路",
    "路灯", "信号灯", "标志牌", "地图", "地球仪", "望远镜", "显微镜", "相机", "电视",
    "冰箱", "洗衣机", "空调", "风扇", "台灯", "蜡烛", "火柴", "钥匙", "锁", "钱包",
    "帽子", "围巾", "手套", "鞋子", "袜子", "裙子", "裤子", "衬衫", "外套", "领带",
    "TYW", "tyw", "蛋仔派对", "鸡蛋", "我的世界", "人", "Google", "宝塔面板",
    "云朵", "外挂", "杀戮光环", "KL_qiqi", "Python", "python", "代码",
    "Java", "java", "Kotlin", "kotlin", "JavaScript", "javascript", "TypeScript", "typescript",
    "HTML", "html", "CSS", "css", "Vue", "vue", "React", "react", "Angular", "angular",
    "初音未来", "洛天依", "少羽", "筷子夹水泥",
    "熊", "鹦鹉", "猫", "狗", "小高拐拐", "女装", "男娘", "ExRFy", "手机", "被子", "蟒蛇", "奥特曼", "金坷垃", "户晨风",
]

# 自动添加好友配置
AUTO_ADD_FRIEND = True

# ============================ 事件响应器定义 ============================
game_cmd = on_command("你画我猜", priority=10, block=True)
private_matcher = on_message(rule=to_me(), priority=5, block=False)
guess_matcher = on_message(priority=50, block=False)
friend_request_matcher = on_request(priority=5, block=False)

# ============================ 好友申请处理 ============================
@friend_request_matcher.handle()
async def handle_friend_request(bot: Bot, event: FriendRequestEvent):
    """自动处理好友申请"""
    if not AUTO_ADD_FRIEND:
        return
    
    user_id = event.user_id
    flag = event.flag
    
    try:
        await bot.set_friend_add_request(flag=flag, approve=True)
        await bot.send_private_msg(
            user_id=user_id,
            message="👋 我是你画我猜游戏Bot，已通过您的好友申请！欢迎使用「/你画我猜 加入游戏」参与游戏"
        )
    except Exception as e:
        print(f"添加好友失败: {e}")

# ============================ 权限检查函数 ============================
async def is_group_admin(bot: Bot, event: GroupMessageEvent) -> bool:
    """检查用户是否为群管理员"""
    try:
        member_info = await bot.get_group_member_info(
            group_id=event.group_id, 
            user_id=event.user_id
        )
        role = member_info.get("role", "member")
        return role in ["admin", "owner"]
    except:
        return False

async def is_super_admin(user_id: int) -> bool:
    return user_id in SUPER_ADMINS

async def check_admin_permission(bot: Bot, event: GroupMessageEvent) -> bool:
    return await is_group_admin(bot, event) or await is_super_admin(event.user_id)

async def check_friend_status(bot: Bot, user_id: int) -> bool:
    """检查用户是否为Bot好友"""
    try:
        await bot.send_private_msg(user_id=user_id, message="[你画我猜]好友状态检查")
        return True
    except:
        return False

async def auto_add_friend_prompt(bot: Bot, user_id: int, group_id: int):
    """提示用户添加好友"""
    try:
        bot_info = await bot.get_login_info()
        bot_qq = bot_info['user_id']
        await bot.send_group_msg(
            group_id=group_id,
            message=f"👤 用户 {await get_user_name(bot, user_id)} 请先添加Bot为好友（QQ: {bot_qq}）才能参与游戏"
        )
    except Exception as e:
        print(f"发送添加好友提示失败: {e}")

# ============================ 游戏逻辑函数 ============================
async def get_user_name(bot: Bot, user_id: int) -> str:
    """获取用户昵称"""
    try:
        info = await bot.get_stranger_info(user_id=user_id)
        return info.get("nickname", str(user_id))
    except:
        return str(user_id)

def calculate_similarity(word1: str, word2: str) -> float:
    """计算词相似度"""
    if word1 == word2:
        return 1.0
    
    len1, len2 = len(word1), len(word2)
    max_len = max(len1, len2)
    
    if max_len == 0:
        return 1.0
    
    if len1 > len2:
        word1, word2 = word2, word1
        len1, len2 = len2, len1
    
    current_row = list(range(len1 + 1))
    for i in range(1, len2 + 1):
        previous_row, current_row = current_row, [i] + [0] * len1
        for j in range(1, len1 + 1):
            add = previous_row[j] + 1
            delete = current_row[j - 1] + 1
            change = previous_row[j - 1]
            if word1[j - 1] != word2[i - 1]:
                change += 1
            current_row[j] = min(add, delete, change)
    
    edit_distance = current_row[len1]
    return 1 - (edit_distance / max_len)

def check_keyword_match(guess: str, target: str) -> bool:
    """检查关键词匹配"""
    guess = guess.strip().lower()
    target = target.strip().lower()
    
    if guess == target:
        return True
    
    if target in guess:
        return True
    
    similarity = calculate_similarity(guess, target)
    if similarity >= 0.7:
        return True
    
    return False

async def start_game(bot: Bot, group_id: int):
    """开始游戏"""
    if group_id not in games:
        return
        
    game = games[group_id]
    game["status"] = "playing"
    game["current_round"] = 0
    game["scores"] = {uid: 0 for uid in game["players"]}  # 修改：初始积分为0
    game["themes"] = {uid: random.choice(THEMES) for uid in game["players"]}
    game["guessers"] = set()
    game["current_guessers"] = set()
    game["painted_players"] = set()
    game["stop_timer"] = False
    
    if not game["players"]:
        await bot.send_group_msg(group_id=group_id, message="⚠️ 没有玩家参与游戏")
        return
    
    game["current_painter"] = random.choice(game["players"])
    game["start_time"] = time.time()
    
    first_painter_name = await get_user_name(bot, game["current_painter"])
    players_list = "\n".join([f"    - {await get_user_name(bot, uid)}" for uid in game["players"]])
    
    await bot.send_group_msg(
        group_id=group_id,
        message=f"🎨 游戏开始！当前玩家：\n{players_list}\n\n首位画家：{first_painter_name}"
    )
    
    theme = game["themes"][game["current_painter"]]
    try:
        await bot.send_private_msg(
            user_id=game["current_painter"],
            message=f"🎨 你的绘画主题是：{theme}\n请私信我发送你的画作图片（360秒内）"
        )
        # 启动画师上传计时器
        await start_painter_timer(bot, group_id, game["current_painter"])
    except:
        await bot.send_group_msg(group_id=group_id, message="⚠️ 无法私信画家，请确保已添加Bot为好友")

async def start_painter_timer(bot: Bot, group_id: int, painter_id: int):
    """启动画师上传计时器（360秒）"""
    if group_id in painter_timers:
        try:
            painter_timers[group_id].cancel()
        except:
            pass
    
    async def painter_timeout():
        try:
            await asyncio.sleep(360)  # 360秒计时
            
            if group_id not in games or games[group_id]["status"] != "playing":
                return
                
            game = games[group_id]
            if game["current_painter"] != painter_id:
                return
            
            # 画师超时未上传作品
            painter_name = await get_user_name(bot, painter_id)
            
            # 扣除积分（从当前积分中扣除）
            current_score = game["scores"].get(painter_id, 0)
            new_score = current_score - 3  # 直接扣除3分，可以为负数
            game["scores"][painter_id] = new_score
            
            await bot.send_group_msg(
                group_id=group_id,
                message=f"⏰ 画师 {painter_name} 360秒内未上传作品！\n"
                       f"📉 扣除3分，当前积分：{new_score}\n"
                       f"切换下一轮..."
            )
            
            # 强制切换到下一个画师
            await next_painter(bot, group_id)
            
        except asyncio.CancelledError:
            # 计时器被取消是正常情况
            return
        except Exception as e:
            print(f"画师计时器异常: {e}")
    
    painter_timers[group_id] = asyncio.create_task(painter_timeout())

async def next_painter(bot: Bot, group_id: int):
    """切换到下一位画家"""
    if group_id not in games:
        return
        
    game = games[group_id]
    game["guessers"] = set()
    game["current_guessers"] = set()
    
    # 记录当前画家已经画过
    if game["current_painter"]:
        game["painted_players"].add(game["current_painter"])
    
    # 检查是否所有玩家都画过一次
    if len(game["painted_players"]) >= len(game["players"]):
        await end_game(bot, group_id)
        return
    
    # 找出还未画过的玩家
    not_painted = [uid for uid in game["players"] if uid not in game["painted_players"]]
    
    if not_painted:
        game["current_painter"] = random.choice(not_painted)
        game["current_round"] += 1
        
        # 在群内提示下一轮画家
        painter_name = await get_user_name(bot, game["current_painter"])
        await bot.send_group_msg(
            group_id=group_id,
            message=f"🎨 下一轮画家是：{painter_name}"
        )
        
        # 私信新画家主题
        theme = game["themes"][game["current_painter"]]
        try:
            await bot.send_private_msg(
                user_id=game["current_painter"],
                message=f"🎨 轮到你了！主题：{theme}\n请私信我发送画作图片（360秒内）"
            )
            # 启动新的画师计时器
            await start_painter_timer(bot, group_id, game["current_painter"])
        except:
            await bot.send_group_msg(group_id=group_id, message="⚠️ 无法私信画家")
    else:
        await end_game(bot, group_id)

async def end_game(bot: Bot, group_id: int):
    """结束游戏并显示排行榜"""
    if group_id not in games:
        return
        
    game = games[group_id]
    game["status"] = "finished"
    
    # 取消所有计时器
    if group_id in game_timers:
        try:
            game_timers[group_id].cancel()
        except:
            pass
        del game_timers[group_id]
    
    if group_id in painter_timers:
        try:
            painter_timers[group_id].cancel()
        except:
            pass
        del painter_timers[group_id]
    
    # 按积分排序
    sorted_scores = sorted(game["scores"].items(), key=lambda x: x[1], reverse=True)
    rank_msg = "🏆 游戏结束！积分榜：\n"
    for i, (uid, score) in enumerate(sorted_scores):
        rank_msg += f"{i+1}. {await get_user_name(bot, uid)}: {score}分\n"
    
    await bot.send_group_msg(group_id=group_id, message=rank_msg)
    
    # 清理数据
    for uid in list(game["players"]):
        if uid in user_current_group:
            del user_current_group[uid]
    if group_id in games:
        del games[group_id]

async def handle_correct_guess(bot: Bot, group_id: int, guesser_id: int):
    """处理猜对逻辑"""
    if group_id not in games or games[group_id]["status"] != "playing":
        return False
        
    game = games[group_id]
    
    # 防止重复处理
    if guesser_id in game["guessers"]:
        return False
        
    painter_id = game["current_painter"]
    
    # 停止当前回合的计时器
    if group_id in game_timers:
        try:
            game_timers[group_id].cancel()
        except:
            pass
        if group_id in game_timers:
            del game_timers[group_id]
    
    # 停止画师计时器
    if group_id in painter_timers:
        try:
            painter_timers[group_id].cancel()
        except:
            pass
        if group_id in painter_timers:
            del painter_timers[group_id]
    
    # 加分（从0开始累计）
    current_guesser_score = game["scores"].get(guesser_id, 0)
    current_painter_score = game["scores"].get(painter_id, 0)
    
    game["scores"][guesser_id] = current_guesser_score + 3
    game["scores"][painter_id] = current_painter_score + 1
    game["guessers"].add(guesser_id)
    
    guesser_name = await get_user_name(bot, guesser_id)
    painter_name = await get_user_name(bot, painter_id)
    
    await bot.send_group_msg(
        group_id=group_id,
        message=Message([
            MessageSegment.text(f"🎉 {guesser_name} 猜对了！\n"),
            MessageSegment.text(f"   {guesser_name} +3分（当前：{current_guesser_score + 3}分）\n"),
            MessageSegment.text(f"   画家 {painter_name} +1分（当前：{current_painter_score + 1}分）\n"),
            MessageSegment.text("即将切换下一轮...")
        ])
    )
    
    await asyncio.sleep(2)
    await next_painter(bot, group_id)
    return True

async def guess_timer(bot: Bot, group_id: int, theme: str):
    """猜题计时器"""
    try:
        await asyncio.sleep(120)  # 120秒计时
        
        if group_id not in games or games[group_id]["status"] != "playing":
            return
            
        # 无人猜对，继续下一轮
        await bot.send_group_msg(
            group_id=group_id,
            message=f"⏰ 时间到！无人猜对正确答案：{theme}\n切换下一轮..."
        )
        await next_painter(bot, group_id)
        
    except asyncio.CancelledError:
        # 计时器被取消是正常情况
        return
    except Exception as e:
        print(f"猜题计时器异常: {e}")

# ============================ 群聊命令处理 ============================
@game_cmd.handle()
async def handle_game_command(bot: Bot, event: GroupMessageEvent, state: T_State, args: Message = CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    arg_text = args.extract_plain_text().strip()
    
    if arg_text == "加入游戏":
        # 检查是否已加入其他群
        if user_id in user_current_group and user_current_group[user_id] != group_id:
            await game_cmd.finish(f"⚠️ 你已加入群 {user_current_group[user_id]} 的游戏")
        
        # 检查好友状态
        if not await check_friend_status(bot, user_id):
            await auto_add_friend_prompt(bot, user_id, group_id)
            await game_cmd.finish("⚠️ 请先添加Bot为好友")
        
        # 初始化游戏数据
        if group_id not in games:
            games[group_id] = {
                "players": [],
                "status": "waiting",
                "scores": {},
                "themes": {},
                "current_painter": None,
                "current_round": 0,
                "start_time": None,
                "guessers": set(),
                "current_guessers": set(),
                "painted_players": set()
            }
        
        game = games[group_id]
        
        if game["status"] == "playing":
            await game_cmd.finish("⚠️ 游戏进行中，无法加入")
        
        if len(game["players"]) >= 20:
            await game_cmd.finish("⚠️ 玩家已满（最多8人）")
        
        if user_id not in game["players"]:
            game["players"].append(user_id)
            user_current_group[user_id] = group_id
        
        if len(game["players"]) == 20:
            await game_cmd.send("✅ 玩家已满，游戏自动开始！")
            await start_game(bot, group_id)
        else:
            await game_cmd.finish(f"✅ 加入成功！当前玩家：{len(game['players'])}/20")
    
    elif arg_text == "退出游戏":
        if group_id not in games or user_id not in games[group_id]["players"]:
            await game_cmd.finish("⚠️ 你未加入当前游戏")
        
        games[group_id]["players"].remove(user_id)
        if user_id in user_current_group:
            del user_current_group[user_id]
        
        if len(games[group_id]["players"]) == 0:
            del games[group_id]
            await game_cmd.finish("✅ 已退出游戏，当前无玩家")
        else:
            await game_cmd.finish(f"✅ 已退出游戏！当前玩家：{len(games[group_id]['players'])}/20")
    
    elif arg_text == "开始游戏":
        if group_id not in games:
            await game_cmd.finish("⚠️ 请先使用「/你画我猜 加入游戏」")
        
        game = games[group_id]
        if game["status"] == "playing":
            await game_cmd.finish("⚠️ 游戏已进行中")
        
        if len(game["players"]) < 2:
            await game_cmd.finish("⚠️ 至少需要2名玩家")
        
        await game_cmd.send("🎮 开始游戏！")
        await start_game(bot, group_id)
    
    elif arg_text.startswith("选"):
        if group_id not in games or games[group_id]["status"] != "playing":
            await game_cmd.finish("⚠️ 游戏未进行中")
        
        game = games[group_id]
        if user_id != game["current_painter"]:
            await game_cmd.finish("⚠️ 只有当前画师可以选择")
        
        selected_text = arg_text[1:].strip()
        selected_id = None
        
        # 解析被选者
        for segment in args:
            if segment.type == "at" and segment.data.get("qq"):
                selected_id = int(segment.data["qq"])
                break
        
        if selected_id is None and selected_text.isdigit():
            selected_id = int(selected_text)
        
        if selected_id is None:
            await game_cmd.finish("⚠️ 请使用「/你画我猜 选 @某人」或「/你画我猜 选 QQ号」")
        
        if selected_id in game["current_guessers"] and selected_id != user_id:
            await handle_correct_guess(bot, group_id, selected_id)
        else:
            await game_cmd.finish("⚠️ 选择失败，请确保该玩家在本轮猜过题且不是画师本人")
    
    elif arg_text == "结束游戏":
        if not await check_admin_permission(bot, event):
            await game_cmd.finish("⚠️ 只有管理员可以结束游戏")
        
        if group_id not in games:
            await game_cmd.finish("⚠️ 当前没有进行中的游戏")
        
        await game_cmd.send("🛑 管理员结束游戏！")
        await end_game(bot, group_id)
    
    elif arg_text == "我的分数":
        # 查看当前游戏中的个人分数
        if group_id in games and user_id in games[group_id]["players"]:
            score = games[group_id]["scores"].get(user_id, 0)
            await game_cmd.finish(f"📊 你当前的积分：{score}")
        else:
            await game_cmd.finish("📊 你当前没有参与游戏")
    
    else:
        help_msg = """
🎨 你画我猜游戏指令：
- /你画我猜 加入游戏 : 加入游戏（需先添加Bot为好友）
- /你画我猜 退出游戏 : 退出游戏
- /你画我猜 开始游戏 : 开始游戏（需至少2人）
- /你画我猜 选 @某人 : 画师选择猜对者
- /你画我猜 结束游戏 : 强制结束游戏（管理员可用）
- /你画我猜 我的分数 : 查看自己的当前积分

游戏规则：
1. 玩家需先添加Bot为好友
2. 满8人自动开始，或手动开始
3. 画家私信收到主题后发送画作（360秒内）
4. 其他玩家猜题，猜对者+3分，画家+1分
5. 360秒内未上传作品扣3分，并切换画师
6. 120秒内无人猜对则自动轮换
7. 每个玩家都会画一次
8. 初始积分为0，仅在本局游戏有效
        """.strip()
        await game_cmd.finish(help_msg)

# ============================ 私信图片处理 ============================
@private_matcher.handle()
async def handle_private_image(bot: Bot, event: PrivateMessageEvent, state: T_State):
    user_id = event.user_id
    
    if user_id not in user_current_group:
        return
    
    group_id = user_current_group[user_id]
    if group_id not in games or games[group_id]["status"] != "playing":
        return
    
    game = games[group_id]
    if user_id != game["current_painter"]:
        await private_matcher.finish("⚠️ 现在不是你的回合")
    
    # 检查图片
    image_msg = None
    for segment in event.message:
        if segment.type == "image":
            image_msg = segment
            break
    
    if not image_msg:
        await private_matcher.finish("⚠️ 请发送图片内容")
    
    # 取消画师上传计时器（成功上传作品）
    if group_id in painter_timers:
        try:
            painter_timers[group_id].cancel()
        except:
            pass
        if group_id in painter_timers:
            del painter_timers[group_id]
    
    # 转发图片到群聊
    theme = game["themes"][user_id]
    painter_name = await get_user_name(bot, user_id)
    
    await bot.send_group_msg(
        group_id=group_id,
        message=Message([
            MessageSegment.text(f"🎨 画家 {painter_name} 提交画作！\n"),
            MessageSegment.text("⏰ 120秒猜题时间开始！\n"),
            image_msg
        ])
    )
    
    # 启动猜题计时器
    if group_id in game_timers:
        try:
            game_timers[group_id].cancel()
        except:
            pass
    
    game_timers[group_id] = asyncio.create_task(guess_timer(bot, group_id, theme))

# ============================ 群聊猜题处理 ============================
@guess_matcher.handle()
async def handle_guess(bot: Bot, event: GroupMessageEvent, state: T_State):
    group_id = event.group_id
    user_id = event.user_id
    
    if (group_id not in games or 
        games[group_id]["status"] != "playing" or
        games[group_id]["current_painter"] is None):
        return
    
    game = games[group_id]
    painter_id = game["current_painter"]
    current_theme = game["themes"].get(painter_id)
    
    if not current_theme:
        return
    
    if (user_id not in game["players"] or 
        user_id == painter_id or
        user_id in game["guessers"]):
        return
    
    # 记录猜题者
    game["current_guessers"].add(user_id)
    
    # 自动检测猜题
    guess_text = event.get_plaintext().strip()
    if guess_text and check_keyword_match(guess_text, current_theme):
        await handle_correct_guess(bot, group_id, user_id)