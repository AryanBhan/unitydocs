# from fastapi import FastAPI
# from fastapi.responses import JSONResponse
# import httpx
# import asyncio
# from functools import partial
# from groq import Groq

# import db_client as db
# from config import settings

# app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

# # Module-level Groq client — instantiated once, not on every request
# groq_client = Groq(api_key=settings.GROQ_API_KEY)

# # Limit concurrent Databricks API calls to avoid 429 rate limiting
# SEMAPHORE = asyncio.Semaphore(5)

# # System schemas to skip — no value in documenting these
# SKIP_SCHEMAS = {"information_schema"}


# def generate_ai_info(catalog, schema, table, table_type, cols):
#     col_list = "\n".join([
#         f"- {c['name']} ({c['type']})"
#         for c in cols
#     ])

#     prompt = f"""
# You are a data documentation assistant.

# Table: {catalog}.{schema}.{table} ({table_type})

# Columns:
# {col_list}

# Respond ONLY in this exact format:

# SUMMARY: <2-3 sentence description of table purpose>
# COLUMNS:
# <column_name>: <one-line description>
# """

#     resp = groq_client.chat.completions.create(
#         model="llama-3.3-70b-versatile",
#         max_tokens=800,
#         messages=[
#             {"role": "user", "content": prompt}
#         ]
#     )

#     text = resp.choices[0].message.content.strip()

#     summary = ""
#     col_descs = {}
#     in_cols = False

#     for line in text.splitlines():
#         line = line.strip()

#         if line.startswith("SUMMARY:"):
#             summary = line.replace("SUMMARY:", "").strip()

#         elif line.startswith("COLUMNS:"):
#             in_cols = True

#         elif in_cols and ":" in line:
#             k, v = line.split(":", 1)
#             col_name = k.strip().lstrip("-").strip()
#             col_descs[col_name] = v.strip()

#     return summary, col_descs


# async def generate_ai_info_async(catalog, schema, table, table_type, cols):
#     """Run blocking Groq call in a thread pool so it doesn't block the event loop."""
#     loop = asyncio.get_event_loop()
#     return await loop.run_in_executor(
#         None,
#         partial(generate_ai_info, catalog, schema, table, table_type, cols)
#     )


# async def add_ai_to_doc(catalog, schema, doc):
#     table_name = doc["table"]["name"]
#     table_type = doc["table"].get("table_type", "")
#     cols = doc["table"]["columns"]

#     ai_summary, ai_col_descs = await generate_ai_info_async(
#         catalog=catalog,
#         schema=schema,
#         table=table_name,
#         table_type=table_type,
#         cols=cols
#     )

#     doc["ai_summary"] = ai_summary

#     for col in cols:
#         col_name = col["name"]
#         col["ai_description"] = ai_col_descs.get(col_name, "")

#     return doc


# @app.exception_handler(httpx.HTTPStatusError)
# async def databricks_error_handler(request, exc: httpx.HTTPStatusError):
#     return JSONResponse(
#         status_code=exc.response.status_code,
#         content={"error": exc.response.text}
#     )


# @app.get("/health")
# async def health():
#     return {"status": "ok"}


# @app.get("/catalogs")
# async def list_catalogs():
#     catalogs = await db.list_catalogs()

#     return {
#         "catalogs": [
#             {
#                 "name": c.get("name"),
#                 "comment": c.get("comment")
#             }
#             for c in catalogs
#         ]
#     }


# @app.get("/catalogs/{catalog}/schemas")
# async def list_schemas(catalog: str):
#     schemas = await db.list_schemas(catalog)

#     return {
#         "catalog": catalog,
#         "schemas": [
#             {
#                 "name": s.get("name")
#             }
#             for s in schemas
#         ]
#     }


# @app.get("/catalogs/{catalog}/schemas/{schema}/tables")
# async def list_tables(catalog: str, schema: str):
#     tables = await db.list_tables(catalog, schema)

#     return {
#         "catalog": catalog,
#         "schema": schema,
#         "tables": [
#             {
#                 "name": t.get("name"),
#                 "type": t.get("table_type")
#             }
#             for t in tables
#         ]
#     }


# @app.get("/doc/{catalog}/{schema}/{table}")
# async def doc_table(catalog: str, schema: str, table: str):
#     async with SEMAPHORE:
#         doc = await db.build_catalog_doc(
#             catalog,
#             schema_name=schema,
#             table_name=table
#         )

