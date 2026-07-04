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
from datetime import datetime, timedelta, timezone
from telegram import Update, ChatPermissions
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


# Har bir foydalanuvchi necha marta ban olganini saqlab turamiz: {(chat_id, user_id): son}
# DIQQAT: bu xotira RAM'da saqlanadi, bot qayta ishga tushsa (redeploy/restart) nolga tushadi.
ban_counts: dict[tuple[int, int], int] = {}


async def chatid_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Joriy chat ID sini ko'rsatadi - guruh ID sini topish uchun ishlatiladi."""
    chat = update.effective_chat
    await update.message.reply_text(
        f"Ushbu chat ID: `{chat.id}`\nTuri: {chat.type}",
        parse_mode="Markdown",
    )


async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /ban komandasi - foydalanuvchini vaqtincha cheklaydi (xabar yoza olmaydi).
    Ishlatish usullari:
      1) Foydalanuvchining xabariga REPLY qilib /ban deb yozish (eng ishonchli usul)
      2) /ban @username
      3) /ban <user_id yoki chat_id>
    Har safar shu odam qayta ban olsa, muddat 2 baravar oshadi: 1s -> 2s -> 4s -> 8s ...
    """
    chat = update.effective_chat
    message = update.message

    # Faqat adminlar ban bera oladi
    requester = await chat.get_member(message.from_user.id)
    if requester.status not in ("administrator", "creator"):
        await message.reply_text("Bu komandani faqat adminlar ishlatishi mumkin.")
        return

    target_user_id = None
    target_name = None

    if message.reply_to_message:
        target_user_id = message.reply_to_message.from_user.id
        target_name = message.reply_to_message.from_user.full_name
    elif context.args:
        arg = context.args[0]
        if arg.startswith("@"):
            try:
                chat_member_info = await context.bot.get_chat(arg)
                target_user_id = chat_member_info.id
                target_name = chat_member_info.full_name or arg
            except Exception:
                await message.reply_text(
                    "Foydalanuvchi topilmadi. Eng ishonchli usul: "
                    "foydalanuvchining xabariga REPLY qilib /ban deb yozing."
                )
                return
        else:
            try:
                target_user_id = int(arg)
                target_name = arg
            except ValueError:
                await message.reply_text("Noto'g'ri ID yoki username formati.")
                return
    else:
        await message.reply_text(
            "Foydalanish:\n"
            "\u2022 Foydalanuvchi xabariga REPLY qilib: /ban\n"
            "\u2022 Yoki: /ban @username\n"
            "\u2022 Yoki: /ban <user_id>"
        )
        return

    key = (chat.id, target_user_id)
    ban_counts[key] = ban_counts.get(key, 0) + 1
    hours = 2 ** (ban_counts[key] - 1)
    until_date = datetime.now(timezone.utc) + timedelta(hours=hours)

    try:
        await context.bot.restrict_chat_member(
            chat_id=chat.id,
            user_id=target_user_id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_audios=False,
                can_send_documents=False,
                can_send_photos=False,
                can_send_videos=False,
                can_send_video_notes=False,
                can_send_voice_notes=False,
                can_send_polls=False,
                can_send_other_messages=False,   # GIF, stiker, o'yin va h.k.
                can_add_web_page_previews=False,
            ),
            until_date=until_date,
        )
        await message.reply_text(
            f"{target_name} {hours} soatga xabar yozishdan cheklandi "
            f"(bu {ban_counts[key]}-marta ban)."
        )
    except Exception as e:
        logger.error(f"Ban berishda xatolik: {e}")
        await message.reply_text(
            "Cheklashda xatolik yuz berdi. Botning \"Restrict members\" "
            "admin huquqi borligini tekshiring."
        )


async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /unban komandasi - foydalanuvchidan cheklovni oldindan olib tashlaydi.
    Ishlatish usullari xuddi /ban kabi: reply, @username yoki user_id.
    Eslatma: ban hisobi (necha marta ban olgani) reset qilinmaydi -
    shuning uchun keyingi safar qayta ban olsa, muddat baribir davom etib o'sadi.
    """
    chat = update.effective_chat
    message = update.message

    requester = await chat.get_member(message.from_user.id)
    if requester.status not in ("administrator", "creator"):
        await message.reply_text("Bu komandani faqat adminlar ishlatishi mumkin.")
        return

    target_user_id = None
    target_name = None

    if message.reply_to_message:
        target_user_id = message.reply_to_message.from_user.id
        target_name = message.reply_to_message.from_user.full_name
    elif context.args:
        arg = context.args[0]
        if arg.startswith("@"):
            try:
                chat_member_info = await context.bot.get_chat(arg)
                target_user_id = chat_member_info.id
                target_name = chat_member_info.full_name or arg
            except Exception:
                await message.reply_text(
                    "Foydalanuvchi topilmadi. Eng ishonchli usul: "
                    "foydalanuvchining xabariga REPLY qilib /unban deb yozing."
                )
                return
        else:
            try:
                target_user_id = int(arg)
                target_name = arg
            except ValueError:
                await message.reply_text("Noto'g'ri ID yoki username formati.")
                return
    else:
        await message.reply_text(
            "Foydalanish:\n"
            "\u2022 Foydalanuvchi xabariga REPLY qilib: /unban\n"
            "\u2022 Yoki: /unban @username\n"
            "\u2022 Yoki: /unban <user_id>"
        )
        return

    try:
        await context.bot.restrict_chat_member(
            chat_id=chat.id,
            user_id=target_user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            ),
        )
        await message.reply_text(f"{target_name} cheklovdan chiqarildi.")
    except Exception as e:
        logger.error(f"Unban qilishda xatolik: {e}")
        await message.reply_text(
            "Cheklovni olib tashlashda xatolik yuz berdi. Botning "
            "\"Restrict members\" admin huquqi borligini tekshiring."
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

    # Foydalanuvchini vaqtincha cheklash komandasi (faqat adminlar uchun)
    app.add_handler(CommandHandler("ban", ban_command))

    # Foydalanuvchidan cheklovni olib tashlash komandasi (faqat adminlar uchun)
    app.add_handler(CommandHandler("unban", unban_command))

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
