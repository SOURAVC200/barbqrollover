import streamlit as st
import pandas as pd
from datetime import datetime
import urllib.parse
import streamlit.components.v1 as components
from sqlalchemy import text

# ==========================================
# 1. DATABASE SETUP (CLOUD POSTGRESQL)
# ==========================================
# Connects securely using Streamlit Secrets
conn = st.connection("postgresql", type="sql", url=st.secrets["DATABASE_URL"])

# Create Tables in the Cloud Database
with conn.session as s:
    s.execute(text('''CREATE TABLE IF NOT EXISTS customers (phone TEXT PRIMARY KEY, name TEXT)'''))
    s.execute(text('''CREATE TABLE IF NOT EXISTS menu (item_name TEXT PRIMARY KEY, price REAL)'''))
    s.execute(text('''CREATE TABLE IF NOT EXISTS invoices 
                 (id SERIAL PRIMARY KEY, phone TEXT, name TEXT, amount REAL, date TEXT, order_details TEXT)'''))
    s.commit()

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
def get_menu():
    menu_df = conn.query("SELECT item_name, price FROM menu")
    if menu_df.empty:
        return {}
    return dict(zip(menu_df['item_name'], menu_df['price']))

def get_whatsapp_link(phone, message):
    clean_phone = ''.join(char for char in phone if char.isdigit() or char == '+')
    encoded_message = urllib.parse.quote(message)
    return f"https://wa.me/{clean_phone}?text={encoded_message}"

# ==========================================
# 3. INITIALIZE SESSION STATE
# ==========================================
if 'step' not in st.session_state: st.session_state.step = 1
if 'cust_name' not in st.session_state: st.session_state.cust_name = ""
if 'cust_phone' not in st.session_state: st.session_state.cust_phone = "+91"
if 'wa_link' not in st.session_state: st.session_state.wa_link = ""

# ==========================================
# 4. USER INTERFACE
# ==========================================
st.set_page_config(page_title="Shop Manager", layout="wide")
st.title("Bar-B-Q Rollover Manager")

menu_choice = st.sidebar.radio("Navigation", ["Create Invoice", "Manage Menu", "Database & Reports"])

