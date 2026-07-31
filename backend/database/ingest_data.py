import os
import json
import pandas as pd
from dotenv import load_dotenv
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document

load_dotenv()

def ingest_movies():
    print("Starting movie ingestion...")
    
    # 1. Load both files
    movies_df = pd.read_csv("database/movies.csv")
    credits_df = pd.read_csv("database/credits.csv")
    
    # 2. Merge them together matching the 'title' column
    df = movies_df.merge(credits_df, on='title')
    
    # Let's take the top 500 to keep it fast
    df = df.head(500) 
    
    documents = []
    
    for index, row in df.iterrows():
        if pd.isna(row['overview']):
            continue
            
        # 3. Clean Genres
        try:
            genres_data = json.loads(row['genres'])
            clean_genres = ", ".join([g['name'] for g in genres_data])
        except:
            clean_genres = "Unknown"
            
        # 4. Clean Cast (Grab the first 4 actors)
        try:
            cast_data = json.loads(row['cast'])
            # The 'cast' list is ordered by importance, so we just take the first 4
            top_cast = ", ".join([actor['name'] for actor in cast_data[:4]])
        except:
            top_cast = "Unknown"
            
        # 5. Build the Ultimate Context String
        combined_text = f"Title: {row['title']}. Genres: {clean_genres}. Cast: {top_cast}. Plot: {row['overview']}"
        
        doc = Document(
            page_content=combined_text,
            metadata={
                "title": row["title"],
                "movie_id": int(row["id"]) if pd.notna(row.get("id")) else None,
            },
        )
        documents.append(doc)
    
    print(f"Loaded {len(documents)} movies with Cast data.")
    
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    
    print("Vectorizing text and saving to database...")
    db = Chroma.from_documents(documents, embeddings, persist_directory="database/chroma_db")
    print("Ingestion complete! Brain populated.")

if __name__ == "__main__":
    ingest_movies()