import os

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

import config


def ingest_pdfs(folder_path="data"):
    docs = []

    # Load all PDFs
    for file in os.listdir(folder_path):
        if file.endswith(".pdf"):
            file_path = os.path.join(folder_path, file)
            print(f"📄 Loading: {file_path}")

            loader = PyPDFLoader(file_path)
            docs.extend(loader.load())

    if not docs:
        print("⚠️ No PDF files found in 'data/' folder")
        return

    print(f"✅ Loaded {len(docs)} pages")

    # Split documents into chunks
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50
    )

    split_docs = splitter.split_documents(docs)
    print(f"✂️ Split into {len(split_docs)} chunks")

    # Create vector DB
    embed_kwargs = {
        "model": config.OLLAMA_EMBED_MODEL,
        "base_url": config.OLLAMA_BASE_URL,
        "keep_alive": int(getattr(config, "OLLAMA_KEEP_ALIVE_S", 0) or 0),
    }
    # If you switch embeddings to an OpenAI-compatible endpoint, update ingest.py similarly
    # or run ingestion through the app path.
    num_ctx = int(getattr(config, "OLLAMA_NUM_CTX", 0) or 0)
    if num_ctx > 0:
        embed_kwargs["num_ctx"] = num_ctx
    vectordb = Chroma(
        persist_directory=config.DB_DIR,
        embedding_function=OllamaEmbeddings(**embed_kwargs)
    )

    vectordb.add_documents(split_docs)
    #vectordb.persist()

    print("🎉 PDFs ingested successfully into vector DB!")


if __name__ == "__main__":
    ingest_pdfs()
