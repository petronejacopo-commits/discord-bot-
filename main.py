import discord
import os
import asyncio
import logging
from dotenv import load_dotenv

from database import db
from welcomer import setup_welcomer
from ticket import setup_ticket, start_cleanup_task, TicketControlView
from settings import setup_settings

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BrotherhoodOrigins")

class BrotherhoodBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.guilds = True
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = discord.app_commands.CommandTree(self)

    async def setup_hook(self):
        # Initialize database
        await db.connect()

        # Load setups
        setup_ticket(self)
        setup_settings(self)
        setup_welcomer(self)

    async def on_ready(self):
        logger.info(f"Logged in as {self.user.name} ({self.user.id})")

        # Start cleanup task
        self.loop.create_task(start_cleanup_task(self))

        # Sync global commands
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} slash commands globally")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")

        # Restore views for all active tickets
        try:
            active_tickets = await db.get_active_tickets()
            restored_count = 0
            for ticket in active_tickets:
                channel_id = ticket["channel_id"]
                owner_id = ticket["owner_id"]
                category = ticket["category"]
                priority = ticket["priority"]

                # Check if channel exists to avoid adding views to deleted channels
                channel = self.get_channel(channel_id)
                if channel:
                    view = TicketControlView(self, owner_id, channel_id, category, priority)

                    assigned_to = ticket.get("assigned_to")
                    if assigned_to:
                        # Update view UI elements if it's assigned
                        view.assign_btn.label = "Rilascia"
                        view.assign_btn.emoji = "🔄"
                        view.assign_btn.style = discord.ButtonStyle.secondary

                    self.add_view(view, message_id=None) # message_id none listens to custom ids system-wide
                    restored_count += 1
                else:
                    logger.warning(f"Ticket channel {channel_id} not found during restore, might have been deleted while offline.")
                    # Optionally mark it as closed if channel is deleted
                    # await db.close_ticket(channel_id)

            logger.info(f"Restored TicketControlView for {restored_count} active tickets.")
        except Exception as e:
            logger.error(f"Failed to restore ticket views: {e}")


def main():
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN")

    if not token or token == "your_discord_bot_token_here":
        logger.error("DISCORD_TOKEN environment variable not set or is default. Please configure .env file.")
        return

    bot = BrotherhoodBot()
    bot.run(token)


if __name__ == "__main__":
    main()
