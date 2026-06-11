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

# from fastapi import FastAPI, Depends
# from fastapi.responses import JSONResponse
# from pydantic import BaseModel
# import httpx
# import asyncio
# from functools import partial
# from groq import Groq

# import db_client as db
# from config import settings
# from connection import WorkspaceConn, get_workspace_conn

# from fastapi.middleware.cors import CORSMiddleware

# app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["https://metalensai.vercel.app"],  # replace with your frontend URL(s)
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],  # needed for X-Databricks-Host / X-Databricks-Token
# )

# # Module-level Groq clients — instantiated once, not on every request
# groq_client = Groq(api_key=settings.GROQ_API_KEY)
# groq_docs_client = Groq(api_key=settings.GROQ_API_KEY_DOCS)

# # Limit concurrent Databricks API calls to avoid 429 rate limiting
# SEMAPHORE = asyncio.Semaphore(5)

# # System schemas to skip — no value in documenting these
# SKIP_SCHEMAS = {"information_schema"}


# # ── request models ───────────────────────────────────────────────────────────

# class ConnectRequest(BaseModel):
#     host: str
#     token: str


# # ── AI helpers (unchanged) ───────────────────────────────────────────────────

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


# # ── connection endpoint ──────────────────────────────────────────────────────

# @app.post("/connect")
# async def connect(req: ConnectRequest):
#     """
#     Validate user-supplied Databricks credentials and return workspace status.
#     Does not persist credentials — frontend stores them (e.g. session storage)
#     and sends them back via X-Databricks-Host / X-Databricks-Token headers.
#     """
#     try:
#         catalogs = await db.list_catalogs(host=req.host, token=req.token)
#         return {
#             "connected": True,
#             "catalog_count": len(catalogs)
#         }
#     except httpx.HTTPStatusError as e:
#         if e.response.status_code in (401, 403):
#             error_msg = "Invalid Databricks token"
#         else:
#             error_msg = f"Connection failed: {e.response.text}"
#         return JSONResponse(
#             status_code=200,
#             content={"connected": False, "error": error_msg}
#         )
#     except httpx.RequestError as e:
#         return JSONResponse(
#             status_code=200,
#             content={"connected": False, "error": f"Could not reach host: {str(e)}"}
#         )


# # ── existing endpoints, now workspace-aware ──────────────────────────────────

# @app.get("/health")
# async def health():
#     return {"status": "ok"}


# @app.get("/catalogs")
# async def list_catalogs(conn: WorkspaceConn = Depends(get_workspace_conn)):
#     catalogs = await db.list_catalogs(**conn.kwargs())

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
# async def list_schemas(catalog: str, conn: WorkspaceConn = Depends(get_workspace_conn)):
#     schemas = await db.list_schemas(catalog, **conn.kwargs())

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
# async def list_tables(catalog: str, schema: str, conn: WorkspaceConn = Depends(get_workspace_conn)):
#     tables = await db.list_tables(catalog, schema, **conn.kwargs())

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
# async def doc_table(catalog: str, schema: str, table: str, conn: WorkspaceConn = Depends(get_workspace_conn)):
#     async with SEMAPHORE:
#         doc = await db.build_catalog_doc(
#             catalog,
#             schema_name=schema,
#             table_name=table,
#             **conn.kwargs()
#         )

#     doc = await add_ai_to_doc(catalog, schema, doc)

#     return doc


# @app.get("/schema-doc/{catalog}/{schema}")
# async def doc_schema(catalog: str, schema: str, conn: WorkspaceConn = Depends(get_workspace_conn)):
#     tables = await db.list_tables(catalog, schema, **conn.kwargs())

#     async def process_table(t):
#         table_name = t.get("name")
#         async with SEMAPHORE:
#             doc = await db.build_catalog_doc(
#                 catalog,
#                 schema_name=schema,
#                 table_name=table_name,
#                 **conn.kwargs()
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
# async def doc_catalog(catalog: str, conn: WorkspaceConn = Depends(get_workspace_conn)):
#     schemas = await db.list_schemas(catalog, **conn.kwargs())

#     catalog_docs = []
#     errors = []

