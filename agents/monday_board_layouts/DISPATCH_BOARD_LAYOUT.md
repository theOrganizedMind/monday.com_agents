# Monday.com Dispatch and Driver Board Layout: 

This document describes the columns, types, and possible values for the Monday.com boards used by the `dispatch_agent`.
Both the **Dispatch** and **Driver** boards should have the following structure for full compatibility.

---

## Dispatch & Driver Board Columns

| Column Name      | Type                | Example Values / Notes                                                                 |
|------------------|---------------------|----------------------------------------------------------------------------------------|
| **Item Name**    | Text                | Any text (e.g., "Dumpster Drop - Main St.")                                            
| **Auto #**       | Auto Number         | Auto-incremented number (e.g., 1, 2, 3, ...)                                           
| **Duplicate**    | Button              | Used to duplicate an item                                                              
| **Driver**       | Dropdown            | "Driver One", "Driver Two", etc.                                  
| **Date**         | Date                | Format: `Mon, May 11, 2026` or `YYYY-MM-DD`                                            
| **Size**         | Dropdown            | "30 yard", "20 yard", etc.
| **Type**         | Dropdown            | "Asbestos", "Clean-Fill", "LEED", "Recycling", "C&D",
| **Description**  | Dropdown            | "Initial Drop", "Dump & Remove", "Dump & Return", "Swap"                               
| **Location**     | Location (Maps)     | Address, lat/lng (e.g., "123 North St., Jacksonville, FL, USA")                      
| **Company**      | Dropdown            | "Example Company One", "Example Company Two", etc.                        
| **Site Contact** | Text                | Name of site contact (e.g., "John Doe")                                                
| **Phone**        | Phone Number        | (e.g., "615-555-1234")                                                                 
| **PO #**         | Text                | Purchase order number                                                                  
| **Disposal**     | Dropdown            | "Disposal Location One", etc.                                                          
| **Files**        | File Upload         | Attach disposal/waste ticket or other files                                            
| **Status**       | Dropdown/Status     | "Done" (driver marks item as done to move to invoicing board), other statuses as needed

---

## Notes

- **Dropdown columns**: The options listed above are examples; you can customize them to match your workflow.
- **Location**: Should be a valid address and/or latitude/longitude for map integration.
- **Status**: Used to trigger automations (e.g., move to invoicing board when marked "Done").
- **Consistency**: Ensure both Dispatch and Driver boards use the same column structure and option values for seamless operation with the `dispatch_agent`.
