from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageSegment
import httpx
# 定义命令
ecyt = on_command('二次元图')
@ecyt.handle()
async def main():
   # 获取随机图片URL
   msg = await get_data()
   # 发送图片给用户
   await ecyt.finish(MessageSegment.image(msg))
async def get_data():
   url = 'https://api.sevin.cn/api/ecy.php'
   async with httpx.AsyncClient() as client:
       resp = await client.get(url)
   data = resp.text.strip()
   return data
