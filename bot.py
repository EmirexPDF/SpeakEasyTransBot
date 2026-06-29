import os
import io
import logging
from googletrans import Translator
import speech_recognition as sr
from pydub import AudioSegment
from telegram import Update, InlineQueryResultArticle, InputMessageContent
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    InlineQueryHandler,
    ContextTypes,
    filters,
)

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Initialize Engines
translator = Translator()
recognizer = sr.Recognizer()

# --- TRANSLATION CORE ENGINE ---

def quick_translate(text: str, target_lang: str = 'en'):
    try:
        result = translator.translate(text, dest=target_lang)
        return result.origin, result.src, result.text
    except Exception as e:
        logger.error(f"Translation pipeline error: {e}")
        return text, "unknown", "Error executing translation pipeline matrix."

# --- TELEGRAM BOT EVENT HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎙️ **Welcome to @SpeakEasyTransBot on Railway!** 🎙️\n\n"
        "Send me any text, voice notes, or `.txt` documents to process:\n"
        "• **Text:** Simply send text to auto-detect and translate.\n"
        "• **Voice Messages:** Convert audio to translated text automatically.\n"
        "• **Documents:** Upload raw `.txt` files for instant processing.\n"
        "• **Inline Mode:** Type `@SpeakEasyTransBot <text>` in any individual or group chat!\n\n"
        "Default translation target language: English (`en`). Change it anytime using: `/lang <language_code>`"
    )

async def change_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        target = context.args[0].lower()
        context.user_data['target_lang'] = target
        await update.message.reply_text(f"🎯 Target translation language set to: `{target}`")
    else:
        await update.message.reply_text("Please specify a code format. Example: `/lang es`, `/lang fr`, `/lang ar`")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = context.user_data.get('target_lang', 'en')
    original_text = update.message.text
    
    _, src, translated = quick_translate(original_text, target)
    await update.message.reply_text(
        f"🌐 *Language Detected:* `{src.upper()}` ➡️ `{target.upper()}`\n\n{translated}",
        parse_mode="Markdown"
    )

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = context.user_data.get('target_lang', 'en')
    await update.message.reply_text("🎙️ Unpacking speech frequencies... decoding audio stream.")
    
    # Extract file array via Telegram servers
    voice_file = await context.bot.get_file(update.message.voice.file_id)
    ogg_buffer = io.BytesIO()
    await voice_file.download_to_memory(out=ogg_buffer)
    ogg_buffer.seek(0)
    
    try:
        # Convert OGG into standard structural audio WAV vectors
        sound = AudioSegment.from_file(ogg_buffer, codec="opus")
        wav_io = io.BytesIO()
        sound.export(wav_io, format="wav")
        wav_io.seek(0)
        
        with sr.AudioFile(wav_io) as source:
            audio_data = recognizer.record(source)
            recognized_text = recognizer.recognize_google(audio_data)
            
        _, src, translated = quick_translate(recognized_text, target)
        await update.message.reply_text(
            f"🗣️ *Transcribed Audio:* \"{recognized_text}\"\n\n"
            f"🔀 *Translated:* ({src.upper()} ➡️ {target.upper()})\n\n{translated}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Voice processor crashed: {e}")
        await update.message.reply_text("❌ Failed to transcribe voice message. Ensure audio path clarity.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = context.user_data.get('target_lang', 'en')
    doc = update.message.document
    
    if not doc.file_name.endswith('.txt'):
        await update.message.reply_text("⚠️ Please send standard `.txt` file structures for translation.")
        return

    await update.message.reply_text("📄 Parsing text document matrices...")
    doc_file = await context.bot.get_file(doc.file_id)
    text_io = io.BytesIO()
    await doc_file.download_to_memory(out=text_io)
    
    try:
        raw_text = text_io.getvalue().decode('utf-8')
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
        
        await update.message.reply_document(document=output_io, caption=f"✅ Finished document translation down to: `{target}`")
    except Exception as e:
        logger.error(f"Document processing failed: {e}")
        await update.message.reply_text("❌ System runtime failed to clear file parsing queues.")

async def handle_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query
    if not query:
        return

    _, src, translated = quick_translate(query, 'en')
    
    results = [
        InlineQueryResultArticle(
            id=str(hash(query)),
            title=f"Translate text to EN ({src.upper()} ➡️ EN)",
            description=translated,
            input_message_content=InputMessageContent(
                message_text=f"🌐 *Translated Engine Output:* \n\n{translated}",
                parse_mode="Markdown"
            )
        )
    ]
    await update.inline_query.answer(results)

# --- BOOT ENGINE ---

def main():
    if not TOKEN:
        logger.error("Missing critical configuration variable assignment for TELEGRAM_BOT_TOKEN.")
        return

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("lang", change_language))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(InlineQueryHandler(handle_inline))

    logger.info("Starting background execution polling for @SpeakEasyTransBot on Railway...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
