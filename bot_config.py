# bot_config.py (FIXED and Updated for lists)

# --- Channel Lists (Use lists for multiple channels) ---
# List all channels where XP submissions are allowed.
INPUT_CHANNEL_IDS = [
    1378229313824096336, # Your original INPUT_CHANNEL_ID is now in a list
] 

# List all channels where the approved XP messages are posted.
OUTPUT_CHANNEL_IDS = [
    1440000428027678741, # Your original OUTPUT_CHANNEL_ID is now in a list
]

# GACHA CHANNEL can remain a single ID (for the Gacha Cog's simple check)
GACHA_CHANNEL_ID = 1446983257487966350 

# --- Role and DB Configuration ---
SUBMISSION_APPROVER_ROLE_ID = 1425411791894220930
MODERATOR_ROLE_ID = 1425411621651611659

DB_NAME = "pity_data.db"