#     doc = await add_ai_to_doc(catalog, schema, doc)

#     return doc


# @app.get("/schema-doc/{catalog}/{schema}")
# async def doc_schema(catalog: str, schema: str):
#     tables = await db.list_tables(catalog, schema)

#     async def process_table(t):
#         table_name = t.get("name")
#         async with SEMAPHORE:
#             doc = await db.build_catalog_doc(
#                 catalog,
#                 schema_name=schema,
#                 table_name=table_name
#             )
#         return await add_ai_to_doc(catalog, schema, doc)

#     # All tables processed in parallel — much faster, won't time out
#     schema_docs = await asyncio.gather(*[process_table(t) for t in tables])

#     return {
#         "catalog": catalog,
#         "schema": schema,
#         "table_count": len(schema_docs),
#         "tables": list(schema_docs)
#     }


# @app.get("/catalog-doc/{catalog}")
# async def doc_catalog(catalog: str):
#     schemas = await db.list_schemas(catalog)

#     catalog_docs = []
#     errors = []

#     async def process_table(catalog, schema_name, t):
#         table_name = t.get("name")
#         try:
#             async with SEMAPHORE:
#                 doc = await db.build_catalog_doc(
#                     catalog,
#                     schema_name=schema_name,
#                     table_name=table_name
#                 )
#             return await add_ai_to_doc(catalog, schema_name, doc), None
#         except Exception as e:
#             return None, {
#                 "level": "table",
#                 "schema": schema_name,
#                 "table": table_name,
#                 "error": str(e)
#             }

#     for s in schemas:
#         schema_name = s.get("name")

#         # Skip system schemas — no value in documenting these
#         if schema_name in SKIP_SCHEMAS:
#             continue

#         try:
#             tables = await db.list_tables(catalog, schema_name)
#         except Exception as e:
#             errors.append({
#                 "level": "schema",
#                 "schema": schema_name,
#                 "error": str(e)
#             })
#             continue

#         # All tables in this schema processed in parallel
#         results = await asyncio.gather(*[
#             process_table(catalog, schema_name, t) for t in tables
#         ])

#         schema_docs = []
#         for doc, err in results:
#             if err:
#                 errors.append(err)
#             else:
#                 schema_docs.append(doc)

#         catalog_docs.append({
#             "schema": schema_name,
#             "table_count": len(schema_docs),
#             "tables": schema_docs
#         })

#     return {
#         "catalog": catalog,
#         "schema_count": len(catalog_docs),
#         "schemas": catalog_docs,
#         "errors": errors
#     }


# from fastapi import FastAPI
# from fastapi.responses import JSONResponse
# import httpx
# import asyncio
# from functools import partial
# from groq import Groq

# import db_client as db
# from config import settings

# app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

# # Module-level Groq clients — instantiated once, not on every request
# groq_client = Groq(api_key=settings.GROQ_API_KEY)
# groq_docs_client = Groq(api_key=settings.GROQ_API_KEY_DOCS)

# # Limit concurrent Databricks API calls to avoid 429 rate limiting
# SEMAPHORE = asyncio.Semaphore(5)

# # System schemas to skip — no value in documenting these
# SKIP_SCHEMAS = {"information_schema"}


# def generate_ai_info(catalog, schema, table, table_type, cols):
#     col_list = "\n".join([
#         f"- {c['name']} ({c['type']})"
#         for c in cols
#     ])

#     prompt = f"""
# You are a data documentation assistant.

# Table: {catalog}.{schema}.{table} ({table_type})

# Columns:
# {col_list}

# Respond ONLY in this exact format:

# SUMMARY: <2-3 sentence description of table purpose>
# COLUMNS:
# <column_name>: <one-line description>
# """

#     resp = groq_client.chat.completions.create(
#         model="llama-3.3-70b-versatile",
#         max_tokens=800,
#         messages=[
#             {"role": "user", "content": prompt}
#         ]
#     )

#     text = resp.choices[0].message.content.strip()

#     summary = ""
#     col_descs = {}
#     in_cols = False

#     for line in text.splitlines():
#         line = line.strip()

#         if line.startswith("SUMMARY:"):
#             summary = line.replace("SUMMARY:", "").strip()

#         elif line.startswith("COLUMNS:"):
#             in_cols = True

#         elif in_cols and ":" in line:
#             k, v = line.split(":", 1)
#             col_name = k.strip().lstrip("-").strip()
#             col_descs[col_name] = v.strip()

