-- ═══════════════════════════════════════════════════════════
-- kb_mp 数据库 Schema（11 表 + 3 角色 + 17 权限码 + 3 种子用户）
-- 适用：MySQL 8.0+ / utf8mb4_unicode_ci
-- ═══════════════════════════════════════════════════════════

-- 1. 创建数据库
DROP DATABASE IF EXISTS kb_mp;
CREATE DATABASE kb_mp DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE kb_mp;

-- ════════════════════════════════════════════════════════════
-- 组织权限域（5 张）
-- ════════════════════════════════════════════════════════════

CREATE TABLE departments (
    id INT NOT NULL AUTO_INCREMENT,
    parent_id INT NULL,
    name VARCHAR(64) NOT NULL,
    leader_id INT NULL,
    sort_order INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_parent (parent_id),
    INDEX idx_leader (leader_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE users (
    id INT NOT NULL AUTO_INCREMENT,
    username VARCHAR(64) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(64) NOT NULL,
    department_id INT NOT NULL,
    status SMALLINT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_username (username),
    INDEX idx_department (department_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE users ADD CONSTRAINT fk_users_department_id
    FOREIGN KEY (department_id) REFERENCES departments(id);
ALTER TABLE departments ADD CONSTRAINT fk_departments_parent_id
    FOREIGN KEY (parent_id) REFERENCES departments(id);
ALTER TABLE departments ADD CONSTRAINT fk_departments_leader_id
    FOREIGN KEY (leader_id) REFERENCES users(id);

CREATE TABLE roles (
    id INT NOT NULL AUTO_INCREMENT,
    role_name VARCHAR(64) NOT NULL,
    role_code VARCHAR(64) NOT NULL,
    description VARCHAR(255) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_role_code (role_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE user_roles (
    id INT NOT NULL AUTO_INCREMENT,
    user_id INT NOT NULL,
    role_id INT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_user_role (user_id, role_id),
    INDEX idx_role (role_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE user_roles ADD CONSTRAINT fk_user_roles_user_id
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE user_roles ADD CONSTRAINT fk_user_roles_role_id
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE;

CREATE TABLE role_permissions (
    id INT NOT NULL AUTO_INCREMENT,
    role_id INT NOT NULL,
    permission_code VARCHAR(64) NOT NULL,
    permission_type VARCHAR(16) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_role_perm (role_id, permission_code),
    INDEX idx_code (permission_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE role_permissions ADD CONSTRAINT fk_role_perm_role_id
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE;

-- ════════════════════════════════════════════════════════════
-- 知识资产域（2 张）
-- ════════════════════════════════════════════════════════════

CREATE TABLE knowledge_units (
    id INT NOT NULL AUTO_INCREMENT,
    unit_code VARCHAR(32) NOT NULL,
    title VARCHAR(255) NOT NULL,
    content MEDIUMTEXT NOT NULL,
    summary VARCHAR(512) NULL,
    category VARCHAR(64) NULL,
    source_file_name VARCHAR(255) NULL,
    file_type VARCHAR(16) NULL,
    file_size BIGINT NULL,
    content_hash VARCHAR(64) NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    creator_id INT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_unit_code (unit_code),
    UNIQUE KEY uk_content_hash (content_hash),
    INDEX idx_category (category),
    INDEX idx_status (status),
    INDEX idx_creator (creator_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE knowledge_units ADD CONSTRAINT fk_units_creator_id
    FOREIGN KEY (creator_id) REFERENCES users(id);

CREATE TABLE unit_permissions (
    id BIGINT NOT NULL AUTO_INCREMENT,
    unit_id INT NOT NULL,
    target_type VARCHAR(16) NOT NULL,
    target_id BIGINT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_unit (unit_id),
    INDEX idx_target (target_type, target_id),
    CONSTRAINT chk_target_consistency CHECK (
        (target_type = 'global' AND target_id IS NULL) OR
        (target_type = 'department' AND target_id IS NOT NULL) OR
        (target_type = 'role' AND target_id IS NOT NULL) OR
        (target_type = 'user' AND target_id IS NOT NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE unit_permissions ADD CONSTRAINT fk_unit_perm_unit_id
    FOREIGN KEY (unit_id) REFERENCES knowledge_units(id) ON DELETE CASCADE;

-- ════════════════════════════════════════════════════════════
-- AI 问答域（2 张）
-- ════════════════════════════════════════════════════════════

CREATE TABLE qa_access_logs (
    id INT NOT NULL AUTO_INCREMENT,
    session_id VARCHAR(64) NOT NULL,
    user_id INT NOT NULL,
    question TEXT NOT NULL,
    answer MEDIUMTEXT NULL,
    recalled_unit_ids_json JSON NULL,
    authorized_unit_ids_json JSON NULL,
    unauthorized_unit_ids_json JSON NULL,
    prompt_tokens INT NULL,
    completion_tokens INT NULL,
    total_tokens INT NULL,
    response_time_ms INT NULL,
    source VARCHAR(16) NOT NULL DEFAULT 'llm',
    related_unit_id BIGINT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_session (session_id),
    INDEX idx_user (user_id),
    INDEX idx_created (created_at),
    INDEX idx_question (question(64)),
    INDEX idx_source (source),
    INDEX idx_source_unit (source, related_unit_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE qa_access_logs ADD CONSTRAINT fk_qa_user_id
    FOREIGN KEY (user_id) REFERENCES users(id);

CREATE TABLE chat_sessions (
    id VARCHAR(64) NOT NULL,
    user_id INT NOT NULL,
    title VARCHAR(255) NULL,
    history_json JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_user_updated (user_id, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE chat_sessions ADD CONSTRAINT fk_chat_user_id
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

-- ════════════════════════════════════════════════════════════
-- 知识沉淀域（2 张）
-- ════════════════════════════════════════════════════════════

CREATE TABLE faqs (
    id INT NOT NULL AUTO_INCREMENT,
    question TEXT NOT NULL,
    question_hash VARCHAR(40) NOT NULL,
    answer MEDIUMTEXT NOT NULL,
    category VARCHAR(64) NULL,
    related_unit_id INT NULL,
    unit_updated_at_snapshot DATETIME NULL,
    source_type VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending_review',
    hit_count BIGINT NOT NULL DEFAULT 0,
    reviewer_id INT NULL,
    reviewed_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_question_hash (question_hash),
    INDEX idx_status_faq (status),
    INDEX idx_source_faq (source_type),
    INDEX idx_related_unit (related_unit_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE faqs ADD CONSTRAINT fk_faq_related_unit
    FOREIGN KEY (related_unit_id) REFERENCES knowledge_units(id);
ALTER TABLE faqs ADD CONSTRAINT fk_faq_reviewer
    FOREIGN KEY (reviewer_id) REFERENCES users(id);

CREATE TABLE knowledge_gaps (
    id INT NOT NULL AUTO_INCREMENT,
    question_pattern VARCHAR(255) NOT NULL,
    question_pattern_hash VARCHAR(40) NOT NULL,
    sample_questions_json JSON NOT NULL,
    ask_count INT NOT NULL DEFAULT 1,
    last_asked_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(16) NOT NULL DEFAULT 'unresolved',
    resolved_unit_id INT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_pattern_hash (question_pattern_hash),
    INDEX idx_status_gap (status),
    INDEX idx_last_asked (last_asked_at),
    INDEX idx_resolved_unit (resolved_unit_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE knowledge_gaps ADD CONSTRAINT fk_gap_resolved_unit
    FOREIGN KEY (resolved_unit_id) REFERENCES knowledge_units(id);

-- ════════════════════════════════════════════════════════════
-- 种子数据：3 部门 + 3 角色 + 17 权限码 + 3 演示用户
-- ════════════════════════════════════════════════════════════

INSERT INTO departments (id, parent_id, name, leader_id, sort_order) VALUES
    (1, NULL, '研发中心', NULL, 0),
    (2, NULL, '产品部', NULL, 1),
    (3, NULL, '运营部', NULL, 2);

-- bcrypt cost=12 哈希
-- admin / Admin@123 → 见下方说明
-- kadmin / Kadmin@123
-- alice / Alice@123
-- 说明：以下哈希为脚本化生成（建议用 scripts/seed.py 生成），此处仅占位
-- 推荐运行 python scripts/seed.py 完成种子数据

INSERT INTO roles (id, role_code, role_name, description) VALUES
    (1, 'system_admin', '系统管理员', '全权限'),
    (2, 'knowledge_admin', '知识管理员', '知识管理子集'),
    (3, 'regular_user', '普通用户', '仅 AI + 知识查询');

-- 17 权限码全集（系统管理员）
INSERT INTO role_permissions (role_id, permission_code, permission_type) VALUES
    (1, 'user:read', 'api'),
    (1, 'user:write', 'api'),
    (1, 'role:read', 'api'),
    (1, 'role:write', 'api'),
    (1, 'dept:read', 'api'),
    (1, 'dept:write', 'api'),
    (1, 'knowledge:read', 'api'),
    (1, 'knowledge:write', 'api'),
    (1, 'knowledge:delete', 'api'),
    (1, 'knowledge:assign_permission', 'api'),
    (1, 'knowledge:check', 'api'),
    (1, 'ai:chat', 'api'),
    (1, 'dashboard:read', 'api'),
    (1, 'faq:read', 'api'),
    (1, 'faq:write', 'api'),
    (1, 'faq:review', 'api'),
    (1, 'gap:read', 'api');

-- 知识管理员（11 权限）
INSERT INTO role_permissions (role_id, permission_code, permission_type) VALUES
    (2, 'knowledge:read', 'api'),
    (2, 'knowledge:write', 'api'),
    (2, 'knowledge:delete', 'api'),
    (2, 'knowledge:assign_permission', 'api'),
    (2, 'knowledge:check', 'api'),
    (2, 'ai:chat', 'api'),
    (2, 'dashboard:read', 'api'),
    (2, 'faq:read', 'api'),
    (2, 'faq:write', 'api'),
    (2, 'faq:review', 'api'),
    (2, 'gap:read', 'api');

-- 普通用户（4 权限）
INSERT INTO role_permissions (role_id, permission_code, permission_type) VALUES
    (3, 'ai:chat', 'api'),
    (3, 'knowledge:read', 'api'),
    (3, 'faq:read', 'api'),
    (3, 'gap:read', 'api');

-- 演示用户（密码哈希由 Python bcrypt 动态生成）
-- 推荐流程：跳过此处 INSERT，运行 `python scripts/seed.py` 自动生成