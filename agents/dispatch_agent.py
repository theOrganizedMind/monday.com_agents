from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
import tkinter as tk
from tkinter import ttk, messagebox
from tkcalendar import DateEntry
import json
import subprocess
import logging
from collections import defaultdict
import time
import traceback

import monday
import contact_book


# ========================================================================== #
# ================================== INFO ================================== #
# ========================================================================== #
# 
# ========================================================================== #
# ================================== TODO ================================== #
# ========================================================================== #
# TODO: 
# ========================================================================== #

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()

MONDAY_API_KEY = os.getenv("MONDAY_API_KEY")
DISPATCH_BOARD_ID = os.getenv("DISPATCH_BOARD_ID")
INVOICING_BOARD_ID = os.getenv("INVOICING_BOARD_ID")
DUMPSTER_INVENTORY_BOARD_ID = os.getenv("DUMPSTER_INVENTORY_BOARD_ID")

# Add all driver board IDs here, matching the driver names in your Dispatch Board
DRIVER_BOARD_IDS = {
    "Jane Doe": os.getenv("JANE_DOE_BOARD_ID"),
    "John Smith": os.getenv("JOHN_SMITH_BOARD_ID"),
    # Add more drivers as needed
}

# --- Fetch dynamic dropdowns and group IDs ---
board_columns = monday.get_board_columns(DISPATCH_BOARD_ID, MONDAY_API_KEY)
group_map = monday.get_group_ids(DISPATCH_BOARD_ID, MONDAY_API_KEY)
# Map column titles to IDs for easy access
column_id_map = {col["title"]: col["id"] for col in board_columns["data"]["boards"][0]["columns"]}

# Fetch dropdown options
size_options = monday.get_dropdown_options(DISPATCH_BOARD_ID, column_id_map["Size"], MONDAY_API_KEY)
type_options = monday.get_dropdown_options(DISPATCH_BOARD_ID, column_id_map["Type"], MONDAY_API_KEY)
desc_options = monday.get_dropdown_options(DISPATCH_BOARD_ID, column_id_map["Description"], MONDAY_API_KEY)
company_options = monday.get_dropdown_options(DISPATCH_BOARD_ID, column_id_map["Company"], MONDAY_API_KEY)
driver_options = monday.get_dropdown_options(DISPATCH_BOARD_ID, column_id_map["Driver"], MONDAY_API_KEY)

# Map driver names to group IDs (ensure group titles match driver names)
driver_group_map = {name: group_map.get(name) for name in driver_options}

# After fetching group_map and driver_options
# print("Driver options from column:", driver_options)
# print("Group titles from board:", list(group_map.keys()))
logging.info(f"Driver options from column: {driver_options}")
logging.info(f"Group titles from board: {list(group_map.keys())}")


# --- Load contacts from JSON ---
def load_contacts():
    """
    Load contacts from the contacts.json file.

    Returns:
        list: List of contact dictionaries.
    """
    # print(f"Loading contacts from json_files/contacts.json")
    logging.info("Loading contacts from json_files/contacts.json")
    with open("json_files/contacts.json") as f:
        return json.load(f)
    
contacts = load_contacts()
contact_names = [c["name"] for c in contacts]
contact_phone_map = {c["name"]: c["phone"] for c in contacts}

# --- Organize contacts by company for fast lookup ---
contacts_by_company = {}
for c in contacts:
    company = c.get("company", "")
    if company not in contacts_by_company:
        contacts_by_company[company] = []
    contacts_by_company[company].append(c)

# --- Dumpster Inventory Helper Functions ---
# Get the column ID for the "Date" column in the Dumpster Inventory board
inventory_board_columns = monday.get_board_columns(DUMPSTER_INVENTORY_BOARD_ID, MONDAY_API_KEY)
date_col_id = None
for col in inventory_board_columns["data"]["boards"][0]["columns"]:
    if col["title"].strip().lower() == "date":
        date_col_id = col["id"]
        break

# For the relevant board (e.g., DISPATCH_BOARD_ID)
board_columns = monday.get_board_columns(DISPATCH_BOARD_ID, MONDAY_API_KEY)
col_id_map = {col["title"].strip().lower(): col["id"] for col in board_columns["data"]["boards"][0]["columns"]}
size_col_id = col_id_map["size"]
desc_col_id = col_id_map["description"]
date_col_id = col_id_map["date"]

def show_loading_popup(root, message="Loading..."):
    """Create and display a modal loading popup tied to the given parent."""
    loading_win = tk.Toplevel(root)
    loading_win.title("Please Wait")
    loading_win.geometry("320x80")
    loading_win.resizable(False, False)
    loading_win.transient(root)
    loading_win.grab_set()
    tk.Label(loading_win, text=message, font=("Arial", 12)).pack(pady=20)
    loading_win.update()
    return loading_win

def get_inventory_column_ids(board_columns):
    """
    Returns a mapping of size label to column ID for the Dumpster Inventory board.
    Example: {'40-yard': 'numbers4', '30-yard': 'numbers', ...}
    """
    size_map = {}
    for col in board_columns["data"]["boards"][0]["columns"]:
        title = col["title"].strip().lower()
        if "yard" in title:
            size_map[title] = col["id"]
    return size_map