#     async def process_table(catalog, schema_name, t):
#         table_name = t.get("name")
#         try:
#             async with SEMAPHORE:
#                 doc = await db.build_catalog_doc(
#                     catalog,
#                     schema_name=schema_name,
#                     table_name=table_name,
#                     **conn.kwargs()
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
#             tables = await db.list_tables(catalog, schema_name, **conn.kwargs())
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
from typing import Optional
import httpx
import asyncio
from functools import partial
from groq import Groq

import db_client as db
from config import settings
from connection import WorkspaceConn, get_workspace_conn
from session import session_store
from cache import cache

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Module-level Groq clients — instantiated once, not on every request
groq_client = Groq(api_key=settings.GROQ_API_KEY)
groq_docs_client = Groq(api_key=settings.GROQ_API_KEY_DOCS)

# Limit concurrent Databricks API calls to avoid 429 rate limiting
SEMAPHORE = asyncio.Semaphore(5)

# System schemas to skip
SKIP_SCHEMAS = {"information_schema"}


# ── Request models ────────────────────────────────────────────────────────────

class ConnectRequest(BaseModel):
    host: str
    token: str


class CopilotRequest(BaseModel):
    question: str
    catalog: str
    schema: Optional[str] = None
    table: Optional[str] = None


# ── Cache key helpers — session scoped ────────────────────────────────────────

def table_cache_keys(conn: WorkspaceConn, catalog: str, schema: str, table: str) -> tuple:
    return (conn.session_id, "table", catalog, schema, table)


def schema_cache_keys(conn: WorkspaceConn, catalog: str, schema: str) -> tuple:
    return (conn.session_id, "schema", catalog, schema)


def catalog_cache_keys(conn: WorkspaceConn, catalog: str) -> tuple:
    return (conn.session_id, "catalog", catalog)


# ── AI helpers ────────────────────────────────────────────────────────────────

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
        messages=[{"role": "user", "content": prompt}]
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
        messages=[{"role": "user", "content": prompt}]
    )

    return resp.choices[0].message.content.strip()


async def generate_ai_info_async(catalog, schema, table, table_type, cols):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        partial(generate_ai_info, catalog, schema, table, table_type, cols)
    )


async def generate_wiki_markdown_async(catalog, schema, table, table_type, comment, cols, ai_summary, ai_col_descs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        partial(generate_wiki_markdown, catalog, schema, table, table_type, comment, cols, ai_summary, ai_col_descs)
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
        col["ai_description"] = ai_col_descs.get(col["name"], "")

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


# ── Copilot ───────────────────────────────────────────────────────────────────

def build_copilot_context(conn: WorkspaceConn, catalog: str, schema: Optional[str], table: Optional[str]) -> Optional[str]:
    """
    Pull the most specific cached doc for this session.
    Priority: table > schema > catalog.
    """
    if table and schema:
        doc = cache.get(*table_cache_keys(conn, catalog, schema, table))
        if doc:
            return f"Table documentation:\n{doc.get('documentation', '')}"

    if schema:
        doc = cache.get(*schema_cache_keys(conn, catalog, schema))
        if doc:
            return f"Schema documentation for {catalog}.{schema}:\n{doc.get('documentation', '')}"

    doc = cache.get(*catalog_cache_keys(conn, catalog))
    if doc:
        return f"Catalog documentation for {catalog}:\n{doc.get('documentation', '')}"

    return None


def run_copilot(question: str, context: str) -> str:
    prompt = f"""
You are a data catalog AI copilot. You have access to the following documentation:

{context}

Answer the user's question clearly and concisely based only on the documentation above.
If the answer is not in the documentation, say so honestly.

User question: {question}
"""

    resp = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )

    return resp.choices[0].message.content.strip()


async def run_copilot_async(question: str, context: str) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(run_copilot, question, context))


# ── Exception handler ─────────────────────────────────────────────────────────

@app.exception_handler(httpx.HTTPStatusError)
async def databricks_error_handler(request, exc: httpx.HTTPStatusError):
    return JSONResponse(
        status_code=exc.response.status_code,
        content={"error": exc.response.text}
    )


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Connect / Disconnect ──────────────────────────────────────────────────────