#     return summary, col_descs


# def generate_wiki_markdown(catalog, schema, table, table_type, comment, cols, ai_summary, ai_col_descs):
#     """Generate a fully curated Markdown page suitable for direct paste into a wiki."""
#     col_rows = "\n".join([
#         f"| {c['name']} | {c['type']} | {'Yes' if c.get('nullable', True) else 'No'} | "
#         f"{ai_col_descs.get(c['name'], '')} |"
#         for c in cols
#     ])

#     prompt = f"""
# You are a technical writer creating a wiki page for a data catalog table.

# Table: {catalog}.{schema}.{table}
# Type: {table_type}
# Existing comment: {comment or "None"}
# AI-generated summary: {ai_summary}

# Columns table (already formatted, do not regenerate):
# | Column | Type | Nullable | Description |
# |---|---|---|---|
# {col_rows}

# Write a polished Markdown wiki page with the following sections:
# 1. A top-level heading with the full table name (catalog.schema.table)
# 2. An "Overview" section (2-4 sentences, expand on the summary, mention table type)
# 3. A "Columns" section containing the columns table EXACTLY as provided above (do not alter it)
# 4. A "Notes" section with any caveats, usage tips, or "None" if nothing relevant

# Respond with ONLY the raw Markdown content, no code fences, no commentary.
# """

#     resp = groq_docs_client.chat.completions.create(
#         model="llama-3.3-70b-versatile",
#         max_tokens=1500,
#         messages=[
#             {"role": "user", "content": prompt}
#         ]
#     )

#     return resp.choices[0].message.content.strip()


# async def generate_ai_info_async(catalog, schema, table, table_type, cols):
#     """Run blocking Groq call in a thread pool so it doesn't block the event loop."""
#     loop = asyncio.get_event_loop()
#     return await loop.run_in_executor(
#         None,
#         partial(generate_ai_info, catalog, schema, table, table_type, cols)
#     )


# async def generate_wiki_markdown_async(catalog, schema, table, table_type, comment, cols, ai_summary, ai_col_descs):
#     """Run blocking Groq call (markdown generation) in a thread pool."""
#     loop = asyncio.get_event_loop()
#     return await loop.run_in_executor(
#         None,
#         partial(
#             generate_wiki_markdown,
#             catalog, schema, table, table_type, comment, cols, ai_summary, ai_col_descs
#         )
#     )


# async def add_ai_to_doc(catalog, schema, doc):
#     table_name = doc["table"]["name"]
#     table_type = doc["table"].get("table_type", "")
#     comment = doc["table"].get("comment")
#     cols = doc["table"]["columns"]

#     ai_summary, ai_col_descs = await generate_ai_info_async(
#         catalog=catalog,
#         schema=schema,
#         table=table_name,
#         table_type=table_type,
#         cols=cols
#     )

#     doc["ai_summary"] = ai_summary

#     for col in cols:
#         col_name = col["name"]
#         col["ai_description"] = ai_col_descs.get(col_name, "")

#     # Generate fully curated wiki markdown using a separate Groq key
#     doc["documentation"] = await generate_wiki_markdown_async(
#         catalog=catalog,
#         schema=schema,
#         table=table_name,
#         table_type=table_type,
#         comment=comment,
#         cols=cols,
#         ai_summary=ai_summary,
#         ai_col_descs=ai_col_descs
#     )

#     return doc


# @app.exception_handler(httpx.HTTPStatusError)
# async def databricks_error_handler(request, exc: httpx.HTTPStatusError):
#     return JSONResponse(
#         status_code=exc.response.status_code,
#         content={"error": exc.response.text}
#     )


# @app.get("/health")
# async def health():
#     return {"status": "ok"}


# @app.get("/catalogs")
# async def list_catalogs():
#     catalogs = await db.list_catalogs()

#     return {
#         "catalogs": [
#             {
#                 "name": c.get("name"),
#                 "comment": c.get("comment")
#             }
#             for c in catalogs
#         ]
#     }


# @app.get("/catalogs/{catalog}/schemas")
# async def list_schemas(catalog: str):
#     schemas = await db.list_schemas(catalog)

#     return {
#         "catalog": catalog,
#         "schemas": [
#             {
#                 "name": s.get("name")
#             }
#             for s in schemas
#         ]
#     }


