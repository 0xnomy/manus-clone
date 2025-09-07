import pandas as pd

class DataCleaningAgent:
    def __init__(self, scraped_data: List[Dict]):
        self.scraped_data = scraped_data

    def clean_data(self) -> pd.DataFrame:
        df = pd.DataFrame(self.scraped_data)
        df['name'] = df['name'].str.strip()
        df['headline'] = df['headline'].str.strip()
        df['location'] = df['location'].str.strip()
        return df
