import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# --- KONFIGURACIJA ---
st.set_page_config(page_title="Discord Bot Admin", layout="wide", page_icon="🎓")
DB_FILE = 'studij.db'

# --- CSS STILI (MINIMALNI - LE ZA GUMBE) ---
st.markdown("""
<style>
    .stButton>button { 
        width: 100%; 
        border-radius: 8px; 
        font-weight: 600; 
    }
</style>
""", unsafe_allow_html=True)

# --- FUNKCIJE ZA BAZO ---
def run_query(query, params=()):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return True
    except sqlite3.Error as e:
        st.error(f"Napaka v bazi: {e}")
        return False

def get_data(query, params=()):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            return pd.read_sql(query, conn, params=params)
    except Exception:
        return pd.DataFrame()

# --- PAMETNO BRISANJE SMERI (CASCADING DELETE) ---
def delete_program_full(prog_id):
    """Izbriše smer in VSE, kar spada zraven (letnike, semestre, predmete, roke, gradiva)."""
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        
        # 1. Najdi vse letnike te smeri
        cur.execute("SELECT id FROM years WHERE program_id=?", (prog_id,))
        years = [r[0] for r in cur.fetchall()]
        
        for yid in years:
            # 2. Najdi vse semestre teh letnikov
            cur.execute("SELECT id FROM semesters WHERE year_id=?", (yid,))
            sems = [r[0] for r in cur.fetchall()]
            
            for sid in sems:
                # 3. Najdi vse predmete teh semestrov
                cur.execute("SELECT id FROM subjects WHERE semester_id=?", (sid,))
                subjs = [r[0] for r in cur.fetchall()]
                
                for sub_id in subjs:
                    # 4. Izbriši gradiva in roke
                    cur.execute("DELETE FROM materials WHERE subject_id=?", (sub_id,))
                    cur.execute("DELETE FROM deadlines WHERE subject_id=?", (sub_id,))
                
                # 5. Izbriši predmete
                cur.execute("DELETE FROM subjects WHERE semester_id=?", (sid,))
            
            # 6. Izbriši semestre
            cur.execute("DELETE FROM semesters WHERE year_id=?", (yid,))
        
        # 7. Izbriši letnike
        cur.execute("DELETE FROM years WHERE program_id=?", (prog_id,))
        
        # 8. Končno izbriši smer
        cur.execute("DELETE FROM study_programs WHERE id=?", (prog_id,))
        conn.commit()

# --- SIDEBAR ---
st.sidebar.title("🎓 Admin Panel")
menu = st.sidebar.radio("Meni:", ["🏠 Domov (Statistika)", "📝 Pregled in Urejanje", "➕ Dodajanje Podatkov"])
st.sidebar.markdown("---")
st.sidebar.info("Podatki so shranjeni v `studij.db`.")

# ==========================================
# 1. DOMOV (DASHBOARD)
# ==========================================
if menu == "🏠 Domov (Statistika)":
    st.title("📊 Pregled Stanja")
    
    test = get_data("SELECT name FROM sqlite_master WHERE type='table' AND name='subjects'")
    if test.empty:
        st.warning("⚠️ Baza še ni ustvarjena. Zaženi `main.py` vsaj enkrat.")
    else:
        try:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("📚 Predmeti", get_data("SELECT COUNT(*) as c FROM subjects")['c'][0])
            c2.metric("📂 Gradiva", get_data("SELECT COUNT(*) as c FROM materials")['c'][0])
            c3.metric("⏳ Roki", get_data("SELECT COUNT(*) as c FROM deadlines WHERE date_time >= DATE('now')")['c'][0])
            c4.metric("🎓 Smeri", get_data("SELECT COUNT(*) as c FROM study_programs")['c'][0])
        except: pass

        st.subheader("📅 Roki v naslednjih 7 dneh")
        upcoming = get_data("""
            SELECT s.name as 'Predmet', d.deadline_type as 'Tip', d.date_time as 'Datum', d.description as 'Opis'
            FROM deadlines d JOIN subjects s ON d.subject_id = s.id
            WHERE d.date_time BETWEEN DATE('now') AND DATE('now', '+7 days')
            ORDER BY d.date_time ASC
        """)
        
        if not upcoming.empty:
            st.dataframe(upcoming, use_container_width=True, hide_index=True)
        else:
            st.info("Ni rokov v kratkem.")

