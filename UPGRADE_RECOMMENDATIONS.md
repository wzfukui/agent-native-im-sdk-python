# Python SDK 升级建议

根据后端最新更新（v2.3），以下是 Python SDK 需要的优化和新增功能：

## 🔴 必需更新（后端 Breaking Changes）

### 1. 认证环境变量
- `JWT_SECRET` 现在是必需的（无默认值）
- `ADMIN_PASS` 现在是必需的（无默认值）
- 更新示例代码和文档说明环境配置要求

### 2. 错误响应格式
后端现在返回结构化错误：
```json
{
  "error": {
    "code": "ENTITY_NOT_FOUND",
    "message": "entity not found",
    "request_id": "req_xxx",
    "status": 404,
    "timestamp": "2026-03-04T12:00:00Z",
    "method": "GET",
    "path": "/api/v1/entities/123"
  }
}
```

**需要更新**：
- `errors.py`: 增强 `APIError` 类，解析结构化错误
- 添加 `error_code`、`request_id` 等字段

## 🟡 新功能支持

### 1. 实体（Entity）管理
```python
# 新增 API
async def update_entity(entity_id: int, metadata: dict) -> Entity
async def reactivate_entity(entity_id: int) -> Entity
async def get_entity_credentials(entity_id: int) -> dict
async def list_devices() -> list[Device]
async def kick_device(device_id: str) -> None
```

### 2. 任务（Task）系统
```python
@dataclass
class Task:
    id: int
    conversation_id: int
    title: str
    description: str = ""
    priority: str = "medium"  # low/medium/high
    status: str = "pending"   # pending/in_progress/done/cancelled
    assignee_id: int | None = None
    parent_task_id: int | None = None
    due_date: str = ""
    created_at: str = ""
    updated_at: str = ""

# 新增 API
async def create_task(conversation_id: int, task: TaskCreate) -> Task
async def list_tasks(conversation_id: int) -> list[Task]
async def update_task(task_id: int, updates: dict) -> Task
async def delete_task(task_id: int) -> None
```

### 3. 会话归档
```python
# 新增 API
async def list_archived_conversations() -> list[Conversation]
async def archive_conversation(conversation_id: int) -> Conversation
async def unarchive_conversation(conversation_id: int) -> Conversation
```

### 4. WebSocket 事件扩展
```python
# 新增事件类型
@dataclass
class TaskEvent:
    type: str  # task.new/updated/deleted
    task: Task

@dataclass
class PresenceEvent:
    type: str  # presence.online/offline
    entity_id: int
    online: bool

@dataclass
class TypingEvent:
    type: str  # typing
    conversation_id: int
    entity_id: int
    entity_name: str
```

## 🟢 优化建议

### 1. 连接管理优化
- 添加自动重连逻辑（指数退避）
- WebSocket 心跳改进（25秒间隔）
- 设备 ID 持久化

### 2. 消息优化
- 支持乐观更新（先显示后确认）
- 添加消息去重机制
- 实现本地消息队列

### 3. 错误处理增强
```python
class StructuredError(APIError):
    def __init__(self, error_detail: dict):
        self.code = error_detail.get("code", "UNKNOWN")
        self.message = error_detail.get("message", "")
        self.request_id = error_detail.get("request_id", "")
        self.status = error_detail.get("status", 0)
        self.timestamp = error_detail.get("timestamp", "")
        super().__init__(self.status, self.message)
```

### 4. 性能优化
- 批量消息发送
- 连接池管理
- 缓存机制（会话列表、参与者）

## 📝 文档更新

### 需要更新的文档
1. **README.md**
   - 添加任务系统使用示例
   - 更新环境变量配置说明
   - 添加错误处理最佳实践

2. **examples/**
   - 添加 `task_bot.py` 示例
   - 添加 `error_handling.py` 示例
   - 更新现有示例使用新 API

3. **API 参考**
   - 完整的 API 端点列表
   - 请求/响应示例
   - 错误码参考

## 🚀 实施计划

### Phase 1 - 关键修复（立即）
- [ ] 更新错误处理以支持结构化错误
- [ ] 添加必需的环境变量文档
- [ ] 修复认证相关的破坏性变更

### Phase 2 - 新功能（1周内）
- [ ] 实现任务系统 API
- [ ] 添加实体管理端点
- [ ] 支持会话归档功能
- [ ] 扩展 WebSocket 事件处理

### Phase 3 - 优化（2周内）
- [ ] 实现自动重连机制
- [ ] 添加消息去重
- [ ] 性能优化
- [ ] 完善文档和示例

## 兼容性说明

- 最低后端版本要求: v2.3
- Python 版本: 3.11+（当前使用 3.14）
- 向后兼容: 保持现有 API 不变，仅添加新功能

## 测试清单

- [ ] 所有新 API 端点的单元测试
- [ ] WebSocket 重连测试
- [ ] 错误处理测试
- [ ] 性能基准测试
- [ ] 示例代码验证