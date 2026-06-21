from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
import tkinter as tk
from tkinter import ttk, messagebox
from tkcalendar import DateEntry
import json
import logging
from collections import defaultdict
import time
import traceback
import requests
import difflib
import sys
from functools import partial

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
# =========================================================================== #

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()

MONDAY_API_KEY = os.getenv("MONDAY_API_KEY")
DISPATCH_BOARD_ID = os.getenv("DISPATCH_BOARD_ID") # <-- Actual Dispatch Board
DUMPSTER_INVENTORY_BOARD_ID = os.getenv("DUMPSTER_INVENTORY_BOARD_ID")
INVOICING_BOARD_ID = os.getenv("INVOICING_BOARD_ID")
AR_BOARD_ID = os.getenv("AR_BOARD_ID")
CUSTOMER_CONFIG_BOARD_ID = os.getenv("CUSTOMER_CONFIG_BOARD_ID")
GOOGLE_MAPS_API = os.getenv("GOOGLE_MAPS_API")

# Dumpster sizing
SIZE_LABEL_MAP = {
    '40 yard': '40 yard',
    '30 yard': '30 yard',
    '20 yard': '20 yard',
    '15 yard': '15 yard'
}

# Dumpster operations
DUMPSTER_DESC_INITIAL_DROP = 'Initial Drop'
DUMPSTER_DESC_DUMP_AND_REMOVE = 'Dump & Remove'

# Inventory thresholds
# INVENTORY_THRESHOLD = 3

# AR (Accounts Receivable)
AR_DAYS_OVERDUE_THRESHOLD = 61

# Location autocomplete
LOCATION_MIN_QUERY_LENGTH = 10 #3
LOCATION_DEBOUNCE_MS = 400

# Fuzzy matching
AR_EXEMPT_MATCH_RATIO = 0.85
AR_CUSTOMER_MATCH_RATIO = 0.7

def calculate_inventory_threshold(driver_board_ids, fallback_threshold=3):
    """
    Keep 1 spare dumpster for every 2 active drivers.
    Uses fallback_threshold if no drivers are available.
    """
    driver_count = len([board_id for board_id in driver_board_ids.values() if board_id])
    if driver_count == 0:
        return fallback_threshold
    return (driver_count + 1) // 2


def load_driver_board_ids():
    """
    Fetch driver names and their Monday.com board IDs from the Drivers Config board.

    Reads the DRIVER_CONFIG_BOARD_ID environment variable to locate the config board.
    Only includes drivers where the 'Active' checkbox is checked. Returns an empty
    dict if the env variable is not set or the API call fails.

    Returns:
        dict: {driver_name: board_id} for all active drivers.
    """
    board_id = os.getenv("DRIVER_CONFIG_BOARD_ID")
    if not board_id:
        return {}
    try:
        cols = monday.get_board_columns(board_id, MONDAY_API_KEY)
        col_map = {c["title"].strip(): c["id"] for c in cols["data"]["boards"][0]["columns"]}
        board_id_col = col_map.get("Board ID")
        active_col = col_map.get("Active")
        items = monday.fetch_all_board_items(MONDAY_API_KEY, board_id)
        result = {}
        for item in items:
            driver_name = item["name"].strip()
            driver_board_id_val = None
            is_active = True
            for col in item["column_values"]:
                if col["id"] == board_id_col:
                    driver_board_id_val = col["text"].strip() if col["text"] else None
                elif col["id"] == active_col:
                    is_active = col["text"] != "" if col["text"] is not None else True
            if driver_name and driver_board_id_val and is_active:
                result[driver_name] = driver_board_id_val
        logging.info(f"Loaded {len(result)} drivers from Monday config board.")
        return result
    except Exception as e:
        logging.warning(f"Failed to load driver board IDs from Monday: {e}")
        return {}

def checkbox_text_to_bool(text):
    """Return True if a Monday checkbox column is checked (non-empty text)."""
    return bool((text or "").strip())

