from nonebot import on_command, on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, PrivateMessageEvent, Message, MessageSegment
from nonebot.adapters.onebot.v11.permission import GROUP_ADMIN, GROUP_OWNER
from nonebot.permission import SUPERUSER
from nonebot.rule import to_me
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot.log import logger
import asyncio
import random
import time
from typing import Dict, List, Set, Optional, Tuple

# 超级管理员QQ号
SUPERUSERS = {3671199392, 156014763}

# ==================== 游戏状态管理类 ====================
class GameState:
    def __init__(self):
        self.games: Dict[int, Dict] = {}  # 群号 -> 游戏数据
        self.player_groups: Dict[int, int] = {}  # 玩家QQ -> 群号
        self.lock = asyncio.Lock()
        self.start_timers: Dict[int, asyncio.Task] = {}  # 开始游戏计时器
        self.night_timers: Dict[int, asyncio.Task] = {}  # 夜晚计时器

    def calculate_roles(self, player_count: int) -> Tuple[List[str], int]:
        """根据玩家人数计算角色分配"""
        if player_count < 4:
            return [], 0
        
        # 4-5人：1杀手，6-8人：2杀手
        werewolf_count = 1 if player_count <= 5 else 2
        
        # 基础角色：预言家、女巫
        roles = ['预言家', '女巫']
        roles.extend(['杀手'] * werewolf_count)
        
        # 剩余为平民
        civilian_count = player_count - len(roles)
        roles.extend(['平民'] * civilian_count)
        
        return roles, werewolf_count

    async def add_player(self, group_id: int, user_id: int) -> Tuple[bool, str]:
        """添加玩家到游戏"""
        async with self.lock:
            # 检查玩家是否已在其他群游戏
            if user_id in self.player_groups:
                if self.player_groups[user_id] != group_id:
                    return False, "您已经在其他群参与游戏，无法重复加入！"
                else:
                    return False, "您已经在本群加入了游戏！"
            
            # 如果群游戏不存在或已结束，创建新游戏
            if group_id not in self.games or self.games[group_id]['status'] == 'finished':
                self._create_new_game(group_id)
            
            game = self.games[group_id]
            
            # 检查游戏状态
            if game['status'] != 'waiting':
                return False, "游戏已开始，无法加入！"
            
            # 检查人数限制
            if len(game['players']) >= game['max_players']:
                return False, "游戏人数已满（最多8人）！"
            
            # 添加玩家
            game['players'].add(user_id)
            self.player_groups[user_id] = group_id
            
            # 初始化玩家技能状态
            game['skill_used'][user_id] = {
                'kill': False, 'prophecy': False, 'poison': False, 'antidote': False, 'last_used': 0
            }
            return True, "加入游戏成功！"

    async def remove_player(self, group_id: int, user_id: int) -> Tuple[bool, str]:
        """移除玩家（退出游戏）"""
        async with self.lock:
            if group_id not in self.games:
                return False, "本群没有进行中的游戏！"
            
            game = self.games[group_id]
            
            if user_id not in game['players']:
                return False, "您没有参与本群游戏！"
            
            # 记录身份信息（用于退出提示）
            identity = game['identities'].get(user_id, '未知')
            
            # 从各种列表中移除玩家
            game['players'].remove(user_id)
            game['alive_players'].discard(user_id)
            game['killed_tonight'].discard(user_id)
            game['saved_tonight'].discard(user_id)
            
            # 移除技能记录
            if user_id in game['skill_used']:
                del game['skill_used'][user_id]
            
            # 移除投票记录
            if user_id in game.get('votes', {}):
                del game['votes'][user_id]
            
            # 移除玩家群组映射
            if user_id in self.player_groups:
                del self.player_groups[user_id]
            
            # 处理游戏状态
            if game['status'] == 'playing' and len(game['alive_players']) < 2:
                game['status'] = 'finished'
                await self._cleanup_game(group_id)
                return True, f"玩家 {user_id}（身份：{identity}）已退出游戏，游戏因人数不足结束！"
            
            # 如果等待中且没有玩家了，清理游戏
            if game['status'] == 'waiting' and len(game['players']) == 0:
                # 取消计时器
                if group_id in self.start_timers:
                    self.start_timers[group_id].cancel()
                    del self.start_timers[group_id]
                del self.games[group_id]
            
            return True, f"玩家 {user_id}（身份：{identity}）已退出游戏！"

    async def start_game(self, group_id: int) -> Tuple[bool, str]:
        """开始游戏"""
        async with self.lock:
            if group_id not in self.games:
                return False, "游戏数据不存在！"
            
            game = self.games[group_id]
            player_count = len(game['players'])
            
            # 检查开始条件
            if player_count < 4 or player_count > 8 or game['status'] != 'waiting':
                return False, "游戏开始条件不满足！"
            
            # 随机分配角色
            players = list(game['players'])
            random.shuffle(players)
            
            # 计算角色分配
            roles, werewolf_count = self.calculate_roles(player_count)
            game['werewolf_count'] = werewolf_count
            
            # 分配身份
            game['identities'] = {}
            for i, player in enumerate(players):
                if i < len(roles):
                    game['identities'][player] = roles[i]
                else:
                    game['identities'][player] = '平民'
            
            # 记录杀手队友信息（新增功能）
            game['werewolf_partners'] = {}
            werewolf_players = [p for p, role in game['identities'].items() if role == '杀手']
            
            for killer in werewolf_players:
                # 排除自己，记录其他杀手队友
                partners = [p for p in werewolf_players if p != killer]
                game['werewolf_partners'][killer] = partners
            
            # 初始化游戏状态
            game['alive_players'] = set(players)
            game['status'] = 'playing'
            game['game_start_time'] = time.time()
            game['round_count'] = 0
            game['killed_tonight'] = set()
            game['saved_tonight'] = set()
            game['votes'] = {}
            
            return True, "游戏开始成功！"

    async def end_game(self, group_id: int, reason: str = "正常结束") -> Tuple[bool, str]:
        """结束游戏并公布所有玩家身份"""
        async with self.lock:
            if group_id not in self.games:
                return False, "游戏数据不存在！"
            
            game = self.games[group_id]
            
            # 记录游戏结束
            game['status'] = 'finished'
            game['end_reason'] = reason
            
            # 生成身份公布信息
            identity_map = {
                '杀手': '🔪🔪杀手',
                '预言家': '🔮🔮预言家', 
                '女巫': '🧪🧪女巫',
                '平民': '👥👥平民'
            }
            
            # 按身份类型分类玩家
            roles_dict = {
                '杀手': [],
                '预言家': [],
                '女巫': [], 
                '平民': []
            }
            
            for player_id in game['players']:
                identity = game['identities'].get(player_id, '未知')
                if identity in roles_dict:
                    roles_dict[identity].append(player_id)
            
            # 构建身份公布消息
            identity_list = []
            for role, players in roles_dict.items():
                if players:
                    icon = identity_map.get(role, '🎭🎭')
                    identity_list.append(f"{icon}{role}：{', '.join(map(str, players))}")
            
            identities_message = "\n".join(identity_list)
            
            # 记录获胜方
            winner = "杀手阵营" if "杀手" in reason else "平民阵营"
            game['winner'] = winner
            
            # 清理玩家群组映射
            for player_id in list(game['players']):
                if player_id in self.player_groups:
                    del self.player_groups[player_id]
            
            # 取消所有计时器
            if group_id in self.start_timers:
                self.start_timers[group_id].cancel()
                del self.start_timers[group_id]
            
            if group_id in self.night_timers:
                self.night_timers[group_id].cancel()
                del self.night_timers[group_id]
            
            # 延迟清理游戏数据
            async def delayed_cleanup():
                await asyncio.sleep(10)  # 留出足够时间发送消息
                async with self.lock:
                    if group_id in self.games and self.games[group_id]['status'] == 'finished':
                        del self.games[group_id]
            
            asyncio.create_task(delayed_cleanup())
            
            return True, identities_message

    def _create_new_game(self, group_id: int):
        """创建新的游戏实例"""
        self.games[group_id] = {
            'players': set(),
            'status': 'waiting',  # waiting, playing, finished
            'identities': {},
            'alive_players': set(),
            'killed_tonight': set(),
            'saved_tonight': set(),
            'skill_used': {},
            'votes': {},
            'max_players': 8,
            'werewolf_count': 0,
            'round_count': 0,
            'skill_timeout': 60,
            'game_start_time': 0,
            'night_start_time': 0,
            'is_night': False,
            'winner': '',
            'end_reason': '',
            'werewolf_partners': {}  # 新增：记录杀手队友信息
        }

    async def can_use_skill(self, user_id: int, skill_type: str, game: Dict) -> Tuple[bool, str]:
        """检查技能使用条件"""
        if user_id not in game.get('skill_used', {}):
            return False, "玩家技能记录不存在"
        
        skill_record = game['skill_used'][user_id]
        
        # 检查技能是否已使用
        if skill_type == 'kill' and skill_record['kill']:
            return False, "❌❌ 您的杀人技能已经使用过了！"
        elif skill_type == 'prophecy' and skill_record['prophecy']:
            return False, "❌❌ 您的查验技能已经使用过了！"
        elif skill_type == 'poison' and skill_record['poison']:
            return False, "❌❌ 您的毒药已经使用过了！"
        elif skill_type == 'antidote' and skill_record['antidote']:
            return False, "❌❌ 您的解药已经使用过了！"
        
        # 检查是否在夜晚阶段
        if not game.get('is_night', False):
            return False, "❌❌ 当前不是夜晚阶段，无法使用技能！"
        
        # 检查时间限制
        current_time = time.time()
        night_elapsed = current_time - game.get('night_start_time', 0)
        if night_elapsed > game['skill_timeout']:
            return False, f"❌❌ 技能使用时间已过！夜晚只有{game['skill_timeout']}秒行动时间"
        
        return True, "可以正常使用技能"

    async def mark_skill_used(self, user_id: int, skill_type: str, game: Dict):
        """标记技能已使用"""
        if user_id in game['skill_used']:
            game['skill_used'][user_id][skill_type] = True
            game['skill_used'][user_id]['last_used'] = time.time()

