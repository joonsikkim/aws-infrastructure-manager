import requests
import json

BASE_URL = "http://127.0.0.1:8000"
PROJECT_ID = "test-project-123"  # Use the same project ID as in plans_api_example.py
USER_ID = "example-user"

def get_dashboard(project_id):
    print(f"--- Getting Dashboard for Project {project_id} ---")
    response = requests.get(f"{BASE_URL}/projects/{project_id}/dashboard", headers={"x-user-id": USER_ID})
    if response.status_code == 200:
        dashboard_data = response.json()
        print("Dashboard data:")
        print(json.dumps(dashboard_data, indent=2))
    else:
        print(f"Error getting dashboard: {response.text}")

def get_history(project_id):
    print(f"\n--- Getting History for Project {project_id} ---")
    response = requests.get(f"{BASE_URL}/projects/{project_id}/history?limit=5", headers={"x-user-id": USER_ID})
    if response.status_code == 200:
        history_data = response.json()
        print(f"Found {len(history_data)} history records:")
        for record in history_data:
            print(f"  - Version: {record['version']}, Timestamp: {record['timestamp']}, Description: {record['change_description']}")
    else:
        print(f"Error getting history: {response.text}")

if __name__ == "__main__":
    # First, ensure the project and some data exist by running the plans_api_example.py
    print("Please ensure you have run 'plans_api_example.py' first to create a project and data.")
    
    get_dashboard(PROJECT_ID)
    get_history(PROJECT_ID)
