# bot.py — FINAL (Slash Commands FIXED, Guild Sync Forced)

import os
import discord
import sqlite3
import traceback
import asyncio
from discord.ext import commands
from dotenv import load_dotenv
from bot_config import DB_NAME

# =========================================================
# 🔧 TEST SERVER ID (ONLY this server gets instant slash cmds)
# =========================================================
TEST_GUILD_ID = 1357263087069167706  # ← CHANGE when needed

# =========================================================
# 🔐 Load token
# =========================================================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# =========================================================
# 🗄️ Database setup
# =========================================================
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
        print(f"❌ DATABASE ERROR: {e}")
        exit(1)
    finally:
        conn.close()

init_db()

# =========================================================
# 🤖 Bot setup
# =========================================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="$$", intents=intents)

# =========================================================
# 🧪 TEST SLASH COMMAND (CONFIRMS EVERYTHING WORKS)
# =========================================================
@bot.tree.command(name="ping", description="Test slash command")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("pong 🏓")

# =========================================================
# 📦 Cogs
# =========================================================
COGS = [
    "gacha_main",
    "xp_reporter_main"
]

# =========================================================
# 🔁 Load cogs BEFORE syncing commands
# =========================================================
@bot.event
async def setup_hook():
    print("⏳ Loading cogs asynchronously...")
    for cog in COGS:
        try:
            await bot.load_extension(cog)
            print(f"✅ Loaded cog: {cog}")
        except Exception as e:
            print(f"❌ Failed to load cog {cog}: {e}")
            traceback.print_exc()

# =========================================================
# 🚀 Ready event → FORCE slash command sync
# =========================================================
@bot.event
async def on_ready():
    guild = discord.Object(id=TEST_GUILD_ID)

    try:
        print(f"🔄 Syncing slash commands to guild {TEST_GUILD_ID}")

        # ⭐ THE CRITICAL FIX ⭐
        bot.tree.copy_global_to(guild=guild)

        synced = await bot.tree.sync(guild=guild)
        print(f"✅ Synced {len(synced)} slash command(s)")

    except Exception as e:
        print(f"❌ SLASH SYNC FAILED: {e}")

    print(f"🤖 Logged in as {bot.user} ({bot.user.id})")
    print("🚀 Bot is fully ready.")

# =========================================================
# ▶️ Start bot
# =========================================================
async def main():
    if not TOKEN:
        print("❌ DISCORD_TOKEN missing in .env")
        return

    print("✅ Token loaded successfully.")
    print("⏳ Starting bot...")

    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user.")
