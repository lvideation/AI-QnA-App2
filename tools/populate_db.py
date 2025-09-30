import sqlite3
import pandas as pd
from faker import Faker
import random
from datetime import datetime, timedelta
import numpy as np
import os

# --- CONFIGURATION ---
DB_FILE = "../data/crmB.db"
DOCS_DIR = "../documents" # Path to the folder where .txt files will be created

# Number of records to generate for each table
NUM_COUNTRIES = 20
NUM_INDUSTRY_SEGMENTS = 10
NUM_EXECUTIVES = 15
NUM_CONSULTANTS = 30
NUM_PRODUCTS = 25
NUM_ACCOUNTS = 100
NUM_OPPORTUNITIES = 250
NUM_ENGAGEMENTS = 80
# Average number of timeline notes per opportunity
NOTES_PER_OPPORTUNITY = 5

# Initialize Faker for data generation
fake = Faker()

# --- HELPER FUNCTIONS ---

def get_db_connection():
    """Establishes a database connection."""
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def get_existing_ids(cursor, table_name, id_column):
    """Fetches all primary key IDs from a given table."""
    cursor.execute(f"SELECT {id_column} FROM {table_name}")
    return [row[0] for row in cursor.fetchall()]

def clear_all_data(conn):
    """Deletes all data from all tables in the correct order."""
    cursor = conn.cursor()
    tables = [
        'Document', 'EngagementOpportunity', 'EngagementConsultant', 'OpportunityTimeline', 
        'OpportunityProduct', 'Engagement', 'Opportunity', 'Product', 'Consultant', 'Account', 
        'AccountExecutive', 'IndustrySegment', 'Country'
    ]
    print("Clearing all existing data from the database...")
    for table in tables:
        try:
            cursor.execute(f"DELETE FROM {table};")
            print(f"  - Cleared {table}")
        except sqlite3.OperationalError:
            print(f"  - Table {table} not found, skipping.")
    conn.commit()
    print("✅ All tables cleared.")


# --- DATA GENERATION FUNCTIONS ---

def generate_countries(num_records):
    """Generates country and continent data with weighting."""
    data = []
    continents = ['North America', 'Europe', 'Asia', 'South America', 'Africa', 'Oceania']
    weights = [0.35, 0.30, 0.20, 0.05, 0.05, 0.05]
    for _ in range(num_records):
        data.append({
            'country_name': fake.unique.country(),
            'continent': random.choices(continents, weights=weights, k=1)[0]
        })
    return data

def generate_simple_table(num_records, generator_func, column_name):
    """Generic generator for simple lookup tables."""
    return [{column_name: generator_func()} for _ in range(num_records)]

def generate_consultants(num_records):
    """Generates consultant data with weighted types."""
    data = []
    types = ['Technical', 'Strategic', 'Functional', 'Advisory']
    weights = [0.4, 0.3, 0.2, 0.1]
    for _ in range(num_records):
        data.append({
            'consultant_name': fake.name(),
            'consultant_type': random.choices(types, weights=weights, k=1)[0]
        })
    return data

def generate_products(num_records):
    """Generates product data with prices following a log-normal distribution."""
    data = []
    for _ in range(num_records):
        price = np.random.lognormal(mean=9.5, sigma=0.8)
        data.append({
            'product_name': ' '.join(fake.words(nb=2)).title() + ' Platform',
            'product_price': max(500, round(price, 2))
        })
    return data

def generate_accounts(num_records, country_ids, industry_ids, executive_ids):
    """Generates account data, linking to parent tables."""
    data = []
    for _ in range(num_records):
        data.append({
            'account_name': fake.company(),
            'country_id': random.choice(country_ids),
            'industry_segment_id': random.choice(industry_ids),
            'account_executive_id': random.choice(executive_ids)
        })
    return data

