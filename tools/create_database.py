import sqlite3
import os

# --- CONFIGURATION ---
DB_FILE = "/Users/venky/AI-QnA-App2/data/crmB.db"

# --- SCHEMA DEFINITION (SQL) ---
# This schema incorporates the suggestions mentioned above.
# Data types have been inferred (INTEGER, TEXT, REAL for float, etc.)
SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS Country (
    country_id INTEGER PRIMARY KEY AUTOINCREMENT,
    country_name TEXT NOT NULL UNIQUE,
    continent TEXT -- e.g., 'North America', 'Asia'
);

CREATE TABLE IF NOT EXISTS IndustrySegment (
    industry_segment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    industry_segment_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS AccountExecutive (
    account_executive_id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_executive_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS Account (
    account_id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_name TEXT NOT NULL,
    industry_segment_id INTEGER,
    account_executive_id INTEGER,
    country_id INTEGER,
    FOREIGN KEY (industry_segment_id) REFERENCES IndustrySegment(industry_segment_id),
    FOREIGN KEY (account_executive_id) REFERENCES AccountExecutive(account_executive_id),
    FOREIGN KEY (country_id) REFERENCES Country(country_id)
);

CREATE TABLE IF NOT EXISTS Consultant (
    consultant_id INTEGER PRIMARY KEY AUTOINCREMENT,
    consultant_name TEXT NOT NULL,
    consultant_type TEXT -- e.g., 'Technical', 'Strategic', 'Functional'
);

CREATE TABLE IF NOT EXISTS Product (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT NOT NULL,
    product_price REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS Opportunity (
    opportunity_id INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_name TEXT NOT NULL,
    account_id INTEGER,
    opportunity_stage TEXT NOT NULL,
    opportunity_type TEXT,
    creation_date TEXT,
    expected_close_date TEXT,
    actual_close_date TEXT,
    FOREIGN KEY (account_id) REFERENCES Account(account_id)
);

CREATE TABLE IF NOT EXISTS OpportunityProduct (
    opportunityproduct_id INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id INTEGER,
    product_id INTEGER,
    product_qty INTEGER NOT NULL,
    FOREIGN KEY (opportunity_id) REFERENCES Opportunity(opportunity_id),
    FOREIGN KEY (product_id) REFERENCES Product(product_id)
);

CREATE TABLE IF NOT EXISTS OpportunityTimeline (
    opportunitytimeline_id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_date TEXT NOT NULL,
    opportunity_id INTEGER,
    comment TEXT,
    sentiment_score REAL,
    FOREIGN KEY (opportunity_id) REFERENCES Opportunity(opportunity_id)
);

CREATE TABLE IF NOT EXISTS Engagement (
    engagement_id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_name TEXT NOT NULL,
    engagement_stage TEXT NOT NULL,
    engagement_type TEXT,
    start_date TEXT,
    expected_close_date TEXT,
    actual_close_date TEXT
);

CREATE TABLE IF NOT EXISTS EngagementConsultant (
    engagementconsultant_id INTEGER PRIMARY KEY AUTOINCREMENT,
    engagement_id INTEGER,
    consultant_id INTEGER,
    consultant_role TEXT,
    FOREIGN KEY (engagement_id) REFERENCES Engagement(engagement_id),
    FOREIGN KEY (consultant_id) REFERENCES Consultant(consultant_id)
);

CREATE TABLE IF NOT EXISTS EngagementOpportunity (
    engagement_id INTEGER,
    opportunity_id INTEGER,
    PRIMARY KEY (engagement_id, opportunity_id),
    FOREIGN KEY (engagement_id) REFERENCES Engagement(engagement_id),
    FOREIGN KEY (opportunity_id) REFERENCES Opportunity(opportunity_id)
);

CREATE TABLE IF NOT EXISTS Document (
    document_id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_name TEXT NOT NULL,
    document_type TEXT,
    storage_path TEXT NOT NULL,
    extracted_text TEXT,
    associated_record_id INTEGER NOT NULL,
    associated_table TEXT NOT NULL -- e.g., 'Account', 'Engagement', 'Opportunity'
);

"""

def create_database():
    """Creates an empty SQLite database file with the defined schema."""
    # Remove the old database file if it exists to start fresh
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
        print(f"Removed old database file: {DB_FILE}")

    conn = None
    try:
        # This command creates the file if it doesn't exist
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        print(f"Database file '{DB_FILE}' created. Now creating tables...")
        
        # Execute all CREATE TABLE statements
        cursor.executescript(SCHEMA_SQL)
        
        # Commit the changes to the database
        conn.commit()
        print("✅ All tables created successfully.")
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        
    finally:
        # Ensure the connection is closed
        if conn:
            conn.close()
            print("Database connection closed.")

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    create_database()