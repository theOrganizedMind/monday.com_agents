from datetime import datetime, timedelta
from collections import namedtuple
import matplotlib.pyplot as plt
import mplcursors
import statistics
from dotenv import load_dotenv
import os
from collections import defaultdict
import logging

import monday

# ========================================================================== #
# ================================== INFO ================================== #
# ========================================================================== #

# ========================================================================== #
# ================================== TODO ================================== #
# ========================================================================== #
# TODO:
# ========================================================================== #

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()

NUM_MONTHS = 12
WORK_DAYS_IN_MONTH = 20
NUM_DRIVERS = 3
AVG_DAILY_FUEL_PER_TRUCK = 100

# Initialize Monday.com client
MONDAY_API_KEY = os.getenv("MONDAY_API_KEY")
FINANCIALS_BOARD_ID = os.getenv("FINANCIALS_BOARD_ID")
FINANCIALS_TODAY_GROUP_ID = os.getenv("FINANCIALS_TODAY_GROUP_ID")
BANK_ONE_BALANCE_GROUP_ID = os.getenv("BANK_ONE_BALANCE_GROUP_ID")
BANK_TWO_BALANCE_GROUP_ID = os.getenv("BANK_TWO_BALANCE_GROUP_ID")
DATE_COLUMN_GROUP_ID = os.getenv("DATE_COLUMN_GROUP_ID")

# ========================================================================== #
# ================================== Example Data ========================== #
# ========================================================================== #
employees = {
    "John Doe": 50000,
    "Jane Smith": 60000,
    "Alice Johnson": 55000,
    "Bob Brown": 58000,
    "Carol White": 62000,
    "David Black": 61000,
}

monthly_disposal_cost = {
    "2023-01": 28746.96, "2023-02": 75139.33, "2023-03": 9609.84, "2023-04": 7841.84, 
    "2023-05": 22373.33, "2023-06": 89105.77, "2023-07": 47241.33, "2023-08": 96054.70, 
    "2023-09": 118583.62, "2023-10": 59554.24, "2023-11": 56924.12, "2023-12": 76883.61,
    "2024-01": 111019.29,
}
# ========================================================================== #

def fetch_monthly_avg_balances_from_monday(num_months=12, all_items=None):
    """
    Calculates and prints the average total bank balance for each month,
    using the sum of bank_two and bank_one columns (number columns).
    Handles missing values as zero.
    """
    if all_items is None:
        all_items = monday.fetch_all_board_items(api_key=MONDAY_API_KEY, 
                                                 board_id=FINANCIALS_BOARD_ID)

    # print(f"Total items fetched: {len(all_items)}")
    logging.info(f"Total items fetched: {len(all_items)}")

    monthly_balances = defaultdict(list)
    for item in all_items:
        columns = {col['id']: col['text'] for col in item['column_values']}
        date_str = columns.get(DATE_COLUMN_GROUP_ID)
        sf_str = columns.get(BANK_TWO_BALANCE_GROUP_ID)
        lg_str = columns.get(BANK_ONE_BALANCE_GROUP_ID)
        # Handle missing/empty values as zero
        try:
            sf_val = float(sf_str.replace(',', '').replace('$', '')) if sf_str else 0.0
        except Exception:
            sf_val = 0.0
        try:
            lg_val = float(lg_str.replace(',', '').replace('$', '')) if lg_str else 0.0
        except Exception:
            lg_val = 0.0
        total_balance = sf_val + lg_val
        # Uncomment for debugging
        # print(f"Item ID: {item['id']}, Date: {date_str}, bank_two: {sf_str}, bank_one: {lg_str}, Total: {total_balance}")
        if not date_str:
            # print("  Skipping: missing date")
            logging.info("  Skipping: missing date")
            continue
        try:
            # Try multiple date formats
            for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y"):
                try:
                    date = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    date = None
            if not date:
                raise ValueError(f"Unrecognized date format: {date_str}")
            monthly_balances[(date.year, date.month)].append(total_balance)
        except Exception as e:
            # print(f"  Skipping item due to parse error: {e}")
            logging.warning(f"  Skipping item due to parse error: {e}")

    # Uncomment for debugging
    # print(f"\nMonthly balances grouped (before averaging):")
    # for (year, month), balances in monthly_balances.items():
    #     print(f"  {year}-{month:02d}: {balances}")

    # Calculate average for each month, sort by (year, month)
    monthly_avg = []
    for (year, month), balances in monthly_balances.items():
        if balances:
            avg = sum(balances) / len(balances)
            monthly_avg.append((year, month, avg))

    # Uncomment for debugging
    # print(f"\nMonthly averages (before limiting to last {num_months}):")
    # for year, month, avg in sorted(monthly_avg):
    #     print(f"  {year}-{month:02d}: ${avg:,.2f}")

    # Sort and print the last num_months
    monthly_avg.sort()
    print(f"\nAverage Bank Balances for the last {num_months} months:")
    for year, month, avg in monthly_avg[-num_months:]:
        print(f"{year}-{month:02d}: ${avg:,.2f}")


