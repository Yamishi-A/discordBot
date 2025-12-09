# bot.py
import os
import discord
import sqlite3
from discord.ext import commands
from dotenv import load_dotenv
from bot_config import DB_NAME # Import DB_NAME for setup

# --- Load .env ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")


# --- DATABASE SETUP (Crucial Initialization) ---
# This ensures the database file and all required tables exist before Cogs load.
conn = None # Initialize conn outside try/finally scope
try:
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # PITY TABLE
    c.execute("""
    CREATE TABLE IF NOT EXISTS pity (
        user_id INTEGER PRIMARY KEY,
        pity_5_star INTEGER DEFAULT 0,
        pity_4_star INTEGER DEFAULT 0,
        total_pulls INTEGER DEFAULT 0
    )
    """)
    # INVENTORY TABLE
    c.execute("""
    CREATE TABLE IF NOT EXISTS inventory (
        user_id INTEGER,
        item_name TEXT,
        quantity INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, item_name)
    )
    """)
    # PULL HISTORY TABLE
    c.execute("""
    CREATE TABLE IF NOT EXISTS pull_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        item_name TEXT,
        rarity INTEGER,
        timestamp INTEGER
    )
    """)
    conn.commit()
    print(f"Database {DB_NAME} initialized and tables checked.")

except Exception as e:
    print(f"FATAL ERROR: Could not initialize database: {e}")
    if conn:
        conn.close()
    exit(1)


# --- BOT SETUP & INTENTS ---
intents = discord.Intents.default()
# Enables the bot to read message content (required for xp_reporter)
intents.message_content = True
# Required for role checks and member lookups (Server Members Intent)
intents.members = True 

bot = commands.Bot(
    command_prefix="/", 
    intents=intents
)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
    print("Bot is ready and Cogs are loaded.")


# --- COG LOADING ---
COGS = ["gacha_cog", "xp_reporter_cog"]

print("STARTING BOT...")

for cog in COGS:
    try:
        # NOTE: Cog filenames must match the names in this list (e.g., 'gacha_cog.py')
        bot.load_extension(cog)
        # The success message is now in the cog's setup function for accuracy
    except Exception as e:
        print(f"Failed to load {cog}: {e}")

# --- RUN BOT ---
if __name__ == "__main__":
    if TOKEN is None:
        print("ERROR: DISCORD_TOKEN not found in environment variables. Bot will not run.")
        
    try:
        if TOKEN is not None:
            bot.run(TOKEN)
    except discord.errors.PrivilegedIntentsRequired:
        print("\nFATAL ERROR: Privileged Intents Required.")
        print("Please enable 'Server Members Intent' and 'Message Content Intent' in the Discord Developer Portal.")
    except Exception as e:
        print(f"An error occurred during bot execution: {e}")
    finally:
        # Close the connection upon shutdown
        if conn:
            conn.close()
            print(f"Closed database connection to {DB_NAME}")