def load_customer_config():
    """
    Load company-level rules from the Customer Config board on Monday.com.

    Reads CUSTOMER_CONFIG_BOARD_ID from the environment. Expects four columns:
    'Company' (item name), 'AR Exempt' (checkbox), 'PO Required' (checkbox),
    and 'Prepaid' (checkbox). Returns an empty dict if the board ID is not set
    or the API call fails.

    Returns:
        dict: {company_name: {"ar_exempt": bool, "po_required": bool, "prepaid": bool}}
    """
    if not CUSTOMER_CONFIG_BOARD_ID:
        logging.warning("CUSTOMER_CONFIG_BOARD_ID not set — customer rules disabled.")
        return {}
    try:
        cols = monday.get_board_columns(CUSTOMER_CONFIG_BOARD_ID, MONDAY_API_KEY)
        col_map = {c["title"].strip(): c["id"] for c in cols["data"]["boards"][0]["columns"]}
        ar_exempt_col = col_map.get("AR Exempt")
        po_required_col = col_map.get("PO Required")
        prepaid_col = col_map.get("Prepaid")
        items = monday.fetch_all_board_items(MONDAY_API_KEY, CUSTOMER_CONFIG_BOARD_ID)
        config = {}
        for item in items:
            company_name = item["name"].strip()
            if not company_name:
                continue
            flags = {"ar_exempt": False, "po_required": False, "prepaid": False}
            for col in item["column_values"]:
                if ar_exempt_col and col["id"] == ar_exempt_col:
                    flags["ar_exempt"] = checkbox_text_to_bool(col["text"])
                elif po_required_col and col["id"] == po_required_col:
                    flags["po_required"] = checkbox_text_to_bool(col["text"])
                elif prepaid_col and col["id"] == prepaid_col:
                    flags["prepaid"] = checkbox_text_to_bool(col["text"])
            config[company_name] = flags
        logging.info(f"Loaded customer config for {len(config)} companies.")
        return config
    except Exception as e:
        logging.warning(f"Failed to load Customer Config board: {e}")
        return {}

def find_customer_config_name(company_name, customer_config):
    """
    Resolve a company name to a key in customer_config using exact,
    case-insensitive, then fuzzy matching.

    Returns:
        str or None: The matched key, or None if no match found.
    """
    if not company_name or not customer_config:
        return None
    if company_name in customer_config:
        return company_name
    lower_name = company_name.lower()
    for key in customer_config:
        if key.lower() == lower_name:
            return key
    matches = difflib.get_close_matches(
        company_name, customer_config.keys(), n=1, cutoff=AR_CUSTOMER_MATCH_RATIO
    )
    return matches[0] if matches else None

def get_customer_rules(company_name):
    """
    Return the Customer Config flags and matched config name for a company.

    Returns:
        tuple: (rules_dict, matched_name_or_None)
            rules_dict keys: "ar_exempt", "po_required", "prepaid" (all bool).
    """
    default_rules = {"ar_exempt": False, "po_required": False, "prepaid": False}
    matched = find_customer_config_name(company_name, CUSTOMER_CONFIG)
    if not matched:
        return default_rules, None
    return CUSTOMER_CONFIG.get(matched, default_rules), matched

def load_contacts_from_monday():
    """
    Fetch contacts from the Monday.com Contacts board.

    Reads the CONTACTS_BOARD_ID environment variable to locate the board. Maps the
    'Company', 'Phone', and 'Email' columns to each contact. Returns 'N/A' for any
    empty Email field. Falls back to load_contacts() (local contacts.json) if the
    env variable is not set or the API call fails.

    Returns:
        list[dict]: List of contact dicts with keys 'name', 'company', 'phone', and 'email'.
    """
    board_id = os.getenv("CONTACTS_BOARD_ID")
    if not board_id:
        logging.warning("CONTACTS_BOARD_ID not set — falling back to local contacts.json")
        return load_contacts()
    try:
        cols = monday.get_board_columns(board_id, MONDAY_API_KEY)
        col_map = {c["title"].strip(): c["id"] for c in cols["data"]["boards"][0]["columns"]}
        company_col = col_map.get("Company")
        phone_col = col_map.get("Phone")
        email_col = col_map.get("Email")
        items = monday.fetch_all_board_items(MONDAY_API_KEY, board_id)
        contacts = []
        for item in items:
            contact = {"name": item["name"].strip(), "company": "", "phone": "", "email": "N/A"}
            for col in item["column_values"]:
                if col["id"] == company_col:
                    contact["company"] = col["text"] or ""
                elif col["id"] == phone_col:
                    contact["phone"] = col["text"] or ""
                elif col["id"] == email_col:
                    contact["email"] = col["text"] or "N/A"
            contacts.append(contact)
        logging.info(f"Loaded {len(contacts)} contacts from Monday contacts board.")
        return contacts
    except Exception as e:
        logging.warning(f"Failed to load contacts from Monday: {e}. Falling back to local file.")
        return load_contacts()