def get_current_inventory(api_key, inventory_board_id, size_col_ids, date_col_id):
    """
    Fetch the most recent inventory counts for each dumpster size from the Dumpster 
    Inventory board.
    Returns a dict: {size: count}
    """
    items = monday.fetch_all_board_items(api_key, inventory_board_id)
    # Find the item with the most recent date
    latest_item = None
    latest_date = None
    for item in items:
        date_val = None
        for col in item['column_values']:
            if col['id'] == date_col_id:
                date_val = col['text']
                break
        if date_val:
            try:
                dt = datetime.strptime(date_val, "%Y-%m-%d")
                if not latest_date or dt > latest_date:
                    latest_date = dt
                    latest_item = item
            except Exception:
                continue
    # Extract inventory counts for each size from the latest item
    inventory = {}
    if latest_item:
        for size_label, col_id in size_col_ids.items():
            for col in latest_item['column_values']:
                if col['id'] == col_id:
                    try:
                        inventory[size_label] = int(col['text'].replace(',', ''))
                    except Exception:
                        inventory[size_label] = 0
    return inventory

def count_pending_drops_and_returns(api_key, board_id, size_label, date_str, 
                                    size_col_id, desc_col_id, date_col_id):
    """
    Count the number of 'Initial Drop' (subtract) and 'Dump & Remove' (add) for a 
    given size and date.
    Returns: (drops, returns)
    """
    items = monday.fetch_all_board_items(api_key, board_id)
    drops = 0
    returns = 0
    for item in items:
        item_size = None
        desc = None
        item_date = None
        for col in item['column_values']:
            if col['id'] == size_col_id:
                item_size = col['text']
            elif col['id'] == desc_col_id:
                desc = col['text']
            elif col['id'] == date_col_id:
                item_date = col['text']
        if item_size and item_size.strip().lower() == size_label.strip().lower():
            if item_date == date_str:
                if desc == 'Initial Drop':
                    drops += 1
                elif desc == 'Dump & Remove':
                    returns += 1
    return drops, returns

def count_pending_drops_and_returns_from_items(items, size_label, date_str, 
                                               size_col_id, desc_col_id, date_col_id):
    """
    Count pending drops and returns from a pre-fetched item collection.

    Returns:
        tuple[int, int]: (drops, returns)
    """
    drops = 0
    returns = 0
    for item in items:
        item_size = None
        desc = None
        item_date = None
        for col in item['column_values']:
            if col['id'] == size_col_id:
                item_size = col['text']
            elif col['id'] == desc_col_id:
                desc = col['text']
            elif col['id'] == date_col_id:
                item_date = col['text']
        if item_size and item_size.strip().lower() == size_label.strip().lower():
            if item_date == date_str:
                if desc == 'Initial Drop':
                    drops += 1
                elif desc == 'Dump & Remove':
                    returns += 1
    return drops, returns

