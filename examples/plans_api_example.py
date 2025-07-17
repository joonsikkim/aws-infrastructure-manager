import requests
import json
import uuid

BASE_URL = "http://127.0.0.1:8000"
PROJECT_ID = "test-project-123"
USER_ID = "example-user"

def create_project():
    print("--- Creating Project ---")
    project_data = {
        "name": "My Test Project",
        "description": "A project for demonstrating the plans API.",
        "settings": {
            "s3_bucket_path": f"s3://my-test-bucket/projects/{PROJECT_ID}",
            "default_region": "us-east-1"
        }
    }
    response = requests.post(f"{BASE_URL}/projects/", json=project_data, headers={"x-user-id": USER_ID})
    if response.status_code == 201:
        print("Project created successfully.")
        return response.json()["id"]
    else:
        print(f"Error creating project: {response.text}")
        # Check if project already exists
        response = requests.get(f"{BASE_URL}/projects/", headers={"x-user-id": USER_ID})
        projects = response.json()
        for p in projects:
            if p["name"] == project_data["name"]:
                print("Project already exists.")
                return p["id"]
        return None

def create_change_plan(project_id):
    print("\n--- Creating Change Plan ---")
    plan_data = {
        "resources": [
            {
                "id": str(uuid.uuid4()),
                "type": "EC2::Instance",
                "name": "my-web-server",
                "region": "us-east-1",
                "properties": {
                    "InstanceType": "t2.micro",
                    "ImageId": "ami-0c55b159cbfafe1f0"
                },
                "tags": {"Name": "my-web-server"}
            }
        ],
        "change_description": "Initial deployment of web server."
    }
    response = requests.post(f"{BASE_URL}/projects/{project_id}/plans/", json=plan_data, headers={"x-user-id": USER_ID})
    if response.status_code == 201:
        print("Change plan created successfully.")
        return response.json()
    else:
        print(f"Error creating change plan: {response.text}")
        return None

def list_change_plans(project_id):
    print("\n--- Listing Change Plans ---")
    response = requests.get(f"{BASE_URL}/projects/{project_id}/plans/", headers={"x-user-id": USER_ID})
    if response.status_code == 200:
        plans = response.json()
        print(f"Found {len(plans)} change plan(s).")
        for plan in plans:
            print(f"  - Plan ID: {plan['id']}, Status: {plan['status']}, Changes: {plan['summary']['total_changes']}")
        return plans
    else:
        print(f"Error listing change plans: {response.text}")
        return []

def get_change_plan(project_id, plan_id):
    print(f"\n--- Getting Change Plan {plan_id} ---")
    response = requests.get(f"{BASE_URL}/projects/{project_id}/plans/{plan_id}", headers={"x-user-id": USER_ID})
    if response.status_code == 200:
        plan = response.json()
        print("Plan details:")
        print(json.dumps(plan, indent=2))
        return plan
    else:
        print(f"Error getting change plan: {response.text}")
        return None

def approve_change_plan(project_id, plan_id):
    print(f"\n--- Approving Change Plan {plan_id} ---")
    approval_data = {"action": "approve"}
    response = requests.post(f"{BASE_URL}/projects/{project_id}/plans/{plan_id}/approval", json=approval_data, headers={"x-user-id": "approver-user"})
    if response.status_code == 200:
        print("Plan approved successfully.")
        return response.json()
    else:
        print(f"Error approving plan: {response.text}")
        return None

def get_plan_status(project_id, plan_id):
    print(f"\n--- Getting Status for Plan {plan_id} ---")
    response = requests.get(f"{BASE_URL}/projects/{project_id}/plans/{plan_id}/status", headers={"x-user-id": USER_ID})
    if response.status_code == 200:
        status = response.json()
        print(f"Plan status: {status['status']}")
        return status
    else:
        print(f"Error getting plan status: {response.text}")
        return None

if __name__ == "__main__":
    # Ensure the project exists
    project_id = create_project()

    if project_id:
        # Create a new change plan
        plan = create_change_plan(project_id)

        if plan:
            plan_id = plan["id"]

            # List all change plans
            list_change_plans(project_id)

            # Get the details of the new plan
            get_change_plan(project_id, plan_id)

            # Get the status of the plan
            get_plan_status(project_id, plan_id)

            # Approve the plan
            approved_plan = approve_change_plan(project_id, plan_id)

            if approved_plan:
                # Get the status again to see the change
                get_plan_status(project_id, plan_id)
