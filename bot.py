# bot.py (FINAL VERSION - Guild Sync Forced, FIXED)
import os
import discord
import sqlite3
import traceback
import asyncio
from discord.ext import commands
from dotenv import load_dotenv
from bot_config import DB_NAME

# --- GUILD ID FOR INSTANT SLASH COMMAND SYNC ---
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
bot.is_ready_once = False  # Prevent double-sync

# --- CORRECT setup_hook (NO decorator!) ---
async def setup_hook():
    print("⏳ Loading cogs asynchronously...")
    for cog in COGS:
        try:
            await bot.load_extension(cog)
            print(f"✅ Loaded cog: {cog}")
        except Exception as e:
            print(f"❌ Failed to load cog {cog}: {e}")
            traceback.print_exc()

bot.setup_hook = setup_hook  # <-- THIS LINE MATTERS

# --- READY EVENT ---
@bot.event
async def on_ready():
    if not bot.is_ready_once:
        try:
            guild_object = discord.Object(id=TEST_GUILD_ID)
            synced = await bot.tree.sync(guild=guild_object)
            print(f"✅ Synced {len(synced)} slash command(s) to guild {TEST_GUILD_ID}")
        except Exception as e:
            print(f"❌ FATAL ERROR: Could not sync slash commands: {e}")

        print(f"🤖 Logged in as {bot.user} ({bot.user.id})")
        print("🚀 Bot is fully ready.")
        bot.is_ready_once = True

# --- ASYNCIO EXECUTION ---
async def main():
    if not TOKEN:
        print("❌ FATAL ERROR: DISCORD_TOKEN is not set.")
        return

    print("✅ Token loaded successfully.")
    print("⏳ Starting bot...")

    try:
        async with bot:
            await bot.start(TOKEN)
    except Exception as e:
        print(f"❌ FATAL ERROR during bot startup: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user.")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