DRIVER_BOARD_IDS = load_driver_board_ids()
INVENTORY_THRESHOLD = calculate_inventory_threshold(DRIVER_BOARD_IDS)
CUSTOMER_CONFIG = load_customer_config()
contacts = load_contacts_from_monday()

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
    
# contacts = load_contacts()
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


def get_place_suggestions(query, api_key):
    """Return a list of (description, place_id) tuples from Places Autocomplete."""
    url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
    params = {"input": query, "key": api_key, "types": "address"}
    try:
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        if data.get("status") == "OK":
            return [(p["description"], p["place_id"]) for p in data["predictions"]]
    except Exception as e:
        logging.warning(f"Place suggestion error: {e}")
    return []

def geocode_place_id(place_id, api_key):
    """Return (lat, lng, formatted_address) for a given place_id."""
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"place_id": place_id, "key": api_key}
    try:
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        if data.get("status") == "OK":
            result = data["results"][0]
            loc = result["geometry"]["location"]
            return loc["lat"], loc["lng"], result["formatted_address"]
    except Exception as e:
        logging.warning(f"Geocoding error: {e}")
    return None, None, None

def fetch_ar_data():
    """
    Fetch all AR records from the Monday.com AR board.

    Returns:
        dict: {customer_name: {"Current": float, "1-30": float, "31-60": float,
               "61-90": float, "91 and over": float}}
        Returns an empty dict if AR_BOARD_ID is not set or the request fails.
    """
    if not AR_BOARD_ID:
        logging.warning("AR_BOARD_ID not set — AR check will be skipped.")
        return {}
    try:
        ar_board_columns = monday.get_board_columns(AR_BOARD_ID, MONDAY_API_KEY)
        ar_col_id_map = {
            col["title"].strip(): col["id"]
            for col in ar_board_columns["data"]["boards"][0]["columns"]
        }
        items = monday.fetch_all_board_items(MONDAY_API_KEY, AR_BOARD_ID)
        ar_data = {}
        for item in items:
            customer = item["name"].strip()
            record = {}
            for col in item["column_values"]:
                for title, col_id in ar_col_id_map.items():
                    if col["id"] == col_id:
                        try:
                            record[title] = float(
                                col["text"].replace(",", "").replace("$", "")
                            ) if col["text"] else 0.0
                        except Exception:
                            record[title] = 0.0
            ar_data[customer] = record
        logging.info(f"Loaded AR data for {len(ar_data)} customers.")
        return ar_data
    except Exception as e:
        logging.warning(f"Failed to fetch AR data: {e}")
        return {}

def find_ar_customer(company_name, ar_data, cutoff=0.7):
    """
    Find the best matching customer name in ar_data for the given company_name.

    Tries exact match, then case-insensitive match, then fuzzy match.

    Args:
        company_name (str): The company name from the dispatch/driver board.
        ar_data (dict): The AR data keyed by customer name.
        cutoff (float): Minimum similarity ratio for fuzzy matching (0–1).

    Returns:
        str or None: The matched key in ar_data, or None if no match found.
    """
    if not company_name or not ar_data:
        return None
    if company_name in ar_data:
        return company_name
    lower_name = company_name.lower()
    for key in ar_data:
        if key.lower() == lower_name:
            return key
    matches = difflib.get_close_matches(company_name, ar_data.keys(), n=1, cutoff=cutoff)
    return matches[0] if matches else None

def is_ar_exempt(company_name):
    """
    Check if a company is AR exempt via the Customer Config board.

    Args:
        company_name (str): The company name to check.

    Returns:
        bool: True if the company is AR exempt, False otherwise.
    """
    rules, _ = get_customer_rules(company_name)
    return rules.get("ar_exempt", False)