# @app.get("/catalogs/{catalog}/schemas/{schema}/tables")
# async def list_tables(catalog: str, schema: str):
#     tables = await db.list_tables(catalog, schema)

#     return {
#         "catalog": catalog,
#         "schema": schema,
#         "tables": [
#             {
#                 "name": t.get("name"),
#                 "type": t.get("table_type")
#             }
#             for t in tables
#         ]
#     }


# @app.get("/doc/{catalog}/{schema}/{table}")
# async def doc_table(catalog: str, schema: str, table: str):
#     async with SEMAPHORE:
#         doc = await db.build_catalog_doc(
#             catalog,
#             schema_name=schema,
#             table_name=table
#         )

#     doc = await add_ai_to_doc(catalog, schema, doc)

#     return doc


# @app.get("/schema-doc/{catalog}/{schema}")
# async def doc_schema(catalog: str, schema: str):
#     tables = await db.list_tables(catalog, schema)

#     async def process_table(t):
#         table_name = t.get("name")
#         async with SEMAPHORE:
#             doc = await db.build_catalog_doc(
#                 catalog,
#                 schema_name=schema,
#                 table_name=table_name
#             )
#         return await add_ai_to_doc(catalog, schema, doc)

#     # All tables processed in parallel — much faster, won't time out
#     schema_docs = await asyncio.gather(*[process_table(t) for t in tables])

#     return {
#         "catalog": catalog,
#         "schema": schema,
#         "table_count": len(schema_docs),
#         "tables": list(schema_docs)
#     }


# @app.get("/catalog-doc/{catalog}")
# async def doc_catalog(catalog: str):
#     schemas = await db.list_schemas(catalog)

#     catalog_docs = []
#     errors = []

#     async def process_table(catalog, schema_name, t):
#         table_name = t.get("name")
#         try:
#             async with SEMAPHORE:
#                 doc = await db.build_catalog_doc(
#                     catalog,
#                     schema_name=schema_name,
#                     table_name=table_name
#                 )
#             return await add_ai_to_doc(catalog, schema_name, doc), None
#         except Exception as e:
#             return None, {
#                 "level": "table",
#                 "schema": schema_name,
#                 "table": table_name,
#                 "error": str(e)
#             }

#     for s in schemas:
#         schema_name = s.get("name")

#         # Skip system schemas — no value in documenting these
#         if schema_name in SKIP_SCHEMAS:
#             continue

#         try:
#             tables = await db.list_tables(catalog, schema_name)
#         except Exception as e:
#             errors.append({
#                 "level": "schema",
#                 "schema": schema_name,
#                 "error": str(e)
#             })
#             continue

#         # All tables in this schema processed in parallel
#         results = await asyncio.gather(*[
#             process_table(catalog, schema_name, t) for t in tables
#         ])

#         schema_docs = []
#         for doc, err in results:
#             if err:
#                 errors.append(err)
#             else:
#                 schema_docs.append(doc)

#         catalog_docs.append({
#             "schema": schema_name,
#             "table_count": len(schema_docs),
#             "tables": schema_docs
#         })

#     return {
#         "catalog": catalog,
#         "schema_count": len(catalog_docs),
#         "schemas": catalog_docs,
#         "errors": errors
#     }

from fastapi import FastAPI, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import httpx
import asyncio
from functools import partial
from groq import Groq

import db_client as db
from config import settings
from connection import WorkspaceConn, get_workspace_conn

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # replace with your frontend URL(s)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],  # needed for X-Databricks-Host / X-Databricks-Token
)

# Module-level Groq clients — instantiated once, not on every request
groq_client = Groq(api_key=settings.GROQ_API_KEY)
groq_docs_client = Groq(api_key=settings.GROQ_API_KEY_DOCS)

# Limit concurrent Databricks API calls to avoid 429 rate limiting
SEMAPHORE = asyncio.Semaphore(5)

# System schemas to skip — no value in documenting these
SKIP_SCHEMAS = {"information_schema"}


# ── request models ───────────────────────────────────────────────────────────

class ConnectRequest(BaseModel):
    host: str
    token: str


# ── AI helpers (unchanged) ───────────────────────────────────────────────────

