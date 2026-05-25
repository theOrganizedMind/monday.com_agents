import tkinter as tk
from tkinter import messagebox, ttk
import json
import os


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
    Add a new contact to the contact book.

    This function retrieves the company name, client name, phone number, 
    and email address from the respective Tkinter entry widgets. It then 
    creates a new contact dictionary with these details and appends it to 
    the contacts list stored in a JSON file. If the JSON file does not 
    exist, it creates a new one. After successfully adding the contact, 
    it clears the entry fields and shows a success message. If the client 
    name or phone number is missing, it shows a warning message.

    Parameters:
    None

    Returns:
    None
    """
    company = combo_company.get()
    client = entry_client.get()
    phone = entry_phone.get()
    email = entry_email.get()

    if client and phone:
        new_contact = {
            "company": company if company else "N/A", 
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
        messagebox.showwarning("Input Error", 
                               "Client name and phone number are required!")
        

def update_contact():
    """
    Update an existing contact in the contact book.

    This function retrieves the selected contact from the contact list, 
    updates its details with the values from the Tkinter entry widgets, 
    and saves the updated contacts list to the JSON file. After 
    successfully updating the contact, it clears the entry fields and 
    shows a success message. If no contact is selected, it shows a warning 
    message.

    Parameters:
    None

    Returns:
    None
    """
    selected_item = contact_list.selection()
    if selected_item:
        item_index = int(selected_item[0])
        contacts = load_data(CONTACTS_DATA)
        
        contacts[item_index] = {
            "company": combo_company.get() if combo_company.get() else "N/A",
            "client": entry_client.get(),
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
    selected_item = contact_list.selection()
    if selected_item:
        item_index = int(selected_item[0])
        contacts = load_data(CONTACTS_DATA)
        del contacts[item_index]
        save_data(contacts, CONTACTS_DATA)
        messagebox.showinfo("Success", "Contact removed successfully!")
        clear_fields()
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

def filter_contacts(event=None):
    """
    Filter the contact list and company dropdown in real time as the user types.

    This function is triggered on key release events in the company and client name
    entry fields. It filters the displayed contacts in the Treeview based on the
    current values of the company and client name fields. It also updates the
    company dropdown menu to only show company names that match the current input.

    Parameters:
        event (Event, optional): The Tkinter event object from the key release.
                                 Defaults to None.

    Returns:
        None
    """
    company = combo_company.get().lower()
    client = entry_client.get().lower()
    contacts = load_data(CONTACTS_DATA)
    filtered = [
        contact for contact in contacts
        if (company in contact["company"].lower() if company else True)
        and (client in contact["name"].lower() if client else True)
    ]
    update_contact_list(filtered)

    # Filter company dropdown values
    all_companies = sorted(set(contact["company"] for contact in contacts if contact["company"] != "N/A"))
    if company:
        filtered_companies = [c for c in all_companies if company in c.lower()]
    else:
        filtered_companies = all_companies
    combo_company["values"] = filtered_companies


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
    Update the company list in the company combobox.

    This function updates the company list in the company combobox with 
    the unique company names from the contacts list.

    Parameters:
    None

    Returns:
    None
    """
    contacts = load_data(CONTACTS_DATA)
    companies = sorted(set(contact["company"] for contact in contacts \
                           if contact["company"] != "N/A"))
    combo_company["values"] = companies


# ========================================================================== #
# ================================ GUI ===================================== #
# ========================================================================== #
if __name__ == "__main__":
    root = tk.Tk()
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
    tk.Button(root, width=15, text="Add Contact", 
            command=add_contact).grid(row=0, column=2, pady=5, sticky="w")
    tk.Button(root, width=15, text="Update Contact", 
            command=update_contact).grid(row=1, column=2, pady=5, sticky="w")
    tk.Button(root, width=15, text="Remove Contact", 
            command=remove_contact).grid(row=2, column=2, pady=5, sticky="w")

    tk.Button(root, width=15, text="Search Contacts", 
            command=search_contact).grid(row=3, column=2, pady=5, sticky="w")
    tk.Button(root, width=15, text="Clear Results", 
            command=clear_results).grid(row=6, column=2, pady=10, sticky="w")

    # Create contact list display
    contact_list = ttk.Treeview(root, columns=("Company Name", "Client Name", 
                                            "Phone Number", "Email"), show="headings")
    contact_list.heading("Company Name", text="Company Name")
    contact_list.heading("Client Name", text="Client Name")
    contact_list.heading("Phone Number", text="Phone Number")
    contact_list.heading("Email", text="Email")
    contact_list.grid(row=7, column=0, columnspan=3, padx=10, pady=10, sticky="nsew")

    # Bind double-click event to inventory list
    contact_list.bind("<Double-1>", on_item_double_click)

    # Bind live filter to typing in company/client fields
    combo_company.bind("<KeyRelease>", filter_contacts)
    entry_client.bind("<KeyRelease>", filter_contacts)

    # Update contact list display on startup
    update_contact_list()
    update_company_list()

    root.mainloop()

