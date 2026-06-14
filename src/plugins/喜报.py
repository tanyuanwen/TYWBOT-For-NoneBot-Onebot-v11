import nonebot
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, Message, MessageSegment
from nonebot.params import CommandArg
from PIL import Image, ImageDraw, ImageFont
import os
import textwrap

# 获取插件所在目录
plugin_dir = os.path.dirname(os.path.abspath(__file__))
background_path = os.path.join(plugin_dir, "喜报.png")

# 注册命令处理器
xibao = on_command("喜报", priority=10, block=True)

@xibao.handle()
async def handle_xibao(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    # 获取用户输入的文字
    text = args.extract_plain_text().strip()
    
    if not text:
        await xibao.finish("请输入要生成喜报的内容，例如：/喜报 恭喜XXX获得一等奖！")
    
    try:
        # 生成喜报图片
        image_path = await generate_xibao_image(text)
        
        # 发送图片
        await xibao.finish(MessageSegment.image(f"file:///{image_path}"))
        
    except Exception as e:
        print(f"生成喜报失败：{str(e)}")

def draw_text_with_border(draw, position, text, font, text_color, border_color, border_width):
    """绘制带边框的文字[6,8](@ref)
    
    Args:
        draw: ImageDraw对象
        position: 文字位置 (x, y)
        text: 要绘制的文字
        font: 字体对象
        text_color: 文字颜色 (RGB元组)
        border_color: 边框颜色 (RGB元组)
        border_width: 边框宽度
    """
    x, y = position
    
    # 先绘制边框（在各个方向上偏移绘制文字）[6](@ref)
    for dx in range(-border_width, border_width + 1):
        for dy in range(-border_width, border_width + 1):
            if dx != 0 or dy != 0:  # 不绘制中心位置
                draw.text((x + dx, y + dy), text, font=font, fill=border_color)
    
    # 最后在中心位置绘制主文字[6](@ref)
    draw.text((x, y), text, font=font, fill=text_color)

async def generate_xibao_image(text: str) -> str:
    """生成喜报图片"""
    
    # 检查背景图片是否存在
    if not os.path.exists(background_path):
        # 如果没有背景图片，创建一个默认的红色背景
        img_width, img_height = 800, 400
        img = Image.new('RGB', (img_width, img_height), color=(200, 30, 30))
        draw = ImageDraw.Draw(img)
        
        # 添加默认标题
        title_font_size = 60
        try:
            title_font = ImageFont.truetype("simhei.ttf", title_font_size)
        except:
            title_font = ImageFont.load_default()
        
        # 绘制标题（带黄色边框的红色文字）
        title = "喜  报"
        title_bbox = draw.textbbox((0, 0), title, font=title_font)
        title_width = title_bbox[2] - title_bbox[0]
        title_height = title_bbox[3] - title_bbox[1]
        title_x = (img_width - title_width) // 2
        title_y = 50
        
        # 使用带边框的文字绘制函数
        draw_text_with_border(draw, (title_x, title_y), title, title_font, 
                             text_color=(255, 0, 0),     # 红色文字
                             border_color=(255, 255, 0), # 黄色边框
                             border_width=2)             # 边框宽度
        
    else:
        # 加载背景图片
        img = Image.open(background_path)
        img = img.convert('RGB')
    
    draw = ImageDraw.Draw(img)
    img_width, img_height = img.size
    
    # 文字自适应大小计算
    max_font_size = 100
    min_font_size = 20
    max_text_width = img_width * 0.8  # 文字最大宽度为图片宽度的80%
    max_text_height = img_height * 0.6  # 文字最大高度为图片高度的60%
    
    # 动态调整字体大小
    font_size = max_font_size
    font_path = "simhei.ttf"  # 使用黑体，可根据需要修改
    
    # 尝试不同的字体大小，找到最适合的
    for test_size in range(max_font_size, min_font_size, -5):
        try:
            font = ImageFont.truetype(font_path, test_size)
        except:
            font = ImageFont.load_default()
        
        # 计算文字包围框
        avg_char_width = test_size * 0.6  # 估算字符平均宽度
        chars_per_line = int(max_text_width / avg_char_width)
        wrapped_text = textwrap.fill(text, width=chars_per_line)
        
        # 计算多行文字高度
        lines = wrapped_text.split('\n')
        total_height = 0
        max_line_width = 0
        
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_width = bbox[2] - bbox[0]
            line_height = bbox[3] - bbox[1]
            total_height += line_height
            max_line_width = max(max_line_width, line_width)
        
        # 检查是否适合
        if max_line_width <= max_text_width and total_height <= max_text_height:
            font_size = test_size
            break
    else:
        font_size = min_font_size
        try:
            font = ImageFont.truetype(font_path, font_size)
        except:
            font = ImageFont.load_default()
    
    # 最终计算文字位置
    wrapped_text = textwrap.fill(text, width=int(max_text_width / (font_size * 0.6)))
    lines = wrapped_text.split('\n')
    
    # 计算总高度
    total_height = 0
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_height = bbox[3] - bbox[1]
        line_heights.append(line_height)
        total_height += line_height
    
    # 垂直居中绘制文字
    y = (img_height - total_height) // 2
    
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        line_width = bbox[2] - bbox[0]
        x = (img_width - line_width) // 2  # 水平居中
        
        # 绘制带黄色边框的红色文字
        draw_text_with_border(draw, (x, y), line, font,
                             text_color=(255, 0, 0),      # 红色文字
                             border_color=(255, 255, 0), # 黄色边框
                             border_width=2)             # 边框宽度
        
        y += line_heights[i]
    
    # 保存图片
    output_path = os.path.join(f"{plugin_dir}\喜悲报", f"喜报_{hash(text) % 10000}.png")
    img.save(output_path, quality=95)
    
    return output_path