import requests
import re
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
DISPATCH_BOARD_ID = os.getenv("DISPATCH_BOARD_ID") #Test Dispatch Board
INVOICING_BOARD_ID = os.getenv("INVOICING_BOARD_ID")

# Add all driver board IDs here, matching the driver names in your Dispatch Board
DRIVER_BOARD_IDS = {
    "Jane Doe": os.getenv("JANE_DOE_BOARD_ID"),
    "John Smith": os.getenv("JOHN_SMITH_BOARD_ID"),
    # Add more drivers as needed
}

def monday_query(query, variables=None):
    """
    Send a GraphQL query or mutation to the Monday.com API.

    Args:
        query (str): The GraphQL query or mutation string.
        variables (dict, optional): Variables for the query/mutation.

    Returns:
        dict: The JSON response from the API.
    """
    url = "https://api.monday.com/v2"
    headers = {
        "Authorization": MONDAY_API_KEY,
        "Content-Type": "application/json"
    }
    response = requests.post(url, json={"query": query, "variables": variables}, headers=headers)
    # print(f"Received response: {response.status_code}")
    logging.info(f"Received response: {response.status_code}")
    return response.json()

def get_board_columns(board_id):
    """
    Fetch the columns for a given Monday.com board.

    Args:
        board_id (str): The ID of the board.

    Returns:
        dict: The columns data from the board.
    """
    # print(f"Fetching board columns for Board ID: {board_id}")
    logging.info(f"Fetching board columns for Board ID: {board_id}")
    query = """
    query ($board_id: [ID!]) {
      boards(ids: $board_id) {
        columns {
          id
          title
          type
          settings_str
        }
      }
    }
    """
    return monday_query(query, {"board_id": board_id})

def get_dropdown_options(board_id, column_id):
    """
    Get dropdown options for a specific column in a Monday.com board.

    Args:
        board_id (str): The ID of the board.
        column_id (str): The ID of the dropdown column.

    Returns:
        list: List of dropdown option names.
    """
    # print(f"Fetching dropdown options for column: {column_id}")
    logging.info(f"Fetching dropdown options for column: {column_id}")
    columns = get_board_columns(board_id)
    for col in columns["data"]["boards"][0]["columns"]:
        if col["id"] == column_id and col["type"] == "dropdown":
            import json
            settings = json.loads(col["settings_str"])
            return [opt["name"] for opt in settings["labels"]]
    return []

def get_group_ids(board_id):
    """
    Retrieve group IDs and titles for a given Monday.com board.

    Args:
        board_id (str): The ID of the board.

    Returns:
        dict: Mapping of group titles to group IDs.
    """
    query = """
    query ($board_id: [ID!]) {
      boards(ids: $board_id) {
        groups {
          id
          title
        }
      }
    }
    """
    result = monday_query(query, {"board_id": board_id})
    return {g["title"]: g["id"] for g in result["data"]["boards"][0]["groups"]}

def create_item(board_id, group_id, item_name, column_values=None):
    """
    Create an item on a Monday.com board in a specific group.

    Args:
        board_id (str): The ID of the board.
        group_id (str): The ID of the group.
        item_name (str): The name of the item to create.
        column_values (dict, optional): Column values for the item.

    Returns:
        dict: The response from the API after creating the item.
    """
    if column_values:
        # print(f"Creating item '{item_name}' in group '{group_id}' with values: {column_values}")
        logging.info(f"Creating item '{item_name}' in group '{group_id}' with values: {column_values}")
        query = """
        mutation ($board_id: ID!, $group_id: String!, $item_name: String!, $column_values: JSON!) {
          create_item(board_id: $board_id, group_id: $group_id, item_name: $item_name, column_values: $column_values) {
            id
          }
        }
        """
        variables = {
            "board_id": board_id,
            "group_id": group_id,
            "item_name": item_name,
            "column_values": json.dumps(column_values)
        }
    else:
        # print(f"Creating item '{item_name}' in group '{group_id}' with NO column values")
        logging.info(f"Creating item '{item_name}' in group '{group_id}' with NO column values")
        query = """
        mutation ($board_id: ID!, $group_id: String!, $item_name: String!) {
          create_item(board_id: $board_id, group_id: $group_id, item_name: $item_name) {
            id
          }
        }
        """
        variables = {
            "board_id": board_id,
            "group_id": group_id,
            "item_name": item_name
        }
    response = monday_query(query, variables)
    # print("Create item response:", response)
    logging.info(f"Create item response: {response}")
    if "errors" in response:
        # print("Error creating item:", response["errors"])
        logging.error(f"Error creating item: {response['errors']}")
    return response

# --- Fetch dynamic dropdowns and group IDs ---
board_columns = get_board_columns(DISPATCH_BOARD_ID)
group_map = get_group_ids(DISPATCH_BOARD_ID)

# Map column titles to IDs for easy access
column_id_map = {col["title"]: col["id"] for col in board_columns["data"]["boards"][0]["columns"]}

# Fetch dropdown options
size_options = get_dropdown_options(DISPATCH_BOARD_ID, column_id_map["Size"])
type_options = get_dropdown_options(DISPATCH_BOARD_ID, column_id_map["Type"])
desc_options = get_dropdown_options(DISPATCH_BOARD_ID, column_id_map["Description"])
company_options = get_dropdown_options(DISPATCH_BOARD_ID, column_id_map["Company"])
driver_options = get_dropdown_options(DISPATCH_BOARD_ID, column_id_map["Driver"])

