import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime, timedelta
import sqlite3
from config import BOT_TOKEN, MAX_PARTICIPANTS, RESPONSES
from utils import log_command
from keep_alive import keep_alive

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Database setup
def setup_database():
    """Initialize SQLite database"""
    try:
        # Create a new database connection
        conn = sqlite3.connect('participants.db')
        cursor = conn.cursor()

        # Drop existing table if it exists
        cursor.execute('DROP TABLE IF EXISTS participants')

        # Create the table without chat_id
        cursor.execute('''
            CREATE TABLE participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT
            )
        ''')
        conn.commit()
        logger.info("Database initialized successfully")
    except sqlite3.Error as e:
        logger.error(f"Database initialization error: {e}")
    finally:
        if conn:
            conn.close()

def get_db():
    """Get database connection"""
    return sqlite3.connect('participants.db', check_same_thread=False)

def get_participants_count():
    """Get current number of participants"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM participants")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def add_participant(user_id: int, username: str):
    """Add a participant to the database"""
    if get_participants_count() >= MAX_PARTICIPANTS:
        logger.info(f"List full, cannot add user {username}")
        return False

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""INSERT INTO participants 
                         (user_id, username) VALUES (?, ?)""",
                      (user_id, username))
        conn.commit()
        success = cursor.rowcount > 0
        logger.info(f"Added user {username} to list. Success: {success}")

        # Log current entries for this user
        cursor.execute("""
            SELECT COUNT(*) FROM participants 
            WHERE user_id=?
        """, (user_id,))
        entry_count = cursor.fetchone()[0]
        logger.info(f"User {username} now has {entry_count} entries in the list")

        return success
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return False
    finally:
        conn.close()

def remove_participant(user_id: int):
    """Remove a single participant entry from the database"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Get the count before deletion
        cursor.execute("""
            SELECT username, COUNT(*) FROM participants 
            WHERE user_id=?
            GROUP BY username
        """, (user_id,))
        result = cursor.fetchone()
        if result:
            username, count = result
            logger.info(f"User {username} has {count} entries before removal")

        # Delete the most recent entry
        cursor.execute("""
            DELETE FROM participants 
            WHERE id = (
                SELECT id FROM participants 
                WHERE user_id=? 
                ORDER BY id DESC LIMIT 1
            )
        """, (user_id,))
        conn.commit()
        success = cursor.rowcount > 0

        if success and result:
            username = result[0]
            logger.info(f"Successfully removed one entry for user {username}")
            # Get remaining count
            cursor.execute("""
                SELECT COUNT(*) FROM participants 
                WHERE user_id=?
            """, (user_id,))
            remaining = cursor.fetchone()[0]
            logger.info(f"User {username} has {remaining} entries remaining")

        return success
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return False
    finally:
        conn.close()

def get_all_participants():
    """Get list of all participants"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM participants")
    participants = [row[0] for row in cursor.fetchall()]
    conn.close()
    return participants

