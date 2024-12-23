import os
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

# For greeting new members once in a short timeframe
last_welcome_time = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command, registers user in DB, and passes referral param if new."""
    logger.info(f"/start command from chat ID: {update.effective_chat.id}")
    try:
        # Only proceed if this is a private (1:1) chat
        if update.effective_chat.type == 'private':
            user_id = update.effective_user.id
            referral_code = context.args[0] if context.args else ''
            logger.info(f"Referral/campaign code: {referral_code}")

            # Open DB session
            db: Session = SessionLocal()
            db_user = db.query(User).filter(User.telegram_user_id == user_id).first()

            if not db_user:
                # New user: store the referral code (if any)
                new_user = User(
                    telegram_user_id=user_id,
                    first_start_param=referral_code if referral_code else None
                )
                db.add(new_user)
                db.commit()
                db.refresh(new_user)
                logger.info(f"New user created with ID {new_user.id}, param={referral_code}")

                # Since it's their first time, pass the referral code in the "open app" link
                if referral_code:
                    open_app_url = f"https://t.me/CoinbeatsMiniApp_bot/miniapp?startapp={referral_code}"
                else:
                    open_app_url = "https://t.me/CoinbeatsMiniApp_bot/miniapp"
            else:
                # Existing user: do NOT pass any referral param anymore
                open_app_url = "https://t.me/CoinbeatsMiniApp_bot/miniapp"

            db.close()

            # Build the keyboard
            keyboard = [
                [InlineKeyboardButton("🚀 Open App", url=open_app_url)],
                [InlineKeyboardButton("📢 Subscribe To Channel", url="https://t.me/CoinBeats")],
                [InlineKeyboardButton("💬 Discussion Groups", url="https://t.me/CoinBeatsDiscuss")],
                [InlineKeyboardButton("🤝 Partnerships for Protocols", url="https://t.me/mikkmm")],
                [InlineKeyboardButton("🆘 Help & Support", url="https://t.me/mikkmm")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Compose welcome message
            welcome_msg = (
                "CoinBeats Crypto School is an interactive platform for crypto education where you can get paid to learn about DeFi, "
                "NFTs, gaming, trading, earning yield, and discovering alpha from top educators. 🤓📕\n\n"
                "All lessons come with quizzes, raffles, tasks. By completing academies, you'll qualify for raffles, weekly scholarships, "
                "and earn points for potential future airdrops. 💰💰\n\n"
                "Start learning and earning daily rewards! 🚀🚀"
            )

            # Send the animation with welcome text
            await context.bot.send_animation(
                chat_id=update.effective_chat.id,
                animation=InputFile(MEDIA_PATH),
                caption=welcome_msg,
                parse_mode='HTML',
                reply_markup=reply_markup
            )

        else:
            # If this is not a private chat
            bot_username = context.bot.username
            await update.message.reply_text(
                f"Please start me in private by clicking: https://t.me/{bot_username}"
            )
    except Exception as e:
        logger.error(f"Error in /start command: {e}")


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback when a user presses an InlineKeyboardButton."""
    query = update.callback_query
    await query.answer()
    try:
        if query.data == 'main':
            await start(update, context)
    except Exception as e:
        logger.error(f"Error in button callback: {e}")