# ==================== 全局游戏状态实例 ====================
game_state = GameState()

# ==================== 群内命令处理器 ====================
killer_group = on_command("谁是杀手", priority=10, block=True)

@killer_group.handle()
async def handle_group_command(bot: Bot, event: GroupMessageEvent, matcher: Matcher, args: Message = CommandArg()):
    command_text = args.extract_plain_text().strip()
    group_id = event.group_id
    user_id = event.user_id
    
    if command_text == "加入游戏":
        await handle_join_game(bot, group_id, user_id, matcher)
    
    elif command_text == "开始游戏":
        await handle_start_game(bot, group_id, user_id, matcher)
    
    elif command_text == "退出游戏":
        await handle_quit_game(group_id, user_id, matcher)
    
    elif command_text == "停止游戏":
        await handle_stop_game(bot, group_id, user_id, matcher)
    
    elif command_text == "游戏状态":
        await handle_game_status(group_id, matcher)
    
    elif not command_text:
        await show_help(matcher)
    
    else:
        await matcher.finish("❌❌ 未知命令！输入【/谁是杀手】查看帮助")

# ==================== 命令处理函数 ====================
async def handle_join_game(bot: Bot, group_id: int, user_id: int, matcher: Matcher):
    """处理加入游戏"""
    try:
        await bot.send_private_msg(user_id=user_id, message="🔐🔐 好友验证通过！")
    except:
        await matcher.finish("❌❌ 无法向您发送私信，请先添加机器人为好友！")
    
    success, message = await game_state.add_player(group_id, user_id)
    if not success:
        await matcher.finish(f"❌❌ {message}")
    
    game = game_state.games[group_id]
    player_count = len(game['players'])
    
    await matcher.send(f"✅ {message}当前人数：{player_count}/8")
    
    # 检查是否满足自动开始条件
    if player_count >= 8:
        await matcher.send("✅ 人数已满，游戏将在10秒后自动开始！")
        if group_id in game_state.start_timers:
            game_state.start_timers[group_id].cancel()
        
        start_task = asyncio.create_task(auto_start_game(bot, group_id, matcher))
        game_state.start_timers[group_id] = start_task

