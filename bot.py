"""
Telegram AI Auto-Reply Bot
--------------------------
Bu bot shaxsiy chatlarga kelgan xabarlarga sizning o'rningizda
Groq (Llama AI) yordamida avtomatik javob beradi.

Ishga tushirishdan oldin .env faylini to'ldiring (bot_token va api_key).
"""

import os
import logging
from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    ContextTypes,
    filters,
)
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ------------------------------------------------------------------
# SIZNING SHAXSINGIZNI TASVIRLAB BERUVCHI "SYSTEM PROMPT"
# Buni o'zingizga moslab o'zgartiring: ismingiz, uslubingiz, kayfiyatingiz va h.k.
# ------------------------------------------------------------------
SYSTEM_PROMPT = """
Sen Sunnatillo o'rniga Telegram orqali xabarlarga javob berayapsan.
Uslubing: samimiy, qisqa va do'stona. O'zbek tilida, kundalik so'zlashuv uslubida yoz.
Agar savol muhim yoki shaxsiy bo'lsa (pul, uchrashuv, muhim qaror), javob berma va
buning o'rniga: "Hozir band ekanman, tez orada o'zim javob beraman" kabi neytral javob yoz.
Javoblaring qisqa bo'lsin (1-3 gap), haddan tashqari rasmiy bo'lma.
"""

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

client = Groq(api_key=GROQ_API_KEY)

# Har bir chat uchun oxirgi bir nechta xabarni saqlab turamiz (soddalashtirilgan xotira)
chat_histories: dict[int, list[dict]] = {}
MAX_HISTORY = 10


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_message = update.message.text

    if not user_message:
        return

    history = chat_histories.setdefault(chat_id, [])
    history.append({"role": "user", "content": user_message})
    history[:] = history[-MAX_HISTORY:]

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + history,
            max_tokens=300,
        )
        reply_text = response.choices[0].message.content
    except Exception as e:
        logger.error(f"AI javob berishda xatolik: {e}")
        reply_text = "Kechirasiz, hozir javob bera olmayapman. Birozdan keyin urinib ko'raman."

    history.append({"role": "assistant", "content": reply_text})

    await update.message.reply_text(reply_text)


def main() -> None:
    if not TELEGRAM_BOT_TOKEN or not GROQ_API_KEY:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN yoki GROQ_API_KEY topilmadi. .env faylini tekshiring."
        )

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Faqat shaxsiy chatlardagi matnli xabarlarga javob beradi (guruh/kanal emas)
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND,
            handle_message,
        )
    )

    logger.info("Bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()
