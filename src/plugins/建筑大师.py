from nonebot import on_command, on_message
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    PrivateMessageEvent,
    MessageSegment,
)
from nonebot.plugin import PluginMetadata
from datetime import datetime
import random, asyncio

__plugin_meta__ = PluginMetadata(
    name="建筑大师",
    description="完整版：4人开局+好友校验+私信举报+单局榜",
    usage="""
/建筑大师 —— 帮助
/建筑大师 开始 —— 创建房间（至少4人）
/建筑大师 加入 —— 必须加Bot好友
群内：/建筑大师 举报 @某人
超管私信：引用消息后输入 /建筑大师 同意举报
""",
)

# ================= 配置 =================
SUPER_ADMIN = 3671199392
MIN_PLAYER = 4
MAX_PLAYER = 20
DRAW_TIME = 300
SHOW_TIME = 30

NO_SUBMIT = -3
REPORT = -10
INIT_SCORE = 20

THEMES = ["天空之城", "古代神庙", "赛博都市"]

games = {}
week_score = {}


def week():
    return f"{datetime.now().year}-{datetime.now().isocalendar().week}"


def init(uid):
    week_score.setdefault(week(), {})
    week_score[week()].setdefault(uid, INIT_SCORE)


def score(uid):
    init(uid)
    return week_score[week()][uid]


def add(uid, d):
    init(uid)
    week_score[week()][uid] += d


# ================= 主命令 =================
bm = on_command("建筑大师", priority=5, block=True)


@bm.handle()
async def main(bot: Bot, event: GroupMessageEvent):
    gid, uid = event.group_id, event.user_id
    args = event.get_plaintext().strip().split()
    sub = args[1] if len(args) > 1 else ""

    # ===== 帮助 =====
    if sub == "" or sub in ("帮助", "help"):
        await bm.finish(__plugin_meta__.usage)

    g = games.get(gid)

    # ===== 创建房间 =====
    if sub == "开始":
        if not g:
            games[gid] = {
                "theme": random.choice(THEMES),
                "owner": uid,
                "players": set(),
                "works": {},
                "votes": {},
                "reports": {},
                "started": False,
            }
            await bm.finish("✅ 房间已创建，至少 4 人才能开始")
        if g["started"]:
            await bm.finish("游戏已开始")
        if len(g["players"]) < MIN_PLAYER:
            await bm.finish(f"❌ 至少 {MIN_PLAYER} 人（当前 {len(g['players'])}）")
        g["started"] = True
        g["stage"] = "draw"
        await bm.send(gid, f"🎨 主题：{g['theme']}")
        asyncio.create_task(draw_end(bot, gid))
        return

    if not g or not g.get("started"):
        await bm.finish("没有进行中的游戏")

    # ===== 加入（含好友校验）=====
    if sub == "加入":
        if score(uid) <= 0:
            await bm.finish("本周信誉分不足")
        try:
            await bot.get_stranger_info(user_id=uid)
        except Exception:
            await bm.finish("❌ 请先加 Bot 好友才能加入")
        g["players"].add(uid)
        await bot.send_private_msg(uid, "✅ 已加入，请私聊发送作品")
        await bm.finish(f"✅ 加入成功({len(g['players'])}/{MAX_PLAYER})")

    # ===== 举报 =====
    if sub == "举报":
        ats = [s for s in event.get_message() if s.type == "at"]
        if not ats:
            await bm.finish("用法：/建筑大师 举报 @某人")
        tid = ats[0].data["qq"]
        g["reports"][uid] = {"target": tid, "msg_id": event.message_id}
        await bot.send_private_msg(
            SUPER_ADMIN,
            MessageSegment.reply(event.message_id) + f"举报：{uid} 举报 {tid}"
        )
        await bm.finish("举报已提交")

    await bm.finish("未知指令")


# ================= 超管同意 =================
@bm.handle()
async def admin(bot: Bot, event: PrivateMessageEvent):
    if event.user_id != SUPER_ADMIN:
        return
    if event.get_plaintext().strip() != "建筑大师 同意举报":
        return
    for g in games.values():
        for r in g.get("reports", {}).values():
            if r.get("done"):
                continue
            add(r["target"], REPORT)
            r["done"] = True
            await bot.send_private_msg(r["reporter"], "✅ 举报成立")


# ================= 私聊交图 =================
@on_message().handle()
async def draw(event: PrivateMessageEvent):
    uid = event.user_id
    for seg in event.get_message():
        if seg.type == "image":
            for g in games.values():
                if uid in g.get("players", set()) and g.get("stage") == "draw":
                    g["works"][uid] = seg


# ================= 绘画结束 =================
async def draw_end(bot, gid):
    await asyncio.sleep(DRAW_TIME)
    g = games[gid]
    g["stage"] = "show"
    for uid in g["players"]:
        if uid not in g["works"]:
            add(uid, NO_SUBMIT)
    asyncio.create_task(show(bot, gid))


# ================= 轮播 =================
async def show(bot, gid):
    g = games[gid]
    for uid in g["players"]:
        if uid in g["works"]:
            await bot.send_group_msg(
                gid,
                message=MessageSegment.image(g["works"][uid].data["url"])
            )
            await asyncio.sleep(SHOW_TIME)
    g["stage"] = "vote"
    await bot.send_group_msg(gid, "🎯 投票开始，输入 0–5")


# ================= 投票 =================
@on_message().handle()
async def vote(event: GroupMessageEvent):
    g = games.get(event.group_id)
    if not g or g.get("stage") != "vote":
        return
    if event.raw_message in map(str, range(6)):
        g["votes"][event.user_id] = int(event.raw_message)


# ================= 结算 =================
@bm.handle()
async def rank(bot: Bot, event: GroupMessageEvent):
    g = games.get(event.group_id)
    if not g:
        return
    r = sorted(g["votes"].items(), key=lambda x: x[1], reverse=True)
    msg = ["🏆 本局排行"]
    for i, (u, s) in enumerate(r, 1):
        msg.append(f"{i}. {MessageSegment.at(u)} —— {s} 分")
    await bm.send(event.group_id, "\n".join(msg))
