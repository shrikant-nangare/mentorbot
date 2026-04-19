import os

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma

import config
from openai_compat_embeddings import OpenAICompatEmbeddings


def _embedding_headers() -> dict[str, str]:
    h: dict[str, str] = {}
    ref = str(getattr(config, "HTTP_REFERER_OPTIONAL", "") or "").strip()
    title = str(getattr(config, "HTTP_TITLE_OPTIONAL", "") or "").strip()
    if ref:
        h["HTTP-Referer"] = ref
    if title:
        h["X-Title"] = title
    return h


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

    base_url = (getattr(config, "EMBEDDINGS_BASE_URL", "") or getattr(config, "LLM_BASE_URL", "")).rstrip("/")
    api_key = str(getattr(config, "EMBEDDINGS_API_KEY", "") or "").strip()

    vectordb = Chroma(
        persist_directory=config.DB_DIR,
        embedding_function=OpenAICompatEmbeddings(
            base_url=base_url,
            api_key=api_key,
            model=str(getattr(config, "EMBEDDINGS_MODEL", "text-embedding-3-small") or "text-embedding-3-small"),
            timeout_s=float(getattr(config, "LLM_TIMEOUT_S", 120.0)),
            extra_headers=_embedding_headers(),
        ),
    )

    vectordb.add_documents(split_docs)

    print("🎉 PDFs ingested successfully into vector DB!")


if __name__ == "__main__":
    ingest_pdfs()
