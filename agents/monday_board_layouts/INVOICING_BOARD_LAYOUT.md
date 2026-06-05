# Monday.com Invoicing Board Layout: 

This document describes the columns, types, and possible values for the Monday.com boards used by the `dispatch_agent`.
The **Invoicing** board should have the following structure for full compatibility.

---

## Invoicing Board Columns

| Column Name      | Type                | Example Values / Notes                                                                 |
|------------------|---------------------|----------------------------------------------------------------------------------------|
| **Item Name**    | Text                | Invoice #                                           
| **Auto #**       | Auto Number         | Auto-incremented number (e.g., 1, 2, 3, ...)                                           
| **Duplicate**    | Button              | Used to duplicate an item                                                              
| **Driver**       | Dropdown            | "Driver One", "Driver Two", etc.                                  
| **Date**         | Date                | Format: `Mon, May 11, 2026` or `YYYY-MM-DD`                                            
| **Size**         | Dropdown            | "30 yard", "20 yard", etc.
| **Type**         | Dropdown            | "Asbestos", "Clean-Fill", "LEED", "Recycling", "C&D"
| **Description**  | Dropdown            | "Initial Drop", "Dump & Remove", "Dump & Return", "Swap"                               
| **Location**     | Location (Maps)     | Address, lat/lng (e.g., "123 North St., Jacksonville, FL, USA")                      
| **Company**      | Dropdown            | "Example Company One", "Example Company Two", etc.                        
| **Site Contact** | Text                | Name of site contact (e.g., "John Doe")                                                
| **Phone**        | Phone Number        | (e.g., "615-555-1234")                                                                 
| **PO #**         | Text                | Purchase order number                                                                  
| **Disposal**     | Dropdown            | "Disposal Location One", etc.                                                          
| **Files**        | File Upload         | Attach disposal/waste ticket or other files                                            
| **Tons**         | Number              | Enter tonnage from waste ticket
| **Disposal Cost**| Number              | Enter the disposal cost from waste ticket
| **Price**        | Number              | Enter the price/invoice amount
| **Gross Profit** | Formula             | Formula column (price - disposal cost)
| **Invoice**      | Button (Automation) | Moves items from Invoicing group to Completed after invoiced.

---

## Notes

- **Dropdown columns**: The options listed above are examples; you can customize them to match your workflow.
- **Location**: Should be a valid address and/or latitude/longitude for map integration.
- **Consistency**: Ensure the invoicing board uses the same column structure and option values for seamless operation with the `dispatch_agent`.
