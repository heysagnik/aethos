import apps.indexing.fields
from django.db import migrations


def enable_pgvector(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("CREATE EXTENSION IF NOT EXISTS vector")


def create_hnsw_index(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            "CREATE INDEX IF NOT EXISTS indexing_chunk_embedding_hnsw "
            "ON indexing_chunk USING hnsw (embedding vector_cosine_ops)"
        )


def drop_hnsw_index(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("DROP INDEX IF EXISTS indexing_chunk_embedding_hnsw")


class Migration(migrations.Migration):
    dependencies = [
        ("indexing", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(enable_pgvector, migrations.RunPython.noop),
        migrations.AddField(
            model_name="chunk",
            name="embedding",
            field=apps.indexing.fields.EmbeddingField(blank=True, null=True),
        ),
        migrations.RunPython(create_hnsw_index, drop_hnsw_index),
    ]