def launch_create_jobs_on_dispatch_board_gui():
    """Launch the Dispatch Board job-creation window and event handlers."""
    root = tk.Tk()
    root.title("Create Jobs On Dispatch Board")
    root.config(padx=20, pady=20)

    fields = {}

    def add_label_entry(row, label, var_type=tk.StringVar, widget=None, **kwargs):
        """
        Add a label and entry (or widget) to the Tkinter grid.

        Args:
            row (int): The row number in the grid.
            label (str): The label text.
            var_type (type): The Tkinter variable type (default: tk.StringVar).
            widget (Tk widget, optional): The widget class to use (e.g., ttk.Combobox).
            **kwargs: Additional keyword arguments for the widget.

        Returns:
            tuple: (variable, widget) created.
        """
        tk.Label(root, text=label).grid(row=row, column=0, sticky="e", padx=10, pady=5)
        var = var_type()
        if widget:
            w = widget(root, textvariable=var, **kwargs)
        else:
            w = tk.Entry(root, textvariable=var, **kwargs)
        w.grid(row=row, column=1, sticky="w", padx=10, pady=5)
        fields[label] = var
        return var, w

    row = 0
    item_name_var, _ = add_label_entry(row, "Item Name")
    row += 1
    driver_var, _ = add_label_entry(row, "Driver", widget=ttk.Combobox, values=driver_options)
    row += 1
    date_var, _ = add_label_entry(row, "Start Date", widget=DateEntry, date_pattern="yyyy-mm-dd")
    row += 1
    size_var, _ = add_label_entry(row, "Size", widget=ttk.Combobox, values=size_options)
    row += 1
    type_var, _ = add_label_entry(row, "Type", widget=ttk.Combobox, values=type_options)
    row += 1
    desc_var, _ = add_label_entry(row, "Description", widget=ttk.Combobox, values=desc_options)
    row += 1
    location_var, _ = add_label_entry(row, "Location")
    row += 1
    company_var, company_box = add_label_entry(row, "Company", widget=ttk.Combobox, values=company_options)
    row += 1
    site_contact_var, site_contact_box = add_label_entry(row, "Site Contact", widget=ttk.Combobox, values=contact_names)
    row += 1
    phone_var, phone_box = add_label_entry(row, "Phone")
    row += 1
    po_var, _ = add_label_entry(row, "PO #")
    row += 1
    duplicates_var, _ = add_label_entry(row, "Duplicates", var_type=tk.IntVar)
    row += 1
    days_var, _ = add_label_entry(row, "Days", var_type=tk.IntVar)
    row += 1

    def open_contacts_gui():
        """
        Launch the contact_book.py GUI in a new process for managing contacts.
        """
        # Adjust the path if needed
        # subprocess.Popen(["python", os.path.join("contact_book", "contact_book.py")])
        contact_book.launch_contact_book(parent=root)


    # --- Filtering and search logic ---
    def on_company_selected(event=None):
        """
        Event handler for when a company is selected in the company dropdown.
        Filters the site contact dropdown to only show contacts for the selected company.
        """
        company = company_var.get()
        filtered_contacts = contacts_by_company.get(company, [])
        names = [c["name"] for c in filtered_contacts]
        site_contact_box['values'] = names
        site_contact_var.set("")
        phone_var.set("")

    def on_company_keyrelease(event):
        """
        Event handler for key release in the company dropdown.
        Filters the company dropdown options as the user types.
        """
        typed = company_var.get().lower()
        filtered_companies = [c for c in company_options if typed in c.lower()]
        company_box['values'] = filtered_companies

    def on_site_contact_selected(event=None):
        """
        Event handler for when a site contact is selected in the site contact dropdown.
        Auto-fills the phone number for the selected contact.
        """
        name = site_contact_var.get()
        company = company_var.get()
        filtered_contacts = contacts_by_company.get(company, [])
        phone = ""
        for c in filtered_contacts:
            if c["name"] == name:
                phone = c.get("phone", "")
                break
        phone_var.set(phone)

    def on_site_contact_keyrelease(event):
        """
        Event handler for key release in the site contact dropdown.
        Filters the site contact dropdown options as the user types.
        """
        company = company_var.get()
        filtered_contacts = contacts_by_company.get(company, [])
        names = [c["name"] for c in filtered_contacts]
        typed = site_contact_var.get().lower()
        filtered_names = [n for n in names if typed in n.lower()]
        site_contact_box['values'] = filtered_names

    # Bind events
    company_box.bind("<<ComboboxSelected>>", on_company_selected)
    company_box.bind("<KeyRelease>", on_company_keyrelease)
    site_contact_box.bind("<<ComboboxSelected>>", on_site_contact_selected)
    site_contact_box.bind("<KeyRelease>", on_site_contact_keyrelease)

    def submit():
        """
        Collects form data and creates dispatch items on the Monday.com board.
        Handles duplicates and days logic for creating multiple items.
        Shows a success message when done.
        """
        loading_popup = show_loading_popup(root, "Adding items to Dispatch Board\n"
                                           " and Checking Inventory...")
        try:
            item_name = item_name_var.get()
            driver = driver_var.get()
            group_id = driver_group_map.get(driver)
            if not group_id:
                messagebox.showerror("Error", "Selected driver does not have a group ID.")
                return
            start_date = datetime.strptime(date_var.get(), "%Y-%m-%d")
            size = size_var.get()
            type_ = type_var.get()
            desc = desc_var.get()
            location = location_var.get()
            company = company_var.get()
            site_contact = site_contact_var.get()
            phone = phone_var.get()
            po = po_var.get()
            duplicates = duplicates_var.get()
            days = days_var.get()

            # print("DISPATCH_BOARD_ID:", DISPATCH_BOARD_ID)
            # print("group_id:", group_id)
            # print("column_id_map:", column_id_map)
            # print("column_values:", column_values)
            # print("driver:", driver)
            logging.info(f"DISPATCH_BOARD_ID: {DISPATCH_BOARD_ID}")
            logging.info(f"group_id: {group_id}")

            # --- Dumpster Inventory Check ---
            if desc == 'Initial Drop':
                # Map size label to match inventory board columns (e.g., '30 yard' → '30 yard')
                size_label_map = {
                    '40 yard': '40 yard',
                    '30 yard': '30 yard',
                    '20 yard': '20 yard',
                    '15 yard': '15 yard'
                }
                inventory_size_label = size_label_map.get(size.lower())
                if not inventory_size_label:
                    messagebox.showerror("Error", f"Unknown dumpster size: {size}")
                    return

                # Get column IDs for inventory board
                inventory_board_columns = monday.get_board_columns(DUMPSTER_INVENTORY_BOARD_ID, MONDAY_API_KEY)
                inventory_col_id_map = {col["title"].strip().lower(): col["id"] for col in inventory_board_columns["data"]["boards"][0]["columns"]}
                size_col_ids = {k: v for k, v in inventory_col_id_map.items() if "yard" in k}
                inventory_date_col_id = inventory_col_id_map["date"]

                # Get current inventory for this size
                inventory = get_current_inventory(MONDAY_API_KEY, DUMPSTER_INVENTORY_BOARD_ID, size_col_ids, inventory_date_col_id)
                current_count = inventory.get(inventory_size_label, 0)

                # Get column IDs for the dispatch board
                dispatch_col_id_map = monday.get_column_ids(DISPATCH_BOARD_ID, MONDAY_API_KEY)
                dispatch_size_col_id = dispatch_col_id_map["size"]
                dispatch_desc_col_id = dispatch_col_id_map["description"]
                dispatch_date_col_id = dispatch_col_id_map["date"]

                today_str = start_date.strftime("%Y-%m-%d")
                drops, returns = count_pending_drops_and_returns(
                MONDAY_API_KEY, DISPATCH_BOARD_ID, size, today_str,
                dispatch_size_col_id, dispatch_desc_col_id, dispatch_date_col_id
                )
                # Count for each driver board
                for driver_name, driver_board_id in DRIVER_BOARD_IDS.items():
                    driver_col_id_map = monday.get_column_ids(driver_board_id, MONDAY_API_KEY)
                    driver_size_col_id = driver_col_id_map["size"]
                    driver_desc_col_id = driver_col_id_map["description"]
                    driver_date_col_id = driver_col_id_map["date"]
                    d_drops, d_returns = count_pending_drops_and_returns(
                        MONDAY_API_KEY, driver_board_id, size, today_str,
                        driver_size_col_id, driver_desc_col_id, driver_date_col_id
                    )
                    drops += d_drops
                    returns += d_returns

                # --- Invoicing Board: Only 'Invoicing' group ---
                invoicing_group_map = monday.get_group_ids(INVOICING_BOARD_ID, MONDAY_API_KEY)
                invoicing_group_id = invoicing_group_map.get("Invoicing")
                if invoicing_group_id:
                    invoicing_col_id_map = monday.get_column_ids(INVOICING_BOARD_ID, MONDAY_API_KEY)
                    inv_size_col_id = invoicing_col_id_map["size"]
                    inv_desc_col_id = invoicing_col_id_map["description"]
                    inv_date_col_id = invoicing_col_id_map["date"]
                    invoicing_items = monday.fetch_items_in_group(MONDAY_API_KEY, INVOICING_BOARD_ID, invoicing_group_id)
                    inv_drops, inv_returns = count_pending_drops_and_returns_from_items(
                        invoicing_items, size, today_str, inv_size_col_id, inv_desc_col_id, inv_date_col_id
                    )
                    drops += inv_drops
                    returns += inv_returns

                available = current_count - drops + returns
                if available <= 3:
                    messagebox.showwarning("Low Inventory", f"We are currently out of {size} dumpsters or inventory is low ({available} left).")
                    return  # Prevent job creation

            # print(f"Creating {duplicates} items for driver {driver} starting {start_date.strftime('%a, %b %d, %Y')}")
            logging.info(f"Creating {duplicates} items for driver {driver} starting {start_date.strftime('%a, %b %d, %Y')}")

            for day in range(days):
                date = (start_date + timedelta(days=day)).strftime("%Y-%m-%d")
                for dup in range(duplicates):
                    # print(f"Creating item {dup+1}/{duplicates} for date {date}")
                    logging.info(f"Creating item {dup+1}/{duplicates} for date {date}")
                    # Everything works except the location 
                    column_values = {
                        column_id_map["Driver"]: driver,
                        column_id_map["Date"]: {"date": date},  # Date: dict with "date" key
                        column_id_map["Size"]: size,
                        column_id_map["Type"]: type_,
                        column_id_map["Description"]: desc,
                        # column_id_map["Location"]: {"address": location}, # <-- Does Not Work
                        # column_id_map["Location"]: location, # <-- Does Not Work
                        # column_id_map["Location"]: json.dumps({"address": location}), # <-- Does Not Work
                        column_id_map["Company"]: company,
                        column_id_map["Site Contact"]: site_contact,
                        column_id_map["Phone"]: {"phone": phone, "countryShortName": None},
                        # column_id_map["Phone"]: phone
                        column_id_map["PO #"]: po,
                    }
                    # print(type(column_values[column_id_map["Location"]]), column_values[column_id_map["Location"]])
                    # print("column_values:", column_values)
                    logging.info(f"column_values: {column_values}")
                    monday.create_item(DISPATCH_BOARD_ID, group_id, item_name, MONDAY_API_KEY, column_values)
                    # create_item(DISPATCH_BOARD_ID, group_id, item_name)
            # print("All items created.")
            logging.info("All items created.")
            messagebox.showinfo("Success", f"Created {duplicates} item(s) for {days} day(s) for {driver}.")
        finally:
            loading_popup.destroy()

    tk.Button(root, text="Create Dispatch Items", command=submit).grid(row=row, column=1, pady=15, padx=10, sticky="e")
    tk.Button(root, text="Contacts", command=open_contacts_gui).grid(row=row+1, column=1, pady=5, padx=10, sticky="e")

    def on_close():
        """Close this window and return to the main menu."""
        root.destroy()
        launch_main_gui()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()

