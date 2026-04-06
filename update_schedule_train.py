# update_schedule_date.py
import mysql.connector
from datetime import datetime, timedelta

# add_schedule_date_column.py


db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'your_password',  # Change to your MySQL root password
    'database': 'railway_db'
}

conn = mysql.connector.connect(**db_config)
cursor = conn.cursor()

# Add the column if it doesn't exist
try:
    cursor.execute("ALTER TABLE trains ADD COLUMN schedule_date DATE")
    print("✅ Added column 'schedule_date'")
except mysql.connector.Error as err:
    if err.errno == 1060:  # Duplicate column
        print("Column 'schedule_date' already exists")
    else:
        print(f"Error: {err}")

# Set all existing rows to current date
cursor.execute("UPDATE trains SET schedule_date = CURDATE()")
conn.commit()
print(f"✅ Updated {cursor.rowcount} trains to schedule_date = {datetime.now().strftime('%Y-%m-%d')}")

cursor.close()
conn.close()

def update_all_train_dates(new_date):
    """
    new_date: string in 'YYYY-MM-DD' format, or a datetime.date object.
    Example: '2026-04-04' or datetime.date(2026, 4, 4)
    """
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    cursor.execute("UPDATE trains SET schedule_date = %s", (new_date,))
    conn.commit()
    affected = cursor.rowcount
    cursor.close()
    conn.close()
    print(f"✅ Updated {affected} trains to schedule date {new_date}")

if __name__ == "__main__":
    # Example: set all trains to tomorrow's date
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    update_all_train_dates(tomorrow)
    print(f"All trains now scheduled for {tomorrow}")