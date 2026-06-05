import tkinter as tk
from tkinter import messagebox, ttk
import json
import os
from dotenv import load_dotenv
import monday


# ========================================================================== #
# ================================ INFO ==================================== #
# ========================================================================== #
# Adds and Searches for contacts stored in a json file. 
# ========================================================================== #
# ================================ TODO ==================================== #
# ========================================================================== #
# TODO: 
# ========================================================================== #


CONTACTS_DATA = "json_files/contacts.json"
filtered_contacts = []

load_dotenv()
MONDAY_API_KEY = os.getenv("MONDAY_API_KEY")
DISPATCH_BOARD_ID = os.getenv("DISPATCH_BOARD_ID")

# casefold(company_name) -> original label from Dispatch board
dispatch_company_lookup = {}


def refresh_dispatch_company_values():
    """
    Pull Company dropdown values from Dispatch board and cache them.
    """
    global dispatch_company_lookup
    dispatch_company_lookup = {}

    if not MONDAY_API_KEY or not DISPATCH_BOARD_ID:
        return

    try:
        board_columns = monday.get_board_columns(DISPATCH_BOARD_ID, MONDAY_API_KEY)
        column_id_map = {
            col["title"].strip().lower(): col["id"]
            for col in board_columns["data"]["boards"][0]["columns"]
        }
        company_col_id = column_id_map.get("company")
        if not company_col_id:
            return

        company_options = monday.get_dropdown_options(
            DISPATCH_BOARD_ID, company_col_id, MONDAY_API_KEY
        )

        dispatch_company_lookup = {
            c.strip().casefold(): c.strip()
            for c in company_options
            if c and c.strip()
        }
    except Exception:
        dispatch_company_lookup = {}


def company_exists_on_dispatch_board(company):
    """
    True if company is empty/N/A or exists in Dispatch board Company dropdown.
    """
    if not company or not company.strip() or company.strip().upper() == "N/A":
        return True
    return company.strip().casefold() in dispatch_company_lookup


# Load data from file
def load_data(file_path):
    """
    Load data from a JSON file.

    This function checks if the specified JSON file exists. If it does, it 
    reads the file and returns the data as a list. If the file does not 
    exist, it returns an empty list.

    Parameters:
    file_path (str): The path to the JSON file.

    Returns:
    list: The data loaded from the JSON file, or an empty list if the file 
    does not exist.
    """
    if os.path.exists(file_path):
        with open(file_path, 'r') as file:
            return json.load(file)
    return []


# Save data to file
def save_data(data, file_path):
    """
    Save data to a JSON file.

    This function writes the specified data to a JSON file at the specified 
    file path.

    Parameters:
    data (list): The data to be saved to the JSON file.
    file_path (str): The path to the JSON file.

    Returns:
    None
    """
    with open(file_path, 'w') as file:
        json.dump(data, file, indent=4)


def clear_fields():
    """
    Clear the input fields.

    This function clears the values in the company, client, phone, and email 
    entry widgets.

    Parameters:
    None

    Returns:
    None
    """
    combo_company.set('')
    entry_client.delete(0, tk.END)
    entry_phone.delete(0, tk.END)
    entry_email.delete(0, tk.END)
    update_company_list()


def add_contact():
    """
    Add a new contact after validating the company against Dispatch board values.

    Reads form values, blocks save when the company does not exist on the
    Dispatch board, normalizes company text when possible, and persists the
    new record to the contacts JSON file.
    """
    company = combo_company.get()
    client = entry_client.get()
    phone = entry_phone.get()
    email = entry_email.get()

    if not company_exists_on_dispatch_board(company):
        messagebox.showwarning(
            "Company Error",
            f"Company name {company} does not exist on the dispatch board."
        )
        return

    if client and phone:
        # Normalize to the exact Dispatch-board label if present
        normalized_company = dispatch_company_lookup.get(
            company.strip().casefold(), company.strip()
        ) if company else "N/A"

        new_contact = {
            "company": normalized_company if normalized_company else "N/A",
            "name": client,
            "phone": phone,
            "email": email if email else "N/A",
        }

        contacts = load_data(CONTACTS_DATA)
        contacts.append(new_contact)
        save_data(contacts, CONTACTS_DATA)

        messagebox.showinfo("Success", "Contact added successfully!")
        clear_fields()
        update_contact_list()
        update_company_list()
    else:
        messagebox.showwarning(
            "Input Error",
            "Client name and phone number are required!"
        )


