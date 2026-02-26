from pathlib import Path
from typing import Any

import verifiers as vf
from datasets import Dataset


class DataPipelineEnv(vf.PythonEnv):
    """RL environment for data transformation tasks using a persistent Python REPL.

    Extends PythonEnv so the agent interacts using the `python` tool which is a persistent
    worker process inside the sandbox with a shared namespace across all calls.
    Task CSV files are uploaded to /data/ before the agent starts. After the agent
    finishes, verify.py runs in the same namespace to score the result.
    pandas and numpy are pre-installed.
    """
    def __init__(
        self,
        dataset_path: str | Path = Path(__file__).parent / "tasks",
        tasks: list[str] | None = None,
        **kwargs,
    ):
        self.dataset_path = Path(dataset_path)
        self.task_names = tasks
        dataset = self._load_dataset()
        rubric = vf.Rubric(funcs=[self.pipeline_reward], weights=[1.0])
        super().__init__(
            pip_install_packages="pandas numpy",
            dataset=dataset,
            rubric=rubric,
            **kwargs,
        )

    def _load_dataset(self) -> Dataset:
        """Build the rollout dataset from task directories.

        Each task directory must contain instruction.md, verify.py, and a data/
        folder. verify_path and data_dir must be hidden from the agent.
        """
        rows = []
        for task_dir in sorted(self.dataset_path.iterdir()):
            if not task_dir.is_dir():
                continue
            if self.task_names and task_dir.name not in self.task_names:
                continue
            instruction_path = task_dir / "instruction.md"
            verify_path = task_dir / "verify.py"
            if not instruction_path.exists() or not verify_path.exists():
                continue
            rows.append({
                "prompt": [{"role": "user", "content": instruction_path.read_text()}],
                "task": task_dir.name,
                "info": {
                    "verify_path": str(verify_path),
                    "data_dir": str(task_dir / "data"),
                },
            })
        return Dataset.from_list(rows)

    async def setup_state(self, state: vf.State, **kwargs: Any) -> vf.State:
        """Create the sandbox and upload the task's data files to /data/.

        Called once per rollout before the agent starts. Waits for the sandbox
        to be ready and then uploads every file in the task's data/ directory.
        """
        state = await super().setup_state(state, **kwargs)
        sandbox_id = state["sandbox_id"]
        sandbox_state = state["sandbox_state"]

        await self._wait_for_sandbox_ready(sandbox_state, sandbox_id)

        data_dir = Path(state["info"]["data_dir"])
        if data_dir.exists():
            await self.sandbox_client.execute_command(
                sandbox_id, "mkdir -p /data", working_dir=None, timeout=30
            )
            for data_file in sorted(data_dir.iterdir()):
                if data_file.is_file():
                    await self.sandbox_client.upload_file(
                        sandbox_id, f"/data/{data_file.name}", str(data_file)
                    )

        return state

    async def post_rollout(self, state: vf.State):
        """Score the agent's work before the destroying the sandbox (rollout over).

        Sends verify.py to the same Python worker the agent was using, so it runs
        in the same namespace and can see all variables the agent set. verify.py
        writes 1.0 or 0.0 to /logs/verifier/reward.txt, this function reads that file and
        stores the value in state for the rubric to read and send to training loop (verifiers API).
        """
        await super().post_rollout(state)

        if isinstance(state.get("error"), vf.InfraError):
            state["pipeline_reward"] = 0.0
            return

        sandbox_id = state.get("sandbox_id")
        python_state = state.get("python_state", {})

        if not sandbox_id or not python_state.get("ready"):
            state["pipeline_reward"] = 0.0
            return

        verify_code = Path(state["info"]["verify_path"]).read_text()
        try:
            await self._send_worker_request(
                sandbox_id, state["sandbox_state"], {"code": verify_code}
            )
        except Exception:
            state["pipeline_reward"] = 0.0
            return

        # Read reward from /logs/verifier/reward.txt
        # verify.py writes "1.0" on pass or "0.0\n<error>" on assertion failure
        try:
            result = await self.sandbox_client.execute_command(
                sandbox_id,
                "cat /logs/verifier/reward.txt 2>/dev/null",
                working_dir=None,
                timeout=10,
            )
            state["pipeline_reward"] = float((result.stdout or "").strip().splitlines()[0])
        except Exception:
            state["pipeline_reward"] = 0.0

    async def pipeline_reward(self, state: vf.State) -> float:
        """Rubric function that returns the reward computed by post_rollout"""
        return state.get("pipeline_reward", 0.0)


def load_environment(
    dataset_path: str | Path = Path(__file__).parent / "tasks",
    tasks: list[str] | None = None,
    max_turns: int = 20,
    timeout_minutes: int = 30,
) -> DataPipelineEnv:
    return DataPipelineEnv(
        dataset_path=dataset_path,
        tasks=tasks,
        max_turns=max_turns,
        timeout_minutes=timeout_minutes,
    )
