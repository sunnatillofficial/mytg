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
# MAJBURIY OBUNA KANALI
# Botdan foydalanish uchun foydalanuvchi shu kanalga obuna bo'lishi shart.
# Bot shu kanalda ADMIN bo'lishi kerak (aks holda obunani tekshira olmaydi).
# ------------------------------------------------------------------
REQUIRED_CHANNEL = "@game_essence"
REQUIRED_CHANNEL_LINK = "https://t.me/game_essence"

# ------------------------------------------------------------------
# SIZNING SHAXSINGIZNI TASVIRLAB BERUVCHI "SYSTEM PROMPT"
# ------------------------------------------------------------------
SYSTEM_PROMPT = """
Sen Sunnatillo o'rniga Telegram guruhidagi xabarlarga javob berayapsan.
Uslubing: samimiy, qisqa va do'stona. O'zbek tilida, kundalik so'zlashuv uslubida yoz.
Agar savol muhim yoki shaxsiy bo'lsa (pul, uchrashuv, muhim qaror), hech qanday javob yozma -
shunchaki "###JIM###" so'zini yoz, boshqa hech narsa qo'shma.
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

# Bot bilan muloqotda bo'lgan barcha chatlar (guruh + shaxsiy) shu yerda saqlanadi.
# DIQQAT: RAM'da saqlanadi, bot qayta ishga tushsa (redeploy/restart) tozalanadi.
known_chats: set[int] = set()


async def track_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Har qanday kelgan xabardan chat ID sini eslab qoladi (reklama uchun kerak)."""
    if update.effective_chat:
        known_chats.add(update.effective_chat.id)


async def is_subscribed(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Foydalanuvchi REQUIRED_CHANNEL kanaliga obuna bo'lganini tekshiradi."""
    try:
        member = await context.bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        return member.status not in ("left", "kicked")
    except Exception as e:
        logger.error(f"Obunani tekshirishda xatolik: {e}")
        # Tekshira olmasak, ehtiyot uchun False qaytaramiz (foydalanishga ruxsat bermaymiz)
        return False


def parse_duration(text: str) -> timedelta | None:
    """
    Muddat matnini timedelta ga aylantiradi.
    Qo'llab-quvvatlanadigan formatlar: 30m, 2h, 1d (daqiqa/soat/kun)
    Agar faqat son yozilsa (masalan "3"), soat sifatida qabul qilinadi.
    """
    text = text.strip().lower()
    if not text:
        return None

    try:
        if text.endswith("m"):
            return timedelta(minutes=int(text[:-1]))
        if text.endswith("h"):
            return timedelta(hours=int(text[:-1]))
        if text.endswith("d"):
            return timedelta(days=int(text[:-1]))
        # Faqat son bo'lsa - soat deb hisoblanadi
        return timedelta(hours=int(text))
    except ValueError:
        return None


async def reklama_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /reklama <matn> - admin kiritgan matnni bot avval muloqotda bo'lgan
    BARCHA guruh va shaxsiy chatlarga yuboradi.
    Guruhda ishlatilsa - faqat o'sha guruh adminlari ishlata oladi.
    Shaxsiy chatda ishlatilsa - faqat ALLOWED_CHAT_IDS ro'yxatidagi (ishonchli) odamlar ishlata oladi.
    """
    chat = update.effective_chat
    message = update.message

    # Ruxsat tekshiruvi
    if chat.type == "private":
        if message.from_user.id not in ALLOWED_CHAT_IDS:
            await message.reply_text("Sizda bu komandani ishlatish huquqi yo'q.")
            return
    else:
        requester = await chat.get_member(message.from_user.id)
        if requester.status not in ("administrator", "creator"):
            await message.reply_text("Bu komandani faqat adminlar ishlatishi mumkin.")
            return

    ad_text = " ".join(context.args) if context.args else None
    if not ad_text:
        await message.reply_text("Foydalanish: /reklama <matningiz>")
        return

    # Yuborish mo'ljallangan barcha chatlar: ma'lum bo'lgan chatlar + ALLOWED_CHAT_IDS
    targets = known_chats | ALLOWED_CHAT_IDS

    success = 0
    failed = 0
    for target_chat_id in targets:
        try:
            await context.bot.send_message(chat_id=target_chat_id, text=ad_text)
            success += 1
        except Exception as e:
            logger.warning(f"Reklama {target_chat_id} ga yuborilmadi: {e}")
            failed += 1

    await message.reply_text(
        f"Reklama yuborildi.\nMuvaffaqiyatli: {success}\nYuborilmadi: {failed}"
    )


async def chatid_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Joriy chat ID sini ko'rsatadi - guruh ID sini topish uchun ishlatiladi."""
    chat = update.effective_chat
    await update.message.reply_text(
        f"Ushbu chat ID: `{chat.id}`\nTuri: {chat.type}",
        parse_mode="Markdown",
    )


async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /ban komandasi - foydalanuvchini siz belgilagan muddatga cheklaydi (xabar yoza olmaydi).
    Ishlatish usullari:
      1) Foydalanuvchining xabariga REPLY qilib: /ban <muddat>   masalan: /ban 3h
      2) /ban @username <muddat>
      3) /ban <user_id> <muddat>
    Muddat formati: 30m (daqiqa), 2h (soat), 1d (kun). Faqat son yozilsa - soat deb olinadi.
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
    duration_text = None

    if message.reply_to_message:
        target_user_id = message.reply_to_message.from_user.id
        target_name = message.reply_to_message.from_user.full_name
        if context.args:
            duration_text = context.args[0]
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
                    "foydalanuvchining xabariga REPLY qilib /ban <muddat> deb yozing."
                )
                return
        else:
            try:
                target_user_id = int(arg)
                target_name = arg
            except ValueError:
                await message.reply_text("Noto'g'ri ID yoki username formati.")
                return
        if len(context.args) > 1:
            duration_text = context.args[1]
    else:
        await message.reply_text(
            "Foydalanish:\n"
            "\u2022 Foydalanuvchi xabariga REPLY qilib: /ban <muddat>  (masalan: /ban 3h)\n"
            "\u2022 Yoki: /ban @username <muddat>\n"
            "\u2022 Yoki: /ban <user_id> <muddat>\n\n"
            "Muddat formati: 30m (daqiqa), 2h (soat), 1d (kun)."
        )
        return

    if not duration_text:
        await message.reply_text(
            "Muddatni ko'rsating. Masalan: /ban 3h (3 soat), /ban 30m (30 daqiqa), /ban 1d (1 kun)."
        )
        return

    duration = parse_duration(duration_text)
    if duration is None:
        await message.reply_text(
            "Muddat formati noto'g'ri. Masalan: 30m, 2h, 1d yoki shunchaki son (soat sifatida)."
        )
        return

    until_date = datetime.now(timezone.utc) + duration

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
            f"{target_name} {duration_text} muddatga xabar yozishdan cheklandi."
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


