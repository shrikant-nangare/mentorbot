import json
from urllib.request import Request, urlopen


class OpenAICompatEmbeddings:
    """
    Minimal embeddings client compatible with langchain-chroma's embedding_function.
    Uses OpenAI-compatible POST /v1/embeddings (or /embeddings when base already ends with /v1).
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_s: float = 30.0,
        extra_headers: dict[str, str] | None = None,
    ):
        self._base_url = (base_url or "").rstrip("/")
        self._api_key = (api_key or "").strip()
        self._model = (model or "").strip()
        self._timeout_s = float(timeout_s)
        self._extra_headers = dict(extra_headers or {})

    def _url(self, v1_path: str) -> str:
        path = v1_path if v1_path.startswith("/") else f"/{v1_path}"
        if self._base_url.endswith("/v1") and path.startswith("/v1/"):
            path = path.removeprefix("/v1")
        return f"{self._base_url}{path}"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        headers.update(self._extra_headers)
        return headers

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not self._model:
            raise ValueError("Embeddings model is not set.")
        url = self._url("/v1/embeddings")
        payload = {"model": self._model, "input": texts}
        req = Request(url, data=json.dumps(payload).encode("utf-8"), headers=self._headers(), method="POST")
        with urlopen(req, timeout=self._timeout_s) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw or "{}")
        items = data.get("data") or []
        # Preserve order by index.
        items_sorted = sorted(items, key=lambda x: int(x.get("index", 0)))
        return [list(map(float, it.get("embedding") or [])) for it in items_sorted]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

