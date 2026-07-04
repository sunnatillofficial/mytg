"""
Telegram AI Auto-Reply Bot
--------------------------
Bu bot FAQAT siz belgilagan guruh(lar)dagi xabarlarga
Groq (Llama AI) yordamida avtomatik javob beradi.

Ishga tushirishdan oldin .env faylini to'ldiring
(TELEGRAM_BOT_TOKEN, GROQ_API_KEY, ALLOWED_CHAT_IDS).
"""

import os
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
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
# BOT FAQAT SHU GURUH(LAR)DA JAVOB BERADI
# .env faylida ALLOWED_CHAT_IDS ga guruh ID(lar)ini yozing.
# Bir nechta guruh bo'lsa vergul bilan ajrating: -1001234567890,-1009876543210
# Guruh ID sini topish uchun pastdagi /chatid komandasidan foydalaning.
# ------------------------------------------------------------------
ALLOWED_CHAT_IDS = {
    int(cid.strip())
    for cid in os.getenv("ALLOWED_CHAT_IDS", "").split(",")
    if cid.strip()
}

# ------------------------------------------------------------------
# SIZNING SHAXSINGIZNI TASVIRLAB BERUVCHI "SYSTEM PROMPT"
# ------------------------------------------------------------------
SYSTEM_PROMPT = """
Sen Sunnatillo o'rniga Telegram guruhidagi xabarlarga javob berayapsan.
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


async def chatid_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Joriy chat ID sini ko'rsatadi - guruh ID sini topish uchun ishlatiladi."""
    chat = update.effective_chat
    await update.message.reply_text(
        f"Ushbu chat ID: `{chat.id}`\nTuri: {chat.type}",
        parse_mode="Markdown",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    logger.info(f"Xabar keldi. Chat ID: {chat_id}, Ruxsat etilganlar: {ALLOWED_CHAT_IDS}")

    # Faqat ruxsat berilgan guruh(lar)da javob beradi
    if chat_id not in ALLOWED_CHAT_IDS:
        logger.info(f"Chat ID {chat_id} ruxsat etilganlar ro'yxatida yo'q, o'tkazib yuborildi.")
        return

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

    if not ALLOWED_CHAT_IDS:
        logger.warning(
            "ALLOWED_CHAT_IDS bo'sh! Bot hech qanday guruhda javob bermaydi. "
            "Guruh ID sini /chatid komandasi bilan toping va .env ga qo'shing."
        )

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Guruh ID sini topish uchun yordamchi komanda (istalgan joyda ishlaydi)
    app.add_handler(CommandHandler("chatid", chatid_command))

    # Guruh va superguruh xabarlariga javob beradi (faqat ALLOWED_CHAT_IDS ichidagilarga)
    app.add_handler(
        MessageHandler(
            filters.TEXT
            & (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP)
            & ~filters.COMMAND,
            handle_message,
        )
    )

    logger.info("Bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()
