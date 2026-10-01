import json

print(
    json.dumps(
        {
            "metrics": {"tokens_per_second": 91.0, "ttft_ms": 86.0},
            "checks": {"tool_calling": True, "structured_output": True},
            "details": {"engine": "demo-candidate"},
        }
    )
)