@app.post("/connect")
async def connect(req: ConnectRequest):
    """
    Validate credentials and create a session.
    Returns session_id — frontend stores this and sends it as X-Session-ID header.
    """
    try:
        catalogs = await db.list_catalogs(host=req.host, token=req.token)
    except httpx.HTTPStatusError as e:
        error_msg = "Invalid Databricks token" if e.response.status_code in (401, 403) else f"Connection failed: {e.response.text}"
        return JSONResponse(status_code=200, content={"connected": False, "error": error_msg})
    except httpx.RequestError as e:
        return JSONResponse(status_code=200, content={"connected": False, "error": f"Could not reach host: {str(e)}"})

    session = session_store.create(host=req.host, token=req.token)

    return {
        "connected": True,
        "session_id": session.session_id,
        "catalog_count": len(catalogs)
    }


@app.post("/disconnect")
async def disconnect(conn: WorkspaceConn = Depends(get_workspace_conn)):
    """
    Invalidate the session and wipe all its cached data.
    """
    cleared = cache.delete_session(conn.session_id)
    session_store.delete(conn.session_id)

    return {
        "disconnected": True,
        "session_id": conn.session_id,
        "cache_entries_cleared": cleared
    }


# ── Browse endpoints (no cache) ───────────────────────────────────────────────

@app.get("/catalogs")
async def list_catalogs(conn: WorkspaceConn = Depends(get_workspace_conn)):
    catalogs = await db.list_catalogs(**conn.kwargs())
    return {"catalogs": [{"name": c.get("name"), "comment": c.get("comment")} for c in catalogs]}


@app.get("/catalogs/{catalog}/schemas")
async def list_schemas(catalog: str, conn: WorkspaceConn = Depends(get_workspace_conn)):
    schemas = await db.list_schemas(catalog, **conn.kwargs())
    return {"catalog": catalog, "schemas": [{"name": s.get("name")} for s in schemas]}


@app.get("/catalogs/{catalog}/schemas/{schema}/tables")
async def list_tables(catalog: str, schema: str, conn: WorkspaceConn = Depends(get_workspace_conn)):
    tables = await db.list_tables(catalog, schema, **conn.kwargs())
    return {"catalog": catalog, "schema": schema, "tables": [{"name": t.get("name"), "type": t.get("table_type")} for t in tables]}


# ── Table doc ─────────────────────────────────────────────────────────────────

@app.get("/doc/{catalog}/{schema}/{table}")
async def doc_table(catalog: str, schema: str, table: str, conn: WorkspaceConn = Depends(get_workspace_conn)):
    keys = table_cache_keys(conn, catalog, schema, table)

    cached = cache.get(*keys)
    if cached:
        return {**cached, "_cache": cache.info(*keys)}

    async with SEMAPHORE:
        doc = await db.build_catalog_doc(catalog, schema_name=schema, table_name=table, **conn.kwargs())

    doc = await add_ai_to_doc(catalog, schema, doc)
    cache.set(*keys, value=doc)

    return {**doc, "_cache": cache.info(*keys)}


@app.delete("/doc/{catalog}/{schema}/{table}/cache")
async def refresh_table_cache(catalog: str, schema: str, table: str, conn: WorkspaceConn = Depends(get_workspace_conn)):
    keys = table_cache_keys(conn, catalog, schema, table)
    deleted = cache.delete(*keys)
    return {"refreshed": deleted, "key": ":".join(keys)}


# ── Schema doc ────────────────────────────────────────────────────────────────

@app.get("/schema-doc/{catalog}/{schema}")
async def doc_schema(catalog: str, schema: str, conn: WorkspaceConn = Depends(get_workspace_conn)):
    keys = schema_cache_keys(conn, catalog, schema)

    cached = cache.get(*keys)
    if cached:
        return {**cached, "_cache": cache.info(*keys)}

    tables = await db.list_tables(catalog, schema, **conn.kwargs())

    async def process_table(t):
        table_name = t.get("name")
        async with SEMAPHORE:
            doc = await db.build_catalog_doc(catalog, schema_name=schema, table_name=table_name, **conn.kwargs())
        return await add_ai_to_doc(catalog, schema, doc)

    schema_docs = list(await asyncio.gather(*[process_table(t) for t in tables]))

    result = {
        "catalog": catalog,
        "schema": schema,
        "table_count": len(schema_docs),
        "tables": schema_docs,
        "documentation": "\n\n---\n\n".join(d.get("documentation", "") for d in schema_docs)
    }

    cache.set(*keys, value=result)

    return {**result, "_cache": cache.info(*keys)}