async def handle_start_game(bot: Bot, group_id: int, user_id: int, matcher: Matcher):
    """处理开始游戏（非管理员可开始）"""
    if group_id not in game_state.games:
        await matcher.finish("❌❌ 本群没有等待中的游戏！")
    
    game = game_state.games[group_id]
    
    if game['status'] != 'waiting':
        await matcher.finish("❌❌ 游戏已开始或已结束！")
    
    player_count = len(game['players'])
    
    if player_count < 4:
        await matcher.finish(f"❌❌ 玩家人数不足（{player_count}/4）！")
    
    # 检查玩家是否在游戏中（非管理员权限检查）
    if user_id not in game['players']:
        await matcher.finish("❌❌ 您需要先加入游戏才能开始游戏！")
    
    # 取消现有计时器
    if group_id in game_state.start_timers:
        game_state.start_timers[group_id].cancel()
    
    await matcher.send("🎮🎮 玩家手动开始游戏！游戏将在5秒后开始！")
    await asyncio.sleep(5)
    
    success, message = await game_state.start_game(group_id)
    if success:
        await start_game_process(bot, group_id, matcher)
    else:
        await matcher.send(f"❌❌ 游戏启动失败：{message}")

async def handle_quit_game(group_id: int, user_id: int, matcher: Matcher):
    """处理退出游戏"""
    success, message = await game_state.remove_player(group_id, user_id)
    await matcher.send(f"📢📢 {message}")

