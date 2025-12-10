# bot.py
import os
import discord
import sqlite3
import traceback
from discord.ext import commands
from dotenv import load_dotenv
from bot_config import DB_NAME

# --- Load .env ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# --- DATABASE SETUP ---
conn = None
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

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix="/",
    intents=intents
)

# --- COG LIST ---
COGS = ["gacha_main", "xp_reporter_main"]


# --- PROPER COG LOADING (sync, before bot.run) ---
def load_cogs():
    print("STARTING COG LOADING...")
    for cog in COGS:
        try:
            bot.load_extension(cog)  # <-- NOT awaited; correct for pre-run
            print(f"✅ Successfully loaded {cog}")
        except Exception as e:
            print(f"❌ Failed to load {cog}: {e}")
            traceback.print_exc()


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
    print("Bot is ready and all Cogs were loaded before startup.")


# --- RUN BOT ---
if __name__ == "__main__":
    if TOKEN is None:
        print("ERROR: DISCORD_TOKEN not found in environment variables.")
    else:
        load_cogs()  # <-- Load cogs BEFORE bot.run()
        try:
            bot.run(TOKEN)
        except discord.errors.PrivilegedIntentsRequired:
            print("\nFATAL ERROR: Privileged Intents Required.")
            print("Enable 'Server Members Intent' and 'Message Content Intent' in Developer Portal.")
        finally:
            if conn:
                conn.close()
                print(f"Closed database connection to {DB_NAME}")
