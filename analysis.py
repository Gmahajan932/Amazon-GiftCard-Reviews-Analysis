import pandas as pd

df = pd.read_csv("data.csv")
print("Number of rows:", len(df))
print('Mean sale amount', df["amount"].mean())
print('Largest sale amount', df["amount"].max())