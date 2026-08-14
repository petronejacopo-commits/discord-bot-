import discord
from discord import app_commands
import os
import sys
import time
import platform
import asyncio
import logging
from database import db
from ticket import send_ticket_panel, TicketPanelView, generate_transcript

logger = logging.getLogger(__name__)

def check_admin_access(interaction: discord.Interaction) -> bool:
    if interaction.user.guild_permissions.administrator:
        return True
    return False

async def async_check_admin_access(interaction: discord.Interaction) -> bool:
    if check_admin_access(interaction):
        return True
    return await db.is_authorized(interaction.guild_id, interaction.user.id)


class BackButton(discord.ui.Button):
    def __init__(self, main_view, label="Indietro", style=discord.ButtonStyle.secondary, row=4):
        super().__init__(label=label, style=style, row=row)
        self.main_view = main_view

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.edit_message(
                content=None,
                embed=self.main_view.original_embed,
                view=self.main_view
            )
        except Exception as e:
            logger.error(e)


# --- WELCOME MODULE ---
class WelcomeColorsModal(discord.ui.Modal, title='Colori Welcome Card'):
    bg1 = discord.ui.TextInput(label='Sfondo 1 (HEX)', placeholder='#1a1a2e', required=False)
    bg2 = discord.ui.TextInput(label='Sfondo 2 (HEX)', placeholder='#16213e', required=False)
    accent = discord.ui.TextInput(label='Colore Accento (HEX)', placeholder='#D4AF37', required=False)
    font = discord.ui.TextInput(label='Font', placeholder='Montserrat-Bold.ttf', required=False)
    logo = discord.ui.TextInput(label='URL Logo/Watermark', required=False)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if self.bg1.value: await db.set_config(interaction.guild_id, "bg_color1", self.bg1.value)
            if self.bg2.value: await db.set_config(interaction.guild_id, "bg_color2", self.bg2.value)
            if self.accent.value: await db.set_config(interaction.guild_id, "accent_color", self.accent.value)
            if self.font.value: await db.set_config(interaction.guild_id, "font", self.font.value)
            if self.logo.value: await db.set_config(interaction.guild_id, "logo_url", self.logo.value)
            await interaction.response.send_message("Colori e font aggiornati.", ephemeral=True)
        except Exception as e:
            logger.error(e)
            await interaction.response.send_message("Errore", ephemeral=True)

