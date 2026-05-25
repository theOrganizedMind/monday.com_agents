# Monday Agents

A Python desktop application for managing dispatch jobs and contacts, 
integrated with Monday.com boards. This tool provides a GUI for creating, 
organizing, and uploading dispatch jobs, as well as managing contact information.

---

## Features

- **Create Dispatch Jobs:**  
	Easily create one or multiple dispatch jobs with dynamic dropdowns for 
    drivers, companies, contacts, and more, all synced with your Monday.com 
    board configuration.

- **Upload Schedule:**  
	Copy scheduled jobs from the main Dispatch Board to individual Driver Boards, 
    preserving order and grouping, with support for recurring jobs and multi-day scheduling.

- **Contact Book Integration:**  
	Manage and auto-fill site contact information from a dedicated contact book,
    with company-based filtering and phone number autofill.

- **Monday.com API Integration:**  
	All job and contact data is synced with your Monday.com boards using the GraphQL API.

- **User-Friendly GUI:**  
	Built with Tkinter and tkcalendar for a simple, accessible desktop experience.

---

## Project Structure

```
agents/
	dispatch_agent.py      # Main dispatch agent GUI and Monday.com integration
contact_book/
	contact_book.py        # Contact book GUI for managing contacts
json_files/
	contacts.json          # Contact data in JSON format
requirements.txt         # Python dependencies
LICENSE.txt
README.md
```

---

## Requirements

- Python 3.8+
- Monday.com API Key and Board IDs (set in a `.env` file)
- Required Python packages (see `requirements.txt`):
	- requests
	- python-dotenv
	- tkcalendar
	- tkinter (usually included with Python)
	- (others as listed in requirements.txt)

---

## Setup

1. **Clone the repository:**
	 ```sh
	 git clone https://github.com/theOrganizedMind/monday.com_agents.git
	 cd monday_agents
	 ```

2. **Install dependencies:**
	 ```sh
	 pip install -r requirements.txt
	 ```

3. **Configure environment variables:**
	 - Create a `.env` file in the project root with your Monday.com API key and board IDs:
		 ```
		 MONDAY_API_KEY=your_monday_api_key
		 DISPATCH_BOARD_ID=your_dispatch_board_id
		 INVOICING_BOARD_ID=your_invoicing_board_id
		 JANE_DOE_BOARD_ID=driver_board_id_1
		 JOHN_SMITH_BOARD_ID=driver_board_id_2
		 # Add more driver board IDs as needed
		 ```

4. **Prepare contacts:**
	 - Edit `json_files/contacts.json` to include your contact data.

---

## Usage

- **Run the Dispatch Agent:**
	```sh
	python agents/dispatch_agent.py
	```
	- Use the GUI to create jobs or upload schedules.
	- Access the contact book from within the job creation window.

- **Manage Contacts:**
	- Launch the contact book GUI from the Dispatch Agent or directly:
		```sh
		python contact_book/contact_book.py
		```

---

## Customization

- Add or update driver names and board IDs in your `.env` file and Monday.com board.
- Update dropdown options (Size, Type, Description, Company, Driver) directly in 
your Monday.com board columns.

---

## Logging

- Application logs are printed to the console for troubleshooting and auditing.

---

## License

See [LICENSE.txt](LICENSE.txt) for license information.
 