def generate_ai_info(catalog, schema, table, table_type, cols):
    col_list = "\n".join([
        f"- {c['name']} ({c['type']})"
        for c in cols
    ])

    prompt = f"""
You are a data documentation assistant.

Table: {catalog}.{schema}.{table} ({table_type})

Columns:
{col_list}

Respond ONLY in this exact format:

SUMMARY: <2-3 sentence description of table purpose>
COLUMNS:
<column_name>: <one-line description>
"""

    resp = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=800,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    text = resp.choices[0].message.content.strip()

    summary = ""
    col_descs = {}
    in_cols = False

    for line in text.splitlines():
        line = line.strip()

        if line.startswith("SUMMARY:"):
            summary = line.replace("SUMMARY:", "").strip()

        elif line.startswith("COLUMNS:"):
            in_cols = True

        elif in_cols and ":" in line:
            k, v = line.split(":", 1)
            col_name = k.strip().lstrip("-").strip()
            col_descs[col_name] = v.strip()

    return summary, col_descs


def generate_wiki_markdown(catalog, schema, table, table_type, comment, cols, ai_summary, ai_col_descs):
    """Generate a fully curated Markdown page suitable for direct paste into a wiki."""
    col_rows = "\n".join([
        f"| {c['name']} | {c['type']} | {'Yes' if c.get('nullable', True) else 'No'} | "
        f"{ai_col_descs.get(c['name'], '')} |"
        for c in cols
    ])

    prompt = f"""
You are a technical writer creating a wiki page for a data catalog table.

Table: {catalog}.{schema}.{table}
Type: {table_type}
Existing comment: {comment or "None"}
AI-generated summary: {ai_summary}

Columns table (already formatted, do not regenerate):
| Column | Type | Nullable | Description |
|---|---|---|---|
{col_rows}

Write a polished Markdown wiki page with the following sections:
1. A top-level heading with the full table name (catalog.schema.table)
2. An "Overview" section (2-4 sentences, expand on the summary, mention table type)
3. A "Columns" section containing the columns table EXACTLY as provided above (do not alter it)
4. A "Notes" section with any caveats, usage tips, or "None" if nothing relevant

Respond with ONLY the raw Markdown content, no code fences, no commentary.
"""

    resp = groq_docs_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=1500,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    return resp.choices[0].message.content.strip()


async def generate_ai_info_async(catalog, schema, table, table_type, cols):
    """Run blocking Groq call in a thread pool so it doesn't block the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        partial(generate_ai_info, catalog, schema, table, table_type, cols)
    )


async def generate_wiki_markdown_async(catalog, schema, table, table_type, comment, cols, ai_summary, ai_col_descs):
    """Run blocking Groq call (markdown generation) in a thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        partial(
            generate_wiki_markdown,
            catalog, schema, table, table_type, comment, cols, ai_summary, ai_col_descs
        )
    )


async def add_ai_to_doc(catalog, schema, doc):
    table_name = doc["table"]["name"]
    table_type = doc["table"].get("table_type", "")
    comment = doc["table"].get("comment")
    cols = doc["table"]["columns"]

    ai_summary, ai_col_descs = await generate_ai_info_async(
        catalog=catalog,
        schema=schema,
        table=table_name,
        table_type=table_type,
        cols=cols
    )

    doc["ai_summary"] = ai_summary

    for col in cols:
        col_name = col["name"]
        col["ai_description"] = ai_col_descs.get(col_name, "")

    # Generate fully curated wiki markdown using a separate Groq key
    doc["documentation"] = await generate_wiki_markdown_async(
        catalog=catalog,
        schema=schema,
        table=table_name,
        table_type=table_type,
        comment=comment,
        cols=cols,
        ai_summary=ai_summary,
        ai_col_descs=ai_col_descs
    )

    return doc


@app.exception_handler(httpx.HTTPStatusError)
async def databricks_error_handler(request, exc: httpx.HTTPStatusError):
    return JSONResponse(
        status_code=exc.response.status_code,
        content={"error": exc.response.text}
    )


# ── connection endpoint ──────────────────────────────────────────────────────

@app.post("/connect")
async def connect(req: ConnectRequest):
    """
    Validate user-supplied Databricks credentials and return workspace status.
    Does not persist credentials — frontend stores them (e.g. session storage)
    and sends them back via X-Databricks-Host / X-Databricks-Token headers.
    """
    try:
        catalogs = await db.list_catalogs(host=req.host, token=req.token)
        return {
            "connected": True,
            "catalog_count": len(catalogs)
        }
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (401, 403):
            error_msg = "Invalid Databricks token"
        else:
            error_msg = f"Connection failed: {e.response.text}"
        return JSONResponse(
            status_code=200,
            content={"connected": False, "error": error_msg}
        )
    except httpx.RequestError as e:
        return JSONResponse(
            status_code=200,
            content={"connected": False, "error": f"Could not reach host: {str(e)}"}
        )


