from nonebot import on_keyword
from nonebot.adapters.onebot.v11 import Message
help = on_keyword({"/help","/帮助"})
@help.handle()
async def _():
   await help.finish("帮助列表:\n/签到     进行签到\n/运势   查看今日运势\n/AI   查看AI菜单\n/系统状态   查看系统状态")