# Map driver names to group IDs (ensure group titles match driver names)
driver_group_map = {name: group_map.get(name) for name in driver_options}

# After fetching group_map and driver_options
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


def launch_create_jobs_gui():
    root = tk.Tk()
    root.title("Create Jobs")
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
    duplicates_var, _ = add_label_entry(row, "Duplicates", var_type=tk.IntVar)
    row += 1
    days_var, _ = add_label_entry(row, "Days", var_type=tk.IntVar)
    row += 1

    def open_contacts_gui():
        """
        Launch the contact_book.py GUI in a new process for managing contacts.
        """
        # Adjust the path if needed
        subprocess.Popen(["python", os.path.join("contact_book", "contact_book.py")])

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
        location = location_var.get() # <-- Not Used
        company = company_var.get()
        site_contact = site_contact_var.get()
        phone = phone_var.get()
        duplicates = duplicates_var.get()
        days = days_var.get()

        logging.info(f"DISPATCH_BOARD_ID: {DISPATCH_BOARD_ID}")
        logging.info(f"group_id: {group_id}")

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
                    column_id_map["Date"]: {"date": date},
                    column_id_map["Size"]: size,
                    column_id_map["Type"]: type_,
                    column_id_map["Description"]: desc,
                    # column_id_map["Location"]: {"address": location}, # <-- Does Not Work See API Docs needs (lat/lng)
                    column_id_map["Company"]: company,
                    column_id_map["Site Contact"]: site_contact,
                    column_id_map["Phone"]: {"phone": phone, "countryShortName": None},
                    column_id_map["Phone"]: phone
                }
                # print(type(column_values[column_id_map["Location"]]), column_values[column_id_map["Location"]])
                # print("column_values:", column_values)
                logging.info(f"column_values: {column_values}")
                create_item(DISPATCH_BOARD_ID, group_id, item_name, column_values)
                # create_item(DISPATCH_BOARD_ID, group_id, item_name)
        # print("All items created.")
        logging.info("All items created.")
        messagebox.showinfo("Success", f"Created {duplicates} item(s) for {days} day(s) for {driver}.")

    tk.Button(root, text="Create Dispatch Items", command=submit).grid(row=row, column=1, pady=15, padx=10, sticky="e")
    tk.Button(root, text="Contacts", command=open_contacts_gui).grid(row=row+1, column=1, pady=5, padx=10, sticky="e")

    root.mainloop()

def launch_upload_schedule_gui():
    """
    Copies tomorrow's (or Monday's) items from the Dispatch Board to the Driver Board,
    preserving order using the Auto Number column, and deletes originals after success.
    """
    query = """
    query ($board_id: [ID!]) {
    boards(ids: $board_id) {
        items_page {
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
    data = monday_query(query, {"board_id": DISPATCH_BOARD_ID})

    if not data or "data" not in data or not data["data"].get("boards"):
        logging.error(f"Monday API error or empty response: {data}")
        messagebox.showerror("API Error", "Failed to fetch items from Monday.com. Check your API key, board ID, and network connection.")
        return

    items = data["data"]["boards"][0]["items_page"]["items"]

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

    def get_col_value(item, col_id, key="text"):
        for col in item["column_values"]:
            if col["id"] == col_id:
                return col.get(key)
        return None

    # Only items for the target date
    filtered_items = [item for item in items if get_col_value(item, date_col_id) == target_date_str]

    # 3. Sort by Auto Number
    sorted_items = sorted(filtered_items, key=lambda item: int(get_col_value(item, auto_col_id) or 0))

    # 4. Group by Driver
    items_by_driver = defaultdict(list)
    for item in sorted_items:
        driver = get_col_value(item, driver_col_id)
        items_by_driver[driver].append(item)

    created_ids = []

    for driver, driver_items in items_by_driver.items():
        driver_board_id = DRIVER_BOARD_IDS.get(driver)
        if not driver_board_id:
            logging.warning(f"No board ID found for driver: {driver}")
            continue
        # Fetch group IDs for the driver's board
        driver_group_map = get_group_ids(driver_board_id)
        group_id = driver_group_map.get(driver)
        if not group_id:
            logging.warning(f"No group ID '{driver}' found on board {driver_board_id} for driver: {driver}")
            continue
        for item in driver_items:
            name = item["name"]
            # Build column_values dict (skip Auto Number)
            values = {}
            for col in item["column_values"]:
                if col["id"] == auto_col_id:
                    continue  # skip auto number
                if col["value"]:
                    values[col["id"]] = json.loads(col["value"])
            # Create item on the correct Driver board in the correct group
            create_item(driver_board_id, group_id, name, values)
            created_ids.append(item["id"])

    messagebox.showinfo("Success", f"Copied {len(sorted_items)} items to Driver Board.")

def launch_main_gui():
    main_root = tk.Tk()
    main_root.title("Dispatch Agent")
    main_root.config(padx=40, pady=40)
    main_root.minsize(width=300, height=150)

    def open_create_jobs():
        main_root.destroy()  # Close main menu
        launch_create_jobs_gui()  # Launch dispatch GUI

    def open_upload_schedule():
        main_root.destroy()
        launch_upload_schedule_gui()

    tk.Button(main_root, text="Create Jobs", width=20, command=open_create_jobs).pack(pady=15)
    tk.Button(main_root, text="Upload Schedule", width=20, command=open_upload_schedule).pack(pady=15)

    main_root.mainloop()

if __name__ == "__main__":
    launch_main_gui()
