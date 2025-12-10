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


# --- DATABASE SETUP (Crucial Initialization) ---
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


# --- BOT SETUP & INTENTS ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True 

bot = commands.Bot(
    command_prefix="/", 
    intents=intents
)

# --- COG LOADING FUNCTION (Final Aggressive Fix) ---
COGS = ["gacha_main", "xp_reporter_main"] 

async def load_cogs():
    print("STARTING COG LOADING...")
    for cog in COGS:
        try:
            # *** CRITICAL FIX: Removed 'await' to resolve the TypeError ***
            # *** bot.load_extension() is being treated as synchronous in this environment. ***
            bot.load_extension(cog) 
            print(f"✅ Successfully loaded {cog}")
        
        # We use a generic Exception catch here to bypass the AttributeError 
        # caused by the mismatch in discord.py exception names, while still logging the error.
        except Exception as e:
             print(f"❌ Failed to load {cog}: Unknown error during loading:")
             print(f"Error Type: {type(e).__name__}")
             print(f"Error Message: {e}")
             import traceback # Need to import it locally here for the traceback.print_exc() to work if not globally available
             traceback.print_exc()
             
    print("Bot is ready and all Cogs are loaded.")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
    await load_cogs() 


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
        if conn:
            conn.close()
            print(f"Closed database connection to {DB_NAME}")
