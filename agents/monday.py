import requests
import logging
import json


# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')


def monday_query(query, variables=None, api_key=None):
    """
    Send a GraphQL query or mutation to the Monday.com API.
    """
    url = "https://api.monday.com/v2"
    if not api_key:
        raise ValueError("API key must be provided to monday_query.")
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json"
    }
    response = requests.post(url, json={"query": query, "variables": variables}, headers=headers)
    logging.info(f"Received response: {response.status_code}")
    return response.json()

def get_board_columns(board_id, api_key):
    """
    Fetch the columns for a given Monday.com board.
    """
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
    return monday_query(query, {"board_id": board_id}, api_key=api_key)


def get_dropdown_options(board_id, column_id, api_key):
    """
    Get dropdown options for a specific column in a Monday.com board.
    """
    logging.info(f"Fetching dropdown options for column: {column_id}")
    columns = get_board_columns(board_id, api_key)
    for col in columns["data"]["boards"][0]["columns"]:
        if col["id"] == column_id and col["type"] == "dropdown":
            settings = json.loads(col["settings_str"])
            return [opt["name"] for opt in settings["labels"]]
    return []


def get_group_ids(board_id, api_key):
    """
    Retrieve group IDs and titles for a given Monday.com board.
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
    result = monday_query(query, {"board_id": board_id}, api_key=api_key)
    return {g["title"]: g["id"] for g in result["data"]["boards"][0]["groups"]}


def create_item(board_id, group_id, item_name, api_key, column_values=None):
    """
    Create an item on a Monday.com board in a specific group.
    """
    if column_values:
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
    response = monday_query(query, variables, api_key=api_key)
    logging.info(f"Create item response: {response}")
    if "errors" in response:
        logging.error(f"Error creating item: {response['errors']}")
    return response


def fetch_all_board_items(api_key, board_id):
    """
    Fetches all items from the Monday.com board using pagination.
    Returns a list of all items.
    """
    query = """
    query ($board_id: [ID!], $limit: Int, $cursor: String) {
      boards(ids: $board_id) {
        items_page(limit: $limit, cursor: $cursor) {
          cursor
          items {
            id
            name
            group {
              id
            }
            column_values {
              id
              text
            }
          }
        }
      }
    }
    """
    variables = {
        "board_id": board_id,
        "limit": 100,
        "cursor": None
    }
    all_items = []
    while True:
        logging.info("Fetching Data...")
        data = monday_query(query, variables, api_key=api_key)
        try:
            items_page = data['data']['boards'][0]['items_page']
            items = items_page['items']
            all_items.extend(items)
            cursor = items_page['cursor']
            if not cursor:
                break
            variables['cursor'] = cursor
        except Exception as e:
            logging.warning(f"Error fetching items from Monday.com: {e}")
            break
    return all_items


def fetch_items_in_group(api_key, board_id, group_id):
    """
    Fetch all items in a specific group on a Monday.com board.
    Returns a list of item dicts.
    """
    query = """
    query ($board_id: [ID!], $group_id: [String!], $limit: Int, $cursor: String) {
      boards(ids: $board_id) {
        groups(ids: $group_id) {
          id
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
    }
    """
    items = []
    cursor = None
    while True:
        variables = {
            "board_id": board_id,
            "group_id": [group_id],
            "limit": 100,
        }
        if cursor:
            variables["cursor"] = cursor
        data = monday_query(query, variables, api_key)
        group_data = data["data"]["boards"][0]["groups"][0]
        page = group_data["items_page"]
        items.extend(page["items"])
        cursor = page.get("cursor")
        if not cursor:
            break
    return items


def get_column_ids(board_id, api_key):
    """
    Returns a dict mapping lowercased column titles to their IDs for the given board.
    Example: {'size': 'numbers', 'description': 'dropdown', 'date': 'date4'}
    """
    board_columns = get_board_columns(board_id, api_key)
    return {col["title"].strip().lower(): col["id"] for col in board_columns["data"]["boards"][0]["columns"]}
