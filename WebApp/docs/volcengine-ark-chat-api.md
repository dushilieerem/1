# 项目使用的火山方舟 Chat API 调用说明

> 本文以 `ResearchEngine/researchengine/api/ai_factor.py` 的当前实现为准，只说明 AI 因子生成功能实际发送给火山方舟的请求。
>
> 更新日期：2026-08-13

## 1. 实际请求地址

项目不是调用标准在线推理地址 `/api/v3/chat/completions`，而是使用火山方舟 Agent Plan 地址：

```text
POST https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions
Authorization: Bearer <API Key>
Content-Type: application/json
```

源码中的拼接方式是：

```python
base_url = os.environ.get(
    "AI_FACTOR_BASE_URL", "https://ark.cn-beijing.volces.com/api/plan/v3"
).rstrip("/")

url = f"{base_url}/chat/completions"
```

因此，只有在设置 `AI_FACTOR_BASE_URL` 时，才会改用新的 Base URL；默认最终地址始终是：

```text
https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions
```

## 2. 项目读取的环境变量

| 配置 | 源码规则 |
|---|---|
| API Key | 优先读取 `AI_FACTOR_API_KEY`；未设置时读取 `ARK_API_KEY`。 |
| Base URL | 读取 `AI_FACTOR_BASE_URL`；默认 `https://ark.cn-beijing.volces.com/api/plan/v3`。 |
| 模型 | 读取 `AI_FACTOR_MODEL_ALIAS`；默认 `ark-code-latest`。 |

PowerShell 配置示例：

```powershell
$env:AI_FACTOR_API_KEY = "你的火山方舟 API Key"
$env:AI_FACTOR_MODEL_ALIAS = "ark-code-latest"
```

也可以只设置方舟通用 Key：

```powershell
$env:ARK_API_KEY = "你的火山方舟 API Key"
```

密钥只应由服务端部署环境注入，不能写入代码、文档示例中的实际值、前端或版本库。

## 3. 项目实际发送的请求体

调用入口为：

```text
POST /api/ai/factor-generations
```

服务端将用户的研究想法组装为一条 `system` 消息和一条 `user` 消息，再请求火山方舟。首次请求体的结构等价于：

```json
{
  "model": "ark-code-latest",
  "messages": [
    {
      "role": "system",
      "content": "你是 SVQuant 因子生成器。只输出 JSON 对象，不要 Markdown。JSON 必须有 factor_name、factor_code、description、used_fields、used_library_methods、assumptions、warnings。factor_code 必须只含一个 def 方法，第一个参数为 self。只可读取字段：amount, close, high, low, open, volume。禁止 import、文件、网络、动态执行、双下划线属性和投资建议。不要调用 self.get_data、self.get_field 或任何未列出的 self 方法。"
    },
    {
      "role": "user",
      "content": "研究想法：生成一个 20 日动量并以成交量确认的日频因子\n频率：1d\n股票池：CSI500\n可用内置库：无\n偏好名称：volume_momentum"
    }
  ],
  "temperature": 0.1,
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "svquant_factor_generation",
      "strict": true,
      "schema": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "factor_name",
          "factor_code",
          "description",
          "used_fields",
          "used_library_methods",
          "assumptions",
          "warnings"
        ],
        "properties": {
          "factor_name": {"type": "string"},
          "factor_code": {"type": "string"},
          "description": {"type": "string"},
          "used_fields": {"type": "array", "items": {"type": "string"}},
          "used_library_methods": {"type": "array", "items": {"type": "string"}},
          "assumptions": {"type": "array", "items": {"type": "string"}},
          "warnings": {"type": "array", "items": {"type": "string"}}
        }
      }
    }
  }
}
```

关键点：

- `model` 的值来自 `AI_FACTOR_MODEL_ALIAS`，缺省为 `ark-code-latest`。
- 项目使用非流式调用；没有发送 `stream` 字段。
- `temperature` 固定为 `0.1`，以降低因子代码生成的随机性。
- `response_format` 要求模型返回严格 JSON，而不是 Markdown、自然语言解释或 Python 代码块。

## 4. cURL 复现项目请求

以下示例只用于验证 Agent Plan 对话接口连通性。真实服务会根据 API 请求动态生成两条 `messages`。

```bash
curl --request POST \
  "https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions" \
  --header "Authorization: Bearer ${AI_FACTOR_API_KEY}" \
  --header "Content-Type: application/json" \
  --data @- <<JSON
{
  "model": "${AI_FACTOR_MODEL_ALIAS:-ark-code-latest}",
  "messages": [
    {
      "role": "system",
      "content": "只输出 JSON 对象，不要 Markdown。"
    },
    {
      "role": "user",
      "content": "生成一个 20 日动量因子。"
    }
  ],
  "temperature": 0.1,
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "svquant_factor_generation",
      "strict": true,
      "schema": {
        "type": "object",
        "additionalProperties": false,
        "required": ["factor_name", "factor_code", "description", "used_fields", "used_library_methods", "assumptions", "warnings"],
        "properties": {
          "factor_name": {"type": "string"},
          "factor_code": {"type": "string"},
          "description": {"type": "string"},
          "used_fields": {"type": "array", "items": {"type": "string"}},
          "used_library_methods": {"type": "array", "items": {"type": "string"}},
          "assumptions": {"type": "array", "items": {"type": "string"}},
          "warnings": {"type": "array", "items": {"type": "string"}}
        }
      }
    }
  }
}
JSON
```

## 5. JSON Schema 不兼容时的降级

部分方舟模型可能返回 HTTP `400`，并在错误消息中包含：

```text
response_format.type is not supported
```

项目仅在这个明确场景下自动再试一次。第二次请求保持相同的 `model`、`messages` 和 `temperature`，但删除 `response_format`：

```json
{
  "model": "ark-code-latest",
  "messages": ["与第一次完全相同"],
  "temperature": 0.1
}
```

这不是跳过安全校验：模型响应返回后，项目仍会执行 JSON 解析、Pydantic 字段校验、Python AST 白名单校验和因子包装后的 `compile` 校验。若模型返回其他 HTTP 错误，或降级请求仍失败，项目对外返回 `503`。

## 6. 响应读取方式

项目预期火山方舟返回 OpenAI 兼容的非流式响应，并读取：

```text
choices[0].message.content
```

等价 Python 代码：

```python
body = json.loads(response.read().decode("utf-8"))
raw_content = body["choices"][0]["message"]["content"]
```

`raw_content` 应是一个 JSON 字符串，随后会被解析为因子草稿对象。

## 7. 超时与错误映射

| 项目行为 | 当前实现 |
|---|---|
| HTTP 方法 | `POST` |
| HTTP 客户端 | Python 标准库 `urllib.request`，未使用方舟 SDK。 |
| 超时 | `urlopen(..., timeout=20)`，即 20 秒。 |
| 成功响应 | 从 `choices[0].message.content` 获取模型内容。 |
| JSON Schema 不支持 | 命中指定的 400 错误后，移除 `response_format` 重试一次。 |
| 其他供应商错误 | 映射为本服务的 HTTP `503`。 |
| `TimeoutError` | 映射为本服务的 HTTP `504`。 |

## 8. 调用链总结

```text
AI_FACTOR_API_KEY / ARK_API_KEY
            ↓
AI_FACTOR_BASE_URL（默认 /api/plan/v3）
            ↓
POST /chat/completions
            ↓
model=ark-code-latest + messages + temperature=0.1 + response_format
            ↓
choices[0].message.content
            ↓
JSON / AST / compile 本地校验
```