# ------------------------------------------
# PAGE 1: CREATE INVOICE
# ------------------------------------------
if menu_choice == "Create Invoice":
    st.header("Create New Invoice")
    
    if st.session_state.step == 1:
        st.subheader("Step 1: Customer Details")
        st.session_state.cust_name = st.text_input("Customer Name", value=st.session_state.cust_name)
        st.session_state.cust_phone = st.text_input("Customer Phone Number", value=st.session_state.cust_phone)
        
        st.write("") 
        if st.button("Next: Select Items >>", type="primary"):
            if st.session_state.cust_name and st.session_state.cust_phone and st.session_state.cust_phone != "+91":
                st.session_state.step = 2
                st.rerun()
            else:
                st.error("Please enter a valid Customer Name and Phone Number.")

    elif st.session_state.step == 2:
        st.subheader(f"Step 2: Order for {st.session_state.cust_name}")
        if st.button("<< Back to Edit Customer"):
            st.session_state.step = 1
            st.rerun()
            
        st.write("---")
        menu_dict = get_menu()
        
        if not menu_dict:
            st.warning("Your menu is empty! Go to 'Manage Menu' to add items.")
        else:
            selected_items = st.multiselect("Choose items", list(menu_dict.keys()))
            quantities = {}
            total_amount = 0.0
            
            if selected_items:
                st.write("---")
                for item in selected_items:
                    col_a, col_b = st.columns([3, 1])
                    with col_a:
                        st.write(f"**{item}** (Rs. {menu_dict[item]:.2f})")
                    with col_b:
                        qty = st.number_input(f"Qty for {item}", min_value=1, value=1, key=item)
                        quantities[item] = qty
                        total_amount += menu_dict[item] * qty
                
                st.write("---")
                st.title(f"Total: Rs. {total_amount:.2f}")
                
                if st.button("Generate, Save & Send Invoice", type="primary"):
                    # Save to Cloud DB
                    with conn.session as s:
                        # 1. Customer
                        s.execute(text("INSERT INTO customers (phone, name) VALUES (:phone, :name) ON CONFLICT (phone) DO UPDATE SET name = EXCLUDED.name"), 
                                  {"phone": st.session_state.cust_phone, "name": st.session_state.cust_name})
                        
                        # 2. Invoice
                        order_details = ", ".join([f"{k} (x{v})" for k, v in quantities.items()])
                        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        s.execute(text("INSERT INTO invoices (phone, name, amount, date, order_details) VALUES (:phone, :name, :amount, :date, :details)"), 
                                  {"phone": st.session_state.cust_phone, "name": st.session_state.cust_name, "amount": total_amount, "date": now, "details": order_details})
                        s.commit()
                    
                    # WhatsApp Link
                    invoice_text = f"Hello {st.session_state.cust_name}! Thank you for grabbing a bite at Bar-B-Q Rollover. Your order of {order_details} came to a total of Rs. {total_amount:.2f}. We hope you enjoyed the food!"
                    st.session_state.wa_link = get_whatsapp_link(st.session_state.cust_phone, invoice_text)
                    st.session_state.step = 3
                    st.rerun()

    elif st.session_state.step == 3:
        st.success("Invoice successfully saved to your Cloud Database!")
        st.info("WhatsApp should open automatically. If your browser blocked it, click the button below.")
        
        components.html(f'<script>window.open("{st.session_state.wa_link}", "_blank");</script>', height=0)
        
        st.markdown(f'''
            <a href="{st.session_state.wa_link}" target="_blank" style="
                display: inline-block; padding: 12px 24px; background-color: #25D366; 
                color: white; text-align: center; text-decoration: none; border-radius: 8px; 
                font-weight: bold; font-size: 16px;">
                Open WhatsApp manually
            </a>
        ''', unsafe_allow_html=True)
        
        st.write("---")
        if st.button("+ Create Another Invoice"):
            st.session_state.step = 1
            st.session_state.cust_name = ""
            st.session_state.cust_phone = "+91"
            st.rerun()

# ------------------------------------------
# PAGE 2: MANAGE MENU
# ------------------------------------------
elif menu_choice == "Manage Menu":
    st.header("Manage Menu")
    
    tab1, tab2, tab3 = st.tabs(["Upload CSV Menu", "Add Single Item", "Edit / Delete Item"])
    
    with tab1:
        st.write("Upload a CSV file to update your menu. Columns must be: `item_name` and `price`.")
        sample_data = pd.DataFrame({"item_name": ["Chicken Roll", "Paneer Tikka Roll", "Cold Coffee"], "price": [80.0, 70.0, 50.0]})
        st.download_button("Download Sample CSV", data=sample_data.to_csv(index=False).encode('utf-8'), file_name="sample_menu.csv", mime="text/csv")
        
        uploaded_file = st.file_uploader("Upload Menu CSV", type=["csv"])
        if uploaded_file is not None:
            df = pd.read_csv(uploaded_file)
            if 'item_name' in df.columns and 'price' in df.columns:
                with conn.session as s:
                    for index, row in df.iterrows():
                        s.execute(text("INSERT INTO menu (item_name, price) VALUES (:name, :price) ON CONFLICT (item_name) DO UPDATE SET price = EXCLUDED.price"), 
                                  {"name": row['item_name'], "price": float(row['price'])})
                    s.commit()
                st.success("Menu updated successfully! Refreshing...")
                st.rerun()
            else:
                st.error("CSV format incorrect!")
                
    with tab2:
        with st.form("add_item_form", clear_on_submit=True):
            new_item = st.text_input("Item Name")
            new_price = st.number_input("Price (Rs.)", min_value=0.0, format="%.2f")
            if st.form_submit_button("Add Item") and new_item:
                with conn.session as s:
                    s.execute(text("INSERT INTO menu (item_name, price) VALUES (:name, :price) ON CONFLICT (item_name) DO UPDATE SET price = EXCLUDED.price"), 
                              {"name": new_item, "price": new_price})
                    s.commit()
                st.success(f"Added {new_item}! Refreshing...")
                st.rerun()

    with tab3:
        menu_dict = get_menu()
        if menu_dict:
            item_to_edit = st.selectbox("Select an item to edit/delete", list(menu_dict.keys()))
            col_e1, col_e2 = st.columns(2)
            
            with col_e1:
                updated_price = st.number_input("Update Price (Rs.)", value=float(menu_dict[item_to_edit]), format="%.2f")
                if st.button("Update Price"):
                    with conn.session as s:
                        s.execute(text("UPDATE menu SET price = :price WHERE item_name = :name"), {"price": updated_price, "name": item_to_edit})
                        s.commit()
                    st.success("Updated! Refreshing...")
                    st.rerun()
                    
            with col_e2:
                st.write("")
                st.write("") 
                if st.button("Delete Item"):
                    with conn.session as s:
                        s.execute(text("DELETE FROM menu WHERE item_name = :name"), {"name": item_to_edit})
                        s.commit()
                    st.warning("Deleted! Refreshing...")
                    st.rerun()

    st.subheader("Current Menu")
    st.dataframe(conn.query("SELECT * FROM menu"), use_container_width=True)