def update_contact():
    """
    Update the selected contact with current form values.

    Validates company values against Dispatch board options, updates the
    selected contact in the JSON store, and refreshes the visible lists.
    """
    selected_item = contact_list.selection()
    if selected_item:
        company = combo_company.get()
        if not company_exists_on_dispatch_board(company):
            messagebox.showwarning(
                "Company Error",
                f"Company name {company} does not exist on the dispatch board."
            )
            return

        item_index = int(selected_item[0])
        contacts = load_data(CONTACTS_DATA)

        normalized_company = dispatch_company_lookup.get(
            company.strip().casefold(), company.strip()
        ) if company else "N/A"

        contacts[item_index] = {
            "company": normalized_company if normalized_company else "N/A",
            "name": entry_client.get(),
            "phone": entry_phone.get(),
            "email": entry_email.get() if entry_email.get() else "N/A",
        }

        save_data(contacts, CONTACTS_DATA)
        messagebox.showinfo("Success", "Contact updated successfully!")
        clear_fields()
        update_contact_list()
        update_company_list()
    else:
        messagebox.showwarning("Selection Error", "No contact selected!")


def remove_contact():
    """
    Remove a contact from the contact book.

    This function retrieves the selected contact from the contact list,
    removes it from the contacts list, and saves the updated contacts list
    to the JSON file. After successfully removing the contact, it clears
    the entry fields and shows a success message. If no contact is
    selected, it shows a warning message.

    Parameters:
    None

    Returns:
    None
    """
    global filtered_contacts
    selected_item = contact_list.selection()
    if selected_item:
        item_index = int(selected_item[0])
        # Use the currently displayed list (filtered or full)
        current_list = filtered_contacts if filtered_contacts else load_data(CONTACTS_DATA)
        contact_to_remove = current_list[item_index]
        # Load the full contacts list
        contacts = load_data(CONTACTS_DATA)
        # Remove by unique fields (name + phone)
        contacts = [
            c for c in contacts
            if not (c["name"] == contact_to_remove["name"] and c["phone"] == contact_to_remove["phone"])
        ]
        save_data(contacts, CONTACTS_DATA)
        messagebox.showinfo("Success", "Contact removed successfully!")
        clear_fields()
        filtered_contacts = []  # Reset filter after removal
        update_contact_list()
        update_company_list()
    else:
        messagebox.showwarning("Selection Error", "No contact selected!")


def search_contact():
    """
    Search for contacts in the contact book based on the search term.

    This function retrieves the search term from the Tkinter entry widget 
    and searches for contacts in the JSON file that match the search term 
    in either the company name or client name. If matching contacts are 
    found, it displays the results in a new Tkinter window. If no matches 
    are found, it shows an information message. If the search term is 
    empty, it shows a warning message.

    Parameters:
    None

    Returns:
    None
    """
    global filtered_contacts
    company = combo_company.get()
    client = entry_client.get()

    if not company and not client:
        messagebox.showwarning("Input Error", 
                               "Please enter a company name or client name to search.")
        return

    contacts = load_data(CONTACTS_DATA)
    filtered_contacts = [contact for contact in contacts if (company.lower() in contact['company'].lower() \
            if company else True) and (client.lower() in contact['name'].lower() if client else True)]
    update_contact_list(filtered_contacts)


def clear_results():
    """
    Clear the search results and display the complete list of contacts.

    This function clears the search results and displays the complete list 
    of contacts in the contact list.

    Parameters:
    None

    Returns:
    None
    """
    global filtered_contacts
    filtered_contacts = []
    update_contact_list()
    update_company_list()
    clear_fields()


# Handle double-click event on contact list
def on_item_double_click(event):
    """
    Handle the double-click event on the contact list.

    This function retrieves the selected contact from the contact list and 
    populates the Tkinter entry widgets with the contact's details.

    Parameters:
    event (Event): The event object representing the double-click event.

    Returns:
    None
    """
    selected_item = contact_list.selection()
    if selected_item:
        item_index = int(selected_item[0])
        contacts = filtered_contacts if filtered_contacts else load_data(CONTACTS_DATA)
        contact = contacts[item_index]
        combo_company.set(contact["company"])
        entry_client.delete(0, tk.END)
        entry_client.insert(0, contact["name"])
        entry_phone.delete(0, tk.END)
        entry_phone.insert(0, contact["phone"])
        entry_email.delete(0, tk.END)
        entry_email.insert(0, contact["email"])


