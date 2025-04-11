import pandas as pd

# Load yo   ur dataset
df = pd.read_csv("emodis_ndvi_v6_67f83d3a4cadc768.csv", encoding='latin1')
print(df.head())

df['Begin Date'] = pd.to_datetime(df['Begin Date'], utc=True)

# Create a new column: the week start date (e.g., Monday)
df['Week Start'] = df['Begin Date'].dt.to_period('W').apply(lambda r: r.start_time)

# Keep the first entry for each week
df_weekly = df.sort_values('Begin Date').groupby('Week Start').first().reset_index()

print(df_weekly.head())