def is_bot_addressed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Guruhda bot faqat 'sunnatillo' so'zi aytilganda yoki unga reply qilinganda javob berishi kerak."""
    message = update.message

    # Bot xabariga reply qilingan bo'lsa
    if message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id:
        return True

    # Xabar matnida "sunnatillo" so'zi bo'lsa (katta-kichik harfga qaramasdan)
    if message.text and "sunnatillo" in message.text.lower():
        return True

    return False


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    chat_id = chat.id
    logger.info(f"Xabar keldi. Chat ID: {chat_id}, Turi: {chat.type}, Ruxsat etilganlar: {ALLOWED_CHAT_IDS}")

    # Guruhda - faqat ALLOWED_CHAT_IDS ro'yxatidagi guruhlarda javob beradi.
    # Shaxsiy chatda - hammaga javob beradi (lekin pastda obuna tekshiriladi).
    if chat.type != "private" and chat_id not in ALLOWED_CHAT_IDS:
        logger.info(f"Chat ID {chat_id} ruxsat etilganlar ro'yxatida yo'q, o'tkazib yuborildi.")
        return

    # Guruhda faqat mention yoki reply qilingandagina javob beradi.
    # Shaxsiy chatda esa har doim javob beradi.
    if chat.type != "private" and not is_bot_addressed(update, context):
        return

    # Botdan foydalanish uchun kerakli kanalga obuna bo'lgan bo'lishi shart
    user_id = update.message.from_user.id
    if not await is_subscribed(user_id, context):
        await update.message.reply_text(
            "\U0001F44B Assalomu alaykum!\n\n"
            "Sunnatilloning shaxsiy botidan foydalanish uchun avval bizning "
            f"kanalimizga obuna bo'lishingiz kerak:\n{REQUIRED_CHANNEL_LINK}\n\n"
            "\u2705 Obuna bo'lgach, shu yerga xabaringizni qayta yuboring - "
            "va suhbatni davom ettiramiz!"
        )
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

    # Sezgir mavzu bo'lsa, AI "###JIM###" deb javob beradi - bunday holda
    # hech narsa yubormaymiz, shunchaki xabarni e'tiborsiz qoldiramiz.
    if "###JIM###" in reply_text:
        logger.info(f"Sezgir mavzu aniqlandi, chat {chat_id} uchun javob yuborilmadi.")
        history.append({"role": "assistant", "content": "(javob berilmadi)"})
        return

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

    # Har qanday xabardan chat ID sini eslab qolish (reklama uchun) - alohida guruhda,
    # bu boshqa handlerlar ishlashiga xalaqit bermaydi.
    app.add_handler(MessageHandler(filters.ALL, track_chat), group=0)

    # Guruh ID sini topish uchun yordamchi komanda (istalgan joyda ishlaydi)
    app.add_handler(CommandHandler("chatid", chatid_command), group=1)

    # Foydalanuvchini vaqtincha cheklash komandasi (faqat adminlar uchun)
    app.add_handler(CommandHandler("ban", ban_command), group=1)

    # Foydalanuvchidan cheklovni olib tashlash komandasi (faqat adminlar uchun)
    app.add_handler(CommandHandler("unban", unban_command), group=1)

    # Reklama/e'lon yuborish komandasi (faqat adminlar uchun)
    app.add_handler(CommandHandler("reklama", reklama_command), group=1)

    # Guruh, superguruh va shaxsiy chat xabarlariga javob beradi
    # (guruhlarda faqat ALLOWED_CHAT_IDS ichidagilarga, shaxsiy chatda hamma uchun)
    app.add_handler(
        MessageHandler(
            filters.TEXT
            & (
                filters.ChatType.GROUP
                | filters.ChatType.SUPERGROUP
                | filters.ChatType.PRIVATE
            )
            & ~filters.COMMAND,
            handle_message,
        ),
        group=1,
    )

    logger.info("Bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()