async def handle_stop_game(bot: Bot, group_id: int, user_id: int, matcher: Matcher):
    """处理停止游戏（需要管理员权限）"""
    # 检查管理员权限
    has_permission = False
    try:
        member_info = await bot.get_group_member_info(group_id=group_id, user_id=user_id)
        if member_info.get('role') in ['admin', 'owner']:
            has_permission = True
    except:
        pass
    
    if not has_permission and user_id not in SUPERUSERS:
        await matcher.finish("❌❌ 只有管理员和超级管理员可以停止游戏！")
    
    success, message = await game_state.end_game(group_id, "管理员强制结束")
    await matcher.send(f"📢📢 {message}")

async def handle_game_status(group_id: int, matcher: Matcher):
    """处理游戏状态查询"""
    if group_id not in game_state.games:
        await matcher.send("✅ 本群没有进行中的游戏")
        return
    
    game = game_state.games[group_id]
    status_msg = f"🎯🎯 游戏状态：{game['status']}\n👥👥 玩家人数：{len(game['players'])}/8"
    
    if game['status'] == 'waiting':
        player_count = len(game['players'])
        if player_count >= 8:
            status_msg += "\n✅ 人数已满，即将自动开始！"
        elif player_count >= 4:
            status_msg += "\n🎮🎮 可手动开始游戏"
    
    elif game['status'] == 'playing':
        status_msg += f"\n❤️ 存活玩家：{len(game['alive_players'])}"
        status_msg += f"\n🔪🔪 杀手数量：{game['werewolf_count']}"
        status_msg += f"\n🔄🔄 当前回合：第{game['round_count']}天"
    
    await matcher.send(status_msg)

async def auto_start_game(bot: Bot, group_id: int, matcher: Matcher):
    """自动开始游戏（满8人时）"""
    try:
        for i in range(10, 0, -1):
            if group_id not in game_state.games or game_state.games[group_id]['status'] != 'waiting':
                return
            await asyncio.sleep(1)
        
        if group_id in game_state.games and game_state.games[group_id]['status'] == 'waiting':
            success, message = await game_state.start_game(group_id)
            if success:
                await start_game_process(bot, group_id, matcher)
    except Exception as e:
        logger.error(f"自动开始游戏出错: {e}")

async def start_game_process(bot: Bot, group_id: int, matcher: Matcher):
    """开始游戏流程"""
    game = game_state.games[group_id]
    werewolf_count = game['werewolf_count']
    player_count = len(game['players'])
    
    # 私信发送身份信息
    successful_sends = 0
    for player, identity in game['identities'].items():
        try:
            skill_help = get_role_skill_help(identity)
            
            # 如果是杀手且有队友，添加队友信息（新增功能）
            extra_info = ""
            if identity == '杀手' and player in game['werewolf_partners']:
                partners = game['werewolf_partners'][player]
                if partners:  # 如果有队友
                    partner_text = ", ".join(map(str, partners))
                    extra_info = f"\n\n🤝🤝 您的杀手队友是：{partner_text}\n💡💡 请与队友协作行动！"
            
            await bot.send_private_msg(
                user_id=player,
                message=f"🎮🎮 游戏开始！\n\n"
                       f"📍 您的身份是：{identity}\n"
                       f"📊📊 游戏信息：{player_count}人局，{werewolf_count}个杀手"
                       f"{extra_info}\n\n"
                       f"💡💡 技能指令：\n{skill_help}\n\n"
                       f"⚠️ 重要提示：所有技能只能使用一次！\n"
                       f"⏰⏰⏰ 夜晚阶段请及时行动！"
            )
            successful_sends += 1
        except Exception as e:
            logger.error(f"向玩家{player}发送身份失败: {e}")
    
    # 群内公告
    start_msg = f"🎉🎉 游戏开始！{player_count}人局，{werewolf_count}个杀手\n"
    start_msg += f"✅ 身份信息已通过私信发送！\n"
    start_msg += f"⚠️ 所有技能只能使用一次，请谨慎选择使用时机！"
    
    await matcher.send(start_msg)
    
    # 开始游戏主循环
    await run_game_loop(bot, group_id)

def get_role_skill_help(identity: str) -> str:
    """获取角色技能帮助信息"""
    if identity == '杀手':
        return "🔪🔪 杀人技能：/谁是杀手 刀 [QQ号]\n💡💡 示例：/谁是杀手 刀 123456"
    elif identity == '预言家':
        return "🔮🔮 查验技能：/谁是杀手 预言 [QQ号]\n💡💡 示例：/谁是杀手 预言 123456"
    elif identity == '女巫':
        return "☠☠️ 毒药：/谁是杀手 毒 [QQ号]\n💊💊 解药：/谁是杀手 救 [QQ号]\n💡💡 每种药物只能使用一次"
    else:
        return "👥👥 平民没有特殊技能，请积极参与讨论和投票"

