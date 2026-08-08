import sqlite3
conn = sqlite3.connect("data/luminalix.db")
c = conn.cursor()
c.execute("SELECT disease, COUNT(*) FROM regional_survey_data GROUP BY disease")
for row in c.fetchall():
    print(row)
c.execute("SELECT COUNT(*) FROM regional_survey_data")
print("Total:", c.fetchone()[0])
