from rag_engine.converters.structuring_json import create_structured_json
from rag_engine.converters.vector_build import build_vector_db
from rag_engine.vector_search import fast_search
import time

pdf_path = "test.pdf"

create_structured_json(pdf_path)

time.sleep(3)  # Just to ensure the file is written before we read it

build_vector_db("structured.json")

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
