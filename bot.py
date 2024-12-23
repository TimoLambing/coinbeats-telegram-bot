import os
import asyncio
import logging
import sys
import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from database import SessionLocal
from models import User

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
MEDIA_PATH = os.getenv('MEDIA_PATH')
ADMIN_USERS = [int(x.strip()) for x in os.getenv('ADMIN_USERS', '').split(',') if x.strip().isdigit()]

# For greeting new members once in a period
last_welcome_time = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"/start command received from chat ID: {update.effective_chat.id}")
    try:
        if update.effective_chat.type == 'private':
            user_id = update.effective_user.id
            referral_code = context.args[0] if context.args else ''
            logger.info(f"Referral code: {referral_code}")

            # Insert user into DB if not existing
            db: Session = SessionLocal()
            db_user = db.query(User).filter(User.telegram_user_id == user_id).first()
            if not db_user:
                new_user = User(telegram_user_id=user_id)
                db.add(new_user)
                db.commit()
                db.refresh(new_user)
                logger.info(f"Added new user ID: {user_id}")
            db.close()

            if referral_code:
                open_app_url = f"https://t.me/CoinbeatsMiniApp_bot/miniapp?startapp={referral_code}"
            else:
                open_app_url = "https://t.me/CoinbeatsMiniApp_bot/miniapp"

            keyboard = [
                [InlineKeyboardButton("🚀 Open App", url=open_app_url)],
                [InlineKeyboardButton("📢 Subscribe To Channel", url="https://t.me/CoinBeats")],
                [InlineKeyboardButton("💬 Discussion Groups", url="https://t.me/CoinBeatsDiscuss")],
                [InlineKeyboardButton("🤝 Partnerships for Protocols", url="https://t.me/mikkmm")],
                [InlineKeyboardButton("🆘 Help & Support", url="https://t.me/mikkmm")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            welcome_message = (
                "CoinBeats Crypto School is an interactive platform for crypto education where you can get paid to learn about DeFi protocols, "
                "NFTs, gaming, trading, earning yield, and discovering alpha from the best educators in the space. 🤓📕\n\n"
                "All lessons come with quizzes, raffles, and tasks. By completing academies, you'll qualify for raffles and participate in Weekly Scholarship "
                "(minimum $100 per student) competitions, as well as earn points for potential future airdrop. 💰💰\n\n"
                "Start learning and earning daily rewards! 🚀🚀"
            )

            await context.bot.send_animation(
                chat_id=update.effective_chat.id,
                animation=InputFile(MEDIA_PATH),
                caption=welcome_message,
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        else:
            bot_username = context.bot.username
            await update.message.reply_text(f"Please start me in private by clicking here: https://t.me/{bot_username}")
    except Exception as e:
        logger.error(f"Error in /start command: {e}")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        if query.data == 'main':
            await start(update, context)
    except Exception as e:
        logger.error(f"Error in button handler: {e}")

async def greet_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_welcome_time
    try:
        for new_member in update.message.new_chat_members:
            if new_member.is_bot:
                continue
            current_time = datetime.datetime.now()
            if last_welcome_time and (current_time - last_welcome_time).seconds < 30:
                return
            last_welcome_time = current_time

            welcome_message = (
                f"Welcome, {new_member.mention_html()}! 🎉\n\n"
                "CoinBeats Crypto School is an interactive platform for crypto education where you can get paid to learn about DeFi protocols, NFTs, gaming, trading, "
                "earning yield, and discovering alpha from the best educators in the space. 🤓📕\n\n"
                "👉 <b>To get started, please start our bot in private:</b> @CoinBeatsBunny_bot\n\n"
                "🚀 Start learning and earning daily rewards!"
            )

            keyboard = [
                [InlineKeyboardButton("🚀 Start Bot in Private", url="https://t.me/CoinBeatsBunny_bot?start=fromgroup")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=welcome_message,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
    except Exception as e:
        logger.error(f"Error in greet_new_member: {e}")

class BroadcastFilter(filters.MessageFilter):
    def filter(self, message):
        return ((message.text and message.text.startswith('/broadcast')) or
                (message.caption and message.caption.startswith('/broadcast')))

broadcast_filter = BroadcastFilter()

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_USERS:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    if update.message.text and update.message.text.startswith('/broadcast'):
        message_text = update.message.text.partition(' ')[2]
    elif update.message.caption and update.message.caption.startswith('/broadcast'):
        message_text = update.message.caption.partition(' ')[2]
    else:
        message_text = ''

    if not message_text and not update.message.photo:
        await update.message.reply_text("Please provide a message or image to broadcast.")
        return

    try:
        parts = message_text.split('||') if message_text else []
        text = parts[0].strip() if parts else ''
        buttons = []

        for part in parts[1:]:
            if ',' in part:
                btn_text, btn_url = part.strip().split(',', 1)
                buttons.append([InlineKeyboardButton(btn_text.strip(), url=btn_url.strip())])

        default_button = [InlineKeyboardButton("🚀 Open App", url="https://t.me/CoinbeatsMiniApp_bot/miniapp")]
        buttons.append(default_button)
        reply_markup = InlineKeyboardMarkup(buttons) if buttons else None

        photo = update.message.photo[-1].file_id if update.message.photo else None

        db: Session = SessionLocal()
        db_users = db.query(User).all()
        db.close()

        for db_user in db_users:
            try:
                if photo:
                    await context.bot.send_photo(
                        chat_id=db_user.telegram_user_id,
                        photo=photo,
                        caption=text,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                else:
                    await context.bot.send_message(
                        chat_id=db_user.telegram_user_id,
                        text=text,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
            except Exception as e:
                logger.error(f"Error sending message to {db_user.telegram_user_id}: {e}")

        await update.message.reply_text("Broadcast sent successfully.")
    except Exception as e:
        logger.error(f"Error in broadcast command: {e}")
        await update.message.reply_text("An error occurred while sending the broadcast. Please check your message format.")

def main():
    logger.info("Starting the bot...")
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, greet_new_member))
    application.add_handler(MessageHandler(broadcast_filter, broadcast))

    application.run_polling()

if __name__ == '__main__':
    main()