def launch_create_jobs_on_driver_board_gui():
    """Launch the Driver Board job-creation window and event handlers."""
    root = tk.Tk()
    root.title("Create Jobs On Driver Board")
    root.config(padx=20, pady=20)

    fields = {}

    def add_label_entry(row, label, var_type=tk.StringVar, widget=None, **kwargs):
        """Add a labeled input control to the Driver Board form grid."""
        tk.Label(root, text=label).grid(row=row, column=0, sticky="e", padx=10, pady=5)
        var = var_type()
        if widget:
            w = widget(root, textvariable=var, **kwargs)
        else:
            w = tk.Entry(root, textvariable=var, **kwargs)
        w.grid(row=row, column=1, sticky="w", padx=10, pady=5)
        fields[label] = var
        return var, w

    row = 0
    item_name_var, _ = add_label_entry(row, "Item Name")
    row += 1
    driver_var, _ = add_label_entry(row, "Driver", widget=ttk.Combobox, values=driver_options)
    row += 1
    date_var, _ = add_label_entry(row, "Start Date", widget=DateEntry, date_pattern="yyyy-mm-dd")
    row += 1
    size_var, _ = add_label_entry(row, "Size", widget=ttk.Combobox, values=size_options)
    row += 1
    type_var, _ = add_label_entry(row, "Type", widget=ttk.Combobox, values=type_options)
    row += 1
    desc_var, _ = add_label_entry(row, "Description", widget=ttk.Combobox, values=desc_options)
    row += 1
    location_var, _ = add_label_entry(row, "Location")
    row += 1
    company_var, company_box = add_label_entry(row, "Company", widget=ttk.Combobox, values=company_options)
    row += 1
    site_contact_var, site_contact_box = add_label_entry(row, "Site Contact", widget=ttk.Combobox, values=contact_names)
    row += 1
    phone_var, phone_box = add_label_entry(row, "Phone")
    row += 1
    po_var, _ = add_label_entry(row, "PO #")
    row += 1
    duplicates_var, _ = add_label_entry(row, "Duplicates", var_type=tk.IntVar)
    row += 1
    days_var, _ = add_label_entry(row, "Days", var_type=tk.IntVar)
    row += 1

    def open_contacts_gui():
        """Open the Contact Book as a child window of this form."""
        # subprocess.Popen(["python", os.path.join("contact_book", "contact_book.py")])
        contact_book.launch_contact_book(parent=root)

    def on_company_selected(event=None):
        """Filter site contacts to the currently selected company."""
        company = company_var.get()
        filtered_contacts = contacts_by_company.get(company, [])
        names = [c["name"] for c in filtered_contacts]
        site_contact_box['values'] = names
        site_contact_var.set("")
        phone_var.set("")

    def on_company_keyrelease(event):
        """Filter company combobox options as the user types."""
        typed = company_var.get().lower()
        filtered_companies = [c for c in company_options if typed in c.lower()]
        company_box['values'] = filtered_companies

    def on_site_contact_selected(event=None):
        """Populate the phone field when a site contact is selected."""
        name = site_contact_var.get()
        company = company_var.get()
        filtered_contacts = contacts_by_company.get(company, [])
        phone = ""
        for c in filtered_contacts:
            if c["name"] == name:
                phone = c.get("phone", "")
                break
        phone_var.set(phone)

    def on_site_contact_keyrelease(event):
        """Filter site contact options based on current typed text."""
        company = company_var.get()
        filtered_contacts = contacts_by_company.get(company, [])
        names = [c["name"] for c in filtered_contacts]
        typed = site_contact_var.get().lower()
        filtered_names = [n for n in names if typed in n.lower()]
        site_contact_box['values'] = filtered_names

    company_box.bind("<<ComboboxSelected>>", on_company_selected)
    company_box.bind("<KeyRelease>", on_company_keyrelease)
    site_contact_box.bind("<<ComboboxSelected>>", on_site_contact_selected)
    site_contact_box.bind("<KeyRelease>", on_site_contact_keyrelease)

    def submit():
        """Validate form data and create one or more items on the selected Driver Board."""
        loading_popup = show_loading_popup(root, "Adding items to Driver Board\n"
                                           " and Checking Inventory...")
        try:
            item_name = item_name_var.get()
            driver = driver_var.get()
            driver_board_id = DRIVER_BOARD_IDS.get(driver)
            if not driver_board_id:
                messagebox.showerror("Error", f"Selected driver '{driver}' does not have a driver board ID.")
                return

            # Fetch group map for the driver board
            driver_group_map = monday.get_group_ids(driver_board_id, MONDAY_API_KEY)
            group_id = driver_group_map.get(driver)
            if not group_id:
                messagebox.showerror("Error", f"Group '{driver}' not found on driver board '{driver_board_id}'.\nAvailable groups: {list(driver_group_map.keys())}")
                return

            start_date = datetime.strptime(date_var.get(), "%Y-%m-%d")
            size = size_var.get()
            type_ = type_var.get()
            desc = desc_var.get()
            location = location_var.get()
            company = company_var.get()
            site_contact = site_contact_var.get()
            phone = phone_var.get()
            po = po_var.get()
            duplicates = duplicates_var.get()
            days = days_var.get()

            # Get column IDs for the current driver board
            board_columns = monday.get_board_columns(driver_board_id, MONDAY_API_KEY)
            column_id_map = {col["title"]: col["id"] for col in board_columns["data"]["boards"][0]["columns"]}

            # --- Dumpster Inventory Check ---
            if desc == 'Initial Drop':
                size_label_map = {
                    '40 yard': '40 yard',
                    '30 yard': '30 yard',
                    '20 yard': '20 yard',
                    '15 yard': '15 yard'
                }
                inventory_size_label = size_label_map.get(size.lower())
                if not inventory_size_label:
                    messagebox.showerror("Error", f"Unknown dumpster size: {size}")
                    return

                # Get column IDs for inventory board
                inventory_board_columns = monday.get_board_columns(DUMPSTER_INVENTORY_BOARD_ID, MONDAY_API_KEY)
                inventory_col_id_map = {col["title"].strip().lower(): col["id"] for col in inventory_board_columns["data"]["boards"][0]["columns"]}
                size_col_ids = {k: v for k, v in inventory_col_id_map.items() if "yard" in k}
                inventory_date_col_id = inventory_col_id_map.get("date")
                if not inventory_date_col_id:
                    messagebox.showerror("Error", "Could not find 'date' column in inventory board.")
                    return

                # Get current inventory for this size
                inventory = get_current_inventory(MONDAY_API_KEY, DUMPSTER_INVENTORY_BOARD_ID, size_col_ids, inventory_date_col_id)
                current_count = inventory.get(inventory_size_label, 0)

                # Get column IDs for the dispatch board
                dispatch_col_id_map = monday.get_column_ids(DISPATCH_BOARD_ID, MONDAY_API_KEY)
                dispatch_size_col_id = dispatch_col_id_map.get("size")
                dispatch_desc_col_id = dispatch_col_id_map.get("description")
                dispatch_date_col_id = dispatch_col_id_map.get("date")
                if not (dispatch_size_col_id and dispatch_desc_col_id and dispatch_date_col_id):
                    messagebox.showerror("Error", "Could not find required columns in dispatch board.")
                    return

                today_str = start_date.strftime("%Y-%m-%d")
                drops, returns = count_pending_drops_and_returns(
                    MONDAY_API_KEY, DISPATCH_BOARD_ID, size, today_str,
                    dispatch_size_col_id, dispatch_desc_col_id, dispatch_date_col_id
                )

                # Count for each driver board
                for driver_name, board_id in DRIVER_BOARD_IDS.items():
                    driver_col_id_map = monday.get_column_ids(board_id, MONDAY_API_KEY)
                    driver_size_col_id = driver_col_id_map.get("size")
                    driver_desc_col_id = driver_col_id_map.get("description")
                    driver_date_col_id = driver_col_id_map.get("date")
                    if not (driver_size_col_id and driver_desc_col_id and driver_date_col_id):
                        continue
                    d_drops, d_returns = count_pending_drops_and_returns(
                        MONDAY_API_KEY, board_id, size, today_str,
                        driver_size_col_id, driver_desc_col_id, driver_date_col_id
                    )
                    drops += d_drops
                    returns += d_returns

                # Invoicing Board: Only 'Invoicing' group
                invoicing_group_map = monday.get_group_ids(INVOICING_BOARD_ID, MONDAY_API_KEY)
                invoicing_group_id = invoicing_group_map.get("Invoicing")
                if invoicing_group_id:
                    invoicing_col_id_map = monday.get_column_ids(INVOICING_BOARD_ID, MONDAY_API_KEY)
                    inv_size_col_id = invoicing_col_id_map.get("size")
                    inv_desc_col_id = invoicing_col_id_map.get("description")
                    inv_date_col_id = invoicing_col_id_map.get("date")
                    if not (inv_size_col_id and inv_desc_col_id and inv_date_col_id):
                        messagebox.showerror("Error", "Could not find required columns in invoicing board.")
                        return
                    invoicing_items = monday.fetch_items_in_group(MONDAY_API_KEY, INVOICING_BOARD_ID, invoicing_group_id)
                    inv_drops, inv_returns = count_pending_drops_and_returns_from_items(
                        invoicing_items, size, today_str, inv_size_col_id, inv_desc_col_id, inv_date_col_id
                    )
                    drops += inv_drops
                    returns += inv_returns

                available = current_count - drops + returns
                if available <= 3:
                    messagebox.showwarning("Low Inventory", f"We are currently out of {size} dumpsters or inventory is low ({available} left).")
                    return  # Prevent job creation

            # --- Create Items ---
            for day in range(days):
                date = (start_date + timedelta(days=day)).strftime("%Y-%m-%d")
                for dup in range(duplicates):
                    column_values = {
                        column_id_map.get("Driver", "driver"): driver,
                        column_id_map.get("Date", "date"): {"date": date},
                        column_id_map.get("Size", "size"): size,
                        column_id_map.get("Type", "type"): type_,
                        column_id_map.get("Description", "description"): desc,
                        column_id_map.get("Company", "company"): company,
                        column_id_map.get("Site Contact", "site contact"): site_contact,
                        column_id_map.get("Phone", "phone"): {"phone": phone, "countryShortName": None},
                        column_id_map.get("PO #"): po,
                    }
                    print(f"Creating item on board {driver_board_id}, group {group_id}, with values: {column_values}")
                    monday.create_item(driver_board_id, group_id, item_name, MONDAY_API_KEY, column_values)
            messagebox.showinfo("Success", f"Created {duplicates} item(s) for {days} day(s) for {driver} on their driver board.")

        except Exception as e:
            messagebox.showerror("Exception", f"An error occurred:\n{e}\n\n{traceback.format_exc()}")
        
        finally:
            loading_popup.destroy()        

    tk.Button(root, text="Create Dispatch Items", command=submit).grid(row=row, column=1, pady=15, padx=10, sticky="e")
    tk.Button(root, text="Contacts", command=open_contacts_gui).grid(row=row+1, column=1, pady=5, padx=10, sticky="e")

    def on_close():
        """Close this window and return to the main menu."""
        root.destroy()
        launch_main_gui()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()

