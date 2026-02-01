import discord
from discord.ext import commands, tasks
from discord.ui import View, Select, ChannelSelect
import aiosqlite
import asyncio
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

# --- KONFIGURACIJA ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
DATABASE_NAME = 'studij.db'

if not TOKEN:
    print("❌ NAPAKA: Token ni najden! Preveri .env datoteko.")
    exit()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- BAZA PODATKOV ---
async def init_db():
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS study_programs (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE)")
        await db.execute("CREATE TABLE IF NOT EXISTS years (id INTEGER PRIMARY KEY AUTOINCREMENT, program_id INTEGER, number INTEGER, FOREIGN KEY(program_id) REFERENCES study_programs(id))")
        await db.execute("CREATE TABLE IF NOT EXISTS semesters (id INTEGER PRIMARY KEY AUTOINCREMENT, year_id INTEGER, number INTEGER, FOREIGN KEY(year_id) REFERENCES years(id))")
        await db.execute("CREATE TABLE IF NOT EXISTS subjects (id INTEGER PRIMARY KEY AUTOINCREMENT, semester_id INTEGER, name TEXT NOT NULL, acronym TEXT, professor TEXT, assistants TEXT, ects INTEGER, FOREIGN KEY(semester_id) REFERENCES semesters(id))")
        await db.execute("CREATE TABLE IF NOT EXISTS materials (id INTEGER PRIMARY KEY AUTOINCREMENT, subject_id INTEGER, url TEXT NOT NULL, description TEXT, type TEXT, FOREIGN KEY(subject_id) REFERENCES subjects(id))")
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS server_config (
                guild_id INTEGER PRIMARY KEY,
                current_program_id INTEGER,
                current_year_id INTEGER,
                current_semester_id INTEGER,
                notification_channel_id INTEGER
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS deadlines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER,
                deadline_type TEXT,
                date_time TEXT,
                description TEXT,
                sent_week BOOLEAN DEFAULT 0,
                sent_day BOOLEAN DEFAULT 0,
                FOREIGN KEY(subject_id) REFERENCES subjects(id)
            )
        """)
        await db.commit()
        print("Baza podatkov je pripravljena.")

# --- UI RAZREDI ZA ARHIV ---

# --- V main.py poišči class PredmetSelect in ZAMENJAJ celo callback funkcijo ---

class PredmetSelect(Select):
    def __init__(self, semester_id):
        self.semester_id = semester_id
        super().__init__(placeholder="📚 Izberi predmet...", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        subject_id = int(self.values[0])
        now_str = datetime.now().strftime("%Y-%m-%d") # Za filtriranje rokov

        async with aiosqlite.connect(DATABASE_NAME) as db:
            # 1. Pridobimo VSE metapodatke predmeta
            cursor = await db.execute("""
                SELECT name, acronym, ects, professor, assistants 
                FROM subjects WHERE id = ?
            """, (subject_id,))
            res = await cursor.fetchone()
            
            # Razpakiramo podatke
            name, acronym, ects, prof, asst = res
            
            # 2. Pridobimo gradiva
            cursor = await db.execute("SELECT description, url FROM materials WHERE subject_id = ?", (subject_id,))
            gradiva = await cursor.fetchall()
            
            # 3. Pridobimo roke (samo prihodnje)
            cursor = await db.execute("""
                SELECT deadline_type, date_time, description 
                FROM deadlines 
                WHERE subject_id = ? AND date_time >= ? 
                ORDER BY date_time ASC
            """, (subject_id, now_str))
            roki = await cursor.fetchall()

        # --- IZDELAVA EMBEDA (Lepši prikaz) ---
        embed = discord.Embed(title=f"{name} ({acronym})", color=discord.Color.blue())
        
        # Glavni podatki
        desc_text = f"**ECTS:** {ects}\n"
        if prof: desc_text += f"**Nosilec:** {prof}\n"
        if asst: desc_text += f"**Asistenti:** {asst}\n"
        embed.description = desc_text

        # Gradiva
        if gradiva:
            materials_text = ""
            for desc, url in gradiva:
                materials_text += f"🔹 [{desc}]({url})\n" # Klikabilni linki
            embed.add_field(name="📂 Gradiva", value=materials_text, inline=False)
        else:
            embed.add_field(name="📂 Gradiva", value="*Ni gradiv*", inline=False)

        # Roki
        if roki:
            roki_text = ""
            for dtype, dtime, desc in roki:
                date_obj = datetime.strptime(dtime, "%Y-%m-%d").strftime("%d. %m. %Y")
                roki_text += f"🔸 **{dtype}**: {date_obj}"
                if desc: roki_text += f" *({desc})*"
                roki_text += "\n"
            embed.add_field(name="⏳ Prihajajoči roki", value=roki_text, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=False)

class SemesterSelect(Select):
    def __init__(self, year_id, options):
        self.year_id = year_id
        super().__init__(placeholder="🍂 Izberi semester...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        semester_id = int(self.values[0])
        async with aiosqlite.connect(DATABASE_NAME) as db:
            cursor = await db.execute("SELECT id, name, acronym FROM subjects WHERE semester_id = ?", (semester_id,))
            predmeti = await cursor.fetchall()

        if not predmeti:
            return await interaction.response.send_message("❌ V tem semestru ni predmetov.", ephemeral=True)

        options = [discord.SelectOption(label=f"{name} ({acronym})"[:100], value=str(pid)) for pid, name, acronym in predmeti]
        view = View()
        view.add_item(PredmetSelect(semester_id))
        view.children[0].options = options
        await interaction.response.edit_message(content="⬇️ Zdaj izberi predmet:", view=view)

class LetnikSelect(Select):
    def __init__(self, program_id, options):
        self.program_id = program_id
        super().__init__(placeholder="📅 Izberi letnik...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        year_id = int(self.values[0])
        async with aiosqlite.connect(DATABASE_NAME) as db:
            cursor = await db.execute("SELECT id, number FROM semesters WHERE year_id = ? ORDER BY number ASC", (year_id,))
            semestri = await cursor.fetchall()

        if not semestri:
            return await interaction.response.send_message("❌ Ta letnik nima semestrov.", ephemeral=True)

        options = [discord.SelectOption(label=f"{'Zimski' if num==1 else 'Poletni'} semester", value=str(sid)) for sid, num in semestri]
        view = View()
        view.add_item(SemesterSelect(year_id, options))
        await interaction.response.edit_message(content="⬇️ Zdaj izberi semester:", view=view)


# --- UI RAZREDI ZA SETUP (CHAIN) ---
class SetupChannelSelect(ChannelSelect):
    def __init__(self, program_id, year_id, semester_id):
        self.prog_id = program_id
        self.year_id = year_id
        self.sem_id = semester_id
        super().__init__(placeholder="📢 Izberi kanal za obvestila...", channel_types=[discord.ChannelType.text], min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        channel = self.values[0]
        async with aiosqlite.connect(DATABASE_NAME) as db:
            await db.execute("""
                INSERT OR REPLACE INTO server_config (guild_id, current_program_id, current_year_id, current_semester_id, notification_channel_id)
                VALUES (?, ?, ?, ?, ?)
            """, (interaction.guild_id, self.prog_id, self.year_id, self.sem_id, channel.id))
            await db.commit()
        await interaction.response.edit_message(content=f"✅ **Setup zaključen!**\nObvestila o rokih bodo prihajala v {channel.mention}.", view=None)

class SetupSemesterSelect(Select):
    def __init__(self, program_id, year_id, options):
        self.prog_id = program_id
        self.year_id = year_id
        super().__init__(placeholder="🍂 Izberi semester...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        sem_id = int(self.values[0])
        view = View()
        view.add_item(SetupChannelSelect(self.prog_id, self.year_id, sem_id))
        await interaction.response.edit_message(content="📢 **Zadnji korak:**\nIzberi kanal, kamor naj bot pošilja opozorila:", view=view)

class SetupLetnikSelect(Select):
    def __init__(self, program_id, options):
        self.prog_id = program_id
        super().__init__(placeholder="📅 Izberi letnik...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        year_id = int(self.values[0])
        async with aiosqlite.connect(DATABASE_NAME) as db:
            cursor = await db.execute("SELECT id, number FROM semesters WHERE year_id = ? ORDER BY number ASC", (year_id,))
            semestri = await cursor.fetchall()
        options = [discord.SelectOption(label=f"{'Zimski' if num==1 else 'Poletni'} semester", value=str(sid)) for sid, num in semestri]
        view = View()
        view.add_item(SetupSemesterSelect(self.prog_id, year_id, options))
        await interaction.response.edit_message(content="⬇️ Izberi semester:", view=view)

class SetupSmerSelect(Select):
    def __init__(self, options):
        super().__init__(placeholder="🎓 Izberi smer študija...", min_values=1, max_values=1, options=options)
    
    async def callback(self, interaction: discord.Interaction):
        prog_id = int(self.values[0])
        async with aiosqlite.connect(DATABASE_NAME) as db:
            cursor = await db.execute("SELECT id, number FROM years WHERE program_id = ? ORDER BY number ASC", (prog_id,))
            letniki = await cursor.fetchall()
        options = [discord.SelectOption(label=f"{num}. letnik", value=str(lid)) for lid, num in letniki]
        view = View()
        view.add_item(SetupLetnikSelect(prog_id, options))
        await interaction.response.edit_message(content="⬇️ Izberi letnik:", view=view)


# --- UI ZA NASTAVITVE ---
class SettingsChannelSelect(ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="📢 Izberi nov kanal...", channel_types=[discord.ChannelType.text], min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        channel = self.values[0]
        async with aiosqlite.connect(DATABASE_NAME) as db:
            await db.execute("UPDATE server_config SET notification_channel_id = ? WHERE guild_id = ?", (channel.id, interaction.guild_id))
            await db.commit()
        await interaction.response.edit_message(content=f"✅ Kanal za obvestila uspešno spremenjen na {channel.mention}.", view=None)

# --- UI RAZREDI ZA POSODOBI ---
class AdminSemesterSelect(Select):
    def __init__(self, year_id, options, program_id):
        self.year_id = year_id
        self.program_id = program_id
        super().__init__(placeholder="⚙️ Nastavi nov semester...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        semester_id = int(self.values[0])
        guild_id = interaction.guild_id
        async with aiosqlite.connect(DATABASE_NAME) as db:
            await db.execute("""
                UPDATE server_config SET current_program_id = ?, current_year_id = ?, current_semester_id = ?
                WHERE guild_id = ?
            """, (self.program_id, self.year_id, semester_id, guild_id))
            await db.commit()
        await interaction.response.edit_message(content=f"✅ **Uspešno posodobljeno!**\nNov semester je nastavljen.", view=None)

class AdminYearSelect(Select):
    def __init__(self, program_id, options):
        self.program_id = program_id
        super().__init__(placeholder="⚙️ Nastavi nov letnik...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        year_id = int(self.values[0])
        async with aiosqlite.connect(DATABASE_NAME) as db:
            cursor = await db.execute("SELECT id, number FROM semesters WHERE year_id = ? ORDER BY number ASC", (year_id,))
            semestri = await cursor.fetchall()
        options = [discord.SelectOption(label=f"{'Zimski' if num==1 else 'Poletni'} semester", value=str(sid)) for sid, num in semestri]
        view = View()
        view.add_item(AdminSemesterSelect(year_id, options, self.program_id))
        await interaction.response.edit_message(content="⬇️ Izberi semester:", view=view)

# --- BACKGROUND TASK ---
@tasks.loop(hours=1)
async def check_deadlines():
    now = datetime.now().date()
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute("""
            SELECT d.id, d.deadline_type, d.date_time, d.description, d.sent_week, d.sent_day, 
                   s.name, sc.notification_channel_id
            FROM deadlines d
            JOIN subjects s ON d.subject_id = s.id
            JOIN semesters sem ON s.semester_id = sem.id
            JOIN server_config sc ON sc.current_semester_id = sem.id
            WHERE d.date_time >= ?
        """, (now.strftime("%Y-%m-%d"),))
        roki = await cursor.fetchall()
        
        for rok in roki:
            rok_id, dtype, ddate_str, desc, sent_week, sent_day, subj_name, channel_id = rok
            if not channel_id: continue
            
            ddate = datetime.strptime(ddate_str, "%Y-%m-%d").date()
            days_left = (ddate - now).days
            channel = bot.get_channel(channel_id)
            if not channel: continue

            if days_left == 7 and not sent_week:
                embed = discord.Embed(title=f"⏳ {dtype} čez 1 teden!", color=discord.Color.orange())
                embed.add_field(name="Predmet", value=subj_name)
                embed.add_field(name="Datum", value=ddate.strftime("%d. %m. %Y"))
                if desc: embed.add_field(name="Opis", value=desc, inline=False)
                await channel.send(embed=embed)
                await db.execute("UPDATE deadlines SET sent_week = 1 WHERE id = ?", (rok_id,))
                await db.commit()

            if days_left == 1 and not sent_day:
                embed = discord.Embed(title=f"🚨 {dtype} je JUTRI!", color=discord.Color.red())
                embed.add_field(name="Predmet", value=subj_name)
                if desc: embed.add_field(name="Opis", value=desc, inline=False)
                await channel.send(embed=embed)
                await db.execute("UPDATE deadlines SET sent_day = 1 WHERE id = ?", (rok_id,))
                await db.commit()

@bot.event
async def on_ready():
    await init_db()
    if not check_deadlines.is_running():
        check_deadlines.start()
    print(f'Prijavljen kot {bot.user}')

# --- UKAZI ZA LASTNIKA ---
@bot.command()
@commands.is_owner()
async def nova_smer(ctx, *, ime_smeri: str):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        try:
            await db.execute("INSERT INTO study_programs (name) VALUES (?)", (ime_smeri,))
            await db.commit()
            await ctx.send(f"✅ Dodana smer: **{ime_smeri}**")
        except: await ctx.send("⚠️ Napaka.")

@bot.command()
@commands.is_owner()
async def dodaj_letnik(ctx, ime_smeri: str, st_letnika: int):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute("SELECT id FROM study_programs WHERE name = ?", (ime_smeri,))
        program = await cursor.fetchone()
        if program:
            await db.execute("INSERT INTO years (program_id, number) VALUES (?, ?)", (program[0], st_letnika))
            await db.commit()
            await ctx.send(f"✅ Dodan letnik {st_letnika}.")

@bot.command()
@commands.is_owner()
async def dodaj_semester(ctx, ime_smeri: str, st_letnika: int, st_semestra: int):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        query = "SELECT y.id FROM years y JOIN study_programs sp ON y.program_id = sp.id WHERE sp.name = ? AND y.number = ?"
        cursor = await db.execute(query, (ime_smeri, st_letnika))
        year = await cursor.fetchone()
        if year:
            await db.execute("INSERT INTO semesters (year_id, number) VALUES (?, ?)", (year[0], st_semestra))
            await db.commit()
            await ctx.send("✅ Dodan semester.")

@bot.command()
@commands.is_owner()
async def dodaj_predmet(ctx, ime_smeri: str, st_letnika: int, st_semestra: int, ime_predmeta: str, kratica: str, ects: int):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        query = """SELECT s.id FROM semesters s JOIN years y ON s.year_id = y.id JOIN study_programs sp ON y.program_id = sp.id 
                   WHERE sp.name = ? AND y.number = ? AND s.number = ?"""
        cursor = await db.execute(query, (ime_smeri, st_letnika, st_semestra))
        semester = await cursor.fetchone()
        if semester:
            await db.execute("INSERT INTO subjects (semester_id, name, acronym, ects) VALUES (?, ?, ?, ?)", 
                             (semester[0], ime_predmeta, kratica, ects))
            await db.commit()
            await ctx.send(f"✅ Dodan predmet {ime_predmeta}.")

# --- ADMIN STREŽNIKA ---
@bot.command()
@commands.has_permissions(administrator=True)
async def setup(ctx):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute("SELECT id, name FROM study_programs")
        smeri = await cursor.fetchall()
        if not smeri: return await ctx.send("⚠️ Baza je prazna.")

    options = [discord.SelectOption(label=name[:100], value=str(pid)) for pid, name in smeri]
    view = View()
    view.add_item(SetupSmerSelect(options))
    await ctx.send("⚙️ **Začenjam Setup**\nIzberi smer študija za ta strežnik:", view=view)

@bot.command()
@commands.has_permissions(administrator=True)
async def nastavitve(ctx):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute("""
            SELECT sp.name, y.number, sem.number, sc.notification_channel_id 
            FROM server_config sc
            JOIN study_programs sp ON sc.current_program_id = sp.id
            JOIN years y ON sc.current_year_id = y.id
            JOIN semesters sem ON sc.current_semester_id = sem.id
            WHERE sc.guild_id = ?
        """, (ctx.guild.id,))
        res = await cursor.fetchone()
    
    if not res: return await ctx.send("⚠️ Bot ni konfiguriran.")

    prog_name, year_num, sem_num, channel_id = res
    channel_mention = f"<#{channel_id}>" if channel_id else "Ni nastavljen"
    sem_name = "Zimski" if sem_num == 1 else "Poletni"

    embed = discord.Embed(title="⚙️ Nastavitve Strežnika", color=discord.Color.blue())
    embed.add_field(name="Smer", value=prog_name, inline=False)
    embed.add_field(name="Letnik", value=f"{year_num}. letnik", inline=True)
    embed.add_field(name="Semester", value=sem_name, inline=True)
    embed.add_field(name="Kanal za obvestila", value=channel_mention, inline=False)
    
    view = View()
    view.add_item(SettingsChannelSelect())
    await ctx.send(embed=embed, view=view)

@bot.command()
@commands.has_permissions(administrator=True)
async def posodobi(ctx):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute("SELECT current_program_id FROM server_config WHERE guild_id = ?", (ctx.guild.id,))
        config = await cursor.fetchone()
        if not config: return await ctx.send("⚠️ Bot ni nastavljen.")
        program_id = config[0]
        cursor = await db.execute("SELECT id, number FROM years WHERE program_id = ? ORDER BY number ASC", (program_id,))
        letniki = await cursor.fetchall()
    if not letniki: return await ctx.send("⚠️ Napaka v bazi.")
    options = [discord.SelectOption(label=f"{num}. letnik", value=str(lid)) for lid, num in letniki]
    view = View()
    view.add_item(AdminYearSelect(program_id, options))
    await ctx.send("⚙️ **Posodobitev semestra**\nIzberi novi letnik:", view=view)

@bot.command()
@commands.has_permissions(administrator=True)
async def dodaj_rok(ctx, kratica: str, tip: str, datum: str, *, opis: str):
    if tip.lower() not in ['vaje', 'kolokvij', 'izpit']: return await ctx.send("❌ Tip mora biti: Vaje, Kolokvij ali Izpit.")
    try:
        db_date = datetime.strptime(datum, "%d.%m.%Y").strftime("%Y-%m-%d")
    except ValueError: return await ctx.send("❌ Napačen format (DD.MM.YYYY).")

    async with aiosqlite.connect(DATABASE_NAME) as db:
        config = await db.execute("SELECT current_semester_id FROM server_config WHERE guild_id = ?", (ctx.guild.id,))
        cfg = await config.fetchone()
        if not cfg: return await ctx.send("⚠️ Bot ni nastavljen.")

        cursor = await db.execute("SELECT id, name FROM subjects WHERE semester_id = ? AND UPPER(acronym) = ?", (cfg[0], kratica.upper()))
        subj = await cursor.fetchone()
        if not subj: return await ctx.send(f"❌ Predmet {kratica} ne obstaja.")

        await db.execute("INSERT INTO deadlines (subject_id, deadline_type, date_time, description) VALUES (?, ?, ?, ?)", 
                         (subj[0], tip.capitalize(), db_date, opis))
        await db.commit()
    await ctx.send(f"✅ Dodan rok: **{subj[1]}** - {tip} ({datum})")

@bot.command()
@commands.has_permissions(administrator=True)
async def dodaj_gradivo(ctx, kratica: str, url: str, *, opis: str):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        config = await db.execute("SELECT current_semester_id FROM server_config WHERE guild_id = ?", (ctx.guild.id,))
        cfg = await config.fetchone()
        if not cfg: return await ctx.send("⚠️ Bot ni nastavljen.")

        cursor = await db.execute("SELECT id, name FROM subjects WHERE semester_id = ? AND UPPER(acronym) = ?", (cfg[0], kratica.upper()))
        subj = await cursor.fetchone()
        if subj:
            await db.execute("INSERT INTO materials (subject_id, url, description, type) VALUES (?, ?, ?, ?)", (subj[0], url, opis, "Gradivo"))
            await db.commit()
            await ctx.send(f"✅ Gradivo dodano.")
        else: await ctx.send("❌ Predmet ne obstaja.")

@bot.command()
async def arhiv(ctx):
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute("SELECT current_program_id FROM server_config WHERE guild_id = ?", (ctx.guild.id,))
        config = await cursor.fetchone()

    if config:
        prog_id = config[0]
        async with aiosqlite.connect(DATABASE_NAME) as db:
            cursor = await db.execute("SELECT id, number FROM years WHERE program_id = ? ORDER BY number ASC", (prog_id,))
            letniki = await cursor.fetchall()
        options = [discord.SelectOption(label=f"{n}. letnik", value=str(i)) for i, n in letniki]
        view = View()
        view.add_item(LetnikSelect(prog_id, options))
        return await ctx.send(f"📂 **Gradiva in roki**\n⬇️ Izberi letnik:", view=view)

    async with aiosqlite.connect(DATABASE_NAME) as db:
        smeri = await (await db.execute("SELECT id, name FROM study_programs")).fetchall()
    
    class SmerSelectArhiv(Select):
        def __init__(self, opts): super().__init__(placeholder="🎓 Izberi smer...", options=opts)
        async def callback(self, i):
            p = int(self.values[0])
            async with aiosqlite.connect(DATABASE_NAME) as db:
                l = await (await db.execute("SELECT id, number FROM years WHERE program_id=?",(p,))).fetchall()
            v = View()
            v.add_item(LetnikSelect(p, [discord.SelectOption(label=f"{n}. letnik", value=str(x)) for x,n in l]))
            await i.response.edit_message(content="⬇️ Izberi letnik:", view=v)

    view = View()
    view.add_item(SmerSelectArhiv([discord.SelectOption(label=n[:100], value=str(i)) for i,n in smeri]))
    await ctx.send("🗄️ **Arhiv (Splošni)**\nIzberi smer:", view=view)

    # --- GLAVNI UKAZ ZA ŠTUDENTE (TRENUTNI SEMESTER) ---

class CurrentSemesterView(View):
    def __init__(self, semester_id, options):
        super().__init__()
        # Ponovno uporabimo PredmetSelect, ki smo ga že definirali za arhiv
        # ampak mu ročno nastavimo opcije, ki veljajo za ta semester
        select_menu = PredmetSelect(semester_id)
        select_menu.options = options
        self.add_item(select_menu)

@bot.command()
async def predmeti(ctx):
    """Prikaže seznam predmetov za TRENUTNI semester strežnika."""
    
    # 1. Pridobimo nastavitve strežnika
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute("""
            SELECT current_semester_id 
            FROM server_config 
            WHERE guild_id = ?
        """, (ctx.guild.id,))
        config = await cursor.fetchone()
    
    # Če setup ni narejen
    if not config:
        return await ctx.send("⚠️ Bot na tem strežniku še ni nastavljen. Administrator naj uporabi `!setup`.")
    
    current_semester_id = config[0]

    # 2. Pridobimo predmete za ta semester
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute("""
            SELECT id, name, acronym 
            FROM subjects 
            WHERE semester_id = ? 
            ORDER BY name ASC
        """, (current_semester_id,))
        predmeti = await cursor.fetchall()

    if not predmeti:
        return await ctx.send("📭 V trenutnem semestru ni vnešenih predmetov.")

    # 3. Pripravimo Dropdown (Select Menu)
    # Omejitev Discorda je 25 opcij na meni. Če jih je več, bi morali narediti paginacijo, 
    # ampak za en semester je ponavadi < 10 predmetov.
    options = []
    for pid, name, acronym in predmeti:
        # Label mora biti krajši od 100 znakov
        label_text = f"{name} ({acronym})"[:100]
        options.append(discord.SelectOption(label=label_text, value=str(pid)))

    # 4. Pošljemo sporočilo z menijem
    view = CurrentSemesterView(current_semester_id, options)
    await ctx.send("📚 **Predmeti v tekočem semestru**\nIzberi predmet za podrobnosti:", view=view)

bot.run(TOKEN)