import os

TASKS_FILE = "tasks.txt"

def load_tasks():
    """Load tasks from a text file."""
    tasks = {}
    if os.path.exists(TASKS_FILE):
        with open(TASKS_FILE, "r") as file:
            for line in file:
                parts = line.strip().split(" | ")
                if len(parts) == 3:
                    task_id, task_description, status = parts
                    tasks[task_id] = {"task": task_description, "completed": status == "Completed"}
    return tasks

def save_tasks(tasks):
    """Save tasks to a text file."""
    with open(TASKS_FILE, "w") as file:
        for task_id, task_info in tasks.items():
            status = "Completed" if task_info["completed"] else "Pending"
            file.write(f"{task_id} | {task_info['task']} | {status}\n")

def get_next_task_id(tasks):
    """Generate the next task ID based on existing ones."""
    if not tasks:
        return "1"
    existing_ids = sorted(map(int, tasks.keys()))  
    return str(existing_ids[-1] + 1)  

def display_tasks(tasks):
    """Display all tasks in the to-do list."""
    if not tasks:
        print("\nNo tasks available.")
    else:
        print("\nTo-Do List:")
        for task_id, task_info in tasks.items():
            status = "Completed" if task_info["completed"] else "Pending"
            print(f"{task_id}. {task_info['task']} - {status}")

def add_task(tasks, task_description):
    """Add a new task to the list and save it."""
    task_id =  get_next_task_id(tasks) 
    tasks[task_id] = {"task": task_description, "completed": False}
    save_tasks(tasks)
    print(f"Task '{task_description}' added successfully!")

def mark_completed(tasks, task_id):
    """Mark a task as completed and save changes."""
    if task_id in tasks:
        tasks[task_id]["completed"] = True
        save_tasks(tasks)
        print(f"Task '{tasks[task_id]['task']}' marked as completed.")
    else:
        print("Task ID not found.")

def delete_task(tasks, task_id):
    """Delete a task from the list and save changes."""
    if task_id in tasks:
        print(f"Task '{tasks[task_id]['task']}' deleted.")
        del tasks[task_id]
        save_tasks(tasks)
    else:
        print("Task ID not found.")

def main():
    tasks = load_tasks()  # Load tasks from file

    while True:
        print("\n--- To-Do List App ---")
        print("1. View Tasks")
        print("2. Add Task")
        print("3. Mark Task as Completed")
        print("4. Delete Task")
        print("5. Exit")

        choice = input("Enter your choice: ")

        if choice == "1":
            display_tasks(tasks)
        elif choice == "2":
            task_description = input("Enter task description: ")
            add_task(tasks, task_description)
        elif choice == "3":
            task_id = input("Enter task ID to mark as completed: ")
            mark_completed(tasks, task_id)
        elif choice == "4":
            task_id = input("Enter task ID to delete: ")
            delete_task(tasks, task_id)
        elif choice == "5":
            print("Exiting the to-do list. Have a great day!")
            break
        else:
            print("Invalid choice. Please enter a number from 1 to 5.")

if __name__ == "__main__":
    main()