def fetch_bank_balances_from_monday(show_monthly_avg=False, num_months=12):
    """
    Fetch the bank_one and bank_two balances from the Monday.com 
    Financials board's Today group. Optionally print monthly averages.
    Returns:
        tuple: (bank_two_balance, bank_one_balance) as floats
    """
    all_items = monday.fetch_all_board_items(api_key=MONDAY_API_KEY, 
                                             board_id=FINANCIALS_BOARD_ID)

    # Optionally print monthly averages (comment/uncomment as needed)
    if show_monthly_avg:
        fetch_monthly_avg_balances_from_monday(num_months=num_months, all_items=all_items)

    # Filter for items in the Today group
    today_items = [item for item in all_items if item['group']['id'] == FINANCIALS_TODAY_GROUP_ID]
    if not today_items:
        # print("No items found in the Today group.")
        logging.info("No items found in the Today group.")
        return None, None

    # Use the first item in the Today group (or modify as needed)
    first_item = today_items[0]
    columns = {col['id']: col['text'] for col in first_item['column_values']}
    try:
        bank_two_balance = float(columns[BANK_TWO_BALANCE_GROUP_ID].replace(',', '').replace('$', ''))
        bank_one_balance = float(columns[BANK_ONE_BALANCE_GROUP_ID].replace(',', '').replace('$', ''))
        return bank_two_balance, bank_one_balance
    except Exception as e:
        # print(f"Error parsing balances: {e}")
        logging.warning(f"Error parsing balances: {e}")
        return None, None


total_payroll = round(sum(employees.values()))
total_monthly_payroll = round(total_payroll / NUM_MONTHS, 2)
total_weekly_payroll = round(total_monthly_payroll / 4)

print(f"Total weekly payroll = ${total_weekly_payroll:,.2f}")

month = datetime.now().strftime("%m")
year = datetime.now().strftime("%Y")
today = datetime.now()
seven_days_later = today + timedelta(days=7)

selected_disposal_months = list(monthly_disposal_cost.values())[-12:]
total_disposal_cost = sum(selected_disposal_months)
avg_disposal_cost = round(statistics.mean(selected_disposal_months))
avg_daily_disposal_cost = round(avg_disposal_cost / WORK_DAYS_IN_MONTH)

print(f"Average daily disposal cost for the past 12 months = ${avg_daily_disposal_cost:,.2f}")

# Set show_monthly_avg to True to show the monthly bank balance averages
bank_two_balance, bank_one_balance = fetch_bank_balances_from_monday(show_monthly_avg=False, num_months=6)
if bank_two_balance is None or bank_one_balance is None:
    # Fallback to manual input if API fails
    bank_two_balance = int(input("Please enter the bank_two bank balance = $"))
    bank_one_balance = int(input("Please enter the bank_one bank balance = $"))

total_current_bank_balance = bank_two_balance + bank_one_balance
num_days_to_display = int(input("Please enter the number of days to forecast and display: "))

pending_receivables_list = [
    (datetime(2026, 6, 5), 13_020.39), # Payment due date
    # Add more as needed
]

# --- Data Structures ---
Bill = namedtuple('Bill', ['date_str', 'amount', 'description'])

def receivables_due_on_date(receivables, date):
    """
    Calculate the total amount of receivables due on a specific date.
    Args:
        receivables (list of tuple): List of (expected_date, amount) tuples.
        date (datetime): The date to check for due receivables.
    Returns:
        float: Total amount of receivables due on the given date.
    """
    return sum(amount for expected_date, amount in receivables if expected_date.date() == date.date())

def parse_date(date_str):
    """
    Parse a date string in MMDDYYYY format to a datetime object.
    Returns None and prints an error if parsing fails.
    
    Args:
        date_str (str): Date string in MMDDYYYY format.
    
    Returns:
        datetime or None: Parsed datetime object or None if invalid.
    """
    try:
        return datetime.strptime(date_str, "%m%d%Y")
    except ValueError:
        print(f"Invalid date format: {date_str}")
        return None

