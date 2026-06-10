# """
# Databricks Unity Catalog REST API wrapper.
# Docs: https://docs.databricks.com/api/workspace/catalogs
# """

# import httpx
# from typing import Optional
# from config import settings


# BASE = settings.DATABRICKS_HOST.rstrip("/")
# HEADERS = {
#     "Authorization": f"Bearer {settings.DATABRICKS_TOKEN}",
#     "Content-Type": "application/json",
# }

# # ── helpers ──────────────────────────────────────────────────────────────────

# async def _get(path: str, params: dict = None) -> dict:
#     async with httpx.AsyncClient(timeout=30) as client:
#         r = await client.get(f"{BASE}/api/2.1/unity-catalog/{path}", headers=HEADERS, params=params)
#         r.raise_for_status()
#         return r.json()


# # ── catalog level ─────────────────────────────────────────────────────────────

# async def list_catalogs() -> list[dict]:
#     data = await _get("catalogs")
#     return data.get("catalogs", [])


# async def get_catalog(catalog_name: str) -> dict:
#     return await _get(f"catalogs/{catalog_name}")


# # ── schema level ──────────────────────────────────────────────────────────────

# async def list_schemas(catalog_name: str) -> list[dict]:
#     data = await _get("schemas", params={"catalog_name": catalog_name})
#     return data.get("schemas", [])


# async def get_schema(catalog_name: str, schema_name: str) -> dict:
#     return await _get(f"schemas/{catalog_name}.{schema_name}")


# # ── table level ───────────────────────────────────────────────────────────────

# async def list_tables(catalog_name: str, schema_name: str) -> list[dict]:
#     data = await _get(
#         "tables",
#         params={"catalog_name": catalog_name, "schema_name": schema_name},
#     )
#     return data.get("tables", [])


# async def get_table(catalog_name: str, schema_name: str, table_name: str) -> dict:
#     return await _get(f"tables/{catalog_name}.{schema_name}.{table_name}")


# # ── doc builder ───────────────────────────────────────────────────────────────

# def _col_summary(columns: list[dict]) -> list[dict]:
#     return [
#         {
#             "name": c.get("name"),
#             "type": c.get("type_text") or c.get("type_name"),
#             "nullable": c.get("nullable", True),
#             "comment": c.get("comment"),
#         }
#         for c in columns
#     ]


# async def build_catalog_doc(
#     catalog_name: str,
#     schema_name: Optional[str] = None,
#     table_name: Optional[str] = None,
# ) -> dict:
#     """
#     Build a brief documentation dict.
#     Scope narrows based on which args are provided.
#     """
#     doc: dict = {}

#     # ── catalog info ──
#     catalog = await get_catalog(catalog_name)
#     doc["catalog"] = {
#         "name": catalog.get("name"),
#         "comment": catalog.get("comment"),
#         "owner": catalog.get("owner"),
#         "created_at": catalog.get("created_at"),
#         "metastore_id": catalog.get("metastore_id"),
#     }

#     # ── schema scope ──
#     if schema_name:
#         schema = await get_schema(catalog_name, schema_name)
#         doc["schema"] = {
#             "name": schema.get("name"),
#             "comment": schema.get("comment"),
#             "owner": schema.get("owner"),
#         }

#         # ── table scope ──
#         if table_name:
#             table = await get_table(catalog_name, schema_name, table_name)
#             doc["table"] = {
#                 "name": table.get("name"),
#                 "full_name": table.get("full_name"),
#                 "table_type": table.get("table_type"),
#                 "data_source_format": table.get("data_source_format"),
#                 "comment": table.get("comment"),
#                 "owner": table.get("owner"),
#                 "storage_location": table.get("storage_location"),
#                 "columns": _col_summary(table.get("columns", [])),
#             }
#         else:
#             # all tables in schema (summary only)
#             tables = await list_tables(catalog_name, schema_name)
#             doc["tables"] = [
#                 {
#                     "name": t.get("name"),
#                     "full_name": t.get("full_name"),
#                     "table_type": t.get("table_type"),
#                     "comment": t.get("comment"),
#                     "column_count": len(t.get("columns", [])),
#                 }
#                 for t in tables
#             ]
#     else:
#         # all schemas in catalog (summary only)
#         schemas = await list_schemas(catalog_name)
#         doc["schemas"] = [
#             {
#                 "name": s.get("name"),
#                 "comment": s.get("comment"),
#                 "owner": s.get("owner"),
#             }
#             for s in schemas
#         ]

#     return doc


"""
Databricks Unity Catalog REST API wrapper.
Docs: https://docs.databricks.com/api/workspace/catalogs
"""

import httpx
from typing import Optional
from config import settings


# ── helpers ──────────────────────────────────────────────────────────────────

