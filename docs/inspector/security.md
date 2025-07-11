# Inspector Security Model

**Version**: 1.0  
**Status**: Current  
**Primary Audience**: Security Engineers, DevOps, Developers

This document describes the security architecture and controls for mcp-agent-inspector.

## 1. Security Principles

1. **Defense in Depth**: Multiple layers of security controls
2. **Least Privilege**: Minimal permissions required for operation
3. **Secure by Default**: Safe configurations out of the box
4. **Zero Trust**: Validate all inputs, even from localhost

## 2. Network Security

### 2.1. Local-Only Binding

By default, Inspector binds only to localhost:

```python
# Default configuration
inspector_config = {
    "host": "127.0.0.1",  # localhost only
    "port": 7800,
    "expose_external": False
}
```

### 2.2. CORS Configuration

Cross-Origin Resource Sharing is strictly controlled:

```python
# 3-understand and later: Configurable allowed origins
cors_config = {
    "allow_origins": ["http://localhost:7800"],  # Default
    "allow_credentials": True,
    "allow_methods": ["GET", "POST"],
    "allow_headers": ["Content-Type", "Authorization"]
}
```

## 3. Authentication & Authorization

### 3.1. Session Token Authentication (3-understand onwards)

Starting in 3-understand milestone, session-token authentication is enabled by default:

```python
# Session token generation
import secrets

def generate_session_token():
    return secrets.token_urlsafe(32)

# Token validation middleware
async def validate_token(request: Request):
    token = request.headers.get("X-Inspector-Token")
    if not token or token != stored_token:
        raise HTTPException(401, "Unauthorized")
```

### 3.2. Role-Based Access Control (6-production)

Future RBAC implementation will support:
- **Observer**: Read-only access to traces and state
- **Developer**: Can pause/resume workflows
- **Admin**: Full control including configuration

### 3.3. MCP Bearer Token Passthrough (6-production)

When an inbound MCP request carries an `Authorization: Bearer…` header, Inspector's
middleware forwards the token to *child* tools **only** if:

1. The configured `auth.forward` flag is true, **and**  
2. The downstream host is in the allow-list.

Until 6-production ships, this flag defaults to *false*.

## 4. Input Validation

### 4.1. Path Traversal Protection

All file access is strictly validated:

```python
def validate_trace_path(session_id: str) -> Path:
    # Sanitize session_id
    clean_id = re.sub(r'[^a-zA-Z0-9-_]', '', session_id)
    
    # Construct path
    trace_path = TRACES_DIR / f"{clean_id}.jsonl.gz"
    
    # Verify within allowed directory
    if not trace_path.resolve().is_relative_to(TRACES_DIR.resolve()):
        raise SecurityError("Path traversal attempt detected")
    
    return trace_path
```

### 4.2. JSON Schema Validation

All API inputs are validated against schemas:

```python
from pydantic import BaseModel, validator

class SignalPayload(BaseModel):
    signal: str
    payload: dict
    
    @validator('signal')
    def validate_signal(cls, v):
        allowed = ["human_input_answer", "pause", "resume"]
        if v not in allowed:
            raise ValueError(f"Invalid signal: {v}")
        return v
```

## 5. Data Protection

### 5.1. Sensitive Data Handling

Inspector never logs or stores:
- API keys or tokens
- Passwords or secrets
- PII without explicit configuration

### 5.2. Trace Data Isolation

Each session's traces are isolated:
- Separate files per session
- No cross-session data access
- Automatic cleanup after retention period

## 6. Known Security Issues & Mitigations

### 6.1. CVE Reference: Inspector RCE (< 0.14.1)

The upstream JavaScript Inspector had an RCE vulnerability due to missing authentication (oligo.security). Our Python implementation mitigates this by:

1. **Default local-only binding** - Not exposed to network
2. **Session token auth (3-understand onwards)** - Required for all state-modifying operations
3. **Input validation** - All user inputs sanitized
4. **No code execution** - Inspector cannot execute arbitrary code

### 6.2. CSRF Protection

Cross-Site Request Forgery protection via:
- Session tokens in headers (not cookies)
- Origin validation for state-changing requests
- SameSite cookie attributes when cookies are used

## 7. Deployment Security

### 7.1. Production Hardening

For production deployments:

```python
# Production configuration
inspector_config = {
    "host": "0.0.0.0",  # If external access needed
    "port": 7800,
    "tls": {
        "enabled": True,
        "cert_file": "/path/to/cert.pem",
        "key_file": "/path/to/key.pem"
    },
    "auth": {
        "enabled": True,
        "provider": "oauth2",  # or "ldap", "saml"
    },
    "cors": {
        "allow_origins": ["https://your-domain.com"]
    }
}
```

### 7.2. Reverse Proxy Setup

Recommended nginx configuration:

```nginx
server {
    listen 443 ssl http2;
    server_name inspector.your-domain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-Content-Type-Options "nosniff";
    add_header X-XSS-Protection "1; mode=block";
    
    location /_mc/ {
        proxy_pass http://127.0.0.1:7800;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Host $host;
        
        # SSE support
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
        proxy_buffering off;
    }
}
```

## 8. Security Checklist

Before deploying Inspector:

- [ ] Change default session token
- [ ] Configure appropriate CORS origins
- [ ] Enable TLS for external access
- [ ] Set up authentication provider
- [ ] Review firewall rules
- [ ] Enable audit logging
- [ ] Set trace data retention policy
- [ ] Test input validation

## 9. Reporting Security Issues

If you discover a security vulnerability:

1. **DO NOT** open a public issue
2. Email security@your-org.com with details
3. Include reproduction steps if possible
4. We aim to respond within 48 hours

## Related Documentation

- [Architecture](architecture.md#security-considerations) - Security design decisions
- [Error Handling](error-handling.md) - Secure error responses
- [Development](development.md) - Secure development practices