def bills_due_on_date(bills, date):
    """
    Calculate the total amount of bills due on a specific date.
    
    Args:
        bills (list of Bill): List of Bill namedtuples.
        date (datetime): The date to check for due bills.
    
    Returns:
        float: Total amount of bills due on the given date.
    """
    return sum(
        bill.amount for bill in bills
        if (parsed := parse_date(bill.date_str)) and parsed.date() == date.date()
    )

# --- Balance Calculation ---
def calculate_daily_balances(start_balance, dates, bank_two_bills, 
                             bank_one_bills, pending_receivables, 
                             receivable_day=2):
    """
    Calculate the daily bank balances over a period, deducting bills and adding receivables.
    
    Args:
        start_balance (float): Starting bank balance.
        dates (list of datetime): List of dates for the period.
        bank_two_bills (list of Bill): Bills for bank_two bank.
        bank_one_bills (list of Bill): Bills for bank_one bank.
        pending_receivables (float): Amount to add after receivable_day.
        receivable_day (int): Index of the day to add receivables (default is 2, the 3rd day).
    
    Returns:
        list of float: Daily bank balances for each date.
    """
    balances = []
    balance = start_balance
    for i, d in enumerate(dates):
        try:
            bills_today = bills_due_on_date(bank_two_bills, d) + bills_due_on_date(bank_one_bills, d)
            balance -= bills_today
            if i == receivable_day:
                balance += pending_receivables
            balances.append(balance)
        except Exception as e:
            # print(f"Error calculating balance for {d}: {e}")
            logging.warning(f"Error calculating balance for {d}: {e}")
            balances.append(balance)
    return balances

def calculate_bank_balances(start_balance, dates, bills, pending_receivables_list=None):
    """
    Calculate the daily bank balances for a single account over a given period, 
    including multiple pending receivables.

    Args:
        start_balance (float): The initial bank balance at the start of the period.
        dates (list of datetime): List of dates to calculate balances for.
        bills (list of Bill): List of Bill namedtuples representing bills to deduct.
        pending_receivables_list (list of tuple, optional): List of (expected_date, amount) tuples.

    Returns:
        list of float: The calculated daily balances for each date in the period.

    The function deducts bills due each day and adds receivables on their expected date.
    """
    balances = []
    balance = start_balance
    for i, d in enumerate(dates):
        try:
            bills_today = bills_due_on_date(bills, d)
            balance -= bills_today
            if pending_receivables_list:
                receivables_today = receivables_due_on_date(pending_receivables_list, d)
                balance += receivables_today
            balances.append(balance)
        except Exception as e:
            # print(f"Error calculating balance for {d}: {e}")
            logging.warning(f"Error calculating balance for {d}: {e}")
            balances.append(balance)        
    return balances

# --- Plotting ---
def plot_balances(date_labels, bank_two_daily, bank_one_daily):
    """
    Plot the daily balances of bank_two and bank_one Bank accounts as separate lines.

    Args:
        date_labels (list of str): List of date labels for the x-axis 
        (e.g., ["04/04", "04/05", ...]).
        bank_two_daily (list of float): Daily balances for the bank_two account.
        bank_one_daily (list of float): Daily balances for the bank_one Bank account.

    The function creates a line chart with interactive tooltips showing the date 
    and balance for each point.
    """
    plt.style.use('seaborn-v0_8')
    plt.figure(figsize=(10, 6))
    line1, = plt.plot(date_labels, bank_two_daily, marker='o', label='bank_two', color='blue')
    line2, = plt.plot(date_labels, bank_one_daily, marker='o', label='bank_one', color='red')
    plt.fill_between(date_labels, bank_two_daily, bank_one_daily, facecolor='blue', alpha=0.1)
    plt.title(f"{len(date_labels)}-Day Bank Balance Trend (After Bills)")
    plt.xlabel("Date")
    plt.ylabel("Bank Balance ($)")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    cursor = mplcursors.cursor([line1, line2], hover=True)
    cursor.connect(
        "add", lambda sel: sel.annotation.set_text(
            f"Date: {date_labels[int(sel.index)]}\n"
            f"{sel.artist.get_label()} Balance: ${sel.target[1]:,.2f}"
        )
    )
    plt.show()

