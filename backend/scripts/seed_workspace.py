"""
One-time workspace seed script.

Run this once after deploying to production (or locally) to:
  1. Create the workspace row in the database
  2. Create a workspace_user row linking your Supabase user to the workspace
  3. Print the exact command to set app_metadata in Supabase

Usage:
    python scripts/seed_workspace.py \
        --name "Terroir" \
        --slug "terroir" \
        --user-id "<your-supabase-user-uuid>"

    # With a custom workspace UUID (idempotent re-runs):
    python scripts/seed_workspace.py \
        --name "Terroir" \
        --slug "terroir" \
        --user-id "<your-supabase-user-uuid>" \
        --workspace-id "<existing-uuid>"

After running, follow the printed instructions to set app_metadata in Supabase.

Requires DATABASE_URL to be set in the environment (or in .env).
"""
from __future__ import annotations

import argparse
import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.workspace import UserRole, Workspace, WorkspaceUser


async def seed(
    name: str,
    slug: str,
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
    role: UserRole,
) -> None:
    db_url = (
        (settings.database_url or "postgresql://postgres:postgres@localhost/incremental_tool_dev")
        .replace("postgresql://", "postgresql+asyncpg://")
        .replace("postgres://", "postgresql+asyncpg://")
    )

    engine = create_async_engine(db_url, echo=False)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async with SessionLocal() as db:
        # ── Workspace ────────────────────────────────────────────────────
        existing_ws = await db.get(Workspace, workspace_id)
        if existing_ws:
            print(f"✓ Workspace already exists: {existing_ws.id} ({existing_ws.slug})")
            workspace = existing_ws
        else:
            # Check slug uniqueness
            slug_q = await db.execute(select(Workspace).where(Workspace.slug == slug))
            if slug_q.scalar_one_or_none():
                raise SystemExit(f"ERROR: A workspace with slug '{slug}' already exists.")

            workspace = Workspace(id=workspace_id, name=name, slug=slug)
            db.add(workspace)
            await db.flush()
            print(f"✓ Created workspace: {workspace.id} ({workspace.slug})")

        # ── WorkspaceUser ────────────────────────────────────────────────
        wu_q = await db.execute(
            select(WorkspaceUser).where(
                WorkspaceUser.workspace_id == workspace.id,
                WorkspaceUser.user_id == user_id,
            )
        )
        wu = wu_q.scalar_one_or_none()
        if wu:
            print(f"✓ WorkspaceUser already exists for user {user_id}")
        else:
            wu = WorkspaceUser(
                workspace_id=workspace.id,
                user_id=user_id,
                role=role,
            )
            db.add(wu)
            print(f"✓ Linked user {user_id} → workspace {workspace.id} as {role.value}")

        await db.commit()

    await engine.dispose()

    # ── Print next steps ─────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("NEXT STEP — set app_metadata in Supabase")
    print("=" * 60)
    print()
    print("Run this in the Supabase SQL editor (or via the Supabase")
    print("Management API / dashboard → Authentication → Users → Edit):")
    print()
    print("  Option A — SQL editor:")
    print(f"""    UPDATE auth.users
    SET raw_app_meta_data = raw_app_meta_data ||
        '{{"workspace_id": "{workspace.id}", "role": "{role.value}"}}'::jsonb
    WHERE id = '{user_id}';""")
    print()
    print("  Option B — Supabase dashboard:")
    print(f"    Authentication → Users → click your user → Edit")
    print(f"    Set app_metadata to:")
    print(f'    {{"workspace_id": "{workspace.id}", "role": "{role.value}"}}')
    print()
    print("After updating, log out and log back in to get a fresh JWT.")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the initial workspace.")
    parser.add_argument("--name", required=True, help="Workspace display name (e.g. 'Terroir')")
    parser.add_argument("--slug", required=True, help="URL-safe slug (e.g. 'terroir')")
    parser.add_argument("--user-id", required=True, help="Your Supabase user UUID")
    parser.add_argument(
        "--workspace-id",
        default=str(uuid.uuid4()),
        help="Workspace UUID (auto-generated if omitted)",
    )
    parser.add_argument(
        "--role",
        default="super_admin",
        choices=["super_admin", "practitioner", "c_suite"],
        help="Your role in the workspace (default: super_admin)",
    )
    args = parser.parse_args()

    asyncio.run(
        seed(
            name=args.name,
            slug=args.slug,
            user_id=uuid.UUID(args.user_id),
            workspace_id=uuid.UUID(args.workspace_id),
            role=UserRole(args.role),
        )
    )


if __name__ == "__main__":
    main()
