
import sqlite3
conn = sqlite3.connect('esg_radar.db')
cursor = conn.cursor()

cursor.execute('SELECT COUNT(*) FROM parsed_articles')
total = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM parsed_articles WHERE impact_level = \"high\"')
high = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM parsed_articles WHERE impact_level = \"medium\"')
medium = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM parsed_articles WHERE impact_level = \"low\"')
low = cursor.fetchone()[0]

print(f'Total parsed  : {total}')
print(f'High impact   : {high}')
print(f'Medium impact : {medium}')
print(f'Low impact    : {low}')
conn.close()
import sqlite3
from config import DATABASE

conn = sqlite3.connect(DATABASE)
cursor = conn.cursor()

cursor.execute("""
SELECT DISTINCT jurisdiction
FROM parsed_articles
ORDER BY jurisdiction
""")

for row in cursor.fetchall():
    print(row[0])

conn.close()