# ==================== 游戏主循环 ====================
async def run_game_loop(bot: Bot, group_id: int):
    """游戏主循环"""
    game = game_state.games.get(group_id)
    if not game or game['status'] != 'playing':
        return
    
    round_count = 0
    
    while game['status'] == 'playing' and len(game['alive_players']) >= 2:
        round_count += 1
        game['round_count'] = round_count
        
        # 夜晚阶段
        await run_night_phase(bot, group_id, game, round_count)
        if await check_game_over(bot, group_id):
            break
        
        # 白天阶段
        await run_day_phase(bot, group_id, game, round_count)
        if await check_game_over(bot, group_id):
            break
        
        await asyncio.sleep(2)

async def run_night_phase(bot: Bot, group_id: int, game: Dict, round_count: int):
    """执行夜晚阶段"""
    game['is_night'] = True
    game['night_start_time'] = time.time()
    game['killed_tonight'] = set()
    game['saved_tonight'] = set()
    
    await bot.send_group_msg(
        group_id=group_id,
        message=f"🌙🌙 第{round_count}天夜晚开始！\n"
               f"⏰⏰⏰ 特殊身份玩家请在{game['skill_timeout']}秒内行动！\n"
               f"💡💡 使用私信发送技能指令！"
    )
    
    # 等待行动时间
    await asyncio.sleep(game['skill_timeout'])
    
    # 处理夜晚结果
    killed_tonight = game['killed_tonight'] - game['saved_tonight']
    
    if killed_tonight:
        for player in killed_tonight:
            if player in game['alive_players']:
                game['alive_players'].remove(player)
                identity = game['identities'][player]
                identity_icon = {'杀手': '🔪🔪', '预言家': '🔮🔮', '女巫': '🧪🧪', '平民': '👥👥'}.get(identity, '🎭🎭')
                await bot.send_group_msg(
                    group_id=group_id,
                    message=f"💀💀 玩家 {player} {identity_icon}{identity} 在夜晚被杀害！"
                )
    else:
        await bot.send_group_msg(group_id=group_id, message="🌃🌃 今晚是平安夜，无人死亡！")
    
    game['is_night'] = False

async def run_day_phase(bot: Bot, group_id: int, game: Dict, round_count: int):
    """执行白天阶段"""
    alive_count = len(game['alive_players'])
    
    # 讨论阶段
    await bot.send_group_msg(
        group_id=group_id,
        message=f"☀☀️ 第{round_count}天白天开始！\n"
               f"❤️ 存活玩家：{alive_count}人\n"
               f"💬💬 请开始讨论（60秒）"
    )
    await asyncio.sleep(60)
    
    # 投票阶段
    await bot.send_group_msg(group_id=group_id, message="🗳🗳️ 开始投票！使用【/谁是杀手 投 QQ号】投票（30秒）")
    game['votes'] = {}
    
    await asyncio.sleep(30)
    
    # 处理投票结果
    if game['votes']:
        vote_count = {}
        for voter, target in game['votes'].items():
            if voter in game['alive_players'] and target in game['alive_players']:
                vote_count[target] = vote_count.get(target, 0) + 1
        
        if vote_count:
            max_votes = max(vote_count.values())
            voted_out = [p for p, v in vote_count.items() if v == max_votes]
            
            if len(voted_out) == 1:
                player_out = voted_out[0]
                game['alive_players'].remove(player_out)
                identity = game['identities'][player_out]
                identity_icon = {'杀手': '🔪🔪', '预言家': '🔮🔮', '女巫': '🧪🧪', '平民': '👥👥'}.get(identity, '🎭🎭')
                await bot.send_group_msg(
                    group_id=group_id,
                    message=f"⚖⚖️ 玩家 {player_out} {identity_icon}{identity} 被投票出局！"
                )

async def check_game_over(bot: Bot, group_id: int) -> bool:
    """检查游戏是否结束"""
    game = game_state.games.get(group_id)
    if not game or game['status'] != 'playing':
        return True
    
    alive_players = game['alive_players']
    alive_count = len(alive_players)
    
    # 检查玩家人数是否足够继续游戏
    if alive_count < 2:
        winner = "杀手阵营"  # 默认
        # 统计身份决定获胜方
        alive_identities = [game['identities'][p] for p in alive_players]
        killer_count = alive_identities.count('杀手')
        if killer_count == 0:
            winner = "平民阵营"
        
        await announce_game_result(bot, group_id, winner)
        return True
    
    # 统计身份决定胜负
    alive_identities = [game['identities'][p] for p in alive_players]
    killer_count = alive_identities.count('杀手')
    civilian_count = alive_count - killer_count
    
    if killer_count == 0:
        await announce_game_result(bot, group_id, "平民阵营")
        return True
    elif killer_count >= civilian_count:
        await announce_game_result(bot, group_id, "杀手阵营")
        return True
    
    return False