def launch_upload_schedule_gui():
    """
    Copies tomorrow's (or Monday's) items from the Dispatch Board to the Driver Board,
    preserving order using the Auto Number column.
    """
    query = """
    query ($board_id: [ID!], $limit: Int, $cursor: String) {
    boards(ids: $board_id) {
        items_page(limit: $limit, cursor: $cursor) {
        cursor
        items {
            id
            name
            column_values {
            id
            text
            value
            }
        }
        }
    }
    }
    """
    confirm = messagebox.askokcancel(
        "Confirm Upload",
        "Are you sure you want to upload the schedule?\n\nThis will copy "
        "all items for the next dispatch day to the driver boards."
    )
    if not confirm:
        # Return to main menu if cancelled
        try:
            # Close any open Tkinter windows if needed
            for widget in tk._default_root.winfo_children():
                widget.destroy()
            tk._default_root.destroy()
        except Exception:
            pass
        launch_main_gui()
        return
    
    def normalize_name(name):
        """Normalize a driver/group name for case-insensitive matching."""
        return name.strip().lower() if name else ""
    
    def fetch_all_items(board_id, limit=100):
        """Fetch all items from a board using cursor-based pagination."""
        all_items = []
        cursor = None
        while True:
            variables = {"board_id": board_id, "limit": limit}
            if cursor:
                variables["cursor"] = cursor
            data = monday.monday_query(query, variables, MONDAY_API_KEY)
            items_page = data["data"]["boards"][0]["items_page"]
            items = items_page["items"]
            all_items.extend(items)
            cursor = items_page.get("cursor")
            if not cursor:
                break
        return all_items
    
    data = monday.monday_query(query, {"board_id": DISPATCH_BOARD_ID}, MONDAY_API_KEY)

    if not data or "data" not in data or not data["data"].get("boards"):
        logging.error(f"Monday API error or empty response: {data}")
        messagebox.showerror("API Error", "Failed to fetch items from Monday.com. "
                            "Check your API key, board ID, and network connection.")
        return

    # items = data["data"]["boards"][0]["items_page"]["items"]
    items = fetch_all_items(DISPATCH_BOARD_ID)

    # 2. Filter for tomorrow (or Monday if today is Friday)
    today = datetime.today().date()
    if today.weekday() == 4:  # Friday
        target_date = today + timedelta(days=3)
    else:
        target_date = today + timedelta(days=1)
    target_date_str = target_date.strftime("%Y-%m-%d")

    date_col_id = column_id_map["Date"]
    auto_col_id = column_id_map["Auto #"]
    driver_col_id = column_id_map["Driver"]
    item_id_col_id = column_id_map["Item ID"]

    def get_col_value(item, col_id, key="text"):
        """
        Extracts the value for a given column from a Monday.com item.
        Handles dropdown columns by checking both 'text' and parsed 'value'.

        Args:
            item (dict): The Monday.com item.
            col_id (str): The column ID to extract.
            key (str): The key to extract ('text' by default).

        Returns:
            str or None: The extracted value, or None if not found.
        """
        for col in item["column_values"]:
            if col["id"] == col_id:
                # Try text first
                if col.get("text"):
                    return col["text"]
                # If text is empty, try to parse value for dropdowns
                if col.get("value"):
                    try:
                        val = json.loads(col["value"])
                        # Dropdowns: look for "labels" (multi-select) or "label" (single-select)
                        if "labels" in val and val["labels"]:
                            return val["labels"][0]
                        if "label" in val:
                            return val["label"]
                    except Exception as e:
                        logging.warning(f"Could not parse value for col {col_id}: {col['value']}")
                return None
        return None
    
    for item in items:
        driver_val = get_col_value(item, driver_col_id)
        date_val = get_col_value(item, date_col_id)
        logging.info(f"PRE-FILTER: Item '{item['name']}' | Driver: {driver_val!r} | Date: {date_val!r}")

    # Only items for the target date
    filtered_items = [item for item in items if get_col_value(item, date_col_id) == target_date_str]

    for item in filtered_items:
        driver_val = get_col_value(item, driver_col_id)
        logging.info(f"POST-FILTER: Item '{item['name']}' | Driver: {driver_val!r}")

    # Debug: Print all driver values from the filtered items
    all_driver_values = [get_col_value(item, driver_col_id) for item in filtered_items]
    logging.info(f"Driver values in filtered items: {all_driver_values}")

    # 3. Sort by Auto Number
    sorted_items = sorted(filtered_items, key=lambda item: int(get_col_value(item, auto_col_id) or 0))

    # 4. Group by normalized Driver
    items_by_driver = defaultdict(list)
    for item in sorted_items:
        driver = get_col_value(item, driver_col_id)
        norm_driver = normalize_name(driver)
        items_by_driver[norm_driver].append(item)

    logging.info(f"Normalized drivers found for upload: {list(items_by_driver.keys())}")

    # Build normalized mapping for driver board IDs and group IDs
    normalized_driver_board_ids = {normalize_name(k): v for k, v in DRIVER_BOARD_IDS.items()}

    # --- Identify dropdown columns by their IDs ---
    dropdown_col_ids = set()
    for col in board_columns["data"]["boards"][0]["columns"]:
        if col["type"] == "dropdown":
            dropdown_col_ids.add(col["id"])

    created_ids = []

    for norm_driver, driver_items in items_by_driver.items():
        driver_board_id = normalized_driver_board_ids.get(norm_driver)
        if not driver_board_id:
            logging.warning(f"Driver '{norm_driver}' found in dispatch board but not in DRIVER_BOARD_IDS mapping.")
            continue
        # Fetch group IDs for the driver's board
        driver_group_map = monday.get_group_ids(driver_board_id, MONDAY_API_KEY)
        normalized_group_map = {normalize_name(k): v for k, v in driver_group_map.items()}
        group_id = normalized_group_map.get(norm_driver)
        if not group_id:
            logging.warning(f"Group titles on {norm_driver}'s board: {list(driver_group_map.keys())}")
            logging.warning(f"No group ID '{norm_driver}' found on board {driver_board_id} for driver: {norm_driver}")
            continue

        for norm_driver, items in items_by_driver.items():
            logging.info(f"NORM GROUP: Driver '{norm_driver}' has {len(items)} items")

        company_col_id = column_id_map["Company"]

        for item in driver_items:
            # Use Item ID as the unique identifier for processing, but keep the name unchanged
            item_id_value = get_col_value(item, item_id_col_id)
            if not item_id_value:
                logging.warning(f"Item missing Item ID, skipping: {item}")
                continue

            name = item["name"]  # Keep the original item name

            values = {}
            company_label = None

            # Extract the company label from the item
            for col in item["column_values"]:
                if col["id"] == company_col_id:
                    company_label = col["text"]
                    break

            # Fetch current company options for the driver board
            driver_board_company_options = monday.get_dropdown_options(driver_board_id, company_col_id, MONDAY_API_KEY)

            # If the company label is missing from the driver board, set to empty
            if company_label not in driver_board_company_options:
                logging.warning(f"Company '{company_label}' not found in {norm_driver}'s driver board dropdown. Setting to empty.")
                company_label = ""

            for col in item["column_values"]:
                if col["id"] == auto_col_id:
                    continue  # skip auto number
                if col["id"] in dropdown_col_ids:
                    # Special handling for Company dropdown
                    if col["id"] == company_col_id:
                        values[col["id"]] = {"labels": [company_label]} if company_label else {"labels": []}
                    else:
                        if col["text"]:
                            values[col["id"]] = {"labels": [col["text"]]}
                elif col["value"]:
                    values[col["id"]] = json.loads(col["value"])
            # Create item on the correct Driver board in the correct group
            monday.create_item(driver_board_id, group_id, name, MONDAY_API_KEY, values)
            # created_ids.append(item["id"])
            created_ids.append(item_id_value)

        # --- Delay Between Drivers
        logging.info(f"Finished copying items for driver '{norm_driver}'. Waiting before next driver...")
        time.sleep(1) # 1 second delay between drivers
        # Add a version with a batch size limit (e.g., 10 items at a time) or more advanced batching!

    messagebox.showinfo("Success", f"Copied {len(sorted_items)} items to Driver Board.")