async def clear_list(context: ContextTypes.DEFAULT_TYPE):
    """Clear the participants list on scheduled days"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM participants")
        conn.commit()
        # Send message to all unique chats where the bot is active
        chat_id = context.job.chat_id
        await context.bot.send_message(
            chat_id=chat_id,
            text=RESPONSES['list_cleared']
        )
        logger.info("Global participant list cleared")
    except sqlite3.Error as e:
        logger.error(f"Error clearing list: {e}")
    finally:
        conn.close()

async def format_participants_list(participants):
    """Format the participants list for display"""
    if not participants:
        return RESPONSES['list_empty']

    # Count occurrences of each participant
    participant_counts = {}
    for name in participants:
        participant_counts[name] = participant_counts.get(name, 0) + 1

    # Format the list with counts
    formatted_list = []
    for name, count in participant_counts.items():
        entry = f"👤 {name}"
        if count > 1:
            entry += f" (x{count})"
        formatted_list.append(entry)

    count = len(participants)  # Total entries
    return f"Участники ({count}/{MAX_PARTICIPANTS}):\n" + "\n".join(formatted_list)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle + and - messages in any chat"""
    if not update.message or not update.message.text:
        logger.info("Received update without message or text")
        return

    message = update.message.text.strip()
    user = update.effective_user
    chat_type = update.effective_chat.type

    logger.info(f"Received message: '{message}' from user {user.first_name} (ID: {user.id}) in chat type: {chat_type}")

    if message in ["+", "-"]:
        try:
            if message == "+":
                if add_participant(user.id, user.first_name):
                    count = get_participants_count()
                    participants = get_all_participants()
                    list_message = await format_participants_list(participants)
                    await update.message.reply_text(
                        f"{RESPONSES['participated'].format(count, MAX_PARTICIPANTS)}\n\n{list_message}"
                    )
                    logger.info(f"User {user.first_name} added to global list. Total: {count}")
                    log_command(
                        user_id=user.id,
                        username=user.first_name,
                        command="participate",
                        message=f"Added to global list. Total: {count}"
                    )
                else:
                    await update.message.reply_text(RESPONSES['list_full'])
                    logger.info(f"User {user.first_name} attempted to join full list")

            elif message == "-":
                if remove_participant(user.id):
                    count = get_participants_count()
                    participants = get_all_participants()
                    list_message = await format_participants_list(participants)
                    await update.message.reply_text(
                        f"{RESPONSES['removed'].format(count, MAX_PARTICIPANTS)}\n\n{list_message}"
                    )
                    logger.info(f"User {user.first_name} removed from global list. Total: {count}")
                    log_command(
                        user_id=user.id,
                        username=user.first_name,
                        command="remove",
                        message=f"Removed from global list. Total: {count}"
                    )
                else:
                    await update.message.reply_text(RESPONSES['not_in_list'])
                    logger.info(f"User {user.first_name} attempted to remove but wasn't in list")
        except Exception as e:
            logger.error(f"Error processing command {message} from user {user.first_name}: {str(e)}")
            await update.message.reply_text(RESPONSES['error'])

    else:
        # Only log unrecognized text messages for debugging
        logger.info(f"Unrecognized message '{message}' received in {chat_type} chat")

async def list_participants_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List command handler"""
    participants = get_all_participants()
    list_message = await format_participants_list(participants)
    await update.message.reply_text(list_message)

    log_command(
        user_id=update.effective_user.id,
        username=update.effective_user.first_name,
        command="/list",
        message=f"Listed {len(participants)} participants"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    await update.message.reply_text(RESPONSES['welcome'])
    log_command(
        user_id=update.effective_user.id,
        username=update.effective_user.first_name,
        command="/start",
        message="Started bot interaction"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command handler"""
    await update.message.reply_text(RESPONSES['help'])
    log_command(
        user_id=update.effective_user.id,
        username=update.effective_user.first_name,
        command="/help",
        message="Requested help information"
    )

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear command handler - only for admins"""
    # Check if user is admin
    user = update.effective_user
    chat = update.effective_chat

    if not chat:
        return

    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        is_admin = member.status in ['creator', 'administrator']

        if not is_admin:
            await update.message.reply_text(RESPONSES['not_admin'])
            logger.info(f"Non-admin user {user.first_name} attempted to clear list")
            return

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM participants")
        conn.commit()
        conn.close()

        await update.message.reply_text(RESPONSES['list_cleared'])
        logger.info(f"Admin {user.first_name} cleared the participants list")

        log_command(
            user_id=user.id,
            username=user.first_name,
            command="/clear",
            message="Manually cleared participant list"
        )
    except Exception as e:
        logger.error(f"Error in clear command: {e}")
        await update.message.reply_text(RESPONSES['error'])

def main():
    """Main function to run the bot"""
    # Keep the bot alive
    keep_alive()
    # Initialize database
    setup_database()

    # Create application
    if not BOT_TOKEN:
        logger.error("No BOT_TOKEN found in environment variables")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list", list_participants_cmd))
    application.add_handler(CommandHandler("clear", clear_command))

    # Message handler for + and - commands with less restrictive filter
    application.add_handler(MessageHandler(
        filters.TEXT,
        handle_message,
        block=False
    ))

    # Log setup
    logger.info("Bot handlers registered")
    logger.info("Starting bot...")

    # Start the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
