import pandas as pd

# Load your Landsat metadata CSV file
df = pd.read_csv("landsat_ot_c2_l2_6801609f32a9692f.csv", encoding='latin1')

# Convert 'Date Acquired' to datetime
df['Date Acquired'] = pd.to_datetime(df['Date Acquired'])

# Add year-week identifier
df['YearWeek'] = df['Date Acquired'].dt.strftime('%Y-%U')

# Drop duplicates per week (keeping the first row of each week)
weekly_df = df.drop_duplicates(subset='YearWeek', keep='first')

# Optionally drop the helper column
weekly_df = weekly_df.drop(columns=['YearWeek'])

# Save to new CSV
weekly_df.to_csv("landsat_weekly_sample.csv", index=False)

print("Weekly sample created with", len(weekly_df), "rows.")
