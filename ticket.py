import discord
import asyncio
import datetime
import html
import os
import logging
from database import db

logger = logging.getLogger(__name__)

# Helper functions
def priority_stars(priority: str) -> str:
    stars = {
        "bassa": "⭐☆☆☆",
        "media": "⭐⭐☆☆",
        "alta": "⭐⭐⭐☆",
        "urgente": "⭐⭐⭐⭐"
    }
    return stars.get(priority.lower(), "⭐☆☆☆")

def priority_color(priority: str) -> int:
    colors = {
        "bassa": 0x2ECC71,    # Green
        "media": 0xF1C40F,    # Yellow
        "alta": 0xE67E22,     # Orange
        "urgente": 0xE74C3C   # Red
    }
    return colors.get(priority.lower(), 0x3498DB)


async def generate_transcript(channel: discord.TextChannel) -> str:
    messages = []
    async for message in channel.history(limit=None, oldest_first=True):
        messages.append(message)

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Transcript - {html.escape(channel.name)}</title>
        <style>
            body {{
                background-color: #36393f;
                color: #dcddde;
                font-family: 'Whitney', 'Helvetica Neue', Helvetica, Arial, sans-serif;
                padding: 20px;
            }}
            .message {{
                display: flex;
                margin-bottom: 20px;
            }}
            .avatar {{
                width: 40px;
                height: 40px;
                border-radius: 50%;
                margin-right: 15px;
            }}
            .content-box {{
                display: flex;
                flex-direction: column;
            }}
            .header {{
                display: flex;
                align-items: baseline;
                margin-bottom: 5px;
            }}
            .username {{
                font-weight: bold;
                color: #ffffff;
                margin-right: 10px;
            }}
            .timestamp {{
                font-size: 0.75em;
                color: #72767d;
            }}
            .text {{
                white-space: pre-wrap;
            }}
        </style>
    </head>
    <body>
        <h2>Transcript: {html.escape(channel.name)}</h2>
    """

    for msg in messages:
        content = html.escape(msg.content)
        author_name = html.escape(msg.author.display_name)
        avatar_url = msg.author.display_avatar.url if msg.author.display_avatar else ""
        timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")

        html_content += f"""
        <div class="message">
            <img class="avatar" src="{avatar_url}" alt="Avatar">
            <div class="content-box">
                <div class="header">
                    <span class="username">{author_name}</span>
                    <span class="timestamp">{timestamp}</span>
                </div>
                <div class="text">{content}</div>
            </div>
        </div>
        """

    html_content += """
    </body>
    </html>
    """
    return html_content


class TicketPanelView(discord.ui.View):
    def __init__(self, bot: discord.Client):
        super().__init__(timeout=None)
        self.bot = bot
        self.category_select = discord.ui.Select(
            placeholder="Caricamento categorie...",
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(label="Loading")],
            custom_id="ticket_panel_select"
        )
        self.category_select.callback = self.select_category
        self.add_item(self.category_select)

    async def update_categories(self, guild_id: int):
        categories = await db.get_categories(guild_id)
        if not categories:
            self.category_select.placeholder = "Nessuna categoria disponibile"
            self.category_select.disabled = True
            self.category_select.options = [discord.SelectOption(label="None", value="none")]
        else:
            self.category_select.placeholder = "Seleziona una categoria"
            self.category_select.disabled = False
            self.category_select.options = [
                discord.SelectOption(
                    label=c["name"],
                    emoji=c["emoji"] if c["emoji"] else None,
                    description=c["description"]
                ) for c in categories
            ]

    async def select_category(self, interaction: discord.Interaction):
        try:
            guild_id = interaction.guild_id
            user = interaction.user
            category_name = self.category_select.values[0]

            # Reset select component state for next use visually
            await interaction.response.defer(ephemeral=True)

            ticket_limit_str = await db.get_config(guild_id, "ticket_limit", "1")
            try:
                ticket_limit = int(ticket_limit_str)
            except ValueError:
                ticket_limit = 1

            # Preliminary check to prevent Discord rate-limiting and channel spam
            current_active = await db.get_ticket_count(guild_id, user.id)
            if current_active >= ticket_limit:
                await interaction.followup.send(f"Hai già raggiunto il limite di {ticket_limit} ticket aperti.", ephemeral=True)
                return

            ticket_category_id = await db.get_config(guild_id, "ticket_category")
            if not ticket_category_id:
                await interaction.followup.send("Errore: La categoria Discord per i ticket non è configurata.", ephemeral=True)
                return

            priority_enabled = (await db.get_config(guild_id, "ticket_priority_enabled", "false")).lower() == "true"
            default_priority = await db.get_config(guild_id, "ticket_default_priority", "media")

            selected_priority = default_priority

            if priority_enabled:
                class PrioritySelectView(discord.ui.View):
                    def __init__(self, default_pri: str):
                        super().__init__(timeout=60)
                        self.value = default_pri

                        options = [
                            discord.SelectOption(label="Bassa", description="⭐", value="bassa", default=(default_pri=="bassa")),
                            discord.SelectOption(label="Media", description="⭐⭐", value="media", default=(default_pri=="media")),
                            discord.SelectOption(label="Alta", description="⭐⭐⭐", value="alta", default=(default_pri=="alta")),
                            discord.SelectOption(label="Urgente", description="⭐⭐⭐⭐", value="urgente", default=(default_pri=="urgente"))
                        ]

                        self.select = discord.ui.Select(placeholder="Seleziona la priorità", options=options)
                        self.select.callback = self.on_select
                        self.add_item(self.select)

                    async def on_select(self, inter: discord.Interaction):
                        self.value = self.select.values[0]
                        await inter.response.defer()
                        self.stop()

                pri_view = PrioritySelectView(default_priority)
                msg = await interaction.followup.send("Seleziona la priorità del ticket:", view=pri_view, ephemeral=True, wait=True)
                await pri_view.wait()
                if pri_view.value:
                    selected_priority = pri_view.value
                await msg.delete()

            discord_category = interaction.guild.get_channel(int(ticket_category_id))
            if not discord_category or not isinstance(discord_category, discord.CategoryChannel):
                await interaction.followup.send("Errore: Categoria Discord configurata non valida.", ephemeral=True)
                return

            staff_role_id = await db.get_config(guild_id, "ticket_staff_role")
            staff_role = interaction.guild.get_role(int(staff_role_id)) if staff_role_id else None

            # Generate generic channel name (will be renamed if DB limits pass, but needed for permissions)
            clean_category = "".join([c for c in category_name if c.isalnum() or c.isspace()]).strip()
            clean_user = "".join([c for c in user.display_name if c.isalnum() or c.isspace()]).strip()
            channel_name = f"🎫・{clean_category}-{clean_user}"

            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                user: discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True)
            }
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(
                    read_messages=True, send_messages=True, read_message_history=True, manage_messages=True
                )

            # Atomically attempt to create ticket in DB with limits.
            # We must create the channel first to get the channel_id for the database
            channel = await interaction.guild.create_text_channel(
                name=channel_name,
                category=discord_category,
                overwrites=overwrites
            )

            success = await db.create_ticket(guild_id, channel.id, user.id, category_name, selected_priority, ticket_limit)
            if not success:
                # Cleanup channel if limit reached
                await channel.delete()
                await interaction.followup.send(f"Hai raggiunto il limite massimo di ticket aperti ({ticket_limit}).", ephemeral=True)
                return

            panel_color = await db.get_config(guild_id, "ticket_panel_color", "0x3498DB")
            try:
                embed_color = int(panel_color.replace("#", "0x"), 16)
            except ValueError:
                embed_color = 0x3498DB

            lore_text = await db.get_config(guild_id, "ticket_lore_text", "Descrivi il tuo problema e uno staffer ti assisterà a breve.")
            footer_text = await db.get_config(guild_id, "ticket_footer_text", "Brotherhood Origins · Sistema Ticket")

            # Fetch custom category welcome message if exists
            categories_data = await db.get_categories(guild_id)
            cat_data = next((c for c in categories_data if c["name"] == category_name), None)
            if cat_data and cat_data.get("welcome_message"):
                 lore_text = cat_data["welcome_message"]

            embed = discord.Embed(
                title=f"Ticket #{channel.id % 10000:04d} — {category_name}",
                description=lore_text,
                color=embed_color
            )
            embed.add_field(name="Stato", value="🟢 Aperto", inline=True)
            embed.add_field(name="Aperto da", value=user.mention, inline=True)
            embed.add_field(name="Assegnato a", value="— Nessuno —", inline=True)
            embed.set_footer(text=footer_text)

            control_view = TicketControlView(self.bot, user.id, channel.id, category_name, selected_priority)
            await channel.send(content=user.mention, embed=embed, view=control_view)

            await interaction.followup.send(f"Ticket creato: {channel.mention}", ephemeral=True)

        except Exception as e:
            logger.error(f"Error creating ticket: {e}")
            try:
                await interaction.followup.send("Si è verificato un errore durante la creazione del ticket.", ephemeral=True)
            except:
                pass


class TicketControlView(discord.ui.View):
    def __init__(self, bot: discord.Client, owner_id: int, channel_id: int, category: str, priority: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.owner_id = owner_id
        self.channel_id = channel_id
        self.category = category
        self.priority = priority

        self.btn_close = discord.ui.Button(label="Chiudi", emoji="🔒", style=discord.ButtonStyle.secondary, row=0, custom_id=f"tc_close_{channel_id}")
        self.btn_close.callback = self.close_btn
        self.add_item(self.btn_close)

        self.btn_assign = discord.ui.Button(label="Prendi in carico", emoji="🙋", style=discord.ButtonStyle.primary, row=0, custom_id=f"tc_assign_{channel_id}")
        self.btn_assign.callback = self.assign_btn
        self.add_item(self.btn_assign)

        self.btn_priority = discord.ui.Button(label="Priorità", emoji="⭐", style=discord.ButtonStyle.secondary, row=0, custom_id=f"tc_prio_{channel_id}")
        self.btn_priority.callback = self.priority_btn
        self.add_item(self.btn_priority)

        self.btn_add_user = discord.ui.Button(label="Aggiungi utente", emoji="➕", style=discord.ButtonStyle.secondary, row=1, custom_id=f"tc_add_{channel_id}")
        self.btn_add_user.callback = self.add_user_btn
        self.add_item(self.btn_add_user)

        self.btn_rem_user = discord.ui.Button(label="Rimuovi utente", emoji="➖", style=discord.ButtonStyle.secondary, row=1, custom_id=f"tc_rem_{channel_id}")
        self.btn_rem_user.callback = self.remove_user_btn
        self.add_item(self.btn_rem_user)

        self.btn_transcript = discord.ui.Button(label="Trascrizione", emoji="📄", style=discord.ButtonStyle.secondary, row=1, custom_id=f"tc_trans_{channel_id}")
        self.btn_transcript.callback = self.transcript_btn
        self.add_item(self.btn_transcript)

    async def is_staff(self, interaction: discord.Interaction) -> bool:
        staff_role_id = await db.get_config(interaction.guild_id, "ticket_staff_role")
        if staff_role_id:
            role = interaction.guild.get_role(int(staff_role_id))
            if role in interaction.user.roles:
                return True
        return interaction.user.guild_permissions.administrator

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        is_stf = await self.is_staff(interaction)
        if not is_stf:
            await interaction.response.send_message("Non hai i permessi per interagire con questo ticket.", ephemeral=True)
            return False
        return True

    async def close_btn(self, interaction: discord.Interaction):
        try:
            class ConfirmClose(discord.ui.View):
                def __init__(self, tc_view: TicketControlView):
                    super().__init__(timeout=60)
                    self.tc_view = tc_view

                @discord.ui.button(label="Conferma", style=discord.ButtonStyle.danger)
                async def confirm(self, inter: discord.Interaction, btn: discord.ui.Button):
                    try:
                        await inter.response.send_message("Chiusura del ticket in corso...", ephemeral=True)
                        await self.tc_view.execute_close(inter.channel, inter.guild)
                        self.stop()
                    except Exception as e:
                        logger.error(f"Error confirm close: {e}")
                        try: await inter.response.send_message("Si è verificato un errore.", ephemeral=True)
                        except: pass

                @discord.ui.button(label="Annulla", style=discord.ButtonStyle.secondary)
                async def cancel(self, inter: discord.Interaction, btn: discord.ui.Button):
                    await inter.response.send_message("Operazione annullata.", ephemeral=True)
                    self.stop()

            await interaction.response.send_message("Sei sicuro di voler chiudere questo ticket?", view=ConfirmClose(self), ephemeral=True)
        except Exception as e:
            logger.error(f"Error close btn: {e}")
            await interaction.response.send_message("Si è verificato un errore generico.", ephemeral=True)

    async def execute_close(self, channel: discord.TextChannel, guild: discord.Guild):
        try:
            transcript = await generate_transcript(channel)
            os.makedirs("transcripts", exist_ok=True)

            # Sanitize channel name for file
            safe_name = "".join([c for c in channel.name if c.isalnum() or c in ('-', '_')]).strip()
            file_path = f"transcripts/ticket_{channel.id}_{safe_name}.html"

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(transcript)

            await db.add_transcript_log(guild.id, channel.id, file_path)

            log_channel_id = await db.get_config(guild.id, "ticket_log_channel")
            if log_channel_id:
                log_channel = guild.get_channel(int(log_channel_id))
                if log_channel:
                    await log_channel.send(
                        content=f"Ticket Chiuso: {channel.name}",
                        file=discord.File(file_path)
                    )

            await db.close_ticket(channel.id)
            await asyncio.sleep(5)
            await channel.delete()
        except Exception as e:
            logger.error(f"Error executing close: {e}")

    async def assign_btn(self, interaction: discord.Interaction):
        try:
            if not await self.is_staff(interaction):
                await interaction.response.send_message("Solo lo staff può prendere in carico i ticket.", ephemeral=True)
                return

            ticket_data = await db.get_ticket_by_channel(self.channel_id)
            if not ticket_data:
                await interaction.response.send_message("Errore: Ticket non trovato nel database.", ephemeral=True)
                return

            assigned_to = ticket_data.get("assigned_to")

            embed = interaction.message.embeds[0]

            if assigned_to:
                if assigned_to != interaction.user.id:
                    await interaction.response.send_message("Ticket già assegnato ad un altro membro dello staff.", ephemeral=True)
                    return
                else:
                    # Release
                    await db.release_ticket(self.channel_id)
                    self.btn_assign.label = "Prendi in carico"
                    self.btn_assign.emoji = "🙋"
                    self.btn_assign.style = discord.ButtonStyle.primary

                    embed.set_field_at(0, name="Stato", value="🟢 Aperto", inline=True)
                    embed.set_field_at(2, name="Assegnato a", value="— Nessuno —", inline=True)

                    await interaction.response.edit_message(embed=embed, view=self)
            else:
                # Assign
                await db.assign_ticket(self.channel_id, interaction.user.id)
                self.btn_assign.label = "Rilascia"
                self.btn_assign.emoji = "🔄"
                self.btn_assign.style = discord.ButtonStyle.secondary

                embed.set_field_at(0, name="Stato", value="🟡 In elaborazione", inline=True)
                embed.set_field_at(2, name="Assegnato a", value=interaction.user.mention, inline=True)

                await interaction.response.edit_message(embed=embed, view=self)
        except Exception as e:
            logger.error(f"Error assigning ticket: {e}")
            await interaction.response.send_message("Si è verificato un errore generico.", ephemeral=True)

    async def priority_btn(self, interaction: discord.Interaction):
        try:
            if not await self.is_staff(interaction):
                await interaction.response.send_message("Solo lo staff può modificare la priorità.", ephemeral=True)
                return

            class PriorityUpdateView(discord.ui.View):
                def __init__(self, tc_view: TicketControlView):
                    super().__init__(timeout=60)
                    self.tc_view = tc_view

                    options = [
                        discord.SelectOption(label="Bassa", description="⭐", value="bassa", default=(tc_view.priority=="bassa")),
                        discord.SelectOption(label="Media", description="⭐⭐", value="media", default=(tc_view.priority=="media")),
                        discord.SelectOption(label="Alta", description="⭐⭐⭐", value="alta", default=(tc_view.priority=="alta")),
                        discord.SelectOption(label="Urgente", description="⭐⭐⭐⭐", value="urgente", default=(tc_view.priority=="urgente"))
                    ]

                    self.select = discord.ui.Select(placeholder="Modifica priorità", options=options)
                    self.select.callback = self.on_select
                    self.add_item(self.select)

                async def on_select(self, inter: discord.Interaction):
                    try:
                        new_pri = self.select.values[0]
                        self.tc_view.priority = new_pri
                        await db.update_ticket_priority(self.tc_view.channel_id, new_pri)

                        color = priority_color(new_pri)
                        embed = discord.Embed(
                            title="Priorità Aggiornata",
                            description=f"La priorità del ticket è stata aggiornata a **{new_pri.capitalize()}**.",
                            color=color
                        )
                        await inter.response.send_message(embed=embed, ephemeral=True)
                        self.stop()
                    except Exception as e:
                        logger.error(f"Error priority: {e}")
                        await inter.response.send_message("Errore generico.", ephemeral=True)

            await interaction.response.send_message("Seleziona la nuova priorità:", view=PriorityUpdateView(self), ephemeral=True)
        except Exception as e:
            logger.error(f"Error priority button: {e}")
            await interaction.response.send_message("Si è verificato un errore generico.", ephemeral=True)


    async def add_user_btn(self, interaction: discord.Interaction):
        try:
            if not await self.is_staff(interaction):
                await interaction.response.send_message("Solo lo staff può aggiungere utenti.", ephemeral=True)
                return

            class AddUserView(discord.ui.View):
                def __init__(self, channel: discord.TextChannel):
                    super().__init__(timeout=60)
                    self.channel = channel
                    self.select = discord.ui.UserSelect(placeholder="Seleziona l'utente da aggiungere", max_values=1)
                    self.select.callback = self.on_select
                    self.add_item(self.select)

                async def on_select(self, inter: discord.Interaction):
                    try:
                        user = self.select.values[0]
                        await self.channel.set_permissions(user, read_messages=True, send_messages=True, read_message_history=True)
                        await inter.response.send_message(f"Permessi aggiunti per {user.mention}.", ephemeral=True)
                        self.stop()
                    except Exception as e:
                        logger.error(f"Error in add_user: {e}")
                        await inter.response.send_message("Errore generico.", ephemeral=True)

            await interaction.response.send_message("Seleziona chi vuoi aggiungere:", view=AddUserView(interaction.channel), ephemeral=True)
        except Exception as e:
            logger.error(f"Error add_user_btn: {e}")
            await interaction.response.send_message("Si è verificato un errore generico.", ephemeral=True)

    async def remove_user_btn(self, interaction: discord.Interaction):
        try:
            if not await self.is_staff(interaction):
                await interaction.response.send_message("Solo lo staff può rimuovere utenti.", ephemeral=True)
                return

            class RemoveUserView(discord.ui.View):
                def __init__(self, channel: discord.TextChannel):
                    super().__init__(timeout=60)
                    self.channel = channel
                    self.select = discord.ui.UserSelect(placeholder="Seleziona l'utente da rimuovere", max_values=1)
                    self.select.callback = self.on_select
                    self.add_item(self.select)

                async def on_select(self, inter: discord.Interaction):
                    try:
                        user = self.select.values[0]
                        await self.channel.set_permissions(user, overwrite=None)
                        await inter.response.send_message(f"Permessi rimossi per {user.mention}.", ephemeral=True)
                        self.stop()
                    except Exception as e:
                        logger.error(f"Error remove_user: {e}")
                        await inter.response.send_message("Errore generico.", ephemeral=True)

            await interaction.response.send_message("Seleziona chi vuoi rimuovere:", view=RemoveUserView(interaction.channel), ephemeral=True)
        except Exception as e:
            logger.error(f"Error remove_user_btn: {e}")
            await interaction.response.send_message("Si è verificato un errore generico.", ephemeral=True)

    async def transcript_btn(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            transcript = await generate_transcript(interaction.channel)
            os.makedirs("transcripts", exist_ok=True)

            safe_name = "".join([c for c in interaction.channel.name if c.isalnum() or c in ('-', '_')]).strip()
            file_path = f"transcripts/manual_ticket_{interaction.channel.id}_{safe_name}.html"

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(transcript)

            await db.add_transcript_log(interaction.guild.id, interaction.channel.id, file_path)

            log_channel_id = await db.get_config(interaction.guild.id, "ticket_log_channel")
            if log_channel_id:
                log_channel = interaction.guild.get_channel(int(log_channel_id))
                if log_channel:
                    await log_channel.send(
                        content=f"Trascrizione manuale generata per: {interaction.channel.name}",
                        file=discord.File(file_path)
                    )

            await interaction.followup.send("Trascrizione salvata e inviata al canale log.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error saving transcript: {e}")
            await interaction.followup.send("Si è verificato un errore durante il salvataggio della trascrizione.", ephemeral=True)

async def send_ticket_panel(bot: discord.Client, channel: discord.TextChannel):
    guild_id = channel.guild.id
    show_status = (await db.get_config(guild_id, "ticket_panel_show_status", "false")).lower() == "true"

    panel_title = await db.get_config(guild_id, "ticket_panel_title", "Supporto Ticket")
    panel_desc = await db.get_config(guild_id, "ticket_panel_description", "Seleziona una categoria dal menu sottostante per aprire un ticket.")
    panel_color_hex = await db.get_config(guild_id, "ticket_panel_color", "0x3498DB")

    try:
        color = int(panel_color_hex.replace("#", "0x"), 16)
    except:
        color = 0x3498DB

    if show_status:
        staff_role_id = await db.get_config(guild_id, "ticket_staff_role")
        staff_online = 0
        if staff_role_id:
            role = channel.guild.get_role(int(staff_role_id))
            if role:
                staff_online = sum(1 for m in role.members if m.status != discord.Status.offline)

        avg_time = await db.get_avg_response_time(guild_id)

        status_line = f"🟢 Staff online: {staff_online}"
        if avg_time > 0:
            status_line += f" · ⏱ Risposta media: {int(avg_time)} min"

        panel_desc += f"\n\n{status_line}"

    embed = discord.Embed(title=panel_title, description=panel_desc, color=color)
    embed.set_footer(text="Brotherhood Origins · Sistema Ticket")

    view = TicketPanelView(bot)
    await view.update_categories(guild_id)

    msg = await channel.send(embed=embed, view=view)
    await db.set_config(guild_id, "ticket_panel_channel", str(channel.id))
    return msg


async def start_cleanup_task(bot: discord.Client):
    while not bot.is_closed():
        try:
            # We fetch distinct guilds that have ticket_auto_cleanup enabled
            # For simplicity, we just fetch all active tickets and check their guild config individually
            active_tickets = await db.get_active_tickets()

            for ticket in active_tickets:
                guild_id = ticket["guild_id"]
                auto_cleanup = (await db.get_config(guild_id, "ticket_auto_cleanup", "false")).lower() == "true"
                if not auto_cleanup:
                    continue

                max_age_days = int(await db.get_config(guild_id, "ticket_max_age_days", "7"))

                created_at_str = ticket["created_at"]
                if created_at_str:
                    try:
                        # Assuming created_at is standard SQLite ISO string format YYYY-MM-DD HH:MM:SS
                        created_at = datetime.datetime.strptime(created_at_str, "%Y-%m-%d %H:%M:%S")
                        now = datetime.datetime.utcnow()
                        if (now - created_at).days >= max_age_days:
                            channel_id = ticket["channel_id"]
                            channel = bot.get_channel(channel_id)

                            if channel:
                                transcript = await generate_transcript(channel)
                                os.makedirs("transcripts", exist_ok=True)

                                safe_name = "".join([c for c in channel.name if c.isalnum() or c in ('-', '_')]).strip()
                                file_path = f"transcripts/expired_ticket_{channel.id}_{safe_name}.html"

                                with open(file_path, "w", encoding="utf-8") as f:
                                    f.write(transcript)

                                await db.add_transcript_log(guild_id, channel.id, file_path)

                                log_channel_id = await db.get_config(guild_id, "ticket_log_channel")
                                if log_channel_id:
                                    log_channel = channel.guild.get_channel(int(log_channel_id))
                                    if log_channel:
                                        await log_channel.send(
                                            content=f"Ticket scaduto chiuso automaticamente: {channel.name}",
                                            file=discord.File(file_path)
                                        )
                                await channel.delete()

                            await db.close_ticket(channel_id)
                            logger.info(f"Ticket {channel_id} scaduto chiuso automaticamente.")
                    except Exception as e:
                        logger.error(f"Error during cleanup of ticket {ticket['channel_id']}: {e}")

        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")

        await asyncio.sleep(3600)

def setup_ticket(bot: discord.Client):
    bot.add_view(TicketPanelView(bot))
    # We don't add TicketControlView here because its items depend on dynamic channels.
    # It will be recovered in main.py during on_ready.