def generate_opportunities(num_records, account_ids):
    """Generates opportunity data with stages, types, and realistic dates."""
    data = []
    stages = ['Prospecting', 'Qualification', 'Proposal', 'Negotiation', 'Closed Won', 'Closed Lost']
    types = ['New Business', 'Upsell', 'Renewal']
    for _ in range(num_records):
        stage = random.choices(stages, weights=[0.1, 0.1, 0.2, 0.1, 0.4, 0.1], k=1)[0]
        opp_type = random.choices(types, weights=[0.6, 0.3, 0.1], k=1)[0]

        creation_date = fake.date_time_between(start_date='-2y', end_date='now')
        expected_close_date = creation_date + timedelta(days=random.randint(30, 180))
        actual_close_date = None
        if 'Closed' in stage:
            actual_close_date = expected_close_date + timedelta(days=random.randint(-20, 20))

        data.append({
            'opportunity_name': f"{opp_type} for {fake.word().title()}",
            'account_id': random.choice(account_ids),
            'opportunity_stage': stage,
            'opportunity_type': opp_type,
            'creation_date': creation_date.strftime("%Y-%m-%d"),
            'expected_close_date': expected_close_date.strftime("%Y-%m-%d"),
            'actual_close_date': actual_close_date.strftime("%Y-%m-%d") if actual_close_date else None
        })
    return data

def generate_engagements(num_records):
    """Generates engagement data with types, stages, and dates."""
    data = []
    stages = ['Discovery', 'In Progress', 'On Hold', 'Completed', 'Cancelled']
    types = ['Proof of Concept', 'Implementation', 'Advisory', 'Training']
    for _ in range(num_records):
        start_date = fake.date_time_between(start_date='-1y', end_date='now')
        expected_close_date = start_date + timedelta(days=random.randint(14, 90))
        stage = random.choices(stages, weights=[0.1, 0.4, 0.1, 0.35, 0.05], k=1)[0]
        actual_close_date = None
        if stage in ['Completed', 'Cancelled']:
            actual_close_date = expected_close_date + timedelta(days=random.randint(-10, 10))

        data.append({
            'engagement_name': fake.bs().title(),
            'engagement_stage': stage,
            'engagement_type': random.choices(types, weights=[0.3, 0.4, 0.2, 0.1], k=1)[0],
            'start_date': start_date.strftime("%Y-%m-%d"),
            'expected_close_date': expected_close_date.strftime("%Y-%m-%d"),
            'actual_close_date': actual_close_date.strftime("%Y-%m-%d") if actual_close_date else None
        })
    return data

def generate_opportunity_timeline(num_records, opportunity_ids_with_dates):
    """Generates fake notes for opportunities for sentiment analysis."""
    data = []
    positive_phrases = ["client is very enthusiastic", "successful demo", "strong positive feedback", "budget is approved", "moving forward", "great rapport with the team"]
    negative_phrases = ["concerns about pricing", "decision-maker is unresponsive", "competitor is involved", "technical issues", "scope creep is a problem", "timeline is at risk"]
    neutral_phrases = ["sent follow-up email", "scheduled next meeting", "internal review meeting", "provided documentation", "clarified requirements"]
    
    if not opportunity_ids_with_dates: return []

    for opp_id, creation_date_str in random.choices(list(opportunity_ids_with_dates.items()), k=num_records):
        creation_date = datetime.strptime(creation_date_str, "%Y-%m-%d")
        log_date = fake.date_time_between(start_date=creation_date, end_date=datetime.now())
        
        sentiment_choice = random.choices(['positive', 'negative', 'neutral'], weights=[0.4, 0.2, 0.4], k=1)[0]
        if sentiment_choice == 'positive':
            comment = random.choice(positive_phrases).capitalize() + ". " + fake.sentence(nb_words=5)
        elif sentiment_choice == 'negative':
            comment = random.choice(negative_phrases).capitalize() + ". " + fake.sentence(nb_words=5)
        else:
            comment = random.choice(neutral_phrases).capitalize() + "."
            
        data.append({
            'log_date': log_date.strftime("%Y-%m-%d"),
            'opportunity_id': opp_id,
            'comment': comment,
            'sentiment_score': None
        })
    return data

