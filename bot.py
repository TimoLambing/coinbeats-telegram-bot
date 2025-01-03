import os
import logging
import sys
import json
import time
from asyncio import Queue, sleep, create_task, Task
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

# Priority Queues
user_message_queue = Queue()
broadcast_message_queue = Queue()
message_worker_task: Task | None = None

# Animation file_id cache
ANIMATION_CACHE_PATH = "animation_cache.json"
ANIMATION_FILE_ID = None

def load_animation_file_id():
    """Load the animation file_id from the cache file."""
    global ANIMATION_FILE_ID
    if os.path.isfile(ANIMATION_CACHE_PATH):
        try:
            with open(ANIMATION_CACHE_PATH, 'r') as cache_file:
                data = json.load(cache_file)
                ANIMATION_FILE_ID = data.get("file_id")
                logger.info(f"Loaded cached animation file_id: {ANIMATION_FILE_ID}")
        except Exception as e:
            logger.error(f"Error loading animation cache: {e}")
    else:
        logger.info("No animation cache found. Will upload animation on first use.")

def save_animation_file_id(file_id):
    """Save the animation file_id to the cache file."""
    global ANIMATION_FILE_ID
    ANIMATION_FILE_ID = file_id
    try:
        with open(ANIMATION_CACHE_PATH, 'w') as cache_file:
            json.dump({"file_id": file_id}, cache_file)
            logger.info(f"Saved animation file_id to cache: {file_id}")
    except Exception as e:
        logger.error(f"Error saving animation cache: {e}")

# Load animation file_id on bot startup
load_animation_file_id()

def safe_db_query(query_function, retries=3, delay=5):
    """Safely execute a database query with retries for transient errors."""
    for attempt in range(retries):
        try:
            db = SessionLocal()
            result = query_function(db)
            db.close()
            return result
        except Exception as e:
            logger.error(f"Database error on attempt {attempt + 1}: {e}")
            time.sleep(delay)
    logger.error("All retries failed. Database query unsuccessful.")
    return None

async def message_worker():
    global message_worker_task
    logger.info("Message worker started.")
    while not user_message_queue.empty() or not broadcast_message_queue.empty():
        try:
            task = None
            if not user_message_queue.empty():
                task = await user_message_queue.get()
                logger.info("Processing user message task.")
            elif not broadcast_message_queue.empty():
                task = await broadcast_message_queue.get()
                logger.info("Processing broadcast message task.")

            if task:
                logger.info("Executing task...")
                await task()
                logger.info("Task executed successfully.")
        except Exception as e:
            logger.error(f"Error processing task: {e}")
        finally:
            if task and not user_message_queue.empty():
                user_message_queue.task_done()
            elif task:
                broadcast_message_queue.task_done()

        # Add a log to see which tasks were completed
        logger.info(f"Remaining tasks in queue: {broadcast_message_queue.qsize()} (broadcast), {user_message_queue.qsize()} (user)")
        await sleep(0.034)

    logger.info("Message worker finished.")
    message_worker_task = None