# ── existing endpoints, now workspace-aware ──────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/catalogs")
async def list_catalogs(conn: WorkspaceConn = Depends(get_workspace_conn)):
    catalogs = await db.list_catalogs(**conn.kwargs())

    return {
        "catalogs": [
            {
                "name": c.get("name"),
                "comment": c.get("comment")
            }
            for c in catalogs
        ]
    }


@app.get("/catalogs/{catalog}/schemas")
async def list_schemas(catalog: str, conn: WorkspaceConn = Depends(get_workspace_conn)):
    schemas = await db.list_schemas(catalog, **conn.kwargs())

    return {
        "catalog": catalog,
        "schemas": [
            {
                "name": s.get("name")
            }
            for s in schemas
        ]
    }


@app.get("/catalogs/{catalog}/schemas/{schema}/tables")
async def list_tables(catalog: str, schema: str, conn: WorkspaceConn = Depends(get_workspace_conn)):
    tables = await db.list_tables(catalog, schema, **conn.kwargs())

    return {
        "catalog": catalog,
        "schema": schema,
        "tables": [
            {
                "name": t.get("name"),
                "type": t.get("table_type")
            }
            for t in tables
        ]
    }


@app.get("/doc/{catalog}/{schema}/{table}")
async def doc_table(catalog: str, schema: str, table: str, conn: WorkspaceConn = Depends(get_workspace_conn)):
    async with SEMAPHORE:
        doc = await db.build_catalog_doc(
            catalog,
            schema_name=schema,
            table_name=table,
            **conn.kwargs()
        )

    doc = await add_ai_to_doc(catalog, schema, doc)

    return doc


@app.get("/schema-doc/{catalog}/{schema}")
async def doc_schema(catalog: str, schema: str, conn: WorkspaceConn = Depends(get_workspace_conn)):
    tables = await db.list_tables(catalog, schema, **conn.kwargs())

    async def process_table(t):
        table_name = t.get("name")
        async with SEMAPHORE:
            doc = await db.build_catalog_doc(
                catalog,
                schema_name=schema,
                table_name=table_name,
                **conn.kwargs()
            )
        return await add_ai_to_doc(catalog, schema, doc)

    # All tables processed in parallel — much faster, won't time out
    schema_docs = await asyncio.gather(*[process_table(t) for t in tables])

    return {
        "catalog": catalog,
        "schema": schema,
        "table_count": len(schema_docs),
        "tables": list(schema_docs)
    }


@app.get("/catalog-doc/{catalog}")
async def doc_catalog(catalog: str, conn: WorkspaceConn = Depends(get_workspace_conn)):
    schemas = await db.list_schemas(catalog, **conn.kwargs())

    catalog_docs = []
    errors = []

    async def process_table(catalog, schema_name, t):
        table_name = t.get("name")
        try:
            async with SEMAPHORE:
                doc = await db.build_catalog_doc(
                    catalog,
                    schema_name=schema_name,
                    table_name=table_name,
                    **conn.kwargs()
                )
            return await add_ai_to_doc(catalog, schema_name, doc), None
        except Exception as e:
            return None, {
                "level": "table",
                "schema": schema_name,
                "table": table_name,
                "error": str(e)
            }

    for s in schemas:
        schema_name = s.get("name")

        # Skip system schemas — no value in documenting these
        if schema_name in SKIP_SCHEMAS:
            continue

        try:
            tables = await db.list_tables(catalog, schema_name, **conn.kwargs())
        except Exception as e:
            errors.append({
                "level": "schema",
                "schema": schema_name,
                "error": str(e)
            })
            continue

        # All tables in this schema processed in parallel
        results = await asyncio.gather(*[
            process_table(catalog, schema_name, t) for t in tables
        ])

        schema_docs = []
        for doc, err in results:
            if err:
                errors.append(err)
            else:
                schema_docs.append(doc)

        catalog_docs.append({
            "schema": schema_name,
            "table_count": len(schema_docs),
            "tables": schema_docs
        })

    return {
        "catalog": catalog,
        "schema_count": len(catalog_docs),
        "schemas": catalog_docs,
        "errors": errors
    }