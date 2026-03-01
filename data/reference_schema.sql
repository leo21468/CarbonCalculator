-- 税收分类编码 → 排放范围 参考表（由 reference table.xlsx 导入）
-- 执行: sqlite3 data/reference_table.db < data/reference_schema.sql
-- 或由 Python 脚本在导入时自动创建

CREATE TABLE IF NOT EXISTS reference_mapping (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tax_code TEXT NOT NULL,
  scope TEXT NOT NULL,
  exclude_keywords TEXT,
  emission_factor_id TEXT DEFAULT 'default',
  name TEXT,
  source_row INTEGER,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_reference_tax_code ON reference_mapping(tax_code);
CREATE INDEX IF NOT EXISTS idx_reference_scope ON reference_mapping(scope);
