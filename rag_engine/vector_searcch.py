import json
from chromadb import PersistentClient
from sentence_transformers import SentenceTransformer
import time

from converters.vector_build import MODEL_NAME, COLLECTION_NAME, DB_PATH


print("--- Loading Resources into RAM ---")
start_load = time.time()

# Load model once globally
model = SentenceTransformer(MODEL_NAME)

# Load Chroma once globally (PersistentClient caches the index in RAM while running)
client = PersistentClient(path=DB_PATH)
collection = client.get_collection(COLLECTION_NAME)

print(f"--- Ready! (Loaded in {time.time() - start_load:.2f}s) ---")

def fast_search(query, top_k=3):
    """Search function using the globally loaded model and collection."""
    start_time = time.time()
    
    # 1. Encode query
    query_embedding = model.encode(query).tolist()
    
    # 2. Query vector DB
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k
    )
    
    end_time = time.time()
    return results, (end_time - start_time)


# ----------------------------
# Continuous Test Loop
# ----------------------------
if __name__ == "__main__":
    print("\n[Vektor RAG Speed Tester]")
    print("Type 'exit' or 'quit' to stop.")
    
    while True:
        user_query = input("\nEnter Search Query: ").strip()
        
        if user_query.lower() in ['exit', 'quit']:
            print("Shutting down...")
            break
            
        if not user_query:
            continue

        # Perform Search
        results, duration = fast_search(user_query)

        print(f"Found {len(results['documents'][0])} results in {duration:.4f} seconds.")
        print("-" * 30)

        # Print results with metadata
        for i in range(len(results['documents'][0])):
            doc = results['documents'][0][i]
            meta = results['metadatas'][0][i]
            dist = results['distances'][0][i]
            
            print(f"RANK {i+1} | Score: {dist:.4f} | Section: {meta['heading']}")
            print(f"Content: {doc[:400]}...") # Showing first 200 chars
            print("-" * 10)
