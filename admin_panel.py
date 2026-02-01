import streamlit as st
import sqlite3
import pandas as pd

# Konfiguracija strani
st.set_page_config(page_title="Discord Bot Admin", layout="wide", page_icon="🎓")
DB_FILE = 'studij.db'

# --- CSS STILI (Za lepši izgled) ---
st.markdown("""
<style>
    .stButton>button { width: 100%; border-radius: 5px; }
    .stSelectbox { margin-bottom: 20px; }
    div[data-testid="stExpander"] details summary p { font-size: 1.1rem; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

st.title("🎓 Nadzorna Plošča (Admin Panel)")

# --- POVEZAVA Z BAZO ---
def run_query(query, params=()):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()

def get_data(query, params=()):
    with sqlite3.connect(DB_FILE) as conn:
        return pd.read_sql(query, conn, params=params)

# --- GLAVNI MENI (SIDEBAR) ---
st.sidebar.header("Navigacija")
akcija = st.sidebar.radio("Izberi akcijo:", ["Pregled in Urejanje", "Dodajanje Podatkov"])

# ==========================================
# 1. PREGLED IN UREJANJE (BRISANJE)
# ==========================================
if akcija == "Pregled in Urejanje":
    
    # Uporabimo zavihke za lepši pregled
    tab1, tab2, tab3 = st.tabs(["📚 Predmeti", "📂 Gradiva", "⏳ Roki"])

    # --- TAB 1: PREDMETI ---
    with tab1:
        st.subheader("Seznam vseh predmetov")
        
        # Iskanje
        search = st.text_input("🔍 Išči predmet (ime ali kratica):", key="search_subj")
        query = """
            SELECT s.id, s.name as 'Ime', s.acronym as 'Kratica', s.ects as 'ECTS', 
                   s.professor as 'Profesor', y.number || '. letnik' as 'Letnik', 
                   CASE WHEN sem.number = 1 THEN 'Zimski' ELSE 'Poletni' END as 'Semester',
                   sp.name as 'Smer'
            FROM subjects s
            JOIN semesters sem ON s.semester_id = sem.id
            JOIN years y ON sem.year_id = y.id
            JOIN study_programs sp ON y.program_id = sp.id
        """
        if search:
            query += f" WHERE s.name LIKE '%{search}%' OR s.acronym LIKE '%{search}%'"
        
        df_predmeti = get_data(query)
        st.dataframe(df_predmeti, use_container_width=True, hide_index=True)

        # Brisanje predmeta
        st.divider()
        with st.expander("🗑️ Izbriši predmet"):
            st.warning("OPOZORILO: Če izbrišeš predmet, se izbrišejo tudi vsa njegova gradiva in roki!")
            options = df_predmeti.apply(lambda x: f"{x['id']}: {x['Ime']} ({x['Kratica']})", axis=1)
            to_delete = st.selectbox("Izberi predmet za izbris:", options, key="del_subj_sel")
            
            if st.button("Izbriši izbran predmet", type="primary"):
                if to_delete:
                    pid = to_delete.split(":")[0]
                    # Najprej izbrišemo odvisne podatke (roki, materiali)
                    run_query("DELETE FROM materials WHERE subject_id = ?", (pid,))
                    run_query("DELETE FROM deadlines WHERE subject_id = ?", (pid,))
                    run_query("DELETE FROM subjects WHERE id = ?", (pid,))
                    st.success("Predmet izbrisan! (Osveži stran)")
                    st.rerun()

    # --- TAB 2: GRADIVA ---
    with tab2:
        st.subheader("Baza gradiv")
        query_mat = """
            SELECT m.id, s.name as 'Predmet', m.description as 'Opis', m.url as 'Povezava'
            FROM materials m
            JOIN subjects s ON m.subject_id = s.id
            ORDER BY s.name
        """
        df_mat = get_data(query_mat)
        
        # Prikaz kot linki v tabeli
        st.data_editor(
            df_mat, 
            column_config={"Povezava": st.column_config.LinkColumn("Povezava")},
            use_container_width=True,
            hide_index=True,
            disabled=True
        )

        st.divider()
        with st.expander("🗑️ Izbriši gradivo"):
            if not df_mat.empty:
                opts_mat = df_mat.apply(lambda x: f"{x['id']}: {x['Opis']} ({x['Predmet']})", axis=1)
                del_mat = st.selectbox("Izberi gradivo:", opts_mat)
                if st.button("Izbriši gradivo", type="primary"):
                    mid = del_mat.split(":")[0]
                    run_query("DELETE FROM materials WHERE id = ?", (mid,))
                    st.success("Gradivo izbrisano!")
                    st.rerun()
            else:
                st.info("Ni gradiv.")

    # --- TAB 3: ROKI ---
    with tab3:
        st.subheader("Koledar rokov")
        query_roki = """
            SELECT d.id, s.name as 'Predmet', d.deadline_type as 'Tip', 
                   d.date_time as 'Datum', d.description as 'Opis'
            FROM deadlines d
            JOIN subjects s ON d.subject_id = s.id
            ORDER BY d.date_time DESC
        """
        df_roki = get_data(query_roki)
        st.dataframe(df_roki, use_container_width=True, hide_index=True)

        st.divider()
        with st.expander("🗑️ Izbriši rok"):
            if not df_roki.empty:
                opts_rok = df_roki.apply(lambda x: f"{x['id']}: {x['Predmet']} - {x['Tip']} ({x['Datum']})", axis=1)
                del_rok = st.selectbox("Izberi rok:", opts_rok)
                if st.button("Izbriši rok", type="primary"):
                    rid = del_rok.split(":")[0]
                    run_query("DELETE FROM deadlines WHERE id = ?", (rid,))
                    st.success("Rok izbrisan!")
                    st.rerun()
            else:
                st.info("Ni vnešenih rokov.")


# ==========================================
# 2. DODAJANJE PODATKOV
# ==========================================
elif akcija == "Dodajanje Podatkov":
    
    st.sidebar.markdown("---")
    tip_vnosa = st.sidebar.radio("Kaj želiš dodati?", ["Nov Predmet", "Novo Gradivo", "Nov Rok (Izpit/Kolokvij)"])

    # --- DODAJ PREDMET ---
    if tip_vnosa == "Nov Predmet":
        st.header("➕ Dodaj nov predmet")
        
        # Kaskadni meniji za lokacijo predmeta
        smeri = get_data("SELECT id, name FROM study_programs")
        if smeri.empty:
            st.error("Najprej moraš dodati smeri preko Discord ukaza !nova_smer")
        else:
            col1, col2, col3 = st.columns(3)
            with col1:
                smer_id = st.selectbox("1. Smer:", smeri['id'], format_func=lambda x: smeri[smeri['id']==x]['name'].values[0])
            
            with col2:
                letniki = get_data("SELECT id, number FROM years WHERE program_id = ?", (smer_id,))
                if not letniki.empty:
                    letnik_id = st.selectbox("2. Letnik:", letniki['id'], format_func=lambda x: f"{letniki[letniki['id']==x]['number'].values[0]}. letnik")
                else:
                    st.warning("Ni letnikov.")
                    letnik_id = None
            
            with col3:
                if letnik_id:
                    semestri = get_data("SELECT id, number FROM semesters WHERE year_id = ?", (letnik_id,))
                    if not semestri.empty:
                        sem_id = st.selectbox("3. Semester:", semestri['id'], format_func=lambda x: "Zimski" if semestri[semestri['id']==x]['number'].values[0]==1 else "Poletni")
                    else:
                        st.warning("Ni semestrov.")
                        sem_id = None
                else:
                    sem_id = None

            if sem_id:
                st.markdown("---")
                with st.form("add_subj_form"):
                    c1, c2 = st.columns(2)
                    ime = c1.text_input("Ime predmeta")
                    kratica = c2.text_input("Kratica (npr. OPA, MAT)")
                    
                    c3, c4, c5 = st.columns(3)
                    prof = c3.text_input("Profesor")
                    asist = c4.text_input("Asistenti")
                    ects = c5.number_input("ECTS točke", 1, 30, 6)
                    
                    submitted = st.form_submit_button("💾 Shrani Predmet")
                    if submitted and ime and kratica:
                        run_query("""
                            INSERT INTO subjects (semester_id, name, acronym, professor, assistants, ects)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (sem_id, ime, kratica, prof, asist, ects))
                        st.success(f"✅ Predmet **{ime}** uspešno dodan!")

    # --- DODAJ GRADIVO ---
    elif tip_vnosa == "Novo Gradivo":
        st.header("➕ Dodaj gradivo")
        
        # Izbira predmeta (z iskanjem v dropdownu)
        vsi_predmeti = get_data("SELECT id, name, acronym FROM subjects ORDER BY name")
        
        if not vsi_predmeti.empty:
            predmet_id = st.selectbox(
                "Izberi predmet:", 
                vsi_predmeti['id'], 
                format_func=lambda x: f"{vsi_predmeti[vsi_predmeti['id']==x]['name'].values[0]} ({vsi_predmeti[vsi_predmeti['id']==x]['acronym'].values[0]})"
            )
            
            with st.form("add_mat_form"):
                url = st.text_input("URL Povezava (https://...)")
                opis = st.text_input("Opis gradiva (npr. Zapiski predavanj)")
                
                submitted = st.form_submit_button("💾 Dodaj Gradivo")
                if submitted and url and opis:
                    run_query("INSERT INTO materials (subject_id, url, description, type) VALUES (?, ?, ?, ?)", 
                              (predmet_id, url, opis, "Gradivo"))
                    st.success("✅ Gradivo uspešno dodano!")
        else:
            st.error("Ni predmetov v bazi.")

    # --- DODAJ ROK ---
    elif tip_vnosa == "Nov Rok (Izpit/Kolokvij)":
        st.header("➕ Dodaj rok")
        
        vsi_predmeti = get_data("SELECT id, name, acronym FROM subjects ORDER BY name")
        
        if not vsi_predmeti.empty:
            predmet_id = st.selectbox(
                "Izberi predmet:", 
                vsi_predmeti['id'], 
                format_func=lambda x: f"{vsi_predmeti[vsi_predmeti['id']==x]['name'].values[0]}"
            )
            
            with st.form("add_deadline_form"):
                col1, col2 = st.columns(2)
                tip = col1.selectbox("Tip roka", ["Izpit", "Kolokvij", "Vaje", "Oddaja naloge"])
                datum = col2.date_input("Datum roka")
                opis = st.text_input("Opis (npr. Prvi rok, Zimski rok)")
                
                submitted = st.form_submit_button("💾 Dodaj Rok")
                if submitted:
                    db_date = datum.strftime("%Y-%m-%d")
                    run_query("INSERT INTO deadlines (subject_id, deadline_type, date_time, description) VALUES (?, ?, ?, ?)", 
                              (predmet_id, tip, db_date, opis))
                    st.success("✅ Rok dodan! Bot bo avtomatsko obvestil študente.")
        else:
            st.error("Ni predmetov v bazi.")