# ==========================================
# 2. PREGLED IN UREJANJE
# ==========================================
elif menu == "📝 Pregled in Urejanje":
    st.title("📝 Upravljanje Podatkov")
    tab1, tab2, tab3, tab4 = st.tabs(["🎓 Smeri", "📚 Predmeti", "📂 Gradiva", "⏳ Roki"])

    # --- TAB 1: SMERI (NOVO!) ---
    with tab1:
        st.subheader("Seznam študijskih smeri")
        df_prog = get_data("SELECT id, name as 'Ime Smeri' FROM study_programs")
        st.dataframe(df_prog, use_container_width=True, hide_index=True)
        
        st.divider()
        with st.expander("🗑️ Izbriši smer (POZOR!)"):
            if not df_prog.empty:
                st.warning("⚠️ OPOZORILO: Če izbrišeš smer, se izbrišejo VSI letniki, predmeti, gradiva in roki te smeri!")
                prog_del = st.selectbox("Izberi smer za izbris:", df_prog['id'], format_func=lambda x: df_prog[df_prog['id']==x]['Ime Smeri'].values[0])
                
                if st.button("🔴 Dokončno Izbriši Smer"):
                    delete_program_full(prog_del)
                    st.success("Smer in vsi podatki uspešno izbrisani.")
                    st.rerun()
            else:
                st.info("Ni vnešenih smeri.")

    # --- TAB 2: PREDMETI ---
    with tab2:
        col_search, _ = st.columns([2,1])
        search = col_search.text_input("🔍 Išči predmet:", key="s_sub")
        
        q = """
            SELECT s.id, s.name as 'Ime', s.acronym as 'Kratica', sp.name as 'Smer', 
                   y.number || '. letnik' as 'Letnik', s.ects as 'ECTS'
            FROM subjects s
            JOIN semesters sem ON s.semester_id = sem.id
            JOIN years y ON sem.year_id = y.id
            JOIN study_programs sp ON y.program_id = sp.id
        """
        if search: q += f" WHERE s.name LIKE '%{search}%' OR s.acronym LIKE '%{search}%'"
        
        df = get_data(q)
        st.dataframe(df, use_container_width=True, hide_index=True)

        c1, c2 = st.columns(2)
        with c1.expander("✏️ Uredi predmet"):
            if not df.empty:
                sid = st.selectbox("Izberi:", df['id'], format_func=lambda x: df[df['id']==x]['Ime'].values[0])
                curr = get_data(f"SELECT * FROM subjects WHERE id={sid}").iloc[0]
                with st.form("ed_sub"):
                    np = st.text_input("Profesor", value=curr['professor'] if curr['professor'] else "")
                    na = st.text_input("Asistenti", value=curr['assistants'] if curr['assistants'] else "")
                    ne = st.number_input("ECTS", value=int(curr['ects']) if curr['ects'] else 6)
                    if st.form_submit_button("Shrani"):
                        run_query("UPDATE subjects SET professor=?, assistants=?, ects=? WHERE id=?", (np, na, ne, sid))
                        st.success("Shranjeno!"); st.rerun()
        
        with c2.expander("🗑️ Izbriši predmet"):
            if not df.empty:
                del_id = st.selectbox("Izberi za izbris:", df['id'], key="d_s", format_func=lambda x: df[df['id']==x]['Ime'].values[0])
                if st.button("Izbriši Predmet", type="primary"):
                    run_query("DELETE FROM materials WHERE subject_id=?", (del_id,))
                    run_query("DELETE FROM deadlines WHERE subject_id=?", (del_id,))
                    run_query("DELETE FROM subjects WHERE id=?", (del_id,))
                    st.success("Izbrisano."); st.rerun()

    # --- TAB 3: GRADIVA (IZBOLJŠANO) ---
    with tab3:
        # Preverjanje za guild_id
        cols = get_data("PRAGMA table_info(materials)")
        has_guild = 'guild_id' in cols['name'].values if not cols.empty else False
        
        # Zdaj prikažemo tudi SMER, da veš kam gradivo spada
        q_m = """
            SELECT m.id, s.name as 'Predmet', sp.name as 'Smer', m.description as 'Opis', m.url as 'URL'
        """
        if has_guild: q_m += ", CASE WHEN m.guild_id IS NULL THEN '🌍 Globalno' ELSE '🔒 Zasebno' END as 'Tip'"
        q_m += """
            FROM materials m 
            JOIN subjects s ON m.subject_id = s.id
            JOIN semesters sem ON s.semester_id = sem.id
            JOIN years y ON sem.year_id = y.id
            JOIN study_programs sp ON y.program_id = sp.id
        """

        df_m = get_data(q_m)
        st.dataframe(df_m, use_container_width=True, hide_index=True)
        
        with st.expander("🗑️ Izbriši gradivo"):
            if not df_m.empty:
                mid = st.selectbox("Gradivo:", df_m['id'], format_func=lambda x: f"{df_m[df_m['id']==x]['Opis'].values[0]} ({df_m[df_m['id']==x]['Predmet'].values[0]})")
                if st.button("Izbriši Gradivo"):
                    run_query("DELETE FROM materials WHERE id=?", (mid,))
                    st.success("Izbrisano."); st.rerun()
            else:
                st.info("Ni gradiv.")

    # --- TAB 4: ROKI ---
    with tab4:
        cols_d = get_data("PRAGMA table_info(deadlines)")
        has_guild_d = 'guild_id' in cols_d['name'].values if not cols_d.empty else False

        q_r = "SELECT d.id, s.name as 'Predmet', d.deadline_type as 'Tip', d.date_time as 'Datum'"
        if has_guild_d: q_r += ", CASE WHEN d.guild_id IS NULL THEN '🌍 Globalno' ELSE '🔒 Zasebno' END as 'Vidnost'"
        q_r += " FROM deadlines d JOIN subjects s ON d.subject_id = s.id ORDER BY d.date_time DESC"

        df_r = get_data(q_r)

        def style_expired(row):
            try:
                if datetime.strptime(row['Datum'], "%Y-%m-%d").date() < datetime.now().date():
                    return ['color: #ff4b4b; font-weight: bold'] * len(row)
            except: pass
            return [''] * len(row)

        st.dataframe(df_r.style.apply(style_expired, axis=1), use_container_width=True, hide_index=True)

        with st.expander("🗑️ Izbriši rok"):
            if not df_r.empty:
                rid = st.selectbox("Rok:", df_r['id'], format_func=lambda x: f"{df_r[df_r['id']==x]['Predmet'].values[0]} ({df_r[df_r['id']==x]['Datum'].values[0]})")
                if st.button("Izbriši Rok"):
                    run_query("DELETE FROM deadlines WHERE id=?", (rid,))
                    st.success("Izbrisano."); st.rerun()