async def announce_game_result(bot: Bot, group_id: int, winner: str):
    """宣布游戏结果并公布身份"""
    game = game_state.games[group_id]
    
    # 宣布胜负
    winner_text = "🎉🎉 游戏结束！所有杀手被消灭，平民阵营获胜！" if winner == "平民阵营" else \
                  "💀💀 游戏结束！杀手阵营获胜！"
    
    await bot.send_group_msg(group_id=group_id, message=winner_text)
    await asyncio.sleep(2)
    
    # 公布所有玩家身份
    success, identities_message = await game_state.end_game(group_id, f"{winner}获胜")
    
    if success:
        # 构建完整的身份公布消息
        identity_map = {
            '杀手': '🔪🔪杀手',
            '预言家': '🔮🔮预言家', 
            '女巫': '🧪🧪女巫',
            '平民': '👥👥平民'
        }
        
        final_message = f"🎉🎉 游戏结束！所有玩家身份公布：\n\n{identities_message}\n\n"
        final_message += f"🏆🏆 获胜方：{winner}\n\n"
        final_message += "🔄🔄 游戏数据已重置！想要开始新游戏，请重新使用【/谁是杀手 加入游戏】"
        
        await bot.send_group_msg(group_id=group_id, message=final_message)

# ==================== 私信命令处理器 ====================
killer_private = on_command("谁是杀手", priority=10, block=True, rule=to_me())

@killer_private.handle()
async def handle_private_command(bot: Bot, event: PrivateMessageEvent, matcher: Matcher, args: Message = CommandArg()):
    user_id = event.user_id
    command_text = args.extract_plain_text().strip()
    
    if command_text in ["退出游戏", "退出"]:
        await handle_private_quit(user_id, matcher)
        return
    
    if command_text in ["身份", "我的身份"]:
        await handle_check_identity(user_id, matcher)
        return
    
    if command_text == "技能状态":
        await handle_skill_status(user_id, matcher)
        return
    
    if command_text == "队友":
        await handle_check_partners(user_id, matcher)
        return
    
    # 获取玩家所在游戏
    group_id = game_state.player_groups.get(user_id)
    if not group_id or group_id not in game_state.games:
        await matcher.finish("❌❌ 您没有参与任何游戏！")
    
    game = game_state.games[group_id]
    
    if game['status'] != 'playing' or user_id not in game['alive_players']:
        await matcher.finish("❌❌ 游戏未进行中或您已出局！")
    
    identity = game['identities'][user_id]
    
    # 处理技能命令
    if identity == '杀手' and command_text.startswith('刀 '):
        await handle_killer_skill(user_id, group_id, game, command_text, matcher)
    
    elif identity == '预言家' and command_text.startswith('预言 '):
        await handle_prophet_skill(user_id, group_id, game, command_text, matcher)
    
    elif identity == '女巫':
        if command_text.startswith('毒 '):
            await handle_poison_skill(user_id, group_id, game, command_text, matcher)
        elif command_text.startswith('救 '):
            await handle_antidote_skill(user_id, group_id, game, command_text, matcher)
        else:
            await matcher.finish("❌❌ 女巫命令格式错误！使用『/谁是杀手 毒 QQ号』或『/谁是杀手 救 QQ号』")
    
    else:
        await matcher.finish("❌❌ 无效的命令或您没有权限使用该技能！")

# ==================== 私信命令处理函数 ====================
async def handle_private_quit(user_id: int, matcher: Matcher):
    """私信退出游戏"""
    group_id = game_state.player_groups.get(user_id)
    if not group_id:
        await matcher.finish("❌❌ 您没有参与任何游戏！")
    
    success, message = await game_state.remove_player(group_id, user_id)
    await matcher.send(f"📢📢 {message}")

async def handle_check_identity(user_id: int, matcher: Matcher):
    """查看身份"""
    group_id = game_state.player_groups.get(user_id)
    if not group_id or group_id not in game_state.games:
        await matcher.finish("❌❌ 您没有参与任何游戏！")
    
    game = game_state.games[group_id]
    identity = game['identities'].get(user_id, '未知')
    identity_display = {
        '杀手': '🔪🔪杀手', '预言家': '🔮🔮预言家', '女巫': '🧪🧪女巫', '平民': '👥👥平民'
    }.get(identity, identity)
    
    await matcher.send(f"🎭🎭 您的身份是：{identity_display}")