def launch_main_gui():
    """Launch the main menu window for Dispatch Agent workflows."""
    main_root = tk.Tk()
    main_root.title("Dispatch Agent")
    main_root.config(padx=40, pady=40)
    main_root.minsize(width=300, height=150)

    def open_create_jobs_on_dispatch_board():
        """Open the Dispatch Board job-creation screen."""
        main_root.destroy()  # Close main menu
        launch_create_jobs_on_dispatch_board_gui()  # Launch dispatch GUI

    def open_create_jobs_on_driver_board():
        """Open the Driver Board job-creation screen."""
        main_root.destroy()
        launch_create_jobs_on_driver_board_gui()

    def open_upload_schedule():
        """Open the schedule upload workflow."""
        main_root.destroy()
        launch_upload_schedule_gui()

    tk.Button(main_root, text="Create Jobs On Dispatch Board", 
              width=30, command=open_create_jobs_on_dispatch_board).pack(pady=15)
    tk.Button(main_root, text="Create Jobs On Driver Board",
              width=30, command=open_create_jobs_on_driver_board).pack(pady=15)
    tk.Button(main_root, text="Upload Schedule", 
              width=30, command=open_upload_schedule).pack(pady=15)

    main_root.mainloop()

if __name__ == "__main__":
    launch_main_gui()
