import os
import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
import datetime

# --- CONFIG ---
SHEET_NAME = "Gestión Financiera"  # Name of your Google Sheet file
SHEET_CARTERA = "Cartera"
SHEET_DINERS = "Diners"
SHEET_HISTORY = "Gastos/Ingresos"

# --- LOGIN CONFIG ---
# Se recomienda usar Streamlit Secrets en la nube. 
# Si no existen, usa estos valores por defecto (solo para pruebas locales).
USER_LOGIN = st.secrets.get("credentials", {}).get("user", "Janiito")
PIN_LOGIN = st.secrets.get("credentials", {}).get("pin", "1119")

# --- AUTH & CONNECTION ---
def get_connection():
    """Establishes connection to Google Sheets with ultra-robust key cleaning."""
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    try:
        # Prioridad 1: Streamlit Secrets (Para Cloud)
        if "gcp_service_account" in st.secrets:
            # Creamos una copia real para no mutar el objeto original de Streamlit
            creds_dict = {}
            for key in st.secrets["gcp_service_account"]:
                creds_dict[key] = st.secrets["gcp_service_account"][key]
            
            # LIMPIEZA TOTAL Y AGRESIVA DE LA CLAVE
            if "private_key" in creds_dict:
                pk = creds_dict["private_key"]
                
                # 1. Normalizar saltos de línea (convertir \n texto a salto real)
                pk = pk.replace("\\n", "\n")
                
                # 2. Limpiar cada línea individualmente y reconstruir
                lines = pk.splitlines()
                clean_lines = []
                for line in lines:
                    clean_line = line.strip()
                    if clean_line:
                        clean_lines.append(clean_line)
                
                creds_dict["private_key"] = "\n".join(clean_lines)
            
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

# --- INICIO APP ---
if not login():
    st.stop()

