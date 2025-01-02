import os
import logging
import sys
from asyncio import Queue, sleep
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from database import SessionLocal
from models import User

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
MEDIA_PATH = os.getenv('MEDIA_PATH')
ADMIN_USERS = [int(x.strip()) for x in os.getenv('ADMIN_USERS', '').split(',') if x.strip().isdigit()]
WEBHOOK_PATH = os.getenv('WEBHOOK_PATH')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
PORT = int(os.getenv('PORT', '8443'))

# Message Queue for handling Telegram flood control
message_queue = Queue()

# Preload media file
def preload_media():
    if os.path.isfile(MEDIA_PATH) and MEDIA_PATH.endswith('.gif'):
        with open(MEDIA_PATH, 'rb') as f:
            return f.read()
    else:
        logger.error(f"Media file not found or incorrect format: {MEDIA_PATH}")
        return None

media_content = preload_media()

async def message_worker(application: Application):
    """Worker that processes messages from the queue and sends them to Telegram."""
    while True:
        task = await message_queue.get()
        try:
            await task()
        except Exception as e:
            logger.error(f"Error processing message queue task: {e}")
        finally:
            message_queue.task_done()
        await sleep(0.034)  # Ensure at least 30ms between messages (Telegram flood limit)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command and registers users in the database."""
    logger.info(f"/start command received from {update.effective_user.id}")
    try:
        if update.effective_chat.type == 'private':
            user_id = update.effective_user.id
            username = update.effective_user.username or "Unknown"
            first_name = update.effective_user.first_name or "Unknown"
            last_name = update.effective_user.last_name or "Unknown"
            referral_code = context.args[0] if context.args else None

            # Save user data to the database
            with SessionLocal() as db:
                user = db.query(User).filter(User.telegram_user_id == user_id).first()
                if not user:
                    user = User(
                        telegram_user_id=user_id,
                        username=username,
                        first_name=first_name,
                        last_name=last_name,
                        first_start_param=referral_code if referral_code else None
                    )
                    db.add(user)
                    db.commit()
                    logger.info(f"New user registered: {user_id}, param={referral_code}")
                else:
                    logger.info(f"Existing user accessed: {user_id}")

            open_app_url = f"https://t.me/CoinbeatsMiniApp_bot/miniapp"
            if referral_code:
                open_app_url += f"?startapp={referral_code}"

            keyboard = [
                [InlineKeyboardButton("🚀 Open App", url=open_app_url)],
                [InlineKeyboardButton("📢 Subscribe To Channel", url="https://t.me/CoinBeats")],
                [InlineKeyboardButton("💬 Discussion Groups", url="https://t.me/CoinBeatsDiscuss")],
                [InlineKeyboardButton("🆘 Help & Support", url="https://t.me/mikkmm")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            welcome_message = (
                "CoinBeats Crypto School is an interactive platform for crypto education where you can get paid to learn about DeFi, "
                "NFTs, gaming, trading, earning yield, and discovering alpha from top educators. 🤓📕\n\n"
                "All lessons come with quizzes, raffles, tasks. By completing academies, you'll qualify for raffles, weekly scholarships, "
                "and earn points for potential future airdrops. 💰💰\n\n"
                "Start learning and earning daily rewards! 🚀🚀"
            )

            await message_queue.put(lambda: context.bot.send_animation(
                chat_id=update.effective_chat.id,
                animation=media_content,
                caption=welcome_message,
                reply_markup=reply_markup
            ))
    except Exception as e:
        logger.error(f"Error in /start: {e}")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /broadcast to send a message or photo to the bot's chat."""
    if update.effective_user.id not in ADMIN_USERS:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    message_text = update.message.text.partition(' ')[2] if update.message.text else ''
    photo = update.message.photo[-1].file_id if update.message.photo else None

    if not message_text and not photo:
        await update.message.reply_text("Please provide a message or photo to broadcast.")
        return

    try:
        parts = message_text.split('||') if message_text else []
        text = parts[0].strip() if parts else ''
        buttons = []

        # Parse custom buttons from the message
        for part in parts[1:]:
            if ',' in part:
                btn_text, btn_url = part.strip().split(',', 1)
                buttons.append([InlineKeyboardButton(btn_text.strip(), url=btn_url.strip())])

        # Add the default "Open App" button to every broadcast
        default_button = [InlineKeyboardButton("🚀 Open App", url="https://t.me/CoinbeatsMiniApp_bot/miniapp")]
        buttons.append(default_button)

        reply_markup = InlineKeyboardMarkup(buttons) if buttons else None

        # Send broadcast
        if photo:
            await message_queue.put(lambda: context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=photo,
                caption=text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            ))
        else:
            await message_queue.put(lambda: context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            ))

        await update.message.reply_text("Broadcast sent successfully.")
    except Exception as e:
        logger.error(f"Error in broadcast: {e}")

def main():
    """Set up webhook and start the bot."""
    logger.info("Starting the bot in webhook mode...")

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(lambda app: app.job_queue.start())  # Start the job queue
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex("^/broadcast"), broadcast))

    # Start message worker for queue
    if application.job_queue:
        application.job_queue.run_once(lambda _: message_worker(application), when=0)

    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=WEBHOOK_PATH,
        webhook_url=f"{WEBHOOK_URL}/{WEBHOOK_PATH}"
    )

if __name__ == '__main__':
    main()
