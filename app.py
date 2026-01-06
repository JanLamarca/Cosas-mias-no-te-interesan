import os
import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
import datetime

import streamlit as st

import streamlit as st

USER_LOGIN = st.secrets["Jan Lamarca"]["user"]
PIN_LOGIN = st.secrets["1234"]["pin"]

# --- CONFIG ---
SHEET_NAME = "Gestión Financiera"  # Name of your Google Sheet file
SHEET_CARTERA = "Cartera"
SHEET_DINERS = "Diners"
SHEET_HISTORY = "Historial" # Nombre de la pestaña

# --- LOGIN CONFIG ---
# Se recomienda usar Streamlit Secrets en la nube. 
# Si no existen, usa estos valores por defecto (solo para pruebas locales).

# --- AUTH & CONNECTION ---
def get_connection():
    """Establishes connection to Google Sheets with robust key cleaning."""
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    try:
        # Prioridad 1: Streamlit Secrets (Para Cloud)
        if "gcp_service_account" in st.secrets:
            # Creamos una copia real para no mutar el objeto original de Streamlit
            creds_dict = {k: st.secrets["gcp_service_account"][k] for k in st.secrets["gcp_service_account"]}
            
            # LIMPIEZA TOTAL Y AGRESIVA DE LA CLAVE
            if "private_key" in creds_dict:
                pk = creds_dict["private_key"].replace("\\n", "\n")
                lines = [l.strip() for l in pk.splitlines() if l.strip()]
                creds_dict["private_key"] = "\n".join(lines)
            
            creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
            
        # Prioridad 2: Archivo local key.json (Para local)
        elif os.path.exists("key.json"):
            creds = Credentials.from_service_account_file("key.json", scopes=scope)
        else:
            return None

        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return None

# --- UI LOGIN ---
def login():
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        st.set_page_config(page_title="Login - Finanzas", page_icon="🔒")
        
        # Centrar el formulario de login
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.title("🔒 Acceso Privado")
            user_input = st.text_input("Usuario")
            pin_input = st.text_input("PIN (Contraseña)", type="password")
            
            if st.button("Entrar", use_container_width=True):
                if user_input == USER_LOGIN and pin_input == PIN_LOGIN:
                    st.session_state.logged_in = True
                    st.rerun()
                else:
                    st.error("Usuario o PIN incorrectos")
        return False
    return True

# --- HELPER FUNCTIONS ---
def parse_euro(value_str):
    """Converts '1.000,50 €' string to 1000.50 float."""
    if not isinstance(value_str, str): return float(value_str or 0)
    clean = value_str.replace("€", "").replace(".", "").replace(",", ".").strip()
    try: return float(clean)
    except ValueError: return 0.0

def format_euro(value_float):
    """Converts 1000.50 float to '1.000,50 €' string."""
    if value_float is None: return "-"
    return "{:,.2f} €".format(value_float).replace(",", "X").replace(".", ",").replace("X", ".")

def get_data(client, worksheet_name):
    """Fetches data from a worksheet and returns a DataFrame and the worksheet object."""
    try:
        sh = client.open(SHEET_NAME)
        ws = sh.worksheet(worksheet_name)
        data = ws.get_all_values()
        if not data: return None, ws
        df = pd.DataFrame(data[1:], columns=data[0]) # Assume first row is header
        return df, ws
    except Exception as e:
        st.error(f"Error leyendo '{worksheet_name}': {e}")
        return None, None

def update_history(client, date_str, preu, pagat, canvi, notes, balance):
    """Adds a row to the history sheet."""
    try:
        sh = client.open(SHEET_NAME)
        
        # Intentar encontrar la hoja de historial de forma más flexible
        all_ws = [w.title for w in sh.worksheets()]
        target = SHEET_HISTORY if SHEET_HISTORY in all_ws else None
        if not target:
            for t in all_ws:
                if "Historial" in t or ("Gastos" in t and "Ingresos" in t):
                    target = t; break
        
        if not target:
            st.error("No se encontró la pestaña de historial.")
            return

        ws = sh.worksheet(target)
        
        # Columns: Data, Preu/Afegit, Pagat, Canvi rebut, Total Cartera/Guardiola, Notes
        row = [date_str, format_euro(preu), format_euro(pagat) if pagat else "-", format_euro(canvi) if canvi else "-", format_euro(balance), notes]
        ws.append_row(row)
        st.toast("✅ Historial actualizado")
    except Exception as e:
        st.error(f"Error historial: {e}")

# --- APP LOGIC ---
if not login(): st.stop()

client = get_connection()