# --- NEW: Function to generate .txt files and their DB records ---
def generate_and_link_documents(conn, id_map):
    """Creates empty .txt files based on business rules and links them in the DB."""
    print("\nGenerating and linking document files...")
    os.makedirs(DOCS_DIR, exist_ok=True) # Create documents folder if it doesn't exist
    
    cursor = conn.cursor()
    document_records = []

    # Rule 1: Create an Account Plan for every Account
    for acc_id in id_map.get('Account', []):
        filename = f"APlan_{acc_id}.txt"
        filepath = os.path.join(DOCS_DIR, filename)
        with open(filepath, 'w') as f:
            f.write(f"Account Plan for Account ID: {acc_id}\n") # Add some placeholder content
        
        document_records.append({
            'document_name': filename,
            'document_type': 'Account Plan',
            'storage_path': filepath,
            'extracted_text': f"Account Plan for Account ID: {acc_id}\n",
            'associated_record_id': acc_id,
            'associated_table': 'Account'
        })
    
    # Rule 2: Create docs for specific Engagement types
    cursor.execute("SELECT engagement_id, engagement_type FROM Engagement")
    engagements = cursor.fetchall()

    for eng_id, eng_type in engagements:
        doc_type = None
        filename = None
        if eng_type == 'Advisory':
            doc_type = 'Business Case'
            filename = f"BusinessCase_{eng_id}.txt"
        elif eng_type == 'Implementation':
            doc_type = 'Solution Architecture'
            filename = f"SolArch_{eng_id}.txt"
        
        if filename:
            filepath = os.path.join(DOCS_DIR, filename)
            with open(filepath, 'w') as f:
                f.write(f"{doc_type} for Engagement ID: {eng_id}\n")
            
            document_records.append({
                'document_name': filename,
                'document_type': doc_type,
                'storage_path': filepath,
                'extracted_text': f"{doc_type} for Engagement ID: {eng_id}\n",
                'associated_record_id': eng_id,
                'associated_table': 'Engagement'
            })

    # Insert all collected document records into the database
    if document_records:
        pd.DataFrame(document_records).to_sql('Document', conn, if_exists='append', index=False)
        print(f"✅ Created {len(document_records)} physical document files and linked them in the database.")
    else:
        print("ℹ️ No documents were generated based on the rules.")


