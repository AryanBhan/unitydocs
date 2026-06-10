#2 For Local Testing on CLI
"""
Interactive CLI — browse Databricks catalog > schema > table
Run: python explore.py
"""

import httpx

BASE = "http://localhost:8000"


def get(path: str) -> dict:
    r = httpx.get(f"{BASE}{path}", timeout=600)
    r.raise_for_status()
    return r.json()


def pick(items: list[str], label: str) -> str:
    print(f"\n── {label} ──")

    for i, item in enumerate(items, 1):
        print(f"  {i}. {item}")

    while True:
        try:
            choice = int(input(f"\nPick {label} number: "))

            if 1 <= choice <= len(items):
                return items[choice - 1]

            print(f"  Enter 1–{len(items)}")

        except ValueError:
            print("  Enter a number")


def print_table_doc(doc):
    table_name = doc["table"]["name"]
    table_type = doc["table"].get("table_type", "")
    cols = doc["table"]["columns"]
    ai_summary = doc.get("ai_summary", "")

    print(f"\n{'═' * 80}")
    print(f"  CATALOG : {doc['catalog']['name']}")
    print(f"  SCHEMA  : {doc['schema']['name']}")
    print(f"  TABLE   : {table_name} ({table_type})")

    print("\n  SUMMARY")
    print("  " + "─" * 40)
    print(f"  {ai_summary}")

    print(f"\n  COLUMNS ({len(cols)}):\n")

    print(
        f"    {'column name':<28} "
        f"{'data type':<14} "
        f"{'nullable':<10} "
        f"description"
    )

    print(
        f"    {'-' * 28} "
        f"{'-' * 14} "
        f"{'-' * 10} "
        f"{'-' * 35}"
    )

    for col in cols:
        col_name = col["name"]
        data_type = col["type"]
        nullable = "yes" if col.get("nullable") else "no"
        description = col.get("ai_description", "")

        print(
            f"    {col_name:<28} "
            f"{data_type:<14} "
            f"{nullable:<10} "
            f"{description}"
        )

    print(f"{'═' * 80}\n")


def main():
    print("\n╔══════════════════════════════╗")
    print("║  Databricks Catalog Explorer ║")
    print("╚══════════════════════════════╝")

    data = get("/catalogs")
    catalogs = [c["name"] for c in data["catalogs"]]
    catalog = pick(catalogs, "Catalog")

    mode = pick(
        [
            "Single table documentation",
            "Whole schema documentation",
            "Whole catalog documentation"
        ],
        "Documentation Mode"
    )

    if mode == "Whole catalog documentation":
        print("\nGenerating documentation for whole catalog...")

        catalog_doc = get(f"/catalog-doc/{catalog}")

        print(f"\n{'#' * 80}")
        print("CATALOG DOCUMENTATION")
        print(f"CATALOG : {catalog_doc['catalog']}")
        print(f"SCHEMAS : {catalog_doc['schema_count']}")
        print(f"{'#' * 80}")
        #updted code
        if catalog_doc.get("errors"):
            print("\nWARNINGS / SKIPPED ITEMS:")
            for err in catalog_doc["errors"]:
                print(
                    f"  - {err.get('level')} | "
                    f"schema={err.get('schema')} | "
                    f"table={err.get('table', '')} | "
                    f"error={err.get('error')}"
                )

        for schema_item in catalog_doc["schemas"]:
            print(f"\n{'*' * 80}")
            print(f"SCHEMA : {schema_item['schema']}")
            print(f"TABLES : {schema_item['table_count']}")
            print(f"{'*' * 80}")

            for doc in schema_item["tables"]:
                print_table_doc(doc)

        return

    data = get(f"/catalogs/{catalog}/schemas")
    schemas = [s["name"] for s in data["schemas"]]
    schema = pick(schemas, "Schema")

    if mode == "Whole schema documentation":
        print("\nGenerating documentation for whole schema...")

        schema_doc = get(f"/schema-doc/{catalog}/{schema}")

        print(f"\n{'#' * 80}")
        print("SCHEMA DOCUMENTATION")
        print(f"CATALOG : {schema_doc['catalog']}")
        print(f"SCHEMA  : {schema_doc['schema']}")
        print(f"TABLES  : {schema_doc['table_count']}")
        print(f"{'#' * 80}")


        for doc in schema_doc["tables"]:
            print_table_doc(doc)

    else:
        data = get(f"/catalogs/{catalog}/schemas/{schema}/tables")
        tables = [t["name"] for t in data["tables"]]

        if not tables:
            print("\n  No tables found in this schema.")
            return

        table = pick(tables, "Table")

        doc = get(f"/doc/{catalog}/{schema}/{table}")
        print_table_doc(doc)


if __name__ == "__main__":
    main()