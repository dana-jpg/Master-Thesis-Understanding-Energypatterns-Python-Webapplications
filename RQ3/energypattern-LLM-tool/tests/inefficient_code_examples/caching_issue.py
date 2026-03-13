
import time
import random

def get_user_data(user_id):
    """
    Simulates fetching user data from a database.
    This function is slow and called repeatedly with the same IDs.
    """
    time.sleep(0.5)
    
    print(f"SELECT * FROM users WHERE id = {user_id}")
    
    return {
        "id": user_id,
        "name": f"User_{user_id}",
        "score": random.randint(0, 100)
    }

def process_batch(user_ids):
    results = []
    for uid in user_ids:
        data = get_user_data(uid)
        results.append(data)
    return results

def main():
    ids = [1, 2, 1, 3, 2, 4, 1, 5]
    print("Processing batch...")
    process_batch(ids)

if __name__ == "__main__":
    main()