def check_ar_overdue(company, ar_data):
    """
    Check whether a company has invoices 61 or more days past due.

    Args:
        company (str): The company name to look up.
        ar_data (dict): The AR data fetched from the Monday.com AR board.

    Returns:
        tuple: (is_overdue: bool, overdue_amount: float, matched_name: str or None)
    """
    matched = find_ar_customer(company, ar_data)
    if not matched:
        return False, 0.0, None
    record = ar_data[matched]
    overdue_amount = record.get("61-90", 0.0) + record.get("91 and over", 0.0)
    return overdue_amount > 0, overdue_amount, matched

# --- Load AR data ---
ar_data = fetch_ar_data()

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
                if desc == DUMPSTER_DESC_INITIAL_DROP:
                    drops += 1
                elif desc == DUMPSTER_DESC_DUMP_AND_REMOVE:
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
                if desc == DUMPSTER_DESC_INITIAL_DROP:
                    drops += 1
                elif desc == DUMPSTER_DESC_DUMP_AND_REMOVE:
                    returns += 1
    return drops, returns

def fetch_location_suggestions(
    location_var,
    location_box,
    place_suggestions,
    location_coords,
    google_maps_api,
    ):
    """
    Fetch address autocomplete suggestions from the Google Places API
    based on the current text in the location field.
    """
    query = location_var.get()
    if len(query) < 3:
        location_box["values"] = []
        return

    suggestions = get_place_suggestions(query, google_maps_api)
    place_suggestions.clear()
    location_coords.clear()

    for desc, place_id in suggestions:
        place_suggestions[desc] = place_id

    location_box["values"] = list(place_suggestions.keys())
    if place_suggestions:
        location_box.event_generate("<Down>")


def on_location_keyrelease(
    event,
    root,
    location_var,
    location_box,
    place_suggestions,
    location_coords,
    location_after_id,
    google_maps_api,
    ):
    """
    Debounce typing in location combobox before fetching suggestions.
    """
    if event.keysym in ("Return", "Tab", "Up", "Down", "Left", "Right"):
        return

    if location_after_id[0]:
        root.after_cancel(location_after_id[0])

    location_after_id[0] = root.after(
        400,
        lambda: fetch_location_suggestions(
            location_var,
            location_box,
            place_suggestions,
            location_coords,
            google_maps_api,
        ),
    )


def on_location_selected(
    event,
    location_var,
    place_suggestions,
    location_coords,
    google_maps_api,
    ):
    """
    Resolve selected suggestion to lat/lng and store in location_coords.
    """
    desc = location_var.get()
    place_id = place_suggestions.get(desc)
    if not place_id:
        return

    lat, lng, address = geocode_place_id(place_id, google_maps_api)
    if lat and lng:
        location_coords["lat"] = lat
        location_coords["lng"] = lng
        location_coords["address"] = address
        logging.info(f"Location resolved: {address} ({lat}, {lng})")
    else:
        logging.warning(f"Could not geocode place_id: {place_id}")