async def handle_skill_status(user_id: int, matcher: Matcher):
    """查看技能状态"""
    group_id = game_state.player_groups.get(user_id)
    if not group_id or group_id not in game_state.games:
        await matcher.finish("❌❌ 您没有参与任何游戏！")
    
    game = game_state.games[group_id]
    
    if game['status'] != 'playing' or user_id not in game['alive_players']:
        await matcher.finish("❌❌ 游戏未进行中或您已出局！")
    
    identity = game['identities'][user_id]
    skill_record = game['skill_used'][user_id]
    
    status_msg = f"🎭🎭 您的身份：{identity}\n⏰⏰⏰ 技能状态：\n"
    
    if identity == '杀手':
        status = "✅ 可用" if not skill_record['kill'] else "❌❌ 已使用"
        status_msg += f"🔪🔪 杀人技能：{status}\n"
    
    elif identity == '预言家':
        status = "✅ 可用" if not skill_record['prophecy'] else "❌❌ 已使用"
        status_msg += f"🔮🔮 查验技能：{status}\n"
    
    elif identity == '女巫':
        poison_status = "✅ 可用" if not skill_record['poison'] else "❌❌ 已使用"
        antidote_status = "✅ 可用" if not skill_record['antidote'] else "❌❌ 已使用"
        status_msg += f"☠☠️ 毒药：{poison_status}\n"
        status_msg += f"💊💊 解药：{antidote_status}\n"
    
    else:
        status_msg += "👥👥 平民没有特殊技能\n"
    
    await matcher.send(status_msg)

async def handle_check_partners(user_id: int, matcher: Matcher):
    """查看队友信息（新增功能）"""
    group_id = game_state.player_groups.get(user_id)
    if not group_id or group_id not in game_state.games:
        await matcher.finish("❌❌ 您没有参与任何游戏！")
    
    game = game_state.games[group_id]
    
    if game['status'] != 'playing' or user_id not in game['alive_players']:
        await matcher.finish("❌❌ 游戏未进行中或您已出局！")
    
    identity = game['identities'][user_id]
    
    if identity != '杀手':
        await matcher.finish("❌❌ 只有杀手身份可以查看队友信息！")
    
    # 获取队友信息
    if user_id in game['werewolf_partners']:
        partners = game['werewolf_partners'][user_id]
        if partners:
            partner_text = ", ".join(map(str, partners))
            await matcher.send(f"🤝🤝 您的杀手队友是：{partner_text}\n💡💡 请与队友协作行动！")
        else:
            await matcher.send("🤝🤝 您没有队友，是唯一的杀手！")
    else:
        await matcher.send("❌❌ 队友信息不存在！")

async def handle_killer_skill(user_id: int, group_id: int, game: Dict, command_text: str, matcher: Matcher):
    """处理杀手技能"""
    can_use, message = await game_state.can_use_skill(user_id, 'kill', game)
    if not can_use:
        await matcher.finish(message)
    
    target_str = command_text[2:].strip()
    try:
        target = int(target_str)
    except:
        await matcher.finish("❌❌ 请输入正确的QQ号！")
    
    if target not in game['alive_players']:
        await matcher.finish("❌❌ 目标玩家不存在或已出局！")
    
    if target == user_id:
        await matcher.finish("❌❌ 不能自杀！")
    
    game['killed_tonight'].add(target)
    await game_state.mark_skill_used(user_id, 'kill', game)
    await matcher.send(f"✅ 您选择了击杀 {target} 号玩家！\n⚠️ 杀人技能已使用，无法再次使用！")

async def handle_prophet_skill(user_id: int, group_id: int, game: Dict, command_text: str, matcher: Matcher):
    """处理预言家技能"""
    can_use, message = await game_state.can_use_skill(user_id, 'prophecy', game)
    if not can_use:
        await matcher.finish(message)
    
    target_str = command_text[3:].strip()
    try:
        target = int(target_str)
    except:
        await matcher.finish("❌❌ 请输入正确的QQ号！")
    
    if target not in game['alive_players']:
        await matcher.finish("❌❌ 目标玩家不存在或已出局！")
    
    if target == user_id:
        await matcher.finish("❌❌ 不能查验自己！")
    
    target_identity = game['identities'][target]
    identity_text = {
        '杀手': '🔪🔪杀手', '预言家': '🔮🔮预言家', '女巫': '🧪🧪女巫', '平民': '👥👥平民'
    }.get(target_identity, '未知')
    
    await game_state.mark_skill_used(user_id, 'prophecy', game)
    await matcher.send(f"🔮🔮 查验结果：玩家 {target} 的身份是：{identity_text}\n⚠️ 查验技能已使用，无法再次使用！")

