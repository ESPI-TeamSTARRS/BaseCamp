class DuplicateIdempotencyKeyError(Exception):
    """Une autre transaction a insere la meme cle d'idempotence entre la lecture et le commit."""
