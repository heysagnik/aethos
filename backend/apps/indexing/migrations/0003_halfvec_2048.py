from django.db import migrations


def to_halfvec(apps, schema_editor):
    """Embeddings moved from 768-d BGE to 2048-d Nemotron; old vectors are meaningless, so drop them.

    A `halfvec` column keeps the HNSW index possible (pgvector indexes `vector` only up to 2000 dims).
    """
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP INDEX IF EXISTS indexing_chunk_embedding_hnsw")
    schema_editor.execute("ALTER TABLE indexing_chunk DROP COLUMN IF EXISTS embedding")
    schema_editor.execute("ALTER TABLE indexing_chunk ADD COLUMN embedding halfvec(2048) NULL")
    schema_editor.execute(
        "CREATE INDEX IF NOT EXISTS indexing_chunk_embedding_hnsw "
        "ON indexing_chunk USING hnsw (embedding halfvec_cosine_ops)"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("indexing", "0002_chunk_embedding"),
    ]

    operations = [migrations.RunPython(to_halfvec, migrations.RunPython.noop)]