def launch_create_jobs_gui(mode="dispatch"):
    """
    Unified job-creation GUI for both Dispatch and Driver boards.
    
    Args:
        mode (str): "dispatch" for Dispatch Board GUI, "driver" for Driver Board GUI.
    """
    # Mode-specific config
    if mode == "dispatch":
        window_title = "Create Jobs On Dispatch Board"
        loading_msg = "Adding items to Dispatch Board\n and Checking Inventory..."
        success_msg_template = "Created {duplicates} item(s) for {days} day(s) for {driver}."
        button_label = "Create Dispatch Items"
        board_id = DISPATCH_BOARD_ID
        group_id_map = driver_group_map
        column_map = column_id_map
    else:  # driver mode
        window_title = "Create Jobs On Driver Board"
        loading_msg = "Adding items to Driver Board\n and Checking Inventory..."
        success_msg_template = "Created {duplicates} item(s) for {days} day(s) for {driver} on their driver board."
        button_label = "Create Driver Items"
        board_id = None  # Will be fetched per-driver
        group_id_map = None  # Will be fetched per-driver
        column_map = None  # Will be fetched per-driver

    root = tk.Tk()
    root.title(window_title)
    root.config(padx=20, pady=20)

    fields = {}

    def add_label_entry(row, label, var_type=tk.StringVar, widget=None, **kwargs):
        """Add a label and entry (or widget) to the Tkinter grid."""
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
    location_var, location_box = add_label_entry(row, "Location", widget=ttk.Combobox, values=[])
    location_box.config(width=40)
    place_suggestions = {}
    location_coords = {}
    location_after_id = [None]
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

    # --- Location autocomplete handlers (shared, using top-level helpers) ---
    location_box.bind(
        "<KeyRelease>",
        partial(
            on_location_keyrelease,
            root=root,
            location_var=location_var,
            location_box=location_box,
            place_suggestions=place_suggestions,
            location_coords=location_coords,
            location_after_id=location_after_id,
            google_maps_api=GOOGLE_MAPS_API,
        ),
    )

    location_box.bind(
        "<<ComboboxSelected>>",
        partial(
            on_location_selected,
            location_var=location_var,
            place_suggestions=place_suggestions,
            location_coords=location_coords,
            google_maps_api=GOOGLE_MAPS_API,
        ),
    )

    # --- Company/contact filtering (shared) ---
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

    def open_contacts_gui():
        """Launch contact book with refresh callback."""
        def refresh_contacts():
            updated_contacts = load_contacts()
            updated_names = [c["name"] for c in updated_contacts]
            updated_phone_map = {c["name"]: c["phone"] for c in updated_contacts}
            updated_by_company = {}
            for c in updated_contacts:
                company = c.get("company", "")
                if company not in updated_by_company:
                    updated_by_company[company] = []
                updated_by_company[company].append(c)

            contacts_by_company.clear()
            contacts_by_company.update(updated_by_company)
            contact_phone_map.clear()
            contact_phone_map.update(updated_phone_map)

            site_contact_box['values'] = updated_names
            logging.info(f"Contacts refreshed: {len(updated_names)} contacts loaded.")

        contact_book.launch_contact_book(parent=root, on_close=refresh_contacts)

    def submit():
        """Submit form and create items."""
        loading_popup = show_loading_popup(root, loading_msg)
        try:
            item_name = item_name_var.get()
            driver = driver_var.get()
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

            # Resolve board IDs and column maps based on mode
            if mode == "dispatch":
                target_board_id = DISPATCH_BOARD_ID
                target_group_id = driver_group_map.get(driver)
                target_column_map = column_id_map
                if not target_group_id:
                    messagebox.showerror("Error", "Selected driver does not have a group ID.")
                    return
            else:  # driver mode
                target_board_id = DRIVER_BOARD_IDS.get(driver)
                if not target_board_id:
                    messagebox.showerror("Error", f"Selected driver '{driver}' does not have a driver board ID.")
                    return
                driver_group_map_local = monday.get_group_ids(target_board_id, MONDAY_API_KEY)
                target_group_id = driver_group_map_local.get(driver)
                if not target_group_id:
                    messagebox.showerror("Error", f"Group '{driver}' not found on driver board.")
                    return
                board_cols = monday.get_board_columns(target_board_id, MONDAY_API_KEY)
                target_column_map = {col["title"]: col["id"] for col in board_cols["data"]["boards"][0]["columns"]}

            logging.info(f"Target Board: {target_board_id}, Group: {target_group_id}")

            # --- Customer Config Checks ---
            customer_rules, _ = get_customer_rules(company)

            if customer_rules.get("prepaid"):
                messagebox.showwarning(
                    "Prepaid Customer",
                    f"{company} is a prepaid customer. Please contact billing and send "
                    "customer an invoice before dumpster request can be scheduled."
                )
                return

            if customer_rules.get("po_required") and not po.strip():
                messagebox.showwarning("PO Required", f"PO number is required for {company}.")
                return

            # --- AR Check ---
            if company and not customer_rules.get("ar_exempt"):
                is_overdue, overdue_amount, matched_name = check_ar_overdue(company, ar_data)
                if is_overdue:
                    messagebox.showerror(
                        "Account On Hold",
                        f"'{company}' has ${overdue_amount:,.2f} in invoices 61+ days past due.\n\n"
                        f"Matched AR record: '{matched_name}'\n\n"
                        "Job creation is not allowed until the account is brought current."
                    )
                    return

            # --- Dumpster Inventory Check ---
            if desc == DUMPSTER_DESC_INITIAL_DROP:
                inventory_size_label = SIZE_LABEL_MAP.get(size.lower())
                if not inventory_size_label:
                    messagebox.showerror("Error", f"Unknown dumpster size: {size}")
                    return

                inventory_board_columns = monday.get_board_columns(DUMPSTER_INVENTORY_BOARD_ID, MONDAY_API_KEY)
                inventory_col_id_map = {col["title"].strip().lower(): col["id"] for col in inventory_board_columns["data"]["boards"][0]["columns"]}
                size_col_ids = {k: v for k, v in inventory_col_id_map.items() if "yard" in k}
                inventory_date_col_id = inventory_col_id_map["date"]

                inventory = get_current_inventory(MONDAY_API_KEY, DUMPSTER_INVENTORY_BOARD_ID, size_col_ids, inventory_date_col_id)
                current_count = inventory.get(inventory_size_label, 0)

                dispatch_col_id_map = monday.get_column_ids(DISPATCH_BOARD_ID, MONDAY_API_KEY)
                dispatch_size_col_id = dispatch_col_id_map["size"]
                dispatch_desc_col_id = dispatch_col_id_map["description"]
                dispatch_date_col_id = dispatch_col_id_map["date"]

                today_str = start_date.strftime("%Y-%m-%d")
                drops, returns = count_pending_drops_and_returns(
                    MONDAY_API_KEY, DISPATCH_BOARD_ID, size, today_str,
                    dispatch_size_col_id, dispatch_desc_col_id, dispatch_date_col_id
                )

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
                if available <= INVENTORY_THRESHOLD:
                    messagebox.showwarning("Low Inventory", 
                                           f"We are currently out of {size} dumpsters "
                                           f"or inventory is low ({available} left, "
                                           f"threshold: {INVENTORY_THRESHOLD}).")
                    return

            logging.info(f"Creating {duplicates} items for driver {driver} starting {start_date.strftime('%a, %b %d, %Y')}")

            for day in range(days):
                date = (start_date + timedelta(days=day)).strftime("%Y-%m-%d")
                for dup in range(duplicates):
                    logging.info(f"Creating item {dup+1}/{duplicates} for date {date}")
                    column_values = {
                        target_column_map["Driver"]: driver,
                        target_column_map["Date"]: {"date": date},
                        target_column_map["Size"]: size,
                        target_column_map["Type"]: type_,
                        target_column_map["Description"]: desc,
                        target_column_map["Company"]: company,
                        target_column_map["Site Contact"]: site_contact,
                        target_column_map["Phone"]: {"phone": phone, "countryShortName": None},
                        target_column_map["PO #"]: po,
                    }

                    if location_coords.get("lat") and location_coords.get("lng"):
                        column_values[target_column_map["Location"]] = {
                            "lat": location_coords["lat"],
                            "lng": location_coords["lng"],
                            "address": location_coords.get("address", location_var.get()),
                        }
                    elif location_var.get():
                        logging.warning("Location text entered but no coordinates resolved — location will be skipped.")

                    logging.info(f"column_values: {column_values}")
                    monday.create_item(target_board_id, target_group_id, item_name, MONDAY_API_KEY, column_values)

            logging.info("All items created.")
            success_msg = success_msg_template.format(duplicates=duplicates, days=days, driver=driver)
            messagebox.showinfo("Success", success_msg)

        except Exception as e:
            messagebox.showerror("Exception", f"An error occurred:\n{e}\n\n{traceback.format_exc()}")
        finally:
            loading_popup.destroy()

    tk.Button(root, text=button_label, command=submit).grid(row=row, column=1, pady=10, padx=10, sticky="e")
    tk.Button(root, text="Contacts", command=open_contacts_gui).grid(row=row+1, column=1, pady=5, padx=10, sticky="e")

    def on_close():
        root.destroy()
        launch_main_gui()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


