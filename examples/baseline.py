import json

print(
    json.dumps(
        {
            "metrics": {"tokens_per_second": 100.0, "ttft_ms": 80.0},
            "checks": {"tool_calling": True, "structured_output": True},
            "details": {"engine": "demo-baseline"},
        }
    )
)
