import os, io, math
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

TOKEN = TOKEN = os.environ.get("TOKEN")
USER_STYLE = {}

def fix_ar(text):
    try: return get_display(arabic_reshaper.reshape(text))
    except: return text

def font(size):
    try: return ImageFont.truetype("arial.ttf", size)
    except: return ImageFont.load_default()

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text
    clean = raw.replace("نار","").replace("يتحرك","").replace("ذهبي","").replace("نيون","").strip() or "باقر"
    clean = fix_ar(clean)
    img = USER_STYLE.get(update.effective_user.id)
    if img: template = img.copy()
    else:
        template = Image.new('RGBA', (512,512), (0,0,0,0))
        d = ImageDraw.Draw(template)
        d.rounded_rectangle([20,130,492,380], radius=35, fill=(20,20,20,255), outline=(255,255,255,255), width=3)
        d.text((256,180), "👑", font=font(40), fill=(255,215,0,255), anchor="mm")
    d = ImageDraw.Draw(template)
    d.text((256,280), clean, font=font(70), fill=(255,255,255,255), anchor="mm")
    bio = io.BytesIO(); bio.name="sticker.webp"; template.save(bio,"WEBP"); bio.seek(0)
    await update.message.reply_sticker(bio)

async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.photo[-1].get_file()
    data = await file.download_as_bytearray()
    img = Image.open(io.BytesIO(data)).convert("RGBA").resize((512,512))
    USER_STYLE[update.effective_user.id] = img
    await update.message.reply_text("تم حفظ الستايل ✅ دزلي اسم")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("البوت شغال 👑 دز صورة ملصق ثم اسم")

app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.PHOTO, on_photo))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
app.run_polling()
