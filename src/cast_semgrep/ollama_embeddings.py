"""Local Ollama embeddings, with model digest provenance and resumable storage."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .embedding_job import EmbeddingError, run_job
from .semantic_api import SemanticEmbeddingInput, SemanticModelInput

DEFAULT_URL = 'http://127.0.0.1:11434'
DEFAULT_MODEL = 'bge-m3:567m-fp16'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class OllamaClient:
    def __init__(self, base_url=DEFAULT_URL):
        try:
            url = urlsplit(base_url)
            local = url.hostname == 'localhost' or ipaddress.ip_address(url.hostname).is_loopback
            if not local or url.scheme not in ('http', 'https') or url.username or url.password or url.query or url.fragment or url.path not in ('', '/'):
                raise ValueError()
            _ = url.port
        except (ValueError, TypeError):
            raise EmbeddingError('L’URL Ollama doit désigner un serveur local (localhost ou adresse de boucle locale).') from None
        self.base_url = base_url.rstrip('/')
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def request(self, path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        for attempt in range(3):
            request = Request(self.base_url + path, data=data, headers={'Content-Type': 'application/json'})
            try:
                with self.opener.open(request, timeout=180) as response:
                    result = json.load(response)
                if not isinstance(result, dict) or 'error' in result:
                    raise EmbeddingError('Ollama a renvoyé une erreur ; le lot n’a pas été enregistré.')
                return result
            except HTTPError as error:
                status = error.code
                error.close()
                if (status == 429 or 500 <= status < 600) and attempt < 2:
                    time.sleep(2 ** (attempt + 1))
                    continue
                raise EmbeddingError(f'Ollama HTTP {status}. Vérifiez le modèle et sa fenêtre de contexte ; aucune troncature automatique.') from None
            except (URLError, TimeoutError, OSError):
                if attempt < 2:
                    time.sleep(2 ** (attempt + 1))
                    continue
                raise EmbeddingError('Serveur Ollama local inaccessible. Vérifiez OLLAMA_BASE_URL et le port ; relancez pour reprendre.') from None
            except (ValueError, UnicodeError):
                raise EmbeddingError('Réponse Ollama illisible ; lot non enregistré.') from None

    def models(self):
        result = self.request('/api/tags').get('models')
        if not isinstance(result, list) or any(not isinstance(m, dict) or not isinstance(m.get('name'), str) for m in result):
            raise EmbeddingError('Catalogue Ollama invalide.')
        return result

    def digest(self, model):
        entry = next((m for m in self.models() if m['name'] == model), None)
        if entry is None:
            raise EmbeddingError('Modèle absent du serveur Ollama. Consultez comparator ollama-models ; aucun téléchargement automatique.')
        digest = entry.get('digest', '')
        if not isinstance(digest, str) or not re.fullmatch(r'(?:sha256:)?[0-9a-f]{64}', digest):
            raise EmbeddingError('Empreinte du modèle Ollama absente ou invalide.')
        return digest.removeprefix('sha256:')

    def describe(self, model):
        digest = self.digest(model)
        info = self.request('/api/show', {'model': model})
        if 'embedding' not in info.get('capabilities', []):
            raise EmbeddingError('Ce modèle Ollama ne déclare pas la capacité embedding.')
        metadata = info.get('model_info', {})
        dimensions = metadata.get(str(metadata.get('general.architecture', '')) + '.embedding_length')
        if type(dimensions) is not int or not 1 <= dimensions <= 16384:
            raise EmbeddingError('Dimension d’embedding absente ou invalide dans les métadonnées Ollama.')
        self.assert_digest(model, digest)
        return digest, dimensions

    def assert_digest(self, model, expected):
        if self.digest(model) != expected:
            raise EmbeddingError('Le modèle Ollama a changé pendant le calcul. Relancez pour enregistrer une nouvelle révision.')

    def embed(self, model, texts, digest, dimensions):
        self.assert_digest(model, digest)
        result = self.request('/api/embed', {'model': model, 'input': texts, 'truncate': False, 'keep_alive': '5m'})
        self.assert_digest(model, digest)
        try:
            if result['model'] != model or not isinstance(result['embeddings'], list) or len(result['embeddings']) != len(texts):
                raise ValueError()
            vectors = []
            for raw in result['embeddings']:
                vector = SemanticEmbeddingInput.valid_vector(raw)
                if vector is None or len(vector) != dimensions:
                    raise ValueError()
                vectors.append(vector)
            tokens = result.get('prompt_eval_count', 0)
            if type(tokens) is not int or tokens < 0:
                raise ValueError()
        except (KeyError, TypeError, ValueError, OverflowError):
            raise EmbeddingError('Vecteurs Ollama invalides (modèle, nombre, dimension ou valeurs) ; lot non enregistré.') from None
        return vectors, tokens


def run_embeddings(settings, *, base_url=None, model=DEFAULT_MODEL, batch_size=32,
                   limit=None, dry_run=False, progress=None, client=None):
    if not 1 <= batch_size <= 128 or (limit is not None and limit < 1):
        raise EmbeddingError('Taille de lot ou limite invalide.')
    client = client or OllamaClient(base_url or settings.ollama_base_url)
    digest, dimensions = client.describe(model)
    # Keep registry keys bounded even for long namespaced model names.
    model_id = hashlib.sha256(model.encode()).hexdigest()[:16]
    config = SemanticModelInput(model_key=f'ollama/{model_id}/{digest}/{dimensions}', provider='ollama',
                                model_name=model, model_revision='sha256:' + digest,
                                dimensions=dimensions).model_dump()
    return run_job(settings, config, batch_size=batch_size, limit=limit, dry_run=dry_run, progress=progress,
                   send=lambda texts: client.embed(model, texts, digest, dimensions))


if __name__ == '__main__':
    import sys
    from .cli import main
    sys.argv.insert(1, 'embed-ollama')
    main()