# --- HELPER FUNCTIONS ---
def parse_euro(value_str):
    """Converts '1.000,50 €' string to 1000.50 float."""
    if not isinstance(value_str, str):
        return float(value_str or 0)
    clean = value_str.replace("€", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(clean)
    except ValueError:
        return 0.0

def format_euro(value_float):
    """Converts 1000.50 float to '1.000,50 €' string."""
    return "{:,.2f} €".format(value_float).replace(",", "X").replace(".", ",").replace("X", ".")

def get_data(client, worksheet_name):
    """Fetches data from a worksheet and returns a DataFrame and the worksheet object."""
    try:
        sh = client.open(SHEET_NAME)
        ws = sh.worksheet(worksheet_name)
        data = ws.get_all_values()
        df = pd.DataFrame(data[1:], columns=data[0]) # Assume first row is header
        return df, ws
    except Exception as e:
        st.error(f"No se pudo leer la hoja '{worksheet_name}'. Error: {e}")
        return None, None

def update_history(client, date_str, amount, notes, total_cartera):
    """Appends a row to the history sheet."""
    try:
        sh = client.open(SHEET_NAME)
        
        # Intentar encontrar la hoja de historial de forma más flexible
        all_worksheets = [w.title for w in sh.worksheets()]
        
        # Si no existe tal cual, buscamos una que contenga "Gastos" e "Ingresos"
        matched_ws = None
        if SHEET_HISTORY in all_worksheets:
            matched_ws = SHEET_HISTORY
        else:
            for title in all_worksheets:
                if "Gastos" in title and ("Ingresos" in title or "Ingresso" in title):
                    matched_ws = title
                    break
        
        if not matched_ws:
            st.error(f"❌ No se encontró la pestaña de historial.")
            st.info(f"Pestañas disponibles: {', '.join(all_worksheets)}")
            st.warning(f"Asegúrate de que una pestaña se llame exactamente '{SHEET_HISTORY}'")
            return

        ws = sh.worksheet(matched_ws)
        
        # Columns: Data, Preu/Afegit, Pagat, Canvi rebut, Total Cartera, Notes
        row = [
            date_str, 
            format_euro(amount), 
            "-", 
            "-", 
            format_euro(total_cartera), 
            notes
        ]
        ws.append_row(row)
        st.toast("✅ Historial actualizado en la hoja de cálculo")
    except Exception as e:
        st.error(f"Error escribiendo historial: {e}")

# --- APP LOGIC ---
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
        
        def calculate_total_from_df(df):
            total = 0.0
            for index, row in df.iterrows():
                val = parse_euro(row['Monedes'])
                qty = int(row['Quantes?']) if str(row['Quantes?']).isdigit() else 0
                total += val * qty
            return total

        total_cartera = calculate_total_from_df(df_cartera)
        total_diners = calculate_total_from_df(df_diners)
        grand_total = total_cartera + total_diners

        # 2. DISPLAY TOTALS (Hero Section)
        col1, col2 = st.columns(2)
        col1.metric("Cartera (Diario)", format_euro(total_cartera))
        col2.metric("Diners (Ahorro)", format_euro(total_diners))
        st.caption(f"Total Global: {format_euro(grand_total)}")

        st.divider()

        # 3. SELECCIÓN DE CUENTA (Botones grandes tipo Web App)
        st.subheader("📍 ¿Qué cuenta vas a usar?")
        source_choice = st.segmented_control(
            "Selecciona cuenta:", 
            ["Cartera", "Diners"], 
            default="Cartera",
            selection_mode="single",
            key="main_source_selector"
        )
        
        st.divider()

        # 4. FORMULARIO DE MOVIMIENTO
        st.subheader(f"📝 Registro en {source_choice}")
        
        with st.form("transaction_form", clear_on_submit=False):
            type_choice = st.radio("Tipo de movimiento:", ["Gasto 📤", "Ingreso 📥"], horizontal=True)
            
            st.info("💡 Consejo: Si marcas los billetes abajo y dejas la cantidad en 0, se calculará automáticamente el total.")
            amount = st.number_input("Cantidad total (€):", min_value=0.0, format="%.2f", step=0.50, value=0.0)
            notes = st.text_input("Concepto / Notas:", placeholder="Ej: Comida, Sueldo, Regalo...")
            
            st.markdown("---")
            st.markdown("### 🪙 Desglose de billetes/monedas")
            update_stock = st.toggle("¿Actualizar stock?", value=True)
            
            active_df = df_cartera if source_choice == "Cartera" else df_diners
            changes = {}
            
            # Preparar denominaciones (ordenadas de mayor a menor)
            denoms = []
            for idx, row in active_df.iterrows():
                denoms.append((idx, parse_euro(row['Monedes']), row['Monedes']))
            denoms.sort(key=lambda x: x[1], reverse=True)

            if update_stock:
                # Layout de rejilla para móvil con botones + y - nativos de Streamlit
                cols = st.columns(3)
                for i, (idx, val_float, val_str) in enumerate(denoms):
                    if val_str == "???" or not val_str: continue
                    with cols[i % 3]:
                        change_val = st.number_input(
                            f"{val_str}", 
                            min_value=-20, 
                            max_value=20, 
                            step=1, 
                            value=0,
                            key=f"denom_{source_choice}_{idx}"
                        )
                        if change_val != 0:
                            changes[idx] = change_val

            submitted = st.form_submit_button("Registrar Movimiento 🚀", use_container_width=True, type="primary")

            if submitted:
                # Calcular total desde el desglose si la cantidad es 0
                calc_total = 0.0
                for idx, delta in changes.items():
                    val = parse_euro(active_df.at[idx, 'Monedes'])
                    calc_total += abs(val * delta) # Usamos valor absoluto para el cálculo del total
                
                final_amount = amount
                if amount == 0 and calc_total > 0:
                    final_amount = calc_total
                    st.toast(f"✅ Total calculado: {format_euro(final_amount)}")
                
                if final_amount <= 0:
                    st.error("Error: Introduce una cantidad o selecciona billetes.")
                else:
                    # Lógica de registro
                    is_expense = "Gasto" in type_choice
                    signed_amount = -final_amount if is_expense else final_amount
                    
                    # 1. Update CSV/Sheet Logic
                    # We need to update the specific cell in the sheet.
                    # 'changes' dict contains {row_index: delta}
                    
                    target_ws = ws_cartera if source_choice == "Cartera" else ws_diners
                    target_df = df_cartera if source_choice == "Cartera" else df_diners
                    
                    # Batch update list
                    # gspread logic: cell(row, col). Row is 1-indexed. Header is row 1. Data starts row 2.
                    # iterrows index is 0-based relative to df. 
                    # So Sheet Row = index + 2.
                    
                    # If user didn't specify breakdown but chose "Update Stock", 
                    # we could implement greedy algo here? 
                    # User requested: "program must update automatically... subtracting 1... if possible".
                    # If user enters changes manually, we trust them.
                    # If 'changes' is empty but amount > 0, we can try to guess or just warn.
                    
                    if update_stock and not changes:
                        st.warning("No indicaste qué billetes cambiaron. Se registrará el historial pero no el stock de monedas.")
                        # Proceed anyway? Or stop? Proceeding is safer for UX, just History log.
                    
                    final_stock_delta = 0.0
                    
                    if changes:
                        # Process updates
                        for idx, delta in changes.items():
                            # Calculate new quantity
                            current_qty = int(target_df.at[idx, 'Quantes?'])
                            new_qty = current_qty + delta
                            
                            # Validation
                            if new_qty < 0:
                                st.error(f"Error: No tienes suficientes {target_df.at[idx, 'Monedes']}")
                                st.stop()
                                
                            # Update Sheet
                            # Column 2 is 'Quantes?'. Row = idx + 2
                            target_ws.update_cell(idx + 2, 2, new_qty)
                            
                            # Update Total Column (Col 3)
                            # val_float = parse_euro(target_df.at[idx, 'Monedes'])
                            # new_subtotal = val_float * new_qty
                            # target_ws.update_cell(idx + 2, 3, format_euro(new_subtotal))
                            # Note: Updating cell by cell is slow. Ideally batch_update.
                            
                            # Calculate how much money actually moved based on counts
                            mon_val = parse_euro(target_df.at[idx, 'Monedes'])
                            final_stock_delta += (mon_val * delta)

                        st.success(f"Stock actualizado. (Delta calculado: {format_euro(final_stock_delta)})")
                    
                    # 2. Update History
                    # We use the calculated total_cartera AFTER the change? Or before?
                    # Usually After.
                    new_total_cartera = total_cartera + (signed_amount if source_choice == "Cartera" else 0)
                    
                    today = datetime.datetime.now().strftime("%d/%m/%y")
                    update_history(client, today, signed_amount, notes, new_total_cartera)
                    
                    st.success("Movimiento registrado correctamente!")
                    st.balloons()
else:
    st.info("Configurando conexión...")