def update_contact_list(filtered_contacts=None):
    """
    Update the contact list display.

    This function updates the contact list display with the contacts from 
    the JSON file. If a filtered contacts list is provided, it displays 
    the filtered contacts instead. The contacts are sorted by company name
    in alphabetical order.

    Parameters:
    filtered_contacts (list, optional): A list of filtered contacts to be 
    displayed. Defaults to None.

    Returns:
    None
    """
    contacts = load_data(CONTACTS_DATA) if filtered_contacts is None else filtered_contacts
    contact_list.delete(*contact_list.get_children())
    for index, contact in enumerate(contacts):
        contact_list.insert("", "end", iid=index, values=(contact["company"], 
                            contact["name"], contact["phone"], contact["email"]))


def update_company_list():
    """
    Refresh company options in the company combobox.

    Prefers authoritative company values pulled from the Dispatch board and
    falls back to unique company names from local contacts data.
    """
    # Prefer authoritative Dispatch board company list.
    if dispatch_company_lookup:
        combo_company["values"] = sorted(dispatch_company_lookup.values())
        return

    # Fallback to companies from contacts.json if Dispatch list unavailable.
    contacts = load_data(CONTACTS_DATA)
    companies = sorted(
        set(contact["company"] for contact in contacts if contact["company"] != "N/A")
    )
    combo_company["values"] = companies


# ========================================================================== #
# ================================ GUI ===================================== #
# ========================================================================== #
def launch_contact_book(parent=None):
    """
    Launch the Contact Book UI as a standalone window or child dialog.

    Args:
        parent: Optional parent Tk window. If provided, opens as a modal
            Toplevel dialog; otherwise starts its own Tk root window.
    """
    global root, combo_company, entry_client, entry_phone, entry_email, contact_list, filtered_contacts
    filtered_contacts = []

    is_standalone = parent is None
    if is_standalone:
        root = tk.Tk()
    else:
        root = tk.Toplevel(parent)
        root.transient(parent)
        root.grab_set()

    root.title("Contact Book")
    root.config(padx=25, pady=25)

    # Labels and entry fields for contact information
    tk.Label(root, text="Company Name:").grid(row=0, column=0, padx=10, pady=5, sticky="e")
    combo_company = ttk.Combobox(root, width=27)
    combo_company.grid(row=0, column=1, padx=10, pady=5)

    tk.Label(root, text="*Client Name:").grid(row=1, column=0, padx=10, pady=5, sticky="e")
    entry_client = tk.Entry(root, width=30)
    entry_client.grid(row=1, column=1, padx=10, pady=5)

    tk.Label(root, text="*Phone Number:").grid(row=2, column=0, padx=10, pady=5, sticky="e")
    entry_phone = tk.Entry(root, width=30)
    entry_phone.grid(row=2, column=1, padx=10, pady=5)

    tk.Label(root, text="Email:").grid(row=3, column=0, padx=10, pady=5, sticky="e")
    entry_email = tk.Entry(root, width=30)
    entry_email.grid(row=3, column=1, padx=10, pady=5)

    # Buttons to add, update, and search contacts
    tk.Button(root, width=15, text="Add Contact", command=add_contact).grid(row=0, column=2, pady=5, sticky="w")
    tk.Button(root, width=15, text="Update Contact", command=update_contact).grid(row=1, column=2, pady=5, sticky="w")
    tk.Button(root, width=15, text="Remove Contact", command=remove_contact).grid(row=2, column=2, pady=5, sticky="w")
    tk.Button(root, width=15, text="Search Contacts", command=search_contact).grid(row=3, column=2, pady=5, sticky="w")
    tk.Button(root, width=15, text="Clear Results", command=clear_results).grid(row=6, column=2, pady=10, sticky="w")

    # Create contact list display
    contact_list = ttk.Treeview(
    root,
    columns=("Company Name", "Client Name", "Phone Number", "Email"),
    show="headings"
    )
    contact_list.heading("Company Name", text="Company Name")
    contact_list.heading("Client Name", text="Client Name")
    contact_list.heading("Phone Number", text="Phone Number")
    contact_list.heading("Email", text="Email")
    contact_list.grid(row=7, column=0, columnspan=3, padx=10, pady=10, sticky="nsew")

    # Bind double-click event
    contact_list.bind("<Double-1>", on_item_double_click)

    # Update contact list display on startup
    refresh_dispatch_company_values()
    update_contact_list()
    update_company_list()

    if is_standalone:
        root.mainloop()

if __name__ == "__main__":
    launch_contact_book()
 
