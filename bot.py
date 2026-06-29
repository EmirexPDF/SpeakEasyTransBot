import os
import io
import logging
import asyncio
from aiohttp import web
from googletrans import Translator
import speech_recognition as sr
from pydub import AudioSegment
from telegram import Update, InlineQueryResultArticle, InputMessageContent
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    InlineQueryHandler,
    ContextTypes,
    filters,
)

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))

# Initialize Engines
translator = Translator()
recognizer = sr.Recognizer()

# --- TRANSLATION CORE OPERATIONS ---

def quick_translate(text: str, target_lang: str = 'en'):
    try:
        result = translator.translate(text, dest=target_lang)
        return result.origin, result.src, result.text
    except Exception as e:
        logger.error(f"Translation failure: {e}")
        return text, "unknown", "Error executing translation pipeline."

# --- TELEGRAM HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌐 **Welcome to @SpeakEasyTransBot!** 🌐\n\n"
        "I can seamlessly process and translate your world:\n"
        "• Send or forward **Text** directly (Auto-detects source)\n"
        "• Send a **Voice Message** for instant voice-to-translated-text conversion\n"
        "• Upload a **.txt document** to translate entire files\n"
        "• Type `@SpeakEasyTransBot <text>` in any chat for **Inline Mode**!\n\n"
        "Default target language is English (`en`). Use /lang <target_code> to change it."
    )

async def change_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        target = context.args[0].lower()
        context.user_data['target_lang'] = target
        await update.message.reply_text(f"🎯 Target language successfully updated to: `{target}`")
    else:
        await update.message.reply_text("Please provide a language code, e.g., `/lang es`, `/lang fr`, `/lang de`.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = context.user_data.get('target_lang', 'en')
    original_text = update.message.text
    
    _, src, translated = quick_translate(original_text, target)
    await update.message.reply_text(
        f"🌐 *Detected Source:* `{src.upper()}` ➡️ `{target.upper()}`\n\n{translated}",
        parse_mode="Markdown"
    )

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = context.user_data.get('target_lang', 'en')
    await update.message.reply_text("🎙️ Processing voice array... decoding audio frequencies.")
    
    # Download audio stream
    voice_file = await context.bot.get_file(update.message.voice.file_id)
    ogg_buffer = io.BytesIO()
    await voice_file.download_to_memory(out=ogg_buffer)
    ogg_buffer.seek(0)
    
    try:
        # Convert OGG/Opus to WAV format using pydub
        sound = AudioSegment.from_file(ogg_buffer, codec="opus")
        wav_io = io.BytesIO()
        sound.export(wav_io, format="wav")
        wav_io.seek(0)
        
        with sr.AudioFile(wav_io) as source:
            audio_data = recognizer.record(source)
            # Perform speech recognition via Google speech fallback
            recognized_text = recognizer.recognize_google(audio_data)
            
        _, src, translated = quick_translate(recognized_text, target)
        await update.message.reply_text(
            f"🗣️ *Transcribed Text:* \"{recognized_text}\"\n\n"
            f"🔀 *Translated:* ({src.upper()} ➡️ {target.upper()})\n\n{translated}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Voice thread failed: {e}")
        await update.message.reply_text("❌ Could not interpret audio clearly or translate speech array.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = context.user_data.get('target_lang', 'en')
    doc = update.message.document
    
    if not doc.file_name.endswith('.txt'):
        await update.message.reply_text("⚠️ For documentation processing, please submit clean `.txt` documents.")
        return

    await update.message.reply_text("📄 Reading document layers...")
    doc_file = await context.bot.get_file(doc.file_id)
    text_io = io.BytesIO()
    await doc_file.download_to_memory(out=text_io)
    
    try:
        raw_text = text_io.getvalue().decode('utf-8')
        # Simple splitting block optimization for safe request chunk distributions
        paragraphs = raw_text.split('\n')
        translated_paragraphs = []
        
        for para in paragraphs:
            if para.strip():
                _, _, trans_para = quick_translate(para, target)
                translated_paragraphs.append(trans_para)
            else:
                translated_paragraphs.append("")
                
        output_text = "\n".join(translated_paragraphs)
        output_io = io.BytesIO(output_text.encode('utf-8'))
        output_io.name = f"translated_{target}_{doc.file_name}"
        
        await update.message.reply_document(document=output_io, caption=f"✅ Document translation fully processed to: `{target}`")
    except Exception as e:
        logger.error(f"Doc parsing dropped error: {e}")
        await update.message.reply_text("❌ Failed to unpack or process your text document parameters cleanly.")

async def handle_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query
    if not query:
        return

    # Automatically converts to English inline unless customized inline syntax parameters are set
    orig, src, translated = quick_translate(query, 'en')
    
    results = [
        InlineQueryResultArticle(
            id=str(hash(query)),
            title=f"Translate to EN ({src.upper()} ➡️ EN)",
            description=translated,
            input_message_content=InputMessageContent(
                message_text=f"🌐 *Translated via SpeakEasy:* \n\n{translated}",
                parse_mode="Markdown"
            )
        )
    ]
    await update.inline_query.answer(results)

# --- ALIVE KEEPER ENDPOINT ---

async def health_check(request):
    return web.Response(text="SpeakEasyTransBot microservices active.")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()

# --- MAIN INVOCATION ENGINE ---

def main():
    if not TOKEN:
        logger.error("System configuration context missing assignment for TELEGRAM_BOT_TOKEN.")
        return

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("lang", change_language))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(InlineQueryHandler(handle_inline))

    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_web_server())

    logger.info("Polling initialization sequence executing for @SpeakEasyTransBot...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
