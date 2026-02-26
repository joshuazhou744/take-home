## Data Pipeline environment

### Run solution or rollouts

Run the `solve.sh` script to test the solution works, from `environments/data_pipeline_python`, should print out "Reward: 1.0"
```
uv add --dev pandas numpy
uv run bash tasks/sales-aggregation/solve.sh
```

Run the verifiers rollouts from root dir:
```
prime env install data_pipeline_python
prime eval run data_pipeline -m openai/gpt-5-nano
```

### Workflow
1. On startup, `load_environment()` is called to create the environment subclass that wraps the `PythonEnv` from verifiers.
- constructs the dataset for the task, loads the rubric function and generates the command to initialize a sandbox with dependencies.
2. Starting a new rollout (task) calls `setup_state` 
- creates a sandbox container using Prime Intellect's API, installs the outlined dependencies from load_environment() (numpy, pandas for this env)
- after confirming the sandbox is ready, uploads the CSV files into the container so they can be read.
3. Agent loop executes the task under the verifiers framework
- behaves similar to a Jupyter notebook.
4. `post_rollout` and verification after the task is done and the outputs are in memory
- reads `verify.py` from the host, sends it to the Python worker in the sandbox which runs it in the same namespace, all variables the agent set are still there
- `verify.py` writes the reward score to `/logs/verifier/reward.txt` (similar to SweHarborEnv), `post_rollout` reads the file and stores the float in the environment state to be sent to the verifiers training loop.