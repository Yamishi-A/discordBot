# bot.py (FINAL VERSION - Guild Sync Forced)
import os
import discord
import sqlite3
import traceback
import asyncio
from discord.ext import commands
from dotenv import load_dotenv
from bot_config import DB_NAME

# --- GUILD ID FOR INSTANT SLASH COMMAND SYNC ---
# This ID (1357263087069167706) forces the commands to appear immediately on your server.
TEST_GUILD_ID = 1357263087069167706

# --- Load .env ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# --- DATABASE SETUP ---
def init_db():
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()

        c.execute("""
        CREATE TABLE IF NOT EXISTS pity (
            user_id INTEGER PRIMARY KEY,
            pity_5_star INTEGER DEFAULT 0,
            pity_4_star INTEGER DEFAULT 0,
            total_pulls INTEGER DEFAULT 0
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            user_id INTEGER,
            item_name TEXT,
            quantity INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, item_name)
        )
        """)

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
        print(f"✅ Database {DB_NAME} initialized and tables checked.")
    except Exception as e:
        print(f"❌ FATAL ERROR: Could not initialize database: {e}")
        exit(1)
    finally:
        conn.close()

init_db()

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="$$", intents=intents)

COGS = ["gacha_main", "xp_reporter_main"]
bot.is_ready_once = False # Flag to ensure sync only happens once

@bot.event
async def setup_hook():
    """Called once when the bot is preparing to connect, before on_ready."""
    print("⏳ Loading cogs asynchronously...")
    for cog in COGS:
        try:
            await bot.load_extension(cog)
            print(f"✅ Loaded cog: {cog}")
        except Exception as e:
            print(f"❌ Failed to load cog {cog}: {e}")
            traceback.print_exc()

@bot.event
async def on_ready():
    """Called when the bot is connected and ready."""
    if not bot.is_ready_once:
        # --- Command Sync (FORCED SYNC TO YOUR GUILD) ---
        try:
            guild_object = discord.Object(id=TEST_GUILD_ID)
            await bot.tree.sync(guild=guild_object)
            print(f"✅ Slash commands synced to Guild ID: {TEST_GUILD_ID}")
        except Exception as e:
            print(f"❌ FATAL ERROR: Could not sync slash commands: {e}")

        print(f"Logged in as {bot.user} ({bot.user.id})")
        print("Bot is fully ready.")
        bot.is_ready_once = True


# --- ASYNCIO EXECUTION BLOCK ---
async def main():
    if not TOKEN:
        print("❌ FATAL ERROR: DISCORD_TOKEN is not set. Check your .env file.")
        return

    print("✅ Token loaded successfully.")
    print("⏳ Starting bot with asyncio...")

    try:
        # Use async with for clean startup/shutdown
        async with bot:
            await bot.start(TOKEN)
    except Exception as e:
         print(f"❌ FATAL ERROR during bot startup: {e}")
         return


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