async def ensure_message_worker():
    global message_worker_task
    if message_worker_task is None or message_worker_task.done():
        message_worker_task = create_task(message_worker())

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command and registers users in the database."""
    global ANIMATION_FILE_ID
    logger.info(f"/start command received from {update.effective_user.id}")
    try:
        if update.effective_chat.type == 'private':
            user_id = update.effective_user.id
            username = update.effective_user.username or "Unknown"
            first_name = update.effective_user.first_name or "Unknown"
            last_name = update.effective_user.last_name or "Unknown"
            referral_code = context.args[0] if context.args else None

            # Database operation
            def query_function(db):
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
                    if user.username != username or user.first_name != first_name or user.last_name != last_name:
                        user.username = username
                        user.first_name = first_name
                        user.last_name = last_name
                        db.commit()
                        logger.info(f"Updated user information: {user_id}")
                return user

            safe_db_query(query_function)

            open_app_url = f"https://t.me/CoinbeatsMiniApp_bot/miniapp"
            if referral_code:
                open_app_url += f"?startapp={referral_code}"

            keyboard = [
                [InlineKeyboardButton("🚀 Open App", url=open_app_url)],
                [InlineKeyboardButton("📢 Subscribe To Channel", url="https://t.me/CoinBeats")],
                [InlineKeyboardButton("💬 Discussion Groups", url="https://t.me/CoinBeatsDiscuss")],
                [InlineKeyboardButton("🤝 Partnerships for Protocols", url="https://t.me/mikkkm")],
                [InlineKeyboardButton("🆘 Help & Support", url="https://t.me/mikkkm")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            welcome_message = (
                "CoinBeats Crypto School is an interactive platform for crypto education where you can get paid to learn about DeFi, "
                "NFTs, gaming, trading, earning yield, and discovering alpha from top educators. 🤓📕\n\n"
                "All lessons come with quizzes, raffles, tasks. By completing academies, you'll qualify for raffles, weekly scholarships, "
                "and earn points for potential future airdrops. 💰💰\n\n"
                "Start learning and earning daily rewards! 🚀🚀"
            )

            # Use cached file_id if available
            if ANIMATION_FILE_ID:
                await user_message_queue.put(lambda: context.bot.send_animation(
                    chat_id=update.effective_chat.id,
                    animation=ANIMATION_FILE_ID,
                    caption=welcome_message,
                    reply_markup=reply_markup
                ))
            else:
                with open(MEDIA_PATH, 'rb') as animation_file:
                    message = await context.bot.send_animation(
                        chat_id=update.effective_chat.id,
                        animation=animation_file,
                        caption=welcome_message,
                        reply_markup=reply_markup
                    )
                    save_animation_file_id(message.animation.file_id)

            await ensure_message_worker()
    except Exception as e:
        logger.error(f"Error in /start: {e}")

        # Define a custom filter for the broadcast command
class BroadcastFilter(filters.MessageFilter):
    def filter(self, message):
        return ((message.text and message.text.startswith('/broadcast')) or
                (message.caption and message.caption.startswith('/broadcast')))

broadcast_filter = BroadcastFilter()

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /broadcast to send a message or photo to all users."""
    if update.effective_user.id not in ADMIN_USERS:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    logger.info("Starting broadcast function...")

    # Extract text and photo from the message
    message_text = None
    if update.message.text and update.message.text.startswith('/broadcast'):
        message_text = update.message.text.partition(' ')[2]
    elif update.message.caption and update.message.caption.startswith('/broadcast'):
        message_text = update.message.caption.partition(' ')[2]

    photo = update.message.photo[-1].file_id if update.message.photo else None

    logger.info(f"Broadcast text: {message_text}")
    if photo:
        logger.info(f"Broadcast photo detected with File ID: {photo}")
    else:
        logger.info("No photo detected in the broadcast message.")

    if not message_text and not photo:
        await update.message.reply_text("Please provide a message or image to broadcast.")
        return

    # Parse text and buttons
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

    logger.info("Loading users from the database...")
    users = safe_db_query(lambda db: [user.telegram_user_id for user in db.query(User).all()])
    if not users:
        logger.warning("No users found in the database for broadcasting.")
        await update.message.reply_text("No users found to broadcast the message.")
        return

    logger.info(f"Loaded {len(users)} users from the database.")
    logger.info(f"User IDs: {users}")

    # Queue messages for broadcasting
    for user_id in users:
        logger.info(f"Queuing message for user_id: {user_id}")
        if photo:
            logger.info(f"Queuing photo message for user_id: {user_id} with caption: {text}")
            await broadcast_message_queue.put(lambda user_id=user_id: context.bot.send_photo(
                chat_id=user_id,
                photo=photo,
                caption=text if text else None,
                reply_markup=reply_markup,
                parse_mode='HTML'
            ))
        else:
            logger.info(f"Queuing text message for user_id: {user_id}")
            await broadcast_message_queue.put(lambda user_id=user_id: context.bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            ))

    await update.message.reply_text("Broadcast has been queued for all users.")
    logger.info("Broadcast has been queued for all users.")

    # Start the message worker to process the queue
    await ensure_message_worker()

def main():
    logger.info("Starting the bot in webhook mode...")

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(broadcast_filter, broadcast))

    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=WEBHOOK_PATH,
        webhook_url=f"{WEBHOOK_URL}/{WEBHOOK_PATH}"
    )

if __name__ == '__main__':
    main()
