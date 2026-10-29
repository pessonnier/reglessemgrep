"""Resumable OpenAI embeddings job; run via comparator embed-openai or python -m."""
from __future__ import annotations

import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .embedding_job import EmbeddingError, run_job
from .semantic_api import SemanticEmbeddingInput, SemanticModelInput

DEFAULT_MODEL = 'text-embedding-3-small'
MODEL_DIMENSIONS = {DEFAULT_MODEL: 1536, 'text-embedding-3-large': 3072}
# A UTF-8 byte bound is conservative for byte-level tokenization: no truncation.
MAX_INPUT_BYTES = 8191


def request_embeddings(api_key, texts, model, dimensions):
    body = json.dumps({'model': model, 'input': texts, 'dimensions': dimensions,
                       'encoding_format': 'float'}).encode()
    for attempt in range(4):
        request = Request('https://api.openai.com/v1/embeddings', data=body,
                          headers={'Authorization': 'Bearer ' + api_key, 'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=60) as response:
                return json.load(response)
        except HTTPError as error:
            status = error.code
            error.close()
            if (status == 429 or 500 <= status < 600) and attempt < 3:
                time.sleep(2 ** (attempt + 1))
                continue
            guidance = 'Vérifiez OPENAI_API_KEY.' if status == 401 else 'Vérifiez les droits et le quota du compte OpenAI.'
            raise EmbeddingError(f'OpenAI HTTP {status}. {guidance} Relancez pour reprendre les lots enregistrés.') from None
        except (URLError, TimeoutError, OSError):
            if attempt < 3:
                time.sleep(2 ** (attempt + 1))
                continue
            raise EmbeddingError('Connexion OpenAI impossible. Les lots enregistrés sont conservés.') from None
        except (ValueError, UnicodeError):
            raise EmbeddingError('Réponse OpenAI illisible ; aucun vecteur de ce lot enregistré.') from None


def validate_response(response, count, model, dimensions):
    """Use explicit response indices, never assume response list order."""
    try:
        if response['model'] != model or len(response['data']) != count:
            raise ValueError()
        vectors = {}
        for item in response['data']:
            index = item['index']
            if type(index) is not int or not 0 <= index < count or index in vectors:
                raise ValueError()
            vector = SemanticEmbeddingInput.valid_vector(item['embedding'])
            if vector is None or len(vector) != dimensions:
                raise ValueError()
            vectors[index] = vector
        tokens = response['usage']['total_tokens']
        if type(tokens) is not int or tokens < 0:
            raise ValueError()
        return [vectors[i] for i in range(count)], tokens
    except (KeyError, TypeError, ValueError, OverflowError):
        raise EmbeddingError('Réponse OpenAI invalide (modèle, indices ou dimensions) ; lot non enregistré.') from None


def run_embeddings(settings, *, model=DEFAULT_MODEL, dimensions=None, revision='alias-v1',
                   batch_size=64, limit=None, dry_run=False, send=request_embeddings, progress=None):
    if model not in MODEL_DIMENSIONS:
        raise EmbeddingError('Modèle pris en charge : text-embedding-3-small ou text-embedding-3-large.')
    dimensions = MODEL_DIMENSIONS[model] if dimensions is None else dimensions
    if not 1 <= dimensions <= MODEL_DIMENSIONS[model] or not 1 <= batch_size <= 128 or (limit is not None and limit < 1):
        raise EmbeddingError('Dimensions, taille de lot ou limite invalides.')
    try:
        config = SemanticModelInput(model_key=f'openai/{model}/{revision}/{dimensions}', provider='openai',
                                    model_name=model, model_revision=revision, dimensions=dimensions).model_dump()
    except ValueError:
        raise EmbeddingError('Révision invalide ; utilisez lettres, chiffres, tirets et points.') from None
    def prepare():
        if not settings.openai_api_key:
            raise EmbeddingError('OPENAI_API_KEY absente. Renseignez-la dans .env ou dans l’environnement, puis relancez.')

    def generate(texts):
        response = send(settings.openai_api_key, texts, model, dimensions)
        return validate_response(response, len(texts), model, dimensions)

    return run_job(settings, config, send=generate, batch_size=batch_size, limit=limit, dry_run=dry_run,
                   max_input_bytes=MAX_INPUT_BYTES, prepare=prepare, progress=progress)


if __name__ == '__main__':
    import sys
    from .cli import main
    sys.argv.insert(1, 'embed-openai')
    main()
