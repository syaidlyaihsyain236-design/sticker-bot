import os
import io
import re
import json
import logging
from pathlib import Path

from telegram import Update, InputSticker
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from telegram.error import TelegramError

from PIL import Image, ImageDraw, ImageFont, ImageOps
import arabic_reshaper
from bidi.algorithm import get_display

# =========================
# إعدادات عامة
# =========================

TOKEN = os.environ.get("TOKEN")
if not TOKEN:
    raise RuntimeError("أضف TOKEN في Environment Variables")

DATA_DIR = Path("bot_data")
DATA_DIR.mkdir(exist_ok=True)

PACKS_FILE = DATA_DIR / "packs.json"
PREFS_FILE = DATA_DIR / "preferences.json"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_json(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

PACKS = load_json(PACKS_FILE)
PREFERENCES = load_json(PREFS_FILE)

def user_key(update):
    return str(update.effective_user.id)

def template_path(uid):
    return DATA_DIR / f"template_{uid}.png"

# =========================
# النص العربي والخطوط
# =========================

def shape_arabic(text):
    try:
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text

def get_font(size):
    candidates = [
        os.environ.get("ARABIC_FONT", ""),
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "arial.ttf",
    ]
    for path in candidates:
        if path and Path(path).is_file():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                pass
    return ImageFont.load_default()

# =========================
# فهم الألوان
# =========================

COLOR_NAMES = {
    "احمر": "#FF3030", "أحمر": "#FF3030", "red": "#FF3030",
    "ازرق": "#247BFF", "أزرق": "#247BFF", "blue": "#247BFF",
    "اخضر": "#16A765", "أخضر": "#16A765", "green": "#16A765",
    "اصفر": "#FFD928", "أصفر": "#FFD928", "yellow": "#FFD928",
    "اسود": "#171717", "أسود": "#171717", "black": "#171717",
    "ابيض": "#FFFFFF", "أبيض": "#FFFFFF", "white": "#FFFFFF",
    "بنفسجي": "#923CDB", "purple": "#923CDB",
    "وردي": "#FF75B8", "زهري": "#FF75B8", "pink": "#FF75B8",
    "برتقالي": "#FF8A24", "orange": "#FF8A24",
    "سماوي": "#35C9E8", "cyan": "#35C9E8",
    "فضي": "#C8CDD3", "silver": "#C8CDD3",
    "ذهبي": "#D9A62E", "gold": "#D9A62E",
    "نحاسي": "#B87333", "copper": "#B87333",
    "رمادي": "#888888", "gray": "#888888", "grey": "#888888",
    "بني": "#895129", "brown": "#895129",
    "كحلي": "#142B55", "navy": "#142B55",
    "فيروزي": "#35C9B5", "turquoise": "#35C9B5",
}

def parse_color(text):
    text = text.strip()
    match = re.search(r"#?([0-9a-fA-F]{6})", text)
    if match:
        value = match.group(1)
        return tuple(int(value[i:i+2], 16) for i in (0, 2, 4))

    normalized = text.lower().replace(" ", "")
    for name, hex_value in COLOR_NAMES.items():
        if name.lower().replace(" ", "") in normalized:
            return tuple(int(hex_value[i:i+2], 16) for i in (1, 3, 5))
    return None

# =========================
# حفظ إعدادات المستخدم
# =========================

def get_prefs(uid):
    return PREFERENCES.get(uid, {
        "text_color": "#FFFFFF",
        "outline_color": "#202020",
        "outline_width": 3,
        "font_size": 72,
        "effect": "normal",
        "target": "text",
        "last_text": "ملصق"
    })

def set_prefs(uid, prefs):
    PREFERENCES[uid] = prefs
    save_json(PREFS_FILE, PREFERENCES)

# =========================
# إنشاء ملصق WEBP
# =========================

def render_sticker(uid, text):
    path = template_path(uid)

    if path.exists():
        base = Image.open(path).convert("RGBA")
        base = ImageOps.fit(base, (512, 512), method=Image.Resampling.LANCZOS)
    else:
        base = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        draw = ImageDraw.Draw(base)
        draw.rounded_rectangle(
            (18, 145, 494, 367),
            radius=38,
            fill=(22, 83, 61, 255),
            outline=(210, 174, 98, 255),
            width=5
        )

    prefs = get_prefs(uid)
    draw = ImageDraw.Draw(base)

    text_color = parse_color(prefs["text_color"]) or (255, 255, 255)
    outline_color = parse_color(prefs["outline_color"]) or (25, 25, 25)
    font_size = int(prefs.get("font_size", 72))

    shaped = shape_arabic(text)
    font = get_font(font_size)

    # تصغير النص إذا تجاوز عرض الملصق
    while font_size > 18:
        bbox = draw.textbbox((0, 0), shaped, font=font, stroke_width=2)
        if bbox[2] - bbox[0] <= 460:
            break
        font_size -= 3
        font = get_font(font_size)

    # تأثير توهج بسيط اختياري
    if prefs.get("effect") == "neon":
        glow = tuple(min(255, int(c * 0.55 + 90)) for c in text_color)
        for width in (12, 8, 5):
            draw.text(
                (256, 256), shaped, font=font, anchor="mm",
                fill=(*glow, 90), stroke_width=width,
                stroke_fill=(*glow, 65)
            )

    draw.text(
        (256, 256), shaped, font=font, anchor="mm",
        fill=(*text_color, 255),
        stroke_width=int(prefs.get("outline_width", 3)),
        stroke_fill=(*outline_color, 255)
    )

    # تيليجرام يقبل WEBP ثابتاً حتى 512x512 وبحجم محدود
    for quality in (92, 85, 78, 70, 62, 55, 45):
        output = io.BytesIO()
        base.save(output, format="WEBP", quality=quality, method=6)
        if output.tell() <= 500 * 1024:
            return output.getvalue()

    raise ValueError("تعذر ضغط الملصق إلى الحجم المطلوب.")

# =========================
# إنشاء وإضافة حزمة ملصقات
# =========================

async def add_sticker_to_pack(bot, user, sticker_bytes):
    uid = str(user.id)
    me = await bot.get_me()

    if not me.username:
        raise RuntimeError("يجب أن يكون للبوت Username.")

    sticker_set = PACKS.get(uid)
    sticker_name = f"stickers_{uid}_by_{me.username.lower()}"[:64]

    sticker = InputSticker(
        sticker=io.BytesIO(sticker_bytes),
        emoji_list=["✨"],
        format="static"
    )

    if not sticker_set:
        await bot.create_new_sticker_set(
            user_id=user.id,
            name=sticker_name,
            title=f"ملصقات {user.first_name or 'My'}"[:64],
            stickers=[sticker],
            sticker_type="regular"
        )
        PACKS[uid] = {
            "name": sticker_name,
            "url": f"https://t.me/addstickers/{sticker_name}"
        }
        save_json(PACKS_FILE, PACKS)
    else:
        await bot.add_sticker_to_set(
            user_id=user.id,
            name=sticker_set["name"],
            sticker=sticker
        )

    return PACKS[uid]["url"]

# =========================
# أوامر البوت
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أهلاً بك في مصنع الملصقات 👑\n\n"
        "• أرسل صورة حتى أجعلها قالباً.\n"
        "• أرسل اسماً حتى أضعه على القالب.\n"
        "• اكتب: لون النص أحمر\n"
        "• اكتب: لون الإطار أزرق\n"
        "• اكتب: حجم الخط 80\n"
        "• اكتب: تأثير نيون أو تأثير عادي\n"
        "• اكتب: معاينة حتى أعيد آخر تصميم.\n"
        "• /pack لعرض حزمة ملصقاتك.\n"
        "• /reset لحذف القالب.\n\n"
        "تستطيع أيضاً كتابة كود لون مثل #12A4EF."
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = user_key(update)
    photo = await update.message.photo[-1].get_file()
    data = await photo.download_as_bytearray()

    try:
        image = Image.open(io.BytesIO(data)).convert("RGBA")
        image = ImageOps.fit(image, (512, 512), method=Image.Resampling.LANCZOS)
        image.save(template_path(uid), format="PNG")
        await update.message.reply_text(
            "تم حفظ الصورة كقالب ✅\n"
            "أرسل الاسم الذي تريد وضعه عليها."
        )
    except Exception:
        await update.message.reply_text("لم أستطع قراءة الصورة. جرّب صورة أخرى.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc or not (doc.mime_type or "").startswith("image/"):
        await update.message.reply_text("أرسل صورة بصيغة صورة، وليس ملفاً غير صوري.")
        return

    uid = user_key(update)
    file = await doc.get_file()
    data = await file.download_as_bytearray()

    try:
        image = Image.open(io.BytesIO(data)).convert("RGBA")
        image = ImageOps.fit(image, (512, 512), method=Image.Resampling.LANCZOS)
        image.save(template_path(uid), format="PNG")
        await update.message.reply_text("تم حفظ الصورة كقالب ✅ أرسل الاسم.")
    except Exception:
        await update.message.reply_text("تعذر فتح هذا الملف كصورة.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = user_key(update)
    raw = update.message.text.strip()
    low = raw.lower()
    prefs = get_prefs(uid)

    # تغيير لون النص
    if low.startswith(("لون النص", "لون الاسم", "text color")):
        color = parse_color(raw)
        if color is None:
            await update.message.reply_text("لم أتعرف على اللون. اكتب اسمه أو كوده مثل #12A4EF.")
            return
        match = re.search(r"#?[0-9a-fA-F]{6}", raw)
        if match:
            prefs["text_color"] = "#" + match.group(0).lstrip("#")
        else:
            for name, value in COLOR_NAMES.items():
                if name.lower() in low:
                    prefs["text_color"] = value
                    break
        set_prefs(uid, prefs)
        await update.message.reply_text("تم تغيير لون النص. أرسل اسماً أو اكتب: معاينة")
        return

    # تغيير لون الإطار
    if low.startswith(("لون الإطار", "لون الاطار", "outline color")):
        color = parse_color(raw)
        if color is None:
            await update.message.reply_text("اكتب لوناً معروفاً أو كود HEX مثل #12A4EF.")
            return
        match = re.search(r"#?[0-9a-fA-F]{6}", raw)
        if match:
            prefs["outline_color"] = "#" + match.group(0).lstrip("#")
        else:
            for name, value in COLOR_NAMES.items():
                if name.lower() in low:
                    prefs["outline_color"] = value
                    break
        set_prefs(uid, prefs)
        await update.message.reply_text("تم تغيير لون الإطار. أرسل اسماً أو اكتب: معاينة")
        return

    # حجم الخط
    if low.startswith(("حجم الخط", "حجم الاسم", "font size")):
        nums = re.findall(r"\d+", raw)
        if not nums or not 18 <= int(nums[-1]) <= 180:
            await update.message.reply_text("اختر حجماً بين 18 و180.")
            return
        prefs["font_size"] = int(nums[-1])
        set_prefs(uid, prefs)
        await update.message.reply_text("تم تغيير حجم الخط. أرسل اسماً أو اكتب: معاينة")
        return

    # تأثير
    if "تأثير نيون" in raw or "تاثير نيون" in raw or low == "neon":
        prefs["effect"] = "neon"
        set_prefs(uid, prefs)
        await update.message.reply_text("تم تفعيل النيون. أرسل اسماً أو اكتب: معاينة")
        return

    if "تأثير عادي" in raw or "تاثير عادي" in raw or low == "normal":
        prefs["effect"] = "normal"
        set_prefs(uid, prefs)
        await update.message.reply_text("تم إلغاء النيون.")
        return

    if low in ("معاينة", "preview"):
        raw = prefs.get("last_text", "ملصق")

    prefs["last_text"] = raw
    set_prefs(uid, prefs)

    try:
        sticker_bytes = render_sticker(uid, raw)
        await update.message.reply_sticker(
            sticker=io.BytesIO(sticker_bytes)
        )

        # إضافة تلقائية إلى حزمة المستخدم؛ إذا لم تنجح، يبقى الملصق صالحاً
        try:
            url = await add_sticker_to_pack(
                context.bot, update.effective_user, sticker_bytes
            )
            await update.message.reply_text(
                f"أُضيف الملصق إلى حزمة ملصقاتك ✅\n{url}"
            )
        except TelegramError as exc:
            log.warning("Sticker pack error: %s", exc)
            await update.message.reply_text(
                "الملصق جاهز ويمكن استخدامه، لكن تعذرت إضافته للحزمة.\n"
                "قد تكون الحزمة غير متاحة أو وصلَت إلى الحد المسموح."
            )
        except Exception as exc:
            log.exception("Pack creation error")
            await update.message.reply_text(
                f"الملصق جاهز، لكن إنشاء الحزمة تعذر: {str(exc)[:180]}"
            )

    except Exception as exc:
        log.exception("Sticker render error")
        await update.message.reply_text(f"تعذر إنشاء الملصق: {str(exc)[:180]}")

async def pack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = PACKS.get(user_key(update))
    if not data:
        await update.message.reply_text("لم تُنشأ حزمة بعد. أرسل اسماً أولاً.")
        return
    await update.message.reply_text(f"رابط حزمة ملصقاتك:\n{data['url']}")

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    path = template_path(user_key(update))
    if path.exists():
        path.unlink()
    await update.message.reply_text("حُذف قالبك. أرسل صورة جديدة.")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("pack", pack_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.IMAGE, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    log.info("Sticker bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
