import pandas as pd


df = pd.read_csv("emodis_ndvi_v6_67f83d3a4cadc768.csv", encoding='latin1', index_col=False)
print(df.head())


df['Begin Date'] = pd.to_datetime(df['Begin Date'], utc=True)


df['Week Start'] = df['Begin Date'].dt.to_period('W').apply(lambda r: r.start_time)


idx = df.groupby('Week Start')['Begin Date'].idxmin()
df_weekly = df.loc[idx].sort_values('Begin Date')


df_weekly.to_csv('weekly_metadata_filtered.csv', index=False)

print("Saved correctly with proper Entity ID as 'weekly_metadata_filtered.csv'") 