if client:
    st.title("💰 Gestión Financiera")
    
    # 1. READ DATA
    df_cartera, ws_cartera = get_data(client, SHEET_CARTERA)
    df_diners, ws_diners = get_data(client, SHEET_DINERS)
    
    if df_cartera is not None and df_diners is not None:
        
        # Calculate Totals
        # Assuming structure: Monedes, Quantes?, Total
        # But 'Total' column in sheet might be a formula or static text.
        # We recalculate for display to be safe.
        
        def calc_total(df):
            return sum(parse_euro(r['Monedes']) * (int(r['Quantes?']) if str(r['Quantes?']).isdigit() else 0) for _, r in df.iterrows())

        total_c = calc_total(df_cartera)
        total_d = calc_total(df_diners)
        
        c1, c2 = st.columns(2)
        c1.metric("Cartera", format_euro(total_c))
        c2.metric("Diners (Ahorros)", format_euro(total_d))
        st.caption(f"Salto Total: {format_euro(total_c + total_d)}")

        st.divider()

        # 3. SELECCIÓN DE CUENTA (Botones grandes tipo Web App)
        st.subheader("📍 ¿De dónde sale/entra el dinero?")
        source = st.segmented_control(
            "Cuenta:", 
            ["Cartera", "Diners"], 
            default="Cartera",
            selection_mode="single",
            key="main_source_selector"
        )
        
        st.divider()

        # 4. FORMULARIO DE MOVIMIENTO
        st.subheader(f"📝 Registro en {source}")
        
        with st.form("main_form", clear_on_submit=False):
            t_type = st.radio("Tipo:", ["Gasto 📤", "Ingreso 📥"], horizontal=True)
            
            col_a, col_b = st.columns(2)
            amount = col_a.number_input("Importe (€):", min_value=0.0, format="%.2f", step=0.01, value=0.0)
            pagat = col_b.number_input("Pagado con (€) [Opcional]:", min_value=0.0, format="%.2f", step=0.01, value=0.0)
            
            notes = st.text_input("Concepto:", placeholder="Ej: Supermercado...")
            
            st.markdown("---")
            st.markdown("### 🪙 Monedas y Billetes")
            st.caption("Si pones el Importe en 0, se calculará sumando lo que marques aquí.")
            
            active_df = df_cartera if source == "Cartera" else df_diners
            changes = {}
            
            # Preparar denominaciones (ordenadas de mayor a menor)
            denoms = []
            for idx, r in active_df.iterrows():
                denoms.append((idx, parse_euro(r['Monedes']), r['Monedes']))
            denoms.sort(key=lambda x: x[1], reverse=True)

            # Layout de rejilla para móvil con botones + y - nativos de Streamlit
            cols = st.columns(3)
            for i, (idx, val, txt) in enumerate(denoms):
                if not txt or txt == "???": continue
                with cols[i % 3]:
                    c_val = st.number_input(
                        f"{txt}", 
                        min_value=-50, 
                        max_value=50, 
                        step=1, 
                        value=0,
                        key=f"d_{source}_{idx}"
                    )
                    if c_val != 0:
                        changes[idx] = c_val

            submitted = st.form_submit_button("REGISTRAR MOVIMIENTO 🚀", use_container_width=True, type="primary")

            if submitted:
                # Calcular total desde el desglose si la cantidad es 0
                calc_val_sum = 0.0
                for idx, delta in changes.items():
                    denom_val = parse_euro(active_df.at[idx, 'Monedes'])
                    calc_val_sum += denom_val * abs(delta)
                
                final_amt = amount
                if amount == 0 and calc_val_sum > 0:
                    final_amt = calc_val_sum
                    st.toast(f"✅ Total calculado: {format_euro(final_amt)}")
                
                is_exp = "Gasto" in t_type
                
                if final_amt <= 0:
                    st.error("Error: Introduce un importe o selecciona billetes.")
                else:
                    # Lógica de registro
                    
                    # 1. Update CSV/Sheet Logic
                    current_ws = ws_cartera if source == "Cartera" else ws_diners
                    current_df = df_cartera if source == "Cartera" else df_diners
                    
                    if changes:
                        # Process updates
                        for idx, delta in changes.items():
                            # INTUICIÓN: En un GASTO, poner '1' significa que quitas 1 billete.
                            # En un INGRESO, poner '1' significa que añades 1 billete.
                            real_delta = -delta if is_exp else delta
                            
                            # Calculate new quantity
                            current_qty = int(current_df.at[idx, 'Quantes?'])
                            new_q = current_qty + real_delta
                            
                            # Validation
                            if new_q < 0:
                                st.error(f"Error: No tienes suficientes {current_df.at[idx, 'Monedes']}")
                                st.stop()
                                
                            # Update quantity (Col 2)
                            current_ws.update_cell(idx + 2, 2, new_q)
                            # Update Total (Col 3)
                            s_total = parse_euro(current_df.at[idx, 'Monedes']) * new_q
                            current_ws.update_cell(idx + 2, 3, format_euro(s_total))

                        st.success(f"Stock actualizado.")
                    elif amount == 0: # If no amount and no changes, it's an error
                        st.error("No se ha especificado un importe ni cambios en el stock.")
                        st.stop()
                    
                    # 2. Update History
                    # We use the calculated total_cartera AFTER the change? Or before?
                    # Usually After.
                    current_balance = total_c if source == "Cartera" else total_d
                    new_val = current_balance + (-final_amt if is_exp else final_amt)
                    
                    canvi = None
                    if pagat > 0 and is_exp:
                        canvi = pagat - final_amt
                        if canvi < 0:
                            st.warning(f"El pago ({format_euro(pagat)}) es menor que el importe ({format_euro(final_amt)}).")
                    
                    update_history(client, datetime.datetime.now().strftime("%d/%m/%y"), 
                                   -final_amt if is_exp else final_amt,
                                   pagat if pagat > 0 else None,
                                   canvi, notes, new_val)
                    st.success("¡Hecho! Recargando...")
                    st.rerun()
else:
    st.info("Conectando con Google Sheets...")



