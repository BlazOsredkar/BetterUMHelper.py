import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# --- KONFIGURACIJA ---
st.set_page_config(page_title="Discord Bot Admin", layout="wide", page_icon="🎓")
DB_FILE = 'studij.db'

# --- CSS STILI (AGRESIVEN POPRAVEK KONTRASTA) ---
st.markdown("""
<style>
    /* Gumbi */
    .stButton>button { width: 100%; border-radius: 8px; font-weight: bold; }
    
    /* 1. KARTICE (Metrics) - Vsilimo belo ozadje in ČRNO pisavo */
    div[data-testid="stMetric"] {
        background-color: #ffffff !important;
        border: 1px solid #cccccc !important;
        padding: 15px !important;
        border-radius: 10px !important;
        color: #000000 !important;
    }
    
    /* Naslov statistike (npr. "Predmeti") */
    div[data-testid="stMetricLabel"] {
        color: #333333 !important; /* Temno siva */
        font-weight: bold !important;
    }
    
    /* Vrednost statistike (npr. "5") */
    div[data-testid="stMetricValue"] {
        color: #000000 !important; /* Črna */
    }

    /* 2. EXPANDERJI (Izbriši gradivo...) */
    div[data-testid="stExpander"] {
        background-color: #ffffff !important;
        border: 1px solid #cccccc !important;
        border-radius: 10px !important;
        color: #000000 !important;
    }
    
    /* Naslov expanderja (tisto kar klikneš) */
    div[data-testid="stExpander"] summary {
        color: #000000 !important; /* Črna */
        font-weight: 600 !important;
    }
    
    /* Vsa besedila znotraj expanderja */
    div[data-testid="stExpander"] p, 
    div[data-testid="stExpander"] span, 
    div[data-testid="stExpander"] div {
        color: #000000 !important;
    }

    /* Popravek za ikono puščice v expanderju */
    div[data-testid="stExpander"] svg {
        fill: #000000 !important;
    }
</style>
""", unsafe_allow_html=True)

# --- POVEZAVA Z BAZO ---
def run_query(query, params=()):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()

def get_data(query, params=()):
    with sqlite3.connect(DB_FILE) as conn:
        return pd.read_sql(query, conn, params=params)

# --- SIDEBAR ---
st.sidebar.title("🎓 Admin Panel")
menu = st.sidebar.radio("Meni:", ["🏠 Domov (Statistika)", "📝 Pregled in Urejanje", "➕ Dodajanje Podatkov"])
st.sidebar.markdown("---")
st.sidebar.info("Opomba: Podatki dodani tukaj so **Globalni** (vidni vsem strežnikom).")

# ==========================================
# 1. DOMOV (DASHBOARD)
# ==========================================
if menu == "🏠 Domov (Statistika)":
    st.title("📊 Pregled Stanja")
    
    try:
        num_subjects = get_data("SELECT COUNT(*) as c FROM subjects")['c'][0]
        num_materials = get_data("SELECT COUNT(*) as c FROM materials")['c'][0]
        num_deadlines = get_data("SELECT COUNT(*) as c FROM deadlines WHERE date_time >= DATE('now')")['c'][0]
        num_servers = get_data("SELECT COUNT(*) as c FROM server_config")['c'][0]
    except:
        st.error("Baza še ni inicializirana. Zaženi bota enkrat, da ustvari tabele.")
        st.stop()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📚 Predmeti", num_subjects)
    col2.metric("📂 Gradiva", num_materials)
    col3.metric("⏳ Aktivni Roki", num_deadlines)
    col4.metric("🤖 Povezani Strežniki", num_servers)

    st.markdown("### 📅 Prihajajoči roki (naslednjih 7 dni)")
    upcoming = get_data("""
        SELECT s.name as 'Predmet', d.deadline_type as 'Tip', d.date_time as 'Datum', d.description as 'Opis'
        FROM deadlines d JOIN subjects s ON d.subject_id = s.id
        WHERE d.date_time BETWEEN DATE('now') AND DATE('now', '+7 days')
        ORDER BY d.date_time ASC
    """)
    if not upcoming.empty:
        st.dataframe(upcoming, width='stretch', hide_index=True)
    else:
        st.success("Ni rokov v naslednjem tednu! 🎉")

