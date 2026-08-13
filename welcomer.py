import discord
import os
import aiohttp
import io
import logging
from database import db

# Safe import for Pillow
try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

logger = logging.getLogger(__name__)

# Predefined templates matching user request
# They differ only in accent color, background color (gradient fallback), and font.
TEMPLATES = {
    "dark_elegance": {
        "accent_color": "#D4AF37",  # Gold
        "bg_color1": "#1a1a2e",
        "bg_color2": "#16213e",
        "font_name": "Montserrat-Bold.ttf"
    },
    "minecraft": {
        "accent_color": "#55FF55",  # Green
        "bg_color1": "#3A3A3A",
        "bg_color2": "#282828",
        "font_name": "Montserrat-Bold.ttf"
    },
    "corporate_blue": {
        "accent_color": "#007BFF",  # Blue
        "bg_color1": "#001F3F",
        "bg_color2": "#003366",
        "font_name": "Montserrat-Bold.ttf"
    },
    "fantasy_purple": {
        "accent_color": "#9B59B6",  # Purple
        "bg_color1": "#2C1B4D",
        "bg_color2": "#1C1132",
        "font_name": "Montserrat-Bold.ttf"
    }
}

async def fetch_image(url: str):
    if not url:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as response:
                if response.status == 200:
                    data = await response.read()
                    return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception as e:
        logger.warning(f"Failed to fetch image from {url}: {e}")
    return None

def hex_to_rgb(hex_code: str, alpha: int = 255):
    hex_code = hex_code.lstrip('#')
    if len(hex_code) == 3:
        hex_code = "".join(c+c for c in hex_code)
    try:
        r, g, b = tuple(int(hex_code[i:i+2], 16) for i in (0, 2, 4))
        return (r, g, b, alpha)
    except:
        return (255, 255, 255, alpha)

def create_gradient(width, height, color1, color2):
    base = Image.new('RGBA', (width, height), color1)
    top = Image.new('RGBA', (width, height), color2)
    mask = Image.new('L', (width, height))
    mask_data = []
    for y in range(height):
        mask_data.extend([int(255 * (y / height))] * width)
    mask.putdata(mask_data)
    base.paste(top, (0, 0), mask)
    return base