def launch_create_jobs_on_dispatch_board_gui():
    """Wrapper: Launch Dispatch Board job-creation GUI."""
    launch_create_jobs_gui("dispatch")


def launch_create_jobs_on_driver_board_gui():
    """Wrapper: Launch Driver Board job-creation GUI."""
    launch_create_jobs_gui("driver")


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
    
    # Debug: PRE-FILTER
    # for item in items:
    #     driver_val = get_col_value(item, driver_col_id)
    #     date_val = get_col_value(item, date_col_id)
        # logging.info(f"PRE-FILTER: Item '{item['name']}' | Driver: {driver_val!r} | Date: {date_val!r}")

    # Only items for the target date
    filtered_items = [item for item in items if get_col_value(item, date_col_id) == target_date_str]

    # Debug: POST-FILTER
    # for item in filtered_items:
    #     driver_val = get_col_value(item, driver_col_id)
        # logging.info(f"POST-FILTER: Item '{item['name']}' | Driver: {driver_val!r}")

    # Debug: Print all driver values from the filtered items
    # all_driver_values = [get_col_value(item, driver_col_id) for item in filtered_items]
    # logging.info(f"Driver values in filtered items: {all_driver_values}")

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

    warnings = []
    created_ids = []
    created_count = 0
    attempted_count = 0
    driver_copy_counts = {}

    for norm_driver, driver_items in items_by_driver.items():
        driver_copy_counts[norm_driver] = {
            "source": len(driver_items),
            "created": 0,
        }

        driver_board_id = normalized_driver_board_ids.get(norm_driver)
        if not driver_board_id:
            if norm_driver == "":
                msg = "Driver column on Dispatch board is empty."
            else:
                msg = (
                    f"Driver '{norm_driver}' is on the Dispatch board but is missing "
                    "from DRIVER_BOARD_IDS."
                )
            logging.warning(msg)
            warnings.append(msg)
            continue

        driver_group_map = monday.get_group_ids(driver_board_id, MONDAY_API_KEY)
        normalized_group_map = {normalize_name(k): v for k, v in driver_group_map.items()}
        group_id = normalized_group_map.get(norm_driver)
        if not group_id:
            msg = f"Driver '{norm_driver}' does not have a matching group on board {driver_board_id}."
            logging.warning(msg)
            warnings.append(msg)
            continue

        company_col_id = column_id_map["Company"]
        driver_board_company_options = monday.get_dropdown_options(
            driver_board_id, company_col_id, MONDAY_API_KEY
        )

        for item in driver_items:
            item_id_value = get_col_value(item, item_id_col_id)
            if not item_id_value:
                msg = f"Skipped item '{item['name']}' for driver '{norm_driver}' because Item ID is missing."
                logging.warning(msg)
                warnings.append(msg)
                continue

            attempted_count += 1
            name = item["name"]
            values = {}
            company_label = None

            for col in item["column_values"]:
                if col["id"] == company_col_id:
                    company_label = col["text"]
                    break

            if company_label and company_label not in driver_board_company_options:
            # if company_label not in driver_board_company_options:
                msg = (
                    f"Company '{company_label}' does not exist on {norm_driver}'s driver board. "
                    "The Company field was left blank."
                )
                logging.warning(msg)
                warnings.append(msg)
                company_label = ""

            for col in item["column_values"]:
                if col["id"] == auto_col_id:
                    continue
                if col["id"] in dropdown_col_ids:
                    if col["id"] == company_col_id:
                        values[col["id"]] = {"labels": [company_label]} if company_label else {"labels": []}
                    elif col["text"]:
                        values[col["id"]] = {"labels": [col["text"]]}
                elif col["value"]:
                    values[col["id"]] = json.loads(col["value"])

            try:
                monday.create_item(driver_board_id, group_id, name, MONDAY_API_KEY, values)
                created_ids.append(item_id_value)
                created_count += 1
                driver_copy_counts[norm_driver]["created"] += 1
            except Exception as e:
                msg = f"Failed to copy item '{name}' to driver '{norm_driver}': {e}"
                logging.warning(msg)
                warnings.append(msg)

        source_count = driver_copy_counts[norm_driver]["source"]
        copied_count = driver_copy_counts[norm_driver]["created"]
        if copied_count != source_count:
            msg = (
                f"{source_count} items were scheduled for '{norm_driver}', "
                f"but only {copied_count} were copied to the driver board."
            )
            logging.warning(msg)
            warnings.append(msg)

        # --- Delay Between Drivers
        logging.info(f"Finished copying items for driver '{norm_driver}'. Waiting before next driver...")
        time.sleep(1) # 1 second delay between drivers

    if warnings:
        summary = (
            f"Copied {created_count} of {len(sorted_items)} dispatch items to Driver Boards.\n\n"
            "Warnings:\n- " + "\n- ".join(warnings)
        )
        messagebox.showwarning("Upload Complete With Warnings", summary)
    else:
        messagebox.showinfo("Success", f"Copied {created_count} items to Driver Board.")


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