@app.delete("/schema-doc/{catalog}/{schema}/cache")
async def refresh_schema_cache(catalog: str, schema: str, conn: WorkspaceConn = Depends(get_workspace_conn)):
    keys = schema_cache_keys(conn, catalog, schema)
    deleted = cache.delete(*keys)
    return {"refreshed": deleted, "key": ":".join(keys)}


# ── Catalog doc ───────────────────────────────────────────────────────────────

@app.get("/catalog-doc/{catalog}")
async def doc_catalog(catalog: str, conn: WorkspaceConn = Depends(get_workspace_conn)):
    keys = catalog_cache_keys(conn, catalog)

    cached = cache.get(*keys)
    if cached:
        return {**cached, "_cache": cache.info(*keys)}

    schemas = await db.list_schemas(catalog, **conn.kwargs())

    catalog_docs = []
    errors = []

    async def process_table(catalog, schema_name, t):
        table_name = t.get("name")
        try:
            async with SEMAPHORE:
                doc = await db.build_catalog_doc(catalog, schema_name=schema_name, table_name=table_name, **conn.kwargs())
            return await add_ai_to_doc(catalog, schema_name, doc), None
        except Exception as e:
            return None, {"level": "table", "schema": schema_name, "table": table_name, "error": str(e)}

    for s in schemas:
        schema_name = s.get("name")

        if schema_name in SKIP_SCHEMAS:
            continue

        try:
            tables = await db.list_tables(catalog, schema_name, **conn.kwargs())
        except Exception as e:
            errors.append({"level": "schema", "schema": schema_name, "error": str(e)})
            continue

        results = await asyncio.gather(*[process_table(catalog, schema_name, t) for t in tables])

        schema_docs = []
        for doc, err in results:
            if err:
                errors.append(err)
            else:
                schema_docs.append(doc)

        catalog_docs.append({
            "schema": schema_name,
            "table_count": len(schema_docs),
            "tables": schema_docs,
            "documentation": "\n\n---\n\n".join(d.get("documentation", "") for d in schema_docs)
        })

    full_doc = "\n\n===\n\n".join(s.get("documentation", "") for s in catalog_docs)

    result = {
        "catalog": catalog,
        "schema_count": len(catalog_docs),
        "schemas": catalog_docs,
        "errors": errors,
        "documentation": full_doc
    }

    cache.set(*keys, value=result)

    return {**result, "_cache": cache.info(*keys)}


@app.delete("/catalog-doc/{catalog}/cache")
async def refresh_catalog_cache(catalog: str, conn: WorkspaceConn = Depends(get_workspace_conn)):
    keys = catalog_cache_keys(conn, catalog)
    deleted = cache.delete(*keys)
    return {"refreshed": deleted, "key": ":".join(keys)}


# ── Copilot ───────────────────────────────────────────────────────────────────

@app.post("/copilot")
async def copilot(req: CopilotRequest, conn: WorkspaceConn = Depends(get_workspace_conn)):
    """
    Answer user questions using cached documentation as context.
    Fully session-scoped — users only ever see their own workspace data.
    Call /catalog-doc, /schema-doc, or /doc first to warm the cache.
    """
    context = build_copilot_context(
        conn=conn,
        catalog=req.catalog,
        schema=req.schema,
        table=req.table
    )

    if not context:
        return JSONResponse(
            status_code=404,
            content={
                "error": "No cached documentation found for this session. Please call /catalog-doc, /schema-doc, or /doc first."
            }
        )

    answer = await run_copilot_async(req.question, context)

    return {
        "question": req.question,
        "answer": answer,
        "context_source": {
            "catalog": req.catalog,
            "schema": req.schema,
            "table": req.table
        }
    }