async def greet_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Greets new members in a group chat. Throttled by last_welcome_time."""
    global last_welcome_time
    try:
        for new_member in update.message.new_chat_members:
            if new_member.is_bot:
                continue  # skip bots
            current_time = datetime.datetime.now()
            if last_welcome_time and (current_time - last_welcome_time).seconds < 30:
                return  # Don't spam welcomes
            last_welcome_time = current_time

            greet_msg = (
                f"Welcome, {new_member.mention_html()}! 🎉\n\n"
                "CoinBeats Crypto School is an interactive platform for crypto education where you can get paid to learn about DeFi protocols, NFTs, gaming, trading, "
                "earning yield, and discovering alpha from top educators. 🤓📕\n\n"
                "👉 <b>To get started, please start our bot in private:</b> @CoinBeatsBunny_bot\n\n"
                "🚀 Start learning and earning daily rewards!"
            )

            keyboard = [
                [InlineKeyboardButton("🚀 Start Bot in Private", url="https://t.me/CoinBeatsBunny_bot?start=fromgroup")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=greet_msg,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
    except Exception as e:
        logger.error(f"Error in greet_new_member: {e}")


class BroadcastFilter(filters.MessageFilter):
    """Custom filter for detecting /broadcast usage."""
    def filter(self, message):
        # Check both text & caption for '/broadcast'
        return (
            (message.text and message.text.startswith('/broadcast')) or
            (message.caption and message.caption.startswith('/broadcast'))
        )

broadcast_filter = BroadcastFilter()


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Allows Admins to broadcast a text or photo to all users in DB."""
    if update.effective_user.id not in ADMIN_USERS:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    # Extract the text after '/broadcast'
    if update.message.text and update.message.text.startswith('/broadcast'):
        message_text = update.message.text.partition(' ')[2]
    elif update.message.caption and update.message.caption.startswith('/broadcast'):
        message_text = update.message.caption.partition(' ')[2]
    else:
        message_text = ''

    if not message_text and not update.message.photo:
        await update.message.reply_text("Please provide a message or an image to broadcast.")
        return

    try:
        # Optional: parse '||' for custom buttons
        parts = message_text.split('||') if message_text else []
        text = parts[0].strip() if parts else ''
        buttons = []

        for part in parts[1:]:
            if ',' in part:
                btn_text, btn_url = part.strip().split(',', 1)
                buttons.append([InlineKeyboardButton(btn_text.strip(), url=btn_url.strip())])

        # Always append an "Open App" button
        default_button = [InlineKeyboardButton("🚀 Open App", url="https://t.me/CoinbeatsMiniApp_bot/miniapp")]
        buttons.append(default_button)
        reply_markup = InlineKeyboardMarkup(buttons) if buttons else None

        # If there's a photo, grab file_id
        photo_id = update.message.photo[-1].file_id if update.message.photo else None

        db: Session = SessionLocal()
        db_users = db.query(User).all()
        db.close()

        sent_count = 0
        for db_user in db_users:
            try:
                if photo_id:
                    await context.bot.send_photo(
                        chat_id=db_user.telegram_user_id,
                        photo=photo_id,
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
                sent_count += 1
            except Exception as e:
                logger.error(f"Error sending broadcast to {db_user.telegram_user_id}: {e}")

        await update.message.reply_text(f"Broadcast sent to {sent_count} users.")
    except Exception as e:
        logger.error(f"Error in broadcast command: {e}")
        await update.message.reply_text("An error occurred while broadcasting. Check logs or message format.")


def main() -> None:
    """Sets up the application in Webhook mode, not polling, 
       so that Telegram sends updates to /bot on your domain."""
    logger.info("Starting the bot in Webhook mode...")

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        # Note: DO NOT call .run_polling() below. We'll use .run_webhook().
        .build()
    )

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, greet_new_member))
    application.add_handler(MessageHandler(broadcast_filter, broadcast))

    # Webhook setup
    # Example path: '/bot'
    # Example listening on 0.0.0.0:8443 inside container. 
    # Then Nginx on the host routes https://bot.coinbeats.xyz/bot → container:8443/bot
    PORT = 8445  # or 8444 / 8445 in each container
    WEBHOOK_PATH = "/bot"
    WEBHOOK_URL = f"https://bot.coinbeats.xyz{WEBHOOK_PATH}"

    # Listen on 0.0.0.0 at PORT in the container
    application.run_webhook(
        listen='0.0.0.0',
        port=PORT,
        url_path=WEBHOOK_PATH,
        webhook_url=WEBHOOK_URL
    )


if __name__ == '__main__':
    main()