# ==========================================
# 2. PREGLED IN UREJANJE
# ==========================================
elif menu == "📝 Pregled in Urejanje":
    st.title("📝 Upravljanje Podatkov")
    tab1, tab2, tab3 = st.tabs(["📚 Predmeti", "📂 Gradiva", "⏳ Roki"])

    # --- TAB 1: PREDMETI ---
    with tab1:
        st.subheader("Seznam predmetov")
        search = st.text_input("🔍 Išči predmet:", key="search_sub")
        
        q_sub = """
            SELECT s.id, s.name as 'Ime', s.acronym as 'Kratica', s.ects as 'ECTS', 
                   s.professor as 'Profesor', s.assistants as 'Asistenti'
            FROM subjects s
        """
        if search:
            q_sub += f" WHERE s.name LIKE '%{search}%' OR s.acronym LIKE '%{search}%'"
        
        df_sub = get_data(q_sub)
        st.dataframe(df_sub, width='stretch', hide_index=True)

        col_edit, col_del = st.columns(2)
        
        with col_edit.expander("✏️ Uredi predmet"):
            if not df_sub.empty:
                sub_to_edit = st.selectbox("Izberi predmet:", df_sub['id'], format_func=lambda x: df_sub[df_sub['id']==x]['Ime'].values[0])
                if sub_to_edit:
                    curr_data = df_sub[df_sub['id'] == sub_to_edit].iloc[0]
                    with st.form("edit_sub"):
                        new_prof = st.text_input("Profesor", value=curr_data['Profesor'] if curr_data['Profesor'] else "")
                        new_asst = st.text_input("Asistenti", value=curr_data['Asistenti'] if curr_data['Asistenti'] else "")
                        new_ects = st.number_input("ECTS", value=int(curr_data['ECTS']))
                        if st.form_submit_button("Shrani Spremembe"):
                            run_query("UPDATE subjects SET professor=?, assistants=?, ects=? WHERE id=?", (new_prof, new_asst, new_ects, sub_to_edit))
                            st.success("Posodobljeno!")
                            st.rerun()

        with col_del.expander("🗑️ Izbriši predmet"):
            if not df_sub.empty:
                st.warning("To izbriše tudi gradiva in roke!")
                sub_to_del = st.selectbox("Izberi predmet za izbris:", df_sub['id'], key="del_sub", format_func=lambda x: df_sub[df_sub['id']==x]['Ime'].values[0])
                if st.button("Potrdi Izbris", type="primary"):
                    run_query("DELETE FROM materials WHERE subject_id=?", (sub_to_del,))
                    run_query("DELETE FROM deadlines WHERE subject_id=?", (sub_to_del,))
                    run_query("DELETE FROM subjects WHERE id=?", (sub_to_del,))
                    st.error("Predmet izbrisan.")
                    st.rerun()

    # --- TAB 2: GRADIVA ---
    with tab2:
        st.subheader("Pregled gradiv")
        try:
            df_mat = get_data("""
                SELECT m.id, s.name as 'Predmet', m.description as 'Opis', m.url as 'URL',
                       CASE WHEN m.guild_id IS NULL THEN '🌍 Globalno' ELSE '🔒 Zasebno' END as 'Tip'
                FROM materials m JOIN subjects s ON m.subject_id = s.id
            """)
        except:
            df_mat = get_data("SELECT m.id, s.name as 'Predmet', m.description as 'Opis', m.url as 'URL' FROM materials m JOIN subjects s ON m.subject_id = s.id")

        st.dataframe(df_mat, width='stretch', hide_index=True)
        
        with st.expander("🗑️ Izbriši gradivo"):
            if not df_mat.empty:
                mat_id = st.selectbox("Gradivo:", df_mat['id'], format_func=lambda x: f"{df_mat[df_mat['id']==x]['Opis'].values[0]} ({df_mat[df_mat['id']==x]['Predmet'].values[0]})")
                if st.button("Izbriši Gradivo"):
                    run_query("DELETE FROM materials WHERE id=?", (mat_id,))
                    st.success("Izbrisano.")
                    st.rerun()

    # --- TAB 3: ROKI ---
    with tab3:
        st.subheader("Pregled rokov")
        try:
            df_rok = get_data("""
                SELECT d.id, s.name as 'Predmet', d.deadline_type as 'Tip', d.date_time as 'Datum', 
                       CASE WHEN d.guild_id IS NULL THEN '🌍 Globalno' ELSE '🔒 Zasebno' END as 'Vidnost'
                FROM deadlines d JOIN subjects s ON d.subject_id = s.id
                ORDER BY d.date_time DESC
            """)
        except:
            df_rok = get_data("SELECT d.id, s.name as 'Predmet', d.deadline_type as 'Tip', d.date_time as 'Datum' FROM deadlines d JOIN subjects s ON d.subject_id = s.id ORDER BY d.date_time DESC")
        
        def highlight_expired(row):
            try:
                deadline = datetime.strptime(row['Datum'], "%Y-%m-%d").date()
                if deadline < datetime.now().date():
                    return ['background-color: #ffebee'] * len(row)
            except: pass
            return [''] * len(row)

        st.dataframe(df_rok.style.apply(highlight_expired, axis=1), width='stretch', hide_index=True)

        with st.expander("🗑️ Izbriši rok"):
            if not df_rok.empty:
                rok_id = st.selectbox("Rok:", df_rok['id'], format_func=lambda x: f"{df_rok[df_rok['id']==x]['Predmet'].values[0]} - {df_rok[df_rok['id']==x]['Datum'].values[0]}")
                if st.button("Izbriši Rok"):
                    run_query("DELETE FROM deadlines WHERE id=?", (rok_id,))
                    st.success("Izbrisano.")
                    st.rerun()