# ------------------------------------------
# PAGE 3: DATABASE & REPORTS
# ------------------------------------------
elif menu_choice == "Database & Reports":
    st.header("Database & Reports")
    
    total_rev_df = conn.query("SELECT SUM(amount) as total FROM invoices")
    total_revenue = total_rev_df['total'].iloc[0]
    if pd.isna(total_revenue): total_revenue = 0.0
    st.metric(label="Total Revenue Generated", value=f"Rs. {total_revenue:.2f}")
    st.write("---")
    
    tab_inv, tab_cust, tab_manage = st.tabs(["Invoices", "Customers", "Edit / Delete Records"])
    
    with tab_inv:
        inv_df = conn.query('SELECT id as "Invoice_ID", name as "Customer", phone as "Phone", amount as "Total", order_details as "Details", date as "Date" FROM invoices ORDER BY id DESC')
        st.dataframe(inv_df, use_container_width=True)
        if not inv_df.empty:
            st.download_button("Download Invoice History", data=inv_df.to_csv(index=False).encode('utf-8'), file_name="invoice_history.csv", mime="text/csv")
            
    with tab_cust:
        cust_df = conn.query('SELECT name as "Name", phone as "Phone" FROM customers')
        st.dataframe(cust_df, use_container_width=True)
        if not cust_df.empty:
            st.download_button("Download Customers", data=cust_df.to_csv(index=False).encode('utf-8'), file_name="customers.csv", mime="text/csv")

    with tab_manage:
        st.subheader("Delete an Invoice")
        if not inv_df.empty:
            inv_list = inv_df['Invoice_ID'].astype(str) + " - " + inv_df['Customer'] + " (Rs. " + inv_df['Total'].astype(str) + ")"
            inv_to_delete = st.selectbox("Select Invoice to delete", inv_list)
            if st.button("Delete Invoice"):
                inv_id = inv_to_delete.split(" - ")[0]
                with conn.session as s:
                    s.execute(text("DELETE FROM invoices WHERE id = :id"), {"id": inv_id})
                    s.commit()
                st.success("Deleted! Refreshing...")
                st.rerun()
            
        st.write("---")
        st.subheader("Delete a Customer")
        if not cust_df.empty:
            cust_to_delete = st.selectbox("Select Customer to delete", cust_df['Phone'] + " - " + cust_df['Name'])
            if st.button("Delete Customer"):
                cust_phone_del = cust_to_delete.split(" - ")[0]
                with conn.session as s:
                    s.execute(text("DELETE FROM customers WHERE phone = :phone"), {"phone": cust_phone_del})
                    s.commit()
                st.success("Deleted! Refreshing...")
                st.rerun()