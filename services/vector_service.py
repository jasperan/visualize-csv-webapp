"""
Oracle AI Vector Search for dataset memory.

Stores dataset metadata + embeddings in Oracle DB so users can
semantically search across all previously uploaded CSVs.

Gracefully degrades when Oracle DB is not available.
"""
import json
import logging
import hashlib
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Oracle DB connection (lazy init)
_pool = None


def _get_pool(config):
    """Get or create the Oracle connection pool. Returns None if unavailable."""
    global _pool
    if _pool is not None:
        return _pool

    dsn = config.get('ORACLE_DSN')
    if not dsn:
        return None

    try:
        import oracledb
        _pool = oracledb.create_pool(
            user=config.get('ORACLE_USER', 'csvviz'),
            password=config.get('ORACLE_PASSWORD', ''),
            dsn=dsn,
            min=1, max=4, increment=1,
        )
        _ensure_table(_pool)
        logger.info('Oracle Vector Search connected: %s', dsn)
        return _pool
    except Exception as e:
        logger.warning('Oracle DB unavailable: %s', e)
        _pool = None
        return None


def _ensure_table(pool):
    """Create the dataset memory table if it doesn't exist."""
    with pool.acquire() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DECLARE
                table_exists NUMBER;
            BEGIN
                SELECT COUNT(*) INTO table_exists
                FROM user_tables WHERE table_name = 'DATASET_MEMORY';
                IF table_exists = 0 THEN
                    EXECUTE IMMEDIATE '
                        CREATE TABLE dataset_memory (
                            id RAW(16) DEFAULT SYS_GUID() PRIMARY KEY,
                            filename VARCHAR2(500) NOT NULL,
                            file_hash VARCHAR2(64) NOT NULL,
                            row_count NUMBER,
                            col_count NUMBER,
                            columns_json CLOB,
                            stats_json CLOB,
                            description VARCHAR2(4000),
                            embedding VECTOR(384, FLOAT32),
                            created_at TIMESTAMP DEFAULT SYSTIMESTAMP,
                            CONSTRAINT uk_dataset_hash UNIQUE (file_hash)
                        )
                    ';
                    EXECUTE IMMEDIATE '
                        CREATE VECTOR INDEX idx_dataset_embedding
                        ON dataset_memory (embedding)
                        ORGANIZATION NEIGHBOR PARTITIONS
                        DISTANCE COSINE
                        WITH TARGET ACCURACY 95
                    ';
                END IF;
            END;
        """)
        conn.commit()


def _compute_hash(df):
    """Compute a stable hash for deduplication."""
    h = hashlib.sha256()
    h.update(','.join(df.columns).encode())
    h.update(str(len(df)).encode())
    for col in df.columns[:10]:
        h.update(str(df[col].dtype).encode())
        sample = df[col].dropna().head(3).tolist()
        h.update(str(sample).encode())
    return h.hexdigest()


def _build_description(filename, df, col_info, stats):
    """Build a text description of the dataset for embedding."""
    parts = [f"Dataset: {filename}"]
    parts.append(f"{len(df)} rows, {len(df.columns)} columns")

    col_descs = []
    for c in col_info:
        desc = f"{c['name']} ({c['col_type']})"
        if c['col_type'] == 'numeric' and c['name'] in stats:
            s = stats[c['name']]
            desc += f" range {s.get('min', '?')}-{s.get('max', '?')}, mean {s.get('mean', '?')}"
        elif c['col_type'] == 'categorical':
            desc += f" {c['nunique']} categories"
        col_descs.append(desc)

    parts.append("Columns: " + "; ".join(col_descs))
    return ". ".join(parts)


def _get_embedding(text, ollama_url, model='nomic-embed-text'):
    """Get embedding vector from Ollama."""
    try:
        resp = requests.post(
            f"{ollama_url}/api/embed",
            json={'model': model, 'input': text},
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            embeddings = data.get('embeddings', [])
            if embeddings:
                return embeddings[0]
        return None
    except Exception as e:
        logger.warning('Embedding generation failed: %s', e)
        return None


def is_available(config):
    """Check if Oracle Vector Search is configured and reachable."""
    pool = _get_pool(config)
    return pool is not None


def store_dataset(config, filename, df, col_info, stats):
    """Store dataset metadata and embedding in Oracle. Returns dataset ID or None."""
    pool = _get_pool(config)
    if not pool:
        return None

    file_hash = _compute_hash(df)
    description = _build_description(filename, df, col_info, stats)

    embedding = _get_embedding(
        description,
        config.get('OLLAMA_BASE_URL', 'http://localhost:11434'),
        config.get('EMBEDDING_MODEL', 'nomic-embed-text'),
    )

    try:
        with pool.acquire() as conn:
            cursor = conn.cursor()

            # Check for existing
            cursor.execute(
                "SELECT id FROM dataset_memory WHERE file_hash = :h",
                {'h': file_hash}
            )
            existing = cursor.fetchone()
            if existing:
                return existing[0].hex() if hasattr(existing[0], 'hex') else str(existing[0])

            # Insert
            import oracledb
            cursor.execute("""
                INSERT INTO dataset_memory
                    (filename, file_hash, row_count, col_count, columns_json, stats_json, description, embedding)
                VALUES
                    (:fname, :fhash, :rows, :cols, :col_json, :stats_json, :descr, :emb)
                RETURNING id INTO :out_id
            """, {
                'fname': filename[:500],
                'fhash': file_hash,
                'rows': len(df),
                'cols': len(df.columns),
                'col_json': json.dumps(col_info),
                'stats_json': json.dumps(stats, default=str),
                'descr': description[:4000],
                'emb': embedding,
                'out_id': cursor.var(oracledb.DB_TYPE_RAW),
            })
            conn.commit()

            out_id = cursor.getbindnames()
            result = cursor.fetchone()
            logger.info('Stored dataset %s in vector memory', filename)
            return file_hash[:12]  # Return short ID
    except Exception as e:
        logger.error('Failed to store dataset: %s', e)
        return None


def search_datasets(config, query, limit=10):
    """Semantic search across stored datasets."""
    pool = _get_pool(config)
    if not pool:
        return []

    embedding = _get_embedding(
        query,
        config.get('OLLAMA_BASE_URL', 'http://localhost:11434'),
        config.get('EMBEDDING_MODEL', 'nomic-embed-text'),
    )

    if not embedding:
        return _text_search(pool, query, limit)

    try:
        with pool.acquire() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT filename, row_count, col_count, description,
                       VECTOR_DISTANCE(embedding, :qvec, COSINE) AS distance,
                       TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI') AS created
                FROM dataset_memory
                ORDER BY distance
                FETCH FIRST :lim ROWS ONLY
            """, {'qvec': embedding, 'lim': limit})

            results = []
            for row in cursor:
                results.append({
                    'filename': row[0],
                    'row_count': row[1],
                    'col_count': row[2],
                    'description': row[3],
                    'similarity': round(1 - (row[4] or 0), 3),
                    'created_at': row[5],
                })
            return results
    except Exception as e:
        logger.error('Vector search failed: %s', e)
        return _text_search(pool, query, limit)


