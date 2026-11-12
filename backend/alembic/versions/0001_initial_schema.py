"""Create Bill Snap database schema and Row Level Security policies."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

_categories = (
    ("Food & Dining", "Meals, cafes, and restaurants", "utensils"),
    ("Shopping", "Retail and personal purchases", "shopping-bag"),
    ("Groceries", "Food and household essentials", "basket"),
    ("Travel", "Transit, lodging, and travel", "plane"),
    ("Healthcare", "Medical and wellness expenses", "heart-pulse"),
    ("Utilities", "Recurring household services", "zap"),
    ("Entertainment", "Leisure and subscriptions", "ticket"),
    ("Education", "Learning and school expenses", "book-open"),
    ("Fuel", "Fuel and vehicle charging", "fuel"),
    ("Others", "Other spending", "circle-ellipsis"),
)


def upgrade():
    op.create_table(
        "profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), sa.ForeignKey("auth.users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("full_name", sa.String(160)),
        sa.Column("email", sa.String(320)),
        sa.Column("preferred_language", sa.String(16), nullable=False, server_default="English"),
        sa.Column("preferred_currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_profiles_email", "profiles", ["email"])

    op.create_table(
        "categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("description", sa.Text()),
        sa.Column("icon", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_categories_name", "categories", ["name"], unique=True)
    for name, description, icon in _categories:
        op.execute(
            sa.text("INSERT INTO categories (name, description, icon) VALUES (:name, :description, :icon)")
            .bindparams(name=name, description=description, icon=icon)
        )

    op.create_table(
        "bills",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("merchant_name", sa.String(200), nullable=False),
        sa.Column("bill_date", sa.Date(), nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("categories.id", ondelete="SET NULL")),
        sa.Column("payment_method", sa.String(60)),
        sa.Column("original_image_path", sa.String(512)),
        sa.Column("sanitized_image_path", sa.String(512)),
        sa.Column("bill_type", sa.String(32), nullable=False, server_default="receipt"),
        sa.Column("review_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("overall_confidence", sa.Numeric(5, 4)),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_bills_user_id", "bills", ["user_id"])
    op.create_index("ix_bills_bill_date", "bills", ["bill_date"])
    op.create_index("ix_bills_category_id", "bills", ["category_id"])
    op.create_index("ix_bills_is_deleted", "bills", ["is_deleted"])
    op.create_index("ix_bills_user_date", "bills", ["user_id", "bill_date"])
    op.create_index("ix_bills_user_merchant", "bills", ["user_id", "merchant_name"])
    op.create_index("ix_bills_user_category", "bills", ["user_id", "category_id"])

    op.create_table(
        "bill_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("bill_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_name", sa.String(240), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("total_price", sa.Numeric(14, 2), nullable=False),
    )
    op.create_index("ix_bill_items_bill_id", "bill_items", ["bill_id"])

    op.create_table(
        "extraction_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("bill_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("merchant_name", sa.String(200)),
        sa.Column("extracted_date", sa.Date()),
        sa.Column("extracted_amount", sa.Numeric(14, 2)),
        sa.Column("extracted_text", sa.Text()),
        sa.Column("merchant_confidence", sa.Numeric(5, 4)),
        sa.Column("date_confidence", sa.Numeric(5, 4)),
        sa.Column("amount_confidence", sa.Numeric(5, 4)),
        sa.Column("category_confidence", sa.Numeric(5, 4)),
        sa.Column("model_name", sa.String(120)),
        sa.Column("extraction_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_extraction_results_bill_id", "extraction_results", ["bill_id"])

    op.create_table(
        "privacy_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bill_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("detected_information_type", sa.String(64), nullable=False),
        sa.Column("redaction_status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_privacy_events_user_id", "privacy_events", ["user_id"])
    op.create_index("ix_privacy_events_bill_id", "privacy_events", ["bill_id"])

    op.create_table(
        "chat_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_chat_conversations_user_id", "chat_conversations", ["user_id"])
    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chat_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_chat_messages_conversation_id", "chat_messages", ["conversation_id"])

    op.create_table(
        "scanner_uploads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bill_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bills.id", ondelete="SET NULL")),
        sa.Column("storage_path", sa.String(512), nullable=False, unique=True),
        sa.Column("mime_type", sa.String(32), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="temporary"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_scanner_uploads_user_id", "scanner_uploads", ["user_id"])
    op.create_index("ix_scanner_uploads_bill_id", "scanner_uploads", ["bill_id"])
    op.create_index("ix_scanner_uploads_storage_path", "scanner_uploads", ["storage_path"], unique=True)
    op.create_index("ix_scanner_uploads_expires_at", "scanner_uploads", ["expires_at"])

    op.create_table(
        "storage_cleanup_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_path", sa.String(512), nullable=False),
        sa.Column("last_error", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_storage_cleanup_jobs_user_id", "storage_cleanup_jobs", ["user_id"])

    op.create_table(
        "account_deletion_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("last_error", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_account_deletion_jobs_user_id", "account_deletion_jobs", ["user_id"], unique=True)

    _enable_rls_policies()


def _enable_rls_policies():
    policy_sql = (
        ("profiles", "profiles_owner", "id = auth.uid()", "id = auth.uid()"),
        ("bills", "bills_owner", "user_id = auth.uid()", "user_id = auth.uid()"),
        (
            "bill_items",
            "bill_items_owner",
            "EXISTS (SELECT 1 FROM bills WHERE bills.id = bill_items.bill_id AND bills.user_id = auth.uid())",
            "EXISTS (SELECT 1 FROM bills WHERE bills.id = bill_items.bill_id AND bills.user_id = auth.uid())",
        ),
        (
            "extraction_results",
            "extraction_results_owner",
            "EXISTS (SELECT 1 FROM bills WHERE bills.id = extraction_results.bill_id AND bills.user_id = auth.uid())",
            "EXISTS (SELECT 1 FROM bills WHERE bills.id = extraction_results.bill_id AND bills.user_id = auth.uid())",
        ),
        ("privacy_events", "privacy_events_owner", "user_id = auth.uid()", "user_id = auth.uid()"),
        ("chat_conversations", "chat_conversations_owner", "user_id = auth.uid()", "user_id = auth.uid()"),
        (
            "chat_messages",
            "chat_messages_owner",
            "EXISTS (SELECT 1 FROM chat_conversations WHERE chat_conversations.id = chat_messages.conversation_id AND chat_conversations.user_id = auth.uid())",
            "EXISTS (SELECT 1 FROM chat_conversations WHERE chat_conversations.id = chat_messages.conversation_id AND chat_conversations.user_id = auth.uid())",
        ),
        ("scanner_uploads", "scanner_uploads_owner", "user_id = auth.uid()", "user_id = auth.uid()"),
        ("storage_cleanup_jobs", "storage_cleanup_jobs_owner", "user_id = auth.uid()", "user_id = auth.uid()"),
        ("account_deletion_jobs", "account_deletion_jobs_owner", "user_id = auth.uid()", "user_id = auth.uid()"),
    )
    for table, policy, using, check in policy_sql:
        op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
        op.execute(
            sa.text(
                f'CREATE POLICY "{policy}" ON "{table}" FOR ALL TO authenticated USING ({using}) WITH CHECK ({check})'
            )
        )
    op.execute(sa.text("ALTER TABLE categories ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("CREATE POLICY categories_read ON categories FOR SELECT TO anon, authenticated USING (true)"))
    op.execute(sa.text("GRANT USAGE ON SCHEMA public TO authenticated, anon"))
    op.execute(
        sa.text(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON profiles, bills, bill_items, extraction_results, "
            "privacy_events, chat_conversations, chat_messages, scanner_uploads, storage_cleanup_jobs, "
            "account_deletion_jobs TO authenticated"
        )
    )
    op.execute(sa.text("GRANT SELECT ON categories TO anon, authenticated"))


def downgrade():
    for table in (
        "account_deletion_jobs",
        "storage_cleanup_jobs",
        "scanner_uploads",
        "chat_messages",
        "chat_conversations",
        "privacy_events",
        "extraction_results",
        "bill_items",
        "bills",
        "categories",
        "profiles",
    ):
        op.drop_table(table)