async def handle_poison_skill(user_id: int, group_id: int, game: Dict, command_text: str, matcher: Matcher):
    """处理毒药技能"""
    can_use, message = await game_state.can_use_skill(user_id, 'poison', game)
    if not can_use:
        await matcher.finish(message)
    
    target_str = command_text[2:].strip()
    try:
        target = int(target_str)
    except:
        await matcher.finish("❌❌ 请输入正确的QQ号！")
    
    if target not in game['alive_players']:
        await matcher.finish("❌❌ 目标玩家不存在或已出局！")
    
    if target == user_id:
        await matcher.finish("❌❌ 不能对自己使用毒药！")
    
    game['killed_tonight'].add(target)
    await game_state.mark_skill_used(user_id, 'poison', game)
    await matcher.send(f"☠☠️ 您使用毒药击杀了 {target} 号玩家！\n⚠️ 毒药已使用，无法再次使用！")

async def handle_antidote_skill(user_id: int, group_id: int, game: Dict, command_text: str, matcher: Matcher):
    """处理解药技能"""
    can_use, message = await game_state.can_use_skill(user_id, 'antidote', game)
    if not can_use:
        await matcher.finish(message)
    
    target_str = command_text[2:].strip()
    try:
        target = int(target_str)
    except:
        await matcher.finish("❌❌ 请输入正确的QQ号！")
    
    if target not in game['killed_tonight']:
        await matcher.finish("❌❌ 该玩家未被击杀！")
    
    game['saved_tonight'].add(target)
    await game_state.mark_skill_used(user_id, 'antidote', game)
    await matcher.send(f"💊💊 您使用解药拯救了 {target} 号玩家！\n⚠️ 解药已使用，无法再次使用！")

# ==================== 投票命令处理器 ====================
vote_cmd = on_command("谁是杀手 投", priority=10, block=True)

@vote_cmd.handle()
async def handle_vote(bot: Bot, event: GroupMessageEvent, matcher: Matcher, args: Message = CommandArg()):
    group_id = event.group_id
    user_id = event.user_id
    
    if group_id not in game_state.games:
        await matcher.finish("❌❌ 本群没有进行中的游戏！")
    
    game = game_state.games[group_id]
    
    if game['status'] != 'playing' or user_id not in game['alive_players']:
        await matcher.finish("❌❌ 您现在不能投票！")
    
    target_str = args.extract_plain_text().strip()
    try:
        target = int(target_str)
    except:
        await matcher.finish("❌❌ 请输入正确的QQ号！")
    
    if target not in game['alive_players']:
        await matcher.finish("❌❌ 目标玩家不存在或已出局！")
    
    if target == user_id:
        await matcher.finish("❌❌ 不能投票给自己！")
    
    # 记录投票
    if 'votes' not in game:
        game['votes'] = {}
    game['votes'][user_id] = target
    
    await matcher.send(f"✅ 玩家 {user_id} 投票给 {target} 号玩家")

# ==================== 帮助信息函数 ====================
async def show_help(matcher: Matcher):
    """显示帮助信息"""
    help_text = """
🎮🎮 谁是杀手游戏 - 完整帮助

👥👥 群内命令：
• /谁是杀手 加入游戏 - 加入游戏（需先加好友）
• /谁是杀手 开始游戏 - 手动开始游戏（需4人）
• /谁是杀手 退出游戏 - 退出当前游戏
• /谁是杀手 停止游戏 - 管理员强制结束
• /谁是杀手 游戏状态 - 查看当前状态
• /谁是杀手 投 QQ号 - 投票出局玩家

📩📩 私信技能命令：
• 杀手：/谁是杀手 刀 QQ号
• 预言家：/谁是杀手 预言 QQ号  
• 女巫：/谁是杀手 毒|救 QQ号
• 通用：/谁是杀手 身份 - 查看身份
• 通用：/谁是杀手 技能状态 - 查看技能
• 杀手：/谁是杀手 队友 - 查看队友信息（新增）

⚔⚔️ 游戏规则：
• 支持4-8人游戏，满8人自动开始
• 身份：杀手、预言家、女巫、平民
• 所有技能只能使用一次！
• 夜晚阶段：特殊身份行动
• 白天阶段：讨论和投票
• 杀手全灭→平民胜，杀手≥平民→杀手胜
• 游戏结束后公布所有身份并重置游戏
• 新增：两狼局杀手会知道队友信息
"""
    await matcher.finish(help_text)