# ==========================================
# 3. DODAJANJE PODATKOV
# ==========================================
elif menu == "➕ Dodajanje Podatkov":
    st.title("➕ Dodajanje v Bazo")
    tip = st.selectbox("Kaj želiš dodati?", ["Nova Smer (Avtomatsko)", "Predmet", "Gradivo", "Rok"])

    # --- NOVA SMER (AVTOMATIKA) ---
    if tip == "Nova Smer (Avtomatsko)":
        st.markdown("### 🎓 Ustvari novo smer in strukturo")
        st.info("Ta funkcija bo ustvarila smer, letnike in semestre avtomatsko.")
        
        with st.form("new_program_auto"):
            ime_smeri = st.text_input("Ime smeri (npr. Računalništvo in IT)")
            st_letnikov = st.number_input("Število letnikov", min_value=1, max_value=6, value=3)
            
            submit_prog = st.form_submit_button("🚀 Ustvari Smer")
            
            if submit_prog and ime_smeri:
                try:
                    with sqlite3.connect(DB_FILE) as conn:
                        cursor = conn.cursor()
                        cursor.execute("INSERT INTO study_programs (name) VALUES (?)", (ime_smeri,))
                        prog_id = cursor.lastrowid
                        for i in range(1, st_letnikov + 1):
                            cursor.execute("INSERT INTO years (program_id, number) VALUES (?, ?)", (prog_id, i))
                            year_id = cursor.lastrowid
                            cursor.execute("INSERT INTO semesters (year_id, number) VALUES (?, ?)", (year_id, 1))
                            cursor.execute("INSERT INTO semesters (year_id, number) VALUES (?, ?)", (year_id, 2))
                        conn.commit()
                    st.success(f"✅ Uspešno ustvarjena smer **{ime_smeri}**!")
                except sqlite3.IntegrityError:
                    st.error("Ta smer že obstaja!")
                except Exception as e:
                    st.error(f"Napaka: {e}")

    # --- PREDMET ---
    elif tip == "Predmet":
        smeri = get_data("SELECT id, name FROM study_programs")
        if smeri.empty: st.error("Ni smeri. Uporabi opcijo 'Nova Smer (Avtomatsko)' zgoraj!")
        else:
            smer = st.selectbox("Smer:", smeri['id'], format_func=lambda x: smeri[smeri['id']==x]['name'].values[0])
            letniki = get_data("SELECT id, number FROM years WHERE program_id=?", (smer,))
            if not letniki.empty:
                letnik = st.selectbox("Letnik:", letniki['id'], format_func=lambda x: f"{letniki[letniki['id']==x]['number'].values[0]}. letnik")
                semestri = get_data("SELECT id, number FROM semesters WHERE year_id=?", (letnik,))
                if not semestri.empty:
                    sem = st.selectbox("Semester:", semestri['id'], format_func=lambda x: "Zimski" if semestri[semestri['id']==x]['number'].values[0]==1 else "Poletni")
                    with st.form("nov_predmet"):
                        ime = st.text_input("Ime predmeta")
                        kratica = st.text_input("Kratica")
                        prof = st.text_input("Profesor")
                        ects = st.number_input("ECTS", value=6)
                        if st.form_submit_button("Dodaj Predmet"):
                            run_query("INSERT INTO subjects (semester_id, name, acronym, professor, ects) VALUES (?,?,?,?,?)", (sem, ime, kratica, prof, ects))
                            st.success("Predmet dodan!")
                else: st.warning("Ta letnik nima semestrov.")
            else: st.warning("Ta smer nima letnikov.")
    
    # --- GRADIVO ---
    elif tip == "Gradivo":
        st.info("Gradiva dodana tukaj bodo vidna **VSEM** strežnikom (Globalno).")
        preds = get_data("SELECT id, name FROM subjects ORDER BY name")
        if not preds.empty:
            p_id = st.selectbox("Predmet:", preds['id'], format_func=lambda x: preds[preds['id']==x]['name'].values[0])
            with st.form("novo_gradivo"):
                url = st.text_input("URL")
                opis = st.text_input("Opis")
                if st.form_submit_button("Dodaj Gradivo"):
                    run_query("INSERT INTO materials (subject_id, url, description, type) VALUES (?,?,?,?)", (p_id, url, opis, "Gradivo"))
                    st.success("Globalno gradivo dodano!")
        else: st.error("Ni predmetov.")

    # --- ROK ---
    elif tip == "Rok":
        st.info("Roki dodani tukaj bodo vidni **VSEM** strežnikom.")
        preds = get_data("SELECT id, name FROM subjects ORDER BY name")
        if not preds.empty:
            p_id = st.selectbox("Predmet:", preds['id'], format_func=lambda x: preds[preds['id']==x]['name'].values[0])
            with st.form("nov_rok"):
                tip_roka = st.selectbox("Tip", ["Izpit", "Kolokvij", "Vaje"])
                datum = st.date_input("Datum")
                opis = st.text_input("Opis")
                if st.form_submit_button("Dodaj Rok"):
                    run_query("INSERT INTO deadlines (subject_id, deadline_type, date_time, description) VALUES (?,?,?,?)", 
                              (p_id, tip_roka, datum.strftime("%Y-%m-%d"), opis))
                    st.success("Globalni rok dodan!")
        else: st.error("Ni predmetov.")