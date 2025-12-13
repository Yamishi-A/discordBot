# xp_reporter_main.py (REFINED VERSION)
# Cleaned, modular, scalable, same behavior

import discord
import re
import math
import logging
import traceback
from discord.ext import commands
from bot_config import INPUT_CHANNEL_IDS, OUTPUT_CHANNEL_IDS, SUBMISSION_APPROVER_ROLE_IDS

# --------------------------------------------------
# LOGGING
# --------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("xp_reporter")

# --------------------------------------------------
# CONSTANTS
# --------------------------------------------------
EMOJI_STR1 = "⭐"
BASE_CROWNS = 500

# --------------------------------------------------
# TRAINING TIERS (DATA-DRIVEN)
# --------------------------------------------------
TRAINING_TIERS = [
    (1, 10, 100, 1),
    (11, 20, 150, 2),
    (21, 30, 200, 3),
]

def get_training_tier_data(level: int) -> dict:
    for min_lvl, max_lvl, xp, tier in TRAINING_TIERS:
        if min_lvl <= level <= max_lvl:
            return {"base_xp": xp, "tier": tier}
    return {"base_xp": 100, "tier": 1}

# --------------------------------------------------
# ACTIVITIES
# --------------------------------------------------
ACTIVITY_MULTIPLIERS = {
    "troll mission": 1.0,
    "solo training": 1.0,
    "afk farm i": 1.0,
    "afk farm ii": 1.0,
    "afk farm iii": 1.15,
}

APPROVED_ACTIVITIES = set(ACTIVITY_MULTIPLIERS.keys())

# --------------------------------------------------
# CALCULATION HELPERS
# --------------------------------------------------

def calculate_xp(base_xp: int, base_multiplier: float, xp_boost: float):
    total_multiplier = base_multiplier * (1 + xp_boost)
    return math.floor(base_xp * total_multiplier), total_multiplier


def calculate_crowns(activity: str, crowns_boost: float):
    if activity != "troll mission":
        return 0
    return int(BASE_CROWNS * (1 + crowns_boost))


def calculate_rift_tokens(activity: str, training_tier: int):
    if activity == "troll mission":
        return training_tier
    return 0

# --------------------------------------------------
# COG
# --------------------------------------------------
class XPReporterCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._cached_mod_ping = None

    # --------------------------------------------------
    # PARSER
    # --------------------------------------------------
    def _parse_xp_submission(self, message):
        content = message.content.strip()
        data = {}

        try:
            data['name'] = re.search(
                r"\*\*Character Name\(s\):\*\*\s*(.+)",
                content, re.IGNORECASE
            ).group(1).strip()

            data['level'] = int(re.search(
                r"\*\*Character Level:\*\*\s*(\d+)",
                content, re.IGNORECASE
            ).group(1))

            data['progression'] = re.search(
                r"\*\*Type of Progression:\*\*(.*?)(?=\*\*|\Z)",
                content, re.IGNORECASE | re.DOTALL
            ).group(1).strip()

            xp_boost = re.search(r"\*\*Boost\(s\) for XP:\*\*\s*(\d+)%", content)
            crowns_boost = re.search(r"\*\*Boost\(s\) for Crowns:\*\*\s*(\d+)%", content)

            data['xp_boost'] = int(xp_boost.group(1)) / 100 if xp_boost else 0.0
            data['crowns_boost'] = int(crowns_boost.group(1)) / 100 if crowns_boost else 0.0

        except Exception:
            return {"valid": False, "reason": "Format Error"}

        data['progression_key'] = data['progression'].lower().strip()
        data['valid'] = True
        return data

    # --------------------------------------------------
    # LISTENER
    # --------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or message.channel.id not in INPUT_CHANNEL_IDS:
            return

        if not message.content.lower().startswith("**character name(s):**"):
            return

        data = self._parse_xp_submission(message)

        if not data.get('valid'):
            await message.add_reaction('❌')
            await message.channel.send(
                f"{message.author.mention}, submission format error. Please follow the template exactly.",
                delete_after=15
            )
            log.warning("Submission parse failure from %s", message.author)
            return

        # --------------------------------------------------
        # ACTIVITY VALIDATION
        # --------------------------------------------------
        if data['progression_key'] not in APPROVED_ACTIVITIES:
            await message.add_reaction('❌')

            if self._cached_mod_ping is None:
                self._cached_mod_ping = " ".join(
                    role.mention
                    for rid in SUBMISSION_APPROVER_ROLE_IDS
                    if (role := message.guild.get_role(rid))
                )

            embed = discord.Embed(
                title="🚫 Submission Denied",
                description=(
                    f"{message.author.mention}, **{data['progression']}** is not auto-approved.\n\n"
                    f"Approved activities: {', '.join(a.title() for a in APPROVED_ACTIVITIES)}\n\n"
                    f"Manual review required: {self._cached_mod_ping}"
                ),
                color=discord.Color.red()
            )

            await message.channel.send(embed=embed)
            log.info("Unknown activity denied: %s", data['progression'])
            return

        # --------------------------------------------------
        # PROCESSING
        # --------------------------------------------------
        try:
            tier_data = get_training_tier_data(data['level'])
            base_multiplier = ACTIVITY_MULTIPLIERS[data['progression_key']]

            final_xp, total_multiplier = calculate_xp(
                tier_data['base_xp'], base_multiplier, data['xp_boost']
            )

            final_crowns = calculate_crowns(
                data['progression_key'], data['crowns_boost']
            )

            rift_tokens = calculate_rift_tokens(
                data['progression_key'], tier_data['tier']
            )

            gains = [f"{final_xp} XP"]
            if final_crowns > 0:
                gains.append(f"{final_crowns} Crowns")
            if rift_tokens > 0:
                gains.append(f"{rift_tokens} Rift Tokens")

            # Channel mapping
            try:
                idx = INPUT_CHANNEL_IDS.index(message.channel.id)
                output_channel = self.bot.get_channel(OUTPUT_CHANNEL_IDS[idx])
            except Exception:
                output_channel = message.channel

            await message.add_reaction('✅')

            embed = discord.Embed(
                title=f"✅ Progression Logged: {data['progression'].title()}",
                description=f"Submitted by {message.author.mention}",
                color=discord.Color.green()
            )

            embed.add_field(name="Character(s)", value=data['name'], inline=True)
            embed.add_field(name="Level", value=data['level'], inline=True)
            embed.add_field(name="Training Tier", value=f"TT{tier_data['tier']}", inline=True)

            embed.add_field(
                name="Multipliers",
                value=(
                    f"Activity: `{base_multiplier:.2f}x`\n"
                    f"XP Boost: `{data['xp_boost']*100:.0f}%`\n"
                    f"Crowns Boost: `{data['crowns_boost']*100:.0f}%`"
                ),
                inline=False
            )

            embed.add_field(
                name=f"{EMOJI_STR1} Total Gains",
                value=f"**{', '.join(gains)}**",
                inline=False
            )

            embed.set_footer(
                text=f"Base XP: {tier_data['base_xp']} | Final Multiplier: {total_multiplier:.2f}x"
            )

            await output_channel.send(embed=embed)
            log.info("Submission processed successfully for %s", message.author)

        except Exception:
            log.error("Fatal processing error", exc_info=True)
            await message.add_reaction('❓')
            await message.channel.send(
                f"❌ Internal error while processing submission ({message.author.mention})"
            )

# --------------------------------------------------
# SETUP
# --------------------------------------------------
async def setup(bot):
    await bot.add_cog(XPReporterCog(bot))