# --- Main Program ---
def main():
    """
    Main function to set up data, calculate balances, print summary, and plot results.
    """
    # Get current and next month/year
    current_month = today.strftime("%m")
    current_year = today.strftime("%Y")
    # Calculate next month and year
    if today.month == 12:
        next_month = "01"
        next_year = str(today.year + 1)
    else:
        next_month = f"{today.month + 1:02d}"
        next_year = current_year

    # Calculate upcoming Saturday and Sunday
    days_until_sat = (5 - today.weekday()) % 7
    upcoming_saturday = today + timedelta(days=days_until_sat)
    days_until_sun = (6 - today.weekday()) % 7
    upcoming_sunday = today + timedelta(days=days_until_sun)

    # Calculate upcoming Friday Payroll
    days_until_fri = (4 - today.weekday()) % 7
    upcoming_friday = today + timedelta(days=days_until_fri)

    # Prepare 7-day date range
    # dates = [today + timedelta(days=i) for i in range(7)]
    dates = [today + timedelta(days=i) for i in range(num_days_to_display)]
    date_labels = [d.strftime("%m/%d") for d in dates]

    disposal_bills = [
        Bill(d.strftime("%m%d%Y"), avg_daily_disposal_cost, "Next Day Disposal")
        for d in dates
    ]

    # Add weekly payroll dynamically
    weekly_payroll = [
        Bill(upcoming_friday.strftime("%m%d%Y"), total_weekly_payroll, "Weekly Payroll")
    ]

    # Add weekend disposal bills dynamically
    weekend_disposal_bills = [
        Bill(upcoming_saturday.strftime("%m%d%Y"), -avg_daily_disposal_cost, "Minus Weekend Disposal"),
        Bill(upcoming_sunday.strftime("%m%d%Y"), -avg_daily_disposal_cost, "Minus Weekend Disposal"),
    ]

    bank_two_bills_list = [
        # --- Current Month ---
        Bill(f"{current_month}01{current_year}", 2000.00, "Property Rent"),
        Bill(f"{current_month}09{current_year}", 5000.00, "Auto Insurance"),
        Bill(f"{current_month}07{current_year}", 28_972.08, "Disposal"),
        # --- Next Month --- 
        Bill(f"{next_month}01{next_year}", 2000.00, "Property Rent"),
        Bill(f"{next_month}09{next_year}", 5000.00, "Auto Insurance"),
        # --- AMEX ---
    ] + weekend_disposal_bills + disposal_bills

    bank_one_bills_list = [
        # --- Current Monthly Loans ---
        Bill(f"{current_month}03{current_year}", 1500.56, "Bank One Loan"),
        Bill(f"{current_month}15{current_year}", 818.79, "Bank One Loan"),
        # --- Checks and Other Payments ---
        Bill(f"{current_month}05{current_year}", 2000, "Permits"),
        Bill(f"{current_month}05{current_year}", 6277, "Subcontractor Payments"),
        # --- Next Month ---
        Bill(f"{next_month}03{next_year}", 1500.56, "Bank One Loan"),
        Bill(f"{next_month}15{next_year}", 818.79, "Bank One Loan"),

        # --- Payroll ---
    ] + weekly_payroll

    bank_two_bills = bank_two_bills_list
    bank_one_bills = bank_one_bills_list

    bank_two_daily = calculate_bank_balances(
        bank_two_balance, dates, bank_two_bills, pending_receivables_list=pending_receivables_list
    )
    bank_one_daily = calculate_bank_balances(
        bank_one_balance, dates, bank_one_bills, pending_receivables_list=None
    )

    # Optionally, calculate combined daily balances
    combined_daily = [sf + lg for sf, lg in zip(bank_two_daily, bank_one_daily)]    

    # Get the set of dates to display
    display_dates = set(d.date() for d in dates)

    # Filter and sum bills due within the displayed range
    bank_two_total = sum(
        b.amount for b in bank_two_bills
        if (parsed := parse_date(b.date_str)) and parsed.date() in display_dates
    )
    bank_one_total = sum(
        b.amount for b in bank_one_bills
        if (parsed := parse_date(b.date_str)) and parsed.date() in display_dates
    )

    # Print summary
    print(f"\nTotal current bank balance = ${total_current_bank_balance:,.2f}\n")
    print(f"Total bank_two Bills Due in {num_days_to_display} day(s) = ${bank_two_total:,.2f}")
    print(f"Total bank_one Bills Due in {num_days_to_display} day(s) = ${bank_one_total:,.2f}\n")
    if pending_receivables_list:
        print("Pending receivables to be added:")
        for expected_date, amount in pending_receivables_list:
            print(f"  ${amount:,.2f} due on {expected_date.strftime('%m/%d/%Y')}")
    print(f"\nEstimated daily balances for next {num_days_to_display} days:")
    for label, bal in zip(date_labels, combined_daily):
        print(f"{label}: ${bal:,.2f}")

    # Plot
    # plot_balances(date_labels, daily_balances)
    plot_balances(date_labels, bank_two_daily, bank_one_daily)

if __name__ == "__main__":
    main()