class WelcomeSettingsViewPage1(discord.ui.View):
    def __init__(self, main_view):
        super().__init__(timeout=None)
        self.main_view = main_view
        self.add_item(BackButton(main_view, row=4))

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="Canale di benvenuto", channel_types=[discord.ChannelType.text])
    async def select_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        try:
            await db.set_config(interaction.guild_id, "welcome_channel", str(select.values[0].id))
            await interaction.response.send_message(f"Canale impostato: {select.values[0].mention}", ephemeral=True)
        except Exception as e:
            logger.error(e)
            await interaction.response.send_message("Errore", ephemeral=True)

    @discord.ui.select(
        placeholder="Template Card",
        options=[
            discord.SelectOption(label="Dark Elegance", value="dark_elegance"),
            discord.SelectOption(label="Minecraft", value="minecraft"),
            discord.SelectOption(label="Corporate Blue", value="corporate_blue"),
            discord.SelectOption(label="Fantasy Purple", value="fantasy_purple")
        ]
    )
    async def select_template(self, interaction: discord.Interaction, select: discord.ui.Select):
        try:
            await db.set_config(interaction.guild_id, "welcome_template", select.values[0])
            await interaction.response.send_message(f"Template impostato: {select.values[0]}", ephemeral=True)
        except Exception as e:
            logger.error(e)
            await interaction.response.send_message("Errore", ephemeral=True)

    @discord.ui.button(label="Attiva/Disattiva Card Grafica", style=discord.ButtonStyle.secondary, row=2)
    async def toggle_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            current = (await db.get_config(interaction.guild_id, "welcome_use_card", "false")).lower() == "true"
            new_val = "false" if current else "true"
            await db.set_config(interaction.guild_id, "welcome_use_card", new_val)
            await interaction.response.send_message(f"Card grafica impostata su: {new_val}", ephemeral=True)
        except Exception as e:
            logger.error(e)
            await interaction.response.send_message("Errore", ephemeral=True)

    @discord.ui.button(label="Modifica Colori/Stili", style=discord.ButtonStyle.secondary, row=2)
    async def edit_colors(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.send_modal(WelcomeColorsModal())
        except Exception as e:
            logger.error(e)

    @discord.ui.button(label="Avanti ➡️", style=discord.ButtonStyle.primary, row=4)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(view=WelcomeSettingsViewPage2(self.main_view))


class WelcomeSettingsViewPage2(discord.ui.View):
    def __init__(self, main_view):
        super().__init__(timeout=None)
        self.main_view = main_view

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Ruolo da pingare al benvenuto")
    async def select_ping_role(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        try:
            await db.set_config(interaction.guild_id, "welcome_ping_role", str(select.values[0].id))
            await interaction.response.send_message("Ruolo ping impostato.", ephemeral=True)
        except Exception as e:
            logger.error(e)
            await interaction.response.send_message("Errore", ephemeral=True)

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Utente da pingare al benvenuto")
    async def select_ping_user(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        try:
            await db.set_config(interaction.guild_id, "welcome_ping_user", str(select.values[0].id))
            await interaction.response.send_message("Utente ping impostato.", ephemeral=True)
        except Exception as e:
            logger.error(e)
            await interaction.response.send_message("Errore", ephemeral=True)

    @discord.ui.button(label="⬅️ Indietro", style=discord.ButtonStyle.primary, row=2)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(view=WelcomeSettingsViewPage1(self.main_view))


# --- TICKET MODULE ---
class TicketLimitModal(discord.ui.Modal, title='Impostazioni Avanzate Ticket'):
    limit = discord.ui.TextInput(label='Limite ticket per utente', default='1')
    panel_desc = discord.ui.TextInput(label='Descrizione Pannello', style=discord.TextStyle.paragraph, required=False)
    panel_color = discord.ui.TextInput(label='Colore Pannello (HEX)', default='0x3498DB')
    panel_title = discord.ui.TextInput(label='Titolo Pannello', default='Supporto Ticket')
    max_age = discord.ui.TextInput(label='Giorni max validità (per Auto-cleanup)', default='7')

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await db.set_config(interaction.guild_id, "ticket_limit", self.limit.value)
            if self.panel_desc.value: await db.set_config(interaction.guild_id, "ticket_panel_description", self.panel_desc.value)
            await db.set_config(interaction.guild_id, "ticket_panel_color", self.panel_color.value)
            await db.set_config(interaction.guild_id, "ticket_panel_title", self.panel_title.value)
            await db.set_config(interaction.guild_id, "ticket_max_age_days", self.max_age.value)
            await interaction.response.send_message("Impostazioni ticket aggiornate.", ephemeral=True)
        except Exception as e:
            logger.error(e)
            await interaction.response.send_message("Errore", ephemeral=True)

class TicketTextModal(discord.ui.Modal, title='Testi Ticket'):
    lore_text = discord.ui.TextInput(label='Testo Lore Ticket (Embed Default)', style=discord.TextStyle.paragraph, required=False)
    footer = discord.ui.TextInput(label='Testo Footer Ticket', required=False)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if self.lore_text.value: await db.set_config(interaction.guild_id, "ticket_lore_text", self.lore_text.value)
            if self.footer.value: await db.set_config(interaction.guild_id, "ticket_footer_text", self.footer.value)
            await interaction.response.send_message("Testi ticket aggiornati.", ephemeral=True)
        except Exception as e:
            logger.error(e)
            await interaction.response.send_message("Errore", ephemeral=True)

class TicketSettingsViewPage1(discord.ui.View):
    def __init__(self, bot: discord.Client, main_view):
        super().__init__(timeout=None)
        self.bot = bot
        self.main_view = main_view
        self.add_item(BackButton(main_view, row=4))

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="Categoria Discord per Ticket", channel_types=[discord.ChannelType.category])
    async def select_category(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        try:
            await db.set_config(interaction.guild_id, "ticket_category", str(select.values[0].id))
            await interaction.response.send_message(f"Categoria ticket impostata.", ephemeral=True)
        except Exception as e:
            logger.error(e)
            await interaction.response.send_message("Errore", ephemeral=True)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Ruolo Staff Ticket")
    async def select_staff(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        try:
            await db.set_config(interaction.guild_id, "ticket_staff_role", str(select.values[0].id))
            await interaction.response.send_message(f"Ruolo staff impostato.", ephemeral=True)
        except Exception as e:
            logger.error(e)
            await interaction.response.send_message("Errore", ephemeral=True)

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="Canale Log (Trascrizioni)", channel_types=[discord.ChannelType.text])
    async def select_log(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        try:
            await db.set_config(interaction.guild_id, "ticket_log_channel", str(select.values[0].id))
            await interaction.response.send_message(f"Canale log impostato.", ephemeral=True)
        except Exception as e:
            logger.error(e)
            await interaction.response.send_message("Errore", ephemeral=True)

    @discord.ui.button(label="Limiti e UI", style=discord.ButtonStyle.secondary, row=3)
    async def extra_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.send_modal(TicketLimitModal())
        except Exception as e:
            logger.error(e)

    @discord.ui.button(label="Testi Embed", style=discord.ButtonStyle.secondary, row=3)
    async def text_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.send_modal(TicketTextModal())
        except Exception as e:
            logger.error(e)

    @discord.ui.button(label="Avanti ➡️", style=discord.ButtonStyle.primary, row=4)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(view=TicketSettingsViewPage2(self.bot, self.main_view))


class TicketSettingsViewPage2(discord.ui.View):
    def __init__(self, bot: discord.Client, main_view):
        super().__init__(timeout=None)
        self.bot = bot
        self.main_view = main_view

    @discord.ui.button(label="Toggle Status", style=discord.ButtonStyle.secondary, row=0)
    async def toggle_status(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            current = (await db.get_config(interaction.guild_id, "ticket_panel_show_status", "false")).lower() == "true"
            new_val = "false" if current else "true"
            await db.set_config(interaction.guild_id, "ticket_panel_show_status", new_val)
            await interaction.response.send_message(f"Status staff nel pannello: {new_val}", ephemeral=True)
        except Exception as e:
            logger.error(e)
            await interaction.response.send_message("Errore", ephemeral=True)

    @discord.ui.button(label="Toggle Priorità", style=discord.ButtonStyle.secondary, row=0)
    async def toggle_priority(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            current = (await db.get_config(interaction.guild_id, "ticket_priority_enabled", "false")).lower() == "true"
            new_val = "false" if current else "true"
            await db.set_config(interaction.guild_id, "ticket_priority_enabled", new_val)
            await interaction.response.send_message(f"Selezione priorità all'apertura: {new_val}", ephemeral=True)
        except Exception as e:
            logger.error(e)
            await interaction.response.send_message("Errore", ephemeral=True)

    @discord.ui.button(label="Toggle Auto-cleanup", style=discord.ButtonStyle.secondary, row=0)
    async def toggle_cleanup(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            current = (await db.get_config(interaction.guild_id, "ticket_auto_cleanup", "false")).lower() == "true"
            new_val = "false" if current else "true"
            await db.set_config(interaction.guild_id, "ticket_auto_cleanup", new_val)
            await interaction.response.send_message(f"Auto-cleanup ticket scaduti: {new_val}", ephemeral=True)
        except Exception as e:
            logger.error(e)
            await interaction.response.send_message("Errore", ephemeral=True)

    @discord.ui.select(
        placeholder="Priorità Default",
        options=[
            discord.SelectOption(label="Bassa", value="bassa"),
            discord.SelectOption(label="Media", value="media"),
            discord.SelectOption(label="Alta", value="alta"),
            discord.SelectOption(label="Urgente", value="urgente")
        ],
        row=1
    )
    async def select_priority(self, interaction: discord.Interaction, select: discord.ui.Select):
        try:
            await db.set_config(interaction.guild_id, "ticket_default_priority", select.values[0])
            await interaction.response.send_message(f"Priorità default impostata: {select.values[0]}", ephemeral=True)
        except Exception as e:
            logger.error(e)
            await interaction.response.send_message("Errore", ephemeral=True)

    @discord.ui.button(label="Invia pannello ticket", style=discord.ButtonStyle.success, row=2)
    async def send_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            categories = await db.get_categories(interaction.guild_id)
            if not categories:
                await interaction.response.send_message("Devi creare almeno una categoria prima di poter inviare il pannello ticket. Usa /setting → Categorie → Aggiungi categoria.", ephemeral=True)
                return

            class PanelChannelSelect(discord.ui.View):
                def __init__(self, bot):
                    super().__init__(timeout=60)
                    self.bot = bot

                @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="Seleziona canale per il pannello", channel_types=[discord.ChannelType.text])
                async def sel(self, inter: discord.Interaction, select: discord.ui.ChannelSelect):
                    try:
                        await inter.response.defer(ephemeral=True)
                        channel_val = select.values[0]
                        channel = self.bot.get_channel(channel_val.id)
                        if not channel:
                            try:
                                channel = await self.bot.fetch_channel(channel_val.id)
                            except:
                                await inter.followup.send("Errore: impossibile risolvere il canale selezionato.", ephemeral=True)
                                return

                        await send_ticket_panel(self.bot, channel)
                        await inter.followup.send(f"Pannello inviato in {channel.mention}", ephemeral=True)
                        self.stop()
                    except Exception as e:
                        logger.error(e)
                        try:
                            await inter.followup.send("Errore generico", ephemeral=True)
                        except:
                            pass

            await interaction.response.send_message("Seleziona in quale canale inviare il pannello dei ticket:", view=PanelChannelSelect(self.bot), ephemeral=True)
        except Exception as e:
            logger.error(e)

    @discord.ui.button(label="⬅️ Indietro", style=discord.ButtonStyle.primary, row=2)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(view=TicketSettingsViewPage1(self.bot, self.main_view))


# --- CATEGORIES MODULE ---
class AddCategoryModal(discord.ui.Modal, title='Aggiungi Categoria Ticket'):
    name = discord.ui.TextInput(label='Nome Categoria')
    desc = discord.ui.TextInput(label='Descrizione breve', required=False)
    welcome = discord.ui.TextInput(label='Messaggio di Benvenuto custom', style=discord.TextStyle.paragraph, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            class EmojiSelectView(discord.ui.View):
                def __init__(self, name_val, desc_val, welcome_val):
                    super().__init__(timeout=120)
                    self.name_val = name_val
                    self.desc_val = desc_val
                    self.welcome_val = welcome_val

                    options = [
                        discord.SelectOption(label="Ticket generico", emoji="🎫", value="🎫"),
                        discord.SelectOption(label="Supporto tecnico", emoji="🛠️", value="🛠️"),
                        discord.SelectOption(label="Pagamenti/acquisti", emoji="💰", value="💰"),
                        discord.SelectOption(label="Segnalazioni/report", emoji="📢", value="📢"),
                        discord.SelectOption(label="Domande generiche", emoji="❓", value="❓"),
                        discord.SelectOption(label="Bug", emoji="🐛", value="🐛"),
                        discord.SelectOption(label="Reclami/problemi", emoji="⚠️", value="⚠️"),
                        discord.SelectOption(label="Gaming/community", emoji="🎮", value="🎮"),
                        discord.SelectOption(label="Collaborazioni/partnership", emoji="🤝", value="🤝"),
                        discord.SelectOption(label="Altro", emoji="📋", value="📋")
                    ]
                    self.select = discord.ui.Select(placeholder="Scegli un'emoji per la categoria", options=options)
                    self.select.callback = self.on_select
                    self.add_item(self.select)

                async def on_select(self, inter: discord.Interaction):
                    try:
                        emoji_val = self.select.values[0]
                        await db.add_category(inter.guild_id, self.name_val, emoji_val, self.desc_val, self.welcome_val)
                        await inter.response.send_message(f"Categoria {self.name_val} aggiunta con successo.", ephemeral=True)
                        self.stop()
                    except Exception as e:
                        logger.error(e)
                        await inter.response.send_message("Errore nel salvataggio della categoria.", ephemeral=True)

            await interaction.response.send_message(
                "Seleziona l'emoji per la nuova categoria:",
                view=EmojiSelectView(self.name.value, self.desc.value, self.welcome.value),
                ephemeral=True
            )
        except Exception as e:
            logger.error(e)
            await interaction.response.send_message("Errore", ephemeral=True)

class CategoriesSettingsView(discord.ui.View):
    def __init__(self, main_view):
        super().__init__(timeout=None)
        self.add_item(BackButton(main_view))

    @discord.ui.button(label="Lista Categorie", style=discord.ButtonStyle.secondary)
    async def list_cats(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            cats = await db.get_categories(interaction.guild_id)
            if not cats:
                await interaction.response.send_message("Nessuna categoria.", ephemeral=True)
                return
            msg = "\n".join([f"- {c['emoji'] or ''} {c['name']}: {c['description'] or 'Nessuna doc'}" for c in cats])
            await interaction.response.send_message(f"Categorie:\n{msg}", ephemeral=True)
        except Exception as e:
            logger.error(e)
            await interaction.response.send_message("Errore", ephemeral=True)

    @discord.ui.button(label="Aggiungi Categoria", style=discord.ButtonStyle.primary)
    async def add_cat(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.send_modal(AddCategoryModal())
        except Exception as e:
            logger.error(e)

    @discord.ui.button(label="Rimuovi Categoria", style=discord.ButtonStyle.danger)
    async def rm_cat(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            cats = await db.get_categories(interaction.guild_id)
            if not cats:
                await interaction.response.send_message("Nessuna categoria da rimuovere.", ephemeral=True)
                return

            class RemoveSelect(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=60)
                    options = [discord.SelectOption(label=c['name']) for c in cats]
                    self.select = discord.ui.Select(placeholder="Scegli da rimuovere", options=options)
                    self.select.callback = self.on_sel
                    self.add_item(self.select)

                async def on_sel(self, inter):
                    try:
                        await db.remove_category(inter.guild_id, self.select.values[0])
                        await inter.response.send_message(f"Rimosso {self.select.values[0]}.", ephemeral=True)
                        self.stop()
                    except Exception as e:
                        logger.error(e)
                        await inter.response.send_message("Errore", ephemeral=True)

            await interaction.response.send_message("Seleziona categoria da rimuovere:", view=RemoveSelect(), ephemeral=True)
        except Exception as e:
            logger.error(e)
            await interaction.response.send_message("Errore", ephemeral=True)


# --- PERMISSIONS MODULE ---
class PermissionsSettingsView(discord.ui.View):
    def __init__(self, main_view):
        super().__init__(timeout=None)
        self.add_item(BackButton(main_view))

    @discord.ui.button(label="Lista Autorizzati", style=discord.ButtonStyle.secondary)
    async def list_users(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            users = await db.get_authorized_users(interaction.guild_id)
            if not users:
                await interaction.response.send_message("Nessun utente extra autorizzato.", ephemeral=True)
                return
            msg = "\n".join([f"- <@{u}>" for u in users])
            await interaction.response.send_message(f"Autorizzati:\n{msg}", ephemeral=True)
        except Exception as e:
            logger.error(e)
            await interaction.response.send_message("Errore", ephemeral=True)

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Aggiungi Utente")
    async def add_user(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        try:
            await db.add_authorized_user(interaction.guild_id, select.values[0].id)
            await interaction.response.send_message(f"{select.values[0].mention} aggiunto.", ephemeral=True)
        except Exception as e:
            logger.error(e)
            await interaction.response.send_message("Errore", ephemeral=True)

    @discord.ui.button(label="Rimuovi Utente Autorizzato", style=discord.ButtonStyle.danger)
    async def rem_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            users = await db.get_authorized_users(interaction.guild_id)
            if not users:
                await interaction.response.send_message("Nessun autorizzato da rimuovere.", ephemeral=True)
                return

            class RemoveAuthView(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=60)
                    options = [discord.SelectOption(label=str(u), value=str(u)) for u in users[:25]]
                    self.select = discord.ui.Select(placeholder="Scegli da rimuovere", options=options)
                    self.select.callback = self.on_sel
                    self.add_item(self.select)

                async def on_sel(self, inter):
                    try:
                        await db.remove_authorized_user(inter.guild_id, int(self.select.values[0]))
                        await inter.response.send_message(f"Utente <@{self.select.values[0]}> rimosso.", ephemeral=True)
                        self.stop()
                    except Exception as e:
                        logger.error(e)
                        await inter.response.send_message("Errore", ephemeral=True)

            await interaction.response.send_message("Seleziona utente da rimuovere:", view=RemoveAuthView(), ephemeral=True)
        except Exception as e:
            logger.error(e)
            await interaction.response.send_message("Errore", ephemeral=True)


class SettingsMenuView(discord.ui.View):
    def __init__(self, bot: discord.Client, embed: discord.Embed):
        super().__init__(timeout=None)
        self.bot = bot
        self.original_embed = embed

    @discord.ui.button(label="Benvenuto", style=discord.ButtonStyle.primary)
    async def btn_welcome(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.edit_message(
                content="**⚙️ Configurazione Benvenuto**\nImposta il canale, attiva/disattiva la card e configura grafica e ruoli.",
                embed=None,
                view=WelcomeSettingsViewPage1(self)
            )
        except Exception as e:
            logger.error(e)

    @discord.ui.button(label="Ticket", style=discord.ButtonStyle.primary)
    async def btn_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.edit_message(
                content="**⚙️ Configurazione Ticket**\nImposta log, permessi e opzioni avanzate del sistema ticket.",
                embed=None,
                view=TicketSettingsViewPage1(self.bot, self)
            )
        except Exception as e:
            logger.error(e)

    @discord.ui.button(label="Categorie", style=discord.ButtonStyle.primary)
    async def btn_categories(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.edit_message(
                content="**⚙️ Configurazione Categorie**\nGestisci le categorie disponibili nel menu ticket.",
                embed=None,
                view=CategoriesSettingsView(self)
            )
        except Exception as e:
            logger.error(e)

    @discord.ui.button(label="Permessi", style=discord.ButtonStyle.primary)
    async def btn_permissions(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.edit_message(
                content="**⚙️ Configurazione Permessi**\nAssegna ruoli amministrativi per il bot ad utenti specifici.",
                embed=None,
                view=PermissionsSettingsView(self)
            )
        except Exception as e:
            logger.error(e)

    @discord.ui.button(label="Aggiorna", style=discord.ButtonStyle.secondary)
    async def btn_refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.edit_message(embed=self.original_embed, view=self)
        except Exception as e:
            logger.error(e)

    @discord.ui.button(label="Chiudi", style=discord.ButtonStyle.danger)
    async def btn_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(view=self)
        except Exception as e:
            logger.error(e)


class MaintenanceView(discord.ui.View):
    def __init__(self, bot: discord.Client):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Riavvia Bot", emoji="🔄", style=discord.ButtonStyle.danger)
    async def btn_restart(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            class ConfirmView(discord.ui.View):
                @discord.ui.button(label="Conferma Riavvio", style=discord.ButtonStyle.danger)
                async def confirm(self, inter: discord.Interaction, btn: discord.ui.Button):
                    try:
                        await inter.response.send_message("Riavvio in corso...", ephemeral=True)
                        sys.exit(0)
                    except Exception as e:
                        logger.error(e)
            await interaction.response.send_message("Sei sicuro di voler riavviare il bot?", view=ConfirmView(), ephemeral=True)
        except Exception as e:
            logger.error(e)

    @discord.ui.button(label="Spegni Bot", emoji="⏹️", style=discord.ButtonStyle.danger)
    async def btn_shutdown(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            class ConfirmView(discord.ui.View):
                def __init__(self, bot):
                    super().__init__()
                    self.bot = bot
                @discord.ui.button(label="Conferma Spegnimento", style=discord.ButtonStyle.danger)
                async def confirm(self, inter: discord.Interaction, btn: discord.ui.Button):
                    try:
                        await inter.response.send_message("Spegnimento in corso...", ephemeral=True)
                        await self.bot.close()
                        sys.exit(0)
                    except Exception as e:
                        logger.error(e)
            await interaction.response.send_message("Sei sicuro di voler spegnere il bot?", view=ConfirmView(self.bot), ephemeral=True)
        except Exception as e:
            logger.error(e)

    @discord.ui.button(label="Pulisci tutti i ticket", emoji="🧹", style=discord.ButtonStyle.danger)
    async def btn_clean_tickets(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            class ConfirmView(discord.ui.View):
                def __init__(self, bot):
                    super().__init__()
                    self.bot = bot
                @discord.ui.button(label="Conferma Pulizia", style=discord.ButtonStyle.danger)
                async def confirm(self, inter: discord.Interaction, btn: discord.ui.Button):
                    try:
                        await inter.response.defer(ephemeral=True)
                        guild_id = inter.guild_id
                        tickets = await db.get_active_tickets(guild_id)
                        for ticket in tickets:
                            try:
                                channel = inter.guild.get_channel(ticket['channel_id'])
                                if channel:
                                    transcript = await generate_transcript(channel)
                                    os.makedirs("transcripts", exist_ok=True)
                                    safe_name = "".join([c for c in channel.name if c.isalnum() or c in ('-', '_')]).strip()
                                    file_path = f"transcripts/bulk_close_ticket_{channel.id}_{safe_name}.html"

                                    with open(file_path, "w", encoding="utf-8") as f:
                                        f.write(transcript)
                                    await db.add_transcript_log(guild_id, channel.id, file_path)

                                    log_channel_id = await db.get_config(guild_id, "ticket_log_channel")
                                    if log_channel_id:
                                        log_channel = channel.guild.get_channel(int(log_channel_id))
                                        if log_channel:
                                            await log_channel.send(content=f"Ticket Chiuso (Pulizia): {channel.name}", file=discord.File(file_path))

                                    await channel.delete()
                                await db.close_ticket(ticket['channel_id'])
                            except Exception as e:
                                logger.error(f"Error bulk cleaning ticket: {e}")
                        await inter.followup.send(f"Pulizia completata. {len(tickets)} ticket chiusi.", ephemeral=True)
                    except Exception as e:
                        logger.error(e)
                        try:
                            await inter.followup.send("Errore generico", ephemeral=True)
                        except:
                            pass
            await interaction.response.send_message("Sei sicuro di voler chiudere e cancellare tutti i ticket attivi di questo server?", view=ConfirmView(self.bot), ephemeral=True)
        except Exception as e:
            logger.error(e)

    @discord.ui.button(label="Backup Database", emoji="📦", style=discord.ButtonStyle.secondary)
    async def btn_backup(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.send_message(file=discord.File("data/bot.db"), ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Errore durante l'invio del backup: {e}", ephemeral=True)

    @discord.ui.button(label="Sincronizza comandi", emoji="⚡", style=discord.ButtonStyle.secondary)
    async def btn_sync(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            try:
                synced = await self.bot.tree.sync()
                await interaction.followup.send(f"Sincronizzati {len(synced)} comandi.", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"Errore durante la sincronizzazione: {e}", ephemeral=True)
        except Exception as e:
            logger.error(e)

    @discord.ui.button(label="Reset totale", emoji="🗑️", style=discord.ButtonStyle.danger)
    async def btn_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            class ConfirmView(discord.ui.View):
                def __init__(self, bot):
                    super().__init__()
                    self.bot = bot
                @discord.ui.button(label="Conferma Reset", style=discord.ButtonStyle.danger)
                async def confirm(self, inter: discord.Interaction, btn: discord.ui.Button):
                    try:
                        await inter.response.defer(ephemeral=True)
                        guild_id = inter.guild_id

                        # Save log channel config before clearing config to send transcripts
                        log_channel_id = await db.get_config(guild_id, "ticket_log_channel")

                        await db.clear_guild_config(guild_id)

                        tickets = await db.get_active_tickets(guild_id)
                        for ticket in tickets:
                            try:
                                channel = inter.guild.get_channel(ticket['channel_id'])
                                if channel:
                                    transcript = await generate_transcript(channel)
                                    os.makedirs("transcripts", exist_ok=True)
                                    safe_name = "".join([c for c in channel.name if c.isalnum() or c in ('-', '_')]).strip()
                                    file_path = f"transcripts/reset_ticket_{channel.id}_{safe_name}.html"

                                    with open(file_path, "w", encoding="utf-8") as f:
                                        f.write(transcript)
                                    await db.add_transcript_log(guild_id, channel.id, file_path)

                                    if log_channel_id:
                                        log_channel = channel.guild.get_channel(int(log_channel_id))
                                        if log_channel:
                                            await log_channel.send(content=f"Ticket Chiuso (Reset Server): {channel.name}", file=discord.File(file_path))

                                    await channel.delete()
                                await db.close_ticket(ticket['channel_id'])
                            except Exception as e:
                                logger.error(f"Error resetting ticket: {e}")
                        await inter.followup.send("Reset totale completato per questo server. Configurazioni eliminate e ticket chiusi.", ephemeral=True)
                    except Exception as e:
                        logger.error(e)
            await interaction.response.send_message("Sei assolutamente sicuro di voler ripristinare le configurazioni ed eliminare i ticket di questo server? Questa azione è irreversibile.", view=ConfirmView(self.bot), ephemeral=True)
        except Exception as e:
            logger.error(e)

    @discord.ui.button(label="Aggiorna", emoji="🔄", style=discord.ButtonStyle.secondary)
    async def btn_refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            embed = interaction.message.embeds[0]
            active = len(await db.get_active_tickets())
            embed.set_field_at(1, name="Ticket totali attivi", value=str(active), inline=False)
            await interaction.response.edit_message(embed=embed, view=self)
        except Exception as e:
            logger.error(e)

    @discord.ui.button(label="Chiudi", emoji="❌", style=discord.ButtonStyle.secondary)
    async def btn_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(view=self)
        except Exception as e:
            logger.error(e)


def setup_settings(bot: discord.Client):

    @bot.tree.command(name="setting", description="Apri il pannello di configurazione del bot")
    async def cmd_setting(interaction: discord.Interaction):
        try:
            if not await async_check_admin_access(interaction):
                await interaction.response.send_message("Non hai i permessi per usare questo comando.", ephemeral=True)
                return

            embed = discord.Embed(
                title="⚙️ Configurazione Bot",
                description="Benvenuto nel pannello di configurazione di Brotherhood Origins. Scegli un modulo da configurare qui sotto.",
                color=0x2b2d31
            )
            view = SettingsMenuView(bot, embed)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            logger.error(e)

    @bot.tree.command(name="maintenance", description="Apri il pannello di manutenzione")
    async def cmd_maintenance(interaction: discord.Interaction):
        try:
            if not await async_check_admin_access(interaction):
                await interaction.response.send_message("Non hai i permessi per usare questo comando.", ephemeral=True)
                return

            active_tickets = len(await db.get_active_tickets())

            embed = discord.Embed(
                title="🔧 Manutenzione",
                description="Pannello amministrativo. **Attenzione**: alcune di queste azioni sono distruttive o influiscono sul funzionamento del bot.",
                color=0xED4245
            )
            embed.add_field(name="Versione Python", value=platform.python_version(), inline=True)
            embed.add_field(name="Versione discord.py", value=discord.__version__, inline=True)
            embed.add_field(name="Ticket totali attivi (Globale)", value=str(active_tickets), inline=False)

            await interaction.response.send_message(embed=embed, view=MaintenanceView(bot), ephemeral=True)
        except Exception as e:
            logger.error(e)

    @bot.tree.command(name="adduser", description="Aggiunge un utente agli amministratori autorizzati del bot")
    @app_commands.describe(user="L'utente da autorizzare")
    async def cmd_adduser(interaction: discord.Interaction, user: discord.Member):
        try:
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("Solo un amministratore Discord del server può eseguire questa azione.", ephemeral=True)
                return

            await db.add_authorized_user(interaction.guild_id, user.id)
            await interaction.response.send_message(f"{user.mention} è stato aggiunto agli utenti autorizzati.", ephemeral=True)
        except Exception as e:
            logger.error(e)

    @bot.tree.command(name="removeuser", description="Rimuove un utente dagli amministratori autorizzati del bot")
    @app_commands.describe(user="L'utente da rimuovere")
    async def cmd_removeuser(interaction: discord.Interaction, user: discord.Member):
        try:
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("Solo un amministratore Discord del server può eseguire questa azione.", ephemeral=True)
                return

            await db.remove_authorized_user(interaction.guild_id, user.id)
            await interaction.response.send_message(f"{user.mention} è stato rimosso dagli utenti autorizzati.", ephemeral=True)
        except Exception as e:
            logger.error(e)