def _build_conn(host: Optional[str] = None, token: Optional[str] = None) -> tuple[str, dict]:
    """
    Resolve effective connection details.
    Priority: explicit host/token (e.g. from request headers) > environment defaults.
    """
    base = (host or settings.DATABRICKS_HOST).rstrip("/")
    auth_token = token or settings.DATABRICKS_TOKEN

    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    }
    return base, headers


async def _get(path: str, params: dict = None, host: Optional[str] = None, token: Optional[str] = None) -> dict:
    base, headers = _build_conn(host, token)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{base}/api/2.1/unity-catalog/{path}", headers=headers, params=params)
        r.raise_for_status()
        return r.json()


# ── catalog level ─────────────────────────────────────────────────────────────

async def list_catalogs(host: Optional[str] = None, token: Optional[str] = None) -> list[dict]:
    data = await _get("catalogs", host=host, token=token)
    return data.get("catalogs", [])


async def get_catalog(catalog_name: str, host: Optional[str] = None, token: Optional[str] = None) -> dict:
    return await _get(f"catalogs/{catalog_name}", host=host, token=token)


# ── schema level ──────────────────────────────────────────────────────────────

async def list_schemas(catalog_name: str, host: Optional[str] = None, token: Optional[str] = None) -> list[dict]:
    data = await _get("schemas", params={"catalog_name": catalog_name}, host=host, token=token)
    return data.get("schemas", [])


async def get_schema(catalog_name: str, schema_name: str, host: Optional[str] = None, token: Optional[str] = None) -> dict:
    return await _get(f"schemas/{catalog_name}.{schema_name}", host=host, token=token)


# ── table level ───────────────────────────────────────────────────────────────

async def list_tables(catalog_name: str, schema_name: str, host: Optional[str] = None, token: Optional[str] = None) -> list[dict]:
    data = await _get(
        "tables",
        params={"catalog_name": catalog_name, "schema_name": schema_name},
        host=host,
        token=token,
    )
    return data.get("tables", [])


async def get_table(catalog_name: str, schema_name: str, table_name: str, host: Optional[str] = None, token: Optional[str] = None) -> dict:
    return await _get(f"tables/{catalog_name}.{schema_name}.{table_name}", host=host, token=token)


# ── doc builder ───────────────────────────────────────────────────────────────

def _col_summary(columns: list[dict]) -> list[dict]:
    return [
        {
            "name": c.get("name"),
            "type": c.get("type_text") or c.get("type_name"),
            "nullable": c.get("nullable", True),
            "comment": c.get("comment"),
        }
        for c in columns
    ]


async def build_catalog_doc(
    catalog_name: str,
    schema_name: Optional[str] = None,
    table_name: Optional[str] = None,
    host: Optional[str] = None,
    token: Optional[str] = None,
) -> dict:
    """
    Build a brief documentation dict.
    Scope narrows based on which args are provided.
    """
    doc: dict = {}

    # ── catalog info ──
    catalog = await get_catalog(catalog_name, host=host, token=token)
    doc["catalog"] = {
        "name": catalog.get("name"),
        "comment": catalog.get("comment"),
        "owner": catalog.get("owner"),
        "created_at": catalog.get("created_at"),
        "metastore_id": catalog.get("metastore_id"),
    }

    # ── schema scope ──
    if schema_name:
        schema = await get_schema(catalog_name, schema_name, host=host, token=token)
        doc["schema"] = {
            "name": schema.get("name"),
            "comment": schema.get("comment"),
            "owner": schema.get("owner"),
        }

        # ── table scope ──
        if table_name:
            table = await get_table(catalog_name, schema_name, table_name, host=host, token=token)
            doc["table"] = {
                "name": table.get("name"),
                "full_name": table.get("full_name"),
                "table_type": table.get("table_type"),
                "data_source_format": table.get("data_source_format"),
                "comment": table.get("comment"),
                "owner": table.get("owner"),
                "storage_location": table.get("storage_location"),
                "columns": _col_summary(table.get("columns", [])),
            }
        else:
            # all tables in schema (summary only)
            tables = await list_tables(catalog_name, schema_name, host=host, token=token)
            doc["tables"] = [
                {
                    "name": t.get("name"),
                    "full_name": t.get("full_name"),
                    "table_type": t.get("table_type"),
                    "comment": t.get("comment"),
                    "column_count": len(t.get("columns", [])),
                }
                for t in tables
            ]
    else:
        # all schemas in catalog (summary only)
        schemas = await list_schemas(catalog_name, host=host, token=token)
        doc["schemas"] = [
            {
                "name": s.get("name"),
                "comment": s.get("comment"),
                "owner": s.get("owner"),
            }
            for s in schemas
        ]

    return doc