# ==========================================
# 3. DODAJANJE
# ==========================================
elif menu == "➕ Dodajanje Podatkov":
    st.title("➕ Dodajanje")
    tip = st.selectbox("Kaj želiš dodati?", ["Nova Smer (Avtomatsko)", "Predmet", "Gradivo", "Rok"])

    if tip == "Nova Smer (Avtomatsko)":
        with st.form("auto_smer"):
            ime = st.text_input("Ime smeri")
            st_let = st.number_input("Št. letnikov", 1, 6, 3)
            if st.form_submit_button("Ustvari"):
                if ime:
                    try:
                        with sqlite3.connect(DB_FILE) as conn:
                            cur = conn.cursor()
                            cur.execute("INSERT INTO study_programs (name) VALUES (?)", (ime,))
                            pid = cur.lastrowid
                            for i in range(1, st_let + 1):
                                cur.execute("INSERT INTO years (program_id, number) VALUES (?, ?)", (pid, i))
                                yid = cur.lastrowid
                                cur.execute("INSERT INTO semesters (year_id, number) VALUES (?, ?)", (yid, 1))
                                cur.execute("INSERT INTO semesters (year_id, number) VALUES (?, ?)", (yid, 2))
                            conn.commit()
                        st.success(f"Smer {ime} ustvarjena!")
                    except: st.error("Napaka ali smer že obstaja.")

    elif tip == "Predmet":
        smeri = get_data("SELECT id, name FROM study_programs")
        if smeri.empty: st.error("Ni smeri.")
        else:
            sid = st.selectbox("Smer:", smeri['id'], format_func=lambda x: smeri[smeri['id']==x]['name'].values[0])
            letniki = get_data("SELECT id, number FROM years WHERE program_id=?", (sid,))
            if not letniki.empty:
                lid = st.selectbox("Letnik:", letniki['id'], format_func=lambda x: str(letniki[letniki['id']==x]['number'].values[0]))
                sems = get_data("SELECT id, number FROM semesters WHERE year_id=?", (lid,))
                if not sems.empty:
                    sem_id = st.selectbox("Semester:", sems['id'], format_func=lambda x: "Zimski" if sems[sems['id']==x]['number'].values[0]==1 else "Poletni")
                    with st.form("add_sub"):
                        ime = st.text_input("Ime")
                        krat = st.text_input("Kratica")
                        prof = st.text_input("Profesor")
                        ects = st.number_input("ECTS", value=6)
                        if st.form_submit_button("Dodaj"):
                            run_query("INSERT INTO subjects (semester_id, name, acronym, professor, ects) VALUES (?,?,?,?,?)", (sem_id, ime, krat, prof, ects))
                            st.success("Dodano!")
            else: st.warning("Ta smer nima letnikov.")

    elif tip in ["Gradivo", "Rok"]:
        preds = get_data("SELECT id, name FROM subjects ORDER BY name")
        if preds.empty: st.error("Ni predmetov.")
        else:
            pid = st.selectbox("Predmet:", preds['id'], format_func=lambda x: preds[preds['id']==x]['name'].values[0])
            if tip == "Gradivo":
                with st.form("add_m"):
                    url = st.text_input("URL")
                    opis = st.text_input("Opis")
                    if st.form_submit_button("Dodaj"):
                        run_query("INSERT INTO materials (subject_id, url, description, type) VALUES (?,?,?,?)", (pid, url, opis, "Gradivo"))
                        st.success("Dodano!")
            else:
                with st.form("add_r"):
                    rtip = st.selectbox("Tip", ["Izpit", "Kolokvij", "Vaje"])
                    dat = st.date_input("Datum")
                    opis = st.text_input("Opis")
                    if st.form_submit_button("Dodaj"):
                        run_query("INSERT INTO deadlines (subject_id, deadline_type, date_time, description) VALUES (?,?,?,?)", (pid, rtip, dat.strftime("%Y-%m-%d"), opis))
                        st.success("Dodano!")