# --- MAIN EXECUTION ---
if __name__ == '__main__':
    conn = get_db_connection()
    clear_all_data(conn)
    cursor = conn.cursor()

    print("\n🚀 Starting synthetic CRM data population...")

    # --- Generate and Insert Lookup Tables ---
    tables_to_populate = {
        "Country": (generate_countries, NUM_COUNTRIES, 'country_id'),
        "IndustrySegment": (generate_simple_table, NUM_INDUSTRY_SEGMENTS, 'industry_segment_id', fake.bs, 'industry_segment_name'),
        "AccountExecutive": (generate_simple_table, NUM_EXECUTIVES, 'account_executive_id', fake.name, 'account_executive_name'),
        "Consultant": (generate_consultants, NUM_CONSULTANTS, 'consultant_id'),
        "Product": (generate_products, NUM_PRODUCTS, 'product_id'),
    }
    id_map = {}
    for name, params in tables_to_populate.items():
        print(f"Generating {name}...")
        data = params[0](params[1], *(params[3:]))
        pd.DataFrame(data).to_sql(name, conn, if_exists='append', index=False)
        id_map[name] = get_existing_ids(cursor, name, params[2])
        print(f"✅ Inserted {len(id_map[name])} records into {name}.")

    # --- Generate and Insert Core Tables Sequentially ---
    print("\nGenerating Account...")
    account_data = generate_accounts(NUM_ACCOUNTS, id_map['Country'], id_map['IndustrySegment'], id_map['AccountExecutive'])
    pd.DataFrame(account_data).to_sql('Account', conn, if_exists='append', index=False)
    id_map['Account'] = get_existing_ids(cursor, 'Account', 'account_id')
    print(f"✅ Inserted {len(id_map['Account'])} records into Account.")

    print("Generating Opportunity...")
    opportunity_data = generate_opportunities(NUM_OPPORTUNITIES, id_map['Account'])
    pd.DataFrame(opportunity_data).to_sql('Opportunity', conn, if_exists='append', index=False)
    id_map['Opportunity'] = get_existing_ids(cursor, 'Opportunity', 'opportunity_id')
    print(f"✅ Inserted {len(id_map['Opportunity'])} records into Opportunity.")

    print("Generating Engagement...")
    engagement_data = generate_engagements(NUM_ENGAGEMENTS)
    pd.DataFrame(engagement_data).to_sql('Engagement', conn, if_exists='append', index=False)
    id_map['Engagement'] = get_existing_ids(cursor, 'Engagement', 'engagement_id')
    print(f"✅ Inserted {len(id_map['Engagement'])} records into Engagement.")
    
    # --- Generate Timeline Notes ---
    cursor.execute("SELECT opportunity_id, creation_date FROM Opportunity")
    opp_dates = dict(cursor.fetchall())
    print("\nGenerating Opportunity Timeline (Notes)...")
    timeline_data = generate_opportunity_timeline(NUM_OPPORTUNITIES * NOTES_PER_OPPORTUNITY, opp_dates)
    pd.DataFrame(timeline_data).to_sql('OpportunityTimeline', conn, if_exists='append', index=False)
    print(f"✅ Inserted {len(timeline_data)} timeline notes.")

    # --- Generate Physical Documents and Link them in DB ---
    generate_and_link_documents(conn, id_map) # This replaces the old document generation logic

    # --- Generate and Insert Junction Tables ---
    print("\nGenerating Opportunity-Product links...")
    num_opp_prod_links = int(NUM_OPPORTUNITIES * 1.5)
    opp_prod_data = []
    for _ in range(num_opp_prod_links):
        opp_prod_data.append({
            'opportunity_id': random.choice(id_map['Opportunity']),
            'product_id': random.choice(id_map['Product']),
            'product_qty': random.randint(1, 10)
        })
    pd.DataFrame(opp_prod_data).to_sql('OpportunityProduct', conn, if_exists='append', index=False)
    print(f"✅ Inserted {len(opp_prod_data)} OpportunityProduct links.")

    print("Generating Engagement-Consultant links...")
    num_eng_con_links = int(NUM_ENGAGEMENTS * 2)
    eng_con_data = []
    roles = ['Lead', 'Support', 'SME']
    for _ in range(num_eng_con_links):
        eng_con_data.append({
            'engagement_id': random.choice(id_map['Engagement']),
            'consultant_id': random.choice(id_map['Consultant']),
            'consultant_role': random.choice(roles)
        })
    pd.DataFrame(eng_con_data).to_sql('EngagementConsultant', conn, if_exists='append', index=False)
    print(f"✅ Inserted {len(eng_con_data)} EngagementConsultant links.")

    print("Generating Engagement-Opportunity links (enforcing one account per engagement)...")
    cursor.execute("SELECT opportunity_id, account_id FROM Opportunity")
    opp_to_account = dict(cursor.fetchall())
    engagement_account_map = {}
    eng_opp_links = set()
    num_eng_opp_links = int(NUM_ENGAGEMENTS * 1.2)
    
    all_opp_ids = id_map['Opportunity']
    all_eng_ids = id_map['Engagement']

    while len(eng_opp_links) < num_eng_opp_links and all_opp_ids:
        eng_id = random.choice(all_eng_ids)
        opp_id = random.choice(all_opp_ids)
        acc_id = opp_to_account.get(opp_id)

        if not acc_id: continue

        if eng_id not in engagement_account_map:
            engagement_account_map[eng_id] = acc_id
            eng_opp_links.add((eng_id, opp_id))
        elif engagement_account_map[eng_id] == acc_id:
            eng_opp_links.add((eng_id, opp_id))
    
    if eng_opp_links:
        eng_opp_data = [{'engagement_id': e, 'opportunity_id': o} for e,o in eng_opp_links]
        pd.DataFrame(eng_opp_data).to_sql('EngagementOpportunity', conn, if_exists='append', index=False)
        print(f"✅ Inserted {len(eng_opp_data)} valid EngagementOpportunity links.")
    else:
        print("ℹ️ No EngagementOpportunity links were generated.")

    # --- Cleanup and Close ---
    conn.commit()
    conn.close()
    print("\n🎉 Database population complete!")