def _text_search(pool, query, limit=10):
    """Fallback text search when embeddings aren't available."""
    try:
        with pool.acquire() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT filename, row_count, col_count, description,
                       TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI') AS created
                FROM dataset_memory
                WHERE LOWER(description) LIKE :q OR LOWER(filename) LIKE :q
                ORDER BY created_at DESC
                FETCH FIRST :lim ROWS ONLY
            """, {'q': f'%{query.lower()}%', 'lim': limit})

            results = []
            for row in cursor:
                results.append({
                    'filename': row[0],
                    'row_count': row[1],
                    'col_count': row[2],
                    'description': row[3],
                    'similarity': None,
                    'created_at': row[4],
                })
            return results
    except Exception as e:
        logger.error('Text search failed: %s', e)
        return []


def list_recent(config, limit=20):
    """List recently stored datasets."""
    pool = _get_pool(config)
    if not pool:
        return []

    try:
        with pool.acquire() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT filename, row_count, col_count, description,
                       TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI') AS created
                FROM dataset_memory
                ORDER BY created_at DESC
                FETCH FIRST :lim ROWS ONLY
            """, {'lim': limit})

            results = []
            for row in cursor:
                results.append({
                    'filename': row[0],
                    'row_count': row[1],
                    'col_count': row[2],
                    'description': row[3],
                    'created_at': row[4],
                })
            return results
    except Exception as e:
        logger.error('List recent failed: %s', e)
        return []
