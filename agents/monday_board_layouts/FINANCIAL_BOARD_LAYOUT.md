# Monday.com Financial Board Layout: 

This document describes the columns, types, and possible values for the Monday.com boards used by the `financial_agent`.
The **Financial** board should have the following structure for full compatibility.

---

## Financials Board Columns

| Column Name      | Type                | Example Values / Notes                                                                 |
|------------------|---------------------|----------------------------------------------------------------------------------------|
| **Item Name**    | Text                | Any text                                         
| **Date**         | Date                | Format: `Mon, May 11, 2026` or `YYYY-MM-DD`                                            
| **Bank One**     | Number              | Enter current bank amount
| **Bank Two**     | Number              | Enter current bank amount
| **Bank Balance** | Formula             | Sums 'Bank One' and 'Bank Two' amounts
| **Daily Gross Profit**| Number         | Enter 'Daily Gross Profit' from Invoicing Board
| **Daily Overhead**| Number             | Enter 'Daily Overhead' amount
| **Estimated Daily P&L**| Formula       | Subtracts 'Daily Overhead' from 'Daily Gross Profit'
| **Monthly Overhead**| Formula          | Multiplys 'Daily Overhead' * 20 (work days in month)

---

## Notes

- **Consistency**: Ensure the board uses the same column structure and option values for seamless operation with the `financial_agent`.