async def generate_welcome_card(member: discord.Member, config: dict) -> io.BytesIO:
    width, height = 800, 300

    template_name = config.get("welcome_template", "dark_elegance")
    template = TEMPLATES.get(template_name, TEMPLATES["dark_elegance"])

    bg_color1 = config.get("bg_color1") or template["bg_color1"]
    bg_color2 = config.get("bg_color2") or template["bg_color2"]
    accent_color = config.get("accent_color") or template["accent_color"]

    bg_url = config.get("background_url")
    bg_image = await fetch_image(bg_url)

    if bg_image:
        bg_image = bg_image.resize((width, height), Image.Resampling.LANCZOS)
    else:
        bg_image = create_gradient(width, height, hex_to_rgb(bg_color1), hex_to_rgb(bg_color2))

    # Dark overlay for readability
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 150))
    final_image = Image.alpha_composite(bg_image, overlay)
    draw = ImageDraw.Draw(final_image)

    # Load fonts
    font_path = f"asset/fonts/{template['font_name']}"
    if not os.path.exists(font_path):
        font_path = "asset/fonts/Montserrat-Bold.ttf"

    try:
        title_font = ImageFont.truetype(font_path, 42)
        subtitle_font = ImageFont.truetype(font_path, 24)
        badge_font = ImageFont.truetype(font_path, 20)
    except Exception:
        title_font = ImageFont.load_default()
        subtitle_font = ImageFont.load_default()
        badge_font = ImageFont.load_default()

    # Draw title
    title_text = f"Welcome, {member.name}"
    # Use newer getbbox method
    title_bbox = draw.textbbox((0, 0), title_text, font=title_font)
    title_w = title_bbox[2] - title_bbox[0]
    draw.text(((width - title_w) / 2, 170), title_text, font=title_font, fill=(255, 255, 255, 255))

    # Draw subtitle
    subtitle_text = "Benvenuto su Brotherhood Origins"
    subtitle_bbox = draw.textbbox((0, 0), subtitle_text, font=subtitle_font)
    subtitle_w = subtitle_bbox[2] - subtitle_bbox[0]
    draw.text(((width - subtitle_w) / 2, 220), subtitle_text, font=subtitle_font, fill=hex_to_rgb("#B0B0B0"))

    # Draw badge (member count)
    badge_text = f"Membro #{member.guild.member_count}"
    badge_bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    badge_w = badge_bbox[2] - badge_bbox[0]
    badge_h = badge_bbox[3] - badge_bbox[1]

    badge_x = (width - badge_w - 40) / 2
    badge_y = 260
    draw.rounded_rectangle([badge_x, badge_y, badge_x + badge_w + 40, badge_y + badge_h + 10], radius=15, fill=(0, 0, 0, 180))
    draw.text((badge_x + 20, badge_y + 3), badge_text, font=badge_font, fill=(200, 200, 200, 255))

    # Avatar setup
    avatar_size = 120
    avatar_y = 30
    avatar_x = (width - avatar_size) // 2

    avatar_data = await member.display_avatar.replace(size=128, format="png").read()
    avatar_img = Image.open(io.BytesIO(avatar_data)).convert("RGBA").resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)

    # Circular mask for avatar
    mask = Image.new("L", (avatar_size, avatar_size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)

    # Draw double border (white 3px + glow accent color)
    glow_size = avatar_size + 16
    glow_img = Image.new("RGBA", (glow_size, glow_size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_img)
    glow_draw.ellipse((0, 0, glow_size, glow_size), fill=hex_to_rgb(accent_color, 255))

    # Blur for glow effect
    glow_img = glow_img.filter(ImageFilter.GaussianBlur(4))

    white_border_size = avatar_size + 6
    white_img = Image.new("RGBA", (white_border_size, white_border_size), (0, 0, 0, 0))
    white_draw = ImageDraw.Draw(white_img)
    white_draw.ellipse((0, 0, white_border_size, white_border_size), fill=(255, 255, 255, 255))

    final_image.paste(glow_img, (avatar_x - 8, avatar_y - 8), glow_img)
    final_image.paste(white_img, (avatar_x - 3, avatar_y - 3), white_img)

    avatar_with_mask = Image.new("RGBA", avatar_img.size)
    avatar_with_mask.paste(avatar_img, (0, 0), mask)
    final_image.paste(avatar_with_mask, (avatar_x, avatar_y), avatar_with_mask)

    # Watermark logo
    logo_url = config.get("logo_url")
    if logo_url:
        logo_img = await fetch_image(logo_url)
        if logo_img:
            logo_img = logo_img.resize((50, 50), Image.Resampling.LANCZOS)
            # Apply opacity (8-20%)
            alpha = logo_img.split()[3]
            alpha = alpha.point(lambda p: p * 0.15)
            logo_img.putalpha(alpha)
            final_image.paste(logo_img, (width - 60, height - 60), logo_img)

    buffer = io.BytesIO()
    final_image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


async def on_member_join(member: discord.Member):
    try:
        guild_id = member.guild.id
        welcome_channel_id = await db.get_config(guild_id, "welcome_channel")
        if not welcome_channel_id:
            return

        try:
            channel = member.guild.get_channel(int(welcome_channel_id))
            if not channel:
                return
        except ValueError:
            return

        use_card = (await db.get_config(guild_id, "welcome_use_card", "false")).lower() == "true"
        ping_role_id = await db.get_config(guild_id, "welcome_ping_role")
        ping_user_id = await db.get_config(guild_id, "welcome_ping_user")

        content_parts = []
        if ping_role_id:
            content_parts.append(f"<@&{ping_role_id}>")
        if ping_user_id:
            content_parts.append(f"<@{ping_user_id}>")

        ping_text = " ".join(content_parts)
        if ping_text:
            ping_text += "\n"

        welcome_text = f"Benvenuto {member.mention} su 𝘽𝙍𝙊𝙏𝙃𝙀𝙍𝙃𝙊𝙊𝘿 𝙊𝙍𝙄𝙂𝙄𝙉𝙎! Sei il {member.guild.member_count}° membro! Ricordati di leggere il regolamento."
        content = ping_text + welcome_text

        allowed_mentions = discord.AllowedMentions(users=True, roles=True, everyone=False)

        if use_card and PIL_AVAILABLE:
            config = {
                "welcome_template": await db.get_config(guild_id, "welcome_template", "dark_elegance"),
                "bg_color1": await db.get_config(guild_id, "bg_color1"),
                "bg_color2": await db.get_config(guild_id, "bg_color2"),
                "accent_color": await db.get_config(guild_id, "accent_color"),
                "background_url": await db.get_config(guild_id, "background_url"),
                "logo_url": await db.get_config(guild_id, "logo_url")
            }
            buffer = await generate_welcome_card(member, config)
            file = discord.File(fp=buffer, filename="welcome.png")
            await channel.send(content=content, file=file, allowed_mentions=allowed_mentions)
        else:
            embed = discord.Embed(
                title=f"Welcome, {member.name}",
                description="Benvenuto su Brotherhood Origins!",
                color=discord.Color.gold()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"Membro #{member.guild.member_count}")
            await channel.send(content=content, embed=embed, allowed_mentions=allowed_mentions)
    except Exception as e:
        logger.error(f"Error in welcome module: {e}")

def setup_welcomer(bot: discord.Client):
    bot.event(on_member_join)
