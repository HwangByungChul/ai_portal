"""Workflow Execution Runner & Checkpoint Engine."""
import time
from typing import Any
from app.workflows.models import WorkflowDefinition
from app.tools.registry import GLOBAL_TOOL_REGISTRY
from app.ai.routing import GLOBAL_ROUTER
from app.errors import AppError

class WorkflowRunner:
    async def run(self, workflow: WorkflowDefinition, inputs: dict[str, Any]) -> dict[str, Any]:
        execution_order = workflow.get_execution_order()
        node_map = {n.node_id: n for n in workflow.nodes}
        context: dict[str, Any] = dict(inputs)
        checkpoints: list[dict[str, Any]] = []

        start_time = time.time()

        for node_id in execution_order:
            node = node_map[node_id]
            node_start = time.time()
            output: Any = None
            status = "success"
            error_code = None

            try:
                if node.node_type == "input":
                    output = context.get(node.config.get("input_key", "query"), inputs)

                elif node.node_type == "read_tool":
                    tool_id = node.config.get("tool_id", "")
                    # Interpolate args from context
                    args = dict(node.config.get("arguments", {}))
                    for k, v in args.items():
                        if isinstance(v, str) and v.startswith("{{") and v.endswith("}}"):
                            ref_key = v[2:-2].strip()
                            args[k] = context.get(ref_key, "")
                    tool_res = await GLOBAL_TOOL_REGISTRY.invoke(tool_id, args)
                    output = tool_res.get("result", {})

                elif node.node_type == "llm":
                    model_id = node.config.get("model_id", "mock-fast")
                    sys_prompt = node.config.get("system_prompt", "Assistant")
                    user_tmpl = node.config.get("user_template", "{{input}}")
                    
                    # Fill user template safely (no eval)
                    for ctx_k, ctx_v in context.items():
                        user_tmpl = user_tmpl.replace(f"{{{{{ctx_k}}}}}", str(ctx_v))

                    _, provider = GLOBAL_ROUTER.route(model_id)
                    messages = [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": user_tmpl},
                    ]
                    from types import SimpleNamespace
                    from uuid import uuid4

                    async def noop_delta(_): pass
                    claim = SimpleNamespace(call_id=uuid4())
                    outcome = await provider.generate(claim, messages, noop_delta)
                    output = outcome.body

                elif node.node_type == "validate":
                    target_key = node.config.get("target_key", "")
                    val = context.get(target_key)
                    if val is None or val == "":
                        raise AppError("WORKFLOW_VALIDATION_FAILED", 422)
                    output = {"valid": True, "validated_value": val}

                elif node.node_type == "output":
                    output = {
                        "summary": context.get("llm_output", context.get("query", "완료")),
                        "context_snapshot": {k: v for k, v in context.items() if not k.startswith("_")},
                    }

            except AppError as err:
                status = "failed"
                error_code = err.code
                output = {"error": err.code, "status": err.status}
            except Exception as ex:
                status = "failed"
                error_code = "NODE_EXECUTION_ERROR"
                output = {"error": str(ex)}

            elapsed_ms = round((time.time() - node_start) * 1000, 2)
            checkpoint = {
                "node_id": node.node_id,
                "node_type": node.node_type,
                "title": node.title,
                "status": status,
                "output": output,
                "elapsed_ms": elapsed_ms,
                "error_code": error_code,
            }
            checkpoints.append(checkpoint)

            # Store in context for downstream nodes
            context[node.node_id] = output
            if node.node_type == "input":
                context["query"] = output
            elif node.node_type == "read_tool":
                context["tool_output"] = output
            elif node.node_type == "llm":
                context["llm_output"] = output

            if status == "failed":
                break

        total_elapsed_ms = round((time.time() - start_time) * 1000, 2)
        overall_status = "completed" if all(c["status"] == "success" for c in checkpoints) else "failed"

        return {
            "workflow_id": workflow.workflow_id,
            "status": overall_status,
            "total_elapsed_ms": total_elapsed_ms,
            "step_count": len(checkpoints),
            "checkpoints": checkpoints,
            "final_output": checkpoints[-1]["output"] if checkpoints else None,
        }

GLOBAL_WORKFLOW_RUNNER = WorkflowRunner()
